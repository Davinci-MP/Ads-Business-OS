"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  ClientBMPreference,
  getClientBMPreferences,
  updateClientBMPreference,
} from "../../lib/api";
import ClientBMPreferenceModal from "../../components/client-bm-preference-modal";

export default function ClientsBMPreferencesPage() {
  const [preferences, setPreferences] = useState<ClientBMPreference[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [bmFilter, setBmFilter] = useState("ALL");
  const [notice, setNotice] = useState<{ text: string; error?: boolean } | null>(null);

  // Modal State
  const [activeClient, setActiveClient] = useState<{ id: number; name: string } | null>(null);
  const [showModal, setShowModal] = useState(false);

  const loadPreferences = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getClientBMPreferences();
      setPreferences(data);
    } catch (err: unknown) {
      setNotice({
        text: err instanceof Error ? err.message : "Không thể tải danh sách phân quyền khách hàng.",
        error: true,
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPreferences();
  }, [loadPreferences]);

  // Quick 1-Click Preset update from table
  const handleQuickPreset = async (
    clientId: number,
    bmId: string,
    role: string,
    access: string
  ) => {
    setBusyId(clientId);
    setNotice(null);
    try {
      const res = await updateClientBMPreference(clientId, {
        preferred_bm_id: bmId,
        bm_role: role,
        ad_account_access_type: access,
        partial_permissions: ["MANAGE_CAMPAIGNS", "VIEW_PERFORMANCE", "CREATIVE_HUB"],
        actor: "clients_table_1click",
      });
      setNotice({ text: ` Đã lưu cấu hình ${bmId} cho ${res.preference.customer_name} thành công!` });
      await loadPreferences();
    } catch (err: unknown) {
      setNotice({
        text: err instanceof Error ? err.message : "Lỗi khi áp dụng cấu hình.",
        error: true,
      });
    } finally {
      setBusyId(null);
    }
  };

  const filtered = preferences.filter((p) => {
    if (bmFilter !== "ALL" && p.preferred_bm_id !== bmFilter) return false;
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      p.customer_name.toLowerCase().includes(q) ||
      String(p.client_id).includes(q) ||
      p.bm_role.toLowerCase().includes(q) ||
      p.preferred_bm_id.toLowerCase().includes(q)
    );
  });

  return (
    <div className="w-full space-y-6 font-sans">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#111827] p-6 rounded-2xl border border-[#1F2937]">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-gray-100 tracking-tight m-0">
              Quản Trị Phân Quyền Multi-BM &amp; Bộ Nhớ Định Tuyến
            </h2>
            <span className="text-xs px-2.5 py-0.5 rounded-full font-mono bg-purple-500/15 text-purple-300 border border-purple-500/30">
              Preference Memory Routing
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            Ghi nhớ Business Manager (BM 1, BM 2, BM 3), vai trò BM (Nhân viên / Quản trị viên) và cấp quyền TKQC (Toàn quyền / Một phần) cho từng khách hàng.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Link
            href="/tasks"
            className="px-3 py-1.5 rounded-xl text-xs font-medium text-gray-300 bg-[#1A2234] border border-[#374151] hover:text-white hover:border-purple-500 transition"
          >
            ← Xem Hộp Thư Tác Vụ
          </Link>
          <button
            onClick={() => void loadPreferences()}
            className="px-3 py-1.5 rounded-xl text-xs font-semibold text-purple-300 bg-purple-500/15 border border-purple-500/30 hover:bg-purple-500/25 transition"
            type="button"
          >
             Tải lại
          </button>
        </div>
      </div>

      {/* Notice Alert */}
      {notice && (
        <div
          className={`p-4 rounded-xl text-xs font-medium flex items-center justify-between border ${
            notice.error
              ? "bg-rose-500/15 border-rose-500/30 text-rose-300"
              : "bg-emerald-500/15 border-emerald-500/30 text-emerald-300"
          }`}
        >
          <span>{notice.text}</span>
          <button onClick={() => setNotice(null)} className="text-gray-400 hover:text-white text-sm" type="button">
            
          </button>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-[#111827] border border-[#1F2937] p-4 rounded-2xl">
          <div className="text-gray-400 text-xs">Tổng Khách Hàng</div>
          <div className="text-2xl font-bold text-white mt-1">{preferences.length}</div>
        </div>
        <div className="bg-[#111827] border border-[#1F2937] p-4 rounded-2xl">
          <div className="text-gray-400 text-xs">Đã Ghi Nhớ Cấu Hình</div>
          <div className="text-2xl font-bold text-emerald-400 mt-1">
            {preferences.filter((p) => p.is_configured).length}
          </div>
        </div>
        <div className="bg-[#111827] border border-[#1F2937] p-4 rounded-2xl">
          <div className="text-gray-400 text-xs">Định Tuyến BM 1 (Chính)</div>
          <div className="text-2xl font-bold text-blue-400 mt-1">
            {preferences.filter((p) => p.preferred_bm_id === "BM_01").length}
          </div>
        </div>
        <div className="bg-[#111827] border border-[#1F2937] p-4 rounded-2xl">
          <div className="text-gray-400 text-xs">Định Tuyến BM 2 &amp; BM 3</div>
          <div className="text-2xl font-bold text-purple-400 mt-1">
            {preferences.filter((p) => p.preferred_bm_id !== "BM_01").length}
          </div>
        </div>
      </div>

      {/* Filters Toolbar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-[#111827] p-3 rounded-2xl border border-[#1F2937]">
        <div className="flex items-center gap-2 flex-1 max-w-md">
          <div className="relative flex-1">
            <input
              type="text"
              placeholder="Tìm theo tên khách hàng hoặc ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-1.5 pl-8 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
            />
            <span className="absolute left-2.5 top-2 text-gray-500 text-xs"></span>
          </div>
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="text-gray-400 hover:text-white text-xs px-2 py-1 rounded bg-[#1A2234]"
              type="button"
            >
              Xóa
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-gray-400">Lọc theo BM:</span>
          {["ALL", "BM_01", "BM_02", "BM_03"].map((bm) => (
            <button
              key={bm}
              onClick={() => setBmFilter(bm)}
              type="button"
              className={`px-3 py-1 rounded-xl text-xs font-medium transition ${
                bmFilter === bm
                  ? "bg-purple-600 text-white font-semibold"
                  : "bg-[#1A2234] text-gray-400 hover:text-white border border-[#374151]"
              }`}
            >
              {bm === "ALL" ? "Tất cả" : bm === "BM_01" ? "BM 1" : bm === "BM_02" ? "BM 2" : "BM 3"}
            </button>
          ))}
        </div>
      </div>

      {/* Main Table */}
      <div className="bg-[#111827] border border-[#1F2937] rounded-2xl overflow-hidden shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-[#1A2234] border-b border-[#1F2937] text-gray-400">
                <th className="py-3 px-4 font-semibold">ID</th>
                <th className="py-3 px-4 font-semibold">Khách Hàng</th>
                <th className="py-3 px-4 font-semibold">BM Chỉ Định</th>
                <th className="py-3 px-4 font-semibold">Vai Trò BM</th>
                <th className="py-3 px-4 font-semibold">Quyền Hạn TKQC</th>
                <th className="py-3 px-4 font-semibold">Trạng Thái Bộ Nhớ</th>
                <th className="py-3 px-4 font-semibold text-right">Thao Tác 1-Click</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1F2937]">
              {loading ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-gray-400">
                    Đang tải danh sách phân quyền khách hàng...
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-gray-400">
                    Không tìm thấy khách hàng nào phù hợp với bộ lọc.
                  </td>
                </tr>
              ) : (
                filtered.map((item) => (
                  <tr key={item.client_id} className="hover:bg-[#1A2234]/50 transition">
                    <td className="py-3.5 px-4 font-mono text-gray-400">#{item.client_id}</td>
                    <td className="py-3.5 px-4">
                      <div className="font-semibold text-white">{item.customer_name}</div>
                      {item.notes && <div className="text-[10px] text-gray-400 line-clamp-1">{item.notes}</div>}
                    </td>
                    <td className="py-3.5 px-4">
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg font-mono font-semibold bg-purple-500/15 text-purple-300 border border-purple-500/30">
                         {item.bm_name}
                      </span>
                    </td>
                    <td className="py-3.5 px-4">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium border ${
                          item.bm_role === "ADMIN"
                            ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
                            : "bg-blue-500/15 text-blue-300 border-blue-500/30"
                        }`}
                      >
                        {item.bm_role_label}
                      </span>
                    </td>
                    <td className="py-3.5 px-4">
                      <div>
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium border ${
                            item.ad_account_access_type === "FULL"
                              ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                              : "bg-indigo-500/15 text-indigo-300 border-indigo-500/30"
                          }`}
                        >
                          {item.ad_account_access_label}
                        </span>
                        {item.ad_account_access_type === "PARTIAL" && item.partial_permissions_labels && (
                          <div className="text-[10px] text-gray-400 mt-1">
                            {item.partial_permissions_labels.join(", ")}
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      {item.is_configured ? (
                        <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400 font-medium">
                          <span className="w-2 h-2 rounded-full bg-emerald-400" />
                          Đã ghi nhớ
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] text-amber-400 font-medium">
                          <span className="w-2 h-2 rounded-full bg-amber-400" />
                          Chưa thiết lập
                        </span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {/* Quick Presets */}
                        <button
                          type="button"
                          disabled={busyId === item.client_id}
                          onClick={() => void handleQuickPreset(item.client_id, "BM_01", "EMPLOYEE", "FULL")}
                          title="Gán nhanh BM 1 (Nhân viên · Đầy đủ)"
                          className="px-2 py-1 rounded-lg text-[10px] font-semibold bg-[#1A2234] border border-blue-500/30 text-blue-300 hover:bg-blue-500/20 transition disabled:opacity-50"
                        >
                          BM 1
                        </button>
                        <button
                          type="button"
                          disabled={busyId === item.client_id}
                          onClick={() => void handleQuickPreset(item.client_id, "BM_02", "EMPLOYEE", "FULL")}
                          title="Gán nhanh BM 2 (Dự phòng)"
                          className="px-2 py-1 rounded-lg text-[10px] font-semibold bg-[#1A2234] border border-purple-500/30 text-purple-300 hover:bg-purple-500/20 transition disabled:opacity-50"
                        >
                          BM 2
                        </button>
                        <button
                          type="button"
                          disabled={busyId === item.client_id}
                          onClick={() => void handleQuickPreset(item.client_id, "BM_03", "EMPLOYEE", "FULL")}
                          title="Gán nhanh BM 3 (Kháng nghị)"
                          className="px-2 py-1 rounded-lg text-[10px] font-semibold bg-[#1A2234] border border-amber-500/30 text-amber-300 hover:bg-amber-500/20 transition disabled:opacity-50"
                        >
                          BM 3
                        </button>

                        {/* Full Modal Edit */}
                        <button
                          type="button"
                          onClick={() => {
                            setActiveClient({ id: item.client_id, name: item.customer_name });
                            setShowModal(true);
                          }}
                          className="px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-purple-600 hover:bg-purple-500 text-white transition flex items-center gap-1 shadow"
                        >
                           Phân Quyền
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal Edit */}
      {activeClient && (
        <ClientBMPreferenceModal
          clientId={activeClient.id}
          clientName={activeClient.name}
          isOpen={showModal}
          onClose={() => {
            setShowModal(false);
            setActiveClient(null);
          }}
          onSaved={() => {
            void loadPreferences();
          }}
        />
      )}
    </div>
  );
}
