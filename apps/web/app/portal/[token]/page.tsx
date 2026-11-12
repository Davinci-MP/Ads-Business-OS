"use client";

import { use, useCallback, useEffect, useState } from "react";
import { getClientPortalData, ClientPortalData } from "../../../lib/api";

const kindLabels: Record<string, string> = {
  DEPOSIT: "Nạp ngân sách",
  ACTUAL_SPEND: "Chi tiêu quảng cáo",
  SERVICE_FEE: "Phí dịch vụ",
  ACCOUNT_FEE: "Phí thuê tài khoản",
  CARD_FEE: "Phí thẻ VCC",
};

export default function ClientPortalPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = use(params);
  const [data, setData] = useState<ClientPortalData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadPortal = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await getClientPortalData(token);
      setData(res);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Cổng thông tin không tồn tại hoặc liên kết đã hết hạn."
      );
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void loadPortal();
  }, [loadPortal]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0B0F19] text-gray-100 flex flex-col items-center justify-center p-6">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-[#6A57F2] to-[#1FB89A] animate-pulse flex items-center justify-center shadow-lg shadow-purple-500/20 mb-4">
          <span className="font-bold text-white text-lg">OS</span>
        </div>
        <p className="text-sm text-gray-400 font-mono">Đang tải dữ liệu cổng thông tin khách hàng...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-[#0B0F19] text-gray-100 flex flex-col items-center justify-center p-6 text-center">
        <div className="w-14 h-14 rounded-2xl bg-rose-500/20 border border-rose-500/30 flex items-center justify-center text-rose-400 text-2xl mb-4">
          
        </div>
        <h2 className="text-xl font-bold text-white tracking-tight">Truy Cập Không Thành Công</h2>
        <p className="text-sm text-gray-400 max-w-md mt-2 mb-6">{error}</p>
        <button
          onClick={() => void loadPortal()}
          className="px-5 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-semibold text-xs transition"
          type="button"
        >
          Thử Lại
        </button>
      </div>
    );
  }

  const { customer, balances, assigned_accounts, recent_transactions } = data;

  return (
    <div className="min-h-screen bg-[#121212] text-white p-4 sm:p-6 lg:p-8 w-full space-y-8 font-sans">
      {/* Brand & Greeting Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#111827] p-6 rounded-3xl border border-[#1F2937] shadow-xl">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-[#6A57F2] via-[#7B61FF] to-[#1FB89A] flex items-center justify-center shadow-lg shadow-purple-500/25 flex-none">
            <span className="font-extrabold text-white text-xl">OS</span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-white tracking-tight m-0">
                {customer.name}
              </h1>
              <span className="text-xs px-2.5 py-0.5 rounded-full font-mono bg-purple-500/20 text-purple-300 border border-purple-500/30">
                VIP Portal
              </span>
            </div>
            <p className="text-xs text-gray-400 mt-0.5">
              Phí dịch vụ: <strong className="text-emerald-400 font-mono">{(customer.fee_rate * 100).toFixed(1)}%</strong> • Chế độ: <span className="font-mono text-gray-300">{customer.recon_mode}</span>
            </p>
          </div>
        </div>

        <button
          onClick={() => void loadPortal()}
          className="px-4 py-2 rounded-xl text-xs font-semibold text-gray-300 hover:text-white bg-[#1F2937] hover:bg-[#2A3449] border border-[#374151] transition flex items-center gap-1.5 self-start md:self-auto"
          type="button"
        >
          <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
          </svg>
          Làm mới số liệu
        </button>
      </div>

      {/* Balances & Deposit Instructions */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {balances.map((b) => (
          <div
            key={b.currency}
            className={`p-6 rounded-3xl border flex flex-col justify-between transition ${
              b.low_alert
                ? "bg-rose-950/20 border-rose-500/40 shadow-lg shadow-rose-950/30"
                : "bg-[#111827] border-[#1F2937]"
            }`}
          >
            <div>
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-400 font-mono">
                  Số Dư Ví {b.currency}
                </span>
                {b.low_alert ? (
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">
                    Cần nạp thêm
                  </span>
                ) : (
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                    Khả dụng
                  </span>
                )}
              </div>

              <div className="text-3xl font-extrabold font-mono tabular-nums text-white mt-3">
                {Number(b.amount).toLocaleString(b.currency === "VND" ? "vi-VN" : "en-US", {
                  minimumFractionDigits: b.currency === "VND" ? 0 : 2,
                })}{" "}
                <span className="text-lg text-purple-300 font-normal">{b.currency}</span>
              </div>

              {b.low_threshold && (
                <div className="text-xs text-gray-400 mt-2 font-mono">
                  Ngưỡng cảnh báo: {Number(b.low_threshold).toLocaleString(b.currency === "VND" ? "vi-VN" : "en-US")} {b.currency}
                </div>
              )}
            </div>

            <div className="mt-5 pt-4 border-t border-[#1F2937]/80">
              <span className="text-[11px] font-semibold text-gray-400 block mb-1">
                Hướng dẫn nạp tiền:
              </span>
              <p className="text-xs text-gray-300 whitespace-pre-line bg-[#0B0F19]/50 p-2.5 rounded-xl border border-[#1F2937]">
                {b.deposit_info}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Assigned Ad Accounts & Spend */}
      <div className="bg-[#111827] rounded-3xl border border-[#1F2937] p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-[#1F2937] pb-4">
          <div>
            <h2 className="text-base font-bold text-white tracking-tight m-0">
              Tài Khoản Quảng Cáo Đang Chạy
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">
              Danh sách tài khoản quảng cáo được phân bổ kèm tổng chi tiêu tích lũy từ khi bắt đầu chạy.
            </p>
          </div>
          <span className="text-xs font-mono text-purple-300 bg-purple-500/10 px-3 py-1 rounded-full border border-purple-500/20">
            {assigned_accounts.length} Tài khoản
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-[#0B0F19]/60 text-gray-400 border-b border-[#1F2937]">
                <th className="py-3 px-4 font-semibold">Tên Tài Khoản QC</th>
                <th className="py-3 px-4 font-semibold">Mã Meta ID</th>
                <th className="py-3 px-4 font-semibold">Múi Giờ</th>
                <th className="py-3 px-4 font-semibold">Chiến Dịch</th>
                <th className="py-3 px-4 font-semibold text-right">Tổng Chi Tiêu Tích Lũy</th>
                <th className="py-3 px-4 font-semibold text-right">Trạng Thái</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1F2937]/50">
              {assigned_accounts.length > 0 ? (
                assigned_accounts.map((acc) => (
                  <tr key={acc.meta_ad_account_id} className="hover:bg-[#1A2234]/50 transition">
                    <td className="py-3 px-4 font-semibold text-gray-200">{acc.name}</td>
                    <td className="py-3 px-4 font-mono text-gray-400">{acc.meta_ad_account_id}</td>
                    <td className="py-3 px-4 font-mono text-gray-400">{acc.timezone_name}</td>
                    <td className="py-3 px-4 font-mono text-purple-300">{acc.campaign_count} campaigns</td>
                    <td className="py-3 px-4 font-mono font-bold text-right text-sm tabular-nums text-white">
                      ${acc.total_spend.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                        {acc.status}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-gray-500">
                    Chưa có tài khoản quảng cáo nào được phân bổ.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Recent Ledger Transactions */}
      <div className="bg-[#111827] rounded-3xl border border-[#1F2937] p-6 shadow-xl space-y-4">
        <div className="border-b border-[#1F2937] pb-4">
          <h2 className="text-base font-bold text-white tracking-tight m-0">
            Lịch Sử Biến Động Ngân Sách
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">
            Lịch sử nạp tiền, chi phí quảng cáo và phí dịch vụ đã được xác nhận ghi sổ.
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-[#0B0F19]/60 text-gray-400 border-b border-[#1F2937]">
                <th className="py-3 px-4 font-semibold">Mã GD</th>
                <th className="py-3 px-4 font-semibold">Khoản Ghi</th>
                <th className="py-3 px-4 font-semibold text-right">Số Tiền</th>
                <th className="py-3 px-4 font-semibold">Bằng Chứng / Ghi Chú</th>
                <th className="py-3 px-4 font-semibold">Thời Gian Ghi Sổ</th>
                <th className="py-3 px-4 font-semibold text-right">Trạng Thái</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1F2937]/50">
              {recent_transactions.length > 0 ? (
                recent_transactions.map((tx) => (
                  <tr key={tx.id} className="hover:bg-[#1A2234]/50 transition">
                    <td className="py-3 px-4 font-mono text-gray-500">#{tx.id}</td>
                    <td className="py-3 px-4 font-medium text-gray-300">
                      {kindLabels[tx.kind] || tx.kind}
                    </td>
                    <td className="py-3 px-4 font-mono font-bold text-right tabular-nums text-white">
                      {tx.kind === "DEPOSIT" ? "+" : "-"}
                      {Number(tx.amount).toLocaleString(tx.currency === "VND" ? "vi-VN" : "en-US", {
                        minimumFractionDigits: tx.currency === "VND" ? 0 : 2,
                      })}{" "}
                      {tx.currency}
                    </td>
                    <td className="py-3 px-4 text-gray-400 max-w-sm truncate" title={tx.evidence}>
                      {tx.evidence}
                    </td>
                    <td className="py-3 px-4 font-mono text-gray-400">
                      {tx.executed_at ? new Date(tx.executed_at).toLocaleString("vi-VN") : "—"}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <span className="px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                        {tx.status}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-gray-500">
                    Chưa có giao dịch biến động nào.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Footer */}
      <div className="text-center text-xs text-gray-500 pt-6">
        © 2026 Ads Business OS • Cổng thông tin khách hàng an toàn &amp; bảo mật
      </div>
    </div>
  );
}
