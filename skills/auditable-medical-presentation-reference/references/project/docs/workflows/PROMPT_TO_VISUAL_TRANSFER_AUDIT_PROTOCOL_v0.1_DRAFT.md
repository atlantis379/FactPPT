# Prompt-to-Visual Transfer Audit Protocol v0.1

**Status:** `DRAFT_SKILL_POLICY_CANDIDATE`

## 1. Purpose

Audit whether an approved PageSpec and VisualSemanticContract are translated into model-specific prompts without semantic loss, then test whether repeated visual generations reliably preserve the intended visual semantics.

The prompt itself is not the source of truth. The chain is:

```text
Approved PageSpec
→ VisualSemanticContract
→ PromptSemanticSpec
→ EnginePrompt
→ PROMPT FIDELITY GATE
→ Generation
→ Visual QA / Stability Audit
```

## 2. Pre-generation prompt audit

Before any image is generated, compare `EnginePrompt` against `PromptSemanticSpec` and PageSpec.

Required checks:
- all required visual assertions represented;
- no forbidden medical assertion introduced;
- all protected topology constraints represented;
- all exact numeric/text items either protected for deterministic overlay or explicitly prohibited from free generation;
- no source material outside PageSpec is invited into the image;
- hierarchy/color/grouping instructions do not imply unsupported evidence strength, causality, sequence or comparison;
- one PageSpec maps to one page;
- source edition/publication metadata are not conflated.

## 3. Prompt semantic object

Each prompt compilation should expose:
- `required_visual_assertions[]`;
- `forbidden_visual_assertions[]`;
- `protected_topology[]`;
- `exact_overlay_objects[]`;
- `generative_freedom[]`;
- `prohibited_generated_text[]`;
- `page_goal_statement`;
- `primary_message_statement`;
- `visual_hierarchy_statement`;
- `expected_failure_modes[]`.

## 4. Prompt Fidelity Gate metrics

- `RequiredAssertionCoverage`;
- `ForbiddenAssertionLeakage`;
- `TopologyInstructionCoverage`;
- `ExactObjectRoutingCorrectness`;
- `PageGoalPromptAlignment`;
- `UnauthorizedSourceExpansionRisk`;
- `PromptAmbiguityCount`.

Prompt status:
- `PASS_FOR_GENERATION`;
- `PASS_WITH_WARNINGS`;
- `REVISE_PROMPT_COMPILER`;
- `BLOCK`.

## 5. Post-generation semantic transfer audit

For each generated image evaluate:
- PageGoal Fidelity;
- PrimaryMessage Fidelity;
- required-object coverage;
- unauthorized semantic additions;
- protected-topology fidelity;
- visual hierarchy fidelity;
- exact-text/numeric mutation if any generative text is present;
- crop/occlusion/legibility;
- provenance/citation layer integrity when composited.

## 6. Stability / repeatability benchmark

Accuracy alone is insufficient. For each engine + visual type + contract, generate repeated attempts under the same semantic contract.

Recommended reference benchmark:
- 3 attempts minimum for low-risk visual-base tasks;
- 5 attempts for semantically structured prompt-driven tasks where model variability matters.

Measure:
- `SemanticPassRate`;
- `UnauthorizedSemanticRate`;
- `TopologyPassRate`;
- `ExactTextMutationRate`;
- `PageGoalPassRate`;
- `InterRunStructureConsistency`;
- `MeanAttemptsToPass`.

A model that produces one good page among many unstable outputs is not qualified for authoritative rendering.

## 7. Route-sensitive acceptance

### Nonsemantic editorial base
Audit mainly:
- no unauthorized text;
- no medical claims/numbers;
- expected composition and safe whitespace;
- stable slot availability.

### Source reconstruction / protected topology
Prompt-driven generation is not authoritative unless topology and exact-object constraints are qualified and verifiable. Prefer deterministic rendering.

### Source/Narrative synthesis visual
Audit that the new visual grammar expresses only approved synthesis relationships and does not invent additional interpretation.

## 8. Failure routing

- prompt omits required meaning → earliest responsible stage `Prompt Compiler`;
- prompt contains correct contract but engine invents semantics → `Generation Capability` failure;
- visual reveals PageSpec ambiguity → route back to `PageSpec`;
- visual reveals unsupported synthesis → route back to `Narrative/PageSpec/Semantic Audit`;
- repeated failures → capability downgrade; do not keep retrying until a lucky output appears.

## 9. Proposed regression rules

- `REG-PROMPT-001`: Prompt must be auditable against a model-independent PromptSemanticSpec before generation.
- `REG-PROMPT-002`: Required and forbidden visual assertions must be explicit, not implicit prose only.
- `REG-PROMPT-003`: Exact medical text/numbers that require deterministic integrity must not be delegated to an unqualified image model.
- `REG-PROMPT-004`: Prompt may not invite source content outside the approved PageSpec.
- `REG-PROMPT-005`: A single successful stochastic output is insufficient evidence of engine qualification; repeatability must be measured.
- `REG-PROMPT-006`: Repeated semantic failure triggers capability downgrade instead of unlimited retries.
- `REG-PROMPT-007`: Prompt-to-visual accuracy and prompt-to-visual stability are separate acceptance dimensions.

These are draft policy candidates and do not alter frozen Module 01–06 rules until explicitly approved/frozen.
