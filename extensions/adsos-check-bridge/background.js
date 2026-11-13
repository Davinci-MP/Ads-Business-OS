/**
 * ADSOS CHECK PRO — Background Service Worker (Cleaned & Unified)
 * - Đã xóa bỏ hoàn toàn lỗi ReferenceError: document is not defined trong Service Worker
 * - Hợp nhất duy nhất 1 chrome.runtime.onMessage.addListener với safeReply chống lỗi đóng kênh
 * - Tự động đồng bộ dữ liệu hai chiều với AdsOS Server & Meta Graph API
 */

const DEFAULT_SERVER_URL = "http://127.0.0.1:8000";
const META_GRAPH_VERSION = "v21.0";

const MAX_CONCURRENT_META_REQUESTS = 3;
const META_QUEUE_MIN_DELAY_MS = 300;
const META_QUEUE_MAX_DELAY_MS = 900;
const META_QUEUE_BASE_BACKOFF_MS = 4000;
const META_QUEUE_MAX_RETRIES = 3;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// --- Token Sanitizer ---
function cleanMetaToken(token) {
  if (!token || typeof token !== "string") return "";
  const m = token.match(/(EAAB[a-zA-Z0-9]{20,}|EAAG[a-zA-Z0-9]{20,}|EAA[a-zA-Z0-9]{30,})/);
  if (m && m[1]) {
    return m[1].replace(/['"\\\s]+$/, "").replace(/u0025.*$/, "");
  }
  return token.trim();
}

function stripFacebookCookieValue(val) {
  if (typeof val !== "string") return "";
  return val.replace(/^["']|["']$/g, "").trim();
}

// --- DeclarativeNetRequest Rules ---
async function setupFacebookCorsRules() {
  try {
    await chrome.declarativeNetRequest.updateDynamicRules({
      removeRuleIds: [1, 2, 3],
      addRules: [
        {
          id: 1,
          priority: 1,
          condition: {
            urlFilter: "*://*.facebook.com/*",
            resourceTypes: ["xmlhttprequest", "other"]
          },
          action: {
            type: "modifyHeaders",
            requestHeaders: [
              { header: "Origin", operation: "set", value: "https://www.facebook.com" },
              { header: "Referer", operation: "set", value: "https://www.facebook.com/" }
            ]
          }
        },
        {
          id: 2,
          priority: 2,
          condition: {
            urlFilter: "*://*.business.facebook.com/*",
            resourceTypes: ["xmlhttprequest", "other"]
          },
          action: {
            type: "modifyHeaders",
            requestHeaders: [
              { header: "Origin", operation: "set", value: "https://business.facebook.com" },
              { header: "Referer", operation: "set", value: "https://business.facebook.com/" }
            ]
          }
        }
      ]
    });
  } catch (e) {
    console.warn("[ADSOS] DNR setup warning:", e);
  }
}

function emitSyncProgress(current, total, message) {
  try {
    chrome.runtime.sendMessage({
      action: "SYNC_PROGRESS",
      current: Math.max(0, Number(current) || 0),
      total: Math.max(0, Number(total) || 0),
      message
    }, () => void chrome.runtime.lastError);
  } catch (_) {}
}

async function readMetaRateLimit(response) {
  if (response.status === 429) return { limited: true, code: 429 };
  try {
    const payload = await response.clone().json();
    const codes = [
      payload?.error?.code,
      payload?.error?.error_subcode,
      ...(Array.isArray(payload?.errors)
        ? payload.errors.map((item) => item?.code ?? item?.extensions?.code)
        : [])
    ].map(Number);
    const code = codes.find((value) => value === 17 || value === 613 || value === 80004);
    return { limited: Boolean(code), code: code || null };
  } catch (_) {
    return { limited: false, code: null };
  }
}

class SmartQueue {
  constructor(maxConcurrent = MAX_CONCURRENT_META_REQUESTS) {
    this.maxConcurrent = maxConcurrent;
    this.pending = [];
    this.active = 0;
    this.pausedUntil = 0;
    this.submitted = 0;
    this.completed = 0;
    this.cancelEpoch = 0;
  }

  resetProgress() {
    if (this.active === 0 && this.pending.length === 0) {
      this.submitted = 0;
      this.completed = 0;
    }
  }

  enqueue(request, message = "Đang tải dữ liệu từ Meta...") {
    this.submitted += 1;
    return new Promise((resolve, reject) => {
      this.pending.push({ request, message, resolve, reject, epoch: this.cancelEpoch });
      this.#drain();
    });
  }

  cancelPending() {
    this.cancelEpoch += 1;
    this.pausedUntil = 0;
    const error = new Error("Hàng đợi đồng bộ đã được người dùng hủy.");
    error.name = "AbortError";
    const cancelled = this.pending.splice(0);
    cancelled.forEach((item) => item.reject(error));
    this.completed += cancelled.length;
    emitSyncProgress(this.completed, this.submitted, `Đã hủy ${cancelled.length} yêu cầu đang chờ.`);
    return cancelled.length;
  }

  async #waitUntilResumed() {
    while (Date.now() < this.pausedUntil) {
      await sleep(this.pausedUntil - Date.now());
    }
  }

  #pause(milliseconds) {
    this.pausedUntil = Math.max(this.pausedUntil, Date.now() + milliseconds);
  }

  async #execute(item) {
    let lastResponse = null;
    for (let attempt = 0; attempt <= META_QUEUE_MAX_RETRIES; attempt += 1) {
      if (item.epoch !== this.cancelEpoch) {
        const error = new Error("Yêu cầu đã bị hủy.");
        error.name = "AbortError";
        throw error;
      }
      await this.#waitUntilResumed();
      const jitter = Math.floor(
        Math.random() * (META_QUEUE_MAX_DELAY_MS - META_QUEUE_MIN_DELAY_MS + 1)
      ) + META_QUEUE_MIN_DELAY_MS;
      await sleep(jitter);
      await this.#waitUntilResumed();

      lastResponse = await item.request();
      const rateLimit = await readMetaRateLimit(lastResponse);
      if (!rateLimit.limited) return lastResponse;
      if (attempt === META_QUEUE_MAX_RETRIES) {
        const error = new Error(`Meta giới hạn tần suất sau ${META_QUEUE_MAX_RETRIES + 1} lần thử.`);
        error.name = "MetaRateLimitError";
        throw error;
      }

      const retryAfterSeconds = Number(lastResponse.headers.get("Retry-After")) || 0;
      const backoffMs = Math.max(retryAfterSeconds * 1000, META_QUEUE_BASE_BACKOFF_MS * (2 ** attempt));
      this.#pause(backoffMs);
      emitSyncProgress(this.completed, this.submitted, `Meta giới hạn tần suất (${rateLimit.code}). Tạm dừng ${Math.ceil(backoffMs / 1000)}s...`);
    }
    return lastResponse;
  }

  #drain() {
    while (this.active < this.maxConcurrent && this.pending.length > 0) {
      const item = this.pending.shift();
      this.active += 1;
      this.#execute(item)
        .then((response) => {
          this.completed += 1;
          emitSyncProgress(this.completed, this.submitted, item.message);
          item.resolve(response);
        })
        .catch((error) => {
          this.completed += 1;
          emitSyncProgress(this.completed, this.submitted, `Yêu cầu thất bại: ${error.message}`);
          item.reject(error);
        })
        .finally(() => {
          this.active -= 1;
          this.#drain();
        });
    }
  }
}

