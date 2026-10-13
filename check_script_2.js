
const ROLE = {{ role | tojson }};
const PATIENT_ID = {{ patient_id | tojson }};

// ---- role-based visibility (server still enforces on every endpoint) ----
(function gate() {
  const roles = new Set(ROLE.split(","));
  document.querySelectorAll("[data-roles]").forEach(el => {
    const allowed = el.dataset.roles.split(",").some(r => roles.has(r));
    el.classList.toggle("hidden", !allowed);
  });
  const runBtn = document.getElementById("bench-run");
  if (runBtn && runBtn.dataset.super !== "yes") runBtn.classList.add("hidden");
})();

// ---- tiny API helper ----
async function api(path, opts = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
  let res;
  try {
    res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      ...opts,
    });
  } catch (e) {
    clearTimeout(timer);
    throw new Error("Request failed or timed out - is the app running on port 8000?");
  }
  clearTimeout(timer);
  if (res.status === 401) throw new Error("Please login first. Refresh and login again.");
if (res.status === 403) throw new Error("DENIED");

if (!res.ok) {
  const message = await res.text();
  throw new Error(`API error ${res.status}: ${message}`);
}

return res.json();
}
function callTool(server, tool, params = {}) {
  return api("/mcp/api/call", { method: "POST",
    body: JSON.stringify({ server, tool, params }) });
}
function show(el, kind, text) {
  el.innerHTML = `<div class="mcp-${kind}">${text}</div>`;
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"]/g, function (c) {
    if (c === "&") return "&amp;";
    if (c === "<") return "&lt;";
    if (c === ">") return "&gt;";
    if (c === '"') return "&quot;";
    return c;
  });
}
function badge(status) {
  const cls = status === "ONLINE" || status === "success" || status === "VERIFIED"
    ? "ok" : (status === "OFFLINE" || status === "denied" || status === "error"
    ? "bad" : "warn");
  return `<span class="th-badge ${cls}">${esc(status)}</span>`;
}

// ================= 1. OVERVIEW =================
api("/mcp/api/overview").then(d => {
  document.getElementById("ov-stats").innerHTML = `
    <div class="mcp-stat"><div class="n">${d.users.total}</div><div class="l">Registered users</div></div>
    <div class="mcp-stat"><div class="n">${d.mcp.online}/${d.mcp.total}</div><div class="l">MCP servers online</div></div>
    <div class="mcp-stat"><div class="n">${d.security.denied_last_24h}</div><div class="l">Denied (24h)</div></div>
    <div class="mcp-stat"><div class="n">${d.tasks.open_care_gaps}</div><div class="l">Open care gaps</div></div>
    <div class="mcp-stat"><div class="n">${d.tasks.pending_review_tasks}</div><div class="l">Review tasks</div></div>
    <div class="mcp-stat"><div class="n">${d.tasks.open_conflicts}</div><div class="l">Open conflicts</div></div>`;
  const ev = d.security.recent;
  document.getElementById("ov-security").innerHTML = ev.length
    ? `<table class="mcp-table"><tr><th>When</th><th>Action</th><th>Actor</th><th>Result</th></tr>` +
      ev.map(e => `<tr><td>${esc(e.at)}</td><td>${esc(e.action)}</td><td>${esc(e.actor || "-")}</td><td>${badge(e.result)}</td></tr>`).join("") +
      `</table>`
    : `<div class="mcp-empty">No security events yet.</div>`;
}).catch(e => {
  show(document.getElementById("ov-stats"), "error", esc(e.message));
  show(document.getElementById("ov-security"), "error", esc(e.message));
});

