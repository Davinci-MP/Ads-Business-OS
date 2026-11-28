"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AdsCheckResponse,
  AdsCheckSummary,
  PixelItem,
  ScanResult,
  ScannedAccountFields,
  SyncedAdAccount,
  SyncedBM,
  SyncedPageItem,
  ViaProfile,
  getAdsCheckData,
  getAdsCheckPixels,
  getVias,
  scanVia,
} from "../../lib/api";
import { MonoIcon } from "../../components/mono-icon";
import "./adscheck.css";

type Tab = "accounts" | "bm" | "page" | "pixel";
type Account = SyncedAdAccount & ScannedAccountFields;

const TABS: { key: Tab; label: string; icon: Parameters<typeof MonoIcon>[0]["name"] }[] = [
  { key: "accounts", label: "Tài khoản quảng cáo", icon: "account" },
  { key: "bm", label: "Business Manager", icon: "business" },
  { key: "page", label: "Fanpage", icon: "customer" },
  { key: "pixel", label: "Pixel", icon: "analytics" },
];

// tab giao diện → tab API (accounts = cá nhân + BM; group = danh sách BM)
const API_TAB: Record<Exclude<Tab, "pixel">, string> = { accounts: "accounts", bm: "group", page: "page" };

const DISABLE_REASON_VI: Record<string, string> = {
  ADS_INTEGRITY_POLICY: "Vi phạm chính sách quảng cáo",
  ADS_IP_REVIEW: "Xét duyệt sở hữu trí tuệ",
  RISK_PAYMENT: "Rủi ro thanh toán",
  GRAY_ACCOUNT_SHUT_DOWN: "Tài khoản xám bị đóng",
  ADS_AFC_REVIEW: "Xét duyệt AFC",
  BUSINESS_INTEGRITY_RAR: "Vi phạm toàn vẹn doanh nghiệp",
  PERMANENT_CLOSE: "Đóng vĩnh viễn",
  UNUSED_RESELLER_ACCOUNT: "TK đại lý không dùng",
  UNUSED_ACCOUNT: "TK không hoạt động",
  UMBRELLA_AD_ACCOUNT: "TK umbrella",
  BUSINESS_MANAGER_INTEGRITY_POLICY: "BM vi phạm chính sách",
  MISREPRESENTED_AD_ACCOUNT: "Thông tin TK sai lệch",
  AOAB_DESHARE_LEGAL_ENTITY: "Gỡ chia sẻ pháp nhân",
  CTX_THREAD_REVIEW: "Xét duyệt hội thoại",
  COMPROMISED_AD_ACCOUNT: "TK bị xâm phạm",
};

const ROLE_VI: Record<string, string> = { ADMIN: "Quản trị", ADVERTISER: "Nhà quảng cáo", ANALYST: "Nhà phân tích" };

const EMPTY_SUMMARY: AdsCheckSummary = {
  total_accounts_count: 0, total_balance: 0, total_threshold: 0, total_limit: 0, total_spend: 0,
  primary_currency: "VND", label: "",
};

const nf = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 });

function Money({ value, currency, empty = "—" }: { value: number | null | undefined; currency?: string; empty?: string }) {
  if (value === null || value === undefined) return <span className="ac-muted">{empty}</span>;
  return <span className="ac-money">{nf.format(value)}<small>{currency}</small></span>;
}

function fmtDate(raw: string | null | undefined): string {
  if (!raw) return "—";
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("vi-VN");
}

function relTime(raw: string | null | undefined): string {
  if (!raw) return "Chưa bắn";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return "—";
  const days = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (days <= 0) return "Hôm nay";
  if (days === 1) return "Hôm qua";
  return `${days} ngày trước`;
}

function accountStatus(a: Account): { cls: string; label: string } {
  const code = a.account_status;
  if (code === 1 || (code === undefined && a.status_dot === "LIVE")) return { cls: "ok", label: "Hoạt động" };
  if (code === 3 || code === 8 || code === 9) return { cls: "warn", label: code === 9 ? "Gia hạn nợ" : "Nợ / Chưa thanh toán" };
  if (code === 7) return { cls: "warn", label: "Đang xét duyệt" };
  if (code === 100) return { cls: "bad", label: "Chờ đóng" };
  if (code === 101) return { cls: "idle", label: "Đã đóng" };
  if (code === 2 || a.status_dot === "DIE") return { cls: "bad", label: "Vô hiệu hóa" };
  return { cls: "idle", label: "Không rõ" };
}

