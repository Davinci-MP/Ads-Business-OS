/**
 * metaOs - Background Service Worker
 * =====================================
 *
 * Core Service Worker của Chrome Extension (Manifest V3).
 * Xử lý tất cả logic chính của extension bao gồm:
 * - Cookie management (đọc/ghi cookies Facebook)
 * - API calls với authentication
 * - Message routing giữa content scripts và UI
 * - Storage operations
 *
 * Kiến trúc:
 * ┌─────────────────┐     ┌──────────────────┐
 * │  Content Script │────►│ Service Worker   │
 * │  (bridge.js)    │◄────│ (background.js)  │
 * └─────────────────┘     └──────────────────┘
 *          ▲                      │
 *          │                      │ fetch with cookies
 *          │                      ▼
 *     postMessage          ┌──────────────────┐
 *          ▲               │  Facebook API    │
 *          │               │  Graph API       │
 * ┌─────────────────┐      └──────────────────┘
 * │   Web Page UI   │
 * │ (bridge-main.js)│
 * └─────────────────┘
 *
 * @module background
 * @author metaOs
 * @version 1.6.3
 */

// ========================================
// SERVICE WORKER KEEP-ALIVE (Manifest V3)
// ========================================
// Service Worker có thể bị ngủ sau 30s không hoạt động
// Cần keep-alive để tránh lỗi "message port closed"

/**
 * Keep-alive bằng chrome.alarms API
 * Tạo alarm mỗi 25 giây để giữ Service Worker active
 */
const KEEP_ALIVE_ALARM = "keepAlive";

// Tạo alarm khi Service Worker khởi động
chrome.alarms.create(KEEP_ALIVE_ALARM, { periodInMinutes: 0.4 }); // ~24 giây

// Listener cho alarm - chỉ cần tồn tại là đủ để keep-alive
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === KEEP_ALIVE_ALARM) {
    // Log nhẹ để verify keep-alive đang hoạt động
    // console.log("[SW] Keep-alive ping");
  }
});

/**
 * Keep-alive bằng ports (backup mechanism)
 * Giữ kết nối với content scripts để Service Worker không ngủ
 */
const connectedPorts = new Set();

chrome.runtime.onConnect.addListener((port) => {
  connectedPorts.add(port);
  port.onDisconnect.addListener(() => {
    void chrome.runtime.lastError; // Suppress "message channel is closed" error
    connectedPorts.delete(port);
  });
});

// ========================================
// DECLARATIVE NET REQUEST - BYPASS CORS
// ========================================

/**
 * Sử dụng declarativeNetRequest để tự động thay đổi Origin và Referer headers
 * cho mọi request đến Facebook từ extension.
 * Đây là công nghệ chính để bypass CORS detection của Facebook.
 */
chrome.declarativeNetRequest.updateDynamicRules({
  addRules: [
    {
      id: 1,
      priority: 1,
      action: {
        type: "modifyHeaders",
        requestHeaders: [
          {
            header: "Origin",
            operation: "set",
            value: "https://www.facebook.com",
          },
          {
            header: "Referer",
            operation: "set",
            value: "https://www.facebook.com/",
          },
        ],
      },
      condition: {
        initiatorDomains: [chrome.runtime.id],
        urlFilter: "*facebook.com*",
        resourceTypes: ["xmlhttprequest"],
      },
    },
    {
      id: 2,
      priority: 1,
      action: {
        type: "modifyHeaders",
        requestHeaders: [
          {
            header: "Origin",
            operation: "set",
            value: "https://business.facebook.com",
          },
          {
            header: "Referer",
            operation: "set",
            value: "https://business.facebook.com/",
          },
        ],
      },
      condition: {
        initiatorDomains: [chrome.runtime.id],
        urlFilter: "*business.facebook.com*",
        resourceTypes: ["xmlhttprequest"],
      },
    },
    {
      id: 3,
      priority: 1,
      action: {
        type: "modifyHeaders",
        requestHeaders: [
          {
            header: "Origin",
            operation: "set",
            value: "https://www.instagram.com",
          },
          {
            header: "Referer",
            operation: "set",
            value: "https://www.instagram.com/",
          },
        ],
      },
      condition: {
        initiatorDomains: [chrome.runtime.id],
        urlFilter: "*instagram.com*",
        resourceTypes: ["xmlhttprequest"],
      },
    },
  ],
  removeRuleIds: [1, 2, 3],
});

/* ============ Chặn Facebook Pixel (công tắc cụm "Tối ưu Facebook") ============
 * Pixel là thẻ <script> do CHÍNH trang web thứ ba nạp, không phải request của extension — nên vá
 * fetch/WebSocket không với tới, phải chặn ở tầng mạng.
 *
 * ⚠ Dùng LỜI GỌI RIÊNG, KHÔNG nhét vào khối luật 1-3 ở trên: khối đó chạy vô điều kiện mỗi lần
 * service worker khởi động, còn luật này bật/tắt theo công tắc. Nhét chung mà quên khai
 * removeRuleIds thì lần khởi động sau báo trùng id, và vì lời gọi là NGUYÊN TỬ nên hỏng luôn cả
 * ba luật bypass CORS ở trên.
 * ⚠ id 10 nằm ngoài dải 1-3 (dynamic đang dùng) và ngoài dải 5000+ (session).
 * ⚠ KHÔNG khai initiatorDomains: luật này phải chạm request do TRANG phát ra, không phải của
 * extension. Và điều kiện phải HẸP — luật chặn thắng luật sửa header bất kể độ ưu tiên, quét rộng
 * tay là giết luôn request của chính extension.
 */
// Web ghi CẢ khoá trung tính "extFbOptimize" lẫn khoá cũ (profile-tools.js) → đọc khoá trung tính trước: bản obfuscate
// có thể tách chuỗi khoá cũ ("fioxFbOpti"+"mize") làm bộ thay chữ của gói đại lý đổi sai tên
const FBOPT_KEY = "extFbOptimize";
const FBOPT_KEY_OLD = "fioxFbOptimize";
const FBOPT_PIXEL_RULE_ID = 10;

function fbOptSyncPixelRule(bat) {
  const luat = {
    id: FBOPT_PIXEL_RULE_ID,
    priority: 1,
    action: { type: "block" },
    condition: {
      requestDomains: ["connect.facebook.net"],
      urlFilter: "fbevents.js",
      resourceTypes: ["script"],
    },
  };
  return chrome.declarativeNetRequest
    .updateDynamicRules({ addRules: bat ? [luat] : [], removeRuleIds: [FBOPT_PIXEL_RULE_ID] })
    .catch((e) => console.warn("[fbOpt] khong cap nhat duoc luat chan Pixel:", e));
}

function fbOptDongBoLuat() {
  try {
    chrome.storage.local.get([FBOPT_KEY, FBOPT_KEY_OLD], (st) => {
      const cfg = (st && (st[FBOPT_KEY] || st[FBOPT_KEY_OLD])) || {};
      fbOptSyncPixelRule(cfg.block_facebook_pixel === true);
    });
  } catch (e) {}
}

// Luật dynamic SỐNG DAI qua restart, nên phải đồng bộ lại lúc khởi động; không thì luật và công
// tắc lệch nhau mà không ai biết (tắt trên web mà Pixel vẫn bị chặn, hoặc ngược lại).
fbOptDongBoLuat();
try { chrome.runtime.onStartup.addListener(fbOptDongBoLuat); } catch (e) {}
try {
  chrome.storage.onChanged.addListener((ch, area) => {
    const c = area === "local" && (ch[FBOPT_KEY] || ch[FBOPT_KEY_OLD]);
    if (!c) return;
    const cfg = c.newValue || {};
    fbOptSyncPixelRule(cfg.block_facebook_pixel === true);
  });
} catch (e) {}

// ========================================
// CONFIGURATION
// ========================================

/**
 * HAI ĐỊA CHỈ — nền cho mô hình cho thuê web con (đại lý dùng domain riêng).
 *
 * PLATFORM_ANCHOR — NHÚNG CỨNG, KHÔNG BAO GIỜ ghi đè.
 *   Dùng cho những thứ đại lý không được phép tắt: xác thực license, chặn key,
 *   nhịp tim, và hỏi trạng thái đại lý. Vì lời gọi đi thẳng tới đây, đại lý dù
 *   chiếm domain của họ cũng không chặn được.
 *
 * apiBase — địa chỉ phục vụ GIAO DIỆN và API của đại lý. Đọc từ storage (về sau
 *   lấy từ tenant.json nhúng lúc tải bản cài). Chưa có thì dùng chính điểm neo.
 *
 * HÔM NAY hai giá trị TRÙNG NHAU nên hành vi không đổi một chút nào — đây chỉ là
 * tách cấu trúc để bản extension đang phát hành đã sẵn cơ chế, vì client cập
 * nhật rất chậm.
 */
const PLATFORM_ANCHOR = "http://127.0.0.1:8000";
let apiBase = PLATFORM_ANCHOR;

// Nạp apiBase đã lưu. Chỉ nhận https + đúng dạng domain để không bị trỏ bậy.
function isValidBase(u) {
  try {
    const x = new URL(String(u));
    const localHttp = x.protocol === "http:" && (x.hostname === "127.0.0.1" || x.hostname === "localhost");
    return (x.protocol === "https:" || localHttp) && /^[a-z0-9.-]+$/i.test(x.hostname) && !x.search && !x.hash;
  } catch { return false; }
}
async function loadApiBase() {
  try {
    const st = await chrome.storage.local.get(["apiBase"]);
    apiBase = isValidBase(st && st.apiBase) ? String(st.apiBase).replace(/\/+$/, "") : PLATFORM_ANCHOR;
  } catch { apiBase = PLATFORM_ANCHOR; }
  return apiBase;
}
loadApiBase();

/**
 * Hỏi ĐIỂM NEO xem đại lý còn hiệu lực không.
 * Đại lý bị ngưng / tự ý chuyển domain đi nơi khác → trả active:false → xoá
 * apiBase đã lưu và quay về nền tảng. Lỗi mạng thì giữ nguyên, không đổi gì
 * (mạng chập chờn không được phép đá người dùng ra khỏi đại lý hợp lệ).
 */
async function syncTenantFromAnchor(licenseKey) {
  try {
    const url = PLATFORM_ANCHOR + "/api/tenant-status" + (licenseKey ? "?key=" + encodeURIComponent(licenseKey) : "");
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) return;
    const d = await r.json();
    if (!d || typeof d !== "object") return;
    if (d.active === false) {
      await chrome.storage.local.remove("apiBase");
      apiBase = PLATFORM_ANCHOR;
      return;
    }
    if (isValidBase(d.apiBase)) {
      const clean = String(d.apiBase).replace(/\/+$/, "");
      if (clean !== apiBase) {
        await chrome.storage.local.set({ apiBase: clean });
        apiBase = clean;
      }
    }
  } catch { /* mạng lỗi: giữ nguyên trạng thái hiện tại */ }
}

// Ghim icon metaOs cục bộ để branding từ API không ghi đè sau khi khởi động.
const DEFAULT_ACTION_ICON = { 16: "img/icon-16.png", 48: "img/icon-48.png", 128: "img/icon-128.png" };

async function applyExtensionIcon() {
  try {
    await chrome.action.setIcon({ path: DEFAULT_ACTION_ICON });
  } catch { /* im lặng — icon là trang trí */ }
}

/**
 * Nhịp hỏi điểm neo (GĐ8).
 *
 * ⚠ Trước đây syncTenantFromAnchor được viết ra nhưng KHÔNG NƠI NÀO GỌI — nghĩa là toàn
 * bộ cơ chế chống đại lý ôm khách bỏ đi là code chết. Đại lý bị chấm dứt mà extension
 * khách vẫn trỏ về domain của họ mãi mãi.
 *
 * Chu kỳ 6 giờ: đủ nhanh để thu hồi trong ngày, đủ thưa để không thành nhịp đập gọi về
 * máy chủ từ hàng nghìn máy. Chạy thêm một lần lúc khởi động vì service worker MV3 hay bị
 * ngủ và alarm có thể trôi.
 */
const TENANT_SYNC_ALARM = "tenantAnchorSync";
chrome.alarms.create(TENANT_SYNC_ALARM, { periodInMinutes: 360, delayInMinutes: 1 });

async function runTenantAnchorSync() {
  try {
    const d = await chrome.storage.local.get(["clientKey", "licenseKey"]);
    let key = d && (d.clientKey || d.licenseKey) ? String(d.clientKey || d.licenseKey) : "";
    // Cài mới: storage CHƯA có licenseKey (content.js chưa seed vì user chưa vào app) → dùng key
    // NHÚNG trong manifest.author (bản tải về đã gắn key riêng) → sync ra apiBase đại lý NGAY,
    // để "mở tiện ích" trỏ đúng domain đại lý thay vì nhảy về nền tảng.
    if (!key) { try { key = String((chrome.runtime.getManifest() || {}).author || ""); } catch {} }
    await syncTenantFromAnchor(key);
    await applyExtensionIcon();
  } catch { /* im lặng: đây là việc nền, không được phép làm hỏng gì khác */ }
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === TENANT_SYNC_ALARM) runTenantAnchorSync();
});

/**
 * ⚠ KHÔNG gọi runTenantAnchorSync() thẳng ở cấp cao nhất.
 *
 * Service worker MV3 bị huỷ sau ~30 giây rảnh và được DỰNG LẠI bởi bất kỳ sự kiện nào —
 * mà file này có onMessage nhận từ content script chạy trên mọi tab Facebook, cộng các
 * alarm khác. Gọi ở cấp cao nhất nghĩa là mỗi lần worker sống lại là một request về điểm
 * neo: không phải 6 giờ/lần mà có thể vài chục lần mỗi giờ TRÊN MỖI MÁY. Nhân với hàng
 * nghìn người dùng là tự đánh sập chính điểm neo của mình.
 *
 * Chỉ chạy khi thật sự cần: lúc cài/cập nhật extension, và lúc trình duyệt khởi động.
 * Ngoài ra để alarm lo — alarm sống sót qua việc worker bị huỷ.
 */
chrome.runtime.onInstalled.addListener(() => { runTenantAnchorSync(); });
chrome.runtime.onStartup.addListener(() => { runTenantAnchorSync(); });

// ========================================
// SHIELD CONFIG SYNC
// ========================================
/**
 * Đồng bộ cấu hình phòng thủ từ server (tag, z-index, vị trí, kích thước...).
 * Content.js đọc _shieldCfg từ chrome.storage để tạo nút nổi + popup.
 * Khi EZTOOL thích nghi → sửa config trên server → ext cũ tự áp dụng.
 * Sync mỗi 4 giờ + lúc cài/startup, giống alarm tenantSync.
 */
const SHIELD_SYNC_ALARM = "shieldCfgSync";
chrome.alarms.create(SHIELD_SYNC_ALARM, { periodInMinutes: 240, delayInMinutes: 0.5 });

let _scBg = {}; // shield config cache cho background.js
async function syncShieldConfig() {
  try {
    await loadApiBase();
    const r = await fetch(apiBase + "/api/ext-shield", { signal: AbortSignal.timeout(8000) });
    if (!r.ok) return;
    const cfg = await r.json();
    if (cfg && typeof cfg === "object") {
      _scBg = cfg;
      await chrome.storage.local.set({ _shieldCfg: cfg });
      if (cfg.syncMin && cfg.syncMin > 0) {
        chrome.alarms.create(SHIELD_SYNC_ALARM, { periodInMinutes: cfg.syncMin, delayInMinutes: cfg.syncMin });
      }
    }
  } catch { /* im lặng */ }
}
// Load cache từ storage khi SW khởi động
chrome.storage.local.get("_shieldCfg", (r) => { if (r._shieldCfg) _scBg = r._shieldCfg; });
chrome.alarms.onAlarm.addListener((alarm) => { if (alarm.name === SHIELD_SYNC_ALARM) syncShieldConfig(); });
chrome.runtime.onInstalled.addListener(() => { syncShieldConfig(); });
chrome.runtime.onStartup.addListener(() => { syncShieldConfig(); });

/**
 * ===== ĐỒNG BỘ NỀN "Chia sẻ báo cáo Ads cho khách" =====
 *
 * Mục tiêu: chỉ cần Chrome bật (KHÔNG cần mở tab công cụ) thì số liệu khách xem vẫn tươi
 * và lệnh sửa của khách vẫn được thực thi. Service worker chạy theo alarm, tự lấy số liệu
 * từng tài khoản đang chia sẻ rồi đẩy lên server.
 *
 * TOKEN: background không tự lấy được token FB → dùng token do PAGE đẩy sẵn vào
 * chrome.storage.local["fioxShareBg"] = {key, token, ts} (ads-share.js, mỗi khi mở tool).
 * Token hết hạn (lâu không mở tool) → fetch trả lỗi OAuth → bỏ qua, chờ mở tool lấy token mới.
 * Chỉ user ĐÃ dùng tính năng chia sẻ mới có fioxShareBg → alarm không đụng máy chủ với user khác.
 */
const SHARE_SYNC_ALARM = "fioxShareSync";
const SHARE_NO_MINOR = ["CLP", "COP", "CRC", "HUF", "ISK", "IDR", "JPY", "KRW", "PYG", "TWD", "VND"];
chrome.alarms.create(SHARE_SYNC_ALARM, { periodInMinutes: 2, delayInMinutes: 0.5 });

function _shareToMinor(whole, ccy) {
  const n = parseFloat(whole); if (isNaN(n)) return 0;
  return SHARE_NO_MINOR.indexOf((ccy || "").toUpperCase()) >= 0 ? n : Math.round(n * 100);
}
// Tiền tệ THẬT của TKQC (Graph). "" = không đọc được → KHÔNG đoán VND (sai tiền tệ = lệch ngân sách 100×).
async function _shareAcctCcy(actId, token) {
  try {
    const d = await fetch("https://graph.facebook.com/" + (_scBg.graphVer || "v18.0") + "/act_" + actId + "?fields=currency&access_token=" + token, { cache: "no-store" }).then((r) => r.json());
    const c = String((d && d.currency) || "").toUpperCase();
    return /^[A-Z]{3}$/.test(c) ? c : "";
  } catch (_) { return ""; }
}
function _shareResLabel(t) {
  if (/messaging/.test(t)) return "tin nhắn";
  if (/lead/.test(t)) return "khách tiềm năng";
  if (/purchase/.test(t)) return "đơn hàng";
  if (/link_click/.test(t)) return "click";
  if (/landing/.test(t)) return "xem trang";
  return "kết quả";
}
function _sharePickResult(actions) {
  if (!Array.isArray(actions) || !actions.length) return { resType: "", resCount: 0 };
  const pref = ["onsite_conversion.messaging_conversation_started_7d", "onsite_conversion.messaging_first_reply", "onsite_conversion.total_messaging_connection", "lead", "onsite_web_lead", "offsite_conversion.fb_pixel_lead", "purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase", "link_click", "landing_page_view", "post_engagement"];
  const map = {}; actions.forEach((a) => { map[a.action_type] = parseFloat(a.value || 0); });
  for (const t of pref) { if (map[t] > 0) return { resType: _shareResLabel(t), resCount: map[t] }; }
  let best = null; actions.forEach((a) => { const v = parseFloat(a.value || 0); if (!best || v > best.v) best = { t: a.action_type, v: v }; });
  return best ? { resType: _shareResLabel(best.t), resCount: best.v } : { resType: "", resCount: 0 };
}
async function _shareFetchAccount(actId, token) {
  const V = _scBg.graphVer || "v18.0", base = "https://graph.facebook.com/" + V;
  const status = encodeURIComponent(JSON.stringify(["ACTIVE", "PAUSED"]));
  const infoUrl = base + "/act_" + actId + "/campaigns?fields=name,status,effective_status,daily_budget,lifetime_budget,objective&effective_status=" + status + "&limit=200&date_preset=maximum&access_token=" + token;
  const insUrl = base + "/act_" + actId + "/insights?level=campaign&fields=campaign_id,spend,cpm,ctr,reach,impressions,frequency,actions&date_preset=last_7d&limit=500&access_token=" + token;
  const [info, ins] = await Promise.all([
    fetch(infoUrl, { cache: "no-store" }).then((r) => r.json()).catch(() => null),
    fetch(insUrl, { cache: "no-store" }).then((r) => r.json()).catch(() => null),
  ]);
  if (!info || info.error || !Array.isArray(info.data)) return { error: (info && info.error) || { message: "no info" } };
  const insMap = {}; if (ins && Array.isArray(ins.data)) ins.data.forEach((x) => { insMap[x.campaign_id] = x; });
  const rows = info.data.map((c) => {
    const m = insMap[c.id] || {};
    const pr = _sharePickResult(m.actions);
    const spend = parseFloat(m.spend || 0);
    return {
      id: String(c.id), accountId: String(actId), name: c.name || "", status: c.status || "", deliveryStatus: c.effective_status || c.status || "",
      dailyBudget: c.daily_budget != null ? Number(c.daily_budget) : null, lifetimeBudget: c.lifetime_budget != null ? Number(c.lifetime_budget) : null,
      spend: spend, results: pr.resCount, cpr: pr.resCount ? spend / pr.resCount : null,
      cpm: parseFloat(m.cpm || 0), ctr: parseFloat(m.ctr || 0), reach: parseFloat(m.reach || 0),
      impressions: parseFloat(m.impressions || 0), frequency: parseFloat(m.frequency || 0),
      objective: c.objective || "", resultType: pr.resType,
    };
  });
  return { rows: rows };
}
function _shareBuildSummary(acct, camps) {
  let tSpend = 0, tRes = 0; camps.forEach((c) => { tSpend += c.spend || 0; tRes += c.results || 0; });
  const byCur = {}; byCur[acct.currency] = Math.round(tSpend);
  const r2 = (n) => n ? Math.round(n * 100) / 100 : null;
  return {
    ky: "Kỳ hiện tại (7 ngày)", tien_te: [acct.currency], tong_chi_theo_tien: byCur, tong_ket_qua: tRes,
    chien_dich: camps.slice(0, 30).map((c) => ({ ten: c.name, tk: acct.name, tien: acct.currency, loai_kq: c.resultType || "kết quả", so_kq: c.results, chi: Math.round(c.spend), cpr: r2(c.cpr), cpm: r2(c.cpm), ctr: r2(c.ctr), tiep_can: c.reach, tan_suat: r2(c.frequency), objective: c.objective, trang_thai: c.deliveryStatus })),
  };
}
function _shareScopeRows(share, rows) {
  if (share.scopeType !== "campaigns") return rows;
  const ids = {}; (share.campaignIds || []).forEach((x) => { ids[String(x)] = 1; });
  return rows.filter((r) => ids[String(r.id)]);
}
async function _shareExec(edit, token) {
  try {
    const V = _scBg.graphVer || "v18.0"; let body = null;
    // Mục tiêu PHẢI thuộc đúng TKQC được chia sẻ (bản chụp trang cũ có thể lẫn TK khác).
    const own = await fetch("https://graph.facebook.com/" + V + "/" + edit.targetId + "?fields=account_id&access_token=" + token, { cache: "no-store" }).then((r) => r.json()).catch(() => null);
    if (!own || own.error || String(own.account_id || "") !== String(edit.accountId || "")) return { ok: false, message: (own && own.error && own.error.message) || "Mục tiêu không nằm trong phạm vi được chia sẻ" };
    if (edit.action === "toggle") { const st = String(edit.params && edit.params.status || "").toUpperCase(); if (st !== "ACTIVE" && st !== "PAUSED") return { ok: false, message: "Trạng thái không hợp lệ" }; body = "status=" + st; }
    else if (edit.action === "budget") {
      const amt = Number(edit.params && edit.params.amount); if (!(amt > 0)) return { ok: false, message: "Ngân sách không hợp lệ" };
      const ccy = String(edit.currency || "").toUpperCase(), real = await _shareAcctCcy(edit.accountId, token);
      if (!/^[A-Z]{3}$/.test(ccy) || !real) return { ok: false, message: "Không đọc được tiền tệ TKQC (token thiếu quyền ads hoặc lỗi mạng) — không quy đổi được ngân sách" };
      if (real !== ccy) return { ok: false, message: "Tiền tệ của liên kết không khớp tài khoản quảng cáo — tạo lại liên kết" };
      const minor = _shareToMinor(amt, ccy); body = ((edit.params && edit.params.budgetType === "lifetime") ? "lifetime_budget=" : "daily_budget=") + encodeURIComponent(minor);
    }
    else if (edit.action === "rename") { const nm = String(edit.params && edit.params.name || "").trim(); if (!nm) return { ok: false, message: "Tên rỗng" }; body = "name=" + encodeURIComponent(nm); }
    else return { ok: false, message: "Thao tác chưa hỗ trợ" };
    const url = "https://graph.facebook.com/" + V + "/" + edit.targetId + "?access_token=" + token + "&format=json&suppress_http_code=1&locale=en_US";
    const res = await fetch(url, { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" }, body: body });
    const t = await res.text(); let d; try { d = t ? JSON.parse(t) : {}; } catch (_) { d = { error: { message: "HTTP " + res.status } }; }
    if (d && d.error) return { ok: false, message: d.error.error_user_msg || d.error.message || "Facebook từ chối" };
    return { ok: true, message: "Đã áp dụng" };
  } catch (e) { return { ok: false, message: (e && e.message) || "Lỗi" }; }
}
async function runShareSync() {
  try {
    // Khoá trung tính trước (web ghi cả 2 — xem FBOPT_KEY)
    const st = await chrome.storage.local.get(["extShareBg", "fioxShareBg"]);
    const cfg = st && (st.extShareBg || st.fioxShareBg);
    if (!cfg || !cfg.key || !cfg.token) return; // chưa dùng tính năng / chưa có token
    const key = String(cfg.key), token = String(cfg.token);
    await loadApiBase();
    const api = (p) => apiBase + p;
    let shares = [];
    try { const r = await fetch(api("/api/share/list?key=" + encodeURIComponent(key)), { cache: "no-store" }).then((x) => x.json()); shares = (r && r.success && r.items) || []; } catch (e) { return; }
    const actives = shares.filter((s) => s.status === "active");
    if (!actives.length) return;
    try { await fetch(api("/api/share/heartbeat"), { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ key: key }) }); } catch (e) {}
    // Gom theo tài khoản để chỉ fetch FB 1 lần / tài khoản.
    const byAcct = {}; actives.forEach((s) => { (byAcct[s.accountId] = byAcct[s.accountId] || []).push(s); });
    let tokenDead = false;
    for (const actId of Object.keys(byAcct)) {
      let fetched; try { fetched = await _shareFetchAccount(actId, token); } catch (e) { continue; }
      // Token FB hết hạn / bị thu hồi (OAuth 190/102) → dừng cả lượt: KHÔNG nhặt lệnh sửa của khách — nhặt rồi chạy bằng
      // token chết thì lệnh bị đánh "lỗi" vĩnh viễn, thay vì nằm chờ tới khi đại lý mở tool (token mới) chạy lại.
      const ec = fetched && fetched.error ? Number(fetched.error.code) : 0;
      if (ec === 190 || ec === 102) { tokenDead = true; break; }
      if (!fetched || fetched.error || !fetched.rows) continue;
      const s0 = byAcct[actId][0];
      const vc = await _shareAcctCcy(actId, token);
      const acct = { id: String(actId), name: s0.accountName || "", currency: vc || s0.currency || "", ccyVerified: !!vc };
      for (const s of byAcct[actId]) {
        const rows = _shareScopeRows(s, fetched.rows);
        if (!rows.length) continue;
        const snapshot = { account: acct, campaigns: rows, adsets: [], ads: [], summary: _shareBuildSummary(acct, rows) };
        try { await fetch(api("/api/share/snapshot"), { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ key: key, id: s.id, snapshot: snapshot }) }); } catch (e) {}
      }
      await new Promise((r) => setTimeout(r, 400));
    }
    if (tokenDead) return;
    // Nhặt lệnh sửa của khách rồi thực thi (đúng bản chất "sửa khi extension chạy").
    try {
      const pend = await fetch(api("/api/share/pending?key=" + encodeURIComponent(key)), { cache: "no-store" }).then((x) => x.json());
      if (pend && pend.success && Array.isArray(pend.edits)) {
        for (const e of pend.edits) {
          const res = await _shareExec(e, token);
          try { await fetch(api("/api/share/edit-result"), { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ key: key, editId: e.editId, ok: !!res.ok, message: res.message || "" }) }); } catch (_) {}
        }
      }
    } catch (e) {}
  } catch (e) { /* việc nền: im lặng */ }
}
chrome.alarms.onAlarm.addListener((alarm) => { if (alarm.name === SHARE_SYNC_ALARM) runShareSync(); });
chrome.runtime.onStartup.addListener(() => { runShareSync(); });

