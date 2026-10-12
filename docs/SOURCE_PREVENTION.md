# Source bound content obligations

`factdeck.content_obligations` adds a deterministic validation step for a new
FactDeck proposal. It complements `factdeck.deck.check`; it does not replace its
verbatim fact gate or semantic review.

## API for the deck submission path

```python
from factdeck.content_obligations import build_obligations, validate_deck

contract = build_obligations(workflow, proposed_deck, verified_facts)
result = validate_deck(workflow, proposed_deck, verified_facts, ordinary_deck_check)
if result["errors"]:
    # reject the DECK submission with these blocking messages
    ...
# surface result["pending"] for selected facts needing human decisions
# show result["warnings"] when automatic source-to-primary mapping is ambiguous
```

`verified_facts` is the existing verified mapping (`{"facts": {fact_id: fact}}`);
`ordinary_deck_check` is the existing deck checker result. `build_obligations`
returns `obligations`, `semantic_bundles`, and `context_signals` for the worker
contract. It includes transcription units with current human/second-read
decisions applied, separate `transcription_proposals`, and facts carved into
the proposed deck. The submit path
should call this only for a new/revised DECK result;
legacy saved projects without these fields remain valid until submitted again.

## Recorded bundles

An explicit `workflow.semantic_bundles` record has this shape:

```json
{
  "id": "bundle-1",
  "role": "footnote",
  "source_unit_refs": ["S01:t1:para4"],
  "relationship_evidence": "S01:t1:para4",
  "primary_fact_refs": ["result-1"],
  "dependent_fact_refs": ["note-1"],
  "dependent_unit_refs": [],
  "adjacent_page_allowed": false,
  "relationship_status": "SUPPORTED"
}
```

Allowed roles are `population`, `condition`, `limit`, `footnote`, `list`, and
`context`. `relationship_evidence` must point to one of the cited source units.
No relationship is inferred from nearby wording. Use `UNKNOWN` or
`NEEDS_HUMAN` while the source does not establish the relationship; that record
is kept in `pending` and does not silently pass. A bundle must name at least one
primary and one dependent fact or unit. Every dependent fact must appear, and
each dependent unit must have a fact visible on the same page. Adjacent-page
coverage is allowed only when the record explicitly sets
`adjacent_page_allowed: true`.

The application owns persistence and should attach/record bundle proposals
through its normal transactional workflow interface. This module is read-only:
it does not update the workflow, source archive, or human confirmations.

## Automatic obligations and context responses

Claim `scope.population` and `scope.condition` values are used only when those
literal excerpts can be tied back to the claim's cited source unit. A candidate
dependent fact qualifies only when its actual displayed text (`display`, or
`quote` when no display is supplied) contains the excerpt. A quote whose display
cuts the excerpt does not qualify. A summary message role of `limit` binds the
corresponding `point_coverage.unit_ids`. Automatic primary mapping requires a
single claim source span, and a primary fact quote must contain the entire
span. A fact overlapping only one of several claim fragments is not treated as
the claim's primary fact. Ambiguous mappings are contract warnings rather than
pending decisions. An automatic obligation is enforced only if its primary
fact is actually used on a page. The builder does not infer population or
conditions from medical vocabulary.

Only strong lead-in and leading-connective signals for facts actually used on a
page require disposition. Unit-before/unit-after shapes remain review warnings.
Every required context signal (`fact_id:kind`) must have a DECK-level
`context_responses` row:

```json
{"signal_id":"result-1:unit_continues","state":"NEEDS_HUMAN",
 "evidence_refs":["S01:t1:para4"],"reason":"原文后续含列表，待人工确认是否完整呈现"}
```

`COVERED` requires source-related facts visible with the signal fact on the
same page, or on an adjacent page explicitly allowed by the response. An
unrelated page fact cannot close the signal. `EXCERPT` requires
evidence, a reason, and a `marker` string that appears in visible page text
(for example, “节选”). Neither state removes an independently created locked
source obligation. `NEEDS_HUMAN` requires a reason and is reported as pending;
it cannot close a binding. Focus and design metadata do not count as visible
evidence. Rendered page notes may count when the ordinary checker includes
them in the page fact list; speaker notes do not. Unknown, duplicate, or
irrelevant signal responses are rejected.

Any visible fact marked `needs_confirmation` is returned as pending. This lets
a reviewer revise the deck; the caller's formal-generation gate must reject a
pending transcription until an independent second read or human confirmation
is complete.

## Compatibility and boundary

Workflows without claim scopes, summary limit roles, explicit bundles, or
context signals produce no new errors. Old stored deck specifications are not
rewritten. The function validates source identifiers and visibility, but a
human reviewer still decides whether a source actually supports an asserted
relationship; ambiguous source relationships remain pending for that decision.
