"""S1 integration: anchoring through the application, isolated from real data."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import main as M  # noqa: E402
from tools import anchor as A  # noqa: E402
from tools import provenance as P  # noqa: E402

needs_crypto = pytest.mark.skipif(A._cryptography() is None,
                                  reason="cryptography library not installed")


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    store = tmp_path / "projects.json"
    anchor_store = tmp_path / "anchors.jsonl"
    keys = tmp_path / "keys"
    monkeypatch.setattr(M, "STORE", store)
    monkeypatch.setattr(M, "ANCHOR_STORE", anchor_store)
    monkeypatch.setattr(M, "ANCHOR_KEY", keys / "anchor-ed25519.pem")
    monkeypatch.setattr(M, "ANCHOR_PUBKEY", keys / "anchor-ed25519.pub.pem")
    project = M.seed_project()
    M.audit(project, "DOCUMENT_UPLOADED", "source.pdf")
    M.save_projects([project])
    return store, anchor_store, project


def test_anchor_publishes_and_verifies(isolated):
    store, anchor_store, project = isolated
    result = M.create_anchor(project)
    assert result["chain_length"] == len(project.audit_chain)
    assert anchor_store.exists()

    report = M.provenance_report(project)
    assert report["anchor"]["latest"]["chain_length"] == result["chain_length"]
    assert report["anchor"]["consistency"]["code"] == A.C_OK


def test_truncation_shows_up_in_the_report(isolated):
    store, anchor_store, project = isolated
    M.create_anchor(project)
    anchored_len = len(project.audit_chain)

    # remove the last entry: S0's chain check still passes
    project.audit_chain = project.audit_chain[:-1]
    assert P.verify_chain(project.audit_chain)["ok"] is True

    report = M.provenance_report(project)
    consistency = report["anchor"]["consistency"]
    assert consistency["code"] == A.C_TRUNCATED
    assert consistency["anchored_length"] == anchored_len
    assert consistency["current_length"] == anchored_len - 1


def test_report_says_truncation_is_undetectable_before_any_anchor(isolated):
    store, anchor_store, project = isolated
    report = M.provenance_report(project)
    assert report["anchor"]["latest"] is None
    assert "truncation" in report["anchor"]["note"].lower()
    assert "truncation" in report["claim_boundary"].lower()


def test_second_anchor_links_to_the_first(isolated):
    store, anchor_store, project = isolated
    first = M.create_anchor(project, note="交付 v1")
    M.audit(project, "HUMAN_REVIEW_DECISION", "approved")
    second = M.create_anchor(project, note="交付 v2")
    anchors = A.load_anchors(anchor_store)
    assert [a["seq"] for a in anchors] == [0, 1]
    assert anchors[1]["prev_anchor_hash"] == first["anchor_hash"]
    assert second["chain_length"] > first["chain_length"]
    assert A.verify_anchor_file(anchors)["ok"] is True


def test_anchoring_an_empty_chain_is_refused(isolated):
    store, anchor_store, project = isolated
    project.audit_chain = []
    with pytest.raises(Exception) as exc:
        M.create_anchor(project)
    assert "empty" in str(exc.value).lower()


def test_anchoring_is_refused_when_the_anchor_file_is_already_broken(isolated):
    """Extending a broken anchor file would bury the evidence."""
    store, anchor_store, project = isolated
    M.create_anchor(project)
    lines = [json.loads(l) for l in anchor_store.read_text(encoding="utf-8").splitlines()
             if l.strip()]
    lines[0]["chain_length"] = 999
    anchor_store.write_text(json.dumps(lines[0], ensure_ascii=False) + "\n", encoding="utf-8")

    with pytest.raises(Exception) as exc:
        M.create_anchor(project, note="try to extend")
    assert "ANCHOR_HASH_MISMATCH" in str(exc.value)


@needs_crypto
def test_created_anchor_is_signed_and_verifiable(isolated):
    store, anchor_store, project = isolated
    result = M.create_anchor(project)
    assert result["signed"] is True
    anchors = A.load_anchors(anchor_store)
    check = A.verify_signature(anchors[0], M.ANCHOR_PUBKEY)
    assert check["ok"] is True and check["code"] == A.S_OK
    assert anchors[0]["signatures"][0]["signer"] == "local-self-generated"


def test_identity_note_does_not_overclaim(isolated):
    store, anchor_store, project = isolated
    note = M.anchor_identity_note().lower()
    assert "does not establish a third-party legal identity" in note
    assert "proves that an anchor was not altered" in note


def test_anchor_survives_a_reload_and_external_verification(isolated, tmp_path):
    store, anchor_store, project = isolated
    M.create_anchor(project)
    # the endpoint persists the anchored state; without this the exported store
    # would be a pre-anchor snapshot and would (correctly) read as truncated
    M.save_projects([project])

    # a third party receives the exported store plus the anchor file
    exported = tmp_path / "exported.json"
    exported.write_text(store.read_text(encoding="utf-8"), encoding="utf-8")
    result = A.verify_all(anchor_store, exported)
    assert result["ok"] is True
    assert result["results"][0]["chain"]["ok"] is True
    assert result["results"][0]["anchor"]["code"] == A.C_OK

    # ...and detects truncation on a later export
    raw = json.loads(exported.read_text(encoding="utf-8"))
    raw[0]["audit_chain"] = raw[0]["audit_chain"][:1]
    exported.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    result = A.verify_all(anchor_store, exported)
    assert result["ok"] is False
    assert result["results"][0]["anchor"]["code"] == A.C_TRUNCATED


def test_stale_export_is_reported_not_passed(isolated, tmp_path):
    """Exporting before persisting the anchored state must not verify."""
    store, anchor_store, project = isolated
    M.create_anchor(project)          # deliberately do NOT re-save
    exported = tmp_path / "stale.json"
    exported.write_text(store.read_text(encoding="utf-8"), encoding="utf-8")
    result = A.verify_all(anchor_store, exported)
    assert result["ok"] is False
    assert result["results"][0]["anchor"]["code"] == A.C_TRUNCATED
