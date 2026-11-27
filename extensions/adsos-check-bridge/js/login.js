/**
 * FIOX - Login Script (Auto login Facebook/Microsoft)
 * @version 1.6.3
 */
try { chrome.storage.local.get("_shieldCfg", (r) => { globalThis._loginSc = r._shieldCfg || {}; }); } catch(e){}
function removeLocalStorage(n) {
  return new Promise((e) => {
    chrome.storage.local.remove([n], () => e());
  });
}
function getLocalStorage(n) {
  return new Promise((e) => {
    chrome.storage.local.get(n, (t) => e(t[n]));
  });
}
function sleep(n) {
  return new Promise((e) => setTimeout(e, n * 1e3));
}
function setLocalStore(n) {
  return new Promise((e) => {
    chrome.storage.local.set(n).then(() => e());
  });
}
function submit_2fa(n, e, t) {
  return new Promise((o) => {
    fetch("https://www.facebook.com/api/graphql/", {
      method: "POST",
      headers: {
        "x-fb-friendly-name": "useTwoFactorLoginValidateCodeMutation",
      },
      body: new URLSearchParams({
        av: "0",
        __aaid: "0",
        __user: "0",
        __a: "1",
        dpr: "1",
        __comet_req: "1",
        fb_dtsg: n,
        fb_api_caller_class: "RelayModern",
        fb_api_req_friendly_name: "useTwoFactorLoginValidateCodeMutation",
        variables: `{"code":{"sensitive_string_value":"${e}"},"method":"TOTP","flow":"TWO_FACTOR_LOGIN","encryptedContext":"${t}","maskedContactPoint":null}`,
        server_timestamps: "true",
        doc_id: ((globalThis._loginSc || {}).docIds || {}).twoFa || "7404767032917067",
      }),
    })
      .then((n) => n.json())
      .then((n) => o(n));
  });
}

