const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
export const SHEETS_REPORT_WORKBOOK_KEY = "adsos.sheets.report.workbook";

async function apiFetch(url: string, options: RequestInit): Promise<Response> {
  const headers = new Headers(options.headers);
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("adsos_auth_token");
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  try { return await fetch(url, { ...options, headers }); }
  catch (error: unknown) {
    if (options.signal?.aborted || (error instanceof Error && error.name === "AbortError")) throw error;
    throw new Error("Không thể kết nối máy chủ AdsOS. Kiểm tra backend và đường truyền.");
  }
}
async function apiFailure(response: Response): Promise<Error> {
  let detail: unknown;
  try { const body: unknown = await response.json(); detail = body && typeof body === "object" && "detail" in body ? body.detail : null; } catch { detail = null; }
  // Validation responses can contain the submitted input; never echo them into a toast.
  if (Array.isArray(detail)) return new Error("Thông tin nhập chưa hợp lệ. Kiểm tra các trường bắt buộc và định dạng.");
  if (typeof detail === "string" && /[à-ỹđĐ]/u.test(detail)) return new Error(detail);
  return new Error(({401:"Bạn chưa xác thực với máy chủ.",403:"Bạn không có quyền thực hiện thao tác này.",404:"Không tìm thấy dữ liệu hoặc chức năng yêu cầu.",409:"Dữ liệu bị trùng hoặc đã thay đổi. Hãy tải lại.",422:"Thông tin nhập chưa hợp lệ.",429:"Đã vượt tần suất yêu cầu. Vui lòng thử lại sau.",500:"Máy chủ gặp lỗi xử lý. Dữ liệu cũ được giữ nguyên."} as Record<number,string>)[response.status] || `Không thể xử lý yêu cầu (HTTP ${response.status}).`);
}

export async function fetchJson<T>(
  path: string,
  opts?: { signal?: AbortSignal },
): Promise<T> {
  const res = await apiFetch(`${API_URL}/api/v1${path}`, {
    cache: "no-store",
    signal: opts?.signal,
  });
  if (!res.ok) {
    throw await apiFailure(res);
  }
  return res.json() as Promise<T>;
}

