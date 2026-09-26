# -*- coding: utf-8 -*-
"""Reading completeness: every unit accounted for, every meaning-critical value accounted for.

The failure these lock down is the one the real GOLD 2026 run exposed: a reading counted as
complete by returning *some* quote-grounded candidate, so eleven values -- including all five
magnitude figures on one page -- were never extracted and nothing noticed.
"""
from __future__ import annotations

import pytest

from app import main
from app.read_units import (DECLINE_REASONS, audit_read_receipts, classify, classify_units,
                            measure_unit)

BODY = "全球慢阻肺病患病率为2.7%，2021年慢阻肺病相关死亡为372万例。"
APPARATUS = ("参考文献 ［1］ Global strategy for prevention，diagnosis and management of COPD：2026 Report. "
             "［2］ WANG Z，LIN J，LIANG L，et al. Global，regional，and national burden of chronic "
             "obstructive pulmonary disease ［J］. Respir Res，2025，26（1）：2. 通信作者：刘升明")


def _claim(page: int, quote: str, text: str | None = None) -> main.Claim:
    return main.Claim(id=f"c{page}{abs(hash(quote)) % 1000}", normalized_claim=text or quote,
                      source_quote=quote, provenance="SOURCE", risk="YELLOW",
                      source_refs=[main.SourceRef(document_id="d", page=page, quote=quote)])


def _audit(units_text: dict[int, str], receipts, claims):
    chunks = [{"page": page, "text": text} for page, text in units_text.items()]
    return audit_read_receipts(units=classify_units(chunks), receipts=receipts, claims=claims)


# ------------------------------------------------------------------ measurement rules
def test_calendar_years_are_not_measurements():
    """"2021 年" is an identifier. Counting it made the audit fire on the masthead and the
    reference list, which is how a completeness rule gets switched off."""
    signals = measure_unit("纳入2021年全球疾病负担研究数据显示，较1990年下降。")
    assert signals["measurements"] == []
    assert signals["magnitudes"] == []


def test_publication_apparatus_is_not_content_but_a_finding_makes_it_mixed():
    assert classify(measure_unit(APPARATUS)) == "NON_CONTENT"
    assert classify(measure_unit(APPARATUS + BODY)) == "MIXED"
    assert classify(measure_unit(BODY)) == "CONTENT_BEARING"


def test_classification_is_deterministic():
    first = classify_units([{"page": 1, "text": BODY}])
    second = classify_units([{"page": 1, "text": BODY}])
    assert first == second
    assert first[0]["rule_version"]


# ------------------------------------------------------------------------- unit receipts
def test_a_unit_that_is_never_accounted_for_blocks():
    result = _audit({1: BODY, 2: BODY}, receipts=[{"page": 1, "status": "HAS_CANDIDATES"}],
                    claims=[_claim(1, BODY)])
    assert result["status"] == "BLOCK"
    assert any(issue["code"] == "UNIT_NOT_ACCOUNTED" and issue["page"] == 2 for issue in result["issues"])


def test_a_content_bearing_unit_may_not_be_declined():
    result = _audit({1: BODY}, receipts=[{"page": 1, "status": "NO_QUOTABLE_CONTENT",
                                          "reason": "MASTHEAD_OR_PUBLICATION_METADATA"}],
                    claims=[])
    assert result["status"] == "BLOCK"
    assert any(issue["code"] == "CONTENT_UNIT_DECLINED" for issue in result["issues"])
    assert result["statistics"]["declined_content_bearing"] == 1


def test_a_reference_list_may_be_declined_with_a_reason():
    result = _audit({1: APPARATUS}, receipts=[{"page": 1, "status": "NO_QUOTABLE_CONTENT",
                                               "reason": "REFERENCE_LIST"}], claims=[])
    assert result["status"] == "PASS"


def test_a_decline_needs_a_reason_from_the_closed_list():
    result = _audit({1: APPARATUS}, receipts=[{"page": 1, "status": "NO_QUOTABLE_CONTENT",
                                               "reason": "did not feel like it"}], claims=[])
    assert any(issue["code"] == "DECLINE_WITHOUT_ALLOWED_REASON" for issue in result["issues"])
    assert "REFERENCE_LIST" in DECLINE_REASONS


def test_a_receipt_without_a_candidate_is_not_evidence_of_reading():
    result = _audit({1: BODY}, receipts=[{"page": 1, "status": "HAS_CANDIDATES"}], claims=[])
    assert any(issue["code"] == "RECEIPT_WITHOUT_CANDIDATE" for issue in result["issues"])


def test_a_receipt_may_not_contradict_its_own_candidates():
    result = _audit({1: BODY}, receipts=[{"page": 1, "status": "NO_QUOTABLE_CONTENT",
                                          "reason": "OTHER"}], claims=[_claim(1, BODY)])
    codes = {issue["code"] for issue in result["issues"]}
    assert "RECEIPT_CONTRADICTS_ITS_OWN_CANDIDATES" in codes


