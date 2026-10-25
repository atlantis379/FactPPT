"""Template-library mainline end to end (`generation_route: TEMPLATE_LIB`, the default since 2026-10-25):
sources → reading → summary → content approval → facts → DECK with template pages → semantic review →
confirmations → RENDER through factdeck/template_lib (native PPTX + trace report) → page review → style
approval → delivery.

Model outputs are hand-written fixtures and approvals are test records, not model evidence, customer sign-off or
medical review. Content is invented."""
from __future__ import annotations

import copy
import io
import json
import zipfile
from pathlib import Path

import pytest

from app.deckflow import Store, WorkflowError, TEMPLATE_ROUTE, stage, summary_key_points
import factdeck_fixture as fx_
from test_deckflow import (OUTLINE, approve, facts_result, finish_gates, read_all, run_task, summary,
                           with_key_points)

F = lambda i: {"fact": i}          # noqa: E731
T = lambda s: {"text": s}          # noqa: E731
META = ("id", "outline_ids", "section_ids", "point_ids", "key_point_ids", "focus")

# legacy page id → (template kind?, layout, fill); titles come from the legacy pages
FILLS = {
    "cover": ("cover", "cover", {"kicker": T("程序验收"), "subtitle": T("虚构资料，仅用于检查生成线")}),
    "part1": ("section", "section", {}),            # the section number is code-written
    "overview": (None, "key_points", {"section": T("概述"), "items": [
        {"heading": T("定义"), "body": F("x.def")}, {"heading": T("患病率"), "body": F("x.prev")},
        {"heading": T("诊断规则"), "body": F("dx.rule")}]}),
    "criteria": (None, "comparison", {"section": T("诊断"), "left_label": F("dx.a"), "right_label": F("dx.b"),
                                      "left_items": [{"text": F("dx.rule")}], "right_items": [{"text": F("dx.rule")}]}),
    "flow": (None, "flow", {"section": T("评估"), "nodes": [{"heading": F("flow.1")}, {"heading": F("flow.2")},
                                                           {"heading": F("flow.3")}],
                            "takeaway": F("risk")}),
    "drugs": (None, "comparison", {"section": T("治疗"), "left_label": F("tbl.a"), "right_label": F("tbl.b"),
                                   "rows": [{"left": F("tbl.a.t"), "right": F("tbl.b.t")},
                                            {"left": F("tbl.a.u"), "right": F("tbl.b.u")},
                                            {"left": F("price.a.ppt"), "right": F("price.b")},
                                            {"left": F("a.limit"), "right": F("b.dose")}]}),
    # two studies in different populations: the source says the rates must not be compared, so no chart
    "studies": (None, "comparison", {"section": T("证据"), "left_label": F("st.a"), "right_label": F("st.b"),
                                     "left_items": [{"text": F("st.a.l")}, {"text": F("st.a.v")}, {"text": F("st.a.pop")}],
                                     "right_items": [{"text": F("st.b.l")}, {"text": F("st.b.v")}, {"text": F("st.b.pop")}],
                                     "takeaway": F("st.caveat")}),
    "followup": (None, "key_points", {"section": T("随访"), "items": [{"heading": T("随访结果"), "body": F("fu")}],
                                      "takeaway": F("st.caveat")}),
    "end": (None, "key_points", {"items": [{"heading": T("诊断"), "body": F("dx.rule")},
                                           {"heading": T("用药限制"), "body": F("a.limit")}]}),
}


def template_deck(w):
    """The fixture deck rewritten as template pages: same ids, titles, outline / section / key point marks."""
    d = fx_.deck_spec([o["id"] for o in w["outline"]])
    pages = []
    for p in d["pages"]:
        kind, layout, fill = FILLS[p["id"]]
        t = {"layout": layout, "fill": copy.deepcopy(fill), **({"kind": kind} if kind else {})}
        pages.append({**{k: p[k] for k in META if k in p}, "layout": "template", "title": p["title"], "template": t})
    d["pages"] = pages
    d["facts_sha256"] = w["facts"]["result_sha256"]
    kp = summary_key_points(w)
    return with_key_points(d, [{"key_point_id": k} for k in kp]) if kp is not None else d


def to_template_deck(store):
    w = store.create("示例病X（模板库主线验收）", OUTLINE, {"audience": "规培医生", "target_pages": 9, "purpose": "程序验收"})
    assert w["generation_route"] == TEMPLATE_ROUTE                 # the default route
    with store.transaction(w["id"], "LEGACY_PROTOCOL_TEST_FIXTURE") as saved:
        saved.pop("source_evidence_policy", None)
    for name, make in fx_.SOURCES.items():
        store.add_source(w["id"], name, make())
    w = read_all(store, w["id"])
    w = run_task(store, w["id"], "SUMMARY", "author-A", lambda t: summary(w))
    w = approve(store, w, "content")
    w = run_task(store, w["id"], "FACTS", "author-A", lambda t: facts_result(w))
    return w


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "deckflow-data")


