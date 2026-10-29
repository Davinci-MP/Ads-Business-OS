export function formatVnd(value) {
  if (value === null || value === undefined || value === "") return "—";
  const text = String(value).trim();
  const match = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(text);
  if (!match) return text;
  const fraction = match[3] || "";
  let integer = BigInt(match[2]);
  if (fraction && fraction[0] >= "5") integer += 1n;
  const sign = match[1] === "-" && integer !== 0n ? "-" : "";
  return sign + integer.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

export function formatBalanceVnd(value) {
  const formatted = formatVnd(value);
  const text = String(value).trim();
  return formatted === "0" && /^-\d+(?:\.\d+)?$/.test(text) && /[1-9]/.test(text)
    ? "-0"
    : formatted;
}
