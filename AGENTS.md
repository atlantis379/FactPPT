# FactPPTv2 — FactDeck mainline

Read `docs/FACTPPTV2.md` before processing a project. This repository is independent
of the migration source. All runtime paths resolve from this repository root.

The mainline is **FactDeck** (`factdeck.v1`, `/api/deck`): sources → summary → fact
store → deck spec → code-rendered native PPTX. The earlier full-slide image workflow
(`57098-full-slide.v1`, `/api/fact`) is kept for existing projects only.

## Worker collaboration (mainline)

- The app owns immutable sources, units, summaries, fact stores, deck specs,
  confirmations, renders and jobs. Workers author JSON; code decides what is accepted.
- Claim tasks with `tools/codex_worker.py`; inspect the claimed brief and complete
  every requested page or unit. Pages marked `requires_visual` need visual inspection
  of the original. Do not claim inspection you did not do.
- READ_SOURCE: record every page; transcribe text and numbers in pictures/charts
  cell by cell exactly as seen. Never guess or complete unreadable content.
- SUMMARY covers all source pages and outline items. Preserve doses, thresholds,
  operators, populations, limitations and uncertainty; list open questions.
- FACTS: every fact is a verbatim quote of one source unit. `display` may only be
  an in-order excerpt of the quote — never reword, never drop a negation or
  qualifier. Anything non-verbatim goes into a named derivation for human review.
- DECK: substantive content is fact references only. Authored text (titles, leads,
  labels) organises and names; it carries no numbers, comparisons, drug/entity
  names or evaluative wording. Follow the project requirements; split dense pages.
- SEMANTIC_REVIEW and SECOND_READ must be done by a different worker identity than
  the author / first reader. Report problems honestly; never approve medical text.
- No image generation for slides: text and decoration are rendered by code. Image
  models may only make text-free illustrations; generating them is not planned for the
  mainline (they carry meaning that no fact can back). Pictures from the originals
  enter only as source figures (`docs/FIGURE_REFERENCE.md`, designed, not built yet).
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
