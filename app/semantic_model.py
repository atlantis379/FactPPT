# -*- coding: utf-8 -*-
"""Semantic-act model gateway: reading, structure, narrative, allocation.

Policy context: `skills/auditable-medical-presentation-reference/references/project/
docs/workflows/SOURCE_READING_TO_NARRATIVE_DERIVATION_POLICY_v0.2.md`. Reading,
structure, narrative and allocation are semantic acts performed by a language
model; deterministic code verifies that they happened, that their claims are
traceable, and that their judgements are declared. Code never produces them, and
the model never grades itself.

This module is the gateway, not the model. It answers three questions and nothing
else:

* **May this capability leave the machine at all?** The engine must be declared in
  `config/semantic_model_capabilities.json` (version-controlled, evidence-backed)
  and be qualified for that capability. An engine cannot be qualified by request,
  and a route without qualification is refused rather than attempted.
* **What is the smallest payload the capability needs?** The registry declares an
  egress contract per capability; `build_payload` applies its allow-list, so a
  forbidden field cannot ride along by accident.
* **What did the model say?** `call_semantic_model` returns parsed JSON for the
  deterministic validators in `app/main.py` to judge. Nothing here writes project
  state, and nothing here trusts model output.

A loopback endpoint is not egress: data stays on the machine, so only the
qualification gate applies. An external endpoint additionally requires the project
to opt in twice — once for external generation, and, for a capability that needs
the source text itself, once more for source-text egress.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "semantic_model_capabilities.json"

#: Source-text egress ladder, weakest first. There is deliberately no "partial" rung:
#: the reading rule requires the full extracted text, so a half-egress policy would
#: exist only to be misapplied. The registry declares the minimum a capability needs.
SOURCE_TEXT_POLICY_LADDER = ("DENY", "FULL_TEXT")

#: Capabilities that need the actual source text must declare it separately from
#: editorial/external generation: sending a patient-facing source document off the
#: machine is a different decision from sending a design brief.
EXTERNAL_GENERATION_POLICY = "CONTRACT_MINIMIZED"


class SemanticGatewayError(ValueError):
    """A semantic capability is unqualified, unpermitted, or answered invalidly."""


# --------------------------------------------------------------------- registry
def load_semantic_registry(path: Path | None = None) -> dict[str, Any]:
    """Load the deployment-owned semantic capability registry."""
    target = path or REGISTRY_PATH
    try:
        registry = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SemanticGatewayError(f"Semantic capability registry is unreadable: {target}") from error
    for key in ("engines", "capabilities"):
        if not isinstance(registry.get(key), dict):
            raise SemanticGatewayError(f"Semantic capability registry is missing '{key}'")
    return registry


def capability_contract(capability: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or load_semantic_registry()
    contract = registry["capabilities"].get(capability)
    if contract is None:
        raise SemanticGatewayError(f"Unknown semantic capability: {capability}")
    return contract


def qualified_engine(capability: str, registry: dict[str, Any] | None = None,
                     engine_id: str | None = None) -> tuple[str, dict[str, Any]]:
    """The model-pipeline engine allowed to execute this capability, if any.

    The local rule engine answers the same capabilities without leaving the
    machine; it is not returned here because callers ask this to decide whether a
    *model* may run the act.

    `engine_id` pins the question to one registered engine. A deployment may register
    several model engines, and "whichever QUALIFIED engine the dict happens to yield first"
    is not an answer an auditor can rely on: the endpoint configuration must be able to say
    which registered engine is behind the URL.
    """
    registry = registry or load_semantic_registry()
    failures: list[str] = []
    for candidate_id, engine in registry["engines"].items():
        if engine_id is not None and candidate_id != engine_id:
            continue
        if engine.get("execution_kind") != "MODEL_PIPELINE":
            failures.append(f"{candidate_id}: is not a MODEL_PIPELINE engine")
            continue
        if capability not in (engine.get("capabilities") or []):
            failures.append(f"{candidate_id}: does not declare {capability}")
            continue
        status = engine.get("qualification_status")
        if status != "QUALIFIED":
            basis = engine.get("qualification_basis") or {}
            missing = basis.get("required_benchmark_suite", "unspecified benchmark suite")
            evidence = basis.get("evidence_refs") or []
            failures.append(f"{candidate_id}: {status}; requires {missing} with recorded evidence "
                            f"(evidence_refs={len(evidence)})")
            continue
        return candidate_id, engine
    if engine_id is not None and not failures:
        failures.append(f"{engine_id}: not present in the semantic capability registry")
    raise SemanticGatewayError(
        f"No qualified model engine for semantic capability '{capability}'. "
        + " | ".join(failures or ["no MODEL_PIPELINE engine is registered"]))


# ------------------------------------------------------------------- endpoint
def configured_semantic_model() -> dict[str, Any] | None:
    """Environment-declared chat endpoint; secrets stay in environment variables.

    Returns None when nothing is configured, which keeps the deterministic engine
    the default rather than an error.
    """
    url = os.environ.get("EASYPPT_SEMANTIC_MODEL_URL", "").strip()
    model_id = os.environ.get("EASYPPT_SEMANTIC_MODEL_ID", "").strip()
    if not url or not model_id:
        return None
    parsed = urlparse(url)
    loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    allowed_schemes = {"http", "https"} if loopback else {"https"}
    if parsed.scheme not in allowed_schemes or not parsed.hostname:
        raise SemanticGatewayError("Semantic model URL must be loopback HTTP or HTTPS")
    engine_id = os.environ.get("EASYPPT_SEMANTIC_MODEL_ENGINE", "").strip() or None
    return {"url": url, "model_id": model_id, "external": not loopback,
            "engine_id": engine_id, "adapter_id": f"openai-compatible:{model_id}"}


# ------------------------------------------------------------------ egress gate
def _policy_rank(policy: str) -> int:
    if policy not in SOURCE_TEXT_POLICY_LADDER:
        raise SemanticGatewayError(f"Unknown source-text egress policy: {policy}")
    return SOURCE_TEXT_POLICY_LADDER.index(policy)


def egress_plan(project: Any, capability: str, model: dict[str, Any],
                registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Decide whether this capability may run on this model, and record why.

    Gate order is deliberate: an unknown capability fails before a permission
    question is asked, and an unqualified engine fails before a project policy is
    consulted, because no policy can authorise an unqualified route.
    """
    registry = registry or load_semantic_registry()
    contract = capability_contract(capability, registry)
    engine_id, engine = qualified_engine(capability, registry, model.get("engine_id"))
    exchange = contract["egress_contract"]
    external = bool(model.get("external"))
    plan: dict[str, Any] = {
        "capability": capability,
        "engine_id": engine_id,
        "engine_version": engine.get("engine_version"),
        "external": external,
        "payload_kind": exchange["payload_kind"],
        "allowed_fields": list(exchange["allowed_fields"]),
        "requires_source_text": bool(exchange.get("requires_source_text")),
    }
    if not external:
        plan["decision"] = "LOOPBACK_NO_EGRESS"
        return plan
    if not engine.get("external_data_egress"):
        raise SemanticGatewayError(
            f"Engine {engine_id} is not approved for external data egress; "
            f"capability '{capability}' cannot run on {model['adapter_id']}")
    if exchange.get("requires_source_text"):
        if not getattr(project, "allow_source_text_egress", False):
            raise SemanticGatewayError(
                f"Capability '{capability}' sends source document text off the machine. "
                "Set allow_source_text_egress=true on the project to accept that.")
        minimum = exchange.get("minimum_source_text_policy", "FULL_TEXT")
        actual = getattr(project, "source_text_egress_policy", "DENY")
        if _policy_rank(actual) < _policy_rank(minimum):
            raise SemanticGatewayError(
                f"Capability '{capability}' requires source_text_egress_policy>={minimum}; "
                f"project is at {actual}.")
        plan["policy"] = actual
    else:
        if not getattr(project, "allow_external_generation", False):
            raise SemanticGatewayError(
                f"Capability '{capability}' would leave the machine. "
                "Set allow_external_generation=true on the project to accept that.")
        actual = getattr(project, "generation_data_egress_policy", "DENY")
        if actual != EXTERNAL_GENERATION_POLICY:
            raise SemanticGatewayError(
                f"Capability '{capability}' requires generation_data_egress_policy="
                f"{EXTERNAL_GENERATION_POLICY}; project is at {actual}.")
        plan["policy"] = actual
    plan["decision"] = "EGRESS_APPROVED"
    return plan


