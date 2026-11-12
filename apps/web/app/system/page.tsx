"use client";

import { useApi } from "../../components/ui";
import { fmtTime, fmtVnd, type SystemInfo } from "../../lib/api";

export default function SystemPage() {
  const { data, error, loading, reload } = useApi<SystemInfo>("/dashboard/system");

  if (loading) return <div className="w-full space-y-6"><p className="loading">Đang tải dữ liệu từ DB…</p></div>;
  if (error || !data)
    return (
      <div className="w-full space-y-6">
        <p className="error-box">Không đọc được dữ liệu: {error}</p>
      </div>
    );

  const hasIssues =
    data.api_errors.length > 0 ||
    data.missed_checkpoints.length > 0 ||
    data.campaigns_need_verification.length > 0 ||
    data.unverified_snapshots.length > 0;

  return (
    <div className="w-full space-y-6">
      <h1>Giám sát hệ thống</h1>
      <div className="cards">
        <div className="card">
          <div className="label">Chế độ connector</div>
          <div className="value" style={{ fontSize: 15 }}>
            {data.mode === "live" ? "LIVE (Meta thật)" : "MOCK (chưa có token)"}
          </div>
        </div>
        <div className="card">
          <div className="label">Sync gần nhất</div>
          <div className="value" style={{ fontSize: 15 }}>{fmtTime(data.last_sync_at)}</div>
        </div>
        <div className="card">
          <div className="label">Tình trạng</div>
          <div className={`value ${hasIssues ? "warn" : "ok"}`} style={{ fontSize: 15 }}>
            {hasIssues ? "Cần chú ý" : "Bình thường"}
          </div>
        </div>
      </div>

      <div className="section-title">Checkpoint 09:00 bị bỏ lỡ (MISSED_CHECKPOINT)</div>
      <table>
        <thead><tr><th>Thời điểm ghi nhận</th></tr></thead>
        <tbody>
          {data.missed_checkpoints.map((m, i) => (
            <tr key={i}><td>{fmtTime(m.at)}</td></tr>
          ))}
          {data.missed_checkpoints.length === 0 && (
            <tr><td colSpan={1} className="muted ok">Không có — checkpoint 09:00 đã chạy đúng.</td></tr>
          )}
        </tbody>
      </table>

      <div className="section-title">Lỗi API Meta (giữ nguyên dữ liệu cũ, gắn cờ)</div>
      <table>
        <thead><tr><th>Campaign/account</th><th>Chi tiết</th><th>Thời điểm</th></tr></thead>
        <tbody>
          {data.api_errors.map((e, i) => (
            <tr key={i}>
              <td>{e.entity}</td>
              <td>{e.detail ?? "—"}</td>
              <td className="muted">{fmtTime(e.at)}</td>
            </tr>
          ))}
          {data.api_errors.length === 0 && (
            <tr><td colSpan={3} className="muted ok">Không có lỗi API gần đây.</td></tr>
          )}
        </tbody>
      </table>

      <div className="section-title">Campaign có snapshot UNVERIFIED (cần điều tra)</div>
      <table>
        <thead><tr><th>Campaign</th><th>Snapshot lúc</th><th>Chi tiêu</th></tr></thead>
        <tbody>
          {data.unverified_snapshots.map((s, i) => (
            <tr key={i}>
              <td>{s.meta_campaign_id}</td>
              <td>{fmtTime(s.snapshot_at)}</td>
              <td>{fmtVnd(s.spend_amount)}</td>
            </tr>
          ))}
          {data.unverified_snapshots.length === 0 && (
            <tr><td colSpan={3} className="muted ok">Không có snapshot UNVERIFIED.</td></tr>
          )}
        </tbody>
      </table>

      <div className="section-title">Campaign chưa nhận diện được (UNRECOGNIZED)</div>
      <table>
        <thead><tr><th>Campaign</th><th>Tên</th><th>Trạng thái</th></tr></thead>
        <tbody>
          {data.campaigns_need_verification.map((c, i) => (
            <tr key={c.meta_campaign_id + String(i)}>
              <td>{c.meta_campaign_id}</td>
              <td>{c.name}</td>
              <td><span className="tag warn">{c.status}</span></td>
            </tr>
          ))}
          {data.campaigns_need_verification.length === 0 && (
            <tr><td colSpan={3} className="muted ok">Tất cả campaign đã nhận diện.</td></tr>
          )}
        </tbody>
      </table>

      <div className="toolbar" style={{ marginTop: 14 }}>
        <button onClick={() => void reload()}>Làm mới</button>
      </div>
      <p className="notice muted">
        Danh sách này chỉ liệt kê — hệ thống không tự sửa số liệu đã xác nhận; cần chủ dự án xử lý thủ công.
      </p>
    </div>
  );
}
