"""S0 integration: the app's audit trail is verifiable by an outside party.

The acceptance criterion is not "the app can check itself" -- that is the
self-attestation failure this work removes. It is that a file plus a stdlib-only
script is enough for someone else to decide whether the trail was altered.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import main as M  # noqa: E402
from tools import provenance as P  # noqa: E402


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    """Keep the real data/projects.json untouched."""
    store = tmp_path / "projects.json"
    monkeypatch.setattr(M, "STORE", store)
    return store


def test_audit_calls_build_a_verifiable_chain(isolated_store):
    project = M.seed_project()          # seeds one PROJECT_CREATED entry
    M.audit(project, "DOCUMENT_UPLOADED", "source.pdf")
    M.audit(project, "TRIAGE_DECISION", "MUST_INCLUDE x3")

    result = P.verify_chain(project.audit_chain)
    assert result["ok"] is True
    assert project.audit_head == result["head_hash"]
    # the human-readable log and the chain stay in lockstep
    assert len(project.audit_log) == len(project.audit_chain) == result["count"]
    assert [row["action"] for row in project.audit_log][-3:] == [
        "PROJECT_CREATED", "DOCUMENT_UPLOADED", "TRIAGE_DECISION"]
    # every audit timestamp is carried into the chain, not just the action
    assert [row["at"] for row in project.audit_log] == [
        entry["at"] for entry in project.audit_chain]


def test_chain_survives_a_save_load_round_trip(isolated_store):
    project = M.seed_project()
    M.audit(project, "CREATED", "one")
    M.save_projects([project])

    reloaded = M.load_projects()[0]
    assert P.verify_chain(reloaded.audit_chain)["ok"] is True
    assert reloaded.chain_provenance["status"] == "OK"
    assert reloaded.audit_head == project.audit_head


def _legacy_record() -> dict:
    """A realistic pre-existing record: a real project dump minus the new fields.

    Building it from the real model (rather than hand-writing a stub) is what
    makes this a migration test instead of a fixture that would never occur.
    """
    record = M.seed_project().model_dump(mode="json")
    record["audit_log"] = [
        {"at": "2026-01-01T00:00:00+00:00", "action": "PROJECT_CREATED", "detail": "old"},
        {"at": "2026-01-01T00:00:01+00:00", "action": "DOCUMENT_UPLOADED", "detail": "old"},
    ]
    for key in ("audit_chain", "audit_head", "chain_provenance"):
        record.pop(key, None)
    return record


def test_legacy_log_is_migrated_and_marked_as_unanchored(isolated_store):
    """Pre-existing logs get a chain, but never an implied past guarantee."""
    legacy = _legacy_record()
    isolated_store.write_text(json.dumps([legacy], ensure_ascii=False), encoding="utf-8")

    project = M.load_projects()[0]
    assert len(project.audit_chain) == len(project.audit_log) == 2
    assert P.verify_chain(project.audit_chain)["ok"] is True
    assert project.chain_provenance["status"] == "MIGRATED"
    assert "no cryptographic standing" in project.chain_provenance["migration_note"]


def test_tampered_chain_is_reported_broken_and_never_repaired(isolated_store):
    project = M.seed_project()
    M.audit(project, "CREATED", "one")
    M.audit(project, "APPROVED_FOR_DELIVERY", "two")
    M.save_projects([project])

    raw = json.loads(isolated_store.read_text(encoding="utf-8"))
    raw[0]["audit_chain"][0]["action"] = "REJECTED"          # forge a decision
    raw[0]["audit_chain"][0]["entry_hash"] = "0" * 64        # and cover it up
    isolated_store.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    reloaded = M.load_projects()[0]
    assert reloaded.chain_provenance["status"] == "BROKEN"
    # evidence preserved: the forged entry is still there to inspect
    assert reloaded.audit_chain[0]["action"] == "REJECTED"
    assert reloaded.audit_chain[0]["entry_hash"] == "0" * 64


def test_mid_chain_deletion_is_reported_broken(isolated_store):
    project = M.seed_project()
    M.audit(project, "A", "1")
    M.audit(project, "B", "2")
    M.audit(project, "C", "3")
    M.save_projects([project])

    raw = json.loads(isolated_store.read_text(encoding="utf-8"))
    del raw[0]["audit_chain"][1]
    isolated_store.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    reloaded = M.load_projects()[0]
    assert reloaded.chain_provenance["status"] == "BROKEN"


def test_provenance_report_states_its_own_boundary():
    project = M.seed_project()
    M.audit(project, "CREATED", "one")
    report = M.provenance_report(project)
    assert report["chain"]["ok"] is True
    # the dependency claim must stay accurate: chain verification is stdlib only,
    # signature verification is not
    deps = report["verifier"]["dependencies"]
    assert "stdlib only" in deps
    assert "cryptography" in deps
    # the report must not overclaim: tail truncation needs a published anchor
    assert "truncation" in report["claim_boundary"].lower()
    # and before any anchor exists, it must say so explicitly
    assert report["anchor"]["latest"] is None


def test_outside_party_verifies_with_the_standalone_cli(isolated_store, tmp_path):
    """The acceptance test: no app, no skill, no third-party packages."""
    project = M.seed_project()
    M.audit(project, "CREATED", "one")
    M.audit(project, "HUMAN_REVIEW_DECISION", "approved")
    M.save_projects([project])

    exported = tmp_path / "exported_project.json"
    exported.write_text(isolated_store.read_text(encoding="utf-8"), encoding="utf-8")

    ok = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "provenance.py"),
         "verify-chain", str(exported)],
        capture_output=True, text=True, encoding="utf-8")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    report = json.loads(ok.stdout)
    assert report["ok"] is True
    assert report["failed"] == 0
    assert report["targets"] and report["targets"][0]["ok"] is True

    raw = json.loads(exported.read_text(encoding="utf-8"))
    raw[0]["audit_chain"][1]["payload"]["detail"] = "rewritten after review"
    exported.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    bad = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "provenance.py"),
         "verify-chain", str(exported)],
        capture_output=True, text=True, encoding="utf-8")
    assert bad.returncode == 1
    report = json.loads(bad.stdout)
    assert report["ok"] is False and report["failed"] == 1
    # the failure is reported against the specific project, with a precise code
    assert report["targets"][0]["code"] == P.PAYLOAD_MISMATCH
    assert report["targets"][0]["first_bad_index"] == 1
