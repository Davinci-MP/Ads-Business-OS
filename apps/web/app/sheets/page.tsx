"use client";

import { useEffect, useState } from "react";
import SavedSources from "./saved-sources";
import CustomerSetup from "./customer-setup";
import LinkReview from "./link-review";
import {
  fetchJson,
  postJson,
  SHEETS_REPORT_WORKBOOK_KEY,
  type SavedMapping,
  type SheetCellPreview,
  type SheetPreviewCell,
  type SheetPreviewResponse,
  type SheetsMode,
  type SheetsSheetStructure,
} from "../../lib/api";

const SHEETS_ANALYZE_STATE_KEY = "adsos.sheets.analyze";

type SheetAnalyzeState = {
  spreadsheet: string;
  mode: { mode: string; spreadsheet_id_configured: boolean };
  result: AnalyzeResult;
  at: string;
};

type AnalyzeResult = {
  spreadsheet_key: string;
  mode: string;
  structure: { sheets: SheetsSheetStructure[] };
  proposals: {
    sheet_name: string;
    sheet_type?: string;
    column_letter: string;
    header: string;
    role: string | null;
    confidence: string | null;
    note: string | null;
    source: {
      samples_formatted: string[];
      number_format: string | null;
      format_source: string | null;
      needs_confirmation: boolean;
      has_formula: boolean;
      merge_count: number;
      confirm_reasons?: string[];
    };
    target: { area: string; field: string } | null;
  }[];
};

type CustomerDayGroup = {
  date: string | null;
  dateRange: string;
  startRow: number;
  endRow: number;
  accounts: { rowNumber: number; cells: Record<string, SheetPreviewCell> }[];
  deposits: { rowNumber: number; cells: Record<string, SheetPreviewCell> }[];
};

function columnLetter(index: number): string {
  let value = index + 1;
  let result = "";
  while (value > 0) {
    value -= 1;
    result = String.fromCharCode(65 + (value % 26)) + result;
    value = Math.floor(value / 26);
  }
  return result;
}

function cellsByColumn(row: SheetCellPreview["rows"][number] | undefined) {
  const cells: Record<string, SheetPreviewCell> = {};
  for (const cell of row?.cells ?? []) {
    const column = cell.address.match(/^[A-Z]+/)?.[0];
    if (column) cells[column] = cell;
  }
  return cells;
}

function cellValue(cells: Record<string, SheetPreviewCell>, column: string) {
  return cells[column]?.value;
}

function dateFromCell(cell: SheetPreviewCell | undefined): string | null {
  if (!cell || cell.number_format?.type !== "DATE" || typeof cell.value !== "number") return null;
  const date = new Date(Date.UTC(1899, 11, 30) + Math.floor(cell.value) * 86_400_000);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString().slice(0, 10);
}

