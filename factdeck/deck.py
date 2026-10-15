"""Deck specification checks.

Pages reference facts by id. Text written by the model (titles, leads, labels,
column headers) is allowed only if it carries no substantive content of its own
(see lexicon.lint_text); glossary terms backed by a fact are exempt. Every arrow
in a diagram must name the fact that supports it: a fact shown on the page, or a
transcribed source arrow "A→B" joining the two nodes' texts. The deck must cover every
outline item, and every summary section must be shown on a page or listed as an
omission with a reason the customer can see. A source figure is shown only in a
`figure` slot (a `figure` page, or a `compare` panel) and only as a figure fact;
its caption facts are shown with it. A page shows at most two source figures.
A fact reference may emphasise up to three verbatim fragments of its own text
(`{"fact": id, "emph": ["38%"]}`); emphasis changes weight and colour, never text.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .lexicon import lint_text, canon
from . import charts
from . import compose
from . import recipes

LAYOUTS = {
    # layout: (required keys, limits)
    "cover": ({"title"}, {}),
    "divider": ({"title"}, {}),
    "bullets": ({"title", "items"}, {"items": (1, 8)}),
    "table": ({"title", "columns", "rows"}, {"columns": (2, 7), "rows": (1, 9)}),
    "cards": ({"title", "cards"}, {"cards": (2, 4), "notes": (0, 4)}),
    "compare": ({"title", "panels"}, {"panels": (2, 3), "band": (0, 2), "notes": (0, 3), "footnote": (0, 2)}),
    "flow": ({"title", "nodes", "edges"}, {"nodes": (2, 16), "side": (0, 4), "notes": (0, 3), "footnote": (0, 2)}),
    "statement": ({"title", "statement"}, {"support": (0, 3)}),
    "closing": ({"title"}, {"items": (0, 6)}),
    "agenda": ({"title", "items"}, {"items": (2, 8)}),
    "figure": ({"title", "figure"}, {"side": (0, 3)}),
    "hero": ({"title", "value"}, {"support": (0, 3)}),
    "timeline": ({"title", "steps"}, {"steps": (2, 6)}),
    "grid": ({"title", "tiles"}, {"tiles": (2, 6), "notes": (0, 3), "footnote": (0, 2)}),
    "nested": ({"title", "levels"}, {"levels": (2, 4), "notes": (0, 3), "footnote": (0, 2)}),
    "chart": ({"title", "chart"}, {"side": (0, 3)}),
    "composed": ({"title", "blocks"}, {"blocks": (1, 160)}),
}
MAX_FIGURES_PER_PAGE = 2
F = lambda i: {"fact": i}          # noqa: E731  (placeholder ids in the examples below)
T = lambda s: {"text": s}          # noqa: E731
LAYOUT_GUIDE = {
    # layout: (what it is for, minimal example body; every page also has id, layout, title, outline_ids, section_ids)
    "bullets": ("几条并列、没有更强结构的要点（纯文字页，全篇不宜超过三成）；能用下列结构化版式时优先用它们",
                {"items": [F("f1"), F("f2"), F("f3")]}),
    "table": ("多个对象×多个属性的逐项对照；同一组对象的多个属性放进同一张表（至多 7 列），不要按属性拆成多张两列表", {"columns": ["对象", "属性甲", "属性乙"],
                                           "rows": [[[F("f1")], [F("f2")], [F("f3")]], [[F("f4")], [F("f5")], [F("f6")]]]}),
    "cards": ("2–4 个并列指标/阈值/条件，名称在上、值醒目；notes 放补充说明",
              {"cards": [{"label": F("f1"), "value": F("f2")}, {"label": F("f3"), "value": F("f4")}],
               "notes_title": T("补充说明"), "notes": [F("f5")]}),
    "compare": ("2–3 组对照（两项研究、两种方案、两类人群），每组标题+主值+条目；band 放贯穿两组的结论事实",
                {"panels": [{"heading": F("f1"), "value": F("f2"), "value_label": F("f3"), "items": [F("f4"), F("f5")]},
                            {"heading": F("f6"), "value": F("f7"), "value_label": F("f8"), "items": [F("f9")]}],
                 "band": [F("f10")]}),
    "flow": ("流程、机制、通路、判断路径；节点在 col 0–4、row 0–3 网格上，箭头 [起点, 终点, 支持事实, 标签?]；"
             "支持事实为本页引用的事实，或原件箭头单元建成的事实（不必上页，两端须是两个节点所引事实的单元）；"
             "标签为箭头上的是/否等短事实；tag 为节点下方的附注事实，side 为右侧说明",
             {"nodes": [{"id": "a", "ref": F("n1"), "col": 0, "row": 0}, {"id": "b", "ref": F("n2"), "col": 1, "row": 0, "emphasis": "core"},
                        {"id": "c", "ref": F("n3"), "col": 2, "row": 0, "tag": F("n4")}],
              "edges": [["a", "b", "arrow1"], ["b", "c", "arrow2", F("yes")]], "side": [F("f1")]}),
    "timeline": ("按时间或先后顺序的 2–6 步", {"steps": [{"when": F("f1"), "what": F("f2")}, {"when": F("f3"), "what": F("f4")}]}),
    "grid": ("2–6 个维度/类别，每格标题+1–3 条", {"tiles": [{"heading": T("维度一"), "items": [F("f1")]}, {"heading": T("维度二"), "items": [F("f2"), F("f3")]}]}),
    "hero": ("一个关键短数值做主视觉（≤16 字）", {"value": F("f1"), "label": F("f2"), "support": [F("f3")]}),
    "statement": ("整页只有一句需要单独强调的原文结论时才用（纯文字页）；一句导语加若干要点时，导语放 lead、主体用结构化版式",
                  {"statement": F("f1"), "support": [F("f2")]}),
    "chart": ("同一人群、同一终点下可直接比较的 2–8 个数值", {"chart": {"bars": [{"label": T("组一"), "value": F("f1")}, {"label": T("组二"), "value": F("f2")}]}}),
    "figure": ("展示原件中的图", {"figure": F("g1"), "side": [F("f1")]}),
    "agenda": ("目录", {"items": [T("第一部分"), T("第二部分")]}),
    "divider": ("章节过渡页", {}),
    "cover": ("封面", {}),
    "closing": ("结束页，可列 0–6 条回顾要点", {"items": [F("f1")]}),
    "nested": ("包含关系：外层包含内层（如定义层级 A ⊃ B ⊃ C），由外到内逐层给出名称、至多 3 条说明和可选的数值；最内层自动为深色",
               {"levels": [{"heading": F("f1"), "items": [F("f2")]}, {"heading": F("f3"), "value": F("f4"), "items": [F("f5")]},
                           {"heading": F("f6"), "items": [F("f7")]}]}),
    "composed": ("逐页构图：优先写 recipe + slots（见 recipes：每种构图方案的用途与示例），没有合适方案时再直接放 blocks。先写 design（first 第一眼看到什么、then 随后读什么、reference 供查阅什么、strong 唯一的强元素及为何用这种形状），"
                 "再把块放在版心上（宽 1152，高 462；有 lead 时 436）。块：text（refs 事实/作者文字，role head/key/body/sub/label/note/ref/value）、"
                 "surface（tone line/tint/strong/accent/white，round 为圆）、rule、marker、bar（value_of 数值事实，同一 scale 按比例）、"
                 "arrow（points，from/to 两端文字块，backed_by 原件箭头或被拆成两段的同一句原文）。并列的各项用同一 peer 键，须同等处理",
                 {"design": {"first": "两条通路并列", "then": "各自的环节", "reference": "缩写", "strong": "靶点贴在所属通路下"},
                  "blocks": [{"kind": "surface", "tone": "tint", "x": 0, "y": 0, "w": 1152, "h": 120, "peer": "lane"},
                             {"kind": "text", "id": "a", "role": "body", "refs": [F("s1")], "x": 24, "y": 20, "w": 300, "h": 80},
                             {"kind": "text", "id": "b", "role": "body", "refs": [F("s2")], "x": 380, "y": 20, "w": 300, "h": 80},
                             {"kind": "arrow", "from": "a", "to": "b", "backed_by": "sentence", "points": [[330, 60], [372, 60]]}]}),
}
del F, T
EDGE_LABEL_MAX = 5           # an arrow label sits in the gap between two boxes
HERO_MAX_CHARS = 16        # a hero value is a short number or phrase; longer text belongs in `statement`
SKIP = {"id", "layout", "widths", "edges", "outline_ids", "section_ids", "point_ids", "key_point_ids", "focus", "col", "row", "emphasis", "kind", "orientation",
        # composed-page geometry and styling (no shown text)
        "role", "tone", "peer", "align", "valign", "size", "weight", "radius", "round", "points", "from", "to", "backed_by",
        "value_of", "scale", "design", "sep", "recipe", "group"}


def walk(node, path=""):
    """Yield (path, kind, value) for every fact reference and authored text in a page."""
    if isinstance(node, dict):
        if "fact" in node and set(node) <= {"fact", "emph"}:
            yield path, "fact", node["fact"]
            if "emph" in node:
                yield path, "emph", (node["fact"], node["emph"])
            return
        if "text" in node and len(node) == 1:
            yield path, "text", node["text"]
            return
        for k, v in node.items():
            if k in SKIP:
                continue
            if k == "columns":
                for i, c in enumerate(v):
                    yield f"{path}.columns[{i}]", "text", c if isinstance(c, str) else c.get("text", "")
                continue
            yield from walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, "bad", node


MAX_EMPH = 3


def emph_spans(text: str, emph: list[str]) -> list[tuple[str, bool]]:
    """Split `text` into (piece, emphasised) runs; fragments are matched left to right."""
    out, pos = [], 0
    for frag in emph:
        i = text.find(frag, pos)
        if i < 0:
            raise ValueError(frag)
        if i > pos:
            out.append((text[pos:i], False))
        out.append((frag, True))
        pos = i + len(frag)
    if pos < len(text):
        out.append((text[pos:], False))
    return out


def emph_errors(path: str, fid, emph, facts: dict) -> list[str]:
    f = facts.get(fid)
    if not f:
        return []                                   # reported by the fact reference itself
    if f.get("figure"):
        return [f"{path} 图事实不能设置强调"]
    if not (isinstance(emph, list) and 1 <= len(emph) <= MAX_EMPH and all(isinstance(e, str) and e.strip() for e in emph)):
        return [f"{path} emph 需为 1–{MAX_EMPH} 个非空片段"]
    text = f["display"] or f["quote"]
    try:
        spans = emph_spans(text, emph)
    except ValueError as e:
        return [f"{path} 强调片段“{e}”须按顺序逐字出现在事实 {fid} 的显示文字中"]
    if sum(len(p) for p, on in spans if on) > 0.6 * len(text):
        return [f"{path} 强调片段过多（超过显示文字的六成），强调失去意义"]
    return []


ARROWS = ("->", "⟶", "➔", "➜", "⇒", "⇨", "→")


def _arrowed(text: str) -> str:
    t = canon(text)
    for a in ARROWS:
        t = t.replace(a, "→")
    return t


def arrow_backs(fact: dict | None, a_ref, b_ref, facts: dict) -> bool:
    """True if `fact` is an accepted source arrow joining the two nodes, in this direction.

    An arrow recovered from a slide diagram's geometry names the units at its ends: the
    nodes must show facts quoted from exactly those units. An arrow transcribed from a
    picture reads "A→B" and must join the two nodes' shown texts. Either may back an
    edge without being printed on the slide, since the drawn arrow itself shows it.
    """
    if not fact or fact.get("figure") or fact["status"] != "ACCEPTED":
        return False
    arrow = fact.get("arrow") or {}
    if arrow.get("from") and "→" in _arrowed(fact["quote"]):
        units = []
        for ref in (a_ref, b_ref):
            f = facts.get(ref.get("fact")) if isinstance(ref, dict) else None
            units.append(f.get("unit") if f and not f.get("figure") else None)
        return units == [arrow["from"], arrow["to"]]
    ends = []
    for ref in (a_ref, b_ref):
        if isinstance(ref, dict) and ref.get("fact") in facts:
            f = facts[ref["fact"]]
            ends.append(_arrowed(f["display"] or f["quote"]))
        elif isinstance(ref, dict) and "text" in ref:
            ends.append(_arrowed(ref["text"]))
        else:
            return False
    return all(ends) and f"{ends[0]}→{ends[1]}" in _arrowed(fact["quote"])


def _structure(page: dict) -> list[str]:
    layout = page.get("layout")
    if layout not in LAYOUTS:
        return [f"未知版式：{layout}（可用：{'、'.join(LAYOUTS)}）"]
    required, limits = LAYOUTS[layout]
    errors = [f"缺少字段：{k}" for k in sorted(required) if not page.get(k)]
    for key, (lo, hi) in limits.items():
        n = len(page.get(key) or [])
        if (key in required or n) and not lo <= n <= hi:
            errors.append(f"{key} 数量需为 {lo}–{hi}，当前 {n}（内容多时请拆页）")
    if layout == "table" and page.get("rows"):
        ncol = len(page["columns"])
        for i, row in enumerate(page["rows"]):
            if len(row) != ncol:
                errors.append(f"表格第{i + 1}行有 {len(row)} 格，表头 {ncol} 列")
            if any(not isinstance(cell, list) for cell in row):
                errors.append(f"表格第{i + 1}行的单元格需为引用列表")
        if page.get("widths") and len(page["widths"]) != ncol:
            errors.append("widths 数量与列数不一致")
    if layout == "chart" and page.get("chart"):
        errors += charts.structure_errors(page["chart"])
    if layout == "composed":
        errors += compose.structure_errors(page)
    if layout == "compare":
        for i, pn in enumerate(page.get("panels") or []):
            if not isinstance(pn, dict):
                errors.append(f"第{i + 1}个面板格式错误")
            elif "figure" in pn and (pn.get("items") or pn.get("value") or pn.get("value_label")):
                errors.append(f"第{i + 1}个面板放图时不能再放条目或数值（图下说明由程序随图显示）")
    if layout == "timeline":
        for i, st in enumerate(page.get("steps") or []):
            if not (isinstance(st, dict) and st.get("when") and st.get("what")):
                errors.append(f"时间线第{i + 1}步需有 when 和 what")
    if layout == "nested":
        for i, lv in enumerate(page.get("levels") or []):
            n = len(lv.get("items") or []) if isinstance(lv, dict) else 0
            if not (isinstance(lv, dict) and lv.get("heading") and n <= 3):
                errors.append(f"第{i + 1}层需有 heading，items 至多 3 条")
    for i, x in enumerate(page.get("side") or []):
        if isinstance(x, dict) and "value" in x and not x.get("label"):
            errors.append(f"侧栏第{i + 1}项是数值卡时需有 label（数值说明）")
    if layout == "grid":
        for i, t in enumerate(page.get("tiles") or []):
            n = len(t.get("items") or []) if isinstance(t, dict) else 0
            if not (isinstance(t, dict) and t.get("heading") and 1 <= n <= 3):
                errors.append(f"第{i + 1}格需有 heading 和 1–3 条 items")
    if layout == "flow" and page.get("nodes"):
        ids = [n.get("id") for n in page["nodes"]]
        if len(set(ids)) != len(ids) or not all(ids):
            errors.append("流程图节点编号为空或重复")
        cells = [(n.get("col"), n.get("row")) for n in page["nodes"]]
        if any(not (isinstance(c, int) and isinstance(r, int) and 0 <= c <= 4 and 0 <= r <= 3) for c, r in cells):
            errors.append("流程图节点需给出 col 0–4、row 0–3 的网格位置")
        elif len(set(cells)) != len(cells):
            errors.append("流程图节点网格位置重叠")
        for e in page.get("edges") or []:
            if not (isinstance(e, list) and len(e) in (3, 4) and e[0] in ids and e[1] in ids):
                errors.append(f"箭头格式需为 [起点, 终点, 支持事实] 或 [起点, 终点, 支持事实, 标签]：{e}")
            elif len(e) == 4 and not (isinstance(e[3], dict) and (set(e[3]) == {"fact"} or set(e[3]) == {"text"})):
                errors.append(f"箭头标签需写成 {{\"fact\": 编号}} 或 {{\"text\": 作者文字}}：{e}")
    return errors


NON_CONTENT = {"cover", "divider", "agenda"}


def _outline_order(pages: list[dict], points: dict, unsupported: dict, parts: list[dict], result: dict, err) -> None:
    """A structured outline organises the deck: each content page names the outline points it covers,
    every point with a source is on a page, the pages follow the outline's order, each part opens with a
    divider, and each part's page count is compared with the outline's allotment."""
    shown, last, prev_part = set(), -1, None
    counts: dict[str, int] = {}
    pending_dividers = 0
    for p in pages:
        if p.get("layout") == "divider":
            pending_dividers += 1
            continue
        if p.get("layout") in NON_CONTENT:
            continue
        ids = p.get("point_ids") or []
        if not ids:
            err(f"{p.get('id')}：提纲带要点时，每个内容页需标注 point_ids（本页讲的是哪几条要点）")
            continue
        bad = [x for x in ids if x not in points]
        if bad:
            err(f"{p.get('id')}：point_ids 引用了不存在的提纲要点：{'、'.join(bad)}")
            continue
        gap = [x for x in ids if x in unsupported]
        if gap:
            err(f"{p.get('id')}：要点 {'、'.join(gap)} 在总结中标为无资料支撑，不能上页")
        shown.update(ids)
        idx = min(points[x][0] for x in ids)
        part = points[min(ids, key=lambda x: points[x][0])][2]
        if idx < last:
            err(f"{p.get('id')}：页面顺序与提纲不一致（本页属于第 {idx + 1} 个提纲条目，却排在第 {last + 1} 个之后）")
        last = max(last, idx)
        if part != prev_part:
            if prev_part is not None and not pending_dividers:
                result["warnings"].append(f"{p.get('id')}：进入“{part}”前没有章节页")
            counts[part] = counts.get(part, 0) + pending_dividers
            prev_part = part
        pending_dividers = 0
        counts[part] = counts.get(part, 0) + 1
    missing = [x for x in points if x not in shown and x not in unsupported]
    if missing:
        err("以下提纲要点既未上页，也未在总结中标为无资料支撑：" + "、".join(missing))
    for pt in parts:
        lo_hi, n = pt.get("pages"), counts.get(pt["title"], 0)
        if lo_hi and not lo_hi[0] - 1 <= n <= lo_hi[1] + 1:
            result["warnings"].append(f"“{pt['title']}”共 {n} 页，提纲建议 {lo_hi[0]}–{lo_hi[1]} 页")


RELATION_LAYOUTS = {"sequence": {"flow", "timeline"}, "branch": {"flow"}, "any_of": {"cards", "grid"}, "all_of": {"cards", "grid"},
                    "compare": {"compare", "table"}, "matrix": {"table"}, "evidence": {"hero", "cards", "chart"}}


def _message_checks(pages: list[dict], checked: list[dict], sections: list[dict], facts: dict, result: dict, err) -> None:
    """The summary's information structure carried onto the pages: each content page names its focus (a fact from
    its chapter's core point or one of its relations); a relation's units appear on a page whose layout fits the
    relation; a limiting point's own text is shown on a page. Points are outline points (point_coverage) or, for an
    outline without points, the chapter's key points; pages belong to a chapter through point_ids or section_ids."""
    msgs = {}
    for s in sections:
        if not s.get("message"):
            continue
        rows = s.get("point_coverage") if s.get("outline_id") else [{"point_id": k.get("id"), "unit_ids": k.get("unit_ids")}
                                                                     for k in s.get("key_points") or []]
        msgs[s["id"]] = (s["message"], {r["point_id"]: r.get("unit_ids") or [] for r in rows or [] if r.get("point_id")})
    if not msgs:
        return
    item_of = {pid: sid for sid, (_, cover) in msgs.items() for pid in cover}

    def chapters(p):
        return {item_of[x] for x in p.get("point_ids") or [] if x in item_of} | {x for x in p.get("section_ids") or [] if x in msgs}

    shown_units = []                                  # per page: the source units its facts quote
    for p, c in zip(pages, checked):
        shown_units.append({facts[x].get("unit") for x in c["facts"] + c["edge_facts"] if x in facts})
    for p, c, units in zip(pages, checked, shown_units):
        if p.get("layout") in NON_CONTENT or p.get("layout") == "closing":
            continue
        own = [msgs[x] for x in sorted(chapters(p))]
        if not own:
            continue
        focus = (p.get("focus") or {}).get("fact") if isinstance(p.get("focus"), dict) else None
        if not focus:
            err(f"{p.get('id')}：须标注本页焦点（focus）：本章核心要点或某条要点关系中的一条事实")
            continue
        if focus not in c["facts"]:
            err(f"{p.get('id')}：焦点 {focus} 须是本页显示的事实")
            continue
        allowed = set()
        for m, cover in own:
            core = next((k for k, v in m["roles"].items() if v == "core"), None)
            allowed |= set(cover.get(core) or []) | {u for r in m.get("relations") or [] for u in r["unit_ids"]}
        if facts[focus].get("unit") not in allowed:
            result["warnings"].append(f"{p.get('id')}：焦点 {focus} 既不属于该章的核心要点，也不属于要点关系")
    for sid, (m, cover) in msgs.items():
        for r in m.get("relations") or []:
            fit = RELATION_LAYOUTS.get(r["type"])
            where = [p for p, units in zip(pages, shown_units) if units & set(r["unit_ids"]) and sid in chapters(p)]
            if fit and where and not any(p.get("layout") in fit for p in where):
                result["warnings"].append(f"{sid} 的“{r['type']}”关系显示在 {'、'.join(p.get('id', '') for p in where)}，"
                                          f"版式宜用 {' / '.join(sorted(fit))}")
        for pid, role in m["roles"].items():
            if role != "limit":
                continue
            on = [p.get("id") for p, units in zip(pages, shown_units)
                  if (pid in (p.get("point_ids") or []) or sid in (p.get("section_ids") or [])) and units & set(cover.get(pid) or [])]
            if not on:
                err(f"限定要点 {pid} 的原文未出现在任何页面（须在该章页面上显示其原文事实）")


