"""Kiểm thử AI Orchestrator: phân tách STAFF_TOOLS vs CUSTOMER_TOOLS, cách ly Chat ID và Provider."""

from decimal import Decimal
import pytest

from app.models.ad_account import AdAccount, AdAccountAssignment
from app.models.campaign import Campaign
from app.models.customer import Customer
from app.models.prepaid import ClientBalance
from app.models.spend import SpendSnapshot, utcnow
from app.services.ai.orchestrator import AIOrchestrator, get_llm_provider
from app.services.ai.providers.base import BaseLLMProvider, LLMMessage, LLMResponse, ToolCall
from app.services.ai.providers.gemini import GeminiProvider
from app.services.ai.providers.mock import MockLLMProvider
from app.services.ai.providers.ollama import OllamaProvider


def test_provider_resolution(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.llm_provider", "gemini")
    p1 = get_llm_provider()
    assert isinstance(p1, GeminiProvider)

    monkeypatch.setattr("app.core.config.settings.llm_provider", "ollama")
    p2 = get_llm_provider()
    assert isinstance(p2, OllamaProvider)

    monkeypatch.setattr("app.core.config.settings.llm_provider", "mock")
    p3 = get_llm_provider()
    assert isinstance(p3, MockLLMProvider)


def test_staff_orchestrator_overview(db):
    """Nhân viên hỏi tổng quan trên Web CRM -> Orchestrator tự gọi STAFF_TOOLS (get_system_overview)."""
    # Tạo dữ liệu mẫu
    cust = Customer(name="Khách Hàng VIP 1", telegram_chat_id="111222")
    db.add(cust)
    db.commit()

    acc = AdAccount(meta_ad_account_id="act_888999", name="TKQC VIP 1", timezone_name="Asia/Ho_Chi_Minh")
    db.add(acc)
    db.commit()

    camp = Campaign(meta_campaign_id="cmp_001", ad_account_id=acc.id, customer_id=cust.id, name="Chiến Dịch Black Friday")
    db.add(camp)
    db.commit()

    snap = SpendSnapshot(campaign_id=camp.id, snapshot_at=utcnow(), spend_amount=Decimal("1500000"), currency="VND")
    db.add(snap)
    db.commit()

    orchestrator = AIOrchestrator(provider=MockLLMProvider())

    res = orchestrator.process_chat(
        db=db,
        message="Cho tôi xem báo cáo tổng quan hệ thống hôm nay",
        role="staff",
        staff_user_id=1,
        staff_username="admin_tester",
    )

    assert res["status"] == "success"
    assert "get_system_overview" in res["tools_used"]
    assert "tra cứu thành công" in res["reply"]


def test_customer_orchestrator_locked_by_chat_id(db):
    """Khách hàng tra cứu số dư trên Telegram -> Chỉ xem được số dư của CHÍNH MÌNH."""
    # Tạo 2 khách hàng riêng biệt
    cust_a = Customer(name="Khách Hàng A", telegram_chat_id="tg_chat_aaa")
    cust_b = Customer(name="Khách Hàng B", telegram_chat_id="tg_chat_bbb")
    db.add_all([cust_a, cust_b])
    db.commit()

    bal_a = ClientBalance(customer_id=cust_a.id, currency="VND", amount=Decimal("20000000"))
    bal_b = ClientBalance(customer_id=cust_b.id, currency="VND", amount=Decimal("999999999"))
    db.add_all([bal_a, bal_b])
    db.commit()

    orchestrator = AIOrchestrator(provider=MockLLMProvider())

    # Khách A hỏi số dư
    res_a = orchestrator.process_chat(
        db=db,
        message="Cho tôi kiểm tra số dư ví hiện tại",
        role="customer",
        telegram_chat_id="tg_chat_aaa",
    )

    assert res_a["status"] == "success"
    assert "get_my_balance" in res_a["tools_used"]
    # Số dư của A (20.000.000) được tra cứu, tuyệt đối không lộ số dư của B (999.999.999)
    assert "20000000" in res_a["reply"]
    assert "999999999" not in res_a["reply"]


def test_customer_orchestrator_unlinked_rejection(db):
    """Telegram Chat ID chưa liên kết -> Bị từ chối truy cập ngay lập tức."""
    orchestrator = AIOrchestrator(provider=MockLLMProvider())

    res = orchestrator.process_chat(
        db=db,
        message="Xem số dư của tôi",
        role="customer",
        telegram_chat_id="stranger_chat_id_999999",
    )

    assert res["status"] == "unauthorized"
    assert "Chưa liên kết tài khoản" in res["reply"]
    assert len(res["tools_used"]) == 0


def test_gemini_provider_preserves_thought_signature_and_raw_content(monkeypatch):
    """Đảm bảo GeminiProvider giữ nguyên raw_content và thought_signature khi gọi tool nhiều lượt."""
    captured_payloads = []

    class MockHttpxClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, params=None, json=None, headers=None):
            captured_payloads.append(json)
            # Lần gọi đầu: trả về tool call kèm thoughtSignature và thinking thought
            if len(captured_payloads) == 1:
                return MockResponse(
                    200,
                    {
                        "candidates": [
                            {
                                "content": {
                                    "role": "model",
                                    "parts": [
                                        {"thought": True, "text": "Tôi cần tra cứu danh sách khách hàng."},
                                        {
                                            "functionCall": {
                                                "name": "get_customers_summary",
                                                "args": {"limit": 10},
                                            },
                                            "thoughtSignature": "test_thought_signature_xyz_789",
                                        },
                                    ],
                                }
                            }
                        ]
                    },
                )
            # Lần gọi thứ hai: trả lời câu trả lời cuối cùng
            return MockResponse(
                200,
                {
                    "candidates": [
                        {
                            "content": {
                                "role": "model",
                                "parts": [{"text": "Hệ thống có tổng cộng 5 khách hàng."}],
                            }
                        }
                    ]
                },
            )

    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data
            self.text = "OK"

        def json(self):
            return self._json

    monkeypatch.setattr("httpx.Client", MockHttpxClient)

    provider = GeminiProvider(api_key="dummy_key", model="gemini-3-flash-preview")

    # Lượt 1: User gửi câu hỏi
    resp1 = provider.chat(messages=[LLMMessage(role="user", content="Tóm tắt khách hàng")])
    assert resp1.has_tool_calls
    assert len(resp1.tool_calls) == 1
    assert resp1.tool_calls[0].name == "get_customers_summary"
    assert resp1.raw_content is not None
    assert resp1.raw_content["parts"][1]["thoughtSignature"] == "test_thought_signature_xyz_789"

    # Lượt 2: Gửi lại tool response
    msg_model = LLMMessage(
        role="assistant",
        raw_content=resp1.raw_content,
        tool_calls=resp1.tool_calls,
    )
    msg_tool = LLMMessage(
        role="tool",
        function_responses=[
            {
                "functionResponse": {
                    "name": "get_customers_summary",
                    "response": {"name": "get_customers_summary", "content": {"total": 5}},
                }
            }
        ],
    )
    resp2 = provider.chat(messages=[
        LLMMessage(role="user", content="Tóm tắt khách hàng"),
        msg_model,
        msg_tool,
    ])

    assert not resp2.has_tool_calls
    assert "5 khách hàng" in resp2.text

    # Kiểm tra payload lượt 2 gửi lên Gemini API
    assert len(captured_payloads) == 2
    contents_turn2 = captured_payloads[1]["contents"]
    assert len(contents_turn2) == 3
    # Turn 0: User prompt
    assert contents_turn2[0]["role"] == "user"
    # Turn 1: Model raw_content được giữ NGUYÊN VẸN, thoughtSignature được bảo toàn
    assert contents_turn2[1]["role"] == "model"
    assert contents_turn2[1]["parts"][1]["thoughtSignature"] == "test_thought_signature_xyz_789"
    # Turn 2: User turn chứa functionResponse (chuẩn REST v1beta)
    assert contents_turn2[2]["role"] == "user"
    assert "functionResponse" in contents_turn2[2]["parts"][0]
    assert contents_turn2[2]["parts"][0]["functionResponse"]["name"] == "get_customers_summary"


