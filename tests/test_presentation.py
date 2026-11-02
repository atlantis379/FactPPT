"""presentation.v2 — the model decides the page, the code only checks what can be checked.

Two kinds of rule live here.  The first asks "could this page show something the material does not say".
The second asks "would this page read wrong even though every word is real" — a sentence that opens with a
pronoun, an attribution a comparison makes without support, a point longer than its column.  Those are refused
at the spec, before anything is drawn, so they cannot be discovered by looking at a picture afterwards.

Structure and emphasis are not tested: that is the model's judgement, not a property of the code.
"""
from __future__ import annotations

import re

import pytest

from factdeck import presentation as P
from factdeck.lexicon import number_occurrences
from factdeck.presentation_render import _title_lines, render_deck, render_page

FACTS = {
    "a": {"quote": "全球范围内的研究表明，高达70%的慢性阻塞性肺疾病成人患者未被确诊。",
          "source_id": "GOLD2026", "location": "PDF 第 12 页"},
    "b": {"quote": "一项涵盖27国的协作研究发现，患病率为9.7%，其中81%的病例未被确诊。",
          "source_id": "GOLD2026", "location": "PDF 第 12 页"},
    "c": {"quote": "这些国家中超过90%-95%的病例未被确诊。",
          "source_id": "GOLD2026", "location": "PDF 第 13 页"},
    "e": {"quote": "在低收入和中等收入国家，超过90%-95%的病例未被确诊。",
          "source_id": "GOLD2026", "location": "PDF 第 13 页"},
    "d": {"quote": "急性加重恢复时间因人而异，最长可达4-6周。",
          "source_id": "GOLD2026", "location": "PDF 第 40 页"},
    "mild": {"quote": "轻中度患者的急性加重恢复较快，通常不需住院。",
             "source_id": "GOLD2026", "location": "PDF 第 40 页"},
    "severe": {"quote": "重度未控制患者的急性加重更频繁，恢复也更慢。",
               "source_id": "GOLD2026", "location": "PDF 第 41 页"},
    "vas": {"quote": "呼吸困难视觉模拟评分≥5",
            "source_id": "GOLD2026", "location": "PDF 第 44 页"},
    "ster": {"quote": "对于中度/重度急性加重的患者，推荐使用全身性糖皮质激素，疗程不超过5天。",
             "source_id": "GOLD2026", "location": "PDF 第 58 页"},
    "abx": {"quote": "对于有脓痰、既往肺部感染史等的患者，推荐抗生素治疗总疗程为5天。",
            "source_id": "GOLD2026", "location": "PDF 第 58 页"},
    "age": {"quote": "适用于所有≥ 50 岁及以上的成人",
            "source_id": "GOLD2026", "location": "PDF 第 71 页"},
    "sex": {"quote": "男性患者中吸烟者占70%，女性患者中吸烟者占30%。", "source_id": "S", "location": "p"},
    "both": {"quote": "其急性加重和肺炎风险分别高出15.5倍和2.8倍。", "source_id": "S", "location": "p"},
    "ceil": {"quote": "超过10%的患者死亡。", "source_id": "S", "location": "p"},
    "other": {"quote": "60%的患者接受了手术。", "source_id": "S", "location": "p"},
    "no": {"quote": "A组患者不建议使用吸入性糖皮质激素。", "source_id": "S", "location": "p"},
    "dose": {"quote": "PCV20覆盖20%的血清型。", "source_id": "S", "location": "p"},
}
HEAD = {"fact": "a", "show": "高达70%的慢性阻塞性肺疾病成人患者未被确诊"}


