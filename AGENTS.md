# FactPPTv2 — FactDeck mainline

Read `docs/FACTPPTV2.md` before processing a project. This repository is independent
of the migration source. All runtime paths resolve from this repository root.

The mainline is **FactDeck** (`factdeck.v1`, `/api/deck`): sources → summary → fact
store → deck spec → code-rendered native PPTX. The earlier full-slide image workflow
(`57098-full-slide.v1`, `/api/fact`) is kept for existing projects only.

The user selected visual route **A with native vectors** on 2026-10-01:
locked content/design → full design image with text → remove text → vectorize
artwork → native PPT shapes → locked native text/tables/data/connectors.
Read `docs/PPT_GENERATION_ROUTE.md` and its decision record. This is the selected
visual direction; the production API has not yet integrated these tool stages.

## Worker collaboration (mainline)

- The app owns immutable sources, units, summaries, fact stores, deck specs,
  confirmations, renders and jobs. Workers author JSON; code decides what is accepted.
- Claim tasks with `tools/codex_worker.py`; inspect the claimed brief and complete
  every requested page or unit. Pages marked `requires_visual` need visual inspection
  of the original. Do not claim inspection you did not do.
- READ_SOURCE: record every page; transcribe text and numbers in pictures/charts
  cell by cell exactly as seen; in diagrams, each box is a cell and each arrow a cell
  "start→end". Never guess or complete unreadable content.
- CLAIMS lists what each page of a source says: each claim is 1–8 verbatim spans
  (a sentence or a cell, never a whole page) with a type (recommendation, result,
  association, interpretation, …) and scope fragments; the source gets a profile
  (guideline, trial, promotional, …). Excerpt and label only; never reword or infer.
- SUMMARY covers all source pages and outline items, citing claims (`claim_ids`). Preserve doses, thresholds,
  operators, populations, limitations and uncertainty; list open questions.
  With a structured outline, each item gets a `message`: a verbatim core sentence
  (prefer the author's marked titles/emphasis), one role per point (exactly one core;
  limits must reach the pages) and relations, preferring the sources' candidates.
- FACTS: every fact is a verbatim quote of one source unit. `display` may only be
  an in-order excerpt of the quote — never reword, never drop a negation or
  qualifier. Anything non-verbatim goes into a named derivation for human review.
- DECK: substantive content is fact references only. Design the page first; when the
  store's facts are too coarse for a slot (label/value, flow node, table cell), carve
  new verbatim facts from source units in the deck's `facts` — same code gate, no
  derivations, each one used on a page. Authored text (titles, leads, labels)
  organises and names; it carries no numbers, comparisons, drug/entity names or
  evaluative wording. Mark each content page's `focus` from the item's core or relations.
  Choose layouts by content shape (flow/cards/compare/timeline/
  grid before bullets). Follow the project requirements; split dense pages.
  One page, one design solution: write each content page's `design` note first (what is seen
  first / read next / kept for reference / the one strong element and why), then choose a layout
  or compose the page (`composed`, `factdeck/compose.py`). Peers get identical treatment; a
  dropped scope label ("中国：") must be stated once on the page. Whitespace and repetition are
  signals: fix them for that page or give the reason in `design.exceptions`.
- SUMMARY_REVIEW, SEMANTIC_REVIEW and SECOND_READ must be done by a different worker
  identity than the author / first reader (SUMMARY_REVIEW also not by the claims author).
  SUMMARY_REVIEW judges every point ENTAILED / PARTIAL / NOT_ENTAILED / CONTRADICTED. Report problems honestly; never approve medical text.
- Route A may generate full-slide design references with text to establish the
  visual design. Generated text, numbers and medical relationships are not content
  authority. Remove design text, trace the actual artwork into native editable paths,
  group components, and fill native text/tables/data/connectors from locked facts.
  Do not substitute an embedded SVG or a whole-slide bitmap for native geometry.
  Partial texture loss is accepted. Use the current muted blue-gray palette as a
  starting point. Original source figures still follow `docs/FIGURE_REFERENCE.md`.
- Route A is the default production mainline. Start/resume with `generate`;
  the application queues VISUAL_DESIGN → VISUAL_LAYOUT → VISUAL_CLEAN → VISUAL_VECTOR.
  Use the existing Codex + Adobe execution endpoint, submit actual PNG/SVG with
  `asset` and the exact receipt contract, and layout JSON with `complete`.
  View actual design/clean outputs before claiming inspection. Do not edit locked
  content in layout results. Complete assets automatically trigger native compile
  and PowerPoint rendering; human gates remain mandatory. See docs/PPT_GENERATION_ROUTE.md.
- No external research by default. For a failed task report failure; don't
  fabricate results. Stop at customer confirmations, human confirmations and page review.

## Earlier full-slide image workflow (`/api/fact`, `--api fact`)

Only for existing projects on that workflow: image jobs call the native `image_gen`
tool, generate the complete slide with all locked text, use the claimed five-part
prompt and approved sample reference, and store the actual PNG through the image
completion endpoint with a receipt of the actual tool call. It does not qualify
ImageGen as an exact text renderer for any other pipeline.

## Development

Preserve legacy semantic endpoints and their safeguards. SQLite transactions
serialize job claims; do not replace them with concurrent writes to
`data/projects.json`. Keep factdeck domain-neutral: subject-specific vocabulary
belongs in project terms or `config/factdeck_lexicon.json`, not in code.

The UI must use the licensed template selected by the user (MIT or a purchased
commercial template). Do not invent a replacement visual shell. Preserve the
selected template's license; do not treat premium addons as free MIT components.