// ========================================
// ACTION CLICK - Mở tab khi click icon
// ========================================
let _clickSynced = false;

chrome.action.onClicked.addListener(async (tab) => {
  await loadApiBase();
  if (apiBase === PLATFORM_ANCHOR && !_clickSynced) {
    _clickSynced = true;
    await runTenantAnchorSync();
    await loadApiBase();
  }
  chrome.tabs.create({ url: apiBase + "/metaos" });
});

// ========================================
// COOKIE MANAGEMENT
// ========================================

/**
 * Lấy tất cả cookies cho một URL cụ thể
 *
 * Đặc biệt với Facebook, sẽ lấy cookies từ cả:
 * - hostname chính (facebook.com)
 * - domain .facebook.com (để bao gồm subdomains)
 *
 * @param {string} url - URL cần lấy cookies
 * @returns {Promise<Array>} Mảng cookie objects
 *
 * @example
 * const cookies = await getCookiesForUrl("https://www.facebook.com");
 * // Returns: [{name: "c_user", value: "123456", ...}, ...]
 */
async function getCookiesForUrl(url) {
  try {
    const urlObj = new URL(url);
    const cookies = await chrome.cookies.getAll({ domain: urlObj.hostname });

    // Nếu là facebook.com, lấy thêm cookies từ .facebook.com
    if (urlObj.hostname.includes("facebook.com")) {
      const fbCookies = await chrome.cookies.getAll({
        domain: ".facebook.com",
      });
      // Merge và loại bỏ duplicates (ưu tiên cookie từ hostname chính)
      const allCookies = [...cookies];
      for (const cookie of fbCookies) {
        if (!allCookies.find((c) => c.name === cookie.name)) {
          allCookies.push(cookie);
        }
      }
      return allCookies;
    }

    return cookies;
  } catch (error) {
    console.error("getCookiesForUrl error:", error);
    return [];
  }
}

/**
 * Format mảng cookies thành chuỗi Cookie header
 *
 * @param {Array} cookies - Mảng cookie objects từ chrome.cookies API
 * @returns {string} Cookie header string theo format "name1=value1; name2=value2"
 *
 * @example
 * formatCookieHeader([{name: "c_user", value: "123"}, {name: "xs", value: "abc"}])
 * // Returns: "c_user=123; xs=abc"
 */
function formatCookieHeader(cookies) {
  return cookies.map((c) => `${c.name}=${c.value}`).join("; ");
}

async function collectMetaOsSession(readPageTokens = false) {
  const cookies = await getCookiesForUrl("https://www.facebook.com/");
  const cookie = formatCookieHeader(cookies);
  const values = Object.fromEntries(cookies.map((item) => [item.name, item.value]));
  const stored = await chrome.storage.local.get([
    "accessToken", "eaagToken", "eaabToken", "fb_dtsg", "extShareBg", "fioxShareBg",
  ]);
  const share = stored.extShareBg || stored.fioxShareBg || {};
  let accessToken = stored.accessToken || share.token || "";
  let fbDtsg = stored.fb_dtsg || "";
  if (readPageTokens && values.c_user) {
    try {
      const response = await fetch("https://www.facebook.com/", { credentials: "include", cache: "no-store" });
      const html = await response.text();
      accessToken = accessToken || ((html.match(/\b(EAA[A-Za-z0-9]+)\b/) || [])[1] || "");
      fbDtsg = fbDtsg || ((html.match(/\["DTSGInitialData",\[\],\{"token":"([^"]+)"/) || html.match(/name="fb_dtsg" value="([^"]+)"/) || [])[1] || "");
    } catch (_) {}
  }
  const eaagToken = stored.eaagToken || (String(accessToken).startsWith("EAAG") ? accessToken : "");
  const eaabToken = stored.eaabToken || (String(accessToken).startsWith("EAAB") ? accessToken : "");
  return {
    success: Boolean(values.c_user), uid: values.c_user || "", c_user: values.c_user || "",
    cookie, accessToken, access_token: accessToken, eaag_token: eaagToken,
    eaab_token: eaabToken, fb_dtsg: fbDtsg,
  };
}

const METAOS_SESSION_SYNC_ALARM = "metaosSessionSync";
chrome.alarms.create(METAOS_SESSION_SYNC_ALARM, { periodInMinutes: 5, delayInMinutes: 1 });

async function syncMetaOsSession() {
  try {
    const session = await collectMetaOsSession(false);
    if (!session.uid) return;
    const stored = await chrome.storage.local.get(["clientKey", "licenseKey"]);
    const clientKey = String(stored.clientKey || stored.licenseKey || "").trim();
    await loadApiBase();
    await fetch(apiBase + "/api/v1/vias/extension-ingest", {
      method: "POST",
      headers: { "content-type": "application/json", "x-adsos-client-key": clientKey },
      body: JSON.stringify({
        fb_uid: session.uid, client_key: clientKey || null, profile_name: "metaOs Chrome",
        cookie: session.cookie, access_token: session.access_token || null,
        eaag_token: session.eaag_token || null, eaab_token: session.eaab_token || null,
        fb_dtsg: session.fb_dtsg || null, device_name: navigator.userAgent,
      }),
    });
  } catch (_) {}
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === METAOS_SESSION_SYNC_ALARM) syncMetaOsSession();
});
chrome.runtime.onInstalled.addListener(syncMetaOsSession);
chrome.runtime.onStartup.addListener(syncMetaOsSession);

// ========================================
// FETCH FUNCTIONS
// ========================================

/**
 * Thực hiện fetch request với cookies đính kèm
 *
 * Service Worker trong MV3 không tự động gửi cookies,
 * nên cần đọc cookies và đính vào header thủ công.
 *
 * Với Facebook requests, tự động thêm các headers:
 * - User-Agent: Chrome browser
 * - Accept: HTML/XML/WebP
 * - Accept-Language: en-US
 *
 * @param {string} url - URL cần fetch
 * @param {Object} options - Fetch options (method, headers, body)
 * @param {string} responseType - Loại response: "text" | "json" | "blob"
 * @returns {Promise<Object>} Result object với {success, data, url, status, ok}
 *
 * @example
 * const result = await fetchWithCookies("https://facebook.com", {}, "text");
 * if (result.success) {
 *   console.log(result.data); // HTML content
 * }
 */
