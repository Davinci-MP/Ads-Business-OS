"use client";

import { useCallback, useEffect, useState } from "react";
import { MonoIcon } from "@/components/mono-icon";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const ROLES = ["OWNER", "STAFF_OPS", "STAFF_SUPPORT", "ACCOUNTANT"] as const;
type StaffRole = (typeof ROLES)[number];

type Staff = {
  id: number;
  username: string;
  full_name: string | null;
  email: string | null;
  role: StaffRole;
  assigned_customer_ids: number[];
  is_active: boolean;
  last_login_at: string | null;
  created_at: string | null;
};

type Customer = { id: number; name: string };
type AuditLog = {
  id: number;
  username: string | null;
  role: string | null;
  action_type: string;
  target_bm_id: string | null;
  target_account_ids: string[] | null;
  recipient_info: string | null;
  status: string;
  detail: string | null;
  created_at: string | null;
};

type StaffDraft = {
  username: string;
  full_name: string;
  email: string;
  password: string;
  role: StaffRole;
  assigned_customer_ids: number[];
};

const EMPTY_DRAFT: StaffDraft = {
  username: "",
  full_name: "",
  email: "",
  password: "",
  role: "STAFF_SUPPORT",
  assigned_customer_ids: [],
};

async function staffRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem("adsos_auth_token");
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE}/api/v1${path}`, { ...options, headers, cache: "no-store" });
  const body = await response.json().catch(() => ({})) as { detail?: string };
  if (!response.ok) throw new Error(body.detail || `Yêu cầu thất bại (HTTP ${response.status}).`);
  return body as T;
}

function toDraft(staff?: Staff): StaffDraft {
  if (!staff) return { ...EMPTY_DRAFT };
  return {
    username: staff.username,
    full_name: staff.full_name || "",
    email: staff.email || "",
    password: "",
    role: staff.role,
    assigned_customer_ids: staff.assigned_customer_ids || [],
  };
}

export default function StaffPage() {
  const [staff, setStaff] = useState<Staff[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [editing, setEditing] = useState<Staff | "new" | null>(null);
  const [draft, setDraft] = useState<StaffDraft>({ ...EMPTY_DRAFT });
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ text: string; error?: boolean } | null>(null);

  const load = useCallback(async () => {
    try {
      setBusy(true);
      const [staffRows, customerRows, auditRows] = await Promise.all([
        staffRequest<Staff[]>("/staff"),
        staffRequest<Customer[]>("/customers"),
        staffRequest<AuditLog[]>("/staff/audit-logs"),
      ]);
      setStaff(staffRows);
      setCustomers(customerRows);
      setLogs(auditRows);
    } catch (error) {
      setFeedback({ text: error instanceof Error ? error.message : "Không tải được dữ liệu nhân sự.", error: true });
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const openEditor = (value: Staff | "new") => {
    setEditing(value);
    setDraft(toDraft(value === "new" ? undefined : value));
    setFeedback(null);
  };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      setBusy(true);
      if (editing === "new") {
        await staffRequest<Staff>("/staff", { method: "POST", body: JSON.stringify(draft) });
        setFeedback({ text: "Đã tạo nhân viên và lưu phân quyền." });
      } else if (editing) {
        const payload = { ...draft, username: undefined, password: draft.password || undefined };
        await staffRequest<Staff>(`/staff/${editing.id}`, { method: "PATCH", body: JSON.stringify(payload) });
        setFeedback({ text: "Đã lưu vai trò, khách hàng phụ trách và thông tin nhân viên." });
      }
      setEditing(null);
      await load();
    } catch (error) {
      setFeedback({ text: error instanceof Error ? error.message : "Không lưu được nhân viên.", error: true });
    } finally {
      setBusy(false);
    }
  };

  const toggleActive = async (row: Staff) => {
    try {
      setBusy(true);
      await staffRequest(`/staff/${row.id}`, { method: "PATCH", body: JSON.stringify({ is_active: !row.is_active }) });
      setFeedback({ text: row.is_active ? "Đã khóa nhân viên." : "Đã mở khóa nhân viên." });
      await load();
    } catch (error) {
      setFeedback({ text: error instanceof Error ? error.message : "Không đổi được trạng thái nhân viên.", error: true });
    } finally {
      setBusy(false);
    }
  };

  const remove = async (row: Staff) => {
    if (!window.confirm(`Xóa nhân viên ${row.username}? Tài khoản sẽ bị vô hiệu hóa và lịch sử vẫn được giữ.`)) return;
    try {
      setBusy(true);
      const result = await staffRequest<{ message: string }>(`/staff/${row.id}`, { method: "DELETE" });
      setFeedback({ text: result.message });
      await load();
    } catch (error) {
      setFeedback({ text: error instanceof Error ? error.message : "Không xóa được nhân viên.", error: true });
    } finally {
      setBusy(false);
    }
  };

  const toggleCustomer = (customerId: number) => {
    setDraft((current) => ({
      ...current,
      assigned_customer_ids: current.assigned_customer_ids.includes(customerId)
        ? current.assigned_customer_ids.filter((id) => id !== customerId)
        : [...current.assigned_customer_ids, customerId],
    }));
  };

  return (
    <div className="space-y-6">
      <div className="page-heading">
        <div><span className="eyebrow">Cài đặt hệ thống</span><h1>Nhân viên và phân quyền</h1><p>Quản lý vai trò, khách hàng phụ trách và nhật ký thao tác thực tế.</p></div>
        <button className="btn primary" onClick={() => openEditor("new")}><MonoIcon name="customer" width={16} />Tạo nhân viên mới</button>
      </div>

      {feedback && <div className={`notice ${feedback.error ? "error-box" : ""}`} role="status">{feedback.text}</div>}

      <section className="metric-grid">
        <article className="metric-card"><div className="metric-label">Tổng nhân sự</div><div className="metric-value">{staff.length}</div></article>
        <article className="metric-card"><div className="metric-label">Đang hoạt động</div><div className="metric-value">{staff.filter((row) => row.is_active).length}</div></article>
        <article className="metric-card"><div className="metric-label">Đã khóa</div><div className="metric-value">{staff.filter((row) => !row.is_active).length}</div></article>
        <article className="metric-card"><div className="metric-label">Khách hàng</div><div className="metric-value">{customers.length}</div></article>
      </section>

      <section className="panel">
        <div className="panel-heading"><div><h2>Danh sách nhân viên</h2><p>Mọi thay đổi được lưu trực tiếp vào cơ sở dữ liệu.</p></div><button className="btn" disabled={busy} onClick={() => void load()}><MonoIcon name="refresh" width={15} />Tải lại</button></div>
        <div className="table-scroll"><table><thead><tr><th>Nhân viên</th><th>Vai trò</th><th>Khách phụ trách</th><th>Trạng thái</th><th>Đăng nhập cuối</th><th>Thao tác</th></tr></thead><tbody>
          {staff.map((row) => <tr key={row.id}>
            <td><strong>{row.full_name || row.username}</strong><small className="table-muted">{row.username} · {row.email || "Chưa có email"}</small></td>
            <td><span className="pill">{row.role}</span></td>
            <td>{row.assigned_customer_ids.length} khách</td>
            <td><span className={`pill ${row.is_active ? "good" : "warn"}`}>{row.is_active ? "Hoạt động" : "Đã khóa"}</span></td>
            <td>{row.last_login_at ? new Date(row.last_login_at).toLocaleString("vi-VN") : "Chưa đăng nhập"}</td>
            <td><div className="page-actions"><button className="btn" onClick={() => openEditor(row)}><MonoIcon name="edit" width={14} />Sửa / Phân quyền</button><button className="btn" disabled={busy} onClick={() => void toggleActive(row)}>{row.is_active ? "Khóa" : "Mở khóa"}</button><button className="btn danger" disabled={busy} onClick={() => void remove(row)}><MonoIcon name="trash" width={14} />Xóa</button></div></td>
          </tr>)}
          {!staff.length && <tr><td colSpan={6}>{busy ? "Đang tải…" : "Chưa có nhân viên."}</td></tr>}
        </tbody></table></div>
      </section>

      <section className="panel">
        <div className="panel-heading"><div><h2>Nhật ký thao tác</h2><p>500 sự kiện mới nhất từ backend.</p></div></div>
        <div className="table-scroll"><table><thead><tr><th>Thời gian</th><th>Người thực hiện</th><th>Hành động</th><th>Đối tượng</th><th>Trạng thái</th><th>Chi tiết</th></tr></thead><tbody>
          {logs.map((log) => <tr key={log.id}><td>{log.created_at ? new Date(log.created_at).toLocaleString("vi-VN") : "—"}</td><td>{log.username || "Hệ thống"}<small className="table-muted">{log.role || "—"}</small></td><td>{log.action_type}</td><td>{log.target_bm_id || log.target_account_ids?.join(", ") || "—"}</td><td><span className={`pill ${log.status === "SUCCESS" ? "good" : "bad"}`}>{log.status}</span></td><td>{log.detail || log.recipient_info || "—"}</td></tr>)}
          {!logs.length && <tr><td colSpan={6}>Chưa có nhật ký.</td></tr>}
        </tbody></table></div>
      </section>

      {editing && <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4"><form className="admin-modal" onSubmit={save}>
        <div className="modal-heading"><div><h2>{editing === "new" ? "Tạo nhân viên" : `Phân quyền ${editing.username}`}</h2><p className="muted">Mật khẩu để trống khi chỉnh sửa nếu không muốn thay đổi.</p></div><button type="button" className="btn icon-btn" onClick={() => setEditing(null)} aria-label="Đóng"><MonoIcon name="close" width={18} /></button></div>
        <div className="admin-form">
          <div className="form-grid"><label>Tên đăng nhập<input required disabled={editing !== "new"} value={draft.username} onChange={(event) => setDraft({ ...draft, username: event.target.value })} /></label><label>Họ tên<input required value={draft.full_name} onChange={(event) => setDraft({ ...draft, full_name: event.target.value })} /></label></div>
          <div className="form-grid"><label>Email<input type="email" value={draft.email} onChange={(event) => setDraft({ ...draft, email: event.target.value })} /></label><label>{editing === "new" ? "Mật khẩu" : "Mật khẩu mới"}<input type="password" required={editing === "new"} minLength={8} value={draft.password} onChange={(event) => setDraft({ ...draft, password: event.target.value })} /></label></div>
          <label>Vai trò<select value={draft.role} onChange={(event) => setDraft({ ...draft, role: event.target.value as StaffRole })}>{ROLES.map((role) => <option key={role}>{role}</option>)}</select></label>
          <fieldset className="panel-body"><legend>Khách hàng phụ trách</legend><div className="grid grid-cols-1 gap-2 sm:grid-cols-2">{customers.map((customer) => <label key={customer.id} className="flex items-center gap-2"><input type="checkbox" checked={draft.assigned_customer_ids.includes(customer.id)} onChange={() => toggleCustomer(customer.id)} />{customer.name}</label>)}</div></fieldset>
          <div className="form-footer"><button type="button" className="btn" onClick={() => setEditing(null)}>Hủy</button><button className="btn primary" disabled={busy}>{busy ? "Đang lưu…" : editing === "new" ? "Tạo nhân viên" : "Lưu phân quyền"}</button></div>
        </div>
      </form></div>}
    </div>
  );
}
