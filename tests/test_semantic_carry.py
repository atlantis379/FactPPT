"""SEMANTIC_REVIEW carries forward earlier independent passes whose content fingerprint is unchanged.

Reviews here are hand-written test records, not model evidence or medical review. Content is invented.
"""
import copy

import pytest

import test_deckflow as T
from test_deckflow import store
from test_review_ledger import BLOCKER, claim, flag_overview, revise
from app import semantic_review as sem
from app.deckflow import WorkflowError

ALL_PAGES = ["cover", "part1", "overview", "criteria", "flow", "drugs", "studies", "followup", "end"]


def edit_followup(d):
    next(p for p in d["pages"] if p["id"] == "followup")["title"].update(text="随访")


def edit_followup_again(d):
    next(p for p in d["pages"] if p["id"] == "followup")["title"].update(text="随访安排")


def reviewed_then_revised(store, edit=None):
    """Both checklists all clear (reviewer-B: COVERAGE, reviewer-C: RELATIONS), then the title of page followup edited."""
    w = T.semantic_review(store, T.to_deck(store)["id"], edit=edit)
    return revise(store, w, edit_followup)


def contract_ids(t, key, id_key):
    return [x[id_key] for x in t["brief"]["result_contract"].get(key) or []]


def test_unchanged_items_keep_an_earlier_pass_and_leave_the_brief(store):
    w = reviewed_then_revised(store)
    t = claim(store, w["id"], "reviewer-B", "COVERAGE")
    b = t["brief"]
    assert b["carried_review"]["pages"] == {"count": 6, "of": 9}
    assert contract_ids(t, "pages", "page_id") == ["studies", "followup", "end"]
    assert [p["page"]["id"] for p in b["pages"]] == ["studies", "followup", "end"]
    assert b["carried_review"]["teaching_items"]["count"] > 0 and b["carried_review"]["source_pages"]["count"] > 0
    assert len(contract_ids(t, "teaching_items", "item_id")) == b["carried_review"]["teaching_items"]["of"] - b["carried_review"]["teaching_items"]["count"]
    assert any(r.startswith("本轮沿用此前独立审核的通过判定：页面6/9") for r in b["rules"])
    w = store.complete(w["id"], t["id"], t["lease_token"], T.all_clear(t))
    rec = w["semantic_checks"]["COVERAGE"]
    assert set(rec["page_verdicts"]) == set(ALL_PAGES) and set(rec["page_verdicts"].values()) == {"SUPPORTED"}
    assert rec["counts"]["deck_pages_read"] == 3 and rec["counts"]["deck_pages_carried_passes"] == 6
    assert len(rec["teaching_items"]) == rec["counts"]["teaching_items"] == b["carried_review"]["teaching_items"]["of"]
    assert rec["reviewers"] == ["reviewer-B"] and rec["carry_memory"]

    t = claim(store, w["id"], "reviewer-C", "RELATIONS")
    c = t["brief"]["carried_review"]
    assert c["pages"]["count"] == 6 and c["relations"]["count"] > 0
    assert len(contract_ids(t, "relations", "relation_id")) == c["relations"]["of"] - c["relations"]["count"]
    assert len(t["brief"]["relations"]) == c["relations"]["of"] - c["relations"]["count"]
    assert len(contract_ids(t, "chapters", "section_id")) == c["chapters"]["of"] - c["chapters"]["count"]
    w = store.complete(w["id"], t["id"], t["lease_token"], T.all_clear(t))
    assert len(w["semantic_checks"]["RELATIONS"]["relations"]) == c["relations"]["of"]
    assert "语义审查" not in " ".join(w["open_items"])

    # a third round: carried passes keep their original round and reviewer
    first = w["issue_ledger"]["semantic"]["rounds"][0]["round"]
    w = revise(store, w, edit_followup_again)
    t = claim(store, w["id"], "reviewer-B", "COVERAGE")
    assert contract_ids(t, "pages", "page_id") == ["studies", "followup", "end"]
    w = store.complete(w["id"], t["id"], t["lease_token"], T.all_clear(t))
    rows = store.semantic_memory(w, "COVERAGE")[1]["rows"]
    assert rows["pages:cover"]["round"] == first and rows["pages:followup"]["round"] > first


def reopened(store, w, check, change):
    """Pages whose carry a change to a copy of the project re-opens."""
    _, memory = store.semantic_memory(w, check)
    before = sem.carried(w, check, sem.context(w), memory)["pages"]
    w2 = copy.deepcopy(w)
    change(w2)
    after = sem.carried(w2, check, sem.context(w2), memory)["pages"]
    assert set(after) <= set(before)
    return set(before) - set(after)


