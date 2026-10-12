"""A route: archived artwork + locked native objects, browser and Office QA."""
from __future__ import annotations

import html
import copy
import json
import re
import threading
import time
from pathlib import Path

from factdeck.native_vectors import trace_svg, add_native_vectors
from factdeck.visual_layout import text_of

OFFICE_LOCK = threading.Lock()

# Detect an isolated final character in a compact bold heading. Measurements
# use real browser glyphs; any size change is recorded with the final model.
ORPHAN_HEADER_JS = """el => [...el.querySelectorAll('[data-qa-text]')].map(n=>{
 const spans=[...n.querySelectorAll('span')];
 if(!spans.length)return null;
 const sizes=spans.map(s=>parseFloat(s.style.fontSize));const size=sizes[0];
 if(size<20||size>40||sizes.some(s=>s!==size)||spans.some(s=>s.style.fontWeight!=='700')||n.firstElementChild.children.length!==1)return null;
 const lines=()=>{const counts=new Map();const walker=document.createTreeWalker(n,NodeFilter.SHOW_TEXT);let t;
  while(t=walker.nextNode())for(let i=0;i<t.length;i++){if(!t.textContent[i].trim())continue;const r=document.createRange();r.setStart(t,i);r.setEnd(t,i+1);const y=Math.round(r.getBoundingClientRect().top);counts.set(y,(counts.get(y)||0)+1);}
  return [...counts.values()];};
 const before=lines();if(before.length!==2||before[1]!==1||before[0]<10)return null;
 const oldWidth=n.clientWidth;let chosen=null;for(let candidate=size;candidate>=Math.max(19.5,size*.885)-.001;candidate-=.5){spans.forEach(s=>s.style.fontSize=candidate+'px');
  for(let extra=1;extra<=16;extra++){n.style.width=(oldWidth+extra)+'px';if(lines().length===1){chosen={new_size:candidate,width_extra:extra};break;}}
  n.style.width=oldWidth+'px';if(chosen!==null)break;
 }
 spans.forEach((s,i)=>s.style.fontSize=sizes[i]+'px');n.style.width=oldWidth+'px';
 return chosen===null?null:{old_size:size,...chosen};
})"""


def fit_orphan_headers(model, measurements, components):
    changes=[]
    for index,fit in enumerate(measurements):
        if not fit:continue
        text=model['texts'][index]
        runs=[r for p in text['paras'] for r in p]
        old=fit['old_size'];new=fit['new_size']
        if not runs or any(not r.get('bold') or abs(r['size']-old)>.01 for r in runs):continue
        if not max(19.5,old*.885)<=new<old<=40:continue
        extra=fit['width_extra']
        if not clear_font_width_headroom(model,text,extra,components):continue
        before=text['w'];text['w']+=extra
        for run in runs:run['size']=new
        changes.append({'text_index':index,'old_size':old,'new_size':new,'old_width':before,'new_width':text['w'],'reason':'Actual browser measured one orphan final character in compact bold heading; fitted in 16px clear card space and within 11.5% font-size adjustment, wording unchanged'})
    return changes

# Tables can grow beyond their CSS height without any td scroll overflow.
# Measure their real boxes as well as the content boxes before native export.
LAYOUT_CHECK_JS = """el => {
 const nodes=[...el.querySelectorAll('[data-qa-text],td')];
 const overflow=nodes.filter(n=>n.scrollHeight>n.clientHeight+1||n.scrollWidth>n.clientWidth+1).map(n=>n.textContent.slice(0,50));
 const tables=[...el.querySelectorAll('[data-qa-table]')];
 const table_dimensions=tables.map((n,i)=>{const r=n.getBoundingClientRect();return {index:i,width:r.width,height:r.height,locked_width:Number(n.dataset.lockWidth),locked_height:Number(n.dataset.lockHeight)};});
 for(const t of table_dimensions)if(t.width>t.locked_width+1.5||t.height>t.locked_height+1.5)overflow.push('table '+t.index+' exceeds locked dimensions');
 for(const [i,n] of [...el.querySelectorAll('[data-lock-row-height]')].entries())if(n.getBoundingClientRect().height>Number(n.dataset.lockRowHeight)+1.5)overflow.push('table row '+i+' exceeds locked height');
 const boxes=[...el.querySelectorAll('[data-qa-text],[data-qa-table]')]; const overlap=[];
 for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++){const a=boxes[i].getBoundingClientRect(),b=boxes[j].getBoundingClientRect();if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>2&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>2)overlap.push([i,j]);}
 return {overflow,overlap,table_dimensions};
}"""


