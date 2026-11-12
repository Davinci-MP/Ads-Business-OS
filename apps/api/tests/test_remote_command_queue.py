from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.connectors.telegram import TelegramBotConnector
from app.core.config import settings
from app.db import get_db
from app.main import app
from app.models.customer import Customer
from app.models.extension_remote import RemoteViaCommand
from app.models.via import SyncedAdAccount, ViaProfile
from app.services.via_manager import encrypt_via_credentials


def _seed_owner(db, *, chat_id: str, act_id: str, uid: str):
    customer = Customer(name=f"Khách Telegram {chat_id}", telegram_chat_id=chat_id)
    via = ViaProfile(
        uid=uid,
        profile_name=f"VIA {uid}",
        profile_dir=f"profiles/{uid}",
        user_agent="Mozilla/5.0 Test",
        encrypted_credentials=encrypt_via_credentials({"access_token": "token-test"}),
        token_status="ACTIVE",
    )
    db.add_all([customer, via])
    db.flush()
    account = SyncedAdAccount(
        via_profile_id=via.id,
        customer_id=customer.id,
        act_id=act_id,
        name=f"TKQC {act_id}",
    )
    db.add(account)
    db.commit()
    return customer, via, account


def _webhook_client(db, monkeypatch):
    connector = TelegramBotConnector(use_mock=True)
    monkeypatch.setattr(settings, "telegram_webhook_secret", "secret-kiem-thu")
    monkeypatch.setattr(
        "app.api.v1.telegram_bot.get_configured_telegram_connector",
        lambda _db: connector,
    )
    monkeypatch.setattr(
        "app.api.v1.remote_commands.get_configured_telegram_connector",
        lambda _db: connector,
    )

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    return TestClient(app), connector


def _post_update(client: TestClient, update_id: int, chat_id: str, text: str):
    return client.post(
        "/api/v1/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret-kiem-thu"},
        json={
            "update_id": update_id,
            "message": {
                "chat": {"id": int(chat_id)},
                "from": {"username": f"khach_{chat_id}"},
                "text": text,
            },
        },
    )


def test_webhook_rejects_unlinked_and_wrong_owner(db, monkeypatch):
    client, connector = _webhook_client(db, monkeypatch)
    try:
        before_count = len(db.scalars(select(RemoteViaCommand.id)).all())
        response = _post_update(client, 810001, "810001", "/setcamp 810000001 Camp kiểm thử")
        assert response.status_code == 200
        assert response.json()["result"]["text"] == (
            "⛔ Lỗi: Telegram của bạn chưa được liên kết với khách hàng nào trên hệ thống."
        )

        _seed_owner(db, chat_id="810002", act_id="810000002", uid="1810000002")
        response = _post_update(client, 810002, "810002", "/set_camp 810000001 Camp không thuộc quyền")
        assert response.status_code == 200
        assert response.json()["result"]["text"] == (
            "⛔ Lỗi: Bạn không có quyền điều khiển tài khoản 810000001."
        )
        assert len(db.scalars(select(RemoteViaCommand.id)).all()) == before_count
        assert len(connector.sent_messages) == 2
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_setcamp_claim_complete_and_cancel_queue(db, monkeypatch):
    customer, via, _ = _seed_owner(
        db,
        chat_id="820001",
        act_id="820000001",
        uid="1820000001",
    )
    client, connector = _webhook_client(db, monkeypatch)
    try:
        accepted = _post_update(
            client,
            820001,
            "820001",
            "/setcamp 820000001 Camp khách hàng tháng 11",
        )
        assert accepted.status_code == 200
        assert "Đã tiếp nhận lệnh Set Camp" in accepted.json()["result"]["text"]

        command = db.scalar(
            select(RemoteViaCommand).where(RemoteViaCommand.customer_id == customer.id)
        )
        assert command is not None
        UUID(command.public_id)
        assert command.via_id == via.id
        assert command.command_type == "SET_CAMP"
        assert command.status == "PENDING"
        assert command.payload["campaign_name"] == "Camp khách hàng tháng 11"
        assert command.payload["status"] == "PAUSED"

        claimed = client.get(
            "/api/v1/remote-commands/pending",
            params={"via_uid": via.uid},
        )
        assert claimed.status_code == 200
        claimed_data = claimed.json()
        assert claimed_data["id"] == command.public_id
        assert claimed_data["status"] == "PROCESSING"
        assert claimed_data["payload"]["status"] == "PAUSED"
        db.refresh(command)
        assert command.status == "PROCESSING"

        completed = client.post(
            f"/api/v1/remote-commands/{command.public_id}/status",
            json={
                "status": "COMPLETED",
                "result": {"campaign_id": "1200000001", "status": "PAUSED"},
                "result_log": "Đã tạo chiến dịch ở trạng thái PAUSED.",
            },
        )
        assert completed.status_code == 200
        db.refresh(command)
        assert command.status == "COMPLETED"
        assert command.result_log == "Đã tạo chiến dịch ở trạng thái PAUSED."
        assert any(
            "Đã lên thành công camp Camp khách hàng tháng 11" in item["text"]
            and "TẠM DỪNG (PAUSED)" in item["text"]
            for item in connector.sent_messages
        )

        second = _post_update(client, 820002, "820001", "/setcamp 820000001 Camp cần hủy")
        assert second.status_code == 200
        pending = db.scalar(
            select(RemoteViaCommand)
            .where(RemoteViaCommand.status == "PENDING", RemoteViaCommand.customer_id == customer.id)
            .order_by(RemoteViaCommand.id.desc())
        )
        cancelled = client.post(f"/api/v1/remote-commands/{pending.public_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["command"]["status"] == "CANCELLED"

        failed_input = _post_update(client, 820003, "820001", "/setcamp 820000001 Camp lỗi Extension")
        assert failed_input.status_code == 200
        failed_command = db.scalar(
            select(RemoteViaCommand)
            .where(RemoteViaCommand.status == "PENDING", RemoteViaCommand.customer_id == customer.id)
            .order_by(RemoteViaCommand.id.desc())
        )
        failed_claim = client.get(
            "/api/v1/remote-commands/pending",
            params={"via_uid": via.uid},
        )
        assert failed_claim.json()["id"] == failed_command.public_id
        failed_report = client.post(
            f"/api/v1/remote-commands/{failed_command.public_id}/status",
            json={"status": "FAILED", "result_log": "Meta từ chối quyền ads_management."},
        )
        assert failed_report.status_code == 200
        assert any(
            "Meta từ chối quyền ads_management." in item["text"]
            for item in connector.sent_messages
        )

        duplicate = _post_update(client, 820003, "820001", "/setcamp 820000001 Không được tạo trùng")
        assert duplicate.status_code == 200
        assert duplicate.json()["result"]["status"] == "duplicate"
        assert len(db.scalars(
            select(RemoteViaCommand).where(RemoteViaCommand.customer_id == customer.id)
        ).all()) == 3
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_webhook_requires_secret(db, monkeypatch):
    client, _ = _webhook_client(db, monkeypatch)
    try:
        response = client.post(
            "/api/v1/telegram/webhook",
            json={"update_id": 830001, "message": {"chat": {"id": 830001}, "text": "/setcamp 1 A"}},
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_db, None)
