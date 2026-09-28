/* FactDeck mainline UI (Tabler shell) over /api/deck.
   The server decides every gate; this page only shows state and records human decisions. */
"use strict";

const API = "/api/deck";
const $ = (sel, root = document) => root.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const short = (h) => (h ? String(h).slice(0, 12) : "—");
const time = (t) => (t ? String(t).replace("T", " ").slice(0, 19) : "—");

const STEPS = [
  ["阅读", ["READING_REQUIRED"]],
  ["总结", ["SUMMARY_REQUIRED"]],
  ["内容确认", ["CONTENT_CONFIRMATION"]],
  ["事实库", ["FACTS_REQUIRED"]],
  ["页面规格", ["DECK_REQUIRED", "DECK_REVISION"]],
  ["确认与审查", ["CONFIRMATIONS_REQUIRED", "SEMANTIC_REVIEW_REQUIRED", "SEMANTIC_ISSUES"]],
  ["渲染", ["RENDER_REQUIRED"]],
  ["样页审核", ["SAMPLES_REVIEW"]],
  ["风格确认", ["STYLE_CONFIRMATION"]],
  ["逐页审核", ["PAGE_REVIEW"]],
  ["交付", ["READY_TO_EXPORT", "DELIVERED"]],
];
const STAGE_LABEL = {
  READING_REQUIRED: "待阅读资料", SUMMARY_REQUIRED: "待全文总结", CONTENT_CONFIRMATION: "待客户确认内容",
  FACTS_REQUIRED: "待建立事实库", DECK_REQUIRED: "待编写页面规格", DECK_REVISION: "页面规格需修订",
  CONFIRMATIONS_REQUIRED: "待人工确认", SEMANTIC_REVIEW_REQUIRED: "待独立语义审查", SEMANTIC_ISSUES: "语义审查有阻断问题",
  RENDER_REQUIRED: "待正式渲染", SAMPLES_REVIEW: "待审核前5页", STYLE_CONFIRMATION: "待客户确认风格",
  PAGE_REVIEW: "待逐页审核", READY_TO_EXPORT: "可交付", DELIVERED: "已交付",
};
const KIND_LABEL = {
  READ_SOURCE: "阅读资料", SECOND_READ: "第二次独立转录", SUMMARY: "全文总结",
  FACTS: "事实库", DECK: "页面规格", SEMANTIC_REVIEW: "独立语义审查",
};
const TABS = [
  ["overview", "项目与需求", "ti-settings"], ["sources", "资料", "ti-files"], ["tasks", "执行端任务", "ti-list-check"],
  ["summary", "总结与内容确认", "ti-notes"], ["facts", "事实库", "ti-database"], ["deck", "页面规格", "ti-layout-board"],
  ["confirm", "人工确认", "ti-user-check"], ["render", "渲染与审核", "ti-photo"], ["delivery", "交付与记录", "ti-package-export"],
];

let health = { themes: [] };
let current = null;   // workflow being shown

// ------------------------------------------------------------ helpers
function me() {
  const v = $("#me").value.trim();
  if (!v) throw new Error("请先在右上角填写当前操作人姓名");
  return v;
}
try { $("#me").value = localStorage.getItem("factdeck.me") || ""; } catch (e) { /* storage unavailable */ }
$("#me").addEventListener("change", () => { try { localStorage.setItem("factdeck.me", $("#me").value.trim()); } catch (e) { /* ignore */ } });

async function api(method, path, body, raw = false) {
  const opt = { method, headers: {} };
  if (body instanceof FormData) opt.body = body;
  else if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
  const res = await fetch(API + path, opt);
  if (res.status === 204) return null;
  if (!res.ok) {
    let msg = res.status + " " + res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (e) { /* not json */ }
    const err = new Error(msg); err.status = res.status; throw err;
  }
  return raw ? res.text() : res.json();
}
async function optional(path, raw = false) {
  try { return await api("GET", path, undefined, raw); } catch (e) { if (e.status === 409) return null; throw e; }
}
function flash(msg, kind = "danger") {
  $("#flash").innerHTML = `<div class="alert alert-${kind} alert-dismissible" role="alert"><div>${esc(msg)}</div>
    <a class="btn-close" data-bs-dismiss="alert" aria-label="close"></a></div>`;
  window.scrollTo({ top: 0, behavior: "smooth" });
}
async function act(fn, ok) {
  try {
    const r = await fn();
    if (r && r.id && r.stage) current = r;
    if (ok) flash(ok, "success");
    await route();
  } catch (e) { flash(e.message); }
}
function badge(text, color) { return `<span class="badge bg-${color}-lt">${esc(text)}</span>`; }
function stageBadge(stage) {
  const color = stage === "DELIVERED" ? "green" : stage === "READY_TO_EXPORT" ? "teal" : /REVISION|ISSUES/.test(stage) ? "red" : "blue";
  return badge(STAGE_LABEL[stage] || stage, color);
}
function card(title, body, extra = "") {
  return `<div class="card mb-3"><div class="card-header"><h3 class="card-title">${title}</h3>${extra ? `<div class="card-actions">${extra}</div>` : ""}</div>${body}</div>`;
}
function empty(text) { return `<div class="card-body text-secondary">${esc(text)}</div>`; }
function wid() { return current.id; }
function url(path) { return `${API}/workflows/${encodeURIComponent(wid())}${path}`; }

