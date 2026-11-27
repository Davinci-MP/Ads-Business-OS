"use client";

import { useEffect, useState } from "react";
import { MonoIcon } from "./mono-icon";
import {
  postSheetWritebackFromVias,
  type SheetWritebackItem,
  type SheetWritebackResponse,
} from "../lib/api";
import { formatVnd } from "../lib/vnd.mjs";

interface ViaSheetWritebackModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  defaultDate?: string;
}

export default function ViaSheetWritebackModal({
  isOpen,
  onClose,
  onSuccess,
  defaultDate,
}: ViaSheetWritebackModalProps) {
  const todayStr = () => new Date().toISOString().slice(0, 10);
  const [reportDate, setReportDate] = useState(defaultDate || todayStr());
  const [autoBorders, setAutoBorders] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [commitLoading, setCommitLoading] = useState(false);
  const [previewData, setPreviewData] = useState<SheetWritebackResponse | null>(null);
  const [feedback, setFeedback] = useState<{ message: string; error?: boolean } | null>(null);

  useEffect(() => {
    if (defaultDate) setReportDate(defaultDate);
  }, [defaultDate]);

  useEffect(() => {
    if (!isOpen) {
      setFeedback(null);
      setPreviewData(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleDryRun = async () => {
    setPreviewLoading(true);
    setFeedback(null);
    try {
      const res = await postSheetWritebackFromVias({
        report_date: reportDate,
        dry_run: true,
        auto_create_borders: autoBorders,
      });
      setPreviewData(res);
      setFeedback({
        message: `Đã tạo bản xem trước cho ${res.total_clients} khách hàng (${res.summary.rows_inserted} dòng mới, ${res.summary.rows_updated} dòng cập nhật). Chưa ghi vào Sheet.`,
      });
    } catch (err: unknown) {
      setFeedback({
        message: err instanceof Error ? err.message : String(err),
        error: true,
      });
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleCommit = async () => {
    setCommitLoading(true);
    setFeedback(null);
    try {
      const res = await postSheetWritebackFromVias({
        report_date: reportDate,
        dry_run: false,
        auto_create_borders: autoBorders,
      });
      setPreviewData(res);
      setFeedback({
        message: res.message || `Đã ghi thành công báo cáo lên Sheet cho ${res.total_clients} khách!`,
      });
      if (onSuccess) onSuccess();
    } catch (err: unknown) {
      setFeedback({
        message: err instanceof Error ? err.message : String(err),
        error: true,
      });
    } finally {
      setCommitLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-md">
      <div className="relative w-full max-w-5xl max-h-[92vh] flex flex-col rounded-2xl border border-slate-800 bg-[#0f172a] p-6 shadow-2xl text-slate-100">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-800 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/20 text-indigo-400 font-bold text-sm">
                
              </span>
              <h2 className="text-xl font-bold tracking-tight text-white">
                Kẻ & Ghi Báo Cáo VIA Lên Google Sheet
              </h2>
            </div>
            <p className="mt-1 text-xs text-slate-400">
              Tự động gom chi tiêu các TKQC gán cho từng khách hàng, tính phí dịch vụ và điền dòng báo cáo tương ứng trên Google Sheet đã liên kết.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <MonoIcon name="close" className="h-4 w-4" />
          </button>
        </div>

        {/* Toolbar & Controls */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800/80 bg-slate-900/60 p-4">
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-xs font-medium text-slate-300">
              <span>Ngày báo cáo:</span>
              <input
                type="date"
                value={reportDate}
                onChange={(e) => setReportDate(e.target.value)}
                className="rounded-lg border border-slate-700 bg-[#1e293b] px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
            </label>

            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={autoBorders}
                onChange={(e) => setAutoBorders(e.target.checked)}
                className="h-4 w-4 rounded border-slate-700 bg-slate-800 text-indigo-600 focus:ring-indigo-500"
              />
              <span>Tự động kẻ viền ô & công thức (Borders & Formulas)</span>
            </label>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={previewLoading || commitLoading}
              onClick={handleDryRun}
              className="inline-flex items-center gap-1.5 rounded-xl border border-indigo-500/30 bg-[#eef4ff] px-3.5 py-1.5 text-xs font-medium text-indigo-300 hover:bg-[#eef4ff] transition-colors disabled:opacity-50"
            >
              {previewLoading ? " Đang tính toán…" : " Xem Trước Dòng Sẽ Kẻ"}
            </button>

            <button
              type="button"
              disabled={commitLoading || previewLoading}
              onClick={handleCommit}
              className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 px-4 py-1.5 text-xs font-semibold text-white shadow-lg shadow-emerald-950/40 hover:from-emerald-500 hover:to-teal-500 transition-all disabled:opacity-50"
            >
              {commitLoading ? " Đang ghi lên Sheet…" : " Xác Nhận Kẻ & Ghi Lên Sheet"}
            </button>
          </div>
        </div>

        {/* Feedback Alert */}
        {feedback && (
          <div
            className={`mt-3 rounded-xl border p-3 text-xs ${
              feedback.error
                ? "border-rose-500/30 bg-rose-950/30 text-rose-300"
                : "border-emerald-500/30 bg-emerald-950/30 text-emerald-300"
            }`}
          >
            {feedback.message}
          </div>
        )}

        {/* Preview Summary Bar */}
        {previewData && (
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3">
              <span className="text-[11px] text-slate-400">Tổng khách hàng</span>
              <p className="mt-1 text-base font-semibold text-white">{previewData.total_clients} khách</p>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3">
              <span className="text-[11px] text-slate-400">Dòng mới / Cập nhật</span>
              <p className="mt-1 text-base font-semibold text-indigo-300">
                <span className="text-emerald-400">+{previewData.summary.rows_inserted} mới</span>
                {" · "}
                <span className="text-amber-300">{previewData.summary.rows_updated} sửa</span>
              </p>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3">
              <span className="text-[11px] text-slate-400">Tổng chi tiêu QC</span>
              <p className="mt-1 text-base font-semibold text-white font-mono">
                {formatVnd(previewData.summary.total_spend_vnd)} đ
              </p>
            </div>
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-3">
              <span className="text-[11px] text-emerald-400 font-medium">Lợi nhuận (Phí)</span>
              <p className="mt-1 text-base font-bold text-emerald-300 font-mono">
                +{formatVnd(previewData.summary.total_fee_vnd)} đ
              </p>
            </div>
          </div>
        )}

        {/* Table Content */}
        <div className="mt-4 flex-1 overflow-auto rounded-xl border border-slate-800">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="sticky top-0 bg-slate-900/95 backdrop-blur-sm text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
              <tr>
                <th className="px-3 py-2.5 font-semibold">Khách hàng</th>
                <th className="px-3 py-2.5 font-semibold">Tab Sheet</th>
                <th className="px-3 py-2.5 font-semibold">TKQC VIA</th>
                <th className="px-3 py-2.5 font-semibold">Hành động</th>
                <th className="px-3 py-2.5 font-semibold text-right">Chi tiêu trước</th>
                <th className="px-3 py-2.5 font-semibold text-right">Chi tiêu mới</th>
                <th className="px-3 py-2.5 font-semibold text-right">% Phí</th>
                <th className="px-3 py-2.5 font-semibold text-right">Phí (Lợi nhuận)</th>
                <th className="px-3 py-2.5 font-semibold text-right">Tổng gồm phí</th>
                <th className="px-3 py-2.5 font-semibold">Tiền nạp bảo lưu</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono">
              {!previewData ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-slate-500 font-sans">
                    Nhấn <strong className="text-indigo-400">" Xem Trước Dòng Sẽ Kẻ"</strong> để nạp danh sách tính toán chi tiêu và kiểm tra trước khi ghi lên Google Sheet.
                  </td>
                </tr>
              ) : previewData.clients.length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-slate-500 font-sans">
                    Không có khách hàng nào hoạt động trong hệ thống.
                  </td>
                </tr>
              ) : (
                previewData.clients.map((item: SheetWritebackItem) => {
                  const isNew = item.action === "INSERTED_NEW_ROW";
                  const hasSpend = Number(item.new_spend_vnd) > 0;
                  return (
                    <tr
                      key={item.customer_id}
                      className="hover:bg-slate-800/40 transition-colors"
                    >
                      <td className="px-3 py-2 font-sans font-medium text-white">
                        {item.customer_name}
                      </td>
                      <td className="px-3 py-2 text-slate-300 font-sans">
                        <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[11px]">
                          {item.sheet_title}
                        </span>
                        <span className="ml-1 text-[10px] text-slate-500">#{item.row_index}</span>
                      </td>
                      <td className="px-3 py-2 text-slate-400 font-sans max-w-[150px] truncate" title={item.account_names}>
                        {item.ad_accounts.length > 0 ? (
                          <span className="text-indigo-300">
                            {item.ad_accounts.length} TK ({item.ad_accounts[0]}...)
                          </span>
                        ) : (
                          <span className="text-slate-500">Mặc định</span>
                        )}
                      </td>
                      <td className="px-3 py-2 font-sans">
                        {isNew ? (
                          <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-400 border border-emerald-500/30">
                            + Dòng mới #{item.row_index}
                          </span>
                        ) : (
                          <span className="inline-flex items-center rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-300 border border-amber-500/30">
                            Cập nhật #{item.row_index}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right text-slate-400">
                        {formatVnd(item.previous_spend_vnd)} đ
                      </td>
                      <td className={`px-3 py-2 text-right font-semibold ${hasSpend ? "text-white" : "text-slate-500"}`}>
                        {formatVnd(item.new_spend_vnd)} đ
                      </td>
                      <td className="px-3 py-2 text-right text-indigo-300">
                        {item.fee_rate_pct}%
                      </td>
                      <td className="px-3 py-2 text-right font-bold text-emerald-400">
                        {formatVnd(item.fee_vnd)} đ
                      </td>
                      <td className="px-3 py-2 text-right text-indigo-200">
                        {formatVnd(item.total_vnd)} đ
                      </td>
                      <td className="px-3 py-2 font-sans text-[11px] text-slate-400">
                        {Number(item.preserved_deposits.budget_deposits_vnd || 0) > 0 && (
                          <span className="text-sky-400 mr-2">
                            Nạp: {formatVnd(item.preserved_deposits.budget_deposits_vnd)} đ
                          </span>
                        )}
                        {Number(item.preserved_deposits.usdt_received || 0) > 0 && (
                          <span className="text-violet-300">
                            USDT: {item.preserved_deposits.usdt_received}
                          </span>
                        )}
                        {Number(item.preserved_deposits.budget_deposits_vnd || 0) === 0 &&
                          Number(item.preserved_deposits.usdt_received || 0) === 0 && (
                            <span className="text-slate-600">—</span>
                          )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Footer */}
        <div className="mt-4 flex items-center justify-between border-t border-slate-800 pt-3 text-xs text-slate-500 font-sans">
          <span>
            Bảo toàn nguyên vẹn số tiền nạp thủ công (VND / USDT) và ghi chú ở các cột J, K, L.
          </span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-1.5 text-xs text-slate-200 hover:bg-slate-700 transition-colors"
          >
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
}
