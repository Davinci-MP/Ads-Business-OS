"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  API_BASE,
  bulkAssignAccountsCustomer,
  fetchJson,
  fmtTime,
  getAdsCheckData,
  SyncedAdAccount,
  ViaProfile,
  maxcareSyncReports,
  updateAdsCheckAccount,
} from "../../lib/api";
import { Pagination, useToast } from "../../components/admin-ui";
import { loadAllAccounts } from "../../components/admin-data";
import { assignedDebtTotals, csvCell } from "../../lib/admin-utils.mjs";
import CustomerSpendReportModal from "@/components/CustomerSpendReportModal";
import { MonoIcon } from "@/components/mono-icon";
import ShareBmAccountsModal from "@/components/ShareBmAccountsModal";

type CustomerRef = { id: number; name: string; fee_rate?: string; telegram_chat_id?: string | null };
type SyncedBMRef = { id: number; bm_id: string; name: string };

const TIMEZONES = [
  "Asia/Ho_Chi_Minh",
  "UTC",
  "America/Los_Angeles",
  "Europe/Moscow",
  "Asia/Dubai",
  "Asia/Karachi",
];

const formatDebtVND = new Intl.NumberFormat("vi-VN", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});
const formatDebtUSD = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function ensureArray<T>(val: unknown): T[] {
  if (Array.isArray(val)) return val as T[];
  if (val && typeof val === "object") {
    const obj = val as Record<string, unknown>;
    if (Array.isArray(obj.items)) return obj.items as T[];
    if (Array.isArray(obj.vias)) return obj.vias as T[];
    if (Array.isArray(obj.bms)) return obj.bms as T[];
    if (Array.isArray(obj.data)) return obj.data as T[];
    if (Array.isArray(obj.accounts)) return obj.accounts as T[];
    if (Array.isArray(obj.customers)) return obj.customers as T[];
    if (Array.isArray(obj.pages)) return obj.pages as T[];
  }
  return [];
}

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<SyncedAdAccount[]>([]);
  const [customers, setCustomers] = useState<CustomerRef[]>([]);
  const [vias, setVias] = useState<ViaProfile[]>([]);
  const [bms, setBms] = useState<SyncedBMRef[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: "success" | "error" | "info"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const notify = useToast();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // Filters
  const [statusPill, setStatusPill] = useState<string>("ALL");
  const [accountTypeFilter, setAccountTypeFilter] = useState<string>("ALL");
  const [customerFilter, setCustomerFilter] = useState<string>("");
  const [viaFilter, setViaFilter] = useState<string>("");
  const [bmFilter, setBmFilter] = useState<string>("");
  const [currencyFilter, setCurrencyFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Bulk Selection
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bulkCustomerId, setBulkCustomerId] = useState<string>("");

  // Modals / Tools toggle
  const [showLegacyTools, setShowLegacyTools] = useState(false);
  const [showCustomerSpendModal, setShowCustomerSpendModal] = useState(false);
  const [showShareBmModal, setShowShareBmModal] = useState(false);

  // Legacy Form States
  const [newCustomerName, setNewCustomerName] = useState("");
  const [newCustomerChatId, setNewCustomerChatId] = useState("");
  const [createActId, setCreateActId] = useState("");
  const [createName, setCreateName] = useState("");
  const [createBm, setCreateBm] = useState("");
  const [newTz, setNewTz] = useState(TIMEZONES[0]);

  const showToast = useCallback((text: string, type: "success" | "error" | "info" = "success") => {
    notify(text, type);
    setTimeout(() => {
      setToast((prev) => (prev?.text === text ? null : prev));
    }, 4000);
  }, [notify]);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [adsRes, custRes, viaRes, bmRes] = await Promise.all([
        loadAllAccounts(),
        fetchJson<CustomerRef[]>("/customers").catch(() => []),
        fetchJson<ViaProfile[]>("/vias").catch(() => []),
        getAdsCheckData({ tab: "group", page_size: 200 }).then((r) => r.items).catch(() => []),
      ]);

      setAccounts(adsRes);
      setCustomers(ensureArray<CustomerRef>(custRes));
      setVias(ensureArray<ViaProfile>(viaRes));
      setBms(ensureArray<SyncedBMRef>(bmRes));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
    const urlParams = new URLSearchParams(window.location.search);
    const cid = urlParams.get("customerId");
    if (cid) setCustomerFilter(cid);
    const query = urlParams.get("q");
    if (query) setSearchQuery(query);
  }, [loadData]);

  // Inline Assign Customer handler (1-Click)
  const handleInlineAssign = async (actId: string, custIdStr: string) => {
    const custId = custIdStr ? Number(custIdStr) : null;
    const targetCustomer = customers.find((c) => c.id === custId);
    try {
      setBusy(true);
      const res = await updateAdsCheckAccount(actId, { customer_id: custId });
      if (res.success) {
        setAccounts((prev) =>
          prev.map((acc) => acc.act_id === actId ? res.account : acc)
        );
        showToast(
          custId
            ? ` Đã gắn TKQC act_${actId} cho khách hàng [${targetCustomer?.name || custId}]`
            : `ℹ Đã hủy gắn khách cho TKQC act_${actId}`,
          "success"
        );
      }
    } catch (err) {
      showToast(` Lỗi khi gắn khách: ${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setBusy(false);
    }
  };

  const handleInlineFee = async (account: SyncedAdAccount, value: string) => {
    const normalized = value.trim();
    const nextValue = normalized === "" ? null : Number(normalized);
    if (nextValue !== null && (!Number.isFinite(nextValue) || nextValue < 0 || nextValue > 100)) {
      showToast("Phí dịch vụ phải nằm trong khoảng 0–100%.", "error");
      return;
    }
    try {
      setBusy(true);
      const res = await updateAdsCheckAccount(account.act_id, { service_fee_percent: nextValue });
      setAccounts((current) => current.map((row) => row.act_id === account.act_id ? res.account : row));
      showToast(`Đã lưu phí dịch vụ cho act_${account.act_id}.`);
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Không lưu được phí dịch vụ.", "error");
    } finally {
      setBusy(false);
    }
  };

  // Bulk Assign Customer
  const handleBulkAssign = async () => {
    if (selectedIds.length === 0) return;
    const custId = bulkCustomerId ? Number(bulkCustomerId) : null;
    const targetCustomer = customers.find((c) => c.id === custId);
    try {
      setBusy(true);
      const res = await bulkAssignAccountsCustomer(selectedIds, custId);
      if (res.success) {
        setAccounts((prev) =>
          prev.map((acc) =>
            selectedIds.includes(acc.act_id)
              ? {
                  ...acc,
                  customer_id: custId,
                  customer_name: targetCustomer?.name || null,
                  is_assigned: Boolean(custId),
                }
              : acc
          )
        );
        showToast(
          custId
            ? ` Đã gắn ${res.updated_count} TKQC đã chọn cho khách [${targetCustomer?.name || custId}]`
            : `ℹ Đã hủy gắn khách cho ${res.updated_count} TKQC đã chọn`,
          "success"
        );
        setSelectedIds([]);
        setBulkCustomerId("");
      }
    } catch (err) {
      showToast(` Lỗi khi gắn hàng loạt: ${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setBusy(false);
    }
  };

  const checkSelectedSources = async () => {
    const viaIds = [...new Set(accounts.filter(a => selectedIds.includes(a.act_id)).map(a => a.via_profile_id).filter(id => id > 0))];
    if (!viaIds.length) { showToast("Tài khoản được chọn chưa có VIA nguồn hợp lệ.", "info"); return; }
    setBusy(true);
    try {
      const result = await maxcareSyncReports({ via_ids: viaIds, concurrency: 3 });
      showToast(`Đã đồng bộ ${result.done.length} VIA; ${result.failed.length} VIA lỗi nguồn.`, result.failed.length ? "info" : "success");
      await loadData();
    } catch (error: unknown) { showToast(error instanceof Error ? error.message : "Không thể kiểm tra nguồn tài khoản.", "error"); }
    finally { setBusy(false); }
  };

  // Export SMIT CSV
  const handleExportSMITCsv = () => {
    const targets = selectedIds.length > 0 ? accounts.filter((a) => selectedIds.includes(a.act_id)) : filteredRows;
    if (targets.length === 0) {
      showToast("Không có dữ liệu để xuất", "info");
      return;
    }

    const headers = [
      "STT",
      "ID Tài Khoản",
      "Tên TKQC",
      "Trạng Thái",
      "Khách Hàng",
      "VIA Nguồn",
      "Loại TK",
      "Dư Nợ",
      "Ngưỡng",
      "Hạn Mức Ngày",
      "Tổng Chi Tiêu",
      "Tiền Tệ",
      "Thẻ Thanh Toán",
      "Múi Giờ",
      "Cập Nhật Cuối",
    ];

    const csvRows = [headers.map(csvCell).join(",")];
    targets.forEach((acc, idx) => csvRows.push([
      idx + 1, `act_${acc.act_id.replace(/^act_/, "")}`, acc.name, acc.status_dot,
      acc.customer_name, acc.via_profile_name || acc.via_uid, acc.account_type,
      acc.balance, acc.threshold, acc.ad_trust_dsl, acc.total_spend, acc.currency,
      acc.card_display, acc.timezone_name, acc.updated_at,
    ].map(csvCell).join(",")));

    const blob = new Blob(["\uFEFF" + csvRows.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `ADSOS_SMIT_Accounts_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    showToast(` Đã xuất ${targets.length} tài khoản chuẩn SMIT CSV`, "success");
  };

  // Filter Logic
  const filteredRows = useMemo(() => {
    return accounts.filter((acc) => {
      // 1. Status Pill
      if (statusPill === "LIVE") {
        if (!(acc.status_dot === "LIVE" || acc.account_status === 1)) return false;
      } else if (statusPill === "DIE") {
        if (!(acc.status_dot === "DIE" || acc.account_status === 2)) return false;
      } else if (statusPill === "UNSETTLED") {
        if (!(acc.status_dot === "WARNING" || acc.account_status === 3 || (acc.balance || 0) > 0)) return false;
      } else if (statusPill === "UNASSIGNED") {
        if (acc.customer_id != null) return false;
      } else if (statusPill === "ASSIGNED") {
        if (acc.customer_id == null) return false;
      }

      // 1b. Account Type Filter (PERSONAL / BM / BUSINESS)
      if (accountTypeFilter === "PERSONAL") {
        if (acc.account_type && acc.account_type.toUpperCase() !== "PERSONAL") return false;
        if (!acc.account_type && acc.bm_id) return false;
      } else if (accountTypeFilter === "BM" || accountTypeFilter === "BUSINESS") {
        const isBm = (acc.account_type && (acc.account_type.toUpperCase() === "BM" || acc.account_type.toUpperCase() === "BUSINESS")) || Boolean(acc.bm_id);
        if (!isBm) return false;
      }

      // 2. Customer
      if (customerFilter && String(acc.customer_id) !== customerFilter) return false;

      // 3. VIA
      if (viaFilter && String(acc.via_profile_id) !== viaFilter) return false;

      // 4. BM
      if (bmFilter && acc.bm_id !== bmFilter) return false;

      // 5. Currency
      if (currencyFilter && (acc.currency || "VND").toUpperCase() !== currencyFilter.toUpperCase()) return false;

      // 6. Search (ID, Name, Card last4)
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchId = (acc.act_id || "").toLowerCase().includes(q) || `act_${acc.act_id}`.toLowerCase().includes(q);
        const matchName = (acc.name || "").toLowerCase().includes(q);
        const matchCard = (acc.payment_card_last4 || "").includes(q);
        const matchCustomer = (acc.customer_name || "").toLowerCase().includes(q);
        if (!matchId && !matchName && !matchCard && !matchCustomer) return false;
      }

      return true;
    });
  }, [accounts, statusPill, accountTypeFilter, customerFilter, viaFilter, bmFilter, currencyFilter, searchQuery]);

  useEffect(() => setPage(1), [searchQuery, statusPill, accountTypeFilter, customerFilter, viaFilter, bmFilter, currencyFilter, pageSize]);
  const pageRows = filteredRows.slice((page - 1) * pageSize, page * pageSize);

  // Overall KPI counts
  const kpis = useMemo(() => {
    const total = accounts.length;
    const live = accounts.filter((a) => a.status_dot === "LIVE" || a.account_status === 1).length;
    const die = accounts.filter((a) => a.status_dot === "DIE" || a.account_status === 2).length;
    const debt = accounts.filter((a) => a.status_dot === "WARNING" || a.account_status === 3 || (a.balance || 0) > 0).length;
    const assignedAccounts = accounts.filter((a) => a.customer_id != null);
    const assigned = assignedAccounts.length;
    const unassigned = total - assigned;
    const assignedDebt = assignedDebtTotals(assignedAccounts);
    return {
      total,
      live,
      die,
      debt,
      assigned,
      unassigned,
      totalDebtVND: assignedDebt.VND,
      totalDebtUSD: assignedDebt.USD,
    };
  }, [accounts]);

  // Select all checkboxes handler
  const handleToggleSelectAll = () => {
    const visibleIds = pageRows.map(a => a.act_id);
    if (visibleIds.every(id => selectedIds.includes(id))) setSelectedIds(ids => ids.filter(id => !visibleIds.includes(id)));
    else setSelectedIds(ids => [...new Set([...ids, ...visibleIds])]);
  };

  const handleToggleRow = (actId: string) => {
    setSelectedIds((prev) =>
      prev.includes(actId) ? prev.filter((id) => id !== actId) : [...prev, actId]
    );
  };

  const copyToClipboard = (text: string, label: string) => {
    void navigator.clipboard.writeText(text).then(() => showToast(`Đã sao chép ${label}.`, "info")).catch(() => showToast("Không thể sao chép vào bộ nhớ tạm.", "error"));
  };

  return (
    <div className="w-full space-y-6 text-white">
      {/* TOAST NOTIFICATION */}
      {toast && (
        <div
          className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-5 py-3.5 rounded-2xl shadow-2xl border text-sm font-medium backdrop-blur-xl animate-bounce-once ${
            toast.type === "success"
              ? "bg-emerald-950/90 border-emerald-500/50 text-emerald-200"
              : toast.type === "error"
              ? "bg-rose-950/90 border-rose-500/50 text-rose-200"
              : "bg-slate-900/90 border-slate-700 text-slate-200"
          }`}
        >
          <span>{toast.text}</span>
          <button
            onClick={() => setToast(null)}
            className="text-slate-400 hover:text-white text-xs px-1.5 py-0.5 rounded"
          >
            <MonoIcon name="close" className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* ZONE 1: TOP HEADER & ACTIONS */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800/80 pb-6">
        <div>
          <div className="flex items-center gap-3">
            <span className="text-3xl"></span>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
                Quản Trị Tài Khoản Quảng Cáo
                <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
                  Tài sản quảng cáo
                </span>
              </h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Quản lý tập trung toàn bộ TKQC cá nhân & BM, gán khách hàng 1-click, theo dõi số dư nợ và thẻ thanh toán.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5 flex-wrap">
          <button
            onClick={loadData}
            disabled={loading || busy}
            className="flex items-center gap-2 bg-[#1f1f1f] hover:bg-[#282828] text-white px-4 py-2 rounded-full text-xs font-bold uppercase tracking-[1.4px] border border-[#333333] transition"
          >
            <span className={loading ? "animate-spin" : ""}></span>
            Làm mới
          </button>

          <button
            onClick={handleExportSMITCsv}
            className="flex items-center gap-2 bg-[#1ed760] hover:bg-[#1fdf64] text-black px-4 py-2 rounded-full text-xs font-bold uppercase tracking-[1.4px] shadow-md transition"
          >
             Xuất danh sách CSV
          </button>

          <button
            onClick={() => setShowCustomerSpendModal(true)}
            className="flex items-center gap-2 bg-[#1f1f1f] hover:bg-[#282828] text-[#38bdf8] border border-[#38bdf8]/40 px-4 py-2 rounded-full text-xs font-bold uppercase tracking-[1.4px] shadow-sm transition"
          >
            <span></span>
            Báo Cáo 4% Phí
          </button>

          <button
            onClick={() => setShowLegacyTools(!showLegacyTools)}
            className="flex items-center gap-2 bg-[#1f1f1f] hover:bg-[#282828] text-[#b3b3b3] hover:text-white px-4 py-2 rounded-full text-xs font-bold uppercase tracking-[1.4px] border border-[#333333] transition"
          >
             {showLegacyTools ? "Thu gọn công cụ" : "Thêm TK / Khách thủ công"}
          </button>
        </div>
      </div>

      {/* COLLAPSIBLE LEGACY TOOLS */}
      {showLegacyTools && (
        <div className="bg-[#181818] border border-[#282828] rounded-[8px] shadow-[0_8px_8px_rgba(0,0,0,0.3)] p-5 shadow-2xl backdrop-blur-md grid grid-cols-1 md:grid-cols-2 gap-6 animate-fade-in">
          {/* Thêm Khách Hàng */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
              <span></span> Tạo Khách Hàng Mới
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <input
                value={newCustomerName}
                onChange={(e) => setNewCustomerName(e.target.value)}
                placeholder="Tên khách hàng (VD: KH Alpha)"
                className="bg-[#1E293B] border border-slate-700 text-slate-100 placeholder-slate-400 rounded-xl px-3.5 py-2 text-xs focus:border-indigo-500 focus:outline-none"
              />
              <input
                value={newCustomerChatId}
                onChange={(e) => setNewCustomerChatId(e.target.value)}
                placeholder="Telegram Chat ID (tùy chọn)"
                className="bg-[#1E293B] border border-slate-700 text-slate-100 placeholder-slate-400 rounded-xl px-3.5 py-2 text-xs focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <button
              disabled={busy || !newCustomerName.trim()}
              onClick={async () => {
                try {
                  setBusy(true);
                  const res = await fetch(`${API_BASE}/api/v1/customers`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      name: newCustomerName.trim(),
                      telegram_chat_id: newCustomerChatId.trim() || null,
                    }),
                  });
                  if (!res.ok) throw new Error(await res.text());
                  showToast(`Đã tạo khách hàng [${newCustomerName.trim()}]`, "success");
                  setNewCustomerName("");
                  setNewCustomerChatId("");
                  await loadData();
                } catch (e) {
                  showToast(`Lỗi: ${e instanceof Error ? e.message : String(e)}`, "error");
                } finally {
                  setBusy(false);
                }
              }}
              className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-1.5 rounded-xl text-xs font-semibold disabled:opacity-50 transition"
            >
              + Tạo khách hàng
            </button>
          </div>

          {/* Thêm Account Thủ Công */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
              <span></span> Thêm Ad Account Thủ Công
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <input
                value={createActId}
                onChange={(e) => setCreateActId(e.target.value)}
                placeholder="Act ID (VD: act_12345)"
                className="bg-[#1E293B] border border-slate-700 text-slate-100 placeholder-slate-400 rounded-xl px-3.5 py-2 text-xs focus:border-indigo-500 focus:outline-none"
              />
              <input
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                placeholder="Tên account"
                className="bg-[#1E293B] border border-slate-700 text-slate-100 placeholder-slate-400 rounded-xl px-3.5 py-2 text-xs focus:border-indigo-500 focus:outline-none"
              />
              <input
                value={createBm}
                onChange={(e) => setCreateBm(e.target.value)}
                placeholder="BM ID (tùy chọn)"
                className="bg-[#1E293B] border border-slate-700 text-slate-100 placeholder-slate-400 rounded-xl px-3.5 py-2 text-xs focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <button
              disabled={busy || !createActId.trim()}
              onClick={async () => {
                try {
                  setBusy(true);
                  const res = await fetch(`${API_BASE}/api/v1/ad-accounts`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      meta_ad_account_id: createActId.trim(),
                      name: createName.trim() || `Tài khoản ${createActId.trim()}`,
                      timezone_name: newTz,
                      business_manager_id: createBm || null,
                    }),
                  });
                  if (!res.ok) throw new Error(await res.text());
                  showToast(`Đã thêm tài khoản [${createActId.trim()}]`, "success");
                  setCreateActId("");
                  setCreateName("");
                  setCreateBm("");
                  await loadData();
                } catch (e) {
                  showToast(`Lỗi: ${e instanceof Error ? e.message : String(e)}`, "error");
                } finally {
                  setBusy(false);
                }
              }}
              className="bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-1.5 rounded-xl text-xs font-semibold disabled:opacity-50 transition"
            >
              + Thêm tài khoản
            </button>
          </div>
        </div>
      )}

      {/* ZONE 2: KPI SUMMARY STRIP */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        <div className="bg-[#181818] border border-[#282828] rounded-[8px] shadow-[0_8px_8px_rgba(0,0,0,0.3)] p-4 shadow-xl">
          <span className="text-xs font-medium text-slate-400">Tổng TKQC</span>
          <div className="text-2xl font-bold font-mono text-white mt-1">{kpis.total}</div>
        </div>
        <div className="bg-[#181818] border border-[#1ed760]/30 rounded-[8px] p-4 shadow-[0_8px_8px_rgba(0,0,0,0.3)]">
          <span className="text-xs font-medium text-emerald-400"> Hoạt Động (Live)</span>
          <div className="text-2xl font-bold font-mono text-emerald-300 mt-1">{kpis.live}</div>
        </div>
        <div className="bg-[#181818] border border-[#f3727f]/30 rounded-[8px] p-4 shadow-[0_8px_8px_rgba(0,0,0,0.3)]">
          <span className="text-xs font-medium text-rose-400"> Vô Hiệu Hóa (Die)</span>
          <div className="text-2xl font-bold font-mono text-rose-300 mt-1">{kpis.die}</div>
        </div>
        <div className="bg-[#181818] border border-[#ffa42b]/30 rounded-[8px] p-4 shadow-[0_8px_8px_rgba(0,0,0,0.3)]">
          <span className="text-xs font-medium text-amber-400"> Đang Nợ / Tạm Dừng</span>
          <div className="text-2xl font-bold font-mono text-amber-300 mt-1">{kpis.debt}</div>
        </div>
        <div className="bg-[#181818] border border-[#282828] rounded-[8px] p-4 shadow-[0_8px_8px_rgba(0,0,0,0.3)]">
          <span className="text-xs font-medium text-slate-300"> Chưa Gắn Khách</span>
          <div className="text-2xl font-bold font-mono text-slate-200 mt-1">{kpis.unassigned}</div>
        </div>
        <div className="bg-[#181818] border border-[#539df5]/30 rounded-[8px] p-4 shadow-[0_8px_8px_rgba(0,0,0,0.3)]">
          <span className="text-xs font-medium text-indigo-300"> Đã Gắn Khách</span>
          <div className="text-2xl font-bold font-mono text-indigo-300 mt-1">{kpis.assigned}</div>
        </div>
        <div className="bg-[#181818] border border-[#282828] rounded-[8px] shadow-[0_8px_8px_rgba(0,0,0,0.3)] p-4 shadow-xl">
          <span className="text-xs font-medium text-slate-400">Tổng Dư Nợ Meta (Đã Gán)</span>
          <div className="text-sm font-bold font-mono text-rose-400 mt-2 whitespace-nowrap">
            {formatDebtVND.format(kpis.totalDebtVND)} ₫ | {formatDebtUSD.format(kpis.totalDebtUSD)} $
          </div>
        </div>
      </div>

      {/* ZONE 3: STATUS PILLS & FILTERS TOOLBAR */}
      <div className="bg-[#181818] border border-[#282828] rounded-[8px] shadow-[0_8px_8px_rgba(0,0,0,0.3)] p-4 shadow-xl backdrop-blur-md space-y-4">
        {/* Status Pills */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-thin">
          <button
            onClick={() => setStatusPill("ALL")}
            className={`px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-[1.4px] transition ${
              statusPill === "ALL"
                ? "bg-[#1ed760] text-black shadow-md"
                : "bg-[#1f1f1f] text-[#b3b3b3] hover:text-white hover:bg-[#282828] border border-[#333333]"
            }`}
          >
            Tất cả ({kpis.total})
          </button>
          <button
            onClick={() => setStatusPill("LIVE")}
            className={`px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-[1.4px] transition flex items-center gap-1.5 ${
              statusPill === "LIVE"
                ? "bg-[#1ed760] text-black shadow-md"
                : "bg-[#1f1f1f] text-[#1ed760] hover:text-white hover:bg-[#282828] border border-[#333333]"
            }`}
          >
            <span></span> Live ({kpis.live})
          </button>
          <button
            onClick={() => setStatusPill("DIE")}
            className={`px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-[1.4px] transition flex items-center gap-1.5 ${
              statusPill === "DIE"
                ? "bg-[#f3727f] text-black shadow-md"
                : "bg-[#1f1f1f] text-[#f3727f] hover:text-white hover:bg-[#282828] border border-[#333333]"
            }`}
          >
            <span></span> Die ({kpis.die})
          </button>
          <button
            onClick={() => setStatusPill("UNSETTLED")}
            className={`px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-[1.4px] transition flex items-center gap-1.5 ${
              statusPill === "UNSETTLED"
                ? "bg-[#ffa42b] text-black shadow-md"
                : "bg-[#1f1f1f] text-[#ffa42b] hover:text-white hover:bg-[#282828] border border-[#333333]"
            }`}
          >
            <span></span> Nợ ({kpis.debt})
          </button>
          <button
            onClick={() => setStatusPill("UNASSIGNED")}
            className={`px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-[1.4px] transition flex items-center gap-1.5 ${
              statusPill === "UNASSIGNED"
                ? "bg-white text-black shadow-md"
                : "bg-[#1f1f1f] text-[#b3b3b3] hover:text-white hover:bg-[#282828] border border-[#333333]"
            }`}
          >
            <span></span> Chưa Gắn ({kpis.unassigned})
          </button>
          <button
            onClick={() => setStatusPill("ASSIGNED")}
            className={`px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-[1.4px] transition flex items-center gap-1.5 ${
              statusPill === "ASSIGNED"
                ? "bg-[#539df5] text-black shadow-md"
                : "bg-[#1f1f1f] text-[#539df5] hover:text-white hover:bg-[#282828] border border-[#333333]"
            }`}
          >
            <span></span> Đã Gắn ({kpis.assigned})
          </button>
        </div>

        {/* Dropdowns & Search Input */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 pt-2 border-t border-slate-800/60">
          <div>
            <label className="block text-[11px] font-medium text-slate-400 mb-1"> Loại Tài Khoản</label>
            <select
              value={accountTypeFilter}
              onChange={(e) => setAccountTypeFilter(e.target.value)}
              className="w-full bg-[#1f1f1f] border border-[#333333] text-white rounded-full px-3.5 py-2 text-xs focus:border-[#1ed760] focus:outline-none"
            >
              <option value="ALL">Tất cả loại TK</option>
              <option value="PERSONAL">TK Cá nhân (Personal)</option>
              <option value="BM">TK Doanh nghiệp (BM)</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-medium text-slate-400 mb-1"> Chọn Khách Hàng</label>
            <select
              value={customerFilter}
              onChange={(e) => setCustomerFilter(e.target.value)}
              className="w-full bg-[#1f1f1f] border border-[#333333] text-white rounded-full px-3.5 py-2 text-xs focus:border-[#1ed760] focus:outline-none"
            >
              <option value="">Tất cả khách hàng ({(customers || []).length})</option>
              {(customers || []).map((c) => (
                <option key={c.id} value={String(c.id)}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-medium text-slate-400 mb-1"> Chọn VIA Nguồn</label>
            <select
              value={viaFilter}
              onChange={(e) => setViaFilter(e.target.value)}
              className="w-full bg-[#1f1f1f] border border-[#333333] text-white rounded-full px-3.5 py-2 text-xs focus:border-[#1ed760] focus:outline-none"
            >
              <option value="">Tất cả VIA ({(vias || []).length})</option>
              {(vias || []).map((v) => (
                <option key={v.id} value={String(v.id)}>
                  {v.profile_name} (UID: {v.uid})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-medium text-slate-400 mb-1"> Chọn Business Manager (BM)</label>
            <select
              value={bmFilter}
              onChange={(e) => setBmFilter(e.target.value)}
              className="w-full bg-[#1f1f1f] border border-[#333333] text-white rounded-full px-3.5 py-2 text-xs focus:border-[#1ed760] focus:outline-none"
            >
              <option value="">Tất cả BM ({(bms || []).length})</option>
              {(bms || []).map((b) => (
                <option key={b.id} value={b.bm_id}>
                  {b.name} ({b.bm_id})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-medium text-slate-400 mb-1"> Tiền tệ</label>
            <select
              value={currencyFilter}
              onChange={(e) => setCurrencyFilter(e.target.value)}
              className="w-full bg-[#1f1f1f] border border-[#333333] text-white rounded-full px-3.5 py-2 text-xs focus:border-[#1ed760] focus:outline-none"
            >
              <option value="">Tất cả tiền tệ</option>
              <option value="USD">USD ($)</option>
              <option value="VND">VND (₫)</option>
              <option value="EUR">EUR (€)</option>
              <option value="PHP">PHP (₱)</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-medium text-slate-400 mb-1"> Ô tìm kiếm nhanh</label>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="ID, Tên TK, 4 số cuối thẻ..."
              className="w-full bg-[#1f1f1f] border border-[#333333] text-white placeholder-[#727272] rounded-full px-3.5 py-2 text-xs focus:border-[#1ed760] focus:outline-none"
            />
          </div>
        </div>
      </div>

      {/* FLOATING BULK ACTION TOOLBAR */}
      {selectedIds.length > 0 && (
        <div className="sticky top-4 z-40 bg-[#181818]/95 border border-[#1ed760]/40 rounded-[8px] p-4 shadow-[0_8px_24px_rgba(0,0,0,0.5)] backdrop-blur-xl flex flex-wrap items-center justify-between gap-4 animate-slide-down">
          <div className="flex items-center gap-3">
            <span className="w-2.5 h-2.5 rounded-full bg-indigo-400 animate-pulse" />
            <span className="text-sm font-semibold text-white">
              Đã chọn <span className="font-bold font-mono text-indigo-400">{selectedIds.length}</span> tài khoản
            </span>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-300 font-medium"> Gắn cho khách:</span>
              <select
                value={bulkCustomerId}
                onChange={(e) => setBulkCustomerId(e.target.value)}
                className="bg-[#1E293B] border border-slate-700 text-slate-100 rounded-xl px-3 py-1.5 text-xs focus:border-indigo-500 focus:outline-none"
              >
                <option value="">— Chọn khách hàng —</option>
                {(customers || []).map((c) => (
                  <option key={c.id} value={String(c.id)}>
                    {c.name}
                  </option>
                ))}
              </select>
              <button
                disabled={busy}
                onClick={handleBulkAssign}
                className="bg-[#1ed760] hover:bg-[#1fdf64] text-black px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-[1.4px] shadow transition disabled:opacity-50"
              >
                Lưu Gắn Kết
              </button>
              <button className="btn" type="button" onClick={() => setShowShareBmModal(true)}>
                Chia sẻ BM &amp; gán TKQC
              </button>
            </div>

            <button
              onClick={handleExportSMITCsv}
              className="bg-[#1f1f1f] hover:bg-[#282828] text-white px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-[1.4px] border border-[#333333] transition"
            >
               Xuất {selectedIds.length} TK (CSV)
            </button>
            <button className="btn" disabled={busy} title="Đồng bộ số dư và trạng thái từ các VIA của tài khoản đã chọn; không thay đổi thẻ hoặc tài sản Meta." onClick={() => void checkSelectedSources()}>↻ Kiểm tra nguồn & số dư</button>

            <button
              onClick={() => setSelectedIds([])}
              className="text-slate-400 hover:text-white text-xs px-2 py-1"
            >
              Bỏ chọn
            </button>
          </div>
        </div>
      )}

      {/* FULL 15-COLUMN SMIT PRO DATA TABLE */}
      <div className="bg-[#181818] border border-[#282828] rounded-[8px] shadow-[0_8px_8px_rgba(0,0,0,0.3)] shadow-2xl overflow-hidden backdrop-blur-md">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-[#1f1f1f] border-b border-[#282828] text-[#b3b3b3] font-bold uppercase tracking-[1.4px] text-[11px]">
                <th className="py-3 px-3 w-10 text-center">
                  <input
                    type="checkbox"
                    checked={pageRows.length > 0 && pageRows.every(a => selectedIds.includes(a.act_id))}
                    onChange={handleToggleSelectAll}
                    className="w-4 h-4 rounded bg-slate-800 border-slate-700 text-indigo-500 focus:ring-0 cursor-pointer accent-[#1ed760]"
                  />
                </th>
                <th className="py-3 px-2 w-10 text-center">STT</th>
                <th className="py-3 px-3">Trạng Thái</th>
                <th className="py-3 px-3">ID Tài Khoản</th>
                <th className="py-3 px-3">Tên TKQC</th>
                <th className="py-3 px-3 min-w-[180px]"> Khách Hàng Gắn Kết</th>
                <th className="py-3 px-3 min-w-[120px]">Phí dịch vụ %</th>
                <th className="py-3 px-3"> VIA Nguồn</th>
                <th className="py-3 px-3">Loại TK</th>
                <th className="py-3 px-3 text-right">Dư Nợ (Balance)</th>
                <th className="py-3 px-3 text-right">Ngưỡng</th>
                <th className="py-3 px-3 text-right">Limit Ngày</th>
                <th className="py-3 px-3 text-right">Tổng Tiêu</th>
                <th className="py-3 px-2 text-center">Tiền Tệ</th>
                <th className="py-3 px-3"> Thẻ TT</th>
                <th className="py-3 px-3">Múi Giờ</th>
                <th className="py-3 px-3">Cập Nhật</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#282828]">
              {loading ? (
                <tr>
                  <td colSpan={17} className="py-12 text-center text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <span className="text-2xl animate-spin"></span>
                      <span>Đang đọc tài khoản quảng cáo đã đồng bộ…</span>
                    </div>
                  </td>
                </tr>
              ) : filteredRows.length === 0 ? (
                <tr>
                  <td colSpan={17} className="py-12 text-center text-slate-400">
                    Không tìm thấy tài khoản quảng cáo nào phù hợp với bộ lọc.
                  </td>
                </tr>
              ) : (
                pageRows.map((acc, index) => {
                  const isChecked = selectedIds.includes(acc.act_id);
                  const isLive = acc.status_dot === "LIVE" || acc.account_status === 1;
                  const isDie = acc.status_dot === "DIE" || acc.account_status === 2;
                  const hasDebt = (acc.balance || 0) > 0;

                  return (
                    <tr
                      key={acc.id || acc.act_id}
                      className={`hover:bg-slate-800/40 transition-colors ${
                        isChecked ? "bg-indigo-950/20" : ""
                      }`}
                    >
                      {/* 1. Checkbox */}
                      <td className="py-3 px-3 text-center">
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => handleToggleRow(acc.act_id)}
                          className="w-4 h-4 rounded bg-slate-800 border-slate-700 text-indigo-500 focus:ring-0 cursor-pointer accent-[#1ed760]"
                        />
                      </td>

                      {/* 2. STT */}
                      <td className="py-3 px-2 text-center font-mono text-slate-400 text-[11px]">
                        {(page - 1) * pageSize + index + 1}
                      </td>

                      {/* 3. Trạng Thái Badge */}
                      <td className="py-3 px-3 whitespace-nowrap">
                        {isLive ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-950/80 border border-emerald-500/40 text-emerald-400">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                            Hoạt động
                          </span>
                        ) : isDie ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-rose-950/80 border border-rose-500/40 text-rose-400">
                            <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
                            Vô hiệu hóa
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-amber-950/80 border border-amber-500/40 text-amber-400">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                            Tạm dừng
                          </span>
                        )}
                        {hasDebt && (
                          <span className="ml-1.5 px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                            NỢ
                          </span>
                        )}
                      </td>

                      {/* 4. ID Tài Khoản + Copy */}
                      <td className="py-3 px-3 whitespace-nowrap">
                        <div className="flex items-center gap-1.5">
                          <span className="font-mono font-bold text-indigo-300">
                            act_{acc.act_id}
                          </span>
                          <button
                            onClick={() => copyToClipboard(`act_${acc.act_id}`, "Mã Act ID")}
                            title="Sao chép ID"
                            className="text-slate-400 hover:text-white p-0.5 rounded transition"
                          >
                            <MonoIcon name="copy" className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </td>

                      {/* 5. Tên TKQC */}
                      <td className="py-3 px-3 font-medium text-slate-100 max-w-[200px] truncate" title={acc.name}>
                        {acc.name}
                      </td>

                      {/* 6.  Khách Hàng Gắn Kết (Inline Selector) */}
                      <td className="py-3 px-3">
                        <select
                          value={acc.customer_id ? String(acc.customer_id) : ""}
                          disabled={busy}
                          onChange={(e) => void handleInlineAssign(acc.act_id, e.target.value)}
                          className={`w-full text-xs font-semibold rounded-xl px-2.5 py-1.5 border transition focus:outline-none focus:ring-1 focus:ring-indigo-500 ${
                            acc.customer_id
                              ? "bg-indigo-950/60 border-indigo-500/50 text-indigo-200"
                              : "bg-[#1E293B] border-slate-700 text-slate-400 italic"
                          }`}
                        >
                          <option value=""> Chưa gán khách (Unassigned)</option>
                          {(customers || []).map((c) => (
                            <option key={c.id} value={String(c.id)} className="bg-slate-900 text-white not-italic">
                               {c.name}
                            </option>
                          ))}
                        </select>
                      </td>

                      <td className="py-3 px-3">
                        <input
                          type="number"
                          min="0"
                          max="100"
                          step="0.01"
                          disabled={busy}
                          defaultValue={acc.service_fee_percent ?? (acc.customer_id ? Number(customers.find((customer) => customer.id === acc.customer_id)?.fee_rate || 0) * 100 : "")}
                          onBlur={(event) => void handleInlineFee(acc, event.target.value)}
                          className="w-24 rounded-lg border border-[#333333] bg-[#1f1f1f] px-2 py-1 text-right font-mono text-xs text-white"
                          aria-label={`Phí dịch vụ act_${acc.act_id}`}
                        />
                      </td>

                      {/* 7.  VIA Nguồn */}
                      <td className="py-3 px-3 whitespace-nowrap">
                        {acc.via_profile_name || acc.via_uid ? (
                          <div className="space-y-0.5">
                            <div className="font-semibold text-slate-200">{acc.via_profile_name || "VIA"}</div>
                            <div className="text-[11px] font-mono text-slate-400">{acc.via_uid}</div>
                          </div>
                        ) : (
                          <span className="text-slate-400 italic">—</span>
                        )}
                      </td>

                      {/* 8. Loại TK */}
                      <td className="py-3 px-3 whitespace-nowrap">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            acc.account_type === "BM"
                              ? "bg-purple-950/80 text-purple-300 border border-purple-500/30"
                              : "bg-blue-950/80 text-blue-300 border border-blue-500/30"
                          }`}
                        >
                          {acc.account_type || "PERSONAL"}
                        </span>
                        {acc.bm_id && (
                          <div className="text-[10px] font-mono text-slate-400 mt-0.5">{acc.bm_id}</div>
                        )}
                      </td>

                      {/* 9. Dư Nợ (Balance) */}
                      <td className="py-3 px-3 text-right font-mono font-bold whitespace-nowrap">
                        <span className={hasDebt ? "text-rose-400" : "text-slate-400"}>
                          {(acc.balance || 0).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 2 })}
                        </span>
                      </td>

                      {/* 10. Ngưỡng (Threshold) */}
                      <td className="py-3 px-3 text-right font-mono font-medium text-slate-300 whitespace-nowrap">
                        {(acc.threshold || 0).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 2 })}
                      </td>

                      {/* 11. Limit Ngày / Spend Cap */}
                      <td className="py-3 px-3 text-right font-mono font-medium text-slate-300 whitespace-nowrap">
                        {(acc.ad_trust_dsl || 0) > 0
                          ? (acc.ad_trust_dsl || 0).toLocaleString("en-US", { minimumFractionDigits: 0 })
                          : "No Limit"}
                      </td>

                      {/* 12. Tổng Chi Tiêu */}
                      <td className="py-3 px-3 text-right font-mono font-bold text-indigo-300 whitespace-nowrap">
                        {(acc.total_spend || 0).toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}
                      </td>

                      {/* 13. Tiền Tệ */}
                      <td className="py-3 px-2 text-center font-mono font-bold text-slate-300 whitespace-nowrap">
                        {acc.currency || "VND"}
                      </td>

                      {/* 14.  Thẻ TT */}
                      <td className="py-3 px-3 whitespace-nowrap">
                        {acc.payment_card_last4 ? (
                          <span className="inline-flex items-center gap-1 font-mono text-slate-200 bg-slate-800/80 px-2 py-0.5 rounded border border-slate-700">
                            <span></span>
                            <span>{acc.payment_card_brand || "CARD"} - {acc.payment_card_last4}</span>
                          </span>
                        ) : (
                          <span className="text-slate-400 italic">Chưa gắn thẻ</span>
                        )}
                      </td>

                      {/* 15. Múi Giờ */}
                      <td className="py-3 px-3 text-slate-400 text-[11px] whitespace-nowrap">
                        {acc.timezone_name || "GMT+7"}
                      </td>

                      {/* 16. Cập Nhật Cuối */}
                      <td className="py-3 px-3 text-slate-400 text-[11px] whitespace-nowrap">
                        {acc.updated_at ? fmtTime(acc.updated_at) : "—"}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      <Pagination total={filteredRows.length} page={page} size={pageSize} onPage={setPage} onSize={setPageSize} />

      {/* Customer Spend & 4% Rental Fee Modal */}
      <CustomerSpendReportModal
        isOpen={showCustomerSpendModal}
        onClose={() => setShowCustomerSpendModal(false)}
      />
      <ShareBmAccountsModal
        open={showShareBmModal}
        onClose={() => setShowShareBmModal(false)}
        accounts={accounts}
        customers={customers}
        bms={bms}
        initialAccountIds={selectedIds}
      />
    </div>
  );
}
