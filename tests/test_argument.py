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
    "ulam": {"quote": "对于稳定期症状明显的患者，首选LABA+LAMA联合治疗。"},
    "pcv": {"quote": "我们推荐慢性阻塞性肺疾病患者使用PCV20或PCV21。"},
    "cit": {"quote": "因其会对健康状况产生负面影响，加剧气流阻塞、(486) 疾病进展、住院及再入院率，并增加死亡风险。"},
    "mo": {"quote": "建议所有年满 ≥ 6 个月且无禁忌症的人群每年常规接种流感疫苗。"},
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
        ok(claim(grade="L1", text="漏诊比误诊更常见"))
    with pytest.raises(A.ArgumentError, match="须声明 grade"):
        ok(claim(grade="strong"))


def test_a_directed_claim_is_a_page_without_any_number():
    """指南最该讲的是“怎么治”，那句话常常没有数字。定向（L2）用逐字 scope 代替数字，也能成页。"""
    a = ok(claim(grade="L2", text="稳定期首选LABA+LAMA联合治疗", evidence=["ulam"],
                 scope="稳定期症状明显的患者"))["claims"][1]
    assert a["grade"] == "L2" and a["scope"] == "稳定期症状明显的患者" and a["numbers"] == set()


def test_a_directed_claim_without_a_scope_is_refused():
    """「首选联合治疗」没说给谁：没有对象的断言既不能核对，也放不上页面。"""
    with pytest.raises(A.ArgumentError, match="须给出 scope"):
        ok(claim(grade="L2", text="稳定期首选联合治疗", evidence=["ulam"]))


def test_a_number_forces_the_grade_up_never_down():
    """句中有数还声明成 L2，是两处里错了一处：要么把等级提到 L3，要么把数删掉。"""
    with pytest.raises(A.ArgumentError, match="句中有数字"):
        ok(claim(grade="L2", text="稳定期的患者中 70% 未被确诊", evidence=["ud-70"],
                 scope="稳定期症状明显的患者"))


def test_a_number_must_be_in_the_sentence_it_cites():
    with pytest.raises(A.ArgumentError, match="找不到：80"):
        ok(claim(text="全球80%的成人患者未被确诊"))


def test_the_unit_is_checked_apart_from_the_digits():
    """数字一样、单位换掉，意思全变：70% 写成 70 例，读者读到的是另一个事实。"""
    with pytest.raises(A.ArgumentError, match="单位在来源句里没有：例"):
        ok(claim(text="全球70例成人患者未被确诊"))


def test_a_scope_has_to_be_the_source_wording():
    """适用范围也是事实，不能改写：照抄那句里的写法，改动一个字就不是出处了。"""
    with pytest.raises(A.ArgumentError, match="不是证据句的原文"):
        ok(claim(grade="L4", scope="在低收入国家超过70%"))
    with pytest.raises(A.ArgumentError, match="须给出 scope"):
        ok(claim(grade="L4"))
    assert ok(claim(grade="L4", scope="高达70%的慢性阻塞性肺疾病成人患者"))["claims"][1]["grade"] == "L4"


def test_a_scope_too_short_to_say_anything_is_refused():
    with pytest.raises(A.ArgumentError, match="太短"):
        ok(claim(grade="L4", scope="部分"))


# ------------------------------------------------------------------------ names that contain numerals

def test_a_product_name_is_not_a_quantity():
    """「推荐 PCV20 或 PCV21」里的数是名字。它必须写对，但它没有量化任何东西，不能把一句推荐抬成 L3。"""
    a = ok(claim(grade="L2", text="推荐COPD患者使用PCV20或PCV21", evidence=["pcv"],
                 scope="慢性阻塞性肺疾病患者"))["claims"][1]
    assert a["grade"] == "L2" and a["numbers"] == {"20", "21"}


def test_a_misnamed_product_is_still_refused():
    """名字不算量化，不等于写错名字不要紧：PCV13 不在原文里，照样拒。"""
    with pytest.raises(A.ArgumentError, match="找不到：13"):
        ok(claim(grade="L2", text="推荐COPD患者使用PCV13", evidence=["pcv"],
                 scope="慢性阻塞性肺疾病患者"))


def test_names_and_quantities_are_told_apart():
    assert A.data_numbers("支气管扩张后 FEV1/FVC 低于 0.7") == {"0.7"}
    assert A.data_numbers("推荐 PCV20 或 PCV21") == set()
    assert A.data_numbers("GOLD 2026 年报告") == set()
    assert {"15.5", "4.3"} <= A.data_numbers("风险高出 15.5 倍，死亡高出 4.3 倍")


def test_a_citation_number_is_apparatus_not_wording():
    """证据句里夹着 (486)，它把要照抄的短语切成两半；而 486 本身也绝不能变成一条可引用的数据。"""
    a = ok(claim(grade="L2", text="加重会加剧气流阻塞与住院风险", evidence=["cit"],
                 scope="加剧气流阻塞、疾病进展、住院及再入院率"))["claims"][1]
    assert a["grade"] == "L2"
    assert "486" not in A.numbers(FACTS["cit"]["quote"])


def test_a_counter_is_not_the_unit():
    """「6 个月」的单位是月，不是个：把个读成单位，最普通的一句话就会被判成换了单位。"""
    ok(claim(grade="L3", text="6月龄以上人群每年接种流感疫苗", evidence=["mo"]))


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
