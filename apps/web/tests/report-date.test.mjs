import test from "node:test";
import assert from "node:assert/strict";
import { dateInReportMonth } from "../lib/report-date.mjs";

test("restored October date follows selected November and remains a valid day", () => {
  assert.equal(dateInReportMonth("2026-10-15", "2026", "11"), "2026-11-15");
  assert.equal(dateInReportMonth("2026-10-31", "2026", "11"), "2026-11-30");
});

test("changing year handles leap days and month length", () => {
  assert.equal(dateInReportMonth("2024-02-29", "2026", "02"), "2026-02-28");
  assert.equal(dateInReportMonth("2026-01-31", "2028", "02"), "2028-02-29");
  assert.equal(dateInReportMonth("2026-12-12", "2027", "01"), "2027-01-12");
});

test("selected day is kept and empty date starts at first day", () => {
  assert.equal(dateInReportMonth("2026-11-03", "2026", "11"), "2026-11-03");
  assert.equal(dateInReportMonth("", "2026", "11"), "2026-11-01");
});
