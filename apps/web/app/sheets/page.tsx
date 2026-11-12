"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  fetchJson,
  patchJson,
  postJson,
  SHEETS_REPORT_WORKBOOK_KEY,
  type SavedMapping,
  type SavedSheetSnapshot,
  type SavedSheetSnapshotEnvelope,
  type SavedSheetSource,
  type SheetCellPreview,
  type SheetPreviewCell,
  type SheetPreviewResponse,
  type SheetsMode,
  type SheetsSheetStructure,
  type SheetsSourceReportCustomer,
  type SheetSyncAttempt,
  type SheetSyncHistoryEnvelope,
} from "../../lib/api";
import { formatVnd } from "../../lib/vnd.mjs";
import ViaSheetWritebackModal from "../../components/ViaSheetWritebackModal";
import CustomerSetup from "./customer-setup";
import LinkReview from "./link-review";

const SHEETS_ANALYZE_STATE_KEY = "adsos.sheets.analyze";
const HISTORY_PREVIEW_COUNT = 5;

type Customer = { id: number; name: string };
type LinkItem = { sheet_id: number; source_title: string; customer_id: number };

type Rollover = {
  previous_closed: boolean;
  unlinked_previous: string[];
  unlinked_current: string[];
  customers: {
    customer_id: number;
    previous_source: string | null;
    next_source: string | null;
    previous_value: string | null;
    next_value: string | null;
    status: string;
    difference: string | null;
    tolerance: string;
  }[];
};

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

