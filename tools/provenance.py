"""Offline, dependency-free provenance chain.

Why a separate module
---------------------
A third party must be able to check our audit trail without installing our app,
our skill, or any third-party package. This module therefore imports **stdlib
only** and never imports from ``app`` or ``skills``.

What the chain proves, and what it does not
-------------------------------------------
Each entry binds its position, time, action, payload digest and predecessor into
one hash::

    entry_hash = SHA256(domain || canonical({seq, at, action,
                                             payload_sha256, prev_hash}))

Binding ``seq``/``at``/``action`` (not just the payload) means reordering,
back-dating and renaming are detectable, not merely content edits.

Guarantees:
  * editing a payload            -> detected (payload/entry hash mismatch)
  * deleting a middle entry      -> detected (prev_hash link broken)
  * swapping two entries         -> detected (seq + link broken)
  * changing an action label     -> detected (entry hash mismatch)

NOT guaranteed by the chain alone:
  * truncating the TAIL of the log. Removing the last N entries leaves a
    perfectly valid shorter chain. Truncation is only detectable once the head
    hash is anchored outside our storage (RFC 3161 timestamp, published
    append-only file, or a signature) -- see ``tools/anchor.py``.

This limitation is stated here on purpose: a chain that claims to detect
truncation without an anchor would be the exact "self-attestation" failure this
work is meant to remove.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

DOMAIN = "easypPT.audit.chain.v1"
GENESIS = "0" * 64

# verification outcome codes (stable, machine-readable)
OK = "OK"
EMPTY = "EMPTY"
GENESIS_MISMATCH = "GENESIS_MISMATCH"
SEQ_MISMATCH = "SEQ_MISMATCH"
PREV_MISMATCH = "PREV_MISMATCH"
ENTRY_HASH_MISMATCH = "ENTRY_HASH_MISMATCH"
PAYLOAD_MISMATCH = "PAYLOAD_MISMATCH"
MALFORMED_ENTRY = "MALFORMED_ENTRY"
UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"

CHAIN_VERSION = 1


# --------------------------------------------------------------------- digests
def _reject_floats(value: Any, path: str = "$") -> None:
    """Audit payloads may not contain floats.

    ``allow_nan=False`` only rejects NaN/Infinity, so an ordinary float would slip
    through and make the digest depend on platform float formatting. Medical
    numbers must travel as exact decimal strings.
    """
    if isinstance(value, float):
        raise ValueError(
            f"float not allowed at {path}: audit payloads must carry exact "
            f"decimal strings, not binary floats"
        )
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_floats(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_floats(item, f"{path}[{index}]")


def canonical_json(value: Any) -> str:
    """Canonical JSON: sorted keys, no floats, no NaN/Infinity, no spare spaces."""
    _reject_floats(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_bytes(data: bytes) -> str:
    return sha256_hex(data)


def digest_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def payload_digest(payload: Any) -> str:
    """Digest of an entry's payload alone (stable across key order)."""
    return sha256_hex(canonical_json(payload).encode("utf-8"))


# ----------------------------------------------------------------------- chain
def compute_entry_hash(*, seq: int, at: str, action: str, payload_sha256: str,
                       prev_hash: str, version: int = CHAIN_VERSION) -> str:
    material = canonical_json({
        "domain": DOMAIN,
        "version": version,
        "seq": seq,
        "at": at,
        "action": action,
        "payload_sha256": payload_sha256,
        "prev_hash": prev_hash,
    })
    return sha256_hex(material.encode("utf-8"))


def make_entry(prev_hash: str, seq: int, at: str, action: str,
               payload: Any, *, keep_payload: bool = True,
               version: int = CHAIN_VERSION) -> dict:
    """Build one chained entry.

    ``keep_payload=False`` stores only the digest (privacy-preserving logs); the
    chain stays verifiable, but the caller can no longer re-verify payload
    content -- only that it has not changed since it was digested.
    """
    p_digest = payload_digest(payload)
    entry = {
        "version": version,
        "seq": seq,
        "at": at,
        "action": action,
        "payload_sha256": p_digest,
        "prev_hash": prev_hash,
    }
    entry["entry_hash"] = compute_entry_hash(
        seq=seq, at=at, action=action, payload_sha256=p_digest,
        prev_hash=prev_hash, version=version,
    )
    if keep_payload:
        entry["payload"] = payload
    return entry


