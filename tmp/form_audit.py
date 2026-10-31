"""Audit: for each real deck, what could each page legitimately be drawn as — and how often is that text?

Answers 'how many pages should actually have a chart' on material that exists, instead of guessing.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factdeck.presentation import FORMS, form_supported, materials

DECKS = {
    "GOLD 2026（20 页）": (ROOT / "output/gold2026_deck/deck.json",
                           ROOT / "output/gold2026_deck/facts_verified.json", "facts"),
    "biologics（15 页）": (ROOT / "output/biologics_template_run/work/deck_from_map.json",
                           ROOT / "output/biologics_template_run/work/deck_from_map.json", "facts"),
}

for label, (deck_path, facts_path, key) in DECKS.items():
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    facts = {f["id"]: f for f in json.loads(facts_path.read_text(encoding="utf-8"))[key]}
    rows, tally = [], {}
    def fact_ids(node):
        out = []
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "fact" and isinstance(v, str):
                    out.append(v)
                else:
                    out += fact_ids(v)
        elif isinstance(node, list):
            for v in node:
                out += fact_ids(v)
        return out

    for p in deck.get("pages") or []:
        ids = [x for x in dict.fromkeys(fact_ids(p)) if x in facts]
        if not ids:
            continue
        mat = materials(ids, facts)
        fits = [f for f in ("bars", "trend", "threshold", "decision")
                if form_supported(f, mat, None, None)[0]]
        best = fits[0] if fits else "text"
        tally[best] = tally.get(best, 0) + 1
        rows.append((p.get("id", "?"), len(ids), len(mat["comparable"]),
                     len({x["token"] for x in mat["timeline"]}), len(mat["thresholds"]),
                     len(mat["conditions"]), ",".join(fits) or "—"))
    print(f"\n=== {label}：{len(rows)} 页有内容 ===")
    print(f"{'页':22s} {'句':>3s} {'可比组':>5s} {'时间量':>5s} {'阈值':>4s} {'条件':>4s}  可画")
    for r in rows:
        print(f"{r[0][:22]:22s} {r[1]:3d} {r[2]:5d} {r[3]:5d} {r[4]:4d} {r[5]:4d}  {r[6]}")
    print("小结：", tally, f"／ 纯文字 {tally.get('text', 0)} 页")
