"""Command-line entry point for the native-editable beautification MVP."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.packager import build_pptx, verify_pptx
from app.layout_ir import design_brief
from app.native_beautifier import compile_beautification_plan
from app.delivery_evidence import (make_quality_report, validate_quality_report,
                                   write_quality_report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Beautify an approved Semantic Deck as native editable PPTX objects.")
    parser.add_argument("semantic_deck", type=Path)
    parser.add_argument("output_pptx", type=Path)
    parser.add_argument("--plan", type=Path, help="Write the inspectable BeautificationPlan JSON.")
    parser.add_argument("--layout-ir", type=Path, help="Validated model layout intent JSON; semantic text remains locked.")
    parser.add_argument("--layout-brief", type=Path, help="Write the model-facing layout design brief JSON.")
    parser.add_argument("--preview-dir", type=Path, help="Write a PNG and layout JSON for every slide.")
    parser.add_argument("--editorial-asset", type=Path, action="append", help="Validated ChatGPT Image editorial asset manifest; repeat for multiple assets.")
    parser.add_argument("--finalize", action="store_true", help="Run package, layout, font and first-party reimport validation.")
    parser.add_argument("--validation-receipt", type=Path, help="Required with --finalize; must be outside the PPTX output directory.")
    parser.add_argument("--quality-report", type=Path, help="Stage and PPTX quality receipt; defaults to OUTPUT.pptx.quality.json.")
    args = parser.parse_args()
    if args.finalize and args.validation_receipt is None:
        parser.error("--validation-receipt is required with --finalize")
    deck = json.loads(args.semantic_deck.read_text(encoding="utf-8"))
    layout_ir = json.loads(args.layout_ir.read_text(encoding="utf-8")) if args.layout_ir else None
    if args.layout_brief:
        args.layout_brief.parent.mkdir(parents=True, exist_ok=True)
        args.layout_brief.write_text(json.dumps(design_brief(deck), ensure_ascii=False, indent=2), encoding="utf-8")
    build_pptx(
        deck,
        args.output_pptx,
        plan_target=args.plan,
        preview_dir=args.preview_dir,
        finalize=args.finalize,
        validation_receipt=args.validation_receipt,
        editorial_asset_manifest=args.editorial_asset,
        layout_ir=layout_ir,
    )
    result = verify_pptx(deck, args.output_pptx, editorial_asset_manifest=args.editorial_asset,
                         layout_ir=layout_ir)
    if result["status"] == "PASS":
        from app.editorial_assets import load_editorial_asset_manifest
        from app.packager import WORKSPACE
        assets = [load_editorial_asset_manifest(item, workspace=WORKSPACE)
                  for item in (args.editorial_asset or [])]
        plan = compile_beautification_plan(deck, editorial_assets=assets, layout_ir=layout_ir)
        report = make_quality_report(
            deck, plan, args.output_pptx, result, layout_ir=layout_ir,
            editorial_asset_sha256s=[item["sha256"] for item in assets],
            finalizer_receipt=args.validation_receipt if args.finalize else None)
        validate_quality_report(report, deck, plan, args.output_pptx, layout_ir=layout_ir,
                                editorial_asset_sha256s=[item["sha256"] for item in assets],
                                finalizer_receipt=args.validation_receipt if args.finalize else None)
        report_path = args.quality_report or args.output_pptx.with_suffix(args.output_pptx.suffix + ".quality.json")
        write_quality_report(report_path, report)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
