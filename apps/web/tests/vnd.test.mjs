import { strict as assert } from "node:assert";
import { test } from "node:test";
import { formatBalanceVnd, formatVnd } from "../lib/vnd.mjs";

test("VND display rounds half up exactly and preserves null versus zero", () => {
  assert.equal(formatVnd(null), "—");
  assert.equal(formatVnd(0), "0");
  assert.equal(formatVnd("1234.49"), "1.234");
  assert.equal(formatVnd("1234.50"), "1.235");
  assert.equal(formatVnd("-1234.50"), "-1.235");
  assert.equal(formatVnd("9007199254740993.5"), "9.007.199.254.740.994");
});

test("negative balances retain their sign even when rounded to zero", () => {
  assert.equal(formatBalanceVnd("-0.4"), "-0");
  assert.equal(formatBalanceVnd("-0.5"), "-1");
  assert.equal(formatBalanceVnd("-0.0"), "0");
  assert.equal(formatBalanceVnd(null), "—");
});
