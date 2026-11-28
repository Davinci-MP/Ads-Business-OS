"""Quét kiểu ToolFB qua Graph API chính thức: đúng giá trị, không bịa, giữ dữ liệu khi lỗi."""

import itertools

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.via import SyncedAdAccount, SyncedBM, SyncedPage, ViaProfile
from app.services.meta_scan import aggregate_pixels, parse_account, scan_via
from app.services.via_manager import encrypt_via_credentials, normalize_amount

_seq = itertools.count(1)


@pytest.mark.parametrize(
    ("raw", "currency", "expected"),
    [("12345", "USD", 123.45), ("990000", "VND", 990000.0), ("150000", "THB", 1500.0),
     ("5000", "JPY", 5000.0), ("250000", "IDR", 250000.0), ("1999", "PHP", 19.99)],
)
def test_normalize_amount_theo_bang_offset_meta(raw, currency, expected):
    assert normalize_amount(raw, currency) == expected


def test_parse_account_lay_dung_truong_va_de_trong_khi_thieu():
    acc = parse_account({
        "account_id": "111", "name": "TK A", "account_status": 3, "disable_reason": 3, "currency": "USD",
        "balance": "2500", "amount_spent": "100000", "spend_cap": "500000", "adtrust_dsl": "5000",
        "timezone_name": "Asia/Bangkok", "created_time": "2021-05-04T10:22:33+0000",
        "user_tasks": ["MANAGE", "ADVERTISE"], "is_prepay_account": False,
        "adspaymentcycle": {"data": [{"threshold_amount": "2000"}]},
        "funding_source_details": {"display_string": "Visa *1234"},
        "adspixels": {"data": [{"id": "px1", "name": "Pixel 1", "last_fired_time": "2026-11-27T00:00:00+0000"}]},
    })
    assert acc["status_dot"] == "DIE" and acc["status_name"] == "UNSETTLED"
    assert acc["disable_reason"] == "RISK_PAYMENT"
    assert (acc["balance"], acc["amount_spent"], acc["spend_cap"], acc["ad_trust_dsl"], acc["threshold"]) == (
        25.0, 1000.0, 5000.0, 50.0, 20.0)
    assert acc["user_role"] == "ADMIN" and acc["card_last4"] == "1234"
    assert acc["created_time"].year == 2021 and acc["account_type"] == "PERSONAL"
    assert acc["pixels"][0]["id"] == "px1"

    bare = parse_account({"id": "act_222", "name": "TK B", "account_status": 1, "currency": "VND"})
    assert bare["balance"] is None and bare["spend_cap"] is None and bare["ad_trust_dsl"] is None
    assert bare["user_role"] == "" and bare["timezone_name"] == "" and bare["pixels"] is None
    assert parse_account({"id": "act_9", "account_status": 1}, bm=("bm1", "BM One"))["account_type"] == "BM"


def _graph(personal, bm_owned, bm_client, pages):
    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p.endswith("/me/adaccounts"):
            return httpx.Response(200, json={"data": personal})
        if p.endswith("/me/businesses"):
            return httpx.Response(200, json={"data": [{"id": "777001", "name": "BM One",
                                                        "verification_status": "verified",
                                                        "created_time": "2020-01-02T00:00:00+0000"}]})
        if p.endswith("/777001/owned_ad_accounts"):
            return httpx.Response(200, json={"data": bm_owned})
        if p.endswith("/777001/client_ad_accounts"):
            return httpx.Response(200, json={"data": bm_client})
        if p.endswith("/me/accounts"):
            return httpx.Response(200, json={"data": pages})
        return httpx.Response(404, json={"error": {"message": "unexpected " + p}})
    return httpx.MockTransport(handler)


def _via(db, token="EAAQscantoken"):
    n = next(_seq)
    via = ViaProfile(uid=f"66000000{n:04d}", profile_name=f"scan {n}", profile_dir=f"profiles/scan{n}",
                     user_agent="UA", encrypted_credentials=encrypt_via_credentials({"access_token": f"{token}{n}"}),
                     token_status="ACTIVE")
    db.add(via)
    db.commit()
    return via