async function fetchWithCookies(url, options = {}, responseType = "text") {
  try {
    // Tạo AbortController với timeout 60s (safety net)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000);

    // Chuẩn bị headers
    // KHÔNG set Cookie, Origin, Referer, Sec-Fetch-* — đây là forbidden headers
    // Cookie: dùng credentials:"include" thay thế
    // Origin/Referer: đã xử lý bởi declarativeNetRequest rules
    // Sec-Fetch-*: Chrome tự thêm đúng giá trị
    const headers = { ...(options.headers || {}) };

    // Xóa forbidden headers nếu caller truyền vào
    delete headers["Cookie"];
    delete headers["Origin"];
    delete headers["Referer"];
    delete headers["Sec-Fetch-Dest"];
    delete headers["Sec-Fetch-Mode"];
    delete headers["Sec-Fetch-Site"];
    delete headers["Sec-Fetch-User"];
    delete headers["Upgrade-Insecure-Requests"];

    const _defUA = _scBg.ua || "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";
    // Headers giống browser thật cho Facebook
    if (url.includes("facebook.com") || url.includes("fb.com")) {
      headers["User-Agent"] = headers["User-Agent"] || _defUA;
      headers["Accept"] =
        headers["Accept"] ||
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7";
      headers["Accept-Language"] =
        headers["Accept-Language"] || "en-US,en;q=0.9";
    }

    // Headers giống browser thật cho Instagram
    if (url.includes("instagram.com")) {
      headers["User-Agent"] = headers["User-Agent"] || _defUA;
      headers["Accept"] =
        headers["Accept"] ||
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8";
      headers["Accept-Language"] =
        headers["Accept-Language"] || "en-US,en;q=0.9";
      headers["X-IG-App-ID"] = headers["X-IG-App-ID"] || (_scBg.igAppId || "936619743392459");
    }

    // Thực hiện fetch
    const fetchOptions = {
      method: options.method || "GET",
      headers: headers,
      // Per-request (fbFetchAs: có _acctCookie HOẶC _captureSetCookie) → "omit": Chrome KHÔNG lưu
      // Set-Cookie của acc vào cookie jar CHUNG (không "đăng nhập" acc vào trình duyệt; cô lập đa luồng).
      // Cookie GỬI ĐI do DNR set header (không phụ thuộc credentials). Path legacy (phiên chính chủ) giữ "include".
      credentials:
        options._acctCookie || options._captureSetCookie || options._pxSlot != null ? "omit" : "include",
      redirect: options.redirect || "follow", // "manual" khi caller cần đọc Set-Cookie ở response 302
      signal: controller.signal,
    };

    // body_b64: caller encode binary body thành base64 (vd: file upload)
    // — workaround chrome.runtime.sendMessage JSON-serialize Uint8Array thành plain object.
    // Decode base64 → Uint8Array → assign body. String JSON-safe qua mọi boundary.
    if (options.body_b64 && ["POST", "PUT", "PATCH"].includes(fetchOptions.method)) {
      const bin = atob(options.body_b64);
      const u8 = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
      fetchOptions.body = u8;
    } else if (
      options.body &&
      ["POST", "PUT", "PATCH"].includes(fetchOptions.method)
    ) {
      fetchOptions.body = options.body;
    }

    const response = await fetch(url, fetchOptions);
    clearTimeout(timeoutId); // Clear timeout khi thành công

    // Xử lý response theo type yêu cầu
    let data;
    if (responseType === "json") {
      const text = await response.text();
      const cleanText = text.replace(/^for\s*\(\s*;\s*;\s*\)\s*;?\s*/, "");
      try {
        data = JSON.parse(cleanText);
      } catch {
        data = cleanText;
      }
    } else if (responseType === "blob") {
      const blob = await response.blob();
      const reader = new FileReader();
      data = await new Promise((resolve) => {
        reader.onloadend = () => resolve(reader.result);
        reader.readAsDataURL(blob);
      });
    } else {
      data = await response.text();
    }

    return {
      success: true,
      data,
      url: response.url,
      status: response.status,
      ok: response.ok,
    };
  } catch (error) {
    // Chỉ method + đường dẫn: query chứa access_token/fb_dtsg — log này hiện ở trang Lỗi, khách hay chụp gửi hỗ trợ.
    const where = ((options && options.method) || "GET") + " " + String(url).split(/[?#]/)[0];
    // Handle timeout/abort error
    if (error.name === "AbortError") {
      console.error("fetchWithCookies timeout:", where);
      return { success: false, error: "Request timeout (60s)" };
    }
    // Lỗi tầng mạng (mất mạng/ngủ máy/proxy chết…): caller đã nhận success:false và tự fallback/bỏ lượt → warn
    // (trang Lỗi chrome://extensions chỉ thu console.error + lỗi không bắt, warn vẫn còn ở console service worker).
    console.warn("fetchWithCookies error:", where, error);
    return { success: false, error: error.message };
  }
}

// ========================================
// FETCH AS ACCOUNT (cookie-pool đa luồng — clone-tao-bm)
// ========================================

/**
 * Counter cho session-rule id inject Cookie per-account.
 * Bắt đầu 5000 cho rõ ràng (session rule là store riêng, không đụng dynamic rule 1-3).
 */
let _acctRuleSeq = 5000;

// ===== User-Agent per-account + Proxy theo NHÓM (B2) — set bởi page =====
// _acctUaList: list UA từ Cài đặt (clone) → fbFetchAs áp theo uid (DNR, per-account).
// Proxy: Chrome KHÔNG cho per-request proxy với HTTPS (cắt query khỏi PAC) → B2 set 1 proxy
// GLOBAL cho MỖI NHÓM account (host-based PAC chỉ FB/IG, còn lại DIRECT); các nhóm chạy tuần tự.
let _acctUaList = [];
let _acctProxyAuth = {}; // "host:port" -> { username, password } cho onAuthRequired

function _uidFromCookie(c) {
  const m = (c || "").match(/c_user=(\d+)/);
  return m ? m[1] : "";
}

// Parse 1 dòng proxy → { host, port, user, pass }. Hỗ trợ: ip:port | ip:port:user:pass |
// http://user:pass@ip:port | user:pass@ip:port.
function _parseProxy(line) {
  let s = (line || "").trim();
  if (!s) return null;
  s = s.replace(/^https?:\/\//i, "");
  let host = "", port = "", user = "", pass = "";
  if (s.includes("@")) {
    const at = s.split("@");
    const cred = (at[0] || "").split(":");
    const hp = (at[1] || "").split(":");
    user = cred[0] || ""; pass = cred[1] || "";
    host = hp[0] || ""; port = hp[1] || "";
  } else {
    const p = s.split(":");
    host = p[0] || ""; port = p[1] || ""; user = p[2] || ""; pass = p[3] || "";
  }
  // Sạch host/port về ASCII (PAC chỉ nhận ASCII) — bỏ ký tự ẩn/non-ASCII do copy-paste.
  host = host.replace(/[^a-zA-Z0-9.\-]/g, "");
  port = port.replace(/\D/g, "");
  if (!host || !port) return null;
  return { host, port, user, pass };
}

// Lưu list UA (per-account, áp qua DNR trong fbFetchAs).
function setupAcctLists(uaList) {
  _acctUaList = Array.isArray(uaList) ? uaList.map((s) => (s || "").trim()).filter(Boolean) : [];
}

// ⚠ MV3 KILL/TÁI SINH service worker rất thường (ngủ sau ~30s, chết khi hết bộ nhớ…). Proxy GLOBAL chỉ
// được TRANG set 1 lần/nhóm; nếu SW tái sinh giữa mẻ, lệnh clear lúc-khởi-động (cuối file) XOÁ mất PAC →
// fetch đi THẲNG IP máy (proxy SAI vẫn chạy OK, KHÔNG trừ dung lượng). Và khi SW vừa thức do chính
// setGroupProxy đánh thức, clear-khởi-động còn ĐUA với set. FIX: (1) lưu proxy đang áp vào storage.session;
// (2) startup RE-APPLY nếu còn mới thay vì xoá mù; (3) setGroupProxy/clearAcctLists ĐỢI startup xong
// (_fbProxyReady) mới chạy → hết đua clear-vs-set. (Debugger giữ SW thức nên lỗi này bị che khi gỡ lỗi.)
const _FB_PROXY_KEY = "_fbGroupProxy";
const _FB_PROXY_TTL = 15 * 60 * 1000; // proxy "treo" quá 15' (mẻ crash, không clear) → startup tự dọn
let _fbProxyStartupDone;
const _fbProxyReady = new Promise((r) => { _fbProxyStartupDone = r; });

// Proxy RIÊNG TỪNG TÀI KHOẢN ("port-slot", xem khối PROXY PORT-SLOT bên dưới) — trạng thái + khoá lưu.
const _PX_KEY = "_fbSlotProxy";
const _PX_REQ_KEY = "_fbSlotRequired"; // dấu "đang BẮT BUỘC proxy riêng" — sống qua lần SW tái sinh (xem fbFetchAs)
const _PX_TTL = 6 * 60 * 60 * 1000; // quá hạn này mà không ai gia hạn → startup dọn trạng thái slot treo (mux tự có TTL trượt 20')
const _PX_REQ_IDLE = 30 * 60 * 1000; // quá hạn này không có gia hạn nào → coi như trang đã đóng, thôi chặn
const _PX_ID_RX = /(?:^|;)\s*(c_user|ds_user_id|b_user)=(\d+)/g;
// Họ miền đi qua mux — PHẢI khớp allowDomains/allowExact của server/lib/pxmux.js (mux từ chối host ngoài danh sách).
const _PX_DOMAINS = ["facebook.com", "instagram.com", "fb.com", "messenger.com", "fbcdn.net", "cdninstagram.com", "fbsbx.com", "facebook.net"];
const _PX_EXACT = ["api.ipify.org", "api64.ipify.org", "ipv4.icanhazip.com"];
let _pxState = null; // {host,port,token,base,count,dynCount,max,idSlot:Map,dynNext,ts} — null = KHÔNG ở chế độ slot
let _pxReqTs = 0; // lần gia hạn phiên slot gần nhất (0 = không bắt buộc); còn mới mà _pxState mất → CHẶN request tài khoản
let _pxLastBase = 40000;
let _pxSaveTimer = null;

// Áp 1 proxy GLOBAL vào chrome.proxy (PAC host-based: chỉ FB/IG đi proxy) + build _acctProxyAuth.
// KHÔNG đụng storage — để startup tái lập PAC mà GIỮ nguyên timestamp đã lưu. proxy rỗng/sai → clear (DIRECT).
async function _applyProxyPac(proxyLine) {
  _acctProxyAuth = {};
  const hasLine = !!(proxyLine && String(proxyLine).trim());
  const p = hasLine ? _parseProxy(proxyLine) : null;
  if (!p) {
    if (hasLine) {
      // Proxy ĐƯỢC cấu hình nhưng SAI định dạng (không tách được host/port): KHÔNG đi thẳng IP (vừa rò IP
      // thật, vừa không trừ data proxy). Fail-closed — route FB/IG tới proxy không kết nối được (mandatory)
      // để request CHẾT, buộc sửa lại proxy thay vì lặng lẽ lộ IP. (proxy RỖNG = chủ ý clear → DIRECT, giữ nguyên.)
      const deadPac =
        "function FindProxyForURL(url, host) {\n" +
        '  if (host.indexOf("facebook.com") !== -1 || host.indexOf("instagram.com") !== -1 || host.indexOf("fb.com") !== -1 || host.indexOf("ipify.org") !== -1)\n' +
        '    return "PROXY 127.0.0.1:1";\n' +
        '  return "DIRECT";\n}';
      await chrome.proxy.settings.set({ value: { mode: "pac_script", pacScript: { data: deadPac, mandatory: true } }, scope: "regular" });
      return;
    }
    await chrome.proxy.settings.clear({ scope: "regular" });
    return;
  }
  if (p.user) _acctProxyAuth[p.host + ":" + p.port] = { username: p.user, password: p.pass };
  const pac =
    "function FindProxyForURL(url, host) {\n" +
    '  if (host.indexOf("facebook.com") !== -1 || host.indexOf("instagram.com") !== -1 || host.indexOf("fb.com") !== -1 || host.indexOf("ipify.org") !== -1)\n' +
    '    return "PROXY ' + p.host + ":" + p.port + '";\n' +
    '  return "DIRECT";\n}';
  // mandatory:true → proxy chết/không kết nối được thì request CHẾT (fail-closed), KHÔNG lén fallback DIRECT.
  await chrome.proxy.settings.set({ value: { mode: "pac_script", pacScript: { data: pac, mandatory: true } }, scope: "regular" });
}

// B2: set 1 proxy GLOBAL cho cả nhóm hiện tại. proxy="" → clear (DIRECT). LƯU lại để SW tái sinh re-apply.
async function setGroupProxy(proxyLine) {
  await _fbProxyReady; // đợi startup (clear/re-apply) xong → set KHÔNG bị clear-khởi-động đè (hết đua)
  if (_pxState || _pxReqTs) await _pxReset(); // proxy theo nhóm và port-slot loại trừ lẫn nhau (chung 1 chrome.proxy)
  const valid = !!(proxyLine && _parseProxy(proxyLine));
  try {
    await _applyProxyPac(proxyLine);
    try {
      if (valid) await chrome.storage.session.set({ [_FB_PROXY_KEY]: { line: proxyLine, ts: Date.now() } });
      else await chrome.storage.session.remove(_FB_PROXY_KEY);
    } catch (e) {}
  } catch (e) {
    // PAC lỗi (vd host non-ASCII còn sót) → bỏ proxy nhóm này, không crash mẻ chạy.
    try { await chrome.storage.session.remove(_FB_PROXY_KEY); } catch (_) {}
    try { await chrome.proxy.settings.clear({ scope: "regular" }); } catch (_) {}
    throw e;
  }
}

// ============================================================================
// PROXY PORT-SLOT — proxy RIÊNG cho từng tài khoản/request (đối tác của server/lib/pxmux.js)
// ----------------------------------------------------------------------------
// Chrome chỉ có 1 proxy toàn cục NHƯNG PAC thấy được CỔNG đích. Mỗi tài khoản = 1 slot; request của tài khoản được gắn
// cổng (base+slot) vào URL facebook/instagram: https://www.facebook.com:40017/… PAC TĨNH (đặt 1 lần/mẻ) chuyển mọi
// request cổng [base, base+9999] tới multiplexer của metaOs (TLS đầu-cuối Chrome↔FB: mux KHÔNG đọc được cookie/token);
// mux chọn proxy upstream theo slot. Request KHÔNG tag (duyệt web thường, cổng 443) vẫn DIRECT.
// FAIL-CLOSED: mux/proxy chết → request chết, không bao giờ lén đi thẳng IP máy.
// ⚠ Redirect: FB/IG có lúc trả Location KHÔNG còn cổng tag (vd /checkpoint/ → https://www.facebook.com/) → để Chrome tự
//   theo thì hop sau đi cổng 443 = lọt IP thật. Nên với request có slot, extension TỰ theo redirect từng hop và gắn lại tag.
// ⚠ Danh tính → slot: _pxSlot tường minh, hoặc _acctCookie chứa c_user/ds_user_id/b_user đã biết. Id MỚI trong Set-Cookie của
//   request ĐÃ có slot tự gán cùng slot (login IG → cookie phiên → phiên BM…), nên 1 dòng luôn 1 IP xuyên suốt luồng.
// ============================================================================
function _pxIds(cookie) {
  const ids = [];
  const s = String(cookie || "");
  let m;
  _PX_ID_RX.lastIndex = 0;
  while ((m = _PX_ID_RX.exec(s))) ids.push(m[2]);
  return ids;
}

// Host được gắn tag/đi qua mux. Khớp ĐÚNG đuôi miền (không includes) — tránh facebook.com.evil.com.
function _pxHostOk(h) {
  h = String(h || "").toLowerCase();
  return _PX_EXACT.includes(h) || _PX_DOMAINS.some((d) => h === d || h.endsWith("." + d));
}
// Họ miền cookie: cookie FB không được gửi sang instagram.com (và ngược lại) khi theo redirect.
function _pxFamily(h) {
  h = String(h || "").toLowerCase();
  if (/(^|\.)(facebook\.com|fb\.com)$/.test(h)) return "fb";
  if (/(^|\.)instagram\.com$/.test(h)) return "ig";
  return "";
}

// Gắn cổng slot vào URL. Trả "" khi URL KHÔNG thể đi qua mux (host ngoài họ miền cho phép, URL hỏng, chưa có phiên) —
// caller phải CHẶN request, tuyệt đối không gửi nguyên URL (không tag = PAC để DIRECT = lộ IP máy).
function _pxTag(url, slot) {
  if (!_pxState) return "";
  let u;
  try { u = new URL(url); } catch (e) { return ""; }
  if (u.protocol === "http:") u.protocol = "https:"; // FB/IG chỉ phục vụ HTTPS; http:// sẽ đi cổng 80 = DIRECT nếu để nguyên
  if (u.protocol !== "https:" || !_pxHostOk(u.hostname)) return "";
  u.port = String(_pxState.base + slot);
  return u.toString();
}
// Bỏ ":4xxxx" khỏi URL (res.url/Location) trước khi trả cho feature — feature luôn thấy URL thường, gọi lại sẽ được gắn tag lại.
function _pxUntag(s) {
  if (typeof s !== "string" || !s) return s;
  const lo = _pxLastBase, hi = _pxLastBase + 9999;
  return s.replace(/(https?:\/\/[A-Za-z0-9.\-]+):(\d{5})(?=[\/?#"'\s]|$)/g, (m, host, port) => {
    const p = +port;
    return p >= lo && p <= hi ? host : m;
  });
}
// Bỏ marker "__fbacct=…" (do fbFetchAs thêm vào URL để DNR nhận ra request) khỏi Location: FB trả Location kèm nguyên query nên marker của hop
// trước bị dội ngược; để nguyên thì hop sau mang 2 marker và feature/lần gọi sau nhìn thấy tham số lạ.
function _pxStripMarker(s) {
  if (typeof s !== "string" || s.indexOf("__fbacct=") < 0) return s;
  const h = s.indexOf("#");
  const hash = h < 0 ? "" : s.slice(h);
  const rest = h < 0 ? s : s.slice(0, h);
  const q = rest.indexOf("?");
  if (q < 0) return s;
  const kept = rest.slice(q + 1).split("&").filter((p) => !p.startsWith("__fbacct=")); // không tuần tự hoá lại → giữ nguyên mã hoá của tham số khác
  return rest.slice(0, q) + (kept.length ? "?" + kept.join("&") : "") + hash;
}

// Debounce NGẮN: bí danh danh tính→slot chưa kịp lưu mà SW bị kill = lần khôi phục sau tài khoản đó nhận slot ĐỘNG khác (nhảy IP)
function _pxScheduleSave() {
  if (_pxSaveTimer) return;
  _pxSaveTimer = setTimeout(() => { _pxSaveTimer = null; _pxSave().catch(() => {}); }, 400);
}
async function _pxSave() {
  const st = _pxState;
  if (!st) return;
  await chrome.storage.session.set({
    [_PX_KEY]: { host: st.host, port: st.port, portCount: st.portCount, token: st.token, base: st.base, count: st.count, dynCount: st.dynCount, dynNext: st.dynNext, idSlot: Object.fromEntries(st.idSlot), ts: st.ts },
  });
}
async function _pxReset() {
  _pxState = null;
  _pxReqTs = 0;
  if (_pxSaveTimer) { clearTimeout(_pxSaveTimer); _pxSaveTimer = null; }
  try { await chrome.storage.session.remove([_PX_KEY, _PX_REQ_KEY]); } catch (e) {}
}

// Chrome giới hạn socket theo TỪNG proxy (~32 ở bản ≤147): mỗi tài khoản cần vài tunnel (instagram/business/graph…) nên 1
// cổng mux sớm nghẽn. Mux nghe K cổng liên tiếp (port..port+K-1); PAC chia slot qua K cổng đó → mỗi cổng là 1 "chuỗi proxy"
// riêng với trần riêng (K×32). Slot s → cổng (s % K) vì cổng đích = base+s và base chọn tuỳ ý → dùng (p - base) % K.
function _pxBuildPac(st) {
  const lo = st.base, hi = st.base + 9999;
  return (
    "function FindProxyForURL(url, host) {\n" +
    "  var m = /^https:\\/\\/[^\\/:]+:(\\d+)(\\/|$)/.exec(url);\n" +
    '  if (!m) return "DIRECT";\n' +
    "  var p = parseInt(m[1], 10);\n" +
    "  if (p < " + lo + " || p > " + hi + ') return "DIRECT";\n' +
    "  var h = host.toLowerCase();\n" +
    "  var ex = " + JSON.stringify(_PX_EXACT) + ", dm = " + JSON.stringify(_PX_DOMAINS) + ", ok = ex.indexOf(h) >= 0;\n" +
    '  for (var i = 0; !ok && i < dm.length; i++) if (h === dm[i] || h.slice(-(dm[i].length + 1)) === "." + dm[i]) ok = true;\n' +
    '  if (ok) return "PROXY ' + st.host + ':" + (' + st.port + " + ((p - " + lo + ") % " + st.portCount + '));\n' +
    '  return "DIRECT";\n}'
  );
}
// mandatory:true + KHÔNG có "DIRECT" dự phòng trong kết quả PAC → mux chết thì request chết (fail-closed).
async function _pxApplyPac(st) {
  _acctProxyAuth = {};
  for (let i = 0; i < st.portCount; i++) _acctProxyAuth[st.host + ":" + (st.port + i)] = { username: st.token, password: "x" };
  await chrome.proxy.settings.set({ value: { mode: "pac_script", pacScript: { data: _pxBuildPac(st), mandatory: true } }, scope: "regular" });
  // Extension khác/VPN/chính sách đang giữ quyền proxy → PAC của ta KHÔNG có hiệu lực: báo ngay thay vì để request chết khó hiểu.
  const g = await chrome.proxy.settings.get({});
  if (g && g.levelOfControl && g.levelOfControl !== "controlled_by_this_extension") {
    throw new Error("px: Chrome không cho extension này điều khiển proxy (" + g.levelOfControl + ") — tắt extension/VPN proxy khác");
  }
}

// Làm "ấm" từng cổng mux. Request ĐẦU TIÊN tới 1 cổng proxy mà Chrome chưa có credential bị 407 → thương lượng qua onAuthRequired, và Chrome
// KHÔNG phát onHeadersReceived cho response thật của request đó (đã đo trên Chrome 156: chỉ có sự kiện 407) ⇒ mất Set-Cookie/Location của
// đúng request đầu tiên — thường chính là bước đăng nhập. Gọi thử 1 request tới MỖI cổng ngay khi dựng phiên (song song, ≤15s) để credential
// vào bộ nhớ Chrome trước khi request tài khoản nào chạy. Lỗi (proxy upstream hỏng, đích chậm…) KHÔNG làm hỏng phiên: thương lượng 407 xảy ra
// trước bước upstream nên cổng vẫn ấm; trang đo sức khoẻ thật bằng "cổng sticky" (px-slot.js).
async function _pxWarm(st) {
  await Promise.all(Array.from({ length: st.portCount }, async (_, k) => {
    const ctrl = new AbortController();
    const tm = setTimeout(() => ctrl.abort(), 15000);
    try {
      const r = await fetch("https://api.ipify.org:" + (st.base + k) + "/?w=" + Date.now().toString(36) + k, { credentials: "omit", cache: "no-store", signal: ctrl.signal });
      try { await r.text(); } catch (e) {}
    } catch (e) {
      console.warn("[px] làm ấm cổng mux", st.port + k, "lỗi:", e && e.message);
    } finally { clearTimeout(tm); }
  }));
}

// Trang gửi cấu hình phiên multiplexer 1 lần/mẻ (và mỗi lần gia hạn). cfg: {host,port,token,base,count,ids:{id:slot},keepAliases}
async function setProxySlots(cfg) {
  await _fbProxyReady;
  cfg = cfg || {};
  const host = String(cfg.host || "");
  const port = Number(cfg.port);
  const base = Number(cfg.base) || 40000;
  const token = String(cfg.token || "");
  // host/port đi thẳng vào chuỗi PAC → kiểm chặt (không cho ký tự nào có thể thoát khỏi chuỗi)
  if (!/^[A-Za-z0-9.\-]{1,253}$/.test(host)) throw new Error("px: host không hợp lệ");
  if (!(Number.isInteger(port) && port >= 1 && port <= 65535)) throw new Error("px: port không hợp lệ");
  if (!/^[A-Za-z0-9_.\-]{8,64}$/.test(token)) throw new Error("px: token không hợp lệ"); // token mux dạng <keyId>.<mac> (có dấu chấm)
  if (!(Number.isInteger(base) && base >= 20000 && base <= 55000)) throw new Error("px: base không hợp lệ");
  const portCount = Math.max(1, Math.min(16, Number(cfg.ports) || 1));
  if (port + portCount - 1 > 65535) throw new Error("px: port không hợp lệ");
  const count = Math.max(1, Math.min(9900, Number(cfg.count) || 1));
  const keep = !!(cfg.keepAliases && _pxState);
  const idSlot = keep ? _pxState.idSlot : new Map();
  if (cfg.ids && typeof cfg.ids === "object") {
    for (const k of Object.keys(cfg.ids)) {
      const s = Number(cfg.ids[k]);
      if (/^\d{3,20}$/.test(k) && Number.isInteger(s) && s >= 0 && s < count) idSlot.set(k, s);
    }
  }
  // Slot ĐỘNG cho tài khoản chưa đăng ký lúc bắt đầu mẻ (id chỉ lộ ra sau khi đăng nhập): nhiều chỗ thì mỗi tài khoản lạ 1 slot riêng,
  // hết chỗ thì quay vòng (2 tài khoản dùng chung IP). Slot luôn < 10000 (độ rộng dải cổng mux).
  const dynCount = Math.max(16, Math.min(512, 9999 - count));
  const st = { host, port, portCount, token, base, count, dynCount, max: count + dynCount, idSlot, dynNext: keep ? _pxState.dynNext : 0, ts: Date.now() };
  try { await chrome.storage.session.remove(_FB_PROXY_KEY); } catch (e) {} // loại trừ với proxy theo nhóm
  // PAC chỉ phụ thuộc host/port/portCount/base (token KHÔNG nằm trong PAC). Gia hạn mỗi phút mà PAC không đổi → KHÔNG đặt
  // lại chrome.proxy (đổi cấu hình proxy có thể khiến Chrome dọn kết nối đang mở = đứt request đang bay giữa mẻ).
  const samePac = !!(_pxState && _pxState.host === host && _pxState.port === port && _pxState.portCount === portCount && _pxState.base === base);
  const prev = _pxState;
  _pxState = st;
  _pxLastBase = base;
  try {
    if (samePac) {
      _acctProxyAuth = {};
      for (let i = 0; i < portCount; i++) _acctProxyAuth[host + ":" + (port + i)] = { username: token, password: "x" };
    } else {
      await _pxApplyPac(st);
    }
  } catch (e) {
    _pxState = prev; // không nhận cấu hình mới (vd extension khác giữ quyền proxy) → không để trạng thái nửa vời
    throw e;
  }
  if (!samePac) await _pxWarm(st); // chỉ khi PAC/cổng đổi: gia hạn mỗi phút không tốn thêm request
  await _pxSave();
  // Dấu "bắt buộc proxy riêng" + nhịp tim: mỗi lần gia hạn làm mới. Nếu sau này _pxState mất (khôi phục SW lỗi, bị reset) mà dấu còn
  // mới thì fbFetchAs CHẶN thay vì lén đi thẳng IP máy; trang đóng/hỏng (không còn gia hạn) → hết _PX_REQ_IDLE tự thôi chặn.
  _pxReqTs = Date.now();
  try { await chrome.storage.session.set({ [_PX_REQ_KEY]: { ts: _pxReqTs } }); } catch (e) {}
}

// Trang kết thúc chế độ slot (đúng 1 lần, ở stop()): bỏ trạng thái + dấu bắt buộc + PAC của ta. Khác clearAcctLists: lệnh đó
// là "hết mẻ" của MỌI chế độ và có thể đến từ tab khác — không được đụng vào phiên slot đang chạy.
async function endProxySlots() {
  await _fbProxyReady;
  const had = !!_pxState;
  await _pxReset();
  if (had) {
    _acctProxyAuth = {};
    try { await chrome.proxy.settings.clear({ scope: "regular" }); } catch (e) {}
  }
}

// Slot của 1 request: _pxSlot tường minh > id trong _acctCookie đã biết > slot ĐỘNG cho tài khoản lạ.
// Không có danh tính nào (caller quên _pxSlot) → null: CHẶN, không đoán (đoán = có thể nhảy IP giữa chừng).
function _pxResolveSlot(options) {
  const st = _pxState;
  if (options && options._pxSlot != null && options._pxSlot !== "") {
    const n = Number(options._pxSlot);
    if (Number.isInteger(n) && n >= 0 && n < st.max) return n;
    return null;
  }
  const ids = _pxIds(options && options._acctCookie);
  for (const id of ids) {
    const s = st.idSlot.get(id);
    if (s != null) return s;
  }
  if (!ids.length) return null;
  const s = st.count + (st.dynNext++ % st.dynCount); // tài khoản ngoài danh sách mẻ: slot riêng (vẫn qua proxy, KHÔNG DIRECT)
  ids.forEach((id) => st.idSlot.set(id, s));
  console.warn("[px] slot động", s, "cho tài khoản chưa đăng ký trong mẻ");
  _pxScheduleSave();
  return s;
}
function _pxLearn(slot, cookieStr) {
  const st = _pxState;
  if (!st) return;
  let added = false;
  for (const id of _pxIds(cookieStr)) {
    if (!st.idSlot.has(id)) { st.idSlot.set(id, slot); added = true; }
  }
  if (added) _pxScheduleSave();
}

// Chạy 1 request AS account qua slot: gắn tag + TỰ theo redirect (xem ⚠ Redirect ở đầu khối).
async function _pxFetchAs(url, options, responseType) {
  const slot = _pxResolveSlot(options);
  if (slot == null) return { success: false, error: "px: thiếu _pxSlot/danh tính tài khoản (chặn để không đi thẳng IP máy)" };
  let cur = _pxUntag(url);
  // Chỉ TỰ theo redirect với host FB/IG: bộ bắt Location/Set-Cookie (webRequest) chỉ phủ 2 họ miền đó — ép lên ipify (đèn báo,
  // không redirect) chỉ khiến mỗi request chờ hết 3s vô ích.
  let hostFam = "";
  try { hostFam = _pxFamily(new URL(cur).hostname); } catch (e) {}
  const follow = (!options.redirect || options.redirect === "follow") && hostFam !== "";
  let o = Object.assign({}, options);
  let method = String(o.method || "GET").toUpperCase();
  const cookies = [];
  for (let hop = 0; hop < 10; hop++) {
    // Không gắn được tag (host ngoài họ miền cho phép / phiên đã bị reset giữa chừng) → CHẶN: gửi nguyên URL = PAC để DIRECT = lộ IP máy
    const tagged = _pxTag(cur, slot);
    if (!tagged) return { success: false, error: "px: URL không đi qua proxy riêng được (ngoài họ miền Facebook/Instagram hoặc phiên đã kết thúc) — chặn để không đi thẳng IP máy" };
    const res = await _fbFetchAsOnce(tagged, follow ? Object.assign({}, o, { redirect: "manual", _captureLocation: true }) : o, responseType);
    if (!res) return res;
    _pxLearn(slot, o._acctCookie);
    if (res.setCookie) { _pxLearn(slot, res.setCookie); cookies.push(res.setCookie); }
    res.url = _pxUntag(res.url);
    if (res.location) res.location = _pxStripMarker(_pxUntag(res.location));
    if (!follow) return res; // caller tự theo redirect: Location đã bỏ tag → lần gọi sau được gắn tag lại
    const redirected = res.success && res.location && (res.status === 0 || (res.status >= 300 && res.status < 400));
    if (!redirected) {
      if (cookies.length > 1 && options._captureSetCookie) res.setCookie = cookies.join("; "); // gom Set-Cookie của mọi hop
      return res;
    }
    let next;
    try { next = new URL(res.location, cur); } catch (e) { return res; }
    if (!_pxHostOk(next.hostname)) return res; // ra ngoài FB/IG: dừng, KHÔNG gửi cookie tài khoản đi nơi khác
    if (_pxFamily(next.hostname) !== _pxFamily(new URL(cur).hostname)) { o = Object.assign({}, o); delete o._acctCookie; } // như trình duyệt: cookie không vượt họ miền
    const code = res.locationStatus || 302;
    if ((code === 301 || code === 302 || code === 303) && method !== "GET" && method !== "HEAD") {
      method = "GET";
      o = Object.assign({}, o, { method: "GET" });
      delete o.body;
      delete o.body_b64;
    }
    cur = next.href;
  }
  return { success: false, error: "px: quá nhiều lần chuyển hướng" };
}

async function clearAcctLists() {
  await _fbProxyReady;
  // Phiên port-slot đang chạy (có thể do TAB KHÁC): chrome.proxy + _acctProxyAuth là của nó, kết thúc riêng bằng endProxySlots —
  // "hết mẻ" của chế độ khác không được gỡ PAC/credential của phiên đó (request đang bay sẽ chết giữa chừng).
  if (_pxState) return;
  _acctUaList = [];
  _acctProxyAuth = {};
  try { await chrome.storage.session.remove(_FB_PROXY_KEY); } catch (e) {}
  try { await chrome.proxy.settings.clear({ scope: "regular" }); } catch (e) {}
}

// Trả credentials cho proxy có auth (user:pass) — blocking, cần permission webRequestAuthProvider.
// Chỉ trả khi challenger nằm trong _acctProxyAuth (proxy ta dùng); proxy khác để Chrome xử mặc định.
// Riêng mux port-slot: Chrome lặp lại ĐÚNG credential cũ ~30 lần/request khi mux từ chối nó (token sai/mux đổi secret) — mỗi vòng
// là 1 CONNECT nữa lên mux. Request đã được cấp credential mà bị thách thức lần 2 = credential bị từ chối → HUỶ ngay (lỗi rõ, không
// vòng lặp). Chỉ áp cho cổng mux của phiên slot; proxy theo nhóm (chế độ cũ) giữ nguyên hành vi.
const _pxAuthGiven = new Map();
chrome.webRequest.onAuthRequired.addListener(
  (details) => {
    try {
      if (details.isProxy && details.challenger) {
        const key = details.challenger.host + ":" + details.challenger.port;
        const cred = _acctProxyAuth[key];
        if (cred) {
          const st = _pxState;
          if (st && details.requestId != null && details.challenger.host === st.host && details.challenger.port >= st.port && details.challenger.port < st.port + st.portCount) {
            if (_pxAuthGiven.has(details.requestId)) return { cancel: true };
            _pxAuthGiven.set(details.requestId, 1);
            if (_pxAuthGiven.size > 3000) for (const k of _pxAuthGiven.keys()) { _pxAuthGiven.delete(k); if (_pxAuthGiven.size <= 1500) break; }
          }
          return { authCredentials: cred };
        }
      }
    } catch (e) {}
    return {};
  },
  { urls: ["<all_urls>"] },
  ["blocking"],
);

// SW khởi động (MV3 tái sinh SW): nếu CÒN proxy đang áp (lưu session, còn trong TTL) → RE-APPLY để fetch
// giữa mẻ vẫn qua proxy; cũ/không có → clear (dọn proxy treo do lần trước crash). Xong mới mở cổng
// _fbProxyReady cho setGroupProxy/clearAcctLists chạy — hết đua clear-vs-set lúc SW vừa thức.
(async () => {
  try {
    // Port-slot: còn phiên mới (lưu session, trong TTL) → KHÔI PHỤC trạng thái + PAC tĩnh rồi dừng; quá hạn → dọn.
    const ps = await chrome.storage.session.get([_PX_KEY, _PX_REQ_KEY]);
    const rq = ps && ps[_PX_REQ_KEY];
    if (rq && Number(rq.ts) > 0) _pxReqTs = Number(rq.ts); // dấu "bắt buộc" sống sót qua việc khôi phục lỗi bên dưới → fbFetchAs vẫn CHẶN
    const p = ps && ps[_PX_KEY];
    if (p && p.host && p.token && p.ts && (Date.now() - p.ts) < _PX_TTL) {
      const dyn = p.dynCount || 64;
      _pxState = { host: p.host, port: p.port, portCount: p.portCount || 1, token: p.token, base: p.base, count: p.count, dynCount: dyn, max: p.count + dyn, idSlot: new Map(Object.entries(p.idSlot || {})), dynNext: p.dynNext || 0, ts: p.ts };
      _pxLastBase = p.base;
      await _pxApplyPac(_pxState);
      return;
    }
    if (p) { try { await chrome.storage.session.remove(_PX_KEY); } catch (e) {} }

    const s = await chrome.storage.session.get(_FB_PROXY_KEY);
    const g = s && s[_FB_PROXY_KEY];
    if (g && g.line && g.ts && (Date.now() - g.ts) < _FB_PROXY_TTL) {
      await _applyProxyPac(g.line); // GIỮ nguyên ts đã lưu → vẫn hết hạn sau TTL dù SW tái sinh nhiều lần
    } else {
      if (g) { try { await chrome.storage.session.remove(_FB_PROXY_KEY); } catch (e) {} }
      await chrome.proxy.settings.clear({ scope: "regular" });
    }
  } catch (e) {
    // Khôi phục port-slot lỗi (vd extension khác giữ quyền proxy): bỏ luôn trạng thái slot — nếu giữ lại thì request vẫn bị gắn
    // tag trong khi PAC đã bị xoá bên dưới (request tag đi thẳng tới cổng lạ của FB và hỏng khó hiểu). Dấu _pxReqTs GIỮ NGUYÊN:
    // còn mới thì fbFetchAs chặn request tài khoản (thay vì cho đi thẳng IP máy) cho tới khi trang dựng lại phiên.
    _pxState = null;
    try { await chrome.storage.session.remove(_PX_KEY); } catch (_) {}
    try { await chrome.proxy.settings.clear({ scope: "regular" }); } catch (_) {}
  } finally {
    _fbProxyStartupDone();
  }
})();

// ⚠ ĐẢM BẢO proxy active NGAY TRƯỚC MỖI request FB (per-request guarantee — thứ user cần "mỗi api đi cùng
// proxy"). MV3 tái sinh SW giữa mẻ → PAC bị clear-khởi-động xoá; re-apply ở startup là ASYNC nên fetch
// ngay-sau-khi-SW-vừa-thức có thể bắn TRƯỚC khi PAC dựng lại → request đi THẲNG IP (proxy sai vẫn gửi OK,
// không trừ data). Đây là khe hở bị CHE khi gỡ lỗi (debugger giữ SW thức nên re-apply luôn kịp). Fix: chờ
// _fbProxyReady (startup xong) + nếu còn proxy đang áp (storage) mà chrome.proxy chưa phải pac_script thì
// re-apply NGAY → KHÔNG request FB nào lọt ra ngoài proxy.
async function _ensureGroupProxy() {
  try {
    await _fbProxyReady;
    const s = await chrome.storage.session.get(_FB_PROXY_KEY);
    const g = s && s[_FB_PROXY_KEY];
    if (g && g.line && g.ts && (Date.now() - g.ts) < _FB_PROXY_TTL) {
      const cur = await chrome.proxy.settings.get({});
      if (!cur || !cur.value || cur.value.mode !== "pac_script") await _applyProxyPac(g.line);
    }
  } catch (e) {}
}

// ===== Bắt Set-Cookie/Location của response: MỘT listener webRequest dùng chung (tra Map nonce → handler) =====
// Thêm/gỡ listener cho TỪNG request làm Chrome dựng lại bảng handler mỗi lần: 100 request đồng thời → độ trễ O(N²) (đo ~45s với N=100).
// Giờ: cài lười khi có request cần bắt đầu tiên, gỡ sau 5s không còn handler nào (không để lại hook trên lưu lượng duyệt web của khách).
// Chỉ nhận request do CHÍNH extension phát (tabId -1) kiểu fetch/XHR — không đụng tab của khách.
const _capHandlers = new Map();
let _capOn = false;
let _capIdleTimer = null;
function _capOnHeaders(details) {
  try {
    if (!details || !details.url || !_capHandlers.size) return;
    // FB hay trả Location mang NGUYÊN query của request (kể cả marker __fbacct của hop trước) → URL có thể chứa NHIỀU marker:
    // tìm marker nào đang có handler (bản "lấy marker đầu tiên" làm mất Set-Cookie của hop sau cú redirect login → web.facebook.com)
    const rx = /__fbacct=([A-Za-z0-9]+)/g;
    let m;
    while ((m = rx.exec(details.url))) {
      const h = _capHandlers.get(m[1]);
      if (h) { h(details); return; }
    }
  } catch (_) {}
}
function _capAdd(nonce, handler) {
  if (_capIdleTimer) { clearTimeout(_capIdleTimer); _capIdleTimer = null; }
  if (!_capOn) {
    try {
      chrome.webRequest.onHeadersReceived.addListener(
        _capOnHeaders,
        { urls: ["*://*.facebook.com/*", "*://*.instagram.com/*"], types: ["xmlhttprequest"], tabId: -1 },
        ["responseHeaders", "extraHeaders"],
      );
      _capOn = true;
    } catch (e) {
      return false; // không gắn được listener → caller trả về không có setCookie và tự báo lỗi
    }
  }
  _capHandlers.set(nonce, handler);
  return true;
}
function _capRemove(nonce) {
  _capHandlers.delete(nonce);
  if (_capHandlers.size || !_capOn || _capIdleTimer) return;
  _capIdleTimer = setTimeout(() => {
    _capIdleTimer = null;
    if (_capHandlers.size) return;
    try { chrome.webRequest.onHeadersReceived.removeListener(_capOnHeaders); } catch (_) {}
    _capOn = false;
  }, 5000);
}

/**
 * Fetch Facebook AS một account cụ thể bằng cookie truyền vào (KHÔNG dùng cookie jar).
 *
 * Cơ chế: thêm 1 declarativeNetRequest SESSION rule (in-memory, không ghi disk) khớp
 * marker "__fbacct=<nonce>" trong URL → set header Cookie = cookie của account đó.
 * URL được gắn marker; request PHẢI đi từ Service Worker (DNR initiatorDomains:[ext]
 * mới khớp) nên gọi fetchWithCookies TRỰC TIẾP — KHÔNG qua performFetch (performFetch
 * có fallback fetch qua tab Facebook = account đang login = SAI account).
 *
 * Nhiều request song song: mỗi cái 1 nonce + 1 rule id riêng → không đụng nhau.
 * Rule bị xóa ngay sau khi xong (finally). DNR "set" Cookie đè cookie jar.
 *
 * @param {string} url
 * @param {Object} options - bắt buộc có options._acctCookie = chuỗi cookie account
 * @param {string} responseType - "text" | "json" | "blob"
 * @returns {Promise<Object>} {success, data, ...} như fetchWithCookies
 */
async function fbFetchAs(url, options, responseType) {
  // Đợi startup (khôi phục PAC/trạng thái port-slot khi SW tái sinh) rồi mới quyết định đường đi.
  await _fbProxyReady;
  if (_pxState) return await _pxFetchAs(url, options || {}, responseType); // chế độ port-slot: gắn tag + tự theo redirect
  // Trang đã yêu cầu proxy riêng (_pxSlot) HOẶC phiên slot đang bắt buộc (còn nhịp tim gia hạn) mà extension không còn trạng thái
  // (khôi phục SW lỗi/bị reset) → CHẶN, không lén đi thẳng IP máy. Trang dựng lại phiên ở nhịp gia hạn kế tiếp (≤ 60s).
  if ((options && options._pxSlot != null) || _pxRequired()) return { success: false, error: "px: phiên proxy riêng chưa/không còn hiệu lực" };
  return await _fbFetchAsOnce(url, options, responseType);
}
function _pxRequired() {
  return _pxReqTs > 0 && Date.now() - _pxReqTs < _PX_REQ_IDLE;
}

// 1 request AS account (không tag, không theo redirect) — thân hàm gốc của fbFetchAs.
async function _fbFetchAsOnce(url, options, responseType) {
  const cookie = options && options._acctCookie;
  // _captureSetCookie: bắt Set-Cookie ở response (fetch KHÔNG đọc được) để login lấy cookie b_user.
  // Khi chỉ bắt set-cookie mà KHÔNG có _acctCookie (vd FB auth/token xác thực bằng access_token trong
  // body), vẫn chạy — nhưng XOÁ cookie header để cookie jar của khách không rò vào, giữ cô lập đa luồng.
  const wantSetCookie = !!(options && options._captureSetCookie);
  // _captureLocation: đọc header Location của response 3xx. fetch redirect:"manual" trong SW trả
  // opaqueredirect (không đọc được header) → phải bắt qua webRequest.onHeadersReceived (tầng mạng).
  // Dùng để FOLLOW redirect THỦ CÔNG từng hop (vd đăng nhập BM qua IG-OIDC SSO).
  const wantLocation = !!(options && options._captureLocation);
  const wantSlot = !!(options && options._pxSlot != null); // port-slot: request không cookie vẫn đi đường cô lập này
  if (!cookie && !wantSetCookie && !wantLocation && !wantSlot) {
    return { success: false, error: "fbFetchAs: thiếu _acctCookie" };
  }

  await _ensureGroupProxy(); // per-request: proxy PHẢI active trước khi fetch (chống SW tái sinh làm lọt ra ngoài proxy)

  const uid = cookie ? _uidFromCookie(cookie) : "";
  _acctRuleSeq = _acctRuleSeq >= 2000000 ? 5000 : _acctRuleSeq + 1;
  const ruleId = _acctRuleSeq;
  const nonce =
    "fa" + ruleId + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  const markedUrl = url + (url.includes("?") ? "&" : "?") + "__fbacct=" + nonce;

  // requestHeaders: cookie + UA per-account (theo uid). UA cũng forbidden trong fetch → set qua DNR.
  // (Proxy KHÔNG đi qua đây — B2 set proxy GLOBAL theo nhóm bằng setGroupProxy.)
  const reqHeaders = [];
  if (cookie) {
    reqHeaders.push({ header: "cookie", operation: "set", value: cookie });
    if (_acctUaList.length && uid) {
      const ui = (parseInt(uid.slice(-9), 10) || 0) % _acctUaList.length;
      reqHeaders.push({ header: "user-agent", operation: "set", value: _acctUaList[ui] });
    }
  } else {
    // Không có _acctCookie (chỉ bắt set-cookie) → xoá cookie jar cho request này (cô lập).
    reqHeaders.push({ header: "cookie", operation: "remove" });
  }
  // Referer facebook.com (forbidden trong fetch → set qua DNR). Một số API cũ (graphqlbatch)
  // bắt buộc có Referer, thiếu → error 1357032. Chỉ set khi caller yêu cầu (_referer).
  if (options && options._referer) {
    reqHeaders.push({ header: "referer", operation: "set", value: options._referer });
  }
  // Origin cũng forbidden trong fetch → set qua DNR (vd auth/token cần origin instagram.com).
  if (options && options._origin) {
    reqHeaders.push({ header: "origin", operation: "set", value: options._origin });
  }

  // Bắt Set-Cookie từ response qua webRequest.onHeadersReceived (tầng mạng, thấy cả header nhạy cảm
  // nhờ "extraHeaders"). Lọc theo nonce trong URL để cô lập từng request chạy song song.
  // ⚠ Listener PHI-BLOCKING → Chrome gửi event bất đồng bộ; với redirect:"manual" fetch() resolve
  // NGAY ở 302 nên có thể đọc capturedSetCookies TRƯỚC khi listener chạy. Dùng captureDone để CHỜ
  // listener bắn xong (hoặc timeout) rồi mới đọc — tránh đua trả về cookie rỗng khi tải nặng.
  let capturedSetCookies = [];
  let capturedLocation = "";
  let capturedStatus = 0; // mã 301/302/303/307/308 — cần để theo redirect đúng ngữ nghĩa (port-slot)
  let capRegistered = false;
  let captureFired = null;
  const wantCapture = wantSetCookie || wantLocation;
  const captureDone = wantCapture ? new Promise((res) => { captureFired = res; }) : null;
  if (wantCapture) {
    capRegistered = _capAdd(nonce, (details) => {
      try {
        // 407 = bước thương lượng credential với proxy (cổng mux "nguội"), KHÔNG phải response thật: bỏ qua, kẻo coi như đã bắt
        // xong rồi mất Set-Cookie/Location của response thật tới ngay sau đó.
        if (details.statusCode === 407) return;
        const hs = details.responseHeaders || [];
        capturedStatus = details.statusCode || 0;
        for (const h of hs) {
          if (!h || !h.name || !h.value) continue;
          const hn = h.name.toLowerCase();
          if (hn === "set-cookie") capturedSetCookies.push(h.value);
          else if (hn === "location") capturedLocation = h.value;
        }
      } catch (_) {}
      if (captureFired) { captureFired(); captureFired = null; } // nonce khớp → đánh dấu đã bắt xong
    });
  }

  try {
    await chrome.declarativeNetRequest.updateSessionRules({
      addRules: [
        {
          id: ruleId,
          priority: 2,
          action: {
            type: "modifyHeaders",
            requestHeaders: reqHeaders,
          },
          condition: {
            initiatorDomains: [chrome.runtime.id],
            urlFilter: "__fbacct=" + nonce,
            resourceTypes: ["xmlhttprequest"],
          },
        },
      ],
    });
  } catch (e) {
    if (capRegistered) _capRemove(nonce);
    // Không inject được cookie → KHÔNG fetch (tránh chạy nhầm account của jar)
    return { success: false, error: "fbFetchAs rule add failed: " + (e && e.message) };
  }

  try {
    const res = await fetchWithCookies(markedUrl, options, responseType);
    if (wantCapture && res) {
      // Chờ listener onHeadersReceived bắn xong (hoặc tối đa 3s) rồi mới đọc — vá đua phi-blocking.
      try { await Promise.race([captureDone, new Promise((r) => setTimeout(r, 3000))]); } catch (_) {}
      if (wantSetCookie) {
        // Ghép như insta.js getCookies: mỗi dòng Set-Cookie lấy phần name=value đầu, bỏ deleted/rỗng.
        res.setCookie = capturedSetCookies
          .map((e) => e.split(";")[0])
          .filter((p) => { const v = p.split("=").slice(1).join("="); return v && v !== "deleted"; })
          .join("; ");
      }
      if (wantLocation) { res.location = capturedLocation; res.locationStatus = capturedStatus; }
    }
    return res;
  } finally {
    try {
      await chrome.declarativeNetRequest.updateSessionRules({ removeRuleIds: [ruleId] });
    } catch (_) {}
    if (capRegistered) _capRemove(nonce);
  }
}

// ========================================
// TAB MANAGEMENT
// ========================================

/**
 * Tìm tab Facebook đang mở để sử dụng cho fetch operations
 *
 * Ưu tiên tab:
 * 1. Tab đã load xong (status = "complete")
 * 2. Tab bất kỳ nếu không có tab complete
 *
 * @returns {Promise<chrome.tabs.Tab|null>} Tab object hoặc null
 */
// findFacebookTab() được định nghĩa ở dưới (phiên bản đầy đủ hơn)

/**
 * Tìm tab Business Manager để lấy Access Token
 *
 * BM page cần thiết vì access token EAAG chỉ có ở BM,
 * không có ở facebook.com thường.
 *
 * @returns {Promise<chrome.tabs.Tab|null>} Tab object hoặc null
 */
async function findBusinessManagerTab() {
  // Ưu tiên tìm tab business.facebook.com
  const bmTabs = await chrome.tabs.query({
    url: ["https://business.facebook.com/*"],
  });

  if (bmTabs.length > 0) {
    const activeTabs = bmTabs.filter((t) => t.status === "complete");
    const result = activeTabs.length > 0 ? activeTabs[0] : bmTabs[0];
    return result;
  }

  // Fallback: tìm tab facebook thường nếu không có BM tab
  return await findFacebookTab();
}

/**
 * Đảm bảo content script (fb-fetcher.js) đã được inject vào tab
 *
 * Content script cần thiết để thực hiện fetch với cookies từ Facebook page.
 * Nếu chưa có, sẽ inject script vào tab.
 *
 * @param {number} tabId - ID của tab cần kiểm tra
 * @returns {Promise<boolean>} true nếu script đã sẵn sàng
 */
async function ensureContentScriptInjected(tabId) {
  try {
    // Thử gửi ping message để kiểm tra script đã load chưa
    const response = await chrome.tabs.sendMessage(tabId, { action: "ping" });
    return response && response.pong;
  } catch (error) {
    // Script chưa load, thử inject thủ công
    try {
      await chrome.scripting.executeScript({
        target: { tabId },
        files: ["js/content.js"],
      });
      // Đợi script load xong
      await new Promise((resolve) => setTimeout(resolve, 500));
      return true;
    } catch (injectError) {
      console.error("Failed to inject content script:", injectError);
      return false;
    }
  }
}

// ========================================
// CONTENT SCRIPT COMMUNICATION
// ========================================

/**
 * Gửi message đến Facebook tab với retry mechanism
 *
 * Thử gửi message tối đa (retries + 1) lần, mỗi lần cách nhau 500ms.
 * Tự động inject content script nếu chưa có.
 *
 * @param {Object} message - Message object cần gửi
 * @param {number} retries - Số lần retry (default: 2)
 * @returns {Promise<Object>} Response từ content script
 * @throws {Error} Nếu không tìm thấy FB tab hoặc tất cả retries fail
 */
async function sendToFacebookTab(message, retries = 2) {
  const fbTab = await findFacebookTab();

  if (!fbTab) {
    throw new Error("No Facebook tab found. Please open facebook.com");
  }

  // Đảm bảo script đã inject
  const injected = await ensureContentScriptInjected(fbTab.id);

  let lastError;
  for (let i = 0; i <= retries; i++) {
    try {
      const response = await chrome.tabs.sendMessage(fbTab.id, message);
      return response;
    } catch (error) {
      lastError = error;
      if (i < retries) {
        // Đợi và thử lại
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
    }
  }

  throw lastError;
}

/**
 * Inject và thực thi fetch trực tiếp trong MAIN world của tab Facebook
 * Đây là cách giả lập như người dùng đang gõ code trong DevTools console
 * Facebook không thể phát hiện vì code chạy trong context thật của trang
 *
 * @param {number} tabId - ID của tab Facebook
 * @param {string} url - URL cần fetch
 * @param {Object} options - Fetch options
 * @param {string} responseType - "text" | "json"
 * @returns {Promise<Object>} Fetch result
 */
async function executeInPageContext(tabId, url, options, responseType) {
  const result = await chrome.scripting.executeScript({
    target: { tabId: tabId },
    world: "MAIN", // QUAN TRỌNG: Chạy trong MAIN world (như DevTools console)
    func: async (fetchUrl, fetchOptions, respType) => {
      try {
        // Lấy native fetch từ iframe để tránh bị Facebook hook
        // Đây là kỹ thuật "fetch2" - tạo iframe ẩn và dùng fetch của nó
        let nativeFetch = window.fetch;

        try {
          // Tạo iframe ẩn để lấy fetch gốc chưa bị hook
          const iframe = document.createElement("iframe");
          iframe.style.display = "none";
          document.body.appendChild(iframe);
          nativeFetch = iframe.contentWindow.fetch.bind(iframe.contentWindow);
          document.body.removeChild(iframe);
        } catch (e) {
          // Fallback về fetch thường nếu không tạo được iframe
          nativeFetch = window.fetch;
        }

        // Thực hiện fetch với native fetch
        const response = await nativeFetch(fetchUrl, {
          method: fetchOptions.method || "GET",
          headers: fetchOptions.headers || {},
          body: fetchOptions.body || null,
          credentials: "include",
        });

        let data = await response.text();

        if (respType === "json") {
          try {
            // Xóa prefix "for (;;);" của Facebook
            data = JSON.parse(
              data.replace(/^for\s*\(\s*;\s*;\s*\)\s*;?\s*/, ""),
            );
          } catch (e) {
            // Giữ nguyên text nếu không parse được
          }
        }

        return {
          success: true,
          data: data,
          status: response.status,
          ok: response.ok,
          url: response.url,
        };
      } catch (error) {
        return { success: false, error: error.message };
      }
    },
    args: [url, options, responseType],
  });

  if (result && result[0] && result[0].result) {
    return result[0].result;
  }
  throw new Error("Script execution failed");
}

/**
 * Tìm tab Facebook đang mở và đã login
 * @returns {Promise<chrome.tabs.Tab|null>}
 */
async function findFacebookTab() {
  const tabs = await chrome.tabs.query({
    url: ["*://*.facebook.com/*", "*://*.fb.com/*"],
  });

  // Ưu tiên business.facebook.com
  const bmTab = tabs.find(
    (t) => t.url && t.url.includes("business.facebook.com"),
  );
  if (bmTab) return bmTab;

  // Sau đó là www.facebook.com
  const wwwTab = tabs.find((t) => t.url && t.url.includes("www.facebook.com"));
  if (wwwTab) return wwwTab;

  // Bất kỳ tab Facebook nào
  return tabs[0] || null;
}

// ========================================
// RUNNER CỤC BỘ (tool metaOs Runner cài trên máy khách)
// ========================================
// Chrome chỉ nhận MỘT cấu hình proxy cho cả profile, tự ép User-Agent, và dùng chung một cookie jar cho mọi tài
// khoản. Vì vậy request THEO DÒNG được đẩy sang tool chạy ngoài Chrome: mỗi dòng một cookie + một proxy + một UA
// riêng, tách biệt thật. Toàn bộ logic tính năng vẫn ở đây — tool chỉ gửi hộ.
// Tool nghe 127.0.0.1 và chỉ gửi được tới miền Facebook/Instagram, nên không dùng được làm proxy mở.
const _RN_PORT0 = 28450;
const _RN_PORTS = 10;
const _RN_PORT_TTL = 30000; // nhớ cổng 30s; tool restart/đổi cổng thì lần sau dò lại
let _rnState = null; // {ids:{uid:{proxy,ua}}, ts} — trang gửi 1 lần mỗi mẻ
let _rnPort = 0;        // cổng ĐIỀU KHIỂN (/ping) — tool giữ riêng, không nhận /fetch nên không bao giờ kẹt
let _rnFetchPorts = []; // các cổng chia tải /fetch
let _rnRR = 0;          // con trỏ xoay vòng giữa các cổng fetch
let _rnWsCo = false;    // tool có hỗ trợ ghép kênh WebSocket không
let _rnFindMo = null;   // lượt dò đang chạy — gộp mọi lời gọi đồng thời vào đúng một lượt
let _rnHut = 0;         // số nhịp dò LIÊN TIẾP hụt ở cổng đã biết — hụt đủ lâu mới coi là tool dời cổng thật
const _RN_HUT_TOI_DA = 3; // ~90s (3 nhịp TTL) mới mở lại cuộc dò rộng
let _rnPortTs = 0;

async function _rnPingPort(p, ms) {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), ms);
  try {
    const r = await fetch("http://127.0.0.1:" + p + "/ping", { signal: ac.signal, cache: "no-store" });
    if (!r.ok) return null;
    const j = await r.json();
    return j && j.app === "metaos-runner" ? j : null;
  } catch (e) { return null; } finally { clearTimeout(t); }
}

// Dò THEO BẬC, không bắn hết một lượt. Bắn cả dải cùng lúc thì mấy base dự phòng (28500/28550/28600) gần như
// luôn trống → lần dò nào cũng đẻ ra mấy dòng ERR_CONNECTION_REFUSED đỏ chót trong bảng Network, khách tưởng hỏng.
// Theo bậc thì ca bình thường chỉ tốn ĐÚNG MỘT ping vào cổng đã biết.
async function _rnFind(force) {
  const now = Date.now();
  if (!force && _rnPort && now - _rnPortTs < _RN_PORT_TTL) return _rnPort;
  // GỘP các lần dò đồng thời: chạy 100 luồng mà mỗi request tự dò một lượt thì thành bão ping, Chrome cạn
  // socket, ping lại càng hụt — vòng xoáy tự nuôi. Một lượt dò duy nhất, cả đám dùng chung kết quả.
  if (_rnFindMo) return _rnFindMo;
  _rnFindMo = _rnFindThat(force, now).finally(() => { _rnFindMo = null; });
  return _rnFindMo;
}

async function _rnFindThat(force, now) {
  const thuDai = async (ds) => {
    const res = await Promise.all(ds.map((p) => _rnPingPort(p, 3000).then((j) => (j ? { p, j } : null))));
    return res.find((x) => x) || null;
  };

  let hit = null;
  // Bậc 1: cổng đã biết — tool không đổi cổng thì dừng ngay ở đây, không đụng tới cổng trống nào
  if (_rnPort) {
    const j = await _rnPingPort(_rnPort, 3000);
    if (j) hit = { p: _rnPort, j };
    // Tool tự cập nhật (đổi file exe rồi chạy lại) chỉ hụt vài giây rồi về ĐÚNG cổng cũ. Quét lại cả dải ngay lúc
    // đó là đẻ ra cả chục dòng ERR_CONNECTION_REFUSED đỏ chót trong bảng Network — khách tưởng hỏng. Nên nhịp dò
    // THƯỜNG mà hụt thì cứ giữ cổng cũ, chỉ tốn đúng 1 ping; hụt liên tiếp đủ lâu mới coi là tool dời cổng thật.
    // Lượt dò BẮT BUỘC (trang hỏi trạng thái / sắp chạy mẻ) vẫn quét đủ, để không bao giờ báo sai là tool đang chạy.
    if (!hit) {
      _rnHut++;
      if (!force && _rnHut < _RN_HUT_TOI_DA) { _rnPortTs = now; return _rnPort; }
    }
  }
  // Bậc 2: dải chính
  if (!hit) {
    const dai = [];
    for (let i = 0; i < _RN_PORTS; i++) if (_RN_PORT0 + i !== _rnPort) dai.push(_RN_PORT0 + i);
    hit = await thuDai(dai);
  }
  // Bậc 3: base dự phòng — chỉ tới đây khi dải chính cũng trống, tức tool thật sự đã dời base.
  if (!hit) hit = await thuDai([28500, 28550, 28600]);

  if (!hit) {
    _rnPortTs = now;
    // Dò hụt thì GIỮ cổng đã biết: lúc chạy nặng, một nhịp ping quá hạn là chuyện bình thường. Xoá cổng đi là
    // đẩy mọi request sau vào dò lại cả dải — đúng cái vòng xoáy làm ngập bảng Network bằng ping lỗi.
    if (_rnPort) return _rnPort;
    _rnFetchPorts = [];
    return 0;
  }
  // Tool mới tự khai cổng điều khiển + cổng chia tải. Tool CŨ chỉ có 1 cổng → dùng luôn cổng đó cho cả hai việc.
  _rnHut = 0;
  _rnPort = hit.j.cong || hit.p;
  _rnFetchPorts = Array.isArray(hit.j.congFetch) && hit.j.congFetch.length ? hit.j.congFetch.slice() : [_rnPort];
  _rnWsCo = !!hit.j.ws;        // tool có ghép kênh WebSocket không
  _rnLuongCo = !!hit.j.luong;  // tool có kênh nhận–trả tách rời không (đường nhanh nhất, không trần kết nối)
  _rnPortTs = now;
  return _rnPort;
}

// Danh tính của dòng: lấy uid trong cookie để tra proxy/UA mà trang đã gán cho dòng đó.
function _rnIdentity(options) {
  const ck = String((options && options._acctCookie) || "");
  const uid = ck ? _uidFromCookie(ck) : "";
  const map = (_rnState && _rnState.ids) || {};
  if (uid && map[uid]) return { uid, ...map[uid] };
  if (options && options._rnCtx && map[options._rnCtx]) return { uid: options._rnCtx, ...map[options._rnCtx] };
  return { uid: uid || "" };
}

// ───────── Kênh NHẬN–TRẢ TÁCH RỜI: phá trần 6-kết-nối-mỗi-cổng mà không cần WebSocket ─────────
// /submit chỉ giao việc rồi nhả kết nối ngay (~1ms), kết quả chảy về qua MỘT luồng /events mở sẵn. Nhờ vậy không
// request nào giữ kết nối trong lúc chờ Facebook → số luồng song song không còn bị trình duyệt chặn.
let _rnLuongCo = false;     // tool có hỗ trợ kênh này không
let _rnSid = "";            // mã luồng của phiên service worker này
let _rnLuongMo = null;      // promise đang mở luồng (gộp lời gọi đồng thời)
let _rnLuongSong = false;
let _rnLuongSeq = 0;
const _rnLuongCho = new Map(); // id → {resolve, timer}

function _rnLuongDong(lyDo) {
  _rnLuongSong = false; _rnLuongMo = null;
  // Trả lời dứt khoát cho mọi việc đang chờ — KHÔNG bỏ lửng, nếu không dòng lưới kẹt vĩnh viễn
  for (const [, w] of _rnLuongCho) { try { clearTimeout(w.timer); } catch (e) {} w.resolve({ success: false, error: lyDo, rnMissing: true }); }
  _rnLuongCho.clear();
}

// Đọc luồng NDJSON: mỗi dòng là 1 kết quả, ghép theo id
async function _rnLuongDoc(port) {
  const r = await fetch("http://127.0.0.1:" + port + "/events?sid=" + _rnSid, { cache: "no-store" });
  if (!r.ok || !r.body) throw new Error("không mở được luồng kết quả");
  _rnLuongSong = true;
  (async () => {
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let dem = "";
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        dem += dec.decode(value, { stream: true });
        let i;
        while ((i = dem.indexOf("\n")) >= 0) {
          const dong = dem.slice(0, i); dem = dem.slice(i + 1);
          if (!dong) continue;
          let j;
          try { j = JSON.parse(dong); } catch (e) { continue; }
          if (!j || !j.id) continue; // nhịp tim / báo sẵn sàng
          const w = _rnLuongCho.get(j.id);
          if (!w) continue;
          _rnLuongCho.delete(j.id);
          try { clearTimeout(w.timer); } catch (e) {}
          w.resolve(j);
        }
      }
    } catch (e) {}
    _rnLuongDong("luồng kết quả của tool đã đứt");
  })();
}

function _rnLuongKetNoi(port) {
  if (_rnLuongSong) return Promise.resolve(true);
  if (_rnLuongMo) return _rnLuongMo;
  if (!_rnSid) _rnSid = "s" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
  _rnLuongMo = _rnLuongDoc(port).then(() => true).catch((e) => { _rnLuongMo = null; throw e; });
  return _rnLuongMo;
}

// GỘP việc: mọi request phát ra trong cùng một nhịp được gom vào một lần giao. Nếu mỗi việc một POST thì chính
// khâu giao thành nút cổ chai (vẫn 6 khe/cổng), 500 việc mất ~1,6s mới giao xong nên không bao giờ đủ 500 cùng chạy.
const _RN_GOP_TOI_DA = 100; // trần mỗi lần giao, để thân request không phình quá to khi có dữ liệu tải lên
let _rnHangCho = [];
let _rnHenGiao = false;

function _rnGiaoNgay(port) {
  _rnHenGiao = false;
  const lo = _rnHangCho;
  _rnHangCho = [];
  if (!lo.length) return;
  for (let i = 0; i < lo.length; i += _RN_GOP_TOI_DA) {
    const phan = lo.slice(i, i + _RN_GOP_TOI_DA);
    fetch("http://127.0.0.1:" + port + "/submit", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sid: _rnSid, jobs: phan }), cache: "no-store",
    }).then((r) => {
      if (r.ok) return;
      // 409 = tool không còn luồng cho sid này (service worker vừa hồi sinh) → mở lại ở lần sau
      _rnLuongSong = false; _rnLuongMo = null;
      for (const v of phan) _rnTraSom(v.id, { success: false, error: "tool chưa sẵn sàng nhận việc", rnMissing: true });
    }).catch((e) => {
      for (const v of phan) _rnTraSom(v.id, { success: false, error: "không giao được việc cho tool: " + ((e && e.message) || e), rnMissing: true });
    });
  }
}

