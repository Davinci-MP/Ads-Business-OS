"use client";

import Link from "next/link";
import { FormEvent, useRef, useState } from "react";
import { Balance, ConnectionsResult, ExchangeConnection, History, exchangeRequest, formatUsdt } from "../../../lib/exchange-api";
import styles from "./wallets.module.css";

const at = (value: string | null) => value ? new Date(value).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" }) : "Chưa cập nhật";
const message = (error: unknown) => error instanceof Error ? error.message : "Không kết nối được máy chủ. Vui lòng thử lại.";

export default function WalletsPage() {
  const [token, setToken] = useState("");
  const [unlocked, setUnlocked] = useState(false);
  const [data, setData] = useState<ConnectionsResult | null>(null);
  const [balances, setBalances] = useState<Record<number, Balance[]>>({});
  const [history, setHistory] = useState<Record<number, History[]>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [label, setLabel] = useState("Binance chính");
  const [apiKey, setApiKey] = useState("");
  const [secret, setSecret] = useState("");
  const [disconnecting, setDisconnecting] = useState<number | null>(null);
  const generation = useRef(0);

  async function load(auth: string) {
    const version = generation.current;
    const next = await exchangeRequest<ConnectionsResult>(auth, "/connections");
    const results = await Promise.all(next.connections.map(async c => {
      const result = await exchangeRequest<{ snapshots: Balance[] }>(auth, `/connections/${c.id}/snapshots?limit=20`);
      return [c.id, result.snapshots] as const;
    }));
    if (generation.current !== version) return;
    setData(next); setBalances(Object.fromEntries(results)); setUnlocked(true);
  }
  async function run(key: string, action: () => Promise<void>) {
    if (busy) return;
    setBusy(key); setError(""); setNotice("");
    try { await action(); } catch (e) { setError(message(e)); } finally { setBusy(""); }
  }
  function closeForm() { setFormOpen(false); setApiKey(""); setSecret(""); setEditing(null); }
  function lock() {
    generation.current++; setUnlocked(false); setToken(""); setData(null); setBalances({}); setHistory({}); closeForm(); setError(""); setNotice("");
  }
  function openForm(connection?: ExchangeConnection) {
    setEditing(connection?.id ?? null); setLabel(connection?.label ?? "Binance chính"); setApiKey(""); setSecret(""); setFormOpen(true); setError(""); setNotice("");
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    await run("save", async () => {
      if ((apiKey.trim() && !secret.trim()) || (!apiKey.trim() && secret.trim())) throw new Error("Khi thay khóa, cần nhập cả API Key và Secret Key.");
      await exchangeRequest(token, editing ? `/connections/${editing}` : "/connections", editing ? "PUT" : "POST", {
        label: label.trim(), ...(apiKey.trim() ? { api_key: apiKey.trim(), api_secret: secret.trim() } : {}),
      });
      closeForm(); setNotice("Đã lưu kết nối. Bấm Cập nhật số dư để lưu lần đọc mới."); await load(token);
    });
  }

  return <main className={styles.page}>
    <Link href="/config" className={styles.back}>← Cấu hình</Link>
    <div className={styles.header}><div><h1>Ví & tài khoản sàn</h1><p>Theo dõi tiền đang giữ, tách riêng tài khoản sàn và địa chỉ blockchain.</p></div>
      {unlocked && <button disabled={!!busy} onClick={lock}>Khóa cấu hình</button>}
    </div>
    {error && <div role="alert" className={styles.error}>{error}</div>}
    {notice && <p role="status" className={styles.notice}>{notice}</p>}
    {!unlocked ? <section className={styles.card}>
      <h2>Mở quản lý kết nối</h2><p>Nhập mã quản trị do máy chủ cấu hình. Đây không phải API Key Binance.</p>
      <form onSubmit={e => { e.preventDefault(); void run("unlock", () => load(token)); }} className={styles.form}>
        <label>Mã quản trị<input type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)} required /></label>
        <button className={styles.primary} disabled={!!busy || !token}>{busy ? "Đang kiểm tra…" : "Mở kết nối"}</button>
      </form>
      <details><summary>Chưa có mã quản trị?</summary><p>Máy chủ cần cấu hình khóa mã hóa và mã quản trị trước khi lưu kết nối. Không nhập khóa Binance vào ô này. Mã quản trị chỉ được giữ trong bộ nhớ của trang, không lưu sau reload.</p></details>
    </section> : <>
      <section className={styles.card}>
        <div className={styles.header}><div><h2>Tài khoản sàn</h2><p>Binance: USDT trong Spot và Funding. Earn, Futures và Margin chưa thuộc phạm vi.</p></div>
          <div className={styles.actions}><button disabled={!!busy} onClick={() => void run("reload", () => load(token))}>Tải lại</button><button className={styles.primary} disabled={!!busy || !data?.secure_storage_ready} onClick={() => openForm()}>+ Thêm kết nối</button></div>
        </div>
        {!data?.secure_storage_ready && <p className={styles.error}>Chưa cấu hình khóa mã hóa phía máy chủ. Chưa thể lưu API Key/Secret.</p>}
        <div className={styles.providers}><span>Binance · Hỗ trợ</span><span>OKX · Chưa hỗ trợ</span><span>MEXC · Chưa hỗ trợ</span></div>
        {!data?.connections.length && <p className={styles.empty}>Chưa có tài khoản sàn được kết nối. Thêm Binance để bắt đầu đọc số dư.</p>}
      </section>

      {formOpen && <section className={styles.card} aria-label="Cấu hình Binance">
        <h2>{editing ? "Cấu hình kết nối Binance" : "Thêm kết nối Binance"}</h2>
        <p>Chỉ dùng khóa mới có quyền đọc. Không bật giao dịch, chuyển hoặc rút tiền.</p>
        <form className={styles.form} onSubmit={save}>
          <label>Nhà cung cấp<select disabled><option>Binance</option></select></label>
          <label>Tên kết nối<input value={label} maxLength={64} required onChange={e => setLabel(e.target.value)} /></label>
          <label>API Key<input type="password" autoComplete="off" value={apiKey} required={!editing} onChange={e => setApiKey(e.target.value)} /></label>
          <label>Secret Key<input type="password" autoComplete="new-password" value={secret} required={!editing} onChange={e => setSecret(e.target.value)} /></label>
          {editing && <p>Để trống cả hai ô khóa để giữ nguyên. Nhập đủ hai ô khi thay khóa.</p>}
          <div className={styles.actions}><button type="submit" className={styles.primary} disabled={!!busy}>{busy === "save" ? "Đang kiểm tra và lưu…" : editing ? "Lưu thay đổi" : "Kiểm tra và lưu"}</button><button type="button" disabled={!!busy} onClick={closeForm}>Hủy</button></div>
        </form>
      </section>}

      {data?.connections.map(c => <section className={styles.card} key={c.id}>
        <div className={styles.header}><div><h2>{c.label}</h2><p>Binance · {c.last_error ? "Cần kiểm tra" : c.last_ok_at ? "Đã đọc số dư" : "Đã lưu, chưa đọc số dư"}</p></div>
          <div className={styles.actions}><button className={styles.primary} disabled={!!busy} onClick={() => void run(`read-${c.id}`, async () => { await exchangeRequest(token, `/connections/${c.id}/read-balances`, "POST"); await load(token); setNotice("Đã cập nhật kết quả đọc. Kiểm tra trạng thái từng ví."); })}>{busy === `read-${c.id}` ? "Đang đọc…" : "Cập nhật số dư"}</button><button disabled={!!busy} onClick={() => openForm(c)}>Cấu hình</button></div>
        </div>
        {c.last_error && <p role="alert" className={styles.error}>{c.last_error}. Số dư bên dưới là lần đọc thành công gần nhất của từng ví.</p>}
        <div className={styles.grid}>{["spot", "funding"].map(wallet => {
          const balance = balances[c.id]?.find(b => b.wallet_type === wallet && b.asset === "USDT");
          const stale = !!balance && !!c.wallet_errors?.[wallet];
          return <article className={styles.balance} key={wallet}><h3>{wallet === "spot" ? "Spot" : "Funding"}</h3><p>USDT khả dụng</p><strong>{formatUsdt(balance?.free)} <small>USDT</small></strong>
            <p className={styles.muted}>{at(balance?.read_at ?? null)}{stale && " · Dữ liệu cũ"}</p>
            {c.wallet_errors?.[wallet] && <p className={styles.error}>{c.wallet_errors[wallet]}</p>}
            <dl><div><dt>Đang khóa</dt><dd>{formatUsdt(balance?.locked)}</dd></div><div><dt>Đóng băng</dt><dd>{formatUsdt(balance?.freeze)}</dd></div><div><dt>Đang rút</dt><dd>{formatUsdt(balance?.withdrawing)}</dd></div></dl>
          </article>;
        })}</div>
        <div className={styles.actions}><label className={styles.toggle}><input type="checkbox" checked={c.auto_sync} disabled={!!busy || !data.scheduler_enabled} onChange={e => { const enabled = e.target.checked; void run(`sync-${c.id}`, async () => { await exchangeRequest(token, `/connections/${c.id}`, "PUT", { auto_sync: enabled }); await load(token); }); }} /> Tự cập nhật</label>{!data.scheduler_enabled && <span className={styles.muted}>Lịch đồng bộ máy chủ đang tắt</span>}</div>
        <details onToggle={e => { if (e.currentTarget.open) void run(`history-${c.id}`, async () => { const result = await exchangeRequest<{history: History[]}>(token, `/connections/${c.id}/history?limit=5`); setHistory(old => ({...old, [c.id]: result.history})); }); }}>
          <summary>Lịch sử và quản lý kết nối</summary>
          <p>API Key kết thúc bằng {c.api_key_last4 || "—"}. Không hiển thị lại Secret Key.</p>
          {history[c.id]?.length ? <ul>{history[c.id].map(h => <li key={h.id}>{at(h.started_at)} · {h.status}{h.error_message ? ` · ${h.error_message}` : ""}</li>)}</ul> : <p>Chưa có lịch sử để hiển thị.</p>}
          {disconnecting === c.id ? <div className={styles.actions}><p>Ngắt kết nối và dừng đồng bộ? Lịch sử vẫn được giữ.</p><button className={styles.danger} disabled={!!busy} onClick={() => void run("disconnect", async () => { await exchangeRequest(token, `/connections/${c.id}`, "DELETE"); setDisconnecting(null); await load(token); })}>Xác nhận ngắt</button><button onClick={() => setDisconnecting(null)} disabled={!!busy}>Hủy</button></div> : <button className={styles.danger} disabled={!!busy} onClick={() => setDisconnecting(c.id)}>Ngắt kết nối</button>}
        </details>
      </section>)}
    </>}
    <section className={styles.card}><h2>Địa chỉ blockchain</h2><p>Địa chỉ nạp TRC20 được theo dõi riêng. Số dư tại địa chỉ nạp Binance không phải số dư tài khoản Binance.</p><Link href="/config#usdt-wallet">Xem kết nối TRC20 hiện có →</Link></section>
    <p className={styles.muted}>Không cộng số dư các kết nối có thể cùng một tài khoản. Chưa tự quy đổi hoặc đối soát ngân sách Sheets.</p>
  </main>;
}
