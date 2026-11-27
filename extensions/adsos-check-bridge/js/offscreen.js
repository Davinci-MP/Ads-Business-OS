/**
 * Offscreen document (chỉ có chrome.runtime): nhúng trang chạy nền <origin>/ext-runner của app — logic việc nền do
 * server phục vụ — rồi báo service worker khi trang đó chạy xong. Chỉ nhận tin của ĐÚNG iframe đó, đúng origin, đúng
 * mã lượt chạy. origin/r/j do background.js truyền qua query (đã kiểm origin thuộc tên miền app).
 * Tên tin nhắn KHÔNG chứa thương hiệu: gói tải của đại lý thay chữ trong .js extension, trang server thì không.
 */
(function () {
  var q = new URLSearchParams(location.search);
  var origin = q.get("o") || "", run = q.get("r") || "", jobs = q.get("j") || "";
  function report(rep) { try { chrome.runtime.sendMessage({ action: "bgJobs.done", r: run, report: rep }).catch(function () {}); } catch (e) {} }
  if (!/^https:\/\/[a-z0-9.-]+$/i.test(origin) && !/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin)) { report({ err: "bad-origin" }); return; }
  var f = document.createElement("iframe");
  f.src = origin + "/ext-runner?r=" + encodeURIComponent(run) + "&j=" + encodeURIComponent(jobs);
  window.addEventListener("message", function (e) {
    if (e.origin !== origin || e.source !== f.contentWindow) return;
    var d = e.data || {};
    if (d.type !== "bgJobs:done" || d.r !== run) return;
    report(d.report || null);
  });
  document.body.appendChild(f);
})();
