"""Claims inventory (the evidence layer between reading and summary) and the independent summary review.

Content is invented; claims and reviews here are test records, not model evidence or real review.
"""
import copy

import pytest

from app.deckflow import Store, WorkflowError, stage
from factdeck.claims import cites, qualifiers
from factdeck.lexicon import locate
import factdeck_fixture as fx_
import test_deckflow as T
from test_outline_structure import OUTLINE, add_messages, structured_summary


def test_spans_are_located_in_the_raw_text_under_canon_matching():
    text = "在原有规范化使用中‑高剂量ICS‑LABA等基础上\n具有2型炎症特征的患者"
    a, b = locate(text, "等基础上 具有2型炎症")
    assert text[a:b] == "等基础上\n具有2型炎症"
    assert locate(text, "不存在的句子") is None
    assert cites("死亡风险更高¹") == ["1"]
    assert cites("机制¹⁻⁴，见¹⁰,¹¹") == ["1", "2", "3", "4", "10", "11"]
    assert {"可能", "约"} <= set(qualifiers("约30%的患者可能获益"))


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "claims-data")


def read_only(store, title="论断"):
    w = store.create(title, OUTLINE)
    for name, make in fx_.SOURCES.items():
        store.add_source(w["id"], name, make())
    store.queue(w["id"], "READ_SOURCE")
    while t := store.claim(w["id"], "reader-1", "READ_SOURCE"):
        r = copy.deepcopy(t["brief"]["result_contract"])
        for row in r["pages"]:
            row["visual_inspected"] = True
        store.complete(w["id"], t["id"], t["lease_token"], r)
    return store.get(w["id"])


def test_claims_are_required_before_the_summary(store):
    w = read_only(store)
    assert w["stage"] == "CLAIMS_REQUIRED"
    with pytest.raises(WorkflowError, match="论断清单"):
        store.queue(w["id"], "SUMMARY")
    w = T.claim_all(store, w["id"])
    assert w["stage"] == "SUMMARY_REQUIRED"


def test_claims_are_verbatim_spans_with_labels_checked_by_code(store):
    w = read_only(store)
    store.queue(w["id"], "CLAIMS")
    t = store.claim(w["id"], "claims-1", "CLAIMS")
    page = next(p for p in t["brief"]["pages"] if p["classification"] == "SUBSTANTIVE" and p["units"])
    other = next(p for p in t["brief"]["pages"] if p["id"] != page["id"] and p["units"])
    unit = page["units"][0]

    def submit(claim, profile=None, no_claims=""):
        r = copy.deepcopy(t["brief"]["result_contract"])
        for row, p in zip(r["pages"], t["brief"]["pages"]):
            row["claims"], row["no_claims"] = [], "测试：本页不列论断"
            if p["id"] == page["id"]:
                row["claims"], row["no_claims"] = ([claim] if claim else []), no_claims
        if profile:
            r["profile"] = profile
        store.complete(w["id"], t["id"], t["lease_token"], r)

    good = {"id": "k1", "type": "definition", "spans": [{"unit_id": unit["id"], "quote": unit["text"][:12]}], "scope": {}}
    with pytest.raises(WorkflowError, match="不是单元"):
        submit({**good, "spans": [{"unit_id": unit["id"], "quote": "资料里没有的一句话"}]})
    with pytest.raises(WorkflowError, match="本页的文字单元"):
        submit({**good, "spans": [{"unit_id": other["units"][0]["id"], "quote": other["units"][0]["text"][:6]}]})
    with pytest.raises(WorkflowError, match="不能引整页"):
        submit({**good, "spans": [{"unit_id": unit["id"], "quote": "甲" * 201}]})
    with pytest.raises(WorkflowError, match="类型"):
        submit({**good, "type": "opinion"})
    with pytest.raises(WorkflowError, match="scope.population"):
        submit({**good, "scope": {"population": "资料里没有的人群"}})
    with pytest.raises(WorkflowError, match="profile.kind"):
        submit(good, profile={"kind": "blog"})
    with pytest.raises(WorkflowError, match="no_claims"):
        submit(None)
    submit(good)
    w = store.get(w["id"])
    items = next(s for s in w["sources"] if s["id"] == page["id"].split(":")[0])["claims"]["items"]
    k = next(k for k in items if k["page_id"] == page["id"])
    assert k["id"] == page["id"] + "#k1" and k["spans"][0]["start"] == 0 and k["unit_ids"] == [unit["id"]]


