"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getVccCardTransactions,
  getVccRiskOverview,
  syncVccRisk,
  updateVccCardThreshold,
  VccRiskAlert,
  VccRiskCard,
  VccRiskOverview,
  VccTransactionItem,
} from "../../lib/vcc-risk-api";

export default function VccRiskPage() {
  const [data, setData] = useState<VccRiskOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [search, setSearch] = useState("");
  const [filterRisk, setFilterRisk] = useState<"ALL" | "CRITICAL" | "WARNING" | "SAFE">("ALL");

  // State cho Modal biến động số dư
  const [selectedCard, setSelectedCard] = useState<VccRiskCard | null>(null);
  const [txns, setTxns] = useState<VccTransactionItem[]>([]);
  const [loadingTxns, setLoadingTxns] = useState(false);

  // State cho việc sửa ngưỡng trực tiếp
  const [editingCardId, setEditingCardId] = useState<string | null>(null);
  const [thresholdInput, setThresholdInput] = useState<string>("");
  const [savingThreshold, setSavingThreshold] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const res = await getVccRiskOverview();
      setData(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setActionMessage(`Lỗi tải dữ liệu: ${msg}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleSync = async () => {
    try {
      setSyncing(true);
      setActionMessage("Đang đồng bộ thẻ VCC từ PingPong và quét nợ Meta...");
      const res = await syncVccRisk();
      setData(res);
      setActionMessage("Đồng bộ thành công! Dữ liệu số dư và nợ TKQC đã được cập nhật.");
      setTimeout(() => setActionMessage(null), 4000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setActionMessage(`Lỗi đồng bộ: ${msg}`);
    } finally {
      setSyncing(false);
    }
  };

  const openTxnModal = async (card: VccRiskCard) => {
    setSelectedCard(card);
    setLoadingTxns(true);
    setTxns([]);
    try {
      const list = await getVccCardTransactions(card.id, 50);
      setTxns(list);
    } catch (err: unknown) {
      console.error("Lỗi tải biến động:", err);
    } finally {
      setLoadingTxns(false);
    }
  };

  const handleSaveThreshold = async (cardId: string) => {
    const val = parseFloat(thresholdInput);
    if (isNaN(val) || val < 0) {
      alert("Vui lòng nhập ngưỡng số dư hợp lệ (lớn hơn hoặc bằng 0).");
      return;
    }
    try {
      setSavingThreshold(true);
      const res = await updateVccCardThreshold(cardId, val);
      setActionMessage(res.message);
      setEditingCardId(null);
      await loadData();
      setTimeout(() => setActionMessage(null), 4000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Lỗi cập nhật: ${msg}`);
    } finally {
      setSavingThreshold(false);
    }
  };

  const filteredCards = useMemo(() => {
    if (!data?.cards) return [];
    return data.cards.filter((card) => {
      // Lọc theo trạng thái rủi ro
      if (filterRisk !== "ALL" && card.risk_status !== filterRisk) return false;

      // Tìm kiếm theo 4 số cuối, remark, tên TKQC hoặc act_id
      if (!search.trim()) return true;
      const q = search.toLowerCase();
      const matchLast4 = card.last_four.includes(q);
      const matchRemark = card.remark?.toLowerCase().includes(q);
      const matchAccName = card.ad_account?.name?.toLowerCase().includes(q);
      const matchActId = card.ad_account?.act_id?.toLowerCase().includes(q);
      return matchLast4 || matchRemark || matchAccName || matchActId;
    });
  }, [data?.cards, filterRisk, search]);

  return (
    <div className="w-full space-y-6 text-white">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[#282828] pb-5">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="p-2 rounded-xl bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
              
            </span>
            <h1 className="text-2xl font-bold tracking-tight text-white m-0">
              Quản Trị Thẻ VCC & Rủi Ro Thanh Toán Meta
            </h1>
          </div>
          <p className="text-sm text-[#b3b3b3] mt-1">
            Đồng bộ thẻ ảo PingPong Issuing 2.7.1, liên kết chéo TKQC Meta, cảnh báo tụt ngưỡng và thiếu hụt quỹ Master.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleSync}
            disabled={syncing}
            className="flex items-center gap-2 px-5 py-2.5 rounded-full font-bold text-xs uppercase tracking-[1.4px] bg-[#1ed760] hover:bg-[#1fdf64] text-black shadow-md transition-all disabled:opacity-50"
          >
            <span className={syncing ? "animate-spin" : ""}></span>
            {syncing ? "Đang Quét Rủi Ro..." : "Đồng Bộ & Quét Rủi Ro"}
          </button>
        </div>
      </div>

      {/* Thông báo thao tác */}
      {actionMessage && (
        <div className="p-3.5 rounded-xl bg-slate-800/90 border border-[#333333] text-white text-sm flex items-center justify-between animate-fade-in shadow-md">
          <span>{actionMessage}</span>
          <button
            onClick={() => setActionMessage(null)}
            className="text-[#b3b3b3] hover:text-white text-xs px-2 py-1"
          >
             Đóng
          </button>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Master USD Balance */}
        <div className="bg-[#181818] border border-[#282828] rounded-[8px] p-5 shadow-xl backdrop-blur-md">
          <div className="text-xs font-semibold text-[#b3b3b3] uppercase tracking-wider">
            Quỹ Master USD PingPong
          </div>
          <div className="text-2xl font-black text-emerald-400 mt-2 font-mono">
            ${(data?.master_usd_balance ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </div>
          <div className="text-xs text-[#b3b3b3] mt-1">
            Số dư khả dụng để charge tất cả thẻ VCC
          </div>
        </div>

        {/* Card 2: Total Meta Debt */}
        <div className="bg-[#181818] border border-[#282828] rounded-[8px] p-5 shadow-xl backdrop-blur-md">
          <div className="text-xs font-semibold text-[#b3b3b3] uppercase tracking-wider">
            Tổng Dư Nợ TKQC Meta
          </div>
          <div className="text-2xl font-black text-rose-400 mt-2 font-mono">
            ${(data?.total_meta_debt ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </div>
          <div className="text-xs text-[#b3b3b3] mt-1">
            Số tiền Meta chuẩn bị tự động trừ thẻ
          </div>
        </div>

        {/* Card 3: Active VCCs */}
        <div className="bg-[#181818] border border-[#282828] rounded-[8px] p-5 shadow-xl backdrop-blur-md">
          <div className="text-xs font-semibold text-[#b3b3b3] uppercase tracking-wider">
            Thẻ VCC Đang Hoạt Động
          </div>
          <div className="text-2xl font-black text-sky-400 mt-2 font-mono">
            {data?.total_active_cards ?? 0}
          </div>
          <div className="text-xs text-[#b3b3b3] mt-1">
            Thẻ trạng thái ACTIVE sẵn sàng chi tiêu
          </div>
        </div>

        {/* Card 4: Critical Alerts */}
        <div className="bg-[#181818] border border-[#282828] rounded-[8px] p-5 shadow-xl backdrop-blur-md">
          <div className="text-xs font-semibold text-[#b3b3b3] uppercase tracking-wider">
            Cảnh Báo Nguy Hiểm
          </div>
          <div className="text-2xl font-black text-amber-400 mt-2 font-mono flex items-center gap-2">
            <span>{data?.critical_alerts_count ?? 0}</span>
            {data && data.critical_alerts_count > 0 && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/30 animate-pulse font-normal">
                Cần nạp thẻ ngay
              </span>
            )}
          </div>
          <div className="text-xs text-[#b3b3b3] mt-1">
            {data?.warning_alerts_count ?? 0} thẻ sắp chạm ngưỡng cảnh báo
          </div>
        </div>
      </div>

      {/* Dải Cảnh Báo Chủ Động (Active Alerts Banner) */}
      {data && data.alerts.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold uppercase tracking-wider text-[#b3b3b3] flex items-center gap-2 m-0">
              <span></span>
              <span>Cảnh Báo Rủi Ro Cần Xử Lý ({data.alerts.length})</span>
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {data.alerts.map((alert: VccRiskAlert, idx: number) => (
              <div
                key={idx}
                className={`p-4 rounded-xl border text-sm flex items-start gap-3 shadow-lg ${
                  alert.severity === "CRITICAL"
                    ? "bg-rose-950/40 border-rose-500/60 text-rose-200"
                    : "bg-amber-950/40 border-amber-500/50 text-amber-200"
                }`}
              >
                <span className="text-lg flex-shrink-0">
                  {alert.severity === "CRITICAL" ? "" : ""}
                </span>
                <div className="space-y-1">
                  <div className="font-semibold">{alert.message}</div>
                  <div className="text-xs opacity-75 font-mono">
                    Quy tắc: {alert.rule} • Mức độ: {alert.severity}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Thanh Công Cụ & Bộ Lọc Thẻ */}
      <div className="bg-[#181818] border border-[#282828] rounded-[8px] p-4 shadow-xl backdrop-blur-md flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setFilterRisk("ALL")}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
              filterRisk === "ALL"
                ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                : "bg-slate-800 text-[#b3b3b3] hover:bg-slate-700"
            }`}
          >
            Tất cả ({data?.cards.length ?? 0})
          </button>
          <button
            onClick={() => setFilterRisk("CRITICAL")}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
              filterRisk === "CRITICAL"
                ? "bg-rose-600 text-white shadow-md shadow-rose-600/30"
                : "bg-slate-800 text-rose-300 hover:bg-slate-700"
            }`}
          >
             Nguy cơ tụt ngưỡng ({data?.cards.filter((c) => c.risk_status === "CRITICAL").length ?? 0})
          </button>
          <button
            onClick={() => setFilterRisk("WARNING")}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
              filterRisk === "WARNING"
                ? "bg-amber-600 text-white shadow-md shadow-amber-600/30"
                : "bg-slate-800 text-amber-300 hover:bg-slate-700"
            }`}
          >
             Sắp hết tiền ({data?.cards.filter((c) => c.risk_status === "WARNING").length ?? 0})
          </button>
          <button
            onClick={() => setFilterRisk("SAFE")}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
              filterRisk === "SAFE"
                ? "bg-emerald-600 text-white shadow-md shadow-emerald-600/30"
                : "bg-slate-800 text-emerald-300 hover:bg-slate-700"
            }`}
          >
             An toàn ({data?.cards.filter((c) => c.risk_status === "SAFE").length ?? 0})
          </button>
        </div>

        <div className="w-full md:w-72">
          <input
            type="text"
            placeholder="Tìm 4 số cuối, remark, tên TKQC..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-[#1f1f1f] border border-[#333333] text-white placeholder-slate-400 rounded-xl px-3.5 py-2 text-sm focus:border-indigo-500 focus:outline-none"
          />
        </div>
      </div>

      {/* Bảng Danh Sách Thẻ VCC & Mapping TKQC */}
      <div className="bg-[#181818] border border-[#282828] rounded-[8px] shadow-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="border-b border-[#282828] bg-slate-900/80 text-xs font-semibold uppercase tracking-wider text-[#b3b3b3]">
                <th className="py-3.5 px-4">4 Số Cuối</th>
                <th className="py-3.5 px-4">Remark (Tên TK/Khách)</th>
                <th className="py-3.5 px-4 text-right">Số Dư Thẻ (USD)</th>
                <th className="py-3.5 px-4">TKQC Gắn Kèm (Tên & ID)</th>
                <th className="py-3.5 px-4 text-right">Nợ TKQC (Balance)</th>
                <th className="py-3.5 px-4 text-center">Cảnh Báo Khi Dưới (USD)</th>
                <th className="py-3.5 px-4 text-center">Trạng Thái Rủi Ro</th>
                <th className="py-3.5 px-4 text-center">Hành Động</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {loading && !data ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-[#b3b3b3]">
                    <span className="inline-block animate-spin mr-2"></span> Đang tải dữ liệu thẻ VCC...
                  </td>
                </tr>
              ) : filteredCards.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-[#b3b3b3]">
                    Không tìm thấy thẻ VCC nào phù hợp với bộ lọc hiện tại.
                  </td>
                </tr>
              ) : (
                filteredCards.map((card) => {
                  const isCritical = card.risk_status === "CRITICAL";
                  const isWarning = card.risk_status === "WARNING";
                  const isEditing = editingCardId === card.id;

                  return (
                    <tr
                      key={card.id}
                      className={`transition-colors ${
                        isCritical
                          ? "bg-rose-950/20 border-l-4 border-l-rose-500 hover:bg-rose-950/30"
                          : isWarning
                          ? "bg-amber-950/10 border-l-4 border-l-amber-500 hover:bg-amber-950/20"
                          : "hover:bg-slate-800/40"
                      }`}
                    >
                      {/* Cột 1: 4 số cuối & PAN */}
                      <td className="py-3.5 px-4 font-mono font-bold text-white">
                        <div className="flex items-center gap-2">
                          <span className="px-2 py-0.5 rounded-md bg-slate-800 border border-[#333333] text-xs">
                            *{card.last_four}
                          </span>
                          <span className="text-xs text-[#b3b3b3] hidden sm:inline">
                            {card.card_number_masked}
                          </span>
                        </div>
                      </td>

                      {/* Cột 2: Remark */}
                      <td className="py-3.5 px-4 font-medium text-white">
                        {card.remark || "—"}
                      </td>

                      {/* Cột 3: Số dư thẻ */}
                      <td className="py-3.5 px-4 text-right font-mono font-bold">
                        <span
                          className={
                            isCritical
                              ? "text-rose-400"
                              : isWarning
                              ? "text-amber-400"
                              : "text-emerald-400"
                          }
                        >
                          ${card.available_balance.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                        </span>
                      </td>

                      {/* Cột 4: TKQC gắn kèm */}
                      <td className="py-3.5 px-4">
                        {card.ad_account ? (
                          <div className="space-y-0.5">
                            <div className="font-medium text-white flex items-center gap-1.5">
                              <span>{card.ad_account.name}</span>
                              {card.ad_account.status_dot && (
                                <span
                                  className={`w-2 h-2 rounded-full ${
                                    card.ad_account.status_dot === "LIVE"
                                      ? "bg-emerald-400"
                                      : "bg-rose-500"
                                  }`}
                                />
                              )}
                            </div>
                            <div className="text-xs font-mono text-[#b3b3b3]">
                              {card.ad_account.act_id}
                            </div>
                          </div>
                        ) : (
                          <span className="text-xs text-[#b3b3b3] italic">
                            Chưa khớp TKQC (Tự do)
                          </span>
                        )}
                      </td>

                      {/* Cột 5: Nợ TKQC */}
                      <td className="py-3.5 px-4 text-right font-mono font-bold">
                        {card.ad_account ? (
                          <span
                            className={
                              card.ad_account.balance > card.available_balance
                                ? "text-rose-400 animate-pulse"
                                : "text-[#b3b3b3]"
                            }
                          >
                            ${card.ad_account.balance.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                          </span>
                        ) : (
                          <span className="text-[#b3b3b3]">—</span>
                        )}
                      </td>

                      {/* Cột 6: Ngưỡng cảnh báo (Inline Editor) */}
                      <td className="py-3.5 px-4 text-center font-mono">
                        {isEditing ? (
                          <div className="flex items-center justify-center gap-1.5">
                            <input
                              type="number"
                              min="0"
                              step="1"
                              value={thresholdInput}
                              onChange={(e) => setThresholdInput(e.target.value)}
                              className="w-20 bg-[#1f1f1f] border border-indigo-500 rounded-lg px-2 py-1 text-xs text-right text-white focus:outline-none"
                              autoFocus
                              onKeyDown={(e) => {
                                if (e.key === "Enter") void handleSaveThreshold(card.id);
                                if (e.key === "Escape") setEditingCardId(null);
                              }}
                            />
                            <button
                              onClick={() => handleSaveThreshold(card.id)}
                              disabled={savingThreshold}
                              className="px-2 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs"
                            >
                              
                            </button>
                            <button
                              onClick={() => setEditingCardId(null)}
                              className="px-2 py-1 bg-slate-700 hover:bg-slate-600 text-[#b3b3b3] rounded-lg text-xs"
                            >
                              
                            </button>
                          </div>
                        ) : (
                          <div
                            onClick={() => {
                              setEditingCardId(card.id);
                              setThresholdInput(String(card.low_balance_threshold));
                            }}
                            className="cursor-pointer group flex items-center justify-center gap-1 text-[#b3b3b3] hover:text-indigo-400"
                            title="Bấm để sửa ngưỡng cảnh báo"
                          >
                            <span>${card.low_balance_threshold}</span>
                            <span className="text-[10px] text-[#b3b3b3] group-hover:text-indigo-400">
                              
                            </span>
                          </div>
                        )}
                      </td>

                      {/* Cột 7: Trạng thái rủi ro */}
                      <td className="py-3.5 px-4 text-center">
                        <span
                          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${
                            isCritical
                              ? "bg-rose-500/20 text-rose-300 border border-rose-500/40 animate-pulse"
                              : isWarning
                              ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                              : "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                          }`}
                        >
                          {card.risk_label}
                        </span>
                      </td>

                      {/* Cột 8: Hành động */}
                      <td className="py-3.5 px-4 text-center">
                        <button
                          onClick={() => openTxnModal(card)}
                          className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800 hover:bg-slate-700 text-white border border-[#333333] transition-all"
                        >
                          Xem biến động
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal Biến Động Số Dư (vcc_transactions) */}
      {selectedCard && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-fade-in">
          <div className="bg-[#111827] border border-[#282828] rounded-[8px] w-full max-w-3xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
            {/* Modal Header */}
            <div className="p-5 border-b border-[#282828] flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-white m-0 flex items-center gap-2">
                  <span></span>
                  <span>Biến Động Giao Dịch Thẻ *{selectedCard.last_four}</span>
                </h3>
                <p className="text-xs text-[#b3b3b3] mt-1">
                  Remark: {selectedCard.remark || "—"} • Số dư khả dụng:{" "}
                  <span className="font-mono font-bold text-emerald-400">
                    ${selectedCard.available_balance.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                  </span>
                </p>
              </div>

              <button
                onClick={() => setSelectedCard(null)}
                className="w-8 h-8 rounded-full bg-slate-800 hover:bg-slate-700 text-[#b3b3b3] hover:text-white flex items-center justify-center text-sm"
              >
                
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-5 overflow-y-auto flex-1">
              {loadingTxns ? (
                <div className="py-12 text-center text-[#b3b3b3]">
                  <span className="inline-block animate-spin mr-2"></span> Đang tải lịch sử giao dịch từ PingPong...
                </div>
              ) : txns.length === 0 ? (
                <div className="py-12 text-center text-[#b3b3b3]">
                  Chưa có giao dịch uỷ quyền hoặc thanh toán nào được ghi nhận cho thẻ này.
                </div>
              ) : (
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-[#282828] bg-slate-900 text-[#b3b3b3] uppercase font-semibold">
                      <th className="py-2.5 px-3">Thời Gian</th>
                      <th className="py-2.5 px-3">Đơn Vị Chấp Nhận (Merchant)</th>
                      <th className="py-2.5 px-3 text-right">Uỷ Quyền (Auth)</th>
                      <th className="py-2.5 px-3 text-right">Quyết Toán (Settle)</th>
                      <th className="py-2.5 px-3 text-center">Trạng Thái</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono">
                    {txns.map((t) => (
                      <tr key={t.id} className="hover:bg-slate-800/30">
                        <td className="py-2.5 px-3 text-[#b3b3b3]">
                          {t.transaction_time ? t.transaction_time.replace("T", " ").slice(0, 19) : "—"}
                        </td>
                        <td className="py-2.5 px-3 font-sans font-medium text-white">
                          {t.merchant_name}
                        </td>
                        <td className="py-2.5 px-3 text-right text-[#b3b3b3]">
                          ${t.auth_amount.toFixed(2)}
                        </td>
                        <td className="py-2.5 px-3 text-right font-bold text-rose-400">
                          ${t.settle_amount.toFixed(2)}
                        </td>
                        <td className="py-2.5 px-3 text-center">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-semibold font-sans ${
                              t.status === "SETTLED"
                                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                : t.status === "AUTHORIZED"
                                ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                                : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                            }`}
                          >
                            {t.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-[#282828] flex justify-end">
              <button
                onClick={() => setSelectedCard(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-xs font-semibold"
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
