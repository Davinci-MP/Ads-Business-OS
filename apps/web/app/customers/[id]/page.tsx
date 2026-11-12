"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { fetchJson, ClientBMPreference } from "../../../lib/api";
import CustomerSheets from "../../customer-sheets";
import CustomerYearSummary from "../../customer-year-summary";
import ClientBMPreferenceModal from "../../../components/client-bm-preference-modal";

type CustomerReport = {
  customer: { id: number; name: string; fee_rate: string; recon_mode: string; profit_share_enabled: boolean };
  meta_source_label: string;
  company_reference_state: string;
  daily_spend: { rows: { business_date: string; meta_spend: number | null; manual_spend: number | null; fee: number | null; billing_total: number | null; manual_by_currency?: Record<string, number>; fee_by_currency?: Record<string, number>; meta_source: string; campaign_count: number }[]; meta_mode: string; meta_source_label: string; note: string };
  accounts_history: { ad_account_meta_id: string | null; status: string | null; valid_from: string | null; valid_to: string | null }[];
  campaigns: { meta_campaign_id: string; name: string; recognition_status: string | null; report_period_start: string | null; report_period_end: string | null; meta_status: string | null }[];
  deposits_usdt: { tx_hash: string; amount: string; currency: string; occurred_at: string | null }[];
  account_summary_by_day: { business_date: string; ad_account_meta_id: string; currency: string; total_observed: number | null; total_sheet: number | null; delta_account_day: number | null; match_status: string | null; baseline_confirmed: boolean; campaign_set_complete: boolean; campaigns: { campaign_meta_id: string | null; observed_spend: string | null; match_status: string; review_kind: string }[] }[];
  reviews: { id: number; review_kind: string; match_status: string; business_date: string; ad_account_meta_id: string; campaign_meta_id: string | null; observed_spend: string | null; sheet_spend: string | null }[];
  fee_note: string;
  error?: string;
};

const cell: React.CSSProperties = {
  border: "1px solid #ddd",
  padding: "4px 8px",
  verticalAlign: "top",
  textAlign: "left",
};

