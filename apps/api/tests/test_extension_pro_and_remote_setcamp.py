"""Kiểm thử tính năng ADSOS CHECK PRO Extension, Client Binding Keys, Campaign Templates & Remote Task Executor."""

import io
import json
import zipfile
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.customer import Customer
from app.models.extension_remote import CampaignTemplate, ExtensionClientKey, ExtensionRemoteTask, RemoteViaCommand
from app.models.via import AdAccountSnapshot, SyncedAdAccount, SyncedBM, SyncedPage, ViaProfile
from app.services.telegram_bot import TelegramBotAgent
from app.services.via_manager import encrypt_via_credentials


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app, base_url="http://127.0.0.1")
    yield test_client
    app.dependency_overrides.clear()


def test_download_extension_zip(client):
    """Kiểm tra API tải về tiện ích Chrome Extension ADSOS PRO dạng ZIP."""
    res = client.get("/api/v1/vias/download-extension")
    assert res.status_code == 200
    assert "application/zip" in res.headers["content-type"]
    assert "attachment" in res.headers["content-disposition"]

    buf = io.BytesIO(res.content)
    with zipfile.ZipFile(buf, "r") as zf:
        namelist = zf.namelist()
        assert "manifest.json" in namelist
        assert "offscreen.html" in namelist
        assert "js/background.js" in namelist
        assert "js/content.js" in namelist
        assert "js/bridge-main.js" in namelist
        assert "img/icon-128.png" in namelist

        # Kiểm tra nội dung manifest
        manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest_data["manifest_version"] == 3
        assert manifest_data["name"] == "metaOs"
        assert manifest_data["homepage_url"] == "http://127.0.0.1:8000/metaos"


def test_extension_client_keys_crud(client, db):
    """Kiểm tra tạo, liệt kê và xóa Client Binding Key."""
    # Tạo key mới
    res = client.post(
        "/api/v1/vias/extension-client-keys",
        json={"client_name": "Agency Test Hà Nội"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["client_name"] == "Agency Test Hà Nội"
    assert data["api_key"].startswith("ADSOS-CLI-")
    key_id = data["id"]
    api_key = data["api_key"]

    # Liệt kê keys
    list_res = client.get("/api/v1/vias/extension-client-keys")
    assert list_res.status_code == 200
    keys = list_res.json()
    assert any(k["id"] == key_id and k["api_key"] == api_key for k in keys)

    # Xóa key
    del_res = client.delete(f"/api/v1/vias/extension-client-keys/{key_id}")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Kiểm tra key không còn trong DB
    deleted = db.get(ExtensionClientKey, key_id)
    assert deleted is None


def test_extension_ingest_payload(client, db):
    """Kiểm tra Extension Ingest API đồng bộ toàn diện Session, Token, TKQC, BM và Fanpage."""
    # 1. Tạo customer và client key liên kết
    customer = Customer(name="Công ty Thời Trang ABC")
    db.add(customer)
    db.commit()
    db.refresh(customer)

    key_res = client.post(
        "/api/v1/vias/extension-client-keys",
        json={"client_id": customer.id, "client_name": customer.name},
    )
    client_key = key_res.json()["api_key"]

    # 2. Gửi payload ingest từ Extension
    payload = {
        "fb_uid": "100088997766554",
        "client_key": client_key,
        "profile_name": "VIA Khách Thời Trang",
        "cookie": "c_user=100088997766554; xs=45%3Asecretxs;",
        "access_token": "EAABMockTokenForExtensionTesting12345",
        "device_name": "Chrome 133 / Windows 11",
        "ad_accounts": [
            {
                "act_id": "9876543210",
                "name": "TKQC Thời Trang Váy Nữ",
                "account_status": "LIVE",
                "currency": "VND",
                "amount_spent": 12500000,
                "balance": 1850000,
                "threshold": 20000000,
                "spend_cap": 5000000,
                "card_last4": "5566",
                "card_type": "MASTERCARD",
            }
        ],
        "business_managers": [
            {
                "bm_id": "8877665544",
                "name": "BM Doanh Nghiệp Thời Trang",
                "verification_status": "verified",
            }
        ],
        "fanpages": [
            {
                "page_id": "7766554433",
                "name": "Fanpage Váy Xinh",
                "fan_count": 35000,
            }
        ],
    }

    ingest_res = client.post("/api/v1/vias/extension-ingest", json=payload)
    assert ingest_res.status_code == 200
    res_data = ingest_res.json()
    assert res_data["success"] is True
    assert res_data["fb_uid"] == "100088997766554"
    assert res_data["token_status"] == "ACTIVE"
    assert res_data["uid_live_status"] == "LIVE"
    assert res_data["ad_account_count"] == 1
    assert res_data["bm_count"] == 1
    assert res_data["page_count"] == 1
    assert res_data["client_id"] == customer.id

    # 3. Kiểm tra bản ghi trong Database
    via = db.scalar(select(ViaProfile).where(ViaProfile.uid == "100088997766554"))
    assert via is not None
    assert via.client_id == customer.id
    assert via.token_status == "ACTIVE"

    # Kiểm tra SyncedAdAccount & Snapshot
    synced_acc = db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.act_id == "9876543210"))
    assert synced_acc is not None
    assert synced_acc.name == "TKQC Thời Trang Váy Nữ"
    assert synced_acc.payment_card_last4 == "5566"

    snapshot = db.scalar(
        select(AdAccountSnapshot)
        .where(AdAccountSnapshot.act_id == "9876543210")
        .order_by(AdAccountSnapshot.id.desc())
    )
    assert snapshot is not None
    assert snapshot.total_spend == 12500000
    assert snapshot.balance == 1850000