def append(chain: list[dict], at: str, action: str, payload: Any, **kwargs) -> dict:
    """Append an entry to ``chain`` in place and return it."""
    entry = make_entry(head_hash(chain), len(chain), at, action, payload, **kwargs)
    chain.append(entry)
    return entry


def head_hash(chain: Sequence[dict]) -> str:
    if not chain:
        return GENESIS
    return chain[-1].get("entry_hash", GENESIS)


def _entry_reason(entry: dict, seq: int, prev: str) -> str | None:
    if not isinstance(entry, dict):
        return MALFORMED_ENTRY
    required = ("version", "seq", "at", "action", "payload_sha256", "prev_hash", "entry_hash")
    if any(key not in entry for key in required):
        return MALFORMED_ENTRY
    if entry["version"] != CHAIN_VERSION:
        return UNSUPPORTED_VERSION
    if entry["seq"] != seq:
        return SEQ_MISMATCH
    if entry["prev_hash"] != prev:
        return PREV_MISMATCH
    expected = compute_entry_hash(
        seq=entry["seq"], at=entry["at"], action=entry["action"],
        payload_sha256=entry["payload_sha256"], prev_hash=entry["prev_hash"],
        version=entry["version"],
    )
    if expected != entry["entry_hash"]:
        return ENTRY_HASH_MISMATCH
    if "payload" in entry and payload_digest(entry["payload"]) != entry["payload_sha256"]:
        return PAYLOAD_MISMATCH
    return None


def verify_chain(chain: Sequence[dict]) -> dict:
    """Verify a chain and report the FIRST broken link (fail closed)."""
    result = {
        "ok": False,
        "code": EMPTY,
        "count": len(chain),
        "first_bad_index": None,
        "head_hash": GENESIS,
        "reason": "empty chain carries no integrity claim",
    }
    if not chain:
        return result
    prev = GENESIS
    for index, entry in enumerate(chain):
        reason = _entry_reason(entry, index, prev)
        if reason is not None:
            result.update({
                "ok": False, "code": reason, "first_bad_index": index,
                "head_hash": prev,
                "reason": f"entry {index} failed: {reason}",
            })
            return result
        prev = entry["entry_hash"]
    result.update({
        "ok": True, "code": OK, "head_hash": prev,
        "reason": "chain intact from genesis; tail truncation still requires an anchor",
    })
    return result


def build_chain(entries: Iterable[dict]) -> list[dict]:
    """Rebuild a chain from a legacy, unchained log.

    Used only for migration. The caller MUST record that these entries carried no
    cryptographic standing before migration: a chain built now proves nothing
    about the past, it only fixes the state from this point forward.
    """
    chain: list[dict] = []
    for record in entries:
        at = str(record.get("at", ""))
        action = str(record.get("action", ""))
        payload = {"detail": record.get("detail", "")}
        append(chain, at, action, payload)
    return chain


# ---------------------------------------------------------------------- files
def verify_files(base_dir: str | Path, records: Sequence[dict]) -> dict:
    """Verify files against expected sha256 values.

    ``records``: ``[{"path": <relative>, "sha256": <hex>}]``. Paths are resolved
    under ``base_dir`` and must stay inside it.
    """
    root = Path(base_dir).resolve()
    rows, failed = [], 0
    for record in records:
        rel = record.get("path")
        expected = (record.get("sha256") or "").lower()
        row = {"path": rel, "expected": expected, "status": "OK", "actual": None}
        if not rel or not expected:
            row["status"] = "UNVERIFIABLE_NO_PATH"
            row["reason"] = "manifest carries a digest without a path"
        else:
            candidate = (root / rel).resolve()
            if not candidate.is_relative_to(root):
                row["status"] = "PATH_ESCAPE"
            elif not candidate.exists():
                row["status"] = "MISSING"
            else:
                actual = digest_file(candidate)
                row["actual"] = actual
                if actual != expected:
                    row["status"] = "HASH_MISMATCH"
        if row["status"] != "OK":
            failed += 1
        rows.append(row)
    return {"ok": failed == 0, "checked": len(rows), "failed": failed, "records": rows}


