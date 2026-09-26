# Stage Output Contracts v0.3

> For v0.5 runs, INTEGRITY_AND_QUALITY_v0.5.md overrides the prototype, schema, exact-verifier and dual-artifact clauses below; the frozen stage numbers are unchanged.

This file supersedes `STAGE_OUTPUT_CONTRACTS_v0.2.md` for active model-first reference runs. Frozen specs remain authoritative and are unchanged.

| Stage | Required input | Required output | Blocking failure |
|---|---|---|---|
| W00 | source file(s) | SourceManifest + SourceIntakeRecord + applicable SourceVersionChain | source identity/MIME/magic/hash not reproducible; unanchored effective version |
| W01 | SourceManifest | ExtractedPage records + DocumentStructureAudit + rendered/OCR/DICOM refs | silent page omission / unresolved layout, table continuation or DICOM surface |
| W02 | ExtractedPage | SourceSpan, ClaimCandidate, AtomicClaim, NumericFact, SourceRef, provenance | SOURCE object lacks source binding |
| W02-FSC | full Evidence Universe + coverage manifest + independent review | FullSourceCoverageAudit + FactOracleReview | self-certified/unknown denominator; silent/narrative-changing omission |
| W03 | evidence objects | VerificationResult per meaning-critical object | unresolved RED fact / numeric semantics uncertain |
| W04 | verified evidence + presentation context | PresentationContextProfile + AdaptationContract + ContextIntegrityCheck | context mutates source fact/scope |
| W05 | context + verified full evidence | TriageDecision set | required evidence unclassified / meaning bundle broken |
| W06 | Triage + context | NarrativeDraft | unsupported narrative fact / context mutation |
| W06-NR | NarrativeDraft | NarrativeRationalityAudit + applicable CaseBoundaryReview + ApprovedNarrativeArchitecture | revisions/block or case generalization unresolved |
| W06-NP | ApprovedNarrativeArchitecture | PageAllocationAudit + ApprovedPageAllocationPlan | invalid cognitive decomposition |
| W07 | approved narrative/page allocation/evidence | PageSpec[] | no unique PrimaryMessage / required bindings absent |
| W08 | PageSpec + approved evidence | SemanticPageGraph Draft | unsupported relationship / logic/binding loss |
| W09 | semantic graph candidate | Medical/Numeric/Logic Audit + IssueRegister/corrections | source/numeric/logic failure unresolved |
| W10 | W09-approved current objects | ApprovedSemanticPageGraph | stale/unapproved object included |
| W11 | W10 graph + context + frozen selector governance | VisualStrategyDecisionSet | invalid visual grammar / forced misleading visual |
| W12-A abstract routing | W10 + W11 | abstract PageGenerationPlan/component routes | Visual Type or semantics changed |
| W12-B runtime qualification | abstract routes + PortableRuntimeBundle | effective_generation_route per component/page + runtime qualification audit | missing qualified engine, verifier, egress clearance or asset contract |
| W13 | W10 + W11 + W12 effective routes | VisualGenerationContract + PromptManifest/model-specific prompt | mandatory/exact/prohibited/verification registers incomplete |
| W14 | contract + effective route | versioned generated/composited asset + GenerationOutputManifest + execution provenance | Protected Semantic Layer mutated |
| W15 | generated asset + GenerationOutputManifest + same contract | PostGenerationQA + page-complete PrivacySurfaceAudit | mandatory/exact/numeric/relation/visual-semantic/privacy failure or untested surface |
| W16 | RED/exception items | HumanReviewRecord | required human decision missing |
| W17 | approved artifacts | delivery package + DeliveryManifest | rejected/stale asset included |
| W18 | full run history | BenchmarkRecord + lessons/regression candidates | disposition/metrics/issues not recorded |

## PortableRuntimeBundle requirement for W12-B

W12 effective routing requires the active `PORTABLE_RUNTIME_CAPABILITY_CONTRACT_v0.1.md` bundle:

- RuntimeCapabilityProfile;
- GenerationCapabilityRegistry;
- PostGenerationVerifierCapabilityRegistry;
- DataEgressPolicy/PrivacyDecision;
- MedicalVisualAssetContract(s) as needed;
- QualificationEvidence;
- fallback capability records when fallback is advertised.

W12-A may PASS while W12-B remains BLOCKED. This preserves the model's semantic routing work without fabricating engine capability.

## GenerationOutputManifest requirement

W14 controlled renderers/compositors should emit a machine-readable `GenerationOutputManifest` containing actual rendered text strings, semantic object/relationship IDs, logic/group bindings, NumericFact IDs/strings, asset IDs/hashes, protected-layer IDs/hashes, provenance and layout-region IDs.

W15 exact/numeric/topology/logic/provenance checks should preferentially compare this manifest to approved contracts. Pixel OCR is fallback-only and is not the sole RED approval path.

## Issue contract

Every issue should record:
- `issue_id`;
- `stage_detected`;
- `earliest_responsible_stage`;
- `severity`;
- affected object/version IDs;
- source/evidence;
- owner;
- state;
- resolution revision;
- regression test ID.

## State progression

Recommended stage states:
`NOT_STARTED`, `IN_PROGRESS`, `PASS`, `PASS_WITH_WARNINGS`, `PARTIAL_PASS`, `BLOCKED`, `NEEDS_HUMAN_REVIEW`, `FAIL`, `STALE`.

A later stage cannot convert an unresolved upstream BLOCK/FAIL into PASS without a new immutable revision and re-verification.
