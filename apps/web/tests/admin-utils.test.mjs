import test from "node:test";
import assert from "node:assert/strict";
import { assignedDebtTotals, changePercent, csvCell, moneyText, reportWindow, sumMoney } from "../lib/admin-utils.mjs";

test("money totals use exact decimals and preserve negative and large values", () => {
  assert.equal(sumMoney(["0.1","0.2","-0.05"]),"0.25");
  assert.equal(sumMoney(["9007199254740993.01","0.09"]),"9007199254740993.10");
  assert.equal(sumMoney(["invalid"]),null);
});
test("money labels use half-up rounding and keep unknown distinct from zero", () => {
  assert.equal(moneyText("1.5","VND"),"2 đ");
  assert.equal(moneyText("-1.5","VND"),"-2 đ");
  assert.equal(moneyText("1.005","USD"),"1,01 USD");
  assert.equal(moneyText(null),"Chưa có dữ liệu");
  assert.equal(moneyText("0"),"0 đ");
});
test("CSV escapes quotes and spreadsheet formula prefixes", () => {
  assert.equal(csvCell('a"b'),'"a""b"');
  assert.equal(csvCell("=1+1"),'"\'=1+1"');
});
test("tổng dư nợ chỉ tính tài khoản đã gán và giữ riêng từng tiền tệ", () => {
  assert.deepEqual(assignedDebtTotals([
    { customer_id: 10, balance: 1_500_000, currency: "VND" },
    { customer_id: 11, balance: "12.50", currency: "usd" },
    { customer_id: null, balance: 999_000, currency: "VND" },
    { balance: 20, currency: "USD" },
    { customer_id: 12, balance: 100, currency: "EUR" },
  ]), { VND: 1_500_000, USD: 12.5 });
});
test("date window uses Vietnam business date at UTC midnight boundary", () => {
  assert.deepEqual(reportWindow(7,new Date("2026-11-06T18:00:00Z")),{from:"2026-11-01",to:"2026-11-07"});
});
test("day comparison requires both dates and a positive baseline", () => {
  assert.equal(changePercent("105","100"),"+5,00%");
  assert.equal(changePercent("95","100"),"−5,00%");
  assert.equal(changePercent("1","0"),null);
  assert.equal(changePercent(null,"100"),null);
});
