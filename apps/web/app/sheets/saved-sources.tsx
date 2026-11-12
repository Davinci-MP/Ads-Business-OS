"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  fetchJson,
  patchJson,
  postJson,
  SHEETS_REPORT_WORKBOOK_KEY,
  type SavedSheetSnapshot,
  type SavedSheetSnapshotEnvelope,
  type SavedSheetSource,
  type SheetSyncAttempt,
  type SheetSyncHistoryEnvelope,
} from "../../lib/api";
import { formatVnd } from "../../lib/vnd.mjs";

type Customer = { id: number; name: string };
type Link = { sheet_id: number; source_title: string; customer_id: number };
type Rollover = {
  previous_closed: boolean;
  unlinked_previous: string[];
  unlinked_current: string[];
  customers: {
    customer_id: number;
    previous_source: string | null;
    next_source: string | null;
    previous_value: string | null;
    next_value: string | null;
    status: string;
    difference: string | null;
    tolerance: string;
  }[];
};

function timeText(value: string) {
  return new Date(value).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" });
}

const BTN =
  "rounded-xl bg-indigo-600 px-3.5 py-2 text-xs font-semibold text-white shadow-lg shadow-indigo-600/20 hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 transition";
const BTN_ALT =
  "rounded-xl border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-medium text-slate-200 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50 transition";
const INPUT =
  "rounded-xl border border-slate-700 bg-[#1E293B] px-3.5 py-2 text-xs text-slate-100 placeholder-slate-400 focus:border-indigo-500 focus:outline-none";
const HISTORY_PREVIEW = 5;

