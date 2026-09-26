# Reference Pipeline Execution Checklist v0.1

**Status:** `FROZEN_PROCESS_CHECKLIST`

Use this checklist for every Model-first Reference Pipeline test. A stage is not complete until all required boxes are checked or an explicit blocker is recorded.

## A. Run metadata

- [ ] Test ID assigned
- [ ] Source filename recorded
- [ ] Source SHA256 recorded
- [ ] Source version recorded
- [ ] Page count recorded
- [ ] Presenter role recorded
- [ ] Audience recorded
- [ ] Scenario/project type recorded
- [ ] Presentation question recorded
- [ ] Duration recorded
- [ ] Output language recorded
- [ ] External research allowed/denied recorded
- [ ] Synthetic case default confirmed OFF unless explicitly requested

## B. Source registration and extraction

- [ ] Original source retained / retrievable
- [ ] Document hash verified
- [ ] Page numbers preserved
- [ ] Page text extracted
- [ ] Rendered page images available
- [ ] Table pages flagged
- [ ] Figure/flowchart pages flagged
- [ ] Extraction warnings recorded
- [ ] Corrupted text-layer pages visually checked
- [ ] No silent page omission

## C. Structured Evidence Layer

- [ ] SourceSpan created
- [ ] Atomic Claim candidates created
- [ ] `source_quote` preserved
- [ ] `normalized_claim` stored separately
- [ ] Population captured where meaning-critical
- [ ] Condition captured where meaning-critical
- [ ] Timeframe captured where meaning-critical
- [ ] Dose captured where present
- [ ] Threshold captured where present
- [ ] NumericFacts separately structured
- [ ] Recommendation class separately structured
- [ ] Evidence level separately structured
- [ ] Table/Figure provenance retained
- [ ] SOURCE/SUMMARY/SYNTHESIS provenance assigned
- [ ] Risk level assigned or explicitly UNASSESSED
- [ ] No clinical edge created during Claim extraction
- [ ] No external knowledge presented as SOURCE

## D. Evidence verification

- [ ] Claim atomicity checked
- [ ] Qualifier preservation checked
- [ ] Negation checked
- [ ] Modality checked
- [ ] Quantifier checked
- [ ] Number value checked
- [ ] Operator checked (`<`, `>`, `≤`, `≥`, `=`)
- [ ] Range checked
- [ ] Unit checked
- [ ] Statistic type checked
- [ ] CI checked
- [ ] P value checked
- [ ] Sample size checked
- [ ] Recommendation class checked
- [ ] Evidence level checked
- [ ] Source page/location checked
- [ ] RED evidence objects have no unresolved silent error

## E. Role preparation

- [ ] RoleProfile generated
- [ ] Audience depth defined
- [ ] Presenter responsibility defined
- [ ] Same source facts preserved across roles
- [ ] Role changes selection/depth/order only
- [ ] Clinical facts not altered by role adaptation

## F. Information Triage

- [ ] Presentation Question drives selection
- [ ] Audience considered
- [ ] Project type considered
- [ ] Goal considered
- [ ] Duration considered
- [ ] Each item assigned MUST/SHOULD/APPENDIX/EXCLUDED
- [ ] Each decision has reason
- [ ] Meaning-Preserving Bundles retained
- [ ] EXCLUDED content preserved in source layer
- [ ] No clinical relationship invented

## G. Narrative and outline

- [ ] Narrative Spine created
- [ ] Source document TOC not copied mechanically
- [ ] Section goals defined
- [ ] Presentation order justified
- [ ] Narrative provenance recorded
- [ ] No unsupported fact added for storytelling completeness

## H. PageSpec

For every page:
- [ ] Page Goal exists
- [ ] Exactly one Primary Message exists
- [ ] Supporting Claims only support Primary Message
- [ ] Conditions/Data/Caveats are present when meaning-critical
- [ ] Source layer is explicit
- [ ] Risk level assigned
- [ ] Claim-to-page mapping recorded

## I. Semantic Relationship & Evidence Binding

- [ ] Relationship type identified
- [ ] Direction checked
- [ ] Conditions preserved
- [ ] AND/OR/NOT/EXCEPT preserved
- [ ] Recommendation/evidence binding preserved
- [ ] Data binding preserved
- [ ] Visual grammar is licensed by approved semantics
- [ ] Comparability gate checked when direct comparison is used
- [ ] No auto-created clinical edge without support

## J. Medical / Numeric / Logic audit

