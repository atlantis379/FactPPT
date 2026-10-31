"""The borrowed design rules: what the audit refuses and what it only reports.

Every case here is one line of ``design-principle.md`` turned into a measurement, so a page that breaks a rule is
caught by the same pass that catches overflow — not by looking at a screenshot afterwards.
"""
from __future__ import annotations

from factdeck import design_audit as D


def page(**kw) -> dict:
    ink = [{"role": "title", "text": "标题", "size": 40, "weight": "bold", "lineHeight": 1.22,
            "top": 78, "bottom": 118, "inMain": False},
           {"role": "body", "text": "正文", "size": 18, "weight": "normal", "lineHeight": 1.55,
            "top": 200, "bottom": 520, "inMain": True},
           {"role": "note", "text": "来源", "size": 14, "weight": "normal", "lineHeight": 1.45,
            "top": 670, "bottom": 690, "inMain": False}]
    base = {"ink": ink, "footerTop": 670}
    base.update(kw)
    return base


def rules(measured, **kw) -> list[str]:
    return [b["rule"] for b in D.audit(measured, **kw)]


def test_a_page_that_follows_the_rules_passes():
    assert rules(page()) == []


def test_text_below_the_floor_of_its_role_is_an_error():
    bad = page()
    bad["ink"][2] = {**bad["ink"][2], "size": 12}          # 12px footnote, floor is 14
    found = D.audit(bad)
    assert [b["rule"] for b in found] == ["min-size"]
    assert found[0].get("level") != "warn"


def test_a_body_smaller_than_the_body_floor_is_refused():
    bad = page()
    bad["ink"][1] = {**bad["ink"][1], "size": 16}          # 16px body, floor is 18
    assert "min-size" in rules(bad)


def test_the_page_may_not_spend_more_than_four_type_styles():
    many = page()
    many["ink"] = many["ink"] + [
        {"role": "label", "text": "a", "size": 16, "weight": "bold", "lineHeight": 1.3, "top": 150, "bottom": 170},
        {"role": "label", "text": "b", "size": 22, "weight": "bold", "lineHeight": 1.3, "top": 150, "bottom": 170},
        {"role": "take", "text": "c", "size": 18, "weight": "normal", "lineHeight": 1.4, "top": 600, "bottom": 620},
    ]
    assert "type-styles" in rules(many)
    assert all(b.get("level") == "warn" for b in D.audit(many) if b["rule"] == "type-styles")


def test_a_unit_does_not_spend_a_style_of_its_own():
    with_unit = page()
    with_unit["ink"] = with_unit["ink"] + [
        {"role": "figure", "text": "5", "size": 96, "weight": "bold", "lineHeight": 1, "top": 200, "bottom": 300},
        {"role": "unit", "text": "天", "size": 31, "weight": "bold", "lineHeight": 1, "top": 280, "bottom": 300},
    ]
    assert "type-styles" not in rules(with_unit)


def test_the_footer_sits_where_the_rule_says():
    assert "footer" in rules(page(footerTop=690))


def test_content_may_not_run_under_the_footer():
    spill = page()
    spill["ink"][1] = {**spill["ink"][1], "bottom": 700}
    assert "content-height" in rules(spill)


def test_a_page_that_cannot_fill_its_area_is_reported_not_refused():
    thin = page()
    thin["ink"][1] = {**thin["ink"][1], "top": 300, "bottom": 360}
    found = [b for b in D.audit(thin) if b["rule"] == "content-fill"]
    assert found and found[0]["level"] == "warn"


def test_a_hero_page_may_leave_room():
    """§4.1: 一页只说一件事时，四周的空白就是这页的内容。留白是模型的声明，不是漏排的版面。"""
    thin = page()
    thin["ink"][1] = {**thin["ink"][1], "top": 300, "bottom": 360}
    assert "content-fill" not in rules(thin, role="hero")
    # 留白可以声明，别的规则不可以：越界照样报
    thin["ink"][1] = {**thin["ink"][1], "bottom": 700}
    assert "content-height" in rules(thin, role="hero")
