"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  fetchJson, patchJson, postJson, SHEETS_REPORT_WORKBOOK_KEY,
  type SavedSheetSnapshot, type SavedSheetSnapshotEnvelope, type SavedSheetSource,
  type SheetSyncAttempt, type SheetSyncHistoryEnvelope,
} from "../../lib/api";
import { formatVnd } from "../../lib/vnd.mjs";

type Customer = { id: number; name: string };
type Link = { sheet_id: number; source_title: string; customer_id: number };
type Rollover = {
  previous_closed: boolean;
  unlinked_previous: string[];
  unlinked_current: string[];
  customers: {
    customer_id: number; previous_source: string | null; next_source: string | null;
    previous_value: string | null; next_value: string | null; status: string;
    difference: string | null; tolerance: string;
  }[];
};

function timeText(value: string) {
  return new Date(value).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" });
}

const BTN = "rounded-md border border-sky-700 bg-sky-700 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-50";
const BTN_ALT = "rounded-md border border-sky-700 bg-white px-3 py-1.5 text-sm font-medium text-sky-800 shadow-sm hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-50";
const INPUT = "rounded border border-slate-400 bg-white p-1.5";
const HISTORY_PREVIEW = 5;

function apiMessage(err: unknown) {
  const text = err instanceof Error ? err.message : String(err);
  const json = text.slice(text.indexOf("{"));
  try {
    const detail = (JSON.parse(json) as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return "Dữ liệu nhập chưa hợp lệ; kiểm tra tháng, năm và đường dẫn.";
  } catch { /* giữ nguyên thông báo gốc */ }
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
  const [formErrors, setFormErrors] = useState<{ month?: string; year?: string; workbook?: string; name?: string; form?: string }>({});
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
    void Promise.all([refreshSources(), fetchJson<Customer[]>("/customers").then(setCustomers)]).catch(
      (err: unknown) => setError(err instanceof Error ? err.message : String(err)),
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
    setSnapshotId((id) => versions.snapshots.some((version) => String(version.id) === id) ? id : String(versions.snapshots[0]?.id ?? ""));
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
        .then((value) => { if (active) setSnapshot(value); })
        .catch((err: unknown) => { if (active) setError(err instanceof Error ? err.message : String(err)); });
    }
    return () => { active = false; };
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
    if (!/^\d{4}$/.test(year) || Number(year) < 2000 || Number(year) > 2100) errors.year = "Nhập năm 4 chữ số (2000–2100).";
    if (!workbook.trim()) errors.workbook = "Dán link hoặc ID Google Sheets.";
    if (!shownName.trim()) errors.name = "Nhập tên báo cáo.";
    setFormErrors(errors);
    setSaved(null);
    if (Object.keys(errors).length > 0) return;
    setSaving(true);
    setMessage(null);
    try {
      const source = await postJson<SavedSheetSource>("/sheets/sources", {
        spreadsheet: workbook.trim(), period: periodValue, name: shownName.trim(), replace_existing: replace,
        set_default: makeDefault, sync_enabled: autoSync,
      });
      await refreshSources();
      setSelectedId(String(source.id));
      setSaved({
        id: source.id, period: source.period,
        status: source.last_attempt?.status ?? "CHƯA ĐỌC", error: source.last_attempt?.error ?? null,
      });
      setReplace(false);
      setConflict(false);
      setWorkbook("");
    } catch (err) {
      const text = apiMessage(err);
      if (/thay thế/.test(text)) {
        setConflict(true);
        setFormErrors({ form: `Kỳ ${periodValue} đã có một nguồn đang dùng. Tích xác nhận thay nguồn rồi bấm lưu lại; bản cũ vẫn được giữ trong lịch sử.` });
      } else {
        setFormErrors({ form: text });
      }
    } finally {
      setSaving(false);
    }
  }

  const visibleHistory = showAllHistory ? history : history.slice(0, HISTORY_PREVIEW);

  return (
    <section id="saved-sources" className="my-6 rounded-xl border border-sky-200 bg-sky-50 p-4">
      <h2 className="text-lg font-semibold">Báo cáo Sheets theo tháng</h2>
      <p className="my-2 text-sm">Chỉ đọc Sheets; đồng bộ mỗi 15 phút khi backend chạy và nguồn bật tự đồng bộ.</p>
      {error && <p role="alert" className="my-2 text-red-700">{error}</p>}
      {message && <p role="status" className="my-2 text-green-700">{message}</p>}
      <form onSubmit={(e) => void createSource(e)} noValidate className="my-3 space-y-3 rounded-lg border border-sky-300 bg-white p-4" aria-label="Thêm báo cáo tháng">
        <h3 className="font-semibold">Thêm báo cáo tháng</h3>
        <div className="flex flex-wrap items-start gap-3">
          <label className="text-sm">Tháng
            <select value={month} onChange={(e) => { setMonth(e.target.value); setConflict(false); setReplace(false); }} className={`${INPUT} ml-1`} aria-invalid={!!formErrors.month}>
              <option value="">Chọn…</option>
              {Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, "0")).map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
            {formErrors.month && <span role="alert" className="block text-red-700">{formErrors.month}</span>}
          </label>
          <label className="text-sm">Năm
            <input inputMode="numeric" maxLength={4} value={year} onChange={(e) => { setYear(e.target.value.replace(/\D/g, "")); setConflict(false); setReplace(false); }} className={`${INPUT} ml-1 w-20`} aria-invalid={!!formErrors.year} />
            {formErrors.year && <span role="alert" className="block text-red-700">{formErrors.year}</span>}
          </label>
          <label className="grow text-sm">Link Google Sheets
            <input value={workbook} onChange={(e) => setWorkbook(e.target.value)} placeholder="https://docs.google.com/spreadsheets/d/…" className={`${INPUT} mt-1 w-full`} aria-invalid={!!formErrors.workbook} />
            {formErrors.workbook && <span role="alert" className="block text-red-700">{formErrors.workbook}</span>}
          </label>
        </div>
        <label className="block text-sm">Tên báo cáo
          <input value={shownName} onChange={(e) => { setName(e.target.value); setNameEdited(true); }} className={`${INPUT} ml-1 w-full max-w-md`} aria-invalid={!!formErrors.name} />
          {formErrors.name && <span role="alert" className="block text-red-700">{formErrors.name}</span>}
        </label>
        <div className="flex flex-wrap gap-4 text-sm">
          <label><input type="checkbox" checked={autoSync} onChange={(e) => setAutoSync(e.target.checked)} /> Tự đồng bộ mỗi 15 phút (mặc định tắt)</label>
          <label><input type="checkbox" checked={makeDefault} onChange={(e) => setMakeDefault(e.target.checked)} /> Đặt làm nguồn mặc định</label>
          {conflict && <label className="font-medium text-amber-800"><input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} /> Xác nhận thay nguồn đang dùng của kỳ {periodValue}</label>}
        </div>
        {formErrors.form && <p role="alert" className="text-sm text-red-700">{formErrors.form}</p>}
        {saving && <p role="status" className="text-sm text-sky-800">Đang kiểm tra và đọc báo cáo… có thể mất tới một phút.</p>}
        {saved && <div role="status" className={`rounded border p-2 text-sm ${saved.status === "ERROR" || saved.status === "CHƯA ĐỌC" ? "border-amber-400 bg-amber-50" : "border-green-400 bg-green-50"}`}>
          {saved.status === "ERROR" || saved.status === "CHƯA ĐỌC"
            ? <>Đã lưu cấu hình kỳ {saved.period} nhưng chưa đọc được báo cáo: {saved.error ?? "chưa có lần đọc"}. Kiểm tra quyền chia sẻ cho service account rồi bấm “Cập nhật ngay” ở nguồn này để thử lại.</>
            : <>Đã lưu kỳ {saved.period}{saved.status === "READY" ? "" : ` (${saved.status}: có cảnh báo chất lượng dữ liệu, vẫn lưu để xem)`}.</>}
          {" "}<a href="#source-detail" className="font-medium text-sky-800 underline">Xem báo cáo</a>
        </div>}
        <button type="submit" disabled={saving || busy} className={BTN}>{saving ? "Đang kiểm tra…" : "Kiểm tra và lưu báo cáo"}</button>
      </form>
      <h3 className="mt-4 font-semibold">Nguồn đã lưu</h3>
      <label className="text-sm">Chọn nguồn{" "}
        <select value={selectedId} onChange={(e) => setSelectedId(e.target.value)} className={INPUT}>
          <option value="">Chọn nguồn</option>
          {sources.map((source) => <option key={source.id} value={source.id}>{source.period} · {source.name}{source.active ? "" : " · đã thay thế"}</option>)}
        </select>
      </label>
      {selected && <div id="source-detail">
        <p className="my-2 text-sm">Mapping {selected.mapping_version} · {selected.sync_enabled ? "Tự đồng bộ bật" : "Tự đồng bộ tắt"} · {selected.is_default ? "Nguồn mặc định" : "Không mặc định"}{selected.latest_snapshot ? "" : " · chưa có bản đọc"}</p>
        <div className="flex flex-wrap gap-2">
          <button className={BTN} disabled={busy || !selected.active} onClick={() => void run(async () => {
            const attempt = await postJson<SheetSyncAttempt>(`/sheets/sources/${selected.id}/sync`);
            await refreshDetail();
            if (attempt.status === "ERROR") throw new Error(attempt.error ?? "Đọc nguồn thất bại.");
          }, "Đã cập nhật bản lưu.")}>Cập nhật ngay</button>
          <button className={BTN_ALT} disabled={busy || !selected.active || selected.is_default} onClick={() => void run(async () => {
            await patchJson(`/sheets/sources/${selected.id}`, { set_default: true });
          }, "Đã chọn nguồn mặc định.")}>Chọn mặc định</button>
          <button className={BTN_ALT} disabled={busy || !selected.active} onClick={() => void run(async () => {
            await patchJson(`/sheets/sources/${selected.id}`, { sync_enabled: !selected.sync_enabled });
          }, "Đã cập nhật lịch đồng bộ.")}>{selected.sync_enabled ? "Tắt tự đồng bộ" : "Bật tự đồng bộ"}</button>
        </div>
        <h3 className="mt-4 font-semibold">Lịch sử đồng bộ</h3>
        {history.length === 0 ? <p>Chưa có lần đọc.</p> : <>
          <ul className="text-sm">{visibleHistory.map((item) =>
            <li key={item.id}>{timeText(item.started_at)} · {item.trigger} · {item.status}{item.error ? ` · ${item.error}` : ""}{item.snapshot_id ? ` · bản #${item.snapshot_id}` : ""}</li>)}</ul>
          {history.length > HISTORY_PREVIEW && <button type="button" className={`${BTN_ALT} mt-1`} onClick={() => setShowAllHistory((v) => !v)}>
            {showAllHistory ? "Thu gọn" : `Xem thêm (${history.length - HISTORY_PREVIEW} lượt)`}</button>}
        </>}
        <h3 className="mt-4 font-semibold">Bản lưu và chốt kỳ</h3>
        <label>Bản lưu{" "}
          <select value={snapshotId} onChange={(e) => { setSnapshotId(e.target.value); setAcknowledge(false); }} className="rounded border p-1">
            {snapshots.map((item) => <option value={item.id} key={item.id}>#{item.id} · {timeText(item.read_at)} · {item.quality}{selected.closure?.snapshot_id === item.id ? " · BẢN CHỐT" : ""}</option>)}
          </select>
        </label>
        {snapshot?.report && <>
          <p>Trạng thái {snapshot.quality} · {(snapshot.report.customers ?? []).length} tab khách · {snapshot.report.issues.length} cảnh báo nguồn. Xem chi tiết bên dưới và tại /reports trước khi chốt.</p>
          {snapshot.quality !== "READY" && <label><input type="checkbox" checked={acknowledge} onChange={(e) => setAcknowledge(e.target.checked)} /> Tôi đã xem và chấp nhận bản còn thiếu khi chốt</label>}
          <details><summary>Phần thiếu và cảnh báo</summary>
            <ul>{snapshot.report.issues.map((issue, index) => <li key={index}>{issue.source}: {issue.message}</li>)}
              {(snapshot.report.customers ?? []).filter((c) => c.completeness_status === "NEEDS_REVIEW" || c.profile_status === "SOURCE_ERROR" || c.profile_status === "STRUCTURE_ERROR")
                .map((c) => <li key={c.source_sheet}><details>
                  <summary>{c.source_sheet}: {c.profile_status} · {c.completeness_status ?? "chưa đọc đủ"} · {(c.issues ?? []).length} cảnh báo</summary>
                  <ul>{(c.issues ?? []).map((issue, index) => <li key={index}>{issue.source}: {issue.message}</li>)}</ul>
                </details></li>)}</ul>
          </details>
          <button className={BTN} disabled={busy || !!selected.closure || (snapshot.quality !== "READY" && !acknowledge)}
            onClick={() => void run(async () => {
              await postJson(`/sheets/sources/${selected.id}/closure`, { snapshot_id: Number(snapshotId), acknowledge_partial: acknowledge });
            }, "Đã chốt bản được chọn; các lần đọc sau không ghi đè bản chốt.")}>Chốt kỳ với bản đã chọn</button>
        </>}
        <h3 className="mt-4 font-semibold">Liên kết định danh khách cho chuyển kỳ</h3>
        <p className="text-sm">Người vận hành xác nhận từng tab với khách nội bộ; không ghép theo tên hoặc vị trí. Tên tab đổi cần xác nhận lại.</p>
        <ul>{links.map((link) => <li key={link.sheet_id}>{link.source_title} → {customers.find((c) => c.id === link.customer_id)?.name ?? `khách #${link.customer_id}`}</li>)}</ul>
        <div className="flex flex-wrap gap-2">
          <select value={sheetId} onChange={(e) => setSheetId(e.target.value)} className="rounded border p-1">
            <option value="">Chọn tab khách</option>
            {(snapshot?.report?.customers ?? []).filter((c) => c.sheet_id !== null).map((c) => <option key={c.sheet_id} value={c.sheet_id ?? ""}>{c.source_sheet}</option>)}
          </select>
          <select value={customerId} onChange={(e) => setCustomerId(e.target.value)} className="rounded border p-1">
            <option value="">Chọn khách nội bộ</option>
            {customers.map((c) => <option key={c.id} value={c.id}>{c.name} · #{c.id}</option>)}
          </select>
          <label><input type="checkbox" checked={confirmRenamed} onChange={(e) => setConfirmRenamed(e.target.checked)} /> Xác nhận tab đã đổi tên, cùng sheet ID và cùng khách</label>
          <button className={BTN} disabled={busy || !sheetId || !customerId} onClick={() => void run(async () => {
            await postJson(`/sheets/sources/${selected.id}/links`, { sheet_id: Number(sheetId), customer_id: Number(customerId), confirm_renamed: confirmRenamed });
            setConfirmRenamed(false);
            await refreshDetail();
          }, "Đã xác nhận liên kết khách.")}>Xác nhận liên kết</button>
        </div>
        <h3 className="mt-4 font-semibold">Đối chiếu chuyển kỳ</h3>
        <select value={previousId} onChange={(e) => { setPreviousId(e.target.value); setRollover(null); }} className="rounded border p-1">
          <option value="">Chọn nguồn kỳ trước đã chốt</option>
          {sources.filter((source) => source.id !== selected.id).map((source) => <option key={source.id} value={source.id}>{source.period} · {source.name}</option>)}
        </select>{" "}
        <button className={BTN_ALT} disabled={busy || !previousId} onClick={() => void run(async () => {
          setRollover(await fetchJson<Rollover>(`/sheets/sources/${selected.id}/rollover?previous_source_id=${previousId}`));
        }, "Đã đối chiếu; không thay đổi số trên Sheets.")}>Xem đối chiếu</button>
        {rollover && <div>
          {!rollover.previous_closed && <p><strong>Chưa chốt</strong> — đối chiếu tạm L1 kỳ trước (snapshot mới nhất) với J1 kỳ này; đối chiếu chính thức chỉ dựa trên bản chốt.</p>}
          {rollover.unlinked_previous.length > 0 && <p>Thiếu liên kết kỳ trước: {rollover.unlinked_previous.join(", ")}</p>}
          {rollover.unlinked_current.length > 0 && <p>Thiếu liên kết kỳ này: {rollover.unlinked_current.join(", ")}</p>}
          {rollover.customers.length === 0 && <p>Chưa có liên kết khách được xác nhận.</p>}
          {rollover.customers.map((row) => <p key={row.customer_id}>
            {customers.find((c) => c.id === row.customer_id)?.name ?? `Khách #${row.customer_id}`} · {row.status} · {row.previous_source ?? "thiếu liên kết"}: {formatVnd(row.previous_value)} → {row.next_source ?? "thiếu liên kết"}: {formatVnd(row.next_value)} · chênh {formatVnd(row.difference)} VND (tolerance {row.tolerance})
            <span title={`Nguồn chính xác: ${row.previous_value ?? "—"} → ${row.next_value ?? "—"}; chênh: ${row.difference ?? "—"}`}> · giá trị chính xác trong truy vết</span>
          </p>)}
        </div>}
      </div>}
    </section>
  );
}
