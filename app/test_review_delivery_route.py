"""The full Item 1 route: source -> verification -> issuance -> delivery.

The unit tests either side of this file each pass while the *seam* between
them is broken. That was the actual state of the codebase: `ReviewReceipt`
existed, `apply_review` existed, and no caller could produce a receipt outside
a fixture -- so the rule "the generating model must not sign off on its own
content" was enforceable in principle and unenforced in practice.

These tests drive the whole route and check what a delivery actually requires.
"""
from __future__ import annotations

import pytest

from app.content_contract import (EvidenceAssertion, SlideStatement, SourceExcerpt,
                                  SourceLocator, contract_digest, digest)
from app.content_validation import ContentPackage, verify_content_package
from app.delivery_gate import DELIVERABLE, WITHHELD, delivery_gate
from app.review_issuance import (ReviewIssuanceError, ReviewRegistry, ReviewerEnrolment,
                                 enrol_reviewer, issue_receipt, trusted_reviews,
                                 trusted_reviews as _trusted)

QUALIFIED = {"semantic-review-v1"}
AUTHOR = "generator"


def package(quote: str, claim: str, slide: str | None = None) -> ContentPackage:
    return ContentPackage(
        source_excerpts=[SourceExcerpt(
            id="s", source_sha256=digest("input"), locator=SourceLocator(kind="PDF", page=2),
            extracted_text=quote, quote=quote)],
        assertions=[EvidenceAssertion(id="a", text=claim, source_excerpt_ids=["s"])],
        slide_statements=[SlideStatement(id="p", text=slide or claim, assertion_ids=["a"])],
    )


def human(registry: ReviewRegistry, reviewer_id: str = "reviewer-1") -> None:
    enrol_reviewer(registry, ReviewerEnrolment(reviewer_id=reviewer_id,
                                               reviewer_kind="HUMAN"), QUALIFIED)


def sign(registry: ReviewRegistry, item: ContentPackage, *, reviewer_id: str = "reviewer-1",
         decision: str = "APPROVE") -> None:
    """Sign the assertion and the slide that depends on it.

    The evidence ids must match the ones the verifier will put on the finding,
    and those differ by object kind: an assertion's finding cites its *source*
    ids, a slide's finding cites its *assertion* ids. Citing the source for the
    slide trips `REVIEW_EVIDENCE_MISMATCH` -- which is how this was discovered.
    """
    assertion = item.assertions[0]
    issue_receipt(registry, subject=assertion, dependencies=item.source_excerpts,
                  author_id=AUTHOR, reviewer_id=reviewer_id, decision=decision,
                  rationale="Reviewed the source span and the wording.",
                  evidence_ids=list(assertion.source_excerpt_ids))
    statement = item.slide_statements[0]
    issue_receipt(registry, subject=statement, dependencies=[assertion],
                  author_id=AUTHOR, reviewer_id=reviewer_id, decision=decision,
                  rationale="Checked the slide text against the assertion.",
                  evidence_ids=list(statement.assertion_ids))


def drive(item: ContentPackage, registry: ReviewRegistry,
          reviewed: list[str]) -> tuple[str, str]:
    """Run verify -> gate and return (report status, delivery decision)."""
    receipts = trusted_reviews(registry, reviewed, QUALIFIED)
    report = verify_content_package(
        item, authored_by=AUTHOR,
        trusted_assertion_reviews={k: v for k, v in receipts.items() if k == "a"},
        trusted_slide_reviews={k: v for k, v in receipts.items() if k == "p"},
        trusted_excerpts={"s": item.source_excerpts[0]},
        qualified_review_ids=QUALIFIED)
    decision = delivery_gate(report, registry, reviewed_object_ids=reviewed,
                             qualified_review_ids=QUALIFIED)
    return report.status, decision.decision


