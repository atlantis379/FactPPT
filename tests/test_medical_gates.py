from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import jsonschema


SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "auditable-medical-presentation-reference" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from medical_gates import (  # noqa: E402
    PRIVACY_SURFACES,
    validate_case_boundary,
    validate_document_structure,
    validate_fact_oracle,
    validate_privacy_gate,
    validate_source_intake,
    validate_source_version_chain,
)


SHA = "a" * 64


def test_source_intake_accepts_bound_pdf_and_rejects_html_disguised_as_pdf():
    fixture_root = Path(__file__).parent / "fixtures" / "source_intake"
    good = fixture_root / "source_good.pdf"
    record = {
        "schema_version": "0.1",
        "source_id": "fixture-pdf",
        "path": good.name,
        "http_status": 200,
        "final_url": "https://example.org/source.pdf",
        "declared_content_type": "application/pdf",
        "byte_length": good.stat().st_size,
        "sha256": hashlib.sha256(good.read_bytes()).hexdigest(),
        "retrieved_at": "2026-09-07T00:00:00Z",
        "redirect_chain": [],
    }
    assert validate_source_intake(record, fixture_root) == []

    bad = fixture_root / "source_bad.pdf"
    record.update(path=bad.name, byte_length=bad.stat().st_size, sha256=hashlib.sha256(bad.read_bytes()).hexdigest())
    assert "SOURCE_MAGIC_MISMATCH" in validate_source_intake(record, fixture_root)


def fact_oracle():
    return {
        "schema_version": "0.1",
        "source_sha256": SHA,
        "total_pages": 2,
        "extraction_run_id": "extract-1",
        "extractor_identity": "extractor-a",
        "review_run_id": "review-1",
        "reviewer_identity": "reviewer-b",
        "denominator_status": "REVIEWED_COMPLETE",
        "page_reviews": [
            {"page_number": 1, "status": "REVIEWED", "review_evidence_refs": ["render:p1"]},
            {"page_number": 2, "status": "REVIEWED_NO_SUBSTANTIVE_CONTENT", "review_evidence_refs": ["render:p2"]},
        ],
        "facts": [{"fact_id": "dose", "risk": "RED", "review_status": "APPROVED", "source_anchors": ["p1:table1:r2c3"]}],
        "reviewer_signed_at": "2026-09-07T00:00:00Z",
    }


def test_fact_oracle_requires_independence_and_every_page():
    record = fact_oracle()
    assert validate_fact_oracle(record) == []
    record["reviewer_identity"] = record["extractor_identity"]
    record["page_reviews"].pop()
    errors = validate_fact_oracle(record)
    assert "ORACLE_REVIEWER_NOT_INDEPENDENT" in errors
    assert "ORACLE_PAGE_COVERAGE_GAP" in errors


def source_chain():
    return {
        "schema_version": "0.1",
        "sources": [
            {"source_id": "old", "sha256": "b" * 64, "version_label": "original"},
            {"source_id": "new", "sha256": "c" * 64, "version_label": "corrected"},
        ],
        "relations": [{"from_source_id": "old", "to_source_id": "new", "relation_type": "CORRECTED_BY", "explicit_evidence_ref": "new:p5:corrigenda"}],
        "effective_source_ids": ["new"],
        "effective_claim_ids": ["dose:v2"],
        "corrections": [{
            "correction_id": "corr-1",
            "correction_notice_anchor": "new:p5:corrigenda",
            "old_fact": {"claim_id": "dose:v1", "source_id": "old", "status": "SUPERSEDED", "text": "20 mg for 2 days"},
            "effective_fact": {"claim_id": "dose:v2", "source_id": "new", "status": "EFFECTIVE", "text": "20 mg single dose"},
        }],
    }


def test_source_version_chain_rejects_old_fact_in_effective_index():
    record = source_chain()
    assert validate_source_version_chain(record) == []
    record["effective_claim_ids"].append("dose:v1")
    assert "corr-1:SUPERSEDED_FACT_STILL_EFFECTIVE" in validate_source_version_chain(record)


def test_case_report_observation_passes_but_unreviewed_population_claim_blocks():
    observation = {
        "claim_id": "case-observation",
        "source_function": "CASE_REPORT",
        "source_language_strength": "OBSERVED",
        "target_scope": "SINGLE_CASE",
        "assertion_role": "OBSERVATION",
        "provenance": "SOURCE",
        "external_support_refs": [],
        "human_review_status": "NOT_REQUIRED",
    }
    assert validate_case_boundary({"schema_version": "0.1", "claims": [observation]}) == []
    generalized = dict(observation, claim_id="bad", target_scope="POPULATION", assertion_role="EFFICACY")
    errors = validate_case_boundary({"schema_version": "0.1", "claims": [generalized]})
    assert "bad:CASE_GENERALIZATION_NOT_SYNTHESIS" in errors
    assert "bad:CASE_GENERALIZATION_EXTERNAL_SUPPORT_MISSING" in errors
    assert "bad:CASE_GENERALIZATION_HUMAN_REVIEW_MISSING" in errors


