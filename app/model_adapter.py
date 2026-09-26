"""Model-adapter contracts and audit records.

This module is the stable boundary between the application and whatever produced a
result. It does not decide *whether* a capability may run — that is
`app/semantic_model.py` for semantic acts and the generation capability registry for
rendering. It decides what a run is allowed to record.

Two rules hold here:

* an external adapter may not be recorded without an explicit data-egress decision
  naming the capability, the policy and the payload that left the machine;
* every run keeps adapter/model/prompt versions plus input and output hashes, so a
  later reviewer can tell which engine produced which judgement.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any


LOCAL_DETERMINISTIC_ADAPTER = {
    "adapter_id": "local-deterministic",
    "provider": "local",
    "model_id": "rule-engine",
    "model_version": "v0.1",
    "external": False,
    "qualified_capabilities": ["source_candidate_extraction", "triage", "architect", "verification"],
}

#: Fields an egress decision must carry for an external run to be recordable.
REQUIRED_EGRESS_FIELDS = {"capability", "decision", "payload_sha256", "payload_bytes"}


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_egress_decision(egress: Any) -> dict[str, Any]:
    """Reject an egress record that cannot be audited after the fact."""
    if not isinstance(egress, dict):
        raise ValueError("External adapters require an explicit data-egress decision object")
    missing = sorted(REQUIRED_EGRESS_FIELDS - set(egress))
    if missing:
        raise ValueError("Data-egress decision is incomplete: " + ", ".join(missing))
    if egress.get("decision") not in {"EGRESS_APPROVED", "LOOPBACK_NO_EGRESS"}:
        raise ValueError(f"Data-egress decision is not an approval: {egress.get('decision')}")
    return egress


def record_run(agent: str, input_data: Any, output_data: Any, *,
               adapter: dict[str, Any] = LOCAL_DETERMINISTIC_ADAPTER,
               prompt_version: str = "deterministic-v0.1",
               egress: dict[str, Any] | None = None) -> dict[str, Any]:
    if adapter.get("external"):
        egress = validate_egress_decision(egress)
    record = {
        "run_id": f"run_{uuid.uuid4().hex[:10]}",
        "agent": agent,
        "adapter_id": adapter["adapter_id"],
        "provider": adapter["provider"],
        "model_id": adapter["model_id"],
        "model_version": adapter["model_version"],
        "prompt_version": prompt_version,
        "external": bool(adapter.get("external")),
        "input_hash": _digest(input_data),
        "output_hash": _digest(output_data),
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }
    if egress is not None:
        record["data_egress"] = egress
    return record


def semantic_adapter(model: dict[str, Any]) -> dict[str, Any]:
    """Describe a configured semantic endpoint as an adapter for audit purposes.

    The registry, not this descriptor, decides what the endpoint is qualified to do;
    `qualified_capabilities` here is deliberately empty so a deployment cannot read
    a qualification out of a runtime object.
    """
    return {
        "adapter_id": model["adapter_id"],
        "provider": "external" if model.get("external") else "local",
        "model_id": model["model_id"],
        "model_version": "deployment-declared",
        "external": bool(model.get("external")),
        "qualified_capabilities": [],
    }


def list_adapters(semantic_model: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    adapters = [LOCAL_DETERMINISTIC_ADAPTER]
    if semantic_model is not None:
        adapters.append(semantic_adapter(semantic_model))
    return adapters
