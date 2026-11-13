"""Dịch vụ tự động phân tích VIA thô (Raw Line), sinh mã 2FA TOTP (RFC 6238),
đăng nhập tự động & trích xuất Session Cookie/Token (EAAG/EAAB/fb_dtsg),
kèm quét sâu tài sản quảng cáo (Deep Asset Sync).
"""

from __future__ import annotations

import base64
import email
import hashlib
import hmac
import imaplib
import logging
import re
import struct
import time
from typing import Any, Optional

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.via import SyncedAdAccount, SyncedBM, SyncedPage, ViaProfile
from app.services.via_manager import (
    clean_meta_token,
    decrypt_via_credentials,
    encrypt_via_credentials,
    sync_via_all_assets,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. LIVE 2FA TOTP GENERATOR (RFC 6238 HMAC-SHA1)
# ==============================================================================

def generate_totp_code(secret: str, interval: int = 30, digits: int = 6) -> tuple[str, int]:
    """Tạo mã xác thực 2 bước 6 số từ khóa 2FA Base32 theo chuẩn RFC 6238 và trả về (code, remaining_seconds).
    Hoàn toàn bằng thư viện chuẩn Python (zero external dependencies).
    """
    if not secret:
        return "", 0
    clean_secret = secret.replace(" ", "").strip().upper()
    missing_padding = len(clean_secret) % 8
    if missing_padding != 0:
        clean_secret += "=" * (8 - missing_padding)

    try:
        key = base64.b32decode(clean_secret, casefold=True)
    except Exception as exc:
        logger.debug("Lỗi giải mã base32 của 2FA secret '%s': %s", secret, exc)
        return "", 0

    now = int(time.time())
    counter = now // interval
    remaining_seconds = interval - (now % interval)
    counter_bytes = struct.pack(">Q", counter)

    mac = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code_int = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    code = str(code_int % (10**digits)).zfill(digits)
    return code, remaining_seconds


# ==============================================================================
# 2. PARSER DÒNG NGUYÊN LIỆU VIA THÔ (RAW LINE PARSER)
# ==============================================================================

def parse_via_raw_line(line: str) -> Optional[dict[str, Any]]:
    """Phân tích 1 dòng nguyên liệu VIA theo định dạng tiêu chuẩn:
    uid|pass|2fa|mail|passmail|mailbackup|passmailbackup (|cookie|token tùy chọn)
    
    Hỗ trợ linh hoạt:
    - 2 đến 7+ trường phân cách bằng dấu pipe (|).
    - Tự động khử khoảng trắng trong 2FA secret.
    - Nhận diện thông minh Cookie (c_user/xs/datr) và Token EAAG/EAAB/EAA bất kể vị trí.
    - Trả về mã OTP 6 số thời gian thực nếu có mã 2FA.
    """
    clean_line = (line or "").strip()
    if not clean_line or clean_line.startswith("#") or clean_line.startswith("//"):
        return None

    parts = [p.strip() for p in clean_line.split("|")]
    if len(parts) < 2:
        return None

    uid = parts[0]
    password = parts[1]

    two_fa_secret = ""
    mail = ""
    passmail = ""
    mailbackup = ""
    passmailbackup = ""
    cookie = ""
    eaag_token = ""
    eaab_token = ""
    access_token = ""

    # Quét nhận diện cookie và token trước
    remaining_tokens: list[str] = []
    for p in parts[2:]:
        if not p:
            continue
        # Nhận diện Cookie chuỗi (c_user=... xs=...)
        if ("c_user=" in p or "xs=" in p or "datr=" in p) and not cookie:
            cookie = p
            continue
        # Nhận diện Token EAAG
        if p.startswith("EAAG") and not eaag_token:
            eaag_token = clean_meta_token(p)
            if not access_token:
                access_token = eaag_token
            continue
        # Nhận diện Token EAAB
        if p.startswith("EAAB") and not eaab_token:
            eaab_token = clean_meta_token(p)
            if not access_token:
                access_token = eaab_token
            continue
        # Nhận diện Token Meta khác
        if p.startswith("EAA") and not access_token:
            access_token = clean_meta_token(p)
            continue
        remaining_tokens.append(p)

    # Phân bổ tuần tự các trường còn lại: 2FA, mail, passmail, mailbackup, passmailbackup
    idx = 0
    if idx < len(remaining_tokens):
        item = remaining_tokens[idx]
        # Nếu không chứa @ và có dạng mã 2FA (hoặc vị trí thứ 3 theo chuẩn)
        if "@" not in item:
            two_fa_secret = item.replace(" ", "").upper()
            idx += 1

    if idx < len(remaining_tokens):
        item = remaining_tokens[idx]
        if "@" in item:
            mail = item
            idx += 1
        elif not two_fa_secret:
            two_fa_secret = item.replace(" ", "").upper()
            idx += 1

    if idx < len(remaining_tokens):
        item = remaining_tokens[idx]
        if mail and not passmail and "@" not in item:
            passmail = item
            idx += 1

    if idx < len(remaining_tokens):
        item = remaining_tokens[idx]
        if "@" in item:
            mailbackup = item
            idx += 1
        elif not passmail:
            passmail = item
            idx += 1

    if idx < len(remaining_tokens):
        item = remaining_tokens[idx]
        if mailbackup and not passmailbackup and "@" not in item:
            passmailbackup = item
            idx += 1
        elif "@" in item and not mailbackup:
            mailbackup = item
            idx += 1

    if idx < len(remaining_tokens) and mailbackup and not passmailbackup:
        passmailbackup = remaining_tokens[idx]
        idx += 1

    totp_code, rem_secs = generate_totp_code(two_fa_secret) if two_fa_secret else ("", 0)

    return {
        "uid": uid,
        "fb_uid": uid,
        "password": password,
        "fb_password": password,
        "two_fa_secret": two_fa_secret,
        "email": mail,
        "email_password": passmail,
        "backup_email": mailbackup,
        "backup_email_password": passmailbackup,
        "raw_line": clean_line,
        "cookie": cookie,
        "eaag_token": eaag_token,
        "eaab_token": eaab_token,
        "access_token": access_token or eaag_token or eaab_token,
        "fb_dtsg": "",
        "totp_code": totp_code,
        "remaining_seconds": rem_secs,
    }


def parse_bulk_raw_vias(raw_text: str) -> list[dict[str, Any]]:
    """Phân tích văn bản chứa nhiều dòng VIA (từ 1 đến hàng trăm tài khoản)."""
    results: list[dict[str, Any]] = []
    lines = (raw_text or "").splitlines()
    for line in lines:
        parsed = parse_via_raw_line(line)
        if parsed and parsed.get("uid"):
            results.append(parsed)
    return results


# ==============================================================================
# 3. IMAP SECURITY OTP RETRIEVAL (TỰ ĐỘNG ĐỌC MÃ FACEBOOK TỪ EMAIL)
# ==============================================================================

def retrieve_email_otp(email_addr: str, password: str, timeout: int = 15) -> Optional[str]:
    """Kết nối IMAP tự động đọc mã bảo mật Facebook 6-8 số từ hòm thư Outlook / Hotmail / Gmail."""
    if not email_addr or not password or "@" not in email_addr:
        return None

    domain = email_addr.split("@")[-1].lower()
    if any(k in domain for k in ("outlook", "hotmail", "live", "msn")):
        imap_server = "outlook.office365.com"
    elif "gmail" in domain:
        imap_server = "imap.gmail.com"
    else:
        imap_server = "outlook.office365.com"

    try:
        mail = imaplib.IMAP4_SSL(imap_server, timeout=timeout)
        mail.login(email_addr, password)
        mail.select("INBOX")

        status, messages = mail.search(None, '(OR FROM "security@facebookmail.com" SUBJECT "Facebook")')
        if status != "OK" or not messages or not messages[0]:
            mail.logout()
            return None

        # Lấy email gần nhất
        msg_ids = messages[0].split()
        latest_id = msg_ids[-1]
        res, msg_data = mail.fetch(latest_id, "(RFC822)")
        if res != "OK":
            mail.logout()
            return None

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() in ("text/plain", "text/html"):
                    body += str(part.get_payload(decode=True) or "")
        else:
            body = str(msg.get_payload(decode=True) or "")

        mail.logout()

        # Tìm mã số 6-8 chữ số
        matches = re.findall(r"\b(\d{6,8})\b", body)
        if matches:
            return matches[0]
        return None
    except Exception as exc:
        logger.debug("Không thể đọc OTP qua IMAP cho %s: %s", email_addr, exc)
        return None


# ==============================================================================
# 4. TOKEN HARVESTER (TRÍCH XUẤT EAAG / EAAB / FB_DTSG TỪ SESSION COOKIE)
# ==============================================================================

def harvest_tokens_from_cookie(cookie_str: str, proxy_url: Optional[str] = None) -> dict[str, str]:
    """Dùng cookie sống để kéo Token EAAG, EAAB và fb_dtsg từ trang Business & Ads Manager."""
    if not cookie_str or "c_user" not in cookie_str:
        return {"eaag_token": "", "eaab_token": "", "fb_dtsg": ""}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cookie": cookie_str,
    }

    client_kwargs: dict[str, Any] = {
        "headers": headers,
        "follow_redirects": True,
        "timeout": 15.0,
    }
    if proxy_url:
        client_kwargs["proxy"] = proxy_url

    eaag_token = ""
    eaab_token = ""
    fb_dtsg = ""

    with httpx.Client(**client_kwargs) as client:
        # 1. Kéo EAAG + fb_dtsg từ billing hub
        try:
            r1 = client.get("https://business.facebook.com/billing_hub/payment_settings/")
            html1 = r1.text
            eaag_match = re.search(r'["\'](EAAG[a-zA-Z0-9]+)["\']', html1)
            if eaag_match:
                eaag_token = eaag_match.group(1)
            dtsg_match = re.search(r'["\']DTSGInitialData["\'],\[\],\{["\']token["\']:["\']([^"\']+)["\']', html1)
            if not dtsg_match:
                dtsg_match = re.search(r'name="fb_dtsg"\s+value="([^"]+)"', html1)
            if dtsg_match:
                fb_dtsg = dtsg_match.group(1)
        except Exception as e:
            logger.debug("Lỗi kéo EAAG từ billing hub: %s", e)

        # 2. Kéo EAAB từ adsmanager
        try:
            r2 = client.get("https://adsmanager.facebook.com/adsmanager/manage/campaigns")
            html2 = r2.text
            eaab_match = re.search(r'["\'](EAAB[a-zA-Z0-9]+)["\']', html2)
            if eaab_match:
                eaab_token = eaab_match.group(1)
            if not fb_dtsg:
                dtsg_match2 = re.search(r'["\']DTSGInitialData["\'],\[\],\{["\']token["\']:["\']([^"\']+)["\']', html2)
                if dtsg_match2:
                    fb_dtsg = dtsg_match2.group(1)
        except Exception as e:
            logger.debug("Lỗi kéo EAAB từ adsmanager: %s", e)

    return {
        "eaag_token": eaag_token,
        "eaab_token": eaab_token,
        "fb_dtsg": fb_dtsg,
    }


