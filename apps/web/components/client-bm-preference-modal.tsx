"use client";

import { useEffect, useState } from "react";
import { MonoIcon } from "./mono-icon";
import {
  BMRoutingOptions,
  ClientBMPreference,
  getBMRoutingOptions,
  getClientBMPreference,
  updateClientBMPreference,
} from "../lib/api";

interface ClientBMPreferenceModalProps {
  clientId: number;
  clientName: string;
  isOpen: boolean;
  onClose: () => void;
  onSaved?: (pref: ClientBMPreference) => void;
}

const DEFAULT_OPTIONS: BMRoutingOptions = {
  available_bms: [
    { id: "BM_01", name: "BM 1", full_name: "BM 1 (Chính - Ads Holding 01)", description: "Kho tài khoản chính ngạch uy tín cao" },
    { id: "BM_02", name: "BM 2", full_name: "BM 2 (Dự phòng - Ads Holding 02)", description: "Kho tài khoản dự phòng luân chuyển" },
    { id: "BM_03", name: "BM 3", full_name: "BM 3 (Kháng nghị - Ads Holding 03)", description: "Chuyên dùng cho tài khoản thử nghiệm" },
  ],
  roles: [
    { value: "EMPLOYEE", label: "Nhân viên (EMPLOYEE)", description: "Khuyên dùng cho khách hàng" },
    { value: "ADMIN", label: "Quản trị viên (ADMIN)", description: "Toàn quyền quản trị BM" },
  ],
  access_types: [
    { value: "FULL", label: "Truy cập đầy đủ (FULL)", description: "Toàn quyền quản lý chiến dịch và báo cáo" },
    { value: "PARTIAL", label: "Truy cập một phần (PARTIAL)", description: "Giới hạn theo từng quyền cụ thể" },
  ],
  partial_permissions: [
    { key: "MANAGE_CAMPAIGNS", label: "Quản lý chiến dịch", description: "Tạo, sửa, bật/tắt quảng cáo" },
    { key: "VIEW_PERFORMANCE", label: "Xem hiệu quả", description: "Xem báo cáo số liệu và chi tiêu" },
    { key: "CREATIVE_HUB", label: "Creative Hub", description: "Tạo mockup và kiểm duyệt mẫu quảng cáo" },
  ],
};