// ------------------------------------------------------------ routing
window.addEventListener("hashchange", route);
async function route() {
  const [, id, tab] = (location.hash.replace(/^#\/?/, "").match(/^w\/([^/]+)\/?(\w*)/) || []);
  try {
    if (!id) { current = null; return renderList(); }
    current = await api("GET", `/workflows/${encodeURIComponent(id)}`);
    await renderWorkflow(tab || "overview");
  } catch (e) { $("#view").innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div><a href="#/">返回项目列表</a>`; }
}

// ------------------------------------------------------------ project list
async function renderList() {
  const list = await api("GET", "/workflows");
  const themes = health.themes.map((t) => `<option>${esc(t)}</option>`).join("");
  $("#view").innerHTML = `
    <div class="page-header mb-3"><h2 class="page-title">项目</h2></div>
    <div class="row g-3">
      <div class="col-lg-7">${card("全部项目", list.length ? `<div class="table-responsive"><table class="table table-vcenter card-table">
        <thead><tr><th>名称</th><th>阶段</th><th>资料</th><th>页数</th><th>更新</th></tr></thead><tbody>
        ${list.map((w) => `<tr><td><a href="#/w/${esc(w.id)}">${esc(w.title)}</a></td><td>${stageBadge(w.stage)}</td>
          <td>${w.sources}</td><td>${w.pages}</td><td class="text-secondary">${time(w.updated_at)}</td></tr>`).join("")}
        </tbody></table></div>` : empty("还没有项目。"))}</div>
      <div class="col-lg-5">${card("新建项目", `<form id="create" class="card-body">
        <div class="mb-3"><label class="form-label required">名称</label><input name="title" class="form-control" required maxlength="200"></div>
        <div class="mb-3"><label class="form-label">教学提纲（每行一条）</label><textarea name="outline" class="form-control" rows="4"></textarea></div>
        ${requirementFields({})}
        <div class="mb-3"><label class="form-label">配色</label><select name="theme" class="form-select">${themes}</select></div>
        <button class="btn btn-primary"><i class="ti ti-plus me-1"></i>创建</button></form>`)}</div>
    </div>`;
  $("#create").onsubmit = (ev) => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    act(async () => {
      const w = await api("POST", "/workflows", { title: f.get("title"), outline: f.get("outline"), theme: f.get("theme"), requirements: readRequirements(f) });
      location.hash = `#/w/${w.id}`;
    });
  };
}

function requirementFields(r) {
  const input = (k, label, type = "text") => `<div class="col-md-6"><label class="form-label">${label}</label>
    <input name="req_${k}" type="${type}" class="form-control" value="${esc(r[k] ?? "")}" ${type === "number" ? 'min="1"' : ""}></div>`;
  const area = (k, label) => `<div class="col-12"><label class="form-label">${label}</label>
    <textarea name="req_${k}" class="form-control" rows="2">${esc(r[k] ?? "")}</textarea></div>`;
  return `<div class="row g-2 mb-3">${input("audience", "受众")}${input("tone", "语气")}${input("duration_minutes", "时长（分钟）", "number")}
    ${input("target_pages", "目标页数", "number")}${area("purpose", "目的")}${area("emphasis", "重点")}${area("notes", "其他要求")}</div>`;
}
function readRequirements(f) {
  const r = {};
  for (const k of ["audience", "purpose", "duration_minutes", "target_pages", "emphasis", "tone", "notes"]) {
    const v = String(f.get("req_" + k) ?? "").trim();
    if (v) r[k] = /duration_minutes|target_pages/.test(k) ? Number(v) : v;
  }
  return r;
}

// ------------------------------------------------------------ workflow shell
async function renderWorkflow(tab) {
  const w = current;
  const at = STEPS.findIndex(([, st]) => st.includes(w.stage));
  const steps = STEPS.map(([label], i) => `<li class="step-item ${i === at ? "active" : ""}">${label}</li>`).join("");
  const nav = TABS.map(([k, label, icon]) => `<li class="nav-item"><a class="nav-link ${k === tab ? "active" : ""}" href="#/w/${esc(w.id)}/${k}">
    <i class="ti ${icon} me-1"></i>${label}</a></li>`).join("");
  $("#view").innerHTML = `
    <div class="page-header mb-3"><div class="row align-items-center">
      <div class="col"><div class="page-pretitle"><a href="#/">项目</a> / ${esc(w.id)} · 修订 ${w.revision}</div>
        <h2 class="page-title">${esc(w.title)}&nbsp;${stageBadge(w.stage)}</h2></div>
      <div class="col-auto"><button class="btn" id="reload"><i class="ti ti-refresh me-1"></i>刷新</button></div></div></div>
    <div class="card mb-3"><div class="card-body">
      <ul class="steps steps-counter stage-steps mb-2">${steps}</ul>
      ${w.open_items.length ? `<div class="text-secondary small">待办：${w.open_items.map(esc).join("；")}</div>` : `<div class="text-success small">没有待办。</div>`}
    </div></div>
    <ul class="nav nav-tabs mb-3 flex-nowrap overflow-auto">${nav}</ul>
    <div id="tab"></div>`;
  $("#reload").onclick = () => route();
  const views = { overview: tabOverview, sources: tabSources, tasks: tabTasks, summary: tabSummary, facts: tabFacts,
                  deck: tabDeck, confirm: tabConfirm, render: tabRender, delivery: tabDelivery };
  await (views[tab] || tabOverview)();
}

