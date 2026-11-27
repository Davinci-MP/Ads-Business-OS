"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchJson, postJson, type SavedSheetSource } from "../../lib/api";

type Row = {
  sheet_id: number;
  spreadsheet_id: string;
  source_sheet: string;
  suggested_name: string;
  status: "LINKED" | "LINK_REVIEW" | "UNLINKED" | "DISMISSED";
  profile_status: string | null;
  customer_id: number | null;
  warnings: string[];
  name_exists: boolean;
};

type Proposals = {
  source_id: number;
  period: string;
  snapshot_id: number | null;
  rows: Row[];
  customers: { id: number; name: string; linked_in_source: boolean }[];
  create_defaults: string;
};

type Choice = {
  action: "" | "link" | "create" | "dismiss" | "restore";
  customerId: string;
  name: string;
};

const STATUS_BADGE: Record<Row["status"], { label: string; cls: string }> = {
  LINKED: {
    label: "Đã liên kết",
    cls: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30",
  },
  LINK_REVIEW: {
    label: "Cần xác nhận lại",
    cls: "bg-amber-500/10 text-amber-400 border border-amber-500/30",
  },
  UNLINKED: {
    label: "Chưa liên kết",
    cls: "bg-sky-500/10 text-sky-400 border border-sky-500/30",
  },
  DISMISSED: {
    label: "Đã bỏ qua (không phải khách)",
    cls: "bg-slate-800 text-slate-400 border border-slate-700",
  },
};

interface CustomerSetupProps {
  activeSourceId?: number | null;
}

