/* Local workbench extensions over the licensed Tabler shell. */
const WORKBENCH_STEPS = [
  ["sources", "上传资料", "ti-files"], ["overview", "要求与模板", "ti-palette"],
  ["summary", "内容复核", "ti-checklist"], ["render", "生成与审核", "ti-presentation"],
  ["delivery", "下载交付", "ti-download"],
];
const THEME_NAMES = {"navy-teal":"墨蓝青绿", "clinical-blue":"经典蓝", "graphite-amber":"炭黑琥珀", forest:"森林绿", plum:"梅紫", brand:"我的模板"};
const STAGE_ACTIONS = {
  SUMMARY_AMEND_RUNNING:["查看答复处理进度",null,"tasks"],
  READING_REQUIRED:["开始读取资料","READ_SOURCE","sources"], CLAIMS_REQUIRED:["整理来源要点","CLAIMS","summary"],
  SUMMARY_REQUIRED:["生成全文总结","SUMMARY","summary"], SUMMARY_REVIEW_REQUIRED:["启动独立内容审核","SUMMARY_REVIEW","summary"],
  SUMMARY_ISSUES:["查看问题并修订",null,"confirm"], CONTENT_CONFIRMATION:["复核并确认内容",null,"confirm"],
  FACTS_REQUIRED:["准备已确认内容","FACTS","summary"], DECK_REQUIRED:["编排PPT页面","DECK","render"],
  DECK_REVISION:["查看页面编排问题",null,"deck"], CONFIRMATIONS_REQUIRED:["处理待确认项目",null,"confirm"],
  SEMANTIC_REVIEW_REQUIRED:["审核页面内容与关系","SEMANTIC_REVIEW","render"], SEMANTIC_ISSUES:["查看页面审核问题",null,"confirm"],
  RENDER_REQUIRED:["进入PPT生成",null,"render"], GENERATION_RUNNING:["查看生成进度",null,"render"],
  GENERATION_FAILED:["处理生成问题",null,"render"], SAMPLES_REVIEW:["审核样页",null,"render"],
  STYLE_CONFIRMATION:["确认样页风格",null,"render"], PAGE_REVIEW:["继续逐页审核",null,"render"],
  PARTIAL_READY:["查看本次生成范围",null,"render"], READY_TO_EXPORT:["生成交付包",null,"delivery"], DELIVERED:["下载文件",null,"delivery"],
};
let workbenchPoll = null;

