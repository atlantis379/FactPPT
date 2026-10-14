"""Source figures phase 2 (docs/FIGURE_REFERENCE.md): PDF page crops and figures in compare panels.

The PDF is a generated vector drawing and all reviews/licences are test records; they are
not real source figures, customer licences or medical/privacy review.
"""
import copy
import hashlib
import io

import pytest
from PIL import Image

from app.deckflow import Store, WorkflowError, verified, figures, figure_states, pending_items, checked
from factdeck.deck import check as deck_check
from factdeck.ingest import IngestError, check_bbox, crop_pdf_page, iou, extract_all
import factdeck_fixture as fx_
import test_deckflow as T
from test_figures import picture, FIG, review, licence

BOX = [0.1, 0.2, 0.9, 0.6]
CROP = "S06:p1:c1"


def vector_chart_pdf() -> bytes:
    """One A4 page: a caption line and a bar chart drawn with vector strokes (no embedded picture)."""
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.text(25, 50, "Figure 2 Response rate by group (fictional)")
    pdf.line(30, 160, 180, 160)                     # axis
    pdf.line(30, 70, 30, 160)
    for i, h in enumerate((60, 35, 80)):
        pdf.rect(45 + i * 45, 160 - h, 25, h, style="F")
    pdf.text(30, 170, "A        B        C")
    pdf.text(25, 230, "Body text below the chart (fictional).")
    return bytes(pdf.output())


# ------------------------------------------------------------------ primitives
def test_bbox_rules():
    assert check_bbox([0, 0, 1, 1]) == [0, 0, 1, 1]
    for bad in ([0, 0, 1], [0.5, 0, 0.4, 1], [0, 0, 1.2, 1], [0, 0, 0.02, 1], "0,0,1,1", [0, 0, True, 1]):
        with pytest.raises(IngestError):
            check_bbox(bad)
    assert iou(BOX, BOX) == 1.0 and iou([0, 0, 0.5, 0.5], [0.5, 0.5, 1, 1]) == 0.0
    assert 0.9 < iou(BOX, [0.1, 0.2, 0.9, 0.63]) < 1


def test_crop_is_code_rendered_and_deterministic():
    pdf = vector_chart_pdf()
    assert extract_all("c.pdf", pdf, "S01")[2] == []                  # vector drawing: no embedded figure
    a, w, h = crop_pdf_page(pdf, 1, BOX)
    assert a == crop_pdf_page(pdf, 1, BOX)[0]
    assert (w, h) == Image.open(io.BytesIO(a)).size and abs(w - 0.8 * 1654) <= 2 and abs(h - 0.4 * 2339) <= 2
    im = Image.open(io.BytesIO(a)).convert("L")
    assert im.getextrema()[0] < 60                                      # the bars are in the crop
    with pytest.raises(IngestError):
        crop_pdf_page(pdf, 2, BOX)


# ------------------------------------------------------------------ reading / second read
@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "crops-data")


def claim_read(store, wid):
    store.queue(wid, "READ_SOURCE")
    t = store.claim(wid, "reader-1", "READ_SOURCE")
    r = copy.deepcopy(t["brief"]["result_contract"])
    for row in r["pages"]:
        row["visual_inspected"] = True
    return t, r


