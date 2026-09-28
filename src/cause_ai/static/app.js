"use strict";

const state = { user: null, dashboard: null, currentView: "dashboard", selectedCase: null };
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const human = value => String(value ?? "").replaceAll("_", " ").toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
const currency = (amount, unit = "INR") => new Intl.NumberFormat("en-IN", { style: "currency", currency: unit, maximumFractionDigits: 2 }).format(Number(amount || 0));
const initials = name => String(name || "U").split(/[ _-]+/).map(p => p[0]).join("").slice(0, 2).toUpperCase();
const canAnalyst = () => ["analyst", "admin"].includes(state.user?.role);
const canDepartment = () => ["department", "admin"].includes(state.user?.role);

async function api(path, options = {}) {
  const response = await fetch(path, { credentials: "same-origin", ...options, headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data?.error?.message || `Request failed (${response.status})`);
  return data;
}

function toast(message, error = false) {
  const node = document.createElement("div");
  node.className = `toast${error ? " error" : ""}`;
  node.textContent = message;
  $("#toast-region").append(node);
  window.setTimeout(() => node.remove(), 3800);
}

function showLogin(message = "") {
  state.user = null;
  $("#app-view").hidden = true;
  $("#login-view").hidden = false;
  $("#login-error").textContent = message;
}

function showApp(user) {
  state.user = user;
  $("#login-view").hidden = true;
  $("#app-view").hidden = false;
  $("#user-name").textContent = human(user.username);
  $("#user-role").textContent = human(user.role);
  $("#user-avatar").textContent = initials(user.username);
  $("#regulatory-nav").hidden = user.role !== "admin";
  loadDashboard().then(() => navigate(location.hash.slice(1) || "dashboard")).catch(err => toast(err.message, true));
}

async function loadDashboard() {
  state.dashboard = await api("/api/dashboard");
  $("#nav-case-count").textContent = state.dashboard.open_cases;
}

function pageHeading(title, description, actions = "") {
  const today = new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "2-digit", month: "long", year: "numeric" }).format(new Date()).toUpperCase();
  return `<div class="page-heading"><div><p class="eyebrow">${escapeHtml(state.currentView === "dashboard" ? `${today} · SYNTHETIC DATA` : "CAUSE AI WORKSPACE")}</p><h1>${escapeHtml(title)}</h1><p>${escapeHtml(description)}</p></div><div class="heading-actions">${actions}</div></div>`;
}

function badge(value, kind = value) {
  return `<span class="badge ${escapeHtml(String(kind).toLowerCase())}">${escapeHtml(human(value))}</span>`;
}

function caseIdentity(c) {
  const type = c.subject_type === "USER" ? "User ID" : c.subject_type === "COMPANY" ? "Company ID" : "User/Company ID";
  return `<span class="case-identity"><span>${escapeHtml(type)}: ${escapeHtml(c.subject_id || "Not provided")}</span><span>Email ID: ${escapeHtml(c.email_id || "Not provided")}</span>${c.identity_status === "UNVERIFIED" ? "<span class=\"identity-warning\">Identity supplied by source · unverified</span>" : ""}</span>`;
}

function caseRows(cases) {
  if (!cases.length) return `<tr><td colspan="7"><div class="empty-state"><div class="empty-icon">⌕</div>No cases match these filters.</div></td></tr>`;
  return cases.map(c => `<tr>
    <td><button class="case-id" data-case="${escapeHtml(c.id)}">${escapeHtml(c.id)}</button>${caseIdentity(c)}</td>
    <td><span class="case-title">${escapeHtml(c.title)}</span><span class="case-sub">${escapeHtml(c.payment_id)} · ${escapeHtml(human(c.type))}</span></td>
    <td class="money">${escapeHtml(currency(c.amount, c.currency))}</td>
    <td>${badge(c.risk.level)}</td><td>${badge(c.evidence_status, c.evidence_status === "VERIFIED" ? "verified" : c.evidence_status === "CONFLICTING" ? "conflicting" : "medium")}</td>
    <td>${badge(c.status)}</td><td>${escapeHtml(c.department)}</td></tr>`).join("");
}

