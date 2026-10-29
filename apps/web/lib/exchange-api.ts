const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export type ExchangeConnection = { id: number; label: string; provider: string; status: string; auto_sync: boolean; api_key_last4?: string; last_error: string | null; last_ok_at: string | null; last_checked_at: string | null; wallet_errors?: Record<string, string> };
export type Balance = { id: number; wallet_type: string; asset: string; free: string | null; locked: string | null; freeze: string | null; withdrawing: string | null; read_at: string };
export type History = { id: number; started_at: string; status: string; error_message: string | null };
export type ConnectionsResult = { connections: ExchangeConnection[]; scheduler_enabled: boolean; secure_storage_ready: boolean };

export async function exchangeRequest<T>(token: string, path: string, method = "GET", body?: unknown): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120000);
  try {
    const response = await fetch(`${BASE}/api/v1/exchange${path}`, {
      method, cache: "no-store", signal: controller.signal,
      headers: { "Content-Type": "application/json", "X-Adsos-Wallet-Token": token },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = data?.detail;
      throw new Error(typeof detail === "string" ? detail : typeof detail?.error === "string" ? detail.error : `Không thực hiện được yêu cầu (${response.status}).`);
    }
    return data as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw new Error("Yêu cầu quá thời gian. Tải lại danh sách trước khi thử lưu lần nữa.");
    throw error;
  } finally { clearTimeout(timeout); }
}

// Group decimal strings without rounding money through JavaScript Number.
export function formatUsdt(value: string | null | undefined): string {
  if (value == null) return "—";
  const [whole, fraction = ""] = value.split(".");
  const tail = fraction.replace(/0+$/, "");
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ".") + (tail ? `,${tail}` : "");
}
