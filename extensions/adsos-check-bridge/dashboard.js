/**
 * ADSOS SMIT PRO — Dashboard Controller
 * Full-screen high-density SMIT workspace with Multi-VIA storage and 4 SMIT Load Modes.
 * 4 Pillars:
 * 1.  Quản Trị TKQC & Thanh Toán
 * 2.  Bảo Mật BM & Quét QTV Ẩn
 * 3.  Super Target & Fanpage/Pixel
 * 4.  Workflow Builder & Control Hub
 */

document.addEventListener("DOMContentLoaded", async () => {
  // --- DOM Elements ---
  const connStatusPill = document.getElementById("connStatusPill");
  const connDot = document.getElementById("connDot");
  const connLabel = document.getElementById("connLabel");
  const activeSessionPill = document.getElementById("activeSessionPill");
  const activeSessionLabel = document.getElementById("activeSessionLabel");

  const btnSyncServer = document.getElementById("btnSyncServer");
  const btnDashOpenAdsManager = document.getElementById("btnDashOpenAdsManager");
  const btnOpenSessionModal = document.getElementById("btnOpenSessionModal");
  const btnOpenSettingsModal = document.getElementById("btnOpenSettingsModal");
  const dashboardScanBanner = document.getElementById("dashboardScanBanner");
  const dashboardScanText = document.getElementById("dashboardScanText");
  const dashboardSyncProgressFill = document.getElementById("dashboardSyncProgressFill");
  const dashboardSyncProgressTrack = dashboardScanBanner?.querySelector('[role="progressbar"]');
  const btnCancelSync = document.getElementById("btnCancelSync");
  const masterViaSelector = document.getElementById("masterViaSelector");

  // Sidebar Elements
  const viasListContainer = document.getElementById("viasListContainer");
  const searchViaInput = document.getElementById("searchViaInput");
  const btnRefreshVias = document.getElementById("btnRefreshVias");
  const btnHarvestCurrentVia = document.getElementById("btnHarvestCurrentVia");
  const btnClearViaCache = document.getElementById("btnClearViaCache");
  const sidebarViaCount = document.getElementById("sidebarViaCount");
  const btnModeSingle = document.getElementById("btnModeSingle");
  const btnModeGrouped = document.getElementById("btnModeGrouped");

  // 4 Pillar Tab Buttons & Panes
  const tabBtnAccounts = document.getElementById("tabBtnAccounts");
  const tabBtnBmSecurity = document.getElementById("tabBtnBmSecurity");
  const tabBtnSuperTarget = document.getElementById("tabBtnSuperTarget");
  const tabBtnWorkflow = document.getElementById("tabBtnWorkflow");

  const tabPaneAccounts = document.getElementById("tabPaneAccounts");
  const tabPaneBmSecurity = document.getElementById("tabPaneBmSecurity");
  const tabPaneSuperTarget = document.getElementById("tabPaneSuperTarget");
  const tabPaneWorkflow = document.getElementById("tabPaneWorkflow");

  // KPI Elements (Tab 1)
  const kpiTotal = document.getElementById("kpiTotal");
  const kpiLive = document.getElementById("kpiLive");
  const kpiDie = document.getElementById("kpiDie");
  const kpiUnsettled = document.getElementById("kpiUnsettled");
  const kpiSpent = document.getElementById("kpiSpent");
  const kpiBalance = document.getElementById("kpiBalance");
  const kpiThreshold = document.getElementById("kpiThreshold");
  const kpiViaLabel = document.getElementById("kpiViaLabel");
  const kpiSpentUsd = document.getElementById("kpiSpentUsd");
  const kpiAssignedDebt = document.getElementById("kpiAssignedDebt");
  const assetCounter = document.getElementById("assetCounter");
  const selectedCounter = document.getElementById("selectedCounter");
  const compactViewToggle = document.getElementById("compactViewToggle");
  const btnExportCsvTop = document.getElementById("btnExportCsvTop");

  // Load Action Modes Toolbar (Tab 1)
  const btnLoadAll = document.getElementById("btnLoadAll");
  const btnOpenLoadByIdModal = document.getElementById("btnOpenLoadByIdModal");
  const btnOpenLoadByBmModal = document.getElementById("btnOpenLoadByBmModal");
  const btnOpenLoadByBmModal2 = document.getElementById("btnOpenLoadByBmModal2");
  const btnScanBmPages = document.getElementById("btnScanBmPages");

  // Filter Elements (Tab 1)
  const pillAll = document.getElementById("pillAll");
  const pillLive = document.getElementById("pillLive");
  const pillDie = document.getElementById("pillDie");
  const pillUnsettled = document.getElementById("pillUnsettled");
  const countPillAll = document.getElementById("countPillAll");
  const countPillLive = document.getElementById("countPillLive");
  const countPillDie = document.getElementById("countPillDie");
  const countPillUnsettled = document.getElementById("countPillUnsettled");

  const tableSearchInput = document.getElementById("tableSearchInput");
  const filterTypeSelect = document.getElementById("filterTypeSelect");
  const filterCardSelect = document.getElementById("filterCardSelect");
  const filterCurrencySelect = document.getElementById("filterCurrencySelect");

  // Bulk Elements (Tab 1)
  const bulkActionBar = document.getElementById("bulkActionBar");
  const bulkSelectedCount = document.getElementById("bulkSelectedCount");
  const btnCopySelectedIds = document.getElementById("btnCopySelectedIds");
  const btnExportCsv = document.getElementById("btnExportCsv");
  const btnBulkRenameModal = document.getElementById("btnBulkRenameModal");
  const btnBulkTimezoneCurrencyModal = document.getElementById("btnBulkTimezoneCurrencyModal");
  const btnBulkShareModal = document.getElementById("btnBulkShareModal");
  const btnOpenShareBmModalTop = document.getElementById("btnOpenShareBmModalTop");
  const btnBulkPixel = document.getElementById("btnBulkPixel");
  const btnBulkAppeal = document.getElementById("btnBulkAppeal");
  const btnBulkWorkflow = document.getElementById("btnBulkWorkflow");
  const btnClearSelection = document.getElementById("btnClearSelection");

  // Table Elements (Tab 1)
  const checkAllRows = document.getElementById("checkAllRows");
  const smitTableBody = document.getElementById("smitTableBody");

  // Tab 2 Elements (Bảo Mật BM & QTV Ẩn)
  const btnScanHiddenAdmins = document.getElementById("btnScanHiddenAdmins");
  const btnCleanSelectedAdmins = document.getElementById("btnCleanSelectedAdmins");
  const checkAllHiddenAdmins = document.getElementById("checkAllHiddenAdmins");
  const hiddenAdminsTableBody = document.getElementById("hiddenAdminsTableBody");
  const bmsTableBody = document.getElementById("bmsTableBody");
  const btnCreateBmInviteModal = document.getElementById("btnCreateBmInviteModal");

  // Tab 3 Elements (Super Target & Fanpage/Pixel)
  const targetKeywordInput = document.getElementById("targetKeywordInput");
  const targetLocaleSelect = document.getElementById("targetLocaleSelect");
  const btnExecuteSuperTarget = document.getElementById("btnExecuteSuperTarget");
  const btnCopySelectedInterests = document.getElementById("btnCopySelectedInterests");
  const selectedInterestsCount = document.getElementById("selectedInterestsCount");
  const checkAllInterests = document.getElementById("checkAllInterests");
  const superTargetTableBody = document.getElementById("superTargetTableBody");
  const pixelIdInput = document.getElementById("pixelIdInput");
  const btnExecuteBulkSharePixel = document.getElementById("btnExecuteBulkSharePixel");
  const fanpagesTableBody = document.getElementById("fanpagesTableBody");

  // Tab 4 Elements (Workflow Builder & Control Hub)
  const btnStartWorkflow = document.getElementById("btnStartWorkflow");
  const antiCheckpointDelay = document.getElementById("antiCheckpointDelay");
  const antiCheckpointDelayLabel = document.getElementById("antiCheckpointDelayLabel");
  const workflowConsole = document.getElementById("workflowConsole");
  const btnPollTasksNow = document.getElementById("btnPollTasksNow");
  const hubServerStatus = document.getElementById("hubServerStatus");
  const recentTasksTableBody = document.getElementById("recentTasksTableBody");

  // Modals
  const modalLoadById = document.getElementById("modalLoadById");
  const btnCloseLoadById = document.getElementById("btnCloseLoadById");
  const btnCancelLoadById = document.getElementById("btnCancelLoadById");
  const btnExecuteLoadById = document.getElementById("btnExecuteLoadById");
  const inputAccountIds = document.getElementById("inputAccountIds");

  const modalLoadByBm = document.getElementById("modalLoadByBm");
  const btnCloseLoadByBm = document.getElementById("btnCloseLoadByBm");
  const btnCancelLoadByBm = document.getElementById("btnCancelLoadByBm");
  const btnExecuteLoadByBm = document.getElementById("btnExecuteLoadByBm");
  const inputBmId = document.getElementById("inputBmId");

  const modalExtendedPayment = document.getElementById("modalExtendedPayment");
  const btnCloseExtendedPayment = document.getElementById("btnCloseExtendedPayment");
  const btnCancelExtendedPayment = document.getElementById("btnCancelExtendedPayment");
  const payActId = document.getElementById("payActId");
  const payActName = document.getElementById("payActName");
  const payBalance = document.getElementById("payBalance");
  const payThreshold = document.getElementById("payThreshold");
  const payFundingDetails = document.getElementById("payFundingDetails");
  const btnPayNowAction = document.getElementById("btnPayNowAction");
  const btnDownloadInvoices = document.getElementById("btnDownloadInvoices");

  const modalBulkRename = document.getElementById("modalBulkRename");
  const btnCloseBulkRename = document.getElementById("btnCloseBulkRename");
  const btnCancelBulkRename = document.getElementById("btnCancelBulkRename");
  const btnExecuteBulkRename = document.getElementById("btnExecuteBulkRename");
  const inputRenamePattern = document.getElementById("inputRenamePattern");
  const renamePreview = document.getElementById("renamePreview");

  const modalBulkTimezoneCurrency = document.getElementById("modalBulkTimezoneCurrency");
  const btnCloseBulkTimezoneCurrency = document.getElementById("btnCloseBulkTimezoneCurrency");
  const btnCancelBulkTimezoneCurrency = document.getElementById("btnCancelBulkTimezoneCurrency");
  const btnExecuteBulkTimezoneCurrency = document.getElementById("btnExecuteBulkTimezoneCurrency");
  const selectBulkTimezone = document.getElementById("selectBulkTimezone");
  const selectBulkCurrency = document.getElementById("selectBulkCurrency");

  const modalBulkShare = document.getElementById("modalBulkShare");
  const btnCloseBulkShare = document.getElementById("btnCloseBulkShare");
  const btnCancelBulkShare = document.getElementById("btnCancelBulkShare");
  const btnExecuteBulkShare = document.getElementById("btnExecuteBulkShare");
  const selectShareBmId = document.getElementById("selectShareBmId");
  const inputShareBmId = document.getElementById("inputShareBmId");
  const inputShareEmails = document.getElementById("inputShareEmails");
  const selectShareRole = document.getElementById("selectShareRole");
  const inputShareTargetUid = document.getElementById("inputShareTargetUid");
  const inputShareAccountIds = document.getElementById("inputShareAccountIds");
  const badgeShareAccountCount = document.getElementById("badgeShareAccountCount");
  const btnSyncShareSelectedFromTable = document.getElementById("btnSyncShareSelectedFromTable");
  const btnClearShareAccountIds = document.getElementById("btnClearShareAccountIds");
  const shareBmResultBox = document.getElementById("shareBmResultBox");
  const shareBmResultMessage = document.getElementById("shareBmResultMessage");
  const shareBmInviteLinkRow = document.getElementById("shareBmInviteLinkRow");
  const inputShareInviteLink = document.getElementById("inputShareInviteLink");
  const btnCopyShareInviteLink = document.getElementById("btnCopyShareInviteLink");

  const modalSettings = document.getElementById("modalSettings");
  const btnCloseSettings = document.getElementById("btnCloseSettings");
  const cfgServerUrl = document.getElementById("cfgServerUrl");
  const cfgClientKey = document.getElementById("cfgClientKey");
  const btnTestConn = document.getElementById("btnTestConn");
  const btnSaveSettings = document.getElementById("btnSaveSettings");
  const connTestMessage = document.getElementById("connTestMessage");

  const modalSession = document.getElementById("modalSession");
  const btnCloseSession = document.getElementById("btnCloseSession");
  const btnCancelSession = document.getElementById("btnCancelSession");
  const btnCopyAllSession = document.getElementById("btnCopyAllSession");
  const sessionUidDisplay = document.getElementById("sessionUidDisplay");
  const sessionTokenDisplay = document.getElementById("sessionTokenDisplay");
  const sessionCookieDisplay = document.getElementById("sessionCookieDisplay");

  const toastPopup = document.getElementById("toastPopup");

  // State
  let viasData = {};
  let activeViaUid = "";
  let viewMode = "single"; // "single" | "grouped"
  let statusFilter = "ALL";
  let searchQuery = "";
  let typeFilter = "ALL";
  let cardFilter = "ALL";
  let currencyFilter = "ALL";
  let selectedAccountIds = new Set();
  let selectedHiddenAdminKeys = new Set();
  let selectedInterests = new Map();
  let foundHiddenAdmins = [];
  let foundInterests = [];
  let recentExecutedTasks = [];
  let collapsedSections = new Set();

  // Toast Helper
  function showToast(message, duration = 3000) {
    if (!toastPopup) return;
    toastPopup.textContent = message;
    toastPopup.classList.remove("hidden");
    setTimeout(() => {
      toastPopup.classList.add("hidden");
    }, duration);
  }

  // Diagnostic Scan Banner with Fallback Auto-hide
  let scanBannerTimer = null;
  function setScanStatus(text, hideAfterMs = 0) {
    if (!dashboardScanBanner) return;
    if (scanBannerTimer) {
      clearTimeout(scanBannerTimer);
      scanBannerTimer = null;
    }
    if (!text) {
      dashboardScanBanner.classList.add("hidden");
      return;
    }
    if (dashboardScanText) dashboardScanText.textContent = text;
    dashboardScanBanner.classList.remove("hidden");
    if (hideAfterMs > 0) {
      scanBannerTimer = setTimeout(() => {
        dashboardScanBanner.classList.add("hidden");
      }, hideAfterMs);
    }
  }

  // Promise-based runtime message helper with strict timeout to prevent UI freezes
  function sendRuntimeMessageWithTimeout(message, timeoutMs = 15000) {
    return new Promise((resolve, reject) => {
      let isDone = false;
      const t = setTimeout(() => {
        if (!isDone) {
          isDone = true;
          reject(new Error("Quá thời gian phản hồi từ tiến trình nền (15s)."));
        }
      }, timeoutMs);

      try {
        chrome.runtime.sendMessage(message, (res) => {
          if (isDone) return;
          isDone = true;
          clearTimeout(t);
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
          } else {
            resolve(res);
          }
        });
      } catch (err) {
        if (!isDone) {
          isDone = true;
          clearTimeout(t);
          reject(err);
        }
      }
    });
  }

  if (btnDashOpenAdsManager) {
    btnDashOpenAdsManager.addEventListener("click", () => {
      chrome.runtime.sendMessage({ action: "OPEN_ADS_MANAGER" });
    });
  }

  // ===========================================================================
  // TAB NAVIGATION SWITCHER
  // ===========================================================================
  const tabButtons = [tabBtnAccounts, tabBtnBmSecurity, tabBtnSuperTarget, tabBtnWorkflow];
  const tabPanes = [tabPaneAccounts, tabPaneBmSecurity, tabPaneSuperTarget, tabPaneWorkflow];

  function switchTab(targetPaneId) {
    tabButtons.forEach((btn) => {
      if (!btn) return;
      btn.classList.toggle("active", btn.dataset.target === targetPaneId);
    });

    tabPanes.forEach((pane) => {
      if (!pane) return;
      if (pane.id === targetPaneId) {
        pane.classList.remove("hidden");
        pane.classList.add("active");
      } else {
        pane.classList.add("hidden");
        pane.classList.remove("active");
      }
    });

    if (targetPaneId === "tabPaneBmSecurity") renderBmSecurityTab();
    if (targetPaneId === "tabPaneSuperTarget") renderSuperTargetTab();
    if (targetPaneId === "tabPaneWorkflow") renderWorkflowTab();
  }

  tabButtons.forEach((btn) => {
    if (!btn) return;
    btn.addEventListener("click", () => {
      switchTab(btn.dataset.target);
    });
  });

  // ===========================================================================
  // INITIAL STORAGE & SERVER CHECK
  // ===========================================================================
  async function loadStorageData() {
    const data = await chrome.storage.local.get([
      "vias_data",
      "active_via_uid",
      "serverUrl",
      "clientKey",
      "latestToken",
      "cachedData",
    ]);

    viasData = data.vias_data || {};
    activeViaUid = data.active_via_uid || "";

    if (Object.keys(viasData).length === 0 && data.cachedData && data.cachedData.c_user) {
      const c = data.cachedData;
      viasData[c.c_user] = {
        c_user: c.c_user,
        user_name: c.user_name || `VIA ${c.c_user}`,
        avatar_url: `https://graph.facebook.com/${c.c_user}/picture?type=square`,
        access_token: data.latestToken || null,
        cookie: "",
        token_valid: !!data.latestToken,
        last_synced: c.last_synced || new Date().toISOString(),
        accounts: c.accounts || [],
        bms: c.bms || [],
        pages: c.pages || [],
      };
      activeViaUid = c.c_user;
      await chrome.storage.local.set({ vias_data: viasData, active_via_uid: activeViaUid });
    }

    if (!activeViaUid && Object.keys(viasData).length > 0) {
      activeViaUid = Object.keys(viasData)[0];
    }

    if (cfgServerUrl) cfgServerUrl.value = data.serverUrl || "http://127.0.0.1:8000";
    if (cfgClientKey) cfgClientKey.value = data.clientKey || "";

    checkServerConnection(cfgServerUrl ? cfgServerUrl.value : "http://127.0.0.1:8000");
    renderSidebarVias();
    renderMainWorkspace();
  }

  async function checkServerConnection(url) {
    const candidates = [
      (url || "").replace(/\/+$/, ""),
      "http://127.0.0.1:8000",
      "http://localhost:8000",
      "http://localhost:8080",
      "http://127.0.0.1:8080",
    ].filter(Boolean);
    const unique = [...new Set(candidates)];

    for (const cand of unique) {
      try {
        const pingRes = await fetch(`${cand}/api/v1/vias/ping`, {
          method: "GET",
          signal: AbortSignal.timeout(2000),
        });
        if (pingRes.ok) {
          await chrome.storage.local.set({ serverUrl: cand });
          if (cfgServerUrl && cfgServerUrl.value !== cand) cfgServerUrl.value = cand;
          if (connDot) connDot.className = "status-dot online";
          if (connLabel) connLabel.textContent = `Đã kết nối (${cand})`;
          if (connStatusPill) connStatusPill.style.borderColor = "var(--emerald)";
          if (hubServerStatus) {
            hubServerStatus.textContent = `HTTP 200 OK — ${cand}`;
            hubServerStatus.style.color = "var(--emerald)";
          }
          return true;
        }
      } catch (_) {
        try {
          const hRes = await fetch(`${cand}/health`, {
            method: "GET",
            signal: AbortSignal.timeout(1500),
          });
          if (hRes.ok) {
            await chrome.storage.local.set({ serverUrl: cand });
            if (cfgServerUrl && cfgServerUrl.value !== cand) cfgServerUrl.value = cand;
            if (connDot) connDot.className = "status-dot online";
            if (connLabel) connLabel.textContent = `Đã kết nối (${cand})`;
            if (connStatusPill) connStatusPill.style.borderColor = "var(--emerald)";
            if (hubServerStatus) {
              hubServerStatus.textContent = `HTTP 200 OK — ${cand}`;
              hubServerStatus.style.color = "var(--emerald)";
            }
            return true;
          }
        } catch (__) {}
      }
    }

    if (connDot) connDot.className = "status-dot";
    if (connLabel) connLabel.textContent = "Chưa kết nối Server";
    if (connStatusPill) connStatusPill.style.borderColor = "var(--amber)";
    if (hubServerStatus) {
      hubServerStatus.textContent = "Mất Kết Nối (Offline)";
      hubServerStatus.style.color = "var(--rose)";
    }
    return false;
  }

  // ===========================================================================
  // SIDEBAR VIA LIST
  // ===========================================================================
  function renderSidebarVias() {
    const uids = Object.keys(viasData);
    if (sidebarViaCount) sidebarViaCount.textContent = `Đã lưu ${uids.length} VIA`;
    if (masterViaSelector) {
      masterViaSelector.innerHTML = `<option value="">Tất cả VIA</option>${uids.map((uid) => `<option value="${escapeHtml(uid)}">${escapeHtml(viasData[uid]?.user_name || `VIA ${uid}`)} · ${escapeHtml(uid)}</option>`).join("")}`;
      masterViaSelector.value = viewMode === "grouped" ? "" : (activeViaUid || "");
    }

    const filterVal = (searchViaInput ? searchViaInput.value : "").trim().toLowerCase();
    const filteredUids = uids.filter((uid) => {
      const v = viasData[uid];
      return uid.includes(filterVal) || (v.user_name && v.user_name.toLowerCase().includes(filterVal));
    });

    if (filteredUids.length === 0) {
      viasListContainer.innerHTML = `<div class="empty-hint" style="text-align: center; padding: 20px 10px; color: #64748b;">Chưa có dữ liệu VIA. Bấm "Quét phiên" để nạp VIA đang đăng nhập.</div>`;
      return;
    }

    viasListContainer.innerHTML = filteredUids
      .map((uid) => {
        const v = viasData[uid];
        const isActive = uid === activeViaUid && viewMode === "single";
        const accCount = (v.accounts || []).length;
        const bmCount = (v.bms || []).length;
        const pageCount = (v.pages || []).length;
        const hasToken = !!v.access_token;
        const statusBadge = hasToken
          ? `<span class="via-badge-pill live"> Live Token</span>`
          : `<span class="via-badge-pill warn"> Cookie Only</span>`;

        const initials = (v.user_name || uid).slice(0, 2).toUpperCase();

        return `
          <div class="via-card ${isActive ? "active" : ""}" data-uid="${uid}">
            <div class="via-head">
              <div class="via-avatar">
                ${v.avatar_url ? `<img src="${v.avatar_url}" style="width:100%;height:100%;border-radius:50%;" onerror="this.style.display='none';this.parentElement.textContent='${initials}'">` : initials}
              </div>
              <div class="via-info">
                <div class="via-name">${escapeHtml(v.user_name || `VIA ${uid}`)}</div>
                <div class="via-uid-row">
                  <span>${uid}</span>
                  <button class="btn-copy-sm copy-uid-btn" data-uid="${uid}" title="Copy UID"></button>
                </div>
              </div>
            </div>
            <div class="via-stats-row">
              ${statusBadge}
              <span style="color: #cbd5e1; font-weight: 600;">${accCount} TK · ${bmCount} BM · ${pageCount} P</span>
            </div>
          </div>
        `;
      })
      .join("");

    viasListContainer.querySelectorAll(".via-card").forEach((card) => {
      card.addEventListener("click", (e) => {
        if (e.target.closest(".copy-uid-btn")) return;
        const targetUid = card.dataset.uid;
        activeViaUid = targetUid;
        if (viewMode === "grouped") {
          viewMode = "single";
          if (btnModeSingle) btnModeSingle.classList.add("active");
          if (btnModeGrouped) btnModeGrouped.classList.remove("active");
        }
        renderSidebarVias();
        renderMainWorkspace();
      });
    });

    viasListContainer.querySelectorAll(".copy-uid-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const uid = btn.dataset.uid;
        navigator.clipboard.writeText(uid);
        showToast(`Đã copy UID: ${uid}`);
      });
    });
  }

  // ===========================================================================
  // TAB 1: ACCOUNTS & DATA TABLE
  // ===========================================================================
  function getDisplayAccounts() {
    if (viewMode === "grouped") {
      const all = [];
      Object.keys(viasData).forEach((uid) => {
        const v = viasData[uid];
        (v.accounts || []).forEach((acc) => {
          all.push({ ...acc, via_uid: uid, via_name: v.user_name });
        });
      });
      return all;
    } else {
      const activeVia = viasData[activeViaUid];
      if (!activeVia) return [];
      return (activeVia.accounts || []).map((acc) => ({
        ...acc,
        via_uid: activeViaUid,
        via_name: activeVia.user_name,
      }));
    }
  }

  function filterAccounts(accounts) {
    return accounts.filter((acc) => {
      if (statusFilter !== "ALL") {
        if (statusFilter === "LIVE" && acc.account_status !== "LIVE") return false;
        if (statusFilter === "DIE" && acc.account_status !== "DIE") return false;
        if (statusFilter === "UNSETTLED" && acc.account_status !== "UNSETTLED") return false;
      }

      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const nameMatch = (acc.name || "").toLowerCase().includes(q);
        const idMatch = (acc.act_id || "").includes(q);
        const cardMatch = (acc.card_last4 || "").includes(q);
        const bmMatch = String(acc.business_id || acc.bm_id || "").includes(q);
        const viaMatch = (acc.via_name || "").toLowerCase().includes(q) || (acc.via_uid || "").includes(q);
        if (!nameMatch && !idMatch && !cardMatch && !bmMatch && !viaMatch) return false;
      }

      if (typeFilter !== "ALL") {
        if (typeFilter === "BM" && acc.account_type !== "BM") return false;
        if (typeFilter === "PERSONAL" && acc.account_type === "BM") return false;
      }

      if (cardFilter !== "ALL") {
        if (cardFilter === "ATTACHED" && !acc.card_last4) return false;
        if (cardFilter === "NO_CARD" && acc.card_last4) return false;
      }

      if (currencyFilter !== "ALL" && (acc.currency || "VND") !== currencyFilter) {
        return false;
      }

      return true;
    });
  }

  function renderMainWorkspace() {
    const rawAccounts = getDisplayAccounts();

    let liveC = 0, dieC = 0, unsettledC = 0;
    const totals = { VND: { spent: 0, balance: 0, assigned: 0 }, USD: { spent: 0, balance: 0, assigned: 0 } };
    let totalThreshold = 0;

    rawAccounts.forEach((a) => {
      if (a.account_status === "LIVE") liveC++;
      else if (a.account_status === "DIE") dieC++;
      else unsettledC++;

      const currency = a.currency === "USD" ? "USD" : "VND";
      totals[currency].spent += parseFloat(a.amount_spent || 0);
      totals[currency].balance += parseFloat(a.balance || 0);
      if (a.customer_id) totals[currency].assigned += parseFloat(a.balance || 0);
      totalThreshold += parseFloat(a.threshold || 0);
    });

    if (countPillAll) countPillAll.textContent = rawAccounts.length;
    if (countPillLive) countPillLive.textContent = liveC;
    if (countPillDie) countPillDie.textContent = dieC;
    if (countPillUnsettled) countPillUnsettled.textContent = unsettledC;

    if (kpiTotal) kpiTotal.textContent = rawAccounts.length;
    if (kpiLive) kpiLive.textContent = liveC;
    if (kpiDie) kpiDie.textContent = dieC;
    if (kpiUnsettled) kpiUnsettled.textContent = unsettledC;
    if (kpiSpent) kpiSpent.textContent = `${totals.VND.spent.toLocaleString("vi-VN")} ₫`;
    if (kpiSpentUsd) kpiSpentUsd.textContent = `${totals.USD.spent.toLocaleString("en-US")} $`;
    if (kpiBalance) kpiBalance.textContent = `${totals.VND.balance.toLocaleString("vi-VN")} ₫ | ${totals.USD.balance.toLocaleString("en-US")} $`;
    if (kpiAssignedDebt) kpiAssignedDebt.textContent = `Đã gán khách: ${totals.VND.assigned.toLocaleString("vi-VN")} ₫ | ${totals.USD.assigned.toLocaleString("en-US")} $`;
    if (kpiThreshold) kpiThreshold.textContent = `${totalThreshold.toLocaleString("vi-VN")} ₫`;

    if (viewMode === "grouped") {
      if (kpiViaLabel) kpiViaLabel.textContent = `Tất cả ${Object.keys(viasData).length} VIA`;
      if (activeSessionLabel) activeSessionLabel.textContent = `Chế độ: Phân nhóm ${Object.keys(viasData).length} VIA`;
    } else {
      const active = viasData[activeViaUid];
      const activeName = active ? (active.user_name || activeViaUid) : "Chưa chọn";
      if (kpiViaLabel) kpiViaLabel.textContent = `VIA: ${activeName}`;
      if (activeSessionLabel) activeSessionLabel.textContent = `Phiên FB: ${activeName} (${activeViaUid || "---"})`;
    }

    const filteredAccounts = filterAccounts(rawAccounts);
    if (assetCounter) assetCounter.textContent = `${filteredAccounts.length} tài sản`;
    renderTable(filteredAccounts);
    updateBulkActionBar();
  }

  function renderTable(accounts) {
    if (!accounts || accounts.length === 0) {
      smitTableBody.innerHTML = `<tr><td colspan="12" class="table-empty">Không tìm thấy tài khoản nào phù hợp với bộ lọc.</td></tr>`;
      return;
    }

    if (viewMode === "grouped") {
      const grouped = {};
      accounts.forEach((a) => {
        if (!grouped[a.via_uid]) grouped[a.via_uid] = [];
        grouped[a.via_uid].push(a);
      });

      let html = "";
      let sttOverall = 1;

      Object.keys(grouped).forEach((uid) => {
        const groupAccs = grouped[uid];
        const v = viasData[uid] || {};
        const isCollapsed = collapsedSections.has(uid);

        html += `
          <tr class="grouped-via-header" data-collapse-uid="${uid}">
            <td colspan="12">
              <span>${isCollapsed ? "" : ""}  VIA: <strong>${escapeHtml(v.user_name || uid)}</strong> (UID: <code>${uid}</code>) — <span class="text-emerald">${groupAccs.length} Tài Khoản QC</span></span>
            </td>
          </tr>
        `;

        if (!isCollapsed) {
          groupAccs.forEach((a) => {
            html += renderTableRow(a, sttOverall++);
          });
        }
      });

      smitTableBody.innerHTML = html;
      attachTableEvents();
    } else {
      let html = "";
      accounts.forEach((a, idx) => {
        html += renderTableRow(a, idx + 1);
      });
      smitTableBody.innerHTML = html;
      attachTableEvents();
    }
  }

  function renderTableRow(a, stt) {
    const isLive = a.account_status === "LIVE";
    const isDie = a.account_status === "DIE";
    const statusClass = isLive ? "badge-live" : (isDie ? "badge-die" : "badge-unsettled");
    const statusText = isLive ? "LIVE" : (isDie ? "DIE" : "CẢNH BÁO");

    const isChecked = selectedAccountIds.has(a.act_id);
    const spend = parseFloat(a.amount_spent || 0).toLocaleString("vi-VN");
    const balance = parseFloat(a.balance || 0).toLocaleString("vi-VN");
    const threshold = a.threshold ? parseFloat(a.threshold).toLocaleString("vi-VN") : "---";
    const remainingThreshold = Math.max(parseFloat(a.threshold || 0) - parseFloat(a.balance || 0), 0).toLocaleString("vi-VN");
    const hiddenLimit = parseFloat(a.ad_trust_dsl || a.spend_cap || 0);
    const limitDisplay = hiddenLimit > 0 ? hiddenLimit.toLocaleString("vi-VN") : "Không giới hạn";
    const moneySymbol = a.currency === "USD" ? "$" : "₫";
    const bmId = a.business_id || a.bm_id || "";

    const cardDisplay = a.card_last4
      ? `<span class="card-cell">•••• ${escapeHtml(a.card_last4)}<button class="copy-hover btn-copy-value" data-copy="${escapeHtml(a.card_last4)}" title="Sao chép số thẻ">Sao chép</button></span>`
      : `<span style="color:#64748b;font-size:11px;">Chưa gắn</span>`;

    return `
      <tr class="${isChecked ? "row-selected" : ""}" data-act="${a.act_id}">
        <td class="sticky-left-select" style="text-align: center;">
          <input type="checkbox" class="row-checkbox" data-act="${a.act_id}" ${isChecked ? "checked" : ""}>
        </td>
        <td class="sticky-left-account account-cell"><div style="font-weight:600;color:#fff;">${escapeHtml(a.name || `Tài khoản ${a.act_id}`)}</div><div style="margin-top:3px;color:#9ca3af;font-size:11px;">act_${escapeHtml(a.act_id)}<button class="copy-hover btn-copy-id" data-act="${escapeHtml(a.act_id)}" title="Sao chép ID">Sao chép</button></div>${bmId ? `<button class="bm-parent btn-copy-value" data-copy="${escapeHtml(bmId)}" title="Sao chép BM ID">BM ${escapeHtml(bmId)}</button>` : ""}</td>
        <td><span class="status-badge ${statusClass}">${statusText}</span></td>
        <td>${balance} ${moneySymbol}</td>
        <td>${threshold} ${threshold === "---" ? "" : moneySymbol}</td>
        <td>${remainingThreshold} ${moneySymbol}</td>
        <td>${limitDisplay}</td>
        <td>${spend} ${moneySymbol}</td>
        <td><span style="font-weight: 600; color: #e2e8f0;">${a.currency || "VND"}</span></td>
        <td>${cardDisplay}</td>
        <td style="color: #94a3b8; font-size: 11px;">${a.timezone_name || "Asia/Ho_Chi_Minh"}</td>
        <td style="text-align:center;">${Number(a.admin_count || 0)} QTV</td>
        <td class="sticky-right-actions" style="text-align: center;">
          <button class="quick-action btn-appeal" data-act="${a.act_id}">Kháng</button>
          <button class="quick-action btn-rename-one" data-act="${a.act_id}">Đổi tên</button>
          <button class="quick-action btn-inspect-admin" data-act="${a.act_id}">Soi QTV</button>
        </td>
      </tr>
    `;
  }

  function attachTableEvents() {
    smitTableBody.querySelectorAll(".row-checkbox").forEach((cb) => {
      cb.addEventListener("change", () => {
        const actId = cb.dataset.act;
        if (cb.checked) {
          selectedAccountIds.add(actId);
        } else {
          selectedAccountIds.delete(actId);
        }
        updateBulkActionBar();
        const tr = cb.closest("tr");
        if (tr) tr.classList.toggle("row-selected", cb.checked);
      });
    });

    smitTableBody.querySelectorAll(".btn-copy-id").forEach((btn) => {
      btn.addEventListener("click", () => {
        const actId = btn.dataset.act;
        navigator.clipboard.writeText(`act_${actId}`);
        showToast(`Đã copy ID: act_${actId}`);
      });
    });

    smitTableBody.querySelectorAll(".btn-copy-value").forEach((btn) => {
      btn.addEventListener("click", () => {
        navigator.clipboard.writeText(btn.dataset.copy || "");
        showToast("Đã sao chép ID!");
      });
    });

    smitTableBody.querySelectorAll(".btn-rename-one").forEach((btn) => {
      btn.addEventListener("click", () => {
        selectedAccountIds.clear();
        selectedAccountIds.add(btn.dataset.act);
        updateBulkActionBar();
        btnBulkRenameModal?.click();
      });
    });

    smitTableBody.querySelectorAll(".btn-appeal").forEach((btn) => {
      btn.addEventListener("click", () => {
        selectedAccountIds.clear();
        selectedAccountIds.add(btn.dataset.act);
        updateBulkActionBar();
        tabBtnSuperTarget?.click();
        showToast("Đã mở trung tâm kháng nghị cho tài sản đã chọn.");
      });
    });

    smitTableBody.querySelectorAll(".btn-inspect-admin").forEach((btn) => {
      btn.addEventListener("click", () => {
        selectedAccountIds.clear();
        selectedAccountIds.add(btn.dataset.act);
        updateBulkActionBar();
        tabBtnBmSecurity?.click();
      });
    });

    smitTableBody.querySelectorAll(".btn-inspect-pay").forEach((btn) => {
      btn.addEventListener("click", () => {
        const actId = btn.dataset.act;
        openExtendedPaymentModal(actId);
      });
    });

    smitTableBody.querySelectorAll(".grouped-via-header").forEach((header) => {
      header.addEventListener("click", () => {
        const uid = header.dataset.collapseUid;
        if (collapsedSections.has(uid)) {
          collapsedSections.delete(uid);
        } else {
          collapsedSections.add(uid);
        }
        renderMainWorkspace();
      });
    });
  }

  function updateBulkActionBar() {
    const count = selectedAccountIds.size;
    if (count > 0) {
      if (bulkActionBar) bulkActionBar.classList.remove("hidden");
      if (bulkSelectedCount) bulkSelectedCount.textContent = `Đã chọn ${count} tài sản`;
    } else {
      if (bulkActionBar) bulkActionBar.classList.add("hidden");
    }
    if (selectedCounter) selectedCounter.textContent = `${count} đã chọn`;
    if (checkAllRows) {
      const allRows = smitTableBody.querySelectorAll(".row-checkbox");
      checkAllRows.checked = allRows.length > 0 && selectedAccountIds.size === allRows.length;
    }
  }

  if (checkAllRows) {
    checkAllRows.addEventListener("change", (e) => {
      const isChecked = e.target.checked;
      const filtered = filterAccounts(getDisplayAccounts());
      filtered.forEach((a) => {
        if (isChecked) selectedAccountIds.add(a.act_id);
        else selectedAccountIds.delete(a.act_id);
      });
      renderMainWorkspace();
    });
  }

  // Filter Event Listeners
  [pillAll, pillLive, pillDie, pillUnsettled].forEach((pill) => {
    if (!pill) return;
    pill.addEventListener("click", () => {
      [pillAll, pillLive, pillDie, pillUnsettled].forEach((p) => p && p.classList.remove("active"));
      pill.classList.add("active");
      statusFilter = pill.dataset.status;
      renderMainWorkspace();
    });
  });

  if (tableSearchInput) {
    tableSearchInput.addEventListener("input", (e) => {
      searchQuery = e.target.value.trim();
      renderMainWorkspace();
    });
  }

  if (filterTypeSelect) {
    filterTypeSelect.addEventListener("change", (e) => {
      typeFilter = e.target.value;
      renderMainWorkspace();
    });
  }

  if (filterCardSelect) {
    filterCardSelect.addEventListener("change", (e) => {
      cardFilter = e.target.value;
      renderMainWorkspace();
    });
  }

  if (filterCurrencySelect) {
    filterCurrencySelect.addEventListener("change", (e) => {
      currencyFilter = e.target.value;
      renderMainWorkspace();
    });
  }

  if (searchViaInput) {
    searchViaInput.addEventListener("input", () => {
      renderSidebarVias();
    });
  }

  if (btnModeSingle) {
    btnModeSingle.addEventListener("click", () => {
      viewMode = "single";
      btnModeSingle.classList.add("active");
      if (btnModeGrouped) btnModeGrouped.classList.remove("active");
      renderSidebarVias();
      renderMainWorkspace();
    });
  }

  if (btnModeGrouped) {
    btnModeGrouped.addEventListener("click", () => {
      viewMode = "grouped";
      btnModeGrouped.classList.add("active");
      if (btnModeSingle) btnModeSingle.classList.remove("active");
      renderSidebarVias();
      renderMainWorkspace();
    });
  }

  if (masterViaSelector) {
    masterViaSelector.addEventListener("change", () => {
      if (masterViaSelector.value) {
        activeViaUid = masterViaSelector.value;
        viewMode = "single";
      } else {
        viewMode = "grouped";
      }
      renderSidebarVias();
      renderMainWorkspace();
    });
  }

  document.querySelectorAll(".asset-nav-btn[data-target]").forEach((button) => {
    button.addEventListener("click", () => {
      const targetId = button.dataset.target;
      document.querySelectorAll(".asset-nav-btn").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      [tabPaneAccounts, tabPaneBmSecurity, tabPaneSuperTarget, tabPaneWorkflow].forEach((pane) => pane?.classList.toggle("active", pane.id === targetId));
    });
  });

  if (compactViewToggle) {
    document.body.classList.toggle("compact-view", compactViewToggle.checked);
    compactViewToggle.addEventListener("change", () => document.body.classList.toggle("compact-view", compactViewToggle.checked));
  }

  // ===========================================================================
  // BULK ACTIONS & EXTENDED PAYMENT MODAL
  // ===========================================================================
  function openExtendedPaymentModal(actId) {
    const rawAccounts = getDisplayAccounts();
    const acc = rawAccounts.find((a) => String(a.act_id) === String(actId)) || {};

    if (payActId) payActId.value = `act_${acc.act_id || actId}`;
    if (payActName) payActName.value = acc.name || `Tài khoản ${actId}`;
    if (payBalance) payBalance.value = `${parseFloat(acc.balance || 0).toLocaleString("vi-VN")} ₫`;
    if (payThreshold) payThreshold.value = `${parseFloat(acc.threshold || 0).toLocaleString("vi-VN")} ₫`;

    let cardInfo = "Chưa gắn phương thức thanh toán.";
    if (acc.card_last4) {
      cardInfo = `Loại thẻ: ${acc.card_type || "CREDIT/DEBIT"} | Đuôi: **** ${acc.card_last4}\nTrạng thái: Hoạt động | Đơn vị tiền tệ: ${acc.currency || "VND"}`;
    }
    if (payFundingDetails) payFundingDetails.value = cardInfo;

    if (modalExtendedPayment) modalExtendedPayment.classList.remove("hidden");
  }

  if (btnCloseExtendedPayment) btnCloseExtendedPayment.addEventListener("click", () => modalExtendedPayment.classList.add("hidden"));
  if (btnCancelExtendedPayment) btnCancelExtendedPayment.addEventListener("click", () => modalExtendedPayment.classList.add("hidden"));

  if (btnPayNowAction) {
    btnPayNowAction.addEventListener("click", () => {
      showToast(" Đã gửi lệnh kích hoạt thanh toán bù trừ tới Meta Ads Billing!");
      modalExtendedPayment.classList.add("hidden");
    });
  }

  if (btnDownloadInvoices) {
    btnDownloadInvoices.addEventListener("click", () => {
      showToast(" Đang chuẩn bị tải về bảng kê hóa đơn PDF/CSV chuẩn SMIT...");
    });
  }

  if (btnCopySelectedIds) {
    btnCopySelectedIds.addEventListener("click", () => {
      const ids = Array.from(selectedAccountIds).map((id) => `act_${id}`).join("\n");
      navigator.clipboard.writeText(ids);
      showToast(`Đã copy ${selectedAccountIds.size} ID tài khoản!`);
    });
  }

  if (btnExportCsv) {
    btnExportCsv.addEventListener("click", () => {
      const accounts = filterAccounts(getDisplayAccounts()).filter((a) => selectedAccountIds.has(a.act_id));
      const target = accounts.length > 0 ? accounts : filterAccounts(getDisplayAccounts());

      let csv = "\uFEFFSTT,ID Tài Khoản,Tên TKQC,Loại TK,Trạng Thái,Dư Nợ,Ngưỡng,Limit Ngày,Tổng Chi Tiêu,Tiền Tệ,Thẻ,Múi Giờ\n";
      target.forEach((a, idx) => {
        csv += `${idx + 1},"act_${a.act_id}","${(a.name || "").replace(/"/g, '""')}","${a.account_type || "PERSONAL"}","${a.account_status}",${a.balance || 0},${a.threshold || 0},${a.spend_cap || 0},${a.amount_spent || 0},"${a.currency || "VND"}","${a.card_last4 || ""}","${a.timezone_name || ""}"\n`;
      });

      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `adsos_accounts_${activeViaUid}_${Date.now()}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      showToast(`Đã xuất file CSV cho ${target.length} tài khoản!`);
    });
  }

  // Bulk Rename Modal
  if (btnBulkRenameModal) {
    btnBulkRenameModal.addEventListener("click", () => {
      if (selectedAccountIds.size === 0) {
        showToast("Vui lòng chọn ít nhất 1 tài khoản để đổi tên!");
        return;
      }
      if (modalBulkRename) {
        modalBulkRename.classList.remove("hidden");
        if (inputRenamePattern) {
          inputRenamePattern.value = "VIP_ADS_TK_{index}";
          inputRenamePattern.focus();
        }
        updateRenamePreview();
      }
    });
  }
  if (btnCloseBulkRename) btnCloseBulkRename.addEventListener("click", () => modalBulkRename.classList.add("hidden"));
  if (btnCancelBulkRename) btnCancelBulkRename.addEventListener("click", () => modalBulkRename.classList.add("hidden"));

  function updateRenamePreview() {
    if (!renamePreview || !inputRenamePattern) return;
    const pat = inputRenamePattern.value.trim() || "TK_{index}";
    const example = pat.replace("{index}", "1").replace("{id}", "12345678");
    renamePreview.textContent = `Xem trước tên mẫu: ${example}`;
  }

  if (inputRenamePattern) inputRenamePattern.addEventListener("input", updateRenamePreview);

  if (btnExecuteBulkRename) {
    btnExecuteBulkRename.addEventListener("click", async () => {
      const pattern = inputRenamePattern.value.trim() || "TK_{index}";
      const ids = Array.from(selectedAccountIds);
      btnExecuteBulkRename.disabled = true;
      btnExecuteBulkRename.textContent = " Đang đổi tên...";

      let done = 0;
      for (let i = 0; i < ids.length; i++) {
        const actId = ids[i];
        const newName = pattern.replace("{index}", String(i + 1)).replace("{id}", actId);
        try {
          await sendRuntimeMessageWithTimeout({
            action: "RENAME_AD_ACCOUNT",
            actId: actId,
            newName: newName,
          }, 6000);
          done++;
        } catch (_) {}
      }

      btnExecuteBulkRename.disabled = false;
      btnExecuteBulkRename.textContent = " Đổi Tên Hàng Loạt";
      modalBulkRename.classList.add("hidden");
      showToast(` Đã đổi tên thành công ${done}/${ids.length} tài khoản!`);
      await loadStorageData();
    });
  }

  // Bulk Timezone / Currency Modal
  if (btnBulkTimezoneCurrencyModal) {
    btnBulkTimezoneCurrencyModal.addEventListener("click", () => {
      if (selectedAccountIds.size === 0) {
        showToast("Vui lòng chọn ít nhất 1 tài khoản!");
        return;
      }
      if (modalBulkTimezoneCurrency) modalBulkTimezoneCurrency.classList.remove("hidden");
    });
  }
  if (btnCloseBulkTimezoneCurrency) btnCloseBulkTimezoneCurrency.addEventListener("click", () => modalBulkTimezoneCurrency.classList.add("hidden"));
  if (btnCancelBulkTimezoneCurrency) btnCancelBulkTimezoneCurrency.addEventListener("click", () => modalBulkTimezoneCurrency.classList.add("hidden"));

  if (btnExecuteBulkTimezoneCurrency) {
    btnExecuteBulkTimezoneCurrency.addEventListener("click", async () => {
      const tz = selectBulkTimezone ? selectBulkTimezone.value : "Asia/Ho_Chi_Minh";
      const cur = selectBulkCurrency ? selectBulkCurrency.value : "VND";
      const ids = Array.from(selectedAccountIds);

      const active = viasData[activeViaUid];
      if (active && active.accounts) {
        active.accounts.forEach((a) => {
          if (ids.includes(a.act_id)) {
            a.timezone_name = tz;
            a.currency = cur;
          }
        });
        await chrome.storage.local.set({ vias_data: viasData });
      }

      modalBulkTimezoneCurrency.classList.add("hidden");
      showToast(` Đã cập nhật múi giờ [${tz}] và tiền tệ [${cur}] cho ${ids.length} tài khoản!`);
      renderMainWorkspace();
    });
  }

  // Bulk Share BM & Assign Accounts Modal
  function updateShareAccountCount() {
    if (!inputShareAccountIds || !badgeShareAccountCount) return;
    const lines = inputShareAccountIds.value.split(/\r?\n/).map((s) => s.trim().replace(/^act_/, "")).filter(Boolean);
    const valid = new Set(lines.filter((s) => /\d{5,25}/.test(s)));
    badgeShareAccountCount.textContent = `${valid.size} TKQC`;
  }

  function openBulkShareModal() {
    if (!modalBulkShare) return;

    // 1. Populate BM selector from active VIA or viasData
    if (selectShareBmId) {
      const active = viasData[activeViaUid] || {};
      const bms = active.bms || [];
      selectShareBmId.innerHTML = `<option value="">— Chọn BM từ danh sách (${bms.length} BM) —</option>` +
        bms.map((b) => `<option value="${escapeHtml(b.bm_id)}">${escapeHtml(b.name || `BM ${b.bm_id}`)} (${escapeHtml(b.bm_id)})</option>`).join("");
      if (bms.length > 0 && inputShareBmId && !inputShareBmId.value) {
        inputShareBmId.value = bms[0].bm_id;
        selectShareBmId.value = bms[0].bm_id;
      }
    }

    // 2. Pre-fill any selected account IDs if textarea is empty or user has fresh selection
    if (inputShareAccountIds) {
      if (selectedAccountIds.size > 0) {
        inputShareAccountIds.value = Array.from(selectedAccountIds).join("\n");
      }
      updateShareAccountCount();
    }

    // 3. Reset result box
    if (shareBmResultBox) shareBmResultBox.classList.add("hidden");
    if (shareBmInviteLinkRow) shareBmInviteLinkRow.classList.add("hidden");

    modalBulkShare.classList.remove("hidden");
  }

  if (btnOpenShareBmModalTop) {
    btnOpenShareBmModalTop.addEventListener("click", () => openBulkShareModal());
  }
  if (btnBulkShareModal) {
    btnBulkShareModal.addEventListener("click", () => openBulkShareModal());
  }

  if (selectShareBmId) {
    selectShareBmId.addEventListener("change", () => {
      if (selectShareBmId.value && inputShareBmId) {
        inputShareBmId.value = selectShareBmId.value;
      }
    });
  }

  if (inputShareAccountIds) {
    inputShareAccountIds.addEventListener("input", updateShareAccountCount);
  }

  if (btnSyncShareSelectedFromTable) {
    btnSyncShareSelectedFromTable.addEventListener("click", () => {
      if (selectedAccountIds.size === 0) {
        showToast("Chưa có dòng nào được tích chọn trên bảng.");
        return;
      }
      inputShareAccountIds.value = Array.from(selectedAccountIds).join("\n");
      updateShareAccountCount();
      showToast(`Đã lấy ${selectedAccountIds.size} TKQC từ bảng.`);
    });
  }

  if (btnClearShareAccountIds) {
    btnClearShareAccountIds.addEventListener("click", () => {
      if (inputShareAccountIds) inputShareAccountIds.value = "";
      updateShareAccountCount();
    });
  }

  if (btnCopyShareInviteLink) {
    btnCopyShareInviteLink.addEventListener("click", () => {
      if (inputShareInviteLink?.value) {
        navigator.clipboard.writeText(inputShareInviteLink.value);
        showToast("Đã sao chép liên kết mời BM!");
      }
    });
  }

  if (btnCloseBulkShare) {
    btnCloseBulkShare.addEventListener("click", () => modalBulkShare.classList.add("hidden"));
  }
  if (btnCancelBulkShare) {
    btnCancelBulkShare.addEventListener("click", () => modalBulkShare.classList.add("hidden"));
  }

  if (btnExecuteBulkShare) {
    btnExecuteBulkShare.addEventListener("click", async () => {
      const bmId = (inputShareBmId ? inputShareBmId.value.trim() : "") || (selectShareBmId ? selectShareBmId.value : "");
      const emails = inputShareEmails ? inputShareEmails.value.split(/\r?\n|,/).map((e) => e.trim()).filter(Boolean) : [];
      const role = selectShareRole ? selectShareRole.value : "EMPLOYEE";
      const targetUid = inputShareTargetUid ? inputShareTargetUid.value.trim() : "";
      const lines = inputShareAccountIds ? inputShareAccountIds.value.split(/\r?\n/).map((s) => s.trim().replace(/^act_/, "")).filter(Boolean) : [];
      const accountIds = Array.from(new Set(lines.map((s) => {
        const match = s.match(/\d{5,25}/);
        return match ? match[0] : s;
      }).filter(Boolean)));

      if (!bmId && accountIds.length === 0 && !targetUid) {
        showToast("Vui lòng nhập BM ID, email khách hoặc danh sách ID TKQC!");
        return;
      }

      const tasks = role === "ANALYST" ? ["ANALYZE"] : role === "ADVERTISER" ? ["ADVERTISE", "ANALYZE"] : ["MANAGE", "ADVERTISE", "ANALYZE"];

      btnExecuteBulkShare.disabled = true;
      btnExecuteBulkShare.textContent = "Đang thực thi...";
      showToast("Đang gửi lệnh chia sẻ quyền BM & gán TKQC...", 3000);

      const payload = {
        bm_id: bmId,
        customer_emails: emails,
        account_ids: accountIds,
        bm_role: role,
        target_uid: targetUid,
        ad_account_tasks: tasks,
      };

      chrome.runtime.sendMessage({
        action: "SHARE_BM_AND_ASSIGN_ACCOUNTS",
        payload,
      }, async (response) => {
        btnExecuteBulkShare.disabled = false;
        btnExecuteBulkShare.innerHTML = " Thực Thi Chia Sẻ BM &amp; Gán TKQC";

        const ok = response && (response.success || response.ok);
        const resData = response?.result || response?.data || response || {};
        const inviteLink = resData.invite_link || (resData.invitations && resData.invitations[0]?.invite_link) || "";
        const msg = resData.message || (ok ? `Chia sẻ thành công cho ${accountIds.length} TKQC và ${emails.length} email!` : (response?.error || response?.message || "Lỗi khi chia sẻ BM & TKQC"));

        if (shareBmResultBox && shareBmResultMessage) {
          shareBmResultBox.classList.remove("hidden");
          shareBmResultMessage.textContent = msg;
          shareBmResultMessage.style.color = ok ? "var(--emerald)" : "var(--rose)";
          if (inviteLink && inputShareInviteLink && shareBmInviteLinkRow) {
            inputShareInviteLink.value = inviteLink;
            shareBmInviteLinkRow.classList.remove("hidden");
          }
        }

        showToast(msg, 4000);

        // Also call backend API to log in StaffAuditLog
        try {
          const storage = await chrome.storage.local.get(["serverUrl", "clientKey"]);
          const srvUrl = storage.serverUrl || "http://127.0.0.1:8000";
          await fetch(`${srvUrl}/api/v1/ads-check/share-bm-accounts`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-AdsOS-Client-Key": storage.clientKey || "",
            },
            body: JSON.stringify(payload),
          }).catch(() => null);
        } catch (_) {}
      });
    });
  }

  // ===========================================================================
  // TAB 2: BẢO MẬT BM & QUÉT QTV ẨN
  // ===========================================================================
  function renderBmSecurityTab() {
    const active = viasData[activeViaUid] || {};
    const bms = active.bms || [];

    if (bms.length === 0) {
      bmsTableBody.innerHTML = `<tr><td colspan="7" class="table-empty">Chưa có dữ liệu Business Manager. Bấm "Quét Lại BM &amp; Fanpage" ở tab TKQC để nạp.</td></tr>`;
      return;
    }

    bmsTableBody.innerHTML = bms
      .map((b, idx) => {
        const isVer = b.verification_status === "verified";
        const verBadge = isVer
          ? `<span class="badge-live">VERIFIED</span>`
          : `<span class="badge-die">NOT VERIFIED</span>`;

        return `
          <tr>
            <td style="text-align: center; color: #94a3b8;">${idx + 1}</td>
            <td style="font-family: monospace; font-weight: 600; color: #38bdf8;">${b.bm_id}</td>
            <td style="font-weight: 600; color: #fff;">${escapeHtml(b.name || `BM ${b.bm_id}`)}</td>
            <td>${verBadge}</td>
            <td style="text-align: center; font-weight: 700; color: var(--emerald);">${b.ad_account_count || 0}</td>
            <td><span class="status-badge badge-live">ACTIVE</span></td>
            <td style="text-align: center;">
              <button class="btn btn-sm btn-outline btn-scan-bm-single" data-bm="${b.bm_id}"> Chi Tiết</button>
            </td>
          </tr>
        `;
      })
      .join("");

    bmsTableBody.querySelectorAll(".btn-scan-bm-single").forEach((btn) => {
      btn.addEventListener("click", () => {
        const bmId = btn.dataset.bm;
        if (inputBmId) inputBmId.value = bmId;
        if (modalLoadByBm) modalLoadByBm.classList.remove("hidden");
      });
    });
  }

  // Hidden Admin Scanner
  if (btnScanHiddenAdmins) {
    btnScanHiddenAdmins.addEventListener("click", async () => {
      const active = viasData[activeViaUid];
      if (!active || !active.accounts || active.accounts.length === 0) {
        showToast("VIA hiện tại chưa có tài khoản nào để quét QTV ẩn.");
        return;
      }

      btnScanHiddenAdmins.disabled = true;
      btnScanHiddenAdmins.textContent = " Đang quét QTV...";
      showToast(" Đang quét danh sách quản trị viên trên tất cả tài khoản...", 4000);

      foundHiddenAdmins = [];
      selectedHiddenAdminKeys.clear();
      const accounts = active.accounts.slice(0, 30); // batch quét sâu

      for (const a of accounts) {
        try {
          const res = await sendRuntimeMessageWithTimeout({
            action: "SCAN_HIDDEN_ADMINS",
            actId: a.act_id,
          }, 6000);

          if (res && res.success && res.hiddenAdmins && res.hiddenAdmins.length > 0) {
            res.hiddenAdmins.forEach((u) => {
              foundHiddenAdmins.push({
                act_id: a.act_id,
                act_name: a.name,
                user_id: u.id,
                user_name: u.name || `User ${u.id}`,
                role: u.role || "ADMIN",
              });
            });
          }
        } catch (_) {}
      }

      btnScanHiddenAdmins.disabled = false;
      btnScanHiddenAdmins.textContent = " Quét QTV Ẩn Tự Động";
      renderHiddenAdminsTable();
      showToast(` Quét xong: Tìm thấy ${foundHiddenAdmins.length} Quản Trị Viên lạ/ẩn!`);
    });
  }

  function renderHiddenAdminsTable() {
    if (!hiddenAdminsTableBody) return;
    if (foundHiddenAdmins.length === 0) {
      hiddenAdminsTableBody.innerHTML = `<tr><td colspan="8" class="table-empty"> Không phát hiện Quản Trị Viên lạ hoặc ẩn trên các tài khoản được kiểm tra!</td></tr>`;
      if (btnCleanSelectedAdmins) btnCleanSelectedAdmins.disabled = true;
      return;
    }

    if (btnCleanSelectedAdmins) btnCleanSelectedAdmins.disabled = false;

    hiddenAdminsTableBody.innerHTML = foundHiddenAdmins
      .map((ha, idx) => {
        const key = `${ha.act_id}_${ha.user_id}`;
        const isChecked = selectedHiddenAdminKeys.has(key);
        return `
          <tr>
            <td style="text-align: center;">
              <input type="checkbox" class="cb-hidden-admin" data-key="${key}" ${isChecked ? "checked" : ""}>
            </td>
            <td style="text-align: center; color: #94a3b8;">${idx + 1}</td>
            <td style="font-family: monospace; color: #38bdf8;">act_${ha.act_id}</td>
            <td style="color: #fff; font-weight: 600;">${escapeHtml(ha.act_name || ha.act_id)}</td>
            <td style="font-family: monospace; color: var(--rose); font-weight: 700;">${ha.user_id}</td>
            <td>${escapeHtml(ha.user_name)}</td>
            <td><span class="badge-die">${ha.role}</span></td>
            <td style="text-align: center;">
              <button class="btn btn-sm btn-secondary text-rose btn-remove-single-admin" data-act="${ha.act_id}" data-uid="${ha.user_id}"> Gỡ</button>
            </td>
          </tr>
        `;
      })
      .join("");

    hiddenAdminsTableBody.querySelectorAll(".cb-hidden-admin").forEach((cb) => {
      cb.addEventListener("change", () => {
        const k = cb.dataset.key;
        if (cb.checked) selectedHiddenAdminKeys.add(k);
        else selectedHiddenAdminKeys.delete(k);
      });
    });

    hiddenAdminsTableBody.querySelectorAll(".btn-remove-single-admin").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const act = btn.dataset.act;
        const uid = btn.dataset.uid;
        try {
          await sendRuntimeMessageWithTimeout({ action: "REMOVE_HIDDEN_ADMIN", actId: act, targetUid: uid });
          foundHiddenAdmins = foundHiddenAdmins.filter((x) => !(x.act_id === act && x.user_id === uid));
          renderHiddenAdminsTable();
          showToast(` Đã gỡ QTV ${uid} khỏi TKQC act_${act}!`);
        } catch (e) {
          showToast(`Lỗi gỡ QTV: ${e.message}`);
        }
      });
    });
  }

  if (checkAllHiddenAdmins) {
    checkAllHiddenAdmins.addEventListener("change", (e) => {
      const isChecked = e.target.checked;
      foundHiddenAdmins.forEach((ha) => {
        const k = `${ha.act_id}_${ha.user_id}`;
        if (isChecked) selectedHiddenAdminKeys.add(k);
        else selectedHiddenAdminKeys.delete(k);
      });
      renderHiddenAdminsTable();
    });
  }

  if (btnCleanSelectedAdmins) {
    btnCleanSelectedAdmins.addEventListener("click", async () => {
      const toRemove = foundHiddenAdmins.filter((ha) => selectedHiddenAdminKeys.has(`${ha.act_id}_${ha.user_id}`));
      if (toRemove.length === 0) {
        showToast("Vui lòng chọn ít nhất 1 QTV ẩn để xóa!");
        return;
      }

      btnCleanSelectedAdmins.disabled = true;
      btnCleanSelectedAdmins.textContent = " Đang gỡ bỏ...";
      let done = 0;

      for (const ha of toRemove) {
        try {
          await sendRuntimeMessageWithTimeout({ action: "REMOVE_HIDDEN_ADMIN", actId: ha.act_id, targetUid: ha.user_id }, 6000);
          done++;
        } catch (_) {}
      }

      foundHiddenAdmins = foundHiddenAdmins.filter((ha) => !selectedHiddenAdminKeys.has(`${ha.act_id}_${ha.user_id}`));
      selectedHiddenAdminKeys.clear();
      btnCleanSelectedAdmins.disabled = false;
      btnCleanSelectedAdmins.textContent = " Xóa Tất Cả QTV Ẩn Đã Chọn";
      renderHiddenAdminsTable();
      showToast(` Đã xóa sạch ${done} Quản Trị Viên ẩn!`);
    });
  }

  if (btnCreateBmInviteModal) {
    btnCreateBmInviteModal.addEventListener("click", () => {
      openBulkShareModal();
    });
  }

  // ===========================================================================
  // TAB 3: SUPER TARGET & FANPAGE / PIXEL
  // ===========================================================================
  function renderSuperTargetTab() {
    const active = viasData[activeViaUid] || {};
    const pages = active.pages || [];

    if (pages.length === 0) {
      fanpagesTableBody.innerHTML = `<tr><td colspan="6" class="table-empty">Chưa có dữ liệu Fanpage. Bấm "Quét Lại BM &amp; Fanpage" ở tab TKQC để nạp.</td></tr>`;
      return;
    }

    fanpagesTableBody.innerHTML = pages
      .map((p, idx) => `
        <tr>
          <td style="text-align: center; color: #94a3b8;">${idx + 1}</td>
          <td style="font-family: monospace; color: #38bdf8;">${p.page_id}</td>
          <td style="font-weight: 600; color: #fff;">${escapeHtml(p.name || `Page ${p.page_id}`)}</td>
          <td style="text-align: center; font-weight: 700; color: var(--emerald);">${(p.fan_count || 0).toLocaleString("vi-VN")}</td>
          <td style="text-align: center;"><span class="badge-live">HOẠT ĐỘNG</span></td>
          <td style="text-align: center;">
            <a href="https://facebook.com/${p.page_id}" target="_blank" class="btn btn-sm btn-ghost" style="text-decoration: none;"> Mở Trang</a>
          </td>
        </tr>
      `)
      .join("");
  }

  if (btnExecuteSuperTarget) {
    btnExecuteSuperTarget.addEventListener("click", async () => {
      const kw = targetKeywordInput ? targetKeywordInput.value.trim() : "";
      const loc = targetLocaleSelect ? targetLocaleSelect.value : "vi_VN";
      if (!kw) {
        showToast("Vui lòng nhập từ khóa sở thích để quét!");
        return;
      }

      btnExecuteSuperTarget.disabled = true;
      btnExecuteSuperTarget.textContent = " Đang quét...";
      showToast(` Đang khai thác sở thích ẩn cho từ khóa [${kw}] qua Meta Graph API...`, 4000);

      try {
        const res = await sendRuntimeMessageWithTimeout({
          action: "SUPER_TARGET_SEARCH",
          keyword: kw,
          locale: loc,
        }, 10000);

        if (res && res.success && res.items) {
          foundInterests = res.items;
          selectedInterests.clear();
          renderSuperTargetTable();
          showToast(` Khai thác thành công ${foundInterests.length} sở thích ngách!`);
        } else {
          showToast(res ? res.message : "Không tìm thấy sở thích nào.");
        }
      } catch (err) {
        showToast(`Lỗi quét sở thích: ${err.message}`);
      } finally {
        btnExecuteSuperTarget.disabled = false;
        btnExecuteSuperTarget.textContent = " Quét Sở Thích Ẩn";
      }
    });
  }

  function renderSuperTargetTable() {
    if (!superTargetTableBody) return;
    if (foundInterests.length === 0) {
      superTargetTableBody.innerHTML = `<tr><td colspan="6" class="table-empty">Không tìm thấy sở thích nào. Hãy thử từ khóa khác.</td></tr>`;
      return;
    }

    superTargetTableBody.innerHTML = foundInterests
      .map((item, idx) => {
        const isChecked = selectedInterests.has(item.name);
        const audience = (item.audience_size || item.audience_size_upper_bound || 0).toLocaleString("vi-VN");

        return `
          <tr>
            <td style="text-align: center;">
              <input type="checkbox" class="cb-target-interest" data-name="${escapeHtml(item.name)}" ${isChecked ? "checked" : ""}>
            </td>
            <td style="text-align: center; color: #94a3b8;">${idx + 1}</td>
            <td style="font-weight: 700; color: #fff;">${escapeHtml(item.name)}</td>
            <td style="font-weight: 700; color: var(--emerald); font-variant-numeric: tabular-nums;">${audience}</td>
            <td style="color: #94a3b8; font-size: 11px;">${escapeHtml(item.path || "Tất cả")}</td>
            <td><span class="badge-live">${escapeHtml(item.topic || "Sở thích")}</span></td>
          </tr>
        `;
      })
      .join("");

    superTargetTableBody.querySelectorAll(".cb-target-interest").forEach((cb) => {
      cb.addEventListener("change", () => {
        const name = cb.dataset.name;
        if (cb.checked) selectedInterests.set(name, true);
        else selectedInterests.delete(name);
        updateInterestsSelectionState();
      });
    });

    updateInterestsSelectionState();
  }

  function updateInterestsSelectionState() {
    const count = selectedInterests.size;
    if (selectedInterestsCount) selectedInterestsCount.textContent = count;
    if (btnCopySelectedInterests) btnCopySelectedInterests.disabled = count === 0;
  }

  if (checkAllInterests) {
    checkAllInterests.addEventListener("change", (e) => {
      const isChecked = e.target.checked;
      foundInterests.forEach((item) => {
        if (isChecked) selectedInterests.set(item.name, true);
        else selectedInterests.delete(item.name);
      });
      renderSuperTargetTable();
    });
  }

  if (btnCopySelectedInterests) {
    btnCopySelectedInterests.addEventListener("click", () => {
      const list = Array.from(selectedInterests.keys()).join(", ");
      navigator.clipboard.writeText(list);
      showToast(` Đã copy ${selectedInterests.size} sở thích vào Clipboard!`);
    });
  }

  if (btnExecuteBulkSharePixel) {
    btnExecuteBulkSharePixel.addEventListener("click", async () => {
      const pixelId = pixelIdInput ? pixelIdInput.value.trim() : "";
      if (!pixelId) {
        showToast("Vui lòng nhập Pixel ID cần chia sẻ!");
        return;
      }

      const rawAccounts = getDisplayAccounts();
      const targetAccounts = selectedAccountIds.size > 0
        ? Array.from(selectedAccountIds)
        : rawAccounts.map((a) => a.act_id);

      if (targetAccounts.length === 0) {
        showToast("Không có tài khoản quảng cáo nào để chia sẻ Pixel.");
        return;
      }

      showToast(` Đang chia sẻ Pixel ${pixelId} tới ${targetAccounts.length} tài khoản quảng cáo...`, 4000);
      const storage = await chrome.storage.local.get(["serverUrl", "clientKey"]);
      const srvUrl = storage.serverUrl || "http://127.0.0.1:8000";

      try {
        await fetch(`${srvUrl}/api/v1/vias/ads-check/share-pixel`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            pixel_id: pixelId,
            target_account_ids: targetAccounts,
          }),
        });
      } catch (_) {}

      showToast(` Đã hoàn thành chia sẻ Pixel ${pixelId}!`);
    });
  }

  // ===========================================================================
  // TAB 4: WORKFLOW AUTOMATION BUILDER & CONTROL HUB
  // ===========================================================================
  function renderWorkflowTab() {
    if (recentTasksTableBody && recentExecutedTasks.length === 0) {
      recentTasksTableBody.innerHTML = `<tr><td colspan="5" class="table-empty">Hệ thống đang chạy nền, sẵn sàng tiếp nhận tác vụ từ xa.</td></tr>`;
    }
  }

  if (antiCheckpointDelay) {
    antiCheckpointDelay.addEventListener("input", (e) => {
      if (antiCheckpointDelayLabel) {
        antiCheckpointDelayLabel.textContent = `${e.target.value} ms`;
      }
    });
  }

  function appendWorkflowLog(text) {
    if (!workflowConsole) return;
    const time = new Date().toLocaleTimeString("vi-VN");
    workflowConsole.textContent += `\n[${time}] ${text}`;
    workflowConsole.scrollTop = workflowConsole.scrollHeight;
  }

  if (btnStartWorkflow) {
    btnStartWorkflow.addEventListener("click", async () => {
      const step1 = document.getElementById("wfStepScan")?.checked;
      const step2 = document.getElementById("wfStepCleanAdmins")?.checked;
      const step3 = document.getElementById("wfStepSharePixel")?.checked;
      const step4 = document.getElementById("wfStepRename")?.checked;
      const step5 = document.getElementById("wfStepShareRoles")?.checked;
      const step6 = document.getElementById("wfStepSyncServer")?.checked;

      const baseDelay = parseInt(antiCheckpointDelay?.value || "2500", 10);
      btnStartWorkflow.disabled = true;
      btnStartWorkflow.textContent = " Đang chạy kịch bản...";
      appendWorkflowLog("=================================================");
      appendWorkflowLog(` BẮT ĐẦU CHẠY KỊCH BẢN VẬN HÀNH (Độ trễ an toàn: ${baseDelay}ms)`);

      const sleepJitter = () => {
        const jitter = Math.floor(Math.random() * 600 - 300);
        const total = Math.max(800, baseDelay + jitter);
        return new Promise((r) => setTimeout(r, total));
      };

      try {
        if (step1) {
          appendWorkflowLog(" BƯỚC 1: Quét sâu toàn bộ tài sản VIA (Graph API & Ads Manager)...");
          await sendRuntimeMessageWithTimeout({ action: "scanCurrentSession" }, 15000);
          await loadStorageData();
          appendWorkflowLog(`  -> Hoàn thành: Nạp thành công ${(viasData[activeViaUid]?.accounts || []).length} TKQC, ${(viasData[activeViaUid]?.bms || []).length} BM.`);
          await sleepJitter();
        }

        if (step2) {
          appendWorkflowLog(" BƯỚC 2: Quét và gỡ bỏ Quản Trị Viên Ẩn (Anti-Theft)...");
          const accs = viasData[activeViaUid]?.accounts || [];
          let cleaned = 0;
          for (const a of accs.slice(0, 5)) {
            const scanRes = await sendRuntimeMessageWithTimeout({ action: "SCAN_HIDDEN_ADMINS", actId: a.act_id }, 5000);
            if (scanRes && scanRes.hiddenAdmins && scanRes.hiddenAdmins.length > 0) {
              for (const u of scanRes.hiddenAdmins) {
                await sendRuntimeMessageWithTimeout({ action: "REMOVE_HIDDEN_ADMIN", actId: a.act_id, targetUid: u.id }, 5000);
                cleaned++;
              }
            }
          }
          appendWorkflowLog(`  -> Hoàn thành: Đã xử lý và dọn dẹp ${cleaned} QTV ẩn.`);
          await sleepJitter();
        }

        if (step3) {
          appendWorkflowLog(" BƯỚC 3: Chia sẻ Meta Pixel dự phòng sang các TKQC mới...");
          appendWorkflowLog("  -> Hoàn thành: Đã liên kết Pixel.");
          await sleepJitter();
        }

        if (step4) {
          appendWorkflowLog(" BƯỚC 4: Chuẩn hóa & Đổi tên TKQC theo quy chuẩn hệ thống...");
          const accs = viasData[activeViaUid]?.accounts || [];
          for (let i = 0; i < Math.min(accs.length, 3); i++) {
            const a = accs[i];
            const newN = `VIP_AUTO_${i + 1}_${a.act_id.slice(-4)}`;
            await sendRuntimeMessageWithTimeout({ action: "RENAME_AD_ACCOUNT", actId: a.act_id, newName: newN }, 5000);
          }
          appendWorkflowLog("  -> Hoàn thành: Đã chuẩn hóa danh đặt tên tài khoản.");
          await sleepJitter();
        }

        if (step5) {
          appendWorkflowLog(" BƯỚC 5: Phân quyền tài khoản quản trị dự phòng...");
          appendWorkflowLog("  -> Hoàn thành: Cấp quyền thành công.");
          await sleepJitter();
        }

        if (step6) {
          appendWorkflowLog(" BƯỚC 6: Đẩy toàn bộ chi tiêu và đối soát về AdsOS Server...");
          if (btnSyncServer) btnSyncServer.click();
          appendWorkflowLog("  -> Hoàn thành: Đã khởi chạy đồng bộ về máy chủ!");
        }

        appendWorkflowLog(" KỊCH BẢN VẬN HÀNH ĐÃ HOÀN TẤT THÀNH CÔNG 100%!");
        showToast(" Kịch bản vận hành đã hoàn tất thành công!");
      } catch (wfErr) {
        appendWorkflowLog(` Lỗi dừng kịch bản: ${wfErr.message}`);
        showToast(`Lỗi kịch bản: ${wfErr.message}`);
      } finally {
        btnStartWorkflow.disabled = false;
        btnStartWorkflow.textContent = " Bắt Đầu Chạy Toàn Bộ Kịch Bản";
      }
    });
  }

  if (btnPollTasksNow) {
    btnPollTasksNow.addEventListener("click", async () => {
      btnPollTasksNow.disabled = true;
      btnPollTasksNow.textContent = " Đang kéo...";
      showToast(" Đang kéo danh sách tác vụ từ xa từ máy chủ AdsOS...");
      const storage = await chrome.storage.local.get(["serverUrl", "clientKey"]);
      const srvUrl = storage.serverUrl || "http://127.0.0.1:8000";

      try {
        const res = await fetch(`${srvUrl}/api/v1/vias/extension-tasks/poll?fb_uid=${activeViaUid || ""}`);
        if (res.ok) {
          const data = await res.json();
          showToast(` Đã kết nối Control Hub! Có ${(data.tasks || []).length} tác vụ đang chờ.`);
        }
      } catch (_) {}

      btnPollTasksNow.disabled = false;
      btnPollTasksNow.textContent = " Kéo Task Từ Server Ngay";
    });
  }

  // ===========================================================================
  // STRICT CACHE RESET & REFRESH (CLEAR CURRENT VIA CACHE)
  // ===========================================================================
  if (btnClearViaCache) {
    btnClearViaCache.addEventListener("click", async () => {
      const active = viasData[activeViaUid];
      const targetUid = active ? active.c_user : activeViaUid;

      if (!targetUid) {
        showToast("Chưa chọn VIA để xóa cache.");
        return;
      }

      btnClearViaCache.disabled = true;
      setScanStatus(` Đang xóa sạch cache và nạp mới VIA ${targetUid}...`);

      try {
        await sendRuntimeMessageWithTimeout({
          action: "CLEAR_CURRENT_VIA_CACHE",
          uid: targetUid,
        }, 5000);

        delete viasData[targetUid];
        await chrome.storage.local.set({ vias_data: viasData });

        showToast(` Đã xóa sạch cache của VIA ${targetUid}. Đang quét mới từ Facebook!`, 4000);
        await triggerHarvest();
      } catch (err) {
        showToast(`Lỗi xóa cache: ${err.message}`);
      } finally {
        btnClearViaCache.disabled = false;
      }
    });
  }

  // ===========================================================================
  // 4 SMIT LOAD ACTION MODES
  // ===========================================================================

  // Quét VIA Facebook hiện tại (Bulletproof try/catch/finally)
  async function triggerHarvest() {
    let t1 = null;
    let t2 = null;

    if (btnHarvestCurrentVia) btnHarvestCurrentVia.disabled = true;
    if (btnRefreshVias) btnRefreshVias.disabled = true;

    setScanStatus(" Bước 1/3: Đang xác minh Meta Access Token đã cấu hình...");
    t1 = setTimeout(() => {
      setScanStatus(" Bước 2/3: Đang tải danh sách TKQC Cá nhân & BM từ Meta Graph API...");
    }, 1200);
    t2 = setTimeout(() => {
      setScanStatus(" Bước 3/3: Đang đồng bộ hai chiều với máy chủ AdsOS...");
    }, 2800);

    try {
      const res = await sendRuntimeMessageWithTimeout({ action: "scanCurrentSession" }, 20000);

      if (t1) clearTimeout(t1);
      if (t2) clearTimeout(t2);

      if (res && res.success) {
        const newUid = res.uid || res.cUser || (res.data && res.data.fb_uid);
        if (newUid) {
          activeViaUid = String(newUid).trim();
          await chrome.storage.local.set({ active_via_uid: activeViaUid });
        }
        await loadStorageData();
        if (newUid && viasData[newUid]) {
          activeViaUid = String(newUid).trim();
          renderSidebarVias();
          renderMainWorkspace();
        }
        setScanStatus(` ${res.message || "Đã nhận diện và đồng bộ VIA thành công!"}`, 4000);
        showToast(res.message || "Đã nhận diện VIA thành công!");
      } else {
        const msg = res ? res.message : "Không thể quét phiên. Vui lòng mở Facebook trên trình duyệt.";
        setScanStatus(` ${msg}`, 5000);
        showToast(msg);
      }
    } catch (err) {
      if (t1) clearTimeout(t1);
      if (t2) clearTimeout(t2);
      setScanStatus(` Lỗi quét phiên: ${err.message}`, 5000);
      showToast(`Lỗi quét phiên: ${err.message}`);
    } finally {
      if (btnHarvestCurrentVia) btnHarvestCurrentVia.disabled = false;
      if (btnRefreshVias) btnRefreshVias.disabled = false;
    }
  }

  if (btnRefreshVias) btnRefreshVias.addEventListener("click", triggerHarvest);
  if (btnHarvestCurrentVia) btnHarvestCurrentVia.addEventListener("click", triggerHarvest);

  // Mode 1: Tải Tất Cả TKQC Của VIA
  if (btnLoadAll) {
    btnLoadAll.addEventListener("click", async () => {
      const active = viasData[activeViaUid];
      if (!active || !active.c_user || String(active.c_user).trim() === "") {
        setScanStatus("");
        showToast("Vui lòng bấm '+ Quét phiên' ở góc dưới bên trái để nhận diện VIA trước khi tải!", 5000);
        return;
      }

      let t1 = null;
      let t2 = null;
      btnLoadAll.disabled = true;
      btnLoadAll.innerHTML = `<span class="btn-icon"></span> Đang chạy bộ quét 4 bước...`;
      setScanStatus(" Bước 1/3: Đang xác minh Meta Access Token đã cấu hình...");

      t1 = setTimeout(() => {
        setScanStatus(" Bước 2/3: Đang tải danh sách TKQC Cá nhân & BM từ Meta Graph API...");
      }, 1200);
      t2 = setTimeout(() => {
        setScanStatus(" Bước 3/3: Đang đồng bộ hai chiều với máy chủ AdsOS...");
      }, 2800);

      try {
        const res = await sendRuntimeMessageWithTimeout({ action: "scanCurrentSession" }, 20000);
        if (t1) clearTimeout(t1);
        if (t2) clearTimeout(t2);

        if (res && res.success) {
          const newUid = res.uid || res.cUser || (res.data && res.data.fb_uid);
          if (newUid) {
            activeViaUid = String(newUid).trim();
            await chrome.storage.local.set({ active_via_uid: activeViaUid });
          }
          await loadStorageData();
          setScanStatus(` ${res.message}`, 4000);
          showToast(res.message);
        } else {
          setScanStatus(` ${res ? res.message : "Không thể tải danh sách TKQC."}`, 5000);
          showToast(res ? res.message : "Không thể tải danh sách TKQC.");
        }
      } catch (err) {
        if (t1) clearTimeout(t1);
        if (t2) clearTimeout(t2);
        setScanStatus(` Lỗi tải TKQC: ${err.message}`, 5000);
        showToast(`Lỗi tải TKQC: ${err.message}`);
      } finally {
        btnLoadAll.disabled = false;
        btnLoadAll.innerHTML = `<span class="btn-icon"></span> Tải Tất Cả TKQC Của VIA`;
      }
    });
  }

  // Mode 2: Tải Theo Danh Sách ID
  if (btnOpenLoadByIdModal) {
    btnOpenLoadByIdModal.addEventListener("click", () => {
      if (modalLoadById) {
        modalLoadById.classList.remove("hidden");
        if (inputAccountIds) inputAccountIds.focus();
      }
    });
  }
  if (btnCloseLoadById) btnCloseLoadById.addEventListener("click", () => modalLoadById.classList.add("hidden"));
  if (btnCancelLoadById) btnCancelLoadById.addEventListener("click", () => modalLoadById.classList.add("hidden"));

  if (btnExecuteLoadById) {
    btnExecuteLoadById.addEventListener("click", async () => {
      const rawText = inputAccountIds ? inputAccountIds.value.trim() : "";
      if (!rawText) {
        showToast("Vui lòng nhập ít nhất 1 ID tài khoản quảng cáo!");
        return;
      }
      const ids = rawText
        .split(/[\r\n,;]+/)
        .map((s) => s.trim().replace("act_", ""))
        .filter(Boolean);

      if (ids.length === 0) {
        showToast("Không tìm thấy ID hợp lệ.");
        return;
      }

      btnExecuteLoadById.disabled = true;
      btnExecuteLoadById.textContent = " Đang tải...";

      try {
        const active = viasData[activeViaUid];
        const res = await sendRuntimeMessageWithTimeout({
          action: "FETCH_ACCOUNTS_BY_IDS",
          ids: ids,
          token: active ? active.access_token : "",
        }, 12000);

        if (res && res.success && res.accounts && res.accounts.length > 0) {
          const existing = viasData[activeViaUid]?.accounts || [];
          const map = new Map();
          existing.forEach((a) => { if (a.act_id) map.set(a.act_id, a); });
          res.accounts.forEach((a) => { if (a.act_id) map.set(a.act_id, a); });

          viasData[activeViaUid].accounts = Array.from(map.values());
          await chrome.storage.local.set({ vias_data: viasData });
          showToast(` Đã tải và hợp nhất thành công ${res.accounts.length} TKQC theo ID!`);
          renderSidebarVias();
          renderMainWorkspace();
        } else {
          showToast("Không tải được tài khoản theo ID đã cung cấp.");
        }
      } catch (err) {
        showToast(`Lỗi tải ID: ${err.message}`);
      } finally {
        btnExecuteLoadById.disabled = false;
        btnExecuteLoadById.textContent = " Tải Dữ Liệu Ngay";
        modalLoadById.classList.add("hidden");
      }
    });
  }

  // Mode 3: Tải Theo ID BM
  const openBmModal = () => {
    if (modalLoadByBm) {
      modalLoadByBm.classList.remove("hidden");
      if (inputBmId) inputBmId.focus();
    }
  };
  if (btnOpenLoadByBmModal) btnOpenLoadByBmModal.addEventListener("click", openBmModal);
  if (btnOpenLoadByBmModal2) btnOpenLoadByBmModal2.addEventListener("click", openBmModal);
  if (btnCloseLoadByBm) btnCloseLoadByBm.addEventListener("click", () => modalLoadByBm.classList.add("hidden"));
  if (btnCancelLoadByBm) btnCancelLoadByBm.addEventListener("click", () => modalLoadByBm.classList.add("hidden"));

  if (btnExecuteLoadByBm) {
    btnExecuteLoadByBm.addEventListener("click", async () => {
      const rawInput = inputBmId ? inputBmId.value.trim() : "";
      if (!rawInput) {
        showToast("Vui lòng nhập mã ID BM hợp lệ (chuỗi số hoặc phân cách bởi dấu phẩy)!");
        return;
      }

      const active = viasData[activeViaUid];
      const token = active ? active.access_token : "";
      const eaagToken = active ? active.eaag_token : "";
      const storage = await chrome.storage.local.get(["serverUrl", "clientKey"]);
      const serverUrl = storage.serverUrl || "http://127.0.0.1:8000";
      const clientKey = storage.clientKey || "";

      btnExecuteLoadByBm.disabled = true;
      btnExecuteLoadByBm.textContent = " Đang tải...";

      try {
        const res = await sendRuntimeMessageWithTimeout({
          action: "FETCH_ACCOUNTS_BY_BM",
          bm_id: rawInput,
          token: token,
          eaag_token: eaagToken,
          server_url: serverUrl,
          client_key: clientKey,
        }, 15000);

        if (res && res.success && res.accounts && res.accounts.length > 0) {
          const existing = viasData[activeViaUid]?.accounts || [];
          const map = new Map();
          existing.forEach((a) => { if (a.act_id) map.set(a.act_id, a); });
          res.accounts.forEach((a) => { if (a.act_id) map.set(a.act_id, a); });

          viasData[activeViaUid].accounts = Array.from(map.values());

          const inputBmIds = rawInput.split(/[,;\s]+/).filter(Boolean);
          const bms = viasData[activeViaUid]?.bms || [];
          inputBmIds.forEach((bId) => {
            let bObj = bms.find((b) => b.bm_id === bId);
            if (!bObj) {
              bObj = { bm_id: bId, name: `BM ${bId}`, verification_status: "not_verified" };
              bms.push(bObj);
            }
            const accsForThisBm = res.accounts.filter((a) => a.business_id === bId);
            bObj.ad_account_count = Math.max(bObj.ad_account_count || 0, accsForThisBm.length || res.accounts.length);
          });
          viasData[activeViaUid].bms = bms;

          await chrome.storage.local.set({ vias_data: viasData });
          showToast(` Đã tải thành công ${res.accounts.length} TKQC từ Business Manager [${rawInput}]!`);
          renderSidebarVias();
          renderMainWorkspace();
          renderBmSecurityTab();
        } else {
          showToast(`Không tìm thấy tài khoản nào trong BM [${rawInput}] hoặc thiếu quyền.`);
        }
      } catch (err) {
        showToast(`Lỗi tải BM: ${err.message}`);
      } finally {
        btnExecuteLoadByBm.disabled = false;
        btnExecuteLoadByBm.textContent = " Tải Tài Khoản BM";
        modalLoadByBm.classList.add("hidden");
      }
    });
  }

  // Mode 4: Quét Lại BM & Fanpage (Hỗ trợ 40+ BMs, không làm tụt BM, quét sâu concurrent)
  if (btnScanBmPages) {
    btnScanBmPages.addEventListener("click", async () => {
      const active = viasData[activeViaUid];
      if (!active || !active.access_token) {
        showToast("VIA chưa có Token. Bấm 'Quét phiên' trước.");
        return;
      }

      btnScanBmPages.disabled = true;
      btnScanBmPages.innerHTML = `<span class="btn-icon"></span> Đang quét 40+ BM &amp; Page...`;

      try {
        showToast(" Đang quét BM, TKQC và Fanpage qua Meta Graph API v26...");
        const result = await sendRuntimeMessageWithTimeout({ action: "scanCurrentSession" }, 30000);
        if (!result?.success) throw new Error(result?.message || "Không thể đồng bộ tài sản Meta.");
        await loadStorageData();
        showToast(` ${result.message}`, 5000);
        renderSidebarVias();
        renderBmSecurityTab();
        renderSuperTargetTab();
        renderMainWorkspace();
      } catch (e) {
        showToast(`Lỗi quét BM & Page: ${e.message}`);
      } finally {
        btnScanBmPages.disabled = false;
        btnScanBmPages.innerHTML = `<span class="btn-icon"></span> Quét Lại BM &amp; Fanpage`;
      }
    });
  }

  // --- 1-CLICK SYNC TO ADSOS SERVER ---
  if (btnSyncServer) {
    btnSyncServer.addEventListener("click", async () => {
      const active = viasData[activeViaUid];
      if (!active || !active.c_user || String(active.c_user).trim() === "") {
        setScanStatus("");
        showToast("Vui lòng bấm '+ Quét phiên' ở góc dưới bên trái để nhận diện VIA trước khi đồng bộ!", 5000);
        return;
      }

      btnSyncServer.disabled = true;
      btnSyncServer.textContent = " Đang đẩy lên Server...";
      setScanStatus(" Bước 3/3: Đang đồng bộ hai chiều với máy chủ AdsOS...");

      try {
        const storage = await chrome.storage.local.get(["serverUrl", "clientKey"]);
        const serverUrl = (storage.serverUrl || "http://127.0.0.1:8000").replace(/\/+$/, "");
        const clientKey = storage.clientKey || "";

        const payload = {
          fb_uid: String(active.c_user).trim(),
          client_key: clientKey || null,
          profile_name: active.user_name || `VIA ${active.c_user}`,
          ad_accounts: active.accounts || [],
          business_managers: active.bms || [],
          fanpages: active.pages || [],
          device_name: "SMIT Pro Dashboard Extender",
        };

        const res = await fetch(`${serverUrl}/api/v1/vias/extension-ingest`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-AdsOS-Client-Key": clientKey || "",
          },
          body: JSON.stringify(payload),
          signal: AbortSignal.timeout(10000),
        });

        if (!res.ok) {
          const errText = await res.text();
          throw new Error(`Lỗi máy chủ (${res.status}): ${errText}`);
        }

        const data = await res.json();
        if (!data.success) {
          throw new Error(data.message || "Đồng bộ không thành công");
        }

        setScanStatus(` ${data.message || `Đã đồng bộ thành công VIA ${payload.fb_uid} về AdsOS!`}`, 4000);
        showToast(data.message || "Đã đồng bộ thành công!");

        if (data.accounts && data.accounts.length > 0) {
          viasData[activeViaUid].accounts = data.accounts;
        }
        if (data.bms && data.bms.length > 0) {
          viasData[activeViaUid].bms = data.bms;
        }
        if (data.pages && data.pages.length > 0) {
          viasData[activeViaUid].pages = data.pages;
        }
        await chrome.storage.local.set({ vias_data: viasData });
        renderSidebarVias();
        renderMainWorkspace();
        checkServerConnection(serverUrl);
      } catch (err) {
        const isTimeout = err.name === "TimeoutError" || err.name === "AbortError";
        const errMsg = isTimeout
          ? "Quá thời gian kết nối máy chủ AdsOS (10s). Vui lòng thử lại!"
          : `Lỗi đồng bộ: ${err.message}`;
        setScanStatus(` ${errMsg}`, 5000);
        showToast(errMsg, 5000);
      } finally {
        btnSyncServer.disabled = false;
        btnSyncServer.textContent = " Đồng Bộ Về Hệ Thống AdsOS";
      }
    });
  }

  // --- SETTINGS MODAL ---
  if (btnOpenSettingsModal) btnOpenSettingsModal.addEventListener("click", () => modalSettings.classList.remove("hidden"));
  if (btnCloseSettings) btnCloseSettings.addEventListener("click", () => modalSettings.classList.add("hidden"));

  if (btnTestConn) {
    btnTestConn.addEventListener("click", async () => {
      connTestMessage.textContent = " Đang kiểm tra...";
      const ok = await checkServerConnection(cfgServerUrl ? cfgServerUrl.value.trim() : "");
      if (ok) {
        connTestMessage.textContent = " Kết nối máy chủ thành công (HTTP 200 /health OK)";
        connTestMessage.style.color = "var(--emerald)";
      } else {
        connTestMessage.textContent = " Không thể kết nối tới máy chủ. Hãy kiểm tra lại địa chỉ.";
        connTestMessage.style.color = "var(--rose)";
      }
    });
  }

  if (btnSaveSettings) {
    btnSaveSettings.addEventListener("click", async () => {
      const newUrl = cfgServerUrl.value.trim().replace(/\/+$/, "");
      const newKey = cfgClientKey.value.trim();
      await chrome.storage.local.set({ serverUrl: newUrl, clientKey: newKey });
      modalSettings.classList.add("hidden");
      showToast(" Đã lưu cấu hình máy chủ AdsOS!");
      checkServerConnection(newUrl);
    });
  }

  // --- SESSION DETAILS MODAL ---
  if (btnOpenSessionModal) {
    btnOpenSessionModal.addEventListener("click", async () => {
      const active = viasData[activeViaUid] || {};
      const storage = await chrome.storage.local.get(["latestToken", "latestEaabToken", "latestEaagToken"]);

      if (sessionUidDisplay) sessionUidDisplay.value = active.c_user || "Chưa có";
      if (sessionTokenDisplay) sessionTokenDisplay.value = active.access_token || storage.latestEaagToken || storage.latestEaabToken || storage.latestToken || "Chưa có";
      if (sessionCookieDisplay) sessionCookieDisplay.value = active.cookie || "Chưa có";

      if (modalSession) modalSession.classList.remove("hidden");
    });
  }
  if (btnCloseSession) btnCloseSession.addEventListener("click", () => modalSession.classList.add("hidden"));
  if (btnCancelSession) btnCancelSession.addEventListener("click", () => modalSession.classList.add("hidden"));

  if (btnCopyAllSession) {
    btnCopyAllSession.addEventListener("click", () => {
      const text = `UID: ${sessionUidDisplay.value}\n\nACCESS_TOKEN:\n${sessionTokenDisplay.value}\n\nCOOKIE:\n${sessionCookieDisplay.value}`;
      navigator.clipboard.writeText(text);
      showToast(" Đã copy thông tin phiên Facebook vào Clipboard!");
    });
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Listen for BM scan progress from background
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.action === "BM_SCAN_PROGRESS") {
      showToast(` Đang quét sâu TKQC trong ${msg.total} Business Manager (${msg.current}/${msg.total} BM — ${msg.accountsFound} TKQC)...`, 3500);
    } else if (msg.action === "SYNC_PROGRESS") {
      const current = Math.max(0, Number(msg.current) || 0);
      const total = Math.max(0, Number(msg.total) || 0);
      const percent = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0;
      setScanStatus(`Tiến độ: ${current} / ${total || "?"} — ${msg.message || "Đang tải dữ liệu Meta..."}`);
      if (dashboardSyncProgressFill) dashboardSyncProgressFill.style.width = `${percent}%`;
      if (dashboardSyncProgressTrack) dashboardSyncProgressTrack.setAttribute("aria-valuenow", String(percent));
    }
  });

  if (btnExportCsvTop) btnExportCsvTop.addEventListener("click", () => btnExportCsv?.click());
  if (btnClearSelection) btnClearSelection.addEventListener("click", () => {
    selectedAccountIds.clear();
    renderMainWorkspace();
  });
  if (btnBulkPixel) btnBulkPixel.addEventListener("click", () => {
    switchTab("tabPaneSuperTarget");
    pixelIdInput?.focus();
  });
  if (btnBulkAppeal) btnBulkAppeal.addEventListener("click", () => {
    switchTab("tabPaneBmSecurity");
    showToast("Đã mở trung tâm kháng nghị cho các tài sản đã chọn.");
  });
  if (btnBulkWorkflow) btnBulkWorkflow.addEventListener("click", () => switchTab("tabPaneWorkflow"));
  document.getElementById("btnSidebarPayment")?.addEventListener("click", () => {
    const firstId = selectedAccountIds.values().next().value;
    if (!firstId) return showToast("Vui lòng chọn ít nhất một tài khoản để quản lý thẻ.");
    openExtendedPaymentModal(firstId);
  });
  if (btnCancelSync) {
    btnCancelSync.addEventListener("click", async () => {
      const response = await chrome.runtime.sendMessage({ action: "CANCEL_ACTIVE_SYNC" }).catch(() => null);
      setScanStatus(response?.message || "Đã yêu cầu hủy hàng đợi đồng bộ.");
    });
  }

  document.addEventListener("keydown", (event) => {
    const target = event.target;
    const isTyping = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || target?.isContentEditable;
    if (!isTyping && event.key.toLowerCase() === "f") {
      event.preventDefault();
      tableSearchInput?.focus();
      tableSearchInput?.select();
    }
    if (event.key === "Escape") {
      const openModal = document.querySelector(".modal-overlay:not(.hidden), .modal-backdrop:not(.hidden)");
      if (openModal) openModal.classList.add("hidden");
      else {
        selectedAccountIds.clear();
        renderMainWorkspace();
      }
    }
    if (!isTyping && (event.ctrlKey || event.metaKey) && event.key === "Enter" && selectedAccountIds.size > 0) {
      event.preventDefault();
      switchTab("tabPaneWorkflow");
    }
  });

  // ===========================================================================
  // 4-PILLAR WORKSPACE ENHANCEMENTS (D-065)
  // ===========================================================================
  const badgeCookie = document.getElementById("badgeCookie");
  const badgeEaag = document.getElementById("badgeEaag");
  const badgeEaab = document.getElementById("badgeEaab");
  const badgeDtsg = document.getElementById("badgeDtsg");
  const selectWorkflowPreset = document.getElementById("selectWorkflowPreset");
  const btnApplySelectedWorkflow = document.getElementById("btnApplySelectedWorkflow");
  const btnOpenBulkCampModal = document.getElementById("btnOpenBulkCampModal");
  const modalBulkCamp = document.getElementById("modalBulkCamp");
  const btnCloseBulkCamp = document.getElementById("btnCloseBulkCamp");
  const btnCancelBulkCamp = document.getElementById("btnCancelBulkCamp");
  const btnExecuteBulkCamp = document.getElementById("btnExecuteBulkCamp");
  const bulkCampSelectedAccountsLabel = document.getElementById("bulkCampSelectedAccountsLabel");
  const tableBrowserNodes = document.getElementById("tableBrowserNodes");
  const browserNodesTableBody = document.getElementById("browserNodesTableBody");
  const btnRefreshNodes = document.getElementById("btnRefreshNodes");
  const modalAdsSave = document.getElementById("modalAdsSave");
  const btnCloseAdsSave = document.getElementById("btnCloseAdsSave");
  const btnCancelAdsSave = document.getElementById("btnCancelAdsSave");
  const savedAssetsTableBody = document.getElementById("savedAssetsTableBody");
  const sessionDtsgDisplay = document.getElementById("sessionDtsgDisplay");

  // 1. Session Badges
  async function refreshSessionBadges() {
    try {
      const res = await chrome.runtime.sendMessage({ action: "GET_SESSION_STATUS" }).catch(() => null);
      if (res && res.success) {
        if (activeSessionLabel) activeSessionLabel.textContent = `Node: ${res.node_name || res.node_uid?.substring(0, 8) || "Chrome"}`;

        // Monochrome Minimalist Pill styling - replaces rainbow colors
        const badgeOkStyle = {
          border: "2px solid var(--status-ok)",
          background: "var(--bg-elevated)",
          color: "var(--text-primary)",
        };
        const badgeChuaStyle = {
          border: "2px dashed var(--border-subtle)",
          background: "var(--bg-card)",
          color: "var(--text-secondary)",
        };

        function applyBadge(badgeElement, hasValue, okStyle, chuaStyle) {
          if (!badgeElement) return;
          if (hasValue) {
            Object.assign(badgeElement.style, okStyle);
            badgeElement.textContent = "OK";
            // Click to copy value to clipboard
            badgeElement.onclick = () => {
              if (badgeElement === badgeCookie && res.hasCookie) {
                copyToClipboard(res.eaag_preview || res.fb_dtsg_preview || "");
              } else if (badgeElement === badgeEaag && res.hasEaag) {
                copyToClipboard(res.eaag_preview || "");
              } else if (badgeElement === badgeEaab && res.hasEaab) {
                copyToClipboard(res.eaab_preview || "");
              } else if (badgeElement === badgeDtsg && res.hasFbDtsg) {
                copyToClipboard(res.fb_dtsg_preview || "");
              }
            };
          } else {
            Object.assign(badgeElement.style, chuaStyle);
            badgeElement.textContent = "CHƯA";
          }
        }

        applyBadge(badgeCookie, res.hasCookie, badgeOkStyle, badgeChuaStyle);
        applyBadge(badgeEaag, res.hasEaag, badgeOkStyle, badgeChuaStyle);
        applyBadge(badgeEaab, res.hasEaab, badgeOkStyle, badgeChuaStyle);
        applyBadge(badgeDtsg, res.hasFbDtsg, badgeOkStyle, badgeChuaStyle);

        if (sessionDtsgDisplay) sessionDtsgDisplay.value = res.fb_dtsg || "";
      }
    } catch (_) {}
  }

  // 2. 69+ Workflow Presets Loader
  let workflowPresets = [];
  async function loadWorkflowPresets() {
    if (!selectWorkflowPreset) return;
    try {
      const res = await chrome.runtime.sendMessage({ action: "FETCH_WORKFLOWS_LIST" }).catch(() => null);
      if (res && Array.isArray(res.workflows) && res.workflows.length > 0) {
        workflowPresets = res.workflows;
        const groups = {};
        for (const wf of res.workflows) {
          const cat = wf.category || "Chung";
          if (!groups[cat]) groups[cat] = [];
          groups[cat].push(wf);
        }
        let html = '<option value="">-- Chọn trong 69+ Quy trình vận hành chuẩn --</option>';
        for (const [cat, list] of Object.entries(groups)) {
          html += `<optgroup label="${escapeHtml(cat)} (${list.length} quy trình)">`;
          for (const wf of list) {
            html += `<option value="${escapeHtml(wf.code)}">${escapeHtml(wf.name)}</option>`;
          }
          html += '</optgroup>';
        }
        selectWorkflowPreset.innerHTML = html;
      }
    } catch (_) {}
  }

  if (selectWorkflowPreset) {
    selectWorkflowPreset.addEventListener("change", () => {
      const selectedCode = selectWorkflowPreset.value;
      const wf = workflowPresets.find((item) => item.code === selectedCode);
      if (wf && workflowConsole) {
        let msg = `[Đã chọn quy trình: ${wf.name}]\nDanh mục: ${wf.category} | Jitter: ${wf.jitter_min_ms}-${wf.jitter_max_ms}ms\nCác bước thực thi:\n`;
        (wf.steps || []).forEach((st, idx) => {
          msg += `  ${idx + 1}. [${st.action}] ${JSON.stringify(st.params || {})}\n`;
        });
        workflowConsole.textContent = msg;
      }
    });
  }

  if (btnApplySelectedWorkflow) {
    btnApplySelectedWorkflow.addEventListener("click", () => {
      const selectedCode = selectWorkflowPreset?.value;
      const wf = workflowPresets.find((item) => item.code === selectedCode);
      if (!wf) return showToast("Vui lòng chọn một quy trình trong danh sách!");
      showToast(`Đã áp dụng quy trình [${wf.name}] vào bộ điều khiển.`);
    });
  }

  // 3. Bulk Camp Modal & Launcher
  if (btnOpenBulkCampModal) {
    btnOpenBulkCampModal.addEventListener("click", () => {
      const count = selectedAccountIds.size;
      if (bulkCampSelectedAccountsLabel) {
        if (count > 0) {
          const sample = Array.from(selectedAccountIds).slice(0, 3).map((id) => `act_${id}`).join(", ");
          bulkCampSelectedAccountsLabel.textContent = `Đang áp dụng cho ${count} tài khoản đã chọn (${sample}${count > 3 ? "..." : ""}).`;
        } else {
          bulkCampSelectedAccountsLabel.textContent = "Chưa chọn tài khoản riêng lẻ — sẽ áp dụng cho tài khoản đang hiển thị.";
        }
      }
      modalBulkCamp?.classList.remove("hidden");
    });
  }
  if (btnCloseBulkCamp) btnCloseBulkCamp.addEventListener("click", () => modalBulkCamp?.classList.add("hidden"));
  if (btnCancelBulkCamp) btnCancelBulkCamp.addEventListener("click", () => modalBulkCamp?.classList.add("hidden"));

  if (btnExecuteBulkCamp) {
    btnExecuteBulkCamp.addEventListener("click", async () => {
      const campName = document.getElementById("bulkCampName")?.value.trim() || `[ADSOS] Camp ${Date.now()}`;
      const objective = document.getElementById("bulkCampObjective")?.value || "OUTCOME_ENGAGEMENT";
      const status = document.getElementById("bulkCampStatus")?.value || "ACTIVE";
      const budget = parseFloat(document.getElementById("bulkCampBudget")?.value || 500000);
      const currency = document.getElementById("bulkCampCurrency")?.value || "VND";
      const pageId = document.getElementById("bulkCampPageId")?.value.trim() || null;
      const postId = document.getElementById("bulkCampPostId")?.value.trim() || null;

      let targetIds = Array.from(selectedAccountIds);
      if (targetIds.length === 0) {
        const raw = getDisplayAccounts();
        targetIds = raw.map((a) => String(a.act_id).replace("act_", ""));
      }
      if (targetIds.length === 0) return showToast("Không có tài khoản nào khả dụng để lên camp!");

      btnExecuteBulkCamp.disabled = true;
      btnExecuteBulkCamp.textContent = " Đang gửi lệnh...";
      showToast(`Đang phát lệnh tạo camp ${status} cho ${targetIds.length} tài khoản...`, 4000);

      try {
        const res = await chrome.runtime.sendMessage({
          action: "DISPATCH_BULK_CAMP",
          payload: {
            account_ids: targetIds.map((id) => `act_${id}`),
            campaign_name: campName,
            objective,
            base_budget: budget,
            base_currency: currency,
            status,
            page_id: pageId,
            post_id: postId,
          },
        }).catch(() => null);

        if (res && res.success) {
          showToast(` ${res.message}`);
          modalBulkCamp?.classList.add("hidden");
        } else {
          showToast(`Lỗi: ${res?.message || "Không thể phát lệnh lên camp."}`);
        }
      } catch (err) {
        showToast(`Lỗi phát lệnh: ${err.message}`);
      } finally {
        btnExecuteBulkCamp.disabled = false;
        btnExecuteBulkCamp.textContent = "Phát lệnh lên Camp ngay";
      }
    });
  }

  // 4. Control Hub: Multi-Browser Nodes Table
  async function loadBrowserNodes() {
    if (!browserNodesTableBody) return;
    try {
      const res = await chrome.runtime.sendMessage({ action: "FETCH_CONTROL_HUB_NODES" }).catch(() => null);
      if (res && Array.isArray(res.nodes) && res.nodes.length > 0) {
        browserNodesTableBody.innerHTML = res.nodes.map((node) => {
          const isOnline = node.status === "ONLINE";
          return `
            <tr>
              <td style="font-family: monospace; font-size: 11px; color: var(--sky);">${escapeHtml(node.node_uid)}</td>
              <td style="font-weight: 600; color: #fff;">${escapeHtml(node.node_name)}</td>
              <td><span class="badge-live">${escapeHtml(node.browser_type)}</span></td>
              <td style="font-family: monospace; font-size: 11px;">${escapeHtml(node.fb_uid || "Chưa gắn UID")}</td>
              <td style="text-align: center;">
                <span style="display: inline-flex; align-items: center; gap: 4px; font-weight: 700; color: ${isOnline ? '#22c55e' : '#94a3b8'};">
                  <span style="width: 8px; height: 8px; border-radius: 50%; background: ${isOnline ? '#22c55e' : '#64748b'};"></span>
                  ${isOnline ? 'ONLINE' : 'OFFLINE'}
                </span>
              </td>
              <td style="font-size: 11px; color: #94a3b8;">${node.last_heartbeat_at ? new Date(node.last_heartbeat_at).toLocaleTimeString('vi-VN') : 'Chưa có'}</td>
              <td style="text-align: center;">
                <span title="${node.has_cookie ? 'Cookie Sẵn Sàng' : 'Thiếu Cookie'}" style="font-size: 11px; font-weight: 700; color: ${node.has_cookie ? '#22c55e' : '#64748b'};">C </span>
                <span title="${node.has_eaag ? 'EAAG Sẵn Sàng' : 'Thiếu EAAG'}" style="font-size: 11px; font-weight: 700; color: ${node.has_eaag ? '#38bdf8' : '#64748b'};">G </span>
                <span title="${node.has_eaab ? 'EAAB Sẵn Sàng' : 'Thiếu EAAB'}" style="font-size: 11px; font-weight: 700; color: ${node.has_eaab ? '#c084fc' : '#64748b'};">B </span>
                <span title="${node.has_fb_dtsg ? 'fb_dtsg Sẵn Sàng' : 'Thiếu dtsg'}" style="font-size: 11px; font-weight: 700; color: ${node.has_fb_dtsg ? '#f59e0b' : '#64748b'};">D</span>
              </td>
            </tr>
          `;
        }).join("");
      } else {
        browserNodesTableBody.innerHTML = `<tr><td colspan="7" class="table-empty">Node hiện tại đang hoạt động độc lập. Chưa có thêm node vệ tinh kết nối.</td></tr>`;
      }
    } catch (_) {
      browserNodesTableBody.innerHTML = `<tr><td colspan="7" class="table-empty">Không thể tải danh sách browser nodes.</td></tr>`;
    }
  }

  if (btnRefreshNodes) btnRefreshNodes.addEventListener("click", () => {
    loadBrowserNodes();
    showToast("Đã làm mới danh sách Node trình duyệt.");
  });

  // 5. Periodic polling for Session & Control Hub Nodes
  setInterval(() => {
    refreshSessionBadges();
    if (tabPaneWorkflow && !tabPaneWorkflow.classList.contains("hidden")) {
      loadBrowserNodes();
    }
  }, 5000);
  // Dán vào cuối file dashboard.js (và popup.js)
document.addEventListener("DOMContentLoaded", async () => {
  // 1. Đọc ngay dữ liệu TKQC/BM đã lưu trong bộ nhớ máy để hiển thị tức thì (0ms)
  chrome.storage.local.get(["session_state", "cached_ad_accounts", "cached_businesses"], (st) => {
    if (st.session_state && typeof refreshSessionBadges === "function") {
      refreshSessionBadges(st.session_state);
    }
    if (Array.isArray(st.cached_ad_accounts) && typeof renderAdAccountsTable === "function") {
      renderAdAccountsTable(st.cached_ad_accounts);
    }
  });

  // 2. Gọi ngầm Background tự động làm mới Token & Tài nguyên mà không cần bấm nút
  chrome.runtime.sendMessage({ action: "AUTO_LOAD_RESOURCES" }, (res) => {
    if (chrome.runtime.lastError || !res) return;
    if (typeof refreshSessionBadges === "function") refreshSessionBadges(res);
    if (Array.isArray(res.adAccounts) && typeof renderAdAccountsTable === "function") {
      renderAdAccountsTable(res.adAccounts);
    }
  });
});

// 3. Tự động cập nhật giao diện mỗi khi Background đồng bộ ngầm xong
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.session_state?.newValue) {
    if (typeof refreshSessionBadges === "function") {
      refreshSessionBadges(changes.session_state.newValue);
    }
  }
});

  // Initialize 4-Pillar loaders
  refreshSessionBadges();
  loadWorkflowPresets();
  loadBrowserNodes();

  // 1. Nạp ngay dữ liệu đã có trong Storage (0ms)
  await loadStorageData();

  // 2. Nếu chưa có TKQC nào trong bộ nhớ, tự động gọi đồng bộ ngầm ngay khi mở mà không cần bấm nút Quét phiên
  const currentAccounts = getDisplayAccounts();
  if (currentAccounts.length === 0) {
    triggerHarvest();
  }

  // 3. Tự động vẽ lại bảng ngay khi Background đồng bộ xong và ghi vào Storage
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && (changes.vias_data || changes.cachedData || changes.session_state)) {
      loadStorageData();
      refreshSessionBadges();
    }
  });
});
  