function casesTable(cases, withFilters = false) {
  const filter = withFilters ? `<div class="filter-row"><input id="case-search" class="search-input" type="search" placeholder="Search ID, user, email, payment…" aria-label="Search cases"><select id="case-status" class="filter-select" aria-label="Filter status"><option value="">All statuses</option>${["DETECTED", "INVESTIGATING", "DECISION_READY", "ESCALATED", "RESOLVED", "VERIFIED"].map(s => `<option>${s}</option>`).join("")}</select><select id="case-risk" class="filter-select" aria-label="Filter risk"><option value="">All risk</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select><select id="case-type" class="filter-select" aria-label="Filter issue"><option value="">All issue types</option>${[...new Set(cases.map(c => c.type))].map(t => `<option value="${escapeHtml(t)}">${escapeHtml(human(t))}</option>`).join("")}</select><span id="filter-count" class="muted">${cases.length} cases</span></div>` : "";
  return `<section class="content-card">${filter}<div class="table-wrap"><table><thead><tr><th>Case ID · User/Company · Email</th><th>Exception</th><th>Amount</th><th>Risk</th><th>Evidence</th><th>Status</th><th>Assigned queue</th></tr></thead><tbody id="case-table-body">${caseRows(cases)}</tbody></table></div></section>`;
}

function attachCaseOpeners(root = document) {
  $$('[data-case]', root).forEach(button => button.addEventListener("click", () => openCase(button.dataset.case)));
}

function renderDashboard() {
  const d = state.dashboard;
  const recent = [...d.cases].sort((a, b) => ({ HIGH: 0, MEDIUM: 1, LOW: 2 }[a.risk.level] - { HIGH: 0, MEDIUM: 1, LOW: 2 }[b.risk.level])).slice(0, 5);
  const tickets = d.tickets.filter(t => t.status !== "CLOSED").slice(0, 3);
  $("#page-content").innerHTML = `${pageHeading("Command center", "A clear view of financial exceptions, exposure and work in progress.", '<button class="button" data-navigate="cases">View exception queue <span aria-hidden="true">→</span></button>')}
    <div class="metrics">
      <article class="metric-card"><div class="metric-top">Total exceptions <span class="metric-icon">◎</span></div><div class="metric-value">${d.total_cases}</div><div class="metric-foot">Across synthetic finance records</div></article>
      <article class="metric-card"><div class="metric-top">Open cases <span class="metric-icon metric-open">◷</span></div><div class="metric-value">${d.open_cases}</div><div class="metric-foot">Need attention or verification</div></article>
      <article class="metric-card"><div class="metric-top">High risk <span class="metric-icon metric-high">△</span></div><div class="metric-value">${d.high_risk}</div><div class="metric-foot">Evidence-linked risk factors</div></article>
      <article class="metric-card"><div class="metric-top">Active tickets <span class="metric-icon metric-ticket">▤</span></div><div class="metric-value">${d.open_tickets}</div><div class="metric-foot">In configured department queues</div></article>
    </div>
    <div class="content-card priority-card"><div class="card-header"><div><h2>Priority exceptions</h2><p>Cases ordered by explainable risk level</p></div><button class="text-link" data-navigate="cases">View all cases →</button></div><div class="table-wrap"><table><thead><tr><th>Case ID · User/Company · Email</th><th>Exception</th><th>Amount</th><th>Risk</th><th>Evidence</th><th>Status</th><th>Assigned queue</th></tr></thead><tbody>${caseRows(recent)}</tbody></table></div></div>
    <div class="content-card"><div class="card-header"><div><h2>Department work</h2><p>Active tickets with a clear owner and next step</p></div><button class="text-link" data-navigate="tickets">Open ticket board →</button></div>${tickets.length ? `<div class="table-wrap"><table><thead><tr><th>Ticket</th><th>Case</th><th>Department</th><th>Priority</th><th>Status</th><th>Next step</th></tr></thead><tbody>${tickets.map(t => `<tr><td class="case-id">${escapeHtml(t.id)}</td><td><button class="case-id" data-case="${escapeHtml(t.case_id)}">${escapeHtml(t.case_id)}</button></td><td>${escapeHtml(t.department)}</td><td>${badge(t.priority)}</td><td>${badge(t.status)}</td><td><button class="text-link" data-case="${escapeHtml(t.case_id)}">Review case →</button></td></tr>`).join("")}</tbody></table></div>` : `<div class="empty-state">No active department tickets.</div>`}</div>`;
  attachCaseOpeners();
}

function renderCases() {
  $("#page-content").innerHTML = `${pageHeading("Exception queue", "Search, filter and open evidence-backed financial cases.", '<span class="demo-pill"><i></i> 8 SYNTHETIC CASES</span>')}${casesTable(state.dashboard.cases, true)}`;
  const update = () => {
    const query = $("#case-search").value.toLocaleLowerCase();
    const status = $("#case-status").value;
    const risk = $("#case-risk").value;
    const type = $("#case-type").value;
    const filtered = state.dashboard.cases.filter(c => (!query || `${c.id} ${c.title} ${c.payment_id} ${c.type} ${c.summary}`.toLocaleLowerCase().includes(query)) && (!status || c.status === status) && (!risk || c.risk.level === risk) && (!type || c.type === type));
    $("#case-table-body").innerHTML = caseRows(filtered);
    $("#filter-count").textContent = `${filtered.length} case${filtered.length === 1 ? "" : "s"}`;
    attachCaseOpeners();
  };
  ["#case-search", "#case-status", "#case-risk", "#case-type"].forEach(sel => $(sel).addEventListener("input", update));
  attachCaseOpeners();
}