// ------------------------------------------------------------ tabs
function tabOverview() {
  const w = current;
  const themes = health.themes.map((t) => `<option ${t === w.theme ? "selected" : ""}>${esc(t)}</option>`).join("");
  $("#tab").innerHTML = card("项目与需求", `<form id="settings" class="card-body">
      <div class="alert alert-warning">修改提纲或需求会使总结、事实库或页面规格失效，需要重新生成和确认。</div>
      <div class="mb-3"><label class="form-label">名称</label><input name="title" class="form-control" value="${esc(w.title)}"></div>
      <div class="mb-3"><label class="form-label">教学提纲（每行一条）</label>
        <textarea name="outline" class="form-control" rows="6">${esc(w.outline.map((o) => o.text).join("\n"))}</textarea></div>
      ${requirementFields(w.requirements)}
      <div class="mb-3"><label class="form-label">配色</label><select name="theme" class="form-select">${themes}</select></div>
      <button class="btn btn-primary">保存</button></form>`);
  $("#settings").onsubmit = (ev) => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    act(() => api("PATCH", `/workflows/${wid()}`, { title: f.get("title"), outline: f.get("outline"), theme: f.get("theme"), requirements: readRequirements(f) }), "已保存");
  };
}

function tabSources() {
  const w = current;
  const rows = w.sources.map((s) => {
    const read = s.pages.filter((p) => p.reading).length;
    const visual = s.pages.filter((p) => p.requires_visual).length;
    const cells = s.transcriptions.length;
    const second = s.transcriptions.filter((u) => u.second_read).length;
    return `<tr><td class="mono">${esc(s.id)}</td>
      <td><a href="${url(`/sources/${encodeURIComponent(s.id)}/file`)}">${esc(s.filename)}</a><div class="text-secondary small mono">${short(s.sha256)}</div></td>
      <td>${esc(s.kind)}</td><td>${read} / ${s.pages.length}${visual ? `<div class="small text-secondary">需看图 ${visual}</div>` : ""}</td>
      <td>${s.units.length}</td><td>${cells ? `${cells}（复读 ${second}）` : "—"}</td>
      <td><button class="btn btn-sm btn-ghost-danger" data-remove="${esc(s.id)}">移除</button></td></tr>`;
  }).join("");
  const pagesList = w.sources.map((s) => s.pages.map((p) => `<tr><td class="mono">${esc(p.id)}</td><td>${esc(s.filename)} · ${esc(p.location)}</td>
      <td>${p.requires_visual ? badge("需看原图", "orange") : ""}</td>
      <td>${p.reading ? badge("已阅读", "green") : badge("未阅读", "secondary")}</td></tr>`).join("")).join("");
  $("#tab").innerHTML = card("资料", `<div class="card-body border-bottom">
      <form id="upload" class="d-flex gap-2 flex-wrap"><input type="file" name="file" class="form-control" style="max-width:28rem" multiple
        accept=".pdf,.pptx,.docx,.xlsx,.txt,.md,.png,.jpg,.jpeg,.webp">
        <button class="btn btn-primary"><i class="ti ti-upload me-1"></i>导入</button></form>
      <div class="form-hint">支持 PDF、PPTX、DOCX、XLSX、TXT/MD、PNG/JPG/WEBP，单个不超过 40MB。原件导入后不可修改。</div></div>
    ${w.sources.length ? `<div class="table-responsive"><table class="table card-table table-vcenter">
      <thead><tr><th>ID</th><th>文件</th><th>类型</th><th>已阅读页</th><th>可引用单元</th><th>图表转录</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`
      : empty("尚未导入资料。")}`)
    + (pagesList ? card("阅读页", `<div class="table-responsive" style="max-height:28rem"><table class="table card-table table-sm">
      <thead><tr><th>页</th><th>位置</th><th></th><th>状态</th></tr></thead><tbody>${pagesList}</tbody></table></div>`) : "");
  $("#upload").onsubmit = (ev) => {
    ev.preventDefault();
    const files = [...ev.target.file.files];
    if (!files.length) return flash("请选择文件");
    act(async () => {
      let last;
      for (const file of files) { const fd = new FormData(); fd.append("file", file); last = await api("POST", `/workflows/${wid()}/sources`, fd); }
      return last;
    }, `已导入 ${files.length} 份资料`);
  };
  document.querySelectorAll("[data-remove]").forEach((b) => b.onclick = () => {
    if (confirm(`移除资料 ${b.dataset.remove}？下游的总结、事实库和页面会失效。`))
      act(() => api("DELETE", `/workflows/${wid()}/sources/${encodeURIComponent(b.dataset.remove)}`), "已移除");
  });
}