const STAGE_GUIDANCE = {
  SUMMARY_AMEND_RUNNING:"答复已保存，局部处理任务已排队；执行端提交后自动排队独立复核。",
  READING_REQUIRED:"上传全部资料，填写要求并选择模板，再启动资料读取。",
  CLAIMS_REQUIRED:"资料已读取，下一步整理来源要点并保留出处。",
  SUMMARY_REQUIRED:"来源要点已准备，下一步生成覆盖全部章节的总结。",
  SUMMARY_REVIEW_REQUIRED:"总结已生成，须由独立执行端逐项审核；审核后再由你确认内容。",
  SUMMARY_ISSUES:"查看审核问题，修订总结，再提交独立审核。",
  CONTENT_CONFIRMATION:"请对照原资料复核总结，填写右上角姓名并记录内容确认。",
  FACTS_REQUIRED:"内容已确认，下一步由执行端建立可追溯的事实库。",
  DECK_REQUIRED:"事实库已准备，下一步由执行端编排页面与阅读顺序。",
  DECK_REVISION:"查看页面编排问题，由执行端修订后重新审核。",
  CONFIRMATIONS_REQUIRED:"逐项查看待确认内容及来源依据，再记录人工确认。",
  SEMANTIC_REVIEW_REQUIRED:"页面已编排，须由独立执行端核对内容与关系。",
  SEMANTIC_ISSUES:"页面审核有阻断问题，需修订并重新审核。",
  RENDER_REQUIRED:"点击下方“开始／续跑生成”，进入设计和原生PPT制作。",
  GENERATION_RUNNING:"查看逐页进度；设计、去字和矢量化由Codex＋Adobe执行端完成。",
  GENERATION_FAILED:"查看任务错误，处理后点击“开始／续跑生成”重试。",
  SAMPLES_REVIEW:"先审核前5页：对照来源核对内容，查看版面后逐页记录结论。",
  STYLE_CONFIRMATION:"前5页已审核通过，请查看样页并记录客户风格确认。",
  PAGE_REVIEW:"继续核对剩余页面的内容、版面和来源，逐页记录审核结论。",
  PARTIAL_READY:"本次部分页面已完成；整套交付仍需完成其余页面的生成和审核。",
  READY_TO_EXPORT:"整套交付条件已满足，进入下载交付并生成交付包。",
  DELIVERED:"交付包已生成，可下载PPTX、PDF和审核记录。",
};
const EXECUTOR_STAGES = new Set(["SUMMARY_AMEND_RUNNING","READING_REQUIRED","CLAIMS_REQUIRED","SUMMARY_REQUIRED","SUMMARY_REVIEW_REQUIRED","SUMMARY_ISSUES","FACTS_REQUIRED","DECK_REQUIRED","DECK_REVISION","SEMANTIC_REVIEW_REQUIRED","SEMANTIC_ISSUES","GENERATION_RUNNING","GENERATION_FAILED"]);
function responsibility(w) {
  if(w.stage==="READING_REQUIRED" && !(Array.isArray(w.sources)?w.sources.length:w.sources)) return {kind:"user",label:"需要你操作",task:"上传资料，填写生成要求并选择模板。"};
  if(EXECUTOR_STAGES.has(w.stage)) return {kind:"executor",label:"由执行端处理",task:/ISSUES|REVISION/.test(w.stage)?"执行端修订内容并重新独立审核；你可查看问题，审核完成后再确认。":"执行端完成内容或设计任务；你可查看进度，无需填写审核结论。"};
  if(w.stage==="DELIVERED") return {kind:"done",label:"已完成，可下载",task:"下载交付文件。"};
  return {kind:"user",label:"需要你操作",task:STAGE_GUIDANCE[w.stage] || "查看当前待办并处理。"};
}
function responsibilityPanel(w) {
  const r=responsibility(w);
  return card("本阶段由谁处理",`<div class="card-body"><div class="row g-3"><div class="col-md-4"><div class="fw-bold text-primary mb-2">你需要做什么</div><div>${r.kind==="user"?esc(r.task):r.kind==="done"?"文件已可下载。":"当前无需提交人工确认。可查看结果；如需补充要求，可联系执行端。"}</div></div><div class="col-md-4"><div class="fw-bold mb-2">执行端负责</div><div>${r.kind==="executor"?esc(r.task):"内容整理、独立审核、页面编排与视觉素材制作。进入相应阶段后处理。"}</div><div class="small text-secondary mt-2">目前须在Codex对话中安排执行；网页排队不会自动调用模型。</div></div><div class="col-md-4"><div class="fw-bold mb-2">系统自动完成</div><div>校验提交结果、更新状态、保存记录；视觉素材齐备后编译原生PPT并渲染预览。</div><div class="small text-secondary mt-2">系统不会替你确认内容、风格或逐页审核。</div></div></div></div>`);
}
function stageGuide(w) {
  const action=STAGE_ACTIONS[w.stage] || ["查看项目",null,"overview"];
  const tasks=Array.isArray(w.tasks)?w.tasks.filter(t=>["PENDING","RUNNING"].includes(t.status) && (!action[1] || t.kind===action[1])):[];
  const running=tasks.some(t=>t.status==="RUNNING" && t.lease_until>Date.now()/1000);
  const phase=["READING_REQUIRED","CLAIMS_REQUIRED","SUMMARY_REQUIRED"].includes(w.stage)?0:["SUMMARY_AMEND_RUNNING","SUMMARY_REVIEW_REQUIRED","SUMMARY_ISSUES","CONTENT_CONFIRMATION","FACTS_REQUIRED"].includes(w.stage)?1:["READY_TO_EXPORT","DELIVERED"].includes(w.stage)?3:2;
  return {phase,text:STAGE_GUIDANCE[w.stage] || "查看当前待办，完成后进入下一阶段。",owner:running?"执行端正在处理":tasks.length?"等待执行端领取":responsibility(w).label,waiting:tasks.length && !running,target:tasks.length?"tasks":action[2]};
}
function workflowGuide(w) {
  const g=stageGuide(w),labels=["资料准备","内容审核与确认","页面制作与审核","下载交付"];
  return card("当前进展与下一步",`<div class="card-body"><div class="d-flex gap-2 flex-wrap mb-3">${labels.map((label,i)=>`<span class="badge bg-${w.stage==="DELIVERED"||i<g.phase?"green":i===g.phase?"blue":"secondary"}-lt">${i+1}. ${label}${w.stage==="DELIVERED"||i<g.phase?" · 已通过":i===g.phase?" · 当前阶段":" · 后续"}</span>`).join("")}</div><div class="fw-bold mb-2">${esc(g.owner)}</div><div>${esc(g.text)}</div>${g.waiting?'<div class="text-warning mt-2">任务已排队，尚未开始处理。需要Codex执行端领取，网页不会自动启动模型；无需重复提交。</div>':""}<details class="mt-3"><summary>第一次使用？查看操作顺序</summary><ol class="mt-2"><li>上传资料，填写受众、时长等要求并选择模板。</li><li>启动读取与总结任务；执行端完成后，复核并确认内容。</li><li>完成页面编排与人工确认，启动生成；先审核样页，再审核全部页面。</li><li>全部通过后生成交付包，下载PPT和PDF。</li></ol><div class="small text-secondary">填写右上角姓名后才能记录确认或审核。修改资料或内容会使相关确认失效，需按当前阶段重新处理。</div></details></div>`);
}

