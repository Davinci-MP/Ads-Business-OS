/**
 * ADSOS CHECK PRO — Popup Controller
 */

document.addEventListener("DOMContentLoaded", async () => {
  // Elements
  const headerUid = document.getElementById("headerUid");
  const connectionBadge = document.getElementById("connectionBadge");
  const statusLabel = document.getElementById("statusLabel");
  const btnToggleSettings = document.getElementById("btnToggleSettings");
  const configDrawer = document.getElementById("configDrawer");
  const serverUrlInput = document.getElementById("serverUrlInput");
  const clientKeyInput = document.getElementById("clientKeyInput");
  const btnSaveConfig = document.getElementById("btnSaveConfig");
  const btnCancelConfig = document.getElementById("btnCancelConfig");
  const toastNotice = document.getElementById("toastNotice");
  const btnOpenDashboard = document.getElementById("btnOpenDashboard");
  if (btnOpenDashboard) {
    btnOpenDashboard.addEventListener("click", () => {
      chrome.tabs.create({ url: chrome.runtime.getURL("dashboard.html") });
    });
  }
  const btnOpenAdsManager = document.getElementById("btnOpenAdsManager");
  const scanStatusBanner = document.getElementById("scanStatusBanner");

  if (btnOpenAdsManager) {
    btnOpenAdsManager.addEventListener("click", () => {
      chrome.tabs.create({ url: "https://adsmanager.facebook.com/adsmanager/manage/accounts" });
    });
  }

  function setScanStatus(text, hideAfterMs = 0) {
    if (!scanStatusBanner) return;
    if (!text) {
      scanStatusBanner.classList.add("hidden");
      return;
    }
    scanStatusBanner.textContent = text;
    scanStatusBanner.classList.remove("hidden");
    if (hideAfterMs > 0) {
      setTimeout(() => scanStatusBanner.classList.add("hidden"), hideAfterMs);
    }
  }

  const tabButtons = document.querySelectorAll(".tab-btn");
  const tabPanes = document.querySelectorAll(".tab-pane");

  const kpiTotalAccounts = document.getElementById("kpiTotalAccounts");
  const kpiLiveDie = document.getElementById("kpiLiveDie");
  const kpiTotalSpend = document.getElementById("kpiTotalSpend");
  const kpiTotalBalance = document.getElementById("kpiTotalBalance");

  const countAccounts = document.getElementById("countAccounts");
  const countBms = document.getElementById("countBms");
  const countTasks = document.getElementById("countTasks");

  const accountsTableBody = document.getElementById("accountsTableBody");
  const bmsTableBody = document.getElementById("bmsTableBody");
  const pagesTableBody = document.getElementById("pagesTableBody");
  const filterAccountsInput = document.getElementById("filterAccountsInput");
  const btnQuickRefreshAccounts = document.getElementById("btnQuickRefreshAccounts");

  const shareSelectAccount = document.getElementById("shareSelectAccount");
  const setcampAccountSelect = document.getElementById("setcampAccountSelect");
  const setcampTemplateSelect = document.getElementById("setcampTemplateSelect");

  const btnFullSync = document.getElementById("btnFullSync");
  const btnCopyCookieToken = document.getElementById("btnCopyCookieToken");
  const btnExecuteShare = document.getElementById("btnExecuteShare");
  const btnExecuteSetCamp = document.getElementById("btnExecuteSetCamp");
  const btnRefreshTasks = document.getElementById("btnRefreshTasks");
  const taskListContainer = document.getElementById("taskListContainer");

  const popupNodeName = document.getElementById("popupNodeName");
  const popupBadgeCookie = document.getElementById("popupBadgeCookie");
  const popupBadgeEaag = document.getElementById("popupBadgeEaag");
  const popupBadgeEaab = document.getElementById("popupBadgeEaab");
  const popupBadgeDtsg = document.getElementById("popupBadgeDtsg");

  async function updatePopupSessionBadges() {
    try {
      const res = await chrome.runtime.sendMessage({ action: "GET_SESSION_STATUS" }).catch(() => null);
      if (res && res.success) {
        if (popupNodeName) popupNodeName.textContent = `Node: ${res.node_name || res.node_uid?.substring(0, 8) || "Chrome"}`;

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
              if (badgeElement === popupBadgeCookie && res.hasCookie) {
                copyToClipboard(res.eaag_preview || res.fb_dtsg_preview || "");
              } else if (badgeElement === popupBadgeEaag && res.hasEaag) {
                copyToClipboard(res.eaag_preview || "");
              } else if (badgeElement === popupBadgeEaab && res.hasEaab) {
                copyToClipboard(res.eaab_preview || "");
              } else if (badgeElement === popupBadgeDtsg && res.hasFbDtsg) {
                copyToClipboard(res.fb_dtsg_preview || "");
              }
            };
          } else {
            Object.assign(badgeElement.style, chuaStyle);
            badgeElement.textContent = "CHƯA";
          }
        }

        applyBadge(popupBadgeCookie, res.hasCookie, badgeOkStyle, badgeChuaStyle);
        applyBadge(popupBadgeEaag, res.hasEaag, badgeOkStyle, badgeChuaStyle);
        applyBadge(popupBadgeEaab, res.hasEaab, badgeOkStyle, badgeChuaStyle);
        applyBadge(popupBadgeDtsg, res.hasFbDtsg, badgeOkStyle, badgeChuaStyle);

        if (headerUid && res.uid) {
          headerUid.textContent = res.uid;
        }
      }
    } catch (_) {}
  }
  updatePopupSessionBadges();

  let allAccounts = [];
  let allBms = [];
  let allPages = [];

  // Show Toast
  function showToast(msg, duration = 3000) {
    toastNotice.textContent = msg;
    toastNotice.classList.remove("hidden");
    setTimeout(() => {
      toastNotice.classList.add("hidden");
    }, duration);
  }

  // Load Config
  const storage = await chrome.storage.local.get(["serverUrl", "clientKey", "cachedData"]);
  const serverUrl = storage.serverUrl || "http://127.0.0.1:8000";
  const clientKey = storage.clientKey || "";
  serverUrlInput.value = serverUrl;
  clientKeyInput.value = clientKey;

  // Toggle Config Drawer
  btnToggleSettings.addEventListener("click", () => {
    configDrawer.classList.toggle("hidden");
  });
  btnCancelConfig.addEventListener("click", () => {
    configDrawer.classList.add("hidden");
  });

  // Save Config
  btnSaveConfig.addEventListener("click", async () => {
    const newUrl = serverUrlInput.value.trim().replace(/\/+$/, "");
    const newKey = clientKeyInput.value.trim();
    await chrome.storage.local.set({ serverUrl: newUrl, clientKey: newKey });
    configDrawer.classList.add("hidden");
    showToast(" Đã lưu cấu hình máy chủ & mã khách hàng!");
    checkServerConnection(newUrl);
  });

  // Check Server Connection
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
          signal: AbortSignal.timeout(1800),
        });
        if (pingRes.ok) {
          await chrome.storage.local.set({ serverUrl: cand });
          if (serverUrlInput && serverUrlInput.value !== cand) serverUrlInput.value = cand;
          statusLabel.textContent = `Đã kết nối (${cand})`;
          connectionBadge.querySelector(".status-dot").className = "status-dot online";
          return true;
        }
      } catch (_) {
        try {
          const hRes = await fetch(`${cand}/health`, {
            method: "GET",
            signal: AbortSignal.timeout(1200),
          });
          if (hRes.ok) {
            await chrome.storage.local.set({ serverUrl: cand });
            if (serverUrlInput && serverUrlInput.value !== cand) serverUrlInput.value = cand;
            statusLabel.textContent = `Đã kết nối (${cand})`;
            connectionBadge.querySelector(".status-dot").className = "status-dot online";
            return true;
          }
        } catch (__) {}
      }
    }

    statusLabel.textContent = "Không nối được Server";
    connectionBadge.querySelector(".status-dot").className = "status-dot";
    return false;
  }
  checkServerConnection(serverUrl);

  // Switch Tabs
  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabButtons.forEach((b) => b.classList.remove("active"));
      tabPanes.forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const targetPane = document.getElementById(btn.dataset.tab);
      if (targetPane) targetPane.classList.add("active");
    });
  });

  // Render UI from Data
  function renderAllData(data) {
    if (!data) return;
    if (data.c_user) {
      headerUid.textContent = data.user_name ? `${data.c_user} (${data.user_name})` : data.c_user;
    }

    allAccounts = data.accounts || [];
    allBms = data.bms || [];
    allPages = data.pages || [];

    countAccounts.textContent = allAccounts.length;
    countBms.textContent = allBms.length;

    // Calculate KPIs
    let totalSpend = 0;
    let totalBalance = 0;
    let liveCount = 0;
    let dieCount = 0;

    allAccounts.forEach((acc) => {
      if (acc.account_status === "LIVE") liveCount++;
      else dieCount++;
      totalSpend += parseFloat(acc.amount_spent || 0);
      totalBalance += parseFloat(acc.balance || 0);
    });

    kpiTotalAccounts.textContent = allAccounts.length;
    kpiLiveDie.textContent = `${liveCount} Live · ${dieCount} Die`;
    kpiTotalSpend.textContent = `${totalSpend.toLocaleString("vi-VN")} ₫`;
    kpiTotalBalance.textContent = `${totalBalance.toLocaleString("vi-VN")} ₫`;

    renderAccountsTable(allAccounts);
    renderBmsTable(allBms);
    renderPagesTable(allPages);
    populateSelects(allAccounts);
  }

  function renderAccountsTable(accounts) {
    if (!accounts || accounts.length === 0) {
      accountsTableBody.innerHTML = `<tr><td colspan="6" class="text-center py-4 text-muted">Chưa có dữ liệu TKQC. Bấm " Đồng Bộ Toàn Bộ Về Server" để quét.</td></tr>`;
      return;
    }

    accountsTableBody.innerHTML = accounts
      .map((a) => {
        const isLive = a.account_status === "LIVE";
        const statusBadge = isLive
          ? `<span class="badge badge-live">LIVE</span>`
          : `<span class="badge badge-die">${a.account_status || "DIE"}</span>`;
        const spend = parseFloat(a.amount_spent || 0).toLocaleString("vi-VN");
        const balance = parseFloat(a.balance || 0).toLocaleString("vi-VN");
        const threshold = a.threshold ? parseFloat(a.threshold).toLocaleString("vi-VN") : "---";
        const cardDisplay = a.card_last4 ? ` ${a.card_last4}` : "Chưa gắn";

        return `
          <tr>
            <td>
              <div style="font-weight: 600; color: #fff;">${escapeHtml(a.name)}</div>
              <div style="font-size: 10px; color: #94a3b8; font-family: monospace;">act_${a.act_id}</div>
            </td>
            <td>${statusBadge}</td>
            <td>
              <div>Ngưỡng: ${threshold}</div>
              <div style="font-size: 10px; color: #94a3b8;">Limit: ${a.spend_cap !== "0" ? a.spend_cap : "Không giới hạn"}</div>
            </td>
            <td>
              <div style="color: #38bdf8;">Dư: ${balance}</div>
              <div style="font-size: 10px; color: #818cf8;">Tiêu: ${spend}</div>
            </td>
            <td>
              <div>${a.currency}</div>
              <div style="font-size: 10px; color: #34d399;">${cardDisplay}</div>
            </td>
            <td>
              <button class="btn btn-outline btn-sm copy-btn" data-act="${a.act_id}"> ID</button>
            </td>
          </tr>
        `;
      })
      .join("");

    // Attach copy button events
    document.querySelectorAll(".copy-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const actId = btn.dataset.act;
        navigator.clipboard.writeText(`act_${actId}`);
        showToast(`Đã copy ID: act_${actId}`);
      });
    });
  }

  function renderBmsTable(bms) {
    if (!bms || bms.length === 0) {
      bmsTableBody.innerHTML = `<tr><td colspan="5" class="text-center py-3 text-muted">Không tìm thấy Business Manager nào.</td></tr>`;
      return;
    }
    bmsTableBody.innerHTML = bms
      .map(
        (b) => `
        <tr>
          <td style="font-family: monospace; color: #38bdf8;">${b.bm_id}</td>
          <td style="font-weight: 600;">${escapeHtml(b.name)}</td>
          <td><span class="badge ${b.verification_status === "verified" ? "badge-live" : "badge-warn"}">${b.verification_status || "Chưa xác minh"}</span></td>
          <td>${b.account_count || "---"}</td>
          <td><a href="https://business.facebook.com/settings?business_id=${b.bm_id}" target="_blank" style="color: #818cf8; text-decoration: none;"> Mở BM</a></td>
        </tr>
      `
      )
      .join("");
  }

  function renderPagesTable(pages) {
    if (!pages || pages.length === 0) {
      pagesTableBody.innerHTML = `<tr><td colspan="4" class="text-center py-3 text-muted">Không tìm thấy Fanpage nào.</td></tr>`;
      return;
    }
    pagesTableBody.innerHTML = pages
      .map(
        (p) => `
        <tr>
          <td style="font-family: monospace; color: #38bdf8;">${p.page_id}</td>
          <td style="font-weight: 600;">${escapeHtml(p.name)}</td>
          <td>${(p.fan_count || 0).toLocaleString("vi-VN")} likes</td>
          <td><a href="https://facebook.com/${p.page_id}" target="_blank" style="color: #818cf8; text-decoration: none;"> Mở Page</a></td>
        </tr>
      `
      )
      .join("");
  }

  function populateSelects(accounts) {
    shareSelectAccount.innerHTML = `<option value="">-- Chọn TKQC cần share --</option>` +
      accounts.map((a) => `<option value="${a.act_id}">${escapeHtml(a.name)} (act_${a.act_id})</option>`).join("");

    setcampAccountSelect.innerHTML = `<option value="">-- Chọn TKQC --</option>` +
      accounts.map((a) => `<option value="${a.act_id}">${escapeHtml(a.name)} (act_${a.act_id})</option>`).join("");
  }

  // Load Templates from Server
  async function loadCampaignTemplates() {
    try {
      const cfg = await chrome.storage.local.get(["serverUrl", "clientKey"]);
      const res = await fetch(`${cfg.serverUrl || DEFAULT_SERVER_URL}/api/v1/vias/campaign-templates`, {
        headers: { "X-AdsOS-Client-Key": cfg.clientKey || "" }
      });
      if (res.ok) {
        const templates = await res.json();
        if (templates && templates.length > 0) {
          setcampTemplateSelect.innerHTML = templates
            .map((t) => `<option value="${t.id}" data-budget="${t.daily_budget}" data-obj="${t.objective}">${escapeHtml(t.name)} (${parseInt(t.daily_budget).toLocaleString("vi-VN")} đ - ${t.objective})</option>`)
            .join("");
        }
      }
    } catch (_) {}
  }
  loadCampaignTemplates();

  // Filter accounts
  filterAccountsInput.addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase().trim();
    if (!q) {
      renderAccountsTable(allAccounts);
      return;
    }
    const filtered = allAccounts.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        a.act_id.includes(q) ||
        (a.card_last4 && a.card_last4.includes(q))
    );
    renderAccountsTable(filtered);
  });

  btnQuickRefreshAccounts.addEventListener("click", () => {
    triggerSync();
  });

  // Action: Trigger Full Sync
  async function triggerSync() {
    let t1 = null;
    let t2 = null;
    btnFullSync.disabled = true;
    btnFullSync.textContent = " Đang quét & đồng bộ...";
    setScanStatus(" Bước 1/3: Đang xác minh Meta Access Token đã cấu hình...");

    t1 = setTimeout(() => {
      setScanStatus(" Bước 2/3: Đang tải danh sách TKQC Cá nhân & BM từ Meta Graph API...");
    }, 1200);

    t2 = setTimeout(() => {
      setScanStatus(" Bước 3/3: Đang đồng bộ hai chiều với máy chủ AdsOS...");
    }, 2800);

    chrome.runtime.sendMessage({ action: "scanCurrentSession" }, (response) => {
      if (t1) clearTimeout(t1);
      if (t2) clearTimeout(t2);
      btnFullSync.disabled = false;
      btnFullSync.textContent = " Đồng Bộ Toàn Bộ Về Server";

      if (response && response.success) {
        setScanStatus(` ${response.message}`, 4000);
        showToast(response.message);
        if (response.accounts && Array.isArray(response.accounts)) {
          renderAllData({
            accounts: response.accounts,
            bms: response.bms || [],
            pages: response.pages || [],
            c_user: response.data?.fb_uid || response.cUser || response.uid,
            user_name: response.data?.profile_name,
          });
        } else {
          chrome.storage.local.get(["cachedData"], (res) => {
            renderAllData(res.cachedData);
          });
        }
      } else {
        setScanStatus(` ${response ? response.message : "Đồng bộ thất bại; kiểm tra mạng!"}`, 5000);
        showToast(response ? response.message : "Đồng bộ thất bại; kiểm tra mạng!");
      }
    });
  }
  btnFullSync.addEventListener("click", triggerSync);

  // Action: Copy Cookie & Token
  btnCopyCookieToken.addEventListener("click", async () => {
    chrome.cookies.getAll({ domain: ".facebook.com" }, async (cookies) => {
      const cookieStr = (cookies || []).map((c) => `${c.name}=${c.value}`).join("; ");
      const storage = await chrome.storage.local.get(["latestToken", "latestEaabToken", "latestEaagToken"]);
      const token = storage.latestEaagToken || storage.latestEaabToken || storage.latestToken || "";

      let text = `COOKIE:\n${cookieStr}\n\nTOKEN:\n${token}`;
      if (storage.latestEaagToken) text += `\n\nEAAG TOKEN (BM):\n${storage.latestEaagToken}`;
      if (storage.latestEaabToken) text += `\n\nEAAB TOKEN (Ads):\n${storage.latestEaabToken}`;

      navigator.clipboard.writeText(text);
      showToast(" Đã copy Cookie & Access Token (EAAG/EAAB) vào Clipboard!");
    });
  });

  // Action: Execute Share
  btnExecuteShare.addEventListener("click", () => {
    const actId = shareSelectAccount.value;
    const targetUid = document.getElementById("shareTargetUid").value.trim();
    const role = document.getElementById("shareRoleSelect").value;

    if (!actId || !targetUid) {
      showToast("Vui lòng chọn TKQC và nhập UID Facebook nhận quyền!");
      return;
    }

    btnExecuteShare.disabled = true;
    btnExecuteShare.textContent = " Đang gửi lệnh Share...";

    chrome.runtime.sendMessage(
      {
        action: "EXECUTE_SHARE",
        act_id: actId,
        target_uid: targetUid,
        role: role,
        serverUrl: serverUrlInput.value.trim(),
        clientKey: clientKeyInput.value.trim(),
      },
      (res) => {
        btnExecuteShare.disabled = false;
        btnExecuteShare.textContent = " Thực Thi Share Quyền Trực Tiếp";
        showToast(" Đã gửi lệnh Share TKQC thành công!");
      }
    );
  });

  // Action: Execute Set Camp
  btnExecuteSetCamp.addEventListener("click", () => {
    const actId = setcampAccountSelect.value;
    const budget = document.getElementById("setcampBudgetInput").value;
    const postOrPage = document.getElementById("setcampPostInput").value.trim();

    if (!actId) {
      showToast("Vui lòng chọn TKQC cần Set Camp!");
      return;
    }

    btnExecuteSetCamp.disabled = true;
    btnExecuteSetCamp.textContent = " Đang tạo Camp trên trình duyệt...";

    chrome.runtime.sendMessage(
      {
        action: "EXECUTE_SETCAMP",
        act_id: actId,
        payload: {
          name: `Auto Camp — ${new Date().toLocaleTimeString("vi-VN")}`,
          daily_budget: budget,
          post_or_page: postOrPage,
          status_on_create: "PAUSED",
        },
        serverUrl: serverUrlInput.value.trim(),
        clientKey: clientKeyInput.value.trim(),
      },
      (res) => {
        btnExecuteSetCamp.disabled = false;
        btnExecuteSetCamp.textContent = " Khởi Tạo Camp Tức Thì Trên Trình Duyệt";
        showToast(" Đã tạo Campaign thành công trực tiếp từ trình duyệt!");
      }
    );
  });

  // Action: Fetch Tasks Log
  async function refreshTasksLog() {
    const cfg = await chrome.storage.local.get(["serverUrl", "clientKey"]);
    try {
      const res = await fetch(`${cfg.serverUrl || DEFAULT_SERVER_URL}/api/v1/vias/extension-tasks/poll?limit=20`, {
        headers: { "X-AdsOS-Client-Key": cfg.clientKey || "" }
      });
      if (res.ok) {
        const data = await res.json();
        const tasks = data.tasks || [];
        countTasks.textContent = tasks.length;
        if (tasks.length === 0) {
          taskListContainer.innerHTML = `<div class="text-center py-4 text-muted">Chưa có tác vụ nào trong hàng đợi.</div>`;
          return;
        }
        taskListContainer.innerHTML = tasks.map((t) => `
          <div class="task-item">
            <div class="task-item-head">
              <span class="task-type">${t.task_type}</span>
              <span class="badge ${t.status === "COMPLETED" ? "badge-live" : (t.status === "FAILED" ? "badge-die" : "badge-warn")}">${t.status}</span>
            </div>
            <div style="color: #cbd5e1; font-size: 11px;">Mục tiêu: <code>act_${t.target_act_id || "ALL"}</code> | Yêu cầu: ${t.requested_by}</div>
            <div style="color: #64748b; font-size: 10px; margin-top: 2px;">Tạo lúc: ${new Date(t.created_at).toLocaleTimeString("vi-VN")}</div>
          </div>
        `).join("");
      }
    } catch (_) {
      taskListContainer.innerHTML = `<div class="text-center py-3 text-rose">Không thể tải lịch sử lệnh từ Server.</div>`;
    }
  }
  btnRefreshTasks.addEventListener("click", refreshTasksLog);

  chrome.runtime.onMessage.addListener((message) => {
    if (message.action !== "SYNC_PROGRESS") return;
    const current = Math.max(0, Number(message.current) || 0);
    const total = Math.max(0, Number(message.total) || 0);
    setScanStatus(
      `Tiến độ: ${current} / ${total || "?"} — ${message.message || "Đang tải dữ liệu Meta..."}`
    );
  });

  
  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // 1. Hiển thị ngay dữ liệu trong cache khi mở Popup
  if (storage.cachedData && storage.cachedData.accounts && storage.cachedData.accounts.length > 0) {
    renderAllData(storage.cachedData);
  } else {
    // 2. Tự động đồng bộ ngay lần đầu mở Popup mà không cần bấm nút
    triggerSync();
  }

  // 3. Tự động cập nhật bảng Popup khi Background lưu dữ liệu mới
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes.cachedData?.newValue) {
      renderAllData(changes.cachedData.newValue);
      updatePopupSessionBadges();
    }
  });
});