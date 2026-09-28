"""Source figures (docs/FIGURE_REFERENCE.md, phase 1: embedded pictures).

Pictures are generated test images and approvals/reviews are test records; they are
not real source figures, customer licences or medical/privacy review.
"""
import copy
import hashlib
import io

import pytest
from PIL import Image, ImageDraw

from app.deckflow import Store, WorkflowError, digest, verified, figures
from factdeck import facts as fx
from factdeck.deck import check as deck_check
from factdeck.ingest import extract_all
import factdeck_fixture as fx_
import test_deckflow as T


def picture(w=900, h=600, fmt="PNG") -> bytes:
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    m = min(w, h) // 8
    d.rectangle([m, m, w - m, h - m], outline="navy", width=4)
    d.line([m, h - m, w - m, m], fill="teal", width=4)
    buf = io.BytesIO()
    im.save(buf, fmt)
    return buf.getvalue()


def pdf_with_picture() -> bytes:
    buf = io.BytesIO()
    Image.open(io.BytesIO(picture())).convert("RGB").save(buf, "PDF")
    return buf.getvalue()


def pptx_with_picture() -> bytes:
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.shapes.add_picture(io.BytesIO(picture()), Inches(1), Inches(1))
    s.shapes.add_picture(io.BytesIO(picture(40, 40)), Inches(6), Inches(1))      # icon: not a figure
    s.shapes.add_textbox(Inches(1), Inches(5), Inches(4), Inches(1)).text_frame.text = "图1 示意（虚构）"
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def docx_with_picture() -> bytes:
    from docx import Document
    d = Document()
    d.add_paragraph("正文一段（虚构）")
    d.add_picture(io.BytesIO(picture(fmt="JPEG")))
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


# ------------------------------------------------------------------ ingest
@pytest.mark.parametrize("name,make,page", [("a.pdf", pdf_with_picture, "S01:p1"), ("b.pptx", pptx_with_picture, "S01:s1"),
                                            ("c.docx", docx_with_picture, "S01:d1"), ("d.png", picture, "S01:img")])
def test_embedded_pictures_are_registered_as_figures(name, make, page):
    pages, _, figs = extract_all(name, make(), "S01")
    assert [(f.id, f.page_id, f.width, f.height, f.method) for f in figs] == [(f"{page}:g1", page, 900, 600, "embedded")]
    assert next(p for p in pages if p.id == page).requires_visual
    assert Image.open(io.BytesIO(figs[0].png)).size == (900, 600)


def test_tiny_pictures_are_not_figures():
    assert extract_all("e.jpg", picture(80, 80, "JPEG"), "S01")[2] == []


def test_png_figure_keeps_pixels():
    raw = picture()
    fig = extract_all("d.png", raw, "S01")[2][0]
    assert Image.open(io.BytesIO(fig.png)).tobytes() == Image.open(io.BytesIO(raw)).tobytes()


# ------------------------------------------------------------------ fact gate / deck check
def gate(figure_state):
    units = [{"id": "U1", "source_id": "S01", "location": "第1页", "text": "图2 两组的累计发生率曲线"}]
    F, D, Tm = fx.parse({"facts": [{"id": "cap", "unit": "U1", "quote": "图2 两组的累计发生率曲线"},
                                   {"id": "fig", "figure": "S01:p1:g1", "caption": ["cap"]},
                                   {"id": "fig.quote", "figure": "S01:p1:g1", "unit": "U1", "quote": "图2"},
                                   {"id": "fig.badcap", "figure": "S01:p1:g1", "caption": ["nope"]},
                                   {"id": "fig.missing", "figure": "S09:p1:g1"},
                                   {"id": "text.cap", "unit": "U1", "quote": "图2", "caption": ["cap"]}]})
    fx.verify(F, D, units, {}, Tm, {"S01:p1:g1": {"source_id": "S01", "location": "第1页 图1", **figure_state}})
    return {f["id"]: f for f in fx.as_dict(F, D, [])["facts"]}


def test_figure_fact_gate():
    f = gate({"pending": [], "rejected": []})
    assert f["fig"]["status"] == "ACCEPTED" and not f["fig"]["needs_confirmation"] and f["fig"]["location"] == "第1页 图1"
    for bad in ("fig.quote", "fig.badcap", "fig.missing", "text.cap"):
        assert f[bad]["status"] == "REJECTED", bad
    f = gate({"pending": ["尚未登记图片使用许可"], "rejected": []})
    assert f["fig"]["status"] == "ACCEPTED" and f["fig"]["needs_confirmation"]
    f = gate({"pending": [], "rejected": ["图中含患者可识别信息，不能上页"]})
    assert f["fig"]["status"] == "REJECTED"


