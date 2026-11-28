"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  checkViaLive,
  checkViasLiveBulk,
  deleteVia,
  fetchJson,
  forceSyncAllViaAssets,
  getSyncedBMs,
  getVia2FA,
  getVias,
  syncViaAssets,
  SyncedBM,
  togglePrimaryRentalBM,
  updateViaInfo,
  updateViaProxy,
  ViaProfile,
  ViaStats,
} from "../../lib/api";
import ExtensionManagerModal from "@/components/ExtensionManagerModal";
import AutoSetCampModal from "@/components/AutoSetCampModal";
import RawViaImportModal from "@/components/RawViaImportModal";
import CreateViaModal from "@/components/CreateViaModal";
import { MonoIcon } from "@/components/mono-icon";

const EMPTY_STATS: ViaStats = {
  total_vias: 0,
  live_count: 0,
  die_count: 0,
  unknown_count: 0,
  active_tokens: 0,
  checkpoint_tokens: 0,
  total_bms: 0,
  primary_bms: 0,
  total_ad_accounts: 0,
  total_pages: 0,
};

// Lý do lỗi do backend trả về qua ?oauth_error= sau khi Meta redirect lại
const OAUTH_ERRORS: Record<string, string> = {
  access_denied: "Bạn đã hủy cấp quyền Meta. Dữ liệu VIA không thay đổi.",
  uid_mismatch:
    "VIA này đã liên kết với một tài khoản Facebook khác lúc cấp quyền lần đầu. Hãy đăng nhập đúng tài khoản đó rồi thử lại. Token không được lưu.",
  account_linked_elsewhere:
    "Tài khoản Facebook vừa đăng nhập đã được liên kết với một VIA khác. Mỗi tài khoản Facebook chỉ gắn với một VIA. Token không được lưu.",
  missing_code: "Meta không trả mã cấp quyền. Vui lòng thử lại.",
  meta_error: "Meta báo lỗi khi cấp quyền. Kiểm tra App Roles và Valid OAuth Redirect URIs trong ứng dụng Meta.",
  via_not_found: "Không tìm thấy VIA cần cấp quyền (có thể đã bị xóa).",
  token_exchange_failed:
    "Không đổi được mã lấy token. Kiểm tra FACEBOOK_APP_SECRET và FACEBOOK_REDIRECT_URI trên server.",
  secure_storage_failed: "Không lưu được token mã hóa trên server. Kiểm tra khóa mã hóa của backend.",
};

type Feedback = { text: string; error?: boolean } | null;
type RowMenu = { via: ViaProfile; top: number; left: number } | null;

function TokenStatus({ status }: { status: string }) {
  if (status === "ACTIVE") return <span className="status ok">Đã cấp quyền</span>;
  if (status === "EXPIRED") return <span className="status bad">Token hết hạn</span>;
  if (status === "CHECKPOINT") return <span className="status warn">Checkpoint</span>;
  return <span className="status idle">Chưa cấp quyền</span>;
}

function LiveStatus({ status }: { status: string }) {
  if (status === "LIVE") return <span className="status ok">LIVE</span>;
  if (status === "DIE") return <span className="status bad">DIE</span>;
  return <span className="status idle">Chưa kiểm tra</span>;
}