def test_campaign_templates_crud(client, db):
    """Kiểm tra CRUD Mẫu chiến dịch Auto Set Camp."""
    # Tạo mẫu mới
    req_body = {
        "name": "Mẫu Chuyển Đổi Váy Hè 2026",
        "objective": "OUTCOME_SALES",
        "daily_budget": "750000",
        "currency": "VND",
        "targeting_json": '{"age_min": 18, "age_max": 45, "genders": [2]}',
        "page_id": "11223344",
        "status_on_create": "ACTIVE",
    }
    create_res = client.post("/api/v1/vias/campaign-templates", json=req_body)
    assert create_res.status_code == 200
    template_data = create_res.json()
    assert template_data["name"] == "Mẫu Chuyển Đổi Váy Hè 2026"
    assert template_data["daily_budget"] == "750000"
    template_id = template_data["id"]

    # Liệt kê
    list_res = client.get("/api/v1/vias/campaign-templates")
    assert list_res.status_code == 200
    templates = list_res.json()
    assert any(t["id"] == template_id for t in templates)

    # Xóa
    del_res = client.delete(f"/api/v1/vias/campaign-templates/{template_id}")
    assert del_res.status_code == 200
    assert db.get(CampaignTemplate, template_id) is None


def test_extension_tasks_queue_poll_report(client, db):
    """Kiểm tra toàn trình luồng Task từ xa: Queue -> Poll (PENDING->RUNNING) -> Report (COMPLETED)."""
    # 1. Đẩy lệnh tạo campaign từ xa vào hàng đợi
    queue_req = {
        "fb_uid": "100088997766554",
        "task_type": "CREATE_CAMPAIGN",
        "target_act_id": "act_9876543210",
        "payload": {
            "name": "Chiến dịch Test Remote Task",
            "daily_budget": "500000",
            "objective": "OUTCOME_TRAFFIC",
        },
        "requested_by": "DASHBOARD_TEST",
    }
    q_res = client.post("/api/v1/vias/extension-tasks", json=queue_req)
    assert q_res.status_code == 200
    task_id = q_res.json()["task_id"]
    assert q_res.json()["status"] == "PENDING"

    # 2. Extension gọi Poll để nhận tác vụ
    poll_res = client.get(f"/api/v1/vias/extension-tasks/poll?fb_uid=100088997766554")
    assert poll_res.status_code == 200
    tasks = poll_res.json()["tasks"]
    assert any(t["id"] == task_id for t in tasks)

    # Kiểm tra task chuyển sang RUNNING
    task_in_db = db.get(ExtensionRemoteTask, task_id)
    assert task_in_db.status == "RUNNING"

    # 3. Extension báo cáo kết quả hoàn thành
    report_res = client.post(
        f"/api/v1/vias/extension-tasks/{task_id}/report",
        json={
            "status": "COMPLETED",
            "result": {"meta_campaign_id": "2384999888777", "meta_adset_id": "2384999888778"},
        },
    )
    assert report_res.status_code == 200
    assert report_res.json()["success"] is True

    # Kiểm tra trạng thái cuối trong DB
    db.refresh(task_in_db)
    assert task_in_db.status == "COMPLETED"
    assert "2384999888777" in task_in_db.result_json


def test_telegram_bot_setcamp_command(db):
    """Kiểm tra lệnh /setcamp trên Telegram Bot tự động kích hoạt Remote Task cho Extension."""
    # 1. Tạo Template mẫu
    template = CampaignTemplate(
        name="MauFastFood",
        objective="OUTCOME_LEADS",
        daily_budget="400000",
        currency="VND",
        status_on_create="PAUSED",
    )
    db.add(template)

    # Tạo VIA trong DB
    via = ViaProfile(
        uid="1000777111222",
        profile_name="VIA Chạy Fast Food",
        profile_dir="profiles/via_1000777111222",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        encrypted_credentials=encrypt_via_credentials({"cookie": "c_user=1000777111222;", "access_token": "EAAB123"}),
        token_status="ACTIVE",
        uid_live_status="LIVE",
    )
    customer = Customer(name="Khách Set Camp 998877", telegram_chat_id="998877")
    db.add_all([via, customer])
    db.flush()
    db.add(
        SyncedAdAccount(
            via_profile_id=via.id,
            customer_id=customer.id,
            act_id="123987",
            name="TKQC Fast Food",
        )
    )
    db.commit()

    bot = TelegramBotAgent()
    reply = bot.dispatch_command(
        db,
        "/setcamp 123987 MauFastFood",
        actor="test_user",
        chat_id="998877",
    )

    assert "Đã tiếp nhận lệnh Set Camp" in reply

    # Kiểm tra lệnh trong remote_via_commands
    task = db.scalar(
        select(RemoteViaCommand)
        .where(RemoteViaCommand.requested_by_telegram == "998877")
        .order_by(RemoteViaCommand.id.desc())
    )
    assert task is not None
    assert task.command_type == "SET_CAMP"
    assert task.status == "PENDING"
    assert task.act_id == "act_123987"
    assert task.payload["status"] == "PAUSED"
