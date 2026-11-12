"""Kiểm tra cơ chế Progressive Field Fallback & Endpoint Isolation khi Meta Graph API trả về HTTP 400."""

import httpx
import pytest
from sqlalchemy import select

from app.models.via import SyncedAdAccount, SyncedBM, SyncedPage, ViaProfile
from app.services.sync_engine import fetch_via_ad_account_reports
from app.services.via_manager import (
    clean_meta_token,
    decrypt_via_credentials,
    encrypt_via_credentials,
    is_synthetic_meta_token,
    sync_via_all_assets,
)


def test_clean_meta_token_sanitization():
    """Kiểm tra clean_meta_token loại bỏ ký tự escape JSON, nháy kép, khoảng trắng."""
    # 1. Trailing JSON escape và nháy kép
    raw1 = 'EAABw1234567890abcdef1234567890\\u0025"'
    assert clean_meta_token(raw1) == "EAABw1234567890abcdef1234567890"

    raw2 = "  EAABw1234567890abcdef1234567890' \n"
    assert clean_meta_token(raw2) == "EAABw1234567890abcdef1234567890"

    raw3 = '{\\"token\\": \\"EAAG1234567890abcdef1234567890\\"}'
    assert clean_meta_token(raw3) == "EAAG1234567890abcdef1234567890"

    # 2. Token nội bộ / Synthetic tokens
    assert clean_meta_token("EAAB_LOCAL_1234567890") == "EAAB_LOCAL_1234567890"
    assert clean_meta_token("EAAB_FALLBACK_DEV") == "EAAB_FALLBACK_DEV"
    assert clean_meta_token("EAAB_TEST_TOKEN") == "EAAB_TEST_TOKEN"

    # 3. Token ngắn trong fixture
    assert clean_meta_token("EAAB123") == "EAAB123"

    # 4. None và rỗng
    assert clean_meta_token(None) is None
    assert clean_meta_token("") is None
    assert clean_meta_token("   ") is None


def test_is_synthetic_meta_token():
    """Kiểm tra nhận diện token synthetic/offline dev."""
    assert is_synthetic_meta_token("EAAB_LOCAL_123") is True
    assert is_synthetic_meta_token("EAAB_FALLBACK_456") is True
    assert is_synthetic_meta_token("EAAB_MOCK_789") is True
    assert is_synthetic_meta_token("EAA_MOCK_XYZ") is True
    assert is_synthetic_meta_token("EAAB_REAL_123_LOCAL") is True
    assert is_synthetic_meta_token("EAABw1234567890abcdef1234567890") is False
    assert is_synthetic_meta_token("EAAB_EXPIRED_TOKEN_123") is False