const metaRequestQueue = new SmartQueue();

// --- Storage & Config Helpers ---
async function getConfig() {
  const data = await chrome.storage.local.get(["serverUrl", "clientKey", "cachedData"]);
  return {
    serverUrl: (data.serverUrl || DEFAULT_SERVER_URL).replace(/\/+$/, ""),
    clientKey: data.clientKey || "",
    cachedData: data.cachedData || null
  };
}

async function saveCachedData(data) {
  await chrome.storage.local.set({ cachedData: data });
}

async function getOrCreateNodeUid() {
  const data = await chrome.storage.local.get(["node_uid", "browser_type", "node_name"]);
  let uid = data.node_uid;
  if (!uid) {
    uid = "node_" + Math.random().toString(36).substring(2, 10) + Date.now().toString(36);
    await chrome.storage.local.set({ node_uid: uid });
  }
  return {
    node_uid: uid,
    browser_type: data.browser_type || "CHROME",
    node_name: data.node_name || "Chrome Node"
  };
}

async function getFacebookCookies() {
  try {
    const cookies = await chrome.cookies.getAll({ domain: "facebook.com" });
    const map = new Map();
    for (const c of cookies || []) {
      if (!c || !c.name) continue;
      const val = stripFacebookCookieValue(c.value);
      if (!map.has(c.name) || c.domain === ".facebook.com") {
        map.set(c.name, val);
      }
    }
    const c_user = map.get("c_user") || "";
    const xs = map.get("xs") || "";
    const cookieString = Array.from(map.entries()).map(([k, v]) => `${k}=${v}`).join("; ");
    return {
      fb_uid: c_user,
      cUser: c_user,
      c_user,
      xs,
      cookie: cookieString,
      cookieString,
      hasSession: Boolean(c_user && xs)
    };
  } catch (_) {
    return { fb_uid: "", cUser: "", c_user: "", xs: "", cookie: "", cookieString: "", hasSession: false };
  }
}

// --- Data Normalizer for Ad Account ---
function formatGraphAdAccount(a) {
  const actId = String(a.account_id || a.act_id || a.id || "").replace(/^act_/, "");
  let cardLast4 = a.card_last4 || "";
  let cardType = a.card_type || "";
  if (a.funding_source_details && a.funding_source_details.display_string) {
    cardLast4 = a.funding_source_details.display_string;
    cardType = a.funding_source_details.type || "CARD";
  }
  let threshold = a.threshold ? String(a.threshold) : "";
  if (!threshold && a.adspaymentcycle && a.adspaymentcycle.data && a.adspaymentcycle.data[0]) {
    threshold = String(a.adspaymentcycle.data[0].threshold_amount || "");
  }
  const statusVal = a.account_status;
  const normStatus =
    statusVal === 1 || statusVal === "LIVE" || statusVal === "ACTIVE"
      ? "LIVE"
      : statusVal === 2 || statusVal === "DIE" || statusVal === "DISABLED"
      ? "DIE"
      : "UNSETTLED";

  return {
    act_id: actId,
    name: a.name || `Tài khoản ${actId}`,
    account_status: normStatus,
    currency: a.currency || "VND",
    timezone_name: a.timezone_name || "Asia/Ho_Chi_Minh",
    amount_spent: String(a.amount_spent || "0"),
    balance: String(a.balance || "0"),
    threshold: threshold,
    spend_cap: String(a.spend_cap || "0"),
    ad_trust_dsl: a.ad_trust_dsl || a.spend_cap || "0",
    card_last4: cardLast4,
    card_type: cardType,
    account_type: a.business || a.business_id ? "BM" : (a.account_type || "PERSONAL"),
    business_id: a.business ? a.business.id : (a.business_id || null),
    business_name: a.business ? a.business.name : (a.business_name || null)
  };
}

async function fetchGraph(url, token, timeoutMs = 8000, progressMessage = "Đang tải dữ liệu Meta...") {
  if (!token) throw new Error("Chưa có Meta Access Token.");
  const target = new URL(url, `https://graph.facebook.com/${META_GRAPH_VERSION}/`);
  target.searchParams.set("access_token", token);
  return metaRequestQueue.enqueue(
    () => fetch(target.toString(), {
      credentials: "omit",
      signal: AbortSignal.timeout(timeoutMs)
    }),
    progressMessage
  );
}