function limitText(a: Account) {
  if (a.ad_trust_dsl === null || a.ad_trust_dsl === undefined) return <span className="ac-muted">—</span>;
  if (a.ad_trust_dsl < 0) return <span className="ac-chip assigned">Không giới hạn</span>;
  return <Money value={a.ad_trust_dsl} currency={a.currency} />;
}

function csvCell(v: unknown): string {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

type ScanRow = { via: ViaProfile; state: "wait" | "run" | "done" | "fail"; result?: ScanResult };

export default function AdsCheckPage() {
  const [tab, setTab] = useState<Tab>("accounts");
  const [data, setData] = useState<AdsCheckResponse | null>(null);
  // Thẻ thống kê luôn là số liệu TKQC (API trả summary theo tab đang mở).
  const [accountSummary, setAccountSummary] = useState<AdsCheckSummary>(EMPTY_SUMMARY);
  const [pixels, setPixels] = useState<PixelItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [vias, setVias] = useState<ViaProfile[]>([]);
  const [viaId, setViaId] = useState("");
  const [status, setStatus] = useState("");
  const [accountType, setAccountType] = useState("");
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [page, setPage] = useState(1);
  const [reloadKey, setReloadKey] = useState(0);
  const [copied, setCopied] = useState<string | null>(null);
  const [scanOpen, setScanOpen] = useState(false);
  const [scanTarget, setScanTarget] = useState("all");
  const [scanRows, setScanRows] = useState<ScanRow[]>([]);
  const [scanning, setScanning] = useState(false);
  const [exporting, setExporting] = useState(false);
  const pageSize = 50;

  const authorizedVias = useMemo(() => vias.filter((v) => v.token_status === "ACTIVE"), [vias]);

  useEffect(() => {
    getVias().then((r) => setVias(r.vias || [])).catch(() => setVias([]));
  }, [reloadKey]);

  // Hỗ trợ link từ Dàn VIA: /adscheck?via_id=<id>
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("via_id");
    if (id && /^\d+$/.test(id)) setViaId(id);
  }, []);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 350);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => setPage(1), [tab, viaId, status, accountType, debounced]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (tab === "pixel") {
        const res = await getAdsCheckPixels({ via_id: viaId ? Number(viaId) : undefined, search: debounced || undefined });
        setPixels(res.items || []);
      } else {
        const res = await getAdsCheckData({
          tab: API_TAB[tab],
          via_id: viaId ? Number(viaId) : undefined,
          search: debounced || undefined,
          status: tab === "accounts" && status ? status : undefined,
          account_type: tab === "accounts" && accountType ? accountType : undefined,
          page,
          page_size: pageSize,
        });
        setData(res);
        if (tab === "accounts") setAccountSummary(res.summary || EMPTY_SUMMARY);
      }
      if (tab !== "accounts") {
        const sum = await getAdsCheckData({ tab: "accounts", via_id: viaId ? Number(viaId) : undefined, page: 1, page_size: 1 });
        setAccountSummary(sum.summary || EMPTY_SUMMARY);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không tải được dữ liệu ADS CHECK");
    } finally {
      setLoading(false);
    }
  }, [tab, viaId, status, accountType, debounced, page]);

  useEffect(() => {
    void load();
  }, [load, reloadKey]);

  const summary = accountSummary;
  const totalPages = Math.max(1, data?.total_pages || Math.ceil((data?.total_count || 0) / pageSize));
  const extraCurrencies = Object.keys(summary.currency_breakdown || {}).filter((c) => c !== summary.primary_currency);

  async function runScan() {
    const targets = scanTarget === "all" ? authorizedVias : authorizedVias.filter((v) => String(v.id) === scanTarget);
    if (!targets.length) return;
    setScanning(true);
    const rows: ScanRow[] = targets.map((via) => ({ via, state: "wait" }));
    setScanRows(rows);
    for (let i = 0; i < rows.length; i += 1) {
      rows[i] = { ...rows[i], state: "run" };
      setScanRows([...rows]);
      try {
        const result = await scanVia(rows[i].via.id);
        rows[i] = { ...rows[i], state: result.ok ? "done" : "fail", result };
      } catch (e) {
        rows[i] = { ...rows[i], state: "fail", result: { ok: false, via_id: rows[i].via.id, error: e instanceof Error ? e.message : "Lỗi không xác định" } };
      }
      setScanRows([...rows]);
    }
    setScanning(false);
    setReloadKey((k) => k + 1);
  }

  async function exportCsv() {
    setExporting(true);
    try {
      const all: Account[] = [];
      for (let p = 1; p <= 40; p += 1) {
        const res = await getAdsCheckData({
          tab: "accounts", via_id: viaId ? Number(viaId) : undefined, search: debounced || undefined,
          status: status || undefined, account_type: accountType || undefined, page: p, page_size: 500,
        });
        all.push(...(res.items as Account[]));
        if (all.length >= res.total_count || !res.items.length) break;
      }
      const header = ["ID TKQC", "Tên", "Trạng thái", "Lý do khoá", "Loại", "BM", "Tiền tệ", "Số dư", "Đã tiêu",
        "Limit/ngày", "Ngưỡng", "Spend cap", "Thẻ", "Quyền", "Múi giờ", "Ngày tạo", "Số pixel", "VIA"];
      const lines = all.map((a) => [
        a.act_id, a.name, accountStatus(a).label,
        a.disable_reason && a.disable_reason !== "NONE" ? DISABLE_REASON_VI[a.disable_reason] || a.disable_reason : "",
        a.account_type === "BM" ? "BM" : "Cá nhân", a.business_name || a.bm_id || "", a.currency,
        a.balance ?? "", a.amount_spent ?? a.total_spend ?? "",
        a.ad_trust_dsl !== null && a.ad_trust_dsl !== undefined && a.ad_trust_dsl < 0 ? "Không giới hạn" : a.ad_trust_dsl ?? "",
        a.threshold ?? "", a.spend_cap ?? "", a.funding_source_summary || "", a.user_role ? ROLE_VI[a.user_role] || a.user_role : "",
        a.timezone_name || "", fmtDate(a.created_time), a.pixel_count ?? "", a.via_profile_name || "",
      ].map(csvCell).join(","));
      const blob = new Blob(["﻿" + [header.join(","), ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `ads-check-${new Date().toISOString().slice(0, 10)}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không xuất được CSV");
    } finally {
      setExporting(false);
    }
  }

  function copy(text: string) {
    void navigator.clipboard?.writeText(text);
    setCopied(text);
    setTimeout(() => setCopied(null), 1200);
  }

  const items = (data?.items || []) as unknown[];
  const rowCount = tab === "pixel" ? pixels.length : data?.total_count || 0;

  return (
    <div className="ac-root">
      <section className="ac-hero">
        <div>
          <span className="ac-hero-badge"><MonoIcon name="shield" /> Graph API chính thức · token OAuth của VIA</span>
          <h1><MonoIcon name="shield" /> ADS CHECK</h1>
          <p>Quét tài khoản quảng cáo (cá nhân &amp; BM), Business Manager, Fanpage và Pixel của từng VIA đã cấp quyền Facebook.</p>
        </div>
        <div className="ac-hero-actions">
          <button className="ac-hero-btn ac-hero-btn-primary" onClick={() => setScanOpen((v) => !v)}>
            <MonoIcon name="sync" /> Quét tài sản
          </button>
          <button className="ac-hero-btn" onClick={() => void exportCsv()} disabled={exporting}>
            <MonoIcon name="export" /> {exporting ? "Đang xuất..." : "Xuất CSV"}
          </button>
        </div>
      </section>

      {scanOpen && (
        <section className="ac-panel ac-scan">
          <div className="ac-scan-head">
            <div>
              <h3>Quét tài sản Meta</h3>
              <p>Lấy dữ liệu mới nhất từ Meta cho VIA đã cấp quyền. Lỗi ở VIA nào thì dữ liệu cũ của VIA đó được giữ nguyên.</p>
            </div>
            <div className="ac-scan-actions">
              <select className="ac-select" value={scanTarget} onChange={(e) => setScanTarget(e.target.value)} disabled={scanning}>
                <option value="all">Tất cả VIA đã cấp quyền ({authorizedVias.length})</option>
                {authorizedVias.map((v) => (
                  <option key={v.id} value={String(v.id)}>{v.profile_name || v.uid}{v.meta_user_name ? ` · ${v.meta_user_name}` : ""}</option>
                ))}
              </select>
              <button className="ac-btn-primary" onClick={() => void runScan()} disabled={scanning || authorizedVias.length === 0}>
                {scanning ? "Đang quét..." : "Bắt đầu quét"}
              </button>
            </div>
          </div>
          {authorizedVias.length === 0 && (
            <p className="ac-scan-note">Chưa có VIA nào cấp quyền. Vào <a href="/vias">Dàn VIA</a> → <b>Cấp quyền Facebook</b> trước khi quét.</p>
          )}
          {scanRows.length > 0 && (
            <ul className="ac-progress">
              {scanRows.map((r) => (
                <li key={r.via.id} className={`ac-progress-row ${r.state}`}>
                  <span className="ac-progress-dot" aria-hidden="true" />
                  <div className="ac-progress-main">
                    <b>{r.via.profile_name || r.via.uid}</b>
                    {r.state === "wait" && <span className="ac-muted">Đang chờ</span>}
                    {r.state === "run" && <span className="ac-muted">Đang quét TKQC, BM, Page, Pixel...</span>}
                    {r.state === "done" && r.result?.counts && (
                      <span>
                        {r.result.counts.accounts} TKQC ({r.result.counts.live} live · {r.result.counts.die} die) · {r.result.counts.bms} BM ·{" "}
                        {r.result.counts.pages} Page · {r.result.counts.pixels} Pixel
                      </span>
                    )}
                    {r.state === "fail" && <span className="ac-error-text">{r.result?.error}</span>}
                    {r.result?.warnings && r.result.warnings.length > 0 && (
                      <details className="ac-warn-details">
                        <summary>{r.result.warnings.length} cảnh báo từ Meta</summary>
                        <ul>{r.result.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
                      </details>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section className="ac-stats">
        <div className="ac-stat">
          <div className="ac-stat-icon i1"><MonoIcon name="account" /></div>
          <div>
            <div className="ac-stat-label">Tài khoản</div>
            <div className="ac-stat-value">{nf.format(summary.total_accounts_count || 0)}</div>
            <div className="ac-stat-sub">{summary.label || "Chưa có dữ liệu — hãy Quét tài sản"}</div>
          </div>
        </div>
        <div className="ac-stat">
          <div className="ac-stat-icon i2"><MonoIcon name="dashboard" /></div>
          <div>
            <div className="ac-stat-label">Tổng số dư</div>
            <div className="ac-stat-value">{nf.format(summary.total_balance || 0)}</div>
            <div className="ac-stat-sub">{summary.primary_currency}{extraCurrencies.length ? ` · +${extraCurrencies.length} loại tiền khác` : ""}</div>
          </div>
        </div>
        <div className="ac-stat">
          <div className="ac-stat-icon i3"><MonoIcon name="analytics" /></div>
          <div>
            <div className="ac-stat-label">Tổng đã tiêu</div>
            <div className="ac-stat-value">{nf.format(summary.total_spend || 0)}</div>
            <div className="ac-stat-sub">{summary.primary_currency} · không cộng chéo tiền tệ</div>
          </div>
        </div>
        <div className="ac-stat">
          <div className="ac-stat-icon i4"><MonoIcon name="shield" /></div>
          <div>
            <div className="ac-stat-label">Tổng limit/ngày</div>
            <div className="ac-stat-value">{nf.format(summary.total_limit || 0)}</div>
            <div className="ac-stat-sub">{summary.primary_currency}</div>
          </div>
        </div>
      </section>

      <section className="ac-panel">
        <div className="ac-toolbar">
          <div className="ac-tabs" role="tablist">
            {TABS.map((t) => (
              <button key={t.key} role="tab" aria-selected={tab === t.key} className={`ac-tab ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
                <MonoIcon name={t.icon} /> {t.label}
                {tab === t.key && !loading ? <span className="ac-pill-count">{rowCount}</span> : null}
              </button>
            ))}
          </div>
          <div className="ac-filters">
            <select className="ac-select" value={viaId} onChange={(e) => setViaId(e.target.value)} aria-label="Lọc theo VIA">
              <option value="">Tất cả VIA</option>
              {vias.map((v) => <option key={v.id} value={String(v.id)}>{v.profile_name || v.uid}</option>)}
            </select>
            {tab === "accounts" && (
              <>
                <select className="ac-select" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Lọc trạng thái">
                  <option value="">Mọi trạng thái</option>
                  <option value="LIVE">Hoạt động</option>
                  <option value="DIE">Vô hiệu hóa</option>
                  <option value="UNSETTLED">Nợ / Chưa thanh toán</option>
                  <option value="IN_REVIEW">Đang xét duyệt</option>
                </select>
                <select className="ac-select" value={accountType} onChange={(e) => setAccountType(e.target.value)} aria-label="Lọc loại tài khoản">
                  <option value="">Cá nhân &amp; BM</option>
                  <option value="PERSONAL">Cá nhân</option>
                  <option value="BM">Thuộc BM</option>
                </select>
              </>
            )}
            <label className="ac-searchbox">
              <MonoIcon name="search" />
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Tìm theo ID, tên..." aria-label="Tìm kiếm" />
            </label>
          </div>
        </div>

        {error && <div className="ac-error">{error}</div>}

        <div className="ac-table-wrap">
          {loading ? (
            <div className="ac-loading">Đang tải dữ liệu...</div>
          ) : rowCount === 0 ? (
            <div className="ac-empty">
              <MonoIcon name="shield" />
              <h3>Chưa có dữ liệu</h3>
              <p>
                {authorizedVias.length === 0
                  ? "Chưa có VIA nào cấp quyền Facebook. Vào Dàn VIA → Cấp quyền Facebook, rồi quay lại bấm Quét tài sản."
                  : "Bấm Quét tài sản để lấy dữ liệu mới nhất từ Meta, hoặc thử bỏ bớt bộ lọc."}
              </p>
            </div>
          ) : tab === "accounts" ? (
            <table className="ac-table">
              <thead>
                <tr>
                  <th>Trạng thái</th><th>Tài khoản</th><th>Loại / BM</th><th>Số dư</th><th>Đã tiêu</th><th>Limit/ngày</th>
                  <th>Ngưỡng</th><th>Spend cap</th><th>Thẻ</th><th>Quyền</th><th>Múi giờ</th><th>Ngày tạo</th><th>Pixel</th><th>VIA</th>
                </tr>
              </thead>
              <tbody>
                {(items as Account[]).map((a) => {
                  const st = accountStatus(a);
                  const reason = a.disable_reason && a.disable_reason !== "NONE" ? DISABLE_REASON_VI[a.disable_reason] || a.disable_reason : null;
                  return (
                    <tr key={a.id}>
                      <td>
                        <span className={`ac-status ${st.cls}`}>{st.label}</span>
                        {reason && <div className="ac-sub ac-error-text">{reason}</div>}
                      </td>
                      <td>
                        <div className="ac-acct">
                          <span className="ac-acct-name">{a.name}</span>
                          <span className="ac-acct-id">
                            act_{a.act_id}
                            <button onClick={() => copy(a.act_id)} aria-label="Sao chép ID" title="Sao chép ID"><MonoIcon name={copied === a.act_id ? "check" : "copy"} /></button>
                          </span>
                        </div>
                      </td>
                      <td>
                        {a.account_type === "BM" ? (
                          <><span className="ac-chip assigned">BM</span><div className="ac-sub">{a.business_name || a.bm_id}</div></>
                        ) : <span className="ac-chip">Cá nhân</span>}
                      </td>
                      <td><Money value={a.balance} currency={a.currency} /></td>
                      <td><Money value={a.amount_spent ?? a.total_spend} currency={a.currency} /></td>
                      <td>{limitText(a)}</td>
                      <td><Money value={a.threshold} currency={a.currency} /></td>
                      <td>{a.spend_cap ? <Money value={a.spend_cap} currency={a.currency} /> : <span className="ac-muted">Không đặt</span>}</td>
                      <td className="ac-mono">{a.funding_source_summary || "—"}</td>
                      <td>{a.user_role ? ROLE_VI[a.user_role] || a.user_role : "—"}</td>
                      <td className="ac-mono">{a.timezone_name || "—"}</td>
                      <td>{fmtDate(a.created_time)}</td>
                      <td>{a.pixel_count ?? 0}</td>
                      <td className="ac-sub">{a.via_profile_name || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : tab === "bm" ? (
            <table className="ac-table">
              <thead><tr><th>Business Manager</th><th>Xác minh</th><th>Năm tạo</th><th>Số TKQC</th><th>VIA</th></tr></thead>
              <tbody>
                {(items as SyncedBM[]).map((b) => (
                  <tr key={b.id}>
                    <td>
                      <div className="ac-acct">
                        <span className="ac-acct-name">{b.name}</span>
                        <span className="ac-acct-id">{b.bm_id}<button onClick={() => copy(b.bm_id)} aria-label="Sao chép ID"><MonoIcon name={copied === b.bm_id ? "check" : "copy"} /></button></span>
                      </div>
                    </td>
                    <td>
                      {String(b.verified_status || "").toLowerCase() === "verified"
                        ? <span className="ac-status ok">Đã xác minh</span>
                        : <span className="ac-status idle">{b.verified_status ? "Chưa xác minh" : "—"}</span>}
                    </td>
                    <td>{b.created_year || "—"}</td>
                    <td>{b.ad_account_count}</td>
                    <td className="ac-sub">{b.via_profile_name || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : tab === "page" ? (
            <table className="ac-table">
              <thead><tr><th>Fanpage</th><th>Danh mục</th><th>Lượt thích</th><th>Người theo dõi</th><th>VIA</th></tr></thead>
              <tbody>
                {(items as SyncedPageItem[]).map((p) => (
                  <tr key={p.id}>
                    <td>
                      <div className="ac-acct">
                        <span className="ac-acct-name">{p.name}</span>
                        <span className="ac-acct-id">{p.page_id}<button onClick={() => copy(p.page_id)} aria-label="Sao chép ID"><MonoIcon name={copied === p.page_id ? "check" : "copy"} /></button></span>
                      </div>
                    </td>
                    <td>{p.category || "—"}</td>
                    <td>{nf.format(p.likes_count || 0)}</td>
                    <td>{nf.format(p.followers_count || 0)}</td>
                    <td className="ac-sub">{p.via_profile_name || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table className="ac-table">
              <thead><tr><th>Pixel</th><th>Lần bắn gần nhất</th><th>Tình trạng</th><th>TKQC dùng pixel</th><th>Ngày tạo</th></tr></thead>
              <tbody>
                {pixels.map((px) => {
                  const days = px.last_fired_time ? (Date.now() - new Date(px.last_fired_time).getTime()) / 86400000 : null;
                  const state = px.is_unavailable ? { cls: "bad", label: "Không khả dụng" }
                    : days === null ? { cls: "idle", label: "Chưa bắn sự kiện" }
                    : days <= 7 ? { cls: "ok", label: "Đang hoạt động" } : { cls: "warn", label: "Lâu không bắn" };
                  return (
                    <tr key={px.pixel_id}>
                      <td>
                        <div className="ac-acct">
                          <span className="ac-acct-name">{px.name || "Pixel"}</span>
                          <span className="ac-acct-id">{px.pixel_id}<button onClick={() => copy(px.pixel_id)} aria-label="Sao chép ID"><MonoIcon name={copied === px.pixel_id ? "check" : "copy"} /></button></span>
                        </div>
                      </td>
                      <td>{relTime(px.last_fired_time)}</td>
                      <td><span className={`ac-status ${state.cls}`}>{state.label}</span></td>
                      <td>
                        <b>{px.accounts.length}</b>
                        <div className="ac-sub">{px.accounts.slice(0, 3).map((a) => a.name || `act_${a.act_id}`).join(", ")}{px.accounts.length > 3 ? ` +${px.accounts.length - 3}` : ""}</div>
                      </td>
                      <td>{fmtDate(px.creation_time)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {tab !== "pixel" && rowCount > 0 && (
          <div className="ac-footer">
            <span>Trang {page}/{totalPages} · {nf.format(data?.total_count || 0)} dòng</span>
            <div className="ac-pager">
              <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} aria-label="Trang trước"><MonoIcon name="chevron-left" /></button>
              <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages} aria-label="Trang sau"><MonoIcon name="chevron-right" /></button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