def neighbours(pages):
    out = set(pages)
    for p in pages:
        i = ALL_PAGES.index(p)
        out |= {ALL_PAGES[j] for j in (i - 1, i + 1) if 0 <= j < len(ALL_PAGES)}
    return out


def test_a_changed_display_text_or_source_unit_reopens_only_the_page_that_shows_it(store):
    w = T.semantic_review(store, T.to_deck(store)["id"])
    ctx = sem.context(w)
    assert set(sem.carried(w, "COVERAGE", ctx, store.semantic_memory(w, "COVERAGE")[1])["pages"]) == set(ALL_PAGES)
    on = lambda f: [p for p in ALL_PAGES if f in ctx["page_facts"][p]]
    assert on("b.dose") == ["drugs"]

    def display(w2):                                     # the fact's display text, shortened within its quote
        fact = next(f for f in w2["facts"]["result"]["facts"] if f["id"] == "b.dose")
        fact["display"] = "剂量为100mg"
    for check in sem.CHECKS:
        assert reopened(store, w, check, display) == neighbours(["drugs"]) == {"flow", "drugs", "studies"}

    unit = ctx["v"]["facts"]["fu"]["unit"]
    showing = [p for p in ALL_PAGES if unit in ctx["page_units"][p]]
    assert showing and len(neighbours(showing)) < len(ALL_PAGES)

    def source(w2):                                      # the cited unit's source text changes
        u = next(u for s in w2["sources"] for u in s["units"] if u["id"] == unit)
        u["text"] += "（补充说明）"
    assert reopened(store, w, "COVERAGE", source) == neighbours(showing)


def test_a_result_that_judges_a_carried_item_again_is_refused(store):
    w = reviewed_then_revised(store)
    t = claim(store, w["id"], "reviewer-B", "COVERAGE")
    r = T.all_clear(t)
    r["pages"].insert(0, {"page_id": "cover", "verdict": "SUPPORTED", "issues": []})
    with pytest.raises(WorkflowError, match="沿用通过判定的页面不在本轮pages中：cover"):
        store.complete(w["id"], t["id"], t["lease_token"], r)
    r = T.all_clear(t)
    r["pages"].pop(0)                                    # a listed page left out is still refused
    with pytest.raises(WorkflowError, match="逐页"):
        store.complete(w["id"], t["id"], t["lease_token"], r)
    carried_item = next(k for k in store.semantic_memory(store.get(w["id"]), "COVERAGE")[1]["rows"]
                        if k.startswith("teaching_items:") and k.split(":", 1)[1] not in contract_ids(t, "teaching_items", "item_id"))
    r = T.all_clear(t)
    r["teaching_items"].append({"item_id": carried_item.split(":", 1)[1], "status": "EXCLUDED", "deck_pages": [], "reason": "测试"})
    with pytest.raises(WorkflowError, match="沿用通过判定的教学条目"):
        store.complete(w["id"], t["id"], t["lease_token"], r)
    w = store.complete(w["id"], t["id"], t["lease_token"], T.all_clear(t))

    t = claim(store, w["id"], "reviewer-C", "RELATIONS")
    listed = set(contract_ids(t, "relations", "relation_id"))
    carried_rel = next(k.split(":", 1)[1] for k in store.semantic_memory(w, "RELATIONS")[1]["rows"]
                       if k.startswith("relations:") and k.split(":", 1)[1] not in listed)
    r = T.all_clear(t)
    r["relations"].append({"relation_id": carried_rel, "verdict": "SUPPORTED", "issue": ""})
    with pytest.raises(WorkflowError, match="沿用通过判定的关系"):
        store.complete(w["id"], t["id"], t["lease_token"], r)


