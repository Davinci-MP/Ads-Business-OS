import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import desc, select

from app.api.v1.unified import router as unified_router
from app.db import get_db
from app.models.ad_account import AdAccount
from app.models.client_task import (
    ClientTask,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_PENDING,
    TASK_TYPE_ADD_AD_ACCOUNT,
    TASK_TYPE_ADD_MAIL_TO_BM,
    TASK_TYPE_CHECK_BALANCE,
    TASK_TYPE_SETTLE_DEBT,
    TASK_TYPE_TOPUP_BUDGET,
)
from app.models.customer import Customer
from app.models.meta_risk import MetaAccountRisk
from app.services.task_dispatcher import (
    classify_client_message,
    dispatch_client_message,
    match_or_create_customer,
)
from app.services.telegram_bot import TelegramBotAgent
from conftest import make_customer


@pytest.fixture
def test_app(db):
    app = FastAPI()
    app.include_router(unified_router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_classify_client_messages():
    # 1. ADD_MAIL_TO_BM
    msg1 = "Em ơi mời mail marketing@partner.com vào bm 1234567890123 quyền admin giúp anh với"
    t1, d1, p1 = classify_client_message(msg1)
    assert t1 == TASK_TYPE_ADD_MAIL_TO_BM
    assert d1.get("email") == "marketing@partner.com"
    assert d1.get("bm_id") == "1234567890123"
    assert d1.get("role") == "ADMIN"

    # 2. ADD_AD_ACCOUNT
    msg2 = "Cấp thêm tài khoản quảng cáo act_9876543210123 chạy lead nhé"
    t2, d2, p2 = classify_client_message(msg2)
    assert t2 == TASK_TYPE_ADD_AD_ACCOUNT
    assert d2.get("account_id") == "act_9876543210123"

    # 3. SETTLE_DEBT
    msg3 = "Tài khoản act_11223344556677 bị nợ cước 500k, thanh toán gấp giúp anh"
    t3, d3, p3 = classify_client_message(msg3)
    assert t3 == TASK_TYPE_SETTLE_DEBT
    assert p3 in ("HIGH", "URGENT")
    assert d3.get("account_id") == "act_11223344556677"

    # 4. TOPUP_BUDGET
    msg4 = "Anh vừa chuyển khoản 20 triệu nạp tiền ngân sách nhé, kiểm tra giúp anh"
    t4, d4, p4 = classify_client_message(msg4)
    assert t4 == TASK_TYPE_TOPUP_BUDGET

    # 5. CHECK_BALANCE
    msg5 = "Số dư ví hiện tại còn bao nhiêu tiền em ơi?"
    t5, d5, p5 = classify_client_message(msg5)
    assert t5 == TASK_TYPE_CHECK_BALANCE


def test_match_customer_and_dispatch(db):
    # Tạo customer mẫu
    c = Customer(
        name="Công Ty TNHH Alpha Tech",
        telegram_chat_id="99887766",
        telegram_username="alphatech_ceo",
    )
    db.add(c)
    db.commit()

    # 1. Match by chat_id
    matched1 = match_or_create_customer(db, chat_id="99887766")
    assert matched1 is not None
    assert matched1.id == c.id

    # 2. Match by username
    matched2 = match_or_create_customer(db, chat_id="11112222", username="@alphatech_ceo")
    assert matched2 is not None
    assert matched2.id == c.id

    # 3. Match by name in text
    matched3 = match_or_create_customer(db, chat_id="33334444", text="Cho khách hàng Alpha Tech thêm tài khoản nhé")
    assert matched3 is not None
    assert matched3.id == c.id

    # 4. Dispatch client message
    res = dispatch_client_message(
        session=db,
        chat_id="99887766",
        username="alphatech_ceo",
        sender_name="Mr. Alpha",
        message_text="Em mời mail dev@alphatech.vn vào bm 888999000111 với",
    )
    assert res["task_id"] is not None
    assert res["task_type"] == TASK_TYPE_ADD_MAIL_TO_BM
    assert res["customer_id"] == c.id
    assert "dev@alphatech.vn" in res["reply_text"]
    assert "888999000111" in res["reply_text"]

    # Kiểm tra record trong db
    task = db.get(ClientTask, res["task_id"])
    assert task is not None
    assert task.status == TASK_STATUS_PENDING
    assert task.customer_id == c.id


def test_unified_endpoints(test_app, db):
    # Setup test ad account & risk
    acc = AdAccount(meta_ad_account_id="act_unified_01", name="TKQC Unified Test", timezone_name="Asia/Ho_Chi_Minh")
    db.add(acc)
    db.flush()
    risk = MetaAccountRisk(account_id=acc.meta_ad_account_id, locked=False, currency="USD")
    db.add(risk)

    # 1. Overview endpoint
    ov_res = test_app.get("/unified/overview")
    assert ov_res.status_code == 200
    ov_data = ov_res.json()
    assert "connectors" in ov_data
    assert "meta_ads" in ov_data["connectors"]
    assert "binance" in ov_data["connectors"]
    assert "pingpong" in ov_data["connectors"]
    assert "stats" in ov_data

    # 2. Treasury endpoint
    tr_res = test_app.get("/unified/treasury")
    assert tr_res.status_code == 200
    tr_data = tr_res.json()
    assert "total_liquid_usd_estimate" in tr_data
    assert "sources" in tr_data

    # 3. Accounts endpoint
    acc_res = test_app.get("/unified/accounts")
    assert acc_res.status_code == 200
    accounts_list = acc_res.json()
    assert any(a["meta_ad_account_id"] == "act_unified_01" for a in accounts_list)

    # 4. Tasks endpoints
    c = make_customer(db, "Khách Hàng Unified Tasks")
    create_res = test_app.post(
        "/unified/tasks/create",
        json={
            "customer_id": c.id,
            "task_type": "ADD_MAIL_TO_BM",
            "raw_message": "Mời mail partner@gmail.com vào BM",
            "extracted_data": {"email": "partner@gmail.com"},
            "priority": "HIGH",
        },
    )
    assert create_res.status_code == 200
    task_id = create_res.json()["id"]

    # List tasks
    list_res = test_app.get("/unified/tasks")
    assert list_res.status_code == 200
    tasks_list = list_res.json()
    assert any(t["id"] == task_id for t in tasks_list)

    # Update status to IN_PROGRESS then COMPLETED
    patch1 = test_app.post(f"/unified/tasks/{task_id}/status", json={"status": "IN_PROGRESS", "assigned_to": "admin_kythuat"})
    assert patch1.status_code == 200
    assert patch1.json()["status"] == TASK_STATUS_IN_PROGRESS

    patch2 = test_app.post(f"/unified/tasks/{task_id}/status", json={"status": "COMPLETED", "notes": "Đã gửi link mời thành công"})
    assert patch2.status_code == 200
    assert patch2.json()["status"] == TASK_STATUS_COMPLETED


def test_telegram_bot_process_update_with_ai_dispatcher(db):
    bot = TelegramBotAgent()
    # Mock whitelist check to allow chat 123456
    bot.telegram.allowed_chat_ids.add("123456")

    # Gửi tin nhắn thông thường (không phải slash command)
    update = {
        "update_id": 9991,
        "message": {
            "chat": {"id": 123456},
            "from": {"id": 123456, "username": "client_vip", "first_name": "VIP"},
            "text": "Mời mail vip@client.com vào BM 1020304050 quyền admin nhé",
        },
    }
    result = bot.process_update(db, update)
    assert result is not None
    assert result["status"] == "processed"
    assert "vip@client.com" in result["text"]
    assert "1020304050" in result["text"]

    # Kiểm tra task được tạo trong database
    task = db.scalar(select(ClientTask).where(ClientTask.telegram_chat_id == "123456").order_by(desc(ClientTask.id)))
    assert task is not None
    assert task.task_type == TASK_TYPE_ADD_MAIL_TO_BM
