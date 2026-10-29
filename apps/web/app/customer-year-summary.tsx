"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchJson } from "../lib/api";
import { loadPref, savePref } from "../lib/prefs";
import { formatVnd } from "../lib/vnd.mjs";

const FLOW_FIELDS = [
  "budget_deposits_vnd",
  "spend_vnd",
  "fee",
  "billing_total",
  "usdt_received",
  "usdt_refunded",
  "usdt_net",
] as const;
type FlowField = (typeof FLOW_FIELDS)[number];
const VND_FIELDS: FlowField[] = ["budget_deposits_vnd", "spend_vnd", "fee", "billing_total"];

const FIELD_LABELS: Record<FlowField, string> = {
  budget_deposits_vnd: "Nạp trong kỳ",
  spend_vnd: "Chi tiêu",
  fee: "Phí",
  billing_total: "Tổng trừ",
  usdt_received: "USDT nhận",
  usdt_refunded: "USDT hoàn",
  usdt_net: "USDT ròng",
};

const STATE_LABELS: Record<string, string> = {
  PROVISIONAL: "Tạm (chưa chốt)",
  CLOSED: "Đã chốt",
  NOT_CLOSED: "Chưa chốt",
  NOT_CLOSED_NO_SOURCE: "Chưa có nguồn",
  CONFLICTING_CLOSURES: "Xung đột bản chốt",
  MISSING_SOURCE: "Thiếu nguồn",
  MISSING_SNAPSHOT: "Thiếu bản lưu",
};

const LINK_LABELS: Record<string, string> = {
  LINKED: "Đã liên kết",
  UNLINKED: "Chưa liên kết",
  LINK_REVIEW: "Cần xác nhận lại tab",
  SOURCE_ERROR: "Lỗi dữ liệu tab",
};

type MonthValue = { value: string | null; source: string | null };
type CustomerYearMonth = {
  period: string;
  state: string;
  link_state: string | null;
  source_id?: number;
  source_name?: string;
  active_source_id?: number;
  snapshot_id?: number;
  read_at?: string | null;
  quality?: string | null;
  closed_at?: string | null;
  closure_note?: string;
  last_attempt?: { status: string; error: string | null } | null;
  values: Partial<Record<FlowField, MonthValue>>;
};
type RankRow = {
  customer_id: number;
  name: string;
  months_with_value: Record<FlowField, number>;
  totals: Record<FlowField, string | null>;
};
type Summary = {
  year: number;
  basis: string;
  customer_id: number;
  customer_name: string;
  months: CustomerYearMonth[];
  months_with_value: Record<FlowField, number>;
  totals: Record<FlowField, { value: string | null; months_with_value: number; total_months: number }>;
  opening_balance: { period: string; value: string | null; source: string | null } | null;
  closing_balance: { period: string; value: string | null; source: string | null } | null;
  ranking: RankRow[];
  rank_by: string | null;
};

function flowValue(field: FlowField, value: MonthValue | undefined): string | null {
  if (!value || value.value == null) return null;
  const raw = String(value.value).trim();
  if (!VND_FIELDS.includes(field)) return `${formatVnd(raw)} USDT`;
  return `${formatVnd(raw)} VND`;
}

function cellText(field: FlowField, value: MonthValue | undefined): string {
  if (!value || value.value == null) return "—";
  const text = flowValue(field, value);
  return text ?? "—";
}

function cellTitle(field: FlowField, value: MonthValue | undefined): string | undefined {
  if (!value || value.value == null) return undefined;
  const parts: string[] = [];
  if (value.source) parts.push(`Nguồn: ${value.source}`);
  if (value.value != null) parts.push(`Giá trị gốc: ${value.value}`);
  else parts.push("Không có số");
  return parts.join(" · ");
}

