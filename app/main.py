from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.packager import build_pptx, verify_pptx
from app.delivery_evidence import (finalizer_receipt_matches, make_quality_report, validate_quality_report,
                                   write_quality_report)
from app.content_validation import ContentPackage, ContentReport, verify_content_package
from app.content_contract import SourceLocator
from app.delivery_gate import DeliveryDecision
from app.native_beautifier import compile_beautification_plan
from app.editorial_assets import load_editorial_asset_manifest
from app.full_summary import (authoring_brief as full_summary_authoring_brief,
                              digest as full_summary_digest,
                              validate as validate_full_summary,
                              with_locations as summary_with_locations)
from app.layout_ir import (LayoutIntentError, call_layout_model, call_visual_review_model, configured_model,
                           configured_review_model,
                           design_brief, merge_layout_ir, semantic_digest,
                           validate_layout_ir)
from app.model_adapter import LOCAL_DETERMINISTIC_ADAPTER, list_adapters, record_run, semantic_adapter
from app.reading_structure import (FIGURE_INTENTS, STRUCTURE_RENDERING_KINDS, artifact_digest,
                                   join_pages_to_claims, summarize as summarize_reading,
                                   validate_reading_structure)
from app.read_units import (CLASSIFICATIONS, DECLINE_REASONS, EXCLUSION_REASONS,
                            audit_read_receipts, classify_units, terms)
from app.semantic_fidelity import contradiction_signals, missing_source_signals
from app.source_extract import SourceCapacityError, extract_source
from factdeck.jobstats import ensure_job, stage as job_stage
from app.semantic_model import (SemanticGatewayError, build_payload, call_semantic_model,
                                configured_semantic_model, describe_capabilities, egress_plan,
                                payload_fingerprint, qualified_engine)
from app.visual_review import review_issues, sha256_file
from app.visual_quality import issues as visual_quality_issues
from tools import anchor as ANCH
from tools import provenance as PROV

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
STORE = DATA / "projects.json"
ANCHOR_STORE = Path(os.environ.get("EASYPPT_ANCHOR_STORE", DATA / "anchors.jsonl"))
ANCHOR_KEY = DATA / "keys" / "anchor-ed25519.pem"
ANCHOR_PUBKEY = DATA / "keys" / "anchor-ed25519.pub.pem"
REVIEW_STORE = Path(os.environ.get("EASYPPT_REVIEW_STORE", DATA / "reviews.json"))
# No model may approve content until a real benchmark run is accepted by an
# operator and its qualification is installed in the deployment registry.
QUALIFIED_REVIEW_IDS: set[str] = set()
RULES = ROOT / "config" / "rules" / "mvp_rules.json"
GENERATION_CAPABILITY_CONFIG = ROOT / "config" / "generation_capabilities.json"

Provenance = Literal["SOURCE", "SUMMARY", "SYNTHESIS", "EXTERNAL_VERIFICATION"]
Risk = Literal["GREEN", "YELLOW", "RED"]


class SourceRef(BaseModel):
    document_id: str
    page: int = Field(ge=1)
    quote: str
    locator: SourceLocator | None = None


class NumericFact(BaseModel):
    value: str
    unit: str | None = None
    metric: str | None = None
    population: str | None = None
    timeframe: str | None = None
    outcome: str | None = None
    intervention: str | None = None
    comparator: str | None = None
    statistic_type: str | None = None
    status: Literal["BOUND", "PARTIALLY_BOUND", "UNBOUND"] = "BOUND"
    value_origin: Literal["SOURCE_EXACT", "DERIVED_CALCULATION", "ESTIMATED_FROM_FIGURE", "NOT_REPORTED"] = "SOURCE_EXACT"
    derivation_kind: Literal["RELATIVE_REDUCTION", "ABSOLUTE_DIFFERENCE"] | None = None
    derivation_formula: str | None = None
    input_fact_ids: list[str] = []
    value_role: Literal["OBSERVED_VALUE", "CHANGE_FROM_BASELINE", "ABSOLUTE_DIFFERENCE", "RELATIVE_CHANGE"] = "OBSERVED_VALUE"
    comparability_status: Literal["NOT_APPLICABLE", "COMPARABLE", "NOT_COMPARABLE", "UNKNOWN"] = "NOT_APPLICABLE"


class Claim(BaseModel):
    id: str = Field(default_factory=lambda: f"clm_{uuid.uuid4().hex[:8]}")
    version: int = Field(default=1, ge=1)
    supersedes_claim_id: str | None = None
    superseded_by_claim_id: str | None = None
    normalized_claim: str
    source_quote: str | None = None
    provenance: Provenance
    risk: Risk = "YELLOW"
    source_refs: list[SourceRef] = []
    conditions: list[str] = []
    numeric_facts: list[NumericFact] = []
    triage: Literal["MUST_INCLUDE", "SHOULD_INCLUDE", "APPENDIX", "EXCLUDED"] = "SHOULD_INCLUDE"
    review_status: Literal["APPROVED", "NEEDS_HUMAN_REVIEW", "BLOCKED"] = "NEEDS_HUMAN_REVIEW"
    canonical_claim_id: str | None = None
    conflict_group_id: str | None = None
    ambiguity: bool = False


class Relationship(BaseModel):
    id: str = Field(default_factory=lambda: f"rel_{uuid.uuid4().hex[:8]}")
    from_claim_id: str
    to_claim_id: str
    relation_type: str
    direction: Literal["FORWARD", "BIDIRECTIONAL", "NONE"] = "FORWARD"
    logic_operator: Literal["NONE", "AND", "OR", "NOT", "EXCEPT"] = "NONE"
    polarity: Literal["POSITIVE", "NEGATIVE", "NEUTRAL", "CONTRAINDICATION"] = "NEUTRAL"
    recommendation_class: str | None = None
    evidence_level: str | None = None
    provenance: Provenance
    risk: Risk = "YELLOW"
    conditions: list[str] = []
    source_refs: list[SourceRef] = []
    status: Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "NEEDS_HUMAN_REVIEW", "UNSUPPORTED", "CONFLICT", "AMBIGUOUS"] = "NEEDS_HUMAN_REVIEW"
    review_status: Literal["APPROVED", "NEEDS_HUMAN_REVIEW", "BLOCKED"] = "NEEDS_HUMAN_REVIEW"


class PageSpec(BaseModel):
    id: str
    title: str
    primary_message: str
    visual_type: str
    claim_ids: list[str]
    relationship_ids: list[str] = []
    provenance: Provenance
    goal: str
    revision_status: Literal["ACTIVE", "STALE"] = "ACTIVE"
    #: Audit linkage back to the accepted reading: the artifact page this PageSpec was
    #: allocated from, the narrative nodes it renders, and the source blocks it covers.
    reading_page_id: str | None = None
    narrative_node_ids: list[str] = []
    source_block_ids: list[int] = []
    #: The reading's own declared figure intent for this page. Kept beside `visual_type`
    #: because the intent is what says *why* the page is shaped that way: `visual_type` is the
    #: application's renderer vocabulary, and deriving layout signals by substring-matching it
    #: threw the declaration away -- a page declared COMPARISON landed on `EVIDENCE_MAP`, whose
    #: only signal is DEFAULT, so the comparison layout was denied to the page that needed it.
    figure_intent: str | None = None
    #: Set when the reading declares this page renders the argument's shape rather than evidence
    #: (ROADMAP / SECTION_QUESTION / PART_RECAP / CONSOLIDATION). Such a page carries no Claims,
    #: so it is the only place the throughline can appear.
    renders_structure: str | None = None
    structure_text: str | None = None
    structure_segments: list[str] = []


class LayoutRunRequest(BaseModel):
    page_ids: list[str] | None = None


class VisualReviewPageSubmission(BaseModel):
    page_id: str
    image_sha256: str
    verdict: Literal["PASS", "REVISE"]
    concerns: list[str] = []


class VisualReviewSubmission(BaseModel):
    preview_sha256: str
    pages: list[VisualReviewPageSubmission]


class LayoutCycleRequest(LayoutRunRequest):
    max_rounds: int = Field(default=2, ge=1, le=3)


class TriageDecision(BaseModel):
    claim_id: str
    bucket: Literal["MUST_INCLUDE", "SHOULD_INCLUDE", "APPENDIX", "EXCLUDED"]
    score: int = Field(ge=0, le=100)
    reason: str
    meaning_preserving_bundle: list[str] = []
    presentation_cost_seconds: int = Field(default=0, ge=0)
    overridden: bool = False


class NarrativePlan(BaseModel):
    id: str = Field(default_factory=lambda: f"nar_{uuid.uuid4().hex[:8]}")
    narrative_spine: str
    provenance: Provenance
    audience_strategy: str = "balanced_source_faithful"
    sections: list[dict]
    generated_at: str


class PipelineRequest(BaseModel):
    document_id: str | None = None


class DocumentPageText(BaseModel):
    page: int = Field(ge=1)
    text: str


class DocumentTextRequest(BaseModel):
    """Page text obtained outside the application, for a source that has no text layer.

    A scanned PDF extracts to nothing, so the reading would come back empty and the run would
    look merely thin rather than broken. The text has to be attached to the *original*
    document: an accepted reading artifact binds the original file's sha256, so OCR-ing to a
    new searchable PDF and uploading that would break the chain of custody.
    """
    document_id: str
    pages: list[DocumentPageText]
    text_provenance: dict[str, Any]
    reviewer: str = Field(min_length=2, max_length=100)
    rationale: str = Field(min_length=10, max_length=1000)


class RelationshipRequest(BaseModel):
    from_claim_id: str
    to_claim_id: str
    relation_type: str
    direction: Literal["FORWARD", "BIDIRECTIONAL", "NONE"] = "FORWARD"
    logic_operator: Literal["NONE", "AND", "OR", "NOT", "EXCEPT"] = "NONE"
    polarity: Literal["POSITIVE", "NEGATIVE", "NEUTRAL", "CONTRAINDICATION"] = "NEUTRAL"
    recommendation_class: str | None = None
    evidence_level: str | None = None
    provenance: Provenance
    risk: Risk = "YELLOW"
    conditions: list[str] = []
    source_refs: list[SourceRef] = []


class ProjectConfigPatch(BaseModel):
    project_type: Literal["medical_congress", "journal_club", "case_discussion", "evidence_brief", "teaching"] | None = None
    project_goal: str | None = Field(default=None, min_length=3, max_length=500)
    presentation_question: str | None = None
    audience: str | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=180)
    language: str | None = Field(default=None, min_length=2, max_length=20)
    output_type: Literal["PPTX", "SEMANTIC_DECK_JSON"] | None = None
    allow_external_sources: bool | None = None
    allow_external_generation: bool | None = None
    generation_data_egress_policy: Literal["DENY", "EDITORIAL_ONLY", "CONTRACT_MINIMIZED"] | None = None
    verification_mode: Literal["SOURCE_FIDELITY", "CROSS_SOURCE_CONSISTENCY", "EXTERNAL_MEDICAL_CHECK"] | None = None
    external_medical_check: bool | None = None
    output_channel: Literal["internal_deck", "client_delivery", "public_xiaohongshu"] | None = None
    synthetic_case: bool | None = None