# ==============================================================================
# 5. STATEFUL HTTP SESSION LOGIN & 2FA BYPASS ENGINE
# ==============================================================================

def execute_http_session_login(
    uid: str,
    password: str,
    two_fa_secret: str = "",
    email_addr: str = "",
    email_pass: str = "",
    proxy_url: Optional[str] = None,
) -> dict[str, Any]:
    """Đăng nhập Facebook tự động mô phỏng trình duyệt (Mobile/Mbasic Web Flow),
    tự động vượt qua checkpoint 2FA TOTP và thu thập Cookie session hợp lệ.
    """
    if not uid or not password:
        return {"success": False, "status": "WRONG_PASS", "error": "Thiếu UID hoặc Mật khẩu Facebook"}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    client_kwargs: dict[str, Any] = {
        "headers": headers,
        "follow_redirects": True,
        "timeout": 20.0,
    }
    if proxy_url:
        client_kwargs["proxy"] = proxy_url

    with httpx.Client(**client_kwargs) as client:
        # Bước 1: Mở trang login mbasic lấy hidden input
        try:
            resp = client.get("https://mbasic.facebook.com/login.php")
        except Exception as net_err:
            return {"success": False, "status": "PENDING", "error": f"Lỗi kết nối tới Facebook: {net_err}"}

        login_html = resp.text

        # Trích xuất form login
        action_match = re.search(r'<form\s+[^>]*action="([^"]+)"', login_html)
        action_url = action_match.group(1) if action_match else "https://mbasic.facebook.com/login/device-based/regular/login/"
        if not action_url.startswith("http"):
            action_url = "https://mbasic.facebook.com" + action_url

        form_data: dict[str, str] = {}
        for input_match in re.finditer(r'<input\s+[^>]*name="([^"]+)"\s+[^>]*value="([^"]*)"', login_html):
            form_data[input_match.group(1)] = input_match.group(2)

        form_data["email"] = uid
        form_data["pass"] = password
        form_data["login"] = "Log In"

        # Bước 2: Submit credentials
        try:
            post_resp = client.post(action_url, data=form_data)
        except Exception as post_err:
            return {"success": False, "status": "PENDING", "error": f"Lỗi gửi thông tin đăng nhập: {post_err}"}

        cookies = dict(client.cookies)

        # Kiểm tra thành công ngay (có c_user và xs)
        if "c_user" in cookies and "xs" in cookies:
            cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
            return {"success": True, "status": "READY", "cookie": cookie_str, "cookies": cookies}

        page_text = post_resp.text

        # Kiểm tra sai mật khẩu
        if "login_attempt" in str(post_resp.url) or "incorrect" in page_text.lower() or "không chính xác" in page_text.lower():
            return {"success": False, "status": "WRONG_PASS", "error": "Mật khẩu Facebook không chính xác"}

        # Bước 3: Phát hiện 2FA Checkpoint
        if "approvals_code" in page_text or "checkpoint" in str(post_resp.url).lower() or "two_step" in page_text.lower():
            if not two_fa_secret:
                return {
                    "success": False,
                    "status": "CHECKPOINT",
                    "error": "Tài khoản bật bảo mật 2 bước nhưng chưa cung cấp 2FA Secret",
                }

            # Sinh mã TOTP thời gian thực
            totp_code, _ = generate_totp_code(two_fa_secret)
            if not totp_code:
                return {"success": False, "status": "CHECKPOINT", "error": "Khóa 2FA Secret không hợp lệ"}

            # Trích xuất form 2FA
            action_match_2fa = re.search(r'<form\s+[^>]*action="([^"]+)"', page_text)
            action_url_2fa = action_match_2fa.group(1) if action_match_2fa else str(post_resp.url)
            if not action_url_2fa.startswith("http"):
                action_url_2fa = "https://mbasic.facebook.com" + action_url_2fa

            form_data_2fa: dict[str, str] = {}
            for input_match in re.finditer(r'<input\s+[^>]*name="([^"]+)"\s+[^>]*value="([^"]*)"', page_text):
                form_data_2fa[input_match.group(1)] = input_match.group(2)

            form_data_2fa["approvals_code"] = totp_code
            form_data_2fa["submit[Submit Code]"] = "Submit Code"

            try:
                resp_2fa = client.post(action_url_2fa, data=form_data_2fa)
                page_text_2fa = resp_2fa.text
            except Exception as e:
                return {"success": False, "status": "CHECKPOINT", "error": f"Lỗi gửi mã 2FA: {e}"}

            cookies = dict(client.cookies)
            if "c_user" in cookies and "xs" in cookies:
                cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
                return {"success": True, "status": "READY", "cookie": cookie_str, "cookies": cookies}

            # Bước 4: Vượt qua "Save Browser" (Lưu trình duyệt) nếu có
            if "name_action_selected" in page_text_2fa or "save_device" in page_text_2fa or "checkpoint" in str(resp_2fa.url):
                action_match_save = re.search(r'<form\s+[^>]*action="([^"]+)"', page_text_2fa)
                action_url_save = action_match_save.group(1) if action_match_save else str(resp_2fa.url)
                if not action_url_save.startswith("http"):
                    action_url_save = "https://mbasic.facebook.com" + action_url_save

                form_data_save: dict[str, str] = {}
                for input_match in re.finditer(r'<input\s+[^>]*name="([^"]+)"\s+[^>]*value="([^"]*)"', page_text_2fa):
                    form_data_save[input_match.group(1)] = input_match.group(2)

                form_data_save["name_action_selected"] = "save_device"
                form_data_save["submit[Continue]"] = "Continue"

                try:
                    resp_save = client.post(action_url_save, data=form_data_save)
                except Exception:
                    pass

                cookies = dict(client.cookies)
                if "c_user" in cookies and "xs" in cookies:
                    cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
                    return {"success": True, "status": "READY", "cookie": cookie_str, "cookies": cookies}

            # Bước 5: Thử đọc mã bảo mật qua email nếu checkpoint đòi email OTP
            if email_addr and email_pass and ("email" in page_text_2fa.lower() or "mail" in page_text_2fa.lower()):
                email_otp = retrieve_email_otp(email_addr, email_pass)
                if email_otp:
                    form_data_2fa["approvals_code"] = email_otp
                    try:
                        client.post(action_url_2fa, data=form_data_2fa)
                        cookies = dict(client.cookies)
                        if "c_user" in cookies:
                            cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
                            return {"success": True, "status": "READY", "cookie": cookie_str, "cookies": cookies}
                    except Exception:
                        pass

            return {
                "success": False,
                "status": "CHECKPOINT",
                "error": "Tài khoản bị Checkpoint nâng cao (cần phê duyệt thiết bị hoặc email xác nhận)",
            }

        return {
            "success": False,
            "status": "CHECKPOINT" if "checkpoint" in str(post_resp.url) else "PENDING",
            "error": "Chưa hoàn tất phiên đăng nhập (Facebook chuyển hướng bảo mật)",
        }


