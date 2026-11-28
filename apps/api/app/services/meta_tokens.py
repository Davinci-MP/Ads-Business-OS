"""Nguồn token Meta cho job/dashboard khi chạy trên server.

Local: token lấy từ env ``ADSOS_META_ACCESS_TOKEN`` / ``ADSOS_META_TOKEN_MAP`` (như trước).
Server: token nằm trong VIA đã cấp quyền OAuth (``token_status == ACTIVE``), lưu mã hóa.
Không bao giờ log token.

Dữ liệu mock chỉ được dùng ở ``APP_ENV=local``: staging/production không có token thật thì
job bỏ qua, KHÔNG ghi số liệu giả lập (AGENTS.md: không ghi đè dữ liệu bằng số giả).
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import select

from app.connectors.meta import TOKEN_ENV, TOKEN_MAP_ENV, MetaAdsConnector, build_connector
from app.core.config import settings
from app.models.via import SyncedAdAccount, ViaProfile
from app.services.via_manager import clean_meta_token, is_synthetic_meta_token

NO_META_TOKEN_STATUS = "NO_META_TOKEN"


def _env_tokens_configured() -> bool:
    return bool(os.environ.get(TOKEN_ENV, "").strip() or os.environ.get(TOKEN_MAP_ENV, "").strip())


def via_token_sources(session: Any) -> tuple[dict[str, str], list[str]]:
    """(token_map ``{"act_<id>": token}``, danh sách token VIA để tự liệt kê tài khoản)."""
    token_map: dict[str, str] = {}
    discovery: list[str] = []
    vias = session.scalars(
        select(ViaProfile).where(ViaProfile.token_status == "ACTIVE").order_by(ViaProfile.id)
    ).all()
    for via in vias:
        token = clean_meta_token(via.access_token)
        if not token or is_synthetic_meta_token(token):
            continue
        if token not in discovery:
            discovery.append(token)
        act_ids = session.scalars(
            select(SyncedAdAccount.act_id).where(SyncedAdAccount.via_profile_id == via.id)
        ).all()
        for act_id in act_ids:
            raw = str(act_id or "").strip()
            if raw:
                token_map.setdefault(raw if raw.startswith("act_") else f"act_{raw}", token)
    return token_map, discovery


def build_job_connector(session: Any) -> MetaAdsConnector:
    """Connector cho job/dashboard: env token nếu có (local), không thì token VIA (server)."""
    if _env_tokens_configured():
        return build_connector()
    token_map, discovery = via_token_sources(session)
    if discovery:
        return MetaAdsConnector(token_map=token_map, discovery_tokens=discovery, use_mock=False)
    return build_connector()


def mock_blocked(connector: Any) -> bool:
    """True khi connector là mock mà môi trường không phải local → không được ghi dữ liệu."""
    return getattr(connector, "mode", "live") == "mock" and settings.app_env != "local"
