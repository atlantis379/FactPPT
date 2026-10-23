"""Composed pages: one design solution per page.

A composed page places blocks on the body (1152 px wide; 462 px high under a title, 436 px under a title and a
lead). Every block is a primitive the PPTX exporter rebuilds natively: text boxes, filled or outlined surfaces
(round ones become circles), rules, markers, proportional bars, arrow lines and icons. What the page says is still only
verified facts and linted authored labels; the composition — what is seen first, what is read next, what is kept
for reference — is the page's own and is recorded in its design note.

Rules that follow from meaning apply to every composed page:
  * blocks that are peers (same `peer` key) share one surface treatment, since peers are equal;
  * a bar's length is its value on a shared scale, from zero;
  * an arrow is backed by a source arrow, or by one source sentence whose two excerpts it joins in order (a split
    sentence; listed for semantic review);
  * an icon stands for one term the page shows in a text block (`for`); it never says anything the text does not;
  * a drawn line names the facts it draws (`encodes`), or is an axis (`axis: true`);
  * a page that draws states in `design.figure` the layer its drawing carries that the text cannot (where a number
    sits on a scale, how a course runs over time, how parts connect). A drawing without such a layer is not drawn.
"""
from __future__ import annotations

import re

from .lexicon import canon

BODY_W = 1152
BODY_H = {False: 462, True: 436}          # body height without / with a lead
KINDS = {"text", "surface", "rule", "marker", "bar", "arrow", "line", "icon"}
LINE_TONES = {"primary2", "accent", "line", "muted", "primary"}
# text roles: (size px, weight, tone); a block may override size (from SIZES), weight and tone
ROLES = {"head": (20, 700, "primary"), "key": (21, 400, "ink"), "body": (17, 400, "ink"), "sub": (15, 400, "ink"),
         "label": (13, 700, "muted"), "note": (13, 400, "muted"), "ref": (12, 400, "muted"), "value": (40, 700, "accent")}