def test_author_marks_left_out_of_the_claims_are_reported(store):
    from test_message_structure import _pptx
    w = store.create("标记", OUTLINE)
    w = store.add_source(w["id"], "m.pptx", _pptx())
    store.queue(w["id"], "READ_SOURCE")
    t = store.claim(w["id"], "reader-1", "READ_SOURCE")
    r = copy.deepcopy(t["brief"]["result_contract"])
    for row in r["pages"]:
        row["visual_inspected"] = True
    store.complete(w["id"], t["id"], t["lease_token"], r)
    w = T.claim_all(store, w["id"])                     # the fixture claims quote each unit's first 120 characters: all covered
    assert not [x for x in w["sources"][0]["claims"]["warnings"] if "未列入" in x]
    with store.transaction(w["id"], "TEST_DROP_CLAIMS") as ww:
        ww["sources"][0]["claims"] = None
    store.queue(w["id"], "CLAIMS")
    t = store.claim(w["id"], "claims-1", "CLAIMS")
    r = copy.deepcopy(t["brief"]["result_contract"])
    for row in r["pages"]:
        row["claims"], row["no_claims"] = [], "测试：不列论断"
    store.complete(w["id"], t["id"], t["lease_token"], r)
    warnings = store.get(w["id"])["sources"][0]["claims"]["warnings"]
    assert any("页标题“示例评估先于治疗”未列入" in x for x in warnings)
    assert any("强调“关键步骤不可省略”未列入" in x for x in warnings)


def _summarised(store):
    w = store.create("总结审查", OUTLINE)
    for name, make in fx_.SOURCES.items():
        store.add_source(w["id"], name, make())
    w = T.read_all(store, w["id"])
    w = T.run_task(store, w["id"], "SUMMARY", "author-A", lambda t: add_messages(w, structured_summary(w)))
    assert w["stage"] == "SUMMARY_REVIEW_REQUIRED"
    return w


def test_points_cite_claims_and_code_derives_units_and_unbacked_numbers(store):
    w = _summarised(store)
    row = w["summary"]["sections"][0]["point_coverage"][0]
    claims = {k["id"]: k for s in w["sources"] for k in s["claims"]["items"]}
    assert row["unit_ids"] == list(dict.fromkeys(u for c in row["claim_ids"] for u in claims[c]["unit_ids"]))
    assert isinstance(row["unmatched_tokens"], list)


def test_summary_review_is_independent_complete_and_gates_confirmation(store):
    w = _summarised(store)
    for worker, match in (("author-A", "总结作者"), ("claims-1", "论断清单作者")):
        store.queue(w["id"], "SUMMARY_REVIEW")
        t = store.claim(w["id"], worker, "SUMMARY_REVIEW")
        with pytest.raises(WorkflowError, match=match):
            store.complete(w["id"], t["id"], t["lease_token"], t["brief"]["result_contract"])
        store.fail(w["id"], t["id"], t["lease_token"], "测试：换审查人")
    store.queue(w["id"], "SUMMARY_REVIEW")
    t = store.claim(w["id"], "reviewer-S", "SUMMARY_REVIEW")
    assert t, "review task"
    r = copy.deepcopy(t["brief"]["result_contract"])
    assert r["sections"][0]["points"] and "core" in r["sections"][0]
    lazy = copy.deepcopy(r)
    lazy["sections"][0]["points"].pop()
    with pytest.raises(WorkflowError, match="逐条审查"):
        store.complete(w["id"], t["id"], t["lease_token"], lazy)
    silent = copy.deepcopy(r)
    silent["sections"][0]["points"][0]["verdict"] = "NOT_ENTAILED"
    with pytest.raises(WorkflowError, match="写明问题"):
        store.complete(w["id"], t["id"], t["lease_token"], silent)
    silent["sections"][0]["points"][0]["issue"] = "原文只说相关，要点写成了因果（测试）"
    silent["sections"][0]["points"][1]["verdict"] = "PARTIAL"
    silent["sections"][0]["points"][1]["issue"] = "缺少人群限定（测试）"
    w = store.complete(w["id"], t["id"], t["lease_token"], silent)
    assert w["stage"] == "SUMMARY_ISSUES"
    issues = w["summary_review"]["issues"]
    assert [i["severity"] for i in issues] == ["BLOCKER", "NOTE"]
    with pytest.raises(WorkflowError, match="阻断问题"):
        store.approval(w["id"], "content", {"customer": "C", "operator": "O", "method": "TEST", "subject_sha256": w["approval_subjects"]["content"]})
    w = store.dismiss_summary_issue(w["id"], issues[0]["id"], {"reviewer": "TEST-REVIEWER", "reason": "测试：人工核对后驳回"})
    assert w["stage"] == "CONTENT_CONFIRMATION"
    w = T.approve(store, w, "content")
    assert w["content_approval"]