def test_adaccounts_fallback_and_client_bm_mapping(db):
    """Fallback /me vẫn phải được liên kết lại BM khi tài khoản xuất hiện trong client_ad_accounts."""
    via = ViaProfile(
        uid="888001122334455",
        profile_name="VIA Test Fallback 400",
        profile_dir="profiles/via_888001122334455",
        user_agent="Mozilla/5.0 Chrome/131.0.0.0",
        encrypted_credentials=encrypt_via_credentials({
            "access_token": "EAABRealTokenForTestingFallback1234567890",
        }),
        token_status="ACTIVE",
    )
    db.add(via)
    db.commit()

    called_urls = []

    def fake_handler(request: httpx.Request):
        url_str = str(request.url)
        called_urls.append(url_str)

        if "me/adaccounts" in url_str:
            fields = request.url.params.get("fields", "")
            # Nếu có trường mở rộng (adspaymentcycle hoặc funding_source_details) -> trả về 400 Invalid request
            if "adspaymentcycle" in fields or "funding_source_details" in fields:
                return httpx.Response(
                    400,
                    json={
                        "error": {
                            "message": "Invalid request: (#100) Field adspaymentcycle does not exist on type AdAccount",
                            "type": "OAuthException",
                            "code": 100,
                        }
                    },
                )
            # Khi fallback sang trường cơ bản -> trả về 200 thành công
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "act_777888999",
                            "account_id": "777888999",
                            "name": "TKQC Fallback Thanh Cong",
                            "account_status": 1,
                            "currency": "VND",
                            "amount_spent": 1250000.0,
                            "balance": 250000.0,
                            "timezone_name": "Asia/Ho_Chi_Minh",
                        }
                    ]
                },
            )

        if "me/businesses" in url_str:
            return httpx.Response(200, json={"data": [{"id": "BM_SHARED_01", "name": "BM Đối tác"}]})

        if request.url.path.endswith("/BM_SHARED_01"):
            fields = request.url.params.get("fields", "")
            assert "owned_ad_accounts" in fields
            assert "client_ad_accounts" in fields
            return httpx.Response(
                200,
                json={
                    "id": "BM_SHARED_01",
                    "owned_ad_accounts": {"data": []},
                    "client_ad_accounts": {
                        "data": [
                            {
                                "id": "act_777888999",
                                "account_id": "777888999",
                                "name": "TKQC Được Chia Sẻ",
                                "account_status": 1,
                                "currency": "VND",
                                "balance": 250000.0,
                            }
                        ],
                        "paging": {"next": "https://graph.facebook.com/client-page-2"},
                    },
                },
            )

        if "client-page-2" in url_str:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "act_777889000",
                            "account_id": "777889000",
                            "name": "TKQC Chia Sẻ Trang 2",
                            "account_status": 1,
                            "currency": "USD",
                            "balance": 15.0,
                        }
                    ]
                },
            )

        if "me/accounts" in url_str:
            return httpx.Response(200, json={"data": []})

        return httpx.Response(404, json={"error": "Not Found"})

    transport = httpx.MockTransport(fake_handler)

    res = sync_via_all_assets(
        session=db,
        via_id=via.id,
        mock_data=None,
        client_transport=transport,
        mock_mode=False,
    )

    assert res["success"] is True
    assert res["status"] == "ACTIVE"
    assert res["personal_accounts_count"] == 0
    assert res["bm_accounts_count"] == 2

    # Kiểm tra database đã lưu đúng TKQC
    acc = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.act_id == "777888999"))
    assert acc is not None
    assert acc.name == "TKQC Fallback Thanh Cong"
    assert acc.status_dot == "LIVE"
    assert acc.balance == 250000.0
    assert acc.bm_id == "BM_SHARED_01"
    assert acc.account_type == "BM"
    paged_acc = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.act_id == "777889000"))
    assert paged_acc is not None
    assert paged_acc.bm_id == "BM_SHARED_01"


def test_me_businesses_400_does_not_abort_sync(db):
    """Khi /me/businesses trả về 400 (thiếu quyền BM), quá trình đồng bộ không bị huỷ và vẫn lưu TKQC + BM bóc tách."""
    via = ViaProfile(
        uid="888001122334466",
        profile_name="VIA Test BM 400 Isolation",
        profile_dir="profiles/via_888001122334466",
        user_agent="Mozilla/5.0 Chrome/131.0.0.0",
        encrypted_credentials=encrypt_via_credentials({
            "access_token": "EAABTokenWithoutBMPermissions1234567890",
        }),
        token_status="ACTIVE",
    )
    db.add(via)
    db.commit()

    def fake_handler(request: httpx.Request):
        url_str = str(request.url)
        if "me/adaccounts" in url_str:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "act_555444333",
                            "account_id": "555444333",
                            "name": "TKQC Tu BM Bóc Tách",
                            "account_status": 1,
                            "currency": "VND",
                            "amount_spent": 500000.0,
                            "balance": 100000.0,
                            "business": {"id": "BM_EXTRACTED_999", "name": "Holding BM Tu Dong"},
                        }
                    ]
                },
            )

        if "me/businesses" in url_str:
            # Giả lập lỗi 400 / 403 thường gặp trên token cá nhân không có quyền BM
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "Invalid request: (#200) Requires business_management permission to manage the object",
                        "type": "OAuthException",
                        "code": 200,
                    }
                },
            )

        if "me/accounts" in url_str:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "PAGE_TEST_001",
                            "name": "Fanpage Thời Trang Test",
                            "category": "Thương mại điện tử",
                            "fan_count": 888,
                        }
                    ]
                },
            )

        return httpx.Response(404, json={"error": "Not Found"})

    transport = httpx.MockTransport(fake_handler)

    res = sync_via_all_assets(
        session=db,
        via_id=via.id,
        mock_data=None,
        client_transport=transport,
        mock_mode=False,
    )

    assert res["success"] is True
    assert res["status"] == "ACTIVE"
    assert res["bm_accounts_count"] == 1
    assert res["bms_count"] == 1
    assert res["pages_count"] == 1

    # Kiểm tra BM được bóc tách từ business node của TKQC
    bm = db.scalar(select(SyncedBM).where(SyncedBM.bm_id == "BM_EXTRACTED_999"))
    assert bm is not None
    assert bm.name == "Holding BM Tu Dong"

    # Kiểm tra Fanpage được lưu
    page = db.scalar(select(SyncedPage).where(SyncedPage.page_id == "PAGE_TEST_001"))
    assert page is not None
    assert page.name == "Fanpage Thời Trang Test"


