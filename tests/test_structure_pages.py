# -*- coding: utf-8 -*-
"""A page that renders the argument's shape, not evidence.

The reading artifact may declare ROADMAP / SECTION_QUESTION / PART_RECAP / CONSOLIDATION pages.
Such a page legitimately cites no source blocks. Every delivered deck was missing a visible
throughline because these pages were dropped outright: `architect_from_reading_structure`
skipped any page with no approved Claim, and the renderer had no archetype that could lay one
out anyway. The thread was written in the artifact and had no slide to appear on.
"""
from __future__ import annotations

from app.native_beautifier import _evaluate_candidates, _layout_structure


def _structure_page(**overrides) -> dict:
    page = {"page_id": "pg_struct", "title": "本章主线", "primary_message": "先说清这一章要回答什么",
            "visual_type": "EVIDENCE_MAP", "claims": [], "relationships": [],
            "renders_structure": "ROADMAP",
            "structure_text": "在病原学大多查不出来的现实下，肺炎该怎么诊断、分层、经验性用药、判断疗效。",
            "structure_segments": ["问题：病原学查不出", "原因：培养慢阳性率低",
                                   "解决：诊断三步＋分层用药", "注意：疗程与特殊人群"]}
    page.update(overrides)
    return page


def _tokens() -> dict:
    from app.native_beautifier import DESIGN_TOKENS
    return DESIGN_TOKENS


def test_a_structure_page_is_a_candidate_even_with_no_claims():
    candidates = _evaluate_candidates(_structure_page())
    assert [item["archetype"] for item in candidates] == ["STRUCTURE_PAGE"]
    assert candidates[0]["status"] == "VALID"


def test_a_claim_less_page_without_a_structure_declaration_stays_uncandidateable():
    """The exception is narrow on purpose: it must not become a way to render a page with no
    evidence at all. Without the declaration, nothing is valid."""
    page = _structure_page()
    page.pop("renders_structure")
    assert all(item["status"] != "VALID" for item in _evaluate_candidates(page))


def test_the_structure_page_renders_the_reading_words_not_an_invented_caption():
    elements, connectors = _layout_structure(_structure_page(), _tokens())
    rendered = " ".join(str(item.get("text") or "") for item in elements)
    assert "在病原学大多查不出来的现实下" in rendered
    assert "解决：诊断三步＋分层用药" in rendered
    assert connectors == []
    assert not any(str(item.get("name", "")).startswith("claim:") for item in elements)


def test_the_structure_page_does_not_overflow_its_band():
    from app.layout_ir import assess_plan_text_fit
    for segments in ([], ["问题：甲", "原因：乙", "解决：丙", "注意：丁"]):
        page = _structure_page(structure_segments=segments)
        elements, _ = _layout_structure(page, _tokens())
        plan = {"pages": [{"page_id": page["page_id"], "selected_archetype": "STRUCTURE_PAGE",
                           "elements": elements, "connectors": []}]}
        result = assess_plan_text_fit(plan)
        assert result["status"] == "PASS", result["issues"]
