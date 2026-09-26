"""S0 acceptance: the audit chain detects tampering, offline, stdlib only.

Every negative case here is a real attack on the log. A checker that cannot fail
is not a checker, so each tamper test asserts the exact failure code rather than
merely "not ok".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import provenance as P  # noqa: E402


def chained(n: int = 3) -> list[dict]:
    chain: list[dict] = []
    for i in range(n):
        P.append(chain, f"2026-09-11T00:00:0{i}+00:00", f"ACTION_{i}",
                 {"detail": f"payload {i}", "value": str(i)})
    return chain


# ------------------------------------------------------------------- positives
def test_empty_chain_makes_no_claim():
    result = P.verify_chain([])
    assert result["ok"] is False
    assert result["code"] == P.EMPTY
    assert result["head_hash"] == P.GENESIS


def test_intact_chain_verifies():
    chain = chained(4)
    result = P.verify_chain(chain)
    assert result["ok"] is True
    assert result["code"] == P.OK
    assert result["count"] == 4
    assert result["head_hash"] == chain[-1]["entry_hash"]


def test_head_hash_of_empty_is_genesis():
    assert P.head_hash([]) == P.GENESIS


def test_payload_free_entries_still_verify():
    chain: list[dict] = []
    for i in range(3):
        P.append(chain, "2026-09-11T00:00:00+00:00", f"A{i}", {"detail": str(i)},
                 keep_payload=False)
    assert all("payload" not in e for e in chain)
    assert P.verify_chain(chain)["ok"] is True


def test_canonical_digest_is_key_order_independent():
    assert P.payload_digest({"a": 1, "b": [2, 3]}) == P.payload_digest({"b": [2, 3], "a": 1})


def test_build_chain_migrates_a_legacy_log():
    legacy = [{"at": "2026-01-01T00:00:00+00:00", "action": "CREATED", "detail": "d0"},
              {"at": "2026-01-01T00:00:01+00:00", "action": "UPLOADED", "detail": "d1"}]
    chain = P.build_chain(legacy)
    assert len(chain) == 2
    assert P.verify_chain(chain)["ok"] is True
    assert [e["seq"] for e in chain] == [0, 1]


# ------------------------------------------------------------------- negatives
def test_middle_entry_deletion_is_detected():
    chain = chained(4)
    del chain[1]
    result = P.verify_chain(chain)
    assert result["ok"] is False
    assert result["code"] == P.SEQ_MISMATCH
    assert result["first_bad_index"] == 1


def test_payload_edit_is_detected():
    chain = chained(3)
    chain[2]["payload"]["detail"] = "tampered"
    result = P.verify_chain(chain)
    assert result["ok"] is False
    assert result["code"] == P.PAYLOAD_MISMATCH
    assert result["first_bad_index"] == 2


def test_swapped_entries_are_detected():
    chain = chained(4)
    chain[1], chain[2] = chain[2], chain[1]
    result = P.verify_chain(chain)
    assert result["ok"] is False
    assert result["code"] == P.SEQ_MISMATCH


def test_relabelled_action_is_detected():
    chain = chained(3)
    chain[1]["action"] = "APPROVED"
    result = P.verify_chain(chain)
    assert result["ok"] is False
    assert result["code"] == P.ENTRY_HASH_MISMATCH


def test_backdated_timestamp_is_detected():
    chain = chained(3)
    chain[2]["at"] = "2020-01-01T00:00:00+00:00"
    result = P.verify_chain(chain)
    assert result["ok"] is False
    assert result["code"] == P.ENTRY_HASH_MISMATCH


def test_forged_entry_hash_is_detected():
    chain = chained(2)
    chain[-1]["entry_hash"] = "f" * 64
    result = P.verify_chain(chain)
    assert result["ok"] is False
    assert result["code"] == P.ENTRY_HASH_MISMATCH


def test_unchained_entry_injected_into_chain_is_rejected():
    chain = chained(2)
    chain.insert(1, {"at": "x", "action": "Y", "detail": "legacy"})
    result = P.verify_chain(chain)
    assert result["ok"] is False
    assert result["code"] == P.MALFORMED_ENTRY
    assert result["first_bad_index"] == 1


def test_unknown_chain_version_is_rejected():
    chain = chained(2)
    chain[1]["version"] = 99
    result = P.verify_chain(chain)
    assert result["ok"] is False
    assert result["code"] == P.UNSUPPORTED_VERSION


def test_genesis_link_cannot_be_rewritten():
    """The first entry must link to GENESIS; rewriting that link is caught.

    The positional genesis check fires first, which is the more specific code --
    the entry is rejected before its own hash is even recomputed.
    """
    chain = chained(2)
    chain[0]["prev_hash"] = "a" * 64
    result = P.verify_chain(chain)
    assert result["ok"] is False
    assert result["code"] == P.PREV_MISMATCH
    assert result["first_bad_index"] == 0


# ------------------------------------------------------- documented limitations
def test_tail_truncation_is_NOT_detected_by_the_chain_alone():
    """KNOWN GAP, closed only by an external anchor (S1).

    Removing trailing entries leaves a shorter but perfectly valid chain. This
    test pins that behaviour so S1's anchor work has a concrete target: after the
    anchor lands, truncation must be caught by comparing the anchored head hash
    with the freshly computed head.
    """
    chain = chained(4)
    truncated = chain[:2]
    result = P.verify_chain(truncated)
    assert result["ok"] is True, "chain alone cannot see truncation - by design"
    anchored_head = P.head_hash(chain)
    assert P.head_hash(truncated) != anchored_head, "the anchor is what closes the gap"


def test_floats_are_rejected_from_canonical_payloads():
    with pytest.raises(ValueError):
        P.canonical_json({"value": 1.5})
    with pytest.raises(ValueError):
        P.payload_digest({"value": float("nan")})


# ----------------------------------------------------------------------- files
def test_verify_files_accepts_matching_content(tmp_path: Path):
    target = tmp_path / "artifact.bin"
    target.write_bytes(b"delivered artifact")
    records = [{"path": "artifact.bin", "sha256": P.digest_file(target)}]
    result = P.verify_files(tmp_path, records)
    assert result["ok"] is True and result["failed"] == 0


def test_verify_files_catches_modified_artifact(tmp_path: Path):
    target = tmp_path / "artifact.bin"
    target.write_bytes(b"delivered artifact")
    good = P.digest_file(target)
    target.write_bytes(b"delivered artifact ")  # one byte appended
    result = P.verify_files(tmp_path, [{"path": "artifact.bin", "sha256": good}])
    assert result["ok"] is False
    assert result["records"][0]["status"] == "HASH_MISMATCH"


def test_verify_files_reports_missing_and_unverifiable(tmp_path: Path):
    result = P.verify_files(tmp_path, [
        {"path": "nope.bin", "sha256": "a" * 64},
        {"path": None, "sha256": "b" * 64},
    ])
    codes = {row["status"] for row in result["records"]}
    assert codes == {"MISSING", "UNVERIFIABLE_NO_PATH"}
    assert result["ok"] is False


def test_verify_files_refuses_path_escape(tmp_path: Path):
    outside = tmp_path.parent / "outside.bin"
    outside.write_bytes(b"x")
    result = P.verify_files(tmp_path, [{"path": "../outside.bin",
                                        "sha256": P.digest_file(outside)}])
    assert result["ok"] is False
    assert result["records"][0]["status"] == "PATH_ESCAPE"
    outside.unlink()


# -------------------------------------------------------------------------- CLI
def test_cli_verify_chain_exit_codes(tmp_path: Path, capsys):
    chain = chained(3)
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"audit_chain": chain}, ensure_ascii=False), encoding="utf-8")
    assert P.main(["verify-chain", str(good)]) == 0

    bad_chain = chained(3)
    bad_chain[0]["action"] = "FORGED"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"audit_chain": bad_chain}, ensure_ascii=False), encoding="utf-8")
    assert P.main(["verify-chain", str(bad)]) == 1


def test_cli_head_matches_last_entry(tmp_path: Path, capsys):
    chain = chained(3)
    path = tmp_path / "chain.json"
    path.write_text(json.dumps({"audit_chain": chain}, ensure_ascii=False), encoding="utf-8")
    assert P.main(["head", str(path)]) == 0
    assert capsys.readouterr().out.strip() == chain[-1]["entry_hash"]
