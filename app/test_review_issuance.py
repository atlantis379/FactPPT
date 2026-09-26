"""The trusted issuance channel: who may sign, over what, and what that buys.

These tests exist because the acceptance rule "the generating model must not
sign off on its own content" was previously true of the *models* and absent
from the *workflow*: nothing in the codebase could produce a server-side
receipt, so every caller either passed a fixture or passed nothing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.content_contract import EvidenceAssertion, SourceExcerpt, SourceLocator
from app.review_issuance import (ReviewIssuanceError, ReviewRegistry,
                                 ReviewerEnrolment, enrol_reviewer, issue_receipt,
                                 trusted_reviews)

SHA = "a" * 64
QUALIFIED = {"semantic-review-v1"}


def excerpt() -> SourceExcerpt:
    return SourceExcerpt(id="s", source_sha256=SHA,
                         locator=SourceLocator(kind="PDF", page=1),
                         extracted_text="Completed questionnaires report 80% satisfaction.",
                         quote="80% satisfaction")


def assertion() -> EvidenceAssertion:
    return EvidenceAssertion(id="a", text="Satisfaction was 80%.", source_excerpt_ids=["s"])


def enrolled_human(registry: ReviewRegistry, reviewer_id: str = "reviewer-1") -> ReviewerEnrolment:
    return enrol_reviewer(registry, ReviewerEnrolment(reviewer_id=reviewer_id,
                                                      reviewer_kind="HUMAN"),
                          QUALIFIED)


def test_an_author_cannot_issue_a_receipt_for_their_own_content():
    """The acceptance rule, enforced at the only place a receipt is created."""
    registry = ReviewRegistry()
    enrolled_human(registry, "generator")
    with pytest.raises(ReviewIssuanceError, match="author cannot issue"):
        issue_receipt(registry, subject=assertion(), dependencies=[excerpt()],
                      author_id="generator", reviewer_id="generator",
                      decision="APPROVE", rationale="Looks correct to me.",
                      evidence_ids=["s"])


def test_an_unenrolled_reviewer_cannot_issue():
    """There is no path from submit-a-review to become-a-reviewer."""
    registry = ReviewRegistry()
    with pytest.raises(ReviewIssuanceError, match="not enrolled"):
        issue_receipt(registry, subject=assertion(), dependencies=[excerpt()],
                      author_id="generator", reviewer_id="stranger",
                      decision="APPROVE", rationale="Looks correct to me.",
                      evidence_ids=["s"])


def test_a_model_reviewer_cannot_enrol_without_a_recognised_qualification():
    """Enrolling a model is not the same as qualifying it."""
    registry = ReviewRegistry()
    with pytest.raises(ReviewIssuanceError, match="not recognised"):
        enrol_reviewer(registry, ReviewerEnrolment(reviewer_id="model-1",
                                                   reviewer_kind="QUALIFIED_MODEL",
                                                   qualification_id="invented-id"),
                       QUALIFIED)


def test_a_qualified_model_reviewer_enrols_and_signs_with_its_qualification():
    registry = ReviewRegistry()
    enrol_reviewer(registry, ReviewerEnrolment(reviewer_id="model-1",
                                               reviewer_kind="QUALIFIED_MODEL",
                                               qualification_id="semantic-review-v1"),
                   QUALIFIED)
    receipt = issue_receipt(registry, subject=assertion(), dependencies=[excerpt()],
                            author_id="generator", reviewer_id="model-1",
                            decision="APPROVE", rationale="Checked against the source span.",
                            evidence_ids=["s"])
    assert receipt.reviewer_kind == "QUALIFIED_MODEL"
    assert receipt.qualification_id == "semantic-review-v1"


def test_the_digest_is_computed_from_the_subject_not_asserted_by_the_caller():
    """A caller-supplied digest would let a receipt be held open over an edit."""
    registry = ReviewRegistry()
    enrolled_human(registry)
    receipt = issue_receipt(registry, subject=assertion(), dependencies=[excerpt()],
                            author_id="generator", reviewer_id="reviewer-1",
                            decision="APPROVE", rationale="Checked the population.",
                            evidence_ids=["s"])
    later = EvidenceAssertion(id="a", text="Satisfaction was 95%.", source_excerpt_ids=["s"])
    changed = issue_receipt(registry, subject=later, dependencies=[excerpt()],
                            author_id="generator", reviewer_id="reviewer-1",
                            decision="APPROVE", rationale="Checked the population.",
                            evidence_ids=["s"])
    assert receipt.subject_digest != changed.subject_digest


def test_a_stale_expectation_refuses_to_issue_rather_than_silently_rebinding():
    """Re-review is the remedy; quietly re-binding the digest is not."""
    registry = ReviewRegistry()
    enrolled_human(registry)
    with pytest.raises(ReviewIssuanceError, match="changed since the review"):
        issue_receipt(registry, subject=assertion(), dependencies=[excerpt()],
                      author_id="generator", reviewer_id="reviewer-1",
                      decision="APPROVE", rationale="Checked the population.",
                      evidence_ids=["s"], expected_digest="b" * 64)


def test_trusted_reviews_returns_only_receipts_this_deployment_issued():
    registry = ReviewRegistry()
    enrolled_human(registry)
    receipt = issue_receipt(registry, subject=assertion(), dependencies=[excerpt()],
                            author_id="generator", reviewer_id="reviewer-1",
                            decision="APPROVE", rationale="Checked the population.",
                            evidence_ids=["s"])
    assert trusted_reviews(registry, ["a"], QUALIFIED) == {"a": receipt}
    assert trusted_reviews(registry, ["nonexistent"], QUALIFIED) == {}


def test_a_later_rejection_is_not_outvoted_by_an_earlier_approval():
    """Issue order matters for the decision, so the latest one must win."""
    registry = ReviewRegistry()
    enrolled_human(registry, "reviewer-1")
    enrolled_human(registry, "reviewer-2")
    issue_receipt(registry, subject=assertion(), dependencies=[excerpt()],
                  author_id="generator", reviewer_id="reviewer-1",
                  decision="APPROVE", rationale="Checked the population.",
                  evidence_ids=["s"])
    registry.issued["reviewer-1"]["a"].issued_at = datetime.now(timezone.utc) - timedelta(hours=1)
    issue_receipt(registry, subject=assertion(), dependencies=[excerpt()],
                  author_id="generator", reviewer_id="reviewer-2",
                  decision="REJECT", rationale="The population wording is misleading.",
                  evidence_ids=["s"])
    chosen = trusted_reviews(registry, ["a"], QUALIFIED)
    assert chosen["a"].decision == "REJECT"


def test_receipts_survive_a_round_trip_through_the_store(tmp_path):
    registry = ReviewRegistry()
    enrolled_human(registry)
    issue_receipt(registry, subject=assertion(), dependencies=[excerpt()],
                  author_id="generator", reviewer_id="reviewer-1",
                  decision="APPROVE", rationale="Checked the population.",
                  evidence_ids=["s"])
    path = tmp_path / "reviews.json"
    registry.save(path)
    reloaded = ReviewRegistry.load(path)
    assert trusted_reviews(reloaded, ["a"], QUALIFIED)["a"].decision == "APPROVE"
    assert "reviewer-1" in reloaded.reviewers


def test_a_missing_store_loads_as_empty_rather_than_failing(tmp_path):
    """A deployment that has enrolled nobody must still start."""
    assert ReviewRegistry.load(tmp_path / "absent.json").reviewers == {}
