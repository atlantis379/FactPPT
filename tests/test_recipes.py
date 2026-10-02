"""Composition recipes: slots in, composed blocks out; the same checks apply to the result.

Content is invented test data.
"""
import pytest

from factdeck import compose, recipes
from factdeck.deck import check

from tests.test_composed import facts as real_facts


def fake_facts(page_slots) -> dict:
    """Every fact id referenced in `page_slots`, with a short text holding one year-like number (bar values and dates parse)."""
    ids = set()

    def walk(x):
        if isinstance(x, dict):
            if "fact" in x:
                ids.add(x["fact"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(page_slots)
    return {i: {"id": i, "quote": f"示例{2010 + n}", "display": "", "status": "ACCEPTED", "needs_confirmation": False}
            for n, i in enumerate(sorted(ids))}


@pytest.mark.parametrize("name", sorted(recipes.RECIPES))
def test_every_recipe_example_places_its_blocks_inside_the_body(name):
    _, use_for, slots = recipes.RECIPES[name]
    assert use_for
    page = {"id": "p", "layout": "composed", "recipe": name, "title": {"text": "标题"}, "slots": slots}
    out = recipes.expand(page, fake_facts(slots))
    assert out["blocks"] and "slots" not in out
    assert compose.structure_errors(out) == [], name


def test_measured_heights_replace_estimates():
    c = recipes.Ctx({"id": "p"}, {})
    text = "一段需要测量高度的文字"
    assert c.height(text, 17, 300) == recipes.height(text, 17, 300)
    c = recipes.Ctx({"id": "p"}, {}, {recipes.mkey(text, 17, 300): 77})
    assert c.height(text, 17, 300) == 77


def test_content_too_tall_for_a_page_is_reported_not_squeezed():
    rows = [[{"fact": f"o{i}"}, [{"fact": f"p{i}{j}"} for j in range(4)]] for i in range(12)]
    slots = {"headers": [{"text": "对象"}, {"text": "属性"}], "rows": rows}
    deck = {"pages": [{"id": "p", "layout": "composed", "recipe": "entity_rows", "title": {"text": "标题"}, "slots": slots}]}
    _, errors = recipes.expand_deck(deck, fake_facts(slots))
    assert "拆页" in errors["p"]


def test_a_recipe_page_passes_the_same_checks_as_any_composed_page():
    fs = real_facts()
    page = {"id": "p", "layout": "composed", "recipe": "entity_rows", "title": {"text": "标题"},
            "slots": {"headers": [{"text": "对象"}, {"text": "年份"}], "rows": [[{"fact": "c1"}, {"fact": "y.cn"}]]}}
    res = check({"pages": [page]}, fs)["pages"][0]
    assert any("范围标签“中国”" in e for e in res["errors"])          # the scope rule still applies
    page["slots"]["rows"][0].append({"fact": "lg.cn"})
    page["slots"]["headers"].append({"text": "地区"})
    assert check({"pages": [page]}, fs)["pages"][0]["errors"] == []


def test_recipe_items_are_grouped_for_editing():
    _, _, slots = recipes.RECIPES["lanes"]
    out = recipes.expand({"id": "p", "layout": "composed", "recipe": "lanes", "title": {"text": "标题"}, "slots": slots}, fake_facts(slots))
    groups = {b.get("group") for b in out["blocks"]}
    assert {"lane0", "lane1", "attached"} <= groups
