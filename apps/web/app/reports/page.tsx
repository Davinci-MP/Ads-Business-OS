"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";

import { fetchJson } from "../../lib/api";
import { loadPref, savePref } from "../../lib/prefs";
import { formatVnd } from "../../lib/vnd.mjs";
import SheetsSourceReportView from "./sheets-source-report";
import WalletBalanceCard from "../wallet-balance-card";

/* ============================ Kiểu dữ liệu từ API thực ============================ */

type MoneyBlock = {
  amount: number | null;
  currency: string | null;
  data_state: string;
  by_currency?: Record<string, number>;
  note?: string;
  reason?: string;
};

type DepositsBlock = {
  amount: number | null;
  currency: string;
  count: number;
  data_state: string;
};

type KPIBlock = {
  window: { from: string | null; to: string | null };
  company_data_state: string;
  coverage: { customers_with_data: number; customers_total: number };
  meta_source_label: string;
  meta_mode: string;
  note: string;
  meta_spend: MoneyBlock;
  service_fee_revenue: MoneyBlock;
  service_fee_revenue_by_currency: Record<string, number>;
  deposits: DepositsBlock;
  account_costs: MoneyBlock;
  operating_costs: MoneyBlock;
  profit_provisional: MoneyBlock & { note: string };
  profit_final: { amount: number | null; data_state: string };
  billing_total: MoneyBlock;
  receivable: { amount: number | null; data_state: string; note: string };
  customers_checked: number;
  customers_unchecked: number;
};

type DailyRow = {
  business_date: string;
  customer_id: number | null;
  customer_name: string | null;
  meta_spend: number;
  manual_spend: number;
  fee: number;
  billing_total: number;
  meta_by_currency: Record<string, number>;
  manual_by_currency: Record<string, number>;
  fee_by_currency: Record<string, number>;
  billing_by_currency: Record<string, number>;
  meta_source: string;
  campaign_count: number;
};

type ChartRow = {
  business_date: string;
  meta_by_currency: Record<string, number>;
  manual_by_currency: Record<string, number>;
  fee_by_currency: Record<string, number>;
  billing_by_currency: Record<string, number>;
};

type DailyPayload = {
  rows: DailyRow[];
  chart_rows: ChartRow[];
  meta_source_label: string;
  meta_mode: string;
  note: string;
};

type TransactionRow = {
  id: number;
  tx_hash: string;
  amount: string;
  currency: string;
  occurred_at: string;
  status: string;
  customer_id: number | null;
  customer_name: string | null;
};

type TransactionsPayload = {
  rows: TransactionRow[];
  source: string;
};

type CustomerRef = { id: number; name: string };
type Range =
  | { kind: "today" }
  | { kind: "yesterday" }
  | { kind: "day"; value: string }
  | { kind: "range"; from: string; to: string }
  | { kind: "month"; value: string };

/* ============================ Helpers ============================ */

function isoDay(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

function rangeFrom(kind: Range): { from: string | null; to: string | null } {
  switch (kind.kind) {
    case "today":
      return { from: isoDay(0), to: isoDay(0) };
    case "yesterday":
      return { from: isoDay(-1), to: isoDay(-1) };
    case "day":
      return { from: kind.value, to: kind.value };
    case "range":
      return { from: kind.from, to: kind.to };
    case "month": {
      const [y, m] = kind.value.split("-");
      const last = new Date(Number(y), Number(m), 0).getDate();
      return { from: `${kind.value}-01`, to: `${kind.value}-${String(last).padStart(2, "0")}` };
    }
    default:
      return { from: null, to: null };
  }
}

function fmt(value: number | null | undefined, currency: string | null): string {
  if (value === null || value === undefined) return "—";
  const formatted = currency === "VND" ? formatVnd(value) : value.toLocaleString("vi-VN", { maximumFractionDigits: 2 });
  return currency ? `${formatted} ${currency}` : formatted;
}

function fmtTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("vi-VN", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "Asia/Ho_Chi_Minh",
  });
}

function fmtByCurrency(byCur: Record<string, number> | undefined | null): string {
  if (!byCur) return "";
  const parts = Object.entries(byCur)
    .map(([cur, v]) => fmt(v, cur));
  return parts.length === 0 ? "chưa có dữ liệu phí trong kỳ" : parts.join(" · ");
}

