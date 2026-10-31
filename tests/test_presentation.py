"""presentation.v1 — the model decides the page, the code only checks what can be checked.

Every rule asserted here answers one question: could this page show something the material does not say?
Structure and emphasis are not tested — that is the model's judgement, not a property of the code.
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
    "d": {"quote": "急性加重恢复时间因人而异，最长可达4-6周。",
          "source_id": "GOLD2026", "location": "PDF 第 40 页"},
}


def spec(**page) -> dict:
    base = {"id": "p1", "structure": "stat", "headline": "大部分患者没有被诊断",
            "lead": {"value": "70%", "label": "成人患者未被确诊", "from": "a"},
            "items": [{"fact": "b"}, {"fact": "c"}]}
    base.update(page)
    return {"schema_version": P.SCHEMA, "pages": [base]}


def test_a_page_is_resolved_to_the_sentences_own_words():
    out = P.check(spec(), FACTS)
    page = out["pages"][0]
    assert page["lead"]["value"] == "70%" and page["lead"]["quote"] == FACTS["a"]["quote"]
    assert [i["quote"] for i in page["items"]] == [FACTS["b"]["quote"], FACTS["c"]["quote"]]
    assert page["items"][0]["page_id"] == "PDF 第 12 页"


def test_a_headline_number_must_exist_on_that_page():
    P.check(spec(headline="高达 70% 的患者未被确诊"), FACTS)          # on the page, accepted
    with pytest.raises(P.PresentationError, match="headline 的数字在本页句子中找不到"):
        P.check(spec(headline="高达 95% 的患者未被确诊"), FACTS)      # 95% is not in any sentence here


def test_a_headline_cannot_borrow_a_number_from_another_page():
    other = {**FACTS, "z": {"quote": "死亡风险高出4.3倍。", "source_id": "GOLD2026", "location": "第 9 页"}}
    with pytest.raises(P.PresentationError, match="headline 的数字"):
        P.check(spec(headline="死亡风险高出 4.3 倍"), other)          # true in the material, absent from this page


def test_the_lead_value_must_be_a_number_in_the_sentence_it_names():
    with pytest.raises(P.PresentationError, match="lead.value"):
        P.check(spec(lead={"value": "80%", "label": "未确诊", "from": "a"}), FACTS)
    with pytest.raises(P.PresentationError, match="不是该句中的数字"):
        P.check(spec(lead={"value": "70%", "label": "未确诊", "from": "d"}), FACTS)   # d says 4-6周, not 70%
    P.check(spec(lead={"value": "4-6周", "label": "恢复时间", "from": "d"}), FACTS)   # the lead may cite any page sentence


def test_the_lead_label_is_organising_text_and_carries_no_number():
    with pytest.raises(P.PresentationError, match="lead.label 是组织文字"):
        P.check(spec(lead={"value": "70%", "label": "70% 未确诊", "from": "a"}), FACTS)


def test_an_unknown_sentence_is_refused():
    with pytest.raises(P.PresentationError, match="引用了不存在的句子"):
        P.check(spec(items=[{"fact": "nope"}]), FACTS)


def test_slot_counts_belong_to_the_structure():
    with pytest.raises(P.PresentationError, match="items 须为"):
        P.check(spec(structure="points", lead=None, items=[{"fact": "b"}]), FACTS)     # points needs 3-6
    P.check(spec(structure="points", lead=None, items=[{"fact": "a"}, {"fact": "b"}, {"fact": "c"}]), FACTS)


def test_an_unknown_structure_is_refused():
    with pytest.raises(P.PresentationError, match="structure 须为"):
        P.check(spec(structure="poster"), FACTS)


def test_a_takeaway_that_repeats_a_point_adds_nothing():
    with pytest.raises(P.PresentationError, match="takeaway 与页内某条要点是同一句"):
        P.check(spec(takeaway={"fact": "b"}), FACTS)


def test_a_takeaway_has_to_fit_one_line():
    long_fact = {**FACTS, "long": {"quote": "这是一句很长的话" * 8, "source_id": "S", "location": "p"}}
    with pytest.raises(P.PresentationError, match="超过一行的"):
        P.check(spec(takeaway={"fact": "long"}), long_fact)


def test_only_a_comparison_has_side_labels():
    P.check(spec(structure="compare", lead=None, labels=["重度", "轻中度"],
                 items=[{"fact": "a"}, {"fact": "b"}, {"fact": "c"}]), FACTS)
    with pytest.raises(P.PresentationError, match="只有 compare 有 labels"):
        P.check(spec(labels=["左", "右"]), FACTS)


def test_section_label_is_text_without_numbers():
    P.check(spec(section="疾病负担"), FACTS)
    with pytest.raises(P.PresentationError, match="section 是组织文字"):
        P.check(spec(section="2026 年更新"), FACTS)


@pytest.mark.parametrize("structure,items", [
    ("points", [{"fact": "a"}, {"fact": "b"}, {"fact": "c"}]),
    ("compare", [{"fact": "a"}, {"fact": "b"}, {"fact": "c"}]),
    ("steps", [{"fact": "a"}, {"fact": "b"}, {"fact": "c"}]),
])
def test_every_structure_renders_the_sentences_verbatim(structure, items):
    page = P.check(spec(structure=structure, lead=None, items=items), FACTS)["pages"][0]
    html = render_page(page, page_no=1, total=1, source="来源：GOLD 2026")
    for i in items:
        assert FACTS[i["fact"]]["quote"].replace("<", "&lt;") in html
    assert "1 / 1" in html and "来源：GOLD 2026" in html


def test_a_deck_numbers_its_pages_and_carries_its_sections():
    pages = P.check({"schema_version": P.SCHEMA, "pages": [
        {**spec()["pages"][0], "section": "疾病负担"},
        {**spec(id="p2", structure="points", lead=None,
                items=[{"fact": "a"}, {"fact": "b"}, {"fact": "c"}])["pages"][0], "section": "治疗"},
    ]}, FACTS)["pages"]
    html = render_deck(pages, source="来源：GOLD 2026")
    assert html.count('class="slide"') == 2
    assert "疾病负担" in html and "治疗" in html and "2 / 2" in html
