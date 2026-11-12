"""Kiểm thử tính năng Multi-BM Auto-Fulfillment & Client Permission Memory Routing."""

import json
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.connectors.telegram import TelegramBotConnector
from app.db import get_db
from app.main import app
from app.models.client_bm_preference import (
    ACCESS_TYPE_FULL,
    ACCESS_TYPE_PARTIAL,
    BM_ROLE_ADMIN,
    BM_ROLE_EMPLOYEE,
    DEFAULT_PARTIAL_PERMISSIONS,
    ClientBMPreference,
)
from app.models.client_task import (
    TASK_STATUS_PENDING,
    TASK_TYPE_ADD_AD_ACCOUNT,
    TASK_TYPE_ADD_MAIL_TO_BM,
    ClientTask,
)
from app.models.customer import Customer
from app.services.auto_fulfillment import (
    AVAILABLE_BMS,
    apply_admin_bm_selection,
    format_auto_routed_notification,
    format_interactive_telegram_prompt,
    get_client_bm_preference,
    route_and_fulfill_client_task,
    save_or_update_client_bm_preference,
)
from app.services.task_dispatcher import dispatch_client_message
from app.services.telegram_bot import TelegramBotAgent


def test_preference_crud(db):
    """Kiểm thử khởi tạo, lưu trữ và cập nhật ClientBMPreference."""
    cust = Customer(name="Công ty TNHH An Phát", telegram_username="anphat_ads", telegram_chat_id="11223344")
    db.add(cust)
    db.commit()

    # Ban đầu chưa có preference
    pref = get_client_bm_preference(db, cust.id)
    assert pref is None

    # Tạo mới preference
    saved = save_or_update_client_bm_preference(
        session=db,
        client_id=cust.id,
        preferred_bm_id="BM_02",
        bm_role=BM_ROLE_ADMIN,
        ad_account_access_type=ACCESS_TYPE_PARTIAL,
        partial_permissions=["MANAGE_CAMPAIGNS", "VIEW_PERFORMANCE"],
        notes="Khách hàng VIP cần quyền admin BM 2",
    )
    assert saved.client_id == cust.id
    assert saved.preferred_bm_id == "BM_02"
    assert saved.bm_role == BM_ROLE_ADMIN
    assert saved.ad_account_access_type == ACCESS_TYPE_PARTIAL
    assert saved.get_permissions_list() == ["MANAGE_CAMPAIGNS", "VIEW_PERFORMANCE"]

    # Cập nhật ghi đè (Override)
    updated = save_or_update_client_bm_preference(
        session=db,
        client_id=cust.id,
        preferred_bm_id="BM_01",
        bm_role=BM_ROLE_EMPLOYEE,
        ad_account_access_type=ACCESS_TYPE_FULL,
    )
    assert updated.preferred_bm_id == "BM_01"
    assert updated.bm_role == BM_ROLE_EMPLOYEE
    assert updated.ad_account_access_type == ACCESS_TYPE_FULL


def test_auto_fulfillment_new_client_interactive_prompt(db):
    """Khi khách hàng mới chưa có preference, hệ thống kích hoạt prompt tương tác gửi tới Admin."""
    cust = Customer(name="Bách Hóa Xanh Media", telegram_username="bhx_media", telegram_chat_id="55667788")
    db.add(cust)
    db.commit()

    # Khách hàng gửi yêu cầu mời mail vào BM
    mock_tg = TelegramBotConnector(admin_chat_id="9999", use_mock=True)
    msg = "Nhờ admin mời mail marketing@bhx.vn vào BM giúp em nhé"

    res = dispatch_client_message(
        session=db,
        chat_id="55667788",
        username="bhx_media",
        message_text=msg,
        telegram_connector=mock_tg,
    )

    task = db.get(ClientTask, res["task_id"])
    assert task is not None
    assert task.task_type == TASK_TYPE_ADD_MAIL_TO_BM

    # Kiểm tra extracted_data có trạng thái AWAITING_ADMIN_PREFERENCE_SELECTION
    extracted = json.loads(task.extracted_data)
    assert extracted["fulfillment"]["status"] == "AWAITING_ADMIN_PREFERENCE_SELECTION"
    assert extracted["fulfillment"]["prompt_sent"] is True

    # Kiểm tra Admin nhận được Telegram Prompt tương tác bằng Tiếng Việt
    assert len(mock_tg.sent_messages) >= 1
    admin_msg = mock_tg.sent_messages[0]["text"]
    assert "YÊU CẦU CẤU HÌNH PHÂN QUYỀN BM" in admin_msg
    assert "BM_01" in admin_msg
    assert "BM_02" in admin_msg
    assert "BM_03" in admin_msg
    assert "EMPLOYEE" in admin_msg
    assert "ADMIN" in admin_msg
    assert "/set_bm" in admin_msg


