#!/usr/bin/env python3
"""Template-library deck: plan → layout selector → HTML → Playwright measure → native PPTX (+ job stats).

Usage:
  .venv/bin/python tools/template_deck.py [--plan factdeck/examples/copd_layout_sample/plan.json]
         [--out output/template_deck] [--office-render] [--llm] [--font "Noto Sans CJK SC"]
  .venv/bin/python tools/template_deck.py --deck <project>/deck.json --facts <project>/facts_verified.json
         [--sources <project>/sources_manifest.json] --out output/<name>      # bound: trace.md / trace.json

Writes deck.pptx, pages/*.html|png (HTML previews), decisions.json (selector record per page), job.json
(pages, QA, native counts, verification) and job_stats.json (wall time per stage, model-call tokens).
The LLM tie-break is off unless --llm is given and EASYPPT_SEMANTIC_MODEL_* is configured.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factdeck.template_lib import integrate  # noqa: E402
from factdeck.template_lib import native as N  # noqa: E402
from factdeck.template_lib import pipeline  # noqa: E402
from factdeck.template_lib import selector as S  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=str(ROOT / "factdeck/examples/copd_layout_sample/plan.json"))
    ap.add_argument("--out", default=str(ROOT / "output/template_deck"))
    ap.add_argument("--office-render", action="store_true", help="LibreOffice → PDF → PNG of the written PPTX")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--font", default=N.DEFAULT_FONT)
    ap.add_argument("--no-previews", action="store_true")
    ap.add_argument("--deck", help="deck.json whose layout:template pages carry bound fills (needs --facts)")
    ap.add_argument("--facts", help="facts_verified.json: bind every fill to the fact store and write trace.md")
    ap.add_argument("--sources", help="sources_manifest.json ({source id: name}) for footers and the trace report")
    a = ap.parse_args()
    facts = sources = None
    glossary, terms = [], []
    if a.facts:
        fv = json.loads(Path(a.facts).read_text(encoding="utf-8"))
        facts = {f["id"]: f for f in fv["facts"]}
        terms = fv.get("terms", [])
    if a.sources:
        sources = json.loads(Path(a.sources).read_text(encoding="utf-8"))
    if a.deck:
        if facts is None:
            ap.error("--deck 需要 --facts（模板页的填充引用事实库）")
        deck = json.loads(Path(a.deck).read_text(encoding="utf-8"))
        plan = integrate.deck_plan(deck)
        glossary = [x["text"] for x in deck.get("glossary", deck.get("terms", []))]
    else:
        plan = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    tb = S.env_llm_tiebreaker() if a.llm else None
    rec = pipeline.run(plan, a.out, tiebreaker=tb, font=a.font, previews=not a.no_previews,
                       office_render=a.office_render, facts=facts, sources=sources, glossary=glossary, terms=terms)
    st = rec["stats"]
    print(json.dumps({"job_id": rec["job_id"], "pptx": rec["native"]["pptx"], "verify": rec["verify"],
                      "total_seconds": st["total_seconds"], "stage_seconds": st["stage_seconds"],
                      "tokens": st["tokens"]}, ensure_ascii=False, indent=1))
    bad = [p for p in rec["pages"] if p["status"] != "OK"]
    for p in bad:
        print("NOT RENDERED", p["page_id"], p["status"], p.get("errors") or p.get("fill_fallback"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
