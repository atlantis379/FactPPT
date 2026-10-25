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
  ["论断清单", ["CLAIMS_REQUIRED"]],
  ["总结", ["SUMMARY_REQUIRED"]],
  ["总结审查", ["SUMMARY_REVIEW_REQUIRED", "SUMMARY_ISSUES"]],
  ["内容确认", ["CONTENT_CONFIRMATION"]],
  ["事实库", ["FACTS_REQUIRED"]],
  ["页面规格", ["DECK_REQUIRED", "DECK_REVISION"]],
  ["确认与审查", ["CONFIRMATIONS_REQUIRED", "SEMANTIC_REVIEW_REQUIRED", "SEMANTIC_ISSUES"]],
  ["生成", ["RENDER_REQUIRED", "GENERATION_RUNNING", "GENERATION_FAILED"]],
  ["样页审核", ["SAMPLES_REVIEW"]],
  ["风格确认", ["STYLE_CONFIRMATION"]],
  ["逐页审核", ["PAGE_REVIEW"]],
  ["交付", ["READY_TO_EXPORT", "DELIVERED"]],
];
const STAGE_LABEL = {
  READING_REQUIRED: "待阅读资料", CLAIMS_REQUIRED: "待列论断清单", SUMMARY_REQUIRED: "待全文总结",
  SUMMARY_AMEND_RUNNING: "答复处理中", SUMMARY_REVIEW_REQUIRED: "待独立总结审查", SUMMARY_ISSUES: "总结审查有阻断问题", CONTENT_CONFIRMATION: "待客户确认内容",
  FACTS_REQUIRED: "待建立事实库", DECK_REQUIRED: "待编写页面规格", DECK_REVISION: "页面规格需修订",
  CONFIRMATIONS_REQUIRED: "待人工确认", SEMANTIC_REVIEW_REQUIRED: "待独立语义审查", SEMANTIC_ISSUES: "语义审查有阻断问题",
  RENDER_REQUIRED: "待正式渲染", SAMPLES_REVIEW: "待审核前5页", STYLE_CONFIRMATION: "待客户确认风格",
  GENERATION_RUNNING: "A 原生矢量生成中", GENERATION_FAILED: "生成需处理",
  PAGE_REVIEW: "待逐页审核", READY_TO_EXPORT: "可交付", DELIVERED: "已交付",
  PARTIAL_READY: "本次部分页面已完成审核",
};
const KIND_LABEL = {
  READ_SOURCE: "阅读资料", SECOND_READ: "第二次独立转录/截取", CLAIMS: "论断清单", SUMMARY: "全文总结",
  SUMMARY_AMEND: "处理人工答复（局部修订）", SUMMARY_REVIEW: "独立总结审查",
  FACTS: "事实库", DECK: "页面规格", SEMANTIC_REVIEW: "独立语义审查",
  VISUAL_DESIGN: "完整设计稿", VISUAL_LAYOUT: "版面拆解", VISUAL_CLEAN: "去字与图形分离", VISUAL_VECTOR: "图形矢量化", VISUAL_CRITIQUE: "版面评审",
};
const TABS = [
  ["overview", "项目与需求", "ti-settings"], ["templates", "选择模板", "ti-palette"], ["sources", "资料", "ti-files"], ["tasks", "执行端任务", "ti-list-check"],
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
    document.querySelectorAll('[data-unsaved="true"]').forEach(el=>delete el.dataset.unsaved);
    await route();
  } catch (e) { flash(e.message); }
}
function badge(text, color) { return `<span class="badge bg-${color}-lt">${esc(text)}</span>`; }
function stageBadge(stage) {
  const color = stage === "DELIVERED" ? "green" : stage === "READY_TO_EXPORT" ? "teal" : /REVISION|ISSUES|FAILED/.test(stage) ? "red" : "blue";
  return badge(STAGE_LABEL[stage] || stage, color);
}
function card(title, body, extra = "") {
  const human = /客户.*确认|逐页审核|人工确认|选择PPT风格|学术原生模板库|项目与需求|客户模板|新建项目/.test(title);
  const executor = /独立总结审查|执行端任务|事实库|页面规格/.test(title);
  const reference = /全文总结|对照原始资料/.test(title);
  const tag = human ? badge("需要你操作", "blue") : executor ? badge("执行端处理 · 可查看", "secondary") : reference ? badge("供你查看", "secondary") : "";
  title += tag ? `<span class="ms-2 small">${tag}</span>` : "";
  return `<div class="card mb-3"><div class="card-header"><h3 class="card-title">${title}</h3>${extra ? `<div class="card-actions">${extra}</div>` : ""}</div>${body}</div>`;
}
function empty(text) { return `<div class="card-body text-secondary">${esc(text)}</div>`; }
function wid() { return current.id; }
function url(path) { return `${API}/workflows/${encodeURIComponent(wid())}${path}`; }

// ------------------------------------------------------------ source figures
const DEID_LABEL = { NO_PATIENT_CONTENT: "无患者内容", DEIDENTIFIED: "已去标识", IDENTIFIABLE: "含可识别信息" };
function figUrl(fid) { return url(`/figures/${encodeURIComponent(fid)}/file`); }
function figureInfo(w, fid) {
  const g = w.sources.flatMap((s) => s.figures || []).find((x) => x.id === fid);
  if (!g) return null;
  const page = w.sources.flatMap((s) => s.pages).find((p) => p.id === g.page_id);
  const rev = (w.confirmations.figures || {})[fid], lic = (w.confirmations.figure_licenses || {})[fid];
  return { g, reading: page && page.reading && page.reading.figures ? page.reading.figures[fid] : null,
           review: rev && rev.figure_sha256 === g.sha256 ? rev : null, licence: lic && lic.figure_sha256 === g.sha256 ? lic : null };
}
function figureBadges(info) {
  const r = info.review, l = info.licence;
  return [r ? badge(DEID_LABEL[r.deidentified], r.deidentified === "IDENTIFIABLE" ? "red" : "green") : badge("待截取/去标识确认", "orange"),
          l ? badge(l.permitted ? "已许可" : "未许可", l.permitted ? "green" : "red") : badge("待登记许可", "orange"),
          info.reading && info.reading.may_contain_patient_info ? badge("可能含患者信息", "red") : ""].join(" ");
}
function cropBox(b, style) {
  return `<div style="position:absolute;left:${b[0] * 100}%;top:${b[1] * 100}%;width:${(b[2] - b[0]) * 100}%;height:${(b[3] - b[1]) * 100}%;${style}"></div>`;
}
// the whole original page with the crop box (solid) and the independent second box (dashed)
function cropView(it, height = 320) {
  const sr = it.second_read;
  return `<a href="${it.page_image_url}" target="_blank" style="position:relative;display:inline-block;height:${height}px">
      <img src="${it.page_image_url}" alt="原页" loading="lazy" style="height:100%;border:1px solid var(--tblr-border-color)">
      ${cropBox(it.bbox, "border:2px solid #d63939")}${sr ? cropBox(sr.bbox, "border:2px dashed #206bc4") : ""}</a>
    <div class="small text-secondary mt-1"><span style="color:#d63939">实线</span>：截取区域
      ${sr ? `· <span style="color:#206bc4">虚线</span>：第二次独立截取（交并比 ${sr.iou}）` : "· 尚无第二次独立截取"}</div>`;
}
function figureThumb(fid, height = 120) {
  return `<a href="${figUrl(fid)}" target="_blank"><img src="${figUrl(fid)}" alt="${esc(fid)}" loading="lazy"
    style="max-width:100%;height:${height}px;object-fit:contain;background:var(--tblr-bg-surface-secondary)"></a>`;
}