function tabTasks() {
  const w = current;
  const buttons = Object.entries(KIND_LABEL).map(([k, label]) =>
    `<button class="btn btn-sm" data-queue="${k}"><i class="ti ti-plus me-1"></i>${label}</button>`).join(" ");
  const color = { PENDING: "secondary", RUNNING: "blue", COMPLETE: "green", FAILED: "red", CANCELLED: "secondary" };
  const rows = [...w.tasks].reverse().map((t) => `<tr><td>${esc(KIND_LABEL[t.kind] || t.kind)}</td><td class="mono">${esc(t.binding ?? "—")}</td>
      <td>${badge(t.status, color[t.status] || "secondary")}</td><td>${esc(t.worker ?? "—")}</td><td>${t.attempts}</td>
      <td class="text-secondary">${time(t.created_at)}</td><td class="small text-danger">${esc(t.error ?? "")}</td></tr>`).join("");
  $("#tab").innerHTML = card("执行端任务", `<div class="card-body border-bottom">
      <div class="d-flex flex-wrap gap-2">${buttons}</div>
      <div class="form-hint mt-2">任务由执行端领取完成：<code>python tools/codex_worker.py</code>。服务器会拒绝前置条件未满足的任务；
        语义审查和第二次转录须由不同的执行端身份完成。</div></div>
    ${w.tasks.length ? `<div class="table-responsive"><table class="table card-table table-vcenter">
      <thead><tr><th>类型</th><th>对象</th><th>状态</th><th>执行端</th><th>尝试</th><th>创建</th><th>错误</th></tr></thead><tbody>${rows}</tbody></table></div>`
      : empty("还没有任务。")}`);
  document.querySelectorAll("[data-queue]").forEach((b) => b.onclick = () =>
    act(() => api("POST", `/workflows/${wid()}/tasks`, { kind: b.dataset.queue }), `已加入：${KIND_LABEL[b.dataset.queue]}`));
}

function approvalForm(id, subject, label) {
  return `<form id="${id}" class="card-body border-top">
    <div class="row g-2">
      <div class="col-md-4"><label class="form-label required">客户</label><input name="customer" class="form-control" required></div>
      <div class="col-md-4"><label class="form-label required">确认方式</label><input name="method" class="form-control" placeholder="如：邮件、会议、签字稿" required></div>
      <div class="col-md-4"><label class="form-label">操作人</label><input class="form-control" value="${esc($("#me").value)}" disabled></div>
      <div class="col-12"><label class="form-label">客户反馈</label><textarea name="feedback" class="form-control" rows="2"></textarea></div>
    </div>
    <div class="form-hint my-2">确认对象校验值：<span class="mono">${esc(subject)}</span>。内容更新后校验值会变化，旧的确认不再有效。</div>
    <button class="btn btn-success"><i class="ti ti-check me-1"></i>${label}</button></form>`;
}
function bindApproval(id, kind, subject) {
  const form = $("#" + id);
  if (!form) return;
  form.onsubmit = (ev) => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    act(() => api("POST", `/workflows/${wid()}/approvals/${kind}`, { customer: f.get("customer"), operator: me(), method: f.get("method"),
      feedback: f.get("feedback"), subject_sha256: subject }), "确认已记录");
  };
}

function tabSummary() {
  const w = current, s = w.summary, a = w.content_approval, subject = w.approval_subjects.content;
  if (!s) { $("#tab").innerHTML = card("全文总结", empty("尚无总结。全部资料阅读完成后，在“执行端任务”中加入“全文总结”。")); return; }
  const loc = {};
  w.sources.forEach((src) => src.pages.forEach((p) => { loc[p.id] = `${src.filename} · ${p.location}`; }));
  const sections = s.sections.map((x) => `<div class="mb-3"><h4 class="mb-1">${esc(x.title)} <span class="text-secondary small mono">${esc(x.id)}</span></h4>
      <div class="quote">${esc(x.summary)}</div>
      <div class="small text-secondary mt-1">来源：${x.source_page_ids.map((r) => esc(loc[r] || r)).join("；")}</div></div>`).join("");
  const issues = s.pending_issues.length ? `<div class="alert alert-warning"><b>待解决问题（需先处理才能确认）</b><ul class="mb-0">
      ${s.pending_issues.map((i) => `<li>${esc(typeof i === "string" ? i : JSON.stringify(i))}</li>`).join("")}</ul></div>` : "";
  const approved = a && a.subject_sha256 === subject;
  $("#tab").innerHTML = card("全文总结", `<div class="card-body">
      ${subject ? "" : `<div class="alert alert-danger">总结已过期（资料、阅读或提纲已变更），需要重新生成。</div>`}
      ${issues}<p class="quote">${esc(s.overall_summary)}</p><hr>${sections}</div>`,
      `<a class="btn btn-sm" href="${url("/confirmation-draft")}"><i class="ti ti-download me-1"></i>内容确认稿</a>`)
    + card("客户内容确认", (approved ? `<div class="card-body"><div class="alert alert-success mb-0">已确认：${esc(a.customer)}（${esc(a.method)}），
        操作人 ${esc(a.operator)}，${time(a.at)}</div></div>` : subject && !s.pending_issues.length ? approvalForm("approve-content", subject, "记录客户已确认内容")
        : empty("当前不能确认：需先有当前版本的总结并处理全部待解决问题。")));
  bindApproval("approve-content", "content", subject);
}