def test_auto_fulfillment_existing_preference_auto_routed(db):
    """Khi khách hàng đã có preference lưu sẵn, hệ thống tự động ghi nhớ và định tuyến."""
    cust = Customer(name="Tập Đoàn Sao Mai", telegram_username="saomai_corp", telegram_chat_id="77889900")
    db.add(cust)
    db.commit()

    # Đã lưu sẵn preference BM_03, EMPLOYEE, FULL
    save_or_update_client_bm_preference(
        session=db,
        client_id=cust.id,
        preferred_bm_id="BM_03",
        bm_role=BM_ROLE_EMPLOYEE,
        ad_account_access_type=ACCESS_TYPE_FULL,
    )

    mock_tg = TelegramBotConnector(admin_chat_id="9999", use_mock=True)
    msg = "Mời mail dev@saomai.vn vào BM với ạ"

    res = dispatch_client_message(
        session=db,
        chat_id="77889900",
        username="saomai_corp",
        message_text=msg,
        telegram_connector=mock_tg,
    )

    task = db.get(ClientTask, res["task_id"])
    assert task is not None
    extracted = json.loads(task.extracted_data)

    # Đã được tự động định tuyến
    assert extracted["fulfillment"]["status"] == "AUTO_ROUTED"
    assert extracted["fulfillment"]["preferred_bm_id"] == "BM_03"
    assert extracted["fulfillment"]["bm_role"] == "EMPLOYEE"
    assert extracted["fulfillment"]["auto_remembered"] is True

    # Phản hồi cho khách hàng có thông tin định tuyến
    assert "Tự động định tuyến" in res["reply_text"]
    assert "BM 3" in res["reply_text"] or "BM_03" in res["reply_text"]

    # Đã gửi thông báo xác nhận tới Admin
    assert len(mock_tg.sent_messages) >= 1
    admin_alert = mock_tg.sent_messages[0]["text"]
    assert "TỰ ĐỘNG ĐỊNH TUYẾN PHÂN QUYỀN" in admin_alert
    assert "BM 3" in admin_alert or "BM_03" in admin_alert


def test_admin_telegram_set_bm_command(db):
    """Admin dùng lệnh /set_bm trên Telegram để cấu hình và tự động cập nhật các task đang chờ."""
    cust = Customer(name="Công ty Vận Tải Đông Á", telegram_username="donga_logistics", telegram_chat_id="33445566")
    db.add(cust)
    db.commit()

    # Tạo 1 task đang chờ
    task = ClientTask(
        customer_id=cust.id,
        telegram_chat_id="33445566",
        task_type=TASK_TYPE_ADD_MAIL_TO_BM,
        raw_message="Mời email ops@donga.vn",
        extracted_data=json.dumps({"email": "ops@donga.vn"}),
    )
    db.add(task)
    db.commit()

    agent = TelegramBotAgent(telegram_connector=TelegramBotConnector(use_mock=True))

    # Thực thi lệnh /set_bm
    cmd = f"/set_bm {cust.id} BM_02 ADMIN PARTIAL"
    reply = agent.dispatch_command(db, cmd, actor="super_admin")

    assert "ĐÃ THIẾT LẬP & GHI NHỚ CẤU HÌNH PHÂN QUYỀN BM" in reply
    assert "BM 2" in reply or "BM_02" in reply

    # Kiểm tra DB preference đã được lưu
    pref = get_client_bm_preference(db, cust.id)
    assert pref is not None
    assert pref.preferred_bm_id == "BM_02"
    assert pref.bm_role == BM_ROLE_ADMIN
    assert pref.ad_account_access_type == ACCESS_TYPE_PARTIAL

    # Task đang chờ đã được cập nhật
    db.refresh(task)
    task_extracted = json.loads(task.extracted_data)
    assert task_extracted["fulfillment"]["status"] == "AUTO_ROUTED"
    assert task_extracted["fulfillment"]["preferred_bm_id"] == "BM_02"


def test_clients_bm_preferences_api(db):
    """Kiểm thử các API REST: GET /clients/bm-options, PATCH /clients/{id}/bm-preferences."""
    app.dependency_overrides[get_db] = lambda: db
    try:
        cust = Customer(name="Thời Trang Hè Phố", telegram_username="hepho_fashion")
        db.add(cust)
        db.commit()

        client = TestClient(app)

        # 1. Options endpoint
        opt_res = client.get("/api/v1/clients/bm-options")
        assert opt_res.status_code == 200
        opts = opt_res.json()
        assert len(opts["available_bms"]) == 3
        assert len(opts["roles"]) == 2
        assert len(opts["access_types"]) == 2

        # 2. Get initial preference (chưa cấu hình)
        get_res = client.get(f"/api/v1/clients/{cust.id}/bm-preferences")
        assert get_res.status_code == 200
        data = get_res.json()
        assert data["is_configured"] is False
        assert data["preferred_bm_id"] == "BM_01"

        # 3. Patch update / override
        payload = {
            "preferred_bm_id": "BM_03",
            "bm_role": "ADMIN",
            "ad_account_access_type": "PARTIAL",
            "partial_permissions": ["MANAGE_CAMPAIGNS", "CREATIVE_HUB"],
            "notes": "Cập nhật qua Web UI 1-click",
            "actor": "admin_web",
        }
        patch_res = client.patch(f"/api/v1/clients/{cust.id}/bm-preferences", json=payload)
        assert patch_res.status_code == 200
        patch_data = patch_res.json()
        assert patch_data["success"] is True
        assert patch_data["preference"]["preferred_bm_id"] == "BM_03"
        assert patch_data["preference"]["bm_role"] == "ADMIN"
        assert patch_data["preference"]["ad_account_access_type"] == "PARTIAL"
        assert patch_data["preference"]["partial_permissions"] == ["MANAGE_CAMPAIGNS", "CREATIVE_HUB"]

        # 4. Verify alias /customers/{id}/bm-preferences
        alias_res = client.get(f"/api/v1/customers/{cust.id}/bm-preferences")
        assert alias_res.status_code == 200
        assert alias_res.json()["preferred_bm_id"] == "BM_03"
        assert alias_res.json()["is_configured"] is True

        # 5. List all preferences
        list_res = client.get("/api/v1/clients/preferences")
        assert list_res.status_code == 200
        prefs_list = list_res.json()
        matching = [p for p in prefs_list if p["client_id"] == cust.id]
        assert len(matching) == 1
        assert matching[0]["preferred_bm_id"] == "BM_03"
    finally:
        app.dependency_overrides.pop(get_db, None)
