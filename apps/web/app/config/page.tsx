"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJson, postJson } from "../../lib/api";

type MetaCheck = {
  mode: string;
  api_version: string;
  accounts_accessible: number;
  ok: boolean;
  error: string | null;
};

type LatestBalance = {
  balance: string | null;
  read_at: string | null;
  source: string | null;
  note: string | null;
};

type Wallet = {
  id: number;
  wallet_name: string;
  wallet_address: string;
  network: string;
  contract: string;
  auto_sync: boolean;
  last_checked_at: string | null;
  last_ok_at: string | null;
  last_error: string | null;
  latest_balance: LatestBalance | null;
};

type WalletConfig = {
  mode_live: boolean;
  wallet: Wallet | null;
  env_wallet_configured: boolean;
  network: string;
  contract: string;
  disclaimers: string[];
};

type VerifyResult = {
  ok: boolean;
  balance: string | null;
  read_at: string | null;
  note: string | null;
  error?: string;
  saved_wallet_address?: string | null;
};

type SavedResult = { saved: boolean; wallet_address: string; verified: boolean };

type ReadResult = { balance: string | null; read_at: string | null; note: string | null };

export default function ConfigPage() {
  const [check, setCheck] = useState<MetaCheck | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const runCheck = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const data = await fetchJson<MetaCheck>("/meta-sync/check");
      setCheck(data);
      if (!data.ok && data.error) setError(data.error);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      setCheck(null);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    runCheck();
  }, [runCheck]);

  // ===== Ví USDT TRC20 =====
  const [config, setConfig] = useState<WalletConfig | null>(null);
  const [walletError, setWalletError] = useState<string | null>(null);
  const [walletMsg, setWalletMsg] = useState<string | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [saving, setSaving] = useState(false);
  const [reading, setReading] = useState(false);
  const [wName, setWName] = useState("Ví chung USDT TRC20");
  const [wAddr, setWAddr] = useState("TPVT4NSNjCCEeaR5FpAq3Q9g65hXF8Uh9r");
  const [verifyResult, setVerifyResult] = useState<VerifyResult | null>(null);
  const loadedOnce = useRef(false);

  const loadWallet = useCallback(async () => {
    setWalletError(null);
    try {
      const data = await fetchJson<WalletConfig>("/usdt/wallet");
      setConfig(data);
      if (data.wallet && !loadedOnce.current) {
        loadedOnce.current = true;
        setWName(data.wallet.wallet_name);
        setWAddr(data.wallet.wallet_address);
      }
    } catch (e) {
      setWalletError((e as Error).message);
    }
  }, []);
  useEffect(() => { void loadWallet(); }, [loadWallet]);

  const verify = useCallback(async () => {
    setVerifying(true); setWalletMsg(null); setConflict(null); setWalletError(null); setVerifyResult(null);
    try {
      const result = await postJson<VerifyResult>("/usdt/wallet/verify", { address: wAddr });
      setVerifyResult(result);
      setWalletMsg("Kiểm tra kết nối THÀNH CÔNG. Bấm Lưu để lưu địa chỉ theo dõi.");
    } catch (e) {
      const msg = (e as Error).message;
      setWalletError(msg);
      setVerifyResult({ ok: false, balance: null, read_at: null, note: null, error: msg });
    } finally { setVerifying(false); }
  }, [wAddr]);

  const save = useCallback(async () => {
    setSaving(true); setWalletMsg(null); setConflict(null); setWalletError(null);
    try {
      const res = await postJson<SavedResult>("/usdt/wallet", { wallet_name: wName, address: wAddr });
      setWalletMsg(`Đã lưu ví ${res.wallet_address} (đã kiểm tra kết nối).`);
      loadedOnce.current = false;
      await loadWallet();
    } catch (e) {
      const message = (e as Error).message;
      if (message.includes("Đã có ví khác được theo dõi") || message.includes("409")) {
        setConflict(message);
      } else {
        setWalletError(message);
      }
    } finally { setSaving(false); }
  }, [wAddr, wName, loadWallet]);

  const toggleSync = useCallback(async (next: boolean) => {
    setWalletMsg(null); setWalletError(null);
    try {
      await fetch("/api/v1/usdt/wallet", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ auto_sync: next }) });
      setWalletMsg(next ? "Đã BẬT tự đồng bộ." : "Đã TẮT tự đồng bộ.");
      await loadWallet();
    } catch (e) { setWalletError((e as Error).message); }
  }, [loadWallet]);

  const readBalance = useCallback(async () => {
    setReading(true); setWalletMsg(null); setWalletError(null);
    try {
      const res = await postJson<ReadResult>("/usdt/wallet/read-balance", {});
      setWalletMsg(res.balance == null
        ? `Đã kiểm tra (${res.read_at}) — chưa có dữ liệu USDT GLU trên ví; không giả 0.`
        : `Số dư hiện tại: ${res.balance} USDT (lúc ${res.read_at}).`);
      await loadWallet();
    } catch (e) {
      setWalletError(`Không đọc được số dư: ${(e as Error).message}`);
    } finally { setReading(false); }
  }, [loadWallet]);

  const fmtAt = (iso?: string | null) =>
    iso ? new Date(iso).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" }) : "—";

  return (
    <div className="w-full space-y-6">
      <h1>Cấu hình kết nối</h1>
      <p><a href="/config/wallets" style={{display:"inline-block",background:"#155778",color:"white",padding:"12px 18px",borderRadius:8}}>Ví &amp; tài khoản sàn — Binance</a></p>
      <p>
        Meta: API v26.0 mặc định (D-040, env <code>ADSOS_META_API_VERSION</code>), nhiều BM + token map theo
        BM/ad account, chỉ đọc (GET). Token KHÔNG được dán vào chat — chỉ qua biến môi trường.
      </p>

      <section id="usdt-wallet" style={{ border: "1px solid #ddd", borderRadius: 12, padding: 16, marginTop: 16 }}>
        <h2>Ví USDT TRC20 (TRON Mainnet)</h2>
        <p>
          Theo dõi số dư on-chain của địa chỉ ví công khai — chỉ ĐỌC. Không yêu cầu private key / seed
          phrase / ký ví / quyền chuyển tiền. API key provider (nếu cần) đặt qua env
          <code> ADSOS_TRON_API_KEY</code> phía backend, không đưa vào giao diện.
        </p>
        {walletError && (
          <p style={{ color: "crimson" }} role="alert">
            {walletError}{" "}
            <button type="button" onClick={() => void loadWallet()}>Thử lại</button>
          </p>
        )}
        {conflict && <p style={{ color: "crimson" }} role="alert">{conflict}</p>}
        {walletMsg && <p style={{ color: "seagreen" }}>{walletMsg}</p>}

        {config?.wallet == null ? (
          <>
            <p style={{ fontStyle: "italic" }}>Chưa lưu ví nào. Nhập tên ví + địa chỉ rồi bấm Kiểm tra kết nối.</p>
            <label style={{ display: "block" }}>Tên ví{" "}
              <input value={wName} onChange={(e) => setWName(e.target.value)} style={{ width: "min(100%, 320px)" }} />
            </label>
            <label style={{ display: "block", marginTop: 8 }}>
              Địa chỉ công khai{" "}
              <input value={wAddr} onChange={(e) => setWAddr(e.target.value)} style={{ width: "min(100%, 480px)" }} />
            </label>
            <p>Mạng: <b>TRON Mainnet</b></p>
            <button type="button" onClick={() => void verify()} disabled={verifying || !wAddr.trim()}>
              {verifying ? "Đang kiểm tra…" : "Kiểm tra kết nối"}
            </button>{" "}
            <button type="button" onClick={() => void save()} disabled={saving || !wAddr.trim()}>
              {saving ? "Đang lưu…" : "Lưu"}
            </button>{" "}
            <button type="button" onClick={() => void readBalance()} disabled={reading || !config?.wallet}>
              {reading ? "Đang đọc…" : "Cập nhật số dư"}
            </button>
            {verifyResult && (
              <p>
                {verifyResult.ok ? "Kết nối OK" : "Kết nối THẤT BẠI"}
                {verifyResult.balance == null ? " — chưa có dữ liệu USDT trên ví (không giả 0)" : ` — số dư đọc thử: ${verifyResult.balance} USDT`}
                {verifyResult.read_at ? ` (lúc ${fmtAt(verifyResult.read_at)})` : ""}
                {verifyResult.note ? ` — ${verifyResult.note}` : ""}
              </p>
            )}
            {verifyResult && !verifyResult.ok && (
              <p>Lỗi không biến số dư thành 0; kiểm tra địa chỉ/mạng rồi thử lại.</p>
            )}
          </>
        ) : (
          <>
            <ul>
              <li>Tên ví: <b>{config.wallet.wallet_name}</b></li>
              <li>Địa chỉ: <code>{config.wallet.wallet_address}</code></li>
              <li>Mạng: <b>{config.wallet.network}</b></li>
              <li>Hợp đồng USDT: <code>{config.wallet.contract}</code></li>
              <li>
                Tự đồng bộ:{" "}
                <input
                  type="checkbox"
                  checked={config.wallet.auto_sync}
                  onChange={(e) => void toggleSync(e.target.checked)}
                  aria-label="Bật/tắt tự đồng bộ số dư"
                />
                <span style={{ color: config.wallet.auto_sync ? "seagreen" : undefined }}>
                  {config.wallet.auto_sync ? "ĐANG BẬT" : "TẮT (mặc định)"}
                </span>
              </li>
              <li>
                Số dư USDT: <b>{config.wallet.latest_balance?.balance ?? "—"}</b>
                {config.wallet.latest_balance?.balance == null && " (không giả 0)"}
              </li>
              <li>Thời điểm đọc: {fmtAt(config.wallet.latest_balance?.read_at)}</li>
              <li>
                Trạng thái kết nối:{" "}
                <b>{config.wallet.last_error ? "LỖI" : config.wallet.last_ok_at ? "OK" : "CHƯA ĐỌC"}</b>
              </li>
              {config.wallet.last_error && (<li style={{ color: "crimson" }}>Lỗi gần nhất: {config.wallet.last_error}</li>)}
            </ul>
            <button type="button" onClick={() => void readBalance()} disabled={reading}>
              {reading ? "Đang đọc…" : "Cập nhật số dư"}
            </button>{" "}
            <button type="button" onClick={() => void loadWallet()}>Tải lại cấu hình</button>
          </>
        )}
        <details style={{ marginTop: 12 }}>
          <summary>Lưu ý an toàn & đối soát</summary>
          <ul>
            {(config?.disclaimers ?? []).map((d) => (<li key={d}>{d}</li>))}
          </ul>
        </details>
      </section>

      <h2 style={{ marginTop: 24 }}>Bước 1 — Cấp token Meta (một lần)</h2>
      <ol>
        <li>
          Business Settings → System User → tạo user <code>adsos-readonly</code>.
        </li>
        <li>
          Add Assets → chọn business/ad account → quyền tối thiểu <code>ads_read</code>.
        </li>
        <li>Generate Token → quyền <code>ads_read</code>. Không copy token vào hội thoại/log.</li>
        <li>
          Đặt biến môi trường trong PowerShell <b>trước khi khởi động backend</b>:
          <pre style={{ background: "#f6f6f6", padding: 8 }}>$env:ADSOS_META_ACCESS_TOKEN = "..."</pre>
          hoặc nhiều BM:
          <pre style={{ background: "#f6f6f6", padding: 8 }}>
            {"$env:ADSOS_META_TOKEN_MAP = 'act_id_1=TOKEN1,bm_id_2=TOKEN2'"}
          </pre>
        </li>
        <li>Khởi động lại uvicorn (nếu chạy --reload, restart process để đọc env mới).</li>
      </ol>

      <h2>Bước 2 — Kiểm tra quyền truy cập Meta</h2>
      <button onClick={() => runCheck()} disabled={busy}>
        {busy ? "Đang kiểm…" : "Kiểm tra lại"}
      </button>
      <p>
        Endpoint: <code>GET /api/v1/meta-sync/check</code> — mock mode → 400 (không fallback), live → kiểm
        token + quyền <code>ads_read</code> + số account truy cập được.
      </p>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      {check && (
        <ul>
          <li>
            mode: <b>{check.mode}</b>
          </li>
          <li>api_version: {check.api_version}</li>
          <li>
            token + <code>ads_read</code>: <b>{check.ok ? "OK" : "LỖI"}</b>
          </li>
          <li>Số ad account truy cập được: {check.accounts_accessible}</li>
        </ul>
      )}

      <h2>Google Sheets (đã kết nối read-only)</h2>
      <p>
        Service account reader qua <code>ADSOS_GOOGLE_SERVICE_ACCOUNT_FILE</code> — chỉ đọc. Spreadsheet
        đang dùng ở màn <code>/sheets</code>.
      </p>
    </div>
  );
}
