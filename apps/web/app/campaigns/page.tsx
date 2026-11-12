"use client";

import { useState } from "react";
import { Tag, useApi } from "../../components/ui";
import {
  fmtTime,
  fmtVnd,
  postJson,
  type CampaignRow,
  type MetaBillingHealth,
  type MetaCampaignTask,
  type TelegramStatus,
} from "../../lib/api";

type TabKey = "campaigns" | "billing" | "builder";

export default function CampaignsPage() {
  const [activeTab, setActiveTab] = useState<TabKey>("campaigns");

  // Dữ liệu Tab 1: Campaigns & Chi tiêu
  const {
    data: campaigns,
    error: campError,
    loading: campLoading,
    reload: reloadCamp,
  } = useApi<CampaignRow[]>("/dashboard/campaigns");

  // Dữ liệu Tab 2: Sức khoẻ thanh toán tài khoản
  const {
    data: billingAccounts,
    error: billingError,
    loading: billingLoading,
    reload: reloadBilling,
  } = useApi<MetaBillingHealth[]>("/meta/accounts/billing");

  // Dữ liệu Tab 3: Tasks & Telegram status & Telemetry
  const {
    data: tasks,
    loading: tasksLoading,
    reload: reloadTasks,
  } = useApi<MetaCampaignTask[]>("/meta/campaigns/tasks");

  const {
    data: tgStatus,
    reload: reloadTg,
  } = useApi<TelegramStatus>("/telegram/status");

  const {
    data: telemetry,
    reload: reloadTelemetry,
  } = useApi<{ max_util_pct: number; should_throttle: boolean }>("/meta/telemetry");

  const { data: managedAccounts, reload: reloadManagedAccounts } = useApi<{ meta_ad_account_id: string; allow_violated_accounts: boolean }[]>("/ad-accounts");
  const [overrideBusy, setOverrideBusy] = useState(false);

  // Form state cho Tạo chiến dịch
  const [actId, setActId] = useState("");
  const [campName, setCampName] = useState("");
  const [budgetStr, setBudgetStr] = useState("500000");
  const [objective, setObjective] = useState("OUTCOME_LEADS");
  const [postId, setPostId] = useState("");
  const [creating, setCreating] = useState(false);
  const [createMsg, setCreateMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  const selectedAccount = managedAccounts?.find((a) => a.meta_ad_account_id.replace(/^act_/, "") === actId.trim().replace(/^act_/, ""));

  const handleDryRun = () => {
    if (!actId.trim() || !campName.trim() || !budgetStr.trim()) {
      setCreateMsg({ ok: false, text: "Vui lòng nhập đầy đủ Tài khoản, Tên chiến dịch và Ngân sách ngày." });
      return;
    }
    const num = Number(budgetStr.replace(/\D/g, ""));
    if (isNaN(num) || num <= 0) {
      setCreateMsg({ ok: false, text: "Ngân sách ngày không hợp lệ." });
      return;
    }
    setPreviewOpen(true);
    setCreateMsg(null);
  };

  const handleCreate = async () => {
    setCreating(true);
    setCreateMsg(null);
    try {
      const budgetNum = Number(budgetStr.replace(/\D/g, ""));
      const res = await postJson<{ success: boolean; message: string; meta_campaign_id: string }>(
        "/meta/campaigns/create",
        {
          ad_account_id: actId.trim(),
          campaign_name: campName.trim(),
          daily_budget: budgetNum,
          objective,
          post_id: postId.trim() || null,
          created_by: "web_ui",
        }
      );
      setCreateMsg({
        ok: true,
        text: `${res.message} (Mã Camp: ${res.meta_campaign_id})`,
      });
      setPreviewOpen(false);
      setCampName("");
      void reloadTasks();
      void reloadCamp();
    } catch (err) {
      setCreateMsg({
        ok: false,
        text: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setCreating(false);
    }
  };

  const handleToggleStatus = async (metaCampaignId: string, currentStatus: string) => {
    const nextStatus = currentStatus === "ACTIVE" ? "PAUSED" : "ACTIVE";
    const label = nextStatus === "ACTIVE" ? "BẬT" : "TẮT";
    if (!confirm(`Bạn có chắc muốn ${label} chiến dịch ${metaCampaignId}?`)) return;

    try {
      await postJson(`/meta/campaigns/${metaCampaignId}/status`, {
        status: nextStatus,
        actor: "web_ui",
      });
      void reloadCamp();
      void reloadTasks();
    } catch (err) {
      alert(`Lỗi đổi trạng thái: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const sortedCampaigns = campaigns ? [...campaigns].sort((a, b) => {
    if (a.recognition_status === "UNRECOGNIZED" && b.recognition_status !== "UNRECOGNIZED") return -1;
    if (b.recognition_status === "UNRECOGNIZED" && a.recognition_status !== "UNRECOGNIZED") return 1;
    return (a.customer_name ?? "").localeCompare(b.customer_name ?? "");
  }) : [];

  return (
    <div className="w-full space-y-6">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>Quản trị Chiến dịch &amp; Telegram Bot Agent</h1>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={() => {
              void reloadCamp();
              void reloadBilling();
              void reloadTasks();
              void reloadTg();
              void reloadTelemetry();
            }}
            className="px-4 py-2 rounded-full bg-[#1ed760] hover:bg-[#1fdf64] text-black text-xs font-bold uppercase tracking-[1.4px] shadow transition"
            style={{ border: 0, cursor: "pointer" }}
          >
            Làm mới tất cả
          </button>
        </div>
      </div>

      {/* Tabs Selector */}
      <div style={{ display: "flex", gap: 8, borderBottom: "2px solid #e3e7ee", marginBottom: 20 }}>
        <button
          onClick={() => setActiveTab("campaigns")}
          style={{
            background: "none",
            border: "none",
            padding: "10px 16px",
            fontWeight: activeTab === "campaigns" ? 700 : 500,
            borderBottom: activeTab === "campaigns" ? "3px solid #16324f" : "3px solid transparent",
            color: activeTab === "campaigns" ? "#16324f" : "#66707d",
            cursor: "pointer",
            fontSize: 14,
          }}
        >
           Chiến dịch &amp; Chi tiêu ({sortedCampaigns.length})
        </button>
        <button
          onClick={() => setActiveTab("billing")}
          style={{
            background: "none",
            border: "none",
            padding: "10px 16px",
            fontWeight: activeTab === "billing" ? 700 : 500,
            borderBottom: activeTab === "billing" ? "3px solid #16324f" : "3px solid transparent",
            color: activeTab === "billing" ? "#16324f" : "#66707d",
            cursor: "pointer",
            fontSize: 14,
          }}
        >
           Tài khoản &amp; Hạn mức thanh toán
        </button>
        <button
          onClick={() => setActiveTab("builder")}
          style={{
            background: "none",
            border: "none",
            padding: "10px 16px",
            fontWeight: activeTab === "builder" ? 700 : 500,
            borderBottom: activeTab === "builder" ? "3px solid #16324f" : "3px solid transparent",
            color: activeTab === "builder" ? "#16324f" : "#66707d",
            cursor: "pointer",
            fontSize: 14,
          }}
        >
           Lên Camp an toàn &amp; Telegram Bot
        </button>
      </div>

      {/* TAB 1: Danh sách Campaign */}
      {activeTab === "campaigns" && (
        <div>
          <div className="toolbar">
            <span className="muted">Chi tiêu = snapshot tích lũy mới nhất (không cộng dồn).</span>
          </div>

          {campLoading && <p className="loading">Đang tải dữ liệu từ DB…</p>}
          {campError && <p className="error-box">Không đọc được dữ liệu: {campError}</p>}

          {campaigns && (
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
                  <th>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {sortedCampaigns.map((c) => (
                  <tr key={c.campaign_id}>
                    <td>
                      <b>{c.campaign_name}</b>
                      <div className="muted">{c.meta_campaign_id}</div>
                    </td>
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
                    <td>
                      <button
                        onClick={() => void handleToggleStatus(c.meta_campaign_id, c.meta_status ?? "PAUSED")}
                        style={{
                          background: c.meta_status === "ACTIVE" ? "#fde3e0" : "#e3f6e8",
                          color: c.meta_status === "ACTIVE" ? "#c0392b" : "#1e7d3c",
                          border: "1px solid currentColor",
                          borderRadius: 4,
                          padding: "3px 8px",
                          fontSize: 11,
                          cursor: "pointer",
                          fontWeight: 600,
                        }}
                      >
                        {c.meta_status === "ACTIVE" ? "Tạm dừng" : "Bật"}
                      </button>
                    </td>
                  </tr>
                ))}
                {sortedCampaigns.length === 0 && (
                  <tr>
                    <td colSpan={11} className="muted">Chưa có campaign nào được ghi nhận.</td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
          <p className="notice muted" style={{ marginTop: 12 }}>
            UNRECOGNIZED giữ nguyên — không tự gán khách; UNVERIFIED là snapshot cần điều tra, không nằm trong tổng chính thức.
          </p>
        </div>
      )}

      {/* TAB 2: Sức khoẻ thanh toán tài khoản */}
      {activeTab === "billing" && (
        <div>
          <div className="toolbar">
            <span className="muted">Thông tin hạn mức tín dụng, nợ cước và tình trạng tài khoản quảng cáo Meta.</span>
          </div>

          {billingLoading && <p className="loading">Đang tải thông số thanh toán từ Meta API…</p>}
          {billingError && <p className="error-box">Không thể lấy dữ liệu thanh toán: {billingError}</p>}

          {billingAccounts && (
            <table>
              <thead>
                <tr>
                  <th>Tài khoản</th>
                  <th>ID Meta</th>
                  <th>Trạng thái</th>
                  <th>Tiền tệ</th>
                  <th>Đã chi tiêu</th>
                  <th>Nợ cước hiện tại</th>
                  <th>Ngưỡng thanh toán</th>
                  <th>Giới hạn chi tiêu</th>
                </tr>
              </thead>
              <tbody>
                {billingAccounts.map((acc) => (
                  <tr key={acc.meta_ad_account_id}>
                    <td><b>{acc.name}</b></td>
                    <td><code>{acc.meta_ad_account_id}</code></td>
                    <td>
                      <span className={`tag ${acc.account_status === 1 ? "ok" : "bad"}`}>
                        {acc.account_status_label}
                      </span>
                      {acc.disable_reason > 0 && (
                        <div className="muted" style={{ fontSize: 11 }}>{acc.disable_reason_label}</div>
                      )}
                    </td>
                    <td><b>{acc.currency}</b></td>
                    <td>{fmtVnd(acc.amount_spent)} {acc.currency}</td>
                    <td>
                      <span style={{ color: acc.balance > 0 ? "#c0392b" : "inherit", fontWeight: acc.balance > 0 ? 600 : 400 }}>
                        {fmtVnd(acc.balance)} {acc.currency}
                      </span>
                    </td>
                    <td>{acc.billing_threshold != null ? `${fmtVnd(acc.billing_threshold)} ${acc.currency}` : "—"}</td>
                    <td>{acc.spend_cap != null ? `${fmtVnd(acc.spend_cap)} ${acc.currency}` : "Không giới hạn"}</td>
                  </tr>
                ))}
                {billingAccounts.length === 0 && (
                  <tr>
                    <td colSpan={8} className="muted">Không tìm thấy tài khoản quảng cáo nào.</td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* TAB 3: Campaign Builder & Telegram Agent */}
      {activeTab === "builder" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
          {/* Cột trái: Form tạo campaign an toàn */}
          <div style={{ background: "#181818", border: "1px solid #282828", borderRadius: 8, boxShadow: "0 8px 8px rgba(0,0,0,0.3)", padding: 18 }}>
            <h2 style={{ fontSize: 16, marginTop: 0, marginBottom: 12 }}> Tạo chiến dịch có kiểm soát (PAUSED)</h2>
            <p className="muted" style={{ fontSize: 13, marginBottom: 16 }}>
              Chiến dịch tạo qua hệ thống luôn mặc định ở trạng thái <b>TẠM DỪNG (PAUSED)</b> để đảm bảo an toàn tuyệt đối.
              Kiểm tra hạn mức ngân sách ngày tự động.
            </p>

            {createMsg && (
              <div
                style={{
                  padding: "10px 14px",
                  borderRadius: 6,
                  marginBottom: 14,
                  fontSize: 13,
                  background: createMsg.ok ? "#e3f6e8" : "#fde3e0",
                  color: createMsg.ok ? "#1e7d3c" : "#c0392b",
                  border: `1px solid ${createMsg.ok ? "#a3e6b5" : "#f8b4af"}`,
                }}
              >
                {createMsg.text}
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#465360", marginBottom: 4 }}>
                  Tài khoản quảng cáo (act_xxxx) *
                </label>
                <input
                  type="text"
                  placeholder="Ví dụ: act_mock_1 hoặc 123456789"
                  value={actId}
                  onChange={(e) => setActId(e.target.value)}
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #ccd4de", fontSize: 13 }}
                />
              </div>

              <label><input type="checkbox" role="switch" checked={selectedAccount?.allow_violated_accounts ?? false} disabled={!selectedAccount || overrideBusy} onChange={async (e) => {
                setOverrideBusy(true);
                try {
                  await postJson(`/meta/accounts/${encodeURIComponent(actId.trim())}/violation-override`, { enabled: e.target.checked });
                  await reloadManagedAccounts();
                } catch (err) { setCreateMsg({ ok: false, text: err instanceof Error ? err.message : String(err) }); }
                finally { setOverrideBusy(false); }
              }} />Cho phép chạy tài khoản vi phạm / Đặc cách</label>
              {!selectedAccount && <p className="muted">Thêm tài khoản vào mục Tài khoản trước khi cấu hình đặc cách.</p>}
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#465360", marginBottom: 4 }}>
                  Tên chiến dịch *
                </label>
                <input
                  type="text"
                  placeholder="Ví dụ: Chiến dịch Chuyển đổi Lead Q4"
                  value={campName}
                  onChange={(e) => setCampName(e.target.value)}
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #ccd4de", fontSize: 13 }}
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#465360", marginBottom: 4 }}>
                    Ngân sách ngày (VND) *
                  </label>
                  <input
                    type="text"
                    placeholder="500000"
                    value={budgetStr}
                    onChange={(e) => setBudgetStr(e.target.value)}
                    style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #ccd4de", fontSize: 13 }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#465360", marginBottom: 4 }}>
                    Mục tiêu (Objective)
                  </label>
                  <select
                    value={objective}
                    onChange={(e) => setObjective(e.target.value)}
                    style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #ccd4de", fontSize: 13 }}
                  >
                    <option value="OUTCOME_LEADS">Tìm kiếm khách hàng tiềm năng (Leads)</option>
                    <option value="OUTCOME_SALES">Bán hàng (Sales / Purchase)</option>
                    <option value="OUTCOME_TRAFFIC">Lưu lượng truy cập (Traffic)</option>
                    <option value="OUTCOME_ENGAGEMENT">Tương tác / Nhắn tin (Engagement)</option>
                  </select>
                </div>
              </div>

              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#465360", marginBottom: 4 }}>
                  ID Bài viết quảng cáo (Tùy chọn: page_id_post_id)
                </label>
                <input
                  type="text"
                  placeholder="Ví dụ: 123456789_987654321"
                  value={postId}
                  onChange={(e) => setPostId(e.target.value)}
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #ccd4de", fontSize: 13 }}
                />
              </div>

              {previewOpen && (
                <div style={{ background: "#f8fafc", border: "1px solid #cbd5e1", borderRadius: 8, padding: 12, marginTop: 4 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6, color: "#0f172a" }}> Xác nhận thiết lập (Dry-Run Preview):</div>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "#334155" }}>
                    <li>Tài khoản: <code>{actId}</code></li>
                    <li>Tên chiến dịch: <b>{campName}</b></li>
                    <li>Ngân sách: <b>{fmtVnd(budgetStr)} đ/ngày</b></li>
                    <li>Mục tiêu: <code>{objective}</code></li>
                    <li>Trạng thái khởi tạo: <span className="tag warn">PAUSED (An toàn)</span></li>
                  </ul>
                  <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
                    <button
                      onClick={() => void handleCreate()}
                      disabled={creating}
                      className="px-4 py-2 rounded-full bg-[#1ed760] hover:bg-[#1fdf64] text-black text-xs font-bold uppercase tracking-[1.4px] shadow transition cursor-pointer"
                      style={{ border: 0 }}
                    >
                      {creating ? "Đang gửi lên Meta…" : "Xác nhận tạo Campaign (PAUSED)"}
                    </button>
                    <button
                      onClick={() => setPreviewOpen(false)}
                      className="px-4 py-2 rounded-full bg-[#1f1f1f] hover:bg-[#282828] text-[#b3b3b3] hover:text-white border border-[#333333] text-xs font-bold uppercase tracking-[1.4px] transition cursor-pointer"
                      style={{ border: "1px solid #333333" }}
                    >
                      Hủy
                    </button>
                  </div>
                </div>
              )}

              {!previewOpen && (
                <div style={{ marginTop: 8 }}>
                  <button
                    onClick={handleDryRun}
                    disabled={overrideBusy}
                    className="px-5 py-2.5 rounded-full bg-[#1ed760] hover:bg-[#1fdf64] text-black text-xs font-bold uppercase tracking-[1.4px] shadow transition cursor-pointer"
                    style={{ border: 0 }}
                  >
                    Xem trước &amp; Xác nhận an toàn
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Cột phải: Trạng thái Telegram Bot & Lịch sử Tasks */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Box Telegram Bot & Telemetry */}
            <div style={{ background: "#181818", border: "1px solid #282828", borderRadius: 8, boxShadow: "0 8px 8px rgba(0,0,0,0.3)", padding: 18 }}>
              <h2 style={{ fontSize: 16, marginTop: 0, marginBottom: 12 }}> Telegram Bot Agent &amp; Telemetry</h2>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
                <div style={{ background: "#f8fafc", padding: 10, borderRadius: 6, border: "1px solid #e2e8f0" }}>
                  <div className="muted" style={{ fontSize: 11 }}>Trạng thái Bot</div>
                  <div style={{ fontWeight: 700, fontSize: 14, color: tgStatus?.is_configured ? "#1e7d3c" : "#b7791f" }}>
                    {tgStatus?.is_configured ? "Đã cấu hình (Live)" : "Chế độ Mock (Kiểm thử)"}
                  </div>
                  <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
                    Whitelist: <b>{tgStatus?.allowed_chat_ids_count ?? 0} chats</b>
                  </div>
                </div>
                <div style={{ background: "#f8fafc", padding: 10, borderRadius: 6, border: "1px solid #e2e8f0" }}>
                  <div className="muted" style={{ fontSize: 11 }}>Meta Rate-limit Usage</div>
                  <div style={{ fontWeight: 700, fontSize: 14, color: (telemetry?.max_util_pct ?? 0) >= 80 ? "#c0392b" : "#1e7d3c" }}>
                    {telemetry?.max_util_pct != null ? `${telemetry.max_util_pct.toFixed(1)}%` : "0.0%"}
                  </div>
                  <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
                    {(telemetry?.max_util_pct ?? 0) >= 80 ? " Đang tự động giảm tải" : "Bình thường"}
                  </div>
                </div>
              </div>

              <div style={{ background: "#f1f5f9", padding: 10, borderRadius: 6, fontSize: 12 }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}> Lệnh Telegram hỗ trợ:</div>
                <code style={{ display: "block", color: "#0f172a", marginBottom: 2 }}>/tk — Xem tài khoản &amp; cước</code>
                <code style={{ display: "block", color: "#0f172a", marginBottom: 2 }}>/baocao [act_id] [preset] — Báo cáo hiệu suất</code>
                <code style={{ display: "block", color: "#0f172a", marginBottom: 2 }}>/lencamp &lt;act_id&gt; &lt;tên&gt; &lt;ngân_sách&gt; — Lên camp PAUSED</code>
                <code style={{ display: "block", color: "#0f172a", marginBottom: 2 }}>/batcamp &lt;id&gt; — Bật chiến dịch</code>
                <code style={{ display: "block", color: "#0f172a" }}>/tatcamp &lt;id&gt; — Tắt chiến dịch</code>
              </div>
            </div>

            {/* Box Lịch sử Tasks */}
            <div style={{ background: "#181818", border: "1px solid #282828", borderRadius: 8, boxShadow: "0 8px 8px rgba(0,0,0,0.3)", padding: 18, flex: 1 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <h2 style={{ fontSize: 15, margin: 0 }}> Lịch sử tạo Campaign gần đây</h2>
                <button
                  onClick={() => void reloadTasks()}
                  style={{ background: "none", border: 0, color: "#1ed760", cursor: "pointer", fontSize: 12, fontWeight: 600 }}
                >
                  Tải lại
                </button>
              </div>

              {tasksLoading && <p className="loading">Đang tải lịch sử tasks…</p>}

              {tasks && (
                <div style={{ maxHeight: 280, overflowY: "auto" }}>
                  <table style={{ fontSize: 12 }}>
                    <thead>
                      <tr>
                        <th>Tên Camp</th>
                        <th>Ngân sách</th>
                        <th>Trạng thái</th>
                        <th>Tác nhân</th>
                        <th>Thời gian</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tasks.slice(0, 10).map((t) => (
                        <tr key={t.id}>
                          <td>
                            <b>{t.campaign_name}</b>
                            {t.meta_campaign_id && (
                              <div className="muted" style={{ fontSize: 10 }}>{t.meta_campaign_id}</div>
                            )}
                          </td>
                          <td>{fmtVnd(t.daily_budget)} đ</td>
                          <td>
                            <span className={`tag ${t.status === "SUCCESS" ? "ok" : "bad"}`}>
                              {t.status === "SUCCESS" ? "Thành công" : "Lỗi"}
                            </span>
                          </td>
                          <td className="muted">{t.created_by}</td>
                          <td className="muted">{fmtTime(t.created_at)}</td>
                        </tr>
                      ))}
                      {tasks.length === 0 && (
                        <tr>
                          <td colSpan={5} className="muted">Chưa có tác vụ tạo nào.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
