"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  approvePrepaidTransaction,
  generatePortalToken,
  getPrepaidOverview,
  processPrepaidTransactions,
  rejectPrepaidTransaction,
  requestPrepaidTransaction,
  setPrepaidThreshold,
  ClientBalanceItem,
  LedgerTransactionItem,
  PrepaidOverview,
  fetchJson,
} from "../../lib/api";

const kindLabels: Record<string, string> = {
  DEPOSIT: "Nạp ngân sách",
  ACTUAL_SPEND: "Chi tiêu QC",
  SERVICE_FEE: "Phí dịch vụ",
  ACCOUNT_FEE: "Phí thuê TK",
  CARD_FEE: "Phí thẻ VCC",
};

const statusConfig: Record<string, { label: string; badge: string }> = {
  CREATED: { label: "Chờ duyệt", badge: "bg-amber-500/20 text-amber-300 border-amber-500/30" },
  APPROVED: { label: "Đã duyệt", badge: "bg-blue-500/20 text-blue-300 border-blue-500/30" },
  EXECUTED: { label: "Đã ghi sổ", badge: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" },
  REJECTED: { label: "Đã từ chối", badge: "bg-rose-500/20 text-rose-400 border-rose-500/30" },
  NEEDS_CONFIRMATION: { label: "Cần xác nhận lại", badge: "bg-purple-500/20 text-purple-300 border-purple-500/30" },
};

export default function BalancesPage() {
  const [data, setData] = useState<PrepaidOverview | null>(null);
  const [customers, setCustomers] = useState<{ id: number; name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error?: boolean } | null>(null);

  // Modals
  const [showDepositModal, setShowDepositModal] = useState(false);
  const [showThresholdModal, setShowThresholdModal] = useState(false);
  const [showPortalModal, setShowPortalModal] = useState(false);
  const [portalInfo, setPortalInfo] = useState<{ name: string; url: string; token: string } | null>(null);

  // Deposit Form State
  const [depCustomer, setDepCustomer] = useState("");
  const [depCurrency, setDepCurrency] = useState("VND");
  const [depKind, setDepKind] = useState("DEPOSIT");
  const [depAmount, setDepAmount] = useState("");
  const [depSource, setDepSource] = useState("");
  const [depEvidence, setDepEvidence] = useState("");
  const [depActor, setDepActor] = useState("admin_ketoan");

  // Threshold Form State
  const [threshCustomer, setThreshCustomer] = useState("");
  const [threshCurrency, setThreshCurrency] = useState("VND");
  const [threshValue, setThreshValue] = useState("");
  const [threshDepositInfo, setThreshDepositInfo] = useState("");
  const [threshActor, setThreshActor] = useState("admin_ketoan");

  const attemptKey = useRef<string>(crypto.randomUUID());

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [overview, custList] = await Promise.all([
        getPrepaidOverview(),
        fetchJson<{ id: number; name: string }[]>("/customers"),
      ]);
      setData(overview);
      setCustomers(custList);
    } catch (err: unknown) {
      setNotice({
        text: err instanceof Error ? err.message : "Không thể tải dữ liệu sổ ngân sách.",
        error: true,
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // Handle Create Deposit Request
  const handleCreateDeposit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!depCustomer || !depAmount || !depEvidence) {
      setNotice({ text: "Vui lòng nhập đầy đủ các thông tin bắt buộc.", error: true });
      return;
    }
    setBusy(true);
    try {
      await requestPrepaidTransaction({
        customer_id: Number(depCustomer),
        currency: depCurrency,
        amount: depAmount,
        kind: depKind,
        evidence: depEvidence,
        actor: depActor,
        idempotency_key: attemptKey.current,
        source_ledger_id: depSource ? Number(depSource) : null,
      });
      attemptKey.current = crypto.randomUUID();
      setShowDepositModal(false);
      setDepAmount("");
      setDepEvidence("");
      setDepSource("");
      setNotice({ text: "Đã tạo đề nghị ghi sổ thành công. Đang chờ phê duyệt." });
      await loadData();
    } catch (err: unknown) {
      setNotice({ text: err instanceof Error ? err.message : "Lỗi tạo đề nghị ghi sổ.", error: true });
    } finally {
      setBusy(false);
    }
  };

  // Handle Set Threshold
  const handleSetThreshold = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!threshCustomer) {
      setNotice({ text: "Vui lòng chọn khách hàng.", error: true });
      return;
    }
    setBusy(true);
    try {
      await setPrepaidThreshold(Number(threshCustomer), {
        currency: threshCurrency,
        low_threshold: threshValue ? threshValue : null,
        deposit_info: threshDepositInfo,
        actor: threshActor,
      });
      setShowThresholdModal(false);
      setNotice({ text: "Đã lưu ngưỡng cảnh báo và thông tin nạp tiền thành công." });
      await loadData();
    } catch (err: unknown) {
      setNotice({ text: err instanceof Error ? err.message : "Lỗi cập nhật ngưỡng.", error: true });
    } finally {
      setBusy(false);
    }
  };

  // Handle Approve Transaction
  const handleApprove = async (txId: number) => {
    setBusy(true);
    try {
      await approvePrepaidTransaction(txId, "admin_duyet");
      setNotice({ text: `Đã phê duyệt giao dịch #${txId}.` });
      await loadData();
    } catch (err: unknown) {
      setNotice({ text: err instanceof Error ? err.message : "Lỗi duyệt giao dịch.", error: true });
    } finally {
      setBusy(false);
    }
  };

  // Handle Reject Transaction
  const handleReject = async (txId: number) => {
    setBusy(true);
    try {
      await rejectPrepaidTransaction(txId, "admin_duyet");
      setNotice({ text: `Đã từ chối giao dịch #${txId}.` });
      await loadData();
    } catch (err: unknown) {
      setNotice({ text: err instanceof Error ? err.message : "Lỗi từ chối giao dịch.", error: true });
    } finally {
      setBusy(false);
    }
  };

  // Handle Batch Execution
  const handleProcessBatch = async () => {
    setBusy(true);
    try {
      const res = await processPrepaidTransactions();
      setNotice({ text: res.message });
      await loadData();
    } catch (err: unknown) {
      setNotice({ text: err instanceof Error ? err.message : "Lỗi ghi sổ các khoản đã duyệt.", error: true });
    } finally {
      setBusy(false);
    }
  };

  // Handle Portal Token Generation
  const handleGeneratePortal = async (customerId: number, customerName: string) => {
    setBusy(true);
    try {
      const res = await generatePortalToken(customerId);
      const fullUrl = `${window.location.origin}/portal/${res.portal_token}`;
      setPortalInfo({ name: customerName, url: fullUrl, token: res.portal_token });
      setShowPortalModal(true);
    } catch (err: unknown) {
      setNotice({ text: err instanceof Error ? err.message : "Lỗi tạo link cổng khách hàng.", error: true });
    } finally {
      setBusy(false);
    }
  };

  // KPI Calculations
  const totalBalancesVnd =
    data?.balances
      .filter((b) => b.currency === "VND")
      .reduce((sum, b) => sum + Number(b.amount || 0), 0) || 0;
  const totalBalancesUsd =
    data?.balances
      .filter((b) => b.currency === "USD")
      .reduce((sum, b) => sum + Number(b.amount || 0), 0) || 0;
  const lowAlertCount = data?.balances.filter((b) => b.low).length || 0;
  const pendingTxCount = data?.transactions.filter((t) => t.status === "CREATED").length || 0;

  return (
    <div className="w-full space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#111827] p-6 rounded-2xl border border-[#1F2937]">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-gray-100 tracking-tight m-0">
              Sổ Trả Trước &amp; Quản Lý Công Nợ
            </h2>
            <span className="text-xs px-2.5 py-0.5 rounded-full font-mono bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
              Prepaid Ledger
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            Quản trị độc lập từng loại tiền tệ (VND / USD / USDT), kiểm soát nạp tiền, chi tiêu và đối soát theo thời gian thực.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => void loadData()}
            disabled={loading || busy}
            className="px-3.5 py-2 rounded-xl text-xs font-medium text-gray-300 hover:text-white bg-[#1F2937] hover:bg-[#2A3449] border border-[#374151] transition flex items-center gap-1.5"
            type="button"
          >
            <svg className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
            </svg>
            Làm mới
          </button>
          <button
            onClick={() => setShowThresholdModal(true)}
            disabled={busy}
            className="px-3.5 py-2 rounded-xl text-xs font-medium text-gray-300 hover:text-white bg-[#1F2937] hover:bg-[#2A3449] border border-[#374151] transition flex items-center gap-1.5"
            type="button"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 20h9M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
            </svg>
            Ngưỡng &amp; Cảnh báo
          </button>
          <button
            onClick={() => setShowDepositModal(true)}
            disabled={busy}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 shadow-md shadow-purple-600/20 transition flex items-center gap-1.5"
            type="button"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            + Đề Nghị Nạp Tiền
          </button>
        </div>
      </div>

      {/* Notification Toast */}
      {notice && (
        <div
          className={`p-4 rounded-xl text-xs flex items-center justify-between border ${
            notice.error
              ? "bg-rose-500/10 text-rose-300 border-rose-500/30"
              : "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
          }`}
        >
          <span>{notice.text}</span>
          <button
            onClick={() => setNotice(null)}
            className="text-gray-400 hover:text-white"
            type="button"
          >
            
          </button>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[#111827] p-5 rounded-2xl border border-[#1F2937]">
          <span className="text-xs font-medium text-gray-400">Tổng Số Dư Trả Trước (VND)</span>
          <div className="text-2xl font-bold font-mono tabular-nums text-white mt-1">
            {totalBalancesVnd.toLocaleString("vi-VN")} ₫
          </div>
          <div className="text-[11px] text-gray-500 mt-2 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            Khách nạp tiền khả dụng
          </div>
        </div>

        <div className="bg-[#111827] p-5 rounded-2xl border border-[#1F2937]">
          <span className="text-xs font-medium text-gray-400">Tổng Số Dư Trả Trước (USD)</span>
          <div className="text-2xl font-bold font-mono tabular-nums text-white mt-1">
            ${totalBalancesUsd.toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] text-gray-500 mt-2 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />
            Tài khoản ngoại tệ
          </div>
        </div>

        <div className="bg-[#111827] p-5 rounded-2xl border border-[#1F2937]">
          <span className="text-xs font-medium text-gray-400">Cảnh Báo Số Dư Thấp</span>
          <div className={`text-2xl font-bold font-mono tabular-nums mt-1 ${lowAlertCount > 0 ? "text-rose-400" : "text-emerald-400"}`}>
            {lowAlertCount} Khách hàng
          </div>
          <div className="text-[11px] text-gray-500 mt-2">
            {lowAlertCount > 0 ? " Cần nhắc khách nạp thêm ngân sách" : "Tất cả trên mức an toàn"}
          </div>
        </div>

        <div className="bg-[#111827] p-5 rounded-2xl border border-[#1F2937]">
          <span className="text-xs font-medium text-gray-400">Giao Dịch Đang Chờ Duyệt</span>
          <div className={`text-2xl font-bold font-mono tabular-nums mt-1 ${pendingTxCount > 0 ? "text-amber-300" : "text-gray-400"}`}>
            {pendingTxCount} Khoản
          </div>
          <div className="text-[11px] text-gray-500 mt-2 flex items-center justify-between">
            <span>Cần kế toán xác nhận</span>
            {pendingTxCount > 0 && (
              <span className="text-[10px] bg-amber-500/20 text-amber-300 px-1.5 py-0.5 rounded">Action</span>
            )}
          </div>
        </div>
      </div>

      {/* Client Balances Table */}
      <div className="bg-[#111827] rounded-2xl border border-[#1F2937] overflow-hidden">
        <div className="p-4 border-b border-[#1F2937] flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-200 tracking-tight">
            Số Dư Ngân Sách Từng Khách Hàng
          </h3>
          <span className="text-xs text-gray-500 font-mono">
            {data?.balances.length || 0} tài khoản ngân sách
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-[#0B0F19]/60 text-gray-400 border-b border-[#1F2937]">
                <th className="py-3 px-4 font-semibold">Khách Hàng</th>
                <th className="py-3 px-4 font-semibold">Tiền Tệ</th>
                <th className="py-3 px-4 font-semibold text-right">Số Dư Hiện Tại</th>
                <th className="py-3 px-4 font-semibold text-right">Ngưỡng Báo Động</th>
                <th className="py-3 px-4 font-semibold">Tình Trạng</th>
                <th className="py-3 px-4 font-semibold text-right">Cổng Khách Hàng (Portal)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1F2937]/50">
              {data?.balances && data.balances.length > 0 ? (
                data.balances.map((b) => (
                  <tr key={b.id} className="hover:bg-[#1A2234]/50 transition">
                    <td className="py-3 px-4 font-medium text-gray-200">
                      {b.customer_name || `Khách hàng #${b.customer_id}`}
                    </td>
                    <td className="py-3 px-4 font-mono text-purple-300">{b.currency}</td>
                    <td className="py-3 px-4 font-mono font-bold text-right text-sm tabular-nums text-white">
                      {Number(b.amount).toLocaleString(b.currency === "VND" ? "vi-VN" : "en-US", {
                        minimumFractionDigits: b.currency === "VND" ? 0 : 2,
                      })}{" "}
                      {b.currency}
                    </td>
                    <td className="py-3 px-4 font-mono text-right text-gray-400 tabular-nums">
                      {b.low_threshold
                        ? `${Number(b.low_threshold).toLocaleString(b.currency === "VND" ? "vi-VN" : "en-US")} ${b.currency}`
                        : "Chưa đặt"}
                    </td>
                    <td className="py-3 px-4">
                      {b.low ? (
                        <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/30">
                           Số dư thấp
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                           Bình thường
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => handleGeneratePortal(b.customer_id, b.customer_name || `Khách #${b.customer_id}`)}
                        className="px-2.5 py-1 rounded-lg text-[11px] font-medium bg-purple-500/15 text-purple-300 hover:bg-purple-500/25 border border-purple-500/30 transition inline-flex items-center gap-1"
                        type="button"
                      >
                        <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
                          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
                        </svg>
                        Tạo Link Portal
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-gray-500">
                    Chưa có sổ ngân sách nào được khởi tạo.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Ledger Transactions Table */}
      <div className="bg-[#111827] rounded-2xl border border-[#1F2937] overflow-hidden">
        <div className="p-4 border-b border-[#1F2937] flex items-center justify-between flex-wrap gap-3">
          <div>
            <h3 className="text-sm font-semibold text-gray-200 tracking-tight">
              Sổ Cái Giao Dịch &amp; Đề Nghị Ghi Sổ
            </h3>
            <span className="text-xs text-gray-500">
              Chỉ các khoản có bằng chứng xác minh và được duyệt mới trừ/cộng vào số dư thực tế.
            </span>
          </div>

          <button
            onClick={() => void handleProcessBatch()}
            disabled={busy}
            className="px-3.5 py-1.5 rounded-xl text-xs font-semibold text-emerald-300 bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 transition flex items-center gap-1.5"
            type="button"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="20 6 9 17 4 12" />
            </svg>
            Ghi Sổ Các Khoản Đã Duyệt
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-[#0B0F19]/60 text-gray-400 border-b border-[#1F2937]">
                <th className="py-3 px-4 font-semibold">Mã GD</th>
                <th className="py-3 px-4 font-semibold">Khách Hàng</th>
                <th className="py-3 px-4 font-semibold">Khoản Ghi</th>
                <th className="py-3 px-4 font-semibold text-right">Số Tiền</th>
                <th className="py-3 px-4 font-semibold">Trạng Thái</th>
                <th className="py-3 px-4 font-semibold">Bằng Chứng / Căn Cứ</th>
                <th className="py-3 px-4 font-semibold">Người Tạo</th>
                <th className="py-3 px-4 font-semibold text-right">Hành Động</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1F2937]/50">
              {data?.transactions && data.transactions.length > 0 ? (
                data.transactions.map((tx) => {
                  const cfg = statusConfig[tx.status] || {
                    label: tx.status,
                    badge: "bg-gray-800 text-gray-400",
                  };
                  return (
                    <tr key={tx.id} className="hover:bg-[#1A2234]/50 transition">
                      <td className="py-3 px-4 font-mono text-gray-500">#{tx.id}</td>
                      <td className="py-3 px-4 font-medium text-gray-200">
                        {customers.find((c) => c.id === tx.customer_id)?.name || `ID ${tx.customer_id}`}
                      </td>
                      <td className="py-3 px-4">
                        <span className="text-gray-300 font-medium">{kindLabels[tx.kind] || tx.kind}</span>
                      </td>
                      <td className="py-3 px-4 font-mono font-bold text-right tabular-nums text-white">
                        {tx.kind === "DEPOSIT" ? "+" : "-"}
                        {Number(tx.amount).toLocaleString(tx.currency === "VND" ? "vi-VN" : "en-US", {
                          minimumFractionDigits: tx.currency === "VND" ? 0 : 2,
                        })}{" "}
                        {tx.currency}
                      </td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${cfg.badge}`}>
                          {cfg.label}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-gray-300 max-w-xs truncate" title={tx.evidence}>
                        {tx.evidence}
                      </td>
                      <td className="py-3 px-4 text-gray-400 font-mono text-[11px]">{tx.requested_by}</td>
                      <td className="py-3 px-4 text-right">
                        {tx.status === "CREATED" && (
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              onClick={() => void handleApprove(tx.id)}
                              disabled={busy}
                              className="px-2 py-1 rounded-md text-[11px] font-semibold bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 border border-emerald-500/30 transition"
                              type="button"
                            >
                              Duyệt
                            </button>
                            <button
                              onClick={() => void handleReject(tx.id)}
                              disabled={busy}
                              className="px-2 py-1 rounded-md text-[11px] font-semibold bg-rose-500/20 text-rose-300 hover:bg-rose-500/30 border border-rose-500/30 transition"
                              type="button"
                            >
                              Từ chối
                            </button>
                          </div>
                        )}
                        {tx.status === "APPROVED" && (
                          <span className="text-[11px] text-blue-400 font-medium">Chờ ghi sổ</span>
                        )}
                        {tx.status === "EXECUTED" && (
                          <span className="text-[11px] text-emerald-400 font-mono"> Hoàn tất</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-gray-500">
                    Chưa có giao dịch ghi sổ nào.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* MODAL 1: Create Deposit / Deduction Request */}
      {showDepositModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fadeIn">
          <div className="bg-[#111827] border border-[#1F2937] rounded-2xl w-full max-w-lg p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-[#1F2937] pb-3">
              <h3 className="text-base font-bold text-white tracking-tight">
                Tạo Đề Nghị Ghi Sổ Ngân Sách
              </h3>
              <button
                onClick={() => setShowDepositModal(false)}
                className="text-gray-400 hover:text-white"
                type="button"
              >
                
              </button>
            </div>

            <form onSubmit={handleCreateDeposit} className="space-y-4 text-xs">
              <div>
                <label className="block text-gray-300 font-medium mb-1">Khách hàng (*)</label>
                <select
                  required
                  value={depCustomer}
                  onChange={(e) => setDepCustomer(e.target.value)}
                  className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                >
                  <option value="">-- Chọn khách hàng --</option>
                  {customers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} (ID: {c.id})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-gray-300 font-medium mb-1">Loại khoản (*)</label>
                  <select
                    value={depKind}
                    onChange={(e) => setDepKind(e.target.value)}
                    className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                  >
                    {Object.entries(kindLabels).map(([k, label]) => (
                      <option key={k} value={k}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-gray-300 font-medium mb-1">Tiền tệ (*)</label>
                  <select
                    value={depCurrency}
                    onChange={(e) => setDepCurrency(e.target.value)}
                    className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500 font-mono"
                  >
                    <option value="VND">VND (Đồng)</option>
                    <option value="USD">USD (Đô la)</option>
                    <option value="USDT">USDT (Tether)</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-gray-300 font-medium mb-1">Số tiền (*)</label>
                <input
                  type="text"
                  required
                  inputMode="decimal"
                  placeholder="Ví dụ: 10000000"
                  value={depAmount}
                  onChange={(e) => setDepAmount(e.target.value)}
                  className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white font-mono text-sm focus:outline-none focus:border-purple-500"
                />
              </div>

              {depKind !== "DEPOSIT" && (
                <div>
                  <label className="block text-gray-300 font-medium mb-1">Mã khoản nguồn đã chốt (*)</label>
                  <input
                    type="number"
                    min="1"
                    placeholder="Mã ID khoản trong LedgerEntry"
                    value={depSource}
                    onChange={(e) => setDepSource(e.target.value)}
                    className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white font-mono focus:outline-none focus:border-purple-500"
                  />
                </div>
              )}

              <div>
                <label className="block text-gray-300 font-medium mb-1">
                  Bằng chứng nhận tiền / Căn cứ trừ tiền (*)
                </label>
                <textarea
                  required
                  rows={2}
                  placeholder="Mã giao dịch ngân hàng Vietcombank, hình ảnh UNC hoặc link đối soát..."
                  value={depEvidence}
                  onChange={(e) => setDepEvidence(e.target.value)}
                  className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                />
              </div>

              <div>
                <label className="block text-gray-300 font-medium mb-1">Người đề xuất (*)</label>
                <input
                  type="text"
                  required
                  value={depActor}
                  onChange={(e) => setDepActor(e.target.value)}
                  className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500 font-mono"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-[#1F2937]">
                <button
                  type="button"
                  onClick={() => setShowDepositModal(false)}
                  className="px-4 py-2 rounded-xl text-gray-400 hover:text-white hover:bg-gray-800 transition"
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  disabled={busy}
                  className="px-5 py-2 rounded-xl font-semibold text-white bg-purple-600 hover:bg-purple-500 transition"
                >
                  Gửi Đề Nghị
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2: Set Threshold & Bank Info */}
      {showThresholdModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fadeIn">
          <div className="bg-[#111827] border border-[#1F2937] rounded-2xl w-full max-w-lg p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-[#1F2937] pb-3">
              <h3 className="text-base font-bold text-white tracking-tight">
                Cấu Hình Ngưỡng Cảnh Báo &amp; Nạp Tiền
              </h3>
              <button
                onClick={() => setShowThresholdModal(false)}
                className="text-gray-400 hover:text-white"
                type="button"
              >
                
              </button>
            </div>

            <form onSubmit={handleSetThreshold} className="space-y-4 text-xs">
              <div>
                <label className="block text-gray-300 font-medium mb-1">Khách hàng (*)</label>
                <select
                  required
                  value={threshCustomer}
                  onChange={(e) => setThreshCustomer(e.target.value)}
                  className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                >
                  <option value="">-- Chọn khách hàng --</option>
                  {customers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-gray-300 font-medium mb-1">Tiền tệ</label>
                <select
                  value={threshCurrency}
                  onChange={(e) => setThreshCurrency(e.target.value)}
                  className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white font-mono"
                >
                  <option value="VND">VND</option>
                  <option value="USD">USD</option>
                  <option value="USDT">USDT</option>
                </select>
              </div>

              <div>
                <label className="block text-gray-300 font-medium mb-1">
                  Mức số dư tối thiểu kích hoạt cảnh báo (Để trống để tắt)
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  placeholder="Ví dụ: 3000000"
                  value={threshValue}
                  onChange={(e) => setThreshValue(e.target.value)}
                  className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white font-mono focus:outline-none focus:border-purple-500"
                />
              </div>

              <div>
                <label className="block text-gray-300 font-medium mb-1">
                  Thông tin tài khoản nhận tiền (VietQR / STK Ngân Hàng)
                </label>
                <textarea
                  rows={3}
                  placeholder="STK: 1903... Techcombank - Tên: NGUYEN VAN A. Nội dung: [TENKH] NAP ADS"
                  value={threshDepositInfo}
                  onChange={(e) => setThreshDepositInfo(e.target.value)}
                  className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-[#1F2937]">
                <button
                  type="button"
                  onClick={() => setShowThresholdModal(false)}
                  className="px-4 py-2 rounded-xl text-gray-400 hover:text-white hover:bg-gray-800 transition"
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  disabled={busy}
                  className="px-5 py-2 rounded-xl font-semibold text-white bg-purple-600 hover:bg-purple-500 transition"
                >
                  Lưu Cấu Hình
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 3: Portal Link Generated */}
      {showPortalModal && portalInfo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fadeIn">
          <div className="bg-[#111827] border border-[#1F2937] rounded-2xl w-full max-w-lg p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-[#1F2937] pb-3">
              <h3 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
                <span className="text-emerald-400"></span> Link Cổng Khách Hàng (Client Portal)
              </h3>
              <button
                onClick={() => setShowPortalModal(false)}
                className="text-gray-400 hover:text-white"
                type="button"
              >
                
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <p className="text-gray-300">
                Link truy cập riêng tư dành cho khách hàng <strong className="text-purple-300">{portalInfo.name}</strong>. Khách hàng có thể tự xem số dư ví trả trước, chi tiêu thực tế của các tài khoản quảng cáo mà không cần tài khoản đăng nhập.
              </p>

              <div>
                <label className="block text-gray-400 mb-1 font-medium">Đường dẫn Portal:</label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    readOnly
                    value={portalInfo.url}
                    className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-gray-200 font-mono text-xs select-all"
                  />
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(portalInfo.url);
                      setNotice({ text: "Đã sao chép link Portal vào Clipboard!" });
                    }}
                    className="px-3 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-semibold flex-none"
                    type="button"
                  >
                    Sao chép
                  </button>
                </div>
              </div>

              <div className="bg-[#1A2234] p-3 rounded-xl border border-[#374151] text-[11px] text-gray-400">
                 <strong>Bảo mật:</strong> Token được mã hóa 64 ký tự hex ngẫu nhiên. Nếu nghi ngờ lộ link, quản trị viên có thể bấm tạo mới để vô hiệu hóa link cũ.
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => setShowPortalModal(false)}
                className="px-4 py-2 rounded-xl text-gray-300 hover:text-white bg-gray-800 transition text-xs"
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
