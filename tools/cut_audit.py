"""Audit sentence cutting on real material — before and after a change to the cutter, no model calls, no writes.

    python tools/cut_audit.py DATA_ROOT [--workflow ID] [--save baseline.json] [--against baseline.json]

Code cuts every unit into verbatim sentences (`factdeck.auto_claims`); a mis-cut shows by punctuation (a bracket
closed with no opening, one left open, a sentence starting on a comma, an over-long merge — `auto_claims.ANOMALIES`).
This tool cuts every project in DATA_ROOT and reports those anomalies. To check a cutter change:

    git stash; python tools/cut_audit.py data/deckflow --save before.json; git stash pop
    python tools/cut_audit.py data/deckflow --against before.json

`--against` lists, per project, the sentences whose text changed under the same id, the sentences added and
removed, and the anomalies fixed and introduced. Exit 1 when the change introduces anomalies. What the change does
to accepted work is `tools/replay.py`'s question.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.deckflow import all_units  # noqa: E402
from factdeck import auto_claims  # noqa: E402

EXAMPLES = 5


def projects(data_root: Path, only: str | None):
    db = sqlite3.connect(f"file:{(data_root / 'workflow.sqlite3').as_posix()}?mode=ro", uri=True)
    for wid, state in db.execute("SELECT id, state FROM workflows"):
        if only and wid != only:
            continue
        w = json.loads(state)
        if any(s.get("pages") for s in w.get("sources") or []):
            yield w


def cut(w: dict) -> dict[str, dict]:
    page_class = {p["id"]: (p.get("reading") or {}).get("classification", "") for s in w["sources"] for p in s["pages"]}
    return {c["id"]: {"quote": c["quote"], "kind": c["kind"], "anomalies": c.get("anomalies", [])}
            for c in auto_claims.cut(all_units(w), page_class, {})}


def short(q: str, n: int = 70) -> str:
    q = " ".join(q.split())
    return q if len(q) <= n else q[:n] + "…"


def where(a: str, b: str) -> tuple[str, str]:
    """The two texts from just before where they first differ."""
    a, b = " ".join(a.split()), " ".join(b.split())
    i = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    s = max(i - 12, 0)
    return ("…" if s else "") + a[s:s + 50], ("…" if s else "") + b[s:s + 50]


def audit(data_root: Path, only: str | None = None) -> dict:
    return {"cutter": auto_claims.SCHEMA, "projects": {w["id"]: {"title": w.get("title", ""), "sentences": cut(w)}
                                                       for w in projects(data_root, only)}}


def compare(before: dict, now: dict) -> dict:
    out = {}
    for wid, p in now["projects"].items():
        a, b = (before["projects"].get(wid) or {}).get("sentences"), p["sentences"]
        if a is None:
            continue
        changed = [x for x in b if x in a and a[x]["quote"] != b[x]["quote"]]
        # both sides judged by the current detector, so a baseline cut by older code compares fairly
        bad = lambda s: {(x, k) for x, c in s.items() for k in auto_claims.anomalies(c["quote"], c["kind"])}
        fixed, new = bad(a) - bad(b), bad(b) - bad(a)
        out[wid] = {"title": p["title"], "changed": changed, "added": [x for x in b if x not in a],
                    "removed": [x for x in a if x not in b], "fixed": sorted(fixed), "introduced": sorted(new),
                    "examples": [{"id": x, "before": a[x]["quote"], "now": b[x]["quote"]} for x in changed[:EXAMPLES]]}
    return out


def markdown(now: dict, diff: dict | None) -> str:
    out = [f"# Cut audit ({now['cutter']})\n"]
    for wid, p in now["projects"].items():
        s = p["sentences"]
        counted = [c for c in s.values() if c["kind"] in ("sentence", "cell")]
        codes = Counter(k for c in counted for k in c["anomalies"])
        out.append(f"## {p['title']} `{wid}`\n\n{len(counted)} sentences/cells; anomalies: "
                   + (", ".join(f"{k} {v}" for k, v in codes.most_common()) or "none"))
        for k in codes:
            for x, c in [(x, c) for x, c in s.items() if k in c["anomalies"]][:EXAMPLES]:
                out.append(f"- {k} `{x}` {short(c['quote'])}")
        d = (diff or {}).get(wid)
        if d:
            out.append(f"\nAgainst the baseline: {len(d['changed'])} changed under the same id, {len(d['added'])} added, "
                       f"{len(d['removed'])} removed; anomalies fixed {len(d['fixed'])}, introduced {len(d['introduced'])}.")
            for e in d["examples"]:
                a, b = where(e["before"], e["now"])
                out.append(f"- `{e['id']}` before「{a}」now「{b}」")
            for x, k in d["introduced"][:EXAMPLES]:
                out.append(f"- introduced {k} `{x}` {short(s[x]['quote'])}")
        out.append("")
    if diff is not None:
        out.append("RESULT: " + ("FAIL — the change introduces anomalies" if any(d["introduced"] for d in diff.values()) else "PASS"))
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("data_root", type=Path)
    ap.add_argument("--workflow")
    ap.add_argument("--save", type=Path, help="write this cut as a baseline")
    ap.add_argument("--against", type=Path, help="compare with a saved baseline")
    ap.add_argument("--out", type=Path, help="write the markdown report here")
    a = ap.parse_args()
    now = audit(a.data_root.resolve(), a.workflow)
    if a.save:
        a.save.write_text(json.dumps(now, ensure_ascii=False), encoding="utf-8")
    diff = compare(json.loads(a.against.read_text(encoding="utf-8")), now) if a.against else None
    md = markdown(now, diff)
    if a.out:
        a.out.write_text(md, encoding="utf-8")
    sys.stdout.write(md)
    sys.exit(1 if diff and any(d["introduced"] for d in diff.values()) else 0)


if __name__ == "__main__":
    main()
