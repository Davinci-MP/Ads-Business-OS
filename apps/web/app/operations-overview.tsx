"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { fetchJson, fmtTime } from "../lib/api";
import { formatBalanceVnd } from "../lib/vnd.mjs";

type Source = {
  id: number; name: string; period: string; sync_enabled: boolean; snapshot_id: number | null; read_at: string | null;
  quality: string | null; closed: boolean; last_attempt: { status: string; error: string | null } | null;
};
type OpsOverview = {
  source: Source | null; message?: string;
  metrics: null | {
    customers: { count: number; linked: number; dismissed: number; error_tabs: number };
    accounts: { count: number; spending: number; spend_unknown: number };
    negative_balance: { count: number; balance_missing: number };
    needs_topup: { count: number; thresholds_missing: number; balance_missing: number };
  };
  tasks?: { key: string; label: string; count: number; href: string }[];
  internal: { label: string; customers: number; ad_accounts: number; campaigns: number; manual_status: { updated: number; not_updated: number } };
};
type ListRow = Record<string, string | number | boolean | string[] | null>;
type Metric = "customers" | "accounts" | "accounts_spending" | "negative_balance" | "needs_topup" | "unlinked" | "accounts_unassigned" | "review";

const TITLES: Record<Metric, string> = {
  customers: "Khách trong kỳ (tab khách trong nguồn)", accounts: "TKQC ghi nhận trong kỳ", accounts_spending: "TKQC có chi tiêu",
  negative_balance: "Khách số dư âm", needs_topup: "Khách cần nhắc nạp", unlinked: "Tab khách chưa liên kết",
  accounts_unassigned: "TKQC chưa xác nhận phân công", review: "Cảnh báo dữ liệu cần rà soát",
};

const COLUMNS: Record<string, string> = {
  sheet_id: "Sheet ID", source_sheet: "Tab nguồn", profile_status: "Trạng thái tab", customer_id: "ID hồ sơ", customer_name: "Hồ sơ nội bộ",
  link_status: "Liên kết", balance_vnd: "Số dư (VND)", threshold_vnd: "Ngưỡng (VND)", account_id: "ID TKQC", tabs: "Tab chứa TKQC",
  day_rows: "Số dòng ngày", spend_known: "Đủ dữ liệu chi tiêu", has_spend: "Có chi tiêu", assignment_known: "Đã có phân công xác nhận",
  severity: "Mức độ", source: "Ô/nguồn", message: "Nội dung",
};

function Card({ label, value, note, metric, onOpen, tone }: { label: string; value: number | null; note?: string; metric: Metric; onOpen: (m: Metric) => void; tone?: string }) {
  return (
    <button type="button" className="card" style={{ textAlign: "left", cursor: "pointer" }} onClick={() => onOpen(metric)} aria-label={`Mở danh sách: ${label}`}>
      <div className="label">{label}</div>
      <div className={`value ${tone ?? ""}`}>{value == null ? "Chưa đủ dữ liệu" : value}</div>
      {note && <div className="muted">{note}</div>}
    </button>
  );
}

