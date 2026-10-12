"""Issue ledger, two-checklist semantic review and impact-scoped regression (SEMANTIC_REVIEW_PROTOCOL.md).

Reviews here are hand-written test records, not model evidence or medical review. Content is invented.
"""
import copy

import pytest

import test_deckflow as T
from test_deckflow import store
from app.deckflow import WorkflowError, context_warnings, checked, verified
from factdeck.context import signals

BLOCKER = {"severity": "BLOCKER", "category": "CONTENT_ERROR", "source_ref": "overview.txt 第1段", "evidence": "页面所见",
           "problem": "节选未说明统计人群", "suggestion": "补出人群"}


def claim(store, wid, worker, check=None):
    store.queue(wid, "SEMANTIC_REVIEW", [check] if check else None)
    t = store.claim(wid, worker, "SEMANTIC_REVIEW", check)
    assert t, (worker, check)
    return t


def flag_overview(r):
    i = next(n for n, p in enumerate(r["pages"]) if p["page_id"] == "overview")
    r["pages"][i] = {"page_id": "overview", "verdict": "ISSUES", "issues": [{**BLOCKER, "ref": "overview"}]}


def with_issue(store):
    """A deck whose coverage checklist left one blocker on page overview."""
    w = T.to_deck(store)
    return T.semantic_review(store, w["id"], edit=lambda c, r: flag_overview(r) if c == "COVERAGE" else None)


def revise(store, w, edit_page=None, responses=None):
    d = copy.deepcopy(w["deck"]["result"])
    d["facts_sha256"] = w["facts"]["result_sha256"]
    if edit_page:
        edit_page(d)
    if responses is not None:
        d["issue_responses"] = responses
    return store.author(w["id"], "DECK", d, "author-A")


def test_issue_ids_are_stable_and_a_new_round_must_answer_every_open_issue(store):
    w = with_issue(store)
    assert [i["id"] for i in w["issue_ledger"]["semantic"]["issues"]] == ["SEM-0001"]
    # a revision has to answer every unresolved issue
    with pytest.raises(WorkflowError, match="逐条回应"):
        revise(store, w, lambda d: d["pages"][2]["title"].update(text="示例病X的定义"))
    w = revise(store, w, lambda d: d["pages"][2]["title"].update(text="示例病X的定义"),
               [{"issue_id": "SEM-0001", "action": "CHANGED", "pages": ["overview"], "note": "补出人群"}])
    t = claim(store, w["id"], "reviewer-B", "COVERAGE")
    assert [i["id"] for i in t["brief"]["prior_issues"]] == ["SEM-0001"]
    assert t["brief"]["prior_issues"][0]["author_response"]["action"] == "CHANGED"
    r = T.all_clear(t)
    r["prior_issues"] = []
    with pytest.raises(WorkflowError, match="缺少 SEM-0001"):
        store.complete(w["id"], t["id"], t["lease_token"], r)
    r["prior_issues"] = [{"issue_id": "SEM-0001", "status": "FIXED", "evidence": "已修订", "evidence_refs": []}]
    with pytest.raises(WorkflowError, match="evidence_refs"):
        store.complete(w["id"], t["id"], t["lease_token"], r)
    r["prior_issues"] = [{"issue_id": "SEM-0001", "status": "OPEN", "evidence": "仍未写人群", "evidence_refs": []}]
    with pytest.raises(WorkflowError, match="判为通过"):                  # page judged fine but the issue left open
        store.complete(w["id"], t["id"], t["lease_token"], r)
    r["prior_issues"] = [{"issue_id": "SEM-0001", "status": "FIXED", "evidence": "标题与节选已写明成人", "evidence_refs": ["overview"]}]
    w = store.complete(w["id"], t["id"], t["lease_token"], r)
    issue = w["issue_ledger"]["semantic"]["issues"][0]
    assert issue["status"] == "FIXED" and [h["status"] for h in issue["history"]] == ["OPEN", "FIXED"]


