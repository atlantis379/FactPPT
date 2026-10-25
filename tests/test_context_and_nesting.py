"""Sentence context left off a page, nested table rows, and transcribed parent cells (decisions of 2026-10-18)."""
from dataclasses import asdict

import pytest

from factdeck import facts as fx
from factdeck.deck import check
from factdeck.ingest import IngestError, transcription_units
from factdeck.lexicon import canon, missing_context, sentence_of

T = lambda s: {"text": s}       # noqa: E731
F = lambda i: {"fact": i}       # noqa: E731

COHORT = "一项来自纵向队列的报告显示，在调整吸烟因素后，被诊断为哮喘的成年人患该病的风险比非哮喘者高12倍。"
UNITS = [
    {"id": "u1", "source_id": "S1", "page_id": "S1:p1", "location": "第1页", "text": COHORT},
    {"id": "u2", "source_id": "S1", "page_id": "S1:p1", "location": "第1页",
     "text": "该病现已成为全球三大致死原因之一，其中近90%的死亡发生在低收入和中等收入国家。\n"
             "被动接触烟雾也可能导致呼吸系统症状，特别是在长期暴露后。"},
    {"id": "u3", "source_id": "S1", "page_id": "S1:p2", "location": "第2页", "text": "第1章：定义\n关键要点\n该病是一种异质性肺部疾病。"},
    {"id": "S1:p3:x.g", "source_id": "S1", "page_id": "S1:p3", "location": "第3页 表", "text": "Environmental COPD"},
    {"id": "S1:p3:x.c", "source_id": "S1", "page_id": "S1:p3", "location": "第3页 表", "text": "Cigarette smoking COPD", "parent": "S1:p3:x.g"},
    {"id": "S1:p3:x.p", "source_id": "S1", "page_id": "S1:p3", "location": "第3页 表", "text": "Biomass exposure COPD", "parent": "S1:p3:x.g"},
    {"id": "S1:p3:x.d", "source_id": "S1", "page_id": "S1:p3", "location": "第3页 表", "text": "Tobacco smoke"},
    {"id": "S1:p3:x.e", "source_id": "S1", "page_id": "S1:p3", "location": "第3页 表", "text": "Household pollution"},
]


def verified(raw):
    F_, D_, T_ = fx.parse({"facts": raw})
    fx.verify(F_, D_, UNITS, {}, T_)
    return {f.id: asdict(f) for f in F_}


def errors(pages, raw):
    res = check({"title": "t", "pages": pages}, verified(raw))
    return [e for p in res["pages"] for e in p["errors"]]


def page(*items, pid="p1"):
    return {"id": pid, "layout": "bullets", "title": T("要点"), "items": [F(i) for i in items]}


def test_sentence_ends_at_short_heading_lines_not_at_wrapping():
    s, _, q0, q1 = sentence_of(UNITS[2]["text"], "该病是一种异质性肺部疾病")
    assert s == canon("该病是一种异质性肺部疾病。") and q0 == 0
    wrapped = "使用固定比值来定义气流阻塞可能导致老年人的过度诊断，以及在约1%的青年人中漏诊，尤其是轻度疾病患者，相较于使用基于正常值下限的截断值。"
    s, _, q0, _ = sentence_of(wrapped[:40] + "\n" + wrapped[40:], "以及在约1%的青年人中漏诊")
    assert s == canon(wrapped) and q0 > 0


def test_a_study_clause_left_off_the_page_must_be_stated():
    quote = "被诊断为哮喘的成年人患该病的风险比非哮喘者高12倍"
    errs = errors([page("a")], [{"id": "a", "unit": "u1", "quote": quote}])
    assert len(errs) == 1 and "一项来自纵向队列的报告显示" in errs[0] and "在调整吸烟因素后" in errs[0]
    raw = [{"id": "a", "unit": "u1", "quote": quote}, {"id": "s", "unit": "u1", "quote": "一项来自纵向队列的报告显示"},
           {"id": "c", "unit": "u1", "quote": "在调整吸烟因素后"}]
    assert errors([page("a", "s", "c")], raw) == []
    assert errors([page("a", "s")], raw) and errors([page("a", pid="p1"), page("s", "c", pid="p2")], raw)   # on this page


def test_excerpting_the_quote_is_judged_against_the_sentence_too():
    raw = [{"id": "a", "unit": "u1", "quote": COHORT, "display": "被诊断为哮喘的成年人患该病的风险比非哮喘者高12倍"}]
    assert errors([page("a")], raw)
    assert errors([page("a")], [{"id": "a", "unit": "u1", "quote": COHORT}]) == []


def test_a_further_statement_after_the_shown_text_is_not_context_but_a_qualifier_is():
    assert errors([page("a")], [{"id": "a", "unit": "u2", "quote": "该病现已成为全球三大致死原因之一"}]) == []
    errs = errors([page("b")], [{"id": "b", "unit": "u2", "quote": "被动接触烟雾也可能导致呼吸系统症状"}])
    assert len(errs) == 1 and "特别是在长期暴露后" in errs[0]


