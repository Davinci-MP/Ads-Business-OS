(async function () {
  "use strict";
  const params = new URLSearchParams(location.search);
  const accountId = (params.get("id") || "").replace(/^act_/, "");
  const output = document.getElementById("output");
  function fact(label, value) {
    const box = document.createElement("div"); box.className = "fact";
    const name = document.createElement("span"); name.textContent = label;
    const val = document.createElement("strong"); val.textContent = value == null || value === "" ? "—" : String(value);
    box.append(name, val); document.getElementById("facts").appendChild(box);
  }
  try {
    if (!accountId) throw new Error("URL thiếu ID tài khoản quảng cáo.");
    const bridge = await metaOs.waitForBridge(6000);
    const tokens = await bridge.getTokens();
    const token = metaOs.tokenFrom(tokens);
    if (!token) throw new Error("Chưa có access token Meta trong phiên hiện tại.");
    const fields = "id,name,account_status,currency,amount_spent,balance,spend_cap,business_name";
    const result = await bridge.fetch("https://graph.facebook.com/v26.0/act_" + encodeURIComponent(accountId) + "?fields=" + encodeURIComponent(fields) + "&access_token=" + encodeURIComponent(token), {}, "json");
    const data = result.data || result;
    if (!result.success || data.error) throw new Error((data.error && data.error.message) || result.error || "Meta từ chối yêu cầu");
    metaOs.setText("subtitle", "act_" + accountId);
    fact("Tên", data.name); fact("Tiền tệ", data.currency); fact("Trạng thái", data.account_status); fact("Doanh nghiệp", data.business_name); fact("Đã chi", data.amount_spent); fact("Số dư", data.balance); fact("Giới hạn", data.spend_cap);
    output.textContent = "Dữ liệu được đọc trực tiếp từ Meta; token không hiển thị hoặc ghi log.";
  } catch (error) { output.textContent = "Lỗi: " + error.message; }
})();
