"""Design features: emphasis, hero/timeline/grid, fact-driven charts, client brand.

Content is invented test data; templates and logos are generated for the test.
"""
import io
import re
import zipfile

import pytest
from PIL import Image

from app.deckflow import Store, WorkflowError
from deckkit import colorutil as CU
from factdeck import facts as fx
from factdeck.brand import from_template, BrandError
from factdeck.charts import chart_value, ChartError
from factdeck.deck import check
from factdeck.render import render, chart_geometry_errors
import test_deckflow as T

UNITS = [{"id": "U1", "source_id": "S01", "location": "第1段", "text": "研究甲纳入成人患者320例，主要终点缓解率为38%，安慰剂组为12%"},
         {"id": "U2", "source_id": "S02", "location": "第2段", "text": "研究乙纳入青少年患者96例，缓解率为29%"},
         {"id": "U3", "source_id": "S01", "location": "第3段", "text": "2019年启动入组；2021年完成主要终点分析；2023年公布长期随访结果"},
         {"id": "U4", "source_id": "S01", "location": "第4段", "text": "成人患病率约为12.5%，治疗12个月后约40~45%的患者达到缓解"}]


def facts():
    F = lambda i, u, q, d="": {"id": i, "unit": u, "quote": q, **({"display": d} if d else {})}
    raw = {"facts": [F("a.n", "U1", "研究甲"), F("a.v", "U1", "38%"), F("p.n", "U1", "安慰剂组"), F("p.v", "U1", "12%"),
                     F("b.n", "U2", "研究乙"), F("b.v", "U2", "29%"), F("a.pop", "U1", "纳入成人患者320例"),
                     F("t1", "U3", "2019年启动入组"), F("t2", "U3", "2021年完成主要终点分析"),
                     F("prev", "U4", "成人患病率约为12.5%", "约为12.5%"), F("prev.l", "U4", "成人患病率"),
                     F("range", "U4", "治疗12个月后约40~45%的患者达到缓解")]}
    Fs, D, Tm = fx.parse(raw)
    fx.verify(Fs, D, UNITS, {}, Tm)
    out = {f["id"]: f for f in fx.as_dict(Fs, D, [])["facts"]}
    assert all(f["status"] == "ACCEPTED" for f in out.values())
    return out


t = lambda s: {"text": s}
r = lambda i, **k: {"fact": i, **k}
BARS = [{"label": r("a.n"), "value": r("a.v")}, {"label": r("p.n"), "value": r("p.v")}]


def errors(page, fs=None):
    return check({"pages": [page]}, fs or facts())["pages"][0]["errors"]


# ------------------------------------------------------------------ emphasis
def test_emphasis_must_be_verbatim_fragments_in_order():
    page = lambda *e: {"id": "p", "layout": "bullets", "title": t("要点"), "items": [r("a.pop", emph=list(e))]}
    assert errors(page("320例")) == []
    assert errors(page("成人", "320例")) == []
    assert errors(page("320例", "成人"))                # out of order
    assert errors(page("300例"))                        # not in the text
    assert errors(page("纳入成人患者320"))               # emphasising most of the text
    assert errors(page(*["纳", "入", "成", "人"]))       # more than three fragments


# ------------------------------------------------------------------ layouts
def test_new_layout_structures():
    assert errors({"id": "h", "layout": "hero", "title": t("数"), "value": r("prev"), "label": r("prev.l")}) == []
    assert errors({"id": "h", "layout": "hero", "title": t("数"), "value": r("range")})        # too long for a hero value
    assert errors({"id": "l", "layout": "timeline", "title": t("进程"), "steps": [{"when": r("t1"), "what": r("a.pop")}, {"when": r("t2"), "what": r("a.v")}]}) == []
    assert errors({"id": "l", "layout": "timeline", "title": t("进程"), "steps": [{"when": r("t1")}, {"when": r("t2"), "what": r("a.v")}]})
    assert errors({"id": "g", "layout": "grid", "title": t("要点"), "tiles": [{"heading": t("甲"), "items": [r("a.v")]}, {"heading": t("乙"), "items": [r("b.v")]}]}) == []
    assert errors({"id": "g", "layout": "grid", "title": t("要点"), "tiles": [{"heading": t("甲"), "items": []}, {"heading": t("乙"), "items": [r("b.v")]}]})


