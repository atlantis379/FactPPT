"""S1 acceptance: an external anchor closes the tail-truncation gap.

S0 proved the chain is self-consistent and documented one gap: deleting trailing
entries leaves a shorter but valid chain. Every test here is written against that
gap -- if truncation still verifies OK, S1 has not delivered anything.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import anchor as A  # noqa: E402
from tools import provenance as P  # noqa: E402

needs_crypto = pytest.mark.skipif(A._cryptography() is None,
                                  reason="cryptography library not installed")


def chain_of(n: int) -> list[dict]:
    chain: list[dict] = []
    for i in range(n):
        P.append(chain, f"2026-09-11T00:00:{i:02d}+00:00", f"ACTION_{i}",
                 {"detail": f"payload {i}"})
    return chain


def project_of(project_id: str, n: int) -> dict:
    return {"id": project_id, "audit_chain": chain_of(n)}


def anchored(tmp_path: Path, project_id: str = "prj_a", n: int = 3):
    """Return (anchor_path, projects_path, project)."""
    project = project_of(project_id, n)
    projects = tmp_path / "projects.json"
    projects.write_text(json.dumps([project], ensure_ascii=False), encoding="utf-8")
    anchor_path = tmp_path / "anchors.jsonl"
    record = A.make_anchor(prev_anchor_hash=A.GENESIS_ANCHOR, seq=0,
                           at="2026-09-11T00:00:00+00:00", project_id=project_id,
                           chain_length=n, chain_head=P.head_hash(project["audit_chain"]))
    A.append_anchor(anchor_path, record)
    return anchor_path, projects, project


# ------------------------------------------------------------------ positives
def test_append_only_file_verifies(tmp_path):
    anchor_path, projects, _ = anchored(tmp_path, n=3)
    result = A.verify_all(anchor_path, projects)
    assert result["ok"] is True
    assert result["anchor_file"]["code"] == A.A_OK
    assert result["results"][0]["anchor"]["code"] == A.C_OK


def test_anchor_file_requires_linking_head(tmp_path):
    anchor_path, _, _ = anchored(tmp_path)
    stray = A.make_anchor(prev_anchor_hash="f" * 64, seq=1,
                          at="2026-09-12T00:00:00+00:00", project_id="prj_a",
                          chain_length=3, chain_head="a" * 64)
    with pytest.raises(ValueError, match="does not link"):
        A.append_anchor(anchor_path, stray)


def test_anchor_file_requires_continuing_sequence(tmp_path):
    anchor_path, _, _ = anchored(tmp_path)
    last = A.load_anchors(anchor_path)[-1]
    wrong_seq = A.make_anchor(prev_anchor_hash=last["anchor_hash"], seq=7,
                              at="2026-09-12T00:00:00+00:00", project_id="prj_a",
                              chain_length=3, chain_head="a" * 64)
    with pytest.raises(ValueError, match="seq does not continue"):
        A.append_anchor(anchor_path, wrong_seq)


def test_growing_a_chain_stays_consistent_with_its_anchor(tmp_path):
    """Appending more entries after anchoring is normal and must still pass."""
    anchor_path, projects, project = anchored(tmp_path, n=3)
    P.append(project["audit_chain"], "2026-09-11T01:00:00+00:00", "LATER", {"detail": "x"})
    projects.write_text(json.dumps([project], ensure_ascii=False), encoding="utf-8")
    result = A.verify_all(anchor_path, projects)
    assert result["ok"] is True
    assert result["results"][0]["anchor"]["grown_by"] == 1


# ---------------------------------------------- the S0 gap, now closed
def test_tail_truncation_is_detected_once_anchored(tmp_path):
    """S0 could not see this; S1 must."""
    anchor_path, projects, project = anchored(tmp_path, n=5)
    # an attacker removes the last two entries: the chain is still self-consistent
    project["audit_chain"] = project["audit_chain"][:3]
    assert P.verify_chain(project["audit_chain"])["ok"] is True, "chain alone still passes"
    projects.write_text(json.dumps([project], ensure_ascii=False), encoding="utf-8")

    result = A.verify_all(anchor_path, projects)
    assert result["ok"] is False
    row = result["results"][0]["anchor"]
    assert row["code"] == A.C_TRUNCATED
    assert row["anchored_length"] == 5 and row["current_length"] == 3


def test_truncation_to_empty_is_detected(tmp_path):
    anchor_path, projects, project = anchored(tmp_path, n=2)
    project["audit_chain"] = []
    projects.write_text(json.dumps([project], ensure_ascii=False), encoding="utf-8")
    result = A.verify_all(anchor_path, projects)
    assert result["ok"] is False
    assert result["results"][0]["anchor"]["code"] == A.C_TRUNCATED


def test_partial_rewrite_breaks_the_chain_link(tmp_path):
    """A naive edit leaves the next entry pointing at the old hash."""
    anchor_path, projects, project = anchored(tmp_path, n=4)
    forged = chain_of(4)
    forged[2]["payload"]["detail"] = "rewritten"
    forged[2]["entry_hash"] = P.compute_entry_hash(
        seq=2, at=forged[2]["at"], action=forged[2]["action"],
        payload_sha256=P.payload_digest(forged[2]["payload"]),
        prev_hash=forged[1]["entry_hash"])
    project["audit_chain"] = forged
    projects.write_text(json.dumps([project], ensure_ascii=False), encoding="utf-8")
    result = A.verify_all(anchor_path, projects)
    assert result["ok"] is False
    # the chain check catches it first, with a precise link failure
    assert result["results"][0]["chain"]["ok"] is False
    assert result["results"][0]["chain"]["code"] in (
        P.PREV_MISMATCH, P.ENTRY_HASH_MISMATCH)


def test_fully_consistent_tail_rewrite_is_caught_by_the_anchor(tmp_path):
    """The sharp case: rebuild the tail so the chain is self-consistent.

    A forged chain that survives S0's own checker requires updating BOTH
    ``prev_hash`` and ``entry_hash`` from the edit onward -- which is exactly the
    effort an anchor makes pointless.
    """
    anchor_path, projects, project = anchored(tmp_path, n=4)
    forged = chain_of(4)
    forged[2]["payload"]["detail"] = "rewritten consistently"
    for index in (2, 3):
        forged[index]["payload_sha256"] = P.payload_digest(forged[index]["payload"])
        forged[index]["prev_hash"] = forged[index - 1]["entry_hash"]
        forged[index]["entry_hash"] = P.compute_entry_hash(
            seq=index, at=forged[index]["at"], action=forged[index]["action"],
            payload_sha256=forged[index]["payload_sha256"],
            prev_hash=forged[index]["prev_hash"])
    project["audit_chain"] = forged
    projects.write_text(json.dumps([project], ensure_ascii=False), encoding="utf-8")

    assert P.verify_chain(forged)["ok"] is True, "the rewritten chain is self-consistent"
    result = A.verify_all(anchor_path, projects)
    assert result["ok"] is False
    row = result["results"][0]
    assert row["chain"]["ok"] is True
    assert row["anchor"]["code"] == A.C_HEAD_MISMATCH


def test_project_without_any_anchor_is_reported_not_silently_passed(tmp_path):
    anchor_path, projects, _ = anchored(tmp_path, project_id="prj_a")
    other = project_of("prj_never_anchored", 2)
    data = json.loads(projects.read_text(encoding="utf-8"))
    data.append(other)
    projects.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    result = A.verify_all(anchor_path, projects)
    assert result["ok"] is False
    codes = {row["project_id"]: row["anchor"]["code"] for row in result["results"]}
    assert codes["prj_never_anchored"] == A.C_NO_ANCHOR


# ----------------------------------------------------------- anchor tampering
def test_editing_an_anchor_record_is_detected(tmp_path):
    anchor_path, projects, _ = anchored(tmp_path, n=3)
    lines = [json.loads(l) for l in anchor_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines[0]["chain_length"] = 99          # claim a longer chain than was anchored
    anchor_path.write_text(json.dumps(lines[0], ensure_ascii=False) + "\n", encoding="utf-8")
    state = A.verify_anchor_file(A.load_anchors(anchor_path))
    assert state["ok"] is False
    assert state["code"] == A.A_HASH_MISMATCH


def test_deleting_a_middle_anchor_is_detected(tmp_path):
    anchor_path = tmp_path / "anchors.jsonl"
    project = project_of("prj_a", 2)
    chain = project["audit_chain"]
    for i in range(3):
        record = A.make_anchor(prev_anchor_hash=A.last_anchor_hash(A.load_anchors(anchor_path)),
                               seq=i, at=f"2026-09-11T00:00:0{i}+00:00",
                               project_id="prj_a", chain_length=len(chain),
                               chain_head=P.head_hash(chain))
        A.append_anchor(anchor_path, record)
    lines = [json.loads(l) for l in anchor_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    del lines[1]
    anchor_path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n",
                           encoding="utf-8")
    state = A.verify_anchor_file(A.load_anchors(anchor_path))
    assert state["ok"] is False
    assert state["code"] == A.A_SEQ_MISMATCH


def test_backdated_anchor_is_rejected(tmp_path):
    anchor_path = tmp_path / "anchors.jsonl"
    project = project_of("prj_a", 2)
    chain = project["audit_chain"]
    first = A.make_anchor(prev_anchor_hash=A.GENESIS_ANCHOR, seq=0,
                          at="2026-09-11T00:00:00+00:00", project_id="prj_a",
                          chain_length=len(chain), chain_head=P.head_hash(chain))
    A.append_anchor(anchor_path, first)
    backdated = A.make_anchor(prev_anchor_hash=first["anchor_hash"], seq=1,
                              at="2020-01-01T00:00:00+00:00", project_id="prj_a",
                              chain_length=len(chain), chain_head=P.head_hash(chain))
    A.append_anchor(anchor_path, backdated)          # allowed at write time
    state = A.verify_anchor_file(A.load_anchors(anchor_path))
    assert state["ok"] is False
    assert state["code"] == A.A_BACKDATED


def test_appending_to_a_broken_anchor_file_is_refused(tmp_path):
    anchor_path, projects, _ = anchored(tmp_path, n=3)
    lines = [json.loads(l) for l in anchor_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines[0]["note"] = "edited after the fact"
    anchor_path.write_text(json.dumps(lines[0], ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="existing anchor file is"):
        A.append_anchor(anchor_path, A.make_anchor(
            prev_anchor_hash=lines[0]["anchor_hash"], seq=1,
            at="2026-09-12T00:00:00+00:00", project_id="prj_a",
            chain_length=3, chain_head="a" * 64))


def test_malformed_anchor_line_is_reported(tmp_path):
    anchor_path = tmp_path / "anchors.jsonl"
    anchor_path.write_text('{"version": 1, "seq": 0}\n', encoding="utf-8")
    state = A.verify_anchor_file(A.load_anchors(anchor_path))
    assert state["ok"] is False
    assert state["code"] == A.A_MALFORMED


def test_unsupported_anchor_version_is_reported(tmp_path):
    anchor_path, _, _ = anchored(tmp_path, n=2)
    lines = [json.loads(l) for l in anchor_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines[0]["version"] = 99
    state = A.verify_anchor_file(lines)
    assert state["ok"] is False
    assert state["code"] == A.A_UNSUPPORTED


# --------------------------------------------------------------- signatures
@needs_crypto
def test_signed_anchor_verifies_with_its_public_key(tmp_path):
    keys = tmp_path / "keys"
    A.generate_keypair(keys / "priv.pem", keys / "pub.pem")
    anchor_path = tmp_path / "anchors.jsonl"
    project = project_of("prj_a", 2)
    record = A.make_anchor(prev_anchor_hash=A.GENESIS_ANCHOR, seq=0,
                           at="2026-09-11T00:00:00+00:00", project_id="prj_a",
                           chain_length=2, chain_head=P.head_hash(project["audit_chain"]))
    A.sign_anchor(record, keys / "priv.pem", signer="ci")
    A.append_anchor(anchor_path, record)
    result = A.verify_signature(record, keys / "pub.pem")
    assert result["ok"] is True and result["code"] == A.S_OK


@needs_crypto
def test_signature_fails_after_the_anchor_is_edited(tmp_path):
    keys = tmp_path / "keys"
    A.generate_keypair(keys / "priv.pem", keys / "pub.pem")
    project = project_of("prj_a", 2)
    record = A.make_anchor(prev_anchor_hash=A.GENESIS_ANCHOR, seq=0,
                           at="2026-09-11T00:00:00+00:00", project_id="prj_a",
                           chain_length=2, chain_head=P.head_hash(project["audit_chain"]))
    A.sign_anchor(record, keys / "priv.pem")
    record["chain_length"] = 1                    # edit AFTER signing
    result = A.verify_signature(record, keys / "pub.pem")
    assert result["ok"] is False and result["code"] == A.S_INVALID


@needs_crypto
def test_signature_from_a_different_key_is_rejected(tmp_path):
    keys = tmp_path / "keys"
    other = tmp_path / "other"
    A.generate_keypair(keys / "priv.pem", keys / "pub.pem")
    A.generate_keypair(other / "priv.pem", other / "pub.pem")
    project = project_of("prj_a", 2)
    record = A.make_anchor(prev_anchor_hash=A.GENESIS_ANCHOR, seq=0,
                           at="2026-09-11T00:00:00+00:00", project_id="prj_a",
                           chain_length=2, chain_head=P.head_hash(project["audit_chain"]))
    A.sign_anchor(record, other / "priv.pem")
    result = A.verify_signature(record, keys / "pub.pem")
    assert result["ok"] is False and result["code"] == A.S_INVALID


def test_unsigned_anchor_is_not_reported_as_verified(tmp_path):
    project = project_of("prj_a", 2)
    record = A.make_anchor(prev_anchor_hash=A.GENESIS_ANCHOR, seq=0,
                           at="2026-09-11T00:00:00+00:00", project_id="prj_a",
                           chain_length=2, chain_head=P.head_hash(project["audit_chain"]))
    result = A.verify_signature(record, tmp_path / "missing.pem")
    assert result["ok"] is False
    assert result["code"] == A.S_MISSING


def test_missing_public_key_is_reported_not_assumed_ok(tmp_path):
    project = project_of("prj_a", 2)
    record = A.make_anchor(prev_anchor_hash=A.GENESIS_ANCHOR, seq=0,
                           at="2026-09-11T00:00:00+00:00", project_id="prj_a",
                           chain_length=2, chain_head=P.head_hash(project["audit_chain"]))
    record["signatures"] = [{"signer": "x", "algorithm": "ed25519",
                             "signature": "AAAA"}]
    result = A.verify_signature(record, tmp_path / "nope.pem")
    assert result["ok"] is False
    assert result["code"] in (A.S_KEY_MISSING, A.S_LIB_MISSING)


# ------------------------------------------------------------------- CLI
def test_cli_runs_as_a_standalone_script(tmp_path):
    """The documented third-party command must work from a plain shell.

    Running `python tools/anchor.py` puts tools/ rather than the repository root
    on sys.path. In-process tests cannot see that, so this one shells out.
    """
    import subprocess
    project = project_of("prj_a", 3)
    projects = tmp_path / "projects.json"
    projects.write_text(json.dumps([project], ensure_ascii=False), encoding="utf-8")
    anchor_path = tmp_path / "anchors.jsonl"

    append = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "anchor.py"),
         "append", str(anchor_path), str(projects)],
        capture_output=True, text=True, encoding="utf-8", cwd=str(tmp_path))
    assert append.returncode == 0, append.stdout + append.stderr

    verify = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "anchor.py"),
         "verify", str(anchor_path), str(projects)],
        capture_output=True, text=True, encoding="utf-8", cwd=str(tmp_path))
    assert verify.returncode == 0, verify.stdout + verify.stderr
    assert json.loads(verify.stdout)["ok"] is True


def test_cli_append_then_verify_round_trip(tmp_path, capsys):
    project = project_of("prj_a", 3)
    projects = tmp_path / "projects.json"
    projects.write_text(json.dumps([project], ensure_ascii=False), encoding="utf-8")
    anchor_path = tmp_path / "anchors.jsonl"
    assert A.main(["append", str(anchor_path), str(projects), "--note", "交付 v1"]) == 0
    capsys.readouterr()
    assert A.main(["show", str(anchor_path)]) == 0
    capsys.readouterr()
    assert A.main(["verify", str(anchor_path), str(projects)]) == 0
    capsys.readouterr()

    # truncate the chain, then the CLI must exit non-zero
    project["audit_chain"] = project["audit_chain"][:1]
    projects.write_text(json.dumps([project], ensure_ascii=False), encoding="utf-8")
    assert A.main(["verify", str(anchor_path), str(projects)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"][0]["anchor"]["code"] == A.C_TRUNCATED
