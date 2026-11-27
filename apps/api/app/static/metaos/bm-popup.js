(async function () {
  "use strict";
  const params = new URLSearchParams(location.search);
  const businessId = params.get("bm") || "";
  const output = document.getElementById("output");
  function fact(label, value) {
    const box = document.createElement("div"); box.className = "fact";
    const name = document.createElement("span"); name.textContent = label;
    const val = document.createElement("strong"); val.textContent = value == null || value === "" ? "—" : String(value);
    box.append(name, val); document.getElementById("facts").appendChild(box);
  }
  try {
    if (!businessId) throw new Error("URL thiếu Business ID.");
    const bridge = await metaOs.waitForBridge(6000);
    const tokens = await bridge.getTokens();
    const token = metaOs.tokenFrom(tokens);
    if (!token) throw new Error("Chưa có access token Meta trong phiên hiện tại.");
    const fields = "id,name,verification_status,created_time,owned_ad_accounts.limit(100){id},client_ad_accounts.limit(100){id}";
    const result = await bridge.fetch("https://graph.facebook.com/v26.0/" + encodeURIComponent(businessId) + "?fields=" + encodeURIComponent(fields) + "&access_token=" + encodeURIComponent(token), {}, "json");
    const data = result.data || result;
    if (!result.success || data.error) throw new Error((data.error && data.error.message) || result.error || "Meta từ chối yêu cầu");
    metaOs.setText("subtitle", businessId);
    fact("Tên BM", data.name); fact("Xác minh", data.verification_status); fact("Ngày tạo", data.created_time); fact("TKQC sở hữu", (data.owned_ad_accounts && data.owned_ad_accounts.data || []).length); fact("TKQC được chia sẻ", (data.client_ad_accounts && data.client_ad_accounts.data || []).length);
    output.textContent = "Dữ liệu được đọc trực tiếp từ Meta; token không hiển thị hoặc ghi log.";
  } catch (error) { output.textContent = "Lỗi: " + error.message; }
})();
