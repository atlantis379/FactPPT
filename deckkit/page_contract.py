"""Page-level contract for teaching decks, and the gates that enforce it.

The specification already existed in the project; nothing enforced it:

* ``docs/.../NARRATIVE_TO_PAGE_DECOMPOSITION_AUDIT_POLICY_v0.1.md``
  §4.1 one coherent cognitive unit per page
  §4.2 one primary message per page (two -> split, same twice -> merge)
  §4.5 density must fit the speaking time
  §4.10 source page/section boundaries are NOT valid page boundaries
* ``docs/.../NARRATIVE_RATIONALITY_AUDIT_POLICY_v0.1.md``
  §4.12 the ending must close the presentation question

This module turns those prose rules into a machine-checkable page contract.
A page that cannot state its cognitive unit, its single primary message and the
carrier it chose is not a page the specification would approve.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Sequence

#: every page must declare these (cover/closing are exempt from the teaching fields)
REQUIRED_FIELDS = ("section_label", "title", "source_ref", "primary_message",
                   "display_intent", "cognitive_unit", "body_kind")

DISPLAY_INTENTS = {
    "ORIENT",            # 导读 / 章节引导
    "CLASSIFY",          # 分类
    "COMPARE",           # 对照
    "ROUTE",             # 路径 / 流程
    "EXPLAIN",           # 机制解释
    "SHOW_EVIDENCE",     # 呈现证据 / 数据
    "CONNECT_DIAGNOSIS_TO_ACTION",
    "SUMMARIZE",         # 小节小结
    "SUMMARIZE_UNCERTAINTY",
}

#: the carrier a page uses. "text" is legal but bounded: past the limit the page
#: should move to a structured carrier rather than hold a wall of prose.
BODY_KINDS = {"cover", "closing", "statement", "bullets", "kpi", "table",
              "matrix", "flow", "quickref", "text"}

#: a pure prose block longer than this signals the wrong carrier was chosen
TEXT_CARRIER_LIMIT = 160
#: cards per page before density review (§4.5)
MAX_CARDS = 4
#: characters per card body before density review
MAX_CARD_CHARS = 160

GATES = {
    "GATE-PAGE-001": "page declares a single primary_message",
    "GATE-PAGE-002": "no two pages repeat the same primary_message",
    "GATE-PAGE-003": "prose carrier stays within the density limit",
    "GATE-PAGE-004": "title is distilled, not the body's first sentence",
    "GATE-PAGE-005": "every teaching section closes with a summary/comparison page",
}

TEACHING_TYPES = {"cards", "kpi", "table", "compare", "steps", "timeline",
                  "statement", "matrix", "flow", "quickref", "chart"}


def _text_of(slide: dict) -> str:
    parts: list[str] = [str(slide.get("title", "")), str(slide.get("subtitle", "")),
                        str(slide.get("body", "")), str(slide.get("keypoint", ""))]
    for card in slide.get("cards", []) or []:
        parts.append(str(card.get("title", "")))
        parts.append(str(card.get("body", "")))
    for key in ("kpis", "steps", "items", "images"):
        for item in slide.get(key, []) or []:
            parts.extend(str(v) for v in item.values() if isinstance(v, (str, int, float)))
    for row in slide.get("rows", []) or []:
        parts.extend(str(c) for c in row)
    return " ".join(p for p in parts if p)


def _prose_blocks(slide: dict) -> list[str]:
    blocks = []
    if slide.get("body"):
        blocks.append(str(slide["body"]))
    for card in slide.get("cards", []) or []:
        if card.get("body"):
            blocks.append(str(card["body"]))
    return blocks


def check_page(slide: dict, index: int) -> list[dict]:
    """Contract violations for one page."""
    issues: list[dict] = []
    kind = (slide.get("type") or "").lower()
    if kind in ("cover", "closing"):
        return issues
    page_id = slide.get("page_id") or f"#{index}"

    for field in REQUIRED_FIELDS:
        value = slide.get(field)
        if value in (None, "", [], {}):
            issues.append({"gate": "GATE-PAGE-001", "page": page_id, "field": field,
                           "message": f"page does not declare {field!r}"})

    intent = slide.get("display_intent")
    if intent and intent not in DISPLAY_INTENTS:
        issues.append({"gate": "GATE-PAGE-001", "page": page_id, "field": "display_intent",
                       "message": f"unknown display_intent {intent!r}"})
    carrier = slide.get("body_kind")
    if carrier and carrier not in BODY_KINDS:
        issues.append({"gate": "GATE-PAGE-001", "page": page_id, "field": "body_kind",
                       "message": f"unknown body_kind {carrier!r}"})

    # GATE-PAGE-003 -- prose carrier must stay within the density limit
    blocks = _prose_blocks(slide)
    if carrier in ("text", "bullets", None):
        for block in blocks:
            if len(block) > TEXT_CARRIER_LIMIT:
                issues.append({
                    "gate": "GATE-PAGE-003", "page": page_id, "field": "body",
                    "message": (f"prose block of {len(block)} chars exceeds "
                                f"{TEXT_CARRIER_LIMIT}; use kpi/table/matrix/flow or split "
                                f"the page"),
                })
                break
    if len(slide.get("cards", []) or []) > MAX_CARDS:
        issues.append({"gate": "GATE-PAGE-003", "page": page_id, "field": "cards",
                       "message": f"{len(slide['cards'])} cards exceeds {MAX_CARDS}"})

    # GATE-PAGE-004 -- title must be distilled, not the body's opening
    title = str(slide.get("title", "")).strip()
    if title and blocks:
        head = "".join(blocks[0].split())[:len("".join(title.split()))]
        if head and head == "".join(title.split()):
            issues.append({"gate": "GATE-PAGE-004", "page": page_id, "field": "title",
                           "message": "title duplicates the body's first sentence; "
                                      "it must state the page's judgement"})
    return issues


def check(deck: dict) -> dict:
    """Run every page gate over a deck."""
    slides = deck.get("slides", [])
    issues: list[dict] = []
    for index, slide in enumerate(slides, start=1):
        slide.setdefault("page_id", f"p{index:03d}")
        issues.extend(check_page(slide, index))

    # GATE-PAGE-002 -- two pages repeating one primary message means merge, UNLESS
    # one declares that it continues the other: that is one cognitive unit split for
    # density (§4.5), which the policy allows.
    by_id = {s["page_id"]: s for s in slides}
    seen: dict[str, list[str]] = {}
    for slide in slides:
        message = str(slide.get("primary_message", "")).strip()
        if message:
            seen.setdefault("".join(message.split()), []).append(slide["page_id"])
    for _message, pages in seen.items():
        roots = []
        for page_id in pages:
            root, hops = page_id, 0
            while by_id.get(root, {}).get("continues"):
                root = by_id[root]["continues"]
                hops += 1
                if hops > 100:      # defensive: a cycle must not hang the gate
                    break
            roots.append(root)
        if len(set(roots)) > 1:
            issues.append({"gate": "GATE-PAGE-002", "pages": pages,
                           "message": f"{len(set(roots))} independent pages share one "
                                      f"primary message"})

    # GATE-PAGE-005 -- each section must close
    teaching = [s for s in slides if (s.get("type") or "").lower() in TEACHING_TYPES]
    sections: dict[str, list[dict]] = {}
    for slide in teaching:
        label = str(slide.get("section_label") or slide.get("chapter_section") or "").strip()
        if label:
            sections.setdefault(label, []).append(slide)
    for label, pages in sections.items():
        # a section too short to need a summary is not a violation
        if len(pages) < 3:
            continue
        if not any(str(p.get("display_intent", "")).startswith(("SUMMARIZE", "COMPARE"))
                   for p in pages):
            issues.append({"gate": "GATE-PAGE-005", "section": label,
                           "message": f"section {label!r} ({len(pages)} pages) has no "
                                      f"closing summary/comparison page"})

    blocked = [i for i in issues if i["gate"] in ("GATE-PAGE-001", "GATE-PAGE-004")]
    by_gate: dict[str, int] = {}
    for issue in issues:
        by_gate[issue["gate"]] = by_gate.get(issue["gate"], 0) + 1
    return {
        "deck": deck.get("meta", {}).get("title", ""),
        "pages": len(slides),
        "teaching_pages": len(teaching),
        "sections": len(sections),
        "issues": len(issues),
        "blocking": len(blocked),
        "by_gate": by_gate,
        "status": "PASS" if not issues else ("BLOCK" if blocked else "REVISIONS_REQUIRED"),
        "detail": issues[:40],
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        print("usage: python -m deckkit.page_contract DECK.json [--full]")
        return 2
    deck = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    result = check(deck)
    if "--full" not in args:
        result = {**result, "detail": result["detail"][:12]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