function renderEvidence(evidence) {
  if (!evidence.length) return `<div class="empty-state">No linked evidence is available.</div>`;
  return `<div class="evidence-list">${evidence.map(item => `<div class="evidence-item"><span class="evidence-dot ${item.status === "CONFLICTING" ? "conflicting" : ""}">${item.status === "CONFLICTING" ? "!" : "✓"}</span><div class="evidence-copy"><strong>${escapeHtml(item.fact)}</strong><p>Verification: ${badge(item.status, item.status === "VERIFIED" ? "verified" : "conflicting")}</p><div class="source-line"><span>${escapeHtml(human(item.source_type))}</span><span class="source-id">${escapeHtml(item.source_id)}</span><span>${escapeHtml(human(item.authority))}</span><span>${escapeHtml(item.timestamp)}</span></div></div></div>`).join("")}</div>`;
}

function renderAudit(events) {
  if (!events?.length) return `<div class="empty-state">No audit events have been recorded for this item yet.</div>`;
  return `<div class="audit-list">${events.slice().reverse().map(e => `<div class="audit-row"><div class="audit-time">${escapeHtml(new Date(e.created_at).toLocaleString())}</div><div><div class="audit-action">${escapeHtml(human(e.action))}</div><div class="audit-detail">${escapeHtml(e.reason)}${e.details?.outcome ? ` · ${escapeHtml(human(e.details.outcome))}` : ""}</div></div><div class="audit-actor">${escapeHtml(human(e.actor))} · ${escapeHtml(human(e.role))}</div></div>`).join("")}</div>`;
}

async function openCase(caseId) {
  state.selectedCase = caseId;
  state.currentView = "case";
  $("#page-crumb").textContent = caseId;
  $("#page-content").innerHTML = '<div class="loading">Loading evidence and case history…</div>';
  try {
    const c = await api(`/api/cases/${encodeURIComponent(caseId)}`);
    renderCase(c);
  } catch (err) { toast(err.message, true); navigate("cases"); }
}

