"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchJson, postJson, type SheetSyncAttempt } from "../lib/api";
import { formatBalanceVnd, formatVnd } from "../lib/vnd.mjs";
import { loadPref, savePref } from "../lib/prefs";

type Metric = {
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
  state: "MISSING_SOURCE" | "MISSING_SNAPSHOT" | "CLOSED" | "PROVISIONAL" | "CONFLICTING_CLOSURES" | "NOT_CLOSED" | "NOT_CLOSED_NO_SOURCE" | "CURRENT_AFTER_CLOSURE";
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
  months: Month[];
  months_with_data: number;
  flows: Record<string, Flow>;
  opening_balance: { period: string; metric: Metric } | null;
  closing_balance: { period: string; metric: Metric } | null;
};

const fields = [
  { key: "budget_deposits_vnd", label: "Nạp trong kỳ" },
  { key: "spend_vnd", label: "Chi tiêu quảng cáo" },
  { key: "fee", label: "Phí / Lợi nhuận" },
  { key: "billing_total", label: "Tổng chi tiêu gồm phí" },
  { key: "usdt_received", label: "USDT nhận", usdt: true },
  { key: "usdt_refunded", label: "USDT hoàn", usdt: true },
  { key: "usdt_net", label: "USDT ròng", usdt: true },
];

function usdtText(value: string) {
  const match = value.match(/^(-?)(\d+)(\.\d+)?$/);
  return match ? `${match[1]}${match[2].replace(/\B(?=(\d{3})+(?!\d))/g, ".")}${match[3] ? `,${match[3].slice(1)}` : ""}` : value;
}

function money(value: string | null | undefined, usdt = false, balance = false) {
  if (value == null) return "—";
  return `${usdt ? usdtText(value) : balance ? formatBalanceVnd(value) : formatVnd(value)} ${usdt ? "USDT" : "VND"}`;
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
  let label = `${month.state === "CLOSED" ? "Đã chốt" : "Tạm tính"}${month.quality === "PARTIAL" ? " · Một phần" : ""}`;
  if (month.state === "CLOSED" && month.closure_note) label += ` · ${month.closure_note}`;
  return label;
}

const BASIS_PREF = "customers-total";
const YEAR_PREF = `${BASIS_PREF}.year`;
const MONTH_PREF = `${BASIS_PREF}.month`;
const MODE_PREF = `${BASIS_PREF}.mode`;
const BASIS_KEY = `${BASIS_PREF}.basis`;