def test_reader_boxes_become_code_cut_figures(store):
    w = store.create("截取", "条目")
    w = store.add_source(w["id"], "chart.pdf", vector_chart_pdf())
    t, base = claim_read(store, w["id"])
    page = t["brief"]["pages"][0]
    assert page["page_image_url"].endswith("/sources/S01/pages/S01:p1/image") and base["pages"][0]["crops"] == []
    assert any("crops" in rule for rule in t["brief"]["rules"])
    for broken in ([{"id": "c1", "bbox": [0.1, 0.2, 0.9], "note": "柱状图（虚构）"}],
                   [{"id": "x1", "bbox": BOX, "note": "柱状图（虚构）"}],
                   [{"id": "c1", "bbox": BOX, "note": ""}],
                   [{"id": "c1", "bbox": BOX, "note": "柱状图（虚构）", "caption_unit_ids": ["S09:p1"]}],
                   [{"id": "c1", "bbox": BOX, "note": "柱状图（虚构）"}, {"id": "c1", "bbox": BOX, "note": "柱状图（虚构）"}]):
        r = copy.deepcopy(base)
        r["pages"][0]["crops"] = broken
        with pytest.raises(WorkflowError):
            store.complete(w["id"], t["id"], t["lease_token"], r)
    r = copy.deepcopy(base)
    r["pages"][0]["crops"] = [{"id": "c1", "bbox": BOX, "note": "三组柱状图（虚构）", "caption_unit_ids": ["S01:p1"]}]
    r["pages"][0]["transcription"] = [{"id": "c1c1", "location": "图中横轴", "text": "A B C", "figure": "S01:p1:c1"}]
    w = store.complete(w["id"], t["id"], t["lease_token"], r)
    g = figures(w)["S01:p1:c1"]
    assert (g["method"], g["bbox"], g["dpi"], g["reader"]) == ("page_crop", BOX, 200, "reader-1")
    data = store.path(g["path"]).read_bytes()
    assert data == crop_pdf_page(vector_chart_pdf(), 1, BOX)[0] and hashlib.sha256(data).hexdigest() == g["sha256"]
    assert w["sources"][0]["pages"][0]["reading"]["figures"]["S01:p1:c1"]["bbox"] == BOX
    assert "截取区域尚无第二次独立截取" in figure_states(w)["S01:p1:c1"]["pending"]

    # the second read gets no first box, must come from someone else, and must box every crop
    store.queue(w["id"], "SECOND_READ")
    t2 = store.claim(w["id"], "reader-2", "SECOND_READ")
    assert "bbox" not in str(t2["brief"]["crops"]) and t2["brief"]["crops"][0]["description"] == "三组柱状图（虚构）"
    assert [c["unit_id"] for c in t2["brief"]["cells"]] == ["S01:p1:x.c1c1"]


def second_read(store, wid, box, cells=True):
    store.queue(wid, "SECOND_READ")
    t = store.claim(wid, "reader-2", "SECOND_READ")
    r = copy.deepcopy(t["brief"]["result_contract"])
    for c in r["cells"]:
        c["text"] = "A B C"
    for c in r["crops"]:
        c["bbox"] = box
    return t, r


def read_one_crop(store):
    w = store.create("截取复核", "条目")
    store.add_source(w["id"], "chart.pdf", vector_chart_pdf())
    t, r = claim_read(store, w["id"])
    r["pages"][0]["crops"] = [{"id": "c1", "bbox": BOX, "note": "三组柱状图（虚构）"}]
    return store.complete(w["id"], t["id"], t["lease_token"], r)


def test_second_box_agrees_or_sends_the_crop_to_a_person(store, tmp_path):
    w = read_one_crop(store)
    fig = "S01:p1:c1"
    t, r = second_read(store, w["id"], BOX)
    assert t["brief"]["crops"][0]["figure_id"] == fig and not t["brief"]["cells"]        # queued for the crop alone
    with pytest.raises(WorkflowError, match="逐张"):
        store.complete(w["id"], t["id"], t["lease_token"], {**r, "crops": []})
    w = store.complete(w["id"], t["id"], t["lease_token"], {**r, "crops": [{"figure_id": fig, "bbox": [0.1, 0.2, 0.9, 0.62]}]})
    g = figures(w)[fig]
    assert g["second_read"]["agree"] and g["second_read"]["iou"] >= 0.9
    assert not any("截取区域" in x for x in figure_states(w)[fig]["pending"])

    # a second box that differs sends the crop to a person, who must say why the first box is complete
    other = Store(tmp_path / "other")
    w2 = read_one_crop(other)
    t, r = second_read(other, w2["id"], [0.1, 0.2, 0.6, 0.6])
    w2 = other.complete(w2["id"], t["id"], t["lease_token"], r)
    g = figures(w2)[fig]
    assert not g["second_read"]["agree"] and g["second_read"]["iou"] < 0.9
    with pytest.raises(WorkflowError, match="交并比"):
        other.confirm_figure(w2["id"], fig, {"reviewer": "R", "crop_complete": True, "deidentified": "NO_PATIENT_CONTENT"})
    w2 = other.confirm_figure(w2["id"], fig, {"reviewer": "R", "crop_complete": True, "deidentified": "NO_PATIENT_CONTENT",
                                              "note": "对照原页：第二次框漏掉右侧柱，现有截取完整（测试记录）"})
    assert w2["confirmations"]["figures"][fig]["mismatch_checked"] == [0.1, 0.2, 0.6, 0.6]
    assert not any("不一致" in x for x in figure_states(w2)[fig]["pending"])


