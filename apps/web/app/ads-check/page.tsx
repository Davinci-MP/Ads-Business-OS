"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import React, { Suspense, useEffect, useMemo, useRef, useState } from "react";
import {
  AdsCheckResponse,
  AdsCheckSummary,
  ClientBMPreference,
  SyncedAdAccount,
  SyncedBM,
  SyncedPageItem,
  ViaProfile,
  extendedPaymentAction,
  getAdsCheckData,
  getClientBMPreferences,
  getSyncedBMs,
  getVias,
  harvestViaSession,
  openInViaBrowser,
  removeHiddenAdmins,
  renameAccounts,
  assignAccountCustomer,
  fetchJson,
  sharePixel,
  superShareAds,
  superTargetAction,
  getSuperTargets,
  syncViaAssets,
} from "../../lib/api";
import ExtensionManagerModal from "@/components/ExtensionManagerModal";
import ControlHubNodesBar from "@/components/ControlHubNodesBar";
import WorkflowCatalogModal from "@/components/WorkflowCatalogModal";

function ensureArray<T>(val: unknown): T[] {
  if (Array.isArray(val)) return val as T[];
  if (val && typeof val === "object") {
    const obj = val as Record<string, unknown>;
    if (Array.isArray(obj.items)) return obj.items as T[];
    if (Array.isArray(obj.vias)) return obj.vias as T[];
    if (Array.isArray(obj.bms)) return obj.bms as T[];
    if (Array.isArray(obj.data)) return obj.data as T[];
    if (Array.isArray(obj.accounts)) return obj.accounts as T[];
    if (Array.isArray(obj.customers)) return obj.customers as T[];
    if (Array.isArray(obj.pages)) return obj.pages as T[];
  }
  return [];
}
import AutoSetCampModal from "@/components/AutoSetCampModal";
import CustomerSpendReportModal from "@/components/CustomerSpendReportModal";
import ShareBmAccountsModal from "@/components/ShareBmAccountsModal";
import RawViaImportModal from "@/components/RawViaImportModal";

type TabType = "accounts" | "personal" | "bm" | "group" | "page" | "tasks";

