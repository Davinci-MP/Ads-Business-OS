"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchJson, fmtTime, patchJson, type SavedSheetSource } from "../lib/api";
import { loadPref, savePref } from "../lib/prefs";
import { formatBalanceVnd, formatVnd } from "../lib/vnd.mjs";

type CustomerBalance = {
  customer_id: number;
  name: string;
  link_status: "LINKED" | "UNLINKED" | "LINK_REVIEW" | "SOURCE_ERROR" | "NO_SNAPSHOT";
  source_sheet: string | null;
  budget_deposits_vnd: string | null;
  spend_vnd: string | null;
  fee: string | null;
  current_balance: string | null;
  budget_alert_threshold_vnd: string | null;
  low_balance: boolean;
  account_count: number;
  conflicting_accounts: number;
  data_status: string | null;
};

type Overview = {
  source_id: number;
  source_name: string;
  period: string;
  snapshot_id: number | null;
  read_at: string | null;
  quality: string | null;
  closed_snapshot_id: number | null;
  last_attempt: { status: string; error: string | null } | null;
  customers: CustomerBalance[];
};

const linkLabels: Record<CustomerBalance["link_status"], string> = {
  LINKED: "Đã liên kết",
  UNLINKED: "Chưa liên kết tab",
  LINK_REVIEW: "Cần xác nhận lại tab",
  SOURCE_ERROR: "Lỗi dữ liệu tab",
  NO_SNAPSHOT: "Chưa có bản lưu",
};

function money(value: string | null, balance = false): string {
  return value == null ? "Chưa có dữ liệu" : `${balance ? formatBalanceVnd(value) : formatVnd(value)} VND`;
}

function isNegative(value: string | null): boolean {
  return value !== null && value.startsWith("-") && /[1-9]/.test(value);
}

