"""presentation.v1 — the model decides the page, the code only checks what can be checked.

Two kinds of rule live here.  The first asks "could this page show something the material does not say".
The second asks "would this page read wrong even though every word is real" — a sentence that opens with a
pronoun, an attribution a comparison makes without support, a point longer than its column.  Those are refused
at the spec, before anything is drawn, so they cannot be discovered by looking at a picture afterwards.

Structure and emphasis are not tested: that is the model's judgement, not a property of the code.
"""
from __future__ import annotations

import pytest

from factdeck import presentation as P
from factdeck.presentation_render import render_deck, render_page

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
}


def item(fact, label="要点"):
    return {"facts": [fact] if isinstance(fact, str) else list(fact), "label": label}


def spec(**page) -> dict:
    base = {"id": "p1", "structure": "stat", "headline": "大部分患者没有被诊断",
            "lead": {"value": "70%", "label": "成人患者未被确诊", "from": "a"},
            "items": [item("b", "多国研究"), item("e", "中低收入国家")]}
    base.update(page)
    return {"schema_version": P.SCHEMA, "pages": [base]}


def test_a_page_is_resolved_to_the_sentences_own_words():
    page = P.check(spec(), FACTS)["pages"][0]
    assert page["lead"]["value"] == "70%" and page["lead"]["quote"] == FACTS["a"]["quote"]
    assert [i["quote"] for i in page["items"]] == [FACTS["b"]["quote"], FACTS["e"]["quote"]]
    assert [i["label"] for i in page["items"]] == ["多国研究", "中低收入国家"]
    assert page["items"][0]["page_id"] == "PDF 第 12 页"


# ---------------------------------------------- does the page say something the material does not?

def test_a_headline_number_must_exist_on_that_page():
    P.check(spec(headline="高达 70% 的患者未被确诊"), FACTS)
    with pytest.raises(P.PresentationError, match="headline 的数字在本页句子中找不到"):
        P.check(spec(headline="高达 95% 的患者未被确诊"), FACTS)


def test_a_headline_cannot_borrow_a_number_from_another_page():
    other = {**FACTS, "z": {"quote": "死亡风险高出4.3倍。", "source_id": "GOLD2026", "location": "第 9 页"}}
    with pytest.raises(P.PresentationError, match="headline 的数字"):
        P.check(spec(headline="死亡风险高出 4.3 倍"), other)


def test_the_lead_value_must_be_a_number_in_the_sentence_it_names():
    with pytest.raises(P.PresentationError, match="lead.value"):
        P.check(spec(lead={"value": "80%", "label": "未确诊", "from": "a"}), FACTS)
    with pytest.raises(P.PresentationError, match="不是该句中的数字"):
        P.check(spec(lead={"value": "70%", "label": "未确诊", "from": "d"}), FACTS)


def test_the_lead_label_is_organising_text_and_carries_no_number():
    with pytest.raises(P.PresentationError, match="lead.label 是组织文字"):
        P.check(spec(lead={"value": "70%", "label": "70% 未确诊", "from": "a"}), FACTS)


def test_an_unknown_sentence_is_refused():
    with pytest.raises(P.PresentationError, match="引用了不存在的句子"):
        P.check(spec(items=[item("nope", "无")]), FACTS)


def test_a_takeaway_that_repeats_a_point_or_the_lead_adds_nothing():
    with pytest.raises(P.PresentationError, match="takeaway 与页内某条要点是同一句"):
        P.check(spec(takeaway={"fact": "b"}), FACTS)
    with pytest.raises(P.PresentationError, match="takeaway 与主数字是同一句"):
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
        assert FACTS[it["facts"][0]]["quote"] in html and it["label"] in html
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
            "thresholds": [{"indicator": "呼吸困难评分", "op": "≥", "value": "≥5", "fact": "vas"}]}
    base.update(page)
    return {"schema_version": P.SCHEMA, "pages": [base]}


def test_a_gauge_resolves_to_the_sentence_that_states_it():
    th = P.check(figure(), FACTS)["pages"][0]["thresholds"][0]
    assert th["token"] == "≥5" and th["op"] == "≥" and th["fact"] == "vas"
    assert th["holds"] == "≥5" and th["other"] == "<5"
    assert th["clause"] == "呼吸困难视觉模拟评分≥5"


