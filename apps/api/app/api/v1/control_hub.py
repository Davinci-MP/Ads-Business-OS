"""API Control Hub — Điều khiển đa trình duyệt & Session Cloud Hub (D-065).

Chức năng:
1. Nhận heartbeat từ các node trình duyệt (Chrome, AdsPower, GoLogin, KiKLogin).
2. Đồng bộ an toàn session cookie, EAAG, EAAB, fb_dtsg (mã hóa Fernet ở DB).
3. Trả về các lệnh điều phối PENDING cho node mục tiêu.
4. Điều phối lệnh (dispatch) từ bất kỳ trình duyệt hoặc thiết bị di động nào tới target node.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.local_admin import require_local_admin_or_owner
from app.db import get_db
from app.models.customer import utcnow
from app.models.extension_remote import BrowserNode, RemoteViaCommand
from app.models.via import ViaProfile

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/control-hub",
    tags=["control-hub"],
    dependencies=[Depends(require_local_admin_or_owner)],
)


# ==============================================================================
# PYDANTIC SCHEMAS
# ==============================================================================

class NodeHeartbeatRequest(BaseModel):
    model_config = {"extra": "allow"}

    node_uid: str = Field(..., description="UID duy nhất của browser profile node")
    node_name: Optional[str] = Field("Chrome Profile Node", description="Tên định danh node")
    browser_type: Optional[str] = Field("CHROME", description="CHROME | ADSPOWER | GOLOGIN | KIKLOGIN | OTHER")
    via_id: Optional[int] = Field(None, description="ID của VIA Profile liên kết nếu có")
    fb_uid: Optional[str] = Field(None, description="UID Facebook đang đăng nhập")
    eaag_token: Optional[str] = Field(None, description="Token EAAG Business trích xuất từ session")
    eaab_token: Optional[str] = Field(None, description="Token EAAB Ads Manager trích xuất từ session")
    cookie: Optional[str] = Field(None, description="Cookie session Facebook (c_user, xs, datr...)")
    fb_dtsg: Optional[str] = Field(None, description="Token fb_dtsg chống CSRF phục vụ GraphQL mutation")
    status: Optional[str] = Field("ONLINE", description="ONLINE | OFFLINE | BUSY")


class DispatchCommandRequest(BaseModel):
    model_config = {"extra": "allow"}

    node_uid: Optional[str] = Field(None, description="Target Browser Node UID")
    via_id: Optional[int] = Field(None, description="Target VIA Profile ID")
    via_uid: Optional[str] = Field(None, description="Target Facebook UID")
    act_id: Optional[str] = Field("act_0", description="ID tài khoản quảng cáo mục tiêu")
    command: Optional[str] = Field(None, description="Alias cho command_type")
    command_type: Optional[str] = Field(None, description="Loại tác vụ: WORKFLOW_EXECUTE, SET_CAMP, PAUSE_CAMP, RESUME_CAMP, BULK_RENAME, SHARE_PIXEL, PAY_NOW...")
    payload: Optional[dict[str, Any]] = Field(default_factory=dict, description="Payload tham số của lệnh")
    requested_by: Optional[str] = Field("CONTROL_HUB", description="Người hoặc hệ thống phát lệnh")


# ==============================================================================
# ENDPOINTS
# ==============================================================================

@router.post("/nodes/heartbeat")
def node_heartbeat(
    req: NodeHeartbeatRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Nhận heartbeat định kỳ (5s) từ Browser Node, cập nhật session tokens (mã hóa Fernet) và trả về lệnh PENDING."""
    node = db.scalar(select(BrowserNode).where(BrowserNode.node_uid == req.node_uid))
    now = utcnow()

    if not node:
        node = BrowserNode(
            node_uid=req.node_uid,
            node_name=req.node_name or f"Node-{req.node_uid[:8]}",
            browser_type=(req.browser_type or "CHROME").upper(),
            status=(req.status or "ONLINE").upper(),
            last_heartbeat_at=now,
        )
        db.add(node)
        db.flush()

    node.last_heartbeat_at = now
    if req.status:
        node.status = req.status.upper()
    if req.node_name:
        node.node_name = req.node_name
    if req.browser_type:
        node.browser_type = req.browser_type.upper()
    if req.via_id is not None:
        node.via_id = req.via_id
    if req.fb_uid:
        node.fb_uid = req.fb_uid

    # Cập nhật các token/cookie với Fernet mã hóa
    if req.eaag_token:
        node.eaag_token = req.eaag_token
    if req.eaab_token:
        node.eaab_token = req.eaab_token
    if req.cookie:
        node.cookie = req.cookie
    if req.fb_dtsg:
        node.fb_dtsg = req.fb_dtsg

    # Tự động liên kết VIA Profile nếu chưa có via_id
    if not node.via_id and node.fb_uid:
        linked_via = db.scalar(select(ViaProfile).where(ViaProfile.uid == node.fb_uid))
        if linked_via:
            node.via_id = linked_via.id
            # Đồng bộ ngược token vào ViaProfile nếu VIA chưa có
            if req.eaag_token and not linked_via.access_token:
                linked_via.access_token = req.eaag_token
            if req.cookie and not linked_via.cookies:
                linked_via.cookies = req.cookie

    db.commit()

    # Tìm các lệnh PENDING dành cho node hoặc FB UID này
    conditions = [RemoteViaCommand.status == "PENDING"]
    if node.fb_uid:
        conditions.append(or_(
            RemoteViaCommand.via_uid == node.fb_uid,
            RemoteViaCommand.via_uid == "*",
            RemoteViaCommand.via_uid == "",
        ))

    pending_cmds = db.scalars(
        select(RemoteViaCommand)
        .where(*conditions)
        .order_by(RemoteViaCommand.id.asc())
        .limit(10)
    ).all()

    cmds_data = []
    for cmd in pending_cmds:
        payload_dict = cmd.payload or {}
        if not payload_dict and cmd.payload_json:
            try:
                payload_dict = json.loads(cmd.payload_json)
            except Exception:
                payload_dict = {}
        cmds_data.append({
            "id": cmd.public_id or str(cmd.id),
            "numeric_id": cmd.id,
            "command_type": cmd.command_type,
            "task_type": cmd.command_type,
            "act_id": cmd.act_id,
            "ad_account_id": cmd.ad_account_id or cmd.act_id,
            "payload": payload_dict,
            "created_at": cmd.created_at.isoformat() if cmd.created_at else None,
        })

    return {
        "success": True,
        "status": "ok",
        "node_id": node.id,
        "node_uid": node.node_uid,
        "server_time": now.isoformat(),
        "pending_commands": cmds_data,
        "pending_tasks": cmds_data,
        "message": f"Heartbeat thành công cho node {node.node_uid}",
    }


