"""Deck specification checks.

Pages reference facts by id. Text written by the model (titles, leads, labels,
column headers) is allowed only if it carries no substantive content of its own
(see lexicon.lint_text); glossary terms backed by a fact are exempt. Every arrow
in a diagram must name the fact that supports it. The deck must cover every
outline item, and every summary section must be shown on a page or listed as an
omission with a reason the customer can see. A source figure is shown only in a
`figure` slot and only as a figure fact; its caption facts are shown with it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .lexicon import lint_text, canon

LAYOUTS = {
    # layout: (required keys, limits)
    "cover": ({"title"}, {}),
    "divider": ({"title"}, {}),
    "bullets": ({"title", "items"}, {"items": (1, 8)}),
    "table": ({"title", "columns", "rows"}, {"columns": (2, 7), "rows": (1, 9)}),
    "cards": ({"title", "cards"}, {"cards": (2, 4), "notes": (0, 4)}),
    "compare": ({"title", "panels"}, {"panels": (2, 3), "band": (0, 2)}),
    "flow": ({"title", "nodes", "edges"}, {"nodes": (2, 16), "side": (0, 4)}),
    "statement": ({"title", "statement"}, {"support": (0, 3)}),
    "closing": ({"title"}, {"items": (0, 6)}),
    "figure": ({"title", "figure"}, {"side": (0, 3)}),
}
SKIP = {"id", "layout", "widths", "edges", "outline_ids", "section_ids", "col", "row", "emphasis", "kind"}


def walk(node, path=""):
    """Yield (path, kind, value) for every fact reference and authored text in a page."""
    if isinstance(node, dict):
        if "fact" in node and len(node) == 1:
            yield path, "fact", node["fact"]
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
            if not (isinstance(e, list) and len(e) == 3 and e[0] in ids and e[1] in ids):
                errors.append(f"箭头格式需为 [起点, 终点, 支持事实]：{e}")
    return errors


def check(deck: dict, facts: dict[str, dict], terms: list[str] | tuple[str, ...] = (),
          outline: list[dict] | None = None, sections: list[dict] | None = None,
          requirements: dict | None = None) -> dict:
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
    pages = deck.get("pages") or []
    if not pages:
        err("没有页面")
    ids = [p.get("id") for p in pages]
    if len(set(ids)) != len(ids) or not all(isinstance(i, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,60}", i) for i in ids):
        err("页面编号为空、非法或重复")
    for page in pages:
        errors, pending, used = _structure(page), [], []
        for path, kind, value in walk({k: v for k, v in page.items()}):
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
        for e in page.get("edges") or []:
            if isinstance(e, list) and len(e) == 3 and e[2] not in used:
                errors.append(f"箭头 {e[0]}→{e[1]} 的支持事实 {e[2]} 未在本页引用或未通过")
        if page.get("layout") not in {"cover", "divider", "closing"} and not used:
            errors.append("内容页至少要引用一条事实")
        result["pages"].append({"id": page.get("id"), "facts": sorted(set(used)), "pending": sorted(set(pending)), "errors": errors})
        result["errors"] += len(errors)
        result["pending"] += len(set(pending))

    coverage = {"outline": [], "sections": [], "omissions": []}
    if outline is not None:
        mapped = {o for p in pages for o in p.get("outline_ids") or []}
        known = {o["id"] for o in outline}
        for o in outline:
            where = [p["id"] for p in pages if o["id"] in (p.get("outline_ids") or [])]
            coverage["outline"].append({"outline_id": o["id"], "text": o["text"], "pages": where})
            if not where:
                err(f"教学提纲“{o['text']}”没有对应页面")
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
    if requirements and requirements.get("target_pages"):
        target, n = int(requirements["target_pages"]), len(pages)
        if abs(n - target) > max(2, target * 0.3):
            result["warnings"].append(f"页数 {n} 与需求 {target} 相差较大")
    result["coverage"] = coverage
    return result


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
