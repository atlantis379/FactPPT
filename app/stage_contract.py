"""Small, deterministic contracts for presentation delivery stages.

Stage records describe the exact bytes handed from one stage to the next. They
are evidence of execution and freshness, not a substitute for semantic review.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "delivery-stages.v1"
STAGES = ("approved_content", "page_plan", "pptx_build", "pptx_quality")


def digest_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def digest_file(path: str | Path) -> str:
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def stage_record(stage: str, inputs: Mapping[str, str], output_sha256: str,
                 *, status: str = "PASS", tool: str) -> dict[str, Any]:
    if stage not in STAGES or status not in {"PASS", "FAIL"}:
        raise ValueError("Unsupported delivery stage or status")
    if not tool or not inputs or any(not key or not value for key, value in inputs.items()):
        raise ValueError("Stage inputs and tool identity are required")
    if len(output_sha256) != 64 or any(char not in "0123456789abcdef" for char in output_sha256):
        raise ValueError("Stage output must be a lowercase SHA-256 digest")
    return {"stage": stage, "status": status, "tool": tool,
            "inputs": dict(sorted(inputs.items())), "output_sha256": output_sha256}


def validate_chain(records: list[dict[str, Any]]) -> None:
    if [record.get("stage") for record in records] != list(STAGES):
        raise ValueError("Delivery stages are missing or out of order")
    if any(record.get("status") != "PASS" for record in records):
        raise ValueError("A delivery stage did not pass")
    expected_links = (
        (1, "approved_content", 0),
        (2, "page_plan", 1),
        (3, "pptx_build", 2),
    )
    for later, input_name, earlier in expected_links:
        if records[later].get("inputs", {}).get(input_name) != records[earlier].get("output_sha256"):
            raise ValueError(f"Stale or missing stage link: {input_name}")