def fit_text_lineboxes(model, measurements):
    """Only add small font-metric headroom where neighbouring text stays clear."""
    changes=[]
    for index,m in enumerate(measurements):
        if m['scroll_w']>m['client_w']+1: continue
        extra=m['scroll_h']-m['client_h']
        if not 1<extra<=16: continue
        t=model['texts'][index]; height=t['h']+extra
        if t['y']+height>720: continue
        neighbours=[other for j,other in enumerate(model['texts']) if j!=index]+model.get('tables',[])
        collision=any(min(t['x']+t['w'],other['x']+other['w'])-max(t['x'],other['x'])>2 and min(t['y']+height,other['y']+other['h'])-max(t['y'],other['y'])>2 for other in neighbours)
        if collision: continue
        changes.append({'text_index':index,'old_height':t['h'],'new_height':height,'reason':'Measured font line-box headroom; wording, font size and position unchanged'})
        t['h']=height
    return changes


def svg_markup(vectors):
    paths=[]
    for v in vectors:
        d=" ".join(c[0]+" "+",".join(str(x) for x in c[1:]) for c in v["commands"])
        paths.append(f'<path d="{d}" fill="{v["fill"] or "none"}" stroke="{v["stroke"] or "none"}" stroke-width="{v["width"]}" opacity="{v["opacity"]}"/>')
    return '<svg style="position:absolute;inset:0" width="1280" height="720" viewBox="0 0 1280 720">'+"".join(paths)+'</svg>'


def document(models, vectors, font, figure_files=None):
    def color(c): return "#"+c["hex"] if c else "transparent"
    def box(v): return f'left:{v["x"]}px;top:{v["y"]}px;width:{v["w"]}px;height:{v["h"]}px;'
    def paras(v):
        return "".join('<div>'+"".join(f'<span style="font-family:{html.escape(r.get("font",font),quote=True)};font-size:{r["size"]}px;font-weight:{700 if r.get("bold") else 400};color:{color(r.get("color"))}">{html.escape(r["text"])}</span>' for r in p)+'</div>' for p in v.get("paras",[]))
    sections=[]
    for i,(m,vec) in enumerate(zip(models,vectors)):
        items=[svg_markup(vec)]
        for s in m["shapes"]:
            border=f'border:{s["line"]["w"]}px solid {color(s["line"]["color"])};' if s.get("line") else ""
            items.append(f'<div style="position:absolute;{box(s)}background:{color(s.get("fill"))};border-radius:{s["radius"]}px;{border}"></div>')
            for a in s.get("accents",[]): items.append(f'<div style="position:absolute;{box(a)}background:{color(a["color"])}"></div>')
        for ln in m["lines"]:
            points=" ".join(f"{x},{y}" for x,y in ln["points"])
            arrow_end=f' marker-end="url(#arrow{i}_{len(items)})"' if ln.get('arrow',True) else ''
            items.append(f'<svg style="position:absolute;inset:0" width="1280" height="720"><defs><marker id="arrow{i}_{len(items)}" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0 L7 3.5 L0 7" fill="#{ln["color"]}"/></marker></defs><polyline points="{points}" fill="none" stroke="#{ln["color"]}" stroke-width="{ln["w"]}"{arrow_end}/></svg>')
        for g in m.get("figures",[])+m.get("rasters",[]): items.append(f'<img style="position:absolute;{box(g)}" src="{html.escape((figure_files or {})[g["id"]])}">')
        for t in m["tables"]:
            rows=[]
            for row in t["rows"]:
                cells=[]
                for c in row["cells"]:
                    pad=" ".join(str(n)+"px" for n in c["pad"])
                    runs=[r for p in c['paras'] for r in p]
                    size=max((r['size'] for r in runs),default=16)
                    cell_font=html.escape(next((r.get('font',font) for r in runs),font),quote=True)
                    cells.append(f'<td style="padding:{pad};width:{c["w"]}px;height:{row["h"]}px;background:{color(c.get("fill"))};font-family:{cell_font};font-size:{size}px;line-height:{c["lineHeight"]}px;white-space:pre-line;text-align:{c.get("align","left")};vertical-align:{"middle" if c.get("anchor")=="middle" else "bottom" if c.get("anchor")=="bottom" else "top"};border-bottom:1px solid {color(c.get("border"))}">{paras(c)}</td>')
                rows.append(f'<tr data-lock-row-height="{row["h"]}">'+"".join(cells)+'</tr>')
            items.append(f'<table data-qa-table data-lock-width="{t["w"]}" data-lock-height="{t["h"]}" style="position:absolute;table-layout:fixed;border-collapse:collapse;{box(t)}">'+"".join(rows)+'</table>')
        for t in m["texts"]:
            align=t.get("align","left"); anchor="display:flex;align-items:center;" if t.get("anchor")=="middle" else ""
            size=max((r["size"] for p in t["paras"] for r in p),default=16)
            items.append(f'<div data-qa-text style="position:absolute;{box(t)}font-size:{size}px;line-height:{t["lineHeight"]}px;text-align:{align};white-space:{"nowrap" if t["nowrap"] else "pre-line"};{anchor}"><div style="width:100%">{paras(t)}</div></div>')
        sections.append(f'<section id="slide{i+1}" style="background:{color(m["background"])}">'+"".join(items)+'</section>')
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>*{box-sizing:border-box}body{margin:0;font-family:'+html.escape(font)+'}section{position:relative;width:1280px;height:720px;overflow:hidden;break-after:page}td div{margin:0}svg{pointer-events:none}@page{size:1280px 720px;margin:0}</style><body>'+"".join(sections)+'</body></html>'