// ------------------------------------------------------------ routing
let renderedHash = location.hash;
window.addEventListener("hashchange", () => {
  if(document.querySelector('[data-unsaved="true"]') && !confirm("有尚未保存的修改，离开此页面将丢失这些修改。是否离开？")) {
    history.replaceState(null,"",renderedHash || "#/");return;
  }
  route();
});
window.addEventListener("beforeunload",ev=>{
  if(document.querySelector('[data-unsaved="true"]')) {ev.preventDefault();ev.returnValue="";}
});
async function route() {
  clearTimeout(workbenchPoll);
  clearTimeout(generationPoll);
  renderedHash=location.hash;
  if(location.hash==='#/templates') {
    current=null;
    try { $('#view').innerHTML='<div class="page-header mb-3"><a href="#/">返回项目列表</a><h2 class="page-title mt-2">10套学术模板</h2><div class="text-secondary mt-2">先查看与下载，进入项目的“要求与模板”后选择使用。</div></div>'+academicTemplateChooser({},await api('GET','/templates')); bindAcademicTemplates(); }
    catch(e){$('#view').innerHTML='<div class="alert alert-danger">'+esc(e.message)+'</div>';}
    return;
  }
  const [, id, tab] = (location.hash.replace(/^#\/?/, "").match(/^w\/([^/]+)\/?(\w*)/) || []);
  try {
    if (!id) { current = null; return renderList(); }
    current = await api("GET", `/workflows/${encodeURIComponent(id)}`);
    await renderWorkflow(tab || workbenchDefault(current));
  } catch (e) { $("#view").innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div><a href="#/">返回项目列表</a>`; }
}

// ------------------------------------------------------------ project list
async function renderList() {
  const list = await api("GET", "/workflows");
  const themes = health.themes.map((t) => `<option>${esc(t)}</option>`).join("");
  $("#view").innerHTML = `
    <div class="page-header mb-3"><div class="page-pretitle">本机PPT工作台</div><h2 class="page-title">我的PPT项目</h2><div class="text-secondary mt-2">上传原始材料，确认内容与风格，生成可编辑的PPT。</div></div>
    ${card("从这里开始", '<div class="card-body"><b>已有项目：</b>点击下方项目入口，先看“当前进展与下一步”。<br><b>新项目：</b>右侧填写名称和要求创建项目 → 上传资料 → 选择模板 → 内容复核 → 生成与审核 → 下载交付。<div class="text-secondary small mt-2">你负责要求、确认和逐页审核；Codex执行端负责内容与设计任务。已排队表示等待领取，不代表模型正在运行。</div></div>')}
    <div class="row g-3">
      <div class="col-lg-7">${card("全部项目", list.length ? `<div class="table-responsive"><table class="table table-vcenter card-table">
        <thead><tr><th>名称</th><th>阶段</th><th>资料</th><th>页数</th><th>下一步</th><th>更新</th></tr></thead><tbody>
        ${list.map((w) => `<tr><td><a href="#/w/${esc(w.id)}">${esc(w.title)}</a></td><td>${stageBadge(w.stage)}</td>
          <td>${w.sources}</td><td>${w.pages}</td><td><div class="mb-1">${badge(responsibility(w).label,responsibility(w).kind==="user"?"blue":"secondary")}</div><div class="small mb-2">${esc(stageGuide(w).text)}</div><a class="btn btn-sm btn-primary" href="#/w/${esc(w.id)}/${stageGuide(w).target}">${responsibility(w).kind==="executor"?"查看进展":"前往处理"}</a></td><td class="text-secondary">${time(w.updated_at)}</td></tr>`).join("")}
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
      location.hash = `#/w/${w.id}/sources`;
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
  $("#view").innerHTML = workbenchHeader(w, tab) + '<div id="tab"></div>';
  const views = { overview: tabOverview, templates: tabTemplates, sources: tabSources, tasks: tabTasks, summary: tabSummary, facts: tabFacts,
                  deck: tabDeck, confirm: tabConfirm, render: tabRender, delivery: tabDelivery };
  await (views[tab] || tabOverview)();
  bindWorkbench(w, tab);
  document.querySelectorAll("form input,form textarea,form select").forEach(el=>el.addEventListener("input",()=>el.form.dataset.unsaved="true"));
}

// ------------------------------------------------------------ tabs
async function tabOverview() {
  const w = current;
  const themes = health.themes.map((t) => `<option ${t === w.theme ? "selected" : ""}>${esc(t)}</option>`).join("")
    + (w.brand ? `<option value="brand" ${w.theme === "brand" ? "selected" : ""}>客户模板（${esc(w.brand.filename)}）</option>` : "");
  $("#tab").innerHTML = card("PPT模板", `<div class="card-body"><div class="fw-bold mb-2">${esc(w.visual_template?.name || '尚未选择学术模板')}</div><p>在独立页面预览并选择学术模板；已保存的内容确认继续保留。</p><a class="btn btn-primary" href="#/w/${esc(w.id)}/templates">进入选择模板页面</a></div>`)+card("项目与需求", `<form id="settings" class="card-body">
      <div class="form-hint mb-2">${w.generation_route === "TEMPLATE_LIB" ? "PPT 正式生成采用固定模板库：选版式器按内容选版式，程序生成原生可编辑 PPTX，并附逐页溯源报告。" : "本项目采用 A 原生矢量方案（已于 2026-10-25 停用，仅供已有项目）：完整设计稿 → 去字 → 矢量化 → 原生文字与图形。"}</div>
      <div class="alert alert-warning">修改提纲或需求会使总结、事实库或页面规格失效，需要重新生成和确认。</div>
      <div class="mb-3"><label class="form-label">名称</label><input name="title" class="form-control" value="${esc(w.title)}"></div>
      <div class="mb-3"><label class="form-label">教学提纲（每行一条）</label>
        <textarea name="outline" class="form-control" rows="6">${esc(w.outline.map((o) => o.text).join("\n"))}</textarea></div>
      ${requirementFields(w.requirements)}
      <div class="mb-3"><label class="form-label">配色</label><select name="theme" class="form-select">${themes}</select></div>
      <button class="btn btn-primary">保存</button></form>`)+`<details class="mb-3"><summary class="card card-body">辅助配色与自定义模板</summary>${templateChooser(w)}${brandCard(w)}</details>`;
  $("#settings").onsubmit = (ev) => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    act(() => api("PATCH", `/workflows/${wid()}`, { title: f.get("title"), outline: f.get("outline"), theme: f.get("theme"), requirements: readRequirements(f) }), "已保存");
  };
  bindBrand();
  bindTemplateChooser();
}

async function tabTemplates() {
  const w = current;
  const templates = await api('GET','/templates');
  $("#tab").innerHTML = `<div class="page-header mb-3"><h2 class="page-title">选择PPT模板</h2><p class="text-secondary mt-2">先查看正文、流程和表格样页，再选择适合本课件的设计。选择只更新视觉要求，不替代内容确认。</p></div>`
    + academicTemplateChooser(w,templates)
    + `<div class="btn-list mb-3"><a class="btn" href="#/w/${esc(w.id)}/overview">返回生成要求</a><a class="btn btn-outline-primary" href="#/w/${esc(w.id)}/${esc(workbenchDefault(w))}">返回当前处理步骤</a></div>`;
  bindAcademicTemplates();
}

const TOKEN_LABEL = { primary: "主色", primary2: "主色2", accent: "强调", accent2: "强调2", "accent-on-dark": "深底强调",
                      ink: "正文", muted: "次要文字", soft: "浅底", sky: "底色", line: "分隔线" };
function swatch(color, label) {
  return `<div class="text-center" style="width:5.5rem"><div style="height:2.2rem;border-radius:6px;border:1px solid var(--tblr-border-color);background:${esc(color)}"></div>
    <div class="small">${esc(label)}</div><div class="mono">${esc(color)}</div></div>`;
}
function brandCard(w) {
  const b = w.brand;
  const upload = (id, accept, label) => `<form id="${id}" class="d-flex gap-2 flex-wrap mb-2"><input type="file" name="file" class="form-control" style="max-width:24rem" accept="${accept}" required>
    <button class="btn">${label}</button></form>`;
  if (!b) return card("客户模板", `<div class="card-body">${upload("brand-template", ".pptx,.potx", "导入模板")}
    <div class="form-hint">从客户的 PowerPoint 模板读取配色和字体，只改变外观；文字、版式和核对规则不变。颜色会按对比度要求自动调整，原色一并记录。</div></div>`);
  const orig = Object.entries(b.template_colors || {}).filter(([k]) => /accent|dk|lt/.test(k)).map(([k, v]) => swatch(v, k)).join("");
  return card(`客户模板 <span class="text-secondary small">${esc(b.filename)}</span>${w.theme === "brand" ? " " + badge("使用中", "green") : ""}`,
    `<div class="card-body">
      <div class="mb-2 small text-secondary">实际使用的配色（已按对比度调整）：主色/白 ${b.contrast.primary_on_white}，强调/白 ${b.contrast.accent_on_white}，
        深底强调 ${b.contrast.accent_on_dark}，正文/白 ${b.contrast.ink_on_white}</div>
      <div class="d-flex flex-wrap gap-2 mb-3">${Object.entries(b.tokens).map(([k, v]) => swatch(v, TOKEN_LABEL[k] || k)).join("")}</div>
      <details class="mb-3"><summary class="small">模板原色</summary><div class="d-flex flex-wrap gap-2 mt-2">${orig}</div></details>
      <div class="mb-3 small">正文字体：<b>${esc(b.font || "（模板未指定，使用微软雅黑）")}</b>
        <span class="text-secondary">渲染机未安装该字体时会改用微软雅黑，并在渲染结果中提示。</span></div>
      <div class="row g-3"><div class="col-md-6"><div class="form-label">标志（可选，显示在内容页右上角）</div>
        ${b.logo ? `<img src="${url("/brand/logo")}?v=${short(b.logo.sha256)}" alt="logo" style="max-height:48px;max-width:200px" class="mb-2 d-block">` : ""}
        ${upload("brand-logo", ".png,.jpg,.jpeg", b.logo ? "更换标志" : "上传标志")}</div>
      <div class="col-md-6"><div class="form-label">更换模板</div>${upload("brand-template", ".pptx,.potx", "重新导入")}
        <button class="btn btn-ghost-danger btn-sm" id="brand-remove">移除客户模板</button></div></div>
    </div>`);
}
function bindBrand() {
  const up = (id, path, ok) => { const f = $("#" + id); if (!f) return; f.onsubmit = (ev) => {
    ev.preventDefault();
    const fd = new FormData(); fd.append("file", ev.target.file.files[0]);
    act(() => api("POST", `/workflows/${wid()}${path}`, fd), ok);
  }; };
  up("brand-template", "/brand/template", "已导入客户模板，配色已切换为客户模板；需要重新渲染");
  up("brand-logo", "/brand/logo", "标志已更新；需要重新渲染");
  const rm = $("#brand-remove");
  if (rm) rm.onclick = () => { if (confirm("移除客户模板？配色将恢复为默认。")) act(() => api("DELETE", `/workflows/${wid()}/brand`), "已移除"); };
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
    + (w.sources.some((s) => (s.figures || []).length) ? card("原件图片", `<div class="card-body"><div class="row row-cards">
      ${w.sources.flatMap((s) => (s.figures || []).map((g) => {
        const info = figureInfo(w, g.id);
        return `<div class="col-sm-6 col-lg-3"><div class="card card-sm"><div class="text-center p-2">${figureThumb(g.id)}</div>
          <div class="card-body"><div class="mono small">${esc(g.id)}</div><div class="small">${esc(s.filename)} · ${esc(g.location)}</div>
          <div class="small text-secondary">${g.width}×${g.height}px · ${g.method === "page_crop" ? `页面截取 ${g.dpi} dpi` : "原件内嵌"}</div>
          ${info.reading ? `<div class="small mt-1">${esc(info.reading.note)}</div>` : `<div class="small text-secondary mt-1">尚未阅读</div>`}
          <div class="mt-1">${figureBadges(info)}</div></div></div></div>`;
      })).join("")}</div>
      <div class="form-hint mt-2">原件中的图由程序取出，像素未作修改。只有页面用到的图需要确认，确认在“人工确认”中进行。</div></div>`) : "")
    + (pagesList ? card("阅读页", `<div class="table-responsive" style="max-height:28rem"><table class="table card-table table-sm">
      <thead><tr><th>页</th><th>位置</th><th></th><th>状态</th></tr></thead><tbody>${pagesList}</tbody></table></div>`) : "");
  $("#upload").onsubmit = (ev) => {
    ev.preventDefault();
    const files = [...ev.target.file.files];
    if (!files.length) return flash("请选择文件");
    act(async () => {
      let last;
      const button=ev.target.querySelector("button"), id=wid();button.disabled=true;
      try { for (const [i,file] of files.entries()) { button.textContent=`正在导入 ${i+1}/${files.length}：${file.name}`;const fd = new FormData(); fd.append("file", file); last = await api("POST", `/workflows/${id}/sources`, fd); } }
      finally { button.disabled=false;button.textContent="导入"; }
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
  const buttons = Object.entries(KIND_LABEL).filter(([k]) => !["VISUAL_DESIGN", "VISUAL_LAYOUT", "VISUAL_CLEAN", "VISUAL_VECTOR"].includes(k)).map(([k, label]) =>
    `<button class="btn btn-sm" data-queue="${k}"><i class="ti ti-plus me-1"></i>${label}</button>`).join(" ");
  const color = { PENDING: "secondary", RUNNING: "blue", COMPLETE: "green", FAILED: "red", CANCELLED: "secondary" };
  const rows = [...w.tasks].reverse().map((t) => `<tr><td>${esc(KIND_LABEL[t.kind] || t.kind)}${t.brief?.regression ? `<div class="small text-secondary">${t.brief.regression.mode === "IMPACT" ? `局部复核 · ${t.brief.regression.affected.length} 页重新检查` : "全量复核"}<details><summary>范围与原因</summary>${esc(t.brief.regression.reason)}<br>${t.brief.regression.affected.map(esc).join("、")}</details></div>` : ""}</td><td class="mono">${esc(t.binding ?? "—")}</td>
      <td>${badge(t.status, color[t.status] || "secondary")}</td><td>${esc(t.worker ?? "—")}</td><td>${t.attempts}</td>
      <td class="text-secondary">${time(t.created_at)}</td><td class="small text-danger">${esc(t.error ?? "")}</td></tr>`).join("");
  $("#tab").innerHTML = card("执行端任务", `<div class="card-body border-bottom">
      <div class="d-flex flex-wrap gap-2">${buttons}</div>
      ${current && current.generation_route === "TEMPLATE_LIB" ? "" : '<div class="form-hint mt-2">设计稿、版面拆解、去字和矢量化由“渲染与审核”页的生成入口自动排队。</div>'}
      <div class="form-hint mt-2">任务由执行端领取完成：<code>python tools/codex_worker.py</code>。服务器会拒绝前置条件未满足的任务；
        语义审查和第二次转录须由不同的执行端身份完成。</div></div>
    ${w.tasks.length ? `<div class="table-responsive"><table class="table card-table table-vcenter">
      <thead><tr><th>类型</th><th>对象</th><th>状态</th><th>执行端</th><th>尝试</th><th>创建</th><th>错误</th></tr></thead><tbody>${rows}</tbody></table></div>`
      : empty("还没有任务。")}`);
  document.querySelectorAll("[data-queue]").forEach((b) => b.onclick = () =>
    act(() => api("POST", `/workflows/${wid()}/tasks`, { kind: b.dataset.queue }), `已加入：${KIND_LABEL[b.dataset.queue]}`));
}

const OPEN_STATUS = ["OPEN", "NEEDS_HUMAN", "RETAINED"];
const STATUS_LABEL = { OPEN: ["仍未解决", "red"], NEEDS_HUMAN: ["待您裁定", "orange"], RETAINED: ["依据不足保留", "yellow"],
  FIXED: ["已修复（独立复核）", "green"], HUMAN_RULED: ["已人工裁定", "secondary"] };
const CATEGORY_LABEL = { CONTENT_ERROR: "内容错误", EVIDENCE_MISSING: "来源证据缺失", EXPRESSION_AMBIGUITY: "表达歧义", HUMAN_DECISION: "人工决策" };
const statusBadge = (i) => badge(...(STATUS_LABEL[i.status] || [i.status || "—", "secondary"]));
const unresolved = (i) => OPEN_STATUS.includes(i.status);
function ledgerRows(issues, ruled, formAttr, editable) {
  const order = (i) => (unresolved(i) ? 0 : 1) * 10 + (i.status === "NEEDS_HUMAN" ? 0 : 1) * 5 + (i.severity === "BLOCKER" ? 0 : 1);
  return [...issues].sort((a, b) => order(a) - order(b)).map((i) => {
    const d = ruled[i.id];
    const meta = [i.check && i.check !== "SUMMARY" ? i.check : "", CATEGORY_LABEL[i.category] || "",
      i.source_ref ? "来源：" + i.source_ref : "", i.rounds > 1 ? `经过 ${i.rounds} 轮记录` : ""].filter(Boolean).map(esc).join(" · ");
    const locate = i.status !== "NEEDS_HUMAN" && formAttr === "data-sdismiss"
      ? `<button type="button" class="btn btn-sm mb-2" data-edit-summary="${esc(i.ref)}">定位并修订</button>` : "";
    const ruling = d ? `<span class="small">裁定：${esc(d.reason)}（${esc(d.reviewer)}）</span>` : editable && unresolved(i)
      ? `${locate}<details ${i.status === "NEEDS_HUMAN" ? "open" : ""}><summary class="small text-secondary">${i.status === "NEEDS_HUMAN" ? "填写您的裁定" : "问题不成立？填写裁定依据"}</summary>
         <form ${formAttr}="${esc(i.id)}" data-group-ids="${esc((i.group_ids || [i.id]).join(','))}" class="d-flex gap-1"><input name="reason" class="form-control form-control-sm" placeholder="裁定与依据" required>
         <button class="btn btn-sm">记录裁定</button></form></details>` : "";
    return `<tr><td class="mono" style="min-width:8rem"><span class="text-nowrap">${esc(i.id)}</span>${i.group_ids?.length > 1 ? `<div class="small">关联 ${i.group_ids.length} 条记录</div>` : ""}<div class="small text-secondary">${esc(i.ref || "")}</div></td>
      <td>${i.severity === "BLOCKER" ? badge("阻断", "red") : badge("提示", "secondary")}<div class="mt-1">${statusBadge(i)}</div></td>
      <td>${esc(i.problem)}<div class="small text-secondary">${meta}</div>${i.group_members ? `<details><summary>同一事项的全部记录与依据</summary>${i.group_members.map(x => `<p><b>${esc(x.id)}</b> ${esc(x.problem)}<br>来源：${esc(x.source_ref)}</p>`).join('')}<p>提交裁定将逐条记录到上述编号，历史记录保留。</p></details>` : ""}${i.suggestion ? `<div class="small">建议：${esc(i.suggestion)}</div>` : ""}</td>
      <td>${ruling}</td></tr>`;
  }).join("");
}

function approvalForm(id, subject, label) {
  const ack = (current && current.content_acknowledge) || [];
  const ackBox = id === "approve-content" && ack.length ? `<div class="alert alert-warning"><b>尚未闭环的 ${ack.length} 条提示</b>（非阻断，确认即表示您已知悉）：<span class="mono">${ack.map(esc).join("、")}</span>
    <label class="form-check mt-2 mb-0"><input class="form-check-input" type="checkbox" name="ack" required><span class="form-check-label">我已逐条查看上述提示及其影响</span></label></div>` : "";
  if(id === "approve-content") return `<form id="${id}" class="card-body"><p>确认后将锁定本版本总结，进入事实库与页面编排。</p>${ackBox}<label class="form-label required" for="content-customer">确认人姓名</label><input id="content-customer" name="customer" class="form-control mb-3" value="${esc($("#me").value)}" required maxlength="200"><input type="hidden" name="method" value="本机人工内容复核"><label class="form-label" for="content-feedback">补充意见（可选）</label><textarea id="content-feedback" name="feedback" class="form-control mb-3" rows="2"></textarea><label class="form-check mb-3"><input class="form-check-input" type="checkbox" required><span class="form-check-label">我已阅读本版本确认稿，确认内容与来源、授课要求一致。</span></label><button class="btn btn-success">${label}</button><details class="small text-secondary mt-3"><summary>版本记录</summary><span class="mono">${esc(subject)}</span></details></form>`;
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
    act(() => api("POST", `/workflows/${wid()}/approvals/${kind}`, { customer: f.get("customer"), operator: kind === "content" ? String(f.get("customer")).trim() : me(), method: f.get("method"),
      feedback: f.get("feedback"), subject_sha256: subject,
      ...(kind === "content" ? { acknowledged_issues: current.content_acknowledge || [] } : {}) }), "确认已记录");
  };
}

function tabSummary(issuesOnly = false) {
  const w = current, s = w.summary, a = w.content_approval, subject = w.approval_subjects.content;
  if (!s) { $("#tab").innerHTML = card("全文总结", empty("尚无总结。全部资料阅读完成后，在“执行端任务”中加入“全文总结”。")); return; }
  const loc = {}, unit = {};
  w.sources.forEach((src) => src.pages.forEach((p) => { loc[p.id] = `${src.filename} · ${p.location}`; }));
  w.sources.forEach((src) => [...src.units, ...src.transcriptions].forEach((u) => { unit[u.id] = u; }));
  const points = (x) => (x.key_points || []).length ? `<div class="mt-2">${x.key_points.map((k) => `<div class="mb-2"><b>要点：</b>${esc(k.point)}
      ${(k.unit_ids||[]).map((id) => unit[id] ? `<div class="small text-secondary ms-3">原文（${esc(unit[id].location)}）：${esc(unit[id].text)} <button type="button" class="btn btn-sm btn-link p-0" data-source-page="${esc(unit[id].page_id)}">对照原页</button></div>` : "").join("")}</div>`).join("")}</div>` : "";
  const sections = s.sections.map((x) => `<div class="mb-3"><h4 class="mb-1">${esc(x.title)} <span class="text-secondary small mono">${esc(x.id)}</span></h4>
      <div class="quote">${esc(x.summary)}</div>${points(x)}
      <div class="small text-secondary mt-1">来源：${x.source_page_ids.map((r) => esc(loc[r] || r)).join("；")}</div></div>`).join("");
  const issues = s.pending_issues.length ? `<details class="alert alert-warning"><summary class="fw-bold">总结作者列出的 ${s.pending_issues.length} 项待确认事项（点击展开）</summary><div class="small mt-2">来自总结中的待处理清单，包含来源异常、引用限制和需求确认；不是独立审核新增的错误数。需逐项有依据地处理后才能确认内容。</div><ul class="mb-0 mt-2">
      ${s.pending_issues.map((i) => `<li>${esc(typeof i === "string" ? i : JSON.stringify(i))}</li>`).join("")}</ul></details>` : "";
  const approved = a && a.subject_sha256 === subject;
  const sr = w.summary_review, srCurrent = sr && !["SUMMARY_REVIEW_REQUIRED"].includes(w.stage) && subject;
  const judgments = srCurrent ? sr.sections.flatMap(section=>section.key_points || []) : [];
  const verdictCount = verdict => judgments.filter(point=>point.verdict===verdict).length;
  const blockerCount = srCurrent ? sr.issues.filter(issue=>issue.severity==="BLOCKER" && unresolved(issue)).length : 0;
  const noteCount = srCurrent ? sr.issues.filter(issue=>issue.severity==="NOTE" && unresolved(issue)).length : 0;
  const reviewCounts = srCurrent ? `<div class="card-body border-bottom"><b>要点判定：</b>${judgments.length} 条中，${verdictCount("ENTAILED")} 条支持、${verdictCount("PARTIAL")} 条部分支持、${verdictCount("NOT_ENTAILED")} 条不支持、${verdictCount("CONTRADICTED")} 条矛盾。<br><b>审核问题记录：</b>${blockerCount} 个未处理阻断、${noteCount} 个提示。<div class="small text-secondary mt-2">要点判定、审核问题记录和总结作者的 ${s.pending_issues.length} 项待确认事项按不同对象计数。同一要点可同时产生提示和阻断，一条问题也可能涉及多个位置；三种数字不相加。阻断须修订或由审核人有依据地驳回，提示应逐项核查。</div></div>` : "";
  const repairPrompt = `请修订项目 ${w.id} 当前总结中的全部未处理阻断及相关审核意见，按原资料逐项更正并记录依据，再安排独立执行端审核新版本；停在人工内容确认，不自动确认或生成PPT。`;
  const repairPanel = blockerCount ? card("处理未通过的总结", `<div class="card-body"><b>${blockerCount} 个阻断尚未处理</b><div class="mt-2">推荐交给Codex执行端按来源修订，再做独立复核。仅重复审核或刷新页面不会消除问题。</div><div class="btn-list mt-3"><button type="button" class="btn btn-primary" id="show-repair-request">交给执行端修订</button><button type="button" class="btn" data-edit-summary="">我手动修订</button><button type="button" class="btn" id="show-review-issues">查看阻断明细</button></div><div id="repair-request" class="mt-3" hidden><label class="form-label" for="repair-prompt">把下面这段发送到当前Codex对话，即可安排执行。此按钮只展示请求，不会自动启动模型。</label><textarea id="repair-prompt" class="form-control" rows="4" readonly>${esc(repairPrompt)}</textarea></div></div>`) : "";
  const srRows = srCurrent ? ledgerRows(sr.issues, sr.dismissed, "data-sdismiss", true) : "";
  const review = card(`独立总结审查${srCurrent ? ` <span class="text-secondary small">${esc(sr.reviewer)} · ${time(sr.at)}</span>` : ""}`,
    !srCurrent ? empty("当前总结尚未经独立审查。在“执行端任务”中加入“独立总结审查”（须由总结作者和论断清单作者之外的执行端完成）。")
      : srRows ? `${reviewCounts}<div class="card-body border-bottom small text-secondary">问题台账保留历次审查的全部问题，编号不变；每轮复核须逐条回看未闭环问题。只有确认问题不成立或需要您决定时才记录裁定；成立的问题应修订总结。</div>
        <div class="table-responsive"><table class="table card-table"><thead><tr><th>位置</th><th>级别</th><th>问题</th><th></th></tr></thead><tbody>${srRows}</tbody></table></div>`
      : empty("审查未报告问题。"));
  const canApprove = subject && !s.pending_issues.length && ["CONTENT_CONFIRMATION"].includes(w.stage);
  $("#tab").innerHTML = repairPanel + `<div class="row g-3"><div class="col-lg-5">${sourceEvidencePanel(w)}</div><div class="col-lg-7">` + card("全文总结", `<div class="card-body">
      ${subject ? "" : `<div class="alert alert-danger">总结已过期（资料、阅读或提纲已变更），需要重新生成。</div>`}
      ${issues}<p class="quote">${esc(s.overall_summary)}</p><hr>${sections}</div>`,
      `<a class="btn btn-sm" href="${url("/confirmation-draft")}"><i class="ti ti-download me-1"></i>内容确认稿</a>`)
    + `<div id="summary-review-issues">${review}</div>`
    + card("客户内容确认", (approved ? `<div class="card-body"><div class="alert alert-success mb-0">已确认：${esc(a.customer)}（${esc(a.method)}），
        操作人 ${esc(a.operator)}，${time(a.at)}</div></div>` : canApprove ? approvalForm("approve-content", subject, "记录客户已确认内容")
        : empty("当前不能确认：需先有当前版本的总结，经独立审查且无未处理的阻断问题，并处理全部待解决问题。")))
    + summaryEditor(w) + '</div></div>';
  if (issuesOnly) {
    $("#tab").innerHTML = confirmationFlow(w, {review, repairPanel, canApprove, approved, subject, blockerCount});
  } else {
    const panel=$("#repair-request")?.closest(".card");
    if(panel) panel.remove();
    $("#summary-edit")?.closest("details")?.remove();
    const reviewSection=$("#summary-review-issues");
    if(reviewSection) reviewSection.innerHTML=card("审核结果与问题处理", `<div class="card-body">${srCurrent?`${blockerCount} 个未处理阻断、${noteCount} 个提示。`:"当前总结尚未完成独立审核。"}<div class="mt-2">问题明细和修订入口集中在“待确认与问题”。</div><a class="btn btn-primary mt-2" href="#/w/${esc(w.id)}/confirm">查看并处理问题</a></div>`);
  }
  bindSourceEvidence();
  bindSummaryEditor();
  if(issuesOnly) bindConfirmationFlow(w, subject);
  document.querySelectorAll("[data-edit-summary]").forEach(button=>button.onclick=()=>{
    const form=$("#summary-edit"); if(!form)return flash("当前版本没有可编辑总结，请安排执行端重新生成。");
    for(let ancestor=form.parentElement;ancestor;ancestor=ancestor.parentElement) if(ancestor.tagName==="DETAILS") ancestor.open=true;
    const match=button.dataset.editSummary.match(/(s\d+)[.:]key(\d+)$/);
    const index=match?s.sections.findIndex(section=>section.id===match[1]):-1;
    const field=index>=0?form.elements.namedItem(`point_${index}_${Number(match[2])-1}`):button.dataset.editSummary==="pending_issues"?form.elements.namedItem("pending"):form;
    (field || form).scrollIntoView({behavior:"smooth",block:"center"}); if(field && field!==form)field.focus({preventScroll:true});
  });
  const request=$("#show-repair-request");if(request)request.onclick=()=>{$("#repair-request").hidden=false;$("#repair-prompt").focus();$("#repair-prompt").select();};
  const showIssues=$("#show-review-issues");if(showIssues)showIssues.onclick=()=>{
    const target=$("#summary-review-issues");target.closest("details").open=true;
    target.scrollIntoView({behavior:"smooth",block:"start"});
  };
  bindApproval("approve-content", "content", subject);
  document.querySelectorAll("form[data-sdismiss]").forEach((f) => f.onsubmit = (ev) => {
    ev.preventDefault();
    act(() => api("POST", `/workflows/${wid()}/summary-review/issues/${encodeURIComponent(f.dataset.sdismiss)}/dismiss`,
      { reviewer: me(), reason: f.reason.value }), "裁定已记录");
  });
}

function confirmationFlow(w, state) {
  const {review, repairPanel, canApprove, approved, subject, blockerCount}=state;
  const pending=w.summary.pending_issues, receipt=w.summary_pending_responses;
  const saved=receipt && receipt.subject_sha256===subject;
  const sourceForRef = (ref) => {
    const m=String(ref).match(/^(S\d+):p(\d+)(?:#k(\d+))?$/); if(!m)return null;
    const [,sid,pageNo,claimNo]=m, source=w.sources.find(x=>x.id===sid), page=source?.pages.find(x=>x.id===`${sid}:p${pageNo}`);
    if(!source||!page)return {ref};
    const claim=claimNo?(source.claims?.items||[]).find(x=>x.id===`${sid}:p${pageNo}#k${claimNo}`):null;
    const units=[...source.units,...source.transcriptions].filter(x=>x.page_id===page.id);
    return {ref,sid,page,claim,units};
  };
  const issueSourceRefs = (text) => {
    const refs=[];
    for(const match of text.matchAll(/(S\d+):p(\d+)(?:#k(\d+))?((?:(?:\/|[与和及])p\d+(?:#k\d+)?)*)/g)){
      refs.push(`${match[1]}:p${match[2]}${match[3]?`#k${match[3]}`:""}`);
      for(const suffix of match[4].matchAll(/(?:\/|[与和及])p(\d+)(?:#k(\d+))?/g)) refs.push(`${match[1]}:p${suffix[1]}${suffix[2]?`#k${suffix[2]}`:""}`);
    }
    return [...new Set(refs)];
  };
  const sourceEvidence = (item) => {
    const text=typeof item==="string"?item:JSON.stringify(item);
    const refs=issueSourceRefs(text);
    if(!refs.length)return `<div class="small text-warning mt-2">该事项没有可识别的来源页码；请先在确认稿中核对来源位置。</div>`;
    return `<div class="mt-2"><div class="small fw-bold mb-1">对应来源与原文</div>${refs.map(ref=>{
      const evidence=sourceForRef(ref); if(!evidence?.page)return `<div class="small text-danger">${esc(ref)}：当前项目中找不到对应原始页。</div>`;
      const quote=evidence.claim?.spans?.map(span=>span.quote).join("；");
      const transcript=quote||evidence.units.map(unit=>unit.text).join("\n\n")||evidence.page.text||"该页没有可显示的文字转录，请查看原页图。";
      const label=quote?"论断原文片段":"该来源页的文字转录";
      return `<details class="border rounded p-2 mb-2"><summary>${esc(ref)} · ${esc(evidence.page.location)}${quote?" · 精确论断片段":" · 查看页面原文"}</summary><div class="small mt-2"><b>${label}：</b><div class="quote mt-1">${esc(transcript)}</div><button type="button" class="btn btn-sm btn-link px-0" data-source-page="${esc(evidence.page.id)}">在原始资料栏打开本页</button></div></details>`;
    }).join("")}</div>`;
  };
  const waiting=["SUMMARY_AMEND_RUNNING","SUMMARY_REVIEW_REQUIRED"].includes(w.stage);
  const title=w.stage==="SUMMARY_AMEND_RUNNING"?"答复已提交，执行端处理已排队":approved?"内容已确认":blockerCount?"先修订审核问题":waiting?"等待独立审核":pending.length?`先回答 ${pending.length} 项待确认事项`:"请复核并确认内容";
  const explanation=w.stage==="SUMMARY_AMEND_RUNNING"?"系统已排好局部修订任务，仅处理本次答复对应的事项。执行端提交后自动进入独立复核，通过后开放最终确认。":approved?"本版本确认已记录，可以进入下一阶段。":blockerCount?"执行端需要先修订这些问题。你可以查看具体意见并安排处理。":waiting?"独立执行端完成审核后，才会开放内容确认。":pending.length?"内容独立审核已通过。请在下面逐项选择你掌握的情况；保存答复后，由执行端处理来源记录并复核，再开放最终确认。":"阅读确认稿，核对要求和内容后，在下方填写确认信息并提交。";
  const answers=pending.length?`<form id="pending-answers" class="card-body">${pending.map((item,i)=>{
    const previous=saved?receipt.answers.find(answer=>answer.index===i):null;
    return `<fieldset class="confirmation-question mb-3"><legend class="fs-4 mb-2">待确认事项 ${i+1}</legend><p>${esc(typeof item==="string"?item:JSON.stringify(item))}</p>${sourceEvidence(item)}<label class="form-label mt-3" for="pending-choice-${i}">你掌握的情况</label><select id="pending-choice-${i}" name="answer_${i}" class="form-select mb-2" required><option value="">请选择</option>${[["AVAILABLE","已有相关文件或明确依据"],["UNAVAILABLE","目前没有相关文件或依据"],["UNKNOWN","我还不能确定，需要进一步核对"]].map(([value,label])=>`<option value="${value}" ${previous?.answer===value?"selected":""}>${label}</option>`).join("")}</select><label class="form-label" for="pending-note-${i}">依据或补充说明</label><textarea id="pending-note-${i}" name="note_${i}" class="form-control" rows="2" placeholder="如有文件，请说明文件名，并在“上传资料”中补充；没有或不确定也可如实说明。">${esc(previous?.note||"")}</textarea></fieldset>`;
  }).join("")}<div class="mb-3"><label class="form-label required" for="pending-operator">你的姓名（记录用）</label><input id="pending-operator" name="operator" class="form-control" value="${esc($("#me").value)}" required maxlength="200"></div><button class="btn btn-primary">${saved?"更新答复":"保存答复"}</button><div class="form-hint mt-2">保存答复会留下记录。最终内容确认须在执行端处理及独立复核后提交。</div></form>`:"";
  const prompt=`请处理项目 ${w.id} 当前版本已保存的 summary_pending_responses。依据人工答复和原资料更新来源限制与待确认事项，记录处理依据，安排独立复核；停在人工内容确认。未确定的事项保留，不自动确认或生成PPT。`;
  const followUp=saved?`<div class="card-body border-bottom"><div class="alert alert-success">答复已保存：${esc(receipt.operator)} · ${time(receipt.at)}。下一步由执行端处理。</div><details><summary>如何让执行端继续处理？</summary><p class="mt-2">将下面这段发送到当前Codex对话。网页尚不能自动启动执行端。</p><textarea class="form-control" rows="4" readonly aria-label="执行端处理请求">${esc(prompt)}</textarea></details></div>`:"";
  const finalForm=approved?`<div class="card-body text-success">已由 ${esc(w.content_approval.customer)} 确认，${time(w.content_approval.at)}。</div>`:canApprove?approvalForm("approve-content",subject,"确认本版本内容"): `<div class="card-body"><button class="btn btn-success" disabled>确认本版本内容</button><div class="mt-2 text-secondary">${blockerCount?"先完成审核问题修订及复核。":waiting?"独立审核尚未完成。":pending.length?"先处理上方待确认事项，再由执行端更新记录并复核。":"请完成当前版本的前置条件。"}</div></div>`;
  return `<div id="confirmation-flow">${card(title,`<div class="card-body"><p class="mb-3">${explanation}</p><div class="confirmation-steps"><span class="badge bg-${pending.length?"blue":"green"}-lt">1. 回答待确认事项</span><span class="badge bg-${waiting||blockerCount?"blue":"secondary"}-lt">2. 执行端处理与复核</span><span class="badge bg-${canApprove?"blue":approved?"green":"secondary"}-lt">3. 确认内容</span></div></div>`)}<div class="row g-3 align-items-start"><div class="col-lg-5">${sourceEvidencePanel(w)}</div><div class="col-lg-7">${pending.length?card("第一步：回答待确认事项",followUp+answers):""}${repairPanel}${card("复核本版本内容",`<div class="card-body"><p>核对受众、授课时长、覆盖范围，以及要点和来源限制。</p><div class="btn-list"><a class="btn" href="#/w/${esc(w.id)}/summary">查看原文与总结</a><a class="btn" href="${url("/confirmation-draft")}" target="_blank">打开内容确认稿</a></div></div>`)}${card("最终确认",finalForm)}<details class="card mb-3"><summary class="card-body fw-bold">查看独立审核明细与高级修订</summary><div id="summary-review-issues">${review}</div>${summaryEditor(w)}</details></div></div></div>`;
}
function bindConfirmationFlow(w,subject) {
  const form=$("#pending-answers");if(!form)return;
  form.onsubmit=event=>{
    event.preventDefault();const data=new FormData(form),operator=String(data.get("operator")||"").trim();
    const answers=w.summary.pending_issues.map((_,index)=>({index,answer:String(data.get(`answer_${index}`)),note:String(data.get(`note_${index}`)||"").trim()}));
    if(answers.some(answer=>answer.answer==="AVAILABLE" && !answer.note))return flash("选择已有文件或依据时，请填写对应的文件名或依据说明。");
    act(()=>api("POST",`/workflows/${w.id}/summary/pending-responses`,{operator,subject_sha256:subject,answers}),"答复已保存，局部处理任务已自动排队。完成处理及独立复核后开放内容确认。");
  };
}

async function tabFacts() {
  const data = await optional(`/workflows/${wid()}/facts`);
  if (!data) { $("#tab").innerHTML = card("事实库", empty("尚无事实库。客户确认内容后，在“执行端任务”中加入“事实库”。")); return; }
  const rows = data.facts.map((f) => `<tr class="${f.status === "REJECTED" ? "table-danger" : ""}">
      <td class="mono">${esc(f.id)}</td>
      <td>${f.status === "ACCEPTED" ? badge("通过", "green") : badge("拒绝", "red")}${f.needs_confirmation ? " " + badge("待确认", "orange") : ""}</td>
      <td>${f.figure ? `<div>${figureThumb(f.figure, 90)}</div><div class="small text-secondary">原件图 ${esc(f.figure)}${f.caption.length ? ` · 图注：${esc(f.caption.join(", "))}` : ""}</div>`
        : `<div>${esc(f.display || f.quote)}</div>${f.display && f.display !== f.quote ? `<div class="text-secondary small quote">原文：${esc(f.quote)}</div>` : ""}`}
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
  if (w.summary && ["SUMMARY_AMEND_RUNNING","SUMMARY_ISSUES","SUMMARY_REVIEW_REQUIRED","CONTENT_CONFIRMATION"].includes(w.stage)) return tabSummary(true);
  const data = await optional(`/workflows/${wid()}/confirmations`);
  const sr = w.semantic_review;
  let html = "";
  const activeReviews = w.tasks.filter(t => t.kind === "SEMANTIC_REVIEW" && ["PENDING", "RUNNING"].includes(t.status));
  const openSemantic = (sr?.issues || []).filter(unresolved);
  const executorIssues = openSemantic.filter(i => i.status !== "NEEDS_HUMAN");
  const humanRecords = openSemantic.filter(i => i.status === "NEEDS_HUMAN");
  const groupedIds = new Set();
  const humanIssues = (w.review_issue_groups || []).map(g => {
    const members = humanRecords.filter(i => g.issue_ids.includes(i.id));
    members.forEach(i => groupedIds.add(i.id));
    return members.length ? {...members[0], problem:g.label, group_ids:members.map(i => i.id), group_members:members} : null;
  }).filter(Boolean).concat(humanRecords.filter(i => !groupedIds.has(i.id)));
  const plan = w.review_scope_plan;
  if (activeReviews.length) html += `<div class="alert alert-info">独立复核正在处理本版本。你可以先查看原图和待办，复核完成后再保存人工决定，以免使正在检查的版本失效。</div>`;
  html += card("现在需要做什么", `<div class="card-body"><div class="row g-3"><div class="col-md-6"><h3>${sr?.input_sha256 && !activeReviews.length ? "执行端检查已完成" : "执行端处理中"}</h3><p>${activeReviews.length ? "独立复核已排队或正在处理，完成后更新本页。" : executorIssues.length ? `有 ${executorIssues.length} 条问题记录需要执行端修订或复核。` : sr?.input_sha256 ? "本版独立复核已完成，当前等待来源确认与人工裁定。" : "查看下方审核记录；尚未完成的检查由执行端处理。"}</p><a class="btn btn-outline-primary" href="#/w/${esc(w.id)}/tasks">查看执行进度</a></div><div class="col-md-6"><h3>需要你处理</h3><p>${humanIssues.length} 组人工裁定事项；来源文字更正见下方“人工确认”。先打开原图与对照稿，再逐项保存决定。重复记录可能指向同一事项。</p><button class="btn btn-primary" id="show-human-decisions">查看待裁定事项</button></div></div>${plan ? `<div class="alert alert-info mt-3 mb-0">本轮按影响范围复核：${plan.changed_pages.length} 个修改或受影响页面。未改内容复用有效审核证据；复用不代表本版本已通过。<details class="mt-2"><summary>查看复核范围</summary>${plan.changed_pages.map(esc).join("、")}</details></div>` : ""}<p class="small text-secondary mt-3 mb-0">保存答复或裁定后，系统重新计算状态。需要修订或复核时由执行端继续处理；网页排队不会自动调用模型。仍有阻断时不能进入正式生成。</p></div>`);
  if (w.review_material && w.review_material.subject_sha256 === w.deck?.result_sha256) html += card("原图与拟采用内容对照", `<div class="card-body"><p>先对照原图查看更正提案和需要裁定的关系，再在下方逐项记录确认或裁定。</p><a class="btn btn-outline-primary" target="_blank" href="${esc(w.review_material.url)}">打开人工裁定对照稿</a><span class="small text-secondary ms-2">对照稿只供查看，操作在本工作台保存。</span></div>`);
  if (!data) html += card("人工确认", empty("尚无当前版本的页面规格。"));
  else {
    const items = data.pending.map((it, n) => {
      if (it.kind === "derivation") return `<div class="card-body border-bottom"><div class="mb-1">${badge("推导", "purple")} <span class="mono">${esc(it.id)}</span>
          · 用于 ${esc(it.facts.join(", "))}</div><div><b>${esc(it.claim)}</b></div><div class="small text-secondary">规则：${esc(it.rule)} · 依据：${esc(it.evidence.join(", "))}</div>
        <form data-der="${esc(it.id)}" class="d-flex gap-2 mt-2 flex-wrap"><input name="note" class="form-control form-control-sm" style="max-width:24rem" placeholder="备注">
          <button class="btn btn-sm btn-success" name="d" value="CONFIRM">确认成立</button><button class="btn btn-sm btn-danger" name="d" value="REJECT">否定</button></form></div>`;
      if (it.kind === "figure_review") return `<div class="card-body border-bottom"><div class="mb-1">${badge("截取与去标识", "azure")}
          <span class="mono">${esc(it.id)}</span> · ${esc(it.location)} · ${it.width}×${it.height}px
          ${it.reading && it.reading.may_contain_patient_info ? badge("阅读时提示：可能含患者信息", "red") : ""}</div>
        <div class="row g-3"><div class="col-md-5">${figureThumb(it.id, 220)}${it.method === "page_crop" ? `<div class="mt-2">${cropView(it)}</div>` : ""}</div><div class="col-md-7">
          ${it.second_read && !it.second_read.agree ? `<div class="alert alert-warning py-2 small">两次独立截取区域不一致（交并比 ${it.second_read.iou}）。
            请对照原页，在备注中说明现有截取为何完整；若确有遗漏，不要登记，请重新排队阅读并修正截取区域。</div>` : ""}
          ${it.reading ? `<div class="small text-secondary mb-2">阅读说明：${esc(it.reading.note)}</div>` : ""}
          <div class="small mb-2">请打开 <a href="${url(`/sources/${encodeURIComponent(it.source_id)}/file`)}" target="_blank">原件</a> 对照：图例、坐标轴、脚注、显著性标记是否都在；图中有无姓名、编号、日期、面部等可识别信息。</div>
          <form data-figreview="${esc(it.id)}">
            <label class="form-check"><input class="form-check-input" type="checkbox" name="crop" required><span class="form-check-label">已对照原件，图完整无缺</span></label>
            <select name="deid" class="form-select form-select-sm mb-2" required><option value="">去标识结论…</option>
              ${Object.entries(DEID_LABEL).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
            <input name="note" class="form-control form-control-sm mb-2" placeholder="备注">
            <button class="btn btn-sm btn-primary">登记</button></form></div></div></div>`;
      if (it.kind === "figure_second_crop") return `<div class="card-body border-bottom"><div class="mb-1">${badge("待第二次截取", "orange")}
          <span class="mono">${esc(it.id)}</span> · ${esc(it.location)}</div>
        <div class="small text-secondary">此图由阅读执行端按区域从原页截取，需另一执行端独立截取一次（排队“第二次独立转录/截取”任务）后才能正式渲染。</div></div>`;
      if (it.kind === "figure_licence") return `<div class="card-body border-bottom"><div class="mb-1">${badge("使用许可", "teal")}
          <span class="mono">${esc(it.id)}</span> · ${esc(it.location)}</div>
        <div class="d-flex gap-3 align-items-start">${figureThumb(it.id, 90)}
        <form data-figlicence="${esc(it.id)}" class="flex-fill"><div class="row g-2">
          <div class="col-md-4"><input name="customer" class="form-control form-control-sm" placeholder="客户" required></div>
          <div class="col-md-4"><input name="method" class="form-control form-control-sm" placeholder="确认方式" required></div>
          <div class="col-md-4"><input name="scope" class="form-control form-control-sm" placeholder="使用范围"></div></div>
          <div class="d-flex gap-2 mt-2 flex-wrap"><button class="btn btn-sm btn-success" name="p" value="yes">客户许可使用</button>
            <button class="btn btn-sm btn-danger" name="p" value="no">客户不许可</button>
            <button class="btn btn-sm" name="p" value="all">许可本资料全部待许可的图</button></div></form></div></div>`;
      if (it.kind === "conflict") return `<div class="card-body border-bottom"><div class="mb-1">${badge("冲突", "red")} ${esc(it.entity)} · ${esc(it.attribute)}</div>
        <form data-conflict="${n}" class="mt-1">${Object.entries(it.values).map(([val, ids]) => ids.map((fid) =>
          `<label class="form-check"><input class="form-check-input" type="radio" name="fact_id" value="${esc(fid)}" required>
           <span class="form-check-label">${esc(val)} <span class="mono text-secondary">${esc(fid)}</span></span></label>`).join("")).join("")}
          <div class="d-flex gap-2 mt-1"><input name="note" class="form-control form-control-sm" style="max-width:24rem" placeholder="裁定理由">
          <button class="btn btn-sm btn-primary">采用所选事实</button></div></form></div>`;
      return `<div class="card-body border-bottom"><div class="mb-1">${badge("图表转录", "orange")} <span class="mono">${esc(it.id)}</span> · ${esc(it.location)}</div>
        <div class="small text-secondary">${esc(it.reason)}</div>
        ${it.proposal_of ? `<div class="alert alert-warning small">这是待确认的更正提案；原转录保留。<details><summary>查看原转录</summary><span class="quote">${esc(it.original_text)}</span></details></div>` : ""}
        ${it.page_image_url ? `<a target="_blank" href="${esc(it.page_image_url)}">打开原始资料页逐字对照</a>` : ""}
        <div class="small">${it.proposal_of ? "更正提案" : "第一次"}：<span class="quote">${esc(it.text)}</span>${it.second_read ? `<br>第二次：<span class="quote">${esc(it.second_read.text ?? JSON.stringify(it.second_read))}</span>` : ""}</div>
        <form data-unit="${esc(it.id)}" class="mt-2"><textarea name="text" class="form-control form-control-sm mb-1" rows="2" required>${esc(it.text)}</textarea>
          <label class="form-check"><input class="form-check-input" type="checkbox" name="checked" required><span class="form-check-label">我已对照原件逐字核对</span></label>
          <button class="btn btn-sm btn-primary">确认转录文字</button></form></div>`;
    }).join("");
    html += card(`人工确认 ${data.pending.length ? badge(`${data.pending.length} 项待处理`, "orange") : badge("无待处理", "green")}`,
      items || empty("页面用到的推导、冲突和图表转录都已确认。"));
  }
  if (sr) {
    const rows = ledgerRows(sr.issues.filter(i => !unresolved(i)), sr.dismissed, "data-dismiss", false);
    const issueTable = rows => `<div class="table-responsive"><table class="table card-table"><thead><tr><th>编号</th><th>级别/状态</th><th>问题与依据</th><th>操作</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    html += `<section id="human-decisions">${card("需要你裁定的事项", humanIssues.length ? issueTable(ledgerRows(humanIssues, sr.dismissed, "data-dismiss", true)) : empty("暂无审核台账中的人工裁定事项。来源转录更正请在上方逐项处理。"))}</section>`;
    if (executorIssues.length) html += card("由执行端修订与复核", `<div class="card-body text-secondary">以下问题由执行端按原资料修订，再独立复核。你无需为修订问题填写通过结论。</div>` + issueTable(ledgerRows(executorIssues, sr.dismissed, "data-dismiss", false)));
    const checks = sr.checks || {};
    const names = { COVERAGE: "覆盖/逐字检查", RELATIONS: "语义/关系检查" };
    const checkRows = Object.keys(names).map((c) => {
      const x = checks[c];
      if (!x) return `<tr><td>${names[c]}</td><td colspan="3" class="text-secondary">尚未完成（须由不同的独立执行端完成）</td></tr>`;
      const n = x.counts || {};
      const mode = (x.regression || {}).mode === "IMPACT" ? "按影响范围复核" : "全量复核";
      const extra = (n.teaching_items ? ` · 教学条目 ${n.teaching_items}` : "") + (n.relations ? ` · 关系 ${n.relations}` : "");
      return `<tr><td>${names[c]}</td><td class="small">${esc(x.reviewer)} · 第 ${x.round} 轮 · ${time(x.at)}<div class="text-secondary">${mode}</div></td>
        <td class="small">来源清单 ${n.source_pages ?? "—"} 页 · 页面 ${n.deck_pages_read ?? 0} 复读 / ${n.deck_pages_carried ?? 0} 沿用 · 历史问题 ${n.prior_issues ?? 0} · 新增记录 ${n.new_issues ?? 0}${n.duplicate_issue_records ? `（其中 ${n.duplicate_issue_records} 条为旧事项重复）` : ""}${extra} · 查看原图 ${n.viewed_source_pages ?? 0}</td>
        <td class="small text-warning">${(x.unchecked || []).length ? "范围与待确认说明：" + x.unchecked.map(esc).join("；") : ""}</td></tr>`;
    }).join("");
    const human = sr.issues.filter((i) => i.status === "NEEDS_HUMAN");
    const humanBox = human.length ? `<div class="card-body border-bottom small text-secondary">${humanIssues.length} 组人工事项对应 ${human.length} 条历史问题记录。上方已按同一事项合并操作入口，全部记录与依据保留。</div>` : "";
    html += card(`审核记录与已处理事项 <span class="text-secondary small">${esc(sr.reviewer)}</span>`,
      `<div class="table-responsive"><table class="table card-table table-sm"><tbody>${checkRows}</tbody></table></div>` + humanBox
      + (rows ? `<div class="card-body border-bottom small text-secondary">问题台账保留历次审查的全部问题，编号不变；修订版须逐条回应，复核须逐条给出处置，关闭须有证据。只有确认问题不成立或由您决定时才记录裁定。</div>
        <div class="table-responsive"><table class="table card-table"><thead><tr><th>编号</th><th>级别/状态</th><th>问题</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`
        : empty("审查未报告问题。")));
  } else html += card("独立语义审查", empty("尚无语义审查。在“执行端任务”中加入“独立语义审查”：覆盖/逐字检查与语义/关系检查须由两个不同的独立执行端完成。"));
  $("#tab").innerHTML = html;

  if (activeReviews.length) document.querySelectorAll('#tab form button[type="submit"], #tab form button:not([type])').forEach(b => {
    b.disabled = true;
    b.title = '独立复核完成后可提交；目前可先查看资料';
  });

  const showHuman = $("#show-human-decisions");
  if (showHuman) showHuman.onclick = () => $("#human-decisions")?.scrollIntoView({behavior:"smooth",block:"start"});
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
  document.querySelectorAll("form[data-figreview]").forEach((f) => f.onsubmit = (ev) => {
    ev.preventDefault();
    act(() => api("POST", `/workflows/${wid()}/confirmations/figures/${encodeURIComponent(f.dataset.figreview)}/review`,
      { reviewer: me(), crop_complete: f.crop.checked, deidentified: f.deid.value, note: f.note.value }), "已登记");
  });
  document.querySelectorAll("form[data-figlicence]").forEach((f) => f.onsubmit = (ev) => {
    ev.preventDefault();
    const choice = ev.submitter.value, it = data.pending.find((x) => x.kind === "figure_licence" && x.id === f.dataset.figlicence);
    const ids = choice === "all" ? data.pending.filter((x) => x.kind === "figure_licence" && x.source_id === it.source_id).map((x) => x.id) : [it.id];
    const body = { customer: f.customer.value, operator: "", method: f.method.value, scope: f.scope.value, permitted: choice !== "no" };
    act(async () => {
      body.operator = me();
      let last;
      for (const id of ids) last = await api("POST", `/workflows/${wid()}/confirmations/figures/${encodeURIComponent(id)}/licence`, body);
      return last;
    }, `已逐张登记 ${ids.length} 张图的许可`);
  });
  document.querySelectorAll("form[data-dismiss]").forEach((f) => f.onsubmit = (ev) => {
    ev.preventDefault();
    act(async () => {
      let saved;
      for (const id of (f.dataset.groupIds || f.dataset.dismiss).split(',')) saved = await api("POST", `/workflows/${wid()}/semantic-review/issues/${encodeURIComponent(id)}/dismiss`, {reviewer:me(),reason:f.reason.value});
      return saved;
    }, "裁定已逐条记录到关联台账");
  });
}

function reviewState(w, p) {
  const r = w.page_reviews[p.id];
  if (!r || r.png_sha256 !== p.sha256) return ["未审核", "secondary"];
  return r.visual_status === "PASS" && r.content_status === "PASS" ? ["通过", "green"] : ["需修改", "red"];
}

let generationPoll = null;
function generationProgress(g) {
  if (!g || !g.pages.length) return '<div class="text-secondary small">启动后先锁定内容，再由 Codex＋Adobe 执行端制作每页设计与矢量素材。</div>';
  const labels = { design: "设计稿", layout: "版面拆解", clean: "去字", vector: "矢量化" };
  const cost = g.cost || {};
  return `<div class="small mb-2">${badge(g.status === "COMPLETE" ? "已生成" : g.status === "FAILED" ? "需处理" : g.status === "STALE" ? "内容已变化" : "生成中", g.status === "FAILED" ? "red" : "azure")}
      · 已存档调用 ${cost.accepted_tool_calls || 0} · 任务尝试 ${cost.task_attempts || 0} · 已报工具耗时 ${cost.reported_tool_seconds || 0} 秒</div>
    ${g.render && g.render.error ? `<div class="alert alert-warning">${esc(g.render.error)}</div>` : ""}
    <div class="table-responsive"><table class="table table-sm"><thead><tr><th>页面</th>${Object.values(labels).map(l => `<th>${l}</th>`).join("")}<th>进度</th></tr></thead><tbody>
      ${g.pages.map(p => `<tr><td>${esc(p.id)}</td>${Object.keys(labels).map(k => `<td>${p.stages[k] ? badge("已完成", "green") : "待完成"}</td>`).join("")}
        <td>${p.tasks.map(t => `${esc(KIND_LABEL[t.kind])} · ${esc(t.status)}${t.error ? `<div class="text-warning">${esc(t.error)}</div>` : ""}`).join("")}</td></tr>`).join("")}</tbody></table></div>
    <div class="form-hint">费用尚无真实计费数据。调用回执与矢量差异随交付存档。</div>`;
}
function tabRender() {
  clearTimeout(generationPoll);
  const w = current, r = w.render, d = w.draft_render;
  const canGenerate = ["RENDER_REQUIRED","GENERATION_RUNNING","GENERATION_FAILED"].includes(w.stage);
  const canDraft = !!w.deck && !["READING_REQUIRED","CLAIMS_REQUIRED","SUMMARY_REQUIRED","SUMMARY_REVIEW_REQUIRED","SUMMARY_ISSUES","CONTENT_CONFIRMATION","FACTS_REQUIRED","DECK_REQUIRED"].includes(w.stage);
  const nextTab = (STAGE_ACTIONS[w.stage] || [null,null,"summary"])[2];
  const gateNotice = !canGenerate ? `<div class="alert alert-info"><div><b>暂不能正式生成：${esc(STAGE_LABEL[w.stage] || w.stage)}</b><div>${w.open_items.map(esc).join("；") || "请完成当前阶段。"}</div><a class="btn btn-sm mt-2" href="#/w/${esc(w.id)}/${nextTab}">处理当前步骤</a> <a class="btn btn-sm mt-2" href="#/w/${esc(w.id)}/tasks">查看执行任务</a></div></div>` : "";
  const lowDpi = (x) => x && x.warnings && x.warnings.figure_low_dpi.length ? `<div class="small text-warning">清晰度提示（不拦截，请在逐页审核时判断）：
      ${x.warnings.figure_low_dpi.map((d) => `${esc(d.fact)} 约 ${d.dpi} dpi`).join("；")}，低于 150 dpi</div>` : "";
  const other = (x) => x && x.warnings ? [...(x.warnings.render || []), ...(x.warnings.deck || [])].map((m) =>
      `<div class="small text-warning">${esc(m)}</div>`).join("") : "";
  const summary = (x) => x ? lowDpi(x) + other(x) + `<div class="small text-secondary">${time(x.at)} · 硬错误 ${x.hard_errors} ·
      ${Object.entries(x.summary).map(([k, v]) => `${esc(k)} ${v}`).join(" · ")}</div>` : "";
  const files = (x, kind) => x ? ["deck.pptx", "deck.pdf", "deck.html", "render_report.json", ...(x.trace_report ? ["trace.md"] : [])].map((n) =>
      `<a class="btn btn-sm" href="${url(`/render/${kind}/${n}`)}" target="_blank">${n}</a>`).join(" ") : "";
  // what the page reviewer checks on every page (app/deckflow.py RUBRIC); ticking one means "needs revision"
  const RUBRIC = [["first_glance", "第一眼"], ["peers", "并列同等"], ["qualifiers", "限定未变"], ["whitespace", "留白"],
    ["reading_order", "阅读方向"], ["repetition", "不重复"]];
  const DESIGN = [["first", "第一眼"], ["then", "随后"], ["reference", "查阅"], ["strong", "强元素"]];
  const pageNotes = (p) => {
    const d = p.design || {}, sig = p.signals || [], rev = p.review || [];
    const lines = DESIGN.filter(([k]) => d[k]).map(([k, n]) => `<div><span class="text-secondary">${n}：</span>${esc(d[k])}</div>`).join("");
    const sigs = sig.map((s) => `<div class="${s.justified ? "text-secondary" : "text-warning"}">${s.justified ? "已说明" : "待处理"} · ${esc(s.detail)}${s.justified ? `（${esc(s.justified)}）` : ""}</div>`).join("");
    const revs = rev.map((x) => `<div class="text-secondary">语义审查 · ${esc(x)}</div>`).join("");
    // the visual critique of this exact image (another worker; advisory, never a page review)
    const cr = w.critique && w.critique.pages[p.id] && w.critique.pages[p.id].png_sha256 === p.sha256 ? w.critique.pages[p.id] : null;
    const crit = cr ? `<div class="mt-1"><span class="text-secondary">版面评审（${esc(w.critique.critic)}）：</span>${
      RUBRIC.filter(([k]) => cr.rubric[k] === "REVISE").map(([, n]) => badge(n, "orange")).join(" ") || badge("各项通过", "green")}
      ${cr.fixes.map((f) => `<div>· ${esc(f)}</div>`).join("")}</div>` : "";
    return lines || sigs || revs || crit ? `<details class="small mb-1"><summary>本页设计、提示与审查项${sig.some((s) => !s.justified) ? " " + badge("有提示", "yellow") : ""}</summary>
      ${lines}${sigs}${revs}${crit}</details>` : "";
  };
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
          ${pageNotes(p)}
          <form data-review="${esc(p.id)}" data-sha="${esc(p.sha256)}">
            <div class="d-flex flex-wrap gap-2 small mb-1"><span class="text-secondary">需修改：</span>${RUBRIC.map(([k, n]) =>
              `<label class="form-check form-check-inline m-0"><input class="form-check-input" type="checkbox" name="r_${k}"><span class="form-check-label">${n}</span></label>`).join("")}</div>
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
    card(w.generation_route === "TEMPLATE_LIB" ? 'PPT 生成 · 模板库 <span class="badge bg-secondary-lt ms-2">你启动 · 程序生成 · 逐页溯源</span>'
         : 'PPT 生成 · A 原生矢量 <span class="badge bg-secondary-lt ms-2">你启动 · 执行端制作 · 系统导出</span>', `<div class="card-body">
      <div class="d-flex gap-2 flex-wrap mb-2">
        <button class="btn btn-primary" id="render-final" ${canGenerate?"":"disabled"}><i class="ti ti-player-play me-1"></i>开始／续跑生成</button>
        <button class="btn" id="render-draft" ${canDraft?"":"disabled"}>生成内容校对稿（无完整视觉设计）</button></div>${gateNotice}${!canDraft?'<div class="text-secondary mb-2">草稿尚不可用：需先完成当前版本的页面规格。</div>':""}
      <div class="form-hint mb-2">${w.generation_route === "TEMPLATE_LIB" ? "选版式 → 绑定事实 → 原生文字、表格与图形 → PowerPoint 画面核对 → 溯源报告（trace.md）。生成后逐页审核。草稿用于内容检查。" : "完整设计稿 → 版面拆解 → 去字 → 矢量化 → 原生文字、表格与图形 → PowerPoint 渲染核对。素材齐备后自动导出；完成后逐页审核。草稿用于内容检查。"}</div>
      <div id="generation-progress">${generationProgress(w.generation_status)}</div>
      ${r ? `<div class="mb-2"><b>正式版</b> <span class="mono small">${short(r.input_sha256)}</span> ${r.hard_errors ? badge("有硬错误", "red") : ""} ${files(r, "final")}${summary(r)}</div>` : ""}
      ${d ? `<div class="alert alert-warning"><div><b>内容校对稿 · 尚未完成视觉设计</b><div class="mb-2">此文件用于核对文字和来源，主要显示文字与基础排版。所选模板的插画、矢量图形和完整版面需等待 A 路线制作完成；请在“正式版”下载设计后的PPT。</div><span class="mono small">${short(d.input_sha256)}</span> ${files(d, "draft")}${summary(d)}</div></div>` : ""}</div>`)
    + (r ? card("客户风格确认（前5页）", styleDone ? `<div class="card-body"><div class="alert alert-success mb-0">已确认：${esc(a.customer)}（${esc(a.method)}），${time(a.at)}</div></div>`
        : subject && samplesOk ? approvalForm("approve-style", subject, "记录客户已确认样页风格") : empty("前5页全部审核通过后才能记录风格确认。")) : "")
    + (r ? card("逐页审核", `<div class="card-body">${gallery}</div>`) : "");
  $("#render-final").onclick = () => act(() => api("POST", `/workflows/${wid()}/generation`), "生成流程已启动，执行端任务已排队");
  $("#render-draft").onclick = () => act(() => api("POST", `/workflows/${wid()}/render?draft=true`), "内容校对稿已生成；完整视觉设计仍需执行端制作");
  if (w.generation_status && ["WAITING_WORKER", "PENDING", "RUNNING"].includes(w.generation_status.status)) {
    const id = wid();
    const poll = async () => {
      if (!current || !$("#generation-progress") || current.id !== id) return;
      try {
        const g = await api("GET", `/workflows/${id}/generation`);
        if (!current || !$("#generation-progress") || current.id !== id) return;
        $("#generation-progress").innerHTML = generationProgress(g);
        if (g.status === "COMPLETE") { await route(); return; }
        if (["WAITING_WORKER", "PENDING", "RUNNING"].includes(g.status)) generationPoll = setTimeout(poll, 5000);
      } catch (e) { generationPoll = setTimeout(poll, 15000); }
    };
    generationPoll = setTimeout(poll, 5000);
  }
  bindApproval("approve-style", "style", subject);
  document.querySelectorAll("form[data-review]").forEach((f) => f.onsubmit = (ev) => {
    ev.preventDefault();
    act(() => api("POST", `/workflows/${wid()}/pages/${encodeURIComponent(f.dataset.review)}/review`, {
      reviewer: me(), png_sha256: f.dataset.sha, sources_checked: f.checked.checked,
      visual_status: f.visual.value, content_status: f.content.value, feedback: f.feedback.value,
      rubric: Object.fromEntries(RUBRIC.map(([k]) => [k, f[`r_${k}`].checked ? "REVISE" : "PASS"])) }), `已记录 ${f.dataset.review}`);
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
