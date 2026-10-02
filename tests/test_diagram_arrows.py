"""Diagram arrows recovered from slide geometry, and labelled edges on flow pages.

Content is invented test data; the slide is generated for the test.
"""
import io

from pptx import Presentation
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

from factdeck import facts as fx
from factdeck.deck import check
from factdeck.diagram import arrows
from factdeck.ingest import extract_all
from factdeck.render import render

W = 12192000
E = lambda x: int(x * 12700)            # points → EMU


def box(x, y, w=80, h=30):
    return (E(x), E(y), E(w), E(h))


# ------------------------------------------------------------------ geometry
def test_split_through_a_bracket_gives_one_arrow_per_branch_with_its_label():
    boxes = {"q": box(100, 100), "yes": box(40, 200), "no": box(160, 200), "l_yes": box(70, 160, 12, 18), "l_no": box(150, 160, 12, 18)}
    trunk = ([(E(140), E(130)), (E(140), E(170))], False, True, "q", None)          # arrowhead onto the bracket
    bracket = ([(E(80), E(200)), (E(80), E(170)), (E(200), E(170)), (E(200), E(200))], True, True, "yes", "no")
    got = arrows(boxes, [trunk, bracket], [], {"l_yes": "是", "l_no": "否"}, W)
    assert {(a["from"], a["to"], a["label"]) for a in got} == {("q", "yes", "l_yes"), ("q", "no", "l_no")}


def test_lines_without_arrowheads_say_nothing_about_direction():
    boxes = {"a": box(0, 0), "b": box(200, 0)}
    assert arrows(boxes, [([(E(80), E(15)), (E(200), E(15))], False, False, "a", "b")], [], {}, W) == []


def test_block_arrow_joins_the_nearest_boxes_and_prefers_the_specific_one():
    boxes = {"big": box(0, 0, 400, 100), "pill": box(20, 60, 80, 40), "card": box(20, 160, 100, 40)}
    got = arrows(boxes, [], [(E(40), E(110), E(20), E(40), "down")], {}, W)
    assert [(a["from"], a["to"]) for a in got] == [("pill", "card")]


def _slide_with_diagram():
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[6])
    q = s.shapes.add_shape(MSO_SHAPE.DIAMOND, Inches(3), Inches(1), Inches(2), Inches(1))
    q.text_frame.text = "指标甲升高？"
    a = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1), Inches(3), Inches(2), Inches(0.8))
    a.text_frame.text = "进入路径一"
    b = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(5), Inches(3), Inches(2), Inches(0.8))
    b.text_frame.text = "进入路径二"
    for target, (x, y), label in ((a, (2.8, 2.35), "是"), (b, (4.8, 2.35), "否")):     # on the connector's midpoint
        c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, 0, 0, 0, 0)
        c.begin_connect(q, 2)
        c.end_connect(target, 0)
        c.line._get_or_add_ln().append(c.line._ln.makeelement(qn("a:tailEnd"), {"type": "triangle"}))
        t = s.shapes.add_textbox(Inches(x), Inches(y), Inches(0.4), Inches(0.3))
        t.text_frame.text = label
    down = s.shapes.add_shape(MSO_SHAPE.DOWN_ARROW, Inches(1.8), Inches(4), Inches(0.4), Inches(0.6))
    c2 = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(4.7), Inches(2), Inches(0.6))
    c2.text_frame.text = "随访评估"
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def test_pptx_ingest_records_arrows_with_their_end_units_and_labels():
    _, units, _ = extract_all("d.pptx", _slide_with_diagram(), "S01")
    by_id = {u.id: u for u in units}
    arrows_ = [u for u in units if u.method == "pptx_arrow"]
    got = {(by_id[u.arrow["from"]].text, by_id[u.arrow["to"]].text, by_id[u.arrow["label"]].text if u.arrow["label"] else None) for u in arrows_}
    assert got == {("指标甲升高？", "进入路径一", "是"), ("指标甲升高？", "进入路径二", "否"), ("进入路径一", "随访评估", None)}
    assert any(u.text == "指标甲升高？→进入路径一（是）" for u in arrows_)


