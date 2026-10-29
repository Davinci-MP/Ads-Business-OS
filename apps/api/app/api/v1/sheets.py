"""REST endpoints cho Google Sheets module (S6/S6+, D-024/D-028).

Guard cứng:
- KHÔNG endpoint nào ghi/sửa Google Sheets — chỉ đọc + phân tích + mapping trong DB.
- KHÔNG trả token/secret trong response — chỉ trả `mode` và cờ cấu hình.
- Mapping chỉ là cấu hình nội bộ; CONFIRMED = chủ dự án xác nhận (Q-007).
- Nhập Spreadsheet URL/ID từ màn hình quản trị: chỉ khi env có access token
  (quyền chỉ đọc) mới đọc được bảng thật; thiếu token → 400 với hướng dẫn,
  KHÔNG fallback mock với spreadsheet lạ (sẽ đọc sai cấu trúc).
"""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.sheets import (
    ACCESS_TOKEN_ENV,
    SheetsAuthError,
    SERVICE_ACCOUNT_FILE_ENV,
    GoogleSheetsConnector,
    SheetsAPIError,
    build_connector,
    parse_spreadsheet_url,
    service_account_configured,
)
from app.db import get_db
from app.models.sheets import SheetMapping
from app.services import sheets_compare
from app.services import sheets_report
from app.services import sheets_structure

router = APIRouter(prefix="/sheets", tags=["sheets"])


def _connector_for(spreadsheet: Optional[str]) -> GoogleSheetsConnector:
    """Connector cho URL/ID nhập tay (live, token từ env) hoặc mặc định (env/mock)."""
    if not spreadsheet or not spreadsheet.strip():
        return build_connector()
    try:
        spreadsheet_id = parse_spreadsheet_url(spreadsheet)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not os.environ.get(ACCESS_TOKEN_ENV, "") and not service_account_configured():
        raise HTTPException(
            status_code=400,
            detail=(
                "Chưa có quyền chỉ đọc Google Sheets trong env — không đọc được bảng thật. "
                f"Đặt {ACCESS_TOKEN_ENV} (scope sheets.readonly) hoặc service account Viewer "
                f"({SERVICE_ACCOUNT_FILE_ENV} trỏ tới JSON ngoài repo, token tự refresh). KHÔNG gửi secret vào chat."
            ),
        )
    return GoogleSheetsConnector(spreadsheet_id=spreadsheet_id, use_mock=False)


class AnalyzeRequest(BaseModel):
    """Body cho POST /sheets/analyze — URL hoặc Spreadsheet ID."""

    spreadsheet: str


class PreviewRequest(BaseModel):
    """Body cho POST /sheets/preview — đọc một tab theo sheetId, không lưu dữ liệu."""

    spreadsheet: str
    sheet_id: int


class SourceReportRequest(BaseModel):
    """Body cho POST /sheets/report — đọc báo cáo nguồn từ workbook được chọn."""

    spreadsheet: str


@router.get("/mode")
def sheets_mode() -> dict[str, Any]:
    """Trạng thái connector mặc định: mock/live + cách xác thực (không lộ secret)."""
    connector = build_connector()
    return {
        "mode": connector.mode,
        "spreadsheet_id_configured": connector.spreadsheet_key != "mock",
        "auth": connector.auth_method,
    }


@router.get("/structure")
def sheets_structure_analysis(spreadsheet: Optional[str] = Query(None)) -> dict[str, Any]:
    """Phân tích cấu trúc workbook (mặc định mock khi chưa cấu hình — D-028)."""
    connector = _connector_for(spreadsheet)
    try:
        return sheets_structure.analyze_workbook_detailed(connector)
    except SheetsAPIError as exc:
        status = 401 if isinstance(exc, SheetsAuthError) or getattr(exc, "status_code", None) in (401, 403) else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get("/structure/proposal")
def sheets_mapping_proposal(spreadsheet: Optional[str] = Query(None)) -> list[dict[str, Any]]:
    """Đề xuất mapping từ cấu trúc đã phân tích (PROPOSED — chưa xác nhận)."""
    connector = _connector_for(spreadsheet)
    try:
        structure = sheets_structure.analyze_workbook_detailed(connector)
    except SheetsAPIError as exc:
        status = 401 if isinstance(exc, SheetsAuthError) or getattr(exc, "status_code", None) in (401, 403) else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return sheets_structure.propose_mapping(structure)


@router.post("/analyze")
def sheets_analyze(request: AnalyzeRequest = Body(...)) -> dict[str, Any]:
    """Phân tích URL/ID nhập tay → preview cấu trúc + mapping (KHÔNG lưu gì)."""
    connector = _connector_for(request.spreadsheet)
    try:
        structure = sheets_structure.analyze_workbook_detailed(connector)
    except SheetsAPIError as exc:
        status = 401 if isinstance(exc, SheetsAuthError) or getattr(exc, "status_code", None) in (401, 403) else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return {
        "spreadsheet_key": structure["spreadsheet_key"],
        "mode": structure["mode"],
        "structure": structure,
        "proposals": sheets_structure.propose_mapping(structure),
    }