# --------------------------------------------------------------- meaning-critical values
def test_an_unaccounted_measurement_blocks_and_is_named():
    result = _audit({1: BODY}, receipts=[{"page": 1, "status": "HAS_CANDIDATES"}],
                    claims=[_claim(1, "全球慢阻肺病患病率为2.7%", "全球慢阻肺病患病率为2.7%。")])
    assert result["status"] == "BLOCK"
    named = [issue for issue in result["issues"] if issue["code"] == "MEANING_TOKEN_NOT_ACCOUNTED"]
    assert any(issue["token"] == "372万" for issue in named)
    assert result["statistics"]["tokens_unaccounted"] == 1


def test_an_exclusion_with_a_stated_reason_is_accepted():
    result = _audit({1: BODY}, receipts=[{"page": 1, "status": "HAS_CANDIDATES",
                                          "exclusions": [{"token": "372万",
                                                          "reason": "DUPLICATED_ELSEWHERE_IN_DECK"}]}],
                    claims=[_claim(1, "全球慢阻肺病患病率为2.7%", "全球慢阻肺病患病率为2.7%。")])
    assert result["status"] == "PASS"
    assert result["statistics"]["tokens_excluded"] == 1


def test_an_exclusion_with_an_unknown_reason_is_refused():
    result = _audit({1: BODY}, receipts=[{"page": 1, "status": "HAS_CANDIDATES",
                                          "exclusions": [{"token": "372万", "reason": "not important"}]}],
                    claims=[_claim(1, "全球慢阻肺病患病率为2.7%", "全球慢阻肺病患病率为2.7%。")])
    assert any(issue["code"] == "EXCLUSION_REASON_UNKNOWN" for issue in result["issues"])


def test_a_threshold_may_not_be_excluded():
    """Thresholds are the class whose silent loss this project exists to prevent."""
    text = "E组标准为过去一年≥1次中重度急性加重。"
    result = _audit({1: text}, receipts=[{"page": 1, "status": "HAS_CANDIDATES",
                                          "exclusions": [{"token": "≥1",
                                                          "reason": "CONTEXT_ONLY_NOT_A_FINDING"}]}],
                    claims=[_claim(1, "E组标准为过去一年中重度急性加重", "E组标准为过去一年中重度急性加重。")])
    assert result["status"] == "BLOCK"
    assert any(issue["code"] == "THRESHOLD_MAY_NOT_BE_EXCLUDED" for issue in result["issues"])
    assert result["statistics"]["thresholds_unaccounted"] == 1


def test_a_covered_threshold_passes_without_an_exclusion():
    text = "E组标准为过去一年≥1次中重度急性加重。"
    result = _audit({1: text}, receipts=[{"page": 1, "status": "HAS_CANDIDATES"}],
                    claims=[_claim(1, "过去一年≥1次中重度急性加重", "过去一年≥1次中重度急性加重。")])
    assert result["status"] == "PASS"


# -------------------------------------------------------------------- reviewer override
def test_a_reviewer_override_changes_the_classification_the_audit_uses():
    """The classifier is a rule and will sometimes be wrong; disagreeing must be possible,
    recorded, and traceable to the rule version it disagreed with."""
    project = main.Project(title="t", presentation_question="q",
                           documents=[{"id": "d", "sha256": "s", "chunks": [{"page": 1, "text": BODY}]}])
    before = classify_units(project.documents[0]["chunks"])[0]
    assert before["computed_classification"] == "CONTENT_BEARING"
    event = main.record_read_unit_review(project, main.ReadUnitReviewRequest(
        page=1, decision="NON_CONTENT", reviewer="medical-reviewer",
        rationale="这张页只是封面引用，不含本课件要讲的医学主张"))
    assert event["computed_classification"] == "CONTENT_BEARING"
    assert event["rule_version"] == before["rule_version"]
    assert main.read_unit_overrides(project) == {1: "NON_CONTENT"}
    after = classify_units(project.documents[0]["chunks"], overrides=main.read_unit_overrides(project))[0]
    assert after["classification"] == "NON_CONTENT"
    assert after["classification_source"] == "REVIEWER_OVERRIDE"


def test_an_override_does_not_reach_a_unit_that_is_not_in_the_document():
    project = main.Project(title="t", presentation_question="q",
                           documents=[{"id": "d", "sha256": "s", "chunks": [{"page": 1, "text": BODY}]}])
    with pytest.raises(main.HTTPException, match="not in the imported document"):
        main.record_read_unit_review(project, main.ReadUnitReviewRequest(
            page=9, decision="NON_CONTENT", reviewer="medical-reviewer",
            rationale="不存在的单元不应被登记为任何分类"))
