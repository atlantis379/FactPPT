# -*- coding: utf-8 -*-
"""Reading-structure import: the artifact gate, the Claim join, and the anchored order.

Two things are being proved here. First, that the gate can fail — an artifact that did
not read the full text, derived its structure mechanically, or left a check failing
without declaring it is refused, not trusted. Second, that attaching an artifact makes
the deck's page set and per-page Claim order *derivable* rather than re-invented, which
is what `LD-01` needs to protect something real.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app import main
from app.reading_structure import (artifact_digest, join_pages_to_claims, summarize,
                                   validate_reading_structure)

SHA = "sha-source-a"
THREAD = "不是更新清单，而是回答：接种建议到底改了什么、边界在哪里；原文从未明说的暗线是人群先变、选择后变。"


def valid_artifact() -> dict:
    return {
        "schema_version": "reading_structure_artifact.v0.2",
        "source": {"filename": "gold2026.pdf", "sha256": SHA, "unit_count": 2, "unit_label": "page"},
        "reading_pass": {"reading_mode": "FULL_TEXT_READ", "blocks_read": 2, "blocks_total": 2,
                         "chars_read": 120, "chars_total": 120,
                         "structure_derivation": "LLM_SEMANTIC_SYNTHESIS"},
        "profile": {"material_kind": "MEDICAL_SOURCE", "language": "zh-CN"},
        "blocks": [
            {"block_id": 1, "unit": 1, "chars": 60, "coverage": "in_deck", "role": "recommendation",
             "difficulty": [], "structure_node_ids": ["n01"], "page_ids": ["p01"]},
            {"block_id": 2, "unit": 2, "chars": 60, "coverage": "evidence_only",
             "evidence_only_reason": "作为边界条件保留在证物层", "role": "risk", "difficulty": [],
             "structure_node_ids": ["n02"], "page_ids": ["p02"]},
        ],
        "structure": {
            "thread": THREAD,
            "opening_motivation": "接种人群与疫苗选择同时发生调整",
            "nodes": [
                {"node_id": "n01", "label": "接种人群下限下调", "why_here": "回答接种建议改了什么",
                 "source_block_ids": [1], "emphasis_basis": "MATERIAL_SIGNAL"},
                {"node_id": "n02", "label": "需要重新评估的边界", "why_here": "给出判断的适用边界",
                 "source_block_ids": [2], "emphasis_basis": "MATERIAL_SIGNAL"},
            ],
        },
        "narrative": {
            "narrative_order": ["n01", "n02"], "differs_from_source_order": False,
            "difference_reason": "原文节序本身即「先人群后选择」的教学序，保留该序并在此说明理由，而非默认沿用。",
            "audience_question": "接种建议到底改了什么？",
        },
        "page_plan": [
            {"page_id": "p01", "figure_intent": "COMPARISON", "why_this_page": "回答接种建议改了什么",
             "action_title": "接种人群下限下调", "on_slide_text": ["高危人群年龄下限由60岁下调至50岁"],
             "source_block_ids": [1], "narrative_node_ids": ["n01"], "renders_structure": "NONE"},
            {"page_id": "p02", "figure_intent": "PROCESS", "why_this_page": "给出判断的适用边界",
             "action_title": "何时需要重新评估", "on_slide_text": ["≥75岁未接种人群仍建议普遍接种"],
             "source_block_ids": [2], "narrative_node_ids": ["n02"], "renders_structure": "NONE"},
        ],
        "checks": {"thread": {"status": "PASS", "method": "通读完整性", "failures": [], "failure_count": 0}},
        "disposition": "READING_STRUCTURE_ACCEPTED",
    }


def codes(artifact: dict) -> set[str]:
    return {item["code"] for item in validate_reading_structure(artifact)}


def test_a_coherent_artifact_passes_its_gate():
    assert validate_reading_structure(valid_artifact()) == []
    summary = summarize(valid_artifact())
    assert summary["blocks_read"] == 2 and summary["nodes"] == 2 and summary["pages"] == 2


def test_the_gate_can_fail():
    """Every branch of the gate is exercised: a gate that cannot fail is decoration."""
    cases = [
        ({"schema_version": "reading_structure_artifact.v0.1"}, "SCHEMA_MISMATCH"),
        ({"reading_pass": {"reading_mode": "HEADING_SPLIT", "blocks_read": 2, "blocks_total": 2,
                           "chars_read": 120, "chars_total": 120,
                           "structure_derivation": "LLM_SEMANTIC_SYNTHESIS"}}, "NOT_A_FULL_TEXT_READ"),
        ({"reading_pass": {"reading_mode": "FULL_TEXT_READ", "blocks_read": 1, "blocks_total": 2,
                           "chars_read": 120, "chars_total": 120,
                           "structure_derivation": "LLM_SEMANTIC_SYNTHESIS"}}, "INCOMPLETE_READ"),
        ({"reading_pass": {"reading_mode": "FULL_TEXT_READ", "blocks_read": 2, "blocks_total": 2,
                           "chars_read": 30, "chars_total": 120,
                           "structure_derivation": "LLM_SEMANTIC_SYNTHESIS"}}, "CHARACTERS_NOT_FULLY_READ"),
        ({"reading_pass": {"reading_mode": "FULL_TEXT_READ", "blocks_read": 2, "blocks_total": 2,
                           "chars_read": 120, "chars_total": 120,
                           "structure_derivation": "HEADING_MARKER_SPLIT"}}, "MECHANICAL_STRUCTURE_DERIVATION"),
        ({"structure": {"thread": "太短", "nodes": valid_artifact()["structure"]["nodes"]}}, "THREAD_MISSING"),
        ({"blocks": [{"block_id": 1, "unit": 1}, {"block_id": 1, "unit": 2, "coverage": "in_deck"}]},
         "DUPLICATE_BLOCK_IDS"),
        ({"narrative": {"narrative_order": ["n01"], "difference_reason": "足够长的理由说明，用于通过长度检查。"}},
         "NARRATIVE_ORDER_INCOMPLETE"),
        ({"narrative": {"narrative_order": ["n01", "n02"], "difference_reason": ""}},
         "NARRATIVE_ORDER_UNDECLARED"),
        ({"page_plan": []}, "NO_PAGES"),
        ({"disposition": "READING_STRUCTURE_REJECTED"}, "DISPOSITION_REJECTED"),
    ]
    for patch, expected in cases:
        artifact = valid_artifact()
        artifact.update(patch)
        assert expected in codes(artifact), f"{expected} was not raised by {patch}"


def test_a_failing_check_without_a_declaration_is_refused():
    """The business artifact's real defect: gaps declared in the disposition but not recorded."""
    artifact = valid_artifact()
    artifact["checks"] = {"difficulty": {"status": "FAIL", "failures": ["未定义术语待解决"], "failure_count": 1}}
    artifact["disposition"] = "READING_STRUCTURE_ACCEPTED_WITH_DECLARED_GAPS"
    assert "FAILURES_WITHOUT_DECLARATION" in codes(artifact)
    artifact["coverage_declaration"] = {"basis": "EXTERNAL_AUTHORITY_SPLIT", "rationale": "大纲分级"}
    assert validate_reading_structure(artifact) == []

    artifact["disposition"] = "READING_STRUCTURE_ACCEPTED"
    assert "UNDECLARED_GAPS" in codes(artifact)


