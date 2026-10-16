"""One chunk of a claimed SUMMARY / SUMMARY_REVIEW task, extracted from its brief, so a worker session reads only the
pages it is about to work on instead of the whole brief. Read-only: it never changes the task or its result.

usage: python tools/chunk_packet.py --task TASK.json [--chunk N | --next] [--images DIR] [--out FILE]
  --next      the first chunk not yet done: the task's live draft in the project store (or --done N N ...)
  --images    folder with <source id>/pNN.png page images; paths of the chunk's pages are listed when present
"""
import argparse
import json
import sys
from pathlib import Path


def live_done(task_id):
    """done_chunks of the task's current draft, read from the project store (the task file is a claim-time copy)."""
    import os
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.deckflow import Store
    root = os.environ.get("FACTDECK_DATA_ROOT")
    store = Store(Path(root) if root else None)
    with store.connect() as db:
        ids = [r[0] for r in db.execute("SELECT id FROM workflows WHERE instr(state, ?) > 0", (task_id,)).fetchall()]
    for wid in ids:
        for t in store.get(wid)["tasks"]:
            if t["id"] == task_id:
                return (t.get("draft") or {}).get("done_chunks") or []
    return None


def unit_texts(brief):
    out = {}
    for s in brief.get("sources") or []:
        for p in s["pages"]:
            for u in p.get("units") or []:
                out[u["id"]] = u["text"]
        for u in s.get("transcriptions") or []:
            out[u["id"]] = u["text"]
    return out


def image(images, page_id):
    if not images:
        return None
    sid, _, n = page_id.partition(":p")
    f = Path(images) / sid / f"p{int(n):02d}.png" if n.isdigit() else None
    return str(f) if f and f.exists() else None


def summary_packet(brief, chunk, images):
    pages = set(chunk["page_ids"])
    units = set(chunk["unit_ids"])
    texts = unit_texts(brief)
    cov = {r["unit_id"]: r for r in brief["source_coverage_input"]["units"]}
    out = []
    for s in brief["sources"]:
        for p in s["pages"]:
            if p["id"] not in pages:
                continue
            ids = [u for u in chunk["unit_ids"] if cov[u]["page_id"] == p["id"]]
            out.append({"page_id": p["id"], "location": p["location"], "reading": p.get("reading"),
                        "image": image(images, p["id"]),
                        "units": [{"unit_id": u, "text": texts.get(u, ""),
                                   "segments": [{"index": g["index"], "text": texts.get(u, "")[g["start"]:g["end"]]} for g in cov[u]["segments"]]}
                                  for u in ids],
                        "claims": p.get("claims") or []})
    cands = [c for s in brief["sources"] for c in s.get("relation_candidates") or [] if set(c.get("unit_ids") or []) & units]
    return {"kind": "SUMMARY", "chunk": chunk["index"], "of": len(brief["chunks"]), "pages": out, "relation_candidates": cands,
            "segments": sum(len(u["segments"]) for p in out for u in p["units"])}


def review_packet(brief, chunk, images):
    units = set(chunk["unit_ids"])
    points = {}
    for sec in brief.get("sections") or []:
        for i, k in enumerate(sec.get("key_points") or [], 1):
            points[f"{sec['section_id']}.k{i}"] = k.get("point", "")
    targets = [t for t in brief.get("coverage_targets") or [] if t["unit_id"] in units]
    named = sorted({e["point_id"] for t in targets for e in t.get("expressions") or []})
    return {"kind": "SUMMARY_REVIEW", "chunk": chunk["index"], "of": len(brief["chunks"]),
            "images": {p: image(images, p) for p in chunk["page_ids"] if image(images, p)},
            "targets": targets, "points": {p: points.get(p, "") for p in named}}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--task", type=Path, required=True)
    ap.add_argument("--chunk", type=int)
    ap.add_argument("--next", action="store_true")
    ap.add_argument("--done", type=int, nargs="*", help="chunks already done (default: draft.done_chunks in the task file)")
    ap.add_argument("--images", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    task = json.loads(a.task.read_text(encoding="utf-8-sig"))
    brief = task["brief"]
    plan = brief.get("chunks") or []
    if a.next:
        live = live_done(task["id"]) if a.done is None else None
        done = set(a.done if a.done is not None else live if live is not None else (task.get("draft") or {}).get("done_chunks") or [])
        left = [c for c in plan if c["index"] not in done]
        if not left:
            print(json.dumps({"next": None, "note": "全部分块已完成"}, ensure_ascii=False)); return
        chunk = left[0]
    else:
        chunk = next((c for c in plan if c["index"] == a.chunk), None)
        if chunk is None:
            sys.exit(f"没有第 {a.chunk} 块（共 {len(plan)} 块）")
    packet = (summary_packet if task["kind"] == "SUMMARY" else review_packet)(brief, chunk, a.images)
    text = json.dumps(packet, ensure_ascii=False, indent=1)
    if a.out:
        a.out.write_text(text, encoding="utf-8"); print(json.dumps({"out": str(a.out), "chunk": chunk["index"]}, ensure_ascii=False))
    else:
        sys.stdout.reconfigure(encoding="utf-8"); print(text)


if __name__ == "__main__":
    main()
