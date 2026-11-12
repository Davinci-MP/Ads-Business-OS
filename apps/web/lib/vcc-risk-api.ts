/**
 * Client API kết nối Động cơ Quản trị Rủi ro Thẻ VCC PingPong và Meta Ad Accounts
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface VccRiskCard {
  id: string;
  card_number_masked: string;
  last_four: string;
  remark: string;
  status: string;
  currency: string;
  allocated_balance: number;
  available_balance: number;
  low_balance_threshold: number;
  risk_status: "SAFE" | "WARNING" | "CRITICAL";
  risk_label: string;
  ad_account: {
    id: number;
    act_id: string;
    name: string;
    balance: number;
    threshold: number;
    status_dot?: string;
  } | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface VccRiskAlert {
  rule: string;
  severity: "WARNING" | "CRITICAL";
  card_id?: string;
  last_four?: string;
  remark?: string;
  act_id?: string;
  ad_account_name?: string;
  debt?: number;
  available_balance?: number;
  threshold?: number;
  master_usd_balance?: number;
  total_meta_debt?: number;
  deficit?: number;
  message: string;
}

export interface VccRiskOverview {
  master_usd_balance: number;
  total_meta_debt: number;
  total_active_cards: number;
  critical_alerts_count: number;
  warning_alerts_count: number;
  cards: VccRiskCard[];
  alerts: VccRiskAlert[];
}

export interface VccTransactionItem {
  id: string;
  card_id: string;
  auth_amount: number;
  settle_amount: number;
  currency: string;
  merchant_name: string;
  status: string;
  transaction_time: string | null;
}

export async function getVccRiskOverview(): Promise<VccRiskOverview> {
  const res = await fetch(`${API_URL}/api/v1/vcc-risk/overview`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Lỗi tải dữ liệu rủi ro VCC: ${res.statusText}`);
  return res.json();
}

export async function syncVccRisk(): Promise<VccRiskOverview> {
  const res = await fetch(`${API_URL}/api/v1/vcc-risk/sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Lỗi đồng bộ VCC: ${res.statusText}`);
  return res.json();
}

export async function updateVccCardThreshold(cardId: string, threshold: number): Promise<{ ok: boolean; message: string }> {
  const res = await fetch(`${API_URL}/api/v1/vcc-risk/cards/${encodeURIComponent(cardId)}/threshold`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ threshold }),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Lỗi cập nhật ngưỡng: ${res.statusText}`);
  return res.json();
}

export async function getVccCardTransactions(cardId: string, limit: number = 50): Promise<VccTransactionItem[]> {
  const res = await fetch(`${API_URL}/api/v1/vcc-risk/cards/${encodeURIComponent(cardId)}/transactions?limit=${limit}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Lỗi tải lịch sử giao dịch thẻ: ${res.statusText}`);
  return res.json();
}