def test_no_cookie_header_leaked_to_graph_api(db):
    """Xác nhận không bao giờ gắn Cookie hoặc Origin header khi gọi Graph API."""
    via = ViaProfile(
        uid="888001122334477",
        profile_name="VIA Test Header Isolation",
        profile_dir="profiles/via_888001122334477",
        user_agent="Mozilla/5.0 Chrome/131.0.0.0",
        encrypted_credentials=encrypt_via_credentials({
            "cookie": "c_user=1000888999; xs=super_secret_cookie_string;",
            "access_token": "EAABTokenHeaderIsolationTest1234567890",
        }),
        token_status="ACTIVE",
    )
    db.add(via)
    db.commit()

    captured_headers = []

    def fake_handler(request: httpx.Request):
        captured_headers.append(dict(request.headers))
        return httpx.Response(200, json={"data": []})

    transport = httpx.MockTransport(fake_handler)

    res = sync_via_all_assets(
        session=db,
        via_id=via.id,
        mock_data=None,
        client_transport=transport,
        mock_mode=False,
    )

    assert res["success"] is True
    assert len(captured_headers) >= 1
    for headers in captured_headers:
        assert "cookie" not in headers
        assert "Cookie" not in headers
        assert "origin" not in headers
        assert "Origin" not in headers
        assert "referer" not in headers
        assert "Referer" not in headers


def test_local_synthetic_token_does_not_call_graph(db):
    """Token synthetic EAAB_LOCAL_... không gọi live Graph và giữ nguyên ACTIVE."""
    via = ViaProfile(
        uid="888001122334488",
        profile_name="VIA Test Local Synthetic",
        profile_dir="profiles/via_888001122334488",
        user_agent="Mozilla/5.0 Chrome/131.0.0.0",
        encrypted_credentials=encrypt_via_credentials({
            "access_token": "EAAB_LOCAL_OFFLINE_FIXTURE_12345",
        }),
        token_status="ACTIVE",
    )
    db.add(via)
    db.commit()

    def asserting_handler(request: httpx.Request):
        pytest.fail("Graph API không được phép gọi khi token là EAAB_LOCAL_...")

    transport = httpx.MockTransport(asserting_handler)

    res = sync_via_all_assets(
        session=db,
        via_id=via.id,
        mock_data=None,
        client_transport=transport,
        mock_mode=False,
    )

    assert res["success"] is True
    assert res["status"] == "ACTIVE"
    assert "Token nội bộ/kiểm thử" in res["message"]


