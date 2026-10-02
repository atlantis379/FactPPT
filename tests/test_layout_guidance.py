"""Structured layouts: diagram arrows backed by transcribed source arrows, layout guide, monotony warning.

Content is invented test data.
"""
from factdeck import facts as fx
from factdeck.deck import check, _structure, LAYOUTS, LAYOUT_GUIDE

UNITS = [{"id": "D1", "source_id": "S01", "location": "第2页 图 节点1", "text": "诱因"},
         {"id": "D2", "source_id": "S01", "location": "第2页 图 节点2", "text": "屏障受损"},
         {"id": "D3", "source_id": "S01", "location": "第2页 图 节点3", "text": "炎症放大"},
         {"id": "A1", "source_id": "S01", "location": "第2页 图 箭头1", "text": "诱因 → 屏障受损"},
         {"id": "A2", "source_id": "S01", "location": "第2页 图 箭头2", "text": "屏障受损→炎症放大（持续）"},
         {"id": "P1", "source_id": "S01", "location": "第3段", "text": "诱因作用于屏障，随后引起炎症放大"}]


def facts():
    F = lambda i, u, q: {"id": i, "unit": u, "quote": q}
    Fs, D, T = fx.parse({"facts": [F("n1", "D1", "诱因"), F("n2", "D2", "屏障受损"), F("n3", "D3", "炎症放大"),
                                   F("a1", "A1", "诱因 → 屏障受损"), F("a2", "A2", "屏障受损→炎症放大（持续）"),
                                   F("p1", "P1", "诱因作用于屏障，随后引起炎症放大")]})
    fx.verify(Fs, D, UNITS, {}, T)
    out = {f["id"]: f for f in fx.as_dict(Fs, D, [])["facts"]}
    assert all(f["status"] == "ACCEPTED" for f in out.values())
    return out


def flow(edges):
    return {"id": "m", "layout": "flow", "title": {"text": "过程"},
            "nodes": [{"id": "a", "ref": {"fact": "n1"}, "col": 0, "row": 0}, {"id": "b", "ref": {"fact": "n2"}, "col": 1, "row": 0},
                      {"id": "c", "ref": {"fact": "n3"}, "col": 2, "row": 0}], "edges": edges}


def test_transcribed_arrow_backs_an_edge_without_being_shown():
    res = check({"pages": [flow([["a", "b", "a1"], ["b", "c", "a2"]])]}, facts())
    page = res["pages"][0]
    assert page["errors"] == []
    assert page["edge_facts"] == ["a1", "a2"] and not {"a1", "a2"} & set(page["facts"])


def test_arrow_fact_must_join_the_two_nodes_in_its_direction():
    assert check({"pages": [flow([["b", "a", "a1"]])]}, facts())["pages"][0]["errors"]      # reversed
    assert check({"pages": [flow([["a", "c", "a1"]])]}, facts())["pages"][0]["errors"]      # wrong end
    assert check({"pages": [flow([["a", "c", "p1"]])]}, facts())["pages"][0]["errors"]      # prose, not an arrow, and not shown


def test_shown_fact_still_backs_an_edge():
    page = {**flow([["a", "c", "p1"]]), "side": [{"fact": "p1"}]}
    res = check({"pages": [page]}, facts())["pages"][0]
    assert res["errors"] == [] and res["edge_facts"] == []


def test_every_layout_has_a_valid_example():
    assert set(LAYOUT_GUIDE) == set(LAYOUTS)
    for layout, (use_for, body) in LAYOUT_GUIDE.items():
        assert use_for
        assert _structure({"id": "x", "layout": layout, "title": {"text": "标题"}, **body}) == [], layout


def test_tables_splitting_one_set_of_objects_by_attribute_are_flagged():
    fs = facts()
    tbl = lambda i, col: {"id": i, "layout": "table", "title": {"text": "对照"}, "columns": ["对象", col],
                          "rows": [[[{"fact": "n1"}], [{"fact": "p1"}]], [[{"fact": "n2"}], [{"fact": "p1"}]]]}
    other = {**tbl("c", "属性丙"), "rows": [[[{"fact": "n3"}], [{"fact": "p1"}]]]}
    assert any("合并为一张多列表" in w for w in check({"pages": [tbl("a", "属性甲"), tbl("b", "属性乙")]}, fs)["warnings"])
    assert not any("合并" in w for w in check({"pages": [tbl("a", "属性甲"), other]}, fs)["warnings"])


def test_long_runs_of_lists_and_tables_are_flagged():
    fs = facts()
    bullets = lambda i: {"id": f"b{i}", "layout": "bullets", "title": {"text": "要点"}, "items": [{"fact": "p1"}]}
    plain = check({"pages": [bullets(i) for i in range(6)]}, fs)
    assert plain["errors"] == 0 and any("连续 6 页" in w for w in plain["warnings"]) and any("过于单一" in w for w in plain["warnings"])
    statement = {"id": "s", "layout": "statement", "title": {"text": "要点"}, "statement": {"fact": "p1"}}
    assert any("连续 4 页" in w for w in check({"pages": [bullets(0), statement, bullets(1), bullets(2)]}, fs)["warnings"])
    mixed = [bullets(0), {**flow([["a", "b", "a1"]])}, bullets(1), {**flow([["b", "c", "a2"]]), "id": "m2"},
             {**flow([["a", "b", "a1"]]), "id": "m3"}, {**flow([["b", "c", "a2"]]), "id": "m4"}, {**flow([["a", "b", "a1"]]), "id": "m5"}]
    warnings = check({"pages": mixed}, fs)["warnings"]
    assert not any("纯文字" in w or "只用列表" in w for w in warnings)
    assert any("同一种构图 flow" in w for w in warnings)          # four flows in a row: a different signal


def test_the_same_composition_page_after_page_is_a_signal_a_page_may_justify():
    fs = facts()
    flows = [{**flow([["a", "b", "a1"]]), "id": f"f{i}"} for i in range(3)]
    assert any("连续 3 页使用同一种构图" in w for w in check({"pages": flows}, fs)["warnings"])
    why = {"exceptions": [{"signal": "repetition", "reason": "同一流程的三个阶段"}]}
    justified = [flows[0]] + [{**f, "design": why} for f in flows[1:]]
    assert not any("同一种构图" in w for w in check({"pages": justified}, fs)["warnings"])