function timeText(value: string) {
  return new Date(value).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" });
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
      const input = Object.values(cells).find((c) => c.address === address);
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

function SheetValue({
  cell,
  cells,
}: {
  cell: SheetPreviewCell | undefined;
  cells: Record<string, SheetPreviewCell>;
}) {
  if (!cell) return <span className="text-slate-500">—</span>;
  const missingInput = formulaHasMissingInput(cell, cells);
  return (
    <span className="inline-flex flex-col gap-0.5">
      <span className={missingInput ? "font-semibold text-amber-400" : "font-medium text-slate-100"}>
        {missingInput ? "Thiếu đầu vào" : String(cell.value)}
      </span>
      <span className="text-[11px] text-slate-400">
        {cell.formatted_value && cell.formatted_value !== String(cell.value)
          ? `Sheet: ${cell.formatted_value} · `
          : ""}
        <code className="text-slate-300 bg-slate-800/80 px-1 py-0.5 rounded text-[10px]">{cell.address}</code>
        {cell.formula ? ` · ${cell.formula}` : ""}
        {missingInput ? " · công thức chưa xác nhận" : ""}
      </span>
    </span>
  );
}

export default function SheetsPage() {
  const thisYear = new Date().getFullYear();

  // Zone 1 & 2 Source States
  const [sources, setSources] = useState<SavedSheetSource[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [snapshots, setSnapshots] = useState<SavedSheetSnapshot[]>([]);
  const [history, setHistory] = useState<SheetSyncAttempt[]>([]);
  const [links, setLinks] = useState<LinkItem[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [snapshotId, setSnapshotId] = useState("");
  const [snapshot, setSnapshot] = useState<SavedSheetSnapshot | null>(null);
  const [showAllHistory, setShowAllHistory] = useState(false);
  const [acknowledge, setAcknowledge] = useState(false);

  // Link & Rollover
  const [sheetId, setSheetId] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [confirmRenamed, setConfirmRenamed] = useState(false);
  const [previousId, setPreviousId] = useState("");
  const [rollover, setRollover] = useState<Rollover | null>(null);

  // Add Source Form
  const [showAddSourceForm, setShowAddSourceForm] = useState(false);
  const [month, setMonth] = useState("");
  const [year, setYear] = useState(String(thisYear));
  const [name, setName] = useState("");
  const [nameEdited, setNameEdited] = useState(false);
  const [workbook, setWorkbook] = useState("");
  const [replace, setReplace] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [autoSync, setAutoSync] = useState(false);
  const [makeDefault, setMakeDefault] = useState(false);
  const [savingSource, setSavingSource] = useState(false);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  // Zone 3 Workspace Navigation
  const [activeTab, setActiveTab] = useState<"tabs" | "warnings" | "snapshots" | "history">("tabs");
  const [subTab, setSubTab] = useState<"overview" | "analyzer" | "setup" | "review">("overview");
  const [customerFilter, setCustomerFilter] = useState("");
  const [inspectedCustomer, setInspectedCustomer] = useState<SheetsSourceReportCustomer | null>(null);

  // Live Analyzer & Ad-Hoc Preview
  const [spreadsheetInput, setSpreadsheetInput] = useState("");
  const [mode, setMode] = useState<SheetsMode | null>(null);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [restoredAt, setRestoredAt] = useState<string | null>(null);
  const [mappings, setMappings] = useState<SavedMapping[]>([]);
  const [summaryPreview, setSummaryPreview] = useState<SheetPreviewResponse | null>(null);
  const [customerPreview, setCustomerPreview] = useState<SheetPreviewResponse | null>(null);
  const [readAt, setReadAt] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState("");
  const [analyzeBusy, setAnalyzeBusy] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // Modals & Feedback
  const [showWritebackModal, setShowWritebackModal] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selected = useMemo(
    () => sources.find((source) => String(source.id) === selectedId),
    [sources, selectedId],
  );

  const periodValue = month && /^\d{4}$/.test(year) ? `${year}-${month}` : "";
  const suggestedName = month && /^\d{4}$/.test(year) ? `Báo cáo tháng ${month}/${year}` : "";
  const shownName = nameEdited ? name : suggestedName;

  // Initial load
  const refreshSources = useCallback(async () => {
    try {
      const data = await fetchJson<{ sources: SavedSheetSource[] }>("/sheets/sources");
      setSources(data.sources);
      setSelectedId((current) => {
        if (current && data.sources.some((s) => String(s.id) === current)) return current;
        const defaultSource = data.sources.find((s) => s.is_default);
        if (defaultSource) return String(defaultSource.id);
        const activeSource = data.sources.find((s) => s.active);
        if (activeSource) return String(activeSource.id);
        return data.sources[0] ? String(data.sources[0].id) : "";
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    setWorkbook(window.sessionStorage.getItem(SHEETS_REPORT_WORKBOOK_KEY) ?? "");
    void Promise.all([
      refreshSources(),
      fetchJson<Customer[]>("/customers").then(setCustomers),
      fetchJson<SavedMapping[]>("/sheets/mappings").then(setMappings).catch(() => {}),
    ]);
  }, [refreshSources]);

  // Handle URL Hash navigation (#customer-setup, #link-review, #saved-sources)
  useEffect(() => {
    if (typeof window !== "undefined") {
      const hash = window.location.hash;
      if (hash === "#customer-setup") {
        setActiveTab("tabs");
        setSubTab("setup");
      } else if (hash === "#link-review") {
        setActiveTab("tabs");
        setSubTab("review");
      }
    }
  }, []);

  // Restore session analyze state
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
      // Bỏ qua lỗi session hỏng
    }
  }, []);

  // Refresh source details when selectedId changes
  const refreshDetail = useCallback(async () => {
    if (!selectedId) return;
    try {
      const [versions, attempts, savedLinks] = await Promise.all([
        fetchJson<SavedSheetSnapshotEnvelope>(`/sheets/sources/${selectedId}/snapshots`),
        fetchJson<SheetSyncHistoryEnvelope>(`/sheets/sources/${selectedId}/history`),
        fetchJson<LinkItem[]>(`/sheets/sources/${selectedId}/links`),
      ]);
      setSnapshots(versions.snapshots);
      setHistory(attempts.history);
      setLinks(savedLinks);
      setSnapshotId((id) =>
        versions.snapshots.some((version) => String(version.id) === id)
          ? id
          : String(versions.snapshots[0]?.id ?? ""),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [selectedId]);

  useEffect(() => {
    setSnapshot(null);
    setSnapshots([]);
    setHistory([]);
    setLinks([]);
    setSnapshotId("");
    setRollover(null);
    setShowAllHistory(false);
    void refreshDetail();
  }, [refreshDetail]);

  // Load snapshot report details when snapshotId changes
  useEffect(() => {
    let active = true;
    setSnapshot(null);
    if (selectedId && snapshotId) {
      fetchJson<SavedSheetSnapshot>(`/sheets/sources/${selectedId}/report?snapshot_id=${snapshotId}`)
        .then((value) => {
          if (active) setSnapshot(value);
        })
        .catch((err: unknown) => {
          if (active) setError(err instanceof Error ? err.message : String(err));
        });
    }
    return () => {
      active = false;
    };
  }, [selectedId, snapshotId]);

  // Quick Action: Sync Now
  async function handleSyncNow() {
    if (!selected) return;
    setActionLoading("sync");
    setError(null);
    setNotice(null);
    try {
      const attempt = await postJson<SheetSyncAttempt>(`/sheets/sources/${selected.id}/sync`);
      await refreshDetail();
      await refreshSources();
      if (attempt.status === "ERROR") {
        throw new Error(attempt.error ?? "Đọc nguồn Google Sheets thất bại.");
      }
      setNotice(`Đã đồng bộ thành công bản lưu #${attempt.snapshot_id ?? ""}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setActionLoading(null);
    }
  }

  // Quick Action: Set Default Source
  async function handleSetDefault(source: SavedSheetSource) {
    setActionLoading(`default-${source.id}`);
    setError(null);
    setNotice(null);
    try {
      await patchJson(`/sheets/sources/${source.id}`, { set_default: true });
      await refreshSources();
      setNotice(`Đã đặt kỳ ${source.period} (${source.name}) làm nguồn mặc định.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setActionLoading(null);
    }
  }

  // Quick Action: Toggle Auto Sync
  async function handleToggleAutoSync(source: SavedSheetSource) {
    setActionLoading(`sync-toggle-${source.id}`);
    setError(null);
    setNotice(null);
    try {
      const next = !source.sync_enabled;
      await patchJson(`/sheets/sources/${source.id}`, { sync_enabled: next });
      await refreshSources();
      setNotice(`Đã ${next ? "bật" : "tắt"} tự đồng bộ 15 phút cho ${source.period}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setActionLoading(null);
    }
  }

  // Create Monthly Source
  async function handleCreateSource(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!month) errs.month = "Vui lòng chọn tháng.";
    if (!/^\d{4}$/.test(year) || Number(year) < 2000 || Number(year) > 2100) {
      errs.year = "Nhập năm 4 chữ số (2000–2100).";
    }
    if (!workbook.trim()) errs.workbook = "Dán link hoặc ID Google Sheets.";
    if (!shownName.trim()) errs.name = "Nhập tên báo cáo.";
    setFormErrors(errs);
    if (Object.keys(errs).length > 0) return;

    setSavingSource(true);
    setError(null);
    setNotice(null);
    try {
      const res = await postJson<SavedSheetSource>("/sheets/sources", {
        spreadsheet: workbook.trim(),
        period: periodValue,
        name: shownName.trim(),
        replace_existing: replace,
        set_default: makeDefault,
        sync_enabled: autoSync,
      });
      await refreshSources();
      setSelectedId(String(res.id));
      setNotice(`Đã tạo và kiểm tra thành công nguồn kỳ ${res.period}.`);
      setShowAddSourceForm(false);
      setWorkbook("");
      setReplace(false);
      setConflict(false);
    } catch (err: unknown) {
      const text = err instanceof Error ? err.message : String(err);
      if (/thay thế/.test(text)) {
        setConflict(true);
        setFormErrors({
          form: `Kỳ ${periodValue} đã có một nguồn đang dùng. Tích chọn "Xác nhận thay nguồn" rồi bấm lưu lại.`,
        });
      } else {
        setFormErrors({ form: text });
      }
    } finally {
      setSavingSource(false);
    }
  }

  // Finalize / Close Period
  async function handleFinalizeClosure() {
    if (!selected || !snapshotId) return;
    if (!window.confirm(`Xác nhận chốt kỳ ${selected.period} với bản lưu #${snapshotId}? Sau khi chốt, các lần sync tự động tiếp theo sẽ không ghi đè bản này.`)) return;
    setActionLoading("closure");
    setError(null);
    setNotice(null);
    try {
      await postJson(`/sheets/sources/${selected.id}/closure`, {
        snapshot_id: Number(snapshotId),
        acknowledge_partial: acknowledge,
      });
      await refreshSources();
      await refreshDetail();
      setNotice(`Đã chốt kỳ ${selected.period} thành công với bản #${snapshotId}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setActionLoading(null);
    }
  }

  // Live Analyzer: Analyze
  async function runAnalyze() {
    if (!spreadsheetInput.trim()) return;
    setAnalyzeBusy(true);
    setSummaryPreview(null);
    setCustomerPreview(null);
    setPreviewError(null);
    setError(null);
    setNotice(null);
    try {
      const data = await postJson<AnalyzeResult>("/sheets/analyze", {
        spreadsheet: spreadsheetInput.trim(),
      });
      const trimmed = spreadsheetInput.trim();
      window.sessionStorage.setItem(SHEETS_REPORT_WORKBOOK_KEY, trimmed);
      setResult(data);
      setRestoredAt(null);
      const analyzedMode: SheetsMode = {
        mode: data.mode,
        spreadsheet_id_configured: data.spreadsheet_key !== "mock",
      };
      setMode(analyzedMode);
      window.sessionStorage.setItem(
        SHEETS_ANALYZE_STATE_KEY,
        JSON.stringify({
          spreadsheet: trimmed,
          mode: analyzedMode,
          result: data,
          at: new Date().toISOString(),
        }),
      );
      setNotice(`Đã phân tích ${data.structure?.sheets?.length ?? 0} sheet trong workbook.`);
      await loadReportPreview(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAnalyzeBusy(false);
    }
  }

  async function loadReportPreview(analysis: AnalyzeResult) {
    const sheets = analysis.structure?.sheets ?? [];
    const summary = sheets.find((s) => s.title === "TỔNG T10");
    const customer = sheets.find((s) => s.title === "JOKER");
    if (summary?.sheet_id === undefined || customer?.sheet_id === undefined) {
      setSummaryPreview(null);
      setCustomerPreview(null);
      return;
    }
    setPreviewBusy(true);
    setPreviewError(null);
    try {
      const [sumData, custData] = await Promise.all([
        postJson<SheetPreviewResponse>("/sheets/preview", {
          spreadsheet: spreadsheetInput.trim(),
          sheet_id: summary.sheet_id,
        }),
        postJson<SheetPreviewResponse>("/sheets/preview", {
          spreadsheet: spreadsheetInput.trim(),
          sheet_id: customer.sheet_id,
        }),
      ]);
      setSummaryPreview(sumData);
      setCustomerPreview(custData);
      setSelectedDate(customerDayGroups(custData).find((g) => g.date)?.date ?? "");
      setReadAt(new Date().toISOString());
    } catch (e) {
      setPreviewError(e instanceof Error ? e.message : String(e));
    } finally {
      setPreviewBusy(false);
    }
  }

  async function saveProposal() {
    setActionLoading("proposal");
    setError(null);
    setNotice(null);
    try {
      const query = spreadsheetInput.trim() ? `&spreadsheet=${encodeURIComponent(spreadsheetInput.trim())}` : "";
      const res = await postJson<{ created?: number; updated?: number; unchanged?: number }>(
        `/sheets/mappings/proposal?actor=owner${query}`,
        {},
      );
      setNotice(`Đã lưu đề xuất: tạo ${res.created ?? 0}, cập nhật ${res.updated ?? 0}, giữ ${res.unchanged ?? 0}.`);
      setMappings(await fetchJson<SavedMapping[]>("/sheets/mappings"));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setActionLoading(null);
    }
  }

  async function confirmSheet(sheetName: string) {
    setActionLoading(`confirm-${sheetName}`);
    setError(null);
    setNotice(null);
    try {
      const query = spreadsheetInput.trim() ? `&spreadsheet=${encodeURIComponent(spreadsheetInput.trim())}` : "";
      const res = await postJson<{ confirmed?: number }>(
        `/sheets/mappings/confirm?sheet_name=${encodeURIComponent(sheetName)}&actor=owner${query}`,
        {},
      );
      setNotice(`Đã xác nhận ${res.confirmed ?? 0} cột của sheet "${sheetName}".`);
      setMappings(await fetchJson<SavedMapping[]>("/sheets/mappings"));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setActionLoading(null);
    }
  }

  // Pre-calculations for Zone 1 KPIs
  const customerTabs = useMemo(() => snapshot?.report?.customers ?? [], [snapshot]);

  const customerIssuesCount = useMemo(() => {
    return customerTabs.reduce((acc, c) => acc + (c.issues?.length ?? 0), 0);
  }, [customerTabs]);

  const totalWarnings = useMemo(() => {
    return (snapshot?.report?.issues?.length ?? 0) + customerIssuesCount;
  }, [snapshot, customerIssuesCount]);

  const filteredCustomerTabs = useMemo(() => {
    if (!customerFilter.trim()) return customerTabs;
    const term = customerFilter.toLowerCase().trim();
    return customerTabs.filter(
      (c) =>
        c.source_sheet.toLowerCase().includes(term) ||
        c.display_name?.toLowerCase().includes(term) ||
        String(c.sheet_id).includes(term),
    );
  }, [customerTabs, customerFilter]);

  const visibleHistory = showAllHistory ? history : history.slice(0, HISTORY_PREVIEW_COUNT);

  // Live analyzer variables
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
    <div className="w-full space-y-6 text-white">
      {/* ------------------------------------------------------------- */}
      {/* ZONE 1: TOP ACTION HEADER & ACTIVE SOURCE STATUS STRIP        */}
      {/* ------------------------------------------------------------- */}
      <section className="rounded-[8px] border border-[#282828]/80 bg-[#181818]/95 p-5 sm:p-6 shadow-2xl backdrop-blur-md space-y-5">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-[#282828]/80 pb-5">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <span className="text-3xl"></span>
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white">
                Trung Tâm Quản Lý &amp; Đồng Bộ Google Sheets
              </h1>
            </div>
            <p className="text-xs sm:text-sm text-slate-400">
              Tự động đồng bộ 15 phút một lần từ Google Sheets (chế độ chỉ đọc), đối chiếu hai chiều và hỗ trợ kẻ &amp; ghi ngược báo cáo VIA.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {/* Primary Action 1: Add New Monthly Sheet */}
            <button
              type="button"
              onClick={() => setShowAddSourceForm((v) => !v)}
              className={`rounded-xl px-4 py-2 text-xs sm:text-sm font-semibold transition flex items-center gap-2 shadow-lg ${
                showAddSourceForm
                  ? "bg-slate-800 text-slate-200 border border-[#333333] hover:bg-slate-700"
                  : "bg-[#1ed760] text-black font-bold hover:bg-indigo-500 shadow-indigo-600/20"
              }`}
            >
              <span>{showAddSourceForm ? " Đóng Form Thêm" : " Thêm Sheet Tháng Mới"}</span>
            </button>

            {/* Primary Action 2: Immediate Sync */}
            <button
              type="button"
              disabled={!selected || !selected.active || actionLoading === "sync"}
              onClick={() => void handleSyncNow()}
              className="rounded-xl border border-[#333333] bg-slate-800 px-4 py-2 text-xs sm:text-sm font-semibold text-slate-100 hover:bg-slate-700 transition disabled:opacity-40 flex items-center gap-2"
            >
              <span className={actionLoading === "sync" ? "animate-spin" : ""}></span>
              <span>{actionLoading === "sync" ? "Đang đồng bộ..." : "Cập Nhật / Đồng Bộ Ngay"}</span>
            </button>

            {/* Primary Action 3: Via Sheet Writeback Modal */}
            <button
              type="button"
              onClick={() => setShowWritebackModal(true)}
              className="rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 text-xs sm:text-sm font-semibold transition shadow-lg shadow-emerald-600/20 flex items-center gap-2"
            >
              <span></span>
              <span>Kẻ &amp; Ghi Báo Cáo Từ VIA Lên Sheet</span>
            </button>

            {/* Primary Action 4: Open Original Google Sheet */}
            {selected?.spreadsheet_id && (
              <button
                type="button"
                onClick={() => {
                  const url = selected.spreadsheet_id.startsWith("http")
                    ? selected.spreadsheet_id
                    : `https://docs.google.com/spreadsheets/d/${selected.spreadsheet_id}`;
                  window.open(url, "_blank");
                }}
                className="rounded-xl border border-[#333333] bg-slate-800/80 hover:bg-slate-700 px-3.5 py-2 text-xs sm:text-sm font-medium text-slate-300 transition flex items-center gap-2"
              >
                <span></span>
                <span className="hidden sm:inline">Mở Google Sheet Gốc</span>
              </button>
            )}
          </div>
        </div>

        {/* Quick KPI Strip for Currently Selected Sheet Source */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
          {/* KPI 1: Active Period */}
          <div className="rounded-xl border border-[#282828] bg-slate-900/90 p-4 space-y-1.5">
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              Kỳ Báo Cáo Đang Chọn
            </div>
            <div className="text-base sm:text-lg font-bold text-white truncate">
              {selected ? `${selected.period} · ${selected.name}` : "Chưa chọn nguồn"}
            </div>
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              {selected?.is_default && (
                <span className="rounded-full bg-[#1ed760]/10 border border-[#1ed760]/30 px-2 py-0.5 text-[10px] font-semibold text-[#1ed760]">
                  ⭐ Mặc định
                </span>
              )}
              {selected && (
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                    selected.sync_enabled
                      ? "bg-emerald-500/10 border border-emerald-500/30 text-emerald-400"
                      : "bg-slate-800 border border-[#333333] text-slate-400"
                  }`}
                >
                  {selected.sync_enabled ? " Auto-sync: BẬT" : "Auto-sync: TẮT"}
                </span>
              )}
              {selected?.closure && (
                <span className="rounded-full bg-sky-500/10 border border-sky-500/30 px-2 py-0.5 text-[10px] font-semibold text-sky-400">
                   Đã chốt kỳ
                </span>
              )}
            </div>
          </div>

          {/* KPI 2: Customer Tabs Count */}
          <div className="rounded-xl border border-[#282828] bg-slate-900/90 p-4 space-y-1.5">
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              Số Tab Khách Hàng
            </div>
            <div className="text-2xl font-black text-sky-400 font-mono">
              {customerTabs.length}{" "}
              <span className="text-xs font-normal text-slate-400">tab khách</span>
            </div>
            <div className="text-xs text-slate-500">
              {snapshot?.report ? `${snapshot.report.workbook_tab_count} tab toàn workbook` : "Chưa tải báo cáo"}
            </div>
          </div>

          {/* KPI 3: Latest Snapshot */}
          <div className="rounded-xl border border-[#282828] bg-slate-900/90 p-4 space-y-1.5">
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              Bản Lưu Mới Nhất
            </div>
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold text-slate-100 font-mono">
                #{snapshot?.id ?? selected?.latest_snapshot?.id ?? "—"}
              </span>
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                  (snapshot?.quality ?? selected?.latest_snapshot?.quality) === "READY"
                    ? "bg-emerald-500/10 border border-emerald-500/30 text-emerald-400"
                    : (snapshot?.quality ?? selected?.latest_snapshot?.quality) === "PARTIAL"
                      ? "bg-amber-500/10 border border-amber-500/30 text-amber-400"
                      : "bg-rose-500/10 border border-rose-500/30 text-rose-400"
                }`}
              >
                {snapshot?.quality ?? selected?.latest_snapshot?.quality ?? "CHƯA ĐỌC"}
              </span>
            </div>
            <div className="text-xs text-slate-500 truncate">
              {snapshot?.read_at ? timeText(snapshot.read_at) : "Chưa có bản đọc"}
            </div>
          </div>

          {/* KPI 4: Warnings & Diagnostics (Clickable!) */}
          <button
            type="button"
            onClick={() => setActiveTab("warnings")}
            className="rounded-xl border border-[#282828] bg-slate-900/90 p-4 space-y-1.5 text-left hover:border-amber-500/50 hover:bg-slate-800/60 transition group cursor-pointer"
          >
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between">
              <span>Cảnh Báo Nguồn</span>
              <span className="text-[10px] text-amber-400 group-hover:underline">Chi tiết →</span>
            </div>
            <div
              className={`text-2xl font-black font-mono ${
                totalWarnings === 0
                  ? "text-emerald-400"
                  : totalWarnings > 5
                    ? "text-rose-400"
                    : "text-amber-400"
              }`}
            >
              {totalWarnings}{" "}
              <span className="text-xs font-normal text-slate-400">cảnh báo</span>
            </div>
            <div className="text-xs text-slate-500">
              {totalWarnings === 0 ? "Hoàn hảo · Không lỗi" : "Nhấn để xem chi tiết & phần thiếu"}
            </div>
          </button>
        </div>

        {/* Global Feedback Notifications */}
        {notice && (
          <div className="rounded-xl border border-emerald-800/60 bg-emerald-950/40 p-3.5 text-xs sm:text-sm text-emerald-200 flex items-center justify-between">
            <span> {notice}</span>
            <button type="button" onClick={() => setNotice(null)} className="text-emerald-400 hover:text-white"></button>
          </div>
        )}
        {error && (
          <div className="rounded-xl border border-rose-800/60 bg-rose-950/40 p-3.5 text-xs sm:text-sm text-rose-200 flex items-center justify-between">
            <span> {error}</span>
            <button type="button" onClick={() => setError(null)} className="text-rose-400 hover:text-white"></button>
          </div>
        )}
      </section>

      {/* ------------------------------------------------------------- */}
      {/* 2-COLUMN MAIN WORKSPACE (Zone 2 Left & Zone 3 Right)          */}
      {/* ------------------------------------------------------------- */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* =========================================================== */}
        {/* ZONE 2: LEFT SIDEBAR / SELECTOR (lg:col-span-4)             */}
        {/* =========================================================== */}
        <aside className="lg:col-span-4 space-y-5">
          {/* Collapsible: Add New Monthly Source Form */}
          {showAddSourceForm && (
            <div className="rounded-[8px] border border-indigo-800/80 bg-[#181818]/95 p-5 shadow-2xl backdrop-blur-md space-y-4">
              <div className="flex items-center justify-between border-b border-[#282828] pb-3">
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <span></span> Thêm Báo Cáo Tháng Mới
                </h3>
                <button
                  type="button"
                  onClick={() => setShowAddSourceForm(false)}
                  className="text-xs text-slate-400 hover:text-slate-200"
                >
                  Đóng
                </button>
              </div>

              <form onSubmit={(e) => void handleCreateSource(e)} noValidate className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <label className="text-xs font-medium text-slate-300">
                    Tháng (1..12)
                    <select
                      value={month}
                      onChange={(e) => {
                        setMonth(e.target.value);
                        setConflict(false);
                        setReplace(false);
                      }}
                      className="mt-1 w-full rounded-xl border border-[#333333] bg-[#1f1f1f] px-3 py-2 text-xs text-slate-100 focus:border-[#1ed760] focus:outline-none"
                    >
                      <option value="">Chọn…</option>
                      {Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, "0")).map((m) => (
                        <option key={m} value={m}>
                          Tháng {m}
                        </option>
                      ))}
                    </select>
                    {formErrors.month && <span className="text-[11px] text-rose-400">{formErrors.month}</span>}
                  </label>

                  <label className="text-xs font-medium text-slate-300">
                    Năm (2026)
                    <input
                      inputMode="numeric"
                      maxLength={4}
                      value={year}
                      onChange={(e) => {
                        setYear(e.target.value.replace(/\D/g, ""));
                        setConflict(false);
                        setReplace(false);
                      }}
                      className="mt-1 w-full rounded-xl border border-[#333333] bg-[#1f1f1f] px-3 py-2 text-xs text-slate-100 focus:border-[#1ed760] focus:outline-none"
                    />
                    {formErrors.year && <span className="text-[11px] text-rose-400">{formErrors.year}</span>}
                  </label>
                </div>

                <label className="block text-xs font-medium text-slate-300">
                  Link Google Sheets (URL hoặc ID)
                  <input
                    value={workbook}
                    onChange={(e) => setWorkbook(e.target.value)}
                    placeholder="https://docs.google.com/spreadsheets/d/… hoặc ID"
                    className="mt-1 w-full rounded-xl border border-[#333333] bg-[#1f1f1f] px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:border-[#1ed760] focus:outline-none"
                  />
                  {formErrors.workbook && <span className="text-[11px] text-rose-400">{formErrors.workbook}</span>}
                </label>

                <label className="block text-xs font-medium text-slate-300">
                  Tên báo cáo
                  <input
                    value={shownName}
                    onChange={(e) => {
                      setName(e.target.value);
                      setNameEdited(true);
                    }}
                    placeholder="Báo cáo tháng 10/2026"
                    className="mt-1 w-full rounded-xl border border-[#333333] bg-[#1f1f1f] px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:border-[#1ed760] focus:outline-none"
                  />
                  {formErrors.name && <span className="text-[11px] text-rose-400">{formErrors.name}</span>}
                </label>

                <div className="space-y-2 pt-1 text-xs text-slate-300">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={autoSync}
                      onChange={(e) => setAutoSync(e.target.checked)}
                      className="accent-indigo-500 rounded"
                    />
                    Tự đồng bộ mỗi 15 phút
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={makeDefault}
                      onChange={(e) => setMakeDefault(e.target.checked)}
                      className="accent-indigo-500 rounded"
                    />
                    Đặt làm nguồn mặc định
                  </label>
                  {conflict && (
                    <label className="flex items-center gap-2 font-medium text-amber-400 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={replace}
                        onChange={(e) => setReplace(e.target.checked)}
                        className="accent-amber-500 rounded"
                      />
                      Xác nhận thay thế nguồn đang dùng của kỳ {periodValue}
                    </label>
                  )}
                </div>

                {formErrors.form && (
                  <div className="rounded-xl border border-rose-800 bg-rose-950/40 p-2.5 text-xs text-rose-300">
                    {formErrors.form}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={savingSource}
                  className="w-full rounded-xl bg-indigo-600 hover:bg-indigo-500 px-4 py-2.5 text-xs font-semibold text-white transition shadow-lg shadow-indigo-600/20 disabled:opacity-50"
                >
                  {savingSource ? "Đang kiểm tra và đọc Sheets…" : " Kiểm Tra & Lưu Báo Cáo"}
                </button>
              </form>
            </div>
          )}

          {/* Obsidian Source Cards Selector */}
          <div
            id="saved-sources"
            className="rounded-[8px] border border-[#282828]/80 bg-[#181818]/95 p-5 shadow-xl backdrop-blur-md space-y-4"
          >
            <div className="flex items-center justify-between border-b border-[#282828] pb-3">
              <div>
                <h2 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                  <span></span> Nguồn Đã Lưu ({sources.length})
                </h2>
                <p className="text-[11px] text-slate-400">Chọn nguồn để xem preview &amp; đối soát</p>
              </div>

              {/* Quick Dropdown */}
              <select
                value={selectedId}
                onChange={(e) => setSelectedId(e.target.value)}
                className="rounded-xl border border-[#333333] bg-[#1f1f1f] px-2.5 py-1 text-xs text-slate-100 focus:border-[#1ed760] focus:outline-none"
                aria-label="Chọn nguồn báo cáo"
              >
                {sources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.period} · {s.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Source Cards List */}
            <div className="space-y-3 max-h-[620px] overflow-y-auto pr-1">
              {sources.map((source) => {
                const isCurrent = String(source.id) === selectedId;
                return (
                  <div
                    key={source.id}
                    onClick={() => setSelectedId(String(source.id))}
                    className={`rounded-xl border p-4 transition-all duration-200 cursor-pointer space-y-3 ${
                      isCurrent
                        ? "border-[#1ed760] bg-indigo-950/20 ring-1 ring-indigo-500/40 shadow-lg shadow-indigo-500/10"
                        : "border-[#282828]/80 bg-slate-900/60 hover:border-[#333333] hover:bg-slate-800/40"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-sm font-bold text-white">{source.period}</span>
                          {source.is_default && (
                            <span className="rounded-full bg-[#1ed760]/10 border border-[#1ed760]/30 px-2 py-0.2 text-[10px] font-semibold text-[#1ed760]">
                              ⭐ Mặc định
                            </span>
                          )}
                          {!source.active && (
                            <span className="rounded-full bg-slate-800 border border-[#333333] px-2 py-0.2 text-[10px] font-semibold text-slate-400">
                              Đã thay thế
                            </span>
                          )}
                        </div>
                        <div className="text-xs font-medium text-slate-200 mt-0.5">{source.name}</div>
                      </div>

                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                          source.last_attempt?.status === "SUCCESS"
                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                            : source.last_attempt?.status === "PARTIAL"
                              ? "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                              : source.last_attempt?.status === "ERROR"
                                ? "bg-rose-500/10 text-rose-400 border border-rose-500/30"
                                : "bg-slate-800 text-slate-400 border border-[#333333]"
                        }`}
                      >
                        {source.last_attempt?.status ?? "CHƯA ĐỌC"}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                      <span>Mapping v{source.mapping_version}</span>
                      <span>·</span>
                      <span className={source.sync_enabled ? "text-emerald-400" : "text-slate-500"}>
                        {source.sync_enabled ? " Tự đồng bộ 15p" : "Tự đồng bộ TẮT"}
                      </span>
                      {source.closure && (
                        <>
                          <span>·</span>
                          <span className="text-sky-400"> Đã chốt</span>
                        </>
                      )}
                    </div>

                    {/* 1-Click Action Buttons Right on Card */}
                    <div
                      className="flex flex-wrap gap-1.5 pt-1 border-t border-[#282828]/60"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button
                        type="button"
                        disabled={actionLoading === "sync" || !source.active}
                        onClick={() => void handleSyncNow()}
                        className="rounded-lg bg-indigo-600/80 hover:bg-indigo-600 px-2.5 py-1 text-[11px] font-medium text-white transition disabled:opacity-40"
                      >
                         Cập nhật ngay
                      </button>

                      <button
                        type="button"
                        disabled={source.is_default || !source.active || actionLoading === `default-${source.id}`}
                        onClick={() => void handleSetDefault(source)}
                        className="rounded-lg border border-[#333333] bg-slate-800 hover:bg-slate-700 px-2 py-1 text-[11px] font-medium text-slate-300 transition disabled:opacity-40"
                      >
                        ⭐ Đặt mặc định
                      </button>

                      <button
                        type="button"
                        disabled={!source.active || actionLoading === `sync-toggle-${source.id}`}
                        onClick={() => void handleToggleAutoSync(source)}
                        className="rounded-lg border border-[#333333] bg-slate-800 hover:bg-slate-700 px-2 py-1 text-[11px] font-medium text-slate-300 transition disabled:opacity-40"
                      >
                        {source.sync_enabled ? "Tắt sync" : "Bật sync 15p"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </aside>

        {/* =========================================================== */}
        {/* ZONE 3: MAIN ORGANIZED TABBED WORKSPACE (lg:col-span-8)    */}
        {/* =========================================================== */}
        <section className="lg:col-span-8 space-y-5">
          {/* Lucian-UXUI 039 Sliding Pill Navigation Tabs */}
          <div className="flex flex-wrap items-center gap-1.5 p-1.5 rounded-[8px] border border-[#282828]/80 bg-[#181818]/95 shadow-lg backdrop-blur-md">
            <button
              type="button"
              onClick={() => setActiveTab("tabs")}
              className={`rounded-xl px-4 py-2.5 text-xs sm:text-sm font-semibold transition-all duration-200 flex items-center gap-2 ${
                activeTab === "tabs"
                  ? "bg-[#1ed760] text-black font-bold shadow-lg shadow-indigo-600/30 font-bold"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
              }`}
            >
              <span></span>
              <span>Dữ Liệu Tab Khách &amp; Phân Tích Cấu Trúc</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("warnings")}
              className={`rounded-xl px-4 py-2.5 text-xs sm:text-sm font-semibold transition-all duration-200 flex items-center gap-2 ${
                activeTab === "warnings"
                  ? "bg-[#1ed760] text-black font-bold shadow-lg shadow-indigo-600/30 font-bold"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
              }`}
            >
              <span></span>
              <span>Cảnh Báo &amp; Phần Thiếu</span>
              {totalWarnings > 0 && (
                <span className="rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 px-2 py-0.2 text-[10px] font-bold">
                  {totalWarnings}
                </span>
              )}
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("snapshots")}
              className={`rounded-xl px-4 py-2.5 text-xs sm:text-sm font-semibold transition-all duration-200 flex items-center gap-2 ${
                activeTab === "snapshots"
                  ? "bg-[#1ed760] text-black font-bold shadow-lg shadow-indigo-600/30 font-bold"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
              }`}
            >
              <span></span>
              <span>Bản Lưu &amp; Chốt Kỳ</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("history")}
              className={`rounded-xl px-4 py-2.5 text-xs sm:text-sm font-semibold transition-all duration-200 flex items-center gap-2 ${
                activeTab === "history"
                  ? "bg-[#1ed760] text-black font-bold shadow-lg shadow-indigo-600/30 font-bold"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
              }`}
            >
              <span></span>
              <span>Lịch Sử Đồng Bộ</span>
            </button>
          </div>

          {/* --------------------------------------------------------- */}
          {/* TAB 1: DỮ LIỆU TAB KHÁCH & PHÂN TÍCH CẤU TRÚC             */}
          {/* --------------------------------------------------------- */}
          {activeTab === "tabs" && (
            <div className="space-y-5">
              {/* Sub-view switcher */}
              <div className="flex flex-wrap items-center gap-2 border-b border-[#282828] pb-3">
                <button
                  type="button"
                  onClick={() => setSubTab("overview")}
                  className={`rounded-xl px-3.5 py-1.5 text-xs font-semibold transition ${
                    subTab === "overview"
                      ? "bg-slate-800 text-white border border-[#333333] shadow"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
                  }`}
                >
                  Danh Sách Tab Khách ({customerTabs.length})
                </button>
                <button
                  type="button"
                  onClick={() => setSubTab("analyzer")}
                  className={`rounded-xl px-3.5 py-1.5 text-xs font-semibold transition ${
                    subTab === "analyzer"
                      ? "bg-slate-800 text-white border border-[#333333] shadow"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
                  }`}
                >
                  Phân Tích Cấu Trúc Trực Tiếp
                </button>
                <button
                  type="button"
                  onClick={() => setSubTab("setup")}
                  className={`rounded-xl px-3.5 py-1.5 text-xs font-semibold transition ${
                    subTab === "setup"
                      ? "bg-slate-800 text-white border border-[#333333] shadow"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
                  }`}
                >
                  Thiết Lập Khách Hàng (Customer Setup)
                </button>
                <button
                  type="button"
                  onClick={() => setSubTab("review")}
                  className={`rounded-xl px-3.5 py-1.5 text-xs font-semibold transition ${
                    subTab === "review"
                      ? "bg-slate-800 text-white border border-[#333333] shadow"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
                  }`}
                >
                  Rà Soát Liên Kết Đa Kỳ
                </button>
              </div>

              {/* Sub-view 1: Overview Customer Tabs */}
              {subTab === "overview" && (
                <div className="rounded-[8px] border border-[#282828]/80 bg-[#181818]/95 p-5 shadow-xl backdrop-blur-md space-y-4">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div>
                      <h3 className="text-base font-bold text-white flex items-center gap-2">
                        <span></span> Tab Khách Hàng Trong Nguồn Hiện Tại
                      </h3>
                      <p className="text-xs text-slate-400">
                        {customerTabs.length} tab khách được diễn giải từ snapshot #{snapshot?.id ?? "—"}
                      </p>
                    </div>

                    {/* Search / Filter input */}
                    <div className="w-full sm:w-64">
                      <input
                        type="text"
                        value={customerFilter}
                        onChange={(e) => setCustomerFilter(e.target.value)}
                        placeholder=" Tìm tên tab khách hàng..."
                        className="w-full rounded-xl border border-[#333333] bg-[#1f1f1f] px-3 py-1.5 text-xs text-slate-100 placeholder-slate-400 focus:border-[#1ed760] focus:outline-none"
                      />
                    </div>
                  </div>

                  {filteredCustomerTabs.length === 0 ? (
                    <div className="rounded-xl border border-[#282828] bg-slate-900/60 p-6 text-center text-xs text-slate-400">
                      {customerFilter ? "Không tìm thấy tab khách khớp từ khóa." : "Chưa có tab khách nào trong snapshot."}
                    </div>
                  ) : (
                    <div className="overflow-x-auto rounded-xl border border-[#282828] bg-slate-900/60">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-slate-900 text-slate-400 uppercase font-semibold">
                          <tr>
                            <th className="p-3">Tab Khách / Sheet</th>
                            <th className="p-3">Hồ Sơ Nội Bộ</th>
                            <th className="p-3">Số Dư Đầu Kỳ</th>
                            <th className="p-3">Nạp USDT</th>
                            <th className="p-3">Chi Tiêu Meta</th>
                            <th className="p-3">Phí Dịch Vụ</th>
                            <th className="p-3">Số Dư Cuối Kỳ</th>
                            <th className="p-3">Trạng Thái</th>
                            <th className="p-3 text-center">Hành Động</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/80">
                          {filteredCustomerTabs.map((c) => {
                            const linkedCust = links.find((l) => l.sheet_id === c.sheet_id);
                            const customerName = linkedCust
                              ? customers.find((x) => x.id === linkedCust.customer_id)?.name ?? `#${linkedCust.customer_id}`
                              : null;

                            // Calculate spend
                            const totalSpendVnd = (c.daily ?? []).reduce(
                              (sum, d) => sum + (d.spend_vnd ? Number(d.spend_vnd) : 0),
                              0,
                            );

                            return (
                              <tr key={c.source_sheet} className="hover:bg-slate-800/40 transition-colors">
                                <td className="p-3">
                                  <div className="font-semibold text-slate-100">{c.source_sheet}</div>
                                  <div className="text-[10px] text-slate-500 font-mono">
                                    sheetId: {c.sheet_id ?? "—"}
                                  </div>
                                </td>

                                <td className="p-3">
                                  {customerName ? (
                                    <span className="font-medium text-emerald-400">{customerName}</span>
                                  ) : (
                                    <span className="text-slate-500 italic">Chưa liên kết</span>
                                  )}
                                </td>

                                <td className="p-3 font-mono text-slate-300">
                                  {c.opening_balance?.formatted_value ??
                                    (c.opening_balance?.value ? `${formatVnd(c.opening_balance.value)} đ` : "—")}
                                </td>

                                <td className="p-3">
                                  {c.usdt_receipts_state === "HAS_RECORDS" ? (
                                    <span className="rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 px-1.5 py-0.5 text-[10px] font-semibold">
                                      Có nạp USDT
                                    </span>
                                  ) : (
                                    <span className="text-slate-500">—</span>
                                  )}
                                </td>

                                <td className="p-3 font-mono text-slate-200">
                                  {totalSpendVnd > 0 ? `${formatVnd(totalSpendVnd)} đ` : "—"}
                                </td>

                                <td className="p-3 font-mono text-slate-400">
                                  {c.tab_source_totals?.fee?.formatted_value ?? "—"}
                                </td>

                                <td className="p-3 font-mono font-semibold text-white">
                                  {c.linked_summary_rows?.[0]?.closing_balance_value != null
                                    ? `${formatVnd(c.linked_summary_rows[0].closing_balance_value)} đ`
                                    : "—"}
                                </td>

                                <td className="p-3">
                                  <div className="flex flex-wrap gap-1 items-center">
                                    <span
                                      className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                                        c.profile_status === "VALID"
                                          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                                          : "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                                      }`}
                                    >
                                      {c.completeness_status ?? c.profile_status}
                                    </span>
                                    {c.issues && c.issues.length > 0 && (
                                      <span className="rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/30 px-1.5 py-0.5 text-[10px] font-semibold">
                                        {c.issues.length} cảnh báo
                                      </span>
                                    )}
                                  </div>
                                </td>

                                <td className="p-3 text-center">
                                  <button
                                    type="button"
                                    onClick={() => setInspectedCustomer(c)}
                                    className="rounded-lg border border-[#333333] bg-slate-800 hover:bg-slate-700 px-2.5 py-1 text-[11px] font-medium text-[#1ed760] transition"
                                  >
                                    Chi tiết tab
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* Sub-view 2: Live Analyzer & Structure Proposals */}
              {subTab === "analyzer" && (
                <div className="rounded-[8px] border border-[#282828]/80 bg-[#181818]/95 p-5 shadow-xl backdrop-blur-md space-y-5">
                  <div>
                    <h3 className="text-base font-bold text-white flex items-center gap-2">
                      <span></span> Đọc &amp; Phân Tích Cấu Trúc Trực Tiếp
                    </h3>
                    <p className="text-xs text-slate-400">
                      Đọc trực tiếp cấu trúc các cột, ô dữ liệu và đề xuất mapping từ bất kỳ Google Sheets URL hoặc ID nào.
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      className="grow rounded-xl border border-[#333333] bg-[#1f1f1f] px-3.5 py-2 text-xs text-slate-100 placeholder-slate-400 focus:border-[#1ed760] focus:outline-none"
                      placeholder="https://docs.google.com/spreadsheets/d/… hoặc ID"
                      value={spreadsheetInput}
                      onChange={(e) => setSpreadsheetInput(e.target.value)}
                    />
                    {selected?.spreadsheet_id && (
                      <button
                        type="button"
                        onClick={() => setSpreadsheetInput(selected.spreadsheet_id)}
                        className="rounded-xl border border-[#333333] bg-slate-800 px-3 py-2 text-xs font-medium text-slate-300 hover:bg-slate-700"
                      >
                        Lấy ID nguồn đang chọn
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={analyzeBusy || previewBusy || !spreadsheetInput.trim()}
                      onClick={() => void runAnalyze()}
                      className="rounded-xl bg-indigo-600 hover:bg-indigo-500 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-indigo-600/20 disabled:opacity-50"
                    >
                      {analyzeBusy || previewBusy ? "Đang đọc Sheets…" : "Đọc báo cáo preview"}
                    </button>
                  </div>

                  {restoredAt && (
                    <p className="text-xs text-slate-400">
                      Đã khôi phục kết quả phân tích trong phiên này (lúc {new Date(restoredAt).toLocaleTimeString("vi-VN")}).
                    </p>
                  )}

                  {/* Summary Joker Preview */}
                  {summaryPreview && (
                    <div className="space-y-3 pt-3 border-t border-[#282828]">
                      <h4 className="font-bold text-xs uppercase tracking-wider text-slate-300">
                        Tab Tổng Hợp — {summaryPreview.source.title}
                      </h4>
                      {summaryJokerRow ? (
                        <div className="overflow-x-auto rounded-xl border border-[#282828] bg-slate-900/60">
                          <table className="min-w-[760px] w-full text-left text-xs">
                            <thead className="bg-slate-900 text-slate-400 uppercase font-semibold">
                              <tr>
                                {summaryColumns.map((col) => (
                                  <th key={col} className="p-3">
                                    {summaryHeaderCells[col]?.value ?? `Cột ${col}`}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              <tr>
                                {summaryColumns.map((col) => (
                                  <td key={col} className="border-t border-[#282828]/80 p-3 align-top">
                                    {col === "C" && jokerOpeningBalanceCell && (
                                      <span className="mb-1 block text-[10px] font-semibold text-sky-400">
                                        Ngân sách từ kỳ trước (VND)
                                      </span>
                                    )}
                                    <SheetValue cell={summaryJokerCells[col]} cells={summaryJokerCells} />
                                  </td>
                                ))}
                              </tr>
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className="text-xs text-slate-400">Không tìm thấy dòng khách JOKER trong tab tổng hợp.</p>
                      )}
                    </div>
                  )}

                  {/* Customer Preview with Date Groups */}
                  {customerPreview && (
                    <div className="space-y-3 pt-3 border-t border-[#282828]">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h4 className="font-bold text-xs uppercase tracking-wider text-slate-300">
                          Chi Tiết Khách — {customerPreview.source.title}
                        </h4>
                        <label className="flex items-center gap-2 text-xs text-slate-400">
                          Ngày dữ liệu:
                          <select
                            value={selectedDate}
                            onChange={(e) => setSelectedDate(e.target.value)}
                            className="rounded-xl border border-[#333333] bg-[#1f1f1f] px-2.5 py-1 text-xs text-slate-100"
                          >
                            <option value="">Tất cả ngày đọc được</option>
                            {availableDates.map((d) => (
                              <option key={d} value={d}>
                                {d}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>

                      {visibleDayGroups.length === 0 ? (
                        <p className="text-xs text-slate-400">Chưa có dòng chi tiết với ô ngày hợp lệ.</p>
                      ) : (
                        <div className="space-y-4">
                          {visibleDayGroups.map((group) => (
                            <div
                              key={`${group.date}-${group.startRow}`}
                              className="rounded-xl border border-[#282828] bg-slate-900/50 overflow-hidden"
                            >
                              <div className="flex items-center justify-between bg-slate-900 px-4 py-2.5 border-b border-[#282828]">
                                <span className="font-bold text-xs text-white">
                                  {group.date} · phạm vi {group.dateRange}
                                </span>
                                <span className="text-[11px] text-slate-400 font-mono">
                                  {group.accounts.length} dòng TKQC
                                </span>
                              </div>
                              <div className="overflow-x-auto">
                                <table className="min-w-[900px] w-full text-left text-xs">
                                  <thead className="bg-slate-900/60 text-slate-400 text-[11px]">
                                    <tr>
                                      <th className="p-2.5">Tiền tệ (B)</th>
                                      <th className="p-2.5">ID TKQC (C)</th>
                                      <th className="p-2.5">Chi tiêu gốc (E/F)</th>
                                      <th className="p-2.5">Tỷ giá (I)</th>
                                      <th className="p-2.5">Chi tiêu VND (F)</th>
                                      <th className="p-2.5">Phí (G)</th>
                                      <th className="p-2.5">Tổng gồm phí (H)</th>
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-slate-800/60">
                                    {group.accounts.map((acc) => (
                                      <tr key={acc.rowNumber} className="hover:bg-slate-800/30">
                                        <td className="p-2.5">
                                          <SheetValue cell={acc.cells.B} cells={acc.cells} />
                                        </td>
                                        <td className="p-2.5 font-mono">
                                          <SheetValue cell={acc.cells.C} cells={acc.cells} />
                                        </td>
                                        <td className="p-2.5">
                                          <SheetValue cell={acc.cells.E ?? acc.cells.F} cells={acc.cells} />
                                        </td>
                                        <td className="p-2.5">
                                          <SheetValue cell={acc.cells.I} cells={acc.cells} />
                                        </td>
                                        <td className="p-2.5">
                                          <SheetValue cell={acc.cells.F} cells={acc.cells} />
                                        </td>
                                        <td className="p-2.5">
                                          <SheetValue cell={acc.cells.G} cells={acc.cells} />
                                        </td>
                                        <td className="p-2.5">
                                          <SheetValue cell={acc.cells.H} cells={acc.cells} />
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Structural Column Proposals & Mappings */}
                  {result?.structure?.sheets?.map((sheet) => (
                    <div key={sheet.title} className="space-y-3 pt-3 border-t border-[#282828]">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="text-xs font-bold text-white">
                          Sheet &ldquo;{sheet.title}&rdquo; — {sheet.row_count} dòng · header ở dòng{" "}
                          {(sheet.header_row_index ?? -1) + 1}
                        </div>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            disabled={actionLoading === "proposal"}
                            onClick={() => void saveProposal()}
                            className="rounded-xl border border-[#333333] bg-slate-800 hover:bg-slate-700 px-3 py-1.5 text-xs font-medium text-slate-200"
                          >
                            Lưu đề xuất mapping
                          </button>
                          <button
                            type="button"
                            disabled={actionLoading === `confirm-${sheet.title}`}
                            onClick={() => void confirmSheet(sheet.title)}
                            className="rounded-xl bg-indigo-600 hover:bg-indigo-500 px-3 py-1.5 text-xs font-semibold text-white"
                          >
                            Xác nhận mapping sheet này
                          </button>
                        </div>
                      </div>

                      <div className="overflow-x-auto rounded-xl border border-[#282828] bg-slate-900/60">
                        <table className="w-full text-left text-xs">
                          <thead className="bg-slate-900 text-slate-400 uppercase font-semibold">
                            <tr>
                              <th className="p-2.5">Cột</th>
                              <th className="p-2.5">Header</th>
                              <th className="p-2.5">Đề xuất vai trò</th>
                              <th className="p-2.5">Đích dự kiến</th>
                              <th className="p-2.5">Định dạng</th>
                              <th className="p-2.5">Trạng thái</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/80">
                            {sheet.columns.map((col) => {
                              const proposal = result.proposals.find(
                                (p) => p.sheet_name === sheet.title && p.column_letter === col.column_letter,
                              );
                              return (
                                <tr key={col.column_letter} className="hover:bg-slate-800/40">
                                  <td className="p-2.5 font-bold font-mono text-white">{col.column_letter}</td>
                                  <td className="p-2.5 text-slate-200">{col.header}</td>
                                  <td className="p-2.5 font-medium text-[#1ed760]">{proposal?.role ?? "—"}</td>
                                  <td className="p-2.5 text-slate-400">
                                    {proposal?.target ? `${proposal.target.area} · ${proposal.target.field}` : "—"}
                                  </td>
                                  <td className="p-2.5 font-mono text-slate-400">
                                    {col.number_format?.type ?? "heuristic"}
                                  </td>
                                  <td className="p-2.5">
                                    <span
                                      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                                        col.needs_confirmation
                                          ? "bg-rose-500/10 text-rose-400 border border-rose-500/30"
                                          : proposal?.role
                                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                                            : "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                                      }`}
                                    >
                                      {col.needs_confirmation
                                        ? "NEEDS_CONFIRMATION"
                                        : proposal?.role
                                          ? "Nhận diện chắc"
                                          : "Chờ xác nhận"}
                                    </span>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ))}

                  {/* Saved mappings */}
                  {mappings.length > 0 && (
                    <div className="space-y-3 pt-3 border-t border-[#282828]">
                      <h4 className="font-bold text-xs uppercase tracking-wider text-slate-300">
                        Mapping Đã Lưu ({mappings.length})
                      </h4>
                      <div className="overflow-x-auto rounded-xl border border-[#282828] bg-slate-900/60 max-h-60 overflow-y-auto">
                        <table className="w-full text-left text-xs">
                          <thead className="bg-slate-900 text-slate-400 uppercase font-semibold">
                            <tr>
                              <th className="p-2.5">Sheet</th>
                              <th className="p-2.5">Cột</th>
                              <th className="p-2.5">Header</th>
                              <th className="p-2.5">Vai trò</th>
                              <th className="p-2.5">Trạng thái</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/80">
                            {mappings.map((m) => (
                              <tr key={m.id} className="hover:bg-slate-800/40">
                                <td className="p-2.5 font-medium text-white">{m.sheet_name}</td>
                                <td className="p-2.5 font-mono text-[#1ed760]">{m.column_letter}</td>
                                <td className="p-2.5 text-slate-300">{m.header}</td>
                                <td className="p-2.5 text-slate-300">{m.role ?? "—"}</td>
                                <td className="p-2.5">
                                  <span
                                    className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                                      m.status === "CONFIRMED"
                                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                                        : "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                                    }`}
                                  >
                                    {m.status}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Sub-view 3: Customer Setup */}
              {subTab === "setup" && (
                <CustomerSetup activeSourceId={selected ? selected.id : null} />
              )}

              {/* Sub-view 4: Link Review */}
              {subTab === "review" && <LinkReview />}
            </div>
          )}

          {/* --------------------------------------------------------- */}
          {/* TAB 2: CẢNH BÁO & PHẦN THIẾU (WARNINGS & DIAGNOSTICS)      */}
          {/* --------------------------------------------------------- */}
          {activeTab === "warnings" && (
            <div className="rounded-[8px] border border-[#282828]/80 bg-[#181818]/95 p-5 sm:p-6 shadow-xl backdrop-blur-md space-y-6">
              <div className="border-b border-[#282828] pb-3">
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <span></span> Trung Tâm Cảnh Báo &amp; Phần Thiếu Dữ Liệu
                </h3>
                <p className="text-xs text-slate-400">
                  Tổng hợp toàn bộ cảnh báo chất lượng từ workbook, tab khách chưa hoàn chỉnh hoặc công thức thiếu đầu vào.
                </p>
              </div>

              {totalWarnings === 0 ? (
                <div className="rounded-xl border border-emerald-800/60 bg-emerald-950/30 p-8 text-center space-y-2">
                  <div className="text-3xl"></div>
                  <div className="text-base font-bold text-emerald-300">
                    Tuyệt vời! Không phát hiện bất kỳ cảnh báo nào.
                  </div>
                  <p className="text-xs text-slate-400 max-w-md mx-auto">
                    Toàn bộ cấu trúc workbook, các tab khách và các công thức chi tiêu/ngân sách đều đầy đủ và hợp lệ.
                  </p>
                </div>
              ) : (
                <div className="space-y-5">
                  {/* Global issues from snapshot */}
                  {snapshot?.report?.issues && snapshot.report.issues.length > 0 && (
                    <div className="space-y-3">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-amber-400">
                        Cảnh Báo Từ Nguồn Google Sheets ({snapshot.report.issues.length})
                      </h4>
                      <div className="space-y-2">
                        {snapshot.report.issues.map((issue, idx) => (
                          <div
                            key={idx}
                            className="rounded-xl border border-amber-800/50 bg-amber-950/20 p-4 space-y-1 text-xs"
                          >
                            <div className="flex items-center gap-2 font-semibold text-amber-300">
                              <span className="rounded bg-amber-500/20 border border-amber-500/40 px-1.5 py-0.2 text-[10px]">
                                {issue.severity ?? "WARNING"}
                              </span>
                              <span>{issue.source}</span>
                            </div>
                            <p className="text-slate-300 leading-relaxed">{issue.message}</p>
                            {issue.references && issue.references.length > 0 && (
                              <div className="text-[11px] text-slate-400 pt-1 font-mono">
                                Tham chiếu ô: {issue.references.join(", ")}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Customer tabs with issues or incomplete profile */}
                  {customerTabs.filter(
                    (c) =>
                      (c.issues && c.issues.length > 0) ||
                      c.completeness_status === "NEEDS_REVIEW" ||
                      c.profile_status === "SOURCE_ERROR" ||
                      c.profile_status === "STRUCTURE_ERROR",
                  ).length > 0 && (
                    <div className="space-y-3 pt-3 border-t border-[#282828]">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-rose-400">
                        Tab Khách Hàng Cần Rà Soát (
                        {
                          customerTabs.filter(
                            (c) =>
                              (c.issues && c.issues.length > 0) ||
                              c.completeness_status === "NEEDS_REVIEW" ||
                              c.profile_status === "SOURCE_ERROR" ||
                              c.profile_status === "STRUCTURE_ERROR",
                          ).length
                        }
                        )
                      </h4>
                      <div className="space-y-2">
                        {customerTabs
                          .filter(
                            (c) =>
                              (c.issues && c.issues.length > 0) ||
                              c.completeness_status === "NEEDS_REVIEW" ||
                              c.profile_status === "SOURCE_ERROR" ||
                              c.profile_status === "STRUCTURE_ERROR",
                          )
                          .map((c) => (
                            <div
                              key={c.source_sheet}
                              className="rounded-xl border border-rose-800/50 bg-rose-950/20 p-4 space-y-2 text-xs"
                            >
                              <div className="flex items-center justify-between">
                                <span className="font-bold text-white text-sm">
                                  Tab: {c.source_sheet} (ID: {c.sheet_id ?? "—"})
                                </span>
                                <span className="rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/40 px-2 py-0.5 text-[10px] font-bold">
                                  {c.profile_status} · {c.completeness_status ?? "chưa hoàn chỉnh"}
                                </span>
                              </div>
                              {c.issues && c.issues.length > 0 && (
                                <ul className="space-y-1 list-disc list-inside text-rose-200 pl-1">
                                  {c.issues.map((iss, i) => (
                                    <li key={i}>
                                      <strong className="text-white">{iss.source}:</strong> {iss.message}
                                    </li>
                                  ))}
                                </ul>
                              )}
                              <div className="pt-1 flex gap-2">
                                <button
                                  type="button"
                                  onClick={() => {
                                    setActiveTab("tabs");
                                    setSubTab("setup");
                                  }}
                                  className="rounded-lg border border-[#333333] bg-slate-800 hover:bg-slate-700 px-2.5 py-1 text-[11px] font-medium text-slate-300"
                                >
                                  Đi tới thiết lập hồ sơ tab này →
                                </button>
                              </div>
                            </div>
                          ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* --------------------------------------------------------- */}
          {/* TAB 3: BẢN LƯU VÀ CHỐT KỲ (SNAPSHOTS & FINALIZE)           */}
          {/* --------------------------------------------------------- */}
          {activeTab === "snapshots" && (
            <div className="rounded-[8px] border border-[#282828]/80 bg-[#181818]/95 p-5 sm:p-6 shadow-xl backdrop-blur-md space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#282828] pb-4">
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    <span></span> Bản Lưu Snapshot &amp; Chốt Kỳ Báo Cáo
                  </h3>
                  <p className="text-xs text-slate-400">
                    Chọn bản snapshot đã đọc để khóa số liệu kỳ. Các lần sync tự động sau sẽ không ghi đè lên bản chốt.
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <label className="text-xs font-medium text-slate-300">Chọn bản lưu:</label>
                  <select
                    value={snapshotId}
                    onChange={(e) => {
                      setSnapshotId(e.target.value);
                      setAcknowledge(false);
                    }}
                    className="rounded-xl border border-[#333333] bg-[#1f1f1f] px-3 py-1.5 text-xs text-slate-100 focus:border-[#1ed760] focus:outline-none"
                  >
                    {snapshots.map((item) => (
                      <option value={item.id} key={item.id}>
                        #{item.id} · {timeText(item.read_at)} · {item.quality}
                        {selected?.closure?.snapshot_id === item.id ? " · BẢN CHỐT" : ""}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {snapshot && (
                <div className="rounded-xl border border-[#282828] bg-slate-900/90 p-5 space-y-4 text-xs">
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#282828]/80 pb-3">
                    <div className="space-y-1">
                      <div className="text-sm font-bold text-white flex items-center gap-2">
                        <span>Bản Snapshot #{snapshot.id}</span>
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                            snapshot.quality === "READY"
                              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                              : "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                          }`}
                        >
                          {snapshot.quality}
                        </span>
                      </div>
                      <div className="text-slate-400">
                        Đọc lúc: {timeText(snapshot.read_at)} · Mapping version: {snapshot.mapping_version}
                      </div>
                    </div>

                    {selected?.closure ? (
                      <span className="rounded-full bg-emerald-500/10 border border-emerald-500/30 px-3 py-1 text-xs font-bold text-emerald-400">
                         KỲ ĐÃ CHỐT VỚI BẢN #{selected.closure.snapshot_id}
                      </span>
                    ) : (
                      <span className="rounded-full bg-slate-800 border border-[#333333] px-3 py-1 text-xs font-medium text-slate-400">
                         KỲ CHƯA ĐƯỢC CHỐT
                      </span>
                    )}
                  </div>

                  <p className="text-slate-300 leading-relaxed">
                    Bản lưu này chứa <strong>{(snapshot.report?.customers ?? []).length} tab khách</strong> và{" "}
                    <strong>{snapshot.report?.issues.length ?? 0} cảnh báo nguồn</strong>. Vui lòng kiểm tra kỹ số dư và
                    chi tiêu trước khi thực hiện chốt kỳ.
                  </p>

                  {!selected?.closure && (
                    <div className="space-y-3 pt-2">
                      {snapshot.quality !== "READY" && (
                        <label className="flex items-center gap-2.5 font-medium text-amber-300 cursor-pointer bg-amber-950/20 border border-amber-800/40 p-3 rounded-xl">
                          <input
                            type="checkbox"
                            checked={acknowledge}
                            onChange={(e) => setAcknowledge(e.target.checked)}
                            className="accent-amber-500 rounded h-4 w-4"
                          />
                          <span>
                            Tôi đã xem và chấp nhận bản còn thiếu (PARTIAL) khi chốt kỳ {selected?.period}
                          </span>
                        </label>
                      )}

                      <button
                        type="button"
                        disabled={
                          actionLoading === "closure" ||
                          !!selected?.closure ||
                          (snapshot.quality !== "READY" && !acknowledge)
                        }
                        onClick={() => void handleFinalizeClosure()}
                        className="rounded-xl bg-indigo-600 hover:bg-indigo-500 px-5 py-2.5 text-xs font-bold text-white transition shadow-lg shadow-indigo-600/20 disabled:opacity-40"
                      >
                        {actionLoading === "closure" ? "Đang ghi chốt kỳ..." : ` Chốt Kỳ Với Bản #${snapshot.id}`}
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Customer Link Identity Pairing Section */}
              <div className="space-y-3 pt-3 border-t border-[#282828]">
                <h4 className="font-bold text-xs uppercase tracking-wider text-slate-300">
                  Liên Kết Định Danh Khách Cho Chuyển Kỳ (Rollover)
                </h4>
                <p className="text-xs text-slate-400">
                  Người vận hành ghép từng tab nguồn với hồ sơ khách nội bộ để đối chiếu số dư chuyển kỳ.
                </p>

                {links.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {links.map((link) => (
                      <div
                        key={link.sheet_id}
                        className="rounded-lg bg-slate-900 border border-[#282828] px-2.5 py-1 text-xs text-slate-300"
                      >
                        <span className="font-semibold text-white">{link.source_title}</span> →{" "}
                        <span className="text-emerald-400">
                          {customers.find((c) => c.id === link.customer_id)?.name ?? `khách #${link.customer_id}`}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <select
                    value={sheetId}
                    onChange={(e) => setSheetId(e.target.value)}
                    className="rounded-xl border border-[#333333] bg-[#1f1f1f] px-3 py-1.5 text-xs text-slate-100 focus:border-[#1ed760] focus:outline-none"
                  >
                    <option value="">Chọn tab khách…</option>
                    {(snapshot?.report?.customers ?? [])
                      .filter((c) => c.sheet_id !== null)
                      .map((c) => (
                        <option key={c.sheet_id} value={c.sheet_id ?? ""}>
                          {c.source_sheet}
                        </option>
                      ))}
                  </select>

                  <select
                    value={customerId}
                    onChange={(e) => setCustomerId(e.target.value)}
                    className="rounded-xl border border-[#333333] bg-[#1f1f1f] px-3 py-1.5 text-xs text-slate-100 focus:border-[#1ed760] focus:outline-none"
                  >
                    <option value="">Chọn khách nội bộ…</option>
                    {customers.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} · #{c.id}
                      </option>
                    ))}
                  </select>

                  <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={confirmRenamed}
                      onChange={(e) => setConfirmRenamed(e.target.checked)}
                      className="accent-indigo-500 rounded"
                    />
                    Tab đã đổi tên
                  </label>

                  <button
                    type="button"
                    disabled={!selected || !sheetId || !customerId}
                    onClick={() =>
                      void (async () => {
                        if (!selected) return;
                        await postJson(`/sheets/sources/${selected.id}/links`, {
                          sheet_id: Number(sheetId),
                          customer_id: Number(customerId),
                          confirm_renamed: confirmRenamed,
                        });
                        setConfirmRenamed(false);
                        await refreshDetail();
                        setNotice("Đã xác nhận liên kết khách.");
                      })()
                    }
                    className="rounded-xl bg-indigo-600 hover:bg-indigo-500 px-3.5 py-1.5 text-xs font-semibold text-white disabled:opacity-40 transition"
                  >
                    Xác nhận liên kết
                  </button>
                </div>
              </div>

              {/* Rollover Comparison Section */}
              <div className="space-y-3 pt-3 border-t border-[#282828]">
                <h4 className="font-bold text-xs uppercase tracking-wider text-slate-300">
                  Đối Chiếu Số Dư Chuyển Kỳ
                </h4>
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={previousId}
                    onChange={(e) => {
                      setPreviousId(e.target.value);
                      setRollover(null);
                    }}
                    className="rounded-xl border border-[#333333] bg-[#1f1f1f] px-3 py-1.5 text-xs text-slate-100 focus:border-[#1ed760] focus:outline-none"
                  >
                    <option value="">Chọn nguồn kỳ trước đã chốt…</option>
                    {sources
                      .filter((s) => s.id !== selected?.id)
                      .map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.period} · {s.name}
                        </option>
                      ))}
                  </select>

                  <button
                    type="button"
                    disabled={!selected || !previousId}
                    onClick={() =>
                      void (async () => {
                        if (!selected) return;
                        setRollover(
                          await fetchJson<Rollover>(
                            `/sheets/sources/${selected.id}/rollover?previous_source_id=${previousId}`,
                          ),
                        );
                      })()
                    }
                    className="rounded-xl border border-[#333333] bg-slate-800 hover:bg-slate-700 px-3.5 py-1.5 text-xs font-medium text-slate-200 disabled:opacity-40"
                  >
                    Xem đối chiếu
                  </button>
                </div>

                {rollover && (
                  <div className="rounded-xl bg-slate-900/90 border border-[#282828] p-4 text-xs space-y-2">
                    {!rollover.previous_closed && (
                      <p className="text-amber-400 font-semibold">
                        Kỳ trước chưa chốt — Đây là đối chiếu tạm tính giữa snapshot mới nhất.
                      </p>
                    )}
                    {rollover.customers.map((row) => (
                      <div
                        key={row.customer_id}
                        className="flex flex-wrap justify-between gap-2 border-b border-[#282828]/80 pb-2 pt-1"
                      >
                        <span>
                          <strong className="text-white">
                            {customers.find((c) => c.id === row.customer_id)?.name ?? `Khách #${row.customer_id}`}
                          </strong>{" "}
                          · {row.status}
                        </span>
                        <span className="font-mono text-slate-300">
                          {formatVnd(row.previous_value)} → {formatVnd(row.next_value)} · chênh{" "}
                          <span className={Number(row.difference) !== 0 ? "text-amber-400" : "text-emerald-400"}>
                            {formatVnd(row.difference)} VND
                          </span>
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* --------------------------------------------------------- */}
          {/* TAB 4: LỊCH SỬ ĐỒNG BỘ (SYNC HISTORY)                     */}
          {/* --------------------------------------------------------- */}
          {activeTab === "history" && (
            <div className="rounded-[8px] border border-[#282828]/80 bg-[#181818]/95 p-5 sm:p-6 shadow-xl backdrop-blur-md space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#282828] pb-3">
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    <span></span> Lịch Sử Đồng Bộ &amp; Audit Log
                  </h3>
                  <p className="text-xs text-slate-400">
                    Ghi chép toàn bộ các lượt đồng bộ tự động theo cron 15 phút hoặc kích hoạt thủ công.
                  </p>
                </div>

                <button
                  type="button"
                  onClick={() => void refreshDetail()}
                  className="rounded-xl border border-[#333333] bg-slate-800 hover:bg-slate-700 px-3 py-1.5 text-xs font-medium text-slate-200"
                >
                   Làm mới lịch sử
                </button>
              </div>

              {history.length === 0 ? (
                <div className="rounded-xl border border-[#282828] bg-slate-900/60 p-6 text-center text-xs text-slate-400">
                  Chưa có lượt đồng bộ nào cho nguồn này.
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="overflow-x-auto rounded-xl border border-[#282828] bg-slate-900/60">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-900 text-slate-400 uppercase font-semibold">
                        <tr>
                          <th className="p-3">Thời Gian Bắt Đầu</th>
                          <th className="p-3">Loại Kích Hoạt</th>
                          <th className="p-3">Trạng Thái</th>
                          <th className="p-3">Bản Lưu</th>
                          <th className="p-3">Chi Tiết / Lỗi</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/80">
                        {visibleHistory.map((item) => (
                          <tr key={item.id} className="hover:bg-slate-800/40 transition-colors">
                            <td className="p-3 font-mono text-slate-300">{timeText(item.started_at)}</td>
                            <td className="p-3">
                              <span
                                className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                                  item.trigger === "SCHEDULED"
                                    ? "bg-sky-500/10 text-sky-400 border border-sky-500/30"
                                    : "bg-purple-500/10 text-purple-400 border border-purple-500/30"
                                }`}
                              >
                                {item.trigger}
                              </span>
                            </td>
                            <td className="p-3">
                              <span
                                className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                                  item.status === "SUCCESS"
                                    ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                                    : item.status === "PARTIAL"
                                      ? "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                                      : "bg-rose-500/10 text-rose-400 border border-rose-500/30"
                                }`}
                              >
                                {item.status}
                              </span>
                            </td>
                            <td className="p-3 font-mono text-slate-300">
                              {item.snapshot_id ? `#${item.snapshot_id}` : "—"}
                            </td>
                            <td className="p-3 text-slate-400">
                              {item.error ? (
                                <span className="text-rose-400">{item.error}</span>
                              ) : (
                                "Đồng bộ hoàn thành bình thường"
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {history.length > HISTORY_PREVIEW_COUNT && (
                    <div className="flex justify-center pt-1">
                      <button
                        type="button"
                        onClick={() => setShowAllHistory((v) => !v)}
                        className="rounded-xl border border-[#333333] bg-slate-800 hover:bg-slate-700 px-4 py-2 text-xs font-medium text-slate-300 transition"
                      >
                        {showAllHistory ? "Thu gọn danh sách" : `Xem thêm (${history.length - HISTORY_PREVIEW_COUNT} lượt)`}
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      {/* ------------------------------------------------------------- */}
      {/* DRAWER / MODAL: CHI TIẾT TAB KHÁCH ĐƯỢC CHỌN (INSPECTOR)      */}
      {/* ------------------------------------------------------------- */}
      {inspectedCustomer && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm"
          onClick={() => setInspectedCustomer(null)}
        >
          <div
            className="w-full max-w-4xl max-h-[85vh] overflow-y-auto rounded-[8px] border border-[#282828] bg-[#181818] p-6 shadow-2xl space-y-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-[#282828] pb-3">
              <div>
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <span></span> Tab Khách: {inspectedCustomer.source_sheet}
                </h3>
                <p className="text-xs text-slate-400">
                  sheetId: {inspectedCustomer.sheet_id ?? "—"} · Trạng thái: {inspectedCustomer.profile_status}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setInspectedCustomer(null)}
                className="text-slate-400 hover:text-white text-sm"
              >
                 Đóng
              </button>
            </div>

            {/* Balances overview */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="rounded-xl bg-slate-900 border border-[#282828] p-3">
                <div className="text-[10px] text-slate-400 uppercase font-semibold">Số Dư Đầu Kỳ</div>
                <div className="text-base font-bold text-slate-100 mt-1 font-mono">
                  {inspectedCustomer.opening_balance?.formatted_value ??
                    (inspectedCustomer.opening_balance?.value
                      ? `${formatVnd(inspectedCustomer.opening_balance.value)} đ`
                      : "—")}
                </div>
              </div>

              <div className="rounded-xl bg-slate-900 border border-[#282828] p-3">
                <div className="text-[10px] text-slate-400 uppercase font-semibold">Số Dư Cuối Kỳ</div>
                <div className="text-base font-bold text-emerald-400 mt-1 font-mono">
                  {inspectedCustomer.linked_summary_rows?.[0]?.closing_balance_value != null
                    ? `${formatVnd(inspectedCustomer.linked_summary_rows[0].closing_balance_value)} đ`
                    : "—"}
                </div>
              </div>

              <div className="rounded-xl bg-slate-900 border border-[#282828] p-3">
                <div className="text-[10px] text-slate-400 uppercase font-semibold">Phạm Vi Ngày Ghi Nhận</div>
                <div className="text-xs font-semibold text-slate-200 mt-1">
                  {inspectedCustomer.observed_date_from && inspectedCustomer.observed_date_to
                    ? `${inspectedCustomer.observed_date_from} → ${inspectedCustomer.observed_date_to}`
                    : "Chưa rõ"}
                </div>
              </div>
            </div>

            {/* Daily breakdown */}
            {inspectedCustomer.daily && inspectedCustomer.daily.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                  Bảng Dữ Liệu Chi Tiêu Theo Ngày ({inspectedCustomer.daily.length} ngày)
                </h4>
                <div className="overflow-x-auto rounded-xl border border-[#282828] bg-slate-900/60 max-h-60 overflow-y-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-900 text-slate-400 uppercase font-semibold">
                      <tr>
                        <th className="p-2.5">Ngày</th>
                        <th className="p-2.5">Chi Tiêu VND</th>
                        <th className="p-2.5">Số Dòng TKQC</th>
                        <th className="p-2.5">Trạng Thái Dữ Liệu</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/80">
                      {inspectedCustomer.daily.map((d) => (
                        <tr key={d.business_date} className="hover:bg-slate-800/40">
                          <td className="p-2.5 font-mono text-white">{d.business_date}</td>
                          <td className="p-2.5 font-mono text-slate-200">
                            {d.spend_vnd ? `${formatVnd(d.spend_vnd)} đ` : "—"}
                          </td>
                          <td className="p-2.5 text-slate-400">{d.account_rows?.length ?? 0} dòng</td>
                          <td className="p-2.5 text-slate-400">{d.data_state}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Issues */}
            {inspectedCustomer.issues && inspectedCustomer.issues.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-bold text-rose-400 uppercase tracking-wider">
                  Cảnh Báo Của Tab Này ({inspectedCustomer.issues.length})
                </h4>
                <ul className="rounded-xl border border-rose-800/50 bg-rose-950/20 p-3 space-y-1 text-xs text-rose-300 list-disc list-inside">
                  {inspectedCustomer.issues.map((iss, i) => (
                    <li key={i}>
                      <strong className="text-white">{iss.source}:</strong> {iss.message}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* MODAL: VIA SHEET WRITEBACK                                    */}
      {/* ------------------------------------------------------------- */}
      <ViaSheetWritebackModal
        isOpen={showWritebackModal}
        onClose={() => setShowWritebackModal(false)}
        onSuccess={() => {
          setNotice("Đã hoàn tất ghi dòng báo cáo từ VIA lên Google Sheets.");
          void refreshDetail();
        }}
      />
    </div>
  );
}