def test_needs_human_items_wait_for_a_ruling_and_cannot_loop_through_revisions(store):
    w = T.to_deck(store)

    def unknown(check, r):
        if check == "RELATIONS":
            r["relations"][0].update(verdict="UNKNOWN", issue="原文只列出条目，未说明须同时满足还是任选其一")
    w = T.semantic_review(store, w["id"], edit=unknown)
    issue = w["issue_ledger"]["semantic"]["issues"][0]
    assert issue["status"] == "NEEDS_HUMAN" and issue["category"] == "HUMAN_DECISION"
    assert "语义审查有 1 个阻断问题（其中 1 个须人工裁定" in " ".join(w["open_items"])
    w = store.dismiss_issue(w["id"], issue["id"], {"reviewer": "TEST-REVIEWER", "reason": "按原文列表呈现，页面不表达合取或择一"})
    assert w["issue_ledger"]["semantic"]["issues"][0]["status"] == "HUMAN_RULED"
    with pytest.raises(WorkflowError, match="已闭环"):
        store.dismiss_issue(w["id"], issue["id"], {"reviewer": "TEST-REVIEWER", "reason": "again"})


def test_coverage_needs_a_status_for_every_source_page_and_teaching_item(store):
    w = T.to_deck(store)
    t = claim(store, w["id"], "reviewer-B", "COVERAGE")
    inv = t["brief"]["source_pages"]
    assert inv and all("regions" in r and "presented_on" in r for r in inv)
    assert {r["kind"] for r in t["brief"]["teaching_items"]} >= {"outline", "section", "key_point"}
    r = T.all_clear(t)
    r["source_pages"].pop()
    with pytest.raises(WorkflowError, match="每个来源页都须给出状态"):
        store.complete(w["id"], t["id"], t["lease_token"], r)
    r = T.all_clear(t)
    blank = next(x for x in r["source_pages"] if x["status"] == "EXCLUDED")
    blank.update(status="NEEDS_HUMAN", reason="是否讲授这一页需要用户决定")
    w = store.complete(w["id"], t["id"], t["lease_token"], r)
    i = w["issue_ledger"]["semantic"]["issues"][0]
    assert i["ref"] == blank["source_page_id"] and i["status"] == "NEEDS_HUMAN"
    rec = w["semantic_checks"]["COVERAGE"]
    assert rec["counts"]["source_pages"] == len(inv) and rec["counts"]["deck_pages_read"] == rec["counts"]["deck_pages"]


def test_after_a_small_revision_only_affected_pages_are_reread(store):
    w = T.to_deck(store)
    w = T.semantic_review(store, w["id"])
    assert "语义审查" not in " ".join(w["open_items"])
    w = revise(store, w, lambda d: next(p for p in d["pages"] if p["id"] == "followup")["title"].update(text="随访"))
    t = claim(store, w["id"], "reviewer-B", "COVERAGE")
    reg = t["brief"]["regression"]
    assert reg["mode"] == "IMPACT" and reg["changed"] == ["followup"]
    assert set(reg["affected"]) == {"studies", "followup", "end"}            # neighbours re-read for continuity
    carried = {p["page_id"] for p in t["brief"]["result_contract"]["pages"] if p["verdict"] == "CARRIED"}
    assert carried == {"cover", "part1", "overview", "criteria", "flow", "drugs"}
    r = T.all_clear(t)
    next(p for p in r["pages"] if p["page_id"] == "followup")["verdict"] = "CARRIED"
    with pytest.raises(WorkflowError, match="受本次修订影响"):
        store.complete(w["id"], t["id"], t["lease_token"], r)
    w = store.complete(w["id"], t["id"], t["lease_token"], T.all_clear(t))
    assert w["semantic_checks"]["COVERAGE"]["counts"]["deck_pages_carried"] == 6


def test_the_two_checklists_need_different_independent_workers(store):
    w = T.to_deck(store)
    t = claim(store, w["id"], "reviewer-B", "COVERAGE")
    w = store.complete(w["id"], t["id"], t["lease_token"], T.all_clear(t))
    assert "需要独立语义审查：语义/关系检查" in " ".join(w["open_items"])
    assert store.claim(w["id"], "reviewer-B", "SEMANTIC_REVIEW") is None


