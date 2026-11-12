"""TRON connector — CHỈ ĐỌC số dư USDT TRC20 trên ví chung.

Quy tắc (theo chỉ đạo chủ dự án):
- 호출 TrongGrid chỉ đọc: GET `v1/accounts` và POST `wallet/triggerconstantcontract`
  (constant call — KHÔNG broadcast giao dịch, KHÔNG ký, KHÔNG gửi tiền, KHÔNG ghi key).
  Địa chỉ ví qua env `ADSOS_TRON_WALLET_ADDRESS` — KHÔNG hardcode.
- Chưa cấu hình địa chỉ ví → mock mode rõ ràng (không tự đoán địa chỉ, không fallback).
- Chỉ достаточно căn cứ để kết luận số dư: kết quả `balanceOf(address)` trên hợp đồng
  USDT (triggerconstantcontract thành công, uint256 hợp lệ). Danh sách token `trc20`
  của account trên TrongGrid có thể vắng token — vắng ≠ số dư 0; khi trực tiếp đọc được
  `balanceOf` xác định (kể cả số nguyên 0) mới ghi số dư; lỗi/không hợp lệ → None + nguyên nhân.
- Số dư là giá trị TẠI THỜI ĐIỂM ĐỌC: không thuộc tháng/năm của báo cáo, không dùng
  để đối chiếu trực tiếp với L1/đến kỳ của tháng cũ, không cộng L1 nhiều tháng.
- Đọc được ví ≠ đủ cơ sở đối soát toàn doanh nghiệp; giao dịch vẫn phải xử lý theo
  luồng nhập/match riêng (Q-006).
- Token/secret không có trong connector; không log nội dung request/response nhạy cảm.
"""
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import quote

import httpx

# Hợp đồng USDT TRC20 chuẩn trên TRON mainnet (công khai, không phải secret).
USDT_TRC20_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
USDT_DECIMALS = 6

_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


