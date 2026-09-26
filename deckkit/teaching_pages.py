"""Build teaching pages that satisfy the page contract.

The previous builder mapped source paragraphs to slides, which the project's own
``NARRATIVE_TO_PAGE_DECOMPOSITION_AUDIT_POLICY`` calls an invalid decomposition
rationale (§4.10). This module implements the decomposition the policy asks for:

    outline node  ->  COGNITIVE UNIT  ->  carrier  ->  page

Rules applied (all extractive -- nothing is invented):

* **one cognitive unit per page** (§4.1). A textbook topic marker (【流行病学】,
  【分类】…) or a numbered sub-section is a unit; its paragraphs are the evidence.
* **one primary message per page** (§4.2), taken from the unit's own topic
  sentence rather than written by us.
* **carrier chosen by content shape** (§4.13 display intent before visual
  strategy): numbers -> kpi, parallel enumeration -> matrix, ordering -> flow,
  identification/differential -> quickref, otherwise bounded bullets.
* **every section closes** (§4.12) with a section summary page built from the
  units already presented on it.
* **density** (§4.5): a bullet carrier may not carry more than four items of 160
  characters, so a unit too long for one page is split.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

from deckkit import exhibits as EX
from deckkit import outline as OL

try:
    from deckkit.extract import _clean, numbers_in, sentences
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from deckkit.extract import _clean, numbers_in, sentences

MAX_BULLETS = 4
#: rows a matrix page can hold at 1280x720 before density review
MAX_MATRIX_ROWS = 14
#: pixel budget for a matrix body (1280x720 canvas, header 150px, keypoint+footer ~110px)
MATRIX_PX_BUDGET = 452
#: usable width per cell, used to estimate how many lines a cell wraps to
MATRIX_BODY_PX = 1180


MAX_BULLET_CHARS = 160
MAX_PRIMARY_CHARS = 46

#: sentence shapes that carry a caution worth surfacing as the page keypoint
_KEYPOINT_HINTS = ("注意", "但", "不能", "必须", "关键", "重要", "因此", "故", "应",
                   "禁忌", "警惕", "首选")
_KEYPOINT_TONES = {
    "danger": ("禁忌", "不能", "严禁", "致死", "危险"),
    "warn": ("注意", "警惕", "但", "然而"),
    "ok": ("首选", "推荐", "有效"),
}

_ENUM = re.compile(
    r"[①②③④⑤⑥⑦⑧⑨⑩]"
    r"|[（(][一二三四五六七八九十]{1,2}[）)]"
    r"|(?<![\d.])\d{1,2}[.、](?=[\u4e00-\u9fff])"   # mid-string, CJK follows
)
_ORDER = re.compile(r"首先|然后|随后|接着|第一步|第二步|程序|流程|步骤|路径|→")
_DIFF = re.compile(r"鉴别|区别|不同|对照|对比|区别于|vs|VS|相较")
_NUMBERISH = re.compile(r"\d")


def _fit_rows(rows: list, columns: list, budget: int = MATRIX_PX_BUDGET):
    """Keep the rows that fit the vertical budget; return (kept, overflow).

    Row height is estimated from how many lines the widest cell wraps to, because
    a flat row cap still overflowed: two rows of long prose are taller than six
    rows of short labels.
    """
    # per-column width: the first column is pinned to 16%, the rest share the rest
    count = max(1, len(columns))
    widths = [MATRIX_BODY_PX * 0.16] + [MATRIX_BODY_PX * 0.84 / max(1, count - 1)] * (count - 1)
    per_line = [max(4, int(width / 7.4)) for width in widths]
    used = 40                      # header row
    kept: list = []
    overflow: list = []
    for row in rows:
        lines = 1
        for index, cell in enumerate(row):
            limit = per_line[min(index, len(per_line) - 1)]
            lines = max(lines, (len(str(cell)) + limit - 1) // limit)
        height = lines * 19 + 24
        if not overflow and used + height <= budget:
            kept.append(row)
            used += height
        else:
            overflow.append(row)
    return kept, overflow


def _sentences(text: str) -> list[str]:
    return [s for s in (sentences(text) or []) if s.strip()]


def _distilled_title(unit: dict, path: Sequence[str], items: int | None = None) -> str:
    """Compose a page title from the unit's own markers.

    A title must state the page's subject, not repeat its first sentence
    (GATE-PAGE-004). Qualifiers such as "三条" are DERIVED from counting the
    unit's own items -- they are not medical content we supplied.
    """
    title = unit.get("title", "").strip()
    kind = unit.get("kind")
    if kind == "topic":
        parent = path[-1] if path else ""
        head = f"{parent} · {title}" if parent and parent not in title else title
    else:
        head = f"{unit.get('marker','')} {title}".strip()
    if items and items >= 3 and not _NUMBERISH.search(head):
        head = f"{head}（{items} 项）"
    return head


def _primary_message(text: str) -> str:
    """The unit's own topic sentence, trimmed. Extractive, never authored."""
    for sentence in _sentences(text):
        cleaned = _clean(sentence)
        if len(cleaned) >= 8:
            return cleaned[:MAX_PRIMARY_CHARS]
    return _clean(text)[:MAX_PRIMARY_CHARS]


