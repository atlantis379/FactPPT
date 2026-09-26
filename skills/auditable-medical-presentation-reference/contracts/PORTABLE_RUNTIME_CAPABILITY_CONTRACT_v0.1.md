# Portable Runtime Capability Contract v0.1

Status: `ACTIVE_SKILL_CONTRACT_NOT_FROZEN_SPEC`

Purpose: make the Auditable Medical Presentation Skill portable across runtimes without hard-coding vendor/model assumptions, while preserving W12/W13/W14 auditability and the frozen Module 06 routing constraints.

This contract does **not** change any frozen spec. It defines the runtime information that must be injected into the Skill before an abstract W12 route may become an `effective_generation_route`.

## 1. Core principle

```text
Portable Skill
  decides WHAT must be generated,
  WHAT semantic/exactness guarantees are required,
  WHAT route classes are legal,
  WHAT verification must exist

Runtime Profile
  declares WHICH concrete engine/version can satisfy those guarantees,
  WITH WHAT qualification evidence,
  UNDER WHAT data-egress policy,
  WITH WHICH verifier/version,
  and WITH WHICH asset contracts
```

The Skill must never infer a capability from a vendor name, product family, marketing claim, historical version, or model reputation.

## 2. Required runtime bundle

Every execution environment that wants W12 effective routing must provide a versioned `PortableRuntimeBundle` containing:

1. `RuntimeCapabilityProfile`;
2. `GenerationCapabilityRegistry`;
3. `PostGenerationVerifierCapabilityRegistry`;
4. `DataEgressPolicy / PrivacyDecision`;
5. `MedicalVisualAssetContract[]` for every source/verified medical asset used by the route;
6. `FallbackCapabilityRecord[]` when fallback is advertised;
7. `QualificationEvidence[]` for every Hard-qualified capability;
8. `RuntimeInvalidationPolicy`.

Missing required objects do not invalidate the upstream semantic plan. They block only effective route binding.

## 3. RuntimeCapabilityProfile minimum fields

A runtime profile must declare:

- `runtime_profile_id`;
- `profile_version`;
- `skill_compatibility`;
- `environment_name` and `platform`;
- `reasoning_model_id/version` when relevant;
- available execution classes;
- processing boundary / locality;
- artifact persistence capability;
- supported content types;
- capability-registry references;
- verifier-registry references;
- egress-policy reference;
- known limitations;
- material-change invalidation triggers;
- current overall qualification status.

Allowed overall qualification statuses:

- `QUALIFIED`;
- `REFERENCE_QUALIFIED`;
- `PARTIALLY_QUALIFIED`;
- `QUALIFICATION_PENDING`;
- `UNQUALIFIED`;
- `STALE`;
- `BLOCKED`.

`REFERENCE_QUALIFIED` means qualified only for a named reference/benchmark scope and must not be generalized to production or other domains.

## 4. GenerationCapabilityRecord

Each concrete engine/renderer/compositor must be version-bound and record, at minimum:

- `capability_record_id`;
- `engine_id`;
- `engine_version`;
- `implementation_class`;
- `component_types_supported`;
- `strategies_supported`;
- `qualification_status`;
- `qualification_evidence_ids`;
- `processing_boundary`;
- `exact_text_authority`;
- `exact_data_geometry`;
- `semantic_topology_lock`;
- `node_edge_direction_lock`;
- `logic_lock`;
- `group_membership_lock`;
- `asset_integrity_preservation`;
- `prompt_driven_editorial_composition`;
- `deterministic_output_manifest_support`;
- `protected_layer_support`;
- `post_render_verification_hooks`;
- `seed/reproducibility controls` where applicable;
- `known_failure_modes`;
- `fallback_compatibility`.

Capabilities must use explicit values such as `QUALIFIED`, `NOT_QUALIFIED`, `UNKNOWN`, or bounded capability profiles. `true` must not be used as a substitute for untested qualification.

## 5. Qualification evidence contract

A Hard-qualified capability requires version-specific benchmark evidence.

Every `QualificationEvidence` must include:

- `qualification_evidence_id`;
- `capability_record_id` or `verifier_capability_id`;
- `benchmark_id/version`;
- tested engine/verifier version;
- test corpus/scope;
- positive cases;
- negative/adversarial cases;
- expected outcomes;
- observed outcomes;
- pass/fail metrics;
- known misses;
- qualification scope;
- date;
- reviewer/model provenance;
- invalidation conditions.

Benchmark evidence must test failure detection, not only successful examples.

A capability cannot be upgraded to `QUALIFIED` merely because the current reference case happened to render acceptably.

## 6. Required verifier registry