export default function CustomerDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Array.isArray(params.id) ? params.id[0] : params.id;
  const [report, setReport] = useState<CustomerReport | null>(null);
  const [bmPref, setBmPref] = useState<ClientBMPreference | null>(null);
  const [showBmModal, setShowBmModal] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadBmPref = (customerId: string) => {
    fetchJson<ClientBMPreference>(`/clients/${customerId}/bm-preferences`)
      .then((data) => setBmPref(data))
      .catch(() => {});
  };

  useEffect(() => {
    if (!id) return;
    fetchJson<CustomerReport>(`/reports/customers/${id}`)
      .then((data) => {
        if (data && "error" in data && data.error) setError(data.error);
        else setReport(data);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));

    loadBmPref(id);
  }, [id]);

  if (error) {
    return (
      <div className="w-full space-y-4">
        <p style={{ color: "crimson" }}>Lỗi: {error}</p>
        <Link href="/reports">← Về báo cáo</Link>
      </div>
    );
  }
  if (!report) {
    return <div className="w-full space-y-4">Đang tải…</div>;
  }

  const c = report.customer;
  return (
    <div className="w-full space-y-6">
      <p>
        <Link href="/reports">← Báo cáo</Link>
      </p>
      <h1>{c.name}</h1>
      <CustomerSheets customerId={c.id} />
      <CustomerYearSummary customerId={c.id} />
      <p>
        ID {c.id} · fee_rate {c.fee_rate} (khoản riêng) · recon_mode {c.recon_mode} · profit_share{" "}
        {c.profit_share_enabled ? "BẬT" : "TẮT"} · {c.profit_share_enabled ? "chỉ theo D-022" : "mặc định"}
      </p>
      <p style={{ color: "#666" }}>
        Nguồn số Meta: {report.meta_source_label} · {report.fee_note}
      </p>

      <div style={{ background: "#111827", border: "1px solid #1F2937", borderRadius: 12, padding: 16, margin: "16px 0", color: "#f3f4f6" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 18 }}></span>
            <strong style={{ fontSize: 15, color: "#fff" }}>Phân Quyền Multi-BM &amp; Bộ Nhớ Định Tuyến</strong>
            {bmPref?.is_configured ? (
              <span style={{ fontSize: 11, background: "rgba(16, 185, 129, 0.2)", color: "#34d399", padding: "2px 8px", borderRadius: 999, border: "1px solid rgba(16, 185, 129, 0.3)" }}>
                 Đã ghi nhớ
              </span>
            ) : (
              <span style={{ fontSize: 11, background: "rgba(245, 158, 11, 0.2)", color: "#fbbf24", padding: "2px 8px", borderRadius: 999, border: "1px solid rgba(245, 158, 11, 0.3)" }}>
                Chưa thiết lập
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={() => setShowBmModal(true)}
            style={{ background: "#9333ea", color: "#fff", border: "none", padding: "6px 14px", borderRadius: 8, cursor: "pointer", fontSize: 12, fontWeight: 600 }}
          >
             Chỉnh Sửa Phân Quyền (1-Click)
          </button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, fontSize: 12, background: "#1A2234", padding: 12, borderRadius: 8 }}>
          <div>
            <span style={{ color: "#9ca3af", display: "block", fontSize: 11 }}>BM Chỉ Định:</span>
            <strong style={{ color: "#c084fc", fontSize: 13 }}>{bmPref?.bm_full_name || bmPref?.bm_name || "BM 1 (Mặc định)"}</strong>
          </div>
          <div>
            <span style={{ color: "#9ca3af", display: "block", fontSize: 11 }}>Vai Trò BM:</span>
            <strong style={{ color: "#60a5fa", fontSize: 13 }}>{bmPref?.bm_role_label || "Nhân viên (EMPLOYEE)"}</strong>
          </div>
          <div>
            <span style={{ color: "#9ca3af", display: "block", fontSize: 11 }}>Quyền Hạn TKQC:</span>
            <strong style={{ color: "#34d399", fontSize: 13 }}>{bmPref?.ad_account_access_label || "Truy cập đầy đủ (FULL)"}</strong>
            {bmPref?.ad_account_access_type === "PARTIAL" && bmPref?.partial_permissions_labels && (
              <div style={{ color: "#9ca3af", fontSize: 10, marginTop: 2 }}>{bmPref.partial_permissions_labels.join(", ")}</div>
            )}
          </div>
        </div>
      </div>

      <h2>Xếp lịch sử ad account</h2>
      <table style={{ borderCollapse: "collapse", marginBottom: 16 }}>
        <thead>
          <tr>
            <th style={cell}>Account</th>
            <th style={cell}>Trạng thái</th>
            <th style={cell}>Từ</th>
            <th style={cell}>Đến</th>
          </tr>
        </thead>
        <tbody>
          {report.accounts_history.map((h, i) => (
            <tr key={`${h.ad_account_meta_id}-${i}`}>
              <td style={cell}>{h.ad_account_meta_id ?? "—"}</td>
              <td style={cell}>{h.status ?? "—"}</td>
              <td style={cell}>{h.valid_from ?? "—"}</td>
              <td style={cell}>{h.valid_to ?? "hiện tại"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Campaigns</h2>
      <table style={{ borderCollapse: "collapse", marginBottom: 16 }}>
        <thead>
          <tr>
            <th style={cell}>Campaign ID</th>
            <th style={cell}>Tên</th>
            <th style={cell}>Nhận diện</th>
            <th style={cell}>Kỳ (start → end)</th>
            <th style={cell}>Trạng thái Meta</th>
          </tr>
        </thead>
        <tbody>
          {report.campaigns.map((cmp) => (
            <tr key={cmp.meta_campaign_id}>
              <td style={cell}>{cmp.meta_campaign_id}</td>
              <td style={cell}>{cmp.name}</td>
              <td style={cell}>{cmp.recognition_status ?? "—"}</td>
              <td style={cell}>
                {cmp.report_period_start ?? "—"} → {cmp.report_period_end ?? "—"}
              </td>
              <td style={cell}>{cmp.meta_status ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Nạp USDT (MATCHED — đơn vị riêng, không trộn profit)</h2>
      {report.deposits_usdt.length === 0 ? (
        <p>Chưa có giao dịch MATCHED.</p>
      ) : (
        <ul>
          {report.deposits_usdt.map((d) => (
            <li key={d.tx_hash}>
              {d.tx_hash} · {d.amount} {d.currency} · {d.occurred_at ?? "—"}
            </li>
          ))}
        </ul>
      )}

      <h2>Chi tiêu theo ngày</h2>
      <p style={{ fontSize: 13, color: "#666" }}>Các cột số là phần USD; tiền khác hiển thị theo đơn vị riêng.</p>
      {report.daily_spend.rows.length === 0 ? (
        <p>Không có dòng nào — KHÔNG hiển thị 0 giả.</p>
      ) : (
        <table style={{ borderCollapse: "collapse", marginBottom: 16 }}>
          <thead>
            <tr>
              <th style={cell}>Ngày</th>
              <th style={cell}>Meta</th>
              <th style={cell}>Manual</th>
              <th style={cell}>Phí</th>
              <th style={cell}>Billing</th>
              <th style={cell}>Nguồn</th>
            </tr>
          </thead>
          <tbody>
            {report.daily_spend.rows.map((row) => {
              const manualOther = Object.entries(row.manual_by_currency ?? {})
                .filter(([cur, v]) => cur !== "USD" && v !== 0)
                .map(([cur, v]) => `${v.toLocaleString("vi-VN")} ${cur}`)
                .join(" · ");
              const feeOther = Object.entries(row.fee_by_currency ?? {})
                .filter(([cur, v]) => cur !== "USD" && v !== 0)
                .map(([cur, v]) => `${v.toLocaleString("vi-VN")} ${cur}`)
                .join(" · ");
              return (
                <tr key={row.business_date}>
                  <td style={cell}>{row.business_date}</td>
                  <td style={cell}>{row.meta_spend ?? "—"}</td>
                  <td style={cell}>
                    {row.manual_spend ?? "—"}
                    {manualOther && <div style={{ fontSize: 12 }}>{manualOther}</div>}
                  </td>
                  <td style={cell}>
                    {row.fee ?? "—"}
                    {feeOther && <div style={{ fontSize: 12 }}>{feeOther}</div>}
                  </td>
                  <td style={cell}>{row.billing_total ?? "—"}</td>
                  <td style={cell}>{row.meta_source}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      <h2>Kết luận theo account + ngày nghiệp vụ</h2>
      <table style={{ borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={cell}>Ngày</th>
            <th style={cell}>Account</th>
            <th style={cell}>Đơn vị</th>
            <th style={cell}>Tổng quan sát</th>
            <th style={cell}>Baseline</th>
            <th style={cell}>Chênh lệch</th>
            <th style={cell}>Kết luận</th>
            <th style={cell}>Campaigns (mỗi ID 1 dòng)</th>
          </tr>
        </thead>
        <tbody>
          {report.account_summary_by_day.map((row, idx) => (
            <tr key={`${row.business_date}-${row.ad_account_meta_id}-${idx}`}>
              <td style={cell}>{row.business_date}</td>
              <td style={cell}>{row.ad_account_meta_id}</td>
              <td style={cell}>{row.currency}</td>
              <td style={cell}>{row.total_observed ?? "—"}</td>
              <td style={cell}>
                {row.total_sheet ?? "—"}
                <div style={{ fontSize: 12 }}>
                  {row.baseline_confirmed ? "mapping CONFIRMED " : "preview chưa chốt "} ·{" "}
                  {row.campaign_set_complete ? "đủ tập campaign " : "chưa xác nhận tập "}
                </div>
              </td>
              <td style={cell}>{row.delta_account_day ?? "—"}</td>
              <td style={cell}>
                <strong>{row.match_status ?? "—"}</strong>
              </td>
              <td style={cell}>
                {row.campaigns.map((cmp, i) => (
                  <div key={i}>
                    {cmp.campaign_meta_id ?? "—"}: {cmp.observed_spend ?? "—"} ({cmp.review_kind})
                  </div>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {showBmModal && id && (
        <ClientBMPreferenceModal
          clientId={Number(id)}
          clientName={c.name}
          isOpen={showBmModal}
          onClose={() => setShowBmModal(false)}
          onSaved={() => loadBmPref(id)}
        />
      )}
    </div>
  );
}