def document_structure():
    return {
        "schema_version": "0.1",
        "document_sha256": SHA,
        "total_pages": 2,
        "pages": [
            {"page_number": 1, "text_extraction_quality": "GOOD", "rendered_review_status": "NOT_APPLICABLE", "ocr_status": "NOT_APPLICABLE", "contains_red_exact_text": False, "exact_text_authority": "NATIVE_TEXT"},
            {"page_number": 2, "text_extraction_quality": "CORRUPT", "rendered_review_status": "PASS", "ocr_status": "PASS_SECONDARY_ONLY", "contains_red_exact_text": True, "exact_text_authority": "HUMAN_VERIFIED"},
        ],
        "tables": [{"table_id": "t1", "page_numbers": [1, 2], "continuation_group_id": "tg1", "repeated_header_verified": True, "footnote_ownership_verified": True, "cell_ownership_verified": True}],
        "dicom_assets": [{"asset_id": "d1", "metadata_scan_status": "PASS", "pixel_overlay_scan_status": "PASS", "evidence_refs": ["dicom:audit"]}],
    }


def test_document_structure_requires_table_ownership_and_dicom_pixel_scan():
    record = document_structure()
    assert validate_document_structure(record) == []
    record["tables"][0]["cell_ownership_verified"] = False
    record["dicom_assets"][0]["pixel_overlay_scan_status"] = "NOT_TESTABLE"
    errors = validate_document_structure(record)
    assert "t1:TABLE_CELL_OWNERSHIP_UNVERIFIED" in errors
    assert "d1:DICOM_PIXEL_SCAN_NOT_PASS" in errors


def privacy_record():
    surfaces = []
    for name in PRIVACY_SURFACES:
        if name in {"DICOM_METADATA", "DICOM_PIXEL_OVERLAY", "FACE_OR_DISTINCTIVE_MARK"}:
            surfaces.append({"surface": name, "status": "NOT_APPLICABLE", "reason": "No applicable object on this page", "evidence_refs": [], "findings": []})
        else:
            surfaces.append({"surface": name, "status": "PASS", "evidence_refs": [f"audit:{name}"], "findings": []})
    return {
        "schema_version": "0.1",
        "artifact_sha256": SHA,
        "total_pages": 1,
        "pages": [{"page_number": 1, "surfaces": surfaces}],
        "post_transform_residual_scan": {"status": "PASS", "artifact_sha256": SHA, "evidence_refs": ["residual"]},
        "cross_page_consistency": {"status": "PASS", "artifact_sha256": SHA, "evidence_refs": ["consistency"]},
        "reviewer_identity": "privacy-reviewer",
        "reviewed_at": "2026-09-07T00:00:00Z",
    }


def test_privacy_gate_requires_every_surface_and_hash_bound_residual_scan():
    record = privacy_record()
    assert validate_privacy_gate(record) == []
    record["pages"][0]["surfaces"].pop()
    record["post_transform_residual_scan"]["artifact_sha256"] = "d" * 64
    errors = validate_privacy_gate(record)
    assert any(error.startswith("PAGE_1:PRIVACY_SURFACE_MISSING") for error in errors)
    assert "PRIVACY_POST_TRANSFORM_SCAN_NOT_BOUND_PASS" in errors


def test_privacy_gate_distinguishes_public_contact_and_unresolved_patient_identifier():
    record = privacy_record()
    text = next(item for item in record["pages"][0]["surfaces"] if item["surface"] == "TEXT_LAYER")
    text["findings"] = [
        {"classification": "PUBLIC_CONTACT", "context_evidence_ref": "article:corresponding-author"},
        {"classification": "PATIENT_IDENTIFIER", "resolution": "PENDING"},
    ]
    errors = validate_privacy_gate(record)
    assert "PAGE_1:TEXT_LAYER:PATIENT_IDENTIFIER_UNRESOLVED" in errors
    assert "PAGE_1:TEXT_LAYER:PUBLIC_CONTACT_CONTEXT_UNPROVEN" not in errors


def test_gate_contract_schemas_accept_positive_fixtures():
    schema_root = SCRIPTS.parent / "schemas"
    source_file = Path(__file__).parent / "fixtures" / "source_intake" / "source_good.pdf"
    fixtures = {
        "source_intake_record.v0.1.schema.json": {
            "schema_version": "0.1", "source_id": "fixture-pdf", "path": source_file.name, "http_status": 200,
            "final_url": "https://example.org/source.pdf", "declared_content_type": "application/pdf",
            "byte_length": source_file.stat().st_size, "sha256": hashlib.sha256(source_file.read_bytes()).hexdigest(),
            "retrieved_at": "2026-09-07T00:00:00Z", "redirect_chain": [],
        },
        "fact_oracle_review.v0.1.schema.json": fact_oracle(),
        "source_version_chain.v0.1.schema.json": source_chain(),
        "case_boundary_review.v0.1.schema.json": {
            "schema_version": "0.1",
            "claims": [{
                "claim_id": "case-observation", "source_function": "CASE_REPORT", "source_language_strength": "OBSERVED",
                "target_scope": "SINGLE_CASE", "assertion_role": "OBSERVATION", "provenance": "SOURCE",
                "external_support_refs": [], "human_review_status": "NOT_REQUIRED",
            }],
        },
        "document_structure_audit.v0.1.schema.json": document_structure(),
        "privacy_surface_audit.v0.1.schema.json": privacy_record(),
    }
    for name, fixture in fixtures.items():
        schema = json.loads((schema_root / name).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(fixture)