A runtime eligible for W12/W14 must register executable verifier capabilities for the meaning-critical obligations present in the route.

The registry must be able to declare separate validators for:

- exact text;
- numeric/operator/unit/context binding;
- semantic topology;
- AND/OR/NOT/EXCEPT logic;
- grouping/ownership/legend binding;
- provenance/source/asset identity;
- protected-layer integrity;
- visual visibility/occlusion/hierarchy;
- data geometry/axis/scale where present.

A single multimodal model may support multiple checks, but the registry must still expose them as separately auditable capabilities and must state whether each capability is authoritative, secondary, or human-review-only.

## 7. No-OCR-first verification architecture

For exact text and semantics, the preferred portable design is **manifest-first**, not OCR-first.

Qualified renderers/compositors should emit a `GenerationOutputManifest` containing:

- actual rendered text strings;
- semantic object IDs;
- relationship IDs;
- group membership;
- logic operators;
- numeric fact IDs and exact strings;
- asset IDs/hashes;
- protected-layer IDs/hashes;
- layout region IDs;
- source/citation IDs.

Post-generation validation then compares:

```text
Approved Semantic Graph / ExactTextRegister / AssetContract
              ↓
      GenerationOutputManifest
              ↓
    structured diff validators
              +
 secondary rendered-asset visual review
```

OCR is only a fallback when no authoritative output manifest/text layer exists and must never be the sole approval basis for RED exact text when a controlled compositor can provide a manifest.

## 8. DataEgressPolicy contract

Every runtime must declare a project-specific policy; example/default policy files are not sufficient for effective routing.

The policy must cover at least:

- data classification levels;
- public-source material;
- licensed/restricted source material;
- patient/PHI/PII material;
- internal/confidential material;
- derived prompts;
- source screenshots/figures;
- external third-party model processing;
- platform-managed generation;
- prompt/log retention;
- permitted persistence targets;
- de-identification requirements;
- default action when classification is unknown.

The safest default for unknown classification is `DENY_EXTERNAL_PROCESSING`.

## 9. MedicalVisualAssetContract contract

Any source figure, verified medical illustration, anatomy image, pathology image, procedure image, or other medical visual asset used as a meaning-bearing layer requires a versioned contract.

Minimum fields:

- `asset_contract_id`;
- `asset_id/version`;
- asset role;
- source document/file identity;
- page/figure/region pointer;
- canonical asset hash/dimensions when materialized;
- authority level;
- allowed transforms;
- prohibited transforms;
- AI-generation/edit permissions;
- derivative-asset requirements;
- provenance obligations;
- integrity-verification method;
- post-generation QA requirement;
- usage scope.

`RENDER_AUTHORITATIVE` source figures must never be replaced by an AI redraw as source authority.

## 10. Verification-path eligibility

For every meaning-critical Generation Component, W12 must name an executable verification path with:

- validator capability ID/version;
- verification target;
- expected source/contract;
- failure action;
- escalation/human-review rule.

A route is ineligible if a locked semantic obligation cannot be verified.

## 11. Fallback contract

Fallback records may change only:

- engine/version;
- rendering technique;
- non-semantic visual polish.

Fallback may not change:

- Visual Type;
- Page Goal;
- semantic graph;
- relationship direction;
- logic;
- exact text requirement;
- numeric precision;
- asset authority;
- verification requirement;
- data-egress rule.

No legal fallback → `UNROUTABLE` or `NEEDS_HUMAN_REVIEW`.

## 12. Material-change invalidation

At minimum, requalification is required after a material change to:

- engine/model/renderer/compositor version;
- prompt compiler affecting locked output;
- text renderer;
- diagram renderer;
- asset pipeline;
- output manifest format;
- verifier model/version;
- data-egress behavior;
- platform processing boundary;
- seed/reproducibility semantics.

Runtime profiles must not silently inherit qualification across material changes.

## 13. W12 gate behavior

W12 may always produce an **abstract legal route plan** from W10 + W11.

W12 may produce an `effective_generation_route` only when all required conditions are satisfied:

```text
approved upstream objects
AND qualified concrete generation capability
AND project-specific egress clearance
AND executable qualified verification path
AND required MedicalVisualAssetContract(s)
AND legal fallback or explicit no-fallback state
```

If any condition is missing:

- preserve the abstract route plan;
- create/update a gap register;
- do not advance to W13 for the affected page/component.

## 14. Portability invariant

A portable Skill package must remain semantically valid if the runtime changes from one vendor/model/toolchain to another.

Only the runtime bundle should change.

Therefore vendor/model/renderer-specific assumptions belong in versioned runtime profiles and capability registries, never in frozen medical semantics or PageSpecs.
