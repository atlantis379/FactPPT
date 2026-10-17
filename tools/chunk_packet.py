"""One chunk of a claimed SUMMARY / SUMMARY_REVIEW task, extracted from its brief, so a worker session reads only the
pages it is about to work on instead of the whole brief. Read-only: it never changes the task or its result.

usage: python tools/chunk_packet.py --task TASK.json [--chunk N | --next] [--images DIR] [--out FILE]
       python tools/chunk_packet.py --task TASK.json --draft-out FILE   (the current saved draft, to continue from)
       python tools/chunk_packet.py --task TASK.json (--chunk N | --section ID) --fragment-out FILE   (SUMMARY: the fragment to write)
       python tools/chunk_packet.py --task TASK.json --section ID [--images DIR] [--out F]          (SUMMARY revision: the section's pages)
  --next      the first chunk not yet done: the task's live draft in the project store (or --done N N ...)
  --images    folder with <source id>/pNN.png page images; paths of the chunk's pages are listed when present
"""
import argparse
import os
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def live_units(task_id):
    """Every unit's text in the project that holds this task (for briefs issued before they carried every unit)."""
    store, wid = _store_of(task_id)
    if not wid:
        return {}
    from app.deckflow import all_units
    return {u["id"]: u["text"] for u in all_units(store.get(wid))}


def _store_of(task_id):
    import os
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.deckflow import Store
    root = os.environ.get("FACTDECK_DATA_ROOT")
    store = Store(Path(root) if root else None)
    with store.connect() as db:
        row = db.execute("SELECT id FROM workflows WHERE instr(state, ?) > 0", (task_id,)).fetchone()
    return store, row and row[0]


def live_draft(task_id):
    """The task's current draft in the project store (the task file is a claim-time copy)."""
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
                return t.get("draft") or {}
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


def summary_packet(brief, chunk, images, task_id=None):
    pages = set(chunk["page_ids"])
    units = set(chunk["unit_ids"])
    texts = unit_texts(brief)
    if task_id and units - set(texts):
        texts = {**live_units(task_id), **texts}
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
    inside = [sec for sec in brief.get("sections") or [] if set(sec.get("source_page_ids") or []) and
              set(sec["source_page_ids"]) <= set(chunk["page_ids"])]
    return {"kind": "SUMMARY_REVIEW", "chunk": chunk["index"], "of": len(brief["chunks"]),
            "images": {p: image(images, p) for p in chunk["page_ids"] if image(images, p)},
            "targets": targets, "points": {p: points.get(p, "") for p in named},
            "sections": inside,
            "note": "sections 是页码全在本块内的章节：本块会话一并给出它们的章节行（summary_verdict、points、key_points、core、relations）；"
                    "跨块的章节由收尾会话判定。"}