def check(deck: dict, facts: dict[str, dict], terms: list[str] | tuple[str, ...] = (),
          outline: list[dict] | None = None, sections: list[dict] | None = None,
          requirements: dict | None = None, parts: list[dict] | None = None,
          key_points: dict[str, str] | None = None) -> dict:
    """`key_points` (id -> point text) is given for a complete-notes summary (model_understanding.v4): every
    content page names the summary key points it teaches and every key point reaches a page; page count follows
    the content, so no target-page pressure is reported."""
    glossary_items = deck.get("glossary", deck.get("terms", []))
    glossary = [x["text"] for x in glossary_items]
    result = {"pages": [], "errors": 0, "pending": 0, "deck_errors": [], "warnings": []}

    def err(msg):
        result["deck_errors"].append(msg)
        result["errors"] += 1

    for term in glossary_items:
        f = facts.get(term.get("fact"))
        if not f or f["status"] != "ACCEPTED" or canon(term["text"]) not in canon(f["quote"]):
            err(f"术语“{term.get('text')}”需出现在已通过的事实 {term.get('fact')} 的引文中")
    deck, recipe_errors = recipes.expand_deck(deck, facts)      # recipe pages become composed blocks first
    pages = deck.get("pages") or []
    if not pages:
        err("没有页面")
    ids = [p.get("id") for p in pages]
    if len(set(ids)) != len(ids) or not all(isinstance(i, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,60}", i) for i in ids):
        err("页面编号为空、非法或重复")
    for page in pages:
        errors, pending, used = _structure(page) + ([recipe_errors[page.get("id")]] if page.get("id") in recipe_errors else []), [], []
        for path, kind, value in walk({k: v for k, v in page.items()}):
            if kind == "emph":
                errors += emph_errors(path, *value, facts)
                continue
            if kind == "bad":
                errors.append(f"{path} 需写成 {{\"fact\": 编号}} 或 {{\"text\": 作者文字}}")
            elif kind == "text":
                for p in lint_text(str(value), glossary, terms):
                    errors.append(f"{path} “{value}”：{p}")
            else:
                f = facts.get(value)
                slot = path.endswith(".figure")
                if not f:
                    errors.append(f"{path} 引用了不存在的事实 {value}")
                elif slot != bool(f.get("figure")):
                    errors.append(f"{path} 图位置只能放图事实，图事实只能放在图位置：{value}")
                elif f["status"] != "ACCEPTED":
                    errors.append(f"{path} 引用了被拒绝的事实 {value}：{'；'.join(f['problems'])}")
                else:
                    shown = [value] + (list(f.get("caption") or []) if slot else [])
                    used += shown
                    pending += [x for x in shown if facts[x]["needs_confirmation"]]
        shown_figs = sorted({x for x in used if facts[x].get("figure")})
        if len(shown_figs) > MAX_FIGURES_PER_PAGE:
            errors.append(f"一页至多放 {MAX_FIGURES_PER_PAGE} 张原件图，当前 {len(shown_figs)} 张（请拆页）")
        elif len(shown_figs) == 2 and not errors:
            result["warnings"].append(f"{page.get('id')}：两张原件图并排展示暗示可比，须经语义审查确认原文支持这一比较")
        edge_facts = []
        nodes = {n.get("id"): n for n in page.get("nodes") or [] if isinstance(n, dict)}
        edges = [e for e in page.get("edges") or [] if isinstance(e, list) and len(e) in (3, 4)]
        for e in edges:                                  # labels first: a label is shown text like any other
            lab = e[3] if len(e) == 4 and isinstance(e[3], dict) else None
            if not lab:
                continue
            if "text" in lab:
                errors += [f"箭头 {e[0]}→{e[1]} 的标签“{lab['text']}”：{p}" for p in lint_text(str(lab["text"]), glossary, terms)]
                shown_label = str(lab["text"])
            else:
                f = facts.get(lab.get("fact"))
                if not f or f.get("figure") or f["status"] != "ACCEPTED":
                    errors.append(f"箭头 {e[0]}→{e[1]} 的标签须为已通过的文字事实：{lab.get('fact')}")
                    continue
                used.append(lab["fact"])
                if f["needs_confirmation"]:
                    pending.append(lab["fact"])
                shown_label = f["display"] or f["quote"]
            if len(shown_label.strip()) > EDGE_LABEL_MAX:
                errors.append(f"箭头 {e[0]}→{e[1]} 的标签过长（至多 {EDGE_LABEL_MAX} 字）；较长的说明请放节点或侧栏")
        for e in edges:
            lab = e[3] if len(e) == 4 and isinstance(e[3], dict) else None
            sup = facts.get(e[2])
            if e[2] not in used:
                if arrow_backs(sup, *(nodes.get(x, {}).get("ref") for x in e[:2]), facts=facts):
                    edge_facts.append(e[2])
                    if sup["needs_confirmation"]:
                        pending.append(e[2])
                else:
                    errors.append(f"箭头 {e[0]}→{e[1]} 的支持事实 {e[2]} 未在本页引用，也不是连接这两个节点的原件箭头")
                    continue
            src_label = ((sup or {}).get("arrow") or {}).get("label")
            if src_label:                                # the original labels this arrow: the page must say the same
                lf = facts.get(lab.get("fact")) if lab and "fact" in lab else None
                if not lab:
                    result["warnings"].append(f"{page.get('id')}：箭头 {e[0]}→{e[1]} 在原件中带标签，页面未显示")
                elif not lf or lf.get("unit") != src_label:
                    errors.append(f"箭头 {e[0]}→{e[1]} 的标签须引用原件中这条箭头的标签（单元 {src_label}）")
        review = []
        if page.get("layout") == "composed" and not errors:
            blocks = {b["id"]: b for b in page["blocks"] if b.get("id")}
            try:
                compose.bar_values(page, facts)
            except ValueError as e:
                errors.append(str(e))
            for b in page["blocks"]:
                if b["kind"] == "bar" and b["value_of"] not in used:
                    errors.append(f"条形 {b['value_of']} 的数值须在本页显示（条形本身不显示文字）")
                if b["kind"] != "arrow":
                    continue
                sup = facts.get(b["backed_by"])
                ends = [facts.get(compose.first_fact(blocks[x]) or "") for x in (b["from"], b["to"])]
                if b["backed_by"] in used:
                    continue
                if arrow_backs(sup, *({"fact": compose.first_fact(blocks[x])} for x in (b["from"], b["to"])), facts=facts):
                    edge_facts.append(b["backed_by"])
                elif compose.chain_backs(sup, *ends):
                    edge_facts.append(b["backed_by"])
                    review.append(f"箭头 {b['from']}→{b['to']}：把原文一句拆成先后环节（{b['backed_by']}），请确认原文确有此顺序")
                else:
                    errors.append(f"箭头 {b['from']}→{b['to']} 的支持事实 {b['backed_by']} 既不是原件箭头，也不是依次包含两端文字的同一句原文")
                    continue
                if sup and sup["needs_confirmation"]:
                    pending.append(b["backed_by"])
        # what the semantic reviewer must look at on this page: emphasis inside a quote, text an excerpt leaves out
        for path, kind, value in walk({k: v for k, v in page.items()}):
            if kind == "emph":
                review.append(f"{path}：在引文“{(facts.get(value[0]) or {}).get('quote', '')[:40]}”中强调了 {'、'.join(value[1])}")
        for x in sorted(set(used)):
            f = facts.get(x) or {}
            only_scope = f.get("scope") and canon(f.get("dropped") or "") == canon("".join(f"{x}:" for x in f["scope"]))
            if f.get("display") and f.get("dropped") and not only_scope:        # a stated scope label is checked above
                review.append(f"{x}：节选删去了“{f['dropped'][:40]}”")
        # signals: visual observations the page may fix or justify in its design note
        signals = []
        shown = [(x, (facts[x].get("display") or facts[x].get("quote") or "").strip()) for x in used if x in facts and not facts[x].get("figure")]
        counts: dict[str, int] = {}
        for _, t in shown:
            counts[t] = counts.get(t, 0) + 1
        repeated = sorted(t for t, n in counts.items() if n > 1 and t)
        labels: dict[str, int] = {}
        for _, t in shown:
            m = re.match(r"\s*([^\s:：;；，,。0-9]{1,12})[：:]", t)
            if m:
                labels[m.group(1)] = labels.get(m.group(1), 0) + 1
        repeated += [f"{k}：（{n} 处）" for k, n in sorted(labels.items()) if n > 1]
        if repeated:
            signals.append({"signal": "repetition", "detail": "同一文字在本页重复出现：" + "、".join(repeated[:6])
                            + "；整组共有的标签或数值可只写一次（范围标签删去后须在本页写明）"})
        justified = {e.get("signal"): str(e.get("reason") or "").strip() for e in ((page.get("design") or {}).get("exceptions") or []) if isinstance(e, dict)}
        for s in signals:
            s["justified"] = justified.get(s["signal"])
            if not s["justified"]:
                result["warnings"].append(f"{page.get('id')}：{s['detail']}")
        if page.get("layout") == "chart" and not errors:
            try:
                cm = charts.model(page["chart"], facts)
                if len(cm["sources"]) > 1:
                    result["warnings"].append(f"{page.get('id')}：图表数值来自 {len(cm['sources'])} 份资料，并排展示暗示可比，须经语义审查确认")
            except charts.ChartError as e:
                errors.append(f"图表：{e}")
        hero = page.get("value") if page.get("layout") == "hero" else None
        if isinstance(hero, dict) and hero.get("fact") in facts:
            f = facts[hero["fact"]]
            if len(f["display"] or f["quote"]) > HERO_MAX_CHARS:
                errors.append(f"主数字页的 value 需不超过 {HERO_MAX_CHARS} 字（可用 display 节选），长句请用 statement 版式")
        for ref in page.get("band") or []:          # the one dark strip is for a conclusion, not an abbreviation list
            text = (facts.get(ref.get("fact")) or {}).get("display") or (facts.get(ref.get("fact")) or {}).get("quote") or ""
            if re.match(r"\s*[A-Za-z][\w₀-₉\-/]*\s*[：:]", text) and re.search(r"[；;]", text):
                result["warnings"].append(f"{page.get('id')}：强调条里是缩写注释，应放 footnote（页脚注释）")
        # a label cut off an excerpt ("中国：2017" shown as "2017") must be stated once elsewhere on the page
        page_text = {x: canon(facts[x].get("display") or facts[x].get("quote") or "") for x in set(used) if x in facts}
        for x in sorted(set(used)):
            for label in (facts.get(x) or {}).get("scope") or []:
                if not any(canon(label) in t for y, t in page_text.items() if y != x):
                    errors.append(f"{x} 的显示文字删去了范围标签“{label}”，本页须另有事实写明它（整组只写一次）")
        if page.get("layout") not in {"cover", "divider", "closing", "agenda"} and not used:
            errors.append("内容页至少要引用一条事实")
        result["pages"].append({"id": page.get("id"), "facts": sorted(set(used)), "edge_facts": sorted(set(edge_facts)),
                                "pending": sorted(set(pending)), "errors": errors, "review": review, "signals": signals,
                                "design": page.get("design") or {}})
        result["errors"] += len(errors)
        result["pending"] += len(set(pending))

    coverage = {"outline": [], "sections": [], "omissions": [], "points": []}
    points = {p["id"]: (i, o["id"], o.get("part", "")) for i, o in enumerate(outline or []) for p in o.get("points") or []}
    unsupported = {r["point_id"]: r["unsupported"] for s in sections or [] for r in s.get("point_coverage") or []
                   if r.get("unsupported") is not None}
    if points:
        _outline_order(pages, points, unsupported, parts or [], result, err)
        _message_checks(pages, result["pages"], sections or [], facts, result, err)
    if outline is not None:
        mapped = {o for p in pages for o in p.get("outline_ids") or []}
        known = {o["id"] for o in outline}
        for o in outline:
            own = {p["id"] for p in o.get("points") or []}
            where = [p["id"] for p in pages if o["id"] in (p.get("outline_ids") or []) or own & set(p.get("point_ids") or [])]
            coverage["outline"].append({"outline_id": o["id"], "text": o["text"], "pages": where})
            if not where and not (own and own <= set(unsupported)):     # an item whose every point lacks a source has no page
                err(f"教学提纲“{o['text']}”没有对应页面")
            for pt in o.get("points") or []:
                shown = [p["id"] for p in pages if pt["id"] in (p.get("point_ids") or [])]
                coverage["points"].append({"point_id": pt["id"], "text": pt["text"], "pages": shown, "unsupported": unsupported.get(pt["id"])})
        if mapped - known:
            err("页面引用了不存在的提纲条目：" + "、".join(sorted(mapped - known)))
    if sections is not None:
        omitted = {o.get("section_id"): o for o in deck.get("omissions") or []}
        known = {s["id"] for s in sections}
        for s in sections:
            where = [p["id"] for p in pages if s["id"] in (p.get("section_ids") or [])]
            coverage["sections"].append({"section_id": s["id"], "title": s["title"], "pages": where})
            if not where and not str(omitted.get(s["id"], {}).get("reason", "")).strip():
                err(f"总结章节“{s['title']}”未上页，也未在 omissions 中说明原因")
        for sid, o in omitted.items():
            if sid not in known:
                err(f"omissions 引用了不存在的章节：{sid}")
            else:
                coverage["omissions"].append({"section_id": sid, "reason": o.get("reason", "")})
    if key_points is not None:
        _key_point_coverage(pages, key_points, coverage, err)
    if requirements and requirements.get("target_pages") and key_points is None:
        target, n = int(requirements["target_pages"]), len(pages)
        if abs(n - target) > max(2, target * 0.3):
            result["warnings"].append(f"页数 {n} 与需求 {target} 相差较大")
    result["warnings"] += monotony_warnings(pages)
    result["coverage"] = coverage
    return result


def _key_point_coverage(pages: list[dict], key_points: dict[str, str], coverage: dict, err) -> None:
    """Complete-notes summaries are not compressed by selection: every key point is taught on at least one page
    (a dense point may span several); what the slide leaves out is carried by the speaker notes."""
    where = {k: [] for k in key_points}
    for p in pages:
        if p.get("layout") in NON_CONTENT or p.get("layout") == "closing":
            continue
        ids = p.get("key_point_ids")
        if not isinstance(ids, list) or not ids:
            err(f"{p.get('id')}：内容页需用 key_point_ids 标注本页讲的总结要点（<章节id>.k<序号>）")
            continue
        bad = [x for x in ids if x not in key_points]
        if bad:
            err(f"{p.get('id')}：key_point_ids 引用了不存在的总结要点：{'、'.join(map(str, bad))}")
        for x in ids:
            if x in where:
                where[x].append(p.get("id"))
    missing = [k for k, v in where.items() if not v]
    if missing:
        err("以下总结要点没有任何页面讲授（v4总结是完整笔记，要点不得删减；内容多就拆页）：" + "、".join(missing))
    coverage["key_points"] = [{"key_point_id": k, "pages": v} for k, v in where.items()]


def teaching_notes(pages: list[dict], key_points: dict[str, str]) -> dict[str, str]:
    """Speaker notes per page: the full confirmed summary text of the key points the page teaches, verbatim."""
    out = {}
    for p in pages:
        ids = [x for x in p.get("key_point_ids") or [] if x in key_points]
        if ids:
            out[p["id"]] = "\n\n".join(f"〔{x}〕{key_points[x]}" for x in ids)
    return out


PLAIN_LAYOUTS = {"bullets", "statement", "table"}
PLAIN_RUN = 4                # this many plain pages in a row is flagged
TEXT_LAYOUTS = {"bullets", "statement"}
TEXT_SHARE = 0.3             # so is a deck where more than this share of content pages are text only
SAME_RUN = 2                 # more than this many consecutive pages with one composition (recipe or layout) is flagged


def monotony_warnings(pages: list[dict]) -> list[str]:
    """Advisory only: long runs of lists, statements and tables usually mean structure was left unused,
    and a deck that is mostly text pages has no page that leads the eye."""
    content = [p for p in pages if p.get("layout") not in {"cover", "divider", "closing", "agenda"}]
    out, run = [], []
    for p in content + [{}]:
        if p.get("layout") in PLAIN_LAYOUTS:
            run.append(p.get("id"))
            continue
        if len(run) >= PLAIN_RUN:
            out.append(f"连续 {len(run)} 页只用列表、陈述或表格（{run[0]}–{run[-1]}）：流程、并列指标、对照、时间顺序等内容请改用 flow/cards/compare/timeline/grid 等版式")
        run = []
    # the same objects (first column) split over adjacent narrow tables belong in one table with more columns
    def first_col(p):
        rows = p.get("rows") or []
        return tuple(canon(str(c[0].get("fact") or c[0].get("text") or "")) for c in (r[0] for r in rows) if c and isinstance(c[0], dict))
    tables = [p for p in content if p.get("layout") == "table" and len(p.get("columns") or []) <= 3]
    for a, b in zip(content, content[1:]):
        if a in tables and b in tables and first_col(a) and set(first_col(a)) == set(first_col(b)):
            out.append(f"{a.get('id')} 与 {b.get('id')} 的首列是同一组对象：请合并为一张多列表（至多 7 列），不要按属性拆成多张两列表")
    # the same composition page after page reads as a template, whatever the content: vary it or say why
    def composition(p):
        return p.get("recipe") or p.get("layout")
    run = []
    for p in content + [{}]:
        if run and composition(p) == composition(run[-1]) and composition(p) != "composed":
            run.append(p)
            continue
        if len(run) > SAME_RUN and not all(any(e.get("signal") == "repetition" for e in ((q.get("design") or {}).get("exceptions") or [])
                                               if isinstance(e, dict)) for q in run[1:]):
            out.append(f"连续 {len(run)} 页使用同一种构图 {composition(run[0])}（{run[0].get('id')}–{run[-1].get('id')}）："
                       "内容形状不同的页面宜换一种构图；确属同类内容时请在 design.exceptions 中说明")
        run = [p]
    text = sum(p.get("layout") in TEXT_LAYOUTS for p in content)
    if len(content) >= 6 and text / len(content) > TEXT_SHARE:
        out.append(f"内容页中 {text}/{len(content)} 页为纯文字（列表或陈述），版式过于单一：每页应有一个结构化主体")
    return out


def main(project: Path) -> dict:
    deck = json.loads((project / "deck.json").read_text(encoding="utf-8"))
    fv = json.loads((project / "facts_verified.json").read_text(encoding="utf-8"))
    facts = {f["id"]: f for f in fv["facts"]}
    res = check(deck, facts, fv.get("terms", []))
    (project / "deck_check.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


if __name__ == "__main__":
    import sys
    r = main(Path(sys.argv[1]))
    for p in r["pages"]:
        print(f"{p['id']:10s} 事实{len(p['facts']):3d}  待确认{len(p['pending']):3d}  错误{len(p['errors'])}")
        for e in p["errors"]:
            print("    ✗", e)
    print("总错误", r["errors"])
