# Reliable PPT v0.3 Agent Governance Pack

Start here:
1. Read `AGENTS.md`.
2. Read `docs/specs/DEVELOPMENT_CONTRACT.md`.
3. Read `docs/specs/SYSTEM_SPEC_v0.3.md`.
4. Follow the active M0 contract in `docs/milestones/CURRENT.md`.
5. Run `python -m unittest discover -s tests/governance -v` and `python tools/governance/check.py --changed-file <path>` for local checks.
6. Complete independent audit and CI before marking M0 frozen. Future v0.2 schemas require an explicit frozen-manifest entry and a later milestone.

## Teaching-layout deck

This package has no HTTP `/api/deck`. The default generation entry is `factdeck.deck.build_deck`. `python -m factdeck.render` measures those pages; it does not fill slides on a second path.

`build_deck` slims a SUMMARY, selects a teaching layout, and renders it with `factdeck.html_templates.render_html`. Fact text on the page is whatever the display fact gate admits. A rejected or unreviewed fill is left out of the HTML. A dangling half-sentence is omitted with its bullet or slot. Chapter limits are `max_sections`, `max_pages`, and `bullets_per_section` on that call (`factdeck.summary.ChapterLimits`). The same entry refuses an equal card wall when admitted facts do not differentiate the peer cards. Cover, section, and comparison have no body template here.

## Pipeline order

Deck generation in this package follows this order:

1. INGEST → UNITS. Unchanged. Not implemented here.
2. SEMANTIC_MAP (`semantic_map.v1`). What the material is about.
3. CLAIMS. Verbatim spans attached under those nodes.
4. SUMMARY, then SUMMARY_REVIEW.
5. FACTS gate → slot pairing → PPT.

`factdeck.semantic_map.parse_semantic_map` checks the map. `one_liner` and each node `thesis` are one sentence and must not contain decimal digits, so the map cannot add a clinical quantity. Node `role` is `definition`, `burden`, `assessment`, `pathway`, `indication`, `table`, `followup`, or `other`. `unit_hints` are hints only. Optional `edges` use `sequence`, `contrast`, `condition`, or `evidence`. Edges are stored and checked. They are not Approved Relations, and they do not reorder chapters.

`attach_claims` runs only with a map. Each claim needs `claim_id`, verbatim `text`, `source_text` (the original span), and `source_span_ids`. `text` must be an exact substring of `source_text`. `semantic_node_id` is required. A missing id, an unknown id, or the reserved id `unassigned` stays in the `unassigned` bucket and is not copied onto another node. This field is a factdeck attachment. The frozen v0.2 Claim schema is unchanged.

`summary_from_semantic_map` orders chapters mainline-first, then the other nodes, preserving relative order. A node with no key points is still a chapter: `max_sections` counts it, and it emits no page. A key point must cite `claim_ids` from its own node. `classify_key_points` flags `WRONG_NODE`. The summary and `build_deck` reject that flag. Bullet strings are copied into the existing slim pass, which still applies the fact gate and the half-sentence rule. `build_deck(..., semantic_map=, key_points=, claims=)` uses this path. Calling `build_deck` with slides and no map is unchanged.

Frozen spec stage names in `docs/specs/SYSTEM_SPEC_v0.3.md` §17.1 (`parse_document`, `segment_document`, `extract_claims`, `build_slide_plans`, and the rest) are not renamed. M0 stays frozen.

### In this repository

| Stage | Entry |
| --- | --- |
| SEMANTIC_MAP | `factdeck.semantic_map.parse_semantic_map` |
| CLAIMS | `factdeck.semantic_map.attach_claims` |
| SUMMARY | `factdeck.semantic_map.summary_from_semantic_map` |
| FACTS | `factdeck.facts.gate_display` |
| SLOTS | `factdeck.slots.trace_slide` |
| PPT | `factdeck.deck.build_deck` |

### Residual for local FactPPTv2

- No `src/` worker. Ingest and unit segmentation are absent (`parse_document`, `segment_document`, `materialize_source_spans`).
- No LLM call and no prompt that proposes a semantic map. This tree only validates `semantic_map.v1`.
- No claim extractor. Callers pass spans that were already cut. Without `source_text`, verbatim cannot be checked, and the validator rejects the claim.
- No SUMMARY_REVIEW queue. The handoff is `attach_claims(...).unassigned` plus a `WRONG_NODE` flag. This PR does not render that bucket.
- `semantic_node_id` is not added to the frozen v0.2 Claim schema. Editing `docs/specs/` or `schemas/v0_2/` needs an approved change request.
- No artifact store and no idempotency-key rerun for SEMANTIC_MAP (IDEMP-001). The validator does not write history.
- Summary bullets keep the first `source_span_id`. The claim record keeps the full list.
- Map edges do not become graph relations and do not change chapter order.
