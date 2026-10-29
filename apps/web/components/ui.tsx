"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchJson } from "../lib/api";

export function useApi<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetchJson<T>(path);
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, error, loading, reload };
}

const TAG_STYLES: Record<string, { cls: string; label: string }> = {
  ACTIVE: { cls: "ok", label: "Hoạt động" },
  RESTRICTED: { cls: "bad", label: "Bị hạn chế" },
  REPLACED: { cls: "warn", label: "Đã thay thế" },
  DEAD: { cls: "bad", label: "Ngừng dùng" },
  CONFIRMED: { cls: "ok", label: "Đã xác nhận" },
  UNRECOGNIZED: { cls: "warn", label: "Cần kiểm tra" },
  PAUSED: { cls: "warn", label: "Tạm dừng" },
  ENDED: { cls: "warn", label: "Đã kết thúc" },
};

export function Tag({ value }: { value: string | null }) {
  if (!value) return <span className="muted">—</span>;
  const style = TAG_STYLES[value] ?? { cls: "warn", label: value };
  return <span className={`tag ${style.cls}`}>{style.label}</span>;
}
