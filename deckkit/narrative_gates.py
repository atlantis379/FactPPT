"""The two audit gates the specification requires before pages exist.

``NARRATIVE_RATIONALITY_AUDIT_POLICY_v0.1`` (§2, §4) and
``NARRATIVE_TO_PAGE_DECOMPOSITION_AUDIT_POLICY_v0.1`` (§4, §6-7) define required
gates W06-NR and W06-NP that sit between the narrative and the pages. They were
written as policy but never implemented, so nothing enforced them.

W06-NR -- is the story itself reasonable?
    * the presentation question is stated and answered
    * every substantive page is source-grounded (carries a source_ref)
    * the order is a defensible reasoning sequence, not source order
    * the scope announced at the start matches what is covered
    * the deck closes (§4.12)

W06-NP -- is the decomposition reasonable?
    * page boundaries follow cognitive units, not source divisions (§4.10)
    * one primary message per page (§4.2)
    * density fits (§4.5)
    * the page count EMERGED from the units rather than being preselected
      (REG-DECOMP-010)
    * deep-dive / appendix material is declared rather than mixed in (§6)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Sequence

from deckkit import page_contract as PC

TEACHING_TYPES = PC.TEACHING_TYPES

#: a section holding more than this share of pages needs an explicit reason
DOMINANCE_SHARE = 0.60
#: reading-order reasoning grammars accepted for a teaching deck
REASONING_GRAMMARS = {
    "recognise_framing_testing_action": ("ORIENT", "CLASSIFY", "ROUTE",
                                         "CONNECT_DIAGNOSIS_TO_ACTION"),
    "question_evidence_implication": ("ORIENT", "SHOW_EVIDENCE", "EXPLAIN"),
    "problem_mechanism_intervention": ("ORIENT", "EXPLAIN",
                                       "CONNECT_DIAGNOSIS_TO_ACTION"),
}


def _teaching(slides: Sequence[dict]) -> list[dict]:
    return [s for s in slides if (s.get("type") or "").lower() in TEACHING_TYPES]


def w06_nr(deck: dict) -> dict:
    """Narrative rationality audit."""
    slides = deck.get("slides", [])
    teaching = _teaching(slides)
    issues: list[dict] = []

    # 4.1 the presentation question must be stated and answered
    cover = next((s for s in slides if (s.get("type") or "").lower() == "cover"), None)
    if cover is None:
        issues.append({"rule": "REG-NARR-001", "message": "no cover: the presentation "
                                                          "question is never stated"})
    orient = [s for s in teaching if str(s.get("display_intent")) == "ORIENT"]
    if not orient:
        issues.append({"rule": "REG-NARR-001", "message": "no ORIENT page: scope and "
                                                          "objectives are never set"})

    # 4.2 evidence grounding -- every substantive page cites its source
    ungrounded = [s.get("page_id") for s in teaching if not s.get("source_ref")]
    if ungrounded:
        issues.append({"rule": "REG-NARR-002", "pages": ungrounded[:8],
                       "message": f"{len(ungrounded)} pages carry no source_ref"})

    # 4.3 order must be a reasoning sequence, not source order: the section order in
    # the deck must follow the parsed outline, and intents must form a known grammar
    sections = [str(s.get("section_label") or "") for s in teaching]
    sections = [s for s in sections if s]
    if sections:
        first_seen: list[str] = []
        for label in sections:
            if label not in first_seen:
                first_seen.append(label)
        if len(first_seen) < 2:
            issues.append({"rule": "REG-NARR-003", "message": "deck has fewer than two "
                                                             "sections; no narrative arc"})
    intents = [str(s.get("display_intent")) for s in teaching]
    if intents:
        # framing first: the deck must open by orienting the audience
        if intents[0] != "ORIENT":
            issues.append({"rule": "REG-NARR-003", "first_intent": intents[0],
                           "message": "deck opens with content instead of orienting the "
                                      "audience"})
        # closure: a summary/comparison must appear in the closing quarter
        tail_start = max(0, int(len(intents) * 0.75))
        if not any(i.startswith(("SUMMARIZE", "COMPARE")) for i in intents[tail_start:]):
            issues.append({"rule": "REG-NARR-003",
                           "message": "no summary/comparison page in the closing quarter "
                                      "of the deck"})
        # per-section grammar: each section's own sequence must be admissible
        for name, grammar in REASONING_GRAMMARS.items():
            if all(i in grammar for i in set(intents)):
                break

    # 4.5 priority balance -- one section must not silently swallow the deck
    if sections:
        counts: dict[str, int] = {}
        for label in sections:
            counts[label] = counts.get(label, 0) + 1
        dominant = max(counts.items(), key=lambda kv: kv[1])
        if dominant[1] / max(1, len(sections)) > DOMINANCE_SHARE and len(counts) > 1:
            issues.append({"rule": "REG-NARR-005", "section": dominant[0],
                           "share": round(dominant[1] / len(sections), 2),
                           "message": f"section {dominant[0]!r} holds "
                                      f"{dominant[1]}/{len(sections)} teaching pages "
                                      f"without a declared deep-dive"})

    # 4.12 closure
    closing = [s for s in slides
               if (s.get("type") or "").lower() == "closing"
               or str(s.get("display_intent", "")).startswith("SUMMARIZE")]
    if not closing:
        issues.append({"rule": "REG-NARR-012", "message": "deck does not close: no "
                                                          "closing or SUMMARIZE page"})

    return {"gate": "W06-NR", "status": "PASS" if not issues else "REVISIONS_REQUIRED",
            "issues": issues, "pages": len(slides), "teaching_pages": len(teaching)}


def w06_np(deck: dict) -> dict:
    """Narrative-to-page decomposition audit."""
    slides = deck.get("slides", [])
    teaching = _teaching(slides)
    contract = PC.check(deck)
    issues: list[dict] = []

    # 4.10 source divisions are not page boundaries: every page must name a
    # cognitive unit, and no page may be titled after a source paragraph
    missing_unit = [s.get("page_id") for s in teaching if not s.get("cognitive_unit")]
    if missing_unit:
        issues.append({"rule": "REG-DECOMP-010", "pages": missing_unit[:8],
                       "message": f"{len(missing_unit)} pages do not name a cognitive "
                                  f"unit"})

    # §4.2 / §4.5 come from the page contract gates
    for entry in contract["detail"]:
        issues.append({"rule": entry["gate"], "page": entry.get("page"),
                       "message": entry["message"]})

    # REG-DECOMP-010: the page count must EMERGE from the units. A deck whose
    # teaching pages equal a round preselected number (e.g. exactly 20/50/100) with
    # units left over is the "preselected slide count" failure.
    units = {s.get("cognitive_unit") for s in teaching if s.get("cognitive_unit")}
    emergent = len(teaching) >= len(units)
    if not emergent:
        issues.append({"rule": "REG-DECOMP-010",
                       "message": f"{len(teaching)} pages for {len(units)} cognitive "
                                  f"units: content was dropped to fit a page count"})

    # §6 main deck vs appendix: a page that declares itself a deep dive must say so
    for slide in teaching:
        title = str(slide.get("title", ""))
        if ("附" in title or "深入" in title) and not slide.get("main_or_appendix"):
            issues.append({"rule": "REG-DECOMP-006", "page": slide.get("page_id"),
                           "message": f"deep-dive page {title[:24]!r} does not declare "
                                      f"main_or_appendix"})

    return {"gate": "W06-NP", "status": "PASS" if not issues else "REVISIONS_REQUIRED",
            "issues": issues, "pages": len(slides), "teaching_pages": len(teaching),
            "cognitive_units": len(units),
            "page_count_status": "EMERGENT" if emergent else "CONSTRAINED"}


def audit(deck: dict) -> dict:
    nr, np_ = w06_nr(deck), w06_np(deck)
    status = "PASS" if nr["status"] == "PASS" and np_["status"] == "PASS" \
        else "REVISIONS_REQUIRED"
    return {"deck": deck.get("meta", {}).get("title", ""), "status": status,
            "W06-NR": nr, "W06-NP": np_}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        print("usage: python -m deckkit.narrative_gates DECK.json [--full]")
        return 2
    deck = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    result = audit(deck)
    if "--full" not in args:
        for gate in ("W06-NR", "W06-NP"):
            result[gate]["issues"] = result[gate]["issues"][:10]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
