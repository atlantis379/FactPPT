# Case Report Evidence Boundary v0.1

Read this reference whenever a user-supplied or externally retrieved source is a case report or case series.

A case report can directly support what was observed in that reported patient: presentation, tests, interventions, relative chronology, outcome and author-described interpretation. It does not by itself establish population efficacy, universal diagnostic sufficiency, causal effect or a clinical recommendation.

Before a case-derived statement expands beyond `SINGLE_CASE` or `CASE_SERIES_DESCRIPTIVE`, or changes from observation/sequence to causality, efficacy, diagnostic sufficiency or population recommendation, require all three:

1. provenance is `SYNTHESIS`;
2. independent external support is explicitly bound;
3. human medical review is `APPROVED`.

Even with those three, the final wording must identify the source functions separately; do not make the case report appear to be the evidentiary basis for the population claim. Publication consent does not prove presentation-level de-identification.

Validate the structured review with:

```text
python scripts/skill_tool.py case-boundary CASE_BOUNDARY_REVIEW.json
```