export default function CustomerYearSummary({ customerId }: { customerId: number }) {
  const [year, setYear] = useState(() => loadPref("customerYear.year", String(new Date().getFullYear())));
  const [basis, setBasis] = useState(() => loadPref("customerYear.basis", "current"));
  const [rankBy, setRankBy] = useState(() => loadPref("customerYear.rankBy", ""));
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submit, setSubmit] = useState(0);

  useEffect(() => { savePref("customerYear.year", year); }, [year]);
  useEffect(() => { savePref("customerYear.basis", basis); }, [basis]);
  useEffect(() => { savePref("customerYear.rankBy", rankBy); }, [rankBy]);

  useEffect(() => {
    if (!submit) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({
      year, basis, customer_id: String(customerId),
    });
    if (rankBy) params.set("rank_by", rankBy);
    fetchJson<Summary>(`/sheets/sources/customer-year-summary?${params.toString()}`, { signal: controller.signal })
      .then((data) => setSummary(data))
      .catch((e) => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [submit, customerId, year, basis, rankBy]);

  useEffect(() => { setSubmit((n) => n + 1); }, [customerId]); // load lần đầu và khi đổi khách

  return (
    <section>
      <h2 className="section-title">Báo cáo Sheets theo năm</h2>
      <div className="status-form">
        <label>
          Năm
          <input
            aria-label="Năm báo cáo năm"
            type="number" min={1} max={9999} value={year}
            onChange={(e) => setYear(e.target.value)}
          />
        </label>
        <label>
          Chế độ dữ liệu
          <select
            aria-label="Chế độ dữ liệu năm"
            value={basis}
            onChange={(e) => setBasis(e.target.value)}
          >
            <option value="current">Bản đọc mới nhất của nguồn hiệu lực</option>
            <option value="closed">Chỉ bản chốt</option>
          </select>
        </label>
        <label>
          Xếp hạng theo
          <select
            aria-label="Xếp hạng theo chỉ tiêu"
            value={rankBy}
            onChange={(e) => setRankBy(e.target.value)}
          >
            <option value="">Không xếp hạng (theo tên)</option>
            {FLOW_FIELDS.map((field) => <option key={field} value={field}>{FIELD_LABELS[field]}</option>)}
          </select>
        </label>
        <button onClick={() => setSubmit((n) => n + 1)}>Xem báo cáo năm</button>
      </div>
      {error && <p className="error-box">Không tải được báo cáo năm: {error} <button onClick={() => setSubmit((n) => n + 1)}>Thử lại</button></p>}
      {loading && <p className="loading">Đang tải báo cáo năm…</p>}
      {summary && summary.customer_id === customerId && <>
        <p className="muted">
          {summary.basis === "closed"
            ? "Mỗi kỳ dùng đúng bản chốt; kỳ chưa chốt để trống, không tự thay bằng bản hiện hành."
            : "Mỗi kỳ dùng bản đọc thành công mới nhất của nguồn hiệu lực; nếu kỳ đã có bản chốt, bản này chỉ là bản đọc mới hơn (không ghi đè bản chốt)."}
          Không cộng số dư qua các tháng (D-052); ô thiếu hiển thị “—”, không thay bằng 0.
        </p>
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <Th>Tháng</Th><Th>Trạng thái</Th><Th>Liên kết tab</Th>
                {FLOW_FIELDS.map((field) => <Th key={field}>{FIELD_LABELS[field]}</Th>)}
              </tr>
            </thead>
            <tbody>
              {summary.months.map((month) => {
                const hasState = STATE_LABELS[month.state] ?? month.state;
                const linkLabel = month.link_state == null ? "—" : (LINK_LABELS[month.link_state] ?? month.link_state);
                const readInfo = [
                  month.state === "PROVISIONAL" || month.state === "CLOSED" ? `Bản #${month.snapshot_id}` : null,
                  month.last_attempt ? `Đọc gần nhất: ${month.last_attempt.status}` : null,
                ].filter(Boolean).join(" · ");
                return (
                  <tr key={month.period}>
                    <td><strong>{month.period}</strong></td>
                    <td>{hasState}{month.closure_note && <div style={{ fontSize: 11 }}>{month.closure_note}</div>}
                      {(month.state === "NOT_CLOSED" || month.state === "NOT_CLOSED_NO_SOURCE") &&
                        " · Không tự thay bằng bản hiện hành"}
                      {month.source_name && <div style={{ fontSize: 11 }}>{month.source_name}</div>}</td>
                    <td>{linkLabel}</td>
                    {FLOW_FIELDS.map((field) => (
                      <td key={field} title={cellTitle(field, month.values[field])}>
                        {cellText(field, month.values[field])}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <h3 className="section-title">Tổng phát sinh năm {summary.year} ({summary.basis === "closed" ? "chỉ bản chốt" : "hiện hành"})</h3>
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead><tr><Th>Chỉ tiêu</Th><Th>Tổng năm</Th><Th>Tháng có số</Th></tr></thead>
            <tbody>
              {FLOW_FIELDS.map((field) => (
                <tr key={field}>
                  <td>{FIELD_LABELS[field]}</td>
                  <td>{summary.totals[field].value == null ? "—" : flowValue(field, { value: summary.totals[field].value, source: null })}
                    {summary.totals[field].value == null && <div style={{ fontSize: 11 }}>Không tự tính từ số thiếu</div>}</td>
                  <td>{summary.months_with_value[field]}/{summary.totals[field].total_months}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p style={{ marginTop: 8 }}>
          Số dư đầu năm: {summary.opening_balance?.value != null
            ? <strong>{formatVnd(summary.opening_balance.value)} VND</strong>
            : "Chưa có dữ liệu"}
          {summary.opening_balance && (
            <span className="muted"> ({summary.opening_balance.period})</span>
          )}
          <br />
          Số dư đến kỳ {summary.closing_balance?.period ?? "—"}: {summary.closing_balance?.value != null
            ? <strong>{formatVnd(summary.closing_balance.value)} VND</strong>
            : <span>Chưa có dữ liệu</span>}
          {!summary.closing_balance && <span className="muted"> (chưa có kỳ nào có số dư hiện tại)</span>}
          {summary.closing_balance?.period !== `${summary.year}-12` &&
            <span className="muted"> — chưa phải số dư cuối năm vì chưa có tháng 12</span>}
        </p>

        <h3 className="section-title">Tổng hợp theo khách trong năm</h3>
        <p className="muted">Chỉ cộng các phát sinh (K1/F1/G1/H1 và USDT có căn cứ kỳ); không cộng số dư qua các tháng. Khách chưa liên kết tab không có số.</p>
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <Th>#</Th><Th>Khách</Th>
                {FLOW_FIELDS.map((field) => <Th key={field}>{FIELD_LABELS[field]}</Th>)}
              </tr>
            </thead>
            <tbody>
              {summary.ranking.map((row, index) => (
                <tr key={row.customer_id} style={row.customer_id === customerId ? { background: "#f4f8ff" } : undefined}>
                  <td>{index + 1}</td>
                  <td><Link href={`/customers/${row.customer_id}`}>{row.name}</Link></td>
                  {FLOW_FIELDS.map((field) => {
                    const value = row.totals[field];
                    return (
                      <td key={field}>{value == null ? "—" : flowValue(field, { value, source: null })}
                        <div style={{ fontSize: 11 }}>{row.months_with_value[field]} tháng có số</div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ marginTop: 8 }}>
          <Link href="/reports#tong">Xem tổng tất cả khách trong kỳ ở tab Tổng</Link>
        </div>
      </>}
    </section>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th style={{ whiteSpace: "nowrap" }}>{children}</th>;
}
