"""Persistent A-route orchestration for the Codex + Adobe execution endpoint.

Tool calls stay outside the application. Each accepted result queues its successor;
only native compilation/rendering runs inside the application, after all assets exist.
"""
from __future__ import annotations

import copy
from functools import lru_cache
import io
import json
import math
import secrets
import time
from pathlib import Path

from app.fact57098 import digest, sha, now, uid, require, WorkflowError
from factdeck.visual_layout import PALETTE, contract, accept_layout, text_of
from app.deck_scope import selected_spec, scope_of

VISUAL_KINDS=("VISUAL_DESIGN","VISUAL_LAYOUT","VISUAL_CLEAN","VISUAL_VECTOR","VISUAL_BLIND_READ")
ROUTE="A_NATIVE_VECTOR"
VERSION="factdeck.visual-a.1"
NATIVE_RENDER_VERSION="factdeck.visual-native-export.5"
ASSET_KIND={"VISUAL_DESIGN":"design","VISUAL_CLEAN":"clean","VISUAL_VECTOR":"vector"}
# Accepted tool names per stage. Adobe image_instruct_edit was tried for CLEAN and kept
# footer text; its connector also caps prompts at 1,500 characters.
ALLOWED_TOOLS={"VISUAL_DESIGN":["image_gen","image_gen.imagegen","image_gen__imagegen"],
               "VISUAL_CLEAN":["image_gen","image_gen.imagegen","image_gen__imagegen"],
               "VISUAL_VECTOR":["adobe_image_vectorize","mcp__codex_apps__adobe_image_vectorize"]}
CLEAN_PROMPT_LIMIT=1500
# Pages in flight at once. Later pages are queued as earlier ones finish, so a
# first-design revision does not cancel a whole deck of queued tasks.
DEFAULT_BATCH_SIZE=5
# Part of the design fingerprint: a brief change makes still-pending design tasks stale, so
# they are re-issued with the new brief instead of being run on the old one.
DESIGN_BRIEF_VERSION="design-brief.10"
# Content pages: the executor reads the page's locked text and writes a drawing plan (relation +
# terms + a closed object list, config/visual_grammar.json); the image call uses the brief prompt
# plus that list. An independent blind read of the text-free image is compared with the plan.
from factdeck.visual_grammar import plan_prompt, PLAN_MARK, illustrated  # noqa: E402  re-exported for workers and tests


def page_passages(p):
    """Passages a plan may draw from: every locked text except titles, plus table cells."""
    m=p["lock"]["model"]
    texts=[text_of(t) for t in m["texts"] if t.get("role")!="title" and text_of(t).strip()]
    return texts+[text_of(c) for tb in m["tables"] for row in tb["rows"] for c in row["cells"] if text_of(c).strip()]


def page_focus(w,page_id):
    """The page focus (deck spec `focus`) as displayed text, from the fact store or the deck's carved facts."""
    page=next((x for x in selected_spec((w.get('deck') or {}).get('result') or {}).get('pages',[]) if x.get('id')==page_id),None)
    fid=((page or {}).get('focus') or {}).get('fact')
    if not fid: return ""
    for f in ((w.get('facts') or {}).get('result') or {}).get('facts',[])+((w.get('deck') or {}).get('result') or {}).get('facts',[]):
        if f.get('id')==fid: return f.get('display') or f.get('quote') or ""
    return ""


def plan_of(p):
    d=p["assets"].get("design")
    return ((d or {}).get("receipt") or {}).get("qa",{}).get("illustration_plan") if d else None


def requires_blind_read(p):
    return bool((plan_of(p) or {}).get("units"))


# Page roles. Cover-type pages share the cover's print-style artwork; content pages carry an
# explanatory graphic shaped by their own information (classification, comparison, condition, scope).
COVER_LAYOUTS={"cover","divider","closing"}


def bound_standard(w):
    registry=Path(__file__).resolve().parents[1]/'config/visual_standard_bindings.json'
    if not registry.is_file():return None
    binding=json.loads(registry.read_text(encoding='utf-8')).get(w['id'])
    if not binding:return None
    if binding.get('template_id')!=(w.get('visual_template') or {}).get('id'):return None
    root=registry.parents[1];path=(root/binding['standard_path']).resolve()
    require(path.is_relative_to(root.resolve()) and path.is_file(),'视觉标准文件不可用')
    require(sha(path.read_bytes())==binding['standard_sha256'],'视觉标准绑定已变化')
    standard=json.loads(path.read_text(encoding='utf-8'))
    require(standard.get('frozen') is True and standard.get('final_native_visual_approval') is True,'视觉标准尚未确认')
    return standard,binding,path


def effective_visual_standard(w):
    bound=bound_standard(w)
    if not bound:return None
    standard,binding,_=bound
    return {'version':standard['version'],'sha256':binding['standard_sha256'],'model':standard['model'],'policy':binding['policy']}


@lru_cache(maxsize=256)
def _file_sha(path: str, mtime_ns: int, size: int) -> str:
    return sha(Path(path).read_bytes())


def verified_file(path: Path, want: str, root: Path) -> bool:
    """A reference image is usable when it lies under its root and still has the recorded checksum. Hashing is cached
    per (path, mtime, size), so fingerprints computed inside transactions do not re-read unchanged files."""
    try:
        path=path.resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file(): return False
        st=path.stat()
        return _file_sha(str(path),st.st_mtime_ns,st.st_size)==want
    except OSError:
        return False


def standard_content_references(w):
    """The confirmed standard's content-page samples as actual text-free clean images (its prompt
    protocol prefers clean images as structure/colour reference). The cover sample is excluded."""
    bound=bound_standard(w)
    if not bound:return []
    standard,_,path=bound; refs=[]
    for page in standard.get('pages',[]):
        if page.get('render_reference'):continue          # the cover sample, rebuilt from a supplied design
        f=(path.parent/'native_assets'/page['trial_id']/'clean.png').resolve()
        want=page['assets_sha256']['clean.png']
        if not verified_file(f,want,path.parent): continue       # missing or changed: left out, never fatal
        refs.append({'name':f"standard_content_{int(page['page']):02d}",'sha256':want,'path':f})
    return refs


def project_content_references(w):
    """User-supplied reference images for this project's content pages (config/visual_references.json)."""
    registry=Path(__file__).resolve().parents[1]/'config/visual_references.json'
    if not registry.is_file():return []
    entry=json.loads(registry.read_text(encoding='utf-8')).get(w['id']) or {}
    root=registry.parents[1].resolve(); refs=[]
    for r in entry.get('content',[]):
        f=(root/r['path']).resolve()
        if not verified_file(f,r['sha256'],root): continue      # missing or changed: left out, never fatal
        refs.append({'name':r['name'],'sha256':r['sha256'],'path':f})
    return refs


