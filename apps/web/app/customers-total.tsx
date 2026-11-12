"use client";

import { useCallback, useEffect, useState } from "react";
import {
  fetchJson,
  postJson,
  type ClientDailyBreakdownItem,
  type DailyBreakdownItem,
  type DailySummary,
  type SheetSyncAttempt,
} from "../lib/api";
import { formatBalanceVnd, formatVnd } from "../lib/vnd.mjs";
import { loadPref, savePref } from "../lib/prefs";
import { dateInReportMonth } from "../lib/report-date.mjs";
import ViaSheetWritebackModal from "../components/ViaSheetWritebackModal";
import { MonoIcon } from "../components/mono-icon";

type Metric = {
  basis?: string;
  source?: string | null;
  difference?: string | null;
  value: string | null;
  status: string;
  complete_customers: number;
  total_customers: number;
  missing_customers: string[];
  contributions: { customer: string; source: string | string[] | null; value: string }[];
};

type Flow = {
  value: string | null;
  status: string;
  complete_months: number;
  total_months: number;
  missing_or_partial_months: string[];
  contributions: { period: string; value: string }[];
};

type Month = {
  period: string;
  state:
    | "MISSING_SOURCE"
    | "MISSING_SNAPSHOT"
    | "CLOSED"
    | "PROVISIONAL"
    | "CONFLICTING_CLOSURES"
    | "NOT_CLOSED"
    | "NOT_CLOSED_NO_SOURCE"
    | "CURRENT_AFTER_CLOSURE";
  source_id?: number;
  active_source_id?: number | null;
  name?: string;
  snapshot_id?: number;
  closure_snapshot_id?: number | null;
  closed_at?: string | null;
  closure_note?: string | null;
  read_at?: string;
  quality?: string;
  sync_enabled?: boolean;
  latest_read_at?: string | null;
  last_attempt?: { status: string; started_at: string; error: string | null } | null;
  metrics?: Record<string, Metric>;
  period_mismatches?: { customer: string; periods: string[] }[];
};

type YearSummary = {
  year: number;
  basis: string;
  scope?: string;
  months: Month[];
  months_with_data: number;
  flows: Record<string, Flow>;
  opening_balance: { period: string; metric: Metric } | null;
  closing_balance: { period: string; metric: Metric } | null;
  daily_breakdown?: DailyBreakdownItem[];
  client_daily_breakdown?: ClientDailyBreakdownItem[];
  daily_summary?: DailySummary;
};

const fields = [
  { key: "budget_deposits_vnd", label: "Nạp trong kỳ", theme: "sky" },
  { key: "spend_vnd", label: "Chi tiêu quảng cáo", theme: "white" },
  { key: "fee", label: "Phí khách hàng", theme: "emerald" },
  { key: "billing_total", label: "Tổng chi tiêu gồm phí", theme: "indigo" },
  { key: "usdt_received", label: "USDT nhận", usdt: true, theme: "violet" },
  { key: "usdt_refunded", label: "USDT hoàn", usdt: true, theme: "teal" },
  { key: "usdt_net", label: "USDT ròng", usdt: true, theme: "violet" },
];

function usdtText(value: string) {
  const match = value.match(/^(-?)(\d+)(\.\d+)?$/);
  return match
    ? `${match[1]}${match[2].replace(/\B(?=(\d{3})+(?!\d))/g, ".")}${
        match[3] ? `,${match[3].slice(1)}` : ""
      }`
    : value;
}

function money(value: string | null | undefined, usdt = false, balance = false) {
  if (value == null) return "—";
  return `${
    usdt ? usdtText(value) : balance ? formatBalanceVnd(value) : formatVnd(value)
  } ${usdt ? "USDT" : "đ"}`;
}

function stateText(month: Month) {
  if (month.state === "MISSING_SOURCE") return "Chưa có nguồn";
  if (month.state === "MISSING_SNAPSHOT") return "Chưa có bản lưu";
  if (month.state === "CONFLICTING_CLOSURES") return "Có nhiều bản chốt · cần rà soát";
  if (month.state === "NOT_CLOSED_NO_SOURCE") return "Chưa chốt · chưa có nguồn";
  if (month.state === "NOT_CLOSED") return "Chưa chốt · không dùng bản hiện hành thay bản chốt";
  if (month.state === "CURRENT_AFTER_CLOSURE") {
    let label = "Dữ liệu mới hơn bản chốt (rà soát)";
    if (month.closure_snapshot_id) label += ` · bản chốt #${month.closure_snapshot_id}`;
    if (month.closure_note) label += ` · ${month.closure_note}`;
    return label;
  }
  let label = `${month.state === "CLOSED" ? "Đã chốt" : "Tạm tính"}${
    month.quality === "PARTIAL" ? " · Một phần" : ""
  }`;
  if (month.state === "CLOSED" && month.closure_note) label += ` · ${month.closure_note}`;
  return label;
}

