"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MonoIcon, type MonoIconName } from "./mono-icon";

export interface NavItem {
  href: string;
  label: string;
  icon: MonoIconName;
  badge?: string;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Tổng quan", icon: "dashboard" },
  { href: "/#khach-hang", label: "Khách hàng", icon: "customer" },
  { href: "/campaigns", label: "Campaign & Chi tiêu", icon: "campaign" },
  { href: "/accounts", label: "Tài khoản QC", icon: "account" },
  { href: "/vias", label: "Quản lý Dàn VIA & BM", icon: "via", badge: "100+ VIA" },
  { href: "/vias/maxcare", label: "MaxCare — Nuôi VIA", icon: "via", badge: "MaxCare" },
  { href: "/ads-check", label: "ADSOS CHECK", icon: "account", badge: "CHECK" },
  { href: "/vcc-risk", label: "VCC & Rủi Ro Thẻ", icon: "account", badge: "VCC" },
  { href: "/risk", label: "Rủi ro tài khoản", icon: "filter" },
  { href: "/balances", label: "Số dư & Sổ giao dịch", icon: "analytics" },
  { href: "/reports", label: "Kinh doanh", icon: "analytics" },
  { href: "/reviews", label: "Đối chiếu", icon: "check" },
  { href: "/sheets", label: "Google Sheets", icon: "account" },
  { href: "/telegram", label: "Telegram Bot & Quy tắc", icon: "bell", badge: "Mới" },
  { href: "/config", label: "Cấu hình ví & sàn", icon: "settings" },
  { href: "/system", label: "Giám sát hệ thống", icon: "settings" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      style={{
        width: 240,
        background: "#0c0d14",
        borderRight: "1px solid rgba(255, 255, 255, 0.08)",
        color: "#f4f0e8",
        padding: "20px 12px",
        display: "flex",
        flexDirection: "column",
        gap: 6,
        flexShrink: 0,
        minHeight: "100vh",
      }}
    >
      <div style={{ padding: "0 10px 16px", borderBottom: "1px solid rgba(255, 255, 255, 0.08)", marginBottom: 8 }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: "#fff", display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 20 }}></span> Ads Business OS
        </div>
        <div style={{ fontSize: 11, color: "rgba(244, 240, 232, 0.45)", marginTop: 2 }}>Bảng quản trị tự động hóa</div>
      </div>

      <nav style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        {NAV_ITEMS.map((item) => {
          const activePaths = NAV_ITEMS.filter((o) => o.href === item.href || pathname.startsWith(o.href)).map((o) => o.href);
          const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href) && item.href === activePaths.reduce((a, b) => (b.length > a.length ? b : a)));
          const isTelegram = item.href === "/telegram";

          return (
            <Link
              key={item.href}
              href={item.href}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "9px 12px",
                borderRadius: 7,
                fontSize: 13,
                textDecoration: "none",
                fontWeight: isActive ? 600 : 400,
                color: isActive ? "#fff" : isTelegram ? "#b7a4ff" : "rgba(244, 240, 232, 0.72)",
                background: isActive
                  ? isTelegram
                    ? "rgba(183, 164, 255, 0.16)"
                    : "#1a1b25"
                  : "transparent",
                border: isActive
                  ? isTelegram
                    ? "1px solid rgba(183, 164, 255, 0.3)"
                    : "1px solid rgba(255, 255, 255, 0.06)"
                  : "1px solid transparent",
                transition: "all 0.15s ease",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                <MonoIcon name={item.icon} width={16} height={16} />
                <span>{item.label}</span>
              </div>
              {item.badge && (
                <span
                  style={{
                    background: "rgba(183, 164, 255, 0.2)",
                    color: "#b7a4ff",
                    fontSize: 10,
                    fontWeight: 700,
                    padding: "1px 6px",
                    borderRadius: 999,
                    border: "1px solid rgba(183, 164, 255, 0.4)",
                  }}
                >
                  {item.badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div style={{ marginTop: "auto", padding: "14px 10px 0", borderTop: "1px solid rgba(255, 255, 255, 0.08)" }}>
        <div style={{ fontSize: 11, color: "rgba(244, 240, 232, 0.4)" }}>Phiên bản: 2.4.0 (Tự động hóa)</div>
        <div style={{ fontSize: 11, color: "rgba(244, 240, 232, 0.4)", marginTop: 2 }}>Múi giờ: Asia/Ho_Chi_Minh</div>
      </div>
    </aside>
  );
}