def test_orchestrator_multi_turn_history_stripping(db):
    """Lịch sử hội thoại từ client được làm sạch, bỏ qua các turn rỗng hoặc partial tool calls."""
    captured_messages = []

    class DummyProvider(BaseLLMProvider):
        def chat(self, messages, tools=None, system_instruction=""):
            captured_messages.append(messages)
            return LLMResponse(text="Đã nhận câu hỏi mới.")

    orchestrator = AIOrchestrator(provider=DummyProvider())

    history = [
        {"role": "user", "content": "Chào bạn"},
        {"role": "assistant", "content": ""},  # Rỗng -> phải bị lọc bỏ
        {"role": "assistant", "content": "Xin chào! Tôi có thể giúp gì cho bạn?"},
        {"role": "tool", "content": ""},       # Tool dang dở -> phải bị lọc bỏ
        {"role": "user", "content": "   "},    # Khoảng trắng -> phải bị lọc bỏ
    ]

    res = orchestrator.process_chat(
        db=db,
        message="Hôm nay thế nào?",
        role="staff",
        history=history,
    )

    assert res["status"] == "success"
    assert len(captured_messages) == 1
    sent_msgs = captured_messages[0]
    # Chỉ gồm 2 tin hợp lệ từ history + 1 tin mới:
    # 1. user "Chào bạn"
    # 2. assistant "Xin chào! Tôi có thể giúp gì cho bạn?"
    # 3. user "Hôm nay thế nào?"
    assert len(sent_msgs) == 3
    assert sent_msgs[0].content == "Chào bạn"
    assert sent_msgs[1].content == "Xin chào! Tôi có thể giúp gì cho bạn?"
    assert sent_msgs[2].content == "Hôm nay thế nào?"


