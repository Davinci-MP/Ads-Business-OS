import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Ads Business OS",
  description: "Dashboard quản lý hoạt động kinh doanh tài khoản quảng cáo",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body>
        <nav className="nav">
          <span className="brand">Ads Business OS</span>
          <a href="/">Tổng quan</a>
          <a href="/#khach-hang">Khách hàng</a>
          <a href="/campaigns">Campaign</a>
          <a href="/accounts">Tài khoản</a>
          <a href="/reports">Kinh doanh</a>
          <a href="/reviews">Đối chiếu</a>
          <a href="/sheets">Google Sheets</a>
          <a href="/config">Cấu hình</a>
          <a href="/system">Giám sát hệ thống</a>
        </nav>
        {children}
      </body>
    </html>
  );
}