def test_figure_slot_holds_only_figure_facts():
    f = gate({"pending": [], "rejected": []})
    page = lambda **k: {"id": "p", "layout": "figure", "title": {"text": "原件图"}, **k}
    ok = deck_check({"pages": [page(figure={"fact": "fig"})]}, f)
    assert ok["errors"] == 0 and ok["pages"][0]["facts"] == ["cap", "fig"]
    assert deck_check({"pages": [page(figure={"fact": "cap"})]}, f)["errors"]
    wrong = {"id": "q", "layout": "bullets", "title": {"text": "要点"}, "items": [{"fact": "fig"}]}
    assert deck_check({"pages": [wrong]}, f)["errors"]


# ------------------------------------------------------------------ workflow
FIG = "S05:img:g1"


def read_with_figures(store, wid):
    store.queue(wid, "READ_SOURCE")
    while t := store.claim(wid, "reader-1", "READ_SOURCE"):
        result = copy.deepcopy(t["brief"]["result_contract"])
        for row in result["pages"]:
            row["visual_inspected"] = True
            if row["id"] == "S03:s1":
                row["transcription"] = [{"id": "c1", "location": "柱状图 研究甲标签", "text": "缓解率38%"}]
            for f in row["figures"]:
                f["note"] = "测试用线框图，一条对角线（虚构）"
            if row["id"] == "S05:img":
                row["transcription"] = [{"id": "g1c1", "location": "图中图例", "text": "A组", "figure": FIG}]
        store.complete(wid, t["id"], t["lease_token"], result)
    return store.get(wid)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "figures-data")


def to_figure_deck(store):
    w = store.create("原件图验收", T.OUTLINE, {"audience": "规培医生", "target_pages": 10})
    for name, make in fx_.SOURCES.items():
        store.add_source(w["id"], name, make())
    w = store.add_source(w["id"], "figure.png", picture())
    assert list(figures(w)) == [FIG]
    w = read_with_figures(store, w["id"])
    w = T.run_task(store, w["id"], "SUMMARY", "author-A", lambda t: T.summary(w))
    w = T.approve(store, w, "content")

    def facts(t):
        r = T.facts_result(w)
        r["facts"].append({"id": "fig.a", "figure": FIG, "caption": ["st.caveat"], "section_ids": ["s3"]})
        return r
    w = T.run_task(store, w["id"], "FACTS", "author-A", facts)
    assert verified(w)["facts"]["fig.a"]["needs_confirmation"]

    def deck(t):
        d = T.deck_result(w)
        d["pages"].insert(-1, {"id": "figure", "layout": "figure", "section": {"text": "证据"}, "title": {"text": "原件图"},
                               "figure": {"fact": "fig.a"}, "side": [{"fact": "st.a.v"}],
                               "outline_ids": [w["outline"][2]["id"]], "section_ids": ["s3"]})
        return d
    w = T.run_task(store, w["id"], "DECK", "author-A", deck)
    store.queue(w["id"], "SEMANTIC_REVIEW")
    t = store.claim(w["id"], "reviewer-B", "SEMANTIC_REVIEW")
    assert any(f.get("figure_url") for p in t["brief"]["pages"] for f in p["facts"])
    store.complete(w["id"], t["id"], t["lease_token"], t["brief"]["result_contract"])
    w = store.resolve_conflict(w["id"], {"reviewer": "TEST-REVIEWER", "entity": "药物A", "attribute": "单价(元)", "fact_id": "price.a.ppt"})
    store.queue(w["id"], "SECOND_READ")
    while t := store.claim(w["id"], "reader-2", "SECOND_READ"):
        cells = [{"unit_id": c["unit_id"], "text": {"S03:s1:x.c1": "缓解率38%", "S05:img:x.g1c1": "A组"}[c["unit_id"]]} for c in t["brief"]["cells"]]
        w = store.complete(w["id"], t["id"], t["lease_token"], {"source_sha256": t["brief"]["source"]["sha256"], "cells": cells})
    return w


def review(store, w, deid="NO_PATIENT_CONTENT"):
    return store.confirm_figure(w["id"], FIG, {"reviewer": "TEST-REVIEWER", "crop_complete": True, "deidentified": deid})


def licence(store, w, permitted=True):
    return store.license_figure(w["id"], FIG, {"customer": "TEST-CUSTOMER", "operator": "TEST-OPERATOR",
                                               "method": "AUTOMATED_PROTOCOL_TEST_NOT_REAL_LICENCE", "permitted": permitted})


def test_reading_must_describe_every_figure(store):
    w = store.create("图阅读", "条目")
    w = store.add_source(w["id"], "figure.png", picture())
    store.queue(w["id"], "READ_SOURCE")
    t = store.claim(w["id"], "reader-1", "READ_SOURCE")
    assert t["brief"]["pages"][0]["figures"][0]["url"].endswith(f"/figures/{FIG.replace('S05', 'S01')}/file")
    base = copy.deepcopy(t["brief"]["result_contract"])
    base["pages"][0]["visual_inspected"] = True
    for broken in ({"figures": []}, {"figures": [{"id": "S01:img:g1", "note": ""}]},
                   {"figures": [{"id": "S01:img:g1", "note": "线框图"}],
                    "transcription": [{"id": "x", "location": "图例", "text": "A", "figure": "S01:img:g9"}]}):
        r = copy.deepcopy(base)
        r["pages"][0].update(broken)
        with pytest.raises(WorkflowError):
            store.complete(w["id"], t["id"], t["lease_token"], r)


