"""Regression cases for source and delivered-content completeness."""
from __future__ import annotations

import asyncio
import hashlib
import io
import os
import tempfile
from pathlib import Path

import pytest
from fastapi import UploadFile
from pptx import Presentation
from pptx.util import Emu

from app import main, render_readback
from app.native_beautifier import (BeautificationPlanError, compile_beautification_plan,
                                   validate_beautification_plan, _source_lines)
from app.test_source_extract import docx_bytes, pdf_bytes, xlsx_bytes


def project_with_document(chunks: list[dict]) -> main.Project:
    return main.Project(title="Coverage", presentation_question="What does the source say?",
                        documents=[{"id": "d", "kind": "PDF", "extractor_version": "source_extract.v1",
                                    "coverage_status": "COMPLETE",
                                    "chunks": chunks}])


def test_candidate_extraction_keeps_sentence_26_and_long_quote():
    sentences = [f"Observation number {number} applies to the declared cohort." for number in range(30)]
    sentences.append("A" * 1_200 + ".")
    source = " ".join(sentences)
    project = project_with_document([{"page": 1, "text": source,
                                      "locator": {"kind": "PDF", "page": 1,
                                                  "start": 0, "end": len(source)}}])
    claims = main.source_extractor(project, "d")
    assert len(claims) == 31
    assert claims[25].source_quote == sentences[25]
    assert len(claims[-1].source_quote) > 1_000
    assert claims[-1].source_refs[0].locator.end == len(source)


def test_quote_offsets_keep_pdf_region_after_whitespace_reflow():
    assert main.quote_offsets("Revenue reached 120 units", "Header\nRevenue reached\n120 units.") == (7, 32)


def test_incomplete_extraction_blocks_candidate_reading(monkeypatch):
    project = project_with_document([{"page": 1, "text": "Visible text."}])
    project.workflow_state = "UPLOADED"
    project.documents[0]["coverage_status"] = "NEEDS_REVIEW"
    project.documents[0]["coverage_issues"] = ["PDF_PAGE_1_NON_TEXT_OBJECT_PRESENT"]
    monkeypatch.setattr(main, "get_project", lambda _id: ([project], project))
    monkeypatch.setattr(main, "save_projects", lambda _projects: None)
    with pytest.raises(main.HTTPException) as error:
        main.extract_project_claims(project.id, main.PipelineRequest())
    assert error.value.status_code == 422
    assert "PDF_PAGE_1_NON_TEXT_OBJECT_PRESENT" in error.value.detail["issues"]


def test_legacy_document_without_coverage_metadata_cannot_claim_complete_reading(monkeypatch):
    project = project_with_document([{"page": 1, "text": "Visible text."}])
    project.workflow_state = "UPLOADED"
    project.documents[0].pop("extractor_version")
    monkeypatch.setattr(main, "get_project", lambda _id: ([project], project))
    monkeypatch.setattr(main, "save_projects", lambda _projects: None)
    with pytest.raises(main.HTTPException) as error:
        main.extract_project_claims(project.id, main.PipelineRequest())
    assert error.value.status_code == 422
    assert "SOURCE_COVERAGE_UNVERIFIED" in error.value.detail["issues"]


def test_upload_capacity_error_is_explicit(monkeypatch):
    def over_limit(_filename, _content):
        raise main.SourceCapacityError("source exceeds extracted-character limit")
    monkeypatch.setattr(main, "extract_source", over_limit)
    with pytest.raises(main.HTTPException) as error:
        asyncio.run(main.upload_pdf("p", UploadFile(file=io.BytesIO(b"fake"), filename="huge.pdf")))
    assert error.value.status_code == 413


@pytest.mark.parametrize("filename,expected_kind,locator_key", [
    ("long.pdf", "PDF", "page"),
    ("long.docx", "DOCX", "paragraph"),
    ("sheets.xlsx", "XLSX", "sheet"),
])
def test_upload_preserves_native_location_and_coverage(monkeypatch,
                                                       filename, expected_kind, locator_key):
    content = (pdf_bytes([f"Record {i:03d} " + "A" * 110 for i in range(120)])
               if expected_kind == "PDF" else
               docx_bytes() if expected_kind == "DOCX" else xlsx_bytes())
    project = main.Project(title="Coverage", presentation_question="What does the source say?")
    saved = {}
    monkeypatch.setattr(Path, "write_bytes", lambda path, value: saved.setdefault(path.name, value) and len(value))
    monkeypatch.setattr(main, "get_project", lambda _id: ([project], project))
    monkeypatch.setattr(main, "save_projects", lambda _projects: None)
    result = asyncio.run(main.upload_pdf(project.id, UploadFile(file=io.BytesIO(content), filename=filename)))
    document = result["document"]
    assert document["kind"] == expected_kind
    assert document["sha256"] == hashlib.sha256(content).hexdigest()
    assert document["extractor_version"] == "source_extract.v1"
    assert content in saved.values()
    assert document["units_extracted"] == len(result["source_chunks"])
    assert all(locator_key in chunk["locator"] or
               expected_kind == "DOCX" and "table" in chunk["locator"]
               for chunk in result["source_chunks"])
    if expected_kind == "PDF":
        assert len(result["source_chunks"][0]["text"]) > 12_000
    if expected_kind == "DOCX":
        assert any(chunk["locator"].get("paragraph") == 30 for chunk in result["source_chunks"])
    if expected_kind == "XLSX":
        assert document["coverage_status"] == "NEEDS_REVIEW"
        assert any("FORMULA_VALUE_UNAVAILABLE" in issue for issue in document["coverage_issues"])
        assert {chunk["locator"]["sheet"] for chunk in result["source_chunks"]} == {"Baseline", "Current"}