export default function CustomerSetup({ activeSourceId }: CustomerSetupProps) {
  const [sources, setSources] = useState<SavedSheetSource[]>([]);
  const [sourceId, setSourceId] = useState<number | null>(activeSourceId ?? null);
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
        if (activeSourceId) {
          setSourceId(activeSourceId);
        } else {
          const current = r.sources.find((s) => s.is_default) ?? r.sources.find((s) => s.active);
          setSourceId(current?.id ?? null);
        }
      })
      .catch((e: Error) => setError(e.message));
  }, [activeSourceId]);

  useEffect(() => {
    if (activeSourceId && activeSourceId !== sourceId) {
      setSourceId(activeSourceId);
    }
  }, [activeSourceId, sourceId]);

  const load = useCallback(async (id: number) => {
    setLoading(true);
    setError(null);
    setData(null);
    setChoices({});
    setSelected(new Set());
    setReviewing(false);
    try {
      setData(await fetchJson<Proposals>(`/sheets/sources/${id}/customer-setup`));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (sourceId) void load(sourceId);
  }, [sourceId, load]);

  const choice = (row: Row): Choice =>
    choices[row.sheet_id] ?? { action: "", customerId: "", name: row.suggested_name };
  const patch = (row: Row, next: Partial<Choice>) =>
    setChoices((c) => ({ ...c, [row.sheet_id]: { ...choice(row), ...next } }));

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
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      const res = await postJson<{ results: { result: string }[] }>(
        `/sheets/sources/${data.source_id}/customer-setup`,
        {
          confirm: true,
          items: pending.map((row) => {
            const c = choice(row);
            return {
              sheet_id: row.sheet_id,
              action: c.action,
              expected_source_sheet: row.source_sheet,
              customer_id: c.action === "link" ? Number(c.customerId) : null,
              name: c.action === "create" ? c.name.trim() : null,
            };
          }),
        },
      );
      setMessage(`Đã xử lý ${res.results.length} tab thành công. Không có khoản tiền hoặc phân công TKQC nào bị ghi đè.`);
      await load(data.source_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      id="customer-setup"
      className="rounded-2xl border border-slate-800/80 bg-[#111827]/95 p-5 shadow-xl backdrop-blur-md space-y-4 text-slate-100"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <span></span> Thiết Lập Khách Hàng Từ Sheets
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Liên kết từng tab Google Sheets với hồ sơ khách nội bộ. Hệ thống chỉ đề xuất tên, không tự liên kết giả định.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-slate-300">Nguồn kỳ:</label>
          <select
            value={sourceId ?? ""}
            onChange={(e) => setSourceId(Number(e.target.value) || null)}
            className="rounded-xl border border-slate-700 bg-[#1E293B] px-3 py-1.5 text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
          >
            <option value="">Chọn nguồn</option>
            {sources
              .filter((s) => s.active)
              .map((s) => (
                <option key={s.id} value={s.id}>
                  {s.period} — {s.name}
                </option>
              ))}
          </select>
          {sourceId && (
            <button
              type="button"
              onClick={() => void load(sourceId)}
              disabled={loading}
              className="rounded-xl border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700 transition disabled:opacity-50"
            >
              {loading ? "Đang tải…" : "Làm mới"}
            </button>
          )}
        </div>
      </div>

      {loading && (
        <div className="flex items-center gap-2 p-4 text-sm text-sky-400 bg-sky-950/20 border border-sky-800/40 rounded-xl">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-sky-400 border-t-transparent" />
          <span>Đang tải danh sách tab và đối soát hồ sơ khách...</span>
        </div>
      )}

      {error && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-rose-800/60 bg-rose-950/40 p-4 text-sm text-rose-200" role="alert">
          <span>{error}</span>
          <button
            type="button"
            className="rounded-lg border border-rose-700 bg-rose-900/50 px-3 py-1 text-xs font-semibold hover:bg-rose-900"
            onClick={() => sourceId && void load(sourceId)}
          >
            Thử lại
          </button>
        </div>
      )}

      {message && (
        <div className="rounded-xl border border-emerald-800/60 bg-emerald-950/40 p-4 text-sm text-emerald-200" role="status">
          {message}
        </div>
      )}

      {data && data.snapshot_id == null && !loading && (
        <div className="rounded-xl border border-amber-800/60 bg-amber-950/30 p-4 text-sm text-amber-300">
          Nguồn kỳ này chưa có bản lưu snapshot nào; vui lòng bấm &ldquo;Cập nhật / Đồng bộ ngay&rdquo; trước để tải cấu trúc tab.
        </div>
      )}

      {data && data.rows.length > 0 && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-slate-900/90 border border-slate-800 p-3">
            <div className="text-xs text-slate-300">
              Đã chọn <span className="font-bold text-indigo-400">{selected.size}</span> / {data.rows.length} tab:
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={!selected.size}
                onClick={() => bulk("create")}
                className="rounded-xl border border-indigo-700/60 bg-[#eef4ff] px-3 py-1.5 text-xs font-medium text-indigo-300 hover:bg-[#eef4ff] disabled:opacity-40 transition"
              >
                Tạo hồ sơ theo tên đề xuất
              </button>
              <button
                type="button"
                disabled={!selected.size}
                onClick={() => bulk("dismiss")}
                className="rounded-xl border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700 disabled:opacity-40 transition"
              >
                Bỏ qua (không phải khách)
              </button>
              <button
                type="button"
                disabled={!selected.size}
                onClick={() => bulk("")}
                className="rounded-xl border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-400 hover:bg-slate-700 disabled:opacity-40 transition"
              >
                Bỏ chọn hành động
              </button>
            </div>
          </div>

          <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-900 text-slate-400 uppercase font-semibold">
                <tr>
                  <th className="p-3 w-10 text-center">
                    <input
                      type="checkbox"
                      aria-label="Chọn tất cả"
                      className="accent-indigo-500 rounded"
                      checked={
                        selected.size > 0 &&
                        selected.size ===
                          data.rows.filter((r) => r.status === "UNLINKED" || r.status === "DISMISSED").length
                      }
                      onChange={(e) => {
                        if (e.target.checked) {
                          const validIds = data.rows
                            .filter((r) => r.status === "UNLINKED" || r.status === "DISMISSED")
                            .map((r) => r.sheet_id);
                          setSelected(new Set(validIds));
                        } else {
                          setSelected(new Set());
                        }
                      }}
                    />
                  </th>
                  <th className="p-3">Tab nguồn</th>
                  <th className="p-3">Tên đề xuất</th>
                  <th className="p-3">Hồ sơ nội bộ liên kết</th>
                  <th className="p-3">Hành động</th>
                  <th className="p-3">Cảnh báo</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/80">
                {data.rows.map((row) => {
                  const c = choice(row);
                  const linkedName = data.customers.find((x) => x.id === row.customer_id)?.name;
                  const editable = row.status === "UNLINKED";
                  const badge = STATUS_BADGE[row.status];
                  return (
                    <tr key={row.sheet_id} className="hover:bg-slate-800/40 transition-colors">
                      <td className="p-3 text-center">
                        <input
                          type="checkbox"
                          aria-label={`Chọn ${row.source_sheet}`}
                          disabled={row.status === "LINKED" || row.status === "LINK_REVIEW"}
                          checked={selected.has(row.sheet_id)}
                          onChange={(e) =>
                            setSelected((s) => {
                              const n = new Set(s);
                              if (e.target.checked) n.add(row.sheet_id);
                              else n.delete(row.sheet_id);
                              return n;
                            })
                          }
                          className="accent-indigo-500 rounded"
                        />
                      </td>
                      <td className="p-3 font-medium text-slate-100">
                        <div className="font-semibold">{row.source_sheet}</div>
                        <div className="flex items-center gap-1.5 mt-1">
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${badge.cls}`}>
                            {badge.label}
                          </span>
                          <span className="text-slate-500 font-mono text-[10px]">ID: {row.sheet_id}</span>
                        </div>
                      </td>
                      <td className="p-3">
                        {editable && c.action === "create" ? (
                          <input
                            value={c.name}
                            onChange={(e) => patch(row, { name: e.target.value })}
                            aria-label="Tên hồ sơ mới"
                            className="rounded-lg border border-slate-700 bg-[#1E293B] px-2.5 py-1 text-xs text-slate-100 focus:border-indigo-500 focus:outline-none w-full max-w-xs"
                          />
                        ) : (
                          <span className="text-slate-300">{row.suggested_name}</span>
                        )}
                      </td>
                      <td className="p-3">
                        {linkedName ? (
                          <span className="font-semibold text-emerald-400">{linkedName}</span>
                        ) : editable && c.action === "link" ? (
                          <select
                            value={c.customerId}
                            onChange={(e) => patch(row, { customerId: e.target.value })}
                            aria-label="Hồ sơ nội bộ"
                            className="rounded-lg border border-slate-700 bg-[#1E293B] px-2 py-1 text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
                          >
                            <option value="">Chọn hồ sơ...</option>
                            {data.customers
                              .filter((x) => !x.linked_in_source)
                              .map((x) => (
                                <option key={x.id} value={x.id}>
                                  {x.name}
                                </option>
                              ))}
                          </select>
                        ) : (
                          <span className="text-slate-500 italic">Chưa liên kết</span>
                        )}
                      </td>
                      <td className="p-3">
                        {row.status === "DISMISSED" ? (
                          <select
                            value={c.action}
                            onChange={(e) => patch(row, { action: e.target.value as Choice["action"] })}
                            className="rounded-lg border border-slate-700 bg-[#1E293B] px-2 py-1 text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
                          >
                            <option value="">Giữ nguyên bỏ qua</option>
                            <option value="restore">Khôi phục là tab khách</option>
                          </select>
                        ) : editable ? (
                          <select
                            value={c.action}
                            onChange={(e) => patch(row, { action: e.target.value as Choice["action"] })}
                            className="rounded-lg border border-slate-700 bg-[#1E293B] px-2 py-1 text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
                          >
                            <option value="">Chưa chọn hành động</option>
                            <option value="link">Liên kết hồ sơ đã có</option>
                            <option value="create">Tạo hồ sơ mới rồi liên kết</option>
                            <option value="dismiss">Bỏ qua (không phải khách)</option>
                          </select>
                        ) : (
                          <span className="text-slate-500">Đã chốt</span>
                        )}
                      </td>
                      <td className="p-3">
                        {row.warnings.length ? (
                          <ul className="text-amber-400 space-y-0.5 list-disc list-inside text-[11px]">
                            {row.warnings.map((w, idx) => (
                              <li key={idx}>{w}</li>
                            ))}
                          </ul>
                        ) : (
                          <span className="text-slate-600">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {!reviewing && (
            <div className="flex justify-end">
              <button
                type="button"
                disabled={!pending.length}
                onClick={() => setReviewing(true)}
                className="rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-40 transition shadow-lg shadow-indigo-600/20"
              >
                Xem lại {pending.length} thay đổi đã chọn
              </button>
            </div>
          )}

          {reviewing && (
            <div
              className="rounded-xl border border-indigo-800/60 bg-[#eef4ff] p-4 text-xs text-indigo-200 space-y-3"
              role="region"
              aria-label="Xác nhận thiết lập"
            >
              <div className="font-bold text-sm text-indigo-100">
                Xác nhận thay đổi — Chưa ghi gì cho đến khi bạn bấm &ldquo;Xác nhận lưu&rdquo;:
              </div>
              <ul className="space-y-1 pl-4 list-disc text-slate-200">
                {pending.map((row) => {
                  const c = choice(row);
                  const target =
                    c.action === "link"
                      ? `liên kết với “${data.customers.find((x) => String(x.id) === c.customerId)?.name ?? "?"}”`
                      : c.action === "create"
                        ? `tạo hồ sơ mới “${c.name.trim()}” rồi liên kết`
                        : c.action === "dismiss"
                          ? "bỏ qua, không tính là khách"
                          : "khôi phục là tab khách";
                  return (
                    <li key={row.sheet_id}>
                      <span className="font-semibold text-white">{row.source_sheet}</span>: {target}
                    </li>
                  );
                })}
              </ul>
              {data.create_defaults && <p className="text-slate-400 italic">{data.create_defaults}</p>}
              {problems.map((p, i) => (
                <div key={i} className="rounded-lg border border-rose-800 bg-rose-950/50 p-2 text-rose-300">
                  {p}
                </div>
              ))}
              <div className="flex items-center gap-2 pt-2">
                <button
                  type="button"
                  disabled={busy || problems.length > 0}
                  onClick={() => void submit()}
                  className="rounded-xl bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-40 transition shadow-lg shadow-emerald-600/20"
                >
                  {busy ? "Đang ghi..." : "Xác nhận lưu thiết lập"}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setReviewing(false)}
                  className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-medium text-slate-300 hover:bg-slate-700 transition"
                >
                  Quay lại chỉnh sửa
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      <details className="mt-2 text-xs text-slate-400 cursor-pointer">
        <summary className="hover:text-slate-200 font-medium">Chi tiết nguyên tắc hoạt động thiết lập khách</summary>
        <div className="mt-2 space-y-1 rounded-xl bg-slate-900/60 p-3 text-slate-400 border border-slate-800 leading-relaxed">
          <p>
            • Tab được định danh bằng tổ hợp Spreadsheet ID + sheetId của nguồn tháng.
          </p>
          <p>
            • Tab ẩn và tab tổng hợp sẽ tự động không xuất hiện ở danh sách này.
          </p>
          <p>
            • Tab bỏ qua chỉ bị loại khỏi danh sách khách, không xóa bất kỳ ô dữ liệu nào trong Google Sheets và có thể khôi phục bất cứ lúc nào.
          </p>
          <p>
            • Mỗi tháng là một nguồn riêng biệt nên tab của tháng mới cần được người vận hành xác nhận chủ động để tránh nhập nhầm hồ sơ.
          </p>
        </div>
      </details>
    </section>
  );
}
