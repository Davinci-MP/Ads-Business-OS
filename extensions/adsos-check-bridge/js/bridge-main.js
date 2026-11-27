(function () {
  if (window.__extensionBridgeReady && !window.__extensionBridgeFallback) return; // chỉ bail nếu bridge THẬT đã chạy; nếu mới chỉ có fallback thì vẫn chạy để ghi đè bằng bridge thật
  const REQ = "METAOS_REQUEST_",
    RES = "METAOS_RESPONSE_";
  let rid = 0;
  const pending = new Map();
  window.addEventListener("message", (e) => {
    if (
      e.source !== window ||
      !e.data ||
      !e.data.type ||
      !e.data.type.startsWith(RES)
    )
      return;
    const { id, result } = e.data,
      fn = pending.get(id);
    fn && (pending.delete(id), fn(result));
  });
  function send(a, p = {}) {
    return new Promise((r) => {
      const id = ++rid;
      pending.set(id, r);
      window.postMessage({ type: REQ + id, id, action: a, payload: p }, "*");
      setTimeout(() => {
        pending.has(id) &&
          (pending.delete(id), r({ success: !1, error: "Timeout" }));
      }, 6e4);
    });
  }
  const EB = {
    extensionId: null,
    _isConnected: !0,
    isConnected() {
      return this._isConnected;
    },
    isInExtension() {
      return !0;
    },
    onReady(fn) {
      typeof fn === "function" && fn();
    },
    getManifest: () => send("getManifest"),
    getExtensionId: async () => {
      const e = await send("getExtensionId");
      e.success && e.extensionId && (EB.extensionId = e.extensionId);
      return e;
    },
    getExtensionURL: (p) => send("getExtensionURL", { path: p }),
    checkLive: () => send("checkLive"),
    getAccessToken: () => send("getAccessToken"),
    getTokens: () => send("getTokens"),
    fetch: (u, o = {}, rt = "text") =>
      send("fetch", { url: u, options: o, responseType: rt }),
    fetchWithCookies: (u, o = {}, rt = "text") =>
      send("fetchWithCookies", { url: u, options: o, responseType: rt }),
    graphqlRequest: (u, b, h = {}) =>
      send("graphqlRequest", { url: u, body: b, headers: h }),
    storage: {
      get: (k) => send("storage.get", { keys: k }),
      set: (d) => send("storage.set", { data: d }),
      remove: (k) => send("storage.remove", { keys: k }),
    },
    emptyCookie: (d = "facebook.com") => send("emptyCookie", { domain: d }),
    setCookie: (c) => send("setCookie", c),
    getCookies: (d) => send("getCookies", { domain: d }),
    openTab: (u) => send("openTab", { url: u }),
    openWindow: (o) => send("openWindow", o || {}),
    owaReadOtp: (opts) => send("owaReadOtp", opts || {}),
    setupAcctLists: (ua) => send("setupAcctLists", { uaList: ua }),
    setGroupProxy: (p) => send("setGroupProxy", { proxy: p }),
    setProxySlots: (cfg) => send("setProxySlots", { cfg }),
    endProxySlots: () => send("endProxySlots"),
    // Tool metaOs Runner cài trên máy khách: hỏi trạng thái, bật cho mẻ (kèm bảng uid→{proxy,ua}), tắt khi kết mẻ.
    runnerStatus: () => send("runnerStatus"),
    setRunner: (cfg) => send("setRunner", { cfg }),
    endRunner: () => send("endRunner"),
    clearAcctLists: () => send("clearAcctLists"),
  };
  window.ExtensionBridge = EB;
  window.EB = EB;
  window.__extensionBridgeReady = !0;
  window.__extensionBridgeFallback = !1; // bridge THẬT active → xoá cờ fallback (nếu fallback lỡ set trước)
  EB.getExtensionId().then((e) => {
    e.success &&
      ((window.__extensionId = e.extensionId),
      (EB.extensionId = e.extensionId));
  });
  window.dispatchEvent(
    new CustomEvent("ExtensionBridgeReady", {
      detail: { extensionId: EB.extensionId },
    })
  );
})();