def content_references(w):
    """Project references when the user supplied them, else the confirmed standard's content samples."""
    return project_content_references(w) or standard_content_references(w)


def page_layout(w,page_id):
    page=next((p for p in selected_spec((w.get('deck') or {}).get('result') or {}).get('pages',[]) if p.get('id')==page_id),None)
    return (page or {}).get('layout','')


def page_role(w,page_id):
    page=next((p for p in selected_spec((w.get('deck') or {}).get('result') or {}).get('pages',[]) if p.get('id')==page_id),None)
    return 'cover' if page and page.get('layout') in COVER_LAYOUTS else 'content'


def base_input(w):
    from app.deckflow import render_input
    return render_input(w, include_visual=False)


def current(w):
    g=w.get("generation")
    return bool(g) and g["input_sha256"]==base_input(w)


def ready(w):
    from app.deckflow import semantic_current, open_issues
    g=w.get('generation')
    if not g or not all(p.get('layout') and set(p['assets'])=={'design','clean','vector'} for p in g['pages']):return False
    if not all(not requires_blind_read(p) or (p.get('blind_read') or {}).get('status')=='PASS' for p in g['pages']):return False
    return current(w) and semantic_current(w) and not open_issues(w)


def render_fingerprint(w):
    if not current(w): return None
    g=w["generation"]
    return digest({"version":VERSION,"renderer":NATIVE_RENDER_VERSION,"id":g["id"],"pages":[{"id":p["id"],"assets":{k:a["sha256"] for k,a in p["assets"].items()},"layout":p.get("layout")} for p in g["pages"]]})


def view(w):
    g=w.get("generation")
    if not g: return {"route":w.get("generation_route", "CODE_NATIVE"),"status":"NOT_STARTED","pages":[],"cost":{"tool_calls":0}}
    tasks=[t for t in w["tasks"] if t["kind"] in VISUAL_KINDS and t.get("generation_id")==g["id"]]
    result={"id":g["id"],"route":ROUTE,"current":current(w),"status":g["render"]["status"] if ready(w) else "WAITING_WORKER",
            "pages":[],"render":{k:v for k,v in g["render"].items() if k not in {"lease_token"}},"cost":{},"input_sha256":g["input_sha256"]}
    result['scope']=g.get('scope');result['complete_deck']=not bool(g.get('scope'))
    if not current(w): result["status"]="STALE"
    elif any(t["status"]=="FAILED" for t in tasks): result["status"]="FAILED"
    all_assets=[a for p in g['pages'] for group in [p['assets'],*[h['assets'] for h in p.get('history',[])]] for a in group.values()]
    receipts=list({(a['receipt']['tool'],a['receipt']['tool_call_id']):a['receipt'] for a in all_assets}.values())
    result["cost"]={"accepted_tool_calls":len(receipts),"task_attempts":sum(t["attempts"] for t in tasks),
                    "retry_attempts":sum(max(0,t["attempts"]-1) for t in tasks),"reported_tool_seconds":round(sum(r["elapsed_seconds"] for r in receipts if r.get("elapsed_seconds") is not None),3),
                    "unknown_tool_timings":sum(r.get("elapsed_seconds") is None for r in receipts),
                    "asset_bytes":sum(a["bytes"] for p in g["pages"] for a in p["assets"].values()),
                    "archived_asset_bytes":sum(a['bytes'] for a in {a['sha256']:a for a in all_assets}.values()),
                    "preparation_seconds":g.get("preparation_seconds"),"render_seconds":g["render"].get("seconds"),"output_bytes":g["render"].get("output_bytes"),
                    "currency_cost":None,"note":"仅记录已提交实际调用与任务尝试；未提交的调用无法计数，无真实费用数据。耗时缺失单独计数，不按零耗时处理；并发调用的等待时间可能重叠。"}
    for p in g["pages"]:
        pending=[t for t in tasks if t["binding"]==p["id"] and t["status"] in {"PENDING","RUNNING","FAILED"}]
        result["pages"].append({"id":p["id"],"stages":{**{k:k in p["assets"] for k in ("design","clean","vector")},"layout":bool(p.get("layout"))},
                                "tasks":[{k:t[k] for k in ("id","kind","status","attempts","error")} for t in pending],
                                "assets":{k:{"sha256":a["sha256"],"bytes":a["bytes"],"url":f'/api/deck/workflows/{w["id"]}/generation/assets/{p["id"]}/{k}'} for k,a in p["assets"].items()}})
        if (p.get("layout") or {}).get("preflight"): result["pages"][-1]["preflight"]=p["layout"]["preflight"]
        if requires_blind_read(p):
            br=p.get("blind_read") or {}
            result["pages"][-1]["blind_read"]={"status":br.get("status","PENDING"),"issues":br.get("issues",[]),"worker":br.get("worker")}
        pv=p.get("preview")
        if pv and pv.get("fingerprint")==digest({"renderer":NATIVE_RENDER_VERSION,"assets":{k:a["sha256"] for k,a in p["assets"].items()},"layout":p.get("layout")}):
            result["pages"][-1]["preview"]={**{k:pv.get(k) for k in ("status","error","issues","seconds","at")},
                                            "url":f'/api/deck/workflows/{w["id"]}/generation/previews/{p["id"]}' if pv.get("slide") else None}
    return result