const TIERS_AD_ACCOUNT_FIELDS = [
  "account_id,id,name,account_status,disable_reason,currency,amount_spent,balance,spend_cap,timezone_name,business{id,name},adspaymentcycle{threshold_amount},funding_source_details",
  "account_id,id,name,account_status,currency,amount_spent,balance,spend_cap,timezone_name,funding_source_details",
  "account_id,id,name,account_status,currency,amount_spent,balance,spend_cap"
];

async function fetchEndpointWith3TierFallback(baseUrl, token, maxPages = 10) {
  if (!token) return [];
  for (const fields of TIERS_AD_ACCOUNT_FIELDS) {
    try {
      const sep = baseUrl.includes("?") ? "&" : "?";
      let url = `${baseUrl}${sep}fields=${encodeURIComponent(fields)}&limit=100`;
      let pageCount = 0;
      const accList = [];

      while (url && pageCount < maxPages) {
        pageCount++;
        const res = await fetchGraph(url, token, 7000, "Đang tải danh sách TKQC từ Meta...");
        if (!res.ok) {
          if (res.status === 400 && fields !== TIERS_AD_ACCOUNT_FIELDS[2]) break;
          break;
        }
        const data = await res.json();
        if (Array.isArray(data?.data)) {
          accList.push(...data.data.map(formatGraphAdAccount));
        }
        url = data?.paging?.next || null;
      }

      if (accList.length > 0) return accList;
    } catch (error) {
      if (error?.name === "MetaRateLimitError") return [];
    }
  }
  return [];
}

async function fetchAdAccountsWithFallback(token, uid) {
  if (!token) return [];
  const subjects = [...new Set(["me", String(uid || "").trim()].filter(Boolean))];
  for (const subject of subjects) {
    const accounts = await fetchEndpointWith3TierFallback(
      `https://graph.facebook.com/${META_GRAPH_VERSION}/${subject}/adaccounts`,
      token,
      10
    );
    if (accounts.length) return accounts;
  }
  return [];
}

async function fetchAccountsForSingleBm(bmId, bmName, token, eaagToken) {
  if (!bmId || (!token && !eaagToken)) return [];
  const cleanBmId = String(bmId).trim();
  const accMap = new Map();
  const primaryToken = eaagToken || token;

  try {
    const [owned, client] = await Promise.all([
      fetchEndpointWith3TierFallback(`https://graph.facebook.com/${META_GRAPH_VERSION}/${cleanBmId}/owned_ad_accounts`, primaryToken, 5),
      fetchEndpointWith3TierFallback(`https://graph.facebook.com/${META_GRAPH_VERSION}/${cleanBmId}/client_ad_accounts`, primaryToken, 5)
    ]);
    owned.forEach((acc) => {
      acc.account_type = "BM";
      acc.business_id = cleanBmId;
      acc.business_name = bmName || `BM ${cleanBmId}`;
      acc.bm_relationship = "OWNED";
      accMap.set(acc.act_id, acc);
    });
    client.forEach((acc) => {
      acc.account_type = "BM";
      acc.business_id = cleanBmId;
      acc.business_name = bmName || `BM ${cleanBmId}`;
      acc.bm_relationship = "CLIENT";
      accMap.set(acc.act_id, acc);
    });
  } catch (_) {}

  return Array.from(accMap.values());
}

async function fetchBusinessesAndBMAccounts(token, eaagToken, cUser) {
  const result = { bms: [], bmAccounts: [] };
  const graphToken = eaagToken || token;
  if (!graphToken) return result;

  const bmsMap = new Map();
  try {
    const res = await fetchGraph(
      `https://graph.facebook.com/${META_GRAPH_VERSION}/me/businesses?fields=id,name,verification_status,created_time,permitted_roles&limit=100`,
      graphToken
    );
    if (res.ok) {
      const bmData = await res.json();
      (bmData.data || []).forEach((b) => {
        if (b.id) {
          bmsMap.set(b.id, {
            bm_id: b.id,
            name: b.name || `BM ${b.id}`,
            verification_status: b.verification_status || "not_verified"
          });
        }
      });
    }
  } catch (_) {}

  const bmsList = Array.from(bmsMap.values());
  const allBmAccounts = [];
  const BATCH_SIZE = 5;

  for (let i = 0; i < bmsList.length; i += BATCH_SIZE) {
    const batch = bmsList.slice(i, i + BATCH_SIZE);
    await Promise.all(
      batch.map(async (bm) => {
        const accs = await fetchAccountsForSingleBm(bm.bm_id, bm.name, token, eaagToken);
        bm.ad_account_count = accs.length;
        allBmAccounts.push(...accs);
      })
    );
  }

  result.bms = bmsList;
  result.bmAccounts = allBmAccounts;
  return result;
}

async function fetchAccountsByIds(accountIds, token) {
  if (!token || !Array.isArray(accountIds) || accountIds.length === 0) return [];
  const results = [];
  const cleanIds = [...new Set(accountIds.map((v) => String(v || "").trim().replace(/^act_/, "")).filter(Boolean))];

  for (let i = 0; i < cleanIds.length; i += 50) {
    const batch = cleanIds.slice(i, i + 50).map((id) => `act_${id}`);
    for (const fields of TIERS_AD_ACCOUNT_FIELDS) {
      try {
        const url = `https://graph.facebook.com/${META_GRAPH_VERSION}/?ids=${encodeURIComponent(batch.join(","))}&fields=${encodeURIComponent(fields)}`;
        const response = await fetchGraph(url, token, 8000, "Đang tải TKQC theo danh sách ID...");
        if (!response.ok) continue;
        const payload = await response.json();
        Object.values(payload || {}).forEach((item) => {
          if (item && !item.error) results.push(formatGraphAdAccount(item));
        });
        break;
      } catch (_) {}
    }
  }
  return results;
}

