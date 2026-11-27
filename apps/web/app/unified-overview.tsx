"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { getUnifiedOverview, UnifiedOverview } from "../lib/api";
import { getVccRiskOverview, VccRiskAlert } from "../lib/vcc-risk-api";

export default function UnifiedOverviewWidget() {
  const [data, setData] = useState<UnifiedOverview | null>(null);
  const [vccAlerts, setVccAlerts] = useState<VccRiskAlert[]>([]);
  const [loading, setLoading] = useState(true);

  const loadOverview = useCallback(async () => {
    try {
      setLoading(true);
      const [res, vccRes] = await Promise.allSettled([
        getUnifiedOverview(),
        getVccRiskOverview(),
      ]);
      if (res.status === "fulfilled") setData(res.value);
      if (vccRes.status === "fulfilled" && vccRes.value?.alerts) {
        setVccAlerts(vccRes.value.alerts);
      }
    } catch {
      // Keep silent fallback or show subtle indicator
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  if (loading && !data) {
    return (
      <div className="bg-[#181818] p-5 rounded-[8px] border border-[#282828] shadow-[0_8px_8px_rgba(0,0,0,0.3)] animate-pulse mb-6">
        <div className="h-4 bg-[#282828] rounded w-48 mb-3" />
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="h-16 bg-[#1f1f1f] rounded-[8px]" />
          ))}
        </div>
      </div>
    );
  }

  if (!data) return null;

  const { connectors, stats } = data;

  return (
    <div className="w-full bg-[#181818] p-5 rounded-[8px] border border-[#282828] shadow-[0_8px_8px_rgba(0,0,0,0.3)] mb-6 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#282828] pb-3">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#0070f3] animate-pulse" />
          <h2 className="text-sm font-bold text-white tracking-tight m-0 uppercase">
            Hệ Thống Kết Nối Đa Nền Tảng (Unified Platform Hub)
          </h2>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-[#b3b3b3]">Chế độ:</span>
          <span className="px-3 py-0.5 rounded-full font-bold uppercase tracking-[1.4px] bg-[#0070f3]/15 text-[#0070f3] border border-[#0070f3]/30 text-[10px]">
            {data.platform_mode.toUpperCase()}
          </span>
          {stats.pending_client_tasks > 0 && (
            <Link
              href="/tasks"
              className="px-3 py-1 rounded-full font-bold uppercase tracking-[1.4px] bg-[#ffa42b]/20 text-[#ffa42b] border border-[#ffa42b]/30 animate-pulse hover:bg-[#ffa42b]/30 transition text-[10px]"
            >
               {stats.pending_client_tasks} Tác vụ chờ
            </Link>
          )}
        </div>
      </div>

      {/* Grid Connectors */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {/* 1. Meta Ads */}
        <div className="bg-[#1f1f1f] p-3.5 rounded-[8px] border border-[#282828] hover:border-[#333333] transition flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider">Meta Ads</span>
              <span className="w-2 h-2 rounded-full bg-[#0070f3]" />
            </div>
            <div className="text-xs font-mono font-bold text-[#0070f3] mt-1">
              v{connectors.meta_ads.version}
            </div>
          </div>
          <span className="text-[10px] text-[#b3b3b3] mt-2">
            Chế độ: <b className="text-white">{connectors.meta_ads.mode}</b>
          </span>
        </div>

        {/* 2. Binance */}
        <div className="bg-[#1f1f1f] p-3.5 rounded-[8px] border border-[#282828] hover:border-[#333333] transition flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider">Binance</span>
              <span
                className={`w-2 h-2 rounded-full ${
                  connectors.binance.connected ? "bg-[#0070f3]" : "bg-[#727272]"
                }`}
              />
            </div>
            <div className="text-xs font-mono font-bold text-[#ffa42b] mt-1 truncate">
              {connectors.binance.connected ? connectors.binance.label || "Chỉ đọc" : "Chưa kết nối"}
            </div>
          </div>
          <span className="text-[10px] text-[#b3b3b3] mt-2">
            {connectors.binance.read_only_verified ? " Read-Only Verified" : "Spot / Funding"}
          </span>
        </div>

        {/* 3. PingPong VCC */}
        <div className="bg-[#1f1f1f] p-3.5 rounded-[8px] border border-[#282828] hover:border-[#333333] transition flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider">PingPong VCC</span>
              <span
                className={`w-2 h-2 rounded-full ${
                  connectors.pingpong.connected ? "bg-[#0070f3]" : "bg-[#727272]"
                }`}
              />
            </div>
            <div className="text-xs font-mono font-bold text-[#0070f3] mt-1 truncate">
              {connectors.pingpong.connected ? connectors.pingpong.label || "Đang kết nối" : "Chưa cấu hình"}
            </div>
          </div>
          <span className="text-[10px] text-[#b3b3b3] mt-2">
            {connectors.pingpong.read_only_verified ? " Read-Only OpenAPI" : "Thẻ ảo trả trước"}
          </span>
        </div>

        {/* 4. TRON Blockchain */}
        <div className="bg-[#1f1f1f] p-3.5 rounded-[8px] border border-[#282828] hover:border-[#333333] transition flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider">TRON TRC20</span>
              <span
                className={`w-2 h-2 rounded-full ${
                  connectors.tron.configured ? "bg-[#0070f3]" : "bg-[#727272]"
                }`}
              />
            </div>
            <div className="text-xs font-mono font-bold text-[#539df5] mt-1 truncate">
              {connectors.tron.configured ? connectors.tron.address : "Chưa nhập ví"}
            </div>
          </div>
          <span className="text-[10px] text-[#b3b3b3] mt-2">Ví lạnh USDT</span>
        </div>

        {/* 5. Google Sheets */}
        <div className="bg-[#1f1f1f] p-3.5 rounded-[8px] border border-[#282828] hover:border-[#333333] transition flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider">Google Sheets</span>
              <span className="w-2 h-2 rounded-full bg-[#0070f3]" />
            </div>
            <div className="text-xs font-mono font-bold text-white mt-1">
              {connectors.sheets.active_sources} Nguồn báo cáo
            </div>
          </div>
          <span className="text-[10px] text-[#b3b3b3] mt-2">Đồng bộ tự động</span>
        </div>

        {/* 6. Telegram AI Bot */}
        <div className="bg-[#1f1f1f] p-3.5 rounded-[8px] border border-[#282828] hover:border-[#333333] transition flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider">Telegram AI</span>
              <span
                className={`w-2 h-2 rounded-full ${
                  connectors.telegram.configured ? "bg-[#0070f3]" : "bg-[#727272]"
                }`}
              />
            </div>
            <div className="text-xs font-mono font-bold text-[#ffa42b] mt-1">
              {connectors.telegram.active_rules} Quy tắc chạy
            </div>
          </div>
          <span className="text-[10px] text-[#b3b3b3] mt-2">Smart Dispatcher</span>
        </div>
      </div>

      {/* Dải Cảnh Báo Thẻ VCC & Nợ Meta nếu có nguy hiểm */}
      {vccAlerts.length > 0 && (
        <div className="p-3.5 rounded-[8px] bg-[#f3727f]/10 border border-[#f3727f]/30 text-[#f3727f] text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-2 shadow-[0_8px_8px_rgba(0,0,0,0.3)]">
          <div className="flex items-center gap-2">
            <span className="text-base animate-pulse"></span>
            <span className="font-bold">
              Cảnh báo VCC & Nợ Meta: {vccAlerts[0].message}
              {vccAlerts.length > 1 && ` (+${vccAlerts.length - 1} cảnh báo khác)`}
            </span>
          </div>
          <Link
            href="/vcc-risk"
            className="px-3.5 py-1.5 rounded-full bg-[#f3727f] hover:bg-[#ff8591] text-black font-bold uppercase tracking-[1.4px] text-[10px] transition text-center whitespace-nowrap shadow-sm"
          >
            Quản trị VCC & Rủi ro →
          </Link>
        </div>
      )}
    </div>
  );
}
