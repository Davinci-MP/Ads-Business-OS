"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { fetchJson } from "../lib/api";
import { formatUsdt } from "../lib/exchange-api";

export type TreasurySummaryData = {
  summary: {
    total_liquid_usdt: string;
    total_pingpong_usd: string;
    grand_total_working_capital: string;
    total_active_vcc_cards: number;
    total_vcc_available_balance: string;
    total_vcc_spending_limit: string;
  };
  breakdown: {
    tron: {
      total_usdt: string;
      wallets_count: number;
      items: Array<{
        id: number;
        name: string;
        address: string;
        balance: string;
        read_at: string | null;
        last_error: string | null;
      }>;
    };
    binance: {
      total_usdt: string;
      spot_usdt: string;
      funding_usdt: string;
      accounts_count: number;
      items: Array<{
        id: number;
        label: string;
        spot_free: string;
        funding_free: string;
        total_usdt: string;
        read_at: string | null;
        last_error: string | null;
      }>;
    };
    pingpong: {
      total_usd: string;
      currencies: Record<string, { available: string; pending: string; total: string }>;
      active_cards_count: number;
      cards_available_balance: string;
      cards_spending_limit: string;
      accounts_count: number;
      items: Array<{
        id: number;
        label: string;
        balances: Record<string, { available: string; pending: string; total: string }>;
        active_cards_count: number;
        cards_available_balance: string;
        cards_spending_limit: string;
        last_ok_at: string | null;
        last_error: string | null;
      }>;
    };
  };
};