def plain(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


def item(fact, label="要点"):
    return {"facts": [fact] if isinstance(fact, str) else list(fact), "label": label}


def spec(**page) -> dict:
    base = {"id": "p1", "structure": "stat", "headline": HEAD,
            "lead": {"value": "高达70%", "label": "未被确诊", "from": "a"},
            "items": [item("b", "多国研究"), item("e", "中低收入国家")]}
    base.update(page)
    return {"schema_version": P.SCHEMA, "pages": [base]}


def test_a_page_is_resolved_to_the_sentences_own_words():
    page = P.check(spec(), FACTS)["pages"][0]
    assert page["lead"]["value"] == "高达70%" and page["lead"]["quote"] == FACTS["a"]["quote"]
    assert [i["quote"] for i in page["items"]] == [FACTS["b"]["quote"], FACTS["e"]["quote"]]
    assert [i["label"] for i in page["items"]] == ["多国研究", "中低收入国家"]
    assert page["items"][0]["page_id"] == "PDF 第 12 页"


# ---------------------------------------------- does the page say something the material does not?

def test_a_headline_cannot_be_written():
    """标题是页面上最大的字。「九成患者」「必须首选」都没有句子撑着，所以标题不写，只引用。"""
    with pytest.raises(P.PresentationError, match="不能直接写成文字"):
        P.check(spec(headline="九成患者不知道自己得病"), FACTS)
    with pytest.raises(P.PresentationError, match="不能直接写成文字"):
        P.check(spec(headline="阿奇霉素优于所有吸入药物，必须首选"), FACTS)


def test_a_headline_is_the_sentence_or_a_faithful_piece_of_it():
    assert P.check(spec(), FACTS)["pages"][0]["headline"] == HEAD["show"]
    for show in ("A组患者建议使用吸入性糖皮质激素", "吸入性糖皮质激素"):
        with pytest.raises(P.PresentationError, match="show"):
            P.check(spec(headline={"fact": "no", "show": show}), FACTS)


def test_a_headline_that_needs_the_sentence_before_it_is_refused():
    with pytest.raises(P.PresentationError, match="以指代开头"):
        P.check(spec(headline={"fact": "c"}), FACTS)


def test_a_synthesised_headline_stays_off_the_slide_until_a_person_confirms_it():
    ref = {"derived": "漏诊在各国都很普遍", "from": ["a", "b"]}
    res = P.check(spec(headline=ref), FACTS)
    assert res["pending"][0]["text"] == ref["derived"]
    with pytest.raises(ValueError, match="待确认"):
        render_page(res["pages"][0], page_no=1, total=1, source="s")
    done = P.check(spec(headline=ref), FACTS, confirmed={res["pending"][0]["digest"]})
    assert done["pending"] == []
    assert ref["derived"] in render_page(done["pages"][0], page_no=1, total=1, source="s")


def test_a_headline_may_mark_a_stretch_of_itself_and_nothing_else():
    head = {**HEAD, "em": "未被确诊"}
    assert P.check(spec(headline=head), FACTS)["pages"][0]["headline_em"] == ["未被确诊"]
    with pytest.raises(P.PresentationError, match="连续片段"):
        P.check(spec(headline={**HEAD, "em": "已确诊"}), FACTS)


def test_every_contract_page_has_the_slots_the_check_demands():
    """合同里的样板就是模型照抄的东西：少一个必填项，它写的每一页都会被拒。"""
    pages = P.contract()["pages"]
    for page in pages:
        for it in page.get("items", []):
            assert "label" in it
        assert isinstance(page["headline"], dict)
    assert any("derived" in page["headline"] for page in pages)


def test_the_lead_value_must_be_a_number_in_the_sentence_it_names():
    with pytest.raises(P.PresentationError, match="lead.value"):
        P.check(spec(lead={"value": "高达80%", "label": "未确诊", "from": "a"}), FACTS)
    with pytest.raises(P.PresentationError, match="不是该句中的数字"):
        P.check(spec(lead={"value": "高达70%", "label": "未确诊", "from": "d"}), FACTS)


def test_the_lead_label_is_organising_text_and_carries_no_number():
    for label in ("70% 未确诊", "七成未确诊"):
        with pytest.raises(P.PresentationError, match="lead.label 是组织文字"):
            P.check(spec(lead={"value": "高达70%", "label": label, "from": "a"}), FACTS)


def test_a_bound_shown_as_a_lead_keeps_its_word():
    """「超过10%」写成 10%，读者读到的是一个原文没有给出的确切数。"""
    with pytest.raises(P.PresentationError, match="丢了原文的限定词"):
        P.check(spec(lead={"value": "10%", "label": "死亡比例", "from": "ceil"}), FACTS)
    page = P.check(spec(lead={"value": "超过10%", "label": "死亡比例", "from": "ceil"}), FACTS)["pages"][0]
    assert page["lead"]["value"] == "超过10%"


def test_an_unknown_sentence_is_refused():
    with pytest.raises(P.PresentationError, match="引用了不存在的句子"):
        P.check(spec(items=[item("nope", "无")]), FACTS)


def test_a_takeaway_that_repeats_a_point_or_the_lead_adds_nothing():
    with pytest.raises(P.PresentationError, match="takeaway 与页内某条要点是同一句"):
        P.check(spec(takeaway={"fact": "b"}), FACTS)
    with pytest.raises(P.PresentationError, match="takeaway 与主数字是同一句"):
        P.check(spec(headline=None, takeaway={"fact": "a"}), FACTS)
    with pytest.raises(P.PresentationError, match="takeaway 与标题是同一句"):
        P.check(spec(takeaway={"fact": "a"}), FACTS)


# ------------------------------------ does the page read right even though every word is real?

def test_a_sentence_that_opens_with_a_pronoun_is_refused_alone():
    """这句「这些国家中超过90%-95%的病例未被确诊」没有点名任何国家：单独放在页面上就是残句。"""
    with pytest.raises(P.PresentationError, match="以指代开头"):
        P.check(spec(items=[item("c", "中低收入国家")]), FACTS)


def test_the_pronoun_sentence_is_accepted_once_its_context_comes_with_it():
    page = P.check(spec(items=[item(["b", "c"], "中低收入国家")]), FACTS)["pages"][0]
    assert page["items"][0]["quote"] == FACTS["b"]["quote"] + FACTS["c"]["quote"]


def test_every_point_needs_a_label_to_read_before_the_sentence():
    with pytest.raises(P.PresentationError, match="须给出 label"):
        P.check(spec(items=[{"facts": ["b"]}]), FACTS)


def test_two_points_may_not_share_a_label():
    with pytest.raises(P.PresentationError, match="label 与同页其它条重复"):
        P.check(spec(items=[item("b", "相同"), item("e", "相同")]), FACTS)


def test_a_point_longer_than_its_column_is_refused_before_drawing():
    long_fact = {**FACTS, "l": {"quote": "研究表明，" + "这是一句很长很长的说明文字" * 6,
                                "source_id": "S", "location": "p"}}
    with pytest.raises(P.PresentationError, match="每栏最多放"):
        P.check(spec(items=[item("l", "长句")]), long_fact)


def test_a_comparison_may_not_put_a_sentence_on_a_side_it_never_names():
    """恢复时间那句没有提轻中度患者；放到「轻中度」一栏，页面就替原文作了它没有的归属。"""
    cmp_spec = spec(structure="compare", lead=None, labels=["重度未控制", "轻中度"],
                    items=[item("severe", "加重频繁"), item("d", "恢复时间")])
    with pytest.raises(P.PresentationError, match="没有提到「轻中度」"):
        P.check(cmp_spec, FACTS)


def test_a_comparison_whose_sides_are_named_by_their_sentences_passes():
    cmp_spec = spec(structure="compare", lead=None, labels=["重度未控制", "轻中度"],
                    items=[item("severe", "加重频繁"), item("mild", "恢复较快")])
    page = P.check(cmp_spec, FACTS)["pages"][0]
    assert page["labels"] == ["重度未控制", "轻中度"]


def test_a_comparison_must_name_its_two_sides():
    with pytest.raises(P.PresentationError, match="须给出 labels"):
        P.check(spec(structure="compare", lead=None,
                     items=[item("severe", "加重频繁"), item("mild", "恢复较快")]), FACTS)


def test_only_a_comparison_has_side_labels():
    with pytest.raises(P.PresentationError, match="只有 compare 有 labels"):
        P.check(spec(labels=["左", "右"]), FACTS)


def test_an_unknown_structure_and_slot_counts_are_refused():
    with pytest.raises(P.PresentationError, match="structure 须为"):
        P.check(spec(structure="poster"), FACTS)
    with pytest.raises(P.PresentationError, match="items 须为"):
        P.check(spec(structure="points", lead=None, items=[item("b")]), FACTS)


def test_section_label_is_text_without_numbers():
    P.check(spec(section="疾病负担"), FACTS)
    with pytest.raises(P.PresentationError, match="section 是组织文字"):
        P.check(spec(section="2026 年更新"), FACTS)


# ------------------------------------------------------------------------------------ rendering

@pytest.mark.parametrize("structure,items,labels", [
    ("points", [item("a", "总体"), item("b", "多国"), item("e", "中低收入")], None),
    ("compare", [item("severe", "加重频繁"), item("mild", "恢复较快")], ["重度未控制", "轻中度"]),
    ("steps", [item("a", "发现"), item("b", "研究"), item("e", "结论")], None),
])
def test_every_structure_renders_the_sentences_and_their_labels(structure, items, labels):
    page = P.check(spec(structure=structure, lead=None, items=items, labels=labels), FACTS)["pages"][0]
    html = render_page(page, page_no=1, total=1, source="来源：GOLD 2026")
    for it in items:
        assert FACTS[it["facts"][0]]["quote"] in plain(html) and it["label"] in html
    assert "1 / 1" in html and "来源：GOLD 2026" in html


def test_a_deck_numbers_its_pages_and_carries_its_sections():
    pages = P.check({"schema_version": P.SCHEMA, "pages": [
        {**spec()["pages"][0], "section": "疾病负担"},
        {**spec(id="p2", structure="points", lead=None,
                items=[item("a", "总体"), item("b", "多国"), item("e", "中低收入")])["pages"][0],
         "section": "治疗"},
    ]}, FACTS)["pages"]
    html = render_deck(pages, source="来源：GOLD 2026")
    assert html.count('class="slide"') == 2
    assert "疾病负担" in html and "治疗" in html and "2 / 2" in html


# ------------------------------------------------------------------- a figure the model asks for
# A page may declare the visual form its argument needs.  Declaring it is judgement; meeting it is a fact the
# code checks against the sentences — so a chart is never drawn from material that cannot fill it.

def figure(**page) -> dict:
    base = {"id": "f1", "structure": "stat", "form": "threshold", "lead": None,
            "thresholds": [{"indicator": "视觉模拟评分", "op": "≥", "value": "≥5", "fact": "vas"}]}
    base.update(page)
    return {"schema_version": P.SCHEMA, "pages": [base]}


def test_a_gauge_resolves_to_the_sentence_that_states_it():
    th = P.check(figure(), FACTS)["pages"][0]["thresholds"][0]
    assert th["token"] == "≥5" and th["op"] == "≥" and th["fact"] == "vas"
    assert th["holds"] == "≥5" and th["other"] == "<5"
    assert th["clause"] == "呼吸困难视觉模拟评分≥5"


def test_a_word_comparison_is_matched_to_its_symbol():
    th = P.check(figure(thresholds=[{"indicator": "疗程", "op": "不超过", "value": "5天",
                                     "fact": "ster"}]), FACTS)["pages"][0]["thresholds"][0]
    assert th["op"] == "≤" and th["holds"] == "≤5天" and th["other"] == ">5天"


def test_a_gauge_may_not_widen_the_comparison_the_sentence_makes():
    # "≥5" in the source must not become ≤5, and "不超过5天" must not become <5天: the boundary would then
    # include cases the source excludes.
    with pytest.raises(P.PresentationError, match="与原文不符"):
        P.check(figure(thresholds=[{"indicator": "疗程", "op": "≥", "value": "5天", "fact": "ster"}]), FACTS)
    with pytest.raises(P.PresentationError, match="与原文不符"):
        P.check(figure(thresholds=[{"indicator": "视觉模拟评分", "op": "≤", "value": "≥5", "fact": "vas"}]), FACTS)


def test_a_gauge_needs_a_number_the_sentence_actually_has():
    with pytest.raises(P.PresentationError, match="不是来源句中的数字"):
        P.check(figure(thresholds=[{"indicator": "疗程", "op": "≤", "value": "7天", "fact": "ster"}]), FACTS)


def test_a_range_cannot_be_drawn_as_one_boundary():
    with pytest.raises(P.PresentationError, match="是一个区间"):
        P.check(figure(thresholds=[{"indicator": "病例", "op": ">", "value": "90-95%", "fact": "e"}]), FACTS)


def test_a_sentence_without_a_comparison_cannot_be_a_gauge():
    with pytest.raises(P.PresentationError, match="没有比较符"):
        P.check(figure(thresholds=[{"indicator": "成人患者", "op": ">", "value": "70%", "fact": "a"}]), FACTS)


def test_the_indicator_must_be_a_name_the_sentence_supports():
    with pytest.raises(P.PresentationError, match="在本页句子里找不到"):
        P.check(figure(thresholds=[{"indicator": "漏诊率", "op": "≥", "value": "≥5", "fact": "vas"}]), FACTS)


def test_one_measure_is_drawn_once():
    with pytest.raises(P.PresentationError, match="同一根量规不画两遍"):
        P.check(figure(thresholds=[
            {"indicator": "视觉模拟评分", "op": "≥", "value": "≥5", "fact": "vas"},
            {"indicator": "视觉模拟评分", "op": "<", "value": "≥5", "fact": "vas"}]), FACTS)


def test_a_threshold_page_carries_its_gauges_and_nothing_beside_them():
    # One gauge plus a point gives the point the wider column and the figure ends up smaller than the text
    # next to it.  The sentence that explains a boundary goes in takeaway, or on a page of its own.
    with pytest.raises(P.PresentationError, match="不列 items"):
        P.check(figure(items=[item("abx", "抗生素")]), FACTS)


def test_two_boundaries_can_share_a_page_and_a_third_cannot():
    # Two divisions are a figure.  Three of different units are a list drawn as stripes: the page stops being
    # about a boundary and becomes a table.  A list belongs in points.
    P.check(figure(thresholds=[
        {"indicator": "视觉模拟评分", "op": "≥", "value": "≥5", "fact": "vas"},
        {"indicator": "疗程", "op": "≤", "value": "5天", "fact": "ster"}]), FACTS)
    with pytest.raises(P.PresentationError, match="一页最多 2 根"):
        P.check(figure(thresholds=[
            {"indicator": "视觉模拟评分", "op": "≥", "value": "≥5", "fact": "vas"},
            {"indicator": "疗程", "op": "≤", "value": "5天", "fact": "ster"},
            {"indicator": "成人", "op": "≥", "value": "50", "fact": "age"}]), FACTS)


def test_a_figure_page_does_not_also_carry_a_lead():
    with pytest.raises(P.PresentationError, match="主数字已经在图里"):
        P.check(figure(lead={"value": "5", "label": "分界", "from": "vas"}), FACTS)




def test_a_ceiling_puts_the_band_on_the_side_the_sentence_describes():
    # ≤ holds below the boundary, so the filled half and its label sit on the left.
    page = P.check(figure(thresholds=[{"indicator": "疗程", "op": "≤", "value": "5天", "fact": "ster"}]),
                   FACTS)["pages"][0]
    html = render_page(page, page_no=1, total=1, source="来源：GOLD 2026")
    assert 'justify-content:flex-start' in html and '<span class="hold">≤5天</span>' in html
    assert "疗程不超过5天" in html


def test_a_floor_puts_the_band_on_the_other_side():
    # ≥ holds above the boundary: filled half on the right, and its label with it.
    page = P.check(figure(), FACTS)["pages"][0]
    html = render_page(page, page_no=1, total=1, source="来源：GOLD 2026")
    assert 'justify-content:flex-end' in html and '<span class="hold">≥5</span>' in html


# ---------------------------------------------------------------- a figure the model composes
# A page's picture is not one of seven fixed shells: the model says which parts it is made of, in what order, and
# each part is checked against the sentences it draws from.  Geometry stays with the code.

MEN = {"indicator": "男性", "value": "70%", "fact": "sex", "base": "吸烟者"}
WOMEN = {"indicator": "女性", "value": "30%", "fact": "sex", "base": "吸烟者"}


def bars(*series, **page) -> dict:
    base = {"id": "b1", "structure": "stat", "lead": None,
            "figure": [{"kind": "bars", "series": list(series) or [MEN, WOMEN]}]}
    base.update(page)
    return {"schema_version": P.SCHEMA, "pages": [base]}


def part_bars(*series, label=None) -> dict:
    out = {"kind": "bars", "series": list(series) or [MEN, WOMEN]}
    if label:
        out["label"] = label
    return out


def test_bars_are_measured_against_the_largest_so_length_means_something():
    series = P.check(bars(), FACTS)["pages"][0]["bars"]["series"]
    assert [x["ratio"] for x in series] == [1.0, 0.4286]
    assert series[0]["unit"] == "%" and series[0]["numeral"] == "70"


def test_a_bar_takes_the_number_its_own_clause_gives_it():
    """男女画反：两个数都在句子里，两个词也都在句子里，错的只是谁配谁。"""
    with pytest.raises(P.PresentationError, match="顺序相反"):
        P.check(bars({**MEN, "value": "30%"}, {**WOMEN, "value": "70%"}), FACTS)
    with pytest.raises(P.PresentationError, match="不在一个分句"):
        P.check(bars({**MEN, "value": "30%"}, {"indicator": "吸烟者", "value": "60%", "fact": "smoke", "base": "吸烟者"}),
                {**FACTS, "smoke": {"quote": "吸烟者占60%的人群。", "source_id": "S", "location": "p"}})


def test_respectively_binds_by_order_when_every_number_is_drawn():
    series = [{"indicator": "急性加重", "value": "15.5倍", "fact": "both"},
              {"indicator": "肺炎", "value": "2.8倍", "fact": "both"}]
    assert P.check(bars(*series), FACTS)["pages"][0]["bars"]["series"][1]["amount"] == 2.8
    with pytest.raises(P.PresentationError, match="顺序相反"):
        P.check(bars({**series[0], "value": "2.8倍"}, {**series[1], "value": "15.5倍"}), FACTS)
    with pytest.raises(P.PresentationError, match="不在一个分句"):
        P.check(bars(series[1], {"indicator": "死亡", "value": "4.3倍", "fact": "death"}),
                {**FACTS, "death": {"quote": "死亡风险高出4.3倍。", "source_id": "S", "location": "p"}})


def test_a_bound_is_not_a_bar():
    with pytest.raises(P.PresentationError, match="界值"):
        P.check(bars({"indicator": "患者", "value": "10%", "fact": "ceil", "base": "患者"},
                     {"indicator": "手术", "value": "60%", "fact": "other", "base": "患者"}), FACTS)


def test_percentages_share_a_scale_only_over_one_denominator():
    a70 = {"indicator": "未被确诊", "value": "70%", "fact": "a", "base": "成人患者"}
    b81 = {"indicator": "未被确诊", "value": "81%", "fact": "b", "base": "病例"}
    with pytest.raises(P.PresentationError, match="分母不同"):
        P.check(bars(a70, {**b81, "indicator": "病例"}), FACTS)
    with pytest.raises(P.PresentationError, match="base"):
        P.check(bars({**MEN, "base": None}, WOMEN), FACTS)
    with pytest.raises(P.PresentationError, match="base"):
        P.check(bars({**MEN, "base": "原文没有的词"}, WOMEN), FACTS)


def test_a_name_with_a_digit_is_not_a_number_to_draw():
    hits = number_occurrences(FACTS["dose"]["quote"])
    assert [h["token"] for h in hits] == ["20%"]


def test_a_number_shaped_like_a_year_is_a_year_only_without_another_unit():
    assert [h["token"] for h in number_occurrences("2024年共纳入2000例，随访2000小时。")] == ["2000例", "2000小时"]


def test_every_number_in_a_clause_is_found():
    assert [h["token"] for h in number_occurrences(FACTS["both"]["quote"])] == ["15.5倍", "2.8倍"]


def test_bars_of_different_units_are_refused():
    """一根 5 天的柱和一根 70% 的柱并排，长的那根并不意味着「更多」：没有共同的刻度，长度就是假的。"""
    with pytest.raises(P.PresentationError, match="量纲不一致"):
        P.check(bars({"indicator": "疗程", "value": "5天", "fact": "abx"}, MEN), FACTS)


def test_a_bar_needs_a_number_the_sentence_has_and_a_unit_to_measure_in():
    with pytest.raises(P.PresentationError, match="不是来源句中的数字"):
        P.check(bars({**MEN, "value": "12%"}, WOMEN), FACTS)
    with pytest.raises(P.PresentationError, match="没有单位"):
        P.check(bars({"indicator": "国", "value": "27", "fact": "b"}, MEN), FACTS)


def test_a_range_or_a_single_bar_is_not_a_comparison():
    with pytest.raises(P.PresentationError, match="是一个区间"):
        P.check(bars({"indicator": "病例", "value": "90-95%", "fact": "e", "base": "病例"}, MEN), FACTS)
    with pytest.raises(P.PresentationError, match="构不成比较"):
        P.check(bars(MEN), FACTS)


def test_bars_equal_in_length_are_not_a_comparison_either():
    with pytest.raises(P.PresentationError, match="数值都一样"):
        P.check(bars(MEN, {"indicator": "成人患者", "value": "70%", "fact": "a", "base": "成人患者"}), FACTS)


def test_more_bars_than_a_page_can_be_read_across():
    many = [{"indicator": f"指标{k}", "value": "9.7%", "fact": "b"} for k in range(P.MAX_BARS + 1)]
    with pytest.raises(P.PresentationError, match="一页最多"):
        P.check(bars(*many), FACTS)


def test_a_page_composes_a_gauge_over_a_set_of_bars():
    spec = {"schema_version": P.SCHEMA, "pages": [{
        "id": "c1", "structure": "stat", "headline": HEAD,
        "figure": [{"kind": "split", "thresholds": [
            {"indicator": "视觉模拟评分", "op": "≥", "value": "≥5", "fact": "vas"}]},
            part_bars()]}]}
    page = P.check(spec, FACTS)["pages"][0]
    assert [f["kind"] for f in page["figure"]] == ["split", "bars"] and page["form"] == "composite"
    html = render_page(page, page_no=1, total=1, source="来源：GOLD 2026")
    assert 'class="figs"' in html and 'class="th"' in html and 'class="br-fill"' in html


def test_two_groups_of_bars_have_to_say_which_is_which():
    spec = {"schema_version": P.SCHEMA, "pages": [{
        "id": "c2", "structure": "stat", "lead": None,
        "figure": [part_bars(), part_bars()]}]}
    with pytest.raises(P.PresentationError, match="须给出 label"):
        P.check(spec, FACTS)
    spec["pages"][0]["figure"] = [part_bars(label="全国"), part_bars(label="基层")]
    P.check(spec, FACTS)


def test_two_parts_may_not_add_up_to_a_third_gauge():
    # The two-gauge ceiling is about the page, not the part: 2 + 1 is still a table.
    spec = {"schema_version": P.SCHEMA, "pages": [{
        "id": "c3", "structure": "stat", "lead": None, "figure": [
            {"kind": "split", "thresholds": [
                {"indicator": "视觉模拟评分", "op": "≥", "value": "≥5", "fact": "vas"},
                {"indicator": "疗程", "op": "≤", "value": "5天", "fact": "ster"}]},
            {"kind": "split", "thresholds": [
                {"indicator": "成人", "op": "≥", "value": "50", "fact": "age"}]}]}]}
    with pytest.raises(P.PresentationError, match="一页最多 2 根"):
        P.check(spec, FACTS)


def test_a_part_kind_must_be_one_the_renderer_knows():
    spec = {"schema_version": P.SCHEMA, "pages": [{
        "id": "c4", "structure": "stat", "lead": None,
        "figure": [{"kind": "pie", "series": []}]}]}
    with pytest.raises(P.PresentationError, match="kind 须为"):
        P.check(spec, FACTS)


def test_more_parts_than_a_page_can_hold_are_refused():
    spec = {"schema_version": P.SCHEMA, "pages": [{
        "id": "c5", "structure": "stat", "lead": None,
        "figure": [part_bars(), part_bars(label="全国"), part_bars(label="基层"), part_bars(label="社区")]}]}
    with pytest.raises(P.PresentationError, match="一页最多 .* 部分"):
        P.check(spec, FACTS)


# ------------------------------------------------------------------------ which points lead
# A page of four equal cards says four equal things.  The model may say which of them carry the page; the code
# owns how much bigger a core point is set.

def points_page(*weights, structure="points") -> dict:
    facts = ["a", "b", "e", "mild"][:len(weights)]
    labels = ["总体", "多国", "中低收入", "恢复"][:len(weights)]
    items = []
    for k, w in enumerate(weights):
        it = {"facts": [facts[k]], "label": labels[k]}
        if w:
            it["weight"] = w
        items.append(it)
    return {"schema_version": P.SCHEMA, "pages": [{"id": "w1", "structure": structure, "items": items}]}


def test_a_marked_point_is_set_a_step_above_the_ones_that_support_it():
    page = P.check(points_page("core", "support", "support"), FACTS)["pages"][0]
    assert page["weights"] == ["core", "support", "support"]
    html = render_page(page, page_no=1, total=1, source="来源：GOLD 2026")
    assert '<li class="core">' in html and "font-size:24px" in html


def test_unmarked_points_stay_equal():
    page = P.check(points_page(None, None, None), FACTS)["pages"][0]
    assert page["weights"] == ["support", "support", "support"]
    assert 'class="core"' not in render_page(page, page_no=1, total=1, source="来源：GOLD 2026")


def test_marking_only_half_the_points_leaves_the_rest_to_guesswork():
    with pytest.raises(P.PresentationError, match="只标一半"):
        P.check(points_page("core", None, None), FACTS)


def test_a_page_where_everything_is_core_has_no_core():
    with pytest.raises(P.PresentationError, match="全是 core"):
        P.check(points_page("core", "core", "core"), FACTS)
    with pytest.raises(P.PresentationError, match="最多 2 条"):
        P.check(points_page("core", "core", "core", "support"), FACTS)


def test_only_the_structure_that_needs_weight_takes_one():
    """steps 已经有编号、compare 已经有两栏：再标主次就是第二套指令，两套会打架。"""
    with pytest.raises(P.PresentationError, match="不标 weight"):
        P.check(points_page("core", "support", "support", structure="steps"), FACTS)


def test_a_weight_must_be_one_of_the_two_words():
    with pytest.raises(P.PresentationError, match="weight 须为"):
        P.check(points_page("main", "support", "support"), FACTS)


# -------------------------------------------------------------------------- room to breathe
def test_a_page_may_declare_itself_a_hero_page():
    assert P.check(spec(role="hero"), FACTS)["pages"][0]["role"] == "hero"
    assert P.check(spec(), FACTS)["pages"][0]["role"] == "supporting"
    with pytest.raises(P.PresentationError, match="role 须为"):
        P.check(spec(role="poster"), FACTS)


# ---------------------------------------------------------------------------------------- the shell
# These hold for any material: nothing below knows what a page is about.

def test_a_short_title_stays_on_one_line_and_a_long_one_breaks_at_a_clause():
    assert _title_lines("甲乙丙丁") == ["甲乙丙丁"]
    left, right = "一" * 20 + "，", "二" * 22
    assert _title_lines(left + right) == [left, right]


def test_a_long_title_without_a_clause_mark_never_breaks_inside_a_latin_word():
    text = "一" * 24 + "ABCDEFGHIJKLMNOPQRST" + "二" * 16
    lines = _title_lines(text)
    assert "".join(lines) == text and len(lines) == 2
    assert not (lines[0][-1].isascii() and lines[1][0].isascii())


def test_the_body_starts_where_the_title_ends():
    one = render_page(P.check(spec(), FACTS)["pages"][0], page_no=1, total=1, source="s")
    two = render_page(P.check(spec(headline={"fact": "ster"}), FACTS)["pages"][0], page_no=1, total=1, source="s")
    top = lambda html: int(re.search(r'class="main" style="top:(\d+)px', html).group(1))
    assert top(two) > top(one)


def test_a_title_drops_its_full_stop_and_keeps_its_words():
    html = render_page(P.check(spec(headline={"fact": "ster"}), FACTS)["pages"][0], page_no=1, total=1, source="s")
    title = plain(re.search(r"<h1.*?</h1>", html).group(0))
    assert title == FACTS["ster"]["quote"].rstrip("。")


def test_numbers_are_marked_with_their_qualifier_and_the_words_stay_the_same():
    assert P.emphasis_spans("超过70%的患者") == [(0, 5)]
    assert P.emphasis_spans("PCV20覆盖20%") == [(7, 10)]
    html = render_page(P.check(spec(structure="points", lead=None, items=[item("a"), item("b", "b"), item("e", "e")]),
                               FACTS)["pages"][0], page_no=1, total=1, source="s")
    assert '<span class="num">高达70%</span>' in html and FACTS["a"]["quote"] in plain(html)


def test_a_qualified_lead_is_set_with_its_word_small_beside_it():
    html = render_page(P.check(spec(), FACTS)["pages"][0], page_no=1, total=1, source="s")
    assert '<span class="stat-pre">高达</span>70<span class="stat-unit">%</span>' in html


def test_parallel_points_are_rows_that_share_the_height():
    page = P.check(spec(structure="points", lead=None, items=[item("a", "一"), item("b", "二"), item("e", "三")]), FACTS)
    html = render_page(page["pages"][0], page_no=1, total=1, source="s")
    assert 'grid-template-rows:repeat(3,1fr)' in html and html.count('class="row2"') == 3