def safe_nowrap_ink_overhang(model, text, extra_pixels):
    """Allow small serif ink overhang of an unbroken numeric token in clear space."""
    single_number=bool(re.fullmatch(r'[\d.,:%/()+\-−–≈~<>≤≥×]+',text_of(text).strip()))
    if not (text.get('nowrap') or single_number) or not 0<extra_pixels<=16:return False
    right=text['x']+text['w']+extra_pixels
    if right>1280:return False
    neighbours=[t for t in model['texts'] if t is not text]+model.get('tables',[])
    return not any(min(right,t['x']+t['w'])-max(text['x'],t['x'])>2 and min(text['y']+text['h'],t['y']+t['h'])-max(text['y'],t['y'])>2 for t in neighbours)


def clear_font_width_headroom(model,text,extra,components=()):
    if not 0<extra<=16 or text['x']+text['w']+extra>1280:return False
    neighbours=[t for t in model['texts'] if t is not text]+model.get('tables',[])
    if any(min(text['x']+text['w']+extra,t['x']+t['w'])-max(text['x'],t['x'])>2 and min(text['y']+text['h'],t['y']+t['h'])-max(text['y'],t['y'])>2 for t in neighbours):return False
    containers=[c for c in components if c['x']<=text['x'] and text['x']+text['w']<=c['x']+c['w'] and c['y']<=text['y'] and text['y']+text['h']<=c['y']+c['h']+16]
    if containers:
        container=min(containers,key=lambda c:c['w']*c['h'])
        if text['x']+text['w']+extra>container['x']+container['w']-2:return False
    return True