def test_legacy_review_issues_are_carried_into_the_ledger(store):
    w = T.to_deck(store)
    with store.transaction(w["id"], "TEST_LEGACY") as ww:            # a review stored before the ledger existed
        ww["semantic_review"] = {"input_sha256": "old", "reviewer": "old-reviewer", "at": "2026-10-08",
                                 "issues": [{"id": "overview#1", "page_id": "overview", "severity": "BLOCKER", "ref": "x.prev", "problem": "旧问题"},
                                            {"id": "coverage#s3", "page_id": None, "severity": "BLOCKER", "ref": "s3", "problem": "旧覆盖问题"}],
                                 "dismissed": {}}
        ww.pop("issue_ledger", None)
    w = store.get(w["id"])
    ids = {i["legacy_id"]: (i["id"], i["check"]) for i in w["issue_ledger"]["semantic"]["issues"]}
    assert ids == {"overview#1": ("SEM-0001", "RELATIONS"), "coverage#s3": ("SEM-0002", "COVERAGE")}
    t = claim(store, w["id"], "reviewer-B", "COVERAGE")
    assert [i["id"] for i in t["brief"]["prior_issues"]] == ["SEM-0002"]


def test_summary_issues_keep_their_id_across_rounds_and_closure_must_agree_with_the_verdicts(store):
    import test_summary_review_coverage as S
    w = S.summarised(store)
    store.queue(w["id"], "SUMMARY_REVIEW")
    t = store.claim(w["id"], "reviewer-S", "SUMMARY_REVIEW")
    r = copy.deepcopy(t["brief"]["result_contract"])
    r["sections"][0].update(summary_verdict="NOT_ENTAILED", summary_issue="原文没有这一归纳")
    w = store.complete(w["id"], t["id"], t["lease_token"], r)
    assert w["stage"] == "SUMMARY_ISSUES" and w["issue_ledger"]["summary"]["issues"][0]["id"] == "SR-0001"
    # a revised summary goes back to review; the next reviewer must answer SR-0001
    s = copy.deepcopy(w["summary"])
    s["sections"][0]["summary"] += "（修订）"
    w = store.author(w["id"], "SUMMARY", s, "author-A")
    store.queue(w["id"], "SUMMARY_REVIEW")
    t = store.claim(w["id"], "reviewer-T", "SUMMARY_REVIEW")
    assert [i["id"] for i in t["brief"]["prior_issues"]] == ["SR-0001"]
    r = copy.deepcopy(t["brief"]["result_contract"])
    r["sections"][0].update(summary_verdict="NOT_ENTAILED", summary_issue="仍没有依据")
    r["prior_issues"] = [{"issue_id": "SR-0001", "status": "FIXED", "evidence": "已修订", "evidence_refs": ["s1"]}]
    with pytest.raises(WorkflowError, match="仍有问题"):
        store.complete(w["id"], t["id"], t["lease_token"], r)
    r["prior_issues"][0].update(status="OPEN", evidence="修订后仍无依据", evidence_refs=[])
    w = store.complete(w["id"], t["id"], t["lease_token"], r)
    issues = w["issue_ledger"]["summary"]["issues"]
    assert len(issues) == 1 and issues[0]["problem"].endswith("仍没有依据") and len(issues[0]["history"]) == 2