SIZES = {12, 13, 14, 15, 16, 17, 18, 20, 21, 22, 24, 26, 28, 32, 34, 40, 48, 56, 64}
TEXT_TONES = {"ink", "muted", "primary", "primary2", "accent", "on-dark", "on-dark-accent"}
SURFACE_TONES = {"line", "tint", "strong", "accent", "white"}
RULE_TONES = {"line", "strong", "accent"}
BAR_TONES = {"strong", "quiet", "accent"}
SIGNALS = {"whitespace", "repetition", "type_sizes", "strong_areas", "balance", "alignment"}
DESIGN_KEYS = {"first", "then", "reference", "strong", "exceptions", "figure"}
DRAWN = {"line", "icon", "arrow", "bar"}     # blocks that draw: a page with any of them states its figure layer
LINE_H = 1.55                           # running text: line height as a multiple of the size
LINE_H_DISPLAY = 1.3                    # display sizes (24 px and up: values, large names) set tighter


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def structure_errors(page: dict) -> list[str]:
    """Shape of a composed page: known block kinds, geometry inside the body, valid roles/tones, arrow ends, peers."""
    errors = []
    blocks = page.get("blocks") or []
    body_h = BODY_H[bool(page.get("lead") or page.get("headline"))]
    ids = [b.get("id") for b in blocks if isinstance(b, dict) and b.get("id")]
    if len(set(ids)) != len(ids):
        errors.append("blocks 的 id 重复")
    by_id = {b["id"]: b for b in blocks if isinstance(b, dict) and b.get("id")}
    for i, b in enumerate(blocks):
        where = f"blocks[{i}]"
        if not isinstance(b, dict) or b.get("kind") not in KINDS:
            errors.append(f"{where} 的 kind 需为 {'、'.join(sorted(KINDS))} 之一")
            continue
        k = b["kind"]
        if k == "arrow":
            pts = b.get("points")
            if not (isinstance(pts, list) and len(pts) >= 2 and all(isinstance(p, list) and len(p) == 2 and all(_num(v) for v in p) for p in pts)):
                errors.append(f"{where} 箭头需有 points：[[x, y], [x, y], …]")
            elif any(not (-0.5 <= x <= BODY_W + 0.5 and -0.5 <= y <= body_h + 0.5) for x, y in pts):
                errors.append(f"{where} 箭头超出版心")
            if not (b.get("from") in by_id and b.get("to") in by_id):
                errors.append(f"{where} 箭头需以 from / to 指明两端的文字块 id")
            elif not all(by_id[x]["kind"] == "text" for x in (b["from"], b["to"])):
                errors.append(f"{where} 箭头两端须为文字块")
            if not isinstance(b.get("backed_by"), str):
                errors.append(f"{where} 箭头需以 backed_by 给出支持事实")
            continue
        if k == "line":                                   # a drawn course (a curve, an axis), not a relation
            pts = b.get("points")
            if not (isinstance(pts, list) and len(pts) >= 2 and all(isinstance(p, list) and len(p) == 2 and all(_num(v) for v in p) for p in pts)):
                errors.append(f"{where} 线条需有 points：[[x, y], [x, y], …]")
            elif any(not (-0.5 <= x <= BODY_W + 0.5 and -0.5 <= y <= body_h + 0.5) for x, y in pts):
                errors.append(f"{where} 线条超出版心")
            if b.get("tone", "primary2") not in LINE_TONES:
                errors.append(f"{where} 线条 tone 需为 {'、'.join(sorted(LINE_TONES))} 之一")
            enc = b.get("encodes")
            if not b.get("axis") and not (isinstance(enc, list) and enc and all(isinstance(x, str) for x in enc)):
                errors.append(f"{where} 线条需以 encodes 列出它画出的事实（本页显示的事实编号），坐标轴与网格线写 axis: true")
            continue
        if k == "icon":
            shown = {first_fact(t) for t in blocks if isinstance(t, dict) and t.get("kind") == "text"}
            if not isinstance(b.get("icon"), str):
                errors.append(f"{where} 图标需以 icon 指明图标文件 id")
            if not (isinstance(b.get("for"), str) and b["for"] in shown):
                errors.append(f"{where} 图标需以 for 指明它代表的事实，且该事实须是本页某个文字块的首个事实")
        geo = [b.get(x) for x in ("x", "y", "h")] + ([b.get("w")] if k != "bar" else [b.get("max_w")])
        if not all(_num(v) for v in geo):
            errors.append(f"{where} 需给出数值 x、y、{'max_w' if k == 'bar' else 'w'}、h")
            continue
        x, y, h, w = geo
        if x < -0.5 or y < -0.5 or x + w > BODY_W + 0.5 or y + h > body_h + 0.5 or w <= 0 or h <= 0:
            errors.append(f"{where} 超出版心（宽 {BODY_W}、高 {body_h}）")
        if k == "text":
            refs = b.get("refs")
            if not (isinstance(refs, list) and refs):
                errors.append(f"{where} 文字块需有 refs（事实或作者文字的列表）")
            if b.get("role") not in ROLES:
                errors.append(f"{where} role 需为 {'、'.join(ROLES)} 之一")
            if "size" in b and b["size"] not in SIZES:
                errors.append(f"{where} size 需取字号阶梯 {sorted(SIZES)} 中的值")
            if "tone" in b and b["tone"] not in TEXT_TONES:
                errors.append(f"{where} 文字 tone 需为 {'、'.join(sorted(TEXT_TONES))} 之一")
            if b.get("align", "left") not in {"left", "center", "right"}:
                errors.append(f"{where} align 需为 left / center / right")
        elif k == "surface" and b.get("tone") not in SURFACE_TONES:
            errors.append(f"{where} 面 tone 需为 {'、'.join(sorted(SURFACE_TONES))} 之一")
        elif k == "rule" and b.get("tone", "line") not in RULE_TONES:
            errors.append(f"{where} 线 tone 需为 {'、'.join(sorted(RULE_TONES))} 之一")
        elif k == "marker" and b.get("tone") not in SURFACE_TONES:
            errors.append(f"{where} 标记 tone 需为 {'、'.join(sorted(SURFACE_TONES))} 之一")
        elif k == "bar":
            if not isinstance(b.get("value_of"), str) or not isinstance(b.get("scale"), str):
                errors.append(f"{where} 条形需以 value_of 指明数值事实、以 scale 指明同一刻度组")
            if b.get("tone", "quiet") not in BAR_TONES:
                errors.append(f"{where} 条形 tone 需为 {'、'.join(sorted(BAR_TONES))} 之一")
    peers: dict[str, list[dict]] = {}
    for b in blocks:
        if isinstance(b, dict) and b.get("peer"):
            peers.setdefault(b["peer"], []).append(b)
    for key, group in peers.items():
        looks = {(b.get("kind"), b.get("tone"), b.get("role"), b.get("size"), b.get("weight"), b.get("radius"), bool(b.get("round")))
                 for b in group}
        if len(looks) > 1:
            errors.append(f"并列组“{key}”的各项处理不一致：并列的各项须同等处理，重点用位置或关系表达，而不是让其中一项更醒目")
    d = page.get("design")
    drawn = sorted({b["kind"] for b in blocks if isinstance(b, dict) and b.get("kind") in DRAWN} | ({"diagram"} if page.get("diagram") else set()))
    if drawn and not (isinstance(d, dict) and isinstance(d.get("figure"), str) and d["figure"].strip()):
        errors.append(f"本页画了图（{'、'.join(drawn)}）：须在 design.figure 写明这张图承担了哪一层文字讲不了的内容；说不出来就不画")
    if d is not None:
        if not isinstance(d, dict) or set(d) - DESIGN_KEYS:
            errors.append(f"design 只能包含 {'、'.join(sorted(DESIGN_KEYS))}")
        else:
            for e in d.get("exceptions") or []:
                if not (isinstance(e, dict) and e.get("signal") in SIGNALS and str(e.get("reason", "")).strip()):
                    errors.append(f"design.exceptions 每项需为 {{signal: {'|'.join(sorted(SIGNALS))}, reason: 理由}}")
    return errors