def test_figure_needs_review_and_licence_before_final_render(store):
    w = to_figure_deck(store)
    assert w["stage"] == "CONFIRMATIONS_REQUIRED", w["open_items"]
    pend = store.get(w["id"])
    from app.deckflow import pending_items, checked
    v = verified(pend)
    kinds = sorted(i["kind"] for i in pending_items(pend, v, checked(pend, v)))
    assert kinds == ["figure_licence", "figure_review"]
    with pytest.raises(WorkflowError, match="正式渲染前"):
        store.render(w["id"])
    with pytest.raises(WorkflowError, match="完整"):
        store.confirm_figure(w["id"], FIG, {"reviewer": "R", "crop_complete": False, "deidentified": "NO_PATIENT_CONTENT"})
    review(store, w)
    w = licence(store, w)
    assert w["stage"] == "RENDER_REQUIRED", w["open_items"]

    w = store.render(w["id"])
    r = w["render"]
    assert r["hard_errors"] == 0 and r["summary"]["figures"] == 1 and r["summary"]["pptx_missing_figures"] == 0
    from pptx import Presentation
    prs = Presentation(str(store.path(r["path"] + "/deck.pptx")))
    fig_sha = figures(w)[FIG]["sha256"]
    blobs = [hashlib.sha256(sh.image.blob).hexdigest() for s in prs.slides for sh in s.shapes if sh.shape_type == 13]
    assert fig_sha in blobs

    # changing the review makes the render stale; an identifiable picture is refused
    w = review(store, w, "IDENTIFIABLE")
    assert verified(w)["facts"]["fig.a"]["status"] == "REJECTED"
    assert w["stage"] == "DECK_REVISION"
    w = review(store, w, "DEIDENTIFIED")
    assert w["stage"] == "RENDER_REQUIRED"
    w = licence(store, w, permitted=False)
    assert w["stage"] == "DECK_REVISION"


def test_full_delivery_lists_figures(store):
    w = to_figure_deck(store)
    review(store, w)
    licence(store, w)
    w = store.render(w["id"])
    for p in w["render"]["pages"]:
        w = store.review(w["id"], p["id"], {"reviewer": "TEST-REVIEWER", "png_sha256": p["sha256"], "sources_checked": True,
                                            "visual_status": "PASS", "content_status": "PASS"})
        if p["id"] == w["render"]["pages"][4]["id"]:
            w = T.approve(store, w, "style")
    w = store.export(w["id"])
    assert w["stage"] == "DELIVERED"
    import json
    report = json.loads(store.path(w["deliveries"][-1]["path"] + "/verification_report.json").read_text(encoding="utf-8"))
    [item] = report["figures"]
    assert item["figure"] == FIG and item["review"]["deidentified"] == "NO_PATIENT_CONTENT" and item["licence"]["permitted"]


def test_tampered_figure_file_is_detected(store):
    w = to_figure_deck(store)
    review(store, w)
    licence(store, w)
    store.path(figures(store.get(w["id"]))[FIG]["path"]).write_bytes(picture(901, 600))
    with pytest.raises(WorkflowError, match="图文件"):
        review(store, w)
    with pytest.raises(ValueError, match="图文件已被修改"):
        store.render(w["id"])


def test_figure_endpoints(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app.deckflow_api as api
    from app.main import app
    monkeypatch.setattr(api, "store", Store(tmp_path / "api-fig"))
    c = TestClient(app)
    wid = c.post("/api/deck/workflows", json={"title": "图接口"}).json()["id"]
    assert c.post(f"/api/deck/workflows/{wid}/sources", files={"file": ("f.png", picture())}).status_code == 200
    r = c.get(f"/api/deck/workflows/{wid}/figures/S01:img:g1/file")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert c.get(f"/api/deck/workflows/{wid}/figures/S01:img:g9/file").status_code == 404
    bad = c.post(f"/api/deck/workflows/{wid}/confirmations/figures/S01:img:g1/review",
                 json={"reviewer": "R", "crop_complete": True, "deidentified": "MAYBE"})
    assert bad.status_code == 422
    ok = c.post(f"/api/deck/workflows/{wid}/confirmations/figures/S01:img:g1/licence",
                json={"customer": "C", "operator": "O", "method": "TEST", "permitted": True})
    assert ok.status_code == 200 and ok.json()["confirmations"]["figure_licenses"]["S01:img:g1"]["permitted"] is True
