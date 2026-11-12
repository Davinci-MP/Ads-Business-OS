// =============================================================================
// ADSOS CHECK PRO — Content Script (Lite Mode for localhost / 127.0.0.1)
// =============================================================================
// - Chỉ chạy bridge-main.js script injection và postMessage relay trên localhost
// - KHÔNG thực hiện showPopover(), Bubble Bar, hay Facebook DOM observers trên localhost
// - Bảo vệ tất cả document.body / document.head accessesagainst null ở document_start
// - Chỉ báo cáo act_id từ URL; không đọc cookie/token/HTML phiên Facebook.
// =============================================================================

(function () {
  "use strict";

  // ---- LOCALHOST GUARD: chỉ chạy bridge injection & relay trên localhost ----
  const localhostRE = /^https?:\/\/(localhost|127\.0\.0\.1)(?::\d+)?/;
  const isLocalhost = localhostRE.test(window.location.href);

  // Chỉ report page context và act_id detection trên localhost
  function reportPageContext() {
    if (window.location.href === lastReportedUrl) return;
    lastReportedUrl = window.location.href;
    const match = window.location.href.match(/(?:act[=_]|act_)([0-9]{5,})/);
    try {
      chrome.runtime.sendMessage({
        type: "FB_PAGE_CONTEXT",
        url: window.location.href,
        act_ids: match ? [match[1]] : [],
      }, () => void chrome.runtime.lastError);
    } catch (_) {}
  }

  let lastReportedUrl = "";

  // Chỉ chạy reportPageContext trên localhost
  if (isLocalhost) {
    reportPageContext();
    window.addEventListener("load", reportPageContext);
    setInterval(reportPageContext, 4000);
  }

  // ---- LOCALHOST-GUARDED VARIABLES & FUNCTIONS ----
  let currentActId = "";
  let currentDetails = null;

  // Guard all document.body / document.head accesses: chỉ chạy DOM ops không phải localhost
  function safeDomOperation(fn) {
    if (isLocalhost) return;
    if (document.body && document.head) {
      fn();
    }
  }

  // showPopover KHÔNG chạy trên localhost
  function showPopover() {
    if (isLocalhost) return;
    const popover = document.createElement("div");
    popover.id = "adsos-popover";
    Object.assign(popover.style, {
      position: "fixed",
      top: "20px",
      left: "50%",
      transform: "translateX(-50%)",
      zIndex: "2147483647",
      background: "var(--bg-elevated)",
      border: "2px solid var(--status-ok)",
      borderRadius: "6px",
      padding: "8px 12px",
      minWidth: "260px",
      boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
      fontFamily: "inherit",
    });
    popover.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <span style="font-weight:600;color:var(--text-primary)">ADSOS CHECK V8</span>
        <button id="adsos-close-popover" style="background:none;border:none;font-size:1.2rem;color:var(--text-secondary)">✕</button>
      </div>
      <div style="display:flex;flex-direction:column;gap:4px">
        <button class="adsos-popover-btn" data-tab="1">Trình quảng cáo</button>
        <button class="adsos-popover-btn" data-tab="2">Lập hoá đơn</button>
        <button class="adsos-popover-btn" data-tab="3">Trình tổng quan</button>
        <button class="adsos-popover-btn" data-tab="4">Người dùng</button>
        <button class="adsos-popover-btn" data-tab="5" style="background:var(--status-ok);color:var(--bg-elevated)">Sáng / Tối</button>
        <button class="adsos-popover-btn" data-action="gdcu">Giao diện cũ</button>
      </div>
    `;
    document.body.appendChild(popover);

    popover.querySelectorAll(".adsos-popover-btn").forEach(btn => {
      btn.onclick = () => {
        const tab = btn.dataset.tab;
        const action = btn.dataset.action;
        if (tab === "5") {
          const html = document.documentElement;
          const newTheme = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
          html.setAttribute("data-theme", newTheme);
          chrome.storage.local.set({ adsos_theme: newTheme });
          btn.textContent = newTheme === "dark" ? "Sáng" : "Tối";
        } else if (action === "gdcu") {
          try {
            const fb_dtsg = document.querySelector('input[name="fb_dtsg"]')?.value || "";
            const uid = document.querySelector('input[name="c_user"]')?.value || "";
            const lsd = document.querySelector('input[name="lsd"]')?.value || "";
            if (!uid) { alert("Không tìm thấy UID Facebook"); return; }
            const variables = JSON.stringify({
              input: {
                client_mutation_id: "3",
                actor_id: uid,
                bmc_optin_status: "OPT_OUT"
              }
            });
            const graphqlReq = {
              operationName: "BizKitSetBMCOptinStatusMutation",
              fb_dtsg,
              variables,
              doc_id: "8398852550167223"
            };
            chrome.runtime.sendMessage({ action: "GRAPHQL_REQUEST", req: graphqlReq }, (res) => {
              if (res && res.success) {
                alert("Đã gửi yêu cầu opt-out thành công");
                window.location.reload();
              } else {
                alert("Lỗi opt-out: " + (res && res.message ? res.message : "Unknown error"));
              }
            });
          } catch (_) {
            alert("Lỗi khi gửi opt-out");
          }
        } else {
          chrome.runtime.sendMessage({ action: `SHOW_TAB_${tab}` });
        }
      };
    });

    popover.querySelector("#adsos-close-popover").onclick = () => document.body.removeChild(popover);
  }

  // Bubble Bar & Facebook DOM observers KHÔNG chạy trên localhost
  function initWidgetEvents() {
    // Chỉ inject bridge-main.js script và postMessage relay trên localhost
    if (isLocalhost) {
      // Inject bridge script only on localhost
      const bridgeScript = document.createElement("script");
      bridgeScript.src = chrome.runtime.getURL("bridge-main.js");
      bridgeScript.async = true;
      document.head.appendChild(bridgeScript);

      // postMessage relay: forward messages between extension and localhost page
      window.addEventListener("message", (e) => {
        if (e.data && e.data.type === "ADSOS_BRIDGE_RELAY") {
          const requestId = e.data.requestId;
          chrome.runtime.sendMessage(e.data.payload).then((result) => {
            window.postMessage({
              type: `XMETA_RESPONSE_${requestId}`,
              success: result?.success !== false,
              result,
              error: result?.message,
            }, "*");
          }).catch((error) => {
            window.postMessage({ type: `XMETA_RESPONSE_${requestId}`, success: false, error: error.message }, "*");
          });
        }
      });
    }

    // Không chạy showPopover, Bubble Bar hay Facebook DOM observers trên localhost
    if (!isLocalhost) {
      // Original widget initialization (full mode)
      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAdsOsCheckV8Widget);
      } else {
        initAdsOsCheckV8Widget();
      }
    }
  }

  // Safe document access helpers for localhost
  function $(selector) {
    if (isLocalhost) return null;
    const el = document.body?.querySelector(selector);
    return el || null;
  }

  // Initialize: only bridge injection + relay on localhost
  if (isLocalhost) {
    // Report page context on load + interval
    reportPageContext();
    window.addEventListener("load", reportPageContext);
    setInterval(reportPageContext, 4000);

    // Inject bridge script + postMessage relay
    const bridgeScript = document.createElement("script");
    bridgeScript.src = chrome.runtime.getURL("bridge-main.js");
    bridgeScript.async = true;
    document.head.appendChild(bridgeScript);

    window.addEventListener("message", (e) => {
      if (e.data && e.data.type === "ADSOS_BRIDGE_RELAY") {
        const requestId = e.data.requestId;
        chrome.runtime.sendMessage(e.data.payload).then((result) => {
          window.postMessage({
            type: `XMETA_RESPONSE_${requestId}`,
            success: result?.success !== false,
            result,
            error: result?.message,
          }, "*");
        }).catch((error) => {
          window.postMessage({ type: `XMETA_RESPONSE_${requestId}`, success: false, error: error.message }, "*");
        });
      }
    });
  } else {
    // Full mode: original widget init on DOM ready
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initWidgetEvents);
    } else {
      initWidgetEvents();
    }
  }

  // ---- LOCALHOST SAFE NAVIGATION & URL DETECTION ----
  function detectActIdFromUrlOrDom() {
    const url = window.location.href;
    // Only look for act_id in URL query params on localhost
    const m = url.match(/[?&#](?:act|account_id|asset_id)=([0-9]{5,})/);
    if (m && m[1]) return m[1];
    // DOM inspection skipped on localhost
    return "";
  }

  // Report initial page context
  if (isLocalhost) {
    reportPageContext();
  }

})();