function _rnTraSom(id, kq) {
  const w = _rnLuongCho.get(id);
  if (!w) return;
  _rnLuongCho.delete(id);
  try { clearTimeout(w.timer); } catch (e) {}
  w.resolve(kq);
}

function _rnLuongGui(port, body) {
  const id = "j" + (++_rnLuongSeq);
  return new Promise((res) => {
    // Hạn 70s > hạn 60s của tool: tool luôn trả trước, hạn này chỉ chống treo khi luồng chết im
    const timer = setTimeout(() => { _rnLuongCho.delete(id); res({ success: false, error: "tool không trả lời (quá 70s)", code: "ETIMEOUT" }); }, 70000);
    _rnLuongCho.set(id, { resolve: res, timer });
    _rnHangCho.push(Object.assign({ id }, body));
    if (!_rnHenGiao) { _rnHenGiao = true; Promise.resolve().then(() => _rnGiaoNgay(port)); }
  });
}

// ───────── Kênh WebSocket tới tool: 1 socket, vô hạn request song song ─────────
// Nhiều cổng HTTP chỉ nâng trần lên ~138 (giới hạn socket của Chrome). WebSocket ghép kênh thì không dính trần
// đó: mọi request đi chung 1 socket, ghép bằng id. Tool cũ không có WS → tự quay về đường HTTP nhiều cổng.
let _rnWs = null;          // socket đang mở
let _rnWsMo = null;        // promise đang mở (gộp các lời gọi đồng thời, tránh mở nhiều socket)
let _rnWsSeq = 0;
const _rnWsCho = new Map(); // id → {resolve, timer}