def build_payload(capability: str, source: dict[str, Any],
                  registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the payload the capability needs, filtered by its egress contract.

    The allow-list is enforced rather than documented: a field the contract does
    not name is dropped here, so a caller cannot widen egress by passing more.
    """
    registry = registry or load_semantic_registry()
    exchange = capability_contract(capability, registry)["egress_contract"]
    allowed = set(exchange["allowed_fields"])

    def keep(record: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in record.items() if key in allowed}

    if capability == "source_candidate_extraction":
        pages = [keep({"document_id": page.get("document_id"), "page": page.get("page"),
                       "text": page.get("text", "")}) for page in source.get("pages", [])]
        return {"capability": capability, "payload_kind": exchange["payload_kind"], "pages": pages}
    if capability == "full_source_summary":
        pages = [keep({"page": page.get("page"), "text": page.get("text", ""),
                       "source_block_ids": page.get("source_block_ids", [])})
                 for page in source.get("pages", [])]
        return {"capability": capability, "payload_kind": exchange["payload_kind"],
                "reading_structure_sha256": source.get("reading_structure_sha256"),
                "source_sha256": source.get("source_sha256"), "pages": pages}
    if capability == "triage":
        return {"capability": capability, "payload_kind": exchange["payload_kind"],
                "presentation_question": source.get("presentation_question", ""),
                "audience": source.get("audience", ""),
                "duration_minutes": source.get("duration_minutes"),
                "claims": [keep(claim) for claim in source.get("claims", [])]}
    if capability == "architect":
        return {"capability": capability, "payload_kind": exchange["payload_kind"],
                "presentation_question": source.get("presentation_question", ""),
                "audience": source.get("audience", ""),
                "duration_minutes": source.get("duration_minutes"),
                "claims": [keep(claim) for claim in source.get("claims", [])]}
    raise SemanticGatewayError(f"No payload builder for capability: {capability}")


def payload_fingerprint(payload: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return {"payload_sha256": hashlib.sha256(encoded).hexdigest(), "payload_bytes": len(encoded)}


# ---------------------------------------------------------------------- prompt
SYSTEM_PROMPTS = {
    "full_source_summary": """Read every supplied source page and write a section-level summary of the entire material.
Return one JSON object only, with exactly this output shape:
{"schema_version":"full_source_summary.v1","reading_structure_sha256":"<copy from input>",
 "source_sha256":"<copy from input>","overall_summary":"<substantive prose>",
 "sections":[{"section_id":"s01","title":"<semantic section title>",
 "summary":"<substantive source-grounded prose>","source_block_ids":[1,2]}]}
Choose sections by the argument and content, not by page breaks or a slide template. Cite only
block IDs supplied alongside supporting source pages, and cite at least one block from EVERY page
across the sections, including material omitted from a presentation. Keep all meaning-critical
populations, conditions, comparisons, thresholds, units, recommendations, dates, uncertainty and
limitations. Preserve disagreements and historical context; do not import outside medical facts,
silently correct unclear OCR, or turn an observation into advice. If a page is unreadable or the
material cannot be summarized faithfully, return {"error":"<reason>","pages":[<page numbers>]}
instead of fabricating a complete summary.""",
    "source_candidate_extraction": """You read a medical source document and report what it says.
Return JSON only, no commentary:
{"units":[{"page":<int>,"status":"HAS_CANDIDATES"|"NO_QUOTABLE_CONTENT","reason":"<required only when declined>","paragraph_exclusions": [{"paragraph": 0, "reason": "HEADING_OR_LABEL"}],
    "exclusions":[{"token":"<verbatim value>","reason":"<why it stays out>"}]}],
 "candidates":[{"page":<int>,"quote":"<verbatim>","claim":"<one atomic assertion>"}]}
Account for EVERY page you were given, exactly once, in `units`. Use HAS_CANDIDATES when the page
states something quotable, and quote it in `candidates`. Use NO_QUOTABLE_CONTENT only for pages that
carry no assertion (masthead, reference list, acknowledgements, table of contents), and give a reason
from: MASTHEAD_OR_PUBLICATION_METADATA, REFERENCE_LIST, ACKNOWLEDGEMENT_OR_CONTRIBUTION,
TABLE_OF_CONTENTS, DUPLICATE_OF_ANOTHER_UNIT, OTHER.
Every candidate MUST carry a quote copied character-for-character from the provided page text.
A quote that does not appear verbatim in that page will be discarded by the validator, so do not
paraphrase, translate, merge or tidy it. One candidate states one assertion.
Report every threshold (>=, <=, <, >), every measurement with a unit, and every magnitude figure the
source states; each is either carried by one of your quotes or listed in that page's `exclusions` with
a reason from: NOT_DECISION_RELEVANT_FOR_AUDIENCE, DUPLICATED_ELSEWHERE_IN_DECK,
CONTEXT_ONLY_NOT_A_FINDING, SUPERSEDED_BY_ANOTHER_TOKEN, SOURCE_ITSELF_QUALIFIES_OR_RETRACTS.
A threshold may NOT be excluded: if the source states one, quote it.
Account for paragraphs, not just pages: every paragraph of 40 characters or more is either
represented by one of your quotes or listed in that page's `paragraph_exclusions` (by paragraph
index, counting from 0, blank lines skipped) with a reason from: HEADING_OR_LABEL,
TABLE_OR_FIGURE_CAPTION, OPERATIONAL_DETAIL, DUPLICATED_ELSEWHERE_IN_DECK, CONTEXT_ONLY_NOT_A_FINDING,
NOT_DECISION_RELEVANT_FOR_AUDIENCE, SUPERSEDED_BY_ANOTHER_TOKEN, SOURCE_ITSELF_QUALIFIES_OR_RETRACTS.
A page yielding one quotable sentence is not evidence that the page was read: a whole treatment table
once went unextracted from a page that had already produced candidates, and the page-level rule passed.
Read broadly — the selection of what a presentation shows is a later, separate act. Never infer a
relationship between statements, never add a number that is not in the quote, never add clinical
advice, and never fill a gap with general knowledge. If a page states nothing quotable, decline it
with a reason.""",
    "triage": """You choose which approved claims a time-boxed presentation must include.
