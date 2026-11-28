"""MaxCare Sync Engine — đồng bộ báo cáo tài khoản quảng cáo của dàn VIA song song.

Nguyên tắc:
- Chỉ GET Graph API `me/adaccounts`, dùng Token (Fernet credentials) và Proxy riêng của từng VIA.
- KHÔNG dùng mock trong chế độ thật; lỗi fetch -> giữ nguyên dữ liệu cũ, KHÔNG ghi đè bằng 0.
- Snapshot append-only `ad_account_snapshots` với unique (act_id, snapshot_at) chống ghi trùng.
"""

from __future__ import annotations

import asyncio
import logging
import os
from decimal import Decimal
from typing import Any, Optional

import httpx

from app.core.meta_proof import add_proof_to_graph_request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models.customer import utcnow
from app.models.via import AdAccountSnapshot, SyncedAdAccount, ViaProfile
from app.services.via_manager import (
    clean_meta_token,
    decrypt_via_credentials,
    is_mock_sync_allowed,
    is_synthetic_meta_token,
    normalize_proxy_config,
)

logger = logging.getLogger(__name__)

_META_FIELDS = (
    "id,name,account_status,balance,currency,amount_spent,"
    "adtrust_dsl,spend_cap,daily_spend_cap_limit,disable_reason"
)

_STATUS_DOT_MAP = {
    1: "LIVE",
    2: "DIE",   # DISABLED
    3: "DIE",   # UNSETTLED
    7: "WARNING",
    8: "WARNING",
    9: "WARNING",
}


def _resolve_concurrency(concurrency: Optional[int] = None) -> int:
    if concurrency is not None and int(concurrency) > 0:
        return max(1, min(int(concurrency), 20))
    env_value = os.getenv("ADSOS_MAXCARE_CONCURRENCY", "").strip()
    if env_value.isdigit():
        return max(1, min(int(env_value), 20))
    return 5


def normalize_amount(raw_value: Any, currency: str) -> float:
    """Chuẩn hóa tiền: minor unit (cents) -> đơn vị chính cho USD/EUR/GBP...; VND giữ nguyên."""
    try:
        value = Decimal(str(raw_value))
    except Exception:
        return 0.0
    if value == 0:
        return 0.0
    if (currency or "").strip().upper() not in ("USD", "EUR", "GBP", "AUD", "CAD", "SGD"):
        return float(value)
    return float(value / Decimal("100"))


def status_dot_from_account_status(account_status: Any) -> str:
    try:
        return _STATUS_DOT_MAP.get(int(account_status), "WARNING")
    except Exception:
        return "WARNING"


