"""Geometry-only visual contracts. Workers never supply replacement slide text."""
from __future__ import annotations

import copy
import math
import re

PALETTE = {"paper":"#F6F4EF", "ink":"#151B24", "primary":"#355E78", "table_header":"#3E6278"}


def text_of(obj):
    return "\n".join("".join(r["text"] for r in para) for para in obj.get("paras", []))


def objects(model):
    return {f"{kind}:{i}": obj for kind in ("texts", "tables", "shapes", "figures", "rasters") for i, obj in enumerate(model.get(kind, []))}


def contract(model):
    slots = []
    for key, obj in objects(model).items():
        s = {"id":key, **{k:obj[k] for k in ("x","y","w","h")}}
        if key.startswith("texts:"):
            s.update(text=text_of(obj), role=obj.get("role"), size=max((r["size"] for p in obj["paras"] for r in p), default=18), paragraph_count=len(obj["paras"]))
        if key.startswith("tables:"):
            s["cells"] = [[text_of(c) for c in row["cells"]] for row in obj["rows"]]
            s.update(column_count=len(obj["rows"][0]["cells"]), row_count=len(obj["rows"]))
        slots.append(s)
    return {"slots":slots, "connectors":copy.deepcopy(model["lines"]),
            "rules":["逐个覆盖所有 slots；只提交位置、大小与文字样式，不提交任何替换文字。文本框可设 font、bold、line_height；paragraph_styles 按 paragraph_count 逐段设置 font、bold、size、color，禁止替换原文。",
                     "从完整设计稿还原原生文字区与组件分组。保留完整表格、限定条件、来源与阅读顺序。",
                     "表格可设 font、size、line_height、col_widths 与 row_heights；列数、行数和原文锁定，宽度总和须等于表宽、高度总和须等于表高，填色保持不变。",
                     "连接线的起终对象与方向锁定；随对象移动，不能增删或反向。图表数据形状的几何锁定。",
                     "组件 name 只用于编辑分组，bbox 为 1280×720 坐标。允许纹理损失，须说明视觉差异。"]}