def test_a_new_summary_needs_a_new_review(store):
    w = _summarised(store)
    w = T.review_summary(store, w["id"])
    assert w["stage"] == "CONTENT_CONFIRMATION"
    r = add_messages(w, structured_summary(w))
    r["overall_summary"] += "（修订）"
    w = store.author(w["id"], "SUMMARY", r, "测试编辑")
    assert w["stage"] == "SUMMARY_REVIEW_REQUIRED"


def test_confirmation_draft_shows_the_review(store, monkeypatch):
    from fastapi.testclient import TestClient
    import app.deckflow_api as api
    from app.main import app
    monkeypatch.setattr(api, "store", store)
    w = _summarised(store)
    text = TestClient(app).get(f"/api/deck/workflows/{w['id']}/confirmation-draft").text
    assert "当前总结尚未经独立审查" in text
    store.queue(w["id"], "SUMMARY_REVIEW")
    t = store.claim(w["id"], "reviewer-S", "SUMMARY_REVIEW")
    r = copy.deepcopy(t["brief"]["result_contract"])
    pid = r["sections"][0]["points"][0]["point_id"]
    r["sections"][0]["points"][0].update(verdict="NOT_ENTAILED", issue="原文只说相关（测试）")
    w = store.complete(w["id"], t["id"], t["lease_token"], r)
    store.dismiss_summary_issue(w["id"], w["summary_review"]["issues"][0]["id"], {"reviewer": "R", "reason": "测试驳回"})
    text = TestClient(app).get(f"/api/deck/workflows/{w['id']}/confirmation-draft").text
    assert "（审查：原文不支持）" in text and "审查意见：原文只说相关（测试）" in text
    assert f"阻断 {pid}：NOT_ENTAILED：原文只说相关（测试）（已驳回：测试驳回）" in text


def test_unbacked_tokens_ignore_citation_marks_line_breaks_and_unit_words():
    from app.deckflow import unbacked_tokens
    evidence = ["新可来治疗后\nFEV₁(LS均值) 显著*提高¹\n255.1 mL", "ACT≤19分", "1.53\n-64%"]
    assert unbacked_tokens("FEV1提高255.1 mL，ACT≤19，下降64%", evidence) == []
    assert unbacked_tokens("至少12个月", evidence) == ["12个月"]


def test_table_items_may_state_why_there_is_no_core_sentence(store):
    store2 = store
    w = store2.create("无核心句", OUTLINE)
    for name, make in fx_.SOURCES.items():
        store2.add_source(w["id"], name, make())
    w = T.read_all(store2, w["id"])
    r = add_messages(w, structured_summary(w))
    m = r["sections"][2]["message"]
    m["core"] = {"none": "测试：表格类内容"}
    with pytest.raises(WorkflowError, match="core.none"):
        store2.author(w["id"], "SUMMARY", r, "测试编辑")
    m["roles"] = {k: "support" for k in m["roles"]}
    w = store2.author(w["id"], "SUMMARY", r, "测试编辑")
    from app.deckflow import story_line
    assert "（无核心句：测试：表格类内容）" in story_line(w)[2]


def test_new_task_kinds_are_available_over_http(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app.deckflow_api as api
    from app.main import app
    store = Store(tmp_path / "http")
    monkeypatch.setattr(api, "store", store)
    w = read_only(store)
    res = TestClient(app).post(f"/api/deck/workflows/{w['id']}/tasks", json={"kind": "CLAIMS"})
    assert res.status_code == 200 and any(t["kind"] == "CLAIMS" for t in res.json()["tasks"])


def test_statement_says_what_the_sources_say_when_the_outline_goes_further(store, monkeypatch):
    from fastapi.testclient import TestClient
    import app.deckflow_api as api
    from app.main import app
    monkeypatch.setattr(api, "store", store)
    w = store.create("资料实际说", OUTLINE)
    for name, make in fx_.SOURCES.items():
        store.add_source(w["id"], name, make())
    w = T.read_all(store, w["id"])
    r = add_messages(w, structured_summary(w))
    row = r["sections"][0]["point_coverage"][0]
    row["statement"] = "资料只写了这一句（测试）"
    w = store.author(w["id"], "SUMMARY", r, "测试编辑")
    saved = w["summary"]["sections"][0]["point_coverage"][0]
    assert saved["statement"] == "资料只写了这一句（测试）" and "outline_unmatched_tokens" in saved
    text = TestClient(app).get(f"/api/deck/workflows/{w['id']}/confirmation-draft").text
    assert "**资料实际说**：资料只写了这一句（测试）" in text and "## 提纲措辞与资料不一致" in text
