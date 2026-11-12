import "./globals.css";
import "./admin.css";
import type { Metadata } from "next";
import { AppShell } from "./shell";

export const metadata: Metadata = {
  title: "Ads Business OS — Quản trị Kinh doanh Ads",
  description: "Dashboard điều hành hoạt động kinh doanh tài khoản quảng cáo Meta Ads, Ví USDT và Sàn đối tác",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" data-theme="dark" className="dark" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <script dangerouslySetInnerHTML={{ __html: `try{var t=localStorage.getItem('adsos.theme')||'dark';document.documentElement.dataset.theme=t;document.documentElement.classList.toggle('dark',t==='dark')}catch(e){}` }} />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