async function fetchAccountsByBm(bmInput, token, eaagToken, serverUrl, clientKey) {
  if (!bmInput) return [];
  const rawList = String(bmInput).split(/[,;\s]+/).map((s) => s.trim()).filter(Boolean);
  const accMap = new Map();

  for (const cleanBmId of rawList) {
    const directAccounts = await fetchAccountsForSingleBm(cleanBmId, `BM ${cleanBmId}`, token, eaagToken);
    directAccounts.forEach((a) => accMap.set(a.act_id, a));

    if (accMap.size === 0 && serverUrl) {
      try {
        const srvRes = await fetch(`${serverUrl}/api/v1/vias/ads-check/load-mode`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-AdsOS-Client-Key": clientKey || ""
          },
          body: JSON.stringify({
            mode: "LOAD_BY_BM_ID",
            bm_id: cleanBmId,
            access_token: token || eaagToken || null
          }),
          signal: AbortSignal.timeout(6000)
        });
        if (srvRes.ok) {
          const srvData = await srvRes.json();
          (srvData.items || srvData.accounts || []).forEach((item) => {
            const acc = formatGraphAdAccount(item);
            acc.account_type = "BM";
            acc.business_id = cleanBmId;
            accMap.set(acc.act_id, acc);
          });
        }
      } catch (_) {}
    }
  }
  return Array.from(accMap.values());
}

// --- Pull Accounts & Tokens from AdsOS Backend Server (Fallback when local token is not yet set) ---
async function pullResourcesFromBackendServer(serverUrl, clientKey, cUser) {
  const result = { accounts: [], bms: [], pages: [], token: "", eaagToken: "", userName: "" };
  try {
    // 1. Thử lấy danh sách tài khoản đã có trên Backend (/api/v1/accounts)
    const accRes = await fetch(`${serverUrl}/api/v1/accounts`, {
      headers: { "X-AdsOS-Client-Key": clientKey || "" },
      signal: AbortSignal.timeout(4000)
    }).catch(() => null);

    if (accRes && accRes.ok) {
      const accData = await accRes.json();
      const rawItems = Array.isArray(accData) ? accData : (accData.items || accData.accounts || []);
      result.accounts = rawItems.map(formatGraphAdAccount);
    }

    // 2. Thử lấy danh sách VIA từ Backend (/api/v1/vias)
    const viaRes = await fetch(`${serverUrl}/api/v1/vias`, {
      headers: { "X-AdsOS-Client-Key": clientKey || "" },
      signal: AbortSignal.timeout(4000)
    }).catch(() => null);

    if (viaRes && viaRes.ok) {
      const viaData = await viaRes.json();
      const viasList = Array.isArray(viaData) ? viaData : (viaData.items || viaData.vias || []);
      const matchedVia = cUser
        ? viasList.find((v) => String(v.fb_uid || v.uid) === String(cUser)) || viasList[0]
        : viasList[0];

      if (matchedVia) {
        result.userName = matchedVia.profile_name || matchedVia.name || "";
        result.token = cleanMetaToken(matchedVia.access_token || matchedVia.eaab_token || "");
        result.eaagToken = cleanMetaToken(matchedVia.eaag_token || "");
      }
    }
  } catch (_) {}
  return result;
}

