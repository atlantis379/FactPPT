"""Composed pages (one design solution per page) and the rules that still hold on every page.

Content is invented test data.
"""
from factdeck import facts as fx
from factdeck import compose
from factdeck.deck import check
from factdeck.lexicon import scope_labels
from factdeck.render import sparse, whitespace_reason

UNITS = [{"id": "Y1", "source_id": "S01", "location": "第1页 表", "text": "中国：2017\n美国：2003"},
         {"id": "S1", "source_id": "S01", "location": "第2页", "text": "甲细胞释放乙因子，激活丙细胞"},
         {"id": "V1", "source_id": "S01", "location": "第3页 图", "text": "20.0%"},
         {"id": "V2", "source_id": "S01", "location": "第3页 图", "text": "34.0%"},
         {"id": "N1", "source_id": "S01", "location": "第4页", "text": "轻度"},
         {"id": "N2", "source_id": "S01", "location": "第4页", "text": "轻度"}]


def facts():
    F = lambda i, u, q, d="": {"id": i, "unit": u, "quote": q, **({"display": d} if d else {})}
    Fs, D, T = fx.parse({"facts": [F("y.cn", "Y1", "中国：2017", "2017"), F("lg.cn", "Y1", "中国：2017", "中国"),
                                   F("s", "S1", "甲细胞释放乙因子，激活丙细胞"), F("c1", "S1", "甲细胞释放乙因子"),
                                   F("c2", "S1", "激活丙细胞"), F("v1", "V1", "20.0%"), F("v2", "V2", "34.0%"),
                                   F("k1", "N1", "轻度"), F("k2", "N2", "轻度")]})
    fx.verify(Fs, D, UNITS, {}, T)
    out = {f["id"]: f for f in fx.as_dict(Fs, D, [])["facts"]}
    assert all(f["status"] == "ACCEPTED" for f in out.values()), {k: f["problems"] for k, f in out.items()}
    return out


def text(fid, x=0, y=0, **kw):
    return {"kind": "text", "x": x, "y": y, "w": 300, "h": 40, "role": "body", "refs": [{"fact": fid}], **kw}


def page(blocks, **kw):
    return {"id": "p", "layout": "composed", "title": {"text": "标题"}, "blocks": blocks, **kw}


def run(p):
    return check({"pages": [p]}, facts())


def test_a_dropped_scope_label_must_be_stated_once_on_the_page():
    assert scope_labels("2017", "中国：2017\n美国：2003") == ["中国"]
    assert facts()["y.cn"]["scope"] == ["中国"]
    alone = run(page([text("y.cn")]))["pages"][0]["errors"]
    assert any("范围标签“中国”" in e for e in alone)
    assert run(page([text("y.cn"), text("lg.cn", y=60)]))["pages"][0]["errors"] == []


def test_a_dropped_entry_that_is_not_followed_by_kept_text_is_not_a_scope_label():
    assert scope_labels("SEA：重度哮喘", "SEA：重度哮喘；OCS：口服激素") == []


def test_peers_must_share_one_treatment():
    a = {"kind": "surface", "x": 0, "y": 0, "w": 500, "h": 100, "tone": "tint", "peer": "lane"}
    b = {**a, "y": 120}
    assert run(page([a, b, text("c1", 20, 20)]))["pages"][0]["errors"] == []
    errs = run(page([a, {**b, "tone": "strong"}, text("c1", 20, 20)]))["pages"][0]["errors"]
    assert any("并列组“lane”" in e for e in errs)


def test_a_sentence_split_into_steps_backs_its_own_arrows_in_order_only():
    blocks = [text("c1", id="a"), text("c2", x=400, id="b")]
    ok = run(page(blocks + [{"kind": "arrow", "from": "a", "to": "b", "backed_by": "s", "points": [[310, 20], [390, 20]]}]))["pages"][0]
    assert ok["errors"] == [] and ok["edge_facts"] == ["s"]
    assert any("拆成先后环节" in r for r in ok["review"])
    back = run(page(blocks + [{"kind": "arrow", "from": "b", "to": "a", "backed_by": "s", "points": [[390, 20], [310, 20]]}]))
    assert back["pages"][0]["errors"]


def test_bars_are_proportional_and_their_values_must_be_shown():
    bars = [{"kind": "bar", "x": 0, "y": 0, "max_w": 400, "h": 20, "value_of": "v1", "scale": "s"},
            {"kind": "bar", "x": 0, "y": 30, "max_w": 400, "h": 20, "value_of": "v2", "scale": "s", "tone": "strong"}]
    hidden = run(page(bars))["pages"][0]["errors"]
    assert any("须在本页显示" in e for e in hidden)
    shown = page(bars + [text("v1", 500, 0), text("v2", 500, 30)])
    assert run(shown)["pages"][0]["errors"] == []
    m = compose.model(shown, compose.bar_values(shown, facts()))
    widths = [b["w"] for b in m["blocks"] if b["kind"] == "bar"]
    assert widths == [round(20.0 / 34.0 * 400, 1), 400]


def test_blocks_stay_inside_the_body():
    errs = run(page([text("c1", x=1000)]))["pages"][0]["errors"]
    assert any("超出版心" in e for e in errs)
    under_lead = page([text("c1", y=420)], lead={"fact": "c2"})         # 436 px under a lead
    assert any("超出版心" in e for e in run(under_lead)["pages"][0]["errors"])


def test_emphasis_inside_a_quote_goes_to_semantic_review():
    p = page([{**text("s"), "refs": [{"fact": "s", "emph": ["激活"]}]}])
    assert any("强调了 激活" in r for r in run(p)["pages"][0]["review"])


def test_repetition_is_a_signal_the_page_may_justify():
    p = page([text("k1"), text("k2", y=60)])
    res = run(p)
    assert any("重复" in w for w in res["warnings"])
    why = page([text("k1"), text("k2", y=60)], design={"first": "两组", "exceptions": [{"signal": "repetition", "reason": "两张图各标一次"}]})
    res = run(why)
    assert not any("重复" in w for w in res["warnings"])
    assert res["pages"][0]["signals"][0]["justified"] == "两张图各标一次"


def test_design_exceptions_need_a_known_signal_and_a_reason():
    bad = page([text("c1")], design={"exceptions": [{"signal": "whitespace"}]})
    assert any("design.exceptions" in e for e in run(bad)["pages"][0]["errors"])


def test_whitespace_is_a_signal_the_page_may_justify():
    slide = {"id": "p", "occupancy": 1, "hole": {"share": 0.3}}
    plain = {"layout": "composed"}
    assert sparse(slide, plain) and whitespace_reason(plain) is None
    why = {"layout": "composed", "design": {"exceptions": [{"signal": "whitespace", "reason": "年代间隔"}]}}
    assert whitespace_reason(why) == "年代间隔"
    assert not sparse({"id": "c", "occupancy": 0.1}, {"layout": "cover"})
