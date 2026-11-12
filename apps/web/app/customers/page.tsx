"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { useAdminData } from "../../components/admin-data";
import { Empty, ErrorNotice, Metric, Modal, PageHeading, Pagination, useToast } from "../../components/admin-ui";
import { deleteJson, patchJson, postJson, putJson } from "../../lib/api";
import { sumMoney, moneyText } from "../../lib/admin-utils.mjs";
import type { Customer } from "../../types/admin";

type SavedCustomer = { customer_id: number };

export default function CustomersPage() {
  const { data, loading, errors, reload } = useAdminData();
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [view, setView] = useState("table");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [editing, setEditing] = useState<Customer | "new" | null>(null);
  const [deleting, setDeleting] = useState<Customer | null>(null);
  const [name, setName] = useState("");
  const [telegram, setTelegram] = useState("");
  const [chat, setChat] = useState("");
  const [fee, setFee] = useState("4");
  const [sheetUrl, setSheetUrl] = useState("");
  const [sheetTab, setSheetTab] = useState("");
  const [syncTime, setSyncTime] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => setSearch(new URLSearchParams(window.location.search).get("q") || ""), []);
  useEffect(() => setPage(1), [search, size]);
  const rows = data.customers.filter(customer =>
    `${customer.name} ${customer.telegram_username || ""} ${customer.telegram_chat_id || ""}`
      .toLowerCase().includes(search.toLowerCase()),
  );
  const accountsFor = (id: number) => data.accounts.filter(account => account.customer_id === id);
  const spendFor = (id: number) => {
    const groups = new Map<string, (string | number)[]>();
    for (const account of accountsFor(id)) {
      const values = groups.get(account.currency) || [];
      values.push(account.total_spend);
      groups.set(account.currency, values);
    }
    return [...groups].map(([currency, values]) => moneyText(sumMoney(values), currency)).join(" · ") || "Chưa có dữ liệu";
  };
  const open = (customer: Customer | "new") => {
    setEditing(customer);
    setName(customer === "new" ? "" : customer.name);
    setTelegram(customer === "new" ? "" : customer.telegram_username || "");
    setChat(customer === "new" ? "" : customer.telegram_chat_id || "");
    let defaultFee = "4";
    try { defaultFee = localStorage.getItem("adsos.new-customer-fee") || "4"; } catch { /* trình duyệt chặn lưu cục bộ */ }
    setFee(customer === "new" ? defaultFee : String(Number(customer.fee_rate) * 100));
    setSheetUrl(customer === "new" ? "" : customer.sheet_url || "");
    setSheetTab(customer === "new" ? "" : customer.sheet_tab_name || "");
    setSyncTime(customer === "new" ? "" : customer.sync_time || "");
    setSelected(customer === "new" ? [] : accountsFor(customer.id).map(account => account.act_id));
  };
  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!editing) return;
    setSaving(true);
    try {
      const normalizedFee = fee.trim();
      if (!/^\d{1,3}(\.\d{1,2})?$/.test(normalizedFee) || Number(normalizedFee) > 100) {
        throw new Error("Phí phải từ 0 đến 100%, tối đa hai chữ số thập phân.");
      }
      const [whole, fraction = ""] = normalizedFee.split(".");
      const units = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
      const rate = `${units / 10000n}.${String(units % 10000n).padStart(4, "0")}`;
      const body = {
        name: name.trim(),
        telegram_username: telegram.trim().replace(/^@/, "") || null,
        telegram_chat_id: chat.trim() || null,
        fee_rate: rate,
        sheet_url: sheetUrl.trim() || null,
        sheet_tab_name: sheetTab.trim() || null,
        sync_time: syncTime || null,
      };
      const result = editing === "new"
        ? await postJson<SavedCustomer>("/customers", body)
        : await patchJson<SavedCustomer>(`/customers/${editing.id}`, body);
      const retained: Customer = {
        ...body,
        id: result.customer_id,
        recon_mode: "SIMPLE_FEE",
        is_active: true,
        sheet_sync_approval_status: body.sheet_url && body.sheet_tab_name && body.sync_time ? "PENDING" : null,
      };
      setEditing(retained);
      await putJson(`/customers/${result.customer_id}/ad-accounts`, { act_ids: selected });
      toast("Đã lưu khách hàng, lịch đồng bộ và danh sách TKQC.");
      setEditing(null);
      await reload();
    } catch (error) {
      toast(error instanceof Error ? error.message : "Không thể lưu khách hàng.", "error");
      await reload();
    } finally {
      setSaving(false);
    }
  };
  const remove = async () => {
    if (!deleting) return;
    setSaving(true);
    try {
      await deleteJson(`/customers/${deleting.id}`);
      toast("Đã vô hiệu hóa khách hàng và đóng các phân công đang mở.");
      setDeleting(null);
      await reload();
    } catch (error) {
      toast(error instanceof Error ? error.message : "Không thể vô hiệu hóa khách hàng.", "error");
    } finally { setSaving(false); }
  };
  const approve = async (customer: Customer) => {
    try {
      await postJson(`/customers/${customer.id}/sheet-sync/approve`, { actor: "owner" });
      toast("Đã phê duyệt lịch ghi Google Sheets cho khách hàng.");
      await reload();
    } catch (error) {
      toast(error instanceof Error ? error.message : "Không thể phê duyệt lịch đồng bộ.", "error");
    }
  };
  const approvalLabel = (status: string | null) => ({
    PENDING: "Chờ phê duyệt",
    APPROVED: "Đã phê duyệt",
    REVOKED: "Đã thu hồi",
  }[status || ""] || "Chưa phê duyệt");

  return <>
    <PageHeading eyebrow="QUẢN LÝ KHÁCH THUÊ" title="Khách hàng & đối soát" description="Quản lý hồ sơ, TKQC và lịch Google Sheets riêng cho từng khách hàng." actions={<><Link href="/customers/finance" className="btn">Tổng tài chính ↗</Link><button className="btn primary" onClick={() => open("new")}>+ Thêm khách hàng</button></>}/>
    <ErrorNotice message={errors.join(" · ") || null}/>
    <div className="metric-grid"><Metric label="Khách hàng hoạt động" value={loading ? "—" : data.customers.filter(customer => customer.is_active).length} note="Hồ sơ đang được vận hành" icon=""/><Metric label="TKQC đã gán" value={data.accounts.filter(account => account.customer_id != null).length} note="Theo phân công hiện hành" tone="emerald"/><Metric label="Có lịch Sheets" value={data.customers.filter(customer => customer.sync_time).length} note="Lịch chạy theo giờ Việt Nam"/><Metric label="Chờ phê duyệt" value={data.customers.filter(customer => customer.sheet_sync_approval_status === "PENDING").length} note="Chưa được phép ghi bảng thật" tone="rose"/></div>
    <section className="panel"><div className="filter-bar"><input aria-label="Tìm khách hàng" placeholder="Tìm tên, Telegram hoặc Chat ID…" value={search} onChange={event => setSearch(event.target.value)}/><div className="segmented"><button className={`btn ${view === "table" ? "active" : ""}`} onClick={() => setView("table")}>Dạng bảng</button><button className={`btn ${view === "grid" ? "active" : ""}`} onClick={() => setView("grid")}>Dạng thẻ</button></div><Link href="/clients" className="btn">Định tuyến BM</Link></div>
      {!rows.length ? <Empty description={loading ? "Đang đọc danh sách khách…" : "Không tìm thấy khách hàng phù hợp."}/> : view === "table" ? <div className="table-scroll"><table><thead><tr><th>Khách hàng</th><th>Telegram</th><th>TKQC</th><th>Chi tiêu lũy kế · ảnh đọc</th><th>Phí</th><th>Google Sheets</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody>{rows.slice((page - 1) * size, page * size).map(customer => <tr key={customer.id}><td><Link href={`/customers/${customer.id}`}><strong>{customer.name}</strong></Link><small className="table-muted">Mã khách #{customer.id}</small></td><td>{customer.telegram_username ? `@${customer.telegram_username}` : customer.telegram_chat_id || "Chưa cấu hình"}</td><td>{accountsFor(customer.id).length}</td><td className="mono">{spendFor(customer.id)}</td><td>{Number(customer.fee_rate) * 100}%</td><td>{customer.sheet_tab_name || "Chưa cấu hình"}<small className="table-muted">{customer.sync_time ? `${customer.sync_time} · ${approvalLabel(customer.sheet_sync_approval_status)}` : "Chưa đặt giờ"}</small></td><td><span className={`pill ${customer.is_active ? "good" : "warn"}`}>{customer.is_active ? "Hoạt động" : "Đã vô hiệu hóa"}</span></td><td><div className="page-actions"><button className="btn" disabled={!customer.is_active} onClick={() => open(customer)}>Sửa</button>{customer.sheet_sync_approval_status === "PENDING" && <button className="btn" onClick={() => void approve(customer)}>Phê duyệt lịch</button>}<button className="btn danger" disabled={!customer.is_active} onClick={() => setDeleting(customer)}>Xóa</button></div></td></tr>)}</tbody></table></div> : <div className="customer-grid panel-body">{rows.slice((page - 1) * size, page * size).map(customer => <article className="customer-card" key={customer.id}><header><div className="admin-avatar">{customer.name.slice(0, 2).toUpperCase()}</div><div><h3>{customer.name}</h3><small className="muted">{customer.telegram_username ? `@${customer.telegram_username}` : "Chưa gắn Telegram"}</small></div></header><dl><div><dt>TKQC đang gán</dt><dd>{accountsFor(customer.id).length}</dd></div><div><dt>Mức phí dịch vụ</dt><dd>{Number(customer.fee_rate) * 100}%</dd></div><div><dt>Giờ đồng bộ</dt><dd>{customer.sync_time || "Chưa đặt"}</dd></div><div><dt>Tab Sheets</dt><dd>{customer.sheet_tab_name || "Chưa cấu hình"}</dd></div></dl><div className="page-actions"><button className="btn" disabled={!customer.is_active} onClick={() => open(customer)}>Chỉnh sửa</button><button className="btn danger" disabled={!customer.is_active} onClick={() => setDeleting(customer)}>Xóa</button></div></article>)}</div>}
      <Pagination total={rows.length} page={page} size={size} onPage={setPage} onSize={setSize}/>
    </section>
    {editing && <Modal title={editing === "new" ? "Thêm khách hàng" : "Chỉnh sửa khách hàng"} onClose={() => { if (!saving) setEditing(null); }}><form className="admin-form" onSubmit={event => void save(event)}><label>Tên khách hàng<input required maxLength={255} value={name} onChange={event => setName(event.target.value)}/></label><div className="form-grid"><label>Username Telegram<input maxLength={64} placeholder="@khachhang" value={telegram} onChange={event => setTelegram(event.target.value)}/></label><label>Telegram Chat ID<input maxLength={64} value={chat} onChange={event => setChat(event.target.value)}/></label></div><label>Phí dịch vụ đã thỏa thuận (%)<input required type="number" min="0" max="100" step="0.01" value={fee} onChange={event => setFee(event.target.value)}/><small>Phí là khoản riêng, không gộp vào chi tiêu Meta.</small></label><label>URL Google Sheets<input type="url" maxLength={1024} placeholder="https://docs.google.com/spreadsheets/d/…" value={sheetUrl} onChange={event => setSheetUrl(event.target.value)}/></label><div className="form-grid"><label>Tên tab Sheets<input maxLength={255} placeholder="JOKER" value={sheetTab} onChange={event => setSheetTab(event.target.value)}/></label><label>Giờ đồng bộ<input type="time" step="60" value={syncTime} onChange={event => setSyncTime(event.target.value)}/></label></div><label>Gắn / bỏ gắn TKQC<select multiple size={7} value={selected} onChange={event => setSelected([...event.target.selectedOptions].map(option => option.value))}>{data.accounts.map(account => <option key={account.act_id} value={account.act_id}>{account.name} · act_{account.act_id.replace(/^act_/, "")} {account.customer_name ? `· ${account.customer_name}` : "· Chưa gán"}</option>)}</select><small>Danh sách sau khi lưu là phân công hiện hành; lịch sử cũ vẫn được giữ.</small></label><div className="form-footer"><button type="button" className="btn" disabled={saving} onClick={() => setEditing(null)}>Hủy</button><button className="btn primary" disabled={saving}>{saving ? "Đang lưu…" : "Lưu khách hàng"}</button></div></form></Modal>}
    {deleting && <Modal title="Xác nhận xóa khách hàng" onClose={() => { if (!saving) setDeleting(null); }}><div className="panel-body"><p>Khách hàng <strong>{deleting.name}</strong> sẽ được vô hiệu hóa và bỏ gán khỏi TKQC hiện hành. Lịch sử, chi tiêu và nhật ký không bị xóa.</p><div className="form-footer"><button className="btn" disabled={saving} onClick={() => setDeleting(null)}>Hủy</button><button className="btn danger" disabled={saving} onClick={() => void remove()}>{saving ? "Đang xử lý…" : "Xóa an toàn"}</button></div></div></Modal>}
  </>;
}
