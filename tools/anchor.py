"""External anchors: close the tail-truncation gap, and bind a head to a key.

S0's chain detects edits, reordering and mid-chain deletion, but NOT tail
truncation: removing trailing entries leaves a shorter yet perfectly valid chain.
An anchor records a chain head in a store outside the chain, so a shortened chain
can no longer match what was published.

Two independent mechanisms
--------------------------
1. **Append-only anchor file** (stdlib verifiable). Each anchor links to the
   previous one, so "append-only" is enforced by cryptography rather than by
   convention: rewriting or deleting an earlier anchor breaks the anchor chain.
2. **Ed25519 signature** (needs ``cryptography``). Binds the head to a key so a
   third party can attribute it. If the library is absent, verification reports
   ``SIGNATURE_LIB_MISSING`` -- it never reports success it cannot justify.

Not implemented here
--------------------
RFC 3161 TSA attestation. The plan called for ``--tsa <url>``; this environment
resolves every TSA hostname into 198.18.0.0/15 (a DNS-interception range), so a
live timestamp token cannot be validated here. Shipping an unexercised network
crypto path would contradict the evidence discipline this work exists to enforce,
so TSA is deliberately deferred to S1.1 with a documented seam (``tsa`` block in
the anchor record) rather than faked.
"""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

# Importable both as a package module (`from tools import anchor`) and as a
# standalone script (`python tools/anchor.py ...`). Without this fallback the
# documented third-party command fails from a plain shell, because running a
# script puts tools/ -- not the repository root -- on sys.path.
try:
    from tools import provenance as P
except ImportError:  # pragma: no cover - exercised by the subprocess test
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools import provenance as P

ANCHOR_VERSION = 1
GENESIS_ANCHOR = "0" * 64
ANCHOR_DOMAIN = "easyPPT.anchor.v1"

# verification codes
A_OK = "OK"
A_EMPTY = "EMPTY"
A_MALFORMED = "MALFORMED_ANCHOR"
A_UNSUPPORTED = "UNSUPPORTED_ANCHOR_VERSION"
A_SEQ_MISMATCH = "ANCHOR_SEQ_MISMATCH"
A_LINK_MISMATCH = "ANCHOR_LINK_MISMATCH"
A_HASH_MISMATCH = "ANCHOR_HASH_MISMATCH"
A_BACKDATED = "ANCHOR_BACKDATED"

# chain-vs-anchor codes
C_OK = "OK"
C_TRUNCATED = "CHAIN_TRUNCATED_BELOW_ANCHOR"
C_HEAD_MISMATCH = "CHAIN_HEAD_MISMATCH"
C_NO_ANCHOR = "NO_ANCHOR_FOR_PROJECT"

# signature codes
S_OK = "SIGNATURE_OK"
S_INVALID = "SIGNATURE_INVALID"
S_MISSING = "SIGNATURE_MISSING"
S_LIB_MISSING = "SIGNATURE_LIB_MISSING"
S_KEY_MISSING = "SIGNATURE_KEY_MISSING"

SIGNED_FIELDS = ("version", "seq", "at", "project_id", "chain_length",
                 "chain_head", "prev_anchor_hash", "note")


# ------------------------------------------------------------------ primitives
def _cryptography():
    """Return the Ed25519 module, or None when the library is unavailable."""
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
        return ed25519
    except Exception:  # noqa: BLE001
        return None


def signing_payload(record: dict) -> bytes:
    """Canonical bytes a signature covers: every field except the signatures."""
    material = {key: record.get(key) for key in SIGNED_FIELDS if key in record}
    material["domain"] = ANCHOR_DOMAIN
    return P.canonical_json(material).encode("utf-8")


def anchor_hash(record: dict) -> str:
    return P.sha256_hex(signing_payload(record))


def make_anchor(*, prev_anchor_hash: str, seq: int, at: str, project_id: str,
                chain_length: int, chain_head: str, note: str = "",
                version: int = ANCHOR_VERSION) -> dict:
    record = {
        "version": version,
        "seq": seq,
        "at": at,
        "project_id": project_id,
        "chain_length": int(chain_length),
        "chain_head": chain_head,
        "prev_anchor_hash": prev_anchor_hash,
        "note": note,
    }
    record["anchor_hash"] = anchor_hash(record)
    record["signatures"] = []
    return record


