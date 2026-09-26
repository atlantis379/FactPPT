"""Focused regression checks for model-controlled, semantics-locked layout."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.layout_ir import (LayoutIntentError, TEXT_FRAME_INSET_HORIZONTAL, assess_plan_text_fit,
                           configured_model, configured_review_model, design_brief, measure_text, merge_layout_ir,
                           validate_layout_ir)
from app.native_beautifier import BeautificationPlanError, compile_beautification_plan
from app.packager import build_pptx, verify_pptx


def sample_deck() -> dict:
    claims = [
        {"id": "c1", "normalized_claim": "先核对感染证据和病情严重程度", "conditions": [],
         "provenance": "SOURCE", "risk": "GREEN", "source_refs": [{"document_id": "d", "page": 1}]},
        {"id": "c2", "normalized_claim": "影像结果需要结合临床表现解释", "conditions": [],
         "provenance": "SOURCE", "risk": "GREEN", "source_refs": [{"document_id": "d", "page": 2}]},
    ]
    return {"project_id": "demo", "pages": [{"page_id": "p1", "goal": "解释初步评估",
            "title": "肺炎的初步评估", "primary_message": "临床证据和影像结果需要共同解读",
            "visual_type": "EVIDENCE_MAP", "claims": claims, "relationships": []}]}


def focus_proposal(deck: dict) -> dict:
    return {"schema_version": "layout-ir.v1", "semantic_digest": design_brief(deck)["semantic_digest"],
            "pages": [{"page_id": "p1", "archetype": "FOCUS_EVIDENCE", "focus_claim_id": "c1",
                       "rationale": "先突出评估起点，再说明影像证据的解释边界"}]}


def flex_proposal(deck: dict) -> dict:
    return {"schema_version": "layout-ir.v1", "semantic_digest": design_brief(deck)["semantic_digest"],
            "pages": [{"page_id": "p1", "archetype": "FLEX_COMPOSITION", "focus_claim_id": "c1",
                       "layout_tree": {"kind": "row", "gap": 28, "children": [
                           {"kind": "claim", "claim_id": "c1", "weight": 2},
                           {"kind": "claim", "claim_id": "c2", "weight": 1}]},
                       "rationale": "按主次信息量分配宽度，保留两条证据的阅读顺序"}]}


def focusable_deck() -> dict:
    """Four approved Claims: enough support rows to expose the focal row band."""
    claims = [
        {"id": "c1", "normalized_claim": "将高危人群的年龄下限从60岁下调至50岁", "conditions": [],
         "provenance": "SUMMARY", "risk": "GREEN", "source_refs": [{"document_id": "d", "page": 1}]},
        {"id": "c2", "normalized_claim": "首次将mRNA疫苗纳入建议", "conditions": [],
         "provenance": "SUMMARY", "risk": "GREEN", "source_refs": [{"document_id": "d", "page": 2}]},
        {"id": "c3", "normalized_claim": "佐剂疫苗保护期由2季延长至3季", "conditions": [],
         "provenance": "SOURCE", "risk": "GREEN", "source_refs": [{"document_id": "d", "page": 3}]},
        {"id": "c4", "normalized_claim": "继续建议每年接种流感疫苗", "conditions": [],
         "provenance": "SUMMARY", "risk": "GREEN", "source_refs": [{"document_id": "d", "page": 4}]},
    ]
    return {"project_id": "demo", "pages": [{"page_id": "p1", "goal": "疫苗接种更新",
            "title": "疫苗接种建议", "primary_message": "接种人群与疫苗选择均有更新",
            "visual_type": "EVIDENCE_MAP", "claims": claims, "relationships": []}]}


def focus_proposal_for(deck: dict, focal: str) -> dict:
    return {"schema_version": "layout-ir.v1", "semantic_digest": design_brief(deck)["semantic_digest"],
            "pages": [{"page_id": "p1", "archetype": "FOCUS_EVIDENCE", "focus_claim_id": focal,
                       "rationale": "先突出页面主信息，其余 Claim 作为支撑证据"}]}


def test_model_intent_changes_composition_without_changing_evidence():
    deck = sample_deck()
    ir = merge_layout_ir(deck, None, focus_proposal(deck))
    plan = compile_beautification_plan(deck, layout_ir=ir)
    assert plan["pages"][0]["selected_archetype"] == "FOCUS_EVIDENCE"
    assert plan["text_fit"]["status"] == "PASS"
    named = {e["name"]: e for e in plan["pages"][0]["elements"]}
    assert named["claim:c1"]["text"] == deck["pages"][0]["claims"][0]["normalized_claim"]
    assert named["claim:c2"]["text"] == deck["pages"][0]["claims"][1]["normalized_claim"]


def test_model_flex_tree_controls_geometry_with_claims_locked():
    deck = sample_deck()
    plan = compile_beautification_plan(deck, layout_ir=flex_proposal(deck))
    claims = {e["name"]: e for e in plan["pages"][0]["elements"] if e["name"].startswith("claim:")}
    assert plan["pages"][0]["selected_archetype"] == "FLEX_COMPOSITION"
    assert claims["claim:c1"]["position"]["width"] > claims["claim:c2"]["position"]["width"]
    provenance = next(e for e in plan["pages"][0]["elements"] if e["name"] == "provenance:c1")
    assert provenance["position"]["top"] - (claims["claim:c1"]["position"]["top"]
            + claims["claim:c1"]["position"]["height"]) == 10
    assert plan["text_fit"]["status"] == "PASS"
    bad = flex_proposal(deck)
    bad["pages"][0]["layout_tree"]["children"][1]["claim_id"] = "c1"
    with pytest.raises(LayoutIntentError, match="every Claim once"):
        validate_layout_ir(deck, bad)


def test_model_cannot_imply_unapproved_sequence_or_comparison():
    deck = sample_deck()
    candidates = {item["archetype"]: item["status"]
                  for item in design_brief(deck)["pages"][0]["candidates"]}
    assert candidates["TIMELINE"] == "REJECTED"
    assert candidates["COMPARISON_COLUMNS"] == "REJECTED"
    proposal = focus_proposal(deck)
    proposal["pages"][0]["archetype"] = "TIMELINE"
    proposal["pages"][0].pop("focus_claim_id")
    with pytest.raises(LayoutIntentError, match="valid candidate"):
        validate_layout_ir(deck, proposal)


def test_stale_or_content_bearing_model_output_is_rejected():
    deck = sample_deck()
    proposal = focus_proposal(deck)
    proposal["pages"][0]["text"] = "未经批准的医学结论"
    with pytest.raises(LayoutIntentError, match="unsupported fields"):
        validate_layout_ir(deck, proposal)
    proposal["pages"][0].pop("text")
    deck["pages"][0]["claims"][0]["normalized_claim"] += "（修订）"
    with pytest.raises(LayoutIntentError, match="stale"):
        validate_layout_ir(deck, proposal)


def test_model_selected_layout_cannot_silently_shrink_dense_text():
    deck = sample_deck()
    # Overflows the supporting slot at the declared body size while still fitting the layout's
    # own capacity envelope, so the only way to render it would be to shrink below body size.
    # The invariant is that such text is *surfaced* (split or re-composed) instead.
    deck["pages"][0]["claims"][1]["normalized_claim"] = "需要结合临床表现解释。" * 45
    proposal = focus_proposal(deck)
    with pytest.raises(BeautificationPlanError, match="does not fit"):
        compile_beautification_plan(deck, layout_ir=proposal)


def test_model_endpoint_classification(monkeypatch):
    monkeypatch.setenv("EASYPPT_LAYOUT_MODEL_URL", "http://127.0.0.1:1234/v1/chat/completions")
    monkeypatch.setenv("EASYPPT_LAYOUT_MODEL_ID", "local-vision")
    assert configured_model()["external"] is False
    monkeypatch.setenv("EASYPPT_LAYOUT_MODEL_URL", "http://example.com/v1/chat/completions")
    with pytest.raises(LayoutIntentError, match="loopback HTTP or HTTPS"):
        configured_model()


def test_visual_review_uses_a_separate_model_configuration(monkeypatch):
    url = "http://127.0.0.1:1234/v1/chat/completions"
    monkeypatch.setenv("EASYPPT_LAYOUT_MODEL_URL", url)
    monkeypatch.setenv("EASYPPT_LAYOUT_MODEL_ID", "designer")
    monkeypatch.setenv("EASYPPT_LAYOUT_REVIEW_MODEL_URL", url)
    monkeypatch.setenv("EASYPPT_LAYOUT_REVIEW_MODEL_ID", "designer")
    with pytest.raises(LayoutIntentError, match="must differ"):
        configured_review_model()
    monkeypatch.setenv("EASYPPT_LAYOUT_REVIEW_MODEL_ID", "independent-vision")
    reviewer = configured_review_model()
    assert reviewer["model_id"] == "independent-vision"
    assert reviewer["api_key_env"] == "EASYPPT_LAYOUT_REVIEW_MODEL_API_KEY"


def test_api_model_design_is_checked_and_persisted(monkeypatch):
    from app import main

    deck = sample_deck()
    project = main.Project(title="demo", presentation_question="如何评估？")
    monkeypatch.setattr(main, "get_project", lambda project_id: ([project], project))
    monkeypatch.setattr(main, "semantic_deck", lambda value: deck)
    monkeypatch.setattr(main, "save_projects", lambda value: None)
    monkeypatch.setattr(main, "configured_model", lambda: {
        "url": "http://127.0.0.1:1234/v1/chat/completions", "model_id": "local",
        "external": False, "adapter_id": "local-test"})
    monkeypatch.setattr(main, "call_layout_model", lambda brief, model, feedback="": focus_proposal(deck))
    result = main.run_layout_design("demo", main.LayoutRunRequest(page_ids=["p1"]))
    assert result["status"] == "ACCEPTED"
    assert project.layout_ir["pages"][0]["archetype"] == "FOCUS_EVIDENCE"
    assert project.model_runs[-1]["agent"] == "layout_designer"


def test_api_visual_review_uses_rendered_and_verified_slide(monkeypatch):
    from app import main
    from app.validation import render_with_powerpoint
    import uuid

    deck = sample_deck()
    project = main.Project(title="demo", presentation_question="如何评估？")
    project.layout_ir = flex_proposal(deck)
    monkeypatch.setattr(main, "get_project", lambda project_id: ([project], project))
    monkeypatch.setattr(main, "semantic_deck", lambda value: deck)
    monkeypatch.setattr(main, "save_projects", lambda value: None)
    plan_hash = uuid.uuid4().hex
    monkeypatch.setattr(main, "_visual_plan_digest", lambda *args: plan_hash)
    monkeypatch.setattr(main, "configured_review_model", lambda: {
        "url": "http://127.0.0.1:1234/v1/chat/completions", "model_id": "local-vision",
        "external": False, "adapter_id": "local-vision-test"})
    monkeypatch.setattr(main, "call_visual_review_model", lambda brief, image_path, model: {
        "page_id": brief["pages"][0]["page_id"], "verdict": "REVISE",
        "concerns": ["证据区留白偏大"]})
    calls = []
    def fake_build(deck, target, **kwargs):
        calls.append("build")
        assert kwargs["validation_receipt"].parent != target.parent
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"pptx")
        kwargs["validation_receipt"].parent.mkdir(parents=True, exist_ok=True)
        from app.stage_contract import digest_file
        import json
        kwargs["validation_receipt"].write_text(json.dumps({
            "schemaVersion": "presentation-finalization.v1",
            "finalSha256": digest_file(target),
            "packageIntegrity": {"status": "pass"},
            "presentationLayout": {"exitCode": 0, "findingCount": 0},
            "fontSelection": {"passed": True},
            "firstPartyImport": {"passed": True}}), encoding="utf-8")
        return target
    def fake_render(src, out):
        calls.append("powerpoint")
        out.mkdir(parents=True, exist_ok=True)
        (out / "slide-01.png").write_bytes(b"powerpoint png")
        return {"slides": 1}
    monkeypatch.setattr(main, "build_pptx", fake_build)
    monkeypatch.setattr(main, "verify_pptx", lambda *args, **kwargs: {"status": "PASS"})
    monkeypatch.setattr(render_with_powerpoint, "render", fake_render)
    result = main.run_layout_visual_review("demo", main.LayoutRunRequest(page_ids=["p1"]))
    assert result["status"] == "ADVISORY_REVIEW"
    assert result["pages"][0]["verdict"] == "REVISE"
    assert project.layout_visual_reviews[-1]["preview_sha256"]
    assert result["renderer"] == "powerpoint"
    assert calls[-1] == "powerpoint"
    # Losing the finalizer receipt invalidates an otherwise intact visual cache.
    Path(result["validation_receipt_path"]).unlink()
    main.run_layout_visual_review("demo", main.LayoutRunRequest(page_ids=["p1"]))
    assert calls.count("build") == 2


def test_operator_visual_review_requires_exact_deck_and_every_image(monkeypatch):
    from app import main

    deck = sample_deck()
    project = main.Project(title="demo", presentation_question="如何评估？")
    monkeypatch.setattr(main, "get_project", lambda project_id: ([project], project))
    monkeypatch.setattr(main, "semantic_deck", lambda value: deck)
    monkeypatch.setattr(main, "save_projects", lambda value: None)
    monkeypatch.setattr(main, "_render_visual_package", lambda project, deck: {
        "preview_sha256": "exact-deck", "renderer": "powerpoint",
        "images": [{"page_id": "p1", "sha256": "exact-image", "path": "managed.png"}]})
    page = main.VisualReviewPageSubmission(page_id="p1", image_sha256="exact-image",
                                            verdict="REVISE", concerns=["层级不足"])
    with pytest.raises(main.HTTPException, match="PPTX bytes"):
        main.register_layout_visual_review("demo", main.VisualReviewSubmission(
            preview_sha256="old", pages=[page]))
    with pytest.raises(main.HTTPException, match="every slide"):
        main.register_layout_visual_review("demo", main.VisualReviewSubmission(
            preview_sha256="exact-deck", pages=[]))
    record = main.register_layout_visual_review("demo", main.VisualReviewSubmission(
        preview_sha256="exact-deck", pages=[page]))
    assert record["pages"] == [{"page_id": "p1", "verdict": "REVISE", "concerns": ["层级不足"]}]
    assert record["adapter_id"] == "operator-model:submitted"


def test_layout_cycle_retries_only_pages_flagged_by_visual_review(monkeypatch):
    from app import main

    deck = sample_deck()
    calls = []
    monkeypatch.setattr(main, "run_layout_design", lambda project_id, request: (
        calls.append(("design", request.page_ids)) or
        {"layout_ir": focus_proposal(deck)}))
    verdicts = ["REVISE", "PASS"]
    monkeypatch.setattr(main, "run_layout_visual_review", lambda project_id, request: (
        calls.append(("review", request.page_ids)) or
        {"pages": [{"page_id": "p1", "verdict": verdicts.pop(0), "concerns": []}]}))
    result = main.run_layout_cycle("demo", main.LayoutCycleRequest(page_ids=["p1"], max_rounds=2))
    assert result["status"] == "ADVISORY_VISUAL_PASS"
    assert len(result["rounds"]) == 2
    assert calls == [("design", ["p1"]), ("review", None),
                     ("design", ["p1"]), ("review", None)]


def test_model_layout_round_trip_keeps_native_claims_and_sources(tmp_path):
    deck = sample_deck()
    ir = focus_proposal(deck)
    output_dir = tmp_path
    target = output_dir / "focus.pptx"
    build_pptx(deck, target, layout_ir=ir, mark_operation=False)
    result = verify_pptx(deck, target, layout_ir=ir)
    assert result["status"] == "PASS"
    assert result["native_editable"] is True
    assert result["selected_archetypes"] == ["FOCUS_EVIDENCE"]


def test_focus_evidence_cannot_promote_a_later_claim():
    """Focusing Claim 3 would render a page that reads in a different order than approved."""
    deck = focusable_deck()
    with pytest.raises(LayoutIntentError, match="first approved Claim"):
        validate_layout_ir(deck, focus_proposal_for(deck, "c3"))


#: Wraps into two lines with no text-frame inset, three lines with the DrawingML
#: default inset -- the wrap-boundary case that put slide text on top of its own
#: provenance label in the real GOLD 2026 deck.
WRAP_BOUNDARY_CLAIM = "共病管理提出“多病协同”理念，采用4Ms评估框架；正式将人工智能与远程医疗技术纳入诊疗体系。"


def test_text_frame_inset_is_part_of_the_text_fit_check():
    text, width, font = WRAP_BOUNDARY_CLAIM, 538, 23
    naive = measure_text(text, width, font, horizontal_inset=0, vertical_inset=0)
    real = measure_text(text, width, font, horizontal_inset=TEXT_FRAME_INSET_HORIZONTAL,
                        vertical_inset=0)
    assert real["line_count"] > naive["line_count"], "fixture no longer sits on a wrap boundary"
    plan = {"pages": [{"page_id": "p1", "elements": [
        {"kind": "text", "name": "claim:c1", "text": text,
         "position": {"left": 88, "top": 100, "width": width, "height": naive["required_height"]},
         "style": {"fontSize": font}}]}]}
    report = assess_plan_text_fit(plan)
    assert report["status"] == "REVIEW"
    assert report["issues"][0]["object"] == "claim:c1"
    assert report["issues"][0]["required_height"] == real["required_height"]


def test_flex_claim_box_is_tall_enough_for_the_real_text_frame():
    deck = sample_deck()
    deck["pages"][0]["claims"][1]["normalized_claim"] = WRAP_BOUNDARY_CLAIM
    proposal = flex_proposal(deck)
    proposal["pages"][0]["layout_tree"] = {"kind": "row", "gap": 12, "children": [
        {"kind": "claim", "claim_id": "c1", "weight": 1},
        {"kind": "claim", "claim_id": "c2", "weight": 1}]}
    plan = compile_beautification_plan(deck, layout_ir=proposal)
    box = next(e for e in plan["pages"][0]["elements"] if e["name"] == "claim:c2")
    required = measure_text(box["text"], box["position"]["width"], box["style"]["fontSize"],
                            horizontal_inset=TEXT_FRAME_INSET_HORIZONTAL, vertical_inset=0)
    assert required["line_count"] == 3
    assert box["position"]["height"] >= required["required_height"]


def test_focus_evidence_focal_claim_reads_first_in_the_rendered_file(tmp_path):
    """With three support rows the focal block must stay in the first visual band."""
    deck = focusable_deck()
    ir = merge_layout_ir(deck, None, focus_proposal_for(deck, "c1"))
    plan = compile_beautification_plan(deck, layout_ir=ir)
    assert plan["text_fit"]["status"] == "PASS"
    output_dir = tmp_path
    target = output_dir / "focus-order.pptx"
    build_pptx(deck, target, layout_ir=ir, mark_operation=False)
    result = verify_pptx(deck, target, layout_ir=ir)
    assert result["status"] == "PASS", result["issues"]
    assert result["selected_archetypes"] == ["FOCUS_EVIDENCE"]


# --- a subtitle identical to the title is drawn once -------------------------------------
#
# The header renders `title` and `primary_message` as two separate text boxes. When the reading
# artifact declares the same string in both -- as run_ch06's artifact does on all 28 pages -- the
# page showed two identical lines, one bold and one grey. The compiler now draws the subtitle only
# when it says something the title does not.

REPEATED_HEADER = "本章学习主线"


def repeated_header_deck() -> dict:
    deck = sample_deck()
    deck["pages"][0]["title"] = REPEATED_HEADER
    deck["pages"][0]["primary_message"] = REPEATED_HEADER
    return deck


def test_a_subtitle_repeating_the_title_is_not_drawn_as_a_second_line():
    plan = compile_beautification_plan(repeated_header_deck())
    names = [element["name"] for element in plan["pages"][0]["elements"]]
    assert "title:p1" in names
    assert "primary:p1" not in names, "the repeated subtitle was drawn as a second identical line"


def test_a_distinct_subtitle_is_still_drawn():
    """The rule must not silence a subtitle that actually says something new."""
    deck = sample_deck()
    plan = compile_beautification_plan(deck)
    drawn = {element["name"]: element["text"] for element in plan["pages"][0]["elements"]}
    assert drawn["primary:p1"] == deck["pages"][0]["primary_message"]
    assert drawn["title:p1"] == deck["pages"][0]["title"]


def test_a_whitespace_only_difference_still_counts_as_the_same_line():
    deck = sample_deck()
    deck["pages"][0]["title"] = "本章 学习主线"
    deck["pages"][0]["primary_message"] = "本章学习主线"
    names = [element["name"] for element in compile_beautification_plan(deck)["pages"][0]["elements"]]
    assert "primary:p1" not in names


def test_dropping_the_repeated_subtitle_keeps_the_pptx_packager_satisfied(tmp_path):
    """`verify_pptx` requires both the title and the primary message in the page's visible text.

    Omitting the second box must not read as a missing primary message: the title carries the same
    string, so the packager's substring test still finds it -- once, not twice.
    """
    import zipfile

    deck = repeated_header_deck()
    output_dir = tmp_path
    target = output_dir / "repeated-header.pptx"
    build_pptx(deck, target, mark_operation=False)
    result = verify_pptx(deck, target)
    assert result["status"] == "PASS", result["issues"]
    with zipfile.ZipFile(target) as archive:
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
    assert slide_xml.count(REPEATED_HEADER) == 1, (
        f"the header text appears {slide_xml.count(REPEATED_HEADER)} times on the slide; "
        "it must appear exactly once")
