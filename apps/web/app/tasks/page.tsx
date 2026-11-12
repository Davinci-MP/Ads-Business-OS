"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  createClientTaskManual,
  cancelRemoteCommand,
  getClientTasks,
  getRemoteCommands,
  updateClientTaskStatus,
  fetchJson,
  ClientTaskItem,
  RemoteCommandItem,
  ClientBMPreference,
  getClientBMPreferences,
} from "../../lib/api";
import ClientBMPreferenceModal from "../../components/client-bm-preference-modal";

const typeConfig: Record<string, { label: string; badge: string; icon: string }> = {
  ADD_MAIL_TO_BM: {
    label: "Mời mail vào BM",
    badge: "bg-purple-500/20 text-purple-300 border-purple-500/30",
    icon: "",
  },
  ADD_AD_ACCOUNT: {
    label: "Cấp / Gán TKQC",
    badge: "bg-blue-500/20 text-blue-300 border-blue-500/30",
    icon: "",
  },
  SETTLE_DEBT: {
    label: "Thanh toán nợ cước",
    badge: "bg-rose-500/20 text-rose-300 border-rose-500/30",
    icon: "",
  },
  TOPUP_BUDGET: {
    label: "Nạp ngân sách",
    badge: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
    icon: "",
  },
  CHECK_BALANCE: {
    label: "Tra cứu số dư",
    badge: "bg-amber-500/20 text-amber-300 border-amber-500/30",
    icon: "",
  },
  GENERAL_SUPPORT: {
    label: "Hỗ trợ chung",
    badge: "bg-gray-700 text-gray-300 border-gray-600",
    icon: "",
  },
};