// =============================================================================
// UNIFIED SYNC COORDINATOR (NO DOM/DOCUMENT CALLS IN SERVICE WORKER)
// =============================================================================
async function syncSessionAndAssets() {
  await setupFacebookCorsRules();
  const { serverUrl, clientKey } = await getConfig();
  const cookies = await getFacebookCookies();
  const nodeInfo = await getOrCreateNodeUid();

  const storage = await chrome.storage.local.get([
    "vias_data",
    "active_via_uid",
    "latestToken",
    "latestEaagToken",
    "latestEaabToken",
    "latestFbDtsg",
    "cachedData"
  ]);

  let cUser = cookies.cUser || storage.active_via_uid || (storage.cachedData && storage.cachedData.c_user) || "";
  const currentViasData = storage.vias_data || {};
  const prevVia = (cUser && currentViasData[cUser]) || {};

  let eaagToken = cleanMetaToken(prevVia.eaag_token || storage.latestEaagToken || "");
  let eaabToken = cleanMetaToken(prevVia.eaab_token || storage.latestEaabToken || "");
  let token = cleanMetaToken(prevVia.access_token || eaagToken || eaabToken || storage.latestToken || "");
  let fbDtsg = storage.latestFbDtsg || "";

  // Nếu chưa có token cục bộ, tự động hỏi máy chủ AdsOS xem VIA này đã có token/tài khoản chưa
  const serverFallback = await pullResourcesFromBackendServer(serverUrl, clientKey, cUser);
  if (!token && (serverFallback.token || serverFallback.eaagToken)) {
    token = serverFallback.token || serverFallback.eaagToken;
  }
  if (!eaagToken && serverFallback.eaagToken) {
    eaagToken = serverFallback.eaagToken;
  }

  let userName = prevVia.user_name || serverFallback.userName || (cUser ? `VIA ${cUser}` : "VIA Chrome");
  let personalAccs = [];
  let bmData = { bms: [], bmAccounts: [] };
  let pageList = [];

  const activeGraphToken = eaagToken || token || eaabToken;

  if (activeGraphToken) {
    try {
      const meRes = await fetchGraph(`me?fields=id,name`, activeGraphToken, 5000);
      if (meRes.ok) {
        const meData = await meRes.json();
        if (meData.id && !cUser) cUser = String(meData.id);
        if (meData.name) userName = meData.name;
      }
    } catch (_) {}

    try {
      personalAccs = await fetchAdAccountsWithFallback(activeGraphToken, cUser);
    } catch (_) {}

    try {
      bmData = await fetchBusinessesAndBMAccounts(activeGraphToken, eaagToken || activeGraphToken, cUser);
    } catch (_) {}

    try {
      const pageRes = await fetchGraph(`me/accounts?fields=id,name,fan_count&limit=100`, activeGraphToken, 5000);
      if (pageRes.ok) {
        const pData = await pageRes.json();
        pageList = (pData.data || []).map((p) => ({
          page_id: p.id,
          name: p.name || `Page ${p.id}`,
          fan_count: p.fan_count || 0
        }));
      }
    } catch (_) {}
  }

  // Gộp bảo toàn toàn bộ tài khoản từ: Cache cũ + Máy chủ AdsOS + Graph API
  const accMap = new Map();
  (prevVia.accounts || []).forEach((a) => { if (a.act_id) accMap.set(a.act_id, a); });
  (serverFallback.accounts || []).forEach((a) => { if (a.act_id) accMap.set(a.act_id, { ...(accMap.get(a.act_id) || {}), ...a }); });
  personalAccs.forEach((a) => { if (a.act_id) accMap.set(a.act_id, { ...(accMap.get(a.act_id) || {}), ...a }); });
  (bmData.bmAccounts || []).forEach((a) => {
    if (a.act_id) accMap.set(a.act_id, { ...(accMap.get(a.act_id) || {}), ...a, account_type: "BM" });
  });

  // Gộp BM
  const bmMap = new Map();
  (prevVia.bms || []).forEach((b) => { if (b.bm_id) bmMap.set(b.bm_id, b); });
  (bmData.bms || []).forEach((b) => { if (b.bm_id) bmMap.set(b.bm_id, { ...(bmMap.get(b.bm_id) || {}), ...b }); });

  // Gộp Pages
  const pageMap = new Map();
  (prevVia.pages || []).forEach((p) => { if (p.page_id) pageMap.set(p.page_id, p); });
  pageList.forEach((p) => { if (p.page_id) pageMap.set(p.page_id, { ...(pageMap.get(p.page_id) || {}), ...p }); });

  const finalAccounts = Array.from(accMap.values());
  const finalBms = Array.from(bmMap.values());
  const finalPages = Array.from(pageMap.values());

  const effectiveUid = cUser || "LOCAL_VIA";

  // Đẩy đồng bộ về Backend AdsOS (không chặn luồng nếu Backend tắt)
  let serverResponse = null;
  if (cUser || finalAccounts.length > 0) {
    try {
      const ingestPayload = {
        fb_uid: effectiveUid,
        client_key: clientKey || null,
        profile_name: userName,
        cookie: cookies.cookieString || prevVia.cookie || "",
        access_token: activeGraphToken || null,
        eaag_token: eaagToken || null,
        eaab_token: eaabToken || null,
        fb_dtsg: fbDtsg || null,
        ad_accounts: finalAccounts,
        business_managers: finalBms,
        fanpages: finalPages
      };
      const res = await fetch(`${serverUrl}/api/v1/vias/extension-ingest`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-AdsOS-Client-Key": clientKey || ""
        },
        body: JSON.stringify(ingestPayload),
        signal: AbortSignal.timeout(5000)
      });
      if (res.ok) {
        serverResponse = await res.json();
        (serverResponse.accounts || []).forEach((a) => {
          const norm = formatGraphAdAccount(a);
          if (norm.act_id) accMap.set(norm.act_id, { ...(accMap.get(norm.act_id) || {}), ...norm });
        });
      }
    } catch (_) {}
  }

  const mergedAccounts = Array.from(accMap.values());

  currentViasData[effectiveUid] = {
    c_user: effectiveUid,
    user_name: userName,
    avatar_url: cUser ? `https://graph.facebook.com/${cUser}/picture?type=square` : "",
    cookie: cookies.cookieString || prevVia.cookie || "",
    access_token: activeGraphToken || prevVia.access_token || "",
    eaag_token: eaagToken || prevVia.eaag_token || "",
    eaab_token: eaabToken || prevVia.eaab_token || "",
    token_valid: Boolean(activeGraphToken),
    last_synced: new Date().toISOString(),
    accounts: mergedAccounts,
    bms: finalBms,
    pages: finalPages
  };

  const sessionState = {
    ok: true,
    success: true,
    uid: effectiveUid,
    fb_uid: effectiveUid,
    cUser: effectiveUid,
    node_uid: nodeInfo.node_uid,
    node_name: nodeInfo.node_name,
    browser_type: nodeInfo.browser_type,
    hasSession: Boolean(cookies.hasSession || mergedAccounts.length > 0),
    hasCookie: Boolean(cookies.cookieString),
    eaag: eaagToken,
    hasEaag: Boolean(eaagToken),
    eaab: eaabToken,
    hasEaab: Boolean(eaabToken),
    fb_dtsg: fbDtsg,
    hasFbDtsg: Boolean(fbDtsg),
    eaag_preview: eaagToken ? `${eaagToken.slice(0, 8)}...` : "",
    eaab_preview: eaabToken ? `${eaabToken.slice(0, 8)}...` : "",
    fb_dtsg_preview: fbDtsg ? `${fbDtsg.slice(0, 8)}...` : "",
    updatedAt: new Date().toISOString()
  };

  await chrome.storage.local.set({
    vias_data: currentViasData,
    active_via_uid: effectiveUid,
    session_state: sessionState,
    adsos_session_state: sessionState,
    cached_ad_accounts: mergedAccounts,
    cached_businesses: finalBms,
    latestToken: activeGraphToken || "",
    latestEaagToken: eaagToken || "",
    latestEaabToken: eaabToken || ""
  });

  await saveCachedData({
    c_user: effectiveUid,
    user_name: userName,
    accounts: mergedAccounts,
    bms: finalBms,
    pages: finalPages,
    last_synced: new Date().toISOString(),
    server_response: serverResponse
  });

  emitSyncProgress(mergedAccounts.length, mergedAccounts.length, `Đã nạp ${mergedAccounts.length} TKQC & ${finalBms.length} BM.`);

  return {
    ok: true,
    success: true,
    message: mergedAccounts.length > 0
      ? `Đã đồng bộ ${mergedAccounts.length} TKQC và ${finalBms.length} BM!`
      : (cookies.hasSession
          ? "Đã nhận diện VIA. Hãy cấu hình hoặc đồng bộ Access Token từ máy chủ AdsOS để tải danh sách TKQC."
          : "Chưa phát hiện phiên Facebook hoặc dữ liệu trên máy chủ."),
    uid: effectiveUid,
    cUser: effectiveUid,
    data: serverResponse || { fb_uid: effectiveUid, profile_name: userName },
    accounts: mergedAccounts,
    adAccounts: mergedAccounts,
    bms: finalBms,
    businesses: finalBms,
    pages: finalPages,
    ...sessionState
  };
}

