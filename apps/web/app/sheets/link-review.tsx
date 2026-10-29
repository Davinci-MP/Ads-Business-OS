"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchJson } from "../../lib/api";

type Tab = {
  sheet_id: number; tab: string; profile_status: string | null;
  link_state: "LINKED" | "UNLINKED" | "LINK_REVIEW";
  linked_customers: { customer_id: number; customer_name: string | null }[];
  flags: string[];
  note: string | null;
  proposals: string[];
};
type SourceRow = {
  source_id: number; period: string; name: string; active: boolean;
  closed: boolean; closed_at: string | null;
  snapshot_id: number | null; snapshot_read_at: string | null; tabs: Tab[];
};
type LinkReview = { generated_at: string; note: string; sources: SourceRow[] };

const STATE_LABEL: Record<Tab["link_state"], string> = {
  LINKED: "Đã liên kết", UNLINKED: "Chưa liên kết", LINK_REVIEW: "Cần rà soát",
};
const FLAG_LABEL: Record<string, string> = {
  UNLINKED: "Chưa liên kết",
  TEST_PROFILE: "Hồ sơ dấu hiệu thử nghiệm",
  LINKED_OTHER_ELSEWHERE: "Liên kết khác ở kỳ khác",
  MULTI_LINKED: "Nhiều hồ sơ cùng tab",
};

export default function LinkReview() {
  const [data, setData] = useState<LinkReview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true); setError(null);
    fetchJson<LinkReview>("/sheets/sources/link-review")
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <section id="link-review" className="my-6 rounded-xl border border-slate-200 p-4">
      <h2>Rà soát liên kết khách</h2>
      <p className="muted">
        Danh sách CHỈ ĐỌC để ra soát trước khi xác nhận: tab chưa liên kết, hồ sơ có dấu hiệu thử nghiệm,
        cùng tab đã liên kết khách khác ở kỳ khác. Không tự đổi/xoá liên kết — hành động ghi chỉ qua
        “Thiết lập khách hàng từ Sheets”.
      </p>
      <button type="button" onClick={load} disabled={loading}>{loading ? "Đang tải…" : "Tải lại"}</button>
      {error && <p className="error-box">{error}</p>}
      {data && !loading && (
        <>
          <p className="muted">Tạo lúc {new Date(data.generated_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}. {data.note}</p>
          {data.sources.map((source) => (
            <div key={source.source_id} className="my-4">
              <h3 className="section-title">
                {source.period} — {source.name}{source.closed ? " · Đã chốt kỳ" : ""}{source.snapshot_id == null ? " · Chưa có bản lưu" : ""}
              </h3>
              {source.snapshot_id == null ? (
                <p className="muted">Nguồn chưa có snapshot; chưa có tab để rà soát.</p>
              ) : source.tabs.length === 0 ? (
                <p className="muted">Snapshot không có tab khách.</p>
              ) : (
                <div style={{ overflowX: "auto" }}><table>
                  <thead><tr><th>Tab nguồn</th><th>Trạng thái liên kết</th><th>Hồ sơ liên kết</th><th>Đề xuất cần xác nhận</th></tr></thead>
                  <tbody>{source.tabs.map((tab) => (
                    <tr key={tab.sheet_id}>
                      <td>{tab.tab}<div className="muted">sheetId {tab.sheet_id} · {tab.profile_status ?? "—"}</div></td>
                      <td>{STATE_LABEL[tab.link_state]}</td>
                      <td>{tab.linked_customers.length === 0 ? "—" : tab.linked_customers.map((c) => c.customer_name ?? `#${c.customer_id}`).join(", ")}</td>
                      <td>
                        {tab.flags.length > 0 && (
                          <ul>{tab.flags.map((f) => <li key={f}>{FLAG_LABEL[f] ?? f}</li>)}</ul>
                        )}
                        <ul>{tab.proposals.map((p) => <li key={p}>{p}</li>)}</ul>
                        {tab.flags.length === 0 && tab.proposals.length === 0 ? "—" : null}
                        {tab.note && <div className="muted">{tab.note}</div>}
                      </td>
                    </tr>
                  ))}</tbody>
                </table></div>
              )}
            </div>
          ))}
        </>
      )}
    </section>
  );
}