function workbenchGroup(tab) {
  if (tab === "templates") return "overview";
  if (["confirm","facts","summary"].includes(tab)) return "summary";
  if (["deck","render"].includes(tab)) return "render";
  return tab;
}
function workbenchDefault(w) {
  if (!w.sources.length) return "sources";
  return (STAGE_ACTIONS[w.stage] || [null,null,"overview"])[2];
}
function workbenchHeader(w, tab) {
  const active = workbenchGroup(tab);
  const nav = WORKBENCH_STEPS.map(([k,label,icon],i)=>`<a class="workbench-step ${k===active?"active":""}" ${k===active?'aria-current="step"':""} href="#/w/${esc(w.id)}/${k}"><span class="avatar avatar-sm rounded-circle">${i+1}</span><span><i class="ti ${icon} me-1"></i>${label}</span></a>`).join("");
  const action = w.stage === "CONTENT_CONFIRMATION" && w.summary?.pending_issues?.length
    ? ["回答待确认事项",null,"confirm"] : STAGE_ACTIONS[w.stage] || ["查看项目",null,"overview"];
  const tasks = w.tasks.filter(t=>["PENDING","RUNNING"].includes(t.status));
  const pending = tasks.filter(t=>t.status==="PENDING").length;
  const expired = tasks.filter(t=>t.status==="RUNNING" && t.lease_until<=Date.now()/1000).length;
  const running = tasks.filter(t=>t.status==="RUNNING" && t.lease_until>Date.now()/1000).length;
  const existing = action[1] && tasks.some(t=>t.kind===action[1]);
  return `<div class="page-header mb-3"><div class="row align-items-center g-2"><div class="col"><div class="page-pretitle"><a href="#/">本机工作台</a> / 修订 ${w.revision}</div><h2 class="page-title">${esc(w.title)}</h2></div><div class="col-auto">${stageBadge(w.stage)} <button id="reload" class="btn btn-sm ms-2"><i class="ti ti-refresh me-1"></i>刷新</button></div></div></div>
    <div class="card mb-3"><div class="card-body"><nav class="workbench-steps" aria-label="PPT制作流程">${nav}</nav></div></div>
    <div class="card mb-3"><div class="card-body"><div class="row align-items-center g-3"><div class="col"><div class="fw-bold">${esc(STAGE_LABEL[w.stage] || "处理项目")}</div><div class="text-secondary small mt-1">${w.stage==="CONFIRMATIONS_REQUIRED" && w.review_issue_groups?.length ? "请处理下方来源文字确认与人工裁定；同一事项的重复台账记录已合并操作入口。" : w.open_items.length?w.open_items.map(esc).join("；"):"全部交付条件已满足。"}</div>${tasks.length?`<div class="small mt-1">${running} 项处理中 · ${pending} 项等待执行${pending?"（等待执行端领取）":""}${expired?` · ${expired} 项领取已过期，等待执行端重新领取`:""}</div>`:""}</div><div class="col-auto"><button id="workbench-next" class="btn ${responsibility(w).kind==="user"?"btn-primary":"btn-outline-secondary"}" ${!w.sources.length&&action[1]?"disabled":""}>${existing?"查看已排队任务":esc(action[0])}</button></div></div></div></div>
    ${["confirm","templates"].includes(tab)?"":responsibilityPanel(w)+workflowGuide(w)}
    ${active==="overview"?`<div class="btn-list mb-3"><a class="btn ${tab==="overview"?"btn-primary":""}" href="#/w/${esc(w.id)}/overview">生成要求</a><a class="btn ${tab==="templates"?"btn-primary":""}" href="#/w/${esc(w.id)}/templates">选择模板</a></div>`:""}
    ${active==="summary"?`<div class="btn-list mb-3"><a class="btn ${tab==="summary"?"btn-primary":""}" href="#/w/${esc(w.id)}/summary">原文与总结</a><a class="btn ${tab==="confirm"?"btn-primary":""}" href="#/w/${esc(w.id)}/confirm">待确认与问题</a></div>`:""}
    <details class="mb-3"><summary class="text-secondary small">执行记录与内容明细</summary><div class="btn-list mt-2">${[["tasks","执行任务"],["facts","来源事实"],["deck","页面编排"]].map(([k,n])=>`<a class="btn btn-sm" href="#/w/${esc(w.id)}/${k}">${n}</a>`).join("")}</div></details>`;
}
function bindWorkbench(w, tab) {
  $("#reload").onclick=()=>route();
  const go = target => {
    const hash = `#/w/${w.id}/${target}`;
    if (location.hash === hash) { route(); flash("已刷新当前步骤，请查看下方记录与说明。", "info"); }
    else location.hash = hash;
  };
  $("#workbench-next").onclick=()=>{
    const action=STAGE_ACTIONS[w.stage] || [null,null,"overview"];
    if(action[1] && w.tasks.some(t=>t.kind===action[1] && ["PENDING","RUNNING"].includes(t.status))) go("tasks");
    else if(action[1]) act(()=>api("POST",`/workflows/${wid()}/tasks`,{kind:action[1]}),"任务已排队，等待执行端处理");
    else if(tab==="confirm" && action[2]==="confirm") ($("#confirmation-flow") || $("#show-human-decisions") || $("#tab"))?.scrollIntoView({behavior:"smooth",block:"start"});
    else go(action[2]);
  };
  clearTimeout(workbenchPoll);
  const id=w.id, stamp=JSON.stringify([w.stage,w.updated_at,w.tasks.map(t=>[t.id,t.status,t.attempts])]);
  const poll=async()=>{
    if(!current||current.id!==id) return;
    try {
      const next=await api("GET",`/workflows/${encodeURIComponent(id)}/progress`);
      const changed=JSON.stringify([next.stage,next.updated_at,next.tasks.map(t=>[t.id,t.status,t.attempts])])!==stamp;
      if(changed) {
        // Never destroy unsaved edits or move an operator away from a review.
        if(document.activeElement?.matches("input,textarea,select")||document.querySelector('[data-unsaved="true"]')) {
          $("#reload").classList.add("btn-warning"); $("#reload").textContent="有新进度（保存后刷新）";
        } else { await route(); return; }
      }
    } catch (_) { /* keep the current screen and retry */ }
    workbenchPoll=setTimeout(poll,10000);
  };
  if(w.tasks.some(t=>["PENDING","RUNNING"].includes(t.status))) workbenchPoll=setTimeout(poll,10000);
}
function templateChooser(w) {
  const palettes=health.theme_palettes || {};
  return card("辅助配色方案",`<div class="card-body"><div class="row g-3">${health.themes.map(k=>{
    const p=palettes[k]||{};
    return `<div class="col-sm-6 col-lg-4"><button type="button" class="template-choice ${w.theme===k?"selected":""}" data-theme="${esc(k)}" aria-pressed="${w.theme===k}"><div class="template-sample" style="background:${esc(p.sky||"#f4f6fa")};color:${esc(p.ink||"#182433")}"><div class="fw-bold" style="color:${esc(p.primary||"#355e78")}">章节标题</div><div class="sample-rule" style="background:${esc(p.accent||"#355e78")}"></div><div class="small">清晰的层级 · 原生可编辑内容</div><div class="d-flex gap-1 mt-3">${[p.primary,p.accent,p.soft].filter(Boolean).map(c=>`<span class="sample-chip" style="background:${esc(c)}"></span>`).join("")}</div></div><div class="p-2 fw-medium">${esc(THEME_NAMES[k]||k)}${w.theme===k?' <i class="ti ti-check text-success"></i>':""}</div></button></div>`;
  }).join("")}</div><div class="form-hint mt-3">这里选择配色风格。上传自己的PPT模板可读取字体与配色；当前不继承其完整母版和版式。最终构图采用已选定的原生矢量路线。</div></div>`);
}
function bindTemplateChooser(){
  document.querySelectorAll("[data-theme]").forEach(b=>b.onclick=()=>act(()=>api("PATCH",`/workflows/${wid()}`,{theme:b.dataset.theme}),"已选择PPT风格"));
}
function academicTemplateChooser(w,templates){
  return card('选择学术PPT模板',`<div class="card-body"><div class="alert alert-info"><b>当前选择：${esc(w.visual_template?.name || '尚未选择学术模板')}</b><div class="mt-1">${w.visual_template?'制作时参照已选模板的构图、配色与原生样页。':'未选择时采用A路线默认的低饱和蓝灰设计。可先看样例，再选择。'}</div>${w.generation?'<div class="mt-2">本项目已开始视觉制作。更换模板会使已有视觉稿及相关视觉确认失效，需要按新模板重新制作；已确认的内容保留。</div>':''}</div><p class="text-secondary">每套有封面、章节、正文、对照、流程和表格六种实际样页。先按用途筛选，打开预览查看正文与表格，再点击“选择此模板”。选择后显示“已选择”。</p><div class="btn-list mb-3" role="group" aria-label="按模板用途筛选">${['全部','教学课件','论文答辩','临床汇报','学术研讨'].map((x,i)=>`<button type="button" class="btn btn-sm ${i===0?'btn-primary':''}" data-template-use="${esc(x)}" aria-pressed="${i===0}">${esc(x)}</button>`).join('')}</div><div class="row g-3">${templates.map(t=>`
    <div class="col-md-6 col-xl-4" data-template-card data-template-uses="${esc((t.uses||[]).join('|'))}"><div class="card h-100 ${w.visual_template?.id===t.id?'border-primary':''}">
      <a href="${esc(t.preview_url||t.design_url||'#')}" target="_blank" rel="noopener"><img src="${esc(t.preview_url||t.design_url||'')}" class="w-100" alt="${esc(t.name)}六页原生预览" loading="lazy"></a>
      <div class="card-body"><h4>${esc(t.name)} ${w.visual_template?.id===t.id?'✓ 已选择':''}</h4><p class="mb-2">${esc(t.suitable_for||'学术演示与内容汇报。')}</p><div class="small text-secondary mb-2">${esc(t.tone||'')} · ${esc(t.status)}</div><div class="d-flex gap-2 mb-3">${Object.values(t.palette||{}).map(c=>`<span class="sample-chip" style="background:${esc(c)};border:1px solid #ccd3db" title="${esc(c)}"></span>`).join('')}</div><div class="btn-list">
      ${t.ready?`${w.id?`<button class="btn btn-primary btn-sm" data-academic-template="${esc(t.id)}" ${w.visual_template?.id===t.id?'disabled':''}>${w.visual_template?.id===t.id?'已选择':'选择此模板'}</button>`:''}<a class="btn btn-sm" href="/api/deck/templates/${esc(t.id)}/deck.pdf" target="_blank">查看六页样例</a><details class="w-100"><summary class="small text-secondary">下载可编辑样例与模板</summary><div class="btn-list mt-2"><a class="btn btn-sm" href="/api/deck/templates/${esc(t.id)}/template.potx">POTX模板</a><a class="btn btn-sm" href="${esc(t.download_url)}">PPTX样例</a></div></details>`:'<button class="btn btn-sm" disabled>重建检查中</button>'}
      <a class="btn btn-sm" href="${esc(t.design_url||'#')}" target="_blank" rel="noopener">原始设计稿</a></div></div>
    </div></div>`).join('')}</div>${w.visual_template?'<button class="btn btn-sm mt-3" id="clear-academic-template">取消学术模板选择</button>':''}</div>`);
}
function bindAcademicTemplates(){
  document.querySelectorAll('[data-template-use]').forEach(b=>b.onclick=()=>{
    document.querySelectorAll('[data-template-use]').forEach(x=>{x.classList.toggle('btn-primary',x===b);x.setAttribute('aria-pressed',String(x===b));});
    document.querySelectorAll('[data-template-card]').forEach(x=>x.hidden=b.dataset.templateUse!=='全部'&&!x.dataset.templateUses.split('|').includes(b.dataset.templateUse));
  });
  const changeTemplate=id=>{
    if(current.generation && !confirm('本项目已开始视觉制作。更换模板需要重做已有视觉稿和相关视觉审核；已确认的内容保留。是否应用？'))return;
    act(()=>api('PATCH',`/workflows/${wid()}`,{visual_template:id}),'模板选择已保存；制作时按新模板执行');
  };
  document.querySelectorAll('[data-academic-template]').forEach(b=>b.onclick=()=>changeTemplate(b.dataset.academicTemplate));
  const clear=$('#clear-academic-template');if(clear)clear.onclick=()=>changeTemplate(null);
}
function sourceEvidencePanel(w) {
  const options=w.sources.flatMap(s=>s.pages.map(p=>`<option value="${esc(s.id)}|${esc(p.id)}">${esc(s.filename)} · ${esc(p.location)}</option>`)).join("");
  return `<aside class="card source-evidence"><div class="card-header"><h3 class="card-title">对照原始资料</h3></div><div class="card-body"><label for="source-page" class="form-label">来源页面</label><select id="source-page" class="form-select mb-3">${options}</select><div id="source-evidence-body"></div></div></aside>`;
}
function bindSourceEvidence(){
  const select=$("#source-page"); if(!select) return;
  const show=()=>{
    const [sid,pid]=select.value.split("|"), s=current.sources.find(s=>s.id===sid); if(!s)return;
    const image=url(`/sources/${encodeURIComponent(sid)}/pages/${encodeURIComponent(pid)}/image`);
    const units=[...s.units,...s.transcriptions].filter(u=>u.page_id===pid);
    $("#source-evidence-body").innerHTML=`<a href="${image}" target="_blank" rel="noopener"><img class="source-page-image" src="${image}" alt="原始资料页面"><span class="small">打开原页大图</span></a><details class="mt-3"><summary>查看原文与转录</summary>${units.map(u=>`<div class="quote border-bottom py-2"><b>${esc(u.location)}</b><div>${esc(u.text)}</div></div>`).join("")}</details>`;
    $(".source-page-image").onerror=ev=>{ev.target.hidden=true;};
  };
  select.onchange=show;show();
  document.querySelectorAll("[data-source-page]").forEach(b=>b.onclick=()=>{
    const p=b.dataset.sourcePage,s=current.sources.find(s=>s.pages.some(p2=>p2.id===p));
    if(s){select.value=`${s.id}|${p}`;show();}
  });
}
function summaryEditor(w){
  if(!w.summary||!w.approval_subjects.content)return "";
  return `<details class="card mb-3"><summary class="card-body fw-bold">修订总结文字</summary><form id="summary-edit" class="card-body pt-0"><div class="form-hint mb-3">修改后需重新独立审核及确认，原文引用保留。新增内容应有实际来源支持。</div><label class="form-label">整章总述</label><textarea class="form-control mb-3" name="overall" rows="4" required>${esc(w.summary.overall_summary)}</textarea>${w.summary.sections.map((s,i)=>`<fieldset class="mb-3"><legend class="form-label">${esc(s.title)}</legend><textarea name="section_${i}" class="form-control mb-2" rows="3" required>${esc(s.summary)}</textarea>${(s.key_points||[]).map((p,j)=>`<label class="form-label small">要点 ${j+1}</label><textarea name="point_${i}_${j}" class="form-control mb-2" rows="2" required>${esc(p.point)}</textarea>`).join("")}</fieldset>`).join("")}<label class="form-label">待处理事项（每行一项，解决后可移除；保存后仍须独立复核）</label><textarea name="pending" class="form-control mb-3" rows="3">${esc(w.summary.pending_issues.map(x=>typeof x==="string"?x:JSON.stringify(x)).join("\n"))}</textarea><button class="btn btn-primary">保存修订并重新审核</button></form></details>`;
}
function bindSummaryEditor(){
  const form=$("#summary-edit");if(!form)return;
  form.oninput=()=>form.dataset.unsaved="true";
  form.onsubmit=ev=>{
    ev.preventDefault();const data=new FormData(form),result=structuredClone(current.summary);
    result.overall_summary=String(data.get("overall"));
    result.sections.forEach((s,i)=>{s.summary=String(data.get(`section_${i}`));s.key_points.forEach((p,j)=>p.point=String(data.get(`point_${i}_${j}`)));});
    result.pending_issues=String(data.get("pending")).split("\n").map(s=>s.trim()).filter(Boolean);
    act(async()=>{
      const id=wid(),w=await api("PUT",`/workflows/${id}/summary`,{operator:me(),result});
      form.dataset.unsaved="false";
      try {await api("POST",`/workflows/${id}/tasks`,{kind:"SUMMARY_REVIEW"});flash("修订已保存，独立审核已排队","success");}
      catch(e){flash("修订已保存；审核排队失败，请使用上方按钮重试："+e.message,"warning");}
      return w;
    });
  };
}