def _keypoint(text: str) -> tuple[str, str]:
    """The unit's own caution sentence, with a tone inferred from its wording."""
    best = ""
    for sentence in _sentences(text):
        cleaned = _clean(sentence)
        if len(cleaned) < 10 or len(cleaned) > 120:
            continue
        if any(hint in cleaned for hint in _KEYPOINT_HINTS):
            if not best or len(cleaned) < len(best):
                best = cleaned
    if not best:
        return "", "info"
    tone = "info"
    for candidate, words in _KEYPOINT_TONES.items():
        if any(word in best for word in words):
            tone = candidate
            break
    return best, tone


def _split_items(text: str) -> list[tuple[str, str]]:
    """Split an enumerable unit into (marker, body) items, in document order."""
    marks = list(_ENUM.finditer(text))
    if len(marks) < 3:
        return []
    items = []
    for index, match in enumerate(marks):
        start = match.end()
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        body = _clean(text[start:end])
        if body:
            items.append((match.group(0).strip(), body[:200]))
    return items


def choose_carrier(unit: dict) -> dict:
    """Pick the carrier from the unit's content shape. Returns a page fragment."""
    text = " ".join(unit.get("paragraphs", []))
    title_hint = unit.get("title", "")
    numbers = numbers_in(text)
    items = _split_items(text)

    # numbers first: a unit full of magnitudes reads better as a KPI row
    if len(numbers) >= 3 and len(text) <= 400:
        kpis = []
        for number in numbers[:4]:
            label = _clean(number.get("context", ""))[:46] or number.get("metric", "")
            kpis.append({"value": str(number.get("value", "")),
                         "unit": str(number.get("unit", "") or ""),
                         "tag": "", "label": label})
        return {"type": "kpi", "body_kind": "kpi", "kpis": kpis, "items_count": len(kpis)}

    if _DIFF.search(title_hint) or _DIFF.search(text[:120]):
        if len(items) >= 2:
            rows = [[marker, body] for marker, body in items]
            kept, overflow = _fit_rows(rows, ["项目", "要点"])
            return {"type": "matrix", "body_kind": "matrix",
                    "columns": ["项目", "要点"], "rows": kept,
                    "row_overflow": overflow, "items_count": len(items)}

    if _ORDER.search(title_hint):
        rows = [[{"text": _clean(s)[:60], "kind": "box"} for s in _sentences(text)[:4]]]
        if rows[0]:
            return {"type": "flow", "body_kind": "flow", "flow": rows,
                    "items_count": len(rows[0])}

    if len(items) >= 3:
        rows = [[marker, body] for marker, body in items]
        kept, overflow = _fit_rows(rows, ["条目", "内容"])
        return {"type": "matrix", "body_kind": "matrix",
                "columns": ["条目", "内容"], "rows": kept,
                "row_overflow": overflow, "items_count": len(items)}

    bullets = [_clean(s)[:MAX_BULLET_CHARS] for s in _sentences(text) if len(_clean(s)) >= 8]
    if not bullets:
        bullets = [_clean(text)[:MAX_BULLET_CHARS]]
    return {"type": "cards", "body_kind": "bullets",
            "cards": [{"title": "", "body": b, "tone": ""} for b in bullets[:MAX_BULLETS]],
            "overflow": bullets[MAX_BULLETS:], "items_count": len(bullets)}


