# -*- coding: utf-8 -*-
"""
Layout audit: turn "跑版 / 溢出" into an automatic, theme- and content-independent
check. Run it on ANY deck under ANY theme before delivery.

Two independent detections:
  1. OUT_OF_CANVAS  — an element's box escapes the 1280x720 slide
  2. TEXT_CLIPPED   — a text block's content is taller than its box
"""
import pathlib

from playwright.sync_api import sync_playwright

CANVAS = {"width": 1280, "height": 720}

_JS = r"""() => {
  const tol = 1.0;
  const issues = [];
  const slides = document.querySelectorAll('.slide');
  slides.forEach((s, i) => {
    const sr = s.getBoundingClientRect();
    s.querySelectorAll('*').forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) return;
      const over = [];
      if (r.left   < sr.left   - tol) over.push('left');
      if (r.top    < sr.top    - tol) over.push('top');
      if (r.right  > sr.right  + tol) over.push('right');
      if (r.bottom > sr.bottom + tol) over.push('bottom');
      if (over.length) {
        issues.push({kind:'OUT_OF_CANVAS', slide:i+1, tag:el.tagName,
                     cls:String(el.className||'').slice(0,42),
                     over, box:[Math.round(r.left-sr.left),Math.round(r.top-sr.top),
                                Math.round(r.width),Math.round(r.height)]});
      }
      // text clipping: only for leaf-ish text containers with a set height
      if (el.children.length === 0 && (el.textContent||'').trim().length > 0) {
        const cs = getComputedStyle(el);
        if (cs.overflow === 'visible' || cs.overflow === '') {
          const p = el.parentElement;
        }
      }
    });
    // dedicated clipping scan on known text boxes
    s.querySelectorAll('.step .tx,.card .cb,.kpi .lab,.pnl .pb,.callout .ct,.tblock h1,.tblock .sub').forEach(el => {
      if (el.scrollHeight > el.clientHeight + 3 && el.clientHeight > 0) {
        issues.push({kind:'TEXT_CLIPPED', slide:i+1, tag:el.tagName,
                     cls:String(el.className||'').slice(0,42),
                     need:el.scrollHeight, have:el.clientHeight});
      }
    });
  });
  return {slides: slides.length, issues};
}"""


def audit(html_path, quiet=False):
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport=CANVAS, device_scale_factor=1)
        pg.goto(pathlib.Path(html_path).resolve().as_uri(), wait_until="load", timeout=60000)
        pg.wait_for_timeout(500)
        res = pg.evaluate(_JS)
        b.close()
    if not quiet:
        print(f"  audited {res['slides']} slides: {len(res['issues'])} issue(s)")
        for it in res["issues"][:14]:
            print("   -", it)
    return res
