"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Empty, ErrorNotice, PageHeading } from "../../components/admin-ui";
import { SpendChart } from "../../components/spend-chart";
import { fetchJson } from "../../lib/api";
import { moneyText } from "../../lib/admin-utils.mjs";
import type { OperationalDashboard } from "../../types/admin";

type FilterKey = "today" | "yesterday" | "last7" | "last14" | "last28" | "last30" | "thisWeek" | "lastWeek" | "thisMonth" | "lastMonth" | "max" | "custom";
type DateRange = { date_from?: string; date_to?: string };

const FILTERS: Array<{ value: FilterKey; label: string }> = [
  { value: "today", label: "Hôm nay" },
  { value: "yesterday", label: "Hôm qua" },
  { value: "last7", label: "7 ngày qua" },
  { value: "last14", label: "14 ngày qua" },
  { value: "last28", label: "28 ngày qua" },
  { value: "last30", label: "30 ngày qua" },
  { value: "thisWeek", label: "Tuần này" },
  { value: "lastWeek", label: "Tuần trước" },
  { value: "thisMonth", label: "Tháng này" },
  { value: "lastMonth", label: "Tháng trước" },
  { value: "max", label: "Tối đa" },
  { value: "custom", label: "Tùy chỉnh (Date Range Picker)" },
];

function todayInVietnam() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
}
function shiftDate(value: string, days: number) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}
function rangeFor(filter: FilterKey, customFrom: string, customTo: string): DateRange {
  const today = todayInVietnam();
  if (filter === "max") return {};
  if (filter === "custom") return { date_from: customFrom || today, date_to: customTo || today };
  if (filter === "today") return { date_from: today, date_to: today };
  if (filter === "yesterday") { const day = shiftDate(today, -1); return { date_from: day, date_to: day }; }
  const lengths: Partial<Record<FilterKey, number>> = { last7: 7, last14: 14, last28: 28, last30: 30 };
  if (lengths[filter]) return { date_from: shiftDate(today, -(lengths[filter] as number) + 1), date_to: today };
  const current = new Date(`${today}T00:00:00Z`);
  if (filter === "thisWeek" || filter === "lastWeek") {
    const mondayOffset = (current.getUTCDay() + 6) % 7;
    const thisMonday = shiftDate(today, -mondayOffset);
    return filter === "thisWeek"
      ? { date_from: thisMonday, date_to: today }
      : { date_from: shiftDate(thisMonday, -7), date_to: shiftDate(thisMonday, -1) };
  }
  const monthStart = `${today.slice(0, 7)}-01`;
  if (filter === "thisMonth") return { date_from: monthStart, date_to: today };
  const previousEnd = shiftDate(monthStart, -1);
  return { date_from: `${previousEnd.slice(0, 7)}-01`, date_to: previousEnd };
}
function twoDecimals(value: string, currency: string) {
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value);
  if (!match) return "Chưa có dữ liệu";
  const fraction = (match[3] || "").padEnd(3, "0");
  let minor = BigInt(match[2] + fraction.slice(0, 2));
  if (fraction[2] >= "5") minor += 1n;
  const digits = minor.toString().padStart(3, "0");
  return `${match[1] && minor ? "-" : ""}${digits.slice(0, -2).replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${digits.slice(-2)} ${currency}`;
}
function KpiCard({ label, value, note, tone = "emerald" }: { label: string; value: ReactNode; note: string; tone?: "emerald" | "rose" | "amber" }) {
  const toneClass = tone === "rose" ? "text-[#ef4444]" : tone === "amber" ? "text-[#f59e0b]" : "text-[#10b981]";
  return <article className="rounded-xl border border-slate-300 bg-white p-5 text-slate-900 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-50"><p className="m-0 text-sm font-bold text-slate-700 dark:text-slate-200">{label}</p><div className={`mt-3 text-3xl font-black tracking-tight ${toneClass}`}>{value}</div><p className="mt-2 text-sm font-semibold text-slate-700 dark:text-slate-200">{note}</p></article>;
}