// ================= 2. REGISTRY =================
api("/mcp/api/registry").then(d => {
  const rows = d.servers;
  document.getElementById("reg-body").innerHTML =
    `<table class="mcp-table"><tr><th>Server</th><th>Group</th><th>Category</th><th>Tools</th><th>Roles</th><th>Status</th><th>Last check</th><th>Error</th></tr>` +
    rows.map(s => `<tr><td><b>${esc(s.name)}</b><br><span style="opacity:.6;font-size:11px">${esc(s.service_identity)} :${s.port}</span></td>` +
      `<td>${esc(s.group)}</td><td>${esc(s.category)}</td>` +
      `<td>${(s.tools || []).length} tools</td>` +
      `<td>${esc((s.required_roles || []).join(", "))}</td>` +
      `<td>${badge(s.status)}</td><td>${esc(s.checked_at)}</td><td>${esc(s.last_error || "-")}</td></tr>`).join("") +
    `</table>`;
}).catch(e => show(document.getElementById("reg-body"),
  e.message === "DENIED" ? "denied" : "error",
  e.message === "DENIED" ? "Only admins and the superuser can view the registry." : esc(e.message)));

// ================= 3. AI SAFETY =================
function loadBenchmarks() {
  api("/mcp/api/benchmarks").then(d => {
    const el = document.getElementById("safety-body");
    if (!d.latest) { show(el, "empty", "No benchmark run yet - run the suite."); return; }
    const m = d.latest.metrics || {};
    el.innerHTML = `
      <div class="mcp-stats">
        <div class="mcp-stat"><div class="n">${d.latest.passed}/${d.latest.total}</div><div class="l">Tests passed</div></div>
        <div class="mcp-stat"><div class="n">${m.pass_rate ?? "-"}</div><div class="l">Pass rate</div></div>
        <div class="mcp-stat"><div class="n">${m.grounding_accuracy ?? "-"}</div><div class="l">Grounding accuracy</div></div>
        <div class="mcp-stat"><div class="n">${m.refusal_accuracy ?? "-"}</div><div class="l">Refusal accuracy</div></div>
        <div class="mcp-stat"><div class="n">${m.unsupported_claim_rate ?? "-"}</div><div class="l">Unsupported-claim rate</div></div>
      </div>
      <table class="mcp-table" style="margin-top:12px"><tr><th>Test</th><th>Category</th><th>Result</th></tr>` +
      d.latest.results.map(r => `<tr><td>${esc(r.test_id)}</td><td>${esc(r.category)}</td><td>${badge(r.passed ? "success" : "error")}</td></tr>`).join("") +
      `</table>`;
  }).catch(e => show(document.getElementById("safety-body"), "error", esc(e.message)));
}
document.getElementById("bench-run").addEventListener("click", () => {
  const el = document.getElementById("safety-body");
  show(el, "loading", "Running benchmarks…");
  api("/mcp/api/benchmarks/run", { method: "POST", body: "{}" })
    .then(() => loadBenchmarks())
    .catch(e => show(el, "error", esc(e.message)));
});
loadBenchmarks();

