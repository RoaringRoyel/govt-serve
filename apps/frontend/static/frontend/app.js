"use strict";
const S = { access: localStorage.getItem("access"), refresh: localStorage.getItem("refresh"), user: null, categories: [] };
const STATUSES = [["not_validated", "Not validated yet"], ["validated", "Validated"], ["officer_assigned", "Officer assigned"], ["pending", "Pending"], ["task_done", "Task done"]];
const BADGE = { not_validated: "secondary", validated: "info", officer_assigned: "primary", pending: "warning", task_done: "success", low: "success", medium: "warning", high: "danger" };
const POINTS = { high: 3, medium: 2, low: 1 };
const $ = (s, el = document) => el.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const badge = (k, label) => `<span class="badge text-bg-${BADGE[k] || "secondary"}">${esc(label || k)}</span>`;
const fmt = (d) => (d ? new Date(d).toLocaleString() : "");

function toast(msg, ok = true) {
  const el = document.createElement("div");
  el.className = `toast align-items-center text-bg-${ok ? "success" : "danger"} border-0 show`;
  el.innerHTML = `<div class="d-flex"><div class="toast-body">${esc(msg)}</div></div>`;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), 4000);
}
function errText(status, data) {
  if (status === 429) return "Too many requests. Please wait a moment and try again.";
  if (data && data.detail) return data.detail;
  if (data && typeof data === "object") return Object.entries(data).map(([k, v]) => `${k}: ${[].concat(v).join(" ")}`).join(" | ");
  return `Error ${status}`;
}
async function refreshToken() {
  const r = await fetch("/api/auth/refresh/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh: S.refresh }) });
  if (!r.ok) return false;
  S.access = (await r.json()).access;
  localStorage.setItem("access", S.access);
  return true;
}
async function api(path, { method = "GET", body, form } = {}, retry = true) {
  const headers = {};
  if (S.access) headers.Authorization = "Bearer " + S.access;
  let payload;
  if (form) payload = form;
  else if (body) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const res = await fetch("/api" + path, { method, headers, body: payload });
  if (res.status === 401 && retry && S.refresh && !path.startsWith("/auth/")) {
    if (await refreshToken()) return api(path, { method, body, form }, false);
    logout();
    throw new Error("Session expired, please log in again.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(errText(res.status, data));
  return data;
}
const act = async (fn) => { try { await fn(); } catch (e) { toast(e.message, false); } };

function saveSession(d) {
  S.access = d.access; S.refresh = d.refresh; S.user = d.user;
  localStorage.setItem("access", d.access); localStorage.setItem("refresh", d.refresh);
}
function logout() {
  localStorage.clear(); S.access = S.refresh = S.user = null; boot();
}

/* ---------------- auth screen ---------------- */
function renderAuth() {
  $("#nav-user").innerHTML = "";
  $("#app").innerHTML = `
  <div class="row justify-content-center"><div class="col-md-6"><div class="card shadow-sm"><div class="card-body">
    <ul class="nav nav-pills mb-3">
      <li class="nav-item"><button class="nav-link active" data-bs-toggle="pill" data-bs-target="#tab-login">Login</button></li>
      <li class="nav-item"><button class="nav-link" data-bs-toggle="pill" data-bs-target="#tab-register">Create citizen account</button></li>
    </ul>
    <div class="tab-content">
      <form class="tab-pane fade show active" id="tab-login">
        <input class="form-control mb-2" name="email" type="email" placeholder="Email" required>
        <input class="form-control mb-3" name="password" type="password" placeholder="Password" required>
        <button class="btn btn-primary w-100">Login</button>
      </form>
      <form class="tab-pane fade" id="tab-register">
        <input class="form-control mb-2" name="full_name" placeholder="Full name" required>
        <input class="form-control mb-2" name="email" type="email" placeholder="Email" required>
        <input class="form-control mb-2" name="phone" placeholder="Phone (e.g. +8801712345678)" required>
        <input class="form-control mb-3" name="password" type="password" minlength="8" placeholder="Password (min 8 characters)" required>
        <button class="btn btn-success w-100">Register</button>
      </form>
    </div></div></div></div></div>`;
  $("#tab-login").onsubmit = (e) => { e.preventDefault(); act(async () => {
    saveSession(await api("/auth/login/", { method: "POST", body: Object.fromEntries(new FormData(e.target)) })); boot(); }); };
  $("#tab-register").onsubmit = (e) => { e.preventDefault(); act(async () => {
    saveSession(await api("/auth/register/", { method: "POST", body: Object.fromEntries(new FormData(e.target)) })); boot(); }); };
}

/* ---------------- shared: request table + detail modal ---------------- */
function requestTable(rows, cols) {
  if (!rows.length) return `<p class="text-muted mb-0">Nothing here yet.</p>`;
  return `<div class="table-responsive"><table class="table table-hover align-middle">
    <thead><tr><th>#</th><th>Title</th><th>Category</th>${cols.includes("citizen") ? "<th>Citizen</th>" : ""}<th>Priority</th><th>Status</th>${cols.includes("officer") ? "<th>Officer</th>" : ""}</tr></thead>
    <tbody>${rows.map((r) => `<tr class="clickable" data-open="${r.id}"><td>${r.id}</td><td>${esc(r.title)}</td><td>${esc(r.category_name)}</td>
      ${cols.includes("citizen") ? `<td>${esc(r.citizen_name)}</td>` : ""}<td>${badge(r.priority, r.priority_label)}</td><td>${badge(r.status, r.status_label)}</td>
      ${cols.includes("officer") ? `<td>${esc(r.officer_name || "-")}</td>` : ""}</tr>`).join("")}</tbody></table></div>`;
}
function bindOpen(root) { root.querySelectorAll("[data-open]").forEach((tr) => (tr.onclick = () => openRequest(tr.dataset.open))); }
function progress(status) {
  const idx = STATUSES.findIndex((s) => s[0] === status);
  return `<div class="d-flex gap-1 my-3">${STATUSES.map((s, i) => `<div class="step"><div class="progress" style="height:8px"><div class="progress-bar ${i <= idx ? "bg-success" : ""}" style="width:${i <= idx ? 100 : 0}%"></div></div>${esc(s[1])}</div>`).join("")}</div>`;
}
async function downloadFile(url, name) {
  const res = await fetch(url, { headers: { Authorization: "Bearer " + S.access } });
  if (!res.ok) return toast("Download failed", false);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(await res.blob()); a.download = name; a.click();
}

async function openRequest(id) {
  await act(async () => {
    const role = S.user.role;
    const [r, comments, files] = await Promise.all([api(`/requests/${id}/`), api(`/requests/${id}/comments/`), api(`/requests/${id}/attachments/`)]);
    let officers = [];
    if (role === "admin" && ["validated", "officer_assigned"].includes(r.status)) officers = await api("/admin/officers/available/");
    let actions = "";
    if (role === "admin" && r.status === "not_validated") actions = `<button class="btn btn-info" id="a-validate">Validate request</button>`;
    if (role === "admin" && ["validated", "officer_assigned"].includes(r.status))
      actions = `<div class="input-group"><select class="form-select" id="a-officer"><option value="">Select an available officer...</option>
        ${officers.map((o) => `<option value="${o.id}">${esc(o.full_name)} (${o.active_tasks} active)</option>`).join("")}</select>
        <button class="btn btn-primary" id="a-assign">Assign</button></div>${officers.length ? "" : '<div class="text-danger small mt-1">No officer is available right now.</div>'}`;
    if (role === "officer" && r.status === "officer_assigned") actions = `<button class="btn btn-warning" data-status="pending">Start work (set Pending)</button>`;
    if (role === "officer" && r.status === "pending") actions = `<button class="btn btn-success" data-status="task_done">Mark task done (+${POINTS[r.priority]} points)</button>`;
    const canEdit = role === "citizen" && r.status === "not_validated";
    const audience = role === "citizen" ? "" : `<select class="form-select" name="audience" style="max-width:220px"><option value="citizen">Comment for citizen</option><option value="officer">Comment for officer (internal)</option></select>`;
    $("#detailBody").innerHTML = `
      <div class="d-flex justify-content-between"><h5>#${r.id} ${esc(r.title)}</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
      <div class="mb-2">${badge(r.priority, r.priority_label + " priority")} ${badge(r.status, r.status_label)} <span class="text-muted small">${esc(r.category_name)} - by ${esc(r.citizen_name)} - ${fmt(r.created_at)}</span></div>
      ${progress(r.status)}
      <p class="mb-1">${esc(r.description)}</p>
      ${r.remarks ? `<p class="text-muted"><b>Citizen remarks:</b> ${esc(r.remarks)}</p>` : ""}
      <p class="small">Officer: <b>${esc(r.officer_name || "not assigned yet")}</b></p>
      ${actions ? `<div class="p-2 bg-light border rounded mb-3">${actions}</div>` : ""}
      ${canEdit ? `<details class="mb-3"><summary>Edit request</summary><form id="editForm" class="mt-2">
        <input class="form-control mb-2" name="title" value="${esc(r.title)}" required>
        <textarea class="form-control mb-2" name="description" rows="3" required>${esc(r.description)}</textarea>
        <textarea class="form-control mb-2" name="remarks" rows="2" placeholder="Remarks">${esc(r.remarks)}</textarea>
        <select class="form-select mb-2" name="priority">${["low", "medium", "high"].map((p) => `<option ${p === r.priority ? "selected" : ""}>${p}</option>`).join("")}</select>
        <button class="btn btn-sm btn-primary">Save changes</button></form></details>` : ""}
      <h6>Attachments</h6>
      <ul class="list-unstyled small">${files.map((f) => `<li><a href="#" data-dl="${esc(f.download_url)}" data-name="${esc(f.original_name)}">${esc(f.original_name)}</a> (${Math.round(f.size / 1024)} KB, ${esc(f.uploaded_by_name)})</li>`).join("") || "<li class='text-muted'>None</li>"}</ul>
      <form id="fileForm" class="input-group input-group-sm mb-3"><input type="file" class="form-control" name="file" required><button class="btn btn-outline-secondary">Upload</button></form>
      <h6>Comments</h6>
      <div class="mb-2">${comments.map((c) => `<div class="border rounded p-2 mb-1 ${c.audience === "officer" ? "border-warning" : ""}"><b>${esc(c.author_name)}</b> <span class="text-muted small">(${esc(c.author_role)}, ${fmt(c.created_at)})</span>${c.audience === "officer" ? ' <span class="badge text-bg-warning">internal</span>' : ""}<div class="chat-msg">${esc(c.body)}</div></div>`).join("") || "<p class='text-muted small'>No comments yet.</p>"}</div>
      <form id="commentForm" class="d-flex gap-2">${audience}<input class="form-control" name="body" placeholder="Write a comment..." required><button class="btn btn-primary">Send</button></form>`;
    const modal = bootstrap.Modal.getOrCreateInstance($("#detailModal"));
    modal.show();
    const reload = () => { openRequest(id); refreshView(); };
    const v = $("#a-validate"); if (v) v.onclick = () => act(async () => { await api(`/requests/${id}/validate/`, { method: "POST" }); toast("Validated"); reload(); });
    const a = $("#a-assign"); if (a) a.onclick = () => act(async () => {
      const officer_id = $("#a-officer").value; if (!officer_id) throw new Error("Choose an officer first.");
      await api(`/requests/${id}/assign/`, { method: "POST", body: { officer_id: Number(officer_id) } }); toast("Officer assigned"); reload(); });
    document.querySelectorAll("[data-status]").forEach((b) => (b.onclick = () => act(async () => {
      await api(`/requests/${id}/status/`, { method: "POST", body: { status: b.dataset.status } }); toast("Status updated"); reload(); })));
    document.querySelectorAll("[data-dl]").forEach((l) => (l.onclick = (e) => { e.preventDefault(); downloadFile(l.dataset.dl, l.dataset.name); }));
    const ef = $("#editForm"); if (ef) ef.onsubmit = (e) => { e.preventDefault(); act(async () => {
      await api(`/requests/${id}/`, { method: "PATCH", body: Object.fromEntries(new FormData(ef)) }); toast("Saved"); reload(); }); };
    $("#fileForm").onsubmit = (e) => { e.preventDefault(); act(async () => {
      await api(`/requests/${id}/attachments/`, { method: "POST", form: new FormData(e.target) }); toast("File uploaded"); reload(); }); };
    $("#commentForm").onsubmit = (e) => { e.preventDefault(); act(async () => {
      await api(`/requests/${id}/comments/`, { method: "POST", body: Object.fromEntries(new FormData(e.target)) }); reload(); }); };
  });
}

/* ---------------- citizen ---------------- */
async function renderCitizen() {
  S.categories = await api("/categories/");
  $("#app").innerHTML = `<div class="row g-4">
    <div class="col-lg-5"><div class="card shadow-sm mb-4"><div class="card-header">Submit a new request</div><div class="card-body">
      <form id="newReq">
        <select class="form-select mb-2" name="category" required><option value="">Select service...</option>${S.categories.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}</select>
        <select class="form-select mb-2" name="priority"><option value="low">Low priority</option><option value="medium" selected>Medium priority</option><option value="high">High priority</option></select>
        <input class="form-control mb-2" name="title" placeholder="Short title" required maxlength="200">
        <textarea class="form-control mb-2" name="description" rows="3" placeholder="Describe your request" required></textarea>
        <textarea class="form-control mb-2" name="remarks" rows="2" placeholder="Remarks (optional)"></textarea>
        <input type="file" class="form-control mb-3" name="file">
        <button class="btn btn-primary w-100">Submit request</button>
      </form></div></div>
      <div class="card shadow-sm"><div class="card-header">AI support</div><div class="card-body">
        <div class="chat-box border rounded p-2 mb-2" id="chat"><div class="chat-msg text-muted">Ask about NID, passport, police verification, missing reports, or the status of your requests.</div></div>
        <form id="chatForm" class="input-group"><input class="form-control" name="question" placeholder="Ask a question..." required><button class="btn btn-outline-primary">Ask</button></form>
      </div></div></div>
    <div class="col-lg-7"><div class="card shadow-sm"><div class="card-header">My requests</div><div class="card-body" id="list"></div></div></div></div>`;
  $("#newReq").onsubmit = (e) => { e.preventDefault(); act(async () => {
    const fd = new FormData(e.target); const file = fd.get("file"); fd.delete("file");
    const created = await api("/requests/", { method: "POST", body: Object.fromEntries(fd) });
    if (file && file.size) { const f = new FormData(); f.append("file", file); await api(`/requests/${created.id}/attachments/`, { method: "POST", form: f }); }
    e.target.reset(); toast("Request submitted. Status: Not validated yet."); refreshView(); }); };
  $("#chatForm").onsubmit = (e) => { e.preventDefault(); act(async () => {
    const q = new FormData(e.target).get("question"); const chat = $("#chat");
    chat.insertAdjacentHTML("beforeend", `<div class="chat-msg mt-2"><b>You:</b> ${esc(q)}</div>`); e.target.reset();
    const r = await api("/support/ask/", { method: "POST", body: { question: q } });
    chat.insertAdjacentHTML("beforeend", `<div class="chat-msg mt-2"><b>Assistant:</b> ${esc(r.answer)}</div>`); chat.scrollTop = chat.scrollHeight; }); };
  await citizenList();
}
async function citizenList() {
  const data = await api("/requests/?page_size=100");
  $("#list").innerHTML = requestTable(data.results, []); bindOpen($("#list"));
}

/* ---------------- officer ---------------- */
async function renderOfficer() {
  const me = await api("/auth/me/");
  const data = await api("/requests/?page_size=100");
  const active = data.results.filter((r) => r.status !== "task_done").length;
  $("#app").innerHTML = `<div class="row g-3 mb-4">
    <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2">${me.points}</div>My points</div></div></div>
    <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2">${active}</div>Active tasks</div></div></div>
    <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2">${data.results.length - active}</div>Completed</div></div></div></div>
    <div class="card shadow-sm"><div class="card-header">My assigned tasks <span class="text-muted small">(High = 3 pts, Medium = 2, Low = 1)</span></div><div class="card-body" id="list">${requestTable(data.results, ["citizen"])}</div></div>`;
  bindOpen($("#app"));
}

/* ---------------- admin ---------------- */
let adminTab = "overview";
async function renderAdmin() {
  $("#app").innerHTML = `<ul class="nav nav-tabs mb-3">${["overview", "requests", "officers", "categories", "audit"].map((t) =>
    `<li class="nav-item"><button class="nav-link ${t === adminTab ? "active" : ""}" data-tab="${t}">${t[0].toUpperCase() + t.slice(1)}</button></li>`).join("")}</ul><div id="tab"></div>`;
  document.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => { adminTab = b.dataset.tab; renderAdmin(); }));
  const el = $("#tab");
  if (adminTab === "overview") {
    const s = await api("/admin/stats/");
    el.innerHTML = `<div class="row g-3 mb-4">
      ${[["Total requests", s.totals.all], ["Pending (not done)", s.totals.pending], ["Completed", s.totals.completed], ["Waiting validation", s.by_status.not_validated]]
        .map(([l, n]) => `<div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2">${n}</div>${l}</div></div></div>`).join("")}</div>
      <div class="row g-3"><div class="col-md-6"><div class="card shadow-sm"><div class="card-header">By status</div><ul class="list-group list-group-flush">
        ${STATUSES.map(([k, l]) => `<li class="list-group-item d-flex justify-content-between">${l}<span class="badge text-bg-${BADGE[k]}">${s.by_status[k]}</span></li>`).join("")}</ul></div></div>
      <div class="col-md-6"><div class="card shadow-sm"><div class="card-header">By category</div><ul class="list-group list-group-flush">
        ${s.by_category.map((c) => `<li class="list-group-item d-flex justify-content-between">${esc(c.category)}<span class="badge text-bg-dark">${c.count}</span></li>`).join("")}</ul></div></div></div>
      <div class="card shadow-sm mt-4"><div class="card-header">Officer workload</div><div class="card-body">${officerTable(s.officers)}</div></div>`;
  } else if (adminTab === "requests") {
    el.innerHTML = `<div class="card shadow-sm"><div class="card-body"><select class="form-select mb-3" id="f-status" style="max-width:260px"><option value="">All statuses</option>${STATUSES.map(([k, l]) => `<option value="${k}">${l}</option>`).join("")}</select><div id="list"></div></div></div>`;
    const load = async () => { const st = $("#f-status").value; const d = await api(`/requests/?page_size=100${st ? "&status=" + st : ""}`);
      $("#list").innerHTML = requestTable(d.results, ["citizen", "officer"]); bindOpen($("#list")); };
    $("#f-status").onchange = () => act(load); await load();
  } else if (adminTab === "officers") {
    const officers = await api("/admin/officers/");
    el.innerHTML = `<div class="card shadow-sm mb-4"><div class="card-header">Officers</div><div class="card-body">${officerTable(officers)}</div></div>
      <div class="card shadow-sm"><div class="card-header">Add officer</div><div class="card-body"><form id="offForm" class="row g-2">
        <div class="col-md-3"><input class="form-control" name="full_name" placeholder="Full name" required></div>
        <div class="col-md-3"><input class="form-control" name="email" type="email" placeholder="Email" required></div>
        <div class="col-md-2"><input class="form-control" name="phone" placeholder="Phone" required></div>
        <div class="col-md-2"><input class="form-control" name="password" type="password" placeholder="Password" required></div>
        <div class="col-md-2"><button class="btn btn-primary w-100">Create</button></div></form></div></div>`;
    $("#offForm").onsubmit = (e) => { e.preventDefault(); act(async () => {
      await api("/admin/officers/", { method: "POST", body: Object.fromEntries(new FormData(e.target)) }); toast("Officer created"); renderAdmin(); }); };
  } else if (adminTab === "categories") {
    const cats = await api("/categories/");
    el.innerHTML = `<div class="card shadow-sm"><div class="card-header">Service categories</div><ul class="list-group list-group-flush">
      ${cats.map((c) => `<li class="list-group-item d-flex justify-content-between align-items-center">${esc(c.name)} ${c.is_active ? "" : "(inactive)"}
        <button class="btn btn-sm btn-outline-secondary" data-toggle="${c.id}" data-active="${c.is_active}">${c.is_active ? "Deactivate" : "Activate"}</button></li>`).join("")}</ul>
      <div class="card-body"><form id="catForm" class="input-group"><input class="form-control" name="name" placeholder="New category name" required><button class="btn btn-primary">Add</button></form></div></div>`;
    $("#catForm").onsubmit = (e) => { e.preventDefault(); act(async () => {
      await api("/categories/", { method: "POST", body: Object.fromEntries(new FormData(e.target)) }); renderAdmin(); }); };
    document.querySelectorAll("[data-toggle]").forEach((b) => (b.onclick = () => act(async () => {
      await api(`/categories/${b.dataset.toggle}/`, { method: "PATCH", body: { is_active: b.dataset.active !== "true" } }); renderAdmin(); })));
  } else {
    const logs = (await api("/admin/audit-logs/?page_size=100")).results;
    el.innerHTML = `<div class="card shadow-sm"><div class="card-header">Audit log (latest 100)</div><div class="table-responsive"><table class="table table-sm mb-0"><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Target</th><th>IP</th></tr></thead>
      <tbody>${logs.map((l) => `<tr><td>${fmt(l.created_at)}</td><td>${esc(l.actor_email || "-")}</td><td>${esc(l.action)}</td><td>${esc(l.target_type)} ${esc(l.target_id)}</td><td>${esc(l.ip_address || "")}</td></tr>`).join("")}</tbody></table></div></div>`;
  }
  bindOpen(el);
}
function officerTable(officers) {
  if (!officers.length) return `<p class="text-muted mb-0">No officers yet.</p>`;
  return `<div class="table-responsive"><table class="table align-middle"><thead><tr><th>Officer</th><th>Availability</th><th>Working on</th><th>Active</th><th>Completed</th><th>Points</th></tr></thead><tbody>
    ${officers.map((o) => `<tr><td>${esc(o.full_name)}<div class="small text-muted">${esc(o.email)}</div></td>
      <td>${o.available ? '<span class="badge text-bg-success">Available</span>' : '<span class="badge text-bg-secondary">Busy</span>'}</td>
      <td>${o.current_tasks.map((t) => `<div class="small clickable" data-open="${t.id}">#${t.id} ${esc(t.title)} ${badge(t.priority, t.priority)} ${badge(t.status, t.status.replace("_", " "))}</div>`).join("") || '<span class="text-muted small">Idle</span>'}</td>
      <td>${o.active_tasks}</td><td>${o.completed_tasks}</td><td><b>${o.points}</b></td></tr>`).join("")}</tbody></table></div>`;
}

/* ---------------- boot ---------------- */
function refreshView() { if (S.user) act(viewFor); }
function viewFor() {
  return { citizen: renderCitizen, officer: renderOfficer, admin: renderAdmin }[S.user.role]();
}
async function boot() {
  if (!S.access) return renderAuth();
  try { S.user = await api("/auth/me/"); } catch { return renderAuth(); }
  $("#nav-user").innerHTML = `${esc(S.user.full_name)} <span class="badge text-bg-light">${esc(S.user.role)}</span> <button class="btn btn-sm btn-outline-light ms-2" id="change-pw">Change password</button> <button class="btn btn-sm btn-outline-light ms-1" id="logout">Logout</button>`;
  $("#logout").onclick = logout;
  $("#change-pw").onclick = () => { $("#pwForm").reset(); bootstrap.Modal.getOrCreateInstance($("#pwModal")).show(); };
  act(viewFor);
}
$("#pwForm").onsubmit = (e) => { e.preventDefault(); act(async () => {
  const d = Object.fromEntries(new FormData(e.target));
  if (d.new_password !== d.confirm_password) throw new Error("New passwords do not match.");
  await api("/auth/change-password/", { method: "POST", body: { old_password: d.old_password, new_password: d.new_password } });
  bootstrap.Modal.getOrCreateInstance($("#pwModal")).hide(); e.target.reset(); toast("Password changed successfully."); }); };
boot();
