"""Semantic-first route in the deckflow: the model maps the material and works out each topic; code cuts the sentences,
attaches them and checks every reference.

Content is invented; maps and topic passes here are test records, not model output.
"""
import copy

import pytest

from app.deckflow import Store, WorkflowError, all_units
from app import semantic_map_stage as sm
from factdeck.auto_claims import row_key
import factdeck_fixture as fx_
from test_outline_structure import OUTLINE


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "map-data")


def read_with_map(store):
    w = store.create("语义地图", OUTLINE, semantic_map_first=True)
    for name, make in fx_.SOURCES.items():
        store.add_source(w["id"], name, make())
    store.queue(w["id"], "READ_SOURCE")
    while t := store.claim(w["id"], "reader-1", "READ_SOURCE"):
        r = copy.deepcopy(t["brief"]["result_contract"])
        for row in r["pages"]:
            row["visual_inspected"] = True
        store.complete(w["id"], t["id"], t["lease_token"], r)
    return store.get(w["id"])


def map_result(brief, split=1):
    """Two topics: the first `split` sources' units, then the rest (test record)."""
    units = [[u["id"] for p in s["pages"] for u in p["units"]] for s in brief["sources"]]
    r = copy.deepcopy(brief["result_contract"])
    r["one_liner"] = "资料先讲定义再讲处理。"
    r["nodes"] = [{"id": "n1", "title": "定义", "role": "definition", "thesis": "这一部分说明概念。",
                   "unit_hints": [u for g in units[:split] for u in g], "mainline": True, "pages": 1},
                  {"id": "n2", "title": "处理", "role": "pathway", "thesis": "这一部分说明处理路径。",
                   "unit_hints": [u for g in units[split:] for u in g], "mainline": False}]
    r["edges"] = [{"from": "n1", "to": "n2", "relation": "sequence"}]
    return r


def mapped(store):
    w = read_with_map(store)
    store.queue(w["id"], "SEMANTIC_MAP")
    t = store.claim(w["id"], "mapper-1", "SEMANTIC_MAP")
    store.complete(w["id"], t["id"], t["lease_token"], map_result(t["brief"]))
    return store.get(w["id"])


def topic_result(brief):
    """One core message citing the first sentence; every other sentence left out by id (test record)."""
    sent = [s[0] for s in brief["sentences"] if s[1] == "sentence"]
    r = copy.deepcopy(brief["result_contract"])
    r["question"] = "这一主题回答什么？"
    r["messages"] = [{"id": "m1", "role": "core", "label": "主题要点", "claims": sent[:1]}]
    r["relations"] = []
    r["page_plan"] = [["m1"]]
    rows = sorted({row_key(c[0].rsplit("~", 1)[0]) for c in brief["sentences"] if c[1] == "cell"})
    r["checks"] = []
    r["left_out"] = ([{"ids": [x], "why": "off_topic", "note": f"测试记录：第{i}句不讲"} for i, x in enumerate(sent[1:], 1)]
                     + [{"row": x, "why": "off_topic", "note": f"测试记录：表格行{x}不讲"} for x in rows])
    return r


def test_map_comes_after_reading_and_claims_are_not_a_model_task(store):
    w = read_with_map(store)
    assert w["stage"] == "SEMANTIC_MAP_REQUIRED"
    with pytest.raises(WorkflowError, match="语义地图"):
        store.queue(w["id"], "TOPIC_PASS")
    store.queue(w["id"], "SEMANTIC_MAP")
    t = store.claim(w["id"], "mapper-1", "SEMANTIC_MAP")
    b = t["brief"]
    assert not any("哮喘" in r for r in b["rules"])          # rules stay domain-neutral
    bad = map_result(b)
    bad["nodes"][0]["unit_hints"].append("no-such-unit")
    with pytest.raises(WorkflowError, match="不存在的单元"):
        store.complete(w["id"], t["id"], t["lease_token"], bad)
    gap = map_result(b)
    gap["nodes"][1]["unit_hints"] = []
    with pytest.raises(WorkflowError, match="没有归入任何节点"):
        store.complete(w["id"], t["id"], t["lease_token"], gap)
    digits = map_result(b)
    digits["one_liner"] = "资料讲了3件事。"
    with pytest.raises(WorkflowError, match="DIGITS"):
        store.complete(w["id"], t["id"], t["lease_token"], digits)
    store.complete(w["id"], t["id"], t["lease_token"], map_result(b))
    w = store.get(w["id"])
    assert w["stage"] == "TOPICS_REQUIRED"
    with pytest.raises(WorkflowError, match="不再安排论断清单"):
        store.queue(w["id"], "CLAIMS")


