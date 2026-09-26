"""Stateless verification for the cross-industry v2 content contract.

This endpoint reports what can be proven mechanically. It does not mint human
or model approval receipts; a future authenticated review workflow owns those.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.content_contract import (
    ControlledCalculation,
    DataFact,
    EvidenceAssertion,
    ReviewFinding,
    ReviewReceipt,
    SlideStatement,
    SourceExcerpt,
    apply_review,
    assess_assertion,
    assess_calculation,
    assess_slide_statement,
    contract_digest,
)
from app.source_extract import SourceCapacityError, SourceExtraction, extract_source


class ContentPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_excerpts: list[SourceExcerpt] = Field(min_length=1)
    assertions: list[EvidenceAssertion] = Field(min_length=1)
    slide_statements: list[SlideStatement] = Field(default_factory=list)
    data_facts: list[DataFact] = Field(default_factory=list)
    calculations: list[ControlledCalculation] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self):
        all_ids = []
        for label, items in (("source excerpt", self.source_excerpts),
                             ("assertion", self.assertions),
                             ("slide statement", self.slide_statements),
                             ("data fact", self.data_facts),
                             ("calculation", self.calculations)):
            ids = [item.id for item in items]
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate {label} id")
            all_ids.extend(ids)
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("object ids must be unique across content kinds")
        return self


class ContentReport(BaseModel):
    status: str
    source_findings: dict[str, ReviewFinding]
    assertion_findings: dict[str, ReviewFinding]
    slide_findings: dict[str, ReviewFinding]
    calculation_findings: dict[str, ReviewFinding]


def verify_content_package(
    package: ContentPackage, *, authored_by: str | None = None,
    trusted_assertion_reviews: dict[str, ReviewReceipt] | None = None,
    trusted_slide_reviews: dict[str, ReviewReceipt] | None = None,
    qualified_review_ids: set[str] | None = None,
    trusted_excerpts: dict[str, SourceExcerpt] | None = None,
    incomplete_source_hashes: set[str] | None = None,
) -> ContentReport:
    """Review inputs are trusted server-side arguments, absent from the public API."""
    excerpts = {item.id: item for item in package.source_excerpts}
    source_findings = {}
    for item in package.source_excerpts:
        trusted = (trusted_excerpts or {}).get(item.id)
        if trusted is None:
            source_findings[item.id] = ReviewFinding(
                status="NEEDS_REVIEW", codes=["SOURCE_FILE_NOT_VERIFIED"], evidence_ids=[item.id])
        elif item != trusted:
            source_findings[item.id] = ReviewFinding(
                status="BLOCK", codes=["SOURCE_EXCERPT_MISMATCH"], evidence_ids=[item.id])
        elif item.source_sha256 in (incomplete_source_hashes or set()):
            source_findings[item.id] = ReviewFinding(
                status="NEEDS_REVIEW", codes=["SOURCE_EXTRACTION_INCOMPLETE"],
                evidence_ids=[item.id])
        else:
            source_findings[item.id] = ReviewFinding(
                status="SUPPORTED", codes=["SERVER_EXTRACTED_SOURCE"], evidence_ids=[item.id])
    assertions = {item.id: item for item in package.assertions}
    facts = {item.id: item for item in package.data_facts}
    calculations = {item.id: item for item in package.calculations}
    assertion_findings = {}
    for item in package.assertions:
        finding = assess_assertion(item, excerpts, calculations, facts)
        upstream_sources = [source_findings[key] for key in item.source_excerpt_ids
                            if key in source_findings]
        if finding.status != "BLOCK" and any(source.status == "BLOCK" for source in upstream_sources):
            finding = ReviewFinding(status="BLOCK", codes=["UPSTREAM_SOURCE_BLOCKED"],
                                    evidence_ids=item.source_excerpt_ids)
        elif finding.status == "SUPPORTED" and any(source.status == "NEEDS_REVIEW" for source in upstream_sources):
            finding = ReviewFinding(status="NEEDS_REVIEW", codes=["UPSTREAM_SOURCE_NOT_VERIFIED"],
                                    evidence_ids=item.source_excerpt_ids)
        if authored_by is not None:
            dependencies = [excerpts[key] for key in item.source_excerpt_ids if key in excerpts]
            dependencies += [calculations[key] for key in item.calculation_ids if key in calculations]
            key = contract_digest(item, dependencies)
            if all(source.status == "SUPPORTED" for source in upstream_sources):
                finding = apply_review(finding, key, authored_by,
                                       (trusted_assertion_reviews or {}).get(item.id),
                                       qualified_review_ids)
        assertion_findings[item.id] = finding
    slide_findings = {}
    for statement in package.slide_statements:
        finding = assess_slide_statement(statement, assertions)
        if authored_by is not None:
            dependencies = [assertions[key] for key in statement.assertion_ids
                            if key in assertions]
            key = contract_digest(statement, dependencies)
            finding = apply_review(finding, key, authored_by,
                                   (trusted_slide_reviews or {}).get(statement.id),
                                   qualified_review_ids)
        upstream = [assertion_findings[key] for key in statement.assertion_ids
                    if key in assertion_findings]
        if finding.status != "BLOCK" and any(item.status == "BLOCK" for item in upstream):
            finding = ReviewFinding(status="BLOCK", codes=["UPSTREAM_ASSERTION_BLOCKED"],
                                    evidence_ids=statement.assertion_ids)
        elif finding.status == "SUPPORTED" and any(item.status == "NEEDS_REVIEW" for item in upstream):
            finding = ReviewFinding(status="NEEDS_REVIEW", codes=["UPSTREAM_ASSERTION_NEEDS_REVIEW"],
                                    evidence_ids=statement.assertion_ids)
        slide_findings[statement.id] = finding
    calculation_findings = {}
    for item in package.calculations:
        finding = assess_calculation(item, facts, excerpts)
        source_ids = [facts[key].source_excerpt_id for key in item.input_ids if key in facts]
        upstream_sources = [source_findings[key] for key in source_ids if key in source_findings]
        if finding.status != "BLOCK" and any(source.status == "BLOCK" for source in upstream_sources):
            finding = ReviewFinding(status="BLOCK", codes=["UPSTREAM_SOURCE_BLOCKED"],
                                    evidence_ids=source_ids)
        elif finding.status == "SUPPORTED" and any(source.status == "NEEDS_REVIEW" for source in upstream_sources):
            finding = ReviewFinding(status="NEEDS_REVIEW", codes=["UPSTREAM_SOURCE_NOT_VERIFIED"],
                                    evidence_ids=source_ids)
        calculation_findings[item.id] = finding
    all_findings = [*source_findings.values(), *assertion_findings.values(), *slide_findings.values(),
                    *calculation_findings.values()]
    status = ("BLOCK" if any(item.status == "BLOCK" for item in all_findings) else
              "NEEDS_REVIEW" if any(item.status == "NEEDS_REVIEW" for item in all_findings) else
              "SUPPORTED")
    return ContentReport(status=status, source_findings=source_findings,
                         assertion_findings=assertion_findings,
                         slide_findings=slide_findings,
                         calculation_findings=calculation_findings)


def verify_content_files(package: ContentPackage,
                         files: list[tuple[str, bytes]], *,
                         max_total_bytes: int = 100 * 1024 * 1024,
                         max_files: int = 20) -> tuple[ContentReport, list[SourceExtraction]]:
    """Build trusted excerpts from actual supplied file bytes, then verify."""
    if len(files) > max_files or sum(len(content) for _, content in files) > max_total_bytes:
        raise SourceCapacityError("source batch exceeds declared file or byte limit")
    extractions = [extract_source(filename, content) for filename, content in files]
    trusted = {item.id: item for extraction in extractions for item in extraction.excerpts}
    incomplete_hashes = {item.source_sha256 for item in extractions
                         if item.status != "COMPLETE"}
    report = verify_content_package(package, trusted_excerpts=trusted,
                                    incomplete_source_hashes=incomplete_hashes)
    return report, extractions
