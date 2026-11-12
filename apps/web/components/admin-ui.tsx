"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { MonoIcon } from "./mono-icon";

type ToastKind = "success" | "error" | "warning" | "info";
type Notice = { id: number; message: string; kind: ToastKind };
const ToastContext = createContext<(message: string, kind?: ToastKind) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [notices, setNotices] = useState<Notice[]>([]);
  const nextId = useRef(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  useEffect(() => () => timers.current.forEach(clearTimeout), []);
  const notify = useCallback((message: string, kind: ToastKind = "success") => {
    const id = ++nextId.current;
    setNotices(items => [...items.slice(-3), { id, message, kind }]);
    timers.current.push(setTimeout(() => setNotices(items => items.filter(item => item.id !== id)), 4000));
  }, []);
  return <ToastContext.Provider value={notify}>{children}<div className="toast-stack" aria-live="polite" aria-atomic="false">
    {notices.map(item => <div key={item.id} className={`toast toast-${item.kind}`} role={item.kind === "error" ? "alert" : "status"}>
      <span>{item.kind === "success" ? "" : item.kind === "error" ? "!" : "i"}</span><p>{item.message}</p>
      <button aria-label="Đóng thông báo" onClick={() => setNotices(items => items.filter(n => n.id !== item.id))}><MonoIcon name="close" width={15} height={15} /></button>
    </div>)}
  </div></ToastContext.Provider>;
}
export const useToast = () => useContext(ToastContext);

export function PageHeading({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description: string; actions?: ReactNode }) {
  return <div className="page-heading"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h1>{title}</h1><p>{description}</p></div><div className="page-actions">{actions}</div></div>;
}
export function Metric({ label, value, note, tone = "indigo", badge }: { label: string; value: ReactNode; note: string; tone?: string; icon?: string; badge?: string }) {
  return <article className="metric-card"><div className="metric-label">{label}<span className={`metric-icon ${tone}`}><MonoIcon name="analytics" width={17} height={17} /></span></div><div className="metric-value">{value}</div>{badge && <span className="pill" style={{marginTop:8}}>{badge}</span>}<p>{note}</p></article>;
}
export function Empty({ title = "Chưa có dữ liệu", description = "Dữ liệu sẽ hiển thị sau khi nguồn được kết nối và đồng bộ.", action }: { title?: string; description?: string; action?: ReactNode }) {
  return <div className="empty-state"><span><MonoIcon name="account" width={26} height={26} /></span><h3>{title}</h3><p>{description}</p>{action}</div>;
}
export function ErrorNotice({ message, retry }: { message: string | null; retry?: () => void }) {
  return message ? <div className="error-box" role="alert">{message}{retry && <button className="btn" onClick={retry}>Thử lại</button>}</div> : null;
}
export function Pagination({ total, page, size, onPage, onSize }: { total: number; page: number; size: number; onPage: (n: number) => void; onSize: (n: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / size));
  return <div className="pagination"><span>{total ? (page - 1) * size + 1 : 0}–{Math.min(page * size, total)} trong {total} bản ghi</span><label>Số dòng <select aria-label="Số dòng mỗi trang" value={size} onChange={e => onSize(Number(e.target.value))}>{[10, 20, 50].map(n => <option key={n}>{n}</option>)}</select></label><div><button className="btn icon-btn" aria-label="Trang trước" disabled={page <= 1} onClick={() => onPage(page - 1)}><MonoIcon name="chevron-left" /></button><span>{page} / {pages}</span><button className="btn icon-btn" aria-label="Trang sau" disabled={page >= pages} onClick={() => onPage(page + 1)}><MonoIcon name="chevron-right" /></button></div></div>;
}
export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    const cancel = (e: Event) => { e.preventDefault(); close.current(); };
    dialog?.addEventListener("cancel", cancel);
    return () => { dialog?.removeEventListener("cancel", cancel); dialog?.close(); };
  }, []);
  return <dialog ref={ref} className="admin-modal" aria-labelledby="modal-title" onClick={e => { if (e.target === ref.current) onClose(); }}><div className="modal-heading"><h2 id="modal-title">{title}</h2><button className="btn icon-btn" type="button" aria-label="Đóng hộp thoại" onClick={onClose}><MonoIcon name="close" /></button></div>{children}</dialog>;
}