def test_missing_context_looks_before_between_and_after_the_shown_pieces():
    s = canon("在老年患者中，剂量减至一半，治疗12个月时复发率8%，尤其是轻度患者")
    shown = [[s.index("剂量"), s.index("剂量") + 6], [s.index("复发率"), len(canon("在老年患者中，剂量减至一半，治疗12个月时复发率8%"))]]
    assert missing_context(s, shown) == ["在老年患者中", "治疗12个月时", "尤其是轻度患者"]


def test_reference_markers_figure_pointers_and_numbering_are_not_context():
    s = canon("如图2.5所示，对全美近10,000名成年人的调查(13,14)显示，归因比例为19.2%(15)")
    k = s.index("归因")
    assert missing_context(s, [[k, len(s)]]) == [canon("对全美近10,000名成年人的调查")]
    s = canon("方法可分为：1) 主动发现或 2) 机会性发现")
    assert missing_context(s, [[s.index("机会性"), len(s)]]) == []


def test_bibliography_glued_into_a_sentence_is_not_context():
    # real slides/PDFs: the text layer runs a reference entry, a volume:pages tail or a journal issue header into the
    # next sentence; the citation is not context, the qualifiers after it still are
    def gap(text, shown):
        s, q = canon(text), canon(shown)
        return missing_context(s, [[s.index(q), s.index(q) + len(q)]])
    assert gap("1.中华医学会呼吸病学分会.支气管哮喘防治指南(2024年版)[J].中华结核和呼吸杂志,2025,48(3):208-248."
               "中国哮喘指南2024:在重度哮喘患者中,每3个月需监测血嗜酸性粒细胞计数", "需监测血嗜酸性粒细胞计数") \
        == [canon("中国哮喘指南2024"), canon("在重度哮喘患者中"), canon("每3个月")]
    assert gap("16:611-624.重度未控制哮喘患者面临更高的夜间憋醒风险", "重度未控制哮喘患者面临更高的夜间憋醒风险") == []
    assert gap("(BiomedicalTransformation),2026年3月,第7卷,第1期更稳妥的做法往往是谨慎降阶", "更稳妥的做法往往是谨慎降阶") == []
    s, _, q0, _ = sentence_of("GINA2025 1 指南 2 ➢LAMA具有一定的支气管舒张作用", "LAMA具有一定的支气管舒张作用")
    assert s == canon("LAMA具有一定的支气管舒张作用") and q0 == 0         # “➢” starts a bullet, like “•”


def table(rows, levels=None):
    return {"id": "t", "layout": "table", "title": T("分型"), "columns": ["分型", "描述"], "rows": rows,
            **({"levels": levels} if levels is not None else {})}


TAX = [{"id": x, "unit": f"S1:p3:x.{x}", "quote": t} for x, t in
       (("g", "Environmental COPD"), ("c", "Cigarette smoking COPD"), ("p", "Biomass exposure COPD"),
        ("d", "Tobacco smoke"), ("e", "Household pollution"))]


def test_transcribed_sub_rows_must_sit_under_their_group_row():
    flat = [[[F("g"), F("c")], [F("d")]], [[F("p")], [F("e")]]]
    errs = errors([table(flat)], TAX)
    assert any("S1:p3:x.g" in e and "第2行" in e for e in errs) and any("第1行" in e for e in errs)
    nested = [[[F("g")], []], [[F("c")], [F("d")]], [[F("p")], [F("e")]]]
    assert errors([table(nested, [0, 1, 1])], TAX) == []
    assert errors([table(nested)], TAX)                                   # same rows, no levels: still flat
    assert any("深了不止一级" in e for e in errors([table(nested, [0, 2, 1])], TAX))
    assert any("levels 需与行数一致" in e for e in errors([table(nested, [0, 1])], TAX))


def test_entity_rows_nest_the_same_way():
    slots = {"headers": [T("分型"), T("描述")], "rows": [[F("g"), []], [F("c"), F("d")], [F("p"), F("e")]]}
    pg = lambda lv: {"id": "e", "layout": "composed", "title": T("分型"), "recipe": "entity_rows",  # noqa: E731
                     "slots": {**slots, **({"levels": lv} if lv else {})}}
    assert errors([pg([0, 1, 1])], TAX) == []
    assert errors([pg(None)], TAX)


def test_a_transcribed_cell_names_an_earlier_cell_on_its_page_as_parent():
    pg = {"id": "S1:p3", "source_id": "S1", "location": "第3页"}
    got = transcription_units(pg, [{"id": "g", "location": "表 分组", "text": "Environmental COPD"},
                                   {"id": "c", "location": "表 子类", "text": "Cigarette smoking COPD", "parent": "g"}], "R1")
    assert "parent" not in got[0] and got[1]["parent"] == "S1:p3:x.g"
    for bad in ("c", "z"):
        with pytest.raises(IngestError):
            transcription_units(pg, [{"id": "c", "location": "表", "text": "x", "parent": bad},
                                     {"id": "g", "location": "表", "text": "y"}], "R1")