function stateBadgeClass(state: string): string {
  const s = (state || "").toLowerCase();
  if (s.includes("đầy đủ")) return "border-adsos-ok/20 bg-adsos-ok/10 text-adsos-ok";
  if (s.includes("tạm tính")) return "border-adsos-warn/20 bg-adsos-warn/10 text-adsos-warn";
  if (s.includes("chưa đủ")) return "border-slate-200 bg-slate-50 text-slate-600";
  if (s.includes("một phần")) return "border-adsos-warn/20 bg-adsos-warn/10 text-adsos-warn";
  if (s.includes("đã chốt")) return "border-adsos-ok/20 bg-adsos-ok/10 text-adsos-ok";
  return "border-slate-200 bg-slate-50 text-slate-600";
}

function transactionStatusClass(status: string): string {
  if (status === "MATCHED") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "UNMATCHED") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-slate-200 bg-slate-50 text-slate-600";
}

/* ============================ Thành phần UI ============================ */

function StateBadge({ state }: { state: string }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded border text-xs font-medium ${stateBadgeClass(state)}`}>
      {state}
    </span>
  );
}

function StatCard({
  title,
  value,
  currency,
  state,
  multiCurrency,
  detail,
}: {
  title: string;
  value: number | null;
  currency: string | null;
  state: string;
  multiCurrency?: Record<string, number>;
  detail?: string;
}) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-medium text-slate-600">{title}</h3>
        {!["đầy đủ", "đã chốt"].includes(state.toLowerCase()) && <StateBadge state={state} />}
      </div>
      <div className={`text-2xl font-bold ${value !== null && value < 0 ? "text-rose-700" : "text-adsos-slate"}`}>{fmt(value, currency)}</div>
      {multiCurrency && Object.keys(multiCurrency).length > 0 && (
        <p className="text-xs text-slate-500 mt-2">{fmtByCurrency(multiCurrency)}</p>
      )}
      {detail && <details><summary>Chi tiết dữ liệu</summary><p>{detail}</p></details>}
    </div>
  );
}

function Empty({ title }: { title: string }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-8 text-center">
      <p className="text-slate-500 text-sm">{title}</p>
    </div>
  );
}

function ChartCard({
  data,
  currency,
  currencies,
  loading,
  onCurrencyChange,
}: {
  data: { date: string; metaSpend: number | null; manualSpend: number | null; fee: number | null }[];
  currency: string | null;
  currencies: string[];
  loading: boolean;
  onCurrencyChange: (currency: string) => void;
}) {
  const hasValues = data.some((row) => row.metaSpend != null || row.manualSpend != null || row.fee != null);
  if (loading) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-5">
        <div className="h-5 w-64 rounded bg-slate-200 animate-pulse mb-5" />
        <div className="h-[300px] w-full rounded-lg bg-slate-100 animate-pulse" />
      </div>
    );
  }

  if (!hasValues || !currency) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-slate-800 mb-3">Chi tiêu và phí dịch vụ theo ngày</h3>
        <Empty title="Chưa có dữ liệu biểu đồ trong kỳ đã chọn." />
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <div>
          <h3 className="text-base font-semibold text-slate-900">Chi tiêu và phí dịch vụ theo ngày</h3>
          <p className="text-xs text-slate-500 mt-1">Dữ liệu tổng hợp từ Backend; mỗi biểu đồ chỉ dùng một đơn vị tiền.</p>
        </div>
        {currencies.length > 1 && (
          <label className="flex items-center gap-2 text-xs font-medium text-slate-600">
            Đơn vị
            <select
              aria-label="Đơn vị tiền trên biểu đồ"
              value={currency}
              onChange={(event) => onCurrencyChange(event.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            >
              {currencies.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
        )}
      </div>
      <div className="h-[300px] w-full">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data} margin={{ top: 12, right: 16, left: 8, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#66707d" }} />
            <YAxis tickFormatter={(value) => fmt(value, currency)} tick={{ fontSize: 11, fill: "#66707d" }} />
            <Tooltip
              content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null;
                return (
                  <div className="rounded-lg border border-slate-200 bg-white p-3 text-xs shadow-lg">
                    <div className="font-semibold text-slate-700 mb-2">{label}</div>
                    {payload.map((item) => (
                      <div key={String(item.dataKey)} className="flex justify-between gap-5">
                        <span className="text-slate-500">{item.name}</span>
                        <span className="font-semibold text-slate-900">{fmt(typeof item.value === "number" ? item.value : null, currency)}</span>
                      </div>
                    ))}
                  </div>
                );
              }}
            />
            <Legend />
            <Line connectNulls={false} type="monotone" dataKey="metaSpend" name="Chi tiêu Meta" stroke="#16324f" strokeWidth={2} dot={false} />
            <Line connectNulls={false} type="monotone" dataKey="manualSpend" name="Chi tiêu nhập tay" stroke="#0f766e" strokeWidth={2} dot={false} />
            <Line connectNulls={false} type="monotone" dataKey="fee" name="Phí dịch vụ" stroke="#d97706" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-slate-500 mt-2">
        Phí dịch vụ là doanh thu phí, không phải tiền khách nạp. Không quy đổi hoặc cộng chéo tiền tệ.
      </p>
    </div>
  );
}

/* ============================ Trang ============================ */

export default function ReportsPage() {
  const [reportSource, setReportSource] = useState<"system" | "sheets">(
    () => (loadPref("reports.source", "system") === "sheets" ? "sheets" : "system"),
  );
  const [kind, setKind] = useState<Range["kind"]>(() => {
    const saved = loadPref("reports.kind", "today");
    return saved === "day" || saved === "range" || saved === "month" ? saved : "today";
  });
  const [dayValue, setDayValue] = useState(() => loadPref("reports.day", isoDay(0)));
  const [fromValue, setFromValue] = useState(() => loadPref("reports.from", isoDay(-7)));
  const [toValue, setToValue] = useState(() => loadPref("reports.to", isoDay(0)));
  const [monthValue, setMonthValue] = useState(() => loadPref("reports.month", loadPref("reports.day", isoDay(0)).slice(0, 7)));
  const [customerId, setCustomerId] = useState<string>(() => loadPref("reports.customer", ""));
  const [customers, setCustomers] = useState<CustomerRef[]>([]);

  useEffect(() => {
    savePref("reports.source", reportSource);
    savePref("reports.kind", kind);
    savePref("reports.day", dayValue);
    savePref("reports.from", fromValue);
    savePref("reports.to", toValue);
    savePref("reports.month", monthValue);
    savePref("reports.customer", customerId);
  }, [reportSource, kind, dayValue, fromValue, toValue, monthValue, customerId]);

  // KPI region (cards)
  const [kpi, setKpi] = useState<KPIBlock | null>(null);
  const [kpiError, setKpiError] = useState<string | null>(null);
  const [kpiLoading, setKpiLoading] = useState(false);

  // Daily region (chart + table)
  const [rows, setRows] = useState<DailyRow[]>([]);
  const [chartRows, setChartRows] = useState<ChartRow[]>([]);
  const [metaColumn, setMetaColumn] = useState<{ meta_mode: string; meta_source_label: string; note: string } | null>(null);
  const [dailyError, setDailyError] = useState<string | null>(null);
  const [dailyLoading, setDailyLoading] = useState(false);

  const [transactions, setTransactions] = useState<TransactionRow[]>([]);
  const [transactionsError, setTransactionsError] = useState<string | null>(null);
  const [transactionsLoading, setTransactionsLoading] = useState(true);

  const requestId = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const transactionRequestId = useRef(0);

  useEffect(() => {
    fetchJson<CustomerRef[]>("/customers")
      .then((data) => setCustomers(Array.isArray(data) ? data : []))
      .catch(() => setCustomers([]));
  }, []);

  const buildQuery = useCallback(
    (range: Range) => {
      const { from, to } = rangeFrom(range);
      const qs = new URLSearchParams();
      if (from) qs.set("from", from);
      if (to) qs.set("to", to);
      if (customerId) qs.set("customer_id", customerId);
      return qs.toString();
    },
    [customerId],
  );

  const withGuard = useCallback(
    (
      expectedId: number,
      promise: Promise<unknown>,
      onData: (d: unknown) => void,
      onError: (e: unknown) => void,
    ) => {
      return promise
        .then((data) => {
          if (expectedId !== requestId.current) return;
          onData(data);
        })
        .catch((e) => {
          if (expectedId !== requestId.current) return;
          if (e instanceof DOMException && e.name === "AbortError") return;
          onError(e);
        });
    },
    [],
  );

  const load = useCallback(async () => {
    const id = ++requestId.current;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    // Xóa dữ liệu kỳ cũ trước khi tải mới: không hiển thị số kỳ cũ dưới header kỳ mới.
    setKpi(null);
    setKpiError(null);
    setRows([]);
    setChartRows([]);
    setMetaColumn(null);
    setKpiLoading(true);
    setDailyLoading(true);
    setDailyError(null);

    const range: Range =
      kind === "day"
        ? { kind, value: dayValue }
        : kind === "range"
          ? { kind, from: fromValue, to: toValue }
          : kind === "month"
            ? { kind, value: monthValue }
            : { kind };
    const { from, to } = rangeFrom(range);
    if (from && to && from > to) {
      setKpiLoading(false);
      setDailyLoading(false);
      setKpiError("Từ ngày không được sau đến ngày.");
      setDailyError("Từ ngày không được sau đến ngày.");
      return;
    }
    const qs = buildQuery(range);
    const kpiUrl = `/reports/kpi?${qs}`;
    const dailyUrl = `/reports/daily?${qs}`;

    await Promise.all([
      withGuard(
        id,
        fetchJson<KPIBlock>(kpiUrl, { signal: controller.signal }),
        (data) => {
          setKpi(data as KPIBlock);
          setKpiLoading(false);
        },
        (e) => {
          setKpiError(e instanceof Error ? e.message : String(e));
          setKpiLoading(false);
        },
      ),
      withGuard(
        id,
        fetchJson<DailyPayload>(dailyUrl, { signal: controller.signal }),
        (data) => {
          const d = data as DailyPayload;
          setRows(d.rows);
          setChartRows(d.chart_rows);
          setMetaColumn({
            meta_mode: d.meta_mode,
            meta_source_label: d.meta_source_label,
            note: d.note,
          });
          setDailyLoading(false);
        },
        (e) => {
          setDailyError(e instanceof Error ? e.message : String(e));
          setDailyLoading(false);
        },
      ),
    ]);
  }, [kind, dayValue, fromValue, toValue, monthValue, customerId, buildQuery, withGuard]);

  useEffect(() => {
    if (reportSource === "system") {
      void load();
      return;
    }
    controllerRef.current?.abort();
    requestId.current += 1;
    setKpi(null);
    setRows([]);
    setChartRows([]);
    setMetaColumn(null);
    setKpiError(null);
    setDailyError(null);
    setKpiLoading(false);
    setDailyLoading(false);
  }, [reportSource, load]);

  const loadTransactions = useCallback(async () => {
    const request = ++transactionRequestId.current;
    if (reportSource !== "system") {
      setTransactions([]);
      setTransactionsError(null);
      setTransactionsLoading(false);
      return;
    }
    setTransactionsLoading(true);
    setTransactionsError(null);
    const query = new URLSearchParams({ limit: "5" });
    if (customerId) query.set("customer_id", customerId);
    try {
      const data = await fetchJson<TransactionsPayload>(`/reports/transactions?${query.toString()}`);
      if (request === transactionRequestId.current) setTransactions(data.rows);
    } catch (error) {
      if (request === transactionRequestId.current) {
        setTransactionsError(error instanceof Error ? error.message : String(error));
      }
    } finally {
      if (request === transactionRequestId.current) setTransactionsLoading(false);
    }
  }, [customerId, reportSource]);

  useEffect(() => {
    void loadTransactions();
  }, [loadTransactions]);

  const chartCurrencies = Array.from(new Set(
    chartRows.flatMap((row) => [
      ...Object.keys(row.meta_by_currency),
      ...Object.keys(row.manual_by_currency),
      ...Object.keys(row.fee_by_currency),
    ]),
  )).sort();
  const [selectedCurrency, setSelectedCurrency] = useState("USD");
  const chartCurrency = chartCurrencies.includes(selectedCurrency)
    ? selectedCurrency
    : chartCurrencies[0] ?? null;
  const chartData = chartRows.map((row) => ({
    date: row.business_date,
    metaSpend: row.meta_by_currency[chartCurrency ?? ""] ?? null,
    manualSpend: row.manual_by_currency[chartCurrency ?? ""] ?? null,
    fee: row.fee_by_currency[chartCurrency ?? ""] ?? null,
  }));

  // ---------- render ----------
  const hasKpiData = kpi !== null;
  const rangeLabel = (() => {
    if (kpi?.window.from && kpi.window.to) return `${kpi.window.from} → ${kpi.window.to}`;
    return "toàn bộ dữ liệu";
  })();
  const systemPartial = kpi && /một phần|chưa đủ/i.test(kpi.company_data_state);
  const systemMock = metaColumn?.meta_source_label === "MOCK_DATA";

  return (
    <div className="w-full space-y-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-slate-900">Tổng quan tài chính</h1>
          </div>
          <div className="flex flex-col gap-2 sm:items-end">
            <label className="flex items-center gap-2 text-xs font-medium text-slate-500">
              Nguồn báo cáo
              <select
                value={reportSource}
                onChange={(event) => setReportSource(event.target.value as "system" | "sheets")}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800"
              >
                <option value="system">Nguồn hệ thống (Meta + Manual)</option>
                <option value="sheets">Google Sheets</option>
              </select>
            </label>
          </div>
        </div>
      </div>

      {reportSource === "sheets" ? <SheetsSourceReportView /> : (
      <>
      {/* Filter bar */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm">
          <label className="block text-xs font-medium text-slate-500 mb-2">Kỳ báo cáo</label>
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as Range["kind"])}
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-adsos-slate focus:border-adsos-slate outline-none"
          >
            <option value="today">Hôm nay</option>
            <option value="yesterday">Hôm qua</option>
            <option value="day">Ngày tùy chọn</option>
            <option value="range">Khoảng ngày</option>
            <option value="month">Tháng</option>
          </select>
        </div>
        {kind === "day" && (
          <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm">
            <label className="block text-xs font-medium text-slate-500 mb-2">Ngày</label>
            <input
              type="date"
              value={dayValue}
              onChange={(e) => setDayValue(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-adsos-slate focus:border-adsos-slate outline-none"
            />
          </div>
        )}
        {kind === "range" && (
          <>
            <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm">
              <label className="block text-xs font-medium text-slate-500 mb-2">Từ ngày</label>
              <input
                type="date"
                value={fromValue}
                onChange={(e) => setFromValue(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-adsos-slate focus:border-adsos-slate outline-none"
              />
            </div>
            <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm">
              <label className="block text-xs font-medium text-slate-500 mb-2">Đến ngày</label>
              <input
                type="date"
                value={toValue}
                onChange={(e) => setToValue(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-adsos-slate focus:border-adsos-slate outline-none"
              />
            </div>
          </>
        )}
        {kind === "month" && (
          <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm">
            <label className="block text-xs font-medium text-slate-500 mb-2">Tháng</label>
            <input
              type="month"
              value={monthValue}
              onChange={(e) => setMonthValue(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-adsos-slate focus:border-adsos-slate outline-none"
            />
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-6">
        <label htmlFor="report-customer" className="text-xs font-medium text-slate-500">Lọc bảng và giao dịch theo khách:</label>
        <select
          id="report-customer"
          value={customerId}
          onChange={(e) => setCustomerId(e.target.value)}
          className="border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-adsos-slate focus:border-adsos-slate outline-none"
        >
          <option value="">Toàn bộ khách hàng</option>
          {customers.map((c) => (
            <option key={c.id} value={String(c.id)}>
              {c.name}
            </option>
          ))}
        </select>
        <button
          onClick={load}
          disabled={kpiLoading || dailyLoading}
          className="inline-flex items-center gap-1.5 bg-adsos-slate hover:bg-adsos-slateHover text-white text-sm font-medium rounded-lg px-4 py-2 transition disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {kpiLoading || dailyLoading ? "Đang tải…" : "Cập nhật"}
        </button>
      </div>

      {(kpiError || dailyError || transactionsError || systemPartial || systemMock) && (
        <details className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
          <summary className="cursor-pointer font-medium">{kpiError || dailyError || transactionsError ? "Một phần báo cáo không tải được." : systemPartial ? "Báo cáo chưa đầy đủ." : ""} {systemMock && "Dữ liệu Meta đang ở chế độ thử nghiệm."} Xem chi tiết</summary>
          {systemMock && <p className="mt-2">Meta đang ở chế độ thử nghiệm, không phải dữ liệu live.</p>}
          {systemPartial && <p className="mt-2">Trạng thái tổng hợp: {kpi?.company_data_state}.</p>}
          {kpiError && <p className="mt-2">Chỉ số: {kpiError} <button type="button" className="underline" onClick={load}>Thử lại</button></p>}
          {dailyError && <p className="mt-2">Báo cáo ngày: {dailyError} <button type="button" className="underline" onClick={load}>Thử lại</button></p>}
          {transactionsError && <p className="mt-2">Giao dịch USDT: {transactionsError} <button type="button" className="underline" onClick={loadTransactions}>Thử lại</button></p>}
        </details>
      )}

      {/* KPI cards */}
      <section className="mb-8">
        <div className="flex items-end justify-between gap-3 mb-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Chỉ số tài chính</h2>
            <p className="text-xs text-slate-500 mt-1">{rangeLabel}</p>
          </div>
          <span className="hidden sm:inline text-xs text-slate-500">Ad Spend ≠ doanh thu phí ≠ tiền khách nạp</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {hasKpiData && kpi ? (
            <>
              <StatCard
                title="Chi tiêu Meta Ads"
                value={kpi.meta_spend.amount}
                currency={kpi.meta_spend.currency}
                state={kpi.meta_spend.data_state}
                multiCurrency={kpi.meta_spend.by_currency}
              />
              <StatCard
                title="Doanh thu phí dịch vụ"
                value={kpi.service_fee_revenue.amount}
                currency={kpi.service_fee_revenue.currency}
                state={kpi.service_fee_revenue.data_state}
                multiCurrency={kpi.service_fee_revenue.by_currency}
              />
              <StatCard
                title="Tiền khách nạp"
                value={kpi.deposits.amount}
                currency={kpi.deposits.currency}
                state={kpi.deposits.data_state}
              />
              <StatCard
                title="Chi phí tài khoản"
                value={kpi.account_costs.amount}
                currency={kpi.account_costs.currency}
                state={kpi.account_costs.data_state}
                detail={kpi.account_costs.reason}
              />
              <StatCard
                title="Chi phí vận hành"
                value={kpi.operating_costs.amount}
                currency={kpi.operating_costs.currency}
                state={kpi.operating_costs.data_state}
                multiCurrency={kpi.operating_costs.by_currency}
              />
              <StatCard
                title="Lợi nhuận ròng đã chốt"
                value={kpi.profit_final.amount}
                currency={null}
                state={kpi.profit_final.data_state}
              />
            </>
          ) : (
            <>
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <div key={i} className="bg-white border border-slate-200 rounded-xl p-5 animate-pulse">
                  <div className="h-4 bg-slate-200 rounded w-3/4 mb-2"></div>
                  <div className="h-10 bg-slate-200 rounded w-full"></div>
                  <div className="h-6 bg-slate-200 rounded w-2/3 mt-3"></div>
                </div>
              ))}
            </>
          )}
        </div>
      </section>

      <details className="mb-6 rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-700">
        <summary className="cursor-pointer font-medium">Chi tiết dữ liệu</summary>
        <div className="mt-3 space-y-2">
          <p>Doanh thu phí là khoản riêng, không phải chi tiêu Meta hoặc tiền khách nạp. Tiền nạp USDT TRC20 đã khớp được giữ đơn vị riêng.</p>
          <p>Chi phí tài khoản là chi phí mua TKQC; chi phí vận hành chưa có nguồn ghi nhận. Lợi nhuận ròng đã chốt không được thay bằng lợi nhuận tạm tính.</p>
          <p>Chưa có so sánh tăng trưởng kỳ trước; không cộng chéo tiền tệ. {kpi?.note}</p>
          <p>Độ phủ: {kpi ? `${kpi.coverage.customers_with_data}/${kpi.coverage.customers_total} khách` : "—"} · Meta: {metaColumn?.meta_mode ?? "—"} · {metaColumn?.meta_source_label ?? "—"}. Báo cáo hệ thống chưa cung cấp thời điểm cập nhật dữ liệu.</p>
          <Link className="underline" href="/sheets">Mở trang Sheets chi tiết / mapping</Link>
          {metaColumn?.note && <p>{metaColumn.note}</p>}
        </div>
      </details>

      {/* Chart */}
      <section className="mb-8">
        {dailyError ? null : (
          <ChartCard
            data={chartData}
            currency={chartCurrency}
            currencies={chartCurrencies}
            loading={dailyLoading}
            onCurrencyChange={setSelectedCurrency}
          />
        )}
      </section>

      {/* Recent transactions */}
      <details className="mb-8 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <summary className="cursor-pointer font-semibold">Giao dịch nhận USDT gần đây</summary>
      <section className="mt-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Giao dịch nhận USDT gần đây</h2>
            <p className="mt-1 text-xs text-slate-500">Nguồn: bản ghi hiện có trong Backend; không tạo giao dịch giả.</p>
          </div>
          <span className="text-xs text-slate-500">Tối đa 5 giao dịch</span>
        </div>
        {transactionsLoading ? (
          <div className="space-y-3" aria-label="Đang tải giao dịch">
            {[1, 2, 3].map((item) => <div key={item} className="h-10 rounded-lg bg-slate-100 animate-pulse" />)}
          </div>
        ) : transactions.length === 0 ? (
          <Empty title="Chưa có giao dịch USDT được ghi nhận trong Backend." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-sm">
              <thead>
                <tr className="bg-slate-50 text-left">
                  <th className="px-4 py-3 font-medium text-slate-600 border-b border-slate-200">Thời điểm</th>
                  <th className="px-4 py-3 font-medium text-slate-600 border-b border-slate-200">Khách</th>
                  <th className="px-4 py-3 font-medium text-slate-600 border-b border-slate-200">Giao dịch</th>
                  <th className="px-4 py-3 font-medium text-slate-600 border-b border-slate-200 text-right">Số tiền</th>
                  <th className="px-4 py-3 font-medium text-slate-600 border-b border-slate-200">Trạng thái</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {transactions.map((transaction) => (
                  <tr key={transaction.id} className="hover:bg-slate-50/70">
                    <td className="px-4 py-3 text-slate-600">{fmtTime(transaction.occurred_at)}</td>
                    <td className="px-4 py-3 text-slate-700">{transaction.customer_name ?? "Chưa xác định"}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500">{transaction.tx_hash}</td>
                    <td className="px-4 py-3 text-right font-medium text-slate-900">{transaction.amount} {transaction.currency}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${transactionStatusClass(transaction.status)}`}>
                        {transaction.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      </details>

      {/* Table */}
      <details className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <summary className="cursor-pointer font-semibold">Chi tiết theo ngày / khách</summary>
      <section className="mt-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-3">
          <div>
            <h2 className="text-sm font-bold text-slate-700">Chi tiêu theo ngày / khách</h2>
            <p className="text-xs text-slate-600">
              Ngày = ngày nghiệp vụ từ mã tên campaign (D-026) + manual_reviews. Cột $ là phần USD;
              phần tiền khác hiển thị theo đơn vị riêng, không cộng chéo.
            </p>
          </div>
          <Link href="/reviews" className="inline-flex items-center gap-1.5 text-sm font-medium text-adsos-slate hover:text-adsos-slateHover underline-offset-4 hover:underline">
            → Đến đối chiếu thủ công
          </Link>
        </div>

        {dailyLoading ? (
          <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5" aria-label="Đang tải báo cáo ngày">
            {[1, 2, 3, 4].map((item) => <div key={item} className="h-8 rounded bg-slate-100 animate-pulse" />)}
          </div>
        ) : rows.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-xl p-8 text-center">
            <p className="text-slate-500 text-sm">Không có dữ liệu trong khung — KHÔNG hiển thị 0 giả.</p>
            {metaColumn?.note && <p className="text-xs text-slate-400 mt-2">{metaColumn.note}</p>}
          </div>
        ) : (
          <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-sm border-collapse">
              <thead>
                <tr className="bg-slate-50 text-left">
                  <th className="px-4 py-3 font-medium text-slate-600 border-b border-slate-200">Ngày nghiệp vụ</th>
                  <th className="px-4 py-3 font-medium text-slate-600 border-b border-slate-200">Khách</th>
                  <th className="px-4 py-3 font-medium text-slate-600 border-b border-slate-200 text-right">Chi tiêu Meta</th>
                  <th className="px-4 py-3 font-medium text-slate-600 border-b border-slate-200 text-right">Chi tiêu Manual</th>
                  <th className="px-4 py-3 font-medium text-slate-600 border-b border-slate-200 text-right">Phí dịch vụ</th>
                  <th className="px-4 py-3 font-medium text-slate-600 border-b border-slate-200 text-right">Tổng billing</th>
                  <th className="px-4 py-3 font-medium text-slate-600 border-b border-slate-200 text-center">Campaign</th>
                  <th className="px-4 py-3 font-medium text-slate-600 border-b border-slate-200">Nguồn</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((row) => {
                  const nonUsdManual = Object.entries(row.manual_by_currency ?? {}).filter(
                    ([cur]) => cur !== "USD",
                  );
                  const nonUsdFee = Object.entries(row.fee_by_currency ?? {}).filter(
                    ([cur]) => cur !== "USD",
                  );
                  const nonUsdBilling = Object.entries(row.billing_by_currency ?? {}).filter(
                    ([cur]) => cur !== "USD",
                  );
                  return (
                    <tr key={`${row.business_date}:${row.customer_id}`} className="hover:bg-slate-50/50 transition">
                      <td className="px-4 py-3 text-slate-700 border-b border-slate-100">{row.business_date}</td>
                      <td className="px-4 py-3 text-slate-700 border-b border-slate-100">{row.customer_name ?? "—"}</td>
                      <td className="px-4 py-3 text-right text-slate-700 border-b border-slate-100">
                        {row.meta_by_currency.USD === undefined ? "—" : fmt(row.meta_by_currency.USD, "$")}
                      </td>
                      <td className="px-4 py-3 text-right text-slate-700 border-b border-slate-100">
                        {row.manual_by_currency.USD === undefined ? "—" : fmt(row.manual_by_currency.USD, "$")}
                        {nonUsdManual.length > 0 && (
                          <div className="mt-1 text-xs text-slate-500">
                            {nonUsdManual.map(([cur, v]) => fmt(v, cur)).join(" · ")}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right text-slate-700 border-b border-slate-100">
                        {row.fee_by_currency.USD === undefined ? "—" : fmt(row.fee_by_currency.USD, "$")}
                        {nonUsdFee.length > 0 && (
                          <div className="mt-1 text-xs text-slate-500">
                            {nonUsdFee.map(([cur, v]) => fmt(v, cur)).join(" · ")}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right text-slate-700 border-b border-slate-100">
                        {row.billing_by_currency.USD === undefined ? "—" : fmt(row.billing_by_currency.USD, "$")}
                        {nonUsdBilling.length > 0 && (
                          <div className="mt-1 text-xs text-slate-500">
                            {nonUsdBilling.map(([cur, v]) => fmt(v, cur)).join(" · ")}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right text-slate-700 border-b border-slate-100 text-center">
                        {Object.keys(row.meta_by_currency).length === 0 ? "—" : row.campaign_count}
                      </td>
                      <td className="px-4 py-3 text-slate-700 border-b border-slate-100">
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs border border-slate-200 bg-slate-50 text-slate-600">
                          {row.meta_source}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            </div>
            <p className="px-4 py-3 text-xs text-slate-500 border-t border-slate-100">{metaColumn?.note ?? ""}</p>
          </div>
        )}
      </section>
      </details>
      </>
      )}
      <WalletBalanceCard />
    </div>
  );
}
