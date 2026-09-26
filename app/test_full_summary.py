from __future__ import annotations

import copy

import pytest
from fastapi import HTTPException

from app import main
from app.full_summary import authoring_brief, digest, validate, with_locations
from app.test_reading_structure import project_with_source, valid_artifact


def authored_summary(reading: dict) -> dict:
    return {
        "schema_version": "full_source_summary.v1",
        "reading_structure_sha256": digest(reading),
        "source_sha256": reading["source"]["sha256"],
        "overall_summary": "本材料先讨论接种对象的变化，再说明疫苗选择应如何随人群和风险边界调整；省略在演示稿之外的内容仍保留来源定位，供复核时查看。",
        "sections": [
            {"section_id": "s01", "title": "接种对象", "summary": "材料先给出接种对象的变化，并把年龄和风险因素作为判断建议适用性的边界。",
             "source_block_ids": [1]},
            {"section_id": "s02", "title": "选择边界", "summary": "随后讨论何时需要重新评估疫苗选择；这一部分在证据层保留，不能从演示稿的省略推断原文没有涉及。",
             "source_block_ids": [2]},
        ],
    }


def test_full_summary_exposes_exact_source_locations():
    reading = valid_artifact()
    summary = authored_summary(reading)
    assert validate(summary, reading) == []
    located = with_locations(summary, reading)
    assert [section["sources"][0]["page"] for section in located["sections"]] == [1, 2]
    assert located["sections"][0]["summary"] == summary["sections"][0]["summary"]


def test_full_summary_blocks_stale_reading_and_missing_page():
    reading = valid_artifact()
    summary = authored_summary(reading)
    stale = copy.deepcopy(reading)
    stale["structure"]["thread"] += "修订"
    assert any("current reading" in issue for issue in validate(summary, stale))
    summary["sections"].pop()
    assert any("page(s) [2]" in issue for issue in validate(summary, reading))
    summary = authored_summary(reading)
    summary["sections"][0]["source_block_ids"] = [{"block_id": 1}]
    assert any("malformed source block" in issue for issue in validate(summary, reading))


def test_authoring_brief_carries_entire_current_source_and_citation_ids():
    reading = valid_artifact()
    document = project_with_source().documents[0]
    brief = authoring_brief(reading, document)
    assert brief["reading_structure_sha256"] == digest(reading)
    assert [(item["page"], item["text"], item["source_block_ids"])
            for item in brief["pages"]] == [(1, "文本一", [1]), (2, "文本二", [2])]
    assert len(brief["pages"]) == reading["source"]["unit_count"]


def test_authoring_brief_refuses_partial_or_wrong_source():
    reading = valid_artifact()
    document = project_with_source().documents[0]
    with pytest.raises(ValueError, match="every source page"):
        authoring_brief(reading, {**document, "chunks": document["chunks"][:1]})
    with pytest.raises(ValueError, match="matching source identity"):
        authoring_brief(reading, {**document, "sha256": "wrong"})


def test_summary_is_required_for_delivery_when_reading_artifact_is_attached(monkeypatch):
    project = project_with_source()
    project.reading_structure = valid_artifact()
    monkeypatch.setattr(main, "get_project", lambda project_id: ([project], project))
    monkeypatch.setattr(main, "semantic_deck", lambda value: {"pages": []})
    with pytest.raises(HTTPException) as error:
        main.export_presentation("demo")
    assert error.value.status_code == 409
    assert "Full-source summary" in error.value.detail


def test_full_summary_brief_endpoint_and_automatic_route_fail_closed(monkeypatch):
    project = project_with_source()
    project.reading_structure = valid_artifact()
    monkeypatch.setattr(main, "get_project", lambda project_id: ([project], project))
    monkeypatch.setattr(main, "configured_semantic_model", lambda: {
        "url": "http://127.0.0.1:1234/v1/chat/completions", "model_id": "unqualified",
        "external": False, "engine_id": "operator_model_workflow"})
    brief = main.get_full_summary_brief("demo")
    assert len(brief["pages"]) == 2
    with pytest.raises(HTTPException, match="route refused"):
        main.run_full_summary("demo")
    assert project.full_summary is None


def test_qualified_model_summary_output_is_validated_before_registration(monkeypatch):
    project = project_with_source()
    project.reading_structure = valid_artifact()
    monkeypatch.setattr(main, "get_project", lambda project_id: ([project], project))
    monkeypatch.setattr(main, "save_projects", lambda value: None)
    monkeypatch.setattr(main, "resolve_semantic_route", lambda project, capability: {
        "model": {"adapter_id": "qualified-test", "external": False},
        "engine_id": "qualified-test", "egress": {"decision": "LOOPBACK_NO_EGRESS"}})
    monkeypatch.setattr(main, "call_semantic_model", lambda capability, payload, model:
                        authored_summary(project.reading_structure))
    result = main.run_full_summary("demo")
    assert result["status"] == "ACCEPTED"
    assert project.model_runs[-1]["agent"] == "full_source_summarizer"
    assert len(result["summary"]["sections"]) == 2
