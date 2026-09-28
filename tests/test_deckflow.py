"""FactDeck mainline: protocol and gate tests.

Model outputs here are hand-written fixtures and approvals are test records; they are
not model evidence, customer sign-off or medical review. Content is invented.
"""
import copy
import io
import zipfile

import pytest

from app.deckflow import Store, WorkflowError, digest, input_hash, stage, verified
import factdeck_fixture as fx_

OUTLINE = "认识示例病X\n评估与治疗\n研究证据"


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "deckflow-data")


def read_all(store, wid, worker="reader-1"):
    store.queue(wid, "READ_SOURCE")
    while True:
        t = store.claim(wid, worker, "READ_SOURCE")
        if not t:
            break
        result = copy.deepcopy(t["brief"]["result_contract"])
        for row in result["pages"]:
            row["visual_inspected"] = True
            if row["id"] == "S03:s1":              # a chart on the slide, transcribed by the reader
                row["transcription"] = [{"id": "c1", "location": "柱状图 研究甲标签", "text": "缓解率38%"}]
        store.complete(wid, t["id"], t["lease_token"], result)
    return store.get(wid)


def summary(w):
    ids = [p["id"] for s in w["sources"] for p in s["pages"]]
    return {"schema_version": "full_source_summary.v2", "input_sha256": input_hash(w),
            "overall_summary": "程序验收用的虚构资料总结：示例病X的定义与诊断、评估流程与药物、两项研究及其不可直接比较的限制。",
            "sections": [{"id": "s1", "title": "概述与诊断", "summary": "示例病X的定义、患病率与两项诊断指标的同时满足规则。", "source_page_ids": ids[:3]},
                         {"id": "s2", "title": "评估与治疗", "summary": "评估流程、高风险人群、药物靶点与用法以及用药限制。", "source_page_ids": ids[3:5]},
                         {"id": "s3", "title": "研究证据", "summary": "两项研究的人群与缓解率，以及随访结果和比较限制。", "source_page_ids": ids[5:]}],
            "outline_coverage": [{"outline_id": o["id"], "section_ids": [f"s{i}"]} for i, o in enumerate(w["outline"], 1)],
            "pending_issues": []}


def run_task(store, wid, kind, worker, make):
    store.queue(wid, kind)
    t = store.claim(wid, worker, kind)
    assert t, kind
    return store.complete(wid, t["id"], t["lease_token"], make(t))


def approve(store, w, kind):
    return store.approval(w["id"], kind, {"customer": "TEST-CUSTOMER", "operator": "TEST-OPERATOR",
                                          "method": "AUTOMATED_PROTOCOL_TEST_NOT_REAL_APPROVAL", "subject_sha256": w["approval_subjects"][kind]})


def facts_result(w):
    r = fx_.facts_proposal(fx_.UIDS)
    r["facts"].append({"id": "chart.a", "unit": "S03:s1:x.c1", "quote": "缓解率38%", "section_ids": ["s3"]})
    r["summary_sha256"] = digest(w["summary"])
    return r


def deck_result(w):
    d = fx_.deck_spec([o["id"] for o in w["outline"]])
    d["pages"][6]["panels"][0]["items"].append({"fact": "chart.a"})
    d["facts_sha256"] = w["facts"]["result_sha256"]
    return d


def to_deck(store):
    w = store.create("示例病X（程序验收）", OUTLINE, {"audience": "规培医生", "target_pages": 9, "purpose": "程序验收"})
    for name, make in fx_.SOURCES.items():
        store.add_source(w["id"], name, make())
    w = read_all(store, w["id"])
    assert stage(w) == "SUMMARY_REQUIRED"
    w = run_task(store, w["id"], "SUMMARY", "author-A", lambda t: summary(w))
    w = approve(store, w, "content")
    w = run_task(store, w["id"], "FACTS", "author-A", lambda t: facts_result(w))
    w = run_task(store, w["id"], "DECK", "author-A", lambda t: deck_result(w))
    return w


def test_sources_are_split_into_pages_and_quotable_units(store):
    w = store.create("拆分", "")
    for name, make in fx_.SOURCES.items():
        w = store.add_source(w["id"], name, make())
    assert [s["id"] for s in w["sources"]] == ["S01", "S02", "S03", "S04"]
    units = {u["id"]: u for s in w["sources"] for u in s["units"]}
    assert set(fx_.UIDS.values()) <= set(units)
    assert units["S03:s1:t1r2c2"]["location"] == "第1页 表格1 第2行第2列"
    assert all(p["requires_visual"] for p in w["sources"][2]["pages"])        # slides are always checked visually
    with pytest.raises(WorkflowError):
        store.add_source(w["id"], "again.txt", fx_.txt_source())
    with pytest.raises(WorkflowError):
        store.add_source(w["id"], "x.exe", b"MZ")


