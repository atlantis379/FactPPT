import copy
import pytest
import test_deckflow as T
from test_deckflow import store
from app.deckflow import WorkflowError, summary_review_current, key_point_targets


def summarised(store):
    w = store.create("虚构覆盖测试", T.OUTLINE, {"audience": "本科生"})
    for name, make in T.fx_.SOURCES.items():
        store.add_source(w["id"], name, make())
    w = T.read_all(store, w["id"])
    return T.run_task(store, w["id"], "SUMMARY", "author-A", lambda t: T.summary(w))


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra", "stale", "bad_verdict", "silent_issue", "duplicate_section", "duplicate_point"])
def test_key_point_and_duplicate_coverage_rejected(store, mutation):
    w = summarised(store)
    store.queue(w["id"], "SUMMARY_REVIEW")
    t = store.claim(w["id"], "independent-v2", "SUMMARY_REVIEW")
    result = copy.deepcopy(t["brief"]["result_contract"])
    row = result["sections"][0]
    if mutation == "missing": row["key_points"].pop()
    if mutation == "duplicate": row["key_points"].append(copy.deepcopy(row["key_points"][0]))
    if mutation == "extra": row["key_points"].append({"target_id": "invented", "verdict": "ENTAILED"})
    if mutation == "stale": row["key_points"][0]["target_id"] = "old-version:key1"
    if mutation == "bad_verdict": row["key_points"][0]["verdict"] = "PASS"
    if mutation == "silent_issue": row["key_points"][0]["verdict"] = "CONTRADICTED"
    if mutation == "duplicate_section": result["sections"].append(copy.deepcopy(row))
    if mutation == "duplicate_point":
        # Ordinary outline has no points; an unexpected point must be rejected too.
        row["points"] = [{"point_id": "fake", "verdict": "ENTAILED"}] * 2
    with pytest.raises(WorkflowError):
        store.complete(w["id"], t["id"], t["lease_token"], result)


def test_key_issue_blocks_confirmation_and_targets_bind_whole_version(store):
    w = summarised(store)
    store.queue(w["id"], "SUMMARY_REVIEW")
    t = store.claim(w["id"], "independent-v2", "SUMMARY_REVIEW")
    result = copy.deepcopy(t["brief"]["result_contract"])
    result["sections"][0]["key_points"][0].update(verdict="NOT_ENTAILED", issue="虚构测试：原文没有此断言")
    w = store.complete(w["id"], t["id"], t["lease_token"], result)
    assert w["stage"] == "SUMMARY_ISSUES"
    assert summary_review_current(w)
    first = key_point_targets(w, w["summary"]["sections"][0])[0]["target_id"]
    w["summary"]["overall_summary"] += "修订"
    assert first != key_point_targets(w, w["summary"]["sections"][0])[0]["target_id"]
    assert not summary_review_current(w)


def test_old_review_is_not_migrated_to_new_coverage(store):
    w = summarised(store)
    w = T.review_summary(store, w["id"])
    del w["summary_review"]["schema_version"]
    assert not summary_review_current(w)