def test_second_reader_must_differ_and_non_pdf_cannot_crop(store):
    w = read_one_crop(store)
    store.queue(w["id"], "SECOND_READ")
    t = store.claim(w["id"], "reader-1", "SECOND_READ")
    r = copy.deepcopy(t["brief"]["result_contract"])
    with pytest.raises(WorkflowError, match="不同的执行端"):
        store.complete(w["id"], t["id"], t["lease_token"], r)

    w = store.create("图片资料", "条目")
    store.add_source(w["id"], "figure.png", picture())
    t, r = claim_read(store, w["id"])
    assert "crops" not in r["pages"][0] and "page_image_url" not in t["brief"]["pages"][0]
    r["pages"][0]["figures"][0]["note"] = "线框图（虚构）"
    r["pages"][0]["crops"] = [{"id": "c1", "bbox": BOX, "note": "线框图（虚构）"}]
    with pytest.raises(WorkflowError, match="只有PDF"):
        store.complete(w["id"], t["id"], t["lease_token"], r)


def test_page_image_endpoint(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app.deckflow_api as api
    from app.main import app
    monkeypatch.setattr(api, "store", Store(tmp_path / "api-crop"))
    c = TestClient(app)
    wid = c.post("/api/deck/workflows", json={"title": "整页图"}).json()["id"]
    c.post(f"/api/deck/workflows/{wid}/sources", files={"file": ("c.pdf", vector_chart_pdf())})
    c.post(f"/api/deck/workflows/{wid}/sources", files={"file": ("f.png", picture())})
    r = c.get(f"/api/deck/workflows/{wid}/sources/S01/pages/S01:p1/image")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(r.content)).size[0] > 800
    assert c.get(f"/api/deck/workflows/{wid}/sources/S02/pages/S02:img/image").status_code == 404
    assert c.get(f"/api/deck/workflows/{wid}/sources/S01/pages/S01:p9/image").status_code == 404


# ------------------------------------------------------------------ compare panels
def test_compare_panel_figure_rules():
    facts = {"a": {"figure": "F1", "status": "ACCEPTED", "needs_confirmation": False, "caption": [], "problems": []},
             "b": {"figure": "F2", "status": "ACCEPTED", "needs_confirmation": False, "caption": [], "problems": []},
             "c": {"figure": "F3", "status": "ACCEPTED", "needs_confirmation": False, "caption": [], "problems": []},
             "t": {"status": "ACCEPTED", "needs_confirmation": False, "quote": "文字", "display": "", "problems": []}}
    page = lambda panels: {"pages": [{"id": "p", "layout": "compare", "title": {"text": "对照"}, "panels": panels}]}
    ok = deck_check(page([{"heading": {"text": "甲"}, "figure": {"fact": "a"}}, {"heading": {"text": "乙"}, "figure": {"fact": "b"}}]), facts)
    assert ok["errors"] == 0 and any("并排" in x for x in ok["warnings"])
    three = deck_check(page([{"heading": {"text": k}, "figure": {"fact": k}} for k in "abc"]), facts)
    assert any("至多" in e for e in three["pages"][0]["errors"])
    mixed = deck_check(page([{"heading": {"text": "甲"}, "figure": {"fact": "a"}, "items": [{"fact": "t"}]},
                             {"heading": {"text": "乙"}, "items": [{"fact": "t"}]}]), facts)
    assert any("放图时" in e for e in mixed["pages"][0]["errors"])
    wrong = deck_check(page([{"heading": {"text": "甲"}, "items": [{"fact": "a"}]}, {"heading": {"text": "乙"}, "items": [{"fact": "t"}]}]), facts)
    assert any("图位置" in e for e in wrong["pages"][0]["errors"])


