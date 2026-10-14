"""Inspect a VISUAL_VECTOR result before submitting it.

Writes one sheet: clean PNG | Adobe SVG rendered by Chromium | native trace (what the
PowerPoint export receives). Use this instead of a generic SVG viewer: renderers without
linearGradient support paint gradient paths black, which looks like a vectorisation defect.
It renders files only; it never calls a model or Adobe.

    python tools/vector_preview.py --svg artwork.svg --clean clean.png --out vector_check.png
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from factdeck.visual_qa import vector_preview


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--svg", type=Path, required=True)
    parser.add_argument("--clean", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--task", type=Path, help="VISUAL_VECTOR task contract, to group paths by its layout components")
    args = parser.parse_args()
    components = ()
    if args.task:
        regions = json.loads(args.task.read_text(encoding="utf-8-sig"))["brief"].get("regions") or {}
        components = regions.get("native_regions") or ()
    print(json.dumps(vector_preview(args.svg.read_bytes(), args.clean, args.out, components), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