// ================= 4. PATIENT JOURNEY =================
async function loadJourney() {
  const pid = parseInt(document.getElementById("journey-patient").value, 10);
  const el = document.getElementById("journey-body");
  if (!pid) { show(el, "empty", "Enter a patient ID."); return; }
  show(el, "loading", "Loading journey…");
  try {
    const tl = await callTool("health-timeline", "build_health_timeline", { patient_id: pid });
    if (!tl.success) throw new Error(tl.status === "ACCESS_DENIED"
      ? "You are not authorized to view this patient's records." : (tl.error || "Failed"));
    const gaps = await callTool("care-gap-intelligence", "detect_care_gaps", { patient_id: pid });
    el.innerHTML = `
      <h3 style="font-size:13px;margin:4px 0 6px">Timeline (${tl.entries} events)</h3>
      <ul class="mcp-timeline">${tl.timeline.map(e =>
        `<li><b>${esc(e.kind)}</b> — ${esc(e.summary)}<br><span class="ref">${esc(e.ref)} · ${esc(e.at)}</span></li>`).join("")}</ul>
      <h3 style="font-size:13px;margin:14px 0 6px">Missing steps / care gaps (${gaps.gaps_found || 0})</h3>
      ${gaps.success ? `<div class="mcp-pre">${esc(JSON.stringify(gaps.gaps, null, 2))}</div>`
        : `<div class="mcp-empty">No gap data for this scope.</div>`}`;
  } catch (e) {
    show(el, e.message.includes("not authorized") ? "denied" : "error", esc(e.message));
  }
}
document.getElementById("journey-load").addEventListener("click", loadJourney);
document.getElementById("journey-download").addEventListener("click", async () => {
  const pid = parseInt(document.getElementById("journey-patient").value, 10);
  if (!pid) return;
  const r = await callTool("health-timeline", "generate_verified_patient_summary", { patient_id: pid });
  if (!r.success) { alert(r.error || "Failed"); return; }
  const blob = new Blob([r.summary], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `patient-summary-${pid}.txt`;
  a.click();
  URL.revokeObjectURL(a.href);
});

// ================= 5. SIMULATOR =================
document.getElementById("sim-type").addEventListener("change", e => {
  const t = e.target.value;
  document.getElementById("sim-doc-label").classList.toggle("hidden", t !== "doctor_unavailability");
  document.getElementById("sim-doctor").classList.toggle("hidden", t !== "doctor_unavailability");
  document.getElementById("sim-label").textContent =
  t === "reschedule" ? "Shift days" : "Days";
});
document.getElementById("sim-run").addEventListener("click", async () => {
  const el = document.getElementById("sim-body");
  const type = document.getElementById("sim-type").value;
  const params = { days: parseInt(document.getElementById("sim-days").value, 10) || 7 };
  if (type === "reschedule") params.shift_days = params.days;
  if (type === "doctor_unavailability") params.doctor_id = parseInt(document.getElementById("sim-doctor").value, 10) || 1;
  show(el, "loading", "Simulating…");
  try {
    const r = await callTool("workflow-simulator", "simulate_scenario",
      { scenario: { scenario_type: type, params } });
    if (!r.success) throw new Error(r.error || "Failed");
    el.innerHTML = `
      <div class="th-badge warn">SYNTHETIC - not real patient facts</div>
      <div class="mcp-stats" style="margin-top:10px">
        ${Object.entries(r.affected_counts).map(([k, v]) =>
          `<div class="mcp-stat"><div class="n">${v}</div><div class="l">${esc(k)}</div></div>`).join("")}
      </div>
      <h3 style="font-size:13px;margin:12px 0 6px">Assumptions</h3>
      <div class="mcp-pre">${esc(JSON.stringify(r.assumptions, null, 2))}</div>
      <h3 style="font-size:13px;margin:12px 0 6px">Outcomes</h3>
      <div class="mcp-pre">${esc(JSON.stringify(r.outputs, null, 2))}</div>`;
  } catch (e) { show(el, "error", esc(e.message)); }
});

// ================= 6. CLINICAL SAFETY =================
document.getElementById("clin-scan").addEventListener("click", async () => {
  const el = document.getElementById("clin-body");
  const pidRaw = document.getElementById("clin-patient").value;
  const params = pidRaw ? { patient_id: parseInt(pidRaw, 10) } : {};
  show(el, "loading", "Scanning records…");
  try {
    const det = await callTool("clinical-safety", "detect_record_conflicts", params);
    if (!det.success) throw new Error(det.error || "Failed");
    const hist = await callTool("clinical-safety", "get_conflict_resolution_history", {});
    el.innerHTML = `
      <div class="mcp-pre">${esc(JSON.stringify(det.conflicts, null, 2))}</div>
      <h3 style="font-size:13px;margin:12px 0 6px">Conflict register</h3>
      ${hist.success && hist.conflicts.length ? `<table class="mcp-table"><tr><th>Ref</th><th>Type</th><th>Severity</th><th>Status</th><th>Detected</th></tr>` +
        hist.conflicts.map(c => `<tr><td>${esc(c.ref)}</td><td>${esc(c.type)}</td><td>${esc(c.severity)}</td><td>${badge(c.status)}</td><td>${esc(c.detected_at)}</td></tr>`).join("") + `</table>`
        : `<div class="mcp-empty">No conflicts recorded.</div>`}`;
  } catch (e) { show(el, "error", esc(e.message)); }
});

// ================= 7. ACCESS CONTROL =================
api("/mcp/api/roles").then(d => {
  const el = document.getElementById("access-body");
  const perms = d.permissions;
  el.innerHTML = `
    <table class="mcp-table"><tr><th>Permission</th>${d.roles.map(r => `<th>${esc(r)}</th>`).join("")}</tr>` +
    perms.map(p => `<tr><td>${esc(p.key)}<br><span style="opacity:.6;font-size:11px">${esc(p.description)}</span></td>` +
      d.roles.map(r => `<td>${d.matrix[r][p.key] ? "&#10003;" : "&#10007;"}</td>`).join("") +
      `</tr>`).join("") + `</table>
    <h3 style="font-size:13px;margin:14px 0 6px">Runtime overrides (${d.overrides.length})</h3>
    ${d.overrides.length ? `<div class="mcp-pre">${esc(JSON.stringify(d.overrides, null, 2))}</div>`
      : `<div class="mcp-empty">No overrides - defaults apply.</div>`}`;
}).catch(e => show(document.getElementById("access-body"), "error", esc(e.message)));

// ================= 8. AUDIT EXPLORER =================
document.getElementById("aud-load").addEventListener("click", async () => {
  const el = document.getElementById("aud-body");
  const q = new URLSearchParams({
    hours: document.getElementById("aud-hours").value || 24,
    actor: document.getElementById("aud-actor").value,
    server: document.getElementById("aud-server").value,
    tool: document.getElementById("aud-tool").value,
    result: document.getElementById("aud-result").value,
    correlation_id: document.getElementById("aud-corr").value,
  });
  show(el, "loading", "Searching…");
  try {
    const d = await api("/mcp/api/audit?" + q.toString());
    el.innerHTML = d.count
      ? `<table class="mcp-table"><tr><th>When</th><th>Actor</th><th>Role</th><th>Server/Tool</th><th>Action</th><th>Result</th><th>Correlation</th></tr>` +
        d.events.map(e => `<tr><td>${esc(e.at)}</td><td>${esc(e.actor || "-")}</td><td>${esc(e.role || "-")}</td><td>${esc((e.server || "") + "." + (e.tool || ""))}</td><td>${esc(e.action || "-")}</td><td>${badge(e.result)}</td><td style="font-size:11px">${esc(e.correlation_id || "-")}</td></tr>`).join("") + `</table>`
      : `<div class="mcp-empty">No events match these filters.</div>`;
  } catch (e) { show(el, "error", esc(e.message)); }
});

// ================= 9. CHANGE & APPROVAL =================
document.getElementById("chg-type").addEventListener("change", e => {
  const doc = e.target.value === "doctor_deactivation";
  document.getElementById("chg-doc-label").classList.toggle("hidden", !doc);
  document.getElementById("chg-doctor").classList.toggle("hidden", !doc);
});
async function previewChange() {
  const el = document.getElementById("chg-body");
  const type = document.getElementById("chg-type").value;
  const change = { change_type: type };   
    if (type === "doctor_deactivation") change.doctor_id = parseInt(document.getElementById("chg-doctor").value, 10) || 1;
  show(el, "loading", "Previewing…");
  try {
    const r = await api("/mcp/api/change-requests/preview", {
      method: "POST", body: JSON.stringify({ change }) });
    if (!r.success) throw new Error(r.error || "Failed");
    el.innerHTML = `<div class="mcp-pre">${esc(JSON.stringify(r.impact, null, 2))}</div>
      <div class="mcp-empty" style="margin-top:6px">Preview only - nothing was changed.</div>`;
  } catch (e) { show(el, "error", esc(e.message)); }
}
document.getElementById("chg-preview").addEventListener("click", previewChange);
document.getElementById("chg-request").addEventListener("click", async () => {
  const el = document.getElementById("chg-body");
  const type = document.getElementById("chg-type").value;
  const change = { change_type: type, description: "Requested from the intelligence console" };
  if (type === "doctor_deactivation") change.doctor_id = parseInt(document.getElementById("chg-doctor").value, 10) || 1;
  try {
    const r = await callTool("change-approval", "request_approval", { change });
    if (!r.success) throw new Error(r.error || "Failed");
    el.innerHTML = `<div class="th-badge ok">Change request #${r.change_request_id} created - ${esc(r.status)}</div>`;
    loadChangeRequests();
  } catch (e) { show(el, "error", esc(e.message)); }
});
function loadChangeRequests() {
  api("/mcp/api/change-requests").then(d => {
    const el = document.getElementById("chg-list");
    el.innerHTML = d.change_requests.length
      ? `<table class="mcp-table"><tr><th>ID</th><th>Type</th><th>Status</th><th>Proposed by</th><th>Created</th></tr>` +
        d.change_requests.map(c => `<tr><td>#${c.id}</td><td>${esc(c.change_type)}</td><td>${badge(c.status)}</td><td>${esc(c.proposed_by || "-")}</td><td>${esc(c.created_at)}</td></tr>`).join("") + `</table>`
      : `<div class="mcp-empty">No change requests yet.</div>`;
  }).catch(() => {});
}
loadChangeRequests();

// ================= 10. FLIGHT RECORDER & RECOVERY =================
async function loadRecoveryList() {
  try {
    const d = await api("/mcp/api/recovery");
    const el = document.getElementById("rec-list");
    el.innerHTML = `
      <h3 style="font-size:13px;margin:0 0 6px">Recovery attempts (${d.attempts.length})</h3>
      ${d.attempts.length ? `<table class="mcp-table"><tr><th>ID</th><th>Type</th><th>Status</th><th>Attempts</th><th>Correlation</th></tr>` +
        d.attempts.map(a => `<tr><td>#${a.id}</td><td>${esc(a.incident_type)}</td><td>${badge(a.status)}</td><td>${a.attempts}</td><td style="font-size:11px">${esc(a.correlation_id || "-")}</td></tr>`).join("") + `</table>`
        : `<div class="mcp-empty">No recovery attempts recorded.</div>`}
      <h3 style="font-size:13px;margin:14px 0 6px">Recent workflow events (${d.recent_events.length})</h3>
      ${d.recent_events.length ? `<table class="mcp-table"><tr><th>When</th><th>Workflow</th><th>Type</th><th>Resource</th><th>Correlation</th></tr>` +       
        
        d.recent_events.map(e => `<tr><td>${esc(e.at)}</td><td>${esc(e.workflow)}</td><td>${esc(e.type)}</td><td>${esc(e.resource || "-")}</td><td style="font-size:11px">${esc(e.correlation_id)}</td></tr>`).join("") + `</table>`
        : `<div class="mcp-empty">No workflow events recorded.</div>`}`;
  } catch (e) { /* list is best-effort */ }
}
async function reconstruct() {
  const corr = document.getElementById("rec-corr").value.trim();
  const el = document.getElementById("rec-body");
  if (!corr) { show(el, "empty", "Enter a correlation ID."); return; }
  show(el, "loading", "Reconstructing…");
  try {
    const r = await callTool("flight-recorder", "reconstruct_event_history",
      { correlation_id: corr });
    if (!r.success) throw new Error(r.error || "Failed");
    el.innerHTML = r.found
      ? `<ul class="mcp-timeline">${r.events.map(e =>
          `<li><b>${esc(e.type)}</b> [${esc(e.workflow)}] ${esc(e.resource || "")}<br><span class="ref">${esc(e.ref)} · ${esc(e.at)}</span></li>`).join("")}</ul>`
      : `<div class="mcp-empty">No events for this correlation ID.</div>`;
  } catch (e) { show(el, "error", esc(e.message)); }
}
async function reconcile() {
  const corr = document.getElementById("rec-corr").value.trim();
  const el = document.getElementById("rec-body");
  if (!corr) { show(el, "empty", "Enter a correlation ID."); return; }
  show(el, "loading", "Reconciling (idempotent)…");
  try {
    const r = await callTool("flight-recorder", "reconcile_failed_workflow",
      { correlation_id: corr });
    if (!r.success) throw new Error(r.error || "Failed");
    el.innerHTML = `<div class="mcp-pre">${esc(JSON.stringify(r.recovered, null, 2))}</div>`;
    loadRecoveryList();
  } catch (e) { show(el, "error", esc(e.message)); }
}
document.getElementById("rec-timeline").addEventListener("click", reconstruct);
document.getElementById("rec-reconcile").addEventListener("click", reconcile);
loadRecoveryList();