function renderCase(c) {
  const decision = c.decision;
  const ticket = c.tickets?.find(t => t.status !== "CLOSED") || c.tickets?.at(-1);
  const factors = c.risk.factors.length ? c.risk.factors.map(f => `<div class="factor"><i>◆</i><span>${escapeHtml(f.explanation)}${f.evidence_id ? ` · <span class="source-id">${escapeHtml(f.evidence_id)}</span>` : ""}</span></div>`).join("") : `<div class="factor"><i>◆</i><span>No elevated configured risk factors were detected.</span></div>`;
  const policy = c.policy;
  const repeatHistory = c.subject_history?.length ? `<section class="section-card"><div class="section-title"><h3>Previous reports for this subject</h3><span>${Number(c.report_count)} total reports</span></div><div class="section-body"><p class="case-summary">A repeat request was matched using the supplied subject ID, payment ID, and exception type. Identity data has not been independently verified.</p><div class="repeat-history">${c.subject_history.map(item => `<div class="repeat-history-row"><button class="case-id" data-case="${escapeHtml(item.id)}">${escapeHtml(item.id)}</button><span>${escapeHtml(human(item.status))}</span><span>${escapeHtml(human(item.outcome || "No decision"))}</span><small>${escapeHtml(item.updated_at)}</small></div>`).join("")}</div></div></section>` : "";
  $("#page-content").innerHTML = `${pageHeading("Case investigation", c.summary, `<button class="button" data-navigate="cases">← Back to queue</button>`)}
    <div class="detail-title case-detail-title"><button class="back-button" data-navigate="cases" aria-label="Back to cases">←</button><h1>${escapeHtml(c.title)}</h1>${badge(c.status)}<span class="case-id">${escapeHtml(c.id)}</span>${caseIdentity(c)}</div>
    <div class="detail-layout"><div class="detail-main">
      <section class="section-card"><div class="section-title"><h3>Case summary</h3><span>${escapeHtml(c.payment_id)}</span></div><div class="section-body"><p class="case-summary">${escapeHtml(c.summary)}</p><div class="meta-grid summary-meta"><div class="meta-cell"><small>FINANCIAL EXPOSURE</small><strong>${escapeHtml(currency(c.amount, c.currency))}</strong></div><div class="meta-cell"><small>EXCEPTION TYPE</small><strong>${escapeHtml(human(c.type))}</strong></div><div class="meta-cell"><small>REPORT COUNT</small><strong>${Number(c.report_count)}</strong></div><div class="meta-cell"><small>ROUTING QUEUE</small><strong>${escapeHtml(c.department)}</strong></div></div></div></section>
      ${repeatHistory}
      <section class="section-card"><div class="section-title"><h3>Evidence package</h3><span>${c.evidence.length} source${c.evidence.length === 1 ? "" : "s"}</span></div><div class="section-body">${renderEvidence(c.evidence)}</div></section>
      <section class="section-card"><div class="section-title"><h3>Transaction timeline</h3><span>Source-linked activity</span></div><div class="section-body"><div class="timeline">${c.timeline.map(item => `<div class="timeline-item"><span class="timeline-dot"></span><div class="timeline-copy"><strong>${escapeHtml(item.event)}</strong><small>${escapeHtml(item.time)} · ${escapeHtml(item.source)}</small></div></div>`).join("")}</div></div></section>
      <section class="section-card"><div class="section-title"><h3>Case audit trail</h3><span>Append-only record</span></div>${renderAudit(c.audit)}</section>
    </div><div class="detail-side">
      <section class="section-card"><div class="section-title"><h3>Explainable risk</h3>${badge(c.risk.level)}</div><div class="section-body"><div class="risk-score"><div class="score-ring"><strong>${c.risk.score}</strong></div><div class="risk-meta"><strong>${escapeHtml(c.risk.level)} risk</strong><small>Configured demo score · 0–100</small></div></div><div class="risk-bar"><progress max="100" value="${c.risk.score}" aria-label="Risk score ${c.risk.score} out of 100"></progress></div><div class="factor-list">${factors}</div></div></section>
      <section class="section-card"><div class="section-title"><h3>Rule evaluation</h3>${badge(policy.status, policy.status === "PASS" ? "verified" : policy.status === "FAIL" ? "rejected" : "medium")}</div><div class="section-body"><div class="decision-box"><strong>${escapeHtml(policy.id)} · v${escapeHtml(policy.version)}</strong><p>${escapeHtml(policy.description)}</p><div class="policy-source">Source: ${escapeHtml(policy.source)}<br>Effective: ${escapeHtml(policy.effective_from)}</div></div></div></section>
      <section class="section-card"><div class="section-title"><h3>Decision</h3><span>Automatic deterministic evaluation</span></div><div class="section-body">${decision ? `<div class="decision-box">${badge(decision.outcome)}<p>${escapeHtml(decision.reason)}</p>${decision.blockers?.length ? `<div class="blocker">Blockers: ${escapeHtml(decision.blockers.map(human).join(", "))}</div>` : ""}<div class="policy-source">The decision was recorded automatically at detection. This demo does not execute payment actions.</div></div>` : `<div class="decision-box"><strong>Historical case without a decision</strong><p>New cases are evaluated automatically at detection. This seeded historical case has no recorded decision.</p></div>`}</div></section>
      ${ticket ? renderTicketPanel(ticket, c) : ""}
    </div></div>`;
  $$('[data-navigate]').forEach(button => button.addEventListener("click", () => navigate(button.dataset.navigate)));
  attachCaseOpeners($("#page-content"));
  attachTicketActions(c, ticket);
}

