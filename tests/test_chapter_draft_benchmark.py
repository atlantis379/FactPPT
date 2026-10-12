import copy
import pytest
from tools.chapter_draft_benchmark import normalize_metadata, parse_response, validate_page


def brief():
    return {"page": {"id": "S03:p1"}, "result_contract": {"coverage": {
        "read_claim_ids": ["S03:p1#k1"], "read_unit_ids": ["S03:p1:u1"]}}}


def result():
    return {"id": "S03:p1", "summary": "虚构测试语句，包含足够长度来检查请求绑定字段和来源编号的恢复。",
            "key_points": [{"point": "虚构测试观点", "claim_ids": ["S03:p1#k1", "S03:p1:u1"]}],
            "coverage": copy.deepcopy(brief()["result_contract"]["coverage"]), "pending_issues": []}


def test_only_locked_metadata_and_known_namespace_are_restored():
    original = result()
    restored, repairs = normalize_metadata(original, brief())
    assert len(repairs) == 2
    assert restored["summary"] == original["summary"]
    assert restored["key_points"][0]["point"] == original["key_points"][0]["point"]
    assert restored["key_points"][0]["unit_ids"] == ["S03:p1:u1"]
    assert "source_page_ids" not in original
    assert validate_page(restored, brief()) == []


def test_wrong_page_and_unknown_identifiers_are_never_fixed():
    original = result()
    original["source_page_ids"] = ["S03:p2"]
    original["key_points"][0]["claim_ids"] = ["S03:p2:u1"]
    restored, _ = normalize_metadata(original, brief())
    assert "page_binding" in validate_page(restored, brief())
    assert "key0:claims" in validate_page(restored, brief())


def test_json_wrapper_is_removed_without_a_model_but_truncation_fails():
    obj, repaired = parse_response('```json\n{"threshold":"≥300/μL"}\n```')
    assert repaired and obj["threshold"] == "≥300/μL"
    with pytest.raises(ValueError):
        parse_response('{"threshold":"≥300')


def test_cross_page_citation_requires_actual_supplied_neighbor_evidence():
    neighbor = {"page": {"id": "S03:p2"}, "result_contract": {"coverage": {
        "read_claim_ids": ["S03:p2#k1"], "read_unit_ids": ["S03:p2:u1"]}}}
    original = result()
    original["source_page_ids"] = ["S03:p1", "S03:p2"]
    original["key_points"][0]["claim_ids"] = ["S03:p2:u1"]
    restored, _ = normalize_metadata(original, brief(), [neighbor])
    assert validate_page(restored, brief(), [neighbor]) == []
    assert "page_binding" in validate_page(restored, brief())
    assert "key0:claims" in validate_page(restored, brief())
