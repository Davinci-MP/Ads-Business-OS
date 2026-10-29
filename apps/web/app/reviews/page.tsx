"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJson, postJson } from "../../lib/api";

type CustomerRef = { id: number; name: string };
type ReviewRow = {
  id: number;
  customer_name: string | null;
  business_date: string;
  ad_account_meta_id: string;
  campaign_meta_id: string | null;
  campaign_name: string | null;
  observed_spend: string | null;
  sheet_spend: string | null;
  delta: string | null;
  currency: string;
  review_kind: string;
  match_status: string;
  note: string | null;
};
type SummaryRow = {
  business_date: string;
  customer_id: number;
  ad_account_meta_id: string;
  currency: string;
  total_observed: number | null;
  total_sheet: number | null;
  delta_account_day: number | null;
  match_status: string | null;
  baseline_confirmed: boolean;
  campaign_set_complete: boolean;
  campaigns: {
    campaign_meta_id: string | null;
    campaign_name: string | null;
    observed_spend: string | null;
    review_kind: string;
    match_status: string;
    last_observed_at: string | null;
  }[];
};
type ObservationRow = {
  id: number;
  observed_spend: string | null;
  currency: string;
  sheet_baseline: string | null;
  delta_account_day: string | null;
  match_status: string;
  observed_at: string | null;
  recorded_at: string | null;
  note: string | null;
};

