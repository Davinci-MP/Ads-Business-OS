import "./globals.css";
import "./admin.css";
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { AppShell } from "./shell";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist", display: "swap" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap" });

export const metadata: Metadata = {
  title: "Ads Business OS — Quản trị Kinh doanh Ads",
  description: "Dashboard điều hành hoạt động kinh doanh tài khoản quảng cáo Meta Ads, Ví USDT và Sàn đối tác",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" data-theme="light" className={`${geist.variable} ${geistMono.variable}`} suppressHydrationWarning>
      <body suppressHydrationWarning>
        <script dangerouslySetInnerHTML={{ __html: `try{var t=localStorage.getItem('adsos.theme')||'light';document.documentElement.dataset.theme=t;document.documentElement.classList.toggle('dark',t==='dark')}catch(e){}` }} />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
