"""argument.v1 — what the deck asserts, and whether the count of assertions justifies the page count.

The grade is the model's declaration, not a code guess: a first attempt graded text from keyword tables and both
「漏诊是最先要处理的问题」and「初始治疗按分组选择」came out as noun phrases, which is worse than not grading at
all.  So every case here is about *verifying a declaration* — the number is in the sentence, the unit survived,
the modality did not get stronger — never about deciding how strong a sentence sounds.
"""
from __future__ import annotations

import pytest

from factdeck import argument as A

FACTS = {
    "ud-70": {"quote": "全球范围内的研究表明，高达70%的慢性阻塞性肺疾病成人患者未被确诊。"},
    "ud-81": {"quote": "一项涵盖27国的协作研究发现，患病率为9.7%，其中81%的病例未被确诊。"},
    "ud-exac": {"quote": "其经年龄和性别校正后的急性加重和肺炎风险比，分别比同龄非慢性阻塞性肺疾病个体高出15.5倍和2.8倍。"},
    "ster": {"quote": "对于中度/重度急性加重的患者，推荐使用全身性糖皮质激素，疗程不超过5天。"},
    "pv": {"quote": "适用于所有≥ 50 岁及以上的成人"},
    "abx": {"quote": "对于有脓痰、既往肺部感染史等的患者，推荐抗生素治疗总疗程为5天。"},
}


def spec(*claims) -> dict:
    return {"schema_version": A.SCHEMA, "claims": list(claims)}


def claim(**kw) -> dict:
    base = {"id": "c1", "grade": "L3", "text": "全球70%的成人患者未被确诊", "evidence": ["ud-70"]}
    base.update(kw)
    return base


def action_claim() -> dict:
    """Every list needs one that lands on an action, or the deck informs and does not decide."""
    return {"id": "ck", "grade": "L3", "text": "推荐抗生素疗程 5 天", "evidence": ["abx"]}


def ok(*extra) -> dict:
    return A.check(spec(action_claim(), *extra), FACTS)


# ------------------------------------------------------------------ the declaration and its evidence

def test_a_declared_quantisation_is_resolved_against_its_sentence():
    a = ok(claim())["claims"][1]
    assert a["grade"] == "L3" and a["numbers"] == {"70"} and a["units"] == {"%"}
    assert a["quotes"] == [FACTS["ud-70"]["quote"]]


def test_a_declared_quantisation_without_a_number_is_refused():
    """等级是声明，声明就得有东西撑着：说 L3 而句子里没有可核对的数，等于把判断当成了数据。"""
    with pytest.raises(A.ArgumentError, match="没有任何可核对的数字"):
        ok(claim(text="非药物治疗的要点"))


def test_a_chinese_numeral_does_not_count_as_data():
    """「七成」读者没法拿去核对：原文写 70%，断言就该写 70%。"""
    with pytest.raises(A.ArgumentError, match="没有任何可核对的数字"):
        ok(claim(text="全球七成成人患者未被确诊"))


def test_a_grade_below_the_floor_cannot_be_a_page():
    with pytest.raises(A.ArgumentError, match="不能单独成一页"):
        ok(claim(grade="L2", text="漏诊比误诊更常见"))
    with pytest.raises(A.ArgumentError, match="须声明 grade"):
        ok(claim(grade="strong"))


def test_a_number_must_be_in_the_sentence_it_cites():
    with pytest.raises(A.ArgumentError, match="找不到：80"):
        ok(claim(text="全球80%的成人患者未被确诊"))


def test_the_unit_is_checked_apart_from_the_digits():
    """数字一样、单位换掉，意思全变：70% 写成 70 例，读者读到的是另一个事实。"""
    with pytest.raises(A.ArgumentError, match="单位在来源句里没有：例"):
        ok(claim(text="全球70例成人患者未被确诊"))


def test_a_boundary_needs_a_quantity_and_its_own_evidence():
    with pytest.raises(A.ArgumentError, match="没有给 boundary"):
        ok(claim(grade="L4"))
    with pytest.raises(A.ArgumentError, match="边界里有句外的数字：90"):
        ok(claim(grade="L4", boundary="在低收入国家超过 90%"))
    assert ok(claim(grade="L4", boundary="适用于未接受过治疗的患者"))["claims"][1]["grade"] == "L4"


def test_a_boundary_too_short_to_say_anything_is_refused():
    with pytest.raises(A.ArgumentError, match="太短"):
        ok(claim(grade="L4", boundary="部分"))


# ------------------------------------------------------------------------------- what changes meaning

def test_modality_may_be_lowered_but_never_raised():
    # 原文是推荐 → 断言写成「可以考虑」：保守，允许。
    ok(claim(text="可以考虑全身激素，疗程不超过 5 天", evidence=["ster"]))
    # 原文只是描述 → 断言写成「应」：数字全对，结论已经错了。
    with pytest.raises(A.ArgumentError, match="用了强推荐"):
        ok(claim(text="50 岁以上成人都应接种疫苗", evidence=["pv"]))


def test_two_assertions_may_not_say_the_same_thing():
    with pytest.raises(A.ArgumentError, match="说的是同一件事"):
        ok(claim(), claim(id="c2"))


def test_opposite_polarity_is_not_a_duplicate():
    """「70% 未被确诊」和「70% 已确诊」只差一个字，意思相反：字符重合度高不等于重复。"""
    A.check(spec(action_claim(),
                 claim(text="全球70%的成人患者未被确诊"),
                 claim(id="c2", text="全球70%的成人患者已确诊")), FACTS)


def test_the_list_has_to_land_on_an_action():
    with pytest.raises(A.ArgumentError, match="没有一条落到行动"):
        A.check(spec(claim(), claim(id="c2", text="相对同龄人风险高出 15.5 倍", evidence=["ud-exac"])), FACTS)


# ------------------------------------------------------------------------------------ the page count

def test_pages_follow_from_the_assertions_not_the_other_way_round():
    rng = A.page_range(13)
    assert (rng["low"], rng["high"], rng["sections"]) == (13, 17, 4)
    assert "不成立" in A.verdict(20, rng) and "补 7 条" in A.verdict(20, rng)
    assert "成立" in A.verdict(15, rng)


def test_a_deck_too_short_for_its_assertions_is_refused_too():
    assert "太挤" in A.verdict(6, A.page_range(13))


def test_the_clock_caps_the_page_count():
    """40 条断言 × 20 分钟是矛盾的：时钟只够 24 页，而 40 条断言要 40 页。要说出来，不能悄悄排 40 页。"""
    rng = A.page_range(40, minutes=20)
    assert (rng["high"], rng["time_max"], rng["over"]) == (24, 24, 16)
    assert "讲不完" in A.verdict(40, rng) and "删掉 16 条" in A.verdict(40, rng)


def test_a_title_with_no_digit_cannot_pass_as_quantified():
    """这是代码能独立回答的、关于强弱的一个问题：没有数字的标题，无论怎么措辞都不是 L3。"""
    assert A.quantifiable("全球70%的成人患者未被确诊", FACTS, ["ud-70"])
    assert not A.quantifiable("漏诊是最先要处理的问题", FACTS, ["ud-70"])
    assert not A.quantifiable("全球80%的成人患者未被确诊", FACTS, ["ud-70"])
