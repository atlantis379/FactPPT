"""The delivery gate: reporting uncertainty must not be the same as shipping it.

The verifier is allowed to answer `NEEDS_REVIEW` -- that is the honest answer.
The gate is not. These tests pin the difference, because the failure mode this
guards against is a pipeline that faithfully records uncertainty and then
delivers anyway.
"""
from __future__ import annotations

from app.content_contract import EvidenceAssertion, ReviewFinding, SourceExcerpt, SourceLocator
from app.content_validation import ContentReport
from app.delivery_gate import DELIVERABLE, WITHHELD, delivery_gate
from app.review_issuance import (ReviewRegistry, ReviewerEnrolment, enrol_reviewer,
                                 issue_receipt)

SHA = "a" * 64
QUALIFIED = {"semantic-review-v1"}


def report(*statuses: tuple[str, str]) -> ContentReport:
    return ContentReport(
        status="SUPPORTED",
        source_findings={},
        assertion_findings={object_id: ReviewFinding(status=status, codes=[], evidence_ids=[])
                            for object_id, status in statuses},
        slide_findings={},
        calculation_findings={},
    )


def excerpt() -> SourceExcerpt:
    return SourceExcerpt(id="s", source_sha256=SHA,
                         locator=SourceLocator(kind="PDF", page=1),
                         extracted_text="Completed questionnaires report 80% satisfaction.",
                         quote="80% satisfaction")


def assertion(object_id: str = "a") -> EvidenceAssertion:
    return EvidenceAssertion(id=object_id, text="Satisfaction was 80%.", source_excerpt_ids=["s"])


def registry_with_receipt(object_id: str = "a", decision: str = "APPROVE") -> ReviewRegistry:
    registry = ReviewRegistry()
    enrol_reviewer(registry, ReviewerEnrolment(reviewer_id="reviewer-1", reviewer_kind="HUMAN"),
                   QUALIFIED)
    issue_receipt(registry, subject=assertion(object_id), dependencies=[excerpt()],
                  author_id="generator", reviewer_id="reviewer-1", decision=decision,
                  rationale="Checked the population and the wording.", evidence_ids=["s"])
    return registry


def test_a_supported_object_with_an_issued_receipt_is_deliverable():
    decision = delivery_gate(report(("a", "SUPPORTED")), registry_with_receipt(),
                             reviewed_object_ids=["a"], qualified_review_ids=QUALIFIED)
    assert decision.decision == DELIVERABLE


def test_an_object_still_awaiting_review_withholds_delivery():
    """The whole point: NEEDS_REVIEW is honest to report and fatal to ship."""
    decision = delivery_gate(report(("a", "NEEDS_REVIEW")), ReviewRegistry(),
                             reviewed_object_ids=["a"], qualified_review_ids=QUALIFIED)
    assert decision.decision == WITHHELD
    assert decision.unreviewed_ids == ["a"]
    assert "silence is not approval" in decision.reason


def test_a_blocked_object_can_never_be_delivered():
    """No receipt, no rationale and no reviewer seniority overrides a block."""
    decision = delivery_gate(report(("a", "BLOCK")), registry_with_receipt(),
                             reviewed_object_ids=["a"], qualified_review_ids=QUALIFIED)
    assert decision.decision == WITHHELD
    assert decision.blocking_ids == ["a"]
    assert "any review route" in decision.reason


def test_an_approval_with_no_receipt_is_not_traceable_and_withholds():
    """A finding that says SUPPORTED is not evidence a review happened."""
    decision = delivery_gate(report(("a", "SUPPORTED")), ReviewRegistry(),
                             reviewed_object_ids=["a"], qualified_review_ids=QUALIFIED)
    assert decision.decision == WITHHELD
    assert decision.unattributed_ids == ["a"]
    assert "no receipt" in decision.reason


def test_a_receipt_from_an_unenrolled_reviewer_does_not_unlock_delivery():
    """Removing the reviewer after the fact invalidates the approval."""
    registry = registry_with_receipt()
    registry.reviewers.clear()
    decision = delivery_gate(report(("a", "SUPPORTED")), registry,
                             reviewed_object_ids=["a"], qualified_review_ids=QUALIFIED)
    assert decision.decision == WITHHELD
    assert decision.unattributed_ids == ["a"]


def test_a_model_receipt_stops_counting_when_its_qualification_is_withdrawn():
    registry = ReviewRegistry()
    enrol_reviewer(registry, ReviewerEnrolment(reviewer_id="model-1",
                                               reviewer_kind="QUALIFIED_MODEL",
                                               qualification_id="semantic-review-v1"),
                   QUALIFIED)
    issue_receipt(registry, subject=assertion(), dependencies=[excerpt()],
                  author_id="generator", reviewer_id="model-1", decision="APPROVE",
                  rationale="Checked against the source span.", evidence_ids=["s"])
    assert delivery_gate(report(("a", "SUPPORTED")), registry, reviewed_object_ids=["a"],
                         qualified_review_ids=QUALIFIED).decision == DELIVERABLE
    assert delivery_gate(report(("a", "SUPPORTED")), registry, reviewed_object_ids=["a"],
                         qualified_review_ids=set()).decision == WITHHELD


def test_a_rejection_withholds_delivery_even_though_it_is_not_a_block():
    decision = delivery_gate(report(("a", "NEEDS_REVIEW")), registry_with_receipt(decision="REJECT"),
                             reviewed_object_ids=["a"], qualified_review_ids=QUALIFIED)
    assert decision.decision == WITHHELD


def test_a_report_covering_nothing_is_not_deliverable():
    """An empty pass must not be mistaken for a clean one."""
    decision = delivery_gate(report(), ReviewRegistry(), reviewed_object_ids=[],
                             qualified_review_ids=QUALIFIED)
    assert decision.decision == WITHHELD
    assert "no deliverable content" in decision.reason


def test_one_bad_object_among_good_ones_blocks_the_whole_deck():
    """Partial delivery is not a mode; the deck ships whole or not at all."""
    registry = registry_with_receipt("a")
    decision = delivery_gate(report(("a", "SUPPORTED"), ("b", "BLOCK")), registry,
                             reviewed_object_ids=["a", "b"], qualified_review_ids=QUALIFIED)
    assert decision.decision == WITHHELD
    assert decision.blocking_ids == ["b"]


def test_unverified_source_blocks_delivery_even_if_claim_has_receipt():
    item = report(("a", "SUPPORTED"))
    item.source_findings["s"] = ReviewFinding(
        status="NEEDS_REVIEW", codes=["SOURCE_FILE_NOT_VERIFIED"], evidence_ids=["s"])
    decision = delivery_gate(item, registry_with_receipt(),
                             reviewed_object_ids=["a"], qualified_review_ids=QUALIFIED)
    assert decision.decision == WITHHELD
    assert decision.unreviewed_ids == ["s"]


def test_callers_cannot_omit_an_authored_object_from_reviewed_ids():
    decision = delivery_gate(report(("a", "SUPPORTED")), registry_with_receipt(),
                             reviewed_object_ids=[], qualified_review_ids=QUALIFIED)
    assert decision.decision == WITHHELD
    assert decision.unattributed_ids == ["a"]


def test_inconsistent_report_status_cannot_open_delivery_gate():
    item = report(("a", "SUPPORTED"))
    item.status = "NEEDS_REVIEW"
    decision = delivery_gate(item, registry_with_receipt(),
                             reviewed_object_ids=["a"], qualified_review_ids=QUALIFIED)
    assert decision.decision == WITHHELD