def _intent(unit: dict, carrier: str) -> str:
    title = unit.get("title", "") + unit.get("marker", "")
    if any(word in title for word in ("分类", "类型", "分型")):
        return "CLASSIFY"
    if any(word in title for word in ("鉴别", "区别", "对照", "比较")):
        return "COMPARE"
    if any(word in title for word in ("诊断", "程序", "流程", "路径", "步骤")):
        return "ROUTE"
    if any(word in title for word in ("治疗", "预防", "管理")):
        return "CONNECT_DIAGNOSIS_TO_ACTION"
    if any(word in title for word in ("流行病学", "负担", "数据", "发病率", "病死率")):
        return "SHOW_EVIDENCE"
    if carrier == "kpi":
        return "SHOW_EVIDENCE"
    if carrier == "flow":
        return "ROUTE"
    if carrier == "matrix":
        return "CLASSIFY"
    return "EXPLAIN"


def build_chapter(chapter: dict, parsed: dict, meta: dict) -> dict:
    """Assemble a contract-compliant teaching deck for one chapter."""
    title = f"{chapter['syllabus_no']} {chapter['title']}"
    slides: list[dict] = []
    counter = {"n": 0}
    emitted: set[str] = set()
    seen_sections: set[str] = set()

    def already(text: str) -> bool:
        key = "".join(str(text).split())[:120]
        if not key:
            return False
        if key in emitted:
            return True
        emitted.add(key)
        return False

    def next_id(prefix: str) -> str:
        counter["n"] += 1
        return f"{prefix}{counter['n']:03d}"

    slides.append({
        "type": "cover", "page_id": next_id("p"), "kicker": "教学课件", "title": title,
        "subtitle": "按认知单元组织 · 每页一个判断",
        "body": chapter.get("no_mismatch_note", "") if chapter.get("no_mismatch") else "",
        "motif": "layers",
        "meta_lines": [meta.get("author", ""), meta.get("org", "")],
    })

    # 导读：学习目标 + 教学内容 + 章节目录，均来自教学大纲
    goals = chapter.get("goals", {})
    if goals.get("knowledge"):
        slides.append({
            "type": "cards", "page_id": next_id("p"), "section_label": "学习目标",
            "title": "本章学习目标 · 知识目标",
            "source_ref": {"page": (chapter.get("syllabus_pages") or [""])[0], "kind": "大纲"},
            "primary_message": f"本章要求掌握 {len(goals['knowledge'])} 项知识目标",
            "display_intent": "ORIENT", "cognitive_unit": "本章要学什么",
            "body_kind": "bullets",
            "cards": [{"title": f"{i+1}", "body": g[:MAX_BULLET_CHARS], "tone": ""}
                      for i, g in enumerate(goals["knowledge"][:MAX_BULLETS])],
        })
    sections = [n for n in parsed["nodes"] if n["kind"] == "section"]
    if sections:
        slides.append({
            "type": "quickref", "page_id": next_id("p"), "section_label": "章节目录",
            "title": "本章结构与教学顺序", "cols": 2,
            "source_ref": {"page": sections[0]["page"], "kind": "整理"},
            "primary_message": f"本章共 {len(sections)} 节，按教材顺序展开",
            "display_intent": "ORIENT", "cognitive_unit": "本章由哪几节构成",
            "body_kind": "quickref",
            "items": [{"title": f"{n['marker']} {n['title']}",
                       "body": (n["paragraphs"][0][:90] if n["paragraphs"] else "")}
                      for n in sections],
        })

    # 逐节：认知单元 → 载体 → 页面，节末补对照/小结页
    path: list[str] = []
    section_units: list[dict] = []

    def close_section(label: str, units: list[dict]) -> None:
        # A one-unit section IS its own summary; a substantial section needs one.
        if len(units) < 3:
            return
        columns = ["要点", "核心内容"]
        # units store source paragraphs, not a precomputed message: deriving it here
        # is what stopped the content column coming out empty on every row
        rows = [[u.get("title", "")[:24],
                 _primary_message(" ".join(u.get("paragraphs", [])))[:70]]
                for u in units]
        # the summary must obey the same row budget as any other matrix: a section
        # with ten units previously produced a ten-row table and ran off the canvas
        kept, overflow = _fit_rows(rows, columns)
        first = next_id("p")
        slides.append({
            "type": "matrix", "page_id": first, "section_label": label, "chip": "小结",
            "title": f"{label} · 小结",
            "source_ref": {"page": units[0].get("page"), "kind": "整理"},
            "primary_message": f"{label}：{units[0].get('title','')[:20]} 等 "
                               f"{len(units)} 个要点回顾",
            "display_intent": "SUMMARIZE", "cognitive_unit": f"{label} 讲了什么",
            "body_kind": "matrix",
            "keypoint": "以上要点均取自教材原文；具体表述与适用条件以教材为准。",
            "keypoint_tone": "info",
            "columns": columns, "rows": kept,
        })
        index = 2
        while overflow:
            kept, overflow = _fit_rows(overflow, columns)
            slides.append({
                "type": "matrix", "page_id": f"{first}s{index}",
                "section_label": label, "chip": "小结",
                "title": f"{label} · 小结（续 {index}）",
                "source_ref": {"page": units[0].get("page"), "kind": "整理"},
                "primary_message": f"{label}：{units[0].get('title','')[:20]} 等 "
                                   f"{len(units)} 个要点回顾",
                "display_intent": "SUMMARIZE",
                "cognitive_unit": f"{label} 讲了什么",
                "body_kind": "matrix", "continues": first,
                "keypoint": "", "keypoint_tone": "info",
                "columns": columns, "rows": kept,
            })
            index += 1

    for node in parsed["nodes"]:
        kind = node["kind"]
        if kind == "chapter":
            continue
        if kind == "section":
            label = f"{node['marker']} {node['title']}"
            if label in seen_sections:
                # the scan split one section across pages; it is still ONE section,
                # so keep accumulating instead of opening a duplicate group
                path = [label]
                continue
            seen_sections.add(label)
            if section_units:
                close_section(path[0] if path else "本节", section_units)
                section_units = []
            path = [label]
            slides.append({
                "type": "statement", "page_id": next_id("p"),
                # the divider belongs to the section it opens, so the closing gate can
                # group it correctly; the chip is what marks it as a divider
                "section_label": f"{node['marker']} {node['title']}",
                "chip": "节引导",
                "title": f"{node['marker']} {node['title']}",
                "source_ref": {"page": node["page"], "kind": "原文"},
                # the divider's message is the section NAME, not its first paragraph:
                # reusing the paragraph made the divider a duplicate of the first unit
                "primary_message": f"{node['marker']} {node['title']}",
                "display_intent": "ORIENT",
                "cognitive_unit": f"{node['marker']} 的主要内容",
                "body_kind": "statement",
                "keypoint": "", "keypoint_tone": "info",
                "kicker": f"教材第 {node['page']} 页起",
                "body": (node["paragraphs"][0][:160] if node["paragraphs"] else ""),
            })
            if node["paragraphs"]:
                unit = {"kind": kind, "title": node["title"], "marker": node["marker"],
                        "paragraphs": node["paragraphs"], "page": node["page"]}
                section_units.append(unit)
                slides.append(_page_for(unit, path, next_id("p")))
            continue

        if kind in ("cn", "paren"):
            # deliberately do NOT close here: the section must accumulate every unit
            # so its closing page summarises the whole section, not the last sub-part
            path = (path[:1] if path else []) + [f"{node['marker']} {node['title']}"]
            if already(" ".join(node["paragraphs"])):
                continue
            unit = {"kind": kind, "title": node["title"], "marker": node["marker"],
                    "paragraphs": node["paragraphs"], "page": node["page"]}
            section_units.append(unit)
            slides.append(_page_for(unit, path, next_id("p")))
            continue

        if kind == "topic" and node["paragraphs"]:
            if already(" ".join(node["paragraphs"])):
                continue
            unit = {"kind": kind, "title": node["title"], "marker": f"【{node['title']}】",
                    "paragraphs": node["paragraphs"], "page": node["page"]}
            section_units.append(unit)
            slides.append(_page_for(unit, path, next_id("p")))

    if section_units:
        close_section(path[0] if path else "本节", section_units)

    homework = list(chapter.get("homework", []))
    if homework:
        slides.append({
            "type": "cards", "page_id": next_id("p"), "section_label": "课后作业",
            "title": "课后作业",
            "source_ref": {"page": (chapter.get("syllabus_pages") or [-1])[-1], "kind": "大纲"},
            "primary_message": f"{len(homework)} 道课后作业，覆盖本章全部目标",
            "display_intent": "SUMMARIZE", "cognitive_unit": "本章需要掌握到什么程度",
            "body_kind": "bullets",
            "cards": [{"title": f"{i+1}", "body": h[:MAX_BULLET_CHARS], "tone": ""}
                      for i, h in enumerate(homework[:MAX_BULLETS])],
        })

    slides.append({
        "type": "closing", "page_id": next_id("p"), "title": "本章小结", "subtitle": "",
        "body": "本课件按认知单元组织：每页一个判断，学习目标与作业来自教学大纲，"
                "正文取自教材扫描页 OCR，每页标注教材页码，低置信段落需人工核对。",
        "motif": "check", "meta_lines": [meta.get("footer_right", "")],
    })
    return {"meta": {**meta, "title": title}, "theme": meta.get("theme", "clinical"),
            "slides": slides}


