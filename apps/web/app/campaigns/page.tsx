"use client";

import { Tag, useApi } from "../../components/ui";
import { fmtTime, fmtVnd, type CampaignRow } from "../../lib/api";

export default function CampaignsPage() {
  const { data, error, loading, reload } = useApi<CampaignRow[]>("/dashboard/campaigns");

  if (loading) return <main className="page"><p className="loading">Đang tải dữ liệu từ DB…</p></main>;
  if (error || !data)
    return (
      <main className="page">
        <p className="error-box">Không đọc được dữ liệu: {error}</p>
      </main>
    );

  const sorted = [...data].sort((a, b) => {
    if (a.recognition_status === "UNRECOGNIZED" && b.recognition_status !== "UNRECOGNIZED") return -1;
    if (b.recognition_status === "UNRECOGNIZED" && a.recognition_status !== "UNRECOGNIZED") return 1;
    return (a.customer_name ?? "").localeCompare(b.customer_name ?? "");
  });

  return (
    <main className="page">
      <h1>Campaign &amp; chi tiêu</h1>
      <div className="toolbar">
        <button onClick={() => void reload()}>Làm mới</button>
        <span className="muted">Chi tiêu = snapshot tích lũy mới nhất (không cộng dồn).</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>Campaign</th>
            <th>Khách</th>
            <th>Ad account</th>
            <th>Múi giờ</th>
            <th>Kỳ báo cáo</th>
            <th>Chi tiêu mới nhất</th>
            <th>Mốc 09:00</th>
            <th>Tiền trôi</th>
            <th>Trạng thái Meta</th>
            <th>Nhận diện</th>
            <th>Cập nhật</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((c) => (
            <tr key={c.campaign_id}>
              <td>{c.campaign_name}<div className="muted">{c.meta_campaign_id}</div></td>
              <td>{c.customer_name ?? <span className="tag warn">Chưa gán</span>}</td>
              <td>{c.ad_account_id ?? "—"}</td>
              <td className="muted">{c.timezone_name ?? "—"}</td>
              <td className="muted">
                {c.report_period_start ?? "?"}
                {c.report_period_end ? ` → ${c.report_period_end}` : ""}
              </td>
              <td>
                {fmtVnd(c.latest_spend)}
                {c.unverified && <span className="tag warn"> UNVERIFIED</span>}
              </td>
              <td>{fmtVnd(c.checkpoint_9h_spend)}</td>
              <td>{fmtVnd(c.drift_amount)}</td>
              <td><Tag value={c.meta_status} /></td>
              <td><Tag value={c.recognition_status} /></td>
              <td className="muted">{fmtTime(c.latest_spend_at)}</td>
            </tr>
          ))}
          {data.length === 0 && (
            <tr>
              <td colSpan={11} className="muted">Chưa có campaign — chạy sync Meta (mock) để tạo dữ liệu.</td>
            </tr>
          )}
        </tbody>
      </table>
      <p className="notice muted">
        UNRECOGNIZED vừa để nguyên — không tự gán khách; UNVERIFIED là snapshot cần điều tra, không nằm trong tổng chính thức.
      </p>
    </main>
  );
}
