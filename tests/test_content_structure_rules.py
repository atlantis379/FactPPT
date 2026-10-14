"""Content-side rules from the 2026-10-13 audit: every chapter carries its information structure (R1), every
candidate relation on a chapter's pages is adopted or declined (R2), reviews start with no pre-filled verdicts (B1),
the semantic review also judges relations that the pages lose or flatten and whether a chapter's core and limits
can be read back from its pages (R4), unfixable issues start with a person and the content rules are frozen per
project (R5). Fixture data are invented; they are not real reviews or approvals."""
import copy

import pytest

import test_deckflow as T
from test_deckflow import store  # noqa: F401  (fixture)
from test_summary_review_coverage import summarised
from app.deckflow import WorkflowError, story_line, CONTENT_RULES_VERSION, relation_candidates_of, all_units


def plain_summary(w):
    """The fixture summary for an outline without points, before any information structure is added."""
    return T._summary(w)


def test_chapters_without_outline_points_still_need_their_message(store):
    w = summarised(store)
    s = w["summary"]["sections"][0]
    assert [k["id"] for k in s["key_points"]] == [f"{s['id']}.k{i}" for i in range(1, len(s["key_points"]) + 1)]
    assert s["message"]["roles"] and story_line(w)                      # B3: the storyline now covers these chapters
    bare = plain_summary(store.get(w["id"]))
    with pytest.raises(WorkflowError, match="信息结构 message"):
        store.author(w["id"], "SUMMARY", bare, "author-A")


def test_every_candidate_relation_on_a_chapter_is_adopted_or_declined(store):
    w = summarised(store)
    unit_page = {u["id"]: u["page_id"] for u in all_units(w)}
    sec = next((s for s in w["summary"]["sections"] if s["message"]["candidate_decisions"]), None)
    if sec is None:
        pytest.skip("fixture sources have no candidate relations")
    good = T.summary(store.get(w["id"]))
    idx = [s["id"] for s in good["sections"]].index(sec["id"])
    def variant(change):
        r = copy.deepcopy(good); change(r["sections"][idx]["message"]); return r
    with pytest.raises(WorkflowError, match="未处理的候选关系"):
        store.author(w["id"], "SUMMARY", variant(lambda m: m["candidate_decisions"].pop()), "author-A")
    with pytest.raises(WorkflowError, match="ADOPTED|REJECTED"):
        store.author(w["id"], "SUMMARY", variant(lambda m: m["candidate_decisions"][0].update(reason="随便")), "author-A")
    with pytest.raises(WorkflowError, match="from_candidate"):
        store.author(w["id"], "SUMMARY", variant(lambda m: m["candidate_decisions"][0].update(decision="ADOPTED")), "author-A")
    cid = sec["message"]["candidate_decisions"][0]["candidate"]
    assert any(unit_page.get(u) in sec["source_page_ids"] for u in relation_candidates_of(w)[cid]["unit_ids"])


def test_review_contracts_have_no_prefilled_verdicts(store):
    w = summarised(store)
    store.queue(w["id"], "SUMMARY_REVIEW")
    t = store.claim(w["id"], "independent-v2", "SUMMARY_REVIEW")
    rows = t["brief"]["result_contract"]["sections"]
    assert all(r["summary_verdict"] == "" and all(k["verdict"] == "" for k in r["key_points"]) for r in rows)
    with pytest.raises(WorkflowError, match="summary_verdict"):
        store.complete(w["id"], t["id"], t["lease_token"], t["brief"]["result_contract"])     # silence is not a pass


def deck_ready(store):
    return T.to_deck(store)


def test_semantic_review_judges_lost_relations_and_chapter_outcomes(store):
    w = deck_ready(store)
    store.queue(w["id"], "SEMANTIC_REVIEW")
    t = store.claim(w["id"], "reviewer-B", "SEMANTIC_REVIEW")
    assert all(p["verdict"] in ("", "CARRIED") for p in t["brief"]["result_contract"]["pages"])
    w = store.complete(w["id"], t["id"], t["lease_token"], T.all_clear(t))
    t = store.claim(w["id"], "reviewer-C", "SEMANTIC_REVIEW")
    assert t["binding"] == "RELATIONS"
    chapters = t["brief"]["result_contract"]["chapters"]
    assert chapters and {c["section_id"] for c in chapters} <= {s["id"] for s in w["summary"]["sections"]}
    r = T.all_clear(t)
    r["chapters"][0].update(core_on_pages="NO", issue="TEST: 页面只有并列清单，读不出本章核心句")
    w = store.complete(w["id"], t["id"], t["lease_token"], r)
    issue = next(i for i in w["issue_ledger"]["semantic"]["issues"] if i["ref"] == chapters[0]["section_id"])
    assert issue["category"] == "EXPRESSION_AMBIGUITY" and issue["severity"] == "BLOCKER" and issue["status"] == "OPEN"


