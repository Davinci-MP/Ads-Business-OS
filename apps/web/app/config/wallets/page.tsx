"use client";

import Link from "next/link";
import { FormEvent, useRef, useState } from "react";
import {
  Balance,
  ConnectionsResult,
  ExchangeConnection,
  History,
  VirtualCard,
  exchangeRequest,
  formatUsdt,
} from "../../../lib/exchange-api";
import styles from "./wallets.module.css";

const at = (value: string | null) =>
  value ? new Date(value).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" }) : "Chưa cập nhật";
const message = (error: unknown) =>
  error instanceof Error ? error.message : "Không kết nối được máy chủ. Vui lòng thử lại.";

export default function WalletsPage() {
  const [token, setToken] = useState("");
  const [unlocked, setUnlocked] = useState(false);
  const [data, setData] = useState<ConnectionsResult | null>(null);
  const [balances, setBalances] = useState<Record<number, Balance[]>>({});
  const [cards, setCards] = useState<Record<number, VirtualCard[]>>({});
  const [history, setHistory] = useState<Record<number, History[]>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // Modal / Form state
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [provider, setProvider] = useState<"binance" | "pingpong">("binance");
  const [label, setLabel] = useState("Binance chính");
  const [apiKey, setApiKey] = useState("");
  const [secret, setSecret] = useState("");
  const [accountId, setAccountId] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [disconnecting, setDisconnecting] = useState<number | null>(null);
  const generation = useRef(0);

  async function load(auth: string) {
    const version = generation.current;
    const next = await exchangeRequest<ConnectionsResult>(auth, "/connections");

    const balanceEntries = await Promise.all(
      next.connections.map(async (c) => {
        const result = await exchangeRequest<{ snapshots: Balance[] }>(
          auth,
          `/connections/${c.id}/snapshots?limit=50`
        );
        return [c.id, result.snapshots] as const;
      })
    );

    const cardEntries = await Promise.all(
      next.connections.map(async (c) => {
        if (c.provider === "pingpong") {
          const result = await exchangeRequest<{ cards: VirtualCard[] }>(
            auth,
            `/connections/${c.id}/cards?limit=50`
          );
          return [c.id, result.cards] as const;
        }
        return [c.id, [] as VirtualCard[]] as const;
      })
    );

    if (generation.current !== version) return;
    setData(next);
    setBalances(Object.fromEntries(balanceEntries));
    setCards(Object.fromEntries(cardEntries));
    setUnlocked(true);
  }

  async function run(key: string, action: () => Promise<void>) {
    if (busy) return;
    setBusy(key);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy("");
    }
  }

  function closeForm() {
    setFormOpen(false);
    setApiKey("");
    setSecret("");
    setAccountId("");
    setBaseUrl("");
    setEditing(null);
  }

  function lock() {
    generation.current++;
    setUnlocked(false);
    setToken("");
    setData(null);
    setBalances({});
    setCards({});
    setHistory({});
    closeForm();
    setError("");
    setNotice("");
  }

  function openForm(connection?: ExchangeConnection, defaultProv: "binance" | "pingpong" = "binance") {
    setEditing(connection?.id ?? null);
    const prov = (connection?.provider as "binance" | "pingpong") || defaultProv;
    setProvider(prov);
    setLabel(connection?.label ?? (prov === "pingpong" ? "PingPong chính" : "Binance chính"));
    setApiKey("");
    setSecret("");
    setAccountId(connection?.account_id ?? "");
    setBaseUrl(connection?.base_url ?? "");
    setFormOpen(true);
    setError("");
    setNotice("");
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    await run("save", async () => {
      if ((apiKey.trim() && !secret.trim()) || (!apiKey.trim() && secret.trim())) {
        throw new Error("Khi thay khóa, cần nhập đủ cả Khóa truy cập (API Key/Client ID) và Khóa bí mật (Secret).");
      }
      const body: Record<string, unknown> = {
        provider,
        label: label.trim(),
        ...(apiKey.trim() ? { api_key: apiKey.trim(), api_secret: secret.trim() } : {}),
      };
      if (provider === "pingpong") {
        if (accountId.trim()) body.account_id = accountId.trim();
        body.base_url = baseUrl.trim() || "https://gateway.pingpongx.com";
      }
      await exchangeRequest(
        token,
        editing ? `/connections/${editing}` : "/connections",
        editing ? "PUT" : "POST",
        body
      );
      closeForm();
      setNotice("Đã lưu kết nối. Bấm 'Cập nhật số dư' để đồng bộ dữ liệu mới nhất.");
      await load(token);
    });
  }

  return (
    <main className={styles.page}>
      <Link href="/config" className={styles.back}>
        ← Cấu hình
      </Link>
      <div className={styles.header}>
        <div>
          <h1>Ví & tài khoản nguồn tiền</h1>
          <p>Theo dõi tiền đang giữ, quản lý tài khoản sàn Binance và cổng thanh toán PingPong VCC.</p>
        </div>
        {unlocked && (
          <button disabled={!!busy} onClick={lock}>
            Khóa cấu hình
          </button>
        )}
      </div>

      {error && (
        <div role="alert" className={styles.error}>
          {error}
        </div>
      )}
      {notice && (
        <p role="status" className={styles.notice}>
          {notice}
        </p>
      )}

      {!unlocked ? (
        <section className={styles.card}>
          <h2>Mở quản lý kết nối</h2>
          <p>Nhập mã quản trị do máy chủ cấu hình. Mã này chỉ lưu tạm trong phiên làm việc trình duyệt.</p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void run("unlock", () => load(token));
            }}
            className={styles.form}
          >
            <label>
              Mã quản trị
              <input
                type="password"
                autoComplete="off"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                required
              />
            </label>
            <button className={styles.primary} disabled={!!busy || !token}>
              {busy ? "Đang kiểm tra…" : "Mở kết nối"}
            </button>
          </form>
          <details>
            <summary>Chưa có mã quản trị?</summary>
            <p>
              Máy chủ cần cấu hình khóa mã hóa (Fernet) và mã quản trị (X-Adsos-Wallet-Token) trước khi lưu kết
              nối. Không nhập API Key/Secret của Binance hay PingPong vào ô này.
            </p>
          </details>
        </section>
      ) : (
        <>
          <section className={styles.card}>
            <div className={styles.header}>
              <div>
                <h2>Tài khoản sàn & nguồn tiền kết nối</h2>
                <p>Binance (Spot, Funding USDT) và PingPong (Nguồn tiền đa tệ, Thẻ ảo Commercial VCC).</p>
              </div>
              <div className={styles.actions}>
                <button disabled={!!busy} onClick={() => void run("reload", () => load(token))}>
                  Tải lại
                </button>
                <button
                  className={styles.primary}
                  disabled={!!busy || !data?.secure_storage_ready}
                  onClick={() => openForm(undefined, "binance")}
                >
                  + Thêm kết nối
                </button>
              </div>
            </div>
            {!data?.secure_storage_ready && (
              <p className={styles.error}>
                Chưa cấu hình khóa mã hóa phía máy chủ (ADSOS_EXCHANGE_MASTER_KEY). Chưa thể lưu khóa mới.
              </p>
            )}
            <div className={styles.providers}>
              <span className={styles.activeProvider}>Binance · Hỗ trợ</span>
              <span className={styles.activeProvider}>PingPong · Hỗ trợ (VCC & Nguồn tiền)</span>
              <span>OKX · Chưa hỗ trợ</span>
              <span>MEXC · Chưa hỗ trợ</span>
            </div>
            {!data?.connections.length && (
              <p className={styles.empty}>
                Chưa có tài khoản nào được kết nối. Bấm &quot;+ Thêm kết nối&quot; để thêm Binance hoặc PingPong.
              </p>
            )}
          </section>

          {formOpen && (
            <section
              className={styles.card}
              aria-label={editing ? `Sửa kết nối ${label}` : "Thêm kết nối mới"}
            >
              <h2>{editing ? `Cấu hình kết nối ${label}` : "Thêm kết nối mới"}</h2>
              <p>Chỉ dùng khóa có quyền đọc (Read-Only). Nghiêm cấm cấp quyền giao dịch, rút tiền hoặc tạo thẻ.</p>
              <form className={styles.form} onSubmit={save}>
                <label>
                  Nhà cung cấp
                  <select
                    disabled={!!editing}
                    value={provider}
                    onChange={(e) => {
                      const p = e.target.value as "binance" | "pingpong";
                      setProvider(p);
                      setLabel(p === "pingpong" ? "PingPong chính" : "Binance chính");
                    }}
                  >
                    <option value="binance">Binance (Spot + Funding)</option>
                    <option value="pingpong">PingPong (Nguồn tiền & Thẻ ảo VCC)</option>
                  </select>
                </label>
                <label>
                  Tên kết nối
                  <input
                    value={label}
                    maxLength={64}
                    required
                    onChange={(e) => setLabel(e.target.value)}
                  />
                </label>

                {provider === "binance" ? (
                  <>
                    <label>
                      API Key
                      <input
                        type="password"
                        autoComplete="off"
                        value={apiKey}
                        required={!editing}
                        placeholder={editing ? "Để trống nếu không đổi" : "Nhập Binance API Key"}
                        onChange={(e) => setApiKey(e.target.value)}
                      />
                    </label>
                    <label>
                      Secret Key
                      <input
                        type="password"
                        autoComplete="new-password"
                        value={secret}
                        required={!editing}
                        placeholder={editing ? "Để trống nếu không đổi" : "Nhập Binance Secret Key"}
                        onChange={(e) => setSecret(e.target.value)}
                      />
                    </label>
                  </>
                ) : (
                  <>
                    <label>
                      App ID (Issuing 2.7.1)
                      <input
                        type="password"
                        autoComplete="off"
                        value={apiKey}
                        required={!editing}
                        placeholder={editing ? "Để trống nếu không đổi" : "Nhập App ID được PingPong cấp"}
                        onChange={(e) => setApiKey(e.target.value)}
                      />
                    </label>
                    <label>
                      App Secret
                      <input
                        type="password"
                        autoComplete="new-password"
                        value={secret}
                        required={!editing}
                        placeholder={editing ? "Để trống nếu không đổi" : "Nhập App Secret được PingPong cấp"}
                        onChange={(e) => setSecret(e.target.value)}
                      />
                    </label>
                    <p className={styles.muted}>
                      Dùng App ID/App Secret của Issuing, không dùng Merchant ID. Ứng dụng chỉ đọc số dư và thẻ;
                      API không cung cấp bằng chứng xác minh quyền chỉ đọc của khóa. Cấu hình IP whitelist tại PingPong.
                    </p>
                    <label>
                      Base URL (Tùy chọn)
                      <input
                        value={baseUrl}
                        placeholder="https://gateway.pingpongx.com"
                        onChange={(e) => setBaseUrl(e.target.value)}
                      />
                    </label>
                  </>
                )}

                {editing && <p className={styles.muted}>Để trống cả hai ô khóa để giữ nguyên khóa hiện tại.</p>}

                <div className={styles.actions}>
                  <button type="submit" className={styles.primary} disabled={!!busy}>
                    {busy === "save"
                      ? "Đang xác minh & lưu…"
                      : editing
                      ? "Lưu thay đổi"
                      : "Kiểm tra và lưu kết nối"}
                  </button>
                  <button type="button" disabled={!!busy} onClick={closeForm}>
                    Hủy
                  </button>
                </div>
              </form>
            </section>
          )}

          {data?.connections.map((c) => {
            const isPingPong = c.provider === "pingpong";
            const connectionCards = cards[c.id] || [];

            // Thu thập balances theo asset
            const connSnapshots = balances[c.id] || [];
            // Lấy snapshot mới nhất cho mỗi asset
            const latestByAsset: Record<string, Balance> = {};
            for (const snap of connSnapshots) {
              const key = `${snap.wallet_type}-${snap.asset}`;
              if (!latestByAsset[key]) {
                latestByAsset[key] = snap;
              }
            }

            return (
              <section className={styles.card} key={c.id}>
                <div className={styles.header}>
                  <div>
                    <h2>{c.label}</h2>
                    <p>
                      {isPingPong ? "PingPong (Nguồn tiền & Thẻ ảo VCC)" : "Binance (Spot & Funding)"} ·{" "}
                      {c.last_error
                        ? "Cần kiểm tra lại kết nối"
                        : c.last_ok_at
                        ? "Đã kết nối thành công"
                        : "Đã lưu, chưa đọc số dư"}
                    </p>
                  </div>
                  <div className={styles.actions}>
                    <button
                      className={styles.primary}
                      disabled={!!busy}
                      onClick={() =>
                        void run(`read-${c.id}`, async () => {
                          await exchangeRequest(token, `/connections/${c.id}/read-balances`, "POST");
                          await load(token);
                          setNotice("Đã cập nhật số dư thành công.");
                        })
                      }
                    >
                      {busy === `read-${c.id}` ? "Đang đọc…" : "Cập nhật số dư"}
                    </button>
                    <button disabled={!!busy} onClick={() => openForm(c)}>
                      Cấu hình
                    </button>
                  </div>
                </div>

                {c.last_error && (
                  <p role="alert" className={styles.error}>
                    {c.last_error}. Số dư hiển thị bên dưới là lần đọc thành công gần nhất.
                  </p>
                )}

                {/* ===================== GIAO DIỆN PINGPONG ===================== */}
                {isPingPong ? (
                  <>
                    {/* 1. Nguồn tiền PingPong (Balances) */}
                    <div className={styles.sectionTitle}>
                      <span></span> Nguồn tiền PingPong (Balances)
                    </div>
                    {Object.keys(latestByAsset).length === 0 ? (
                      <p className={styles.empty}>Chưa có dữ liệu số dư. Bấm &quot;Cập nhật số dư&quot; để đọc số dư mới nhất.</p>
                    ) : (
                      <div className={styles.grid}>
                        {Object.values(latestByAsset).map((b) => {
                          return (
                            <article className={styles.balance} key={`${b.wallet_type}-${b.asset}`}>
                              <h3>Ví {b.asset}</h3>
                              <p>Số dư khả dụng</p>
                              <strong>
                                {formatUsdt(b.free)} <small>{b.asset}</small>
                              </strong>
                              <p className={styles.muted}>{at(b.read_at)}</p>
                              <dl>
                                <div>
                                  <dt>Tạm giữ / Chờ xử lý</dt>
                                  <dd>{formatUsdt(b.locked)} {b.asset}</dd>
                                </div>
                              </dl>
                            </article>
                          );
                        })}
                      </div>
                    )}

                    {/* 2. Danh sách Thẻ ảo / VCC (Cards) */}
                    <div className={styles.sectionTitle}>
                      <span></span> Danh sách Thẻ ảo / VCC (Virtual Cards)
                    </div>
                    {connectionCards.length === 0 ? (
                      <p className={styles.empty}>Chưa có thẻ ảo nào được tìm thấy hoặc chưa đồng bộ.</p>
                    ) : (
                      <div className={styles.tableWrapper}>
                        <table className={styles.table}>
                          <thead>
                            <tr>
                              <th>Tên thẻ / Chủ thẻ</th>
                              <th>4 số cuối</th>
                              <th>Tiền tệ</th>
                              <th>Trạng thái thẻ</th>
                              <th>Hạn mức chi tiêu</th>
                              <th>Số dư khả dụng</th>
                            </tr>
                          </thead>
                          <tbody>
                            {connectionCards.map((card) => {
                              const badgeClass =
                                card.status === "ACTIVE"
                                  ? styles.badgeActive
                                  : card.status === "FROZEN"
                                  ? styles.badgeFrozen
                                  : card.status === "CLOSED"
                                  ? styles.badgeClosed
                                  : styles.badgeOther;

                              return (
                                <tr key={card.card_id}>
                                  <td>
                                    <strong>{card.card_name || card.card_id}</strong>
                                    {card.card_name && card.card_name !== card.card_id && (
                                      <div className={styles.muted}>{card.card_id}</div>
                                    )}
                                  </td>
                                  <td>
                                    <code>**** {card.last4}</code>
                                  </td>
                                  <td>{card.currency}</td>
                                  <td>
                                    <span className={`${styles.badge} ${badgeClass}`}>
                                      {card.status === "ACTIVE"
                                        ? "Hoạt động"
                                        : card.status === "FROZEN"
                                        ? "Tạm khóa"
                                        : card.status === "CLOSED"
                                        ? "Đã đóng"
                                        : card.status}
                                    </span>
                                  </td>
                                  <td>{card.spending_limit ? `${formatUsdt(card.spending_limit)} ${card.currency}` : "Không giới hạn"}</td>
                                  <td>
                                    <strong>{card.available_balance ? `${formatUsdt(card.available_balance)} ${card.currency}` : "—"}</strong>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </>
                ) : (
                  /* ===================== GIAO DIỆN BINANCE ===================== */
                  <div className={styles.grid}>
                    {["spot", "funding"].map((wallet) => {
                      const balance = (balances[c.id] || []).find(
                        (b) => b.wallet_type === wallet && b.asset === "USDT"
                      );
                      const stale = !!balance && !!c.wallet_errors?.[wallet];
                      return (
                        <article className={styles.balance} key={wallet}>
                          <h3>{wallet === "spot" ? "Ví Spot" : "Ví Funding"}</h3>
                          <p>USDT khả dụng</p>
                          <strong>
                            {formatUsdt(balance?.free)} <small>USDT</small>
                          </strong>
                          <p className={styles.muted}>
                            {at(balance?.read_at ?? null)}
                            {stale && " · Dữ liệu cũ"}
                          </p>
                          {c.wallet_errors?.[wallet] && (
                            <p className={styles.error}>{c.wallet_errors[wallet]}</p>
                          )}
                          <dl>
                            <div>
                              <dt>Đang khóa</dt>
                              <dd>{formatUsdt(balance?.locked)}</dd>
                            </div>
                            <div>
                              <dt>Đóng băng</dt>
                              <dd>{formatUsdt(balance?.freeze)}</dd>
                            </div>
                            <div>
                              <dt>Đang rút</dt>
                              <dd>{formatUsdt(balance?.withdrawing)}</dd>
                            </div>
                          </dl>
                        </article>
                      );
                    })}
                  </div>
                )}

                <div className={styles.actions}>
                  <label className={styles.toggle}>
                    <input
                      type="checkbox"
                      checked={c.auto_sync}
                      disabled={!!busy || !data.scheduler_enabled}
                      onChange={(e) => {
                        const enabled = e.target.checked;
                        void run(`sync-${c.id}`, async () => {
                          await exchangeRequest(token, `/connections/${c.id}`, "PUT", {
                            auto_sync: enabled,
                          });
                          await load(token);
                        });
                      }}
                    />{" "}
                    Tự cập nhật định kỳ
                  </label>
                  {!data.scheduler_enabled && (
                    <span className={styles.muted}>Lịch đồng bộ máy chủ đang tắt</span>
                  )}
                </div>

                <details
                  onToggle={(e) => {
                    if (e.currentTarget.open) {
                      void run(`history-${c.id}`, async () => {
                        const res = await exchangeRequest<{ history: History[] }>(
                          token,
                          `/connections/${c.id}/history?limit=5`
                        );
                        setHistory((old) => ({ ...old, [c.id]: res.history }));
                      });
                    }
                  }}
                >
                  <summary>Lịch sử đồng bộ & Quản lý</summary>
                  <p>Khóa truy cập kết thúc bằng: {c.api_key_last4 || "—"}. Secret Key được mã hóa tuyệt đối.</p>
                  {c.account_id && <p>Account ID: {c.account_id}</p>}
                  {history[c.id]?.length ? (
                    <ul>
                      {history[c.id].map((h) => (
                        <li key={h.id}>
                          {at(h.started_at)} · {h.status}
                          {h.error_message ? ` · ${h.error_message}` : ""}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>Chưa có lịch sử đồng bộ để hiển thị.</p>
                  )}
                  {disconnecting === c.id ? (
                    <div className={styles.actions}>
                      <p>Ngắt kết nối và dừng đồng bộ? Dữ liệu lịch sử vẫn được bảo toàn.</p>
                      <button
                        className={styles.danger}
                        disabled={!!busy}
                        onClick={() =>
                          void run("disconnect", async () => {
                            await exchangeRequest(token, `/connections/${c.id}`, "DELETE");
                            setDisconnecting(null);
                            await load(token);
                          })
                        }
                      >
                        Xác nhận ngắt
                      </button>
                      <button onClick={() => setDisconnecting(null)} disabled={!!busy}>
                        Hủy
                      </button>
                    </div>
                  ) : (
                    <button
                      className={styles.danger}
                      disabled={!!busy}
                      onClick={() => setDisconnecting(c.id)}
                    >
                      Ngắt kết nối
                    </button>
                  )}
                </details>
              </section>
            );
          })}
        </>
      )}

      <section className={styles.card}>
        <h2>Địa chỉ blockchain</h2>
        <p>Địa chỉ nạp TRC20 được theo dõi riêng. Số dư tại địa chỉ nạp Binance không phải số dư tài khoản Binance.</p>
        <Link href="/config#usdt-wallet">Xem kết nối TRC20 hiện có →</Link>
      </section>
      <p className={styles.muted}>
        Không cộng số dư các kết nối có thể cùng một tài khoản. Chưa tự quy đổi hoặc đối soát ngân sách Sheets.
      </p>
    </main>
  );
}
