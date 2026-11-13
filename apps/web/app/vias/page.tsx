"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  bulkImportVias,
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
import { MonoIcon } from "@/components/mono-icon";

export default function ViasFarmPage() {
  const [activeTab, setActiveTab] = useState<"vias" | "bms">("vias");
  const [vias, setVias] = useState<ViaProfile[]>([]);
  const [syncedBms, setSyncedBms] = useState<SyncedBM[]>([]);
  const [stats, setStats] = useState<ViaStats>({
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
  });

  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [feedback, setFeedback] = useState<{ text: string; error?: boolean } | null>(null);

  // Modals state
  const [showImportModal, setShowImportModal] = useState(false);
  const [showExtensionModal, setShowExtensionModal] = useState(false);
  const [showSetCampModal, setShowSetCampModal] = useState(false);
  const [targetSetCampViaId, setTargetSetCampViaId] = useState<number | undefined>(undefined);
  const [bulkText, setBulkText] = useState("");
  const [defaultProxy, setDefaultProxy] = useState("");
  const [isImporting, setIsImporting] = useState(false);

  // Proxy Edit Modal
  const [proxyModalVia, setProxyModalVia] = useState<ViaProfile | null>(null);
  const [proxyInput, setProxyInput] = useState("");
  const [isSavingProxy, setIsSavingProxy] = useState(false);

  // Single action loadings
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null);
  const [bulkChecking, setBulkChecking] = useState(false);
  const [syncingAll, setSyncingAll] = useState(false);

  // Inline edit profile_name & note state
  const [editingViaId, setEditingViaId] = useState<number | null>(null);
  const [editProfileName, setEditProfileName] = useState("");
  const [editNote, setEditNote] = useState("");
  const [isSavingEdit, setIsSavingEdit] = useState(false);

  // Live countdown state for 2FA OTP codes
  const [isMounted, setIsMounted] = useState(false);
  const [otpCountdowns, setOtpCountdowns] = useState<Record<number, { code: string; rem: number }>>({});
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  useEffect(() => {
    setIsMounted(true);
    const params = new URLSearchParams(window.location.search);
    const query = params.get("q");
    if (query) setSearch(query);
    if (params.get("success") === "true") {
      setFeedback({ text: "Cấp quyền thành công! Token đã được lưu an toàn." });
      window.history.replaceState({}, "", "/vias");
    } else if (params.get("success") === "false") {
      const reason = params.get("oauth_error");
      const message = reason === "access_denied"
        ? "Bạn đã hủy cấp quyền Meta. Dữ liệu VIA không thay đổi."
        : reason === "uid_mismatch"
          ? "Tài khoản Meta được cấp quyền không khớp UID của VIA. Token không được lưu."
          : "Không thể hoàn tất cấp quyền Meta. Token cũ được giữ nguyên.";
      setFeedback({ text: message, error: true });
      window.history.replaceState({}, "", "/vias");
    }
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [viaRes, bmRes] = await Promise.all([
        getVias(),
        getSyncedBMs(),
      ]);
      setVias(viaRes.vias || []);
      setStats(viaRes.stats);
      setSyncedBms(bmRes.bms || []);

      // Khởi tạo live OTP
      const otps: Record<number, { code: string; rem: number }> = {};
      viaRes.vias.forEach((v) => {
        if (v.live_2fa?.code) {
          otps[v.id] = { code: v.live_2fa.code, rem: v.live_2fa.remaining_seconds || 30 };
        }
      });
      setOtpCountdowns(otps);
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi khi tải dữ liệu dàn VIA.",
        error: true,
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  // Timer giảm số giây đếm ngược OTP mỗi giây
  useEffect(() => {
    const timer = setInterval(() => {
      setOtpCountdowns((prev) => {
        const next: Record<number, { code: string; rem: number }> = {};
        let needsFetch = false;
        Object.entries(prev).forEach(([key, val]) => {
          const id = Number(key);
          if (val.rem > 1) {
            next[id] = { code: val.code, rem: val.rem - 1 };
          } else {
            next[id] = { code: val.code, rem: 30 };
            needsFetch = true;
          }
        });
        if (needsFetch) {
          // Khi hết chu kỳ 30s, fetch lại mã mới cho các VIA đang hiển thị
          vias.forEach((v) => {
            if (v.has_2fa) {
              getVia2FA(v.id).then((res) => {
                if (res.code) {
                  setOtpCountdowns((cur) => ({
                    ...cur,
                    [v.id]: { code: res.code, rem: res.remaining_seconds || 30 },
                  }));
                }
              }).catch(() => {});
            }
          });
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [vias]);

  const copyToClipboard = (text: string, keyName: string, toastText?: string) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopiedKey(keyName);
    if (toastText) {
      setFeedback({ text: toastText });
    }
    setTimeout(() => {
      setCopiedKey(null);
    }, 1500);
  };

  // 1-Click Check Live Single UID
  const handleCheckLive = async (via: ViaProfile) => {
    try {
      setActionLoadingId(via.id);
      const res = await checkViaLive(via.id);
      setVias((prev) =>
        prev.map((v) =>
          v.id === via.id
            ? { ...v, uid_live_status: res.uid_live_status, last_live_check_at: res.last_live_check_at }
            : v
        )
      );
      setFeedback({ text: ` UID ${via.uid} trạng thái hiện tại: ${res.uid_live_status}` });
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi khi kiểm tra Live UID.",
        error: true,
      });
    } finally {
      setActionLoadingId(null);
    }
  };

  // Bulk Check Live UIDs
  const handleBulkCheckLive = async () => {
    try {
      setBulkChecking(true);
      setFeedback({ text: " Đang quét trạng thái Live / Die toàn bộ dàn VIA..." });
      const res = await checkViasLiveBulk();
      setFeedback({
        text: ` Hoàn tất quét! Đã kiểm tra: ${res.total_checked} VIA — ${res.live_count} LIVE, ${res.die_count} DIE.`,
      });
      await loadData();
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi khi quét Live hàng loạt.",
        error: true,
      });
    } finally {
      setBulkChecking(false);
    }
  };

  const handleForceSyncAll = async () => {
    try {
      setSyncingAll(true);
      const res = await forceSyncAllViaAssets();
      setFeedback({ text: ` ${res.message}` });
      window.setTimeout(() => void loadData(), 1500);
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Không thể khởi chạy đồng bộ toàn bộ VIA.",
        error: true,
      });
    } finally {
      setSyncingAll(false);
    }
  };

  const formatSyncTime = (value: string | null) => {
    if (!value) return "Chưa đồng bộ";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Chưa đồng bộ";
    return new Intl.DateTimeFormat("vi-VN", {
      dateStyle: "short",
      timeStyle: "short",
      timeZone: "Asia/Ho_Chi_Minh",
    }).format(date);
  };

  // 1-Click Sync BM Assets
  const handleSyncAssets = async (via: ViaProfile) => {
    try {
      setActionLoadingId(via.id);
      const res = await syncViaAssets(via.id);
      setFeedback({ text: ` ${res.message}` });
      await loadData();
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi đồng bộ BM.",
        error: true,
      });
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleMetaOAuth = async (via: ViaProfile) => {
    try {
      setActionLoadingId(via.id);
      const result = await fetchJson<{ authorization_url: string }>(
        `/oauth/facebook/login?via_id=${encodeURIComponent(via.id)}`
      );
      window.location.assign(result.authorization_url);
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Không thể bắt đầu cấp quyền OAuth Meta.",
        error: true,
      });
    } finally {
      setActionLoadingId(null);
    }
  };

  // Delete VIA
  const handleDeleteVia = async (via: ViaProfile) => {
    if (!confirm(`Bạn có chắc chắn muốn xóa VIA #${via.id} (${via.uid}) khỏi hệ thống?`)) return;
    try {
      await deleteVia(via.id);
      setFeedback({ text: ` Đã xóa thành công VIA ${via.uid}` });
      setVias((prev) => prev.filter((v) => v.id !== via.id));
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi xóa VIA.",
        error: true,
      });
    }
  };

  // Toggle Primary Rental BM
  const handleTogglePrimaryBM = async (bm: SyncedBM) => {
    try {
      const res = await togglePrimaryRentalBM(bm.bm_id, !bm.is_primary_rental);
      setFeedback({ text: res.message });
      setSyncedBms((prev) =>
        prev.map((b) => (b.bm_id === bm.bm_id ? res.bm : b))
      );
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi gắn cờ BM.",
        error: true,
      });
    }
  };

  // Save Proxy
  const handleSaveProxy = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!proxyModalVia) return;
    try {
      setIsSavingProxy(true);
      const res = await updateViaProxy(proxyModalVia.id, proxyInput);
      setFeedback({ text: res.message });
      setVias((prev) =>
        prev.map((v) => (v.id === proxyModalVia.id ? res.via : v))
      );
      setProxyModalVia(null);
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi lưu proxy.",
        error: true,
      });
    } finally {
      setIsSavingProxy(false);
    }
  };

  // Start / Cancel / Save Inline Edit Profile Name & Note
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
      setFeedback({ text: "Tên Profile không được để trống.", error: true });
      return;
    }
    try {
      setIsSavingEdit(true);
      const res = await updateViaInfo(viaId, {
        profile_name: cleanName,
        note: editNote.trim() || null,
      });
      setVias((prev) =>
        prev.map((v) =>
          v.id === viaId
            ? { ...v, profile_name: res.via.profile_name, note: res.via.note }
            : v
        )
      );
      setFeedback({ text: ` Đã lưu thông tin cho VIA ${res.via.uid}` });
      cancelEditingVia();
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi khi cập nhật thông tin VIA.",
        error: true,
      });
    } finally {
      setIsSavingEdit(false);
    }
  };

  // Bulk Import Submit
  const handleBulkImport = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!bulkText.trim()) return;
    try {
      setIsImporting(true);
      const res = await bulkImportVias(bulkText, defaultProxy.trim() || undefined);
      setFeedback({
        text: ` Đã nhập thành công ${res.imported} VIA mới, cập nhật ${res.updated} VIA! ${
          res.errors.length > 0 ? `(Có ${res.errors.length} dòng lỗi)` : ""
        }`,
        error: res.errors.length > 0 && res.imported === 0,
      });
      setShowImportModal(false);
      setBulkText("");
      setDefaultProxy("");
      await loadData();
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi nhập hàng loạt VIA.",
        error: true,
      });
    } finally {
      setIsImporting(false);
    }
  };

  // Filtered VIAs
  const filteredVias = useMemo(() => {
    return vias.filter((v) => {
      if (statusFilter === "LIVE" && v.uid_live_status !== "LIVE") return false;
      if (statusFilter === "DIE" && v.uid_live_status !== "DIE") return false;
      if (statusFilter === "ACTIVE_TOKEN" && v.token_status !== "ACTIVE") return false;
      if (statusFilter === "CHECKPOINT" && v.token_status !== "CHECKPOINT") return false;

      if (search.trim()) {
        const q = search.trim().toLowerCase();
        const matchUid = v.uid.toLowerCase().includes(q);
        const matchName = v.profile_name.toLowerCase().includes(q);
        const matchEmail = (v.email || "").toLowerCase().includes(q) || (v.backup_email || "").toLowerCase().includes(q);
        const matchProxy = (v.proxy?.display || "").toLowerCase().includes(q);
        if (!matchUid && !matchName && !matchEmail && !matchProxy) return false;
      }
      return true;
    });
  }, [vias, statusFilter, search]);

  return (
    <div className="w-full space-y-6">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-[#1F2937] pb-5">
        <div>
          <div className="flex items-center gap-3">
            <span className="text-2xl"></span>
            <h1 className="text-xl font-bold text-white tracking-tight m-0">
              Quản lý dàn VIA
            </h1>
            <span className="text-xs px-2.5 py-0.5 rounded-full font-mono bg-purple-500/20 text-purple-300 border border-purple-500/30">
              Hồ sơ & phiên đăng nhập
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-1.5">
            Quản lý hồ sơ, trình duyệt độc lập, proxy, mã 2FA và tài sản Business Manager đã đồng bộ.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => setShowExtensionModal(true)}
            className="px-3.5 py-2 rounded-xl text-xs font-semibold bg-cyan-950/80 border border-cyan-500/50 text-cyan-300 hover:bg-cyan-900/50 transition flex items-center gap-1.5 shadow-lg shadow-cyan-950/40"
            title="Tải & Quản lý Extension ADSOS CHECK PRO (Client Key, ZIP)"
          >
            <span></span>
            <span>Tiện ích trình duyệt</span>
          </button>
          <button
            type="button"
            onClick={() => {
              setTargetSetCampViaId(undefined);
              setShowSetCampModal(true);
            }}
            className="px-3.5 py-2 rounded-xl text-xs font-semibold bg-amber-950/80 border border-amber-500/50 text-amber-300 hover:bg-amber-900/50 transition flex items-center gap-1.5 shadow-lg shadow-amber-950/40"
            title="Quản lý Mẫu & Giao lệnh Auto Set Camp / Share từ xa"
          >
            <span></span>
            <span>Thiết lập chiến dịch</span>
          </button>
          <Link
            href="/ads-check"
            className="px-3.5 py-2 rounded-xl text-xs font-semibold bg-indigo-950/80 border border-indigo-500/50 text-indigo-300 hover:bg-indigo-900/50 transition flex items-center gap-1.5 shadow-lg shadow-indigo-950/40"
          >
            <span></span>
            <span>Bảng ADSOS CHECK</span>
          </Link>
          <button
            type="button"
            onClick={() => void handleBulkCheckLive()}
            disabled={bulkChecking}
            className="px-3.5 py-2 rounded-xl text-xs font-semibold bg-[#1A2234] border border-blue-500/40 text-blue-300 hover:bg-blue-500/10 transition flex items-center gap-1.5 disabled:opacity-50"
          >
            <span>{bulkChecking ? "" : ""}</span>
            <span>{bulkChecking ? "Đang Quét..." : "Check Live UID Hàng Loạt"}</span>
          </button>
          <button
            type="button"
            onClick={() => void handleForceSyncAll()}
            disabled={syncingAll}
            className="px-3.5 py-2 rounded-xl text-xs font-semibold bg-[#1A2234] border border-purple-500/40 text-purple-300 hover:bg-purple-500/10 transition flex items-center gap-1.5 disabled:opacity-50"
          >
            <span>{syncingAll ? "" : ""}</span>
            <span>{syncingAll ? "Đang xếp lịch..." : "Đồng bộ tất cả ngay"}</span>
          </button>
          <button
            type="button"
            onClick={() => setShowImportModal(true)}
            className="px-4 py-2 rounded-xl text-xs font-semibold bg-purple-600 hover:bg-purple-500 text-white transition flex items-center gap-1.5 shadow-lg shadow-purple-900/20"
          >
            <span></span>
            <span>Thêm / Nhập Hàng Loạt VIA</span>
          </button>
          <button
            type="button"
            onClick={() => void loadData()}
            className="px-3 py-2 rounded-xl text-xs text-gray-400 hover:text-white bg-[#1A2234] border border-[#374151] hover:border-gray-500 transition"
            title="Làm mới dữ liệu"
          >
            
          </button>
        </div>
      </div>

      {/* Feedback banner */}
      {feedback && (
        <div
          className={`p-3.5 rounded-xl text-xs font-medium border flex items-center justify-between ${
            feedback.error
              ? "bg-rose-500/15 border-rose-500/30 text-rose-300"
              : "bg-emerald-500/15 border-emerald-500/30 text-emerald-300"
          }`}
        >
          <span>{feedback.text}</span>
          <button
            type="button"
            onClick={() => setFeedback(null)}
            className="text-gray-400 hover:text-white text-xs px-2"
          >
            
          </button>
        </div>
      )}

      {/* 4 Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Card 1: Dàn VIA */}
        <div className="bg-[#111827] border border-[#1F2937] rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between text-gray-400 text-xs mb-1">
            <span>Dàn VIA Farm</span>
            <span className="text-purple-400"> 100+</span>
          </div>
          <div className="text-2xl font-bold font-mono text-white tabular-nums">
            {stats.total_vias}
          </div>
          <div className="flex items-center gap-2 mt-2 text-[11px] font-mono">
            <span className="px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
               {stats.live_count} LIVE
            </span>
            <span className="px-1.5 py-0.5 rounded bg-rose-500/15 text-rose-300 border border-rose-500/30">
               {stats.die_count} DIE
            </span>
            <span className="px-1.5 py-0.5 rounded bg-gray-500/15 text-gray-400 border border-gray-600">
               {stats.unknown_count} Chưa
            </span>
          </div>
        </div>

        {/* Card 2: Trạng thái Token */}
        <div className="bg-[#111827] border border-[#1F2937] rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between text-gray-400 text-xs mb-1">
            <span>Phiên &amp; Token Meta</span>
            <span className="text-emerald-400"> Auth</span>
          </div>
          <div className="text-2xl font-bold font-mono text-white tabular-nums">
            {stats.active_tokens} <span className="text-xs text-gray-400 font-normal">Active</span>
          </div>
          <div className="flex items-center gap-2 mt-2 text-[11px] font-mono">
            <span className="px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30">
               {stats.checkpoint_tokens} Checkpoint
            </span>
            <span className="text-gray-400 text-[10px]">
              Profile riêng cách ly 100%
            </span>
          </div>
        </div>

        {/* Card 3: Business Manager */}
        <div className="bg-[#111827] border border-[#1F2937] rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between text-gray-400 text-xs mb-1">
            <span>Business Manager (BM)</span>
            <span className="text-amber-400"> Synced</span>
          </div>
          <div className="text-2xl font-bold font-mono text-amber-300 tabular-nums">
            {stats.total_bms} <span className="text-xs text-gray-400 font-normal">BM</span>
          </div>
          <div className="flex items-center gap-1.5 mt-2 text-[11px] font-mono">
            <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 font-bold">
               {stats.primary_bms} BM Cho Thuê
            </span>
            <span className="text-gray-400 text-[10px]">Ưu tiên cấp phát</span>
          </div>
        </div>

        {/* Card 4: Tổng tài sản TKQC & Page */}
        <div className="bg-[#111827] border border-[#1F2937] rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between text-gray-400 text-xs mb-1">
            <span>Tài Sản Đã Khám Phá</span>
            <span className="text-blue-400"> Asset</span>
          </div>
          <div className="text-2xl font-bold font-mono text-white tabular-nums">
            {stats.total_ad_accounts} <span className="text-xs text-gray-400 font-normal">TKQC</span>
          </div>
          <div className="flex items-center gap-2 mt-2 text-[11px] font-mono">
            <span className="px-1.5 py-0.5 rounded bg-blue-500/15 text-blue-300 border border-blue-500/30">
               {stats.total_pages} Fanpages
            </span>
            <span className="text-gray-400 text-[10px]">Tự động map</span>
          </div>
        </div>
      </div>

      {/* Tabs & Search Filter Bar */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 bg-[#111827] p-3 rounded-2xl border border-[#1F2937]">
        {/* Tab switchers */}
        <div className="flex items-center gap-1 bg-[#0B0F19] p-1 rounded-xl border border-[#1F2937]">
          <button
            type="button"
            onClick={() => setActiveTab("vias")}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 ${
              activeTab === "vias"
                ? "bg-purple-600 text-white shadow-sm"
                : "text-gray-400 hover:text-white hover:bg-gray-800"
            }`}
          >
            <span> Dàn VIA Profile</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-black/40 font-mono">
              {filteredVias.length}
            </span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("bms")}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 ${
              activeTab === "bms"
                ? "bg-purple-600 text-white shadow-sm"
                : "text-gray-400 hover:text-white hover:bg-gray-800"
            }`}
          >
            <span> Danh Sách Business Manager (BM)</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-black/40 font-mono">
              {syncedBms.length}
            </span>
          </button>
        </div>

        {/* Filter & Search */}
        <div className="flex items-center gap-2 flex-1 max-w-md justify-end">
          {activeTab === "vias" && (
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-[#0B0F19] border border-[#1F2937] text-gray-200 text-xs rounded-xl px-2.5 py-1.5 focus:outline-none focus:border-purple-500"
            >
              <option value="ALL">Tất cả trạng thái</option>
              <option value="LIVE">Chỉ UID LIVE</option>
              <option value="DIE">Chỉ UID DIE</option>
              <option value="ACTIVE_TOKEN">Token ACTIVE</option>
              <option value="CHECKPOINT">Token CHECKPOINT</option>
            </select>
          )}

          <div className="relative flex-1">
            <input
              type="text"
              placeholder="Tìm theo UID, tên profile, mail, proxy..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-[#0B0F19] border border-[#1F2937] text-gray-200 text-xs rounded-xl pl-8 pr-3 py-1.5 focus:outline-none focus:border-purple-500"
            />
            <span className="absolute left-2.5 top-2 text-gray-500 text-xs"></span>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      {loading ? (
        <div className="py-20 text-center text-xs text-gray-400 bg-[#111827] rounded-2xl border border-[#1F2937]">
          Đang tải dữ liệu Dàn VIA &amp; BM...
        </div>
      ) : activeTab === "vias" ? (
        /* =========================================================================
           TAB 1: DÀN VIA PROFILE TABLE
           ========================================================================= */
        <div className="bg-[#111827] border border-[#1F2937] rounded-2xl overflow-hidden shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-[#1F2937] bg-[#161F30]/60 text-gray-400 font-semibold uppercase tracking-wider text-[11px]">
                  <th className="py-3 px-4">Profile / UID</th>
                  <th className="py-3 px-3">Trạng thái UID</th>
                  <th className="py-3 px-3">Mã 2FA (Live OTP)</th>
                  <th className="py-3 px-3">Email &amp; Backup</th>
                  <th className="py-3 px-3">Proxy Riêng</th>
                  <th className="py-3 px-3">Tài sản (BM/TKQC)</th>
                  <th className="py-3 px-3">Trạng thái Token</th>
                  <th className="py-3 px-4 text-right">Thao tác nhanh</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1F2937] text-gray-300 font-mono tabular-nums">
                {filteredVias.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-12 text-center text-gray-500 text-xs">
                      Không tìm thấy VIA nào phù hợp với bộ lọc.
                    </td>
                  </tr>
                ) : (
                  filteredVias.map((via) => {
                    const otpData = otpCountdowns[via.id];
                    const isLoading = actionLoadingId === via.id;

                    return (
                      <tr key={via.id} className="hover:bg-[#1A2234]/50 transition group">
                        {/* Profile / UID */}
                        <td className="py-3.5 px-4 font-sans">
                          {editingViaId === via.id ? (
                            <div className="bg-[#0c101c] border border-purple-500/60 rounded-xl p-2.5 shadow-2xl space-y-2 min-w-[240px]">
                              <div className="flex items-center justify-between border-b border-gray-800 pb-1">
                                <span className="text-[11px] font-bold text-purple-300 flex items-center gap-1">
                                  <span></span> Sửa Tên &amp; Ghi chú #{via.id}
                                </span>
                                <span className="text-[10px] text-gray-500 font-mono">{via.uid}</span>
                              </div>
                              <div>
                                <label className="text-[10px] font-medium text-gray-400 block mb-0.5">
                                  Tên Profile / Biệt danh:
                                </label>
                                <input
                                  type="text"
                                  value={editProfileName}
                                  onChange={(e) => setEditProfileName(e.target.value)}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter") {
                                      e.preventDefault();
                                      void handleSaveViaInfo(via.id);
                                    } else if (e.key === "Escape") {
                                      cancelEditingVia();
                                    }
                                  }}
                                  placeholder="VD: VIA-001 - Cầm BM1"
                                  autoFocus
                                  className="w-full bg-[#161c2e] border border-purple-500/40 rounded-lg px-2.5 py-1 text-xs text-white focus:outline-none focus:border-purple-400"
                                />
                              </div>
                              <div>
                                <label className="text-[10px] font-medium text-gray-400 block mb-0.5">
                                  Ghi chú (Note):
                                </label>
                                <input
                                  type="text"
                                  value={editNote}
                                  onChange={(e) => setEditNote(e.target.value)}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter") {
                                      e.preventDefault();
                                      void handleSaveViaInfo(via.id);
                                    } else if (e.key === "Escape") {
                                      cancelEditingVia();
                                    }
                                  }}
                                  placeholder="VD: Nuôi từ 2024, chuyên chạy thời trang"
                                  className="w-full bg-[#161c2e] border border-gray-700 rounded-lg px-2.5 py-1 text-xs text-gray-200 focus:outline-none focus:border-purple-400"
                                />
                              </div>
                              <div className="flex items-center justify-end gap-1.5 pt-1">
                                <button
                                  type="button"
                                  onClick={cancelEditingVia}
                                  className="px-2.5 py-1 rounded-lg text-[11px] text-gray-400 hover:text-white bg-[#1F2937] hover:bg-gray-700 transition"
                                >
                                  Hủy (Esc)
                                </button>
                                <button
                                  type="button"
                                  disabled={isSavingEdit}
                                  onClick={() => void handleSaveViaInfo(via.id)}
                                  className="px-3 py-1 rounded-lg text-[11px] font-semibold text-white bg-purple-600 hover:bg-purple-500 transition disabled:opacity-50"
                                >
                                  {isSavingEdit ? "Đang lưu..." : "Lưu (Enter)"}
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div>
                              <div className="flex items-center gap-1.5">
                                <span
                                  onClick={() => startEditingVia(via)}
                                  className="font-bold text-white text-xs cursor-pointer hover:text-purple-300 hover:underline transition"
                                  title="Bấm để đổi tên profile &amp; ghi chú"
                                >
                                  {via.profile_name}
                                </span>
                                <button
                                  type="button"
                                  onClick={() => startEditingVia(via)}
                                  className="text-gray-400 hover:text-purple-300 transition text-[11px] p-0.5"
                                  title="Sửa tên Profile &amp; Ghi chú"
                                >
                                  <MonoIcon name="edit" className="h-3.5 w-3.5" />
                                </button>
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/15 text-purple-300 font-mono border border-purple-500/20">
                                  #{via.id}
                                </span>
                              </div>
                              <div className="flex items-center gap-1.5 mt-1">
                                <a
                                  href={`https://m.facebook.com/${via.uid}`}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="font-mono text-purple-300 hover:text-purple-200 text-xs hover:underline"
                                >
                                  {via.uid}
                                </a>
                                <button
                                  type="button"
                                  onClick={() => copyToClipboard(via.uid, `uid-${via.id}`)}
                                  className="text-gray-500 hover:text-gray-300 text-[10px]"
                                  title="Sao chép UID"
                                >
                                  <MonoIcon name={copiedKey === `uid-${via.id}` ? "check" : "copy"} className="h-3.5 w-3.5" />
                                </button>
                              </div>
                              {via.note && (
                                <div
                                  className="mt-1 flex items-center gap-1 text-[11px] text-amber-200/90 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-md max-w-[210px] truncate"
                                  title={via.note}
                                >
                                  <span></span>
                                  <span className="truncate">{via.note}</span>
                                </div>
                              )}
                              <div className="text-[10px] text-gray-500 font-mono mt-0.5">
                                {via.profile_dir}
                              </div>
                            </div>
                          )}
                        </td>

                        {/* Trạng thái UID */}
                        <td className="py-3.5 px-3">
                          {via.uid_live_status === "LIVE" ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                              LIVE
                            </span>
                          ) : via.uid_live_status === "DIE" ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/15 text-rose-300 border border-rose-500/30">
                              <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
                              DIE
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-gray-500/15 text-gray-400 border border-gray-600">
                              CHƯA CHECK
                            </span>
                          )}
                          {via.last_live_check_at && (
                            <div className="text-[9px] text-gray-500 mt-1" suppressHydrationWarning>
                              {isMounted
                                ? new Date(via.last_live_check_at).toLocaleTimeString("vi-VN", {
                                    hour: "2-digit",
                                    minute: "2-digit",
                                  })
                                : "—"}
                            </div>
                          )}
                        </td>

                        {/* Mã 2FA (Live OTP) */}
                        <td className="py-3.5 px-3">
                          {via.has_2fa ? (
                            <div className="flex items-center gap-2">
                              <div className="bg-[#0B0F19] px-2.5 py-1 rounded-lg border border-[#374151]">
                                <div
                                  className="font-mono text-sm font-bold text-emerald-400 tracking-wider tabular-nums"
                                  suppressHydrationWarning
                                >
                                  {isMounted
                                    ? otpData?.code || via.live_2fa?.code || "------"
                                    : via.live_2fa?.code || "------"}
                                </div>
                                <div className="flex items-center justify-between text-[9px] text-gray-400 mt-0.5">
                                  <span>2FA</span>
                                  <span className="text-amber-400 font-mono font-bold tabular-nums" suppressHydrationWarning>
                                    {isMounted && otpData ? `${otpData.rem}s` : "30s"}
                                  </span>
                                </div>
                              </div>
                              <button
                                type="button"
                                onClick={() => {
                                  const code = otpData?.code || via.live_2fa?.code;
                                  if (code) {
                                    copyToClipboard(code, `otp-${via.id}`, `Đã sao chép mã 2FA: ${code}`);
                                  }
                                }}
                                className="p-1.5 rounded-lg bg-[#1F2937] hover:bg-gray-700 text-gray-300 text-xs transition"
                                title="Sao chép mã 2FA"
                              >
                                <MonoIcon name={copiedKey === `otp-${via.id}` ? "check" : "copy"} className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          ) : (
                            <span className="text-gray-500 text-[10px]">Chưa cài 2FA</span>
                          )}
                        </td>

                        {/* Email & Backup */}
                        <td className="py-3.5 px-3 font-sans">
                          {via.email ? (
                            <div className="flex items-center gap-1 text-[11px] text-gray-200">
                              <span className="truncate max-w-[140px]">{via.email}</span>
                              <button
                                type="button"
                                onClick={() => copyToClipboard(via.email, `mail-${via.id}`)}
                                className="text-gray-500 hover:text-gray-300 text-[10px]"
                              >
                                <MonoIcon name={copiedKey === `mail-${via.id}` ? "check" : "copy"} className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          ) : (
                            <span className="text-gray-500 text-[10px]">Không có email</span>
                          )}
                          {via.backup_email && (
                            <div className="text-[10px] text-gray-400 mt-0.5 truncate max-w-[140px]">
                              {via.backup_email}
                            </div>
                          )}
                        </td>

                        {/* Proxy Riêng */}
                        <td className="py-3.5 px-3 font-sans">
                          {via.proxy?.display ? (
                            <div className="space-y-1">
                              <div className="text-[11px] font-mono text-blue-300 truncate max-w-[140px]">
                                {via.proxy.display}
                              </div>
                              <div className="flex items-center gap-1.5">
                                <span className="text-[9px] px-1 rounded bg-blue-500/20 text-blue-300">
                                  Proxy riêng
                                </span>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setProxyModalVia(via);
                                    setProxyInput(via.proxy.config || "");
                                  }}
                                  className="text-[10px] text-gray-400 hover:text-white underline"
                                >
                                  Sửa
                                </button>
                              </div>
                            </div>
                          ) : (
                            <button
                              type="button"
                              onClick={() => {
                                setProxyModalVia(via);
                                setProxyInput("");
                              }}
                              className="px-2 py-0.5 rounded text-[10px] bg-[#1A2234] border border-[#374151] hover:border-gray-500 text-gray-300 transition"
                            >
                              + Gắn Proxy
                            </button>
                          )}
                        </td>

                        {/* Tài sản (BM / TKQC / Page) */}
                        <td className="py-3.5 px-3">
                          <div className="flex flex-col gap-1 text-[10px]">
                            <span className="text-amber-300 font-semibold">
                               {via.bm_count} BM
                            </span>
                            <span className="text-blue-300">
                               {via.ad_account_count} TKQC
                            </span>
                            <span className="text-emerald-300">
                               {via.page_count} Pages
                            </span>
                            <span className="text-gray-400 leading-4">
                              Đồng bộ lần cuối: {formatSyncTime(via.last_synced_at)}
                            </span>
                          </div>
                        </td>

                        {/* Trạng thái Token */}
                        <td className="py-3.5 px-3">
                          {via.token_status === "ACTIVE" ? (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                              ACTIVE
                            </span>
                          ) : via.token_status === "CHECKPOINT" ? (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30">
                              CHECKPOINT
                            </span>
                          ) : via.token_status === "EXPIRED" ? (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/15 text-rose-300 border border-rose-500/30">
                              EXPIRED
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-gray-500/15 text-gray-400 border border-gray-600">
                              NONE
                            </span>
                          )}
                        </td>

                        {/* Thao tác Nhanh */}
                        <td className="py-3.5 px-4 text-right font-sans">
                          <div className="flex items-center justify-end gap-1.5 flex-wrap">
                            <button
                              type="button"
                              disabled={isLoading}
                              onClick={() => void handleMetaOAuth(via)}
                              className="px-2 py-1 rounded-lg text-[11px] font-medium bg-emerald-950/80 border border-emerald-500/40 text-emerald-300 hover:bg-emerald-900/40 transition disabled:opacity-50"
                              title="Cấp quyền qua OAuth 2.0 chính thức của Meta"
                            >
                               Cấp quyền OAuth (An toàn)
                            </button>
                            <button
                              type="button"
                              disabled={isLoading}
                              onClick={() => void handleSyncAssets(via)}
                              className="px-2 py-1 rounded-lg text-[11px] font-medium bg-[#1A2234] border border-purple-500/30 text-purple-300 hover:bg-purple-500/10 transition disabled:opacity-50"
                              title="Đồng bộ toàn bộ BM, TKQC, Fanpage"
                            >
                               Sync BM
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setTargetSetCampViaId(via.id);
                                setShowSetCampModal(true);
                              }}
                              className="px-2 py-1 rounded-lg text-[11px] font-medium bg-[#1A2234] border border-amber-500/40 text-amber-300 hover:bg-amber-500/10 transition"
                              title="Giao lệnh tạo Campaign / Share TKQC từ xa cho VIA này"
                            >
                               Set Camp
                            </button>
                            <Link
                              href={`/ads-check?via_id=${via.id}`}
                              className="px-2 py-1 rounded-lg text-[11px] font-medium bg-[#1A2234] border border-indigo-500/40 text-indigo-300 hover:bg-indigo-500/10 transition"
                              title="Xem bảng ADSOS CHECK của VIA này"
                            >
                               ADSOS CHECK
                            </Link>
                            <button
                              type="button"
                              disabled={isLoading}
                              onClick={() => void handleCheckLive(via)}
                              className="px-2 py-1 rounded-lg text-[11px] font-medium bg-[#1A2234] border border-blue-500/30 text-blue-300 hover:bg-blue-500/10 transition disabled:opacity-50"
                              title="Kiểm tra Live UID ngay lập tức"
                            >
                               Check
                            </button>
                            <button
                              type="button"
                              onClick={() => void handleDeleteVia(via)}
                              className="p-1 rounded-lg text-gray-500 hover:text-rose-400 hover:bg-rose-500/10 transition"
                              title="Xóa VIA"
                            >
                              <MonoIcon name="trash" className="h-4 w-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        /* =========================================================================
           TAB 2: SYNCED BMS SUB-PANEL
           ========================================================================= */
        <div className="space-y-4">
          <div className="bg-[#111827] border border-[#1F2937] rounded-2xl p-4 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-white tracking-tight m-0">
                 Danh Sách Business Manager Được Quản Lý Bởi Dàn VIA
              </h3>
              <p className="text-xs text-gray-400 mt-1">
                Gắn cờ <strong> Đặt làm BM Chính Cho Thuê</strong> để hệ thống tự động ưu tiên BM này khi cấp quyền TKQC hoặc mời khách hàng.
              </p>
            </div>
            <div className="text-xs font-mono px-3 py-1.5 rounded-xl bg-amber-500/15 text-amber-300 border border-amber-500/30 font-bold">
               {syncedBms.filter((b) => b.is_primary_rental).length} BM Chính Cho Thuê Đang Hoạt Động
            </div>
          </div>

          <div className="bg-[#111827] border border-[#1F2937] rounded-2xl overflow-hidden shadow-xl">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-[#1F2937] bg-[#161F30]/60 text-gray-400 font-semibold uppercase tracking-wider text-[11px]">
                  <th className="py-3 px-4">Cờ Cho Thuê</th>
                  <th className="py-3 px-4">BM ID</th>
                  <th className="py-3 px-4">Tên Business Manager</th>
                  <th className="py-3 px-4">VIA Quản Lý</th>
                  <th className="py-3 px-3">Tài sản (TKQC / Page)</th>
                  <th className="py-3 px-3">Trạng thái</th>
                  <th className="py-3 px-4 text-right">Hành động</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1F2937] text-gray-300 font-mono tabular-nums">
                {syncedBms.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-12 text-center text-gray-500 text-xs font-sans">
                      Chưa có BM nào được đồng bộ. Hãy bấm nút <strong> Sync BM</strong> trên các VIA để kéo BM về.
                    </td>
                  </tr>
                ) : (
                  syncedBms.map((bm) => (
                    <tr
                      key={bm.bm_id}
                      className={`hover:bg-[#1A2234]/50 transition ${
                        bm.is_primary_rental ? "bg-amber-500/5" : ""
                      }`}
                    >
                      {/* Cờ Cho Thuê */}
                      <td className="py-3.5 px-4">
                        <button
                          type="button"
                          onClick={() => void handleTogglePrimaryBM(bm)}
                          className={`px-2.5 py-1 rounded-xl text-xs font-bold transition flex items-center gap-1.5 ${
                            bm.is_primary_rental
                              ? "bg-amber-500/20 text-amber-300 border border-amber-500/50 hover:bg-amber-500/30"
                              : "bg-[#1A2234] border border-[#374151] text-gray-400 hover:text-amber-300 hover:border-amber-500/30"
                          }`}
                        >
                          <span>{bm.is_primary_rental ? "" : ""}</span>
                          <span>{bm.is_primary_rental ? "BM Cho Thuê" : "Thường"}</span>
                        </button>
                      </td>

                      {/* BM ID */}
                      <td className="py-3.5 px-4 font-mono font-bold text-purple-300">
                        {bm.bm_id}
                      </td>

                      {/* Tên BM */}
                      <td className="py-3.5 px-4 font-sans font-semibold text-white">
                        {bm.name}
                      </td>

                      {/* VIA Quản Lý */}
                      <td className="py-3.5 px-4 font-sans">
                        {bm.via_uid ? (
                          <div>
                            <div className="font-mono text-emerald-300 text-xs">
                              {bm.via_uid}
                            </div>
                            <div className="text-[10px] text-gray-400 font-sans">
                              {bm.via_profile_name || "Profile VIA"}
                            </div>
                          </div>
                        ) : (
                          <span className="text-gray-500 text-[10px]">Chưa gắn VIA</span>
                        )}
                      </td>

                      {/* Tài sản */}
                      <td className="py-3.5 px-3">
                        <span className="text-blue-300 font-semibold">{bm.ad_account_count} TKQC</span> ·{" "}
                        <span className="text-gray-400">{bm.page_count} Pages</span>
                      </td>

                      {/* Trạng thái */}
                      <td className="py-3.5 px-3">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                          {bm.status}
                        </span>
                      </td>

                      {/* Hành động */}
                      <td className="py-3.5 px-4 text-right font-sans">
                        <button
                          type="button"
                          onClick={() => void handleTogglePrimaryBM(bm)}
                          className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-[#1A2234] hover:bg-[#222E46] text-amber-300 border border-amber-500/30 transition"
                        >
                          {bm.is_primary_rental ? "Bỏ cờ chính" : " Đặt làm BM Chính Cho Thuê"}
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* =========================================================================
         MODAL 1: BULK IMPORT 100+ VIAS
         ========================================================================= */}
      {/* MODAL 1: NẠP NGUYÊN LIỆU & QUÉT SÂU TOÀN BỘ (RAW VIA + 2FA + TOKENS + DEEP ASSET SWEEP) */}
      <RawViaImportModal
        open={showImportModal}
        onClose={() => setShowImportModal(false)}
        onSuccess={() => void loadData()}
      />

      {/* =========================================================================
         MODAL 2: GẮN / SỬA PROXY RIÊNG CHO VIA
         ========================================================================= */}
      {proxyModalVia && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fadeIn">
          <div className="bg-[#111827] border border-[#1F2937] rounded-2xl w-full max-w-md p-6 shadow-2xl space-y-4 text-gray-200">
            <div className="flex items-start justify-between border-b border-[#1F2937] pb-3">
              <div>
                <h3 className="text-base font-bold text-white tracking-tight m-0">
                   Cấu Hình Proxy Riêng Cho VIA
                </h3>
                <p className="text-xs text-gray-400 mt-1">
                  VIA: <span className="text-purple-300 font-mono">{proxyModalVia.uid}</span> ({proxyModalVia.profile_name})
                </p>
              </div>
              <button
                type="button"
                onClick={() => setProxyModalVia(null)}
                className="text-gray-400 hover:text-white p-1"
              >
                
              </button>
            </div>

            <form onSubmit={(e) => void handleSaveProxy(e)} className="space-y-4 text-xs">
              <div>
                <label className="block text-gray-300 font-semibold mb-1">
                  Địa chỉ Proxy (HTTP hoặc SOCKS5):
                </label>
                <input
                  required
                  type="text"
                  placeholder="IP:Port:User:Pass hoặc URL"
                  value={proxyInput}
                  onChange={(e) => setProxyInput(e.target.value)}
                  className="w-full bg-[#0B0F19] border border-[#1F2937] rounded-xl px-3 py-2 text-white font-mono text-xs focus:outline-none focus:border-purple-500"
                />
                <div className="text-[10px] text-gray-400 mt-1.5 space-y-0.5">
                  <p>Hỗ trợ các định dạng:</p>
                  <p>• <code>103.45.67.89:8080:username:password</code></p>
                  <p>• <code>http://user:pass@103.45.67.89:8080</code></p>
                  <p>• <code>socks5://user:pass@103.45.67.89:1080</code></p>
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-[#1F2937]">
                <button
                  type="button"
                  onClick={() => setProxyModalVia(null)}
                  className="px-4 py-2 rounded-xl text-gray-400 hover:text-white hover:bg-gray-800 transition"
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  disabled={isSavingProxy || !proxyInput.trim()}
                  className="px-5 py-2 rounded-xl font-semibold text-white bg-blue-600 hover:bg-blue-500 transition disabled:opacity-50"
                >
                  {isSavingProxy ? "Đang lưu..." : "Lưu & Kích Hoạt Proxy"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Extension Manager Modal */}
      <ExtensionManagerModal
        isOpen={showExtensionModal}
        onClose={() => setShowExtensionModal(false)}
      />

      {/* Auto Set Camp Remote Command Modal */}
      <AutoSetCampModal
        isOpen={showSetCampModal}
        onClose={() => setShowSetCampModal(false)}
        vias={vias}
        defaultViaId={targetSetCampViaId}
      />
    </div>
  );
}
