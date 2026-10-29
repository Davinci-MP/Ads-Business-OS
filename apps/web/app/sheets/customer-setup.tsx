"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchJson, postJson, type SavedSheetSource } from "../../lib/api";

type Row = {
  sheet_id: number; spreadsheet_id: string; source_sheet: string; suggested_name: string;
  status: "LINKED" | "LINK_REVIEW" | "UNLINKED" | "DISMISSED"; profile_status: string | null;
  customer_id: number | null; warnings: string[]; name_exists: boolean;
};
type Proposals = {
  source_id: number; period: string; snapshot_id: number | null; rows: Row[];
  customers: { id: number; name: string; linked_in_source: boolean }[]; create_defaults: string;
};
type Choice = { action: "" | "link" | "create" | "dismiss" | "restore"; customerId: string; name: string };

const STATUS: Record<Row["status"], string> = {
  LINKED: "Đã liên kết", LINK_REVIEW: "Cần xác nhận lại", UNLINKED: "Chưa liên kết", DISMISSED: "Đã bỏ qua (không phải khách)",
};

export default function CustomerSetup() {
  const [sources, setSources] = useState<SavedSheetSource[]>([]);
  const [sourceId, setSourceId] = useState<number | null>(null);
  const [data, setData] = useState<Proposals | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [choices, setChoices] = useState<Record<number, Choice>>({});
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [reviewing, setReviewing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    fetchJson<{ sources: SavedSheetSource[] }>("/sheets/sources")
      .then((r) => {
        setSources(r.sources);
        const current = r.sources.find((s) => s.is_default) ?? r.sources.find((s) => s.active);
        setSourceId(current?.id ?? null);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const load = useCallback(async (id: number) => {
    setLoading(true); setError(null); setData(null); setChoices({}); setSelected(new Set()); setReviewing(false);
    try { setData(await fetchJson<Proposals>(`/sheets/sources/${id}/customer-setup`)); }
    catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (sourceId) void load(sourceId); }, [sourceId, load]);

  const choice = (row: Row): Choice => choices[row.sheet_id] ?? { action: "", customerId: "", name: row.suggested_name };
  const patch = (row: Row, next: Partial<Choice>) => setChoices((c) => ({ ...c, [row.sheet_id]: { ...choice(row), ...next } }));
  const pending = (data?.rows ?? []).filter((row) => choice(row).action !== "");
  const problems = pending.flatMap((row) => {
    const c = choice(row);
    if (c.action === "link" && !c.customerId) return [`${row.source_sheet}: chưa chọn hồ sơ để liên kết.`];
    if (c.action === "create" && !c.name.trim()) return [`${row.source_sheet}: chưa có tên hồ sơ.`];
    return [];
  });

  const bulk = (action: Choice["action"]) => {
    for (const id of selected) {
      const row = data?.rows.find((r) => r.sheet_id === id);
      if (row) patch(row, { action });
    }
  };

  async function submit() {
    if (!data) return;
    setBusy(true); setMessage(null); setError(null);
    try {
      const res = await postJson<{ results: { result: string }[] }>(`/sheets/sources/${data.source_id}/customer-setup`, {
        confirm: true,
        items: pending.map((row) => {
          const c = choice(row);
          return { sheet_id: row.sheet_id, action: c.action, expected_source_sheet: row.source_sheet,
            customer_id: c.action === "link" ? Number(c.customerId) : null, name: c.action === "create" ? c.name.trim() : null };
        }),
      });
      setMessage(`Đã xử lý ${res.results.length} tab. Không có khoản tiền hoặc phân công TKQC nào được tạo.`);
      await load(data.source_id);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <section id="customer-setup" className="my-6 rounded-xl border border-slate-200 p-4">
      <h2>Thiết lập khách hàng từ Sheets</h2>
      <p className="muted">Liên kết tab nguồn với hồ sơ khách nội bộ. Hệ thống chỉ đề xuất tên; không tự liên kết theo tên gần giống.</p>
      <label>Nguồn tháng{" "}
        <select value={sourceId ?? ""} onChange={(e) => setSourceId(Number(e.target.value) || null)}>
          <option value="">Chọn nguồn</option>
          {sources.filter((s) => s.active).map((s) => <option key={s.id} value={s.id}>{s.period} — {s.name}</option>)}
        </select>
      </label>
      {loading && <p className="loading">Đang tải danh sách tab…</p>}
      {error && <p className="error-box">{error} <button type="button" onClick={() => sourceId && void load(sourceId)}>Thử lại</button></p>}
      {message && <p className="notice">{message}</p>}
      {data && data.snapshot_id == null && <p className="notice">Nguồn chưa có bản lưu; chưa có tab để thiết lập.</p>}
      {data && data.rows.length > 0 && <>
        <div className="my-2">
          <span>Đã chọn {selected.size} tab: </span>
          <button type="button" disabled={!selected.size} onClick={() => bulk("create")}>Tạo hồ sơ mới theo tên đề xuất</button>{" "}
          <button type="button" disabled={!selected.size} onClick={() => bulk("dismiss")}>Bỏ qua (không phải khách)</button>{" "}
          <button type="button" disabled={!selected.size} onClick={() => bulk("")}>Bỏ chọn hành động</button>
        </div>
        <div style={{ overflowX: "auto" }}><table>
          <thead><tr><th></th><th>Tab nguồn</th><th>Tên khách đề xuất</th><th>Hồ sơ nội bộ liên kết</th><th>Hành động</th><th>Cảnh báo</th></tr></thead>
          <tbody>{data.rows.map((row) => {
            const c = choice(row);
            const linkedName = data.customers.find((x) => x.id === row.customer_id)?.name;
            const editable = row.status === "UNLINKED";
            return <tr key={row.sheet_id}>
              <td><input type="checkbox" aria-label={`Chọn ${row.source_sheet}`} disabled={row.status === "LINKED" || row.status === "LINK_REVIEW"}
                checked={selected.has(row.sheet_id)} onChange={(e) => setSelected((s) => { const n = new Set(s); if (e.target.checked) n.add(row.sheet_id); else n.delete(row.sheet_id); return n; })} /></td>
              <td>{row.source_sheet}<div className="muted">{STATUS[row.status]} · sheetId {row.sheet_id}</div></td>
              <td>{editable && c.action === "create"
                ? <input value={c.name} onChange={(e) => patch(row, { name: e.target.value })} aria-label="Tên hồ sơ mới" />
                : row.suggested_name}</td>
              <td>{linkedName ?? (editable && c.action === "link"
                ? <select value={c.customerId} onChange={(e) => patch(row, { customerId: e.target.value })} aria-label="Hồ sơ nội bộ">
                    <option value="">Chọn hồ sơ</option>
                    {data.customers.filter((x) => !x.linked_in_source).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                  </select>
                : "Chưa liên kết")}</td>
              <td>{row.status === "DISMISSED"
                ? <select value={c.action} onChange={(e) => patch(row, { action: e.target.value as Choice["action"] })}><option value="">Giữ nguyên</option><option value="restore">Khôi phục là tab khách</option></select>
                : editable
                  ? <select value={c.action} onChange={(e) => patch(row, { action: e.target.value as Choice["action"] })}>
                      <option value="">Chưa chọn</option><option value="link">Liên kết hồ sơ đã có</option>
                      <option value="create">Tạo hồ sơ mới rồi liên kết</option><option value="dismiss">Bỏ qua tab không phải khách</option>
                    </select>
                  : "Không cần"}</td>
              <td>{row.warnings.length ? <ul>{row.warnings.map((w) => <li key={w}>{w}</li>)}</ul> : "—"}</td>
            </tr>;
          })}</tbody>
        </table></div>
        {!reviewing && <button type="button" disabled={!pending.length} onClick={() => setReviewing(true)}>Xem lại {pending.length} thay đổi</button>}
        {reviewing && <div className="notice" role="region" aria-label="Xác nhận thiết lập">
          <strong>Xác nhận một lần — chưa ghi gì cho đến khi bạn bấm Xác nhận:</strong>
          <ul>{pending.map((row) => {
            const c = choice(row);
            const target = c.action === "link" ? `liên kết với “${data.customers.find((x) => String(x.id) === c.customerId)?.name ?? "?"}”`
              : c.action === "create" ? `tạo hồ sơ mới “${c.name.trim()}” rồi liên kết`
              : c.action === "dismiss" ? "bỏ qua, không tính là khách" : "khôi phục là tab khách";
            return <li key={row.sheet_id}>{row.source_sheet}: {target}</li>;
          })}</ul>
          <p className="muted">{data.create_defaults}</p>
          {problems.map((p) => <p key={p} className="error-box">{p}</p>)}
          <button type="button" disabled={busy || problems.length > 0} onClick={() => void submit()}>{busy ? "Đang ghi…" : "Xác nhận"}</button>{" "}
          <button type="button" disabled={busy} onClick={() => setReviewing(false)}>Quay lại</button>
        </div>}
      </>}
      <details className="my-2"><summary>Chi tiết cách hoạt động</summary>
        <p>Tab được định danh bằng spreadsheet ID + sheetId của nguồn tháng. Tab ẩn và tab tổng hợp không xuất hiện ở đây. Tab bỏ qua chỉ bị loại khỏi
          danh sách khách, dữ liệu nguồn không bị xóa và có thể khôi phục. Mỗi tháng có nguồn riêng nên tab của tháng mới cần được liên kết lại (không ghép theo tên).</p>
      </details>
    </section>
  );
}