def fragment(task, chunk=None, section=None):
    """The fragment a session writes: the current section(s) on the chunk's pages, or a skeleton for a new section."""
    from factdeck import summary_fragments as sf
    brief = task["brief"]
    cid = (brief.get("chapter") or {}).get("id")
    current = (live_draft(task["id"]) or {}).get("summary") or brief.get("revision_base") or {}
    store, wid = _store_of(task["id"])
    from app.deckflow import all_units, chapter_of, chapter_view
    w = store.get(wid)
    units = all_units(chapter_view(w, chapter_of(w, cid)) if cid else w)
    unit_pages = {u["id"]: u["page_id"] for u in units}
    parts = sf.split(current, unit_pages) if current.get("sections") else []
    plan = brief.get("chunks") or []
    if section:
        mine = [f for f in parts if f["sections"][0]["id"] == section]
        if not mine:
            sys.exit(f"当前草稿中没有章节 {section}")
    else:
        mine = [f for f in parts if set(f["sections"][0].get("source_page_ids") or []) & set(chunk["page_ids"])]
    head = {"schema_version": brief["result_contract"]["schema_version"], "input_sha256": brief["input_sha256"],
            "summary_algorithm": brief.get("summary_algorithm")}
    if mine:
        out = sf.concat(mine, head)
        pages = set().union(*(set(f["sections"][0]["source_page_ids"]) for f in mine))
        out["fragment_chunks"] = [c["index"] for c in plan if set(c["page_ids"]) & pages]
        out["existing"] = True
    else:
        rc = brief["result_contract"]
        sid = f"{cid}-c{chunk['index']}" if cid else f"c{chunk['index']}"
        cov = brief["source_coverage_input"]
        out = {**head, "existing": False,
               "sections": [{"id": sid, "title": "", "summary": "", "source_page_ids": list(chunk["page_ids"]), "key_points": [],
                             "message": {"core": {"claim_id": ""}, "roles": {}, "relations": [], "candidate_decisions": []}}],
               "source_understanding": {"schema_version": rc["source_understanding"]["schema_version"], "sections": [
                   {**rc["source_understanding"]["sections"][0], "section_id": sid, "conclusions": [], "relations": []}]},
               "evidence_index": {"schema_version": rc["evidence_index"]["schema_version"], "points": [], "page_decisions": []},
               "source_coverage": {"schema_version": cov["schema_version"], "segmenter": cov["segmenter"],
                                   "source_units_sha256": cov["source_units_sha256"], "units": []},
               "pending_issues": [], "fragment_chunks": [chunk["index"]]}
    if section or (mine and brief.get("review_issues")):
        secs = {s["id"] for s in out["sections"]}
        pages = set().union(*(set(s["source_page_ids"]) for s in out["sections"]))
        def mine_ref(ref):
            head_ = str(ref).split("/")[0]
            return (str(ref).split(".")[0] in secs or head_ in pages or unit_pages.get(head_) in pages)
        out["review_issues"] = [i for i in brief.get("review_issues") or [] if mine_ref(i.get("ref"))]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--task", type=Path, required=True)
    ap.add_argument("--chunk", type=int)
    ap.add_argument("--next", action="store_true")
    ap.add_argument("--done", type=int, nargs="*", help="chunks already done (default: draft.done_chunks in the task file)")
    ap.add_argument("--images", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--draft-out", type=Path, help="write the task's current saved draft (summary or review result) here and exit")
    ap.add_argument("--fragment-out", type=Path, help="SUMMARY: write the fragment to edit for --chunk N or --section ID "
                                                       "(current section(s) on those pages, or a skeleton for a new section)")
    ap.add_argument("--section", help="with --fragment-out: a section of the current draft (revision of that section)")
    a = ap.parse_args()
    task = json.loads(a.task.read_text(encoding="utf-8-sig"))
    if a.draft_out:
        d = live_draft(task["id"]) or {}
        body = d.get("summary") if task["kind"] == "SUMMARY" else d.get("result")
        if body is None:
            print(json.dumps({"draft": None, "note": "项目中还没有保存的草稿"}, ensure_ascii=False)); return
        a.draft_out.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"draft_out": str(a.draft_out), "done_chunks": d.get("done_chunks")}, ensure_ascii=False)); return
    brief = task["brief"]
    plan = brief.get("chunks") or []
    if a.fragment_out:
        chunk = None if a.section else next((c for c in plan if c["index"] == a.chunk), None)
        if not a.section and chunk is None:
            sys.exit("--fragment-out 需要 --chunk N（存在的块）或 --section ID")
        frag = fragment(task, chunk, a.section)
        a.fragment_out.write_text(json.dumps(frag, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"fragment_out": str(a.fragment_out), "sections": [x["id"] for x in frag["sections"]],
                          "existing": frag["existing"], "fragment_chunks": frag["fragment_chunks"],
                          "review_issues": len(frag.get("review_issues") or [])}, ensure_ascii=False)); return
    if a.next:
        live = (live_draft(task["id"]) or {}).get("done_chunks") if a.done is None else None
        done = set(a.done if a.done is not None else live if live is not None else (task.get("draft") or {}).get("done_chunks") or [])
        left = [c for c in plan if c["index"] not in done]
        if not left:
            print(json.dumps({"next": None, "note": "全部分块已完成"}, ensure_ascii=False)); return
        chunk = left[0]
    elif a.section and a.chunk is None:
        # a revision of one section: its pages, gathered from the chunks they fall in
        d = live_draft(task["id"]) or {}
        current = d.get("summary") or brief.get("revision_base") or {}
        sec = next((s for s in current.get("sections") or [] if s["id"] == a.section), None)
        if sec is None:
            sys.exit(f"当前草稿中没有章节 {a.section}")
        pages = set(sec.get("source_page_ids") or [])
        mine = [c for c in plan if set(c["page_ids"]) & pages]
        page_of = {r["unit_id"]: r["page_id"] for r in brief["source_coverage_input"]["units"]}
        chunk = {"index": [c["index"] for c in mine], "page_ids": [p for c in mine for p in c["page_ids"] if p in pages],
                 "unit_ids": [u for c in mine for u in c["unit_ids"] if page_of.get(u) in pages]}
    else:
        chunk = next((c for c in plan if c["index"] == a.chunk), None)
        if chunk is None:
            sys.exit(f"没有第 {a.chunk} 块（共 {len(plan)} 块）")
    packet = summary_packet(brief, chunk, a.images, task["id"]) if task["kind"] == "SUMMARY" else review_packet(brief, chunk, a.images)
    text = json.dumps(packet, ensure_ascii=False, indent=1)
    if a.out:
        a.out.write_text(text, encoding="utf-8"); print(json.dumps({"out": str(a.out), "chunk": chunk["index"]}, ensure_ascii=False))
    else:
        sys.stdout.reconfigure(encoding="utf-8"); print(text)


if __name__ == "__main__":
    main()