function renderTicketPanel(ticket, c) {
  const responseForm = canDepartment() && !["RESOLVED", "VERIFIED", "CLOSED"].includes(ticket.status) ? `<form id="response-form" class="ticket-actions"><div class="form-group"><label class="field-label" for="ticket-comment">Department finding</label><textarea id="ticket-comment" class="field-textarea" minlength="5" maxlength="2000" placeholder="Record the finding and next action" required></textarea></div><button class="button secondary" type="submit">Submit department finding</button></form>` : "";
  const resolutionForm = canDepartment() && !["RESOLVED", "VERIFIED", "CLOSED"].includes(ticket.status) ? `<form id="resolution-form" class="ticket-actions resolution-actions"><div class="form-group"><label class="field-label" for="resolution-text">Proposed resolution</label><textarea id="resolution-text" class="field-textarea" minlength="15" maxlength="2000" placeholder="Explain how this case was resolved" required></textarea></div><label class="field-label">Cite verified evidence</label>${c.evidence.filter(e => e.status === "VERIFIED").map(e => `<label class="evidence-check"><input type="checkbox" name="resolution-evidence" value="${escapeHtml(e.id)}"><span>${escapeHtml(e.fact)} <span class="source-id">${escapeHtml(e.id)}</span></span></label>`).join("")}<button class="button primary" type="submit">Submit resolution</button></form>` : "";
  const verify = canAnalyst() && ticket.status === "RESOLVED" ? `<button id="verify-button" class="button primary">Verify resolution</button>` : "";
  return `<section class="section-card"><div class="section-title"><h3>Department ticket</h3>${badge(ticket.status)}</div><div class="section-body"><div class="meta-grid"><div class="meta-cell"><small>TICKET ID</small><strong>${escapeHtml(ticket.id)}</strong></div><div class="meta-cell"><small>PRIORITY</small><strong>${escapeHtml(ticket.priority)}</strong></div><div class="meta-cell"><small>QUEUE</small><strong>${escapeHtml(ticket.department)}</strong></div><div class="meta-cell"><small>SLA DUE</small><strong>${escapeHtml(ticket.sla_due || "Not configured")}</strong></div></div><p class="case-summary ticket-summary">${escapeHtml(ticket.summary)}</p>${ticket.comments?.length ? `<div class="decision-box ticket-note"><strong>Department findings</strong>${ticket.comments.map(item => `<p>${escapeHtml(item.text)}<br><small>${escapeHtml(human(item.actor))} · ${escapeHtml(item.created_at)}</small></p>`).join("")}</div>` : ""}${ticket.resolution ? `<div class="decision-box ticket-note"><strong>Submitted resolution</strong><p>${escapeHtml(ticket.resolution.text)}</p><small>Evidence: ${ticket.resolution.evidence_ids.map(escapeHtml).join(", ")} · ${escapeHtml(ticket.resolution.actor)}</small></div>` : ""}${responseForm}${resolutionForm}${verify}${ticket.verification ? `<div class="decision-box verification-note"><strong>Independent verification</strong><p>${badge(ticket.verification.status, ticket.verification.status === "PASSED" ? "verified" : "rejected")} · ${escapeHtml(ticket.verification.method)}</p></div>` : ""}</div></section>`;
}

function attachTicketActions(c, ticket) {
  $("#response-form")?.addEventListener("submit", async event => {
    event.preventDefault();
    try { await api(`/api/tickets/${encodeURIComponent(ticket.id)}/respond`, { method: "POST", body: JSON.stringify({ comment: $("#ticket-comment").value }) }); toast("Department finding recorded."); await loadDashboard(); openCase(c.id); }
    catch (err) { toast(err.message, true); }
  });
  $("#resolution-form")?.addEventListener("submit", async event => {
    event.preventDefault();
    const evidence_ids = $$('input[name="resolution-evidence"]:checked').map(input => input.value);
    try { await api(`/api/tickets/${encodeURIComponent(ticket.id)}/resolve`, { method: "POST", body: JSON.stringify({ resolution: $("#resolution-text").value, evidence_ids }) }); toast("Resolution submitted for independent verification."); await loadDashboard(); openCase(c.id); }
    catch (err) { toast(err.message, true); }
  });
  $("#verify-button")?.addEventListener("click", async () => {
    try { const result = await api(`/api/tickets/${encodeURIComponent(ticket.id)}/verify`, { method: "POST", body: "{}" }); toast(`Verification ${result.verification.status.toLowerCase()}.`); await loadDashboard(); openCase(c.id); }
    catch (err) { toast(err.message, true); }
  });
}

function renderTickets() {
  const tickets = state.dashboard.tickets;
  const items = tickets.map(t => `<tr><td class="case-id">${escapeHtml(t.id)}</td><td><button class="case-id" data-case="${escapeHtml(t.case_id)}">${escapeHtml(t.case_id)}</button></td><td>${escapeHtml(t.department)}</td><td>${badge(t.priority)}</td><td>${badge(t.status)}</td><td>${escapeHtml(t.sla_due || "Not configured")}</td><td><button class="text-link" data-case="${escapeHtml(t.case_id)}">Open workspace →</button></td></tr>`).join("");
  const actions = canAnalyst() ? '<button id="run-reminders" class="button">Check overdue reminders</button>' : '<span class="demo-pill"><i></i> CONFIGURABLE DEMO QUEUES</span>';
  $("#page-content").innerHTML = `${pageHeading("Department tickets", "Review assigned cases, record findings and submit evidence-backed resolutions.", actions)}<section class="content-card"><div class="card-header"><div><h2>Active and recent tickets</h2><p>Current queue ownership and case status</p></div></div><div class="table-wrap"><table><thead><tr><th>Ticket ID</th><th>Case</th><th>Department queue</th><th>Priority</th><th>Status</th><th>SLA due</th><th>Workspace</th></tr></thead><tbody>${items || '<tr><td colspan="7"><div class="empty-state">No tickets are currently available.</div></td></tr>'}</tbody></table></div></section>`;
  attachCaseOpeners();
  $("#run-reminders")?.addEventListener("click", async () => {
    try { const result = await api("/api/reminders/run", { method: "POST", body: "{}" }); toast(`${result.count} overdue reminder${result.count === 1 ? "" : "s"} recorded.`); await loadDashboard(); renderTickets(); }
    catch (err) { toast(err.message, true); }
  });
}

