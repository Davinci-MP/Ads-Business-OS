const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const SHEETS_REPORT_WORKBOOK_KEY = "adsos.sheets.report.workbook";

export async function fetchJson<T>(
  path: string,
  opts?: { signal?: AbortSignal },
): Promise<T> {
  const res = await fetch(`${API_URL}/api/v1${path}`, {
    cache: "no-store",
    signal: opts?.signal,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export async function postJson<T>(
  path: string,
  body: unknown = {},
  opts?: { signal?: AbortSignal },
): Promise<T> {
  const res = await fetch(`${API_URL}/api/v1${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
    signal: opts?.signal,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}/api/v1${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
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

export const fmtVnd = (v: string | null) =>
  v == null ? "—" : Number(v).toLocaleString("vi-VN", { maximumFractionDigits: 2 });

export const fmtTime = (v: string | null) => (v == null ? "—" : new Date(v).toLocaleString("vi-VN"));

export const API_BASE = API_URL;
