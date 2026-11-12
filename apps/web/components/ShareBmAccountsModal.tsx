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
    try { return JSON.parse(localStorage.getItem("adsos_auth_user") || "{}").role || ""; }
    catch { return ""; }
  }, [open]);

  const selectedIds = useMemo(() => {
    const ids = new Set(initialAccountIds.map((id) => id.replace("act_", "")));
    if (customerId) {
      accounts.filter((account) => String(account.customer_id) === customerId).forEach((account) => ids.add(account.act_id));
    }
    for (const line of manualIds.split(/\r?\n/)) {
      const match = line.match(/\d{5,25}/);
      if (match) ids.add(match[0]);
    }
    return [...ids];
  }, [accounts, customerId, initialAccountIds, manualIds]);

  useEffect(() => {
    if (!open) return;
    setResult(null);
    setFeedback(null);
    if (!bmId && bms.length) setBmId(bms[0].bm_id);
  }, [bms, bmId, open]);

  if (!open) return null;

  const toggleTask = (task: string) => setTasks((current) => current.includes(task) ? current.filter((item) => item !== task) : [...current, task]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      setBusy(true);
      setFeedback(null);
      const response = await shareBmAccounts({
        bm_id: bmId.trim(),
        customer_emails: emails.split(/\r?\n|,/).map((email) => email.trim()).filter(Boolean),
        bm_role: role,
        ad_account_tasks: tasks,
        account_ids: selectedIds,
        customer_id: customerId ? Number(customerId) : undefined,
      });
      setResult(response);
      setFeedback({ text: response.message });
    } catch (error) {
      setFeedback({ text: error instanceof Error ? error.message : "Không thể xếp lệnh chia sẻ BM.", error: true });
    } finally {
      setBusy(false);
    }
  };

  return <div className="fixed inset-0 z-50 grid place-items-center bg-black/75 p-4">
    <form className="admin-modal" onSubmit={submit}>
      <div className="modal-heading"><div><h2>Chia sẻ quyền BM và gán TKQC</h2><p className="muted">Lệnh được lưu vào hàng đợi và Extension thực thi bằng phiên VIA hợp lệ.</p></div><button type="button" className="btn icon-btn" onClick={onClose} aria-label="Đóng"><MonoIcon name="close" width={18} /></button></div>
      {feedback && <div className={feedback.error ? "error-box" : "notice"} role="status">{feedback.text}</div>}
      <div className="admin-form">
        <label>ID BM đích<input list="share-bm-options" required value={bmId} onChange={(event) => setBmId(event.target.value)} placeholder="Nhập hoặc chọn BM ID" /></label>
        <datalist id="share-bm-options">{bms.map((bm) => <option key={bm.bm_id} value={bm.bm_id}>{bm.name}</option>)}</datalist>
        <label>Email khách hàng, mỗi dòng một email<textarea required rows={3} value={emails} onChange={(event) => setEmails(event.target.value)} placeholder="khach@example.com" /></label>
        <div className="form-grid"><label>Vai trò BM<select value={role} onChange={(event) => setRole(event.target.value)}><option value="EMPLOYEE">EMPLOYEE</option><option value="ADMIN" disabled={currentRole !== "OWNER"}>ADMIN</option><option value="FINANCE_EDITOR">FINANCE_EDITOR</option><option value="FINANCE_ANALYST">FINANCE_ANALYST</option><option value="DEVELOPER">DEVELOPER</option></select></label><label>Chọn theo khách hàng đã gán<select value={customerId} onChange={(event) => setCustomerId(event.target.value)}><option value="">Không chọn</option>{customers.map((customer) => <option key={customer.id} value={customer.id}>{customer.name}</option>)}</select></label></div>
        <fieldset className="panel-body"><legend>Quyền TKQC</legend><div className="page-actions">{["MANAGE", "ADVERTISE", "ANALYZE"].map((task) => <label key={task} className="flex items-center gap-2"><input type="checkbox" checked={tasks.includes(task)} onChange={() => toggleTask(task)} />{task}</label>)}</div></fieldset>
        <label>Nhập ID TKQC bằng tay, mỗi ID một dòng<textarea rows={4} value={manualIds} onChange={(event) => setManualIds(event.target.value)} placeholder="act_123456789\n987654321" /><small>Đã hợp nhất và loại trùng: {selectedIds.length} TKQC.</small></label>
        {result && <div className="notice"><strong>Mã lệnh: {result.command_id}</strong><p>{result.results.map((item) => `${item.account_id}: ${item.status}`).join(" · ")}</p><div className="page-actions"><input readOnly value={result.invite_link} aria-label="Liên kết quản lý lời mời" /><button type="button" className="btn" onClick={() => void navigator.clipboard.writeText(result.invite_link)}><MonoIcon name="copy" width={14} />Sao chép liên kết</button></div></div>}
        <div className="form-footer"><button type="button" className="btn" onClick={onClose}>Đóng</button><button className="btn primary" disabled={busy || selectedIds.length === 0 || tasks.length === 0}>{busy ? "Đang xếp lệnh…" : "Thực thi Share & Gán TKQC"}</button></div>
      </div>
    </form>
  </div>;
}