export default function DashboardPage() {
  const [filter, setFilter] = useState<FilterKey>("last30");
  const [customFrom, setCustomFrom] = useState(todayInVietnam());
  const [customTo, setCustomTo] = useState(todayInVietnam());
  const [currency, setCurrency] = useState("USD");
  const [data, setData] = useState<OperationalDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const range = useMemo(() => rangeFor(filter, customFrom, customTo), [filter, customFrom, customTo]);
  const reload = () => {
    const controller = new AbortController();
    const query = new URLSearchParams();
    if (range.date_from) query.set("date_from", range.date_from);
    if (range.date_to) query.set("date_to", range.date_to);
    setLoading(true);
    setError(null);
    void fetchJson<OperationalDashboard>(`/dashboard/operational${query.size ? `?${query}` : ""}`, { signal: controller.signal })
      .then(setData)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Không thể tải dashboard vận hành."))
      .finally(() => setLoading(false));
    return controller;
  };
  useEffect(() => { const controller = reload(); return () => controller.abort(); }, [range.date_from, range.date_to]);
  const metrics = data?.metrics;
  const verified = data?.meta_mode.toLowerCase() === "live";
  const currencies = [...new Set([
    "USD", "VND",
    ...Object.keys(metrics?.today_spend_by_currency || {}),
    ...Object.keys(metrics?.debt_threshold_by_currency || {}),
    ...(data?.chart.chart_rows.flatMap(row => Object.keys(row.meta_by_currency)) || []),
  ])];
  const topAccounts = (data?.top_accounts || []).filter(account => account.currency === currency).slice(0, 10);
  const filterLabel = FILTERS.find(item => item.value === filter)?.label || "Khoảng đã chọn";
  const statusLabel = (status: string) => ({ PENDING: "Chờ xử lý", RUNNING: "Đang xử lý", PROCESSING: "Đang xử lý", COMPLETED: "Hoàn tất" }[status] || status);

  return <>
    <PageHeading eyebrow="TỔNG QUAN VẬN HÀNH" title="Dashboard Ads Business OS" description="Số liệu chỉ gồm TKQC đang gán cho khách hàng; tiền tệ được giữ riêng, không cộng chéo." actions={<><Link className="btn" href="/customers/finance">Tổng tài chính ↗</Link><button className="btn primary" disabled={loading} onClick={() => reload()}>↻ Làm mới dữ liệu</button></>}/>
    <ErrorNotice message={error} retry={() => reload()}/>
    <div className="mb-5 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-7">
      <KpiCard label="Tổng chi tiêu hôm nay" value={loading ? "—" : verified ? moneyText(metrics?.today_spend_by_currency[currency], currency) : "Chưa xác minh"} note={`${data?.business_date || "—"} · ${currency} · Meta đã xác minh`}/>
      <KpiCard label="Tổng ngưỡng dư nợ" value={loading ? "—" : moneyText(metrics?.debt_threshold_by_currency[currency], currency)} note="Chỉ TKQC đang gán cho khách" tone="amber"/>
      <KpiCard label="TK đang hoạt động" value={loading ? "—" : metrics?.active_accounts.toLocaleString("vi-VN")} note={`${metrics?.assigned_accounts || 0} TKQC đã gán`} />
      <KpiCard label="TK vô hiệu hóa hôm nay" value={loading ? "—" : metrics?.disabled_today.toLocaleString("vi-VN")} note="Chuyển trạng thái sang DIE trong ngày" tone="rose"/>
      <KpiCard label="Phí khách hàng hôm nay" value={loading ? "—" : verified ? moneyText(metrics?.fee_by_currency[currency], currency) : "Chưa xác minh"} note="Phí theo hồ sơ; chưa phải tiền thực thu"/>
      <KpiCard label="Ví Binance" value={loading ? "—" : metrics?.binance_accounts ? twoDecimals(metrics.binance_usdt, "USDT") : "Chưa kết nối"} note="Spot + Funding, ảnh đọc mới nhất"/>
      <KpiCard label="PingPong" value={loading ? "—" : metrics?.pingpong_accounts ? twoDecimals(metrics.pingpong_usd, "USD") : "Chưa kết nối"} note="Số dư khả dụng Issuing"/>
    </div>
    <section className="panel"><div className="panel-heading"><div><h2 className="text-2xl font-extrabold">Bảng số liệu chi tiêu</h2><p className="font-semibold text-slate-700 dark:text-slate-200">Chi tiêu Meta so với phí dịch vụ · khoảng trống không được xem là 0</p><div className="chart-legend"><span><i className="legend-dot" style={{ background: "#10b981" }}/>Chi tiêu Meta</span><span><i className="legend-dot" style={{ background: "#f59e0b" }}/>Phí dịch vụ</span></div></div><div className="page-actions"><select aria-label="Tiền tệ biểu đồ" value={currency} onChange={event => setCurrency(event.target.value)}>{currencies.map(item => <option key={item}>{item}</option>)}</select><select aria-label="Khoảng thời gian" value={filter} onChange={event => setFilter(event.target.value as FilterKey)}>{FILTERS.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select>{filter === "custom" && <><label>Từ ngày<input type="date" value={customFrom} max={customTo} onChange={event => setCustomFrom(event.target.value)}/></label><label>Đến ngày<input type="date" value={customTo} min={customFrom} onChange={event => setCustomTo(event.target.value)}/></label></>}</div></div><div className="px-5 pb-2 text-sm font-bold text-slate-700 dark:text-slate-200">Bộ lọc: {filterLabel}</div><SpendChart data={data?.chart} currency={currency} loading={loading}/></section>
    <div className="dashboard-columns"><section className="panel"><div className="panel-heading"><div><h2 className="text-2xl font-extrabold">TKQC chi tiêu cao nhất</h2><p>Chi tiêu hôm nay · {currency} · chỉ tài khoản đang gán</p></div><Link className="btn" href="/accounts">Xem tất cả →</Link></div>{topAccounts.length ? <div className="table-scroll"><table><thead><tr><th>ID TKQC</th><th>Tên TK</th><th>Khách hàng gán</th><th>Chi tiêu hôm nay</th></tr></thead><tbody>{topAccounts.map(account => <tr key={`${account.act_id}-${account.currency}`}><td className="mono">act_{account.act_id}</td><td><strong>{account.account_name}</strong></td><td>{account.customer_name}</td><td className="mono text-lg font-extrabold text-[#10b981]">{moneyText(account.spend, account.currency)}</td></tr>)}</tbody></table></div> : <Empty description={loading ? "Đang đọc chi tiêu tài khoản…" : "Chưa có chi tiêu Meta đã xác minh hôm nay cho tiền tệ đã chọn."}/>}</section>
      <section className="panel"><div className="panel-heading"><div><h2 className="text-2xl font-extrabold">Hàng đợi chiến dịch</h2><p>Lệnh Auto Set Camp gần nhất</p></div><Link className="btn" href="/auto-set-camp">Mở hàng đợi →</Link></div>{data?.commands.length ? <div className="table-scroll"><table><thead><tr><th>Lệnh</th><th>TK đích</th><th>Trạng thái</th><th>Thời gian</th></tr></thead><tbody>{data.commands.map(command => <tr key={command.id}><td><strong>{command.command}</strong><small className="table-muted">#{command.id}</small></td><td className="mono">{command.target_account || "Chưa có"}</td><td><span className={`pill ${command.status === "COMPLETED" ? "good" : "warn"}`}>{statusLabel(command.status)}</span></td><td>{command.created_at ? new Date(command.created_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" }) : "—"}</td></tr>)}</tbody></table></div> : <Empty description={loading ? "Đang đọc hàng đợi…" : "Hiện chưa có lệnh chờ, đang xử lý hoặc đã hoàn tất."}/>}</section></div>
    <div className="quick-links"><Link href="/sheets">↗ Nguồn Google Sheets</Link><Link href="/config/wallets">↗ Ví & tài khoản sàn</Link><Link href="/system">↗ Nhật ký hệ thống</Link><Link href="/operations">↗ Tổng quan đối soát chi tiết</Link></div>
  </>;
}