def _page_for(unit: dict, path: Sequence[str], page_id: str) -> dict:
    """One cognitive unit -> one page (split only when the bullet limit is exceeded)."""
    carrier = choose_carrier(unit)
    text = " ".join(unit.get("paragraphs", []))
    title = _distilled_title(unit, path, carrier.get("items_count"))
    keypoint, tone = _keypoint(text)
    page = {
        "type": carrier["type"], "page_id": page_id,
        "section_label": path[0] if path else "",
        "chip": unit.get("title", "") or unit.get("marker", ""),
        "title": title,
        "source_ref": {"page": unit.get("page"), "kind": "原文"},
        "primary_message": _primary_message(text),
        "display_intent": _intent(unit, carrier["body_kind"]),
        "cognitive_unit": unit.get("title", "") or unit.get("marker", ""),
        "body_kind": carrier["body_kind"],
    }
    # a keypoint that repeats a card wastes the emphasis slot
    card_bodies = {str(c.get("body", "")).strip() for c in (carrier.get("cards") or [])}
    if keypoint and keypoint.strip() in card_bodies:
        for sentence in _sentences(text):
            cleaned = _clean(sentence)
            if cleaned and cleaned not in card_bodies and any(
                    hint in cleaned for hint in _KEYPOINT_HINTS):
                keypoint, tone = cleaned[:120], tone
                break
        else:
            keypoint = ""
    page["keypoint"] = keypoint
    page["keypoint_tone"] = tone
    for key in ("kpis", "columns", "rows", "flow", "items"):
        if key in carrier:
            page[key] = carrier[key]
    if carrier.get("row_overflow"):
        page["_row_overflow"] = carrier["row_overflow"]
    if "cards" in carrier:
        page["cards"] = carrier["cards"]
        overflow = carrier.get("overflow") or []
        if overflow:
            page["_overflow"] = overflow
    return page


