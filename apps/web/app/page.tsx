"use client";

import { useEffect, useState } from "react";
import { useApi } from "../components/ui";
import { type Overview } from "../lib/api";
import CustomersTotal from "./customers-total";
import OperationsOverview from "./operations-overview";
import CustomerSheets, { BudgetThreshold } from "./customer-sheets";

export default function OverviewPage() {
  const { data, error, loading, reload } = useApi<Overview>("/dashboard/overview");
  const [tab, setTab] = useState<"overview" | "customers" | "total">("overview");
  useEffect(() => {
    const update = () => setTab(window.location.hash === "#tong" ? "total" : window.location.hash === "#khach-hang" ? "customers" : "overview");
    update();
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);

  const legacyPending = tab === "customers" && (loading || error || !data);
  const rows = data?.students ?? [];
  return (
    <main className="page">
      <nav aria-label="Khách hàng" className="my-4 flex gap-4 border-b border-slate-200">
        <a href="#tong-quan" aria-current={tab === "overview" ? "page" : undefined} className={tab === "overview" ? "font-bold text-sky-700" : ""}>Tổng quan</a>
        <a href="#khach-hang" aria-current={tab === "customers" ? "page" : undefined} className={tab === "customers" ? "font-bold text-sky-700" : ""}>Danh sách khách hàng</a>
        <a href="#tong" aria-current={tab === "total" ? "page" : undefined} className={tab === "total" ? "font-bold text-sky-700" : ""}>Tổng</a>
      </nav>
      {tab === "overview" ? <OperationsOverview /> : tab === "total" ? <CustomersTotal /> : legacyPending ? (
        loading ? <p className="loading">Đang tải danh sách khách…</p>
          : <p className="error-box">Không đọc được dữ liệu: {error} <button type="button" onClick={() => void reload()}>Thử lại</button></p>
      ) : <>
      <p><a href="/sheets#customer-setup">Thiết lập khách hàng từ Sheets</a></p>
      <div className="section-title">Khách hàng nội bộ</div>
      <div style={{ overflowX: "auto" }}><table>
        <thead><tr><th>ID</th><th>Tên khách</th><th>Chế độ đối soát</th><th>Phí dịch vụ</th><th>Ngưỡng nhắc nạp</th></tr></thead>
        <tbody>
          {rows.map((c) => <tr key={c.id}>
            <td>{c.id}</td><td><a href={`/customers/${c.id}`}>{c.name}</a></td><td>{c.recon_mode}</td><td>{c.fee_rate}</td>
            <td><BudgetThreshold row={{ customer_id: c.id, budget_alert_threshold_vnd: c.budget_alert_threshold_vnd }} onSaved={() => void reload()} /></td>
          </tr>)}
          {rows.length === 0 && <tr><td colSpan={5}>Chưa có khách trong DB.</td></tr>}
        </tbody>
      </table></div>
      <CustomerSheets />
      <p className="notice muted">
        Dữ liệu lấy trực tiếp từ backend DB — chỉ đọc; không ghi Google Sheets Production.
      </p>
      </>}
    </main>
  );
}
