import pytest
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from uuid import uuid4

from app.core.config import settings
from app.db import get_db
from app.main import app
from app.models.extension_remote import (
    ExtensionClientKey,
    ExtensionReportEdit,
    ExtensionReportSnapshot,
)
from app.models.via import ViaProfile
from app.services.via_manager import decrypt_via_credentials, ingest_extension_payload


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def extension_key(db):
    row = ExtensionClientKey(client_name="metaOs test", api_key=f"ADSOS-CLI-{uuid4().hex[:16].upper()}")
    db.add(row)
    db.commit()
    return row.api_key


def test_metaos_pages_and_discovery(client):
    assert "metaOs Extension Hub" in client.get("/metaos").text
    assert client.get("/metaos-assets/style.css").status_code == 200
    assert client.get("/popup").status_code == 200
    assert client.get("/bm-popup.html").status_code == 200
    assert client.get("/ext-runner").status_code == 200

    tenant = client.get("/api/tenant-status").json()
    assert tenant == {"active": True, "apiBase": "http://127.0.0.1", "brand": "metaOs"}
    shield = client.get("/api/ext-shield").json()
    assert shield["graphVer"] == settings.meta_api_version


def test_report_share_snapshot_and_edit_lifecycle(client, db, extension_key, monkeypatch):
    monkeypatch.setattr(settings, "meta_writes_enabled", True)
    created = client.post(
        "/api/share",
        json={
            "key": extension_key,
            "accountId": "act_12345",
            "accountName": "Tài khoản test",
            "currency": "vnd",
            "scopeType": "campaigns",
            "campaignIds": ["99"],
        },
    )
    assert created.status_code == 200
    share_id = created.json()["item"]["id"]

    listed = client.get("/api/share/list", params={"key": extension_key}).json()
    assert [item["id"] for item in listed["items"]] == [share_id]
    assert client.post("/api/share/heartbeat", json={"key": extension_key}).json()["updated"] == 1

    snapshot = {"spend": "125000.50", "status": "VERIFIED"}
    first = client.post(
        "/api/share/snapshot", json={"key": extension_key, "id": share_id, "snapshot": snapshot}
    ).json()
    second = client.post(
        "/api/share/snapshot", json={"key": extension_key, "id": share_id, "snapshot": snapshot}
    ).json()
    assert first["created"] is True
    assert second == {"success": True, "snapshotId": first["snapshotId"], "created": False}
    assert db.scalar(select(func.count()).select_from(ExtensionReportSnapshot)) == 1
    assert client.get(f"/api/share/{share_id}").json()["snapshot"] == snapshot

    queued = client.post(
        f"/api/share/{share_id}/edits",
        json={
            "key": extension_key,
            "targetId": "99",
            "accountId": "act_12345",
            "currency": "VND",
            "action": "toggle",
            "params": {"status": "PAUSED"},
        },
    ).json()
    edit_id = queued["editId"]
    pending = client.get("/api/share/pending", params={"key": extension_key}).json()["edits"]
    assert [item["editId"] for item in pending] == [edit_id]
    assert client.get("/api/share/pending", params={"key": extension_key}).json()["edits"] == []

    result = {"key": extension_key, "editId": edit_id, "ok": True, "message": "Đã áp dụng"}
    assert client.post("/api/share/edit-result", json=result).json()["status"] == "COMPLETED"
    assert client.post("/api/share/edit-result", json=result).json()["status"] == "COMPLETED"
    assert client.post("/api/share/edit-result", json={**result, "ok": False}).status_code == 409
    assert db.scalar(select(ExtensionReportEdit).where(ExtensionReportEdit.public_id == edit_id)).result_message == "Đã áp dụng"

    revoked = client.post(
        f"/api/share/{share_id}/status", params={"key": extension_key, "status": "revoked"}
    )
    assert revoked.status_code == 200
    assert client.get(f"/api/share/{share_id}").status_code == 404
    assert db.scalar(select(func.count()).select_from(ExtensionReportSnapshot)) == 1


def test_key_boundary_and_optional_integrations_fail_closed(client, extension_key, monkeypatch):
    monkeypatch.setattr(settings, "meta_writes_enabled", False)
    assert client.get("/api/share/list", params={"key": "wrong"}).status_code == 403
    share_id = client.post(
        "/api/share", json={"key": extension_key, "accountId": "123", "currency": "VND"}
    ).json()["item"]["id"]
    assert client.post(
        f"/api/share/{share_id}/edits",
        json={
            "key": extension_key,
            "targetId": "99",
            "accountId": "123",
            "currency": "VND",
            "action": "toggle",
            "params": {"status": "PAUSED"},
        },
    ).status_code == 403
    monkeypatch.setattr(settings, "ai_api_url", "")
    monkeypatch.setattr(settings, "ai_api_key", "")
    monkeypatch.setattr(settings, "ai_model", "")
    monkeypatch.setattr(settings, "zalo_notify_url", "")
    assert client.post(
        "/api/ai/seeding", json={"licenseKey": extension_key, "caption": "test", "count": 1}
    ).status_code == 503
    assert client.post(
        "/api/zalo/notify", json={"key": extension_key, "message": "test"}
    ).status_code == 503


def test_extension_ingest_never_invents_a_meta_token(db):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="<html>no token</html>"))
    cookie = "c_user=1000777000111; xs=99%3ARealSessionValue123456; datr=datr-live"
    result = ingest_extension_payload(
        db,
        {"fb_uid": "1000777000111", "cookie": cookie, "profile_name": "metaOs cookie only"},
        client_transport=transport,
    )

    assert result["success"] is True
    assert result["token_status"] == "NONE"
    assert result["uid_live_status"] == "LIVE"
    credentials = decrypt_via_credentials(db.get(ViaProfile, result["via_id"]).encrypted_credentials)
    assert credentials["cookie"] == cookie
    assert credentials["access_token"] == ""