# ------------------------------------------------------------------ charts
@pytest.mark.parametrize("text,value", [("38%", (38.0, "%")), ("约为12.5%", (12.5, "%")), ("1,204元", (1204.0, "元")), ("纳入320例", (320.0, "例"))])
def test_chart_values_are_read_from_fact_text(text, value):
    assert chart_value(text) == value


@pytest.mark.parametrize("text", ["40~45%", "≥150单位", "-5%", "38% vs 12%", "无数字"])
def test_chart_rejects_values_that_are_not_single_plain_numbers(text):
    with pytest.raises(ChartError):
        chart_value(text)


def test_chart_checks():
    page = lambda bars, **k: {"id": "c", "layout": "chart", "title": t("缓解率"), "chart": {"bars": bars, **k}}
    assert errors(page(BARS)) == []
    assert errors(page(BARS[:1]))                                                     # fewer than two bars
    assert errors(page([BARS[0], {"label": r("b.n"), "value": r("a.pop")}]))          # % vs 例
    assert errors(page([BARS[0], {"label": r("b.n"), "value": r("range")}]))          # range
    assert errors(page([BARS[0], {"label": r("b.n"), "value": t("29%")}]))            # typed value
    assert errors(page(BARS, orientation="diagonal"))
    fs = facts()
    res = check({"pages": [page([BARS[0], {"label": r("b.n"), "value": r("b.v")}])]}, fs)
    assert res["errors"] == 0 and any("2 份资料" in w for w in res["warnings"])


def test_chart_geometry_is_recomputed_from_facts():
    fs = facts()
    page = {"layout": "chart", "chart": {"bars": BARS}}
    ok = [{"fact": "a.v", "length": 38 / 40 * 300, "plot": 300}, {"fact": "p.v", "length": 12 / 40 * 300, "plot": 300}]
    assert chart_geometry_errors(page, fs, ok) == []
    wrong = [ok[0], {"fact": "p.v", "length": 20 / 40 * 300, "plot": 300}]
    assert chart_geometry_errors(page, fs, wrong)


def test_new_layouts_render_cleanly_and_export_natively(tmp_path):
    fs = facts()
    deck = {"title": "版式", "pages": [
        {"id": "hero", "layout": "hero", "title": t("患病情况"), "value": r("prev"), "label": r("prev.l")},
        {"id": "tl", "layout": "timeline", "title": t("研究进程"), "steps": [{"when": r("t1"), "what": r("a.pop", emph=["320例"])}, {"when": r("t2"), "what": r("a.v")}]},
        {"id": "grid", "layout": "grid", "title": t("要点"), "tiles": [{"heading": t("甲"), "items": [r("a.v")]}, {"heading": t("乙"), "items": [r("b.v")]}]},
        {"id": "cv", "layout": "chart", "title": t("缓解率"), "chart": {"bars": BARS}},
        {"id": "ch", "layout": "chart", "title": t("缓解率"), "chart": {"orientation": "horizontal", "bars": BARS}}]}
    rep = render(deck, fs, {"S01": {"title": "资料一"}, "S02": {"title": "资料二"}}, tmp_path)
    assert rep["hard_errors"] == 0, rep["summary"]
    from pptx import Presentation
    prs = Presentation(str(tmp_path / "deck.pptx"))
    runs = [run for sh in prs.slides[1].shapes if sh.has_text_frame for p in sh.text_frame.paragraphs for run in p.runs]
    assert any(run.text == "320例" and run.font.bold for run in runs)              # emphasis survives as a bold run
    assert any(run.text == "纳入成人患者" and not run.font.bold for run in runs)
    rects = [sh for sh in prs.slides[3].shapes if sh.shape_type == 1]
    tallest = max(rects, key=lambda sh: sh.height)
    bars = sorted((sh.height for sh in rects if abs(sh.width - tallest.width) < 2 and sh.top + sh.height == tallest.top + tallest.height), reverse=True)
    assert len(bars) == 2 and abs(bars[0] / bars[1] - 38 / 12) < 0.02          # native bars keep the ratio


