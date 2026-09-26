"""Offline qualification gate for an independent semantic-review model.

Running a model and approving its operational registration are separate actions.
This module scores recorded answers; it never installs qualification by itself.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


BENCHMARK = Path(__file__).with_name("reviewer_benchmark.json")


class ReviewerAnswer(BaseModel):
    case_id: str
    decision: Literal["APPROVE", "REJECT", "REVIEW"]
    rationale: str = Field(min_length=12)


class QualificationResult(BaseModel):
    engine_id: str
    engine_version: str
    suite_sha256: str
    status: Literal["QUALIFIED_CANDIDATE", "FAILED"]
    total: int
    correct: int
    failures: list[str]


def evaluate_reviewer(engine_id: str, engine_version: str,
                      answers: list[ReviewerAnswer]) -> QualificationResult:
    """Require every case correct; missing or duplicate responses fail."""
    raw = BENCHMARK.read_bytes()
    cases = json.loads(raw.decode("utf-8"))
    expected = {case["id"]: case["decision"] for case in cases}
    received: dict[str, ReviewerAnswer] = {}
    failures = []
    for answer in answers:
        if answer.case_id in received:
            failures.append(f"duplicate:{answer.case_id}")
        received[answer.case_id] = answer
    for case_id, decision in expected.items():
        if case_id not in received:
            failures.append(f"missing:{case_id}")
        elif received[case_id].decision != decision:
            failures.append(f"wrong:{case_id}")
    failures.extend(f"unknown:{case_id}" for case_id in received if case_id not in expected)
    correct = sum(case_id in received and received[case_id].decision == decision
                  for case_id, decision in expected.items())
    return QualificationResult(engine_id=engine_id, engine_version=engine_version,
                               suite_sha256=hashlib.sha256(raw).hexdigest(),
                               status="FAILED" if failures else "QUALIFIED_CANDIDATE",
                               total=len(expected), correct=correct, failures=failures)