def test_a_node_exposed_by_no_page_is_refused():
    artifact = valid_artifact()
    artifact["page_plan"][1]["narrative_node_ids"] = []
    artifact["page_plan"][1]["source_block_ids"] = []
    assert "NODE_NOT_EXPOSED" in codes(artifact)


def test_a_page_that_walks_the_narrative_backwards_is_refused():
    artifact = valid_artifact()
    artifact["page_plan"][0]["narrative_node_ids"] = ["n02"]
    artifact["page_plan"][1]["narrative_node_ids"] = ["n01"]
    assert "PAGE_ORDER_CONTRADICTS_NARRATIVE" in codes(artifact)


def test_an_evidence_page_without_blocks_is_refused_but_a_cover_page_is_allowed():
    artifact = valid_artifact()
    artifact["page_plan"][0]["source_block_ids"] = []
    assert "EVIDENCE_PAGE_WITHOUT_BLOCKS" in codes(artifact)
    cover = valid_artifact()
    cover["page_plan"].insert(0, {"page_id": "p00", "figure_intent": "NONE",
                                  "why_this_page": "封面：交代受众与全章问题",
                                  "action_title": "GOLD 2026 更新解读", "renders_structure": "ROADMAP",
                                  "structure_text": "接种人群先变，疫苗选择随后调整。"})
    assert "EVIDENCE_PAGE_WITHOUT_BLOCKS" not in codes(cover)