export default function ViasFarmPage() {
  const [activeTab, setActiveTab] = useState<"vias" | "bms">("vias");
  const [vias, setVias] = useState<ViaProfile[]>([]);
  const [syncedBms, setSyncedBms] = useState<SyncedBM[]>([]);
  const [stats, setStats] = useState<ViaStats>(EMPTY_STATS);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [feedback, setFeedback] = useState<Feedback>(null);

  // Modal & menu
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [showExtensionModal, setShowExtensionModal] = useState(false);
  const [showSetCampModal, setShowSetCampModal] = useState(false);
  const [targetSetCampViaId, setTargetSetCampViaId] = useState<number | undefined>(undefined);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [rowMenu, setRowMenu] = useState<RowMenu>(null);

  // Proxy modal
  const [proxyModalVia, setProxyModalVia] = useState<ViaProfile | null>(null);
  const [proxyInput, setProxyInput] = useState("");
  const [isSavingProxy, setIsSavingProxy] = useState(false);

  // Trạng thái thao tác
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null);
  const [bulkChecking, setBulkChecking] = useState(false);
  const [syncingAll, setSyncingAll] = useState(false);

  // Sửa tên & ghi chú inline
  const [editingViaId, setEditingViaId] = useState<number | null>(null);
  const [editProfileName, setEditProfileName] = useState("");
  const [editNote, setEditNote] = useState("");
  const [isSavingEdit, setIsSavingEdit] = useState(false);

  // OTP & hydration
  const [isMounted, setIsMounted] = useState(false);
  const [otpCountdowns, setOtpCountdowns] = useState<Record<number, { code: string; rem: number }>>({});
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Đọc kết quả OAuth sau khi Meta redirect về /vias
  useEffect(() => {
    setIsMounted(true);
    const params = new URLSearchParams(window.location.search);
    const query = params.get("q");
    if (query) setSearch(query);
    if (params.get("success") === "true") {
      setFeedback({ text: "Cấp quyền Facebook thành công. Token đã được lưu mã hóa — bấm Đồng bộ để kéo BM, TKQC, Fanpage." });
      window.history.replaceState({}, "", "/vias");
    } else if (params.get("success") === "false") {
      const reason = params.get("oauth_error") || "";
      setFeedback({
        text: OAUTH_ERRORS[reason] || "Không thể hoàn tất cấp quyền Meta. Token cũ được giữ nguyên.",
        error: true,
      });
      window.history.replaceState({}, "", "/vias");
    }
  }, []);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [viaRes, bmRes] = await Promise.all([getVias(), getSyncedBMs()]);
      setVias(viaRes.vias || []);
      setStats(viaRes.stats || EMPTY_STATS);
      setSyncedBms(bmRes.bms || []);
      const otps: Record<number, { code: string; rem: number }> = {};
      (viaRes.vias || []).forEach((v) => {
        if (v.live_2fa?.code) otps[v.id] = { code: v.live_2fa.code, rem: v.live_2fa.remaining_seconds || 30 };
      });
      setOtpCountdowns(otps);
    } catch (err: unknown) {
      setFeedback({ text: err instanceof Error ? err.message : "Lỗi khi tải dữ liệu dàn VIA.", error: true });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // Đếm ngược OTP, hết chu kỳ thì lấy mã mới
  useEffect(() => {
    const timer = setInterval(() => {
      setOtpCountdowns((prev) => {
        const next: Record<number, { code: string; rem: number }> = {};
        let needsFetch = false;
        Object.entries(prev).forEach(([key, val]) => {
          const id = Number(key);
          if (val.rem > 1) next[id] = { code: val.code, rem: val.rem - 1 };
          else {
            next[id] = { code: val.code, rem: 30 };
            needsFetch = true;
          }
        });
        if (needsFetch) {
          vias.forEach((v) => {
            if (!v.has_2fa) return;
            getVia2FA(v.id)
              .then((res) => {
                if (res.code) setOtpCountdowns((cur) => ({ ...cur, [v.id]: { code: res.code, rem: res.remaining_seconds || 30 } }));
              })
              .catch(() => {});
          });
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [vias]);

  // Đóng menu khi bấm ra ngoài / cuộn
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (!(e.target as HTMLElement).closest(".menu-wrap")) {
        setToolsOpen(false);
        setRowMenu(null);
      }
    };
    const onScroll = () => setRowMenu(null);
    document.addEventListener("mousedown", onDown);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  const copyToClipboard = (text: string, keyName: string, toastText?: string) => {
    if (!text) return;
    void navigator.clipboard.writeText(text);
    setCopiedKey(keyName);
    if (toastText) setFeedback({ text: toastText });
    setTimeout(() => setCopiedKey(null), 1500);
  };

  const fail = (err: unknown, fallback: string) =>
    setFeedback({ text: err instanceof Error ? err.message : fallback, error: true });

  const handleCheckLive = async (via: ViaProfile) => {
    try {
      setActionLoadingId(via.id);
      const res = await checkViaLive(via.id);
      setVias((prev) =>
        prev.map((v) => (v.id === via.id ? { ...v, uid_live_status: res.uid_live_status, last_live_check_at: res.last_live_check_at } : v)),
      );
      setFeedback({ text: `UID ${via.uid}: ${res.uid_live_status}` });
    } catch (err) {
      fail(err, "Lỗi khi kiểm tra Live UID.");
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleBulkCheckLive = async () => {
    try {
      setBulkChecking(true);
      setFeedback({ text: "Đang kiểm tra Live/Die toàn bộ dàn VIA..." });
      const res = await checkViasLiveBulk();
      setFeedback({ text: `Đã kiểm tra ${res.total_checked} VIA — ${res.live_count} LIVE, ${res.die_count} DIE.` });
      await loadData();
    } catch (err) {
      fail(err, "Lỗi khi kiểm tra Live hàng loạt.");
    } finally {
      setBulkChecking(false);
    }
  };

  const handleForceSyncAll = async () => {
    try {
      setSyncingAll(true);
      const res = await forceSyncAllViaAssets();
      setFeedback({ text: res.message });
      window.setTimeout(() => void loadData(), 1500);
    } catch (err) {
      fail(err, "Không thể khởi chạy đồng bộ toàn bộ VIA.");
    } finally {
      setSyncingAll(false);
    }
  };

  const formatTime = (value: string | null, withDate = true) => {
    if (!value || !isMounted) return null;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return null;
    return new Intl.DateTimeFormat("vi-VN", {
      ...(withDate ? { dateStyle: "short" } : {}),
      timeStyle: "short",
      timeZone: "Asia/Ho_Chi_Minh",
    }).format(date);
  };

  const handleSyncAssets = async (via: ViaProfile) => {
    try {
      setActionLoadingId(via.id);
      const res = await syncViaAssets(via.id);
      setFeedback({ text: res.message });
      await loadData();
    } catch (err) {
      fail(err, "Lỗi đồng bộ tài sản.");
    } finally {
      setActionLoadingId(null);
    }
  };

  // Luồng OAuth 2.0 chính thức của Meta
  const handleMetaOAuth = async (via: ViaProfile) => {
    try {
      setActionLoadingId(via.id);
      const result = await fetchJson<{ authorization_url: string }>(
        `/oauth/facebook/login?via_id=${encodeURIComponent(via.id)}`,
      );
      window.location.assign(result.authorization_url);
    } catch (err) {
      fail(err, "Không thể bắt đầu cấp quyền Facebook.");
      setActionLoadingId(null);
    }
  };

  const handleDeleteVia = async (via: ViaProfile) => {
    if (!confirm(`Xóa VIA #${via.id} (${via.uid}) khỏi hệ thống?`)) return;
    try {
      await deleteVia(via.id);
      setFeedback({ text: `Đã xóa VIA ${via.uid}` });
      setVias((prev) => prev.filter((v) => v.id !== via.id));
    } catch (err) {
      fail(err, "Lỗi xóa VIA.");
    }
  };

  const handleTogglePrimaryBM = async (bm: SyncedBM) => {
    try {
      const res = await togglePrimaryRentalBM(bm.bm_id, !bm.is_primary_rental);
      setFeedback({ text: res.message });
      setSyncedBms((prev) => prev.map((b) => (b.bm_id === bm.bm_id ? res.bm : b)));
    } catch (err) {
      fail(err, "Lỗi gắn cờ BM.");
    }
  };

  const handleSaveProxy = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!proxyModalVia) return;
    try {
      setIsSavingProxy(true);
      const res = await updateViaProxy(proxyModalVia.id, proxyInput);
      setFeedback({ text: res.message });
      setVias((prev) => prev.map((v) => (v.id === proxyModalVia.id ? res.via : v)));
      setProxyModalVia(null);
    } catch (err) {
      fail(err, "Lỗi lưu proxy.");
    } finally {
      setIsSavingProxy(false);
    }
  };

  const startEditingVia = (via: ViaProfile) => {
    setEditingViaId(via.id);
    setEditProfileName(via.profile_name || "");
    setEditNote(via.note || "");
  };

  const cancelEditingVia = () => {
    setEditingViaId(null);
    setEditProfileName("");
    setEditNote("");
  };

  const handleSaveViaInfo = async (viaId: number) => {
    const cleanName = editProfileName.trim();
    if (!cleanName) {
      setFeedback({ text: "Tên hồ sơ không được để trống.", error: true });
      return;
    }
    try {
      setIsSavingEdit(true);
      const res = await updateViaInfo(viaId, { profile_name: cleanName, note: editNote.trim() || null });
      setVias((prev) => prev.map((v) => (v.id === viaId ? { ...v, profile_name: res.via.profile_name, note: res.via.note } : v)));
      setFeedback({ text: `Đã lưu thông tin VIA ${res.via.uid}` });
      cancelEditingVia();
    } catch (err) {
      fail(err, "Lỗi khi cập nhật thông tin VIA.");
    } finally {
      setIsSavingEdit(false);
    }
  };

  const openRowMenu = (via: ViaProfile, e: React.MouseEvent<HTMLButtonElement>) => {
    if (rowMenu?.via.id === via.id) {
      setRowMenu(null);
      return;
    }
    const r = e.currentTarget.getBoundingClientRect();
    const width = 230;
    const left = Math.max(8, Math.min(r.right - width, window.innerWidth - width - 8));
    const openUp = r.bottom + 220 > window.innerHeight;
    setRowMenu({ via, left, top: openUp ? r.top - 214 : r.bottom + 6 });
  };

  const filteredVias = useMemo(() => {
    const q = search.trim().toLowerCase();
    return vias.filter((v) => {
      if (statusFilter === "LIVE" && v.uid_live_status !== "LIVE") return false;
      if (statusFilter === "DIE" && v.uid_live_status !== "DIE") return false;
      if (statusFilter === "ACTIVE_TOKEN" && v.token_status !== "ACTIVE") return false;
      if (statusFilter === "NO_TOKEN" && v.token_status === "ACTIVE") return false;
      if (statusFilter === "CHECKPOINT" && v.token_status !== "CHECKPOINT") return false;
      if (!q) return true;
      return (
        v.uid.toLowerCase().includes(q) ||
        v.profile_name.toLowerCase().includes(q) ||
        (v.email || "").toLowerCase().includes(q) ||
        (v.backup_email || "").toLowerCase().includes(q) ||
        (v.proxy?.display || "").toLowerCase().includes(q)
      );
    });
  }, [vias, statusFilter, search]);

  const isEmpty = !loading && vias.length === 0;
  const unauthorized = Math.max(0, stats.total_vias - stats.active_tokens);

  return (
    <div className="via-page">
      {/* Tiêu đề + thao tác chính */}
      <header className="page-heading">
        <div>
          <span className="eyebrow">Tài sản Meta</span>
          <h1>Dàn VIA</h1>
          <p>
            Tài khoản Facebook dùng để cấp quyền Meta qua OAuth chính thức, rồi đồng bộ Business Manager, tài khoản
            quảng cáo và Fanpage.
          </p>
        </div>
        <div className="page-actions">
          <button type="button" className="btn icon" onClick={() => void loadData()} title="Làm mới" aria-label="Làm mới">
            <MonoIcon name="refresh" />
          </button>
          <div className="menu-wrap">
            <button type="button" className="btn" onClick={() => setToolsOpen((v) => !v)} aria-expanded={toolsOpen}>
              Công cụ
              <MonoIcon name="chevron-down" />
            </button>
            {toolsOpen && (
              <div className="menu" role="menu">
                <button type="button" disabled={bulkChecking || vias.length === 0} onClick={() => { setToolsOpen(false); void handleBulkCheckLive(); }}>
                  <MonoIcon name="check" />
                  {bulkChecking ? "Đang kiểm tra..." : "Kiểm tra Live UID hàng loạt"}
                </button>
                <button type="button" disabled={syncingAll || vias.length === 0} onClick={() => { setToolsOpen(false); void handleForceSyncAll(); }}>
                  <MonoIcon name="sync" />
                  {syncingAll ? "Đang xếp lịch..." : "Đồng bộ tài sản tất cả VIA"}
                </button>
                <hr />
                <button type="button" onClick={() => { setToolsOpen(false); setTargetSetCampViaId(undefined); setShowSetCampModal(true); }}>
                  <MonoIcon name="campaign" />
                  Thiết lập chiến dịch từ xa
                </button>
                <Link href="/ads-check" onClick={() => setToolsOpen(false)}>
                  <MonoIcon name="account" />
                  Bảng ADSOS CHECK
                </Link>
                <button type="button" onClick={() => { setToolsOpen(false); setShowExtensionModal(true); }}>
                  <MonoIcon name="link" />
                  Tiện ích trình duyệt
                </button>
              </div>
            )}
          </div>
          <button type="button" className="btn" onClick={() => setShowImportModal(true)}>
            <MonoIcon name="upload" />
            Nhập hàng loạt
          </button>
          <button type="button" className="btn primary" onClick={() => setShowCreateModal(true)}>
            <MonoIcon name="plus" />
            Tạo VIA
          </button>
        </div>
      </header>

      {feedback && (
        <div className={`via-banner ${feedback.error ? "err" : "ok"}`} role="status">
          <span>{feedback.text}</span>
          <button type="button" onClick={() => setFeedback(null)} aria-label="Đóng thông báo">
            <MonoIcon name="close" />
          </button>
        </div>
      )}

      {isEmpty ? (
        /* Màn hướng dẫn khi chưa có VIA */
        <section className="via-onboard">
          <header>
            <h2>Chưa có VIA nào</h2>
            <p>Kết nối tài khoản Facebook đầu tiên để hệ thống đọc được BM, tài khoản quảng cáo và Fanpage bạn quản lý.</p>
          </header>
          <div className="via-steps">
            <div className="via-step">
              <b>1</b>
              <h3>Tạo VIA</h3>
              <p>Nhập UID của tài khoản Facebook. Mật khẩu không bắt buộc.</p>
            </div>
            <div className="via-step">
              <b>2</b>
              <h3>Cấp quyền Facebook</h3>
              <p>Đăng nhập qua hộp thoại chính thức của Meta và cho phép quyền đọc quảng cáo. Token được lưu mã hóa.</p>
            </div>
            <div className="via-step">
              <b>3</b>
              <h3>Đồng bộ tài sản</h3>
              <p>Bấm Đồng bộ để kéo Business Manager, tài khoản quảng cáo và Fanpage về hệ thống.</p>
            </div>
          </div>
          <div className="via-onboard-actions">
            <button type="button" className="btn primary" onClick={() => setShowCreateModal(true)}>
              <MonoIcon name="plus" />
              Tạo VIA đầu tiên
            </button>
            <button type="button" className="btn" onClick={() => setShowImportModal(true)}>
              <MonoIcon name="upload" />
              Nhập hàng loạt
            </button>
          </div>
          <p className="via-tip">
            Lấy UID: mở Graph API Explorer của Meta, chạy <code>me?fields=id</code> bằng đúng tài khoản sẽ cấp quyền. Tài
            khoản đăng nhập ở bước 2 phải trùng UID này, và phải được thêm vào App Roles của ứng dụng Meta khi ứng dụng
            còn ở chế độ Development.
          </p>
        </section>
      ) : (
        <>
          {/* Số liệu */}
          <section className="metric-grid">
            <div className="metric-card">
              <div className="metric-label">VIA</div>
              <div className="metric-value">{stats.total_vias}</div>
              <div className="via-metric-sub">
                <span className="status ok">{stats.live_count} LIVE</span>
                <span className="status bad">{stats.die_count} DIE</span>
                <span className="status idle">{stats.unknown_count} chưa kiểm tra</span>
              </div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Đã cấp quyền Meta</div>
              <div className="metric-value">{stats.active_tokens}</div>
              <div className="via-metric-sub">
                {unauthorized > 0 && <span className="status idle">{unauthorized} chưa cấp quyền</span>}
                {stats.checkpoint_tokens > 0 && <span className="status warn">{stats.checkpoint_tokens} checkpoint</span>}
              </div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Business Manager</div>
              <div className="metric-value">{stats.total_bms}</div>
              <div className="via-metric-sub">
                <span className="status idle">{stats.primary_bms} BM cho thuê</span>
              </div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Tài sản đã đồng bộ</div>
              <div className="metric-value">{stats.total_ad_accounts}</div>
              <div className="via-metric-sub">
                <span className="status idle">TKQC</span>
                <span className="status idle">{stats.total_pages} Fanpage</span>
              </div>
            </div>
          </section>

          <section className="panel">
            <div className="via-toolbar">
              <div className="segmented" role="tablist">
                <button type="button" role="tab" aria-selected={activeTab === "vias"} className={`btn ${activeTab === "vias" ? "active" : ""}`} onClick={() => setActiveTab("vias")}>
                  VIA <span className="count-badge">{filteredVias.length}</span>
                </button>
                <button type="button" role="tab" aria-selected={activeTab === "bms"} className={`btn ${activeTab === "bms" ? "active" : ""}`} onClick={() => setActiveTab("bms")}>
                  Business Manager <span className="count-badge">{syncedBms.length}</span>
                </button>
              </div>
              {activeTab === "vias" && (
                <div className="via-toolbar-right">
                  <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Lọc trạng thái">
                    <option value="ALL">Tất cả trạng thái</option>
                    <option value="NO_TOKEN">Chưa cấp quyền</option>
                    <option value="ACTIVE_TOKEN">Đã cấp quyền</option>
                    <option value="CHECKPOINT">Checkpoint</option>
                    <option value="LIVE">UID LIVE</option>
                    <option value="DIE">UID DIE</option>
                  </select>
                  <div className="via-search">
                    <MonoIcon name="search" />
                    <input type="search" placeholder="Tìm UID, tên, email, proxy..." value={search} onChange={(e) => setSearch(e.target.value)} />
                  </div>
                </div>
              )}
            </div>

            {loading ? (
              <div className="loading">Đang tải dữ liệu...</div>
            ) : activeTab === "vias" ? (
              <div className="table-scroll">
                <table className="via-table">
                  <thead>
                    <tr>
                      <th>Hồ sơ</th>
                      <th>Kết nối Meta</th>
                      <th>UID</th>
                      <th>2FA</th>
                      <th>Proxy</th>
                      <th>Tài sản</th>
                      <th style={{ textAlign: "right" }}>Thao tác</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredVias.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="muted" style={{ textAlign: "center", padding: "40px 16px" }}>
                          Không có VIA nào khớp bộ lọc.
                        </td>
                      </tr>
                    ) : (
                      filteredVias.map((via) => {
                        const otp = otpCountdowns[via.id];
                        const busy = actionLoadingId === via.id;
                        const authorized = via.token_status === "ACTIVE";
                        const expires = formatTime(via.token_expires_at);
                        return (
                          <tr key={via.id}>
                            {/* Hồ sơ */}
                            <td>
                              {editingViaId === via.id ? (
                                <div className="via-edit">
                                  <input
                                    autoFocus
                                    value={editProfileName}
                                    placeholder="Tên hồ sơ"
                                    onChange={(e) => setEditProfileName(e.target.value)}
                                    onKeyDown={(e) => {
                                      if (e.key === "Enter") { e.preventDefault(); void handleSaveViaInfo(via.id); }
                                      else if (e.key === "Escape") cancelEditingVia();
                                    }}
                                  />
                                  <input
                                    value={editNote}
                                    placeholder="Ghi chú"
                                    onChange={(e) => setEditNote(e.target.value)}
                                    onKeyDown={(e) => {
                                      if (e.key === "Enter") { e.preventDefault(); void handleSaveViaInfo(via.id); }
                                      else if (e.key === "Escape") cancelEditingVia();
                                    }}
                                  />
                                  <div className="via-edit-actions">
                                    <button type="button" className="btn sm" onClick={cancelEditingVia}>Hủy</button>
                                    <button type="button" className="btn sm primary" disabled={isSavingEdit} onClick={() => void handleSaveViaInfo(via.id)}>
                                      {isSavingEdit ? "Đang lưu..." : "Lưu"}
                                    </button>
                                  </div>
                                </div>
                              ) : (
                                <>
                                  <div className="via-name">
                                    <span>{via.profile_name}</span>
                                    <button type="button" onClick={() => startEditingVia(via)} title="Sửa tên & ghi chú" aria-label="Sửa tên & ghi chú">
                                      <MonoIcon name="edit" />
                                    </button>
                                  </div>
                                  <div className="via-sub">
                                    <a href={`https://www.facebook.com/${via.uid}`} target="_blank" rel="noreferrer">{via.uid}</a>
                                    <button type="button" onClick={() => copyToClipboard(via.uid, `uid-${via.id}`)} title="Sao chép UID" aria-label="Sao chép UID">
                                      <MonoIcon name={copiedKey === `uid-${via.id}` ? "check" : "copy"} />
                                    </button>
                                  </div>
                                  {via.email && <div className="via-sub">{via.email}</div>}
                                  {via.note && <div className="via-note" title={via.note}>{via.note}</div>}
                                </>
                              )}
                            </td>

                            {/* Kết nối Meta */}
                            <td>
                              <div className="via-connect">
                                <TokenStatus status={via.token_status} />
                                {via.meta_user_name && (
                                  <span className="table-muted" title="Tài khoản Facebook đã liên kết qua OAuth">
                                    FB: {via.meta_user_name}
                                  </span>
                                )}
                                {authorized ? (
                                  <>
                                    {expires && <span className="table-muted">Hết hạn: {expires}</span>}
                                    <button type="button" className="link-btn" disabled={busy} onClick={() => void handleMetaOAuth(via)}>
                                      Cấp quyền lại
                                    </button>
                                  </>
                                ) : (
                                  <button type="button" className="btn sm primary" disabled={busy} onClick={() => void handleMetaOAuth(via)}>
                                    <MonoIcon name="key" />
                                    {busy ? "Đang mở..." : "Cấp quyền Facebook"}
                                  </button>
                                )}
                              </div>
                            </td>

                            {/* UID live */}
                            <td>
                              <LiveStatus status={via.uid_live_status} />
                              {formatTime(via.last_live_check_at, false) && (
                                <span className="table-muted">{formatTime(via.last_live_check_at, false)}</span>
                              )}
                            </td>

                            {/* 2FA */}
                            <td>
                              {via.has_2fa ? (
                                <div className="via-otp">
                                  <div>
                                    <strong suppressHydrationWarning>{otp?.code || via.live_2fa?.code || "------"}</strong>
                                    <small suppressHydrationWarning>{isMounted && otp ? `${otp.rem}s` : "30s"}</small>
                                  </div>
                                  <button
                                    type="button"
                                    className="btn icon sm"
                                    title="Sao chép mã 2FA"
                                    aria-label="Sao chép mã 2FA"
                                    onClick={() => {
                                      const code = otp?.code || via.live_2fa?.code;
                                      if (code) copyToClipboard(code, `otp-${via.id}`, `Đã sao chép mã 2FA ${code}`);
                                    }}
                                  >
                                    <MonoIcon name={copiedKey === `otp-${via.id}` ? "check" : "copy"} />
                                  </button>
                                </div>
                              ) : (
                                <span className="muted">—</span>
                              )}
                            </td>

                            {/* Proxy */}
                            <td>
                              {via.proxy?.display ? (
                                <>
                                  <div className="mono" style={{ maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis" }}>{via.proxy.display}</div>
                                  <button type="button" className="link-btn" onClick={() => { setProxyModalVia(via); setProxyInput(via.proxy.config || ""); }}>
                                    Sửa
                                  </button>
                                </>
                              ) : (
                                <button type="button" className="link-btn" onClick={() => { setProxyModalVia(via); setProxyInput(""); }}>
                                  + Gắn proxy
                                </button>
                              )}
                            </td>

                            {/* Tài sản */}
                            <td>
                              <div className="via-assets">
                                <div>{via.bm_count} BM · {via.ad_account_count} TKQC · {via.page_count} Page</div>
                                <span>{formatTime(via.last_synced_at) ? `Đồng bộ ${formatTime(via.last_synced_at)}` : "Chưa đồng bộ"}</span>
                              </div>
                            </td>

                            {/* Thao tác */}
                            <td>
                              <div className="row-actions">
                                <button
                                  type="button"
                                  className="btn sm"
                                  disabled={busy}
                                  onClick={() => void handleSyncAssets(via)}
                                  title={authorized ? "Đồng bộ BM, TKQC, Fanpage" : "Nên cấp quyền Facebook trước khi đồng bộ"}
                                >
                                  <MonoIcon name="sync" />
                                  Đồng bộ
                                </button>
                                <span className="menu-wrap">
                                  <button type="button" className="btn icon sm" onClick={(e) => openRowMenu(via, e)} aria-label="Thao tác khác" aria-expanded={rowMenu?.via.id === via.id}>
                                    <MonoIcon name="more" />
                                  </button>
                                </span>
                              </div>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            ) : (
              /* Tab Business Manager */
              <div className="table-scroll">
                <table className="via-table">
                  <thead>
                    <tr>
                      <th>Business Manager</th>
                      <th>VIA quản lý</th>
                      <th>Tài sản</th>
                      <th>Trạng thái</th>
                      <th style={{ textAlign: "right" }}>BM cho thuê</th>
                    </tr>
                  </thead>
                  <tbody>
                    {syncedBms.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="muted" style={{ textAlign: "center", padding: "40px 16px" }}>
                          Chưa có BM nào. Cấp quyền Facebook cho VIA rồi bấm Đồng bộ để kéo BM về.
                        </td>
                      </tr>
                    ) : (
                      syncedBms.map((bm) => (
                        <tr key={bm.bm_id}>
                          <td>
                            <div className="via-name">{bm.name}</div>
                            <div className="via-sub mono">{bm.bm_id}</div>
                          </td>
                          <td>
                            {bm.via_uid ? (
                              <>
                                <div>{bm.via_profile_name || "VIA"}</div>
                                <div className="via-sub mono">{bm.via_uid}</div>
                              </>
                            ) : (
                              <span className="muted">Chưa gắn VIA</span>
                            )}
                          </td>
                          <td>{bm.ad_account_count} TKQC · {bm.page_count} Page</td>
                          <td><span className="status idle">{bm.status}</span></td>
                          <td style={{ textAlign: "right" }}>
                            <button type="button" className={`btn sm ${bm.is_primary_rental ? "primary" : ""}`} onClick={() => void handleTogglePrimaryBM(bm)}>
                              {bm.is_primary_rental ? "Đang cho thuê" : "Đặt làm BM cho thuê"}
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {/* Menu thao tác của từng dòng (fixed để không bị bảng cắt) */}
      {rowMenu && (
        <div className="menu-wrap">
          <div className="menu" role="menu" style={{ position: "fixed", top: rowMenu.top, left: rowMenu.left, right: "auto", width: 230 }}>
            <button type="button" onClick={() => { const v = rowMenu.via; setRowMenu(null); void handleMetaOAuth(v); }}>
              <MonoIcon name="key" />
              {rowMenu.via.token_status === "ACTIVE" ? "Cấp quyền Facebook lại" : "Cấp quyền Facebook"}
            </button>
            <button type="button" onClick={() => { const v = rowMenu.via; setRowMenu(null); void handleCheckLive(v); }}>
              <MonoIcon name="check" />
              Kiểm tra Live UID
            </button>
            <button type="button" onClick={() => { const v = rowMenu.via; setRowMenu(null); setTargetSetCampViaId(v.id); setShowSetCampModal(true); }}>
              <MonoIcon name="campaign" />
              Giao lệnh Set Camp
            </button>
            <Link href={`/ads-check?via_id=${rowMenu.via.id}`} onClick={() => setRowMenu(null)}>
              <MonoIcon name="account" />
              Xem ADSOS CHECK
            </Link>
            <hr />
            <button type="button" className="danger" onClick={() => { const v = rowMenu.via; setRowMenu(null); void handleDeleteVia(v); }}>
              <MonoIcon name="trash" />
              Xóa VIA
            </button>
          </div>
        </div>
      )}

      {/* Modal tạo VIA */}
      <CreateViaModal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreated={() => void loadData()}
        onAuthorize={(via) => {
          setShowCreateModal(false);
          void handleMetaOAuth(via);
        }}
      />

      {/* Modal nhập hàng loạt */}
      <RawViaImportModal open={showImportModal} onClose={() => setShowImportModal(false)} onSuccess={() => void loadData()} />

      {/* Modal proxy */}
      {proxyModalVia && (
        <div className="modal-overlay" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && setProxyModalVia(null)}>
          <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="proxy-title">
            <header>
              <div>
                <h2 id="proxy-title">Proxy riêng</h2>
                <p>
                  {proxyModalVia.profile_name} · <span className="mono">{proxyModalVia.uid}</span>
                </p>
              </div>
              <button type="button" onClick={() => setProxyModalVia(null)} aria-label="Đóng">
                <MonoIcon name="close" />
              </button>
            </header>
            <form onSubmit={(e) => void handleSaveProxy(e)}>
              <div className="modal-body">
                <label className="field">
                  Địa chỉ proxy (HTTP hoặc SOCKS5)
                  <input required autoFocus placeholder="IP:Port:User:Pass hoặc URL" value={proxyInput} onChange={(e) => setProxyInput(e.target.value)} />
                  <span className="field-hint">
                    Hỗ trợ <code>103.45.67.89:8080:user:pass</code>, <code>http://user:pass@host:8080</code>,{" "}
                    <code>socks5://user:pass@host:1080</code>.
                  </span>
                </label>
              </div>
              <footer>
                <button type="button" className="btn" onClick={() => setProxyModalVia(null)}>Hủy</button>
                <button type="submit" className="btn primary" disabled={isSavingProxy || !proxyInput.trim()}>
                  {isSavingProxy ? "Đang lưu..." : "Lưu proxy"}
                </button>
              </footer>
            </form>
          </div>
        </div>
      )}

      <ExtensionManagerModal isOpen={showExtensionModal} onClose={() => setShowExtensionModal(false)} />
      <AutoSetCampModal isOpen={showSetCampModal} onClose={() => setShowSetCampModal(false)} vias={vias} defaultViaId={targetSetCampViaId} />
    </div>
  );
}