function _rnWsDong(lyDo) {
  _rnWs = null; _rnWsMo = null;
  // Trả lời dứt khoát cho mọi request đang chờ, KHÔNG treo vĩnh viễn (dòng lưới sẽ kẹt mãi nếu bỏ lửng)
  for (const [, w] of _rnWsCho) { try { clearTimeout(w.timer); } catch (e) {} w.resolve({ success: false, error: lyDo, rnMissing: true }); }
  _rnWsCho.clear();
}

function _rnWsKetNoi(port) {
  if (_rnWs && _rnWs.readyState === 1) return Promise.resolve(_rnWs);
  if (_rnWsMo) return _rnWsMo;
  _rnWsMo = new Promise((res, rej) => {
    let ws;
    try { ws = new WebSocket("ws://127.0.0.1:" + port + "/ws"); } catch (e) { _rnWsMo = null; return rej(e); }
    // Chờ ngắn thôi: máy nào chặn WebSocket (proxy hệ thống, VPN kiểu WARP...) thì bỏ sớm để rơi về đường HTTP,
    // và chỉ ĐÚNG MỘT request đầu phải trả giá này — sau đó _rnWsCo = false nên không thử lại nữa.
    const to = setTimeout(() => { try { ws.close(); } catch (e) {} _rnWsMo = null; rej(new Error("quá hạn mở WebSocket")); }, 2500);
    ws.onopen = () => { clearTimeout(to); _rnWs = ws; res(ws); };
    ws.onerror = () => { clearTimeout(to); _rnWsMo = null; rej(new Error("không mở được WebSocket")); };
    ws.onclose = () => { clearTimeout(to); _rnWsDong("mất kết nối tới tool Runner"); };
    ws.onmessage = (ev) => {
      let j;
      try { j = JSON.parse(ev.data); } catch (e) { return; }
      const w = _rnWsCho.get(j && j.id);
      if (!w) return;
      _rnWsCho.delete(j.id);
      try { clearTimeout(w.timer); } catch (e) {}
      w.resolve(j);
    };
  });
  return _rnWsMo;
}

function _rnWsGui(ws, body) {
  return new Promise((res) => {
    const id = "r" + (++_rnWsSeq);
    // Hạn 65s khớp hạn 60s bên tool: tool luôn trả lời trước, hạn này chỉ để không treo khi socket chết im
    const timer = setTimeout(() => { _rnWsCho.delete(id); res({ success: false, error: "tool không trả lời (quá 65s)", code: "ETIMEOUT" }); }, 65000);
    _rnWsCho.set(id, { resolve: res, timer });
    try { ws.send(JSON.stringify(Object.assign({ id }, body))); }
    catch (e) { _rnWsCho.delete(id); clearTimeout(timer); res({ success: false, error: "không gửi được qua WebSocket", rnMissing: true }); }
  });
}

async function _rnFetchAs(url, options, responseType) {
  const port = await _rnFind(false);
  if (!port) {
    // FAIL-CLOSED: thà báo lỗi còn hơn âm thầm chạy bằng IP máy và cookie jar dùng chung
    return { success: false, error: "Chưa thấy tool Runner đang chạy — hãy mở tool rồi chạy lại", rnMissing: true };
  }
  const id = _rnIdentity(options);
  const o = options || {};
  const headers = {};
  for (const k of Object.keys(o.headers || {})) headers[k] = o.headers[k];
  const body = {
    v: 1,
    ctx: id.uid || "mac-dinh",
    url: String(url),
    method: String(o.method || "GET"),
    headers,
    cookie: o._acctCookie || "",
    ua: id.ua || "",
    referer: o._referer || "",
    origin: o._origin || "",
    proxy: id.proxy || "",
    redirect: o.redirect === "manual" ? "manual" : "follow",
    responseType: responseType || "text",
    captureSetCookie: !!o._captureSetCookie,
    captureLocation: !!o._captureLocation,
  };
  if (o.body_b64) body.body_b64 = String(o.body_b64);
  else if (typeof o.body === "string") body.body = o.body;

  // ƯU TIÊN 1 — kênh nhận–trả tách rời: /submit nhả kết nối ngay, kết quả về qua luồng /events.
  // Đây là đường duy nhất không dính trần 6-kết-nối-mỗi-cổng của Chrome, nên chạy được hàng trăm luồng.
  if (_rnLuongCo) {
    try {
      await _rnLuongKetNoi(port);
      const j = await _rnLuongGui(port, body);
      if (j && j.success === false && /^E(PROXY|407)/.test(String(j.code || ""))) j.rnProxyErr = true;
      if (!(j && j.rnMissing)) return j; // rnMissing = luồng vừa đứt → thử nốt các đường dưới
    } catch (e) {
      _rnLuongCo = false; // không mở được luồng → thôi, dùng đường cũ
    }
  }
  // ƯU TIÊN 2 — WebSocket: 1 socket ghép kênh nên số request song song KHÔNG còn bị trần socket của Chrome chặn.
  if (_rnWsCo) {
    try {
      const ws = await _rnWsKetNoi(port);
      const j = await _rnWsGui(ws, body);
      if (j && j.success === false && /^E(PROXY|407)/.test(String(j.code || ""))) j.rnProxyErr = true;
      return j;
    } catch (e) {
      // Mở WS hỏng (tool vừa tắt, hoặc bản tool không có WS) → rơi xuống đường HTTP bên dưới, không làm hỏng mẻ
      _rnWsCo = false;
    }
  }
  // Dự phòng: chia đều qua các cổng fetch. Chrome tính trần kết nối theo TỪNG host:port, nên nhiều cổng = nhiều
  // luồng hơn, và cổng điều khiển không bị request chiếm chỗ (/ping không bị kẹt sau request treo).
  const fp = _rnFetchPorts.length ? _rnFetchPorts : [port];
  const pFetch = fp[_rnRR++ % fp.length];
  try {
    const r = await fetch("http://127.0.0.1:" + pFetch + "/fetch", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), cache: "no-store",
    });
    const j = await r.json();
    if (j && j.success === false && /^E(PROXY|407)/.test(String(j.code || ""))) j.rnProxyErr = true;
    return j;
  } catch (e) {
    // Buộc dò lại ở lần sau nhưng GIỮ cổng đang biết: xoá cổng thì 100 luồng cùng lúc sẽ cùng dò lại cả dải —
    // đúng cái bão ping. Hết hạn bộ nhớ là đủ để kiểm lại, mà vẫn chỉ tốn 1 ping nhờ gộp lượt dò.
    _rnPortTs = 0;
    return { success: false, error: "Không gọi được tool Runner: " + ((e && e.message) || e), rnMissing: true };
  }
}

/**
 * Thực hiện fetch với fallback strategy
 *
 * Strategy: Fetch trực tiếp từ Service Worker (như extension gốc)
 * Service Worker có host_permissions nên bypass được CORS
 *
 * @param {string} url - URL cần fetch
 * @param {Object} options - Fetch options
 * @param {string} responseType - Loại response
 * @returns {Promise<Object>} Fetch result
 */
async function performFetch(url, options, responseType) {
  // clone-tao-bm: chạy AS account khác bằng cookie truyền vào (đa luồng cookie-pool).
  // Đi path riêng (SW-initiated, KHÔNG fallback tab). Request không có _acctCookie/_captureSetCookie
  // giữ NGUYÊN hành vi cũ bên dưới — isolation tuyệt đối.
  if (options && (options._acctCookie || options._captureSetCookie || options._pxSlot != null)) {
    // Mẻ đang bật tool cục bộ → đẩy sang tool (ngoài Chrome: proxy + UA + cookie riêng từng dòng, tách biệt thật).
    // Không có _rnState = trang chưa bật → giữ nguyên đường cũ trong Chrome.
    if (_rnState) return await _rnFetchAs(url, options, responseType);
    return await fbFetchAs(url, options, responseType);
  }

  // Request FB không-cookie cũng PHẢI qua proxy (per-request guarantee, chống SW tái sinh làm lọt).
  try { if (/facebook\.com|instagram\.com|fb\.com/.test(String(url || ""))) await _ensureGroupProxy(); } catch (e) {}

  // ⚠ CẢ BA chiến lược đều từng vứt lý do thất bại: nhánh !success bỏ luôn result.error, còn
  // nhánh catch để trống. Kết quả là khách chỉ nhận đúng câu "All fetch methods failed" — vô nghĩa,
  // trong khi lý do thật rất cụ thể và khách tự sửa được (thường là chưa mở tab facebook.com).
  const why = [];
  const note = (n, v) => { const s = String((v && v.message) || v || "").trim(); if (s) why.push("(" + n + ") " + s.slice(0, 120)); };

  // Ưu tiên 1: Fetch trực tiếp từ Service Worker với credentials
  try {
    const result = await fetchWithCookies(url, options, responseType);
    if (result && result.success) {
      return result;
    }
    note(1, result && result.error);
  } catch (error) {
    note(1, error);
  }

  // Ưu tiên 2: Thử qua content script trên Facebook tab
  try {
    const response = await sendToFacebookTab({
      action: "fb-fetch",
      url,
      options,
      responseType,
    });
    if (response && response.success) {
      return response;
    }
    note(2, response && response.error);
  } catch (error) {
    note(2, error);
  }

  // Ưu tiên 3: Inject và fetch trong MAIN world của Facebook tab
  try {
    const fbTab = await findFacebookTab();
    if (fbTab) {
      const result = await executeInPageContext(
        fbTab.id,
        url,
        options,
        responseType,
      );
      if (result && result.success) {
        return result;
      }
      note(3, result && result.error);
    } else {
      // Trường hợp PHỔ BIẾN NHẤT và khách tự sửa được — trước đây im lặng tuyệt đối.
      note(3, "Không có tab facebook.com nào đang mở — hãy mở sẵn 1 tab facebook.com rồi chạy lại");
    }
  } catch (error) {
    note(3, error);
  }

  return {
    success: false,
    error: "All fetch methods failed" + (why.length ? " — " + why.join(" · ") : ""),
  };
}

// ========================================
// MESSAGE HANDLERS
// ========================================

/**
 * Main Message Handler
 *
 * Nhận và xử lý tất cả messages từ:
 * - Content scripts (bridge.js, fb-fetcher.js)
 * - Extension popup
 * - Web pages (thông qua bridge)
 *
 * Pattern: Action-based routing với async response
 */
let _ssCursorTab = null; // tab đang quay screen-studio — đích relay toạ độ chuột từ các tab khác