def test_open_notes_must_be_acknowledged_at_content_confirmation(store):
    import test_summary_review_coverage as S
    w = S.summarised(store)
    store.queue(w["id"], "SUMMARY_REVIEW")
    t = store.claim(w["id"], "reviewer-S", "SUMMARY_REVIEW")
    r = copy.deepcopy(t["brief"]["result_contract"])
    r["sections"][0].update(summary_verdict="PARTIAL", summary_issue="缺少人群限定")
    w = store.complete(w["id"], t["id"], t["lease_token"], r)
    assert w["stage"] == "CONTENT_CONFIRMATION" and w["content_acknowledge"] == ["SR-0001"]
    rec = {"customer": "TEST-CUSTOMER", "operator": "TEST-OPERATOR", "method": "AUTOMATED_PROTOCOL_TEST_NOT_REAL_APPROVAL",
           "subject_sha256": w["approval_subjects"]["content"]}
    with pytest.raises(WorkflowError, match="已知悉"):
        store.approval(w["id"], "content", rec)
    w = store.approval(w["id"], "content", {**rec, "acknowledged_issues": ["SR-0001"]})
    assert w["content_approval"]["acknowledged_issues"] == ["SR-0001"]


def test_context_signals_flag_lead_ins_connectives_and_cut_units():
    kinds = lambda *a: [s["kind"] for s in signals(*a)]
    assert kinds("可考虑以下选项：", None, "对于持续加重者，可考虑以下选项：生物制剂") == ["lead_in", "unit_continues", "unit_precedes"]
    assert kinds("然而，不推荐使用", None, "然而，不推荐使用") == ["leading_connective"]
    assert kinds("成人患病率约为12.5%", None, "成人患病率约为12.5%") == []


def test_deck_warns_about_a_lead_in_without_its_items(store):
    w = T.to_deck(store)
    v = verified(w)
    v["facts"]["dx.rule"] = {**v["facts"]["dx.rule"], "display": "诊断需同时满足以下条件："}
    warn = context_warnings(w, w["deck"]["result"], checked(w), v)
    assert any(x.startswith("overview：dx.rule 是列表或下文的引导句") for x in warn), warn


def test_archived_checkpoint_reuses_evidence_without_approving_or_closing_live_issues(store):
    from app import semantic_review as sem
    from app.fact57098 import digest
    w = T.to_deck(store)
    t = claim(store, w['id'], 'archived-reviewer', 'COVERAGE')
    r = T.all_clear(t)
    w = store.get(w['id'])
    before = copy.deepcopy(w)
    receipt = {'task_id': t['id'], 'worker': t['worker'],
               'input_sha256': r['input_sha256'], 'result_sha256': digest(r)}
    sem.checkpoint(w, r, t['worker'], 'COVERAGE', receipt=receipt)
    assert w.get('semantic_checks') == before.get('semantic_checks')
    assert w.get('issue_ledger') == before.get('issue_ledger')
    assert not sem.check_current(w, 'COVERAGE')
    assert sem.regression(w, 'COVERAGE', sem.context(w))['mode'] == 'IMPACT'
    w['summary']['overall_summary'] += 'changed scope'
    assert sem.regression(w, 'COVERAGE', sem.context(w))['mode'] == 'FULL'


def test_checkpoint_rejects_changed_archived_result(store):
    from app import semantic_review as sem
    w = T.to_deck(store)
    t = claim(store, w['id'], 'archived-reviewer', 'COVERAGE')
    r = T.all_clear(t)
    with pytest.raises(WorkflowError, match='校验值'):
        sem.checkpoint(w, r, t['worker'], 'COVERAGE', receipt={'task_id': t['id'],
            'worker': t['worker'], 'input_sha256': r['input_sha256'], 'result_sha256': 'invalid'})


def test_existing_issue_reference_preserves_id_when_reported_on_a_page(store):
    from app import review_ledger as ledger
    w = with_issue(store)
    prior = [{'issue_id':'SEM-0001','status':'NEEDS_HUMAN','evidence':'来源关系未明','evidence_refs':[]}]
    result = ledger.record_round(w, 'semantic', 'COVERAGE', reviewer='reviewer-B', input_sha256='test',
        dispositions=prior, valid_refs={'overview'}, new_issues=[{**BLOCKER,'category':'HUMAN_DECISION',
            'ref':'overview','relation':'','existing_issue_id':'SEM-0001'}])
    assert not result['new'] and result['merged'] == ['SEM-0001']
    assert len(ledger.issues(w,'semantic')) == 1