export async function postJson<T>(
  path: string,
  body: unknown = {},
  opts?: { signal?: AbortSignal },
): Promise<T> {
  const res = await apiFetch(`${API_URL}/api/v1${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
    signal: opts?.signal,
  });
  if (!res.ok) {
    throw await apiFailure(res);
  }
  return res.json() as Promise<T>;
}


export async function deleteJson<T>(path: string): Promise<T> {
  const res = await apiFetch(`${API_URL}/api/v1${path}`, {
    method: "DELETE",
    cache: "no-store",
  });
  if (!res.ok) throw await apiFailure(res);
  return res.json() as Promise<T>;
}

export async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const res = await apiFetch(`${API_URL}/api/v1${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) throw await apiFailure(res);
  return res.json() as Promise<T>;
}

export async function putJson<T>(path: string, body: unknown): Promise<T> {
  const res = await apiFetch(`${API_URL}/api/v1${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) throw await apiFailure(res);
  return res.json() as Promise<T>;
}

export type SavedSheetSnapshot = {
  id: number;
  source_id: number;
  read_at: string;
  mapping_version: string;
  quality: string;
  report?: SheetsSourceReport;
};

export type SheetSyncAttempt = {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  error: string | null;
  snapshot_id: number | null;
  trigger: string;
};

export type SavedSheetSnapshotEnvelope = {
  total: number;
  snapshots: SavedSheetSnapshot[];
};

export type SheetSyncHistoryEnvelope = {
  total: number;
  history: SheetSyncAttempt[];
};

export type SavedSheetSource = {
  id: number;
  period: string;
  name: string;
  spreadsheet_id: string;
  mapping_version: string;
  active: boolean;
  sync_enabled: boolean;
  is_default: boolean;
  last_attempt: SheetSyncAttempt | null;
  latest_snapshot: SavedSheetSnapshot | null;
  closure: { snapshot_id: number; closed_at: string } | null;
};

export type Overview = {
  mode: string;
  totals: {
    customers: number;
    accounts_total: number;
    accounts_active: number;
    accounts_restricted: number;
    accounts_replaced: number;
    accounts_dead: number;
    assignments_active: number;
    campaigns_total: number;
    campaigns_confirmed: number;
    campaigns_need_check: number;
  };
  students?: { id: number; name: string; recon_mode: string; fee_rate: string; budget_alert_threshold_vnd: string | null }[];
  last_sync_at: string | null;
};

export type CampaignRow = {
  campaign_id: number;
  meta_campaign_id: string;
  campaign_name: string;
  customer_id: number | null;
  customer_name: string | null;
  ad_account_id: string | null;
  timezone_name: string | null;
  meta_status: string | null;
  report_period_start: string | null;
  report_period_end: string | null;
  checkpoint_9h_spend: string | null;
  checkpoint_9h_at: string | null;
  latest_spend: string | null;
  latest_spend_at: string | null;
  drift_amount: string | null;
  recognition_status: string | null;
  unverified: boolean;
  updated_at: string | null;
};

export type AccountRow = {
  allow_violated_accounts: boolean;
  account_id: number;
  meta_ad_account_id: string;
  name: string;
  business_manager_id: string | null;
  timezone_name: string;
  status: string;
  restricted_at: string | null;
  purchase_cost: string | null;
  customer_id: number | null;
  customer_name: string | null;
  assignment_status: "ASSIGNED" | "UNASSIGNED" | "CONFLICT";
  current_assignment_id: number | null;
  replaced_by: string | null;
  assignment_history: {
    customer_id: number;
    customer_name: string | null;
    valid_from: string | null;
    valid_to: string | null;
  }[];
};

export type SheetCustomerLink = {
  sheet_id: number;
  customer_id: number;
  source_title: string;
};

export type SystemInfo = {
  mode: string;
  last_sync_at: string | null;
  api_errors: { entity: string; detail: string | null; at: string | null }[];
  missed_checkpoints: { at: string | null }[];
  campaigns_need_verification: { meta_campaign_id: string; name: string; status: string }[];
  unverified_snapshots: { meta_campaign_id: string; snapshot_at: string; spend_amount: string }[];
};

export type SheetsMode = { mode: string; spreadsheet_id_configured: boolean };

export type SheetsColumn = {
  column_index: number;
  column_letter: string;
  header: string;
  kind_majority: string | null;
  non_empty_ratio: number;
  samples: unknown[];
  samples_formatted?: string[];
  number_format: { type: string; pattern: string | null; currency: string | null } | null;
  format_source: string | null;
  has_formula: boolean;
  merge_count: number;
  needs_confirmation: boolean;
  confirm_reasons: string[];
};

export type SheetsSheetStructure = {
  title: string;
  sheet_id?: number;
  row_count: number;
  header_row_index: number | null;
  locale: string | null;
  merges: { start_row: number; end_row: number; start_col: number; end_col: number }[];
  separator_rows: number[];
  formula_cells: string[];
  columns: SheetsColumn[];
  notes: string[];
};

export type SheetsProposal = {
  sheet_name: string;
  column_letter: string;
  header: string;
  role: string | null;
  field: string;
  confidence: string | null;
  note: string | null;
  source: {
    sheet: string;
    column_letter: string;
    header: string;
    samples: unknown[];
    samples_formatted: string[];
    number_format: string | null;
    format_source: string | null;
    locale: string | null;
    merge_count: number;
    has_formula: boolean;
    needs_confirmation: boolean;
  };
  target: { area: string; field: string } | null;
};

export type SheetsAnalyzeResponse = {
  spreadsheet_key: string;
  mode: string;
  structure: { spreadsheet_key: string; mode: string; sheets: SheetsSheetStructure[] };
  proposals: SheetsProposal[];
};

export type SheetPreviewCell = {
  address: string;
  value: string | number | boolean | null;
  formula: string | null;
  formatted_value: string | null;
  number_format: { type: string | null; pattern: string | null } | null;
  note: string | null;
};

export type SheetPreviewRow = {
  row_number: number;
  cells: SheetPreviewCell[];
};

export type SheetCellPreview = {
  title: string;
  locale: string | null;
  grid_rows: number | null;
  grid_columns: number | null;
  merges: {
    range: string;
    start_row: number;
    end_row: number;
    start_col: number;
    end_col: number;
  }[];
  rows: SheetPreviewRow[];
};

export type SheetPreviewResponse = {
  mode: string;
  sheet_id: number;
  preview_status: string;
  mapping_status: string;
  analysis: SheetsSheetStructure;
  source: SheetCellPreview;
};

export type SheetsSourceReportCell = SheetPreviewCell;

export type SheetsSourceReportRow = {
  summary_sheet: string;
  summary_row: number;
  customer_label: string;
  customer_sheet: string | null;
  link_status: string;
  unresolved_references: { sheet: string; cells: string[] }[];
  opening_balance_refers_to_source: boolean;
  closing_balance_value: string | number | null;
  closing_balance_formula: string | null;
  closing_balance_source: string | null;
  cells: SheetsSourceReportCell[];
};

export type SheetsSourceTotal = {
  value: string;
  formatted_value: string | null;
  currency: string | null;
  formula: string | null;
  source: string;
  status: string;
};

export type SheetsSourceReportCustomer = {
  display_name: string;
  source_sheet: string;
  sheet_id: number | null;
  read_scope?: string | null;
  completeness_status?: string;
  profile_status: string;
  source_periods: string[];
  source_rows?: SheetPreviewRow[];
  observed_date_from: string | null;
  observed_date_to: string | null;
  period_coverage_complete: boolean;
  period_coverage_note: string;
  source_config_period?: string | null;
  activity_status?: { period: string; status: string; conflict: boolean } | null;
  usdt_receipts_state?: "NO_RECORDED" | "HAS_RECORDS" | "NEEDS_REVIEW";
  field_status?: Record<string, { status: string; reason: string; source: string | null }>;
  opening_balance?: {
    value: string | null;
    formatted_value: string | null;
    currency: string | null;
    source: string | null;
    status: string;
  };
  tab_source_totals?: Record<string, SheetsSourceTotal>;
  period_totals?: Record<string, {
    spend_original_by_currency: Record<string, string>;
    spend_vnd: string | null;
    fee_by_currency: Record<string, string>;
    billing_by_currency: Record<string, string>;
    source_totals?: Record<string, SheetsSourceTotal>;
    source_detail_differences?: {
      field: string;
      source: string;
      source_value: string;
      detail_value: string;
      difference: string;
      note: string;
    }[];
    usdt_received: string | null;
    usdt_received_vnd: string | null;
    budget_deposits_vnd: string | null;
    budget_deposits_status: string;
    budget_deposits_reason: string;
  }>;
  closing_balances?: {
    summary_sheet: string;
    summary_row: number;
    value: string | number | null;
    formatted_value: string | null;
    currency: string | null;
    formula: string | null;
    source: string | null;
  }[];
  deposits?: {
    business_date: string | null;
    amount_usdt: string | number | null;
    amount_vnd: string | number | null;
    rate: string | number | null;
    source_cells: string[];
    source_row: number;
    status: string;
    included: boolean;
    exclusion_reason: string | null;
  }[];
  account_rows?: {
    row_number: number;
    business_date: string | null;
    account_id: string;
    account_currency: string | null;
    cells: SheetsSourceReportCell[];
    missing_inputs: string[];
    status: string;
    original_spend?: { value: string | null; currency: string | null; source: string | null };
  }[];
  unclassified_rows?: {
    row_number: number;
    business_date: string | null;
    cells: SheetsSourceReportCell[];
    status: string;
    reason: string;
  }[];
  daily?: {
    business_date: string;
    spend_by_currency: Record<string, string>;
    spend_vnd: string | null;
    fee_by_currency: Record<string, string>;
    billing_by_currency: Record<string, string>;
    source_cells: string[];
    account_rows: number[];
    data_state: string;
  }[];
  issues?: { severity: string; source: string; message: string; references?: string[] }[];
  linked_summary_rows: SheetsSourceReportRow[];
  ignored_columns: string[];
};

export type SheetsSourceReport = {
  mode: string;
  status: string;
  spreadsheet_key: string;
  read_at: string;
  workbook_tab_count: number;
  all_customer_totals?: {
    period: string | null;
    metrics: Record<string, {
      value: string | null;
      complete_customers: number;
      total_customers: number;
      missing_customers: string[];
      status: "PARTIAL" | "COMPLETE";
      contributions: { customer: string; source: string | string[] | null; value: string; date?: string }[];
    }>;
  };
  summary_tabs?: {
    title: string;
    sheet_id: number | null;
    header_row: number;
    rows: SheetsSourceReportRow[];
    source_columns: Record<string, string>;
  }[];
  customers?: SheetsSourceReportCustomer[];
  issues: { severity: string; source: string; message: string; references?: string[] }[];
  mapping_status: string;
  meta_reconciliation_status: string;
  notes: string[];
};

export type SavedMapping = {
  id: number;
  spreadsheet_key: string;
  sheet_name: string;
  column_letter: string;
  header: string;
  role: string | null;
  field: string;
  status: string;
  note: string | null;
};

export const fmtVnd = (v: string | number | null) =>
  v == null ? "—" : Number(v).toLocaleString("vi-VN", { maximumFractionDigits: 2 });

export const fmtTime = (v: string | null) => (v == null ? "—" : new Date(v).toLocaleString("vi-VN"));

export const API_BASE = API_URL;


export type MetaBillingHealth = {
  meta_ad_account_id: string;
  account_id: string;
  name: string;
  account_status: number;
  account_status_label: string;
  disable_reason: number;
  disable_reason_label: string;
  currency: string;
  amount_spent: number;
  balance: number;
  spend_cap: number | null;
  billing_threshold: number | null;
  allow_violated_accounts?: boolean;
  locked?: boolean;
  risk_code?: string;
};

export type MetaCampaignTask = {
  id: number;
  ad_account_id: string;
  campaign_name: string;
  objective: string;
  daily_budget: number;
  status: string;
  meta_campaign_id: string | null;
  meta_adset_id: string | null;
  meta_ad_id: string | null;
  error_message: string | null;
  created_by: string;
  created_at: string | null;
};

export type TelegramStatus = {
  mode: string;
  is_configured: boolean;
  admin_chat_id_configured: boolean;
  allowed_chat_ids_count: number;
  allowed_chat_ids: string[];
};

export type AutomationRule = {
  id: number;
  name: string;
  rule_type: string;
  threshold: number;
  currency: string;
  target_entity_id: string | null;
  action_type: string;
  is_enabled: boolean;
  last_triggered_at: string | null;
  trigger_count: number;
  created_at: string | null;
};

export type TelegramActivityLog = {
  id: number;
  chat_id: string;
  username: string;
  command: string;
  response_summary: string | null;
  status: string;
  created_at: string | null;
};

export type TelegramConfigInfo = {
  has_token: boolean;
  admin_chat_id: string;
  allowed_chat_ids: string;
  webhook_url: string;
};

export type TelegramFullStatus = {
  mode: string;
  is_configured: boolean;
  admin_chat_id: string | null;
  admin_chat_id_configured: boolean;
  allowed_chat_ids_count: number;
  allowed_chat_ids: string[];
  bot_info: { id: number; username?: string; first_name?: string } | null;
  connection_ok: boolean;
  webhook_info: { url?: string; pending_update_count?: number } | null;
  active_rules_count: number;
};


// ==========================================
// PREPAID BALANCES & LEDGER TYPES & CLIENTS
// ==========================================

export type ClientBalanceItem = {
  id: number;
  customer_id: number;
  customer_name: string | null;
  currency: string;
  amount: string;
  low_threshold: string | null;
  deposit_info: string | null;
  low: boolean;
};

export type LedgerTransactionItem = {
  id: number;
  customer_id: number;
  currency: string;
  amount: string;
  kind: string;
  status: string;
  evidence: string;
  source_ledger_id: number | null;
  created_at: string;
  requested_by: string;
  approved_by: string | null;
  executed_at?: string | null;
};

export type PrepaidOverview = {
  balances: ClientBalanceItem[];
  transactions: LedgerTransactionItem[];
  notice: string;
};

export async function getPrepaidOverview(): Promise<PrepaidOverview> {
  return fetchJson<PrepaidOverview>("/prepaid");
}

export async function requestPrepaidTransaction(body: {
  customer_id: number;
  currency?: string;
  amount: number | string;
  kind?: string;
  idempotency_key: string;
  evidence: string;
  actor: string;
  source_ledger_id?: number | null;
}): Promise<LedgerTransactionItem> {
  return postJson<LedgerTransactionItem>("/prepaid/transactions", body);
}

export async function approvePrepaidTransaction(
  txId: number,
  actor: string
): Promise<LedgerTransactionItem> {
  return postJson<LedgerTransactionItem>(`/prepaid/transactions/${txId}/approve`, { actor });
}

export async function rejectPrepaidTransaction(
  txId: number,
  actor: string
): Promise<LedgerTransactionItem> {
  return postJson<LedgerTransactionItem>(`/prepaid/transactions/${txId}/reject`, { actor });
}

export async function processPrepaidTransactions(): Promise<{ processed: number; message: string }> {
  return postJson<{ processed: number; message: string }>("/prepaid/process", {});
}

export async function setPrepaidThreshold(
  customerId: number,
  body: {
    currency?: string;
    low_threshold: number | string | null;
    deposit_info?: string;
    actor: string;
  }
): Promise<{ message: string }> {
  return postJson<{ message: string }>(`/prepaid/customers/${customerId}/threshold`, body);
}

// ==========================================
// INVENTORY VAULT TYPES & CLIENTS
// ==========================================

export type InventoryItem = {
  id: number;
  item_type: "VIA" | "BM" | "PAGE" | "PROXY" | string;
  name: string;
  status: "AVAILABLE" | "ASSIGNED" | "DEAD" | string;
  assigned_customer_id: number | null;
  customer_name: string | null;
  assigned_ad_account_id: string | null;
  notes: string | null;
  has_credentials: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export async function getInventoryItems(params?: {
  item_type?: string;
  status?: string;
}): Promise<InventoryItem[]> {
  const q = new URLSearchParams();
  if (params?.item_type) q.append("item_type", params.item_type);
  if (params?.status) q.append("status", params.status);
  const query = q.toString() ? `?${q.toString()}` : "";
  return fetchJson<InventoryItem[]>(`/inventory${query}`);
}

export async function createInventoryItem(body: {
  item_type: string;
  name: string;
  credentials: string;
  notes?: string;
  assigned_customer_id?: number | null;
  assigned_ad_account_id?: string | null;
}): Promise<InventoryItem> {
  return postJson<InventoryItem>("/inventory", body);
}

export async function getInventoryCredentials(
  itemId: number
): Promise<{ id: number; name: string; item_type: string; credentials: string }> {
  return fetchJson<{ id: number; name: string; item_type: string; credentials: string }>(
    `/inventory/${itemId}/credentials`
  );
}

export async function handoverInventoryItem(
  itemId: number,
  body: { customer_id: number; assigned_ad_account_id?: string; actor?: string }
): Promise<InventoryItem & { credentials?: string }> {
  return postJson<InventoryItem & { credentials?: string }>(`/inventory/${itemId}/handover`, body);
}

export async function updateInventoryStatus(
  itemId: number,
  body: { status: string; notes?: string }
): Promise<InventoryItem> {
  return patchJson<InventoryItem>(`/inventory/${itemId}/status`, body);
}

export async function deleteInventoryItem(itemId: number): Promise<{ message: string }> {
  return deleteJson<{ message: string }>(`/inventory/${itemId}`);
}

// ==========================================
// CLIENT PORTAL TYPES & CLIENTS
// ==========================================

export type ClientPortalData = {
  customer: {
    id: number;
    name: string;
    fee_rate: number;
    recon_mode: string;
  };
  balances: {
    currency: string;
    amount: string;
    low_threshold: string | null;
    deposit_info: string;
    low_alert: boolean;
  }[];
  assigned_accounts: {
    meta_ad_account_id: string;
    name: string;
    status: string;
    timezone_name: string;
    total_spend: number;
    currency: string;
    campaign_count: number;
  }[];
  recent_transactions: {
    id: number;
    amount: string;
    currency: string;
    kind: string;
    status: string;
    evidence: string;
    created_at: string | null;
    executed_at: string | null;
  }[];
};

export async function getClientPortalData(token: string): Promise<ClientPortalData> {
  return fetchJson<ClientPortalData>(`/portal/${token}`);
}

export async function generatePortalToken(
  customerId: number
): Promise<{ customer_id: number; customer_name: string; portal_token: string; portal_url: string }> {
  return postJson<{ customer_id: number; customer_name: string; portal_token: string; portal_url: string }>(
    `/portal/customers/${customerId}/generate-token`,
    {}
  );
}

export async function revokePortalToken(customerId: number): Promise<{ message: string }> {
  return deleteJson<{ message: string }>(`/portal/customers/${customerId}/token`);
}

// ==========================================
// VIOLATION OVERRIDE & KILLSWITCH CLIENTS
// ==========================================

export async function setViolationOverride(
  accountId: string,
  enabled: boolean
): Promise<{ meta_ad_account_id: string; allow_violated_accounts: boolean }> {
  return postJson<{ meta_ad_account_id: string; allow_violated_accounts: boolean }>(
    `/meta/accounts/${accountId}/violation-override`,
    { enabled }
  );
}

export async function lockMetaAccount(
  accountId: string
): Promise<{ account_id: string; locked: boolean; message: string }> {
  return postJson<{ account_id: string; locked: boolean; message: string }>(
    `/meta-risk/${accountId}/lock`,
    {}
  );
}

export async function unlockMetaAccount(
  accountId: string
): Promise<{ account_id: string; locked: boolean; message: string }> {
  return postJson<{ account_id: string; locked: boolean; message: string }>(
    `/meta-risk/${accountId}/unlock`,
    {}
  );
}


// ==========================================
// UNIFIED PLATFORM & CLIENT TASKS CLIENTS
// ==========================================

export type ClientTaskItem = {
  id: number;
  customer_id: number | null;
  customer_name: string | null;
  telegram_chat_id: string;
  telegram_username: string | null;
  sender_name: string | null;
  task_type: string;
  task_type_label: string;
  raw_message: string;
  extracted_data: Record<string, unknown>;
  status: "PENDING" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED" | string;
  priority: "LOW" | "NORMAL" | "HIGH" | "URGENT" | string;
  assigned_to: string | null;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type RemoteCommandItem = {
  id: string;
  legacy_id: number;
  customer_id: number | null;
  customer_name: string | null;
  ad_account_id: string;
  campaign_name: string | null;
  command_type: string;
  status: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED" | "CANCELLED" | string;
  result_log: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export async function getRemoteCommands(): Promise<RemoteCommandItem[]> {
  return fetchJson<RemoteCommandItem[]>("/remote-commands");
}

export async function cancelRemoteCommand(
  commandId: string
): Promise<{ success: boolean; message: string; command: RemoteCommandItem }> {
  return postJson(`/remote-commands/${encodeURIComponent(commandId)}/cancel`);
}

export type UnifiedOverview = {
  timestamp: string;
  platform_mode: string;
  connectors: {
    meta_ads: { name: string; version: string; mode: string; status: string };
    binance: { name: string; connected: boolean; label: string | null; read_only_verified: boolean; last_ok_at: string | null };
    pingpong: { name: string; connected: boolean; label: string | null; read_only_verified: boolean; last_ok_at: string | null };
    tron: { name: string; configured: boolean; address: string | null };
    sheets: { name: string; active_sources: number };
    telegram: { name: string; configured: boolean; active_rules: number };
  };
  stats: {
    total_ad_accounts: number;
    total_campaigns: number;
    pending_client_tasks: number;
  };
};

export type UnifiedTreasury = {
  total_liquid_usd_estimate: string;
  sources: {
    id: number;
    provider: string;
    live_count?: number;
  die_count?: number;
  unsettled_count?: number;
  assigned_count?: number;
  unassigned_count?: number;
  label: string;
    last_checked_at: string | null;
    balances: { wallet_type: string; asset: string; free: string; locked: string; total: string }[];
    cards: {
      card_id: string;
      card_label: string | null;
      card_last4: string;
      currency: string;
      status: string;
      spending_limit: string | null;
      balance: string;
    }[];
  }[];
  note: string;
};

export type UnifiedAccountItem = {
  id: number;
  meta_ad_account_id: string;
  name: string;
  business_manager_id: string | null;
  timezone_name: string;
  status: string;
  allow_violated_accounts: boolean;
  locked: boolean;
  risk_code: string;
  debt: string;
  currency: string;
  checked_at: string | null;
};

export async function getUnifiedOverview(): Promise<UnifiedOverview> {
  return fetchJson<UnifiedOverview>("/unified/overview");
}

export async function getUnifiedTreasury(): Promise<UnifiedTreasury> {
  return fetchJson<UnifiedTreasury>("/unified/treasury");
}

export async function getUnifiedAccounts(): Promise<UnifiedAccountItem[]> {
  return fetchJson<UnifiedAccountItem[]>("/unified/accounts");
}

export async function getClientTasks(params?: {
  status?: string;
  task_type?: string;
  customer_id?: number;
}): Promise<ClientTaskItem[]> {
  const q = new URLSearchParams();
  if (params?.status) q.append("status", params.status);
  if (params?.task_type) q.append("task_type", params.task_type);
  if (params?.customer_id) q.append("customer_id", String(params.customer_id));
  const query = q.toString() ? `?${q.toString()}` : "";
  return fetchJson<ClientTaskItem[]>(`/unified/tasks${query}`);
}

export async function updateClientTaskStatus(
  taskId: number,
  body: { status: string; notes?: string; assigned_to?: string; actor?: string }
): Promise<{ id: number; status: string; assigned_to?: string; notes?: string; message: string }> {
  return postJson(`/unified/tasks/${taskId}/status`, body);
}

export async function createClientTaskManual(body: {
  customer_id?: number | null;
  task_type: string;
  raw_message: string;
  extracted_data?: Record<string, unknown>;
  priority?: string;
  assigned_to?: string;
  notes?: string;
  sender_name?: string;
}): Promise<{ id: number; status: string; message: string }> {
  return postJson("/unified/tasks/create", body);
}


// -----------------------------------------------------------------------------
// MULTI-BM PREFERENCES & ROUTING
// -----------------------------------------------------------------------------

export type ClientBMPreference = {
  client_id: number;
  customer_id: number;
  customer_name: string;
  preferred_bm_id: string;
  bm_name: string;
  bm_full_name: string;
  is_primary_rental?: boolean;
  via_profile_id?: number | null;
  via_uid?: string | null;
  via_profile_name?: string | null;
  bm_role: "EMPLOYEE" | "ADMIN" | string;
  bm_role_label: string;
  ad_account_access_type: "FULL" | "PARTIAL" | string;
  ad_account_access_label: string;
  partial_permissions: string[];
  partial_permissions_labels: string[];
  is_configured: boolean;
  notes: string | null;
  updated_at: string | null;
};

export type BMRoutingOptions = {
  available_bms: {
    id: string;
    name: string;
    full_name: string;
    description: string;
    is_primary_rental?: boolean;
    via_uid?: string;
    via_profile_id?: number | null;
  }[];
  roles: { value: string; label: string; description: string }[];
  access_types: { value: string; label: string; description: string }[];
  partial_permissions: { key: string; label: string; description: string }[];
};

export async function getBMRoutingOptions(): Promise<BMRoutingOptions> {
  return fetchJson<BMRoutingOptions>("/clients/bm-options");
}

export async function getClientBMPreferences(): Promise<ClientBMPreference[]> {
  return fetchJson<ClientBMPreference[]>("/clients/preferences");
}

export async function getClientBMPreference(clientId: number): Promise<ClientBMPreference> {
  return fetchJson<ClientBMPreference>(`/clients/${clientId}/bm-preferences`);
}

export async function updateClientBMPreference(
  clientId: number,
  body: {
    preferred_bm_id?: string;
    via_profile_id?: number | null;
    bm_role?: string;
    ad_account_access_type?: string;
    partial_permissions?: string[];
    notes?: string;
    actor?: string;
  }
): Promise<{ success: boolean; message: string; preference: ClientBMPreference }> {
  return patchJson(`/clients/${clientId}/bm-preferences`, body);
}


// ==========================================
// MULTI-VIA FARM & BM ASSET DISCOVERY TYPES
// ==========================================

export type ViaProfile = {
  id: number;
  uid: string;
  profile_name: string;
  profile_dir: string;
  user_agent: string;
  uid_live_status: "LIVE" | "DIE" | "UNKNOWN" | string;
  token_status: "ACTIVE" | "EXPIRED" | "CHECKPOINT" | "NONE" | string;
  email: string;
  backup_email: string;
  has_2fa: boolean;
  live_2fa: {
    code: string;
    remaining_seconds: number;
  };
  proxy: {
    config: string;
    display: string;
    status: string;
  };
  category: { id: number; name: string; color: string | null } | null;
  device_name: string | null;
  gender: string | null;
  birthday: string | null;
  note: string | null;
  friends_count: number;
  groups_count: number;
  bm_count: number;
  ad_account_count: number;
  page_count: number;
  last_live_check_at: string | null;
  last_token_refresh: string | null;
  token_expires_at: string | null;
  last_synced_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type SyncedBM = {
  id: number;
  bm_id: string;
  name: string;
  is_primary_rental: boolean;
  via_profile_id: number | null;
  via_uid: string | null;
  via_profile_name: string | null;
  ad_account_count: number;
  page_count: number;
  status: string;
  bm_level?: string;
  verified_status?: string;
  created_year?: string;
  admin_count?: number;
  hidden_admin_count?: number;
  can_create_ad_account?: boolean;
  updated_at: string | null;
};

export type ViaStats = {
  total_vias: number;
  live_count: number;
  die_count: number;
  unknown_count: number;
  active_tokens: number;
  checkpoint_tokens: number;
  total_bms: number;
  primary_bms: number;
  total_ad_accounts: number;
  total_pages: number;
};

export async function getVias(params?: {
  search?: string;
  uid_status?: string;
  token_status?: string;
}): Promise<{ vias: ViaProfile[]; stats: ViaStats }> {
  const q = new URLSearchParams();
  if (params?.search) q.append("search", params.search);
  if (params?.uid_status) q.append("uid_status", params.uid_status);
  if (params?.token_status) q.append("token_status", params.token_status);
  const query = q.toString() ? `?${q.toString()}` : "";
  return fetchJson<{ vias: ViaProfile[]; stats: ViaStats }>(`/vias${query}`);
}

export async function createVia(body: {
  uid: string;
  password: string;
  profile_name?: string;
  two_fa_secret?: string;
  email?: string;
  email_password?: string;
  backup_email?: string;
  proxy_config?: string;
  cookie?: string;
  access_token?: string;
}): Promise<{ success: boolean; message: string; via: ViaProfile }> {
  return postJson("/vias", body);
}

export async function bulkImportVias(
  raw_text: string,
  default_proxy?: string
): Promise<{ success: boolean; total_parsed: number; imported: number; updated: number; errors: string[] }> {
  return postJson("/vias/bulk", { raw_text, default_proxy });
}

export async function getVia2FA(viaId: number): Promise<{
  via_id: number;
  uid: string;
  code: string;
  remaining_seconds: number;
  has_2fa: boolean;
  message: string;
}> {
  return fetchJson(`/vias/${viaId}/2fa`);
}

export async function updateViaProxy(
  viaId: number,
  proxy_config: string
): Promise<{ success: boolean; message: string; via: ViaProfile }> {
  return patchJson(`/vias/${viaId}/proxy`, { proxy_config });
}

export async function updateViaInfo(
  viaId: number,
  body: { profile_name?: string; note?: string | null; proxy_url?: string | null }
): Promise<{ success: boolean; message: string; via: ViaProfile }> {
  return patchJson(`/vias/${viaId}`, body);
}

export async function checkViaLive(viaId: number): Promise<{
  via_id: number;
  uid: string;
  uid_live_status: string;
  last_live_check_at: string;
  message: string;
}> {
  return postJson(`/vias/${viaId}/check-live`, {});
}

export async function checkViasLiveBulk(viaIds?: number[]): Promise<{
  total_checked: number;
  live_count: number;
  die_count: number;
  timestamp: string;
}> {
  return postJson("/vias/check-live-bulk", { via_ids: viaIds || null });
}

export async function loginVia(
  viaId: number,
  body?: { cookie?: string; access_token?: string }
): Promise<{
  success: boolean;
  via_id: number;
  uid: string;
  token_status: string;
  live_2fa_code?: string;
  profile_dir?: string;
  message: string;
}> {
  return postJson(`/vias/${viaId}/login`, body || {});
}

export async function syncViaAssets(viaId: number, signal?: AbortSignal): Promise<{
  success: boolean;
  via_id: number;
  uid: string;
  bms_synced: number;
  ad_account_count: number;
  page_count: number;
  message: string;
}> {
  return postJson(`/vias/${viaId}/sync-assets`, {}, { signal });
}

export async function forceSyncAllViaAssets(): Promise<{
  accepted: boolean;
  message: string;
}> {
  return postJson("/vias/sync-assets-all", {});
}

export async function deleteVia(viaId: number): Promise<{ success: boolean; message: string }> {
  return deleteJson(`/vias/${viaId}`);
}

export async function getSyncedBMs(only_primary?: boolean): Promise<{
  bms: SyncedBM[];
  total: number;
  primary_rental_count: number;
}> {
  const query = only_primary ? "?only_primary=true" : "";
  return fetchJson(`/vias/bms/synced${query}`);
}

export async function togglePrimaryRentalBM(
  bmId: string,
  is_primary?: boolean
): Promise<{ success: boolean; message: string; bm: SyncedBM }> {
  return patchJson(`/vias/bms/${bmId}/primary`, { is_primary_rental: is_primary });
}

// ==========================================
// SMIT ADS CHECK EXPLORER & QUICK ACTIONS
// ==========================================

export type SyncedAdAccount = {
  id: number;
  via_profile_id: number;
  via_uid: string | null;
  via_profile_name: string | null;
  customer_id?: number | null;
  customer_name?: string | null;
  is_assigned?: boolean;
  service_fee_rate?: string | null;
  service_fee_percent?: string | null;
  bm_id: string | null;
  account_type: "PERSONAL" | "BM" | string;
  act_id: string;
  name: string;
  status_dot: "LIVE" | "DIE" | "WARNING" | string;
  account_status: number;
  balance: number;
  threshold: number;
  ad_trust_dsl: number;
  hidden_limit?: number;
  funding_source_summary?: string;
  card_bin?: string;
  location_verified?: boolean;
  appeal_status?: string;
  total_spend: number;
  currency: string;
  payment_card_brand: string | null;
  payment_card_last4: string | null;
  card_display: string;
  disable_reason?: string;
  user_role?: string;
  timezone_name?: string;
  country_code?: string;
  tax_status?: string;
  admin_count?: number;
  hidden_admin_count?: number;
  pixel_id?: string | null;
  pixel_list?: unknown;
  last_billed_date: string | null;
  next_bill_date: string | null;
  updated_at: string | null;
};

export type SyncedPageItem = {
  id: number;
  via_profile_id: number;
  via_uid: string | null;
  via_profile_name: string | null;
  page_id: string;
  name: string;
  category: string;
  likes_count: number;
  followers_count: number;
  is_published: boolean;
  appeal_status?: string;
  updated_at: string | null;
};

export type AdsCheckSummary = {
  total_accounts_count: number;
  total_balance: number;
  total_threshold: number;
  total_limit: number;
  total_spend: number;
  primary_currency: string;
  currency_breakdown?: Record<string, {
    count: number;
    balance: number;
    threshold: number;
    limit: number;
    total_spend: number;
  }>;
  label: string;
};

export type AdsCheckItem = SyncedAdAccount | SyncedBM | SyncedPageItem;
export type AdsCheckResponse = {
  tab: "personal" | "bm" | "group" | "page" | string;
  page: number;
  page_size: number;
  total_count: number;
  total_pages: number;
  summary: AdsCheckSummary;
  items: AdsCheckItem[];
  system_status: string;
};

export async function getAdsCheckData(params?: {
  tab?: string;
  via_id?: number;
  currency_display?: string;
  search?: string;
  status?: string;
  assignment_status?: string;
  customer_id?: number;
  bm_id?: string;
  account_ids?: string;
  card_status?: string;
  account_type?: string;
  currency?: string;
  status_filter?: string;
  mode?: string;
  page?: number;
  page_size?: number;
}): Promise<AdsCheckResponse> {
  const q = new URLSearchParams();
  if (params?.tab) q.append("tab", params.tab);
  if (params?.via_id) q.append("via_id", String(params.via_id));
  if (params?.currency_display) q.append("currency_display", params.currency_display);
  if (params?.search) q.append("search", params.search);
  if (params?.status) q.append("status", params.status);
  if (params?.status_filter) q.append("status_filter", params.status_filter);
  if (params?.assignment_status) q.append("assignment_status", params.assignment_status);
  if (params?.customer_id) q.append("customer_id", String(params.customer_id));
  if (params?.bm_id) q.append("bm_id", params.bm_id);
  if (params?.account_ids) q.append("account_ids", params.account_ids);
  if (params?.card_status) q.append("card_status", params.card_status);
  if (params?.account_type) q.append("account_type", params.account_type);
  if (params?.currency) q.append("currency", params.currency);
  if (params?.mode) q.append("mode", params.mode);
  if (params?.page) q.append("page", String(params.page));
  if (params?.page_size) q.append("page_size", String(params.page_size));
  const query = q.toString() ? `?${q.toString()}` : "";
  return fetchJson<AdsCheckResponse>(`/vias/ads-check${query}`);
}

export async function assignAccountCustomer(
  act_id: string,
  customer_id: number | null
): Promise<{ success: boolean; account: SyncedAdAccount; message: string }> {
  return postJson("/vias/ads-check/assign-customer", { act_id, customer_id });
}

export async function updateAdsCheckAccount(
  actId: string,
  body: { customer_id?: number | null; service_fee_percent?: string | number | null },
): Promise<{ success: boolean; account: SyncedAdAccount; message: string }> {
  return patchJson(`/ads-check/accounts/${actId}`, body);
}

export type ShareBmAccountsResult = {
  success: boolean;
  command_id: string;
  results: Array<{ account_id: string; status: string }>;
  invite_link: string;
  message: string;
};

export async function shareBmAccounts(body: {
  bm_id: string;
  customer_emails: string[];
  bm_role: string;
  ad_account_tasks: string[];
  account_ids: string[];
  customer_id?: number;
}): Promise<ShareBmAccountsResult> {
  return postJson("/ads-check/share-bm-accounts", body);
}

export async function bulkAssignAccountsCustomer(
  account_ids: string[],
  customer_id: number | null
): Promise<{ success: boolean; updated_count: number; customer_id: number | null; customer_name?: string; message: string }> {
  return postJson("/vias/ads-check/bulk-assign-customer", { account_ids, customer_id });
}

export async function loadSmitMode(req: {
  mode: "LOAD_ALL" | "LOAD_BY_ACT_IDS" | "LOAD_BY_BM_ID" | "LOAD_BY_VIA_ID" | string;
  account_ids?: string[];
  bm_id?: string;
  via_id?: number;
  status?: string;
}): Promise<AdsCheckResponse> {
  return postJson("/vias/ads-check/load-mode", req);
}

export async function removeHiddenAdmins(body: {
  account_ids: string[];
  via_id?: number;
}): Promise<{
  success: boolean;
  cleaned_count: number;
  cleaned_accounts: string[];
  message: string;
}> {
  return postJson("/vias/ads-check/remove-hidden-admins", body);
}

export async function renameAccounts(body: {
  account_ids: string[];
  prefix?: string;
  suffix?: string;
  new_name?: string;
  currency?: string;
  timezone_name?: string;
  country_code?: string;
  tax_status?: string;
}): Promise<{
  success: boolean;
  updated_count: number;
  updated_accounts: string[];
  message: string;
}> {
  return postJson("/vias/ads-check/rename-accounts", body);
}

export async function sharePixel(body: {
  pixel_id: string;
  target_account_ids: string[];
  bm_id?: string;
}): Promise<{
  success: boolean;
  pixel_id: string;
  shared_count: number;
  target_accounts: string[];
  bm_id?: string;
  message: string;
}> {
  return postJson("/vias/ads-check/share-pixel", body);
}

export async function superShareAds(body: {
  client_id: number;
  account_ids: string[];
  bm_id?: string;
  via_profile_id?: number;
  role?: string;
  access_type?: string;
  partial_permissions?: string[];
}): Promise<{
  success: boolean;
  client_id: number;
  client_name?: string;
  shared_accounts_count: number;
  account_ids: string[];
  bm_id?: string;
  via_profile_id?: number;
  saved_preferences: boolean;
  message: string;
}> {
  return postJson("/vias/ads-check/super-share-ads", body);
}

export async function launchViaBrowser(
  viaId: number,
  body?: {
    target_type?: string;
    act_id?: string;
    bm_id?: string;
    page_id?: string;
    custom_url?: string;
  }
): Promise<{
  success: boolean;
  launched: boolean;
  simulated: boolean;
  pid: number | null;
  browser_name: string;
  via_id: number;
  via_uid: string;
  profile_name?: string;
  target_url: string;
  live_2fa_code?: string;
  message: string;
}> {
  return postJson(`/vias/${viaId}/launch-browser`, body || {});
}

export async function syncBrowserCookie(viaId: number, cookie: string): Promise<{
  success: boolean;
  via_id: number;
  uid: string;
  token_status: string;
  uid_live_status: string;
  message: string;
}> {
  return postJson(`/vias/${viaId}/sync-browser-cookie`, { cookie });
}

export async function harvestViaSession(viaId: number, signal?: AbortSignal): Promise<{
  success: boolean;
  via_id: number;
  token_status?: string;
  uid_live_status?: string;
  ad_account_count?: number;
  bm_count?: number;
  page_count?: number;
  source?: string;
  message: string;
  via?: ViaProfile;
}> {
  return postJson(`/vias/${viaId}/harvest-session`, {}, { signal });
}

export async function updateManualCredentials(
  viaId: number,
  body: { cookie?: string; access_token?: string }
): Promise<{
  success: boolean;
  via_id: number;
  token_status?: string;
  uid_live_status?: string;
  ad_account_count?: number;
  bm_count?: number;
  page_count?: number;
  message: string;
  via?: ViaProfile;
}> {
  return postJson(`/vias/${viaId}/manual-credentials`, body);
}

export async function openInViaBrowser(body: {
  act_id?: string;
  bm_id?: string;
  page_id?: string;
  via_id?: number;
  target_type?: "ADS_MANAGER" | "BILLING" | "BM_SETTINGS" | "PAGE" | "FB_HOME" | string;
  custom_url?: string;
}): Promise<{
  success: boolean;
  launched: boolean;
  simulated: boolean;
  pid: number | null;
  browser_name: string;
  via_id: number;
  via_uid: string;
  profile_name?: string;
  target_url: string;
  live_2fa_code?: string;
  message: string;
}> {
  return postJson("/vias/ads-check/open-in-via", body);
}

export async function extendedPaymentAction(body: {
  account_ids: string[];
  action: "PAY_NOW" | "SET_PRIMARY_CARD" | "ADD_BACKUP_CARD" | "REMOVE_CARD" | "FETCH_INVOICES" | string;
  card_brand?: string;
  card_last4?: string;
  amount?: number;
}): Promise<{
  success: boolean;
  action: string;
  affected_accounts: string[];
  count: number;
  invoices?: Array<{
    act_id: string;
    name: string;
    invoice_id: string;
    amount: number;
    currency: string;
    payment_method: string;
    billing_date: string;
    status: string;
  }>;
  message: string;
}> {
  return postJson("/vias/ads-check/extended-payment", body);
}

export async function superTargetAction(body: {
  keyword?: string;
  action?: "SEARCH_INTERESTS" | "APPEAL_ACCOUNT" | string;
  account_ids?: string[];
  appeal_reason?: string;
}): Promise<{
  success: boolean;
  action: string;
  keyword?: string;
  interests?: Array<{
    id: string;
    name: string;
    path: string[];
    audience_size_lower_bound: number;
    audience_size_upper_bound: number;
    topic: string;
  }>;
  appealed_accounts?: string[];
  message: string;
}> {
  return postJson("/vias/ads-check/super-target", body);
}

export function getAdsCheckExportUrl(params: {
  tab?: string;
  via_id?: number;
  format_type?: "csv" | "txt";
}): string {
  const q = new URLSearchParams();
  if (params.tab) q.append("tab", params.tab);
  if (params.via_id) q.append("via_id", String(params.via_id));
  if (params.format_type) q.append("format_type", params.format_type);
  return `/api/v1/vias/ads-check/export?${q.toString()}`;
}

// ==========================================
// MAXCARE SUITE — Danh mục, Import, Bulk Login, Seeding, Đồng bộ báo cáo, Xuất
// ==========================================

export type ViaCategoryItem = {
  id: number;
  name: string;
  color: string | null;
  via_count: number;
};

export type MaxcareCategory = { id: number; name: string; color: string | null };

export type MaxcareImportResult = {
  success: boolean;
  total_parsed: number;
  imported: number;
  updated: number;
  errors: string[];
  categories: string[];
};

export type MaxcareLoginResultItem = {
  via_id: number;
  uid?: string | null;
  ok: boolean;
  token_status?: string | null;
  message?: string;
};

export type MaxcareBulkLoginResult = {
  total: number;
  done: MaxcareLoginResultItem[];
  failed: MaxcareLoginResultItem[];
  concurrency?: number;
  timestamp?: string;
  message: string;
};

export type MaxcareCheckLiveResult = {
  action: string;
  total_checked: number;
  live_count: number;
  die_count: number;
  timestamp: string;
};

export type MaxcareUpdateInfoResult = {
  total: number;
  updated: number;
  category: string | null;
  message: string;
};

export type MaxcareExportTokensResult = {
  format: string;
  filename: string;
  content: string;
  total: number;
};

export type MaxcareSeedingCatalogAction = {
  value: string;
  label: string;
  description: string;
};

export type MaxcareSeedingResultItem = {
  via_id: number;
  uid: string;
  status: string;
  detail?: string;
};

export type MaxcareSeedingRunResult = {
  action: string;
  total: number;
  done: number;
  planned: number;
  failed: number;
  results: MaxcareSeedingResultItem[];
  timestamp: string;
};

export type MaxcareSyncReportItem = {
  via_id: number;
  ok: boolean;
  accounts_updated?: number;
  snapshots_created?: number;
  error?: string;
  message?: string;
};

export type MaxcareSyncReportsResult = {
  total: number;
  done: MaxcareSyncReportItem[];
  failed: MaxcareSyncReportItem[];
  concurrency: number;
  timestamp?: string;
};

export type MaxcareActivityLogItem = {
  id: number;
  via_id: number | null;
  action: string;
  status: string;
  detail: string;
  created_at: string | null;
};

export type MaxcareActivityLogsResponse = {
  total: number;
  logs: MaxcareActivityLogItem[];
};

export type MaxcareSnapshotItem = {
  id: number;
  act_id: string;
  status_dot: string | null;
  account_status: number | null;
  balance: number | string;
  threshold: number | string;
  ad_trust_dsl: number | string;
  daily_budget: number | string;
  total_spend: number | string;
  currency: string;
  snapshot_at: string | null;
  source: string;
};

export async function getMaxcareCategories(): Promise<{ categories: ViaCategoryItem[] }> {
  return fetchJson("/vias/maxcare/categories");
}

export async function createMaxcareCategory(
  name: string,
  description?: string
): Promise<{ success: boolean; category: MaxcareCategory }> {
  return postJson("/vias/maxcare/categories", { name, description: description || null });
}

export async function renameMaxcareCategory(
  categoryId: number,
  name: string
): Promise<{ success: boolean; category: MaxcareCategory }> {
  return patchJson(`/vias/maxcare/categories/${categoryId}`, { name });
}

export async function deleteMaxcareCategory(
  categoryId: number
): Promise<{ success: boolean; message: string }> {
  return deleteJson(`/vias/maxcare/categories/${categoryId}`);
}

export async function maxcareBulkImport(
  raw_text: string,
  default_category?: string
): Promise<MaxcareImportResult> {
  return postJson("/vias/maxcare/import", { raw_text, default_category: default_category || null });
}

export async function maxcareAction(
  action: "BULK_LOGIN" | "CHECK_LIVE" | "UPDATE_INFO" | "EXPORT_TOKENS" | string,
  via_ids?: number[],
  params?: Record<string, unknown>
): Promise<
  | MaxcareBulkLoginResult
  | MaxcareCheckLiveResult
  | MaxcareUpdateInfoResult
  | MaxcareExportTokensResult
> {
  return postJson("/vias/maxcare-action", {
    action,
    via_ids: via_ids && via_ids.length > 0 ? via_ids : null,
    params: params || null,
  });
}

export async function getMaxcareSeedingCatalog(): Promise<{
  actions: MaxcareSeedingCatalogAction[];
}> {
  return fetchJson("/vias/maxcare/seeding");
}

export async function maxcareRunSeeding(body: {
  via_ids: number[];
  actions: string[];
  scroll_count?: number;
  like_count?: number;
  join_group_count?: number;
}): Promise<{ success: boolean; results: MaxcareSeedingRunResult[] }> {
  return postJson("/vias/maxcare/seeding", body);
}

export async function maxcareSyncReports(body: {
  via_ids?: number[];
  concurrency?: number;
}): Promise<MaxcareSyncReportsResult> {
  return postJson("/vias/maxcare/sync-reports", {
    via_ids: body.via_ids && body.via_ids.length > 0 ? body.via_ids : null,
    concurrency: body.concurrency ?? 5,
  });
}

export async function getMaxcareActivityLogs(params?: {
  limit?: number;
  offset?: number;
  via_id?: number;
}): Promise<MaxcareActivityLogsResponse> {
  const q = new URLSearchParams();
  if (params?.limit) q.append("limit", String(params.limit));
  if (params?.offset) q.append("offset", String(params.offset));
  if (params?.via_id) q.append("via_id", String(params.via_id));
  const query = q.toString() ? `?${q.toString()}` : "";
  return fetchJson(`/vias/maxcare/activity-logs${query}`);
}

export async function getMaxcareSnapshots(limit?: number): Promise<{
  snapshots: MaxcareSnapshotItem[];
}> {
  const query = limit ? `?limit=${limit}` : "";
  return fetchJson(`/vias/maxcare/snapshots${query}`);
}

export function getMaxcareReportsExportUrl(limit?: number): string {
  const q = limit ? `?limit=${limit}` : "";
  return `${API_BASE}/api/v1/vias/maxcare/reports/export${q}`;
}

export function getMaxcareTokensExportUrl(params: {
  style?: "csv" | "pipe";
  via_ids?: number[];
}): string {
  const q = new URLSearchParams();
  if (params.style) q.append("style", params.style);
  if (params.via_ids && params.via_ids.length > 0)
    q.append("via_ids", params.via_ids.join(","));
  return `${API_BASE}/api/v1/vias/maxcare/tokens/export?${q.toString()}`;
}

// ==========================================
// DAILY PROFIT & VIA SHEET WRITEBACK TYPES
// ==========================================

export type DailyBreakdownItem = {
  date: string;
  day: number;
  spend_vnd: string | null;
  fee: string | null;
  fee_rate_pct: string | null;
  budget_deposits_vnd: string;
  usdt_net: string;
  source_type: "DAILY_ROW" | "NO_DATA";
  active_clients: number;
};

export type ClientDailyBreakdownItem = {
  customer_id: number;
  customer_name: string;
  spend_vnd: string | null;
  fee_rate_pct: string | null;
  fee: string | null;
  budget_deposits_vnd: string;
  usdt_net: string;
  source_type: string;
};

export type DailySummary = {
  selected_date: string;
  profit_selected_date: string | null;
  spend_selected_date: string | null;
  avg_daily_profit: string | null;
  peak_profit_date: {
    date: string;
    fee: string | null;
    spend_vnd: string | null;
  } | null;
  effective_fee_rate_pct: string | null;
  total_month_spend: string | null;
  total_month_fee: string | null;
  total_month_deposits: string;
  total_month_usdt: string;
  days_with_data: number;
  total_days_in_month: number;
};

export type SheetWritebackItem = {
  customer_id: number;
  customer_name: string;
  sheet_title: string;
  spreadsheet_id?: string | null;
  row_index: number;
  action: "UPDATED_EXISTING_ROW" | "INSERTED_NEW_ROW";
  status: string;
  ad_accounts: string[];
  account_names: string;
  account_ids_str: string;
  previous_spend_vnd: string;
  new_spend_vnd: string;
  fee_rate_pct: string;
  fee_vnd: string;
  total_vnd: string;
  preserved_deposits: {
    budget_deposits_vnd: string;
    usdt_received: string;
    usdt_refunded?: string;
    note?: string;
  };
  cells_updated: string[];
  data_source: string;
};

export type SheetWritebackResponse = {
  success: boolean;
  dry_run: boolean;
  execution_status: string;
  message: string;
  report_date_iso: string;
  report_date_vn: string;
  period: string;
  total_clients: number;
  clients: SheetWritebackItem[];
  summary: {
    total_spend_vnd: string;
    total_fee_vnd: string;
    total_including_fee_vnd: string;
    rows_inserted: number;
    rows_updated: number;
  };
};

export async function postSheetWritebackFromVias(body: {
  report_date: string;
  client_ids?: number[];
  dry_run?: boolean;
  auto_create_borders?: boolean;
}): Promise<SheetWritebackResponse> {
  return postJson<SheetWritebackResponse>("/sheets/writeback-from-vias", {
    report_date: body.report_date,
    client_ids: body.client_ids && body.client_ids.length > 0 ? body.client_ids : null,
    dry_run: body.dry_run ?? true,
    auto_create_borders: body.auto_create_borders ?? true,
  });
}

// ==========================================
// ADSOS CHECK PRO EXTENSION & REMOTE TASKS
// ==========================================

export type ExtensionClientKeyItem = {
  id: number;
  client_id: number | null;
  client_name: string;
  api_key: string;
  is_active: boolean;
  last_seen_at: string | null;
  created_at: string;
};

export type CampaignTemplateItem = {
  id: number;
  name: string;
  client_id: number | null;
  objective: string;
  daily_budget: string;
  currency: string;
  targeting_json: string;
  page_id: string | null;
  post_id_or_creative_json: string | null;
  status_on_create: string;
  created_at: string;
};

export type ExtensionRemoteTaskItem = {
  id: number;
  via_id: number | null;
  fb_uid: string;
  task_type: string;
  target_act_id: string | null;
  payload_json: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | string;
  requested_by: string;
  created_at: string;
};

export function getExtensionDownloadUrl(): string {
  return `${API_BASE}/api/v1/vias/download-extension`;
}

export async function listExtensionClientKeys(): Promise<ExtensionClientKeyItem[]> {
  return fetchJson<ExtensionClientKeyItem[]>("/vias/extension-client-keys");
}

export async function createExtensionClientKey(body: {
  client_name: string;
  client_id?: number | null;
  api_key?: string;
}): Promise<ExtensionClientKeyItem> {
  return postJson<ExtensionClientKeyItem>("/vias/extension-client-keys", body);
}

export async function deleteExtensionClientKey(
  keyId: number
): Promise<{ success: boolean; message: string }> {
  return deleteJson<{ success: boolean; message: string }>(`/vias/extension-client-keys/${keyId}`);
}

export async function listCampaignTemplates(): Promise<CampaignTemplateItem[]> {
  return fetchJson<CampaignTemplateItem[]>("/vias/campaign-templates");
}

export async function createCampaignTemplate(body: {
  name: string;
  client_id?: number | null;
  objective?: string;
  daily_budget?: string;
  currency?: string;
  targeting_json?: string;
  page_id?: string;
  post_id_or_creative_json?: string;
  status_on_create?: string;
}): Promise<CampaignTemplateItem> {
  return postJson<CampaignTemplateItem>("/vias/campaign-templates", body);
}

export async function deleteCampaignTemplate(
  templateId: number
): Promise<{ success: boolean; message: string }> {
  return deleteJson<{ success: boolean; message: string }>(`/vias/campaign-templates/${templateId}`);
}

export async function queueExtensionTask(body: {
  via_id?: number;
  fb_uid?: string;
  client_id?: number;
  task_type: string;
  target_act_id?: string;
  payload?: Record<string, unknown>;
  requested_by?: string;
}): Promise<{
  success: boolean;
  task_id: number;
  task_type: string;
  fb_uid: string;
  status: string;
}> {
  return postJson("/vias/extension-tasks", body);
}

export async function pollExtensionTasks(params?: {
  fb_uid?: string;
  client_key?: string;
  limit?: number;
}): Promise<{ tasks: ExtensionRemoteTaskItem[] }> {
  const q = new URLSearchParams();
  if (params?.fb_uid) q.append("fb_uid", params.fb_uid);
  if (params?.client_key) q.append("client_key", params.client_key);
  if (params?.limit) q.append("limit", String(params.limit));
  const query = q.toString() ? `?${q.toString()}` : "";
  return fetchJson<{ tasks: ExtensionRemoteTaskItem[] }>(`/vias/extension-tasks/poll${query}`);
}

export interface CustomerSpendAccountItem {
  account_id: string;
  name: string;
  amount_spent: number;
  balance: number;
  threshold_amount: number;
  currency: string;
  account_status: string;
  via_uid?: string;
  bm_id?: string;
}

export interface CustomerSpendSummaryItem {
  customer_id: number;
  customer_name: string;
  telegram_username?: string;
  telegram_chat_id?: string;
  fee_rate_percent: number;
  account_count: number;
  raw_spend: number;
  fee_amount: number;
  total_payable: number;
  total_balance: number;
  total_threshold: number;
  accounts: CustomerSpendAccountItem[];
}

export interface CustomerSpendSummaryResponse {
  success: boolean;
  customers: CustomerSpendSummaryItem[];
  grand_totals: {
    total_customers: number;
    grand_raw_spend: number;
    grand_fee_amount: number;
    grand_total_payable: number;
  };
}

export async function getCustomerSpendSummary(customerId?: number): Promise<CustomerSpendSummaryResponse> {
  const query = customerId ? `?customer_id=${customerId}` : "";
  return fetchJson<CustomerSpendSummaryResponse>(`/vias/customer-spend-summary${query}`);
}

// ==========================================
// 4-PILLAR CONTROL HUB & WORKFLOW AUTOMATION (D-065)
// ==========================================

export type BrowserNodeItem = {
  id: number;
  node_uid: string;
  node_name: string;
  browser_type: string;
  via_id: number | null;
  fb_uid: string | null;
  status: "ONLINE" | "OFFLINE" | "BUSY" | string;
  last_heartbeat_at: string | null;
  has_eaag: boolean;
  has_eaab: boolean;
  has_cookie: boolean;
  has_fb_dtsg: boolean;
  pending_tasks: number;
  created_at: string | null;
};

export type WorkflowTemplateItem = {
  id: number;
  code: string;
  name: string;
  category: string;
  steps: Array<{ action: string; label?: string; [key: string]: unknown }>;
  jitter_min_ms: number;
  jitter_max_ms: number;
  is_builtin: boolean;
  created_at: string | null;
};

export type SavedAdAssetItem = {
  id: number;
  asset_type: "AUDIENCE" | "AD_POST" | "SUPER_TARGET_SET" | string;
  name: string;
  source_account_id: string | null;
  payload: Record<string, unknown>;
  created_at: string | null;
};

export type SuperTargetInterest = {
  id: string;
  name: string;
  audience_size_lower_bound?: number;
  audience_size_upper_bound?: number;
  path?: string[];
  description?: string;
  topic?: string;
};

export async function getControlHubNodes(): Promise<{ nodes: BrowserNodeItem[]; total: number; online_count: number }> {
  return fetchJson("/control-hub/nodes");
}

export async function dispatchControlHubCommand(body: {
  node_uid?: string;
  command: string;
  payload?: Record<string, unknown>;
  client_id?: number;
}): Promise<{ success: boolean; task_id?: number; message: string }> {
  return postJson("/control-hub/dispatch", body);
}

export async function getWorkflowTemplates(category?: string): Promise<{ workflows: WorkflowTemplateItem[]; total: number }> {
  const query = category ? `?category=${encodeURIComponent(category)}` : "";
  return fetchJson(`/ads-check/workflows${query}`);
}

export async function createCustomWorkflow(body: {
  code: string;
  name: string;
  category: string;
  steps: Array<Record<string, unknown>>;
  jitter_min_ms?: number;
  jitter_max_ms?: number;
}): Promise<{ success: boolean; workflow: WorkflowTemplateItem }> {
  return postJson("/ads-check/workflows", body);
}

export async function getSuperTargets(keyword: string, limit: number = 200): Promise<{
  success: boolean;
  keyword: string;
  total: number;
  data: SuperTargetInterest[];
}> {
  return fetchJson(`/ads-check/super-target?keyword=${encodeURIComponent(keyword)}&limit=${limit}`);
}

export async function createBulkCamp(body: {
  act_ids: string[];
  name: string;
  objective?: string;
  base_daily_budget_vnd?: number;
  status?: "ACTIVE" | "PAUSED";
  targeting_json?: string;
  page_id?: string;
  post_id?: string;
}): Promise<{
  success: boolean;
  total_accounts: number;
  status: string;
  results: Array<{
    act_id: string;
    currency: string;
    budget_in_currency: number;
    campaign_id?: string;
    status: string;
    error?: string;
  }>;
}> {
  return postJson("/ads-check/bulk-camp", body);
}

export async function getSavedAdAssets(assetType?: string): Promise<{
  assets: SavedAdAssetItem[];
  total: number;
}> {
  const query = assetType ? `?asset_type=${encodeURIComponent(assetType)}` : "";
  return fetchJson(`/ads-check/ads-save${query}`);
}

export async function saveAdAsset(body: {
  asset_type: "AUDIENCE" | "AD_POST" | "SUPER_TARGET_SET" | string;
  name: string;
  source_account_id?: string;
  payload: Record<string, unknown>;
}): Promise<{ success: boolean; asset: SavedAdAssetItem }> {
  return postJson("/ads-check/ads-save", body);
}

export async function deleteSavedAdAsset(id: number): Promise<{ success: boolean; message: string }> {
  return deleteJson(`/ads-check/ads-save/${id}`);
}