Return JSON only, no commentary:
{"decisions":[{"claim_id":"...","bucket":"MUST_INCLUDE","reason":"<short>"}]}
The bucket is one of MUST_INCLUDE, SHOULD_INCLUDE, APPENDIX, EXCLUDED. Judge only by the
presentation question and the supplied claim text. Every supplied claim id appears exactly once.
Do not rewrite a claim, do not add a claim, and do not decide that a claim is medically wrong.""",
    "architect": """You order approved claims for one audience and allocate them to pages.
Return JSON only, no commentary:
{"narrative_spine":"<one sentence>","pages":[{"page_id":"...","title":"<action title>",
"primary_message":"<takeaway>","claim_ids":["..."],"why_this_page":"<why the page exists>",
"figure_intent":"COMPARISON"}]}
figure_intent is one of CAUSAL, PROGRESSION, COMPARISON, TAXONOMY, PROCESS, SCALE, DATA,
QUOTATION, NONE. Use every supplied claim exactly once and at most four claims per page. Keep
claim text byte-identical: you choose order, grouping and page intent, never the wording of
evidence. why_this_page states why the page exists, not what it contains. Never invent a claim,
number or relationship, and never drop a claim to save space.""",
}


def call_semantic_model(capability: str, payload: dict[str, Any],
                        model: dict[str, Any]) -> dict[str, Any]:
    """One model call. Returns parsed JSON for deterministic validation."""
    if capability not in SYSTEM_PROMPTS:
        raise SemanticGatewayError(f"No prompt declared for capability: {capability}")
    body = {
        "model": model["model_id"],
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPTS[capability]},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("EASYPPT_SEMANTIC_MODEL_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(model["url"], data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     headers=headers, method="POST")
    try:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, fp, code, msg, headers, newurl):
                return None

        with urllib.request.build_opener(NoRedirect).open(request, timeout=180) as response:
            answer = json.loads(response.read().decode("utf-8"))
        content = answer["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(content)
    except urllib.error.HTTPError as error:
        # An endpoint that refuses the request usually says why. Reporting only
        # "HTTPError" hides the operator's own setup error behind a generic name.
        try:
            detail = error.read().decode("utf-8", "replace")[:500]
        except OSError:
            detail = "<unreadable body>"
        raise SemanticGatewayError(
            f"Semantic model call failed for {capability}: HTTP {error.code} {error.reason}. {detail}") from error
    except (OSError, KeyError, IndexError, TypeError, ValueError) as error:
        raise SemanticGatewayError(
            f"Semantic model call failed for {capability}: {type(error).__name__}") from error
    if not isinstance(parsed, dict):
        raise SemanticGatewayError(f"Semantic model response for {capability} must be a JSON object")
    return parsed


def describe_capabilities(project: Any | None = None) -> dict[str, Any]:
    """Audit view: what is registered, what is qualified, what a project must declare."""
    registry = load_semantic_registry()
    model = configured_semantic_model()
    rows = []
    for capability, contract in registry["capabilities"].items():
        row: dict[str, Any] = {
            "capability": capability,
            "agent": contract.get("agent"),
            "semantic_act": contract.get("semantic_act"),
            "output_validated_by": contract.get("output_validated_by"),
            "rules": contract.get("rules", []),
            "payload_kind": contract["egress_contract"]["payload_kind"],
            "requires_source_text": bool(contract["egress_contract"].get("requires_source_text")),
        }
        try:
            engine_id, _ = qualified_engine(capability, registry,
                                            (model or {}).get("engine_id"))
            row["model_route"] = engine_id
            row["model_route_status"] = "AVAILABLE"
        except SemanticGatewayError as error:
            row["model_route"] = None
            row["model_route_status"] = "BLOCKED"
            row["model_route_blocker"] = str(error)
        if project is not None and model is not None:
            try:
                row["project_egress"] = egress_plan(project, capability, model, registry)["decision"]
            except SemanticGatewayError as error:
                row["project_egress"] = "BLOCKED"
                row["project_egress_blocker"] = str(error)
        rows.append(row)
    return {"registry_version": registry.get("registry_version"), "model_configured": model is not None,
            "model_adapter": model["adapter_id"] if model else None,
            "model_external": model["external"] if model else None,
            "deterministic_fallback": "local_deterministic", "capabilities": rows}