# ------------------------------------------------------------------ deck check and rendering
def _facts():
    """Facts quoted from the generated slide, and which arrow fact joins which pair of nodes."""
    units = [{"id": u.id, "source_id": "S01", "location": u.location, "text": u.text, "arrow": u.arrow}
             for u in extract_all("d.pptx", _slide_with_diagram(), "S01")[1]]
    uid = {u["text"]: u["id"] for u in units if not u["arrow"]}
    F = lambda i, text: {"id": i, "unit": uid[text], "quote": text}
    raw = [F("q", "指标甲升高？"), F("a", "进入路径一"), F("b", "进入路径二"), F("yes", "是"), F("no", "否"), F("c", "随访评估")]
    arrow_units = [u for u in units if u["arrow"]]
    raw += [{"id": f"arr{k}", "unit": u["id"], "quote": u["text"]} for k, u in enumerate(arrow_units)]
    Fs, D, T = fx.parse({"facts": raw})
    fx.verify(Fs, D, units, {}, T)
    out = {f["id"]: f for f in fx.as_dict(Fs, D, [])["facts"]}
    assert all(f["status"] == "ACCEPTED" for f in out.values())
    by_ends = {(u["arrow"]["from"], u["arrow"]["to"]): f"arr{k}" for k, u in enumerate(arrow_units)}
    return out, {(x, y): by_ends[(out[x]["unit"], out[y]["unit"])] for x, y in (("q", "a"), ("q", "b"))}


def flow(edges):
    return {"id": "m", "layout": "flow", "title": {"text": "判断"},
            "nodes": [{"id": "q", "ref": {"fact": "q"}, "col": 0, "row": 1}, {"id": "a", "ref": {"fact": "a"}, "col": 1, "row": 0},
                      {"id": "b", "ref": {"fact": "b"}, "col": 1, "row": 2}], "edges": edges}


def test_source_arrow_backs_an_edge_only_between_its_own_end_units_and_with_its_own_label():
    fs, arr = _facts()
    ok = check({"pages": [flow([["q", "a", arr["q", "a"], {"fact": "yes"}], ["q", "b", arr["q", "b"], {"fact": "no"}]])]}, fs)
    assert ok["errors"] == 0 and set(ok["pages"][0]["edge_facts"]) == {arr["q", "a"], arr["q", "b"]}
    assert {"yes", "no"} <= set(ok["pages"][0]["facts"])
    swapped = check({"pages": [flow([["q", "a", arr["q", "a"], {"fact": "no"}], ["q", "b", arr["q", "b"], {"fact": "yes"}]])]}, fs)
    assert swapped["errors"] == 2                                                   # labels exchanged
    assert check({"pages": [flow([["q", "b", arr["q", "a"]]])]}, fs)["errors"]     # arrow of another branch
    assert check({"pages": [flow([["a", "q", arr["q", "a"]]])]}, fs)["errors"]     # reversed
    unlabelled = check({"pages": [flow([["q", "a", arr["q", "a"]]])]}, fs)
    assert unlabelled["errors"] == 0 and any("带标签" in w for w in unlabelled["warnings"])
    long = check({"pages": [flow([["q", "a", "q", {"text": "这是一段很长的说明"}]])]}, fs)
    assert any("过长" in e for e in long["pages"][0]["errors"])


def test_labelled_flow_renders_labels_as_native_text(tmp_path):
    fs, arr = _facts()
    deck = {"title": "箭头标签", "pages": [flow([["q", "a", arr["q", "a"], {"fact": "yes"}], ["q", "b", arr["q", "b"], {"fact": "no"}]])]}
    report = render(deck, fs, {"S01": {"title": "测试资料", "filename": "d.pptx"}}, tmp_path)
    assert report["hard_errors"] == 0, report["summary"]
    texts = [sh.text_frame.text for sh in Presentation(str(tmp_path / "deck.pptx")).slides[0].shapes if sh.has_text_frame]
    assert "是" in texts and "否" in texts
