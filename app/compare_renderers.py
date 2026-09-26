"""Run the current renderer and PptxGenJS against one frozen Layout IR.

This is a qualification tool, not a production renderer switch. Both outputs
receive the same Semantic Deck and native-object readback checks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

from app.layout_ir import semantic_digest
from app.native_beautifier import compile_beautification_plan
from app.packager import DEFAULT_PPTXGENJS_MODULE, build_pptx, verify_pptx


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODULE = DEFAULT_PPTXGENJS_MODULE


def _render_with_powerpoint(paths: dict[str, Path], output_dir: Path) -> dict[str, int]:
    import win32com.client

    result: dict[str, int] = {}
    app = win32com.client.Dispatch("PowerPoint.Application")
    try:
        for label, source in paths.items():
            folder = output_dir / f"{label}_powerpoint_png"
            folder.mkdir(parents=True, exist_ok=True)
            presentation = app.Presentations.Open(str(source.resolve()), ReadOnly=True, WithWindow=False)
            try:
                for index in range(1, presentation.Slides.Count + 1):
                    presentation.Slides(index).Export(str(folder / f"{index:02d}.png"), "PNG", 1280, 720)
                result[label] = presentation.Slides.Count
            finally:
                presentation.Close()
    finally:
        app.Quit()
    return result


def compare(deck: dict, output_dir: Path, *, layout_ir: dict | None = None,
            module_path: Path = DEFAULT_MODULE, powerpoint_render: bool = False) -> dict:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if not module_path.exists():
        raise FileNotFoundError(f"PptxGenJS comparison module is unavailable: {module_path}")
    plan = compile_beautification_plan(deck, layout_ir=layout_ir)
    plan_path = output_dir / "layout-plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    outputs = {"artifact_tool": output_dir / "artifact_tool.pptx",
               "pptxgenjs": output_dir / "pptxgenjs.pptx"}
    started = time.perf_counter()
    build_pptx(deck, outputs["artifact_tool"], layout_ir=layout_ir, mark_operation=False,
               preview_dir=output_dir / "artifact_tool_preview", writer="artifact_tool")
    artifact_seconds = time.perf_counter() - started
    started = time.perf_counter()
    subprocess.run(["node", str(Path(__file__).with_name("pptxgenjs_writer.mjs")),
                    str(plan_path), str(outputs["pptxgenjs"]), str(module_path.resolve()), str(ROOT)],
                   check=True, capture_output=True, text=True)
    pptxgenjs_seconds = time.perf_counter() - started
    verifications = {label: verify_pptx(deck, path, layout_ir=layout_ir)
                     for label, path in outputs.items()}
    rendered = _render_with_powerpoint(outputs, output_dir) if powerpoint_render else {}
    report = {"schema_version": "renderer-comparison.v1", "semantic_digest": semantic_digest(deck),
              "layout_ir_sha256": hashlib.sha256(json.dumps(layout_ir, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
              "slide_count": len(deck.get("pages", [])), "plan_text_fit": plan["text_fit"],
              "results": {label: {"path": str(path), "bytes": path.stat().st_size,
                                  "build_seconds": round(artifact_seconds if label == "artifact_tool" else pptxgenjs_seconds, 3),
                                  "verification_status": verifications[label]["status"],
                                  "verification_issues": verifications[label]["issues"],
                                  "powerpoint_png_count": rendered.get(label)}
                          for label, path in outputs.items()},
              "decision": "VISUAL_REVIEW_REQUIRED"}
    (output_dir / "comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("semantic_deck", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--layout-ir", type=Path)
    parser.add_argument("--pptxgenjs-module", type=Path, default=DEFAULT_MODULE)
    parser.add_argument("--powerpoint-render", action="store_true")
    args = parser.parse_args()
    deck = json.loads(args.semantic_deck.read_text(encoding="utf-8"))
    layout_ir = json.loads(args.layout_ir.read_text(encoding="utf-8")) if args.layout_ir else None
    report = compare(deck, args.output_dir, layout_ir=layout_ir,
                     module_path=args.pptxgenjs_module, powerpoint_render=args.powerpoint_render)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item["verification_status"] == "PASS" for item in report["results"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
