/* Tối ưu Facebook — cầu chuyển cài đặt sang ngữ cảnh trang.
 *
 * Chạy ở ngữ cảnh CÁCH LY vì đây là nơi DUY NHẤT đọc được chrome.storage. Phần vá thật nằm ở
 * js/fb-opt-main.js chạy ở ngữ cảnh trang, mà ở đó không có chrome.* — nên phải có tệp này
 * chuyển tiếp.
 *
 * ⚠ Cố tình TÁCH KHỎI content.js: khối Facebook trong tệp đó gác bằng host.includes("facebook.com"),
 * tức khớp cả "facebook.com.attacker.com". Ở đây phạm vi do manifest quyết định bằng mẫu khớp
 * (*://*.facebook.com/*), vốn neo đúng hậu tố tên miền nên không dính lỗ đó.
 */
(function () {
  "use strict";

  // Web ghi cả khoá trung tính lẫn khoá cũ → đọc khoá trung tính trước (gói đại lý thay chữ "fiox"; bản obfuscate có
  // thể tách chuỗi khoá cũ làm thay sai tên)
  var KEY = "extFbOptimize";
  var KEY_OLD = "fioxFbOptimize";
  // Tên kênh TRUNG TÍNH (không chứa "fiox"): gói đại lý thay chữ trong từng file riêng — tên có "fiox" mà 1 file bị
  // obfuscate tách chuỗi thì 2 đầu lệch tên, công tắc im lặng. Đổi phải đổi ĐỒNG THỜI ở fb-opt-main.js.
  var KENH = "EXTFBOPT_CFG";
  var SAN_SANG = "EXTFBOPT_READY";
  var cfg = {};

  function gui() {
    try { window.postMessage({ type: KENH, cfg: cfg }, location.origin); } catch (e) {}
  }

  // Bên ngữ cảnh trang gắn xong bộ nghe thì báo sang, lúc đó gửi mới chắc tới nơi.
  window.addEventListener("message", function (e) {
    if (e.source !== window || !e.data || e.data.type !== SAN_SANG) return;
    gui();
  }, false);

  try {
    chrome.storage.local.get([KEY, KEY_OLD], function (st) {
      cfg = (st && (st[KEY] || st[KEY_OLD])) || {};
      gui();
    });
  } catch (e) {}

  // Gạt công tắc trên web phải ăn ngay, không bắt người dùng tải lại tab.
  try {
    chrome.storage.onChanged.addListener(function (ch, area) {
      var c = area === "local" && (ch[KEY] || ch[KEY_OLD]);
      if (!c) return;
      cfg = c.newValue || {};
      gui();
    });
  } catch (e) {}
})();
