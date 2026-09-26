# Page Privacy and Document Surface Gate v0.1

Status: `ACTIVE_SKILL_CONTRACT_NOT_FROZEN_SPEC`

This contract adds deterministic sub-gates without renumbering W00–W18. It does not claim that regex, OCR or a model alone establishes legal compliance.

## Gate placement

1. `W00-SI Source Intake`: before parsing, validate HTTP status, final URL, redirect chain, declared Content-Type, file extension, magic bytes, byte length and SHA-256 with `source-intake`.
2. `W01-DS Document Structure`: after extraction, register every page, corrupted/image-only page, table continuation, footnote/cell ownership, OCR/render route and DICOM asset with `document-structure`.
3. `W15-PRIV Page Privacy`: after the final artifact exists, review every page and every required privacy surface with `privacy-gate`. Bind residual and cross-page consistency results to the exact final artifact hash.
4. W12 data-egress clearance consumes the most recent applicable privacy decision; it does not produce or redefine it.

## Required per-page privacy surfaces

Every page records exactly these surfaces:

- `TEXT_LAYER`;
- `SPEAKER_NOTES`;
- `EMBEDDED_IMAGE_OCR`;
- `DICOM_METADATA`;
- `DICOM_PIXEL_OVERLAY`;
- `FACE_OR_DISTINCTIVE_MARK`;
- `DOCUMENT_METADATA`;
- `FILENAME_ATTACHMENT_NAME`.

`NOT_APPLICABLE` is allowed only with a page-specific reason. `NOT_TESTABLE`, `NEEDS_REVIEW` and `BLOCK` are never delivery clearance. A PASS needs evidence references. Do not infer that a surface is absent merely because text extraction is empty.

Classify findings separately as patient identifiers, quasi-identifiers, public author/institution contacts or ordinary clinical context. A generic e-mail match is not enough to call content patient data. Quasi-identifiers require combination-risk review. Publication consent is not a de-identification result.

If any transformation occurred, run a residual scan on the transformed artifact and verify cross-page pseudonym/date-shift consistency. Both records bind the exact final artifact SHA-256. Date transformation must preserve clinically meaningful intervals and event order or return to semantic review.

The reference validator checks evidence completeness and gate logic. Actual text extraction, OCR, face review, DICOM inspection and metadata removal must be performed by declared, qualified tools or independent reviewers. OCR is a privacy-discovery surface; it is not sole authority for RED exact medical text.

## Cross-page tables and document structure

Every multi-page table has a continuation-group ID, contiguous page membership, repeated-header verification, footnote ownership and cell ownership. Corrupt, image-only or unexplained empty extraction requires rendered inspection and OCR. A page containing RED exact text cannot use `OCR_ONLY` as authority.

Every DICOM asset separately records metadata scan and burned-in pixel scan. Missing capability is `NOT_TESTABLE`, not PASS. Store only de-identified evidence needed for the audit.

## Blocking rules

- Source identity or MIME/magic/hash mismatch blocks W01.
- Silent page omission, unresolved table continuation or required OCR/render review blocks W02-FSC.
- Any missing or uncleared page/privacy surface blocks W17.
- Residual/cross-page results not bound to the final artifact hash block W17.

Run:

```text
python scripts/skill_tool.py source-intake SOURCE_INTAKE.json --root EVIDENCE_ROOT
python scripts/skill_tool.py document-structure DOCUMENT_STRUCTURE.json
python scripts/skill_tool.py privacy-gate PRIVACY_SURFACE_AUDIT.json
```