def parse_ad_account_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Chuẩn hóa 1 dòng Graph API `me/adaccounts` về schema synced_ad_accounts / ad_account_snapshots."""
    act_id = str(raw.get("id") or "").replace("act_", "").strip()
    if not act_id:
        raise ValueError("Dữ liệu Graph thiếu id tài khoản quảng cáo.")
    currency = (raw.get("currency") or "VND").strip().upper()
    account_status = int(raw.get("account_status") or 0)
    disable_reason = (raw.get("disable_reason") or "NONE").strip().upper()
    raw_daily = (
        raw.get("daily_spend_cap_limit")
        if raw.get("daily_spend_cap_limit") is not None
        else raw.get("spend_cap")
    )
    valid_disable = {"NONE", "POLICY", "RISK_PAYMENT", "UNSETTLED", "VERIFY_IDENTITY"}
    return {
        "act_id": act_id,
        "name": (raw.get("name") or "").strip() or act_id,
        "account_status": account_status,
        "status_dot": status_dot_from_account_status(account_status),
        "balance": normalize_amount(raw.get("balance"), currency),
        "total_spend": normalize_amount(raw.get("amount_spent"), currency),
        "ad_trust_dsl": normalize_amount(raw.get("adtrust_dsl"), currency),
        "daily_budget": normalize_amount(raw_daily, currency),
        "currency": currency,
        "disable_reason": disable_reason if disable_reason in valid_disable else "NONE",
    }


def fetch_via_ad_account_reports(
    via: ViaProfile,
    transport: Optional[httpx.BaseTransport] = None,
) -> list[dict[str, Any]]:
    """GET Graph API thật (chỉ đọc): toàn bộ TKQC của VIA, đi qua Proxy riêng của VIA."""
    creds = decrypt_via_credentials(via.encrypted_credentials)
    raw_tok = creds.get("access_token") or ""
    token = clean_meta_token(raw_tok) or raw_tok.strip()

    if is_synthetic_meta_token(token):
        logger.info("VIA %s sử dụng token synthetic / kiểm thử, không gọi Graph API thật.", via.uid)
        return []

    if not (token.startswith("EAAB") or token.startswith("EAAG") or token.startswith("EAA")):
        raise ValueError(
            f"VIA {via.uid} chưa có Access Token Meta thật — không thể đồng bộ báo cáo tài khoản."
        )

    proxy_url = None
    if via.proxy_config:
        normalized = normalize_proxy_config(via.proxy_config)
        if normalized and normalized.get("url"):
            proxy_url = normalized["url"]

    api_version = (
        getattr(settings, "meta_api_version", None) or os.getenv("ADSOS_META_API_VERSION", "v26.0")
    ).strip()

    base_kwargs: dict[str, Any] = {
        "timeout": 20.0,
        "headers": {
            "User-Agent": via.user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json",
        },
    }
    if transport is not None:
        base_kwargs["transport"] = transport
    elif proxy_url:
        base_kwargs["proxy"] = proxy_url

    field_candidates = [
        _META_FIELDS,
        "id,name,account_status,balance,currency,amount_spent,spend_cap,disable_reason",
        "id,name,account_status,balance,currency,amount_spent",
    ]

    rows: list[dict[str, Any]] = []
    paging_next: Optional[str] = None
    base_kwargs["event_hooks"] = {"request": [add_proof_to_graph_request]}
    with httpx.Client(**base_kwargs) as client:
        # Header isolation: không gửi Cookie hoặc Origin đến graph.facebook.com
        for hdr in ("Cookie", "cookie", "Origin", "origin", "Referer", "referer"):
            client.headers.pop(hdr, None)

        while True:
            if paging_next:
                resp = client.get(paging_next)
            else:
                resp = None
                for idx, fields in enumerate(field_candidates):
                    resp = client.get(
                        f"https://graph.facebook.com/{api_version}/me/adaccounts",
                        params={"fields": fields, "limit": 100, "access_token": token},
                    )
                    if resp.status_code == 200:
                        break
                    if resp.status_code == 400:
                        err_payload = {}
                        try:
                            err_payload = resp.json().get("error", {})
                        except Exception:
                            pass
                        err_code = err_payload.get("code")
                        if err_code in (190, 102):
                            break
                        if idx < len(field_candidates) - 1:
                            logger.info(
                                "Graph API 400 trên fields '%s'. Thử tiếp trường fallback...",
                                fields[:30],
                            )
                            continue
                    break

            if resp is None:
                break
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, dict) and payload.get("error"):
                err = payload["error"]
                code = err.get("code")
                message = (err.get("message") or "").strip()
                if code in (190, 102):
                    raise ValueError(f"Token Meta của VIA {via.uid} đã hết hạn (code 190).")
                raise ValueError(f"Meta Graph trả lỗi code {code}: {message or 'không xác định'}")
            data = payload.get("data", []) if isinstance(payload, dict) else []
            rows.extend(item for item in data if isinstance(item, dict))
            paging_next = (
                (payload.get("paging") or {}).get("next") if isinstance(payload, dict) else None
            )
            if not paging_next:
                break
    return rows


def sync_ad_account_reports(
    session,
    via_id: int,
    live_accounts: list[dict[str, Any]],
    now: Optional[Any] = None,
) -> dict[str, Any]:
    """Áp kết quả Graph API thật vào DB: cập nhật synced_ad_accounts + append snapshot append-only."""
    via = session.get(ViaProfile, via_id)
    if not via:
        raise ValueError(f"Không tìm thấy VIA #{via_id}")
    if not live_accounts and not is_mock_sync_allowed():
        raise ValueError("Kết quả thật rỗng — giữ nguyên dữ liệu cũ, không ghi đè bằng 0.")

    stamp = now or utcnow()
    updated = 0
    snapshot_created = 0
    for row in live_accounts:
        item = parse_ad_account_payload(row)
        acc = session.scalar(select(SyncedAdAccount).where(SyncedAdAccount.act_id == item["act_id"]))
        if acc is None:
            acc = SyncedAdAccount(
                via_profile_id=via.id,
                act_id=item["act_id"],
                name=item["name"],
                account_type="BM" if via.bm_count else "PERSONAL",
            )
            session.add(acc)
            session.flush()
        else:
            acc.via_profile_id = via.id
            acc.name = item["name"]

        acc.status_dot = item["status_dot"]
        acc.account_status = item["account_status"]
        acc.balance = item["balance"]
        acc.total_spend = item["total_spend"]
        acc.ad_trust_dsl = item["ad_trust_dsl"]
        acc.daily_budget = item["daily_budget"]
        acc.currency = item["currency"]
        acc.disable_reason = item["disable_reason"]
        acc.last_report_synced_at = stamp

        # Append-only, idemp theo (act_id, snapshot_at): trùng tại cùng mốc -> bỏ qua
        exists = session.scalar(
            select(AdAccountSnapshot).where(
                AdAccountSnapshot.act_id == item["act_id"],
                AdAccountSnapshot.snapshot_at == stamp,
            )
        )
        if exists is None:
            session.add(
                AdAccountSnapshot(
                    ad_account_id=acc.id,
                    act_id=item["act_id"],
                    status_dot=item["status_dot"],
                    account_status=item["account_status"],
                    balance=item["balance"],
                    threshold=acc.threshold or 0.0,
                    ad_trust_dsl=item["ad_trust_dsl"],
                    daily_budget=item["daily_budget"],
                    total_spend=item["total_spend"],
                    currency=item["currency"],
                    snapshot_at=stamp,
                    source="MAXCARE_REPORT_SYNC",
                )
            )
            snapshot_created += 1
            updated += 1

    via.last_synced_at = stamp
    session.commit()
    return {
        "via_id": via.id,
        "uid": via.uid,
        "accounts_updated": updated,
        "snapshots_created": snapshot_created,
        "synced_at": stamp.isoformat(),
    }


def run_reporting_sync(
    session,
    via_ids: Optional[list[int]] = None,
    concurrency: Optional[int] = None,
    transport: Optional[httpx.BaseTransport] = None,
    mock_data: Optional[dict[int, list[dict[str, Any]]]] = None,
    delay_between: float = 0.0,
) -> dict[str, Any]:
    """Đồng bộ song song (asyncio Semaphore 5-10 luồng) báo cáo TKQC cho dàn VIA.

    mock_data: {via_id: [payload Graph...]} chỉ dùng khi mock được phép (PYTEST / env cho phép).
    Session DB dùng chung nhưng serialized bên trong to_thread — SQLite an toàn.
    """
    query = select(ViaProfile).order_by(ViaProfile.id)
    if via_ids:
        query = query.where(ViaProfile.id.in_(via_ids))
    ids = [v.id for v in session.scalars(query).all()]
    limit = _resolve_concurrency(concurrency)
    if not ids:
        return {"total": 0, "done": [], "failed": [], "concurrency": limit}

    allow_mock = is_mock_sync_allowed()
    data_by_via = dict(mock_data or {})
    session_lock = asyncio.Lock()

    async def _one(via_id: int) -> dict[str, Any]:
        await asyncio.sleep(delay_between)
        try:
            # Session SQLAlchemy dùng chung giữa các task: mọi thao tác DB
            # phải giữ session_lock; chỉ fetch mạng chạy ngoài khoá.
            mock_payload: Any = None
            keep_mock = False
            via = None
            async with session_lock:
                via = session.get(ViaProfile, via_id)
                if not via:
                    raise ValueError(f"Không tìm thấy VIA #{via_id}")
                keep_mock = via_id in data_by_via and allow_mock
                if keep_mock:
                    mock_payload = data_by_via[via_id]
            if keep_mock:
                live = mock_payload
            else:
                live = await asyncio.to_thread(fetch_via_ad_account_reports, via, transport)
            async with session_lock:
                result = await asyncio.to_thread(sync_ad_account_reports, session, via_id, live)
            return {**result, "ok": True}
        except Exception as exc:
            logger.info("Sync báo cáo VIA #%s thất bại: %s", via_id, exc)
            return {
                "via_id": via_id,
                "ok": False,
                "error": str(exc),
                "message": f"Đồng bộ báo cáo VIA #{via_id} thất bại: {exc}",
            }

    semaphore = asyncio.Semaphore(limit)

    async def _bounded(via_id: int) -> dict[str, Any]:
        async with semaphore:
            return await _one(via_id)

    async def _gather_all() -> list[dict[str, Any]]:
        return await asyncio.gather(*[_bounded(vid) for vid in ids])

    results = list(asyncio.run(_gather_all()))

    done = [r for r in results if r.get("ok")]
    failed = [r for r in results if not r.get("ok")]
    return {
        "total": len(ids),
        "done": done,
        "failed": failed,
        "concurrency": limit,
        "timestamp": utcnow().isoformat(),
    }


def load_recent_snapshots(session, limit: int = 50) -> list[dict[str, Any]]:
    """Snapshot báo cáo mới nhất của TKQC cho MaxCare Dashboard."""
    limit = max(1, min(int(limit), 200))
    rows = session.scalars(
        select(AdAccountSnapshot).order_by(AdAccountSnapshot.id.desc()).limit(limit)
    ).all()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "id": row.id,
                "act_id": row.act_id,
                "status_dot": row.status_dot,
                "account_status": row.account_status,
                "balance": row.balance,
                "threshold": row.threshold,
                "ad_trust_dsl": row.ad_trust_dsl,
                "daily_budget": row.daily_budget,
                "total_spend": row.total_spend,
                "currency": row.currency,
                "snapshot_at": row.snapshot_at.isoformat() if row.snapshot_at else None,
                "source": row.source,
            }
        )
    return out


def export_maxcare_report_csv(session, limit: int = 100) -> dict[str, Any]:
    """Xuất CSV bảng báo cáo tài khoản quảng cáo (UTF-8, tải trực tiếp về máy)."""
    rows = load_recent_snapshots(session, limit=limit)
    header = [
        "act_id",
        "status_dot",
        "account_status",
        "currency",
        "balance",
        "threshold",
        "ad_trust_dsl",
        "daily_budget",
        "total_spend",
        "snapshot_at",
    ]
    lines = [",".join(header)]
    for row in rows:
        values = [
            str(row["act_id"]),
            str(row["status_dot"] or ""),
            "" if row["account_status"] is None else str(row["account_status"]),
            str(row["currency"]),
            str(Decimal(str(row["balance"]))),
            str(Decimal(str(row["threshold"]))),
            str(Decimal(str(row["ad_trust_dsl"]))),
            str(Decimal(str(row["daily_budget"]))),
            str(Decimal(str(row["total_spend"]))),
            str(row["snapshot_at"] or ""),
        ]
        safe = []
        for text in values:
            if "," in text or '"' in text:
                text = '"' + text.replace('"', '""') + '"'
            safe.append(text)
        lines.append(",".join(safe))
    return {"format": "csv", "filename": "maxcare_report.csv", "content": "\n".join(lines)}