def test_deck_brief_teaches_template_pages(store):
    w = to_template_deck(store)
    store.queue(w["id"], "DECK")
    b = store.claim(w["id"], "author-A", "DECK")["brief"]
    assert set(b["layouts"]) == {"template"} and "recipes" not in b
    lib = b["template_library"]
    assert {"forest_plot", "key_points", "flow", "cover", "section"} <= set(lib)
    slots = lib["forest_plot"]["slots"]
    assert not any(k.lstrip("*").startswith(("refs", "title", "figure")) for k in slots)
    assert slots["*rows[≤13]"]["label"] == "*≤18" and slots["axis"] == "*object"
    assert lib["forest_plot"]["downgrades_to"] == "data_table_highlight"
    assert b["rules"][0].startswith("本项目走模板库主线")
    assert not any(r.startswith(("一页一个设计方案", "chart：")) for r in b["rules"])
    assert all(p["layout"] == "template" for p in b["result_contract"]["pages"])


def test_template_route_refuses_legacy_pages(store):
    from test_deckflow import deck_result
    w = to_template_deck(store)
    with pytest.raises(WorkflowError, match="模板库主线"):
        run_task(store, w["id"], "DECK", "author-A", lambda t: deck_result(store.get(w["id"])))


def test_template_mainline_to_delivery(store):
    pytest.importorskip("playwright")
    w = to_template_deck(store)
    w = run_task(store, w["id"], "DECK", "author-A", lambda t: template_deck(store.get(w["id"])))
    assert any(x.startswith("followup：要点卡片只有 1 条") for x in w["deck"]["warnings"])
    w = finish_gates(store, w)
    w = store.start_generation(w["id"])                    # `generate` on this route is the code render
    r = w["render"]
    assert r and r["route"] == TEMPLATE_ROUTE and r["hard_errors"] == 0, r and r["summary"]
    assert r["summary"]["pending_confirmation"] == 0 and r["summary"]["pictures"] == 0
    assert len(r["pages"]) == 9 and all(p["file"].startswith("slide") for p in r["pages"])
    folder = store.path(r["path"])
    rep = json.loads((folder / "render_report.json").read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in rep["slides"]}
    assert by_id["studies"]["layout"] == "comparison"       # not charted: the source says not comparable
    plan_fills = json.loads((folder / "template" / "job.json").read_text(encoding="utf-8"))["pages"]
    assert plan_fills[1]["fill"]["number"] == "1"                # section ordinal written by code
    assert rep["appearance"]["status"] in {"checked", "skipped"}
    trace = (folder / r["trace_report"]).read_text(encoding="utf-8")
    assert all(f"· {pid} ·" in trace for pid in FILLS) and "未溯源" not in trace
    assert r["stats"]["stage_seconds"] and "tokens" in r["stats"]
    assert w["stage"] == "SAMPLES_REVIEW"
    rec = lambda p: {"reviewer": "TEST-REVIEWER", "png_sha256": p["sha256"], "sources_checked": True,
                     "visual_status": "PASS", "content_status": "PASS"}
    for p in r["pages"][:5]:
        w = store.review(w["id"], p["id"], rec(p))
    assert w["stage"] == "STYLE_CONFIRMATION"
    w = approve(store, w, "style")
    for p in w["render"]["pages"][5:]:
        w = store.review(w["id"], p["id"], rec(p))
    assert w["stage"] == "READY_TO_EXPORT"
    (folder / "template" / "trace.md").write_text("篡改", encoding="utf-8")       # the trace is hash-bound
    with pytest.raises(WorkflowError, match="已被修改"):
        store.export(w["id"])
    (folder / "template" / "trace.md").write_text(trace, encoding="utf-8")
    w = store.export(w["id"])
    assert w["stage"] == "DELIVERED"
    d = w["deliveries"][-1]
    with zipfile.ZipFile(store.path(d["path"] + "/delivery.zip")) as z:
        names = z.namelist()
        assert {"deck.pptx", "deck.pdf", "facts_report.md", "verification_report.json", "trace.md", "trace.json"} <= set(names)
        assert "第 3 页 · overview" in z.read("trace.md").decode("utf-8")
        from pptx import Presentation
        prs = Presentation(io.BytesIO(z.read("deck.pptx")))
        assert len(prs.slides) == 9
        overview = prs.slides[2]
        shown = " ".join(sh.text_frame.text for sh in overview.shapes if sh.has_text_frame)
        assert "示例病X是一种用于程序验收的虚构疾病" in shown and "示例数据" not in shown
        notes = overview.notes_slide.notes_text_frame.text
        assert notes.startswith("【讲稿】") and "【溯源】x.def" in notes


def test_api_generation_renders_template_pages_and_serves_the_trace(tmp_path, monkeypatch):
    pytest.importorskip("playwright")
    from fastapi.testclient import TestClient
    import app.deckflow_api as api
    from app.main import app
    s = Store(tmp_path / "api-template")
    monkeypatch.setattr(api, "store", s)
    c = TestClient(app)
    assert c.get("/api/deck/health").json()["visual_generation"]["default_route"] == TEMPLATE_ROUTE
    w = to_template_deck(s)
    w = run_task(s, w["id"], "DECK", "author-A", lambda t: template_deck(s.get(w["id"])))
    w = finish_gates(s, w)
    r = c.post(f"/api/deck/workflows/{w['id']}/generation")        # the UI's “开始生成” on this route
    assert r.status_code == 200, r.text
    assert r.json()["render"]["route"] == TEMPLATE_ROUTE and not r.json().get("generation")
    md = c.get(f"/api/deck/workflows/{w['id']}/render/final/trace.md")
    assert md.status_code == 200 and "溯源报告" in md.text and "x.def" in md.text
    pptx = c.get(f"/api/deck/workflows/{w['id']}/render/final/deck.pptx")
    assert pptx.status_code == 200 and pptx.content[:2] == b"PK"
