"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AdsCheckResponse,
  AdsCheckSummary,
  getAdsCheckData,
  getVias,
  SyncedAdAccount,
  SyncedBM,
  SyncedPageItem,
  ViaProfile,
} from "../../lib/api";
import { MonoIcon } from "../../components/mono-icon";
import "./adscheck.css";

type Tab = "personal" | "bm" | "page";

const TABS: { key: Tab; label: string; icon: Parameters<typeof MonoIcon>[0]["name"] }[] = [
  { key: "personal", label: "Tài khoản quảng cáo", icon: "account" },
  { key: "bm", label: "Business Manager", icon: "business" },
  { key: "page", label: "Fanpage", icon: "customer" },
];

const EMPTY_SUMMARY: AdsCheckSummary = {
  total_accounts_count: 0,
  total_balance: 0,
  total_threshold: 0,
  total_limit: 0,
  total_spend: 0,
  primary_currency: "USD",
  label: "",
};

function money(v: number, cur: string) {
  const n = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(v || 0);
  return (
    <span className="ac-money">
      {n} <small>{cur}</small>
    </span>
  );
}

function AccountStatus({ dot, reason }: { dot: string; reason?: string }) {
  if (dot === "LIVE") return <span className="ac-status ok">Hoạt động</span>;
  if (dot === "DIE") return <span className="ac-status bad" title={reason}>Vô hiệu hóa</span>;
  if (dot === "WARNING") return <span className="ac-status warn" title={reason}>Cảnh báo</span>;
  return <span className="ac-status idle">Chưa rõ</span>;
}

