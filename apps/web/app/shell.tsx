"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { API_BASE } from "../lib/api";
import { MonoIcon } from "../components/mono-icon";
import { Sidebar } from "./sidebar";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [dark, setDark] = useState(true);

  useEffect(() => {
    const savedTheme = localStorage.getItem("adsos.theme") || "dark";
    const isDark = savedTheme === "dark";
    setDark(isDark);
    document.documentElement.dataset.theme = savedTheme;
    document.documentElement.classList.toggle("dark", isDark);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_BASE}/health`, { signal: controller.signal })
      .then((response) => setConnected(response.ok))
      .catch(() => setConnected(false));
    return () => controller.abort();
  }, []);

  useEffect(() => setMobileOpen(false), [pathname]);

  useEffect(() => {
    if (pathname === "/login" || pathname.startsWith("/portal/")) return;
    const token = localStorage.getItem("adsos_auth_token");
    if (!token) {
      window.location.replace("/login");
      return;
    }
    fetch(`${API_BASE}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => {
        if (!response.ok) throw new Error("Phiên đăng nhập không hợp lệ");
        return response.json();
      })
      .then((user) => localStorage.setItem("adsos_auth_user", JSON.stringify(user)))
      .catch(() => {
        localStorage.removeItem("adsos_auth_token");
        localStorage.removeItem("adsos_auth_user");
        window.location.replace("/login");
      });
  }, [pathname]);

  const toggleTheme = () => {
    const nextDark = !dark;
    const theme = nextDark ? "dark" : "light";
    setDark(nextDark);
    localStorage.setItem("adsos.theme", theme);
    document.documentElement.dataset.theme = theme;
    document.documentElement.classList.toggle("dark", nextDark);
  };

  if (pathname === "/login" || pathname.startsWith("/portal/")) {
    return <>{children}</>;
  }

  return (
    <div className={`admin-shell ${collapsed ? "sidebar-is-collapsed" : ""}`}>
      <a className="skip-link" href="#noi-dung-chinh">Bỏ qua điều hướng</a>
      <Sidebar
        collapsed={collapsed}
        mobileOpen={mobileOpen}
        onCollapse={() => setCollapsed((value) => !value)}
        onClose={() => setMobileOpen(false)}
        connected={connected}
        brand="ADSOS"
      />
      <div className="admin-workspace">
        <header className="admin-header">
          <button className="btn icon-btn mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Mở điều hướng">
            <MonoIcon name="menu" width={18} height={18} />
          </button>
          <div className="header-breadcrumb"><span>ADSOS</span><span>/</span><strong>Không gian điều hành</strong></div>
          <label className="global-search">
            <MonoIcon name="search" width={18} height={18} />
            <input aria-label="Tìm kiếm toàn hệ thống" placeholder="Tìm kiếm nhanh..." />
            <kbd>F</kbd>
          </label>
          <div className="header-actions">
            <button className="btn icon-btn" onClick={toggleTheme} aria-label={dark ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối"}>
              <MonoIcon name={dark ? "sun" : "moon"} width={18} height={18} />
            </button>
          </div>
        </header>
        <main id="noi-dung-chinh" className="app-content">{children}</main>
        <footer className="admin-footer"><span>Ads Business OS</span><span>Vận hành tại múi giờ Asia/Ho_Chi_Minh</span></footer>
      </div>
    </div>
  );
}
