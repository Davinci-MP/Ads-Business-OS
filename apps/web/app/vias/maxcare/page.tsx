"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  createMaxcareCategory,
  deleteMaxcareCategory,
  getMaxcareActivityLogs,
  getMaxcareCategories,
  getMaxcareReportsExportUrl,
  getMaxcareSeedingCatalog,
  getMaxcareSnapshots,
  getMaxcareTokensExportUrl,
  getVias,
  maxcareAction,
  maxcareBulkImport,
  maxcareRunSeeding,
  maxcareSyncReports,
  MaxcareActivityLogsResponse,
  MaxcareBulkLoginResult,
  MaxcareCheckLiveResult,
  MaxcareExportTokensResult,
  MaxcareImportResult,
  MaxcareSeedingCatalogAction,
  MaxcareSeedingRunResult,
  MaxcareSnapshotItem,
  MaxcareSyncReportsResult,
  MaxcareUpdateInfoResult,
  renameMaxcareCategory,
  ViaCategoryItem,
  ViaProfile,
} from "../../../lib/api";
import ViaSheetWritebackModal from "../../../components/ViaSheetWritebackModal";

type ActionLogEntry = { id: string; kind: string; text: string; error?: boolean; time: string };

const nowVn = () =>
  new Date().toLocaleTimeString("vi-VN", { hour12: false });

function formatMoneyValue(val: number | string | null | undefined): string {
  if (val == null) return "0";
  const num = Number(val);
  if (Number.isFinite(num)) {
    return num.toLocaleString("vi-VN", { useGrouping: true });
  }
  return String(val);
}

