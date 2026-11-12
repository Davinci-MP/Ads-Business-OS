"use client";
import { useEffect, useState } from "react";
import { fetchJson } from "../lib/api";
import { reportWindow } from "../lib/admin-utils.mjs";
import type { DailyReport, Kpi } from "../types/admin";
export function useReportData(days: number) {
  const [data, setData] = useState<{ daily: DailyReport; kpi: Kpi } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    const range = reportWindow(days);
    const query = new URLSearchParams(range);
    setLoading(true); setError(null); setData(null);
    void Promise.all([fetchJson<DailyReport>(`/reports/daily?${query}`, { signal: controller.signal }), fetchJson<Kpi>(`/reports/kpi?${query}`, { signal: controller.signal })]).then(([daily, kpi]) => { if (!controller.signal.aborted) setData({ daily, kpi }); }).catch((error: unknown) => { if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Không thể đọc báo cáo."); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [days]);
  return { data, loading, error };
}
