"use client";

import { useCallback, useEffect, useState } from "react";
import {
  createInventoryItem,
  deleteInventoryItem,
  getInventoryCredentials,
  getInventoryItems,
  handoverInventoryItem,
  updateInventoryStatus,
  fetchJson,
  InventoryItem,
} from "../../lib/api";

const typeBadges: Record<string, { label: string; badge: string }> = {
  VIA: { label: "VIA Facebook", badge: "bg-blue-500/20 text-blue-300 border-blue-500/30" },
  BM: { label: "Business Manager", badge: "bg-purple-500/20 text-purple-300 border-purple-500/30" },
  PAGE: { label: "Fanpage Cổ", badge: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30" },
  PROXY: { label: "Proxy Dân Cư", badge: "bg-amber-500/20 text-amber-300 border-amber-500/30" },
};

const statusBadges: Record<string, { label: string; badge: string }> = {
  AVAILABLE: { label: "Sẵn sàng / Khả dụng", badge: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" },
  ASSIGNED: { label: "Đã bàn giao", badge: "bg-indigo-500/20 text-indigo-300 border-indigo-500/30" },
  DEAD: { label: "Die / Checkpoint", badge: "bg-rose-500/20 text-rose-400 border-rose-500/30" },
};

export default function InventoryPage() {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [customers, setCustomers] = useState<{ id: number; name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error?: boolean } | null>(null);

  // Filters
  const [activeTab, setActiveTab] = useState<string>("ALL");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  // Modals
  const [showAddModal, setShowAddModal] = useState(false);
  const [showCredModal, setShowCredModal] = useState(false);
  const [showHandoverModal, setShowHandoverModal] = useState(false);

  // Active Item for credential/handover modal
  const [activeItem, setActiveItem] = useState<InventoryItem | null>(null);
  const [revealedCreds, setRevealedCreds] = useState<string>("");

  // Handover form
  const [handoverCustId, setHandoverCustId] = useState<string>("");
  const [handoverAdAccountId, setHandoverAdAccountId] = useState<string>("");

  // Add Item form
  const [newItemType, setNewItemType] = useState<string>("VIA");
  const [newItemName, setNewItemName] = useState<string>("");
  const [newItemCreds, setNewItemCreds] = useState<string>("");
  const [newItemNotes, setNewItemNotes] = useState<string>("");
  const [newItemCustId, setNewItemCustId] = useState<string>("");

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const params: { item_type?: string; status?: string } = {};
      if (activeTab !== "ALL") params.item_type = activeTab;
      if (statusFilter !== "ALL") params.status = statusFilter;

      const [invList, custList] = await Promise.all([
        getInventoryItems(params),
        fetchJson<{ id: number; name: string }[]>("/customers"),
      ]);
      setItems(invList);
      setCustomers(custList);
    } catch (err: unknown) {
      setNotice({
        text: err instanceof Error ? err.message : "Không thể tải danh sách tài nguyên.",
        error: true,
      });
    } finally {
      setLoading(false);
    }
  }, [activeTab, statusFilter]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // Handle Add Item
  const handleAddItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newItemName.trim() || !newItemCreds.trim()) {
      setNotice({ text: "Vui lòng nhập tên và thông tin đăng nhập.", error: true });
      return;
    }
    setBusy(true);
    try {
      await createInventoryItem({
        item_type: newItemType,
        name: newItemName.trim(),
        credentials: newItemCreds.trim(),
        notes: newItemNotes.trim() || undefined,
        assigned_customer_id: newItemCustId ? Number(newItemCustId) : undefined,
      });
      setShowAddModal(false);
      setNewItemName("");
      setNewItemCreds("");
      setNewItemNotes("");
      setNewItemCustId("");
      setNotice({ text: "Đã thêm tài nguyên mới và mã hóa thông tin thành công." });
      await loadData();
    } catch (err: unknown) {
      setNotice({ text: err instanceof Error ? err.message : "Lỗi thêm tài nguyên.", error: true });
    } finally {
      setBusy(false);
    }
  };

  // Handle View Credentials
  const handleViewCredentials = async (item: InventoryItem) => {
    setBusy(true);
    try {
      const res = await getInventoryCredentials(item.id);
      setActiveItem(item);
      setRevealedCreds(res.credentials);
      setShowCredModal(true);
    } catch (err: unknown) {
      setNotice({ text: err instanceof Error ? err.message : "Lỗi giải mã tài nguyên.", error: true });
    } finally {
      setBusy(false);
    }
  };

  // Handle Handover
  const handleExecuteHandover = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeItem || !handoverCustId) {
      setNotice({ text: "Vui lòng chọn khách hàng nhận bàn giao.", error: true });
      return;
    }
    setBusy(true);
    try {
      const res = await handoverInventoryItem(activeItem.id, {
        customer_id: Number(handoverCustId),
        assigned_ad_account_id: handoverAdAccountId || undefined,
      });
      setShowHandoverModal(false);
      setRevealedCreds(res.credentials || "");
      setShowCredModal(true);
      setNotice({ text: `Đã bàn giao tài nguyên #${activeItem.id} thành công!` });
      await loadData();
    } catch (err: unknown) {
      setNotice({ text: err instanceof Error ? err.message : "Lỗi bàn giao tài nguyên.", error: true });
    } finally {
      setBusy(false);
    }
  };

  // Handle Quick Status Change
  const handleChangeStatus = async (item: InventoryItem, nextStatus: string) => {
    setBusy(true);
    try {
      await updateInventoryStatus(item.id, { status: nextStatus });
      setNotice({ text: `Đã cập nhật trạng thái #${item.id} thành ${nextStatus}.` });
      await loadData();
    } catch (err: unknown) {
      setNotice({ text: err instanceof Error ? err.message : "Lỗi đổi trạng thái.", error: true });
    } finally {
      setBusy(false);
    }
  };

  // Handle Delete
  const handleDeleteItem = async (item: InventoryItem) => {
    if (!confirm(`Bạn có chắc chắn muốn xóa tài nguyên "${item.name}" (ID #${item.id}) khỏi kho?`)) return;
    setBusy(true);
    try {
      await deleteInventoryItem(item.id);
      setNotice({ text: `Đã xóa tài nguyên #${item.id}.` });
      await loadData();
    } catch (err: unknown) {
      setNotice({ text: err instanceof Error ? err.message : "Lỗi xóa tài nguyên.", error: true });
    } finally {
      setBusy(false);
    }
  };

  // Counts
  const countTotal = items.length;
  const countAvailable = items.filter((i) => i.status === "AVAILABLE").length;
  const countAssigned = items.filter((i) => i.status === "ASSIGNED").length;
  const countDead = items.filter((i) => i.status === "DEAD").length;

  return (
    <div className="w-full space-y-6">
      {/* Top Banner & Control */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#111827] p-6 rounded-2xl border border-[#1F2937]">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-gray-100 tracking-tight m-0">
              Kho Tài Nguyên VIA, BM &amp; Proxy
            </h2>
            <span className="text-xs px-2.5 py-0.5 rounded-full font-mono bg-purple-500/15 text-purple-300 border border-purple-500/30">
              Encrypted Vault
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            Lưu trữ mã hóa Fernet toàn bộ mật khẩu, mã 2FA, link mời BM và Proxy. Hỗ trợ bàn giao khách hàng có lưu vết kiểm toán (Audit Trail).
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => void loadData()}
            disabled={loading || busy}
            className="px-3.5 py-2 rounded-xl text-xs font-medium text-gray-300 hover:text-white bg-[#1F2937] hover:bg-[#2A3449] border border-[#374151] transition flex items-center gap-1.5"
            type="button"
          >
            <svg className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
            </svg>
            Làm mới
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            disabled={busy}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 shadow-md shadow-purple-600/20 transition flex items-center gap-1.5"
            type="button"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            + Nhập Tài Nguyên
          </button>
        </div>
      </div>

      {/* Notification Toast */}
      {notice && (
        <div
          className={`p-4 rounded-xl text-xs flex items-center justify-between border ${
            notice.error
              ? "bg-rose-500/10 text-rose-300 border-rose-500/30"
              : "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
          }`}
        >
          <span>{notice.text}</span>
          <button
            onClick={() => setNotice(null)}
            className="text-gray-400 hover:text-white"
            type="button"
          >
            
          </button>
        </div>
      )}

      {/* KPI Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-[#111827] p-4 rounded-2xl border border-[#1F2937]">
          <span className="text-xs text-gray-400">Tổng tài nguyên</span>
          <div className="text-2xl font-bold font-mono tabular-nums text-white mt-1">
            {countTotal}
          </div>
          <div className="text-[11px] text-gray-500 mt-1">Trong kho hệ thống</div>
        </div>
        <div className="bg-[#111827] p-4 rounded-2xl border border-[#1F2937]">
          <span className="text-xs text-emerald-400">Sẵn sàng cấp (Available)</span>
          <div className="text-2xl font-bold font-mono tabular-nums text-emerald-400 mt-1">
            {countAvailable}
          </div>
          <div className="text-[11px] text-gray-500 mt-1">Chưa gán khách hàng</div>
        </div>
        <div className="bg-[#111827] p-4 rounded-2xl border border-[#1F2937]">
          <span className="text-xs text-indigo-400">Đã bàn giao (Assigned)</span>
          <div className="text-2xl font-bold font-mono tabular-nums text-indigo-300 mt-1">
            {countAssigned}
          </div>
          <div className="text-[11px] text-gray-500 mt-1">Đang hoạt động cho khách</div>
        </div>
        <div className="bg-[#111827] p-4 rounded-2xl border border-[#1F2937]">
          <span className="text-xs text-rose-400">Hỏng / Checkpoint (Dead)</span>
          <div className="text-2xl font-bold font-mono tabular-nums text-rose-400 mt-1">
            {countDead}
          </div>
          <div className="text-[11px] text-gray-500 mt-1">Cần kháng hoặc loại bỏ</div>
        </div>
      </div>

      {/* Category Tabs & Status Filter */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 bg-[#111827] p-3 rounded-2xl border border-[#1F2937]">
        {/* Category Tabs */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {[
            { id: "ALL", label: "Tất cả loại" },
            { id: "VIA", label: "VIA FB" },
            { id: "BM", label: "Business Manager" },
            { id: "PAGE", label: "Fanpage" },
            { id: "PROXY", label: "Proxy" },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-1.5 rounded-xl text-xs font-medium transition ${
                activeTab === tab.id
                  ? "bg-purple-600 text-white font-semibold shadow-sm"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
              }`}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Status Dropdown Filter */}
        <div className="flex items-center gap-2 text-xs">
          <span className="text-gray-400">Trạng thái:</span>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-[#1A2234] border border-[#374151] rounded-xl px-2.5 py-1.5 text-gray-200 focus:outline-none focus:border-purple-500"
          >
            <option value="ALL">Tất cả trạng thái</option>
            <option value="AVAILABLE">Sẵn sàng (Available)</option>
            <option value="ASSIGNED">Đã bàn giao (Assigned)</option>
            <option value="DEAD">Die / Checkpoint</option>
          </select>
        </div>
      </div>

      {/* Inventory Table */}
      <div className="bg-[#111827] rounded-2xl border border-[#1F2937] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-[#0B0F19]/60 text-gray-400 border-b border-[#1F2937]">
                <th className="py-3 px-4 font-semibold">Mã</th>
                <th className="py-3 px-4 font-semibold">Loại</th>
                <th className="py-3 px-4 font-semibold">Tên Tài Nguyên</th>
                <th className="py-3 px-4 font-semibold">Trạng Thái</th>
                <th className="py-3 px-4 font-semibold">Khách Hàng Bàn Giao</th>
                <th className="py-3 px-4 font-semibold">Mã TKQC</th>
                <th className="py-3 px-4 font-semibold">Ghi Chú</th>
                <th className="py-3 px-4 font-semibold text-right">Thao Tác Quản Trị</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1F2937]/50">
              {items.length > 0 ? (
                items.map((it) => {
                  const tb = typeBadges[it.item_type] || { label: it.item_type, badge: "bg-gray-800 text-gray-400" };
                  const sb = statusBadges[it.status] || { label: it.status, badge: "bg-gray-800 text-gray-400" };

                  return (
                    <tr key={it.id} className="hover:bg-[#1A2234]/50 transition">
                      <td className="py-3 px-4 font-mono text-gray-500">#{it.id}</td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${tb.badge}`}>
                          {tb.label}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-medium text-gray-200">{it.name}</td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${sb.badge}`}>
                          {sb.label}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-gray-300">
                        {it.customer_name ? (
                          <span className="font-semibold text-purple-300">{it.customer_name}</span>
                        ) : (
                          <span className="text-gray-500 italic">Chưa bàn giao</span>
                        )}
                      </td>
                      <td className="py-3 px-4 font-mono text-gray-400">
                        {it.assigned_ad_account_id || "—"}
                      </td>
                      <td className="py-3 px-4 text-gray-400 max-w-xs truncate" title={it.notes || ""}>
                        {it.notes || "—"}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5 flex-wrap">
                          <button
                            onClick={() => void handleViewCredentials(it)}
                            disabled={busy}
                            className="px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-[#1F2937] hover:bg-[#2A3449] text-gray-200 border border-[#374151] transition"
                            title="Hiện thông tin đăng nhập đã giải mã"
                            type="button"
                          >
                             Mật khẩu
                          </button>
                          {it.status !== "ASSIGNED" && (
                            <button
                              onClick={() => {
                                setActiveItem(it);
                                setShowHandoverModal(true);
                              }}
                              disabled={busy}
                              className="px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-purple-500/20 text-purple-300 hover:bg-purple-500/30 border border-purple-500/30 transition"
                              type="button"
                            >
                              Bàn giao
                            </button>
                          )}
                          {it.status === "ASSIGNED" && (
                            <button
                              onClick={() => void handleChangeStatus(it, "AVAILABLE")}
                              disabled={busy}
                              className="px-2 py-1 rounded-lg text-[10px] text-gray-400 hover:text-white bg-gray-800 transition"
                              title="Thu hồi về kho"
                              type="button"
                            >
                              Thu hồi
                            </button>
                          )}
                          {it.status !== "DEAD" ? (
                            <button
                              onClick={() => void handleChangeStatus(it, "DEAD")}
                              disabled={busy}
                              className="px-2 py-1 rounded-lg text-[10px] text-rose-400 hover:bg-rose-500/20 transition"
                              title="Đánh dấu tài khoản hỏng"
                              type="button"
                            >
                              Báo Die
                            </button>
                          ) : (
                            <button
                              onClick={() => void handleChangeStatus(it, "AVAILABLE")}
                              disabled={busy}
                              className="px-2 py-1 rounded-lg text-[10px] text-emerald-400 hover:bg-emerald-500/20 transition"
                              title="Đánh dấu đã kháng phục hồi"
                              type="button"
                            >
                              Đã Kháng
                            </button>
                          )}
                          <button
                            onClick={() => void handleDeleteItem(it)}
                            disabled={busy}
                            className="p-1 rounded-lg text-gray-500 hover:text-rose-400 hover:bg-gray-800 transition"
                            title="Xóa tài nguyên"
                            type="button"
                          >
                            
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-gray-500">
                    Không tìm thấy tài nguyên nào phù hợp bộ lọc.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* MODAL 1: Add Inventory Item */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fadeIn">
          <div className="bg-[#111827] border border-[#1F2937] rounded-2xl w-full max-w-lg p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-[#1F2937] pb-3">
              <h3 className="text-base font-bold text-white tracking-tight">
                Nhập Tài Nguyên Quảng Cáo Mới
              </h3>
              <button onClick={() => setShowAddModal(false)} className="text-gray-400 hover:text-white" type="button">
                
              </button>
            </div>

            <form onSubmit={handleAddItem} className="space-y-4 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-gray-300 font-medium mb-1">Loại tài nguyên (*)</label>
                  <select
                    value={newItemType}
                    onChange={(e) => setNewItemType(e.target.value)}
                    className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="VIA">VIA Facebook</option>
                    <option value="BM">Business Manager (BM)</option>
                    <option value="PAGE">Fanpage Cổ</option>
                    <option value="PROXY">Proxy</option>
                  </select>
                </div>
                <div>
                  <label className="block text-gray-300 font-medium mb-1">Bàn giao ngay cho khách</label>
                  <select
                    value={newItemCustId}
                    onChange={(e) => setNewItemCustId(e.target.value)}
                    className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="">-- Để trống nếu lưu kho --</option>
                    {customers.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-gray-300 font-medium mb-1">Tên định danh tài nguyên (*)</label>
                <input
                  type="text"
                  required
                  placeholder="Ví dụ: VIA US Cổ 2018 - Nolimit XMDT"
                  value={newItemName}
                  onChange={(e) => setNewItemName(e.target.value)}
                  className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                />
              </div>

              <div>
                <label className="block text-gray-300 font-medium mb-1">
                  Thông tin đăng nhập / Mật khẩu / Token (*) <span className="text-purple-400 text-[11px]">(Mã hóa Fernet)</span>
                </label>
                <textarea
                  required
                  rows={4}
                  placeholder="Cú pháp gợi ý:&#10;• VIA: UID|Pass|2FA_Secret|Email|PassMail&#10;• BM: Link mời tham gia BM&#10;• Proxy: IP:Port:User:Pass"
                  value={newItemCreds}
                  onChange={(e) => setNewItemCreds(e.target.value)}
                  className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white font-mono focus:outline-none focus:border-purple-500"
                />
              </div>

              <div>
                <label className="block text-gray-300 font-medium mb-1">Ghi chú lưu kho</label>
                <input
                  type="text"
                  placeholder="Nguồn mua, giá nhập hoặc lưu ý ip đăng nhập..."
                  value={newItemNotes}
                  onChange={(e) => setNewItemNotes(e.target.value)}
                  className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-[#1F2937]">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 rounded-xl text-gray-400 hover:text-white hover:bg-gray-800 transition"
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  disabled={busy}
                  className="px-5 py-2 rounded-xl font-semibold text-white bg-purple-600 hover:bg-purple-500 transition"
                >
                  Mã Hóa &amp; Lưu Kho
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2: View Decrypted Credentials */}
      {showCredModal && activeItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fadeIn">
          <div className="bg-[#111827] border border-[#1F2937] rounded-2xl w-full max-w-lg p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-[#1F2937] pb-3">
              <h3 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
                <span className="text-purple-400"></span> Thông Tin Đăng Nhập Đã Giải Mã
              </h3>
              <button onClick={() => setShowCredModal(false)} className="text-gray-400 hover:text-white" type="button">
                
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <span className="text-gray-400">Tài nguyên:</span>{" "}
                <strong className="text-white font-semibold">{activeItem.name}</strong> ({activeItem.item_type})
              </div>

              <div>
                <label className="block text-gray-400 mb-1 font-medium">Nội dung giải mã:</label>
                <div className="relative">
                  <textarea
                    readOnly
                    rows={5}
                    value={revealedCreds}
                    className="w-full bg-[#1A2234] border border-[#374151] rounded-xl p-3 text-emerald-300 font-mono text-xs select-all focus:outline-none"
                  />
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(revealedCreds);
                      setNotice({ text: "Đã sao chép thông tin đăng nhập vào Clipboard!" });
                    }}
                    className="absolute top-2 right-2 px-2.5 py-1 rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-medium text-[11px]"
                    type="button"
                  >
                    Sao chép
                  </button>
                </div>
              </div>

              <div className="bg-[#1A2234] p-3 rounded-xl border border-[#374151] text-[11px] text-gray-400">
                 <strong>Lưu ý bảo mật:</strong> Thông tin đăng nhập chỉ được giải mã trên trình duyệt quản trị local. Không chia sẻ nguyên bản ra bên ngoài nếu không có thỏa thuận với khách hàng.
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => setShowCredModal(false)}
                className="px-4 py-2 rounded-xl text-gray-300 hover:text-white bg-gray-800 transition text-xs"
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 3: Handover Modal */}
      {showHandoverModal && activeItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fadeIn">
          <div className="bg-[#111827] border border-[#1F2937] rounded-2xl w-full max-w-lg p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-[#1F2937] pb-3">
              <h3 className="text-base font-bold text-white tracking-tight">
                Bàn Giao Tài Nguyên Cho Khách Hàng
              </h3>
              <button onClick={() => setShowHandoverModal(false)} className="text-gray-400 hover:text-white" type="button">
                
              </button>
            </div>

            <form onSubmit={handleExecuteHandover} className="space-y-4 text-xs">
              <p className="text-gray-300">
                Bàn giao tài nguyên <strong className="text-purple-300">{activeItem.name}</strong> (Mã #{activeItem.id}).
                Sau khi bàn giao, trạng thái sẽ tự động đổi sang <strong className="text-indigo-300">ASSIGNED</strong>.
              </p>

              <div>
                <label className="block text-gray-300 font-medium mb-1">Khách hàng nhận bàn giao (*)</label>
                <select
                  required
                  value={handoverCustId}
                  onChange={(e) => setHandoverCustId(e.target.value)}
                  className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                >
                  <option value="">-- Chọn khách hàng --</option>
                  {customers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} (ID: {c.id})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-gray-300 font-medium mb-1">Mã tài khoản QC gắn kèm (Tùy chọn)</label>
                <input
                  type="text"
                  placeholder="Ví dụ: act_123456789"
                  value={handoverAdAccountId}
                  onChange={(e) => setHandoverAdAccountId(e.target.value)}
                  className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white font-mono focus:outline-none focus:border-purple-500"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-[#1F2937]">
                <button
                  type="button"
                  onClick={() => setShowHandoverModal(false)}
                  className="px-4 py-2 rounded-xl text-gray-400 hover:text-white hover:bg-gray-800 transition"
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  disabled={busy}
                  className="px-5 py-2 rounded-xl font-semibold text-white bg-indigo-600 hover:bg-indigo-500 transition"
                >
                  Xác Nhận Bàn Giao
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
