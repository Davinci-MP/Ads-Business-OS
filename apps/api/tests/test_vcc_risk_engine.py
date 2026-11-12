"""Kiểm thử toàn diện Động cơ Quản trị Rủi ro Thẻ VCC PingPong, Cross-Mapping Meta và Cảnh báo Tài chính."""

from decimal import Decimal
import pytest
from sqlalchemy.orm import Session

from app.models.customer import utcnow
from app.models.vcc import VccCard, VccTransaction
from app.models.via import SyncedAdAccount, ViaProfile
from app.services.risk_engine import RiskManagementEngine


@pytest.fixture(autouse=True)
def clean_vcc_tables(db: Session):
    """Làm sạch các bảng VCC và tài khoản trước và sau mỗi bài test."""
    db.query(VccTransaction).delete()
    db.query(VccCard).delete()
    db.query(SyncedAdAccount).delete()
    db.query(ViaProfile).delete()
    db.commit()
    yield
    db.query(VccTransaction).delete()
    db.query(VccCard).delete()
    db.query(SyncedAdAccount).delete()
    db.query(ViaProfile).delete()
    db.commit()


class MockPingPongConnector:
    """Mock connector PingPong Issuing 2.7.1 cho kiểm thử."""

    def __init__(self, master_usd: Decimal = Decimal("500.00"), cards=None, txns=None):
        self.master_usd = master_usd
        self.cards = cards or [
            {
                "id": "vcc_active_01",
                "card_number_masked": "4593 **** **** 1234",
                "last_four": "1234",
                "status": "ACTIVE",
                "remark": "Thẻ TKQC Media Buyer FB 01 - act_1001",
                "currency": "USD",
                "allocated_balance": Decimal("50.00"),
                "available_balance": Decimal("50.00"),
            },
            {
                "id": "vcc_low_02",
                "card_number_masked": "4593 **** **** 5678",
                "last_four": "5678",
                "status": "ACTIVE",
                "remark": "Thẻ TikTok & FB Dự Phòng",
                "currency": "USD",
                "allocated_balance": Decimal("10.00"),
                "available_balance": Decimal("2.50"),  # Thấp hơn threshold 5.0
            },
            {
                "id": "vcc_frozen_03",
                "card_number_masked": "4593 **** **** 9999",
                "last_four": "9999",
                "status": "FROZEN",
                "remark": "Thẻ Đã Khóa",
                "currency": "USD",
                "allocated_balance": Decimal("0.00"),
                "available_balance": Decimal("0.00"),
            },
        ]
        self.txns = txns or [
            {
                "id": "txn_001",
                "card_id": "vcc_active_01",
                "auth_amount": Decimal("25.00"),
                "settle_amount": Decimal("25.00"),
                "currency": "USD",
                "merchant_name": "FACEBOOK ADS",
                "status": "SETTLED",
                "transaction_time": "2026-11-03T10:00:00Z",
            }
        ]

    def get_usd_budget_balance(self) -> Decimal:
        return self.master_usd

    def get_active_cards(self) -> list[dict]:
        return [c for c in self.cards if c.get("status") == "ACTIVE"]

    def get_card_transactions(self, card_id: str, limit: int = 50) -> list[dict]:
        return [t for t in self.txns if t.get("card_id") == str(card_id)]


def test_vcc_sync_cards(db: Session):
    """Kiểm tra đồng bộ danh sách thẻ VCC từ PingPong vào DB."""
    mock_conn = MockPingPongConnector()
    synced = RiskManagementEngine.sync_vcc_cards(db, connector=mock_conn)

    assert len(synced) == 2  # Chỉ có 2 thẻ ACTIVE
    card1 = db.get(VccCard, "vcc_active_01")
    assert card1 is not None
    assert card1.last_four == "1234"
    assert card1.available_balance == Decimal("50.00")
    assert card1.low_balance_threshold == Decimal("5.0")

    card2 = db.get(VccCard, "vcc_low_02")
    assert card2 is not None
    assert card2.available_balance == Decimal("2.50")


