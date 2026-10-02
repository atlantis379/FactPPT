"""Persistent A-route orchestration for the Codex + Adobe execution endpoint.

Tool calls stay outside the application. Each accepted result queues its successor;
only native compilation/rendering runs inside the application, after all assets exist.
"""
from __future__ import annotations

import copy
import io
import json
import math
import secrets
import time
from pathlib import Path

from app.fact57098 import digest, sha, now, uid, require, WorkflowError
from factdeck.visual_layout import PALETTE, contract, accept_layout, text_of
from app.deck_scope import selected_spec, scope_of

VISUAL_KINDS=("VISUAL_DESIGN","VISUAL_LAYOUT","VISUAL_CLEAN","VISUAL_VECTOR")
ROUTE="A_NATIVE_VECTOR"
VERSION="factdeck.visual-a.1"
NATIVE_RENDER_VERSION="factdeck.visual-native-export.5"
ASSET_KIND={"VISUAL_DESIGN":"design","VISUAL_CLEAN":"clean","VISUAL_VECTOR":"vector"}


def base_input(w):
    from app.deckflow import render_input
    return render_input(w, include_visual=False)


def current(w):
    g=w.get("generation")
    return bool(g) and g["input_sha256"]==base_input(w)


def ready(w):
    from app.deckflow import semantic_current, open_issues
    return current(w) and semantic_current(w) and not open_issues(w) and all(p.get("layout") and set(p["assets"])=={"design","clean","vector"} for p in w["generation"]["pages"])


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
    return result


