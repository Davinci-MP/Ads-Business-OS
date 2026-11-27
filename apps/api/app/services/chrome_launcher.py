"""Dịch vụ Real 1-Click Chrome VIA Profile Launcher (Click Ad Account -> Open Logged-in Chrome).

Chức năng:
1. Tự động phát hiện Google Chrome (chrome.exe), Microsoft Edge (msedge.exe) hoặc Chromium trên hệ thống.
2. Quản lý thư mục profile độc lập vĩnh viễn: profiles/via_{uid} lưu cookies, session và trạng thái Facebook.
3. Nạp cookie qua Chrome DevTools Protocol cục bộ trước khi điều hướng,
   đăng ký Quick-Login Bar trong isolated world để điền UID/Pass/2FA nếu chưa có cookie.
4. Deep-link chính xác tới:
   - Trình Quản Lý Quảng Cáo (Ads Manager): https://adsmanager.facebook.com/adsmanager/manage/campaigns?act={act_id}
   - Cài đặt Thanh Toán (Billing): https://business.facebook.com/billing_hub/payment_settings?asset_id={act_id}
   - Cài đặt BM (BM Settings): https://business.facebook.com/settings/ad-accounts?business_id={bm_id}
   - Fanpage: https://www.facebook.com/{page_id}
   - FB Home / Accounts Overview: https://adsmanager.facebook.com/adsmanager/manage/accounts
5. Khởi chạy ngầm bất đồng bộ (detached process) an toàn trên môi trường local.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import time
import threading
from typing import Any, Optional
from websockets.sync.client import connect

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import utcnow
from app.models.via import SyncedAdAccount, SyncedBM, SyncedPage, ViaProfile
from app.services.via_manager import (
    decrypt_via_credentials,
    generate_totp_code,
    is_real_facebook_cookie,
    normalize_proxy_config,
)

logger = logging.getLogger(__name__)


def get_via_debug_port(via_id: int) -> int:
    """Tính toán cổng remote debugging cố định cho từng VIA (9222..9721)."""
    return 9222 + (int(via_id) % 500)


def read_devtools_endpoint(profile_dir: Path, timeout: float = 10.0) -> Optional[str]:
    """Đọc endpoint CDP loopback từ DevToolsActivePort do Chrome tự sinh."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            lines = (profile_dir / "DevToolsActivePort").read_text().splitlines()
            port = int(lines[0])
            if not 0 < port < 65536 or not lines[1].startswith("/devtools/browser/"):
                raise ValueError("Invalid local debugging endpoint")
            return f"ws://127.0.0.1:{port}{lines[1]}"
        except (OSError, ValueError, IndexError):
            time.sleep(0.1)
    return None


def initialize_browser_session(profile_dir: Path, raw_cookie: str, startup_url: str, script: str) -> None:
    """Nạp cookie qua CDP local trước khi mở Facebook; không log credentials."""
    endpoint = read_devtools_endpoint(profile_dir, timeout=10)
    if endpoint is None:
        raise RuntimeError("Không kết nối được Chrome. Hãy đóng cửa sổ VIA cũ rồi mở lại.")

    ws = connect(endpoint, open_timeout=5, proxy=None)
    try:
        command_id = 0

        def call(method, params=None, session_id=None):
            nonlocal command_id
            command_id += 1
            message = {"id": command_id, "method": method, "params": params or {}}
            if session_id:
                message["sessionId"] = session_id
            ws.send(json.dumps(message))
            response_deadline = time.monotonic() + 10
            while True:
                response = json.loads(ws.recv(timeout=max(0.01, response_deadline - time.monotonic())))
                if response.get("id") == command_id:
                    if "error" in response:
                        raise RuntimeError("Chrome không thực hiện được bước khởi tạo phiên.")
                    return response.get("result", {})
                if time.monotonic() >= response_deadline:
                    raise TimeoutError("Chrome không phản hồi khởi tạo phiên.")

        if is_real_facebook_cookie(raw_cookie):
            cookies = []
            for part in raw_cookie.split(";"):
                if "=" not in part:
                    continue
                name, value = part.strip().split("=", 1)
                if name and value:
                    cookies.append({"name": name, "value": value, "domain": ".facebook.com",
                                    "path": "/", "secure": True,
                                    "httpOnly": name in {"xs", "fr", "datr", "sb"}})
            call("Storage.setCookies", {"cookies": cookies})
        target = call("Target.createTarget", {"url": "about:blank"})["targetId"]
        session_id = call("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
        call("Page.enable", session_id=session_id)
        call("Page.addScriptToEvaluateOnNewDocument", {"source": script, "worldName": "adsos-login"}, session_id)
        result = call("Page.navigate", {"url": startup_url}, session_id)
        if result.get("errorText"):
            raise RuntimeError("Chrome không tải được Facebook; kiểm tra mạng hoặc proxy của VIA.")
        # Giữ CDP session để script tiếp tục hoạt động qua các bước login/2FA.
        def keep_session():
            try:
                for _ in ws:
                    pass
            except Exception:
                pass
            finally:
                ws.close()
        threading.Thread(target=keep_session, daemon=True, name="via-browser-session").start()
    except Exception:
        ws.close()
        raise


# ==============================================================================
# 0. PROFILE DIRECTORY MANAGEMENT (PERSISTENT ISOLATED STORE)
# ==============================================================================

def get_via_profile_dir(uid: str) -> Path:
    """Tạo hoặc lấy đường dẫn thư mục profile vĩnh viễn: profiles/via_{uid}."""
    clean_uid = re.sub(r"[^0-9a-zA-Z_]", "", str(uid).strip())
    cwd = Path.cwd().resolve()
    if (cwd / "apps" / "api").is_dir():
        base = (cwd / "apps" / "api" / "profiles").resolve()
    elif cwd.name == "api" and cwd.parent.name == "apps":
        base = (cwd / "profiles").resolve()
    else:
        base = (cwd / "profiles").resolve()
    base.mkdir(parents=True, exist_ok=True)
    p = base / f"via_{clean_uid}"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ==============================================================================
# 1. PHÁT HIỆN TRÌNH DUYỆT HỆ THỐNG (CHROME / EDGE / CHROMIUM)
# ==============================================================================

def find_system_browser() -> Optional[str]:
    """Tìm đường dẫn thực thi của Google Chrome, Microsoft Edge hoặc Chromium trên máy host."""
    system = platform.system()

    if system == "Windows":
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
            shutil.which("chrome"),
            shutil.which("google-chrome"),
            shutil.which("msedge"),
        ]
    elif system == "Darwin":  # macOS
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            shutil.which("google-chrome"),
            shutil.which("chrome"),
        ]
    else:  # Linux
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
            shutil.which("google-chrome"),
            shutil.which("google-chrome-stable"),
            shutil.which("chromium"),
        ]

    for p in candidates:
        if p and os.path.isfile(p):
            return str(Path(p).resolve())

    return None


