"""designed.v1 — a generator designs the page freely; what the page states is not up to it.

The facts here are about a gearbox on purpose.  Nothing in this pipeline may know a subject, so a rule that only
works on clinical sentences fails here.  Every test is an error a generator could make.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from factdeck import assets as A
from factdeck import designed as D


def fact(quote: str, **kw) -> dict:
    return {"quote": quote, "display": "", "status": "ACCEPTED", "needs_confirmation": False, "source_id": "手册", "location": "第 3 页", **kw}


FACTS = {
    "no": fact("该型号不建议在高温环境下连续运行。"),
    "over": fact("超过70%的故障来自润滑不足。"),
    "a": fact("其寿命为8000小时。"),
    "b": fact("其寿命为2000小时。"),
    "chain": fact("润滑不足导致轴承磨损。"),
    "lub": fact("润滑不足"),
    "wear": fact("轴承磨损"),
    "other": fact("外壳由铝合金制成。"),
    "gear": fact("齿轮箱内部包含行星齿轮。"),
}
STYLE = A.styles()["clinical_blue"]
BOX = "position:absolute;left:64px;width:900px"


def text(fid, show=None, tier="body", top=200, id_=None, size=22) -> str:
    extra = f' data-show="{show}"' if show else ""
    i = f' id="{id_}"' if id_ else ""
    return (f'<div data-t data-tier="{tier}"{i} style="{BOX};top:{top}px;font-size:{size}px;line-height:1.4">'
            f'<span data-fact="{fid}"{extra}></span></div>')


def label(words: str, top=60) -> str:
    return (f'<div data-t data-tier="title" style="{BOX};top:{top}px;font-size:44px;line-height:1.3;font-weight:700">'
            f'<span data-text>{words}</span></div>')


def page(html: str, **kw) -> dict:
    return {"id": "p1", "html": html, **kw}


def errors(p, assets=None, confirmed=()) -> list[str]:
    return D.check(p, FACTS, assets or {}, confirmed)["errors"]


# ------------------------------------------------------------------------------------------------- words

def test_a_faithful_page_has_no_errors():
    assert errors(page(label("运行限制") + text("no"))) == []


@pytest.mark.parametrize("show", ["该型号建议在高温环境下连续运行", "70%的故障来自润滑不足"])
def test_an_excerpt_may_not_change_what_the_sentence_says(show):
    fid = "no" if "型号" in show else "over"
    assert any("show" in e for e in errors(page(text(fid, show=show))))


def test_a_word_outside_a_reference_is_refused():
    assert errors(page('<div data-t style="left:0"><span>这样写不行</span></div>'))


@pytest.mark.parametrize("words", ["故障率70%", "七成故障", "明显优于同类"])
def test_a_label_may_name_but_not_state(words):
    assert any("只能命名" in e for e in errors(page(label(words))))


def test_a_synthesis_waits_for_a_person():
    p = page('<div data-t style="left:0"><span data-derived="d1"></span></div>',
             derived={"d1": {"text": "润滑是首要问题", "from": ["over", "chain"]}})
    res = D.check(p, FACTS, {})
    assert res["errors"] == [] and res["pending"][0]["text"] == "润滑是首要问题"
    assert D.check(p, FACTS, {}, {res["pending"][0]["digest"]})["pending"] == []


# ------------------------------------------------------------------------------------------------- logic

def arrow(backed: str) -> str:
    return (text("lub", id_="x", top=200) + text("wear", id_="y", top=300)
            + '<svg data-edges style="position:absolute;left:0;top:0;width:1280px;height:720px">'
              f'<polyline points="100,240 100,300" data-from="x" data-to="y" data-backed="{backed}"/></svg>')


def test_an_arrow_needs_a_sentence_that_says_it():
    assert errors(page(arrow("chain"))) == []
    assert any("这个关系原文没有" in e for e in errors(page(arrow("other"))))


def test_an_arrow_the_wrong_way_round_is_refused():
    p = page(arrow("chain").replace('data-from="x" data-to="y"', 'data-from="y" data-to="x"'))
    assert any("这个关系原文没有" in e for e in errors(p))


# ----------------------------------------------------------------------------------- what the code draws

def test_a_bar_stands_for_one_number_in_its_sentence():
    values, bad = D.bar_values([{"fact": "a"}], FACTS)
    assert values == {"a": 8000.0} and not bad
    assert D.bar_values([{"fact": "multi"}], {"multi": fact("甲为5例，乙为7例。")})[1]


# -------------------------------------------------------------------------------- pictures in the page

def picture(tmp_path: Path, role="illustration", anchors=None) -> A.Manifest:
    m = A.Manifest(tmp_path / "assets")
    src = tmp_path / "s.png"
    Image.new("RGBA", (200, 200), (40, 90, 200, 255)).save(src)
    spec = None
    if role == "illustration":
        spec = A.check_spec({"schema_version": A.SCHEMA, "mode": "schematic", "elements": [{"name": "行星齿轮", "fact": "gear"}],
                             "anchors": anchors or {}}, FACTS)
    m.add("fig", role, A.Picture(src.read_bytes(), "drawer", "m"), spec=spec, prompt="p", style="s")
    return m


def img(top=200, left=900, size=300) -> str:
    return (f'<img data-asset="fig" data-role="illustration" '
            f'style="position:absolute;left:{left}px;top:{top}px;width:{size}px;height:{size}px">')


def test_an_asset_not_in_the_manifest_is_refused():
    assert any("不在清单里" in e for e in errors(page(img())))


def test_a_url_background_is_refused_and_a_gradient_is_not():
    assert errors(page(label("甲"), css=".x{background-image:url(a.png)}"))
    assert errors(page(label("甲"), css=".x{background:linear-gradient(90deg,#fff,#eee)}")) == []


def test_a_leader_must_point_at_a_reviewed_place_and_say_its_name(tmp_path):
    m = picture(tmp_path, anchors={"a1": {"name": "行星齿轮", "x": .5, "y": .5}})
    leader = ('<svg data-edges style="position:absolute;left:0;top:0;width:1280px;height:720px">'
              '<polyline points="500,300 1050,350" data-anchor="fig:{k}" data-label="tag"/></svg>')
    good = text("gear", show="行星齿轮", id_="tag") + img() + leader.format(k="a1")
    assert errors(page(good), m.items) == []
    assert any("标定点不存在" in e for e in errors(page(good.replace("fig:a1", "fig:zz")), m.items))
    wrong = text("other", show="外壳", id_="tag") + img() + leader.format(k="a1")
    assert any("须说到" in e for e in errors(page(wrong), m.items))


# ------------------------------------------------------------------------------------- the whole way out

def _chromium_ok() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            pw.chromium.launch().close()
        return True
    except Exception:
        return False


needs_browser = pytest.mark.skipif(not _chromium_ok(), reason="playwright chromium not available")
FULL = label("润滑与寿命") + text("over", tier="body", top=180, size=28) + text("other", top=280) + text("no", top=380) + text("chain", top=480)


def out(tmp_path) -> Path:
    return tmp_path / "out" / "deck.pptx"


@needs_browser
def test_a_clean_page_becomes_a_native_deck_with_a_trace(tmp_path):
    m = A.Manifest(tmp_path / "a")
    res = D.export([page(FULL)], FACTS, m, STYLE, out(tmp_path), source="来源：手册")
    assert res["ok"], res
    from pptx import Presentation
    shown = " ".join(s.text_frame.text for s in Presentation(res["pptx"]).slides[0].shapes if s.has_text_frame)
    assert "超过70%" in shown and "来源：手册" in shown
    assert "第 3 页" in out(tmp_path).with_suffix(".trace.md").read_text(encoding="utf-8")


@needs_browser
def test_an_unsigned_illustration_stops_the_deck(tmp_path):
    m = picture(tmp_path)
    res = D.export([page(FULL + img(top=20, left=1000, size=120))], FACTS, m, STYLE, out(tmp_path), source="s")
    assert not res["ok"] and res["pptx"] is None and "等待主讲人确认" in res["pages"][0]["pending"][0]["why"]


@needs_browser
def test_a_signed_illustration_ships_as_a_picture_and_the_trace_says_signed_not_verified(tmp_path):
    m = picture(tmp_path)
    items = A.checklist(m.items["fig"]["spec"])
    m.review("fig", "reader", {"has_text": False}, {"answers": [{"id": c["id"], "answer": "yes"} for c in items], "beyond": ["轴承"]})
    m.sign("fig", "主讲人")
    res = D.export([page(FULL + img(top=20, left=1000, size=120))], FACTS, m, STYLE, out(tmp_path), source="s")
    assert res["ok"], res
    from pptx import Presentation
    assert any(s.name == "asset:fig" for s in Presentation(res["pptx"]).slides[0].shapes)
    report = out(tmp_path).with_suffix(".trace.md").read_text(encoding="utf-8")
    assert "主讲人已确认" in report and "不代表图的内容已被验证" in report and "轴承" in report


@needs_browser
def test_text_on_a_picture_is_refused(tmp_path):
    m = picture(tmp_path)
    items = A.checklist(m.items["fig"]["spec"])
    m.review("fig", "reader", {"has_text": False}, {"answers": [{"id": c["id"], "answer": "yes"} for c in items]})
    m.sign("fig", "主讲人")
    res = D.export([page(FULL + img(top=170, left=100, size=300))], FACTS, m, STYLE, out(tmp_path), source="s")
    assert not res["ok"] and any("text-on-image" in e for e in res["pages"][0]["errors"])


@needs_browser
def test_a_bar_drawn_at_the_wrong_length_is_refused(tmp_path):
    def bar(fid, w, top):
        return f'<div data-shape data-value-of="{fid}" data-scale="life" style="position:absolute;left:64px;top:{top}px;width:{w}px;height:40px;background:#0B46B4"></div>'
    html = FULL + bar("a", 800, 560) + bar("b", 700, 610)
    res = D.export([page(html, design={"figure": "柱长"})], FACTS, A.Manifest(tmp_path / "a"), STYLE, out(tmp_path), source="s")
    assert not res["ok"] and any("按数值应为" in e for e in res["pages"][0]["errors"]), res


@needs_browser
def test_a_leader_that_lands_elsewhere_is_refused(tmp_path):
    m = picture(tmp_path, anchors={"a1": {"name": "行星齿轮", "x": .5, "y": .5}})
    items = A.checklist(m.items["fig"]["spec"])
    m.review("fig", "reader", {"has_text": False}, {"answers": [{"id": c["id"], "answer": "yes"} for c in items]})
    m.sign("fig", "主讲人")
    leader = ('<svg data-edges style="position:absolute;left:0;top:0;width:1280px;height:720px">'
              '<polyline points="964,300 {x},{y}" data-anchor="fig:a1" data-label="tag"/></svg>')
    base = FULL + img(top=20, left=1000, size=200) + text("gear", show="行星齿轮", id_="tag", top=590)
    miss = D.export([page(base + leader.format(x=1010, y=30))], FACTS, m, STYLE, out(tmp_path), source="s")
    assert any("离标定点" in e for e in miss["pages"][0]["errors"])
    hit = D.export([page(base + leader.format(x=1100, y=120))], FACTS, m, STYLE, out(tmp_path), source="s")
    assert not any("离标定点" in e for e in hit["pages"][0]["errors"])
