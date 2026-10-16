"""Chaptered summaries and the task archive.

Fixture summaries and reviews are hand-written test records, not model output or real reviews. Content is invented.
"""
import copy

import pytest

import test_deckflow as T
from test_deckflow import store
from app.deckflow import WorkflowError, chapter_view, summary_review_current

PLAN = [{"id": "ch1", "title": "认识示例病X", "source_ids": ["S01", "S02"], "outline_ids": ["outline_1"]},
        {"id": "ch2", "title": "评估、治疗与研究", "source_ids": ["S03", "S04"], "outline_ids": ["outline_2", "outline_3"]}]


def project(store):
    w = store.create("虚构分章测试", T.OUTLINE, {"audience": "本科生"})
    for name, make in T.fx_.SOURCES.items():
        store.add_source(w["id"], name, make())
    T.read_all(store, w["id"])
    return store.set_chapters(w["id"], PLAN, "TEST-OPERATOR", "测试：按章撰写")


def chapter_summary(w, cid, note=""):
    """A synthetic chapter summary inside the chapter's view (test record)."""
    c = next(c for c in PLAN if c["id"] == cid)
    v = chapter_view(w, c)
    ids = [p["id"] for s in v["sources"] for p in s["pages"]]
    cuts = [ids] if len(c["outline_ids"]) == 1 else [ids[:len(ids) // 2], ids[len(ids) // 2:]]
    sections = [T.with_message(v, {"id": f"{cid}-s{i}", "title": f"第{i}节", "summary": "本节虚构资料的要点与限制（程序验收用）。",
                                   "source_page_ids": pages, "key_points": T.key_points(v, pages)})
                for i, pages in enumerate(cuts, 1)]
    r = {"schema_version": "full_source_summary.v3", "input_sha256": T.input_hash(v),
         "overall_summary": f"程序验收用的虚构分章总结：{c['title']}的定义、评估与限制，以及不可直接比较的研究结果。{note}",
         "sections": sections, "outline_coverage": [{"outline_id": o, "section_ids": [f"{cid}-s{min(i, len(sections))}"]}
                                                    for i, o in enumerate(c["outline_ids"], 1)], "pending_issues": []}
    return T.with_understanding(v, r)


def write(store, wid, worker="author-A", note="", expect=None):
    store.queue(wid, "SUMMARY")
    t = store.claim(wid, worker, "SUMMARY")
    assert t and (expect is None or t["binding"] == expect)
    return t, store.complete(wid, t["id"], t["lease_token"], chapter_summary(store.get(wid), t["binding"], note))


def review(store, wid, worker="reviewer-R", edit=None):
    store.queue(wid, "SUMMARY_REVIEW")
    t = store.claim(wid, worker, "SUMMARY_REVIEW")
    assert t
    r = T.clear_summary_review(t["brief"]["result_contract"])
    if edit:
        edit(t, r)
    return t, store.complete(wid, t["id"], t["lease_token"], r)


def test_chapters_are_written_reviewed_and_merged_one_at_a_time(store):
    w = project(store)
    assert w["stage"] == "SUMMARY_REQUIRED" and [r["state"] for r in w["chapter_status"]] == ["WRITE", "WRITE"]

    t, w = write(store, w["id"], expect="ch1")
    # the task carried only its chapter: its sources, its outline item, chapter-prefixed ids
    assert [s["id"] for s in t["brief"]["sources"]] == ["S01", "S02"] and [o["id"] for o in t["brief"]["outline"]] == ["outline_1"]
    assert t["brief"]["result_contract"]["sections"][0]["id"] == "ch1-s1" and t["brief"]["chapter"]["of"] == 2
    assert w["summary"] is None and [r["state"] for r in w["chapter_status"]] == ["REVIEW", "WRITE"]

    t, w = write(store, w["id"], expect="ch2")
    assert [s["id"] for s in t["brief"]["sources"]] == ["S03", "S04"]
    assert w["summary"] and [s["id"] for s in w["summary"]["sections"]] == ["ch1-s1", "ch2-s1", "ch2-s2"]
    assert w["summary"]["overall_summary"].startswith("【认识示例病X】")
    assert w["stage"] == "SUMMARY_REVIEW_REQUIRED"

    # the author of a chapter cannot review it
    store.queue(w["id"], "SUMMARY_REVIEW")
    assert store.claim(w["id"], "author-A", "SUMMARY_REVIEW") is None

    def flag(t, r):
        r["sections"][0]["key_points"][0].update(verdict="NOT_ENTAILED", issue="虚构测试：原文没有此断言")
    t, w = review(store, w["id"], edit=flag)
    assert t["binding"] == "ch1"
    issue = next(i for i in w["issue_ledger"]["summary"]["issues"] if i["status"] == "OPEN")
    assert issue["check"] == "SUMMARY:ch1"
    t, w = review(store, w["id"])
    assert t["binding"] == "ch2" and t["brief"]["prior_issues"] == []          # ch1's issue is not ch2's business
    assert w["stage"] == "SUMMARY_ISSUES" and summary_review_current(w)

    # the revision goes back to ch1 only, with its review issue and its current part as the base
    t, w = write(store, w["id"], note="修订", expect="ch1")
    assert [i["id"] for i in t["brief"]["review_issues"]] == [issue["id"]] and t["brief"]["revision_base"]["sections"][0]["id"] == "ch1-s1"
    assert w["stage"] == "SUMMARY_REVIEW_REQUIRED" and [r["state"] for r in w["chapter_status"]] == ["REVIEW", "DONE"]

    def fixed(t, r):
        r["prior_issues"] = [{"issue_id": issue["id"], "status": "FIXED", "evidence": "已改写（测试记录）", "evidence_refs": ["ch1-s1"]}]
    t, w = review(store, w["id"], edit=fixed)
    assert t["binding"] == "ch1" and w["stage"] == "CONTENT_CONFIRMATION"
    w = T.approve(store, w, "content")
    assert w["stage"] == "FACTS_REQUIRED"


def test_finished_tasks_are_archived_and_restorable(store):
    w = project(store)
    t, w = write(store, w["id"])
    done = next(x for x in w["tasks"] if x["id"] == t["id"])
    assert done["status"] == "COMPLETE" and done["archive"]["bytes"] > 4096
    assert set(done["brief"]) <= {"kind", "regression", "summary_algorithm", "chapter"}
    full = store.archived_task(w, done)
    assert full["brief"]["result_contract"] == t["brief"]["result_contract"]


def test_chapter_plan_is_checked_and_recorded(store):
    w = project(store)
    bad = copy.deepcopy(PLAN)
    bad[1]["source_ids"] = ["S03"]                                     # S04 in no chapter
    with pytest.raises(WorkflowError):
        store.set_chapters(w["id"], bad, "TEST-OPERATOR", "测试：漏掉资料")
    with pytest.raises(WorkflowError):                                # 4 sources, 3 outline items
        store.set_chapters(w["id"], "by_source", "TEST-OPERATOR", "测试：自动分章")
    _, w = write(store, w["id"])
    w = store.set_chapters(w["id"], [], "TEST-OPERATOR", "测试：改回整体撰写")
    assert w["chapters"] == [] and w["summary"] is None and w["chapters_history"][-1]["set_aside_chapters"]["ch1"]["path"]


def read_with_reference_page(store, wid):
    """Read the fixtures and mark the last page with text as a reference list (test record)."""
    store.queue(wid, "READ_SOURCE")
    marked = None
    while t := store.claim(wid, "reader-1", "READ_SOURCE"):
        result = copy.deepcopy(t["brief"]["result_contract"])
        for row, page in zip(result["pages"], t["brief"]["pages"]):
            row["visual_inspected"] = True
            if row["id"] == "S03:s1":
                row["transcription"] = [{"id": "c1", "location": "柱状图 研究甲标签", "text": "缓解率38%"}]
        if t["binding"] == "S04":
            row["classification"], marked = "REFERENCE", row["id"]
        store.complete(wid, t["id"], t["lease_token"], result)
    return T.claim_all(store, wid), marked


def test_reference_pages_are_registered_by_code_and_reviewed_per_page(store):
    from app.deckflow import reference_units, all_units
    w = store.create("虚构参考页测试", T.OUTLINE, {"audience": "本科生"})
    for name, make in T.fx_.SOURCES.items():
        store.add_source(w["id"], name, make())
    w, ref_page = read_with_reference_page(store, w["id"])
    refs = reference_units(w)
    assert refs and all(u["page_id"] == ref_page for u in all_units(w) if u["id"] in refs)

    store.queue(w["id"], "SUMMARY")
    t = store.claim(w["id"], "author-A", "SUMMARY")
    assert not any(set(c["unit_ids"]) & refs for c in t["brief"]["chunks"])      # authors do not register them
    r = T._summary(w)
    for sec in r["sections"]:
        sec["key_points"] = [k for k in sec["key_points"] if not set(k["unit_ids"]) & refs]
        T.with_message(w, sec)
    T.with_understanding(w, r)
    r["source_coverage"]["units"] = [x for x in r["source_coverage"]["units"] if x["unit_id"] not in refs]
    r["evidence_index"]["page_decisions"] = [d for d in r["evidence_index"]["page_decisions"] if d["page_id"] != ref_page]
    w = store.complete(w["id"], t["id"], t["lease_token"], r)
    rows = [x for x in w["summary"]["source_coverage"]["units"] if x["unit_id"] in refs]
    assert rows and all(x["registered_by"] == "code:reference_page" for x in rows)

    store.queue(w["id"], "SUMMARY_REVIEW")
    t = store.claim(w["id"], "reviewer-R", "SUMMARY_REVIEW")
    page = [x for x in t["brief"]["coverage_targets"] if x.get("registered_by")]
    assert [x["target_id"] for x in page] == [f"{ref_page}/reference_page"]
    result = T.clear_summary_review(t["brief"]["result_contract"])
    next(x for x in result["coverage_review"] if x["target_id"] == page[0]["target_id"]).update(
        verdict="REJECTED", issue="虚构测试：本页夹有正文")
    w = store.complete(w["id"], t["id"], t["lease_token"], result)
    assert any(i["ref"] == f"{ref_page}/reference_page" and i["status"] == "OPEN" for i in w["issue_ledger"]["summary"]["issues"])


def test_unchanged_targets_keep_an_earlier_pass(store):
    w = project(store)
    write(store, w["id"]); write(store, w["id"])
    t, w = review(store, w["id"])
    assert t["brief"]["carried_coverage"]["count"] == 0
    # rewrite ch1 with an unchanged body: every coverage target keeps its earlier pass
    store.queue(w["id"], "SUMMARY", ["ch1"])
    t = store.claim(w["id"], "author-A", "SUMMARY")
    w = store.complete(w["id"], t["id"], t["lease_token"], chapter_summary(store.get(w["id"]), "ch1", "修订"))
    t, w = review(store, w["id"])
    c = t["brief"]["carried_coverage"]
    assert t["binding"] == "ch1" and c["count"] == c["of"] > 0 and t["brief"]["coverage_targets"] == []


def test_sections_saved_as_separate_fragments_merge_into_one_draft(store):
    from factdeck import summary_fragments as sf
    from app.deckflow import all_units
    w = project(store)
    store.queue(w["id"], "SUMMARY", ["ch2"])
    t = store.claim(w["id"], "author-A", "SUMMARY")
    full = chapter_summary(store.get(w["id"]), "ch2")
    pages = {u["id"]: u["page_id"] for u in all_units(store.get(w["id"]))}
    parts = sf.split(full, pages)
    assert len(parts) == 2
    for part in reversed(parts):                                       # any order, as parallel sessions finish
        frag = {**{k: full[k] for k in ("schema_version", "input_sha256", "summary_algorithm")}, **part, "fragment_chunks": [0]}
        store.save_summary_draft(w["id"], t["id"], t["lease_token"], frag)
    clash = {**parts[0], "sections": [{**parts[0]["sections"][0], "id": "ch2-other"}], "fragment_chunks": [0]}
    with pytest.raises(WorkflowError):                                  # a page belongs to one section only
        store.save_summary_draft(w["id"], t["id"], t["lease_token"], clash)
    draft = next(x for x in store.get(w["id"])["tasks"] if x["id"] == t["id"])["draft"]["summary"]
    assert [s["id"] for s in draft["sections"]] == [s["id"] for s in full["sections"]]
    strip = lambda rows: [{**r, "parts": [{k: v for k, v in x.items() if k not in ("start", "end")} for x in r["parts"]]} for r in rows]
    assert strip(draft["source_coverage"]["units"]) == strip(full["source_coverage"]["units"])   # the progress check adds offsets
    w = store.complete(w["id"], t["id"], t["lease_token"], {**draft, "overall_summary": full["overall_summary"],
                                                             "outline_coverage": full["outline_coverage"]})
    assert [r["state"] for r in w["chapter_status"]] == ["WRITE", "REVIEW"]


def test_garbled_text_is_refused_when_a_draft_is_saved(store):
    w = project(store)
    store.queue(w["id"], "SUMMARY", ["ch1"])
    t = store.claim(w["id"], "author-A", "SUMMARY")
    r = chapter_summary(store.get(w["id"]), "ch1")
    r["sections"][0]["key_points"][0]["point"] = "????????????"                       # what a broken pipe leaves
    with pytest.raises(WorkflowError, match="OutputEncoding"):
        store.save_summary_draft(w["id"], t["id"], t["lease_token"], {**r, "fragment_chunks": [0]})