export default function ClientBMPreferenceModal({
  clientId,
  clientName,
  isOpen,
  onClose,
  onSaved,
}: ClientBMPreferenceModalProps) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [options, setOptions] = useState<BMRoutingOptions>(DEFAULT_OPTIONS);
  const [pref, setPref] = useState<ClientBMPreference | null>(null);

  // Form State
  const [selectedBm, setSelectedBm] = useState<string>("BM_01");
  const [selectedRole, setSelectedRole] = useState<string>("EMPLOYEE");
  const [selectedAccess, setSelectedAccess] = useState<string>("FULL");
  const [selectedPerms, setSelectedPerms] = useState<string[]>([
    "MANAGE_CAMPAIGNS",
    "VIEW_PERFORMANCE",
    "CREATIVE_HUB",
  ]);
  const [notes, setNotes] = useState<string>("");
  const [autoRemember, setAutoRemember] = useState<boolean>(true);
  const [feedback, setFeedback] = useState<{ text: string; error?: boolean } | null>(null);

  useEffect(() => {
    if (!isOpen || !clientId) return;

    let active = true;
    setLoading(true);
    setFeedback(null);

    Promise.all([
      getBMRoutingOptions().catch(() => DEFAULT_OPTIONS),
      getClientBMPreference(clientId),
    ])
      .then(([optRes, prefRes]) => {
        if (!active) return;
        setOptions(optRes || DEFAULT_OPTIONS);
        setPref(prefRes);
        setSelectedBm(prefRes.preferred_bm_id || "BM_01");
        setSelectedRole(prefRes.bm_role || "EMPLOYEE");
        setSelectedAccess(prefRes.ad_account_access_type || "FULL");
        setSelectedPerms(
          prefRes.partial_permissions && prefRes.partial_permissions.length > 0
            ? prefRes.partial_permissions
            : ["MANAGE_CAMPAIGNS", "VIEW_PERFORMANCE", "CREATIVE_HUB"]
        );
        setNotes(prefRes.notes || "");
      })
      .catch((err: unknown) => {
        if (!active) return;
        setFeedback({
          text: err instanceof Error ? err.message : "Không thể tải cấu hình BM hiện tại.",
          error: true,
        });
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [isOpen, clientId]);

  if (!isOpen) return null;

  const togglePermission = (key: string) => {
    if (selectedPerms.includes(key)) {
      setSelectedPerms(selectedPerms.filter((p) => p !== key));
    } else {
      setSelectedPerms([...selectedPerms, key]);
    }
  };

  const applyPreset = (bm: string, role: string, access: string, perms: string[]) => {
    setSelectedBm(bm);
    setSelectedRole(role);
    setSelectedAccess(access);
    setSelectedPerms(perms);
  };

  const handleSave = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setSaving(true);
    setFeedback(null);

    try {
      const chosenBmObj = options.available_bms.find((b) => b.id === selectedBm);
      if (autoRemember) {
        const res = await updateClientBMPreference(clientId, {
          preferred_bm_id: selectedBm,
          via_profile_id: chosenBmObj?.via_profile_id,
          bm_role: selectedRole,
          ad_account_access_type: selectedAccess,
          partial_permissions: selectedAccess === "PARTIAL" ? selectedPerms : ["MANAGE_CAMPAIGNS", "VIEW_PERFORMANCE", "CREATIVE_HUB"],
          notes: notes.trim() || undefined,
          actor: "admin_web_1click",
        });

        setPref(res.preference);
        setFeedback({ text: " Đã lưu và ghi nhớ phân quyền BM thành công! Hệ thống sẽ tự động định tuyến các lần sau." });
        if (onSaved) {
          onSaved(res.preference);
        }
      } else {
        setFeedback({ text: " Đã áp dụng phân quyền BM cho phiên làm việc hiện tại!" });
        if (onSaved && pref) {
          onSaved({
            ...pref,
            preferred_bm_id: selectedBm,
            via_profile_id: chosenBmObj?.via_profile_id,
            via_uid: chosenBmObj?.via_uid,
            bm_role: selectedRole,
            ad_account_access_type: selectedAccess,
            partial_permissions: selectedAccess === "PARTIAL" ? selectedPerms : ["MANAGE_CAMPAIGNS", "VIEW_PERFORMANCE", "CREATIVE_HUB"],
          });
        }
      }
      setTimeout(() => {
        onClose();
      }, 1200);
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi khi lưu cấu hình BM.",
        error: true,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fadeIn">
      <div className="bg-[#111827] border border-[#1F2937] rounded-2xl w-full max-w-xl p-6 shadow-2xl space-y-5 text-gray-200">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-[#1F2937] pb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xl"></span>
              <h3 className="text-base font-bold text-white tracking-tight m-0">
                Bộ Nhớ Định Tuyến &amp; Phân Quyền Multi-BM
              </h3>
            </div>
            <p className="text-xs text-gray-400 mt-1">
              Khách hàng: <strong className="text-purple-300">{clientName}</strong> (ID: #{clientId})
            </p>
          </div>
          <button
            onClick={onClose}
            type="button"
            className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-gray-800 transition"
          >
            <MonoIcon name="close" className="h-4 w-4" />
          </button>
        </div>

        {/* Feedback message */}
        {feedback && (
          <div
            className={`p-3 rounded-xl text-xs font-medium border ${
              feedback.error
                ? "bg-rose-500/15 border-rose-500/30 text-rose-300"
                : "bg-emerald-500/15 border-emerald-500/30 text-emerald-300"
            }`}
          >
            {feedback.text}
          </div>
        )}

        {loading ? (
          <div className="py-12 text-center text-xs text-gray-400">Đang tải cấu hình ưu tiên...</div>
        ) : (
          <div className="space-y-4 text-xs">
            {/* Memory status banner */}
            <div className="flex items-center justify-between p-3 rounded-xl bg-[#1A2234] border border-[#374151]">
              <div className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-full ${pref?.is_configured ? "bg-emerald-400 shadow-sm" : "bg-amber-400 animate-pulse"}`} />
                <span className="font-semibold text-gray-200">
                  {pref?.is_configured ? "Đã Ghi Nhớ Cấu Hình Ưu Tiên" : "Chưa Lưu Cấu Hình (Đang Dùng Mặc Định)"}
                </span>
              </div>
              <span className="text-[11px] text-gray-400 font-mono">
                {pref?.updated_at ? `Cập nhật: ${new Date(pref.updated_at).toLocaleDateString("vi-VN")}` : "Mới khởi tạo"}
              </span>
            </div>

            {/* Quick 1-Click Presets */}
            <div>
              <label className="block text-gray-400 text-[11px] font-semibold uppercase tracking-wider mb-2">
                Thiết Lập Nhanh 1-Click (Presets)
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                <button
                  type="button"
                  onClick={() => applyPreset("BM_01", "EMPLOYEE", "FULL", ["MANAGE_CAMPAIGNS", "VIEW_PERFORMANCE", "CREATIVE_HUB"])}
                  className="px-2.5 py-2 rounded-xl bg-[#0B0F19] border border-blue-500/30 hover:border-blue-400 text-blue-300 text-left transition hover:bg-blue-500/10"
                >
                  <div className="font-bold text-[11px]"> BM 1 Tiêu Chuẩn</div>
                  <div className="text-[10px] text-gray-400">Nhân viên · Toàn quyền</div>
                </button>
                <button
                  type="button"
                  onClick={() => applyPreset("BM_02", "EMPLOYEE", "FULL", ["MANAGE_CAMPAIGNS", "VIEW_PERFORMANCE", "CREATIVE_HUB"])}
                  className="px-2.5 py-2 rounded-xl bg-[#0B0F19] border border-purple-500/30 hover:border-purple-400 text-purple-300 text-left transition hover:bg-purple-500/10"
                >
                  <div className="font-bold text-[11px]"> BM 2 Dự Phòng</div>
                  <div className="text-[10px] text-gray-400">Nhân viên · Toàn quyền</div>
                </button>
                <button
                  type="button"
                  onClick={() => applyPreset("BM_01", "ADMIN", "FULL", ["MANAGE_CAMPAIGNS", "VIEW_PERFORMANCE", "CREATIVE_HUB"])}
                  className="px-2.5 py-2 rounded-xl bg-[#0B0F19] border border-amber-500/30 hover:border-amber-400 text-amber-300 text-left transition hover:bg-amber-500/10"
                >
                  <div className="font-bold text-[11px]"> BM 1 Quản Trị</div>
                  <div className="text-[10px] text-gray-400">Admin · Toàn quyền</div>
                </button>
              </div>
            </div>

            {/* 1. BM Selection */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-gray-300 font-semibold text-xs">
                  1. Business Manager (BM) Lưu Trữ &amp; Phân Phối TKQC
                </label>
                <span className="text-[11px] text-amber-400 font-medium">
                  Ưu tiên  BM Chính Cho Thuê
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 max-h-56 overflow-y-auto pr-1">
                {options.available_bms
                  .slice()
                  .sort((a, b) => (b.is_primary_rental ? 1 : 0) - (a.is_primary_rental ? 1 : 0))
                  .map((bm) => (
                    <button
                      key={bm.id}
                      type="button"
                      onClick={() => setSelectedBm(bm.id)}
                      className={`p-3 rounded-xl border text-left transition relative ${
                        selectedBm === bm.id
                          ? "bg-purple-600/20 border-purple-500 text-white font-semibold ring-1 ring-purple-500"
                          : bm.is_primary_rental
                          ? "bg-[#1E1B2E] border-amber-500/40 text-amber-100 hover:border-amber-400"
                          : "bg-[#1A2234] border-[#374151] text-gray-300 hover:border-gray-500"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-1.5">
                          {bm.is_primary_rental && (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                               BM Cho Thuê
                            </span>
                          )}
                          <span className="font-mono text-[11px] text-gray-300">{bm.id}</span>
                        </div>
                        {selectedBm === bm.id && <span className="text-purple-400 text-xs font-bold"> Đã chọn</span>}
                      </div>
                      <div className="font-bold text-xs text-purple-300 line-clamp-1">{bm.name}</div>
                      <div className="text-[10px] text-gray-400 line-clamp-2 mt-0.5">{bm.description}</div>
                      {bm.via_uid && (
                        <div className="text-[9px] text-gray-400 mt-1 font-mono">
                          Quản lý bởi VIA: <span className="text-emerald-300">{bm.via_uid}</span>
                        </div>
                      )}
                    </button>
                  ))}
              </div>
            </div>

            {/* 2. BM Role & Access Level */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-gray-300 font-semibold mb-1.5">
                  2. Vai Trò Trên BM
                </label>
                <div className="space-y-1.5">
                  {options.roles.map((r) => (
                    <label
                      key={r.value}
                      className={`flex items-center justify-between p-2.5 rounded-xl border cursor-pointer transition ${
                        selectedRole === r.value
                          ? "bg-blue-500/15 border-blue-500 text-white font-semibold"
                          : "bg-[#1A2234] border-[#374151] text-gray-300 hover:border-gray-500"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <input
                          type="radio"
                          name="bm_role"
                          value={r.value}
                          checked={selectedRole === r.value}
                          onChange={() => setSelectedRole(r.value)}
                          className="accent-blue-500"
                        />
                        <span className="text-xs">{r.label}</span>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-gray-300 font-semibold mb-1.5">
                  3. Cấp Quyền Tài Khoản QC
                </label>
                <div className="space-y-1.5">
                  {options.access_types.map((acc) => (
                    <label
                      key={acc.value}
                      className={`flex items-center justify-between p-2.5 rounded-xl border cursor-pointer transition ${
                        selectedAccess === acc.value
                          ? "bg-emerald-500/15 border-emerald-500 text-white font-semibold"
                          : "bg-[#1A2234] border-[#374151] text-gray-300 hover:border-gray-500"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <input
                          type="radio"
                          name="access_type"
                          value={acc.value}
                          checked={selectedAccess === acc.value}
                          onChange={() => setSelectedAccess(acc.value)}
                          className="accent-emerald-500"
                        />
                        <span className="text-xs">{acc.label}</span>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            </div>

            {/* 3. Partial Permissions (if PARTIAL selected or always configurable) */}
            {selectedAccess === "PARTIAL" && (
              <div className="p-3 rounded-xl bg-[#1A2234] border border-[#374151] space-y-2">
                <label className="block text-amber-300 font-semibold text-xs">
                  Danh Sách Quyền Giới Hạn (PARTIAL PERMISSIONS):
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  {options.partial_permissions.map((p) => {
                    const checked = selectedPerms.includes(p.key);
                    return (
                      <button
                        type="button"
                        key={p.key}
                        onClick={() => togglePermission(p.key)}
                        className={`p-2 rounded-lg border text-left transition flex items-center gap-2 ${
                          checked
                            ? "bg-amber-500/20 border-amber-500/50 text-white"
                            : "bg-[#0B0F19] border-[#374151] text-gray-400 hover:text-white"
                        }`}
                      >
                        <span className={`text-xs ${checked ? "text-amber-400" : "text-gray-500"}`}>
                          {checked ? "" : ""}
                        </span>
                        <div>
                          <div className="font-semibold text-[11px]">{p.label}</div>
                          <div className="text-[9px] text-gray-400">{p.description}</div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Auto-Remember Toggle */}
            <label className="flex items-center gap-3 p-3 rounded-xl bg-[#1A2234] border border-[#374151] cursor-pointer hover:border-purple-500/40 transition">
              <input
                type="checkbox"
                checked={autoRemember}
                onChange={(e) => setAutoRemember(e.target.checked)}
                className="w-4 h-4 rounded accent-purple-600 cursor-pointer"
              />
              <div className="text-xs">
                <span className="font-semibold text-white">
                  Ghi nhớ BM &amp; thiết lập quyền này cho khách hàng ở lần sau
                </span>
                <p className="text-[11px] text-gray-400 m-0">
                  Tự động lưu và ưu tiên áp dụng cấu hình này cho mọi tác vụ chia sẻ BM / TKQC tiếp theo.
                </p>
              </div>
            </label>

            {/* Notes */}
            <div>
              <label className="block text-gray-400 font-medium mb-1">
                Ghi chú nội bộ
              </label>
              <input
                type="text"
                placeholder="Ví dụ: Khách hàng chỉ chạy camp chuyển đổi, tài khoản chính ngạch..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full bg-[#1A2234] border border-[#374151] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-purple-500 text-xs"
              />
            </div>
          </div>
        )}

        {/* Footer Actions */}
        <div className="flex items-center justify-between pt-4 border-t border-[#1F2937]">
          <div className="text-[11px] text-gray-400 flex items-center gap-1.5">
            <span></span>
            <span>Hệ thống tự động ghi nhớ cấu hình cho các yêu cầu Telegram tiếp theo.</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-gray-400 hover:text-white hover:bg-gray-800 transition text-xs"
            >
              Hủy
            </button>
            <button
              type="button"
              disabled={saving || loading}
              onClick={() => void handleSave()}
              className="px-5 py-2 rounded-xl font-semibold text-white bg-purple-600 hover:bg-purple-500 transition text-xs flex items-center gap-2 disabled:opacity-50"
            >
              {saving ? "Đang lưu..." : "Lưu & Ghi Nhớ Phân Quyền (1-Click)"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
