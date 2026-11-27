"use client";

import React, { useEffect, useState } from "react";
import { MonoIcon } from "./mono-icon";
import {
  CampaignTemplateItem,
  createCampaignTemplate,
  deleteCampaignTemplate,
  ExtensionRemoteTaskItem,
  listCampaignTemplates,
  pollExtensionTasks,
  queueExtensionTask,
} from "@/lib/api";

type AutoSetCampModalProps = {
  isOpen: boolean;
  onClose: () => void;
  vias?: Array<{ id: number; uid: string; profile_name: string; token_status: string }>;
  defaultActId?: string;
  defaultViaId?: number;
};

export default function AutoSetCampModal({
  isOpen,
  onClose,
  vias = [],
  defaultActId = "",
  defaultViaId,
}: AutoSetCampModalProps) {
  const [activeTab, setActiveTab] = useState<"dispatch" | "templates" | "history">("dispatch");

  // Templates
  const [templates, setTemplates] = useState<CampaignTemplateItem[]>([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);

  // New Template Form
  const [newTemplateName, setNewTemplateName] = useState("");
  const [newObjective, setNewObjective] = useState("OUTCOME_ENGAGEMENT");
  const [newBudget, setNewBudget] = useState("500000");
  const [newPageId, setNewPageId] = useState("");
  const [newPostId, setNewPostId] = useState("");
  const [newTemplateStatus, setNewTemplateStatus] = useState<"ACTIVE" | "PAUSED">("ACTIVE");
  const [savingTemplate, setSavingTemplate] = useState(false);

  // Dispatch Form
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("");
  const [selectedViaId, setSelectedViaId] = useState<string>(defaultViaId ? String(defaultViaId) : "");
  const [targetActId, setTargetActId] = useState<string>(defaultActId);
  const [overrideBudget, setOverrideBudget] = useState<string>("");
  const [campaignStatus, setCampaignStatus] = useState<"ACTIVE" | "PAUSED">("ACTIVE");
  const [dispatching, setDispatching] = useState(false);
  const [notice, setNotice] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Task History
  const [tasks, setTasks] = useState<ExtensionRemoteTaskItem[]>([]);
  const [loadingTasks, setLoadingTasks] = useState(false);

  useEffect(() => {
    if (isOpen) {
      loadTemplates();
      loadTasks();
      if (defaultViaId) setSelectedViaId(String(defaultViaId));
      if (defaultActId) setTargetActId(defaultActId);
    }
  }, [isOpen, defaultViaId, defaultActId]);

  async function loadTemplates() {
    setLoadingTemplates(true);
    try {
      const data = await listCampaignTemplates();
      setTemplates(data);
      if (data.length > 0 && !selectedTemplateId) {
        setSelectedTemplateId(String(data[0].id));
      }
    } catch (_) {
    } finally {
      setLoadingTemplates(false);
    }
  }

  async function loadTasks() {
    setLoadingTasks(true);
    try {
      const data = await pollExtensionTasks({ limit: 20 });
      setTasks(data.tasks || []);
    } catch (_) {
    } finally {
      setLoadingTasks(false);
    }
  }

  async function handleCreateTemplate(e: React.FormEvent) {
    e.preventDefault();
    if (!newTemplateName.trim()) return;
    setSavingTemplate(true);
    setNotice(null);
    try {
      await createCampaignTemplate({
        name: newTemplateName.trim(),
        objective: newObjective,
        daily_budget: newBudget.trim() || "500000",
        page_id: newPageId.trim() || undefined,
        post_id_or_creative_json: newPostId.trim() || undefined,
        status_on_create: newTemplateStatus,
      });
      setNewTemplateName("");
      setNewPageId("");
      setNewPostId("");
      await loadTemplates();
      setNotice({ type: "success", text: "Đã lưu mẫu chiến dịch thành công!" });
    } catch (err: unknown) {
      setNotice({ type: "error", text: (err instanceof Error ? err.message : "") || "Lưu mẫu thất bại." });
    } finally {
      setSavingTemplate(false);
    }
  }

  async function handleDeleteTemplate(id: number) {
    if (!confirm("Bạn có chắc chắn muốn xóa mẫu chiến dịch này?")) return;
    try {
      await deleteCampaignTemplate(id);
      setTemplates((prev) => prev.filter((t) => t.id !== id));
    } catch (err: unknown) {
      alert((err instanceof Error ? err.message : "") || "Xóa mẫu thất bại.");
    }
  }

  async function handleDispatch(e: React.FormEvent) {
    e.preventDefault();
    setNotice(null);

    const chosenTemplate = templates.find((t) => String(t.id) === selectedTemplateId);
    const chosenVia = vias.find((v) => String(v.id) === selectedViaId);

    const cleanActId = targetActId.replace("act_", "").trim();
    if (!cleanActId) {
      setNotice({ type: "error", text: "Vui lòng nhập hoặc chọn ID Tài khoản quảng cáo (act_...)" });
      return;
    }

    setDispatching(true);
    try {
      const budgetToUse = overrideBudget.trim() || (chosenTemplate ? chosenTemplate.daily_budget : "500000");

      const res = await queueExtensionTask({
        via_id: chosenVia ? chosenVia.id : undefined,
        fb_uid: chosenVia ? chosenVia.uid : undefined,
        task_type: "CREATE_CAMPAIGN",
        target_act_id: cleanActId,
        requested_by: "WEB_ADMIN",
        payload: {
          name: chosenTemplate ? `${chosenTemplate.name} — Auto` : `Auto Camp ${cleanActId}`,
          objective: chosenTemplate ? chosenTemplate.objective : "OUTCOME_ENGAGEMENT",
          daily_budget: budgetToUse,
          page_id: chosenTemplate ? chosenTemplate.page_id : null,
          post_id: chosenTemplate ? chosenTemplate.post_id_or_creative_json : null,
          status_on_create: campaignStatus,
        },
      });

      setNotice({
        type: "success",
        text: ` Đã bắn lệnh Set Camp thành công (Tác vụ #${res.task_id}) tới VIA ${res.fb_uid}! Extension trên trình duyệt sẽ tự động thực thi.`,
      });
      await loadTasks();
      setActiveTab("history");
    } catch (err: unknown) {
      setNotice({ type: "error", text: (err instanceof Error ? err.message : "") || "Bắn lệnh thất bại." });
    } finally {
      setDispatching(false);
    }
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-in fade-in duration-200">
      <div className="relative w-full max-w-3xl rounded-2xl border border-slate-800 bg-[#0f172a] shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* HEADER */}
        <div className="flex items-center justify-between border-b border-slate-800/80 px-6 py-4 bg-[#111827]/90">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10 text-xl text-emerald-400 border border-emerald-500/20">
              
            </span>
            <div>
              <h2 className="text-lg font-bold text-white tracking-tight">
                Tự Động Set Camp & Điều Khiển Từ Xa (Remote Engine)
              </h2>
              <p className="text-xs text-slate-400">
                Lên chiến dịch Meta tự động bằng phiên Chrome thật của VIA qua Chrome Extension
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <MonoIcon name="close" className="h-4 w-4" />
          </button>
        </div>

        {/* TABS */}
        <div className="flex border-b border-slate-800 bg-slate-950/60 px-6 pt-2 gap-2">
          <button
            onClick={() => setActiveTab("dispatch")}
            className={`px-4 py-2 text-xs font-semibold rounded-t-lg transition-colors border-b-2 ${
              activeTab === "dispatch"
                ? "border-emerald-500 text-emerald-400 bg-emerald-950/20"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
             Bắn Lệnh Set Camp Mới
          </button>
          <button
            onClick={() => setActiveTab("templates")}
            className={`px-4 py-2 text-xs font-semibold rounded-t-lg transition-colors border-b-2 ${
              activeTab === "templates"
                ? "border-indigo-500 text-indigo-400 bg-[#eef4ff]"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
             Quản Lý Mẫu Chiến Dịch ({templates.length})
          </button>
          <button
            onClick={() => {
              setActiveTab("history");
              loadTasks();
            }}
            className={`px-4 py-2 text-xs font-semibold rounded-t-lg transition-colors border-b-2 ${
              activeTab === "history"
                ? "border-amber-500 text-amber-400 bg-amber-950/20"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
             Lịch Sử Thực Thi ({tasks.length})
          </button>
        </div>

        {/* BODY */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {notice && (
            <div
              className={`rounded-xl border px-4 py-3 text-xs flex items-center justify-between ${
                notice.type === "success"
                  ? "border-emerald-500/30 bg-emerald-950/20 text-emerald-300"
                  : "border-rose-500/30 bg-rose-950/20 text-rose-300"
              }`}
            >
              <span>{notice.text}</span>
              <button onClick={() => setNotice(null)} className="text-slate-400 hover:text-white">
                
              </button>
            </div>
          )}

          {/* TAB 1: DISPATCH FORM */}
          {activeTab === "dispatch" && (
            <form onSubmit={handleDispatch} className="space-y-4">
              <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Select Template */}
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Mẫu Chiến Dịch (Template):
                    </label>
                    <select
                      value={selectedTemplateId}
                      onChange={(e) => setSelectedTemplateId(e.target.value)}
                      className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
                    >
                      {templates.length === 0 ? (
                        <option value="">-- Chưa có mẫu (Dùng mặc định Mess 500k) --</option>
                      ) : (
                        templates.map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.name} ({parseInt(t.daily_budget).toLocaleString("vi-VN")} đ · {t.objective})
                          </option>
                        ))
                      )}
                    </select>
                  </div>

                  {/* Select VIA */}
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      VIA Thực Thi (Trình duyệt Chrome mở):
                    </label>
                    <select
                      value={selectedViaId}
                      onChange={(e) => setSelectedViaId(e.target.value)}
                      className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
                    >
                      <option value="">-- Tự động chọn VIA đang ACTIVE --</option>
                      {vias.map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.profile_name} ({v.uid}) [{v.token_status}]
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Target Ad Account */}
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      ID Tài Khoản Quảng Cáo (act_...):
                    </label>
                    <input
                      type="text"
                      placeholder="VD: 100088402955133 hoặc act_12345678"
                      value={targetActId}
                      onChange={(e) => setTargetActId(e.target.value)}
                      className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-mono text-white focus:border-emerald-500 focus:outline-none"
                    />
                  </div>

                  {/* Override Budget */}
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Ngân Sách Ngày (VND, bỏ trống để dùng theo mẫu):
                    </label>
                    <input
                      type="number"
                      placeholder="VD: 500000"
                      value={overrideBudget}
                      onChange={(e) => setOverrideBudget(e.target.value)}
                      className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-mono text-white focus:border-emerald-500 focus:outline-none"
                    />
                  </div>

                  {/* Campaign Status (D-065) */}
                  <div className="md:col-span-2">
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Trạng Thái Chiến Dịch (D-065):
                    </label>
                    <div className="flex items-center gap-3">
                      <label className="flex items-center gap-2 cursor-pointer bg-slate-950 px-3 py-2 rounded-xl border border-slate-800 hover:border-emerald-500 transition">
                        <input
                          type="radio"
                          name="campaignStatus"
                          value="ACTIVE"
                          checked={campaignStatus === "ACTIVE"}
                          onChange={() => setCampaignStatus("ACTIVE")}
                          className="text-emerald-500 focus:ring-emerald-500"
                        />
                        <span className="text-xs font-semibold text-emerald-400">ACTIVE (Bật chạy ngay)</span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer bg-slate-950 px-3 py-2 rounded-xl border border-slate-800 hover:border-amber-500 transition">
                        <input
                          type="radio"
                          name="campaignStatus"
                          value="PAUSED"
                          checked={campaignStatus === "PAUSED"}
                          onChange={() => setCampaignStatus("PAUSED")}
                          className="text-amber-500 focus:ring-amber-500"
                        />
                        <span className="text-xs font-semibold text-amber-400">PAUSED (Tạm dừng - Chờ duyệt)</span>
                      </label>
                    </div>
                  </div>
                </div>

                <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-3 text-xs text-slate-400 flex items-start gap-2">
                  <span className="text-emerald-400 text-sm"></span>
                  <span>
                    Lệnh Set Camp sẽ được đẩy trực tiếp vào hàng đợi <code>extension_remote_tasks</code>. Khi trình duyệt Chrome của VIA mở, Extension tự động gọi Meta Graph API từ chính IP/Proxy và Cookie của VIA, tránh 100% rủi ro Checkpoint do lệch IP máy chủ!
                  </span>
                </div>

                <button
                  type="submit"
                  disabled={dispatching}
                  className="w-full rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 py-3 text-xs font-bold text-white shadow-lg shadow-emerald-950/50 hover:from-emerald-500 hover:to-teal-500 disabled:opacity-50 transition-all"
                >
                  {dispatching ? " Đang Bắn Lệnh..." : " Bắn Lệnh Set Camp Xuống Extension Ngay"}
                </button>
              </div>
            </form>
          )}

          {/* TAB 2: MANAGE TEMPLATES */}
          {activeTab === "templates" && (
            <div className="space-y-4">
              {/* CREATE TEMPLATE FORM */}
              <form onSubmit={handleCreateTemplate} className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-3">
                <div className="text-xs font-bold text-indigo-400 flex items-center gap-1.5">
                  <span></span> Thêm Mẫu Chiến Dịch Mới
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-[11px] text-slate-400 mb-1">Tên Mẫu:</label>
                    <input
                      type="text"
                      placeholder="VD: Mẫu Mess Thời Trang Nữ"
                      value={newTemplateName}
                      onChange={(e) => setNewTemplateName(e.target.value)}
                      className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-white focus:border-indigo-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-slate-400 mb-1">Mục Tiêu:</label>
                    <select
                      value={newObjective}
                      onChange={(e) => setNewObjective(e.target.value)}
                      className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-white focus:border-indigo-500 focus:outline-none"
                    >
                      <option value="OUTCOME_ENGAGEMENT">Tương tác / Tin nhắn (Engagement)</option>
                      <option value="OUTCOME_SALES">Doanh số / Chuyển đổi (Sales)</option>
                      <option value="OUTCOME_TRAFFIC">Lưu lượng truy cập (Traffic)</option>
                      <option value="OUTCOME_LEADS">Khách hàng tiềm năng (Leads)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[11px] text-slate-400 mb-1">Ngân Sách Ngày (VND):</label>
                    <input
                      type="number"
                      value={newBudget}
                      onChange={(e) => setNewBudget(e.target.value)}
                      className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-white focus:border-indigo-500 focus:outline-none"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] text-slate-400 mb-1">ID Fanpage (tùy chọn):</label>
                    <input
                      type="text"
                      placeholder="VD: 100234567890123"
                      value={newPageId}
                      onChange={(e) => setNewPageId(e.target.value)}
                      className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-white focus:border-indigo-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-slate-400 mb-1">ID Bài Viết / Creative (tùy chọn):</label>
                    <input
                      type="text"
                      placeholder="VD: 100234567890123_987654321"
                      value={newPostId}
                      onChange={(e) => setNewPostId(e.target.value)}
                      className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-white focus:border-indigo-500 focus:outline-none"
                    />
                  </div>
                </div>

                <div className="flex justify-end">
                  <button
                    type="submit"
                    disabled={savingTemplate || !newTemplateName.trim()}
                    className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors"
                  >
                    {savingTemplate ? "Đang lưu..." : " Lưu Mẫu Chiến Dịch"}
                  </button>
                </div>
              </form>

              {/* TEMPLATES LIST */}
              <div className="rounded-xl border border-slate-800 overflow-hidden">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-slate-800 bg-slate-950/60 text-slate-400 font-semibold">
                      <th className="p-3">Tên Mẫu</th>
                      <th className="p-3">Mục Tiêu</th>
                      <th className="p-3">Ngân Sách</th>
                      <th className="p-3">Page / Bài Viết</th>
                      <th className="p-3 text-right">Thao Tác</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 text-slate-300">
                    {loadingTemplates ? (
                      <tr>
                        <td colSpan={5} className="p-4 text-center text-slate-500">
                          Đang tải mẫu...
                        </td>
                      </tr>
                    ) : templates.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="p-4 text-center text-slate-500">
                          Chưa có mẫu nào. Hãy tạo mẫu đầu tiên ở form trên!
                        </td>
                      </tr>
                    ) : (
                      templates.map((t) => (
                        <tr key={t.id} className="hover:bg-slate-800/30 transition-colors">
                          <td className="p-3 font-semibold text-white">{t.name}</td>
                          <td className="p-3">
                            <span className="bg-slate-800 px-2 py-0.5 rounded text-[11px] text-sky-300 font-mono">
                              {t.objective}
                            </span>
                          </td>
                          <td className="p-3 font-mono text-emerald-400">
                            {parseInt(t.daily_budget).toLocaleString("vi-VN")} ₫
                          </td>
                          <td className="p-3 text-slate-400 font-mono text-[11px]">
                            {t.page_id || t.post_id_or_creative_json ? (
                              <span>
                                {t.page_id ? `Page: ${t.page_id}` : ""} {t.post_id_or_creative_json ? `Post: ${t.post_id_or_creative_json}` : ""}
                              </span>
                            ) : (
                              <span className="text-slate-600">---</span>
                            )}
                          </td>
                          <td className="p-3 text-right">
                            <button
                              onClick={() => handleDeleteTemplate(t.id)}
                              className="rounded-lg border border-rose-500/20 bg-rose-950/20 px-2.5 py-1 text-[11px] text-rose-300 hover:bg-rose-900/40 transition-colors"
                            >
                              Xóa
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 3: TASK HISTORY */}
          {activeTab === "history" && (
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-xs text-slate-400">
                  Hiển thị 20 lệnh điều phối gần nhất gửi xuống các VIA
                </span>
                <button
                  onClick={loadTasks}
                  disabled={loadingTasks}
                  className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1 text-xs text-slate-300 hover:bg-slate-700 transition-colors"
                >
                  {loadingTasks ? "Đang tải..." : " Làm mới"}
                </button>
              </div>

              <div className="rounded-xl border border-slate-800 overflow-hidden">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-slate-800 bg-slate-950/60 text-slate-400 font-semibold">
                      <th className="p-3">Mã #</th>
                      <th className="p-3">Lệnh</th>
                      <th className="p-3">Mục Tiêu TKQC</th>
                      <th className="p-3">VIA Điều Phối</th>
                      <th className="p-3">Trạng Thái</th>
                      <th className="p-3">Thời Gian</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 text-slate-300">
                    {loadingTasks ? (
                      <tr>
                        <td colSpan={6} className="p-4 text-center text-slate-500">
                          Đang tải danh sách tác vụ...
                        </td>
                      </tr>
                    ) : tasks.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="p-4 text-center text-slate-500">
                          Chưa có tác vụ nào trong hàng đợi.
                        </td>
                      </tr>
                    ) : (
                      tasks.map((t) => {
                        const isDone = t.status === "COMPLETED";
                        const isRunning = t.status === "RUNNING";
                        const isFailed = t.status === "FAILED";

                        return (
                          <tr key={t.id} className="hover:bg-slate-800/30 transition-colors">
                            <td className="p-3 font-mono text-slate-400">#{t.id}</td>
                            <td className="p-3 font-semibold text-white">
                              <span className="bg-[#eef4ff] border border-indigo-500/30 px-2 py-0.5 rounded text-[11px] text-indigo-300">
                                {t.task_type}
                              </span>
                            </td>
                            <td className="p-3 font-mono text-slate-300">
                              {t.target_act_id ? `act_${t.target_act_id}` : "---"}
                            </td>
                            <td className="p-3 font-mono text-slate-400">{t.fb_uid}</td>
                            <td className="p-3">
                              <span
                                className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                                  isDone
                                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                                    : isRunning
                                    ? "bg-sky-500/10 text-sky-400 border-sky-500/30 animate-pulse"
                                    : isFailed
                                    ? "bg-rose-500/10 text-rose-400 border-rose-500/30"
                                    : "bg-amber-500/10 text-amber-400 border-amber-500/30"
                                }`}
                              >
                                {t.status}
                              </span>
                            </td>
                            <td className="p-3 text-slate-500">
                              {new Date(t.created_at).toLocaleTimeString("vi-VN")}
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* FOOTER */}
        <div className="border-t border-slate-800/80 px-6 py-3 bg-[#111827]/80 flex justify-end">
          <button
            onClick={onClose}
            className="rounded-xl border border-slate-700 bg-slate-800 px-5 py-2 text-xs font-semibold text-white hover:bg-slate-700 transition-colors"
          >
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
}