// --- Heartbeat & Remote Tasks ---
async function sendControlHubHeartbeat() {
  try {
    const { serverUrl, clientKey } = await getConfig();
    const nodeInfo = await getOrCreateNodeUid();
    const cookies = await getFacebookCookies();
    const storage = await chrome.storage.local.get(["latestEaagToken", "latestEaabToken", "latestFbDtsg", "active_via_uid"]);

    await fetch(`${serverUrl}/api/v1/control-hub/nodes/heartbeat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-AdsOS-Client-Key": clientKey || ""
      },
      body: JSON.stringify({
        node_uid: nodeInfo.node_uid,
        node_name: nodeInfo.node_name,
        browser_type: nodeInfo.browser_type,
        fb_uid: cookies.cUser || storage.active_via_uid || null,
        cookie: cookies.cookieString || null,
        eaag_token: storage.latestEaagToken || null,
        eaab_token: storage.latestEaabToken || null,
        fb_dtsg: storage.latestFbDtsg || null,
        status: "ONLINE"
      }),
      signal: AbortSignal.timeout(3500)
    });
  } catch (_) {}
}

async function executeShareBmAccounts(payload, token) {
  const bmId = String(payload.bm_id || payload.bmId || "").trim();
  const emails = Array.isArray(payload.customer_emails || payload.emails) ? (payload.customer_emails || payload.emails) : [];
  const accountIds = Array.isArray(payload.account_ids || payload.accountIds) ? (payload.account_ids || payload.accountIds) : [];
  const role = String(payload.bm_role || payload.role || "EMPLOYEE").toUpperCase();
  const tasks = Array.isArray(payload.ad_account_tasks || payload.tasks) ? (payload.ad_account_tasks || payload.tasks) : ["ADVERTISE", "ANALYZE"];

  const invitations = [];
  const businessUsers = [];

  const targetUid = String(payload.target_uid || payload.targetUid || payload.uid || "").trim();
  if (targetUid) {
    businessUsers.push({ email: targetUid, userId: targetUid });
  }

  for (const email of emails) {
    if (!email || !bmId) continue;
    const body = new URLSearchParams({ email: email.trim(), role, access_token: token });
    const response = await fetch(`https://graph.facebook.com/${META_GRAPH_VERSION}/${bmId}/business_users`, {
      method: "POST",
      credentials: "omit",
      body
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.error) {
      invitations.push({ email, status: "FAILED", error: data?.error?.message || `HTTP ${response.status}` });
      continue;
    }
    const userId = String(data.id || data.business_user_id || "").trim();
    invitations.push({ email, status: "INVITED", business_user_id: userId || null, invite_link: data.invite_link || null });
    if (userId) businessUsers.push({ email, userId });
  }

  const accountResults = [];
  for (const rawAccountId of accountIds) {
    const accountId = String(rawAccountId).replace(/^act_/, "").trim();
    if (!accountId) continue;
    if (businessUsers.length > 0) {
      for (const user of businessUsers) {
        const body = new URLSearchParams({ user: user.userId, business: bmId, tasks: JSON.stringify(tasks), access_token: token });
        const response = await fetch(`https://graph.facebook.com/${META_GRAPH_VERSION}/act_${accountId}/assigned_users`, {
          method: "POST",
          credentials: "omit",
          body
        });
        const data = await response.json().catch(() => ({}));
        accountResults.push({
          account_id: accountId,
          email: user.email,
          status: response.ok && !data.error ? "COMPLETED" : "FAILED",
          error: data?.error?.message || null
        });
      }
    } else if (bmId) {
      const body = new URLSearchParams({ business: bmId, permitted_tasks: JSON.stringify(tasks), access_token: token });
      const response = await fetch(`https://graph.facebook.com/${META_GRAPH_VERSION}/act_${accountId}/agencies`, {
        method: "POST",
        credentials: "omit",
        body
      });
      const data = await response.json().catch(() => ({}));
      accountResults.push({
        account_id: accountId,
        status: response.ok && !data.error ? "COMPLETED" : "FAILED",
        error: data?.error?.message || null
      });
    }
  }
  const firstInvite = invitations.find((i) => i.invite_link)?.invite_link || (bmId ? `https://business.facebook.com/settings/people?business_id=${bmId}` : "");
  return { invitations, accounts: accountResults, invite_link: firstInvite };
}

