#!/usr/bin/env python3
"""Render pharma chart-led template previews → HTML + PNG (1280×720 @2x) + layout QA.

Usage: .venv/bin/python tools/render_pharma_previews.py [--out DIR] [--only STEM]

QA (Playwright measure): every [data-check=fit] box must not scroll/clip; every element
inside a slide must stay within the 1280×720 canvas; SVG text bboxes must stay inside their
<svg>; body blocks must not overlap the footer.  Exit code 1 when any check fails.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factdeck import template_lib as tl
from factdeck.template_lib.pharma_fixtures import PAGES

THEME = "gold_clinical"

from factdeck.template_lib.measure import MEASURE_JS  # noqa: E402  (moved; re-exported for older imports)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/workspace/sync/template-lib-pharma")
    ap.add_argument("--only", default=None)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = []
    for stem, family, variant, fill in PAGES:
        if args.only and not any(o in stem for o in args.only.split(",")):
            continue
        rep = tl.validate_fill(family, fill, variant=variant)
        if not rep["ok"]:
            print("INVALID", stem, rep["errors"])
            return 1
        html = tl.render_deck_html([{"family": family, "fill": fill, "variant": variant}], theme=THEME)
        p = out / f"{stem}.html"
        p.write_text(html, encoding="utf-8")
        jobs.append((stem, p))

    from playwright.sync_api import sync_playwright

    qa = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=2)
        for stem, p in jobs:
            page.goto(p.as_uri())
            page.wait_for_timeout(150)
            issues = page.evaluate(MEASURE_JS)
            qa[stem] = issues
            page.locator(".slide").first.screenshot(path=str(out / f"{stem}.png"))
            print(f"{stem}: {'OK' if not issues else f'{len(issues)} issue(s)'}")
            for it in issues[:12]:
                print("   ", json.dumps(it, ensure_ascii=False))
        browser.close()
    (out / "qa-measure.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if any(qa.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