def test_open_issues_are_still_dispositioned_and_their_pages_are_judged_again(store):
    w = T.semantic_review(store, T.to_deck(store)["id"], edit=lambda c, r: flag_overview(r) if c == "COVERAGE" else None)
    assert [i["id"] for i in w["issue_ledger"]["semantic"]["issues"]] == ["SEM-0001"]
    w = revise(store, w, edit_followup, [{"issue_id": "SEM-0001", "action": "NOT_CHANGED", "note": "本轮只改随访页"}])
    t = claim(store, w["id"], "reviewer-B", "COVERAGE")
    pages = contract_ids(t, "pages", "page_id")
    assert "overview" in pages and "criteria" not in pages and "cover" not in pages     # the issue's page is listed
    assert [i["id"] for i in t["brief"]["prior_issues"]] == ["SEM-0001"]
    r = T.all_clear(t)
    r["prior_issues"] = []
    with pytest.raises(WorkflowError, match="缺少 SEM-0001"):
        store.complete(w["id"], t["id"], t["lease_token"], r)
    r["prior_issues"] = [{"issue_id": "SEM-0001", "status": "OPEN", "evidence": "仍未写人群", "evidence_refs": []}]
    with pytest.raises(WorkflowError, match="判为通过"):
        store.complete(w["id"], t["id"], t["lease_token"], r)
    i = pages.index("overview")
    r["pages"][i] = {"page_id": "overview", "verdict": "ISSUES", "issues": [{**BLOCKER, "ref": "overview"}]}
    w = store.complete(w["id"], t["id"], t["lease_token"], r)
    issue = w["issue_ledger"]["semantic"]["issues"]
    assert len(issue) == 1 and issue[0]["status"] == "OPEN"                 # merged into SEM-0001, not duplicated
    # an item an open issue sits on never enters the memory: the next round lists it again
    rows = store.semantic_memory(w, "COVERAGE")[1]["rows"]
    assert "pages:overview" not in rows and "pages:criteria" in rows
    w = revise(store, w, edit_followup_again, [{"issue_id": "SEM-0001", "action": "NOT_CHANGED", "note": "仍待处理"}])
    t = claim(store, w["id"], "reviewer-B", "COVERAGE")
    assert contract_ids(t, "pages", "page_id") == ["overview", "studies", "followup", "end"]
    assert [i["id"] for i in t["brief"]["prior_issues"]] == ["SEM-0001"]


def test_identity_rules_hold_for_carried_passes(store):
    w = reviewed_then_revised(store)
    store.queue(w["id"], "SEMANTIC_REVIEW")
    assert store.claim(w["id"], "author-A", "SEMANTIC_REVIEW") is None
    # whoever's passes the other checklist would carry is not handed this one
    assert store.claim(w["id"], "reviewer-C", "SEMANTIC_REVIEW", "COVERAGE") is None
    assert store.claim(w["id"], "reviewer-B", "SEMANTIC_REVIEW", "RELATIONS") is None
    # a new COVERAGE reviewer keeps reviewer-B's carried passes, which stay reviewer-B's
    t = claim(store, w["id"], "reviewer-D", "COVERAGE")
    w = store.complete(w["id"], t["id"], t["lease_token"], T.all_clear(t))
    rec = w["semantic_checks"]["COVERAGE"]
    assert rec["reviewer"] == "reviewer-D" and rec["reviewers"] == ["reviewer-B", "reviewer-D"]
    rows = store.semantic_memory(w, "COVERAGE")[1]["rows"]
    assert rows["pages:cover"]["reviewer"] == "reviewer-B" and rows["pages:followup"]["reviewer"] == "reviewer-D"
    assert w["semantic_review"]["checks"]["COVERAGE"]["reviewers"] == ["reviewer-B", "reviewer-D"]
    # so reviewer-B may not do RELATIONS on this version, neither through claim nor by a direct result
    assert store.claim(w["id"], "reviewer-B", "SEMANTIC_REVIEW", "RELATIONS") is None
    t = claim(store, w["id"], "reviewer-C", "RELATIONS")
    with store.transaction(w["id"], "TEST_IDENTITY") as ww:
        with pytest.raises(WorkflowError, match="不同的独立执行端"):
            store.accept_semantic(ww, T.all_clear(t), "reviewer-B", "RELATIONS", t["brief"])
        with pytest.raises(WorkflowError, match="编写事实库和页面之外"):
            store.accept_semantic(ww, T.all_clear(t), "author-A", "RELATIONS", t["brief"])
    # passes are never carried under an identity that is now an author
    w = store.get(w["id"])
    ctx = sem.context(w)
    memory = store.semantic_memory(w, "COVERAGE")[1]
    w2 = copy.deepcopy(w)
    w2["deck"]["author"] = "reviewer-B"
    assert sem.carried(w, "COVERAGE", ctx, memory)["pages"] and not {
        p for p, e in sem.carried(w2, "COVERAGE", ctx, memory)["pages"].items() if e["reviewer"] == "reviewer-B"}