def test_reading_must_cover_every_page_and_inspect_visuals(store):
    w = store.create("阅读", "")
    w = store.add_source(w["id"], "studies.pptx", fx_.pptx_source())
    store.queue(w["id"], "READ_SOURCE")
    t = store.claim(w["id"], "reader-1")
    lazy = copy.deepcopy(t["brief"]["result_contract"])
    with pytest.raises(WorkflowError, match="视觉"):
        store.complete(w["id"], t["id"], t["lease_token"], lazy)
    lazy["pages"] = []
    with pytest.raises(WorkflowError, match="全部页面"):
        store.complete(w["id"], t["id"], t["lease_token"], lazy)


def test_fact_gate_runs_on_the_store(store):
    w = to_deck(store)
    v = verified(w)
    assert v["facts"]["bad.num"]["status"] == "REJECTED"
    assert v["facts"]["bad.neg"]["status"] == "REJECTED"
    assert v["facts"]["chart.a"]["needs_confirmation"]                          # transcription, no second read yet
    assert [c["key"] for c in v["conflicts"]] == ["药物A|单价(元)"]
    assert w["facts"]["rejected"] == 2


def test_deck_with_authored_claims_is_refused(store):
    w = to_deck(store)
    bad = deck_result(w)
    bad["pages"][2]["title"] = {"text": "药物A显著降低发作72%"}
    with pytest.raises(WorkflowError, match="作者文字"):
        store.author(w["id"], "DECK", bad, "editor")
    bad = deck_result(w)
    bad["pages"] = [p for p in bad["pages"] if w["outline"][2]["id"] not in (p.get("outline_ids") or [])]
    with pytest.raises(WorkflowError, match="提纲"):
        store.author(w["id"], "DECK", bad, "editor")


def test_semantic_review_must_be_independent_and_blocks_on_issues(store):
    w = to_deck(store)
    brief_pages = None

    def review(t, verdicts=None):
        nonlocal brief_pages
        r = copy.deepcopy(t["brief"]["result_contract"])
        brief_pages = t["brief"]["pages"]
        if verdicts:
            r["pages"][2] = {"page_id": r["pages"][2]["page_id"], "verdict": "ISSUES",
                             "issues": [{"severity": "BLOCKER", "ref": "x.prev", "problem": "节选未说明患病率的统计人群"}]}
        return r

    store.queue(w["id"], "SEMANTIC_REVIEW")
    t = store.claim(w["id"], "author-A", "SEMANTIC_REVIEW")
    with pytest.raises(WorkflowError, match="执行端"):
        store.complete(w["id"], t["id"], t["lease_token"], review(t))
    store.fail(w["id"], t["id"], t["lease_token"], "wrong worker")
    t = store.claim(w["id"], "reviewer-B", "SEMANTIC_REVIEW")
    w = store.complete(w["id"], t["id"], t["lease_token"], review(t, True))
    assert any(f["dropped_from_quote"] == "" for p in brief_pages for f in p["facts"])
    assert "语义审查有 1 个阻断问题" in " ".join(w["open_items"])
    w = store.dismiss_issue(w["id"], "overview#1", {"reviewer": "TEST-REVIEWER", "reason": "来源原文即为成人患病率，页面已写明成人"})
    assert "语义审查" not in " ".join(w["open_items"])


def finish_gates(store, w):
    store.queue(w["id"], "SEMANTIC_REVIEW")
    t = store.claim(w["id"], "reviewer-B", "SEMANTIC_REVIEW")
    w = store.complete(w["id"], t["id"], t["lease_token"], t["brief"]["result_contract"])
    assert w["stage"] == "CONFIRMATIONS_REQUIRED"
    with pytest.raises(WorkflowError, match="正式渲染前"):
        store.render(w["id"])
    w = store.resolve_conflict(w["id"], {"reviewer": "TEST-REVIEWER", "entity": "药物A", "attribute": "单价(元)", "fact_id": "price.a.ppt"})
    assert verified(w)["facts"]["price.a.xls"]["status"] == "REJECTED"
    # second, blind transcription by another worker
    store.queue(w["id"], "SECOND_READ")
    t = store.claim(w["id"], "reader-1", "SECOND_READ")
    assert "text" not in t["brief"]["cells"][0]
    with pytest.raises(WorkflowError, match="不同的执行端"):
        store.complete(w["id"], t["id"], t["lease_token"], {"source_sha256": t["brief"]["source"]["sha256"], "cells": [{"unit_id": "S03:s1:x.c1", "text": "缓解率38%"}]})
    store.fail(w["id"], t["id"], t["lease_token"], "same reader")
    t = store.claim(w["id"], "reader-2", "SECOND_READ")
    w = store.complete(w["id"], t["id"], t["lease_token"], {"source_sha256": t["brief"]["source"]["sha256"], "cells": [{"unit_id": "S03:s1:x.c1", "text": "缓解率 38%"}]})
    assert not verified(w)["facts"]["chart.a"]["needs_confirmation"]
    assert w["stage"] == "RENDER_REQUIRED", w["open_items"]
    return w


