// fb-opt-relay.js - Listen for EXTFBOPT_READY and sync config via postMessage
// ISOLATED world ONLY - talks to MAIN world via window.postMessage

// Signal MAIN world that ISOLATED world is ready
window.addEventListener("load", () => {
  window.postMessage({ type: "EXTFBOPT_READY" }, "*");
});

// Receive config from MAIN world
window.addEventListener("message", (e) => {
  if (e.data?.type === "EXTFBOPT_CFG") {
    const cfg = e.data.cfg || {};
    chrome.storage.local.get(["extFbOptimize"], (res) => {
      chrome.storage.local.set({ extFbOptimize: cfg.extFbOptimize || res.extFbOptimize });
    });
  }
});

// Listen for storage changes and forward to MAIN world
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.extFbOptimize) {
    const cfg = changes.extFbOptimize.newValue;
    // Forward to MAIN world via postMessage
    if (typeof window.EXTFBOPT_CFG === "function") {
      window.EXTFBOPT_CFG(cfg);
    } else {
      // Fallback: postMessage to MAIN world
      window.postMessage({ type: "EXTFBOPT_CFG_UPDATED", cfg }, "*");
    }
  }
});