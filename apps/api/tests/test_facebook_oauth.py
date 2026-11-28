"""Kiểm thử OAuth Meta chính thức cho VIA, không dùng cookie hoặc DOM."""

from __future__ import annotations

import hashlib
import hmac

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.v1.oauth import get_oauth_http_client
from app.core.config import settings
from app.db import get_db
from app.main import app
from app.models.via import ViaProfile
from app.services.via_manager import encrypt_via_credentials


def _add_via(db, uid: str, token_status: str = "NONE") -> ViaProfile:
    via = ViaProfile(
        uid=uid,
        profile_name=f"VIA OAuth {uid}",
        profile_dir=f"profiles/{uid}",
        user_agent="Trình duyệt kiểm thử",
        encrypted_credentials=encrypt_via_credentials(
            {"password": "mat-khau-test", "access_token": "token-cu"}
        ),
        token_status=token_status,
    )
    db.add(via)
    db.commit()
    return via


@pytest.fixture
def oauth_config(monkeypatch):
    monkeypatch.setattr(settings, "facebook_app_id", "app-test-123")
    monkeypatch.setattr(settings, "facebook_app_secret", "bi-mat-chi-dung-test")
    monkeypatch.setattr(
        settings,
        "facebook_redirect_uri",
        "http://127.0.0.1:8000/api/v1/oauth/facebook/callback",
    )
    monkeypatch.setattr(
        settings,
        "exchange_ui_origins",
        "http://localhost:3000,http://127.0.0.1:3000",
    )