export default function TreasurySummary() {
  const [data, setData] = useState<TreasurySummaryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchJson<TreasurySummaryData>("/treasury/summary");
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !data) {
    return (
      <section className="bg-[#181818] border border-[#282828] rounded-[8px] p-5 shadow-[0_8px_8px_rgba(0,0,0,0.3)] mb-6 animate-pulse">
        <div className="h-4 bg-[#282828] rounded w-64 mb-4" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-24 bg-[#1f1f1f] rounded-[8px]" />
          ))}
        </div>
      </section>
    );
  }

  if (error && !data) {
    return (
      <section className="bg-[#181818] border border-[#f3727f]/30 rounded-[8px] p-5 shadow-[0_8px_8px_rgba(0,0,0,0.3)] mb-6">
        <div className="flex items-center justify-between">
          <span className="text-[#f3727f] text-sm">Lỗi tải dữ liệu ngân quỹ: {error}</span>
          <button
            type="button"
            onClick={load}
            className="px-4 py-1.5 rounded-full bg-[#1f1f1f] text-white hover:bg-[#282828] text-xs font-bold uppercase tracking-[1.4px]"
          >
            Thử lại
          </button>
        </div>
      </section>
    );
  }

  if (!data) return null;

  const s = data.summary;
  const b = data.breakdown;

  return (
    <section className="w-full bg-[#181818] border border-[#282828] rounded-[8px] p-6 shadow-[0_8px_8px_rgba(0,0,0,0.3)] mb-6 space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#282828] pb-4">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2 m-0 uppercase tracking-tight">
            <span></span> Tổng quan Nguồn vốn & Thẻ (Treasury Summary)
          </h2>
          <p className="text-xs text-[#b3b3b3] mt-1">
            Tổng hợp vốn thanh khoản từ Ví TRON on-chain, Sàn Binance và Cổng PingPong VCC.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={load}
            className="px-4 py-2 rounded-full bg-[#1f1f1f] hover:bg-[#282828] text-[#b3b3b3] hover:text-white border border-[#333333] text-xs font-bold uppercase tracking-[1.4px] transition"
          >
            Làm mới
          </button>
          <Link
            href="/config/wallets"
            className="px-4 py-2 rounded-full bg-[#1ed760] hover:bg-[#1fdf64] text-black text-xs font-bold uppercase tracking-[1.4px] shadow-md transition"
          >
            Quản lý ví & sàn →
          </Link>
        </div>
      </div>

      {/* KPI CARDS */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
        {/* Tổng vốn khả dụng */}
        <div className="bg-[#1f1f1f] border border-[#1ed760]/40 border-l-4 border-l-[#1ed760] rounded-[8px] p-4 shadow-[0_8px_8px_rgba(0,0,0,0.3)]">
          <div className="text-[11px] font-bold text-[#1ed760] uppercase tracking-[1.4px]">
            TỔNG VỐN KHẢ DỤNG
          </div>
          <div className="text-2xl font-black font-mono text-white mt-1.5">
            {formatUsdt(s.grand_total_working_capital)} <span className="text-xs text-[#b3b3b3]">USD</span>
          </div>
          <div className="text-xs text-[#b3b3b3] mt-1 truncate">
            {formatUsdt(s.total_liquid_usdt)} USDT + {formatUsdt(s.total_pingpong_usd)} USD
          </div>
        </div>

        {/* Ví TRON */}
        <div className="bg-[#1f1f1f] border border-[#282828] border-l-4 border-l-[#539df5] rounded-[8px] p-4 shadow-[0_8px_8px_rgba(0,0,0,0.3)]">
          <div className="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-[1.4px]">
            Ví TRON On-chain
          </div>
          <div className="text-2xl font-black font-mono text-white mt-1.5">
            {formatUsdt(b.tron.total_usdt)} <span className="text-xs text-[#b3b3b3]">USDT</span>
          </div>
          <div className="text-xs text-[#b3b3b3] mt-1">
            {b.tron.wallets_count} địa chỉ ví theo dõi
          </div>
        </div>

        {/* Binance */}
        <div className="bg-[#1f1f1f] border border-[#282828] border-l-4 border-l-[#ffa42b] rounded-[8px] p-4 shadow-[0_8px_8px_rgba(0,0,0,0.3)]">
          <div className="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-[1.4px]">
            Sàn Binance (USDT)
          </div>
          <div className="text-2xl font-black font-mono text-white mt-1.5">
            {formatUsdt(b.binance.total_usdt)} <span className="text-xs text-[#b3b3b3]">USDT</span>
          </div>
          <div className="text-xs text-[#b3b3b3] mt-1">
            Spot: {formatUsdt(b.binance.spot_usdt)} · Funding: {formatUsdt(b.binance.funding_usdt)}
          </div>
        </div>

        {/* PingPong Balances */}
        <div className="bg-[#1f1f1f] border border-[#282828] border-l-4 border-l-[#1ed760] rounded-[8px] p-4 shadow-[0_8px_8px_rgba(0,0,0,0.3)]">
          <div className="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-[1.4px]">
            PingPong Master (USD)
          </div>
          <div className="text-2xl font-black font-mono text-white mt-1.5">
            {formatUsdt(b.pingpong.total_usd)} <span className="text-xs text-[#b3b3b3]">USD</span>
          </div>
          <div className="text-xs text-[#b3b3b3] mt-1">
            {b.pingpong.accounts_count} tài khoản kết nối
          </div>
        </div>

        {/* Thẻ ảo PingPong VCC */}
        <div className="bg-[#1f1f1f] border border-[#282828] border-l-4 border-l-[#f3727f] rounded-[8px] p-4 shadow-[0_8px_8px_rgba(0,0,0,0.3)]">
          <div className="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-[1.4px]">
            Thẻ ảo VCC PingPong
          </div>
          <div className="text-2xl font-black font-mono text-white mt-1.5">
            {s.total_active_vcc_cards} <span className="text-xs text-[#b3b3b3]">thẻ live</span>
          </div>
          <div className="text-xs text-[#b3b3b3] mt-1">
            Dư: {formatUsdt(s.total_vcc_available_balance)} $ · Hạn: {formatUsdt(s.total_vcc_spending_limit)} $
          </div>
        </div>
      </div>
    </section>
  );
}