def test_a_slide_receipt_citing_source_ids_instead_of_assertion_ids_is_rejected():
    """Pins the evidence-id contract that is easy to get wrong and hard to see.

    Findings cite different things by object kind: an assertion cites its
    sources, a slide cites its assertions. Getting this backwards produces a
    BLOCK that looks like a content problem when it is a wiring problem, so it
    is worth an explicit regression.
    """
    item = package("在已完成问卷的客户中，满意率为80%。", "已完成问卷的客户满意率为80%。")
    registry = ReviewRegistry()
    human(registry)
    assertion = item.assertions[0]
    issue_receipt(registry, subject=assertion, dependencies=item.source_excerpts,
                  author_id=AUTHOR, reviewer_id="reviewer-1", decision="APPROVE",
                  rationale="Reviewed the source span and wording.",
                  evidence_ids=list(assertion.source_excerpt_ids))
    statement = item.slide_statements[0]
    issue_receipt(registry, subject=statement, dependencies=[assertion],
                  author_id=AUTHOR, reviewer_id="reviewer-1", decision="APPROVE",
                  rationale="Checked the slide against the assertion.",
                  evidence_ids=list(assertion.source_excerpt_ids))  # wrong: source, not assertion

    receipts = trusted_reviews(registry, ["a", "p"], QUALIFIED)
    report = verify_content_package(
        item, authored_by=AUTHOR,
        trusted_assertion_reviews={"a": receipts["a"]},
        trusted_slide_reviews={"p": receipts["p"]},
        trusted_excerpts={"s": item.source_excerpts[0]},
        qualified_review_ids=QUALIFIED)
    assert report.slide_findings["p"].codes == ["REVIEW_EVIDENCE_MISMATCH"]


def test_a_paraphrase_no_lexical_check_can_certify_becomes_deliverable_after_review():
    """The whole point of the review route: it certifies what code cannot."""
    item = package("在已完成问卷的客户中，满意率为80%。", "已完成问卷的客户满意率为80%。")
    registry = ReviewRegistry()
    human(registry)

    assert drive(item, registry, ["a", "p"])[0] == "NEEDS_REVIEW"
    sign(registry, item)
    status, decision = drive(item, registry, ["a", "p"])
    assert status == "SUPPORTED"
    assert decision == DELIVERABLE


def test_a_reversal_stays_blocked_even_when_a_reviewer_signs_it():
    """A receipt buys an inference; it never overrules a contradiction."""
    item = package("该观察记录未显示方案甲改善目标结局。", "该观察记录显示方案甲改善目标结局。")
    registry = ReviewRegistry()
    human(registry)
    sign(registry, item)
    status, decision = drive(item, registry, ["a", "p"])
    assert status == "BLOCK"
    assert decision == WITHHELD


def test_the_generating_model_cannot_sign_its_own_content():
    """The acceptance rule, exercised through the real route rather than the model."""
    item = package("仅试点地区的收入增长。", "试点地区的收入增长。")
    registry = ReviewRegistry()
    human(registry, AUTHOR)
    with pytest.raises(ReviewIssuanceError, match="author cannot issue"):
        sign(registry, item, reviewer_id=AUTHOR)
    assert drive(item, registry, ["a", "p"])[1] == WITHHELD


def test_an_edited_claim_invalidates_the_receipt_and_withholds_delivery():
    """The stale-review path, driven end to end rather than asserted on a unit."""
    item = package("在已完成问卷的客户中，满意率为80%。", "已完成问卷的客户满意率为80%。")
    registry = ReviewRegistry()
    human(registry)
    sign(registry, item)

    edited = package("在已完成问卷的客户中，满意率为80%。", "所有客户满意率为80%。")
    status, decision = drive(edited, registry, ["a", "p"])
    assert status != "SUPPORTED"
    assert decision == WITHHELD


def test_a_model_reviewer_route_requires_a_registered_qualification_end_to_end():
    item = package("在已完成问卷的客户中，满意率为80%。", "已完成问卷的客户满意率为80%。")
    registry = ReviewRegistry()
    enrol_reviewer(registry, ReviewerEnrolment(reviewer_id="model-1",
                                               reviewer_kind="QUALIFIED_MODEL",
                                               qualification_id="semantic-review-v1"),
                   QUALIFIED)
    sign(registry, item, reviewer_id="model-1")

    receipts = trusted_reviews(registry, ["a", "p"], QUALIFIED)
    report = verify_content_package(
        item, authored_by=AUTHOR,
        trusted_assertion_reviews={k: v for k, v in receipts.items() if k == "a"},
        trusted_slide_reviews={k: v for k, v in receipts.items() if k == "p"},
        trusted_excerpts={"s": item.source_excerpts[0]},
        qualified_review_ids=QUALIFIED)
    assert report.status == "SUPPORTED"
    assert delivery_gate(report, registry, reviewed_object_ids=["a", "p"],
                         qualified_review_ids=QUALIFIED).decision == DELIVERABLE

    # Withdraw the qualification; the same stored receipt must stop counting.
    assert delivery_gate(report, registry, reviewed_object_ids=["a", "p"],
                         qualified_review_ids=set()).decision == WITHHELD
