"use client";

import React, { useEffect, useState } from "react";
import { MonoIcon } from "./mono-icon";
import {
  createExtensionClientKey,
  deleteExtensionClientKey,
  ExtensionClientKeyItem,
  getExtensionDownloadUrl,
  listExtensionClientKeys,
} from "@/lib/api";

type ExtensionManagerModalProps = {
  isOpen: boolean;
  onClose: () => void;
};

export default function ExtensionManagerModal({
  isOpen,
  onClose,
}: ExtensionManagerModalProps) {
  const [keys, setKeys] = useState<ExtensionClientKeyItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [newClientName, setNewClientName] = useState("");
  const [creating, setCreating] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [copiedPath, setCopiedPath] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const localExtPath = "D:\\ads-business-os\\extensions\\adsos-check-bridge";

  useEffect(() => {
    if (isOpen) {
      loadKeys();
    }
  }, [isOpen]);

  async function loadKeys() {
    setLoading(true);
    setErrorMsg(null);
    try {
      const data = await listExtensionClientKeys();
      setKeys(data);
    } catch (err: unknown) {
      setErrorMsg((err instanceof Error ? err.message : "") || "Không thể tải danh sách Client Key.");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateKey(e: React.FormEvent) {
    e.preventDefault();
    if (!newClientName.trim()) return;
    setCreating(true);
    setErrorMsg(null);
    try {
      await createExtensionClientKey({
        client_name: newClientName.trim(),
      });
      setNewClientName("");
      await loadKeys();
    } catch (err: unknown) {
      setErrorMsg((err instanceof Error ? err.message : "") || "Tạo Client Key thất bại.");
    } finally {
      setCreating(false);
    }
  }

  async function handleDeleteKey(id: number) {
    if (!confirm("Bạn có chắc chắn muốn xóa mã kết nối này?")) return;
    try {
      await deleteExtensionClientKey(id);
      setKeys((prev) => prev.filter((k) => k.id !== id));
    } catch (err: unknown) {
      alert((err instanceof Error ? err.message : "") || "Xóa mã thất bại.");
    }
  }

  function handleCopyPath() {
    navigator.clipboard.writeText(localExtPath);
    setCopiedPath(true);
    setTimeout(() => setCopiedPath(false), 2500);
  }

  function handleCopyKeyText(keyStr: string) {
    navigator.clipboard.writeText(keyStr);
    setCopiedKey(keyStr);
    setTimeout(() => setCopiedKey(null), 2500);
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-in fade-in duration-200">
      <div className="relative w-full max-w-3xl rounded-2xl border border-slate-800 bg-[#0f172a] shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* HEADER */}
        <div className="flex items-center justify-between border-b border-slate-800/80 px-6 py-4 bg-[#111827]/90">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/10 text-xl text-indigo-400 border border-indigo-500/20">
              
            </span>
            <div>
              <h2 className="text-lg font-bold text-white tracking-tight">
                Cài Đặt & Quản Lý Extension metaOs
              </h2>
              <p className="text-xs text-slate-400">
                Tiện ích Chrome thu hoạch Cookie, Token Meta, quản lý TKQC & điều phối Set Camp từ xa
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <MonoIcon name="close" className="h-4 w-4" />
          </button>
        </div>

        {/* BODY */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {errorMsg && (
            <div className="rounded-xl border border-rose-500/30 bg-rose-950/20 px-4 py-3 text-xs text-rose-300">
               {errorMsg}
            </div>
          )}

          {/* SECTION 1: DOWNLOAD & LOCAL PATH */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-950/10 p-4 space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-emerald-400">
                <span></span> Tải Gói Extension (.zip)
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Đóng gói toàn bộ mã nguồn Manifest V3 thành file zip. Gửi file này cho nhân viên hoặc khách hàng để cài trực tiếp vào Chrome.
              </p>
              <a
                href={getExtensionDownloadUrl()}
                download="metaos-extension.zip"
                className="inline-flex items-center justify-center gap-2 w-full rounded-xl bg-emerald-600 px-4 py-2.5 text-xs font-semibold text-white shadow-lg shadow-emerald-950/50 hover:bg-emerald-500 transition-colors"
              >
                <span></span> Tải Gói Cài Đặt (.zip) Ngay
              </a>
            </div>

            <div className="rounded-xl border border-indigo-500/20 bg-[#eef4ff] p-4 space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-indigo-400">
                <span></span> Cài Trực Tiếp Từ Mã Nguồn Local
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Mở <code>chrome://extensions</code> trên máy tính, bật <strong>Developer mode</strong> rồi bấm <strong>Load unpacked</strong> trỏ tới:
              </p>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  readOnly
                  value={localExtPath}
                  className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-mono text-slate-300 select-all"
                />
                <button
                  onClick={handleCopyPath}
                  className="shrink-0 rounded-lg border border-indigo-500/30 bg-indigo-500/20 px-3 py-1.5 text-xs font-medium text-indigo-300 hover:bg-indigo-500/30 transition-colors"
                >
                  {copiedPath ? "Đã copy " : "Copy"}
                </button>
              </div>
            </div>
          </div>

          {/* SECTION 2: CLIENT BINDING KEYS */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <span></span> Mã Khách Hàng (Client Binding Keys)
                </h3>
                <p className="text-xs text-slate-400">
                  Cấp mã riêng cho từng khách hàng để dữ liệu VIA & TKQC tự động phân bổ về đúng khách
                </p>
              </div>

              {/* CREATE KEY FORM */}
              <form onSubmit={handleCreateKey} className="flex items-center gap-2">
                <input
                  type="text"
                  placeholder="Tên khách hàng / Agency..."
                  value={newClientName}
                  onChange={(e) => setNewClientName(e.target.value)}
                  className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={creating || !newClientName.trim()}
                  className="rounded-xl bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors shrink-0"
                >
                  {creating ? "Đang tạo..." : "+ Tạo Mã Mới"}
                </button>
              </form>
            </div>

            {/* KEYS TABLE */}
            <div className="rounded-xl border border-slate-800 overflow-hidden">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-950/60 text-slate-400 font-semibold">
                    <th className="p-3">Khách Hàng</th>
                    <th className="p-3">Mã Kết Nối (API Key)</th>
                    <th className="p-3">Lần Cuối Hoạt Động</th>
                    <th className="p-3 text-right">Thao Tác</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-slate-300">
                  {loading ? (
                    <tr>
                      <td colSpan={4} className="p-4 text-center text-slate-500">
                        Đang tải danh sách mã...
                      </td>
                    </tr>
                  ) : keys.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="p-4 text-center text-slate-500">
                        Chưa có mã kết nối nào. Hãy tạo mã đầu tiên để gửi cho khách hàng!
                      </td>
                    </tr>
                  ) : (
                    keys.map((k) => (
                      <tr key={k.id} className="hover:bg-slate-800/30 transition-colors">
                        <td className="p-3 font-medium text-white">{k.client_name}</td>
                        <td className="p-3">
                          <span className="font-mono bg-slate-950 border border-slate-800 px-2 py-0.5 rounded text-amber-300 select-all">
                            {k.api_key}
                          </span>
                        </td>
                        <td className="p-3 text-slate-400">
                          {k.last_seen_at ? (
                            <span className="inline-flex items-center gap-1.5 text-emerald-400">
                              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                              {new Date(k.last_seen_at).toLocaleString("vi-VN")}
                            </span>
                          ) : (
                            <span className="text-slate-500">Chưa kết nối</span>
                          )}
                        </td>
                        <td className="p-3 text-right space-x-2">
                          <button
                            onClick={() => handleCopyKeyText(k.api_key)}
                            className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-[11px] text-slate-200 hover:bg-slate-700 transition-colors"
                          >
                            {copiedKey === k.api_key ? "Đã copy " : "Copy"}
                          </button>
                          <button
                            onClick={() => handleDeleteKey(k.id)}
                            className="rounded-lg border border-rose-500/20 bg-rose-950/20 px-2.5 py-1 text-[11px] text-rose-300 hover:bg-rose-900/40 transition-colors"
                          >
                            Xóa
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* INSTRUCTION CARD */}
          <div className="rounded-xl border border-slate-800/80 bg-slate-950/40 p-4 text-xs text-slate-400 space-y-2">
            <div className="font-semibold text-slate-300"> Hướng Dẫn Nhanh Cho Khách Hàng:</div>
            <ol className="list-decimal list-inside space-y-1 text-slate-400">
              <li>Tải file <code>metaos-extension.zip</code> và giải nén ra thư mục bất kỳ.</li>
              <li>Mở trình duyệt Google Chrome, truy cập <code>chrome://extensions</code>, gạt bật <strong>Developer mode</strong> ở góc phải.</li>
              <li>Bấm nút <strong>Load unpacked</strong> rồi chọn thư mục vừa giải nén.</li>
              <li>Bấm vào biểu tượng extension trên thanh công cụ, mở  Cấu hình và dán <strong>Mã Khách Hàng</strong> được cấp ở trên.</li>
              <li>Bấm nút <strong> Đồng Bộ Toàn Bộ Về Server</strong> — Dữ liệu tài khoản sẽ tự động hiển thị trên Dashboard!</li>
            </ol>
          </div>
        </div>

        {/* FOOTER */}
        <div className="border-t border-slate-800/80 px-6 py-3 bg-[#111827]/80 flex justify-end">
          <button
            onClick={onClose}
            className="rounded-xl border border-slate-700 bg-slate-800 px-5 py-2 text-xs font-semibold text-white hover:bg-slate-700 transition-colors"
          >
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
}
