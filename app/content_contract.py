"""Cross-industry source, assertion and slide-text contracts.

The contract separates an extracted source span from an authored assertion and
from its presentation wording. A lexical check can reject contradictions or
accept verbatim reuse; it cannot certify a free paraphrase as entailed.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.semantic_fidelity import contradiction_signals, missing_source_signals


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


class SourceLocator(BaseModel):
    kind: Literal["PDF", "DOCX", "XLSX"]
    page: int | None = Field(default=None, ge=1)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)
    part: Literal["body", "header", "footer"] | None = None
    section: int | None = Field(default=None, ge=0)
    paragraph: int | None = Field(default=None, ge=0)
    table: int | None = Field(default=None, ge=0)
    row: int | None = Field(default=None, ge=0)
    column: int | None = Field(default=None, ge=0)
    sheet: str | None = None
    cell: str | None = None

    @model_validator(mode="after")
    def require_native_position(self):
        if self.kind == "PDF" and self.page is None:
            raise ValueError("PDF locator requires page")
        if (self.start is None) != (self.end is None):
            raise ValueError("text offsets require both start and end")
        if self.start is not None and self.end <= self.start:
            raise ValueError("text offset end must follow start")
        if self.kind == "DOCX" and self.paragraph is None and self.table is None:
            raise ValueError("DOCX locator requires paragraph or table")
        if self.kind == "DOCX" and self.table is not None and (self.row is None or self.column is None):
            raise ValueError("DOCX table locator requires row and column")
        if self.kind == "XLSX" and (not self.sheet or not self.cell):
            raise ValueError("XLSX locator requires sheet and cell")
        return self


class SourceExcerpt(BaseModel):
    id: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    locator: SourceLocator
    extracted_text: str = Field(min_length=1)
    quote: str = Field(min_length=1)

    @model_validator(mode="after")
    def quote_must_exist(self):
        if _compact(self.quote) not in _compact(self.extracted_text):
            raise ValueError("quote must occur in extracted source text")
        return self


class EvidenceAssertion(BaseModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_excerpt_ids: list[str] = Field(min_length=1)
    calculation_ids: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)


class SlideStatement(BaseModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    assertion_ids: list[str] = Field(min_length=1)


class ReviewFinding(BaseModel):
    status: Literal["SUPPORTED", "NEEDS_REVIEW", "BLOCK"]
    codes: list[str]
    evidence_ids: list[str]


class ReviewReceipt(BaseModel):
    """A review decision for one immutable version of an authored object."""

    subject_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    author_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    reviewer_kind: Literal["HUMAN", "QUALIFIED_MODEL"]
    qualification_id: str | None = None
    decision: Literal["APPROVE", "REJECT"]
    rationale: str = Field(min_length=12)
    evidence_ids: list[str] = Field(min_length=1)
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def independent_reviewer(self):
        if self.author_id == self.reviewer_id:
            raise ValueError("author cannot review their own content")
        if self.reviewer_kind == "QUALIFIED_MODEL" and not self.qualification_id:
            raise ValueError("model reviewer requires qualification evidence")
        return self


def contract_digest(subject: BaseModel, dependencies: list[BaseModel]) -> str:
    """Bind approval to text and every supporting object, including source hash."""
    payload = {
        "subject": subject.model_dump(mode="json"),
        "dependencies": [item.model_dump(mode="json") for item in dependencies],
    }
    return digest(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def apply_review(finding: ReviewFinding, subject_digest: str, authored_by: str,
                 receipt: ReviewReceipt | None,
                 qualified_review_ids: set[str] | None = None) -> ReviewFinding:
    """A review may resolve uncertainty, but never override a deterministic block."""
    if finding.status == "BLOCK" or receipt is None:
        return finding
    if receipt.subject_digest != subject_digest:
        return ReviewFinding(status="NEEDS_REVIEW", codes=["STALE_REVIEW"],
                             evidence_ids=finding.evidence_ids)
    if set(receipt.evidence_ids) != set(finding.evidence_ids):
        return ReviewFinding(status="BLOCK", codes=["REVIEW_EVIDENCE_MISMATCH"],
                             evidence_ids=finding.evidence_ids)
    if receipt.author_id != authored_by:
        return ReviewFinding(status="BLOCK", codes=["REVIEW_AUTHOR_MISMATCH"],
                             evidence_ids=finding.evidence_ids)
    if (receipt.reviewer_kind == "QUALIFIED_MODEL" and
            receipt.qualification_id not in (qualified_review_ids or set())):
        return ReviewFinding(status="NEEDS_REVIEW", codes=["UNQUALIFIED_REVIEW_ROUTE"],
                             evidence_ids=finding.evidence_ids)
    if receipt.decision == "REJECT":
        return ReviewFinding(status="BLOCK", codes=["INDEPENDENT_REVIEW_REJECTED"],
                             evidence_ids=finding.evidence_ids)
    if finding.status == "SUPPORTED":
        return finding
    return ReviewFinding(status="SUPPORTED", codes=["INDEPENDENT_REVIEW_APPROVED"],
                         evidence_ids=finding.evidence_ids)


def _numeric_mentions(text: str) -> set[str]:
    tokens = re.findall(r"(?<![\d.,])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\d.,])", text)
    return {str(Decimal(token.replace(",", "")).normalize()) for token in tokens}


_UNIT_PATTERN = re.compile(
    r"(?<![\d.,])((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)[\s]*"
    r"(亿元|万元|千元|元|万吨|千吨|吨|千克|克|公里|米|厘米|毫米|"
    r"百分比|百分点|%|人|家|件|单|次|天|月|年|GB|MB|kg|km|m)",
    re.IGNORECASE,
)


def _measurements(text: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for match in _UNIT_PATTERN.finditer(text):
        value = str(Decimal(match.group(1).replace(",", "")).normalize())
        result.setdefault(value, set()).add(match.group(2).casefold())
    return result


def _unit_conflict(source: str, statement: str) -> bool:
    source_units = _measurements(source)
    for value, units in _measurements(statement).items():
        if value in source_units and not units.issubset(source_units[value]):
            return True
    return False


def assess_assertion(assertion: EvidenceAssertion,
                     excerpts: dict[str, SourceExcerpt],
                     calculations: dict[str, ControlledCalculation] | None = None,
                     facts: dict[str, DataFact] | None = None) -> ReviewFinding:
    missing = [key for key in assertion.source_excerpt_ids if key not in excerpts]
    if missing:
        return ReviewFinding(status="BLOCK", codes=["MISSING_SOURCE_EXCERPT"], evidence_ids=missing)
    selected = [excerpts[key] for key in assertion.source_excerpt_ids]
    reversals = [code for item in selected
                 for code in contradiction_signals(item.quote, assertion.text)]
    if reversals:
        return ReviewFinding(status="BLOCK", codes=sorted(set(reversals)),
                             evidence_ids=assertion.source_excerpt_ids)
    allowed_numbers = set().union(*(_numeric_mentions(item.quote) for item in selected))
    calculations = calculations or {}
    for key in assertion.calculation_ids:
        calculation = calculations.get(key)
        if calculation is None:
            return ReviewFinding(status="BLOCK", codes=["MISSING_CALCULATION"], evidence_ids=[key])
        input_source_ids = {facts[fact_id].source_excerpt_id for fact_id in calculation.input_ids
                            if facts is not None and fact_id in facts}
        if input_source_ids - set(assertion.source_excerpt_ids):
            return ReviewFinding(status="BLOCK", codes=["CALCULATION_SOURCE_NOT_LINKED"],
                                 evidence_ids=sorted(input_source_ids - set(assertion.source_excerpt_ids)))
        calc_finding = assess_calculation(calculation, facts or {}, excerpts)
        if calc_finding.status != "SUPPORTED":
            return calc_finding
        allowed_numbers.add(str(Decimal(calculation.result).normalize()))
    if _numeric_mentions(assertion.text) - allowed_numbers:
        return ReviewFinding(status="BLOCK", codes=["UNSOURCED_NUMBER"],
                             evidence_ids=assertion.source_excerpt_ids + assertion.calculation_ids)
    if _unit_conflict("\n".join(item.quote for item in selected), assertion.text):
        return ReviewFinding(status="BLOCK", codes=["UNIT_MISMATCH"],
                             evidence_ids=assertion.source_excerpt_ids)
    if len(selected) > 1:
        # Multi-span synthesis is allowed, but cannot be certified by a lexical check.
        return ReviewFinding(status="NEEDS_REVIEW", codes=["MULTI_SPAN_SYNTHESIS"],
                             evidence_ids=assertion.source_excerpt_ids)
    if len(selected) == 1 and _compact(assertion.text) == _compact(selected[0].quote):
        return ReviewFinding(status="SUPPORTED", codes=["VERBATIM_SOURCE_SPAN"],
                             evidence_ids=assertion.source_excerpt_ids)
    omissions = [code for item in selected
                 for code in missing_source_signals(item.quote, assertion.text)]
    return ReviewFinding(status="NEEDS_REVIEW",
                         codes=sorted(set(omissions)) or ["SEMANTIC_PARAPHRASE_REVIEW"],
                         evidence_ids=assertion.source_excerpt_ids)


def assess_slide_statement(statement: SlideStatement,
                           assertions: dict[str, EvidenceAssertion]) -> ReviewFinding:
    missing = [key for key in statement.assertion_ids if key not in assertions]
    if missing:
        return ReviewFinding(status="BLOCK", codes=["MISSING_ASSERTION"], evidence_ids=missing)
    selected = [assertions[key] for key in statement.assertion_ids]
    reversals = [code for item in selected
                 for code in contradiction_signals(item.text, statement.text)]
    if reversals:
        return ReviewFinding(status="BLOCK", codes=sorted(set(reversals)),
                             evidence_ids=statement.assertion_ids)
    allowed_numbers = set().union(*(_numeric_mentions(item.text) for item in selected))
    if _numeric_mentions(statement.text) - allowed_numbers:
        return ReviewFinding(status="BLOCK", codes=["UNAPPROVED_SLIDE_NUMBER"],
                             evidence_ids=statement.assertion_ids)
    if _unit_conflict("\n".join(item.text for item in selected), statement.text):
        return ReviewFinding(status="BLOCK", codes=["UNAPPROVED_SLIDE_UNIT"],
                             evidence_ids=statement.assertion_ids)
    if len(selected) == 1 and _compact(statement.text) == _compact(selected[0].text):
        return ReviewFinding(status="SUPPORTED", codes=["UNCHANGED_ASSERTION"],
                             evidence_ids=statement.assertion_ids)
    return ReviewFinding(status="NEEDS_REVIEW", codes=["SLIDE_PARAPHRASE_REVIEW"],
                         evidence_ids=statement.assertion_ids)


class ControlledCalculation(BaseModel):
    id: str = Field(min_length=1)
    operation: Literal["SUM", "DIFFERENCE", "RATIO", "PERCENT_CHANGE"]
    inputs: list[str] = Field(min_length=2, max_length=2)
    input_ids: list[str] = Field(min_length=2, max_length=2)
    result: str
    unit: str

    @model_validator(mode="after")
    def check_result(self):
        if len(set(self.input_ids)) != 2:
            raise ValueError("calculation inputs must refer to two distinct facts")
        try:
            left, right = (Decimal(value) for value in self.inputs)
            expected = {
                "SUM": lambda: left + right,
                "DIFFERENCE": lambda: right - left,
                "RATIO": lambda: right / left,
                "PERCENT_CHANGE": lambda: (right - left) / left * 100,
            }[self.operation]()
            actual = Decimal(self.result)
        except (InvalidOperation, ZeroDivisionError) as exc:
            raise ValueError("calculation has invalid input or division by zero") from exc
        if not all(value.is_finite() for value in (left, right, actual)):
            raise ValueError("calculation values must be finite")
        if expected != actual:
            raise ValueError("result does not equal the declared calculation")
        if self.operation == "PERCENT_CHANGE" and self.unit not in {"%", "percent"}:
            raise ValueError("percent change must use a percent unit")
        return self


class DataFact(BaseModel):
    id: str = Field(min_length=1)
    source_excerpt_id: str = Field(min_length=1)
    value: str = Field(min_length=1)
    unit: str = Field(min_length=1)

    @model_validator(mode="after")
    def finite_number(self):
        try:
            number = Decimal(self.value)
        except InvalidOperation as exc:
            raise ValueError("data fact must contain a decimal number") from exc
        if not number.is_finite():
            raise ValueError("data fact must contain a finite number")
        return self


def assess_calculation(calculation: ControlledCalculation,
                       facts: dict[str, DataFact],
                       excerpts: dict[str, SourceExcerpt]) -> ReviewFinding:
    missing = [key for key in calculation.input_ids if key not in facts]
    if missing:
        return ReviewFinding(status="BLOCK", codes=["MISSING_DATA_FACT"], evidence_ids=missing)
    inputs = [facts[key] for key in calculation.input_ids]
    missing_sources = [fact.source_excerpt_id for fact in inputs
                       if fact.source_excerpt_id not in excerpts]
    if missing_sources:
        return ReviewFinding(status="BLOCK", codes=["MISSING_SOURCE_EXCERPT"],
                             evidence_ids=missing_sources)
    if any(Decimal(fact.value) != Decimal(value)
           for fact, value in zip(inputs, calculation.inputs)):
        return ReviewFinding(status="BLOCK", codes=["CALCULATION_INPUT_MISMATCH"],
                             evidence_ids=calculation.input_ids)
    for fact in inputs:
        quote = excerpts[fact.source_excerpt_id].quote
        numeric_pattern = rf"(?<![\d.,]){re.escape(fact.value)}(?![\d.,])\s*{re.escape(fact.unit)}"
        if not re.search(numeric_pattern, quote):
            return ReviewFinding(status="NEEDS_REVIEW", codes=["DATA_FACT_SOURCE_BINDING"],
                                 evidence_ids=[fact.source_excerpt_id])
    if inputs[0].unit != inputs[1].unit:
        return ReviewFinding(status="BLOCK", codes=["INCOMPATIBLE_INPUT_UNITS"],
                             evidence_ids=calculation.input_ids)
    if calculation.operation in {"SUM", "DIFFERENCE"} and calculation.unit != inputs[0].unit:
        return ReviewFinding(status="BLOCK", codes=["RESULT_UNIT_MISMATCH"],
                             evidence_ids=calculation.input_ids)
    if calculation.operation == "RATIO" and calculation.unit not in {"ratio", "倍", "x"}:
        return ReviewFinding(status="BLOCK", codes=["RESULT_UNIT_MISMATCH"],
                             evidence_ids=calculation.input_ids)
    return ReviewFinding(status="SUPPORTED", codes=["CONTROLLED_CALCULATION"],
                         evidence_ids=calculation.input_ids)