export default function CustomersTotal() {
  const now = new Date();
  const initialYear = loadPref(YEAR_PREF, String(now.getFullYear()));
  const [year, setYear] = useState(initialYear);
  const [month, setMonth] = useState(loadPref(MONTH_PREF, String(now.getMonth() + 1).padStart(2, "0")));
  const [mode, setMode] = useState<"month" | "year">(loadPref(MODE_PREF, "month") === "year" ? "year" : "month");
  const [basis, setBasis] = useState<"current" | "closed">(loadPref(BASIS_PREF, "current") === "closed" ? "closed" : "current");
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
    fetchJson<YearSummary>(`/sheets/sources/year-summary?year=${year}&basis=${basis}`)
      .then((result) => { if (active) setData(result); })
      .catch((failure: unknown) => { if (active) setError(failure instanceof Error ? failure.message : String(failure)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [year, basis, revision]);

  useEffect(() => { savePref(YEAR_PREF, year); }, [year]);
  useEffect(() => { savePref(MONTH_PREF, month); }, [month]);
  useEffect(() => { savePref(MODE_PREF, mode); }, [mode]);
  useEffect(() => { savePref(BASIS_KEY, basis); }, [basis]);

  const selected = data?.year === Number(year) ? data.months.find((item) => item.period === `${year}-${month}`) : undefined;
  const sync = useCallback(async () => {
    if (!selected?.active_source_id) return;
    setBusy(true);
    setError(null);
    try {
      const attempt = await postJson<SheetSyncAttempt>(`/sheets/sources/${selected.active_source_id}/sync`);
      if (attempt.status === "ERROR") throw new Error(attempt.error ?? "Không đọc được nguồn.");
      setRevision((value) => value + 1);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }, [selected]);

  const metrics = mode === "month" ? selected?.metrics : undefined;
  const opening = mode === "month" ? metrics?.opening_balance : data?.opening_balance?.metric;
  const closing = mode === "month" ? metrics?.current_balance : data?.closing_balance?.metric;
  const closingLabel = mode === "month" ? "Số dư hiện tại" :
    data?.closing_balance?.period.endsWith("-12") ? "Số dư cuối năm" :
    data?.closing_balance ? `Số dư đến kỳ ${data.closing_balance.period}` : "Số dư cuối năm";

  function card(label: string, value: string | null | undefined, coverage: string | null, usdt = false, balance = false) {
    return <article key={label} className="rounded-xl border border-slate-200 bg-white p-4">
      <h3 className="text-sm text-slate-600">{label}</h3>
      <p className={`mt-2 text-xl font-semibold ${balance && value?.startsWith("-") ? "text-rose-700" : ""}`}>{money(value, usdt, balance)}</p>
      {coverage && <p className="mt-1 text-xs text-amber-800">{coverage}</p>}
    </article>;
  }
  function metricCoverage(metric: Metric | undefined | null) {
    return !metric ? "Chưa có dữ liệu" : metric.status !== "COMPLETE" ? `Một phần · ${metric.complete_customers}/${metric.total_customers} khách` : null;
  }

  const basisText = basis === "closed"
    ? "Bản chốt: chỉ dùng bản chốt; kỳ chưa chốt để trống, không âm thầm dùng bản hiện hành."
    : "Dữ liệu mới nhất: bản đọc thành công mới nhất của nguồn đang hoạt động; kỳ đã có bản chốt vẫn được nhãn rõ (bản chốt không bị ghi đè).";

  return <section id="tong" className="space-y-4">
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div><h2 className="text-lg font-semibold">Tổng tài chính — tất cả khách</h2><p className="text-sm text-slate-600">{basisText} Chỉ đọc dữ liệu Sheets đã lưu.</p></div>
      <a className="text-sky-700 underline" href="/sheets#saved-sources">Quản lý nguồn, liên kết khách và lịch sử</a>
    </div>
    <div className="flex flex-wrap items-end gap-3">
      <label>Chế độ dữ liệu <select aria-label="Chế độ dữ liệu tổng" value={basis} onChange={(event) => setBasis(event.target.value as "current" | "closed")} className="rounded border p-1">
        <option value="current">Dữ liệu mới nhất</option>
        <option value="closed">Bản chốt</option>
      </select></label>
      <label>Năm <input aria-label="Năm báo cáo" type="number" min="1" max="9999" value={year} onChange={(event) => setYear(event.target.value)} className="w-24 rounded border p-1" /></label>
      <label>Phạm vi <select aria-label="Phạm vi tổng" value={mode} onChange={(event) => setMode(event.target.value as "month" | "year")} className="rounded border p-1"><option value="month">Một tháng</option><option value="year">Cả năm</option></select></label>
      {mode === "month" && <label>Tháng <select aria-label="Tháng báo cáo" value={month} onChange={(event) => setMonth(event.target.value)} className="rounded border p-1">{Array.from({ length: 12 }, (_, i) => <option key={i} value={String(i + 1).padStart(2, "0")}>{i + 1}</option>)}</select></label>}
      {mode === "month" && selected?.state !== "NOT_CLOSED" && <button type="button" disabled={!selected?.active_source_id || busy} onClick={() => void sync()}>{busy ? "Đang cập nhật…" : "Cập nhật ngay"}</button>}
      {mode === "month" && selected?.state === "NOT_CLOSED" && <p className="text-xs text-slate-500">Kỳ chưa chốt; không có bản chốt để hiển thị.</p>}
    </div>
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {loading && <p>Đang tải dữ liệu đã lưu…</p>}
    {!loading && !data && !error && <p>Nhập năm hợp lệ để xem báo cáo.</p>}
    {data && String(data.year) === year && <>
      <p className="text-sm text-slate-600">{mode === "year" ? `Các tháng đã có dữ liệu: ${data.months_with_data}/12 · tổng phần đã biết.` : `${year}-${month} · ${selected ? stateText(selected) : "Chưa có nguồn"}`}</p>
      {(mode === "year" ? data.months : selected ? [selected] : []).some((item) => item.period_mismatches?.length) && <p className="text-sm text-amber-800">Có ngày nguồn ngoài kỳ đăng ký; xem khách và kỳ liên quan trong Chi tiết dữ liệu.</p>}
      {(mode === "year" ? data.months : selected ? [selected] : []).some((item) => item.last_attempt?.status === "ERROR") && <p role="alert" className="text-sm text-amber-800">Có nguồn cập nhật thất bại; xem lỗi trong Chi tiết dữ liệu.</p>}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {card(mode === "year" ? "Số dư đầu năm" : "Số dư đầu kỳ", opening?.value, metricCoverage(opening), false, true)}
        {fields.map((field) => {
          const annual = data.flows[field.key];
          const monthly = metrics?.[field.key];
          const coverage = mode === "year" ? annual.status !== "COMPLETE" ? `Một phần · ${annual.complete_months}/12 tháng đầy đủ` : null : metricCoverage(monthly);
          return card(field.label, mode === "year" ? annual.value : monthly?.value, coverage, field.usdt);
        })}
        {card(closingLabel, closing?.value, metricCoverage(closing), false, true)}
      </div>
      <details className="rounded-xl border border-slate-200 p-4">
        <summary className="cursor-pointer font-semibold">Chi tiết dữ liệu</summary>
        <p className="mt-2 text-sm">Lợi nhuận theo quy ước bằng phí, chưa trừ chi phí TKQC. USDT chưa đủ căn cứ kỳ không được cộng; không cộng số dư qua các tháng.</p>
        {(mode === "year" ? data.months : selected ? [selected] : []).map((item) => <div key={item.period} className="mt-3 border-t pt-2 text-sm">
          <strong>{item.period} · {stateText(item)}</strong>{item.name ? ` · ${item.name}` : ""}{item.read_at ? ` · ${new Date(item.read_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}` : ""}
          {item.snapshot_id && <span> · bản lưu #{item.snapshot_id}</span>}
          {item.closed_at && <span> · chốt {new Date(item.closed_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })} (actor không lưu ở bản chốt cũ)</span>}
          {item.active_source_id && item.source_id && item.active_source_id !== item.source_id && <p>Bản chốt thuộc nguồn cũ; nguồn thay thế chỉ dùng để cập nhật, không ghi đè bản chốt.</p>}
          {item.last_attempt && <p>Lần thử gần nhất: {new Date(item.last_attempt.started_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })} · {item.last_attempt.status}{item.last_attempt.error ? ` · ${item.last_attempt.error}` : ""}</p>}
          {item.period_mismatches?.map((entry) => <p key={entry.customer}>{entry.customer}: có ngày nguồn ngoài kỳ đăng ký ({entry.periods.join(", ")}); cần rà soát.</p>)}
          {item.metrics && Object.entries(item.metrics).map(([key, metric]) => <details key={key} className="mt-1"><summary className="cursor-pointer">{key}: {metric.complete_customers}/{metric.total_customers} khách{metric.missing_customers.length ? ` · thiếu: ${metric.missing_customers.join(", ")}` : ""}</summary><ul>{metric.contributions.map((contribution, index) => <li key={`${contribution.customer}-${index}`}>{contribution.customer} · {Array.isArray(contribution.source) ? contribution.source.join(", ") : contribution.source ?? "—"} · {contribution.value}</li>)}</ul></details>)}
        </div>)}
      </details>
      <section><h3 className="font-semibold">Nguồn theo tháng — {year}</h3>
        <div className="overflow-x-auto"><table><thead><tr><th>Tháng</th><th>Nguồn</th><th>Dữ liệu / chốt</th><th>Lần đọc gần nhất</th><th>Tự đồng bộ</th></tr></thead><tbody>
          {data.months.map((item) => <tr key={item.period}><td>{item.period}</td><td>{item.name ?? "Chưa có nguồn"}</td><td>{stateText(item)}{item.last_attempt?.status === "ERROR" ? " · Lần cập nhật lỗi" : ""}</td><td>{item.latest_read_at ? new Date(item.latest_read_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" }) : "—"}</td><td>{item.active_source_id ? item.sync_enabled ? "Bật" : "Tắt" : "—"}</td></tr>)}
        </tbody></table></div>
      </section>
      <p className="text-xs text-slate-500">Tự đồng bộ chỉ hoạt động khi backend đang chạy. Liên kết khách và đối chiếu chuyển kỳ được xác nhận tại trang quản lý nguồn.</p>
    </>}
  </section>;
}