# ------------------------------------------------------------------ brand
def template(accent1="C8102E", accent2="F2A900", font="BrandSans") -> bytes:
    from pptx import Presentation
    b = io.BytesIO()
    Presentation().save(b)
    src, out = zipfile.ZipFile(io.BytesIO(b.getvalue())), io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n in src.namelist():
            d = src.read(n)
            if re.match(r"ppt/theme/theme\d+\.xml$", n):
                x = d.decode("utf-8")
                x = re.sub(r'(<a:accent1><a:srgbClr val=")[0-9A-Fa-f]{6}', r"\g<1>" + accent1, x)
                x = re.sub(r'(<a:accent2><a:srgbClr val=")[0-9A-Fa-f]{6}', r"\g<1>" + accent2, x)
                x = re.sub(r'(<a:minorFont>.*?<a:font script="Hans" typeface=")[^"]*', r"\g<1>" + font, x, flags=re.S)
                d = x.encode("utf-8")
            z.writestr(n, d)
    return out.getvalue()


def test_brand_tokens_meet_contrast_even_for_pale_brand_colours():
    b = from_template(template(accent1="FFE066", accent2="B3E5FC"))
    k = b["tokens"]
    assert CU.contrast(k["primary"], "#FFFFFF") >= 7 and CU.contrast(k["accent"], "#FFFFFF") >= 4.5
    assert CU.contrast(k["accent-on-dark"], k["primary"]) >= 4.5 and CU.contrast(k["ink"], "#FFFFFF") >= 7
    assert b["template_colors"]["accent1"] == "#FFE066" and b["font"] == "BrandSans"
    with pytest.raises(BrandError):
        from_template(b"not a pptx")


def logo() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (300, 80), "#C8102E").save(buf, "PNG")
    return buf.getvalue()


def test_brand_in_workflow(tmp_path):
    s = Store(tmp_path / "brand")
    w = T.to_deck(s)
    w = T.finish_gates(s, w)
    with pytest.raises(WorkflowError):
        s.settings(w["id"], {"theme": "brand"})                                     # no template yet
    with pytest.raises(WorkflowError):
        s.brand_template(w["id"], "t.pdf", template())
    w = s.brand_template(w["id"], "客户模板.pptx", template())
    assert w["theme"] == "brand" and w["brand"]["tokens"]["primary"] and w["stage"] == "RENDER_REQUIRED"
    w = s.brand_logo(w["id"], "logo.png", logo())
    w = s.render(w["id"])
    r = w["render"]
    assert r["hard_errors"] == 0 and r["logo_file"] == "logo.png"
    assert any("BrandSans" in x for x in r["warnings"]["render"]) and r["font"] == "Microsoft YaHei"   # not installed → fallback
    before = r["input_sha256"]
    w = s.brand_logo(w["id"], "logo2.png", _other_logo())
    assert w["stage"] == "RENDER_REQUIRED"                                                  # new logo → re-render
    w = s.remove_brand(w["id"])
    assert w["theme"] == "navy-teal" and w["brand"] is None
    assert before


def _other_logo() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (300, 80), "#003366").save(buf, "PNG")
    return buf.getvalue()


def test_brand_endpoints(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app.deckflow_api as api
    from app.main import app
    monkeypatch.setattr(api, "store", Store(tmp_path / "api-brand"))
    c = TestClient(app)
    wid = c.post("/api/deck/workflows", json={"title": "品牌"}).json()["id"]
    assert c.post(f"/api/deck/workflows/{wid}/brand/logo", files={"file": ("l.png", logo())}).status_code == 409
    assert c.post(f"/api/deck/workflows/{wid}/brand/template", files={"file": ("t.pptx", b"junk")}).status_code == 422
    r = c.post(f"/api/deck/workflows/{wid}/brand/template", files={"file": ("t.pptx", template())})
    assert r.status_code == 200 and r.json()["theme"] == "brand"
    assert c.post(f"/api/deck/workflows/{wid}/brand/logo", files={"file": ("l.png", logo())}).status_code == 200
    assert c.get(f"/api/deck/workflows/{wid}/brand/logo").status_code == 200
    assert c.delete(f"/api/deck/workflows/{wid}/brand").json()["theme"] == "navy-teal"
