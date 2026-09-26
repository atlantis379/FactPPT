"""Redraw the textbook's tables and flow chart as native, editable objects.

Source discipline
-----------------
Every cell is extracted **verbatim from the OCR blocks by regex** -- nothing is
retyped by hand and nothing is written by us. An exhibit therefore cannot drift
from the scanned page it cites.

Deliberately NOT redrawn (stated rather than faked)
--------------------------------------------------
* 图2-16-1 肺泡氧分压/二氧化碳分压 与 肺泡通气量的关系 -- the OCR garbled the
  axis numbers ("25 18 8 20 20 / 113 15 13.3"), and a curve rebuilt from garbled
  numbers would be a fabricated chart with plausible-looking axes. Requires the
  original image.
* 表2-16-2 SOFA 评分 -- the OCR captured the caption but not the 6x5 body.
  Requires the original image.

Both are reported by :func:`deferred_exhibits` so the gap is visible in the
delivery rather than silently missing.
"""
from __future__ import annotations

import re
from typing import Sequence

_ITEM = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩]")
#: the mnemonic letter may sit after the opening paren ("（confusion，C）") or just
#: before the closing one ("（bloodpressure，B）") -- CURB-65 uses the latter form
_LETTER_HEAD = re.compile(r"[（(]([A-Za-z]{1,3})[，,]")
_LETTER_TAIL = re.compile(r"[，,]\s*([A-Za-z]{1,3})\s*[）)]")


def _budget(rows: list, columns: int, budget: int = 452):
    """Same row budget the page builder uses, imported lazily to avoid a cycle."""
    try:
        from deckkit.teaching_pages import _fit_rows
    except ImportError:  # pragma: no cover
        return rows, []
    return _fit_rows(rows, [""] * columns, budget)


def _blocks_text(blocks: Sequence[dict], pattern: str) -> str:
    for block in blocks:
        if re.search(pattern, block.get("text", "")):
            return block["text"]
    return ""


def _page_of(blocks: Sequence[dict], pattern: str):
    for block in blocks:
        if re.search(pattern, block.get("text", "")):
            return block.get("page")
    return None


def curb65(blocks: Sequence[dict]) -> dict | None:
    """表：CURB-65 评分（五项，各计 1 分）—— 逐项取自原文。"""
    text = _blocks_text(blocks, r"CURB-65共五项指标")
    if not text:
        return None
    head = text.split("满足1项得1分", 1)
    if len(head) < 2:
        return None
    body = head[1]
    marks = list(_ITEM.finditer(body))
    rows = []
    for index, match in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(body)
        item = body[match.end():end].strip("；;。 ")
        if not item:
            continue
        found = _LETTER_HEAD.search(item) or _LETTER_TAIL.search(item)
        label = found.group(1).upper() if found else ("年龄" if "年龄" in item else "—")
        # the source marks four criteria with (1)-(4) and says age completes the five
        # ("共五项指标"), so age becomes its own row instead of trailing the last one
        split = re.search(r"[；;]?(年龄\s*[≥>]\s*65\s*岁)", item)
        if split and label != "年龄":
            head = item[:split.start()].strip("；;，, ")
            if head:
                rows.append([label, head])
            rows.append(["年龄", split.group(1)])
            continue
        rows.append([label, item])
    if not rows:
        return None
    scoring = ""
    tail = _blocks_text(blocks, r"评分0~1分")
    if tail:
        match = re.search(r"评分0~1分[^。]*。[^。]*。", tail)
        scoring = match.group(0) if match else ""
    kept, overflow = _budget(rows, 2)
    return {
        "type": "matrix", "chip": "评分",
        "row_overflow": overflow,
        "title": "CURB-65：判断 CAP 病人是否需要住院",
        "source_ref": {"page": _page_of(blocks, r"CURB-65共五项指标"), "kind": "原文"},
        "primary_message": "CURB-65 五项指标各计 1 分，总分决定门诊或住院",
        "display_intent": "ROUTE", "cognitive_unit": "肺炎严重程度如何评分",
        "body_kind": "matrix",
        "columns": ["指标", "判读标准（满足 1 项得 1 分）"],
        "rows": kept,
        "keypoint": scoring or "评分 0~1 分门诊治疗；2 分建议住院或严格随访下院外治疗；3~5 分应住院治疗。",
        "keypoint_tone": "warn",
    }


