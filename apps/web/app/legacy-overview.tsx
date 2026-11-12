"use client";

import { useEffect, useState } from "react";
import { useApi } from "../components/ui";
import { type Overview } from "../lib/api";
import CustomersTotal from "./customers-total";
import OperationsOverview from "./operations-overview";
import CustomerSheets, { BudgetThreshold } from "./customer-sheets";
import TreasurySummary from "./treasury-summary";
import UnifiedOverviewWidget from "./unified-overview";

export default function OverviewPage() {
  const { data, error, loading, reload } = useApi<Overview>("/dashboard/overview");
  const [tab, setTab] = useState<"overview" | "customers" | "total">("overview");
  useEffect(() => {
    const update = () =>
      setTab(
        window.location.hash === "#tong"
          ? "total"
          : window.location.hash === "#khach-hang"
          ? "customers"
          : "overview"
      );
    update();
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);

  const legacyPending = tab === "customers" && (loading || error || !data);
  const rows = data?.students ?? [];
  return (
    <div className="w-full space-y-6">
      <UnifiedOverviewWidget />
      <TreasurySummary />
      <nav aria-label="Khách hàng" className="my-5 flex gap-2 overflow-x-auto pb-1">
        <a
          href="#tong-quan"
          aria-current={tab === "overview" ? "page" : undefined}
          className={`px-4 py-2 rounded-full text-xs font-bold uppercase tracking-[1.4px] transition ${
            tab === "overview"
              ? "bg-[#1ed760] text-black shadow-md"
              : "bg-[#1f1f1f] text-[#b3b3b3] hover:text-white hover:bg-[#282828] border border-[#333333]"
          }`}
        >
          Tổng quan vận hành
        </a>
        <a
          href="#khach-hang"
          aria-current={tab === "customers" ? "page" : undefined}
          className={`px-4 py-2 rounded-full text-xs font-bold uppercase tracking-[1.4px] transition ${
            tab === "customers"
              ? "bg-[#1ed760] text-black shadow-md"
              : "bg-[#1f1f1f] text-[#b3b3b3] hover:text-white hover:bg-[#282828] border border-[#333333]"
          }`}
        >
          Danh sách khách hàng
        </a>
        <a
          href="#tong"
          aria-current={tab === "total" ? "page" : undefined}
          className={`px-4 py-2 rounded-full text-xs font-bold uppercase tracking-[1.4px] transition ${
            tab === "total"
              ? "bg-[#1ed760] text-black shadow-md"
              : "bg-[#1f1f1f] text-[#b3b3b3] hover:text-white hover:bg-[#282828] border border-[#333333]"
          }`}
        >
          Tổng tài chính
        </a>
      </nav>
      {tab === "overview" ? (
        <OperationsOverview />
      ) : tab === "total" ? (
        <CustomersTotal />
      ) : legacyPending ? (
        loading ? (
          <p className="loading">Đang tải danh sách khách…</p>
        ) : (
          <p className="error-box">
            Không đọc được dữ liệu: {error}{" "}
            <button
              type="button"
              onClick={() => void reload()}
              className="ml-2 px-3 py-1 rounded-full bg-[#1f1f1f] text-white hover:bg-[#282828] text-xs font-bold uppercase tracking-[1.4px]"
            >
              Thử lại
            </button>
          </p>
        )
      ) : (
        <>
          <p className="mb-4">
            <a href="/sheets#customer-setup" className="text-[#1ed760] hover:underline font-bold text-xs uppercase tracking-[1.2px]">
              + Thiết lập khách hàng từ Sheets ↗
            </a>
          </p>
          <div className="section-title">Khách hàng nội bộ</div>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Tên khách</th>
                  <th>Chế độ đối soát</th>
                  <th>Phí dịch vụ</th>
                  <th>Ngưỡng nhắc nạp</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id}>
                    <td className="font-mono text-[#b3b3b3]">{c.id}</td>
                    <td>
                      <a href={`/customers/${c.id}`} className="text-white hover:text-[#1ed760] font-bold">
                        {c.name}
                      </a>
                    </td>
                    <td><span className="tag ok">{c.recon_mode}</span></td>
                    <td className="font-mono">{c.fee_rate}</td>
                    <td>
                      <BudgetThreshold
                        row={{
                          customer_id: c.id,
                          budget_alert_threshold_vnd: c.budget_alert_threshold_vnd,
                        }}
                        onSaved={() => void reload()}
                      />
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={5} className="text-center text-[#b3b3b3] py-8">Chưa có khách trong DB.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <CustomerSheets />
          <p className="notice muted text-xs text-[#b3b3b3] mt-4">
            Dữ liệu lấy trực tiếp từ backend DB — chỉ đọc; không ghi Google Sheets Production.
          </p>
        </>
      )}
    </div>
  );
}
