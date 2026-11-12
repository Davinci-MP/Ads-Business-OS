"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchJson } from "../../lib/api";

type Tab = {
  sheet_id: number;
  tab: string;
  profile_status: string | null;
  link_state: "LINKED" | "UNLINKED" | "LINK_REVIEW";
  linked_customers: { customer_id: number; customer_name: string | null }[];
  flags: string[];
  note: string | null;
  proposals: string[];
};

type SourceRow = {
  source_id: number;
  period: string;
  name: string;
  active: boolean;
  closed: boolean;
  closed_at: string | null;
  snapshot_id: number | null;
  snapshot_read_at: string | null;
  tabs: Tab[];
};

type LinkReviewData = {
  generated_at: string;
  note: string;
  sources: SourceRow[];
};

const STATE_BADGE: Record<Tab["link_state"], { label: string; cls: string }> = {
  LINKED: {
    label: "Đã liên kết",
    cls: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30",
  },
  UNLINKED: {
    label: "Chưa liên kết",
    cls: "bg-sky-500/10 text-sky-400 border border-sky-500/30",
  },
  LINK_REVIEW: {
    label: "Cần rà soát",
    cls: "bg-amber-500/10 text-amber-400 border border-amber-500/30",
  },
};

const FLAG_LABEL: Record<string, string> = {
  UNLINKED: "Chưa liên kết",
  TEST_PROFILE: "Hồ sơ dấu hiệu thử nghiệm",
  LINKED_OTHER_ELSEWHERE: "Liên kết khác ở kỳ khác",
  MULTI_LINKED: "Nhiều hồ sơ cùng tab",
};

export default function LinkReview() {
  const [data, setData] = useState<LinkReviewData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchJson<LinkReviewData>("sheets/sources/link-review")
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section
      id="link-review"
      className="rounded-2xl border border-slate-800/80 bg-[#111827]/95 p-5 shadow-xl backdrop-blur-md space-y-4 text-slate-100"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <span></span> Rà Soát Liên Kết Khách Đa Kỳ
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Danh sách CHỈ ĐỌC để kiểm tra tính toàn vẹn: phát hiện tab chưa liên kết, dấu hiệu hồ sơ thử nghiệm,
            hoặc tab trùng liên kết khách khác giữa các kỳ.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="rounded-xl border border-slate-700 bg-slate-800 px-3.5 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700 transition disabled:opacity-50"
        >
          {loading ? "Đang tải…" : "Làm mới danh sách"}
        </button>
      </div>

      {error && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-rose-800/60 bg-rose-950/40 p-4 text-sm text-rose-200" role="alert">
          <span>{error}</span>
          <button
            type="button"
            className="rounded-lg border border-rose-700 bg-rose-900/50 px-3 py-1 text-xs font-semibold hover:bg-rose-900"
            onClick={load}
          >
            Thử lại
          </button>
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-2 p-4 text-sm text-sky-400 bg-sky-950/20 border border-sky-800/40 rounded-xl">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-sky-400 border-t-transparent" />
          <span>Đang phân tích liên kết khách trên các kỳ...</span>
        </div>
      )}

      {data && !loading && (
        <div className="space-y-6">
          <div className="flex items-center justify-between text-xs text-slate-400 bg-slate-900/70 p-3 rounded-xl border border-slate-800">
            <span>
              Tạo lúc:{" "}
              <strong className="text-slate-200">
                {new Date(data.generated_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}
              </strong>
            </span>
            <span className="italic">{data.note}</span>
          </div>

          {data.sources.map((source) => (
            <div key={source.source_id} className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/50 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold text-slate-100">
                    {source.period} — {source.name}
                  </span>
                  {source.closed && (
                    <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
                      Đã chốt kỳ
                    </span>
                  )}
                  {source.snapshot_id == null && (
                    <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-400">
                      Chưa có bản lưu
                    </span>
                  )}
                </div>
                {source.snapshot_read_at && (
                  <span className="text-[11px] text-slate-500">
                    Snapshot #{source.snapshot_id} ·{" "}
                    {new Date(source.snapshot_read_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}
                  </span>
                )}
              </div>

              {source.snapshot_id == null ? (
                <p className="text-xs text-slate-500 italic p-3">Nguồn này chưa có snapshot; chưa có tab để rà soát.</p>
              ) : source.tabs.length === 0 ? (
                <p className="text-xs text-slate-500 italic p-3">Snapshot không có tab khách nào.</p>
              ) : (
                <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/80">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-900 text-slate-400 uppercase font-semibold">
                      <tr>
                        <th className="p-3">Tab nguồn</th>
                        <th className="p-3">Trạng thái</th>
                        <th className="p-3">Hồ sơ liên kết</th>
                        <th className="p-3">Đề xuất & Cảnh báo</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/80">
                      {source.tabs.map((tab) => {
                        const badge = STATE_BADGE[tab.link_state];
                        return (
                          <tr key={tab.sheet_id} className="hover:bg-slate-800/40 transition-colors">
                            <td className="p-3">
                              <div className="font-semibold text-slate-200">{tab.tab}</div>
                              <div className="text-[11px] text-slate-500 font-mono">
                                sheetId {tab.sheet_id} {tab.profile_status ? `· ${tab.profile_status}` : ""}
                              </div>
                            </td>
                            <td className="p-3">
                              <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-semibold ${badge.cls}`}>
                                {badge.label}
                              </span>
                            </td>
                            <td className="p-3 text-slate-300">
                              {tab.linked_customers.length === 0 ? (
                                <span className="text-slate-500 italic">—</span>
                              ) : (
                                tab.linked_customers
                                  .map((c) => c.customer_name ?? `Khách #${c.customer_id}`)
                                  .join(", ")
                              )}
                            </td>
                            <td className="p-3">
                              {tab.flags.length > 0 && (
                                <div className="flex flex-wrap gap-1 mb-1">
                                  {tab.flags.map((f) => (
                                    <span
                                      key={f}
                                      className="rounded bg-rose-500/10 border border-rose-500/30 px-1.5 py-0.5 text-[10px] font-medium text-rose-300"
                                    >
                                      {FLAG_LABEL[f] ?? f}
                                    </span>
                                  ))}
                                </div>
                              )}
                              {tab.proposals.length > 0 && (
                                <ul className="text-amber-400 space-y-0.5 text-[11px] list-disc list-inside">
                                  {tab.proposals.map((p, idx) => (
                                    <li key={idx}>{p}</li>
                                  ))}
                                </ul>
                              )}
                              {tab.flags.length === 0 && tab.proposals.length === 0 && (
                                <span className="text-slate-600">—</span>
                              )}
                              {tab.note && <div className="mt-1 text-[11px] text-slate-500 italic">{tab.note}</div>}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