def test_orchestrator_batches_multiple_tools_in_single_turn(db):
    """Nếu LLM yêu cầu nhiều công cụ trong 1 turn, orchestrator gom thành 1 turn user chứa tất cả functionResponse."""
    calls_count = 0

    class MultiToolProvider(BaseLLMProvider):
        def chat(self, messages, tools=None, system_instruction=""):
            nonlocal calls_count
            calls_count += 1
            if calls_count == 1:
                return LLMResponse(
                    text="",
                    tool_calls=[
                        ToolCall(name="get_system_overview", args={}),
                        ToolCall(name="get_customers_summary", args={"limit": 5}),
                    ],
                    raw_content={
                        "role": "model",
                        "parts": [
                            {"functionCall": {"name": "get_system_overview", "args": {}}},
                            {
                                "functionCall": {"name": "get_customers_summary", "args": {"limit": 5}},
                                "thoughtSignature": "sig_batch_tool_123",
                            },
                        ],
                    },
                )
            # Lần gọi 2: kiểm tra messages gửi vào
            assert len(messages) == 3
            # msg 0: user
            assert messages[0].role == "user"
            # msg 1: model raw_content
            assert messages[1].role == "assistant"
            assert messages[1].raw_content["parts"][1]["thoughtSignature"] == "sig_batch_tool_123"
            # msg 2: tool responses gom chung 1 turn
            assert messages[2].role == "tool"
            assert len(messages[2].function_responses) == 2
            assert messages[2].function_responses[0]["functionResponse"]["name"] == "get_system_overview"
            assert messages[2].function_responses[1]["functionResponse"]["name"] == "get_customers_summary"
            return LLMResponse(text="Đã xử lý xong cả 2 công cụ.")

    orchestrator = AIOrchestrator(provider=MultiToolProvider())

    res = orchestrator.process_chat(
        db=db,
        message="Xem tổng quan và khách hàng",
        role="staff",
    )

    assert res["status"] == "success"
    assert "get_system_overview" in res["tools_used"]
    assert "get_customers_summary" in res["tools_used"]
    assert calls_count == 2