def test_issues_a_revision_cannot_fix_start_with_a_person(store):
    w = deck_ready(store)
    store.queue(w["id"], "SEMANTIC_REVIEW")
    t = store.claim(w["id"], "reviewer-B", "SEMANTIC_REVIEW")
    page = t["brief"]["pages"][2]["page"]["id"]

    def flag(r):
        r["pages"][2] = {"page_id": page, "verdict": "ISSUES", "issues": [{
            "severity": "BLOCKER", "category": "EVIDENCE_MISSING", "ref": "x.prev", "source_ref": "overview.txt 第1段",
            "evidence": "TEST", "problem": "TEST: 原件图无法辨认，需人工对照", "suggestion": "人工确认"}]}
    w = store.complete(w["id"], t["id"], t["lease_token"], T.all_clear(t, flag))
    assert w["issue_ledger"]["semantic"]["issues"][0]["status"] == "NEEDS_HUMAN"


def test_content_rules_are_frozen_per_project_and_adopted_on_record(store):
    w = store.create("规则版本", T.OUTLINE)
    assert w["rules_version"] == CONTENT_RULES_VERSION
    with store.transaction(w["id"], "TEST_OLD_RULES") as state:
        state["rules_version"] = "content-rules.TEST-OLD"
    for name, make in T.fx_.SOURCES.items():
        store.add_source(w["id"], name, make())
    with pytest.raises(WorkflowError, match="adopt-rules"):
        store.queue(w["id"], "READ_SOURCE")
    with pytest.raises(WorkflowError, match="原因"):
        store.adopt_rules(w["id"], "TEST-OPERATOR", "")
    w = store.adopt_rules(w["id"], "TEST-OPERATOR", "TEST: adopt the audited rules")
    assert w["rules_version"] == CONTENT_RULES_VERSION and w["rules_history"][-1]["from"] == "content-rules.TEST-OLD"
    store.queue(w["id"], "READ_SOURCE")


def test_transcribed_pdf_arrows_become_diagram_candidates():
    from factdeck.structure import candidates
    def cell(i, text, fig="P:p1:g1"):
        return {"id": f"P:p1:x.c{i}", "page_id": "P:p1", "figure_id": fig, "method": "visual_transcription", "arrow": None, "text": text}
    units = [cell(1, "Measure A→A ≥ 0.7"), cell(2, "Measure A→A < 0.7"), cell(3, "A < 0.7→Confirm"),     # one box, two ways out
             cell(4, "Step 1→Step 2", "P:p1:g2"), cell(5, "Step 2→Step 3", "P:p1:g2"),                 # a second figure: a chain
             cell(6, "→icon bullet without a start box"), cell(7, "Plain transcribed text")]
    found = {tuple(c["unit_ids"]): c["type"] for c in candidates(units) if c["basis"] == "arrow"}
    assert found == {("P:p1:x.c1", "P:p1:x.c2", "P:p1:x.c3"): "branch", ("P:p1:x.c4", "P:p1:x.c5"): "sequence"}


def test_a_corrected_transcription_updates_the_sources_candidates(store):
    w = summarised(store)
    cell = next(u for src in w["sources"] for u in src["transcriptions"])
    sid = cell["id"].split(":")[0]
    w = store.confirm_transcription(w["id"], cell["id"], {"reviewer": "TEST-REVIEWER", "text": "TEST 甲框→TEST 乙框", "original_checked": True})
    rel = next(src for src in w["sources"] if src["id"] == sid)["relations"]
    assert any(c["basis"] == "arrow" and cell["id"] in c["unit_ids"] for c in rel)
