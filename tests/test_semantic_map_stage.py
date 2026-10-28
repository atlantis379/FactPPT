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
    assert isinstance(b["cut_warnings"], dict) and set(b["cut_warning_codes"]) == {"orphan_close", "open_at_end", "starts_mid", "too_long"}

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


def test_a_referral_arriving_while_a_topic_runs_does_not_cancel_it(store):
    """Topics run in parallel: n1 referring a sentence to n2 while n2 is out must not void n2's work; n2 answers for
    the new sentence in a follow-up pass that starts from its accepted result."""
    w = mapped(store)
    store.queue(w["id"], "TOPIC_PASS")
    t1 = store.claim(w["id"], "topic-1", "TOPIC_PASS", "n1")
    t2 = store.claim(w["id"], "topic-2", "TOPIC_PASS", "n2")
    r1 = topic_result(t1["brief"])
    moved = next(x for x in r1["left_out"] if "ids" in x)
    moved.update(why="other_topic", topic="n2", note="测试记录：属于处理主题")
    store.complete(w["id"], t1["id"], t1["lease_token"], r1)
    store.complete(w["id"], t2["id"], t2["lease_token"], topic_result(t2["brief"]))   # not refused: the referral is new
    w = store.get(w["id"])
    assert sm.topic_current(w, "n2") and sm.pending_referrals(w, "n2") == {moved["ids"][0]: "n1"}
    assert w["stage"] == "TOPICS_REQUIRED" and "新转来的句子" in w["open_items"][0] and w["summary"] is None
    store.queue(w["id"], "TOPIC_PASS")
    t = store.claim(w["id"], "topic-2", "TOPIC_PASS")
    b = t["brief"]
    assert t["binding"] == "n2" and b["new_referrals"] == moved["ids"] and b["revision_base"]["messages"]
    r = topic_result(b)
    r["checks"] = [{"claims": moved["ids"], "reason": "测试记录：转来的句子待核"}]
    store.complete(w["id"], t["id"], t["lease_token"], r)
    w = store.get(w["id"])
    assert not sm.pending_referrals(w, "n2") and w["stage"] == "CONTENT_CONFIRMATION"


def test_the_draft_reports_planned_pages_against_the_estimate():
    w_pages = {"target": 1, "planned": 2, "estimated": 1, "over_estimate": [{"topic": "定义", "planned": 2, "estimated": 1}]}
    md = sm.draft_markdown({"one_liner": "一句话。", "topics": [], "pages": w_pages})
    assert "计划 2 页" in md and "要求 1 页" in md and "定义 2/1" in md


def test_a_stale_topic_pass_refers_nothing(store):
    """Referral ids from a pass made under an older cut or map may name other sentences: only current passes refer."""
    w = mapped(store)
    store.queue(w["id"], "TOPIC_PASS")
    t1 = store.claim(w["id"], "topic-1", "TOPIC_PASS", "n1")
    r1 = topic_result(t1["brief"])
    moved = next(x for x in r1["left_out"] if "ids" in x)
    moved.update(why="other_topic", topic="n2", note="测试记录：属于处理主题")
    store.complete(w["id"], t1["id"], t1["lease_token"], r1)
    with store.transaction(w["id"], "TEST_STALE") as ww:
        assert sm.referred_to(ww, "n2") == {moved["ids"][0]: "n1"}
        ww["topic_passes"]["n1"]["input_sha256"] = "stale"
        assert sm.referred_to(ww, "n2") == {}


def _all_passed(store):
    w = mapped(store)
    store.queue(w["id"], "TOPIC_PASS")
    while t := store.claim(w["id"], "topic-1", "TOPIC_PASS"):
        r = topic_result(t["brief"])
        if t["binding"] == "n1":                 # n1 also cites a sentence of n2 (borrowed)
            other = next(c for c in sm.claims(store.get(w["id"])).values() if c["topic"] == "n2" and c["kind"] == "sentence")
            r["messages"][0]["claims"].append(other["id"])
        store.complete(w["id"], t["id"], t["lease_token"], r)
    return store.get(w["id"]), other


def _recut(monkeypatch, sentence_id, text):
    """A new cutter under which `sentence_id` names other text (the units are unchanged)."""
    from factdeck import auto_claims
    real = auto_claims.cut
    monkeypatch.setattr(sm, "_CUTS", {})            # the cache trusts that one cutter version cuts one way
    monkeypatch.setattr(auto_claims, "SCHEMA", auto_claims.SCHEMA + "+recut")
    monkeypatch.setattr(auto_claims, "cut", lambda *a: [{**c, "quote": text} if c["id"] == sentence_id else c for c in real(*a)])


def test_a_reference_is_valid_only_while_its_text_is_unchanged(store, monkeypatch):
    """Ids are positions; references carry the text they were accepted on. Text that changes under an id is named;
    a new cutter that leaves a topic's sentences alone leaves its pass current."""
    w, other = _all_passed(store)
    assert all(sm.topic_current(w, n) for n in ("n1", "n2"))
    from factdeck import auto_claims
    monkeypatch.setattr(auto_claims, "SCHEMA", "auto_claims.test-recut")       # a recut giving the same sentences
    assert all(sm.topic_current(w, n) for n in ("n1", "n2"))
    _recut(monkeypatch, other["id"], "另一段完全不同的文字。")
    w = store.get(w["id"])
    assert other["id"] in sm.changed_references(w, "n1") and not sm.topic_current(w, "n1")
    assert w["stage"] == "TOPICS_REQUIRED" and any("原文已变化" in x for x in w["open_items"])


def test_an_exclusion_holds_only_for_the_text_the_customer_decided_on(store, monkeypatch):
    w = mapped(store)
    target = next(c for c in sm.claims(w).values() if c["kind"] == "sentence")
    w = store.settings(w["id"], {"exclusions": [{"id": "d1", "decision": "测试记录：这一句不用", "sentences": [target["id"]]}]})
    assert w["exclusions"][0]["anchors"] == {target["id"]: sm.anchor(target["quote"])}
    assert sm.claims(w)[target["id"]]["kind"] == "excluded"
    with pytest.raises(WorkflowError, match="不存在的句子"):
        store.settings(w["id"], {"exclusions": [{"id": "d2", "decision": "测试记录", "sentences": ["nowhere~1"]}]})
    _recut(monkeypatch, target["id"], "另一段完全不同的文字。")
    w = store.get(w["id"])
    assert sm.claims(w)[target["id"]]["kind"] != "excluded"                     # never applied to text not decided on
    assert w["stage"] == "EXCLUSIONS_CHANGED" and "d1" in w["open_items"][0]


def test_replay_names_accepted_work_that_a_code_change_would_misread(store, monkeypatch):
    """tools/replay.py re-accepts the archived results under the current code without writing anything: clean on
    unchanged code, and it names a referenced sentence whose text changed under its id."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("replay", Path(__file__).resolve().parents[1] / "tools" / "replay.py")
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)
    w, other = _all_passed(store)
    root = store.root
    report = replay.replay(root, w["id"])
    assert not replay.failed(report) and [t["status"] for t in report["topics"]] == ["OK", "OK"]
    _recut(monkeypatch, other["id"], "另一段完全不同的文字。")
    report = replay.replay(root, w["id"])
    n1 = next(t for t in report["topics"] if t["topic"] == "n1")
    assert replay.failed(report) and [x["id"] for x in n1["text_changed"]] == [other["id"]]
    assert "RESULT: FAIL" in replay.markdown(report)
    assert store.get(w["id"])["topic_passes"]["n1"]["result"] == w["topic_passes"]["n1"]["result"]   # nothing written