function customerDayGroups(preview: SheetPreviewResponse): CustomerDayGroup[] {
  const source = preview.source;
  const dateColumn = preview.analysis.columns.find((column) =>
    /^(ngày|ngay|date)$/i.test(column.header.trim()),
  )?.column_letter;
  if (!dateColumn) return [];

  const rowsByNumber = new Map(
    source.rows.map((row) => [row.row_number, { row, cells: cellsByColumn(row) }]),
  );
  const dateColumnIndex = preview.analysis.columns.find((column) => column.column_letter === dateColumn)?.column_index;
  if (dateColumnIndex === undefined) return [];
  const ranges = new Map<string, { dateRange: string; startRow: number; endRow: number }>();
  for (const { row, cells } of rowsByNumber.values()) {
    if (!dateFromCell(cells[dateColumn])) continue;
    const rowIndex = row.row_number - 1;
    const merge = source.merges.find(
      (candidate) =>
        candidate.start_row <= rowIndex &&
        rowIndex < candidate.end_row &&
        candidate.start_col <= dateColumnIndex &&
        dateColumnIndex < candidate.end_col,
    );
    const startRow = merge ? merge.start_row + 1 : row.row_number;
    const endRow = merge ? merge.end_row : row.row_number;
    ranges.set(`${startRow}:${endRow}`, {
      dateRange: merge?.range ?? `${dateColumn}${row.row_number}`,
      startRow,
      endRow,
    });
  }
  const groups: CustomerDayGroup[] = [];

  for (const { dateRange, startRow, endRow } of [...ranges.values()].sort((left, right) => left.startRow - right.startRow)) {
    const anchor = rowsByNumber.get(startRow);
    if (!anchor) continue;
    const date = dateFromCell(anchor.cells[dateColumn]);
    if (!date) continue;

    const accounts: CustomerDayGroup["accounts"] = [];
    const deposits: CustomerDayGroup["deposits"] = [];
    for (let rowNumber = startRow; rowNumber <= endRow; rowNumber += 1) {
      const entry = rowsByNumber.get(rowNumber);
      if (!entry) continue;
      const { cells } = entry;
      const accountId = cellValue(cells, "C");
      if (typeof accountId === "string" && accountId.length > 0) {
        accounts.push({ rowNumber, cells });
      }
      const usdt = cellValue(cells, "J");
      const vndFormula = cells.K?.formula ?? "";
      const hasUsdtInput = usdt !== null && usdt !== undefined && usdt !== "";
      const hasUsdtConversion = /J\$?\d+/i.test(vndFormula) && /L\$?\d+/i.test(vndFormula);
      if (hasUsdtInput || hasUsdtConversion) {
        deposits.push({ rowNumber, cells });
      }
    }

    if (accounts.length > 0 || deposits.length > 0) {
      groups.push({ date, dateRange, startRow, endRow, accounts, deposits });
    }
  }

  return groups;
}

function formulaHasMissingInput(cell: SheetPreviewCell, cells: Record<string, SheetPreviewCell>): boolean {
  const isMissing = (candidate: SheetPreviewCell, visited: Set<string>): boolean => {
    if (!candidate.formula) return false;
    if (visited.has(candidate.address)) return false;
    visited.add(candidate.address);
    const references = candidate.formula.match(/\$?[A-Z]{1,3}\$?\d+/g) ?? [];
    return references.some((reference) => {
      const address = reference.replace(/\$/g, "");
      const currentRow = Number(candidate.address.match(/\d+$/)?.[0]);
      const referenceRow = Number(address.match(/\d+$/)?.[0]);
      if (!currentRow || referenceRow !== currentRow) return false;
      const input = cellsByAddress(cells, address);
      return (
        !input ||
        input.value === null ||
        input.value === undefined ||
        input.value === "" ||
        isMissing(input, visited)
      );
    });
  };
  return isMissing(cell, new Set());
}

function cellsByAddress(cells: Record<string, SheetPreviewCell>, address: string) {
  return Object.values(cells).find((cell) => cell.address === address);
}

function SheetValue({
  cell,
  cells,
}: {
  cell: SheetPreviewCell | undefined;
  cells: Record<string, SheetPreviewCell>;
}) {
  if (!cell) return <span className="text-slate-400">—</span>;
  const missingInput = formulaHasMissingInput(cell, cells);
  return (
    <span className="inline-flex flex-col gap-1">
      <span className="font-medium text-slate-900">
        {missingInput ? "Thiếu đầu vào" : String(cell.value)}
      </span>
      <span className="text-xs text-slate-500">
        {cell.formatted_value && cell.formatted_value !== String(cell.value)
          ? `Hiển thị Sheet: ${cell.formatted_value} · `
          : ""}
        <code>{cell.address}</code>
        {cell.formula ? ` · ${cell.formula}` : ""}
        {missingInput ? " · kết quả công thức không xác nhận" : ""}
      </span>
    </span>
  );
}