def test_cookie_html_fallback_when_token_rejected(db):
    """Khi Token hết hạn hoặc bị từ chối 400/401, tự động làm mới từ Cookie qua Ads Manager HTML."""
    via = ViaProfile(
        uid="888001122334499",
        profile_name="VIA Test Cookie Fallback",
        profile_dir="profiles/via_888001122334499",
        user_agent="Mozilla/5.0 Chrome/131.0.0.0",
        encrypted_credentials=encrypt_via_credentials({
            "cookie": "c_user=1000888999; xs=fresh_valid_session;",
            "access_token": "EAAB_EXPIRED_BAD_TOKEN_12345",
        }),
        token_status="ACTIVE",
    )
    db.add(via)
    db.commit()

    def fake_handler(request: httpx.Request):
        url_str = str(request.url)
        # Giả lập Ads Manager trả về Token mới trong HTML
        if "adsmanager.facebook.com" in url_str:
            html_body = """
            <html>
                <script>
                    window.__accessToken = "EAABFreshTokenExtractedFromCookie1234567890";
                    const x = "EAABFreshTokenExtractedFromCookie1234567890";
                </script>
            </html>
            """
            return httpx.Response(200, text=html_body)

        if "me/adaccounts" in url_str:
            auth = request.headers.get("authorization", "")
            token_in_url = request.url.params.get("access_token", "")
            # Nếu token cũ -> từ chối 400
            if "EAAB_EXPIRED_BAD_TOKEN_12345" in auth or "EAAB_EXPIRED_BAD_TOKEN_12345" in token_in_url:
                return httpx.Response(
                    400,
                    json={
                        "error": {
                            "message": "Invalid request: The access token could not be decrypted",
                            "type": "OAuthException",
                            "code": 190,
                        }
                    },
                )
            # Token mới -> trả về 200
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "act_111999888",
                            "account_id": "111999888",
                            "name": "TKQC Sau Khi Cookie Refresh",
                            "account_status": 1,
                            "currency": "VND",
                            "amount_spent": 1000000.0,
                            "balance": 0.0,
                        }
                    ]
                },
            )

        return httpx.Response(200, json={"data": []})

    transport = httpx.MockTransport(fake_handler)

    res = sync_via_all_assets(
        session=db,
        via_id=via.id,
        mock_data=None,
        client_transport=transport,
        mock_mode=False,
    )

    assert res["success"] is True
    assert res["status"] == "ACTIVE"

    # Token mới phải được cập nhật vào credentials
    db.refresh(via)
    creds = decrypt_via_credentials(via.encrypted_credentials)
    assert creds["access_token"] == "EAABFreshTokenExtractedFromCookie1234567890"

    # TKQC mới được lưu vào DB
    acc = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.act_id == "111999888"))
    assert acc is not None
    assert acc.name == "TKQC Sau Khi Cookie Refresh"


def test_sync_engine_fetch_reports_fallback_on_400(db):
    """Kiểm tra fetch_via_ad_account_reports trong sync_engine cũng có cơ chế fallback khi gặp 400."""
    via = ViaProfile(
        uid="888001122334500",
        profile_name="VIA Test SyncEngine Fallback",
        profile_dir="profiles/via_888001122334500",
        user_agent="Mozilla/5.0 Chrome/131.0.0.0",
        encrypted_credentials=encrypt_via_credentials({
            "access_token": "EAABTokenForSyncEngineTesting1234567890",
        }),
        token_status="ACTIVE",
    )
    db.add(via)
    db.commit()

    attempts = []

    def fake_handler(request: httpx.Request):
        url_str = str(request.url)
        fields = request.url.params.get("fields", "")
        attempts.append(fields)

        # Lần 1 với _META_FIELDS đầy đủ -> trả về 400
        if "adtrust_dsl" in fields or "daily_spend_cap_limit" in fields:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "Invalid request: Field adtrust_dsl does not exist",
                        "type": "OAuthException",
                        "code": 100,
                    }
                },
            )

        # Lần 2 với fallback fields -> trả về 200
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "act_666777888",
                        "name": "TKQC Sync Engine OK",
                        "account_status": 1,
                        "currency": "VND",
                        "amount_spent": 800000,
                        "balance": 150000,
                    }
                ]
            },
        )

    transport = httpx.MockTransport(fake_handler)
    rows = fetch_via_ad_account_reports(via, transport=transport)

    assert len(rows) == 1
    assert rows[0]["id"] == "act_666777888"
    assert len(attempts) >= 2
