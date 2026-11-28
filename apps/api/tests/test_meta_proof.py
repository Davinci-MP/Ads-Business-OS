import hashlib
import hmac

import httpx
import pytest

from app.core.config import settings
from app.core.meta_proof import (
    add_proof_to_graph_request,
    compute_appsecret_proof,
    with_appsecret_proof,
)

SECRET = "bi-mat-test-khong-that"
TOKEN = "EAAQtoken-cua-app-nay"


def _expected(token: str) -> str:
    return hmac.new(SECRET.encode(), token.encode(), hashlib.sha256).hexdigest()


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings, "facebook_app_secret", SECRET)


def test_compute_dung_chuan_hmac_sha256():
    assert compute_appsecret_proof(TOKEN) == _expected(TOKEN)


@pytest.mark.parametrize("token", ["", None, "EAABtoken-ads-manager", "EAAGtoken-business"])
def test_khong_ky_token_rong_hoac_token_app_noi_bo_facebook(token):
    assert compute_appsecret_proof(token) is None


def test_khong_ky_khi_chua_cau_hinh_secret(monkeypatch):
    monkeypatch.setattr(settings, "facebook_app_secret", "")
    assert compute_appsecret_proof(TOKEN) is None
    assert with_appsecret_proof({"access_token": TOKEN}) == {"access_token": TOKEN}


def test_with_appsecret_proof_them_vao_ban_sao_va_khong_ghi_de():
    original = {"fields": "id", "access_token": TOKEN}
    signed = with_appsecret_proof(original)
    assert signed["appsecret_proof"] == _expected(TOKEN)
    assert "appsecret_proof" not in original
    assert with_appsecret_proof({"access_token": TOKEN, "appsecret_proof": "x"})["appsecret_proof"] == "x"
    assert with_appsecret_proof({"fields": "id"}, TOKEN)["appsecret_proof"] == _expected(TOKEN)


def _client(seen):
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={})

    return httpx.Client(
        transport=httpx.MockTransport(handler),
        event_hooks={"request": [add_proof_to_graph_request]},
    )


def test_hook_ky_token_tren_url_va_header_ke_ca_link_next():
    seen = []
    with _client(seen) as client:
        client.get("https://graph.facebook.com/v26.0/me/adaccounts", params={"access_token": TOKEN})
        client.get(f"https://graph.facebook.com/v26.0/me/adaccounts?access_token={TOKEN}&after=abc")
        client.get("https://graph.facebook.com/v26.0/me", headers={"Authorization": f"Bearer {TOKEN}"})
    assert [r.url.params.get("appsecret_proof") for r in seen] == [_expected(TOKEN)] * 3


def test_hook_bo_qua_host_khac_va_khong_nhan_doi_proof():
    seen = []
    with _client(seen) as client:
        client.get("https://example.com/me", params={"access_token": TOKEN})
        client.get(
            "https://graph.facebook.com/v26.0/me",
            params={"access_token": TOKEN, "appsecret_proof": "san-co"},
        )
        client.get("https://graph.facebook.com/v26.0/me", params={"access_token": "EAAGtoken-business"})
    assert "appsecret_proof" not in seen[0].url.params
    assert seen[1].url.params.get_list("appsecret_proof") == ["san-co"]
    assert "appsecret_proof" not in seen[2].url.params
