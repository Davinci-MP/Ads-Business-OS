export function sumMoney(values: (string | number)[]): string | null;
export function moneyText(value: string | number | null | undefined, currency?: string): string;
export function csvCell(value: unknown): string;
export function assignedDebtTotals(accounts: Array<{
  customer_id?: number | null;
  balance?: string | number | null;
  currency?: string | null;
}>): { VND: number; USD: number };
export function changePercent(current: string | number | null | undefined, previous: string | number | null | undefined): string | null;
export function reportWindow(days: number, today?: Date): { from: string; to: string };
