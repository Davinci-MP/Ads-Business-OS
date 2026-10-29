"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  postJson,
  fetchJson,
  type AccountRow,
  type SavedSheetSource,
  type SavedSheetSnapshot,
  type SavedSheetSnapshotEnvelope,
  type SheetSyncAttempt,
  type SheetCustomerLink,
  type SheetsSourceReport,
  type SheetsSourceReportCell,
  type SheetsSourceReportCustomer,
} from "../../lib/api";
import { formatBalanceVnd, formatVnd } from "../../lib/vnd.mjs";
import { loadPref, savePref } from "../../lib/prefs";

function sourceText(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  const raw = String(value);
  const match = raw.match(/^(-?)(\d+)(\.\d+)?$/);
  if (!match) return raw;
  const integer = match[2].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${match[1]}${integer}${match[3] ? `,${match[3].slice(1)}` : ""}`;
}

function cellColumn(address: string): string {
  return address.match(/[A-Z]+/)?.[0] ?? "";
}

function cellText(cell: SheetsSourceReportCell, knownVnd = false): string {
  const pattern = cell.number_format?.pattern ?? "";
  if (knownVnd || (cell.number_format?.type === "CURRENCY" && /VND|₫|đ/i.test(pattern))) {
    return formatVnd(typeof cell.value === "boolean" ? null : cell.value);
  }
  const raw = sourceText(cell.value);
  if (cell.formatted_value !== null && cell.formatted_value !== "" && cell.formatted_value !== raw) {
    return `Sheet: ${cell.formatted_value} · raw: ${raw}`;
  }
  return raw;
}

function currencyMapText(values: Record<string, string> | undefined): string | null {
  if (!values || Object.keys(values).length === 0) return null;
  return Object.entries(values)
    .map(([currency, amount]) => `${currency === "VND" ? formatVnd(amount) : sourceText(amount)} ${currency}`)
    .join(" · ");
}

function timeText(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" });
}

function badgeClass(status: string): string {
  if (status === "CONFIRMED" || status === "READY") {
    return "border-emerald-200 bg-emerald-50 text-emerald-800";
  }
  if (status === "PARTIAL" || status === "PREVIEW" || status === "DETECTED") {
    return "border-amber-200 bg-amber-50 text-amber-800";
  }
  return "border-slate-200 bg-slate-50 text-slate-700";
}

function StatusBadge({ status, label }: { status: string; label?: string }) {
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${badgeClass(status)}`}>
      {label ?? status.replaceAll("_", " ")}
    </span>
  );
}

function Card({
  title,
  value,
  unit,
  status,
  missingLabel,
  vnd,
  balance,
  coverage,
}: {
  title: string;
  value: string | number | null | undefined;
  unit?: string | null;
  status?: string;
  missingLabel?: string;
  vnd?: boolean;
  balance?: boolean;
  coverage?: string;
}) {
  const empty = value === null || value === undefined || value === "";
  const uncertain = status && ["PREVIEW", "UNIDENTIFIED", "NEEDS_CONFIRMATION", "NEEDS_REVIEW"].includes(status);
  const negative = !empty && (balance ? formatBalanceVnd(value).startsWith("-") : Number(value) < 0);
  return (
    <article className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-medium text-slate-600">{title}</h3>
        {(empty || uncertain || status === "PARTIAL") && <StatusBadge status="NEEDS_REVIEW" label={status === "PARTIAL" ? `Một phần${coverage ? ` · ${coverage}` : ""}` : empty ? (missingLabel ?? "Chưa có dữ liệu") : status === "NEEDS_REVIEW" ? "Chưa đủ dữ liệu" : "Chưa xác nhận"} />}
      </div>
      <p className={`mt-3 break-words text-xl font-semibold ${negative ? "text-rose-700" : "text-slate-900"}`}>
        {empty ? "—" : `${balance ? formatBalanceVnd(value) : vnd ? formatVnd(value) : sourceText(value)}${unit ? ` ${unit}` : ""}`}
      </p>
    </article>
  );
}

function accountContext(
  row: NonNullable<SheetsSourceReportCustomer["account_rows"]>[number],
  customer: SheetsSourceReportCustomer,
  accounts: AccountRow[] | null,
  links: SheetCustomerLink[] | null,
  error: string | null,
) {
  const matches = accounts?.filter((item) => item.meta_ad_account_id.replace(/^act_/i, "") === row.account_id.replace(/^act_/i, "")) ?? [];
  const account = matches.length === 1 ? matches[0] : undefined;
  const link = links?.find((item) => item.sheet_id === customer.sheet_id && item.source_title === customer.source_sheet);
  const applicable = account?.assignment_history.filter((assignment) =>
    row.business_date && assignment.valid_from && assignment.valid_from.slice(0, 10) <= row.business_date &&
    (!assignment.valid_to || assignment.valid_to.slice(0, 10) >= row.business_date),
  ) ?? [];
  const candidate = applicable.length === 1 ? applicable[0] : null;
  const assignment = candidate && row.business_date && candidate.valid_from &&
    candidate.valid_from.slice(0, 10) < row.business_date &&
    (!candidate.valid_to || candidate.valid_to.slice(0, 10) > row.business_date) &&
    link && candidate.customer_id === link.customer_id ? candidate : null;
  const status = account && account.status !== "ACTIVE" ? account.status : "Chưa cập nhật";
  return {
    user: assignment?.customer_name ? `${assignment.customer_name} · khách được phân công` : `${customer.display_name} · khách của tab`,
    assignmentNote: applicable.length > 0 && !assignment ? "Phân công chưa khớp hoặc chưa xác nhận liên kết tab." : null,
    statusKey: matches.length > 1 ? "AMBIGUOUS" : account && account.status !== "ACTIVE" ? account.status : "UNUPDATED",
    status: error ? "Không tải được dữ liệu" : accounts === null ? "Đang tải" : matches.length > 1 ? "ID trùng, cần đối chiếu" : status,
    cost: error ? "Không tải được dữ liệu" : accounts === null ? "Đang tải" : matches.length > 1 ? "ID trùng, cần đối chiếu" : account?.purchase_cost != null ? `${sourceText(account.purchase_cost)} · chưa xác định đơn vị` : "Chưa nhập",
  };
}

function RawCells({ cells }: { cells: SheetsSourceReportCell[] }) {
  const visible = cells.filter((cell) => cell.value !== null || cell.formula);
  if (visible.length === 0) return <span className="text-slate-400">Không có giá trị nguồn</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {visible.map((cell) => (
        <span
          key={cell.address}
          title={cell.formula ? `${cell.address} · ${cell.formula}` : cell.address}
          className="inline-flex max-w-full items-center gap-1 rounded-md bg-slate-50 px-2 py-1 text-xs text-slate-700 ring-1 ring-inset ring-slate-200"
        >
          <span className="shrink-0 font-mono text-slate-500">{cell.address}</span>
          <span className="truncate">{cellText(cell, ["F", "G", "H", "K"].includes(cellColumn(cell.address)))}</span>
        </span>
      ))}
    </div>
  );
}

