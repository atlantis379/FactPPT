# Native-editable PPTX Beautification MVP v0.1

## Outcome

Transform an approved Semantic Deck into a polished 16:9 PPTX whose titles, claims, provenance labels, source footer and explicit relationship connectors remain native PowerPoint objects. Beautification is a display transformation, not a semantic authoring stage.

## Two-stage contract

1. Compile `native_beautification_plan.v0.1` from the approved Semantic Deck.
2. Validate page identity, Claim/Relationship coverage, exact Claim text, geometry and source ownership.
3. Render only a validated plan with a qualified native-object renderer.
4. Export PPTX plus a per-page review PNG and retain the plan as audit evidence.
5. Run semantic/package checks and visual inspection before delivery.

The compiler evaluates exactly five MVP archetypes: `EDITORIAL_STATEMENT`, `EVIDENCE_CARDS`, `COMPARISON_COLUMNS`, `DECISION_FLOW` and `TIMELINE`. It records all candidate scores and rejection reasons. Selection is deterministic for the same Semantic Deck and design tokens. When a validated editorial underlay is present, the compiler also selects the corresponding native-layer fusion variant and applies its declared palette, safe zones and surface policy.

## Capacity and no-loss behavior

- Each MVP page accepts one to four approved Claims.
- A page with zero Claims, more than four Claims, duplicate Claim IDs, an out-of-page Relationship endpoint, or no density-safe candidate is blocked.
- The compiler must request PageSpec revision/splitting. It must not truncate, summarize, rewrite, shrink below legibility, or omit content to make the page fit.
- Every approved Relationship on the page is rendered as a named connector, even when the selected archetype is not `DECISION_FLOW`; `FORWARD`, `BIDIRECTIONAL` and `NONE` endpoint semantics are preserved.

## Native-object ownership

These roles remain native and editable: title, primary message, Claim text, numeric evidence, source footer, provenance labels and Relationship connectors. Object names bind to semantic IDs, for example `claim:<id>` and `clinical_relationship:<id>`. Speaker notes retain sources, Claim IDs, selected archetype and active fusion variant.

## Optional ChatGPT Image / Figma layer

External visual providers are extension points, disabled by default. The ChatGPT Image route is implemented by [its dedicated underlay contract](CHATGPT_IMAGE_EDITORIAL_UNDERLAY_v0.1.md). External providers may provide only:

- background texture;
- decorative illustration;
- non-semantic icon.

They may not own, rasterize, restate or repaint protected native roles. Each accepted external asset requires provider/model or Figma-file provenance, prompt/version where applicable, SHA-256, license/usage status, a declared safe region and a final rendered-page review. A provider failure falls back to the native plan without changing semantics.

## Acceptance

- Plan schema and cross-reference validation PASS.
- PPTX package opens and reimports.
- Exact title, primary message, Claim text, Claim IDs, Relationship IDs, sources and notes PASS.
- No flattened picture object is present in the native-only MVP route.
- Every slide is rendered and inspected for overflow, overlap, wrapping and connector collision.
- An active editorial underlay has a validated fusion theme; native Claim surfaces use translucent/open treatments, preserve the protected decoration zone and do not revert to opaque generic white panels.
- Delivery remains subject to independent medical, privacy and human-review gates.
