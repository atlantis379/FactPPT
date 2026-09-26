"""Readback verification against a REAL deck produced by the public PPTX writer.

The unit tests use synthesised files. These build the artifact with the same Node
runtime and beautification plan the product uses, then verify it -- and then inject
a rendering-level defect into the delivered file to show the check blocks it.

Skipped when the locked Node/PptxGenJS writer is unavailable, so the suite stays
runnable in Python-only environments.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import render_readback as RR  # noqa: E402
from app.main import (Claim, PageSpec, Project, SourceRef,  # noqa: E402
                      record_verification, semantic_deck)
from app.native_beautifier import compile_beautification_plan  # noqa: E402
from app.packager import DEFAULT_PPTXGENJS_MODULE, build_pptx  # noqa: E402

needs_builder = pytest.mark.skipif(
    not DEFAULT_PPTXGENJS_MODULE.exists(),
    reason="locked PptxGenJS writer is not installed; run npm ci")

DOC_TEXT = "First sourced fact. Second sourced fact."


def build_real_deck(target: Path) -> dict:
    claims = [
        Claim(id="a", normalized_claim="First sourced fact", provenance="SOURCE",
              source_quote="First sourced fact",
              source_refs=[SourceRef(document_id="d", page=1, quote="First")],
              conditions=["context"]),
        Claim(id="b", normalized_claim="Second sourced fact", provenance="SOURCE",
              source_quote="Second sourced fact",
              source_refs=[SourceRef(document_id="d", page=1, quote="Second")],
              conditions=["context"]),
    ]
    page = PageSpec(id="p", title="First sourced fact", primary_message="First sourced fact",
                    visual_type="EVIDENCE_MAP", claim_ids=["a", "b"], provenance="SOURCE",
                    goal="teach")
    project = Project(title="t", presentation_question="fact", claims=claims, pages=[page],
                      documents=[{"id": "d", "chunks": [{"page": 1, "text": DOC_TEXT}]}])
    record_verification(project)
    deck = semantic_deck(project)
    build_pptx(deck, target)
    return deck


@needs_builder
def test_real_deck_passes_the_readback(tmp_path):
    target = tmp_path / "real.pptx"
    deck = build_real_deck(target)
    contract = RR.contract_from_plan(compile_beautification_plan(deck))
    result = RR.verify_render(target, contract)
    assert result["status"] == "PASS", result["issues"]
    assert result["issues"] == []
    assert result["coverage"]["reading_order"] == "CHECKED"


@needs_builder
def test_real_deck_readback_blocks_a_reading_order_defect(tmp_path):
    """Reproduce the A04 failure mode inside the product's own output.

    The delivered file is edited directly (as a downstream tool or a human would),
    not the plan: the verifier must judge the bytes actually shipped.
    """
    from pptx import Presentation
    from pptx.util import Emu

    target = tmp_path / "tampered.pptx"
    deck = build_real_deck(target)
    contract = RR.contract_from_plan(compile_beautification_plan(deck))

    presentation = Presentation(str(target))
    slide = presentation.slides[0]
    by_name = {shape.name: shape for shape in slide.shapes}
    first, second = by_name["claim:a"], by_name["claim:b"]

    # The flow archetype places the two cards side by side in ONE row, so the
    # reader meets them left to right. Swapping their horizontal positions makes
    # the reader meet b first while the page still declares a then b.
    first_left, second_left = first.left, second.left
    first.left, second.left = Emu(second_left), Emu(first_left)
    presentation.save(str(target))

    result = RR.verify_render(target, contract)
    assert result["status"] == "BLOCK"
    order_issue = next(i for i in result["issues"] if i["code"] == "READING_ORDER_MISMATCH")
    assert order_issue["detail"]["declared"] == ["claim:a", "claim:b"]
    assert order_issue["detail"]["rendered"] == ["claim:b", "claim:a"]


@needs_builder
def test_real_deck_readback_blocks_a_dropped_mandatory_object(tmp_path):
    """Deleting a semantic object from the shipped file must not pass this time."""
    from pptx import Presentation

    target = tmp_path / "dropped.pptx"
    deck = build_real_deck(target)
    visual_contracts = [{"page_id": "p", "mandatory_object_ids": ["a"],
                         "exact_text_register": ["First sourced fact"]}]
    contract = RR.contract_from_plan(compile_beautification_plan(deck),
                                     visual_contracts=visual_contracts)

    presentation = Presentation(str(target))
    slide = presentation.slides[0]
    for shape in list(slide.shapes):
        if shape.name == "claim:a":
            shape._element.getparent().remove(shape._element)
    presentation.save(str(target))

    result = RR.verify_render(target, contract)
    assert result["status"] == "BLOCK"
    codes = {i["code"] for i in result["issues"]}
    assert "MANDATORY_OBJECT_MISSING" in codes