class TronAPIError(Exception):
    """Lỗi gọi TrongGrid — KHÔNG fallback mock khi đã cấu hình địa chỉ ví."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _abi_parameter(address: str) -> str:
    """Mã hoá địa chỉ TRON thành 32 byte ABI cho `_balanceOf(address)` (20 byte địa chỉ thực, MSB padded với 0)."""
    num = 0
    for ch in address:
        num = num * 58 + _BASE58_ALPHABET.index(ch)
    raw = num.to_bytes(25, "big")
    # Địa chỉ TRON Base58Check 25 bytes gồm: 1 byte prefix (0x41) + 20 byte EVM address + 4 byte checksum.
    # Chuẩn ABI Solidity của address: 20 bytes địa chỉ thực, đệm 12 bytes 0 (24 hex zeros) vào bên TRÁI (MSB).
    return raw[1:21].hex().rjust(64, "0")


def _parse_balance_of_hex(hex_value: str) -> str | None:
    """uint256 hex 64 ký tự → chuỗi USDT theo decimals 6; không hợp lệ → `None`."""
    value = (hex_value or "").strip()
    if value[:2] in ("0x", "0X"):
        value = value[2:]
    value = value.rjust(64, "0")
    if len(value) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in value):
        return None
    return _format_usdt(str(int(value, 16)))


def _format_usdt(raw: str) -> str:
    amount = Decimal(raw) / Decimal(10**USDT_DECIMALS)
    normalized = amount.normalize()
    return format(normalized, "f")


class TronConnector:
    api_base = "https://api.trongrid.io"

    def __init__(self, wallet_address: str = "", timeout: float = 15.0, transport: httpx.BaseTransport | None = None, api_key: str = ""):
        self.wallet_address = (wallet_address or "").strip()
        self.contract = USDT_TRC20_CONTRACT
        self._api_key = (api_key or "").strip()
        self._timeout = timeout
        self._transport = transport

    def __repr__(self) -> str:
        key_part = ", api_key=***" if self._api_key else ""
        return f"TronConnector(wallet_address={self.wallet_address!r}{key_part})"

    @property
    def mock_mode(self) -> bool:
        return self.wallet_address == ""

    def _http_client(self) -> httpx.Client:
        return httpx.Client(timeout=self._timeout, transport=self._transport)

    def _headers(self) -> dict:
        return {"TRON-PRO-API-KEY": self._api_key} if self._api_key else {}

    def _guard(self, response: httpx.Response, action: str) -> None:
        if response.status_code == 200:
            return
        try:
            body = response.json()
            detail = str(body.get("error") or body.get("message") or "")
        except ValueError:
            detail = ""
        raise TronAPIError(
            f"{action} TrongGrid HTTP {response.status_code}" + (f": {detail}" if detail else "")
        )

    def _balance_of_direct(self) -> str | None:
        """Đọc trực tiếp `balanceOf(address)` — constant call, không broadcast giao dịch.

        Thành công (result true, uint256 hợp lệ) trả chuỗi USDT theo decimals 6.
        Lỗi HTTP/phản hồi bất thường (`result` false, thiếu `constant_result`,
        hex không chuẩn) → `TronAPIError` — không suy diễn 0.
        """
        body = {
            "owner_address": self.wallet_address,
            "contract_address": USDT_TRC20_CONTRACT,
            "function_selector": "balanceOf(address)",
            "parameter": _abi_parameter(self.wallet_address),
            "visible": True,
        }
        url = f"{self.api_base}/wallet/triggerconstantcontract"
        try:
            with self._http_client() as client:
                response = client.post(url, json=body, headers=self._headers())
        except httpx.HTTPError as exc:
            raise TronAPIError(f"Lỗi kết nối TrongGrid: {type(exc).__name__}") from exc
        self._guard(response, "Lỗi đọc balanceOf")
        try:
            payload = response.json()
        except ValueError as exc:
            raise TronAPIError("Phản hồi đọc balanceOf TrongGrid không phải JSON hợp lệ.") from exc
        result = payload.get("result") or {}
        if not (isinstance(result, dict) and result.get("result") is True):
            raise TronAPIError(
                f"Phản hồi đọc balanceOf không thành công (result={result.get('result')})."
            )
        results = payload.get("constant_result") or []
        raw = results[0] if results else None
        if not isinstance(raw, str) or _parse_balance_of_hex(raw) is None:
            raise TronAPIError("Phản hồi đọc balanceOf không đủ/đúng chuẩn uint256.")
        return _parse_balance_of_hex(raw)

    def wallet_balance(self) -> dict:
        """Số dư USDT TRC20 trên ví tại thời điểm đọc (chỉ đọc, không ghi DB).

        Chưa cấu hình ví → `mode=mock`, `balance=None` (KHÔNG giả 0).
        Ví chưa tồn tại/chưa có dữ liệu account → `balance=None` + note rõ (KHÔNG giả 0).
        Token vắng trong `trc20` → tự đọc trực tiếp `balanceOf` trên hợp đồng USDT;
        đọc thành công → số dư xác định (kể cả "0"); đọc lỗi → `TronAPIError`.
        """
        if self.mock_mode:
            return {
                "mode": "mock", "wallet_configured": False,
                "wallet_address": None, "balance": None, "contract": None,
                "read_at": None,
                "note": "Chưa cấu hình địa chỉ ví (ADSOS_TRON_WALLET_ADDRESS) — chưa đọc được số dư thật, không giả 0.",
            }
        base: dict = {
            "mode": "live", "wallet_configured": True,
            "wallet_address": self.wallet_address,
            "contract": USDT_TRC20_CONTRACT,
            "read_at": _now_iso(),
        }
        url = f"{self.api_base}/v1/accounts/{quote(self.wallet_address)}"
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                headers = {"TRON-PRO-API-KEY": self._api_key} if self._api_key else {}
                response = client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise TronAPIError(f"Lỗi kết nối TrongGrid: {type(exc).__name__}") from exc
        if response.status_code != 200:
            detail = ""
            try:
                body = response.json()
                detail = str(body.get("error") or body.get("message") or "")
            except ValueError:
                detail = ""
            raise TronAPIError(f"Lỗi TrongGrid HTTP {response.status_code}" + (f": {detail}" if detail else ""))
        try:
            payload = response.json()
        except ValueError as exc:
            raise TronAPIError("Phản hồi TrongGrid không phải JSON hợp lệ.") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        if not data:
            return {
                **base,
                "balance": None,
                "note": "Ví chưa tồn tại trên mạng TRON hoặc chưa có dữ liệu tài khoản; hiển thị chưa có dữ liệu, không giả 0.",
            }
        trc20 = data[0].get("trc20") or []
        balance = None
        for entry in trc20:
            if isinstance(entry, dict) and USDT_TRC20_CONTRACT in entry:
                raw = entry[USDT_TRC20_CONTRACT]
                if raw is not None and str(raw).strip().isdigit():
                    balance = _format_usdt(str(raw).strip())
                break
        if balance is None:
            # Token vắng khỏi danh sách `trc20` ≠ số dư 0 — đọc trực tiếp
            # `balanceOf` trên hợp đồng USDT (constant call chỉ đọc) mới kết luận.
            direct = self._balance_of_direct()
            return {**base, "balance": direct, "note": None}
        return {**base, "balance": balance, "note": None}