@router.post("/preview")
def sheets_preview(request: PreviewRequest = Body(...)) -> dict[str, Any]:
    """Đọc giá trị/formula của đúng tab theo sheetId và trả địa chỉ ô nguồn — không ghi DB."""
    connector = _connector_for(request.spreadsheet)
    try:
        matches = [sheet for sheet in connector.list_sheets() if sheet.get("sheet_id") == request.sheet_id and not sheet.get("hidden")]
        if len(matches) != 1:
            raise HTTPException(status_code=404, detail="Không tìm thấy đúng một tab có sheetId này")
        detail = connector.read_sheet_detail(matches[0]["title"])
        analysis = sheets_structure.analyze_sheet_detail(detail)
    except SheetsAPIError as exc:
        status = 401 if isinstance(exc, SheetsAuthError) or getattr(exc, "status_code", None) in (401, 403) else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    return {
        "mode": connector.mode,
        "sheet_id": request.sheet_id,
        "preview_status": "PREVIEW",
        "mapping_status": "NEEDS_CONFIRMATION",
        "analysis": analysis,
        "source": sheets_structure.build_cell_preview(detail),
    }


@router.post("/report")
def sheets_source_report(request: SourceReportRequest = Body(...)) -> dict[str, Any]:
    """Đọc summary và các tab khách được summary tham chiếu; không ghi Sheets/DB."""
    connector = _connector_for(request.spreadsheet)
    try:
        return sheets_report.build_sheets_source_report(connector)
    except SheetsAPIError as exc:
        status = 401 if isinstance(exc, SheetsAuthError) or getattr(exc, "status_code", None) in (401, 403) else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post("/mappings/proposal")
def sheets_save_proposal(
    actor: str = Query("owner", description="Ai duyệt lưu proposal (audit log)"),
    spreadsheet: Optional[str] = Query(None, description="URL hoặc Spreadsheet ID (mặc định theo env/mock)"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Lưu đề xuất mapping vào `sheet_mappings` (idempotent; CONFIRMED không bị đè)."""
    connector = _connector_for(spreadsheet)
    try:
        structure = sheets_structure.analyze_workbook_detailed(connector)
    except SheetsAPIError as exc:
        status = 401 if isinstance(exc, SheetsAuthError) or getattr(exc, "status_code", None) in (401, 403) else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    proposals = sheets_structure.propose_mapping(structure)
    if not proposals:
        raise HTTPException(status_code=400, detail="Không có đề xuất mapping nào để lưu")
    result = sheets_structure.persist_proposals(db, structure["spreadsheet_key"], proposals, actor=actor)
    return {"spreadsheet_key": structure["spreadsheet_key"], **result}


@router.post("/mappings/confirm")
def sheets_confirm_mapping(
    sheet_name: str = Query(..., description="Tên sheet cần xác nhận mapping"),
    actor: str = Query("owner", description="Ai xác nhận (audit log)"),
    spreadsheet: Optional[str] = Query(None, description="URL hoặc Spreadsheet ID (mặc định theo env/mock)"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Xác nhận mapping của 1 sheet: PROPOSED → CONFIRMED + audit log (DB nội bộ)."""
    connector = _connector_for(spreadsheet)
    result = sheets_structure.confirm_sheet_mappings(db, connector.spreadsheet_key, sheet_name, actor=actor)
    if result["confirmed"] == 0:
        raise HTTPException(
            status_code=404, detail="Không có mapping PROPOSED nào cho sheet này — hãy lưu proposal trước"
        )
    return {"sheet_name": sheet_name, **result}


@router.get("/compare")
def sheets_compare_with_db(
    sheet_name: str = Query(..., description="Tên sheet khách cần đối chiếu"),
    sheet: Optional[str] = Query(None, alias="sheet", description="Bí danh của sheet_name"),
    spreadsheet: Optional[str] = Query(None, description="URL hoặc Spreadsheet ID (mặc định theo env/mock)"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Đối chiếu chi tiêu dòng Sheets với snapshot Meta trong DB — CHỈ ĐỌC (Q-007).

    Yêu cầu mapping CONFIRMED đủ DATE + ACCOUNT + SPEND; thiếu → NEEDS_MAPPING.
    Sheet VND vs Meta USD → NEEDS_CONFIRMATION (Q-005), không tự đổi tiền.
    """
    connector = _connector_for(spreadsheet)
    try:
        return sheets_compare.compare_sheet_with_db(db, connector, sheet or sheet_name)
    except SheetsAPIError as exc:
        status = 401 if isinstance(exc, SheetsAuthError) or getattr(exc, "status_code", None) in (401, 403) else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get("/mappings")
def sheets_list_mappings(
    sheet_name: Optional[str] = Query(None, description="Lọc theo tên sheet"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Danh sách mapping đã lưu (cấu hình nội bộ, không đụng bảng thật)."""
    query = select(SheetMapping).order_by(SheetMapping.sheet_name, SheetMapping.column_index)
    if sheet_name:
        query = query.where(SheetMapping.sheet_name == sheet_name)
    rows = db.execute(query).scalars().all()
    return [
        {
            "id": row.id,
            "spreadsheet_key": row.spreadsheet_key,
            "sheet_name": row.sheet_name,
            "column_index": row.column_index,
            "column_letter": row.column_letter,
            "header": row.header,
            "role": row.role,
            "field": row.field,
            "status": row.status,
            "note": row.note,
        }
        for row in rows
    ]