const BASIS_PREF = "customers-total";
const YEAR_PREF = `${BASIS_PREF}.year`;
const MONTH_PREF = `${BASIS_PREF}.month`;
const MODE_PREF = `${BASIS_PREF}.mode`;
const BASIS_KEY = `${BASIS_PREF}.basis`;
const DATE_PREF = `${BASIS_PREF}.date`;

export default function CustomersTotal() {
  const now = new Date();
  const initialYear = loadPref(YEAR_PREF, String(now.getFullYear()));
  const initialMonth = loadPref(MONTH_PREF, String(now.getMonth() + 1).padStart(2, "0"));
  const initialDate = loadPref(DATE_PREF, now.toISOString().slice(0, 10));

  const [year, setYear] = useState(initialYear);
  const [month, setMonth] = useState(initialMonth);
  const [storedDate, setSelectedDate] = useState(initialDate);
  const selectedDate = dateInReportMonth(storedDate, year, month);
  const [mode, setMode] = useState<"month" | "year" | "day">(
    (loadPref(MODE_PREF, "month") as "month" | "year" | "day") || "month"
  );
  const [basis, setBasis] = useState<"current" | "closed">(
    loadPref(BASIS_PREF, "current") === "closed" ? "closed" : "current"
  );
  const [dailyInspectorTab, setDailyInspectorTab] = useState<"daily_table" | "client_rank">(
    "daily_table"
  );
  const [showWritebackModal, setShowWritebackModal] = useState(false);

  const [data, setData] = useState<YearSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let active = true;
    setData(null);
    setError(null);
    if (!/^\d{4}$/.test(year) || year === "0000") {
      setLoading(false);
      return;
    }
    setLoading(true);

    const queryParams = new URLSearchParams({
      year,
      basis,
      scope: mode,
      month,
      date: selectedDate,
    });

    fetchJson<YearSummary>(`/sheets/sources/year-summary?${queryParams.toString()}`)
      .then((result) => {
        if (active) setData(result);
      })
      .catch((failure: unknown) => {
        if (active) setError(failure instanceof Error ? failure.message : String(failure));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [year, month, selectedDate, mode, basis, revision]);

  useEffect(() => {
    savePref(YEAR_PREF, year);
  }, [year]);
  useEffect(() => {
    savePref(MONTH_PREF, month);
  }, [month]);
  useEffect(() => {
    savePref(MODE_PREF, mode);
  }, [mode]);
  useEffect(() => {
    savePref(BASIS_KEY, basis);
  }, [basis]);
  useEffect(() => {
    savePref(DATE_PREF, selectedDate);
  }, [selectedDate]);

  const selectedMonthObj =
    data?.year === Number(year)
      ? data.months.find((item) => item.period === `${year}-${month}`)
      : undefined;

  const sync = useCallback(async () => {
    if (!selectedMonthObj?.active_source_id) return;
    setBusy(true);
    setError(null);
    try {
      const attempt = await postJson<SheetSyncAttempt>(
        `/sheets/sources/${selectedMonthObj.active_source_id}/sync`
      );
      if (attempt.status === "ERROR")
        throw new Error(attempt.error ?? "Không đọc được nguồn.");
      setRevision((value) => value + 1);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }, [selectedMonthObj]);

  const shiftDate = (deltaDays: number) => {
    const cur = new Date(selectedDate);
    cur.setDate(cur.getDate() + deltaDays);
    const newStr = cur.toISOString().slice(0, 10);
    setSelectedDate(newStr);
    setYear(String(cur.getFullYear()));
    setMonth(String(cur.getMonth() + 1).padStart(2, "0"));
  };

  const jumpToToday = () => {
    const today = new Date();
    setSelectedDate(today.toISOString().slice(0, 10));
    setYear(String(today.getFullYear()));
    setMonth(String(today.getMonth() + 1).padStart(2, "0"));
  };

  const metrics = mode === "year" ? undefined : selectedMonthObj?.metrics;
  const opening = mode === "year" ? data?.opening_balance?.metric : metrics?.opening_balance;
  const closing = mode === "year" ? data?.closing_balance?.metric : metrics?.current_balance;
  const closingLabel =
    mode === "year"
      ? data?.closing_balance?.period.endsWith("-12")
        ? "Số dư cuối năm"
        : data?.closing_balance
        ? `Số dư đến kỳ ${data.closing_balance.period}`
        : "Số dư cuối năm"
      : "Số dư hiện tại";

  function metricCoverage(metric: Metric | undefined | null) {
    if (metric?.basis === "SUMMARY_ROW") {
      if (metric.value == null) return "Chưa xác định được ô tổng hợp lệ";
      return null;
    }
    return !metric
      ? "Chưa có dữ liệu"
      : metric.status !== "COMPLETE"
      ? `Một phần · ${metric.complete_customers}/${metric.total_customers} khách`
      : null;
  }

  const effectiveFeePct =
    data?.daily_summary?.effective_fee_rate_pct || "4.00";

  function card(
    label: string,
    value: string | null | undefined,
    coverage: string | null,
    usdt = false,
    balance = false,
    theme: string = "default"
  ) {
    let valueColor = "text-white";
    let borderAccent = "border-slate-800/80 hover:border-indigo-500/40";
    let bgAccent = "bg-[#111827]/95";

    if (theme === "emerald") {
      valueColor = "text-emerald-400";
      borderAccent = "border-emerald-500/40 bg-emerald-950/20 shadow-emerald-950/20";
      bgAccent = "bg-[#0b1b16]/90";
    } else if (theme === "indigo") {
      valueColor = "text-indigo-300";
    } else if (theme === "sky") {
      valueColor = "text-sky-400";
    } else if (theme === "amber") {
      valueColor = "text-amber-300";
    } else if (theme === "violet") {
      valueColor = "text-violet-300";
    } else if (theme === "teal") {
      valueColor = "text-teal-300";
    }

    if (balance && value?.startsWith("-")) {
      valueColor = "text-rose-400";
    }

    return (
      <article
        key={label}
        className={`rounded-2xl border ${borderAccent} ${bgAccent} p-5 shadow-xl backdrop-blur-md transition-all duration-200 flex flex-col justify-between`}
      >
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-xs font-medium uppercase tracking-wider text-slate-400">
            {label}
          </h3>
          {theme === "emerald" && (
            <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-mono font-medium text-emerald-300 border border-emerald-500/30">
              % Phí: {effectiveFeePct}%
            </span>
          )}
        </div>
        <p className={`mt-3 text-2xl font-bold font-mono tracking-tight tabular-nums ${valueColor}`}>
          {money(value, usdt, balance)}
        </p>
        <div className="mt-2 min-h-[20px]">
          {coverage && (
            <span className="inline-flex items-center rounded-full bg-amber-500/10 border border-amber-500/20 px-2.5 py-0.5 text-[11px] font-medium text-amber-300">
              {coverage}
            </span>
          )}
        </div>
      </article>
    );
  }

  const basisText =
    basis === "closed"
      ? "Bản chốt: chỉ dùng bản chốt; kỳ chưa chốt để trống, không âm thầm dùng bản hiện hành."
      : "Dữ liệu mới nhất: bản đọc thành công mới nhất của nguồn đang hoạt động; kỳ đã có bản chốt vẫn được nhãn rõ.";

  const peakDayFeeNum = Number(data?.daily_summary?.peak_profit_date?.fee || 1);

  return (
    <section id="tong" className="space-y-6 text-slate-100">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
        <div>
          <div className="flex items-center gap-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-500/20 text-indigo-400 font-bold text-base shadow-inner">
              <MonoIcon name="analytics" className="h-4 w-4" />
            </span>
            <h2 className="text-xl font-bold tracking-tight text-white">
              Tổng tài chính — Tất cả khách hàng
            </h2>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            {basisText} Số liệu chuẩn xác theo nguyên tắc bất biến Decimal ROUND_HALF_UP.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setShowWritebackModal(true)}
            className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-indigo-950/50 hover:from-indigo-500 hover:to-violet-500 transition-all cursor-pointer"
          >
            <span></span> Kẻ & Ghi Báo Cáo VIA Lên Sheet
          </button>
          <a
            className="rounded-xl border border-slate-700 bg-slate-900/60 px-3.5 py-2 text-xs font-medium text-sky-400 hover:bg-slate-800 hover:text-sky-300 transition-colors"
            href="/sheets#saved-sources"
          >
            Quản lý nguồn & liên kết →
          </a>
        </div>
      </div>

      {/* Filter Control Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-800/80 bg-[#0f172a]/95 p-4 shadow-lg backdrop-blur-md">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-slate-300">
            <span className="text-slate-400 font-medium">Chế độ:</span>
            <select
              aria-label="Chế độ dữ liệu tổng"
              value={basis}
              onChange={(e) => setBasis(e.target.value as "current" | "closed")}
              className="rounded-xl border border-slate-700 bg-[#1e293b] px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            >
              <option value="current">Dữ liệu mới nhất</option>
              <option value="closed">Bản chốt</option>
            </select>
          </label>

          <label className="flex items-center gap-2 text-xs text-slate-300">
            <span className="text-slate-400 font-medium">Năm:</span>
            <input
              aria-label="Năm báo cáo"
              type="number"
              min="1"
              max="9999"
              value={year}
              onChange={(e) => setYear(e.target.value)}
              className="w-20 rounded-xl border border-slate-700 bg-[#1e293b] px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
          </label>

          <label className="flex items-center gap-2 text-xs text-slate-300">
            <span className="text-slate-400 font-medium">Phạm vi:</span>
            <select
              aria-label="Phạm vi tổng"
              value={mode}
              onChange={(e) => setMode(e.target.value as "month" | "year" | "day")}
              className="rounded-xl border border-slate-700 bg-[#1e293b] px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            >
              <option value="month">Một tháng</option>
              <option value="day">Theo ngày (Kiểm tra lãi ngày)</option>
              <option value="year">Cả năm</option>
            </select>
          </label>

          {mode !== "year" && (
            <label className="flex items-center gap-2 text-xs text-slate-300">
              <span className="text-slate-400 font-medium">Tháng:</span>
              <select
                aria-label="Tháng báo cáo"
                value={month}
                onChange={(e) => setMonth(e.target.value)}
                className="rounded-xl border border-slate-700 bg-[#1e293b] px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              >
                {Array.from({ length: 12 }, (_, i) => (
                  <option key={i} value={String(i + 1).padStart(2, "0")}>
                    Tháng {i + 1}
                  </option>
                ))}
              </select>
            </label>
          )}

          {mode === "day" && (
            <div className="flex items-center gap-1.5 border-l border-slate-800 pl-3">
              <span className="text-xs text-slate-400 font-medium">Ngày:</span>
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => {
                  setSelectedDate(e.target.value);
                  const p = e.target.value.split("-");
                  if (p.length === 3) {
                    setYear(p[0]);
                    setMonth(p[1]);
                  }
                }}
                className="rounded-xl border border-slate-700 bg-[#1e293b] px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
              <button
                type="button"
                onClick={() => shiftDate(-1)}
                className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-700"
                title="Ngày hôm trước"
              >
                ← Hôm qua
              </button>
              <button
                type="button"
                onClick={jumpToToday}
                className="rounded-lg border border-indigo-500/40 bg-indigo-950/40 px-2.5 py-1 text-xs font-medium text-indigo-300 hover:bg-indigo-900/40"
              >
                Hôm nay
              </button>
              <button
                type="button"
                onClick={() => shiftDate(1)}
                className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-700"
                title="Ngày hôm sau"
              >
                Ngày mai →
              </button>
            </div>
          )}
        </div>

        <div>
          {mode !== "year" && selectedMonthObj?.state !== "NOT_CLOSED" && (
            <button
              type="button"
              disabled={!selectedMonthObj?.active_source_id || busy}
              onClick={() => void sync()}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-medium text-slate-200 hover:bg-slate-700 hover:text-white transition-colors disabled:opacity-50"
            >
              {busy ? " Đang cập nhật…" : " Cập nhật ngay"}
            </button>
          )}
          {mode !== "year" && selectedMonthObj?.state === "NOT_CLOSED" && (
            <span className="text-xs text-slate-500">
              Kỳ chưa chốt; không có bản chốt để hiển thị.
            </span>
          )}
        </div>
      </div>

      {/* Errors & Loading */}
      {error && (
        <div role="alert" className="rounded-xl border border-rose-500/30 bg-rose-950/40 p-4 text-xs text-rose-300">
           {error}
        </div>
      )}
      {loading && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 text-center text-sm text-slate-400">
           Đang tính toán dữ liệu tài chính từ các bản snapshot Sheets...
        </div>
      )}
      {!loading && !data && !error && (
        <p className="text-sm text-slate-500">Nhập năm hợp lệ để xem báo cáo.</p>
      )}

      {/* Main Content when data ready */}
      {data && String(data.year) === year && (
        <>
          <div className="flex items-center justify-between text-xs text-slate-400">
            <p>
              {mode === "year"
                ? `Các tháng đã có dữ liệu: ${data.months_with_data}/12 tháng.`
                : `${year}-${month} · ${
                    selectedMonthObj ? stateText(selectedMonthObj) : "Chưa có nguồn"
                  }`}
            </p>
          </div>

          {/* KPI CARDS (Obsidian High Contrast Grid) */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {card(
              mode === "year" ? "Số dư đầu năm" : "Số dư đầu kỳ",
              opening?.value,
              metricCoverage(opening),
              false,
              true,
              "sky"
            )}
            {fields.map((field) => {
              const annual = data.flows[field.key];
              const monthly = metrics?.[field.key];
              const coverage =
                mode === "year"
                  ? annual.status !== "COMPLETE"
                    ? `Một phần · ${annual.complete_months}/12 tháng`
                    : null
                  : metricCoverage(monthly);
              const val = mode === "year" ? annual.value : monthly?.value;
              return card(field.label, val, coverage, field.usdt, false, field.theme);
            })}
            {card(
              closingLabel,
              closing?.value,
              metricCoverage(closing),
              false,
              true,
              "amber"
            )}
          </div>

          {/* DAILY PROFIT INSPECTOR PANEL */}
          <div className="mt-8 rounded-2xl border border-slate-800/80 bg-[#111827]/90 p-6 shadow-2xl backdrop-blur-md">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
              <div className="flex items-center gap-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-emerald-500/20 text-emerald-400 font-bold text-base">
                  <MonoIcon name="check" className="h-4 w-4" />
                </span>
                <div>
                  <h3 className="text-lg font-bold text-white">
                    Kiểm Tra Lãi & Chi Tiêu Theo Ngày (Daily Profit Inspector)
                  </h3>
                  <p className="text-xs text-slate-400">
                    Chỉ dùng chi tiêu và phí có ngày trên Sheet. Ngày chưa nhập hiển thị chưa có dữ liệu; phí dịch vụ không phải lợi nhuận ròng.
                  </p>
                </div>
              </div>

              {/* Tabs selector */}
              <div className="flex items-center gap-1 rounded-xl border border-slate-800 bg-slate-900/80 p-1">
                <button
                  type="button"
                  onClick={() => setDailyInspectorTab("daily_table")}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
                    dailyInspectorTab === "daily_table"
                      ? "bg-indigo-600 text-white shadow"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                   Bảng Lãi Từng Ngày Trong Tháng
                </button>
                <button
                  type="button"
                  onClick={() => setDailyInspectorTab("client_rank")}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
                    dailyInspectorTab === "client_rank"
                      ? "bg-indigo-600 text-white shadow"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                   Chi Tiết Lãi Theo Khách Hàng ({selectedDate})
                </button>
              </div>
            </div>

            {/* 4 Daily KPI Highlights */}
            {data.daily_summary && (
              <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                {/* 1. Lãi ròng ngày chọn */}
                <div className="rounded-xl border border-emerald-500/40 bg-emerald-950/20 p-4 shadow-lg shadow-emerald-950/20">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-emerald-400 font-medium"> Phí dịch vụ ngày chọn</span>
                    <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 text-[10px] text-emerald-300 font-mono">
                      {data.daily_summary.selected_date}
                    </span>
                  </div>
                  <p className="mt-2 text-2xl font-bold font-mono text-emerald-300 tabular-nums">
                    {data.daily_summary.profit_selected_date == null ? "Chưa có dữ liệu" : money(data.daily_summary.profit_selected_date)}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-400 font-mono">
                    Chi tiêu: {formatVnd(data.daily_summary.spend_selected_date)} đ
                  </p>
                </div>

                {/* 2. Trung bình lãi/ngày */}
                <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4 shadow-lg">
                  <span className="text-xs text-sky-400 font-medium"> Trung bình phí/ngày</span>
                  <p className="mt-2 text-2xl font-bold font-mono text-sky-300 tabular-nums">
                    {money(data.daily_summary.avg_daily_profit)}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-400">
                    Tính trên {data.daily_summary.days_with_data} ngày có hoạt động chi tiêu
                  </p>
                </div>

                {/* 3. Ngày lãi đỉnh nhất tháng */}
                <div className="rounded-xl border border-amber-500/30 bg-amber-950/20 p-4 shadow-lg shadow-amber-950/20">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-amber-400 font-medium"> Ngày có phí cao nhất</span>
                    {data.daily_summary.peak_profit_date && (
                      <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] text-amber-300 font-mono">
                        {data.daily_summary.peak_profit_date.date}
                      </span>
                    )}
                  </div>
                  <p className="mt-2 text-2xl font-bold font-mono text-amber-300 tabular-nums">
                    {data.daily_summary.peak_profit_date
                      ? `+${formatVnd(data.daily_summary.peak_profit_date.fee)} đ`
                      : "—"}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-400 font-mono">
                    {data.daily_summary.peak_profit_date
                      ? `Chi tiêu: ${formatVnd(data.daily_summary.peak_profit_date.spend_vnd)} đ`
                      : "Chưa có dữ liệu"}
                  </p>
                </div>

                {/* 4. Tỷ suất phí thực tế */}
                <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4 shadow-lg">
                  <span className="text-xs text-indigo-400 font-medium"> Tỷ suất phí thực tế</span>
                  <p className="mt-2 text-2xl font-bold font-mono text-indigo-300 tabular-nums">
                    {data.daily_summary.effective_fee_rate_pct == null ? "—" : `${data.daily_summary.effective_fee_rate_pct}%`}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-400 font-mono">
                    Tổng phí có dữ liệu ngày: {money(data.daily_summary.total_month_fee)}
                  </p>
                </div>
              </div>
            )}

            {/* TAB 1: BẢNG LÃI TỪNG NGÀY TRONG THÁNG */}
            {dailyInspectorTab === "daily_table" && (
              <div className="mt-5 overflow-x-auto rounded-xl border border-slate-800">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-slate-900/90 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
                    <tr>
                      <th className="px-3 py-2.5 font-semibold">Ngày</th>
                      <th className="px-3 py-2.5 font-semibold text-right">Chi tiêu QC (VND)</th>
                      <th className="px-3 py-2.5 font-semibold">Phí / Lợi nhuận (VND) & Biểu đồ</th>
                      <th className="px-3 py-2.5 font-semibold text-right">% Phí</th>
                      <th className="px-3 py-2.5 font-semibold text-right">Tiền nạp (VND)</th>
                      <th className="px-3 py-2.5 font-semibold text-right">USDT ròng</th>
                      <th className="px-3 py-2.5 font-semibold">Nguồn tính</th>
                      <th className="px-3 py-2.5 font-semibold text-center">Thao tác</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono">
                    {data.daily_breakdown?.map((dayItem) => {
                      const isSelected = dayItem.date === selectedDate;
                      const feeNum = Number(dayItem.fee || 0);
                      const barWidth = peakDayFeeNum > 0 ? Math.min(100, Math.round((feeNum / peakDayFeeNum) * 100)) : 0;
                      const hasSpend = Number(dayItem.spend_vnd) > 0;

                      return (
                        <tr
                          key={dayItem.date}
                          onClick={() => setSelectedDate(dayItem.date)}
                          className={`cursor-pointer transition-colors ${
                            isSelected
                              ? "bg-indigo-950/40 border-l-4 border-l-indigo-500 font-semibold"
                              : "hover:bg-slate-800/40"
                          }`}
                        >
                          <td className="px-3 py-2 text-slate-200">
                            <span className="font-mono">{dayItem.date}</span>
                            {isSelected && (
                              <span className="ml-1.5 rounded bg-indigo-500/20 px-1.5 py-0.2 text-[10px] text-indigo-300 font-sans">
                                Đang chọn
                              </span>
                            )}
                          </td>
                          <td className={`px-3 py-2 text-right ${hasSpend ? "text-white" : "text-slate-500"}`}>
                            {money(dayItem.spend_vnd)}
                          </td>
                          <td className="px-3 py-2 min-w-[200px]">
                            <div className="flex items-center gap-2">
                              <span className={`w-28 text-right font-bold ${feeNum > 0 ? "text-emerald-400" : "text-slate-500"}`}>
                                {dayItem.fee == null ? "Chưa có dữ liệu" : money(dayItem.fee)}
                              </span>
                              <div className="h-2 flex-1 rounded-full bg-slate-800 overflow-hidden">
                                <div
                                  className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-teal-400"
                                  style={{ width: `${barWidth}%` }}
                                />
                              </div>
                            </div>
                          </td>
                          <td className="px-3 py-2 text-right text-indigo-300">
                            {dayItem.fee_rate_pct == null ? "—" : `${dayItem.fee_rate_pct}%`}
                          </td>
                          <td className="px-3 py-2 text-right text-sky-400">
                            {Number(dayItem.budget_deposits_vnd || 0) > 0 ? `${formatVnd(dayItem.budget_deposits_vnd)} đ` : "—"}
                          </td>
                          <td className="px-3 py-2 text-right text-violet-300">
                            {Number(dayItem.usdt_net || 0) !== 0 ? dayItem.usdt_net : "—"}
                          </td>
                          <td className="px-3 py-2 font-sans">
                            <span
                              className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                                dayItem.source_type === "DAILY_ROW"
                                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                  : dayItem.source_type === "NO_DATA"
                                  ? "bg-sky-500/10 text-sky-400 border border-sky-500/20"
                                  : "bg-amber-500/10 text-amber-300 border border-amber-500/20"
                              }`}
                            >
                              {dayItem.source_type === "NO_DATA" ? "Chưa có dữ liệu" : "Dữ liệu Sheet"}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-center font-sans">
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedDate(dayItem.date);
                                setDailyInspectorTab("client_rank");
                              }}
                              className="rounded px-2 py-1 text-[11px] text-indigo-400 hover:bg-indigo-950/50 hover:text-indigo-300 transition-colors"
                            >
                              Xem khách →
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* TAB 2: CHI TIẾT LÃI THEO KHÁCH HÀNG */}
            {dailyInspectorTab === "client_rank" && (
              <div className="mt-5 space-y-3">
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>
                    Bảng xếp hạng đóng góp lợi nhuận & chi tiêu của từng khách hàng cho ngày{" "}
                    <strong className="text-indigo-300 font-mono">{selectedDate}</strong>.
                  </span>
                  <span className="text-slate-500">
                    Tổng số khách hàng: {data.client_daily_breakdown?.length || 0}
                  </span>
                </div>

                <div className="overflow-x-auto rounded-xl border border-slate-800">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead className="bg-slate-900/90 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
                      <tr>
                        <th className="px-3 py-2.5 font-semibold">Khách hàng</th>
                        <th className="px-3 py-2.5 font-semibold text-right">Chi tiêu QC (VND)</th>
                        <th className="px-3 py-2.5 font-semibold text-right">% Phí</th>
                        <th className="px-3 py-2.5 font-semibold text-right">Phí / Lợi nhuận (VND)</th>
                        <th className="px-3 py-2.5 font-semibold text-right">Tiền nạp (VND)</th>
                        <th className="px-3 py-2.5 font-semibold text-right">USDT ròng</th>
                        <th className="px-3 py-2.5 font-semibold">Nguồn tính</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono">
                      {data.client_daily_breakdown?.map((clientItem) => {
                        const feeNum = Number(clientItem.fee || 0);
                        const hasSpend = Number(clientItem.spend_vnd) > 0;
                        return (
                          <tr
                            key={clientItem.customer_id}
                            className="hover:bg-slate-800/40 transition-colors"
                          >
                            <td className="px-3 py-2 font-sans font-medium text-white">
                              {clientItem.customer_name}
                            </td>
                            <td className={`px-3 py-2 text-right ${hasSpend ? "text-white" : "text-slate-500"}`}>
                              {money(clientItem.spend_vnd)}
                            </td>
                            <td className="px-3 py-2 text-right text-indigo-300">
                              {clientItem.fee_rate_pct == null ? "—" : `${clientItem.fee_rate_pct}%`}
                            </td>
                            <td className={`px-3 py-2 text-right font-bold ${feeNum > 0 ? "text-emerald-400" : "text-slate-500"}`}>
                              {clientItem.fee == null ? "Chưa có dữ liệu" : money(clientItem.fee)}
                            </td>
                            <td className="px-3 py-2 text-right text-sky-400">
                              {Number(clientItem.budget_deposits_vnd || 0) > 0
                                ? `${formatVnd(clientItem.budget_deposits_vnd)} đ`
                                : "—"}
                            </td>
                            <td className="px-3 py-2 text-right text-violet-300">
                              {Number(clientItem.usdt_net || 0) !== 0 ? clientItem.usdt_net : "—"}
                            </td>
                            <td className="px-3 py-2 font-sans">
                              <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300">
                                {clientItem.source_type === "NO_DATA" ? "Chưa có dữ liệu" : "Dữ liệu Sheet"}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>

          {/* Collapsible Details */}
          <details className="rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 backdrop-blur-md">
            <summary className="cursor-pointer font-semibold text-sm text-slate-300 hover:text-white transition-colors">
              Chi tiết dữ liệu kỹ thuật Sheets & Lịch sử đồng bộ
            </summary>
            <p className="mt-2 text-xs text-slate-400">
              Lợi nhuận theo quy ước bằng phí, chưa trừ chi phí TKQC. USDT chưa đủ căn cứ kỳ không được cộng; không cộng số dư qua các tháng.
            </p>
            {(mode === "year" ? data.months : selectedMonthObj ? [selectedMonthObj] : []).map(
              (item) => (
                <div key={item.period} className="mt-3 border-t border-slate-800 pt-3 text-xs text-slate-300">
                  <strong className="text-white">
                    {item.period} · {stateText(item)}
                  </strong>
                  {item.name ? ` · ${item.name}` : ""}
                  {item.read_at ? ` · ${new Date(item.read_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}` : ""}
                  {item.snapshot_id && <span className="text-indigo-400"> · bản lưu #{item.snapshot_id}</span>}
                  {item.closed_at && (
                    <span className="text-emerald-400">
                      {" "}
                      · chốt{" "}
                      {new Date(item.closed_at).toLocaleString("vi-VN", {
                        timeZone: "Asia/Ho_Chi_Minh",
                      })}
                    </span>
                  )}
                  {item.last_attempt && (
                    <p className="mt-1 text-slate-400">
                      Lần thử gần nhất:{" "}
                      {new Date(item.last_attempt.started_at).toLocaleString("vi-VN", {
                        timeZone: "Asia/Ho_Chi_Minh",
                      })}{" "}
                      · {item.last_attempt.status}
                      {item.last_attempt.error ? ` · ${item.last_attempt.error}` : ""}
                    </p>
                  )}
                </div>
              )
            )}
          </details>

          {/* Sources Summary by Month */}
          <section className="rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 backdrop-blur-md">
            <h3 className="font-semibold text-sm text-white mb-3">Nguồn theo tháng — {year}</h3>
            <div className="overflow-x-auto rounded-xl border border-slate-800">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-slate-900 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
                  <tr>
                    <th className="px-3 py-2.5 font-semibold">Tháng</th>
                    <th className="px-3 py-2.5 font-semibold">Nguồn</th>
                    <th className="px-3 py-2.5 font-semibold">Dữ liệu / chốt</th>
                    <th className="px-3 py-2.5 font-semibold">Lần đọc gần nhất</th>
                    <th className="px-3 py-2.5 font-semibold text-center">Tự đồng bộ</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {data.months.map((item) => (
                    <tr key={item.period} className="hover:bg-slate-800/40">
                      <td className="px-3 py-2 font-mono text-slate-300">{item.period}</td>
                      <td className="px-3 py-2 text-slate-200">{item.name ?? "Chưa có nguồn"}</td>
                      <td className="px-3 py-2 text-slate-400">
                        {stateText(item)}
                        {item.last_attempt?.status === "ERROR" ? " · Lần cập nhật lỗi" : ""}
                      </td>
                      <td className="px-3 py-2 text-slate-400 font-mono">
                        {item.latest_read_at
                          ? new Date(item.latest_read_at).toLocaleString("vi-VN", {
                              timeZone: "Asia/Ho_Chi_Minh",
                            })
                          : "—"}
                      </td>
                      <td className="px-3 py-2 text-center">
                        {item.active_source_id ? (
                          <span
                            className={`rounded px-2 py-0.5 text-[10px] font-medium ${
                              item.sync_enabled
                                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                : "bg-slate-800 text-slate-400"
                            }`}
                          >
                            {item.sync_enabled ? "Bật" : "Tắt"}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {/* Via Sheet Writeback Modal */}
      <ViaSheetWritebackModal
        isOpen={showWritebackModal}
        onClose={() => setShowWritebackModal(false)}
        defaultDate={selectedDate}
        onSuccess={() => setRevision((v) => v + 1)}
      />
    </section>
  );
}