def last_anchor_hash(anchors: Sequence[dict]) -> str:
    if not anchors:
        return GENESIS_ANCHOR
    return anchors[-1].get("anchor_hash", GENESIS_ANCHOR)


def _anchor_reason(record: Any, seq: int, prev: str) -> str | None:
    if not isinstance(record, dict):
        return A_MALFORMED
    required = ("version", "seq", "at", "project_id", "chain_length",
                "chain_head", "prev_anchor_hash", "anchor_hash")
    if any(key not in record for key in required):
        return A_MALFORMED
    if record["version"] != ANCHOR_VERSION:
        return A_UNSUPPORTED
    if record["seq"] != seq:
        return A_SEQ_MISMATCH
    if record["prev_anchor_hash"] != prev:
        return A_LINK_MISMATCH
    if anchor_hash(record) != record["anchor_hash"]:
        return A_HASH_MISMATCH
    return None


def verify_anchor_file(anchors: Sequence[dict]) -> dict:
    """Verify the anchor file's own append-only chain (stdlib only)."""
    result = {"ok": False, "code": A_EMPTY, "count": len(anchors),
              "first_bad_index": None, "head_hash": GENESIS_ANCHOR,
              "reason": "no anchors recorded"}
    if not anchors:
        return result
    prev = GENESIS_ANCHOR
    prev_at = ""
    for index, record in enumerate(anchors):
        reason = _anchor_reason(record, index, prev)
        if reason is not None:
            result.update({"ok": False, "code": reason, "first_bad_index": index,
                           "head_hash": prev,
                           "reason": f"anchor {index} failed: {reason}"})
            return result
        # timestamps must not go backwards: an append-only log cannot be back-dated
        if prev_at and str(record["at"]) < prev_at:
            result.update({"ok": False, "code": A_BACKDATED, "first_bad_index": index,
                           "head_hash": prev,
                           "reason": f"anchor {index} predates its predecessor"})
            return result
        prev = record["anchor_hash"]
        prev_at = str(record["at"])
    result.update({"ok": True, "code": A_OK, "head_hash": prev,
                   "reason": "anchor chain intact"})
    return result