// ===== OWA (Outlook Web) — đọc OTP qua tab nền, dùng phiên đăng nhập sẵn trong Chrome =====
// Mở 1 tab outlook.live.com nền (active:false), TÁI DÙNG; content.js (nhánh outlook) cào OTP/link
// từ DOM rồi trả về. KHÔNG cần mật khẩu. Tái dùng thì reload cho chắc có mail mới nhất.
let _owaTabId = null;
const _owaUrl = "https://outlook.live.com/mail/0/";
const _owaSleep = (ms) => new Promise((r) => setTimeout(r, ms));
function _owaWait(tabId, timeout) {
  return new Promise((resolve) => {
    let done = false;
    const fin = (ok) => { if (done) return; done = true; try { chrome.tabs.onUpdated.removeListener(onUpd); } catch (e) {} resolve(ok); };
    const onUpd = (id, info) => { if (id === tabId && info && info.status === "complete") fin(true); };
    try { chrome.tabs.onUpdated.addListener(onUpd); } catch (e) { return resolve(false); }
    setTimeout(() => fin(false), timeout || 45000);
  });
}
function _owaSend(tabId, msg, timeout) {
  return new Promise((resolve) => {
    let done = false; const fin = (v) => { if (!done) { done = true; resolve(v); } };
    try { chrome.tabs.sendMessage(tabId, msg, (res) => { void chrome.runtime.lastError; fin(res || null); }); } catch (e) { fin(null); }
    setTimeout(() => fin(null), timeout || 20000);
  });
}
async function _owaAlive(tabId) { if (!tabId) return false; try { return !!(await chrome.tabs.get(tabId)); } catch (e) { return false; } }
// ⚠ Tìm tab Outlook ĐANG MỞ SẴN (của user hoặc phiên trước) để DÙNG LẠI — KHÔNG đẻ tab mới mỗi lần (user yêu cầu).
// Ưu tiên tab /mail/ và tab NỀN (active:false, đỡ làm phiền) hơn tab user đang xem.
async function _owaFindTab() {
  try {
    const tabs = await chrome.tabs.query({ url: ["*://outlook.live.com/*", "*://outlook.office.com/*", "*://outlook.office365.com/*"] });
    if (!tabs || !tabs.length) return null;
    const mail = tabs.filter((t) => /\/mail\//.test(t.url || ""));
    const pool = mail.length ? mail : tabs;
    const bg = pool.find((t) => !t.active);
    return (bg || pool[0]).id;
  } catch (e) { return null; }
}
async function _owaReadOtp(opts) {
  const sender = (opts && opts.sender) || "facebook";
  const email = (opts && opts.email) || "";
  let reused = await _owaAlive(_owaTabId);
  if (!reused) {
    const found = await _owaFindTab();   // có tab outlook sẵn → dùng lại, không mở mới
    if (found) { _owaTabId = found; reused = true; }
  }
  if (!reused) {
    const tab = await chrome.tabs.create({ url: _owaUrl, active: false });
    _owaTabId = tab.id;
    await _owaWait(_owaTabId, 45000);
    await _owaSleep(3500); // chờ inbox render
  } else {
    // Tab đang xem (active) → KHÔNG reload lặp (làm phiền user); chỉ đưa về /mail/0/ nếu đang ở trang khác, dựa live-update.
    // Tab nền → reload cho chắc có mail mới nhất.
    let t = null; try { t = await chrome.tabs.get(_owaTabId); } catch (e) {}
    if (t && t.active) {
      if (!/\/mail\//.test(t.url || "")) { try { await chrome.tabs.update(_owaTabId, { url: _owaUrl }); await _owaWait(_owaTabId, 45000); } catch (e) {} }
      await _owaSleep(2500);
    } else {
      try { await chrome.tabs.reload(_owaTabId); } catch (e) {}
      await _owaWait(_owaTabId, 45000);
      await _owaSleep(3000);
    }
  }
  let res = await _owaSend(_owaTabId, { action: "owaScrapeOtp", email: email, sender: sender }, 20000);
  if (!res) { await _owaSleep(1800); res = await _owaSend(_owaTabId, { action: "owaScrapeOtp", email: email, sender: sender }, 20000); }
  if (!res) return { success: false, error: "Không đọc được tab Outlook (có thể chưa đăng nhập hoặc trang chưa tải xong)" };
  return res;
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  // ===== PING - Wake up Service Worker =====
  /**
   * ACTION: ping
   * Đơn giản trả về pong để wake up Service Worker
   * và xác nhận Service Worker đang hoạt động
   */
  if (request.action === "ping") {
    sendResponse({ pong: true });
    return true;
  }

  if (request.action === "checkLive") {
    collectMetaOsSession(false).then((session) => {
      sendResponse({ success: session.success, uid: session.uid, live: session.success });
    });
    return true;
  }

  if (request.action === "getAccessToken" || request.action === "getTokens") {
    collectMetaOsSession(true).then(sendResponse).catch((error) => {
      sendResponse({ success: false, error: error && error.message ? error.message : "Không đọc được phiên Meta" });
    });
    return true;
  }

  // ===== OWA READ OTP — mở tab Outlook nền, cào OTP từ phiên đăng nhập sẵn =====
  if (request.action === "owaReadOtp") {
    (async () => {
      try { sendResponse(await _owaReadOtp({ email: request.email, sender: request.sender })); }
      catch (e) { sendResponse({ success: false, error: (e && e.message) || "owa error" }); }
    })();
    return true;
  }

  // ===== META AI PROBE (Bước 1 — thử: chạy Meta.ai NGẦM từ nền extension, không mở tab) =====
  // Mục tiêu: xác minh WebSocket DGW mở TỪ NỀN (Chrome TLS thật) + cookie khách (chèn qua DNR)
  // có qua được pre-auth của Meta không (server Node bị 4005 vì TLS không phải browser).
  // Trả report: cookie khách, lấy token được không, kết quả WS (estab code 200 = QUA, close 4005 = chặn).
  if (request.action === "metaAiProbe") {
    (async () => {
      const report = {};
      const RULE_ID = 2900001;
      try {
        // 1) Cookie meta.ai của khách (chrome.cookies đọc được cả httpOnly)
        let cks = [];
        try { cks = await chrome.cookies.getAll({ domain: "meta.ai" }); } catch (e) { report.cookieErr = e.message; }
        const cookieStr = (cks || []).map((c) => c.name + "=" + c.value).join("; ");
        report.cookieCount = (cks || []).length;
        report.hasEcto = /(^|;\s*)ecto_1_sess=/.test(cookieStr);

        // 2) Lấy token + viewerId từ HTML meta.ai (SW fetch = Chrome TLS + cookie jar)
        let html = "";
        try {
          const res = await fetch("https://www.meta.ai/", { credentials: "include", headers: { Accept: "text/html" } });
          report.htmlStatus = res.status;
          html = await res.text();
        } catch (e) { report.fetchErr = e.message; }
        const tokenM = html.match(/ecto1:[A-Za-z0-9_.\-:=]+/);
        const viewerM = html.match(/"viewerId"\s*:\s*"(\d{5,})"/) || html.match(/viewerId[\\"':\s]{1,8}(\d{5,})/);
        const token = tokenM ? tokenM[0] : "";
        report.tokenFound = !!token;
        report.tokenLen = token.length;
        report.viewerId = viewerM ? viewerM[1] : "";
        if (!token) { sendResponse({ success: true, report }); return; }

        // 3+4) Thử mở WS DGW từ nền với vài tổ hợp header (chèn qua DNR), tìm tổ hợp qua pre-auth.
        // Nghi phạm chính: Origin phải = https://www.meta.ai (WS từ nền mặc định Origin chrome-extension://).
        const mkParams = (nonce) => new URLSearchParams({
          "x-dgw-appid": "1522763855472543", "x-dgw-appversion": "1.0.0", "x-dgw-authtype": "15:0",
          "x-dgw-version": "5", "x-dgw-uuid": "0", "x-dgw-tier": "prod", Authorization: token,
          "x-dgw-app-origin": "meta.ai", "x-dgw-app-clippy-request-id": crypto.randomUUID(), __wsmai: nonce,
        }).toString();
        const tryWs = (url) => new Promise((resolve) => {
          let done = false; const fin = (o) => { if (!done) { done = true; resolve(o); } };
          const to = setTimeout(() => fin({ outcome: "timeout" }), 12000);
          let ws;
          try { ws = new WebSocket(url); } catch (e) { clearTimeout(to); return fin({ outcome: "ctor_err", err: e.message }); }
          ws.binaryType = "arraybuffer";
          ws.onopen = () => {
            try {
              const body = new TextEncoder().encode(JSON.stringify({
                "x-dgw-app-x-ecto-conversation-id": crypto.randomUUID(),
                "x-dgw-app-client-payload-type": "PROTO_INSIDE_JSON",
              }));
              const f = new Uint8Array(6 + body.length);
              f[0] = 0x0f; f[3] = body.length & 0xff; f[4] = (body.length >> 8) & 0xff; f[5] = (body.length >> 16) & 0xff;
              f.set(body, 6); ws.send(f);
            } catch (e) { fin({ outcome: "send_err", err: e.message }); }
          };
          ws.onmessage = (ev) => {
            try {
              const b = new Uint8Array(ev.data);
              if (b[0] === 0x0f) {
                const j = JSON.parse(new TextDecoder().decode(b.subarray(6)));
                clearTimeout(to); try { ws.close(); } catch (e) {}
                fin({ outcome: "estab", code: j.code });
              }
            } catch (e) {}
          };
          ws.onclose = (ev) => { clearTimeout(to); fin({ outcome: "close", code: ev.code, reason: ev.reason }); };
          ws.onerror = () => {};
        });
        const ORIGIN = { header: "origin", operation: "set", value: "https://www.meta.ai" };
        const COOKIE = { header: "cookie", operation: "set", value: cookieStr };
        const combos = [
          { name: "cookie+origin", headers: [COOKIE, ORIGIN] },
          { name: "origin_only", headers: [ORIGIN] },
        ];
        report.wsTries = [];
        for (const combo of combos) {
          const nonce = "wsmai" + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
          try {
            await chrome.declarativeNetRequest.updateSessionRules({
              removeRuleIds: [RULE_ID],
              addRules: [{ id: RULE_ID, priority: 3, action: { type: "modifyHeaders", requestHeaders: combo.headers }, condition: { initiatorDomains: [chrome.runtime.id], urlFilter: "__wsmai=" + nonce, resourceTypes: ["websocket"] } }],
            });
          } catch (e) { report.wsTries.push({ combo: combo.name, dnrErr: e.message }); continue; }
          const outcome = await tryWs("wss://gateway.meta.ai/ws/clippy?" + mkParams(nonce));
          try { await chrome.declarativeNetRequest.updateSessionRules({ removeRuleIds: [RULE_ID] }); } catch (e) {}
          report.wsTries.push({ combo: combo.name, ...outcome });
          if (outcome.outcome === "estab" && outcome.code === 200) { report.winner = combo.name; break; }
        }
        sendResponse({ success: true, report });
      } catch (e) {
        report.fatal = e.message;
        try { await chrome.declarativeNetRequest.updateSessionRules({ removeRuleIds: [RULE_ID] }); } catch (_) {}
        sendResponse({ success: false, report, error: e.message });
      }
    })();
    return true;
  }

  // ===== META AI PAGE-WS SETUP (thử hướng: WS mở TỪ TRANG FIOX, DNR sửa Origin+Cookie) =====
  // Khác metaAiProbe (WS mở từ service worker): ở đây SW chỉ lấy token + dựng rule DNR (match theo
  // nonce, KHÔNG giới hạn initiator) rồi trả token+nonce để TRANG tự mở WS. Vì DNR áp cho request
  // của trang (không chắc áp cho request của SW) nên Origin/Cookie mới thực sự được ghi đè.
  if (request.action === "metaAiPageWsSetup") {
    (async () => {
      const out = {};
      const RID = 2900002;
      try {
        let cks = [];
        try { cks = await chrome.cookies.getAll({ domain: "meta.ai" }); } catch (e) { out.cookieErr = e.message; }
        const cookieStr = (cks || []).map((c) => c.name + "=" + c.value).join("; ");
        out.cookieCount = (cks || []).length;
        let html = "";
        try { const res = await fetch("https://www.meta.ai/", { credentials: "include", headers: { Accept: "text/html" } }); out.htmlStatus = res.status; html = await res.text(); } catch (e) { out.fetchErr = e.message; }
        const tokenM = html.match(/ecto1:[A-Za-z0-9_.\-:=]+/);
        const viewerM = html.match(/"viewerId"\s*:\s*"(\d{5,})"/) || html.match(/viewerId[\\"':\s]{1,8}(\d{5,})/);
        const token = tokenM ? tokenM[0] : "";
        const viewerId = viewerM ? viewerM[1] : "";
        out.tokenFound = !!token;
        if (!token) { sendResponse({ success: true, out }); return; }
        const nonce = "wsmaipg" + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
        try {
          await chrome.declarativeNetRequest.updateSessionRules({
            removeRuleIds: [RID],
            addRules: [{
              id: RID, priority: 3,
              action: { type: "modifyHeaders", requestHeaders: [
                { header: "cookie", operation: "set", value: cookieStr },
                { header: "origin", operation: "set", value: "https://www.meta.ai" },
              ] },
              condition: { urlFilter: "__wsmaipg=" + nonce, resourceTypes: ["websocket"] },
            }],
          });
        } catch (e) { out.dnrErr = e.message; }
        setTimeout(() => { try { chrome.declarativeNetRequest.updateSessionRules({ removeRuleIds: [RID] }); } catch (e) {} }, 60000);
        // token + nonce trả cho TRANG tự mở WS (snippet chỉ in outcome, không in token)
        sendResponse({ success: true, token, viewerId, nonce, out });
      } catch (e) {
        sendResponse({ success: false, error: e.message, out });
      }
    })();
    return true;
  }

  // ===== fxGetLang — ngôn ngữ app cho iframe panel cross-site =====
  // content.js (chạy trên facebook.com) không đọc được cookie máy chủ; iframe panel (/popup, /bm-popup.html)
  // nhúng cross-site nên cookie fiox_lang KHÔNG tới server → phải truyền ?lang=. Đọc cookie fiox_lang của
  // apiBase qua chrome.cookies rồi trả về để content.js nối vào src.
  if (request.action === "fxGetLang") {
    (async () => {
      let lang = "";
      try {
        await loadApiBase();
        if (apiBase) {
          const ck = await chrome.cookies.get({ url: apiBase, name: "fiox_lang" });
          if (ck && ck.value) lang = ck.value;
        }
      } catch (e) {}
      try { sendResponse({ lang: lang }); } catch (e) {}
    })();
    return true; // async sendResponse
  }

  // ===== SCREEN-STUDIO cursor tracking (auto-zoom đa-tab, giống Captist) =====
  // page(screen-studio) → cursor.start: nhớ tab quay, bật tracking ở MỌI tab khác.
  // content.js mỗi tab → cursor.event: relay về đúng tab quay (cursor.deliver). CHỈ toạ độ, không nội dung.
  if (request.action === "cursor.start") {
    _ssCursorTab = sender && sender.tab && sender.tab.id;
    try { chrome.storage.local.set({ ssCursorTab: _ssCursorTab }); } catch (e) {}
    chrome.tabs.query({}, (tabs) => {
      let n = 0; // số tab web (khác tab quay) được bật tracking → page báo cho user biết đang bám ở đâu
      tabs.forEach((t) => {
        if (t.id == null || t.id === _ssCursorTab || !/^(https?|file):/.test(t.url || "")) return;
        n++;
        try { chrome.tabs.sendMessage(t.id, { action: "cursor.enable" }, () => void chrome.runtime.lastError); } catch (e) {}
      });
      sendResponse({ success: true, enabled: n });
    });
    return true;
  }
  if (request.action === "cursor.stop") {
    chrome.tabs.query({}, (tabs) => {
      tabs.forEach((t) => {
        if (t.id != null) { try { chrome.tabs.sendMessage(t.id, { action: "cursor.disable" }, () => void chrome.runtime.lastError); } catch (e) {} }
      });
    });
    _ssCursorTab = null;
    try { chrome.storage.local.remove("ssCursorTab"); } catch (e) {}
    sendResponse({ success: true });
    return true;
  }
  if (request.action === "cursor.event") {
    const _relay = (tid) => {
      if (tid == null) return;
      try { chrome.tabs.sendMessage(tid, { action: "cursor.deliver", kind: request.kind, x: request.x, y: request.y, vw: request.vw, vh: request.vh, t: request.t }, () => void chrome.runtime.lastError); } catch (e) {}
    };
    if (_ssCursorTab != null) _relay(_ssCursorTab);
    else { try { chrome.storage.local.get(["ssCursorTab"], (st) => { _ssCursorTab = st && st.ssCursorTab; _relay(_ssCursorTab); }); } catch (e) {} }
    return false;
  }

  // ===== FETCH ACTIONS =====

  /**
   * ACTION: fetch
   * Thực hiện fetch request với cookies
   * Có fallback qua content script nếu Service Worker fail
   *
   * @param {string} request.url - URL cần fetch
   * @param {Object} request.options - Fetch options
   * @param {string} request.responseType - "text" | "json" | "blob"
   * @returns {Object} {success, data, url, status, ok}
   */
  if (request.action === "fetch") {
    (async () => {
      try {
        const response = await performFetch(
          request.url,
          request.options || {},
          request.responseType || "text",
        );
        sendResponse(response);
      } catch (error) {
        console.error("Fetch failed:", error);
        sendResponse({ success: false, error: error.message });
      }
    })();
    return true;
  }

  // ACTION: setupAcctLists — page gửi uaList + proxyList (1 lần đầu mẻ clone) → build PAC + UA.
  if (request.action === "setupAcctLists") {
    try {
      setupAcctLists(request.uaList || []);
      sendResponse({ success: true });
    } catch (error) {
      sendResponse({ success: false, error: error.message });
    }
    return true;
  }

  // ACTION: setGroupProxy — B2: set 1 proxy GLOBAL cho nhóm hiện tại (host-based PAC FB/IG).
  if (request.action === "setGroupProxy") {
    (async () => {
      try {
        await setGroupProxy(request.proxy || "");
        sendResponse({ success: true });
      } catch (error) {
        sendResponse({ success: false, error: error.message });
      }
    })();
    return true;
  }

  // ACTION: setProxySlots — proxy RIÊNG từng tài khoản (port-slot): page gửi phiên multiplexer 1 lần/mẻ + mỗi lần gia hạn.
  // ACTION: runnerStatus — trang hỏi tool cục bộ có đang chạy không (để hiện cảnh báo "chưa cài" trước khi chạy mẻ).
  if (request.action === "runnerStatus") {
    (async () => {
      const port = await _rnFind(true); // luôn dò lại: khách vừa mở tool xong là thấy ngay, không phải chờ hết TTL
      if (!port) return sendResponse({ success: true, running: false });
      const j = await _rnPingPort(port, 3000);
      sendResponse({ success: true, running: !!j, port, info: j || null });
    })();
    return true;
  }

  // ACTION: setRunner — trang bật tool cho mẻ này và gửi bảng danh tính: uid → {proxy, ua}.
  // Gửi lại mỗi mẻ (và mỗi lần gia hạn) vì service worker MV3 ngủ là mất hết biến trong bộ nhớ.
  if (request.action === "setRunner") {
    (async () => {
      const cfg = request.cfg || {};
      const ids = {};
      for (const k of Object.keys(cfg.ids || {})) {
        const v = cfg.ids[k] || {};
        ids[String(k)] = { proxy: String(v.proxy || ""), ua: String(v.ua || "") };
      }
      _rnState = { ids, ts: Date.now() };
      const port = await _rnFind(true);
      // Bật mà không có tool thì nói ngay, đừng để từng dòng mới báo lỗi lẻ tẻ
      sendResponse({ success: !!port, port, running: !!port, error: port ? "" : "chưa thấy tool Runner đang chạy" });
    })();
    return true;
  }

  // ACTION: endRunner — kết mẻ / rời trang: bỏ bảng danh tính để request lẻ sau đó không mang proxy của mẻ cũ.
  if (request.action === "endRunner") {
    _rnState = null;
    sendResponse({ success: true });
    return true;
  }

  if (request.action === "setProxySlots") {
    (async () => {
      try {
        await setProxySlots(request.cfg || {});
        sendResponse({ success: true });
      } catch (error) {
        sendResponse({ success: false, error: error.message });
      }
    })();
    return true;
  }

  // ACTION: endProxySlots — trang kết thúc chế độ port-slot: bỏ phiên + dấu bắt buộc + PAC của ta.
  if (request.action === "endProxySlots") {
    (async () => {
      try {
        await endProxySlots();
        sendResponse({ success: true });
      } catch (error) {
        sendResponse({ success: false, error: error.message });
      }
    })();
    return true;
  }

  // ACTION: clearAcctLists — kết thúc mẻ → xóa PAC + UA + auth (proxy về DIRECT).
  if (request.action === "clearAcctLists") {
    (async () => {
      try {
        await clearAcctLists();
        sendResponse({ success: true });
      } catch (error) {
        sendResponse({ success: false, error: error.message });
      }
    })();
    return true;
  }

  /**
   * ACTION: BGrequest
   * Legacy request handler - Fetch URL và trả về JSON trực tiếp
   * Dùng cho login.js để lấy 2FA token từ 2fa.live API
   *
   * @param {string} request.url - URL cần fetch
   * @returns {Object} JSON response trực tiếp từ API (không wrapper)
   */
  if (request.action === "BGrequest") {
    (async () => {
      try {
        // Legacy behavior: fetch và trả về JSON trực tiếp
        const response = await fetch(request.url);
        const data = await response.json();
        sendResponse(data); // Trả về data trực tiếp, không wrapper
      } catch (error) {
        sendResponse({ error: error.message });
      }
    })();
    return true;
  }

  // ===== COOKIE ACTIONS =====

  /**
   * ACTION: getCookies
   * Lấy tất cả cookies của một domain
   *
   * @param {string} request.domain - Domain cần lấy cookies (default: .facebook.com)
   * @returns {Object} {success, cookies: string}
   */
  if (request.action === "getCookies") {
    chrome.cookies.getAll(
      { domain: request.domain || ".facebook.com" },
      (cookies) => {
        const cookieString = cookies
          .map((c) => `${c.name}=${c.value}`)
          .join("; ");
        sendResponse({ success: true, cookies: cookieString });
      },
    );
    return true;
  }

  /**
   * ACTION: emptyCookie
   * Xóa tất cả cookies của một domain
   *
   * @param {string} request.domain - Domain cần xóa cookies (default: facebook.com)
   * @returns {Object} {success: boolean}
   */
  if (request.action === "emptyCookie") {
    (async () => {
      try {
        const domain = request.domain || "facebook.com";
        const cookies = await chrome.cookies.getAll({ domain: "." + domain });

        for (const cookie of cookies) {
          const url = `https://${cookie.domain.replace(/^\./, "")}${
            cookie.path
          }`;
          await chrome.cookies.remove({ url, name: cookie.name });
        }

        sendResponse({ success: true });
      } catch (error) {
        sendResponse({ success: false, error: error.message });
      }
    })();
    return true;
  }

  /**
   * ACTION: setCookie
   * Set một cookie
   *
   * @param {string} request.url - URL của cookie
   * @param {string} request.domain - Domain của cookie
   * @param {string} request.name - Tên cookie
   * @param {string} request.value - Giá trị cookie
   * @returns {Object} {success: boolean}
   */
  if (request.action === "setCookie") {
    (async () => {
      try {
        await chrome.cookies.set({
          url: request.url || "https://www.facebook.com",
          domain: request.domain || ".facebook.com",
          name: request.name,
          value: request.value,
          path: "/",
          expirationDate:
            request.expirationDate ||
            Math.floor(Date.now() / 1000) + 86400 * 365,
        });
        sendResponse({ success: true });
      } catch (error) {
        sendResponse({ success: false, error: error.message });
      }
    })();
    return true;
  }

  // ===== EXTENSION INFO ACTIONS =====

  /**
   * ACTION: getManifest
   * Lấy thông tin manifest của extension
   *
   * @returns {Object} {success, manifest}
   */
  if (request.action === "getManifest") {
    sendResponse({ success: true, manifest: chrome.runtime.getManifest() });
    return true;
  }

  /**
   * ACTION: openTab
   * Mở URL trong tab mới
   *
   * @param {string} request.url - URL cần mở
   * @returns {Object} {success: boolean}
   */
  if (request.action === "openTab") {
    chrome.tabs.create({ url: request.url });
    sendResponse({ success: true });
    return true;
  }

  /**
   * ACTION: openWindow
   * Mở URL trong CỬA SỔ popup tách rời (dùng cho Bảng IG của "Kích BM Vô Hạn").
   * Cửa sổ ĐÃ MỞ SẴN (cùng origin + đường dẫn) thì ĐƯA LÊN TRƯỚC (khôi phục nếu đang thu nhỏ), KHÔNG mở thêm.
   * ⚠ Tìm theo URL THẬT của các tab đang mở chứ KHÔNG nhớ id cửa sổ trong biến: service worker MV3 ngủ sau ~30s
   * là mất sạch biến → bản cũ (map id trong globalThis) mở TRÙNG cửa sổ thứ 2. Cần quyền "tabs" (đã có) để đọc tab.url.
   *
   * @param {string} request.url - URL cần mở
   * @param {number} request.width/height - kích thước cửa sổ
   * @returns {Object} {success: boolean, reused?: boolean}
   */
  if (request.action === "openWindow") {
    (async () => {
      try {
        const norm = (u) => { try { const x = new URL(u); return x.origin + x.pathname; } catch (e) { return String(u || ""); } };
        const want = norm(request.url);
        const wins = await chrome.windows.getAll({ populate: true });
        const hit = wins.find((w) => w.type === "popup" && (w.tabs || []).some((t) => norm(t.url || t.pendingUrl) === want));
        if (hit) {
          await chrome.windows.update(hit.id, hit.state === "minimized" ? { state: "normal", focused: true } : { focused: true });
          sendResponse({ success: true, reused: true });
          return;
        }
        await chrome.windows.create({ url: request.url, type: "popup", width: request.width || 980, height: request.height || 680, focused: true });
        sendResponse({ success: true });
      } catch (e) { try { sendResponse({ success: false, error: e.message }); } catch (_) {} }
    })();
    return true;
  }

  // ===== STORAGE ACTIONS =====

  /**
   * ACTION: storage.get
   * Đọc data từ chrome.storage.local
   *
   * @param {string|Array} request.keys - Key(s) cần đọc
   * @returns {Object} {success, data}
   */
  if (request.action === "storage.get") {
    chrome.storage.local.get(request.keys, (result) => {
      sendResponse({ success: true, data: result });
    });
    return true;
  }

  /**
   * ACTION: storage.set
   * Ghi data vào chrome.storage.local
   *
   * @param {Object} request.data - Object chứa key-value pairs
   * @returns {Object} {success}
   */
  if (request.action === "storage.set") {
    chrome.storage.local.set(request.data, () => {
      sendResponse({ success: true });
    });
    return true;
  }

  /**
   * ACTION: storage.remove
   * Xóa data từ chrome.storage.local
   *
   * @param {string|Array} request.keys - Key(s) cần xóa
   * @returns {Object} {success}
   */
  if (request.action === "storage.remove") {
    chrome.storage.local.remove(request.keys, () => {
      sendResponse({ success: true });
    });
    return true;
  }

  /**
   * ACTION: fetchWithCookies
   * Fetch trực tiếp từ Service Worker với cookies
   * Không có fallback như action "fetch"
   *
   * @param {string} request.url - URL cần fetch
   * @param {Object} request.options - Fetch options
   * @param {string} request.responseType - "text" | "json" | "blob"
   * @returns {Object} Fetch result
   */
  if (request.action === "fetchWithCookies") {
    (async () => {
      try {
        const response = await fetchWithCookies(
          request.url,
          request.options || {},
          request.responseType || "text",
        );
        sendResponse(response);
      } catch (error) {
        sendResponse({ success: false, error: error.message });
      }
    })();
    return true;
  }

  /**
   * ACTION: graphqlRequest
   * Thực hiện GraphQL request đến Facebook API
   * Tự động set Content-Type header
   *
   * @param {string} request.url - GraphQL endpoint URL
   * @param {string} request.body - Request body (form-urlencoded)
   * @param {Object} request.headers - Additional headers
   * @returns {Object} GraphQL response
   */
  if (request.action === "graphqlRequest") {
    (async () => {
      try {
        const options = {
          method: "POST",
          headers: {
            "content-type": "application/x-www-form-urlencoded",
            ...request.headers,
          },
          body: request.body,
        };
        const response = await fetchWithCookies(request.url, options, "text");
        sendResponse(response);
      } catch (error) {
        sendResponse({ success: false, error: error.message });
      }
    })();
    return true;
  }

  // BM Security setup không cần message protocol — background lắng nghe
  // chrome.storage.onChanged tự setup/clear alarm khi tab BM ghi config.
});

// ========================================
// BM SECURITY MONITOR — chạy ngầm dù tab BM đóng
// ========================================
// Background đọc config từ chrome.storage.local (key 'bmSec_<uid>'):
//   { enabled, bmIds:[], snapshot:{bmId:[users]}, lastCheck:ts }
// Mỗi 30 phút (qua chrome.alarms) snapshot lại admin từng BM, diff cũ vs mới,
// có thay đổi → gửi /api/zalo/notify. Tab BM đóng vẫn chạy được vì:
//   - fetchWithCookies dùng cookies FB trực tiếp (no need access_token/dtsg)
//   - HTML scrape endpoint `latest/settings/business_users?business_id=...`
//     trả về JSON preload đủ data (users + role + email + last_active)

const BM_SEC_ALARM_PREFIX = "bmSec_";
const BM_SEC_DEFAULT_PERIOD_MIN = 30;
function _bmSecPeriod(cfg) {
  const m = cfg && Number(cfg.intervalMin);
  return m && m > 0 ? m : BM_SEC_DEFAULT_PERIOD_MIN;
}

// Normalize role text (HTML scrape trả VN tùy locale user) → diff đồng nhất.
const _BG_BM_SEC_ROLE_MAP = {
  "toàn quyền kiểm soát": "Full control",
  "kiểm soát toàn bộ": "Full control",
  "quyền truy cập đầy đủ": "Full control",
  "quyền truy cập tiêu chuẩn": "Standard access",
  "quyền truy cập nâng cao": "Advanced access",
  "quyền truy cập cơ bản": "Basic access",
  "hạn chế": "Limited",
  "tuỳ chỉnh": "Custom",
  "tùy chỉnh": "Custom",
  "không có quyền": "No access",
  "kế toán viên": "Accountant",
  "nhân viên": "Employee",
  "quản trị viên": "Admin",
  "quản trị": "Admin",
};
function _bgBmSecNormalizeRole(r) {
  if (!r) return "";
  return _BG_BM_SEC_ROLE_MAP[String(r).trim().toLowerCase()] || r;
}

// Parse edges từ GraphQL/HTML response → users[] (chung schema).
function _bgBmSecParseEdges(edges) {
  if (!Array.isArray(edges)) return [];
  return edges
    .filter((edge) => {
      const node = edge && edge.node;
      if (node && node.__typename && node.__typename !== "BusinessUser") return false;
      return !(edge && edge.nameColumn && edge.nameColumn.invited_email);
    })
    .map((edge) => {
      const ac = (edge && edge.actionsColumn) || {};
      const nc = (edge && edge.nameColumn) || {};
      const rc = (edge && edge.roleColumn) || {};
      const sc = (edge && edge.statusColumn) || {};
      const ui = (edge && edge.userInfoForSelection) || {};
      const bulk = (edge && edge.bulkUpdatePermissionsData) || {};
      const rs = (rc.permitted_business_account_tasks_summary && rc.permitted_business_account_tasks_summary.standalone) || {};
      const taskArr = Array.isArray(bulk.permitted_business_account_tasks)
        ? bulk.permitted_business_account_tasks.map((t) => String(t.task_id || "")).filter(Boolean).sort()
        : (Array.isArray(ui.permitted_business_account_tasks)
            ? ui.permitted_business_account_tasks.map((t) => String(t.task_id || "")).filter(Boolean).sort()
            : []);
      return {
        id: ac.businessUserID || nc.id || (edge && edge.node && edge.node.id),
        name: ac.businessUserName || nc.name || ui.name || "",
        role: _bgBmSecNormalizeRole(rs.primary_access_summary || rs.advanced_access_summary || ""),
        taskIds: taskArr.join(","),
        email: nc.email || sc.email || ac.email || ui.email || "",
        backedUserType: ac.backed_user_type || nc.backed_user_type || "FACEBOOK",
      };
    })
    .filter((u) => u.id);
}

// Method 1: GraphQL GET với access_token (doc_id 24411698895145972).
// Cần fbAuth.accessToken được tab BM push vào chrome.storage trước đó.
async function _bgBmSecGetAdminsGraphQL(bmId, auth) {
  if (!auth || !auth.accessToken) return null;
  const isEAAI = String(auth.accessToken).startsWith("EAAI");
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
    shouldUseNewEmptyState: !isEAAI,
    id: bmId,
    __relay_internal__pv__BizKitSettingsPeopleEmptyStaterelayprovider: !isEAAI,
  };
  const url =
    "https://graph.facebook.com/graphql?method=post&locale=en_US&pretty=false&format=json" +
    "&fb_api_req_friendly_name=BizKitSettingsPeopleTableListPaginationQuery" +
    "&doc_id=" + (_scBg.docIds && _scBg.docIds.bmUsers || "24411698895145972") + "&fb_api_caller_class=RelayModern&server_timestamps=true" +
    "&variables=" + encodeURIComponent(JSON.stringify(variables)) +
    "&access_token=" + encodeURIComponent(auth.accessToken);
  const res = await fetchWithCookies(url, { method: "GET" }, "text");
  if (!res || !res.success || !res.data) return null;
  let json = null;
  try {
    const txt = String(res.data).replace(/^for\s*\(\s*;\s*;\s*\)\s*;?\s*/, "");
    json = JSON.parse(txt);
  } catch { return null; }
  const node = json && json.data && json.data.node;
  if (!node) return null;
  const viewerId = (node.business_user_for_viewer && node.business_user_for_viewer.id) || null;
  const edges =
    (node.business_users_and_invitations && node.business_users_and_invitations.edges) ||
    (node.business_users && node.business_users.edges) ||
    [];
  return { users: _bgBmSecParseEdges(edges), viewerId };
}

// Method 2: HTML scrape (fallback nếu GraphQL fail).
// locale=en_US ép trả role text English để diff không false positive khi user FB
// đang ở locale vi-VN ('Full control' ↔ 'Toàn quyền kiểm soát').
async function _bgBmSecGetAdminsHTML(bmId) {
  const url = "https://business.facebook.com/latest/settings/business_users?business_id=" + encodeURIComponent(bmId) + "&locale=en_US";
  const res = await fetchWithCookies(url, { headers: { "accept-language": "en-US,en;q=0.9" } }, "text");
  if (!res || !res.success || !res.data) return null;
  const html = String(res.data);

  let viewerId = null;
  const viewerMatch = html.match(/"business_user_for_viewer":\s*\{[^}]*"id":\s*"(\d+)"/);
  if (viewerMatch) viewerId = viewerMatch[1];

  let edges = [];
  const edgesMatch = html.match(
    /"business_users_and_invitations":\s*\{\s*"edges":\s*(\[[\s\S]*?\])\s*,\s*"page_info"/,
  );
  if (edgesMatch) {
    try { edges = JSON.parse(edgesMatch[1]); } catch {}
  }
  return { users: _bgBmSecParseEdges(edges), viewerId };
}

// Snapshot 1 BM — ưu tiên GraphQL (TRUST empty), fallback HTML (chỉ trust nếu có users).
// GraphQL trả empty = user thực sự xóa admins → fire event đúng.
// HTML trả empty = không tin cậy (rate-limit page) → fail, giữ snapshot cũ.
async function _bgBmSecGetAdmins(bmId, auth) {
  try {
    const r = await _bgBmSecGetAdminsGraphQL(bmId, auth);
    if (r && Array.isArray(r.users)) return r; // trust GraphQL (kể cả empty)
  } catch (_) {}
  try {
    const r2 = await _bgBmSecGetAdminsHTML(bmId);
    if (r2 && Array.isArray(r2.users) && r2.users.length) return r2; // HTML chỉ trust nếu non-empty
  } catch (_) {}
  console.warn("[bgBmSec] BM " + bmId + " all methods fail — bỏ qua lần này");
  return null;
}

// Worker pool 20 luồng song song.
async function _bgBmSecCaptureSnapshot(bmIds, auth) {
  const snap = {};
  const queue = [...bmIds];
  const worker = async () => {
    while (queue.length) {
      const bmId = queue.shift();
      if (!bmId) continue;
      try {
        const r = await _bgBmSecGetAdmins(bmId, auth);
        if (r && Array.isArray(r.users)) snap[bmId] = r.users;
      } catch (_) {}
    }
  };
  const workers = [];
  for (let i = 0; i < Math.min(20, bmIds.length); i++) workers.push(worker());
  await Promise.all(workers);
  return snap;
}

function _bgBmSecDiff(oldSnap, newSnap, bmIds) {
  const events = [];
  for (const bmId of bmIds) {
    const oldUsers = oldSnap && oldSnap[bmId];
    const newUsers = newSnap && newSnap[bmId];
    if (!Array.isArray(oldUsers) || !Array.isArray(newUsers)) continue;
    const oldMap = new Map(oldUsers.map((u) => [u.id, u]));
    const newMap = new Map(newUsers.map((u) => [u.id, u]));
    for (const u of newUsers) {
      if (!oldMap.has(u.id)) events.push({ bmId, type: "new", user: u });
      else {
        const o = oldMap.get(u.id);
        // Logic an toàn: only fire khi cả 2 bên đều có taskIds hoặc cả 2 đều thiếu taskIds.
        // Một bên thiếu (HTML scrape partial data) → SKIP để tránh false positive.
        let roleChanged = false;
        if (o.taskIds && u.taskIds) {
          roleChanged = o.taskIds !== u.taskIds;
        } else if (!o.taskIds && !u.taskIds && o.role && u.role) {
          roleChanged = o.role !== u.role;
        }
        if (roleChanged) {
          events.push({ bmId, type: "role_changed", user: u, oldRole: o.role || "—", newRole: u.role || "—" });
        }
      }
    }
    for (const u of oldUsers) {
      if (!newMap.has(u.id)) events.push({ bmId, type: "removed", user: u });
    }
  }
  return events;
}

function _bgBmSecFormatMessage(events, bmNames) {
  bmNames = bmNames || {};
  const bmGroups = {};
  for (const ev of events) {
    if (!bmGroups[ev.bmId]) bmGroups[ev.bmId] = { new: [], removed: [], role_changed: [] };
    if (bmGroups[ev.bmId][ev.type]) bmGroups[ev.bmId][ev.type].push(ev);
  }

  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const timeStr =
    pad(now.getHours()) + ":" + pad(now.getMinutes()) +
    " · " + pad(now.getDate()) + "/" + pad(now.getMonth() + 1) + "/" + now.getFullYear();

  const lines = [
    "🛡 CẢNH BÁO BẢO MẬT BM",
    "━━━━━━━━━━━━━━━━━━━━",
    "🕐 " + timeStr,
    "📊 Phát hiện " + events.length + " thay đổi trên " + Object.keys(bmGroups).length + " BM",
  ];

  for (const bmId of Object.keys(bmGroups)) {
    const g = bmGroups[bmId];
    const bmName = bmNames[bmId];
    lines.push("");
    lines.push("━━━━━━━━━━━━━━━━━━━━");
    lines.push(bmName ? "🏢 BM " + bmId + " - " + bmName : "🏢 BM " + bmId);

    if (g.new.length) {
      lines.push("");
      lines.push("➕ Admin MỚI XUẤT HIỆN (" + g.new.length + ")");
      for (const ev of g.new) {
        const u = ev.user || {};
        lines.push("  • " + (u.name || "—"));
        lines.push("    ID: " + u.id);
        if (u.email) lines.push("    Email: " + u.email);
      }
    }
    if (g.removed.length) {
      lines.push("");
      lines.push("❌ Admin BỊ XOÁ (" + g.removed.length + ")");
      for (const ev of g.removed) {
        const u = ev.user || {};
        lines.push("  • " + (u.name || "—"));
        lines.push("    ID: " + u.id);
        if (u.email) lines.push("    Email: " + u.email);
      }
    }
    if (g.role_changed.length) {
      lines.push("");
      lines.push("🔄 THAY ĐỔI QUYỀN (" + g.role_changed.length + ")");
      for (const ev of g.role_changed) {
        const u = ev.user || {};
        lines.push("  • " + (u.name || "—"));
        lines.push("    ID: " + u.id);
        lines.push("    " + ev.oldRole + "  →  " + ev.newRole);
      }
    }
  }

  lines.push("");
  lines.push("━━━━━━━━━━━━━━━━━━━━");
  lines.push("⚠️ Nếu không phải thao tác của bạn — hãy kiểm tra BM ngay để bảo vệ tài sản.");
  return lines.join("\n");
}

async function _bgBmSecNotifyZalo(key, message) {
  try {
    await fetch(apiBase + "/api/zalo/notify", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ key, message }),
    });
  } catch (e) {
    console.warn("[bgBmSec] notify failed:", e.message);
  }
}

async function runBmSecBackgroundCheck(uid) {
  const cfgKey = BM_SEC_ALARM_PREFIX + uid;
  const authKey = "fbAuth_" + uid;
  const data = await chrome.storage.local.get([cfgKey, authKey, "licenseKey"]);
  const cfg = data[cfgKey];
  const auth = data[authKey];
  // Key CỦA người cấu hình (trang ghi kèm từ 2026-10); khoá licenseKey chung chỉ còn cho cấu hình ghi từ bản web cũ —
  // khoá chung bị người dùng sau trên cùng trình duyệt ghi đè → cảnh báo gửi nhầm người
  const key = (cfg && typeof cfg.lk === "string" && cfg.lk) || data.licenseKey;
  if (!cfg || !cfg.enabled || !Array.isArray(cfg.bmIds) || !cfg.bmIds.length) return;
  if (!key) return;

  const newSnap = await _bgBmSecCaptureSnapshot(cfg.bmIds, auth);
  const events = _bgBmSecDiff(cfg.snapshot || {}, newSnap, cfg.bmIds);

  // Merge: giữ snap cũ cho BM fetch fail (không có trong newSnap)
  for (const bmId of cfg.bmIds) {
    if (!newSnap[bmId] && cfg.snapshot && cfg.snapshot[bmId]) {
      newSnap[bmId] = cfg.snapshot[bmId];
    }
  }
  cfg.snapshot = newSnap;
  cfg.lastCheck = Date.now();
  await chrome.storage.local.set({ [cfgKey]: cfg });

  if (events.length) {
    await _bgBmSecNotifyZalo(key, _bgBmSecFormatMessage(events, cfg.bmNames || {}));
  }
}

// Alarm listener cho bmSec alarms
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (!alarm || !alarm.name) return;
  if (alarm.name === KEEP_ALIVE_ALARM) return;
  if (alarm.name.startsWith(BM_SEC_ALARM_PREFIX)) {
    const uid = alarm.name.slice(BM_SEC_ALARM_PREFIX.length);
    try { await runBmSecBackgroundCheck(uid); } catch (e) { console.warn("[bgBmSec]", e.message); }
  }
});

