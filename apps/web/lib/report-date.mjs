// Keep the inspector in the selected reporting period, including restored preferences.
export function dateInReportMonth(value, year, month) {
  if (!/^\d{4}$/.test(year) || Number(year) < 1 || !/^(0[1-9]|1[0-2])$/.test(month)) return value;
  const y = Number(year);
  const m = Number(month);
  const leap = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
  const lastDay = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1];
  const match = /^\d{4}-\d{2}-(\d{2})$/.exec(value);
  const day = Math.min(lastDay, Math.max(1, match ? Number(match[1]) : 1));
  return `${year}-${month}-${String(day).padStart(2, "0")}`;
}
