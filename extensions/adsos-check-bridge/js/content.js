/**
 * metaOs - Content Script (Unified)
 * Gộp tất cả content scripts: bridge, bridge-main, fb-fetcher, popup inject
 * @version 1.6.3
 */
(function () {
  "use strict";
  const url = location.href,
    host = location.hostname;

  /**
   * HAI ĐỊA CHỈ (xem giải thích đầy đủ ở background.js).
   *
   * PLATFORM_ANCHOR — nhúng cứng. Dùng cho cưỡng chế license (chặn key, nhịp
   *   tim). Cố ý KHÔNG đi qua domain đại lý để đại lý không tắt được.
   * getApiBase() — địa chỉ giao diện của đại lý, đọc từ storage. Hôm nay bằng
   *   chính điểm neo nên hành vi không đổi.
   */
  const PLATFORM_ANCHOR = "http://127.0.0.1:8000";
  let _apiBase = PLATFORM_ANCHOR;
  try {
    chrome.storage &&
      chrome.storage.local.get(["apiBase"], (st) => {
        const v = st && st.apiBase;
        if (typeof v === "string" && /^https?:\/\/[a-z0-9.-]+(?::\d+)?\/?$/i.test(v)) _apiBase = v.replace(/\/+$/, "");
      });
  } catch (e) {}
  const getApiBase = () => _apiBase;

  // Ngôn ngữ app (cookie fiox_lang của apiBase) — nối ?lang= vào iframe panel (/popup, /bm-popup.html)
  // vì panel nhúng cross-site trên facebook.com nên cookie KHÔNG tới server → server mặc định tiếng Việt.
  // Lấy qua background (chrome.cookies). CHỈ ở top frame (panel chỉ dựng ở top) để khỏi spam message
  // trên hàng loạt iframe của Facebook. Làm mới khi tab hiện lại.
  let _fxLang = "";

  // Mini-i18n cho chữ VỎ do content.js tự dựng (bubble-bar) — lớp dịch web-app KHÔNG với tới content
  // script trên facebook.com nên phải tự tra. Khớp CHÍNH XÁC chuỗi nguồn tiếng Việt → bản dịch theo
  // _fxLang; vi / rỗng / không khớp (vd đại lý đổi nhãn qua shield-config) → giữ nguyên.
  const _BB_I18N = {
    "Trình quảng cáo": { en: "Ads Manager", th: "ตัวจัดการโฆษณา", "zh-CN": "广告管理工具", "zh-TW": "廣告管理員", tl: "Ads Manager" },
    "Lập hoá đơn": { en: "Billing", th: "การเรียกเก็บเงิน", "zh-CN": "账单", "zh-TW": "帳單", tl: "Pagsingil" },
    "Trình tổng quan": { en: "Overview", th: "ภาพรวม", "zh-CN": "概览", "zh-TW": "總覽", tl: "Overview" },
    "Người dùng": { en: "Users", th: "ผู้ใช้", "zh-CN": "用户", "zh-TW": "使用者", tl: "Mga user" },
    "Giao diện cũ": { en: "Old interface", th: "อินเทอร์เฟซเดิม", "zh-CN": "旧版界面", "zh-TW": "舊版介面", tl: "Lumang interface" },
    "Đang chuyển…": { en: "Switching…", th: "กำลังสลับ…", "zh-CN": "切换中…", "zh-TW": "切換中…", tl: "Lumilipat…" },
    "Đã chuyển ✓": { en: "Switched ✓", th: "สลับแล้ว ✓", "zh-CN": "已切换 ✓", "zh-TW": "已切換 ✓", tl: "Lumipat na ✓" },
    "Lỗi, thử lại": { en: "Error, retry", th: "ข้อผิดพลาด ลองใหม่", "zh-CN": "出错，重试", "zh-TW": "錯誤，請重試", tl: "Error, subukan ulit" },
    "Thu gọn": { en: "Collapse", th: "ย่อ", "zh-CN": "收起", "zh-TW": "收合", tl: "I-collapse" },
    "Mở thanh công cụ": { en: "Open toolbar", th: "เปิดแถบเครื่องมือ", "zh-CN": "打开工具栏", "zh-TW": "開啟工具列", tl: "Buksan ang toolbar" },
  };
  const _bbT = (s) => {
    if (!_fxLang || _fxLang === "vi") return s;
    const row = _BB_I18N[s];
    return row && row[_fxLang] ? row[_fxLang] : s;
  };
  // Dịch lại nhãn bubble-bar đang hiển thị (khi _fxLang vừa lấy được hoặc user đổi ngôn ngữ rồi quay lại tab).
  // Chọn theo id ngẫu nhiên _rp+"bb" (KHÔNG đặt selector cố định kẻo eztool bắt được).
  const _bbRetranslate = () => {
    try {
      const _bar = document.getElementById(_rp + "bb");
      if (!_bar) return;
      _bar.querySelectorAll("[data-src]").forEach((el) => {
        const s = el.getAttribute("data-src");
        if (s) el.textContent = _bbT(s);
      });
    } catch (e) {}
  };

  function _fxSyncLang() {
    try {
      chrome.runtime.sendMessage({ action: "fxGetLang" }, (r) => {
        if (chrome.runtime.lastError) return;
        if (r && typeof r.lang === "string") { _fxLang = r.lang; _bbRetranslate(); }
      });
    } catch (e) {}
  }
  function _fxLangQS() { return _fxLang ? "&lang=" + encodeURIComponent(_fxLang) : ""; }
  if (window.top === window) {
    _fxSyncLang();
    try { document.addEventListener("visibilitychange", () => { if (!document.hidden) _fxSyncLang(); }); } catch (e) {}
  }

  // Shield config (background.js sync từ server mỗi 4h). Chứa tham số tạo FAB/popup
  // mà server điều khiển: tag, z-index, vị trí, kích thước, shadow DOM, watchdog interval.
  // Khi EZTOOL thích nghi → sửa server → ext cũ tự chạy config mới, KHÔNG cần cập nhật.
  let _sc = {}; // shield config — fallback {} = dùng default cho mọi tham số
  try {
    chrome.storage && chrome.storage.local.get(["_shieldCfg"], (st) => { _sc = (st && st._shieldCfg) || {}; });
  } catch (e) {}

  // Domain đại lý (bản white-label) = host của homepage_url trong manifest — patch tải xuống
  // đặt homepage_url=https://<domain đại lý>. ĐỌC RUNTIME nên KHÔNG phụ thuộc việc thay chuỗi
  // trong content.js; đọc runtime để bản đóng gói luôn nhận đúng máy chủ được cấu hình.
  let _brandHost = "";
  try {
    const _hp = (chrome.runtime.getManifest() || {}).homepage_url || "";
    _brandHost = String(_hp).replace(/^https?:\/\//, "").replace(/\/.*$/, "").toLowerCase();
    if (_brandHost === "127.0.0.1:8000") _brandHost = "";
  } catch (e) {}
  // ⚠ So khớp CHÍNH XÁC, tuyệt đối KHÔNG dùng host.includes(): content script chạy trên
  // <all_urls> nên bất kỳ trang nào cũng gọi hàm này. Với includes(), một domain do kẻ xấu tự
  // đăng ký tên miền chứa chuỗi gần giống đều có thể khớp → extension bơm cầu
  // nối vào trang của họ → trang đó gọi thẳng ExtensionBridge.getCookies(".facebook.com") lấy
  // trọn c_user + xs của khách, hoặc fetch dưới danh nghĩa khách. Nhánh _brandHost bên dưới
  // vốn đã làm đúng theo kiểu này.
  const _isAppHost = () =>
    host === "localhost" ||
    host === "127.0.0.1" ||
    (!!_brandHost && (host === _brandHost || host.endsWith("." + _brandHost)));

  // Auto-login bằng key nhúng: Chrome mới + extension có key (manifest.author) nhưng
  // localStorage trống → app hiện màn login. Trên domain app, GHI SẴN licenseKey = author
  // (chỉ khi CHƯA có key & CHƯA đăng xuất out-key) để app tự đăng nhập, khỏi nhập lại.
  // Chạy ở document_start (trước inline anti-FOUC + via.js) nên chúng thấy key ngay.
  try {
    if (_isAppHost()) {
      var _src0 = localStorage.getItem("licenseKeySource");
      if (_src0 !== "out-key" && !_src0 && !localStorage.getItem("licenseKey")) {
        var _authKey = (chrome.runtime.getManifest() || {}).author || "";
        if (_authKey) localStorage.setItem("licenseKey", _authKey);
      }
    }
  } catch (e) {}

  // ========== APP DOMAINS - Bridge ==========
  // Inject ExtensionBridge cho các domain app
  if (_isAppHost()) {
    // Bridge Main World (expose ExtensionBridge) - use external file to avoid CSP issues
    const script = document.createElement("script");
    script.src = chrome.runtime.getURL("js/bridge-main.js");
    script.onload = function () {
      this.remove();
    };
    document.documentElement.appendChild(script);

    // Bridge Isolated World (handle requests)
    const EXT_ID = chrome.runtime.id,
      REQ = "METAOS_REQUEST_",
      RES = "METAOS_RESPONSE_";

    // Keep-alive: Tạo persistent connection để giữ Service Worker active
    let keepAlivePort = null;
    function connectKeepAlive() {
      try {
        keepAlivePort = chrome.runtime.connect({ name: "keepAlive" });
        keepAlivePort.onDisconnect.addListener(() => {
          void chrome.runtime.lastError; // Suppress bfcache error
          setTimeout(connectKeepAlive, 1000);
        });
      } catch (e) {
        // Thử lại sau 1s
        setTimeout(connectKeepAlive, 1000);
      }
    }
    connectKeepAlive();

    // Wake up Service Worker bằng cách gửi ping message
    function wakeUpSW() {
      return new Promise((resolve) => {
        try {
          chrome.runtime.sendMessage({ action: "ping" }, () => {
            // Ignore errors, just need to wake up
            if (chrome.runtime.lastError) {
              // SW đang ngủ, đợi 100ms cho nó wake up
              setTimeout(resolve, 100);
            } else {
              resolve();
            }
          });
        } catch (e) {
          setTimeout(resolve, 100);
        }
      });
    }

    // sendBG với wake-up và retry logic
    async function sendBG(a, p = {}, retries = 2) {
      // Wake up Service Worker trước
      await wakeUpSW();

      return new Promise((r, j) => {
        const attempt = (remainingRetries) => {
          try {
            chrome.runtime.sendMessage({ action: a, ...p }, (e) => {
              if (chrome.runtime.lastError) {
                const errMsg = chrome.runtime.lastError.message;
                // Nếu port closed và còn retry, thử lại (silent)
                if (
                  remainingRetries > 0 &&
                  (errMsg.includes("message port closed") ||
                    errMsg.includes("Receiving end does not exist"))
                ) {
                  // Wake up lại rồi retry
                  wakeUpSW().then(() => {
                    setTimeout(() => attempt(remainingRetries - 1), 200);
                  });
                  return;
                }
                j(new Error(`[${a}] ${errMsg}`));
              } else {
                r(e);
              }
            });
          } catch (err) {
            if (remainingRetries > 0) {
              wakeUpSW().then(() => {
                setTimeout(() => attempt(remainingRetries - 1), 200);
              });
              return;
            }
            j(err);
          }
        };
        attempt(retries);
      });
    }

    window.addEventListener("message", async (e) => {
      if (
        e.source !== window ||
        !e.data ||
        !e.data.type ||
        !e.data.type.startsWith(REQ)
      )
        return;
      const { type, id, action: a, payload: p } = e.data;
      let r;
      try {
        switch (a) {
          case "getManifest":
            r = { success: !0, data: chrome.runtime.getManifest() };
            break;
          case "getExtensionId":
            r = { success: !0, extensionId: EXT_ID };
            break;
          case "getExtensionURL":
            r = { success: !0, url: chrome.runtime.getURL(p.path || "") };
            break;
          case "checkLive":
          case "getAccessToken":
          case "getTokens":
          case "fetch":
          case "fetchWithCookies":
          case "graphqlRequest":
          case "storage.get":
          case "storage.set":
          case "storage.remove":
          case "emptyCookie":
          case "setCookie":
          case "getCookies":
          case "metaAiProbe":
          case "metaAiPageWsSetup":
          // proxy/UA theo mẻ clone (B2) → relay xuống SW (scripts.js né throttle IG)
          case "setupAcctLists":
          case "setGroupProxy":
          case "setProxySlots": // proxy RIÊNG từng tài khoản (port-slot) — scripts.js/px-slot.js
          case "endProxySlots":
          // tool metaOs Runner cài trên máy khách — bật/tắt mẻ + hỏi trạng thái (scripts.js/setting.js)
          case "runnerStatus":
          case "setRunner":
          case "endRunner":
          case "clearAcctLists":
          case "owaReadOtp":
            r = await sendBG(a, p);
            break;
          case "openTab":
            chrome.runtime.sendMessage({ action: "openTab", url: p.url });
            r = { success: !0 };
            break;
          case "openWindow":
            chrome.runtime.sendMessage({ action: "openWindow", url: p.url, width: p.width, height: p.height });
            r = { success: !0 };
            break;
          default:
            r = { success: !1, error: "Unknown action: " + a };
        }
        window.postMessage({ type: RES + id, id, result: r }, "*");
      } catch (err) {
        window.postMessage(
          { type: RES + id, id, result: { success: !1, error: err.message } },
          "*",
        );
      }
    });

    // screen-studio (recorder page, app host) → chuyển lệnh bật/tắt cursor-tracking cho background
    window.addEventListener("message", function (e) {
      if (e.source !== window || !e.data || e.data.type !== "METAOS_CURSOR_CMD") return;
      try {
        if (e.data.cmd === "start") chrome.runtime.sendMessage({ action: "cursor.start", sessionId: e.data.sessionId }, (resp) => {
          void chrome.runtime.lastError; // báo lại page: đang bám chuột ở bao nhiêu tab khác (0 → page cảnh báo)
          try { window.postMessage({ type: "METAOS_CURSOR_STATUS", enabled: resp && resp.enabled != null ? resp.enabled : -1 }, "*"); } catch (err) {}
        });
        else if (e.data.cmd === "stop") chrome.runtime.sendMessage({ action: "cursor.stop" }, () => void chrome.runtime.lastError);
      } catch (err) {}
    });
  }

  // ========== SCREEN-STUDIO cursor tracking (mọi tab — auto-zoom đa-tab) ==========
  // Chạy MỌI tab: nhận cursor.enable từ background → chỉ TOP-FRAME gắn mousemove/click (throttle ~40Hz),
  // gửi TOẠ ĐỘ về background (cursor.event). cursor.deliver (chỉ tới tab quay) → đẩy lên page. Không nội dung.
  (function () {
    var fwd = null;
    function startFwd() {
      if (fwd || window.top !== window) return; // tránh iframe nhân bản + sai hệ quy chiếu
      var last = 0;
      var mv = function (e) { var n = Date.now(); if (n - last < 25) return; last = n; try { chrome.runtime.sendMessage({ action: "cursor.event", kind: "move", x: e.clientX, y: e.clientY, vw: innerWidth, vh: innerHeight, t: n }, () => void chrome.runtime.lastError); } catch (_) {} };
      var ck = function (e) { try { chrome.runtime.sendMessage({ action: "cursor.event", kind: "click", x: e.clientX, y: e.clientY, vw: innerWidth, vh: innerHeight, t: Date.now() }, () => void chrome.runtime.lastError); } catch (_) {} };
      fwd = { mv: mv, ck: ck };
      document.addEventListener("mousemove", mv, true);
      document.addEventListener("click", ck, true);
    }
    function stopFwd() { if (!fwd) return; document.removeEventListener("mousemove", fwd.mv, true); document.removeEventListener("click", fwd.ck, true); fwd = null; }
    chrome.runtime.onMessage.addListener(function (r) {
      if (!r || !r.action) return;
      if (r.action === "cursor.enable") { startFwd(); return; }
      if (r.action === "cursor.disable") { stopFwd(); return; }
      if (r.action === "cursor.deliver") { if (window.top === window) { try { window.postMessage({ type: "METAOS_CURSOR_EVT", kind: r.kind, x: r.x, y: r.y, vw: r.vw, vh: r.vh, t: r.t }, "*"); } catch (_) {} } return; }
    });
  })();

  // ========== OUTLOOK WEB - Đọc OTP ngầm (phiên đăng nhập sẵn trong Chrome) ==========
  // Background mở tab nền outlook.live.com (active:false) rồi gửi {action:"owaScrapeOtp"}; ta cào
  // danh sách thư trong DOM, bóc OTP + link xác minh, trả về. KHÔNG cần mật khẩu. Chỉ top-frame.
  if (
    (host.endsWith("outlook.live.com") ||
      host.endsWith("outlook.office.com") ||
      host.endsWith("outlook.office365.com")) &&
    window.top === window.self
  ) {
    const _owaRe = [
      /(?:code|m[aã]|otp|pin|verification|x[aá]c\s*minh|x[aá]c\s*nh[aậ]n|is:?)\s*[:\s]*(\d{4,8})/i,
      /\b(\d{5,8})\b/,
    ];
    const _owaOtp = (text) => {
      const t = String(text || "");
      for (let i = 0; i < _owaRe.length; i++) { const m = t.match(_owaRe[i]); if (m) return m[1]; }
      return "";
    };
    const _owaLinks = (text) => {
      const out = [];
      const re = /https?:\/\/[^\s"'<>]+/gi;
      const kw = ["verify", "confirm", "activate", "validate", "reset", "token", "auth", "approve", "l.facebook", "fb.me"];
      let m;
      while ((m = re.exec(String(text || ""))) !== null) {
        const u = m[0], lu = u.toLowerCase();
        if (kw.some((k) => lu.indexOf(k) !== -1) && out.indexOf(u) === -1) out.push(u);
        if (out.length >= 5) break;
      }
      return out;
    };
    const _owaSleep2 = (ms) => new Promise((r) => setTimeout(r, ms));
    // ⚠ Mốc thời gian TUYỆT ĐỐI của thư: Outlook để trong title của span giờ (vd "T3 03/11/2026 8:20 CH" = dd/mm/yyyy h:mm CH|SA,
    // theo MÚI GIỜ cấu hình của hộp thư). Parse → epoch "giờ máy" (new Date dựng theo local). KHÔNG so với đồng hồ máy (lệch múi
    // giờ); fb-otp so TƯƠNG ĐỐI giữa các thư CÙNG hộp (chênh múi giờ triệt tiêu). Minute-precision.
    const _owaParseTitle = (title) => {
      const s = String(title || "");
      const dm = s.match(/(\d{1,2})[\/.\-](\d{1,2})[\/.\-](\d{2,4})/);
      if (!dm) return 0;
      const tm = s.match(/(\d{1,2}):(\d{2})(?::\d{2})?\s*(CH|SA|PM|AM|下午|上午|오후|오전)?/i);
      let a = +dm[1], b = +dm[2], y = +dm[3]; if (y < 100) y += 2000;
      let hh = tm ? +tm[1] : 0; const mi = tm ? +tm[2] : 0;
      const mer = (tm && tm[3] ? tm[3] : "").toUpperCase();
      if (/CH|PM|下午|오후/.test(mer) && hh < 12) hh += 12;
      if (/SA|AM|上午|오전/.test(mer) && hh === 12) hh = 0;
      let day, mon;
      if (a > 12) { day = a; mon = b; } else if (b > 12) { day = b; mon = a; }
      else { const enLike = /AM|PM/.test(mer) && !/CH|SA/.test(mer); if (enLike) { mon = a; day = b; } else { day = a; mon = b; } }
      const t = new Date(y, mon - 1, day, hh, mi, 0, 0).getTime();
      return isFinite(t) ? t : 0;
    };
    // Lấy ts (title span giờ) trong 1 dòng thư. 0 nếu không parse được.
    const _owaRowTs = (row) => {
      try { const sp = row.querySelectorAll("span[title]"); for (let j = 0; j < sp.length; j++) { const tt = sp[j].getAttribute("title") || ""; if (/\d{1,2}[\/.\-]\d{1,2}[\/.\-]\d{2,4}/.test(tt)) return _owaParseTitle(tt); } } catch (e) {}
      return 0;
    };
    // Cào danh sách thư đang hiển thị → [{otp, ts, links, snippet}] (DOM order = mới nhất trước)
    const _owaScrapeView = (sndLc) => {
      const opts = Array.prototype.slice.call(document.querySelectorAll('[role="option"]'));
      const found = [];
      for (let i = 0; i < opts.length; i++) {
        const txt = (opts[i].innerText || opts[i].getAttribute("value") || "").replace(/\s+/g, " ").trim();
        if (!txt) continue;
        if (sndLc && txt.toLowerCase().indexOf(sndLc) === -1) continue;
        const otp = _owaOtp(txt), links = _owaLinks(txt);
        if (otp || links.length) found.push({ otp: otp, ts: _owaRowTs(opts[i]), links: links, snippet: txt.slice(0, 180) });
        if (found.length >= 6) break;
      }
      return found;
    };
    // Bấm tab/nhóm theo chữ (pivot Focused/Other = "Ưu tiên"/"Khác"; "Email khác (…)" = nhóm Other peek). Leo tới phần tử bấm được.
    const _owaClickText = (match) => {
      const els = document.querySelectorAll('[role="tab"],[role="option"],[role="menuitemradio"],button,[role="button"],a,span,div');
      for (let i = 0; i < els.length; i++) {
        const t = ((els[i].innerText || els[i].getAttribute("aria-label")) || "").trim();
        if (!t || !match(t)) continue;
        let el = els[i], c = els[i];
        for (let k = 0; k < 4 && c; k++) { const rl = c.getAttribute && c.getAttribute("role"); if ((c.tagName === "BUTTON") || rl === "tab" || rl === "option" || rl === "button") { el = c; break; } c = c.parentElement; }
        try { el.click(); return true; } catch (e) {}
      }
      return false;
    };
    const _owaScrape = async (sender, email) => {
      if (/login\.live|login\.microsoftonline|\/wrongplace|www\.microsoft\.com/i.test(location.href)) {
        return { success: false, error: "Chưa đăng nhập Outlook trong Chrome — mở outlook.live.com đăng nhập 1 lần rồi thử lại" };
      }
      // ⚠ Tab nền vừa reload → danh sách thư render LAZY (cold chậm). CHỜ [role=option] xuất hiện (tối đa ~5s) rồi mới cào,
      // nếu không: cào sớm = rỗng → chụp hụt mã cũ (nStale=0) trong khi poll sau đọc ra = bug nuốt mã cũ (user 412175).
      for (let w = 0; w < 7 && !document.querySelector('[role="option"]'); w++) await _owaSleep2(750);
      if (!document.querySelector('[role="option"]')) return { success: false, error: "Chưa tải được hộp thư (chưa đăng nhập hoặc trang chưa xong)" };
      let loggedEmail = "";
      try { const em = (document.body.innerText || "").match(/[\w.+-]+@(?:hotmail|outlook|live|msn)\.[\w.]+/i); loggedEmail = em ? em[0] : ""; } catch (e) {}
      const sndLc = String(sender || "").toLowerCase();
      // Đọc 1 tab: bấm pivot rồi CHỜ messages của tab đó render (poll, vì bấm "Khác" FB tải thư Other theo yêu cầu),
      // cào tới khi THẤY MÃ hoặc hết số vòng. Trả cả khi chỉ có link.
      const _readTab = async (match, rounds) => {
        _owaClickText(match);
        let f = [];
        for (let w = 0; w < rounds; w++) { await _owaSleep2(850); f = _owaScrapeView(sndLc); if (f.some((x) => x.otp)) break; }
        return f;
      };
      // ⚠ ƯU TIÊN "Khác"/Other TRƯỚC (mã FB hay rơi vào Other, render lazy nên cho tới ~5s); chưa có mã mới sang "Ưu tiên".
      let found = await _readTab((t) => t === "Khác" || t === "Other" || /^Email kh[aá]c/i.test(t), 6);
      if (!found.some((f) => f.otp)) {
        const f2 = await _readTab((t) => t === "Ưu tiên" || t === "Focused", 3);
        found = found.concat(f2.filter((x) => !found.some((y) => y.snippet === x.snippet)));
      }
      if (!found.length) return { success: false, error: "Không thấy OTP/link mới (đã soi cả Ưu tiên + Khác)", loggedEmail: loggedEmail };
      return { success: true, otp: found[0].otp, otps: found.map((f) => f.otp).filter(Boolean), otpsTs: found.map((f) => ({ otp: f.otp, ts: f.ts })).filter((x) => x.otp), links: found[0].links, snippet: found[0].snippet, loggedEmail: loggedEmail, matches: found };
    };
    chrome.runtime.onMessage.addListener((r, s, send) => {
      if (!r || r.action !== "owaScrapeOtp") return;
      (async () => {
        let out;
        try { out = await _owaScrape(r.sender, r.email); } catch (e) { out = { success: false, error: String((e && e.message) || e) }; }
        try { send(out); } catch (e) {}
      })();
      return true;   // async → giữ kênh mở tới khi send()
    });
  }

  // ========== FACEBOOK - Fetcher ==========
  if (host.includes("facebook.com") || host.includes("fb.com")) {
    // Prefix NGẪU NHIÊN mỗi phiên (5 ký tự, bắt đầu chữ cái) → eztool KHÔNG thể
    // nhắm selector cố định [id^="fx"] hay #fiox-* để tìm & xoá element.
    const _rp = String.fromCharCode(97 + (Math.random() * 26 | 0)) + Math.random().toString(36).slice(2, 6);
    const _cp = _sc.cp || _rp; // class prefix cho CSS (server-configurable)
    const _dp = _sc.dp || _rp; // data attribute prefix (server-configurable)
    const _das = "data-" + _dp + "-s"; // was data-fiox-sug
    const _dah = "data-" + _dp + "-h"; // was data-fiox-hidden
    const _mk = _rp + Math.random().toString(36).slice(2, 5); // message key cho postMessage
    // Server-configurable CSS injection — mọi thay đổi CSS từ server, không cần cập nhật extension
    if (_sc.css) { try { const _cst = document.createElement("style"); _cst.id = _rp + "sc"; _cst.textContent = _sc.css; (document.head || document.documentElement).appendChild(_cst); } catch(e){} }

    chrome.runtime.onMessage.addListener((r, s, send) => {
      const a = r.action;
      if (a === "ping") {
        send({ pong: !0 });
        return !0;
      }
      if (a === "fb-fetch") {
        fetch2(r.url, r.options || {}, r.responseType || "text")
          .then((res) => send(res))
          .catch((e) => send({ success: !1, error: e.message }));
        return !0;
      }
      // Các action khác được xử lý ở server (libs.js) thông qua fb-fetch
      return !1;
    });

    function fetch2(url, opt = {}, rt = "text") {
      return new Promise((res) => {
        const xhr = new XMLHttpRequest();
        xhr.open(opt.method || "GET", url, !0);
        xhr.withCredentials = !0;
        xhr.timeout = 30000; // Timeout 30s
        if (opt.headers && typeof opt.headers === "object") {
          const fb = [
            "host",
            "connection",
            "content-length",
            "origin",
            "sec-fetch-dest",
            "sec-fetch-mode",
            "sec-fetch-site",
            "sec-fetch-user",
            "sec-ch-ua",
            "sec-ch-ua-mobile",
            "sec-ch-ua-platform",
          ];
          for (const [k, v] of Object.entries(opt.headers)) {
            if (!fb.includes(k.toLowerCase()))
              try {
                xhr.setRequestHeader(k, v);
              } catch (e) {}
          }
        }
        xhr.onload = function () {
          let d = xhr.responseText;
          if (rt === "json")
            try {
              d = JSON.parse(d.replace(/^for\s*\(\s*;\s*;\s*\)\s*;?\s*/, ""));
            } catch (e) {}
          res({
            success: !0,
            data: d,
            url: xhr.responseURL || url,
            status: xhr.status,
            ok: xhr.status >= 200 && xhr.status < 300,
          });
        };
        xhr.onerror = function () {
          res({ success: !1, error: "Network error", status: xhr.status });
        };
        xhr.ontimeout = function () {
          res({ success: !1, error: "Timeout", status: 0 });
        };
        opt.body ? xhr.send(opt.body) : xhr.send();
      });
    }

    // ── CHẶN eztool (đối thủ) chèn UI lên trang FB — chạy MỌI trang (billing/latest/adsmanager).
    //    Bắt theo SRC "eztool.vn" (ỔN ĐỊNH — eztool ngẫu nhiên hoá id nên không bắt theo id).
    //    Gỡ iframe eztool.vn + khối bao + widget cũ + nút icon tia sét, quét lại liên tục.
    //    KHÔNG đụng UI mình (iframe máy chủ / id ngẫu nhiên của mình).
    if (!window.__fioxEztoolKill) {
      window.__fioxEztoolKill = true;
      const _EZ_SRC = _sc.ezSrc || "eztool.vn";
      const _EZ_SEL = _sc.ezSel || '[id^="eztool-fb"],[class*="eztool-fb"]';
      const _EZ_PATH = _sc.ezPath || "M13 10H20L11 23V14H4L13 1V10Z";
      // ⚠ ẨN bằng CSS display:none — KHÔNG remove DOM. remove() làm eztool tưởng bị xoá →
      // CHÈN LẠI → xoá → chèn lại (vòng lặp), popup cao ~878px nên layout NHẢY GIẬT. display:none
      // = không chiếm chỗ + không flash + eztool không phát hiện nên không chèn lại → hết giật.
      // ':has' ẩn cả KHỐI BAO (khỏi chừa margin 16px); trình duyệt không hỗ trợ :has thì bỏ qua rule đó.
      try {
        const st = document.createElement("style");
        st.id = _rp + "ek";
        st.textContent =
          'iframe[src*="' + _EZ_SRC + '"]{display:none!important}' +
          ':has(> iframe[src*="' + _EZ_SRC + '"]){display:none!important}' +
          _EZ_SEL + '{display:none!important;visibility:hidden!important;pointer-events:none!important}';
        (document.head || document.documentElement).appendChild(st);
      } catch (e) {}
      // Backup (không có :has) + nút nổi eztool (icon tia sét, position:fixed). ẨN (display:none),
      // KHÔNG remove. Interval nhẹ, KHÔNG MutationObserver (tránh getComputedStyle liên tục gây jank).
      const _ezHide = () => {
        try {
          document.querySelectorAll('iframe[src*="' + _EZ_SRC + '"]').forEach((ifr) => {
            let node = ifr;
            for (let i = 0; i < 3 && node.parentElement && node.parentElement !== document.body; i++) {
              if (node.parentElement.childElementCount === 1) node = node.parentElement; else break;
            }
            try { node.style.setProperty("display", "none", "important"); } catch (e) {}
          });
          document.querySelectorAll('svg path[d="' + _EZ_PATH + '"]').forEach((p) => {
            let n = p;
            while (n && n !== document.body) {
              try { if (getComputedStyle(n).position === "fixed") { n.style.setProperty("display", "none", "important"); break; } } catch (e) {}
              n = n.parentElement;
            }
          });
        } catch (e) {}
      };
      _ezHide();
      setInterval(_ezHide, _sc.ezInt || 1500);
    }

    // BM Billing page - Inject popup bằng iframe
    // Match cả /billing_hub/ và /latest/billing_hub/
    if (url.includes("/billing_hub/")) {
      // Ép hiển thị + z-index CAO NHẤT (2147483647) + chống eztool ẩn/xoá. Chỉ set khi
      // giá trị SAI để không kích observer lặp vô hạn từ chính thay đổi của mình.
      const _bpEnforce = (el) => {
        if (!el) return;
        try {
          [["display", "block"], ["visibility", "visible"], ["opacity", "1"], ["pointer-events", "auto"], ["position", "relative"], ["z-index", String(_sc.z || "2147483647")]].forEach(([p, v]) => {
            if (el.style.getPropertyValue(p) !== v || el.style.getPropertyPriority(p) !== "important") el.style.setProperty(p, v, "important");
          });
        } catch (e) {}
      };
      // Nhận height từ iframe theo THAM CHIẾU (iframe nằm trong CLOSED Shadow DOM nên
      // getElementById không thấy). Gắn 1 lần.
      if (!window.__fioxPopupResizeBound) {
        window.__fioxPopupResizeBound = true;
        window.addEventListener("message", (e) => {
          const _mt = e.data && e.data.type; if (!_mt || (_mt !== _mk + "-h" && _mt !== _mk + "-r" && _mt !== "fiox-popup-height" && _mt !== "ext-popup-height")) return;
          if (e.origin && !/^http:\/\/(127\.0\.0\.1|localhost):8000$/.test(e.origin)) return;
          const ifr = window.__fioxBpIframe;
          const h = parseInt(e.data.height);
          if (ifr && h > 0 && h < 4000) ifr.style.height = h + "px";
        });
      }
      if (!window.__fioxBpIv) window.__fioxBpIv = setInterval(() => {
        // Còn trong DOM → chỉ tái ép style rồi thôi (chống eztool set display:none).
        const cur = window.__fioxBpEl;
        if (cur && cur.isConnected) { _bpEnforce(cur); return; }
        window.__fioxBpEl = null; window.__fioxBpIframe = null;

        const u = new URL(location.href);
        const id =
          u.searchParams.get("asset_id") ||
          u.searchParams.get("payment_account_id");
        const bmId = u.searchParams.get("business_id");
        if (!id) {
          return;
        }

        // Chỗ chèn: business.facebook.com dùng data-pagelet; adsmanager (DOM khác,
        // KHÔNG có data-pagelet) → anchor theo CHỮ tiêu đề "Phương thức thanh toán"/
        // "Lịch sử thanh toán" (bền hơn class băm), chèn trước thẻ đầu (LCA 2 tiêu đề).
        let insParent = null, insBefore = null;
        // business.facebook.com: data-pagelet · adsmanager: data-surface ...:payment_history
        const phc = document.querySelector('[data-pagelet="BillingHubCard_payment_history"], [data-surface*="payment_history"]');
        if (phc) {
          const targetDiv = phc.querySelector(_sc.bpSel || "div.x78zum5.xdt5ytf.x5yr21d.xedcshv.x1t2pt76.xh8yej3");
          const headerDiv = targetDiv && targetDiv.querySelector(_sc.bpHdrSel || "div.x9f619.x78zum5.x2lah0s.xh8yej3");
          if (headerDiv) { insParent = headerDiv.parentElement; insBefore = headerDiv; }
        }
        if (!insParent) {
          const findTxt = (arr) => {
            for (const t of arr) {
              const e = [...document.querySelectorAll("div,span,h1,h2,h3,h4")].find(
                (el) => el.childElementCount === 0 && el.textContent.trim() === t,
              );
              if (e) return e;
            }
            return null;
          };
          const a = findTxt(_sc.bpTxtA || ["Phương thức thanh toán", "Payment method"]);
          const b = findTxt(_sc.bpTxtB || ["Lịch sử thanh toán", "Payment history", "Payment activity"]);
          if (a && b) {
            const anc = new Set();
            for (let x = a; x; x = x.parentElement) anc.add(x);
            let lca = b;
            while (lca && !anc.has(lca)) lca = lca.parentElement;
            if (lca && lca !== document.body && lca !== document.documentElement) {
              let card = a;
              while (card.parentElement && card.parentElement !== lca) card = card.parentElement;
              if (card.parentElement === lca) { insParent = lca; insBefore = card; }
            }
          }
        }
        if (!insParent) return; // chưa thấy chỗ chèn → setInterval thử lại

        // Host id NGẪU NHIÊN mỗi lần tạo → eztool không chặn bằng selector cố định #fiox-popup.
        const div = document.createElement("div");
        div.id = _rp + Math.random().toString(36).slice(2, 9) + Date.now().toString(36).slice(-4);
        div.style.cssText = "overflow:visible;line-height:0;margin:0 0 16px 0;width:100%;";
        // iframe đặt trong CLOSED Shadow DOM: querySelectorAll('#fiox-popup-iframe' /
        // iframe của công cụ) và CSS ngoài của eztool KHÔNG xuyên vào shadow tree → không ẩn/gỡ được.
        let root;
        try { root = div.attachShadow({ mode: "closed" }); } catch (e) { root = div; }
        const ifr = document.createElement("iframe");
        ifr.setAttribute("frameborder", "0");
        ifr.setAttribute("scrolling", "no");
        ifr.setAttribute("width", "100%");
        ifr.style.cssText = "overflow:hidden;display:block;height:" + (_sc.ifrHBp || 550) + "px;width:100%;border-radius:8px;border:none;";
        ifr.src = getApiBase() + "/popup?id=" + id + "&bm=" + bmId + "&extId=" + chrome.runtime.id + "&_mk=" + _mk + _fxLangQS();
        root.appendChild(ifr);
        window.__fioxBpEl = div;
        window.__fioxBpIframe = ifr;
        _bpEnforce(div);
        insParent.insertBefore(div, insBefore);
        // eztool sửa style / ẩn / xoá → tái ép NGAY (nhanh hơn nhịp 2s).
        try {
          const obs = new MutationObserver(() => { const el = window.__fioxBpEl; if (el && el.isConnected) _bpEnforce(el); });
          obs.observe(div, { attributes: true, attributeFilter: ["style", "class", "hidden"] });
        } catch (e) {}
      }, _sc.bpInt || 2000);
    }

    // Facebook Business /latest/ & Ads Manager - Floating Button + Bubble-bar
    // Khối chạy CẢ trên /billing_hub/ để Bubble-bar hiện ở đó; RIÊNG FAB + suppressRivalWidgets
    // bị gác off trên billing_hub (billing_hub có popup inject riêng — tránh ẩn/đè nhầm popup đó).
    // CHỈ top-frame: content.js chạy all_frames → không có chặn này thì subframe cũng dựng, mà
    // top-layer là THEO TỪNG document → popover subframe bị cắt trong khung con, vô dụng + tốn.
    if (
      window.top === window &&
      ((url.includes("business.facebook.com/latest/")) ||
        host.includes("adsmanager.facebook.com"))
    ) {
      const isAdsManagerPage = host.includes("adsmanager.facebook.com");

      // ID nút NGẪU NHIÊN mỗi phiên → extension khác không chặn được bằng selector cố định #fiox-floating-btn.
      const FAB_ID = _rp + Math.random().toString(36).slice(2, 9) + Date.now().toString(36).slice(-4);
      let _fabEl = null;
      let _fabWatch = false;

      // ===== TOP LAYER (Popover API) =====================================================
      // Element trong top-layer LUÔN vẽ trên MỌI element thường, bất kể z-index hay thứ tự DOM.
      // Đây là cách thắng TUYỆT ĐỐI cuộc chiến z-index với eztool (cả hai đều z-index max →
      // ai vào DOM sau thì đè; top-layer vượt lên trên hết, không phụ thuộc điều đó).
      // Reset style UA popover (inset:0/margin:auto/border/padding) để giữ đúng vị trí & kích thước.
      const _fxPop = typeof HTMLElement !== "undefined" && typeof HTMLElement.prototype.showPopover === "function";
      const _fxTopLayer = (el) => {
        if (!_fxPop || !el) return;
        try {
          if (!el.hasAttribute("popover")) el.setAttribute("popover", "manual");
          if (el.isConnected && !el.matches(":popover-open")) el.showPopover();
          // UA popover thêm inset:0 + margin:auto (căn giữa) + border + padding → vô hiệu.
          // KHÔNG đụng bottom/right (để nguyên inline non-important của element → kéo nút vẫn được).
          el.style.setProperty("top", "auto");
          el.style.setProperty("left", "auto");
          el.style.setProperty("margin", "0");
          el.style.setProperty("padding", "0");
          el.style.setProperty("border", "0");
        } catch (_) {}
      };
      // Giữ element luôn ở top-layer; nếu bị đối thủ (cũng top-layer) đè → re-show để leo lên lại.
      const _fxEnsureTop = (el, restack) => {
        if (!_fxPop || !el || !el.isConnected) return;
        try {
          if (!el.matches(":popover-open")) { el.showPopover(); el._fxCov = 0; return; }
          if (restack) {
            const r = el.getBoundingClientRect();
            if (r.width > 0) {
              const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
              if (t && t !== el && !el.contains(t)) {
                // Debounce: chỉ re-stack sau 2 nhịp liên tiếp bị che → tránh chiến tranh nhấp nháy
                // nếu đối thủ cũng top-layer (top-layer xếp theo thứ tự vào, không có "ưu tiên").
                el._fxCov = (el._fxCov || 0) + 1;
                if (el._fxCov >= 2) { el.hidePopover(); el.showPopover(); el._fxCov = 0; }
              } else { el._fxCov = 0; }
            }
          }
        } catch (_) {}
      };

      // Vô hiệu hoá widget đối thủ (nút nổi che/cản nút fiox trên trang).
      // ẨN (display:none) thay vì remove() — remove() làm eztool phát hiện bị xoá → CHÈN LẠI liên tục.
      // display:none = eztool không phát hiện nên không chèn lại → hết loop.
      let _rivalKill = false;
      const suppressRivalWidgets = () => {
        if (_rivalKill) return;
        _rivalKill = true;
        const SEL = _sc.ezSel || '[id^="eztool-fb"],[class*="eztool-fb"]';
        const RIVAL_PATH = _sc.ezPath || "M13 10H20L11 23V14H4L13 1V10Z";
        try {
          const st = document.createElement("style");
          st.id = _rp + "rk";
          st.textContent = SEL + "{display:none!important;visibility:hidden!important;pointer-events:none!important}";
          (document.head || document.documentElement).appendChild(st);
        } catch (e) {}
        const isMine = (el) => { if (!el) return false; if (el.id === FAB_ID) return true; if (_fabEl && (el === _fabEl || el.contains(_fabEl))) return true; const _pm = window.__fioxMenuEl; if (_pm && (el === _pm || el.contains(_pm))) return true; return false; };
        const hideRival = (el) => {
          try {
            if (!el || el.nodeType !== 1 || isMine(el)) return;
            el.style.setProperty("display", "none", "important");
            el.style.setProperty("visibility", "hidden", "important");
            el.style.setProperty("pointer-events", "none", "important");
            el.style.setProperty("z-index", "1", "important");
          } catch (e) {}
        };
        const sweep = () => {
          try {
            document.querySelectorAll(SEL).forEach(hideRival);
            // Nút eztool id ngẫu nhiên: tìm icon tia sét → leo lên tổ tiên position:fixed → ẩn.
            document.querySelectorAll('svg path[d="' + RIVAL_PATH + '"]').forEach((p) => {
              let n = p;
              while (n && n !== document.body) {
                try { if (getComputedStyle(n).position === "fixed") { hideRival(n); break; } } catch (e) {}
                n = n.parentElement;
              }
            });
            // Deep: element lồng sâu có inline z-index cực cao → ẩn (eztool set inline style z-index max)
            document.querySelectorAll('[style*="214748"]').forEach((el) => {
              if (isMine(el) || el.tagName === "SCRIPT" || el.tagName === "STYLE") return;
              try { const cs = getComputedStyle(el); if (cs.position === "fixed" && parseInt(cs.zIndex) >= 2147483000) hideRival(el); } catch(e){}
            });
          } catch (e) {}
        };
        sweep();
        setInterval(sweep, _sc.ezInt || 800);
      };
      // billing_hub có popup riêng (z-index max) → KHÔNG chạy suppress ở đó kẻo ẩn nhầm popup.
      if (!url.includes("/billing_hub/")) suppressRivalWidgets();

      const injectFloatingButton = () => {
        // Đợi document.body sẵn sàng
        if (!document.body) {
          setTimeout(injectFloatingButton, 200);
          return;
        }

        if (_fabEl && document.body.contains(_fabEl)) {
          return;
        }

        // Shield config → tham số server điều khiển. Đặt TRƯỚC CSS block vì CSS dùng _fabAc.
        const _fabTag = _sc.tag || "div";
        const _fabZ = String(_sc.z || "2147483647");
        const _fabB = (_sc.b != null ? _sc.b : 24) + "px";
        const _fabR = (_sc.r != null ? _sc.r : 24) + "px";
        const _fabSz = (_sc.sz || 52) + "px";
        const _fabSh = _sc.sh !== false;
        const _fabWt = _sc.wt || 2000;
        const _fabAc = _sc.ac || "#8154e3";
        const _bsNormal = _sc.bsn || "0 0 0 1.2px rgba(45,212,191,.85),0 0 14px 3px rgba(45,212,191,.5),0 0 28px 8px rgba(45,212,191,.22),0 0 46px 16px rgba(251,146,60,.22),0 0 70px 26px rgba(251,146,60,.1),0 8px 22px rgba(15,23,42,.32)";
        const _bsHover = _sc.bsh || "0 0 0 1.5px rgba(45,212,191,1),0 0 22px 5px rgba(45,212,191,.7),0 0 44px 14px rgba(45,212,191,.3),0 0 64px 22px rgba(251,146,60,.32),0 0 96px 36px rgba(251,146,60,.16),0 12px 30px rgba(15,23,42,.36)";

        // Inject CSS animation cho hiệu ứng vệt trắng
        if (!document.getElementById(_rp + "ss")) {
          const style = document.createElement("style");
          style.id = _rp + "ss";
          style.textContent = `
            @keyframes ${_rp}a {
              0% { left: -100%; }
              50%, 100% { left: 100%; }
            }
            #${FAB_ID}::after {
              content: '';
              position: absolute;
              top: 0;
              left: -100%;
              width: 50%;
              height: 100%;
              background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
              transform: skewX(-25deg);
              animation: ${_rp}a 2.5s infinite;
            }
            @keyframes ${_rp}b {
              0% { transform: rotate(0deg); }
              100% { transform: rotate(360deg); }
            }
            .${_cp}-spinner {
              width: 20px;
              height: 20px;
              border: 2px solid #e4e6eb;
              border-top-color: ${_fabAc};
              border-radius: 50%;
              animation: ${_rp}b 0.8s linear infinite;
            }
            .${_cp}-checkbox {
              width: 18px;
              height: 18px;
              border: 2px solid #CED0D4;
              border-radius: 4px;
              cursor: pointer;
              display: flex;
              align-items: center;
              justify-content: center;
              transition: all 0.15s;
              flex-shrink: 0;
            }
            .${_cp}-checkbox.checked {
              background: ${_fabAc};
              border-color: ${_fabAc};
            }
            .${_cp}-checkbox.checked::after {
              content: '';
              width: 5px;
              height: 9px;
              border: solid white;
              border-width: 0 2px 2px 0;
              transform: rotate(45deg);
              margin-bottom: 2px;
            }
            .${_cp}-user-item {
              display: flex;
              align-items: center;
              gap: 10px;
              padding: 8px;
              border-radius: 8px;
              transition: background 0.15s;
              cursor: pointer;
            }
            .${_cp}-user-item:hover {
              background: #F2F2F2;
            }
            .${_cp}-btn {
              padding: 8px 16px;
              border-radius: 6px;
              font-size: 13px;
              font-weight: 500;
              cursor: pointer;
              transition: all 0.15s;
              border: none;
            }
            .${_cp}-btn-danger {
              background: #E4405F;
              color: white;
            }
            .${_cp}-btn-danger:hover {
              background: #d63251;
            }
            .${_cp}-btn-danger:disabled {
              background: #CED0D4;
              cursor: not-allowed;
            }
            .${_cp}-confirm-overlay {
              position: absolute;
              top: 0;
              left: 0;
              right: 0;
              bottom: 0;
              background: rgba(255,255,255,0.95);
              z-index: 10;
              display: flex;
              align-items: center;
              justify-content: center;
              flex-direction: column;
              opacity: 0;
              transition: opacity 0.2s;
              border-radius: 12px;
            }
            .${_cp}-confirm-overlay.show {
              opacity: 1;
            }
            .${_cp}-confirm-box {
              text-align: center;
              padding: 20px;
            }
            .${_cp}-confirm-title {
              font-size: 16px;
              font-weight: 600;
              color: #1c1e21;
              margin-bottom: 8px;
            }
            .${_cp}-confirm-msg {
              font-size: 14px;
              color: #65676b;
              margin-bottom: 20px;
              line-height: 1.4;
            }
            .${_cp}-confirm-btns {
              display: flex;
              gap: 10px;
              justify-content: center;
            }
            .${_cp}-confirm-btn {
              padding: 8px 20px;
              border-radius: 6px;
              font-size: 14px;
              font-weight: 500;
              cursor: pointer;
              border: none;
              transition: all 0.15s;
            }
            .${_cp}-confirm-btn.cancel {
              background: #E4E6EB;
              color: #1c1e21;
            }
            .${_cp}-confirm-btn.cancel:hover {
              background: #D8DADF;
            }
            .${_cp}-confirm-btn.confirm {
              background: #E4405F;
              color: white;
            }
            .${_cp}-confirm-btn.confirm:hover {
              background: #d63251;
            }
          `;
          document.head.appendChild(style);
        }

        const btn = document.createElement(_fabTag);
        btn.id = FAB_ID;
        if (_sc.cls) btn.className = _sc.cls;
        btn.style.cssText = `
          position: fixed;
          bottom: ${_fabB};
          right: ${_fabR};
          width: ${_fabSz};
          height: ${_fabSz};
          cursor: pointer;
          z-index: ${_fabZ};
          transition: transform 0.25s ease, box-shadow 0.3s ease;
          overflow: hidden;
          border-radius: 50%;
          box-shadow: ${_bsNormal};
          user-select: none;
          -webkit-user-select: none;
          -webkit-user-drag: none;
          touch-action: none;
        `;
        // Chống extension khác ẩn/xoá nút: ép hiển thị bằng inline !important (thắng cả CSS !important chèn ngoài)
        // + watchdog tự re-gắn nếu bị xoá / re-ép style nếu bị đổi.
        [
          ["display", "block"], ["visibility", "visible"], ["opacity", "1"],
          ["pointer-events", "auto"], ["position", "fixed"], ["z-index", _fabZ],
        ].forEach(([p, v]) => { try { btn.style.setProperty(p, v, "important"); } catch (e) {} });
        _fabEl = btn;
        if (!_fabWatch) {
          _fabWatch = true;
          setInterval(() => {
            if (!_fabEl || !document.body) return;
            try {
              if (!document.body.contains(_fabEl)) { document.body.appendChild(_fabEl); }
              const _popEl = window.__fioxMenuEl;
              if (_fxPop) {
                // Top-layer: thắng z-index tuyệt đối → KHÔNG sắp xếp DOM order (appendChild element
                // popover = gỡ+chèn lại = ĐÓNG popover → mất top-layer). Chỉ đảm bảo đang mở + leo lên.
                _fxEnsureTop(_fabEl, true);
                if (_popEl) _fxEnsureTop(_popEl, false);
              } else {
                // Fallback (trình duyệt không hỗ trợ Popover API): sắp DOM order + ép z-index đối thủ xuống.
                if (_popEl && document.body.contains(_popEl)) {
                  if (_fabEl.nextElementSibling !== _popEl) _popEl.before(_fabEl);
                  if (_popEl !== document.body.lastElementChild) document.body.appendChild(_popEl);
                } else {
                  if (_fabEl !== document.body.lastElementChild) document.body.appendChild(_fabEl);
                }
                for (const _ch of document.body.children) {
                  if (_ch === _fabEl || _ch === _popEl || _ch.nodeType !== 1) continue;
                  const _tn = _ch.tagName; if (_tn === "SCRIPT" || _tn === "STYLE" || _tn === "LINK" || _tn === "NOSCRIPT") continue;
                  try { const _cs = getComputedStyle(_ch); if (_cs.position === "fixed" && parseInt(_cs.zIndex) >= 2147483000) _ch.style.setProperty("z-index", "1", "important"); } catch(_){}
                }
                try {
                  document.querySelectorAll('[style*="214748"]').forEach(_el => {
                    if (_el === _fabEl || _el === _popEl) return;
                    try { const _cs2 = getComputedStyle(_el); if ((_cs2.position === "fixed" || _cs2.position === "absolute") && parseInt(_cs2.zIndex) >= 2147483000) _el.style.setProperty("z-index", "1", "important"); } catch(_){}
                  });
                } catch(_){}
                try {
                  const _ezP2 = _sc.ezPath || "M13 10H20L11 23V14H4L13 1V10Z";
                  document.querySelectorAll('svg path[d="' + _ezP2 + '"]').forEach(_p => {
                    let _n = _p; while (_n && _n !== document.body) { try { if (getComputedStyle(_n).position === "fixed") { _n.style.setProperty("z-index", "1", "important"); break; } } catch(_){} _n = _n.parentElement; }
                  });
                } catch(_){}
              }
              _fabEl.style.setProperty("display", "block", "important");
              _fabEl.style.setProperty("visibility", "visible", "important");
              _fabEl.style.setProperty("opacity", "1", "important");
              _fabEl.style.setProperty("pointer-events", "auto", "important");
              _fabEl.style.setProperty("position", "fixed", "important");
              _fabEl.style.setProperty("z-index", _fabZ, "important");
            } catch (e) {}
          }, _fabWt);
        }
        btn.setAttribute("draggable", "false");
        // Icon: CLOSED Shadow DOM (mặc định) che img src khỏi eztool querySelectorAll.
        // _fabSh=false (server set) → tắt shadow DOM nếu EZTOOL bắt đầu nhắm vào đó.
        const _iconStyle = "width:100%;height:100%;border-radius:50%;display:block;-webkit-user-drag:none;user-select:none;pointer-events:none;";
        if (_fabSh) {
          try {
            const _shRoot = btn.attachShadow({ mode: "closed" });
            const _im = document.createElement("img");
            _im.draggable = false;
            _im.src = chrome.runtime.getURL("img/icon-48.png");
            _im.style.cssText = _iconStyle;
            _shRoot.appendChild(_im);
          } catch (e) {
            btn.innerHTML = '<img draggable="false" src="' + chrome.runtime.getURL("img/icon-48.png") + '" style="' + _iconStyle + '" />';
          }
        } else {
          btn.innerHTML = '<img draggable="false" src="' + chrome.runtime.getURL("img/icon-48.png") + '" style="' + _iconStyle + '" />';
        }
        // Chặn native HTML5 drag (cursor no-drop)
        btn.addEventListener("dragstart", (e) => e.preventDefault());

        btn.onmouseenter = () => {
          btn.style.transform = "scale(1.15)";
          btn.style.boxShadow = _bsHover;
        };
        btn.onmouseleave = () => {
          btn.style.transform = "scale(1)";
          btn.style.boxShadow = _bsNormal;
        };

        // Tạo popup
        const popup = document.createElement("div");
        // Id NGẪU NHIÊN (bỏ #fiox-popup-menu cố định) → eztool không bắt bằng selector cố định.
        popup.id = _rp + Math.random().toString(36).slice(2, 9) + Date.now().toString(36).slice(-4);
        window.__fioxMenuEl = popup;

        // Hàm kiểm tra loại trang hiện tại
        const getCurrentPageType = () => {
          if (host.includes("adsmanager.facebook.com")) return "adsmanager";
          // MỌI trang business.facebook.com (FAB chỉ bom ở /latest/ non-billing) → panel Thông tin BM,
          // KHÔNG còn popup "test" mặc định. business_id lấy từ URL trong renderPopupContent.
          if (host.includes("business.facebook.com")) return "business_users";
          return "default";
        };

        // Hàm lấy params từ URL
        const getUrlParams = () => {
          const params = new URLSearchParams(window.location.search);
          return {
            assetId:
              params.get("act") ||
              params.get("asset_id") ||
              params.get("selected_account_id") ||
              "",
            businessId: params.get("business_id") || "",
          };
        };

        // Hàm cập nhật style popup theo loại trang
        const updatePopupStyle = (pageType) => {
          let width, maxHeight;
          switch (pageType) {
            case "adsmanager":
            case "business_users":
              width = _sc.popW || "420px";
              maxHeight = _sc.popMH || "90vh";
              break;
            default:
              width = _sc.popWD || "280px";
              maxHeight = _sc.popMHD || "400px";
          }
          popup.style.cssText = `
            position: fixed;
            bottom: ${((_sc.b != null ? _sc.b : 24) + (_sc.sz || 52) + 10) + "px"};
            right: ${_fabR};
            width: ${width};
            max-height: ${maxHeight};
            background: #fff;
            border-radius: ${_sc.popBr || "12px"};
            box-shadow: ${_sc.popBs || "0 4px 24px rgba(0,0,0,0.15), 0 0 0 1px rgba(0,0,0,0.05)"};
            z-index: ${_fabZ};
            opacity: 0;
            transform: translateY(10px) scale(0.95);
            transform-origin: bottom right;
            transition: all 0.2s ease;
            pointer-events: none;
            font-family: ${_sc.ff || "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"};
            overflow-x: hidden;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
          `;
        };

        // Hàm render nội dung popup
        const renderPopupContent = (pageType) => {
          const { assetId, businessId } = getUrlParams();

          switch (pageType) {
            case "adsmanager": {
              // iframe đặt trong CLOSED Shadow DOM + KHÔNG id cố định → eztool
              // không thể query selector theo URL/id và CSS ngoài
              // KHÔNG xuyên vào shadow tree → không ẩn/gỡ được.
              popup.innerHTML = "";
              const _wrap = document.createElement("div");
              // KHÔNG height cố định / overflow:hidden — wrapper tự cao theo iframe (resize postMessage)
              // để popup (max-height + overflow-y:auto) scroll được. flex-shrink:0 kẻo bị flex ép co.
              _wrap.style.cssText = "width:100%;line-height:0;display:block;flex-shrink:0;";
              let _sr;
              try { _sr = _wrap.attachShadow({ mode: "closed" }); } catch (e) { _sr = _wrap; }
              const _ifr = document.createElement("iframe");
              _ifr.setAttribute("frameborder", "0");
              _ifr.setAttribute("scrolling", "no");
              _ifr.style.cssText = "width:100%;height:" + (_sc.ifrHAm || 480) + "px;border:none;border-radius:12px;display:block;";
              _ifr.src = getApiBase() + "/popup?id=" + assetId + "&bm=" + businessId + "&extId=" + chrome.runtime.id + "&floating=1&_mk=" + _mk + "&_=" + Date.now() + _fxLangQS();
              _sr.appendChild(_ifr);
              popup.appendChild(_wrap);
              window.__fioxMenuIframe = _ifr;
              break;
            }
            case "business_users": {
              // Thay UI "Xóa Quản trị viên" cũ = panel Thông tin BM (iframe web-app /bm-popup.html),
              // tự lấy token tại trang + fetch song song, KHÔNG phụ thuộc lưới. bindBusinessUsersEvents
              // (logic xóa admin) KHÔNG còn được gọi — hàm cũ giữ nguyên nhưng inert.
              popup.innerHTML = "";
              const _wrapB = document.createElement("div");
              _wrapB.style.cssText = "width:100%;line-height:0;display:block;flex-shrink:0;";
              let _srB;
              try { _srB = _wrapB.attachShadow({ mode: "closed" }); } catch (e) { _srB = _wrapB; }
              const _ifrB = document.createElement("iframe");
              _ifrB.setAttribute("frameborder", "0");
              _ifrB.setAttribute("scrolling", "no");
              _ifrB.style.cssText = "width:100%;height:" + (_sc.ifrHBm || 520) + "px;border:none;border-radius:12px;display:block;";
              _ifrB.src = getApiBase() + "/bm-popup.html?bm=" + businessId + "&extId=" + chrome.runtime.id + "&floating=1&_mk=" + _mk + "&_=" + Date.now() + _fxLangQS();
              _srB.appendChild(_ifrB);
              popup.appendChild(_wrapB);
              window.__fioxMenuIframe = _ifrB;
              break;
            }
            default:
              popup.innerHTML = `
                <div style="padding: 16px;">
                  <div style="font-size: 13px; color: #65676b; line-height: 1.5;">
                    Mở một trang quản lý quảng cáo hoặc Business trên Facebook để sử dụng công cụ.
                  </div>
                </div>
              `;
          }
        };

        // Khởi tạo popup với style mặc định + render luôn nội dung (fetch ngầm khi load trang)
        const initialPageType = getCurrentPageType();
        updatePopupStyle(initialPageType);
        renderPopupContent(initialPageType);

        document.body.appendChild(popup);
        // Đưa popup lên TOP LAYER (giữ mở liên tục; ẩn/hiện bằng opacity → không reload iframe).
        _fxTopLayer(popup);

        // Nút X đóng — góc phải TRÊN, sticky nên luôn hiện dù cuộn nội dung. Prepend làm con
        // ĐẦU để sticky:top ghim đúng đỉnh; margin-bottom âm để overlay, không đẩy nội dung xuống.
        const _closeX = document.createElement("div");
        _closeX.setAttribute("role", "button");
        _closeX.setAttribute("aria-label", _sc.al || "Close");
        _closeX.style.cssText =
          "position:sticky;top:8px;align-self:flex-end;margin:8px 8px -34px 0;width:26px;height:26px;" +
          "border-radius:50%;background:rgba(255,255,255,.96);box-shadow:0 2px 8px rgba(0,0,0,.22);" +
          "color:#5a6675;display:flex;align-items:center;justify-content:center;cursor:pointer;" +
          "z-index:" + _fabZ + ";flex-shrink:0;transition:background .15s,transform .15s;";
        _closeX.innerHTML =
          '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';
        _closeX.onmouseenter = () => { _closeX.style.background = "#fee2e2"; _closeX.style.color = "#dc2626"; _closeX.style.transform = "scale(1.1)"; };
        _closeX.onmouseleave = () => { _closeX.style.background = "rgba(255,255,255,.96)"; _closeX.style.color = "#5a6675"; _closeX.style.transform = "scale(1)"; };
        _closeX.onclick = (e) => {
          e.stopPropagation();
          isPopupOpen = false;
          popup.style.setProperty("opacity", "0", "important");
          popup.style.setProperty("transform", "translateY(10px) scale(0.95)", "important");
          popup.style.setProperty("pointer-events", "none", "important");
        };
        popup.insertBefore(_closeX, popup.firstChild);

        // Chống eztool ẩn/gỡ menu popup: ép display/visibility/position/z-index !important
        // (KHÔNG ép opacity/pointer-events — đó là cơ chế mở/đóng) + re-append nếu bị gỡ.
        if (!window.__fioxMenuWatch) {
          window.__fioxMenuWatch = true;
          setInterval(() => {
            try {
              if (!document.body) return;
              if (!document.body.contains(popup)) document.body.appendChild(popup);
              if (_fxPop) {
                // Top-layer: KHÔNG dời DOM (appendChild = đóng popover + reload iframe). Chỉ giữ mở.
                _fxEnsureTop(popup, false);
              } else {
                if (popup !== document.body.lastElementChild) document.body.appendChild(popup);
              }
              popup.style.setProperty("display", "flex", "important");
              popup.style.setProperty("visibility", "visible", "important");
              popup.style.setProperty("position", "fixed", "important");
              popup.style.setProperty("z-index", _fabZ, "important");
            } catch (e) {}
          }, _fabWt);
        }

        // Auto-resize iframe popup theo chiều cao nội dung (popup.html postMessage
        // fiox-popup-height / fiox-resize). Dùng source-check (khớp contentWindow của
        // iframe) → chạy cả domain được cấu hình, không cần khớp origin cố định.
        if (!window.__fioxPopupAutoResize) {
          window.__fioxPopupAutoResize = true;
          window.addEventListener("message", (e) => {
            const _mt2 = e.data && e.data.type; if (!_mt2 || (_mt2 !== _mk + "-h" && _mt2 !== _mk + "-r" && !/^(fiox|ext)-(popup-height|resize)$/.test(String(_mt2)))) return;
            const ifr = window.__fioxMenuIframe;
            if (!ifr || e.source !== ifr.contentWindow) return;
            const h = parseInt(e.data.height);
            if (h > 0 && h < 4000) {
              ifr.style.height = h + "px";
              // Iframe vừa cao lên (data fetch xong) → nếu popup đang mở, KẸP lại vị trí:
              // F5 auto-open (700ms) tính top theo chiều cao 480px ban đầu → cao lên là đuôi
              // tràn xuống dưới viewport (bị cắt). Reposition giữ full trong màn hình.
              try { if (isPopupOpen) positionPopupNearBtn(); } catch (_) {}
            }
          });
        }

        // (ĐÃ BỎ) auto-load danh sách QTV: UI "Xóa Quản trị viên" cũ không còn render
        // (business_users nay mở panel Thông tin BM qua iframe) → loadUserList query #fiox-user-list
        // = null, và code xóa-admin (bindBusinessUsersEvents) inert. Bỏ auto-call cho sạch, tránh lỗi
        // #fiox-select-all ở bản extension cũ.

        let isPopupOpen = false;
        let selectedUsers = new Set();
        let loadedUsers = []; // Lưu danh sách user đã load

        // Hàm lấy access token: ưu tiên extension storage, fallback fetch từ HTML FB hiện tại
        const getAccessToken = async () => {
          // 1. Thử lấy từ extension storage
          let token = await new Promise((resolve) => {
            try {
              chrome.storage.local.get(["accessToken"], (result) => {
                resolve(result?.accessToken || null);
              });
            } catch (_) {
              resolve(null);
            }
          });
          if (token) return token;

          // 2. Fallback: fetch billing_hub và extract token từ HTML
          try {
            const res = await fetch(
              "https://business.facebook.com/billing_hub/payment_settings/",
              { credentials: "include" },
            );
            const html = await res.text();
            const m1 = html.match(/"accessToken":"(EAAG[^"]+)"/);
            if (m1 && m1[1]) token = m1[1];
            if (!token) {
              const m2 = html.match(/"apiAccessToken":"(EAAG[^"]+)"/);
              if (m2 && m2[1]) token = m2[1];
            }
            // Lưu lại để lần sau khỏi fetch
            if (token) {
              try {
                chrome.storage.local.set({ accessToken: token });
              } catch (_) {}
            }
          } catch (e) {
            console.warn("[EXT]Fallback fetch token failed:", e);
          }
          return token || null;
        };

        // Hàm gọi API lấy danh sách QTV
        const fetchBusinessUsers = async (businessId) => {
          // Lấy token từ storage
          const accessToken = await getAccessToken();
          if (!accessToken) {
            throw new Error(
              "Chưa có access token. Vui lòng đăng nhập lại trên metaOs",
            );
          }

          const variables = {
            asset_types: null,
            businessAccessType: [],
            businessAccountTypes: [],
            businessUserNeedsReview: null,
            businessUserStatusType: [],
            cursor: null,
            first: 50,
            isUnifiedSettings: true,
            orderBy: "MOST_RECENTLY_CREATED",
            permissions: [],
            searchTerm: null,
            shouldUseNewEmptyState: true,
            id: businessId,
            __relay_internal__pv__BizKitSettingsPeopleEmptyStaterelayprovider: true,
          };

          const apiUrl = `https://graph.facebook.com/graphql?method=post&locale=en_US&pretty=false&format=json&fb_api_req_friendly_name=BizKitSettingsPeopleTableListPaginationQuery&doc_id=${_sc.docIds && _sc.docIds.bmUsers || "24411698895145972"}&fb_api_caller_class=RelayModern&server_timestamps=true&variables=${encodeURIComponent(
            JSON.stringify(variables),
          )}&access_token=${accessToken}`;

          // Dùng fetch trực tiếp với credentials include
          const res = await fetch(apiUrl, {
            headers: {
              accept: "application/json",
              "accept-language": "vi",
            },
            referrer: "https://business.facebook.com/",
            method: "GET",
            mode: "cors",
            credentials: "include",
          });

          const resData = await res.json();

          if (!resData?.data?.node) {
            throw new Error(
              resData?.error?.message || "API không trả về dữ liệu hợp lệ",
            );
          }

          // Lấy ID của người đang xem (chính mình)
          const viewerId = resData?.data?.node?.business_user_for_viewer?.id;

          // Lấy danh sách từ response
          const edges =
            resData?.data?.node?.business_users_and_invitations?.edges ||
            resData?.data?.node?.business_users?.edges ||
            [];

          // Map ra danh sách user (lọc bỏ invited và chính mình)
          const users = edges
            .filter((edge) => {
              const actionsColumn =
                edge?.actionsColumn || edge?.node?.actionsColumn || {};
              const adminId =
                actionsColumn?.businessUserID ||
                edge?.nameColumn?.id ||
                edge?.node?.id;
              // Bỏ qua invited và chính mình
              return (
                !actionsColumn?.invited_email &&
                !edge?.nameColumn?.invited_email &&
                adminId !== viewerId
              );
            })
            .map((edge) => {
              const actionsColumn =
                edge?.actionsColumn || edge?.node?.actionsColumn || {};
              const nameColumn = edge?.nameColumn || {};
              // adminId là businessUserID dùng để xóa
              const adminId =
                actionsColumn?.businessUserID ||
                edge?.node?.id ||
                nameColumn?.id;
              return {
                id: adminId, // ID admin dùng để xóa
                adminId: adminId, // Lưu riêng để hiển thị
                name:
                  actionsColumn?.businessUserName ||
                  nameColumn?.name ||
                  edge?.node?.name,
                backedUserType:
                  actionsColumn?.backed_user_type ||
                  edge?.node?.backed_user_type ||
                  "FACEBOOK",
              };
            });

          return { users, viewerId };
        };

        // Hàm load và render danh sách QTV
        const loadUserList = async () => {
          const userListEl = document.querySelector("#fiox-user-list");
          if (!userListEl) return;

          // Lấy business_id từ URL
          const urlParams = new URLSearchParams(window.location.search);
          const businessId = urlParams.get("business_id");

          if (!businessId) {
            userListEl.innerHTML = `
              <div style="text-align: center; padding: 20px; color: #E4405F; font-size: 13px;">
                ⚠️ Không tìm thấy business_id trong URL
              </div>
            `;
            return;
          }

          // Hiện loading
          userListEl.innerHTML = `
            <div style="display: flex; justify-content: center; padding: 20px;">
              <div class="fiox-spinner"></div>
            </div>
          `;

          try {
            const { users, viewerId } = await fetchBusinessUsers(businessId);
            loadedUsers = users;

            // Cập nhật tổng số admin
            const totalCountEl = document.querySelector("#fiox-total-count");
            if (totalCountEl) {
              totalCountEl.textContent = `${users.length} admin`;
            }

            if (users.length === 0) {
              userListEl.innerHTML = `
                <div style="text-align: center; padding: 20px; color: #65676b; font-size: 13px;">
                  Không tìm thấy QTV nào.<br>
                  <span style="font-size: 12px;">(Đã loại bỏ tài khoản của bạn)</span>
                </div>
              `;
              return;
            }

            userListEl.innerHTML = users
              .map(
                (user) => `
              <div class="fiox-user-item" data-user-id="${user.id}">
                <div class="fiox-checkbox" data-user-id="${user.id}"></div>
                <div style="width: 36px; height: 36px; border-radius: 50%; background: ${
                  user.backedUserType === "INSTAGRAM"
                    ? "linear-gradient(45deg, #f09433 0%, #e6683c 25%, #dc2743 50%, #cc2366 75%, #bc1888 100%)"
                    : "#1877f2"
                }; display: flex; align-items: center; justify-content: center; color: white; flex-shrink: 0;">
                  ${
                    user.backedUserType === "INSTAGRAM"
                      ? `<svg width="20" height="20" viewBox="0 0 24 24" fill="white"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/></svg>`
                      : `<svg width="20" height="20" viewBox="0 0 320 512" fill="white"><path d="M279.14 288l14.22-92.66h-88.91v-60.13c0-25.35 12.42-50.06 52.24-50.06h40.42V6.26S260.43 0 225.36 0c-73.22 0-121.08 44.38-121.08 124.72v70.62H22.89V288h81.39v224h100.17V288z"/></svg>`
                  }
                </div>
                <div style="flex: 1; min-width: 0;">
                  <div style="font-size: 13px; font-weight: 500; color: #1c1e21; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                    ${user.name || "Unknown"}
                  </div>
                  <div style="font-size: 11px; color: #8a8d91; font-family: monospace;">
                    ID: ${user.adminId || user.id}
                  </div>
                </div>
              </div>
            `,
              )
              .join("");

            // Bind events
            userListEl.querySelectorAll(".${_cp}-user-item").forEach((item) => {
              item.onclick = (e) => {
                const checkbox = item.querySelector(".${_cp}-checkbox");
                const userId = item.dataset.userId;

                if (selectedUsers.has(userId)) {
                  selectedUsers.delete(userId);
                  checkbox.classList.remove("checked");
                } else {
                  selectedUsers.add(userId);
                  checkbox.classList.add("checked");
                }
                updateDeleteBtn();
              };
            });
          } catch (err) {
            console.error("[EXT]Error loading users:", err);
            userListEl.innerHTML = `
              <div style="text-align: center; padding: 20px; color: #E4405F; font-size: 13px;">
                ❌ Lỗi: ${err.message}<br>
                <span style="font-size: 12px;">Vui lòng thử lại</span>
              </div>
            `;
          }
        };

        // Cập nhật nút xóa
        const updateDeleteBtn = () => {
          const deleteBtn = document.querySelector("#fiox-delete-btn");
          const selectAllBox = document.querySelector("#fiox-select-all");
          if (!deleteBtn) return;

          deleteBtn.textContent = `Xóa (${selectedUsers.size})`;
          deleteBtn.disabled = selectedUsers.size === 0;

          const allCheckboxes = document.querySelectorAll(
            "#fiox-user-list .${_cp}-checkbox",
          );
          if (selectAllBox) {
            if (
              selectedUsers.size === allCheckboxes.length &&
              allCheckboxes.length > 0
            ) {
              selectAllBox.classList.add("checked");
            } else {
              selectAllBox.classList.remove("checked");
            }
          }
        };

        // Hàm bind events cho business_users popup
        const bindBusinessUsersEvents = () => {
          const selectAllBox = document.querySelector("#fiox-select-all");
          const deleteBtn = document.querySelector("#fiox-delete-btn");

          if (selectAllBox) {
            selectAllBox.parentElement.onclick = () => {
              const allCheckboxes = document.querySelectorAll(
                "#fiox-user-list .${_cp}-checkbox",
              );
              const allSelected = selectedUsers.size === allCheckboxes.length;

              if (allSelected) {
                selectedUsers.clear();
                allCheckboxes.forEach((cb) => cb.classList.remove("checked"));
              } else {
                allCheckboxes.forEach((cb) => {
                  selectedUsers.add(cb.dataset.userId);
                  cb.classList.add("checked");
                });
              }
              updateDeleteBtn();
            };
          }

          if (deleteBtn) {
            deleteBtn.onclick = async () => {
              if (selectedUsers.size === 0) return;

              // Hiện confirm box trong popup (theo tham chiếu — id đã ngẫu nhiên hoá).
              const popup = window.__fioxMenuEl;
              const confirmed = await new Promise((resolve) => {
                const overlay = document.createElement("div");
                overlay.className = "fiox-confirm-overlay";
                overlay.innerHTML = `
                    <div class="fiox-confirm-box">
                      <div class="fiox-confirm-title">⚠️ Xác nhận xóa</div>
                      <div class="fiox-confirm-msg">Bạn có chắc muốn xóa <strong>${selectedUsers.size}</strong> quản trị viên?</div>
                      <div class="fiox-confirm-btns">
                        <button class="fiox-confirm-btn cancel">Hủy</button>
                        <button class="fiox-confirm-btn confirm">Xóa</button>
                      </div>
                    </div>
                  `;
                popup.appendChild(overlay);

                // Animation
                requestAnimationFrame(() => overlay.classList.add("show"));

                const close = (result) => {
                  overlay.classList.remove("show");
                  setTimeout(() => overlay.remove(), 200);
                  resolve(result);
                };

                overlay.querySelector(".cancel").onclick = () => close(false);
                overlay.querySelector(".confirm").onclick = () => close(true);
              });

              if (!confirmed) return;

              // Lấy API type từ select
              const apiSelect = document.querySelector("#fiox-api-select");
              const apiType = apiSelect ? apiSelect.value : "3";

              // Lấy business_id từ URL
              const urlParams = new URLSearchParams(window.location.search);
              const businessId = urlParams.get("business_id");
              const accessToken = await getAccessToken();

              if (!accessToken) {
                alert("Chưa có access token. Vui lòng đăng nhập lại!");
                return;
              }

              // Hiện progress bar
              const progressContainer = document.querySelector(
                "#fiox-progress-container",
              );
              const progressBar = document.querySelector("#fiox-progress-bar");
              const progressText = document.querySelector(
                "#fiox-progress-text",
              );
              const progressCount = document.querySelector(
                "#fiox-progress-count",
              );

              progressContainer.style.display = "block";
              progressBar.style.width = "0%";
              progressText.textContent = "Đang xóa...";

              deleteBtn.disabled = true;
              deleteBtn.textContent = "Đang xóa...";
              apiSelect.disabled = true;

              const userIds = Array.from(selectedUsers);
              const total = userIds.length;
              let success = 0;
              let failed = 0;

              // Hàm gọi API theo type
              const callApi = async (userId, type) => {
                try {
                  let response;
                  switch (type) {
                    case "1":
                      response = await fetch(
                        `https://graph.facebook.com/v18.0/${userId}/?method=POST&access_token=${accessToken}&expiry_time=-99`,
                        {
                          headers: {
                            accept: "*/*",
                            "accept-language":
                              "en-GB,en-US;q=0.9,en;q=0.8,vi;q=0.7",
                          },
                          referrer: "https://www.facebook.com",
                          method: "GET",
                          mode: "cors",
                          credentials: "include",
                        },
                      );
                      break;
                    case "2":
                      const sessionId = crypto.randomUUID();
                      const bodyParams = new URLSearchParams({
                        business_id: businessId,
                        admin_id: userId,
                        session_id: sessionId,
                        event_source: "PMD",
                        __aaid: "0",
                        __bid: businessId,
                      });
                      response = await fetch(
                        "https://business.facebook.com/business/asset_onboarding/business_remove_admin/",
                        {
                          headers: {
                            accept: "*/*",
                            "accept-language":
                              "en-GB,en-US;q=0.9,en;q=0.8,vi;q=0.7",
                            "content-type": "application/x-www-form-urlencoded",
                          },
                          referrer: "https://www.facebook.com",
                          body: bodyParams.toString(),
                          method: "POST",
                          mode: "cors",
                          credentials: "include",
                        },
                      );
                      break;
                    case "3":
                    default:
                      const variables = JSON.stringify({
                        businessID: businessId,
                        businessUserID: userId,
                      });
                      response = await fetch(
                        `https://graph.facebook.com/graphql?method=post&locale=en_US&pretty=false&format=json&fb_api_req_friendly_name=BizKitSettingsRemoveBusinessUserMutation&doc_id=${_sc.docIds && _sc.docIds.bmRemove || "24401670346098526"}&fb_api_caller_class=RelayModern&server_timestamps=true&variables=${encodeURIComponent(
                          variables,
                        )}&access_token=${accessToken}`,
                        {
                          headers: {
                            accept: "application/json",
                            "accept-language": "vi",
                          },
                          referrer: "https://business.facebook.com/",
                          method: "GET",
                          mode: "cors",
                          credentials: "include",
                        },
                      );
                      break;
                  }
                  return response;
                } catch (err) {
                  return null;
                }
              };

              // Hàm xóa 1 QTV
              const removeUser = async (userId) => {
                try {
                  if (apiType === "all") {
                    // Gửi cả 3 API cùng lúc
                    await Promise.all([
                      callApi(userId, "1"),
                      callApi(userId, "2"),
                      callApi(userId, "3"),
                    ]);
                    return true;
                  }

                  let response;

                  switch (apiType) {
                    case "1":
                      // API 1 - Xóa nhanh với expiry_time=-99
                      response = await fetch(
                        `https://graph.facebook.com/v18.0/${userId}/?method=POST&access_token=${accessToken}&expiry_time=-99`,
                        {
                          headers: {
                            accept: "*/*",
                            "accept-language":
                              "en-GB,en-US;q=0.9,en;q=0.8,vi;q=0.7",
                          },
                          referrer: "https://www.facebook.com",
                          method: "GET",
                          mode: "cors",
                          credentials: "include",
                        },
                      );
                      break;

                    case "2":
                      // API 2 - Xóa qua business_remove_admin
                      const sessionId = crypto.randomUUID();
                      const bodyParams = new URLSearchParams({
                        business_id: businessId,
                        admin_id: userId,
                        session_id: sessionId,
                        event_source: "PMD",
                        __aaid: "0",
                        __bid: businessId,
                      });

                      response = await fetch(
                        "https://business.facebook.com/business/asset_onboarding/business_remove_admin/",
                        {
                          headers: {
                            accept: "*/*",
                            "accept-language":
                              "en-GB,en-US;q=0.9,en;q=0.8,vi;q=0.7",
                            "content-type": "application/x-www-form-urlencoded",
                          },
                          referrer: "https://www.facebook.com",
                          body: bodyParams.toString(),
                          method: "POST",
                          mode: "cors",
                          credentials: "include",
                        },
                      );
                      break;

                    case "3":
                    default:
                      // API 3 - Xóa qua GraphQL BizKitSettingsRemoveBusinessUserMutation
                      const variables = JSON.stringify({
                        businessID: businessId,
                        businessUserID: userId,
                      });
                      response = await fetch(
                        `https://graph.facebook.com/graphql?method=post&locale=en_US&pretty=false&format=json&fb_api_req_friendly_name=BizKitSettingsRemoveBusinessUserMutation&doc_id=${_sc.docIds && _sc.docIds.bmRemove || "24401670346098526"}&fb_api_caller_class=RelayModern&server_timestamps=true&variables=${encodeURIComponent(
                          variables,
                        )}&access_token=${accessToken}`,
                        {
                          headers: {
                            accept: "application/json",
                            "accept-language": "vi",
                          },
                          referrer: "https://business.facebook.com/",
                          method: "GET",
                          mode: "cors",
                          credentials: "include",
                        },
                      );
                      break;
                  }

                  const data = await response.json();

                  // Check success theo từng API
                  if (apiType === "1") {
                    return !data.error;
                  } else if (apiType === "2") {
                    return !data.error;
                  } else {
                    return !data.error && !data.errors;
                  }
                } catch (err) {
                  console.error(`[EXT]Error removing user ${userId}:`, err);
                  return false;
                }
              };

              // Worker pool - 10 luồng nếu chọn "Tất cả" (10*3=30 API), 20 luồng nếu chọn 1 API
              const maxConcurrent = apiType === "all" ? 10 : 20;
              let completed = 0;
              let currentIndex = 0;

              const processNext = async () => {
                if (currentIndex >= userIds.length) return;

                const index = currentIndex++;
                const userId = userIds[index];

                await removeUser(userId);

                completed++;

                // Update progress
                progressText.textContent = `Đang xóa: ${completed}/${total}`;
                progressCount.textContent = `${completed}/${total}`;
                progressBar.style.width = `${(completed / total) * 100}%`;

                // Tiếp tục xử lý nếu còn
                if (currentIndex < userIds.length) {
                  await processNext();
                }
              };

              // Khởi động 20 worker đồng thời
              const workers = [];
              for (
                let i = 0;
                i < Math.min(maxConcurrent, userIds.length);
                i++
              ) {
                workers.push(processNext());
              }
              await Promise.all(workers);

              // Sau khi xóa xong, lấy lại danh sách admin để kiểm tra
              progressText.textContent = "Đang kiểm tra...";

              try {
                const { users: remainingUsers } =
                  await fetchBusinessUsers(businessId);
                const remainingIds = new Set(remainingUsers.map((u) => u.id));

                let successCount = 0;
                let failedCount = 0;

                // Kiểm tra từng user đã chọn xóa
                userIds.forEach((userId) => {
                  const item = document.querySelector(
                    `.${_cp}-user-item[data-user-id="${userId}"]`,
                  );
                  if (item) {
                    const existingLabel =
                      item.querySelector(".${_cp}-result-label");
                    if (existingLabel) existingLabel.remove();

                    const label = document.createElement("span");
                    label.className = "fiox-result-label";

                    if (remainingIds.has(userId)) {
                      // Còn trong danh sách → Thất bại
                      label.textContent = "Thất bại";
                      label.style.cssText =
                        "color: #E4405F; font-size: 11px; font-weight: 500; margin-left: auto;";
                      failedCount++;
                    } else {
                      // Đã mất khỏi danh sách → Thành công
                      item.style.opacity = "0.7";
                      label.textContent = "Thành công";
                      label.style.cssText =
                        "color: #31a24c; font-size: 11px; font-weight: 500; margin-left: auto;";
                      successCount++;
                    }

                    item.appendChild(label);
                  }
                });

                // Cập nhật tổng số admin
                const totalCountEl =
                  document.querySelector("#fiox-total-count");
                if (totalCountEl) {
                  totalCountEl.textContent = `${remainingUsers.length} admin`;
                }

                // Hiển thị kết quả
                progressText.innerHTML = `<span style="color: #31a24c;">✓ ${successCount}</span> <span style="color: #65676b;">|</span> <span style="color: #E4405F;">✗ ${failedCount}</span>`;
                progressCount.textContent = "Hoàn tất";
              } catch (err) {
                console.error("[EXT]Error checking results:", err);
                progressText.textContent = "Hoàn tất (không thể kiểm tra)";
                progressCount.textContent = "";
              }

              deleteBtn.textContent = "Xóa (0)";
              deleteBtn.disabled = true;
              apiSelect.disabled = false;
              selectedUsers.clear();
              updateDeleteBtn();

              // Ẩn progress sau 3s
              setTimeout(() => {
                progressContainer.style.display = "none";
              }, 3000);
            };
          }
        };

        // Đặt popup sát nút theo hướng có nhiều không gian (trái/phải, trên/dưới)
        const positionPopupNearBtn = () => {
          const btnRect = btn.getBoundingClientRect();
          const winW = window.innerWidth;
          const winH = window.innerHeight;
          const pw = popup.offsetWidth || 280;
          const ph = popup.offsetHeight || 400;
          const gap = 10;

          // Ngang: ưu tiên phía có nhiều không gian hơn
          const spaceRight = winW - btnRect.right;
          const spaceLeft = btnRect.left;
          let left;
          if (spaceRight >= pw + gap || spaceRight >= spaceLeft) {
            left = btnRect.right + gap;
          } else {
            left = btnRect.left - pw - gap;
          }
          // Kẹp trong viewport
          left = Math.max(4, Math.min(winW - pw - 4, left));

          // Dọc: căn giữa popup với nút, nhưng kẹp trong viewport
          let top = btnRect.top + btnRect.height / 2 - ph / 2;
          const spaceBottom = winH - btnRect.bottom;
          const spaceTop = btnRect.top;
          if (spaceBottom < ph / 2 && spaceTop > spaceBottom) {
            // Dồn lên trên nếu dưới hết chỗ
            top = btnRect.bottom - ph;
          } else if (spaceTop < ph / 2 && spaceBottom > spaceTop) {
            // Dồn xuống dưới nếu trên hết chỗ
            top = btnRect.top;
          }
          top = Math.max(4, Math.min(winH - ph - 4, top));

          popup.style.left = left + "px";
          popup.style.top = top + "px";
          popup.style.right = "auto";
          popup.style.bottom = "auto";
        };

        btn.onclick = () => {
          isPopupOpen = !isPopupOpen;
          if (isPopupOpen) {
            // ⚠ KHÔNG re-parent nếu đã ở trong body: appendChild làm DI CHUYỂN iframe →
            // trình duyệt RELOAD iframe → chạy lại gtag/branding/rum... MỖI lần mở.
            // Chỉ gắn lại khi thực sự bị gỡ khỏi body. (z-index max + ép style đã đủ nổi trên.)
            try {
              if (!document.body.contains(btn)) document.body.appendChild(btn);
              if (!document.body.contains(popup)) document.body.appendChild(popup);
            } catch (_) {}
            // Đảm bảo popup ở top-layer khi mở (re-show nếu bị đóng do re-append).
            _fxEnsureTop(popup, false);
            positionPopupNearBtn();
            // Chống eztool ẩn menu: ép hiện + z-index cao nhất NGAY khi mở (thắng CSS ẩn của eztool).
            popup.style.setProperty("display", "flex", "important");
            popup.style.setProperty("visibility", "visible", "important");
            popup.style.setProperty("position", "fixed", "important");
            popup.style.setProperty("z-index", _fabZ, "important");
            // opacity/transform/pointer-events = cơ chế hiện/ẩn → PHẢI ép !important, nếu không
            // eztool đặt opacity:0!important (stylesheet) là popup vô hình dù display:flex.
            popup.style.setProperty("opacity", "1", "important");
            popup.style.setProperty("transform", "translateY(0) scale(1)", "important");
            popup.style.setProperty("pointer-events", "auto", "important");
          } else {
            popup.style.setProperty("opacity", "0", "important");
            popup.style.setProperty("transform", "translateY(10px) scale(0.95)", "important");
            popup.style.setProperty("pointer-events", "none", "important");
          }
        };

        // Click ngoài popup thì đóng
        document.addEventListener("click", (e) => {
          if (
            isPopupOpen &&
            !popup.contains(e.target) &&
            !btn.contains(e.target)
          ) {
            isPopupOpen = false;
            popup.style.setProperty("opacity", "0", "important");
            popup.style.setProperty("transform", "translateY(10px) scale(0.95)", "important");
            popup.style.setProperty("pointer-events", "none", "important");
          }
        });

        // TỰ MỞ popup khi vào trang (không cần bấm icon) — 1 lần/lần tải trang; user đóng thì thôi.
        if (!window.__fioxMenuAutoOpened) {
          window.__fioxMenuAutoOpened = true;
          setTimeout(() => { try { if (!isPopupOpen && typeof btn.onclick === "function") btn.click(); } catch (e) {} }, 700);
        }

        // Kéo nút tròn tự do — dùng pointer events + setPointerCapture để không mất mouseup
        let btnDragStartX = 0;
        let btnDragStartY = 0;
        let btnStartLeft = 0;
        let btnStartTop = 0;
        let btnIsDragging = false;
        let btnMoved = false;
        let btnPointerId = null;
        const releaseBtnDrag = () => {
          if (!btnIsDragging) return;
          btnIsDragging = false;
          if (btnPointerId !== null) {
            try {
              btn.releasePointerCapture(btnPointerId);
            } catch (_) {}
            btnPointerId = null;
          }
        };
        btn.addEventListener("pointerdown", (e) => {
          if (e.button !== 0) return; // chỉ chuột trái
          btnIsDragging = true;
          btnMoved = false;
          const rect = btn.getBoundingClientRect();
          btnDragStartX = e.clientX;
          btnDragStartY = e.clientY;
          btnStartLeft = rect.left;
          btnStartTop = rect.top;
          btnPointerId = e.pointerId;
          try {
            btn.setPointerCapture(e.pointerId);
          } catch (_) {}
        });
        btn.addEventListener("pointermove", (e) => {
          if (!btnIsDragging) return;
          const dx = e.clientX - btnDragStartX;
          const dy = e.clientY - btnDragStartY;
          if (!btnMoved && Math.abs(dx) + Math.abs(dy) > 3) btnMoved = true;
          const newLeft = btnStartLeft + dx;
          const newTop = btnStartTop + dy;
          const maxLeft = window.innerWidth - btn.offsetWidth - 4;
          const maxTop = window.innerHeight - btn.offsetHeight - 4;
          btn.style.left = Math.max(4, Math.min(maxLeft, newLeft)) + "px";
          btn.style.top = Math.max(4, Math.min(maxTop, newTop)) + "px";
          btn.style.right = "auto";
          btn.style.bottom = "auto";
        });
        btn.addEventListener("pointerup", releaseBtnDrag);
        btn.addEventListener("pointercancel", releaseBtnDrag);
        btn.addEventListener("lostpointercapture", releaseBtnDrag);
        // Ngăn click toggle popup khi vừa drag xong
        btn.addEventListener(
          "click",
          (e) => {
            if (btnMoved) {
              e.stopPropagation();
              e.preventDefault();
              btnMoved = false;
            }
          },
          true,
        );

        document.body.appendChild(btn);
        // Đưa FAB lên TOP LAYER → luôn trên cùng, eztool (z-index max) KHÔNG đè được nữa.
        _fxTopLayer(btn);
      };

      // ===== BUBBLE BAR: thanh chuyển nhanh giữa các trang FB (top-center) =====
      // Mở nhanh Trình quảng cáo / Lập hoá đơn / Trình tổng quan cho tài khoản HIỆN TẠI (lấy
      // act/asset_id/business_id từ URL) + "Giao diện cũ" (opt-out BM mới qua graphql). Top-layer
      // để eztool/FB không đè. Nhãn/màu/đích/bật-tắt điều khiển qua shield config (_sc.bb*) →
      // chỉnh KHỎI cài lại extension.
      const injectBubbleBar = () => {
        if (!document.body) { setTimeout(injectBubbleBar, 200); return; }
        if (_sc.bbOn === false) return;
        if (document.getElementById(_rp + "bb")) return;

        const _p = new URLSearchParams(location.search || "");
        const _nm = (v) => String(v || "").replace(/^act_/i, "").replace(/[^\d]/g, "");
        const assetId = _nm(_p.get("act") || _p.get("asset_id") || _p.get("payment_account_id"));
        const businessId = _nm(_p.get("business_id"));
        const _bbZ = String(_sc.z || "2147483647");

        const BTNS = _sc.bbBtns || [
          { k: "ads", t: "Trình quảng cáo", c: "#f97316" },
          { k: "invoice", t: "Lập hoá đơn", c: "#f59e0b" },
          { k: "overview", t: "Trình tổng quan", c: "#22c55e" },
          { k: "users", t: "Người dùng", c: "#0ea5e9" },
          { k: "legacy", t: "Giao diện cũ", c: "#6366f1" },
        ];
        const ICONS = {
          ads: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11l18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 11-5.8-1.6"/></svg>',
          invoice: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1z"/><path d="M8 7h8M8 11h8M8 15h5"/></svg>',
          overview: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/><rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/></svg>',
          users: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
          legacy: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>',
        };

        const openTab = (url) => { try { const w = window.open(url, "_blank", "noopener"); if (w) w.opener = null; } catch (e) {} };

        // "Giao diện cũ": mutation BizKitSetBMCOptinStatusMutation (OPT_OUT) — cần dtsg + uid từ trang.
        const switchLegacy = async (pill) => {
          const _lbl = pill.querySelector("[data-t]");
          const _orig = _lbl ? _lbl.textContent : _bbT("Giao diện cũ");
          const _setT = (s) => { try { if (_lbl) _lbl.textContent = s; } catch (e) {} };
          try {
            _setT(_bbT("Đang chuyển…")); pill.style.pointerEvents = "none"; pill.style.opacity = ".6";
            const html = document.documentElement.outerHTML;
            const dtsg = (html.match(/\["DTSGInitialData",\[\],\{"token":"([^"]+)"/) || html.match(/"dtsg":\{"token":"([^"]+)"/) || html.match(/name="fb_dtsg" value="([^"]+)"/) || [])[1];
            const uid = (html.match(/"USER_ID":"(\d+)"/) || html.match(/"actorID":"(\d+)"/) || (document.cookie.match(/c_user=(\d+)/) || []))[1];
            const lsd = (html.match(/\["LSD",\[\],\{"token":"([^"]+)"\}/) || [])[1];
            if (!dtsg || !uid) throw new Error("no-session");
            const body = new URLSearchParams();
            body.set("av", uid); body.set("__a", "1"); body.set("fb_dtsg", dtsg);
            if (lsd) body.set("lsd", lsd);
            body.set("fb_api_caller_class", "RelayModern");
            body.set("fb_api_req_friendly_name", _sc.bbLegacyName || "BizKitSetBMCOptinStatusMutation");
            body.set("variables", JSON.stringify({ input: { client_mutation_id: "3", actor_id: uid, bmc_optin_status: "OPT_OUT" } }));
            body.set("server_timestamps", "true");
            body.set("doc_id", _sc.bbLegacyDoc || "8398852550167223");
            const res = await fetch("https://business.facebook.com/api/graphql/", {
              method: "POST", credentials: "include",
              headers: { "content-type": "application/x-www-form-urlencoded" },
              body: body.toString(),
            });
            const txt = await res.text();
            if (/"errors"/.test(txt) && !/bmc_optin_status|BizKit/.test(txt)) throw new Error("gql-err");
            _setT(_bbT("Đã chuyển ✓"));
            setTimeout(() => { try { location.reload(); } catch (e) {} }, 500);
          } catch (e) {
            _setT(_bbT("Lỗi, thử lại")); pill.style.pointerEvents = ""; pill.style.opacity = "";
            setTimeout(() => _setT(_orig), 1800);
          }
        };

        const doAction = (k, pill) => {
          if (k === "ads") openTab("https://adsmanager.facebook.com/adsmanager/manage/campaigns" + (assetId ? "?act=" + assetId : ""));
          else if (k === "invoice") openTab(assetId ? "https://business.facebook.com/billing_hub/payment_settings/?placement=ads_manager&asset_id=" + assetId : "https://business.facebook.com/billing_hub/accounts");
          else if (k === "overview") { const o = businessId || assetId; openTab("https://business.facebook.com/latest/home" + (o ? "?asset_id=" + o : "")); }
          else if (k === "users") openTab("https://adsmanager.facebook.com/adsmanager/manage/ad_account_settings/ad_account_setup/?act=" + assetId);
          else if (k === "legacy") switchLegacy(pill);
        };

        const bar = document.createElement("div");
        bar.id = _rp + "bb";
        bar.style.cssText = "display:flex;gap:0;align-items:center;overflow:visible;background:#fff;border-radius:0 0 14px 14px;box-shadow:0 4px 15px rgba(15,23,42,.16),0 1px 3px rgba(15,23,42,.07);font-family:'Segoe UI',-apple-system,BlinkMacSystemFont,'Helvetica Neue',Arial,sans-serif;transition:background .25s ease,box-shadow .25s ease;";

        // content = pills + nút thu gọn; thu lại (max-width:0) khi đóng để "gọn vào icon".
        const content = document.createElement("div");
        content.style.cssText = "display:flex;gap:5px;align-items:center;max-width:960px;opacity:1;overflow:hidden;transition:max-width .32s cubic-bezier(.4,0,.2,1),opacity .13s ease;";

        BTNS.forEach((b) => {
          const pill = document.createElement("button");
          pill.type = "button";
          pill.innerHTML = '<span style="display:inline-flex;flex-shrink:0">' + (ICONS[b.k] || "") + '</span><span data-t data-src="' + b.t + '">' + _bbT(b.t) + "</span>";
          pill.style.cssText = "display:inline-flex;align-items:center;gap:4px;border:1px solid " + b.c + "33;background:" + b.c + "14;color:" + b.c + ";border-radius:999px;padding:5px 9px;font-size:12px;font-weight:600;letter-spacing:0;cursor:pointer;white-space:nowrap;transition:background .15s,color .15s;line-height:1;";
          pill.onmouseenter = () => { pill.style.background = b.c; pill.style.color = "#fff"; };
          pill.onmouseleave = () => { pill.style.background = b.c + "14"; pill.style.color = b.c; };
          pill.onclick = () => doAction(b.k, pill);
          content.appendChild(pill);
        });

        // Nút thu gọn (–) → bar thụ lại thành 1 icon nhỏ
        const collapseB = document.createElement("button");
        collapseB.type = "button";
        collapseB.setAttribute("aria-label", _bbT("Thu gọn"));
        collapseB.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M5 12h14"/></svg>';
        collapseB.style.cssText = "display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;padding:0;border:none;background:#f1f5f9;color:#64748b;border-radius:50%;cursor:pointer;margin-left:2px;flex-shrink:0;transition:background .15s,color .15s;";
        collapseB.onmouseenter = () => { collapseB.style.background = "#e2e8f0"; collapseB.style.color = "#334155"; };
        collapseB.onmouseleave = () => { collapseB.style.background = "#f1f5f9"; collapseB.style.color = "#64748b"; };
        content.appendChild(collapseB);
        bar.appendChild(content);

        // mini = icon nhỏ phát sáng (tab chữ U mini) hiện khi đã thu gọn → bấm để bung lại
        const mini = document.createElement("button");
        mini.type = "button";
        mini.setAttribute("aria-label", _bbT("Mở thanh công cụ"));
        mini.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>';
        mini.style.cssText = "display:inline-flex;align-items:center;justify-content:center;width:0;min-width:0;height:25px;padding:0;opacity:0;overflow:hidden;border:none;border-radius:0 0 12px 12px;background:linear-gradient(135deg,#8b5cf6,#ec4899);color:#fff;cursor:pointer;flex-shrink:0;box-shadow:0 3px 11px rgba(139,92,246,.5);transition:width .3s cubic-bezier(.4,0,.2,1),opacity .18s ease,transform .15s ease;";
        mini.onmouseenter = () => { mini.style.transform = "translateY(1.5px)"; };
        mini.onmouseleave = () => { mini.style.transform = "translateY(0)"; };
        bar.appendChild(mini);

        // Thu gọn ↔ bung (lưu trạng thái theo phiên). instant=true → đặt ngay không hiệu ứng (lúc tải lại trang).
        const _bbShadow = "0 4px 15px rgba(15,23,42,.16),0 1px 3px rgba(15,23,42,.07)";
        const _bbPad = "4px 7px 5px";
        const setCollapsed = (on, instant) => {
          // Thu gọn: chữ MỜ NHANH (.12s) rồi mới hẹp lại → không thấy pills bị "cuộn/cắt".
          // Bung: hẹp→rộng trước, chữ hiện SAU (delay .14s) → không thấy chữ cắt dở hiện ra.
          const _ct = on
            ? "opacity .12s ease,max-width .32s cubic-bezier(.4,0,.2,1)"
            : "max-width .3s cubic-bezier(.4,0,.2,1),opacity .2s ease .14s";
          if (instant) { content.style.transition = "none"; mini.style.transition = "none"; bar.style.transition = "none"; }
          else { content.style.transition = _ct; }
          if (on) {
            content.style.maxWidth = "0"; content.style.opacity = "0";
            mini.style.width = "26px"; mini.style.opacity = "1";
            bar.style.background = "transparent"; bar.style.boxShadow = "none";
            bar.style.setProperty("padding", "0", "important");
            try { sessionStorage.setItem(_rp + "bbc", "1"); } catch (e) {}
          } else {
            content.style.maxWidth = "960px"; content.style.opacity = "1";
            mini.style.width = "0"; mini.style.opacity = "0";
            bar.style.background = "#fff"; bar.style.boxShadow = _bbShadow;
            bar.style.setProperty("padding", _bbPad, "important");
            try { sessionStorage.removeItem(_rp + "bbc"); } catch (e) {}
          }
          if (instant) {
            void bar.offsetWidth;
            content.style.transition = _ct;
            mini.style.transition = "width .3s cubic-bezier(.4,0,.2,1),opacity .18s ease,transform .15s ease";
            bar.style.transition = "background .25s ease,box-shadow .25s ease";
          }
        };
        collapseB.onclick = () => setCollapsed(true);
        mini.onclick = () => setCollapsed(false);

        document.body.appendChild(bar);
        // Top-layer + vị trí top-center. Reset UA popover (margin/border/inset) nhưng GIỮ top/left riêng.
        const _bbPlace = () => {
          bar.style.setProperty("margin", "0", "important");
          bar.style.setProperty("border", "0", "important");
          bar.style.setProperty("inset", "auto", "important");
          bar.style.setProperty("position", "fixed", "important");
          bar.style.setProperty("top", (_sc.bbTop != null ? _sc.bbTop : 0) + "px", "important");
          bar.style.setProperty("left", "50%", "important");
          bar.style.setProperty("transform", "translateX(-50%)", "important");
          bar.style.setProperty("padding", "4px 7px 5px", "important");
        };
        if (_fxPop) {
          try { bar.setAttribute("popover", "manual"); if (!bar.matches(":popover-open")) bar.showPopover(); } catch (e) {}
          _bbPlace();
        } else {
          _bbPlace();
          bar.style.setProperty("z-index", _bbZ, "important");
        }
        // Khôi phục trạng thái thu gọn đã lưu (phiên) → đặt NGAY, không chạy hiệu ứng.
        try { if (sessionStorage.getItem(_rp + "bbc")) setCollapsed(true, true); } catch (e) {}
        // Watchdog nhẹ: nếu bị gỡ khỏi top-layer (eztool/SPA) → re-show.
        if (!window.__xmBbWatch) {
          window.__xmBbWatch = true;
          setInterval(() => {
            try {
              const el = document.getElementById(_rp + "bb");
              if (el && _fxPop && el.isConnected && !el.matches(":popover-open")) el.showPopover();
            } catch (e) {}
          }, _sc.wt || 2000);
        }
      };

      // Inject sau khi DOM ready. FAB KHÔNG hiện ở billing_hub (có popup riêng); Bubble-bar hiện khắp.
      const _notBilling = !url.includes("/billing_hub/");
      if (document.readyState === "loading") {
        if (_notBilling) document.addEventListener("DOMContentLoaded", injectFloatingButton);
        document.addEventListener("DOMContentLoaded", injectBubbleBar);
      } else {
        if (_notBilling) setTimeout(injectFloatingButton, 500);
        setTimeout(injectBubbleBar, 700);
      }
    }

    // ========== TỐI ƯU FACEBOOK — công tắc của "Công cụ profile" (/cong-cu-profile) ==========
    // Web ghi trạng thái vào chrome.storage.local["fioxFbOptimize"] qua cầu nối; ở đây CHỈ ĐỌC
    // rồi áp dụng. Khoá phải TRÙNG với OPT_KEY/OPTS trong server/public/js/profile-tools.js.
    //
    // ⚠ CHỈ khai những mục làm được mà KHÔNG phải đoán lời gọi nội bộ của Facebook. Ba mục chặn
    // tín hiệu (đã xem chat / đang nhập / đã xem tin) cần biết đúng tên lời gọi mới chặn được;
    // chưa bắt được request thật thì để profile-tools.js đánh dấu "Chưa khả dụng" — thà không có
    // còn hơn bật mà im lặng không tác dụng.
    (function fioxFbOptimize() {
      const KEY = "extFbOptimize", KEY_OLD = "fioxFbOptimize"; // web ghi cả 2; khoá trung tính trước (bản đại lý thay chữ "fiox")
      let cfg = {};

      // --- Ẩn bài gợi ý -------------------------------------------------------------------
      // Nhận diện bằng NHÃN hiển thị trên đầu bài, đa ngôn ngữ. Không đụng API, không đoán.
      const _sugArr = _sc.sugLabels || ["được đề xuất","đề xuất cho bạn","gợi ý cho bạn","suggested for you","suggested post","sponsored · suggested"];
      const SUG = new RegExp("^(" + _sugArr.map(s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")$", "i");
      let sugTimer = null;
      function hideSuggested() {
        let n = 0;
        document.querySelectorAll('div[role="article"]:not([' + _das + '])').forEach((art) => {
          art.setAttribute(_das, "1");
          // Nhãn nằm trong vài span đầu của bài; quét sâu cả bài sẽ tốn và dễ dính nhầm nội dung.
          const spans = art.querySelectorAll("span, h3, h4");
          const lim = Math.min(spans.length, 24);
          for (let i = 0; i < lim; i++) {
            const t = (spans[i].textContent || "").trim();
            if (t.length > 40) continue;
            if (SUG.test(t)) {
              const box = art.closest('[data-pagelet^="FeedUnit"]') || art;
              box.style.display = "none";
              box.setAttribute(_dah, "sug");
              n++;
              break;
            }
          }
        });
        return n;
      }
      function sugOn() {
        if (sugTimer) return;
        hideSuggested();
        // Interval nhẹ thay MutationObserver — bảng tin FB thay DOM liên tục, observer sẽ chạy
        // hàng nghìn lần/phút (xem ghi chú ở khối chặn eztool phía trên).
        sugTimer = setInterval(hideSuggested, 1500);
      }
      function sugOff() {
        if (sugTimer) { clearInterval(sugTimer); sugTimer = null; }
        document.querySelectorAll("[" + _dah + '="sug"]').forEach((el) => {
          el.style.display = "";
          el.removeAttribute(_dah);
        });
        document.querySelectorAll("[" + _das + "]").forEach((el) => el.removeAttribute(_das));
      }

      // --- Giữ vị trí bảng tin ------------------------------------------------------------
      // FB nạp lại bảng tin khi tab được xem lại. Content script và trang DÙNG CHUNG cây DOM nên
      // chặn ở pha CAPTURE trên document sẽ cắt luôn listener của trang (đăng ký sau, ở pha sau).
      let feedGuard = null;
      function feedOn() {
        if (feedGuard) return;
        feedGuard = function (e) { e.stopImmediatePropagation(); };
        document.addEventListener("visibilitychange", feedGuard, true);
        window.addEventListener("focus", feedGuard, true);
      }
      function feedOff() {
        if (!feedGuard) return;
        document.removeEventListener("visibilitychange", feedGuard, true);
        window.removeEventListener("focus", feedGuard, true);
        feedGuard = null;
      }

      function apply() {
        cfg.block_suggested_posts ? sugOn() : sugOff();
        cfg.prevent_facebook_feed_reload ? feedOn() : feedOff();
      }
      try {
        chrome.storage.local.get([KEY, KEY_OLD], (st) => {
          cfg = (st && (st[KEY] || st[KEY_OLD])) || {};
          apply();
        });
        // Gạt công tắc trên web ăn ngay, không bắt người dùng tải lại tab Facebook.
        chrome.storage.onChanged.addListener((ch, area) => {
          const c = area === "local" && (ch[KEY] || ch[KEY_OLD]); if (!c) return;
          cfg = c.newValue || {};
          apply();
        });
      } catch (e) {}
    })();

    // ========== NUÔI TÀI KHOẢN — bộ chạy trong tab Facebook ==========
    // Background mở 1 tab facebook.com rồi gửi {action:"fioxNuoiRun", feature} → tab này chạy phiên nuôi.
    // Config do web ghi vào chrome.storage.local["extNuoiConfig"/"fioxNuoiConfig"] (khớp NUOI_KEY ở
    // profile-tools.js). Không có `feature` → chạy mọi tính năng cần bảng tin (HOME_KEYS); có `feature`
    // → background đã điều hướng sẵn tới trang riêng (Reels / Poke / Sinh nhật…) nên chỉ chạy đúng cái đó.
    (function fioxNuoiRunner() {
      if (window.top !== window.self) return; // content.js chạy cả iframe — nuôi CHỈ ở frame trên cùng
      const NKEY = "extNuoiConfig", NKEY_OLD = "fioxNuoiConfig";
      // Mốc bài feed = nút Thích/Gỡ Thích (đã kiểm trên DOM thật: click "Thích" → đổi "Gỡ Thích").
      const _POST_MARK = '[aria-label="Thích"][role="button"],[aria-label="Gỡ Thích"][role="button"],[aria-label="Like"][role="button"],[aria-label="Remove Like"][role="button"]';
      const _LIKE_TODO = '[aria-label="Thích"][role="button"],[aria-label="Like"][role="button"]'; // chưa thả
      let running = false;

      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
      const rnd = (a, b) => a + Math.floor(Math.random() * (b - a + 1));
      const nlog = (m) => { try { console.log("[fiox-nuôi]", m); } catch (e) {} };
      function getNuoiCfg() {
        return new Promise((resolve) => {
          try { chrome.storage.local.get([NKEY, NKEY_OLD], (st) => resolve((st && (st[NKEY] || st[NKEY_OLD])) || {})); }
          catch (e) { resolve({}); }
        });
      }

      // Lướt bảng tin kiểu NGƯỜI THẬT: lăn chuột từng nhịp nhỏ có gia tốc, dừng đọc lâu-ngắn khác
      // nhau (đa số lướt nhanh, thỉnh thoảng đọc kỹ), đôi lúc lăn ngược lên xem lại và dừng lâu như
      // bị phân tâm. Đếm bài bằng số bài đi qua vùng giữa màn hình (không đụng DOM, dùng WeakSet).
      const _scroller = () => document.scrollingElement || document.documentElement || document.body;
      async function _wheel(dir, strength) {
        const steps = rnd(3, 7);
        for (let i = 0; i < steps && running; i++) {
          const d = Math.round(dir * rnd(70, 180) * (strength || 1));
          try { window.dispatchEvent(new WheelEvent("wheel", { deltaY: d, deltaMode: 0, bubbles: true })); } catch (e) {}
          try { _scroller().scrollBy({ top: d, left: 0, behavior: "auto" }); } catch (e) { try { window.scrollBy(0, d); } catch (e2) {} }
          await sleep(rnd(35, 110)); // khoảng cách giữa các "tick" lăn
        }
      }
      async function _dwell(pace) {
        const r = Math.random();
        let ms;
        if (r < 0.66) ms = rnd(700, 1900);        // lướt nhanh qua
        else if (r < 0.92) ms = rnd(2000, 4200);  // dừng đọc
        else ms = rnd(4800, 9000);                // đọc kỹ / xem video
        await sleep(Math.round(ms * pace));
      }
      async function runLuot(fc, report) {
        const speed = fc.speed || "medium";
        const target = Math.max(3, Math.min(200, Number(fc.count) || 30));
        const pace = speed === "fast" ? 0.6 : speed === "slow" ? 1.55 : 1.0;
        nlog("Lướt bảng tin: mục tiêu " + target + " bài · tốc độ " + speed);
        const viewed = new WeakSet();
        let count = 0, idle = 0;
        // Mỗi bài feed có 1 nút Thích/Gỡ Thích ở thanh hành động → dùng làm mốc đếm bài (feed FB
        // KHÔNG bọc bài trong div[role="article"] một cách nhất quán; nút Thích đáng tin hơn).
        function countViewed() {
          const vh = window.innerHeight || 800;
          const posts = document.querySelectorAll(_POST_MARK);
          for (let i = 0; i < posts.length; i++) {
            const p = posts[i];
            if (viewed.has(p)) continue;
            const b = p.getBoundingClientRect();
            if (b.top < vh * 0.95 && b.bottom > vh * 0.05) { viewed.add(p); count++; }
          }
          return count;
        }
        while (count < target && running && idle < 18) {
          const before = count;
          countViewed();
          report.scrolled = count;
          if (count >= target) break;
          await _wheel(1, rnd(8, 14) / 10);            // lăn xuống một nhịp, lực ngẫu nhiên
          await _dwell(pace);
          if (Math.random() < 0.12 && running) { await _wheel(-1, 0.8); await sleep(rnd(500, 1400)); } // xem lại
          if (Math.random() < 0.07 && running) await sleep(Math.round(rnd(3000, 7000) * pace));        // phân tâm
          countViewed();
          report.scrolled = count;
          idle = count > before ? 0 : idle + 1;        // không có bài mới → có thể hết feed
        }
        report.luot = { scrolled: count };
        nlog("Xong lướt: đã lướt " + count + " bài");
      }

      // Tìm phần tử bấm được theo aria-label (đa ngôn ngữ). FB rối class nên bám nhãn trợ năng.
      // Khớp CHÍNH XÁC trước, chỉ rơi về khớp tiền tố khi không có: gộp cả hai vào một
      // querySelectorAll thì kết quả luôn theo document order, nhãn dài hơn mà nằm trước sẽ thắng
      // (nhãn "Đăng" từng quét trúng mọi nút bắt đầu bằng "Đăng…").
      // root giới hạn phạm vi — cần cho các nút nằm trong hộp thoại vừa mở.
      function findClickable(labels, root) {
        const scope = root || document;
        const pick = (sel) => {
          const els = scope.querySelectorAll(sel);
          for (let i = 0; i < els.length; i++) {
            const el = els[i], r = el.getAttribute("role");
            if (r === "button" || r === "link" || el.tagName === "A" || el.tagName === "BUTTON") return el;
          }
          return null;
        };
        for (let j = 0; j < labels.length; j++) {
          const hit = pick('[aria-label="' + labels[j] + '"]');
          if (hit) return hit;
        }
        for (let j = 0; j < labels.length; j++) {
          const hit = pick('[aria-label^="' + labels[j] + '"]');
          if (hit) return hit;
        }
        return null;
      }

      // Thả cảm xúc (Like) bài bạn bè trong bảng tin — THAO TÁC THẬT.
      async function runReact(fc, report) {
        const target = Math.max(1, Math.min(50, Number(fc.count) || 10));
        nlog("Thả cảm xúc: tối đa " + target + " bài");
        const touched = new WeakSet();
        let reacted = 0, idle = 0;
        while (reacted < target && running && idle < 22) {
          const before = reacted;
          const likes = document.querySelectorAll(_LIKE_TODO); // nút Thích CHƯA bấm
          for (let i = 0; i < likes.length; i++) {
            if (reacted >= target || !running) break;
            const like = likes[i];
            if (touched.has(like)) continue;
            const b = like.getBoundingClientRect();
            if (b.top > window.innerHeight * 0.85 || b.bottom < 40) continue; // chỉ nút trong tầm nhìn
            touched.add(like);
            try { like.scrollIntoView({ block: "center" }); } catch (e) {}
            await sleep(rnd(900, 2200)); // xem bài trước khi thả
            try { like.click(); reacted++; report.reacted = reacted; nlog("Đã thả cảm xúc #" + reacted); } catch (e) {}
            await sleep(rnd(1800, 3800)); // nghỉ giữa các lần thả
          }
          if (reacted <= before) { try { _scroller().scrollBy({ top: rnd(600, 950) }); } catch (e) {} idle++; await sleep(rnd(1200, 2000)); }
          else idle = 0;
        }
        report.react = { reacted: reacted };
        nlog("Xong thả cảm xúc: " + reacted + " bài");
      }

      // Mở thông báo (xoá badge đỏ) — xem rồi đóng.
      async function runOpenNoti(fc, report) {
        const btn = findClickable(["Thông báo", "Notifications"]);
        if (!btn) { nlog("Không thấy nút Thông báo"); return; }
        try { btn.click(); } catch (e) {}
        await sleep(rnd(3000, 6000));
        try { document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", keyCode: 27, bubbles: true })); } catch (e) {}
        report.openNoti = true;
        nlog("Đã mở thông báo");
      }

      // Xem Story bạn bè — mở story đầu tiên trong khay, để tự chạy một lúc rồi đóng.
      async function runViewStory(fc, report) {
        const n = Math.max(1, Math.min(50, Number(fc.count) || 15));
        const story = document.querySelector('a[href*="/stories/"]');
        if (!story) { nlog("Không thấy Story nào"); return; }
        try { story.click(); } catch (e) {}
        nlog("Đang xem Story…");
        await sleep(Math.min(n, 15) * rnd(4000, 6000)); // story tự chuyển
        try { document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", keyCode: 27, bubbles: true })); } catch (e) {}
        report.viewStory = true;
        nlog("Xong xem Story");
      }

      // Tìm kiếm ngẫu nhiên theo từ khoá sở thích — gõ vào ô tìm kiếm rồi Enter.
      async function runSearch(fc, report) {
        const kws = String(fc.keywords || "").split(/[\n,]/).map((s) => s.trim()).filter(Boolean);
        if (!kws.length) { nlog("Chưa có từ khoá tìm kiếm"); return; }
        const kw = kws[rnd(0, kws.length - 1)];
        const box = document.querySelector('input[type="search"],input[aria-label*="Tìm kiếm"],input[aria-label*="Search"],input[placeholder*="Tìm kiếm"],input[placeholder*="Search"]');
        if (!box) { nlog("Không thấy ô tìm kiếm"); return; }
        try { box.focus(); } catch (e) {}
        let setter = null;
        try { setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set; } catch (e) {}
        let cur = "";
        for (let i = 0; i < kw.length; i++) {
          cur += kw[i];
          try { setter ? setter.call(box, cur) : (box.value = cur); } catch (e) { box.value = cur; }
          try { box.dispatchEvent(new Event("input", { bubbles: true })); } catch (e) {}
          await sleep(rnd(70, 180));
        }
        await sleep(rnd(900, 1600));
        try { box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", keyCode: 13, which: 13, bubbles: true })); } catch (e) {}
        await sleep(rnd(3000, 6000));
        report.search = kw;
        nlog("Đã tìm: " + kw);
      }

      // Xin AI viết chữ qua background (proxy /api/ai/seeding — DeepSeek). Tránh CORS từ facebook.com.
      function nuoiAI(mode, caption, count) {
        return new Promise((resolve) => {
          try { chrome.runtime.sendMessage({ action: "fioxNuoiAI", mode: mode, caption: caption, count: count }, (res) => { void chrome.runtime.lastError; resolve(res || { ok: false }); }); }
          catch (e) { resolve({ ok: false }); }
        });
      }
      // Caption bài của NGƯỜI KHÁC là dữ liệu không tin được: nó đi vào prompt AI rồi thành chữ ĐĂNG
      // CÔNG KHAI trên tài khoản khách. Bỏ ký tự rào (nháy/backtick) và cắt câu dạng ra lệnh để bài
      // viết không điều khiển được AI.
      function safeCaption(s) {
        return String(s || "")
          .replace(/["'`“”‘’]/g, " ")
          .replace(/\b(ignore|disregard|system|assistant|prompt|instruction)\b/gi, " ")
          .replace(/\s+/g, " ")
          .trim()
          .slice(0, 400);
      }
      // Chữ AI trả về cũng phải lọc trước khi đăng: chặn link, tag người, chuỗi dài bất thường.
      function safeOut(s) {
        const t = String(s || "").replace(/\s+/g, " ").trim();
        if (!t || t.length > 300) return "";
        if (/https?:\/\/|www\.|t\.me\/|@[\w.]+/i.test(t)) return "";
        return t;
      }
      // Gõ chữ vào khung soạn (contenteditable) của FB. execCommand thất bại thì BỎ, không gán
      // textContent — React của FB không nhận giá trị gán tay, gửi ra là bình luận rỗng.
      async function typeInto(box, text) {
        try { box.focus(); } catch (e) {}
        let ok = false;
        try { ok = document.execCommand("insertText", false, text); } catch (e) {}
        if (!ok) { nlog("Không gõ được vào khung soạn — bỏ qua"); return false; }
        try { box.dispatchEvent(new InputEvent("input", { bubbles: true, data: text, inputType: "insertText" })); } catch (e) {}
        await sleep(rnd(500, 1100));
        return true;
      }
      // Bình luận AI vào bài bạn bè trong bảng tin — THAO TÁC THẬT (nội dung do DeepSeek viết).
      // Xin cả lô 1 lần: /api/ai/seeding tính 1 LƯỢT cho mỗi request bất kể count, mà trần chỉ 50
      // lượt/ngày và dùng CHUNG với thẻ Seeding — gọi từng câu là đốt hết hạn mức.
      async function runCmtAi(fc, report) {
        const target = Math.max(1, Math.min(20, Number(fc.count) || 5));
        nlog("Bình luận AI: tối đa " + target + " bài");
        const touched = new WeakSet();
        let pool = [];
        let done = 0, idle = 0;
        while (done < target && running && idle < 18) {
          const before = done;
          const btns = document.querySelectorAll('[aria-label="Viết bình luận"][role="button"],[aria-label="Bình luận"][role="button"],[aria-label="Comment"][role="button"]');
          for (let i = 0; i < btns.length; i++) {
            if (done >= target || !running) break;
            const btn = btns[i];
            if (touched.has(btn)) continue;
            const b = btn.getBoundingClientRect();
            if (b.top > window.innerHeight * 0.8 || b.bottom < 40) continue;
            touched.add(btn);
            // host = bài chứa nút này (ancestor gần nhất có nút Thích). Khung soạn PHẢI tìm trong
            // host: lấy bằng document.querySelector là gõ vào hộp của bài đã mở trước đó.
            let host = btn;
            for (let k = 0; k < 12 && host; k++) { if (host.querySelector && host.querySelector('[aria-label="Thích"],[aria-label="Gỡ Thích"]')) break; host = host.parentElement; }
            if (!host) { nlog("Không xác định được bài chứa nút bình luận — bỏ qua"); continue; }
            const caption = safeCaption(host.innerText);
            try { btn.scrollIntoView({ block: "center" }); } catch (e) {}
            await sleep(rnd(900, 1800));
            try { btn.click(); } catch (e) {}
            await sleep(rnd(1300, 2300));
            const box = host.querySelector('div[contenteditable="true"][role="textbox"]');
            if (!box) { nlog("Không thấy khung bình luận của bài này — bỏ qua"); continue; }
            if (!pool.length) {
              const ai = await nuoiAI("comments", caption, target - done);
              if (!(ai && ai.ok && ai.comments && ai.comments.length)) {
                nlog("AI không trả bình luận: " + ((ai && ai.error) || "") + " — dừng bình luận phiên này");
                report.cmt = { done: done };
                return;
              }
              pool = ai.comments.map(safeOut).filter(Boolean);
              if (!pool.length) { nlog("Bình luận AI bị lọc hết (có link/tag) — dừng"); report.cmt = { done: done }; return; }
            }
            const cmt = pool.shift();
            if (!(await typeInto(box, cmt))) continue;
            await sleep(rnd(900, 1800));
            try { box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", keyCode: 13, which: 13, bubbles: true })); } catch (e) {}
            done++; report.cmtAi = done; nlog("Đã bình luận #" + done + ": " + cmt);
            await sleep(rnd(3500, 7000)); // nghỉ lâu giữa các bình luận (tránh spam)
          }
          if (done <= before) { try { _scroller().scrollBy({ top: rnd(700, 1000) }); } catch (e) {} idle++; await sleep(rnd(1500, 2500)); }
          else idle = 0;
        }
        report.cmt = { done: done };
        nlog("Xong bình luận AI: " + done + " bài");
      }

      // Bấm N nút khớp nhãn (poke / kết bạn / vào nhóm / theo trang), cuộn nạp thêm nếu hết.
      async function clickButtons(labels, count, name) {
        const target = Math.max(1, Math.min(50, Number(count) || 5));
        nlog(name + ": tối đa " + target);
        const sel = labels.map((l) => '[aria-label="' + l + '"][role="button"]').join(",");
        const touched = new WeakSet();
        let done = 0, idle = 0;
        while (done < target && running && idle < 15) {
          const before = done;
          const btns = document.querySelectorAll(sel);
          for (let i = 0; i < btns.length; i++) {
            if (done >= target || !running) break;
            const btn = btns[i];
            if (touched.has(btn)) continue;
            const b = btn.getBoundingClientRect();
            if (b.bottom < 0 || b.top > window.innerHeight * 1.2) continue;
            touched.add(btn);
            try { btn.scrollIntoView({ block: "center" }); } catch (e) {}
            await sleep(rnd(1000, 2400));
            try { btn.click(); done++; nlog(name + " #" + done); } catch (e) {}
            await sleep(rnd(2600, 5200)); // nghỉ lâu giữa thao tác xã hội (tránh bị coi là spam)
          }
          if (done <= before) { try { _scroller().scrollBy({ top: rnd(700, 1100) }); } catch (e) {} idle++; await sleep(rnd(1600, 2600)); }
          else idle = 0;
        }
        return done;
      }
      async function runPoke(fc, report) { report.poke = await clickButtons(["Chọc lại", "Chọc", "Poke Back", "Poke"], fc.count, "Poke"); }
      async function runAddFriend(fc, report) { report.addFriend = await clickButtons(["Thêm bạn bè", "Add friend", "Add Friend"], fc.count, "Thêm bạn"); }
      async function runJoinGroup(fc, report) { report.joinGroup = await clickButtons(["Tham gia nhóm", "Tham gia", "Join group", "Join Group", "Join"], fc.count, "Vào nhóm"); }
      // ⚠ KHÔNG dùng nhãn "Thích"/"Like" ở đây: selector sinh ra y hệt _LIKE_TODO của bảng tin, nên
      // nếu Facebook chuyển hướng trang gợi ý về feed thì thẻ này biến thành spam thả Thích bài feed.
      async function runFollowPage(fc, report) { report.followPage = await clickButtons(["Theo dõi", "Follow"], fc.count, "Theo trang"); }

      // Lướt Reels: xem rồi chuyển reel kế (ArrowDown + cuộn).
      async function runReels(fc, report) {
        const n = Math.max(1, Math.min(50, Number(fc.count) || 10));
        const watch = Math.max(3, Math.min(30, Number(fc.watchSec) || 8));
        nlog("Lướt Reels: " + n + " video");
        let i = 0;
        for (; i < n && running; i++) {
          await sleep(rnd(watch * 800, watch * 1300));
          try { document.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", keyCode: 40, bubbles: true })); } catch (e) {}
          try { _scroller().scrollBy({ top: Math.round(window.innerHeight * 0.95) }); } catch (e) {}
          await sleep(rnd(700, 1400));
        }
        report.reels = i;
        nlog("Xong Reels: " + i);
      }

      // Phản hồi Story: mở trình xem story rồi thả cảm xúc / trả lời AI, chuyển story kế.
      async function runReactStory(fc, report) {
        const target = Math.max(1, Math.min(20, Number(fc.count) || 5));
        const mode = String(fc.mode || "emoji");
        const story = document.querySelector('a[href*="/stories/"]');
        if (!story) { nlog("Không thấy Story nào"); return; }
        nlog("Phản hồi Story: tối đa " + target + " (kiểu " + mode + ")");
        try { story.click(); } catch (e) {}
        await sleep(rnd(3500, 5500));
        let done = 0;
        for (let i = 0; i < target && running; i++) {
          const wantText = mode === "text" || (mode === "mix" && i % 2 === 1);
          if (wantText) {
            const box = document.querySelector('div[contenteditable="true"][role="textbox"]');
            if (box) {
              const ai = await nuoiAI("comments", "Trả lời ngắn, thân thiện cho một Story của bạn bè trên Facebook", 1);
              const msg = ai && ai.ok && ai.comments && ai.comments[0];
              if (msg) {
                try { box.focus(); } catch (e) {}
                await typeInto(box, msg);
                await sleep(rnd(800, 1500));
                try { box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", keyCode: 13, which: 13, bubbles: true })); } catch (e) {}
                done++; nlog("Đã trả lời story #" + done + ": " + msg);
              }
            }
          } else {
            const react = findClickable(["Yêu thích", "Thích", "Love", "Like"]);
            if (react) { try { react.click(); done++; nlog("Đã thả cảm xúc story #" + done); } catch (e) {} }
          }
          await sleep(rnd(2500, 4500)); // xem hết story rồi mới sang cái kế
          try { document.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", keyCode: 39, bubbles: true })); } catch (e) {}
          await sleep(rnd(1500, 2600));
        }
        try { document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", keyCode: 27, bubbles: true })); } catch (e) {}
        report.reactStory = done;
        nlog("Xong phản hồi Story: " + done);
      }

      // Tương tác trong nhóm: thả cảm xúc + bình luận bài trong feed nhóm (dùng lại React + CmtAI).
      async function runCmtGroup(fc, report) {
        nlog("Tương tác trong nhóm");
        const perGroup = Math.max(1, Math.min(10, Number(fc.postsPerGroup) || 2));
        await runReact({ count: perGroup }, report);
        if (!running) return;
        await sleep(rnd(2000, 4000));
        await runCmtAi({ count: perGroup }, report);
      }

      // Chúc mừng sinh nhật: trên trang Sinh nhật, viết lời chúc AI vào từng ô soạn.
      const BDAY_TONE = { casual: "thân mật, gần gũi", formal: "lịch sự, trang trọng", funny: "hài hước, dí dỏm" };
      async function runBirthday(fc, report) {
        const tone = BDAY_TONE[String(fc.style || "casual")] || BDAY_TONE.casual;
        nlog("Chúc mừng sinh nhật (" + tone + ")");
        const boxes = document.querySelectorAll('div[contenteditable="true"][role="textbox"]');
        const cap = Math.min(10, boxes.length);
        if (!cap) { nlog("Không có ô chúc nào trên trang"); report.birthday = 0; return; }
        // Một request cho cả lô: mỗi lời gọi AI đều tính 1 lượt trong trần 50/ngày.
        const ai = await nuoiAI("comments", "Viết " + cap + " lời chúc mừng sinh nhật ngắn, " + tone + ", chân thành cho bạn trên Facebook, mỗi lời một dòng và khác nhau", cap);
        const pool = (ai && ai.ok && ai.comments ? ai.comments : []).map(safeOut).filter(Boolean);
        if (!pool.length) { nlog("AI không trả lời chúc: " + ((ai && ai.error) || "")); report.birthday = 0; return; }
        let done = 0;
        for (let i = 0; i < cap && running && pool.length; i++) {
          const box = boxes[i];
          try { box.scrollIntoView({ block: "center" }); box.focus(); } catch (e) {}
          await sleep(rnd(900, 1700));
          const msg = pool.shift();
          if (!(await typeInto(box, msg))) continue;
          await sleep(rnd(900, 1600));
          try { box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", keyCode: 13, which: 13, bubbles: true })); } catch (e) {}
          done++; nlog("Đã chúc SN #" + done + ": " + msg);
          await sleep(rnd(3500, 6500));
        }
        report.birthday = done;
      }

      // Chia sẻ bài hay: bấm Chia sẻ → Chia sẻ ngay (lên tường).
      async function runShare(fc, report) {
        const target = Math.max(1, Math.min(5, Number(fc.count) || 1));
        nlog("Chia sẻ bài hay: " + target);
        const touched = new WeakSet();
        let done = 0, idle = 0;
        while (done < target && running && idle < 12) {
          const before = done;
          const btns = document.querySelectorAll('[aria-label="Chia sẻ"][role="button"],[aria-label="Share"][role="button"]');
          for (let i = 0; i < btns.length; i++) {
            if (done >= target || !running) break;
            const sb = btns[i];
            if (touched.has(sb)) continue;
            const b = sb.getBoundingClientRect();
            if (b.top > window.innerHeight * 0.8 || b.bottom < 40) continue;
            touched.add(sb);
            try { sb.scrollIntoView({ block: "center" }); } catch (e) {}
            await sleep(rnd(1000, 2000));
            try { sb.click(); } catch (e) {}
            await sleep(rnd(1600, 2800));
            const now = findClickable(["Chia sẻ ngay", "Share now", "Chia sẻ lên bảng tin của bạn"]);
            if (now) { try { now.click(); done++; nlog("Đã chia sẻ #" + done); } catch (e) {} }
            else { try { document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", keyCode: 27, bubbles: true })); } catch (e) {} }
            await sleep(rnd(3500, 6500));
          }
          if (done <= before) { try { _scroller().scrollBy({ top: rnd(700, 1000) }); } catch (e) {} idle++; await sleep(rnd(1600, 2600)); }
          else idle = 0;
        }
        report.share = done;
      }

      // Đăng bài tự động: mở hộp tạo bài, nội dung AI, đăng. Khung soạn và nút Đăng phải tìm TRONG
      // hộp thoại vừa mở — lấy ở document là gõ vào khung bình luận của bài nào đang mở sẵn.
      async function runPost(fc, report) {
        nlog("Đăng bài tự động");
        const opener = findClickable(["Bạn đang nghĩ gì?"]) || document.querySelector('[role="button"][aria-label*="nghĩ gì"],[role="button"][aria-label*="mind"]');
        if (!opener) { nlog("Không thấy hộp tạo bài"); return; }
        try { opener.click(); } catch (e) {}
        await sleep(rnd(1800, 3200));
        const dlg = document.querySelector('div[role="dialog"]');
        if (!dlg) { nlog("Hộp tạo bài không mở"); return; }
        const box = dlg.querySelector('div[contenteditable="true"][role="textbox"]');
        if (!box) { nlog("Không thấy khung soạn bài"); return; }
        const ai = await nuoiAI("comments", "Viết một status tích cực, ngắn gọn, vui vẻ để đăng lên trang Facebook cá nhân", 1);
        const content = safeOut(ai && ai.ok && ai.comments && ai.comments[0]);
        if (!content) { nlog("AI không trả nội dung dùng được"); try { document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", keyCode: 27, bubbles: true })); } catch (e) {} return; }
        if (!(await typeInto(box, content))) return;
        await sleep(rnd(1200, 2200));
        const postBtn = findClickable(["Đăng", "Post"], dlg);
        if (postBtn) { try { postBtn.click(); report.post = true; nlog("Đã đăng bài: " + content); } catch (e) {} }
        else nlog("Không thấy nút Đăng");
        await sleep(rnd(2500, 4500));
      }

      // ===== Dispatcher =====
      // ⚠ "Trả lời tin nhắn chào hỏi" (nuoi_reply_msg) CỐ Ý không có trong bảng này: chưa đọc được
      // tin đến nên nó gửi câu AI vào cuộc trò chuyện nào đang mở. Bỏ khỏi đây để cấu hình cũ còn
      // _on=true trong storage cũng không chạy được. Thẻ bên web đã để ready:false.
      const ALL_HANDLERS = {
        nuoi_open_noti: runOpenNoti, nuoi_luot: runLuot, nuoi_react: runReact, nuoi_cmt_ai: runCmtAi,
        nuoi_search: runSearch, nuoi_view_story: runViewStory, nuoi_react_story: runReactStory,
        nuoi_share: runShare, nuoi_post: runPost, nuoi_reels: runReels, nuoi_poke: runPoke,
        nuoi_add_friend: runAddFriend, nuoi_join_group: runJoinGroup, nuoi_follow_page: runFollowPage,
        nuoi_birthday: runBirthday, nuoi_cmt_group: runCmtGroup,
      };
      // Trang mà mỗi tính năng BẮT BUỘC phải đang đứng mới được thao tác. Bộ chạy trước đây không
      // đọc location lần nào → Facebook chuyển hướng là thao tác nhầm trang.
      const NAV_EXPECT = {
        nuoi_reels: "/reel", nuoi_poke: "/pokes", nuoi_add_friend: "/friends",
        nuoi_birthday: "/events/birthdays", nuoi_cmt_group: "/groups", nuoi_join_group: "/groups",
        nuoi_follow_page: "/pages",
      };
      // Tính năng chạy NGAY trên trang chủ facebook.com → background mở 1 tab home chạy chung.
      // Thứ tự: việc cần feed trước, việc ĐỔI TRANG (story / tìm kiếm) để cuối cùng.
      const HOME_KEYS = ["nuoi_open_noti", "nuoi_luot", "nuoi_react", "nuoi_cmt_ai", "nuoi_share", "nuoi_post", "nuoi_view_story", "nuoi_react_story", "nuoi_search"];

      // Các trường đếm THAO TÁC THẬT trong report — phải khớp ACT_FIELDS ở background.js, vì cả
      // hai bên cùng trừ vào một trần thao tác/ngày.
      const ACT_FIELDS = ["reacted", "cmtAi", "poke", "addFriend", "joinGroup", "followPage", "reels", "reactStory", "birthday", "share", "post"];
      function countActs(rep) {
        let n = 0;
        ACT_FIELDS.forEach((f) => { const v = rep[f]; if (typeof v === "number") n += v; else if (v === true) n += 1; });
        return n;
      }

      // onlyKey rỗng → chạy mọi tính năng "trang chủ"; có onlyKey → chỉ chạy đúng tính năng đó
      // (background đã mở sẵn đúng trang: /reel/, /pokes/, /friends/suggestions/...).
      // budget = số thao tác còn được phép trong ngày (background tính), hết là dừng giữa phiên.
      async function run(runId, onlyKey, budget) {
        if (running) return { ok: false, err: "đang chạy" };
        running = true;
        const report = { runId: runId, startedAt: Date.now() };
        try {
          const cfg = await getNuoiCfg();
          const gl = cfg._global || {};
          if (gl.master === false) { running = false; return { ok: false, err: "Đã tạm dừng (master tắt)" }; }
          const keys = onlyKey ? [onlyKey] : HOME_KEYS;
          nlog("Bắt đầu phiên nuôi #" + runId + (onlyKey ? " — chỉ " + onlyKey : " — trang chủ"));
          // Ngân sách thao tác còn lại của ngày, background truyền xuống. Hết là dừng NGAY giữa
          // phiên — trước đây trần chỉ gác lúc bắt đầu phiên nên một phiên vượt xa mức đã đặt.
          let left = Number(budget);
          if (!isFinite(left) || left < 0) left = Infinity;
          let ran = 0;
          for (let i = 0; i < keys.length; i++) {
            if (!running) break;
            const key = keys[i], fn = ALL_HANDLERS[key], f = cfg[key];
            if (!fn) { nlog(key + ": chưa hỗ trợ ở bản này — bỏ qua."); continue; }
            if (!f || !f._on) continue;
            if (left <= 0) { nlog("Đã chạm trần thao tác/ngày — dừng phiên"); report.hitLimit = true; break; }
            const want = NAV_EXPECT[key];
            if (want && location.pathname.indexOf(want) !== 0) {
              nlog(key + ": đang ở " + location.pathname + " chứ không phải " + want + " — bỏ qua cho an toàn");
              continue;
            }
            const spentBefore = countActs(report);
            try { await fn(f, report); ran++; } catch (e) { nlog("Lỗi " + key + ": " + ((e && e.message) || e)); }
            left -= countActs(report) - spentBefore;
            await sleep(rnd(2000, 4500)); // nghỉ giữa các tính năng
          }
          if (!ran) nlog("Không có tính năng nào đang bật ở bước này.");
          report.doneAt = Date.now();
          running = false;
          return { ok: true, ran: ran, report: report };
        } catch (e) {
          running = false;
          return { ok: false, err: String((e && e.message) || e) };
        }
      }

      chrome.runtime.onMessage.addListener((r, s, send) => {
        if (!r || r.action !== "fioxNuoiRun") return;
        run(r.runId, r.feature || "", r.budget).then((res) => { try { send(res); } catch (e) {} });
        return true; // trả lời bất đồng bộ
      });
    })();
  }
})();