export default function MaxcareDashboardPage() {
  // Data
  const [vias, setVias] = useState<ViaProfile[]>([]);
  const [categories, setCategories] = useState<ViaCategoryItem[]>([]);
  const [seedingCatalog, setSeedingCatalog] = useState<MaxcareSeedingCatalogAction[]>([]);
  const [snapshots, setSnapshots] = useState<MaxcareSnapshotItem[]>([]);
  const [logData, setLogData] = useState<MaxcareActivityLogsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState<{ text: string; error?: boolean } | null>(null);
  const [runConsole, setRunConsole] = useState<ActionLogEntry[]>([]);

  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [activeCategory, setActiveCategory] = useState<number | null>(null);
  const [search, setSearch] = useState("");

  // Buttons loading
  const [bulkActionLoading, setBulkActionLoading] = useState<string | null>(null);

  // Modals: Import
  const [showImportModal, setShowImportModal] = useState(false);
  const [importText, setImportText] = useState("");
  const [importCategory, setImportCategory] = useState("");
  const [importLoading, setImportLoading] = useState(false);

  // Modals: Category
  const [showCategoryModal, setShowCategoryModal] = useState(false);
  const [categoryName, setCategoryName] = useState("");
  const [categoryColor, setCategoryColor] = useState("");
  const [categoryLoading, setCategoryLoading] = useState(false);

  // Modals: Update info
  const [showUpdateModal, setShowUpdateModal] = useState(false);
  const [updCategory, setUpdCategory] = useState("");
  const [updDevice, setUpdDevice] = useState("");
  const [updGender, setUpdGender] = useState<"ALL" | "Nam" | "Nữ">("ALL");
  const [updBirthday, setUpdBirthday] = useState("");
  const [updNote, setUpdNote] = useState("");
  const [updAppend, setUpdAppend] = useState(false);
  const [updateLoading, setUpdateLoading] = useState(false);

  // Modals: Seeding
  const [showSeedingModal, setShowSeedingModal] = useState(false);
  const [seedActions, setSeedActions] = useState<string[]>([]);
  const [seedScroll, setSeedScroll] = useState(20);
  const [seedLike, setSeedLike] = useState(3);
  const [seedJoin, setSeedJoin] = useState(1);
  const [seedingLoading, setSeedingLoading] = useState(false);
  const [showWritebackModal, setShowWritebackModal] = useState(false);

  const appendLog = (kind: string, text: string, error?: boolean) => {
    setRunConsole((prev) =>
      [
        { id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, kind, text, error, time: nowVn() },
        ...prev,
      ].slice(0, 60)
    );
  };

  const loadData = async () => {
    try {
      setLoading(true);
      const viaRes = await getVias();
      const [catRes, seedRes, snapRes, logRes] = await Promise.all([
        getMaxcareCategories(),
        getMaxcareSeedingCatalog(),
        getMaxcareSnapshots(60),
        getMaxcareActivityLogs({ limit: 40 }),
      ]);
      setVias(viaRes.vias || []);
      setCategories(catRes.categories || []);
      setSeedingCatalog(seedRes.actions || []);
      setSnapshots(snapRes.snapshots || []);
      setLogData(logRes);
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi khi tải dữ liệu MaxCare.",
        error: true,
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const filteredVias = useMemo(() => {
    let list = vias;
    if (activeCategory !== null) {
      list = list.filter((v) => v.category?.id === activeCategory);
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter((v) => {
        const uid = (v.uid || "").toLowerCase();
        const name = (v.profile_name || "").toLowerCase();
        return uid.includes(q) || name.includes(q);
      });
    }
    return list;
  }, [vias, activeCategory, search]);

  const stats = useMemo(() => {
    const live = vias.filter((v) => v.uid_live_status === "LIVE").length;
    const die = vias.filter((v) => v.uid_live_status === "DIE").length;
    const activeTokens = vias.filter((v) => v.token_status === "ACTIVE").length;
    const totalSpend = snapshots.reduce((acc, s) => acc + Number(s.total_spend || 0), 0);
    const totalBalance = snapshots.reduce((acc, s) => acc + Number(s.balance || 0), 0);
    return {
      totalVias: vias.length,
      live,
      die,
      activeTokens,
      totalSpend,
      totalBalance,
      hasSpentSnapshots: snapshots.length > 0,
    };
  }, [vias, snapshots]);

  const selectedArr = useMemo(() => Array.from(selectedIds), [selectedIds]);

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    setSelectedIds((prev) =>
      prev.size === filteredVias.length
        ? new Set()
        : new Set(filteredVias.map((v) => v.id))
    );
  };

  // ------------------------------------------------------------------
  // API handlers
  // ------------------------------------------------------------------

  const handleCreateCategory = async () => {
    const name = categoryName.trim();
    if (!name) {
      setFeedback({ text: " Vui lòng nhập tên danh mục VIA.", error: true });
      return;
    }
    try {
      setCategoryLoading(true);
      await createMaxcareCategory(name, categoryColor.trim() || undefined);
      setFeedback({ text: ` Đã tạo danh mục "${name}".` });
      setShowCategoryModal(false);
      setCategoryName("");
      setCategoryColor("");
      await loadData();
    } catch (err: unknown) {
      setFeedback({ text: err instanceof Error ? err.message : "Lỗi tạo danh mục.", error: true });
    } finally {
      setCategoryLoading(false);
    }
  };

  const handleDeleteCategory = async (cat: ViaCategoryItem) => {
    if (!window.confirm(`Xóa danh mục "${cat.name}"? Chỉ xóa được khi danh mục trống.`)) return;
    try {
      const res = await deleteMaxcareCategory(cat.id);
      setFeedback({ text: ` ${res.message}` });
      if (activeCategory === cat.id) setActiveCategory(null);
      await loadData();
    } catch (err: unknown) {
      setFeedback({ text: err instanceof Error ? err.message : "Lỗi xóa danh mục.", error: true });
    }
  };

  const handleRenameCategory = async (cat: ViaCategoryItem) => {
    const name = window.prompt("Đổi tên danh mục:", cat.name);
    if (!name || !name.trim()) return;
    try {
      await renameMaxcareCategory(cat.id, name.trim());
      setFeedback({ text: ` Đã đổi tên danh mục thành "${name.trim()}".` });
      await loadData();
    } catch (err: unknown) {
      setFeedback({ text: err instanceof Error ? err.message : "Lỗi đổi tên danh mục.", error: true });
    }
  };

  const handleImport = async () => {
    if (importText.trim().length < 3) {
      setFeedback({ text: " Nhập ít nhất 1 dòng VIA (UID|PASS|2FA|mail|pass mail|backup|cookie|token).", error: true });
      return;
    }
    try {
      setImportLoading(true);
      const res: MaxcareImportResult = await maxcareBulkImport(importText, importCategory.trim() || undefined);
      setFeedback({
        text: ` Import xong: ${res.imported} VIA mới, cập nhật ${res.updated}, lỗi ${res.errors.length}.`,
      });
      appendLog("IMPORT", `Import ${res.total_parsed} dòng → mới: ${res.imported}, cập nhật: ${res.updated}, lỗi: ${res.errors.length}`);
      res.errors.forEach((e) => appendLog("IMPORT", e, true));
      setShowImportModal(false);
      setImportText("");
      await loadData();
    } catch (err: unknown) {
      setFeedback({ text: err instanceof Error ? err.message : "Lỗi import VIA MaxCare.", error: true });
    } finally {
      setImportLoading(false);
    }
  };

  const handleBulkLogin = async () => {
    try {
      setBulkActionLoading("BULK_LOGIN");
      const res = (await maxcareAction(
        "BULK_LOGIN",
        selectedIds.size > 0 ? selectedArr : undefined,
        { concurrency: 8 }
      )) as MaxcareBulkLoginResult;
      setFeedback({ text: ` ${res.message}` });
      res.done.forEach((r) => appendLog("LOGIN", `VIA #${r.via_id}${r.uid ? ` (${r.uid})` : ""} — Đăng nhập thành công${r.token_status ? ` · token ${r.token_status}` : ""}`));
      res.failed.forEach((r) => appendLog("LOGIN", `VIA #${r.via_id}${r.uid ? ` (${r.uid})` : ""} — Thất bại: ${r.message || "lỗi không xác định"}`, true));
      await loadData();
    } catch (err: unknown) {
      setFeedback({ text: err instanceof Error ? err.message : "Lỗi Bulk Login.", error: true });
    } finally {
      setBulkActionLoading(null);
    }
  };

  const handleCheckLive = async () => {
    try {
      setBulkActionLoading("CHECK_LIVE");
      const res = (await maxcareAction(
        "CHECK_LIVE",
        selectedIds.size > 0 ? selectedArr : undefined
      )) as MaxcareCheckLiveResult;
      setFeedback({
        text: ` Quét xong ${res.total_checked} VIA: LIVE ${res.live_count} / DIE ${res.die_count} / Không rõ ${res.total_checked - res.live_count - res.die_count}.`,
      });
      appendLog("CHECK_LIVE", `Tổng ${res.total_checked} → LIVE: ${res.live_count}, DIE: ${res.die_count}`);
      await loadData();
    } catch (err: unknown) {
      setFeedback({ text: err instanceof Error ? err.message : "Lỗi Check Live.", error: true });
    } finally {
      setBulkActionLoading(null);
    }
  };

  const handleUpdateInfo = async () => {
    if (!updCategory.trim() && !updDevice.trim() && updGender === "ALL" && !updBirthday.trim() && !updNote.trim()) {
      setFeedback({ text: " Chưa nhập dữ liệu nào để cập nhật.", error: true });
      return;
    }
    if (selectedIds.size === 0 && !window.confirm("Không chọn VIA nào — cập nhật cho TOÀN BỘ dàn VIA?")) return;
    try {
      setUpdateLoading(true);
      const res = (await maxcareAction("UPDATE_INFO", selectedIds.size > 0 ? selectedArr : undefined, {
        category_name: updCategory.trim() || undefined,
        device_name: updDevice.trim() || undefined,
        gender: updGender === "ALL" ? undefined : updGender,
        birthday: updBirthday.trim() || undefined,
        note: updNote.trim() || undefined,
        as_note_append: updAppend,
      })) as MaxcareUpdateInfoResult;
      setFeedback({ text: ` ${res.message} (Danh mục: ${res.category || "—"})` });
      appendLog("UPDATE_INFO", `Cập nhật ${res.updated}/${res.total} VIA · category=${res.category || "-"} · device=${updDevice.trim() || "-"}`);
      setShowUpdateModal(false);
      await loadData();
    } catch (err: unknown) {
      setFeedback({ text: err instanceof Error ? err.message : "Lỗi cập nhật info hàng loạt.", error: true });
    } finally {
      setUpdateLoading(false);
    }
  };

  const handleSeeding = async () => {
    if (selectedIds.size === 0) {
      setFeedback({ text: " Chọn ít nhất 1 VIA để chạy nuôi tài khoản.", error: true });
      return;
    }
    if (seedActions.length === 0) {
      setFeedback({ text: " Chọn ít nhất 1 hành động nuôi tài khoản.", error: true });
      return;
    }
    try {
      setSeedingLoading(true);
      const resResults = await maxcareRunSeeding({
        via_ids: selectedArr,
        actions: seedActions,
        scroll_count: seedScroll,
        like_count: seedLike,
        join_group_count: seedJoin,
      });
      resResults.results.forEach((r: MaxcareSeedingRunResult) => {
        appendLog("SEEDING", `${r.action} → ${r.total} VIA: DONE ${r.done}, PLANNED ${r.planned}, FAILED ${r.failed}`);
        r.results.filter((item) => item.status === "FAILED").forEach((item) =>
          appendLog("SEEDING", `VIA #${item.via_id}${item.uid ? ` (${item.uid})` : ""} — ${item.detail || item.status}`, true)
        );
      });
      setShowSeedingModal(false);
      setFeedback({ text: ` Đã chạy nuôi tài khoản cho ${selectedArr.length} VIA (${seedActions.join(", ")}).` });
      await loadData();
    } catch (err: unknown) {
      setFeedback({ text: err instanceof Error ? err.message : "Lỗi chạy seeding.", error: true });
    } finally {
      setSeedingLoading(false);
    }
  };

  const handleSyncReports = async () => {
    try {
      setBulkActionLoading("SYNC_REPORTS");
      const res: MaxcareSyncReportsResult = await maxcareSyncReports({
        via_ids: selectedIds.size > 0 ? selectedArr : undefined,
        concurrency: 5,
      });
      setFeedback({
        text: ` Đồng bộ báo cáo: OK ${res.done.length}/${res.total} VIA (${res.concurrency} luồng).`,
      });
      res.done.forEach((r) =>
        appendLog("SYNC_REPORTS", `VIA #${r.via_id} — TKQC cập nhật ${r.accounts_updated ?? 0}, snapshot +${r.snapshots_created ?? 0}`)
      );
      res.failed.forEach((r) => appendLog("SYNC_REPORTS", `VIA #${r.via_id} — Lỗi: ${r.error || r.message || "không rõ"}`, true));
      await loadData();
    } catch (err: unknown) {
      setFeedback({ text: err instanceof Error ? err.message : "Lỗi đồng bộ báo cáo TKQC.", error: true });
    } finally {
      setBulkActionLoading(null);
    }
  };

  const handleExportTokens = (style: "csv" | "pipe") => {
    const url = getMaxcareTokensExportUrl({ style, via_ids: selectedIds.size > 0 ? selectedArr : undefined });
    window.open(url, "_blank");
    setFeedback({ text: ` Đang xuất Token + Cookie (${style.toUpperCase()}) cho ${selectedIds.size > 0 ? selectedIds.size + " VIA đã chọn" : "toàn bộ dàn VIA"}...` });
  };

  const handleExportReports = () => {
    window.open(getMaxcareReportsExportUrl(500), "_blank");
    setFeedback({ text: " Đang xuất CSV báo cáo TKQC MaxCare..." });
  };

  // ------------------------------------------------------------------
  // UI
  // ------------------------------------------------------------------

  const kpiCard = (label: string, value: React.ReactNode, accent: string, sub?: string) => (
    <div
      style={{
        background: "#ffffff",
        border: "1px solid #fafafa",
        borderRadius: 12,
        padding: "14px 16px",
        minWidth: 150,
        flex: 1,
      }}
    >
      <div style={{ fontSize: 11, color: "#666666", textTransform: "uppercase", letterSpacing: 0.6 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color: accent, marginTop: 4, fontFamily: "var(--font-geist-mono, monospace)", fontVariantNumeric: "tabular-nums" }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 11, color: "#666666", marginTop: 2 }}>{sub}</div>}
    </div>
  );

  const dot = (status: string | null) => {
    const color = status === "LIVE" ? "#22C55E" : status === "DIE" ? "#e5484d" : "#f5a623";
    return (
      <span
        title={status || "UNKNOWN"}
        style={{
          display: "inline-block",
          width: 9,
          height: 9,
          borderRadius: "50%",
          background: color,
          boxShadow: `0 0 6px ${color}`,
          marginRight: 6,
        }}
      />
    );
  };

  const tokenBadge = (status: string | null) => {
    const map: Record<string, { bg: string; c: string }> = {
      ACTIVE: { bg: "rgba(34,197,94,0.15)", c: "#16a34a" },
      CHECKPOINT: { bg: "rgba(245,158,11,0.15)", c: "#f5a623" },
      EXPIRED: { bg: "rgba(239,68,68,0.15)", c: "#e5484d" },
      NONE: { bg: "rgba(107,114,128,0.15)", c: "#666666" },
    };
    const s = map[(status || "NONE").toUpperCase()] || map.NONE;
    return (
      <span style={{ background: s.bg, color: s.c, fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 999 }}>
        {status || "NONE"}
      </span>
    );
  };

  const selectedLabel = selectedIds.size > 0 ? `${selectedIds.size} VIA đã chọn` : "Toàn dàn VIA";

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "#ffffff", color: "#171717" }}>
      {/* SIDEBAR */}
      <aside style={{ width: 230, background: "#ffffff", borderRight: "1px solid #fafafa", padding: "18px 10px", flexShrink: 0 }}>
        <Link href="/vias" style={{ display: "block", fontSize: 12, color: "#666666", textDecoration: "none", marginBottom: 14 }}>
          ← Quản lý Dàn VIA
        </Link>
        <div style={{ fontSize: 15, fontWeight: 700, color: "#171717", marginBottom: 4 }}> MaxCare Suite</div>
        <div style={{ fontSize: 10, color: "#666666", marginBottom: 16 }}>Nuôi &amp; khai thác dàn VIA</div>

        <div style={{ fontSize: 10, color: "#666666", textTransform: "uppercase", letterSpacing: 0.8, margin: "10px 8px 6px" }}>
          Danh mục VIA
        </div>
        <button
          onClick={() => { setActiveCategory(null); }}
          style={{
            display: "flex", justifyContent: "space-between", width: "100%", padding: "7px 10px", borderRadius: 7,
            fontSize: 12, textAlign: "left", cursor: "pointer", marginBottom: 2,
            background: activeCategory === null ? "rgba(0,112,243,0.08)" : "transparent",
            color: activeCategory === null ? "#fff" : "rgba(229,231,235,0.75)",
            border: activeCategory === null ? "1px solid rgba(0,112,243,0.08)" : "1px solid transparent",
          }}
        >
          <span> Tất cả VIA</span>
          <span style={{ color: "#666666" }}>{vias.length}</span>
        </button>
        {categories.map((cat) => (
          <div key={cat.id} style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 2 }}>
            <button
              onClick={() => setActiveCategory(cat.id)}
              onDoubleClick={() => handleRenameCategory(cat)}
              style={{
                flex: 1, display: "flex", justifyContent: "space-between", padding: "7px 10px", borderRadius: 7,
                fontSize: 12, textAlign: "left", cursor: "pointer",
                background: activeCategory === cat.id ? "rgba(0,112,243,0.08)" : "transparent",
                color: activeCategory === cat.id ? "#fff" : "rgba(229,231,235,0.75)",
                border: activeCategory === cat.id ? "1px solid rgba(0,112,243,0.08)" : "1px solid transparent",
              }}
            >
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {cat.color ? <span style={{ color: cat.color }}></span> : <span></span>} {cat.name}
              </span>
              <span style={{ color: "#666666" }}>{cat.via_count}</span>
            </button>
            <button
              title="Đổi tên"
              onClick={() => handleRenameCategory(cat)}
              style={{ background: "transparent", border: "none", color: "#666666", cursor: "pointer", fontSize: 12, padding: 2 }}
            >
              
            </button>
            <button
              title="Xóa danh mục trống"
              onClick={() => handleDeleteCategory(cat)}
              style={{ background: "transparent", border: "none", color: "#666666", cursor: "pointer", fontSize: 12, padding: 2 }}
            >
              
            </button>
          </div>
        ))}
        <button
          onClick={() => setShowCategoryModal(true)}
          style={{
            width: "100%", marginTop: 6, padding: "7px 10px", borderRadius: 7, fontSize: 12,
            background: "rgba(0,112,243,0.08)", color: "#0070f3", border: "1px dashed rgba(0,112,243,0.08)", cursor: "pointer",
          }}
        >
           Thêm danh mục
        </button>
      </aside>

      {/* MAIN */}
      <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* HEADER */}
        <div style={{ padding: "18px 22px 12px", borderBottom: "1px solid #fafafa" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <div>
              <div style={{ fontSize: 18, fontWeight: 700, color: "#171717" }}> MaxCare — Nuôi VIA &amp; Báo cáo TKQC</div>
              <div style={{ fontSize: 12, color: "#666666", marginTop: 2 }}>
                Danh mục VIA · Đăng nhập / Thu Token hàng loạt · Nuôi tài khoản · Đồng bộ &amp; xuất báo cáo
              </div>
            </div>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Tìm UID / tên VIA...  (Ctrl+F)"
              style={{
                background: "#ffffff", border: "1px solid #fafafa", borderRadius: 8, padding: "8px 12px",
                color: "#171717", fontSize: 12, width: 260, outline: "none",
              }}
            />
          </div>

          <div style={{ display: "flex", gap: 10, marginTop: 14, flexWrap: "wrap" }}>
            {kpiCard("Dàn VIA", stats.totalVias, "#171717", `LIVE ${stats.live} · DIE ${stats.die}`)}
            {kpiCard("Token hoạt động", stats.activeTokens, "#16a34a")}
            {kpiCard("Snapshot TKQC", snapshots.length, "#0070f3", stats.hasSpentSnapshots ? "có dữ liệu đồng bộ" : "chưa có dữ liệu")}
            {kpiCard("Tổng tiêu (snapshots)", formatMoneyValue(stats.totalSpend), "#f5a623", stats.hasSpentSnapshots ? undefined : "—")}
            {kpiCard("Tổng số dư", formatMoneyValue(stats.totalBalance), "#0070f3", undefined)}
          </div>
        </div>

        {(feedback || null) && (
          <div
            style={{
              margin: "10px 22px 0", padding: "10px 14px", borderRadius: 8, fontSize: 12.5,
              background: feedback!.error ? "rgba(239,68,68,0.12)" : "rgba(34,197,94,0.1)",
              color: feedback!.error ? "#e5484d" : "#0070f3",
              border: feedback!.error ? "1px solid rgba(239,68,68,0.3)" : "1px solid rgba(34,197,94,0.25)",
            }}
          >
            {feedback!.text}{" "}
            <button onClick={() => setFeedback(null)} style={{ background: "none", border: "none", color: "#666666", cursor: "pointer", fontSize: 11 }}>
              
            </button>
          </div>
        )}

        {/* TOOLBAR — služebné nút hành động */}
        <div style={{ padding: "12px 22px", display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", borderBottom: "1px solid #fafafa" }}>
          <span style={{ fontSize: 11, color: "#666666", background: "rgba(0,112,243,0.08)", padding: "4px 10px", borderRadius: 999, border: "1px solid rgba(0,112,243,0.08)" }}>
             {selectedLabel}
          </span>
          <button onClick={() => { setShowImportModal(true); }} style={btnStyle}> Import VIA</button>
          <button onClick={handleBulkLogin} disabled={bulkActionLoading === "BULK_LOGIN"} style={{ ...btnStyle, opacity: bulkActionLoading === "BULK_LOGIN" ? 0.6 : 1 }}>
            {bulkActionLoading === "BULK_LOGIN" ? " Đang đăng nhập..." : " Bulk Login (Thu Token)"}
          </button>
          <button onClick={handleCheckLive} disabled={bulkActionLoading === "CHECK_LIVE"} style={{ ...btnStyle, opacity: bulkActionLoading === "CHECK_LIVE" ? 0.6 : 1 }}>
            {bulkActionLoading === "CHECK_LIVE" ? " Đang quét..." : " Check Live UID"}
          </button>
          <button onClick={() => setShowUpdateModal(true)} style={btnStyle}> Cập nhật info hàng loạt</button>
          <button onClick={() => { setShowSeedingModal(true); }} style={btnStyle}> Nuôi tài khoản</button>
          <button onClick={handleSyncReports} disabled={bulkActionLoading === "SYNC_REPORTS"} style={{ ...btnStyle, opacity: bulkActionLoading === "SYNC_REPORTS" ? 0.6 : 1 }}>
            {bulkActionLoading === "SYNC_REPORTS" ? " Đang đồng bộ..." : " Đồng bộ báo cáo TKQC"}
          </button>
          <button
            onClick={() => setShowWritebackModal(true)}
            style={{
              ...btnStyle,
              background: "linear-gradient(135deg, #4f46e5 0%, #0070f3 100%)",
              color: "#171717",
              borderColor: "#6366f1",
              fontWeight: 600,
            }}
          >
             Kẻ &amp; Ghi Báo Cáo VIA Lên Sheet
          </button>
          <button onClick={handleExportReports} style={btnStyle}> Xuất CSV báo cáo</button>
          <button onClick={() => handleExportTokens("csv")} style={btnStyle}> Xuất Token &amp; Cookie</button>
          <button onClick={() => handleExportTokens("pipe")} style={{ ...btnStyle, opacity: 0.8 }}> (pipe)</button>
        </div>

        {/* TABLE + CONSOLE */}
        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          <div style={{ flex: "1 1 auto", overflow: "auto", padding: "0 22px 12px" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, minWidth: 860 }}>
              <thead>
                <tr style={{ color: "#666666", borderBottom: "1px solid #fafafa", textAlign: "left" }}>
                  <th style={thStyle}>
                    <input type="checkbox" checked={filteredVias.length > 0 && selectedIds.size === filteredVias.length} onChange={toggleSelectAll} />
                  </th>
                  <th style={thStyle}>VIA / UID</th>
                  <th style={thStyle}>Live</th>
                  <th style={thStyle}>Token</th>
                  <th style={thStyle}>Danh mục</th>
                  <th style={thStyle}>2FA</th>
                  <th style={thStyle}>BM / TKQC / Page</th>
                  <th style={thStyle}>Thiết bị</th>
                  <th style={thStyle}>Ghi chú</th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={9} style={{ padding: 24, color: "#666666" }}> Đang tải dữ liệu dàn VIA...</td></tr>
                )}
                {!loading && filteredVias.length === 0 && (
                  <tr><td colSpan={9} style={{ padding: 24, color: "#666666" }}>
                    Chưa có VIA nào {activeCategory !== null ? "thuộc danh mục này" : ""}. Dùng “ Import VIA” (hoặc “Thêm / Nhập hàng loạt VIA” ở trang Quản lý VIA) để nạp danh sách.
                  </td></tr>
                )}
                {filteredVias.map((v) => (
                  <tr key={v.id} style={{ borderBottom: "1px solid #ffffff" }}>
                    <td style={tdStyle}>
                      <input type="checkbox" checked={selectedIds.has(v.id)} onChange={() => toggleSelect(v.id)} />
                    </td>
                    <td style={tdStyle}>
                      <div style={{ fontWeight: 600, color: "#171717" }}>{v.profile_name || `VIA ${v.uid}`}</div>
                      <div style={{ fontFamily: "var(--font-geist-mono, monospace)", color: "#666666", fontSize: 11 }}>{v.uid}</div>
                    </td>
                    <td style={tdStyle}>{dot(v.uid_live_status)}{v.uid_live_status || "—"}</td>
                    <td style={tdStyle}>{tokenBadge(v.token_status)}</td>
                    <td style={tdStyle}>
                      {v.category ? (
                        <span style={{ color: v.category.color || "#0070f3" }}>{v.category.name}</span>
                      ) : (
                        <span style={{ color: "#666666" }}>—</span>
                      )}
                    </td>
                    <td style={tdStyle}>
                      {v.has_2fa ? (
                        <span style={{ fontFamily: "var(--font-geist-mono, monospace)", color: "#0070f3" }}>
                          {v.live_2fa?.code || "------"} ({v.live_2fa?.remaining_seconds ?? "--"}s)
                        </span>
                      ) : (
                        <span style={{ color: "#666666" }}>—</span>
                      )}
                    </td>
                    <td style={tdStyle}>{v.bm_count ?? 0} / {v.ad_account_count ?? 0} / {v.page_count ?? 0}</td>
                    <td style={tdStyle}>{v.device_name || "—"}</td>
                    <td style={{ ...tdStyle, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={v.note || ""}>
                      {v.note || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* RUN CONSOLE — chỉ in kết quả thật từ API */}
          <div style={{ width: 320, flexShrink: 0, borderLeft: "1px solid #fafafa", padding: "12px 14px", display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: 11, color: "#666666", textTransform: "uppercase", letterSpacing: 0.8 }}>Console kết quả</div>
              <button onClick={() => setRunConsole([])} style={{ background: "none", border: "none", color: "#666666", cursor: "pointer", fontSize: 11 }}>
                Xóa console
              </button>
            </div>
            <div style={{ flex: 1, overflowY: "auto", background: "#ffffff", border: "1px solid #fafafa", borderRadius: 8, padding: 10, fontFamily: "var(--font-geist-mono, monospace)", fontSize: 11 }}>
              {runConsole.length === 0 && <div style={{ color: "#666666" }}>Chưa có lượt chạy nào trong phiên này.</div>}
              {runConsole.map((entry) => (
                <div key={entry.id} style={{ color: entry.error ? "#e5484d" : "#16a34a", marginBottom: 4, wordBreak: "break-word" }}>
                  <span style={{ color: "#666666" }}>[{entry.time}]</span> <span style={{ color: "#0070f3" }}>{entry.kind}</span> · {entry.text}
                </div>
              ))}
            </div>

            <div style={{ fontSize: 11, color: "#666666", textTransform: "uppercase", letterSpacing: 0.8, marginTop: 8 }}>Nhật ký hệ thống (DB)</div>
            <div style={{ flex: 1, overflowY: "auto", background: "#ffffff", border: "1px solid #fafafa", borderRadius: 8, padding: 10, fontSize: 11, maxHeight: 200 }}>
              {(logData?.logs.length || 0) === 0 && <div style={{ color: "#666666" }}>Chưa có nhật ký MaxCare nào.</div>}
              {(logData?.logs || []).map((l) => (
                <div key={l.id} style={{ color: l.status === "FAILED" ? "#e5484d" : "rgba(229,231,235,0.7)", marginBottom: 3, wordBreak: "break-word" }}>
                  <span style={{ color: "#666666" }}>#{l.id}</span>{" "}
                  <span style={{ color: l.status === "DONE" ? "#0070f3" : l.status === "FAILED" ? "#e5484d" : "#f5a623" }}>{l.status}</span>{" "}
                  <span style={{ color: "#0070f3" }}>{l.action}</span> {l.detail}
                </div>
              ))}
            </div>

            <div style={{ fontSize: 11, color: "#666666", textTransform: "uppercase", letterSpacing: 0.8, marginTop: 8 }}>Snapshot TKQC mới nhất</div>
            <div style={{ flex: 1, overflowY: "auto", maxHeight: 220, display: "flex", flexDirection: "column", gap: 4 }}>
              {snapshots.length === 0 && <div style={{ color: "#666666", fontSize: 11 }}>Chưa có snapshot. Bấm “ Đồng bộ báo cáo TKQC”.</div>}
              {snapshots.slice(0, 12).map((s) => (
                <div key={s.id} style={{ background: "#ffffff", border: "1px solid #fafafa", borderRadius: 6, padding: "6px 8px", fontSize: 11 }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ fontFamily: "var(--font-geist-mono, monospace)", color: "#171717" }}>{s.act_id}</span>
                    <span style={{ color: s.status_dot === "LIVE" ? "#0070f3" : s.status_dot === "DIE" ? "#e5484d" : "#f5a623" }}>{s.status_dot || "—"}</span>
                  </div>
                  <div style={{ color: "#666666", display: "flex", justifyContent: "space-between", marginTop: 2 }}>
                    <span>Số dư: {formatMoneyValue(s.balance)} {s.currency}</span>
                    <span>Tiêu: {formatMoneyValue(s.total_spend)} {s.currency}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* MODAL: IMPORT */}
        {showImportModal && (
          <Modal onClose={() => setShowImportModal(false)} title=" Import hàng loạt VIA MaxCare">
            <div style={{ fontSize: 12, color: "#666666", marginBottom: 8 }}>
              Hỗ trợ pipe <code>UID|PASS|2FA|mail|pass_mail|mail_backup</code> và JSON dump trả về từ tool harvest.
              Mỗi dòng có thể khai thêm <code>category=</code>, <code>device=</code>, <code>gender=</code>, <code>birthday=</code>, <code>note=</code>, <code>proxy=</code>.
            </div>
            <textarea
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              rows={10}
              placeholder={"1001234567|Matkhau123|JBSWY3DPEHPK3PXP|mail@gmail.com|PassMail1|mail2@gmail.com category=Daily device=iPhone14 gender=F ngày=1/1/1990"}
              style={{ width: "100%", background: "#ffffff", border: "1px solid #fafafa", borderRadius: 8, padding: 10, color: "#171717", fontSize: 12, fontFamily: "var(--font-geist-mono, monospace)", resize: "vertical" }}
            />
            <label style={{ display: "block", fontSize: 12, marginTop: 10, color: "#666666" }}>
              Danh mục mặc định (khi dòng không khai <code>category=</code>)
              <input
                value={importCategory}
                onChange={(e) => setImportCategory(e.target.value)}
                list="category-list"
                style={{ marginLeft: 8, background: "#ffffff", border: "1px solid #fafafa", borderRadius: 6, padding: "6px 8px", color: "#171717", fontSize: 12 }}
              />
              <datalist id="category-list">
                {categories.map((c) => <option key={c.id} value={c.name} />)}
              </datalist>
            </label>
            <ModalActions
              onClose={() => setShowImportModal(false)}
              loading={importLoading}
              label={importLoading ? " Đang import..." : " Import hàng loạt"}
              onConfirm={handleImport}
            />
          </Modal>
        )}

        {/* MODAL: CATEGORY */}
        {showCategoryModal && (
          <Modal onClose={() => setShowCategoryModal(false)} title=" Thêm danh mục VIA">
            <label style={labelStyle}>
              Tên danh mục <span style={{ color: "#e5484d" }}>*</span>
              <input value={categoryName} onChange={(e) => setCategoryName(e.target.value)} style={inputStyle} placeholder="vd: Farm, Daily, Scan ctv, Seeding..." />
            </label>
            <label style={labelStyle}>
              Màu badge (tùy chọn)
              <input value={categoryColor} onChange={(e) => setCategoryColor(e.target.value)} style={inputStyle} placeholder="vd: #0070f3" />
            </label>
            <ModalActions
              onClose={() => setShowCategoryModal(false)}
              loading={categoryLoading}
              label={categoryLoading ? " Đang lưu..." : " Tạo danh mục"}
              onConfirm={handleCreateCategory}
            />
          </Modal>
        )}

        {/* MODAL: UPDATE INFO */}
        {showUpdateModal && (
          <Modal onClose={() => setShowUpdateModal(false)} title=" Cập nhật info hàng loạt">
            <div style={{ fontSize: 12, color: "#666666", marginBottom: 8 }}>Phạm vi: <b style={{ color: "#171717" }}>{selectedLabel}</b>. Chỉ nhập field cần đổi; bỏ trống để giữ nguyên.</div>
            <label style={labelStyle}>
              Chuyển danh mục (tên mới hoặc đã có)
              <input value={updCategory} onChange={(e) => setUpdCategory(e.target.value)} list="category-list" style={inputStyle} placeholder="vd: Daily" />
            </label>
            <label style={labelStyle}>
              Tên thiết bị
              <input value={updDevice} onChange={(e) => setUpdDevice(e.target.value)} style={inputStyle} placeholder="vd: iPhone 14 Pro Max" />
            </label>
            <label style={labelStyle}>
              Giới tính
              <select value={updGender} onChange={(e) => setUpdGender(e.target.value as "ALL" | "Nam" | "Nữ")} style={inputStyle}>
                <option value="ALL">— Giữ nguyên —</option>
                <option value="Nam">Nam</option>
                <option value="Nữ">Nữ</option>
              </select>
            </label>
            <label style={labelStyle}>
              Ngày sinh <span style={{ color: "#666666" }}>(dd/mm/yyyy)</span>
              <input value={updBirthday} onChange={(e) => setUpdBirthday(e.target.value)} style={inputStyle} placeholder="vd: 01/01/1990" />
            </label>
            <label style={labelStyle}>
              Ghi chú
              <input value={updNote} onChange={(e) => setUpdNote(e.target.value)} style={inputStyle} placeholder="Nội dung ghi chú..." />
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#666666", marginTop: 4 }}>
              <input type="checkbox" checked={updAppend} onChange={(e) => setUpdAppend(e.target.checked)} />
              Nội chèn vào ghi chú cũ (thay vì thay thế)
            </label>
            <datalist id="category-list">
              {categories.map((c) => <option key={c.id} value={c.name} />)}
            </datalist>
            <ModalActions
              onClose={() => setShowUpdateModal(false)}
              loading={updateLoading}
              label={updateLoading ? " Đang cập nhật..." : " Cập nhật hàng loạt"}
              onConfirm={handleUpdateInfo}
            />
          </Modal>
        )}

        {/* MODAL: SEEDING */}
        {showSeedingModal && (
          <Modal onClose={() => setShowSeedingModal(false)} title=" Nuôi tài khoản (Social Seeding)">
            <div style={{ fontSize: 12, color: "#666666", marginBottom: 8 }}>
              Phạm vi: <b style={{ color: "#171717" }}>{selectedIds.size > 0 ? `${selectedIds.size} VIA đã chọn` : "chọn VIA trước"}</b>. Mặc định hành động chỉ lên lịch (PLANNED) — chạy thật khi ADSOS_META_WRITES_ENABLED bật.
            </div>
            {seedingCatalog.map((a) => (
              <label key={a.value} style={{ display: "flex", gap: 8, alignItems: "flex-start", padding: "8px 0", borderBottom: "1px solid #ffffff", fontSize: 12 }}>
                <input
                  type="checkbox"
                  checked={seedActions.includes(a.value)}
                  onChange={(e) => {
                    setSeedActions((prev) => (e.target.checked ? [...prev, a.value] : prev.filter((x) => x !== a.value)));
                  }}
                  style={{ marginTop: 3 }}
                />
                <div>
                  <div style={{ color: "#171717", fontWeight: 600 }}>{a.label}</div>
                  <div style={{ color: "#666666", fontSize: 11 }}>{a.description}</div>
                </div>
              </label>
            ))}
            <label style={labelStyle}>
              Số lần lướt newsfeed: <b style={{ color: "#0070f3" }}>{seedScroll}</b>
              <input type="range" min={1} max={100} value={seedScroll} onChange={(e) => setSeedScroll(Number(e.target.value))} style={{ width: "100%" }} />
            </label>
            <label style={labelStyle}>
              Lượt like/comment mỗi phiên: <b style={{ color: "#0070f3" }}>{seedLike}</b>
              <input type="range" min={0} max={50} value={seedLike} onChange={(e) => setSeedLike(Number(e.target.value))} style={{ width: "100%" }} />
            </label>
            <label style={labelStyle}>
              Số group tham gia mỗi phiên: <b style={{ color: "#0070f3" }}>{seedJoin}</b>
              <input type="range" min={0} max={10} value={seedJoin} onChange={(e) => setSeedJoin(Number(e.target.value))} style={{ width: "100%" }} />
            </label>
            <ModalActions
              onClose={() => setShowSeedingModal(false)}
              loading={seedingLoading}
              label={seedingLoading ? " Đang gửi luồng nuôi..." : " Chạy nuôi tài khoản"}
              onConfirm={handleSeeding}
            />
          </Modal>
        )}

        {/* Via Sheet Writeback Modal */}
        <ViaSheetWritebackModal
          isOpen={showWritebackModal}
          onClose={() => setShowWritebackModal(false)}
        />
      </main>
    </div>
  );
}

// ============================================================
// UI helpers (kept out of the component for static rendering)
// ============================================================

const btnStyle: React.CSSProperties = {
  background: "#ffffff",
  border: "1px solid #fafafa",
  color: "#171717",
  borderRadius: 8,
  padding: "8px 12px",
  fontSize: 12,
  cursor: "pointer",
  fontWeight: 600,
};

const thStyle: React.CSSProperties = {
  padding: "8px 8px",
  fontWeight: 600,
  fontSize: 11,
  letterSpacing: 0.4,
  position: "sticky",
  top: 0,
  background: "#ffffff",
  zIndex: 1,
};

const tdStyle: React.CSSProperties = {
  padding: "8px 8px",
  verticalAlign: "middle",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 12,
  color: "#666666",
  marginTop: 10,
};

const inputStyle: React.CSSProperties = {
  display: "block",
  width: "100%",
  marginTop: 4,
  background: "#ffffff",
  border: "1px solid #fafafa",
  borderRadius: 6,
  padding: "7px 9px",
  color: "#171717",
  fontSize: 12,
  outline: "none",
};

function Modal(props: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 50,
        display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
      }}
      onClick={(e) => { if (e.target === e.currentTarget) props.onClose(); }}
    >
      <div
        style={{
          background: "#ffffff", border: "1px solid #fafafa", borderRadius: 12,
          width: "100%", maxWidth: 520, padding: 18, maxHeight: "85vh", overflowY: "auto",
          boxShadow: "0 20px 50px rgba(0,0,0,0.5)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: "#171717" }}>{props.title}</div>
          <button onClick={props.onClose} aria-label="Đóng" style={{ background: "none", border: "none", color: "#666666", cursor: "pointer", display: "grid", placeItems: "center" }}><svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="m6 6 12 12M18 6 6 18" /></svg></button>
        </div>
        {props.children}
      </div>
    </div>
  );
}

function ModalActions(props: { onClose: () => void; loading: boolean; label: string; onConfirm: () => void }) {
  return (
    <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
      <button onClick={props.onClose} style={btnStyle}>Hủy</button>
      <button
        onClick={props.onConfirm}
        disabled={props.loading}
        style={{ ...btnStyle, background: "#0070f3", borderColor: "#5A46B8", color: "#EDE9FE", opacity: props.loading ? 0.6 : 1 }}
      >
        {props.label}
      </button>
    </div>
  );
}
