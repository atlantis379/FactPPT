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