def bar_values(page: dict, facts: dict) -> dict[str, float]:
    """Numeric value of every bar (from its value fact's shown text); raises ValueError on a non-number."""
    out = {}
    for b in page.get("blocks") or []:
        if isinstance(b, dict) and b.get("kind") == "bar":
            f = facts.get(b["value_of"]) or {}
            text = f.get("display") or f.get("quote") or f.get("text") or ""
            nums = re.findall(r"-?\d[\d,]*\.?\d*", text)
            if len(nums) != 1:
                raise ValueError(f"条形 {b['value_of']} 的事实“{text}”须恰好含一个数值")
            out[b["value_of"]] = float(nums[0].replace(",", ""))
    return out


def chain_backs(fact: dict | None, a: dict | None, b: dict | None) -> bool:
    """True if `fact` is one accepted source sentence that contains the two shown excerpts a → b in this order
    (a sentence split into steps: the arrow shows the sentence's own order, not a new relation)."""
    if not fact or fact.get("figure") or fact.get("status") != "ACCEPTED" or not a or not b:
        return False
    if not (a.get("unit") == b.get("unit") == fact.get("unit")):
        return False
    q = canon(fact["quote"])
    ta, tb = (canon(x.get("display") or x.get("quote") or "") for x in (a, b))
    i = q.find(ta)
    return bool(ta and tb) and i >= 0 and q.find(tb, i + len(ta)) >= 0


def first_fact(block: dict) -> str | None:
    for r in block.get("refs") or []:
        if isinstance(r, dict) and "fact" in r:
            return r["fact"]
    return None


def model(page: dict, values: dict[str, float]) -> dict:
    """Render model: every block with its inline style; bars sized on their shared scale; arrows as polylines."""
    top = {}
    for b in page["blocks"]:
        if b["kind"] == "bar":
            top[b["scale"]] = max(top.get(b["scale"], 0), abs(values[b["value_of"]]))
    blocks, arrows = [], []
    for b in page["blocks"]:
        k = b["kind"]
        if k == "arrow":
            arrows.append({"support": b["backed_by"], "tone": b.get("tone", "primary2"), "group": b.get("group", ""),
                           "head": True, "dash": "", "width": b.get("width", 2),
                           "points": " ".join(f"{x},{y}" for x, y in b["points"])})
            continue
        if k == "line":
            tone = b.get("tone", "primary2")
            arrows.append({"support": "", "tone": tone, "group": b.get("group", ""), "head": bool(b.get("head")),
                           "dash": "6 4" if b.get("dash") else "", "width": b.get("width", 2),
                           "var": {"on-dark": "accent-on-dark", "primary2": "primary2", "accent": "accent",
                                   "primary": "primary", "line": "line", "muted": "muted"}[tone],
                           "points": " ".join(f"{x},{y}" for x, y in b["points"])})
            continue
        w = b["w"] if k != "bar" else round(abs(values[b["value_of"]]) / (top[b["scale"]] or 1) * b["max_w"], 1)
        style = f"left:{b['x']}px;top:{b['y']}px;width:{w}px;height:{b['h']}px"
        m = {**b, "w": w}
        if k == "text":
            size, weight, tone = ROLES[b["role"]]
            size = b.get("size", size)
            weight = 700 if b.get("weight") == "bold" else 400 if b.get("weight") == "regular" else weight
            lh = round(size * (LINE_H_DISPLAY if size >= 24 else LINE_H))
            style += (f";font-size:{size}px;line-height:{lh}px;font-weight:{weight};color:var(--t-{b.get('tone', tone)})"
                      f";text-align:{b.get('align', 'left')}")
            if b.get("valign") == "middle":
                style += ";display:flex;align-items:center" + (";justify-content:center" if b.get("align") == "center" else "")
        elif k in ("surface", "marker"):
            radius = "50%" if b.get("round") else f"{b.get('radius', 10 if k == 'surface' else 3)}px"
            style += f";border-radius:{radius}"
        m["style"] = style
        blocks.append(m)
    return {"blocks": blocks, "arrows": arrows}
