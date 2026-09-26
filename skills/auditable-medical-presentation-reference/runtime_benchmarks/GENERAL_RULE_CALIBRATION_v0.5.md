# General rule calibration v0.5

Run from the Skill root or use absolute script paths. Outputs go to new directories outside the immutable package.

1. `python scripts/run_benchmarks.py --out OUTPUT_A --font CJK_FONT --symbol-font SYMBOL_FONT`
2. `python scripts/run_quality_benchmarks.py --out OUTPUT_B`
3. `python scripts/skill_tool.py qualification OUTPUT_A/qualification.json --root OUTPUT_A`
4. `python scripts/skill_tool.py qualification OUTPUT_B/qualification.json --root OUTPUT_B`

The first suite exercises exact data/context, logical reconstruction, stage/subgate consistency, explicit glyph resources and protected composition. The second exercises independently read simple-SVG geometry plus anchored coverage and narrative-oracle calibration. Every case saves the tested input, actual result and hashes; failures are retained. A negative fixture succeeds only when the checker actually rejects it.

Use `scripts/evaluate_quality.py` with explicit contracts to apply checkers to real artifacts. Syntax and required arguments are discoverable through each subcommand's `--help`. `pptx` accepts a family-to-font-file JSON map and any one-based slide number; evaluate every page required by the delivery contract. It does not silently choose fonts.

Do not equate fixture success with real-source clinical correctness. Synthetic geometry data are not medical outcomes. Annotated coverage calibration tests can expose missed facts against an independent oracle; they cannot prove that an unknown real-source oracle is complete. Narrative annotations must independently bind actual assertion text, question coverage and dependencies. An original P05 quality FAIL can be a successful regression result when expected defects are detected.

Runtime fingerprints include source/schema versions, local dependency/platform information and font hashes where applicable. Keep the generated qualification file with all linked evidence; a copied runtime profile alone cannot grant a capability on a different host.