def accept_layout(model, result, chart=False):
    if set(result) - {"input_sha256","objects","components","differences","design_inspected"}:
        raise ValueError("版面结果含未知字段")
    if result.get("design_inspected") is not True: raise ValueError("请实际查看设计稿并记录 design_inspected")
    known = objects(model); edits=result.get("objects",[])
    if not isinstance(edits,list) or len(edits)!=len(known) or {e.get("id") for e in edits}!=set(known):
        raise ValueError("版面须完整且不重复地覆盖全部锁定对象")
    out=copy.deepcopy(model); edited=objects(out)
    def box(obj):
        for k in ("x","y","w","h"):
            if isinstance(obj.get(k),bool) or not isinstance(obj.get(k),(int,float)) or not math.isfinite(obj[k]): raise ValueError("版面坐标无效")
        if obj["x"]<0 or obj["y"]<0 or min(obj["w"],obj["h"])<=0 or obj["x"]+obj["w"]>1280.5 or obj["y"]+obj["h"]>720.5:
            raise ValueError("版面对象越界")
    for e in edits:
        if set(e)-{"id","x","y","w","h","size","color","hidden","font","bold","line_height","paragraph_styles","col_widths","row_heights"}: raise ValueError("对象只能调整几何、文字样式或容器可见性")
        key=e["id"]; obj=edited[key]; old=known[key]; box(e)
        if {"col_widths","row_heights"}.intersection(e) and not key.startswith("tables:"): raise ValueError("行高与列宽只适用于表格")
        if chart and key.startswith("shapes:") and any(e[k]!=old[k] for k in ("x","y","w","h")): raise ValueError("数据图形几何锁定，不可改变")
        if e.get("hidden") and (not key.startswith("shapes:") or chart): raise ValueError("只能隐藏非图表页的装饰容器")
        obj.update({k:e[k] for k in ("x","y","w","h")}); obj["hidden"]=bool(e.get("hidden",False))
        if key.startswith("figures:") and abs(e["w"]/e["h"]-old["w"]/old["h"])>.001: raise ValueError("原件图不可改变宽高比")
        if key.startswith("tables:"):
            if {"color","bold","paragraph_styles"}.intersection(e): raise ValueError("表格仅可调整字体、字号、行距、行高与列宽；单元格内容和填色锁定")
            def dimensions(name, count, total):
                if name not in e: return None
                values=e[name]
                if (not isinstance(values,list) or len(values)!=count or
                    any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in values) or
                    not math.isclose(sum(values),total,rel_tol=1e-6,abs_tol=.01)):
                    raise ValueError("表格行高与列宽须保持原行列数，值须为正有限数且总和匹配表格几何")
                return values
            widths=dimensions("col_widths",len(obj["rows"][0]["cells"]),e["w"])
            heights=dimensions("row_heights",len(obj["rows"]),e["h"])
            if "font" in e and (not isinstance(e["font"],str) or not re.fullmatch(r"[\w .-]{1,100}",e["font"])): raise ValueError("字体名称无效")
            if "size" in e and (isinstance(e["size"],bool) or not isinstance(e["size"],(int,float)) or not math.isfinite(e["size"]) or not 11<=e["size"]<=160): raise ValueError("字号须为 11–160")
            if "line_height" in e and (isinstance(e["line_height"],bool) or not isinstance(e["line_height"],(int,float)) or not math.isfinite(e["line_height"]) or not 11<=e["line_height"]<=220): raise ValueError("行距须为 11–220")
            for ri,row in enumerate(obj["rows"]):
                row["h"] = heights[ri] if heights else row["h"]*e["h"]/old["h"]
                for ci,c in enumerate(row["cells"]):
                    c["w"] = widths[ci] if widths else c["w"]*e["w"]/old["w"]
                    oldsize=max((r["size"] for para in c["paras"] for r in para),default=18)
                    if "size" in e: c["lineHeight"] *= e["size"]/oldsize
                    if "line_height" in e: c["lineHeight"]=e["line_height"]
                    for para in c["paras"]:
                        for run in para:
                            for name in ("font","size"):
                                if name in e: run[name]=e[name]
            continue
        if "size" in e or "color" in e:
            if not key.startswith("texts:"): raise ValueError("字号与颜色只适用于文本框；表格保持锁定单元格结构")
            if "size" in e and (isinstance(e["size"],bool) or not isinstance(e["size"],(int,float)) or not math.isfinite(e["size"]) or not 11<=e["size"]<=160): raise ValueError("字号须为 11–160")
            if "color" in e and not re.fullmatch(r"#[0-9A-Fa-f]{6}",e["color"]): raise ValueError("颜色须为六位十六进制")
            oldsize=max((r["size"] for p in obj["paras"] for r in p),default=18)
            ratio=e.get("size",oldsize)/oldsize; obj["lineHeight"]*=ratio
            for para in obj["paras"]:
                for r in para:
                    r["size"]*=ratio
                    if "color" in e: r["color"]={"hex":e["color"][1:],"a":1}
        style_keys={"font","bold","line_height","paragraph_styles"}
        if style_keys.intersection(e):
            if not key.startswith("texts:"): raise ValueError("文字样式只适用于文本框")
            def apply_style(style, runs):
                if not isinstance(style,dict) or set(style)-{"font","bold","size","color"}: raise ValueError("分段样式不得替换锁定文字")
                if "font" in style and (not isinstance(style["font"],str) or not re.fullmatch(r"[\w .-]{1,100}",style["font"])): raise ValueError("字体名称无效")
                if "bold" in style and not isinstance(style["bold"],bool): raise ValueError("字重须为布尔值")
                if "size" in style and (isinstance(style["size"],bool) or not isinstance(style["size"],(int,float)) or not math.isfinite(style["size"]) or not 11<=style["size"]<=160): raise ValueError("字号须为 11–160")
                if "color" in style and (not isinstance(style["color"],str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}",style["color"])): raise ValueError("颜色须为六位十六进制")
                for run in runs:
                    for name in ("font","bold","size"):
                        if name in style: run[name]=style[name]
                    if "color" in style: run["color"]={"hex":style["color"][1:],"a":1}
            common={k:e[k] for k in ("font","bold") if k in e}
            apply_style(common,[r for para in obj["paras"] for r in para])
            if "paragraph_styles" in e:
                styles=e["paragraph_styles"]
                if not isinstance(styles,list) or len(styles)!=len(obj["paras"]): raise ValueError("分段样式须逐段覆盖锁定文本")
                for style,runs in zip(styles,obj["paras"]): apply_style(style,runs)
            if "line_height" in e:
                height=e["line_height"]
                if isinstance(height,bool) or not isinstance(height,(int,float)) or not math.isfinite(height) or not 11<=height<=220: raise ValueError("行距须为 11–220")
                obj["lineHeight"]=height
        if key.startswith("shapes:"):
            for a in obj.get("accents",[]):
                a.update(x=e["x"]+(a["x"]-old["x"])*e["w"]/old["w"], y=e["y"]+(a["y"]-old["y"])*e["h"]/old["h"],
                         w=a["w"]*e["w"]/old["w"],h=a["h"]*e["h"]/old["h"])
    # Native arrows retain the locked endpoints; interpolate the elbow route
    # after moving the endpoint containers. No worker-authored relation geometry.
    containers={k:v for k,v in known.items() if k.startswith("shapes:")}
    def nearest(pt):
        def distance(v):
            return max(v["x"]-pt[0],0,pt[0]-v["x"]-v["w"])**2+max(v["y"]-pt[1],0,pt[1]-v["y"]-v["h"])**2
        return min(containers,key=lambda k:distance(containers[k])) if containers else None
    for ln in out["lines"]:
        pts=ln["points"]; moves=[]
        for pt in (pts[0],pts[-1]):
            key=nearest(pt)
            if key:
                old,new=known[key],edited[key]
                moves.append([new["x"]+(pt[0]-old["x"])*new["w"]/old["w"]-pt[0],new["y"]+(pt[1]-old["y"])*new["h"]/old["h"]-pt[1]])
            else: moves.append([0,0])
        ln["points"]=[[x+moves[0][0]*(1-i/(len(pts)-1))+moves[1][0]*i/(len(pts)-1),y+moves[0][1]*(1-i/(len(pts)-1))+moves[1][1]*i/(len(pts)-1)] for i,(x,y) in enumerate(pts)]
        if any(not(0<=x<=1280 and 0<=y<=720) for x,y in ln["points"]): raise ValueError("连接线越界")
    components=result.get("components",[])
    if not isinstance(components,list) or not 1<=len(components)<=100: raise ValueError("须提交 1–100 个可编辑组件区域")
    names=[]
    for c in components:
        if set(c)!={"name","x","y","w","h"} or not isinstance(c["name"],str) or not 1<=len(c["name"])<=100: raise ValueError("组件字段无效")
        box(c); names.append(c["name"])
    if len(set(names))!=len(names): raise ValueError("组件名称重复")
    if not isinstance(result.get("differences"),list) or any(not isinstance(s,str) for s in result["differences"]): raise ValueError("须记录视觉差异列表")
    out["shapes"]=[s for s in out["shapes"] if not s.pop("hidden",False)]
    return out