def test_a_word_comparison_is_matched_to_its_symbol():
    th = P.check(figure(thresholds=[{"indicator": "激素疗程", "op": "不超过", "value": "5天",
                                     "fact": "ster"}]), FACTS)["pages"][0]["thresholds"][0]
    assert th["op"] == "≤" and th["holds"] == "≤5天" and th["other"] == ">5天"


def test_a_gauge_may_not_widen_the_comparison_the_sentence_makes():
    # "≥5" in the source must not become ≤5, and "不超过5天" must not become <5天: the boundary would then
    # include cases the source excludes.
    with pytest.raises(P.PresentationError, match="与原文不符"):
        P.check(figure(thresholds=[{"indicator": "激素疗程", "op": "≥", "value": "5天", "fact": "ster"}]), FACTS)
    with pytest.raises(P.PresentationError, match="与原文不符"):
        P.check(figure(thresholds=[{"indicator": "呼吸困难评分", "op": "≤", "value": "≥5", "fact": "vas"}]), FACTS)


def test_a_gauge_needs_a_number_the_sentence_actually_has():
    with pytest.raises(P.PresentationError, match="不是来源句中的数字"):
        P.check(figure(thresholds=[{"indicator": "激素疗程", "op": "≤", "value": "7天", "fact": "ster"}]), FACTS)


def test_a_range_cannot_be_drawn_as_one_boundary():
    with pytest.raises(P.PresentationError, match="是一个区间"):
        P.check(figure(thresholds=[{"indicator": "未确诊比例", "op": ">", "value": "90-95%", "fact": "e"}]), FACTS)


def test_a_sentence_without_a_comparison_cannot_be_a_gauge():
    with pytest.raises(P.PresentationError, match="没有比较符"):
        P.check(figure(thresholds=[{"indicator": "未确诊患者", "op": ">", "value": "70%", "fact": "a"}]), FACTS)


def test_the_indicator_must_be_a_name_the_sentence_supports():
    with pytest.raises(P.PresentationError, match="在本页句子里找不到"):
        P.check(figure(thresholds=[{"indicator": "漏诊率", "op": "≥", "value": "≥5", "fact": "vas"}]), FACTS)


def test_one_measure_is_drawn_once():
    with pytest.raises(P.PresentationError, match="同一根量规不画两遍"):
        P.check(figure(thresholds=[
            {"indicator": "呼吸困难评分", "op": "≥", "value": "≥5", "fact": "vas"},
            {"indicator": "呼吸困难评分", "op": "<", "value": "≥5", "fact": "vas"}]), FACTS)


def test_a_threshold_page_carries_its_gauges_and_nothing_beside_them():
    # One gauge plus a point gives the point the wider column and the figure ends up smaller than the text
    # next to it.  The sentence that explains a boundary goes in takeaway, or on a page of its own.
    with pytest.raises(P.PresentationError, match="不列 items"):
        P.check(figure(items=[item("abx", "抗生素")]), FACTS)


def test_two_boundaries_can_share_a_page_and_a_third_cannot():
    # Two divisions are a figure.  Three of different units are a list drawn as stripes: the page stops being
    # about a boundary and becomes a table.  A list belongs in points.
    P.check(figure(thresholds=[
        {"indicator": "呼吸困难评分", "op": "≥", "value": "≥5", "fact": "vas"},
        {"indicator": "激素疗程", "op": "≤", "value": "5天", "fact": "ster"}]), FACTS)
    with pytest.raises(P.PresentationError, match="一页最多 2 根"):
        P.check(figure(thresholds=[
            {"indicator": "呼吸困难评分", "op": "≥", "value": "≥5", "fact": "vas"},
            {"indicator": "激素疗程", "op": "≤", "value": "5天", "fact": "ster"},
            {"indicator": "成人接种", "op": "≥", "value": "50", "fact": "age"}]), FACTS)


def test_a_figure_page_does_not_also_carry_a_lead():
    with pytest.raises(P.PresentationError, match="主数字已经在图里"):
        P.check(figure(lead={"value": "5", "label": "分界", "from": "vas"}), FACTS)




