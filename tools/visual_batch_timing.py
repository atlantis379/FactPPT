"""Measured A-route throughput for a batch: per page and per stage, from the workflow record.

Read-only. Durations come from task timestamps (created / claimed / completed) and the
elapsed seconds in accepted tool receipts; nothing is estimated. Pages are those with any
visual task created at or after --since (UTC ISO time).

    python tools/visual_batch_timing.py deck_xxx --since 2026-10-14T01:00:00 [--out timing.json]
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.deck_generation import VISUAL_KINDS


def t(value):
    return datetime.fromisoformat(value) if value else None


def seconds(a, b):
    return round((b - a).total_seconds(), 1) if a and b else None


def measure(w, since):
    g = w["generation"]
    tasks = [x for x in w["tasks"] if x["kind"] in VISUAL_KINDS and x.get("generation_id") == g["id"] and t(x.get("created_at")) and t(x["created_at"]) >= since]
    receipts = {}
    for p in g["pages"]:
        for group in [p["assets"], *[h["assets"] for h in p.get("history", [])]]:
            for a in group.values():
                receipts[a["receipt"].get("task_id")] = a["receipt"]
    pages = []
    for p in g["pages"]:
        own = sorted((x for x in tasks if x["binding"] == p["id"]), key=lambda x: x["created_at"])
        if not own: continue
        done = [x for x in own if x["status"] == "COMPLETE"]
        stages = []
        for x in own:
            r = receipts.get(x["id"]) or {}
            stages.append({"kind": x["kind"], "status": x["status"], "attempts": x["attempts"], "worker": x.get("worker"),
                           "queue_wait_s": seconds(t(x["created_at"]), t(x.get("claimed_at"))),
                           "claimed_to_done_s": seconds(t(x.get("claimed_at")), t(x.get("completed_at"))),
                           "tool": r.get("tool"), "tool_s": r.get("elapsed_seconds")})
        complete = p.get("layout") and {"design", "clean", "vector"} <= set(p["assets"])
        wall = seconds(t(own[0]["created_at"]), t(max(x["completed_at"] for x in done))) if complete and done else None
        tool = round(sum(s["tool_s"] or 0 for s in stages if s["status"] == "COMPLETE"), 1)
        pages.append({"page": p["id"], "complete": bool(complete), "wall_s": wall, "tool_s": tool,
                      "overhead_s": round(wall - tool, 1) if wall is not None else None,
                      "retries": sum(max(0, s["attempts"] - 1) for s in stages), "stages": stages})
    finished = [p for p in pages if p["complete"]]
    span = None
    if finished:
        span = seconds(min(t(x["created_at"]) for x in tasks), max(t(x["completed_at"]) for x in tasks if x["status"] == "COMPLETE"))
    return {"workflow_id": w["id"], "generation_id": g["id"], "since": since.isoformat(), "pages_started": len(pages), "pages_complete": len(finished),
            "batch_wall_s": span, "per_page_wall_avg_s": round(span / len(finished), 1) if span and finished else None,
            "per_page_tool_avg_s": round(sum(p["tool_s"] for p in finished) / len(finished), 1) if finished else None,
            "workers": sorted({s["worker"] for p in pages for s in p["stages"] if s["worker"]}), "pages": pages,
            "note": "Measured from task timestamps and accepted receipts. Pages run concurrently, so batch_wall_s / pages is the throughput figure; per-page wall_s overlaps."}


def main():
    from app.deckflow import Store
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("workflow_id"); parser.add_argument("--since", required=True); parser.add_argument("--out", type=Path)
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    since = datetime.fromisoformat(args.since)
    if since.tzinfo is None: since = since.replace(tzinfo=timezone.utc)   # naive input is UTC, like task timestamps
    report = measure(Store(args.data_root).get(args.workflow_id), since)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out: args.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