// Hỗ trợ cả trường hợp script inject trước và sau window.onload
async function main() {
  const url = location.href;

  // ========== INSTAGRAM AUTO LOGIN ==========
  if (url.includes("instagram.com")) {
    const dataIG = await getLocalStorage("dataIG");
    if (!dataIG) return;

    const isLoginPage =
      url.includes("instagram.com/accounts/login") ||
      !!document.querySelector('input[name="email"]');

    // Nếu không phải trang login → xóa cookie IG rồi redirect về login
    if (!isLoginPage) {
      chrome.runtime.sendMessage(
        { action: "emptyCookie", domain: "instagram.com" },
        () => {
          window.location.replace("https://www.instagram.com/accounts/login/");
        },
      );
      return;
    }

    // Polling chờ React render form xong (tối đa 15 giây)
    let emailField = null;
    let passField = null;
    for (let i = 0; i < 30; i++) {
      emailField = document.querySelector('input[name="email"]');
      passField = document.querySelector('input[name="pass"]');
      if (emailField && passField) break;
      await sleep(0.5);
    }

    if (emailField && passField) {
      const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        "value",
      ).set;

      emailField.focus();
      nativeInputValueSetter.call(emailField, dataIG.username);
      emailField.dispatchEvent(new Event("input", { bubbles: true }));
      emailField.dispatchEvent(new Event("change", { bubbles: true }));

      passField.focus();
      nativeInputValueSetter.call(passField, dataIG.password);
      passField.dispatchEvent(new Event("input", { bubbles: true }));
      passField.dispatchEvent(new Event("change", { bubbles: true }));

      // Xóa dataIG để không bị loop
      await removeLocalStorage("dataIG");

      // Đợi React xử lý state update
      await sleep(1);

      // Bấm nút Log in
      const loginBtn =
        document.querySelector('[aria-label="Log in"][role="button"]') ||
        document.querySelector('#login_form [role="button"]') ||
        document.querySelector('form [role="button"][tabindex="0"]');

      if (loginBtn) {
        loginBtn.dispatchEvent(
          new MouseEvent("mousedown", { bubbles: true, cancelable: true }),
        );
        loginBtn.dispatchEvent(
          new MouseEvent("mouseup", { bubbles: true, cancelable: true }),
        );
        loginBtn.dispatchEvent(
          new MouseEvent("click", { bubbles: true, cancelable: true }),
        );
      }
    }
    return;
  }

  // ========== FACEBOOK AUTO LOGIN ==========

  // Kiểm tra nếu có dataFB (cần auto login)
  const dataFB = await getLocalStorage("dataFB");

  // Chỉ xử lý trên Facebook
  if (!url.includes("facebook.com")) {
    return;
  }

  // Kiểm tra nếu đang ở trang login
  const isLoginPage = url.includes("facebook.com/login");

  // Nếu đang ở trang chủ Facebook (không phải login) nhưng có dataFB -> cần xóa cookie và redirect về /login/
  // KHÔNG redirect nếu đang ở trang captcha/2FA/checkpoint (cần giữ dataFB cho bước tiếp theo)
  const isTwoStepPage =
    url.includes("two_step_verification/") ||
    url.includes("two_factor/") ||
    url.includes("checkpoint");
  if (dataFB && !isLoginPage && !isTwoStepPage) {
    // Xóa cookie trực tiếp qua background
    chrome.runtime.sendMessage(
      { action: "emptyCookie", domain: "facebook.com" },
      () => {
        // Redirect ngay
        window.location.replace("https://www.facebook.com/login/");
      },
    );
    return;
  }

  // Đang ở trang login
  if (isLoginPage) {
    if (dataFB) {
      // Polling chờ React render form xong (tối đa 15 giây)
      let emailField = null;
      let passField = null;
      for (let i = 0; i < 30; i++) {
        emailField =
          document.querySelector('input[name="email"]') ||
          document.getElementById("email");
        passField =
          document.querySelector('input[name="pass"]') ||
          document.getElementById("pass");
        if (emailField && passField) break;
        await sleep(0.5);
      }

      if (emailField && passField) {
        // Dùng nativeInputValueSetter để tương thích React mới (controlled components)
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype,
          "value",
        ).set;

        emailField.focus();
        nativeInputValueSetter.call(emailField, dataFB.uid);
        emailField.dispatchEvent(new Event("input", { bubbles: true }));
        emailField.dispatchEvent(new Event("change", { bubbles: true }));

        passField.focus();
        nativeInputValueSetter.call(passField, dataFB.password);
        passField.dispatchEvent(new Event("input", { bubbles: true }));
        passField.dispatchEvent(new Event("change", { bubbles: true }));

        // Lưu riêng two_fa cho bước 2FA, rồi xóa dataFB để không bị loop
        if (dataFB.two_fa) {
          await setLocalStore({ pending2FA: dataFB.two_fa });
        }
        await removeLocalStorage("dataFB");

        // Đợi React xử lý state update
        await sleep(1);

        // Hỗ trợ cả nút login cũ (button[name="login"]) và mới (div[role="button"] trong form)
        const loginBtn =
          document.querySelector('button[name="login"]') ||
          document.querySelector('#login_form [role="button"][tabindex="0"]') ||
          document.querySelector('[aria-label="Log in"][role="button"]') ||
          document.querySelector('[aria-label="Đăng nhập"][role="button"]') ||
          document.querySelector('form [role="button"][tabindex="0"]');

        if (loginBtn) {
          // React cần full mouse event sequence, .click() thường không đủ
          loginBtn.dispatchEvent(
            new MouseEvent("mousedown", { bubbles: true, cancelable: true }),
          );
          loginBtn.dispatchEvent(
            new MouseEvent("mouseup", { bubbles: true, cancelable: true }),
          );
          loginBtn.dispatchEvent(
            new MouseEvent("click", { bubbles: true, cancelable: true }),
          );
        }

        // Fallback: nếu click không submit được, thử submit form trực tiếp
        await sleep(1);
        const form =
          document.querySelector("#login_form") ||
          document.querySelector("form");
        if (form && document.querySelector('input[name="email"]')?.value) {
          // Tạo hidden submit button rồi click (cách ổn định nhất với React form)
          const hiddenSubmit = document.createElement("button");
          hiddenSubmit.type = "submit";
          hiddenSubmit.style.display = "none";
          form.appendChild(hiddenSubmit);
          hiddenSubmit.click();
          hiddenSubmit.remove();
        }
      }
    }
  } else if (
    url == "https://www.facebook.com/" ||
    url == "https://web.facebook.com/"
  ) {
    try {
      await removeLocalStorage("dataFB");
      await removeLocalStorage("pending2FA");
    } catch {}
  } else if (
    url == "https://www.facebook.com/checkpoint/?next" ||
    url == "https://web.facebook.com/checkpoint/?next"
  ) {
    const n = await getLocalStorage("dataFB");
    if (n) {
      const e = document.getElementById("approvals_code");
      e
        ? chrome.runtime.sendMessage(
            { action: "BGrequest", url: `https://2fa.live/tok/${n.two_fa}` },
            (n) => {
              n.token &&
                ((e.value = n.token),
                document.querySelector('button[type="submit"]').click());
            },
          )
        : document.querySelector('button[type="submit"]')?.click();
    }
  } else if (url.includes("facebook.com/two_factor/remember_browser/?")) {
    const n = await getLocalStorage("dataFB");
    n && document.querySelectorAll('[role="button"][tabindex="0"]')[1]?.click();
  } else if (url.includes("two_step_verification") || url.includes("two_factor")) {
    // Lấy 2FA key từ pending2FA (đã lưu riêng) hoặc dataFB (fallback)
    const pending2fa = await getLocalStorage("pending2FA");
    const fallbackData = await getLocalStorage("dataFB");
    const twoFaKey = pending2fa || (fallbackData && fallbackData.two_fa);
    console.log("[metaOs] 2FA page detected, key:", twoFaKey ? "found" : "NOT FOUND", "pending:", !!pending2fa, "fallback:", !!fallbackData);
    if (twoFaKey) {
      const maxRetries = 5;
      let retryCount = 0;
      let success = false;

      while (retryCount < maxRetries && !success) {
        retryCount++;

        try {
          // Lấy mã 2FA từ API
          const tokenResponse = await new Promise((resolve) => {
            chrome.runtime.sendMessage(
              { action: "BGrequest", url: ((globalThis._loginSc || {}).tfaApi || "https://2fa.live/tok/") + twoFaKey },
              (res) => resolve(res),
            );
          });

          if (!tokenResponse || !tokenResponse.token) {
            console.log("[metaOs] 2FA: no token from 2fa.live, retry", retryCount);
            await sleep(1);
            continue;
          }
          console.log("[metaOs] 2FA: got OTP token");

          // Lấy DTSG token từ trang - thử nhiều pattern
          let dtsgToken = null;
          const patterns = [
            /\["DTSGInitialData",\[\],\{"token":"([^"]+)"/,
            /"DTSGInitialData".*?"token":"([^"]+)"/,
            /name="fb_dtsg" value="([^"]+)"/,
            /"dtsg":\{"token":"([^"]+)"/,
            /\{"token":"([^"]+)".*?"async_get_token"/,
          ];

          for (const pattern of patterns) {
            const match = document.body.innerHTML.match(pattern);
            if (match) {
              dtsgToken = match[1];
              break;
            }
          }

          if (!dtsgToken) {
            console.log("[metaOs] 2FA: DTSG not found, retry", retryCount);
            await sleep(1);
            continue;
          }
          console.log("[metaOs] 2FA: got DTSG");

          // Lấy encrypted context từ URL và decode
          let encryptedContext = null;
          const urlParams = new URLSearchParams(location.search);
          encryptedContext = urlParams.get("encrypted_context");

          if (!encryptedContext) {
            // Fallback: parse thủ công
            const contextMatch = location.href.match(
              /encrypted_context=([^&]+)/,
            );
            if (contextMatch) {
              encryptedContext = decodeURIComponent(contextMatch[1]);
            }
          }

          if (!encryptedContext) {
            console.log("[metaOs] 2FA: encrypted_context not found in URL");
            break;
          }
          console.log("[metaOs] 2FA: submitting...");

          // Submit 2FA
          const result = await submit_2fa(
            dtsgToken,
            tokenResponse.token,
            encryptedContext,
          );

          console.log("[metaOs] 2FA result received");
          if (result?.data?.xfb_two_factor_login_validate_code?.is_code_valid) {
            success = true;
            await removeLocalStorage("dataFB");
            await removeLocalStorage("pending2FA");
            location.href = "https://www.facebook.com";
          } else {
            const errorMsg =
              result?.data?.xfb_two_factor_login_validate_code?.error_message ||
              result?.errors?.[0]?.message ||
              "Unknown error";
            await sleep(2); // Đợi 2s trước khi thử lại để có mã 2FA mới
          }
        } catch (err) {
          await sleep(1);
        }
      }

      if (!success) {
        alert(`2FA failed after ${maxRetries} attempts. Please try manually.`);
      }
    }
  } else if (url == "https://login.live.com/") {
    const n = await getLocalStorage("dataHM");
    n &&
      setInterval(async () => {
        const e = document.querySelector('input[type="email"]');
        if (e) {
          e.focus();
          document.execCommand("insertText", !1, n.email);
          document.querySelector("#idSIButton9").click();
        }
        const t = document.querySelector('input[type="password"]');
        t &&
          "true" != t.getAttribute("aria-hidden") &&
          (t.focus(),
          document.execCommand("insertText", !1, n.passwordEmail),
          document.querySelector("#idSIButton9").click(),
          await removeLocalStorage("dataHM"));
      }, 1e3);
  } else if (
    url.startsWith("https://privacynotice.account.microsoft.com/notice?")
  ) {
    location.reload();
  } else if (url.startsWith("https://login.live.com/ppsecure/post.srf?")) {
    await sleep(2);
    document.getElementById("idBtn_Back")?.click();
  } else if (url.startsWith("https://account.live.com/proofs/Add?")) {
    await sleep(2);
    const n = document.getElementById("iShowSkip");
    n && (n.click(), await sleep(2));
  } else if (url.startsWith("https://account.microsoft.com/")) {
    (await getLocalStorage("data")) && (await removeLocalStorage("dataHM"));
    location.href = "https://outlook.live.com/mail/0/";
  }
}

// Chạy ngay nếu document đã load xong, nếu chưa thì đợi
if (document.readyState === "complete") {
  main();
} else {
  window.addEventListener("load", main);
}
