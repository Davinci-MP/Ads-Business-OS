"use client";

import React, { useEffect, useState } from "react";
import {
  BrowserNodeItem,
  dispatchControlHubCommand,
  getControlHubNodes,
} from "../lib/api";
import { MonoIcon } from "./mono-icon";

type Props = {
  selectedAccountIds?: string[];
  onActionComplete?: (msg: string) => void;
};

export default function ControlHubNodesBar({
  selectedAccountIds = [],
  onActionComplete,
}: Props) {
  const [nodes, setNodes] = useState<BrowserNodeItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [showDispatchModal, setShowDispatchModal] = useState(false);
  const [targetNodeUid, setTargetNodeUid] = useState<string>("");
  const [command, setCommand] = useState<string>("CHECK_LIVE");
  const [dispatching, setDispatching] = useState(false);
  const [feedback, setFeedback] = useState<{ text: string; error?: boolean } | null>(null);

  const fetchNodes = async () => {
    try {
      setLoading(true);
      const res = await getControlHubNodes();
      setNodes(res.nodes || []);
      if (!targetNodeUid && res.nodes?.length > 0) {
        setTargetNodeUid(res.nodes[0].node_uid);
      }
    } catch {
      // Keep existing nodes
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchNodes();
    const interval = setInterval(() => {
      void fetchNodes();
    }, 6000);
    return () => clearInterval(interval);
  }, []);

  const handleDispatch = async (e: React.FormEvent) => {
    e.preventDefault();
    setDispatching(true);
    setFeedback(null);
    try {
      const res = await dispatchControlHubCommand({
        node_uid: targetNodeUid || undefined,
        command,
        payload: {
          account_ids: selectedAccountIds,
          timestamp: new Date().toISOString(),
        },
      });
      setFeedback({ text: ` Đã phát lệnh ${command} thành công! Task ID: #${res.task_id || "N/A"}` });
      if (onActionComplete) {
        onActionComplete(`Phát lệnh ${command} tới trình duyệt thành công.`);
      }
      setTimeout(() => setShowDispatchModal(false), 1200);
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Gửi lệnh tới trình duyệt thất bại.",
        error: true,
      });
    } finally {
      setDispatching(false);
    }
  };

  const onlineNodes = nodes.filter((n) => n.status === "ONLINE");

  return (
    <>
      <div className="mx-4 mt-2 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#2A2A32] bg-[#16161A] px-4 py-2 text-xs shadow-md">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              <span
                className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                  onlineNodes.length > 0 ? "bg-emerald-400" : "bg-amber-400"
                }`}
              />
              <span
                className={`relative inline-flex rounded-full h-2.5 w-2.5 ${
                  onlineNodes.length > 0 ? "bg-emerald-500" : "bg-amber-500"
                }`}
              />
            </span>
            <span className="font-semibold text-white">Cloud Control Hub</span>
            <span className="rounded-full bg-emerald-950/60 border border-emerald-500/30 px-2 py-0.5 text-[11px] font-mono text-emerald-400">
              {onlineNodes.length}/{nodes.length} Node Online
            </span>
            {loading && (
              <span className="text-[10px] text-slate-500 animate-spin">⟳</span>
            )}
          </div>

          <div className="flex items-center gap-1.5 flex-wrap">
            {nodes.length === 0 ? (
              <span className="text-[11px] text-slate-500 italic">
                Chưa có Chrome / Antidetect node kết nối. Cài đặt Extension để đồng bộ.
              </span>
            ) : (
              nodes.slice(0, 5).map((node) => (
                <div
                  key={node.node_uid}
                  className="flex items-center gap-1.5 rounded-lg border border-[#2A2A32] bg-[#1E1E24] px-2.5 py-1 text-[11px] text-[#D1D5DB]"
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      node.status === "ONLINE" ? "bg-emerald-400" : "bg-slate-500"
                    }`}
                  />
                  <span className="font-medium text-white">{node.node_name}</span>
                  <span className="text-[10px] font-mono text-[#9CA3AF]">[{node.browser_type}]</span>
                  {node.fb_uid && (
                    <span className="text-[10px] font-mono text-cyan-400">UID: {node.fb_uid}</span>
                  )}
                  <div className="flex items-center gap-1 ml-1">
                    <span
                      className={`px-1 py-0.2 rounded text-[9px] font-bold ${
                        node.has_cookie
                          ? "bg-emerald-500/20 text-emerald-300"
                          : "bg-slate-800 text-slate-500"
                      }`}
                    >
                      Cookie
                    </span>
                    <span
                      className={`px-1 py-0.2 rounded text-[9px] font-bold ${
                        node.has_eaag
                          ? "bg-emerald-500/20 text-emerald-300"
                          : "bg-slate-800 text-slate-500"
                      }`}
                    >
                      EAAG
                    </span>
                    <span
                      className={`px-1 py-0.2 rounded text-[9px] font-bold ${
                        node.has_eaab
                          ? "bg-emerald-500/20 text-emerald-300"
                          : "bg-slate-800 text-slate-500"
                      }`}
                    >
                      EAAB
                    </span>
                    <span
                      className={`px-1 py-0.2 rounded text-[9px] font-bold ${
                        node.has_fb_dtsg
                          ? "bg-emerald-500/20 text-emerald-300"
                          : "bg-slate-800 text-slate-500"
                      }`}
                    >
                      DTSG
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              void fetchNodes();
              setShowDispatchModal(true);
            }}
            className="rounded-lg border border-[#3A3A42] bg-[#222228] px-3 py-1.5 text-xs font-semibold text-white hover:border-emerald-500 hover:bg-emerald-950/20 transition flex items-center gap-1.5 shadow-sm"
          >
            <MonoIcon name="settings" className="h-4 w-4" />
            <span>Điều Khiển Từ Xa</span>
          </button>
        </div>
      </div>

      {/* DISPATCH REMOTE COMMAND MODAL */}
      {showDispatchModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in">
          <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-[#111827] p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <MonoIcon name="settings" className="h-4 w-4" /> Phát lệnh điều khiển từ xa
              </h3>
              <button
                type="button"
                onClick={() => setShowDispatchModal(false)}
                className="text-slate-400 hover:text-white"
              >
                <MonoIcon name="close" className="h-4 w-4" />
              </button>
            </div>

            {feedback && (
              <div
                className={`rounded-xl border px-3.5 py-2 text-xs font-medium ${
                  feedback.error
                    ? "border-rose-500/30 bg-rose-950/30 text-rose-300"
                    : "border-emerald-500/30 bg-emerald-950/30 text-emerald-300"
                }`}
              >
                {feedback.text}
              </div>
            )}

            <form onSubmit={handleDispatch} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">
                  Browser Node Đích:
                </label>
                <select
                  value={targetNodeUid}
                  onChange={(e) => setTargetNodeUid(e.target.value)}
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
                >
                  <option value="">-- Phát tới tất cả Node online --</option>
                  {nodes.map((n) => (
                    <option key={n.node_uid} value={n.node_uid}>
                      {n.node_name} ({n.browser_type}) · {n.status}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">
                  Lệnh Điều Khiển:
                </label>
                <select
                  value={command}
                  onChange={(e) => setCommand(e.target.value)}
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white focus:border-emerald-500 focus:outline-none font-mono"
                >
                  <option value="CHECK_LIVE">CHECK_LIVE (Kiểm tra token & cookie VIA sống/chết)</option>
                  <option value="FORCE_SYNC">FORCE_SYNC (Ép đồng bộ BM, TKQC, Fanpage, Pixel ngay)</option>
                  <option value="REMOVE_HIDDEN_ADMIN">REMOVE_HIDDEN_ADMIN (Quét sâu & xóa QTV ẩn trái phép)</option>
                  <option value="PAY_NOW">PAY_NOW (Kích hoạt thanh toán số dư dư nợ TKQC)</option>
                  <option value="SHARE_PIXEL">SHARE_PIXEL (Phân phối Pixel sang TKQC)</option>
                  <option value="SET_CAMP">SET_CAMP (Bắn lệnh tạo chiến dịch tự động)</option>
                  <option value="RELOAD_EXTENSION">RELOAD_EXTENSION (Tải lại phiên làm việc Extension)</option>
                </select>
              </div>

              <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-3 text-xs text-slate-400">
                Lệnh được đẩy tới Cloud Control Hub và được trình duyệt mục tiêu (Chrome, AdsPower, GoLogin) kéo về thực thi trong vòng 5 giây qua heartbeat an toàn.
              </div>

              <div className="flex items-center justify-end gap-2.5 pt-2">
                <button
                  type="button"
                  onClick={() => setShowDispatchModal(false)}
                  className="rounded-xl border border-slate-700 px-4 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800 transition"
                >
                  Đóng
                </button>
                <button
                  type="submit"
                  disabled={dispatching}
                  className="rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 px-4 py-2 text-xs font-bold text-white shadow-lg shadow-emerald-950/40 hover:from-emerald-500 hover:to-teal-500 disabled:opacity-50 transition"
                >
                  {dispatching ? "Đang phát lệnh..." : "Phát Lệnh Ngay"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