export default function SheetsPage() {
  const [spreadsheetInput, setSpreadsheetInput] = useState("");
  const [mode, setMode] = useState<SheetsMode | null>(null);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [restoredAt, setRestoredAt] = useState<string | null>(null);

  useEffect(() => {
    try {
      const raw = window.sessionStorage.getItem(SHEETS_ANALYZE_STATE_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw) as SheetAnalyzeState;
      if (!saved?.result || !saved?.mode || typeof saved.spreadsheet !== "string") return;
      setSpreadsheetInput(saved.spreadsheet);
      setMode(saved.mode);
      setResult(saved.result);
      setRestoredAt(saved.at ?? null);
    } catch {
      // dữ liệu phiên hỏng thì bỏ qua; người dùng phân tích lại như bình thường.
    }
  }, []);

  const [mappings, setMappings] = useState<SavedMapping[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [summaryPreview, setSummaryPreview] = useState<SheetPreviewResponse | null>(null);
  const [customerPreview, setCustomerPreview] = useState<SheetPreviewResponse | null>(null);
  const [readAt, setReadAt] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState("");

  async function loadReportPreview(analysis: AnalyzeResult) {
    const sheets = analysis.structure?.sheets ?? [];
    const summary = sheets.find((sheet) => sheet.title === "TỔNG T10");
    const customer = sheets.find((sheet) => sheet.title === "JOKER");
    if (summary?.sheet_id === undefined || customer?.sheet_id === undefined) {
      setSummaryPreview(null);
      setCustomerPreview(null);
      setPreviewError(
        "Không tìm thấy đủ tab TỔNG T10 và JOKER trong workbook vừa đọc. Chọn lại đúng workbook và thử lại.",
      );
      return;
    }

    setPreviewBusy(true);
    setPreviewError(null);
    setSummaryPreview(null);
    setCustomerPreview(null);
    setSelectedDate("");
    try {
      const [summaryData, customerData] = await Promise.all([
        postJson<SheetPreviewResponse>("/sheets/preview", {
          spreadsheet: spreadsheetInput.trim(),
          sheet_id: summary.sheet_id,
        }),
        postJson<SheetPreviewResponse>("/sheets/preview", {
          spreadsheet: spreadsheetInput.trim(),
          sheet_id: customer.sheet_id,
        }),
      ]);
      if (summaryData.mode !== "live" || customerData.mode !== "live") {
        throw new Error("Nguồn trả về không ở chế độ LIVE; không hiển thị như dữ liệu Sheets thực.");
      }
      setSummaryPreview(summaryData);
      setCustomerPreview(customerData);
      setSelectedDate(customerDayGroups(customerData).find((group) => group.date)?.date ?? "");
      setReadAt(new Date().toISOString());
    } catch (e) {
      setPreviewError(e instanceof Error ? e.message : String(e));
    } finally {
      setPreviewBusy(false);
    }
  }

  async function run(path: string, body: unknown, okMessage: (data: unknown) => string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const data = await postJson<Record<string, unknown>>(path, body);
      setNotice(okMessage(data));
      return data;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    } finally {
      setBusy(false);
    }
  }

  const spreadsheetQuery = spreadsheetInput.trim()
    ? `&spreadsheet=${encodeURIComponent(spreadsheetInput.trim())}`
    : "";

  async function analyze() {
    setSummaryPreview(null);
    setCustomerPreview(null);
    setPreviewError(null);
    setReadAt(null);
    const data = await run(
      "/sheets/analyze",
      { spreadsheet: spreadsheetInput.trim() },
      (d) => `Đã phân tích ${((d as AnalyzeResult).structure?.sheets ?? []).length} sheet (chỉ đọc — không ghi gì vào Google Sheets).`,
    );
    if (data) {
      const trimmed = spreadsheetInput.trim();
      if (trimmed) {
        window.sessionStorage.setItem(SHEETS_REPORT_WORKBOOK_KEY, trimmed);
      }
      const analyzed = data as unknown as AnalyzeResult;
      setResult(analyzed);
      setRestoredAt(null);
      const analyzedMode: SheetsMode = {
        mode: analyzed.mode,
        spreadsheet_id_configured: analyzed.spreadsheet_key !== "mock",
      };
      setMode(analyzedMode);
      try {
        // Lưu trạng thái phân tích của phiên (sessionStorage tự xoá khi đóng tab)
        // để quay lại trang bằng back/forward mà không cần phân tích lại ngay.
        window.sessionStorage.setItem(
          SHEETS_ANALYZE_STATE_KEY,
          JSON.stringify({
            spreadsheet: trimmed,
            mode: analyzedMode,
            result: analyzed,
            at: new Date().toISOString(),
          } satisfies SheetAnalyzeState),
        );
      } catch {
        // Dữ liệu quá lớn hay sessionStorage bị tắt thì bỏ qua, không chặn luồng chính.
      }
      await loadReportPreview(analyzed);
    }
  }

  async function saveProposal() {
    await run(
      `/sheets/mappings/proposal?actor=owner${spreadsheetQuery}`,
      {},
      (d) =>
        `Đã lưu đề xuất mapping: tạo ${(d as { created?: number }).created ?? 0}, cập nhật ${(d as { updated?: number }).updated ?? 0}, giữ nguyên ${(d as { unchanged?: number }).unchanged ?? 0}.`,
    );
    const saved = await fetchJson<SavedMapping[]>("/sheets/mappings");
    setMappings(saved);
  }

  async function confirmSheet(sheetName: string) {
    await run(
      `/sheets/mappings/confirm?sheet_name=${encodeURIComponent(sheetName)}&actor=owner${spreadsheetQuery}`,
      {},
      (d) => `Đã xác nhận mapping sheet "${sheetName}": ${(d as { confirmed?: number }).confirmed ?? 0} cột (PROPOSED → CONFIRMED).`,
    );
    const saved = await fetchJson<SavedMapping[]>("/sheets/mappings");
    setMappings(saved);
  }

  const dayGroups = customerPreview ? customerDayGroups(customerPreview) : [];
  const availableDates = [...new Set(dayGroups.flatMap((group) => (group.date ? [group.date] : [])))].sort();
  const visibleDayGroups = selectedDate
    ? dayGroups.filter((group) => group.date === selectedDate)
    : dayGroups;
  const summaryHeaderRow = summaryPreview?.source.rows.find(
    (row) => row.row_number === (summaryPreview.analysis.header_row_index ?? -1) + 1,
  );
  const summaryJokerRow = summaryPreview?.source.rows.find(
    (row) => cellsByColumn(row).A?.value === "JOKER",
  );
  const summaryHeaderCells = cellsByColumn(summaryHeaderRow);
  const summaryJokerCells = cellsByColumn(summaryJokerRow);
  const customerSummaryCells = cellsByColumn(
    customerPreview?.source.rows.find((row) => row.row_number === 1),
  );
  const jokerOpeningBalanceCell =
    summaryPreview?.source.title === "TỔNG T10" &&
    customerPreview?.source.title === "JOKER" &&
    summaryJokerCells.C?.formula?.replace(/['$]/g, "").includes("JOKER!J1")
      ? customerSummaryCells.J
      : undefined;
  const summaryColumns = ["A", "B", "C", "D", "E", "F", "G"];
  const periodLabel =
    availableDates.length > 0
      ? `${availableDates[0]} → ${availableDates[availableDates.length - 1]}`
      : "Chưa xác định được từ ô ngày";

  return (
    <main className="page">
      <h1>Google Sheets — báo cáo preview và phân tích cấu trúc</h1>
      <SavedSources />
      <CustomerSetup />
      <LinkReview />
      <p className="notice">        NGUỒN GOOGLE SHEETS — PREVIEW, CHƯA ĐỐI CHIẾU META. Báo cáo này đọc trực tiếp các ô từ
        Sheets; không nhập vào sổ tài chính, không cộng chung với Manual/Meta và không thay đổi dữ liệu
        hay công thức nguồn.
      </p>

      <div className="section-title">Nguồn Google Sheets</div>
      <div className="toolbar flex-wrap">
        <input
          style={{ minWidth: 0, width: "min(100%, 560px)", maxWidth: "100%" }}
          placeholder="https://docs.google.com/spreadsheets/d/… hoặc ID"
          value={spreadsheetInput}
          onChange={(e) => setSpreadsheetInput(e.target.value)}
          aria-label="Spreadsheet URL hoặc ID"
        />
        <button disabled={busy || previewBusy || !spreadsheetInput.trim()} onClick={() => void analyze()}>
          {busy || previewBusy ? "Đang đọc Sheets…" : "Đọc báo cáo preview"}
        </button>
      </div>
      {mode && (
        <p className="muted">
          Chế độ connector mặc định: {mode.mode === "live" ? "LIVE" : "MOCK"}; trạng thái preview chỉ lấy từ
          phản hồi của từng lần đọc.
          {mode.mode !== "live" &&
            " URL cụ thể vẫn có thể được đọc LIVE nếu backend có quyền đọc-only; giao diện sẽ không giả nhãn LIVE khi API trả MOCK."}
        </p>
      )}
      {restoredAt && (
        <p className="muted">
          Đã khôi phục kết quả phân tích đã lưu trong phiên này (lúc{" "}
          {new Date(restoredAt).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}). Workbook có thể đã
          thay đổi sau thời điểm đó; bấm "Đọc báo cáo preview" để đọc lại hiện hành.
        </p>
      )}
      {notice && <p className="notice ok">{notice}</p>}
      {error && (
        <div className="error-box" role="alert">
          <p>{error}</p>
          <button
            className="mt-2 rounded-md border border-red-300 bg-white px-3 py-2 font-medium hover:bg-red-100"
            disabled={busy || previewBusy || !spreadsheetInput.trim()}
            onClick={() => void analyze()}
          >
            Thử lại đọc Sheets
          </button>
        </div>
      )}

      <section className="mt-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-slate-900">Báo cáo Sheets thực</h2>
            <p className="mt-1 text-sm text-slate-600">
              Preview trực tiếp tab tổng hợp và tab khách; không phải kết quả đối chiếu Meta.
            </p>
          </div>
          <span className="rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-900">
            PREVIEW · CHƯA ĐỐI CHIẾU META
          </span>
        </div>

        {previewBusy && (
          <div className="mt-5 animate-pulse space-y-3" aria-label="Đang tải preview">
            <div className="h-5 w-56 rounded bg-slate-200" />
            <div className="h-20 rounded-lg bg-slate-100" />
            <div className="h-40 rounded-lg bg-slate-100" />
          </div>
        )}
        {previewError && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">
            <p>{previewError}</p>
            <button
              className="mt-3 rounded-md border border-red-300 bg-white px-3 py-2 font-medium hover:bg-red-100"
              disabled={previewBusy || !spreadsheetInput.trim()}
              onClick={() => (result ? void loadReportPreview(result) : void analyze())}
            >
              Thử lại
            </button>
          </div>
        )}
        {!previewBusy && !previewError && !summaryPreview && !customerPreview && (
          <p className="mt-4 rounded-lg bg-slate-50 p-4 text-sm text-slate-600">
            Nhập URL/ID để đọc preview chỉ đọc. Riêng thao tác lưu nguồn theo kỳ ở trên lưu Spreadsheet ID đã chuẩn hóa trong DB.
          </p>
        )}

        {summaryPreview && customerPreview && (
          <div className="mt-5 space-y-6">
            <div className="grid gap-3 rounded-lg bg-slate-50 p-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
              <p>
                <span className="text-slate-500">Nguồn:</span> GOOGLE SHEETS · {summaryPreview.mode.toUpperCase()}
              </p>
              <p>
                <span className="text-slate-500">Đọc lúc:</span>{" "}
                {readAt
                  ? new Date(readAt).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })
                  : "—"}
              </p>
              <p>
                <span className="text-slate-500">Tab tổng hợp:</span> {summaryPreview.source.title} · sheetId{" "}
                {summaryPreview.sheet_id}
              </p>
              <p>
                <span className="text-slate-500">Tab khách:</span> {customerPreview.source.title} · sheetId{" "}
                {customerPreview.sheet_id}
              </p>
              <p className="sm:col-span-2">
                <span className="text-slate-500">Kỳ theo các ô ngày:</span> {periodLabel}
              </p>
              <p className="sm:col-span-2">
                <span className="text-slate-500">Mapping:</span> {summaryPreview.mapping_status} · không lưu mapping
              </p>
            </div>

            <div>
              <h3 className="text-lg font-semibold text-slate-900">
                Tổng hợp — {summaryPreview.source.title}
              </h3>
              {summaryJokerRow ? (
                <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200">
                  <table className="min-w-[760px] w-full text-left text-sm">
                    <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                      <tr>
                        {summaryColumns.map((column) => (
                          <th className="px-3 py-3" key={column}>
                            {summaryHeaderCells[column]?.value ?? `Cột ${column}`}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        {summaryColumns.map((column) => (
                          <td className="border-t border-slate-100 px-3 py-3 align-top" key={column}>
                            {column === "C" && jokerOpeningBalanceCell && (
                              <span className="mb-1 block text-xs font-medium text-slate-700">
                                Ngân sách chuyển từ kỳ trước (VND)
                              </span>
                            )}
                            <SheetValue cell={summaryJokerCells[column]} cells={summaryJokerCells} />
                          </td>
                        ))}
                      </tr>
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="mt-2 rounded-lg bg-slate-50 p-4 text-sm text-slate-600">
                  Không tìm thấy dòng khách JOKER trong tab tổng hợp vừa đọc.
                </p>
              )}
              <p className="mt-2 text-xs text-slate-500">
                Giá trị gốc và công thức lấy trực tiếp từ từng ô Sheets; không cộng dòng tổng với chi tiết.
              </p>
            </div>

            <div>
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <h3 className="text-lg font-semibold text-slate-900">
                    Chi tiết khách — {customerPreview.source.title}
                  </h3>
                  <p className="text-sm text-slate-600">
                    Cấu trúc cột được diễn giải riêng cho tab này; không áp dụng sang tab khách khác.
                  </p>
                </div>
                <label className="flex items-center gap-2 text-sm text-slate-700">
                  Ngày dữ liệu
                  <select
                    className="rounded-md border border-slate-300 bg-white px-3 py-2"
                    value={selectedDate}
                    onChange={(event) => setSelectedDate(event.target.value)}
                  >
                    <option value="">Tất cả ngày đọc được</option>
                    {availableDates.map((date) => (
                      <option key={date} value={date}>
                        {date}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              {jokerOpeningBalanceCell && (
                <div className="mt-4 rounded-lg border border-sky-200 bg-sky-50 p-4">
                  <p className="font-semibold text-slate-900">
                    Ngân sách chuyển từ kỳ trước (VND)
                  </p>
                  <p className="mt-1 text-xs text-slate-600">
                    Số dư đầu kỳ của JOKER cho kỳ dữ liệu {periodLabel}; hiển thị một lần ở cấp khách/kỳ, không lặp
                    theo ngày, TKQC hoặc dòng nhận tiền.
                  </p>
                  <div className="mt-2">
                    <SheetValue cell={jokerOpeningBalanceCell} cells={customerSummaryCells} />
                  </div>
                </div>
              )}

              {visibleDayGroups.length === 0 ? (
                <p className="mt-3 rounded-lg bg-slate-50 p-4 text-sm text-slate-600">
                  Chưa có dòng chi tiết với ô ngày được nhận diện trong phạm vi merge.
                </p>
              ) : (
                <div className="mt-4 space-y-5">
                  {visibleDayGroups.map((group) => {
                    const dateRow = customerPreview.source.rows.find((row) => row.row_number === group.startRow);
                    const dateCells = cellsByColumn(dateRow);
                    const dateColumn = customerPreview.analysis.columns.find((column) =>
                      /^(ngày|ngay|date)$/i.test(column.header.trim()),
                    )?.column_letter;
                    const dateCell = dateColumn ? dateCells[dateColumn] : undefined;
                    return (
                      <div className="overflow-hidden rounded-lg border border-slate-200" key={`${group.date}-${group.startRow}`}>
                        <div className="flex flex-wrap items-center justify-between gap-2 bg-slate-50 px-4 py-3">
                          <div>
                            <h4 className="font-semibold text-slate-900">
                              {group.date}
                              {dateCell?.formatted_value ? ` · hiển thị Sheet: ${dateCell.formatted_value}` : ""}
                            </h4>
                            <p className="text-xs text-slate-500">
                              Ô ngày <code>{dateCell?.address ?? "—"}</code>
                              {dateCell?.number_format?.type === "DATE" ? " · ngày lấy từ giá trị DATE của ô" : ""}
                              {" · phạm vi "}
                              {group.dateRange}
                            </p>
                          </div>
                          <span className="text-xs text-slate-600">
                            {group.accounts.length} dòng có ID tài khoản · dữ liệu chưa nhập sổ
                          </span>
                        </div>
                        <div className="overflow-x-auto">
                          <table className="min-w-[1280px] w-full text-left text-sm">
                            <thead className="bg-white text-xs text-slate-600">
                              <tr>
                                <th className="px-3 py-3">Loại tiền TK (B)</th>
                                <th className="px-3 py-3">ID TKQC (C)</th>
                                <th className="px-3 py-3">Chi tiêu gốc (E nếu USD, F nếu VND)</th>
                                <th className="px-3 py-3">Tỷ giá USD/VND (I)</th>
                                <th className="px-3 py-3">Chi tiêu VND (F)</th>
                                <th className="px-3 py-3">Phí (G)</th>
                                <th className="px-3 py-3">Tổng gồm phí (H)</th>
                              </tr>
                            </thead>
                            <tbody>
                              {group.accounts.map((account) => {
                                const currency = String(cellValue(account.cells, "B") ?? "");
                                const usdInput = account.cells.E;
                                const vndValue = account.cells.F;
                                const spendOriginal =
                                  currency === "USD"
                                    ? usdInput
                                    : currency === "VND"
                                      ? vndValue
                                      : usdInput?.value != null
                                        ? usdInput
                                        : vndValue;
                                const missingSpendInput =
                                  currency === "USD" &&
                                  (!usdInput || usdInput.value === null || usdInput.value === "") &&
                                  formulaHasMissingInput(vndValue, account.cells);
                                return (
                                  <tr className="border-t border-slate-100 align-top" key={account.rowNumber}>
                                    <td className="px-3 py-3">
                                      <SheetValue cell={account.cells.B} cells={account.cells} />
                                    </td>
                                    <td className="px-3 py-3 font-mono text-xs">
                                      <SheetValue cell={account.cells.C} cells={account.cells} />
                                    </td>
                                    <td className="px-3 py-3">
                                      {missingSpendInput ? (
                                        <span className="inline-flex flex-col gap-1">
                                          <span className="font-medium text-amber-800">Thiếu đầu vào</span>
                                          <span className="text-xs text-slate-500">
                                            <code>{usdInput?.address ?? `E${account.rowNumber}`}</code> trống; không coi kết quả 0 là chi tiêu đã xác nhận
                                          </span>
                                        </span>
                                      ) : (
                                        <SheetValue cell={spendOriginal} cells={account.cells} />
                                      )}
                                    </td>
                                    <td className="px-3 py-3">
                                      <SheetValue
                                        cell={currency === "USD" ? account.cells.I : undefined}
                                        cells={account.cells}
                                      />
                                    </td>
                                    <td className="px-3 py-3">
                                      <SheetValue cell={vndValue} cells={account.cells} />
                                    </td>
                                    <td className="px-3 py-3">
                                      <SheetValue cell={account.cells.G} cells={account.cells} />
                                    </td>
                                    <td className="px-3 py-3">
                                      <SheetValue cell={account.cells.H} cells={account.cells} />
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>

                        {group.deposits.length > 0 && (
                          <div className="border-t border-slate-200 bg-emerald-50/60 p-4">
                            <h5 className="font-semibold text-slate-900">
                              Nhận USDT trong khối ngày — mỗi dòng nguồn hiển thị một lần
                            </h5>
                            <div className="mt-3 space-y-3">
                              {group.deposits.map((deposit) => (
                                <div
                                  className="grid gap-3 rounded-md border border-emerald-200 bg-white p-3 text-sm sm:grid-cols-3"
                                  key={deposit.rowNumber}
                                >
                                  <div>
                                    <p className="text-xs text-slate-500">USDT (J) · dòng {deposit.rowNumber}</p>
                                    <SheetValue cell={deposit.cells.J} cells={deposit.cells} />
                                  </div>
                                  <div>
                                    <p className="text-xs text-slate-500">Tỷ giá nhận (L)</p>
                                    <SheetValue cell={deposit.cells.L} cells={deposit.cells} />
                                  </div>
                                  <div>
                                    <p className="text-xs text-slate-500">Giá trị VND (K)</p>
                                    <SheetValue cell={deposit.cells.K} cells={deposit.cells} />
                                  </div>
                                </div>
                              ))}
                            </div>
                            <p className="mt-2 text-xs text-slate-500">
                              Dòng nhận tiền được tách khỏi các dòng TKQC, không nhân bản theo số tài khoản. Kết quả lấy từ Sheets; không quy đổi lại.
                            </p>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              <p className="mt-3 text-xs text-slate-500">
                Số hiển thị “giá trị gốc” lấy từ effectiveValue; dòng phụ ghi cách Sheets định dạng và địa chỉ ô.
                Ô công thức có tham chiếu đầu vào trống được đánh dấu thiếu đầu vào.
              </p>
            </div>
          </div>
        )}
      </section>

      {result?.structure?.sheets?.map((sheet) => (
        <section key={sheet.title}>
          <div className="section-title">
            Sheet “{sheet.title}” — {sheet.row_count} dòng · locale {sheet.locale ?? "?"} · header ở dòng{" "}
            {(sheet.header_row_index ?? -1) + 1}
          </div>
          <div className="overflow-x-auto">
            <table>
              <thead>
                <tr>
                  <th>Cột nguồn</th>
                  <th>Header</th>
                  <th>Đề xuất vai trò</th>
                  <th>Đích dự kiến</th>
                  <th>Định dạng</th>
                  <th>Mẫu ô</th>
                  <th>Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {sheet.columns.map((col) => {
                  const proposal = result.proposals.find(
                    (p) => p.sheet_name === sheet.title && p.column_letter === col.column_letter,
                  );
                  return (
                    <tr key={col.column_letter}>
                      <td>{col.column_letter}</td>
                      <td>{col.header}</td>
                      <td>{proposal?.role ?? "—"}</td>
                      <td>{proposal?.target ? `${proposal.target.area} · ${proposal.target.field}` : "—"}</td>
                      <td>
                        {col.number_format
                          ? `${col.number_format.type}${col.number_format.currency ? ` [${col.number_format.currency}]` : ""}`
                          : col.format_source === "heuristic"
                            ? "heuristic (text)"
                            : "—"}
                      </td>
                      <td className="muted">{(col.samples_formatted?.[0] ?? col.samples[0] ?? "—") as string}</td>
                      <td>
                        {col.needs_confirmation ? (
                          <span className="tag bad">NEEDS_CONFIRMATION</span>
                        ) : proposal?.role ? (
                          <span className="tag ok">Nhận diện chắc</span>
                        ) : (
                          <span className="tag warn">Chờ xác nhận</span>
                        )}
                        {proposal?.source?.confirm_reasons?.length ? (
                          <ul className="muted">
                            {proposal.source.confirm_reasons.map((reason, i) => (
                              <li key={i}>{reason}</li>
                            ))}
                          </ul>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {sheet.notes.length > 0 && (
            <ul className="muted">
              {sheet.notes.map((note, i) => (
                <li key={i}>{note}</li>
              ))}
            </ul>
          )}
          <div className="toolbar">
            <button disabled={busy} onClick={() => void saveProposal()}>
              Lưu đề xuất mapping
            </button>
            <button disabled={busy} onClick={() => void confirmSheet(sheet.title)}>
              Xác nhận mapping sheet này
            </button>
          </div>
        </section>
      ))}

      {mappings.length > 0 && (
        <section>
          <div className="section-title">Mapping đã lưu ({mappings.length})</div>
          <div className="overflow-x-auto">
            <table>
              <thead>
                <tr>
                  <th>Sheet</th>
                  <th>Cột</th>
                  <th>Header</th>
                  <th>Vai trò</th>
                  <th>Trạng thái</th>
                  <th>Ghi chú</th>
                </tr>
              </thead>
              <tbody>
                {mappings.map((m) => (
                  <tr key={m.id}>
                    <td>{m.sheet_name}</td>
                    <td>{m.column_letter}</td>
                    <td>{m.header}</td>
                    <td>{m.role ?? "—"}</td>
                    <td>
                      <span className={`tag ${m.status === "CONFIRMED" ? "ok" : "warn"}`}>{m.status}</span>
                    </td>
                    <td className="muted">{m.note ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}