def manifest_records(manifest: dict, *, pptx_path: str | None = None,
                     semantic_deck_path: str | None = None) -> list[dict]:
    """Project a delivery manifest into verifiable file records.

    The manifest stores digests for artifacts whose paths are not recorded in it,
    so callers must supply the paths they have. Anything without a path is
    reported as UNVERIFIABLE rather than silently treated as verified.
    """
    records: list[dict] = []
    if pptx_path is not None:
        records.append({"path": pptx_path, "sha256": manifest.get("pptx_sha256", "")})
    if semantic_deck_path is not None:
        records.append({"path": semantic_deck_path,
                        "sha256": manifest.get("semantic_deck_sha256", "")})
    for item in manifest.get("source_document_hashes", []) or []:
        records.append({"path": item.get("path"), "sha256": item.get("sha256", "")})
    return records


def verify_document(data: Any, key: str = "audit_chain", project_key: str = "projects") -> dict:
    """Verify every chain inside a persisted document.

    Handles the shapes a third party actually receives:
      * a bare chain: ``[{entry}, ...]``
      * one project object: ``{"id": ..., "audit_chain": [...]}``
      * the application store: ``[{project}, {project}, ...]``
      * a wrapper object: ``{"projects": [...]}``
    """
    targets: list[tuple[str, Any]] = []

    def _is_entry(value: Any) -> bool:
        return isinstance(value, dict) and "entry_hash" in value

    def _label(item: dict, index: int) -> str:
        return str(item.get("id") or item.get("project_id") or f"#{index}")

    if isinstance(data, list):
        if data and all(_is_entry(x) for x in data):
            targets = [("<root>", data)]
        else:
            for index, item in enumerate(data):
                if isinstance(item, dict) and key in item:
                    targets.append((_label(item, index), item[key]))
    elif isinstance(data, dict):
        if key in data:
            targets = [(str(data.get("id") or data.get("project_id") or "<root>"), data[key])]
        elif _is_entry(data):
            targets = [("<root>", [data])]
        elif isinstance(data.get(project_key), list):
            return verify_document(data[project_key], key, project_key)

    if not targets:
        return {"ok": False, "code": "NO_CHAIN_FOUND", "failed": 1, "targets": [],
                "reason": f"no '{key}' found in the supplied document"}

    rows = []
    for label, chain in targets:
        result = verify_chain(chain or [])
        rows.append({"target": label, **result})
    failed = sum(1 for row in rows if not row["ok"])
    return {"ok": failed == 0, "targets": rows, "failed": failed,
            "claim_boundary": ("tail truncation is not detectable without an "
                               "external anchor")}


# ------------------------------------------------------------------------ CLI
def _load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _cmd_verify_chain(argv: list[str]) -> int:
    path = argv[0]
    key = argv[argv.index("--key") + 1] if "--key" in argv else "audit_chain"
    result = verify_document(_load(path), key=key)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def _cmd_verify_files(argv: list[str]) -> int:
    bundle = argv[0]
    manifest = _load(argv[1])
    pptx = argv[argv.index("--pptx") + 1] if "--pptx" in argv else None
    deck = argv[argv.index("--deck") + 1] if "--deck" in argv else None
    result = verify_files(bundle, manifest_records(manifest, pptx_path=pptx,
                                                   semantic_deck_path=deck))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def _cmd_head(argv: list[str]) -> int:
    data = _load(argv[0])
    if isinstance(data, dict) and "audit_chain" in data:
        chain = data["audit_chain"]
    elif isinstance(data, list) and data and isinstance(data[0], dict) and "audit_chain" in data[0]:
        chain = data[0]["audit_chain"]
    else:
        chain = data
    print(head_hash(chain or []))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        print("usage: provenance.py verify-chain <json> [--key audit_chain]")
        print("       provenance.py verify-files <bundle_dir> <manifest.json> "
              "[--pptx rel] [--deck rel]")
        print("       provenance.py head <json>")
        return 2
    command, rest = args[0], args[1:]
    if command == "verify-chain":
        return _cmd_verify_chain(rest)
    if command == "verify-files":
        return _cmd_verify_files(rest)
    if command == "head":
        return _cmd_head(rest)
    print(f"unknown command {command!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
