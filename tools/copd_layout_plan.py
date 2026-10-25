#!/usr/bin/env python3
"""Build the COPD slide-level content plan used to exercise the layout selector.

Source material = the repo's COPD teaching sample (all already in the repo):
  * tests/test_template_lib_v1.py   — cover / section / key-points / comparison / flow / timeline fills
  * tools/render_gold_previews.py   — GOLD-density algorithm / ABE matrix / dual-path fills
  * factdeck/template_lib/pharma_fixtures.py — pharma chart-led fills (示例数据, fictional study names)

Each page keeps only *content*: title, flattened text strings (verbatim from the fill) and structured
data derived mechanically from the fill.  The original family is stored as ``origin_layout`` for
evaluation only; the selector never reads it.  ``fills`` keeps the original fill for rendering.
Pages in STRESS are constructed (marked ``constructed``) by cutting data out of the same sample to
exercise the downgrade chain — no new numbers are introduced.

Usage: .venv/bin/python tools/copd_layout_plan.py [--out factdeck/examples/copd_layout_sample/plan.json]
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factdeck.template_lib import pharma_fixtures as px  # noqa: E402
from tools import render_gold_previews as gold  # noqa: E402
from factdeck.template_lib.integrate import data_from_fill, flatten  # noqa: E402

DEMO = "示例数据，教学示意，非诊疗建议"
def _v1():
    spec = importlib.util.spec_from_file_location("tl_v1_fixtures", ROOT / "tests" / "test_template_lib_v1.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def page(pid, family, variant, fill, provenance, kind="content"):
    layout = family if not variant or family not in ("endpoint_readout", "key_points") else f"{family}/{variant}"
    if family == "key_points" and variant != "evidence_takeaways":
        layout = "key_points"
    return {"id": pid, "kind": kind, "title": fill.get("title"), "text": flatten(fill),
            "data": data_from_fill(family, variant, fill), "origin_layout": layout, "provenance": provenance,
            "constructed": False, "fills": {layout: fill}}


def build():
    v1 = _v1()
    V = "tests/test_template_lib_v1.py"
    G = "tools/render_gold_previews.py"
    P = "factdeck/template_lib/pharma_fixtures.py（示例数据）"
    deck = [
        page("cover", "cover", None, v1.COVER_ZH, V, kind="cover"),
        page("kp-3", "key_points", None, v1.KEY3_ZH, V),
        page("gold-algo", "algorithm_tree", None, gold.ALGO, G),
        page("flow-dx", "flow", None, v1.FLOW4_ZH, V),
        page("gold-abe", "assessment_matrix", None, gold.ABE, G),
        page("kp-6", "key_points", None, v1.KEY6_ZH, V),
        page("cmp-ae-stable", "comparison", None, v1.CMP_DUAL_ZH, V),
        page("gold-tx", "dual_path_tree", None, gold.TX, G),
        page("flow-step", "flow", None, v1.FLOW6_ZH, V),
        page("cmp-rec", "comparison", None, v1.CMP_TABLE_ZH, V),
        page("tl-case4", "timeline", None, v1.TL4_ZH, V),
        page("tl-case6", "timeline", None, v1.TL6_ZH, V),
        page("sec-02", "section", None, v1.SECTION_ZH, V, kind="section"),
        page("ph-moa", "moa_cascade", None, px.MOA, P),
        page("ph-trial", "trial_design", None, px.TRIAL, P),
        page("ph-table", "data_table_highlight", None, px.TABLE, P),
        page("ph-endpoint", "endpoint_readout", "bar", px.ENDPOINT_BAR, P),
        page("ph-endpoint-line", "endpoint_readout", "line", px.ENDPOINT_LINE, P),
        page("ph-forest", "forest_plot", None, px.FOREST, P),
        page("ph-swim", "landscape_swimlane", None, px.SWIM, P),
        page("ph-evidence", "key_points", "evidence_takeaways", px.EVIDENCE, P),
    ]
    # Rendering adapters for layouts a page may switch to (same content, no new facts).
    for p in deck:
        d = p["data"]
        if d.get("steps") and p["origin_layout"] == "timeline":
            f = p["fills"]["timeline"]
            p["fills"]["flow"] = {"section": f.get("section"), "title": f["title"], "takeaway": f.get("takeaway"),
                                  "nodes": [{"tag": n["label"], "heading": n["heading"], "body": n.get("body")}
                                            for n in f["nodes"]]}
    stress = stress_pages()
    return deck, stress


def stress_pages():
    """Constructed pages (cut from the same sample) that must downgrade.  No new numbers."""
    F, E, T = px.FOREST, px.ENDPOINT_BAR, px.TRIAL
    two = [r for r in F["rows"] if r["label"] in ("≥ 300", "< 150")]
    s1_items = [{"heading": F["takeaways"][0]["value"], "body": F["takeaways"][0]["text"]},
                {"heading": F["takeaways"][1]["value"], "body": F["takeaways"][1]["text"]}]
    s1 = {"id": "x-forest-2rows", "kind": "content", "title": "血 eos 分层：仅两档率比（RR）",
          "text": [F["subtitle"], F["takeaways"][0]["text"], F["takeaways"][1]["text"]],
          "data": {"effects": [{"label": r["label"], "est": r["est"], "lo": r["lo"], "hi": r["hi"]} for r in two],
                   "items": s1_items},
          "origin_layout": None, "constructed": True,
          "provenance": "构造：从 pharma_fixtures.FOREST 截取 2 行与 2 条要点（示例数据），演示森林图降级",
          "fills": {"key_points": {"section": F["section"], "title": "血 eos 分层：仅两档率比（RR）",
                                   "items": s1_items, "source": DEMO}}}
    s2_items = [{"heading": E["takeaways"][0]["value"], "body": E["title"]},
                {"heading": E["takeaways"][3]["value"], "body": E["takeaways"][3]["text"]}]
    s2 = {"id": "x-readout-1arm", "kind": "content", "title": E["title"],
          "text": [E["subtitle"], E["stats"]["lines"][1], E["takeaways"][3]["text"]],
          "data": {"series": [{"name": E["series"][1]["name"], "values": E["series"][1]["values"][:1]}],
                   "categories": E["categories"][:1], "stats": E["stats"]["lines"], "items": s2_items},
          "origin_layout": None, "constructed": True,
          "provenance": "构造：从 pharma_fixtures.ENDPOINT_BAR 只保留研究药一组数值（无对照组数值），演示终点读出降级",
          "fills": {"key_points": {"section": E["section"], "title": E["title"], "items": s2_items, "source": DEMO}}}
    tl_nodes = [{"label": t["label"], "heading": t["tag"], "body": ph["label"]}
                for t, ph in zip(T["timepoints"], T["phases"] + [{"label": ""}])]
    s3 = {"id": "x-trial-noarms", "kind": "content", "title": T["title"].split("，")[0],
          "text": [T["design_label"], T["population"]] + [e["text"] for e in T["endpoints"][:2]],
          "data": {"timepoints": [t["week"] for t in T["timepoints"]],
                   "steps": [{"when": n["label"], "heading": n["heading"], "body": n["body"]} for n in tl_nodes]},
          "origin_layout": None, "constructed": True,
          "provenance": "构造：从 pharma_fixtures.TRIAL 去掉治疗臂与 n（示例数据），演示试验设计降级",
          "fills": {"timeline": {"section": T["section"], "title": T["title"].split("，")[0], "nodes": tl_nodes,
                                 "source": DEMO}}}
    return [s1, s2, s3]


# Project terms for this sample (subject-specific, so they live with the project, not in selector code).
PROJECT_SIGNALS = {"matrix": [{"name": "症状×加重史", "patterns": ["(mMRC|CAT).{0,40}(加重|exacerbation)"], "weight": 1.0}]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "factdeck/examples/copd_layout_sample/plan.json"))
    args = ap.parse_args()
    deck, stress = build()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"title": "COPD 教学样例（模板库样例内容拆页）", "note": DEMO,
                               "layout_signals": PROJECT_SIGNALS, "pages": deck, "stress_pages": stress}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(out, len(deck), "pages +", len(stress), "stress pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