async function renderAuditPage() {
  $("#page-content").innerHTML = `${pageHeading("Audit history", "Searchable, actor-attributed history of decisions and case actions.")}<section class="content-card"><div class="card-header"><div><h2>Recent events</h2><p>Events are append-only in this demo workspace</p></div><select id="audit-limit" class="filter-select" aria-label="Number of audit events"><option value="50">Latest 50</option><option value="100" selected>Latest 100</option><option value="250">Latest 250</option></select></div><div id="audit-content" class="loading">Loading audit records…</div></section>`;
  const load = async () => {
    try {
      const data = await api(`/api/audit?limit=${$("#audit-limit").value}`);
      $("#audit-content").innerHTML = renderAudit(data.items);
      $$("#audit-content [data-case]").forEach(button => button.addEventListener("click", () => openCase(button.dataset.case)));
    } catch (err) { $("#audit-content").innerHTML = `<div class="empty-state">${escapeHtml(err.message)}</div>`; }
  };
  $("#audit-limit").addEventListener("change", load);
  await load();
}

async function renderRegulatory() {
  const root = $("#page-content");
  root.innerHTML = `${pageHeading("Regulatory update inbox", "Official-source publications are captured for human applicability review. This inbox cannot activate a financial policy.", '<button id="regulatory-scan" class="button primary">Check sources now</button>')}<div id="regulatory-content" class="loading">Loading source status and review queue…</div>`;
  const load = async () => {
    const data = await api("/api/regulatory/inbox");
    const sources = data.sources.map(source => `<article class="section-card"><div class="section-body"><strong>${escapeHtml(source.name)}</strong><p class="case-summary"><a href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer">Open official source ↗</a></p><small>${escapeHtml(source.status || "Never checked")} · Last checked: ${escapeHtml(source.checked_at || "Never")}${source.last_error ? ` · ${escapeHtml(source.last_error)}` : ""}</small></div></article>`).join("");
    const docs = data.documents.map(doc => {
      const reviewForm = doc.review_status === "REVIEW_REQUIRED"
        ? `<form class="reg-review" data-document="${escapeHtml(doc.id)}"><select name="verdict" class="filter-select" aria-label="Review outcome"><option value="NEEDS_LEGAL_REVIEW">Needs legal review</option><option value="RELEVANT">Relevant</option><option value="NOT_APPLICABLE">Not applicable</option></select><textarea name="reason" class="field-textarea" minlength="15" maxlength="2000" placeholder="Record applicability rationale (15–2,000 characters)" required></textarea><button class="button secondary" type="submit">Record review</button></form>`
        : `<p class="case-summary">${escapeHtml(doc.review_status)} by ${escapeHtml(doc.review_actor)}: ${escapeHtml(doc.review_reason)}</p>`;
      return `<article class="section-card regulatory-doc"><div class="section-body"><div class="section-title"><h3>${escapeHtml(doc.title)}</h3>${badge(doc.review_status, doc.review_status === "REVIEW_REQUIRED" ? "medium" : "verified")}</div><p class="case-summary">Source: ${escapeHtml(doc.source_id)} · Captured ${escapeHtml(doc.discovered_at)} · SHA-256 <code>${escapeHtml(doc.content_sha256)}</code>. The server verifies the stored bytes against this hash before recording a review.</p><a href="${escapeHtml(doc.url)}" target="_blank" rel="noopener noreferrer">View official publication ↗</a>${reviewForm}</div></article>`;
    }).join("");
    $("#regulatory-content").innerHTML = `<section class="content-card"><div class="card-header"><div><h2>Monitored official sources</h2><p>Allowlisted NPCI and RBI publication indexes</p></div><span class="badge medium">${data.pending_count} awaiting review</span></div><div class="reg-sources">${sources}</div></section><section class="content-card"><div class="card-header"><div><h2>Captured publications</h2><p>Content-addressed original copies; no automatic interpretation or policy activation</p></div></div>${docs ? `<div class="reg-docs">${docs}</div>` : '<div class="empty-state">No publications have been captured yet. Run a source check or wait for the background monitor.</div>'}</section>`;
    $$(".reg-review").forEach(form => form.addEventListener("submit", async event => {
      event.preventDefault();
      const button = $("button[type=submit]", form); button.disabled = true;
      try {
        const result = await api(`/api/regulatory/documents/${encodeURIComponent(form.dataset.document)}/review`, { method: "POST", body: JSON.stringify({ verdict: form.verdict.value, reason: form.reason.value }) });
        if (result.document.policy_activated) throw new Error("Unexpected policy activation response");
        toast("Review recorded. No policy was activated."); await load();
      } catch (err) { toast(err.message, true); button.disabled = false; }
    }));
  };
  try { await load(); } catch (err) { $("#regulatory-content").innerHTML = `<div class="empty-state">${escapeHtml(err.message)}</div>`; }
  $("#regulatory-scan").addEventListener("click", async event => {
    const button = event.currentTarget; button.disabled = true; button.textContent = "Checking official sources…";
    try { const result = await api("/api/regulatory/scan", { method: "POST", body: "{}" }); toast(`Source check complete. ${result.discovered} new publication${result.discovered === 1 ? "" : "s"} captured.`); await load(); }
    catch (err) { toast(err.message, true); }
    finally { button.disabled = false; button.textContent = "Check sources now"; }
  });
}

