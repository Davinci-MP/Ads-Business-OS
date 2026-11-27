"""AI Orchestrator dùng chung cho cả Web CRM (STAFF_TOOLS) và Telegram Bot (CUSTOMER_TOOLS).

TUÂN THỦ BẮT BUỘC THEO QUY TẮC DỰ ÁN & REQ-1, REQ-3:
- Hỗ trợ Gemini API hoặc Ollama local qua LLM_PROVIDER.
- Phân tách tuyệt đối 2 bộ Tools: STAFF_TOOLS (CRM) và CUSTOMER_TOOLS (Telegram).
- Khóa cứng danh tính khách hàng theo telegram_chat_id, chống can thiệp chéo.
- Lọc bỏ triệt để password, 2fa_secret, cookie, token trước khi nạp dữ liệu cho AI.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.customer import Customer
from app.services.ai.providers.base import BaseLLMProvider, LLMMessage
from app.services.ai.providers.gemini import GeminiProvider
from app.services.ai.providers.mock import MockLLMProvider
from app.services.ai.providers.ollama import OllamaProvider
from app.services.ai.sanitizer import sanitize_data_for_ai
from app.services.ai.tools.base import ToolContext, ToolDefinition
from app.services.ai.tools.customer_tools import CUSTOMER_TOOLS
from app.services.ai.tools.staff_tools import STAFF_TOOLS

logger = logging.getLogger(__name__)


def get_llm_provider(override_name: Optional[str] = None) -> BaseLLMProvider:
    """Khởi tạo LLM Provider dựa trên biến môi trường LLM_PROVIDER hoặc tham số ghi đè."""
    provider_name = (override_name or settings.llm_provider or "gemini").strip().lower()

    if provider_name == "ollama":
        return OllamaProvider()
    if provider_name == "mock":
        return MockLLMProvider()

    # Mặc định: Google Gemini API
    return GeminiProvider()


class AIOrchestrator:
    """Bộ điều phối AI dùng chung kết nối LLM với các công cụ nghiệp vụ an toàn."""

    def __init__(self, provider: Optional[BaseLLMProvider] = None) -> None:
        self.provider = provider or get_llm_provider()

    def get_system_prompt(self, role: str, context: ToolContext) -> str:
        """Tạo system prompt phù hợp cho từng vai trò người dùng."""
        if role == "staff":
            return (
                "Bạn là AI Copilot thông minh cho Hệ điều hành Ads Business OS.\n"
                "Bạn đang hỗ trợ một nhân viên nội bộ / Media Buyer của công ty.\n"
                "QUY TẮC BẮT BUỘC:\n"
                "1. Trả lời bằng Tiếng Việt chuyên nghiệp, súc tích, định dạng markdown rõ ràng (bảng, danh sách gạch đầu dòng).\n"
                "2. Khi được hỏi về số liệu hệ thống, chiến dịch, khách hàng, hay dàn VIA, HÃY SỬ DỤNG CÁC CÔNG CỤ STAFF_TOOLS được cung cấp để tra cứu dữ liệu mới nhất.\n"
                "3. Luôn sử dụng số liệu từ snapshot VERIFIED mới nhất, không tự ý suy đoán chi tiêu.\n"
                "4. Mọi thông tin nhạy cảm (mật khẩu, cookie, mã 2FA, token) đều đã bị lọc bỏ để đảm bảo an toàn tối đa."
            )

        cust_info = f"tên '{context.customer_name}'" if context.customer_name else "đang đăng nhập"
        return (
            "Bạn là Trợ lý AI Chăm sóc Khách hàng của Ads Business OS trên Telegram.\n"
            f"Bạn đang trò chuyện với khách hàng {cust_info}.\n"
            "QUY TẮC BẢO MẬT & VẬN HÀNH BẮT BUỘC:\n"
            "1. Phục vụ với thái độ nhiệt tình, thân thiện, lịch sự 100% bằng Tiếng Việt.\n"
            "2. CHỈ ĐƯỢC PHÉP tra cứu thông tin (số dư ví, chiến dịch, tài khoản QC, yêu cầu hỗ trợ) của CHÍNH KHÁCH HÀNG NÀY thông qua các công cụ CUSTOMER_TOOLS.\n"
            "3. TUYỆT ĐỐI KHÔNG tiết lộ hay nhắc tới tên, chiến dịch, số dư hay bất kỳ dữ liệu nào của các khách hàng khác.\n"
            "4. Định dạng văn bản thân thiện với Telegram (dùng in đậm, mã code ngắn gọn)."
        )

    def process_chat(
        self,
        db: Session,
        message: str,
        role: str = "staff",
        history: Optional[list[dict[str, str]]] = None,
        staff_user_id: Optional[int] = None,
        staff_username: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        max_turns: int = 5,
    ) -> dict[str, Any]:
        """Thực thi luồng trò chuyện có Tool Calling an toàn."""
        clean_chat_id = str(telegram_chat_id).strip() if telegram_chat_id else None

        # 1. Xác thực danh tính và chuẩn bị Context
        customer_id: Optional[int] = None
        customer_name: Optional[str] = None

        if role == "customer":
            if not clean_chat_id:
                return {
                    "reply": "⛔ Không xác định được Telegram Chat ID để thực hiện yêu cầu.",
                    "tools_used": [],
                    "status": "unauthorized",
                }
            cust = db.scalar(
                select(Customer).where(Customer.telegram_chat_id == clean_chat_id, Customer.is_active == True)
            )
            if not cust:
                return {
                    "reply": (
                        f"⛔ <b>Chưa liên kết tài khoản</b>\n\n"
                        f"Telegram Chat ID <code>{clean_chat_id}</code> của bạn chưa được liên kết với bất kỳ khách hàng nào trên hệ thống Ads Business OS.\n"
                        "Vui lòng liên hệ Quản trị viên để được cấp quyền sử dụng."
                    ),
                    "tools_used": [],
                    "status": "unauthorized",
                }
            customer_id = cust.id
            customer_name = cust.name

        context = ToolContext(
            role=role,
            staff_user_id=staff_user_id,
            staff_username=staff_username,
            telegram_chat_id=clean_chat_id,
            customer_id=customer_id,
            customer_name=customer_name,
        )

        # 2. Lựa chọn bộ công cụ theo vai trò (Cách ly hoàn toàn STAFF vs CUSTOMER)
        if role == "staff":
            available_tools_dict = STAFF_TOOLS
        else:
            available_tools_dict = CUSTOMER_TOOLS

        tools_list = list(available_tools_dict.values())
        system_instruction = self.get_system_prompt(role, context)

        # 3. Chuẩn bị lịch sử tin nhắn
        messages: list[LLMMessage] = []
        if history:
            for item in history:
                r = item.get("role", "user")
                c = (item.get("content") or "").strip()
                # Chỉ nạp các tin nhắn hội thoại thông thường có nội dung text hợp lệ
                # Bỏ qua các lượt gọi tool dang dở từ phiên trước để tránh lỗi thiếu thought_signature
                if not c:
                    continue
                if r in ("user", "human"):
                    messages.append(LLMMessage(role="user", content=c))
                elif r in ("assistant", "model", "ai"):
                    messages.append(LLMMessage(role="assistant", content=c))

        messages.append(LLMMessage(role="user", content=message))

        tools_used: list[str] = []
        turn = 0

        # 4. Agentic Tool Calling Loop
        while turn < max_turns:
            turn += 1
            response = self.provider.chat(
                messages=messages,
                tools=tools_list,
                system_instruction=system_instruction,
            )

            if not response.has_tool_calls:
                return {
                    "reply": response.text,
                    "tools_used": tools_used,
                    "status": "success",
                    "provider": getattr(self.provider, "model", type(self.provider).__name__),
                }

            # Nạp lượt phản hồi của model vào lịch sử
            # QUAN TRỌNG: Giữ nguyên vẹn raw_content (candidate["content"]) từ LLM Provider bao gồm thought_signature
            messages.append(LLMMessage(
                role="assistant",
                content=response.text,
                tool_calls=response.tool_calls,
                raw_content=response.raw_content,
            ))

            function_responses: list[dict[str, Any]] = []
            tool_contents: list[Any] = []

            # Xử lý các tool calls mà LLM yêu cầu
            for tc in response.tool_calls:
                tools_used.append(tc.name)
                tool_def = available_tools_dict.get(tc.name)

                if not tool_def or not tool_def.handler:
                    raw_result = {"error": f"Công cụ '{tc.name}' không tồn tại hoặc không được cấp quyền cho vai trò {role}."}
                else:
                    try:
                        raw_result = tool_def.handler(db=db, context=context, **tc.args)
                    except Exception as exc:
                        logger.exception("Lỗi khi chạy tool %s: %s", tc.name, exc)
                        raw_result = {"status": "error", "error": f"Lỗi nội bộ tool {tc.name}: {str(exc)}"}

                # BẢO MẬT BẮT BUỘC: Lọc bỏ password, 2fa, cookie, token trước khi nạp lại LLM
                sanitized_result = sanitize_data_for_ai(raw_result)
                content_payload = sanitized_result if isinstance(sanitized_result, dict) else {"result": sanitized_result}
                tool_contents.append(content_payload)

                fn_resp_item: dict[str, Any] = {
                    "functionResponse": {
                        "name": tc.name,
                        "response": {
                            "name": tc.name,
                            "content": content_payload,
                        },
                    }
                }
                if tc.call_id:
                    fn_resp_item["functionResponse"]["id"] = tc.call_id
                function_responses.append(fn_resp_item)

            # Nạp một lượt phản hồi duy nhất tập hợp kết quả của tất cả tools đã thực thi
            messages.append(LLMMessage(
                role="tool",
                function_responses=function_responses,
                content=json.dumps(tool_contents[0] if len(tool_contents) == 1 else tool_contents, ensure_ascii=False),
            ))

        # Nếu vượt quá số vòng lặp tối đa
        return {
            "reply": "Đã thực hiện xong các thao tác tra cứu dữ liệu. Vui lòng hỏi cụ thể hơn nếu cần thêm thông tin.",
            "tools_used": tools_used,
            "status": "success",
        }