async function tabFacts() {
  const data = await optional(`/workflows/${wid()}/facts`);
  if (!data) { $("#tab").innerHTML = card("事实库", empty("尚无事实库。客户确认内容后，在“执行端任务”中加入“事实库”。")); return; }
  const rows = data.facts.map((f) => `<tr class="${f.status === "REJECTED" ? "table-danger" : ""}">
      <td class="mono">${esc(f.id)}</td>
      <td>${f.status === "ACCEPTED" ? badge("通过", "green") : badge("拒绝", "red")}${f.needs_confirmation ? " " + badge("待确认", "orange") : ""}</td>
      <td><div>${esc(f.display || f.quote)}</div>${f.display && f.display !== f.quote ? `<div class="text-secondary small quote">原文：${esc(f.quote)}</div>` : ""}
        ${f.problems.length ? `<div class="text-danger small">${f.problems.map(esc).join("；")}</div>` : ""}</td>
      <td class="small">${esc(f.location)}</td><td class="small">${esc(f.derivation)}</td></tr>`).join("");
  const ders = data.derivations.map((d) => `<tr><td class="mono">${esc(d.id)}</td><td>${esc(d.claim)}</td><td class="small">${esc(d.rule)}</td>
      <td class="small mono">${esc(d.evidence.join(", "))}</td>
      <td>${d.confirmed ? badge("已确认", "green") : d.rejected ? badge("已否定", "red") : badge("待确认", "orange")}</td></tr>`).join("");
  const accepted = data.facts.filter((f) => f.status === "ACCEPTED").length;
  $("#tab").innerHTML = card(`事实库 <span class="text-secondary small">${accepted} 通过 / ${data.facts.length} 条</span>`,
      `<div class="card-body border-bottom small text-secondary">编写：${esc(data.author)} · ${time(data.at)} ${data.current ? "" : badge("已过期", "red")}
        ${data.terms.length ? `<br>项目术语：${data.terms.map(esc).join("、")}` : ""}</div>
      <div class="table-responsive"><table class="table card-table table-fixed">
      <colgroup><col style="width:9rem"><col style="width:8rem"><col><col style="width:22%"><col style="width:6rem"></colgroup>
      <thead><tr><th>ID</th><th>状态</th><th>显示文字 / 引文</th><th>位置</th><th>推导</th></tr></thead><tbody>${rows}</tbody></table></div>`,
      `<a class="btn btn-sm" href="${url("/facts/report")}" target="_blank"><i class="ti ti-file-text me-1"></i>核对报告</a>`)
    + (ders ? card("推导（需人工确认）", `<div class="table-responsive"><table class="table card-table">
      <thead><tr><th>ID</th><th>结论</th><th>规则</th><th>依据</th><th>状态</th></tr></thead><tbody>${ders}</tbody></table></div>`) : "");
}