def test_each_topic_is_worked_out_by_the_model_and_checked_by_code(store):
    w = mapped(store)
    store.queue(w["id"], "TOPIC_PASS")
    assert sorted(t["binding"] for t in store.get(w["id"])["tasks"] if t["kind"] == "TOPIC_PASS" and t["status"] == "PENDING") == ["n1", "n2"]
    t = store.claim(w["id"], "topic-1", "TOPIC_PASS")
    b = t["brief"]
    assert b["topic"]["id"] == t["binding"] and b["sentences"]

    def refused(change, match):
        r = topic_result(b)
        change(r)
        with pytest.raises(WorkflowError, match=match):
            store.complete(w["id"], t["id"], t["lease_token"], r)

    refused(lambda r: r["messages"][0]["claims"].append("nowhere~1"), "不存在的句子")
    refused(lambda r: r["messages"][0].update(label="第3点"), "不能写数字")
    if sum(1 for s in b["sentences"] if s[1] == "sentence") > 1:
        refused(lambda r: r.update(left_out=[]), "既没有引用")
    refused(lambda r: r.update(page_plan=[["m1"], ["m1"]]), "恰好放一次")
    refused(lambda r: r["messages"][0].update(role="key"), "role")
    store.complete(w["id"], t["id"], t["lease_token"], topic_result(b))
    while t := store.claim(w["id"], "topic-1", "TOPIC_PASS"):
        store.complete(w["id"], t["id"], t["lease_token"], topic_result(t["brief"]))
    w = store.get(w["id"])
    assert w["stage"] == "CONTENT_CONFIRMATION"

    d = sm.draft(w)
    assert [x["id"] for x in d["topics"]] == ["n1", "n2"] and all(x["current"] for x in d["topics"])
    units = {u["id"]: u for u in all_units(w)}
    cl = sm.claims(w)
    for x in d["topics"]:
        for m in x["messages"]:
            for s in m["sentences"]:
                c = cl[s["id"]]
                assert units[c["unit_id"]]["text"][c["start"]:c["end"]] == s["quote"]
    assert "## 定义" in sm.draft_markdown(d)


def test_a_new_map_makes_topic_passes_stale(store):
    w = mapped(store)
    store.queue(w["id"], "TOPIC_PASS")
    while t := store.claim(w["id"], "topic-1", "TOPIC_PASS"):
        store.complete(w["id"], t["id"], t["lease_token"], topic_result(t["brief"]))
    assert store.get(w["id"])["stage"] == "CONTENT_CONFIRMATION"
    with store.transaction(w["id"], "TEST_REMAP") as ww:     # a different accepted map
        b = sm.brief(ww)
        sm.accept(ww, {**map_result(b, split=0), "input_sha256": b["input_sha256"]}, "mapper-2")
    w = store.get(w["id"])
    assert w["stage"] == "TOPICS_REQUIRED" and w["summary"] is None


def worked_out(store):
    w = mapped(store)
    store.queue(w["id"], "TOPIC_PASS")
    while t := store.claim(w["id"], "topic-1", "TOPIC_PASS"):
        store.complete(w["id"], t["id"], t["lease_token"], topic_result(t["brief"]))
    return store.get(w["id"])


def approve_draft(store, w):
    return store.approval(w["id"], "content", {"customer": "TEST-CUSTOMER", "operator": "TEST-OPERATOR",
                                               "method": "AUTOMATED_PROTOCOL_TEST_NOT_REAL_APPROVAL",
                                               "subject_sha256": w["approval_subjects"]["content"]})


def test_the_confirmed_draft_becomes_the_fact_store_and_the_deck_brief(store):
    w = worked_out(store)
    assert w["summary"]["summary_algorithm"] == sm.SUMMARY_ALGORITHM
    with pytest.raises(WorkflowError, match="确认稿已更新"):
        store.approval(w["id"], "content", {"customer": "C", "operator": "O", "method": "M", "subject_sha256": "stale"})
    w = approve_draft(store, w)
    assert w["stage"] == "DECK_REQUIRED"                            # no FACTS task: code built the store at confirmation
    assert w["facts"]["author"] == sm.FACTS_AUTHOR and w["facts"]["rejected"] == 0
    cited = sm.cited(w)
    assert [f["id"] for f in w["facts"]["result"]["facts"]] == cited and cited
    with pytest.raises(WorkflowError, match="代码在客户确认初稿时生成"):
        store.queue(w["id"], "FACTS")
    store.queue(w["id"], "DECK")
    b = store.claim(w["id"], "author-A", "DECK")["brief"]
    assert [t["section_id"] for t in b["topic_draft"]] == ["n1", "n2"]
    assert b["topic_draft"][0]["messages"][0] == {"key_point_id": "n1.k1", "role": "core", "label": "主题要点",
                                                  "facts": w["summary"]["sections"][0]["key_points"][0]["claim_ids"]}
    assert "topic_draft" in b["rules"][0]


def test_every_core_and_limit_message_must_reach_a_page(store):
    from app.deck_scope import check_spec
    from app.deckflow import summary_key_points, summary_point_roles, verified
    w = approve_draft(store, worked_out(store))
    chk = check_spec({"pages": []}, verified(w)["facts"], [], w["outline"], w["summary"]["sections"], w["requirements"],
                     w.get("outline_parts"), key_points=summary_key_points(w), key_roles=summary_point_roles(w))
    assert any("核心或限定要点" in e and "n1.k1" in e and "n2.k1" in e for e in chk["deck_errors"])


def test_existing_projects_keep_the_old_order(store):
    w = store.create("旧项目", OUTLINE)
    assert not w.get("semantic_map_first")
    with pytest.raises(WorkflowError, match="semantic_map_first"):
        store.queue(w["id"], "SEMANTIC_MAP")