// Tab BM ghi config vào chrome.storage qua ExtensionBridge → background tự setup/clear alarm.
// Không cần message protocol riêng — storage.onChanged event covers all.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  for (const k of Object.keys(changes)) {
    if (!k.startsWith(BM_SEC_ALARM_PREFIX)) continue;
    const uid = k.slice(BM_SEC_ALARM_PREFIX.length);
    const cfg = changes[k].newValue;
    const alarmName = k; // bmSec_<uid>
    chrome.alarms.clear(alarmName);
    if (cfg && cfg.enabled && Array.isArray(cfg.bmIds) && cfg.bmIds.length > 0) {
      chrome.alarms.create(alarmName, { periodInMinutes: _bmSecPeriod(cfg) });
    }
  }
});

// Restore alarms khi service worker startup (sau Chrome restart hoặc SW idle):
// chrome.alarms persist nhưng kiểm tra lại config để bảo đảm sync.
chrome.runtime.onStartup.addListener(async () => {
  try {
    const all = await chrome.storage.local.get(null);
    for (const k of Object.keys(all)) {
      if (!k.startsWith(BM_SEC_ALARM_PREFIX)) continue;
      const cfg = all[k];
      if (cfg && cfg.enabled && Array.isArray(cfg.bmIds) && cfg.bmIds.length > 0) {
        await chrome.alarms.create(k, { periodInMinutes: _bmSecPeriod(cfg) });
      }
    }
  } catch (e) { console.warn("[bgBmSec onStartup]", e.message); }
});

// ========================================
// BẢO MẬT TKQC CŨ (ads-security) — ĐÃ GỠ (web gỡ 08/08/2026, logic nền gỡ ở bản 1.9.8; thay bằng "Tự động & Bảo mật"
// trên trang /ads). Lúc cài/cập nhật: xoá cấu hình nền "adsSec_<uid>" còn sót (giữ token FB + license key) và alarm
// cùng tên. Không còn gì thì không làm gì.
// ========================================
async function _adsSecLegacyCleanup() {
  try {
    (await chrome.alarms.getAll()).forEach((a) => { if (a && a.name && a.name.startsWith("adsSec_")) chrome.alarms.clear(a.name); });
    const keys = chrome.storage.local.getKeys ? await chrome.storage.local.getKeys() : Object.keys(await chrome.storage.local.get(null));
    const ks = keys.filter((k) => k.startsWith("adsSec_"));
    if (ks.length) await chrome.storage.local.remove(ks);
  } catch (e) { console.warn("[adsSec cleanup]", e && e.message); }
}
chrome.runtime.onInstalled.addListener(() => { _adsSecLegacyCleanup(); });

// ========================================
// QUY TẮC THEO SỐ DƯ TKQC — từ 1.9.7 KHÔNG chạy ở đây nữa: chạy ở trang /ext-runner của app (xem "VIỆC NỀN DO SERVER
// PHỤC VỤ" ngay dưới) cùng bộ chạy với trang /ads (server/public/js/ads-bal-engine.js).
// ========================================
// Nâng cấp từ bản cũ (≤1.9.6): quy tắc số dư từng chạy NGAY trong file này từ chrome.storage "adsBal_<users.id>" (kèm
// token FB + license key). Bản đó còn giữ dấu "đã tắt" ghi lúc trang đóng → KHÔNG xoá (xoá = lượt sau tắt lại đối tượng
// người dùng đã tự bật, báo trùng): chỉ bỏ token/key + alarm cũ; trang app gộp vào localStorage rồi tự xoá. Còn quy tắc
// bật → đăng ký việc nền ở tên miền app để vẫn chạy khi chưa mở lại /ads.
async function _balLegacyCleanup() {
  try {
    const keys = chrome.storage.local.getKeys ? await chrome.storage.local.getKeys() : Object.keys(await chrome.storage.local.get(null));
    const bal = keys.filter((k) => k.startsWith("adsBal_")), warn = keys.filter((k) => k.startsWith("adsBalWarn_"));
    if (warn.length) await chrome.storage.local.remove(warn);
    (await chrome.alarms.getAll()).forEach((a) => { if (a && a.name && a.name.startsWith("adsBal_")) chrome.alarms.clear(a.name); });
    if (!bal.length) return;
    const got = await chrome.storage.local.get(bal.concat([JOB_REG])), upd = {};
    const reg = Object.assign({}, got[JOB_REG] && typeof got[JOB_REG] === "object" ? got[JOB_REG] : {});
    const origin = new URL(await loadApiBase()).origin, ek = "balance|" + origin;
    let regd = false;
    bal.forEach((k) => {
      const v = got[k]; if (!v || typeof v !== "object") return;
      upd[k] = { v: v.v, rules: v.rules, state: v.state, lastTick: v.lastTick || 0 };
      const on = Array.isArray(v.rules) && v.rules.some((r) => r && r.enabled);
      if (on && !reg[ek] && _jobOriginOk(origin)) { reg[ek] = { on: true, every: 1, origin, at: 0, by: k.slice(7) }; regd = true; }
    });
    if (regd) upd[JOB_REG] = reg;
    await chrome.storage.local.set(upd);
  } catch (e) { console.warn("[bgBal upgrade]", e && e.message); }
}
chrome.runtime.onInstalled.addListener(() => { _balLegacyCleanup(); });

// ========================================
// VIỆC NỀN DO SERVER PHỤC VỤ (từ 1.9.7) — extension chỉ HẸN GIỜ + mở offscreen document nhúng trang <app>/ext-runner;
// logic từng việc nằm ở trang đó (deploy server là cập nhật, KHÔNG phải cài lại extension — trừ khi cần quyền Chrome
// mới). Trang app đăng ký việc qua bridge, THEO TÊN MIỀN (mỗi tên miền 1 localStorage riêng):
//   chrome.storage "bgJobs" = { "<tên>|<origin>": { on, every (phút), origin, at, by } }
// Trang chạy nền là iframe first-party (extension có quyền host) → dùng chung localStorage/Web Locks với tab app
// đang mở; content.js chèn ExtensionBridge vào nó như mọi trang app.
// Tên khoá/tin nhắn KHÔNG chứa thương hiệu (gói đại lý thay chữ trong .js extension; trang server thì không).
// ========================================
const JOB_REG = "bgJobs";
const JOB_LAST = "bgJobsLast"; // { <origin>: { at (lượt gần nhất bắt đầu), idle (số lượt liền không có việc), done, report } }
const JOB_ALARM = "bgJobRunner";
const JOB_TIMEOUT_MS = 95000;
const JOB_IDLE_MS = 600000; // tên miền chạy ≥3 lượt liền không có việc (chưa đăng nhập / chưa có quy tắc) → 10 phút/lượt
let _jobRun = null; // lượt đang chạy { r, at, origin }
// Chỉ tên miền app của CHÍNH gói này (homepage_url = domain nền tảng / đại lý — cùng họ với CSP frame-src) hoặc localhost
function _jobOriginOk(o) {
  try {
    const u = new URL(o);
    if (u.origin !== o) return false;
    if (u.protocol === "http:") return u.hostname === "localhost" || u.hostname === "127.0.0.1";
    if (u.protocol !== "https:") return false;
    const home = new URL(chrome.runtime.getManifest().homepage_url || PLATFORM_ANCHOR).hostname;
    return u.hostname === home || u.hostname.endsWith("." + home);
  } catch (e) { return false; }
}
async function _jobsList() {
  const reg = (await chrome.storage.local.get([JOB_REG]))[JOB_REG];
  if (!reg || typeof reg !== "object") return [];
  return Object.keys(reg).map((k) => Object.assign({}, reg[k], { name: k.split("|")[0] }))
    .filter((j) => j.on === true && /^[a-z0-9_-]{1,40}$/i.test(j.name) && _jobOriginOk(String(j.origin || "")));
}
async function _jobsClose() { try { await chrome.offscreen.closeDocument(); } catch (e) {} } // không có document → bỏ qua
async function _jobsEnsureAlarm() {
  try {
    const jobs = await _jobsList();
    if (!jobs.length) { chrome.alarms.clear(JOB_ALARM); return; }
    const every = Math.max(1, Math.min(...jobs.map((j) => Number(j.every) || 1)));
    chrome.alarms.get(JOB_ALARM, (a) => { if (!a || a.periodInMinutes !== every) chrome.alarms.create(JOB_ALARM, { periodInMinutes: every, delayInMinutes: 0.5 }); });
  } catch (e) { console.warn("[bgJobs]", e && e.message); }
}
// Mỗi lượt: 1 tên miền (chỉ được 1 offscreen document) — tên miền đến hạn chờ lâu nhất; trang chạy nền MỚI (lấy code
// mới nhất của server), chạy xong thì đóng — trang treo không sống qua lượt sau
async function runJobsTick() {
  if (!chrome.offscreen || typeof chrome.offscreen.createDocument !== "function") return; // Chrome < 109
  if (_jobRun && Date.now() - _jobRun.at < JOB_TIMEOUT_MS) return;
  const jobs = await _jobsList();
  if (!jobs.length) { await _jobsClose(); return; }
  const now = Date.now(), last = (await chrome.storage.local.get([JOB_LAST]))[JOB_LAST] || {}, by = {};
  jobs.forEach((j) => {
    const g = by[j.origin] || (by[j.origin] = { names: [], every: 60, at: 0 });
    if (!g.names.includes(j.name)) g.names.push(j.name);
    g.every = Math.min(g.every, Math.max(1, Number(j.every) || 1));
    g.at = Math.max(g.at, Math.min(Number(j.at) || 0, now));
  });
  // Đến hạn: đủ `every` phút từ lượt trước (chừa 15s lệch nhịp alarm); đang thưa nhịp vì không có việc thì 10 phút —
  // trang đăng ký lại (at mới hơn lượt trước) là chạy ngay
  const due = Object.keys(by).filter((o) => {
    const L = last[o] || {}, g = by[o];
    if (!L.at) return true;
    const gap = (L.idle || 0) >= 3 && g.at <= L.at ? JOB_IDLE_MS : g.every * 60000 - 15000;
    return now - L.at >= gap;
  }).sort((a, b) => ((last[a] || {}).at || 0) - ((last[b] || {}).at || 0));
  if (!due.length) return;
  const origin = due[0], names = by[origin].names;
  const r = now.toString(36) + Math.random().toString(36).slice(2, 8);
  _jobRun = { r, at: now, origin };
  last[origin] = Object.assign({}, last[origin], { at: now });
  await chrome.storage.local.set({ [JOB_LAST]: last });
  await _jobsClose();
  try {
    await chrome.offscreen.createDocument({
      url: "offscreen.html?o=" + encodeURIComponent(origin) + "&r=" + r + "&j=" + encodeURIComponent(names.join(",")),
      reasons: ["IFRAME_SCRIPTING"],
      justification: "Run the web app's scheduled background jobs",
    });
  } catch (e) { if (_jobRun && _jobRun.r === r) _jobRun = null; console.warn("[bgJobs] offscreen", e && e.message); return; }
  setTimeout(() => { if (_jobRun && _jobRun.r === r) { _jobRun = null; _jobsClose(); } }, JOB_TIMEOUT_MS);
}
// Lượt "không có việc": mọi việc đều báo bỏ qua vì chưa đăng nhập / chưa có quy tắc / đã tắt hết
function _jobsIdle(rep) {
  const v = rep && typeof rep === "object" ? Object.keys(rep).filter((k) => k !== "timeout").map((k) => rep[k]) : [];
  return v.length > 0 && v.every((x) => x && x.ok && x.r && /^(no-owner|no-rules|disabled)$/.test(String(x.r.skip || "")));
}
async function _jobsDone(run, report) {
  const all = (await chrome.storage.local.get([JOB_LAST]))[JOB_LAST] || {}, L = all[run.origin] || {};
  all[run.origin] = { at: L.at || run.at, idle: _jobsIdle(report) ? (L.idle || 0) + 1 : 0, done: Date.now(), report };
  await chrome.storage.local.set({ [JOB_LAST]: all });
}
chrome.runtime.onMessage.addListener((msg, sender) => {
  if (!msg || msg.action !== "bgJobs.done") return;
  // Chỉ offscreen document của chính extension (content script trên trang web không mạo danh được)
  if (!sender || sender.id !== chrome.runtime.id || !String(sender.url || "").startsWith(chrome.runtime.getURL("offscreen.html"))) return;
  if (!_jobRun || msg.r !== _jobRun.r) return;
  const run = _jobRun;
  _jobRun = null;
  _jobsDone(run, msg.report && typeof msg.report === "object" ? msg.report : null).catch((e) => console.warn("[bgJobs]", e && e.message));
  _jobsClose();
});
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm && alarm.name === JOB_ALARM) runJobsTick().catch((e) => console.warn("[bgJobs]", e && e.message));
});
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes[JOB_REG]) _jobsEnsureAlarm();
});
// Cập nhật/tải lại extension xoá mọi alarm → dựng lại MỖI lần service worker khởi động (như keepAlive ở đầu file)
chrome.runtime.onStartup.addListener(_jobsEnsureAlarm);
chrome.runtime.onInstalled.addListener(_jobsEnsureAlarm);
_jobsEnsureAlarm();