async function tabDeck() {
  const chk = await optional(`/workflows/${wid()}/deck/check`);
  if (!chk) { $("#tab").innerHTML = card("页面规格", empty("尚无页面规格。事实库建立后，在“执行端任务”中加入“页面规格”。")); return; }
  const byId = Object.fromEntries(chk.pages.map((p) => [p.id, p]));
  const rows = chk.layouts.map((l, i) => {
    const p = byId[l.id] || { facts: [], pending: [], errors: [] };
    return `<tr><td>${i + 1}</td><td class="mono">${esc(l.id)}</td><td>${esc(l.layout)}</td><td>${p.facts.length}</td>
      <td>${p.pending.length ? badge(p.pending.length, "orange") : "0"}</td>
      <td class="small">${esc(l.outline_ids.join(", "))}</td>
      <td class="small text-danger">${p.errors.map(esc).join("；")}</td></tr>`;
  }).join("");
  const cov = chk.coverage || { outline: [], sections: [], omissions: [] };
  const omitted = Object.fromEntries((cov.omissions || []).map((o) => [o.section_id, o.reason]));
  const covRow = (label, x) => `<tr><td class="small">${esc(label)}</td><td>${(x.pages || []).length ? esc(x.pages.join(", "))
      : omitted[x.section_id] ? `<span class="small text-secondary">未上页，原因：${esc(omitted[x.section_id])}</span>` : `<span class="text-danger">未覆盖</span>`}</td></tr>`;
  $("#tab").innerHTML = card(`页面规格 ${chk.errors ? badge(`${chk.errors} 处错误`, "red") : badge("核对通过", "green")} ${chk.current ? "" : badge("已过期", "red")}`,
      `${chk.deck_errors.length || chk.warnings.length ? `<div class="card-body border-bottom">
        ${chk.deck_errors.map((e) => `<div class="text-danger">${esc(e)}</div>`).join("")}
        ${chk.warnings.map((e) => `<div class="text-warning">${esc(e)}</div>`).join("")}</div>` : ""}
      <div class="table-responsive"><table class="table card-table table-vcenter">
      <thead><tr><th>#</th><th>页</th><th>版式</th><th>事实</th><th>待确认</th><th>提纲</th><th>错误</th></tr></thead><tbody>${rows}</tbody></table></div>`)
    + `<div class="row g-3"><div class="col-md-6">${card("提纲覆盖", `<table class="table card-table table-sm"><tbody>
        ${cov.outline.map((x) => covRow(x.text, x)).join("") || "<tr><td>无提纲</td></tr>"}</tbody></table>`)}</div>
      <div class="col-md-6">${card("总结章节覆盖", `<table class="table card-table table-sm"><tbody>
        ${cov.sections.map((x) => covRow(x.title, x)).join("")}</tbody></table>`)}</div></div>`;
}

async function tabConfirm() {
  const w = current;
  const data = await optional(`/workflows/${wid()}/confirmations`);
  const sr = w.semantic_review;
  let html = "";
  if (!data) html += card("人工确认", empty("尚无当前版本的页面规格。"));
  else {
    const items = data.pending.map((it, n) => {
      if (it.kind === "derivation") return `<div class="card-body border-bottom"><div class="mb-1">${badge("推导", "purple")} <span class="mono">${esc(it.id)}</span>
          · 用于 ${esc(it.facts.join(", "))}</div><div><b>${esc(it.claim)}</b></div><div class="small text-secondary">规则：${esc(it.rule)} · 依据：${esc(it.evidence.join(", "))}</div>
        <form data-der="${esc(it.id)}" class="d-flex gap-2 mt-2 flex-wrap"><input name="note" class="form-control form-control-sm" style="max-width:24rem" placeholder="备注">
          <button class="btn btn-sm btn-success" name="d" value="CONFIRM">确认成立</button><button class="btn btn-sm btn-danger" name="d" value="REJECT">否定</button></form></div>`;
      if (it.kind === "conflict") return `<div class="card-body border-bottom"><div class="mb-1">${badge("冲突", "red")} ${esc(it.entity)} · ${esc(it.attribute)}</div>
        <form data-conflict="${n}" class="mt-1">${Object.entries(it.values).map(([val, ids]) => ids.map((fid) =>
          `<label class="form-check"><input class="form-check-input" type="radio" name="fact_id" value="${esc(fid)}" required>
           <span class="form-check-label">${esc(val)} <span class="mono text-secondary">${esc(fid)}</span></span></label>`).join("")).join("")}
          <div class="d-flex gap-2 mt-1"><input name="note" class="form-control form-control-sm" style="max-width:24rem" placeholder="裁定理由">
          <button class="btn btn-sm btn-primary">采用所选事实</button></div></form></div>`;
      return `<div class="card-body border-bottom"><div class="mb-1">${badge("图表转录", "orange")} <span class="mono">${esc(it.id)}</span> · ${esc(it.location)}</div>
        <div class="small text-secondary">${esc(it.reason)}</div>
        <div class="small">第一次：<span class="quote">${esc(it.text)}</span>${it.second_read ? `<br>第二次：<span class="quote">${esc(it.second_read.text ?? JSON.stringify(it.second_read))}</span>` : ""}</div>
        <form data-unit="${esc(it.id)}" class="mt-2"><textarea name="text" class="form-control form-control-sm mb-1" rows="2" required>${esc(it.text)}</textarea>
          <label class="form-check"><input class="form-check-input" type="checkbox" name="checked" required><span class="form-check-label">我已对照原件逐字核对</span></label>
          <button class="btn btn-sm btn-primary">确认转录文字</button></form></div>`;
    }).join("");
    html += card(`人工确认 ${data.pending.length ? badge(`${data.pending.length} 项待处理`, "orange") : badge("无待处理", "green")}`,
      items || empty("页面用到的推导、冲突和图表转录都已确认。"));
  }
  if (sr) {
    const rows = sr.issues.map((i) => {
      const d = sr.dismissed[i.id];
      return `<tr><td class="mono">${esc(i.id)}</td><td>${i.severity === "BLOCKER" ? badge("阻断", "red") : badge("提示", "secondary")}</td>
        <td>${esc(i.problem)}${i.ref ? `<div class="small text-secondary">${esc(i.ref)}</div>` : ""}</td>
        <td>${d ? `<span class="small">已驳回：${esc(d.reason)}（${esc(d.reviewer)}）</span>` : i.severity === "BLOCKER"
          ? `<form data-dismiss="${esc(i.id)}" class="d-flex gap-1"><input name="reason" class="form-control form-control-sm" placeholder="驳回理由" required>
             <button class="btn btn-sm">驳回</button></form>` : ""}</td></tr>`;
    }).join("");
    html += card(`独立语义审查 <span class="text-secondary small">${esc(sr.reviewer)} · ${time(sr.at)}</span>`,
      rows ? `<div class="card-body border-bottom small text-secondary">只有确认问题不成立时才驳回；成立的问题应修订事实库或页面规格。</div>
        <div class="table-responsive"><table class="table card-table"><thead><tr><th>ID</th><th>级别</th><th>问题</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`
        : empty("审查未报告问题。"));
  } else html += card("独立语义审查", empty("尚无语义审查。在“执行端任务”中加入“独立语义审查”（须由不同执行端完成）。"));
  $("#tab").innerHTML = html;

  document.querySelectorAll("form[data-der]").forEach((f) => f.onsubmit = (ev) => {
    ev.preventDefault();
    act(() => api("POST", `/workflows/${wid()}/confirmations/derivations/${encodeURIComponent(f.dataset.der)}`,
      { reviewer: me(), decision: ev.submitter.value, note: f.note.value }), "已记录");
  });
  document.querySelectorAll("form[data-conflict]").forEach((f) => f.onsubmit = (ev) => {
    ev.preventDefault();
    const it = data.pending[Number(f.dataset.conflict)];
    act(() => api("POST", `/workflows/${wid()}/confirmations/conflicts`,
      { reviewer: me(), entity: it.entity, attribute: it.attribute, fact_id: f.fact_id.value, note: f.note.value }), "已裁定");
  });
  document.querySelectorAll("form[data-unit]").forEach((f) => f.onsubmit = (ev) => {
    ev.preventDefault();
    act(() => api("POST", `/workflows/${wid()}/confirmations/transcriptions/${encodeURIComponent(f.dataset.unit)}`,
      { reviewer: me(), text: f.text.value, original_checked: f.checked.checked }), "转录已确认");
  });
  document.querySelectorAll("form[data-dismiss]").forEach((f) => f.onsubmit = (ev) => {
    ev.preventDefault();
    act(() => api("POST", `/workflows/${wid()}/semantic-review/issues/${encodeURIComponent(f.dataset.dismiss)}/dismiss`,
      { reviewer: me(), reason: f.reason.value }), "已驳回");
  });
}