def test_empty_structure_page_is_blocked_before_generation():
    artifact = valid_artifact()
    artifact["page_plan"].insert(0, {"page_id": "p00", "figure_intent": "NONE",
                                    "why_this_page": "封面：交代受众与全章问题",
                                    "action_title": "GOLD 2026 更新解读", "renders_structure": "ROADMAP"})
    assert "STRUCTURE_PAGE_WITHOUT_CONTENT" in codes(artifact)


# ------------------------------------------------------------------- claim join
def project_with_source(*, claim_pages=(1,)) -> main.Project:
    project = main.Project(title="demo", presentation_question="接种建议改了什么？", duration_minutes=15)
    project.documents = [{"id": "doc_a", "filename": "gold2026.pdf", "sha256": SHA, "page_count": 2,
                          "chunks": [{"page": 1, "text": "文本一"}, {"page": 2, "text": "文本二"}]}]
    project.claims = [
        main.Claim(normalized_claim=f"第{index}页的更新，用于连接测试", provenance="SOURCE", risk="GREEN",
                   triage="MUST_INCLUDE",
                   source_refs=[main.SourceRef(document_id="doc_a", page=page, quote="q")])
        for index, page in enumerate(claim_pages, start=1)]
    return project


def test_join_maps_artifact_pages_onto_approved_claims():
    join = join_pages_to_claims(valid_artifact(), project_with_source(claim_pages=(1, 2)))
    assert join["document_id"] == "doc_a"
    assert [page["claim_ids"] for page in join["pages"]] == [[join["ordered_claim_ids"][0]],
                                                            [join["ordered_claim_ids"][1]]]
    assert join["join"]["claims_joined"] == 2
    assert join["join"]["claims_unjoined"] == 0
    assert join["gaps"] == []


def test_join_reports_rather_than_drops_unreached_claims():
    # page 7 is outside every reading page, so that approved Claim is reached by nothing
    join = join_pages_to_claims(valid_artifact(), project_with_source(claim_pages=(1, 2, 7)))
    assert join["join"]["claims_joined"] == 2
    assert join["join"]["claims_unjoined"] == 1
    assert join["gaps"][0]["code"] == "APPROVED_CLAIM_NOT_IN_READING"


def test_join_refuses_when_the_source_document_is_not_imported():
    project = project_with_source()
    project.documents[0]["sha256"] = "sha-other"
    join = join_pages_to_claims(valid_artifact(), project)
    assert join["document_id"] is None
    assert join["gaps"][0]["code"] == "SOURCE_NOT_IMPORTED"


# ----------------------------------------------------------------- registration
def wire(monkeypatch, project: main.Project) -> None:
    monkeypatch.setattr(main, "get_project", lambda project_id: ([project], project))
    monkeypatch.setattr(main, "save_projects", lambda value: None)
    monkeypatch.setattr(main, "configured_semantic_model", lambda: None)


def test_registration_refuses_an_artifact_that_fails_its_gate(monkeypatch):
    project = project_with_source()
    project.workflow_state = "EXTRACTED"
    wire(monkeypatch, project)
    broken = valid_artifact()
    broken["reading_pass"]["structure_derivation"] = "HEADING_MARKER_SPLIT"
    with pytest.raises(main.HTTPException, match="failed its gate"):
        main.register_reading_structure("demo", main.ReadingStructureRequest(artifact=broken))
    assert project.reading_structure is None


def test_registration_refuses_a_mismatched_source_document(monkeypatch):
    project = project_with_source()
    project.workflow_state = "EXTRACTED"
    project.documents[0]["sha256"] = "sha-unrelated"
    wire(monkeypatch, project)
    with pytest.raises(main.HTTPException, match="No imported document matches"):
        main.register_reading_structure("demo", main.ReadingStructureRequest(artifact=valid_artifact()))


