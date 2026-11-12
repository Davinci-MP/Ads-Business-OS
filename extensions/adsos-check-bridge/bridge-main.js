// bridge-main.js - Expose ExtensionBridge on authorized domains with postMessage request/response
(function() {
  const authorized = ["localhost", "127.0.0.1"];
  let pendingRequests = {};
  let requestIdCounter = 0;

  // Helper: send request and wait for response
  function sendRequest(action, payload) {
    return new Promise((resolve, reject) => {
      const id = `XMETA_REQUEST_${++requestIdCounter}`;
      pendingRequests[id] = { resolve, reject, action, payload };
      window.postMessage({ type: "ADSOS_BRIDGE_RELAY", requestId: id, payload: { action, payload } }, "*");
      // Timeout after 10 seconds
      setTimeout(() => {
        delete pendingRequests[id];
        reject(new Error("Bridge request timeout"));
      }, 10000);
    });
  }

  // Helper: handle incoming response
  window.addEventListener("message", (e) => {
    if (e.source !== window) return;
    const { type } = e.data;
    if (type && type.startsWith("XMETA_RESPONSE_")) {
      const requestId = type.replace("XMETA_RESPONSE_", "");
      const pending = pendingRequests[requestId];
      if (pending) {
        delete pendingRequests[requestId];
        if (e.data.success) {
          pending.resolve(e.data.result);
        } else {
          pending.reject(new Error(e.data.error || "Unknown error"));
        }
      }
    }
  });

  const EB = {
    // Session & token helpers
    getSession() {
      return sendRequest("GET_SESSION", {});
    },
    getAccessToken() {
      return sendRequest("GET_ACCESS_TOKEN", {});
    },
    getTokens() {
      return sendRequest("GET_TOKENS", {});
    },

    // Bridge native UI actions
    showPopover() {
      return sendRequest("SHOW_POPOVER", {});
    },
    setTheme(mode) {
      return sendRequest("SET_THEME", { mode });
    },

    // Native OTP & BM actions
    readOtp() {
      return sendRequest("OWA_READ_OTP", {});
    },
    removeBmAdmin(bmId, uid, method) {
      return sendRequest("REMOVE_BM_ADMINS", { bmId, uid, method });
    },

    // Super Target & Ads Check
    superTarget(keyword, limit) {
      return sendRequest("FETCH_SUPER_TARGET", { keyword, limit });
    },

    // Manifest & extension info
    getManifest() {
      return sendRequest("GET_MANIFEST", {});
    },
    getExtensionId() {
      return sendRequest("GET_EXTENSION_ID", {});
    },

    // Live check
    checkLive() {
      return sendRequest("CHECK_LIVE", {});
    },
    shareBmAndAssignAccounts(payload) {
      return sendRequest("SHARE_BM_ACCOUNTS", payload);
    },

    // Storage API
    storage: {
      get(keys) {
        return sendRequest("STORAGE_GET", { keys });
      },
      set(items) {
        return sendRequest("STORAGE_SET", { items });
      },
      remove(keys) {
        return sendRequest("STORAGE_REMOVE", { keys });
      }
    },

    // Cookie helpers
    getCookies(filters) {
      return sendRequest("GET_COOKIES", { filters });
    },
    setCookie(cookie) {
      return sendRequest("SET_COOKIE", { cookie });
    },
    emptyCookie() {
      return sendRequest("EMPTY_COOKIE", {});
    },

    // Tab actions
    openTab(url) {
      return sendRequest("OPEN_TAB", { url });
    },
    openWindow(url, features) {
      return sendRequest("OPEN_WINDOW", { url, features });
    },

    // BM management
    setupAcctLists() {
      return sendRequest("SETUP_ACCT_LISTS", {});
    },
    clearAcctLists() {
      return sendRequest("CLEAR_ACCT_LISTS", {});
    },

    // Proxy management
    setGroupProxy(group) {
      return sendRequest("SET_GROUP_PROXY", { group });
    },
    setProxySlots(slots) {
      return sendRequest("SET_PROXY_SLOTS", { slots });
    },
    endProxySlots() {
      return sendRequest("END_PROXY_SLOTS", {});
    },

    // Targeting
    superTarget(keyword, limit) {
      return sendRequest("FETCH_SUPER_TARGET", { keyword, limit });
    }
  };

  // Expose on window for content scripts & web apps
  if (authorized.includes(location.hostname) || location.hostname === "127.0.0.1") {
    window.ExtensionBridge = window.EB = window.ADSOSBridge = EB;
  }
})();