@pytest.fixture
def oauth_client(db, oauth_config):
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app, base_url="http://127.0.0.1")
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def _login_and_state(client: TestClient, via_id: int) -> tuple[httpx.Response, str]:
    response = client.get(
        "/api/v1/oauth/facebook/login",
        params={"via_id": via_id},
        headers={"origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    authorization_url = response.json()["authorization_url"]
    state = parse_qs(urlparse(authorization_url).query)["state"][0]
    return response, state


def test_login_tao_url_chinh_thuc_va_state_da_ky(oauth_client, db):
    via = _add_via(db, "910000000001")

    response, state = _login_and_state(oauth_client, via.id)
    authorization_url = response.json()["authorization_url"]
    parsed = urlparse(authorization_url)
    query = parse_qs(parsed.query)

    assert parsed.netloc == "www.facebook.com"
    assert parsed.path.endswith("/dialog/oauth")
    assert query["client_id"] == ["app-test-123"]
    assert query["redirect_uri"] == [settings.facebook_redirect_uri]
    assert set(query["scope"][0].split(",")) == {
        "ads_read",
        "business_management",
        "pages_show_list",
    }
    assert state.count(".") == 1
    assert settings.facebook_app_secret not in authorization_url


def test_callback_luu_token_dai_han_duoi_dang_ma_hoa(oauth_client, db):
    via = _add_via(db, "910000000002", token_status="EXPIRED")
    _, state = _login_and_state(oauth_client, via.id)
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        if request.url.path.endswith("/oauth/access_token"):
            if request.url.params.get("grant_type") == "fb_exchange_token":
                assert request.url.params["fb_exchange_token"] == "token-ngan-han"
                return httpx.Response(
                    200,
                    json={"access_token": "token-dai-han", "expires_in": 5_184_000},
                )
            assert request.url.params["code"] == "ma-uy-quyen"
            assert request.url.params["client_secret"] == settings.facebook_app_secret
            return httpx.Response(200, json={"access_token": "token-ngan-han"})
        assert request.url.path.endswith("/me")
        assert request.headers["Authorization"] == "Bearer token-dai-han"
        assert "access_token" not in request.url.params
        # App bật "Require App Secret": /me phải kèm appsecret_proof = HMAC-SHA256(token, secret).
        assert request.url.params["appsecret_proof"] == hmac.new(
            settings.facebook_app_secret.encode(), b"token-dai-han", hashlib.sha256
        ).hexdigest()
        return httpx.Response(200, json={"id": via.uid})

    async def override_http_client():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            yield client

    app.dependency_overrides[get_oauth_http_client] = override_http_client
    response = oauth_client.get(
        "/api/v1/oauth/facebook/callback",
        params={"code": "ma-uy-quyen", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:3000/vias?success=true"
    db.expire_all()
    stored = db.get(ViaProfile, via.id)
    assert stored is not None
    assert stored.access_token == "token-dai-han"
    assert "token-dai-han" not in stored.encrypted_credentials
    assert stored.token_status == "ACTIVE"
    assert stored.last_token_refresh is not None
    assert stored.token_expires_at is not None
    assert len(requests_seen) == 3


def test_callback_tu_choi_state_bi_sua(oauth_client, db):
    via = _add_via(db, "910000000003")
    _, state = _login_and_state(oauth_client, via.id)
    tampered = f"{state[:-1]}{'A' if state[-1] != 'A' else 'B'}"

    response = oauth_client.get(
        "/api/v1/oauth/facebook/callback",
        params={"code": "ma-khong-duoc-dung", "state": tampered},
        follow_redirects=False,
    )

    assert response.status_code == 400
    db.expire_all()
    assert db.get(ViaProfile, via.id).access_token == "token-cu"


def test_callback_huy_cap_quyen_giu_nguyen_token(oauth_client, db):
    via = _add_via(db, "910000000004", token_status="ACTIVE")
    _, state = _login_and_state(oauth_client, via.id)

    response = oauth_client.get(
        "/api/v1/oauth/facebook/callback",
        params={"error": "access_denied", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(
        "/vias?success=false&oauth_error=access_denied"
    )
    db.expire_all()
    stored = db.get(ViaProfile, via.id)
    assert stored.access_token == "token-cu"
    assert stored.token_status == "ACTIVE"


def _callback_voi_me(oauth_client, via_id: int, me_payload: dict):
    """Chạy callback với Meta giả: đổi token thành công, /me trả ``me_payload``."""
    _, state = _login_and_state(oauth_client, via_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/access_token"):
            token = "token-dai-han-moi" if request.url.params.get("grant_type") else "token-ngan"
            return httpx.Response(200, json={"access_token": token, "expires_in": 3600})
        return httpx.Response(200, json=me_payload)

    async def override_http_client():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            yield client

    app.dependency_overrides[get_oauth_http_client] = override_http_client
    return oauth_client.get(
        "/api/v1/oauth/facebook/callback",
        params={"code": "ma-uy-quyen", "state": state},
        follow_redirects=False,
    )


def test_callback_lan_dau_lien_ket_app_scoped_id_khac_uid_that(oauth_client, db):
    """/me trả app-scoped ID (khác UID thật) → vẫn lưu token và liên kết ID + tên."""
    via = _add_via(db, "61594426076661", token_status="NONE")
    response = _callback_voi_me(oauth_client, via.id, {"id": "asid-123", "name": "Nguyen Van A"})

    assert response.headers["location"].endswith("/vias?success=true")
    db.expire_all()
    stored = db.get(ViaProfile, via.id)
    assert stored.access_token == "token-dai-han-moi"
    assert stored.token_status == "ACTIVE"
    assert stored.meta_app_user_id == "asid-123"
    assert stored.meta_user_name == "Nguyen Van A"


def test_callback_cap_lai_bang_tai_khoan_khac_bi_tu_choi(oauth_client, db):
    """VIA đã liên kết ID → lần sau đăng nhập tài khoản khác không được thay token."""
    via = _add_via(db, "910000000005", token_status="ACTIVE")
    via.meta_app_user_id = "asid-da-lien-ket"
    db.commit()
    response = _callback_voi_me(oauth_client, via.id, {"id": "asid-khac", "name": "Nguoi Khac"})

    assert response.status_code == 303
    assert response.headers["location"].endswith("/vias?success=false&oauth_error=uid_mismatch")
    db.expire_all()
    stored = db.get(ViaProfile, via.id)
    assert stored.access_token == "token-cu"
    assert stored.meta_app_user_id == "asid-da-lien-ket"


def test_callback_cap_lai_dung_tai_khoan_da_lien_ket(oauth_client, db):
    via = _add_via(db, "910000000006", token_status="EXPIRED")
    via.meta_app_user_id = "asid-cu"
    db.commit()
    response = _callback_voi_me(oauth_client, via.id, {"id": "asid-cu", "name": "Ten Moi"})

    assert response.headers["location"].endswith("/vias?success=true")
    db.expire_all()
    stored = db.get(ViaProfile, via.id)
    assert stored.access_token == "token-dai-han-moi"
    assert stored.meta_user_name == "Ten Moi"


def test_callback_tai_khoan_da_gan_via_khac_bi_tu_choi(oauth_client, db):
    other = _add_via(db, "910000000007", token_status="ACTIVE")
    other.meta_app_user_id = "asid-chung"
    db.commit()
    via = _add_via(db, "910000000008", token_status="NONE")
    response = _callback_voi_me(oauth_client, via.id, {"id": "asid-chung"})

    assert response.headers["location"].endswith(
        "/vias?success=false&oauth_error=account_linked_elsewhere"
    )
    db.expire_all()
    stored = db.get(ViaProfile, via.id)
    assert stored.access_token == "token-cu"
    assert stored.token_status == "NONE"
    assert stored.meta_app_user_id is None
