(async function () {
  "use strict";
  const keyInput = document.getElementById("clientKey");
  const output = document.getElementById("output");
  keyInput.value = localStorage.getItem("metaosClientKey") || "";

  try {
    const response = await fetch("/health", { cache: "no-store" });
    if (!response.ok) throw new Error("HTTP " + response.status);
    document.getElementById("serverDot").classList.add("ok");
    metaOs.setText("serverStatus", "Backend Ads Business OS đang hoạt động");
  } catch (error) {
    document.getElementById("serverDot").classList.add("bad");
    metaOs.setText("serverStatus", "Không kết nối được backend");
  }

  let bridge = null;
  try {
    bridge = await metaOs.waitForBridge(6000);
    document.getElementById("extensionDot").classList.add("ok");
    metaOs.setText("extensionStatus", "Extension metaOs đã kết nối");
  } catch (error) {
    document.getElementById("extensionDot").classList.add("bad");
    metaOs.setText("extensionStatus", error.message);
  }

  document.getElementById("saveKey").addEventListener("click", async () => {
    const key = keyInput.value.trim();
    localStorage.setItem("metaosClientKey", key);
    if (bridge) await bridge.storage.set({ clientKey: key, licenseKey: key });
    output.textContent = "Đã lưu Client Key trên máy này.";
  });

  document.getElementById("syncNow").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      bridge = bridge || await metaOs.waitForBridge(3000);
      const [tokens, cookieResult] = await Promise.all([
        bridge.getTokens(),
        bridge.getCookies(".facebook.com")
      ]);
      const cookieRows = cookieResult.cookies || cookieResult.data || [];
      const cookie = Array.isArray(cookieRows)
        ? cookieRows.map((item) => item.name + "=" + item.value).join("; ")
        : (tokens.cookie || "");
      const uidMatch = cookie.match(/(?:^|;\s*)c_user=([^;]+)/);
      const key = keyInput.value.trim();
      const payload = {
        fb_uid: tokens.uid || tokens.c_user || (uidMatch && uidMatch[1]) || "",
        client_key: key || null,
        profile_name: "metaOs Chrome",
        cookie,
        access_token: metaOs.tokenFrom(tokens) || null,
        eaag_token: tokens.eaag_token || tokens.eaagToken || null,
        eaab_token: tokens.eaab_token || tokens.eaabToken || null,
        fb_dtsg: tokens.fb_dtsg || tokens.dtsg || null,
        device_name: navigator.userAgent
      };
      if (!payload.fb_uid) throw new Error("Không tìm thấy phiên Facebook đang đăng nhập.");
      const response = await fetch("/api/v1/vias/extension-ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-AdsOS-Client-Key": key },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok || data.success === false) throw new Error(data.detail || data.message || "Đồng bộ thất bại");
      output.textContent = JSON.stringify({ success: true, fb_uid: data.fb_uid, via_id: data.via_id, token_status: data.token_status }, null, 2);
    } catch (error) {
      output.textContent = "Lỗi: " + error.message;
    } finally {
      button.disabled = false;
    }
  });
})();