function reviewState(w, p) {
  const r = w.page_reviews[p.id];
  if (!r || r.png_sha256 !== p.sha256) return ["未审核", "secondary"];
  return r.visual_status === "PASS" && r.content_status === "PASS" ? ["通过", "green"] : ["需修改", "red"];
}

function tabRender() {
  const w = current, r = w.render, d = w.draft_render;
  const summary = (x) => x ? `<div class="small text-secondary">${time(x.at)} · 硬错误 ${x.hard_errors} ·
      ${Object.entries(x.summary).map(([k, v]) => `${esc(k)} ${v}`).join(" · ")}</div>` : "";
  const files = (x, kind) => x ? ["deck.pptx", "deck.pdf", "deck.html", "render_report.json"].map((n) =>
      `<a class="btn btn-sm" href="${url(`/render/${kind}/${n}`)}" target="_blank">${n}</a>`).join(" ") : "";
  let gallery = "";
  if (r) {
    gallery = `<div class="row row-cards">${r.pages.map((p, i) => {
      const [label, color] = reviewState(w, p), rev = w.page_reviews[p.id];
      return `<div class="col-md-6 col-xl-4"><div class="card">
        <a href="${url(`/render/final/${p.file}`)}?v=${short(p.sha256)}" target="_blank"><img class="slide-thumb" loading="lazy" alt="${esc(p.id)}"
          src="${url(`/render/final/${p.file}`)}?v=${short(p.sha256)}"></a>
        <div class="card-body p-2"><div class="d-flex justify-content-between align-items-center mb-1">
          <span><b>${i + 1}</b> <span class="mono">${esc(p.id)}</span>${i < 5 ? " " + badge("样页", "azure") : ""}</span>${badge(label, color)}</div>
          ${rev && rev.feedback ? `<div class="small text-secondary mb-1">${esc(rev.feedback)}</div>` : ""}
          <form data-review="${esc(p.id)}" data-sha="${esc(p.sha256)}">
            <div class="d-flex gap-2 small mb-1"><select name="visual" class="form-select form-select-sm"><option value="PASS">版面通过</option><option value="REVISE">版面需修改</option></select>
              <select name="content" class="form-select form-select-sm"><option value="PASS">内容通过</option><option value="REVISE">内容需修改</option></select></div>
            <input name="feedback" class="form-control form-control-sm mb-1" placeholder="意见">
            <label class="form-check small mb-1"><input class="form-check-input" type="checkbox" name="checked" required>
              <span class="form-check-label">已对照备注中的来源位置核对</span></label>
            <button class="btn btn-sm btn-primary w-100">记录审核</button></form></div></div></div>`;
    }).join("")}</div>`;
  }
  const subject = w.approval_subjects.style, a = w.style_approval;
  const styleDone = a && a.subject_sha256 === subject;
  const samplesOk = r && r.pages.slice(0, 5).every((p) => reviewState(w, p)[0] === "通过");
  $("#tab").innerHTML =
    card("渲染", `<div class="card-body">
      <div class="d-flex gap-2 flex-wrap mb-2">
        <button class="btn btn-primary" id="render-final"><i class="ti ti-player-play me-1"></i>正式渲染</button>
        <button class="btn" id="render-draft">草稿渲染</button></div>
      <div class="form-hint mb-2">渲染由代码完成（HTML → PNG/PDF/原生 PPTX 并回读核对）。草稿可带待确认标记，不能用于审核。</div>
      ${r ? `<div class="mb-2"><b>正式版</b> <span class="mono small">${short(r.input_sha256)}</span> ${r.hard_errors ? badge("有硬错误", "red") : ""} ${files(r, "final")}${summary(r)}</div>` : ""}
      ${d ? `<div><b>草稿</b> <span class="mono small">${short(d.input_sha256)}</span> ${files(d, "draft")}${summary(d)}</div>` : ""}</div>`)
    + (r ? card("客户风格确认（前5页）", styleDone ? `<div class="card-body"><div class="alert alert-success mb-0">已确认：${esc(a.customer)}（${esc(a.method)}），${time(a.at)}</div></div>`
        : subject && samplesOk ? approvalForm("approve-style", subject, "记录客户已确认样页风格") : empty("前5页全部审核通过后才能记录风格确认。")) : "")
    + (r ? card("逐页审核", `<div class="card-body">${gallery}</div>`) : "");
  $("#render-final").onclick = () => act(() => api("POST", `/workflows/${wid()}/render`), "正式渲染完成");
  $("#render-draft").onclick = () => act(() => api("POST", `/workflows/${wid()}/render?draft=true`), "草稿渲染完成");
  bindApproval("approve-style", "style", subject);
  document.querySelectorAll("form[data-review]").forEach((f) => f.onsubmit = (ev) => {
    ev.preventDefault();
    act(() => api("POST", `/workflows/${wid()}/pages/${encodeURIComponent(f.dataset.review)}/review`, {
      reviewer: me(), png_sha256: f.dataset.sha, sources_checked: f.checked.checked,
      visual_status: f.visual.value, content_status: f.content.value, feedback: f.feedback.value }), `已记录 ${f.dataset.review}`);
  });
}