def test_rule_1_low_vcc_balance_alert(db: Session):
    """Kiểm tra Quy tắc 1: Cảnh báo khi số dư thẻ VCC < low_balance_threshold."""
    card = VccCard(
        id="card_low",
        card_number_masked="4593 **** **** 4321",
        last_four="4321",
        status="ACTIVE",
        remark="Thẻ Test Low Balance",
        currency="USD",
        allocated_balance=Decimal("10.0"),
        available_balance=Decimal("3.50"),  # < 5.0
        low_balance_threshold=Decimal("5.0"),
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(card)
    db.commit()

    alerts = RiskManagementEngine.evaluate_alerts(db, master_usd_balance=Decimal("1000.0"))
    rule1_alerts = [a for a in alerts if a["rule"] == "RULE_1_LOW_VCC_BALANCE"]

    assert len(rule1_alerts) == 1
    assert rule1_alerts[0]["severity"] == "WARNING"
    assert rule1_alerts[0]["last_four"] == "4321"
    assert "Cảnh báo Thẻ: Thẻ *4321 (Thẻ Test Low Balance) chỉ còn 3.5 USD." in rule1_alerts[0]["message"]


def test_rule_2_meta_debt_exceeds_vcc_balance_critical_alert(db: Session):
    """Kiểm tra Quy tắc 2: Nợ Meta > Số dư thẻ VCC (NGUY CƠ TỤT NGƯỠNG)."""
    # 1. Tạo VIA Profile & TKQC
    via = ViaProfile(
        uid="via_uid_01",
        profile_name="VIA Chạy Thẻ",
        profile_dir="profile_01",
        user_agent="Mozilla/5.0",
        encrypted_credentials="enc",
    )
    db.add(via)
    db.flush()

    ad_acc = SyncedAdAccount(
        via_profile_id=via.id,
        act_id="act_1001",
        name="TKQC Thời Trang Nam",
        balance=75.0,  # Nợ Meta 75 USD
        threshold=100.0,
        currency="USD",
        payment_card_last4="1234",
        funding_source_last_four="1234",
    )
    db.add(ad_acc)

    # 2. Tạo thẻ VCC có cùng 4 số cuối nhưng chỉ còn 50 USD
    card = VccCard(
        id="vcc_01",
        card_number_masked="4593 **** **** 1234",
        last_four="1234",
        status="ACTIVE",
        remark="TK act_1001",
        currency="USD",
        allocated_balance=Decimal("100.0"),
        available_balance=Decimal("50.0"),  # Thấp hơn nợ 75.0
        low_balance_threshold=Decimal("5.0"),
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(card)
    db.commit()

    alerts = RiskManagementEngine.evaluate_alerts(db, master_usd_balance=Decimal("1000.0"))
    rule2_alerts = [a for a in alerts if a["rule"] == "RULE_2_META_DEBT_EXCEEDS_VCC_BALANCE"]

    assert len(rule2_alerts) == 1
    assert rule2_alerts[0]["severity"] == "CRITICAL"
    assert rule2_alerts[0]["act_id"] == "act_1001"
    assert rule2_alerts[0]["debt"] == 75.0
    assert rule2_alerts[0]["available_balance"] == 50.0
    assert "🚨 NGUY HIỂM: TKQC act_1001 đang nợ 75 USD nhưng thẻ *1234 chỉ còn 50 USD!" in rule2_alerts[0]["message"]


def test_rule_3_master_budget_deficit_alert(db: Session):
    """Kiểm tra Quy tắc 3: Tổng nợ Meta > Số dư Quỹ Master USD PingPong."""
    via = ViaProfile(
        uid="via_uid_02",
        profile_name="VIA Test Master",
        profile_dir="profile_02",
        user_agent="Mozilla/5.0",
        encrypted_credentials="enc",
    )
    db.add(via)
    db.flush()

    # Tạo 2 TKQC với tổng nợ = 450 USD
    db.add(SyncedAdAccount(
        via_profile_id=via.id, act_id="act_a", name="TK A", balance=250.0, currency="USD"
    ))
    db.add(SyncedAdAccount(
        via_profile_id=via.id, act_id="act_b", name="TK B", balance=200.0, currency="USD"
    ))
    db.commit()

    # Master USD Balance chỉ có 300 USD (< 450 USD)
    alerts = RiskManagementEngine.evaluate_alerts(db, master_usd_balance=Decimal("300.00"))
    rule3_alerts = [a for a in alerts if a["rule"] == "RULE_3_MASTER_BUDGET_DEFICIT"]

    assert len(rule3_alerts) == 1
    assert rule3_alerts[0]["severity"] == "CRITICAL"
    assert rule3_alerts[0]["total_meta_debt"] == 450.0
    assert rule3_alerts[0]["master_usd_balance"] == 300.0
    assert "Tổng nợ Meta (450 USD) vượt quá số dư Master Budget PingPong (300 USD)!" in rule3_alerts[0]["message"]


def test_auto_mapping_multi_match_resolved_by_remark(db: Session):
    """Kiểm tra khớp chéo khi nhiều TKQC cùng 4 số cuối thẻ, phân giải chính xác qua remark."""
    via = ViaProfile(
        uid="via_uid_multi",
        profile_name="VIA Multi Match",
        profile_dir="profile_03",
        user_agent="Mozilla/5.0",
        encrypted_credentials="enc",
    )
    db.add(via)
    db.flush()

    # 2 TKQC cùng dùng thẻ đuôi 8888
    acc1 = SyncedAdAccount(
        via_profile_id=via.id, act_id="act_99901", name="Khách Hàng Áo Thun",
        balance=10.0, payment_card_last4="8888"
    )
    acc2 = SyncedAdAccount(
        via_profile_id=via.id, act_id="act_99902", name="Khách Hàng Mỹ Phẩm",
        balance=40.0, payment_card_last4="8888"
    )
    db.add_all([acc1, acc2])

    # Thẻ VCC ghi chú rõ là act_99902
    card = VccCard(
        id="card_multi_8888",
        last_four="8888",
        status="ACTIVE",
        remark="Thẻ cấp cho act_99902 Mỹ phẩm",
        available_balance=Decimal("100.0"),
    )
    db.add(card)
    db.commit()

    mappings = RiskManagementEngine.auto_map_cards_to_ad_accounts(db)
    assert len(mappings) == 1
    assert mappings[0]["ad_account"].act_id == "act_99902"


def test_update_card_threshold(db: Session):
    """Kiểm tra cập nhật ngưỡng cảnh báo thẻ VCC."""
    card = VccCard(
        id="card_thresh",
        last_four="7777",
        status="ACTIVE",
        available_balance=Decimal("20.0"),
        low_balance_threshold=Decimal("5.0"),
    )
    db.add(card)
    db.commit()

    updated = RiskManagementEngine.update_card_threshold(db, "card_thresh", Decimal("15.5"))
    assert updated.low_balance_threshold == Decimal("15.5")

    with pytest.raises(ValueError, match="số âm"):
        RiskManagementEngine.update_card_threshold(db, "card_thresh", Decimal("-1.0"))


def test_get_card_transactions_history(db: Session):
    """Kiểm tra lấy lịch sử giao dịch/uỷ quyền thẻ VCC."""
    card = VccCard(id="card_txns", last_four="1111", status="ACTIVE")
    db.add(card)
    db.commit()

    mock_conn = MockPingPongConnector(txns=[
        {
            "id": "t1",
            "card_id": "card_txns",
            "auth_amount": Decimal("10.00"),
            "settle_amount": Decimal("10.00"),
            "currency": "USD",
            "merchant_name": "FACEBOOK ADS",
            "status": "SETTLED",
            "transaction_time": "2026-11-03T11:00:00Z",
        },
        {
            "id": "t2",
            "card_id": "card_txns",
            "auth_amount": Decimal("15.50"),
            "settle_amount": Decimal("15.50"),
            "currency": "USD",
            "merchant_name": "FACEBOOK ADS",
            "status": "SETTLED",
            "transaction_time": "2026-11-03T12:00:00Z",
        },
    ])

    txns = RiskManagementEngine.get_card_transactions_history(
        db, "card_txns", connector=mock_conn
    )
    assert len(txns) == 2
    assert txns[0].id == "t2"  # Sắp xếp mới nhất lên đầu
    assert txns[0].settle_amount == Decimal("15.50")


def test_vcc_risk_api_endpoints(db: Session):
    """Kiểm tra các endpoints HTTP REST API /api/v1/vcc-risk."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import get_db

    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    try:
        # 1. Overview endpoint
        res = client.get("/api/v1/vcc-risk/overview")
        assert res.status_code == 200
        data = res.json()
        assert "master_usd_balance" in data
        assert "total_meta_debt" in data
        assert "cards" in data
        assert "alerts" in data

        # 2. Add card and update threshold endpoint
        card = VccCard(id="api_card_01", last_four="9999", status="ACTIVE", low_balance_threshold=Decimal("5.0"))
        db.add(card)
        db.commit()

        put_res = client.put("/api/v1/vcc-risk/cards/api_card_01/threshold", json={"threshold": 20.0})
        assert put_res.status_code == 200
        assert put_res.json()["ok"] is True
        assert put_res.json()["low_balance_threshold"] == 20.0

        # 3. Get transactions endpoint
        txn = VccTransaction(id="api_txn_01", card_id="api_card_01", auth_amount=Decimal("12.0"), settle_amount=Decimal("12.0"))
        db.add(txn)
        db.commit()

        txns_res = client.get("/api/v1/vcc-risk/cards/api_card_01/transactions")
        assert txns_res.status_code == 200
        txns_data = txns_res.json()
        assert len(txns_data) >= 1
        assert txns_data[0]["id"] == "api_txn_01"
    finally:
        app.dependency_overrides.clear()
