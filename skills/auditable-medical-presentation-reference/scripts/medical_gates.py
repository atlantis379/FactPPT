"""Deterministic high-risk gates for source intake, truth review and privacy.

These validators check whether independently produced evidence is complete and
internally consistent.  They do not infer clinical truth, perform OCR, identify
faces, or de-identify pixels by themselves.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse


HEX64 = re.compile(r"^[0-9a-f]{64}$")
PRIVACY_SURFACES = (
    "TEXT_LAYER",
    "SPEAKER_NOTES",
    "EMBEDDED_IMAGE_OCR",
    "DICOM_METADATA",
    "DICOM_PIXEL_OVERLAY",
    "FACE_OR_DISTINCTIVE_MARK",
    "DOCUMENT_METADATA",
    "FILENAME_ATTACHMENT_NAME",
)
ACCEPTED_SURFACE_RESULTS = {"PASS", "NOT_APPLICABLE"}


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and HEX64.fullmatch(value.lower()) is not None


def _unique(values: list[object]) -> bool:
    return len(values) == len(set(values))


def validate_source_intake(record: dict, evidence_root: Path) -> list[str]:
    """Reject mislabeled downloads and unverifiable source identity at W00."""
    errors: list[str] = []
    raw_path = record.get("path")
    try:
        path = (evidence_root / raw_path).resolve() if raw_path else Path()
        root = evidence_root.resolve()
        if not path.is_relative_to(root):
            return ["SOURCE_PATH_OUTSIDE_EVIDENCE_ROOT"]
    except (OSError, TypeError, ValueError):
        return ["SOURCE_PATH_INVALID"]
    if not path.is_file():
        return ["SOURCE_FILE_MISSING"]

    status = record.get("http_status")
    if not isinstance(status, int) or not 200 <= status < 300:
        errors.append("SOURCE_HTTP_STATUS_NOT_SUCCESS")
    final_url = record.get("final_url", "")
    parsed = urlparse(final_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        errors.append("SOURCE_FINAL_URL_INVALID")
    if not record.get("retrieved_at"):
        errors.append("SOURCE_RETRIEVAL_TIME_MISSING")

    declared = str(record.get("declared_content_type", "")).split(";", 1)[0].strip().lower()
    head = path.read_bytes()[:16]
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        if declared != "application/pdf":
            errors.append("SOURCE_CONTENT_TYPE_MISMATCH")
        if not head.startswith(b"%PDF-"):
            errors.append("SOURCE_MAGIC_MISMATCH")
    elif suffix == ".pptx":
        if declared not in {
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/zip",
        }:
            errors.append("SOURCE_CONTENT_TYPE_MISMATCH")
        if not head.startswith(b"PK\x03\x04"):
            errors.append("SOURCE_MAGIC_MISMATCH")
    else:
        errors.append("SOURCE_EXTENSION_UNSUPPORTED")

    actual_size = path.stat().st_size
    if record.get("byte_length") != actual_size:
        errors.append("SOURCE_BYTE_LENGTH_MISMATCH")
    expected_hash = str(record.get("sha256", "")).lower()
    if not _is_sha(expected_hash) or _digest(path) != expected_hash:
        errors.append("SOURCE_HASH_MISMATCH")
    if record.get("redirect_chain") is None:
        errors.append("SOURCE_REDIRECT_CHAIN_UNRECORDED")
    return sorted(set(errors))


def validate_fact_oracle(record: dict) -> list[str]:
    """Require an independent, page-complete truth inventory before W02-FSC PASS."""
    errors: list[str] = []
    if not _is_sha(record.get("source_sha256")):
        errors.append("ORACLE_SOURCE_HASH_INVALID")
    extraction_run = record.get("extraction_run_id")
    review_run = record.get("review_run_id")
    if not extraction_run or not review_run:
        errors.append("ORACLE_RUN_ID_MISSING")
    if extraction_run == review_run:
        errors.append("ORACLE_SELF_REVIEW")
    if record.get("reviewer_identity") in {None, "", record.get("extractor_identity")}:
        errors.append("ORACLE_REVIEWER_NOT_INDEPENDENT")
    total_pages = record.get("total_pages")
    if not isinstance(total_pages, int) or total_pages < 1:
        return sorted(set(errors + ["ORACLE_PAGE_DENOMINATOR_INVALID"]))

    page_reviews = record.get("page_reviews", [])
    page_numbers = [item.get("page_number") for item in page_reviews]
    if not _unique(page_numbers):
        errors.append("ORACLE_DUPLICATE_PAGE_REVIEW")
    if set(page_numbers) != set(range(1, total_pages + 1)):
        errors.append("ORACLE_PAGE_COVERAGE_GAP")
    for item in page_reviews:
        page = item.get("page_number", "UNKNOWN")
        if item.get("status") not in {"REVIEWED", "REVIEWED_NO_SUBSTANTIVE_CONTENT"}:
            errors.append(f"PAGE_{page}:ORACLE_REVIEW_INCOMPLETE")
        if not item.get("review_evidence_refs"):
            errors.append(f"PAGE_{page}:ORACLE_REVIEW_EVIDENCE_MISSING")

    facts = record.get("facts", [])
    fact_ids = [item.get("fact_id") for item in facts]
    if not _unique(fact_ids):
        errors.append("ORACLE_DUPLICATE_FACT_ID")
    for fact in facts:
        fact_id = fact.get("fact_id", "UNKNOWN")
        if not fact.get("source_anchors"):
            errors.append(f"{fact_id}:ORACLE_SOURCE_ANCHOR_MISSING")
        if fact.get("risk") == "RED" and fact.get("review_status") != "APPROVED":
            errors.append(f"{fact_id}:RED_FACT_NOT_APPROVED")
        if fact.get("review_status") == "DISAGREEMENT" and not fact.get("resolution_ref"):
            errors.append(f"{fact_id}:ORACLE_DISAGREEMENT_UNRESOLVED")
    if record.get("denominator_status") != "REVIEWED_COMPLETE":
        errors.append("ORACLE_DENOMINATOR_NOT_REVIEWED_COMPLETE")
    if not record.get("reviewer_signed_at"):
        errors.append("ORACLE_SIGNATURE_MISSING")
    return sorted(set(errors))


def validate_source_version_chain(record: dict) -> list[str]:
    """Validate explicit document/fact supersession without recency inference."""
    errors: list[str] = []
    sources = record.get("sources", [])
    source_ids = [item.get("source_id") for item in sources]
    if not _unique(source_ids):
        errors.append("SOURCE_CHAIN_DUPLICATE_SOURCE_ID")
    source_set = set(source_ids)
    graph: dict[str, set[str]] = {source_id: set() for source_id in source_set}
    for edge in record.get("relations", []):
        old, new = edge.get("from_source_id"), edge.get("to_source_id")
        if old not in source_set or new not in source_set or old == new:
            errors.append("SOURCE_CHAIN_RELATION_INVALID")
            continue
        if edge.get("relation_type") not in {"CORRECTED_BY", "AMENDED_BY", "SUPERSEDED_BY"}:
            errors.append("SOURCE_CHAIN_RELATION_TYPE_INVALID")
        if not edge.get("explicit_evidence_ref"):
            errors.append("SOURCE_CHAIN_EXPLICIT_EVIDENCE_MISSING")
        graph[old].add(new)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            errors.append("SOURCE_CHAIN_CYCLE")
            return
        if node in visited:
            return
        visiting.add(node)
        for child in graph.get(node, set()):
            visit(child)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)

    effective_sources = set(record.get("effective_source_ids", []))
    if not effective_sources or not effective_sources <= source_set:
        errors.append("SOURCE_CHAIN_EFFECTIVE_SOURCE_INVALID")
    correction_ids: list[object] = []
    for correction in record.get("corrections", []):
        correction_id = correction.get("correction_id", "UNKNOWN")
        correction_ids.append(correction_id)
        old_fact = correction.get("old_fact", {})
        new_fact = correction.get("effective_fact", {})
        if old_fact.get("claim_id") == new_fact.get("claim_id"):
            errors.append(f"{correction_id}:CORRECTION_FACT_ID_NOT_VERSIONED")
        if old_fact.get("status") != "SUPERSEDED":
            errors.append(f"{correction_id}:OLD_FACT_NOT_SUPERSEDED")
        if new_fact.get("status") != "EFFECTIVE":
            errors.append(f"{correction_id}:NEW_FACT_NOT_EFFECTIVE")
        if not correction.get("correction_notice_anchor"):
            errors.append(f"{correction_id}:CORRECTION_NOTICE_ANCHOR_MISSING")
        if new_fact.get("source_id") not in effective_sources:
            errors.append(f"{correction_id}:EFFECTIVE_FACT_SOURCE_NOT_CURRENT")
        if old_fact.get("claim_id") in record.get("effective_claim_ids", []):
            errors.append(f"{correction_id}:SUPERSEDED_FACT_STILL_EFFECTIVE")
    if not _unique(correction_ids):
        errors.append("SOURCE_CHAIN_DUPLICATE_CORRECTION_ID")
    return sorted(set(errors))


def validate_case_boundary(record: dict) -> list[str]:
    """Block single-case observations from silently becoming population claims."""
    errors: list[str] = []
    for claim in record.get("claims", []):
        claim_id = claim.get("claim_id", "UNKNOWN")
        if claim.get("source_function") != "CASE_REPORT":
            continue
        generalized = claim.get("target_scope") not in {"SINGLE_CASE", "CASE_SERIES_DESCRIPTIVE"}
        strong_relation = claim.get("assertion_role") in {
            "CAUSAL",
            "EFFICACY",
            "DIAGNOSTIC_SUFFICIENCY",
            "POPULATION_RECOMMENDATION",
        }
        if generalized or strong_relation:
            if claim.get("provenance") != "SYNTHESIS":
                errors.append(f"{claim_id}:CASE_GENERALIZATION_NOT_SYNTHESIS")
            if not claim.get("external_support_refs"):
                errors.append(f"{claim_id}:CASE_GENERALIZATION_EXTERNAL_SUPPORT_MISSING")
            if claim.get("human_review_status") != "APPROVED":
                errors.append(f"{claim_id}:CASE_GENERALIZATION_HUMAN_REVIEW_MISSING")
        if claim.get("source_language_strength") == "OBSERVED" and claim.get("assertion_role") == "CAUSAL":
            errors.append(f"{claim_id}:CASE_CAUSALITY_UPGRADE")
    return sorted(set(errors))


def validate_document_structure(record: dict) -> list[str]:
    """Audit page completeness, table continuations and OCR/render routing."""
    errors: list[str] = []
    total_pages = record.get("total_pages")
    pages = record.get("pages", [])
    if not isinstance(total_pages, int) or total_pages < 1:
        return ["DOCUMENT_PAGE_DENOMINATOR_INVALID"]
    numbers = [page.get("page_number") for page in pages]
    if not _unique(numbers):
        errors.append("DOCUMENT_DUPLICATE_PAGE")
    if set(numbers) != set(range(1, total_pages + 1)):
        errors.append("DOCUMENT_PAGE_COVERAGE_GAP")
    for page in pages:
        page_no = page.get("page_number", "UNKNOWN")
        quality = page.get("text_extraction_quality")
        if quality in {"CORRUPT", "IMAGE_ONLY", "EMPTY_UNEXPLAINED"}:
            if page.get("rendered_review_status") != "PASS":
                errors.append(f"PAGE_{page_no}:RENDERED_REVIEW_REQUIRED")
            if page.get("ocr_status") not in {"PASS", "PASS_SECONDARY_ONLY"}:
                errors.append(f"PAGE_{page_no}:OCR_REQUIRED")
        if page.get("contains_red_exact_text") and page.get("exact_text_authority") == "OCR_ONLY":
            errors.append(f"PAGE_{page_no}:OCR_CANNOT_APPROVE_RED_EXACT_TEXT")

    table_ids: list[object] = []
    for table in record.get("tables", []):
        table_id = table.get("table_id", "UNKNOWN")
        table_ids.append(table_id)
        table_pages = table.get("page_numbers", [])
        if not table_pages or any(page not in set(numbers) for page in table_pages):
            errors.append(f"{table_id}:TABLE_PAGE_REFERENCE_INVALID")
        if len(table_pages) > 1:
            if not table.get("continuation_group_id"):
                errors.append(f"{table_id}:TABLE_CONTINUATION_ID_MISSING")
            if table_pages != list(range(min(table_pages), max(table_pages) + 1)):
                errors.append(f"{table_id}:TABLE_CONTINUATION_NONCONTIGUOUS")
            if table.get("repeated_header_verified") is not True:
                errors.append(f"{table_id}:TABLE_HEADER_NOT_VERIFIED")
        if table.get("footnote_ownership_verified") is not True:
            errors.append(f"{table_id}:TABLE_FOOTNOTE_OWNERSHIP_UNVERIFIED")
        if table.get("cell_ownership_verified") is not True:
            errors.append(f"{table_id}:TABLE_CELL_OWNERSHIP_UNVERIFIED")
    if not _unique(table_ids):
        errors.append("DOCUMENT_DUPLICATE_TABLE_ID")

    for asset in record.get("dicom_assets", []):
        asset_id = asset.get("asset_id", "UNKNOWN")
        if asset.get("metadata_scan_status") != "PASS":
            errors.append(f"{asset_id}:DICOM_METADATA_SCAN_NOT_PASS")
        if asset.get("pixel_overlay_scan_status") != "PASS":
            errors.append(f"{asset_id}:DICOM_PIXEL_SCAN_NOT_PASS")
        if not asset.get("evidence_refs"):
            errors.append(f"{asset_id}:DICOM_SCAN_EVIDENCE_MISSING")
    return sorted(set(errors))


def validate_privacy_gate(record: dict) -> list[str]:
    """Require page-by-page, surface-by-surface residual privacy evidence."""
    errors: list[str] = []
    artifact_hash = record.get("artifact_sha256")
    if not _is_sha(artifact_hash):
        errors.append("PRIVACY_ARTIFACT_HASH_INVALID")
    total_pages = record.get("total_pages")
    if not isinstance(total_pages, int) or total_pages < 1:
        return sorted(set(errors + ["PRIVACY_PAGE_DENOMINATOR_INVALID"]))
    pages = record.get("pages", [])
    page_numbers = [page.get("page_number") for page in pages]
    if not _unique(page_numbers):
        errors.append("PRIVACY_DUPLICATE_PAGE")
    if set(page_numbers) != set(range(1, total_pages + 1)):
        errors.append("PRIVACY_PAGE_COVERAGE_GAP")

    for page in pages:
        page_no = page.get("page_number", "UNKNOWN")
        surfaces = page.get("surfaces", [])
        names = [surface.get("surface") for surface in surfaces]
        if not _unique(names):
            errors.append(f"PAGE_{page_no}:PRIVACY_DUPLICATE_SURFACE")
        missing = set(PRIVACY_SURFACES) - set(names)
        extra = set(names) - set(PRIVACY_SURFACES)
        if missing:
            errors.append(f"PAGE_{page_no}:PRIVACY_SURFACE_MISSING:{','.join(sorted(missing))}")
        if extra:
            errors.append(f"PAGE_{page_no}:PRIVACY_SURFACE_UNKNOWN:{','.join(sorted(extra))}")
        for surface in surfaces:
            name = surface.get("surface", "UNKNOWN")
            status = surface.get("status")
            if status not in ACCEPTED_SURFACE_RESULTS:
                errors.append(f"PAGE_{page_no}:{name}:PRIVACY_SURFACE_NOT_CLEARED")
            if status == "NOT_APPLICABLE" and not surface.get("reason"):
                errors.append(f"PAGE_{page_no}:{name}:NOT_APPLICABLE_REASON_MISSING")
            if status == "PASS" and not surface.get("evidence_refs"):
                errors.append(f"PAGE_{page_no}:{name}:PRIVACY_EVIDENCE_MISSING")
            for finding in surface.get("findings", []):
                category = finding.get("classification")
                if category == "PATIENT_IDENTIFIER" and finding.get("resolution") != "REMOVED_OR_DEIDENTIFIED":
                    errors.append(f"PAGE_{page_no}:{name}:PATIENT_IDENTIFIER_UNRESOLVED")
                if category == "QUASI_IDENTIFIER" and finding.get("risk_review_status") != "APPROVED":
                    errors.append(f"PAGE_{page_no}:{name}:QUASI_IDENTIFIER_REVIEW_REQUIRED")
                if category == "PUBLIC_CONTACT" and not finding.get("context_evidence_ref"):
                    errors.append(f"PAGE_{page_no}:{name}:PUBLIC_CONTACT_CONTEXT_UNPROVEN")

    residual = record.get("post_transform_residual_scan", {})
    if residual.get("status") != "PASS" or residual.get("artifact_sha256") != artifact_hash:
        errors.append("PRIVACY_POST_TRANSFORM_SCAN_NOT_BOUND_PASS")
    consistency = record.get("cross_page_consistency", {})
    if consistency.get("status") != "PASS" or consistency.get("artifact_sha256") != artifact_hash:
        errors.append("PRIVACY_CROSS_PAGE_CONSISTENCY_NOT_BOUND_PASS")
    if not record.get("reviewer_identity") or not record.get("reviewed_at"):
        errors.append("PRIVACY_REVIEW_ATTESTATION_MISSING")
    return sorted(set(errors))


VALIDATORS = {
    "source-intake": validate_source_intake,
    "fact-oracle": validate_fact_oracle,
    "source-chain": validate_source_version_chain,
    "case-boundary": validate_case_boundary,
    "document-structure": validate_document_structure,
    "privacy-gate": validate_privacy_gate,
}