def test_crop_and_embedded_figure_side_by_side_to_final_render(store):
    w = store.create("并排原件图", T.OUTLINE, {"audience": "规培医生", "target_pages": 10}, generation_route="CODE_NATIVE")
    # Same retained legacy order as test_deckflow.to_deck: facts/deck before second read.
    with store.transaction(w["id"], "LEGACY_PROTOCOL_TEST_FIXTURE") as saved:
        saved.pop("source_evidence_policy", None)
    for name, make in fx_.SOURCES.items():
        store.add_source(w["id"], name, make())
    store.add_source(w["id"], "figure.png", picture())
    w = store.add_source(w["id"], "chart.pdf", vector_chart_pdf())
    store.queue(w["id"], "READ_SOURCE")
    while t := store.claim(w["id"], "reader-1", "READ_SOURCE"):
        r = copy.deepcopy(t["brief"]["result_contract"])
        for row in r["pages"]:
            row["visual_inspected"] = True
            if row["id"] == "S03:s1":
                row["transcription"] = [{"id": "c1", "location": "柱状图 研究甲标签", "text": "缓解率38%"}]
            for f in row["figures"]:
                f["note"] = "测试用线框图，一条对角线（虚构）"
            if row["id"] == "S05:img":
                row["note"] = "整幅线框图，无文字（虚构）"
            if row["id"] == "S06:p1":
                row["crops"] = [{"id": "c1", "bbox": BOX, "note": "三组柱状图（虚构）"}]
        store.complete(w["id"], t["id"], t["lease_token"], r)
    w = T.claim_all(store, w["id"])
    assert sorted(figures(w)) == [FIG, CROP]
    w = T.run_task(store, w["id"], "SUMMARY", "author-A", lambda t: T.summary(w))
    w = T.approve(store, w, "content")

    def facts(t):
        r = T.facts_result(w)
        r["facts"] += [{"id": "fig.a", "figure": FIG, "section_ids": ["s3"]},
                       {"id": "fig.b", "figure": CROP, "section_ids": ["s3"]}]
        return r
    w = T.run_task(store, w["id"], "FACTS", "author-A", facts)

    def deck(t):
        d = T.deck_result(w)
        d["pages"].insert(-1, {"id": "figs", "layout": "compare", "title": {"text": "原件图"},
                               "panels": [{"heading": {"text": "图一"}, "figure": {"fact": "fig.a"}},
                                          {"heading": {"text": "图二"}, "figure": {"fact": "fig.b"}}],
                               "outline_ids": [w["outline"][2]["id"]], "section_ids": ["s3"]})
        return d
    w = T.run_task(store, w["id"], "DECK", "author-A", deck)
    v = verified(w)
    kinds = sorted(i["kind"] for i in pending_items(w, v, checked(w, v)) if i["id"] == CROP)
    assert kinds == ["figure_licence", "figure_review", "figure_second_crop"]
    T.semantic_review(store, w["id"])
    store.resolve_conflict(w["id"], {"reviewer": "TEST-REVIEWER", "entity": "药物A", "attribute": "单价(元)", "fact_id": "price.a.ppt"})
    store.queue(w["id"], "SECOND_READ")
    while t := store.claim(w["id"], "reader-2", "SECOND_READ"):
        r = copy.deepcopy(t["brief"]["result_contract"])
        for c in r["cells"]:
            c["text"] = {"S03:s1:x.c1": "缓解率38%"}[c["unit_id"]]
        for c in r["crops"]:
            c["bbox"] = BOX
        w = store.complete(w["id"], t["id"], t["lease_token"], r)
    for fig in (FIG, CROP):
        store.confirm_figure(w["id"], fig, {"reviewer": "TEST-REVIEWER", "crop_complete": True, "deidentified": "NO_PATIENT_CONTENT"})
        w = store.license_figure(w["id"], fig, {"customer": "TEST-CUSTOMER", "operator": "TEST-OPERATOR",
                                                "method": "AUTOMATED_PROTOCOL_TEST_NOT_REAL_LICENCE", "permitted": True})
    assert w["stage"] == "RENDER_REQUIRED", w["open_items"]
    w = store.render(w["id"])
    r = w["render"]
    assert r["hard_errors"] == 0 and r["summary"]["figures"] == 2 and r["summary"]["pptx_missing_figures"] == 0, r["summary"]
    from pptx import Presentation
    prs = Presentation(str(store.path(r["path"] + "/deck.pptx")))
    slide = prs.slides[[p["id"] for p in r["pages"]].index("figs")]
    blobs = {hashlib.sha256(sh.image.blob).hexdigest() for sh in slide.shapes if sh.shape_type == 13}
    assert {figures(w)[FIG]["sha256"], figures(w)[CROP]["sha256"]} <= blobs