class ProjectCreateRequest(BaseModel):
    """Minimal creation surface; controlled containers are never client settable.

    Unknown fields (including any Project payload carrying claims, pages,
    verification results, visual contracts, or delivery manifests) are
    rejected with 422 instead of being silently absorbed.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    presentation_question: str = Field(min_length=1, max_length=1000)
    project_type: Literal["medical_congress", "journal_club", "case_discussion", "evidence_brief", "teaching"] = "medical_congress"
    audience: str = Field(default="专科医生", min_length=1, max_length=100)
    duration_minutes: int = Field(default=20, ge=1, le=180)
    language: str = Field(default="zh-CN", min_length=2, max_length=20)
    output_type: Literal["PPTX", "SEMANTIC_DECK_JSON"] = "PPTX"
    verification_mode: Literal["SOURCE_FIDELITY", "CROSS_SOURCE_CONSISTENCY", "EXTERNAL_MEDICAL_CHECK"] = "SOURCE_FIDELITY"
    synthetic_case: bool = False


class ReviewDecisionRequest(BaseModel):
    object_type: Literal["claim", "relationship"]
    object_id: str
    decision: Literal["APPROVE", "REJECT"]
    reviewer: str = Field(min_length=2, max_length=100)
    rationale: str = Field(min_length=5, max_length=1000)


class SyntheticCaseRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    scenario_text: str = Field(min_length=20, max_length=5000)
    explicitly_requested: bool = False
    source_claim_ids: list[str] = []
    purpose: Literal["teaching", "simulation"] = "teaching"


class ReadUnitReviewRequest(BaseModel):
    """A reviewer's decision on one source unit's code-computed classification."""
    page: int = Field(ge=1)
    decision: Literal["CONTENT_BEARING", "MIXED", "NON_CONTENT"]
    reviewer: str = Field(min_length=2, max_length=100)
    rationale: str = Field(min_length=10, max_length=1000)


class ClaimBindingPatch(BaseModel):
    conditions: list[str] | None = None
    numeric_facts: list[NumericFact] | None = None
    reviewer: str = Field(min_length=2, max_length=100)
    rationale: str = Field(min_length=5, max_length=1000)


class TriageOverrideRequest(BaseModel):
    bucket: Literal["MUST_INCLUDE", "SHOULD_INCLUDE", "APPENDIX", "EXCLUDED"]
    reviewer: str = Field(min_length=2, max_length=100)
    rationale: str = Field(min_length=5, max_length=1000)


class ClaimRevisionRequest(BaseModel):
    conditions: list[str] | None = None
    numeric_facts: list[NumericFact] | None = None
    responsible_module: Literal["claim_builder", "human_reviewer"] = "human_reviewer"
    revision_reason: str = Field(min_length=5, max_length=1000)
    verification_issue_ids: list[str] = []
    automated: bool = False


class RetryBudgetRequest(BaseModel):
    module: Literal["claim_builder", "medical_information_architect", "semantic_relationship_engine", "visual_design_agent"]
    max_auto_revision_attempts: int = Field(ge=1, le=20)
    recurrent_issue_threshold: int = Field(default=2, ge=2, le=20)


class HumanOverrideRequest(BaseModel):
    verification_issue_id: str
    verification_result_id: str
    reviewer: str = Field(min_length=2, max_length=100)
    reason: str = Field(min_length=5, max_length=1000)
    override_provenance: Literal["HUMAN_SYNTHESIS", "HUMAN_MEDICAL_REVIEW"] = "HUMAN_MEDICAL_REVIEW"


class IssueRouteRequest(BaseModel):
    responsible_module: Literal["claim_builder", "medical_information_architect", "semantic_relationship_engine", "visual_design_agent", "compliance_agent", "human_reviewer"]
    rationale: str = Field(min_length=5, max_length=1000)


class ExternalSource(BaseModel):
    id: str = Field(default_factory=lambda: f"extsrc_{uuid.uuid4().hex[:8]}")
    source_type: str | None = None
    organization: str | None = None
    date_or_version: str | None = None
    primary_or_secondary: Literal["PRIMARY", "SECONDARY"] | None = None
    official_or_regulatory_status: str | None = None
    jurisdiction: str | None = None
    identifier: str | None = None
    retracted: bool = False
    corrected_or_amended: bool = False
    replaces_source_id: str | None = None


class ExternalFindingRequest(BaseModel):
    source: ExternalSource
    finding_text: str = Field(min_length=5, max_length=5000)
    finding_type: Literal["EVIDENCE", "RECOMMENDATION", "REGULATORY", "SAFETY", "VERSION", "OTHER"] = "OTHER"
    risk: Risk = "YELLOW"
    verified_as_of: str = Field(min_length=8, max_length=80)
    search_scope: str = Field(min_length=5, max_length=1000)
    source_claim_ids: list[str] = []


class SourcePriorityPolicyRequest(BaseModel):
    id: str = Field(default_factory=lambda: f"spp_{uuid.uuid4().hex[:8]}")
    jurisdiction: str | None = None
    ordered_source_kinds: list[Literal["REGULATORY", "OFFICIAL_GUIDELINE", "PRIMARY_STUDY", "SYSTEMATIC_REVIEW", "REVIEW", "OTHER"]] = []
    rationale: str = Field(min_length=5, max_length=1000)


class ClaimSupersessionRequest(BaseModel):
    superseded_claim_id: str
    superseding_claim_id: str
    explicit_source_supersession: bool = False
    rationale: str = Field(min_length=5, max_length=1000)


class PageOrderRequest(BaseModel):
    page_ids: list[str] = Field(min_length=1)
    editor: str = Field(min_length=2, max_length=100)
    rationale: str = Field(min_length=5, max_length=1000)


class MedicalVisualAssetRequest(BaseModel):
    id: str = Field(default_factory=lambda: f"asset_{uuid.uuid4().hex[:8]}")
    page_id: str | None = None
    semantic_role: Literal["decorative_reference", "medical_content", "anatomical_reference", "data_visualization"] = "decorative_reference"
    visual_type: str = Field(default="medical_illustration", min_length=2, max_length=100)
    origin: Literal["SOURCE_FIGURE", "ADAPTED_FROM_SOURCE", "AI_GENERATED_MEDICAL_VISUAL", "MEDICAL_REFERENCE_ASSET", "REDRAWN_FROM_EVIDENCE", "USER_PROVIDED"]
    transformation_type: Literal["EXACT_REUSE", "STYLE_ONLY", "LAYOUT_REDESIGN", "SEMANTIC_SIMPLIFICATION", "SEMANTIC_SYNTHESIS", "AI_GENERATED"] = "STYLE_ONLY"
    semantic_object_ids: list[str] = []
    semantic_relationship_ids: list[str] = []
    medical_semantic_source_refs: list[str] = []
    visual_asset_source_refs: list[str] = []
    node_provenance_coverage: float = Field(default=1.0, ge=0, le=1)
    relationship_provenance_coverage: float = Field(default=1.0, ge=0, le=1)
    risk_level: Risk = "YELLOW"
    semantic_fidelity_status: Literal["PASS", "FAIL", "NEEDS_HUMAN_REVIEW", "NOT_RUN"] = "NOT_RUN"
    embedded_text_claim_ids: list[str] = []
    embedded_relationship_ids: list[str] = []
    ai_generation_allowed: bool = False
    medical_verified: bool = False
    copyright_status: Literal["LICENSED", "PUBLIC_DOMAIN", "USER_OWNED", "UNKNOWN", "REQUIRES_LICENSE_RESOLUTION"] = "UNKNOWN"
    license_reference: str | None = None


class VisualBindingRequest(BaseModel):
    id: str = Field(default_factory=lambda: f"vb_{uuid.uuid4().hex[:8]}")
    page_id: str
    binding_type: Literal["legend_to_series", "axis_to_metric", "axis_to_unit", "category_to_population", "category_to_timepoint", "annotation_to_comparison", "color_to_semantic", "label_to_numeric", "group_to_meaning", "connector_to_relationship", "symbol_to_medical_meaning", "hierarchy_to_priority"]
    from_object_id: str = Field(min_length=1, max_length=160)
    to_object_id: str = Field(min_length=1, max_length=160)
    semantic_value: str = Field(min_length=1, max_length=1000)
    source_refs: list[str] = []
    locked: bool = True
    axis_baseline_policy: Literal["ZERO_REQUIRED", "DATA_RANGE_ALLOWED", "NOT_APPLICABLE"] = "NOT_APPLICABLE"


class RenderedVisualBinding(BaseModel):
    """Renderer-observed semantic encoding, compared exactly to the frozen binding."""
    binding_id: str
    binding_type: str
    from_object_id: str
    to_object_id: str
    semantic_value: str


class RenderedAxisScale(BaseModel):
    """Observed axis extent. This prevents a renderer from silently clipping a series."""
    axis_object_id: str
    data_min: float
    data_max: float
    axis_min: float
    axis_max: float
    scale: Literal["LINEAR", "LOG"] = "LINEAR"


class GenerationExecutionRequest(BaseModel):
    """A renderer callback payload; this records execution, it never grants capability."""
    page_id: str
    visual_generation_contract_id: str
    component: str = Field(min_length=2, max_length=240)
    strategy: Literal["DETERMINISTIC_CHART", "DETERMINISTIC_DIAGRAM", "EXACT_CONTENT_COMPOSITOR", "VERIFIED_MEDICAL_ASSET_RENDERER", "PROMPT_DRIVEN_IMAGE", "HYBRID_COMPOSITION", "FULL_IMAGE", "CONTROLLED_COMPOSITION"]
    engine_id: str
    engine_version: str
    operation: Literal["GENERATE", "RENDER", "COMPOSE", "IMPORT_ASSET", "EDIT"]
    output_asset_id: str = Field(min_length=2, max_length=200)
    output_asset_version: str = Field(min_length=1, max_length=100)
    deterministic_spec_ref: str | None = None
    prompt_version: str | None = None
    prompt_hash: str | None = None
    safe_prompt_reference: str | None = None
    validator_result_ids: list[str] = []
    external_egress_used: bool = False


class GenerationCapabilityChangeRequest(BaseModel):
    """A material Engine/Version change only invalidates routes; it cannot qualify one."""
    engine_id: str = Field(min_length=2, max_length=160)
    from_version: str = Field(min_length=1, max_length=100)
    to_version: str = Field(min_length=1, max_length=100)
    possible_impacts: list[Literal["exact_text", "data_geometry", "scale_axis", "topology", "asset_integrity", "privacy", "verifier_compatibility", "prompt_compiler"]] = Field(min_length=1)
    reported_by: str = Field(min_length=2, max_length=100)
    rationale: str = Field(min_length=5, max_length=1000)


class ContextContractRequest(BaseModel):
    id: str = Field(default_factory=lambda: f"ctx_{uuid.uuid4().hex[:8]}")
    from_page_id: str
    to_page_id: str
    scope_type: Literal["page", "page_range", "section"] = "page"
    scope_ids: list[str] = []
    population: str | None = None
    subgroup: str | None = None
    outcome: str | None = None
    timeframe: str | None = None
    intervention: str | None = None
    comparator: str | None = None
    inheritance_allowed: bool = False
    reset_triggers: list[str] = []
    override_log: list[str] = []
    transition_type: Literal["PRESENTATION_DEPENDENCY", "CLINICAL_IMPLICATION", "CONTEXT_RESET", "EXPLICIT_OVERRIDE"]
    rationale: str = Field(min_length=5, max_length=1000)
    relationship_ids: list[str] = []
    source_refs: list[str] = []
    locked: bool = True


class GeneratedVisualVerificationRequest(BaseModel):
    page_id: str
    visual_generation_contract_id: str
    rendered_mandatory_object_ids: list[str] = []
    rendered_exact_text: list[str] = []
    rendered_data_binding_ids: list[str] = []
    rendered_relationship_ids: list[str] = []
    rendered_medical_asset_ids: list[str] = []
    rendered_visual_bindings: list[RenderedVisualBinding] = []
    rendered_axis_scales: list[RenderedAxisScale] = []
    source_visible: bool = False
    visual_semantic_fidelity: Literal["PASS", "FAIL", "NEEDS_HUMAN_REVIEW"] = "NEEDS_HUMAN_REVIEW"
    prohibited_transformations_observed: list[str] = []
    generation_provenance: dict[str, str] = {}


class Project(BaseModel):
    id: str = Field(default_factory=lambda: f"prj_{uuid.uuid4().hex[:8]}")
    title: str
    presentation_question: str
    project_type: Literal["medical_congress", "journal_club", "case_discussion", "evidence_brief", "teaching"] = "medical_congress"
    project_goal: str = "Explain source-faithful medical evidence for the declared audience."
    audience: str = "专科医生"
    duration_minutes: int = Field(default=20, ge=1, le=180)
    language: str = "zh-CN"
    output_type: Literal["PPTX", "SEMANTIC_DECK_JSON"] = "PPTX"
    allow_external_sources: bool = False
    allow_external_generation: bool = False
    generation_data_egress_policy: Literal["DENY", "EDITORIAL_ONLY", "CONTRACT_MINIMIZED"] = "DENY"
    #: Sending a patient-facing source document off the machine is a separate
    #: decision from sending a design brief, so it takes its own opt-in and ladder.
    #: There is no "partial" rung: the reading rule requires the full extracted text,
    #: so a half-egress policy would only exist to be misapplied.
    allow_source_text_egress: bool = False
    source_text_egress_policy: Literal["DENY", "FULL_TEXT"] = "DENY"
    #: The accepted reading artifact this project was designed from, and its digest.
    #: Attached, never regenerated: the reading happened elsewhere and is an input.
    reading_structure: dict | None = None
    reading_structure_sha256: str | None = None
    full_summary: dict | None = None
    full_summary_sha256: str | None = None
    verification_mode: Literal["SOURCE_FIDELITY", "CROSS_SOURCE_CONSISTENCY", "EXTERNAL_MEDICAL_CHECK"] = "SOURCE_FIDELITY"
    external_medical_check: bool = False
    output_channel: Literal["internal_deck", "client_delivery", "public_xiaohongshu"] = "internal_deck"
    synthetic_case: bool = False
    documents: list[dict] = []
    claims: list[Claim] = []
    relationships: list[Relationship] = []
    pages: list[PageSpec] = []
    triage_decisions: list[TriageDecision] = []
    narrative_plans: list[NarrativePlan] = []
    verification_results: list[dict] = []
    compliance_issues: list[dict] = []
    visual_plans: list[dict] = []
    visual_contracts: list[dict] = []
    visual_prompts: list[dict] = []
    layout_ir: dict | None = None
    layout_visual_reviews: list[dict] = []
    medical_visual_assets: list[dict] = []
    visual_bindings: list[dict] = []
    context_contracts: list[dict] = []
    generated_visual_verifications: list[dict] = []
    generation_execution_provenances: list[dict] = []
    generation_capability_changes: list[dict] = []
    revision_snapshots: list[dict] = []
    object_dependencies: list[dict] = []
    verification_issues: list[dict] = []
    reverification_runs: list[dict] = []
    retry_budgets: list[dict] = []
    approved_object_refs: list[dict] = []
    policy_decisions: list[dict] = []
    human_overrides: list[dict] = []
    model_runs: list[dict] = []
    synthetic_cases: list[dict] = []
    external_sources: list[dict] = []
    external_findings: list[dict] = []
    source_priority_policies: list[dict] = []
    claim_supersessions: list[dict] = []
    delivery_manifests: list[dict] = []
    violation_records: list[dict] = []
    #: Reviewer decisions on a code-computed source-unit classification. The classifier is a
    #: versioned rule and will sometimes be wrong; an override is recorded, not silent, and
    #: never rewrites what an earlier run was judged against.
    read_unit_reviews: list[dict] = []
    workflow_state: Literal["CREATED", "UPLOADED", "EXTRACTED", "NEEDS_USER_INPUT", "TRIAGED", "ARCHITECTED", "VERIFIED", "COMPLIANCE_REVIEW", "APPROVED", "BLOCKED"] = "CREATED"
    audit_log: list[dict] = []
    # Tamper-evident companion to audit_log. audit_log stays the human-readable
    # view; audit_chain carries the cryptographic links. See tools/provenance.py.
    audit_chain: list[dict] = []
    audit_head: str = ""
    chain_provenance: dict = {}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def audit(project: Project, action: str, detail: str) -> None:
    """Record an action on both the readable log and the tamper-evident chain."""
    at = now()
    project.audit_log.append({"at": at, "action": action, "detail": detail})
    PROV.append(project.audit_chain, at, action, {"detail": detail})
    project.audit_head = PROV.head_hash(project.audit_chain)
    project.chain_provenance = {
        **project.chain_provenance,
        "domain": PROV.DOMAIN,
        "version": PROV.CHAIN_VERSION,
        "head_hash": project.audit_head,
        "length": len(project.audit_chain),
    }


def ensure_chain(project: Project) -> dict:
    """Make the project's chain usable, without ever repairing a broken one.

    Three cases:
      * chain present and valid  -> keep it, record verification
      * chain absent but a legacy audit_log exists -> build one and mark the
        migration, because entries recorded before migration carry no
        cryptographic standing and must not be presented as if they did
      * chain present but INVALID -> record BROKEN and leave it untouched;
        silently rebuilding would destroy the only evidence of tampering
    """
    if project.audit_chain:
        result = PROV.verify_chain(project.audit_chain)
        project.chain_provenance = {
            **project.chain_provenance,
            "domain": PROV.DOMAIN,
            "version": PROV.CHAIN_VERSION,
            "status": "OK" if result["ok"] else "BROKEN",
            "head_hash": result["head_hash"],
            "length": result["count"],
            "verification": result,
        }
        project.audit_head = result["head_hash"]
        return result

    if project.audit_log:
        project.audit_chain = PROV.build_chain(project.audit_log)
        project.audit_head = PROV.head_hash(project.audit_chain)
        result = PROV.verify_chain(project.audit_chain)
        project.chain_provenance = {
            "domain": PROV.DOMAIN,
            "version": PROV.CHAIN_VERSION,
            "status": "MIGRATED",
            "migrated_at": now(),
            "head_hash": project.audit_head,
            "length": len(project.audit_chain),
            "migration_note": (
                "Chain established at migration time. Earlier audit_log entries "
                "carry no cryptographic standing: this chain fixes the state from "
                "migration onward, it does not attest the past."
            ),
            "verification": result,
        }
        return result

    project.audit_head = PROV.GENESIS
    project.chain_provenance = {
        "domain": PROV.DOMAIN,
        "version": PROV.CHAIN_VERSION,
        "status": "OK",
        "head_hash": PROV.GENESIS,
        "length": 0,
    }
    return PROV.verify_chain([])


def anchor_identity_note() -> str:
    """State plainly what a local signing key does and does not establish."""
    return (
        "The signing key is generated locally and stored beside the data. It "
        "proves that an anchor was not altered after signing, and lets a holder "
        "of the public key attribute it to this installation. It does NOT "
        "establish a third-party legal identity: that requires publishing the "
        "public key through a channel outside this system."
    )


def current_anchor_state(project: Project) -> dict:
    """Latest anchor for this project plus its consistency with the live chain."""
    anchors = ANCH.load_anchors(ANCHOR_STORE)
    latest = ANCH.latest_anchor_for(anchors, project.id)
    state = {
        "anchor_file": str(ANCHOR_STORE),
        "anchor_count": len(anchors),
        "file_state": ANCH.verify_anchor_file(anchors) if anchors else None,
        "latest": None,
        "consistency": ANCH.verify_against_chain(anchors, project.id, project.audit_chain),
        "signature": None,
        "identity_note": anchor_identity_note(),
    }
    if latest is None:
        state["note"] = ("No anchor has been published for this project yet, so tail "
                         "truncation is still undetectable.")
        return state
    state["latest"] = {
        "seq": latest.get("seq"), "at": latest.get("at"),
        "chain_length": latest.get("chain_length"),
        "chain_head": latest.get("chain_head"),
        "signed": bool(latest.get("signatures")),
        "signers": [s.get("signer") for s in (latest.get("signatures") or [])],
    }
    if latest.get("signatures") and ANCHOR_PUBKEY.exists():
        state["signature"] = ANCH.verify_signature(latest, ANCHOR_PUBKEY)
    return state


def create_anchor(project: Project, note: str = "") -> dict:
    """Publish a chain head to the append-only anchor store, signed if possible."""
    anchors = ANCH.load_anchors(ANCHOR_STORE)
    if anchors:
        file_state = ANCH.verify_anchor_file(anchors)
        if not file_state["ok"]:
            raise HTTPException(
                409,
                f"Refusing to anchor: the anchor file is already {file_state['code']} "
                f"at index {file_state['first_bad_index']}. Extending it would bury "
                f"the evidence.",
            )
    if not project.audit_chain:
        raise HTTPException(409, "Nothing to anchor: this project's audit chain is empty.")

    signature_note = ""
    key_available = ANCH._cryptography() is not None
    if key_available:
        if not ANCHOR_KEY.exists():
            ANCH.generate_keypair(ANCHOR_KEY, ANCHOR_PUBKEY)
            signature_note = "signing key generated on first anchor"
    else:
        signature_note = "cryptography library unavailable: anchor recorded unsigned"

    # Record the anchoring in the chain FIRST, then anchor the resulting head.
    # Anchoring before auditing would leave the anchor permanently one entry
    # behind, and an attacker could remove exactly that one trailing entry
    # undetected -- a one-entry truncation window.
    audit(project, "PROVENANCE_ANCHOR_REQUESTED", f"anchoring request note={note!r}")

    record = ANCH.make_anchor(
        prev_anchor_hash=ANCH.last_anchor_hash(anchors),
        seq=len(anchors),
        at=now(),
        project_id=project.id,
        chain_length=len(project.audit_chain),
        chain_head=PROV.head_hash(project.audit_chain),
        note=note,
    )
    if key_available:
        ANCH.sign_anchor(record, ANCHOR_KEY, signer="local-self-generated")
    ANCH.append_anchor(ANCHOR_STORE, record)
    return {
        "project_id": project.id,
        "anchor_hash": record["anchor_hash"],
        "chain_length": record["chain_length"],
        "chain_head": record["chain_head"],
        "signed": bool(record["signatures"]),
        "signature_note": signature_note,
        "verify_command": (f"python tools/anchor.py verify {ANCHOR_STORE} "
                           f"<exported projects.json> --pubkey {ANCHOR_PUBKEY}"),
    }


def provenance_report(project: Project) -> dict:
    """Third-party-checkable provenance statement for one project."""
    verification = PROV.verify_chain(project.audit_chain)
    return {
        "project_id": project.id,
        "chain": verification,
        "provenance": project.chain_provenance,
        "anchor": current_anchor_state(project),
        "audit_log_entries": len(project.audit_log),
        "verifier": {
            "chain": "python tools/provenance.py verify-chain <exported project json>",
            "anchor": ("python tools/anchor.py verify <anchors.jsonl> "
                       "<exported project json> [--pubkey <pub.pem>]"),
            "dependencies": "tools/provenance.py is stdlib only; signatures need 'cryptography'",
        },
        "claim_boundary": (
            "The chain detects edits, reordering, relabelling and mid-chain "
            "deletion. Tail truncation is detected only against a published "
            "anchor; without an anchor it remains undetectable. Neither "
            "mechanism attests that the recorded content is medically correct."
        ),
        "verified_at": now(),
    }


def invalidate_verification(project: Project, reason: str) -> int:
    """Keep historical results but prevent their reuse after semantic changes."""
    invalidated = 0
    for result in project.verification_results:
        if not result.get("stale", False):
            result["stale"] = True
            result["stale_reason"] = reason
            result["stale_at"] = now()
            invalidated += 1
    return invalidated


def record_violation(project: Project, *, rule_id: str, severity: str, message: str, action: str, object_id: str | None = None) -> dict:
    record = {"violation_id": f"vio_{uuid.uuid4().hex[:10]}", "at": now(), "rule_id": rule_id, "severity": severity, "message": message, "action": action, "object_id": object_id, "status": "OPEN"}
    project.violation_records.append(record)
    return record


def authorize_agent_write(project: Project, agent_name: str, resource: str, *, object_id: str | None = None) -> dict:
    capability = AGENT_CAPABILITY_MATRIX.get(agent_name)
    allowed = bool(capability and resource in capability["write"])
    decision = {
        "policy_decision_id": f"pol_{uuid.uuid4().hex[:8]}",
        "project_id": project.id,
        "object_type": resource,
        "object_id": object_id,
        "agent_name": agent_name,
        "decision": "PASS" if allowed else "BLOCK",
        "violated_rule_ids": [] if allowed else ["CAP-01"],
        "required_review_ids": [],
        "evaluated_at": now(),
        "policy_engine_version": "mvp-1",
    }
    if not allowed:
        message = f"Agent {agent_name} is not authorized to write {resource}."
        decision["message"] = message
        record_violation(project, rule_id="CAP-01", severity="CRITICAL", message=message, action="BLOCK", object_id=object_id)
    project.policy_decisions.append(decision)
    audit(project, "AGENT_CAPABILITY_DECISION", json.dumps(decision, ensure_ascii=False))
    return decision


def enforce_agent_write(project: Project, agent_name: str, resource: str, *, object_id: str | None = None) -> None:
    decision = authorize_agent_write(project, agent_name, resource, object_id=object_id)
    if decision["decision"] == "BLOCK":
        raise HTTPException(403, decision["message"])


def seed_project() -> Project:
    doc = "demo_gold_2026"
    refs = lambda page, quote: [SourceRef(document_id=doc, page=page, quote=quote)]
    claims = [
        Claim(id="c_case", normalized_claim="病例发现应针对具有相关风险或症状的人群，并以验证性检查确认。", source_quote="DEMO SOURCE — upload the source PDF to verify the exact wording.", provenance="SUMMARY", risk="YELLOW", source_refs=refs(3, "待上传原文核验"), conditions=["不能暗示全民普筛", "高危定义必须保留原文范围"], triage="MUST_INCLUDE"),
        Claim(id="c_noscreen", normalized_claim="无症状低风险人群不应被简化为普遍筛查对象。", source_quote="DEMO SOURCE — upload the source PDF to verify the exact wording.", provenance="SUMMARY", risk="RED", source_refs=refs(3, "待上传原文核验"), conditions=["无症状", "低风险"], triage="MUST_INCLUDE"),
        Claim(id="c_old", normalized_claim="急性加重风险更新需要同时呈现旧阈值、证据和新版分层。", provenance="SUMMARY", risk="RED", source_refs=refs(5, "待上传原文核验"), conditions=["不得把关联升级为绝对因果"], triage="MUST_INCLUDE"),
        Claim(id="c_new", normalized_claim="单次中重度急性加重进入高风险分层是需要逐字核验的高风险结论。", provenance="SUMMARY", risk="RED", source_refs=refs(5, "待上传原文核验"), conditions=["时间窗", "事件定义", "分组名称"], triage="MUST_INCLUDE", review_status="NEEDS_HUMAN_REVIEW"),
        Claim(id="c_activity", normalized_claim="疾病活动度、低疾病活动度与疾病控制是不同概念，不能在图中混用。", source_quote="DEMO SOURCE — upload the source PDF to verify the exact wording.", provenance="SOURCE", risk="YELLOW", source_refs=refs(6, "待上传原文核验"), conditions=["疾病控制仍需症状及患者影响条件"], triage="MUST_INCLUDE"),
        Claim(id="c_biologic", normalized_claim="生物制剂证据应按患者表型、干预、结局与证据分别展示。", provenance="SYNTHESIS", risk="RED", source_refs=refs(8, "待上传原文核验"), conditions=["不得补写原文没有的效应量或推荐等级"], triage="MUST_INCLUDE", review_status="NEEDS_HUMAN_REVIEW"),
        Claim(id="c_cycle", normalized_claim="长期管理应使用基线、初始治疗、再评估、调整与随访的闭环叙事。", provenance="SYNTHESIS", risk="YELLOW", source_refs=refs(9, "待上传原文核验"), conditions=["不能为了闭环补出药物分支"], triage="MUST_INCLUDE"),
        Claim(id="c_rsv", normalized_claim="疫苗适用人群、年龄阈值和保护期是 RED 数字/限定条件，必须从上传原文绑定。", provenance="SUMMARY", risk="RED", source_refs=refs(4, "待上传原文核验"), conditions=["年龄", "高危人群", "疫苗类型"], numeric_facts=[NumericFact(value="SOURCE REQUIRED", status="UNBOUND")], triage="APPENDIX", review_status="BLOCKED"),
    ]
    relationships = [
        Relationship(id="r_case", from_claim_id="c_case", to_claim_id="c_noscreen", relation_type="EXCLUSION", provenance="SUMMARY", risk="RED", conditions=["无症状低风险人群"], source_refs=refs(3, "待上传原文核验"), status="NEEDS_HUMAN_REVIEW"),
        Relationship(id="r_risk", from_claim_id="c_old", to_claim_id="c_new", relation_type="EVIDENCE_TO_CLASSIFICATION", provenance="SYNTHESIS", risk="RED", conditions=["不表示自动因果"], source_refs=refs(5, "待上传原文核验"), status="NEEDS_HUMAN_REVIEW"),
        Relationship(id="r_activity", from_claim_id="c_activity", to_claim_id="c_cycle", relation_type="MANAGEMENT_CONTEXT", provenance="SYNTHESIS", risk="YELLOW", conditions=["演示组织，不等于临床因果"], source_refs=refs(6, "待上传原文核验")),
    ]
    pages = [
        PageSpec(id="p1", title="GOLD 2026：管理范式升级地图（演示）", primary_message="把更新组织为可核验的管理变化，而非模板式摘要。", visual_type="MANAGEMENT_PARADIGM_MAP", claim_ids=["c_case", "c_new", "c_activity", "c_cycle"], provenance="SYNTHESIS", goal="建立汇报叙事主线"),
        PageSpec(id="p2", title="病例发现：Clinical Decision Map", primary_message="高危/症状人群经工具与肺功能验证；排除条件不可省略。", visual_type="CLINICAL_DECISION_MAP", claim_ids=["c_case", "c_noscreen"], relationship_ids=["r_case"], provenance="SUMMARY", goal="保护病例发现的适用边界"),
        PageSpec(id="p3", title="急性加重：Risk Stratification Evidence Map", primary_message="旧标准、新证据和新版分层须逐段绑定来源。", visual_type="EVIDENCE_MAP", claim_ids=["c_old", "c_new"], relationship_ids=["r_risk"], provenance="SYNTHESIS", goal="展示证据链而不升级因果"),
        PageSpec(id="p4", title="Disease Activity Framework", primary_message="活动度、低活动度与控制存在层级与条件差异。", visual_type="CONCEPTUAL_FRAMEWORK", claim_ids=["c_activity"], provenance="SOURCE", goal="澄清概念边界"),
        PageSpec(id="p5", title="Biologic Evidence Map", primary_message="按表型、干预、结局和证据分层；缺失数字不予补全。", visual_type="EVIDENCE_MATRIX", claim_ids=["c_biologic"], provenance="SYNTHESIS", goal="避免把研究结果升级为推荐"),
        PageSpec(id="p6", title="COPD Management Cycle", primary_message="用可追溯闭环组织管理，但不凭空补全临床路径。", visual_type="MANAGEMENT_CYCLE", claim_ids=["c_cycle"], relationship_ids=["r_activity"], provenance="SYNTHESIS", goal="把随访放入管理循环"),
    ]
    project = Project(title="GOLD 2026 可审计演示 — Demo", presentation_question="GOLD 2026 的哪些更新改变了 COPD 管理，并且其证据边界是什么？", claims=claims, relationships=relationships, pages=pages)
    audit(project, "PROJECT_CREATED", "Loaded the source-faithful GOLD benchmark demo; all source spans require uploaded-PDF verification.")
    return project


def load_projects() -> list[Project]:
    if not STORE.exists():
        return []
    projects = [Project.model_validate(item) for item in json.loads(STORE.read_text(encoding="utf-8"))]
    for project in projects:
        ensure_chain(project)
    return projects


def save_projects(projects: list[Project]) -> None:
    for project in projects:
        project.audit_head = PROV.head_hash(project.audit_chain)
    STORE.write_text(json.dumps([p.model_dump(mode="json") for p in projects], ensure_ascii=False, indent=2), encoding="utf-8")


def get_project(project_id: str) -> tuple[list[Project], Project]:
    projects = load_projects()
    for project in projects:
        if project.id == project_id:
            return projects, project
    raise HTTPException(404, "Project not found")


def rule_registry() -> dict:
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    required = {"id", "constraint_type", "enforced_by", "validated_by", "violation_action", "severity", "rule"}
    incomplete = [{"id": item.get("id", "UNKNOWN"), "missing": sorted(required - set(item))} for item in rules if required - set(item)]
    duplicate_ids = sorted({item["id"] for item in rules if sum(other["id"] == item["id"] for other in rules) > 1})
    return {"status": "PASS" if not incomplete and not duplicate_ids else "BLOCK", "rules": rules, "incomplete": incomplete, "duplicate_ids": duplicate_ids}


def validate(project: Project) -> dict:
    issues: list[dict] = []
    if not project.presentation_question.strip():
        issues.append({"severity": "BLOCK", "rule": "AR-04", "message": "Presentation Question is required before triage."})
    for case in project.synthetic_cases:
        if case.get("disclaimer") != "AI生成模拟病例｜非原文病例｜仅用于教学演示":
            issues.append({"severity": "BLOCK", "rule": "CT-02", "message": "Synthetic case disclaimer is missing or altered."})
        if any(claim_id not in {claim.id for claim in project.claims} for claim_id in case.get("source_claim_ids", [])):
            issues.append({"severity": "BLOCK", "rule": "CT-02", "message": "Synthetic case contains an unknown evidence claim reference."})
    index = {claim.id: claim for claim in project.claims}
    for claim in project.claims:
        if claim.provenance == "EXTERNAL_VERIFICATION":
            issues.append({"severity": "BLOCK", "rule": "CT-01", "object": claim.id, "message": "EXTERNAL_VERIFICATION content belongs in the isolated External Finding pool, not the user Claim Table."})
        if claim.provenance == "SOURCE" and (not claim.source_refs or not claim.source_quote):
            issues.append({"severity": "BLOCK", "rule": "CT-01", "object": claim.id, "message": "SOURCE claim lacks a quote or page-level SourceRef."})
        for fact in claim.numeric_facts:
            missing = numeric_binding_missing(fact, claim)
            origin_issues = numeric_origin_issues(fact, claim)
            if claim.risk == "RED" and (fact.status != "BOUND" or missing):
                detail = ", ".join(missing) if missing else fact.status
                issues.append({"severity": "BLOCK", "rule": "DB-01", "object": claim.id, "message": f"RED numeric fact is not fully bound to its semantic context: {detail}."})
            if origin_issues:
                issues.append({"severity": "BLOCK", "rule": "DB-01", "object": claim.id, "message": "Numeric provenance invalid: " + "; ".join(origin_issues) + "."})
        if claim.conflict_group_id and claim.triage in ("MUST_INCLUDE", "SHOULD_INCLUDE"):
            issues.append({"severity": "HUMAN_REVIEW", "rule": "CF-01", "object": claim.id, "message": f"Claim belongs to unresolved conflict group {claim.conflict_group_id}."})
    for page in project.pages:
        if page.revision_status == "STALE":
            issues.append({"severity": "BLOCK", "rule": "AR-04", "object": page.id, "message": "PageSpec is stale after an immutable upstream Claim revision and must be rebuilt."})
        if not page.primary_message or not page.claim_ids:
            issues.append({"severity": "BLOCK", "rule": "AR-04", "object": page.id, "message": "A PageSpec needs one primary message and supporting claims."})
        if len(page.claim_ids) > 4:
            issues.append({"severity": "BLOCK", "rule": "AR-04", "object": page.id, "message": "A PageSpec exceeds the controlled renderer capacity of four Claims; split the narrative page instead of omitting evidence."})
        for claim_id in page.claim_ids:
            if claim_id not in index:
                issues.append({"severity": "BLOCK", "rule": "SB-03", "object": page.id, "message": f"Page references unknown claim {claim_id}."})
        relationship_ids = {relationship.id for relationship in project.relationships}
        for relationship_id in page.relationship_ids:
            if relationship_id not in relationship_ids:
                issues.append({"severity": "BLOCK", "rule": "CR-13", "object": page.id, "message": f"Page connector references unknown clinical relationship {relationship_id}."})
    for relation in project.relationships:
        if relation.provenance == "SOURCE" and not relation.source_refs:
            issues.append({"severity": "BLOCK", "rule": "CR-13", "object": relation.id, "message": "SOURCE Clinical Relationship lacks its own explicit SourceRef."})
        if relation.logic_operator != "NONE" and not relation.conditions:
            issues.append({"severity": "BLOCK", "rule": "CR-13", "object": relation.id, "message": "Logical clinical relationship requires explicit conditions."})
        if relation.direction == "NONE" and relation.relation_type.upper() in {"CAUSAL", "CLINICAL_PATHWAY", "EVIDENCE_TO_CLASSIFICATION", "ESCALATES_TO"}:
            issues.append({"severity": "BLOCK", "rule": "CR-13", "object": relation.id, "message": "Directed clinical relationship cannot have direction=NONE."})
        if relation.risk == "RED" and (relation.status != "SUPPORTED" or relation.review_status != "APPROVED"):
            issues.append({"severity": "HUMAN_REVIEW", "rule": "CR-13", "object": relation.id, "message": "RED relationship requires human medical review before approval."})
    for visual_issue in medical_visual_asset_issues(project) + visual_binding_issues(project) + contextual_contract_issues(project):
        issues.append({
            "severity": visual_issue["severity"],
            "rule": "CP-01" if visual_issue["type"] == "COPYRIGHT" else "VG-09",
            "object": visual_issue["object"],
            "message": visual_issue["message"],
        })
    if project.output_channel == "public_xiaohongshu":
        unresolved = [c for c in project.claims if c.risk == "RED" and c.review_status != "APPROVED"]
        if unresolved:
            issues.append({"severity": "BLOCK", "rule": "CP-01", "message": "Public delivery is blocked until all RED claims are reviewed and approved."})
    blocked = any(issue["severity"] == "BLOCK" for issue in issues)
    return {"status": "BLOCK" if blocked else ("HUMAN_REVIEW_REQUIRED" if issues else "PASS"), "issues": issues, "checked_at": now()}


# --- Frozen-module MVP services -------------------------------------------------
# These functions are intentionally deterministic and side-effect free except where
# the endpoint persists their result. They are the executable guardrail layer, not
# a substitute for medical judgment or a free-form model prompt.

RISK_WORDS = ("剂量", "阈值", "禁忌", "不推荐", "推荐", "证据等级", "适应证", "风险", "年龄", "随访", "筛查", "排除", "时间")
VISUAL_BY_TERMS = {
    "CLINICAL_DECISION_MAP": ("诊断", "筛查", "路径", "流程", "决策", "检查"),
    "EVIDENCE_MAP": ("证据", "研究", "比较", "风险", "推荐"),
    "EVIDENCE_MATRIX": ("药物", "干预", "结局", "表型", "生物制剂"),
    "MANAGEMENT_CYCLE": ("随访", "再评估", "调整", "管理", "循环"),
    "CONCEPTUAL_FRAMEWORK": ("概念", "机制", "活动度", "控制"),
}
AUDIENCE_FOCUS_TERMS = {
    "specialist": ("证据", "研究", "比较", "风险", "结局", "统计", "生物制剂", "局限", "分层"),
    "trainee": ("筛查", "诊断", "检查", "路径", "治疗", "管理", "随访", "调整", "禁忌"),
    "student": ("概念", "定义", "机制", "活动度", "控制", "基础", "原则", "框架"),
}
AUDIENCE_NARRATIVE_ORDER = {
    "specialist": ("EVIDENCE_MAP", "EVIDENCE_MATRIX", "CONCEPTUAL_FRAMEWORK", "CLINICAL_DECISION_MAP", "MANAGEMENT_CYCLE"),
    "trainee": ("CLINICAL_DECISION_MAP", "MANAGEMENT_CYCLE", "EVIDENCE_MAP", "EVIDENCE_MATRIX", "CONCEPTUAL_FRAMEWORK"),
    "student": ("CONCEPTUAL_FRAMEWORK", "CLINICAL_DECISION_MAP", "MANAGEMENT_CYCLE", "EVIDENCE_MAP", "EVIDENCE_MATRIX"),
}
ALLOWED_STATES = {
    # Re-reading is how a reading is corrected -- a missed paragraph, a wrong quote. It changes the
    # Claim Table, so everything derived from it has to be rebuilt; refusing it after triage left the
    # correction path unreachable and pushed operators into editing the answer outside the pipeline.
    "extract": {"UPLOADED", "EXTRACTED", "NEEDS_USER_INPUT", "TRIAGED", "ARCHITECTED",
                "VERIFIED", "COMPLIANCE_REVIEW", "BLOCKED"},
    "triage": {"CREATED", "EXTRACTED", "NEEDS_USER_INPUT", "TRIAGED"},
    # `architect` is the documented remedy for a TITLE_ENTAILMENT finding (the review sheet
    # routes that issue type here: "Revise title or Primary Message"). A remedy that cannot
    # be executed is not a remedy, so rebuilding the page set is allowed from the states a
    # reviewer can actually reach when a title or allocation is rejected.
    "architect": {"TRIAGED", "ARCHITECTED", "BLOCKED", "COMPLIANCE_REVIEW"},
    # `verify` is read-only and idempotent, so re-running it after remediation must be
    # possible from BLOCKED. Otherwise a BLOCK is a dead end: the loop the review sheet
    # describes (issue -> responsible module -> fix -> re-verify) could not be closed
    # without an unrelated human action first. Everything downstream still requires a
    # non-blocking verification, so nothing is weakened by allowing this.
    "verify": {"ARCHITECTED", "VERIFIED", "BLOCKED"},
    "compliance": {"VERIFIED", "COMPLIANCE_REVIEW"},
    "route_visuals": {"COMPLIANCE_REVIEW"},
    # Attaching a reading is how a narrative gets re-grounded, so it cannot be limited to the
    # states before verification: the code already handles a *changed* artifact (pages go
    # stale, verification is invalidated), and refusing it after routing left that handling
    # unreachable.
    "reading_structure": {"UPLOADED", "EXTRACTED", "NEEDS_USER_INPUT", "TRIAGED", "ARCHITECTED",
                          "VERIFIED", "COMPLIANCE_REVIEW", "BLOCKED"},
}
ACTION_RULES = {
    "extract": ["CT-01", "CT-02"],
    "triage": ["TR-05"],
    "architect": ["AR-04"],
    "verify": ["CT-01", "CF-01", "DB-01", "SB-03", "CR-13"],
    "compliance": ["CP-01"],
    "route_visuals": ["VG-07", "VG-09"],
    "reading_structure": ["RS-01"],
}
AGENT_CAPABILITY_MATRIX = {
    "source_extractor": {"write": {"claims"}, "forbidden": {"relationships", "numeric_facts", "pages"}},
    "information_triage": {"write": {"triage_decisions"}, "forbidden": {"claims", "relationships", "numeric_facts", "pages"}},
    "medical_information_architect": {"write": {"narrative_plans", "pages"}, "forbidden": {"claims", "relationships", "numeric_facts"}},
    "semantic_relationship_engine": {"write": {"relationships", "visual_bindings", "context_contracts"}, "forbidden": {"claims"}},
    "visual_design_agent": {"write": {"visual_prompts"}, "forbidden": {"claims", "relationships", "numeric_facts", "visual_bindings"}},
    "medical_verifier": {"write": {"verification_results", "verification_issues", "reverification_runs"}, "forbidden": {"claims", "relationships", "numeric_facts", "pages"}},
    "reading_structure_import": {"write": {"reading_structure"}, "forbidden": {"claims", "relationships", "numeric_facts", "pages", "triage_decisions"}},
    "read_unit_reviewer": {"write": {"read_unit_reviews"}, "forbidden": {"claims", "relationships", "numeric_facts", "pages"}},
}
def load_generation_capability_registry() -> tuple[str, dict[str, dict]]:
    """Load the deployment-owned, version-controlled execution registry.

    API clients cannot add or qualify engines. Deployments may add a vetted
    external library/model entry here only with retained benchmark evidence.
    """
    try:
        payload = json.loads(GENERATION_CAPABILITY_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Cannot load generation capability registry: {error}") from error
    registry_version = payload.get("registry_version")
    engines = payload.get("engines")
    if not isinstance(registry_version, str) or not registry_version or not isinstance(engines, dict):
        raise RuntimeError("Generation capability registry requires registry_version and engines")
    for engine_id, engine in engines.items():
        if not isinstance(engine, dict) or engine.get("engine_id") != engine_id:
            raise RuntimeError(f"Generation capability registry has an invalid engine entry: {engine_id}")
    return registry_version, engines


GENERATION_CAPABILITY_REGISTRY_VERSION, GENERATION_CAPABILITY_REGISTRY = load_generation_capability_registry()


def generation_engine_registry() -> dict[str, Any]:
    """Expose qualification evidence, never provider credentials or prompts."""
    return {"registry_version": GENERATION_CAPABILITY_REGISTRY_VERSION, "engines": copy.deepcopy(GENERATION_CAPABILITY_REGISTRY)}


def effective_generation_capability_registry(project: Project) -> dict[str, dict]:
    """Project-local view where material changes remove stale versions from routing."""
    registry = copy.deepcopy(GENERATION_CAPABILITY_REGISTRY)
    for change in project.generation_capability_changes:
        engine = registry.get(change.get("engine_id"))
        if engine and engine.get("engine_version") == change.get("from_version"):
            engine["qualification_status"] = "STALE"
            engine["available"] = False
            engine["stale_reason"] = change.get("capability_change_id")
    return registry


def capability_gate(engine: dict, requirements: set[str], *, external_egress_allowed: bool) -> dict:
    """Hard qualification precedes quality, cost, and latency optimization."""
    if engine.get("qualification_status") != "QUALIFIED":
        return {"eligible": False, "reason": "ENGINE_NOT_QUALIFIED"}
    qualification_basis = engine.get("qualification_basis")
    if not isinstance(qualification_basis, dict) or not isinstance(qualification_basis.get("benchmark_suite"), str) or not qualification_basis["benchmark_suite"] or not isinstance(qualification_basis.get("tested_at"), str) or not qualification_basis["tested_at"] or not isinstance(qualification_basis.get("evidence_refs"), list) or not qualification_basis["evidence_refs"]:
        return {"eligible": False, "reason": "MISSING_QUALIFICATION_EVIDENCE"}
    if not engine.get("available", False):
        return {"eligible": False, "reason": "ENGINE_UNAVAILABLE"}
    if engine.get("external", False) and not external_egress_allowed:
        return {"eligible": False, "reason": "DATA_EGRESS_DENIED"}
    capabilities = engine.get("capabilities", {})
    missing = sorted(requirement for requirement in requirements if not capabilities.get(requirement, False))
    if missing:
        return {"eligible": False, "reason": "MISSING_CAPABILITY", "missing": missing}
    if not capabilities.get("post_generation_verification", False):
        return {"eligible": False, "reason": "NO_POST_GENERATION_VERIFIER"}
    return {"eligible": True, "reason": "QUALIFIED"}


def select_qualified_component_engine(registry: dict[str, dict], requirements: set[str], *, external_egress_allowed: bool) -> dict:
    """Select an implementation for one component without changing its semantics."""
    rejected: list[dict] = []
    for engine_id, engine in registry.items():
        gate = capability_gate(engine, requirements, external_egress_allowed=external_egress_allowed)
        if gate["eligible"]:
            return {"status": "ROUTABLE", "engine_id": engine_id, "engine": engine, "rejected_candidates": rejected}
        rejected.append({"engine_id": engine_id, **gate})
    return {"status": "UNROUTABLE", "engine_id": None, "engine": None, "rejected_candidates": rejected}


def record_generation_execution(project: Project, request: GenerationExecutionRequest) -> dict:
    """Record a completed component execution against the pre-approved route.

    The adapter/service that calls a graphics library or an external provider is
    intentionally outside this function. This control-plane function validates
    its declared Engine/Version and egress boundary before retaining provenance.
    """
    contract = next((item for item in project.visual_contracts if item.get("visual_generation_contract_id") == request.visual_generation_contract_id and item.get("page_id") == request.page_id), None)
    if contract is None:
        raise HTTPException(422, "Generation execution must reference the exact Page VisualGenerationContract")
    plan = next((item for item in project.visual_plans if item.get("page_id") == request.page_id), None)
    if plan is None:
        raise HTTPException(422, "Generation execution requires a routed PageGenerationPlan")
    route_components = plan.get("effective_generation_route", {}).get("component_routes", [])
    expected = next((item for item in route_components if item.get("component") == request.component), None)
    if expected is None:
        raise HTTPException(422, f"Component {request.component} is not approved by the effective generation route")
    if expected.get("engine_id") != request.engine_id or expected.get("engine_version") != request.engine_version:
        raise HTTPException(422, "Execution Engine/Version differs from the qualified route; reroute and requalify before use")
    engine = effective_generation_capability_registry(project).get(request.engine_id)
    if engine is None:
        raise HTTPException(422, "Execution engine is absent from the qualified capability registry")
    external_allowed = project.allow_external_generation and project.generation_data_egress_policy != "DENY"
    gate = capability_gate(engine, set(expected.get("requirements", [])), external_egress_allowed=external_allowed)
    if not gate["eligible"]:
        raise HTTPException(422, f"Execution engine is no longer eligible: {gate['reason']}")
    if bool(engine.get("external")) != request.external_egress_used:
        raise HTTPException(422, "Execution egress declaration must match the registered Engine boundary")
    if request.external_egress_used:
        component_type = request.component.split(":", 1)[0]
        if project.generation_data_egress_policy == "EDITORIAL_ONLY" and component_type != "editorial_background":
            raise HTTPException(422, "EDITORIAL_ONLY egress cannot process semantic or medical-asset components")
        if not external_allowed:
            raise HTTPException(422, "External generation is not explicitly enabled for this project")
    record = {
        "generation_execution_provenance_id": f"gep_{uuid.uuid4().hex[:8]}",
        "generation_component_id": f"{request.page_id}:{request.component}",
        "page_id": request.page_id,
        "strategy": request.strategy,
        "engine_id": request.engine_id,
        "engine_version": request.engine_version,
        "execution_kind": engine.get("execution_kind", "UNSPECIFIED"),
        "input_contract_ref": f"{request.visual_generation_contract_id}:v0.1",
        "deterministic_spec_ref": request.deterministic_spec_ref,
        "prompt_version": request.prompt_version,
        "prompt_hash": request.prompt_hash,
        "safe_prompt_reference": request.safe_prompt_reference,
        "operation": request.operation,
        "output_asset_id": request.output_asset_id,
        "output_asset_version": request.output_asset_version,
        "external_egress_used": request.external_egress_used,
        "validator_result_ids": request.validator_result_ids,
        "generated_at": now(),
    }
    project.generation_execution_provenances.append(record)
    return record


def invalidate_generation_capability(project: Project, request: GenerationCapabilityChangeRequest) -> dict:
    """Invalidate only affected generation artifacts after an Engine/Version change."""
    registered = GENERATION_CAPABILITY_REGISTRY.get(request.engine_id)
    if registered is None or registered.get("engine_version") != request.from_version:
        raise HTTPException(422, "Capability change must reference a currently registered Engine/Version; it cannot create a qualification record")
    record = {
        "capability_change_id": f"gcc_{uuid.uuid4().hex[:8]}",
        **request.model_dump(),
        "qualification_invalidated": True,
        "required_actions": ["rerun_capability_validation", "rerun_affected_route_validation", "rerun_post_generation_verification"],
        "recorded_at": now(),
    }
    project.generation_capability_changes.append(record)
    affected_page_ids: set[str] = set()
    for plan in project.visual_plans:
        components = plan.get("effective_generation_route", {}).get("component_routes", [])
        if any(item.get("engine_id") == request.engine_id and item.get("engine_version") == request.from_version for item in components):
            plan["allowed"] = False
            plan["route_status"] = "STALE_CAPABILITY"
            plan["capability_change_id"] = record["capability_change_id"]
            affected_page_ids.add(plan["page_id"])
    for contract in project.visual_contracts:
        if contract.get("page_id") in affected_page_ids:
            contract["stale"] = True
            contract["stale_reason"] = record["capability_change_id"]
    for result in project.generated_visual_verifications:
        if result.get("page_id") in affected_page_ids:
            result["stale"] = True
            result["stale_reason"] = record["capability_change_id"]
    for execution in project.generation_execution_provenances:
        if execution.get("engine_id") == request.engine_id and execution.get("engine_version") == request.from_version:
            execution["stale"] = True
            execution["stale_reason"] = record["capability_change_id"]
    if affected_page_ids:
        project.workflow_state = "COMPLIANCE_REVIEW"
    return {"record": record, "affected_page_ids": sorted(affected_page_ids)}


def missing_generation_execution_components(project: Project) -> list[str]:
    """Every approved route component needs a current, contract-bound execution record."""
    plans = {plan.get("page_id"): plan for plan in project.visual_plans}
    records = {
        (record.get("page_id"), record.get("generation_component_id"), record.get("input_contract_ref"), record.get("engine_id"), record.get("engine_version"))
        for record in project.generation_execution_provenances
        if not record.get("stale")
    }
    missing: list[str] = []
    for contract in project.visual_contracts:
        page_id = contract.get("page_id")
        plan = plans.get(page_id)
        if plan is None:
            missing.append(f"{page_id}:missing_routed_plan")
            continue
        contract_ref = f"{contract['visual_generation_contract_id']}:v0.1"
        for component in plan.get("effective_generation_route", {}).get("component_routes", []):
            component_id = component.get("component")
            key = (page_id, f"{page_id}:{component_id}", contract_ref, component.get("engine_id"), component.get("engine_version"))
            if key not in records:
                missing.append(f"{page_id}:{component_id}")
    return missing


def select_generation_route(*, visual_type: str, has_exact_text: bool, has_exact_geometry: bool, has_topology_lock: bool, editorial_base_allowed: bool, asset_ai_generation_allowed: bool = True, external_egress_allowed: bool = False, capabilities: dict[str, dict] | None = None) -> dict:
    """Choose an effective component route without changing the visual type."""
    registry = capabilities or GENERATION_CAPABILITY_REGISTRY
    requirements: set[str] = set()
    if has_exact_text:
        requirements.add("exact_text_authority")
    if has_exact_geometry:
        requirements.add("exact_data_geometry")
    if has_topology_lock:
        requirements.add("semantic_topology_lock")
    component_routes: list[dict] = []
    rejected: list[dict] = []
    qualified = []
    for engine_id, engine in registry.items():
        gate = capability_gate(engine, requirements, external_egress_allowed=external_egress_allowed)
        if gate["eligible"]:
            qualified.append((engine_id, engine))
        else:
            rejected.append({"engine_id": engine_id, **gate})
    if requirements and not qualified:
        return {"status": "UNROUTABLE", "visual_type": visual_type, "preferred_generation_strategy": "CONTROLLED_COMPOSITION", "effective_generation_route": {"component_routes": [], "composition_strategy": None, "route_deviation_reason": "No qualified engine can preserve required locked semantics."}, "rejected_candidates": rejected}
    if requirements:
        engine_id, engine = qualified[0]
        component_routes.append({"component": "protected_semantic_layer", "engine_id": engine_id, "engine_version": engine["engine_version"], "requirements": sorted(requirements), "generation_mode": "DETERMINISTIC"})
        if editorial_base_allowed:
            component_routes.append({"component": "editorial_background", "engine_id": engine_id, "engine_version": engine["engine_version"], "requirements": [], "generation_mode": "EDITORIAL_ONLY"})
        return {"status": "ROUTABLE", "visual_type": visual_type, "preferred_generation_strategy": "HYBRID_COMPOSITION" if editorial_base_allowed else "CONTROLLED_COMPOSITION", "effective_generation_route": {"component_routes": component_routes, "composition_strategy": "HYBRID_COMPOSITION" if editorial_base_allowed else "CONTROLLED_COMPOSITION", "route_deviation_reason": None}, "rejected_candidates": rejected}
    if not asset_ai_generation_allowed:
        return {"status": "UNROUTABLE", "visual_type": visual_type, "preferred_generation_strategy": "FULL_IMAGE", "effective_generation_route": {"component_routes": [], "composition_strategy": None, "route_deviation_reason": "BLOCKED_BY_ASSET_POLICY"}, "rejected_candidates": rejected}
    eligible = [(engine_id, engine) for engine_id, engine in registry.items() if capability_gate(engine, set(), external_egress_allowed=external_egress_allowed)["eligible"]]
    if not eligible:
        return {"status": "UNROUTABLE", "visual_type": visual_type, "preferred_generation_strategy": "FULL_IMAGE", "effective_generation_route": {"component_routes": [], "composition_strategy": None, "route_deviation_reason": "No qualified verified engine is available."}, "rejected_candidates": rejected}
    engine_id, engine = eligible[0]
    return {"status": "ROUTABLE", "visual_type": visual_type, "preferred_generation_strategy": "FULL_IMAGE", "effective_generation_route": {"component_routes": [{"component": "whole_page_editorial", "engine_id": engine_id, "engine_version": engine["engine_version"], "requirements": [], "generation_mode": "FULL_IMAGE"}], "composition_strategy": "FULL_IMAGE", "route_deviation_reason": None}, "rejected_candidates": rejected}


def audience_profile(audience: str) -> str:
    lowered = audience.lower()
    if any(token in audience for token in ("专家", "专科", "科研", "研究")) or any(token in lowered for token in ("specialist", "expert", "research")):
        return "specialist"
    if any(token in audience for token in ("规培", "住院", "基层", "临床")) or any(token in lowered for token in ("trainee", "resident", "primary")):
        return "trainee"
    if any(token in audience for token in ("学生", "本科", "教学")) or any(token in lowered for token in ("student", "learner")):
        return "student"
    return "trainee"


def audience_fit(claim: Claim, profile: str) -> int:
    return sum(term in claim.normalized_claim for term in AUDIENCE_FOCUS_TERMS[profile])


def infer_risk(text: str) -> Risk:
    return "RED" if any(word in text for word in RISK_WORDS) or re.search(r"\d", text) else "YELLOW"


def numeric_binding_missing(fact: NumericFact, claim: Claim) -> list[str]:
    required = ("value", "unit", "metric", "population", "timeframe", "outcome", "intervention", "comparator", "statistic_type")
    missing = [field for field in required if not getattr(fact, field)]
    if not claim.source_refs:
        missing.append("source_ref")
    return missing


def numeric_origin_issues(fact: NumericFact, claim: Claim) -> list[str]:
    """Validate numeric provenance independently of the numeric string itself."""
    issues: list[str] = []
    missing_tokens = {"NR", "NA", "N/A", "NOT REPORTED", "NOT MEASURED", "UNKNOWN", "缺失", "未报告"}
    source_upper = (claim.source_quote or "").upper()
    value_upper = fact.value.strip().upper()
    if fact.value_origin == "SOURCE_EXACT":
        if fact.derivation_kind or fact.derivation_formula or fact.input_fact_ids:
            issues.append("SOURCE_EXACT may not carry derivation metadata")
        if value_upper == "0" and any(token in source_upper for token in missing_tokens):
            issues.append("source reports missing/NR but value was represented as 0")
    elif fact.value_origin == "DERIVED_CALCULATION":
        if claim.provenance != "SYNTHESIS":
            issues.append("derived calculation requires SYNTHESIS provenance")
        if not fact.derivation_kind or not fact.derivation_formula or len(fact.input_fact_ids) < 2:
            issues.append("derived calculation requires whitelisted kind, formula, and two input Fact IDs")
    elif fact.value_origin == "ESTIMATED_FROM_FIGURE":
        if fact.status == "BOUND":
            issues.append("figure estimate cannot be marked as an exact BOUND value")
    elif fact.value_origin == "NOT_REPORTED":
        if value_upper not in missing_tokens:
            issues.append("NOT_REPORTED must preserve an explicit missing token, never an imputed numeric value")
        if fact.status == "BOUND":
            issues.append("NOT_REPORTED cannot be BOUND")
    if fact.comparability_status == "NOT_COMPARABLE" and fact.value_role in {"ABSOLUTE_DIFFERENCE", "RELATIVE_CHANGE"}:
        issues.append("comparison-derived value cannot use NOT_COMPARABLE inputs")
    return issues


def _source_numeric_tokens(text: str) -> list[float]:
    """All numeric magnitudes present in source text, for exact-value matching.

    A hyphen or dash *between two digits* is a range separator, not a sign:
    "1006-5725", "12-16 周" and "447-458" must yield 1006/5725, 12/16 and 447/458. The
    previous form read the second half as a negative number, so a correct positive
    NumericFact was reported as "does not match any numeric value in the source quote".
    """
    cleaned = re.sub(r"(?<=\d)\s*[-–—－~～]\s*(?=\d)", " ", text or "")
    return [float(m.replace(",", "")) for m in re.findall(r"(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?", cleaned)]


def numeric_source_fidelity_issues(fact: NumericFact, claim: Claim) -> list[str]:
    """P0-1: a SOURCE_EXACT numeric fact's value must actually appear in the source.

    Field completeness and provenance-type rules are not enough; an attacker
    can fill a RED fact with a fabricated magnitude that the source never
    stated. Parseable numeric magnitudes are compared against every numeric
    token in the claim's source quote. Values that cannot be parsed (e.g.
    comparator-prefixed literals such as '>0.05', or missing tokens) fall
    back to the existing origin rules instead of being guessed.
    """
    if fact.value_origin != "SOURCE_EXACT":
        return []
    source = claim.source_quote or ""
    if not source:
        return ["SOURCE_EXACT numeric fact requires a claim with a source_quote"]
    magnitude = re.search(r"[-+]?\d+(?:\.\d+)?", fact.value.replace(",", "").replace("％", "%"))
    if magnitude is None:
        # Non-numeric literal (e.g. NR / N/A) — governed by origin rules, not guessed here.
        return []
    parsed = float(magnitude.group(0))
    if any(abs(token - parsed) < 1e-9 for token in _source_numeric_tokens(source)):
        return []
    return [f"NumericFact value {fact.value!r} does not match any numeric value in the source quote"]


def source_binding_issues(project: Project, claim: Claim) -> list[str]:
    """P0-2: SOURCE Claim source refs must resolve to an uploaded document page.

    Document id, page number, source_ref quote and claim source_quote must
    all be bound to actually uploaded, extracted PDF text. Forged document
    ids, nonexistent pages and fabricated quotes are blocked instead of being
    treated as provenance.
    """
    issues: list[str] = []
    if claim.provenance != "SOURCE":
        return issues
    if not claim.source_refs:
        return ["SOURCE Claim has no source refs"]
    for ref in claim.source_refs:
        document = next((doc for doc in project.documents if doc.get("id") == ref.document_id), None)
        if document is None:
            issues.append(f"source_ref document_id {ref.document_id!r} does not match any uploaded document")
            continue
        page_text = next(
            (chunk.get("text", "") for chunk in document.get("chunks", []) if chunk.get("page") == ref.page),
            None,
        )
        if page_text is None:
            issues.append(f"source_ref page {ref.page} does not exist in document {ref.document_id}")
            continue
        if ref.quote and not quote_occurs_in(ref.quote, page_text):
            issues.append(f"source_ref quote is not contained in document {ref.document_id} page {ref.page}")
        if claim.source_quote and not quote_occurs_in(claim.source_quote, page_text):
            issues.append(f"claim source_quote is not contained in document {ref.document_id} page {ref.page}")
    return issues


def relationship_source_entailment_issues(project: Project, relationship: Relationship) -> list[str]:
    """P0-3: SOURCE relationships need relation-level provenance evidence.

    A non-empty source_refs list is insufficient; the referenced document
    page must exist and actually contain the relationship's claim terms
    (entailment evidence), and the ref quote must be present in the page.
    """
    if relationship.provenance != "SOURCE":
        return []
    if not relationship.source_refs:
        return ["SOURCE relationship requires at least one explicit source ref"]
    issues: list[str] = []
    involved_claims = [
        claim for claim in project.claims
        if claim.id in (relationship.from_claim_id, relationship.to_claim_id)
    ]
    probe_terms = set()
    for claim in involved_claims:
        probe_terms |= terms(claim.normalized_claim)
    for ref in relationship.source_refs:
        document = next((doc for doc in project.documents if doc.get("id") == ref.document_id), None)
        if document is None:
            issues.append(f"relationship source_ref document_id {ref.document_id!r} does not match any uploaded document")
            continue
        page_text = next(
            (chunk.get("text", "") for chunk in document.get("chunks", []) if chunk.get("page") == ref.page),
            None,
        )
        if page_text is None:
            issues.append(f"relationship source_ref page {ref.page} does not exist in document {ref.document_id}")
            continue
        if ref.quote and not quote_occurs_in(ref.quote, page_text):
            issues.append("relationship source_ref quote is not contained in the referenced page")
        elif probe_terms and not any(term in page_text for term in probe_terms):
            issues.append("referenced page contains none of the relationship's claim terms (no entailment evidence)")
    return issues


def policy_gate(project: Project, action: str) -> dict:
    allowed = ALLOWED_STATES[action]
    evaluated_rule_ids = ACTION_RULES[action]
    if project.workflow_state not in allowed:
        return {"status": "BLOCK", "action": action, "evaluated_rule_ids": evaluated_rule_ids, "message": f"{action} is not eligible from workflow state {project.workflow_state}", "next_state_eligible": False}
    if action == "route_visuals":
        verification = project.verification_results[-1] if project.verification_results else None
        compliance_result = compliance(project)
        if verification is None or verification["status"] != "PASS":
            return {"status": "BLOCK", "action": action, "evaluated_rule_ids": evaluated_rule_ids, "message": "Visual routing requires a PASS source-fidelity verification.", "next_state_eligible": False}
        if compliance_result["status"] != "PASS":
            return {"status": "BLOCK", "action": action, "evaluated_rule_ids": evaluated_rule_ids, "message": "Visual routing requires a PASS compliance decision.", "next_state_eligible": False}
    return {"status": "PASS", "action": action, "evaluated_rule_ids": evaluated_rule_ids, "message": "Workflow state and required gates permit this action.", "next_state_eligible": True}


def enforce_policy_gate(projects: list[Project], project: Project, action: str) -> None:
    decision = policy_gate(project, action)
    audit(project, "POLICY_GATE_DECISION", json.dumps(decision, ensure_ascii=False))
    if decision["status"] == "BLOCK":
        for rule_id in decision["evaluated_rule_ids"]:
            record_violation(project, rule_id=rule_id, severity="BLOCK", message=decision["message"], action=action)
    save_projects(projects)
    if decision["status"] != "PASS":
        raise HTTPException(409, decision["message"])


def immutable_snapshot_digest(deck: dict[str, Any], documents: list[dict], *,
                              reading_sha256: str | None = None,
                              extra: dict[str, Any] | None = None) -> str:
    """Hash semantic content, excluding delivery time and mutable audit history.

    The accepted reading artifact is part of the identity when one was attached: a deck
    must not be able to change which narrative it was built from and keep its name.

    `extra` carries the other parts of the delivery identity that must also change the name
    -- the selected model layout and the editorial asset hashes. It exists because the PPTX
    export used to hash a hand-built identity dict *in place of* the deck, which has no
    `presentation_question` and raised KeyError before any export could complete.
    """
    payload = {
        "project_id": deck["project_id"],
        "presentation_question": deck["presentation_question"],
        "export_type": deck["export_type"],
        "pages": deck["pages"],
        "source_documents": [{"id": item["id"], "sha256": item.get("sha256"), "page_count": item.get("page_count")} for item in documents],
    }
    if reading_sha256 is not None:
        payload["reading_structure_sha256"] = reading_sha256
    if extra:
        payload["delivery_identity"] = extra
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def delivery_manifest(project: Project, deck: dict[str, Any], pptx_sha256: str,
                      output_verification: dict, *, extra: dict[str, Any] | None = None,
                      quality_report: dict[str, Any] | None = None) -> dict:
    """Create the immutable delivery record required by the delivery gate.

    `extra` must be the same delivery identity the caller hashed for `snapshot_id`. It was
    previously omitted here, so the manifest stored an id computed from a *smaller* payload
    than the export used; the duplicate guard then never matched and every export appended
    another identical manifest.
    """
    semantic_hash = immutable_snapshot_digest(deck, project.documents,
                                              reading_sha256=project.reading_structure_sha256,
                                              extra=extra)
    return {
        "snapshot_id": f"del_{semantic_hash[:16]}",
        "semantic_deck_sha256": semantic_hash,
        "pptx_sha256": pptx_sha256,
        "created_at": now(),
        "source_document_hashes": [{"id": item["id"], "sha256": item.get("sha256")} for item in project.documents],
        "page_ids": [page["page_id"] for page in deck["pages"]],
        "verification_status": project.verification_results[-1]["status"] if project.verification_results else "MISSING",
        "compliance_status": compliance(project)["status"],
        "post_generation_verification": output_verification,
        "quality_report_sha256": quality_report.get("report_sha256") if quality_report else None,
        "quality_report_file": f"del_{semantic_hash[:16]}.quality.json" if quality_report else None,
    }


def extract_numeric_facts(text: str) -> list[NumericFact]:
    """Harvest candidate numbers, excluding digits that are part of an identifier.

    `FEV1`, `GOLD2026` and `IL-6` contain digits that are not measurements. Harvesting
    them created NumericFacts that could never be grounded, because the exact-value check
    in `numeric_source_fidelity_issues` deliberately ignores digits preceded by a letter
    or underscore. Both sides now agree on what counts as a number, so a RED Claim is no
    longer blocked by a fact that was never a fact.
    """
    facts: list[NumericFact] = []
    for match in re.finditer(r"(?<![A-Za-z0-9_])(?:≥|≤|>|<)?\s*\d+(?:\.\d+)?\s*(?:%|mg|μg|g|mL|岁|天|周|月|年|次|例|例/年|mmHg|mL/min)?", text, re.I):
        value = match.group(0).strip()
        if not value:
            continue
        unit = re.search(r"%|mg|μg|g|mL|岁|天|周|月|年|次|例|mmHg|mL/min", value, re.I)
        facts.append(NumericFact(value=value, unit=unit.group(0) if unit else None, metric="SOURCE_REQUIRED", population="SOURCE_REQUIRED", timeframe="SOURCE_REQUIRED", status="PARTIALLY_BOUND"))
    return facts


def canonicalize_claims(claims: list[Claim]) -> dict:
    """Group same-fact candidates but never merge incompatible numeric variants."""
    groups: dict[str, list[Claim]] = {}
    for claim in claims:
        skeleton = re.sub(r"(?:≥|≤|>|<)?\s*\d+(?:\.\d+)?", "#", claim.normalized_claim.lower())
        skeleton = re.sub(r"\s+", "", skeleton)
        groups.setdefault(skeleton, []).append(claim)
    canonical_groups = 0
    conflicts = 0
    for skeleton, members in groups.items():
        canonical_id = f"can_{hashlib.sha256(skeleton.encode()).hexdigest()[:10]}"
        for member in members:
            member.canonical_claim_id = canonical_id
        canonical_groups += 1
        numeric_signatures = {tuple(fact.value for fact in member.numeric_facts) for member in members}
        documents = {ref.document_id for member in members for ref in member.source_refs}
        if len(members) > 1 and len(documents) > 1 and len(numeric_signatures) > 1:
            conflict_id = f"conf_{hashlib.sha256((skeleton + str(sorted(numeric_signatures))).encode()).hexdigest()[:10]}"
            for member in members:
                member.conflict_group_id = conflict_id
                member.ambiguity = True
                member.review_status = "NEEDS_HUMAN_REVIEW"
            conflicts += 1
    return {"canonical_groups": canonical_groups, "conflict_groups": conflicts}


def qualify_external_source(source: ExternalSource) -> dict:
    """Qualification is a metadata gate, not a medical-truth ranking."""
    required = ("source_type", "organization", "date_or_version", "primary_or_secondary", "official_or_regulatory_status", "jurisdiction", "identifier")
    missing = [field for field in required if not getattr(source, field)]
    if source.retracted:
        return {"status": "REJECTED", "missing": missing, "reason": "Retracted external sources cannot support high-risk medical content."}
    if missing:
        return {"status": "LEAD_ONLY", "missing": missing, "reason": "External source qualification is incomplete."}
    return {"status": "QUALIFIED", "missing": [], "reason": "Metadata qualification complete; content still requires scoped human review."}


def source_version_relation(left: dict, right: dict) -> str:
    """Publication date alone never establishes supersession."""
    if left.get("explicitly_supersedes") == right.get("id"):
        return "SUPERSEDES"
    if right.get("explicitly_supersedes") == left.get("id"):
        return "SUPERSEDED_BY"
    return "UNKNOWN"


def classify_source_kind(source: dict) -> str:
    status = (source.get("official_or_regulatory_status") or "").upper()
    source_type = (source.get("source_type") or "").upper()
    if "REGULATORY" in status or "LABEL" in source_type:
        return "REGULATORY"
    if "GUIDELINE" in status or "GUIDELINE" in source_type:
        return "OFFICIAL_GUIDELINE"
    if "SYSTEMATIC" in source_type or "META" in source_type:
        return "SYSTEMATIC_REVIEW"
    if source.get("primary_or_secondary") == "PRIMARY":
        return "PRIMARY_STUDY"
    if "REVIEW" in source_type:
        return "REVIEW"
    return "OTHER"


def apply_source_priority_policy(left: dict, right: dict, policy: dict | None) -> dict:
    """Prioritize review attention only; never turn source priority into medical truth."""
    if policy is None:
        return {"status": "NO_POLICY", "priority_source_id": None, "reason": "No source-priority policy configured; preserve both sources for review."}
    jurisdiction = policy.get("jurisdiction")
    if jurisdiction and (left.get("jurisdiction") != jurisdiction or right.get("jurisdiction") != jurisdiction):
        return {"status": "NOT_APPLICABLE", "priority_source_id": None, "reason": "Policy jurisdiction does not cover both sources; latest or priority cannot decide applicability."}
    order = policy.get("ordered_source_kinds", [])
    left_kind, right_kind = classify_source_kind(left), classify_source_kind(right)
    left_rank = order.index(left_kind) if left_kind in order else len(order)
    right_rank = order.index(right_kind) if right_kind in order else len(order)
    if left_rank == right_rank:
        return {"status": "TIE", "priority_source_id": None, "reason": "Source priority policy does not distinguish these sources; preserve conflict for human review.", "source_kinds": {left.get("id"): left_kind, right.get("id"): right_kind}}
    priority = left if left_rank < right_rank else right
    return {"status": "PRIORITY_FOR_REVIEW", "priority_source_id": priority.get("id"), "reason": "Priority orders review attention only; the non-priority source is not marked medically false.", "source_kinds": {left.get("id"): left_kind, right.get("id"): right_kind}, "non_truth_ranking": True}


def register_claim_supersession(project: Project, request: ClaimSupersessionRequest) -> dict:
    if not request.explicit_source_supersession:
        raise HTTPException(422, "Claim supersession requires an explicit source version relation; publication date alone is insufficient")
    superseded = next((claim for claim in project.claims if claim.id == request.superseded_claim_id), None)
    superseding = next((claim for claim in project.claims if claim.id == request.superseding_claim_id), None)
    if superseded is None or superseding is None:
        raise HTTPException(404, "Both superseded and superseding Claims must exist")
    if superseded.id == superseding.id:
        raise HTTPException(422, "A Claim cannot supersede itself")
    superseded.superseded_by_claim_id = superseding.id
    record = {
        "claim_supersession_id": f"cs_{uuid.uuid4().hex[:8]}",
        "superseded_claim_id": superseded.id,
        "superseding_claim_id": superseding.id,
        "relation": "SUPERSEDED_BY",
        "rationale": request.rationale,
        "created_at": now(),
    }
    project.claim_supersessions.append(record)
    invalidated = invalidate_verification(project, f"Claim-level supersession registered for {superseded.id}; affected content needs fresh verification.")
    return {"record": record, "invalidated_verification_results": invalidated}


def classify_cross_source_conflict(left: dict, right: dict) -> dict:
    """Compare context before classifying substantive disagreement."""
    context_fields = ("population", "condition", "timeframe", "jurisdiction")
    context_differences = [field for field in context_fields if left.get(field) and right.get(field) and left.get(field) != right.get(field)]
    if context_differences:
        return {"status": "CONTEXT_DIFFERENCE", "conflict_type": None, "context_differences": context_differences, "message": "Context differs; do not label a direct medical contradiction."}
    left_recommendation = str(left.get("recommendation", "")).lower()
    right_recommendation = str(right.get("recommendation", "")).lower()
    if left_recommendation and right_recommendation and left_recommendation != right_recommendation:
        return {"status": "CONFLICT", "conflict_type": "RECOMMENDATION_DIFFERENCE", "context_differences": [], "message": "Comparable contexts express different recommendations."}
    if left.get("value") is not None and right.get("value") is not None and str(left["value"]) != str(right["value"]):
        return {"status": "CONFLICT", "conflict_type": "DIRECT_CONTRADICTION", "context_differences": [], "message": "Comparable contexts contain incompatible values."}
    return {"status": "NO_CONFLICT", "conflict_type": None, "context_differences": [], "message": "No typed substantive conflict detected."}


def create_external_finding(project: Project, request: ExternalFindingRequest) -> dict:
    if not project.external_medical_check or project.verification_mode != "EXTERNAL_MEDICAL_CHECK":
        raise HTTPException(409, "External medical verification is disabled; SOURCE_FIDELITY mode may not silently import external knowledge")
    qualification = qualify_external_source(request.source)
    if request.risk == "RED" and qualification["status"] != "QUALIFIED":
        raise HTTPException(422, "Only a qualified non-retracted external source may support a RED external finding")
    known_claims = {claim.id for claim in project.claims}
    unknown = set(request.source_claim_ids) - known_claims
    if unknown:
        raise HTTPException(422, f"External finding references unknown user-source Claim(s): {sorted(unknown)}")
    source = request.source.model_dump()
    source["qualification"] = qualification
    if not any(item["id"] == source["id"] for item in project.external_sources):
        project.external_sources.append(source)
    finding = {
        "id": f"extfind_{uuid.uuid4().hex[:8]}",
        "provenance": "EXTERNAL_VERIFICATION",
        "source_pool": "EXTERNAL_VERIFICATION_POOL",
        "source_id": source["id"],
        "qualification_status": qualification["status"],
        "finding_text": request.finding_text,
        "finding_type": request.finding_type,
        "risk": request.risk,
        "verified_as_of": request.verified_as_of,
        "search_scope": request.search_scope,
        "source_claim_ids": request.source_claim_ids,
        "created_at": now(),
        "auto_update_user_source": False,
        "delivery_eligible": qualification["status"] == "QUALIFIED" and not request.source.retracted,
    }
    project.external_findings.append(finding)
    return finding


def reorder_pages(project: Project, request: PageOrderRequest) -> dict:
    current_ids = [page.id for page in project.pages]
    if len(request.page_ids) != len(current_ids) or set(request.page_ids) != set(current_ids):
        raise HTTPException(422, "Page order must contain every existing PageSpec exactly once; reordering cannot add or remove pages")
    index = {page.id: page for page in project.pages}
    before = current_ids
    project.pages = [index[page_id] for page_id in request.page_ids]
    for plan in project.narrative_plans:
        for section in plan.sections:
            section["page_ids"] = [page_id for page_id in request.page_ids if page_id in section.get("page_ids", [])]
    invalidated = invalidate_verification(project, "Page order changed; contextual implication requires a fresh verification pass.")
    return {"before_page_ids": before, "after_page_ids": request.page_ids, "editor": request.editor, "rationale": request.rationale, "invalidated_verification_results": invalidated}


def register_medical_visual_asset(project: Project, request: MedicalVisualAssetRequest) -> dict:
    if request.page_id and request.page_id not in {page.id for page in project.pages}:
        raise HTTPException(422, "Medical visual asset references an unknown PageSpec")
    asset = request.model_dump()
    project.medical_visual_assets.append(asset)
    invalidated = invalidate_verification(project, f"Medical visual asset {asset['id']} was registered.")
    return {"asset": asset, "invalidated_verification_results": invalidated}


def register_visual_binding(project: Project, request: VisualBindingRequest) -> dict:
    if request.page_id not in {page.id for page in project.pages}:
        raise HTTPException(422, "VisualBinding references an unknown PageSpec")
    binding = request.model_dump()
    project.visual_bindings.append(binding)
    invalidated = invalidate_verification(project, f"Visual semantic binding {binding['id']} was registered.")
    return {"binding": binding, "invalidated_verification_results": invalidated}


def register_context_contract(project: Project, request: ContextContractRequest) -> dict:
    page_ids = {page.id for page in project.pages}
    if request.from_page_id not in page_ids or request.to_page_id not in page_ids:
        raise HTTPException(422, "Context Contract must reference existing PageSpecs")
    relationship_ids = {relationship.id for relationship in project.relationships}
    if set(request.relationship_ids) - relationship_ids:
        raise HTTPException(422, "Context Contract references an unknown clinical relationship")
    contract = request.model_dump()
    if not contract["scope_ids"]:
        contract["scope_ids"] = [request.from_page_id, request.to_page_id]
    project.context_contracts.append(contract)
    invalidated = invalidate_verification(project, f"Context Contract {contract['id']} was registered.")
    return {"contract": contract, "invalidated_verification_results": invalidated}


def contextual_contract_issues(project: Project) -> list[dict]:
    issues: list[dict] = []
    contracts = {(item.get("from_page_id"), item.get("to_page_id")): item for item in project.context_contracts}
    relationship_ids = {relationship.id for relationship in project.relationships}
    claim_index = {claim.id: claim for claim in project.claims}
    implication_terms = ("因此", "所以", "基于上述", "下一步", "相比之下", "优先", "随后", "应当", "推荐")
    comparison_terms = ("优于", "更好", "更低", "更高", "较低", "较高")
    for current, following in zip(project.pages, project.pages[1:]):
        target_text = following.title + following.primary_message
        contract = contracts.get((current.id, following.id))
        source_claims = [claim_index[claim_id] for claim_id in current.claim_ids if claim_id in claim_index]
        target_claims = [claim_index[claim_id] for claim_id in following.claim_ids if claim_id in claim_index]
        red = any(claim.risk == "RED" for claim in source_claims + target_claims)
        severity = "BLOCK" if red else "HUMAN_REVIEW"
        # A page may legitimately carry words such as “因此” / “推荐”, because the source
        # itself may say that and the Claim is shown verbatim. Such wording is not an
        # implied *cross-page* transition. What makes a transition cross-page is the
        # claim's own evidence: a DIRECT/SOURCE Claim's span sits on the page showing it,
        # so nothing is inherited from the previous page. Only SUMMARY/SYNTHESIS Claims --
        # evidence assembled elsewhere -- are "shown here, proven elsewhere".
        #
        # A verbatim copy of the Claim's text is NOT sufficient on its own: a transition
        # that must be declared could otherwise be laundered by rewording the Claim to
        # match the title. Requiring the Claim's wording to match is not an escape hatch
        # either: wording is a Claim's identity, so changing it to dodge this gate would
        # itself require a new immutable Claim revision and a re-run of the verifier.
        def is_cross_page_wording(claim) -> bool:
            conditioned = implication_terms + comparison_terms + tuple(claim.conditions or [])
            return (claim.provenance != "SOURCE"
                    and any(term and term in claim.normalized_claim for term in conditioned))

        cross_page = any(is_cross_page_wording(claim) for claim in target_claims)
        if any(term in target_text for term in implication_terms) and contract is None and cross_page:
            issues.append({"type": "CONTEXT_CONTRACT", "severity": severity, "object": following.id, "message": "Adjacent-page clinical implication requires an explicit Context Contract; presentation order is not a clinical relationship."})
        if contract:
            if not contract.get("locked", False):
                issues.append({"type": "CONTEXT_CONTRACT", "severity": "BLOCK", "object": contract.get("id"), "message": "Context Contract must be locked before rendering."})
            if contract.get("transition_type") == "CLINICAL_IMPLICATION":
                if not contract.get("relationship_ids") or set(contract.get("relationship_ids", [])) - relationship_ids:
                    issues.append({"type": "CONTEXT_CONTRACT", "severity": "BLOCK", "object": contract.get("id"), "message": "Clinical implication Context Contract requires explicit registered Relationship IDs."})
                if not contract.get("source_refs"):
                    issues.append({"type": "CONTEXT_CONTRACT", "severity": severity, "object": contract.get("id"), "message": "Clinical implication Context Contract lacks source provenance."})
            if contract.get("inheritance_allowed") and not any(contract.get(field) for field in ("population", "subgroup", "outcome", "timeframe", "intervention", "comparator")):
                issues.append({"type": "CONTEXT_CONTRACT", "severity": "BLOCK", "object": contract.get("id"), "message": "Context inheritance is enabled but no inheritable semantic scope is declared."})
        non_comparable = any(fact.comparability_status == "NOT_COMPARABLE" for claim in source_claims + target_claims for fact in claim.numeric_facts)
        if non_comparable and any(term in target_text for term in comparison_terms):
            if not contract or contract.get("transition_type") != "CONTEXT_RESET":
                issues.append({"type": "HIDDEN_CROSS_STUDY_COMPARISON", "severity": "BLOCK", "object": following.id, "message": "NOT_COMPARABLE data cannot become an implied cross-study comparison through page sequence."})
    return issues


def visual_binding_issues(project: Project) -> list[dict]:
    issues: list[dict] = []
    pages = {page.id for page in project.pages}
    claim_ids = {claim.id for claim in project.claims}
    relationship_ids = {relationship.id for relationship in project.relationships}
    for binding in project.visual_bindings:
        binding_id = binding.get("id", "UNKNOWN")
        if binding.get("page_id") not in pages:
            issues.append({"type": "VISUAL_BINDING", "severity": "BLOCK", "object": binding_id, "message": "Visual semantic binding points to an unknown PageSpec."})
        if not binding.get("locked", False):
            issues.append({"type": "VISUAL_BINDING", "severity": "BLOCK", "object": binding_id, "message": "Semantic visual encoding must be locked before rendering."})
        if binding.get("binding_type") in {"connector_to_relationship", "symbol_to_medical_meaning", "group_to_meaning", "color_to_semantic", "hierarchy_to_priority"} and not binding.get("source_refs"):
            issues.append({"type": "VISUAL_BINDING", "severity": "BLOCK", "object": binding_id, "message": "Meaning-bearing visual encoding lacks explicit semantic source reference."})
        if binding.get("binding_type") == "connector_to_relationship" and binding.get("to_object_id") not in relationship_ids:
            issues.append({"type": "VISUAL_BINDING", "severity": "BLOCK", "object": binding_id, "message": "Connector binding references an unknown clinical relationship."})
        if binding.get("binding_type") == "label_to_numeric" and binding.get("to_object_id") not in claim_ids:
            issues.append({"type": "VISUAL_BINDING", "severity": "BLOCK", "object": binding_id, "message": "Numeric label binding must target a registered Claim."})
    return issues


def medical_visual_asset_issues(project: Project) -> list[dict]:
    issues: list[dict] = []
    known_pages = {page.id for page in project.pages}
    known_claims = {claim.id for claim in project.claims}
    known_relationships = {relationship.id for relationship in project.relationships}
    for asset in project.medical_visual_assets:
        asset_id = asset.get("id", "UNKNOWN")
        if asset.get("page_id") and asset["page_id"] not in known_pages:
            issues.append({"type": "MEDICAL_VISUAL_ASSET", "severity": "BLOCK", "object": asset_id, "message": "Medical visual asset points to an unknown PageSpec."})
        if asset.get("origin") == "AI_GENERATED_MEDICAL_VISUAL" and not asset.get("ai_generation_allowed", False):
            issues.append({"type": "MEDICAL_VISUAL_ASSET", "severity": "BLOCK", "object": asset_id, "message": "AI-generated medical visual is disallowed by its asset contract."})
        if asset.get("origin") == "AI_GENERATED_MEDICAL_VISUAL" and asset.get("semantic_role") != "decorative_reference" and not asset.get("medical_verified", False):
            issues.append({"type": "MEDICAL_VISUAL_QA", "severity": "BLOCK", "object": asset_id, "message": "AI-generated medical content is unverified and cannot enter the approved visual."})
        is_medical = asset.get("semantic_role") != "decorative_reference"
        if is_medical and not asset.get("medical_semantic_source_refs"):
            issues.append({"type": "MEDICAL_VISUAL_PROVENANCE", "severity": "BLOCK", "object": asset_id, "message": "Medical visual lacks distinct medical semantic provenance."})
        if asset.get("origin") in {"SOURCE_FIGURE", "ADAPTED_FROM_SOURCE", "MEDICAL_REFERENCE_ASSET"} and not asset.get("visual_asset_source_refs"):
            issues.append({"type": "MEDICAL_VISUAL_PROVENANCE", "severity": "BLOCK", "object": asset_id, "message": "Referenced visual asset lacks distinct asset provenance or license source."})
        if asset.get("risk_level") == "RED":
            if asset.get("node_provenance_coverage", 0) < 1 or asset.get("relationship_provenance_coverage", 0) < 1:
                issues.append({"type": "MEDICAL_VISUAL_PROVENANCE", "severity": "BLOCK", "object": asset_id, "message": "RED medical visual requires 100% node and relationship provenance coverage."})
            if asset.get("semantic_fidelity_status") != "PASS":
                issues.append({"type": "MEDICAL_VISUAL_QA", "severity": "BLOCK", "object": asset_id, "message": "RED medical visual requires a PASS semantic-fidelity QA result."})
        unknown_embedded_claims = sorted(set(asset.get("embedded_text_claim_ids", [])) - known_claims)
        unknown_embedded_relationships = sorted(set(asset.get("embedded_relationship_ids", [])) - known_relationships)
        if unknown_embedded_claims or unknown_embedded_relationships:
            issues.append({"type": "MEDICAL_VISUAL_EMBEDDED_CONTENT", "severity": "BLOCK", "object": asset_id, "message": "Embedded visual text or relationship is not bound to a registered semantic object."})
        if project.output_channel in {"client_delivery", "public_xiaohongshu"} and asset.get("copyright_status") in {"UNKNOWN", "REQUIRES_LICENSE_RESOLUTION"}:
            channel = "Public dissemination" if project.output_channel == "public_xiaohongshu" else "Commercial client delivery"
            issues.append({"type": "COPYRIGHT", "severity": "BLOCK", "object": asset_id, "message": f"{channel} requires a resolved visual-asset license."})
    return issues


def _condition_prefix(sentence: str) -> list[str]:
    """Extract only explicit leading scope; never infer clinical conditions."""
    match = re.match(r"^(?:对于|对|在|当|若|如果)([^，,；;。]{2,120})[，,]", sentence.strip())
    return [match.group(1).strip()] if match else []


def atomic_source_candidates(sentence: str) -> list[tuple[str, list[str]]]:
    """Split only unambiguous semicolon-separated source propositions.

    Full source sentence remains the citation span, so a split Claim never loses
    the condition that supplied its medical scope. Ambiguous comma coordination
    deliberately stays intact for human review rather than creating a relation.
    """
    full = sentence.strip()
    parts = [part.strip(" ，,；;") for part in re.split(r"[；;]+", full) if part.strip(" ，,；;")]
    if len(parts) < 2:
        return [(full, _condition_prefix(full))]
    inherited = _condition_prefix(full)
    candidates: list[tuple[str, list[str]]] = []
    for part in parts:
        conditions = _condition_prefix(part) or inherited
        normalized = part
        if inherited and not _condition_prefix(part):
            normalized = f"在{inherited[0]}条件下，{part}"
        candidates.append((normalized, conditions))
    return candidates


def require_complete_source_extraction(document: dict) -> None:
    if not document.get("extractor_version") or document.get("coverage_status") != "COMPLETE":
        raise HTTPException(422, {
            "message": "Source extraction is incomplete or predates coverage tracking; re-import the original file",
            "issues": document.get("coverage_issues") or ["SOURCE_COVERAGE_UNVERIFIED"],
        })


def source_extractor(project: Project, document_id: str) -> list[Claim]:
    document = next((d for d in project.documents if d["id"] == document_id), None)
    if document is None:
        raise HTTPException(404, "Document not found in project")
    candidates: list[Claim] = []
    for chunk in document.get("chunks", []):
        page = chunk["page"]
        # Conservative sentence segmentation avoids inventing content or relations.
        sentences = [s.strip() for s in re.split(r"(?<=[。！？.!?])\s*", chunk.get("text", "")) if s.strip()]
        cursor = 0
        for sentence in sentences:
            quote = sentence
            locator = dict(chunk.get("locator") or {})
            found = chunk.get("text", "").find(sentence, cursor)
            if found >= 0:
                cursor = found + len(sentence)
                if locator.get("kind") == "PDF":
                    base = int(locator.get("start") or 0)
                    locator["start"], locator["end"] = base + found, base + cursor
            for normalized, conditions in atomic_source_candidates(quote):
                if len(candidates) >= 100_000:
                    raise HTTPException(413, "Candidate count exceeds 100000; split the source into smaller files")
                claim = Claim(
                    normalized_claim=normalized,
                    source_quote=quote,
                    provenance="SOURCE",
                    risk=infer_risk(normalized),
                    source_refs=[SourceRef(document_id=document_id, page=page, quote=quote,
                                           locator=locator or None)],
                    conditions=conditions or ["自动提取候选；需确认人群、条件、时间窗和排除条件"],
                    numeric_facts=extract_numeric_facts(normalized),
                    triage="SHOULD_INCLUDE",
                    review_status="NEEDS_HUMAN_REVIEW",
                )
                candidates.append(claim)
    return candidates


def active_claims(project: Project) -> list[Claim]:
    """Claims that are still in scope: every version except the superseded ones.

    Retention and scope are different things. An immutable revision must keep the earlier
    version readable forever, but the earlier version must stop being *the* Claim the deck
    is built from -- otherwise completing a RED NumericFact binding through the documented
    reviewer channel could never clear the verifier, because the unbound predecessor stayed
    in the verified set and blocked it for good.
    """
    return [claim for claim in project.claims if not claim.superseded_by_claim_id]


def triage_claims(project: Project) -> list[TriageDecision]:
    if not project.presentation_question.strip():
        raise HTTPException(422, "Presentation Question is required before Triage")
    question_terms = terms(project.presentation_question)
    goal_terms = terms(project.project_goal)
    profile = audience_profile(project.audience)
    decisions: list[TriageDecision] = []
    for claim in active_claims(project):
        overlap = len(question_terms & terms(claim.normalized_claim))
        goal_overlap = len(goal_terms & terms(claim.normalized_claim))
        fit = audience_fit(claim, profile)
        score = min(100, 28 + overlap * 18 + min(12, goal_overlap * 4) + min(18, fit * 6) + (12 if claim.provenance == "SOURCE" else 0))
        if overlap >= 2 or (overlap >= 1 and fit >= 1):
            bucket = "MUST_INCLUDE"
        elif overlap == 1:
            bucket = "SHOULD_INCLUDE"
        else:
            bucket = "APPENDIX"
        # RED is a constraint on review and rendering, not an automatic reason
        # to consume the main narrative budget.
        cost = 70 + min(40, len(claim.conditions) * 12) + (20 if claim.numeric_facts else 0) + (20 if claim.risk == "RED" else 0)
        reason = f"Question overlap={overlap}; goal_overlap={goal_overlap}; project_type={project.project_type}; audience_profile={profile}; audience_fit={fit}; risk={claim.risk}; provenance={claim.provenance}; estimated_cost={cost}s."
        decision = TriageDecision(claim_id=claim.id, bucket=bucket, score=score, reason=reason, meaning_preserving_bundle=claim.conditions, presentation_cost_seconds=cost)
        claim.triage = bucket
        decisions.append(decision)
    return decisions


def preserved_triage_overrides(project: Project) -> dict[str, TriageDecision]:
    """Audited bucket overrides, keyed by Claim, captured before triage recomputes.

    An override is a recorded human decision, not a cache of the rule engine's last
    output. Recomputing triage (a routine event: the question, audience or scope
    changed) must not silently delete it, which is what happened before this helper
    existed -- a correction pass that excluded publisher boilerplate was undone by the
    next triage run with no trace in the audit log.
    """
    return {decision.claim_id: decision for decision in project.triage_decisions if decision.overridden}


def apply_triage_overrides(project: Project, previous: dict[str, TriageDecision]) -> list[str]:
    """Re-apply captured overrides onto freshly computed decisions.

    Returns the Claim ids whose override survived. A Claim that no longer exists is
    reported by omission rather than resurrected.
    """
    index = {decision.claim_id: decision for decision in project.triage_decisions}
    claims = {claim.id: claim for claim in project.claims}
    preserved: list[str] = []
    for claim_id, decision in previous.items():
        current = index.get(claim_id)
        claim = claims.get(claim_id)
        if current is None or claim is None:
            continue
        current.bucket = decision.bucket
        current.overridden = True
        current.reason = decision.reason
        claim.triage = decision.bucket
        preserved.append(claim_id)
    return preserved


def duration_assessment(project: Project, decisions: list[TriageDecision]) -> dict:
    """Detect a mainline time conflict before Architect can omit content."""
    must = [decision for decision in decisions if decision.bucket == "MUST_INCLUDE"]
    required_seconds = sum(decision.presentation_cost_seconds for decision in must)
    capacity_seconds = project.duration_minutes * 60
    exceeds = required_seconds > capacity_seconds
    return {
        "duration_minutes": project.duration_minutes,
        "capacity_seconds": capacity_seconds,
        "must_include_seconds": required_seconds,
        "must_include_claim_ids": [decision.claim_id for decision in must],
        "needs_user_input": exceeds,
        "message": "MUST_INCLUDE 内容超过时长预算。请收窄 Presentation Question、扩大时长，或由用户明确调整范围；系统不会静默删除关键内容。" if exceeds else "MUST_INCLUDE 内容在时长预算内。",
    }


def override_triage_decision(project: Project, claim_id: str, request: TriageOverrideRequest) -> dict:
    decision = next((item for item in project.triage_decisions if item.claim_id == claim_id), None)
    claim = next((item for item in project.claims if item.id == claim_id), None)
    if decision is None or claim is None:
        raise HTTPException(404, "TriageDecision or Claim not found; run Triage before overriding content selection")
    before = {"bucket": decision.bucket, "claim_triage": claim.triage, "reason": decision.reason}
    decision.bucket = request.bucket
    decision.overridden = True
    decision.reason = f"{decision.reason} USER_OVERRIDE by {request.reviewer}: {request.rationale}"
    claim.triage = request.bucket
    duration = duration_assessment(project, project.triage_decisions)
    invalidated = invalidate_verification(project, f"Triage override changed {claim_id} to {request.bucket}; narrative must be rebuilt.")
    project.workflow_state = "NEEDS_USER_INPUT" if duration["needs_user_input"] else "TRIAGED"
    return {
        "claim_id": claim_id,
        "before": before,
        "after": {"bucket": decision.bucket, "claim_triage": claim.triage, "reason": decision.reason},
        "reviewer": request.reviewer,
        "rationale": request.rationale,
        "duration_assessment": duration,
        "invalidated_verification_results": invalidated,
    }


def choose_visual(text: str) -> str:
    lowered = text.lower()
    for visual, keywords in VISUAL_BY_TERMS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            return visual
    return "EVIDENCE_MAP"


def architect(project: Project) -> tuple[NarrativePlan, list[PageSpec]]:
    selected = [claim for claim in active_claims(project) if claim.triage in ("MUST_INCLUDE", "SHOULD_INCLUDE")]
    if not selected:
        raise HTTPException(422, "No triaged claims are eligible for a narrative")
    profile = audience_profile(project.audience)
    groups: dict[str, list[Claim]] = {}
    for claim in selected:
        visual = choose_visual(claim.normalized_claim)
        groups.setdefault(visual, []).append(claim)
    order = {visual: position for position, visual in enumerate(AUDIENCE_NARRATIVE_ORDER[profile])}
    ordered_groups = sorted(groups.items(), key=lambda item: (order.get(item[0], len(order)), item[0]))
    pages: list[PageSpec] = []
    sections: list[dict] = []
    for position, (visual, claims) in enumerate(ordered_groups, start=1):
        section_page_ids: list[str] = []
        section_provenance: Provenance = "SOURCE" if len(claims) == 1 else "SYNTHESIS"
        for chunk_number, claim_chunk in enumerate((claims[index:index + 4] for index in range(0, len(claims), 4)), start=1):
            primary = claim_chunk[0]
            provenance: Provenance = primary.provenance if len(claim_chunk) == 1 else "SYNTHESIS"
            suffix = f"（{chunk_number}）" if len(claims) > 4 else ""
            title = f"{visual.replace('_', ' ').title()}｜{primary.normalized_claim[:28]}{suffix}"
            page = PageSpec(id=f"pg_{uuid.uuid4().hex[:8]}", title=title, primary_message=primary.normalized_claim, visual_type=visual, claim_ids=[claim.id for claim in claim_chunk], provenance=provenance, goal=f"服务项目目标：{project.project_goal}；回答 Presentation Question；不新增临床关系")
            pages.append(page)
            section_page_ids.append(page.id)
            section_provenance = "SYNTHESIS" if provenance == "SYNTHESIS" else section_provenance
        sections.append({"order": position, "title": visual.replace("_", " ").title(), "page_ids": section_page_ids, "provenance": section_provenance})
    plan = NarrativePlan(narrative_spine=project.presentation_question, provenance="SYNTHESIS", audience_strategy=f"{profile}_sequence; project_type={project.project_type}; source-faithful claim content unchanged", sections=sections, generated_at=now())
    return plan, pages


def modality_strength(text: str) -> int:
    """A small deterministic guard for consequential Chinese semantic triggers."""
    weak = ("相关", "提示", "可能", "可考虑", "可用于")
    moderate = ("建议", "推荐", "应当", "应")
    strong = ("导致", "引起", "决定", "必须", "禁忌", "证明")
    if any(token in text for token in strong):
        return 3
    if any(token in text for token in moderate):
        return 2
    if any(token in text for token in weak):
        return 1
    return 0


def title_entailment(page: PageSpec, claim_index: dict[str, Claim]) -> dict:
    # Structure pages (ROADMAP / SECTION_QUESTION / PART_RECAP / CONSOLIDATION)
    # intentionally carry no evidence Claims; their title names the narrative frame,
    # not a clinical assertion to be entailed by a Claim.
    if page.renders_structure in STRUCTURE_RENDERING_KINDS:
        return {"page_id": page.id, "status": "SUPPORTED", "coverage": 1.0,
                "source_modality": 0, "presented_modality": 0,
                "supporting_claim_ids": [], "reason": None}
    supporting = [claim_index[claim_id] for claim_id in page.claim_ids if claim_id in claim_index]
    evidence = " ".join(claim.normalized_claim for claim in supporting)
    title_terms = terms(page.title)
    evidence_terms = terms(evidence)
    # Visual-family terms such as "map" are presentation labels, not factual claims.
    factual = {x for x in title_terms if x not in {"map", "framework", "evidence", "clinical", "decision"}}
    ratio = len(factual & evidence_terms) / max(1, len(factual))
    source_modality = max((modality_strength(claim.normalized_claim) for claim in supporting), default=0)
    presented_modality = max(modality_strength(page.title), modality_strength(page.primary_message))
    source_conditions = [condition for claim in supporting for condition in claim.conditions]
    broad_scope = any(term in (page.title + page.primary_message) for term in ("所有患者", "全部患者", "普遍", "全民", "任何患者"))
    status = "SUPPORTED" if ratio >= 0.35 else "PARTIALLY_SUPPORTED"
    reason = None
    if presented_modality > source_modality:
        status = "UNSUPPORTED_STRENGTH_UPGRADE"
        reason = "Presented title or primary message upgrades modality/causality beyond supporting claims."
    elif broad_scope and source_conditions and not any(condition in (page.title + page.primary_message) for condition in source_conditions):
        status = "UNSUPPORTED_SCOPE_EXPANSION"
        reason = "Presented title or primary message broadens a condition-bound source claim."
    return {"page_id": page.id, "status": status, "coverage": round(ratio, 2), "source_modality": source_modality, "presented_modality": presented_modality, "supporting_claim_ids": page.claim_ids, "reason": reason}


def source_span_support(claim: Claim) -> dict:
    """Overlap is relevance evidence; obvious semantic reversals fail closed."""
    if claim.provenance != "SOURCE":
        return {"claim_id": claim.id, "status": "NOT_APPLICABLE", "coverage": None}
    quote_terms = terms(claim.source_quote or "")
    claim_terms = terms(claim.normalized_claim)
    coverage = len(quote_terms & claim_terms) / max(1, len(claim_terms))
    contradictions = contradiction_signals(claim.source_quote or "", claim.normalized_claim)
    omissions = missing_source_signals(claim.source_quote or "", claim.normalized_claim)
    verbatim = re.sub(r"\s+", "", claim.source_quote or "") == re.sub(r"\s+", "", claim.normalized_claim)
    # Minimal-span floor. Verbatim text is necessary but not sufficient: reusing the
    # `source_quote` field to restate a Claim the document never made produced a span with
    # overlap 0.0 that was still reported as SUPPORTED, because the verbatim branch had
    # replaced the old `coverage >= 0.30` test instead of refining it. The binding gate
    # catches the forged quote, so delivery was never at risk, but the span record -- which
    # is what an auditor reads -- claimed a support that did not exist. No overlap at all
    # means the span does not locate the Claim, whatever its provenance field says.
    status = ("CONTRADICTED" if contradictions else
              "UNSUPPORTED_NO_OVERLAP" if verbatim and coverage == 0 else
              "SUPPORTED" if verbatim else "PARTIALLY_SUPPORTED")
    return {"claim_id": claim.id, "status": status, "coverage": round(coverage, 2),
            "semantic_signals": contradictions + omissions,
            "reason": "VERBATIM_SOURCE_SPAN" if verbatim else "PARAPHRASE_REQUIRES_REVIEW"}


def verifier(project: Project) -> dict:
    issues: list[dict] = []
    source_spans: list[dict] = []
    coverage = {"claim": "PASS", "title_primary": "PASS", "data_binding": "PASS", "clinical_relationship": "PASS", "contextual_implication": "PASS", "medical_visual": "NOT_APPLICABLE"}
    for claim in active_claims(project):
        if claim.provenance == "SOURCE" and not claim.source_quote:
            issues.append({"type": "SOURCE_FIDELITY", "severity": "BLOCK", "object": claim.id, "message": "SOURCE Claim lacks source_quote."})
        binding_issues = source_binding_issues(project, claim)
        if binding_issues:
            issues.append({"type": "SOURCE_FIDELITY", "severity": "BLOCK", "object": claim.id, "message": "; ".join(binding_issues) + "."})
        if claim.risk == "RED" and not claim.conditions:
            issues.append({"type": "MEANING_BUNDLE", "severity": "BLOCK", "object": claim.id, "message": "RED Claim has no protected conditions."})
        span = source_span_support(claim)
        source_spans.append(span)
        if span["status"] != "SUPPORTED" and claim.provenance == "SOURCE":
            # CONTRADICTED is a semantic reversal, UNSUPPORTED_NO_OVERLAP is a span that
            # locates nothing: neither is a wording question a reviewer should be asked to
            # wave through, so both block regardless of the Claim's declared risk.
            severity = "BLOCK" if (claim.risk == "RED"
                                   or span["status"] in {"CONTRADICTED", "UNSUPPORTED_NO_OVERLAP"}) else "HUMAN_REVIEW"
            coverage["claim"] = "FAIL"
            issues.append({"type": "MINIMUM_SOURCE_SPAN", "severity": severity, "object": claim.id,
                           "message": "SourceRef locates text but the source does not support the normalized Claim: "
                                      + ", ".join(span["semantic_signals"] or [span["reason"]]) + "."})
        for fact in claim.numeric_facts:
            missing = numeric_binding_missing(fact, claim)
            origin_issues = numeric_origin_issues(fact, claim)
            fidelity_issues = numeric_source_fidelity_issues(fact, claim)
            if claim.risk == "RED" and (fact.status != "BOUND" or missing):
                suffix = "; missing " + ", ".join(missing) if missing else ""
                issues.append({"type": "NUMERICAL_QA", "severity": "BLOCK", "object": claim.id, "message": f"RED NumericFact {fact.value} is {fact.status}{suffix}."})
            if origin_issues:
                issues.append({"type": "NUMERICAL_PROVENANCE", "severity": "BLOCK", "object": claim.id, "message": "; ".join(origin_issues) + "."})
                coverage["data_binding"] = "FAIL"
            if fidelity_issues:
                severity = "BLOCK" if claim.risk == "RED" else "HUMAN_REVIEW"
                issues.append({"type": "NUMERICAL_QA", "severity": severity, "object": claim.id, "message": "; ".join(fidelity_issues) + "."})
                coverage["data_binding"] = "FAIL"
        if claim.conflict_group_id and claim.triage in ("MUST_INCLUDE", "SHOULD_INCLUDE"):
            issues.append({"type": "CROSS_SOURCE_CONFLICT", "severity": "HUMAN_REVIEW", "object": claim.id, "message": f"Claim is in unresolved conflict group {claim.conflict_group_id}."})
    claim_index = {claim.id: claim for claim in project.claims}
    entailments = [title_entailment(page, claim_index) for page in project.pages]
    for result in entailments:
        if result["status"] != "SUPPORTED":
            severity = "BLOCK" if result["status"].startswith("UNSUPPORTED_") else "HUMAN_REVIEW"
            coverage["title_primary"] = "FAIL"
            issues.append({"type": "TITLE_ENTAILMENT", "severity": severity, "object": result["page_id"], "message": result["reason"] or "Page title requires human entailment review."})
    for relationship in project.relationships:
        if relationship.provenance == "SOURCE" and not relationship.source_refs:
            coverage["clinical_relationship"] = "FAIL"
            issues.append({"type": "RELATIONSHIP_PROVENANCE", "severity": "BLOCK", "object": relationship.id, "message": "SOURCE relationship requires its own explicit source span; Claim provenance is insufficient."})
        entailment_issues = relationship_source_entailment_issues(project, relationship)
        if entailment_issues:
            coverage["clinical_relationship"] = "FAIL"
            severity = "BLOCK" if relationship.risk == "RED" else "HUMAN_REVIEW"
            issues.append({"type": "RELATIONSHIP_PROVENANCE", "severity": severity, "object": relationship.id, "message": "; ".join(entailment_issues) + "."})
        if relationship.logic_operator != "NONE" and not relationship.conditions:
            coverage["clinical_relationship"] = "FAIL"
            issues.append({"type": "RELATIONSHIP_LOGIC", "severity": "BLOCK", "object": relationship.id, "message": "AND/OR/NOT/EXCEPT relationship has no bound clinical condition."})
        if relationship.risk == "RED" and (relationship.status != "SUPPORTED" or relationship.review_status != "APPROVED"):
            coverage["clinical_relationship"] = "FAIL"
            issues.append({"type": "RELATIONSHIP", "severity": "HUMAN_REVIEW", "object": relationship.id, "message": "RED relationship may not be automatically approved."})
    semantic_triggers = ("因此", "所以", "基于上述", "下一步", "相比之下", "优先", "随后")
    for page in project.pages:
        if any(trigger in (page.title + page.primary_message) for trigger in semantic_triggers) and not page.relationship_ids:
            coverage["contextual_implication"] = "FAIL"
            page_is_red = any(claim_index[claim_id].risk == "RED" for claim_id in page.claim_ids if claim_id in claim_index)
            severity = "BLOCK" if page_is_red else "HUMAN_REVIEW"
            issues.append({"type": "CONTEXTUAL_IMPLICATION", "severity": severity, "object": page.id, "message": "Semantic trigger requires an explicit verified Relationship; page order and adjacency are insufficient."})
    visual_issues = medical_visual_asset_issues(project) + visual_binding_issues(project)
    if visual_issues:
        coverage["medical_visual"] = "FAIL"
        issues.extend(visual_issues)
    elif project.medical_visual_assets or project.visual_bindings:
        coverage["medical_visual"] = "PASS"
    contextual_issues = contextual_contract_issues(project)
    if contextual_issues:
        coverage["contextual_implication"] = "FAIL"
        issues.extend(contextual_issues)
    status = "BLOCK" if any(i["severity"] == "BLOCK" for i in issues) else ("HUMAN_REVIEW_REQUIRED" if issues else "PASS")
    if project.verification_mode == "EXTERNAL_MEDICAL_CHECK" and not project.external_medical_check:
        issues.append({"type": "EXTERNAL_MODE", "severity": "BLOCK", "object": project.id, "message": "EXTERNAL_MEDICAL_CHECK requires explicit project opt-in."})
        status = "BLOCK"
    return {"status": status, "issues": issues, "title_entailments": entailments, "source_span_support": source_spans, "verification_coverage": coverage, "verification_mode": project.verification_mode, "verified_at": now()}


def record_verification(project: Project) -> dict:
    """Run the verifier and PERSIST the result on the project.

    Export and review-sheet paths require a persisted, current VerificationResult;
    a transient in-memory dict is deliberately rejected so that a one-off check
    cannot be mistaken for a recorded verification. Every caller -- the verify
    endpoint and tests alike -- must go through this function rather than
    appending to ``verification_results`` by hand.
    """
    result = verifier(project)
    persist_verification_issue_lifecycle(project, result)
    project.verification_results.append(result)
    project.workflow_state = "BLOCKED" if result["status"] == "BLOCK" else "VERIFIED"
    project.model_runs.append(record_run(
        "medical_verifier",
        {"claims": [claim.id for claim in project.claims],
         "page_ids": [page.id for page in project.pages]},
        result,
    ))
    audit(project, "MEDICAL_VERIFIER_RUN",
          f"Read-only source fidelity verification: {result['status']}")
    return result


ISSUE_ROUTING = {
    "TITLE_ENTAILMENT": ("medical_information_architect", "Revise title or Primary Message; do not rewrite the Claim to fit a title."),
    "CONTEXTUAL_IMPLICATION": ("medical_information_architect", "Add a Context Contract, reset, or remove unsupported implication."),
    "CONTEXT_CONTRACT": ("medical_information_architect", "Declare explicit context scope or remove unsupported cross-page implication."),
    "NUMERICAL_QA": ("claim_builder", "Correct the NumericFact semantic binding from source evidence."),
    "NUMERICAL_PROVENANCE": ("claim_builder", "Correct numeric origin, formula, or source binding without inventing values."),
    "MINIMUM_SOURCE_SPAN": ("claim_builder", "Restore source-supported wording or route for human source-span review."),
    "SOURCE_FIDELITY": ("claim_builder", "Repair source quote/source reference binding."),
    "RELATIONSHIP": ("semantic_relationship_engine", "Add or correct explicit Relationship provenance and review state."),
    "RELATIONSHIP_PROVENANCE": ("semantic_relationship_engine", "Bind relationship to its own source span; Claim provenance is insufficient."),
    "RELATIONSHIP_LOGIC": ("semantic_relationship_engine", "Record clinical logic conditions without adding a new medical inference."),
    "VISUAL_BINDING": ("visual_design_agent", "Restore locked semantic visual binding from the approved contract."),
    "MEDICAL_VISUAL_QA": ("visual_design_agent", "Route the medical visual through required semantic-fidelity review."),
    "COPYRIGHT": ("compliance_agent", "Resolve license status or remove the asset from delivery."),
}


def issue_route(issue_type: str | None) -> tuple[str, str]:
    return ISSUE_ROUTING.get(issue_type or "", ("human_reviewer", "No safe automated owner; assign an accountable human reviewer."))


def route_verification_issue(project: Project, issue_id: str, request: IssueRouteRequest) -> dict:
    issue = next((item for item in project.verification_issues if item.get("id") == issue_id), None)
    if issue is None:
        raise HTTPException(404, "VerificationIssue not found")
    recommended_module, _ = issue_route(issue.get("type"))
    if request.responsible_module != recommended_module and request.responsible_module != "human_reviewer":
        raise HTTPException(422, f"Issue type {issue.get('type')} must route to {recommended_module} or a human reviewer")
    issue["status"] = "ROUTED"
    issue["responsible_module"] = request.responsible_module
    issue["routing_rationale"] = request.rationale
    issue["routed_at"] = now()
    return issue


def persist_verification_issue_lifecycle(project: Project, result: dict) -> dict:
    """Persist verifier findings without allowing the verifier to repair content."""
    result_id = f"ver_{uuid.uuid4().hex[:8]}"
    result["verification_result_id"] = result_id
    active_keys: set[str] = set()
    created_ids: list[str] = []
    for issue in result.get("issues", []):
        key = hashlib.sha256(json.dumps({"type": issue.get("type"), "object": issue.get("object"), "message": issue.get("message")}, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        active_keys.add(key)
        existing = next((item for item in project.verification_issues if item.get("fingerprint") == key and item.get("status") not in {"VERIFIED_RESOLVED", "WAIVED_BY_HUMAN"}), None)
        if existing:
            existing["status"] = "OPEN"
            existing["last_seen_at"] = now()
            existing["occurrences"] = existing.get("occurrences", 1) + 1
            existing["verification_result_id"] = result_id
            if existing["occurrences"] >= 2 and issue.get("severity") == "BLOCK":
                existing["status"] = "HUMAN_REVIEW_REQUIRED"
            created_ids.append(existing["id"])
        else:
            responsible_module, recommended_action = issue_route(issue.get("type"))
            issue_record = {
                "id": f"iss_{uuid.uuid4().hex[:8]}",
                "fingerprint": key,
                "verification_result_id": result_id,
                "type": issue.get("type"),
                "severity": issue.get("severity"),
                "object": issue.get("object"),
                "message": issue.get("message"),
                "status": "OPEN",
                "recommended_responsible_module": responsible_module,
                "recommended_action": recommended_action,
                "occurrences": 1,
                "created_at": now(),
                "last_seen_at": now(),
            }
            project.verification_issues.append(issue_record)
            created_ids.append(issue_record["id"])
    for item in project.verification_issues:
        if item.get("status") == "RESOLVED_PENDING_REVERIFY" and item.get("fingerprint") not in active_keys:
            item["status"] = "VERIFIED_RESOLVED"
            item["verified_resolved_at"] = now()
    run = {
        "reverification_run_id": f"rr_{uuid.uuid4().hex[:8]}",
        "verification_result_id": result_id,
        "target_issue_ids": created_ids,
        "targeted_reverification": {"status": result["status"]},
        "regression_verification": {"status": result["status"], "new_issue_ids": created_ids},
        "affected_gate_runs": ["medical_fidelity", "data_binding", "clinical_relationship", "context", "medical_visual"],
        "final_status": result["status"],
        "created_at": now(),
    }
    project.reverification_runs.append(run)
    return run


def create_human_override(project: Project, request: HumanOverrideRequest) -> dict:
    issue = next((item for item in project.verification_issues if item.get("id") == request.verification_issue_id), None)
    if issue is None:
        raise HTTPException(404, "VerificationIssue not found")
    if not any(item.get("verification_result_id") == request.verification_result_id for item in project.verification_results):
        raise HTTPException(422, "HumanOverride must reference an immutable recorded VerificationResult")
    override = {
        "override_id": f"hov_{uuid.uuid4().hex[:8]}",
        "verification_issue_id": issue["id"],
        "verification_result_id": request.verification_result_id,
        "original_status": issue["status"],
        "decision": "APPROVED_WITH_OVERRIDE",
        "override_provenance": request.override_provenance,
        "reason": request.reason,
        "reviewer_id": request.reviewer,
        "created_at": now(),
    }
    project.human_overrides.append(override)
    return override


def compliance(project: Project) -> dict:
    """Public-channel and privacy gate.

    Patient-identifier classes (phone, national ID, medical record number) block wherever
    they are found: their presence in the evidence means the project holds identifiable
    data, not merely that a string occurs. An email address is different in one specific
    way -- journals publish the corresponding author's address as standard front matter, so
    finding one *only* in the source is a review item ("confirm this is published
    correspondence"), while finding one in presentation text still blocks because it is
    about to ship. Collapsing those two cases made the gate unsatisfiable on real papers
    while telling a reviewer nothing about the deliverable.
    """
    issues: list[dict] = []
    public_terms = ("保证疗效", "治愈", "私信", "加微信", "购买", "处方", "咨询我")
    publication_contact_categories = {"EMAIL"}
    presentation_corpus = " ".join([claim.normalized_claim for claim in active_claims(project)] + [page.title + page.primary_message for page in project.pages])
    source_corpus = " ".join(chunk.get("text", "") for document in project.documents for chunk in document.get("chunks", []))
    privacy_patterns = {
        "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "PHONE": r"(?<!\d)(?:1[3-9]\d{9}|(?:\+?86[- ]?)?1[3-9]\d{9})(?!\d)",
        "NATIONAL_ID": r"(?<!\d)\d{17}[\dXx](?!\d)",
        "MEDICAL_RECORD_NO": r"(?:住院号|病案号|门诊号|MRN)\s*[:：#]?\s*[A-Za-z0-9-]{5,}",
    }
    for category, pattern in privacy_patterns.items():
        in_presentation = bool(re.search(pattern, presentation_corpus))
        in_source = bool(re.search(pattern, source_corpus))
        if not in_presentation and not in_source:
            continue
        if in_presentation or category not in publication_contact_categories:
            where = "presentation text" if in_presentation else "the source document"
            issues.append({"severity": "BLOCK", "category": "PRIVACY",
                           "message": f"Potential {category} is present in {where}. Redact before any delivery."})
        else:
            issues.append({"severity": "HUMAN_REVIEW", "category": "PRIVACY_SOURCE_ONLY",
                           "message": f"Potential {category} appears only in the source document, not in the deck. "
                                      "A reviewer must confirm it is published correspondence rather than patient data."})
    if project.output_channel == "public_xiaohongshu":
        for term in public_terms:
            if term in presentation_corpus:
                issues.append({"severity": "BLOCK", "category": "PUBLIC_CHANNEL", "message": f"Public channel restricted term: {term}"})
        if any(c.risk == "RED" and c.review_status != "APPROVED" for c in active_claims(project)):
            issues.append({"severity": "BLOCK", "category": "MEDICAL_REVIEW", "message": "Unapproved RED medical claims cannot enter public output."})
    return {"status": "BLOCK" if any(i["severity"] == "BLOCK" for i in issues) else "PASS", "issues": issues, "checked_at": now()}


VISUAL_TYPE_GRAMMAR = {
    "CLINICAL_DECISION_MAP": {"logic": True, "comparison": False, "precision_lookup": False},
    "EVIDENCE_MAP": {"logic": False, "comparison": False, "precision_lookup": False},
    "EVIDENCE_MATRIX": {"logic": False, "comparison": False, "precision_lookup": True},
    "CONCEPTUAL_FRAMEWORK": {"logic": False, "comparison": False, "precision_lookup": False},
    "MANAGEMENT_CYCLE": {"logic": False, "comparison": False, "precision_lookup": False},
    "TABLE_MATRIX": {"logic": True, "comparison": False, "precision_lookup": True},
    "DIRECT_COMPARISON_CHART": {"logic": False, "comparison": True, "precision_lookup": False},
    "TEXT_FORWARD_EDITORIAL": {"logic": True, "comparison": False, "precision_lookup": True},
}


def select_visual_strategy(page: PageSpec, claims: list[Claim], relationships: list[Relationship]) -> dict:
    """Batch-2 selector: classify/validate candidates, never invent semantics."""
    claim_ids = {claim.id for claim in claims}
    page_claims = [claim for claim in claims if claim.id in page.claim_ids]
    page_relationships = [relationship for relationship in relationships if relationship.id in page.relationship_ids]
    text = " ".join([page.goal, page.title, page.primary_message] + [claim.normalized_claim for claim in page_claims]).lower()
    standard = "CONSORT_PARTICIPANT_FLOW" if "consort" in text or "随机" in text and "流程" in text else ("PRISMA_FLOW" if "prisma" in text or "系统综述" in text else None)
    has_logic = any(relationship.logic_operator != "NONE" or relationship.polarity == "CONTRAINDICATION" for relationship in page_relationships)
    has_noncomparable = any(fact.comparability_status in {"NOT_COMPARABLE", "UNKNOWN"} for claim in page_claims for fact in claim.numeric_facts)
    precision_required = any(claim.numeric_facts for claim in page_claims) or any(word in text for word in ("阈值", "剂量", "矩阵", "查阅", "表"))
    candidates = [page.visual_type, "TABLE_MATRIX" if precision_required else "TEXT_FORWARD_EDITORIAL", "TEXT_FORWARD_EDITORIAL"]
    if standard:
        candidates.insert(0, standard)
    deduped = list(dict.fromkeys(candidates))
    evaluated = []
    for visual_type in deduped:
        grammar = VISUAL_TYPE_GRAMMAR.get(visual_type, {"logic": False, "comparison": False, "precision_lookup": False})
        exclusions = []
        if not page_claims and visual_type != "TEXT_FORWARD_EDITORIAL":
            exclusions.append("NO_APPROVED_SEMANTIC_OBJECT")
        if has_logic and not grammar["logic"]:
            exclusions.append("CANNOT_PRESERVE_CLINICAL_LOGIC")
        if has_noncomparable and grammar["comparison"]:
            exclusions.append("COMPARABILITY_GATE_FAILED")
        if precision_required and not grammar["precision_lookup"] and visual_type == "DIRECT_COMPARISON_CHART":
            exclusions.append("PRECISION_LOOKUP_REQUIRED")
        if visual_type in {"CONSORT_PARTICIPANT_FLOW", "PRISMA_FLOW"} and not standard:
            exclusions.append("STANDARD_NOT_APPLICABLE")
        evaluated.append({"visual_type": visual_type, "status": "INVALID_CANDIDATE" if exclusions else "VALID_CANDIDATE", "hard_exclusion_reasons": exclusions})
    valid = [candidate for candidate in evaluated if candidate["status"] == "VALID_CANDIDATE"]
    current = next((candidate for candidate in evaluated if candidate["visual_type"] == page.visual_type), None)
    if not page_claims:
        status, selected, rationale = "NO_VALID_VISUAL", "TEXT_FORWARD_EDITORIAL", "No approved semantic objects exist; do not force a medical visual."
    elif current and current["status"] == "VALID_CANDIDATE":
        status, selected, rationale = "SELECTED", page.visual_type, "Current PageSpec visual type passes frozen hard gates."
    elif valid:
        status, selected, rationale = "NEEDS_HUMAN_REVIEW", valid[0]["visual_type"], "PageSpec visual type failed a hard gate; an alternate safe candidate requires explicit architecture revision."
    else:
        status, selected, rationale = "NO_VALID_VISUAL", "TEXT_FORWARD_EDITORIAL", "Every semantic visual candidate failed frozen hard gates."
    return {
        "selector_version": "batch2-frozen-v0.1",
        "page_id": page.id,
        "decision_status": status,
        "selected_primary_visual": selected,
        "current_page_visual_type": page.visual_type,
        "visual_intent": "PRECISION_LOOKUP" if precision_required else ("CLINICAL_LOGIC" if has_logic else "EXPLAIN"),
        "information_structure": {"has_logic": has_logic, "has_noncomparable_data": has_noncomparable, "precision_required": precision_required, "approved_claim_ids": sorted(claim_ids & set(page.claim_ids))},
        "standard_candidate": standard,
        "candidates": evaluated,
        "selection_rationale": rationale,
        "generation_strategy": "SEPARATE_ROUTER_DECISION",
    }


def visual_router(project: Project, capabilities: dict[str, dict] | None = None) -> list[dict]:
    plans: list[dict] = []
    index = {claim.id: claim for claim in project.claims}
    registry = capabilities or effective_generation_capability_registry(project)
    for page in project.pages:
        strategy = select_visual_strategy(page, project.claims, project.relationships)
        protected = []
        not_comparable = []
        for claim_id in page.claim_ids:
            claim = index.get(claim_id)
            if claim and (claim.risk == "RED" or claim.numeric_facts):
                protected.append({"claim_id": claim_id, "lock": "MEDICAL_TRUTH_LOCK", "reason": "RED or numeric semantic content"})
            if claim:
                not_comparable.extend(fact.value for fact in claim.numeric_facts if fact.comparability_status == "NOT_COMPARABLE")
        prohibited = ["FULL_IMAGE for exact text/numeric/clinical topology", "repaint of protected semantic layer"]
        if not_comparable:
            prohibited.append("direct comparative chart/claim for NOT_COMPARABLE data")
        external_egress_allowed = project.allow_external_generation and project.generation_data_egress_policy != "DENY"
        route = select_generation_route(visual_type=page.visual_type, has_exact_text=bool(protected), has_exact_geometry=any(claim.numeric_facts for claim_id in page.claim_ids if (claim := index.get(claim_id))), has_topology_lock=bool(page.relationship_ids), editorial_base_allowed=True, external_egress_allowed=external_egress_allowed, capabilities=registry)
        page_assets = [asset for asset in project.medical_visual_assets if asset.get("page_id") == page.id]
        asset_routes: list[dict] = []
        asset_rejections: list[dict] = []
        for asset in page_assets:
            asset_route = select_qualified_component_engine(registry, {"medical_asset_pipeline"}, external_egress_allowed=external_egress_allowed)
            if asset_route["status"] != "ROUTABLE":
                asset_rejections.append({"asset_id": asset.get("id"), "reason": "NO_QUALIFIED_MEDICAL_ASSET_PIPELINE", "rejected_candidates": asset_route["rejected_candidates"]})
                continue
            engine = asset_route["engine"]
            asset_routes.append({
                "component": f"medical_visual_asset:{asset['id']}",
                "asset_id": asset["id"],
                "engine_id": asset_route["engine_id"],
                "engine_version": engine["engine_version"],
                "requirements": ["medical_asset_pipeline"],
                "generation_mode": "VERIFIED_MEDICAL_ASSET_RENDERER",
                "asset_contract": {"origin": asset.get("origin"), "semantic_role": asset.get("semantic_role"), "ai_generation_allowed": asset.get("ai_generation_allowed"), "medical_verified": asset.get("medical_verified")},
            })
        composition = route["effective_generation_route"]["composition_strategy"]
        generation_mode = "DETERMINISTIC_COMPOSITOR" if composition in {"CONTROLLED_COMPOSITION", "HYBRID_COMPOSITION"} else "FULL_IMAGE"
        selector_allows = strategy["decision_status"] == "SELECTED"
        effective_route = {**route["effective_generation_route"], "component_routes": route["effective_generation_route"]["component_routes"] + asset_routes}
        allowed = route["status"] == "ROUTABLE" and selector_allows and not asset_rejections
        route_status = route["status"] if selector_allows else strategy["decision_status"]
        if asset_rejections:
            route_status = "UNROUTABLE"
        plans.append({"page_id": page.id, "visual_type": page.visual_type, "visual_strategy_decision": strategy, "preferred_generation_strategy": route["preferred_generation_strategy"], "effective_generation_route": effective_route, "generation_mode": generation_mode, "protected_semantic_layer": protected, "medical_visual_assets": [{"id": asset["id"], "origin": asset.get("origin"), "semantic_role": asset.get("semantic_role")} for asset in page_assets], "not_comparable_values": not_comparable, "allowed": allowed, "route_status": route_status, "rejected_candidates": route["rejected_candidates"] + asset_rejections, "prohibited": prohibited, "verification_required": ["mandatory_object_coverage", "exact_text", "numeric_fidelity", "relationship_fidelity", "comparability_fidelity", "medical_asset_fidelity", "source_visibility"]})
    return plans


def compile_visual_contracts(project: Project, plans: list[dict]) -> list[dict]:
    """Compile approved semantic content to renderer constraints, not a free-form prompt."""
    claim_index = {claim.id: claim for claim in project.claims}
    contracts: list[dict] = []
    for plan in plans:
        page = next(page for page in project.pages if page.id == plan["page_id"])
        claim_objects = [claim_index[claim_id] for claim_id in page.claim_ids if claim_id in claim_index]
        page_bindings = [
            {
                "id": binding["id"],
                "binding_type": binding["binding_type"],
                "from_object_id": binding["from_object_id"],
                "to_object_id": binding["to_object_id"],
                "semantic_value": binding["semantic_value"],
                "axis_baseline_policy": binding.get("axis_baseline_policy", "NOT_APPLICABLE"),
            }
            for binding in project.visual_bindings
            if binding.get("page_id") == page.id
        ]
        exact_text = [page.title, page.primary_message]
        exact_text.extend(fact.value for claim in claim_objects for fact in claim.numeric_facts if claim.risk == "RED")
        contracts.append({
            "visual_generation_contract_id": f"vgc_{project.id}_{page.id}",
            "project_id": project.id,
            "page_id": page.id,
            "approved_semantic_page_graph_version": immutable_snapshot_digest({"project_id": project.id, "presentation_question": project.presentation_question, "export_type": "SEMANTIC_PAGE_GRAPH", "pages": [{"page_id": page.id, "claim_ids": page.claim_ids, "relationship_ids": page.relationship_ids}]}, project.documents, reading_sha256=project.reading_structure_sha256)[:16],
            "page_identity": {"section_id": page.id, "page_type": page.visual_type, "project_type": project.project_type},
            "page_goal": {"text": page.goal, "lock_level": "SEMANTIC_LOCK"},
            "audience": {"primary": project.audience, "expertise_level": audience_profile(project.audience), "lock_level": "HARD_LOCK"},
            "primary_message": {"text": page.primary_message, "provenance": page.provenance, "claim_bindings": page.claim_ids, "render_text_lock": "SEMANTIC_LOCK"},
            "generation_mode": plan["generation_mode"],
            "mandatory_object_ids": page.claim_ids + page.relationship_ids,
            "exact_text_register": exact_text,
            "relationship_ids": page.relationship_ids,
            "data_binding_ids": [f"{claim.id}:numeric:{position}" for claim in claim_objects for position, _ in enumerate(claim.numeric_facts)],
            "medical_visual_asset_ids": [asset["id"] for asset in plan.get("medical_visual_assets", [])],
            "medical_visual_asset_contracts": plan.get("medical_visual_assets", []),
            "protected_semantic_layer": plan["protected_semantic_layer"],
            "visual_semantic_contract": {"relationship_ids": page.relationship_ids, "binding_snapshot": page_bindings, "group_bindings": [binding for binding in page_bindings if binding["binding_type"] == "group_to_meaning"], "logic_bindings": [binding for binding in page_bindings if binding["binding_type"] == "connector_to_relationship"], "legend_bindings": [binding for binding in page_bindings if binding["binding_type"] == "legend_to_series"], "color_semantic_bindings": [binding for binding in page_bindings if binding["binding_type"] == "color_to_semantic"], "status": "LOCKED"},
            "layout_freedom_envelope": {"reading_flow": "top_to_bottom", "title_region": "top", "source_region": "bottom", "semantic_overlap_allowed": False},
            "visual_hierarchy_contract": [{"object_id": "PRIMARY_MESSAGE", "priority_rank": 1, "priority_semantics": "presentation_priority"}],
            "layout_freedom": "presentation_layout_only",
            "prohibited_transformations": plan["prohibited"],
            "output_spec": {"aspect_ratio": "16:9", "presentation_slide": True},
            "post_generation_verification": {"requirements": {"mandatory_object_coverage": 1.0, "exact_text_fidelity": 1.0, "numeric_fidelity": 1.0, "relationship_fidelity": 1.0, "visual_binding_fidelity": 1.0, "axis_extent_fidelity": 1.0, "source_visibility": "REQUIRED"}, "validator_types": plan["verification_required"] + ["visual_binding_fidelity", "axis_extent_fidelity"]},
        })
    return contracts


def compile_prompt_briefs(project: Project, contracts: list[dict]) -> list[dict]:
    """Compile editorial-only prompts; protected medical content is never emitted."""
    briefs: list[dict] = []
    for contract in contracts:
        briefs.append({
            "prompt_brief_id": f"pbc_{project.id}_{contract['page_id']}",
            "page_id": contract["page_id"],
            "prompt_version": "editorial_base_v1",
            "data_egress_policy": "DENY_EXTERNAL",
            "allowed_editorial_prompt": f"Create a restrained 16:9 editorial background for a {contract['page_identity']['page_type']} medical presentation. Reserve a clear top title region and bottom source region. Use neutral whitespace and no icons, labels, numbers, arrows, legends, clinical anatomy, or medical assertions.",
            "protected_content_handled_by": "local_deterministic_compositor",
            "excluded_from_prompt": ["claim text", "exact numbers", "relationship topology", "clinical recommendation strength", "source quote", "patient data"],
            "contract_id": contract["visual_generation_contract_id"],
        })
    return briefs


def verify_generated_visual_contract(project: Project, request: GeneratedVisualVerificationRequest) -> dict:
    contract = next((item for item in project.visual_contracts if item.get("visual_generation_contract_id") == request.visual_generation_contract_id), None)
    if contract is None or contract.get("page_id") != request.page_id:
        raise HTTPException(422, "Generated visual verification must reference the exact Page VisualGenerationContract")
    if contract.get("stale"):
        raise HTTPException(409, "Generated visual verification must use a current contract after capability requalification and rerouting")
    issues: list[dict] = []
    expected_objects = set(contract.get("mandatory_object_ids", []))
    missing_objects = sorted(expected_objects - set(request.rendered_mandatory_object_ids))
    if missing_objects:
        issues.append({"type": "MANDATORY_OBJECT_OMISSION", "severity": "BLOCK", "object": request.page_id, "message": f"Rendered visual omitted mandatory semantic objects: {missing_objects}"})
    expected_text = set(contract.get("exact_text_register", []))
    missing_text = sorted(expected_text - set(request.rendered_exact_text))
    if missing_text:
        issues.append({"type": "EXACT_TEXT_MUTATION", "severity": "BLOCK", "object": request.page_id, "message": "Rendered visual omitted or changed protected exact text."})
    expected_data = set(contract.get("data_binding_ids", []))
    if not expected_data.issubset(set(request.rendered_data_binding_ids)):
        issues.append({"type": "NUMERIC_FIDELITY", "severity": "BLOCK", "object": request.page_id, "message": "Rendered visual does not preserve all contract data bindings."})
    expected_relationships = set(contract.get("relationship_ids", []))
    rendered_relationships = set(request.rendered_relationship_ids)
    if not expected_relationships.issubset(rendered_relationships) or rendered_relationships - expected_relationships:
        issues.append({"type": "RELATIONSHIP_FIDELITY", "severity": "BLOCK", "object": request.page_id, "message": "Rendered visual relationship IDs differ from the approved contract."})
    expected_assets = set(contract.get("medical_visual_asset_ids", []))
    rendered_assets = set(request.rendered_medical_asset_ids)
    if expected_assets != rendered_assets:
        issues.append({"type": "MEDICAL_ASSET_FIDELITY", "severity": "BLOCK", "object": request.page_id, "message": "Rendered medical asset IDs differ from the approved asset contract."})
    expected_bindings = {
        binding["id"]: {key: binding[key] for key in ("binding_type", "from_object_id", "to_object_id", "semantic_value")}
        for binding in contract.get("visual_semantic_contract", {}).get("binding_snapshot", [])
    }
    rendered_bindings = {
        binding.binding_id: {
            "binding_type": binding.binding_type,
            "from_object_id": binding.from_object_id,
            "to_object_id": binding.to_object_id,
            "semantic_value": binding.semantic_value,
        }
        for binding in request.rendered_visual_bindings
    }
    if expected_bindings and expected_bindings != rendered_bindings:
        issues.append({"type": "VISUAL_BINDING_FIDELITY", "severity": "BLOCK", "object": request.page_id, "message": "Rendered legend, color, label, connector, or axis bindings differ from the frozen semantic binding snapshot."})
    axis_policies: dict[str, str] = {}
    for binding in contract.get("visual_semantic_contract", {}).get("binding_snapshot", []):
        if binding["binding_type"] not in {"axis_to_metric", "axis_to_unit"}:
            continue
        axis_id = binding["from_object_id"]
        policy = binding.get("axis_baseline_policy", "NOT_APPLICABLE")
        if axis_policies.get(axis_id) != "ZERO_REQUIRED":
            axis_policies[axis_id] = policy
    rendered_axis_ids = {axis.axis_object_id for axis in request.rendered_axis_scales}
    missing_axis_scales = sorted(set(axis_policies) - rendered_axis_ids)
    if missing_axis_scales:
        issues.append({"type": "AXIS_EXTENT_FIDELITY", "severity": "BLOCK", "object": request.page_id, "message": f"Rendered visual omitted required axis-scale observations: {missing_axis_scales}"})
    for axis in request.rendered_axis_scales:
        if axis.data_min > axis.data_max or axis.axis_min > axis.axis_max:
            issues.append({"type": "AXIS_EXTENT_FIDELITY", "severity": "BLOCK", "object": axis.axis_object_id, "message": "Axis scale bounds are internally invalid."})
        elif axis.axis_min > axis.data_min or axis.axis_max < axis.data_max:
            issues.append({"type": "AXIS_EXTENT_FIDELITY", "severity": "BLOCK", "object": axis.axis_object_id, "message": "Axis scale clips observed data outside the displayed extent."})
        elif axis_policies.get(axis.axis_object_id) == "ZERO_REQUIRED" and axis.axis_min != 0:
            issues.append({"type": "AXIS_BASELINE_POLICY", "severity": "BLOCK", "object": axis.axis_object_id, "message": "Frozen axis policy requires a zero baseline."})
        elif axis.scale == "LOG" and axis.data_min <= 0:
            issues.append({"type": "AXIS_SCALE_POLICY", "severity": "BLOCK", "object": axis.axis_object_id, "message": "A logarithmic axis cannot represent zero or negative observed values."})
    if not request.source_visible:
        issues.append({"type": "SOURCE_VISIBILITY", "severity": "BLOCK", "object": request.page_id, "message": "Rendered visual has no visible source traceability."})
    if request.visual_semantic_fidelity != "PASS":
        issues.append({"type": "VISUAL_SEMANTIC_FIDELITY", "severity": "BLOCK" if request.visual_semantic_fidelity == "FAIL" else "HUMAN_REVIEW", "object": request.page_id, "message": "Visual semantic-fidelity QA is not PASS."})
    forbidden = set(contract.get("prohibited_transformations", []))
    observed = set(request.prohibited_transformations_observed)
    if observed & forbidden or observed:
        issues.append({"type": "PROHIBITED_TRANSFORMATION", "severity": "BLOCK", "object": request.page_id, "message": "Rendered visual reports a prohibited or unapproved semantic transformation."})
    status = "BLOCK" if any(issue["severity"] == "BLOCK" for issue in issues) else ("HUMAN_REVIEW_REQUIRED" if issues else "PASS")
    result = {
        "generated_visual_verification_id": f"gvv_{uuid.uuid4().hex[:8]}",
        "page_id": request.page_id,
        "visual_generation_contract_id": request.visual_generation_contract_id,
        "status": status,
        "issues": issues,
        "generation_provenance": request.generation_provenance,
        "verified_at": now(),
    }
    project.generated_visual_verifications.append(result)
    return result


def review_object(project: Project, request: ReviewDecisionRequest) -> dict:
    if request.object_type == "claim":
        target = next((claim for claim in project.claims if claim.id == request.object_id), None)
        if target is None:
            raise HTTPException(404, "Claim not found")
        if request.decision == "APPROVE":
            if target.risk == "RED" and any(fact.status != "BOUND" or numeric_binding_missing(fact, target) for fact in target.numeric_facts):
                raise HTTPException(422, "A RED Claim with incomplete NumericFact binding cannot be approved")
            if not target.conditions:
                raise HTTPException(422, "Claim conditions must be recorded before approval")
            target.review_status = "APPROVED"
        else:
            target.review_status = "BLOCKED"
    else:
        target = next((relationship for relationship in project.relationships if relationship.id == request.object_id), None)
        if target is None:
            raise HTTPException(404, "Relationship not found")
        if request.decision == "APPROVE":
            if not target.source_refs and target.provenance != "SYNTHESIS":
                raise HTTPException(422, "Non-synthesis Relationship needs an explicit SourceRef")
            if target.provenance == "SOURCE" and relationship_source_entailment_issues(project, target):
                raise HTTPException(422, "A SOURCE Relationship can only be approved with entailed, resolvable provenance")
            target.status = "SUPPORTED"
            target.review_status = "APPROVED"
        else:
            target.status = "UNSUPPORTED"
            target.review_status = "BLOCKED"
    event = {"at": now(), "object_type": request.object_type, "object_id": request.object_id, "decision": request.decision, "reviewer": request.reviewer, "rationale": request.rationale}
    project.human_overrides.append(event)
    event["invalidated_verification_results"] = invalidate_verification(project, f"Human review decision changed {request.object_type} {request.object_id}.")
    if project.workflow_state == "BLOCKED":
        project.workflow_state = "ARCHITECTED"
    return event


def claim_immutable_ref(claim: Claim) -> str:
    root_id = claim.id.split(":v", 1)[0]
    return f"{root_id}:v{claim.version}"


def configure_retry_budget(project: Project, request: RetryBudgetRequest) -> dict:
    project.retry_budgets = [budget for budget in project.retry_budgets if budget.get("module") != request.module]
    budget = {
        "retry_budget_id": f"rb_{uuid.uuid4().hex[:8]}",
        "project_id": project.id,
        "module": request.module,
        "max_auto_revision_attempts": request.max_auto_revision_attempts,
        "current_attempt": 0,
        "recurrent_issue_threshold": request.recurrent_issue_threshold,
        "issue_occurrences": {},
        "status": "ACTIVE",
        "created_at": now(),
    }
    project.retry_budgets.append(budget)
    return budget


def consume_retry_budget(project: Project, module: str, issue_ids: list[str]) -> dict:
    budget = next((item for item in project.retry_budgets if item.get("module") == module), None)
    if budget is None:
        raise HTTPException(409, f"No RetryBudget configured for automated {module} revision")
    if budget.get("status") != "ACTIVE":
        raise HTTPException(409, f"RetryBudget for {module} is {budget.get('status')}; human review is required")
    budget["current_attempt"] = budget.get("current_attempt", 0) + 1
    occurrences = budget.setdefault("issue_occurrences", {})
    recurrent = []
    for issue_id in issue_ids:
        occurrences[issue_id] = occurrences.get(issue_id, 0) + 1
        if occurrences[issue_id] >= budget["recurrent_issue_threshold"]:
            recurrent.append(issue_id)
    if budget["current_attempt"] > budget["max_auto_revision_attempts"] or recurrent:
        budget["status"] = "HUMAN_REVIEW_REQUIRED"
        budget["escalated_at"] = now()
        budget["escalation_reason"] = "RECURRENT_CRITICAL_ISSUE" if recurrent else "AUTO_REVISION_BUDGET_EXHAUSTED"
        return {"allowed": False, "budget": budget, "recurrent_issue_ids": recurrent}
    return {"allowed": True, "budget": budget, "recurrent_issue_ids": []}


def create_claim_revision(project: Project, claim_id: str, request: ClaimRevisionRequest) -> dict:
    """Create a new Claim version; never overwrite the source version in place."""
    previous = next((candidate for candidate in project.claims if candidate.id == claim_id), None)
    if previous is None:
        raise HTTPException(404, "Claim not found")
    if request.conditions is None and request.numeric_facts is None:
        raise HTTPException(422, "A revision must change conditions or NumericFacts")
    if request.automated:
        budget = consume_retry_budget(project, request.responsible_module, request.verification_issue_ids)
        if not budget["allowed"]:
            raise HTTPException(409, f"Automatic revision stopped: {budget['budget']['escalation_reason']}; human review is required")
    root_id = previous.id.split(":v", 1)[0]
    lineage = [candidate for candidate in project.claims if candidate.id.split(":v", 1)[0] == root_id]
    new_version = max(candidate.version for candidate in lineage) + 1
    payload = previous.model_dump()
    payload.update({
        "id": f"{root_id}:v{new_version}",
        "version": new_version,
        "supersedes_claim_id": previous.id,
        "review_status": "NEEDS_HUMAN_REVIEW",
        "conditions": request.conditions if request.conditions is not None else previous.conditions,
        "numeric_facts": request.numeric_facts if request.numeric_facts is not None else previous.numeric_facts,
    })
    revised = Claim(**payload)
    project.claims.append(revised)
    # The predecessor leaves the active set; it stays readable as the superseded version.
    previous.superseded_by_claim_id = revised.id
    stale_pages = []
    for page in project.pages:
        if previous.id in page.claim_ids:
            page.revision_status = "STALE"
            stale_pages.append(page.id)
            project.object_dependencies.append({
                "dependency_id": f"dep_{uuid.uuid4().hex[:8]}",
                "upstream_object": claim_immutable_ref(previous),
                "downstream_object": page.id,
                "dependency_type": "page_claim_binding",
                "status": "STALE",
            })
    stale_relationships = [relation.id for relation in project.relationships if previous.id in {relation.from_claim_id, relation.to_claim_id}]
    for relationship_id in stale_relationships:
        project.object_dependencies.append({
            "dependency_id": f"dep_{uuid.uuid4().hex[:8]}",
            "upstream_object": claim_immutable_ref(previous),
            "downstream_object": relationship_id,
            "dependency_type": "relationship_endpoint",
            "status": "STALE",
        })
    revision = {
        "revision_id": f"rev_{uuid.uuid4().hex[:8]}",
        "object_type": "claim",
        "object_id": root_id,
        "new_claim_id": revised.id,
        "new_version": new_version,
        "supersedes_version": previous.version,
        "verification_issue_ids": request.verification_issue_ids,
        "responsible_module": request.responsible_module,
        "revision_reason": request.revision_reason,
        "created_at": now(),
        "status": "RESOLVED_PENDING_REVERIFY",
        "stale_page_ids": stale_pages,
        "stale_relationship_ids": stale_relationships,
    }
    project.revision_snapshots.append(revision)
    for issue in project.verification_issues:
        if issue.get("id") in request.verification_issue_ids:
            issue["status"] = "RESOLVED_PENDING_REVERIFY"
            issue["revision_id"] = revision["revision_id"]
    invalidated = invalidate_verification(project, f"Immutable revision {claim_immutable_ref(previous)} -> {claim_immutable_ref(revised)} requires re-verification.")
    # A revision invalidates the pages and verification that used the old version. When no
    # page was ever built there is nothing to rebuild, so the project must not be pushed
    # past the stage it is actually at -- doing so made the documented reviewer binding
    # channel unusable before Triage, because Triage may not run from ARCHITECTED.
    project.workflow_state = "ARCHITECTED" if project.pages else "EXTRACTED"
    revision["invalidated_verification_results"] = invalidated
    return {"revision": revision, "claim": revised}


def update_claim_binding(project: Project, claim_id: str, patch: ClaimBindingPatch) -> dict:
    claim = next((candidate for candidate in project.claims if candidate.id == claim_id), None)
    if claim is None:
        raise HTTPException(404, "Claim not found")
    before = {"conditions": claim.conditions, "numeric_facts": [fact.model_dump() for fact in claim.numeric_facts]}
    # Medical truth fields (text, provenance, source quote/ref, risk) deliberately
    # are not writable from this correction endpoint.
    if patch.conditions is not None:
        claim.conditions = patch.conditions
    if patch.numeric_facts is not None:
        claim.numeric_facts = patch.numeric_facts
    claim.review_status = "NEEDS_HUMAN_REVIEW"
    invalidated = invalidate_verification(project, f"Binding correction changed Claim {claim.id} conditions or NumericFacts.")
    event = {"at": now(), "object_type": "claim_binding", "object_id": claim.id, "reviewer": patch.reviewer, "rationale": patch.rationale, "before": before, "after": {"conditions": claim.conditions, "numeric_facts": [fact.model_dump() for fact in claim.numeric_facts]}}
    event["invalidated_verification_results"] = invalidated
    project.human_overrides.append(event)
    if project.workflow_state == "BLOCKED":
        project.workflow_state = "ARCHITECTED"
    return event


def create_synthetic_case(project: Project, request: SyntheticCaseRequest) -> dict:
    if not project.synthetic_case:
        raise HTTPException(409, "Synthetic Case is disabled for this project")
    if not request.explicitly_requested:
        raise HTTPException(422, "Synthetic Case requires explicit user request")
    known_claims = {claim.id for claim in project.claims}
    unknown = set(request.source_claim_ids) - known_claims
    if unknown:
        raise HTTPException(422, f"Synthetic Case references unknown claims: {sorted(unknown)}")
    case = {
        "id": f"syn_{uuid.uuid4().hex[:8]}",
        "title": request.title,
        "scenario_text": request.scenario_text,
        "purpose": request.purpose,
        "source_claim_ids": request.source_claim_ids,
        "provenance": "SYNTHESIS",
        "disclaimer": "AI生成模拟病例｜非原文病例｜仅用于教学演示",
        "created_at": now(),
    }
    # Synthetic data is deliberately isolated from Claim Table / canonicalization.
    project.synthetic_cases.append(case)
    return case


def _require_current_verification(project: Project, purpose: str) -> dict:
    """Fail closed, and say WHY the caller has to re-run verification.

    "run verify first" is misleading when a result exists but was invalidated by
    a semantic change: the operator needs to know the recorded result went stale,
    not that they never verified.
    """
    current = [result for result in project.verification_results
               if not result.get("stale", False)]
    if current:
        return current[-1]
    if project.verification_results:
        reasons = sorted({str(result.get("stale_reason") or "").strip()
                          for result in project.verification_results
                          if result.get("stale")} - {""})
        detail = "; ".join(reasons) or "invalidated by a semantic change"
        raise HTTPException(
            409,
            f"{purpose} requires a persisted, current VerificationResult; the "
            f"recorded result is stale ({detail}). Re-run "
            f"POST /api/projects/{{id}}/verify.",
        )
    raise HTTPException(
        409,
        f"{purpose} requires a persisted, current VerificationResult; run "
        f"POST /api/projects/{{id}}/verify first. Transient one-off verification "
        f"is not accepted.",
    )


def assemble_semantic_deck(project: Project) -> dict:
    """Assemble the approved deck without applying the delivery gates.

    A generator has to hold the approved deck in order to execute a routed component and
    report what it rendered; only then can the post-generation verification the delivery
    gate waits for exist. Requiring the gate before generation therefore closed a loop with
    no entry point. This function is the generator's view; `semantic_deck` is the delivery
    view and keeps every gate. It is not exposed as an endpoint.
    """
    claim_index = {claim.id: claim for claim in project.claims}
    relationship_index = {relationship.id: relationship for relationship in project.relationships}
    return {
        "project_id": project.id,
        "presentation_question": project.presentation_question,
        "export_type": "APPROVED_SEMANTIC_DECK_JSON",
        "pages": [{
            "page_id": page.id,
            "goal": page.goal,
            "title": page.title,
            "primary_message": page.primary_message,
            "visual_type": page.visual_type,
            # The reading's declared intent decides which layout grammars are legal, so it has to
            # reach the compiler. Without it the compiler could only substring-match `visual_type`
            # -- which is how a page declared COMPARISON was denied the comparison layout.
            "figure_intent": page.figure_intent,
            "renders_structure": page.renders_structure,
            "structure_text": page.structure_text,
            "structure_segments": list(page.structure_segments),
            "provenance": page.provenance,
            "claims": [claim_index[claim_id].model_dump() for claim_id in page.claim_ids if claim_id in claim_index],
            "relationships": [relationship_index[relationship_id].model_dump() for relationship_id in page.relationship_ids if relationship_id in relationship_index],
        } for page in project.pages],
        "audit_log": project.audit_log,
        "exported_at": now(),
    }


def attach_relationships_to_pages(pages: list["PageSpec"], project: Project) -> list["PageSpec"]:
    """Place each approved Relationship on the page that holds both of its endpoints.

    Nothing is inferred here: a relationship is *placed*, not created. Without this step an
    approved relationship never reached a page, so the flow layout (which draws named
    connectors only for a page's own relationships) was unreachable and every page rendered as
    independent boxes even after the semantic graph had edges.
    """
    for page in pages:
        owned = set(page.claim_ids)
        page.relationship_ids = [relationship.id for relationship in project.relationships
                                 if relationship.from_claim_id in owned
                                 and relationship.to_claim_id in owned]
    return pages


def semantic_deck(project: Project) -> dict:
    verification = _require_current_verification(project, "Semantic deck export")
    compliance_result = compliance(project)
    if verification["status"] != "PASS" or compliance_result["status"] != "PASS":
        raise HTTPException(409, "Semantic deck export requires PASS verification and compliance gates")
    stale_pages = [page.id for page in project.pages if page.revision_status == "STALE"]
    if stale_pages:
        raise HTTPException(409, f"Semantic deck export requires rebuilding stale pages after an immutable Claim revision: {stale_pages}")
    if project.visual_contracts:
        stale_contracts = [contract["visual_generation_contract_id"] for contract in project.visual_contracts if contract.get("stale")]
        if stale_contracts:
            raise HTTPException(409, f"Semantic deck export requires rerouting after a material renderer capability change: {stale_contracts}")
        missing_executions = missing_generation_execution_components(project)
        if missing_executions:
            raise HTTPException(409, f"Semantic deck export requires current Generation Execution Provenance for every routed component: {missing_executions}")
        latest_visual_qa = {item.get("visual_generation_contract_id"): item for item in project.generated_visual_verifications if not item.get("stale")}
        missing_or_failed = [contract["visual_generation_contract_id"] for contract in project.visual_contracts if latest_visual_qa.get(contract["visual_generation_contract_id"], {}).get("status") != "PASS"]
        if missing_or_failed:
            raise HTTPException(409, f"Semantic deck export requires PASS post-generation visual verification for every routed contract: {missing_or_failed}")
    return assemble_semantic_deck(project)


def medical_review_sheet(project: Project) -> dict:
    validation = validate(project)
    verification = _require_current_verification(project, "Review sheet")
    compliance_result = compliance(project)
    conflict_groups: dict[str, list[Claim]] = {}
    for claim in project.claims:
        if claim.conflict_group_id:
            conflict_groups.setdefault(claim.conflict_group_id, []).append(claim)
    numeric_issues = [issue for issue in verification.get("issues", []) if issue.get("type") in {"NUMERICAL_QA", "NUMERICAL_PROVENANCE", "NUMERIC_FIDELITY"}]
    source_issues = [issue for issue in verification.get("issues", []) if issue.get("type") in {"SOURCE_FIDELITY", "MINIMUM_SOURCE_SPAN", "RELATIONSHIP_PROVENANCE"}]
    return {
        "red_claims": [claim for claim in active_claims(project) if claim.risk == "RED"],
        "red_relationships": [relationship for relationship in project.relationships if relationship.risk == "RED"],
        "synthesis_relationships": [relationship for relationship in project.relationships if relationship.provenance == "SYNTHESIS"],
        "numeric_issues": numeric_issues,
        "source_issues": source_issues,
        "conflict_groups": conflict_groups,
        "compliance_issues": compliance_result["issues"],
        "gate_issues": validation["issues"],
        "verification_issues": project.verification_issues,
        "human_overrides": project.human_overrides,
        "violation_records": project.violation_records,
        "audit_log": project.audit_log,
    }


from contextlib import asynccontextmanager as _generation_context
import threading as _generation_threading

@_generation_context
async def _generation_lifespan(application):
    from app.deckflow_api import recover_generation_jobs
    stop = _generation_threading.Event()
    _generation_threading.Thread(target=recover_generation_jobs, args=(stop,), daemon=True, name="factdeck-native-renderer").start()
    try:
        yield
    finally:
        stop.set()

app = FastAPI(title="FactPPTv2", version="2.0.0", lifespan=_generation_lifespan)
from app.deckflow_api import router as deckflow_router
from app.fact57098_api import router as fact57098_router
app.include_router(deckflow_router)      # mainline: facts + A native-vector generation
app.include_router(fact57098_router)     # earlier full-slide image workflow, kept for existing projects
app.mount("/web", StaticFiles(directory=ROOT / "web"), name="web")


@app.get("/")
def home():
    """FactDeck mainline UI (Tabler, MIT; see web/vendor/tabler/VERSIONS.txt)."""
    from fastapi.responses import FileResponse
    return FileResponse(ROOT / "web" / "deck" / "index.html", headers={"Cache-Control": "no-cache"})


@app.post("/api/v2/content/verify", response_model=ContentReport)
def verify_v2_content(package: ContentPackage):
    """Check generic source/claim/slide links without issuing review approval."""
    return verify_content_package(package)


class ReviewerEnrolmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_id: str = Field(min_length=1)
    reviewer_kind: Literal["HUMAN", "QUALIFIED_MODEL"]
    qualification_id: str | None = None
    note: str = ""


class ReviewIssuanceRequest(BaseModel):
    """A decision made out of band, recorded against the subject as it is now.

    `expected_digest` is optional and only ever used to *refuse*: supplying it
    lets the issuer detect that the subject moved while the review was being
    performed, in which case re-review is the remedy and silent re-binding is
    not available.

    Evidence is not a single list, because the verifier cites different things
    by object kind -- an assertion's finding carries its source ids, a slide's
    finding carries its assertion ids. One shared list would have to be wrong
    for one of them, and the resulting `REVIEW_EVIDENCE_MISMATCH` reads like a
    content problem rather than the wiring mistake it is.
    """

    model_config = ConfigDict(extra="forbid")

    package: ContentPackage
    author_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    decision: Literal["APPROVE", "REJECT"]
    rationale: str = Field(min_length=12)
    assertion_ids: list[str] = Field(default_factory=list)
    slide_statement_ids: list[str] = Field(default_factory=list)
    expected_digest: str | None = None

    @model_validator(mode="after")
    def at_least_one_object(self):
        if not self.assertion_ids and not self.slide_statement_ids:
            raise ValueError("no object ids were supplied to review")
        return self


@app.get("/api/v2/reviewers")
def list_enrolled_reviewers():
    """Reviewer identities stay private until authenticated team access exists."""
    raise HTTPException(503, "v2 review requires authenticated identity and server-bound sources")


@app.post("/api/v2/reviewers", status_code=201)
def enrol_reviewer_route(request: ReviewerEnrolmentRequest):
    """Registration is unavailable until operator authentication exists."""
    raise HTTPException(503, "v2 review requires authenticated identity and server-bound sources")


@app.post("/api/v2/reviews", response_model=ContentReport)
def issue_review_route(request: ReviewIssuanceRequest):
    """Refuse client-supplied author, reviewer and source trust assertions."""
    raise HTTPException(503, "v2 review requires authenticated identity and server-bound sources")


@app.post("/api/v2/delivery-gate", response_model=DeliveryDecision)
def delivery_gate_route(request: ReviewIssuanceRequest):
    """A client-provided package cannot be its own source of trust."""
    raise HTTPException(503, "v2 delivery requires authenticated review and server-bound sources")


@app.get("/api/projects")
def list_projects():
    return [{"id": p.id, "title": p.title, "question": p.presentation_question} for p in load_projects()]


@app.get("/api/model-adapters")
def available_model_adapters():
    try:
        semantic = configured_semantic_model()
    except SemanticGatewayError as error:
        return {"adapters": list_adapters(), "data_egress_default": "DENY_EXTERNAL",
                "semantic_model_configuration_error": str(error)}
    return {"adapters": list_adapters(semantic), "data_egress_default": "DENY_EXTERNAL",
            "semantic_route": "/api/semantic-model-capabilities",
            "deterministic_default": "local_deterministic"}


@app.get("/api/semantic-model-capabilities")
def inspect_semantic_model_capabilities(project_id: str | None = None):
    """Registered semantic capabilities, their qualification status and egress contract.

    Pass `project_id` to also see whether that project's own declarations would let
    each capability run, and which declaration is missing if not.
    """
    project = None
    if project_id:
        _, project = get_project(project_id)
    return describe_capabilities(project)


@app.get("/api/generation-engines")
def available_generation_engines():
    return generation_engine_registry()


@app.get("/api/agent-capabilities")
def inspect_agent_capabilities():
    return {"capabilities": AGENT_CAPABILITY_MATRIX, "policy_engine_version": "mvp-1"}


@app.get("/api/rules")
def inspect_rule_registry():
    return rule_registry()


@app.get("/api/projects/{project_id}")
def read_project(project_id: str):
    _, project = get_project(project_id)
    return {"project": project, "validation": validate(project), "rules": rule_registry()}


@app.get("/api/projects/{project_id}/policy/{action}")
def inspect_policy_gate(project_id: str, action: Literal["extract", "triage", "architect", "verify", "compliance", "route_visuals"]):
    projects, project = get_project(project_id)
    decision = policy_gate(project, action)
    audit(project, "POLICY_GATE_INSPECTED", json.dumps(decision, ensure_ascii=False))
    save_projects(projects)
    return decision


@app.get("/api/projects/{project_id}/documents/{document_id}/chunks")
def read_source_chunks(project_id: str, document_id: str, page: int | None = None):
    """Read-only source viewer payload; source text never passes through a design agent."""
    _, project = get_project(project_id)
    document = next((item for item in project.documents if item["id"] == document_id), None)
    if document is None:
        raise HTTPException(404, "Document not found")
    chunks = document.get("chunks", [])
    if page is not None:
        chunks = [chunk for chunk in chunks if chunk["page"] == page]
    return {"document": {key: value for key, value in document.items() if key != "chunks"}, "chunks": chunks}


@app.post("/api/projects")
def create_project(request: ProjectCreateRequest):
    """Create an empty project from a minimal, strictly-validated request.

    Controlled containers (claims, pages, relationships, verification
    results, visual contracts, delivery manifests, workflow state) are never
    client-settable at creation time; they can only be produced by the
    pipeline endpoints (upload -> extract -> triage -> architect -> verify).
    """
    projects = load_projects()
    project = Project(
        title=request.title,
        presentation_question=request.presentation_question,
        project_type=request.project_type,
        audience=request.audience,
        duration_minutes=request.duration_minutes,
        language=request.language,
        output_type=request.output_type,
        verification_mode=request.verification_mode,
        synthetic_case=request.synthetic_case,
        workflow_state="CREATED",
    )
    audit(project, "PROJECT_CREATED", "Created through API with a minimal controlled surface")
    projects.append(project)
    save_projects(projects)
    return project


@app.patch("/api/projects/{project_id}/config")
def update_project_config(project_id: str, patch: ProjectConfigPatch):
    projects, project = get_project(project_id)
    changes = patch.model_dump(exclude_none=True)
    for field, value in changes.items():
        setattr(project, field, value)
    semantic_config = {"project_type", "project_goal", "presentation_question", "audience", "duration_minutes", "language", "output_type", "allow_external_sources"}
    if semantic_config & set(changes):
        invalidated = invalidate_verification(project, "Project scope, audience, output, or duration changed; triage and narrative must be regenerated.")
        project.workflow_state = "EXTRACTED" if project.claims else "CREATED"
        audit(project, "SEMANTIC_ARTIFACTS_INVALIDATED", f"Configuration change invalidated {invalidated} verification result(s).")
    audit(project, "PROJECT_CONFIG_UPDATED", json.dumps(changes, ensure_ascii=False))
    save_projects(projects)
    return project


@app.post("/api/projects/{project_id}/validate")
def validate_project(project_id: str):
    projects, project = get_project(project_id)
    result = validate(project)
    for issue in result["issues"]:
        record_violation(project, rule_id=issue.get("rule", "UNSPECIFIED"), severity=issue["severity"], message=issue["message"], action="validate", object_id=issue.get("object"))
    audit(project, "VALIDATION_RUN", f"Result: {result['status']}")
    save_projects(projects)
    return result


@app.post("/api/projects/{project_id}/upload")
async def upload_pdf(project_id: str, file: UploadFile = File(...)):
    if not file.filename or Path(file.filename).suffix.lower() not in {".pdf", ".docx", ".xlsx"}:
        raise HTTPException(400, "Only PDF, DOCX and XLSX uploads are accepted.")
    content = await file.read()
    try:
        extraction = extract_source(file.filename, content)
    except SourceCapacityError as exc:
        raise HTTPException(413, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(422, f"Source text extraction failed: {exc}") from exc
    digest = extraction.source_sha256
    target = DATA / f"{digest}{Path(file.filename).suffix.lower()}"
    chunks = [{"page": excerpt.locator.page if extraction.kind == "PDF" else number,
               "text": excerpt.extracted_text,
               "locator": excerpt.locator.model_dump(exclude_none=True),
               "source_excerpt_id": excerpt.id}
              for number, excerpt in enumerate(extraction.excerpts, 1)]
    target.write_bytes(content)
    projects, project = get_project(project_id)
    document = {"id": f"doc_{digest[:12]}", "filename": file.filename,
                "sha256": digest, "kind": extraction.kind,
                "page_count": extraction.units_total if extraction.kind == "PDF" else len(chunks),
                "chunks": chunks, "extractor_version": extraction.extractor_version,
                "coverage_status": extraction.status, "coverage_issues": extraction.issues,
                "units_total": extraction.units_total,
                "units_extracted": extraction.units_extracted, "uploaded_at": now()}
    project.documents.append(document)
    project.workflow_state = "UPLOADED"
    audit(project, "SOURCE_IMPORTED", f"{file.filename}; sha256={digest}; units={extraction.units_total}; coverage={extraction.status}")
    save_projects(projects)
    return {"document": {k: v for k, v in document.items() if k != "chunks"}, "source_chunks": chunks}


@app.post("/api/projects/{project_id}/document-text")
def attach_document_text(project_id: str, request: DocumentTextRequest):
    """Attach externally obtained page text to an already-imported document.

    Refused once Claims exist: they were grounded against the text that was there, and
    silently swapping it underneath them would leave quotes pointing at text that never
    supported them. Inject first, then read.
    """
    projects, project = get_project(project_id)
    enforce_policy_gate(projects, project, "extract")
    document = next((item for item in project.documents if item.get("id") == request.document_id), None)
    if document is None:
        raise HTTPException(404, f"Document {request.document_id} is not imported in this project")
    if document.get("kind", "PDF") != "PDF":
        raise HTTPException(422, "Page-text replacement is available only for PDF; Word and Excel require native re-import")
    if project.claims:
        raise HTTPException(409, "Document text must be attached before any Claim is extracted; "
                                 "existing Claims were grounded against the previous text")

    expected = set(range(1, int(document.get("page_count") or 0) + 1))
    provided = [item.page for item in request.pages]
    if len(provided) != len(set(provided)):
        raise HTTPException(422, "Every page must be supplied exactly once")
    if set(provided) != expected:
        missing = sorted(expected - set(provided))
        extra = sorted(set(provided) - expected)
        raise HTTPException(422, f"Page coverage must match the document: missing={missing}, extra={extra}")
    empty = [item.page for item in request.pages if not item.text.strip()]
    if empty:
        raise HTTPException(422, f"Pages supplied without text: {empty}; declare them explicitly instead "
                                 "of leaving the reading to interpret a blank page")

    document["chunks"] = [{"page": item.page, "text": item.text} for item in sorted(request.pages, key=lambda p: p.page)]
    document["coverage_status"] = "NEEDS_REVIEW"
    document["coverage_issues"] = ["EXTERNAL_TEXT_NOT_BOUND_TO_FILE_BYTES"]
    document["text_provenance"] = {**request.text_provenance, "attached_at": now(),
                                   "reviewer": request.reviewer, "rationale": request.rationale}
    project.workflow_state = "UPLOADED"
    audit(project, "DOCUMENT_TEXT_ATTACHED",
          f"{document['id']}: {len(request.pages)} pages of externally obtained text attached "
          f"(provenance={json.dumps(request.text_provenance, ensure_ascii=False)}); "
          f"the document sha256 is unchanged: {document.get('sha256', '')[:16]}")
    save_projects(projects)
    return {"document_id": document["id"], "sha256": document.get("sha256"),
            "pages": len(request.pages),
            "chars": sum(len(item.text) for item in request.pages),
            "text_provenance": document["text_provenance"]}


# ------------------------------------------------------ semantic-act model route
#: The application's own visual vocabulary stays here, not in the model. The model
#: declares the material-agnostic `figure_intent` that page allocation decided; the
#: mapping onto the app's visual types is code.
FIGURE_INTENT_VISUALS = {
    "COMPARISON": "EVIDENCE_MAP",
    "DATA": "EVIDENCE_MATRIX",
    "PROCESS": "CLINICAL_DECISION_MAP",
    "PROGRESSION": "CLINICAL_DECISION_MAP",
    "CAUSAL": "CONCEPTUAL_FRAMEWORK",
    "TAXONOMY": "CONCEPTUAL_FRAMEWORK",
    "SCALE": "EVIDENCE_MAP",
    "QUOTATION": "EVIDENCE_MAP",
    "NONE": "EVIDENCE_MAP",
}
TRIAGE_BUCKETS = {"MUST_INCLUDE", "SHOULD_INCLUDE", "APPENDIX", "EXCLUDED"}


def _grounding_key(text: str) -> str:
    """Whitespace-insensitive form used to prove a quote really occurs in the page."""
    return re.sub(r"\s+", "", text or "")


def quote_occurs_in(quote: str, page_text: str) -> bool:
    """One containment rule for both acceptance and verification.

    The reader accepts a quote whose whitespace-normalised form occurs in the page
    (PDF extraction re-wraps lines, so a verbatim quote rarely survives byte-for-byte).
    The verifier used to require literal containment instead, so a quote the reader had
    just proved grounded was then blocked as fabricated. Both sides now use this.
    """
    if not quote:
        return False
    key = _grounding_key(quote)
    return bool(key) and key in _grounding_key(page_text)


def quote_offsets(quote: str, page_text: str) -> tuple[int, int] | None:
    """Find the exact character region despite whitespace reflow in a PDF extract."""
    indices = [index for index, character in enumerate(page_text) if not character.isspace()]
    compact = "".join(page_text[index] for index in indices)
    key = _grounding_key(quote)
    found = compact.find(key) if key else -1
    if found < 0:
        return None
    return indices[found], indices[found + len(key) - 1] + 1


def resolve_semantic_route(project: Project, capability: str) -> dict | None:
    """Resolve the model route for a semantic act, or None when none is configured.

    A configured endpoint that is unqualified or not permitted is a REFUSAL, not a
    reason to quietly use the rule engine: the operator asked for the model, and a
    silent downgrade would erase the refusal from the audit trail.
    """
    model = configured_semantic_model()
    if model is None:
        return None
    try:
        plan = egress_plan(project, capability, model)
        engine_id, _ = qualified_engine(capability, engine_id=model.get("engine_id"))
    except SemanticGatewayError as error:
        raise HTTPException(422, f"Semantic model route refused for {capability}: {error}") from error
    return {"model": model, "adapter": semantic_adapter(model), "egress": plan,
            "engine_id": engine_id, "prompt_version": f"{engine_id}:{capability}:v0.1"}


#: Per-call ceiling on an offered reading. Exceeding it is refused, not trimmed.
MODEL_READING_CANDIDATE_CAP = 2000


def extract_candidates_with_model(project: Project, document_id: str,
                                  route: dict) -> tuple[list[Claim], dict]:
    """M1 reading, done by the model, grounded by code.

    The model only says WHAT the source states and proves it with a verbatim quote.
    Risk, numeric facts, conditions, ids and provenance are derived here, so a model
    that misjudges severity cannot change them, and a model that invents a sentence
    cannot pass the quote check.
    """
    document = next((d for d in project.documents if d["id"] == document_id), None)
    if document is None:
        raise HTTPException(404, "Document not found in project")
    require_complete_source_extraction(document)
    pages = [{"document_id": document_id, "page": chunk["page"], "text": chunk.get("text", "")}
             for chunk in document.get("chunks", [])]
    if not pages:
        raise HTTPException(422, "Document has no extracted page text to read")
    payload = build_payload("source_candidate_extraction", {"pages": pages})
    if payload_fingerprint(payload)["payload_bytes"] > 1_000_000:
        raise HTTPException(413, "Model reading exceeds the 1 MB request limit; split the source into smaller files")
    with ensure_job("semantic:source_candidate_extraction", meta={"project_id": project.id}), job_stage("source_candidate_extraction"):
        answer = call_semantic_model("source_candidate_extraction", payload, route["model"])
    offered = answer.get("candidates")
    if not isinstance(offered, list):
        raise HTTPException(422, "Model reading did not return a candidate list")
    page_text = {page["page"]: page["text"] for page in pages}
    claims: list[Claim] = []
    rejected: list[dict] = []
    # A cap exists so one malformed answer cannot exhaust memory, but exceeding it is FATAL, never a
    # silent trim. Cutting the list quietly dropped 183 of 383 candidates once, and the completeness
    # audit then reported the missing quotes as paragraphs the *reading* had failed to account for --
    # the code discarded the evidence and blamed the reading. Worse, the broader the reading, the
    # more it lost, so reading more carefully made the report look worse.
    if len(offered) > MODEL_READING_CANDIDATE_CAP:
        raise HTTPException(422, {
            "message": f"The reading offered {len(offered)} candidates; this application accepts at "
                       f"most {MODEL_READING_CANDIDATE_CAP} in one call. Split the reading into parts "
                       "rather than having evidence dropped and then reported as unread paragraphs.",
            "offered": len(offered), "cap": MODEL_READING_CANDIDATE_CAP})
    for item in offered:
        if not isinstance(item, dict):
            rejected.append({"reason": "candidate is not an object"})
            continue
        page = item.get("page")
        quote = str(item.get("quote") or "").strip()
        statement = str(item.get("claim") or "").strip()
        if not isinstance(page, int) or page not in page_text:
            rejected.append({"reason": "unknown page", "page": page})
            continue
        if not quote or not quote_occurs_in(quote, page_text[page]):
            rejected.append({"reason": "quote is not in the cited page text", "page": page})
            continue
        if len(statement) < 8:
            rejected.append({"reason": "assertion too short to be a claim", "page": page})
            continue
        source_chunk = next((chunk for chunk in document.get("chunks", [])
                             if chunk.get("page") == page), None)
        locator = dict(source_chunk.get("locator") or {}) if source_chunk else {}
        if locator.get("kind") == "PDF":
            offsets = quote_offsets(quote, page_text[page])
            if offsets:
                base = int(locator.get("start") or 0)
                locator["start"], locator["end"] = base + offsets[0], base + offsets[1]
        claims.append(Claim(
            normalized_claim=statement,
            source_quote=quote,
            provenance="SOURCE",
            risk=infer_risk(statement),
            source_refs=[SourceRef(document_id=document_id, page=page, quote=quote,
                                   locator=locator or None)],
            # No condition is fabricated here. `conditions` is a meaning-preserving bundle,
            # and inventing "confirm population, timeframe and exclusions" made every RED
            # Claim satisfy the MEANING_BUNDLE gate with a placeholder while rendering that
            # placeholder onto the slide as if it were a clinical condition. Leaving it empty
            # lets the existing rule block a RED Claim until the reviewer supplies the real
            # bundle through the documented binding channel.
            conditions=[],
            numeric_facts=extract_numeric_facts(statement),
            triage="SHOULD_INCLUDE",
            review_status="NEEDS_HUMAN_REVIEW",
        ))
    if not claims:
        raise HTTPException(422, "Model reading produced no quote-grounded candidate; "
                                 "nothing was written to the Claim Table")
    audit_result = audit_read_receipts(
        units=classify_units(pages, overrides=read_unit_overrides(project)),
        receipts=answer.get("units"), claims=claims)
    if audit_result["status"] != "PASS":
        raise HTTPException(422, {
            "message": "The reading did not account for every source unit and every "
                       "meaning-critical value; nothing was written to the Claim Table. "
                       "Cover each listed unit/value, or exclude it with a stated reason.",
            "read_completeness": audit_result["statistics"], "issues": audit_result["issues"][:40]})
    return claims, {"payload": payload_fingerprint(payload), "candidates_offered": len(offered),
                    "accepted": len(claims), "rejected": rejected[:20],
                    "read_completeness": audit_result["statistics"]}


def read_unit_overrides(project: Project) -> dict[int, str]:
    """The reviewer's latest classification decision per source unit, if any.

    Last decision wins, so a reviewer can change their mind; every decision stays in
    `read_unit_reviews` and in the audit log, so the earlier judgement is still readable.
    """
    overrides: dict[int, str] = {}
    for review in project.read_unit_reviews:
        page = review.get("page")
        if isinstance(page, int) and review.get("decision") in CLASSIFICATIONS:
            overrides[page] = review["decision"]
    return overrides


def record_read_unit_review(project: Project, request: "ReadUnitReviewRequest") -> dict:
    """Record a reviewer's disagreement with the code-owned unit classification."""
    before = next((unit for unit in classify_units(project.documents[-1].get("chunks", []),
                                                   overrides=read_unit_overrides(project))
                   if unit["page"] == request.page), None)
    if before is None and project.documents:
        before = next((unit for unit in classify_units(project.documents[-1].get("chunks", []))
                       if unit["page"] == request.page), None)
    if before is None:
        raise HTTPException(404, f"Source unit {request.page} is not in the imported document")
    event = {
        "review_id": f"rur_{uuid.uuid4().hex[:8]}",
        "page": request.page,
        "computed_classification": before["computed_classification"],
        "previous_classification": before["classification"],
        "decision": request.decision,
        "reviewer": request.reviewer,
        "rationale": request.rationale,
        "rule_version": before["rule_version"],
        "signals": before["signals"],
        "created_at": now(),
    }
    project.read_unit_reviews.append(event)
    return event


def triage_measure(project: Project, claim: Claim) -> dict:
    """Deterministic scoring and budget cost. The model chooses buckets, never budget."""
    question_terms = terms(project.presentation_question)
    goal_terms = terms(project.project_goal)
    profile = audience_profile(project.audience)
    overlap = len(question_terms & terms(claim.normalized_claim))
    goal_overlap = len(goal_terms & terms(claim.normalized_claim))
    fit = audience_fit(claim, profile)
    score = min(100, 28 + overlap * 18 + min(12, goal_overlap * 4) + min(18, fit * 6) + (12 if claim.provenance == "SOURCE" else 0))
    # RED is a constraint on review and rendering, not an automatic reason to
    # consume the main narrative budget.
    cost = 70 + min(40, len(claim.conditions) * 12) + (20 if claim.numeric_facts else 0) + (20 if claim.risk == "RED" else 0)
    return {"overlap": overlap, "goal_overlap": goal_overlap, "profile": profile,
            "audience_fit": fit, "score": score, "cost": cost}


def triage_with_model(project: Project, route: dict) -> tuple[list[TriageDecision], dict]:
    """M2 selection by the model; coverage, buckets and budget stay code-owned."""
    eligible = active_claims(project)
    claims = [{"claim_id": claim.id, "claim_text": claim.normalized_claim,
               "provenance": claim.provenance, "risk": claim.risk, "conditions": claim.conditions}
              for claim in eligible]
    payload = build_payload("triage", {"presentation_question": project.presentation_question,
                                       "audience": project.audience,
                                       "duration_minutes": project.duration_minutes,
                                       "claims": claims})
    with ensure_job("semantic:triage", meta={"project_id": project.id}), job_stage("triage"):
        answer = call_semantic_model("triage", payload, route["model"])
    proposed = answer.get("decisions")
    if not isinstance(proposed, list):
        raise HTTPException(422, "Model triage did not return a decision list")
    by_id: dict[str, dict] = {}
    for item in proposed:
        if not isinstance(item, dict):
            continue
        claim_id = str(item.get("claim_id") or "")
        if claim_id in by_id:
            raise HTTPException(422, f"Model triage decided claim {claim_id} more than once")
        by_id[claim_id] = item
    expected = {claim.id for claim in eligible}
    missing = sorted(expected - set(by_id))
    unknown = sorted(set(by_id) - expected)
    if missing or unknown:
        raise HTTPException(422, f"Model triage must decide every Claim exactly once; "
                                 f"missing={missing[:5]}, unknown={unknown[:5]}")
    decisions: list[TriageDecision] = []
    for claim in eligible:
        item = by_id[claim.id]
        bucket = item.get("bucket")
        if bucket not in TRIAGE_BUCKETS:
            raise HTTPException(422, f"Model triage returned an unknown bucket for {claim.id}: {bucket}")
        measure = triage_measure(project, claim)
        reason = (f"[model] {str(item.get('reason') or '').strip()[:400]} | question_overlap={measure['overlap']}; "
                  f"goal_overlap={measure['goal_overlap']}; project_type={project.project_type}; "
                  f"audience_profile={measure['profile']}; audience_fit={measure['audience_fit']}; "
                  f"risk={claim.risk}; provenance={claim.provenance}; estimated_cost={measure['cost']}s.")
        claim.triage = bucket
        decisions.append(TriageDecision(claim_id=claim.id, bucket=bucket, score=measure["score"],
                                        reason=reason, meaning_preserving_bundle=claim.conditions,
                                        presentation_cost_seconds=measure["cost"]))
    return decisions, {"payload": payload_fingerprint(payload), "decisions": len(decisions)}


def architect_with_model(project: Project, route: dict) -> tuple[NarrativePlan, list[PageSpec], dict]:
    """M3 narrative + M4 allocation by the model; capacity, coverage and order by code."""
    selected = [claim for claim in active_claims(project) if claim.triage in ("MUST_INCLUDE", "SHOULD_INCLUDE")]
    if not selected:
        raise HTTPException(422, "No triaged claims are eligible for a narrative")
    by_id = {claim.id: claim for claim in selected}
    payload = build_payload("architect", {
        "presentation_question": project.presentation_question, "audience": project.audience,
        "duration_minutes": project.duration_minutes,
        "claims": [{"claim_id": claim.id, "claim_text": claim.normalized_claim, "bucket": claim.triage,
                    "conditions": claim.conditions, "provenance": claim.provenance, "risk": claim.risk}
                   for claim in selected]})
    with ensure_job("semantic:architect", meta={"project_id": project.id}), job_stage("architect"):
        answer = call_semantic_model("architect", payload, route["model"])
    spine = str(answer.get("narrative_spine") or "").strip()
    proposed = answer.get("pages")
    if not spine:
        raise HTTPException(422, "Model narrative must state a narrative_spine")
    if not isinstance(proposed, list) or not proposed:
        raise HTTPException(422, "Model narrative did not allocate any page")
    pages: list[PageSpec] = []
    used: list[str] = []
    for index, item in enumerate(proposed, start=1):
        if not isinstance(item, dict):
            raise HTTPException(422, "Model page allocation must be a list of objects")
        claim_ids = [str(value) for value in (item.get("claim_ids") or [])]
        if not claim_ids:
            raise HTTPException(422, f"Model page {index} allocates no Claim")
        if len(claim_ids) > 4:
            raise HTTPException(422, f"Model page {index} exceeds the controlled renderer capacity of four Claims")
        for claim_id in claim_ids:
            if claim_id not in by_id:
                raise HTTPException(422, f"Model page {index} references an unauthorised Claim {claim_id}")
        intent = item.get("figure_intent")
        if intent not in FIGURE_INTENT_VISUALS:
            raise HTTPException(422, f"Model page {index} declares an unknown figure_intent: {intent}")
        why = str(item.get("why_this_page") or "").strip()
        title = str(item.get("title") or "").strip()
        message = str(item.get("primary_message") or "").strip()
        if not why or not title or not message:
            raise HTTPException(422, f"Model page {index} must declare why_this_page, title and primary_message")
        provenance: Provenance = by_id[claim_ids[0]].provenance if len(claim_ids) == 1 else "SYNTHESIS"
        pages.append(PageSpec(id=f"pg_{uuid.uuid4().hex[:8]}", title=title, primary_message=message,
                              visual_type=FIGURE_INTENT_VISUALS[intent], claim_ids=claim_ids,
                              provenance=provenance, figure_intent=intent,
                              goal=f"{why}｜figure_intent={intent}"))
        used.extend(claim_ids)
    duplicates = sorted({claim_id for claim_id in used if used.count(claim_id) > 1})
    dropped = sorted(set(by_id) - set(used))
    if duplicates or dropped:
        raise HTTPException(422, f"Model allocation must use every eligible Claim exactly once; "
                                 f"duplicated={duplicates[:5]}, dropped={dropped[:5]}")
    sections: list[dict] = []
    for page in pages:
        if sections and sections[-1]["title"] == page.visual_type.replace("_", " ").title():
            sections[-1]["page_ids"].append(page.id)
            if page.provenance == "SYNTHESIS":
                sections[-1]["provenance"] = "SYNTHESIS"
        else:
            sections.append({"order": len(sections) + 1, "title": page.visual_type.replace("_", " ").title(),
                             "page_ids": [page.id], "provenance": page.provenance})
    plan = NarrativePlan(narrative_spine=spine, provenance="SYNTHESIS",
                         audience_strategy=f"model_narrative; project_type={project.project_type}; "
                                           f"source-faithful claim content unchanged",
                         sections=sections, generated_at=now())
    return plan, pages, {"payload": payload_fingerprint(payload), "pages": len(pages),
                         "narrative_spine": spine}


@app.post("/api/projects/{project_id}/extract")
def extract_project_claims(project_id: str, request: PipelineRequest):
    projects, project = get_project(project_id)
    enforce_policy_gate(projects, project, "extract")
    enforce_agent_write(project, "source_extractor", "claims")
    document_id = request.document_id or (project.documents[-1]["id"] if project.documents else None)
    if not document_id:
        raise HTTPException(422, "Import a PDF, Word or Excel source before extraction")
    document = next((item for item in project.documents if item.get("id") == document_id), None)
    if document is None:
        raise HTTPException(404, "Document not found in project")
    require_complete_source_extraction(document)
    if project.claims:
        # A re-read replaces the evidence the whole deck rests on. The recorded verification and the
        # pages built from the previous reading must not survive it as if still current.
        invalidated = invalidate_verification(project, "The source was re-read; the recorded verification describes the previous Claim Table.")
        project.pages = []
        project.workflow_state = "UPLOADED"
        audit(project, "REREAD_INVALIDATED_DERIVED_ARTIFACTS",
              f"Re-reading invalidated {invalidated} verification result(s) and cleared the pages built from the previous reading.")
    route = resolve_semantic_route(project, "source_candidate_extraction")
    reading_meta: dict = {"engine": "local_deterministic"}
    if route is None:
        candidates = source_extractor(project, document_id)
        adapter_used, prompt_version, egress = LOCAL_DETERMINISTIC_ADAPTER, "deterministic-v0.1", None
    else:
        candidates, reading_meta = extract_candidates_with_model(project, document_id, route)
        reading_meta["engine"] = route["engine_id"]
        adapter_used, prompt_version, egress = route["adapter"], route["prompt_version"], route["egress"]
    existing_quotes = {(claim.source_refs[0].document_id, claim.source_refs[0].page, claim.source_quote) for claim in project.claims if claim.source_refs and claim.source_quote}
    accepted = [claim for claim in candidates if (claim.source_refs[0].document_id, claim.source_refs[0].page, claim.source_quote) not in existing_quotes]
    project.claims.extend(accepted)
    canonical_result = canonicalize_claims(project.claims)
    project.workflow_state = "EXTRACTED"
    project.model_runs.append(record_run("source_extractor", {"document_id": document_id, "chunks": len(next(d for d in project.documents if d["id"] == document_id).get("chunks", []))}, {"claim_ids": [claim.id for claim in accepted], "reading": reading_meta}, adapter=adapter_used, prompt_version=prompt_version, egress=egress))
    audit(project, "SOURCE_EXTRACTOR_RUN", f"Created {len(accepted)} atomic SOURCE claim candidates from {document_id} via {reading_meta['engine']}; no relationships generated; canonical groups={canonical_result['canonical_groups']}, conflicts={canonical_result['conflict_groups']}.")
    save_projects(projects)
    return {"created_claims": accepted, "count": len(accepted), "canonicalization": canonical_result,
            "reading": reading_meta, "workflow_state": project.workflow_state}


@app.post("/api/projects/{project_id}/triage")
def run_triage(project_id: str):
    projects, project = get_project(project_id)
    enforce_policy_gate(projects, project, "triage")
    enforce_agent_write(project, "information_triage", "triage_decisions")
    route = resolve_semantic_route(project, "triage")
    triage_meta: dict = {"engine": "local_deterministic"}
    previous_overrides = preserved_triage_overrides(project)
    if route is None:
        project.triage_decisions = triage_claims(project)
        adapter_used, prompt_version, egress = LOCAL_DETERMINISTIC_ADAPTER, "deterministic-v0.1", None
    else:
        project.triage_decisions, triage_meta = triage_with_model(project, route)
        triage_meta["engine"] = route["engine_id"]
        adapter_used, prompt_version, egress = route["adapter"], route["prompt_version"], route["egress"]
    preserved = apply_triage_overrides(project, previous_overrides)
    triage_meta["preserved_overrides"] = preserved
    duration = duration_assessment(project, project.triage_decisions)
    project.workflow_state = "NEEDS_USER_INPUT" if duration["needs_user_input"] else "TRIAGED"
    project.model_runs.append(record_run("information_triage", {"question": project.presentation_question, "claim_ids": [claim.id for claim in project.claims]}, {"decisions": [decision.model_dump() for decision in project.triage_decisions], "triage": triage_meta}, adapter=adapter_used, prompt_version=prompt_version, egress=egress))
    audit(project, "TRIAGE_RUN", f"Triaged {len(project.triage_decisions)} claims against Presentation Question via {triage_meta['engine']}; must_include_seconds={duration['must_include_seconds']}; capacity_seconds={duration['capacity_seconds']}; preserved_overrides={len(preserved)}.")
    save_projects(projects)
    return {"decisions": project.triage_decisions, "duration_assessment": duration,
            "triage": triage_meta, "workflow_state": project.workflow_state,
            "preserved_override_claim_ids": preserved}


@app.post("/api/projects/{project_id}/triage/{claim_id}/override")
def override_project_triage(project_id: str, claim_id: str, request: TriageOverrideRequest):
    projects, project = get_project(project_id)
    event = override_triage_decision(project, claim_id, request)
    audit(project, "TRIAGE_DECISION_OVERRIDDEN", json.dumps(event, ensure_ascii=False))
    save_projects(projects)
    return event


def architect_from_reading_structure(project: Project) -> tuple[NarrativePlan, list[PageSpec], dict]:
    """M4 allocation taken from the accepted reading artifact instead of re-derived.

    The artifact already decided the narrative order, the page set, each page's reason
    and its figure intent. Re-deciding any of that here would produce a second, silent
    narrative, so this path only *maps* the artifact onto approved Claims and refuses
    to invent pages. Anything the reading reached but the Claim Table does not cover is
    reported as a gap; nothing is dropped quietly.
    """
    artifact = project.reading_structure or {}
    join = join_pages_to_claims(artifact, project)
    if join["document_id"] is None:
        raise HTTPException(422, join["gaps"][0]["message"])
    narrative = artifact.get("narrative") or {}
    node_ids = [str(node.get("node_id")) for node in (artifact.get("structure") or {}).get("nodes") or []]
    pages: list[PageSpec] = []
    skipped: list[dict] = []
    split: list[dict] = []
    structure_pages: list[str] = []
    existing_ids = {page.reading_page_id: page.id for page in project.pages
                    if page.reading_page_id}
    for entry in join["pages"]:
        renders = entry["renders_structure"]
        if not entry["claim_ids"]:
            if renders in STRUCTURE_RENDERING_KINDS:
                if not str(entry.get("structure_text") or "").strip() and not any(
                        str(item).strip() for item in (entry.get("structure_segments") or [])):
                    raise HTTPException(422, f"Reading page {entry['page_id']} renders {renders} "
                                             "without audience-facing structure content")
                # The reading asked for a page that shows the argument's shape. Dropping it is
                # what left every delivered deck without a visible throughline: the thread was
                # in the artifact and had no page to live on.
                pages.append(PageSpec(
                    id=existing_ids.get(entry["page_id"], f"pg_{uuid.uuid4().hex[:8]}"),
                    title=str(entry.get("action_title") or entry.get("why_this_page") or "本章主线"),
                    primary_message=str(entry.get("primary_message") or entry.get("why_this_page") or ""),
                    visual_type="EVIDENCE_MAP", claim_ids=[], provenance="SYNTHESIS",
                    goal=f"{entry.get('why_this_page') or ''}｜renders_structure={renders}",
                    figure_intent=entry.get("figure_intent") or "NONE",
                    renders_structure=renders,
                    structure_text=entry.get("structure_text"),
                    structure_segments=list(entry.get("structure_segments") or []),
                    reading_page_id=entry["page_id"],
                    narrative_node_ids=[n for n in entry["narrative_node_ids"] if n in node_ids]))
                structure_pages.append(entry["page_id"])
                continue
            skipped.append({"reading_page_id": entry["page_id"], "renders_structure": renders,
                            "reason": "no approved Claim covers this page's source blocks",
                            "source_units": entry["source_units"]})
            continue
        intent = entry["figure_intent"]
        if intent not in FIGURE_INTENT_VISUALS:
            raise HTTPException(422, f"Reading page {entry['page_id']} declares an unknown "
                                     f"figure_intent: {intent}")
        nodes = [node_id for node_id in entry["narrative_node_ids"] if node_id in node_ids]
        # The artifact allocates source content to a page; the controlled renderer holds four
        # Claims per slide. When one source page yields more approved Claims than that, the
        # page is rendered as consecutive slides -- the app's documented remedy -- rather than
        # refused or silently trimmed. The split is recorded, not hidden.
        chunks = [entry["claim_ids"][index:index + 4] for index in range(0, len(entry["claim_ids"]), 4)]
        if len(chunks) > 1:
            split.append({"reading_page_id": entry["page_id"], "parts": len(chunks),
                          "claims": len(entry["claim_ids"])})
        for part, chunk in enumerate(chunks, start=1):
            reading_page_id = entry["page_id"] if part == 1 else f"{entry['page_id']}#{part}"
            provenance: Provenance = "SOURCE" if len(chunk) == 1 else "SYNTHESIS"
            title = (entry["action_title"] or entry["why_this_page"] or entry["page_id"]).strip()
            if len(chunks) > 1:
                title = f"{title}（{part}/{len(chunks)}）"
            # An artifact page may declare the audience-facing subtitle. When it does, use it --
            # `why_this_page` is the reading's reason for the page existing, and rendering that as a
            # subtitle shows the audience a production note. The fallback stays only so artifacts
            # authored before this field existed still build; new artifacts should declare it.
            message = (str(entry.get("primary_message") or "").strip()
                       or (entry["on_slide_text"][0] if entry["on_slide_text"] else "")
                       or entry["why_this_page"]).strip()
            pages.append(PageSpec(
                id=existing_ids.get(reading_page_id, f"pg_{uuid.uuid4().hex[:8]}"),
                title=title[:160], primary_message=message,
                visual_type=FIGURE_INTENT_VISUALS[intent], claim_ids=chunk, provenance=provenance,
                goal=f"{entry['why_this_page']}｜figure_intent={intent}",
                figure_intent=intent,
                reading_page_id=reading_page_id,
                narrative_node_ids=nodes,
                source_block_ids=[value for value in entry["source_block_ids"] if isinstance(value, int)]))
    if not pages:
        raise HTTPException(422, "The reading artifact's pages map to no approved Claim; run Extract and "
                                 "Triage against the same source document first")
    sections: list[dict] = []
    for page in pages:
        label = page.visual_type.replace("_", " ").title()
        if sections and sections[-1]["title"] == label:
            sections[-1]["page_ids"].append(page.id)
            if page.provenance == "SYNTHESIS":
                sections[-1]["provenance"] = "SYNTHESIS"
        else:
            sections.append({"order": len(sections) + 1, "title": label, "page_ids": [page.id],
                             "provenance": page.provenance, "narrative_node_ids": page.narrative_node_ids})
    spine = str((artifact.get("structure") or {}).get("thread") or "").strip()
    plan = NarrativePlan(
        narrative_spine=spine, provenance="SYNTHESIS",
        audience_strategy=f"reading_artifact:{project.reading_structure_sha256[:12]}; "
                          f"audience_question={narrative.get('audience_question', '')}; "
                          f"differs_from_source_order={narrative.get('differs_from_source_order')}; "
                          f"difference_reason={narrative.get('difference_reason', '')}",
        sections=sections, generated_at=now())
    meta = {"engine": "reading_structure_artifact", "reading_structure_sha256": project.reading_structure_sha256,
            "artifact_summary": summarize_reading(artifact), "join": join["join"],
            "allocation_gaps": join["gaps"] + skipped, "capacity_splits": split,
            "narrative_order": narrative.get("narrative_order") or []}
    return plan, pages, meta


class ReadingStructureRequest(BaseModel):
    """An accepted reading artifact produced outside this application."""
    artifact: dict


@app.post("/api/projects/{project_id}/reading-structure")
def register_reading_structure(project_id: str, request: ReadingStructureRequest):
    """Attach an accepted reading artifact. Refuses to accept one that fails its own gate.

    This is an import, not a model call: the reading happened outside this application,
    and the artifact carries its own audit record (reading_pass, structure, narrative,
    checks, profile). Attaching it — and digesting it into the delivery snapshot — is
    what makes the deck's order traceable to a declared narrative.
    """
    projects, project = get_project(project_id)
    enforce_policy_gate(projects, project, "reading_structure")
    enforce_agent_write(project, "reading_structure_import", "reading_structure")
    artifact = request.artifact
    issues = validate_reading_structure(artifact)
    if issues:
        raise HTTPException(422, "Reading artifact failed its gate: "
                                 + "; ".join(f"{item['code']}({item['rule']})" for item in issues[:8]))
    source_sha = (artifact.get("source") or {}).get("sha256")
    if source_sha and not any(item.get("sha256") == source_sha for item in project.documents):
        raise HTTPException(422, "No imported document matches the reading artifact's source sha256; "
                                 "import that document before attaching its reading")
    changed_narrative = bool(project.reading_structure_sha256) and project.reading_structure_sha256 != artifact_digest(artifact)
    if changed_narrative:
        project.pages = [page.model_copy(update={"revision_status": "STALE"}) for page in project.pages]
        project.full_summary = None
        project.full_summary_sha256 = None
    project.reading_structure = artifact
    project.reading_structure_sha256 = artifact_digest(artifact)
    if changed_narrative:
        # Swapping the narrative must not leave a recorded PASS describing the deck built from
        # the previous one. The pages are already stale; the verification has to go with them.
        invalidated = invalidate_verification(
            project, "A different reading artifact was attached; the recorded verification describes the previous narrative.")
        # The narrative changed, so the deck has to be rebuilt -- but a project whose Claims are
        # already triaged is TRIAGED, not EXTRACTED: EXTRACTED would block `architect` and leave the
        # rebuild unreachable, which is the dead end this line created.
        project.workflow_state = ("ARCHITECTED" if project.pages
                                  else "TRIAGED" if project.triage_decisions else "EXTRACTED")
        audit(project, "READING_STRUCTURE_SWAP_INVALIDATED_VERIFICATION",
              f"Attaching a new reading artifact invalidated {invalidated} verification result(s).")
    join = join_pages_to_claims(artifact, project) if source_sha else {"join": {}, "gaps": []}
    # REG-READ-018: record whether this reading was bound to a run, so the project's own audit
    # states it instead of a later reader inferring freshness from the artifact's presence.
    freshness = summarize_reading(artifact).get("executed_for_run") or "NOT_ESTABLISHED"
    audit(project, "READING_STRUCTURE_REGISTERED",
          f"sha256={project.reading_structure_sha256[:16]}; disposition={(artifact.get('disposition'))}; "
          f"blocks={summarize_reading(artifact).get('blocks_read')}/{summarize_reading(artifact).get('blocks_total')}; "
          f"read_freshness={freshness}; "
          f"join={json.dumps(join['join'], ensure_ascii=False)}; gaps={len(join['gaps'])}")
    save_projects(projects)
    return {"reading_structure_sha256": project.reading_structure_sha256,
            "summary": summarize_reading(artifact), "join": join["join"], "gaps": join["gaps"],
            "workflow_state": project.workflow_state}


class FullSummaryRequest(BaseModel):
    """Model-authored summary of every source page, grounded in the accepted reading."""
    summary: dict


@app.get("/api/projects/{project_id}/full-summary/brief")
def get_full_summary_brief(project_id: str):
    """Reusable, full-source input for a model-authored section summary."""
    _, project = get_project(project_id)
    reading = project.reading_structure
    if not reading:
        raise HTTPException(422, "Attach an accepted full-source reading artifact first")
    source_sha = (reading.get("source") or {}).get("sha256")
    document = next((item for item in project.documents if item.get("sha256") == source_sha), None)
    if document is None:
        raise HTTPException(422, "The reading source is not imported in this project")
    try:
        return full_summary_authoring_brief(reading, document)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/projects/{project_id}/full-summary")
def register_full_summary(project_id: str, request: FullSummaryRequest):
    projects, project = get_project(project_id)
    if not project.reading_structure:
        raise HTTPException(422, "Attach a full-source reading artifact before its summary")
    issues = validate_full_summary(request.summary, project.reading_structure)
    if issues:
        raise HTTPException(422, {"message": "Full-source summary failed its gate", "issues": issues})
    project.full_summary = request.summary
    project.full_summary_sha256 = full_summary_digest(request.summary)
    audit(project, "FULL_SOURCE_SUMMARY_REGISTERED",
          f"sha256={project.full_summary_sha256[:16]}; sections={len(request.summary['sections'])}; "
          f"source_pages={(project.reading_structure.get('source') or {}).get('unit_count')}")
    save_projects(projects)
    return {"status": "ACCEPTED", "full_summary_sha256": project.full_summary_sha256,
            "summary": summary_with_locations(request.summary, project.reading_structure)}


@app.post("/api/projects/{project_id}/full-summary/run")
def run_full_summary(project_id: str):
    """Use a qualified model route for a new full-source summary; never fall back to rules."""
    projects, project = get_project(project_id)
    brief = get_full_summary_brief(project_id)
    route = resolve_semantic_route(project, "full_source_summary")
    if route is None:
        raise HTTPException(422, "Configure a qualified semantic model or submit a model-authored full summary")
    payload = build_payload("full_source_summary", brief)
    try:
        with ensure_job("semantic:full_source_summary", meta={"project_id": project.id}), job_stage("full_source_summary"):
            answer = call_semantic_model("full_source_summary", payload, route["model"])
    except SemanticGatewayError as error:
        raise HTTPException(422, str(error)) from error
    issues = validate_full_summary(answer, project.reading_structure)
    if issues:
        raise HTTPException(422, {"message": "Model-authored full-source summary failed its gate",
                                  "issues": issues, "model_error": answer.get("error")})
    project.full_summary = answer
    project.full_summary_sha256 = full_summary_digest(answer)
    project.model_runs.append({"agent": "full_source_summarizer",
                               "adapter_id": route["model"]["adapter_id"],
                               "engine": route["engine_id"],
                               "external": route["model"]["external"],
                               "egress": route["egress"],
                               **payload_fingerprint(payload),
                               "output_hash": project.full_summary_sha256,
                               "executed_at": now()})
    audit(project, "MODEL_FULL_SOURCE_SUMMARY_ACCEPTED",
          f"sha256={project.full_summary_sha256[:16]}; sections={len(answer['sections'])}; "
          f"source_pages={(project.reading_structure.get('source') or {}).get('unit_count')}")
    save_projects(projects)
    return {"status": "ACCEPTED", "full_summary_sha256": project.full_summary_sha256,
            "summary": summary_with_locations(answer, project.reading_structure)}


@app.get("/api/projects/{project_id}/full-summary")
def get_full_summary(project_id: str):
    _, project = get_project(project_id)
    if not project.full_summary or not project.reading_structure:
        return {"status": "NOT_AVAILABLE"}
    issues = validate_full_summary(project.full_summary, project.reading_structure)
    if issues:
        return {"status": "STALE", "issues": issues}
    return {"status": "ACCEPTED", "full_summary_sha256": project.full_summary_sha256,
            "summary": summary_with_locations(project.full_summary, project.reading_structure)}


@app.post("/api/projects/{project_id}/architect")
def run_architect(project_id: str):
    projects, project = get_project(project_id)
    enforce_policy_gate(projects, project, "architect")
    enforce_agent_write(project, "medical_information_architect", "narrative_plans")
    enforce_agent_write(project, "medical_information_architect", "pages")
    if project.reading_structure:
        plan, pages, narrative_meta = architect_from_reading_structure(project)
        adapter_used, prompt_version, egress = LOCAL_DETERMINISTIC_ADAPTER, "reading-structure-import", None
    else:
        route = resolve_semantic_route(project, "architect")
        narrative_meta = {"engine": "local_deterministic"}
        if route is None:
            plan, pages = architect(project)
            adapter_used, prompt_version, egress = LOCAL_DETERMINISTIC_ADAPTER, "deterministic-v0.1", None
        else:
            plan, pages, narrative_meta = architect_with_model(project, route)
            narrative_meta["engine"] = route["engine_id"]
            adapter_used, prompt_version, egress = route["adapter"], route["prompt_version"], route["egress"]
    attach_relationships_to_pages(pages, project)
    project.narrative_plans.append(plan)
    if project.pages:
        # Replacing the page set makes any recorded verification describe a deck that no
        # longer exists. Leaving it current would let a rebuilt deck inherit a PASS it never
        # earned -- the same reason page reordering invalidates verification.
        invalidated = invalidate_verification(
            project, "Architect rebuilt the page set; the recorded verification describes the previous deck.")
        if invalidated:
            audit(project, "ARCHITECT_REBUILD_INVALIDATED_VERIFICATION",
                  f"Rebuilding the page set invalidated {invalidated} verification result(s).")
    project.pages = pages
    project.workflow_state = "ARCHITECTED"
    project.model_runs.append(record_run("medical_information_architect", {"narrative_spine": project.presentation_question, "triage": [decision.model_dump() for decision in project.triage_decisions]}, {"plan": plan.model_dump(), "page_ids": [page.id for page in pages], "narrative": narrative_meta}, adapter=adapter_used, prompt_version=prompt_version, egress=egress))
    audit(project, "MEDICAL_INFORMATION_ARCHITECT_RUN", f"Generated {len(pages)} PageSpecs via {narrative_meta['engine']}; no Clinical Relationship was created.")
    save_projects(projects)
    return {"narrative_plan": plan, "pages": pages, "narrative": narrative_meta,
            "workflow_state": project.workflow_state}


@app.post("/api/projects/{project_id}/read-unit-review")
def review_read_unit(project_id: str, request: ReadUnitReviewRequest):
    """Disagree with the code-owned source-unit classification, on the record.

    `read_unit_classifier.v1` is a rule and will sometimes be wrong about a page. The
    reviewer needs a way to say so that is auditable and does not silently rewrite what an
    earlier run was judged against.
    """
    projects, project = get_project(project_id)
    enforce_agent_write(project, "read_unit_reviewer", "read_unit_reviews")
    event = record_read_unit_review(project, request)
    audit(project, "READ_UNIT_CLASSIFICATION_REVIEWED",
          f"Unit {request.page}: computed={event['computed_classification']} "
          f"-> decision={request.decision} by {request.reviewer}.")
    invalidated = invalidate_verification(
        project, f"Source-unit classification for unit {request.page} changed; the reading must be re-audited.")
    event["invalidated_verification_results"] = invalidated
    save_projects(projects)
    return event


@app.post("/api/projects/{project_id}/relationships")
def register_relationship(project_id: str, request: RelationshipRequest):
    projects, project = get_project(project_id)
    enforce_agent_write(project, "semantic_relationship_engine", "relationships")
    claims = {claim.id for claim in project.claims}
    if request.from_claim_id not in claims or request.to_claim_id not in claims:
        raise HTTPException(422, "Both clinical relationship endpoints must be existing Claims")
    if request.provenance == "SOURCE" and not request.source_refs:
        raise HTTPException(422, "SOURCE relationship requires explicit source refs; constituent SOURCE claims are insufficient")
    relationship = Relationship(**request.model_dump(), status="NEEDS_HUMAN_REVIEW")
    project.relationships.append(relationship)
    invalidated = invalidate_verification(project, f"Relationship {relationship.id} was added.")
    if invalidated:
        project.workflow_state = "ARCHITECTED"
    audit(project, "RELATIONSHIP_REGISTERED", f"Registered {relationship.id} as {relationship.provenance}; explicitly not auto-approved.")
    save_projects(projects)
    return relationship


@app.post("/api/projects/{project_id}/pages/reorder")
def reorder_project_pages(project_id: str, request: PageOrderRequest):
    projects, project = get_project(project_id)
    event = reorder_pages(project, request)
    audit(project, "NARRATIVE_PAGE_ORDER_OVERRIDE", json.dumps(event, ensure_ascii=False))
    save_projects(projects)
    return event


@app.post("/api/projects/{project_id}/medical-visual-assets")
def add_medical_visual_asset(project_id: str, request: MedicalVisualAssetRequest):
    projects, project = get_project(project_id)
    event = register_medical_visual_asset(project, request)
    audit(project, "MEDICAL_VISUAL_ASSET_REGISTERED", f"Registered {event['asset']['id']} as {event['asset']['origin']} for visual governance.")
    save_projects(projects)
    return event


@app.get("/api/projects/{project_id}/medical-visual-assets")
def list_medical_visual_assets(project_id: str):
    _, project = get_project(project_id)
    return {"assets": project.medical_visual_assets, "issues": medical_visual_asset_issues(project)}


@app.post("/api/projects/{project_id}/visual-bindings")
def add_visual_binding(project_id: str, request: VisualBindingRequest):
    projects, project = get_project(project_id)
    enforce_agent_write(project, "semantic_relationship_engine", "visual_bindings")
    event = register_visual_binding(project, request)
    audit(project, "VISUAL_SEMANTIC_BINDING_REGISTERED", f"Registered locked {event['binding']['binding_type']} binding {event['binding']['id']}.")
    save_projects(projects)
    return event


@app.get("/api/projects/{project_id}/visual-bindings")
def list_visual_bindings(project_id: str):
    _, project = get_project(project_id)
    return {"bindings": project.visual_bindings, "issues": visual_binding_issues(project)}


@app.post("/api/projects/{project_id}/context-contracts")
def add_context_contract(project_id: str, request: ContextContractRequest):
    projects, project = get_project(project_id)
    enforce_agent_write(project, "semantic_relationship_engine", "context_contracts")
    event = register_context_contract(project, request)
    audit(project, "CONTEXT_CONTRACT_REGISTERED", f"Registered {event['contract']['transition_type']} Context Contract {event['contract']['id']}.")
    save_projects(projects)
    return event


@app.get("/api/projects/{project_id}/context-contracts")
def list_context_contracts(project_id: str):
    _, project = get_project(project_id)
    return {"contracts": project.context_contracts, "issues": contextual_contract_issues(project)}


@app.post("/api/projects/{project_id}/generated-visual-verifications")
def add_generated_visual_verification(project_id: str, request: GeneratedVisualVerificationRequest):
    projects, project = get_project(project_id)
    result = verify_generated_visual_contract(project, request)
    audit(project, "POST_GENERATION_VISUAL_VERIFICATION_RUN", f"Verified {request.page_id} against {request.visual_generation_contract_id}: {result['status']}.")
    save_projects(projects)
    return result


@app.post("/api/projects/{project_id}/generation-executions")
def add_generation_execution(project_id: str, request: GenerationExecutionRequest):
    projects, project = get_project(project_id)
    record = record_generation_execution(project, request)
    audit(project, "GENERATION_EXECUTION_RECORDED", f"Recorded {record['generation_component_id']} via {record['engine_id']}@{record['engine_version']}; no medical semantic provenance was changed.")
    save_projects(projects)
    return record


@app.get("/api/projects/{project_id}/generation-executions")
def list_generation_executions(project_id: str):
    _, project = get_project(project_id)
    return {"records": project.generation_execution_provenances}


@app.post("/api/projects/{project_id}/generation-capability-changes")
def report_generation_capability_change(project_id: str, request: GenerationCapabilityChangeRequest):
    projects, project = get_project(project_id)
    event = invalidate_generation_capability(project, request)
    audit(project, "GENERATION_CAPABILITY_INVALIDATED", f"Invalidated {request.engine_id}@{request.from_version} after material change; affected pages={event['affected_page_ids']}.")
    save_projects(projects)
    return event


@app.get("/api/projects/{project_id}/generation-capability-changes")
def list_generation_capability_changes(project_id: str):
    _, project = get_project(project_id)
    return {"records": project.generation_capability_changes}


@app.get("/api/projects/{project_id}/generated-visual-verifications")
def list_generated_visual_verifications(project_id: str):
    _, project = get_project(project_id)
    return {"results": project.generated_visual_verifications}


@app.post("/api/projects/{project_id}/review")
def decide_review_item(project_id: str, request: ReviewDecisionRequest):
    projects, project = get_project(project_id)
    event = review_object(project, request)
    audit(project, "HUMAN_REVIEW_DECISION", json.dumps(event, ensure_ascii=False))
    save_projects(projects)
    return event


@app.patch("/api/projects/{project_id}/claims/{claim_id}/binding")
def patch_claim_binding(project_id: str, claim_id: str, patch: ClaimBindingPatch):
    projects, project = get_project(project_id)
    # Public API follows the frozen immutable-revision rule. The in-process
    # helper remains only for legacy project migration tests.
    event = create_claim_revision(project, claim_id, ClaimRevisionRequest(
        conditions=patch.conditions,
        numeric_facts=patch.numeric_facts,
        responsible_module="human_reviewer",
        revision_reason=patch.rationale,
    ))
    project.human_overrides.append({"at": now(), "object_type": "claim_binding", "object_id": claim_id, "reviewer": patch.reviewer, "rationale": patch.rationale, "revision_id": event["revision"]["revision_id"]})
    audit(project, "HUMAN_BINDING_CORRECTION", json.dumps(event["revision"], ensure_ascii=False))
    save_projects(projects)
    return {"revision": event["revision"], "claim": event["claim"]}


@app.post("/api/projects/{project_id}/claims/{claim_id}/revisions")
def revise_claim(project_id: str, claim_id: str, request: ClaimRevisionRequest):
    projects, project = get_project(project_id)
    event = create_claim_revision(project, claim_id, request)
    audit(project, "IMMUTABLE_CLAIM_REVISION_CREATED", json.dumps(event["revision"], ensure_ascii=False))
    save_projects(projects)
    return {"revision": event["revision"], "claim": event["claim"]}


@app.put("/api/projects/{project_id}/retry-budgets")
def set_retry_budget(project_id: str, request: RetryBudgetRequest):
    projects, project = get_project(project_id)
    budget = configure_retry_budget(project, request)
    audit(project, "RETRY_BUDGET_CONFIGURED", f"Configured {request.module} with max_auto_revision_attempts={request.max_auto_revision_attempts}.")
    save_projects(projects)
    return budget


@app.post("/api/projects/{project_id}/synthetic-cases")
def add_synthetic_case(project_id: str, request: SyntheticCaseRequest):
    projects, project = get_project(project_id)
    case = create_synthetic_case(project, request)
    audit(project, "SYNTHETIC_CASE_CREATED", f"Created isolated synthetic case {case['id']} for {case['purpose']}; not added to Claim Table.")
    save_projects(projects)
    return case


@app.post("/api/projects/{project_id}/external-findings")
def add_external_finding(project_id: str, request: ExternalFindingRequest):
    projects, project = get_project(project_id)
    finding = create_external_finding(project, request)
    audit(project, "EXTERNAL_VERIFICATION_FINDING_RECORDED", f"Recorded isolated external finding {finding['id']} from {finding['source_id']}; no user SOURCE Claim was changed.")
    save_projects(projects)
    return finding


@app.get("/api/projects/{project_id}/external-findings")
def list_external_findings(project_id: str):
    _, project = get_project(project_id)
    return {"verification_mode": project.verification_mode, "external_medical_check": project.external_medical_check, "sources": project.external_sources, "findings": project.external_findings}


@app.put("/api/projects/{project_id}/source-priority-policies")
def set_source_priority_policy(project_id: str, request: SourcePriorityPolicyRequest):
    projects, project = get_project(project_id)
    policy = request.model_dump()
    project.source_priority_policies = [item for item in project.source_priority_policies if item.get("jurisdiction") != policy.get("jurisdiction")]
    project.source_priority_policies.append(policy)
    audit(project, "SOURCE_PRIORITY_POLICY_CONFIGURED", f"Configured review-priority policy {policy['id']}; it does not rank medical truth.")
    save_projects(projects)
    return policy


@app.get("/api/projects/{project_id}/source-priority-policies")
def list_source_priority_policies(project_id: str):
    _, project = get_project(project_id)
    return {"policies": project.source_priority_policies}


@app.post("/api/projects/{project_id}/claim-supersessions")
def add_claim_supersession(project_id: str, request: ClaimSupersessionRequest):
    projects, project = get_project(project_id)
    event = register_claim_supersession(project, request)
    audit(project, "CLAIM_LEVEL_SUPERSESSION_REGISTERED", f"Registered {event['record']['superseded_claim_id']} -> {event['record']['superseding_claim_id']} without changing unrelated Claims.")
    save_projects(projects)
    return event


@app.post("/api/projects/{project_id}/verify")
def run_verifier(project_id: str):
    projects, project = get_project(project_id)
    enforce_policy_gate(projects, project, "verify")
    enforce_agent_write(project, "medical_verifier", "verification_results")
    enforce_agent_write(project, "medical_verifier", "verification_issues")
    enforce_agent_write(project, "medical_verifier", "reverification_runs")
    result = record_verification(project)
    save_projects(projects)
    return result


@app.post("/api/projects/{project_id}/human-overrides")
def add_human_override(project_id: str, request: HumanOverrideRequest):
    projects, project = get_project(project_id)
    override = create_human_override(project, request)
    audit(project, "HUMAN_OVERRIDE_RECORDED", f"Recorded {override['override_id']} without changing VerificationResult {override['verification_result_id']}.")
    save_projects(projects)
    return override


@app.post("/api/projects/{project_id}/verification-issues/{issue_id}/route")
def route_issue(project_id: str, issue_id: str, request: IssueRouteRequest):
    projects, project = get_project(project_id)
    issue = route_verification_issue(project, issue_id, request)
    audit(project, "VERIFICATION_ISSUE_ROUTED", f"Routed {issue_id} to {issue['responsible_module']}.")
    save_projects(projects)
    return issue


@app.post("/api/projects/{project_id}/compliance")
def run_compliance(project_id: str):
    projects, project = get_project(project_id)
    enforce_policy_gate(projects, project, "compliance")
    result = compliance(project)
    project.compliance_issues = result["issues"]
    if result["status"] == "BLOCK":
        project.workflow_state = "BLOCKED"
    elif project.workflow_state == "VERIFIED":
        project.workflow_state = "COMPLIANCE_REVIEW"
    audit(project, "COMPLIANCE_AGENT_RUN", f"Compliance result: {result['status']}")
    save_projects(projects)
    return result


@app.post("/api/projects/{project_id}/route-visuals")
def route_visuals(project_id: str):
    projects, project = get_project(project_id)
    enforce_policy_gate(projects, project, "route_visuals")
    project.visual_plans = visual_router(project)
    project.visual_contracts = compile_visual_contracts(project, project.visual_plans)
    project.visual_prompts = compile_prompt_briefs(project, project.visual_contracts)
    audit(project, "GENERATION_STRATEGY_ROUTER_RUN", f"Routed {len(project.visual_plans)} pages with protected semantic layers and compiled editorial-only prompt briefs.")
    save_projects(projects)
    return {"visual_plans": project.visual_plans, "visual_contracts": project.visual_contracts, "prompt_briefs": project.visual_prompts, "capability_registry": generation_engine_registry()}


@app.get("/api/projects/{project_id}/semantic-deck")
def export_semantic_deck(project_id: str):
    _, project = get_project(project_id)
    return semantic_deck(project)


@app.get("/api/projects/{project_id}/layout-design-brief")
def get_layout_design_brief(project_id: str, page_id: str | None = None):
    """Approved, minimized page semantics and legal composition choices for a model."""
    _, project = get_project(project_id)
    deck = semantic_deck(project)
    try:
        return design_brief(deck, page_ids=[page_id] if page_id else None)
    except LayoutIntentError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/projects/{project_id}/layout-ir")
def get_layout_ir(project_id: str):
    _, project = get_project(project_id)
    deck = semantic_deck(project)
    if not project.layout_ir:
        return {"status": "NOT_DESIGNED", "semantic_digest": semantic_digest(deck), "pages": []}
    try:
        validate_layout_ir(deck, project.layout_ir)
    except LayoutIntentError as error:
        raise HTTPException(409, str(error)) from error
    return {"status": "CURRENT", **project.layout_ir}


def _layout_design_digest(layout_ir: dict | None) -> str:
    return hashlib.sha256(json.dumps(layout_ir, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _configured_editorial_asset_hashes() -> list[str]:
    configured = os.environ.get("EASYPPT_EDITORIAL_ASSET_MANIFEST")
    return [load_editorial_asset_manifest(Path(configured), workspace=ROOT)["sha256"]] if configured else []


def _visual_plan_digest(deck: dict, layout_ir: dict | None,
                        editorial_assets: list[dict]) -> str:
    plan = compile_beautification_plan(deck, editorial_assets=editorial_assets,
                                       layout_ir=layout_ir)
    return hashlib.sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _current_visual_review(project: Project, deck: dict,
                           editorial_assets: list[dict]) -> tuple[dict | None, list[str]]:
    semantic_hash = semantic_digest(deck)
    design_hash = _layout_design_digest(project.layout_ir)
    plan_hash = _visual_plan_digest(deck, project.layout_ir, editorial_assets)
    asset_hashes = [item["sha256"] for item in editorial_assets]
    record = next((item for item in reversed(project.layout_visual_reviews)
                   if item.get("semantic_digest") == semantic_hash
                   and item.get("layout_design_digest") == design_hash
                   and item.get("plan_digest") == plan_hash
                   and item.get("editorial_asset_sha256s") == asset_hashes), None)
    issues = review_issues(record, page_ids=[page["page_id"] for page in deck["pages"]],
                           semantic_digest=semantic_hash, design_digest=design_hash,
                           plan_digest=plan_hash, asset_hashes=asset_hashes,
                           review_root=Path(__file__).resolve().parent / ".codex_build" / "layout-reviews")
    plan = compile_beautification_plan(deck, editorial_assets=editorial_assets,
                                       layout_ir=project.layout_ir)
    issues.extend(f"Slide {item['page_id']}: {item['code']} — {item['message']}"
                  for item in visual_quality_issues(plan))
    return record, issues


@app.post("/api/projects/{project_id}/layout-ir")
def submit_layout_ir(project_id: str, proposal: dict[str, Any]):
    """Accept a model or human design proposal, never slide text or geometry."""
    projects, project = get_project(project_id)
    deck = semantic_deck(project)
    try:
        existing = project.layout_ir if project.layout_ir and project.layout_ir.get("semantic_digest") == semantic_digest(deck) else None
        proposal = {**proposal, "adapter": {"adapter_id": "manual-submission", "external": False}}
        merged = merge_layout_ir(deck, existing, proposal)
        compile_beautification_plan(deck, layout_ir=merged)
    except (LayoutIntentError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    project.layout_ir = merged
    audit(project, "LAYOUT_IR_ACCEPTED", f"Accepted {len(proposal['pages'])} page design choices bound to {merged['semantic_digest'][:16]}.")
    save_projects(projects)
    return {"status": "ACCEPTED", "layout_ir": merged}


@app.post("/api/projects/{project_id}/layout-design/run")
def run_layout_design(project_id: str, request: LayoutRunRequest):
    """Optional local or policy-authorized OpenAI-compatible layout model."""
    projects, project = get_project(project_id)
    deck = semantic_deck(project)
    try:
        model = configured_model()
        if model["external"] and not (project.allow_external_generation and
                                      project.generation_data_egress_policy == "CONTRACT_MINIMIZED"):
            raise HTTPException(403, "External layout model requires allow_external_generation and CONTRACT_MINIMIZED data egress")
        page_ids = request.page_ids or [page["page_id"] for page in deck["pages"]]
        if len(page_ids) != len(set(page_ids)):
            raise LayoutIntentError("Duplicate page IDs in layout model request")
        existing = project.layout_ir if project.layout_ir and project.layout_ir.get("semantic_digest") == semantic_digest(deck) else None
        merged = existing
        current_design_digest = _layout_design_digest(existing)
        prior_review = next((item for item in reversed(project.layout_visual_reviews)
                             if item.get("semantic_digest") == semantic_digest(deck)
                             and item.get("layout_design_digest") == current_design_digest
                             and item.get("editorial_asset_sha256s", []) == _configured_editorial_asset_hashes()), None)
        for page_id in page_ids:
            brief = design_brief(deck, page_ids=[page_id])
            page_review = next((item for item in prior_review.get("pages", [])
                                if item.get("page_id") == page_id and item.get("verdict") == "REVISE"), None) if prior_review else None
            feedback = "; ".join(page_review["concerns"]) if page_review else ""
            for attempt in range(2):
                try:
                    proposal = call_layout_model(brief, model, feedback=feedback)
                    if [item.get("page_id") for item in proposal.get("pages", [])] != [page_id]:
                        raise LayoutIntentError(f"Model response must contain only page {page_id}")
                    proposal["adapter"] = {"adapter_id": model["adapter_id"], "external": model["external"]}
                    candidate = merge_layout_ir(deck, merged, proposal)
                    compile_beautification_plan(deck, layout_ir=candidate)
                    merged = candidate
                    break
                except (LayoutIntentError, ValueError) as error:
                    feedback = str(error)
                    if attempt == 1:
                        raise LayoutIntentError(f"Page {page_id}: model could not produce a fitting layout: {feedback}") from error
    except HTTPException:
        raise
    except (LayoutIntentError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    project.layout_ir = merged
    project.model_runs.append({"agent": "layout_designer", "adapter_id": model["adapter_id"],
                               "external": model["external"], "page_ids": page_ids,
                               "semantic_digest": merged["semantic_digest"],
                               "output_hash": hashlib.sha256(json.dumps(merged, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
                               "executed_at": now()})
    audit(project, "MODEL_LAYOUT_DESIGN_ACCEPTED", f"Validated {len(page_ids)} model-designed page compositions.")
    save_projects(projects)
    return {"status": "ACCEPTED", "layout_ir": merged}


@app.get("/api/projects/{project_id}/layout-visual-review")
def get_layout_visual_review(project_id: str):
    _, project = get_project(project_id)
    deck = semantic_deck(project)
    configured = os.environ.get("EASYPPT_EDITORIAL_ASSET_MANIFEST")
    assets = [load_editorial_asset_manifest(Path(configured), workspace=ROOT)] if configured else []
    current, issues = _current_visual_review(project, deck, assets)
    return {"status": "PASS" if not issues else "REVISION_REQUIRED", "issues": issues,
            "review": current}


@app.post("/api/projects/{project_id}/layout-cycle/run")
def run_layout_cycle(project_id: str, request: LayoutCycleRequest):
    """Bounded design → render → visual critique loop for selected pages."""
    pending = request.page_ids
    history = []
    for round_number in range(1, request.max_rounds + 1):
        design = run_layout_design(project_id, LayoutRunRequest(page_ids=pending))
        # A changed layout IR invalidates the prior visual proof for the whole deck.
        # Always re-render and review every slide, including pages not redesigned.
        review = run_layout_visual_review(project_id, LayoutRunRequest())
        upstream = [item for item in review.get("quality_issues", [])
                    if item.get("route") == "UPSTREAM_CONTENT"]
        if upstream:
            history.append({"round": round_number, "quality_issues": upstream,
                            "visual_review": review["pages"]})
            return {"status": "REPAGINATION_REQUIRED", "rounds": history,
                    "quality_issues": upstream, "layout_ir": design["layout_ir"]}
        revised = [item["page_id"] for item in review["pages"] if item["verdict"] == "REVISE"]
        history.append({"round": round_number,
                        "designed_page_ids": [item["page_id"] for item in design["layout_ir"]["pages"]]
                        if pending is None else pending,
                        "visual_review": review["pages"]})
        if not revised:
            return {"status": "ADVISORY_VISUAL_PASS", "rounds": history,
                    "layout_ir": design["layout_ir"]}
        pending = revised
    return {"status": "VISUAL_REVISION_REMAINING", "rounds": history,
            "remaining_page_ids": pending, "layout_ir": design["layout_ir"]}


def _render_visual_package(project: Project, deck: dict) -> dict:
    """Build and verify the exact PowerPoint deck/images offered for W15 review."""
    if project.layout_ir:
        validate_layout_ir(deck, project.layout_ir)
    configured_asset_manifest = Path(os.environ["EASYPPT_EDITORIAL_ASSET_MANIFEST"]) if os.environ.get("EASYPPT_EDITORIAL_ASSET_MANIFEST") else None
    configured_assets = [load_editorial_asset_manifest(configured_asset_manifest, workspace=ROOT)] if configured_asset_manifest else []
    quality = visual_quality_issues(compile_beautification_plan(
        deck, editorial_assets=configured_assets, layout_ir=project.layout_ir))
    design_hash = _layout_design_digest(project.layout_ir)
    asset_hashes = [asset["sha256"] for asset in configured_assets]
    plan_digest = _visual_plan_digest(deck, project.layout_ir, configured_assets)
    review_key = hashlib.sha256((semantic_digest(deck) + design_hash + plan_digest
                                 + "".join(asset_hashes)).encode("ascii")).hexdigest()
    review_dir = Path(__file__).resolve().parent / ".codex_build" / "layout-reviews" / review_key[:16]
    receipt_path = (Path(__file__).resolve().parent / ".codex_build" / "validation-receipts"
                    / f"{review_key[:16]}-{uuid.uuid4().hex[:8]}.json")
    preview_dir = review_dir / "powerpoint_png"
    preview_deck = review_dir / "preview.pptx"
    render_receipt = review_dir / "powerpoint_render.json"
    expected_images = [preview_dir / f"slide-{index:02}.png"
                       for index in range(1, len(deck["pages"]) + 1)]
    cache_ok = (preview_deck.is_file() and zipfile.is_zipfile(preview_deck)
                and all(path.is_file() for path in expected_images))
    if cache_ok:
        try:
            cached = json.loads(render_receipt.read_text(encoding="utf-8"))
            cache_ok = (cached.get("renderer") == "powerpoint"
                        and cached.get("pptx_sha256") == sha256_file(preview_deck)
                        and cached.get("image_sha256s") == [sha256_file(path) for path in expected_images]
                        and Path(cached.get("validation_receipt_path") or "").is_file()
                        and cached.get("validation_receipt_sha256") ==
                        sha256_file(Path(cached["validation_receipt_path"]))
                        and finalizer_receipt_matches(cached["validation_receipt_path"], preview_deck))
        except (OSError, ValueError):
            cache_ok = False
    if not cache_ok:
        # The finalizer refuses to overwrite a prior deck. Replace only this
        # managed key's generated files after an interrupted or invalid build.
        if preview_deck.exists():
            preview_deck.unlink()
        if preview_dir.exists():
            for old_image in preview_dir.glob("slide-*.png"):
                old_image.unlink()
        build_pptx(deck, preview_deck, mark_operation=False, finalize=True,
                   validation_receipt=receipt_path,
                   layout_ir=project.layout_ir, editorial_asset_manifest=configured_asset_manifest)
        if not finalizer_receipt_matches(receipt_path, preview_deck):
            raise LayoutIntentError("Finalizer receipt does not match the generated PPTX")
        from app.validation.render_with_powerpoint import render
        rendered = render(preview_deck, preview_dir)
        if rendered["slides"] != len(deck["pages"]) or not all(path.is_file() for path in expected_images):
            raise LayoutIntentError("PowerPoint did not render every slide in deck order")
        cached = {"renderer": "powerpoint",
                                             "pptx_sha256": sha256_file(preview_deck),
                                             "image_sha256s": [sha256_file(path) for path in expected_images],
                                             "validation_receipt_path": str(receipt_path),
                                             "validation_receipt_sha256": sha256_file(receipt_path)}
        render_receipt.write_text(json.dumps(cached, sort_keys=True), encoding="utf-8")
    verification = verify_pptx(deck, preview_deck, layout_ir=project.layout_ir,
                               editorial_asset_manifest=configured_asset_manifest)
    if verification["status"] != "PASS":
        raise LayoutIntentError("Rendered PPTX failed deterministic verification before visual review")
    return {"status": "PREVIEW_READY", "semantic_digest": semantic_digest(deck),
            "layout_design_digest": design_hash, "preview_sha256": sha256_file(preview_deck),
            "preview_path": str(preview_deck), "renderer": "powerpoint",
            "validation_receipt_path": cached.get("validation_receipt_path"),
            "plan_digest": plan_digest, "editorial_asset_sha256s": asset_hashes,
            "quality_issues": quality,
            "images": [{"page_id": page["page_id"], "path": str(path), "sha256": sha256_file(path)}
                       for page, path in zip(deck["pages"], expected_images)],
            "rendered_at": now()}


@app.post("/api/projects/{project_id}/layout-visual-review/render")
def render_layout_visual_review(project_id: str):
    """Offer real PowerPoint PNGs to an operator model or human reviewer."""
    _, project = get_project(project_id)
    deck = semantic_deck(project)
    try:
        return _render_visual_package(project, deck)
    except (LayoutIntentError, ValueError, OSError, ImportError, RuntimeError) as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/projects/{project_id}/layout-visual-review")
def register_layout_visual_review(project_id: str, submission: VisualReviewSubmission):
    """Accept one operator-authored verdict per exact PowerPoint image."""
    projects, project = get_project(project_id)
    deck = semantic_deck(project)
    try:
        package = _render_visual_package(project, deck)
    except (LayoutIntentError, ValueError, OSError, ImportError, RuntimeError) as error:
        raise HTTPException(422, str(error)) from error
    if submission.preview_sha256 != package["preview_sha256"]:
        raise HTTPException(409, "Reviewed PPTX bytes no longer match the current render")
    expected = package["images"]
    if [item.page_id for item in submission.pages] != [item["page_id"] for item in expected]:
        raise HTTPException(422, "Submit one visual verdict for every slide in deck order")
    if any(item.image_sha256 != image["sha256"] for item, image in zip(submission.pages, expected)):
        raise HTTPException(409, "Reviewed PowerPoint image bytes no longer match the current render")
    blocked = {item["page_id"] for item in package.get("quality_issues", [])}
    if any(item.verdict == "PASS" and item.page_id in blocked for item in submission.pages):
        raise HTTPException(422, "A page with severe content-density issues cannot receive visual PASS; revise its content and pagination")
    pages = [{"page_id": item.page_id, "verdict": item.verdict,
              "concerns": item.concerns[:10]} for item in submission.pages]
    record = {**package, "status": "ADVISORY_REVIEW", "pages": pages,
              "adapter_id": "operator-model:submitted", "external": False,
              "executed_at": now()}
    project.layout_visual_reviews.append(record)
    audit(project, "OPERATOR_LAYOUT_VISUAL_REVIEW",
          f"Reviewed {len(pages)} PowerPoint-rendered pages; "
          f"revisions={sum(item['verdict'] == 'REVISE' for item in pages)}.")
    save_projects(projects)
    return record


@app.post("/api/projects/{project_id}/layout-visual-review/run")
def run_layout_visual_review(project_id: str, request: LayoutRunRequest):
    """Review actual PNGs with a separate vision model; results are hash-bound."""
    projects, project = get_project(project_id)
    deck = semantic_deck(project)
    try:
        model = configured_review_model()
        if model["external"] and not (project.allow_external_generation and
                                      project.generation_data_egress_policy == "CONTRACT_MINIMIZED"):
            raise HTTPException(403, "External visual review requires allow_external_generation and CONTRACT_MINIMIZED data egress")
        page_ids = request.page_ids or [page["page_id"] for page in deck["pages"]]
        if len(page_ids) != len(set(page_ids)):
            raise LayoutIntentError("Duplicate page IDs in visual review request")
        unknown_ids = set(page_ids) - {page["page_id"] for page in deck["pages"]}
        if unknown_ids:
            raise LayoutIntentError(f"Unknown page IDs in visual review request: {sorted(unknown_ids)}")
        package = _render_visual_package(project, deck)
        image_by_page = {item["page_id"]: Path(item["path"]) for item in package["images"]}
        results = [call_visual_review_model(design_brief(deck, page_ids=[page_id]),
                                            image_by_page[page_id], model)
                   for page_id in page_ids]
        for result in results:
            flags = [item for item in package["quality_issues"]
                     if item["page_id"] == result["page_id"]]
            if flags:
                result["verdict"] = "REVISE"
                result["concerns"].extend(item["message"] for item in flags)
    except HTTPException:
        raise
    except (LayoutIntentError, ValueError, OSError, ImportError, RuntimeError) as error:
        raise HTTPException(422, str(error)) from error
    record = {**package, "status": "ADVISORY_REVIEW",
              "adapter_id": model["adapter_id"], "external": model["external"],
              "pages": results,
              "executed_at": now()}
    project.layout_visual_reviews.append(record)
    audit(project, "MODEL_LAYOUT_VISUAL_REVIEW", f"Reviewed {len(results)} rendered pages; advisory only.")
    save_projects(projects)
    return record


@app.get("/api/projects/{project_id}/beautification-plan")
def export_beautification_plan(project_id: str):
    """Expose candidate scores and native object geometry before PPTX export."""
    _, project = get_project(project_id)
    configured = os.environ.get("EASYPPT_EDITORIAL_ASSET_MANIFEST")
    assets = [load_editorial_asset_manifest(Path(configured), workspace=ROOT)] if configured else []
    return compile_beautification_plan(semantic_deck(project), editorial_assets=assets,
                                       layout_ir=project.layout_ir)


@app.get("/api/projects/{project_id}/presentation.pptx")
def export_presentation(project_id: str):
    projects, project = get_project(project_id)
    deck = semantic_deck(project)
    if project.reading_structure:
        if not project.full_summary:
            raise HTTPException(409, "Full-source summary is required before delivery")
        summary_issues = validate_full_summary(project.full_summary, project.reading_structure)
        if summary_issues:
            raise HTTPException(409, {"message": "Full-source summary is stale or incomplete",
                                      "issues": summary_issues})
    configured_asset_manifest = Path(os.environ["EASYPPT_EDITORIAL_ASSET_MANIFEST"]) if os.environ.get("EASYPPT_EDITORIAL_ASSET_MANIFEST") else None
    configured_assets = [load_editorial_asset_manifest(configured_asset_manifest, workspace=ROOT)] if configured_asset_manifest else []
    review, visual_issues = _current_visual_review(project, deck, configured_assets)
    if visual_issues:
        raise HTTPException(409, {"message": "W15 PowerPoint visual review is incomplete",
                                  "issues": visual_issues})
    delivery_identity = {"layout_ir": project.layout_ir,
                         "editorial_asset_sha256s": [asset["sha256"] for asset in configured_assets]}
    semantic_hash = immutable_snapshot_digest(deck, project.documents,
                                              reading_sha256=project.reading_structure_sha256,
                                              extra=delivery_identity)
    snapshot_id = f"del_{semantic_hash[:16]}"
    target = DATA / "exports" / project.id / f"{snapshot_id}.pptx"
    plan_target = DATA / "exports" / project.id / f"{snapshot_id}.beautification.json"
    # Deliver the exact PPTX bytes whose PowerPoint PNGs received W15 review.
    # A second build can change wrapping despite having the same semantic plan.
    reviewed_pptx = Path(review["preview_path"])
    receipt_name = review.get("validation_receipt_path")
    if not receipt_name:
        raise HTTPException(409, "The reviewed PPTX has no finalizer receipt; render and review again")
    receipt_path = Path(receipt_name)
    if not finalizer_receipt_matches(receipt_path, reviewed_pptx):
        raise HTTPException(409, "The reviewed PPTX has no matching finalizer receipt; render and review again")
    if not target.exists() or sha256_file(target) != review["preview_sha256"]:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(reviewed_pptx, target)
    if not plan_target.exists():
        plan_target.write_text(json.dumps(compile_beautification_plan(deck, editorial_assets=configured_assets,
                                                                       layout_ir=project.layout_ir), ensure_ascii=False, indent=2), encoding="utf-8")
    output_verification = verify_pptx(deck, target, editorial_asset_manifest=configured_asset_manifest,
                                      layout_ir=project.layout_ir)
    if output_verification["status"] != "PASS":
        raise HTTPException(500, f"Post-generation verification failed: {output_verification['issues']}")
    pptx_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
    quality_plan = compile_beautification_plan(deck, editorial_assets=configured_assets,
                                               layout_ir=project.layout_ir)
    quality_report = make_quality_report(
        deck, quality_plan, target, output_verification,
        source_documents=project.documents, layout_ir=project.layout_ir,
        editorial_asset_sha256s=delivery_identity["editorial_asset_sha256s"],
        finalizer_receipt=receipt_path)
    validate_quality_report(
        quality_report, deck, quality_plan, target,
        source_documents=project.documents, layout_ir=project.layout_ir,
        editorial_asset_sha256s=delivery_identity["editorial_asset_sha256s"],
        finalizer_receipt=receipt_path)
    quality_path = target.with_suffix(".quality.json")
    write_quality_report(quality_path, quality_report)
    if not any(item["snapshot_id"] == snapshot_id for item in project.delivery_manifests):
        project.delivery_manifests.append(delivery_manifest(project, deck, pptx_sha256,
                                                            output_verification, extra=delivery_identity,
                                                            quality_report=quality_report))
        audit(project, "DELIVERY_SNAPSHOT_CREATED", f"Immutable snapshot {snapshot_id}; pptx_sha256={pptx_sha256}")
    audit(project, "PRESENTATION_PACKAGED", f"Delivered immutable PPTX snapshot: {target.name}")
    save_projects(projects)
    return FileResponse(target, filename=target.name, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")


@app.get("/api/projects/{project_id}/delivery-manifests")
def list_delivery_manifests(project_id: str):
    _, project = get_project(project_id)
    return {"project_id": project.id, "manifests": project.delivery_manifests}


@app.get("/api/projects/{project_id}/provenance")
def get_provenance(project_id: str):
    """Tamper-evident audit trail status, verifiable without this application."""
    _, project = get_project(project_id)
    return provenance_report(project)


@app.post("/api/projects/{project_id}/anchor")
def post_anchor(project_id: str, note: str = ""):
    """Publish this project's chain head to the append-only anchor store."""
    projects, project = get_project(project_id)
    result = create_anchor(project, note=note)
    save_projects(projects)
    return result


@app.get("/api/projects/{project_id}/review-sheet")
def review_sheet(project_id: str):
    _, project = get_project(project_id)
    return medical_review_sheet(project)


@app.get("/legacy")
def legacy_home():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/web/index.html")