def expand_overflow(deck: dict) -> dict:
    """Give overflow bullets their own continuation pages (density, §4.5)."""
    slides: list[dict] = []
    for slide in deck["slides"]:
        row_overflow = slide.pop("_row_overflow", None)
        row_overflow = row_overflow or []
        overflow = slide.pop("_overflow", None)
        slides.append(slide)
        row_index = 2
        while row_overflow:
            kept, row_overflow = _fit_rows(row_overflow, slide.get("columns") or [],
                                           MATRIX_PX_BUDGET)
            slides.append({
                **{k: v for k, v in slide.items()
                   if k not in ("rows", "keypoint", "chip")},
                "page_id": f"{slide['page_id']}r{row_index}",
                "title": f"{slide['title']}（续 {row_index}）",
                "continues": slide["page_id"],
                "chip": slide.get("chip", ""), "rows": kept,
                "keypoint": "", "keypoint_tone": "info",
            })
            row_index += 1
        index = 2
        while overflow:
            chunk, overflow = overflow[:MAX_BULLETS], overflow[MAX_BULLETS:]
            slides.append({
                **{k: v for k, v in slide.items()
                   if k not in ("cards", "keypoint", "section_label")},
                "page_id": f"{slide['page_id']}c{index}",
                "title": f"{slide['title']}（续 {index}）",
                "section_label": slide["section_label"],
                # explicitly the SAME cognitive unit, continued
                "continues": slide["page_id"],
                "keypoint": "", "keypoint_tone": "info",
                "cards": [{"title": "", "body": b, "tone": ""} for b in chunk],
            })
            index += 1
    deck["slides"] = slides
    return deck


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 3:
        print(__doc__)
        print("usage: teaching_pages.py SYLLABUS.json CHAPTER_KEY BLOCKS.json -o OUT.json "
              "[--theme clinical] [--author ..] [--org ..]")
        return 2
    syllabus = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    key, blocks_path = args[1], args[2]
    out = args[args.index("-o") + 1] if "-o" in args else "deck.json"
    theme = args[args.index("--theme") + 1] if "--theme" in args else "clinical"
    author = args[args.index("--author") + 1] if "--author" in args else ""
    org = args[args.index("--org") + 1] if "--org" in args else ""

    chapter = next((c for c in syllabus["chapters"] if c["syllabus_no"] == key), None)
    if chapter is None:
        print(f"chapter {key!r} not found")
        return 1
    blocks = json.loads(Path(blocks_path).read_text(encoding="utf-8"))["blocks"]
    parsed = OL.parse(blocks)
    meta = {
        "brand": f"{key} {chapter['title']}", "tagline": "教学课件", "theme": theme,
        "author": author, "org": org, "source": chapter.get("source_pdf", ""),
        "source_label": "来源", "footer_right": f"{key} {chapter['title']}",
        "title": f"{key} {chapter['title']}",
    }
    deck = expand_overflow(build_chapter(chapter, parsed, meta))
    # stage 4: redraw the textbook's tables/flow as native objects, anchored to the
    # section they belong to
    deck = EX.inject(deck, blocks, after={0: "第一节", 1: "第一节", 2: "第二节"})
    deck.setdefault("meta", {})["deferred_exhibits"] = EX.deferred_exhibits()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")
    kinds: dict[str, int] = {}
    for slide in deck["slides"]:
        kinds[slide["type"]] = kinds.get(slide["type"], 0) + 1
    print(json.dumps({"out": out, "title": deck["meta"]["title"],
                      "slides": len(deck["slides"]), "archetypes": kinds,
                      "outline_nodes": len(parsed["nodes"])},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