# ------------------------------------------------------------------ file I/O
def load_anchors(path: str | Path) -> list[dict]:
    file = Path(path)
    if not file.exists():
        return []
    anchors = []
    for order, line in enumerate(file.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            anchors.append(json.loads(line))
        except json.JSONDecodeError:
            anchors.append({"__malformed_line__": order, "raw": line})
    return anchors


def append_anchor(path: str | Path, record: dict) -> dict:
    """Append one anchor, refusing anything that would break append-only order."""
    file = Path(path)
    existing = load_anchors(file)
    # an anchor file that is already broken must not be extended silently
    if existing:
        state = verify_anchor_file(existing)
        if not state["ok"]:
            raise ValueError(
                f"refusing to append: existing anchor file is {state['code']} "
                f"at index {state['first_bad_index']}"
            )
    expected_prev = last_anchor_hash(existing)
    if record.get("prev_anchor_hash") != expected_prev:
        raise ValueError("refusing to append: anchor does not link to the current head")
    if record.get("seq") != len(existing):
        raise ValueError("refusing to append: anchor seq does not continue the file")
    file.parent.mkdir(parents=True, exist_ok=True)
    with open(file, "a", encoding="utf-8") as handle:
        handle.write(P.canonical_json(record) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return record


# --------------------------------------------------------------------- signing
def generate_keypair(private_path: str | Path, public_path: str | Path) -> dict:
    ed25519 = _cryptography()
    if ed25519 is None:
        raise RuntimeError(S_LIB_MISSING)
    from cryptography.hazmat.primitives import serialization
    key = ed25519.Ed25519PrivateKey.generate()
    priv = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    for target, blob in ((private_path, priv), (public_path, pub)):
        p = Path(target)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
    return {"private_key": str(private_path), "public_key": str(public_path),
            "algorithm": "ed25519", "public_pem": pub.decode("utf-8")}


def sign_anchor(record: dict, private_path: str | Path, *, signer: str = "") -> dict:
    """Attach a detached signature over the anchor's signed fields."""
    ed25519 = _cryptography()
    if ed25519 is None:
        raise RuntimeError(S_LIB_MISSING)
    from cryptography.hazmat.primitives import serialization
    key_file = Path(private_path)
    if not key_file.exists():
        raise RuntimeError(S_KEY_MISSING)
    key = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
    signature = key.sign(signing_payload(record))
    entry = {"signer": signer or key_file.stem, "algorithm": "ed25519",
             "signature": base64.b64encode(signature).decode("ascii")}
    record.setdefault("signatures", []).append(entry)
    return record


def verify_signature(record: dict, public_path: str | Path) -> dict:
    """Verify every attached signature. Never reports OK it cannot justify."""
    signatures = record.get("signatures") or []
    if not signatures:
        return {"ok": False, "code": S_MISSING,
                "reason": "anchor carries no signature"}
    ed25519 = _cryptography()
    if ed25519 is None:
        return {"ok": False, "code": S_LIB_MISSING,
                "reason": "cryptography library unavailable; signature cannot be checked"}
    from cryptography.hazmat.primitives import serialization
    key_file = Path(public_path)
    if not key_file.exists():
        return {"ok": False, "code": S_KEY_MISSING,
                "reason": f"public key not found: {key_file}"}
    public_key = serialization.load_pem_public_key(key_file.read_bytes())
    payload = signing_payload(record)
    checked = []
    for entry in signatures:
        try:
            raw = base64.b64decode(entry.get("signature", ""), validate=True)
            public_key.verify(raw, payload)
            checked.append({"signer": entry.get("signer"), "ok": True})
        except Exception as exc:  # noqa: BLE001
            checked.append({"signer": entry.get("signer"), "ok": False,
                            "error": type(exc).__name__})
    failed = [row for row in checked if not row["ok"]]
    if failed:
        return {"ok": False, "code": S_INVALID, "checked": checked,
                "reason": f"{len(failed)} signature(s) failed verification"}
    return {"ok": True, "code": S_OK, "checked": checked,
            "reason": f"{len(checked)} signature(s) verified"}


# ------------------------------------------------------- chain vs anchor
def latest_anchor_for(anchors: Sequence[dict], project_id: str) -> dict | None:
    found = None
    for record in anchors:
        if record.get("project_id") == project_id and "anchor_hash" in record:
            found = record
    return found


def verify_against_chain(anchors: Sequence[dict], project_id: str,
                         chain: Sequence[dict]) -> dict:
    """The S1 acceptance check: a shortened chain can no longer match its anchor."""
    anchor = latest_anchor_for(anchors, project_id)
    if anchor is None:
        return {"ok": False, "code": C_NO_ANCHOR, "project_id": project_id,
                "reason": "project has never been anchored"}
    anchored_len = int(anchor.get("chain_length", 0))
    anchored_head = anchor.get("chain_head")
    current_len = len(chain)

    if current_len < anchored_len:
        return {"ok": False, "code": C_TRUNCATED, "project_id": project_id,
                "anchored_length": anchored_len, "current_length": current_len,
                "reason": (f"chain has {current_len} entries but {anchored_len} were "
                           f"anchored: entries were removed")}
    entry_hash = chain[anchored_len - 1].get("entry_hash") if anchored_len else None
    if anchored_len and entry_hash != anchored_head:
        return {"ok": False, "code": C_HEAD_MISMATCH, "project_id": project_id,
                "anchored_length": anchored_len,
                "anchored_head": anchored_head, "actual_head": entry_hash,
                "reason": "the entry at the anchored position no longer matches the anchor"}
    return {"ok": True, "code": C_OK, "project_id": project_id,
            "anchored_length": anchored_len, "current_length": current_len,
            "grown_by": current_len - anchored_len,
            "reason": "chain is consistent with its anchor"}


def verify_all(anchor_path: str | Path, projects_path: str | Path,
               public_key: str | Path | None = None) -> dict:
    """Full external verification: anchor file, each chain, anchor consistency, signatures.

    An external verifier must be a COMPLETE check. Checking only anchor
    consistency would report success for a chain that is internally broken.
    """
    anchors = load_anchors(anchor_path)
    file_state = verify_anchor_file(anchors)
    data = json.loads(Path(projects_path).read_text(encoding="utf-8"))
    projects = data if isinstance(data, list) else data.get("projects", [])
    rows, failed = [], 0
    for project in projects:
        project_id = str(project.get("id") or project.get("project_id") or "?")
        chain = project.get("audit_chain") or []
        chain_state = P.verify_chain(chain)
        against = verify_against_chain(anchors, project_id, chain)
        anchor = latest_anchor_for(anchors, project_id)
        signature = None
        if anchor is not None and public_key is not None:
            signature = verify_signature(anchor, public_key)
        bad = (not chain_state["ok"]) or (not against["ok"]) or \
              (signature is not None and not signature["ok"])
        failed += 1 if bad else 0
        rows.append({"project_id": project_id, "chain": chain_state,
                     "anchor": against, "signature": signature, "ok": not bad})
    ok = file_state["ok"] and failed == 0
    return {"ok": ok, "anchor_file": file_state, "projects_checked": len(rows),
            "failed": failed, "results": rows,
            "claim_boundary": ("an anchor closes tail truncation and binds the head to a "
                              "key; it does not attest the truth of the records, and "
                              "RFC 3161 external time is not implemented in this build")}


# ------------------------------------------------------------------------ CLI
def _read(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _cmd_keygen(argv: list[str]) -> int:
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else Path("keys")
    info = generate_keypair(out / "anchor-ed25519.pem", out / "anchor-ed25519.pub.pem")
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _cmd_append(argv: list[str]) -> int:
    anchor_file, projects_file = argv[0], argv[1]
    note = argv[argv.index("--note") + 1] if "--note" in argv else ""
    key = argv[argv.index("--key") + 1] if "--key" in argv else None
    only = argv[argv.index("--project") + 1] if "--project" in argv else None
    anchors = load_anchors(anchor_file)
    state = verify_anchor_file(anchors) if anchors else {"ok": True}
    if not state["ok"]:
        print(json.dumps({"ok": False, "reason": "anchor file already broken",
                          "anchor_file": state}, ensure_ascii=False, indent=2))
        return 1
    data = _read(projects_file)
    projects = data if isinstance(data, list) else data.get("projects", [])
    written = []
    for project in projects:
        project_id = str(project.get("id") or project.get("project_id") or "?")
        if only and project_id != only:
            continue
        chain = project.get("audit_chain") or []
        if not chain:
            continue
        record = make_anchor(
            prev_anchor_hash=last_anchor_hash(anchors),
            seq=len(anchors),
            at=_now(),
            project_id=project_id,
            chain_length=len(chain),
            chain_head=P.head_hash(chain),
            note=note,
        )
        if key:
            sign_anchor(record, key)
        append_anchor(anchor_file, record)
        anchors.append(record)
        written.append({"project_id": project_id, "chain_length": len(chain),
                        "chain_head": record["chain_head"], "signed": bool(key),
                        "anchor_hash": record["anchor_hash"]})
    print(json.dumps({"ok": bool(written), "anchor_file": str(anchor_file),
                      "appended": written}, ensure_ascii=False, indent=2))
    return 0 if written else 1


def _cmd_verify(argv: list[str]) -> int:
    anchor_file, projects_file = argv[0], argv[1]
    pub = argv[argv.index("--pubkey") + 1] if "--pubkey" in argv else None
    result = verify_all(anchor_file, projects_file, pub)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def _cmd_show(argv: list[str]) -> int:
    anchors = load_anchors(argv[0])
    state = verify_anchor_file(anchors)
    rows = [{"seq": a.get("seq"), "at": a.get("at"), "project_id": a.get("project_id"),
             "chain_length": a.get("chain_length"),
             "chain_head": (a.get("chain_head") or "")[:16],
             "signed": bool(a.get("signatures"))} for a in anchors]
    print(json.dumps({"anchor_file": state, "anchors": rows},
                     ensure_ascii=False, indent=2))
    return 0 if state["ok"] else 1


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        print("usage: anchor.py keygen --out keys")
        print("       anchor.py append <anchors.jsonl> <projects.json> "
              "[--project ID] [--key priv.pem] [--note ...]")
        print("       anchor.py verify <anchors.jsonl> <projects.json> [--pubkey pub.pem]")
        print("       anchor.py show <anchors.jsonl>")
        return 2
    command, rest = args[0], args[1:]
    if command == "keygen":
        return _cmd_keygen(rest)
    if command == "append":
        return _cmd_append(rest)
    if command == "verify":
        return _cmd_verify(rest)
    if command == "show":
        return _cmd_show(rest)
    print(f"unknown command {command!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