- [ ] Source Fidelity audit complete
- [ ] Numeric audit complete
- [ ] Title entailment audit complete
- [ ] Relationship audit complete
- [ ] Contextual implication audit complete
- [ ] Comparison audit complete
- [ ] Recommendation strength audit complete
- [ ] Evidence level audit complete
- [ ] Conflict review complete
- [ ] RED synthesis sent to human review when required
- [ ] All issues have owner/status

## K. Approved Semantic Page Graph

- [ ] Only approved/current object versions included
- [ ] Stale objects excluded
- [ ] Source bindings intact
- [ ] Data bindings intact
- [ ] Relationship bindings intact
- [ ] Approval status recorded

## L. Visual Strategy

- [ ] Page Goal considered
- [ ] Visual Intent considered
- [ ] Information structure considered
- [ ] Approved relationships considered
- [ ] Precision requirement considered
- [ ] Hard Gate run before scoring
- [ ] Standard-aware candidate considered where applicable
- [ ] Data shape compatibility checked
- [ ] Temporal structure correctly classified
- [ ] Comparability checked
- [ ] Table/Matrix retained as first-class options
- [ ] NO_VALID_VISUAL allowed
- [ ] Candidate/rejection reasons logged

## M. Generation routing

- [ ] Effective route resolved at necessary semantic granularity
- [ ] Visual Type unchanged
- [ ] Exact quantitative geometry uses qualified route
- [ ] Meaning-critical topology uses qualified route
- [ ] Exact Text uses authoritative-string route
- [ ] Asset contract enforced
- [ ] Data egress/privacy policy enforced
- [ ] Engine/model/renderer version qualification recorded
- [ ] Fallback cannot degrade semantics
- [ ] Verification path exists for each meaning-critical component
- [ ] Protected Semantic Layer plan defined

## N. Visual Generation Contract / Prompt Compiler

- [ ] Approved Semantic Page Graph is input
- [ ] Lock levels assigned
- [ ] Mandatory Content Object Register complete
- [ ] Exact Text Register complete
- [ ] Visual Semantic Contract complete
- [ ] Layout Freedom Envelope complete
- [ ] Presentation vs Clinical/Risk priority separated
- [ ] Asset Contract complete
- [ ] FULL_IMAGE or CONTROLLED_COMPOSITION declared
- [ ] Prohibited Transformations declared
- [ ] Post-generation Verification Contract complete
- [ ] Model-specific prompt generated
- [ ] Prompt contains no unapproved medical semantics

## O. Page generation / controlled composition

- [ ] Editorial base generated only in authorized regions
- [ ] Deterministic charts rendered where required
- [ ] Deterministic diagrams rendered where required
- [ ] Exact text overlaid where required
- [ ] Citation/source overlay applied where required
- [ ] Protected Semantic Layers are not generatively repainted
- [ ] Final asset flattened/versioned
- [ ] Generation Execution Provenance recorded

## P. Post-generation audit

For every generated page:
- [ ] Mandatory Object Coverage passed
- [ ] Exact Text passed
- [ ] Numeric Fidelity passed
- [ ] Relationship Fidelity passed
- [ ] Visual Semantic Fidelity passed
- [ ] Axis/legend/labels passed
- [ ] Citation/source passed
- [ ] Crop/occlusion/warp passed
- [ ] Protected Semantic Layer integrity passed
- [ ] QA result version recorded
- [ ] Failed page re-enters revision loop

## Q. Human review

- [ ] RED medical content reviewed
- [ ] High-risk synthesis reviewed
- [ ] Unresolved conflicts reviewed
- [ ] Extraction uncertainty reviewed
- [ ] Visual QA exceptions reviewed
- [ ] Human override, if any, logged
- [ ] Final approval state recorded

## R. Delivery

- [ ] Approved page images complete
- [ ] Presentation/slide package complete if requested
- [ ] Reference/appendix materials complete if requested
- [ ] Speaker notes complete if requested
- [ ] Evidence traceability material complete
- [ ] Medical Review Sheet complete
- [ ] No unapproved draft asset included

## S. Benchmark record

- [ ] Test result PASS / PARTIAL / FAIL recorded
- [ ] Page first-pass rate recorded
- [ ] Number of visual regeneration attempts recorded
- [ ] Numeric mutation count recorded
- [ ] Source traceability coverage recorded
- [ ] Human correction count recorded
- [ ] Unresolved issues recorded
- [ ] Lessons learned recorded
- [ ] New candidate regression tests recorded
- [ ] Workflow-change proposal opened if process deficiency discovered

## Blocking rule

If any mandatory non-negotiable gate is unchecked, the run must not be labelled `APPROVED_REFERENCE_OUTPUT`.