# ==============================================================================
# 6. AUTO LOGIN, HARVEST & DEEP ASSET SYNC PIPELINE
# ==============================================================================

def auto_login_and_harvest_via(
    via: ViaProfile,
    session: Session,
    proxy_url: Optional[str] = None,
) -> dict[str, Any]:
    """Thực thi toàn diện quy trình tự động hóa cho 1 VIA:
    1. Kiểm tra cookie hiện có: nếu còn sống -> kéo Token EAAG/EAAB/fb_dtsg.
    2. Nếu chưa có cookie hoặc hết hạn -> thực thi HTTP Session Login + 2FA TOTP bypass.
    3. Lưu lại Cookie & Tokens mã hóa an toàn.
    4. Kích hoạt Quét Sâu Toàn Bộ Tài Sản (TKQC, BM, Fanpage, Pixel).
    """
    creds = decrypt_via_credentials(via.encrypted_credentials) if via.encrypted_credentials else {}
    current_cookie = creds.get("cookie", "")
    current_token = creds.get("access_token", "")
    current_eaag = creds.get("eaag_token", "")
    current_eaab = creds.get("eaab_token", "")
    two_fa_secret = creds.get("two_fa_secret", "")
    password = creds.get("password", "")
    email_addr = creds.get("email", "")
    email_pass = creds.get("email_password", "")

    effective_proxy = proxy_url or via.proxy_config or None

    via.login_status = "LOGGING_IN"
    session.flush()

    # --- FAST PATH: Thử kéo token nếu đã có cookie ---
    tokens: dict[str, str] = {}
    if current_cookie and "c_user=" in current_cookie:
        tokens = harvest_tokens_from_cookie(current_cookie, proxy_url=effective_proxy)

    # --- AUTOMATED LOGIN PATH: Nếu chưa có token hoặc chưa có cookie ---
    if not tokens.get("eaag_token") and not tokens.get("eaab_token") and not current_token:
        login_res = execute_http_session_login(
            uid=via.uid,
            password=password,
            two_fa_secret=two_fa_secret,
            email_addr=email_addr,
            email_pass=email_pass,
            proxy_url=effective_proxy,
        )

        if not login_res["success"]:
            via.login_status = login_res["status"]
            via.last_login_error = login_res.get("error")
            session.commit()
            totp_code, rem_secs = generate_totp_code(two_fa_secret) if two_fa_secret else ("", 0)
            return {
                "fb_uid": via.uid,
                "login_status": via.login_status,
                "has_cookie": bool(via.cookie),
                "has_eaag": bool(via.eaag_token),
                "has_eaab": bool(via.eaab_token),
                "totp_code": totp_code,
                "accounts_count": via.ad_account_count,
                "bms_count": via.bm_count,
                "pages_count": via.page_count,
                "message": via.last_login_error or "Đăng nhập thất bại.",
            }

        # Lưu cookie mới
        current_cookie = login_res["cookie"]
        creds["cookie"] = current_cookie
        # Thu hoạch token bằng cookie mới
        tokens = harvest_tokens_from_cookie(current_cookie, proxy_url=effective_proxy)

    # Cập nhật thông tin token vào VIA
    if tokens.get("eaag_token"):
        creds["eaag_token"] = tokens["eaag_token"]
        if not creds.get("access_token"):
            creds["access_token"] = tokens["eaag_token"]
    if tokens.get("eaab_token"):
        creds["eaab_token"] = tokens["eaab_token"]
        if not creds.get("access_token"):
            creds["access_token"] = tokens["eaab_token"]
    if tokens.get("fb_dtsg"):
        creds["fb_dtsg"] = tokens["fb_dtsg"]

    via.encrypted_credentials = encrypt_via_credentials(creds)
    via.login_status = "READY"
    via.token_status = "ACTIVE"
    via.uid_live_status = "LIVE"
    via.last_login_error = None
    session.flush()

    # --- DEEP ASSET SWEEP ---
    try:
        sync_via_all_assets(session=session, via_id=via.id, allow_cookie_token_recovery=True)
    except Exception as sweep_err:
        logger.warning("Deep asset sweep warning cho VIA %s: %s", via.uid, sweep_err)

    session.refresh(via)
    via.ad_account_count = session.scalar(select(func.count(SyncedAdAccount.id)).where(SyncedAdAccount.via_profile_id == via.id)) or 0
    via.bm_count = session.scalar(select(func.count(SyncedBM.id)).where(SyncedBM.via_profile_id == via.id)) or 0
    via.page_count = session.scalar(select(func.count(SyncedPage.id)).where(SyncedPage.via_profile_id == via.id)) or 0
    session.commit()

    totp_code, rem_secs = generate_totp_code(two_fa_secret) if two_fa_secret else ("", 0)

    return {
        "fb_uid": via.uid,
        "login_status": via.login_status,
        "has_cookie": bool(via.cookie),
        "has_eaag": bool(via.eaag_token),
        "has_eaab": bool(via.eaab_token),
        "totp_code": totp_code,
        "accounts_count": via.ad_account_count,
        "bms_count": via.bm_count,
        "pages_count": via.page_count,
        "message": f"Đã đăng nhập thành công và quét {via.ad_account_count} TKQC, {via.bm_count} BM, {via.page_count} Fanpage.",
    }