def test_a_ceiling_puts_the_band_on_the_side_the_sentence_describes():
    # ≤ holds below the boundary, so the filled half and its label sit on the left.
    page = P.check(figure(thresholds=[{"indicator": "激素疗程", "op": "≤", "value": "5天", "fact": "ster"}]),
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

def bars(*series, **page) -> dict:
    base = {"id": "b1", "structure": "stat", "lead": None,
            "figure": [{"kind": "bars", "series": [
                {"indicator": "患病率", "value": "9.7%", "fact": "b"},
                {"indicator": "未确诊比例", "value": "81%", "fact": "b"}]}]}
    if series:
        base["figure"][0]["series"] = list(series)
    base.update(page)
    return {"schema_version": P.SCHEMA, "pages": [base]}


def part_bars(*series, label=None) -> dict:
    series = list(series) or [{"indicator": "患病率", "value": "9.7%", "fact": "b"},
                              {"indicator": "未确诊比例", "value": "81%", "fact": "b"}]
    out = {"kind": "bars", "series": series}
    if label:
        out["label"] = label
    return out


def test_bars_are_measured_against_the_largest_so_length_means_something():
    series = P.check(bars(), FACTS)["pages"][0]["bars"]["series"]
    assert [x["ratio"] for x in series] == [0.1198, 1.0]
    assert series[0]["unit"] == "%" and series[0]["numeral"] == "9.7"


def test_bars_of_different_units_are_refused():
    """一根 5 天的柱和一根 70% 的柱并排，长的那根并不意味着「更多」：没有共同的刻度，长度就是假的。"""
    with pytest.raises(P.PresentationError, match="量纲不一致"):
        P.check(bars({"indicator": "疗程", "value": "5天", "fact": "ster"},
                     {"indicator": "未确诊比例", "value": "70%", "fact": "a"}), FACTS)


def test_a_bar_needs_a_number_the_sentence_has_and_a_unit_to_measure_in():
    with pytest.raises(P.PresentationError, match="不是来源句中的数字"):
        P.check(bars({"indicator": "患病率", "value": "12%", "fact": "b"},
                     {"indicator": "未确诊比例", "value": "81%", "fact": "b"}), FACTS)
    with pytest.raises(P.PresentationError, match="没有单位"):
        P.check(bars({"indicator": "协作国家", "value": "27", "fact": "b"},
                     {"indicator": "未确诊比例", "value": "81%", "fact": "b"}), FACTS)


def test_a_range_or_a_single_bar_is_not_a_comparison():
    with pytest.raises(P.PresentationError, match="是一个区间"):
        P.check(bars({"indicator": "未确诊比例", "value": "90-95%", "fact": "e"},
                     {"indicator": "患病率", "value": "9.7%", "fact": "b"}), FACTS)
    with pytest.raises(P.PresentationError, match="构不成比较"):
        P.check(bars({"indicator": "患病率", "value": "9.7%", "fact": "b"}), FACTS)


def test_bars_equal_in_length_are_not_a_comparison_either():
    with pytest.raises(P.PresentationError, match="数值都一样"):
        P.check(bars({"indicator": "患病率", "value": "9.7%", "fact": "b"},
                     {"indicator": "未确诊比例", "value": "9.7%", "fact": "b"}), FACTS)


def test_more_bars_than_a_page_can_be_read_across():
    many = [{"indicator": f"指标{k}", "value": "9.7%", "fact": "b"} for k in range(P.MAX_BARS + 1)]
    with pytest.raises(P.PresentationError, match="一页最多"):
        P.check(bars(*many), FACTS)


def test_a_page_composes_a_gauge_over_a_set_of_bars():
    spec = {"schema_version": P.SCHEMA, "pages": [{
        "id": "c1", "structure": "stat", "headline": "确诊的比例不到两成",
        "figure": [{"kind": "split", "thresholds": [
            {"indicator": "呼吸困难评分", "op": "≥", "value": "≥5", "fact": "vas"}]},
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
                {"indicator": "呼吸困难评分", "op": "≥", "value": "≥5", "fact": "vas"},
                {"indicator": "激素疗程", "op": "≤", "value": "5天", "fact": "ster"}]},
            {"kind": "split", "thresholds": [
                {"indicator": "成人接种", "op": "≥", "value": "50", "fact": "age"}]}]}]}
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