class GenerationMixin:
    def generation_fingerprint(self,w,kind,page_id):
        require(current(w),"生成输入已过期，请重新启动生成")
        g=w["generation"]; p=next(p for p in g["pages"] if p["id"]==page_id)
        needed={"VISUAL_DESIGN":[],"VISUAL_LAYOUT":["design"],"VISUAL_CLEAN":["design"],"VISUAL_VECTOR":["clean"]}[kind]
        refs={k:p["assets"][k]["sha256"] for k in needed}
        if kind=="VISUAL_DESIGN" and p is not g["pages"][0]: refs["style_reference"]=g["pages"][0]["assets"]["design"]["sha256"]
        return digest({"version":VERSION,"generation":g["id"],"input":g["input_sha256"],"page":p["id"],"revision":p.get("revision",0),"kind":kind,"lock":p["lock"],"references":refs,
                       "layout":p.get("layout") if kind in {"VISUAL_CLEAN","VISUAL_VECTOR"} else None})

    def generation_brief(self,w,kind,page_id):
        g=w["generation"]; p=next(p for p in g["pages"] if p["id"]==page_id)
        required={"VISUAL_DESIGN":[],"VISUAL_LAYOUT":["design"],"VISUAL_CLEAN":["design"],"VISUAL_VECTOR":["clean"]}[kind]
        refs={k:{"sha256":p["assets"][k]["sha256"],"url":f'/api/deck/workflows/{w["id"]}/generation/assets/{page_id}/{k}'} for k in required}
        if kind=="VISUAL_DESIGN" and p is not g["pages"][0] and "design" in g["pages"][0]["assets"]:
            first=g["pages"][0]; refs["style_reference"]={"sha256":first["assets"]["design"]["sha256"],"url":f'/api/deck/workflows/{w["id"]}/generation/assets/{first["id"]}/design'}
        text_lock=[text_of(t) for t in p["lock"]["model"]["texts"]]
        tables=[[[text_of(c) for c in row["cells"]] for row in t["rows"]] for t in p["lock"]["model"]["tables"]]
        common={"schema_version":VERSION,"route":ROUTE,"page_id":page_id,"input_sha256":self.generation_fingerprint(w,kind,page_id),
                "locked_objects":contract(p["lock"]["model"]),"design":p["lock"]["design"],"palette":g["palette"],"assets":refs,
                "rules":["事实与来源来自内容锁；设计图不得增加实质结论、数值或关系。",
                         "必须使用真实工具、实际输出与完整提示词；失败请回报，禁止伪造调用或检查。",
                         "使用工具前下载 refs 中的实际图片，按实际工具要求传本地路径。任务租约15分钟，长调用须续约。"]}
        if kind=="VISUAL_LAYOUT":
            common["result_contract"]={"input_sha256":common["input_sha256"],"design_inspected":False,"objects":[{k:s[k] for k in ("id","x","y","w","h")} for s in common["locked_objects"]["slots"]],
                                       "components":[{"name":"视觉组件","x":0,"y":0,"w":1280,"h":720}],"differences":[]}
            return common
        if kind=="VISUAL_DESIGN":
            style="遵循已选客户模板的配色令牌和字体；保留品牌视觉约定。" if w["theme"]=="brand" else "米白底、炭黑正文、低饱和墨蓝重点。不要高亮电蓝。"
            prompt="生成一页带全部文字的完整演示文稿设计稿，16:9。"+style+"清楚网格、阅读顺序和克制装饰。参考首张设计稿统一整套视觉。所有锁定文字、表格、限定条件与来源完整呈现；不要编造图形表达的新数值或关系。此图片用于后续拆解重建原生PPT，文字区留出可读容量。\n"
            prompt+=json.dumps({"design":p["lock"]["design"],"palette":g["palette"],"text":text_lock,"tables":tables,"native_objects":common["locked_objects"]},ensure_ascii=False)
        elif kind=="VISUAL_CLEAN":
            native_tables=p['layout']['model']['tables']
            prompt="编辑实际设计稿：彻底去除所有文字、字母、数字、单位、标志、水印、文字阴影和残留字符。移除所有数据柱、流程连接线和箭头，之后由原生对象按照锁定内容填回。"
            if native_tables:
                prompt+="彻底删除整块表格，包括表头色块、外框、交替行底色、行线、列线和全部单元格边界；整个表格矩形区域必须补成与周围相同的米白背景，不得留下任何空表格结构。仅保留非表格的装饰色块、插画与构图，包括肺部插画与页底波纹。"
            else:
                prompt+="本页没有待重建的原生表格。卡片容器不是表格，禁止删除卡片。完整保留所有卡片的底色、外框和标题色带，圆形图标底座与非文字图标轮廓，标题装饰短线、肺部插画和页底波纹。只清除其中的文字与数字，不改变这些非文字装饰与容器的布局。"
            prompt+="移除原件证据图与品牌标志的重绘，保留这些对象的占位留白，最终使用实际原件填回。补齐去字区域的背景。不要新增含义或符号。请逐页看实际输出确认无残字。\n"+json.dumps({"native_regions":p["layout"]["components"],"native_table_regions":[{k:t[k] for k in ('x','y','w','h')} for t in native_tables],"locked_boxes":contract(p["layout"]["model"])["slots"]},ensure_ascii=False)
        else: prompt="使用 Adobe image_vectorize 对实际去字 PNG 进行矢量化，提交实际 SVG，不得以图片、手写替代SVG或整页截图伪装工具输出。"
        common["prompt"]=prompt
        common["receipt_contract"]={"contract_sha256":common["input_sha256"],"asset_sha256":"实际文件SHA256","tool":"image_gen" if kind!="VISUAL_VECTOR" else "adobe_image_vectorize",
                                    "tool_call_id":"实际调用标识","prompt":prompt,"input_assets":{k:v["sha256"] for k,v in refs.items()},"elapsed_seconds":0,
                                    "qa":{"inspected":False,**({"text_free":False,"semantic_graphics_removed":False} if kind=="VISUAL_CLEAN" else {})}}
        return common

    def _advance_generation(self,w):
        if not current(w): return
        g=w["generation"]
        for i,p in enumerate(g["pages"]):
            if "design" not in p["assets"]:
                if i and "design" not in g["pages"][0]["assets"]: continue
                kind="VISUAL_DESIGN"
            elif not p.get("layout"): kind="VISUAL_LAYOUT"
            elif "clean" not in p["assets"]: kind="VISUAL_CLEAN"
            elif "vector" not in p["assets"]: kind="VISUAL_VECTOR"
            else: continue
            fp=self.generation_fingerprint(w,kind,p["id"])
            if any(t["kind"]==kind and t["binding"]==p["id"] and t["input_sha256"]==fp and t["status"] in {"PENDING","RUNNING","FAILED"} for t in w["tasks"]): continue
            w["tasks"].append({"id":uid("task"),"kind":kind,"binding":p["id"],"generation_id":g["id"],"input_sha256":fp,"status":"PENDING","attempts":0,
                               "created_at":now(),"worker":None,"lease_token":None,"lease_until":0,"error":None,"brief":self.generation_brief(w,kind,p["id"])})
        if ready(w) and g["render"]["status"]=="WAITING_ASSETS": g["render"]["status"]="PENDING"

    def start_generation(self,workflow_id,first_pages=None):
        from app.deckflow import deck_current, verified, checked, status, figures, render_input
        from factdeck.render import render as prepare
        w=self.get(workflow_id)
        scope=scope_of((w.get('deck') or {}).get('result',{}))
        require(first_pages is None if not scope else first_pages==scope['page_count'], '本次须明确指定已核对的前N页范围',422)
        require(deck_current(w),"请先完成当前版本的页面规格")
        require(status(w)[0] not in {"CONFIRMATIONS_REQUIRED","SEMANTIC_REVIEW_REQUIRED","SEMANTIC_ISSUES","DECK_REVISION"},"正式渲染前需完成事实确认和独立语义审查")
        self.source_integrity(w)
        if current(w):
            with self.transaction(workflow_id,"GENERATION_RESUME") as w:
                g=w["generation"]
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
        report=prepare(spec,v["facts"],src,folder,self.render_theme(w),v["terms"],figures=figs)
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
        generation['scope']=chk.get('scope')
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

    def complete_layout(self,workflow_id,task_id,token,result):
        with self.transaction(workflow_id,"VISUAL_LAYOUT_COMPLETE") as w:
            t=self.leased(w,task_id,token); require(t["kind"]=="VISUAL_LAYOUT","任务类型不符")
            require(result.get("input_sha256")==t["input_sha256"],"版面结果输入校验值不符")
            p=next(p for p in w["generation"]["pages"] if p["id"]==t["binding"])
            model=accept_layout(p["lock"]["model"],result,p["lock"]["chart"])
            p["layout"]={"model":model,"components":result["components"],"differences":result["differences"],"author":t["worker"],"at":now()}
            t.update(status="COMPLETE",completed_at=now(),lease_token=None,result_sha256=digest(result),result_path=self.snapshot(w,"visual_layout_result",result))
            self._advance_generation(w)
        return self.get(workflow_id)

    def visual_asset(self,workflow_id,task_id,token,data,receipt):
        require(isinstance(receipt,dict),"调用回执必须为对象",422)
        with self.transaction(workflow_id,"VISUAL_ASSET_COMPLETE") as w:
            t=self.leased(w,task_id,token); require(t["kind"] in ASSET_KIND,"该任务不接收图片或 SVG",422)
            brief=t["brief"]; kind=t["kind"]
            require(receipt.get("contract_sha256")==t["input_sha256"] and receipt.get("asset_sha256")==sha(data),"调用回执与合同或实际文件不符",422)
            require(receipt.get("prompt")==brief["prompt"] and receipt.get("input_assets")==brief["receipt_contract"]["input_assets"],"完整提示词或参考资产不符",422)
            require(isinstance(receipt.get("tool_call_id"),str) and bool(receipt["tool_call_id"].strip()),"缺少实际调用标识",422)
            seconds=receipt.get("elapsed_seconds")
            unknown=seconds is None and receipt.get("timing_status")=="UNKNOWN_AFTER_INTERRUPTION" and bool(receipt.get("timing_note"))
            require(unknown or (not isinstance(seconds,bool) and isinstance(seconds,(int,float)) and math.isfinite(seconds) and seconds>=0),"调用耗时无效",422)
            tool=receipt.get("tool")
            require(tool in ({"adobe_image_vectorize","mcp__codex_apps__adobe_image_vectorize"} if kind=="VISUAL_VECTOR" else {"image_gen","image_gen.imagegen","image_gen__imagegen"}),"须使用约定的真实工具",422)
            qa=receipt.get("qa") or {}; require(qa.get("inspected") is True,"须查看实际输出后提交检查记录",422)
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
                target["revision"]+=1
                stage=kind if target is p else "VISUAL_DESIGN"
                for asset in {"VISUAL_DESIGN":["design","clean","vector"],"VISUAL_LAYOUT":["clean","vector"],"VISUAL_CLEAN":["clean","vector"],"VISUAL_VECTOR":["vector"]}[stage]: target["assets"].pop(asset,None)
                if stage in {"VISUAL_DESIGN","VISUAL_LAYOUT"}: target["layout"]=None
            g["render"]={"status":"WAITING_ASSETS","attempts":0,"error":None}; self.cancel_stale(w); self._advance_generation(w)
        return self.get(workflow_id)

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
