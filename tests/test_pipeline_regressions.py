# -*- coding: utf-8 -*-
"""Regressions for the defects the end-to-end GOLD 2026 run exposed.

Each test names the observed failure, so a future change that reintroduces it fails here
rather than three stages later in a rendered deck. The run that produced them is recorded in
`app/validation/run_gold2026_v2/`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import main
from app.main import quote_occurs_in
from app.native_beautifier import BeautificationPlanError, compile_beautification_plan, _title_size


def _claim(claim_id: str, text: str, *, risk: str = "YELLOW", conditions: list[str] | None = None):
    return main.Claim(id=claim_id, normalized_claim=text, source_quote=text, provenance="SOURCE",
                      risk=risk, conditions=conditions or [],
                      source_refs=[main.SourceRef(document_id="d", page=1, quote=text)])


def _project(claims=None, pages=None) -> main.Project:
    project = main.Project(title="t", presentation_question="q",
                           documents=[{"id": "d", "sha256": "sha", "chunks": [{"page": 1, "text": "x"}]}])
    project.claims = claims or []
    project.pages = pages or []
    return project


# --------------------------------------------------------------- claim scope and states
def test_a_superseded_claim_version_leaves_the_active_set():
    """Reported failure: completing a RED binding could never clear Verify.

    `PATCH /claims/{id}/binding` creates an immutable new version, but the unbound
    predecessor stayed in the verified set, so NUMERICAL_QA blocked the deck for good.
    """
    claim = _claim("c1", "Risk is 20%", risk="RED", conditions=["adults"])
    project = _project([claim])
    revision = main.create_claim_revision(project, "c1", main.ClaimRevisionRequest(
        conditions=["adults"], numeric_facts=[main.NumericFact(
            value="20", unit="%", metric="risk", population="adults", timeframe="baseline",
            outcome="risk", intervention="none", comparator="none", statistic_type="PROPORTION",
            status="BOUND")],
        revision_reason="complete the numeric binding"))
    assert len(project.claims) == 2, "the old version must stay readable"
    active = main.active_claims(project)
    assert [item.id for item in active] == [revision["claim"].id]
    assert claim.superseded_by_claim_id == revision["claim"].id


def test_binding_before_architect_does_not_strand_the_project_in_architected():
    """Reported failure: binding set workflow_state=ARCHITECTED with no pages built, and
    Triage is not eligible from ARCHITECTED, so the documented binding channel could not be
    used at all before planning."""
    project = _project([_claim("c1", "Risk is 20%", risk="RED")])
    project.workflow_state = "EXTRACTED"
    main.create_claim_revision(project, "c1", main.ClaimRevisionRequest(
        conditions=["adults"], revision_reason="add the missing bundle"))
    assert project.workflow_state == "EXTRACTED"
    assert "EXTRACTED" in main.ALLOWED_STATES["triage"]


def test_verification_can_be_rerun_after_a_block():
    """Reported failure: a BLOCK was a dead end -- the remediation loop the review sheet
    describes (issue -> fix -> reverify) could not be closed."""
    assert "BLOCKED" in main.ALLOWED_STATES["verify"]


def test_rebuilding_pages_invalidates_the_previous_verification():
    """Reported failure: re-architecting replaced the page set while the recorded
    VerificationResult stayed current, so a rebuilt deck could inherit a PASS it never earned.
    """
    assert "BLOCKED" in main.ALLOWED_STATES["architect"]
    assert "COMPLIANCE_REVIEW" in main.ALLOWED_STATES["architect"]


# ---------------------------------------------------------------------------- privacy
def test_a_published_email_in_the_source_is_a_review_item_not_a_delivery_block():
    """Reported failure: every journal PDF carries the corresponding author's address, so
    scanning the source for emails blocked compliance on real literature."""
    project = _project([_claim("c1", "患病率 2.7%")])
    project.documents[0]["chunks"][0]["text"] = "Corresponding author: tlsm@jnu.edu.cn"
    result = main.compliance(project)
    assert result["status"] == "PASS"
    assert result["issues"][0]["category"] == "PRIVACY_SOURCE_ONLY"
    assert result["issues"][0]["severity"] == "HUMAN_REVIEW"


def test_a_patient_identifier_class_still_blocks_wherever_it_appears():
    """A phone number in the evidence means the project holds identifiable data."""
    project = _project([_claim("c1", "患病率 2.7%")])
    project.documents[0]["chunks"][0]["text"] = "患者联系电话 13812345678"
    result = main.compliance(project)
    assert result["status"] == "BLOCK"
    assert result["issues"][0]["category"] == "PRIVACY"


def test_an_email_in_presentation_text_blocks():
    project = _project([_claim("c1", "联系 tlsm@jnu.edu.cn 获取全文")])
    assert main.compliance(project)["status"] == "BLOCK"


# --------------------------------------------------------------------- numeric fidelity
def test_identifier_digits_are_not_harvested_as_measurements():
    """Reported failure: `FEV1` produced a NumericFact "1" that could never be grounded,
    because the exact-value check ignores digits preceded by a letter."""
    assert main.extract_numeric_facts("支气管舒张后FEV1水平以及GOLD2026") == []
    assert [fact.value for fact in main.extract_numeric_facts("疗程缩短至5 d")] == ["5"]


def test_hyphen_ranges_are_not_read_as_negative_numbers():
    """Reported failure: "1006-5725" yielded -5725, so a correct positive fact was reported
    as absent from its own quote."""
    tokens = main._source_numeric_tokens("1006-5725 及 12-16 周")
    assert 5725 in tokens and 16 in tokens and -5725 not in tokens


def test_quote_grounding_is_whitespace_insensitive_on_both_sides():
    """Reported failure: the reader accepted a re-wrapped quote that the verifier then
    rejected as fabricated, because one side normalised whitespace and the other did not."""
    assert quote_occurs_in("全球慢阻肺病患病率为2.7%", "全球慢阻肺病患病率 为 2.7% ，较1990年下降")
    assert not quote_occurs_in("完全不存在的句子", "全球慢阻肺病患病率 为 2.7%")


def test_render_readback_decodes_xml_entities():
    """Reported failure: a Claim containing "<14 d" was reported as altered, because the
    extracted text still held its OOXML escape."""
    from app.packager import _visible_text
    assert _visible_text("<a:t>症状在&lt;14 d内恶化</a:t>") == "症状在<14 d内恶化"


# ------------------------------------------------------------------------- composition
def _deck(page: dict) -> dict:
    return {"project_id": "p", "pages": [page]}


def _flex_page(tree: dict, count: int = 4) -> dict:
    claims = [_claim(f"c{index}", "急性加重定义从症状在<14 d内恶化细化为数天内急性恶化。",
                     risk="RED", conditions=["时间窗以天计"]).model_dump()
              for index in range(1, count + 1)]
    return {"page_id": "p1", "title": "急性加重定义细化并按ROME分级", "primary_message": "更早识别",
            "visual_type": "EVIDENCE_MAP", "claims": claims, "relationships": []}


def _flex_plan(tree: dict):
    from app.layout_ir import semantic_digest
    deck = _deck(_flex_page(tree))
    layout_ir = {"schema_version": "layout-ir.v1", "semantic_digest": semantic_digest(deck),
                 "pages": [{"page_id": "p1", "archetype": "FLEX_COMPOSITION",
                            "layout_tree": tree, "rationale": "模型选择的分组"}]}
    return compile_beautification_plan(deck, layout_ir=layout_ir)


def test_a_column_major_flex_tree_is_rejected_at_design_time():
    """Reported failure: row[column[c1,c2], column[c3,c4]] reads c1, c3, c2, c4, which
    silently reorders the approved narrative. The planner must say so, with the fix."""
    tree = {"kind": "row", "gap": 28, "children": [
        {"kind": "column", "gap": 20, "children": [
            {"kind": "claim", "claim_id": "c1", "weight": 1},
            {"kind": "claim", "claim_id": "c2", "weight": 1}]},
        {"kind": "column", "gap": 20, "children": [
            {"kind": "claim", "claim_id": "c3", "weight": 1},
            {"kind": "claim", "claim_id": "c4", "weight": 1}]}]}
    with pytest.raises(BeautificationPlanError, match="different order than the approved Claims"):
        _flex_plan(tree)


def test_a_row_major_flex_tree_is_accepted():
    tree = {"kind": "column", "gap": 20, "children": [
        {"kind": "row", "gap": 28, "children": [
            {"kind": "claim", "claim_id": "c1", "weight": 1},
            {"kind": "claim", "claim_id": "c2", "weight": 1}]},
        {"kind": "row", "gap": 28, "children": [
            {"kind": "claim", "claim_id": "c3", "weight": 1},
            {"kind": "claim", "claim_id": "c4", "weight": 1}]}]}
    assert _flex_plan(tree)["pages"][0]["selected_archetype"] == "FLEX_COMPOSITION"


def test_a_long_action_title_is_sized_to_its_box_instead_of_rejected():
    """Reported failure: model action titles overflow the fixed 58px title box, and the
    compiler rejected the approved page rather than fitting the box it owns."""
    long_title = "急性加重高风险（E组）标准下调为过去一年≥1次中重度急性加重并强调及早识别与干预"
    assert _title_size(long_title, 1120, 58, (38, 34, 30, 27, 24, 21)) < 38


def test_the_chosen_title_size_is_measured_with_the_real_text_frame_inset():
    """Reported failure: the size was chosen by measuring at zero inset, so the planner then
    rejected the very title it had just sized -- two places disagreeing about LD-03."""
    from app.layout_ir import measure_text, text_frame_insets

    title = "病例发现路径从35岁高危人群到确诊管理，RSV接种年龄同步前移"
    size = _title_size(title, 1120, 58, (38, 34, 30, 27, 24, 21))
    horizontal, vertical = text_frame_insets("text")
    measured = measure_text(title, 1120, size, horizontal_inset=horizontal, vertical_inset=vertical)
    assert measured["required_height"] <= 58, "the size chosen must be one the fit gate accepts"
    at_zero_inset = measure_text(title, 1120, size, horizontal_inset=0, vertical_inset=0)
    assert at_zero_inset["required_height"] <= measured["required_height"]


def test_the_completeness_check_does_not_fail_on_a_legitimate_decline():
    """Reported failure: the check required `units_with_no_candidate` to be empty, which is
    exactly what a legitimate decline looks like -- a masthead has nothing quotable."""
    from app.validation.semantic_act_qualification import check_full_text_read

    pages = {1: "实用医学杂志 ISSN 1006-5725", 2: "患病率为2.7%，死亡372万例。"}
    audit = {"status": "PASS", "rule_version": "test",
             "statistics": {"accounted": 2, "declined": 1, "declined_content_bearing": 0,
                            "tokens": 2, "tokens_covered": 2, "tokens_excluded": 0,
                            "tokens_unaccounted": 0, "thresholds_unaccounted": 0},
             "issues": []}
    result = check_full_text_read(pages, offered_pages={2}, payload_pages=[1, 2], audit=audit)
    assert result["status"] == "PASS"
    assert result["units_with_no_candidate"] == [1]


def test_the_allocation_check_does_not_call_an_appendix_claim_dropped():
    """Reported failure: the check compared the page set against every triaged Claim, so a
    claim deliberately parked in APPENDIX looked like evidence lost by allocation."""
    from app.validation.semantic_act_qualification import check_narrative

    claims = [{"id": "c1", "triage": "MUST_INCLUDE"}, {"id": "c2", "triage": "APPENDIX"}]
    pages = [{"page_id": "p1", "claim_ids": ["c1"], "goal": "有理由", "primary_message": "有信息"}]
    result = check_narrative(pages, claims, None, None, None, None)
    assert result["status"] == "PASS"
    assert result["dropped_claims"] == []
    assert result["claims_in_appendix"] == 1


# -------------------------------------------------------------------------- identity
def test_delivery_identity_folds_in_layout_and_assets():
    """Reported failure: the PPTX export hashed a hand-built identity dict instead of the
    deck, so every export raised KeyError('presentation_question')."""
    deck = {"project_id": "p", "presentation_question": "q", "export_type": "D",
            "pages": [{"page_id": "p1"}]}
    documents = [{"id": "d", "sha256": "s", "page_count": 1}]
    base = main.immutable_snapshot_digest(deck, documents)
    with_layout = main.immutable_snapshot_digest(deck, documents, extra={"layout_ir": {"pages": []}})
    assert base != with_layout
    assert base == main.immutable_snapshot_digest(deck, documents)


def test_the_delivery_manifest_uses_the_same_identity_as_the_export():
    """Reported failure: `delivery_manifest` hashed a smaller payload than the export, so the
    duplicate guard never matched and every export appended another identical manifest."""
    deck = {"project_id": "p", "presentation_question": "q", "export_type": "D",
            "pages": [{"page_id": "p1"}]}
    project = _project()
    documents = [{"id": "d", "sha256": "s", "page_count": 1}]
    project.documents = documents
    extra = {"layout_ir": {"pages": []}, "editorial_asset_sha256s": []}
    expected = f"del_{main.immutable_snapshot_digest(deck, documents, extra=extra)[:16]}"
    manifest = main.delivery_manifest(project, deck, "0" * 64, {"status": "PASS"}, extra=extra)
    assert manifest["snapshot_id"] == expected
