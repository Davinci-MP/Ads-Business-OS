"use client";

import { useCallback, useEffect, useState } from "react";
import { API_BASE, fetchJson, fmtTime, type AccountRow } from "../../lib/api";

type CustomerRef = { id: number; name: string };
type AccountRef = { id: number; name: string; meta_ad_account_id: string; status: string };

const TIMEZONES = ["Asia/Ho_Chi_Minh", "UTC", "America/Los_Angeles", "Europe/Moscow", "Asia/Dubai", "Asia/Karachi"];

export default function AccountsPage() {
  const [rows, setRows] = useState<AccountRow[] | null>(null);
  const [customers, setCustomers] = useState<CustomerRef[]>([]);
  const [accounts, setAccounts] = useState<AccountRef[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const [assignAccountId, setAssignAccountId] = useState("");
  const [assignCustomerId, setAssignCustomerId] = useState("");
  const [assignFrom, setAssignFrom] = useState("");
  const [transferAccountId, setTransferAccountId] = useState("");
  const [transferCustomerId, setTransferCustomerId] = useState("");
  const [replaceOldId, setReplaceOldId] = useState("");
  const [newMetaId, setNewMetaId] = useState("");
  const [newName, setNewName] = useState("");
  const [newTz, setNewTz] = useState(TIMEZONES[0]);
  const [newBm, setNewBm] = useState("");
  const [costAccountId, setCostAccountId] = useState("");
  const [cost, setCost] = useState("");
  const [restrictId, setRestrictId] = useState("");
  const [newCustomerName, setNewCustomerName] = useState("");
  const [newCustomerChatId, setNewCustomerChatId] = useState("");
  const [createActId, setCreateActId] = useState("");
  const [createName, setCreateName] = useState("");
  const [createBm, setCreateBm] = useState("");
  const [query, setQuery] = useState("");
  const [customerFilter, setCustomerFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const load = useCallback(async () => {
    try {
      const [accountRows, customerRows, accountRefs] = await Promise.all([
        fetchJson<AccountRow[]>("/dashboard/accounts"),
        fetchJson<CustomerRef[]>("/customers"),
        fetchJson<AccountRef[]>("/ad-accounts"),
      ]);
      setRows(accountRows);
      setCustomers(customerRows);
      setAccounts(accountRefs);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void load();
    setCustomerFilter(new URLSearchParams(window.location.search).get("customerId") ?? "");
  }, [load]);

  const act = async (path: string, body: unknown, okMsg: string) => {
    setBusy(true);
    setNotice(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error((await res.text()) || `HTTP ${res.status}`);
      setNotice({ ok: true, text: okMsg });
      await load();
      return true;
    } catch (e) {
      setNotice({ ok: false, text: `Lỗi: ${e instanceof Error ? e.message : String(e)}` });
      return false;
    } finally {
      setBusy(false);
    }
  };

  const readOnly = rows === null && !error;
  const transferAccount = rows?.find((row) => String(row.account_id) === transferAccountId);
  const transferCustomer = customers.find((customer) => String(customer.id) === transferCustomerId);
  const visibleRows = (rows ?? []).filter((row) => {
    const text = `${row.meta_ad_account_id} ${row.name} ${row.customer_name ?? ""}`.toLocaleLowerCase("vi");
    return text.includes(query.trim().toLocaleLowerCase("vi"))
      && (!customerFilter || String(row.customer_id) === customerFilter)
      && (!statusFilter || row.status === statusFilter);
  });

  return (
    <main className="page">
      <h1>Tài khoản quảng cáo</h1>
      {readOnly && <p className="loading">Đang tải dữ liệu từ DB…</p>}
      {error && <p className="error-box">Không đọc được dữ liệu: {error}</p>}
      {rows && (
        <>
          <div className="status-form">
            <label>
              Thêm khách hàng
              <input
                value={newCustomerName}
                onChange={(e) => setNewCustomerName(e.target.value)}
                placeholder="VD: KH Alpha"
              />
            </label>
            <label>
              Telegram chat id (tuỳ chọn)
              <input
                value={newCustomerChatId}
                onChange={(e) => setNewCustomerChatId(e.target.value)}
                placeholder="VD: 123456789"
              />
            </label>
            <button
              disabled={busy || !newCustomerName.trim()}
              onClick={() =>
                void act(
                  "/customers",
                  { name: newCustomerName.trim(), telegram_chat_id: newCustomerChatId || null },
                  `Đã tạo khách ${newCustomerName.trim()}.`,
                )
              }
            >
              Tạo khách
            </button>

            <label>
              Thêm ad account (Act ID)
              <input
                value={createActId}
                onChange={(e) => setCreateActId(e.target.value)}
                placeholder="act_..."
              />
            </label>
            <label>
              Tên account
              <input value={createName} onChange={(e) => setCreateName(e.target.value)} placeholder="VD: Acc chính" />
            </label>
            <label>
              BM ID
              <input value={createBm} onChange={(e) => setCreateBm(e.target.value)} placeholder="bm_... (tuỳ chọn)" />
            </label>
            <button
              disabled={busy || !createActId.trim()}
              onClick={async () => {
                const created = await act(
                  "/ad-accounts",
                  {
                    meta_ad_account_id: createActId.trim(),
                    name: createName.trim(),
                    timezone_name: newTz,
                    business_manager_id: createBm || null,
                  },
                  `Đã thêm account ${createActId.trim()}.`,
                );
                if (created) {
                  setCreateActId("");
                  setCreateName("");
                  setCreateBm("");
                }
              }}
            >
              Thêm account
            </button>
          </div>
          <div className="status-form">
            <label>
              Đánh dấu hạn chế thủ công
              <select value={restrictId} onChange={(e) => setRestrictId(e.target.value)}>
                <option value="">— account —</option>
                {accounts.filter((a) => a.status === "ACTIVE").map((a) =>
                  <option key={a.id} value={a.id}>{a.meta_ad_account_id}</option>)}
              </select>
            </label>
            <button disabled={busy || !restrictId}
              onClick={() => void act(`/accounts/${restrictId}/restrict`, {}, "Đã đánh dấu hạn chế trong DB nội bộ.")}>
              Đánh dấu hạn chế
            </button>
            <label>
              Gán account → khách
              <select value={assignAccountId} onChange={(e) => setAssignAccountId(e.target.value)}>
                <option value="">— account —</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.meta_ad_account_id} ({a.status})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Khách
              <select value={assignCustomerId} onChange={(e) => setAssignCustomerId(e.target.value)}>
                <option value="">— khách —</option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </label>
            <label>
              Hiệu lực từ (giờ thiết bị; để trống là hiện tại)
              <input type="datetime-local" value={assignFrom} onChange={(e) => setAssignFrom(e.target.value)} />
            </label>
            <button
              disabled={busy || !assignAccountId || !assignCustomerId}
              onClick={() =>
                void act(
                  "/accounts/assign",
                  { ad_account_id: Number(assignAccountId), customer_id: Number(assignCustomerId),
                    valid_from: assignFrom ? new Date(assignFrom).toISOString() : null },
                  "Đã gán account cho khách.",
                )
              }
            >
              Gán
            </button>

            <label>
              Chuyển TKQC đang phân công
              <select value={transferAccountId} onChange={(e) => setTransferAccountId(e.target.value)}>
                <option value="">— account —</option>
                {rows.filter((row) => row.assignment_status === "ASSIGNED" && row.status === "ACTIVE"
                  && row.current_assignment_id !== null).map((row) =>
                  <option key={row.account_id} value={row.account_id}>{row.meta_ad_account_id} · {row.customer_name}</option>)}
              </select>
            </label>
            <label>
              Khách nhận
              <select value={transferCustomerId} onChange={(e) => setTransferCustomerId(e.target.value)}>
                <option value="">— khách nhận —</option>
                {customers.filter((c) => c.id !== transferAccount?.customer_id).map((c) =>
                  <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </label>
            <button disabled={busy || !transferAccount?.current_assignment_id || !transferCustomer
              || transferCustomer.id === transferAccount.customer_id}
              onClick={() => {
                if (!transferAccount?.current_assignment_id || !transferCustomer) return;
                if (!window.confirm(`Chuyển ${transferAccount.meta_ad_account_id} từ ${transferAccount.customer_name} sang ${transferCustomer.name}, hiệu lực ngay?`)) return;
                void act("/accounts/transfer", {
                  ad_account_id: transferAccount.account_id,
                  customer_id: transferCustomer.id,
                  expected_assignment_id: transferAccount.current_assignment_id,
                }, "Đã chuyển account; lịch sử phân công được giữ.");
              }}>
              Chuyển ngay
            </button>

            <label>
              Thay account bị hạn chế
              <select value={replaceOldId} onChange={(e) => setReplaceOldId(e.target.value)}>
                <option value="">— account cũ —</option>
                {accounts
                  .filter((a) => a.status === "ACTIVE" || a.status === "RESTRICTED")
                  .map((a) => (
                    <option key={a.id} value={a.id}>{a.meta_ad_account_id}</option>
                  ))}
              </select>
            </label>
            <label>
              Account mới (Act ID)
              <input value={newMetaId} onChange={(e) => setNewMetaId(e.target.value)} placeholder="act_..." />
            </label>
            <label>
              Tên
              <input value={newName} onChange={(e) => setNewName(e.target.value)} />
            </label>
            <label>
              Múi giờ
              <select value={newTz} onChange={(e) => setNewTz(e.target.value)}>
                {TIMEZONES.map((tz) => (
                  <option key={tz}>{tz}</option>
                ))}
              </select>
            </label>
            <label>
              BM ID (tuỳ chọn)
              <input value={newBm} onChange={(e) => setNewBm(e.target.value)} placeholder="bm_..." />
            </label>
            <button
              disabled={busy || !replaceOldId || !newMetaId}
              onClick={() =>
                void act(
                  "/accounts/replace",
                  {
                    old_account_id: Number(replaceOldId),
                    new_meta_ad_account_id: newMetaId,
                    new_name: newName,
                    new_timezone_name: newTz,
                    new_business_manager_id: newBm || null,
                  },
                  "Đã thay account; lịch sử giữ nguyên.",
                )
              }
            >
              Thay thế
            </button>

            <label>
              Chi phí mua cũ (chỉ lưu số; chưa có đơn vị)
              <input
                value={cost}
                onChange={(e) => setCost(e.target.value)}
                placeholder="VD: 150.75"
                inputMode="decimal"
              />
            </label>
            <label>
              Cho account
              <select value={costAccountId} onChange={(e) => setCostAccountId(e.target.value)}>
                <option value="">— account —</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>{a.meta_ad_account_id}</option>
                ))}
              </select>
            </label>
            <button
              disabled={busy || !costAccountId || !cost}
              onClick={() => void act(`/accounts/${costAccountId}/purchase-cost`, { cost }, "Đã lưu chi phí mua.")}
            >
              Lưu chi phí
            </button>
          </div>
          {notice && <p className={`notice ${notice.ok ? "ok" : "err"}`}>{notice.text}</p>}

          <div className="status-form">
            <label>Tìm ID, tên TKQC hoặc khách<input value={query} onChange={(e) => setQuery(e.target.value)} /></label>
            <label>Khách được phân công
              <select value={customerFilter} onChange={(e) => setCustomerFilter(e.target.value)}>
                <option value="">Tất cả khách</option>
                {customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </label>
            <label>Trạng thái nội bộ
              <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="">Tất cả</option><option value="ACTIVE">Mặc định ACTIVE</option>
                <option value="RESTRICTED">RESTRICTED</option><option value="REPLACED">REPLACED</option><option value="DEAD">DEAD</option>
              </select>
            </label>
          </div>
          <div style={{ overflowX: "auto" }}><table>
            <thead>
              <tr>
                <th>Act ID</th>
                <th>Tên</th>
                <th>BM đã lưu</th>
                <th>BM tiếp nhận</th>
                <th>Tiền tệ TKQC</th>
                <th>Múi giờ</th>
                <th>Trạng thái nội bộ hiện tại</th>
                <th>Phân công hiện tại</th>
                <th>Chi phí mua cũ</th>
                <th>Giá TKQC thu khách</th>
                <th>Dư nợ Meta bàn giao</th>
                <th>Khách đã trả cho mình</th>
                <th>Mình đã trả nhà cung cấp / Meta</th>
                <th>Cập nhật trạng thái</th>
                <th>Thay thế bằng</th>
                <th>Lịch sử gán</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((r) => (
                <tr key={r.account_id}>
                  <td>{r.meta_ad_account_id}</td>
                  <td>{r.name}</td>
                  <td className="muted">{r.business_manager_id ?? "—"}</td>
                  <td>Chưa cập nhật</td>
                  <td>Chưa cập nhật</td>
                  <td>{r.timezone_name}</td>
                  <td>
                    <span className={`tag ${r.status === "ACTIVE" ? "" : r.status === "RESTRICTED" ? "bad" : r.status === "REPLACED" ? "warn" : "bad"}`}>
                      {r.status === "ACTIVE" ? "Chưa cập nhật (mặc định ACTIVE)" : r.status}
                    </span>
                  </td>
                  <td>{r.assignment_status === "CONFLICT" ? "Xung đột phân công" : r.customer_name ?? "Chưa phân công"}</td>
                  <td>{r.purchase_cost == null ? "Chưa nhập" : `${r.purchase_cost} · chưa xác định đơn vị`}</td>
                  <td>Chưa nhập</td>
                  <td>Chưa nhập</td>
                  <td>Chưa cập nhật</td>
                  <td>Chưa cập nhật</td>
                  <td>{r.status === "RESTRICTED" && r.restricted_at ? fmtTime(r.restricted_at) : "Chưa có thời điểm"}</td>
                  <td className="muted">{r.replaced_by ?? "—"}</td>
                  <td className="muted">
                    {r.assignment_history.map((h, i) => (
                      <div key={i} style={{ fontSize: 11 }}>
                        {h.customer_name ?? `#${h.customer_id}`}: {h.valid_from?.slice(0, 10)}
                        {h.valid_to ? ` → ${h.valid_to.slice(0, 10)}` : " →"}
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
              {visibleRows.length === 0 && (
                <tr><td colSpan={16} className="muted">Không có TKQC phù hợp.</td></tr>
              )}
            </tbody>
          </table></div>
          <p className="notice muted">
            Trạng thái nội bộ không phải Meta live. Chi phí cũ chưa có đơn vị; không suy ra tiền tệ hay tình trạng thanh toán.
            Ghi chỉ vào DB nội bộ (có audit log), không ghi Google Sheets; lịch sử được giữ lại.
          </p>
        </>
      )}
    </main>
  );
}