export default function ReviewsPage() {
  const [customers, setCustomers] = useState<CustomerRef[]>([]);
  const [customerId, setCustomerId] = useState<string>("");
  const [businessDate, setBusinessDate] = useState<string>(new Date().toISOString().slice(0, 10));
  const [sheetName, setSheetName] = useState<string>("JOKER");
  const [spreadsheet, setSpreadsheet] = useState<string>("");
  const [reviews, setReviews] = useState<ReviewRow[]>([]);
  const [summary, setSummary] = useState<SummaryRow[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // F1: một lần lưu = một idempotency_key + một observed_at; retry sau lỗi mạng tái dùng đúng cặp này
  const pendingAttempt = useRef<{ signature: string; key: string; observedAt: string } | null>(null);

  // form nhập 1 campaign quan sát được
  const [adAccount, setAdAccount] = useState("");
  const [campaignId, setcampaignId] = useState("");
  const [campaignName, setcampaignNameForm] = useState("");
  const [observed, setObserved] = useState("");
  const [sheetSpend, setSheetSpend] = useState("");
  const [currency, setCurrency] = useState("USD");
  // F5: baseline từ mapping CONFIRMED? preview NEEDS_MAPPING không được chốt baseline
  const [baselineConfirmed, setBaselineConfirmed] = useState(false);
  const [compareStatus, setCompareStatus] = useState<string | null>(null);
  // F3: đã kiểm tra đủ tập campaign account+ngày? (điều kiện MATCH/DIFF)
  const [setComplete, setSetComplete] = useState(false);
  // lịch sử quan sát (append-only) theo review
  const [obsOpen, setObsOpen] = useState<number | null>(null);
  const [observations, setObservations] = useState<ObservationRow[]>([]);

  useEffect(() => {
    fetchJson<CustomerRef[]>("/customers")
      .then((data) => setCustomers(data))
      .catch(() => setCustomers([]));
  }, []);

  const loadSheetsBaseline = useCallback(async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const qs = new URLSearchParams({ sheet_name: sheetName });
      if (spreadsheet.trim()) qs.set("spreadsheet", spreadsheet.trim());
      const data = await fetchJson<{
        summary?: { status?: string; rows?: number };
        rows: { sheet_value?: number; sheet_currency?: string; ad_account_id?: string; status: string }[];
      }>(`/sheets/compare?${qs.toString()}`);
      const status = data.summary?.status ?? null;
      setCompareStatus(status);
      const usable = data.rows.filter((r) => r.ad_account_id && typeof r.sheet_value === "number");
      if (status === "NEEDS_MAPPING") {
        setBaselineConfirmed(false);
        setNotice(
          "MAPPING CHƯA CONFIRMED — đây chỉ là preview, KHÔNG chốt baseline (verdict sẽ là NEEDS_CONFIRMATION). Xác nhận mapping tab trên /sheets trước.",
        );
      } else if (usable.length === 0) {
        setBaselineConfirmed(false);
        setNotice(
          `Google Sheets: không đọc được baseline số (status=${data.rows.length ? (status ?? data.rows[0].status) : "trống"}) — nhập sheet_spend tay; baseline tay chưa chốt → verdict NEEDS_CONFIRMATION.`,
        );
      } else {
        const first = usable[0];
        setAdAccount(first.ad_account_id ?? "");
        setSheetSpend(String(first.sheet_value));
        setCurrency(first.sheet_currency ?? "USD");
        setBaselineConfirmed(true); // dòng đọc được = mapping đã CONFIRMED (server gate)
        setNotice(
          `Google Sheets: đọc được ${usable.length} dòng từ mapping CONFIRMED — baseline đã chốt dòng đầu (${first.ad_account_id}, ${first.sheet_value}). Kiểm tra lại ngày trước khi lưu.`,
        );
      }
    } catch (e) {
      setBaselineConfirmed(false);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [sheetName, spreadsheet]);

  const refresh = useCallback(async () => {
    if (!customerId) return;
    try {
      const day = businessDate;
      const [reviewRows, summaryRows] = await Promise.all([
        fetchJson<ReviewRow[]>(`/manual-reviews?customer_id=${customerId}&business_date=${day}`),
        fetchJson<SummaryRow[]>(`/manual-reviews/summary?customer_id=${customerId}&business_date=${day}`),
      ]);
      setReviews(reviewRows);
      setSummary(summaryRows);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [customerId, businessDate]);

  async function saveReview(reviewKind: "MANUAL_REVIEWED" | "VISUALLY_REVIEWED") {
    if (!customerId) {
      setError("Chọn khách trước");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const base = {
        customer_id: Number(customerId),
        business_date: businessDate,
        ad_account_meta_id: adAccount.trim(),
        review_kind: reviewKind,
        campaign_meta_id: campaignId.trim() || null,
        campaign_name: campaignName.trim() || null,
        observed_spend: reviewKind === "MANUAL_REVIEWED" ? observed.trim() || null : null,
        sheet_spend: sheetSpend.trim() || null,
        currency,
        sheet_name: sheetName || null,
        note: null,
        sheet_baseline_confirmed: baselineConfirmed && !!sheetSpend.trim(),
        campaign_set_complete: setComplete,
      };
      // Cùng nội dung form = cùng lần thử → giữ key/observed_at để retry không tạo observation trùng
      const signature = JSON.stringify(base);
      if (!pendingAttempt.current || pendingAttempt.current.signature !== signature) {
        const rand =
          typeof crypto !== "undefined" && "randomUUID" in crypto
            ? crypto.randomUUID()
            : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
        pendingAttempt.current = { signature, key: rand, observedAt: new Date().toISOString() };
      }
      const body = {
        ...base,
        idempotency_key: pendingAttempt.current.key,
        observed_at: pendingAttempt.current.observedAt, // thời điểm quan sát thực (F1)
      };
      if (reviewKind === "MANUAL_REVIEWED" && (!adAccount.trim() || !campaignId.trim() || !observed.trim())) {
        setError("Nhập đủ: Account ID + Campaign ID + số tiền quan sát được");
        return;
      }
      if (reviewKind === "VISUALLY_REVIEWED" && !adAccount.trim()) {
        setError("Nhập Account ID cần đánh dấu đã kiểm tra bằng mắt");
        return;
      }
      const data = await postJson<{ match_status: string }>("/manual-reviews", body);
      const extra =
        data.match_status === "VISUAL_ONLY"
          ? " (KHÔNG tự coi là MATCH)"
          : data.match_status === "NEEDS_CONFIRMATION"
            ? " (baseline preview/xung đột — chưa đủ điều kiện kết luận)"
            : data.match_status === "INCOMPLETE"
              ? " (chưa xác nhận đủ tập campaign)"
              : data.match_status === "MATCHED" || data.match_status === "DIFF"
                ? " (kết luận ở mức Customer+Account+Ngày+Currency)"
                : "";
      setNotice(`Đã lưu review: ${reviewKind} → trạng thái ${data.match_status}${extra}.`);
      pendingAttempt.current = null; // lần lưu kế tiếp (nếu có) là một lần kiểm tra mới
      setObserved("");
      setcampaignId("");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function toggleObservations(reviewId: number) {
    if (obsOpen === reviewId) {
      setObsOpen(null);
      setObservations([]);
      return;
    }
    try {
      const rows = await fetchJson<ObservationRow[]>(`/manual-reviews/${reviewId}/observations`);
      setObservations(rows);
      setObsOpen(reviewId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <main style={{ padding: 24 }}>
      <h1>Đối chiếu thủ công (không cần Meta token)</h1>
      <p>
        Quy trình: chọn khách + ngày báo cáo → đọc Google Sheets thật (chỉ đọc) → nhập Campaign ID + tổng
        chi tiêu tích lũy quan sát được trong Ads Manager → hiển thị chênh lệch → xác nhận/lưu.
        Đánh dấu bằng mắt KHÔNG được tự coi là MATCH.
      </p>

      <section style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 16 }}>
        <label>
          Khách:{" "}
          <select value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
            <option value="">—</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Ngày báo cáo: <input type="date" value={businessDate} onChange={(e) => setBusinessDate(e.target.value)} />
        </label>
        <button onClick={refresh} disabled={busy || !customerId}>
          Tải dữ liệu đã lưu
        </button>
      </section>

      <section style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 16, border: "1px solid #eee", padding: 12 }}>
        <strong>Đọc baseline Google Sheets (chỉ đọc)</strong>
        <label>
          Tên tab: <input value={sheetName} onChange={(e) => setSheetName(e.target.value)} />
        </label>
        <label>
          Spreadsheet ID: <input value={spreadsheet} onChange={(e) => setSpreadsheet(e.target.value)} placeholder="để trống = từ env/config" />
        </label>
        <button onClick={loadSheetsBaseline} disabled={busy}>
          Đọc Sheets
        </button>
        <span
          style={{
            padding: "2px 8px",
            borderRadius: 4,
            fontSize: 12,
            background: baselineConfirmed ? "#e6f6ea" : "#fdecea",
            color: baselineConfirmed ? "#1c7c3c" : "#b3261e",
            border: `1px solid ${baselineConfirmed ? "#1c7c3c" : "#b3261e"}`,
          }}
        >
          {baselineConfirmed
            ? "BASELINE CHỐT — mapping CONFIRMED"
            : compareStatus === "NEEDS_MAPPING"
              ? "MAPPING CHƯA CONFIRMED — preview, chưa chốt"
              : "BASELINE TAY/PREVIEW — chưa chốt"}
        </span>
      </section>

      {notice && <p style={{ color: "teal" }}>{notice}</p>}
      {error && <p style={{ color: "crimson" }}>Lỗi: {error}</p>}

      <section style={{ border: "1px solid #eee", padding: 12, marginBottom: 16 }}>
        <strong>Nhập quan sát Ads Manager</strong>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 8 }}>
          <label>
            Account ID:
            <input value={adAccount} onChange={(e) => setAdAccount(e.target.value)} placeholder="15 chữ số" />
          </label>
          <label>
            Campaign ID:
            <input value={campaignId} onChange={(e) => setcampaignId(e.target.value)} />
          </label>
          <label>
            Tên campaign:
            <input value={campaignName} onChange={(e) => setcampaignNameForm(e.target.value)} />
          </label>
          <label>
            Chi tiêu tích lũy quan sát:
            <input value={observed} onChange={(e) => setObserved(e.target.value)} />
          </label>
          <label>
            Baseline Sheets:
            <input value={sheetSpend} onChange={(e) => setSheetSpend(e.target.value)} />
          </label>
          <label>
            Đơn vị:
          <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
              <option>USD</option>
              <option>VND</option>
              <option>GBP</option>
              <option>EUR</option>
            </select>
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <input
              type="checkbox"
              checked={setComplete}
              onChange={(e) => setSetComplete(e.target.checked)}
            />
            Đã kiểm tra đủ tập campaign của account + ngày này (điều kiện MATCH/DIFF)
          </label>
          <button onClick={() => saveReview("MANUAL_REVIEWED")} disabled={busy}>
            Lưu MANUAL_REVIEWED
          </button>
          <button onClick={() => saveReview("VISUALLY_REVIEWED")} disabled={busy}>
            Đánh dấu VISUALLY_REVIEWED
          </button>
        </div>
        <p style={{ fontSize: 12, color: "#666", marginTop: 8 }}>
          MATCH/DIFF chỉ kết luận khi: baseline từ mapping CONFIRMED + đã đủ tập campaign + cùng đơn vị
          (USD/VND có tolerance; GBP/EUR → NEEDS_CONFIRMATION khi thiếu tỷ giá duyệt). Dữ liệu thiếu →
          NEEDS_SHEET_BASELINE / INCOMPLETE — không tự phán.
        </p>
      </section>

      {summary.length > 0 && (
        <>
          <h2>Kết luận theo Customer + Account + Ngày nghiệp vụ + Currency</h2>
          <p style={{ fontSize: 12, color: "#666" }}>
            Mỗi Campaign ID đếm 1 lần; baseline Sheets là số account+ngày (không cộng theo campaign);
            per-campaign chỉ ghi nhận (RECORDED), không phán MATCH/DIFF.
          </p>
          <table style={{ borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={cell}>Ngày</th>
                <th style={cell}>Account</th>
                <th style={cell}>Đơn vị</th>
                <th style={cell}>Tổng quan sát</th>
                <th style={cell}>Baseline Sheets</th>
                <th style={cell}>Chênh lệch</th>
                <th style={cell}>Kết luận</th>
                <th style={cell}>Điều kiện</th>
                <th style={cell}>Campaigns</th>
              </tr>
            </thead>
            <tbody>
              {summary.map((row, idx) => (
                <tr key={`${row.business_date}:${row.ad_account_meta_id}:${row.currency}`}>
                  <td style={cell}>{row.business_date}</td>
                  <td style={cell}>{row.ad_account_meta_id}</td>
                  <td style={cell}>{row.currency}</td>
                  <td style={cell}>{row.total_observed ?? "—"}</td>
                  <td style={cell}>{row.total_sheet ?? "—"}</td>
                  <td style={cell}>{row.delta_account_day ?? "—"}</td>
                  <td style={cell}>
                    <strong>{row.match_status ?? "—"}</strong>
                  </td>
                  <td style={cell}>
                    <div>baseline {row.baseline_confirmed ? "CONFIRMED ✓" : "preview ✗"}</div>
                    <div>tập campaign {row.campaign_set_complete ? "đủ ✓" : "chưa xác nhận ✗"}</div>
                  </td>
                  <td style={cell}>
                    {row.campaigns.map((cmp) => (
                      <div key={cmp.campaign_meta_id ?? `${row.business_date}-${row.ad_account_meta_id}-${idx}`}>
                        {cmp.campaign_meta_id}: obs {cmp.observed_spend ?? "—"} ({cmp.match_status})
                        {cmp.last_observed_at ? ` · lần cuối ${cmp.last_observed_at.slice(11, 16)}Z` : ""}
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {reviews.length > 0 && <h2>Lịch sử review (hiện hành)</h2>}
      <ul>
        {reviews.map((r) => (
          <li key={r.id} style={{ marginBottom: 6 }}>
            #{r.id} {r.review_kind} → {r.match_status} · {r.ad_account_meta_id} · {r.campaign_meta_id ?? "—"} · obs
            {r.observed_spend ?? "—"} vs sheet {r.sheet_spend ?? "—"} ({r.currency}){" "}
            <button onClick={() => toggleObservations(r.id)} style={{ fontSize: 12 }}>
              {obsOpen === r.id ? "Ẩn lịch sử quan sát" : "Xem lịch sử quan sát"}
            </button>
            {obsOpen === r.id && (
              <ul style={{ borderLeft: "3px solid #ddd", paddingLeft: 12, marginTop: 4 }}>
                {observations.map((o) => (
                  <li key={o.id} style={{ fontSize: 13 }}>
                    {o.observed_at ?? "—"} ghi lúc {o.recorded_at ?? "—"}: obs {o.observed_spend ?? "—"} vs baseline{" "}
                    {o.sheet_baseline ?? "—"} → {o.match_status}
                    {o.delta_account_day != null ? ` (Δ ${o.delta_account_day})` : ""}
                    {o.note ? ` · ${o.note}` : ""}
                  </li>
                ))}
                {observations.length === 0 && <li style={{ fontSize: 13 }}>chưa có quan sát nào</li>}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}

const cell: React.CSSProperties = {
  border: "1px solid #ddd",
  padding: "6px 10px",
  verticalAlign: "top",
};
