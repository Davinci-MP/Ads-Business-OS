"use client";

import { useEffect, useMemo, useState } from "react";
import { MonoIcon } from "./mono-icon";
import { shareBmAccounts, type ShareBmAccountsResult, type SyncedAdAccount } from "../lib/api";

type CustomerRef = { id: number; name: string };
type BmRef = { bm_id: string; name: string };

export default function ShareBmAccountsModal({
  open,
  onClose,
  accounts,
  customers,
  bms,
  initialAccountIds,
}: {
  open: boolean;
  onClose: () => void;
  accounts: SyncedAdAccount[];
  customers: CustomerRef[];
  bms: BmRef[];
  initialAccountIds: string[];
}) {
  const [bmId, setBmId] = useState("");
  const [emails, setEmails] = useState("");
  const [role, setRole] = useState("EMPLOYEE");
  const [tasks, setTasks] = useState<string[]>(["ADVERTISE", "ANALYZE"]);
  const [customerId, setCustomerId] = useState("");
  const [manualIds, setManualIds] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ text: string; error?: boolean } | null>(null);
  const [result, setResult] = useState<ShareBmAccountsResult | null>(null);

  const currentRole = useMemo(() => {
    if (typeof window === "undefined") return "";
    try {
      return JSON.parse(localStorage.getItem("adsos_auth_user") || "{}").role || "";
    } catch {
      return "";
    }
  }, [open]);

  const parsedAccountIds = useMemo(() => {
    const ids = new Set<string>();
    for (const line of manualIds.split(/\r?\n/)) {
      const clean = line.replace(/^act_/, "").trim();
      const match = clean.match(/\d{5,25}/);
      if (match) ids.add(match[0]);
    }
    return Array.from(ids);
  }, [manualIds]);

  const parsedEmails = useMemo(() => {
    return emails
      .split(/\r?\n|,/)
      .map((e) => e.trim())
      .filter((e) => e.length > 0);
  }, [emails]);

  useEffect(() => {
    if (!open) return;
    setResult(null);
    setFeedback(null);
    if (!bmId && bms.length > 0) {
      setBmId(bms[0].bm_id);
    }
    if (initialAccountIds && initialAccountIds.length > 0) {
      const clean = initialAccountIds.map((id) => id.replace(/^act_/, "").trim()).filter(Boolean);
      setManualIds(clean.join("\n"));
    }
  }, [open, initialAccountIds, bms]);

  if (!open) return null;

  const toggleTask = (task: string) => {
    setTasks((current) =>
      current.includes(task) ? current.filter((item) => item !== task) : [...current, task]
    );
  };

  const handleSelectCustomer = (cId: string) => {
    setCustomerId(cId);
    if (!cId) return;
    const custAccounts = accounts.filter((a) => String(a.customer_id) === cId);
    const newIds = custAccounts.map((a) => a.act_id.replace(/^act_/, "").trim()).filter(Boolean);
    const current = manualIds.split(/\r?\n/).map((s) => s.replace(/^act_/, "").trim()).filter(Boolean);
    const merged = Array.from(new Set([...current, ...newIds]));
    setManualIds(merged.join("\n"));
    setFeedback({
      text: `Đã tự động thêm ${newIds.length} TKQC của khách hàng vào danh sách gán quyền.`,
      error: false,
    });
  };

  const handleLoadSelectedRows = () => {
    if (!initialAccountIds || initialAccountIds.length === 0) {
      setFeedback({ text: "Hiện không có tài khoản nào đang được tích chọn trên bảng.", error: true });
      return;
    }
    const clean = initialAccountIds.map((id) => id.replace(/^act_/, "").trim()).filter(Boolean);
    const current = manualIds.split(/\r?\n/).map((s) => s.replace(/^act_/, "").trim()).filter(Boolean);
    const merged = Array.from(new Set([...current, ...clean]));
    setManualIds(merged.join("\n"));
    setFeedback({
      text: `Đã nạp ${clean.length} TKQC đang tích chọn trên bảng vào danh sách.`,
      error: false,
    });
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!bmId.trim()) {
      setFeedback({ text: "Vui lòng nhập hoặc chọn Business Manager (BM ID).", error: true });
      return;
    }
    if (parsedEmails.length === 0) {
      setFeedback({ text: "Vui lòng nhập ít nhất một email khách hàng nhận quyền.", error: true });
      return;
    }
    if (parsedAccountIds.length === 0) {
      setFeedback({ text: "Vui lòng cung cấp ít nhất 1 ID tài khoản quảng cáo hợp lệ.", error: true });
      return;
    }
    if (tasks.length === 0) {
      setFeedback({ text: "Vui lòng chọn ít nhất 1 quyền tài khoản quảng cáo (Tasks).", error: true });
      return;
    }

    try {
      setBusy(true);
      setFeedback(null);

      const response = await shareBmAccounts({
        bm_id: bmId.trim(),
        customer_emails: parsedEmails,
        bm_role: role,
        ad_account_tasks: tasks,
        account_ids: parsedAccountIds,
        customer_id: customerId ? Number(customerId) : undefined,
      });

      setResult(response);
      setFeedback({ text: response.message || "Đã xếp lệnh chia sẻ quyền BM & gán TKQC thành công." });

      // Trigger extension bridge if available in browser context
      if (typeof window !== "undefined" && (window as unknown as { ExtensionBridge?: { shareBmAndAssignAccounts?: (p: unknown) => Promise<unknown> } }).ExtensionBridge?.shareBmAndAssignAccounts) {
        try {
          await (window as unknown as { ExtensionBridge: { shareBmAndAssignAccounts: (p: unknown) => Promise<unknown> } }).ExtensionBridge.shareBmAndAssignAccounts({
            bm_id: bmId.trim(),
            customer_emails: parsedEmails,
            bm_role: role,
            ad_account_tasks: tasks,
            account_ids: parsedAccountIds,
            customer_id: customerId ? Number(customerId) : undefined,
          });
        } catch (bridgeErr) {
          console.warn("ExtensionBridge optional relay notice:", bridgeErr);
        }
      }
    } catch (error) {
      setFeedback({
        text: error instanceof Error ? error.message : "Không thể thực thi lệnh chia sẻ BM & gán TKQC.",
        error: true,
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm">
      <div className="relative w-full max-w-2xl max-h-[92vh] overflow-y-auto rounded-2xl border border-[#2A2A32] bg-[#121214] p-6 shadow-2xl text-slate-100 space-y-5">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-[#2A2A32] pb-4">
          <div>
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <svg className="w-5 h-5 text-indigo-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
                <path d="M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
              Chia Sẻ Quyền BM &amp; Gán Tài Khoản Quảng Cáo
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Phân quyền Business Manager qua email khách hàng và gán quyền quản lý / chạy ads hàng loạt tài khoản quảng cáo.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-[#202024] hover:text-white transition"
            aria-label="Đóng"
          >
            <MonoIcon name="close" width={18} />
          </button>
        </div>

        {/* Feedback message */}
        {feedback && (
          <div
            className={`rounded-xl px-4 py-2.5 text-xs font-medium border ${
              feedback.error
                ? "bg-rose-950/40 border-rose-500/50 text-rose-300"
                : "bg-emerald-950/40 border-emerald-500/50 text-emerald-300"
            }`}
            role="status"
          >
            {feedback.text}
          </div>
        )}

        {/* Form */}
        <form onSubmit={submit} className="space-y-4">
          {/* BM ID Selector: Synced list + Manual input */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                BM Đã Đồng Bộ ({bms.length} BM)
              </label>
              <select
                value={bms.some((b) => b.bm_id === bmId) ? bmId : ""}
                onChange={(e) => {
                  if (e.target.value) setBmId(e.target.value);
                }}
                className="w-full bg-[#1A1A1E] border border-[#2A2A32] rounded-lg px-3 py-2 text-xs text-white outline-none focus:border-indigo-500"
              >
                <option value="">— Chọn từ danh sách BM —</option>
                {bms.map((bm) => (
                  <option key={bm.bm_id} value={bm.bm_id}>
                    {bm.name} ({bm.bm_id})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                ID BM Đích (Nhập hoặc Chọn) <span className="text-rose-400">*</span>
              </label>
              <input
                type="text"
                required
                value={bmId}
                onChange={(e) => setBmId(e.target.value)}
                placeholder="VD: 123456789012345"
                className="w-full bg-[#1A1A1E] border border-[#2A2A32] rounded-lg px-3 py-2 text-xs font-mono text-white outline-none focus:border-indigo-500"
              />
            </div>
          </div>

          {/* Customer Email Input */}
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">
              Email Khách Hàng Nhận Quyền (mỗi email 1 dòng) <span className="text-rose-400">*</span>
            </label>
            <textarea
              required
              rows={3}
              value={emails}
              onChange={(e) => setEmails(e.target.value)}
              placeholder="khachhang1@gmail.com&#10;khachhang2@agency.com"
              className="w-full bg-[#1A1A1E] border border-[#2A2A32] rounded-lg p-2.5 text-xs font-mono text-white placeholder-slate-500 outline-none focus:border-indigo-500 resize-none"
            />
            <div className="flex justify-between items-center text-[11px] text-slate-400 mt-0.5">
              <span>Đã nhận diện: {parsedEmails.length} email</span>
              <span>Facebook sẽ gửi link xác nhận BM tới từng email</span>
            </div>
          </div>

          {/* Facebook BM Role & Ad Account Tasks */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                Vai Trò Facebook BM
              </label>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="w-full bg-[#1A1A1E] border border-[#2A2A32] rounded-lg px-3 py-2 text-xs text-white outline-none focus:border-indigo-500"
              >
                <option value="EMPLOYEE">EMPLOYEE (Khuyên dùng - Nhân viên)</option>
                <option value="ADMIN" disabled={currentRole !== "OWNER"}>
                  ADMIN {currentRole !== "OWNER" ? "(Chỉ dành cho Owner)" : ""}
                </option>
                <option value="FINANCE_EDITOR">FINANCE_EDITOR (Biên tập tài chính)</option>
                <option value="FINANCE_ANALYST">FINANCE_ANALYST (Nhà phân tích tài chính)</option>
                <option value="DEVELOPER">DEVELOPER (Nhà phát triển)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                Quyền Hạn Tài Khoản QC (Tasks) <span className="text-rose-400">*</span>
              </label>
              <div className="flex items-center gap-3 pt-2">
                {[
                  { key: "MANAGE", label: "MANAGE (Toàn quyền)" },
                  { key: "ADVERTISE", label: "ADVERTISE (Chạy QC)" },
                  { key: "ANALYZE", label: "ANALYZE (Báo cáo)" },
                ].map((item) => (
                  <label key={item.key} className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={tasks.includes(item.key)}
                      onChange={() => toggleTask(item.key)}
                      className="rounded bg-[#1A1A1E] border-[#2A2A32] text-indigo-500 focus:ring-0 accent-indigo-500"
                    />
                    <span>{item.key}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>

          {/* 3-WAY AD ACCOUNT SELECTOR */}
          <div className="rounded-xl border border-[#2A2A32] bg-[#17171B] p-3.5 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
                Bộ Chọn Tài Khoản Quảng Cáo (3 Cách)
              </span>
              <span className="rounded-full border border-emerald-500/30 bg-emerald-500/15 px-2.5 py-0.5 font-mono text-[11px] font-semibold text-emerald-400">
                Đã nhận diện: {parsedAccountIds.length} TKQC
              </span>
            </div>

            {/* Way 1: Dropdown Chọn theo Khách hàng đã gán */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <div>
                <label className="block text-[11px] font-medium text-slate-400 mb-1">
                  1. Chọn theo Khách hàng đã gán ({customers.length} khách hàng):
                </label>
                <select
                  value={customerId}
                  onChange={(e) => handleSelectCustomer(e.target.value)}
                  className="w-full bg-[#1A1A1E] border border-[#2A2A32] rounded-lg px-3 py-1.5 text-xs text-white outline-none focus:border-indigo-500"
                >
                  <option value="">— Chọn khách hàng để tự điền TKQC —</option>
                  {customers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Way 2: Nạp các TKQC đang tích chọn trên bảng */}
              <div>
                <label className="block text-[11px] font-medium text-slate-400 mb-1">
                  2. Lấy từ dòng đang tích chọn trên bảng:
                </label>
                <button
                  type="button"
                  onClick={handleLoadSelectedRows}
                  className="w-full bg-[#202024] hover:bg-[#2A2A30] text-indigo-400 hover:text-indigo-300 border border-[#2A2A32] hover:border-indigo-500/40 rounded-lg px-3 py-1.5 text-xs font-semibold flex items-center justify-center gap-1.5 transition"
                >
                  <MonoIcon name="copy" width={13} />
                  Lấy các TKQC đang tích chọn trên bảng ({initialAccountIds.length})
                </button>
              </div>
            </div>

            {/* Way 3: Multi-line textarea Nhập / Dán ID TKQC bằng tay */}
            <div>
              <div className="flex justify-between items-center mb-1">
                <label className="text-[11px] font-medium text-slate-400">
                  3. Nhập / Dán ID TKQC bằng tay (mỗi ID 1 dòng):
                </label>
                {manualIds && (
                  <button
                    type="button"
                    onClick={() => setManualIds("")}
                    className="text-[10px] text-slate-500 hover:text-slate-300 underline"
                  >
                    Xóa trắng
                  </button>
                )}
              </div>
              <textarea
                rows={4}
                value={manualIds}
                onChange={(e) => setManualIds(e.target.value)}
                placeholder="act_123456789012345&#10;987654321098765"
                className="w-full bg-[#1A1A1E] border border-[#2A2A32] rounded-lg p-2.5 text-xs font-mono text-white placeholder-slate-500 outline-none focus:border-indigo-500 resize-none"
              />
              <p className="text-[10px] text-slate-500 mt-0.5">
                Hệ thống tự động loại bỏ tiền tố `act_`, chuẩn hóa số ID và loại trừ các dòng trùng lặp.
              </p>
            </div>
          </div>

          {/* Results display */}
          {result && (
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-emerald-400">
                  Mã lệnh: <span className="font-mono text-white">{result.command_id}</span>
                </span>
                <span className="text-[11px] text-slate-400">
                  {result.results.length} tài khoản đã ghi nhận
                </span>
              </div>
              <div className="max-h-32 overflow-y-auto space-y-1 text-xs font-mono">
                {result.results.map((item) => (
                  <div
                    key={item.account_id}
                    className="flex items-center justify-between bg-black/40 px-2.5 py-1 rounded border border-slate-800"
                  >
                    <span className="text-slate-300">act_{item.account_id}</span>
                    <span
                      className={
                        item.status === "FAILED"
                          ? "text-rose-400 font-semibold"
                          : "text-emerald-400 font-semibold"
                      }
                    >
                      {item.status}
                    </span>
                  </div>
                ))}
              </div>
              {result.invite_link && (
                <div className="pt-2 border-t border-emerald-500/20 space-y-1">
                  <label className="text-[11px] font-medium text-slate-300">
                    Liên kết quản lý lời mời:
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      readOnly
                      value={result.invite_link}
                      className="flex-1 bg-black/50 border border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono text-slate-200 select-all outline-none"
                    />
                    <button
                      type="button"
                      className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center gap-1 transition"
                      onClick={() => void navigator.clipboard.writeText(result.invite_link)}
                    >
                      <MonoIcon name="copy" width={14} />
                      Sao chép liên kết
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Modal Footer */}
          <div className="flex items-center justify-end gap-3 pt-3 border-t border-[#2A2A32]">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-[#2A2A32] bg-[#1A1A1E] px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-[#202024] hover:text-white transition"
            >
              Đóng
            </button>
            <button
              type="submit"
              disabled={busy || parsedAccountIds.length === 0 || tasks.length === 0 || parsedEmails.length === 0}
              className="rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2 text-xs font-bold uppercase tracking-wider disabled:opacity-50 transition shadow-lg flex items-center gap-1.5"
            >
              {busy ? "Đang xếp lệnh…" : "Thực thi Share & Gán TKQC"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