function LoadingCards() {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Đang tải báo cáo Sheets">
      {[0, 1, 2, 3].map((item) => (
        <div key={item} className="h-32 animate-pulse rounded-2xl border border-slate-200 bg-white p-5">
          <div className="h-4 w-2/3 rounded bg-slate-200" />
          <div className="mt-5 h-7 w-4/5 rounded bg-slate-100" />
        </div>
      ))}
    </div>
  );
}

function CustomerSummary({ customers }: { customers: SheetsSourceReportCustomer[] }) {
  const columns = [
    { key: "opening", label: "Số dư đầu kỳ" },
    { key: "budget_deposits_vnd", label: "Nạp trong kỳ" },
    { key: "spend_vnd", label: "Chi tiêu quảng cáo" },
    { key: "fee", label: "Phí / Lợi nhuận" },
    { key: "billing_total", label: "Tổng gồm phí" },
    { key: "current_balance", label: "Số dư hiện tại" },
  ];
  return (
    <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="p-4 sm:p-5">
        <h2 className="font-semibold text-slate-900">Tổng hợp khách hàng</h2>
        <p className="mt-1 text-xs text-slate-500">VND · Tổng theo tab nguồn, không theo bộ lọc ngày; kỳ chưa rõ cần xem chi tiết.</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[850px] text-sm">
          <thead className="bg-slate-50 text-xs text-slate-600">
            <tr>
              <th scope="col" className="px-4 py-3 text-left font-medium">Khách hàng</th>
              {columns.map((col) => <th key={col.key} scope="col" className="px-4 py-3 text-right font-medium">{col.label}</th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {customers.map((item) => (
              <tr key={item.source_sheet}>
                <th scope="row" className="px-4 py-3 text-left font-medium text-slate-800">
                  {item.display_name}
                  {item.completeness_status === "NEEDS_REVIEW" && <span className="block text-xs font-normal text-amber-800">Cần rà soát</span>}
                </th>
                {columns.map((col) => {
                  const value = col.key === "opening" ? item.opening_balance?.value : item.tab_source_totals?.[col.key]?.value;
                  const state = col.key === "opening" ? item.opening_balance?.status : item.tab_source_totals?.[col.key]?.status;
                  const balance = col.key === "opening" || col.key === "current_balance";
                  const display = balance ? formatBalanceVnd(value) : formatVnd(value);
                  return <td key={col.key} className={`whitespace-nowrap px-4 py-3 text-right tabular-nums ${display.startsWith("-") ? "text-rose-700" : "text-slate-800"}`}>
                    {display}
                    {value != null && state && ["PREVIEW", "UNIDENTIFIED", "NEEDS_CONFIRMATION", "NEEDS_REVIEW"].includes(state) && <span className="block text-xs text-amber-800">Chưa xác nhận</span>}
                  </td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SummaryTable({ report }: { report: SheetsSourceReport }) {
  const rows = (report.summary_tabs ?? []).flatMap((tab) =>
    tab.rows.map((row) => ({ tab, row })),
  );
  return (
    <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 p-4 sm:p-5">
        <h2 className="font-semibold text-slate-900">Tổng hợp khách theo báo cáo nguồn</h2>
        <p className="mt-1 text-xs text-slate-500">
          Giữ nguyên giá trị/formula từng ô; bảng tổng hợp không được cộng với tab chi tiết.
        </p>
      </div>
      {rows.length === 0 ? (
        <p className="p-5 text-sm text-slate-500">Không nhận diện được dòng tổng hợp có thể hiển thị.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="px-4 py-3 font-medium">Khách / nhãn nguồn</th>
                <th className="px-4 py-3 font-medium">Tab liên kết</th>
                <th className="px-4 py-3 font-medium">Trạng thái liên kết</th>
                <th className="px-4 py-3 font-medium">Giá trị theo Sheet (ô nguồn)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map(({ tab, row }) => (
                <tr key={`${tab.title}:${row.summary_row}`} className="align-top">
                  <td className="px-4 py-3 font-medium text-slate-800">
                    {row.customer_label}
                    <div className="mt-1 text-xs font-normal text-slate-400">
                      {tab.title}!{row.summary_row} · header dòng {tab.header_row} · kỳ không suy ra từ tên tab
                    </div>
                  </td>
                  <td className="px-4 py-3 text-slate-700">{row.customer_sheet ?? "Chưa xác định"}</td>
                  <td className="px-4 py-3"><StatusBadge status={row.link_status} /></td>
                  <td className="max-w-3xl px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      {row.cells
                        .filter((cell) => cell.value !== null || cell.formula)
                        .map((cell) => {
                          const label = tab.source_columns[cellColumn(cell.address)];
                          return (
                            <span
                              key={cell.address}
                              title={cell.formula ?? cell.address}
                              className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs"
                            >
                              <span className="font-medium text-slate-600">{label || cellColumn(cell.address)}</span>
                              <span className="mx-1 text-slate-400">·</span>
                              <span className="font-mono text-slate-500">{cell.address}</span>
                              <span className="mx-1 text-slate-400">=</span>
                              <span className="text-slate-800">{cellText(cell)}</span>
                            </span>
                          );
                        })}
                    </div>
                    {row.unresolved_references.length > 0 && (
                      <p className="mt-2 text-xs text-amber-800">
                        Tham chiếu chưa phân giải: {row.unresolved_references.map((ref) => {
                          const sources = ref.cells.map((address) => {
                            const formula = row.cells.find((cell) => cell.address === address)?.formula;
                            return `${tab.title}!${address}${formula ? ` (${formula})` : ""}`;
                          });
                          return `${sources.join(", ")} → ${ref.sheet}`;
                        }).join(" · ")}
                      </p>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function numberPref(key: string): number | null {
  const restored = Number(loadPref(key, ""));
  return Number.isInteger(restored) && restored > 0 ? restored : null;
}

function urlNumberParam(name: string): number | null {
  if (typeof window === "undefined") return null;
  const raw = new URLSearchParams(window.location.search).get(name);
  const value = Number(raw);
  return raw !== null && Number.isInteger(value) && value > 0 ? value : null;
}

function stillSavedClientMatch(
  data: SheetsSourceReport,
  savedCustomer: string,
): SheetsSourceReportCustomer | null {
  if (!savedCustomer) return null;
  return (data.customers ?? []).find((item) => item.source_sheet === savedCustomer) ?? null;
}

export default function SheetsSourceReportView() {
  const [sources, setSources] = useState<SavedSheetSource[]>([]);
  const [schedulerEnabled, setSchedulerEnabled] = useState<boolean | null>(null);
  // URL hợp lệ ưu tiên lựa chọn đã lưu; URL sai giá trị → bỏ qua, dùng lựa chọn đã lưu/mặc định.
  const [sourceId, setSourceId] = useState<number | null>(() =>
    urlNumberParam("source_id") ?? numberPref("sheetsReport.source"));
  const [snapshots, setSnapshots] = useState<SavedSheetSnapshot[]>([]);
  const [snapshotId, setSnapshotId] = useState<number | null>(() =>
    urlNumberParam("snapshot_id") ?? numberPref("sheetsReport.snapshot"));
  const [report, setReport] = useState<SheetsSourceReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [customerSheet, setCustomerSheet] = useState(() => loadPref("sheetsReport.customer", ""));
  const [period, setPeriod] = useState(() => loadPref("sheetsReport.period", ""));
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [manualAccounts, setManualAccounts] = useState<AccountRow[] | null>(null);
  const [manualError, setManualError] = useState<string | null>(null);
  const [sheetLinks, setSheetLinks] = useState<SheetCustomerLink[] | null>(null);
  const [linksError, setLinksError] = useState<string | null>(null);
  const [accountIdFilter, setAccountIdFilter] = useState("");
  const [accountStatusFilter, setAccountStatusFilter] = useState("");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const requestId = useRef(0);
  const periodSourceRef = useRef<number | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const customerRef = useRef(customerSheet);
  const periodRef = useRef(period);
  customerRef.current = customerSheet;
  periodRef.current = period;
  // Ưu tiên khi mới vào trang: URL hợp lệ → lựa chọn đã lưu → mặc định hệ thống (default/active).
  const requestedSourceRef = useRef<number | null>(urlNumberParam("source_id"));
  const savedSourceRef = useRef<number | null>(numberPref("sheetsReport.source"));
  const requestedSnapshotRef = useRef<number | null>(urlNumberParam("snapshot_id"));
  const loadManualAccounts = useCallback(async () => {
    try {
      setManualAccounts(await fetchJson<AccountRow[]>("/dashboard/accounts"));
      setManualError(null);
    } catch (loadError) {
      setManualAccounts(null);
      setManualError(loadError instanceof Error ? loadError.message : String(loadError));
    }
  }, []);

  useEffect(() => { void loadManualAccounts(); }, [loadManualAccounts]);

  useEffect(() => {
    savePref("sheetsReport.source", sourceId === null ? "" : String(sourceId));
  }, [sourceId]);
  useEffect(() => {
    savePref("sheetsReport.snapshot", snapshotId === null ? "" : String(snapshotId));
  }, [snapshotId]);
  useEffect(() => {
    savePref("sheetsReport.customer", customerSheet);
  }, [customerSheet]);
  useEffect(() => {
    savePref("sheetsReport.period", period);
  }, [period]);

  useEffect(() => {
    if (sourceId === null) return;
    let active = true;
    setSheetLinks(null);
    setLinksError(null);
    fetchJson<SheetCustomerLink[]>(`/sheets/sources/${sourceId}/links`).then((data) => {
      if (active) setSheetLinks(data);
    }).catch((failure: unknown) => {
      if (active) setLinksError(failure instanceof Error ? failure.message : String(failure));
    });
    return () => { active = false; };
  }, [sourceId]);

  const loadReport = useCallback(async (id: number, version: number | null = null) => {
    const request = ++requestId.current;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setReport(null);
    setError(null);
    setLoading(true);
    try {
      const saved = await fetchJson<SavedSheetSnapshot>(
        `/sheets/sources/${id}/report${version === null ? "" : `?snapshot_id=${version}`}`,
        { signal: controller.signal },
      );
      if (request !== requestId.current) return;
      const data = saved.report;
      if (!data) throw new Error("Bản lưu không có nội dung báo cáo.");
      setReport(data);
      setSnapshotId(version);
      const savedCustomer = customerRef.current;
      const stillSaved = stillSavedClientMatch(data, savedCustomer);
      const firstCustomer = stillSaved ?? data.customers?.[0];
      setCustomerSheet(firstCustomer?.source_sheet ?? "");
      const sourcePeriods = new Set([
        ...(firstCustomer?.source_periods ?? []),
        firstCustomer?.activity_status?.period,
        data.all_customer_totals?.period,
      ].filter((value): value is string => Boolean(value)));
      // Giữ kỳ đã lưu nếu còn hợp lệ cho nguồn này; nếu không về kỳ nguồn đang hoạt động.
      setPeriod(periodRef.current && sourcePeriods.has(periodRef.current) ? periodRef.current : data.all_customer_totals?.period ?? "");
      periodSourceRef.current = id;
      setDateFrom("");
      setDateTo("");
    } catch (loadError) {
      if (request !== requestId.current || (loadError instanceof DOMException && loadError.name === "AbortError")) return;
      setError(loadError instanceof Error ? loadError.message : String(loadError));
      if (version !== null) {
        // URL/snapshot_id không hợp lệ → về bản lưu mới nhất của nguồn thay vì để trang rỗng.
        setSnapshotId(null);
        void loadReport(id);
      }
    } finally {
      if (request === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    const requested = requestedSourceRef.current;
    const saved = savedSourceRef.current;
    fetchJson<{ sources: SavedSheetSource[]; scheduler_enabled: boolean }>("/sheets/sources").then((data) => {
      if (!active) return;
      setSources(data.sources);
      setSchedulerEnabled(data.scheduler_enabled);
      const source = data.sources.find((item) => item.id === requested)
        ?? data.sources.find((item) => item.id === saved)
        ?? data.sources.find((item) => item.is_default)
        ?? data.sources.find((item) => item.active);
      if (source) {
        setSourceId(source.id);
        void loadReport(source.id, requestedSnapshotRef.current ?? snapshotId);
      }
    }).catch((loadError: unknown) => {
      if (active) setError(loadError instanceof Error ? loadError.message : String(loadError));
    });
    return () => { active = false; controllerRef.current?.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadReport]);

  useEffect(() => {
    if (sourceId === null) return;
    let active = true;
    const refresh = async () => {
      try {
        const [list, versions] = await Promise.all([
          fetchJson<{ sources: SavedSheetSource[]; scheduler_enabled: boolean }>("/sheets/sources"),
          fetchJson<SavedSheetSnapshotEnvelope>(`/sheets/sources/${sourceId}/snapshots`),
        ]);
        if (active) {
          setSources(list.sources);
          setSchedulerEnabled(list.scheduler_enabled);
          setSnapshots(versions.snapshots);
        }
      } catch (loadError) {
        if (active) setError(loadError instanceof Error ? loadError.message : String(loadError));
      }
    };
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 15000);
    return () => { active = false; window.clearInterval(timer); };
  }, [sourceId]);

  const customers = report?.customers ?? [];
  const customer = customers.find((item) => item.source_sheet === customerSheet) ?? null;
  const periods = customer?.source_periods ?? [];
  const confirmedActivityPeriod = customer?.activity_status?.period;
  const dailyRows = customer?.daily ?? [];
  const filteredDaily = useMemo(
    () => dailyRows.filter((row) => {
      if (period && !row.business_date.startsWith(period)) return false;
      if (dateFrom && row.business_date < dateFrom) return false;
      if (dateTo && row.business_date > dateTo) return false;
      return true;
    }),
    [dailyRows, period, dateFrom, dateTo],
  );
  const visibleAccountRows = useMemo(
    () => (customer?.account_rows ?? []).filter((row) => {
      if (!row.business_date) return false;
      if (period && !row.business_date.startsWith(period)) return false;
      if (dateFrom && row.business_date < dateFrom) return false;
      if (dateTo && row.business_date > dateTo) return false;
      if (accountIdFilter && !row.account_id.toLowerCase().includes(accountIdFilter.toLowerCase().trim())) return false;
      if (accountStatusFilter && customer && manualAccounts !== null && !manualError && accountContext(row, customer, manualAccounts, sheetLinks, manualError).statusKey !== accountStatusFilter) return false;
      return true;
    }),
    [customer, period, dateFrom, dateTo, accountIdFilter, accountStatusFilter, manualAccounts, sheetLinks, manualError],
  );
  const undatedAccountRows = customer?.account_rows?.filter((row) => !row.business_date) ?? [];
  const undatedDeposits = customer?.deposits?.filter((row) => !row.business_date) ?? [];
  const visibleDeposits = useMemo(
    () => (customer?.deposits ?? []).filter((row) => {
      if (!row.business_date) return false;
      if (period && !row.business_date.startsWith(period)) return false;
      if (dateFrom && row.business_date < dateFrom) return false;
      if (dateTo && row.business_date > dateTo) return false;
      return true;
    }),
    [customer, period, dateFrom, dateTo],
  );
  const periodTotals = period ? customer?.period_totals?.[period] : undefined;
  const sourceTotals = periodTotals?.source_totals ?? customer?.tab_source_totals ?? {};
  const fieldStatus = customer?.field_status ?? {};
  const openingBalance = customer?.opening_balance;
  const closingBalance = sourceTotals.current_balance;
  const chartData = filteredDaily.map((row) => ({
    date: row.business_date,
    spendVnd: row.spend_vnd === null ? null : Number(row.spend_vnd),
    feeVnd: row.fee_by_currency.VND === undefined ? null : Number(row.fee_by_currency.VND),
    totalVnd: row.billing_by_currency.VND === undefined ? null : Number(row.billing_by_currency.VND),
  }));
  const sourcePeriods = [...new Set([...periods, confirmedActivityPeriod, report?.all_customer_totals?.period, period].filter((value): value is string => Boolean(value)))].sort();

  const selectedSource = sources.find((item) => item.id === sourceId);
  const stale = Boolean(report && Date.now() - new Date(report.read_at).getTime() > 30 * 60 * 1000);
  const warningMessages = [
    error ? "Không thể cập nhật hoặc tải báo cáo." : null,
    selectedSource?.last_attempt?.status === "ERROR" ? "Lần đồng bộ gần nhất gặp lỗi." : null,
    stale ? "Dữ liệu đã quá 30 phút." : null,
    schedulerEnabled === false || selectedSource?.sync_enabled === false ? "Tự cập nhật đang tắt." : null,
    report && report.status !== "READY" ? "Báo cáo còn dữ liệu cần rà soát." : null,
    customer?.completeness_status === "NEEDS_REVIEW" ? "Dữ liệu khách được chọn chưa đầy đủ." : null,
    customer?.activity_status?.conflict ? "Dữ liệu có thể mâu thuẫn với trạng thái chưa hoạt động." : null,
    (periodTotals?.source_detail_differences?.length ?? 0) > 0 ? "Tổng nguồn và chi tiết có chênh lệch." : null,
    manualError ? "Không tải được dữ liệu tài khoản nội bộ." : null,
    linksError ? "Không tải được liên kết khách đã xác nhận." : null,
  ].filter(Boolean);
  useEffect(() => {
    if (snapshotId === null || loading || snapshots.length === 0) return;
    if (snapshots.some((item) => item.id === snapshotId)) return;
    setSnapshotId(null);
    if (sourceId !== null) void loadReport(sourceId);
  }, [snapshots, snapshotId, loading, sourceId, loadReport]);

  useEffect(() => {
    if (sourceId !== null && snapshotId === null && report && !loading && !syncing &&
        selectedSource?.latest_snapshot &&
        new Date(selectedSource.latest_snapshot.read_at).getTime() !== new Date(report.read_at).getTime()) {
      void loadReport(sourceId);
    }
  }, [sourceId, snapshotId, report, loading, syncing, selectedSource?.latest_snapshot, loadReport]);

  async function syncNow() {
    if (sourceId === null) return;
    setSyncing(true);
    setError(null);
    try {
      const result = await postJson<SheetSyncAttempt>(`/sheets/sources/${sourceId}/sync`);
      const updated = await fetchJson<{ sources: SavedSheetSource[]; scheduler_enabled: boolean }>("/sheets/sources");
      setSources(updated.sources);
      setSchedulerEnabled(updated.scheduler_enabled);
      if (result.status === "ERROR") throw new Error(result.error ?? "Đọc nguồn thất bại.");
      await loadReport(sourceId);
    } catch (syncError) {
      setError(syncError instanceof Error ? syncError.message : String(syncError));
    } finally {
      setSyncing(false);
    }
  }

  const metadataDetails = (
    <div className="space-y-3 text-sm text-slate-700">
      <label htmlFor="saved-sheet-version" className="block font-medium">Bản báo cáo / lịch sử</label>
      <select id="saved-sheet-version" value={snapshotId ?? ""} disabled={loading || syncing || sourceId === null}
        onChange={(event) => { if (sourceId !== null) void loadReport(sourceId, event.target.value ? Number(event.target.value) : null); }}
        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm sm:w-auto">
        <option value="">Bản lưu mới nhất (tạm)</option>
        {snapshots.map((item) => <option key={item.id} value={item.id}>#{item.id} · {timeText(item.read_at)}{selectedSource?.closure?.snapshot_id === item.id ? " · BẢN CHỐT" : ""}</option>)}
      </select>
      <p>Tự cập nhật mỗi 15 phút chỉ khi backend đang chạy. {selectedSource?.sync_enabled ? "Nguồn đang bật đồng bộ." : "Nguồn chưa bật đồng bộ."} {schedulerEnabled === false && "Lịch backend đang tắt."}</p>
      {selectedSource && <p>Lần thử gần nhất: {selectedSource.last_attempt ? `${timeText(selectedSource.last_attempt.started_at)} · ${selectedSource.last_attempt.status}` : "chưa có"} · Lần lưu gần nhất: {selectedSource.latest_snapshot ? timeText(selectedSource.latest_snapshot.read_at) : "chưa có"} · {selectedSource.closure ? `Bản chốt #${selectedSource.closure.snapshot_id}` : "Chưa chốt"}</p>}
      {report && <p>Chế độ: {report.mode} · Trạng thái: {report.status} · Mapping: {report.mapping_status} · Meta: {report.meta_reconciliation_status} · {report.workbook_tab_count} tab.</p>}
      {selectedSource?.last_attempt?.error && <p className="break-words text-rose-800">Lỗi đồng bộ: {selectedSource.last_attempt.error}</p>}
      {error && <p className="break-words text-rose-800">Lỗi tải/cập nhật: {error} <button type="button" className="underline" onClick={() => sourceId !== null && void loadReport(sourceId)}>Thử tải lại</button></p>}
      {manualError && <p className="break-words text-rose-800">Lỗi tài khoản: {manualError} <button type="button" className="underline" onClick={() => void loadManualAccounts()}>Thử lại</button></p>}
      {linksError && <p className="break-words text-rose-800">Lỗi liên kết khách: {linksError}</p>}
      <a className="inline-block underline" href="/sheets#saved-sources">Quản lý nguồn / lịch sử / chốt kỳ</a>
    </div>
  );

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-sky-200 bg-sky-50 p-4 sm:p-5">
        <div className="flex flex-col gap-2 sm:flex-row">
          <label htmlFor="saved-sheet-source" className="sr-only">Nguồn báo cáo đã lưu</label>
          <select id="saved-sheet-source" value={sourceId ?? ""} disabled={syncing} onChange={(event) => {
            const id = Number(event.target.value);
            setSourceId(id);
            setReport(null);
            void loadReport(id);
          }} className="min-w-0 flex-1 rounded-lg border border-sky-200 bg-white px-3 py-2 text-sm text-slate-900">
            {sources.length === 0 && <option value="">Chưa có nguồn đã lưu</option>}
            {sources.map((item) => <option key={item.id} value={item.id}>{item.period} · {item.name}{item.active ? "" : " · đã thay thế"}</option>)}
          </select>
          <button
            type="button" onClick={() => void syncNow()}
            disabled={loading || syncing || !selectedSource?.active}
            className="rounded-lg bg-sky-900 px-4 py-2 text-sm font-medium text-white hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {syncing ? "Đang cập nhật…" : "Cập nhật"}
          </button>
        </div>
        {report && <p className="mt-3 text-xs text-sky-900">Dữ liệu cập nhật lúc {timeText(report.read_at)} · {snapshotId === selectedSource?.closure?.snapshot_id ? "Bản chốt" : snapshotId !== null ? "Bản lịch sử" : selectedSource?.closure ? "Bản mới nhất, không phải bản chốt" : "Chưa chốt"}</p>}
      </section>

      {loading && <LoadingCards />}
      {warningMessages.length > 0 && (
        <section role="alert" className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
          <p>{warningMessages.join(" ")}</p>
          <button type="button" className="font-medium underline" onClick={() => {
            setDetailsOpen(true);
            detailsRef.current?.scrollIntoView({ block: "start" });
            detailsRef.current?.querySelector("summary")?.focus();
          }}>Xem chi tiết</button>
        </section>
      )}
      {!loading && !error && !report && (
        <section className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center">
          <h3 className="font-semibold text-slate-800">Chưa có báo cáo Sheets</h3>
          <p className="mt-2 text-sm text-slate-500">
            Thêm nguồn theo kỳ tại trang Sheets; nguồn sẽ được kiểm tra cấu trúc trước khi lưu.
          </p>
        </section>
      )}
      {report && !loading && (
        <>
          <a className="text-sm text-sky-700 underline" href="/#tong">Xem tổng tài chính tất cả khách</a>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <label htmlFor="sheets-report-period" className="mb-1 block text-xs font-medium text-slate-500">
                Kỳ chi tiết / kỳ nguồn
              </label>
              <select
                id="sheets-report-period"
                value={period}
                onChange={(event) => {
                  setPeriod(event.target.value);
                  setDateFrom("");
                  setDateTo("");
                }}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
              >
                <option value="">Tất cả kỳ có ngày nguồn</option>
                {sourcePeriods.map((item) => <option key={item} value={item}>{item}{!periods.includes(item) ? " · kỳ nguồn, chưa có ngày chi tiết" : ""}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="sheets-report-customer" className="mb-1 block text-xs font-medium text-slate-500">
                Khách / tab khách đã liên kết
              </label>
              <select
                id="sheets-report-customer"
                value={customerSheet}
                onChange={(event) => {
                  setCustomerSheet(event.target.value);
                  setDateFrom("");
                  setDateTo("");
                }}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
              >
                {customers.map((item) => (
                  <option key={item.source_sheet} value={item.source_sheet}>
                    {item.display_name} · {item.source_sheet}
                  </option>
                ))}
                {customers.length === 0 && <option value="">Không có tab khách đọc được</option>}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label htmlFor="sheets-report-from" className="mb-1 block text-xs font-medium text-slate-500">Từ ngày</label>
                <input
                  id="sheets-report-from"
                  type="date"
                  value={dateFrom}
                  onChange={(event) => setDateFrom(event.target.value)}
                  className="w-full rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm"
                />
              </div>
              <div>
                <label htmlFor="sheets-report-to" className="mb-1 block text-xs font-medium text-slate-500">Đến ngày</label>
                <input
                  id="sheets-report-to"
                  type="date"
                  value={dateTo}
                  onChange={(event) => setDateTo(event.target.value)}
                  className="w-full rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm"
                />
              </div>
            </div>
          </div>

          {customer ? (
            <>
              <section>
                <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
                  <div>
                    <h2 className="text-lg font-semibold text-slate-900">
                      {customer.display_name}
                    </h2>
                    <p className="mt-1 text-xs text-slate-500">
                      VND theo tab nguồn{customer.source_config_period ? ` · kỳ nguồn ${customer.source_config_period}` : periods.length === 1 ? ` · kỳ ${periods[0]}` : " · chưa xác định kỳ"}; USDT theo kỳ chi tiết. Lọc ngày chỉ áp dụng cho chi tiết.
                    </p>
                  </div>
                  {customer.activity_status && (
                    <p className="rounded-lg bg-sky-50 p-3 text-xs text-sky-900">
                      Kỳ {customer.activity_status.period}: Chưa hoạt động trong kỳ — theo xác nhận chủ dự án.
                      {customer.activity_status.conflict && " Có dữ liệu có thể mâu thuẫn; cần rà soát."}
                    </p>
                  )}
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <Card
                    title="Số dư đầu kỳ"
                    value={openingBalance?.value}
                    unit="VND"
                    vnd
                    balance
                    status={openingBalance?.status}
                  />
                  <Card
                    title="Nạp trong kỳ"
                    value={sourceTotals.budget_deposits_vnd?.value}
                    unit="VND"
                    vnd
                    status={sourceTotals.budget_deposits_vnd?.status}
                  />
                  <Card
                    title="USDT nhận"
                    value={periodTotals?.usdt_received}
                    unit="USDT"
                    status={undatedDeposits.some((item) => item.included) ? "NEEDS_REVIEW" : fieldStatus.usdt_receipts?.status}
                    missingLabel={customer.usdt_receipts_state === "NO_RECORDED" ? "Chưa ghi nhận" : "Chưa đủ dữ liệu"}
                  />
                  <Card
                    title="Chi tiêu quảng cáo"
                    value={sourceTotals.spend_vnd?.value}
                    unit="VND"
                    vnd
                    status={sourceTotals.spend_vnd?.status ?? fieldStatus.spend_vnd?.status}
                  />
                  <Card
                    title="Phí / Lợi nhuận"
                    value={sourceTotals.fee?.value}
                    unit="VND"
                    vnd
                    status={sourceTotals.fee?.status ?? fieldStatus.fee?.status}
                  />
                  <Card
                    title="Tổng chi tiêu gồm phí"
                    value={sourceTotals.billing_total?.value}
                    unit="VND"
                    vnd
                    status={sourceTotals.billing_total?.status ?? fieldStatus.billing_total?.status}
                  />
                  <Card
                    title="Số dư hiện tại"
                    value={closingBalance?.value}
                    unit="VND"
                    vnd
                    balance
                    status={closingBalance?.status}
                  />
                </div>
              </section>

              <CustomerSummary customers={customers} />

              <details className="rounded-2xl border border-slate-200 bg-white shadow-sm">
                <summary className="cursor-pointer p-4 font-semibold text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-700">Biểu đồ theo ngày</summary>
              <section className="border-t border-slate-200 p-4 sm:p-5">
                <div className="mb-4">
                  <h2 className="font-semibold text-slate-900">Chi tiêu theo ngày (VND theo Sheet)</h2>
                  <p className="mt-1 text-xs text-slate-500">Biểu đồ chỉ lấy dữ liệu ngày đã đọc; không cộng chéo currency.</p>
                </div>
                {chartData.length === 0 ? (
                  <p className="py-10 text-center text-sm text-slate-500">Không có dữ liệu ngày đủ điều kiện trong phạm vi lọc.</p>
                ) : (
                  <div className="h-72 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                        <YAxis tickFormatter={(value) => formatVnd(value)} tick={{ fontSize: 11 }} />
                        <Tooltip formatter={(value) => formatVnd(value as number | string | null)} />
                        <Line type="monotone" dataKey="spendVnd" name="Chi tiêu VND" stroke="#1e3a8a" strokeWidth={2} connectNulls={false} />
                        <Line type="monotone" dataKey="feeVnd" name="Phí VND theo Sheet" stroke="#d97706" strokeWidth={2} connectNulls={false} />
                        <Line type="monotone" dataKey="totalVnd" name="Tổng VND theo Sheet" stroke="#0f766e" strokeWidth={2} connectNulls={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </section>
              </details>

              <details className="rounded-2xl border border-slate-200 bg-white shadow-sm">
                <summary className="cursor-pointer p-4 font-semibold text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-700">Chi tiêu tài khoản quảng cáo theo ngày{undatedAccountRows.length > 0 ? ` · ${undatedAccountRows.length} dòng thiếu ngày` : ""}{(customer.unclassified_rows?.length ?? 0) > 0 ? ` · ${customer.unclassified_rows?.length} dòng cần phân loại` : ""}</summary>
              <section className="border-t border-slate-200">
                <div className="border-b border-slate-100 p-4 sm:p-5">
                  <h2 className="font-semibold text-slate-900">Chi tiêu tài khoản quảng cáo theo ngày</h2>
                  <p className="mt-1 text-xs text-slate-500">
                    Giữ từng dòng nguồn, không cộng các dòng cùng TKQC/ngày. Chi phí mua thuộc tài khoản, không cộng lặp theo ngày.
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Trạng thái là thông tin thủ công hiện tại, không phải trạng thái Meta live hay lịch sử. <a className="underline" href="/accounts">Nhập chi phí / cập nhật tài khoản</a>.
                  </p>
                  {manualError && <p className="mt-2 text-xs text-red-700">Không tải được dữ liệu tài khoản nội bộ: {manualError} <button type="button" className="underline" onClick={() => void loadManualAccounts()}>Thử lại</button></p>}
                  <div className="mt-3 flex flex-wrap gap-3">
                    <label className="text-xs text-slate-600">Lọc ID TKQC
                      <input value={accountIdFilter} onChange={(event) => setAccountIdFilter(event.target.value)} className="ml-2 rounded-lg border border-slate-300 px-2 py-1 text-sm" />
                    </label>
                    <label className="text-xs text-slate-600">Trạng thái hiện tại
                      <select value={accountStatusFilter} onChange={(event) => setAccountStatusFilter(event.target.value)} disabled={manualAccounts === null || Boolean(manualError)} className="ml-2 rounded-lg border border-slate-300 bg-white px-2 py-1 text-sm">
                        <option value="">Tất cả</option>
                        <option value="UNUPDATED">Chưa cập nhật</option>
                        <option value="AMBIGUOUS">ID trùng, cần đối chiếu</option>
                        {[...new Set((manualAccounts ?? []).map((item) => item.status).filter((status) => status !== "ACTIVE"))].sort().map((status) => <option key={status} value={status}>{status}</option>)}
                      </select>
                    </label>
                  </div>
                </div>
                {visibleAccountRows.length === 0 ? (
                  <p className="p-5 text-sm text-slate-500">Không có dòng TKQC trong kỳ / khoảng ngày đã chọn.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[720px] text-left text-sm">
                      <thead className="bg-slate-50 text-xs text-slate-500">
                        <tr>
                          <th className="px-4 py-3 font-medium">Ngày</th>
                          <th className="px-4 py-3 font-medium">ID TKQC</th>
                          <th className="px-4 py-3 font-medium">Người sử dụng</th>
                          <th className="px-4 py-3 font-medium">Tiền tệ</th>
                          <th className="px-4 py-3 text-right font-medium">Chi tiêu trên TKQC</th>
                          <th className="px-4 py-3 text-right font-medium">Chi phí mua TKQC</th>
                          <th className="px-4 py-3 font-medium">Trạng thái hoạt động</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {visibleAccountRows.map((row) => {
                          const context = accountContext(row, customer, manualAccounts, sheetLinks, manualError);
                          const amount = row.original_spend?.value;
                          return (
                          <tr key={`${customer.source_sheet}:${row.row_number}`} className="align-top">
                            <td className="whitespace-nowrap px-4 py-3 text-slate-700">{row.business_date}</td>
                            <td className="px-4 py-3 text-xs text-slate-800">
                              <span className="font-mono">{row.account_id}</span>
                              <details className="mt-2">
                                <summary className="cursor-pointer text-sky-700">Truy vết</summary>
                                <p>Dòng {row.row_number} · {row.status}{context.assignmentNote ? ` · ${context.assignmentNote}` : ""}</p>
                                {row.cells.filter((cell) => cell.value !== null || cell.formula).map((cell) => (
                                  <p key={cell.address}>{cell.address}: {String(cell.value ?? "—")}{cell.formula ? ` · ${cell.formula}` : ""}</p>
                                ))}
                                {row.missing_inputs.length > 0 && <p>Thiếu đầu vào: {row.missing_inputs.join(", ")}</p>}
                              </details>
                            </td>
                            <td className="px-4 py-3 text-slate-700">{context.user}</td>
                            <td className="px-4 py-3 text-slate-700">{row.account_currency ?? "Chưa xác định"}</td>
                            <td className="whitespace-nowrap px-4 py-3 text-right">{amount == null ? "Chưa xác định" : `${row.account_currency === "VND" ? formatVnd(amount) : sourceText(amount)} ${row.account_currency ?? ""}`}</td>
                            <td className="px-4 py-3 text-right text-xs">{context.cost}</td>
                            <td className="px-4 py-3 text-xs">{context.status}<span className="block text-slate-500">Hiện tại · thủ công</span></td>
                          </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
                {undatedAccountRows.length > 0 && (
                  <div className="border-t border-amber-100 bg-amber-50/60 p-4 sm:p-5">
                    <h3 className="font-medium text-amber-950">
                      Bản ghi có ID TK nhưng thiếu ngày ({undatedAccountRows.length})
                    </h3>
                    <p className="mt-1 text-xs text-amber-900">
                      Số dòng nguồn: {undatedAccountRows.map((row) => row.row_number).join(", ")}. Chỉ các dòng có ID TK được tính ở đây; dòng trống phân cách không được tính là bản ghi. Không đưa các dòng này vào kỳ hoặc biểu đồ cho đến khi ngày nguồn được nhận diện.
                    </p>
                    <div className="mt-3 space-y-3">
                      {undatedAccountRows.map((row) => (
                        <div key={`${customer.source_sheet}:undated:${row.row_number}`} className="rounded-lg border border-amber-200 bg-white p-3">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="font-mono text-xs text-slate-800">
                              {customer.source_sheet} dòng {row.row_number} · ID {row.account_id} · {row.account_currency ?? "currency chưa xác định"}
                            </span>
                            <StatusBadge status="NEEDS_CONFIRMATION" label="Ngày chưa xác định" />
                          </div>
                          <div className="mt-2"><RawCells cells={row.cells} /></div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {(customer.unclassified_rows ?? []).length > 0 && (
                  <div className="border-t border-slate-200 bg-slate-50 p-4 sm:p-5">
                    <h3 className="font-medium text-slate-900">
                      Dòng có dữ liệu chưa phân loại ({customer.unclassified_rows?.length ?? 0})
                    </h3>
                    <p className="mt-1 text-xs text-slate-600">
                      Dòng có giá trị 0 hoặc công thức trả ô trống vẫn được giữ để rà soát; không tự coi là dòng phân cách.
                    </p>
                    <div className="mt-3 space-y-3">
                      {(customer.unclassified_rows ?? []).map((row) => (
                        <div key={`${customer.source_sheet}:unclassified:${row.row_number}`} className="rounded-lg border border-slate-200 bg-white p-3">
                          <div className="font-mono text-xs text-slate-800">
                            {customer.source_sheet} dòng {row.row_number} · ngày {row.business_date ?? "chưa xác định"}
                          </div>
                          <p className="mt-1 text-xs text-slate-600">{row.reason}</p>
                          <div className="mt-2"><RawCells cells={row.cells} /></div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </section>
              </details>

              <details className="rounded-2xl border border-slate-200 bg-white shadow-sm">
                <summary className="cursor-pointer p-4 font-semibold text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-700">Khoản nhận USDT{undatedDeposits.length > 0 ? ` · ${undatedDeposits.length} khoản chưa rõ ngày` : ""}</summary>
              <section className="border-t border-slate-200">
                <div className="border-b border-slate-100 p-4 sm:p-5">
                  <h2 className="font-semibold text-slate-900">Khoản nhận USDT theo từng dòng nguồn</h2>
                  <p className="mt-1 text-xs text-slate-500">
                    Không nhân bản khoản nhận theo số dòng TKQC. Ngày chỉ kế thừa trong vùng merge của Sheet.
                  </p>
                </div>
                {visibleDeposits.length === 0 ? (
                  <p className="p-5 text-sm text-slate-500">
                    {customer.usdt_receipts_state === "NO_RECORDED"
                      ? "Chưa ghi nhận khoản nhận USDT."
                      : "Chưa có khoản nhận USDT được nhận diện trong phạm vi chọn."}
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[720px] text-left text-sm">
                      <thead className="bg-slate-50 text-xs text-slate-500">
                        <tr>
                          <th className="px-4 py-3 font-medium">Ngày</th>
                          <th className="px-4 py-3 text-right font-medium">USDT nguồn</th>
                          <th className="px-4 py-3 text-right font-medium">Tỷ giá nhận nguồn</th>
                          <th className="px-4 py-3 text-right font-medium">VND nguồn</th>
                          <th className="px-4 py-3 font-medium">Ô nguồn</th>
                          <th className="px-4 py-3 font-medium">Mapping</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {visibleDeposits.map((deposit) => (
                          <tr key={`${customer.source_sheet}:${deposit.source_row}`} className="align-top">
                            <td className="whitespace-nowrap px-4 py-3">{deposit.business_date ?? "Chưa xác định"}</td>
                            <td className="px-4 py-3 text-right">{sourceText(deposit.amount_usdt)} USDT</td>
                            <td className="px-4 py-3 text-right">
                              {sourceText(deposit.rate)}
                              {deposit.rate === null ? "" : fieldStatus.usdt_vnd_rate?.status === "CONFIRMED" ? " VND/USDT" : " · đơn vị chưa xác nhận"}
                            </td>
                            <td className="px-4 py-3 text-right">{deposit.amount_vnd === null ? "—" : fieldStatus.usdt_receipt_vnd?.status === "CONFIRMED" ? `${formatVnd(deposit.amount_vnd)} VND` : `${sourceText(deposit.amount_vnd)} · đơn vị chưa xác nhận`}</td>
                            <td className="px-4 py-3 font-mono text-xs">{deposit.source_cells.join(", ") || "—"}</td>
                            <td className="px-4 py-3"><StatusBadge status={deposit.status} /> {deposit.exclusion_reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {undatedDeposits.length > 0 && (
                  <div className="border-t border-amber-100 bg-amber-50/60 p-4 text-sm text-amber-950">
                    <p className="font-medium">Khoản nhận chưa xác định ngày ({undatedDeposits.length})</p>
                    <p className="mt-1 text-xs">Không gán vào kỳ hoặc biểu đồ; ngày và mapping cần được xác nhận.</p>
                    <ul className="mt-2 space-y-1">
                      {undatedDeposits.map((deposit) => (
                        <li key={`${customer.source_sheet}:receipt:${deposit.source_row}`}>
                          {customer.source_sheet} dòng {deposit.source_row} · {sourceText(deposit.amount_usdt)} USDT · giá trị nguồn {fieldStatus.usdt_receipt_vnd?.status === "CONFIRMED" ? formatVnd(deposit.amount_vnd) : sourceText(deposit.amount_vnd)}{fieldStatus.usdt_receipt_vnd?.status === "CONFIRMED" ? " VND" : " (đơn vị chưa xác nhận)"} · tỷ giá {sourceText(deposit.rate)}{fieldStatus.usdt_vnd_rate?.status === "CONFIRMED" ? " VND/USDT" : " (đơn vị chưa xác nhận)"} · ô {deposit.source_cells.join(", ")} · {deposit.status}{deposit.exclusion_reason ? ` · ${deposit.exclusion_reason}` : ""}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </section>
              </details>
            </>
          ) : (
            <section className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
              Chưa có tab khách liên kết đủ bằng chứng trong workbook đã đọc. Không tự suy ra tab khách từ tên gần giống.
            </section>
          )}

          <details ref={detailsRef} open={detailsOpen} onToggle={(event) => setDetailsOpen(event.currentTarget.open)}
            className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
            <summary className="cursor-pointer font-semibold text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-700">Chi tiết dữ liệu</summary>
            <div className="mt-4 space-y-4">
            {metadataDetails}
            {customer && (
              <section className="space-y-2 border-t border-slate-200 pt-4 text-sm text-slate-700">
                <h2 className="font-semibold">Giá trị nguồn và phạm vi</h2>
                <p>Tab {customer.source_sheet} · phạm vi đọc {customer.read_scope ?? "toàn tab"} · mapping {customer.profile_status} · độ đầy đủ {customer.completeness_status ?? "chưa đánh giá"} · ngày đã đọc {customer.observed_date_from ?? "—"} → {customer.observed_date_to ?? "—"} · {customer.period_coverage_note}</p>
                <p>Lợi nhuận theo quy ước bằng phí dịch vụ theo yêu cầu chủ dự án, chưa trừ chi phí mua TKQC; không cộng thêm vào phí. Nạp VND và USDT nhận là hai chỉ tiêu riêng.</p>
                <p>USDT nhận là tổng các khoản hợp lệ có ngày thuộc kỳ chi tiết; khoản chưa rõ ngày và dòng loại trừ được giữ trong mục khoản nhận. Không tạo khoản nhận 0 từ ô trống.</p>
                <p>Chi tiêu gốc theo tiền tệ: {currencyMapText(periodTotals?.spend_original_by_currency) ?? "—"}. Chi phí mua TKQC xem theo ID trong chi tiết TKQC; chưa tổng hợp khi thiếu đơn vị hoặc dữ liệu. Dư nợ bàn giao chưa có mapping; tỷ lệ sự cố chưa xác nhận tử số.</p>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px] text-left text-xs">
                    <thead><tr><th className="p-2">Chỉ số</th><th className="p-2">Ô nguồn</th><th className="p-2">Giá trị thô</th><th className="p-2">Công thức</th><th className="p-2">Trạng thái</th></tr></thead>
                    <tbody>
                      <tr><td className="p-2">Số dư đầu kỳ</td><td className="p-2">{openingBalance?.source ?? "—"}</td><td className="p-2">{openingBalance?.value ?? "—"}</td><td className="p-2">{customer.source_rows?.find((row) => row.row_number === 1)?.cells.find((cell) => cell.address === "J1")?.formula ?? "—"}</td><td className="p-2">{openingBalance?.status ?? "—"}</td></tr>
                      {Object.entries(sourceTotals).map(([field, metric]) => (
                        <tr key={field}><td className="p-2">{field}</td><td className="p-2">{metric.source}</td><td className="p-2">{metric.value ?? "—"}</td><td className="p-2">{metric.formula ?? "—"}</td><td className="p-2">{metric.status}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {(periodTotals?.source_detail_differences ?? []).map((item) => (
                  <p key={item.field}>Chênh lệch {item.field}: {item.source} = {item.source_value}, chi tiết = {item.detail_value}, chênh chính xác = {item.difference}. {item.note}</p>
                ))}
              </section>
            )}
            <SummaryTable report={report} />
          {customer && (customer.issues?.length ?? 0) > 0 && (
            <section className="rounded-2xl border border-amber-200 bg-amber-50 p-4 sm:p-5">
              <h2 className="font-semibold text-amber-950">Chất lượng dữ liệu / trường cần xác nhận</h2>
              <ul className="mt-3 space-y-2 text-sm text-amber-950">
                {customer.issues?.map((issue, index) => (
                  <li key={`${issue.source}:${index}`}>[{issue.severity}] {issue.source}: {issue.message}</li>
                ))}
              </ul>
            </section>
          )}

          {(report.issues.length > 0 || Object.keys(fieldStatus).length > 0) && (
            <section className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-5">
              <h2 className="font-semibold text-slate-900">Nguồn, mapping và vấn đề cần lưu ý</h2>
              {customer && (
                <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {Object.entries(fieldStatus).map(([field, state]) => (
                    <div key={field} className="rounded-lg border border-slate-100 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-sm font-medium text-slate-800">{field.replaceAll("_", " ")}</span>
                        <StatusBadge status={state.status} />
                      </div>
                      <p className="mt-1 text-xs text-slate-600">{state.reason}</p>
                      {state.source && <p className="mt-1 font-mono text-[11px] text-slate-400">{state.source}</p>}
                    </div>
                  ))}
                </div>
              )}
              {report.issues.length > 0 && (
                <ul className="mt-4 space-y-2 text-sm text-amber-900">
                  {report.issues.map((issue, index) => (
                    <li key={`${issue.source}:${index}`}>[{issue.severity}] {issue.source}: {issue.message}</li>
                  ))}
                </ul>
              )}
              {report.notes.map((note) => <p key={note} className="mt-2 text-xs text-slate-500">{note}</p>)}
            </section>
          )}
            </div>
          </details>
        </>
      )}
      {!report && (
        <details ref={detailsRef} open={detailsOpen} onToggle={(event) => setDetailsOpen(event.currentTarget.open)}
          className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <summary className="cursor-pointer font-semibold text-slate-900">Chi tiết dữ liệu</summary>
          <div className="mt-4">{metadataDetails}</div>
        </details>
      )}
    </div>
  );
}
