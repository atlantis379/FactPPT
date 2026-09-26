"""Positive/negative calibration for the v0.6 medical source/privacy gates."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
from pathlib import Path

from medical_gates import (
    PRIVACY_SURFACES,
    validate_case_boundary,
    validate_document_structure,
    validate_fact_oracle,
    validate_privacy_gate,
    validate_source_intake,
    validate_source_version_chain,
)


SHA = "a" * 64


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def oracle() -> dict:
    return {"source_sha256": SHA, "total_pages": 2, "extraction_run_id": "extract-1", "extractor_identity": "extractor-a", "review_run_id": "review-1", "reviewer_identity": "reviewer-b", "denominator_status": "REVIEWED_COMPLETE", "page_reviews": [{"page_number": 1, "status": "REVIEWED", "review_evidence_refs": ["p1"]}, {"page_number": 2, "status": "REVIEWED_NO_SUBSTANTIVE_CONTENT", "review_evidence_refs": ["p2"]}], "facts": [{"fact_id": "f1", "risk": "RED", "review_status": "APPROVED", "source_anchors": ["p1:r1"]}], "reviewer_signed_at": "2026-09-07T00:00:00Z"}


def chain() -> dict:
    return {"sources": [{"source_id": "old"}, {"source_id": "new"}], "relations": [{"from_source_id": "old", "to_source_id": "new", "relation_type": "CORRECTED_BY", "explicit_evidence_ref": "new:p5"}], "effective_source_ids": ["new"], "effective_claim_ids": ["f:v2"], "corrections": [{"correction_id": "c1", "correction_notice_anchor": "new:p5", "old_fact": {"claim_id": "f:v1", "source_id": "old", "status": "SUPERSEDED"}, "effective_fact": {"claim_id": "f:v2", "source_id": "new", "status": "EFFECTIVE"}}]}


def case_review() -> dict:
    return {"claims": [{"claim_id": "case1", "source_function": "CASE_REPORT", "source_language_strength": "OBSERVED", "target_scope": "SINGLE_CASE", "assertion_role": "OBSERVATION", "provenance": "SOURCE", "external_support_refs": [], "human_review_status": "NOT_REQUIRED"}]}


def document() -> dict:
    return {"total_pages": 2, "pages": [{"page_number": 1, "text_extraction_quality": "GOOD", "rendered_review_status": "NOT_APPLICABLE", "ocr_status": "NOT_APPLICABLE", "contains_red_exact_text": False, "exact_text_authority": "NATIVE_TEXT"}, {"page_number": 2, "text_extraction_quality": "CORRUPT", "rendered_review_status": "PASS", "ocr_status": "PASS_SECONDARY_ONLY", "contains_red_exact_text": True, "exact_text_authority": "HUMAN_VERIFIED"}], "tables": [{"table_id": "t1", "page_numbers": [1, 2], "continuation_group_id": "tg1", "repeated_header_verified": True, "footnote_ownership_verified": True, "cell_ownership_verified": True}], "dicom_assets": [{"asset_id": "d1", "metadata_scan_status": "PASS", "pixel_overlay_scan_status": "PASS", "evidence_refs": ["d1:audit"]}]}


def privacy() -> dict:
    surfaces = []
    for name in PRIVACY_SURFACES:
        if name in {"DICOM_METADATA", "DICOM_PIXEL_OVERLAY", "FACE_OR_DISTINCTIVE_MARK"}:
            surfaces.append({"surface": name, "status": "NOT_APPLICABLE", "reason": "No applicable object", "evidence_refs": [], "findings": []})
        else:
            surfaces.append({"surface": name, "status": "PASS", "evidence_refs": [name], "findings": []})
    return {"artifact_sha256": SHA, "total_pages": 1, "pages": [{"page_number": 1, "surfaces": surfaces}], "post_transform_residual_scan": {"status": "PASS", "artifact_sha256": SHA}, "cross_page_consistency": {"status": "PASS", "artifact_sha256": SHA}, "reviewer_identity": "privacy-reviewer", "reviewed_at": "2026-09-07T00:00:00Z"}


def run(out: Path) -> int:
    if out.exists():
        raise FileExistsError("Use a new evidence directory")
    out.mkdir(parents=True)
    records = []

    def case(case_id: str, payload: dict, expected: bool, validator) -> None:
        errors = validator(copy.deepcopy(payload))
        accepted = not errors
        result = {"case_id": case_id, "expected_accept": expected, "accepted": accepted, "errors": errors, "status": "PASS" if accepted == expected else "FAIL"}
        write(out / f"{case_id}.json", {"input": payload, "result": result})
        records.append(result)

    good_pdf = out / "valid-source.pdf"
    good_pdf.write_bytes(b"%PDF-1.7\n%%EOF")
    intake = {"path": good_pdf.name, "http_status": 200, "final_url": "https://example.org/source.pdf", "declared_content_type": "application/pdf", "byte_length": good_pdf.stat().st_size, "sha256": hashlib.sha256(good_pdf.read_bytes()).hexdigest(), "retrieved_at": "2026-09-07T00:00:00Z", "redirect_chain": []}
    case("SOURCE_INTAKE_PASS", intake, True, lambda p: validate_source_intake(p, out))
    bad_intake = dict(intake, declared_content_type="text/html")
    case("SOURCE_INTAKE_MIME_FAIL", bad_intake, False, lambda p: validate_source_intake(p, out))

    case("FACT_ORACLE_PASS", oracle(), True, validate_fact_oracle)
    bad = oracle(); bad["review_run_id"] = bad["extraction_run_id"]
    case("FACT_ORACLE_SELF_REVIEW_FAIL", bad, False, validate_fact_oracle)
    case("SOURCE_CHAIN_PASS", chain(), True, validate_source_version_chain)
    bad = chain(); bad["effective_claim_ids"].append("f:v1")
    case("SOURCE_CHAIN_STALE_FACT_FAIL", bad, False, validate_source_version_chain)
    case("CASE_BOUNDARY_PASS", case_review(), True, validate_case_boundary)
    bad = case_review(); bad["claims"][0].update(target_scope="POPULATION", assertion_role="CAUSAL")
    case("CASE_BOUNDARY_GENERALIZATION_FAIL", bad, False, validate_case_boundary)
    case("DOCUMENT_STRUCTURE_PASS", document(), True, validate_document_structure)
    bad = document(); bad["dicom_assets"][0]["pixel_overlay_scan_status"] = "NOT_TESTABLE"
    case("DOCUMENT_DICOM_NOT_TESTABLE_FAIL", bad, False, validate_document_structure)
    case("PRIVACY_PAGE_SURFACES_PASS", privacy(), True, validate_privacy_gate)
    bad = privacy(); bad["pages"][0]["surfaces"].pop()
    case("PRIVACY_MISSING_SURFACE_FAIL", bad, False, validate_privacy_gate)

    summary = {"benchmark": "MEDICAL_GATES_v0.6", "python": platform.python_version(), "passed": sum(item["status"] == "PASS" for item in records), "total": len(records), "failed": [item["case_id"] for item in records if item["status"] != "PASS"]}
    write(out / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.out))
