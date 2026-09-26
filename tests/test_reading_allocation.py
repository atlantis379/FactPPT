# -*- coding: utf-8 -*-
"""Claim-level allocation: one source unit may be divided across several artifact pages.

A `SourceRef` is page-granular, so the original unit-level join could only hand a whole
source page to one artifact page: when two pages cited the same unit, the later one got
nothing. That made "one page per source unit" the only workable shape, which forced the deck
to follow the source's own page boundaries and discarded a reading that grouped the material
by argument. `claim_texts` removes that constraint.
"""
from __future__ import annotations

from app import main
from app.reading_structure import join_pages_to_claims

DOCUMENT_SHA = "sha-under-test"


def _claim(claim_id: str, text: str, page: int, *, triage: str = "MUST_INCLUDE"):
    return main.Claim(id=claim_id, normalized_claim=text, source_quote=text, provenance="SOURCE",
                      risk="YELLOW", triage=triage,
                      source_refs=[main.SourceRef(document_id="doc1", page=page, quote=text)])


def _project(*claims) -> main.Project:
    project = main.Project(title="t", presentation_question="q",
                           documents=[{"id": "doc1", "sha256": DOCUMENT_SHA,
                                       "chunks": [{"page": 2, "text": "x"}, {"page": 3, "text": "y"}]}])
    project.claims = list(claims)
    return project


def _artifact(pages: list[dict]) -> dict:
    return {"schema_version": "reading_structure_artifact.v0.2",
            "source": {"sha256": DOCUMENT_SHA},
            "blocks": [{"block_id": 2, "unit": 2}, {"block_id": 3, "unit": 3}],
            "structure": {"nodes": []},
            "page_plan": pages}


def test_claim_level_pages_may_divide_one_source_unit():
    """The regression this exists for: two topic pages drawing on the same source page."""
    project = _project(_claim("c1", "第一句", 2), _claim("c2", "第二句", 2), _claim("c3", "第三句", 3))
    artifact = _artifact([
        {"page_id": "p1", "source_block_ids": [2, 3], "claim_texts": ["第一句", "第三句"],
         "why_this_page": "主题页一", "figure_intent": "COMPARISON"},
        {"page_id": "p2", "source_block_ids": [2], "claim_texts": ["第二句"],
         "why_this_page": "主题页二", "figure_intent": "DATA"},
    ])
    join = join_pages_to_claims(artifact, project)
    assert [page["claim_ids"] for page in join["pages"]] == [["c1", "c3"], ["c2"]]
    assert [page["allocation_mode"] for page in join["pages"]] == ["CLAIM_TEXTS", "CLAIM_TEXTS"]
    assert join["gaps"] == []
    assert join["join"]["claims_joined"] == 3


def test_unit_level_pages_keep_the_old_behaviour():
    """Backward compatibility: a page without `claim_texts` still joins by unit."""
    project = _project(_claim("c1", "第一句", 2), _claim("c2", "第二句", 3))
    artifact = _artifact([
        {"page_id": "p1", "source_block_ids": [2], "why_this_page": "页一", "figure_intent": "DATA"},
        {"page_id": "p2", "source_block_ids": [3], "why_this_page": "页二", "figure_intent": "DATA"},
    ])
    join = join_pages_to_claims(artifact, project)
    assert [page["claim_ids"] for page in join["pages"]] == [["c1"], ["c2"]]
    assert [page["allocation_mode"] for page in join["pages"]] == ["SOURCE_UNITS", "SOURCE_UNITS"]


def test_a_named_claim_that_does_not_exist_is_reported_not_guessed():
    """The artifact and the extraction can disagree; neither side may be invented."""
    project = _project(_claim("c1", "第一句", 2))
    artifact = _artifact([
        {"page_id": "p1", "source_block_ids": [2], "claim_texts": ["第一句", "从未提取过的句子"],
         "why_this_page": "页一", "figure_intent": "DATA"},
    ])
    join = join_pages_to_claims(artifact, project)
    assert join["pages"][0]["claim_ids"] == ["c1"]
    assert join["pages"][0]["unmatched_claim_texts"] == ["从未提取过的句子"]
    gap = next(item for item in join["gaps"] if item["code"] == "PAGE_CLAIM_TEXT_NOT_FOUND")
    assert gap["page_id"] == "p1"


def test_two_pages_naming_the_same_claim_do_not_render_it_twice():
    project = _project(_claim("c1", "第一句", 2))
    artifact = _artifact([
        {"page_id": "p1", "source_block_ids": [2], "claim_texts": ["第一句"],
         "why_this_page": "页一", "figure_intent": "DATA"},
        {"page_id": "p2", "source_block_ids": [2], "claim_texts": ["第一句"],
         "why_this_page": "页二", "figure_intent": "DATA"},
    ])
    join = join_pages_to_claims(artifact, project)
    assert join["pages"][0]["claim_ids"] == ["c1"]
    assert join["pages"][1]["claim_ids"] == []
    assert join["pages"][1]["overlapped_claim_ids"] == ["c1"]
    assert any(item["code"] == "CLAIM_ALREADY_PLACED" for item in join["gaps"])


def test_an_appendix_claim_cannot_be_named_onto_a_page():
    """Only triaged-in Claims may reach a page, whichever allocation mode is used."""
    project = _project(_claim("c1", "第一句", 2, triage="APPENDIX"))
    artifact = _artifact([
        {"page_id": "p1", "source_block_ids": [2], "claim_texts": ["第一句"],
         "why_this_page": "页一", "figure_intent": "DATA"},
    ])
    join = join_pages_to_claims(artifact, project)
    assert join["pages"][0]["claim_ids"] == []
    assert join["pages"][0]["unmatched_claim_texts"] == ["第一句"]


def test_a_superseded_claim_version_is_not_allocatable():
    """An immutable revision's predecessor is history, not the Claim."""
    old = _claim("c1", "第一句", 2)
    new = _claim("c1:v2", "第一句", 2)
    old.superseded_by_claim_id = new.id
    project = _project(old, new)
    artifact = _artifact([
        {"page_id": "p1", "source_block_ids": [2], "claim_texts": ["第一句"],
         "why_this_page": "页一", "figure_intent": "DATA"},
    ])
    join = join_pages_to_claims(artifact, project)
    assert join["pages"][0]["claim_ids"] == ["c1:v2"]
