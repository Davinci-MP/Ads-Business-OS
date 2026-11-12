import test from "node:test";
import assert from "node:assert/strict";
import { fetchJson, postJson } from "../lib/api.ts";

test("validation feedback is Vietnamese and never echoes submitted secrets", async () => {
  const original=globalThis.fetch;
  globalThis.fetch=async()=>new Response(JSON.stringify({detail:[{msg:"Invalid input",input:"do-not-show-fixture"}]}),{status:422});
  try { await assert.rejects(postJson("/fixture",{}), error=>error.message.includes("Thông tin nhập chưa hợp lệ")&&!error.message.includes("do-not-show-fixture")); }
  finally { globalThis.fetch=original; }
});
test("network feedback is actionable and abort remains distinguishable", async () => {
  const original=globalThis.fetch;
  try {
    globalThis.fetch=async()=>{throw new TypeError("Failed to fetch")};
    await assert.rejects(fetchJson("/fixture"),/Không thể kết nối máy chủ/);
    globalThis.fetch=async()=>{throw new DOMException("aborted","AbortError")};
    await assert.rejects(fetchJson("/fixture"),error=>error.name==="AbortError");
  } finally { globalThis.fetch=original; }
});
