"""Trusted issuance of independent review receipts.

`content_contract.ReviewReceipt` is only a *record*. Until this module existed,
nothing in the codebase could produce one on the server side: the verifier
accepted `trusted_assertion_reviews` as a parameter, and every caller passed
either a test fixture or nothing at all. That made the acceptance rule
"the generating model must not sign off on its own content" unenforceable in
practice -- the rule was real in the model and absent in the workflow.

Two things are therefore separated here, deliberately:

* **Enrolment** (`enrol_reviewer`) is a privileged, out-of-band action. A
  reviewer identity exists only because an operator registered it, and a model
  reviewer additionally needs a qualification id that this deployment already
  recognises. There is no path from "submit a review" to "become a reviewer".
* **Issuance** (`issue_receipt`) records a decision made elsewhere. It refuses
  by construction to let the author sign for themselves, refuses to issue
  against a subject digest the caller merely asserted, and refuses to re-issue
  over a subject that has since changed.

Neither function decides whether content is *true*. They decide whether a
decision was made by someone entitled to make it, about the exact bytes in
hand. The verifier still has the final word.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.content_contract import ReviewReceipt, contract_digest


class ReviewIssuanceError(RuntimeError):
    """A receipt was requested that the deployment must not issue."""


class ReviewerEnrolment(BaseModel):
    """A registered reviewer identity.

    `qualification_id` is required for model reviewers and must appear in the
    deployment's recognised set -- registering a model is not the same as
    qualifying it.
    """

    model_config = ConfigDict(extra="forbid")

    reviewer_id: str = Field(min_length=1)
    reviewer_kind: Literal["HUMAN", "QUALIFIED_MODEL"]
    qualification_id: str | None = None
    enrolled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    note: str = ""

    @model_validator(mode="after")
    def model_reviewers_carry_a_qualification(self):
        if self.reviewer_kind == "QUALIFIED_MODEL" and not self.qualification_id:
            raise ValueError("a model reviewer cannot be enrolled without a qualification id")
        if self.reviewer_kind == "HUMAN" and self.qualification_id:
            raise ValueError("a human reviewer must not carry a model qualification id")
        return self


def _store_path(default: Path) -> Path:
    return Path(os.environ.get("EASYPPT_REVIEW_STORE", default))


class ReviewRegistry(BaseModel):
    """Enrolled reviewers plus every receipt this deployment has issued.

    Receipts are keyed by the reviewer who signed them, because the verifier
    looks a receipt up by the object under review and then checks the signer --
    keeping issuance order here would hide that a later decision replaced an
    earlier one.
    """

    model_config = ConfigDict(extra="forbid")

    reviewers: dict[str, ReviewerEnrolment] = Field(default_factory=dict)
    issued: dict[str, dict[str, ReviewReceipt]] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "ReviewRegistry":
        file = Path(path)
        if not file.exists():
            return cls()
        return cls.model_validate(json.loads(file.read_text(encoding="utf-8")))

    def save(self, path: str | Path) -> None:
        file = Path(path)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(self.model_dump(mode="json"), ensure_ascii=False, indent=2),
                        encoding="utf-8")

    def receipts_for(self, reviewer_id: str) -> dict[str, ReviewReceipt]:
        return self.issued.get(reviewer_id, {})


def enrol_reviewer(registry: ReviewRegistry, enrolment: ReviewerEnrolment,
                   qualified_review_ids: set[str] | None = None) -> ReviewerEnrolment:
    """Register a reviewer identity. Enrolment is not qualification.

    A model reviewer whose qualification id is unknown to this deployment is
    rejected here rather than at review time: a reviewer that can never sign is
    not a reviewer, and enrolling it would only move the failure later.
    """
    if (enrolment.reviewer_kind == "QUALIFIED_MODEL"
            and enrolment.qualification_id not in (qualified_review_ids or set())):
        raise ReviewIssuanceError(
            f"qualification {enrolment.qualification_id!r} is not recognised by this deployment")
    registry.reviewers[enrolment.reviewer_id] = enrolment
    return enrolment


def issue_receipt(registry: ReviewRegistry, *, subject, dependencies: list,
                  author_id: str, reviewer_id: str, decision: str,
                  rationale: str, evidence_ids: list[str],
                  expected_digest: str | None = None) -> ReviewReceipt:
    """Issue a receipt bound to the subject as it exists right now.

    The digest is computed here from the objects, never taken from the caller.
    Accepting a caller-supplied digest would let a client hold a receipt open
    over a subject it can edit afterwards -- which is exactly the staleness
    check the verifier is trying to perform.
    """
    enrolment = registry.reviewers.get(reviewer_id)
    if enrolment is None:
        raise ReviewIssuanceError(f"reviewer {reviewer_id!r} is not enrolled in this deployment")
    if reviewer_id == author_id:
        raise ReviewIssuanceError("the author cannot issue a review receipt for their own content")

    digest = contract_digest(subject, dependencies)
    if expected_digest is not None and expected_digest != digest:
        raise ReviewIssuanceError(
            "the subject changed since the review was performed; re-review is required")

    try:
        receipt = ReviewReceipt(
            subject_digest=digest,
            author_id=author_id,
            reviewer_id=reviewer_id,
            reviewer_kind=enrolment.reviewer_kind,
            qualification_id=enrolment.qualification_id,
            decision=decision,
            rationale=rationale,
            evidence_ids=evidence_ids,
        )
    except ValueError as error:  # pydantic validation of the receipt itself
        raise ReviewIssuanceError(str(error)) from error

    registry.issued.setdefault(reviewer_id, {})[subject.id] = receipt
    return receipt


def trusted_reviews(registry: ReviewRegistry, object_ids: list[str],
                    qualified_review_ids: set[str] | None = None) -> dict[str, ReviewReceipt]:
    """Receipts this deployment issued for the given objects, one per object.

    When more than one enrolled reviewer has signed the same object the later
    decision wins, so a rejection is never silently outvoted by an earlier
    approval. Ties fall back to enrolment order being irrelevant and the
    reviewer id being sorted, so the choice is at least deterministic.
    """
    chosen: dict[str, ReviewReceipt] = {}
    for reviewer_id in sorted(registry.issued):
        enrolment = registry.reviewers.get(reviewer_id)
        if enrolment is None:
            continue
        if (enrolment.reviewer_kind == "QUALIFIED_MODEL"
                and enrolment.qualification_id not in (qualified_review_ids or set())):
            continue
        for object_id, receipt in registry.issued[reviewer_id].items():
            if object_id not in object_ids:
                continue
            current = chosen.get(object_id)
            if current is None or receipt.issued_at >= current.issued_at:
                chosen[object_id] = receipt
    return chosen
