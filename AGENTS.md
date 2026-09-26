# FactPPTv2 — 57098 workflow

Read `docs/FACTPPTV2.md` before processing a project. This repository is independent
of the migration source. All runtime paths resolve from this repository root.

## Codex collaboration

- The app owns immutable sources, summaries, page contracts, approvals and jobs.
- Claim tasks with `tools/codex_worker.py`; inspect the claimed brief and complete
  every requested source unit. PDFs/PPTX/images/tables require visual inspection
  of originals when the contract says so. Do not claim inspection you did not do.
- Summaries cover all source units and teaching outline items. Preserve doses,
  thresholds, operators, populations, limitations and uncertainty.
- Only image jobs call the native `image_gen` tool. Generate the COMPLETE slide
  page with all locked text. Never substitute a PPT render, programmatic image,
  background or source image. Each receipt must report its actual tool call.
- Use the claimed five-part prompt and current approved sample reference. Store
  actual output PNG through the image completion endpoint; don't leave the app
  dependent on a Codex-private output directory.
- For a failed call report failure; don't fabricate model output or receipts.
- The model may provide preliminary QA; it cannot approve medical text or customer
  confirmation. Stop at customer content/style gates and human page review.
- READ_SOURCE/SUMMARY/PAGE_PLAN outputs are source-grounded authored JSON, not
  deterministic generated medical statements. No external research by default.

## Development

Preserve legacy semantic endpoints and their safeguards. Full-slide image mode is
an explicitly separate output workflow; it does not qualify ImageGen as an exact
text renderer for the legacy pipeline. SQLite transactions serialize job claims;
do not replace them with concurrent writes to `data/projects.json`.

The UI must use the licensed template selected by the user (MIT or a purchased
commercial template). Do not invent a replacement visual shell. Preserve the
selected template's license; do not treat premium addons as free MIT components.
