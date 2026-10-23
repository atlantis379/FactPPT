"""Convert archived vector artwork to native, grouped Office custom geometry.

SVG is input data, never an image fallback. Unsupported effects fail explicitly.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path

from lxml import etree


def trace_svg(data: bytes, components=(), preserve_order=False, target_size=(1280,720)):
    from fontTools.svgLib.path import parse_path
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.misc.transform import Transform

    if len(data) > 40 * 1024 * 1024 or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("SVG 太大或含文档实体")
    root = etree.fromstring(data, etree.XMLParser(resolve_entities=False, no_network=True))
    allowed = {"svg", "g", "path", "defs", "linearGradient", "stop", "title", "desc", "metadata"}
    for el in root.iter():
        if not isinstance(el.tag, str): continue
        tag=etree.QName(el).localname
        if tag in {"script","style","image","foreignObject","use","a","iframe","object","embed","animate","animateTransform","set"}:
            raise ValueError("SVG 不支持的元素："+tag)
        if any(etree.QName(k).localname.lower().startswith("on") or etree.QName(k).localname in {"href", "filter", "mask", "clip-path"} for k in el.attrib):
            raise ValueError("SVG 不支持外部引用、事件或裁剪效果")
        if any(isinstance(a.tag,str) and etree.QName(a).localname=="metadata" for a in el.iterancestors()): continue
        if tag not in allowed:
            raise ValueError("SVG 不支持的元素：" + tag)
    view = [float(v) for v in re.split(r"[,\s]+", root.get("viewBox", "").strip()) if v]
    if not view:
        view = [0, 0, float(root.get("width", "0").removesuffix("px")), float(root.get("height", "0").removesuffix("px"))]
    if len(view) != 4 or not all(math.isfinite(v) for v in view) or min(view[2:]) <= 0:
        raise ValueError("SVG 需要有效 viewBox 或宽高")
    if len(target_size)!=2 or not all(math.isfinite(n) and n>0 for n in target_size):
        raise ValueError('无效的矢量目标尺寸')
    if abs(view[2] / view[3] / (target_size[0] / target_size[1]) - 1) > .02:
        raise ValueError("SVG 宽高比须与 16:9 页面一致")

    def styles(el, inherited):
        s = dict(inherited)
        s.update({k: v for k, v in el.attrib.items() if k in {"fill", "stroke", "stroke-width", "opacity", "fill-opacity", "stroke-opacity", "fill-rule"}})
        for part in el.get("style", "").split(";"):
            if ":" in part:
                k, v = part.split(":", 1); s[k.strip()] = v.strip()
        if set(s) - {"fill", "stroke", "stroke-width", "opacity", "fill-opacity", "stroke-opacity", "fill-rule"}:
            raise ValueError("SVG 含未支持的样式")
        return s

    def color(value, gradients):
        value = value.strip()
        if value == "none": return None
        if value in {"white", "black"}: value = "#ffffff" if value == "white" else "#000000"
        if value.startswith("url(#") and value.endswith(")"):
            if value[5:-1] not in gradients: raise ValueError("SVG 渐变引用不存在")
            return gradients[value[5:-1]]
        if re.fullmatch(r"#[0-9a-fA-F]{3}", value): value = "#" + "".join(x * 2 for x in value[1:])
        if re.fullmatch(r"#[0-9a-fA-F]{6}", value): return value.upper()
        m = re.fullmatch(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", value)
        if m and all(0 <= int(n) <= 255 for n in m.groups()): return "#" + "".join(f"{int(n):02X}" for n in m.groups())
        raise ValueError("SVG 未支持的颜色：" + value[:80])

    gradients = {}
    for el in root.iter():
        if not isinstance(el.tag, str) or etree.QName(el).localname != "linearGradient": continue
        values = []
        for stop in el:
            if not isinstance(stop.tag, str): continue
            st = dict(x.strip().split(":", 1) for x in stop.get("style", "").split(";") if ":" in x)
            c = color(stop.get("stop-color") or st.get("stop-color", "black"), {})
            if float(stop.get("stop-opacity") or st.get("stop-opacity", "1")) != 1: raise ValueError("透明渐变尚未支持")
            values.append([int(c[i:i+2], 16) for i in (1, 3, 5)])
        if not values: raise ValueError("SVG 渐变没有色标")
        gradients[el.get("id")] = "#" + "".join(f"{round(sum(v[i] for v in values)/len(values)):02X}" for i in range(3))

    def transform(value):
        out = Transform()
        remainder = re.sub(r"(matrix|translate|scale|rotate)\s*\([^)]*\)", "", value)
        if remainder.strip(): raise ValueError("SVG 未支持的变换：" + value)
        for name, args in re.findall(r"(matrix|translate|scale|rotate)\s*\(([^)]*)\)", value):
            v = [float(x) for x in re.split(r"[,\s]+", args.strip()) if x]
            if not all(math.isfinite(x) for x in v): raise ValueError("SVG 变换数值无效")
            if name == "matrix" and len(v) == 6: t = Transform(*v)
            elif name == "translate" and len(v) in {1, 2}: t = Transform().translate(v[0], v[1] if len(v) == 2 else 0)
            elif name == "scale" and len(v) in {1, 2}: t = Transform().scale(v[0], v[1] if len(v) == 2 else v[0])
            elif name == "rotate" and len(v) in {1, 3}:
                x, y = v[1:] if len(v) == 3 else (0, 0)
                t = Transform().translate(x, y).rotate(math.radians(v[0])).translate(-x, -y)
            else: raise ValueError("SVG 变换参数无效")
            out = out.transform(t)
        return out

    scale = Transform(target_size[0]/view[2], 0, 0, target_size[1]/view[3], -view[0]*target_size[0]/view[2], -view[1]*target_size[1]/view[3])
    buckets = {}; count = 0; total = 0; omitted = 0
    def walk(el, parent, inherited):
        nonlocal count, total, omitted
        if not isinstance(el.tag, str): return
        tag = etree.QName(el).localname
        if tag in {"defs", "title", "desc", "metadata"}: return
        tr = parent.transform(transform(el.get("transform", "")))
        st = styles(el, inherited)
        if tag == "path":
            count += 1
            if count > 100000: raise ValueError("SVG 路径过多")
            fill = color(st.get("fill", "black"), gradients); stroke = color(st.get("stroke", "none"), gradients)
            if st.get("fill-rule", "nonzero") != "nonzero": raise ValueError("SVG evenodd 填充尚未支持")
            if st.get("stroke-opacity", "1") != st.get("fill-opacity", "1") and stroke: raise ValueError("不同填充与描边透明度尚未支持")
            opacity = float(st.get("opacity", "1")) * float(st.get("fill-opacity", "1"))
            width = float(st.get("stroke-width", "1")) * (abs(tr.xx) + abs(tr.yy)) / 2
            if not math.isfinite(opacity) or not 0 <= opacity <= 1 or not math.isfinite(width) or width < 0: raise ValueError("SVG 透明度或描边无效")
            pen = RecordingPen(); parse_path(el.get("d", ""), TransformPen(pen, tr))
            commands = []
            for op, points in pen.value:
                if op == "endPath": continue
                cmd = [{"moveTo":"M", "lineTo":"L", "curveTo":"C", "qCurveTo":"Q", "closePath":"Z"}[op], *[round(n, 4) for pt in points for n in pt]]
                if not all(math.isfinite(n) and abs(n) < 100000 for n in cmd[1:]): raise ValueError("SVG 坐标无效")
                commands.append(cmd)
            total += len(commands)
            if total > 1500000: raise ValueError("SVG 顶点过多")
            coords = [c[1:] for c in commands if len(c) > 1]
            if not coords: return
            if fill and not stroke:
                rgb = [int(fill[i:i+2], 16) for i in (1,3,5)]
                if min(rgb) >= 232 and max(rgb)-min(rgb) <= 8: omitted += 1; return
                fill = "#" + "".join(f"{min(255,round(n/4)*4):02X}" for n in rgb)
            xs = [v for row in coords for v in row[::2]]; ys = [v for row in coords for v in row[1::2]]
            x, y = (min(xs)+max(xs))/2, (min(ys)+max(ys))/2
            group = next((g["name"] for g in components if g["x"] <= x <= g["x"]+g["w"] and g["y"] <= y <= g["y"]+g["h"]), "视觉组件")
            key = (group, fill, stroke, width, opacity, count if preserve_order else None)
            buckets.setdefault(key, {"commands":[], "fill":fill, "stroke":stroke, "width":width, "opacity":opacity, "group":group, "name":group})["commands"].extend(commands)
        for child in el: walk(child, tr, st)
    walk(root, scale, {})
    if not buckets: raise ValueError("SVG 没有可导出的矢量路径")
    return list(buckets.values()), {"raw_paths":count, "native_paths":len(buckets), "commands":total, "paper_paths_omitted":omitted,
                                   "differences":["近白纸张颗粒省略；颜色按4级量化；组件按指定区域归组。", "保留原始路径的绘制顺序。" if preserve_order else "同色路径合并，交叠色面的绘制顺序可能轻微变化。"] + (["线性渐变使用平均色近似。"] if gradients else [])}


def add_native_vectors(pptx_path: Path, vector_models, on_top: bool = False):
    """Add each slide's traced vectors as grouped custom geometry: behind every native object (artwork under a page),
    or, with `on_top`, above them (icons that sit on surfaces)."""
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.oxml.xmlchemy import OxmlElement
    from pptx.oxml.ns import qn
    from pptx.util import Emu
    prs = Presentation(pptx_path)
    for slide, vectors in zip(prs.slides, vector_models):
        groups = defaultdict(list); tree = slide.shapes._spTree
        for i, v in enumerate(vectors):
            coords = [c[1:] for c in v["commands"] if len(c)>1]
            xs = [x for row in coords for x in row[::2]]; ys = [y for row in coords for y in row[1::2]]
            x0, y0 = min(xs), min(ys); w, h = max(max(xs)-x0,.1), max(max(ys)-y0,.1)
            sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(round(x0*9525)), Emu(round(y0*9525)), Emu(round(w*9525)), Emu(round(h*9525)))
            sh.name = f'{v["name"]} {i+1}'; sp = sh._element.spPr
            sp.remove(sp.find(qn("a:prstGeom")))
            geom = OxmlElement("a:custGeom")
            for name in ("avLst", "gdLst", "ahLst", "cxnLst"): geom.append(OxmlElement("a:"+name))
            rect = OxmlElement("a:rect")
            for k, val in dict(l="0",t="0",r="r",b="b").items(): rect.set(k,val)
            geom.append(rect); paths = OxmlElement("a:pathLst"); path = OxmlElement("a:path")
            path.set("w",str(max(1,round(w*1000)))); path.set("h",str(max(1,round(h*1000))))
            path.set("fill","norm" if v["fill"] else "none"); path.set("stroke","1" if v["stroke"] else "0")
            for cmd in v["commands"]:
                el = OxmlElement("a:"+{"M":"moveTo","L":"lnTo","C":"cubicBezTo","Q":"quadBezTo","Z":"close"}[cmd[0]])
                for j in range(1,len(cmd),2):
                    pt=OxmlElement("a:pt"); pt.set("x",str(round((cmd[j]-x0)*1000))); pt.set("y",str(round((cmd[j+1]-y0)*1000))); el.append(pt)
                path.append(el)
            paths.append(path); geom.append(paths); sp.insert(1,geom)
            def fill(parent, value):
                node=OxmlElement("a:solidFill" if value else "a:noFill")
                if value:
                    rgb=OxmlElement("a:srgbClr"); rgb.set("val",value.lstrip("#"))
                    if v["opacity"]<1:
                        alpha=OxmlElement("a:alpha"); alpha.set("val",str(round(v["opacity"]*100000))); rgb.append(alpha)
                    node.append(rgb)
                parent.append(node)
            for old in list(sp):
                if old.tag in {qn("a:solidFill"),qn("a:noFill"),qn("a:ln")}: sp.remove(old)
            fill(sp,v["fill"]); ln=OxmlElement("a:ln"); ln.set("w",str(round(v["width"]*9525))); fill(ln,v["stroke"]); sp.append(ln)
            sh.shadow.inherit=False; sh.text_frame.text=""; groups[v["group"]].append(sh)
        # All generated components sit behind native semantic objects, including title placeholders.
        insert = 2
        for name, shapes in groups.items():
            group=slide.shapes.add_group_shape(shapes); group.name=name; group.shadow.inherit=False
            if on_top: continue
            tree.remove(group._element); tree.insert(insert,group._element); insert+=1
    prs.save(pptx_path)
