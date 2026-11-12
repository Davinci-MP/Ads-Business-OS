"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { MonoIcon, type MonoIconName } from "../components/mono-icon";
export const navigation = [
  { href: "/dashboard", label: "Tổng quan", icon: "dashboard" },
  { href: "/accounts", label: "Tài khoản quảng cáo", icon: "account" },
  { href: "/bms", label: "Business Manager", icon: "business" },
  { href: "/vias", label: "Dàn VIA", icon: "via" },
  { href: "/customers", label: "Khách hàng", icon: "customer" },
  { href: "/analytics", label: "Phân tích & báo cáo", icon: "analytics" },
  { href: "/auto-set-camp", label: "Thiết lập chiến dịch", icon: "campaign" },
  { href: "/settings", label: "Cài đặt", icon: "settings" },
] satisfies Array<{ href: string; label: string; icon: MonoIconName }>;
export function Sidebar({ collapsed, mobileOpen, onCollapse, onClose, connected, brand }: { collapsed: boolean; mobileOpen: boolean; onCollapse: () => void; onClose: () => void; connected: boolean | null; brand: string }) {
  const pathname = usePathname();
  const aside = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!mobileOpen) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const targets = () => [...(aside.current?.querySelectorAll<HTMLElement>("a,button") || [])].filter(el => el.getClientRects().length);
    targets()[0]?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const items = targets();
      const first = items[0], last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("keydown", key); previous?.focus(); };
  }, [mobileOpen]);
  return <>
    {mobileOpen && <button className="sidebar-backdrop" aria-label="Đóng điều hướng" onClick={onClose} />}
    <aside ref={aside} role={mobileOpen ? "dialog" : undefined} aria-modal={mobileOpen || undefined} className={`admin-sidebar ${collapsed ? "collapsed" : ""} ${mobileOpen ? "mobile-open" : ""}`} aria-label="Điều hướng chính">
      <Link href="/dashboard" className="brand" onClick={onClose}><span className="brand-mark">a<span>.</span></span><span className="brand-name">{brand}<small>KHÔNG GIAN ĐIỀU HÀNH</small></span></Link>
      <div className="nav-section-label">KHÔNG GIAN LÀM VIỆC</div>
      <nav>{navigation.map(item => <Link key={item.href} href={item.href} onClick={onClose} title={collapsed ? item.label : undefined} aria-current={pathname.startsWith(item.href) || (pathname === "/" && item.href === "/dashboard") ? "page" : undefined} className="nav-item"><span className="nav-icon"><MonoIcon name={item.icon} /></span><span className="nav-copy">{item.label}</span><span className="nav-active-dot" /></Link>)}</nav>
      <div className="sidebar-bottom"><div className="sidebar-health"><span className={`status-dot ${connected === true ? "online" : ""}`} /><span>{connected === null ? "Đang kiểm tra máy chủ" : connected ? "Máy chủ đã kết nối" : "Chưa kết nối máy chủ"}<small>Proxy: theo cấu hình từng VIA</small></span></div><button className="collapse-button" onClick={onCollapse} aria-label={collapsed ? "Mở rộng điều hướng" : "Thu gọn điều hướng"}><span>{collapsed ? "»" : "«"}</span><span className="nav-copy">Thu gọn thanh bên</span></button></div>
    </aside>
  </>;
}
