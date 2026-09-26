from __future__ import annotations

import json

from app.review_qualification import BENCHMARK, ReviewerAnswer, evaluate_reviewer


def answers():
    cases = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    return [ReviewerAnswer(case_id=case["id"], decision=case["decision"],
                           rationale="Compared the claim with the entire source clause.")
            for case in cases]


def test_complete_independent_review_answers_are_qualification_candidate_only():
    result = evaluate_reviewer("review-model", "2026-09", answers())
    assert result.status == "QUALIFIED_CANDIDATE"
    assert result.correct == result.total == 11
    assert len(result.suite_sha256) == 64


def test_wrong_missing_and_duplicate_answers_fail_qualification():
    submitted = answers()
    submitted[0].decision = "APPROVE"
    submitted.pop()
    submitted.append(submitted[1])
    result = evaluate_reviewer("review-model", "2026-09", submitted)
    assert result.status == "FAILED"
    assert any(failure.startswith("wrong:") for failure in result.failures)
    assert any(failure.startswith("missing:") for failure in result.failures)
    assert any(failure.startswith("duplicate:") for failure in result.failures)