def office_render(folder: Path, count: int, models=None, components=None, template_export=False):
    import pythoncom
    import win32com.client
    from pypdf import PdfReader
    start=time.perf_counter(); checks=[]; text_checks=[]; adjustments=[]
    adjusted_file=folder/'office_adjusted.pptx'
    with OFFICE_LOCK:
        pythoncom.CoInitialize(); app=None; ppt=None
        try:
            app=win32com.client.DispatchEx("PowerPoint.Application")
            ppt=app.Presentations.Open(str((folder/"deck.pptx").resolve()),ReadOnly=True,Untitled=False,WithWindow=False)
            if ppt.Slides.Count!=count: raise ValueError("PowerPoint 页面数量不一致")
            def native_leaves(container):
                for j in range(1,container.Count+1):
                    shape=container(j)
                    if shape.Type==6: yield from native_leaves(shape.GroupItems)
                    else: yield shape
            for i in range(1,count+1):
                slide=ppt.Slides(i)
                measured=0;errors=[];ink_overhang=[]
                for native in native_leaves(slide.Shapes):
                    if native.Type in (14,17) and native.TextFrame2.HasText:
                        measured+=1;tr=native.TextFrame2.TextRange
                        locked=None
                        if models:
                            from factdeck.lexicon import canon
                            model=models[i-1]
                            locked=next((t for t in model['texts'] if canon(text_of(t))==canon(str(native.TextFrame.TextRange.Text).replace('\r','\n'))),None)
                        if (tr.BoundHeight>native.Height+1 or tr.BoundWidth>native.Width+1) and locked is not None:
                            old_width=native.Width
                            for extra in range(1,17):
                                if not clear_font_width_headroom(model,locked,extra,(components or [()]*count)[i-1]):continue
                                native.Width=old_width+extra*.75
                                if tr.BoundHeight<=native.Height+1 and tr.BoundWidth<=native.Width+1:
                                    before=locked['w'];locked['w']+=extra
                                    adjustments.append({'page':i,'text_index':model['texts'].index(locked),'old_width':before,'new_width':locked['w'],'reason':'Measured Office font wrap headroom in clear space; text, size and position unchanged'})
                                    break
                            else:native.Width=old_width
                        if tr.BoundWidth>native.Width+1 and tr.BoundHeight<=native.Height+1 and locked is not None:
                            extra=(tr.BoundWidth-native.Width)/.75
                            if safe_nowrap_ink_overhang(model,locked,extra):
                                ink_overhang.append({'name':native.Name,'extra_pixels':round(extra,3),'reason':'Small measured serif ink overhang in clear space; native bounds and wording unchanged'})
                                continue
                        if tr.BoundWidth>native.Width+1 or tr.BoundHeight>native.Height+1:
                            errors.append({'name':native.Name,'bound_width':round(tr.BoundWidth,2),'bound_height':round(tr.BoundHeight,2),'width':round(native.Width,2),'height':round(native.Height,2)})
                text_checks.append({'page':i,'text_boxes_measured':measured,'overflow':errors,'fontmetric_ink_overhang':ink_overhang})
                if errors:
                    (folder/'office_text_errors.json').write_text(json.dumps(text_checks,ensure_ascii=False,indent=2),encoding='utf8')
                    raise ValueError(f'PowerPoint 第{i}页存在实际文字溢出：'+json.dumps(errors,ensure_ascii=False))
            if adjustments:ppt.SaveCopyAs(str(adjusted_file.resolve()),24)
            if template_export:ppt.SaveCopyAs(str((folder/'template.potx').resolve()),26)
            ppt.SaveAs(str((folder/"deck.pdf").resolve()),32)
            for i in range(1,count+1):
                slide=ppt.Slides(i);slide.Export(str((folder/f"slide{i:02d}.png").resolve()),"PNG",2560,1440)
                groups=[slide.Shapes(j) for j in range(1,slide.Shapes.Count+1) if slide.Shapes(j).Type==6]
                candidates=[(g,g.GroupItems(j)) for g in groups for j in range(1,g.GroupItems.Count+1) if g.GroupItems(j).Type==5 and g.GroupItems(j).Nodes.Count>0]
                if not candidates and template_export:
                    tables=[slide.Shapes(j) for j in range(1,slide.Shapes.Count+1) if slide.Shapes(j).HasTable]
                    if not tables:raise ValueError(f'模板第{i}页没有矢量图形或原生表格')
                    cell=tables[0].Table.Cell(2,1).Shape.TextFrame.TextRange
                    old=str(cell.Text);cell.Text='原生表格编辑检查';editable=str(cell.Text)=='原生表格编辑检查';cell.Text=old
                    if not editable:raise ValueError('原生表格编辑检查失败')
                    checks.append({'page':i,'artwork_absent':True,'native_table_edit':True,'group_move':None,'fill_recolor':None,'contour_edit':None})
                    continue
                if not candidates: raise ValueError(f"第{i}页没有可验证的原生矢量路径")
                group,shape=max(candidates,key=lambda pair:pair[1].Nodes.Count)
                old=group.Left; group.Left=old+3; moved=abs(group.Left-old-3)<.2; group.Left=old
                oldcolor=shape.Fill.ForeColor.RGB; shape.Fill.ForeColor.RGB=0x228B22; recolored=shape.Fill.ForeColor.RGB==0x228B22; shape.Fill.ForeColor.RGB=oldcolor
                x,y=shape.Nodes.Item(1).Points[0]; shape.Nodes.SetPosition(1,x+1,y+1); xx,yy=shape.Nodes.Item(1).Points[0]
                contour=abs(xx-x-1)<.2 and abs(yy-y-1)<.2; shape.Nodes.SetPosition(1,x,y)
                if not(moved and recolored and contour): raise ValueError(f"第{i}页矢量编辑验证失败")
                checks.append({"page":i,"group_move":moved,"fill_recolor":recolored,"contour_edit":contour})
        finally:
            if ppt is not None: ppt.Close()
            if app is not None: app.Quit()
            pythoncom.CoUninitialize()
    if adjustments:adjusted_file.replace(folder/'deck.pptx')
    if len(PdfReader(folder/"deck.pdf").pages)!=count: raise ValueError("Office PDF 页数不一致")
    return {"engine":"Microsoft PowerPoint", "seconds":round(time.perf_counter()-start,3), "editability":checks,"text_bounds":text_checks,"fontmetric_adjustments":adjustments}