def test_scan_via_luu_tkqc_ca_nhan_bm_page_pixel_bang_gia_tri_that(db):
    via = _via(db)
    transport = _graph(
        personal=[{"account_id": "881", "name": "Ca nhan", "account_status": 1, "currency": "USD", "balance": "500",
                   "adspixels": {"data": [{"id": "pxA", "name": "Pixel A"}]}}],
        bm_owned=[{"account_id": "882", "name": "BM own", "account_status": 2, "disable_reason": 1,
                   "currency": "VND", "amount_spent": "990000"}],
        bm_client=[{"account_id": "883", "name": "BM client", "account_status": 1, "currency": "THB",
                    "amount_spent": "150000", "adspixels": {"data": [{"id": "pxA", "name": "Pixel A"}]}}],
        pages=[{"id": "pg1", "name": "Page 1", "category": "Shop", "fan_count": 1200}],
    )
    res = scan_via(db, via, transport=transport)
    assert res["ok"], res
    assert res["counts"] == {"accounts": 3, "personal_accounts": 1, "bm_accounts": 2, "live": 2, "die": 1,
                             "bms": 1, "pages": 1, "pixels": 1}

    rows = {r.act_id: r for r in db.scalars(select(SyncedAdAccount).where(SyncedAdAccount.via_profile_id == via.id))}
    assert rows["881"].balance == 5.0 and rows["881"].account_type == "PERSONAL"
    assert rows["882"].disable_reason == "ADS_INTEGRITY_POLICY" and rows["882"].business_name == "BM One"
    assert rows["883"].amount_spent == 1500.0
    assert rows["881"].country_code == "" and rows["881"].tax_status == "" and rows["881"].user_role == ""
    bm = db.scalar(select(SyncedBM).where(SyncedBM.via_profile_id == via.id))
    assert bm.verified_status == "verified" and bm.created_year == "2020" and bm.ad_account_count == 2
    page = db.scalar(select(SyncedPage).where(SyncedPage.via_profile_id == via.id))
    assert page.likes_count == 1200
    db.refresh(via)
    assert (via.ad_account_count, via.bm_count, via.page_count) == (3, 1, 1)

    pixels = aggregate_pixels(db, via_id=via.id)
    assert len(pixels) == 1 and {a["act_id"] for a in pixels[0]["accounts"]} == {"881", "883"}

    # Quét lại: idempotent, không nhân đôi dòng
    assert scan_via(db, via, transport=transport)["ok"]
    assert db.query(SyncedAdAccount).filter(SyncedAdAccount.via_profile_id == via.id).count() == 3


def test_scan_token_het_han_giu_du_lieu_cu_va_danh_dau_expired(db):
    via = _via(db)
    scan_via(db, via, transport=_graph(
        [{"account_id": "891", "name": "Cu", "account_status": 1, "currency": "USD", "balance": "700"}], [], [], []))

    def expired(request):
        return httpx.Response(400, json={"error": {"message": "Session has expired", "code": 190}})

    res = scan_via(db, via, transport=httpx.MockTransport(expired))
    assert not res["ok"] and "cấp quyền lại" in res["error"]
    db.refresh(via)
    assert via.token_status == "EXPIRED"
    assert db.scalar(select(SyncedAdAccount).where(SyncedAdAccount.act_id == "891")).balance == 7.0


def test_scan_loi_mang_khong_doi_du_lieu(db):
    via = _via(db)

    def boom(request):
        raise httpx.ConnectError("down")

    res = scan_via(db, via, transport=httpx.MockTransport(boom))
    assert not res["ok"] and "giữ nguyên" in res["error"]
    db.refresh(via)
    assert via.token_status == "ACTIVE"


def test_scan_via_chua_co_token(db):
    via = ViaProfile(uid="6609999999", profile_name="no token", profile_dir="profiles/nt", user_agent="UA",
                     encrypted_credentials=encrypt_via_credentials({}), token_status="NONE")
    db.add(via)
    db.commit()
    assert "Cấp quyền Facebook" in scan_via(db, via)["error"]


def test_api_scan_va_pixels(db, monkeypatch):
    via = _via(db)
    import app.services.meta_scan as meta_scan

    real = meta_scan.fetch_via_assets
    monkeypatch.setattr(meta_scan, "fetch_via_assets", lambda token, transport=None: real(token, transport=_graph(
        [{"account_id": "8951", "name": "API", "account_status": 1, "currency": "USD",
          "adspixels": {"data": [{"id": "pxZ", "name": "Pixel Z"}]}}], [], [], [])))
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        res = client.post(f"/api/v1/vias/{via.id}/scan")
        pixels = client.get("/api/v1/vias/ads-check/pixels", params={"via_id": via.id})
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 200 and res.json()["ok"]
    assert pixels.status_code == 200 and pixels.json()["items"][0]["pixel_id"] == "pxZ"


def test_scan_loi_mot_buoc_khong_ghi_de_so_dem_bang_0(db):
    via = _via(db)
    assert scan_via(db, via, transport=_graph(
        [{"account_id": "8971", "name": "A", "account_status": 1, "currency": "USD"}], [], [],
        [{"id": "pg9", "name": "P"}]))["ok"]

    def pages_down(request):
        if request.url.path.endswith("/me/accounts"):
            return httpx.Response(500, json={"error": {"message": "temporarily unavailable"}})
        return _graph([{"account_id": "8971", "name": "A", "account_status": 1, "currency": "USD"}], [], [], []).handle_request(request)

    res = scan_via(db, via, transport=httpx.MockTransport(pages_down))
    assert res["ok"] and res["warnings"]
    db.refresh(via)
    assert via.page_count == 1  # bước Page lỗi → giữ số cũ
