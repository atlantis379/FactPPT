"""The delivery gate: what a deck must prove before it may leave the building.

`verify_content_package` answers "is this content defensible?". It is a
question, and it is allowed to answer `NEEDS_REVIEW` -- that is the honest
answer for a free paraphrase no lexical check can certify.

This module answers a different question: "may this be delivered?". Those are
not the same question, and conflating them is how a system that *reports*
uncertainty ends up *shipping* it. The gate is deliberately stricter than the
verifier, and deliberately unable to grant anything the verifier refused:

* `SUPPORTED` must be reached by every object -- no object may remain
  `NEEDS_REVIEW`. Silence is not consent.
* A `BLOCK` can never be delivered, by anyone, for any reason.
* Approval must be traceable to a receipt that this deployment issued. A
  finding that says `SUPPORTED` is not evidence that a review happened unless
  the registry can produce the receipt behind it.

The gate never mints approval and never re-runs the verifier. It reads a
report the verifier produced and asks whether that report is good enough to
deliver.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.content_validation import ContentReport
from app.review_issuance import ReviewRegistry, trusted_reviews

DELIVERABLE = "DELIVERABLE"
WITHHELD = "WITHHELD"


class DeliveryDecision(BaseModel):
    """Why a report is or is not deliverable, in terms a reviewer can act on."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["DELIVERABLE", "WITHHELD"]
    blocking_ids: list[str] = Field(default_factory=list)
    unreviewed_ids: list[str] = Field(default_factory=list)
    unattributed_ids: list[str] = Field(default_factory=list)
    reason: str


def _findings(report: ContentReport) -> dict[str, str]:
    """Every reviewed object's status, keyed by id.

    Source excerpts carry no authored wording and do not require a reviewer
    signature, but their verification status is still a delivery precondition.
    """
    merged: dict[str, str] = {}
    for group in (report.source_findings, report.assertion_findings, report.slide_findings,
                  report.calculation_findings):
        for object_id, finding in group.items():
            merged[object_id] = finding.status
    return merged


def delivery_gate(report: ContentReport, registry: ReviewRegistry, *,
                  reviewed_object_ids: list[str],
                  qualified_review_ids: set[str] | None = None) -> DeliveryDecision:
    """Decide whether a verified report may be delivered.

    `reviewed_object_ids` are the authored objects that went through the
    issuance channel. An object that is `SUPPORTED` but has no receipt in the
    registry is listed under `unattributed_ids` -- it was approved by something
    this deployment cannot name.
    """
    statuses = _findings(report)
    if report.status != "SUPPORTED":
        return DeliveryDecision(decision=WITHHELD,
                                reason="the verifier report is not fully supported")
    blocking = sorted(k for k, status in statuses.items() if status == "BLOCK")
    if blocking:
        return DeliveryDecision(
            decision=WITHHELD,
            blocking_ids=blocking,
            reason=f"{len(blocking)} object(s) are blocked and cannot be delivered "
                   "by any review route")

    unreviewed = sorted(k for k, status in statuses.items() if status == "NEEDS_REVIEW")
    if unreviewed:
        return DeliveryDecision(
            decision=WITHHELD,
            unreviewed_ids=unreviewed,
            reason=f"{len(unreviewed)} object(s) still need review; silence is not approval")

    authored_ids = set(report.assertion_findings) | set(report.slide_findings)
    requested_ids = set(reviewed_object_ids)
    if requested_ids != authored_ids:
        missing = sorted(authored_ids - requested_ids)
        unexpected = sorted(requested_ids - authored_ids)
        return DeliveryDecision(
            decision=WITHHELD,
            unattributed_ids=missing + unexpected,
            reason="reviewed object ids must exactly cover every assertion and slide statement")

    receipts = trusted_reviews(registry, sorted(authored_ids), qualified_review_ids)
    unattributed = sorted(object_id for object_id in authored_ids
                          if object_id not in receipts)
    if unattributed:
        return DeliveryDecision(
            decision=WITHHELD,
            unattributed_ids=unattributed,
            reason=f"{len(unattributed)} approved object(s) have no receipt from a reviewer "
                   "enrolled in this deployment")

    if not statuses:
        return DeliveryDecision(decision=WITHHELD,
                                reason="the report covers no deliverable content")

    return DeliveryDecision(
        decision=DELIVERABLE,
        reason=f"all {len(statuses)} object(s) supported and traceable to an issued receipt")