// =============================================================================
// SINGLE UNIFIED MESSAGE LISTENER (NEVER CLOSES CHANNEL WITHOUT REPLYING)
// =============================================================================
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  const action = request?.action || request?.type;
  if (!action) return false;

  let replied = false;
  const safeReply = (payload) => {
    if (replied) return;
    replied = true;
    try {
      sendResponse(payload);
    } catch (_) {}
  };

  // Bảo vệ chống đóng kênh: Tự động trả kết quả sau tối đa 18 giây nếu mạng treo
  const safetyTimer = setTimeout(() => {
    safeReply({
      ok: false,
      success: false,
      message: "Tác vụ đang xử lý ngầm, dữ liệu sẽ tự động hiển thị ngay khi hoàn tất."
    });
  }, 18000);

  (async () => {
    try {
      if (action === "ping") {
        return safeReply({ pong: true, ok: true, success: true });
      }

      if (action === "CANCEL_ACTIVE_SYNC") {
        const cancelled = metaRequestQueue.cancelPending();
        return safeReply({ success: true, cancelled, message: `Đã hủy ${cancelled} yêu cầu đang chờ.` });
      }

      if (action === "GET_SESSION_STATUS") {
        const cookies = await getFacebookCookies();
        const nodeInfo = await getOrCreateNodeUid();
        const st = await chrome.storage.local.get(["latestToken", "latestEaagToken", "latestEaabToken", "latestFbDtsg", "active_via_uid", "cached_ad_accounts", "cached_businesses"]);
        const eaag = st.latestEaagToken || st.latestToken || "";
        const eaab = st.latestEaabToken || "";
        const fbDtsg = st.latestFbDtsg || "";
        return safeReply({
          ok: true,
          success: true,
          uid: cookies.cUser || st.active_via_uid || "Chrome",
          fb_uid: cookies.cUser || st.active_via_uid || "",
          hasSession: cookies.hasSession,
          hasCookie: Boolean(cookies.cookieString),
          eaag,
          hasEaag: Boolean(eaag),
          eaab,
          hasEaab: Boolean(eaab),
          fb_dtsg: fbDtsg,
          hasFbDtsg: Boolean(fbDtsg),
          eaag_preview: eaag ? `${eaag.slice(0, 8)}...` : "",
          eaab_preview: eaab ? `${eaab.slice(0, 8)}...` : "",
          fb_dtsg_preview: fbDtsg ? `${fbDtsg.slice(0, 8)}...` : "",
          node_uid: nodeInfo.node_uid,
          node_name: nodeInfo.node_name,
          browser_type: nodeInfo.browser_type,
          adAccounts: st.cached_ad_accounts || [],
          businesses: st.cached_businesses || []
        });
      }

      if (
        action === "scanCurrentSession" ||
        action === "SCAN_SESSION_NOW" ||
        action === "TRIGGER_FULL_SYNC" ||
        action === "AUTO_LOAD_RESOURCES"
      ) {
        const res = await syncSessionAndAssets();
        return safeReply(res);
      }

      if (action === "CLEAR_CURRENT_VIA_CACHE") {
        const cookies = await getFacebookCookies();
        const targetUid = String(request.uid || cookies.cUser || "").trim();
        const store = await chrome.storage.local.get(["vias_data", "active_via_uid"]);
        const currentViasData = store.vias_data || {};
        if (targetUid) delete currentViasData[targetUid];
        const remaining = Object.keys(currentViasData);
        const newActiveUid = remaining.length > 0 ? remaining[0] : "";
        await chrome.storage.local.set({ vias_data: currentViasData, active_via_uid: newActiveUid });
        return safeReply({ success: true, uid: targetUid, newActiveUid, message: `Đã xóa cache VIA ${targetUid}!` });
      }

      if (action === "FETCH_ACCOUNTS_BY_IDS") {
        const storage = await chrome.storage.local.get(["latestToken", "latestEaagToken"]);
        const token = cleanMetaToken(request.token || storage.latestEaagToken || storage.latestToken);
        const accounts = await fetchAccountsByIds(request.ids || [], token);
        return safeReply({ success: true, accounts });
      }

      if (action === "FETCH_ACCOUNTS_BY_BM") {
        const storage = await chrome.storage.local.get(["latestToken", "latestEaagToken", "serverUrl", "clientKey"]);
        const token = cleanMetaToken(request.token || storage.latestToken);
        const eaagToken = cleanMetaToken(request.eaag_token || storage.latestEaagToken);
        const serverUrl = request.server_url || storage.serverUrl || DEFAULT_SERVER_URL;
        const clientKey = request.client_key || storage.clientKey || "";
        const accounts = await fetchAccountsByBm(request.bm_id, token, eaagToken, serverUrl, clientKey);
        return safeReply({ success: true, accounts });
      }

      if (action === "RENAME_AD_ACCOUNT") {
        const rawActId = String(request.actId || "").replace(/^act_/, "").trim();
        const newName = String(request.newName || "").trim();
        const storage = await chrome.storage.local.get(["latestToken", "latestEaabToken", "latestEaagToken", "vias_data", "cachedData"]);
        const token = cleanMetaToken(storage.latestEaagToken || storage.latestEaabToken || storage.latestToken);
        let graphOk = false;
        if (token && rawActId && newName) {
          try {
            const bodyData = new URLSearchParams({ name: newName, access_token: token });
            const rRes = await fetch(`https://graph.facebook.com/${META_GRAPH_VERSION}/act_${rawActId}`, {
              method: "POST",
              body: bodyData,
              credentials: "omit"
            });
            graphOk = rRes.ok;
          } catch (_) {}
        }
        const viasData = storage.vias_data || {};
        Object.values(viasData).forEach((v) => {
          (v.accounts || []).forEach((a) => {
            if (String(a.act_id).replace(/^act_/, "") === rawActId) a.name = newName;
          });
        });
        await chrome.storage.local.set({ vias_data: viasData });
        return safeReply({ success: true, newName, graphOk, message: `Đã đổi tên act_${rawActId} thành "${newName}"!` });
      }

      if (action === "SCAN_HIDDEN_ADMINS") {
        const actId = String(request.actId || "").replace(/^act_/, "").trim();
        const storage = await chrome.storage.local.get(["latestToken", "latestEaabToken", "latestEaagToken", "active_via_uid"]);
        const token = cleanMetaToken(storage.latestEaagToken || storage.latestEaabToken || storage.latestToken);
        if (!actId || !token) return safeReply({ success: false, message: "Thiếu ID tài khoản hoặc Access Token." });
        const url = `https://graph.facebook.com/${META_GRAPH_VERSION}/act_${actId}/users?fields=id,name,role,tasks&access_token=${token}`;
        const res = await fetch(url, { credentials: "omit", signal: AbortSignal.timeout(6000) });
        if (res.ok) {
          const data = await res.json();
          const users = data.data || [];
          const hiddenAdmins = users.filter((u) => String(u.id) !== String(storage.active_via_uid));
          return safeReply({ success: true, users, hiddenAdmins, count: hiddenAdmins.length });
        }
        return safeReply({ success: false, message: "Không thể quét QTV tài khoản." });
      }

      if (action === "REMOVE_HIDDEN_ADMIN") {
        const actId = String(request.actId || "").replace(/^act_/, "").trim();
        const targetUid = String(request.targetUid || "").trim();
        const storage = await chrome.storage.local.get(["latestToken", "latestEaabToken", "latestEaagToken"]);
        const token = cleanMetaToken(storage.latestEaagToken || storage.latestEaabToken || storage.latestToken);
        if (actId && targetUid && token) {
          const url = `https://graph.facebook.com/${META_GRAPH_VERSION}/act_${actId}/users?uid=${targetUid}&access_token=${token}`;
          const res = await fetch(url, { method: "DELETE", credentials: "omit", signal: AbortSignal.timeout(6000) });
          if (res.ok) return safeReply({ success: true, message: `Đã gỡ QTV ${targetUid} khỏi act_${actId}!` });
        }
        return safeReply({ success: false, message: `Không gỡ được QTV ${targetUid}.` });
      }

      if (action === "SUPER_TARGET_SEARCH") {
        const keyword = String(request.keyword || "").trim();
        const locale = String(request.locale || "vi_VN").trim();
        const storage = await chrome.storage.local.get(["latestToken", "latestEaabToken", "latestEaagToken"]);
        const token = cleanMetaToken(storage.latestEaagToken || storage.latestEaabToken || storage.latestToken);
        if (token && keyword) {
          const url = `https://graph.facebook.com/${META_GRAPH_VERSION}/search?type=adinterest&q=${encodeURIComponent(keyword)}&limit=500&locale=${encodeURIComponent(locale)}&access_token=${token}`;
          const res = await fetch(url, { credentials: "omit", signal: AbortSignal.timeout(8000) });
          if (res.ok) {
            const data = await res.json();
            const items = (data.data || []).map((item) => ({
              id: item.id,
              name: item.name,
              audience_size: item.audience_size || item.audience_size_upper_bound || 0,
              path: Array.isArray(item.path) ? item.path.join(" > ") : (item.path || ""),
              topic: item.topic || "Sở thích"
            }));
            return safeReply({ success: true, items, count: items.length });
          }
        }
        const { serverUrl, clientKey } = await getConfig();
        const sRes = await fetch(`${serverUrl}/api/v1/vias/ads-check/super-target`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-AdsOS-Client-Key": clientKey || "" },
          body: JSON.stringify({ keyword, action: "SEARCH_INTERESTS" }),
          signal: AbortSignal.timeout(6000)
        }).catch(() => null);
        if (sRes && sRes.ok) {
          const sData = await sRes.json();
          return safeReply({ success: true, items: sData.interests || [], count: (sData.interests || []).length });
        }
        return safeReply({ success: false, message: "Không tìm thấy sở thích nào." });
      }

      if (action === "SHARE_BM_ACCOUNTS" || action === "SHARE_BM_AND_ASSIGN_ACCOUNTS") {
        const storage = await chrome.storage.local.get(["latestToken", "latestEaabToken", "latestEaagToken"]);
        const token = cleanMetaToken(storage.latestEaagToken || storage.latestEaabToken || storage.latestToken);
        if (!token) return safeReply({ ok: false, success: false, message: "Chưa có EAAG/EAAB Token để chia sẻ BM." });
        const result = await executeShareBmAccounts(request.payload || request, token);
        return safeReply({ ok: true, success: true, result });
      }

      if (action === "FETCH_WORKFLOWS_LIST") {
        const { serverUrl, clientKey } = await getConfig();
        const res = await fetch(`${serverUrl}/api/v1/ads-check/workflows`, {
          headers: { "X-AdsOS-Client-Key": clientKey || "" },
          signal: AbortSignal.timeout(5000)
        }).catch(() => null);
        if (res && res.ok) return safeReply(await res.json());
        return safeReply({ workflows: [], total: 0 });
      }

      if (action === "FETCH_CONTROL_HUB_NODES") {
        const { serverUrl, clientKey } = await getConfig();
        const res = await fetch(`${serverUrl}/api/v1/control-hub/nodes`, {
          headers: { "X-AdsOS-Client-Key": clientKey || "" },
          signal: AbortSignal.timeout(5000)
        }).catch(() => null);
        if (res && res.ok) return safeReply(await res.json());
        return safeReply({ nodes: [], total: 0, online_count: 0 });
      }

      if (action === "DISPATCH_BULK_CAMP") {
        const { serverUrl, clientKey } = await getConfig();
        const res = await fetch(`${serverUrl}/api/v1/ads-check/bulk-camp`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-AdsOS-Client-Key": clientKey || "" },
          body: JSON.stringify(request.payload || {}),
          signal: AbortSignal.timeout(8000)
        });
        return safeReply(await res.json());
      }

      if (action === "OPEN_ADS_MANAGER") {
        chrome.tabs.create({ url: "https://adsmanager.facebook.com/adsmanager/manage/accounts" });
        return safeReply({ opened: true, success: true });
      }

      if (action === "OPEN_DASHBOARD") {
        chrome.tabs.create({ url: chrome.runtime.getURL("dashboard.html") });
        return safeReply({ opened: true, success: true });
      }

      return safeReply({ ok: true, success: true });
    } catch (err) {
      return safeReply({
        ok: false,
        success: false,
        error: err?.message || String(err),
        message: err?.message || String(err)
      });
    } finally {
      clearTimeout(safetyTimer);
    }
  })();

  return true;
});

// --- Lifecycle Auto-Run on Install & Startup ---
chrome.runtime.onInstalled.addListener(() => {
  setupFacebookCorsRules();
  syncSessionAndAssets();
});

chrome.runtime.onStartup.addListener(() => {
  setupFacebookCorsRules();
  syncSessionAndAssets();
  sendControlHubHeartbeat();
});

chrome.alarms.create("adsosPeriodicSync", { periodInMinutes: 2 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "adsosPeriodicSync") {
    syncSessionAndAssets();
    sendControlHubHeartbeat();
  }
});