def one_claim_deck(conditions: list[str]) -> dict:
    return {"project_id": "demo", "pages": [{
        "page_id": "p1", "title": "Source result", "primary_message": "Supported finding",
        "visual_type": "EVIDENCE_MAP", "relationships": [],
        "claims": [{"id": "c1", "normalized_claim": "Supported finding",
                    "provenance": "SOURCE", "risk": "GREEN", "conditions": conditions,
                    "source_refs": [{"document_id": "d", "page": 1, "quote": "source"}]}],
    }]}


def test_four_conditions_survive_plan_and_plan_tampering_is_blocked():
    conditions = ["cohort A", "within 30 days", "after baseline", "only in region B"]
    deck = one_claim_deck(conditions)
    plan = compile_beautification_plan(deck)
    claim = next(item for item in plan["pages"][0]["elements"] if item["name"] == "claim:c1")
    assert all(condition in claim["text"] for condition in conditions)
    claim["text"] = claim["text"].replace(conditions[-1], "")
    report = validate_beautification_plan(deck, plan)
    assert report["status"] == "FAIL"
    assert any(issue["type"] == "CONDITION_OMITTED" for issue in report["issues"])


def test_slide_source_labels_use_word_and_excel_native_positions():
    claims = [{"source_refs": [
        {"document_id": "word", "page": 31,
         "locator": {"kind": "DOCX", "part": "body", "paragraph": 30}},
        {"document_id": "sheet", "page": 2,
         "locator": {"kind": "XLSX", "sheet": "Current", "cell": "C4"}},
    ]}]
    assert _source_lines(claims) == ["word body paragraph[30]", "sheet Current!C4"]


def test_conditions_that_cannot_fit_block_instead_of_shrinking():
    deck = one_claim_deck(["required qualifier " + str(i) + " " + "X" * 100 for i in range(5)])
    with pytest.raises(BeautificationPlanError, match="split"):
        compile_beautification_plan(deck)


def test_chart_declaration_blocks_until_series_readback_is_supported():
    deck = one_claim_deck([])
    deck["pages"][0]["charts"] = [{"id": "chart1"}]
    with pytest.raises(BeautificationPlanError, match="chart-data contract"):
        compile_beautification_plan(deck)


def test_pptx_readback_reports_missing_required_condition():
    handle = tempfile.NamedTemporaryFile(suffix=".pptx", dir=Path(__file__).parent, delete=False)
    target = Path(handle.name)
    handle.close()
    presentation = Presentation()
    presentation.slide_width = Emu(1280 * render_readback.EMU_PER_PX)
    presentation.slide_height = Emu(720 * render_readback.EMU_PER_PX)
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    shape = slide.shapes.add_textbox(Emu(100 * render_readback.EMU_PER_PX),
                                   Emu(100 * render_readback.EMU_PER_PX),
                                   Emu(500 * render_readback.EMU_PER_PX),
                                   Emu(100 * render_readback.EMU_PER_PX))
    shape.name = "claim:c1"
    shape.text = "Supported finding; cohort A"
    presentation.save(target)
    contract = {"canvas": [1280, 720], "pages": [{
        "page_id": "p1", "objects": [{"name": "claim:c1", "box": [100, 100, 500, 100],
                                          "text": "Supported finding; cohort A", "has_geometry": True}],
        "mandatory": ["claim:c1"], "exact_text": [], "reading_order": [], "roles": {},
        "required_text_by_object": {"claim:c1": ["cohort A", "within 30 days"]},
    }]}
    try:
        report = render_readback.verify_render(target, contract)
        assert report["status"] == "BLOCK"
        assert any(issue["code"] == "REQUIRED_TEXT_MISSING" and
                   issue["detail"]["required"] == "within 30 days"
                   for issue in report["omission_report"])
    finally:
        os.unlink(target)