// ========== NUÔI TÀI KHOẢN — điều phối (V1: "Chạy ngay") ==========
// Web bấm "Chạy ngay" → ghi _global.runNow (mốc thời gian) vào extNuoiConfig. Ở đây bắt thay đổi đó
// → mở 1 tab facebook.com (active để DOM render) → gửi {action:"fioxNuoiRun"} cho content script của
// tab đó → tab tự chạy một phiên nuôi (cuộn feed…). KHÔNG đóng tab để người dùng thấy được hoạt động.
(function fioxNuoiOrchestrator() {
  const NKEY = "extNuoiConfig", NKEY_OLD = "fioxNuoiConfig";
  let busy = false;
  const _sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  function _nuoiAnyOn(cfg) {
    return Object.keys(cfg || {}).some((k) => k.indexOf("nuoi_") === 0 && cfg[k] && cfg[k]._on);
  }
  function _nuoiWaitComplete(tabId, timeout) {
    return new Promise((resolve) => {
      let done = false;
      const fin = (ok) => { if (done) return; done = true; try { chrome.tabs.onUpdated.removeListener(onUpd); } catch (e) {} resolve(ok); };
      const onUpd = (id, info) => { if (id === tabId && info && info.status === "complete") fin(true); };
      try { chrome.tabs.onUpdated.addListener(onUpd); } catch (e) { return resolve(false); }
      setTimeout(() => fin(false), timeout || 30000);
    });
  }
  function _nuoiSendTab(tabId, msg) {
    return new Promise((resolve) => {
      try { chrome.tabs.sendMessage(tabId, msg, (res) => { void chrome.runtime.lastError; resolve(res || null); }); }
      catch (e) { resolve(null); }
    });
  }
  // Tính năng phải ở TRANG RIÊNG mới làm được → lần lượt điều hướng chính tab đó rồi gửi {feature}.
  const NAV_PAGES = [
    ["nuoi_reels", "https://www.facebook.com/reel/"],
    ["nuoi_poke", "https://www.facebook.com/pokes/"],
    ["nuoi_add_friend", "https://www.facebook.com/friends/suggestions/"],
    ["nuoi_birthday", "https://www.facebook.com/events/birthdays/"],
    ["nuoi_cmt_group", "https://www.facebook.com/groups/feed/"],
    ["nuoi_join_group", "https://www.facebook.com/groups/discover/"],
    ["nuoi_follow_page", "https://www.facebook.com/pages/?category=suggested"],
  ];
  // Bật trong cấu hình nhưng KHÔNG chạy được — chỉ ghi log, không thao tác gì.
  const NAV_UNSUPPORTED = {
    nuoi_avatar: "Đổi ảnh đại diện / bìa",
    nuoi_reply_msg: "Trả lời tin nhắn chào hỏi",
  };
  // Tab còn sống không? Người dùng đóng tab giữa phiên thì phải dừng, đừng điều hướng tab đã chết.
  async function _nuoiTabAlive(tabId) {
    try { return !!(await chrome.tabs.get(tabId)); } catch (e) { return false; }
  }
  async function _nuoiStep(tabId, runId, feature, label, budget) {
    const res = await _nuoiSendTab(tabId, { action: "fioxNuoiRun", runId: runId, feature: feature || "", budget: budget });
    console.log("[nuôi] " + label + ":", res);
    try { await _nuoiAddActs(_nuoiActs(res && res.report)); } catch (e) {} // cộng dồn trần/ngày
    return res;
  }
  async function _nuoiRunSession() {
    if (busy) return;
    const st = await chrome.storage.local.get([NKEY, NKEY_OLD]);
    const cfg = (st && (st[NKEY] || st[NKEY_OLD])) || {};
    const gl = cfg._global || {};
    if (gl.master === false) { console.log("[nuôi] master tắt — bỏ qua"); return; }
    if (!_nuoiAnyOn(cfg)) { console.log("[nuôi] chưa bật tính năng nào — bỏ qua"); return; }
    busy = true;
    const runId = Date.now();
    const steps = [];
    try {
      // 1) Trang chủ: mọi tính năng cần bảng tin
      const tab = await chrome.tabs.create({ url: "https://www.facebook.com/", active: true });
      await _nuoiWaitComplete(tab.id, 30000);
      await _sleep(3500); // chờ feed render
      const home = await _nuoiStep(tab.id, runId, "", "trang chủ", await _nuoiBudget(gl));
      steps.push({ step: "home", ok: !!(home && home.ok), ran: (home && home.ran) || 0, err: (home && home.err) || null });

      // 2) Từng trang riêng — dùng LẠI tab đó, điều hướng tuần tự
      for (let i = 0; i < NAV_PAGES.length; i++) {
        const key = NAV_PAGES[i][0], url = NAV_PAGES[i][1], f = cfg[key];
        if (!f || !f._on) continue;
        if (!(await _nuoiTabAlive(tab.id))) { console.log("[nuôi] tab đã bị đóng — dừng phiên"); break; }
        const budget = await _nuoiBudget(gl);
        if (budget <= 0) { console.log("[nuôi] đã chạm trần thao tác/ngày — dừng phiên"); break; }
        try {
          await chrome.tabs.update(tab.id, { url: url });
          await _nuoiWaitComplete(tab.id, 30000);
          await _sleep(3500);
          const r = await _nuoiStep(tab.id, runId, key, key, budget);
          steps.push({ step: key, ok: !!(r && r.ok), ran: (r && r.ran) || 0, err: (r && r.err) || null });
        } catch (e) {
          steps.push({ step: key, ok: false, err: String((e && e.message) || e) });
        }
        await _sleep(2000);
      }
      Object.keys(NAV_UNSUPPORTED).forEach((k) => {
        if (cfg[k] && cfg[k]._on) console.log('[nuôi] "' + NAV_UNSUPPORTED[k] + '" đang bật nhưng chưa hỗ trợ — bỏ qua.');
      });
      // ok = có bước nào thật sự chạy được, không phải "vòng lặp đã kết thúc".
      await chrome.storage.local.set({ nuoiLastRun: { at: Date.now(), ok: steps.some((s) => s.ok), steps: steps } });
    } catch (e) {
      console.warn("[nuôi] lỗi phiên:", e && e.message);
      try { await chrome.storage.local.set({ nuoiLastRun: { at: Date.now(), ok: false, steps: steps, err: String((e && e.message) || e) } }); } catch (e2) {}
    } finally {
      busy = false;
    }
  }
  // ===== Lịch tự động =====
  // Chu kỳ (phút) + khung giờ hoạt động + trần số thao tác/ngày. "Chạy ngay" KHÔNG bị các mốc này chặn.
  const NALARM = "fioxNuoiSched";
  // ⚠ Phải khớp ACT_FIELDS trong client/js/content.js — hai bên cùng trừ vào một trần/ngày.
  const ACT_FIELDS = ["reacted", "cmtAi", "poke", "addFriend", "joinGroup", "followPage", "reels", "reactStory", "birthday", "share", "post"];
  function _nuoiActs(rep) {
    let n = 0;
    if (!rep) return n;
    ACT_FIELDS.forEach((f) => { const v = rep[f]; if (typeof v === "number") n += v; else if (v === true) n += 1; });
    return n;
  }
  function _nuoiDayKey() {
    const d = new Date();
    return d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate();
  }
  function _nuoiInHours(gl) {
    let from = Number(gl.activeFrom), to = Number(gl.activeTo);
    if (!isFinite(from)) from = 7;
    if (!isFinite(to)) to = 22;
    if (from === to) return true; // cả ngày
    const h = new Date().getHours();
    return from < to ? h >= from && h < to : h >= from || h < to; // to < from = khung qua đêm
  }
  async function _nuoiAddActs(n) {
    if (!n) return;
    const day = _nuoiDayKey();
    const cur = (await chrome.storage.local.get(["nuoiDaily"])).nuoiDaily || {};
    const acts = (cur.day === day ? Number(cur.acts) || 0 : 0) + n;
    await chrome.storage.local.set({ nuoiDaily: { day: day, acts: acts } });
  }
  // Số thao tác CÒN được phép hôm nay. Truyền xuống content script để nó dừng giữa phiên —
  // chỉ gác lúc bắt đầu phiên thì một phiên vẫn chạy trọn và vượt xa trần.
  async function _nuoiBudget(gl) {
    const lim = Math.max(1, Number(gl && gl.dailyLimit) || 50);
    const cur = (await chrome.storage.local.get(["nuoiDaily"])).nuoiDaily || {};
    const acts = cur.day === _nuoiDayKey() ? Number(cur.acts) || 0 : 0;
    return Math.max(0, lim - acts);
  }
  async function _nuoiOverLimit(gl) {
    return (await _nuoiBudget(gl)) <= 0;
  }
  function _nuoiPeriod(gl) {
    const m = Number(gl && gl.interval);
    return Math.max(15, Math.min(1440, isFinite(m) && m > 0 ? m : 240));
  }
  async function _nuoiEnsureAlarm() {
    try {
      const st = await chrome.storage.local.get([NKEY, NKEY_OLD]);
      const cfg = (st && (st[NKEY] || st[NKEY_OLD])) || {};
      const gl = cfg._global || {};
      if (gl.master === false || !_nuoiAnyOn(cfg)) { chrome.alarms.clear(NALARM); return; }
      const every = _nuoiPeriod(gl);
      chrome.alarms.get(NALARM, (a) => {
        if (!a || a.periodInMinutes !== every) chrome.alarms.create(NALARM, { periodInMinutes: every, delayInMinutes: every });
      });
    } catch (e) {}
  }
  chrome.alarms.onAlarm.addListener(async (alarm) => {
    if (!alarm || alarm.name !== NALARM) return;
    try {
      const st = await chrome.storage.local.get([NKEY, NKEY_OLD]);
      const cfg = (st && (st[NKEY] || st[NKEY_OLD])) || {};
      const gl = cfg._global || {};
      if (gl.master === false || !_nuoiAnyOn(cfg)) { chrome.alarms.clear(NALARM); return; }
      if (!_nuoiInHours(gl)) { console.log("[nuôi] ngoài khung giờ hoạt động — bỏ qua"); return; }
      if (await _nuoiOverLimit(gl)) { console.log("[nuôi] đã chạm trần thao tác/ngày — bỏ qua"); return; }
      _nuoiRunSession().catch((e) => console.warn("[nuôi]", e && e.message));
    } catch (e) {}
  });
  chrome.runtime.onStartup.addListener(_nuoiEnsureAlarm);
  chrome.runtime.onInstalled.addListener(_nuoiEnsureAlarm);
  _nuoiEnsureAlarm();

  chrome.storage.onChanged.addListener(async (changes, area) => {
    if (area !== "local") return;
    const c = changes[NKEY] || changes[NKEY_OLD];
    if (!c) return;
    _nuoiEnsureAlarm(); // đổi chu kỳ / bật-tắt tính năng → dựng lại lịch
    const nv = c.newValue || {};
    const rn = (nv._global && nv._global.runNow) || 0;
    if (!rn) return;
    try {
      const seen = (await chrome.storage.local.get(["nuoiRunNowSeen"])).nuoiRunNowSeen || 0;
      if (rn <= seen) return; // đã xử lý mốc này rồi
      await chrome.storage.local.set({ nuoiRunNowSeen: rn });
    } catch (e) {}
    _nuoiRunSession().catch((e) => console.warn("[nuôi]", e && e.message));
  });
})();

// Nuôi — proxy AI: content script (trên facebook.com) nhờ background gọi /api/ai/seeding (DeepSeek)
// để tránh CORS. Key + apiBase lấy từ chrome.storage. Trả { ok, comments:[...] }.
chrome.runtime.onMessage.addListener((msg, sender, send) => {
  if (!msg || msg.action !== "fioxNuoiAI") return;
  (async () => {
    try {
      // Dùng loadApiBase() (có isValidBase + PLATFORM_ANCHOR) chứ KHÔNG đọc apiBase thô: lời gọi
      // này mang theo license key của khách, không được phép đi tới host lạ hay qua http://.
      const base = await loadApiBase();
      const key = String((await chrome.storage.local.get(["licenseKey"])).licenseKey || "");
      if (!key) { send({ ok: false, error: "Chưa có license key" }); return; }
      const r = await fetch(base + "/api/ai/seeding", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ licenseKey: key, mode: msg.mode === "share" ? "share" : "comments", caption: String(msg.caption || "").slice(0, 1500), count: Math.max(1, Math.min(10, Number(msg.count) || 1)) }),
      });
      const j = await r.json().catch(() => null);
      send(j && j.ok ? { ok: true, comments: j.comments || [] } : { ok: false, error: (j && j.error) || ("HTTP " + r.status) });
    } catch (e) { send({ ok: false, error: String((e && e.message) || e) }); }
  })();
  return true; // trả lời bất đồng bộ
});

// Cùng tài khoản đổi sang key mới (Cấp key mới — key cũ chết ngay): trang Cài đặt ghi "lkMove" {from, to} → chuyển `lk`
// của cấu hình cảnh báo nền (Bảo mật BM) đang giữ key cũ, kẻo cảnh báo khi đóng trang gửi bằng key chết
chrome.storage.onChanged.addListener(async (changes, area) => {
  if (area !== "local" || !changes.lkMove) return;
  const mv = changes.lkMove.newValue;
  if (!mv || typeof mv.from !== "string" || typeof mv.to !== "string" || !mv.from || !mv.to || mv.from === mv.to) return;
  try {
    const keys = chrome.storage.local.getKeys ? await chrome.storage.local.getKeys() : Object.keys(await chrome.storage.local.get(null));
    const ks = keys.filter((k) => k.startsWith(BM_SEC_ALARM_PREFIX));
    if (!ks.length) return;
    const got = await chrome.storage.local.get(ks), upd = {};
    ks.forEach((k) => { const c = got[k]; if (c && typeof c === "object" && c.lk === mv.from) upd[k] = Object.assign({}, c, { lk: mv.to }); });
    if (Object.keys(upd).length) await chrome.storage.local.set(upd);
  } catch (e) { console.warn("[lkMove]", e && e.message); }
});

// ========================================
// PAGE AUTO-REPLY (trả lời bình luận theo từ khoá) — chạy nền dù tab đóng (khi Chrome mở)
// ========================================
// Config chrome.storage.local key 'pageAutoReply_<uid>' do tab Page push:
//   { enabled, pages:[{id,name,token}], rules:[{kw,reply}], sendPm, pmText, intervalMin,
//     startedAt(ms), replied:{pageId:[cmtId]}, lastCheck }
// Mỗi chu kỳ: quét bình luận mới trên feed từng Page → match từ khoá → trả lời công khai (+ nhắn riêng).
// PAGE token do tab push (lưu LOCAL trong extension, KHÔNG lên server). Chỉ chạy khi Chrome mở.
const PAGE_AR_ALARM_PREFIX = "pageAutoReply_";
const PAGE_AR_DEFAULT_PERIOD_MIN = 5;
const PAGE_AR_API_VERSION = _scBg.graphVerPage || "v24.0";
function _bgArPeriod(cfg) { const m = cfg && Number(cfg.intervalMin); return m && m > 0 ? m : PAGE_AR_DEFAULT_PERIOD_MIN; }

function _bgArNorm(s) {
  return String(s == null ? "" : s).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d");
}
function _bgArMatch(message, rules) {
  const m = _bgArNorm(message);
  if (!m) return null;
  for (const r of rules) {
    const kws = String(r.kw || "").split(/[,\n]+/).map((k) => _bgArNorm(k.trim())).filter(Boolean);
    if (!kws.length) continue;
    if (kws.some((k) => m.indexOf(k) >= 0)) return r;
  }
  return null;
}
function _bgArParseTime(v) { if (v == null) return 0; const ms = Date.parse(v); if (!isNaN(ms)) return ms; const n = Number(v); if (!isNaN(n)) return n < 1e12 ? n * 1000 : n; return 0; }

async function _bgArFetchComments(pageId, token) {
  try {
    const fields = "id,created_time,comments.limit(30){id,message,from,created_time}";
    const url = "https://graph.facebook.com/" + PAGE_AR_API_VERSION + "/" + encodeURIComponent(pageId) +
      "/feed?fields=" + encodeURIComponent(fields) + "&limit=10&access_token=" + encodeURIComponent(token);
    const r = await fetch(url);
    const d = await r.json();
    if (!d || d.error || !Array.isArray(d.data)) return [];
    const out = [];
    for (const post of d.data) {
      const cs = post.comments && post.comments.data;
      if (!Array.isArray(cs)) continue;
      for (const c of cs) {
        out.push({ id: String(c.id), message: c.message || "", fromId: c.from && c.from.id ? String(c.from.id) : "", created: _bgArParseTime(c.created_time), postId: String(post.id) });
      }
    }
    return out;
  } catch (e) { return []; }
}
async function _bgArPost(url, params) {
  try {
    const r = await fetch(url, { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" }, body: new URLSearchParams(params).toString() });
    const d = await r.json().catch(() => ({}));
    return !d.error;
  } catch (e) { return false; }
}
async function _bgArReply(pg, c, rule, cfg) {
  let ok = false;
  const reply = String(rule.reply || "").trim();
  if (reply) {
    const url = "https://graph.facebook.com/" + PAGE_AR_API_VERSION + "/" + encodeURIComponent(c.id) + "/comments?access_token=" + encodeURIComponent(pg.token);
    if (await _bgArPost(url, { message: reply })) ok = true;
  }
  if (cfg.sendPm) {
    const pm = String((rule.pm || cfg.pmText || reply) || "").trim();
    if (pm) {
      const url = "https://graph.facebook.com/" + PAGE_AR_API_VERSION + "/" + encodeURIComponent(pg.id) + "/messages?access_token=" + encodeURIComponent(pg.token);
      await _bgArPost(url, { recipient: JSON.stringify({ comment_id: c.id }), message: JSON.stringify({ text: pm }), messaging_type: "RESPONSE" });
    }
  }
  return ok;
}
async function runPageAutoReply(uid) {
  const cfgKey = PAGE_AR_ALARM_PREFIX + uid;
  const data = await chrome.storage.local.get([cfgKey]);
  const cfg = data[cfgKey];
  if (!cfg || !cfg.enabled || !Array.isArray(cfg.pages) || !cfg.pages.length) return;
  if (!Array.isArray(cfg.rules) || !cfg.rules.length) return;
  const startedAt = cfg.startedAt || 0;
  cfg.replied = cfg.replied || {};
  for (const pg of cfg.pages) {
    if (!pg || !pg.id || !pg.token) continue;
    const seen = new Set(Array.isArray(cfg.replied[pg.id]) ? cfg.replied[pg.id] : []);
    const comments = await _bgArFetchComments(pg.id, pg.token);
    for (const c of comments) {
      if (seen.has(c.id)) continue;
      if (c.fromId && String(c.fromId) === String(pg.id)) { seen.add(c.id); continue; } // bình luận của chính Page
      if (startedAt && c.created && c.created < startedAt) { seen.add(c.id); continue; } // chỉ trả lời cmt mới
      const rule = _bgArMatch(c.message, cfg.rules);
      if (!rule) continue;
      await _bgArReply(pg, c, rule, cfg);
      seen.add(c.id); // đánh dấu để không trả lời lặp (kể cả khi lỗi → tránh spam)
    }
    cfg.replied[pg.id] = [...seen].slice(-1000);
  }
  cfg.lastCheck = Date.now();
  await chrome.storage.local.set({ [cfgKey]: cfg });
}
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (!alarm || !alarm.name || !alarm.name.startsWith(PAGE_AR_ALARM_PREFIX)) return;
  const uid = alarm.name.slice(PAGE_AR_ALARM_PREFIX.length);
  try { await runPageAutoReply(uid); } catch (e) { console.warn("[bgAutoReply]", e.message); }
});
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  for (const k of Object.keys(changes)) {
    if (!k.startsWith(PAGE_AR_ALARM_PREFIX)) continue;
    const cfg = changes[k].newValue;
    chrome.alarms.clear(k);
    if (cfg && cfg.enabled && Array.isArray(cfg.pages) && cfg.pages.length > 0 && Array.isArray(cfg.rules) && cfg.rules.length > 0)
      chrome.alarms.create(k, { periodInMinutes: _bgArPeriod(cfg) });
  }
});
chrome.runtime.onStartup.addListener(async () => {
  try {
    const all = await chrome.storage.local.get(null);
    for (const k of Object.keys(all)) {
      if (!k.startsWith(PAGE_AR_ALARM_PREFIX)) continue;
      const cfg = all[k];
      if (cfg && cfg.enabled && Array.isArray(cfg.pages) && cfg.pages.length > 0 && Array.isArray(cfg.rules) && cfg.rules.length > 0)
        await chrome.alarms.create(k, { periodInMinutes: _bgArPeriod(cfg) });
    }
  } catch (e) { console.warn("[bgAutoReply onStartup]", e.message); }
});

// ========================================
// LIFECYCLE EVENTS
// ========================================

/**
 * Extension Install/Update Handler
 * Được gọi khi extension được cài đặt hoặc cập nhật
 */
chrome.runtime.onInstalled.addListener((details) => {
  // Có thể thêm logic khởi tạo ở đây
  // Ví dụ: migrate data, show welcome page, etc.
});
