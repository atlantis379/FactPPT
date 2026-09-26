"""A passed report must belong to the exact inputs and exported bytes."""
from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path

import pytest

from app.delivery_evidence import make_quality_report, validate_quality_report
from app.stage_contract import digest_file, validate_chain


@pytest.fixture
def tmp_path():
    """Use only owned, flat files; the host sandbox blocks pytest temp roots."""
    root = Path(__file__).resolve().parent
    marker = f".delivery-evidence-test-{uuid.uuid4().hex}-"

    class Scratch:
        def __truediv__(self, name):
            return root / (marker + name)

    yield Scratch()
    for item in root.glob(marker + "*"):
        item.unlink(missing_ok=True)


def _fixture(tmp_path):
    pptx = tmp_path / "delivered.pptx"
    pptx.write_bytes(b"example PowerPoint bytes")
    deck = {"project_id": "p1", "pages": [{"page_id": "slide-1", "title": "Result"}]}
    plan = {"pages": [{"page_id": "slide-1", "elements": []}]}
    verification = {"status": "PASS", "issues": [],
                    "render_readback": {"status": "PASS", "artifact_sha256": digest_file(pptx)}}
    sources = [{"id": "source-1", "sha256": "a" * 64}]
    return pptx, deck, plan, verification, sources


def test_report_rejects_changed_content_plan_source_and_pptx(tmp_path):
    pptx, deck, plan, verification, sources = _fixture(tmp_path)
    report = make_quality_report(deck, plan, pptx, verification, source_documents=sources)
    validate_quality_report(report, deck, plan, pptx, source_documents=sources)
    changed_deck = copy.deepcopy(deck)
    changed_deck["pages"][0]["title"] = "Different result"
    with pytest.raises(ValueError, match="current inputs"):
        validate_quality_report(report, changed_deck, plan, pptx, source_documents=sources)
    with pytest.raises(ValueError, match="current inputs"):
        validate_quality_report(report, deck, {"pages": []}, pptx, source_documents=sources)
    with pytest.raises(ValueError, match="current inputs"):
        validate_quality_report(report, deck, plan, pptx,
                                source_documents=[{"id": "source-1", "sha256": "b" * 64}])
    pptx.write_bytes(b"modified PowerPoint bytes")
    with pytest.raises(ValueError, match="exact bytes"):
        validate_quality_report(report, deck, plan, pptx, source_documents=sources)


def test_failed_verification_and_broken_chain_never_pass(tmp_path):
    pptx, deck, plan, verification, sources = _fixture(tmp_path)
    with pytest.raises(ValueError, match="did not pass"):
        make_quality_report(deck, plan, pptx, {**verification, "status": "FAIL"})
    report = make_quality_report(deck, plan, pptx, verification, source_documents=sources)
    broken = copy.deepcopy(report)
    broken["stages"][2]["inputs"]["page_plan"] = "0" * 64
    with pytest.raises(ValueError, match="Quality report bytes changed"):
        validate_quality_report(broken, deck, plan, pptx, source_documents=sources)
    with pytest.raises(ValueError, match="Stale or missing stage link"):
        validate_chain(broken["stages"])


def test_finalizer_receipt_is_bound(tmp_path):
    pptx, deck, plan, verification, _ = _fixture(tmp_path)
    receipt = tmp_path / "finalizer.json"
    receipt.write_text(json.dumps({"schemaVersion": "presentation-finalization.v1",
                                   "finalSha256": digest_file(pptx),
                                   "packageIntegrity": {"status": "pass"},
                                   "presentationLayout": {"exitCode": 0, "findingCount": 0},
                                   "fontSelection": {"passed": True},
                                   "firstPartyImport": {"passed": True}}), encoding="utf-8")
    report = make_quality_report(deck, plan, pptx, verification, finalizer_receipt=receipt)
    assert report["release_eligible"] is True
    receipt.write_text('{"status":"FAIL"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Finalizer receipt"):
        validate_quality_report(report, deck, plan, pptx, finalizer_receipt=receipt)