export function BudgetThreshold({ row, onSaved }: {
  row: Pick<CustomerBalance, "customer_id" | "budget_alert_threshold_vnd">;
  onSaved: () => void;
}) {
  const [amount, setAmount] = useState(row.budget_alert_threshold_vnd ?? "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => setAmount(row.budget_alert_threshold_vnd ?? ""), [row.budget_alert_threshold_vnd]);
  const save = async (value: string | null) => {
    setBusy(true);
    setMessage(null);
    try {
      await patchJson(`/customers/${row.customer_id}/budget-alert`, { threshold_vnd: value });
      setMessage(value === null ? "Đã xóa ngưỡng." : "Đã lưu ngưỡng.");
      onSaved();
    } catch (e) {
      setMessage(`Không lưu được: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };
  return <details>
    <summary>Ngưỡng nhắc nạp: {row.budget_alert_threshold_vnd === null ? "Chưa cấu hình" : money(row.budget_alert_threshold_vnd)}</summary>
    <label>Ngưỡng VND <input value={amount} inputMode="decimal" onChange={(e) => setAmount(e.target.value)} /></label>
    <button disabled={busy || !amount.trim()} onClick={() => void save(amount.trim())}>Lưu ngưỡng</button>{" "}
    <button disabled={busy || row.budget_alert_threshold_vnd === null} onClick={() => void save(null)}>Xóa ngưỡng</button>
    {message && <p role="status">{message}</p>}
  </details>;
}

export default function CustomerSheets({ customerId }: { customerId?: number }) {
  const [sources, setSources] = useState<SavedSheetSource[] | null>(null);
  const [sourceId, setSourceId] = useState(() => loadPref("customerSheets.source", ""));
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    savePref("customerSheets.source", sourceId);
  }, [sourceId]);

  useEffect(() => {
    const controller = new AbortController();
    setSources(null);
    setError(null);
    fetchJson<{ sources: SavedSheetSource[] }>("/sheets/sources", { signal: controller.signal })
      .then(({ sources: items }) => {
        const active = items.filter((item) => item.active);
        setSources(active);
        setSourceId((previous) => active.some((item) => String(item.id) === previous)
          ? previous : String((active.find((item) => item.is_default) ?? active[0])?.id ?? ""));
      })
      .catch((e) => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : String(e)); });
    return () => controller.abort();
  }, [retry]);

  useEffect(() => {
    if (!sourceId) return;
    const controller = new AbortController();
    setOverview(null);
    setError(null);
    fetchJson<Overview>(`/sheets/sources/${sourceId}/customer-overview`, { signal: controller.signal })
      .then(setOverview)
      .catch((e) => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : String(e)); });
    return () => controller.abort();
  }, [sourceId, retry, version]);

  const rows = overview?.source_id === Number(sourceId)
    ? overview.customers.filter((row) => customerId === undefined || row.customer_id === customerId)
    : [];
  return (
    <section>
      <h2 className="section-title">Ngân sách khách từ Sheets</h2>
      <div className="status-form">
        <label>Kỳ và nguồn đang xem
          <select value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
            {!sources?.length && <option value="">Chưa có nguồn hoạt động</option>}
            {sources?.map((source) => <option key={source.id} value={source.id}>{source.period} · {source.name}</option>)}
          </select>
        </label>
        <Link href="/sheets#saved-sources">Quản lý nguồn và liên kết khách</Link>
      </div>
      {error && <p className="error-box">Không tải được dữ liệu: {error} <button onClick={() => setRetry((n) => n + 1)}>Thử lại</button></p>}
      {!error && (!sources || (sourceId && !overview)) && <p>Đang tải dữ liệu Sheets…</p>}
      {!error && sources?.length === 0 && <p>Chưa có nguồn tháng hoạt động.</p>}
      {overview && overview.source_id === Number(sourceId) && <>
        <p>Bản lưu gần nhất: {fmtTime(overview.read_at)} · {overview.quality ?? "Chưa có bản lưu"}
          {overview.closed_snapshot_id !== null && (overview.closed_snapshot_id === overview.snapshot_id ? " · Bản đã chốt" : " · Bản sau chốt để rà soát, không thay bản chốt")}
          {overview.last_attempt && ` · Lần đọc gần nhất: ${overview.last_attempt.status}`}
          {(overview.last_attempt?.status === "ERROR" || overview.last_attempt?.status === "INTERRUPTED") && " · Đang giữ bản lưu trước"}
        </p>
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead><tr><th>Khách</th><th>Nạp trong kỳ</th><th>Chi tiêu</th><th>Phí / lợi nhuận</th><th>Số dư Sheets</th><th>TKQC đã cấp</th><th>Dữ liệu</th><th>Thao tác</th></tr></thead>
            <tbody>{rows.map((row) => <tr key={row.customer_id}>
              <td><Link href={`/customers/${row.customer_id}`}>{row.name}</Link></td>
              <td>{money(row.budget_deposits_vnd)}</td><td>{money(row.spend_vnd)}</td><td>{money(row.fee)}</td>
              <td>{money(row.current_balance, true)}{isNegative(row.current_balance) ? <strong> · Đang nợ theo Sheets</strong>
                : row.low_balance && <strong> · Đến ngưỡng nhắc nạp</strong>}
                <BudgetThreshold row={row} onSaved={() => setVersion((n) => n + 1)} />
              </td>
              <td>{row.account_count}{row.conflicting_accounts > 0 && ` · ${row.conflicting_accounts} xung đột chưa tính`}</td>
              <td>{linkLabels[row.link_status]}{row.link_status === "LINKED" && row.data_status ? ` · ${row.data_status}` : ""}</td>
              <td><Link href={`/accounts?customerId=${row.customer_id}`}>TKQC</Link> · <Link href="/reports">Báo cáo / rà soát</Link></td>
            </tr>)}</tbody>
          </table>
        </div>
        {rows.length === 0 && <p>Không có khách phù hợp trong DB.</p>}
        <details><summary>Chi tiết dữ liệu</summary>
          <p>Chỉ dùng tab đã liên kết với khách trong nguồn này. Số dư là L1 của bản lưu, không phải Meta realtime; ô thiếu không phải 0.</p>
          {(overview.last_attempt?.status === "ERROR" || overview.last_attempt?.status === "INTERRUPTED") && <p>Lỗi đọc: {overview.last_attempt.error ?? "Không có chi tiết"}</p>}
          <p><Link href="/reports">Xem cảnh báo, ô nguồn và khoản chưa rõ ngày/kỳ</Link> · <Link href="/sheets#saved-sources">Xác nhận liên kết tab</Link></p>
        </details>
      </>}
    </section>
  );
}