function AdsCheckContent() {
  const searchParams = useSearchParams();
  const initialViaId = searchParams.get("via_id") ? Number(searchParams.get("via_id")) : undefined;

  // Active Tab & Filters
  const [isMounted, setIsMounted] = useState(false);
  const [activeTab, setActiveTab] = useState<TabType>("accounts");
  const [smitMode, setSmitMode] = useState<string>("LOAD_ALL");
  const [statusFilterPill, setStatusFilterPill] = useState<string>("ALL");
  const [typeFilter, setTypeFilter] = useState<string>("ALL");
  const [cardFilter, setCardFilter] = useState<string>("ALL");
  const [bmFilterId, setBmFilterId] = useState<string>("");
  const [accountIdsFilter, setAccountIdsFilter] = useState<string>("");
  const [customersList, setCustomersList] = useState<{ id: number; name: string }[]>([]);

  // Modals for SMIT Modes
  const [showLoadByIdModal, setShowLoadByIdModal] = useState(false);
  const [loadByIdInput, setLoadByIdInput] = useState("");
  const [showLoadByBmModal, setShowLoadByBmModal] = useState(false);
  const [loadByBmInput, setLoadByBmInput] = useState("");
  const [selectedViaId, setSelectedViaId] = useState<number | undefined>(initialViaId);
  const [currencyDisplay, setCurrencyDisplay] = useState<"ORIGINAL" | "VND" | "USD">("ORIGINAL");
  const [searchTerm, setSearchTerm] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 50;

  // Data state
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<AdsCheckResponse | null>(null);
  const [viasList, setViasList] = useState<ViaProfile[]>([]);
  const [clientPreferences, setClientPreferences] = useState<ClientBMPreference[]>([]);
  const [syncedBmsList, setSyncedBmsList] = useState<SyncedBM[]>([]);

  // Selection state
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([]);
  const [feedback, setFeedback] = useState<{ text: string; error?: boolean } | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [browserLaunchingId, setBrowserLaunchingId] = useState<string | null>(null);

  // Modals
  const [showRemoveAdminModal, setShowRemoveAdminModal] = useState(false);
  const [showRenameModal, setShowRenameModal] = useState(false);
  const [showSharePixelModal, setShowSharePixelModal] = useState(false);
  const [showSuperShareModal, setShowSuperShareModal] = useState(false);
  const [showExtendedPaymentModal, setShowExtendedPaymentModal] = useState(false);
  const [showSuperTargetModal, setShowSuperTargetModal] = useState(false);
  const [showExportDropdown, setShowExportDropdown] = useState(false);
  const [showExtensionModal, setShowExtensionModal] = useState(false);
  const [showSetCampModal, setShowSetCampModal] = useState(false);
  const [showCustomerSpendModal, setShowCustomerSpendModal] = useState(false);
  const [showWorkflowModal, setShowWorkflowModal] = useState(false);
  const [showRawViaModal, setShowRawViaModal] = useState(false);
  const [compactView, setCompactView] = useState(true);
  const [copyNotice, setCopyNotice] = useState<string | null>(null);
  const [batchProgress, setBatchProgress] = useState<{
    label: string;
    current: number;
    total: number;
  } | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const syncAbortRef = useRef<AbortController | null>(null);

  // Extended Payment Modal Form
  const [paymentActionType, setPaymentActionType] = useState<string>("PAY_NOW");
  const [paymentCardBrand, setPaymentCardBrand] = useState("VISA");
  const [paymentCardLast4, setPaymentCardLast4] = useState("8899");
  const [paymentAmount, setPaymentAmount] = useState("");
  const [invoiceResults, setInvoiceResults] = useState<NonNullable<Awaited<ReturnType<typeof extendedPaymentAction>>["invoices"]>>([]);

  // Rename modal states
  const [renamePrefix, setRenamePrefix] = useState("");
  const [renameSuffix, setRenameSuffix] = useState("");
  const [renameBaseName, setRenameBaseName] = useState("");
  const [renameCurrency, setRenameCurrency] = useState("");
  const [renameTimezone, setRenameTimezone] = useState("");
  const [renameCountry, setRenameCountry] = useState("");
  const [renameTaxStatus, setRenameTaxStatus] = useState("");

  // Share Pixel modal
  const [pixelIdInput, setPixelIdInput] = useState("");
  const [pixelBmId, setPixelBmId] = useState("");

  // Super Target & Appeal modal
  const [targetTab, setTargetTab] = useState<"interests" | "appeal">("interests");
  const [targetKeyword, setTargetKeyword] = useState("thời trang");
  const [targetResults, setTargetResults] = useState<NonNullable<Awaited<ReturnType<typeof superTargetAction>>["interests"]>>([]);
  const [appealReason, setAppealReason] = useState("Tài khoản hoạt động chuẩn chính sách, đề nghị Meta mở lại.");

  // Super Share modal
  const [shareClientId, setShareClientId] = useState<number | "">("");
  const [shareBmId, setShareBmId] = useState("");
  const [shareRole, setShareRole] = useState<"EMPLOYEE" | "ADMIN">("EMPLOYEE");
  const [shareAccessType, setShareAccessType] = useState<"FULL" | "PARTIAL">("FULL");
  const [sharePermissions, setSharePermissions] = useState<string[]>([
    "MANAGE_CAMPAIGNS",
    "VIEW_PERFORMANCE",
    "CREATIVE_HUB",
  ]);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  // Load initial dropdowns (VIAs, Client Preferences, BMs)
  useEffect(() => {
    async function loadDropdowns() {
      try {
        const [viaRes, prefRes, bmRes, custRes] = await Promise.all([
          getVias(),
          getClientBMPreferences().catch(() => []),
          getSyncedBMs().catch(() => ({ bms: [] })),
          fetchJson<{ id: number; name: string }[]>("/customers").catch(() => []),
        ]);
        setViasList(ensureArray<ViaProfile>(viaRes));
        setClientPreferences(ensureArray<ClientBMPreference>(prefRes));
        setSyncedBmsList(ensureArray<SyncedBM>(bmRes));
        setCustomersList(ensureArray<{ id: number; name: string }>(custRes));
      } catch (e) {
        console.error("Lỗi tải danh sách hỗ trợ ADSOS CHECK:", e);
      }
    }
    void loadDropdowns();
  }, []);

  // Load main table data
  const fetchData = async () => {
    try {
      setLoading(true);
      const res = await getAdsCheckData({
        tab: activeTab === "accounts" ? "accounts" : activeTab,
        via_id: selectedViaId,
        currency_display: currencyDisplay,
        search: searchTerm,
        status: statusFilterPill !== "ALL" ? statusFilterPill : undefined,
        account_type: typeFilter !== "ALL" ? typeFilter : undefined,
        card_status: cardFilter !== "ALL" ? cardFilter : undefined,
        bm_id: bmFilterId || undefined,
        account_ids: accountIdsFilter || undefined,
        mode: smitMode,
        page,
        page_size: pageSize,
      });
      setData(res);
      setSelectedAccountIds([]);
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi tải bảng ADSOS CHECK.",
        error: true,
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchData();
  }, [activeTab, selectedViaId, currencyDisplay, page, statusFilterPill, typeFilter, cardFilter, bmFilterId, accountIdsFilter, smitMode]);

  // Inline assign customer handler
  const handleInlineAssignCustomer = async (actId: string, custIdStr: string) => {
    const custId = custIdStr ? Number(custIdStr) : null;
    const targetCustomer = customersList.find((c) => c.id === custId);
    try {
      setActionLoading(true);
      const res = await assignAccountCustomer(actId, custId);
      if (res.success) {
        if (data?.items) {
          setData({
            ...data,
            items: data.items.map((acc) =>
              "act_id" in acc && acc.act_id === actId
                ? {
                    ...acc,
                    customer_id: custId,
                    customer_name: targetCustomer?.name || null,
                    is_assigned: Boolean(custId),
                  }
                : acc
            ),
          });
        }
        setFeedback({
          text: custId
            ? ` Đã gắn TKQC act_${actId} cho khách hàng [${targetCustomer?.name || custId}]`
            : `ℹ Đã hủy gắn khách cho TKQC act_${actId}`,
          error: false,
        });
      }
    } catch (err) {
      setFeedback({
        text: ` Lỗi khi gắn khách: ${err instanceof Error ? err.message : String(err)}`,
        error: true,
      });
    } finally {
      setActionLoading(false);
    }
  };

  // Search debounce
  useEffect(() => {
    const handler = setTimeout(() => {
      void fetchData();
    }, 400);
    return () => clearTimeout(handler);
  }, [searchTerm]);

  // Selection toggle
  const handleToggleSelectAll = () => {
    if (!data?.items?.length) return;
    if (selectedAccountIds.length === data.items.length) {
      setSelectedAccountIds([]);
    } else {
      const allIds = data.items.map(it => "act_id" in it ? it.act_id : "bm_id" in it ? it.bm_id : it.page_id);
      setSelectedAccountIds(allIds);
    }
  };

  const handleToggleRow = (id: string) => {
    setSelectedAccountIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  // 1-Click Launch Chrome for VIA
  const handleOpenInVia = async (
    item: { act_id?: string | null; bm_id?: string | null; page_id?: string | null; via_profile_id?: number | null },
    targetType: "ADS_MANAGER" | "BILLING" | "BM_SETTINGS" | "PAGE" | "FB_HOME" = "ADS_MANAGER"
  ) => {
    const idKey = item.act_id || item.bm_id || item.page_id || "browser";
    setBrowserLaunchingId(idKey);
    try {
      const res = await openInViaBrowser({
        act_id: item.act_id ?? undefined,
        bm_id: item.bm_id ?? undefined,
        page_id: item.page_id ?? undefined,
        via_id: item.via_profile_id ?? selectedViaId,
        target_type: targetType,
      });
      setFeedback({
        text: ` Đã mở Chrome VIA ${res.profile_name || res.via_uid} -> ${res.target_url}`,
      });
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi khi mở Chrome VIA.",
        error: true,
      });
    } finally {
      setBrowserLaunchingId(null);
    }
  };

  // Sync VIA Quick Action / Đồng bộ dữ liệu thật
  const handleTriggerSyncVia = async () => {
    if (!selectedViaId && viasList.length === 0) {
      setFeedback({ text: "Chưa có VIA nào trong hệ thống để đồng bộ.", error: true });
      return;
    }
    const targetViaId = selectedViaId || viasList[0].id;
    const controller = new AbortController();
    syncAbortRef.current?.abort();
    syncAbortRef.current = controller;
    try {
      setActionLoading(true);
      setBatchProgress({ label: "Đang xác thực phiên VIA và chuẩn bị đồng bộ...", current: 1, total: 3 });
      try {
        const harvest = await harvestViaSession(targetViaId, controller.signal);
        setBatchProgress({ label: "Đã xác thực phiên, đang nạp tài sản quảng cáo...", current: 2, total: 3 });
        if (harvest.success && harvest.token_status === "ACTIVE") {
          setFeedback({ text: ` ${harvest.message}` });
          setBatchProgress({ label: "Đồng bộ tài sản đã hoàn tất.", current: 3, total: 3 });
          await fetchData();
          return;
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name === "AbortError") throw err;
        // Fallthrough
      }
      const res = await syncViaAssets(targetViaId, controller.signal);
      setBatchProgress({ label: "Đồng bộ tài sản đã hoàn tất.", current: 3, total: 3 });
      setFeedback({ text: ` ${res.message}` });
      await fetchData();
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") {
        setFeedback({ text: "Đã hủy tác vụ đồng bộ theo yêu cầu." });
        setBatchProgress(null);
        return;
      }
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi khi đồng bộ tài sản VIA.",
        error: true,
      });
      setBatchProgress(null);
    } finally {
      setActionLoading(false);
      syncAbortRef.current = null;
    }
  };

  // Quick Action: Remove Hidden Admins
  const handleExecuteRemoveHiddenAdmins = async () => {
    try {
      setActionLoading(true);
      const res = await removeHiddenAdmins({
        account_ids: selectedAccountIds,
        via_id: selectedViaId,
      });
      setFeedback({ text: ` ${res.message}` });
      setShowRemoveAdminModal(false);
      await fetchData();
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi gỡ QTV ẩn.",
        error: true,
      });
    } finally {
      setActionLoading(false);
    }
  };

  // Quick Action: Rename Accounts
  const handleExecuteRename = async (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedAccountIds.length === 0) {
      setFeedback({ text: "Vui lòng chọn ít nhất một tài khoản để đổi thông tin.", error: true });
      return;
    }
    try {
      setActionLoading(true);
      const res = await renameAccounts({
        account_ids: selectedAccountIds,
        prefix: renamePrefix || undefined,
        suffix: renameSuffix || undefined,
        new_name: renameBaseName || undefined,
        currency: renameCurrency || undefined,
        timezone_name: renameTimezone || undefined,
        country_code: renameCountry || undefined,
        tax_status: renameTaxStatus || undefined,
      });
      setFeedback({ text: ` ${res.message}` });
      setShowRenameModal(false);
      setRenamePrefix("");
      setRenameSuffix("");
      setRenameBaseName("");
      setRenameCurrency("");
      setRenameTimezone("");
      setRenameCountry("");
      setRenameTaxStatus("");
      await fetchData();
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi đổi thông tin TKQC.",
        error: true,
      });
    } finally {
      setActionLoading(false);
    }
  };

  // Quick Action: Share Pixel
  const handleExecuteSharePixel = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pixelIdInput.trim()) {
      setFeedback({ text: "Vui lòng nhập Pixel ID.", error: true });
      return;
    }
    if (selectedAccountIds.length === 0) {
      setFeedback({ text: "Vui lòng chọn ít nhất một tài khoản nhận Pixel.", error: true });
      return;
    }
    try {
      setActionLoading(true);
      const res = await sharePixel({
        pixel_id: pixelIdInput.trim(),
        target_account_ids: selectedAccountIds,
        bm_id: pixelBmId.trim() || undefined,
      });
      setFeedback({ text: ` ${res.message}` });
      setShowSharePixelModal(false);
      setPixelIdInput("");
      await fetchData();
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi chia sẻ Pixel.",
        error: true,
      });
    } finally {
      setActionLoading(false);
    }
  };

  // Quick Action: Super Share Ads
  const handleExecuteSuperShareAds = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!shareClientId) {
      setFeedback({ text: "Vui lòng chọn khách hàng nhận tài khoản.", error: true });
      return;
    }
    if (selectedAccountIds.length === 0) {
      setFeedback({ text: "Vui lòng chọn ít nhất một tài khoản quảng cáo.", error: true });
      return;
    }
    try {
      setActionLoading(true);
      const res = await superShareAds({
        client_id: Number(shareClientId),
        account_ids: selectedAccountIds,
        bm_id: shareBmId.trim() || undefined,
        via_profile_id: selectedViaId,
        role: shareRole,
        access_type: shareAccessType,
        partial_permissions: shareAccessType === "PARTIAL" ? sharePermissions : undefined,
      });
      setFeedback({ text: ` ${res.message}` });
      setShowSuperShareModal(false);
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi Super Share Ads.",
        error: true,
      });
    } finally {
      setActionLoading(false);
    }
  };

  // Quick Action: Extended Payment
  const handleExecuteExtendedPayment = async (action: string) => {
    if (selectedAccountIds.length === 0) {
      setFeedback({ text: "Vui lòng chọn ít nhất một tài khoản để thực hiện thanh toán.", error: true });
      return;
    }
    try {
      setActionLoading(true);
      const amt = paymentAmount ? parseFloat(paymentAmount) : undefined;
      const res = await extendedPaymentAction({
        account_ids: selectedAccountIds,
        action,
        card_brand: paymentCardBrand,
        card_last4: paymentCardLast4,
        amount: amt,
      });
      setFeedback({ text: ` ${res.message}` });
      if (res.invoices && res.invoices.length > 0) {
        setInvoiceResults(res.invoices);
      } else {
        setShowExtendedPaymentModal(false);
        await fetchData();
      }
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi thực hiện thanh toán.",
        error: true,
      });
    } finally {
      setActionLoading(false);
    }
  };

  // Quick Action: Super Target & Appeal
  const handleExecuteSuperTarget = async (action: "SEARCH_INTERESTS" | "APPEAL_ACCOUNT") => {
    try {
      setActionLoading(true);
      if (action === "SEARCH_INTERESTS") {
        try {
          const res = await getSuperTargets(targetKeyword, 300);
          setTargetResults((res.data || []).map((item) => ({
            id: item.id,
            name: item.name,
            audience_size_lower_bound: item.audience_size_lower_bound || 0,
            audience_size_upper_bound: item.audience_size_upper_bound || 0,
            path: item.path || [],
            topic: item.topic || "Sở thích ẩn Meta",
          })));
          setFeedback({ text: ` Đã quét thấy ${res.total || res.data?.length || 0} sở thích ẩn Meta!` });
        } catch {
          const res = await superTargetAction({
            keyword: targetKeyword,
            action: "SEARCH_INTERESTS",
          });
          setTargetResults(res.interests || []);
          setFeedback({ text: ` ${res.message}` });
        }
      } else {
        if (selectedAccountIds.length === 0) {
          setFeedback({ text: "Vui lòng tick chọn ít nhất một tài khoản Die để gửi kháng nghị.", error: true });
          return;
        }
        const res = await superTargetAction({
          action: "APPEAL_ACCOUNT",
          account_ids: selectedAccountIds,
          appeal_reason: appealReason,
        });
        setFeedback({ text: ` ${res.message}` });
        setShowSuperTargetModal(false);
        await fetchData();
      }
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi thực hiện Super Target / Kháng nghị.",
        error: true,
      });
    } finally {
      setActionLoading(false);
    }
  };

  // Export helper
  const handleExportFile = (formatType: "csv" | "txt") => {
    setShowExportDropdown(false);
    const url = `/api/v1/vias/ads-check/export?tab=${activeTab}&via_id=${selectedViaId || ""}&format_type=${formatType}`;
    window.open(url, "_blank");
    setFeedback({ text: ` Đang xuất và tải xuống file ${formatType.toUpperCase()} dữ liệu ADSOS CHECK...` });
  };

  // Deterministic currency and number format helpers to prevent hydration mismatch
  const formatMoney = (val: number | null | undefined, curr: string = "VND") => {
    if (val == null) return "0";
    const num = Number(val);
    if (curr === "USD") {
      const parts = num.toFixed(2).split(".");
      parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
      return parts.join(".");
    }
    const rounded = String(Math.round(num));
    return rounded.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  };

  const formatInt = (val: number | null | undefined) => {
    if (val == null) return "0";
    return String(Math.round(Number(val))).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  };

  const copyText = (txt: string) => {
    void navigator.clipboard.writeText(txt);
    setCopyNotice("Đã sao chép ID!");
    if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    copyTimerRef.current = setTimeout(() => setCopyNotice(null), 1600);
  };

  const accountRows = useMemo(
    () => (data?.items || []).filter((item): item is SyncedAdAccount => "act_id" in item),
    [data?.items]
  );
  const activeVia = viasList.find((via) => via.id === selectedViaId) || viasList[0];
  const accountStats = useMemo(() => {
    const totals = {
      live: 0,
      warning: 0,
      die: 0,
      spentVnd: 0,
      spentUsd: 0,
      debtVnd: 0,
      debtUsd: 0,
      assignedDebtVnd: 0,
      assignedDebtUsd: 0,
    };
    for (const account of accountRows) {
      if (account.status_dot === "LIVE") totals.live += 1;
      else if (account.status_dot === "DIE") totals.die += 1;
      else totals.warning += 1;
      const currency = account.currency === "USD" ? "USD" : "VND";
      if (currency === "USD") {
        totals.spentUsd += Number(account.total_spend || 0);
        totals.debtUsd += Number(account.balance || 0);
        if (account.customer_id) totals.assignedDebtUsd += Number(account.balance || 0);
      } else {
        totals.spentVnd += Number(account.total_spend || 0);
        totals.debtVnd += Number(account.balance || 0);
        if (account.customer_id) totals.assignedDebtVnd += Number(account.balance || 0);
      }
    }
    return totals;
  }, [accountRows]);

  const triggerPrimaryWorkflow = () => {
    if (selectedAccountIds.length === 0) {
      setFeedback({ text: "Vui lòng chọn ít nhất một tài sản để chạy kịch bản.", error: true });
      return;
    }
    setShowWorkflowModal(true);
  };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const isTyping = target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.isContentEditable;
      if (!isTyping && event.key.toLowerCase() === "f") {
        event.preventDefault();
        searchInputRef.current?.focus();
        searchInputRef.current?.select();
        return;
      }
      if (event.key === "Escape") {
        const hasOverlay = showLoadByIdModal || showLoadByBmModal || showRemoveAdminModal || showRenameModal
          || showSharePixelModal || showSuperShareModal || showExtendedPaymentModal || showSuperTargetModal
          || showExportDropdown || showExtensionModal || showSetCampModal || showCustomerSpendModal || showWorkflowModal;
        setShowLoadByIdModal(false);
        setShowLoadByBmModal(false);
        setShowRemoveAdminModal(false);
        setShowRenameModal(false);
        setShowSharePixelModal(false);
        setShowSuperShareModal(false);
        setShowExtendedPaymentModal(false);
        setShowSuperTargetModal(false);
        setShowExportDropdown(false);
        setShowExtensionModal(false);
        setShowSetCampModal(false);
        setShowCustomerSpendModal(false);
        setShowWorkflowModal(false);
        if (!hasOverlay) setSelectedAccountIds([]);
      }
      if (!isTyping && (event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        triggerPrimaryWorkflow();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  useEffect(() => {
    if (!batchProgress || batchProgress.current < batchProgress.total) return;
    const timer = setTimeout(() => setBatchProgress(null), 2200);
    return () => clearTimeout(timer);
  }, [batchProgress]);

  return (
    <div className="w-full flex flex-col space-y-4">
      <header className="h-[60px] min-h-[60px] bg-[#1A1A1E] border-b border-[#2A2A32] px-4 sticky top-0 z-40 flex items-center gap-3 shadow-[0_8px_24px_rgba(0,0,0,0.28)]">
        <div className="min-w-[190px]">
          <h1 className="text-2xl leading-none font-bold text-white">ADSOS CHECK</h1>
          <p className="text-xs font-normal text-[#9CA3AF] mt-1">Trung tâm tài sản quảng cáo</p>
        </div>
        <label className="relative flex-1 max-w-xl">
          <svg aria-hidden="true" className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#9CA3AF]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
          </svg>
          <input
            ref={searchInputRef}
            type="search"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="Tìm ID tài khoản, tên, BM hoặc 4 số cuối thẻ..."
            className="h-9 w-full rounded-lg border border-[#2A2A32] bg-[#121214] pl-10 pr-12 text-sm font-medium text-white outline-none placeholder:text-[#6B7280] focus:border-[#2563EB]"
          />
          <kbd className="absolute right-3 top-1/2 -translate-y-1/2 rounded border border-[#3A3A42] bg-[#222228] px-1.5 py-0.5 text-[10px] text-[#9CA3AF]">F</kbd>
        </label>
        <div className="hidden xl:flex items-center gap-1">
          {[
            { key: "ALL", label: "Tất cả", count: accountRows.length, dot: "bg-[#9CA3AF]" },
            { key: "ACTIVE", label: "Live", count: accountStats.live, dot: "bg-[#10B981] shadow-[0_0_8px_rgba(16,185,129,0.5)]" },
            { key: "UNSETTLED", label: "Cảnh báo", count: accountStats.warning, dot: "bg-[#F59E0B] shadow-[0_0_8px_rgba(245,158,11,0.5)]" },
            { key: "DISABLED", label: "Die", count: accountStats.die, dot: "bg-[#EF4444] shadow-[0_0_8px_rgba(239,68,68,0.5)]" },
          ].map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => { setStatusFilterPill(item.key); setPage(1); }}
              className={`h-8 rounded-full border px-2.5 text-xs font-medium transition ${statusFilterPill === item.key ? "border-[#2563EB] bg-[#2563EB]/15 text-white" : "border-[#2A2A32] bg-[#202024] text-[#D1D5DB] hover:border-[#4A4A52]"}`}
            >
              <span className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${item.dot}`} />
              {item.label} {item.count}
            </button>
          ))}
        </div>
        <select
          value={selectedViaId ?? ""}
          onChange={(event) => { setSelectedViaId(event.target.value ? Number(event.target.value) : undefined); setPage(1); }}
          aria-label="Chọn VIA chính"
          className="hidden 2xl:block h-9 max-w-[220px] rounded-lg border border-[#2A2A32] bg-[#121214] px-3 text-xs font-medium text-white outline-none focus:border-[#2563EB]"
        >
          <option value="">Tất cả VIA</option>
          {viasList.map((via) => <option key={via.id} value={via.id}>{via.profile_name} · {via.uid}</option>)}
        </select>
        <div className="hidden 2xl:flex items-center gap-1 text-[10px]">
          <span className="rounded border border-[#3A3A42] bg-[#202024] px-2 py-1 text-[#D1D5DB]">{activeVia?.device_name || "Chrome"}</span>
          <span className="rounded border border-[#3A3A42] px-2 py-1 text-[#9CA3AF]">Cookie · Hồ sơ</span>
          <span className={`rounded border px-2 py-1 ${activeVia?.token_status === "ACTIVE" ? "border-[#10B981]/50 text-[#10B981]" : "border-[#3A3A42] text-[#6B7280]"}`}>EAAG</span>
          <span className={`rounded border px-2 py-1 ${activeVia?.token_status === "ACTIVE" ? "border-[#10B981]/50 text-[#10B981]" : "border-[#3A3A42] text-[#6B7280]"}`}>EAAB</span>
        </div>
        <button
          type="button"
          onClick={() => setShowSuperShareModal(true)}
          className="h-9 px-3.5 rounded-lg border border-indigo-500/60 bg-indigo-600/20 hover:bg-indigo-600/35 text-white flex items-center gap-1.5 text-xs font-semibold shadow-sm transition whitespace-nowrap ml-auto"
          title="Mở hộp thoại Chia sẻ quyền BM & Gán TKQC"
        >
          <svg className="w-4 h-4 text-indigo-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" />
          </svg>
          <span>Chia Sẻ Quyền BM &amp; Gán TKQC</span>
        </button>
      </header>

      {/* 4-PILLAR CONTROL HUB BROWSER NODES STATUS BAR */}
      <ControlHubNodesBar selectedAccountIds={selectedAccountIds} onActionComplete={(msg) => setFeedback({ text: msg, error: false })} />


      {batchProgress && (
        <div className="mx-4 -mt-2 rounded-lg border border-[#2A2A32] bg-[#1A1A1E] px-4 py-2 shadow-lg">
          <div className="mb-2 flex items-center justify-between gap-4 text-xs">
            <span className="font-medium text-[#D1D5DB]">{batchProgress.label} ({batchProgress.current}/{batchProgress.total})</span>
            {batchProgress.current < batchProgress.total && (
              <button type="button" onClick={() => syncAbortRef.current?.abort()} className="text-[#EF4444] hover:text-white"> Hủy lệnh</button>
            )}
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-[#2A2A32]">
            <div className={`h-full rounded-full transition-all duration-300 ${batchProgress.current >= batchProgress.total ? "bg-[#10B981]" : "bg-[#2563EB]"}`} style={{ width: `${Math.round((batchProgress.current / batchProgress.total) * 100)}%` }} />
          </div>
        </div>
      )}

      {copyNotice && <div className="fixed right-6 top-20 z-[80] rounded-lg border border-[#3A3A42] bg-[#1A1A1E] px-3 py-2 text-xs font-medium text-white shadow-xl">{copyNotice}</div>}

      {/* =========================================================================
          TOP HEADER BAR
          ========================================================================= */}
      <header className="hidden">
        {/* Left: Brand & Category Tabs */}
        <div className="flex items-center gap-6 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-xl"></span>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-white tracking-wide">ADSOS CHECK</span>
                <span className="text-[10px] uppercase font-bold tracking-widest px-1.5 py-0.5 rounded bg-[#1ed760]/15 text-[#1ed760] border border-[#1ed760]/30 rounded-full font-bold uppercase tracking-[1.4px]">
                  PRO
                </span>
              </div>
              <div className="text-[10px] text-gray-400">ADSOS CHECK — by FBP ADS</div>
            </div>
          </div>

          {/* Navigation Tabs (4 SMIT Tabs) */}
          <div className="flex items-center bg-[#121212] p-1 rounded-full border border-[#282828] gap-1">
            <button
              type="button"
              onClick={() => {
                setActiveTab("accounts");
                setPage(1);
              }}
              className={`px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-[1.4px] transition flex items-center gap-1.5 ${
                activeTab === "accounts" || activeTab === "personal" || activeTab === "bm"
                  ? "bg-[#1ed760] text-black font-bold shadow-md"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              <span></span>
              <span>Tài Khoản Quảng Cáo</span>
            </button>
            <button
              type="button"
              onClick={() => {
                setActiveTab("group");
                setPage(1);
              }}
              className={`px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-[1.4px] transition flex items-center gap-1.5 ${
                activeTab === "group"
                  ? "bg-[#1ed760] text-black font-bold shadow-md"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              <span></span>
              <span>Business Manager (BM)</span>
            </button>
            <button
              type="button"
              onClick={() => {
                setActiveTab("page");
                setPage(1);
              }}
              className={`px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-[1.4px] transition flex items-center gap-1.5 ${
                activeTab === "page"
                  ? "bg-[#1ed760] text-black font-bold shadow-md"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              <span></span>
              <span>Fanpage</span>
            </button>
            <button
              type="button"
              onClick={() => {
                setActiveTab("tasks");
                setPage(1);
              }}
              className={`px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-[1.4px] transition flex items-center gap-1.5 ${
                activeTab === "tasks"
                  ? "bg-[#1ed760] text-black font-bold shadow-md"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              <span></span>
              <span>Lịch Sử & Điều Phối Set Camp</span>
            </button>
          </div>

          {/* VIA Filter Dropdown */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400">VIA:</span>
            <select
              value={selectedViaId ?? ""}
              onChange={(e) => {
                const v = e.target.value ? Number(e.target.value) : undefined;
                setSelectedViaId(v);
                setPage(1);
              }}
              className="bg-[#0B0F19] border border-[#1F2937] text-white text-xs rounded-lg px-2.5 py-1.5 focus:border-indigo-500 focus:outline-none"
            >
              <option value="">Tất cả dàn VIA</option>
              {(viasList || []).map((via) => (
                <option key={via.id} value={via.id}>
                  {via.profile_name} (UID: {via.uid})
                </option>
              ))}
            </select>
          </div>

          {/* Search Input */}
          <div className="relative">
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Tìm kiếm tên, ID..."
              className="bg-[#0B0F19] border border-[#1F2937] text-white text-xs rounded-lg pl-7 pr-3 py-1.5 w-48 focus:w-60 transition-all focus:border-indigo-500 focus:outline-none"
            />
            <span className="absolute left-2.5 top-2 text-gray-500 text-xs"></span>
          </div>
        </div>

        {/* Right: Status, Currency switcher, Export & Scan Button */}
        <div className="flex items-center gap-3">
          {/* Scan Status Badge */}
          <div
            className="hidden lg:flex items-center gap-2 px-3 py-1.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs cursor-pointer hover:bg-emerald-500/20 transition"
            onClick={() => void fetchData()}
            title="Nhấp để quét lại dữ liệu"
          >
            <span className="animate-spin text-[10px]"></span>
            <span className="font-mono text-[11px]">System status: Scan VIA completed. Cookie/Token active.</span>
          </div>

          {/* Currency Toggle */}
          <div className="flex items-center bg-[#121212] p-0.5 rounded-full border border-[#282828] text-xs">
            <button
              type="button"
              onClick={() => setCurrencyDisplay("ORIGINAL")}
              className={`px-2 py-1 rounded text-[11px] font-medium transition ${
                currencyDisplay === "ORIGINAL" ? "bg-gray-800 text-white font-bold" : "text-gray-400"
              }`}
            >
              Gốc
            </button>
            <button
              type="button"
              onClick={() => setCurrencyDisplay("VND")}
              className={`px-2 py-1 rounded text-[11px] font-medium transition ${
                currencyDisplay === "VND" ? "bg-gray-800 text-white font-bold" : "text-gray-400"
              }`}
            >
              ₫ VND
            </button>
            <button
              type="button"
              onClick={() => setCurrencyDisplay("USD")}
              className={`px-2 py-1 rounded text-[11px] font-medium transition ${
                currencyDisplay === "USD" ? "bg-gray-800 text-white font-bold" : "text-gray-400"
              }`}
            >
              $ USD
            </button>
          </div>

          {/* Export File Dropdown */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowExportDropdown((prev) => !prev)}
              className="px-3.5 py-1.5 rounded-full text-xs font-bold uppercase tracking-[1.4px] bg-[#1f1f1f] hover:bg-[#282828] text-white border border-[#333333] transition flex items-center gap-1.5"
            >
              <span></span>
              <span>Xuất File</span>
            </button>

            {showExportDropdown && (
              <div className="absolute right-0 mt-1 w-36 bg-[#111827] border border-[#1F2937] rounded-xl shadow-2xl py-1 z-50 text-xs font-medium">
                <button
                  type="button"
                  onClick={() => handleExportFile("csv")}
                  className="w-full px-3 py-2 text-left text-gray-300 hover:bg-[#1A2234] hover:text-emerald-400 flex items-center gap-2"
                >
                  <span></span>
                  <span>Xuất CSV (Excel)</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleExportFile("txt")}
                  className="w-full px-3 py-2 text-left text-gray-300 hover:bg-[#1A2234] hover:text-indigo-400 flex items-center gap-2 border-t border-[#1F2937]"
                >
                  <span></span>
                  <span>Xuất TXT (Tab)</span>
                </button>
              </div>
            )}
          </div>

          {/* Nạp Nguyên Liệu & Quét Sâu Toàn Bộ */}
          <button
            type="button"
            onClick={() => setShowRawViaModal(true)}
            className="px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-[1.4px] bg-indigo-600 hover:bg-indigo-500 text-white transition flex items-center gap-1.5 shadow-md shadow-indigo-600/30"
            title="Nạp định dạng VIA thô (uid|pass|2fa|mail...), giải 2FA TOTP và tự động quét sâu toàn bộ TKQC, BM, Fanpage"
          >
            <svg className="w-3.5 h-3.5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            <span>Nạp VIA &amp; Quét Sâu</span>
          </button>

          {/*  Đồng Bộ Dữ Liệu Thật Button */}
          <button
            type="button"
            disabled={actionLoading}
            onClick={() => void handleTriggerSyncVia()}
            className="px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-[1.4px] bg-[#1ed760] hover:bg-[#1fdf64] text-black transition flex items-center gap-1.5 shadow-md disabled:opacity-50"
            title="Thu hoạch session từ Chrome qua CDP và đồng bộ tài sản thật"
          >
            <span></span>
            <span>Đồng Bộ Dữ Liệu Thật</span>
          </button>

          {/*  Extension ADSOS PRO */}
          <button
            type="button"
            onClick={() => setShowExtensionModal(true)}
            className="px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-[1.4px] bg-[#1f1f1f] hover:bg-[#282828] text-white border border-[#333333] transition flex items-center gap-1.5 shadow-sm"
            title="Tải & Quản lý Extension ADSOS CHECK PRO"
          >
            <span></span>
            <span>Extension PRO</span>
          </button>

          {/*  Auto Set Camp */}
          <button
            type="button"
            onClick={() => setShowSetCampModal(true)}
            className="px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-[1.4px] bg-[#1f1f1f] hover:bg-[#282828] text-[#ffa42b] border border-[#ffa42b]/30 transition flex items-center gap-1.5 shadow-sm"
            title="Quản lý Mẫu & Giao lệnh Auto Set Camp / Share từ xa"
          >
            <span></span>
            <span>Auto Set Camp</span>
          </button>

          {/*  Báo Cáo Chi Tiêu Khách Hàng (4% Phí) */}
          <button
            type="button"
            onClick={() => setShowCustomerSpendModal(true)}
            className="px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-[1.4px] bg-[#1f1f1f] hover:bg-[#282828] text-[#38bdf8] border border-[#38bdf8]/40 transition flex items-center gap-1.5 shadow-sm"
            title="Xem bảng kê chi tiêu và đối soát 4% phí dịch vụ cho từng khách hàng"
          >
            <span></span>
            <span>Báo Cáo 4% Phí</span>
          </button>

          <Link
            href="/vias"
            className="px-2.5 py-1.5 rounded-xl text-xs text-gray-400 hover:text-white bg-[#0B0F19] border border-[#1F2937] hover:border-gray-500 transition"
            title="Quay lại Dàn VIA"
          >
            Quản lý VIA ↗
          </Link>
        </div>
      </header>

      {/* Feedback banner */}
      {feedback && (
        <div
          className={`px-5 py-2.5 text-xs font-medium border-b flex items-center justify-between ${
            feedback.error
              ? "bg-rose-500/15 border-rose-500/30 text-rose-300"
              : "bg-emerald-500/15 border-emerald-500/30 text-emerald-300"
          }`}
        >
          <span>{feedback.text}</span>
          <button
            type="button"
            onClick={() => setFeedback(null)}
            className="text-gray-400 hover:text-white px-2"
          >
            
          </button>
        </div>
      )}

      {/* =========================================================================
          MAIN WORKSPACE: LEFT VERTICAL MENU + DATA TABLE
          ========================================================================= */}
      <div className="flex-1 flex overflow-hidden">
        <aside className="hidden lg:flex w-64 flex-shrink-0 flex-col justify-between border-r border-[#2A2A32] bg-[#1A1A1E] p-3 text-sm">
          <nav className="space-y-5">
            <div>
              <p className="mb-2 px-2 text-[10px] font-semibold tracking-[0.14em] text-[#6B7280]">QU&#7842;N L&#221; T&#192;I S&#7842;N</p>
              {[
                { label: "TKQC C\u00e1 nh\u00e2n", tab: "personal" as const },
                { label: "Doanh nghi\u1ec7p (BM)", tab: "group" as const },
                { label: "Fanpage", tab: "page" as const },
              ].map((item) => (
                <button key={item.tab} type="button" onClick={() => { setActiveTab(item.tab); setPage(1); }} className={`mb-1 flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-left text-xs font-medium transition ${activeTab === item.tab ? "border-[#4A4A52] bg-[#26262C] text-white" : "border-transparent text-[#D1D5DB] hover:bg-[#222228] hover:text-white"}`}>
                  <svg aria-hidden="true" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M7 8h10M7 12h6" /></svg>
                  {item.label}
                </button>
              ))}
              <button type="button" onClick={() => selectedAccountIds.length ? setShowSharePixelModal(true) : setFeedback({ text: "Vui l\u00f2ng ch\u1ecdn t\u00e0i kho\u1ea3n tr\u01b0\u1edbc khi chia s\u1ebb Pixel.", error: true })} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs font-medium text-[#D1D5DB] hover:bg-[#222228] hover:text-white">
                <svg aria-hidden="true" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="3" /><path d="M12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M19 5l-2 2M7 17l-2 2" /></svg>
                Pixel
              </button>
            </div>
            <div>
              <p className="mb-2 px-2 text-[10px] font-semibold tracking-[0.14em] text-[#6B7280]">&#272;I&#7872;U KHI&#7874;N V&#7852;N H&#192;NH</p>
              <button type="button" onClick={triggerPrimaryWorkflow} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs font-medium text-[#D1D5DB] hover:bg-[#222228] hover:text-white"><svg aria-hidden="true" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M4 6h10m-6 6h12M4 18h10" /><circle cx="17" cy="6" r="2" /><circle cx="5" cy="12" r="2" /><circle cx="17" cy="18" r="2" /></svg>69+ K&#7883;ch b&#7843;n Workflow</button>
              <button type="button" onClick={() => setShowSetCampModal(true)} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs font-medium text-[#D1D5DB] hover:bg-[#222228] hover:text-white"><svg aria-hidden="true" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M5 4v16M5 5h11l-2 4 2 4H5" /></svg>L&#234;n Camp H&#224;ng Lo&#7841;t</button>
              <button type="button" onClick={() => setShowSuperTargetModal(true)} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs font-medium text-[#D1D5DB] hover:bg-[#222228] hover:text-white"><svg aria-hidden="true" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /><path d="m15 9 6-6" /></svg>Super Target (S&#7903; th&#237;ch &#7849;n)</button>
            </div>
            <div>
              <p className="mb-2 px-2 text-[10px] font-semibold tracking-[0.14em] text-[#6B7280]">TI&#7878;N &#205;CH</p>
              <button type="button" onClick={() => setShowExportDropdown((value) => !value)} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs font-medium text-[#D1D5DB] hover:bg-[#222228] hover:text-white"><svg aria-hidden="true" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M4 7h16v13H4zM8 4h8v3" /></svg>Ads Save (Kho l&#432;u tr&#7919;)</button>
              <button type="button" onClick={() => selectedAccountIds.length ? setShowExtendedPaymentModal(true) : setFeedback({ text: "Vui l\u00f2ng ch\u1ecdn t\u00e0i kho\u1ea3n tr\u01b0\u1edbc khi qu\u1ea3n l\u00fd th\u1ebb.", error: true })} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs font-medium text-[#D1D5DB] hover:bg-[#222228] hover:text-white"><svg aria-hidden="true" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 10h18" /></svg>Extended Payment (Qu&#7843;n l&#253; th&#7867;)</button>
            </div>
          </nav>
          <div className="rounded-lg border border-[#2A2A32] bg-[#121214] p-3 text-xs text-[#9CA3AF]">
            <span className="block font-medium text-white">{selectedAccountIds.length} t&#224;i s&#7843;n &#273;&#227; ch&#7885;n</span>
            <span>Ph&#237;m t&#7855;t: F / Esc / Ctrl+Enter</span>
          </div>
        </aside>
        {/* Left Vertical Sub-Menu (ADSOS CHECK Toolbox) */}
        <aside className="hidden">
          <div className="space-y-1">
            <div className="px-2 py-1.5 text-[10px] font-bold text-gray-500 uppercase tracking-wider">
              ADSOS CHECK TOOLBOX
            </div>

            <button
              type="button"
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-full text-xs font-bold uppercase tracking-[1.2px] bg-[#1ed760]/15 text-[#1ed760] border border-[#1ed760]/30 shadow-sm text-left"
            >
              <span></span>
              <span>Bảng dữ liệu</span>
            </button>

            <button
              type="button"
              onClick={() => {
                if (selectedAccountIds.length === 0) {
                  setFeedback({ text: "Vui lòng tick chọn ít nhất một tài khoản để quản lý thanh toán.", error: true });
                } else {
                  setShowExtendedPaymentModal(true);
                }
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-full text-xs font-bold uppercase tracking-[1.2px] text-[#b3b3b3] hover:bg-[#1f1f1f] hover:text-white transition text-left"
            >
              <span></span>
              <span>Extended Payment</span>
              {selectedAccountIds.length > 0 && (
                <span className="ml-auto text-[10px] px-1.5 py-0.2 rounded-full bg-blue-500/30 text-blue-300">
                  {selectedAccountIds.length}
                </span>
              )}
            </button>

            <button
              type="button"
              onClick={() => {
                if (selectedAccountIds.length === 0) {
                  setFeedback({ text: "Vui lòng tick chọn ít nhất một tài khoản để xóa QTV ẩn.", error: true });
                } else {
                  setShowRemoveAdminModal(true);
                }
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-full text-xs font-bold uppercase tracking-[1.2px] text-[#b3b3b3] hover:bg-[#1f1f1f] hover:text-white transition text-left"
            >
              <span></span>
              <span>Xóa QTV Ẩn</span>
              {selectedAccountIds.length > 0 && (
                <span className="ml-auto text-[10px] px-1.5 py-0.2 rounded-full bg-rose-500/30 text-rose-300">
                  {selectedAccountIds.length}
                </span>
              )}
            </button>

            <button
              type="button"
              onClick={() => {
                if (selectedAccountIds.length === 0) {
                  setFeedback({ text: "Vui lòng tick chọn tài khoản để đổi thông tin.", error: true });
                } else {
                  setShowRenameModal(true);
                }
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-full text-xs font-bold uppercase tracking-[1.2px] text-[#b3b3b3] hover:bg-[#1f1f1f] hover:text-white transition text-left"
            >
              <span></span>
              <span>Đổi info TKQC</span>
            </button>

            <button
              type="button"
              onClick={() => {
                if (selectedAccountIds.length === 0) {
                  setFeedback({ text: "Vui lòng tick chọn tài khoản nhận Pixel.", error: true });
                } else {
                  setShowSharePixelModal(true);
                }
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-full text-xs font-bold uppercase tracking-[1.2px] text-[#b3b3b3] hover:bg-[#1f1f1f] hover:text-white transition text-left"
            >
              <span></span>
              <span>Share Pixel</span>
            </button>

            <button
              type="button"
              onClick={() => {
                if (selectedAccountIds.length === 0) {
                  setFeedback({ text: "Vui lòng tick chọn tài khoản để Super Share.", error: true });
                } else {
                  setShowSuperShareModal(true);
                }
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-full text-xs font-bold uppercase tracking-[1.2px] bg-[#1f1f1f] border border-[#333333] text-white hover:border-[#1ed760]/50 transition text-left shadow-sm"
            >
              <span></span>
              <span>Super Share Ads</span>
              <span className="ml-auto text-[9px] px-1 rounded bg-purple-500/30 text-purple-300 uppercase font-mono">
                Auto
              </span>
            </button>

            <button
              type="button"
              onClick={() => setShowSuperTargetModal(true)}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-amber-300 hover:bg-[#161F33] hover:text-amber-200 transition text-left"
            >
              <span></span>
              <span>Super Target &amp; Kháng</span>
            </button>
          </div>

          {/* Quick Selection Helper */}
          <div className="bg-[#111827] border border-[#1F2937] rounded-xl p-3 text-[11px] space-y-2">
            <div className="text-gray-400 flex items-center justify-between">
              <span>Đã chọn:</span>
              <span className="font-bold text-white font-mono">{selectedAccountIds.length} dòng</span>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleToggleSelectAll}
                className="flex-1 py-1 rounded bg-[#1F2937] hover:bg-gray-700 text-gray-200 text-[10px] transition"
              >
                {selectedAccountIds.length === (data?.items?.length || 0) ? "Bỏ chọn" : "Chọn hết"}
              </button>
              <button
                type="button"
                onClick={() => setSelectedAccountIds([])}
                className="px-2 py-1 rounded bg-[#1F2937] hover:bg-gray-700 text-gray-400 hover:text-white text-[10px] transition"
              >
                Hủy
              </button>
            </div>
          </div>
        </aside>

        {/* Center: Main High-Density Data Table */}
        <div className="flex-1 flex flex-col overflow-hidden bg-[#121214] w-full">
          <section className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 2xl:grid-cols-4">
            <article className="rounded-xl border border-[#2A2A32] bg-[#1A1A1E] p-4"><p className="text-xs font-normal text-[#9CA3AF]">T&#7893;ng T&#224;i Kho&#7843;n Live</p><div className="mt-2 flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-[#10B981] shadow-[0_0_8px_rgba(16,185,129,0.5)]" /><strong className="text-2xl font-bold tabular-nums text-[#10B981]">{accountStats.live}</strong></div></article>
            <article className="rounded-xl border border-[#2A2A32] bg-[#1A1A1E] p-4"><p className="text-xs font-normal text-[#9CA3AF]">T&#7893;ng T&#224;i Kho&#7843;n Die</p><div className="mt-2 flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-[#EF4444] shadow-[0_0_8px_rgba(239,68,68,0.5)]" /><strong className="text-2xl font-bold tabular-nums text-[#EF4444]">{accountStats.die}</strong></div></article>
            <article className="rounded-xl border border-[#2A2A32] bg-[#1A1A1E] p-4"><p className="text-xs font-normal text-[#9CA3AF]">T&#7893;ng Ti&#7873;n &#272;&#227; Ti&#234;u</p><div className="mt-2 text-sm font-semibold tabular-nums text-white"><span>{formatMoney(accountStats.spentVnd, "VND")}</span><span className="mx-2 text-[#4B5563]">|</span><span>{formatMoney(accountStats.spentUsd, "USD")}</span></div></article>
            <article className="rounded-xl border border-[#2A2A32] bg-[#1A1A1E] p-4"><p className="text-xs font-normal text-[#9CA3AF]">T&#7893;ng D&#432; N&#7907;</p><div className="mt-2 text-sm font-semibold tabular-nums text-[#F59E0B]"><span>{formatMoney(accountStats.assignedDebtVnd, "VND")}</span><span className="mx-2 text-[#4B5563]">|</span><span>{formatMoney(accountStats.assignedDebtUsd, "USD")}</span></div><p className="mt-1 text-[10px] text-[#6B7280]">&#272;&#227; g&#225;n kh&#225;ch / T&#7893;ng: {formatMoney(accountStats.debtVnd, "VND")} &#183; {formatMoney(accountStats.debtUsd, "USD")}</p></article>
          </section>
          <div className="flex flex-wrap items-center justify-between gap-3 border-y border-[#2A2A32] bg-[#1A1A1E] px-4 py-2.5">
            <div><span className="text-sm font-semibold text-white">{data?.total_count ?? accountRows.length} t&#224;i s&#7843;n</span><span className="ml-2 text-xs text-[#9CA3AF]">{selectedAccountIds.length} &#273;&#227; ch&#7885;n</span></div>
            <div className="flex items-center gap-3">
              <label className="flex cursor-pointer items-center gap-2 text-xs text-[#D1D5DB]"><span>Chế độ gọn</span><input type="checkbox" checked={compactView} onChange={(event) => setCompactView(event.target.checked)} className="peer sr-only" /><span className="relative h-5 w-9 rounded-full border border-[#3A3A42] bg-[#2A2A32] after:absolute after:left-0.5 after:top-0.5 after:h-3.5 after:w-3.5 after:rounded-full after:bg-[#9CA3AF] after:transition peer-checked:border-[#2563EB] peer-checked:bg-[#2563EB]/30 peer-checked:after:translate-x-4 peer-checked:after:bg-white" /></label>
              <button type="button" onClick={() => handleExportFile("csv")} className="flex h-8 items-center gap-2 rounded-lg border border-[#3A3A42] bg-[#202024] px-3 text-xs font-medium text-[#D1D5DB] hover:border-[#6B7280] hover:text-white"><svg aria-hidden="true" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 3v12m0 0 4-4m-4 4-4-4M5 19h14" /></svg>Xu&#7845;t CSV</button>
            </div>
          </div>
          {/* SMIT 4 LOAD MODES TOOLBAR */}
          <div className="bg-[#181818]/90 border-b border-[#282828] p-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 flex-wrap">
              <button
                type="button"
                onClick={() => setShowRawViaModal(true)}
                className="px-3.5 py-1.5 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white flex items-center gap-1.5 shadow-md shadow-indigo-600/30 transition"
                title="Nạp VIA định dạng Pipe, giải 2FA TOTP và quét sâu toàn bộ tài sản"
              >
                <svg className="w-3.5 h-3.5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
                <span>Nạp VIA &amp; Quét Sâu</span>
              </button>

              <span className="text-[11px] font-bold text-gray-400 uppercase tracking-wider ml-1">CHẾ ĐỘ TẢI SMIT:</span>
              <button
                type="button"
                onClick={() => {
                  setSmitMode("LOAD_ALL");
                  setAccountIdsFilter("");
                  setBmFilterId("");
                  setPage(1);
                  setFeedback({ text: " Đang tải tất cả tài khoản quảng cáo...", error: false });
                }}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition ${
                  smitMode === "LOAD_ALL" && !accountIdsFilter && !bmFilterId
                    ? "bg-[#1ed760] text-black font-bold shadow-md-md shadow-indigo-600/30"
                    : "bg-[#1f1f1f] text-[#b3b3b3] hover:text-white hover:bg-[#282828] border border-[#333333]"
                }`}
              >
                <span></span>
                <span>Tải Tất Cả (Load All)</span>
              </button>

              <button
                type="button"
                onClick={() => setShowLoadByIdModal(true)}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition ${
                  accountIdsFilter
                    ? "bg-[#539df5] text-black font-bold shadow-md"
                    : "bg-[#1f1f1f] text-[#b3b3b3] hover:text-white hover:bg-[#282828] border border-[#333333]"
                }`}
              >
                <span></span>
                <span>Tải Theo ID ({accountIdsFilter ? "Đang lọc" : "Load by ID"})</span>
              </button>

              <button
                type="button"
                onClick={() => setShowLoadByBmModal(true)}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition ${
                  bmFilterId
                    ? "bg-[#1ed760] text-black font-bold shadow-md"
                    : "bg-[#1f1f1f] text-[#b3b3b3] hover:text-white hover:bg-[#282828] border border-[#333333]"
                }`}
              >
                <span></span>
                <span>Tải Theo BM ({bmFilterId ? `BM: ${bmFilterId}` : "Load by BM"})</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  if (selectedViaId) {
                    setSmitMode("LOAD_BY_VIA_ID");
                    setPage(1);
                  } else {
                    setFeedback({ text: "Vui lòng chọn 1 VIA ở danh sách phía trên để tải theo VIA.", error: true });
                  }
                }}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition ${
                  smitMode === "LOAD_BY_VIA_ID" && selectedViaId
                    ? "bg-[#1ed760] text-black font-bold shadow-md"
                    : "bg-[#1f1f1f] text-[#b3b3b3] hover:text-white hover:bg-[#282828] border border-[#333333]"
                }`}
              >
                <span></span>
                <span>Tải Theo VIA</span>
              </button>
            </div>

            {/* Active Filters Clear Badge */}
            {(bmFilterId || accountIdsFilter) && (
              <div className="flex items-center gap-2">
                {bmFilterId && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-purple-950/80 border border-purple-500/40 text-purple-300 text-[11px] font-mono">
                    <span>BM: {bmFilterId}</span>
                    <button onClick={() => setBmFilterId("")} className="hover:text-white ml-1"></button>
                  </span>
                )}
                {accountIdsFilter && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-sky-950/80 border border-sky-500/40 text-sky-300 text-[11px] font-mono">
                    <span>Lọc {accountIdsFilter.split(",").length} IDs</span>
                    <button onClick={() => setAccountIdsFilter("")} className="hover:text-white ml-1"></button>
                  </span>
                )}
              </div>
            )}
          </div>

          {/* SMIT SUB-FILTERS (FOR AD ACCOUNTS TAB) */}
          {(activeTab === "accounts" || activeTab === "personal" || activeTab === "bm") && (
            <div className="bg-[#0B0F19] border-b border-[#1F2937] px-4 py-2 flex flex-wrap items-center justify-between gap-3 text-xs">
              {/* Status Filter Pills */}
              <div className="flex items-center gap-1.5 overflow-x-auto">
                <span className="text-[11px] text-gray-500 font-medium">Trạng thái:</span>
                {[
                  { key: "ALL", label: "Tất cả" },
                  { key: "ACTIVE", label: " Hoạt động" },
                  { key: "DISABLED", label: " Vô hiệu hóa" },
                  { key: "UNSETTLED", label: " Đang nợ" },
                  { key: "IN_REVIEW", label: " Đang xét duyệt" },
                ].map((pill) => (
                  <button
                    key={pill.key}
                    type="button"
                    onClick={() => {
                      setStatusFilterPill(pill.key);
                      setPage(1);
                    }}
                    className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold transition ${
                      statusFilterPill === pill.key
                        ? "bg-slate-200 text-slate-900 shadow"
                        : "bg-[#1f1f1f] text-[#b3b3b3] hover:text-white hover:bg-[#282828] border border-[#333333]"
                    }`}
                  >
                    {pill.label}
                  </button>
                ))}
              </div>

              {/* Type Filter & Card Filter */}
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1">
                  <span className="text-[11px] text-gray-500">Loại:</span>
                  <select
                    value={typeFilter}
                    onChange={(e) => {
                      setTypeFilter(e.target.value);
                      setPage(1);
                    }}
                    className="bg-[#1E293B] border border-slate-700 text-slate-200 text-[11px] rounded-lg px-2 py-1 focus:outline-none"
                  >
                    <option value="ALL">Tất cả loại TK</option>
                    <option value="PERSONAL">TK Cá nhân (Personal)</option>
                    <option value="BM">TK Doanh nghiệp (BM)</option>
                  </select>
                </div>

                <div className="flex items-center gap-1">
                  <span className="text-[11px] text-gray-500">Thẻ:</span>
                  <select
                    value={cardFilter}
                    onChange={(e) => {
                      setCardFilter(e.target.value);
                      setPage(1);
                    }}
                    className="bg-[#1E293B] border border-slate-700 text-slate-200 text-[11px] rounded-lg px-2 py-1 focus:outline-none"
                  >
                    <option value="ALL">Tất cả thẻ</option>
                    <option value="HAS_CARD">Có thẻ</option>
                    <option value="NO_CARD">Chưa gắn thẻ</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          <div className="flex-1 overflow-auto">
            {loading ? (
              <div className="p-12 text-center text-sm text-gray-400 flex flex-col items-center justify-center gap-3">
                <span className="text-3xl animate-spin"></span>
                <span>Đang quét sâu tài sản ADSOS CHECK...</span>
              </div>
            ) : !data?.items || data.items.length === 0 ? (
              <div className="p-12 text-center text-sm text-gray-400 flex flex-col items-center justify-center gap-2">
                <span className="text-4xl"></span>
                <span className="font-semibold text-gray-300">Không có dữ liệu trong mục này</span>
                <span className="text-xs text-gray-500">
                  Hãy nhấn &quot;Đồng Bộ Dữ Liệu Thật&quot; để nạp tài khoản quảng cáo, Business Manager hoặc Page.
                </span>
                <button
                  type="button"
                  onClick={() => void handleTriggerSyncVia()}
                  className="mt-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition flex items-center gap-1.5"
                >
                  <span></span>
                  <span>Đồng Bộ Dữ Liệu Thật</span>
                </button>
              </div>
            ) : (activeTab === "accounts" || activeTab === "personal" || activeTab === "bm") ? (
              /* =========================================================================
                 TABLE FOR AD ACCOUNTS (PERSONAL & BM)
                 ========================================================================= */
              <table className="w-full min-w-[1760px] border-collapse text-left text-sm font-medium tabular-nums">
                <thead className="sticky top-0 z-20 border-b border-[#2A2A32] bg-[#1A1A1E] text-[11px] font-semibold uppercase tracking-[0.08em] text-[#9CA3AF]">
                  <tr>
                    <th className="sticky left-0 z-30 w-10 bg-[#1A1A1E] px-3 py-2.5 text-center">
                      <input
                        type="checkbox"
                        checked={
                          data.items.length > 0 && selectedAccountIds.length === data.items.length
                        }
                        onChange={handleToggleSelectAll}
                        className="rounded border-gray-700 bg-gray-900 text-indigo-500 focus:ring-0 cursor-pointer"
                      />
                    </th>
                    <th className="py-2.5 px-2 w-10 text-center text-[11px] font-medium">STT</th>
                    <th className="sticky left-10 z-30 min-w-[250px] bg-[#1A1A1E] px-3 py-2.5 text-[11px] font-medium">Tài khoản QC / BM cha</th>
                    <th className="min-w-[110px] px-3 py-2.5 text-[11px] font-medium">Trạng thái</th>
                    <th className="py-2.5 px-3 min-w-[170px] text-[11px] font-medium"> Khách Hàng Gắn Kết</th>
                    <th className="py-2.5 px-3 text-right text-[11px] font-medium">Số dư</th>
                    <th className="py-2.5 px-3 text-right text-[11px] font-medium">Ngưỡng</th>
                    <th className="py-2.5 px-3 text-right text-[11px] font-medium">Ngưỡng còn lại</th>
                    <th className="py-2.5 px-3 text-right text-[11px] font-medium">Limit</th>
                    <th className="py-2.5 px-3 text-right text-[11px] font-medium">Tổng tiêu</th>
                    <th className="py-2.5 px-2 text-center text-[11px] font-medium">Tiền tệ</th>
                    <th className="py-2.5 px-3 text-center text-[11px] font-medium">Thẻ</th>
                    <th className="py-2.5 px-2 text-center text-[11px] font-medium">Lý do / Quyền</th>
                    <th className="py-2.5 px-2 text-center text-[11px] font-medium">Múi giờ / QG</th>
                    <th className="py-2.5 px-2 text-center text-[11px] font-medium">QTV (Ẩn)</th>
                    <th className="sticky right-0 z-30 min-w-[210px] bg-[#1A1A1E] px-3 py-2.5 text-center text-[11px] font-medium">Thao tác nhanh</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#2A2A32] bg-[#121214] text-sm font-medium">
                  {(data.items as SyncedAdAccount[]).map((acc: SyncedAdAccount, idx: number) => {
                    const isSelected = selectedAccountIds.includes(acc.act_id);
                    const statusDotClass =
                      acc.status_dot === "LIVE"
                        ? "bg-[#10B981] shadow-[0_0_8px_rgba(16,185,129,0.5)]"
                        : acc.status_dot === "WARNING"
                        ? "bg-[#F59E0B] shadow-[0_0_8px_rgba(245,158,11,0.5)]"
                        : "bg-[#EF4444] shadow-[0_0_8px_rgba(239,68,68,0.5)]";

                    return (
                      <tr
                        key={acc.act_id || idx}
                        onClick={() => handleToggleRow(acc.act_id)}
                        className={`group cursor-pointer select-none transition hover:bg-[#202024] ${
                          isSelected ? "bg-[#2563EB]/10" : ""
                        }`}
                      >
                        <td
                          className={`${compactView ? "py-1.5" : "py-3"} sticky left-0 z-10 bg-[#1A1A1E] px-3 text-center group-hover:bg-[#202024]`}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => handleToggleRow(acc.act_id)}
                            className="rounded border-gray-700 bg-gray-900 text-indigo-500 focus:ring-0 cursor-pointer"
                          />
                        </td>
                        <td className="py-2.5 px-2 text-center text-gray-500 font-sans">
                          {(page - 1) * pageSize + idx + 1}
                        </td>

                        {/* Tài khoản: Status Dot + 2 Lines + 1-Click to Ads Manager */}
                        <td className={`${compactView ? "py-1.5" : "py-3"} sticky left-10 z-10 bg-[#1A1A1E] px-3 group-hover:bg-[#202024]`}>
                          <div className="flex items-start gap-2.5">
                            <span
                              className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${statusDotClass}`}
                              title={`Trạng thái: ${acc.status_dot}`}
                            />
                            <div>
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  void handleOpenInVia(acc, "ADS_MANAGER");
                                }}
                                className="text-white font-semibold font-sans text-xs tracking-tight hover:text-indigo-300 transition text-left flex items-center gap-1.5"
                                title="1-Click mở Chrome VIA vào Ads Manager của tài khoản này"
                              >
                                <span>{acc.name}</span>
                                <span className="text-[10px] text-indigo-400 opacity-80 hover:opacity-100">↗</span>
                              </button>
                              <div className="flex items-center gap-1.5 text-[10px] text-gray-400 mt-0.5">
                                <span
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    void handleOpenInVia(acc, "ADS_MANAGER");
                                  }}
                                  className="hover:underline hover:text-white cursor-pointer"
                                  title="Mở Ads Manager"
                                >
                                  {acc.act_id}
                                </span>
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    copyText(acc.act_id);
                                  }}
                                  className="opacity-0 text-[#9CA3AF] transition hover:text-white group-hover:opacity-100"
                                  title="Sao chép ID"
                                >
                                  <svg aria-hidden="true" className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="8" y="8" width="11" height="11" rx="2" /><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" /></svg>
                                </button>
                                {acc.via_profile_name && (
                                  <span className="text-gray-500 font-sans">
                                    • {acc.via_profile_name}
                                  </span>
                                )}
                              </div>
                              {acc.bm_id && <button type="button" onClick={(event) => { event.stopPropagation(); copyText(acc.bm_id || ""); }} className="mt-1 rounded border border-[#3A3A42] bg-[#202024] px-1.5 py-0.5 text-[9px] text-[#9CA3AF] hover:text-white" title="Sao chép BM ID">BM {acc.bm_id}</button>}
                            </div>
                          </div>
                        </td>

                        <td className={`${compactView ? "py-1.5" : "py-3"} px-3`}><span className="inline-flex items-center gap-2 text-xs text-[#D1D5DB]"><span className={`h-2 w-2 rounded-full ${statusDotClass}`} />{acc.status_dot === "LIVE" ? "Live" : acc.status_dot === "WARNING" ? "Cảnh báo" : "Die"}</span></td>

                        {/*  Khách Hàng Gắn Kết (Inline Selector) */}
                        <td className="py-2 px-3" onClick={(e) => e.stopPropagation()}>
                          <select
                            value={acc.customer_id ? String(acc.customer_id) : ""}
                            onChange={(e) => void handleInlineAssignCustomer(acc.act_id, e.target.value)}
                            className={`w-full text-[11px] font-semibold rounded-lg px-2 py-1 border transition focus:outline-none ${
                              acc.customer_id
                                ? "bg-indigo-950/60 border-indigo-500/50 text-indigo-200"
                                : "bg-slate-900 border-slate-700 text-slate-400 italic"
                            }`}
                          >
                            <option value=""> Chưa gán khách</option>
                            {(customersList || []).map((c) => (
                              <option key={c.id} value={String(c.id)} className="bg-slate-900 text-white not-italic">
                                 {c.name}
                              </option>
                            ))}
                          </select>
                        </td>

                        {/* Số dư */}
                        <td className="py-2.5 px-3 text-right font-medium text-emerald-400" suppressHydrationWarning>
                          {formatMoney(acc.balance, acc.currency)}
                        </td>

                        {/* Ngưỡng */}
                        <td className="py-2.5 px-3 text-right text-gray-200" suppressHydrationWarning>
                          {formatMoney(acc.threshold, acc.currency)}
                        </td>

                        <td className="py-2.5 px-3 text-right text-[#D1D5DB]" suppressHydrationWarning>{formatMoney(Math.max(Number(acc.threshold || 0) - Number(acc.balance || 0), 0), acc.currency)}</td>

                        {/* Limit (ad_trust_dsl) */}
                        <td className="py-2.5 px-3 text-right text-amber-300 font-semibold" suppressHydrationWarning>
                          {acc.ad_trust_dsl > 0
                            ? formatMoney(acc.ad_trust_dsl, acc.currency)
                            : "NOLIMIT"}
                        </td>

                        {/* Tổng tiêu */}
                        <td className="py-2.5 px-3 text-right text-gray-300" suppressHydrationWarning>
                          {formatMoney(acc.total_spend, acc.currency)}
                        </td>

                        {/* Tiền tệ */}
                        <td className="py-2.5 px-2 text-center">
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-[#1F2937] text-gray-300 border border-gray-700">
                            {acc.currency}
                          </span>
                        </td>

                        {/* Thẻ thanh toán */}
                        <td className="py-2.5 px-3 text-center">
                          {acc.payment_card_brand ? (
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-blue-500/10 text-blue-300 border border-blue-500/20 whitespace-nowrap">
                              {acc.card_display}
                            </span>
                          ) : (
                            <span className="text-gray-500 text-[10px]">Chưa gắn</span>
                          )}
                        </td>

                        {/* Lý do / Quyền */}
                        <td className="py-2.5 px-2 text-center font-sans text-[10px]">
                          <div className="flex flex-col items-center gap-0.5">
                            <span
                              className={`px-1.5 py-0.2 rounded font-semibold ${
                                (acc.disable_reason || "NONE") === "NONE"
                                  ? "bg-gray-800 text-gray-400"
                                  : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                              }`}
                            >
                              {acc.disable_reason || "NONE"}
                            </span>
                            <span className="text-gray-400 text-[9px]">{acc.user_role || "ADMIN"}</span>
                          </div>
                        </td>

                        {/* Múi giờ / Quốc gia */}
                        <td className="py-2.5 px-2 text-center font-sans text-[10px] text-gray-300 whitespace-nowrap">
                          <div>{acc.country_code || "VN"}</div>
                          <div className="text-[9px] text-gray-500 truncate max-w-[80px]" title={acc.timezone_name}>
                            {acc.timezone_name ? acc.timezone_name.split("|")[0].trim() : "GMT+7"}
                          </div>
                        </td>

                        {/* QTV (Ẩn) */}
                        <td className="py-2.5 px-2 text-center font-sans text-[10px]">
                          <span className="font-semibold text-gray-200">{acc.admin_count ?? 1} QTV</span>
                          {(acc.hidden_admin_count ?? 0) > 0 && (
                            <div className="text-[9px] font-bold text-rose-400 animate-pulse">
                              ({acc.hidden_admin_count} ẩn)
                            </div>
                          )}
                        </td>

                        {/* Thao tác nhanh */}
                        <td
                          className={`${compactView ? "py-1.5" : "py-3"} sticky right-0 z-10 bg-[#1A1A1E] px-3 text-center group-hover:bg-[#202024]`}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <div className="flex items-center justify-center gap-1">
                            <button
                              type="button"
                              onClick={() => { setSelectedAccountIds([acc.act_id]); setShowSuperShareModal(true); }}
                              className="rounded border border-[#3A3A42] hover:border-indigo-500 px-2 py-1 text-[10px] text-indigo-400 hover:text-white flex items-center gap-1"
                              title="Chia sẻ quyền BM & gán TKQC này"
                            >
                              <svg className="w-3 h-3 text-indigo-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
                                <circle cx="9" cy="7" r="4" />
                                <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
                                <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                              </svg>
                              <span>Share BM / Gán TK</span>
                            </button>
                            <button
                              type="button"
                              onClick={() => { setSelectedAccountIds([acc.act_id]); setShowSuperTargetModal(true); }}
                              className="rounded border border-[#3A3A42] px-2 py-1 text-[10px] text-[#D1D5DB] hover:border-[#EF4444] hover:text-white"
                            >
                              Kháng
                            </button>
                            <button
                              type="button"
                              onClick={() => { setSelectedAccountIds([acc.act_id]); setShowRenameModal(true); }}
                              className="rounded border border-[#3A3A42] px-2 py-1 text-[10px] text-[#D1D5DB] hover:border-[#6B7280] hover:text-white"
                            >
                              Đổi tên
                            </button>
                            <button type="button" onClick={() => { setSelectedAccountIds([acc.act_id]); setShowRemoveAdminModal(true); }} className="rounded border border-[#3A3A42] px-2 py-1 text-[10px] text-[#D1D5DB] hover:border-[#6B7280] hover:text-white">Soi QTV</button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : activeTab === "group" ? (
              /* =========================================================================
                 TABLE FOR GROUP (BUSINESS MANAGERS)
                 ========================================================================= */
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-[#1f1f1f] text-[#b3b3b3] sticky top-0 z-10 border-b border-[#282828] shadow-sm select-none uppercase tracking-[1.4px] text-[11px] font-bold">
                  <tr>
                    <th className="py-2.5 px-3 w-10 text-center">
                      <input
                        type="checkbox"
                        checked={
                          data.items.length > 0 && selectedAccountIds.length === data.items.length
                        }
                        onChange={handleToggleSelectAll}
                        className="rounded border-gray-700 bg-gray-900 text-indigo-500 focus:ring-0 cursor-pointer"
                      />
                    </th>
                    <th className="py-2.5 px-2 w-12 text-center text-[11px] font-medium">STT</th>
                    <th className="py-2.5 px-3 min-w-[240px] text-[11px] font-medium">Tên BM</th>
                    <th className="py-2.5 px-3 text-[11px] font-medium">BM ID</th>
                    <th className="py-2.5 px-3 text-center text-[11px] font-medium">Limit BM</th>
                    <th className="py-2.5 px-3 text-center text-[11px] font-medium">Xác minh</th>
                    <th className="py-2.5 px-3 text-center text-[11px] font-medium">BM Cho Thuê</th>
                    <th className="py-2.5 px-3 text-right text-[11px] font-medium">Số TKQC</th>
                    <th className="py-2.5 px-3 text-right text-[11px] font-medium">Số Page</th>
                    <th className="py-2.5 px-3 text-center text-[11px] font-medium">Hồ sơ VIA</th>
                    <th className="py-2.5 px-3 text-center text-[11px] font-medium">Thao tác</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1F2937]/50 font-mono text-[11px]">
                  {(data.items as SyncedBM[]).map((bm: SyncedBM, idx: number) => {
                    const isSelected = selectedAccountIds.includes(bm.bm_id);
                    const isLaunching = browserLaunchingId === bm.bm_id;
                    return (
                      <tr
                        key={bm.bm_id || idx}
                        onClick={() => handleToggleRow(bm.bm_id)}
                        className={`hover:bg-[#161F33] transition cursor-pointer select-none ${
                          isSelected ? "bg-indigo-950/30" : ""
                        }`}
                      >
                        <td
                          className="py-2.5 px-3 text-center"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => handleToggleRow(bm.bm_id)}
                            className="rounded border-gray-700 bg-gray-900 text-indigo-500 focus:ring-0 cursor-pointer"
                          />
                        </td>
                        <td className="py-2.5 px-2 text-center text-gray-500 font-sans">
                          {(page - 1) * pageSize + idx + 1}
                        </td>
                        <td className="py-2.5 px-3">
                          <div className="text-white font-semibold font-sans text-xs flex items-center gap-2">
                            <span>{bm.name}</span>
                            {bm.is_primary_rental && (
                              <span className="text-[10px] px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
                                 Cho Thuê
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-2.5 px-3 text-gray-300">
                          <div className="flex items-center gap-1.5">
                            <span>{bm.bm_id}</span>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                copyText(bm.bm_id);
                              }}
                              className="text-gray-500 hover:text-white"
                            >
                              
                            </button>
                          </div>
                        </td>
                        <td className="py-2.5 px-3 text-center">
                          <span className="px-2 py-0.5 rounded font-bold text-[10px] bg-purple-500/20 text-purple-300 border border-purple-500/30">
                            {bm.bm_level || "NOLIMIT"}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-center font-sans text-[10px]">
                          <span
                            className={`px-1.5 py-0.2 rounded font-semibold ${
                              (bm.verified_status || "VERIFIED") === "VERIFIED"
                                ? "bg-emerald-500/20 text-emerald-300"
                                : "bg-gray-800 text-gray-400"
                            }`}
                          >
                            {bm.verified_status || "VERIFIED"}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-center">
                          {bm.is_primary_rental ? (
                            <span className="text-amber-400 font-bold"> CHÍNH</span>
                          ) : (
                            <span className="text-gray-500">—</span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 text-right text-blue-300 font-bold">
                          {bm.ad_account_count}
                        </td>
                        <td className="py-2.5 px-3 text-right text-emerald-300 font-bold">
                          {bm.page_count}
                        </td>
                        <td className="py-2.5 px-3 text-center text-gray-400 font-sans text-[10px]">
                          {bm.via_profile_name || "—"}
                        </td>
                        <td
                          className="py-2.5 px-3 text-center"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <div className="flex items-center justify-center gap-1.5">
                            <button
                              type="button"
                              onClick={() => {
                                setActiveTab("accounts");
                                setBmFilterId(bm.bm_id);
                                setPage(1);
                              }}
                              className="px-2 py-1 rounded-lg text-[10px] font-semibold bg-slate-800 border border-slate-700 text-sky-300 hover:bg-slate-700 transition flex items-center gap-1"
                              title="Xem toàn bộ tài khoản quảng cáo thuộc BM này"
                            >
                              <span></span>
                              <span>Xem TKQC</span>
                            </button>
                            <button
                              type="button"
                              disabled={isLaunching}
                              onClick={() => void handleOpenInVia({ bm_id: bm.bm_id, via_profile_id: bm.via_profile_id ?? undefined }, "BM_SETTINGS")}
                              className="px-2 py-1 rounded-lg text-[10px] font-semibold bg-indigo-950/80 border border-indigo-500/40 text-indigo-300 hover:bg-indigo-900/50 transition flex items-center gap-1 disabled:opacity-50"
                              title="1-Click mở Chrome VIA vào Business Settings của BM này"
                            >
                              <span>{isLaunching ? "" : ""}</span>
                              <span>Mở BM</span>
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              /* =========================================================================
                 TABLE FOR FANPAGES
                 ========================================================================= */
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-[#1f1f1f] text-[#b3b3b3] sticky top-0 z-10 border-b border-[#282828] shadow-sm select-none uppercase tracking-[1.4px] text-[11px] font-bold">
                  <tr>
                    <th className="py-2.5 px-3 w-10 text-center">
                      <input
                        type="checkbox"
                        checked={
                          data.items.length > 0 && selectedAccountIds.length === data.items.length
                        }
                        onChange={handleToggleSelectAll}
                        className="rounded border-gray-700 bg-gray-900 text-indigo-500 focus:ring-0 cursor-pointer"
                      />
                    </th>
                    <th className="py-2.5 px-2 w-12 text-center text-[11px] font-medium">STT</th>
                    <th className="py-2.5 px-3 min-w-[260px] text-[11px] font-medium">Tên Fanpage</th>
                    <th className="py-2.5 px-3 text-[11px] font-medium">Page ID</th>
                    <th className="py-2.5 px-3 text-[11px] font-medium">Danh mục</th>
                    <th className="py-2.5 px-3 text-right text-[11px] font-medium">Lượt thích</th>
                    <th className="py-2.5 px-3 text-right text-[11px] font-medium">Theo dõi</th>
                    <th className="py-2.5 px-3 text-center text-[11px] font-medium">Trạng thái</th>
                    <th className="py-2.5 px-3 text-center text-[11px] font-medium">Hồ sơ VIA</th>
                    <th className="py-2.5 px-3 text-center text-[11px] font-medium">Thao tác</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1F2937]/50 font-mono text-[11px]">
                  {(data.items as SyncedPageItem[]).map((pg: SyncedPageItem, idx: number) => {
                    const isSelected = selectedAccountIds.includes(pg.page_id);
                    const isLaunching = browserLaunchingId === pg.page_id;
                    return (
                      <tr
                        key={pg.page_id || idx}
                        onClick={() => handleToggleRow(pg.page_id)}
                        className={`hover:bg-[#161F33] transition cursor-pointer select-none ${
                          isSelected ? "bg-indigo-950/30" : ""
                        }`}
                      >
                        <td
                          className="py-2.5 px-3 text-center"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => handleToggleRow(pg.page_id)}
                            className="rounded border-gray-700 bg-gray-900 text-indigo-500 focus:ring-0 cursor-pointer"
                          />
                        </td>
                        <td className="py-2.5 px-2 text-center text-gray-500 font-sans">
                          {(page - 1) * pageSize + idx + 1}
                        </td>
                        <td className="py-2.5 px-3 text-white font-semibold font-sans text-xs">
                          {pg.name}
                        </td>
                        <td className="py-2.5 px-3 text-gray-300">
                          <div className="flex items-center gap-1.5">
                            <span>{pg.page_id}</span>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                copyText(pg.page_id);
                              }}
                              className="text-gray-500 hover:text-white"
                            >
                              
                            </button>
                          </div>
                        </td>
                        <td className="py-2.5 px-3 text-gray-400 font-sans text-[10px]">
                          {pg.category}
                        </td>
                        <td className="py-2.5 px-3 text-right text-blue-300 font-bold" suppressHydrationWarning>
                          {formatInt(pg.likes_count)}
                        </td>
                        <td className="py-2.5 px-3 text-right text-emerald-300 font-bold" suppressHydrationWarning>
                          {formatInt(pg.followers_count)}
                        </td>
                        <td className="py-2.5 px-3 text-center">
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                            {pg.is_published ? "PUBLISHED" : "UNPUBLISHED"}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-center text-gray-400 font-sans text-[10px]">
                          {pg.via_profile_name || "—"}
                        </td>
                        <td
                          className="py-2.5 px-3 text-center"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            type="button"
                            disabled={isLaunching}
                            onClick={() => void handleOpenInVia({ page_id: pg.page_id, via_profile_id: pg.via_profile_id }, "PAGE")}
                            className="px-2 py-1 rounded-lg text-[10px] font-semibold bg-indigo-950/80 border border-indigo-500/40 text-indigo-300 hover:bg-indigo-900/50 transition flex items-center gap-1 mx-auto disabled:opacity-50"
                            title="1-Click mở Chrome VIA vào Fanpage này"
                          >
                            <span>{isLaunching ? "" : ""}</span>
                            <span>Mở Page</span>
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          {/* =========================================================================
              STICKY SUMMARY FOOTER (TOTAL ACCOUNTS + SUM METRICS)
              ========================================================================= */}
          {data?.summary && (
            <footer className="bg-[#111827] border-t border-[#1F2937] px-6 py-2.5 flex flex-wrap items-center justify-between text-xs font-mono select-none sticky bottom-0 z-20 shadow-xl">
              {/* Left: Summary Label & Brand */}
              <div className="flex items-center gap-3">
                <span className="font-bold text-white font-sans text-sm tracking-wide">
                  {data.summary.label}
                </span>
                <span className="text-[10px] text-gray-400 font-sans hidden sm:inline">
                  • Bản quyền ADSOS CHECK • FBP ADS Agency
                </span>
                {data.total_pages > 1 && (
                  <div className="flex items-center gap-1 text-[11px] text-gray-400 font-sans">
                    <span>Trang {page} / {data.total_pages}</span>
                    <button
                      type="button"
                      disabled={page <= 1}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      className="px-2 py-0.5 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-40"
                    >
                      ←
                    </button>
                    <button
                      type="button"
                      disabled={page >= data.total_pages}
                      onClick={() => setPage((p) => p + 1)}
                      className="px-2 py-0.5 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-40"
                    >
                      →
                    </button>
                  </div>
                )}
              </div>

              {/* Right: Summary Metrics for Financial Tabs */}
              {(activeTab === "personal" || activeTab === "bm") && (
                <div className="flex items-center gap-6 text-[11px]" suppressHydrationWarning>
                  <div className="flex items-center gap-1.5">
                    <span className="text-gray-400 font-sans">Số dư:</span>
                    <span className="font-bold text-emerald-400" suppressHydrationWarning>
                      {formatMoney(data.summary.total_balance, data.summary.primary_currency)}{" "}
                      <span className="text-[10px] text-gray-500 font-sans">
                        ({data.summary.primary_currency})
                      </span>
                    </span>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <span className="text-gray-400 font-sans">Ngưỡng:</span>
                    <span className="font-bold text-white" suppressHydrationWarning>
                      {formatMoney(data.summary.total_threshold, data.summary.primary_currency)}{" "}
                      <span className="text-[10px] text-gray-500 font-sans">
                        ({data.summary.primary_currency})
                      </span>
                    </span>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <span className="text-gray-400 font-sans">Limit:</span>
                    <span className="font-bold text-amber-300" suppressHydrationWarning>
                      {formatMoney(data.summary.total_limit, data.summary.primary_currency)}{" "}
                      <span className="text-[10px] text-gray-500 font-sans">
                        ({data.summary.primary_currency})
                      </span>
                    </span>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <span className="text-gray-400 font-sans">Tổng tiêu:</span>
                    <span className="font-bold text-indigo-300" suppressHydrationWarning>
                      {formatMoney(data.summary.total_spend, data.summary.primary_currency)}{" "}
                      <span className="text-[10px] text-gray-500 font-sans">
                        ({data.summary.primary_currency})
                      </span>
                    </span>
                  </div>
                </div>
              )}
            </footer>
          )}
        </div>
      </div>

      <div className={`fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-xl border border-[#3A3A42] bg-[#1A1A1E]/95 px-3 py-2 shadow-[0_16px_50px_rgba(0,0,0,0.55)] backdrop-blur transition duration-200 ${selectedAccountIds.length ? "translate-y-0 opacity-100" : "pointer-events-none translate-y-8 opacity-0"}`}>
        <span className="whitespace-nowrap px-2 text-xs font-semibold text-white">Đã chọn {selectedAccountIds.length} tài sản</span>
        <button type="button" onClick={() => setShowRenameModal(true)} className="rounded-lg border border-[#3A3A42] px-3 py-1.5 text-xs text-[#D1D5DB] hover:text-white">Đổi tên</button>
        <button type="button" onClick={() => setShowSharePixelModal(true)} className="rounded-lg border border-[#3A3A42] px-3 py-1.5 text-xs text-[#D1D5DB] hover:text-white">Chia sẻ Pixel</button>
        <button
          type="button"
          onClick={() => setShowSuperShareModal(true)}
          className="rounded-lg border border-indigo-500/60 bg-indigo-600/25 hover:bg-indigo-600/40 px-3 py-1.5 text-xs font-semibold text-white flex items-center gap-1.5"
        >
          <svg className="w-3.5 h-3.5 text-indigo-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" />
          </svg>
          <span>Share BM / Gán TK</span>
        </button>
        <button type="button" onClick={() => setShowSuperTargetModal(true)} className="rounded-lg border border-[#3A3A42] px-3 py-1.5 text-xs text-[#D1D5DB] hover:text-white">Kháng nghị</button>
        <button type="button" onClick={triggerPrimaryWorkflow} className="rounded-lg bg-[#2563EB] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#1D4ED8]">Chạy kịch bản <kbd className="ml-1 opacity-70">Ctrl+Enter</kbd></button>
        <button type="button" onClick={() => setSelectedAccountIds([])} className="rounded-lg px-2 py-1.5 text-xs text-[#9CA3AF] hover:text-white">Bỏ chọn <kbd className="ml-1">Esc</kbd></button>
      </div>

      {/* 69+ OPERATIONAL WORKFLOWS MODAL (PILLAR 2) */}
      <WorkflowCatalogModal
        isOpen={showWorkflowModal}
        onClose={() => setShowWorkflowModal(false)}
        selectedAccountIds={selectedAccountIds}
        onWorkflowComplete={(msg) => setFeedback({ text: msg, error: false })}
      />

      {/* =========================================================================
          MODAL: XÓA QUẢN TRỊ VIÊN ẨN (HIDDEN ADMINS)
          ========================================================================= */}
      {showRemoveAdminModal && (
        <div className="fixed inset-0 bg-black/75 z-50 flex items-center justify-center p-4">
          <div className="bg-[#111827] border border-[#1F2937] rounded-2xl w-full max-w-md p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-[#1F2937] pb-3">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <span></span>
                <span>Xóa Quản Trị Viên Ẩn (Clean Hidden Admins)</span>
              </h3>
              <button
                type="button"
                onClick={() => setShowRemoveAdminModal(false)}
                className="text-gray-400 hover:text-white"
              >
                
              </button>
            </div>

            <p className="text-xs text-gray-300 leading-relaxed">
              Hệ thống sẽ quét sâu qua Graph API &amp; Facebook Business Settings để kiểm tra, gỡ bỏ tất cả tài khoản phụ / hacker / quản trị viên ẩn trái phép trên{" "}
              <strong className="text-white font-mono">{selectedAccountIds.length}</strong> tài khoản đã chọn.
            </p>

            <div className="bg-[#0B0F19] p-3 rounded-xl border border-[#1F2937] max-h-36 overflow-y-auto font-mono text-[11px] text-gray-300">
              {selectedAccountIds.map((id) => (
                <div key={id} className="py-0.5">• ID: {id}</div>
              ))}
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowRemoveAdminModal(false)}
                className="px-4 py-2 rounded-xl text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 transition"
              >
                Hủy
              </button>
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => void handleExecuteRemoveHiddenAdmins()}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-rose-600 hover:bg-rose-500 text-white transition flex items-center gap-1.5 disabled:opacity-50"
              >
                <span>{actionLoading ? "" : ""}</span>
                <span>{actionLoading ? "Đang quét & xóa..." : "Xác nhận xóa QTV Ẩn"}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          MODAL: ĐỔI INFO TKQC (TIỀN TỆ, MÚI GIỜ, THUẾ, TÊN MẪU)
          ========================================================================= */}
      {showRenameModal && (
        <div className="fixed inset-0 bg-black/75 z-50 flex items-center justify-center p-4">
          <form
            onSubmit={handleExecuteRename}
            className="bg-[#111827] border border-[#1F2937] rounded-2xl w-full max-w-lg p-6 space-y-4 shadow-2xl"
          >
            <div className="flex items-center justify-between border-b border-[#1F2937] pb-3">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <span></span>
                <span>Đổi Thông Tin TKQC Hàng Loạt</span>
              </h3>
              <button
                type="button"
                onClick={() => setShowRenameModal(false)}
                className="text-gray-400 hover:text-white"
              >
                
              </button>
            </div>

            <p className="text-xs text-gray-400">
              Áp dụng đổi tên mẫu, tiền tệ, múi giờ và thuế cho{" "}
              <strong className="text-white">{selectedAccountIds.length}</strong> tài khoản đã chọn.
            </p>

            <div className="space-y-3">
              <div>
                <label className="block text-[11px] text-gray-400 mb-1">
                  Tên mới cơ sở (Hỗ trợ chèn <code className="text-indigo-400">{"{index}"}</code> để đánh số tự động):
                </label>
                <input
                  type="text"
                  value={renameBaseName}
                  onChange={(e) => setRenameBaseName(e.target.value)}
                  placeholder="VD: FBP Agency Camp {index}"
                  className="w-full bg-[#0B0F19] border border-[#1F2937] rounded-xl px-3 py-2 text-xs text-white focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] text-gray-400 mb-1">Tiền tố (Prefix):</label>
                  <input
                    type="text"
                    value={renamePrefix}
                    onChange={(e) => setRenamePrefix(e.target.value)}
                    placeholder="VD: [VIP]"
                    className="w-full bg-[#0B0F19] border border-[#1F2937] rounded-xl px-3 py-2 text-xs text-white focus:border-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-[11px] text-gray-400 mb-1">Hậu tố (Suffix):</label>
                  <input
                    type="text"
                    value={renameSuffix}
                    onChange={(e) => setRenameSuffix(e.target.value)}
                    placeholder="VD: - 2024"
                    className="w-full bg-[#0B0F19] border border-[#1F2937] rounded-xl px-3 py-2 text-xs text-white focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-[11px] text-gray-400 mb-1">Tiền Tệ:</label>
                  <select
                    value={renameCurrency}
                    onChange={(e) => setRenameCurrency(e.target.value)}
                    className="w-full bg-[#0B0F19] border border-[#1F2937] rounded-xl px-2 py-2 text-xs text-white focus:border-indigo-500 focus:outline-none"
                  >
                    <option value="">Giữ nguyên</option>
                    <option value="VND">VND</option>
                    <option value="USD">USD</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[11px] text-gray-400 mb-1">Quốc Gia:</label>
                  <input
                    type="text"
                    value={renameCountry}
                    onChange={(e) => setRenameCountry(e.target.value)}
                    placeholder="VN / US"
                    className="w-full bg-[#0B0F19] border border-[#1F2937] rounded-xl px-2 py-2 text-xs text-white uppercase focus:border-indigo-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-[11px] text-gray-400 mb-1">Trạng thái Thuế:</label>
                  <select
                    value={renameTaxStatus}
                    onChange={(e) => setRenameTaxStatus(e.target.value)}
                    className="w-full bg-[#0B0F19] border border-[#1F2937] rounded-xl px-2 py-2 text-xs text-white focus:border-indigo-500 focus:outline-none"
                  >
                    <option value="">Giữ nguyên</option>
                    <option value="MIỄN THUẾ">MIỄN THUẾ</option>
                    <option value="ĐÃ KHAI THUẾ">ĐÃ KHAI THUẾ</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-[11px] text-gray-400 mb-1">Múi Giờ:</label>
                <input
                  type="text"
                  value={renameTimezone}
                  onChange={(e) => setRenameTimezone(e.target.value)}
                  placeholder="Asia/Ho_Chi_Minh | GMT+7"
                  className="w-full bg-[#0B0F19] border border-[#1F2937] rounded-xl px-3 py-2 text-xs text-white focus:border-indigo-500 focus:outline-none"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-3">
              <button
                type="button"
                onClick={() => setShowRenameModal(false)}
                className="px-4 py-2 rounded-xl text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 transition"
              >
                Hủy
              </button>
              <button
                type="submit"
                disabled={actionLoading}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition flex items-center gap-1.5 disabled:opacity-50"
              >
                <span>{actionLoading ? "" : ""}</span>
                <span>{actionLoading ? "Đang cập nhật..." : "Cập nhật tài khoản"}</span>
              </button>
            </div>
          </form>
        </div>
      )}

      {/* =========================================================================
          MODAL: SHARE PIXEL
          ========================================================================= */}
      {showSharePixelModal && (
        <div className="fixed inset-0 bg-black/75 z-50 flex items-center justify-center p-4">
          <form
            onSubmit={handleExecuteSharePixel}
            className="bg-[#111827] border border-[#1F2937] rounded-2xl w-full max-w-md p-6 space-y-4 shadow-2xl"
          >
            <div className="flex items-center justify-between border-b border-[#1F2937] pb-3">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <span></span>
                <span>Share Pixel Tới Các Tài Khoản QC</span>
              </h3>
              <button
                type="button"
                onClick={() => setShowSharePixelModal(false)}
                className="text-gray-400 hover:text-white"
              >
                
              </button>
            </div>

            <p className="text-xs text-gray-400">
              Chia sẻ Pixel tự động từ Business Manager tới{" "}
              <strong className="text-white">{selectedAccountIds.length}</strong> tài khoản đã chọn.
            </p>

            <div className="space-y-3">
              <div>
                <label className="block text-[11px] text-gray-400 mb-1">Pixel ID (Bắt buộc):</label>
                <input
                  type="text"
                  required
                  value={pixelIdInput}
                  onChange={(e) => setPixelIdInput(e.target.value)}
                  placeholder="VD: 104598284729102"
                  className="w-full bg-[#0B0F19] border border-[#1F2937] rounded-xl px-3 py-2 text-xs text-white font-mono focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-[11px] text-gray-400 mb-1">
                  Business Manager sở hữu Pixel (Tùy chọn):
                </label>
                <select
                  value={pixelBmId}
                  onChange={(e) => setPixelBmId(e.target.value)}
                  className="w-full bg-[#0B0F19] border border-[#1F2937] rounded-xl px-3 py-2 text-xs text-white focus:border-indigo-500 focus:outline-none"
                >
                  <option value="">Tự động chọn BM Chính Cho Thuê</option>
                  {(syncedBmsList || []).map((bm) => (
                    <option key={bm.bm_id} value={bm.bm_id}>
                      {bm.is_primary_rental ? " " : ""}
                      {bm.name} ({bm.bm_id})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-3">
              <button
                type="button"
                onClick={() => setShowSharePixelModal(false)}
                className="px-4 py-2 rounded-xl text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 transition"
              >
                Hủy
              </button>
              <button
                type="submit"
                disabled={actionLoading}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition flex items-center gap-1.5 disabled:opacity-50"
              >
                <span>{actionLoading ? "" : ""}</span>
                <span>{actionLoading ? "Đang chia sẻ..." : "Chia sẻ Pixel"}</span>
              </button>
            </div>
          </form>
        </div>
      )}

      {/* =========================================================================
          MODAL: SUPER SHARE ADS (AUTO REMEMBER BM ROUTING)
          ========================================================================= */}
      <ShareBmAccountsModal
        open={showSuperShareModal}
        onClose={() => setShowSuperShareModal(false)}
        accounts={accountRows}
        customers={customersList}
        bms={syncedBmsList}
        initialAccountIds={selectedAccountIds}
      />
      {false && (
        <div className="fixed inset-0 bg-black/75 z-50 flex items-center justify-center p-4">
          <form
            onSubmit={handleExecuteSuperShareAds}
            className="bg-[#111827] border border-[#1F2937] rounded-2xl w-full max-w-lg p-6 space-y-4 shadow-2xl"
          >
            <div className="flex items-center justify-between border-b border-[#1F2937] pb-3">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <span></span>
                <span>Super Share Ads &amp; Ghi Nhớ Cấu Hình BM</span>
              </h3>
              <button
                type="button"
                onClick={() => setShowSuperShareModal(false)}
                className="text-gray-400 hover:text-white"
              >
                
              </button>
            </div>

            <p className="text-xs text-gray-300 leading-relaxed">
              Cấp quyền{" "}
              <strong className="text-white font-mono">{selectedAccountIds.length}</strong> tài khoản quảng cáo cho khách hàng, đồng thời tự động lưu cấu hình BM &amp; VIA vào hệ thống bộ nhớ định tuyến (Auto-Remember).
            </p>

            <div className="space-y-3">
              <div>
                <label className="block text-[11px] text-gray-400 mb-1">Khách Hàng Nhận Quyền (Bắt buộc):</label>
                <select
                  required
                  value={shareClientId}
                  onChange={(e) => {
                    const cid = e.target.value ? Number(e.target.value) : "";
                    setShareClientId(cid);
                    if (cid !== "") {
                      const pref = clientPreferences.find((p) => p.client_id === cid);
                      if (pref) {
                        if (pref.preferred_bm_id) setShareBmId(pref.preferred_bm_id);
                        if (pref.bm_role === "ADMIN" || pref.bm_role === "EMPLOYEE") setShareRole(pref.bm_role);
                        if (pref.ad_account_access_type === "FULL" || pref.ad_account_access_type === "PARTIAL") {
                          setShareAccessType(pref.ad_account_access_type);
                        }
                        if (pref.partial_permissions && pref.partial_permissions.length > 0) {
                          setSharePermissions(pref.partial_permissions);
                        }
                      }
                    }
                  }}
                  className="w-full bg-[#0B0F19] border border-[#1F2937] rounded-xl px-3 py-2 text-xs text-white focus:border-indigo-500 focus:outline-none"
                >
                  <option value="">-- Chọn khách hàng --</option>
                  {(clientPreferences || []).map((p) => (
                    <option key={p.client_id} value={p.client_id}>
                      #{p.client_id} — {p.customer_name} {p.preferred_bm_id ? `(${p.bm_name || p.preferred_bm_id})` : ""}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[11px] text-gray-400 mb-1">
                  Business Manager Phân Quyền (Ưu tiên  BM Chính Cho Thuê):
                </label>
                <select
                  value={shareBmId}
                  onChange={(e) => setShareBmId(e.target.value)}
                  className="w-full bg-[#0B0F19] border border-[#1F2937] rounded-xl px-3 py-2 text-xs text-white focus:border-indigo-500 focus:outline-none"
                >
                  <option value="">Tự động ưu tiên BM Chính Cho Thuê</option>
                  {(syncedBmsList || []).map((bm) => (
                    <option key={bm.bm_id} value={bm.bm_id}>
                      {bm.is_primary_rental ? " " : ""}
                      {bm.name} ({bm.bm_id})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] text-gray-400 mb-1">Vai trò BM:</label>
                  <select
                    value={shareRole}
                    onChange={(e) => setShareRole(e.target.value as "EMPLOYEE" | "ADMIN")}
                    className="w-full bg-[#0B0F19] border border-[#1F2937] rounded-xl px-3 py-2 text-xs text-white focus:border-indigo-500 focus:outline-none"
                  >
                    <option value="EMPLOYEE">Nhân viên (EMPLOYEE)</option>
                    <option value="ADMIN">Quản trị viên (ADMIN)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[11px] text-gray-400 mb-1">Loại quyền TKQC:</label>
                  <select
                    value={shareAccessType}
                    onChange={(e) => setShareAccessType(e.target.value as "FULL" | "PARTIAL")}
                    className="w-full bg-[#0B0F19] border border-[#1F2937] rounded-xl px-3 py-2 text-xs text-white focus:border-indigo-500 focus:outline-none"
                  >
                    <option value="FULL">Toàn quyền (FULL ACCESS)</option>
                    <option value="PARTIAL">Phân quyền chi tiết (PARTIAL)</option>
                  </select>
                </div>
              </div>

              {shareAccessType === "PARTIAL" && (
                <div className="bg-[#0B0F19] p-3 rounded-xl border border-[#1F2937] space-y-2 text-xs">
                  <div className="text-[11px] text-gray-400 font-semibold">Quyền hạn chi tiết:</div>
                  {[
                    { key: "MANAGE_CAMPAIGNS", label: "Quản lý chiến dịch quảng cáo" },
                    { key: "VIEW_PERFORMANCE", label: "Xem hiệu quả & báo cáo chi tiêu" },
                    { key: "CREATIVE_HUB", label: "Truy cập Creative Hub & mẫu QC" },
                  ].map((p) => (
                    <label key={p.key} className="flex items-center gap-2 cursor-pointer text-gray-300">
                      <input
                        type="checkbox"
                        checked={sharePermissions.includes(p.key)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSharePermissions([...sharePermissions, p.key]);
                          } else {
                            setSharePermissions(sharePermissions.filter((x) => x !== p.key));
                          }
                        }}
                        className="rounded border-gray-700 bg-gray-900 text-purple-600 focus:ring-0"
                      />
                      <span>{p.label}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>

            <div className="flex justify-end gap-3 pt-3">
              <button
                type="button"
                onClick={() => setShowSuperShareModal(false)}
                className="px-4 py-2 rounded-xl text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 transition"
              >
                Hủy
              </button>
              <button
                type="submit"
                disabled={actionLoading}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-purple-600 hover:bg-purple-500 text-white transition flex items-center gap-1.5 shadow-lg shadow-purple-900/30 disabled:opacity-50"
              >
                <span>{actionLoading ? "" : ""}</span>
                <span>{actionLoading ? "Đang cấp quyền & ghi nhớ..." : "Super Share & Lưu Cấu Hình"}</span>
              </button>
            </div>
          </form>
        </div>
      )}

      {/* =========================================================================
          MODAL: EXTENDED PAYMENT & CARD ACTIONS
          ========================================================================= */}
      {showExtendedPaymentModal && (
        <div className="fixed inset-0 bg-black/75 z-50 flex items-center justify-center p-4">
          <div className="bg-[#111827] border border-[#1F2937] rounded-2xl w-full max-w-lg p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-[#1F2937] pb-3">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <span></span>
                <span>Extended Payment — Thao Tác Thanh Toán &amp; Thẻ</span>
              </h3>
              <button
                type="button"
                onClick={() => {
                  setShowExtendedPaymentModal(false);
                  setInvoiceResults([]);
                }}
                className="text-gray-400 hover:text-white"
              >
                
              </button>
            </div>

            <p className="text-xs text-gray-300 leading-relaxed">
              Thực hiện thanh toán nợ ngay, gán thẻ chính/phụ hoặc gỡ bỏ thẻ cho{" "}
              <strong className="text-white font-mono">{selectedAccountIds.length}</strong> tài khoản đã chọn.
            </p>

            <div className="grid grid-cols-2 gap-2 text-xs">
              {[
                { key: "PAY_NOW", label: "Thanh Toán Nợ Ngay", icon: "" },
                { key: "SET_PRIMARY_CARD", label: "Gán Thẻ Chính", icon: "" },
                { key: "ADD_BACKUP_CARD", label: "Thêm Thẻ Phụ", icon: "" },
                { key: "REMOVE_CARD", label: "Gỡ Bỏ Thẻ", icon: "" },
                { key: "FETCH_INVOICES", label: "Tải Hóa Đơn (Invoices)", icon: "" },
              ].map((act) => (
                <button
                  key={act.key}
                  type="button"
                  onClick={() => setPaymentActionType(act.key)}
                  className={`p-2.5 rounded-xl border text-left font-semibold flex items-center gap-2 transition ${
                    paymentActionType === act.key
                      ? "bg-indigo-600/30 border-indigo-500 text-white shadow-sm"
                      : "bg-[#0B0F19] border-[#1F2937] text-gray-400 hover:text-white hover:border-gray-600"
                  }`}
                >
                  <span>{act.icon}</span>
                  <span>{act.label}</span>
                </button>
              ))}
            </div>

            {/* Inputs based on action */}
            {paymentActionType === "PAY_NOW" && (
              <div className="bg-[#0B0F19] p-3 rounded-xl border border-[#1F2937] space-y-2">
                <label className="block text-[11px] text-gray-400">Số tiền thanh toán nợ (Để trống để trả toàn bộ dư nợ):</label>
                <input
                  type="number"
                  value={paymentAmount}
                  onChange={(e) => setPaymentAmount(e.target.value)}
                  placeholder="VD: 5500000"
                  className="w-full bg-[#111827] border border-[#1F2937] rounded-xl px-3 py-2 text-xs text-emerald-400 font-mono focus:border-indigo-500 focus:outline-none"
                />
              </div>
            )}

            {(paymentActionType === "SET_PRIMARY_CARD" || paymentActionType === "ADD_BACKUP_CARD") && (
              <div className="bg-[#0B0F19] p-3 rounded-xl border border-[#1F2937] grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] text-gray-400 mb-1">Loại Thẻ:</label>
                  <select
                    value={paymentCardBrand}
                    onChange={(e) => setPaymentCardBrand(e.target.value)}
                    className="w-full bg-[#111827] border border-[#1F2937] rounded-xl px-3 py-2 text-xs text-white focus:border-indigo-500 focus:outline-none"
                  >
                    <option value="VISA">VISA</option>
                    <option value="MASTERCARD">MASTERCARD</option>
                    <option value="JCB">JCB</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] text-gray-400 mb-1">4 Số Cuối Thẻ:</label>
                  <input
                    type="text"
                    maxLength={4}
                    value={paymentCardLast4}
                    onChange={(e) => setPaymentCardLast4(e.target.value)}
                    placeholder="8899"
                    className="w-full bg-[#111827] border border-[#1F2937] rounded-xl px-3 py-2 text-xs text-white font-mono focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              </div>
            )}

            {invoiceResults.length > 0 && (
              <div className="bg-[#0B0F19] p-3 rounded-xl border border-[#1F2937] space-y-2 max-h-40 overflow-y-auto font-mono text-[11px]">
                <div className="text-gray-400 font-bold font-sans">Lịch sử hóa đơn đã tải:</div>
                {invoiceResults.map((inv, i) => (
                  <div key={i} className="flex justify-between border-b border-gray-800 py-1 text-gray-300">
                    <span>{inv.invoice_id} ({inv.act_id})</span>
                    <span className="text-emerald-400">{formatMoney(inv.amount, inv.currency)} {inv.currency}</span>
                  </div>
                ))}
              </div>
            )}

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => {
                  setShowExtendedPaymentModal(false);
                  setInvoiceResults([]);
                }}
                className="px-4 py-2 rounded-xl text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 transition"
              >
                Đóng
              </button>
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => void handleExecuteExtendedPayment(paymentActionType)}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition flex items-center gap-1.5 disabled:opacity-50"
              >
                <span>{actionLoading ? "" : ""}</span>
                <span>{actionLoading ? "Đang xử lý..." : "Xác nhận thực thi"}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          MODAL: SUPER TARGET & KHÁNG NGHỊ TÀI KHOẢN DIE
          ========================================================================= */}
      {showSuperTargetModal && (
        <div className="fixed inset-0 bg-black/75 z-50 flex items-center justify-center p-4">
          <div className="bg-[#111827] border border-[#1F2937] rounded-2xl w-full max-w-lg p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-[#1F2937] pb-3">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <span></span>
                <span>Super Target &amp; Kháng Nghị Tài Khoản DIE</span>
              </h3>
              <button
                type="button"
                onClick={() => setShowSuperTargetModal(false)}
                className="text-gray-400 hover:text-white"
              >
                
              </button>
            </div>

            <div className="flex items-center gap-2 border-b border-[#1F2937] pb-2 text-xs">
              <button
                type="button"
                onClick={() => setTargetTab("interests")}
                className={`px-3 py-1.5 rounded-lg font-semibold transition ${
                  targetTab === "interests" ? "bg-amber-500/20 text-amber-300 border border-amber-500/30" : "text-gray-400 hover:text-white"
                }`}
              >
                 Quét Sở Thích Ẩn Meta
              </button>
              <button
                type="button"
                onClick={() => setTargetTab("appeal")}
                className={`px-3 py-1.5 rounded-lg font-semibold transition ${
                  targetTab === "appeal" ? "bg-rose-500/20 text-rose-300 border border-rose-500/30" : "text-gray-400 hover:text-white"
                }`}
              >
                 Gửi Đơn Kháng Nghị DIE
              </button>
            </div>

            {targetTab === "interests" ? (
              <div className="space-y-3">
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={targetKeyword}
                    onChange={(e) => setTargetKeyword(e.target.value)}
                    placeholder="Nhập từ khóa ngành hàng (VD: bất động sản, sneaker, mỹ phẩm)..."
                    className="flex-1 bg-[#0B0F19] border border-[#1F2937] rounded-xl px-3 py-2 text-xs text-white focus:border-amber-500 focus:outline-none"
                  />
                  <button
                    type="button"
                    disabled={actionLoading}
                    onClick={() => void handleExecuteSuperTarget("SEARCH_INTERESTS")}
                    className="px-4 py-2 rounded-xl text-xs font-semibold bg-amber-600 hover:bg-amber-500 text-white transition flex items-center gap-1 disabled:opacity-50"
                  >
                    <span>{actionLoading ? "" : ""}</span>
                    <span>Tìm</span>
                  </button>
                </div>

                {targetResults.length > 0 && (
                  <div className="bg-[#0B0F19] p-3 rounded-xl border border-[#1F2937] space-y-2 max-h-56 overflow-y-auto text-xs">
                    {targetResults.map((item, idx) => (
                      <div key={idx} className="p-2 rounded-lg bg-[#111827] border border-gray-800 flex justify-between items-start">
                        <div>
                          <div className="font-semibold text-white">{item.name}</div>
                          <div className="text-[10px] text-gray-400">{item.path?.join(" > ")} • Chủ đề: {item.topic}</div>
                        </div>
                        <div className="text-right text-[10px] font-mono text-emerald-400">
                          {formatInt(item.audience_size_lower_bound)} - {formatInt(item.audience_size_upper_bound)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-xs text-gray-300">
                  Gửi kháng nghị tự động tới Meta Trust &amp; Safety cho{" "}
                  <strong className="text-white font-mono">{selectedAccountIds.length}</strong> tài khoản đã tick chọn.
                </p>
                <div>
                  <label className="block text-[11px] text-gray-400 mb-1">Lý do kháng nghị:</label>
                  <textarea
                    rows={3}
                    value={appealReason}
                    onChange={(e) => setAppealReason(e.target.value)}
                    className="w-full bg-[#0B0F19] border border-[#1F2937] rounded-xl p-3 text-xs text-white focus:border-rose-500 focus:outline-none"
                  />
                </div>
                <div className="flex justify-end gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowSuperTargetModal(false)}
                    className="px-4 py-2 rounded-xl text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 transition"
                  >
                    Hủy
                  </button>
                  <button
                    type="button"
                    disabled={actionLoading}
                    onClick={() => void handleExecuteSuperTarget("APPEAL_ACCOUNT")}
                    className="px-4 py-2 rounded-xl text-xs font-semibold bg-rose-600 hover:bg-rose-500 text-white transition flex items-center gap-1.5 disabled:opacity-50"
                  >
                    <span>{actionLoading ? "" : ""}</span>
                    <span>Gửi Kháng Nghị</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
      {/* MODAL 1: TẢI THEO DANH SÁCH ID (LOAD BY ACCOUNT ID) */}
      {showLoadByIdModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-[#111827] border border-slate-800 rounded-2xl w-full max-w-lg p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <span></span> Tải Tài Khoản Theo Danh Sách ID (act_id)
              </h3>
              <button
                type="button"
                onClick={() => setShowLoadByIdModal(false)}
                className="text-slate-400 hover:text-white"
              >
                
              </button>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5 font-medium">
                Dán danh sách ID (mỗi ID 1 dòng hoặc cách nhau bằng dấu phẩy):
              </label>
              <textarea
                rows={5}
                value={loadByIdInput}
                onChange={(e) => setLoadByIdInput(e.target.value)}
                placeholder="VD: 123456789, act_987654321, 555666777"
                className="w-full bg-[#1E293B] border border-slate-700 text-slate-100 placeholder-slate-500 rounded-xl p-3 text-xs font-mono focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <div className="flex items-center justify-end gap-2.5 pt-2">
              <button
                type="button"
                onClick={() => setShowLoadByIdModal(false)}
                className="px-4 py-2 rounded-xl text-xs font-medium text-slate-300 hover:bg-slate-800 transition"
              >
                Hủy
              </button>
              <button
                type="button"
                disabled={!loadByIdInput.trim()}
                onClick={() => {
                  setAccountIdsFilter(loadByIdInput.trim());
                  setSmitMode("LOAD_BY_ACT_IDS");
                  setPage(1);
                  setShowLoadByIdModal(false);
                  setFeedback({ text: ` Đang lọc theo danh sách ID đã nhập...`, error: false });
                }}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-sky-600 hover:bg-sky-500 text-white shadow-lg shadow-sky-600/30 transition disabled:opacity-50"
              >
                 Tải Ngay
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 2: TẢI THEO ID BM (LOAD BY BM ID) */}
      {showLoadByBmModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-[#111827] border border-slate-800 rounded-2xl w-full max-w-lg p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <span></span> Tải Tài Khoản Theo Business Manager (BM)
              </h3>
              <button
                type="button"
                onClick={() => setShowLoadByBmModal(false)}
                className="text-slate-400 hover:text-white"
              >
                
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1 font-medium">Chọn BM đã quét:</label>
                <select
                  value={loadByBmInput}
                  onChange={(e) => setLoadByBmInput(e.target.value)}
                  className="w-full bg-[#1E293B] border border-slate-700 text-slate-100 rounded-xl px-3 py-2 text-xs focus:border-indigo-500 focus:outline-none"
                >
                  <option value="">— Chọn Business Manager —</option>
                  {(syncedBmsList || []).map((b) => (
                    <option key={b.id} value={b.bm_id}>
                      {b.name} ({b.bm_id}) · {b.ad_account_count} TKQC
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1 font-medium">Hoặc nhập trực tiếp BM ID:</label>
                <input
                  type="text"
                  value={loadByBmInput}
                  onChange={(e) => setLoadByBmInput(e.target.value)}
                  placeholder="VD: 123456789012345"
                  className="w-full bg-[#1E293B] border border-slate-700 text-slate-100 placeholder-slate-500 rounded-xl px-3 py-2 text-xs font-mono focus:border-indigo-500 focus:outline-none"
                />
              </div>
            </div>
            <div className="flex items-center justify-end gap-2.5 pt-2">
              <button
                type="button"
                onClick={() => setShowLoadByBmModal(false)}
                className="px-4 py-2 rounded-xl text-xs font-medium text-slate-300 hover:bg-slate-800 transition"
              >
                Hủy
              </button>
              <button
                type="button"
                disabled={!loadByBmInput.trim()}
                onClick={() => {
                  setBmFilterId(loadByBmInput.trim());
                  setSmitMode("LOAD_BY_BM_ID");
                  setPage(1);
                  setShowLoadByBmModal(false);
                  setFeedback({ text: ` Đang tải tài khoản thuộc BM [${loadByBmInput.trim()}]...`, error: false });
                }}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-purple-600 hover:bg-purple-500 text-white shadow-lg shadow-purple-600/30 transition disabled:opacity-50"
              >
                 Tải Ngay
              </button>
            </div>
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
        vias={viasList}
        defaultViaId={selectedViaId}
      />

      {/* Customer Spend & 4% Rental Fee Modal */}
      <CustomerSpendReportModal
        isOpen={showCustomerSpendModal}
        onClose={() => setShowCustomerSpendModal(false)}
      />

      {/* Raw VIA Import & Auto Asset Sweep Modal */}
      <RawViaImportModal
        open={showRawViaModal}
        onClose={() => setShowRawViaModal(false)}
        onSuccess={() => void fetchData()}
      />
    </div>
  );
}

export default function AdsCheckPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-[#0B0F19] flex items-center justify-center text-gray-400 text-sm">
          Đang tải bảng ADSOS CHECK...
        </div>
      }
    >
      <AdsCheckContent />
    </Suspense>
  );
}