def test_full_mainline_to_delivery(store):
    pytest.importorskip("playwright")
    w = finish_gates(store, to_deck(store))
    w = store.render(w["id"])
    assert w["render"]["hard_errors"] == 0, w["render"]["summary"]
    assert w["render"]["summary"]["pending_confirmation"] == 0
    assert w["stage"] == "SAMPLES_REVIEW"
    rec = lambda p: {"reviewer": "TEST-REVIEWER", "png_sha256": p["sha256"], "sources_checked": True, "visual_status": "PASS", "content_status": "PASS"}
    for p in w["render"]["pages"][:5]:
        w = store.review(w["id"], p["id"], rec(p))
    assert w["stage"] == "STYLE_CONFIRMATION"
    w = approve(store, w, "style")
    for p in w["render"]["pages"][5:]:
        w = store.review(w["id"], p["id"], rec(p))
    assert w["stage"] == "READY_TO_EXPORT"
    w = store.export(w["id"])
    assert w["stage"] == "DELIVERED"
    d = w["deliveries"][-1]
    with zipfile.ZipFile(store.path(d["path"] + "/delivery.zip")) as z:
        names = z.namelist()
        assert {"deck.pptx", "deck.pdf", "facts_report.md", "verification_report.json"} <= set(names)
        from pptx import Presentation
        prs = Presentation(io.BytesIO(z.read("deck.pptx")))
        assert len(prs.slides) == 9
        notes = prs.slides[2].notes_slide.notes_text_frame.text
        assert "来源追溯" in notes and "overview.txt" in notes
    # changing the requirements makes the deck, review and delivery stale
    w = store.settings(w["id"], {"requirements": {"audience": "护士", "target_pages": 12}})
    assert w["stage"] == "DECK_REQUIRED"


def test_draft_render_is_not_reviewable(store):
    pytest.importorskip("playwright")
    w = to_deck(store)
    w = store.render(w["id"], draft=True)
    assert w["draft_render"]["summary"]["pending_confirmation"] > 0
    assert w["render"] is None
    p = w["draft_render"]["pages"][0]
    with pytest.raises(WorkflowError, match="正式渲染"):
        store.review(w["id"], p["id"], {"reviewer": "R", "png_sha256": p["sha256"], "sources_checked": True, "visual_status": "PASS", "content_status": "PASS"})


def test_changing_sources_invalidates_everything_downstream(store):
    w = to_deck(store)
    w = store.add_source(w["id"], "extra.md", "# 追加\n\n追加的虚构资料。".encode())
    assert w["stage"] == "READING_REQUIRED"
    assert all(t["status"] != "PENDING" or t["kind"] == "READ_SOURCE" for t in w["tasks"])


def test_api_routes_are_mounted(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app.deckflow_api as api
    from app.main import app
    monkeypatch.setattr(api, "store", Store(tmp_path / "api-data"))
    c = TestClient(app)
    assert c.get("/api/deck/health").json()["mainline"] is True
    r = c.post("/api/deck/workflows", json={"title": "接口", "outline": "条目", "requirements": {"target_pages": 5, "audience": "学生"}})
    assert r.status_code == 201
    wid = r.json()["id"]
    r = c.post(f"/api/deck/workflows/{wid}/sources", files={"file": ("a.docx", fx_.docx_source())})
    assert r.status_code == 200 and r.json()["sources"][0]["id"] == "S01"
    assert c.post(f"/api/deck/workflows/{wid}/tasks", json={"kind": "FACTS"}).status_code == 409
    assert c.post("/api/deck/workflows", json={"title": "x", "requirements": {"bogus": 1}}).status_code == 422
    assert c.post("/api/deck/workflows", json={"title": "x", "theme": "neon"}).status_code == 422


def test_home_serves_the_tabler_ui_and_its_assets():
    import re
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    home = c.get("/")
    assert home.status_code == 200 and "FactDeck" in home.text
    assets = re.findall(r'(?:href|src)="(/web/[^"]+)"', home.text)
    assert "/web/vendor/tabler/tabler.min.css" in assets and "/web/deck/app.js" in assets
    for path in assets:
        assert c.get(path).status_code == 200, path


def test_render_endpoint_runs_inside_the_server(tmp_path, monkeypatch):
    pytest.importorskip("playwright")
    from fastapi.testclient import TestClient
    import app.deckflow_api as api
    from app.main import app
    s = Store(tmp_path / "api-render")
    monkeypatch.setattr(api, "store", s)
    w = to_deck(s)
    c = TestClient(app)
    r = c.post(f"/api/deck/workflows/{w['id']}/render", params={"draft": "true"})
    assert r.status_code == 200, r.text
    first = r.json()["draft_render"]["pages"][0]["file"]
    png = c.get(f"/api/deck/workflows/{w['id']}/render/draft/{first}")
    assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
    assert c.get(f"/api/deck/workflows/{w['id']}/render/draft/..%2Fsecret").status_code == 404
