"use client";

import { useEffect, useRef, useState } from "react";
import { createVia, ViaProfile } from "../lib/api";
import { MonoIcon } from "./mono-icon";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Gọi sau khi tạo thành công để trang tải lại danh sách. */
  onCreated: (via: ViaProfile) => void;
  /** Bắt đầu luồng OAuth chính thức của Meta cho VIA vừa tạo. */
  onAuthorize: (via: ViaProfile) => void;
};

const UID_PATTERN = /^\d{5,20}$/;

export default function CreateViaModal({ open, onClose, onCreated, onAuthorize }: Props) {
  const [uid, setUid] = useState("");
  const [profileName, setProfileName] = useState("");
  const [proxy, setProxy] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [password, setPassword] = useState("");
  const [twoFa, setTwoFa] = useState("");
  const [email, setEmail] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<ViaProfile | null>(null);
  const uidRef = useRef<HTMLInputElement>(null);
  // Giữ onClose mới nhất trong ref: trang cha render lại mỗi giây (đồng hồ OTP) nên
  // không được đưa onClose vào deps của effect reset form — nếu không form bị xóa trắng.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    setUid("");
    setProfileName("");
    setProxy("");
    setShowAdvanced(false);
    setPassword("");
    setTwoFa("");
    setEmail("");
    setEmailPassword("");
    setError(null);
    setCreated(null);
    const t = window.setTimeout(() => uidRef.current?.focus(), 30);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!open) return null;

  const cleanUid = uid.trim();
  const uidValid = UID_PATTERN.test(cleanUid);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uidValid) {
      setError("UID phải là dãy số ID tài khoản Facebook (5–20 chữ số).");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await createVia({
        uid: cleanUid,
        profile_name: profileName.trim() || undefined,
        proxy_config: proxy.trim() || undefined,
        password: password || undefined,
        two_fa_secret: twoFa.trim() || undefined,
        email: email.trim() || undefined,
        email_password: emailPassword || undefined,
      });
      setCreated(res.via);
      onCreated(res.via);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Không tạo được VIA.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="create-via-title">
        <header>
          <div>
            <h2 id="create-via-title">{created ? "Đã tạo VIA" : "Tạo VIA"}</h2>
            <p>
              {created
                ? "Bước tiếp theo: cấp quyền Facebook để hệ thống đọc BM, TKQC, Fanpage."
                : "Một VIA là một tài khoản Facebook bạn quản lý. Chỉ cần UID để bắt đầu."}
            </p>
          </div>
          <button type="button" onClick={onClose} aria-label="Đóng">
            <MonoIcon name="close" />
          </button>
        </header>

        {created ? (
          <>
            <div className="modal-body">
              <div className="modal-success">
                <span className="success-mark"><MonoIcon name="check" /></span>
                <h3>
                  {created.profile_name} <span className="mono muted">· {created.uid}</span>
                </h3>
                <p>
                  Bấm <strong>Cấp quyền Facebook</strong> để mở hộp thoại chính thức của Meta. Hãy đăng nhập
                  <strong> đúng tài khoản Facebook có UID {created.uid}</strong> — nếu khác UID, hệ thống sẽ từ chối
                  lưu token. Token được lưu mã hóa, không hiển thị ra giao diện.
                </p>
              </div>
            </div>
            <footer>
              <button type="button" className="btn" onClick={onClose}>
                Để sau
              </button>
              <button type="button" className="btn primary" onClick={() => onAuthorize(created)}>
                <MonoIcon name="key" />
                Cấp quyền Facebook ngay
              </button>
            </footer>
          </>
        ) : (
          <form onSubmit={(e) => void submit(e)}>
            <div className="modal-body">
              <label className="field">
                UID Facebook *
                <input
                  ref={uidRef}
                  inputMode="numeric"
                  autoComplete="off"
                  placeholder="VD: 100012345678901"
                  value={uid}
                  onChange={(e) => setUid(e.target.value.replace(/\s/g, ""))}
                  aria-invalid={uid.length > 0 && !uidValid}
                />
                <span className="field-hint">
                  Dãy số ID của tài khoản Facebook. Lấy nhanh: vào Graph API Explorer, chạy <code>me?fields=id</code>{" "}
                  bằng đúng tài khoản sẽ cấp quyền.
                </span>
              </label>

              <div className="field-row">
                <label className="field">
                  Tên hồ sơ
                  <input
                    placeholder="VD: VIA-001 · BM chính"
                    value={profileName}
                    onChange={(e) => setProfileName(e.target.value)}
                  />
                </label>
                <label className="field">
                  Proxy riêng
                  <input
                    placeholder="IP:Port:User:Pass"
                    value={proxy}
                    onChange={(e) => setProxy(e.target.value)}
                  />
                </label>
              </div>

              <div className={`disclosure ${showAdvanced ? "open" : ""}`}>
                <button type="button" onClick={() => setShowAdvanced((v) => !v)} aria-expanded={showAdvanced}>
                  Thông tin đăng nhập (không bắt buộc)
                  <MonoIcon name="chevron-down" />
                </button>
                {showAdvanced && (
                  <div>
                    <span className="field-hint">
                      Không cần cho cấp quyền OAuth. Chỉ điền nếu bạn dùng chức năng đăng nhập/nuôi tự động. Mọi thông tin
                      được mã hóa trước khi lưu.
                    </span>
                    <div className="field-row">
                      <label className="field">
                        Mật khẩu Facebook
                        <input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
                      </label>
                      <label className="field">
                        Khóa 2FA (TOTP)
                        <input autoComplete="off" placeholder="16/32 ký tự" value={twoFa} onChange={(e) => setTwoFa(e.target.value)} />
                      </label>
                    </div>
                    <div className="field-row">
                      <label className="field">
                        Email
                        <input type="email" autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} />
                      </label>
                      <label className="field">
                        Mật khẩu email
                        <input type="password" autoComplete="new-password" value={emailPassword} onChange={(e) => setEmailPassword(e.target.value)} />
                      </label>
                    </div>
                  </div>
                )}
              </div>

              {error && <div className="form-error">{error}</div>}
            </div>
            <footer>
              <button type="button" className="btn" onClick={onClose}>
                Hủy
              </button>
              <button type="submit" className="btn primary" disabled={submitting || !uidValid}>
                <MonoIcon name="plus" />
                {submitting ? "Đang tạo..." : "Tạo VIA"}
              </button>
            </footer>
          </form>
        )}
      </div>
    </div>
  );
}