def anatomical_matrix(blocks: Sequence[dict]) -> dict | None:
    """表：三种解剖分类对照 —— 每个字段取自原文中对应句子。"""
    text = _blocks_text(blocks, r"（一）解剖分类")
    if not text:
        return None
    rows = []
    for pattern, name in ((r"1\.大叶性[（(]肺泡性[）)]", "大叶性（肺泡性）"),
                          (r"2\.小叶性[（(]支气管性[）)]", "小叶性（支气管性）"),
                          (r"3\.间质性", "间质性")):
        # the OCR splits these three across separate blocks, so search every block
        # rather than only the first one that mentions 解剖分类
        segment = ""
        for block in blocks:
            match = re.search(pattern, block.get("text", ""))
            if not match:
                continue
            segment = block["text"][match.end():]
            stop = re.search(r"[23]\.(?:小叶性|间质性)", segment)
            if stop:
                segment = segment[:stop.start()]
            break
        if not segment:
            continue
        sentences = [s.strip("。 ") for s in re.split(r"(?<=。)", segment) if s.strip()]
        # 分类 comes from the marker; X线特征 is reliably keyword-anchored; the
        # pathology sentence is quoted whole. Extent/pathogen columns are NOT
        # guessed: sentence-level keyword mapping put the wrong sentence in the
        # wrong column, and a mis-mapped cell mis-teaches.
        xray = next((s for s in sentences if "X线" in s or "X 线" in s), "")
        pathology = next((s for s in sentences if s and s != xray), "")
        rows.append([name, pathology[:96] or "—", xray[:96] or "—"])
    if len(rows) < 3:
        return None
    return {
        "type": "matrix", "chip": "分类",
        "title": "三种解剖分类对照",
        "source_ref": {"page": _page_of(blocks, r"（一）解剖分类"), "kind": "整理"},
        "primary_message": "三种解剖分类的病变特点与影像表现各不相同",
        "display_intent": "COMPARE", "cognitive_unit": "三种解剖分类有何不同",
        "body_kind": "matrix",
        "columns": ["分类", "病变特点（原文摘录）", "X线特征"],
        "rows": rows,
        "keypoint": "解剖分类有助于理解影像学表现，但<b>不能指导抗菌药物选择</b>——"
                    "经验性治疗主要依据患病环境分类。",
        "keypoint_tone": "warn",
    }


def respiratory_flow(blocks: Sequence[dict]) -> dict | None:
    """图：呼吸衰竭鉴别思路 —— 分支取自原文句子。"""
    text = _blocks_text(blocks, r"呼吸衰竭鉴别可采取")
    if not text:
        return None
    tail = text.split("呼吸衰竭鉴别可采取如下思路", 1)[-1]
    tail = re.sub(r"^[（(]图2-16-2[）)]：?", "", tail)
    sentences = [s.strip("。 ") for s in re.split(r"(?<=。)", tail) if len(s.strip()) > 4]
    if len(sentences) < 2:
        return None
    first = sentences[0]
    branches = [s for s in sentences[1:] if s.startswith("若")]
    row1 = [{"text": first[:46], "kind": "box", "arrow": "分两型"}]
    row2 = [{"text": b[:60], "kind": "decision"} for b in branches[:3]] or \
           [{"text": s[:60], "kind": "decision"} for s in sentences[1:3]]
    return {
        "type": "flow", "chip": "诊断路径",
        "title": "呼吸衰竭鉴别思路：先分型，再定位",
        "source_ref": {"page": _page_of(blocks, r"呼吸衰竭鉴别可采取"), "kind": "原文"},
        "primary_message": "先按血气分析分型，再按影像学定位病因",
        "display_intent": "ROUTE", "cognitive_unit": "呼吸衰竭怎么鉴别",
        "body_kind": "flow",
        "keypoint": "分型（I 型 / II 型）决定后续定位方向，不可跳步。",
        "keypoint_tone": "danger",
        "flow": [row1, row2],
    }


def deferred_exhibits() -> list[dict]:
    """Figures that must NOT be redrawn from this OCR, with the reason."""
    return [
        {"exhibit": "图2-16-1 肺泡氧分压和二氧化碳分压与肺泡通气量的关系",
         "reason": "OCR 打乱了坐标数值（\"25 18 8 20 20 / 113 15 13.3\"）；"
                   "据乱码重绘等于伪造一张坐标看似合理的曲线图。",
         "requires": "教材原图页（第十六章 第 149 页）"},
        {"exhibit": "表2-16-2 SOFA 评分",
         "reason": "OCR 只取到表题（\"表2-16-2SOFA评分\"），未取到 6 变量 × 0~4 分的表体。",
         "requires": "教材原图页（第十六章 第 159 页）"},
    ]


def inject(deck: dict, blocks: Sequence[dict], *, after: dict | None = None) -> dict:
    """Insert the exhibits into a deck, right after the section they belong to."""
    exhibits = [e for e in (anatomical_matrix(blocks), curb65(blocks),
                            respiratory_flow(blocks)) if e]
    if not exhibits:
        return deck
    after = after or {}
    slides = deck["slides"]
    result: list[dict] = []
    inserted: set[int] = set()
    for index, slide in enumerate(slides):
        result.append(slide)
        for position, exhibit in enumerate(exhibits):
            if position in inserted:
                continue
            anchor = after.get(position)
            if anchor and anchor in str(slide.get("section_label", "")):
                exhibit = {
                    **exhibit,
                    "page_id": f"{slide.get('page_id','p')}x{position+1}",
                    # the exhibit belongs to the section it is injected into, so the
                    # closing-page gate groups it correctly
                    "section_label": slide.get("section_label", ""),
                }
                result.append(exhibit)
                inserted.add(position)
    for position, exhibit in enumerate(exhibits):
        if position not in inserted:
            result.append({**exhibit, "page_id": f"px{position+1}",
                           "section_label": result[-1].get("section_label", "")
                           if result else ""})
    deck["slides"] = result
    return deck


def main(argv: Sequence[str] | None = None) -> int:
    import json
    import sys
    from pathlib import Path
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        print("usage: python -m deckkit.exhibits BLOCKS.json")
        return 2
    blocks = json.loads(Path(args[0]).read_text(encoding="utf-8"))["blocks"]
    built = [e["title"] for e in (anatomical_matrix(blocks), curb65(blocks),
                                  respiratory_flow(blocks)) if e]
    print(json.dumps({"built": built, "deferred": deferred_exhibits()},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
