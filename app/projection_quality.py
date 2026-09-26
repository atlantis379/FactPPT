"""Deterministic gate for source-bound academic projection samples.

This validates authored text, numerical locks, slide typography and package
editability. Actual PowerPoint PNG review remains a separate visual check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

from app.visual_prompt_contract import validate_deck


def contrast(foreground: str, background: str) -> float:
    def luminance(color: str) -> float:
        values = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
        rgb = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values]
        return .2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2]
    a, b = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (a + .05) / (b + .05)


def _ppt_slide_texts(pptx: Path, slide_number: int) -> list[str]:
    with zipfile.ZipFile(pptx) as package:
        xml = package.read(f"ppt/slides/slide{slide_number}.xml")
    root = ET.fromstring(xml)
    return [element.text or "" for element in root.iter()
            if element.tag == "{http://schemas.openxmlformats.org/drawingml/2006/main}t"]


def _legacy_expected(legacy_page: dict) -> dict[str, str]:
    raw = legacy_page["CONTENT_LOCK"]
    name = legacy_page["id"]
    if name == "05-severity-factors":
        return {"factor_local": raw["factors"][0],
                "factor_spread": raw["factors"][1],
                "factor_systemic": raw["factors"][2],
                "context": raw["context"], "caveat": raw["caveat"]}
    if name == "06-curb65":
        result = {f"c{i}_{part}": row[j]
                  for i, row in enumerate(raw["criteria"], 1)
                  for j, part in enumerate(("letter", "label", "value"))}
        result["caveat"] = raw["caveat"]
        return result
    if name == "07-pathogen-evidence":
        return {key: raw[key] for key in ("blood_sputum", "pleural", "contamination",
                                         "urine_antigen", "serology")}
    if name == "08-response-72h":
        result = {key: raw[key] for key in ("timepoint", "response", "condition")}
        result.update({f"s{i}_{part}": row[j]
                       for i, row in enumerate(raw["stability"], 1)
                       for j, part in enumerate(("label", "value"))})
        return result
    raise ValueError(f"Unknown inherited page: {name}")


def evaluate(contract: dict, legacy: dict | None, profile: dict, ledger: list[dict],
             pptx: Path, *, workspace: Path) -> dict:
    validate_deck(contract)
    failures: list[str] = []
    sources = {ref: {"document": record["document"], "sha256": record["sha256"]}
               for ref, record in contract["source_registry"].items()}
    for ref, record in sources.items():
        source = (workspace / record["document"]).resolve()
        if not source.is_file():
            failures.append(f"{ref}: source file missing")
        elif hashlib.sha256(source.read_bytes()).hexdigest() != record["sha256"]:
            failures.append(f"{ref}: source hash changed")
    if legacy is not None and len(contract["pages"]) != len(legacy["pages"]):
        failures.append("Canonical and inherited page counts differ")
    if legacy is not None and any(record["sha256"] != legacy["source_sha256"] for record in sources.values()):
        failures.append("Canonical and legacy source hashes differ")
    pptx_hash = hashlib.sha256(pptx.read_bytes()).hexdigest()
    for index, page in enumerate(contract["pages"], 1):
        content = page["CONTENT_LOCK"]
        actual = {b["id"]: b["text"] for b in content["text_blocks"]}
        if legacy is not None and index <= len(legacy["pages"]):
            old = legacy["pages"][index - 1]
            if content["page_id"] != old["id"]:
                failures.append(f"Slide {index}: page identity drift")
            if (content["title"] != old["CONTENT_LOCK"]["title"] or
                    content["subtitle"] != old["CONTENT_LOCK"]["subtitle"]):
                failures.append(f"Slide {index}: heading drift")
            if actual != _legacy_expected(old):
                failures.append(f"Slide {index}: medical CONTENT_LOCK differs from inherited PPT list")
        slide_ledger = [item for item in ledger if item["slide"] == index]
        used = Counter(item["content_id"] for item in slide_ledger if item["content_id"])
        if used != Counter({block_id: 1 for block_id in actual}):
            failures.append(f"Slide {index}: missing or repeated locked text boxes")
        try:
            slide_texts = Counter(_ppt_slide_texts(pptx, index))
            authored_texts = Counter(item["text"] for item in slide_ledger)
            if slide_texts != authored_texts:
                failures.append(f"Slide {index}: PPTX text differs from authoring ledger")
        except (KeyError, ET.ParseError):
            failures.append(f"Slide {index}: missing or invalid slide XML")
    minimum = profile["minimum_font_px"]
    contrast_min = profile["minimum_contrast"]["normal_text"]
    for item in ledger:
        role = item["role"]
        if item["font_size_px"] < minimum[role]:
            failures.append(f"Slide {item['slide']}: {role} below font floor")
        if item["auto_fit"] != "none":
            failures.append(f"Slide {item['slide']}: auto shrink enabled")
        ratio = contrast(item["color"], item["background"])
        if ratio < contrast_min:
            failures.append(f"Slide {item['slide']}: text contrast {ratio:.2f}:1 below {contrast_min}:1")
        x, y, w, h = item["box"]
        sw, sh = profile["slide_size_px"]
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x+w > sw or y+h > sh:
            failures.append(f"Slide {item['slide']}: text box outside slide")
    with zipfile.ZipFile(pptx) as package:
        slide_files = [name for name in package.namelist()
                       if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)]
        if len(slide_files) != len(contract["pages"]):
            failures.append("PPTX slide count differs from contract")
        for name in slide_files:
            slide_number = int(re.search(r"slide(\d+)\.xml", name).group(1))
            allowed = len(contract["pages"][slide_number-1]["VISUAL_METAPHOR"]["assets"])
            root = ET.fromstring(package.read(name))
            found = sum(element.tag == "{http://schemas.openxmlformats.org/presentationml/2006/main}pic"
                        for element in root.iter())
            if found > allowed:
                failures.append(f"{name}: {found} images exceed {allowed} declared visual assets")
    return {"schema_version": "academic-projection-qa.v1",
            "status": "PASS" if not failures else "FAIL", "failures": failures,
            "pptx_sha256": pptx_hash, "source_registry": sources,
            "slides": len(contract["pages"]), "text_boxes": len(ledger),
            "minimum_font_px": minimum, "minimum_normal_text_contrast": contrast_min,
            "claim_boundary": "Deterministic text/format/package gate; PowerPoint pixel review and clinical W16 are separate."}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--pptx", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--legacy", type=Path,
                        help="Optional inherited content list for an exact before/after lock")
    args = parser.parse_args()
    sample = args.sample_dir
    read = lambda name: json.loads((sample / name).read_text(encoding="utf-8"))
    legacy = json.loads(args.legacy.read_text(encoding="utf-8")) if args.legacy else None
    result = evaluate(read("content_contract.json"), legacy,
                      read("projection_profile.json"),
                      json.loads(args.ledger.read_text(encoding="utf-8")),
                      args.pptx, workspace=Path(__file__).resolve().parent)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