export default function OperationsOverview() {
  const [data, setData] = useState<OpsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<Metric | null>(null);
  const [list, setList] = useState<{ metric: Metric; rows: ListRow[] } | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    fetchJson<OpsOverview>("/dashboard/operations-overview").then(setData).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  const openMetric = (metric: Metric) => {
    setOpen(metric); setList(null); setListError(null);
    fetchJson<{ rows: ListRow[] }>(`/dashboard/operations-overview/${metric}`)
      .then((r) => setList({ metric, rows: r.rows }))
      .catch((e: Error) => setListError(e.message));
  };

  if (error) return <p className="error-box">Không đọc được tổng quan vận hành: {error} <button type="button" onClick={load}>Thử lại</button></p>;
  if (!data) return <p className="loading">Đang tải tổng quan vận hành…</p>;
  const m = data.metrics;
  const src = data.source;
  return (
    <section aria-label="Tổng quan vận hành">
      <h1>Tổng quan vận hành</h1>
      {src ? <p>
        Kỳ <strong>{src.period}</strong> · Nguồn mặc định: {src.name} · {src.closed ? "Đã chốt" : "Tạm tính"} ·
        Đồng bộ gần nhất: {src.read_at ? fmtTime(src.read_at) : "Chưa có bản lưu"} · Tự đồng bộ: {src.sync_enabled ? "Bật" : "Tắt"}
        {src.last_attempt?.status === "ERROR" && <span className="bad"> · Lần đọc gần nhất lỗi (đang giữ bản thành công trước)</span>}
      </p> : <p className="notice">{data.message ?? "Chưa chọn nguồn Sheets mặc định."} <Link href="/sheets#saved-sources">Quản lý nguồn</Link></p>}
      <p className="muted">Số liệu từ bản lưu Sheets, không phải ngân sách hay trạng thái Meta thời gian thực. <Link href="/#tong">Xem tổng tài chính</Link></p>
      {m ? <div className="cards">
        <Card label="Khách trong kỳ" value={m.customers.count} metric="customers" onOpen={openMetric} note={`${m.customers.linked} đã liên kết hồ sơ`} />
        <Card label="TKQC ghi nhận trong kỳ" value={m.accounts.count} metric="accounts" onOpen={openMetric}
          note={m.accounts.spend_unknown ? `${m.accounts.spend_unknown} TKQC chưa đủ dữ liệu chi tiêu` : undefined} />
        <Card label="TKQC có chi tiêu" value={m.accounts.spending} metric="accounts_spending" onOpen={openMetric} />
        <Card label="Khách số dư âm" value={m.negative_balance.count} metric="negative_balance" onOpen={openMetric}
          tone={m.negative_balance.count > 0 ? "bad" : ""} note={m.negative_balance.balance_missing ? `${m.negative_balance.balance_missing} khách chưa có số dư hợp lệ` : undefined} />
        <Card label="Khách cần nhắc nạp" value={m.needs_topup.count} metric="needs_topup" onOpen={openMetric}
          note={m.needs_topup.thresholds_missing ? `${m.needs_topup.thresholds_missing} khách liên kết chưa có ngưỡng` : undefined} />
      </div> : src && <p className="notice">Chưa đủ dữ liệu: nguồn chưa có bản lưu hợp lệ.</p>}
      {data.tasks && <>
        <div className="section-title">Việc cần xử lý</div>
        <ul>{data.tasks.map((t) => <li key={t.key}>
          <button type="button" onClick={() => openMetric(t.key === "sync_error" ? "review" : (t.key as Metric))} disabled={t.key === "sync_error"}>{t.label}: {t.count}</button>{" "}
          <Link href={t.href}>Xử lý</Link></li>)}</ul>
      </>}
      {open && <div className="notice" role="region" aria-label={TITLES[open]}>
        <strong>{TITLES[open]}</strong>{" "}<button type="button" onClick={() => { setOpen(null); setList(null); }}>Đóng</button>
        {listError && <p className="error-box">{listError} <button type="button" onClick={() => openMetric(open)}>Thử lại</button></p>}
        {!list && !listError && <p className="loading">Đang tải danh sách…</p>}
        {list && list.metric === open && (list.rows.length === 0 ? <p>Không có mục nào.</p> : <div style={{ overflowX: "auto" }}><table>
          <thead><tr>{Object.keys(list.rows[0]).map((k) => <th key={k}>{COLUMNS[k] ?? k}</th>)}</tr></thead>
          <tbody>{list.rows.map((row, i) => <tr key={i}>{Object.entries(row).map(([k, v]) => <td key={k}>
            {v == null ? "Chưa đủ dữ liệu" : k.endsWith("_vnd") ? formatBalanceVnd(String(v)) : Array.isArray(v) ? v.join(", ") : typeof v === "boolean" ? (v ? "Có" : "Không") : String(v)}</td>)}</tr>)}</tbody>
        </table></div>)}
      </div>}
      <details className="my-2"><summary>Chi tiết nguồn và cách đếm</summary>
        <ul>
          <li>Khách trong kỳ: số tab khách hiển thị trong nguồn (đã loại tab ẩn và tab tổng hợp, tab bị bỏ qua); không phải số hồ sơ nội bộ đã liên kết.
            {m && ` Tab lỗi nguồn/cấu trúc: ${m.customers.error_tabs}.`}</li>
          <li>TKQC: ID duy nhất trong dữ liệu nguồn (không đếm số dòng ngày), không phải số TKQC đang hoạt động trên Meta.</li>
          <li>Số dư âm: dựa trên L1 hợp lệ; ô trống hoặc tab lỗi không coi là 0.</li>
          <li>Nhắc nạp: chỉ khách đã liên kết, có ngưỡng và số dư hợp lệ không âm ≤ ngưỡng; khách chưa có ngưỡng không phải “an toàn” hay “cần nạp”.</li>
        </ul>
      </details>
      <details className="my-2"><summary>Dữ liệu nội bộ</summary>
        <p className="muted">{data.internal.label}. Có thể gồm dữ liệu thử nghiệm; không dùng làm số liệu vận hành.</p>
        <ul>
          <li>Hồ sơ khách nội bộ: {data.internal.customers}</li>
          <li>Ad account nội bộ: {data.internal.ad_accounts} · Campaign nội bộ: {data.internal.campaigns}</li>
          <li>Trạng thái tài khoản nhập tay: đã cập nhật khác mặc định {data.internal.manual_status.updated} · chưa cập nhật/giá trị mặc định (không có bằng chứng xác nhận) {data.internal.manual_status.not_updated}</li>
        </ul>
        <Link href="/accounts">Mở quản lý TKQC</Link>
      </details>
    </section>
  );
}
