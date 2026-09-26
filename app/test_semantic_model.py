# -*- coding: utf-8 -*-
"""Semantic-act model route: qualification, egress, and deterministic validation.

The gateway exists to make three refusals possible, and each one is tested here:
an engine that is not qualified for a capability, an egress decision the project has
not declared, and model output that the deterministic validator rejects. A refusal
that cannot be observed is not a gate.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import main, semantic_model
from app.model_adapter import record_run, validate_egress_decision
from app.semantic_model import (SemanticGatewayError, build_payload, configured_semantic_model,
                               describe_capabilities, egress_plan, load_semantic_registry,
                               qualified_engine)

VENDOR_ENGINE = "openai_compatible_semantic"
OPERATOR_ENGINE = "operator_model_workflow"

LOOPBACK = {"url": "http://127.0.0.1:1234/v1/chat/completions", "model_id": "local-semantic",
            "external": False, "adapter_id": "openai-compatible:local-semantic", "provider": "local",
            "engine_id": VENDOR_ENGINE}
EXTERNAL = {"url": "https://api.example.com/v1/chat/completions", "model_id": "remote-semantic",
            "external": True, "adapter_id": "openai-compatible:remote-semantic", "provider": "external",
            "model_version": "deployment-declared", "engine_id": VENDOR_ENGINE}
SOURCE_TEXT = "纳入2021年全球疾病负担研究数据显示，全球慢阻肺病患病率为2.7%，较1990年下降1.46%。"


def qualified_registry(tmp_path: Path) -> Path:
    """The shipped registry with vendor qualification evidence attached.

    `EASYPPT_SEMANTIC_MODEL_ENGINE` pins the route to this engine, because the shipped
    registry also carries the qualified operator workflow: without pinning, the loopback
    operator engine would answer and these tests would measure the wrong engine's contract.
    """
    registry = load_semantic_registry()
    engine = registry["engines"][VENDOR_ENGINE]
    engine["qualification_status"] = "QUALIFIED"
    engine["qualification_basis"]["tested_at"] = "2026-09-13"
    engine["qualification_basis"]["evidence_refs"] = ["fixture-only"]
    target = tmp_path / "semantic_model_capabilities.json"
    target.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    return target


@pytest.fixture(autouse=True)
def pin_vendor_engine(monkeypatch):
    monkeypatch.setenv("EASYPPT_SEMANTIC_MODEL_ENGINE", VENDOR_ENGINE)


# ------------------------------------------------------------- registry and gate
def test_every_capability_names_a_deterministic_validator():
    """A capability whose output nothing checks would be a route with no gate."""
    registry = load_semantic_registry()
    for capability, contract in registry["capabilities"].items():
        assert contract["output_validated_by"], capability
        assert contract["egress_contract"]["allowed_fields"], capability
        assert contract["egress_contract"]["forbidden_fields"], capability


def test_unqualified_model_engine_is_refused_with_its_required_suite():
    """A vendor engine with no evidence is refused, and the operator engine does not
    launder that: the refusal names the engine that was actually asked for."""
    with pytest.raises(SemanticGatewayError, match="PENDING_QUALIFICATION"):
        qualified_engine("source_candidate_extraction", engine_id=VENDOR_ENGINE)
    with pytest.raises(SemanticGatewayError, match="SEMANTIC-ACT-QUALIFICATION-v0.1"):
        qualified_engine("source_candidate_extraction", engine_id=VENDOR_ENGINE)
    with pytest.raises(SemanticGatewayError, match="not present in the semantic capability registry"):
        qualified_engine("source_candidate_extraction", engine_id="no_such_engine")


def test_full_summary_is_declared_but_no_engine_is_silently_granted_it():
    registry = load_semantic_registry()
    assert "full_source_summary" in registry["capabilities"]
    with pytest.raises(SemanticGatewayError, match="does not declare full_source_summary"):
        qualified_engine("full_source_summary", registry, engine_id=OPERATOR_ENGINE)
    payload = build_payload("full_source_summary", {
        "reading_structure_sha256": "reading", "source_sha256": "source",
        "pages": [{"page": 1, "text": "原文", "source_block_ids": [3],
                   "private_review_notes": "must not leave"}]}, registry)
    assert payload["pages"] == [{"page": 1, "text": "原文", "source_block_ids": [3]}]
    assert "private_review_notes" not in json.dumps(payload)


def test_the_operator_workflow_is_qualified_and_cannot_reach_the_network():
    """The shipped operator engine is routable, but only over loopback.

    `external_data_egress=false` is what makes that true, so it is asserted rather than
    assumed: a qualified loopback engine must not become a licence to post patient source
    text to a public endpoint.
    """
    engine_id, engine = qualified_engine("source_candidate_extraction",
                                         engine_id="operator_model_workflow")
    assert engine_id == "operator_model_workflow"
    assert engine["external_data_egress"] is False
    assert engine["qualification_basis"]["evidence_refs"], "qualification must carry evidence"
    project = main.Project(title="demo", presentation_question="更新有哪些？")
    project.allow_source_text_egress = True
    project.source_text_egress_policy = "FULL_TEXT"
    with pytest.raises(SemanticGatewayError, match="not approved for external data egress"):
        egress_plan(project, "source_candidate_extraction",
                    {"url": "https://api.example.com/v1/chat/completions", "model_id": "remote",
                     "external": True, "engine_id": "operator_model_workflow",
                     "adapter_id": "openai-compatible:remote"})


def test_unknown_capability_is_refused_before_any_permission_question():
    with pytest.raises(SemanticGatewayError, match="Unknown semantic capability"):
        egress_plan(main.Project(title="demo", presentation_question="更新有哪些？"),
                    "summarize_everything", LOOPBACK)


def test_loopback_endpoint_runs_without_an_egress_declaration(tmp_path, monkeypatch):
    monkeypatch.setattr(semantic_model, "REGISTRY_PATH", qualified_registry(tmp_path))
    project = main.Project(title="demo", presentation_question="更新有哪些？")
    plan = egress_plan(project, "source_candidate_extraction", LOOPBACK)
    assert plan["decision"] == "LOOPBACK_NO_EGRESS"
    assert plan["external"] is False


def test_source_reading_off_machine_requires_its_own_declaration(tmp_path, monkeypatch):
    monkeypatch.setattr(semantic_model, "REGISTRY_PATH", qualified_registry(tmp_path))
    project = main.Project(title="demo", presentation_question="更新有哪些？")
    with pytest.raises(SemanticGatewayError, match="allow_source_text_egress"):
        egress_plan(project, "source_candidate_extraction", EXTERNAL)
    project.allow_source_text_egress = True
    with pytest.raises(SemanticGatewayError, match="source_text_egress_policy"):
        egress_plan(project, "source_candidate_extraction", EXTERNAL)
    project.source_text_egress_policy = "FULL_TEXT"
    plan = egress_plan(project, "source_candidate_extraction", EXTERNAL)
    assert plan["decision"] == "EGRESS_APPROVED"
    assert plan["requires_source_text"] is True


def test_external_generation_policy_does_not_authorise_source_reading(tmp_path, monkeypatch):
    """A design-brief permission must not double as a patient-document permission."""
    monkeypatch.setattr(semantic_model, "REGISTRY_PATH", qualified_registry(tmp_path))
    project = main.Project(title="demo", presentation_question="更新有哪些？", allow_external_generation=True,
                           generation_data_egress_policy="CONTRACT_MINIMIZED")
    with pytest.raises(SemanticGatewayError, match="allow_source_text_egress"):
        egress_plan(project, "source_candidate_extraction", EXTERNAL)
    assert egress_plan(project, "triage", EXTERNAL)["decision"] == "EGRESS_APPROVED"


def test_digest_capability_requires_minimised_generation_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(semantic_model, "REGISTRY_PATH", qualified_registry(tmp_path))
    project = main.Project(title="demo", presentation_question="更新有哪些？", allow_external_generation=True,
                           generation_data_egress_policy="EDITORIAL_ONLY")
    with pytest.raises(SemanticGatewayError, match="CONTRACT_MINIMIZED"):
        egress_plan(project, "triage", EXTERNAL)


def test_payload_allowlist_drops_fields_outside_the_contract():
    payload = build_payload("triage", {
        "presentation_question": "更新有哪些？", "audience": "科室主任", "duration_minutes": 15,
        "claims": [{"claim_id": "c1", "claim_text": "证据", "provenance": "SOURCE", "risk": "GREEN",
                    "conditions": [], "patient_identifiers": ["张三"], "raw_source_text": "全文"}]})
    claim = payload["claims"][0]
    assert "patient_identifiers" not in claim and "raw_source_text" not in claim
    assert claim["claim_id"] == "c1"


def test_configured_endpoint_rejects_plain_http_when_external(monkeypatch):
    monkeypatch.setenv("EASYPPT_SEMANTIC_MODEL_URL", "http://api.example.com/v1/chat/completions")
    monkeypatch.setenv("EASYPPT_SEMANTIC_MODEL_ID", "remote")
    with pytest.raises(SemanticGatewayError, match="loopback HTTP or HTTPS"):
        configured_semantic_model()
    monkeypatch.delenv("EASYPPT_SEMANTIC_MODEL_URL")
    monkeypatch.delenv("EASYPPT_SEMANTIC_MODEL_ID")
    assert configured_semantic_model() is None


def test_audit_record_refuses_external_without_an_egress_decision():
    with pytest.raises(ValueError, match="data-egress decision"):
        record_run("source_extractor", {"a": 1}, {"b": 2}, adapter=EXTERNAL)
    with pytest.raises(ValueError, match="incomplete"):
        record_run("source_extractor", {"a": 1}, {"b": 2}, adapter=EXTERNAL,
                   egress={"capability": "source_candidate_extraction"})
    good = {"capability": "source_candidate_extraction", "decision": "EGRESS_APPROVED",
            "payload_sha256": "0" * 64, "payload_bytes": 10}
    assert validate_egress_decision(good)["decision"] == "EGRESS_APPROVED"
    assert record_run("source_extractor", {"a": 1}, {"b": 2}, adapter=EXTERNAL, egress=good)["external"] is True


def test_capability_view_reports_the_blocker_without_a_qualified_engine(tmp_path, monkeypatch):
    """With every model engine unqualified the audit view must say so, per capability."""
    registry = load_semantic_registry()
    for engine in registry["engines"].values():
        if engine.get("execution_kind") == "MODEL_PIPELINE":
            engine["qualification_status"] = "PENDING_QUALIFICATION"
            engine["qualification_basis"]["evidence_refs"] = []
    target = tmp_path / "unqualified.json"
    target.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(semantic_model, "REGISTRY_PATH", target)
    described = describe_capabilities()
    assert described["capabilities"]
    for row in described["capabilities"]:
        assert row["model_route_status"] == "BLOCKED"
        blocker = row["model_route_blocker"].lower()
        assert "qualification" in blocker or "does not declare" in blocker


# --------------------------------------------------- model output under validation
def project_with_one_page() -> main.Project:
    project = main.Project(title="demo", presentation_question="GOLD 2026 有哪些更新？",
                           project_goal="科内解读", duration_minutes=15)
    project.documents = [{"id": "doc1", "extractor_version": "source_extract.v1",
                          "coverage_status": "COMPLETE",
                          "chunks": [{"page": 1, "text": SOURCE_TEXT}]}]
    project.workflow_state = "UPLOADED"
    return project


def test_model_reading_accepts_a_grounded_quote_and_derives_the_rest(monkeypatch):
    project = project_with_one_page()
    monkeypatch.setattr(main, "call_semantic_model", lambda capability, payload, model: {
        "units": [{"page": 1, "status": "HAS_CANDIDATES"}],
        "candidates": [{"page": 1, "quote": "全球慢阻肺病患病率为2.7%，较1990年下降1.46%",
                        "claim": "全球慢阻肺病患病率为2.7%，较1990年下降1.46%"}]})
    claims, meta = main.extract_candidates_with_model(project, "doc1", {"model": LOOPBACK})
    assert len(claims) == 1 and meta["accepted"] == 1 and meta["rejected"] == []
    assert meta["read_completeness"]["tokens_unaccounted"] == 0
    claim = claims[0]
    assert claim.provenance == "SOURCE" and claim.review_status == "NEEDS_HUMAN_REVIEW"
    assert claim.risk in {"GREEN", "YELLOW", "RED"}
    assert claim.numeric_facts, "numeric facts are derived by code, not requested from the model"


def test_a_reading_that_returns_no_unit_receipts_is_refused(monkeypatch):
    """Reported failure: a reading used to count as complete by returning *some* candidate,
    so eleven values on a real eleven-page paper were never extracted and nothing noticed."""
    project = project_with_one_page()
    monkeypatch.setattr(main, "call_semantic_model", lambda capability, payload, model: {
        "candidates": [{"page": 1, "quote": "患病率为2.7%", "claim": "全球慢阻肺病患病率为2.7%"}]})
    with pytest.raises(main.HTTPException) as error:
        main.extract_candidates_with_model(project, "doc1", {"model": LOOPBACK})
    assert "READ_RECEIPTS_MISSING" in str(error.value.detail)


def test_a_meaning_critical_value_left_unaccounted_blocks_the_reading(monkeypatch):
    """Reported failure: dropping a threshold or a magnitude figure was invisible."""
    project = project_with_one_page()
    monkeypatch.setattr(main, "call_semantic_model", lambda capability, payload, model: {
        "units": [{"page": 1, "status": "HAS_CANDIDATES"}],
        "candidates": [{"page": 1, "quote": "全球慢阻肺病患病率为2.7%",
                        "claim": "全球慢阻肺病患病率为2.7%"}]})
    with pytest.raises(main.HTTPException) as error:
        main.extract_candidates_with_model(project, "doc1", {"model": LOOPBACK})
    detail = error.value.detail
    assert detail["read_completeness"]["tokens_unaccounted"] == 1
    assert any(issue.get("token") == "1.46%" for issue in detail["issues"])


def test_an_excluded_value_with_a_stated_reason_is_accepted(monkeypatch):
    project = project_with_one_page()
    monkeypatch.setattr(main, "call_semantic_model", lambda capability, payload, model: {
        "units": [{"page": 1, "status": "HAS_CANDIDATES",
                   "exclusions": [{"token": "1.46%",
                                   "reason": "CONTEXT_ONLY_NOT_A_FINDING"}]}],
        "candidates": [{"page": 1, "quote": "全球慢阻肺病患病率为2.7%",
                        "claim": "全球慢阻肺病患病率为2.7%"}]})
    claims, meta = main.extract_candidates_with_model(project, "doc1", {"model": LOOPBACK})
    assert len(claims) == 1 and meta["read_completeness"]["tokens_excluded"] == 1


def test_model_reading_discards_ungrounded_quotes(monkeypatch):
    project = project_with_one_page()
    monkeypatch.setattr(main, "call_semantic_model", lambda capability, payload, model: {
        "candidates": [{"page": 1, "quote": "全球患病率高达99.9%", "claim": "全球患病率高达99.9%"},
                       {"page": 9, "quote": SOURCE_TEXT, "claim": "引用了不存在的页"}]})
    with pytest.raises(main.HTTPException, match="no quote-grounded candidate"):
        main.extract_candidates_with_model(project, "doc1", {"model": LOOPBACK})


def test_model_reading_keeps_the_grounded_candidate_and_reports_the_rest(monkeypatch):
    project = project_with_one_page()
    monkeypatch.setattr(main, "call_semantic_model", lambda capability, payload, model: {
        "units": [{"page": 1, "status": "HAS_CANDIDATES"}],
        "candidates": [{"page": 1, "quote": "全球慢阻肺病患病率为2.7%，较1990年下降1.46%",
                        "claim": "全球慢阻肺病患病率为2.7%，较1990年下降1.46%"},
                       {"page": 1, "quote": "原文并未出现的句子", "claim": "模型编造的一条结论"}]})
    claims, meta = main.extract_candidates_with_model(project, "doc1", {"model": LOOPBACK})
    assert len(claims) == 1
    assert meta["rejected"][0]["reason"] == "quote is not in the cited page text"


def triageable_project() -> main.Project:
    project = main.Project(title="demo", presentation_question="更新有哪些？", duration_minutes=15)
    project.claims = [
        main.Claim(normalized_claim="更新一：接种人群年龄下限下调", provenance="SOURCE", risk="GREEN"),
        main.Claim(normalized_claim="更新二：纳入 mRNA 疫苗", provenance="SOURCE", risk="GREEN"),
    ]
    return project


def test_model_triage_must_decide_every_claim_exactly_once(monkeypatch):
    project = triageable_project()
    first = project.claims[0].id
    monkeypatch.setattr(main, "call_semantic_model", lambda capability, payload, model: {
        "decisions": [{"claim_id": first, "bucket": "MUST_INCLUDE", "reason": "核心更新"}]})
    with pytest.raises(main.HTTPException, match="every Claim exactly once"):
        main.triage_with_model(project, {"model": LOOPBACK})


def test_model_triage_keeps_budget_and_score_in_code(monkeypatch):
    project = triageable_project()
    first, second = (claim.id for claim in project.claims)
    monkeypatch.setattr(main, "call_semantic_model", lambda capability, payload, model: {
        "decisions": [{"claim_id": first, "bucket": "MUST_INCLUDE", "reason": "核心更新"},
                      {"claim_id": second, "bucket": "APPENDIX", "reason": "补充"}]})
    decisions, meta = main.triage_with_model(project, {"model": LOOPBACK})
    assert meta["decisions"] == 2
    must = next(item for item in decisions if item.bucket == "MUST_INCLUDE")
    assert must.presentation_cost_seconds > 0
    assert must.reason.startswith("[model]")
    assert project.claims[1].triage == "APPENDIX"


def architectable_project() -> main.Project:
    project = main.Project(title="demo", presentation_question="更新有哪些？", duration_minutes=15)
    project.claims = [
        main.Claim(normalized_claim="更新一：接种人群年龄下限下调", provenance="SOURCE", risk="GREEN", triage="MUST_INCLUDE"),
        main.Claim(normalized_claim="更新二：纳入 mRNA 疫苗", provenance="SOURCE", risk="GREEN", triage="MUST_INCLUDE"),
    ]
    return project


def page_payload(claim_ids: list[str]) -> dict:
    return {"narrative_spine": "两条更新共同改变接种建议",
            "pages": [{"page_id": "p1", "title": "接种建议的两处更新", "primary_message": "人群与选择都有变化",
                       "claim_ids": claim_ids, "why_this_page": "回答接种建议改了什么",
                       "figure_intent": "COMPARISON"}]}


def test_model_allocation_cannot_drop_a_claim(monkeypatch):
    project = architectable_project()
    monkeypatch.setattr(main, "call_semantic_model",
                        lambda capability, payload, model: page_payload([project.claims[0].id]))
    with pytest.raises(main.HTTPException, match="exactly once"):
        main.architect_with_model(project, {"model": LOOPBACK})


def test_model_allocation_cannot_exceed_page_capacity(monkeypatch):
    project = architectable_project()
    monkeypatch.setattr(main, "call_semantic_model", lambda capability, payload, model: {
        "narrative_spine": "spine",
        "pages": [{"page_id": "p1", "title": "t", "primary_message": "m",
                   "claim_ids": ["c1", "c2", "c3", "c4", "c5"], "why_this_page": "w",
                   "figure_intent": "NONE"}]})
    with pytest.raises(main.HTTPException, match="capacity of four Claims"):
        main.architect_with_model(project, {"model": LOOPBACK})


def test_model_allocation_records_why_and_intent_on_the_page(monkeypatch):
    project = architectable_project()
    claim_ids = [claim.id for claim in project.claims]
    monkeypatch.setattr(main, "call_semantic_model",
                        lambda capability, payload, model: page_payload(claim_ids))
    plan, pages, meta = main.architect_with_model(project, {"model": LOOPBACK})
    assert meta["pages"] == 1
    assert pages[0].claim_ids == claim_ids
    assert "figure_intent=COMPARISON" in pages[0].goal
    assert "回答接种建议改了什么" in pages[0].goal
    assert pages[0].visual_type == main.FIGURE_INTENT_VISUALS["COMPARISON"]
    assert plan.sections


def test_model_allocation_rejects_an_unknown_figure_intent(monkeypatch):
    project = architectable_project()
    claim_ids = [claim.id for claim in project.claims]
    payload = page_payload(claim_ids)
    payload["pages"][0]["figure_intent"] = "MINDMAP"
    monkeypatch.setattr(main, "call_semantic_model", lambda capability, payload_, model: payload)
    with pytest.raises(main.HTTPException, match="unknown figure_intent"):
        main.architect_with_model(project, {"model": LOOPBACK})


# ----------------------------------------------------------------- endpoint wire
def test_extract_endpoint_records_the_engine_and_its_egress_decision(tmp_path, monkeypatch):
    monkeypatch.setattr(semantic_model, "REGISTRY_PATH", qualified_registry(tmp_path))
    project = project_with_one_page()
    monkeypatch.setattr(main, "get_project", lambda project_id: ([project], project))
    monkeypatch.setattr(main, "save_projects", lambda value: None)
    monkeypatch.setattr(main, "configured_semantic_model", lambda: LOOPBACK)
    monkeypatch.setattr(main, "call_semantic_model", lambda capability, payload, model: {
        "units": [{"page": 1, "status": "HAS_CANDIDATES"}],
        "candidates": [{"page": 1, "quote": "全球慢阻肺病患病率为2.7%，较1990年下降1.46%",
                        "claim": "全球慢阻肺病患病率为2.7%，较1990年下降1.46%"}]})
    result = main.extract_project_claims("demo", main.PipelineRequest())
    assert result["count"] == 1
    assert result["reading"]["engine"] == "openai_compatible_semantic"
    assert result["reading"]["read_completeness"]["units"] == 1
    run = project.model_runs[-1]
    assert run["adapter_id"] == LOOPBACK["adapter_id"]
    assert run["external"] is False
    assert run["data_egress"]["decision"] == "LOOPBACK_NO_EGRESS"


def test_extract_endpoint_falls_back_when_no_endpoint_is_configured(monkeypatch):
    project = project_with_one_page()
    monkeypatch.setattr(main, "get_project", lambda project_id: ([project], project))
    monkeypatch.setattr(main, "save_projects", lambda value: None)
    monkeypatch.setattr(main, "configured_semantic_model", lambda: None)
    result = main.extract_project_claims("demo", main.PipelineRequest())
    assert result["reading"]["engine"] == "local_deterministic"
    assert project.model_runs[-1]["external"] is False
    assert "data_egress" not in project.model_runs[-1]


def test_extract_endpoint_surfaces_a_refused_route_instead_of_downgrading(tmp_path, monkeypatch):
    """A configured but unqualified route must fail the stage, not quietly use the rule engine."""
    project = project_with_one_page()
    monkeypatch.setattr(main, "get_project", lambda project_id: ([project], project))
    monkeypatch.setattr(main, "save_projects", lambda value: None)
    monkeypatch.setattr(main, "configured_semantic_model", lambda: LOOPBACK)
    with pytest.raises(main.HTTPException, match="route refused"):
        main.extract_project_claims("demo", main.PipelineRequest())