export default function AdsCheckProPage() {
  const [tab, setTab] = useState<Tab>("personal");
  const [data, setData] = useState<AdsCheckResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [vias, setVias] = useState<ViaProfile[]>([]);
  const [viaId, setViaId] = useState<string>("");
  const [status, setStatus] = useState<string>("");
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [page, setPage] = useState(1);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    getVias().then((r) => setVias(r.vias || [])).catch(() => {});
  }, []);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 350);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => setPage(1), [tab, viaId, status, debounced]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getAdsCheckData({
        tab,
        via_id: viaId ? Number(viaId) : undefined,
        status_filter: status || undefined,
        search: debounced || undefined,
        page,
        page_size: 25,
      });
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không tải được dữ liệu ADS CHECK.");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [tab, viaId, status, debounced, page]);

  useEffect(() => {
    void load();
  }, [load]);

  const summary = data?.summary || EMPTY_SUMMARY;
  const cur = summary.primary_currency || "USD";
  const items = data?.items || [];

  const copy = (text: string, key: string) => {
    void navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 1400);
  };

  const stats = useMemo(
    () => [
      { icon: "account", cls: "i1", label: "Tài khoản", value: String(summary.total_accounts_count), sub: data?.total_count ? `${data.total_count} mục` : "" },
      { icon: "dashboard", cls: "i2", label: "Tổng số dư", value: new Intl.NumberFormat("vi-VN").format(summary.total_balance || 0), sub: cur },
      { icon: "analytics", cls: "i3", label: "Tổng chi tiêu", value: new Intl.NumberFormat("vi-VN").format(summary.total_spend || 0), sub: cur },
      { icon: "campaign", cls: "i4", label: "Tổng hạn mức", value: new Intl.NumberFormat("vi-VN").format(summary.total_limit || 0), sub: cur },
    ] as const,
    [summary, cur, data?.total_count],
  );

  return (
    <div className="ac-root">
      <div className="ac-hero">
        <div>
          <h1>
            <MonoIcon name="shield" style={{ width: 26, height: 26 }} /> ADS CHECK
          </h1>
          <p>Kiểm tra tài khoản quảng cáo, Business Manager và Fanpage của từng VIA — dữ liệu lấy trực tiếp từ Graph API chính thức của Meta.</p>
          <span className="ac-hero-badge" style={{ marginTop: 12 }}>
            <MonoIcon name="link" /> {data?.system_status || "Đang kết nối"}
          </span>
        </div>
        <div className="ac-hero-actions">
          <button className="ac-hero-btn" onClick={() => void load()}>
            <MonoIcon name="refresh" /> Làm mới
          </button>
        </div>
      </div>

      <div className="ac-stats">
        {stats.map((s) => (
          <div className="ac-stat" key={s.label}>
            <div className={`ac-stat-icon ${s.cls}`}>
              <MonoIcon name={s.icon} />
            </div>
            <div>
              <div className="ac-stat-label">{s.label}</div>
              <div className="ac-stat-value">{s.value}</div>
              {s.sub && <div className="ac-stat-sub">{s.sub}</div>}
            </div>
          </div>
        ))}
      </div>

      <div className="ac-panel">
        <div className="ac-toolbar">
          <div className="ac-tabs">
            {TABS.map((t) => (
              <button key={t.key} className={`ac-tab ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
                <MonoIcon name={t.icon} />
                {t.label}
                {tab === t.key && data ? <span className="ac-pill-count">{data.total_count}</span> : null}
              </button>
            ))}
          </div>
          <div className="ac-filters">
            <select className="ac-select" value={viaId} onChange={(e) => setViaId(e.target.value)}>
              <option value="">Tất cả VIA</option>
              {vias.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.profile_name} · {v.uid}
                </option>
              ))}
            </select>
            {tab === "personal" && (
              <select className="ac-select" value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">Mọi trạng thái</option>
                <option value="LIVE">Hoạt động</option>
                <option value="DIE">Vô hiệu hóa</option>
                <option value="WARNING">Cảnh báo</option>
              </select>
            )}
            <div className="ac-searchbox">
              <MonoIcon name="search" />
              <input placeholder="Tìm ID, tên..." value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
          </div>
        </div>

        {loading ? (
          <div className="ac-loading">Đang tải dữ liệu...</div>
        ) : error ? (
          <div className="ac-empty">
            <MonoIcon name="close" />
            <h3>Không tải được dữ liệu</h3>
            <p>{error}</p>
          </div>
        ) : items.length === 0 ? (
          <div className="ac-empty">
            <MonoIcon name="shield" />
            <h3>Chưa có dữ liệu</h3>
            <p>Cấp quyền Facebook cho VIA trong mục Dàn VIA rồi bấm Đồng bộ để kéo tài khoản quảng cáo, BM và Fanpage về đây.</p>
          </div>
        ) : (
          <div className="ac-table-wrap">
            {tab === "personal" && (
              <table className="ac-table">
                <thead>
                  <tr>
                    <th>Tài khoản</th>
                    <th>Trạng thái</th>
                    <th>Số dư</th>
                    <th>Đã chi tiêu</th>
                    <th>Hạn mức</th>
                    <th>Thẻ</th>
                    <th>VIA</th>
                    <th>Khách</th>
                  </tr>
                </thead>
                <tbody>
                  {(items as SyncedAdAccount[]).map((a) => (
                    <tr key={a.id}>
                      <td>
                        <div className="ac-acct">
                          <span className="ac-acct-name">{a.name || "(không tên)"}</span>
                          <span className="ac-acct-id">
                            {a.act_id}
                            <button onClick={() => copy(a.act_id, `act-${a.id}`)} title="Sao chép">
                              <MonoIcon name={copied === `act-${a.id}` ? "check" : "copy"} />
                            </button>
                          </span>
                        </div>
                      </td>
                      <td><AccountStatus dot={a.status_dot} reason={a.disable_reason} /></td>
                      <td>{money(a.balance, a.currency || cur)}</td>
                      <td>{money(a.total_spend, a.currency || cur)}</td>
                      <td>{money(a.threshold || a.hidden_limit || 0, a.currency || cur)}</td>
                      <td><span className="ac-mono">{a.card_display || "—"}</span></td>
                      <td><span className="ac-mono">{a.via_uid || "—"}</span></td>
                      <td>
                        {a.is_assigned && a.customer_name ? (
                          <span className="ac-chip assigned">{a.customer_name}</span>
                        ) : (
                          <span className="ac-chip">Chưa gán</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {tab === "bm" && (
              <table className="ac-table">
                <thead>
                  <tr>
                    <th>Business Manager</th>
                    <th>Xác minh</th>
                    <th>TKQC</th>
                    <th>Page</th>
                    <th>Admin</th>
                    <th>VIA</th>
                  </tr>
                </thead>
                <tbody>
                  {(items as SyncedBM[]).map((b) => (
                    <tr key={b.id}>
                      <td>
                        <div className="ac-acct">
                          <span className="ac-acct-name">{b.name}</span>
                          <span className="ac-acct-id">
                            {b.bm_id}
                            <button onClick={() => copy(b.bm_id, `bm-${b.id}`)} title="Sao chép">
                              <MonoIcon name={copied === `bm-${b.id}` ? "check" : "copy"} />
                            </button>
                          </span>
                        </div>
                      </td>
                      <td>
                        {b.verified_status === "verified" ? (
                          <span className="ac-status ok">Đã xác minh</span>
                        ) : (
                          <span className="ac-status idle">{b.verified_status || "Chưa xác minh"}</span>
                        )}
                      </td>
                      <td>{b.ad_account_count}</td>
                      <td>{b.page_count}</td>
                      <td>{b.admin_count ?? "—"}</td>
                      <td><span className="ac-mono">{b.via_uid || "—"}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {tab === "page" && (
              <table className="ac-table">
                <thead>
                  <tr>
                    <th>Fanpage</th>
                    <th>Danh mục</th>
                    <th>Lượt thích</th>
                    <th>Theo dõi</th>
                    <th>Trạng thái</th>
                    <th>VIA</th>
                  </tr>
                </thead>
                <tbody>
                  {(items as SyncedPageItem[]).map((p) => (
                    <tr key={p.id}>
                      <td>
                        <div className="ac-acct">
                          <span className="ac-acct-name">{p.name}</span>
                          <span className="ac-acct-id">
                            {p.page_id}
                            <button onClick={() => copy(p.page_id, `pg-${p.id}`)} title="Sao chép">
                              <MonoIcon name={copied === `pg-${p.id}` ? "check" : "copy"} />
                            </button>
                          </span>
                        </div>
                      </td>
                      <td>{p.category || "—"}</td>
                      <td>{new Intl.NumberFormat("vi-VN").format(p.likes_count || 0)}</td>
                      <td>{new Intl.NumberFormat("vi-VN").format(p.followers_count || 0)}</td>
                      <td>{p.is_published ? <span className="ac-status ok">Đã xuất bản</span> : <span className="ac-status idle">Nháp</span>}</td>
                      <td><span className="ac-mono">{p.via_uid || "—"}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {data && data.total_pages > 1 && (
          <div className="ac-footer">
            <span>
              Trang {data.page}/{data.total_pages} · {data.total_count} mục
            </span>
            <div className="ac-pager">
              <button disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                <MonoIcon name="chevron-left" />
              </button>
              <button disabled={page >= data.total_pages} onClick={() => setPage((p) => p + 1)}>
                <MonoIcon name="chevron-right" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