function apiMessage(err: unknown) {
  const text = err instanceof Error ? err.message : String(err);
  const json = text.slice(text.indexOf("{"));
  try {
    const detail = (JSON.parse(json) as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return "Dữ liệu nhập chưa hợp lệ; kiểm tra tháng, năm và đường dẫn.";
  } catch {
    /* giữ nguyên thông báo gốc */
  }
  return text;
}

export default function SavedSources() {
  const thisYear = new Date().getFullYear();
  const [sources, setSources] = useState<SavedSheetSource[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [month, setMonth] = useState("");
  const [year, setYear] = useState(String(thisYear));
  const [name, setName] = useState("");
  const [nameEdited, setNameEdited] = useState(false);
  const [workbook, setWorkbook] = useState("");
  const [replace, setReplace] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [autoSync, setAutoSync] = useState(false);
  const [makeDefault, setMakeDefault] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formErrors, setFormErrors] = useState<{
    month?: string;
    year?: string;
    workbook?: string;
    name?: string;
    form?: string;
  }>({});
  const [saved, setSaved] = useState<{ id: number; period: string; status: string; error: string | null } | null>(null);
  const [showAllHistory, setShowAllHistory] = useState(false);
  const [snapshots, setSnapshots] = useState<SavedSheetSnapshot[]>([]);
  const [history, setHistory] = useState<SheetSyncAttempt[]>([]);
  const [snapshotId, setSnapshotId] = useState("");
  const [snapshot, setSnapshot] = useState<SavedSheetSnapshot | null>(null);
  const [acknowledge, setAcknowledge] = useState(false);
  const [links, setLinks] = useState<Link[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [sheetId, setSheetId] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [confirmRenamed, setConfirmRenamed] = useState(false);
  const [previousId, setPreviousId] = useState("");
  const [rollover, setRollover] = useState<Rollover | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const selected = sources.find((source) => String(source.id) === selectedId);
  const periodValue = month && /^\d{4}$/.test(year) ? `${year}-${month}` : "";
  const suggestedName = month && /^\d{4}$/.test(year) ? `Báo cáo tháng ${month}/${year}` : "";
  const shownName = nameEdited ? name : suggestedName;

  const refreshSources = useCallback(async () => {
    const data = await fetchJson<{ sources: SavedSheetSource[] }>("/sheets/sources");
    setSources(data.sources);
    setSelectedId((id) => id || String(data.sources.find((source) => source.is_default)?.id ?? data.sources[0]?.id ?? ""));
  }, []);

  useEffect(() => {
    setWorkbook(window.sessionStorage.getItem(SHEETS_REPORT_WORKBOOK_KEY) ?? "");
    void Promise.all([refreshSources(), fetchJson<Customer[]>("/customers").then(setCustomers)]).catch((err: unknown) =>
      setError(err instanceof Error ? err.message : String(err)),
    );
  }, [refreshSources]);

  const refreshDetail = useCallback(async () => {
    if (!selectedId) return;
    const [versions, attempts, savedLinks] = await Promise.all([
      fetchJson<SavedSheetSnapshotEnvelope>(`/sheets/sources/${selectedId}/snapshots`),
      fetchJson<SheetSyncHistoryEnvelope>(`/sheets/sources/${selectedId}/history`),
      fetchJson<Link[]>(`/sheets/sources/${selectedId}/links`),
    ]);
    setSnapshots(versions.snapshots);
    setHistory(attempts.history);
    setLinks(savedLinks);
    setSnapshotId((id) =>
      versions.snapshots.some((version) => String(version.id) === id)
        ? id
        : String(versions.snapshots[0]?.id ?? ""),
    );
  }, [selectedId]);

  useEffect(() => {
    setSnapshot(null);
    setSnapshots([]);
    setHistory([]);
    setLinks([]);
    setSnapshotId("");
    setRollover(null);
    setShowAllHistory(false);
    void refreshDetail().catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, [refreshDetail]);

  useEffect(() => {
    let active = true;
    setSnapshot(null);
    if (selectedId && snapshotId) {
      fetchJson<SavedSheetSnapshot>(`/sheets/sources/${selectedId}/report?snapshot_id=${snapshotId}`)
        .then((value) => {
          if (active) setSnapshot(value);
        })
        .catch((err: unknown) => {
          if (active) setError(err instanceof Error ? err.message : String(err));
        });
    }
    return () => {
      active = false;
    };
  }, [selectedId, snapshotId]);

  async function run(action: () => Promise<void>, success: string) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await action();
      await refreshSources();
      setMessage(success);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function createSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const errors: typeof formErrors = {};
    if (!month) errors.month = "Chọn tháng.";
    if (!/^\d{4}$/.test(year) || Number(year) < 2000 || Number(year) > 2100)
      errors.year = "Nhập năm 4 chữ số (2000–2100).";
    if (!workbook.trim()) errors.workbook = "Dán link hoặc ID Google Sheets.";
    if (!shownName.trim()) errors.name = "Nhập tên báo cáo.";
    setFormErrors(errors);
    setSaved(null);
    if (Object.keys(errors).length > 0) return;
    setSaving(true);
    setMessage(null);
    try {
      const source = await postJson<SavedSheetSource>("/sheets/sources", {
        spreadsheet: workbook.trim(),
        period: periodValue,
        name: shownName.trim(),
        replace_existing: replace,
        set_default: makeDefault,
        sync_enabled: autoSync,
      });
      await refreshSources();
      setSelectedId(String(source.id));
      setSaved({
        id: source.id,
        period: source.period,
        status: source.last_attempt?.status ?? "CHƯA ĐỌC",
        error: source.last_attempt?.error ?? null,
      });
      setReplace(false);
      setConflict(false);
      setWorkbook("");
    } catch (err) {
      const text = apiMessage(err);
      if (/thay thế/.test(text)) {
        setConflict(true);
        setFormErrors({
          form: `Kỳ ${periodValue} đã có một nguồn đang dùng. Tích xác nhận thay nguồn rồi bấm lưu lại; bản cũ vẫn được giữ trong lịch sử.`,
        });
      } else {
        setFormErrors({ form: text });
      }
    } finally {
      setSaving(false);
    }
  }

  const visibleHistory = showAllHistory ? history : history.slice(0, HISTORY_PREVIEW);

  return (
    <section
      id="saved-sources"
      className="my-6 rounded-2xl border border-slate-800/80 bg-[#111827]/95 p-5 shadow-xl backdrop-blur-md text-slate-100 space-y-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <span></span> Báo Cáo Sheets Theo Tháng
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Chế độ chỉ đọc Google Sheets; tự động đồng bộ mỗi 15 phút khi backend chạy và nguồn được bật.
          </p>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-800/60 bg-rose-950/40 p-4 text-xs text-rose-200" role="alert">
          {error}
        </div>
      )}
      {message && (
        <div className="rounded-xl border border-emerald-800/60 bg-emerald-950/40 p-4 text-xs text-emerald-200" role="status">
          {message}
        </div>
      )}

      {/* Form thêm báo cáo */}
      <form
        onSubmit={(e) => void createSource(e)}
        noValidate
        className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/90 p-4"
        aria-label="Thêm báo cáo tháng"
      >
        <h3 className="font-semibold text-sm text-slate-200 flex items-center gap-2">
          <span></span> Thêm Báo Cáo Tháng Mới
        </h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="text-xs font-medium text-slate-300">
            Tháng
            <select
              value={month}
              onChange={(e) => {
                setMonth(e.target.value);
                setConflict(false);
                setReplace(false);
              }}
              className={`${INPUT} mt-1 w-full`}
              aria-invalid={!!formErrors.month}
            >
              <option value="">Chọn tháng…</option>
              {Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, "0")).map((m) => (
                <option key={m} value={m}>
                  Tháng {m}
                </option>
              ))}
            </select>
            {formErrors.month && <span className="mt-1 block text-[11px] text-rose-400">{formErrors.month}</span>}
          </label>
          <label className="text-xs font-medium text-slate-300">
            Năm
            <input
              inputMode="numeric"
              maxLength={4}
              value={year}
              onChange={(e) => {
                setYear(e.target.value.replace(/\D/g, ""));
                setConflict(false);
                setReplace(false);
              }}
              className={`${INPUT} mt-1 w-full`}
              aria-invalid={!!formErrors.year}
            />
            {formErrors.year && <span className="mt-1 block text-[11px] text-rose-400">{formErrors.year}</span>}
          </label>
          <label className="sm:col-span-2 text-xs font-medium text-slate-300">
            Link Google Sheets
            <input
              value={workbook}
              onChange={(e) => setWorkbook(e.target.value)}
              placeholder="https://docs.google.com/spreadsheets/d/… hoặc ID"
              className={`${INPUT} mt-1 w-full`}
              aria-invalid={!!formErrors.workbook}
            />
            {formErrors.workbook && <span className="mt-1 block text-[11px] text-rose-400">{formErrors.workbook}</span>}
          </label>
        </div>
        <label className="block text-xs font-medium text-slate-300">
          Tên báo cáo
          <input
            value={shownName}
            onChange={(e) => {
              setName(e.target.value);
              setNameEdited(true);
            }}
            className={`${INPUT} mt-1 w-full max-w-md`}
            aria-invalid={!!formErrors.name}
          />
          {formErrors.name && <span className="mt-1 block text-[11px] text-rose-400">{formErrors.name}</span>}
        </label>
        <div className="flex flex-wrap gap-4 text-xs text-slate-300">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={autoSync}
              onChange={(e) => setAutoSync(e.target.checked)}
              className="accent-indigo-500 rounded"
            />
            Tự đồng bộ mỗi 15 phút (mặc định tắt)
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={makeDefault}
              onChange={(e) => setMakeDefault(e.target.checked)}
              className="accent-indigo-500 rounded"
            />
            Đặt làm nguồn mặc định
          </label>
          {conflict && (
            <label className="flex items-center gap-2 font-medium text-amber-400 cursor-pointer">
              <input
                type="checkbox"
                checked={replace}
                onChange={(e) => setReplace(e.target.checked)}
                className="accent-amber-500 rounded"
              />
              Xác nhận thay nguồn đang dùng của kỳ {periodValue}
            </label>
          )}
        </div>
        {formErrors.form && (
          <div className="rounded-xl border border-rose-800 bg-rose-950/40 p-3 text-xs text-rose-300" role="alert">
            {formErrors.form}
          </div>
        )}
        {saving && (
          <p className="text-xs text-sky-400 animate-pulse">
            Đang kiểm tra và đọc báo cáo… có thể mất tới một phút.
          </p>
        )}
        {saved && (
          <div
            className={`rounded-xl border p-3 text-xs ${
              saved.status === "ERROR" || saved.status === "CHƯA ĐỌC"
                ? "border-amber-800 bg-amber-950/40 text-amber-300"
                : "border-emerald-800 bg-emerald-950/40 text-emerald-300"
            }`}
          >
            {saved.status === "ERROR" || saved.status === "CHƯA ĐỌC" ? (
              <>
                Đã lưu cấu hình kỳ {saved.period} nhưng chưa đọc được báo cáo: {saved.error ?? "chưa có lần đọc"}. Kiểm
                tra quyền chia sẻ cho service account rồi bấm “Cập nhật ngay” để thử lại.
              </>
            ) : (
              <>
                Đã lưu kỳ {saved.period}
                {saved.status === "READY" ? "" : ` (${saved.status}: có cảnh báo chất lượng dữ liệu)`}.
              </>
            )}{" "}
            <a href="#source-detail" className="font-semibold underline hover:text-white">
              Xem báo cáo
            </a>
          </div>
        )}
        <button type="submit" disabled={saving || busy} className={BTN}>
          {saving ? "Đang kiểm tra…" : "Kiểm tra và lưu báo cáo"}
        </button>
      </form>

      {/* Danh sách nguồn đã lưu */}
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
          <h3 className="font-semibold text-sm text-slate-200">Nguồn Đã Lưu ({sources.length})</h3>
          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-300">Chọn nguồn:</label>
            <select value={selectedId} onChange={(e) => setSelectedId(e.target.value)} className={INPUT}>
              <option value="">Chọn nguồn...</option>
              {sources.map((source) => (
                <option key={source.id} value={source.id}>
                  {source.period} · {source.name}
                  {source.active ? "" : " · đã thay thế"}
                </option>
              ))}
            </select>
          </div>
        </div>

        {selected && (
          <div id="source-detail" className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
              <div>
                <div className="text-sm font-bold text-white flex items-center gap-2">
                  <span>{selected.period}</span> — <span>{selected.name}</span>
                </div>
                <div className="flex items-center gap-2 mt-1 text-xs text-slate-400">
                  <span>Mapping v{selected.mapping_version}</span>
                  <span>·</span>
                  <span className={selected.sync_enabled ? "text-emerald-400" : "text-slate-500"}>
                    {selected.sync_enabled ? "Tự đồng bộ BẬT" : "Tự đồng bộ TẮT"}
                  </span>
                  <span>·</span>
                  <span className={selected.is_default ? "text-indigo-400 font-semibold" : "text-slate-500"}>
                    {selected.is_default ? "Nguồn mặc định" : "Nguồn phụ"}
                  </span>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  className={BTN}
                  disabled={busy || !selected.active}
                  onClick={() =>
                    void run(async () => {
                      const attempt = await postJson<SheetSyncAttempt>(`/sheets/sources/${selected.id}/sync`);
                      await refreshDetail();
                      if (attempt.status === "ERROR") throw new Error(attempt.error ?? "Đọc nguồn thất bại.");
                    }, "Đã cập nhật bản lưu thành công.")
                  }
                >
                  Cập nhật ngay
                </button>
                <button
                  className={BTN_ALT}
                  disabled={busy || !selected.active || selected.is_default}
                  onClick={() =>
                    void run(async () => {
                      await patchJson(`/sheets/sources/${selected.id}`, { set_default: true });
                    }, "Đã chọn làm nguồn mặc định.")
                  }
                >
                  Đặt mặc định
                </button>
                <button
                  className={BTN_ALT}
                  disabled={busy || !selected.active}
                  onClick={() =>
                    void run(async () => {
                      await patchJson(`/sheets/sources/${selected.id}`, { sync_enabled: !selected.sync_enabled });
                    }, "Đã cập nhật lịch đồng bộ.")
                  }
                >
                  {selected.sync_enabled ? "Tắt tự đồng bộ" : "Bật tự đồng bộ"}
                </button>
              </div>
            </div>

            {/* Lịch sử đồng bộ */}
            <div className="space-y-2">
              <h4 className="font-semibold text-xs text-slate-300">Lịch Sử Đồng Bộ</h4>
              {history.length === 0 ? (
                <p className="text-xs text-slate-500">Chưa có lần đọc nào.</p>
              ) : (
                <div className="space-y-1">
                  <ul className="text-xs text-slate-300 space-y-1">
                    {visibleHistory.map((item) => (
                      <li
                        key={item.id}
                        className="flex flex-wrap items-center gap-2 p-2 rounded-lg bg-slate-900/90 border border-slate-800/80"
                      >
                        <span className="font-mono text-slate-400">{timeText(item.started_at)}</span>
                        <span>·</span>
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-300">
                          {item.trigger}
                        </span>
                        <span>·</span>
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                            item.status === "SUCCESS"
                              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                              : item.status === "PARTIAL"
                                ? "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                                : "bg-rose-500/10 text-rose-400 border border-rose-500/30"
                          }`}
                        >
                          {item.status}
                        </span>
                        {item.snapshot_id && <span className="text-slate-400">· bản #{item.snapshot_id}</span>}
                        {item.error && <span className="text-rose-400">· {item.error}</span>}
                      </li>
                    ))}
                  </ul>
                  {history.length > HISTORY_PREVIEW && (
                    <button
                      type="button"
                      className={`${BTN_ALT} mt-2`}
                      onClick={() => setShowAllHistory((v) => !v)}
                    >
                      {showAllHistory ? "Thu gọn" : `Xem thêm (${history.length - HISTORY_PREVIEW} lượt)`}
                    </button>
                  )}
                </div>
              )}
            </div>

            {/* Bản lưu và chốt kỳ */}
            <div className="space-y-3 pt-3 border-t border-slate-800">
              <h4 className="font-semibold text-xs text-slate-300">Bản Lưu & Chốt Kỳ</h4>
              <div className="flex items-center gap-2">
                <label className="text-xs text-slate-300">Bản lưu:</label>
                <select
                  value={snapshotId}
                  onChange={(e) => {
                    setSnapshotId(e.target.value);
                    setAcknowledge(false);
                  }}
                  className={INPUT}
                >
                  {snapshots.map((item) => (
                    <option value={item.id} key={item.id}>
                      #{item.id} · {timeText(item.read_at)} · {item.quality}
                      {selected.closure?.snapshot_id === item.id ? " · BẢN CHỐT" : ""}
                    </option>
                  ))}
                </select>
              </div>

              {snapshot?.report && (
                <div className="space-y-3 rounded-xl bg-slate-900/90 border border-slate-800 p-3 text-xs">
                  <div className="flex flex-wrap items-center gap-3">
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                        snapshot.quality === "READY"
                          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                          : "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                      }`}
                    >
                      {snapshot.quality}
                    </span>
                    <span className="text-slate-300">
                      {(snapshot.report.customers ?? []).length} tab khách · {snapshot.report.issues.length} cảnh báo nguồn
                    </span>
                  </div>

                  {snapshot.quality !== "READY" && (
                    <label className="flex items-center gap-2 font-medium text-amber-300 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={acknowledge}
                        onChange={(e) => setAcknowledge(e.target.checked)}
                        className="accent-amber-500 rounded"
                      />
                      Tôi đã xem và chấp nhận bản còn thiếu khi chốt
                    </label>
                  )}

                  <details className="text-xs text-slate-400">
                    <summary className="cursor-pointer hover:text-slate-200 font-medium">
                      Phần thiếu và cảnh báo chi tiết ({snapshot.report.issues.length})
                    </summary>
                    <ul className="mt-2 space-y-1 list-disc list-inside text-amber-300">
                      {snapshot.report.issues.map((issue, index) => (
                        <li key={index}>
                          <span className="font-semibold text-white">{issue.source}:</span> {issue.message}
                        </li>
                      ))}
                    </ul>
                  </details>

                  <button
                    className={BTN}
                    disabled={busy || !!selected.closure || (snapshot.quality !== "READY" && !acknowledge)}
                    onClick={() =>
                      void run(async () => {
                        await postJson(`/sheets/sources/${selected.id}/closure`, {
                          snapshot_id: Number(snapshotId),
                          acknowledge_partial: acknowledge,
                        });
                      }, "Đã chốt bản được chọn; các lần đọc sau không ghi đè bản chốt.")
                    }
                  >
                    {selected.closure ? "Kỳ đã chốt" : "Chốt kỳ với bản đã chọn"}
                  </button>
                </div>
              )}
            </div>

            {/* Liên kết định danh khách */}
            <div className="space-y-3 pt-3 border-t border-slate-800">
              <h4 className="font-semibold text-xs text-slate-300">Liên Kết Định Danh Khách Cho Chuyển Kỳ</h4>
              <p className="text-xs text-slate-400">
                Người vận hành xác nhận từng tab với khách nội bộ; không ghép theo tên hoặc vị trí.
              </p>
              {links.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {links.map((link) => (
                    <div
                      key={link.sheet_id}
                      className="rounded-lg bg-slate-900 border border-slate-800 px-2.5 py-1 text-xs text-slate-300"
                    >
                      <span className="font-semibold text-white">{link.source_title}</span> →{" "}
                      <span className="text-emerald-400">
                        {customers.find((c) => c.id === link.customer_id)?.name ?? `khách #${link.customer_id}`}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              <div className="flex flex-wrap gap-2 items-center">
                <select value={sheetId} onChange={(e) => setSheetId(e.target.value)} className={INPUT}>
                  <option value="">Chọn tab khách...</option>
                  {(snapshot?.report?.customers ?? [])
                    .filter((c) => c.sheet_id !== null)
                    .map((c) => (
                      <option key={c.sheet_id} value={c.sheet_id ?? ""}>
                        {c.source_sheet}
                      </option>
                    ))}
                </select>
                <select value={customerId} onChange={(e) => setCustomerId(e.target.value)} className={INPUT}>
                  <option value="">Chọn khách nội bộ...</option>
                  {customers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} · #{c.id}
                    </option>
                  ))}
                </select>
                <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={confirmRenamed}
                    onChange={(e) => setConfirmRenamed(e.target.checked)}
                    className="accent-indigo-500 rounded"
                  />
                  Xác nhận tab đã đổi tên
                </label>
                <button
                  className={BTN}
                  disabled={busy || !sheetId || !customerId}
                  onClick={() =>
                    void run(async () => {
                      await postJson(`/sheets/sources/${selected.id}/links`, {
                        sheet_id: Number(sheetId),
                        customer_id: Number(customerId),
                        confirm_renamed: confirmRenamed,
                      });
                      setConfirmRenamed(false);
                      await refreshDetail();
                    }, "Đã xác nhận liên kết khách.")
                  }
                >
                  Xác nhận liên kết
                </button>
              </div>
            </div>

            {/* Đối chiếu chuyển kỳ */}
            <div className="space-y-3 pt-3 border-t border-slate-800">
              <h4 className="font-semibold text-xs text-slate-300">Đối Chiếu Chuyển Kỳ</h4>
              <div className="flex flex-wrap gap-2 items-center">
                <select
                  value={previousId}
                  onChange={(e) => {
                    setPreviousId(e.target.value);
                    setRollover(null);
                  }}
                  className={INPUT}
                >
                  <option value="">Chọn nguồn kỳ trước đã chốt...</option>
                  {sources
                    .filter((source) => source.id !== selected.id)
                    .map((source) => (
                      <option key={source.id} value={source.id}>
                        {source.period} · {source.name}
                      </option>
                    ))}
                </select>
                <button
                  className={BTN_ALT}
                  disabled={busy || !previousId}
                  onClick={() =>
                    void run(async () => {
                      setRollover(
                        await fetchJson<Rollover>(
                          `/sheets/sources/${selected.id}/rollover?previous_source_id=${previousId}`,
                        ),
                      );
                    }, "Đã đối chiếu; không thay đổi số trên Sheets.")
                  }
                >
                  Xem đối chiếu
                </button>
              </div>

              {rollover && (
                <div className="rounded-xl bg-slate-900/90 border border-slate-800 p-3 text-xs space-y-2">
                  {!rollover.previous_closed && (
                    <p className="text-amber-400">
                      <strong>Chưa chốt</strong> — đối chiếu tạm L1 kỳ trước với J1 kỳ này; đối chiếu chính thức chỉ
                      dựa trên bản chốt.
                    </p>
                  )}
                  {rollover.customers.map((row) => (
                    <div key={row.customer_id} className="flex flex-wrap justify-between gap-2 border-b border-slate-800 pb-1">
                      <span>
                        <strong className="text-white">
                          {customers.find((c) => c.id === row.customer_id)?.name ?? `Khách #${row.customer_id}`}
                        </strong>{" "}
                        · {row.status}
                      </span>
                      <span className="font-mono text-slate-300">
                        {formatVnd(row.previous_value)} → {formatVnd(row.next_value)} · chênh{" "}
                        <span className={Number(row.difference) !== 0 ? "text-amber-400" : "text-emerald-400"}>
                          {formatVnd(row.difference)} VND
                        </span>
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
