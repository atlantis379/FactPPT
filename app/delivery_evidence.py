"""Bind approved inputs, quality findings and the delivered PPTX bytes.

The report is a reproducible receipt: it detects stale inputs or a changed
artifact. It does not certify the truth of source documents or replace review.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from app.stage_contract import (SCHEMA_VERSION, digest_file, digest_json,
                                stage_record, validate_chain)


def finalizer_receipt_matches(receipt: str | Path, pptx: str | Path) -> bool:
    try:
        result = json.loads(Path(receipt).read_text(encoding="utf-8"))
        return (result.get("schemaVersion") == "presentation-finalization.v1"
                and result.get("finalSha256") == digest_file(pptx)
                and result.get("packageIntegrity", {}).get("status", "").lower() == "pass"
                and result.get("presentationLayout", {}).get("exitCode") == 0
                and result.get("presentationLayout", {}).get("findingCount") == 0
                and result.get("fontSelection", {}).get("passed") is True
                and result.get("firstPartyImport", {}).get("passed") is True)
    except (OSError, ValueError, TypeError):
        return False


def _tool_hash(module: str) -> str:
    return f"app.{module}@{digest_file(Path(__file__).with_name(module + '.py'))[:16]}"


def make_quality_report(deck: dict[str, Any], plan: dict[str, Any], pptx: str | Path,
                        verification: dict[str, Any], *,
                        source_documents: list[dict[str, Any]] | None = None,
                        layout_ir: dict[str, Any] | None = None,
                        editorial_asset_sha256s: list[str] | None = None,
                        finalizer_receipt: str | Path | None = None) -> dict[str, Any]:
    pptx = Path(pptx)
    pptx_hash = digest_file(pptx)
    readback = verification.get("render_readback") or {}
    if verification.get("status") != "PASS" or readback.get("artifact_sha256") != pptx_hash:
        raise ValueError("PPTX verification did not pass for these exact bytes")
    if finalizer_receipt and not finalizer_receipt_matches(finalizer_receipt, pptx):
        raise ValueError("Finalizer receipt does not match this PPTX or did not pass")
    source_hashes = [{"id": item.get("id"), "sha256": item.get("sha256")}
                     for item in (source_documents or [])]
    if any(not item["id"] or not isinstance(item["sha256"], str)
           or len(item["sha256"]) != 64 for item in source_hashes):
        raise ValueError("Every declared source document needs an ID and SHA-256")
    asset_hashes = list(editorial_asset_sha256s or [])
    receipt_hash = digest_file(finalizer_receipt) if finalizer_receipt else None
    content_hash = digest_json(deck)
    plan_hash = digest_json(plan)
    verification_hash = digest_json(verification)
    records = [
        stage_record("approved_content", {"source_documents": digest_json(source_hashes)},
                     content_hash, tool=_tool_hash("content_contract")),
        stage_record("page_plan", {"approved_content": content_hash,
                                   "layout_ir": digest_json(layout_ir),
                                   "editorial_assets": digest_json(asset_hashes)},
                     plan_hash, tool=_tool_hash("native_beautifier")),
        stage_record("pptx_build", {"page_plan": plan_hash}, pptx_hash,
                     tool=_tool_hash("packager")),
        stage_record("pptx_quality", {"pptx_build": pptx_hash},
                     verification_hash, tool=_tool_hash("render_readback")),
    ]
    validate_chain(records)
    report = {"schema_version": SCHEMA_VERSION, "status": "PASS",
              "release_eligible": bool(receipt_hash),
              "stages": records, "source_documents": source_hashes,
              "editorial_asset_sha256s": asset_hashes,
              "finalizer_receipt_sha256": receipt_hash,
              "verification": verification}
    report["report_sha256"] = digest_json(report)
    return report


def validate_quality_report(report: dict[str, Any], deck: dict[str, Any],
                            plan: dict[str, Any], pptx: str | Path, *,
                            source_documents: list[dict[str, Any]] | None = None,
                            layout_ir: dict[str, Any] | None = None,
                            editorial_asset_sha256s: list[str] | None = None,
                            finalizer_receipt: str | Path | None = None) -> None:
    if report.get("schema_version") != SCHEMA_VERSION or report.get("status") != "PASS":
        raise ValueError("Unsupported or failed quality report")
    stored_hash = report.get("report_sha256")
    body = {key: value for key, value in report.items() if key != "report_sha256"}
    if stored_hash != digest_json(body):
        raise ValueError("Quality report bytes changed")
    expected = make_quality_report(
        deck, plan, pptx, report.get("verification") or {},
        source_documents=source_documents, layout_ir=layout_ir,
        editorial_asset_sha256s=editorial_asset_sha256s,
        finalizer_receipt=finalizer_receipt)
    if report != expected:
        raise ValueError("Quality report does not match current inputs or PPTX")


def write_quality_report(path: str | Path, report: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
                             encoding="utf-8")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
