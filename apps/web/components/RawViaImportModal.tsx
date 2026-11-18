"use client";

import React, { useEffect, useMemo, useState } from "react";
import { MonoIcon } from "./mono-icon";
import {
  importRawViasAndSync,
  createVia,
  forceSyncAllViaAssets,
  type ImportRawViasResponse,
  type ImportRawViasResult,
} from "../lib/api";
import { computeClientTotp } from "../lib/totp";

type ParsedViaPreview = {
  raw: string;
  uid: string;
  pass: string;
  twoFa: string;
  email: string;
  passMail: string;
  backupMail: string;
  passBackupMail: string;
  hasCookie: boolean;
  hasEaag: boolean;
  hasEaab: boolean;
  totpCode?: string;
  remaining?: number;
};

export default function RawViaImportModal({
  open,
  onClose,
  onSuccess,
}: {
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}) {
  const [activeTab, setActiveTab] = useState<"raw_via" | "token_cookie">("raw_via");
  const [rawText, setRawText] = useState("");
  const [proxyUrl, setProxyUrl] = useState("");
  const [autoLoginAndScan, setAutoLoginAndScan] = useState(true);
  const [showPasswords, setShowPasswords] = useState(false);

  // Tab 2 manual fast input state
  const [tab2Mode, setTab2Mode] = useState<"TOKEN" | "COOKIE" | "BM_LIST">("TOKEN");
  const [tab2Uid, setTab2Uid] = useState("");
  const [tab2Input, setTab2Input] = useState("");

  // Progress and results
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [currentStep, setCurrentStep] = useState<number>(0);
  const [stepLabel, setStepLabel] = useState<string>("");
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ text: string; error?: boolean } | null>(null);
  const [importResponse, setImportResponse] = useState<ImportRawViasResponse | null>(null);

  // Live parsed lines with client-side calculated TOTP codes
  const [parsedRows, setParsedRows] = useState<ParsedViaPreview[]>([]);

  // 1-second interval to update remaining seconds and recalculate TOTP
  useEffect(() => {
    if (!open) return;
    const interval = setInterval(async () => {
      if (parsedRows.length === 0) return;
      let hasChanges = false;
      const updated = await Promise.all(
        parsedRows.map(async (row) => {
          if (!row.twoFa) return row;
          const totp = await computeClientTotp(row.twoFa);
          if (totp && (totp.code !== row.totpCode || totp.remaining !== row.remaining)) {
            hasChanges = true;
            return { ...row, totpCode: totp.code, remaining: totp.remaining };
          }
          return row;
        })
      );
      if (hasChanges) {
        setParsedRows(updated);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [open, parsedRows]);

  // Parse raw text as user types or pastes
  useEffect(() => {
    if (!rawText.trim()) {
      setParsedRows([]);
      return;
    }

    const lines = rawText.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    let isCancelled = false;

    async function parseAll() {
      const results: ParsedViaPreview[] = [];
      for (const line of lines) {
        const parts = line.split("|").map((p) => p.trim());
        let uid = "";
        let pass = "";
        let twoFa = "";
        let email = "";
        let passMail = "";
        let backupMail = "";
        let passBackupMail = "";
        let hasCookie = line.includes("c_user=") || line.includes("xs=");
        let hasEaag = line.includes("EAAG");
        let hasEaab = line.includes("EAAB");

        if (parts.length >= 7) {
          uid = parts[0];
          pass = parts[1];
          twoFa = parts[2].replace(/\s+/g, "");
          email = parts[3];
          passMail = parts[4];
          backupMail = parts[5];
          passBackupMail = parts[6];
        } else if (parts.length === 5) {
          uid = parts[0];
          pass = parts[1];
          twoFa = parts[2].replace(/\s+/g, "");
          email = parts[3];
          passMail = parts[4];
        } else if (parts.length === 3) {
          uid = parts[0];
          pass = parts[1];
          twoFa = parts[2].replace(/\s+/g, "");
        } else if (parts.length === 2) {
          uid = parts[0];
          pass = parts[1];
        } else {
          // 1 string - check if UID
          const m = line.match(/\b\d{5,25}\b/);
          if (m) uid = m[0];
        }

        // Check extra pipe fields for cookies or tokens
        for (let i = 2; i < parts.length; i++) {
          const seg = parts[i];
          if (seg.includes("c_user=") || seg.includes("xs=")) hasCookie = true;
          if (seg.startsWith("EAAG")) hasEaag = true;
          if (seg.startsWith("EAAB")) hasEaab = true;
        }

        let totpCode = "";
        let remaining = 30;
        if (twoFa) {
          const clientTotp = await computeClientTotp(twoFa);
          if (clientTotp) {
            totpCode = clientTotp.code;
            remaining = clientTotp.remaining;
          }
        }

        results.push({
          raw: line,
          uid,
          pass,
          twoFa,
          email,
          passMail,
          backupMail,
          passBackupMail,
          hasCookie,
          hasEaag,
          hasEaab,
          totpCode,
          remaining,
        });
      }

      if (!isCancelled) {
        setParsedRows(results);
      }
    }

    void parseAll();
    return () => {
      isCancelled = true;
    };
  }, [rawText]);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  const copyToClipboard = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text);
      showToast(`Đã sao chép ${label}: ${text}`);
    } catch {
      showToast(`Không thể sao chép`);
    }
  };

  const handleExecuteImport = async () => {
    if (!rawText.trim()) {
      setFeedback({ text: "Vui lòng dán ít nhất 1 dòng định dạng VIA.", error: true });
      return;
    }

    setFeedback(null);
    setImportResponse(null);
    setIsSubmitting(true);

    try {
      // Step 1
      setCurrentStep(1);
      setStepLabel("[1/4] Đang lưu VIA & mã hóa thông tin an toàn...");
      await new Promise((r) => setTimeout(r, 400));

      // Step 2
      setCurrentStep(2);
      setStepLabel("[2/4] Đang đăng nhập & giải mã 2FA TOTP...");
      await new Promise((r) => setTimeout(r, 400));

      // Step 3
      setCurrentStep(3);
      setStepLabel("[3/4] Đang trích xuất Session Cookie & EAAG/EAAB...");

      // Execute endpoint
      const res = await importRawViasAndSync({
        raw_vias_text: rawText.trim(),
        auto_login_and_scan: autoLoginAndScan,
        proxy_url: proxyUrl.trim() || undefined,
      });

      // Step 4
      setCurrentStep(4);
      setStepLabel("[4/4] Đang quét sâu TKQC, BM, Fanpage, Pixel...");
      await new Promise((r) => setTimeout(r, 500));

      setImportResponse(res);
      showToast(`Nạp thành công ${res.imported_count} VIA!`);
      if (onSuccess) onSuccess();
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Có lỗi xảy ra khi nạp VIA và quét tài sản.",
        error: true,
      });
    } finally {
      setIsSubmitting(false);
      setCurrentStep(0);
      setStepLabel("");
    }
  };

  const handleExecuteTab2 = async () => {
    if (!tab2Input.trim()) {
      setFeedback({ text: "Vui lòng nhập nội dung Token, Cookie hoặc BM ID.", error: true });
      return;
    }

    setFeedback(null);
    setIsSubmitting(true);
    setCurrentStep(1);
    setStepLabel("Đang xử lý nạp nhanh & đồng bộ tài sản...");

    try {
      if (tab2Mode === "TOKEN") {
        await createVia({
          uid: tab2Uid.trim() || "VIA_TOKEN_" + Date.now().toString().slice(-6),
          password: "",
          access_token: tab2Input.trim(),
        });
        await forceSyncAllViaAssets();
        showToast("Đã lưu Token EAAG và kích hoạt đồng bộ tài sản!");
      } else if (tab2Mode === "COOKIE") {
        const uidMatch = tab2Input.match(/c_user=(\d+)/);
        const uid = tab2Uid.trim() || (uidMatch ? uidMatch[1] : "VIA_COOKIE_" + Date.now().toString().slice(-6));
        await createVia({
          uid,
          password: "",
          cookie: tab2Input.trim(),
        });
        await forceSyncAllViaAssets();
        showToast("Đã lưu Cookie phiên và xếp lịch đồng bộ tài sản!");
      } else {
        // BM List
        await forceSyncAllViaAssets();
        showToast("Đã gửi yêu cầu quét tài sản theo BM!");
      }

      if (onSuccess) onSuccess();
      setTab2Input("");
    } catch (err: unknown) {
      setFeedback({
        text: err instanceof Error ? err.message : "Lỗi khi thực thi nạp nhanh.",
        error: true,
      });
    } finally {
      setIsSubmitting(false);
      setCurrentStep(0);
      setStepLabel("");
    }
  };

  // Aggregated counts from response
  const summaryTotals = useMemo(() => {
    if (!importResponse || !importResponse.results) return null;
    let accounts = 0;
    let bms = 0;
    let pages = 0;
    let pixels = 0;
    for (const r of importResponse.results) {
      accounts += r.accounts_count || 0;
      bms += r.bms_count || 0;
      pages += r.pages_count || 0;
      pixels += r.pixels_count || 0;
    }
    return {
      vias: importResponse.imported_count,
      accounts,
      bms,
      pages,
      pixels,
    };
  }, [importResponse]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm">
      <div className="relative w-full max-w-4xl max-h-[92vh] overflow-y-auto rounded-2xl border border-[#2A2A32] bg-[#121214] p-6 shadow-2xl text-slate-100 space-y-5">
        {/* Toast */}
        {toastMessage && (
          <div className="absolute top-4 right-4 z-50 rounded-xl bg-emerald-600 px-4 py-2 text-xs font-semibold text-white shadow-xl animate-fade-in flex items-center gap-2">
            <MonoIcon name="check" width={14} />
            <span>{toastMessage}</span>
          </div>
        )}

        {/* Header */}
        <div className="flex items-start justify-between border-b border-[#2A2A32] pb-4">
          <div>
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <svg
                className="w-5 h-5 text-indigo-400"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              Nạp Nguyên Liệu &amp; Quét Sâu Toàn Bộ Tài Sản
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Hỗ trợ dán nguyên liệu VIA chuẩn, tự động tạo mã 2FA TOTP, giải đăng nhập, lấy Token EAAG/EAAB và quét toàn bộ TKQC, BM, Fanpage.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-[#202024] hover:text-white transition"
            aria-label="Đóng"
          >
            <MonoIcon name="close" width={18} />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-2 border-b border-[#2A2A32] pb-2">
          <button
            type="button"
            onClick={() => setActiveTab("raw_via")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-2 ${
              activeTab === "raw_via"
                ? "bg-indigo-600 text-white shadow-sm"
                : "bg-[#1E1E24] text-slate-400 hover:text-white"
            }`}
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
            </svg>
            Tab 1: Nạp Định Dạng VIA (uid|pass|2fa|mail...)
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("token_cookie")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-2 ${
              activeTab === "token_cookie"
                ? "bg-indigo-600 text-white shadow-sm"
                : "bg-[#1E1E24] text-slate-400 hover:text-white"
            }`}
          >
            <svg className="w-3.5 h-3.5 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
            </svg>
            Tab 2: Nạp Nhanh Bằng Token / Cookie / ID BM
          </button>
        </div>

        {/* Feedback message */}
        {feedback && (
          <div
            className={`rounded-xl px-4 py-3 text-xs font-medium border flex items-center justify-between ${
              feedback.error
                ? "bg-rose-950/60 border-rose-800/80 text-rose-200"
                : "bg-emerald-950/60 border-emerald-800/80 text-emerald-200"
            }`}
          >
            <span>{feedback.text}</span>
            <button
              type="button"
              onClick={() => setFeedback(null)}
              className="ml-2 text-slate-400 hover:text-white"
            >
              ×
            </button>
          </div>
        )}

        {/* TAB 1: RAW VIA */}
        {activeTab === "raw_via" && (
          <div className="space-y-4">
            {/* Input textarea */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className="text-xs font-bold text-slate-300 flex items-center gap-2">
                  <span>Dán Chuỗi VIA Định Dạng Pipe (|)</span>
                  <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-mono text-slate-400">
                    {parsedRows.length} dòng phát hiện
                  </span>
                </label>
                <button
                  type="button"
                  onClick={() =>
                    setRawText(
                      "100088123456789|MatKhauFB123|JBSWY3DPEHPK3PXP|mail@hotmail.com|PassMail123|backup@gmail.com|PassBackup123"
                    )
                  }
                  className="text-[11px] text-indigo-400 hover:underline"
                >
                  Dán chuỗi mẫu
                </button>
              </div>
              <textarea
                rows={4}
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                placeholder="uid|pass|2fa|mail|passmail|mailbackup|passmailbackup (Mỗi dòng 1 VIA, hoặc dán kèm cookie/token)"
                className="w-full rounded-xl border border-[#2A2A32] bg-[#18181B] p-3 font-mono text-xs text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
              />
            </div>

            {/* Live Preview Table */}
            {parsedRows.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-slate-300 flex items-center gap-2">
                    <span>Xem Trước &amp; Mã 2FA Live ({parsedRows.length} VIA)</span>
                  </h4>
                  <button
                    type="button"
                    onClick={() => setShowPasswords(!showPasswords)}
                    className="text-[11px] text-slate-400 hover:text-white flex items-center gap-1"
                  >
                    <span>{showPasswords ? "Ẩn mật khẩu" : "Hiện mật khẩu"}</span>
                  </button>
                </div>

                <div className="max-h-56 overflow-auto rounded-xl border border-[#2A2A32] bg-[#18181B]">
                  <table className="w-full text-left text-[11px]">
                    <thead className="bg-[#121214] text-slate-400 sticky top-0 border-b border-[#2A2A32]">
                      <tr>
                        <th className="py-2 px-3">UID</th>
                        <th className="py-2 px-3">Mật khẩu</th>
                        <th className="py-2 px-3">Mã 2FA (Live OTP)</th>
                        <th className="py-2 px-3">Email</th>
                        <th className="py-2 px-3">Pass Mail</th>
                        <th className="py-2 px-3">Cookie / Token</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#2A2A32] font-mono text-slate-300">
                      {parsedRows.map((row, idx) => (
                        <tr key={idx} className="hover:bg-slate-800/40">
                          <td className="py-2 px-3 font-semibold text-slate-200">
                            {row.uid || <span className="text-slate-500">Chưa rõ</span>}
                          </td>
                          <td className="py-2 px-3 text-slate-400">
                            {showPasswords ? row.pass || "—" : row.pass ? "••••••••" : "—"}
                          </td>
                          <td className="py-2 px-3">
                            {row.totpCode ? (
                              <div className="inline-flex items-center gap-1.5 bg-[#0e1017] border border-slate-700 rounded-lg px-2 py-0.5">
                                <span className="font-bold text-emerald-400 tabular-nums tracking-wider text-xs">
                                  {row.totpCode}
                                </span>
                                <span className="text-[10px] text-amber-400/80 font-mono tabular-nums">
                                  ({row.remaining}s)
                                </span>
                                <button
                                  type="button"
                                  onClick={() => copyToClipboard(row.totpCode!, "2FA OTP")}
                                  className="text-slate-400 hover:text-white ml-0.5"
                                  title="Sao chép 2FA"
                                >
                                  <MonoIcon name="copy" width={11} />
                                </button>
                              </div>
                            ) : (
                              <span className="text-slate-500">Không có 2FA</span>
                            )}
                          </td>
                          <td className="py-2 px-3 text-slate-300 truncate max-w-[140px]">
                            {row.email || "—"}
                          </td>
                          <td className="py-2 px-3 text-slate-400">
                            {showPasswords ? row.passMail || "—" : row.passMail ? "••••••••" : "—"}
                          </td>
                          <td className="py-2 px-3">
                            <div className="flex items-center gap-1">
                              {row.hasCookie && (
                                <span className="rounded bg-sky-950 px-1.5 py-0.5 text-[9px] font-bold text-sky-400 border border-sky-800/40">
                                  Cookie ✓
                                </span>
                              )}
                              {row.hasEaag && (
                                <span className="rounded bg-indigo-950 px-1.5 py-0.5 text-[9px] font-bold text-indigo-400 border border-indigo-800/40">
                                  EAAG ✓
                                </span>
                              )}
                              {row.hasEaab && (
                                <span className="rounded bg-purple-950 px-1.5 py-0.5 text-[9px] font-bold text-purple-400 border border-purple-800/40">
                                  EAAB ✓
                                </span>
                              )}
                              {!row.hasCookie && !row.hasEaag && !row.hasEaab && (
                                <span className="text-slate-500 text-[10px]">Cần Auto-Login</span>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Options */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 rounded-xl border border-[#2A2A32] bg-[#18181B] p-3 text-xs">
              <label className="flex items-center gap-2 cursor-pointer select-none text-slate-200 font-medium">
                <input
                  type="checkbox"
                  checked={autoLoginAndScan}
                  onChange={(e) => setAutoLoginAndScan(e.target.checked)}
                  className="rounded border-[#3A3A42] bg-[#121214] text-indigo-600 focus:ring-0"
                />
                <span>Tự động đăng nhập VIA &rarr; Lấy Cookie/Token &rarr; Quét toàn bộ TKQC, BM, Fanpage</span>
              </label>

              <div className="space-y-1">
                <label className="text-[11px] font-medium text-slate-400">
                  Proxy dùng chung (Tùy chọn)
                </label>
                <input
                  type="text"
                  value={proxyUrl}
                  onChange={(e) => setProxyUrl(e.target.value)}
                  placeholder="ip:port:user:pass (Áp dụng nếu VIA chưa có proxy riêng)"
                  className="w-full rounded-lg border border-[#2A2A32] bg-[#121214] px-2.5 py-1.5 font-mono text-xs text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
                />
              </div>
            </div>

            {/* Progress indicator */}
            {isSubmitting && (
              <div className="rounded-xl border border-indigo-500/40 bg-indigo-950/40 p-4 space-y-2 animate-pulse">
                <div className="flex items-center justify-between text-xs font-bold text-indigo-300">
                  <span>{stepLabel}</span>
                  <span>{currentStep}/4</span>
                </div>
                <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                  <div
                    className="bg-indigo-500 h-1.5 transition-all duration-300"
                    style={{ width: `${(currentStep / 4) * 100}%` }}
                  />
                </div>
              </div>
            )}

            {/* Results Summary Card */}
            {summaryTotals && (
              <div className="rounded-xl border border-emerald-500/40 bg-emerald-950/30 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-emerald-300 flex items-center gap-1.5">
                    <MonoIcon name="check" width={14} />
                    <span>Kết Quả Nạp &amp; Quét Toàn Bộ Tài Sản</span>
                  </h4>
                  <span className="text-[11px] text-slate-400">
                    {summaryTotals.vias} VIA đã xử lý
                  </span>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-center">
                  <div className="bg-[#121214] p-2.5 rounded-lg border border-[#2A2A32]">
                    <div className="text-[10px] text-slate-400 uppercase font-semibold">VIA Nạp</div>
                    <div className="text-base font-bold text-white tabular-nums">{summaryTotals.vias}</div>
                  </div>
                  <div className="bg-[#121214] p-2.5 rounded-lg border border-[#2A2A32]">
                    <div className="text-[10px] text-slate-400 uppercase font-semibold">TKQC (Ads)</div>
                    <div className="text-base font-bold text-indigo-400 tabular-nums">{summaryTotals.accounts}</div>
                  </div>
                  <div className="bg-[#121214] p-2.5 rounded-lg border border-[#2A2A32]">
                    <div className="text-[10px] text-slate-400 uppercase font-semibold">BMs</div>
                    <div className="text-base font-bold text-purple-400 tabular-nums">{summaryTotals.bms}</div>
                  </div>
                  <div className="bg-[#121214] p-2.5 rounded-lg border border-[#2A2A32]">
                    <div className="text-[10px] text-slate-400 uppercase font-semibold">Fanpage</div>
                    <div className="text-base font-bold text-emerald-400 tabular-nums">{summaryTotals.pages}</div>
                  </div>
                  <div className="bg-[#121214] p-2.5 rounded-lg border border-[#2A2A32]">
                    <div className="text-[10px] text-slate-400 uppercase font-semibold">Pixel</div>
                    <div className="text-base font-bold text-amber-400 tabular-nums">{summaryTotals.pixels}</div>
                  </div>
                </div>

                {/* Per-VIA detailed outcomes */}
                <div className="max-h-40 overflow-auto divide-y divide-[#2A2A32] rounded-lg border border-[#2A2A32] bg-[#121214] text-[11px]">
                  {importResponse?.results.map((res: ImportRawViasResult, i: number) => (
                    <div key={i} className="p-2 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-slate-200">{res.fb_uid}</span>
                        <span
                          className={`rounded px-1.5 py-0.2 text-[9px] font-bold ${
                            res.login_status === "READY"
                              ? "bg-emerald-950 text-emerald-300 border border-emerald-800/40"
                              : res.login_status === "CHECKPOINT"
                              ? "bg-rose-950 text-rose-300 border border-rose-800/40"
                              : "bg-slate-800 text-slate-300"
                          }`}
                        >
                          {res.login_status}
                        </span>
                        {res.totp_code && (
                          <span className="font-mono text-emerald-400 font-bold">
                            2FA: {res.totp_code}
                          </span>
                        )}
                      </div>
                      <div className="text-slate-400 text-[10px]">
                        {res.accounts_count} TKQC | {res.bms_count} BM | {res.pages_count} Page
                        {res.message ? ` — ${res.message}` : ""}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Submit Bar */}
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-300 hover:bg-[#1E1E24] transition"
              >
                Đóng
              </button>
              <button
                type="button"
                disabled={isSubmitting || parsedRows.length === 0}
                onClick={handleExecuteImport}
                className="px-5 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/30 transition disabled:opacity-50 flex items-center gap-2"
              >
                {isSubmitting ? (
                  <>
                    <svg className="animate-spin h-3.5 w-3.5 text-white" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                    </svg>
                    <span>Đang Xử Lý...</span>
                  </>
                ) : (
                  <>
                    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                    </svg>
                    <span>Đăng Nhập Tự Động &amp; Quét Toàn Bộ Tài Sản</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* TAB 2: FAST TOKEN / COOKIE / BM */}
        {activeTab === "token_cookie" && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setTab2Mode("TOKEN")}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium ${
                  tab2Mode === "TOKEN" ? "bg-indigo-600 text-white" : "bg-[#18181B] text-slate-400"
                }`}
              >
                EAAG / EAAB Token
              </button>
              <button
                type="button"
                onClick={() => setTab2Mode("COOKIE")}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium ${
                  tab2Mode === "COOKIE" ? "bg-indigo-600 text-white" : "bg-[#18181B] text-slate-400"
                }`}
              >
                Session Cookie
              </button>
              <button
                type="button"
                onClick={() => setTab2Mode("BM_LIST")}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium ${
                  tab2Mode === "BM_LIST" ? "bg-indigo-600 text-white" : "bg-[#18181B] text-slate-400"
                }`}
              >
                Quét Theo Danh Sách BM
              </button>
            </div>

            <div className="space-y-3">
              {tab2Mode !== "BM_LIST" && (
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-300">
                    UID Facebook (Tùy chọn nếu có sẵn)
                  </label>
                  <input
                    type="text"
                    value={tab2Uid}
                    onChange={(e) => setTab2Uid(e.target.value)}
                    placeholder="100088..."
                    className="w-full rounded-xl border border-[#2A2A32] bg-[#18181B] px-3 py-2 font-mono text-xs text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              )}

              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-300">
                  {tab2Mode === "TOKEN"
                    ? "Dán Token EAAG / EAAB"
                    : tab2Mode === "COOKIE"
                    ? "Dán Cookie Phiên (c_user=...; xs=...; datr=...)"
                    : "Danh Sách BM ID (mỗi dòng 1 ID)"}
                </label>
                <textarea
                  rows={5}
                  value={tab2Input}
                  onChange={(e) => setTab2Input(e.target.value)}
                  placeholder={
                    tab2Mode === "TOKEN"
                      ? "EAAG..."
                      : tab2Mode === "COOKIE"
                      ? "sb=...; datr=...; c_user=1000...; xs=..."
                      : "123456789012345\n987654321098765"
                  }
                  className="w-full rounded-xl border border-[#2A2A32] bg-[#18181B] p-3 font-mono text-xs text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
                />
              </div>
            </div>

            {/* Submit Bar */}
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-300 hover:bg-[#1E1E24] transition"
              >
                Đóng
              </button>
              <button
                type="button"
                disabled={isSubmitting || !tab2Input.trim()}
                onClick={handleExecuteTab2}
                className="px-5 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/30 transition disabled:opacity-50 flex items-center gap-2"
              >
                {isSubmitting ? "Đang Quét..." : "Quét Sâu Tài Sản Nhanh"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