@router.get("/nodes")
def list_browser_nodes(
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Danh sách toàn bộ Antidetect & Browser Nodes đang kết nối Session Cloud Hub."""
    nodes = db.scalars(select(BrowserNode).order_by(BrowserNode.last_heartbeat_at.desc())).all()
    now = utcnow()

    items = []
    for n in nodes:
        # Node được xem là ONLINE nếu heartbeat trong vòng 30 giây gần nhất
        is_active = False
        if n.last_heartbeat_at:
            delta_sec = (now - n.last_heartbeat_at.replace(tzinfo=now.tzinfo) if n.last_heartbeat_at.tzinfo else now - n.last_heartbeat_at).total_seconds()
            is_active = delta_sec < 35

        items.append({
            "id": n.id,
            "node_uid": n.node_uid,
            "node_name": n.node_name,
            "browser_type": n.browser_type,
            "via_id": n.via_id,
            "fb_uid": n.fb_uid,
            "status": "ONLINE" if is_active else "OFFLINE",
            "last_heartbeat_at": n.last_heartbeat_at.isoformat() if n.last_heartbeat_at else None,
            "has_cookie": bool(n.cookie_enc),
            "has_eaag": bool(n.eaag_token_enc),
            "has_eaab": bool(n.eaab_token_enc),
            "has_fb_dtsg": bool(n.fb_dtsg_enc),
            "created_at": n.created_at.isoformat() if n.created_at else None,
        })

    return {
        "nodes": items,
        "total": len(items),
        "online_count": sum(1 for item in items if item["status"] == "ONLINE"),
    }


@router.post("/dispatch")
def dispatch_remote_command(
    req: DispatchCommandRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Phát lệnh điều khiển (Cross-Browser / Mobile-to-Browser) tới hàng đợi thực thi của node mục tiêu."""
    via_uid = (req.via_uid or "").strip()
    act_id = (req.act_id or "act_0").strip()
    if not via_uid and req.node_uid:
        node = db.scalar(select(BrowserNode).where(BrowserNode.node_uid == req.node_uid))
        if node and node.fb_uid:
            via_uid = node.fb_uid
    if not via_uid:
        via_uid = "*"

    cmd_type = (req.command_type or req.command or "WORKFLOW_EXECUTE").strip()

    cmd = RemoteViaCommand(
        via_uid=via_uid,
        act_id=act_id,
        ad_account_id=act_id,
        command_type=cmd_type,
        payload=req.payload or {},
        payload_json=json.dumps(req.payload or {}, ensure_ascii=False),
        status="PENDING",
        requested_by_telegram=req.requested_by or "CONTROL_HUB_WEB",
    )
    db.add(cmd)
    db.commit()
    db.refresh(cmd)

    return {
        "success": True,
        "task_id": cmd.id,
        "command_id": cmd.public_id or str(cmd.id),
        "numeric_id": cmd.id,
        "status": "PENDING",
        "target_via_uid": via_uid,
        "target_act_id": act_id,
        "command_type": cmd_type,
        "message": f"Đã phát lệnh {cmd_type} tới hàng đợi thực thi thành công.",
    }
