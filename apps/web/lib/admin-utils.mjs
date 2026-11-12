export function sumMoney(values) {
  const parts = values.map(String).map(value => /^(-?)(\d+)(?:\.(\d+))?$/.exec(value));
  if (parts.some(part => !part)) return null;
  const scale = Math.max(0, ...parts.map(part => (part[3] || "").length));
  const sum = parts.reduce((total, part) => total + (part[1] ? -1n : 1n) * BigInt(part[2] + (part[3] || "").padEnd(scale, "0")), 0n);
  const digits = (sum < 0n ? -sum : sum).toString().padStart(scale + 1, "0");
  return (sum < 0n ? "-" : "") + (scale ? `${digits.slice(0, -scale)}.${digits.slice(-scale)}` : digits);
}
export function moneyText(value, currency = "VND") {
  if (value == null || !/^-?\d+(\.\d+)?$/.test(String(value))) return "Chưa có dữ liệu";
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(String(value));
  const places = currency === "VND" ? 0 : 2;
  const fraction = (match[3] || "").padEnd(places + 1, "0");
  let minor = BigInt(match[2] + fraction.slice(0, places));
  if (fraction[places] >= "5") minor++;
  const digits = minor.toString().padStart(places + 1, "0");
  const integer = places ? digits.slice(0, -places) : digits;
  return `${match[1] && minor ? "-" : ""}${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".")}${places ? "," + digits.slice(-places) : ""} ${currency === "VND" ? "đ" : currency}`;
}
export function csvCell(value) {
  let text = String(value ?? "");
  if (/^[=+\-@\t\r]/.test(text)) text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}
export function assignedDebtTotals(accounts) {
  return accounts.reduce((totals, account) => {
    if (account?.customer_id == null) return totals;
    const balance = Number(account.balance);
    if (!Number.isFinite(balance)) return totals;
    const currency = String(account.currency || "").toUpperCase();
    if (currency === "VND") totals.VND += balance;
    if (currency === "USD") totals.USD += balance;
    return totals;
  }, { VND: 0, USD: 0 });
}
export function changePercent(current, previous) {
  const currentParts = /^(-?)(\d+)(?:\.(\d+))?$/.exec(String(current));
  const previousParts = /^(-?)(\d+)(?:\.(\d+))?$/.exec(String(previous));
  if (!currentParts || !previousParts) return null;
  const scale = Math.max((currentParts[3] || "").length, (previousParts[3] || "").length);
  const units = part => (part[1] ? -1n : 1n) * BigInt(part[2] + (part[3] || "").padEnd(scale, "0"));
  const before = units(previousParts);
  if (before <= 0n) return null;
  const numerator = (units(currentParts) - before) * 10000n;
  const absolute = numerator < 0n ? -numerator : numerator;
  const rounded = absolute / before + (absolute % before * 2n >= before ? 1n : 0n);
  return `${numerator < 0n ? "−" : "+"}${rounded / 100n},${String(rounded % 100n).padStart(2, "0")}%`;
}
export function reportWindow(days, today = new Date()) {
  const end = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh", year: "numeric", month: "2-digit", day: "2-digit" }).format(today);
  const date = new Date(end + "T00:00:00Z");
  date.setUTCDate(date.getUTCDate() - days + 1);
  return { from: date.toISOString().slice(0, 10), to: end };
}