function renderScan() {
  const example = [
    { record_type: "payment", record_id: "PAY-DEMO-501", payment_id: "PAY-DEMO-501", currency: "INR", amount: "10000.00", status: "CAPTURED", occurred_at: "2026-09-20", subject_type: "COMPANY", subject_id: "SYN-COMPANY-501", email_id: "company501@example.invalid" },
    { record_type: "fee", record_id: "FEE-DEMO-501", payment_id: "PAY-DEMO-501", currency: "INR", amount: "250.00", subject_type: "COMPANY", subject_id: "SYN-COMPANY-501", email_id: "company501@example.invalid" },
    { record_type: "settlement", record_id: "SET-DEMO-501", payment_id: "PAY-DEMO-501", currency: "INR", amount: "9500.00", occurred_at: "2026-09-21", subject_type: "COMPANY", subject_id: "SYN-COMPANY-501", email_id: "company501@example.invalid" }
  ];
  $("#page-content").innerHTML = `${pageHeading("Detection lab", "Preview exception detection and automatic governed routing from normalized source records.", '<span class="demo-pill"><i></i> SYNTHETIC INPUT · AUTOMATED DECISION</span>')}
    ${canAnalyst() ? `<section class="content-card"><div class="card-header"><div><h2>Source records</h2><p>Provide 1–5,000 records as a JSON array. Optional subject ID and email fields enable repeat-report correlation; supplied identities remain unverified.</p></div></div><div class="section-body"><div class="sample-actions"><button id="load-demo-sample" class="button small" type="button">Load built-in sample</button><button id="load-razorpay-public-sample" class="button small" type="button">Load Razorpay public-schema sample</button><span class="muted">Public schema sample uses fictional records only.</span></div><form id="detection-form"><label class="field-label" for="detection-records">Normalized financial records</label><textarea id="detection-records" class="field-textarea code-textarea" rows="12" spellcheck="false" required>${escapeHtml(JSON.stringify(example, null, 2))}</textarea><div class="detection-controls"><label class="field-label" for="timing-window">Settlement timing window</label><input id="timing-window" class="field-input timing-input" type="number" min="0" max="365" value="7"><span class="muted">days</span><button class="button primary" type="submit">Analyze records</button></div></form></div></section><section id="detection-results" class="detection-results" aria-live="polite"></section>` : `<section class="content-card"><div class="empty-state">Detection preview is available to analyst and admin demo roles.</div></section>`}`;
  $("#load-demo-sample")?.addEventListener("click", () => { $("#detection-records").value = JSON.stringify(example, null, 2); toast("Built-in synthetic sample loaded."); });
  $("#load-razorpay-public-sample")?.addEventListener("click", async () => {
    try {
      const response = await fetch("/samples/razorpay_public_schema_sample.json", { credentials: "same-origin" });
      if (!response.ok) throw new Error("The Razorpay public-schema sample is unavailable.");
      $("#detection-records").value = JSON.stringify(await response.json(), null, 2);
      toast("Razorpay public-schema sample loaded. It contains fictional records only.");
    } catch (err) { toast(err.message, true); }
  });
  $("#detection-form")?.addEventListener("submit", async event => {
    event.preventDefault();
    const output = $("#detection-results");
    let records;
    try { records = JSON.parse($("#detection-records").value); }
    catch { toast("Source records must be valid JSON.", true); return; }
    const button = $("#detection-form button[type=submit]");
    button.disabled = true;
    button.textContent = "Analyzing…";
    output.innerHTML = '<section class="content-card"><div class="loading">Checking record integrity and financial relationships…</div></section>';
    try {
      const result = await api("/api/detection/preview", { method: "POST", body: JSON.stringify({ schema_version: "1.1", records, timing_window_days: Number($("#timing-window").value) }) });
      output.innerHTML = `<section class="content-card"><div class="card-header"><div><h2>${result.count} finding${result.count === 1 ? "" : "s"} detected</h2><p>Findings receive an automatic deterministic decision. Unverified, conflicting, repeat, or suspicious reports are routed for human investigation.</p></div><span class="demo-pill"><i></i> PREVIEW</span></div>${result.findings.length ? `<div class="detection-list">${result.findings.map(item => `<article class="detection-row"><div>${badge(item.type, item.type === "SUSPICIOUS_ACTIVITY" ? "high" : "medium")}<h3>${escapeHtml(item.payment_id)}</h3><p>${escapeHtml(item.summary)}</p></div><div class="detection-amount">${escapeHtml(currency(item.amount, item.currency))}<small>${escapeHtml(item.evidence_ids.join(" · "))}</small></div></article>`).join("")}</div><div class="detection-save"><span>Automatic decision and any required department ticket are recorded with the case.</span><button id="save-detected-cases" class="button primary">Create and route ${result.count} case${result.count === 1 ? "" : "s"}</button></div>` : `<div class="empty-state">No configured exception rules matched these records.</div>`}</section>`;
      const saveRequestKey = crypto.randomUUID ? crypto.randomUUID() : `detect-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      $("#save-detected-cases")?.addEventListener("click", async saveEvent => {
        const saveButton = saveEvent.currentTarget;
        saveButton.disabled = true;
        saveButton.textContent = "Saving cases…";
        try {
          const saved = await api("/api/detection/commit", { method: "POST", headers: { "Idempotency-Key": saveRequestKey }, body: JSON.stringify({ schema_version: "1.1", records, timing_window_days: Number($("#timing-window").value) }) });
          toast(saved.duplicate_run ? "This submission was already processed." : `${saved.count} cases decided and routed: ${saved.outcomes.map(item => human(item.outcome)).join(", ")}.`);
          await loadDashboard();
          navigate("cases");
        } catch (err) { toast(err.message, true); saveButton.disabled = false; saveButton.textContent = `Create ${result.count} draft case${result.count === 1 ? "" : "s"}`; }
      });
    } catch (err) { output.innerHTML = `<section class="content-card"><div class="empty-state">${escapeHtml(err.message)}</div></section>`; }
    finally { button.disabled = false; button.textContent = "Analyze records"; }
  });
}

async function navigate(view) {
  if (view === "case") return state.selectedCase && openCase(state.selectedCase);
  state.currentView = ["dashboard", "cases", "scan", "tickets", "audit", "regulatory"].includes(view) && (view !== "regulatory" || state.user?.role === "admin") ? view : "dashboard";
  state.selectedCase = null;
  history.replaceState(null, "", `#${state.currentView}`);
  $$(".nav-item").forEach(button => button.classList.toggle("active", button.dataset.view === state.currentView));
  const labels = { dashboard: "Command center", cases: "Exception queue", scan: "Detection lab", tickets: "Department tickets", audit: "Audit history", regulatory: "Regulatory update inbox" };
  $("#page-crumb").textContent = labels[state.currentView];
  try {
    if (!state.dashboard) await loadDashboard();
    if (state.currentView === "dashboard") renderDashboard();
    if (state.currentView === "cases") renderCases();
    if (state.currentView === "scan") renderScan();
    if (state.currentView === "tickets") renderTickets();
    if (state.currentView === "audit") await renderAuditPage();
    if (state.currentView === "regulatory") await renderRegulatory();
  } catch (err) { $("#page-content").innerHTML = `<section class="content-card"><div class="empty-state">${escapeHtml(err.message)}</div></section>`; }
}

$("#login-form").addEventListener("submit", async event => {
  event.preventDefault();
  const button = $("#login-form button[type=submit]");
  button.disabled = true;
  $("#login-error").textContent = "";
  try { const data = await api("/api/login", { method: "POST", body: JSON.stringify({ username: $("#username").value, password: $("#password").value }) }); showApp(data.user); }
  catch (err) { $("#login-error").textContent = err.message; }
  finally { button.disabled = false; }
});

$("#logout-button").addEventListener("click", async () => {
  try { await api("/api/logout", { method: "POST", body: "{}" }); } catch { /* Expired sessions still return to sign-in. */ }
  showLogin();
});

$("#refresh-button").addEventListener("click", async () => {
  try { await loadDashboard(); await navigate(state.currentView); toast("Workspace refreshed."); }
  catch (err) { toast(err.message, true); }
});

$$('[data-view]').forEach(button => button.addEventListener("click", () => navigate(button.dataset.view)));
document.addEventListener("click", event => {
  const target = event.target.closest("[data-navigate]");
  if (target) navigate(target.dataset.navigate);
});
window.addEventListener("hashchange", () => { if (state.user) navigate(location.hash.slice(1)); });

api("/api/session").then(data => showApp(data.user)).catch(() => showLogin());

