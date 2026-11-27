(function () {
  "use strict";

  function waitForBridge(timeoutMs) {
    if (window.ExtensionBridge) return Promise.resolve(window.ExtensionBridge);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("Chưa phát hiện extension metaOs")), timeoutMs || 5000);
      window.addEventListener("ExtensionBridgeReady", () => {
        clearTimeout(timer);
        resolve(window.ExtensionBridge);
      }, { once: true });
    });
  }

  function tokenFrom(data) {
    if (!data || typeof data !== "object") return "";
    return data.accessToken || data.access_token || data.eaag_token || data.eaagToken || data.eaab_token || data.eaabToken || "";
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value == null ? "" : String(value);
  }

  window.metaOs = { waitForBridge, tokenFrom, setText };
})();