const statusConfig: Record<string, { label: string; badge: string }> = {
  PENDING: { label: "Chờ xử lý", badge: "bg-amber-500/20 text-amber-400 border-amber-500/30" },
  IN_PROGRESS: { label: "Đang xử lý", badge: "bg-blue-500/20 text-blue-400 border-blue-500/30" },
  COMPLETED: { label: "Đã hoàn thành", badge: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" },
  CANCELLED: { label: "Đã hủy", badge: "bg-gray-800 text-gray-400 border-gray-700" },
};

const priorityBadges: Record<string, string> = {
  LOW: "text-gray-400 bg-gray-800",
  NORMAL: "text-blue-300 bg-blue-500/15 border border-blue-500/30",
  HIGH: "text-amber-300 bg-amber-500/15 border border-amber-500/30",
  URGENT: "text-rose-300 bg-rose-500/20 border border-rose-500/40 animate-pulse",
};

const remoteStatusConfig: Record<string, { label: string; badge: string }> = {
  PENDING: { label: "Chờ Extension", badge: "bg-amber-500/20 text-amber-300 border-amber-500/30" },
  PROCESSING: { label: "Đang thực thi", badge: "bg-blue-500/20 text-blue-300 border-blue-500/30" },
  COMPLETED: { label: "Hoàn thành", badge: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30" },
  FAILED: { label: "Thất bại", badge: "bg-rose-500/20 text-rose-300 border-rose-500/30" },
  CANCELLED: { label: "Đã hủy", badge: "bg-gray-800 text-gray-400 border-gray-700" },
};

export default function TasksPage() {
  const [tasks, setTasks] = useState<ClientTaskItem[]>([]);
  const [remoteCommands, setRemoteCommands] = useState<RemoteCommandItem[]>([]);
  const [customers, setCustomers] = useState<{ id: number; name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error?: boolean } | null>(null);

  // Filters & Views
  const [viewMode, setViewMode] = useState<"table" | "kanban">("table");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [typeFilter, setTypeFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Modals
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showActionModal, setShowActionModal] = useState(false);
  const [activeTask, setActiveTask] = useState<ClientTaskItem | null>(null);

  // Multi-BM Preferences State
  const [bmPrefs, setBmPrefs] = useState<Record<number, ClientBMPreference>>({});
  const [bmModalClient, setBmModalClient] = useState<{ id: number; name: string } | null>(null);
  const [showBmModal, setShowBmModal] = useState(false);

  // Action Form
  const [actionStatus, setActionStatus] = useState<string>("IN_PROGRESS");
  const [actionNotes, setActionNotes] = useState<string>("");
  const [actionAssignee, setActionAssignee] = useState<string>("");

  // Create Form
  const [createCustId, setCreateCustId] = useState<string>("");
  const [createSender, setCreateSender] = useState<string>("");
  const [createType, setCreateType] = useState<string>("ADD_MAIL_TO_BM");
  const [createMessage, setCreateMessage] = useState<string>("");
  const [createPriority, setCreatePriority] = useState<string>("NORMAL");
  const [createAssignee, setCreateAssignee] = useState<string>("");

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const params: { status?: string; task_type?: string } = {};
      if (statusFilter !== "ALL") params.status = statusFilter;
      if (typeFilter !== "ALL") params.task_type = typeFilter;

      const [taskList, remoteList, custList, prefList] = await Promise.all([
        getClientTasks(params),
        getRemoteCommands(),
        fetchJson<{ id: number; name: string }[]>("/customers"),
        getClientBMPreferences().catch(() => [] as ClientBMPreference[]),
      ]);
      setTasks(taskList);
      setRemoteCommands(remoteList);
      setCustomers(custList);

      const prefMap: Record<number, ClientBMPreference> = {};
      for (const p of prefList) {
        prefMap[p.client_id] = p;
      }
      setBmPrefs(prefMap);
    } catch (err: unknown) {
      setNotice({
        text: err instanceof Error ? err.message : "Không thể tải danh sách tác vụ.",
        error: true,
      });
    } finally {
      setLoading(false);
    }
  }, [statusFilter, typeFilter]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // Handle Update Status
  const handleUpdateStatus = async (
    task: ClientTaskItem,
    nextStatus: string,
    notes?: string,
    assignee?: string
  ) => {
    setBusy(true);
    try {
      await updateClientTaskStatus(task.id, {
        status: nextStatus,
        notes: notes !== undefined ? notes : task.notes || undefined,
        assigned_to: assignee !== undefined ? assignee : task.assigned_to || undefined,
        actor: "admin_web",
      });
      setShowActionModal(false);
      setNotice({ text: `Đã cập nhật tác vụ #${task.id} thành ${nextStatus}.` });
      await loadData();
    } catch (err: unknown) {
      setNotice({ text: err instanceof Error ? err.message : "Lỗi cập nhật tác vụ.", error: true });
    } finally {
      setBusy(false);
    }
  };

  const handleCancelRemoteCommand = async (command: RemoteCommandItem) => {
    setBusy(true);
    try {
      const response = await cancelRemoteCommand(command.id);
      setNotice({ text: response.message });
      await loadData();
    } catch (err: unknown) {
      setNotice({
        text: err instanceof Error ? err.message : "Không thể hủy lệnh từ xa.",
        error: true,
      });
    } finally {
      setBusy(false);
    }
  };

  // Handle Manual Create
  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createMessage.trim()) {
      setNotice({ text: "Vui lòng nhập nội dung yêu cầu.", error: true });
      return;
    }
    setBusy(true);
    try {
      await createClientTaskManual({
        customer_id: createCustId ? Number(createCustId) : null,
        sender_name: createSender.trim() || undefined,
        task_type: createType,
        raw_message: createMessage.trim(),
        priority: createPriority,
        assigned_to: createAssignee.trim() || undefined,
      });
      setShowCreateModal(false);
      setCreateMessage("");
      setCreateSender("");
      setCreateCustId("");
      setNotice({ text: "Đã tạo tác vụ khách hàng mới thành công!" });
      await loadData();
    } catch (err: unknown) {
      setNotice({ text: err instanceof Error ? err.message : "Lỗi tạo tác vụ.", error: true });
    } finally {
      setBusy(false);
    }
  };

  // Filtered Tasks
  const visibleTasks = tasks.filter((t) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      t.raw_message.toLowerCase().includes(q) ||
      (t.customer_name && t.customer_name.toLowerCase().includes(q)) ||
      (t.sender_name && t.sender_name.toLowerCase().includes(q)) ||
      (t.assigned_to && t.assigned_to.toLowerCase().includes(q)) ||
      String(t.id).includes(q)
    );
  });

  // KPI Counts
  const countPending = tasks.filter((t) => t.status === "PENDING").length;
  const countInProgress = tasks.filter((t) => t.status === "IN_PROGRESS").length;
  const countCompleted = tasks.filter((t) => t.status === "COMPLETED").length;
  const countUrgent = tasks.filter((t) => t.priority === "URGENT" && t.status !== "COMPLETED").length;

  return (
    <div className="w-full space-y-6 font-sans">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#111827] p-6 rounded-2xl border border-[#1F2937]">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-gray-100 tracking-tight m-0">
              Hộp Thư AI &amp; Quản Lý Tác Vụ Khách Hàng
            </h2>
            <span className="text-xs px-2.5 py-0.5 rounded-full font-mono bg-blue-500/15 text-blue-300 border border-blue-500/30">
              Smart Task Dispatcher
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            Tự động nhận diện khách hàng, phân loại yêu cầu Telegram (Mời mail BM, Cấp TKQC, Trả nợ cước) và phân luồng xử lý không để sót việc.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* View Toggle */}
          <div className="flex items-center bg-[#1A2234] p-1 rounded-xl border border-[#374151]">
            <button
              onClick={() => setViewMode("table")}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                viewMode === "table" ? "bg-purple-600 text-white font-semibold" : "text-gray-400 hover:text-white"
              }`}
              type="button"
            >
              Dạng Bảng
            </button>
            <button
              onClick={() => setViewMode("kanban")}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                viewMode === "kanban" ? "bg-purple-600 text-white font-semibold" : "text-gray-400 hover:text-white"
              }`}
              type="button"
            >
              Dạng Kanban
            </button>
          </div>

          <Link
            href="/clients"
            className="px-3.5 py-2 rounded-xl text-xs font-semibold text-purple-300 bg-purple-500/15 border border-purple-500/30 hover:bg-purple-500/25 transition flex items-center gap-1.5"
          >
             Phân Quyền Multi-BM
          </Link>
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
            onClick={() => setShowCreateModal(true)}
            disabled={busy}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 shadow-md shadow-purple-600/20 transition flex items-center gap-1.5"
            type="button"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            + Tạo Tác Vụ
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
          <button onClick={() => setNotice(null)} className="text-gray-400 hover:text-white" type="button">
            
          </button>
        </div>
      )}

      <section className="bg-[#111827] rounded-2xl border border-[#1F2937] overflow-hidden">
        <div className="px-4 py-3 border-b border-[#1F2937] flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-white m-0">Hàng Đợi Lệnh (Remote Tasks)</h3>
            <p className="text-[11px] text-gray-400 mt-1">
              Backend chỉ xếp lệnh; Chrome Extension thực thi Meta và luôn tạo chiến dịch ở trạng thái PAUSED.
            </p>
          </div>
          <span className="text-xs font-mono text-gray-400">{remoteCommands.length} lệnh gần nhất</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#0B0F19]/60 text-gray-400">
              <tr>
                <th className="px-4 py-3">Ngày tạo</th>
                <th className="px-4 py-3">Khách hàng</th>
                <th className="px-4 py-3">Tài khoản</th>
                <th className="px-4 py-3">Lệnh / Chiến dịch</th>
                <th className="px-4 py-3">Trạng thái</th>
                <th className="px-4 py-3">Kết quả</th>
                <th className="px-4 py-3 text-right">Thao tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1F2937]">
              {remoteCommands.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                    Chưa có lệnh từ xa nào.
                  </td>
                </tr>
              ) : remoteCommands.map((command) => {
                const status = remoteStatusConfig[command.status] || {
                  label: command.status,
                  badge: "bg-gray-800 text-gray-400 border-gray-700",
                };
                return (
                  <tr key={command.id} className="hover:bg-[#1A2234]/40">
                    <td className="px-4 py-3 text-gray-400 whitespace-nowrap">
                      {command.created_at
                        ? new Date(command.created_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-purple-300">{command.customer_name || "Chưa gán"}</td>
                    <td className="px-4 py-3 font-mono text-blue-300">{command.ad_account_id}</td>
                    <td className="px-4 py-3">
                      <div className="font-mono text-gray-300">{command.command_type}</div>
                      <div className="text-[11px] text-gray-500 mt-1">{command.campaign_name || "—"}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold ${status.badge}`}>
                        {status.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-400 max-w-sm break-words">
                      {command.result_log || "—"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {command.status === "PENDING" ? (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void handleCancelRemoteCommand(command)}
                          className="px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/30 hover:bg-rose-500/25 disabled:opacity-50"
                        >
                          Hủy Lệnh
                        </button>
                      ) : <span className="text-gray-600">—</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* KPI Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-[#111827] p-4 rounded-2xl border border-[#1F2937]">
          <span className="text-xs text-amber-400 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
            Chờ Tiếp Nhận (Pending)
          </span>
          <div className="text-2xl font-bold font-mono tabular-nums text-amber-300 mt-1">{countPending}</div>
          <div className="text-[11px] text-gray-500 mt-1">Yêu cầu mới từ khách</div>
        </div>

        <div className="bg-[#111827] p-4 rounded-2xl border border-[#1F2937]">
          <span className="text-xs text-blue-400">Đang Xử Lý (In Progress)</span>
          <div className="text-2xl font-bold font-mono tabular-nums text-blue-300 mt-1">{countInProgress}</div>
          <div className="text-[11px] text-gray-500 mt-1">Kỹ thuật viên đang làm</div>
        </div>

        <div className="bg-[#111827] p-4 rounded-2xl border border-[#1F2937]">
          <span className="text-xs text-emerald-400">Đã Hoàn Thành (Done)</span>
          <div className="text-2xl font-bold font-mono tabular-nums text-emerald-400 mt-1">{countCompleted}</div>
          <div className="text-[11px] text-gray-500 mt-1">Đã giao kết quả cho khách</div>
        </div>

        <div className="bg-[#111827] p-4 rounded-2xl border border-[#1F2937]">
          <span className="text-xs text-rose-400">Khẩn Cấp (Urgent)</span>
          <div className="text-2xl font-bold font-mono tabular-nums text-rose-400 mt-1">{countUrgent}</div>
          <div className="text-[11px] text-gray-500 mt-1">Nợ cước / Dừng quảng cáo</div>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-[#111827] p-3 rounded-2xl border border-[#1F2937]">
        <div className="flex items-center gap-2 flex-wrap">
          <input
            type="text"
            placeholder="Tìm theo nội dung, khách hàng, ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-purple-500 min-w-[220px]"
          />

          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="bg-[#1A2234] border border-[#374151] rounded-xl px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-purple-500"
          >
            <option value="ALL">Tất cả loại tác vụ</option>
            <option value="ADD_MAIL_TO_BM">Mời mail vào BM</option>
            <option value="ADD_AD_ACCOUNT">Thêm / Gán TKQC</option>
            <option value="SETTLE_DEBT">Thanh toán nợ cước</option>
            <option value="TOPUP_BUDGET">Nạp ngân sách</option>
            <option value="CHECK_BALANCE">Tra cứu số dư</option>
            <option value="GENERAL_SUPPORT">Hỗ trợ chung</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-[#1A2234] border border-[#374151] rounded-xl px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-purple-500"
          >
            <option value="ALL">Tất cả trạng thái</option>
            <option value="PENDING">Chờ xử lý (Pending)</option>
            <option value="IN_PROGRESS">Đang xử lý (In Progress)</option>
            <option value="COMPLETED">Đã hoàn thành</option>
            <option value="CANCELLED">Đã hủy</option>
          </select>
        </div>

        <span className="text-xs text-gray-500 font-mono text-right">
          Hiển thị {visibleTasks.length} / {tasks.length} tác vụ
        </span>
      </div>

      {/* VIEW 1: TABLE MODE */}
      {viewMode === "table" && (
        <div className="bg-[#111827] rounded-2xl border border-[#1F2937] overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-[#0B0F19]/60 text-gray-400 border-b border-[#1F2937]">
                  <th className="py-3 px-4 font-semibold">Mã</th>
                  <th className="py-3 px-4 font-semibold">Khách Hàng / Nguồn</th>
                  <th className="py-3 px-4 font-semibold">Phân Loại Yêu Cầu</th>
                  <th className="py-3 px-4 font-semibold">Nội Dung Tin Nhắn</th>
                  <th className="py-3 px-4 font-semibold">Dữ Liệu Trích Xuất (AI)</th>
                  <th className="py-3 px-4 font-semibold">Mức Độ</th>
                  <th className="py-3 px-4 font-semibold">Trạng Thái</th>
                  <th className="py-3 px-4 font-semibold">Phụ Trách</th>
                  <th className="py-3 px-4 font-semibold text-right">Thao Tác Nhanh</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1F2937]/50">
                {visibleTasks.length > 0 ? (
                  visibleTasks.map((t) => {
                    const tc = typeConfig[t.task_type] || {
                      label: t.task_type,
                      badge: "bg-gray-800 text-gray-400",
                      icon: "",
                    };
                    const sc = statusConfig[t.status] || {
                      label: t.status,
                      badge: "bg-gray-800 text-gray-400",
                    };

                    return (
                      <tr key={t.id} className="hover:bg-[#1A2234]/50 transition">
                        <td className="py-3 px-4 font-mono text-gray-500">#{t.id}</td>
                        <td className="py-3 px-4">
                          <div className="font-semibold text-gray-200">
                            {t.customer_name ? (
                              <span className="text-purple-300">{t.customer_name}</span>
                            ) : (
                              <span className="text-gray-400 italic">Khách vãng lai</span>
                            )}
                          </div>
                          <div className="text-[11px] text-gray-500 font-mono">
                            {t.sender_name || t.telegram_username ? `@${t.telegram_username || t.sender_name}` : `ID: ${t.telegram_chat_id}`}
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border flex items-center gap-1 w-max ${tc.badge}`}>
                            <span>{tc.icon}</span>
                            <span>{tc.label}</span>
                          </span>
                        </td>
                        <td className="py-3 px-4 text-gray-300 max-w-xs break-words" title={t.raw_message}>
                          {t.raw_message}
                        </td>
                        <td className="py-3 px-4">
                          {t.extracted_data && Object.keys(t.extracted_data).length > 0 ? (
                            <div className="flex flex-col gap-1 text-[11px]">
                              {Boolean(t.extracted_data.email) && (
                                <span className="font-mono text-purple-300 bg-purple-500/10 px-1.5 py-0.5 rounded w-max">
                                   {String(t.extracted_data.email)}
                                </span>
                              )}
                              {Boolean(t.extracted_data.bm_id) && (
                                <span className="font-mono text-blue-300 bg-blue-500/10 px-1.5 py-0.5 rounded w-max">
                                   BM: {String(t.extracted_data.bm_id)}
                                </span>
                              )}
                              {Boolean(t.extracted_data.account_id) && (
                                <span className="font-mono text-emerald-300 bg-emerald-500/10 px-1.5 py-0.5 rounded w-max">
                                   TK: {String(t.extracted_data.account_id)}
                                </span>
                              )}
                              {Boolean(t.extracted_data.role) && (
                                <span className="text-gray-300 text-[10px]">
                                  Quyền: <b>{String(t.extracted_data.role)}</b>
                                </span>
                              )}
                              {t.customer_id && bmPrefs[t.customer_id] && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    setBmModalClient({ id: t.customer_id!, name: t.customer_name || "Khách hàng" });
                                    setShowBmModal(true);
                                  }}
                                  className="font-mono text-purple-300 bg-purple-500/15 hover:bg-purple-500/25 border border-purple-500/30 px-1.5 py-0.5 rounded text-[10px] w-max flex items-center gap-1 transition"
                                  title="Chỉnh sửa phân quyền BM cho khách hàng này"
                                >
                                   {bmPrefs[t.customer_id].bm_name} ({bmPrefs[t.customer_id].bm_role})
                                </button>
                              )}
                            </div>
                          ) : (
                            <span className="text-gray-600">—</span>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${priorityBadges[t.priority] || "text-gray-400"}`}>
                            {t.priority}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${sc.badge}`}>
                            {sc.label}
                          </span>
                        </td>
                        <td className="py-3 px-4 font-mono text-[11px] text-gray-400">
                          {t.assigned_to || <span className="text-gray-600 italic">Chưa gán</span>}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <div className="flex items-center justify-end gap-1 flex-wrap">
                            {t.status === "PENDING" && (
                              <button
                                onClick={() => void handleUpdateStatus(t, "IN_PROGRESS", undefined, "admin")}
                                disabled={busy}
                                className="px-2 py-1 rounded-md text-[11px] font-semibold bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 border border-blue-500/30 transition"
                                type="button"
                              >
                                Tiếp nhận
                              </button>
                            )}
                            {t.status === "IN_PROGRESS" && (
                              <button
                                onClick={() => void handleUpdateStatus(t, "COMPLETED", "Đã xử lý xong yêu cầu")}
                                disabled={busy}
                                className="px-2 py-1 rounded-md text-[11px] font-semibold bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 border border-emerald-500/30 transition"
                                type="button"
                              >
                                Hoàn thành
                              </button>
                            )}
                            {t.customer_id && (
                              <button
                                onClick={() => {
                                  setBmModalClient({ id: t.customer_id!, name: t.customer_name || "Khách hàng" });
                                  setShowBmModal(true);
                                }}
                                disabled={busy}
                                className="px-2 py-1 rounded-md text-[11px] font-semibold bg-purple-600/20 text-purple-300 hover:bg-purple-600/30 border border-purple-500/30 transition"
                                type="button"
                                title="Phân quyền Multi-BM cho khách hàng"
                              >
                                 BM
                              </button>
                            )}
                            <button
                              onClick={() => {
                                setActiveTask(t);
                                setActionStatus(t.status);
                                setActionNotes(t.notes || "");
                                setActionAssignee(t.assigned_to || "");
                                setShowActionModal(true);
                              }}
                              disabled={busy}
                              className="px-2 py-1 rounded-md text-[11px] font-medium bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700 transition"
                              type="button"
                            >
                              Chi tiết
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={9} className="py-8 text-center text-gray-500">
                      Không tìm thấy tác vụ nào phù hợp với bộ lọc hiện thời.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* VIEW 2: KANBAN MODE */}
      {viewMode === "kanban" && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {/* Column 1: PENDING */}
          <div className="bg-[#111827] p-4 rounded-2xl border border-[#1F2937] flex flex-col min-h-[500px]">
            <div className="flex items-center justify-between pb-3 border-b border-[#1F2937] mb-3">
              <span className="font-bold text-xs uppercase text-amber-400 tracking-wider flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-amber-400" />
                Chờ Xử Lý ({tasks.filter((t) => t.status === "PENDING").length})
              </span>
            </div>
            <div className="space-y-3 flex-1 overflow-y-auto">
              {tasks
                .filter((t) => t.status === "PENDING")
                .map((t) => (
                  <div
                    key={t.id}
                    className="bg-[#1A2234] p-3.5 rounded-xl border border-[#374151] hover:border-purple-500/50 transition space-y-2.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono text-gray-500">#{t.id}</span>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${priorityBadges[t.priority]}`}>
                        {t.priority}
                      </span>
                    </div>
                    <div className="font-semibold text-xs text-purple-300">
                      {t.customer_name || t.sender_name || `Khách ${t.telegram_chat_id}`}
                    </div>
                    <p className="text-xs text-gray-300 line-clamp-2">{t.raw_message}</p>
                    {Boolean(t.extracted_data?.email) && (
                      <div className="text-[10px] font-mono bg-purple-500/10 text-purple-300 px-1.5 py-0.5 rounded truncate">
                         {String(t.extracted_data.email)}
                      </div>
                    )}
                    <div className="flex items-center justify-between pt-2 border-t border-[#374151]/60">
                      <span className="text-[10px] text-gray-500">
                        {t.created_at ? new Date(t.created_at).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }) : ""}
                      </span>
                      <button
                        onClick={() => void handleUpdateStatus(t, "IN_PROGRESS", undefined, "admin")}
                        className="px-2 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white font-semibold text-[10px]"
                        type="button"
                      >
                        Tiếp nhận →
                      </button>
                    </div>
                  </div>
                ))}
            </div>
          </div>

          {/* Column 2: IN_PROGRESS */}
          <div className="bg-[#111827] p-4 rounded-2xl border border-[#1F2937] flex flex-col min-h-[500px]">
            <div className="flex items-center justify-between pb-3 border-b border-[#1F2937] mb-3">
              <span className="font-bold text-xs uppercase text-blue-400 tracking-wider flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
                Đang Xử Lý ({tasks.filter((t) => t.status === "IN_PROGRESS").length})
              </span>
            </div>
            <div className="space-y-3 flex-1 overflow-y-auto">
              {tasks
                .filter((t) => t.status === "IN_PROGRESS")
                .map((t) => (
                  <div
                    key={t.id}
                    className="bg-[#1A2234] p-3.5 rounded-xl border border-blue-500/30 hover:border-blue-500 transition space-y-2.5 shadow-md shadow-blue-500/5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono text-gray-500">#{t.id}</span>
                      <span className="text-[10px] text-gray-400 font-mono">
                        Phụ trách: <b>{t.assigned_to || "Admin"}</b>
                      </span>
                    </div>
                    <div className="font-semibold text-xs text-purple-300">
                      {t.customer_name || t.sender_name || `Khách ${t.telegram_chat_id}`}
                    </div>
                    <p className="text-xs text-gray-300">{t.raw_message}</p>
                    <div className="flex items-center justify-between pt-2 border-t border-[#374151]/60">
                      <button
                        onClick={() => {
                          setActiveTask(t);
                          setActionStatus(t.status);
                          setActionNotes(t.notes || "");
                          setActionAssignee(t.assigned_to || "");
                          setShowActionModal(true);
                        }}
                        className="text-[10px] text-gray-400 hover:text-white"
                        type="button"
                      >
                        Ghi chú
                      </button>
                      <button
                        onClick={() => void handleUpdateStatus(t, "COMPLETED", "Đã xử lý xong")}
                        className="px-2 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-[10px]"
                        type="button"
                      >
                        Hoàn thành 
                      </button>
                    </div>
                  </div>
                ))}
            </div>
          </div>

          {/* Column 3: COMPLETED */}
          <div className="bg-[#111827] p-4 rounded-2xl border border-[#1F2937] flex flex-col min-h-[500px]">
            <div className="flex items-center justify-between pb-3 border-b border-[#1F2937] mb-3">
              <span className="font-bold text-xs uppercase text-emerald-400 tracking-wider flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                Đã Hoàn Thành ({tasks.filter((t) => t.status === "COMPLETED").length})
              </span>
            </div>
            <div className="space-y-3 flex-1 overflow-y-auto">
              {tasks
                .filter((t) => t.status === "COMPLETED")
                .slice(0, 15)
                .map((t) => (
                  <div key={t.id} className="bg-[#1A2234]/60 p-3 rounded-xl border border-[#374151]/60 space-y-2 opacity-80 hover:opacity-100 transition">
                    <div className="flex items-center justify-between text-[10px]">
                      <span className="font-mono text-gray-500">#{t.id}</span>
                      <span className="text-emerald-400 font-semibold"> Đã giao</span>
                    </div>
                    <div className="font-semibold text-xs text-gray-200">
                      {t.customer_name || t.sender_name || `Khách ${t.telegram_chat_id}`}
                    </div>
                    <p className="text-xs text-gray-400 line-clamp-1">{t.raw_message}</p>
                    {t.notes && <div className="text-[10px] text-gray-500 italic">Ghi chú: {t.notes}</div>}
                  </div>
                ))}
            </div>
          </div>
        </div>
      )}

      {/* MODAL 1: Create Task Manual */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fadeIn">
          <div className="bg-[#111827] border border-[#1F2937] rounded-2xl w-full max-w-lg p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-[#1F2937] pb-3">
              <h3 className="text-base font-bold text-white tracking-tight">
                Tạo Tác Vụ Khách Hàng Thủ Công
              </h3>
              <button onClick={() => setShowCreateModal(false)} className="text-gray-400 hover:text-white" type="button">
                
              </button>
            </div>

            <form onSubmit={handleCreateTask} className="space-y-4 text-xs">
              <div>
                <label className="block text-gray-300 font-medium mb-1">Khách hàng hồ sơ</label>
                <select
                  value={createCustId}
                  onChange={(e) => setCreateCustId(e.target.value)}
                  className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                >
                  <option value="">-- Để trống nếu khách mới / vãng lai --</option>
                  {customers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} (ID: {c.id})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-gray-300 font-medium mb-1">Tên người gửi / @Username</label>
                  <input
                    type="text"
                    placeholder="VD: @tuan_ads hoặc Anh Tuấn"
                    value={createSender}
                    onChange={(e) => setCreateSender(e.target.value)}
                    className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-gray-300 font-medium mb-1">Phân loại tác vụ (*)</label>
                  <select
                    value={createType}
                    onChange={(e) => setCreateType(e.target.value)}
                    className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="ADD_MAIL_TO_BM">Mời mail vào BM</option>
                    <option value="ADD_AD_ACCOUNT">Thêm / Gán TKQC</option>
                    <option value="SETTLE_DEBT">Thanh toán nợ cước</option>
                    <option value="TOPUP_BUDGET">Nạp ngân sách</option>
                    <option value="CHECK_BALANCE">Tra cứu số dư</option>
                    <option value="GENERAL_SUPPORT">Hỗ trợ chung</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-gray-300 font-medium mb-1">Nội dung yêu cầu từ khách (*)</label>
                <textarea
                  required
                  rows={3}
                  placeholder="Ví dụ: Em ơi mời mail ads.partner@gmail.com vào BM 1020304050 quyền admin giúp anh nhé"
                  value={createMessage}
                  onChange={(e) => setCreateMessage(e.target.value)}
                  className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-gray-300 font-medium mb-1">Mức độ ưu tiên</label>
                  <select
                    value={createPriority}
                    onChange={(e) => setCreatePriority(e.target.value)}
                    className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="LOW">Thấp (LOW)</option>
                    <option value="NORMAL">Bình thường (NORMAL)</option>
                    <option value="HIGH">Cao (HIGH)</option>
                    <option value="URGENT">Khẩn cấp (URGENT)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-gray-300 font-medium mb-1">Gán kỹ thuật viên</label>
                  <input
                    type="text"
                    placeholder="VD: kythuat_01"
                    value={createAssignee}
                    onChange={(e) => setCreateAssignee(e.target.value)}
                    className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-[#1F2937]">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 rounded-xl text-gray-400 hover:text-white hover:bg-gray-800 transition"
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  disabled={busy}
                  className="px-5 py-2 rounded-xl font-semibold text-white bg-purple-600 hover:bg-purple-500 transition"
                >
                  Tạo Tác Vụ
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2: Action / Detail Modal */}
      {showActionModal && activeTask && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fadeIn">
          <div className="bg-[#111827] border border-[#1F2937] rounded-2xl w-full max-w-lg p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-[#1F2937] pb-3">
              <h3 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
                <span>Chi Tiết Tác Vụ #{activeTask.id}</span>
                <span className={`text-[10px] px-2 py-0.5 rounded-full border ${typeConfig[activeTask.task_type]?.badge}`}>
                  {typeConfig[activeTask.task_type]?.label || activeTask.task_type}
                </span>
              </h3>
              <button onClick={() => setShowActionModal(false)} className="text-gray-400 hover:text-white" type="button">
                
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="bg-[#1A2234] p-3 rounded-xl border border-[#374151] space-y-1.5">
                <div className="text-gray-400">Khách hàng: <strong className="text-purple-300">{activeTask.customer_name || "Vãng lai"}</strong></div>
                <div className="text-gray-400">Nguồn: <span className="font-mono text-gray-300">{activeTask.sender_name || activeTask.telegram_username || activeTask.telegram_chat_id}</span></div>
                <div className="text-gray-400">Nội dung gốc:</div>
                <div className="p-2.5 rounded-lg bg-[#0B0F19] text-gray-200 border border-[#1F2937] select-all">
                  {activeTask.raw_message}
                </div>
              </div>

              {activeTask.extracted_data && Object.keys(activeTask.extracted_data).length > 0 && (
                <div className="bg-[#1A2234] p-3 rounded-xl border border-[#374151] space-y-1">
                  <div className="text-gray-400 font-semibold mb-1">Dữ liệu bóc tách từ AI:</div>
                  <pre className="text-[11px] font-mono text-emerald-300 whitespace-pre-wrap">
                    {JSON.stringify(activeTask.extracted_data, null, 2)}
                  </pre>
                </div>
              )}

              {activeTask.customer_id && (
                <div className="bg-[#1A2234] p-3 rounded-xl border border-purple-500/30 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 font-semibold text-purple-300">
                      <span> Phân Quyền Multi-BM</span>
                      {bmPrefs[activeTask.customer_id]?.is_configured ? (
                        <span className="text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-2 py-0.5 rounded-full">
                          Đã ghi nhớ
                        </span>
                      ) : (
                        <span className="text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/30 px-2 py-0.5 rounded-full">
                          Chưa thiết lập
                        </span>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setBmModalClient({
                          id: activeTask.customer_id!,
                          name: activeTask.customer_name || "Khách hàng",
                        });
                        setShowBmModal(true);
                      }}
                      className="px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-purple-600 hover:bg-purple-500 text-white transition flex items-center gap-1 shadow"
                    >
                       Chỉnh Sửa BM (1-Click)
                    </button>
                  </div>

                  <div className="grid grid-cols-3 gap-2 text-[11px] bg-[#0B0F19] p-2 rounded-lg border border-[#1F2937]">
                    <div>
                      <span className="text-gray-400 block text-[10px]">BM Chỉ Định:</span>
                      <strong className="text-white">
                        {bmPrefs[activeTask.customer_id]?.bm_name || "BM 1 (Mặc định)"}
                      </strong>
                    </div>
                    <div>
                      <span className="text-gray-400 block text-[10px]">Vai Trò:</span>
                      <strong className="text-blue-300">
                        {bmPrefs[activeTask.customer_id]?.bm_role_label || "Nhân viên"}
                      </strong>
                    </div>
                    <div>
                      <span className="text-gray-400 block text-[10px]">Quyền TKQC:</span>
                      <strong className="text-emerald-300">
                        {bmPrefs[activeTask.customer_id]?.ad_account_access_label || "Truy cập đầy đủ"}
                      </strong>
                    </div>
                  </div>
                </div>
              )}

              <div>
                <label className="block text-gray-300 font-medium mb-1">Cập nhật trạng thái</label>
                <select
                  value={actionStatus}
                  onChange={(e) => setActionStatus(e.target.value)}
                  className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                >
                  <option value="PENDING">Chờ xử lý (PENDING)</option>
                  <option value="IN_PROGRESS">Đang xử lý (IN_PROGRESS)</option>
                  <option value="COMPLETED">Đã hoàn thành (COMPLETED)</option>
                  <option value="CANCELLED">Đã hủy (CANCELLED)</option>
                </select>
              </div>

              <div>
                <label className="block text-gray-300 font-medium mb-1">Người phụ trách xử lý</label>
                <input
                  type="text"
                  placeholder="Tên kỹ thuật viên"
                  value={actionAssignee}
                  onChange={(e) => setActionAssignee(e.target.value)}
                  className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-gray-300 font-medium mb-1">Ghi chú kết quả / Lưu vết nội bộ</label>
                <textarea
                  rows={2}
                  placeholder="Ghi chú link invite, ID tài khoản đã cấp hoặc lý do hủy..."
                  value={actionNotes}
                  onChange={(e) => setActionNotes(e.target.value)}
                  className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-[#1F2937]">
                <button
                  type="button"
                  onClick={() => setShowActionModal(false)}
                  className="px-4 py-2 rounded-xl text-gray-400 hover:text-white hover:bg-gray-800 transition"
                >
                  Đóng
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void handleUpdateStatus(activeTask, actionStatus, actionNotes, actionAssignee)}
                  className="px-5 py-2 rounded-xl font-semibold text-white bg-purple-600 hover:bg-purple-500 transition"
                >
                  Lưu Thay Đổi
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Multi-BM Preferences Modal */}
      {bmModalClient && (
        <ClientBMPreferenceModal
          clientId={bmModalClient.id}
          clientName={bmModalClient.name}
          isOpen={showBmModal}
          onClose={() => {
            setShowBmModal(false);
            setBmModalClient(null);
          }}
          onSaved={() => {
            void loadData();
          }}
        />
      )}
    </div>
  );
}
