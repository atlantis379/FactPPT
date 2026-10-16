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