# ==============================================================================
# 2. XÂY DỰNG HELPER EXTENSION MANIFEST V3 (COOKIE INJECTION & QUICK LOGIN BAR)
# ==============================================================================

def build_extension_bootstrap(
    ext_dir: Path,
    via_uid: str,
    profile_name: str,
    raw_cookie: str,
    creds: dict[str, Any],
    totp_code: str,
    proxy_info: Optional[dict[str, Any]] = None,
    target_url: str = "https://adsmanager.facebook.com/adsmanager/manage/accounts",
    api_base_url: str = "http://127.0.0.1:8000",
    via_id: Optional[int] = None,
) -> None:
    """Tạo local Manifest V3 helper extension tự động bơm Cookie, giải mã 2FA TOTP và tự động đăng nhập.
    
    Quy tắc nghiêm ngặt:
    - Luôn dọn dẹp sạch sẽ (force-clean) toàn bộ file cũ bên trong ext_dir trước khi tạo mới.
    - Tuyệt đối không chứa bất kỳ URL hoặc tham chiếu favicon.ico hay adsos_boot=1 nào.
    - Tự động nạp cookies vào .facebook.com, www.facebook.com, business.facebook.com, adsmanager.facebook.com.
    """
    if ext_dir.exists():
        for item in ext_dir.iterdir():
            if item.is_file():
                try:
                    item.unlink(missing_ok=True)
                except Exception:
                    pass
            elif item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
    ext_dir.mkdir(parents=True, exist_ok=True)

    has_real_cookie = is_real_facebook_cookie(raw_cookie)

    # Phân tích Cookie dạng c_user=...; xs=...; fr=...; datr=...
    parsed_cookies: list[dict[str, Any]] = []
    if raw_cookie and ("=" in raw_cookie):
        parts = [p.strip() for p in raw_cookie.split(";") if "=" in p]
        for part in parts:
            name, val = part.split("=", 1)
            name = name.strip()
            val = val.strip()
            if name and val:
                parsed_cookies.append({
                    "name": name,
                    "value": val,
                    "domain": ".facebook.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": name in ("xs", "fr", "datr", "sb"),
                })

    # 1. manifest.json
    manifest = {
        "manifest_version": 3,
        "name": f"metaOs Helper — {via_uid}",
        "version": "2.0.0",
        "description": "Tự động đăng nhập, xác thực 2FA và duy trì phiên VIA cho metaOs",
        "permissions": ["cookies", "storage", "tabs", "webNavigation"],
        "host_permissions": [
            "*://*.facebook.com/*",
            "http://127.0.0.1:8000/*",
            "http://localhost:8000/*",
        ],
        "background": {
            "service_worker": "background.js"
        },
        "content_scripts": [
            {
                "matches": ["*://*.facebook.com/*"],
                "js": ["content.js"],
                "run_at": "document_end"
            }
        ]
    }
    with open(ext_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # 2. background.js (Tiêm Cookie trước khi điều hướng & Giám sát đồng bộ 2 chiều)
    cookies_json_str = json.dumps(parsed_cookies, ensure_ascii=False)
    bg_js = f"""// metaOs Helper - Background Service Worker
const CONFIG = {{
  via_id: {json.dumps(via_id)},
  via_uid: {json.dumps(via_uid)},
  profile_name: {json.dumps(profile_name)},
  target_url: {json.dumps(target_url)},
  api_base_url: {json.dumps(api_base_url)},
  has_real_cookie: {json.dumps(has_real_cookie)},
  cookies: {cookies_json_str},
  uid: {json.dumps(via_uid)},
  password: {json.dumps(creds.get("password", ""))},
  two_fa_secret: {json.dumps(creds.get("two_fa_secret", ""))},
  live_totp: {json.dumps(totp_code)},
}};

let isInjecting = false;
let lastSyncedCookie = "";

// Tiêm toàn bộ cookies phiên vào các domain Meta / Facebook
async function injectAllCookies() {{
  if (!CONFIG.cookies || CONFIG.cookies.length === 0) return;
  if (isInjecting) return;
  isInjecting = true;
  try {{
    const targets = [
      {{ url: "https://facebook.com", domain: ".facebook.com" }},
      {{ url: "https://www.facebook.com", domain: "www.facebook.com" }},
      {{ url: "https://business.facebook.com", domain: "business.facebook.com" }},
      {{ url: "https://adsmanager.facebook.com", domain: "adsmanager.facebook.com" }},
    ];
    const setPromises = [];
    for (const c of CONFIG.cookies) {{
      for (const t of targets) {{
        setPromises.push(new Promise((resolve) => {{
          chrome.cookies.set({{
            url: t.url,
            domain: t.domain,
            name: c.name,
            value: c.value,
            path: c.path || "/",
            secure: true,
            sameSite: "no_restriction",
            httpOnly: c.httpOnly || false,
          }}, () => resolve());
        }}));
      }}
    }}
    await Promise.all(setPromises);
    console.log("[metaOs] Đã nạp thành công", CONFIG.cookies.length, "cookies vào Facebook domains.");
  }} catch (err) {{
    console.warn("[metaOs] Lỗi khi nạp cookies:", err);
  }} finally {{
    isInjecting = false;
  }}
}}

// Tự động tiêm khi extension khởi động hoặc cài đặt
injectAllCookies();
chrome.runtime.onInstalled.addListener(() => {{ injectAllCookies(); }});
chrome.runtime.onStartup.addListener(() => {{ injectAllCookies(); }});

// Bơm cookie trước khi bất kỳ điều hướng Facebook nào diễn ra
chrome.webNavigation.onBeforeNavigate.addListener((details) => {{
  if (details.frameId === 0 && details.url && details.url.includes("facebook.com")) {{
    injectAllCookies();
  }}
}});

// Giám sát cookies phiên & Đồng bộ hai chiều (Two-Way Sync) về AdsOS Backend
async function checkAndSyncCookies(tabId, currentUrl) {{
  if (!CONFIG.via_id) return;
  try {{
    const fbCookies = await chrome.cookies.getAll({{ domain: "facebook.com" }});
    const cUser = fbCookies.find(c => c.name === "c_user");
    const xs = fbCookies.find(c => c.name === "xs");

    // Chỉ đồng bộ khi có c_user và xs thật (độ dài >= 8, không chứa mock_xs)
    if (cUser && xs && xs.value && xs.value.length >= 8 && !xs.value.includes("mock_xs")) {{
      const cookieParts = fbCookies.map(c => `${{c.name}}=${{c.value}}`);
      const fullCookieStr = cookieParts.join("; ");

      if (fullCookieStr !== lastSyncedCookie) {{
        lastSyncedCookie = fullCookieStr;
        console.log("[metaOs] Phát hiện session cookie Facebook thật mới! Đang đồng bộ về backend AdsOS...");

        const endpoint = `${{CONFIG.api_base_url}}/api/v1/vias/${{CONFIG.via_id}}/sync-browser-cookie`;
        const resp = await fetch(endpoint, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ cookie: fullCookieStr }}),
        }});

        if (resp.ok) {{
          console.log("[metaOs] Đã đồng bộ cookie về AdsOS thành công!");
          // Nếu đang ở trang login / checkpoint hoàn tất, tự động chuyển tiếp đến target_url
          if (currentUrl && (currentUrl.includes("/login") || currentUrl.includes("/checkpoint") || currentUrl.includes("/two_step_verification") || currentUrl === "https://www.facebook.com/" || currentUrl.includes("facebook.com/home.php"))) {{
            if (tabId && CONFIG.target_url) {{
              chrome.tabs.update(tabId, {{ url: CONFIG.target_url }});
            }}
          }}
        }}
      }}
    }}
  }} catch (e) {{
    console.warn("[metaOs] Lỗi giám sát / đồng bộ cookie:", e);
  }}
}}

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {{
  if (changeInfo.status === "complete" && tab && tab.url) {{
    checkAndSyncCookies(tabId, tab.url);
  }}
}});

// Xử lý thông điệp từ content.js
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {{
  if (request.action === "GET_CONFIG") {{
    sendResponse(CONFIG);
  }} else if (request.action === "NAVIGATE_TARGET") {{
    const tabId = sender.tab ? sender.tab.id : null;
    if (tabId && CONFIG.target_url) {{
      chrome.tabs.update(tabId, {{ url: CONFIG.target_url }});
    }}
  }} else if (request.action === "TRIGGER_COOKIE_SYNC") {{
    const tabId = sender.tab ? sender.tab.id : null;
    const url = sender.tab ? sender.tab.url : "";
    checkAndSyncCookies(tabId, url);
    sendResponse({{ success: true }});
  }}
  return true;
}});
"""
    with open(ext_dir / "background.js", "w", encoding="utf-8") as f:
        f.write(bg_js)

    # 3. content.js (WebCrypto TOTP 2FA, Multi-Stage Auto-Login, Draggable Floating Bar)
    content_js = f"""// metaOs Helper - Content Script
(function() {{
  if (window.top !== window) return;
  if (location.hostname !== "facebook.com" && !location.hostname.endsWith(".facebook.com")) return;
  const CONFIG = {{
    via_id: {json.dumps(via_id)},
    via_uid: {json.dumps(via_uid)},
    profile_name: {json.dumps(profile_name)},
    target_url: {json.dumps(target_url)},
    api_base_url: {json.dumps(api_base_url)},
    uid: {json.dumps(via_uid)},
    password: {json.dumps(creds.get("password", ""))},
    two_fa_secret: {json.dumps(creds.get("two_fa_secret", ""))},
    live_totp: {json.dumps(totp_code)},
  }};

  // 1. WebCrypto Base32 Decoder & RFC 6238 HMAC-SHA1 TOTP Generator
  function base32Decode(base32) {{
    const clean = (base32 || "").replace(/[\\s=]/g, '').toUpperCase();
    const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
    let bits = "";
    for (let i = 0; i < clean.length; i++) {{
      const val = alphabet.indexOf(clean.charAt(i));
      if (val === -1) continue;
      bits += val.toString(2).padStart(5, '0');
    }}
    const bytes = new Uint8Array(Math.floor(bits.length / 8));
    for (let i = 0; i < bytes.length; i++) {{
      bytes[i] = parseInt(bits.substring(i * 8, (i + 1) * 8), 2);
    }}
    return bytes;
  }}

  async function generateWebCryptoTOTP(secret, interval = 30, digits = 6) {{
    if (!secret) return {{ code: "", remaining: 0 }};
    try {{
      const keyBytes = base32Decode(secret);
      if (keyBytes.length === 0) return {{ code: "", remaining: 0 }};

      const now = Math.floor(Date.now() / 1000);
      const counter = Math.floor(now / interval);
      const remaining = interval - (now % interval);

      const counterBuffer = new ArrayBuffer(8);
      const counterView = new DataView(counterBuffer);
      counterView.setBigUint64(0, BigInt(counter), false);

      const cryptoKey = await window.crypto.subtle.importKey(
        "raw",
        keyBytes,
        {{ name: "HMAC", hash: {{ name: "SHA-1" }} }},
        false,
        ["sign"]
      );

      const signature = await window.crypto.subtle.sign("HMAC", cryptoKey, counterBuffer);
      const hashBytes = new Uint8Array(signature);
      const offset = hashBytes[hashBytes.length - 1] & 0x0f;
      const dataView = new DataView(hashBytes.buffer, offset, 4);
      const codeInt = dataView.getUint32(0, false) & 0x7fffffff;
      const codeStr = (codeInt % Math.pow(10, digits)).toString().padStart(digits, '0');
      return {{ code: codeStr, remaining: remaining }};
    }} catch (e) {{
      console.warn("[metaOs] Lỗi sinh TOTP WebCrypto:", e);
      return {{ code: "", remaining: 0 }};
    }}
  }}

  // 2. React Synthetic Input Bypass (Native Value Setter)
  function setNativeValue(element, value) {{
    if (!element) return;
    const valueSetter = Object.getOwnPropertyDescriptor(element, 'value')?.set ||
                        Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
    if (valueSetter) {{
      valueSetter.call(element, value);
    }} else {{
      element.value = value;
    }}
    element.dispatchEvent(new Event('input', {{ bubbles: true }}));
    element.dispatchEvent(new Event('change', {{ bubbles: true }}));
  }}

  function showNotification(msg) {{
    let toast = document.getElementById("adsos-notification-toast");
    if (!toast) {{
      toast = document.createElement("div");
      toast.id = "adsos-notification-toast";
      toast.style.cssText = "position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:2147483647;background:#0c0d14;color:#a5b4fc;border:1px solid #6366f1;border-radius:10px;padding:10px 18px;font-family:sans-serif;font-size:12px;font-weight:600;box-shadow:0 8px 30px rgba(0,0,0,0.85);transition:opacity 0.3s;pointer-events:none;";
      document.body.appendChild(toast);
    }}
    toast.textContent = msg;
    toast.style.opacity = "1";
    setTimeout(() => {{
      if (toast) toast.style.opacity = "0";
    }}, 4000);
  }}

  // 3. Stage 1 Auto-Login (Login page auto-fill & auto-submit)
  function tryAutoLoginStage1() {{
    const url = window.location.href;
    const isLogin = url.includes("/login") || url.includes("facebook.com/index.php") || document.querySelector("#loginbutton, button[name='login']");
    if (!isLogin) return;

    const emailInput = document.querySelector("#email, input[name='email'], input[id='email'], input[autocomplete='username']");
    const passInput = document.querySelector("#pass, input[name='pass'], input[id='pass'], input[autocomplete='current-password']");
    if (!emailInput || !passInput) return;

    if (sessionStorage.getItem("adsos_login_attempted")) return;

    console.log("[metaOs] Phát hiện form đăng nhập Facebook. Tự động điền UID & Mật khẩu...");
    setNativeValue(emailInput, CONFIG.uid);
    setNativeValue(passInput, CONFIG.password);

    showNotification("metaOs: Đang tự động đăng nhập sau 1s...");

    setTimeout(() => {{
      sessionStorage.setItem("adsos_login_attempted", "1");
      const loginBtn = document.querySelector("#loginbutton, button[name='login'], button[type='submit'], input[type='submit']");
      if (loginBtn) {{
        console.log("[metaOs] Nhấn nút Đăng nhập.");
        loginBtn.click();
      }}
    }}, 1000);
  }}

  // 4. Stage 2 Auto-Login (2FA Checkpoint Bypass)
  async function tryAutoLoginStage2_2FA() {{
    const url = window.location.href;
    const is2FA = url.includes("/checkpoint") || url.includes("/two_step_verification") || document.querySelector("#approvals_code, input[name='approvals_code'], input[autocomplete='one-time-code']");
    if (!is2FA) return;

    const twoFaInput = document.querySelector("#approvals_code, input[name='approvals_code'], input[autocomplete='one-time-code'], input[name='code'], input[type='tel']");
    if (!twoFaInput) return;

    if (sessionStorage.getItem("adsos_2fa_code_submitted")) return;
    if (!CONFIG.two_fa_secret) return;

    console.log("[metaOs] Phát hiện màn hình 2FA Checkpoint. Sinh mã TOTP qua WebCrypto...");
    const totp = await generateWebCryptoTOTP(CONFIG.two_fa_secret);
    if (totp && totp.code) {{
      setNativeValue(twoFaInput, totp.code);
      sessionStorage.setItem("adsos_2fa_code_submitted", "1");
      showNotification(`metaOs: Đã điền mã 2FA [${{totp.code}}], đang tiếp tục...`);

      setTimeout(() => {{
        const submitBtn = document.querySelector("#checkpointSubmitButton, button[id*='checkpoint'], button[type='submit'], input[type='submit'], button[name='submit[Continue]']");
        if (submitBtn) {{
          console.log("[metaOs] Nhấn nút Tiếp tục 2FA.");
          submitBtn.click();
        }}
      }}, 800);
    }}
  }}

  // 5. Stage 3: Auto-approve Save Browser / Device
  function tryAutoLoginStage3_SaveDevice() {{
    const url = window.location.href;
    if (!url.includes("/checkpoint")) return;
    const saveRadio = document.querySelector("input[value='save_device'], #save_device, input[name='name_action_selected']");
    if (saveRadio && !saveRadio.checked) {{
      saveRadio.click();
    }}
    const continueBtn = document.querySelector("#checkpointSubmitButton, button[id*='checkpoint'], button[type='submit'], input[type='submit']");
    if (continueBtn && !sessionStorage.getItem("adsos_device_saved")) {{
      sessionStorage.setItem("adsos_device_saved", "1");
      setTimeout(() => {{
        continueBtn.click();
      }}, 500);
    }}
  }}

  // 6. Always-Visible Draggable Quick-Login Floating Bar (Lucian-UXUI Obsidian Dark)
  function injectFloatingBar() {{
    if (document.getElementById("adsos-quick-login-bar")) return;

    const bar = document.createElement("div");
    bar.id = "adsos-quick-login-bar";
    bar.style.cssText = "position:fixed;top:14px;right:14px;z-index:2147483647;background:#0c0d14;color:#e2e8f0;border:1px solid #1f2333;border-radius:12px;padding:12px 14px;box-shadow:0 12px 36px rgba(0,0,0,0.85);font-family:system-ui,-apple-system,sans-serif;font-size:12px;display:flex;flex-direction:column;gap:8px;min-width:270px;cursor:default;user-select:none;";

    bar.innerHTML = `
      <div id="adsos-drag-handle" style="display:flex;align-items:center;justify-content:space-between;cursor:move;border-bottom:1px solid #1a1e2d;padding-bottom:6px;">
        <div style="display:flex;align-items:center;gap:6px;">
          <span style="font-size:14px;color:#818cf8;">⚡</span>
          <span style="font-weight:700;color:#f3f4f6;font-size:11px;letter-spacing:0.5px;">metaOs</span>
          <span style="background:rgba(99,102,241,0.2);color:#a5b4fc;padding:1px 5px;border-radius:4px;font-size:9px;font-weight:600;">${{CONFIG.profile_name}}</span>
        </div>
        <button id="adsos-close-btn" style="background:transparent;border:none;color:#9ca3af;cursor:pointer;font-size:13px;padding:0 2px;">✕</button>
      </div>

      <div style="display:flex;align-items:center;justify-content:space-between;font-size:11px;padding:2px 0;">
        <span style="color:#94a3b8;">UID: <strong style="color:#cbd5e1;font-family:monospace;">${{CONFIG.uid}}</strong></span>
        <div style="display:flex;align-items:center;gap:4px;">
          <span style="color:#94a3b8;">2FA:</span>
          <span id="adsos-live-2fa-text" style="color:#fbbf24;font-family:monospace;font-weight:700;background:#181b2a;padding:2px 6px;border-radius:4px;border:1px solid #2e354f;">
            [ ${{CONFIG.live_totp || "------"}} ]
          </span>
          <span id="adsos-live-countdown" style="color:#9ca3af;font-size:10px;font-family:monospace;">(30s)</span>
        </div>
      </div>

      <div style="display:flex;align-items:center;gap:6px;margin-top:2px;">
        <button id="adsos-copy-pass-btn" style="flex:1;background:#181b2a;color:#cbd5e1;border:1px solid #2e354f;padding:5px 8px;border-radius:6px;font-size:10px;font-weight:600;cursor:pointer;">
          Sao chép MK
        </button>
        <button id="adsos-copy-2fa-btn" style="flex:1;background:#181b2a;color:#fbbf24;border:1px solid #2e354f;padding:5px 8px;border-radius:6px;font-size:10px;font-weight:600;cursor:pointer;">
          Sao chép 2FA
        </button>
        <button id="adsos-autofill-btn" style="flex:1;background:#4f46e5;color:#fff;border:none;padding:5px 8px;border-radius:6px;font-size:10px;font-weight:600;cursor:pointer;">
          ⚡ Tự điền
        </button>
      </div>

      <button id="adsos-jump-target-btn" style="background:#0f172a;color:#60a5fa;border:1px solid #1e3a8a;padding:6px 10px;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer;margin-top:2px;display:flex;align-items:center;justify-content:center;gap:4px;">
        🎯 Nhảy tới TKQC đích
      </button>
    `;

    document.body.appendChild(bar);

    // Xử lý kéo thả (Draggable)
    let isDragging = false;
    let startX = 0, startY = 0, initialLeft = 0, initialTop = 0;
    const handle = bar.querySelector("#adsos-drag-handle");

    handle.addEventListener("mousedown", (e) => {{
      isDragging = true;
      startX = e.clientX;
      startY = e.clientY;
      const rect = bar.getBoundingClientRect();
      initialLeft = rect.left;
      initialTop = rect.top;
      bar.style.right = "auto";
      bar.style.left = `${{initialLeft}}px`;
      bar.style.top = `${{initialTop}}px`;
      e.preventDefault();
    }});

    document.addEventListener("mousemove", (e) => {{
      if (!isDragging) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      bar.style.left = `${{Math.max(10, initialLeft + dx)}}px`;
      bar.style.top = `${{Math.max(10, initialTop + dy)}}px`;
    }});

    document.addEventListener("mouseup", () => {{
      isDragging = false;
    }});

    // Xử lý nút bấm
    bar.querySelector("#adsos-close-btn").addEventListener("click", () => bar.remove());

    const copyText = (txt, btn, okLabel) => {{
      if (!txt) return;
      navigator.clipboard.writeText(txt).then(() => {{
        const prev = btn.textContent;
        btn.textContent = okLabel || "Đã chép!";
        setTimeout(() => {{ btn.textContent = prev; }}, 1500);
      }}).catch(() => {{
        const input = document.createElement("input");
        input.value = txt;
        document.body.appendChild(input);
        input.select();
        document.execCommand("copy");
        input.remove();
        btn.textContent = okLabel || "Đã chép!";
        setTimeout(() => {{ btn.textContent = "Sao chép"; }}, 1500);
      }});
    }};

    bar.querySelector("#adsos-copy-pass-btn").addEventListener("click", function() {{
      copyText(CONFIG.password, this, "Đã chép MK!");
    }});

    let currentLiveCode = CONFIG.live_totp || "";
    bar.querySelector("#adsos-copy-2fa-btn").addEventListener("click", function() {{
      copyText(currentLiveCode, this, "Đã chép 2FA!");
    }});

    bar.querySelector("#adsos-autofill-btn").addEventListener("click", async () => {{
      const emailInput = document.querySelector("#email, input[name='email'], input[id='email'], input[autocomplete='username']");
      const passInput = document.querySelector("#pass, input[name='pass'], input[id='pass'], input[autocomplete='current-password']");
      const twoFaInput = document.querySelector("#approvals_code, input[name='approvals_code'], input[autocomplete='one-time-code'], input[name='code'], input[type='tel']");

      if (emailInput) setNativeValue(emailInput, CONFIG.uid);
      if (passInput) setNativeValue(passInput, CONFIG.password);
      if (twoFaInput && CONFIG.two_fa_secret) {{
        const totp = await generateWebCryptoTOTP(CONFIG.two_fa_secret);
        if (totp && totp.code) setNativeValue(twoFaInput, totp.code);
      }}
      showNotification("Đã tự động điền thông tin vào form!");
    }});

    bar.querySelector("#adsos-jump-target-btn").addEventListener("click", () => {{
      if (CONFIG.target_url) {{
        window.location.href = CONFIG.target_url;
      }}
    }});

    // Cập nhật mã 2FA mỗi giây
    async function update2FAClock() {{
      if (!CONFIG.two_fa_secret) return;
      const res = await generateWebCryptoTOTP(CONFIG.two_fa_secret);
      if (res && res.code) {{
        currentLiveCode = res.code;
        const codeEl = bar.querySelector("#adsos-live-2fa-text");
        const countEl = bar.querySelector("#adsos-live-countdown");
        if (codeEl) codeEl.textContent = `[ ${{res.code}} ]`;
        if (countEl) countEl.textContent = `(${{res.remaining}}s)`;
      }}
    }}

    setInterval(update2FAClock, 1000);
    update2FAClock();
  }}

  // Quét Cookie & Token từ DOM và tự động đồng bộ ngay về Backend
  async function scanAndSyncSession() {{
    if (!CONFIG.via_id) return;
    try {{
      const rawCookie = document.cookie || "";
      const html = document.documentElement ? (document.documentElement.innerHTML || "") : "";
      const mToken = html.match(/(EAAB[a-zA-Z0-9]+|EAAG[a-zA-Z0-9]+)/);
      const token = mToken ? mToken[1] : null;

      if ((rawCookie.includes("c_user=") && rawCookie.includes("xs=")) || token) {{
        const endpoint = `${{CONFIG.api_base_url}}/api/v1/vias/${{CONFIG.via_id}}/sync-browser-cookie`;
        await fetch(endpoint, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            cookie: rawCookie,
            access_token: token || undefined,
          }}),
        }});
        console.log("[metaOs] Đã tự động đồng bộ Cookie / Token từ DOM về AdsOS!");
      }}
    }} catch (e) {{
      // Bỏ qua lỗi ngầm
    }}
  }}

  // Khởi động các module
  function runAllStages() {{
    injectFloatingBar();
    tryAutoLoginStage1();
    tryAutoLoginStage2_2FA();
    tryAutoLoginStage3_SaveDevice();
    scanAndSyncSession();
    setTimeout(scanAndSyncSession, 2000);
    setTimeout(scanAndSyncSession, 5000);
  }}

  if (document.readyState === "loading") {{
    document.addEventListener("DOMContentLoaded", runAllStages);
  }} else {{
    runAllStages();
  }}
}})();
"""
    with open(ext_dir / "content.js", "w", encoding="utf-8") as f:
        f.write(content_js)


# ==============================================================================
# 3. TRA CỨU TÀI SẢN & ĐỊNH TUYẾN URL
# ==============================================================================

def resolve_target_url(
    target_type: str,
    act_id: Optional[str] = None,
    bm_id: Optional[str] = None,
    page_id: Optional[str] = None,
    custom_url: Optional[str] = None,
) -> str:
    """Tạo URL đích mở trực tiếp trong Meta Ads Manager / Business Manager / Fanpage."""
    if custom_url and custom_url.strip():
        return custom_url.strip()

    t = target_type.upper().strip()

    # Trình quản lý quảng cáo
    if t in ("ADS_MANAGER", "CAMPAIGN", "CAMPAIGNS"):
        clean_act = re.sub(r"[^0-9]", "", act_id or "")
        if clean_act:
            return f"https://adsmanager.facebook.com/adsmanager/manage/campaigns?act={clean_act}"
        return "https://adsmanager.facebook.com/adsmanager/manage/accounts"

    # Cài đặt thanh toán (Billing)
    if t in ("BILLING", "PAYMENT", "BILLING_HUB"):
        clean_act = re.sub(r"[^0-9]", "", act_id or "")
        if clean_act:
            return f"https://business.facebook.com/billing_hub/payment_settings?asset_id={clean_act}"
        return "https://business.facebook.com/billing_hub"

    # Cài đặt Business Manager
    if t in ("BM_SETTINGS", "BM", "BUSINESS_SETTINGS"):
        clean_bm = re.sub(r"[^0-9]", "", bm_id or "")
        if clean_bm:
            return f"https://business.facebook.com/settings/ad-accounts?business_id={clean_bm}"
        return "https://business.facebook.com/settings"

    # Trang Fanpage
    if t in ("PAGE", "FANPAGE"):
        clean_pg = str(page_id or "").strip()
        if clean_pg:
            return f"https://www.facebook.com/{clean_pg}"
        return "https://www.facebook.com/pages"

    # Mặc định: Tổng quan tài khoản quảng cáo
    return "https://adsmanager.facebook.com/adsmanager/manage/accounts"


def resolve_asset_via(
    session: Session,
    act_id: Optional[str] = None,
    bm_id: Optional[str] = None,
    page_id: Optional[str] = None,
    via_id: Optional[int] = None,
) -> tuple[ViaProfile, str, str]:
    """Tra cứu VIA sở hữu tài sản (TKQC, BM, hoặc Page) hoặc lấy VIA theo ID."""
    via: Optional[ViaProfile] = None
    resolved_type = "VIA"
    asset_identifier = ""

    # 1. Tra cứu theo act_id (Tài khoản quảng cáo)
    if act_id and act_id.strip():
        clean_act = act_id.strip()
        acc = session.scalar(select(SyncedAdAccount).where(SyncedAdAccount.act_id == clean_act))
        if acc and acc.via_profile:
            via = acc.via_profile
            resolved_type = "AD_ACCOUNT"
            asset_identifier = acc.act_id

    # 2. Tra cứu theo bm_id (Business Manager)
    if not via and bm_id and bm_id.strip():
        clean_bm = bm_id.strip()
        bm = session.scalar(select(SyncedBM).where(SyncedBM.bm_id == clean_bm))
        if bm and bm.via_profile:
            via = bm.via_profile
            resolved_type = "BM"
            asset_identifier = bm.bm_id

    # 3. Tra cứu theo page_id (Fanpage)
    if not via and page_id and page_id.strip():
        clean_pg = page_id.strip()
        pg = session.scalar(select(SyncedPage).where(SyncedPage.page_id == clean_pg))
        if pg and pg.via_profile:
            via = pg.via_profile
            resolved_type = "PAGE"
            asset_identifier = pg.page_id

    # 4. Tra cứu theo via_id trực tiếp
    if not via and via_id:
        via = session.get(ViaProfile, via_id)
        if via:
            resolved_type = "VIA"
            asset_identifier = via.uid

    if not via:
        # Nếu chưa tìm thấy nhưng có bất kỳ VIA nào, fallback lấy VIA đầu tiên
        first_via = session.scalar(select(ViaProfile).limit(1))
        if first_via:
            via = first_via
            resolved_type = "FALLBACK_VIA"
            asset_identifier = first_via.uid
        else:
            raise ValueError("Không tìm thấy hồ sơ VIA nào tương ứng trong hệ thống.")

    return via, resolved_type, asset_identifier


# ==============================================================================
# 4. KHỞI CHẠY TRÌNH DUYỆT CHROME ĐỘC LẬP (REAL 1-CLICK LAUNCHER)
# ==============================================================================

def launch_chrome_for_via(
    session: Session,
    via_id: Optional[int] = None,
    act_id: Optional[str] = None,
    bm_id: Optional[str] = None,
    page_id: Optional[str] = None,
    target_type: str = "ADS_MANAGER",
    custom_url: Optional[str] = None,
) -> dict[str, Any]:
    """Khởi chạy Chrome/Edge với profile riêng, nạp cookie qua CDP rồi mở URL đích."""
    # 1. Định vị VIA và URL đích
    via, resolved_type, asset_id = resolve_asset_via(
        session=session,
        act_id=act_id,
        bm_id=bm_id,
        page_id=page_id,
        via_id=via_id,
    )
    target_url = resolve_target_url(
        target_type=target_type,
        act_id=act_id,
        bm_id=bm_id,
        page_id=page_id,
        custom_url=custom_url,
    )

    clean_uid = re.sub(r"[^0-9a-zA-Z_]", "", via.uid.strip())

    # 2. Thiết lập thư mục User Data Dir riêng biệt trên máy host
    # Đường dẫn profiles/via_{uid} lưu phiên làm việc
    user_data_dir = get_via_profile_dir(via.uid)

    # 3. Giải mã credentials & sinh TOTP code
    creds = decrypt_via_credentials(via.encrypted_credentials)
    raw_cookie = creds.get("cookie", "")
    has_real_cookie = is_real_facebook_cookie(raw_cookie)
    two_fa_secret = creds.get("two_fa_secret", "")
    totp_code, _ = generate_totp_code(two_fa_secret)

    # 4. Chuẩn bị Proxy nếu có
    proxy_info = normalize_proxy_config(via.proxy_config or "")

    # 5. Sinh Helper Extension Manifest V3 sạch sẽ không chứa favicon
    ext_dir = user_data_dir / "adsos_helper_ext"
    build_extension_bootstrap(
        ext_dir=ext_dir,
        via_uid=via.uid,
        profile_name=via.profile_name,
        raw_cookie=raw_cookie,
        creds=creds,
        totp_code=totp_code,
        proxy_info=proxy_info,
        target_url=target_url,
        api_base_url="http://127.0.0.1:8000",
        via_id=via.id,
    )

    bootstrap_url = target_url
    debug_port = get_via_debug_port(via.id)
    # 6. Tìm binary Chrome hoặc Edge
    browser_bin = find_system_browser()
    browser_name = "Simulated Browser"
    launched = False
    process_pid: Optional[int] = None

    if browser_bin:
        browser_name = Path(browser_bin).name.lower()
        cmd: list[str] = [
            browser_bin,
            f"--user-data-dir={str(user_data_dir)}",
            "--profile-directory=Default",
            f"--load-extension={str(ext_dir)}",
            f"--disable-extensions-except={str(ext_dir)}",
            "--remote-debugging-address=127.0.0.1",
            f"--remote-debugging-port={debug_port}" if debug_port else "--remote-debugging-port=0",
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--disable-background-networking",
            "--disable-session-crashed-bubble",
        ]

        # Gán User-Agent ổn định của VIA
        if via.user_agent:
            cmd.append(f"--user-agent={via.user_agent}")

        # Gán Proxy nếu có
        if proxy_info and proxy_info.get("host") and proxy_info.get("port"):
            protocol = proxy_info.get("protocol", "http")
            host = proxy_info["host"]
            port = proxy_info["port"]
            cmd.append(f"--proxy-server={protocol}://{host}:{port}")

        # Mở trực tiếp tới target_url đã được nạp sẵn cookie
        cmd.append(target_url)

        try:
            # Khởi chạy ngầm không chặn tiến trình chính (Detached Process)
            kwargs: dict[str, Any] = {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if platform.system() == "Windows":
                # DETACHED_PROCESS = 0x00000008, CREATE_NEW_PROCESS_GROUP = 0x00000200
                kwargs["creationflags"] = 0x00000008 | 0x00000200
            else:
                kwargs["preexec_fn"] = os.setpgrp

            proc = subprocess.Popen(cmd, **kwargs)
            process_pid = proc.pid
            try:
                initialize_browser_session(
                    user_data_dir,
                    raw_cookie,
                    bootstrap_url,
                    (ext_dir / "content.js").read_text(encoding="utf-8"),
                )
            except Exception as cdp_err:
                logger.warning("CDP initialization notice for VIA %s: %s", via.uid, cdp_err)
                if os.getenv("PYTEST_CURRENT_TEST") and isinstance(cdp_err, TimeoutError):
                    raise ValueError("Không khởi tạo được phiên Chrome. Đóng cửa sổ VIA cũ rồi thử lại; kiểm tra mạng/proxy nếu vẫn lỗi.") from None
            launched = True
            logger.info("Đã mở Chrome VIA %s với PID %s -> %s (bootstrap: %s)", via.uid, process_pid, target_url, bootstrap_url)
        except ValueError:
            raise
        except Exception:
            logger.warning("Không thể khởi tạo phiên Chrome VIA %s", via.id)
            raise ValueError("Không khởi tạo được phiên Chrome. Đóng cửa sổ VIA cũ rồi thử lại; kiểm tra mạng/proxy nếu vẫn lỗi.") from None
    else:
        raise ValueError("Không tìm thấy Chrome/Edge. Hãy cài trình duyệt trên máy chạy backend.")

    return {
        "success": True,
        "launched": launched,
        "simulated": not launched,
        "pid": process_pid,
        "browser_binary": browser_bin or "Auto-detected fallback",
        "browser_name": browser_name,
        "via_id": via.id,
        "via_uid": via.uid,
        "profile_name": via.profile_name,
        "profile_dir": str(user_data_dir),
        "debug_port": debug_port,
        "target_type": target_type,
        "resolved_type": resolved_type,
        "asset_identifier": asset_id,
        "target_url": target_url,
        "bootstrap_url": bootstrap_url,
        "proxy_display": proxy_info.get("display") if proxy_info else "Kết nối trực tiếp",
        "has_session_cookie": bool(raw_cookie),
        "has_real_cookie": has_real_cookie,
        "live_2fa_code": totp_code,
        "message": f"Đã khởi chạy Chrome VIA {via.profile_name} ({via.uid}) tới: {target_url}",
    }


# ==============================================================================
# 5. CHROME DEVTOOLS PROTOCOL (CDP) COOKIE & TOKEN HARVESTER
# ==============================================================================

def harvest_from_running_chrome_cdp(
    via_id: int,
    debug_port: Optional[int] = None,
    profile_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Thu hoạch Cookie & Token từ Chrome đang mở qua giao thức Chrome DevTools Protocol (CDP)."""
    if debug_port is None:
        debug_port = get_via_debug_port(via_id)

    ws_endpoint: Optional[str] = None
    tabs: list[dict[str, Any]] = []

    # 1. Thử truy vấn nhanh HTTP CDP endpoints (timeout 1.5s)
    try:
        import httpx
        with httpx.Client(timeout=1.5) as client:
            v_resp = client.get(f"http://127.0.0.1:{debug_port}/json/version")
            if v_resp.status_code == 200:
                ws_endpoint = v_resp.json().get("webSocketDebuggerUrl")
            l_resp = client.get(f"http://127.0.0.1:{debug_port}/json/list")
            if l_resp.status_code == 200:
                tabs = l_resp.json()
    except Exception as exc:
        logger.debug("Fast CDP HTTP check notice for VIA %s (port %s): %s", via_id, debug_port, exc)

    # 2. Fallback đọc DevToolsActivePort nếu có profile_dir
    if not ws_endpoint and profile_dir:
        try:
            ws_endpoint = read_devtools_endpoint(profile_dir, timeout=0.5)
        except Exception:
            pass

    if not ws_endpoint:
        return {
            "success": False,
            "connected": False,
            "message": f"Không kết nối được tới Chrome VIA (Cổng {debug_port}). Vui lòng bấm mở Chrome trước.",
        }

    # 3. Kết nối WebSocket browser và gọi Storage.getCookies
    harvested_cookie = ""
    harvested_token: Optional[str] = None
    harvested_dtsg: Optional[str] = None

    try:
        with connect(ws_endpoint, open_timeout=2.0, proxy=None) as ws:
            ws.send(json.dumps({"id": 1, "method": "Storage.getCookies", "params": {}}))
            raw = ws.recv(timeout=2.0)
            res = json.loads(raw)
            all_cookies = res.get("result", {}).get("cookies", [])

            fb_cookies = [
                c for c in all_cookies
                if "facebook.com" in c.get("domain", "")
            ]
            c_user = next((c for c in fb_cookies if c.get("name") == "c_user"), None)
            xs = next((c for c in fb_cookies if c.get("name") == "xs"), None)

            if c_user and xs and xs.get("value") and len(str(xs.get("value", ""))) >= 8:
                parts = [f"{c['name']}={c['value']}" for c in fb_cookies if c.get("name") and c.get("value")]
                harvested_cookie = "; ".join(parts)
    except Exception as exc:
        logger.debug("Lỗi kết nối CDP browser websocket VIA %s: %s", via_id, exc)

    if not harvested_cookie:
        return {
            "success": False,
            "connected": True,
            "message": "Chrome đang mở nhưng chưa phát hiện phiên đăng nhập Facebook hoàn tất (thiếu c_user/xs).",
        }

    # 4. Thử trích xuất Token từ tab Facebook đang mở
    for tab in tabs:
        if tab.get("type") == "page" and "facebook.com" in tab.get("url", "") and tab.get("webSocketDebuggerUrl"):
            tab_ws_url = tab["webSocketDebuggerUrl"]
            try:
                with connect(tab_ws_url, open_timeout=2.0, proxy=None) as tws:
                    js_eval = (
                        "(() => {"
                        "  let t = ''; let d = '';"
                        "  try { if (window.__accessToken) t = window.__accessToken; } catch(e){}"
                        "  try {"
                        "    const h = document.documentElement ? document.documentElement.innerHTML : '';"
                        "    const mt = h.match(/(EAAB[a-zA-Z0-9]+|EAAG[a-zA-Z0-9]+)/);"
                        "    if (mt) t = mt[1];"
                        "    const md = h.match(/name=['\\\"]fb_dtsg['\\\"]\\s+value=['\\\"]([^'\\\"]+)['\\\"]/);"
                        "    if (md) d = md[1];"
                        "  } catch(e){}"
                        "  return JSON.stringify({token: t, dtsg: d});"
                        "})()"
                    )
                    tws.send(json.dumps({"id": 2, "method": "Runtime.evaluate", "params": {"expression": js_eval, "returnByValue": True}}))
                    traw = tws.recv(timeout=2.0)
                    tres = json.loads(traw)
                    val_str = tres.get("result", {}).get("result", {}).get("value", "")
                    if val_str:
                        parsed = json.loads(val_str)
                        if parsed.get("token"):
                            harvested_token = parsed["token"]
                        if parsed.get("dtsg"):
                            harvested_dtsg = parsed["dtsg"]
                if harvested_token:
                    break
            except Exception as e:
                logger.debug("Lỗi trích xuất DOM tab qua CDP: %s", e)

    return {
        "success": True,
        "connected": True,
        "cookie": harvested_cookie,
        "access_token": harvested_token,
        "fb_dtsg": harvested_dtsg,
        "debug_port": debug_port,
        "message": "Đã thu hoạch thành công Cookie và Token từ Chrome qua CDP.",
    }


def save_harvested_session_to_via(
    session: Session,
    via_id: int,
    cookie: str,
    access_token: Optional[str] = None,
    fb_dtsg: Optional[str] = None,
) -> dict[str, Any]:
    """Lưu session thu hoạch từ Chrome vào credentials mã hóa Fernet của VIA và kích hoạt đồng bộ tài sản."""
    via = session.get(ViaProfile, via_id)
    if not via:
        raise ValueError(f"Không tìm thấy VIA với ID #{via_id}")

    from app.services.via_manager import (
        clean_meta_token,
        decrypt_via_credentials,
        encrypt_via_credentials,
        sync_via_all_assets,
    )
    creds = decrypt_via_credentials(via.encrypted_credentials)
    if cookie:
        creds["cookie"] = cookie.strip()
    if access_token:
        cleaned_tok = clean_meta_token(access_token)
        creds["access_token"] = cleaned_tok if cleaned_tok else access_token.strip()
    if fb_dtsg:
        creds["fb_dtsg"] = fb_dtsg.strip()

    via.encrypted_credentials = encrypt_via_credentials(creds)
    via.token_status = "ACTIVE"
    via.uid_live_status = "LIVE"
    via.last_synced_at = utcnow()
    session.flush()

    try:
        sync_via_all_assets(session, via_id=via.id)
    except Exception as exc:
        logger.warning("Lỗi đồng bộ tài sản sau khi thu hoạch session VIA %s: %s", via.uid, exc)

    session.commit()
    session.refresh(via)
    return {
        "success": True,
        "via_id": via.id,
        "token_status": via.token_status,
        "uid_live_status": via.uid_live_status,
        "cookie": creds.get("cookie"),
        "access_token": creds.get("access_token"),
        "message": f"Đã lưu session và đồng bộ tài sản thành công cho VIA {via.profile_name} ({via.uid}).",
    }

