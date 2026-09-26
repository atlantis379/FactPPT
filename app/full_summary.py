"""Validate and present a model-authored, source-located full-document summary.

The model writes the prose and chooses section boundaries. Code only checks identity,
coverage, references and shape; it never creates medical summary statements.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


SCHEMA_VERSION = "full_source_summary.v1"


def authoring_brief(reading: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    """Give a model the complete current source and citation IDs, without writing prose.

    The reading artifact records block identity and page location, but does not retain
    block text. The imported document's extracted page text is therefore the source
    shown to the author. A missing page is an error, never an invitation to summarize
    only what happened to be available.
    """
    source = reading.get("source") or {}
    count = source.get("unit_count")
    if not isinstance(count, int) or count < 1 or document.get("sha256") != source.get("sha256"):
        raise ValueError("Reading and imported document have no matching source identity")
    pages: dict[int, str] = {}
    for chunk in document.get("chunks") or []:
        page = chunk.get("page")
        if not isinstance(page, int) or page in pages:
            raise ValueError("Imported document has a missing or duplicate page number")
        pages[page] = str(chunk.get("text") or "")
    if set(pages) != set(range(1, count + 1)):
        raise ValueError("Imported document does not contain every source page")
    if any(not value.strip() for value in pages.values()):
        raise ValueError("Imported document has an empty extracted page; OCR or visual reading is required")
    block_ids: dict[int, list[Any]] = {page: [] for page in pages}
    for block in reading.get("blocks") or []:
        page = block.get("unit")
        if page not in block_ids:
            raise ValueError("Reading block refers to a page outside the source")
        block_ids[page].append(block["block_id"])
    if any(not refs for refs in block_ids.values()):
        raise ValueError("Reading has no block reference for a source page")
    return {
        "schema_version": SCHEMA_VERSION,
        "reading_structure_sha256": digest(reading),
        "source_sha256": source["sha256"],
        "source_filename": source.get("filename"),
        "pages": [{"page": page, "text": pages[page], "source_block_ids": block_ids[page]}
                  for page in range(1, count + 1)],
        "output_contract": {
            "overall_summary": "Model-authored synthesis of the full source, preserving limitations and uncertainty",
            "sections": ["section_id", "title", "summary", "source_block_ids"],
            "rules": ["Read every supplied page; do not omit a page because it is not selected for slides",
                      "Choose semantic sections from the material, not its page breaks",
                      "Cite block IDs on the page supporting each section; preserve source truth conditions",
                      "Do not add external medical facts or silently repair extraction errors"],
        },
    }


def digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def validate(summary: Any, reading: dict[str, Any]) -> list[str]:
    if not isinstance(summary, dict):
        return ["Summary must be a JSON object"]
    errors: list[str] = []
    source = reading.get("source") or {}
    if summary.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"Expected schema_version={SCHEMA_VERSION}")
    if summary.get("reading_structure_sha256") != digest(reading):
        errors.append("Summary is not bound to the current reading artifact")
    if summary.get("source_sha256") != source.get("sha256"):
        errors.append("Summary source sha256 does not match the reading")
    if len(str(summary.get("overall_summary") or "").strip()) < 40:
        errors.append("overall_summary must be substantive model-authored prose")
    sections = summary.get("sections")
    if not isinstance(sections, list) or not sections:
        return errors + ["sections must be a nonempty array"]
    blocks = {block.get("block_id"): block for block in reading.get("blocks") or []
              if isinstance(block, dict)}
    units_total = source.get("unit_count")
    expected_units = set(range(1, units_total + 1)) if isinstance(units_total, int) else set()
    covered_units: set[int] = set()
    seen_ids: set[str] = set()
    for index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            errors.append(f"Section {index} must be an object")
            continue
        section_id = str(section.get("section_id") or "").strip()
        if not section_id or section_id in seen_ids:
            errors.append(f"Section {index} has a missing or duplicate section_id")
        seen_ids.add(section_id)
        if not str(section.get("title") or "").strip():
            errors.append(f"Section {section_id or index} has no title")
        if len(str(section.get("summary") or "").strip()) < 30:
            errors.append(f"Section {section_id or index} has no substantive summary")
        refs = section.get("source_block_ids")
        if not isinstance(refs, list) or not refs:
            errors.append(f"Section {section_id or index} has no source block references")
            continue
        if any(not isinstance(ref, (str, int)) or isinstance(ref, bool) for ref in refs):
            errors.append(f"Section {section_id or index} has malformed source block references")
            continue
        if len(refs) != len(set(map(str, refs))):
            errors.append(f"Section {section_id or index} repeats source block references")
        unknown = [ref for ref in refs if ref not in blocks]
        if unknown:
            errors.append(f"Section {section_id or index} cites unknown blocks {unknown[:5]}")
        covered_units.update(blocks[ref]["unit"] for ref in refs if ref in blocks)
    missing = sorted(expected_units - covered_units)
    if missing:
        errors.append(f"Summary cites no block from source page(s) {missing}")
    if covered_units - expected_units:
        errors.append("Summary cites blocks outside the declared source page range")
    return errors


def with_locations(summary: dict[str, Any], reading: dict[str, Any]) -> dict[str, Any]:
    """Return explicit page and block locators; preserve authored prose unchanged."""
    blocks = {block["block_id"]: block for block in reading.get("blocks") or []}
    source = reading.get("source") or {}
    sections = []
    for section in summary["sections"]:
        rendered = dict(section)
        rendered["sources"] = [{"filename": source.get("filename"),
                                "source_sha256": source.get("sha256"),
                                "page": blocks[ref]["unit"], "block_id": ref}
                               for ref in section["source_block_ids"]]
        sections.append(rendered)
    return {**summary, "sections": sections}
