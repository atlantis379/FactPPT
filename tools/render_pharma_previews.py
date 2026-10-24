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

MEASURE_JS = r"""
() => {
  const out = [];
  const slide = document.querySelector('.slide');
  const S = slide.getBoundingClientRect();
  const tol = 1.5;
  slide.querySelectorAll('[data-check="fit"]').forEach(el => {
    if (el.scrollHeight > el.clientHeight + tol || el.scrollWidth > el.clientWidth + tol) {
      out.push({kind:'overflow', slot: el.dataset.slot || el.className,
        sh: el.scrollHeight, ch: el.clientHeight, sw: el.scrollWidth, cw: el.clientWidth});
    }
  });
  // text clipped by ellipsis / overflow hidden
  slide.querySelectorAll('.htitle,.sub,.foot .row,.p,.d').forEach(el => {
    if (el.scrollWidth > el.clientWidth + tol) out.push({kind:'ellipsis', slot: el.dataset.slot || el.className,
      sw: el.scrollWidth, cw: el.clientWidth});
  });
  slide.querySelectorAll('*').forEach(el => {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return;
    if (r.left < S.left - tol || r.top < S.top - tol || r.right > S.right + tol || r.bottom > S.bottom + tol) {
      out.push({kind:'outside', tag: el.tagName, cls: String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className),
        r: [r.left - S.left, r.top - S.top, r.right - S.left, r.bottom - S.top].map(Math.round)});
    }
  });
  slide.querySelectorAll('svg').forEach(svg => {
    const B = svg.getBoundingClientRect();
    svg.querySelectorAll('text').forEach(t => {
      const r = t.getBoundingClientRect();
      if (r.left < B.left - tol || r.right > B.right + tol || r.top < B.top - tol || r.bottom > B.bottom + tol)
        out.push({kind:'svg-text-outside', text: t.textContent.slice(0, 24),
          r: [r.left - B.left, r.top - B.top, r.right - B.left, r.bottom - B.top].map(Math.round), box: [B.width, B.height]});
    });
  });
  // HTML text boxes inside svg-overlay containers (moa) must fit
  slide.querySelectorAll('[data-box]').forEach(el => {
    if (el.scrollHeight > el.clientHeight + tol || el.scrollWidth > el.clientWidth + tol)
      out.push({kind:'box-overflow', text: el.textContent.trim().slice(0, 20), sh: el.scrollHeight, ch: el.clientHeight});
  });
  const foot = slide.querySelector('.foot');
  const main = slide.querySelector('.main');
  if (foot && main) {
    const F = foot.getBoundingClientRect();
    main.querySelectorAll('*').forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.height && r.bottom > F.top + tol) out.push({kind:'overlaps-footer', tag: el.tagName,
        text: (el.textContent || '').trim().slice(0, 20), bottom: Math.round(r.bottom - S.top)});
    });
  }
  // SVG text vs SVG text collisions (labels overlapping each other)
  slide.querySelectorAll('svg').forEach(svg => {
    const ts = [...svg.querySelectorAll('text')].map(t => [t, t.getBoundingClientRect()]);
    for (let i = 0; i < ts.length; i++) for (let j = i + 1; j < ts.length; j++) {
      const a = ts[i][1], b = ts[j][1];
      const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (ox > 2 && oy > 3) out.push({kind:'svg-text-collision', a: ts[i][0].textContent.slice(0, 16), b: ts[j][0].textContent.slice(0, 16)});
    }
  });
  return out;
}
"""


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