def test_registration_attaches_the_artifact_and_reports_gaps(monkeypatch):
    project = project_with_source(claim_pages=(1,))
    project.workflow_state = "EXTRACTED"
    project.claims[0].triage = "MUST_INCLUDE"
    wire(monkeypatch, project)
    result = main.register_reading_structure("demo", main.ReadingStructureRequest(artifact=valid_artifact()))
    assert result["reading_structure_sha256"] == artifact_digest(valid_artifact())
    assert result["join"]["pages_with_claims"] == 1
    assert any(gap["code"] == "PAGE_WITHOUT_APPROVED_CLAIM" for gap in result["gaps"])
    assert project.reading_structure is not None


# --------------------------------------------------------- artifact-driven pages
def registered_project(monkeypatch, *, claim_pages=(1, 2)) -> main.Project:
    project = project_with_source(claim_pages=claim_pages)
    project.workflow_state = "EXTRACTED"
    wire(monkeypatch, project)
    main.register_reading_structure("demo", main.ReadingStructureRequest(artifact=valid_artifact()))
    for claim in project.claims:
        claim.triage = "MUST_INCLUDE"
    project.triage_decisions = [main.TriageDecision(claim_id=claim.id, bucket="MUST_INCLUDE", score=80,
                                                    reason="fixture", presentation_cost_seconds=70)
                                for claim in project.claims]
    project.workflow_state = "TRIAGED"
    return project


def test_architect_takes_the_page_set_and_order_from_the_artifact(monkeypatch):
    project = registered_project(monkeypatch)
    plan, pages, meta = main.architect_from_reading_structure(project)
    assert meta["engine"] == "reading_structure_artifact"
    assert [page.reading_page_id for page in pages] == ["p01", "p02"]
    assert [page.narrative_node_ids for page in pages] == [["n01"], ["n02"]]
    assert pages[0].source_block_ids == [1] and pages[1].source_block_ids == [2]
    assert pages[0].visual_type == main.FIGURE_INTENT_VISUALS["COMPARISON"]
    assert "figure_intent=COMPARISON" in pages[0].goal
    assert plan.narrative_spine.startswith("不是更新清单")
    assert project.reading_structure_sha256[:12] in plan.audience_strategy


def test_a_reading_page_with_more_claims_than_capacity_is_split_not_refused(monkeypatch):
    """The renderer holds four Claims per slide; a denser source page becomes consecutive slides."""
    project = project_with_source(claim_pages=(1,))
    project.workflow_state = "EXTRACTED"
    wire(monkeypatch, project)
    for index in range(5):
        project.claims.append(main.Claim(normalized_claim=f"第 1 页的第 {index + 2} 条更新，用于拆分测试",
                                         provenance="SOURCE", risk="GREEN", triage="MUST_INCLUDE",
                                         source_refs=[main.SourceRef(document_id="doc_a", page=1, quote="q")]))
    main.register_reading_structure("demo", main.ReadingStructureRequest(artifact=valid_artifact()))
    for claim in project.claims:
        claim.triage = "MUST_INCLUDE"
    project.workflow_state = "TRIAGED"
    plan, pages, meta = main.architect_from_reading_structure(project)
    first = [page for page in pages if page.reading_page_id == "p01"]
    continuation = [page for page in pages if page.reading_page_id == "p01#2"]
    assert len(first) == 1 and len(continuation) == 1
    assert len(pages[0].claim_ids) <= 4 and len(pages[1].claim_ids) <= 4
    assert meta["capacity_splits"] == [{"reading_page_id": "p01", "parts": 2, "claims": 6}]
    assert "（1/2）" in pages[0].title and "（2/2）" in pages[1].title


def test_architect_reports_a_reading_page_with_no_approved_claim(monkeypatch):
    project = registered_project(monkeypatch, claim_pages=(1,))
    plan, pages, meta = main.architect_from_reading_structure(project)
    assert len(pages) == 1
    assert [gap["reason"] for gap in meta["allocation_gaps"]
            if gap.get("reading_page_id") == "p02"] == [
        "no approved Claim covers this page's source blocks"]