class GenerationMixin:
    visual_preflight=True    # browser preflight at layout submission (tests with invented fixtures may turn it off)
    def generation_view(self,workflow_id):
        # Status polling needs generation data, not summary-ledger projections.
        with self.connect() as db:
            row=db.execute('SELECT state FROM workflows WHERE id=?',(workflow_id,)).fetchone()
        require(row,'项目不存在',404)
        return view(json.loads(row[0]))
    def generation_fingerprint(self,w,kind,page_id):
        require(current(w),"生成输入已过期，请重新启动生成")
        g=w["generation"]; p=next(p for p in g["pages"] if p["id"]==page_id)
        needed={"VISUAL_DESIGN":[],"VISUAL_LAYOUT":["design"],"VISUAL_CLEAN":["design"],"VISUAL_VECTOR":["clean"],"VISUAL_BLIND_READ":["design","clean"]}[kind]
        refs={k:p["assets"][k]["sha256"] for k in needed}
        if kind=="VISUAL_DESIGN":
            from factdeck.visual_grammar import grammar
            refs.update({k:v["sha256"] for k,v in self.design_references(w,p).items()}); refs["brief"]=DESIGN_BRIEF_VERSION; refs["grammar"]=digest(grammar())
        return digest({"version":VERSION,"generation":g["id"],"input":g["input_sha256"],"page":p["id"],"revision":p.get("revision",0),"kind":kind,"lock":p["lock"],"references":refs,
                       "layout":p.get("layout") if kind in {"VISUAL_CLEAN","VISUAL_VECTOR"} else None, **({'visual_standard':effective_visual_standard(w)} if effective_visual_standard(w) else {})})

    def design_references(self,w,p):
        """Reference images for a page's design: cover-type pages follow the first design;
        content pages follow the confirmed standard's content samples when one is bound."""
        g=w["generation"]; first=g["pages"][0]
        if p is first: return {}
        standard=content_references(w) if page_role(w,p["id"])=="content" else []
        if standard:
            return {r["name"]:{"sha256":r["sha256"],"url":f'/api/deck/workflows/{w["id"]}/visual-standard/{r["name"]}',"local_path":str(r["path"])} for r in standard}
        if "design" not in first["assets"]: return {}
        return {"style_reference":{"sha256":first["assets"]["design"]["sha256"],"url":f'/api/deck/workflows/{w["id"]}/generation/assets/{first["id"]}/design',"local_path":str(self.path(first["assets"]["design"]["path"]))}}

    def generation_brief(self,w,kind,page_id):
        g=w["generation"]; p=next(p for p in g["pages"] if p["id"]==page_id)
        required={"VISUAL_DESIGN":[],"VISUAL_LAYOUT":["design"],"VISUAL_CLEAN":["design"],"VISUAL_VECTOR":["clean"],"VISUAL_BLIND_READ":["clean"]}[kind]
        refs={k:{"sha256":p["assets"][k]["sha256"],"url":f'/api/deck/workflows/{w["id"]}/generation/assets/{page_id}/{k}',"local_path":str(self.path(p["assets"][k]["path"]))} for k in required}
        if kind=="VISUAL_DESIGN": refs.update(self.design_references(w,p))
        text_lock=[text_of(t) for t in p["lock"]["model"]["texts"]]
        tables=[[[text_of(c) for c in row["cells"]] for row in t["rows"]] for t in p["lock"]["model"]["tables"]]
        common={"schema_version":VERSION,"route":ROUTE,"page_id":page_id,"input_sha256":self.generation_fingerprint(w,kind,page_id),
                "locked_objects":contract(p["lock"]["model"]),"design":p["lock"]["design"],"palette":g["palette"],"assets":refs,
                "rules":["事实与来源来自内容锁；设计图不得增加实质结论、数值或关系。",
                         "必须使用真实工具、实际输出与完整提示词；失败请回报，禁止伪造调用或检查。",
                         "使用工具前下载 refs 中的实际图片，按实际工具要求传本地路径。任务租约15分钟，长调用须续约。"]}
        if kind=="VISUAL_BLIND_READ":
            from factdeck.visual_grammar import grammar
            common.pop("design",None)   # the reader sees the text-free picture and the page text only, never the plan
            common["passages"]=page_passages(p); common["relation_types"]=list(grammar()["relations"])
            common["rules"]=["独立盲读：只看 assets 中的去字图和本页原文 passages，不看作图方案或设计稿。",
                             "逐个清点图中能认出的对象，写出它对应的本页原文词句（逐字）；对应不上的写“无”。",
                             "写出图中各组对象表达的关系：类型取自 relation_types，spans 为表达该关系的原文词句。认不出就不写，不要猜。",
                             "执行端身份须不同于本页设计稿与去字稿的作者。"]
            common["result_contract"]={"input_sha256":common["input_sha256"],"inspected":False,
                                       "objects":[{"description":"图中看到的一个对象","bound_to":"对应的本页原文词句，对应不上写“无”"}],
                                       "relations":[{"type":"relation_types 之一","spans":["表达该关系的原文词句"]}]}
            return common
        if kind=="VISUAL_LAYOUT":
            common["result_contract"]={"input_sha256":common["input_sha256"],"design_inspected":False,"objects":[{k:s[k] for k in ("id","x","y","w","h")} for s in common["locked_objects"]["slots"]],
                                       "components":[{"name":"视觉组件","x":0,"y":0,"w":1280,"h":720}],"differences":[]}
            common["rules"].append("版面以实际设计稿为准：逐个对象把坐标、宽高、字号和颜色调整到设计稿中这段文字所在的位置；默认坐标只是内容锁的原位置，不得未经对照直接提交。原生色块不得盖住设计稿里的插画。")
            return common
        if kind=="VISUAL_DESIGN":
            style="遵循已选客户模板的配色令牌和字体；保留品牌视觉约定。" if w["theme"]=="brand" else "米白底、炭黑正文、低饱和墨蓝重点。不要高亮电蓝。"
            standard_refs=any(k.startswith(("standard_content_","project_reference_")) for k in refs)
            if w.get('visual_template'):
                template=w['visual_template']
                # The template sheet carries placeholder headings and a landscape divider; with the
                # confirmed standard's text-free samples present it is not sent as an image.
                if not standard_refs: refs['academic_template']={'sha256':template['design_sha256'],'url':f'/api/deck/workflows/{w["id"]}/visual-template'}
                style='参照已选学术模板'+template['name']+'的实际六页设计稿，按内容形态选择匹配构图；使用其配色与图形语言。占位文字不作为事实，不照搬示例流程。'+json.dumps(template['palette'],ensure_ascii=False)
            if page_role(w,page_id)=="cover":
                role="本页是封面类页面：可使用版画式插画作为整页背景。参考首张设计稿统一整套视觉。"
            elif not illustrated(page_layout(w,page_id)):
                role="本页是正文页，图形就是原生表格、原件图或目录本身，不另画说明插画；不使用整页背景插画或风景元素，装饰只限角落少量。"
            else:
                from factdeck.visual_grammar import prompt_text
                role=("本页是正文页。视觉主体是按文末作图清单画出的说明插画，帮助读者理解这段文字；图标只能作辅助。"
                      +prompt_text(page_layout(w,page_id))
                      +("参考图只示范如何把文字逻辑画成简化示意图（画法、线条与配色）；参考图中的文字、条目和具体内容一律不得出现，也不得据此增加本页没有的要素。" if any(k.startswith("project_reference_") for k in refs)
                        else "参考图为已确认标准的正文页无字清图，只取配色、线条与留白风格，不照搬其版式。" if standard_refs else "参考首张设计稿的配色与线条风格，不复制其背景。"))
            prompt="生成一页带全部文字的完整演示文稿设计稿，16:9。"+style+"清楚网格、阅读顺序和克制装饰。"+role+"页面上只能出现下方 text 与 tables 中的文字，逐字照抄，不改写、不增删；参考图中的任何文字、标题或示例内容都不得出现。所有锁定文字、表格、限定条件与来源完整呈现；不要编造图形表达的新数值或关系。此图片用于后续拆解重建原生PPT，文字区留出可读容量。\n"
            prompt+=json.dumps({"design":p["lock"]["design"],"palette":g["palette"],"text":text_lock,"tables":tables,"native_objects":common["locked_objects"]},ensure_ascii=False)
        elif kind=="VISUAL_CLEAN":
            native_tables=p['layout']['model']['tables']
            prompt="编辑实际设计稿：彻底去除所有文字、字母、数字、单位、标志、水印、文字阴影和残留字符。只移除数据柱、流程连接线和箭头，之后由原生对象按照锁定内容填回。说明插画（人物、事物与示意图形）不是待移除的图形，必须全部完整保留。"
            if native_tables:
                prompt+="彻底删除整块表格，包括表头色块、外框、交替行底色、行线、列线和全部单元格边界；整个表格矩形区域必须补成与周围相同的米白背景，不得留下任何空表格结构。仅保留非表格的装饰色块、插画与构图，包括主体插画与页底装饰。"
            else:
                prompt+="本页没有待重建的原生表格。卡片容器不是表格，禁止删除卡片。完整保留所有卡片的底色、外框和标题色带，圆形图标底座与非文字图标轮廓，标题装饰短线、主体插画和页底装饰。只清除其中的文字与数字，不改变这些非文字装饰与容器的布局。"
            prompt+="移除原件证据图与品牌标志的重绘，保留这些对象的占位留白，最终使用实际原件填回。补齐去字区域的背景。不要新增含义或符号。请逐页看实际输出确认无残字。"
            # Region geometry is structured contract data, not prompt text: it keeps
            # the edit prompt within tool limits and is not something an image edit can parse.
            common["regions"]={"native_regions":p["layout"]["components"],"native_table_regions":[{k:t[k] for k in ('x','y','w','h')} for t in native_tables],"locked_boxes":contract(p["layout"]["model"])["slots"]}
        else: prompt="使用 Adobe image_vectorize 对实际去字 PNG 进行矢量化，提交实际 SVG，不得以图片、手写替代SVG或整页截图伪装工具输出。"
        standard=effective_visual_standard(w)
        if standard and kind=='VISUAL_DESIGN':
            prompt+='\n已由用户确认的视觉标准：'+json.dumps(standard,ensure_ascii=False)
        elif standard and kind=='VISUAL_CLEAN':
            prompt+='\n遵循已确认视觉标准 '+standard['version']+'（'+standard['sha256'][:12]+'），保留其插画与容器。'
        if standard:common['visual_standard']=standard
        if kind=="VISUAL_CLEAN": require(len(prompt)<=CLEAN_PROMPT_LIMIT,"去字提示词超过工具上限")
        common["prompt"]=prompt
        common["allowed_tools"]=ALLOWED_TOOLS[kind]
        if kind=="VISUAL_DESIGN" and page_role(w,page_id)=="content" and illustrated(page_layout(w,page_id)) and page_passages(p):
            from factdeck.visual_grammar import brief as grammar_brief
            layout=page_layout(w,page_id)
            common["illustration_plan_contract"]={"required":True,"mark":PLAN_MARK,"layout":layout,"grammar":grammar_brief(layout,page_passages(p),page_focus(w,page_id)),
                "schema":{"units":[{"text":"本页逐字片段","relation":{"type":"grammar.relations 之一","span":"原文表达该关系的词句（entity 可空）"},
                                    "terms":[{"span":"该单元原文中的逐字片段","role":"该项在关系中的角色"}],
                                    "draw":[{"object":"要画的对象（非派生时须含所绑定的原文）","bound_to":"所绑定的项或关系词句","derivation":"空，或 grammar.derivations 之一"}],
                                    "encoding":"空间排布（可空，用该关系的默认排布）"}],
                          "omitted":[{"text":"本页逐字片段","reason":"grammar.omission_reasons 之一"}],"arrangement":"插画与文字的位置关系"},
                "rules":["先读 grammar.passages：focus 段落必须配图；标有 candidates 的段落须配图，或以规定原因略去。",
                         "先运行 codex_worker.py design-prompt：它检查方案并生成完整提示词，方案不合格时不生图；把提示词原样交给 image_gen。",
                         "看图确认清单中每个对象都画出、清单外没有多画；之后由另一执行端独立盲读去字图，与方案比对。"]}
        if kind=="VISUAL_CLEAN": common["rules"].append("去字只用 ImageGen 编辑；Adobe image_instruct_edit 已实测保留页脚文字，不在可用工具之列。")
        common["receipt_contract"]={"contract_sha256":common["input_sha256"],"asset_sha256":"实际文件SHA256","tool":ALLOWED_TOOLS[kind][0],
                                    "tool_call_id":"实际调用标识","prompt":prompt,"input_assets":{k:v["sha256"] for k,v in refs.items()},"elapsed_seconds":0,
                                    "qa":{"inspected":False,**({"text_free":False,"semantic_graphics_removed":False,"illustrations_kept":False} if kind=="VISUAL_CLEAN" else {})}}
        return common

    def _advance_generation(self,w):
        if not current(w): return
        g=w["generation"]; size=g.get("batch_size") or DEFAULT_BATCH_SIZE
        live=[t for t in w["tasks"] if t.get("generation_id")==g["id"] and t["kind"] in VISUAL_KINDS and t["status"] in {"PENDING","RUNNING","FAILED"}]
        # Started pages always continue; unstarted pages wait for a free batch slot.
        # Never-claimed design tasks beyond the window are withdrawn (no work is lost).
        started=[p["id"] for p in g["pages"] if (p["assets"] or p.get("layout")) and not (p.get("layout") and {"design","clean","vector"}<=set(p["assets"]))]
        waiting=[t for t in live if t["kind"]=="VISUAL_DESIGN" and t["binding"] not in started]
        slots=max(0,size-len(started))
        focus=g.get("focus_pages") or []
        for t in sorted(waiting,key=lambda t:t["binding"] not in focus):
            if t["status"]=="PENDING" and t["attempts"]==0 and (slots<=0 or (focus and t["binding"] not in focus)): t.update(status="CANCELLED",error="批次窗口外，按批次重新排队")
            else: slots-=1
        # Named sample pages (generate --pages) take the free batch slots first; deck order otherwise.
        focus=g.get("focus_pages") or []
        ordered=sorted(enumerate(g["pages"]),key=lambda ip:(ip[1]["id"] not in focus,focus.index(ip[1]["id"]) if ip[1]["id"] in focus else ip[0]))
        for i,p in ordered:
            kinds=[]
            if "design" not in p["assets"]:
                if not (i and "design" not in g["pages"][0]["assets"]): kinds.append("VISUAL_DESIGN")
            elif not p.get("layout"): kinds.append("VISUAL_LAYOUT")
            elif "clean" not in p["assets"]: kinds.append("VISUAL_CLEAN")
            elif "vector" not in p["assets"]: kinds.append("VISUAL_VECTOR")
            if "clean" in p["assets"] and requires_blind_read(p) and not self.blind_read_current(w,p): kinds.append("VISUAL_BLIND_READ")
            for kind in kinds:
                fp=self.generation_fingerprint(w,kind,p["id"])
                if any(t["kind"]==kind and t["binding"]==p["id"] and t["input_sha256"]==fp and t["status"] in {"PENDING","RUNNING","FAILED"} for t in w["tasks"]): continue
                if kind=="VISUAL_DESIGN" and p["id"] not in started:
                    if slots<=0 or (focus and p["id"] not in focus): continue
                    slots-=1
                w["tasks"].append({"id":uid("task"),"kind":kind,"binding":p["id"],"generation_id":g["id"],"input_sha256":fp,"status":"PENDING","attempts":0,
                                   "created_at":now(),"worker":None,"lease_token":None,"lease_until":0,"error":None,"brief":self.generation_brief(w,kind,p["id"])})
        if ready(w) and g["render"]["status"]=="WAITING_ASSETS": g["render"]["status"]="PENDING"

    def start_generation(self,workflow_id,first_pages=None,batch_size=None,pages=None):
        require(batch_size is None or (isinstance(batch_size,int) and 1<=batch_size<=60),"批次页数须为1–60",422)
        from app.deckflow import deck_current, verified, checked, status, figures, render_input
        from factdeck.render import render as prepare
        w=self.get(workflow_id)
        if w.get("generation_route")=="TEMPLATE_LIB":     # template-library mainline: code render, no visual tasks
            return self.render(workflow_id)
        scope=scope_of((w.get('deck') or {}).get('result',{}))
        require(first_pages is None if not scope else first_pages==scope['page_count'], '本次须明确指定已核对的前N页范围',422)
        require(deck_current(w),"请先完成当前版本的页面规格")
        require(status(w)[0] not in {"CONFIRMATIONS_REQUIRED","SEMANTIC_REVIEW_REQUIRED","SEMANTIC_ISSUES","DECK_REVISION"},"正式渲染前需完成事实确认和独立语义审查")
        self.source_integrity(w)
        if current(w):
            with self.transaction(workflow_id,"GENERATION_RESUME") as w:
                g=w["generation"]
                if batch_size: g["batch_size"]=batch_size
                if pages is not None:
                    require(set(pages)<={p["id"] for p in g["pages"]},"指定页面不在本次生成中",422)
                    g["focus_pages"]=list(pages)
                self.cancel_stale(w)       # tasks issued with an older brief must not hold batch slots
                for t in w["tasks"]:
                    if t.get("generation_id")==g["id"] and t["status"]=="FAILED":
                        t["status"]="CANCELLED"  # keep attempt history; successor gets a new lease/identity
                outdated_export=g['render']['status']=='COMPLETE' and (w.get('render') or {}).get('input_sha256')!=render_input(w)
                if outdated_export or g["render"]["status"]=="FAILED" or (g["render"]["status"]=="RUNNING" and g["render"].get("lease_until",0)<time.time()):
                    g.setdefault("render_history",[]).append(copy.deepcopy(g["render"]))
                    g["render"]={"status":"PENDING","attempts":0,"error":None}
                self._advance_generation(w)
            return self.get(workflow_id)
        start=time.perf_counter(); key=base_input(w); v=verified(w); chk=checked(w,v)
        require(not chk["errors"],"页面规格有错误，请先修订")
        gid=uid("generation"); rel=f'{workflow_id}/generation-inputs/{gid}'; folder=self.path(rel)
        src={s["id"]:{"title":s["title"],"filename":s["filename"]} for s in w["sources"]}
        shown={v["facts"][f]["figure"] for p in chk["pages"] for f in p["facts"] if v["facts"][f].get("figure")}
        figs={k:{"path":str(self.path(g["path"])),"sha256":g["sha256"],"width":g["width"],"height":g["height"]} for k,g in figures(w).items() if k in shown}
        spec=selected_spec(w['deck']['result'])
        from app.deckflow import deck_teaching_notes
        report=prepare(spec,v["facts"],src,folder,self.render_theme(w),v["terms"],figures=figs,teaching_notes=deck_teaching_notes(w,spec))
        if report:
            require(not any(report["summary"].get(k,0) for k in ("fact_text_mismatch","untracked_text","pptx_missing_facts","pptx_missing_figures")),"内容锁准备时出现文字或原件图缺失，不能进入生成")
        lock=json.loads((folder/"native_model.json").read_text(encoding="utf8"))
        # Keep approved brand colors; otherwise use the user's muted A palette.
        if w["theme"]!="brand":
            from factdeck.render import THEMES
            old_ink=THEMES[w["theme"]]["ink"][1:].upper()
            def muted(obj):
                if isinstance(obj,dict):
                    if "hex" in obj:
                        h=obj["hex"].lstrip("#")
                        r,g,b=(int(h[i:i+2],16) for i in (0,2,4))
                        if h.upper()==old_ink: obj["hex"]=PALETTE["ink"][1:]
                        elif b-r>18 and b>g: obj["hex"]=PALETTE["primary"][1:]
                    for val in obj.values(): muted(val)
                elif isinstance(obj,list):
                    for val in obj: muted(val)
            muted(lock["models"])
            for m in lock["models"]:
                m["background"]={"hex":PALETTE["paper"][1:],"a":1}
                for table in m["tables"]:
                    for cell in table["rows"][0]["cells"]: cell["fill"]={"hex":PALETTE["table_header"][1:],"a":1}
        generation={"id":gid,"version":VERSION,"input_sha256":key,"route":ROUTE,"created_at":now(),"font":lock["font"],"palette":PALETTE if w["theme"]!="brand" else self.render_theme(w)["tokens"],
                    "preparation_seconds":round(time.perf_counter()-start,3),"preparation_path":rel,"pages":[],"figures":[],"logos":[],"render":{"status":"WAITING_ASSETS","attempts":0,"error":None}}
        generation['scope']=chk.get('scope'); generation['batch_size']=batch_size or DEFAULT_BATCH_SIZE
        if w.get('visual_template'):
            colors=w['visual_template']['palette']
            generation['palette']={**PALETTE,'primary':'#'+colors['accent'],'paper':'#'+colors['background'],'ink':'#'+colors['ink'],'table_header':'#'+colors['accent']}
            replacements={PALETTE['primary'][1:].upper():colors['accent'],PALETTE['table_header'][1:].upper():colors['accent'],PALETTE['ink'][1:].upper():colors['ink'],PALETTE['paper'][1:].upper():colors['background']}
            def selected_colors(obj):
                if isinstance(obj,dict):
                    if 'hex' in obj and obj['hex'].lstrip('#').upper() in replacements:obj['hex']=replacements[obj['hex'].lstrip('#').upper()]
                    for val in obj.values():selected_colors(val)
                elif isinstance(obj,list):
                    for val in obj:selected_colors(val)
            selected_colors(lock['models'])
        for p,m,n in zip(spec["pages"],lock["models"],lock["notes"]):
            # The compatibility template's text-free cover decoration is replaced
            # by the actual A artwork. It is not source content or a native overlay.
            m["rasters"]=[r for r in m["rasters"] if not r["id"].startswith("art-")]
            for r in m["rasters"]:
                logo=(w.get("brand") or {}).get("logo")
                require(logo and r["id"].startswith("logo-"),"A 路线不支持未归属来源的预渲染位图")
                generation["logos"].append({"id":r["id"],"path":logo["path"],"file":"logo"+Path(logo["path"]).suffix,"sha256":logo["sha256"]})
            generation["pages"].append({"id":p["id"],"revision":0,"lock":{"model":m,"notes":n,"design":p.get("design") or {},"chart":p.get("layout")=="chart"},"assets":{},"layout":None})
            for g in m.get("figures",[]):
                fid=g["id"]; source=figs[v["facts"][fid]["figure"]]
                generation["figures"].append({"fact_id":fid,"path":str(Path(source["path"]).relative_to(self.root)).replace("\\","/"),"file":"figure_"+source["sha256"][:24]+".png","sha256":source["sha256"]})
        with self.transaction(workflow_id,"GENERATION_START") as w2:
            require(base_input(w2)==key,"准备期间内容已变更，请重新启动生成")
            if not current(w2):
                if w2.get("generation"): w2.setdefault("generation_history",[]).append(w2["generation"])
                w2["generation_route"]=ROUTE; w2["generation"]=generation; self.cancel_stale(w2); self._advance_generation(w2)
        return self.get(workflow_id)

    def claim_order(self,tasks):
        # Finish pages already in flight before starting new ones: when a worker can take several
        # visual stages, later stages come first (vector, clean, layout, design); stable otherwise.
        return sorted(tasks,key=lambda t:-VISUAL_KINDS.index(t["kind"]) if t["kind"] in VISUAL_KINDS else 0)

    def layout_preflight(self,w,t,result):
        """The export's browser overflow/overlap gate plus contrast against the design, run before
        the clean/vector tool calls are spent. Slow browser work stays outside the SQLite transaction."""
        from factdeck.visual_qa import preflight_layout, contrast_issues
        p=next((p for p in (w.get("generation") or {}).get("pages",[]) if p["id"]==t.get("binding")),None)
        if not p or "design" not in p["assets"]: return None
        model=accept_layout(p["lock"]["model"],result,p["lock"]["chart"])
        checks=preflight_layout(model,w["generation"]["font"],result.get("components") or ())
        require(not checks["overflow"] and not checks["overlap"],
                "版面预检未通过（与最终导出同一检查）：文字溢出 "+"、".join(checks["overflow"][:5])+(f"；重叠 {checks['overlap'][:5]}" if checks["overlap"] else "")+"。请调整坐标或容量后重新提交",422)
        return {"overflow":[],"overlap":[],"contrast":contrast_issues(model,self.path(p["assets"]["design"]["path"])),"basis":"design"}

    def blind_read_current(self,w,p):
        r=p.get("blind_read")
        return bool(r) and r.get("fingerprint")==self.generation_fingerprint(w,"VISUAL_BLIND_READ",p["id"])

    def complete_blind_read(self,workflow_id,task_id,token,result):
        """Compare an independent reading of the text-free image with the page's drawing plan."""
        from factdeck.visual_grammar import read_issues
        with self.transaction(workflow_id,"VISUAL_BLIND_READ_COMPLETE") as w:
            t=self.leased(w,task_id,token); require(t["kind"]=="VISUAL_BLIND_READ","任务类型不符")
            require(isinstance(result,dict) and result.get("input_sha256")==t["input_sha256"],"盲读结果输入校验值不符",422)
            require(result.get("inspected") is True,"须查看实际去字图后提交",422)
            objects,relations=result.get("objects"),result.get("relations")
            require(isinstance(objects,list) and all(isinstance(o,dict) and isinstance(o.get("description"),str) and isinstance(o.get("bound_to"),str) for o in objects),
                    "objects 须为 [{description, bound_to}]",422)
            require(isinstance(relations,list) and all(isinstance(r,dict) and isinstance(r.get("type"),str) and isinstance(r.get("spans"),list) for r in relations),
                    "relations 须为 [{type, spans}]",422)
            p=next(p for p in w["generation"]["pages"] if p["id"]==t["binding"])
            issues=read_issues(plan_of(p) or {},result,page_passages(p))
            p["blind_read"]={"status":"FAIL" if issues else "PASS","issues":issues,"worker":t["worker"],"at":now(),
                             "fingerprint":t["input_sha256"],"result_path":self.snapshot(w,"visual_blind_read",result)}
            t.update(status="COMPLETE",completed_at=now(),lease_token=None,result_sha256=digest(result),result_path=p["blind_read"]["result_path"])
            self._advance_generation(w)
        return self.get(workflow_id)

    def complete_layout(self,workflow_id,task_id,token,result):
        draft=self.get(workflow_id); t0=next((t for t in draft["tasks"] if t["id"]==task_id),None)
        preflight=self.layout_preflight(draft,t0,result) if t0 and self.visual_preflight and isinstance(result,dict) else None
        with self.transaction(workflow_id,"VISUAL_LAYOUT_COMPLETE") as w:
            t=self.leased(w,task_id,token); require(t["kind"]=="VISUAL_LAYOUT","任务类型不符")
            require(result.get("input_sha256")==t["input_sha256"],"版面结果输入校验值不符")
            p=next(p for p in w["generation"]["pages"] if p["id"]==t["binding"])
            model=accept_layout(p["lock"]["model"],result,p["lock"]["chart"])
            p["layout"]={"model":model,"components":result["components"],"differences":result["differences"],"author":t["worker"],"at":now()}
            if preflight: p["layout"]["preflight"]=preflight
            t.update(status="COMPLETE",completed_at=now(),lease_token=None,result_sha256=digest(result),result_path=self.snapshot(w,"visual_layout_result",result))
            self._advance_generation(w)
        return self.get(workflow_id)

    def visual_asset(self,workflow_id,task_id,token,data,receipt):
        require(isinstance(receipt,dict),"调用回执必须为对象",422)
        with self.transaction(workflow_id,"VISUAL_ASSET_COMPLETE") as w:
            t=self.leased(w,task_id,token); require(t["kind"] in ASSET_KIND,"该任务不接收图片或 SVG",422)
            brief=t["brief"]; kind=t["kind"]
            require(receipt.get("contract_sha256")==t["input_sha256"] and receipt.get("asset_sha256")==sha(data),"调用回执与合同或实际文件不符",422)
            expected=brief["prompt"]
            if brief.get("illustration_plan_contract"):
                from factdeck.visual_grammar import check_plan
                plan=(receipt.get("qa") or {}).get("illustration_plan"); c=brief["illustration_plan_contract"]
                p0=next(p for p in w["generation"]["pages"] if p["id"]==t["binding"])
                try: check_plan(plan,c["layout"],page_passages(p0),c["grammar"]["focus"])
                except ValueError as e: require(False,str(e),422)
                expected=plan_prompt(brief["prompt"],plan)
            require(receipt.get("prompt")==expected and receipt.get("input_assets")==brief["receipt_contract"]["input_assets"],"完整提示词或参考资产不符",422)
            require(isinstance(receipt.get("tool_call_id"),str) and bool(receipt["tool_call_id"].strip()),"缺少实际调用标识",422)
            seconds=receipt.get("elapsed_seconds")
            unknown=seconds is None and receipt.get("timing_status")=="UNKNOWN_AFTER_INTERRUPTION" and bool(receipt.get("timing_note"))
            require(unknown or (not isinstance(seconds,bool) and isinstance(seconds,(int,float)) and math.isfinite(seconds) and seconds>=0),"调用耗时无效",422)
            tool=receipt.get("tool")
            require(tool in ALLOWED_TOOLS[kind],"须使用约定的真实工具",422)
            qa=receipt.get("qa") or {}; require(qa.get("inspected") is True,"须查看实际输出后提交检查记录",422)
            if kind=="VISUAL_CLEAN": require(qa.get("illustrations_kept") is True,"去字稿须确认说明插画已完整保留（只去文字、数据柱和连接线）",422)
            if kind=="VISUAL_CLEAN": require(qa.get("text_free") is True and qa.get("semantic_graphics_removed") is True,"去字稿须检查残字并移除待重建的语义图形",422)
            if kind=="VISUAL_VECTOR":
                from factdeck.native_vectors import trace_svg
                p=next(p for p in w["generation"]["pages"] if p["id"]==t["binding"])
                _,stats=trace_svg(data,p["layout"]["components"]); suffix=".svg"
            else:
                from PIL import Image
                require(0<len(data)<=40*1024*1024,"图片文件为空或超过40MB",422)
                image=Image.open(io.BytesIO(data)); require(image.format=="PNG" and image.width>=600 and image.height>=300 and image.width*image.height<=30000000 and abs(image.width/image.height/(1280/720)-1)<.02,"须提交实际16:9 PNG，不能裁剪、拉伸或换用截图",422)
                image.verify(); stats={"width":image.width,"height":image.height}; suffix=".png"
            path=self.immutable(workflow_id,"visual-assets",data,suffix)
            receipt=copy.deepcopy(receipt); receipt.update(worker=t["worker"],accepted_at=now(),task_id=t["id"])
            record={"path":path,"sha256":sha(data),"bytes":len(data),"receipt":receipt,"receipt_path":self.snapshot(w,"visual_tool_receipt",receipt),"stats":stats}
            p=next(p for p in w["generation"]["pages"] if p["id"]==t["binding"]); p["assets"][ASSET_KIND[kind]]=record
            t.update(status="COMPLETE",completed_at=now(),lease_token=None,result_sha256=sha(data),result_path=path)
            self._advance_generation(w)
        return self.get(workflow_id)

    def revise_generation(self,workflow_id,page_id,kind):
        require(kind in VISUAL_KINDS,"视觉任务类型无效",422)
        with self.transaction(workflow_id,"GENERATION_PAGE_REVISE") as w:
            require(current(w),"生成已过期，请重新启动")
            g=w["generation"]; p=next((p for p in g["pages"] if p["id"]==page_id),None); require(p,"页面不存在",404)
            require(g["render"]["status"]!="RUNNING","正在导出，请等待完成后再修订")
            targets=g["pages"] if p is g["pages"][0] and kind=="VISUAL_DESIGN" else [p]
            for target in targets:
                target.setdefault("history",[]).append({"assets":copy.deepcopy(target["assets"]),"layout":copy.deepcopy(target.get("layout"))})
                target["revision"]+=1; target.pop("preview",None); target.pop("blind_read",None)
                stage=kind if target is p else "VISUAL_DESIGN"
                for asset in {"VISUAL_DESIGN":["design","clean","vector"],"VISUAL_LAYOUT":["clean","vector"],"VISUAL_CLEAN":["clean","vector"],"VISUAL_VECTOR":["vector"],"VISUAL_BLIND_READ":[]}[stage]: target["assets"].pop(asset,None)
                if stage in {"VISUAL_DESIGN","VISUAL_LAYOUT"}: target["layout"]=None
            g["render"]={"status":"WAITING_ASSETS","attempts":0,"error":None}; self.cancel_stale(w); self._advance_generation(w)
        return self.get(workflow_id)

    def run_page_preview(self,workflow_id,page_id):
        """Compile one finished page as soon as its assets exist: browser, native PPTX and PowerPoint,
        plus contrast/occlusion signals. A worker/reviewer preview only: it is not a render, binds no
        review, and the full-deck export keeps every gate."""
        from factdeck.visual_render import render
        from factdeck.visual_qa import contrast_issues, occlusion_issues
        w=self.get(workflow_id); g=w.get("generation")
        p=next((p for p in (g or {}).get("pages",[]) if p["id"]==page_id),None)
        if not g or not current(w) or not p or not p.get("layout") or not {"design","clean","vector"}<=set(p["assets"]): return None
        key=digest({"renderer":NATIVE_RENDER_VERSION,"assets":{k:a["sha256"] for k,a in p["assets"].items()},"layout":p["layout"]})
        if (p.get("preview") or {}).get("fingerprint")==key: return p["preview"]
        rel=f'{workflow_id}/page-previews/{page_id}-{key[:16]}'; folder=self.path(rel); start=time.perf_counter()
        frozen={k:v for k,v in g.items() if k!="pages"}; frozen["pages"]=[copy.deepcopy(p)]
        used={f["id"] for f in p["layout"]["model"].get("figures",[])}; logos={r["id"] for r in p["layout"]["model"].get("rasters",[])}
        frozen["figures"]=[f for f in g.get("figures",[]) if f["fact_id"] in used]; frozen["logos"]=[f for f in g.get("logos",[]) if f["id"] in logos]
        preview={"fingerprint":key,"path":rel,"status":"COMPLETE","error":None,"at":now(),
                 "issues":contrast_issues(p["layout"]["model"],self.path(p["assets"]["clean"]["path"]))+occlusion_issues(p["layout"]["model"],self.path(p["assets"]["clean"]["path"]))}
        try:
            report=render(frozen,folder,self.path,w["title"])
            preview.update(slide=f"{rel}/slide01.png",summary=report["summary"],office={k:report["office"].get(k) for k in ("engine","editability")})
        except Exception as e:
            preview.update(status="FAILED",error=str(e)[:2000])
        preview["seconds"]=round(time.perf_counter()-start,3)
        with self.transaction(workflow_id,"GENERATION_PAGE_PREVIEW") as w:
            g=w.get("generation") or {}; p=next((p for p in g.get("pages",[]) if p["id"]==page_id),None)
            if p and p.get("layout") and digest({"renderer":NATIVE_RENDER_VERSION,"assets":{k:a["sha256"] for k,a in p["assets"].items()},"layout":p["layout"]})==key:
                p["preview"]=preview
        return preview

    def run_generation(self,workflow_id):
        """Reserve a persistent code job, do slow work outside the SQLite transaction."""
        from factdeck.visual_render import render
        from app.deckflow import render_input
        token=secrets.token_urlsafe(24)
        with self.transaction(workflow_id,"GENERATION_RENDER_CLAIM") as w:
            job=(w.get("generation") or {}).get("render",{})
            if not current(w):
                if job: job.update(status="STALE",lease_token=None)
                return self.get(workflow_id)
            if not ready(w):
                if job.get("status") in {"PENDING","WAITING_APPROVAL"}: job.update(status="WAITING_APPROVAL",lease_token=None)
                return self.get(workflow_id)
            if job.get("status")=="WAITING_APPROVAL": job.update(status="PENDING")
            if job.get("status")=="RUNNING" and job.get("lease_until",0)<time.time(): job.update(status="PENDING",lease_token=None)
            if not ready(w) or w["generation"]["render"]["status"]!="PENDING": return self.get(workflow_id)
            g=w["generation"]; g["render"].update(status="RUNNING",lease_token=token,lease_until=time.time()+3600,attempts=g["render"]["attempts"]+1,error=None)
            frozen=copy.deepcopy(g); key=render_input(w); rel=f'{workflow_id}/renders/a-{key[:24]}-{uid("run")}'; title=w["title"]
        try:
            self.source_integrity(self.get(workflow_id))
            for p in frozen["pages"]:
                for a in p["assets"].values(): require(sha(self.path(a["path"]).read_bytes())==a["sha256"],"视觉资产已被修改")
            for f in frozen.get("figures",[]): require(sha(self.path(f["path"]).read_bytes())==f["sha256"],"原件图已被修改")
            for f in frozen.get("logos",[]): require(sha(self.path(f["path"]).read_bytes())==f["sha256"],"品牌标志已被修改")
            report=render(frozen,self.path(rel),self.path,title)
            with self.transaction(workflow_id,"GENERATION_RENDER_COMPLETE") as w:
                require(ready(w) and render_input(w)==key and w["generation"]["render"].get("lease_token")==token,"导出期间输入已变更，结果不能发布")
                self.source_integrity(w)
                folder=self.path(rel)
                w["render"]={"input_sha256":key,"draft":False,"path":rel,"at":now(),"hard_errors":report["hard_errors"],"summary":report["summary"],"route":ROUTE,
                             "pages":[{"id":p["id"],"file":f"slide{i:02d}.png","sha256":sha((folder/f"slide{i:02d}.png").read_bytes()),"design":p["lock"]["design"],"signals":[],"review":[]} for i,p in enumerate(frozen["pages"],1)],
                             "files":{n:sha((folder/n).read_bytes()) for n in ("deck.pptx","deck.pdf","deck.html","render_report.json")},"figure_files":[f["file"] for f in frozen.get("figures",[])],"logo_file":next((f["file"] for f in frozen.get("logos",[])),None),"font":frozen["font"],
                             "warnings":{"figure_low_dpi":[],"render":report["warnings"],"deck":[]},"visual_provenance":view(w),"office":report["office"]}
                w['render']['scope']=frozen.get('scope');w['render']['complete_deck']=not bool(frozen.get('scope'))
                w["generation"]["render"]={"status":"COMPLETE","attempts":frozen["render"]["attempts"],"error":None,"seconds":report["seconds"],"output_bytes":{n:(folder/n).stat().st_size for n in ("deck.pptx","deck.pdf")}}
                w["render"]["visual_provenance"]=view(w)
        except Exception as e:
            with self.transaction(workflow_id,"GENERATION_RENDER_FAILED") as w:
                if w.get("generation",{}).get("render",{}).get("lease_token")==token:
                    w["generation"]["render"].update(status="FAILED",lease_token=None,error=str(e)[:2000])
        return self.get(workflow_id)