async function tabDelivery() {
  const w = current;
  const audit = await api("GET", `/workflows/${wid()}/audit`);
  const names = ["deck.pptx", "deck.pdf", "facts_report.md", "verification_report.json", "delivery.zip"];
  const rows = [...w.deliveries].reverse().map((d) => `<tr><td>v${String(d.version).padStart(3, "0")}</td><td class="text-secondary">${time(d.at)}</td>
      <td>${names.map((n) => `<a class="btn btn-sm" href="${url(`/deliveries/${d.version}/${n}`)}">${n}</a>`).join(" ")}</td></tr>`).join("");
  $("#tab").innerHTML = card("交付", `<div class="card-body border-bottom">
      <button class="btn btn-success" id="export" ${["READY_TO_EXPORT", "DELIVERED"].includes(w.stage) ? "" : "disabled"}>
        <i class="ti ti-package-export me-1"></i>生成交付包</button>
      <span class="form-hint ms-2">全部页面审核通过、内容与风格均已确认后可交付。</span></div>
    ${rows ? `<div class="table-responsive"><table class="table card-table"><tbody>${rows}</tbody></table></div>` : empty("尚无交付版本。")}`)
    + card("审计记录", `<div class="table-responsive" style="max-height:28rem"><table class="table card-table table-sm">
      <thead><tr><th>#</th><th>时间</th><th>事件</th><th>详情</th></tr></thead><tbody>
      ${[...audit].reverse().map((e) => `<tr><td>${e.sequence}</td><td class="text-secondary">${time(e.at)}</td><td>${esc(e.event)}</td>
        <td class="mono">${esc(short(e.details))}</td></tr>`).join("")}</tbody></table></div>`);
  $("#export").onclick = () => act(() => api("POST", `/workflows/${wid()}/export`), "交付包已生成");
}

// ------------------------------------------------------------ start
(async () => {
  try { health = await api("GET", "/health"); } catch (e) { flash("无法连接服务：" + e.message); }
  route();
})();