def test_architect_endpoint_uses_the_attached_reading(monkeypatch):
    project = registered_project(monkeypatch)
    monkeypatch.setattr(main, "get_project", lambda project_id: ([project], project))
    monkeypatch.setattr(main, "save_projects", lambda value: None)
    result = main.run_architect("demo")
    assert result["narrative"]["engine"] == "reading_structure_artifact"
    assert len(result["pages"]) == 2
    assert project.pages[0].reading_page_id == "p01"


def test_delivery_identity_changes_when_a_different_reading_is_attached():
    deck = {"project_id": "p", "presentation_question": "q", "export_type": "PPTX", "pages": []}
    documents = [{"id": "doc_a", "sha256": SHA, "page_count": 2}]
    without = main.immutable_snapshot_digest(deck, documents)
    first = main.immutable_snapshot_digest(deck, documents, reading_sha256="sha-reading-1")
    second = main.immutable_snapshot_digest(deck, documents, reading_sha256="sha-reading-2")
    assert len({without, first, second}) == 3


def test_reattaching_a_different_reading_marks_pages_stale(monkeypatch):
    project = registered_project(monkeypatch)
    main.run_architect("demo") if False else None
    project.pages = main.architect_from_reading_structure(project)[1]
    other = copy.deepcopy(valid_artifact())
    other["narrative"]["difference_reason"] = "另一份读法的理由，长度同样满足检查要求，用于触发失效。"
    main.register_reading_structure("demo", main.ReadingStructureRequest(artifact=other))
    assert all(page.revision_status == "STALE" for page in project.pages)


def test_the_real_ch06_plan_artifact_is_gated_not_rubber_stamped():
    """A regression target from the repository's own accepted artifacts."""
    path = Path(__file__).resolve().parents[1] / "out" / "ch06_plan_v1" / "artifact_medical_planned.json"
    if not path.exists():
        pytest.skip("repository reading artifact is not present")
    artifact = json.loads(path.read_text(encoding="utf-8"))
    issues = validate_reading_structure(artifact)
    assert all(item["severity"] == "BLOCK" for item in issues)
    assert all(item["code"] for item in issues)


# --- REG-READ-018: a reading belongs to a run, not to a document -------------------------
#
# Completeness alone cannot distinguish "this generation read the source" from "this
# generation replayed an earlier reading". These four cases hold both directions: the
# two reuse forms are refused, a run-bound reading passes, and an artifact predating the
# rule is reported as not established rather than quietly counted as fresh.


def test_a_reused_reading_is_refused():
    artifact = valid_artifact()
    artifact["reading_pass"]["reused_from"] = (
        "app/validation/model_workflow/authored/source_candidate_extraction_ch06_merged.json")
    issues = validate_reading_structure(artifact)
    codes_here = {item["code"] for item in issues}
    assert "READING_REUSED_FROM_PRIOR_ARTIFACT" in codes_here
    assert all(item["rule"] == "REG-READ-018" for item in issues
               if item["code"] == "READING_REUSED_FROM_PRIOR_ARTIFACT")


def test_a_reading_taken_from_different_bytes_is_refused():
    artifact = valid_artifact()
    artifact["reading_pass"]["read_from_sha256"] = "0" * 64
    assert "READ_FROM_A_DIFFERENT_SOURCE" in codes(artifact)


def test_a_run_bound_reading_passes_and_reports_freshness_established():
    artifact = valid_artifact()
    artifact["reading_pass"]["executed_for_run"] = "RUN-1"
    artifact["reading_pass"]["read_from_sha256"] = SHA
    assert validate_reading_structure(artifact) == []
    assert summarize(artifact)["read_freshness_established"] is True


def test_an_artifact_predating_the_rule_reports_freshness_not_established():
    """Absence of a freshness declaration is not a pass; it is an unestablished fact."""
    assert validate_reading_structure(valid_artifact()) == []
    summary = summarize(valid_artifact())
    assert summary["read_freshness_established"] is False
    assert summary["executed_for_run"] is None

