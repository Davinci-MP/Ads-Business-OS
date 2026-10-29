"use client";

import { useEffect, useState } from "react";
import { fetchJson } from "../lib/api";

type WalletBalance = {
  mode: string;
  wallet_configured: boolean;
  wallet_address: string | null;
  balance: string | null;
  contract: string | null;
  read_at: string | null;
  note: string | null;
  disclaimers: string[];
};

function formatUsdt(raw: string | null): string {
  if (raw == null) return "—";
  const value = Number.parseFloat(raw);
  if (Number.isNaN(value)) return "—";
  return `${value.toLocaleString("vi-VN", { maximumFractionDigits: 6 })} USDT`;
}

export default function WalletBalanceCard() {
  const [data, setData] = useState<WalletBalance | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submit, setSubmit] = useState(0);

  useEffect(() => {
    if (!submit) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchJson<WalletBalance>("/usdt/wallet-balance", { signal: controller.signal })
      .then((payload) => setData(payload))
      .catch((e) => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [submit]);

  useEffect(() => { setSubmit((n) => n + 1); }, []);

  const readAt = data?.read_at && !Number.isNaN(Date.parse(data.read_at))
    ? new Date(data.read_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })
    : null;

  return (
    <section className="mt-4 border border-slate-200 rounded-2xl bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Ví USDT chung (TRC20)</h2>
          <p className="mt-1 text-xs text-slate-500">
            Số dư chỉ đọc trực tiếp TRON; tách khỏi báo cáo tháng/năm — không tự đối chiếu, không cộng L1 nhiều tháng.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setSubmit((n) => n + 1)}
          disabled={loading}
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-50"
        >
          {loading ? "Đang đọc…" : "Đọc số dư"}
        </button>
      </div>
      {error && (
        <p role="alert" className="mt-3 text-sm text-red-700 border border-red-200 bg-red-50 rounded-lg p-2">
          Không đọc được số dư ví: {error}{" "}
          <button type="button" className="underline" onClick={() => setSubmit((n) => n + 1)}>Thử lại</button>
        </p>
      )}
      {loading && <p className="mt-3 text-sm text-slate-500">Đang tải số dư ví…</p>}
      {data && !loading && (
        <div className="mt-3 space-y-1 text-sm text-slate-700">
          <p className="text-xs text-slate-500">
            {data.mode === "live" ? "TrongGrid chỉ đọc" : data.mode === "mock" ? "Mock — chưa cấu hình ví" : data.mode}
          </p>
          <p>
            Số dư tại thời điểm đọc: <strong className="text-base">{formatUsdt(data.balance)}</strong>
            {readAt && <span className="text-slate-500"> · lúc {readAt} (Asia/Ho_Chi_Minh)</span>}
          </p>
          {data.wallet_address && (
            <p className="break-all text-xs text-slate-500">Ví: {data.wallet_address}</p>
          )}
          {data.note && <p className="text-xs text-amber-700">{data.note}</p>}
          <ul className="list-disc pl-5 text-xs text-slate-500 space-y-0.5 pt-1">
            {(data.disclaimers ?? []).map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      )}
    </section>
  );
}