def render(generation, out: Path, asset_path, title=""):
    from playwright.sync_api import sync_playwright
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    from factdeck.render import build_pptx
    from factdeck.lexicon import canon
    out.mkdir(parents=True,exist_ok=True); start=time.perf_counter()
    models=[]; notes=[]; vectors=[]; stats=[]; pages=generation["pages"]
    for p in pages:
        models.append(copy.deepcopy(p["layout"]["model"])); notes.append(p["lock"]["notes"])
        vec,stat=trace_svg(asset_path(p["assets"]["vector"]["path"]).read_bytes(),p["layout"]["components"],preserve_order=p['layout'].get('preserve_vector_order',False))
        vectors.append(vec); stats.append(stat)
    figures={}; figure_files={}; logos={}
    for f in generation.get("figures",[]):
        target=out/f["file"]; target.write_bytes(asset_path(f["path"]).read_bytes()); figures[f["fact_id"]]=target; figure_files[f["fact_id"]]=f["file"]
    for f in generation.get("logos",[]):
        target=out/f["file"]; target.write_bytes(asset_path(f["path"]).read_bytes()); logos[f["id"]]=target; figure_files[f["id"]]=f["file"]
    html_path=out/"deck.html"; html_path.write_text(document(models,vectors,generation["font"],figure_files),encoding="utf8")
    reports=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(); page=browser.new_page(viewport={"width":1280,"height":720},device_scale_factor=2)
        page.goto(html_path.resolve().as_uri()); page.evaluate("document.fonts.ready")
        for i,p in enumerate(pages,1):
            heading_fits=fit_orphan_headers(models[i-1],page.locator(f'#slide{i}').evaluate(ORPHAN_HEADER_JS),p['layout']['components'])
            if heading_fits:
                html_path.write_text(document(models,vectors,generation['font'],figure_files),encoding='utf8')
                page.goto(html_path.resolve().as_uri());page.evaluate('document.fonts.ready')
            metrics=page.locator(f"#slide{i}").evaluate("el => [...el.querySelectorAll('[data-qa-text]')].map(n=>({scroll_w:n.scrollWidth,client_w:n.clientWidth,scroll_h:n.scrollHeight,client_h:n.clientHeight}))")
            fitted=fit_text_lineboxes(models[i-1],metrics)
            if fitted:
                html_path.write_text(document(models,vectors,generation["font"],figure_files),encoding="utf8")
                page.goto(html_path.resolve().as_uri()); page.evaluate("document.fonts.ready")
            checks=page.locator(f"#slide{i}").evaluate(LAYOUT_CHECK_JS)
            page.locator(f"#slide{i}").screenshot(path=str(out/f"browser-slide{i:02d}.png"))
            reports.append({"id":p["id"],**checks,"design":p["lock"]["design"],"signals":[],"review":[],"vector":stats[i-1],"fontmetric_adjustments":fitted,"typographic_adjustments":heading_fits})
        browser.close()
    if any(r["overflow"] or r["overlap"] for r in reports):
        (out/"layout_errors.json").write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding="utf8")
        raise ValueError("版面存在文字溢出或重叠："+"、".join(r["id"] for r in reports if r["overflow"] or r["overlap"])+"；请修订对应页的 VISUAL_LAYOUT 后续跑")
    build_pptx(models,logos,notes,out/"deck.pptx",title,figures,font=generation["font"],strict_text_geometry=True)
    (out/"native_model.json").write_text(json.dumps({"models":models,"notes":notes,"font":generation["font"],"fontmetric_adjustments":[{"id":r['id'],"changes":r['fontmetric_adjustments']} for r in reports],"typographic_adjustments":[{"id":r['id'],'changes':r['typographic_adjustments']} for r in reports]},ensure_ascii=False,indent=2),encoding="utf8")
    add_native_vectors(out/"deck.pptx",vectors)
    office=office_render(out,len(pages),models,[p['layout']['components'] for p in pages])
    if office['fontmetric_adjustments']:
        html_path.write_text(document(models,vectors,generation['font'],figure_files),encoding='utf8')
        with sync_playwright() as pw:
            browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1280,'height':720},device_scale_factor=2)
            page.goto(html_path.resolve().as_uri());page.evaluate('document.fonts.ready')
            for i in sorted({a['page'] for a in office['fontmetric_adjustments']}):
                checks=page.locator(f'#slide{i}').evaluate(LAYOUT_CHECK_JS)
                if checks['overflow'] or checks['overlap']:raise ValueError('Office字体容量调整后浏览器预检失败')
                page.locator(f'#slide{i}').screenshot(path=str(out/f'browser-slide{i:02d}.png'))
                reports[i-1].update(checks)
            browser.close()
        (out/'native_model.json').write_text(json.dumps({'models':models,'notes':notes,'font':generation['font'],'fontmetric_adjustments':[{'id':r['id'],'changes':r['fontmetric_adjustments']} for r in reports],'typographic_adjustments':[{'id':r['id'],'changes':r['typographic_adjustments']} for r in reports],'office_fontmetric_adjustments':office['fontmetric_adjustments']},ensure_ascii=False,indent=2),encoding='utf8')
    prs=Presentation(out/"deck.pptx")
    def leaves(shapes):
        for s in shapes:
            if s.shape_type==MSO_SHAPE_TYPE.GROUP: yield from leaves(s.shapes)
            else: yield s
    for slide,m,n in zip(prs.slides,models,notes):
        sh=list(leaves(slide.shapes)); actual=sorted(canon(s.text) for s in sh if s.has_text_frame and s.text.strip())
        wanted=sorted(canon(text_of(t)) for t in m["texts"] if text_of(t).strip())
        if actual!=wanted: raise ValueError("原生文字回读与内容锁不一致")
        tables=[s.table for s in sh if s.has_table]
        if len(tables)!=len(m["tables"]): raise ValueError("原生表格数量不一致")
        for table,lock in zip(tables,m["tables"]):
            if [[canon(c.text) for c in row.cells] for row in table.rows]!=[[canon(text_of(c)) for c in row["cells"]] for row in lock["rows"]]: raise ValueError("原生表格单元格不一致")
        pics=[s for s in sh if s.shape_type==MSO_SHAPE_TYPE.PICTURE]
        if len(pics)!=len(m.get("figures",[]))+len(m.get("rasters",[])): raise ValueError("生成图形不得以图片导出")
        import hashlib
        wanted_pics=[hashlib.sha256(figures[g["id"]].read_bytes()).hexdigest() for g in m.get("figures",[])]+[hashlib.sha256(logos[g["id"]].read_bytes()).hexdigest() for g in m.get("rasters",[])]
        if sorted(hashlib.sha256(s.image.blob).hexdigest() for s in pics)!=sorted(wanted_pics): raise ValueError("原件图或品牌标志的实际字节不一致")
        if slide.notes_slide.notes_text_frame.text!=n: raise ValueError("来源备注不一致")
    from app.deck_generation import NATIVE_RENDER_VERSION
    report={"route":"A_NATIVE_VECTOR","renderer_version":NATIVE_RENDER_VERSION,"hard_errors":0,"slides":reports,"font":generation["font"],"office":office,
            "summary":{"slides":len(pages),"generated_picture_objects":0,"native_paths":sum(s["native_paths"] for s in stats),"overflow":0,"overlap":0,"content_mismatch":0},
            "seconds":round(time.perf_counter()-start,3),"warnings":["浏览器预览与 PowerPoint 实际渲染均已存档，视觉差异及残字仍需逐页人工核对。"]}
    (out/"render_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
    return report
