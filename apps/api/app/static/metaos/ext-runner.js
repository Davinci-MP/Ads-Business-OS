(function () {
  "use strict";
  const query = new URLSearchParams(location.search);
  const run = query.get("r") || "";
  const jobs = (query.get("j") || "").split(",").filter(Boolean);
  const report = {};
  jobs.forEach((job) => { report[job] = { ok: true, r: { skip: "no-rules" } }; });
  parent.postMessage({ type: "bgJobs:done", r: run, report }, location.origin);
})();
