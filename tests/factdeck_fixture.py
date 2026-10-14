"""Synthetic multi-format sources and a deck that uses every layout.

All content is invented for program testing ("示例病X", "药物A") and is not medical
information. Used by the engine tests and the workflow tests.
"""
from __future__ import annotations

import io


def txt_source() -> bytes:
    return ("# 示例病X概述（虚构测试资料）\n\n示例病X是一种用于程序验收的虚构疾病，成人患病率约为12.5%。\n\n"
            "诊断需同时满足指标甲≥150单位与指标乙<1.5。\n\n# 治疗原则\n\n药物A不推荐用于18岁以下患者。\n\n"
            "药物B每4周给药一次，剂量为100mg。").encode("utf-8")


def docx_source() -> bytes:
    from docx import Document
    doc = Document()
    doc.add_heading("示例指南（虚构测试资料）", 1)
    doc.add_paragraph("评估流程：先完成症状评估，再检测指标甲，最后判断分型。")
    doc.add_paragraph("高风险人群包括年龄≥65岁或既往住院≥2次的患者。")
    table = doc.add_table(rows=3, cols=3)
    for r, row in enumerate([["药物", "靶点", "用法"], ["药物A", "T-1", "每2周一次"], ["药物B", "T-2", "每4周一次"]]):
        for c, v in enumerate(row):
            table.cell(r, c).text = v
    doc.add_heading("随访", 1)
    doc.add_paragraph("治疗12个月后约40~45%的患者达到示例缓解标准。")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def pptx_source() -> bytes:
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "示例研究对比（虚构）"
    tb = s.shapes.add_textbox(Inches(1), Inches(1.5), Inches(6), Inches(1))
    tb.text_frame.text = "研究甲：纳入成人患者320例，主要终点缓解率38%"
    tb2 = s.shapes.add_textbox(Inches(1), Inches(2.5), Inches(6), Inches(1))
    tb2.text_frame.text = "研究乙：纳入青少年患者96例，主要终点缓解率29%"
    t = s.shapes.add_table(2, 2, Inches(1), Inches(4), Inches(6), Inches(1)).table
    t.cell(0, 0).text, t.cell(0, 1).text = "药物A单价", "986元"
    t.cell(1, 0).text, t.cell(1, 1).text = "药物B单价", "1,204元"
    s.notes_slide.notes_text_frame.text = "两项研究的人群不同，不能直接比较缓解率。"
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def xlsx_source() -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "价格"
    ws.append(["药物", "单价(元)"])
    ws.append(["药物A", 1204])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


SOURCES = {"overview.txt": txt_source, "guide.docx": docx_source, "studies.pptx": pptx_source, "price.xlsx": xlsx_source}


def facts_proposal(uid: dict[str, str]) -> dict:
    """`uid` maps a short key to the actual unit id in the store."""
    F = lambda i, u, q, **k: {"id": i, "unit": uid[u], "quote": q, **k}
    return {
        "terms": ["示例病X", "药物A", "药物B", "指标甲", "指标乙"],
        "facts": [
            F("x.def", "txt_def", "示例病X是一种用于程序验收的虚构疾病", section_ids=["s1"]),
            F("x.prev", "txt_def", "成人患病率约为12.5%", section_ids=["s1"]),
            F("dx.a", "txt_dx", "指标甲≥150单位", section_ids=["s1"]),
            F("dx.b", "txt_dx", "指标乙<1.5", section_ids=["s1"]),
            F("dx.rule", "txt_dx", "诊断需同时满足指标甲≥150单位与指标乙<1.5", section_ids=["s1"]),
            F("a.limit", "txt_a", "药物A不推荐用于18岁以下患者", section_ids=["s2"]),
            F("b.dose", "txt_b", "药物B每4周给药一次，剂量为100mg", display="每4周给药一次，剂量为100mg", section_ids=["s2"]),
            F("flow.1", "doc_flow", "先完成症状评估", section_ids=["s2"]),
            F("flow.2", "doc_flow", "再检测指标甲", section_ids=["s2"]),
            F("flow.3", "doc_flow", "最后判断分型", section_ids=["s2"]),
            F("flow.seq", "doc_flow", "评估流程：先完成症状评估，再检测指标甲，最后判断分型", section_ids=["s2"]),
            F("risk", "doc_risk", "高风险人群包括年龄≥65岁或既往住院≥2次的患者", section_ids=["s2"]),
            F("tbl.a", "doc_a", "药物A"), F("tbl.a.t", "doc_at", "T-1"), F("tbl.a.u", "doc_au", "每2周一次"),
            F("tbl.b", "doc_b", "药物B"), F("tbl.b.t", "doc_bt", "T-2"), F("tbl.b.u", "doc_bu", "每4周一次"),
            F("fu", "doc_fu", "治疗12个月后约40~45%的患者达到示例缓解标准", section_ids=["s3"]),
            F("st.a", "ppt_a", "研究甲", section_ids=["s3"]), F("st.a.pop", "ppt_a", "纳入成人患者320例"),
            F("st.a.v", "ppt_a", "38%"), F("st.a.l", "ppt_a", "主要终点缓解率"),
            F("st.b", "ppt_b", "研究乙", section_ids=["s3"]), F("st.b.pop", "ppt_b", "纳入青少年患者96例"),
            F("st.b.v", "ppt_b", "29%"), F("st.b.l", "ppt_b", "主要终点缓解率"),
            F("st.caveat", "ppt_notes", "两项研究的人群不同，不能直接比较缓解率", section_ids=["s3"]),
            F("price.a.ppt", "ppt_price_a", "986元", entity="药物A", attribute="单价(元)", value="986"),
            F("price.a.xls", "xls_a", "1204", entity="药物A", attribute="单价(元)", value="1204"),
            F("price.b", "ppt_price_b", "1,204元"),
            # rejected on purpose: display not in quote / dropped negation
            F("bad.num", "txt_def", "成人患病率约为12.5%", display="成人患病率约为15%"),
            F("bad.neg", "txt_a", "药物A不推荐用于18岁以下患者", display="药物A推荐用于18岁以下患者"),
        ],
        "derivations": [],
    }


def deck_spec(outline_ids: list[str]) -> dict:
    o = outline_ids
    return {
        "title": "示例病X（程序验收用虚构课件）",
        "theme": "navy-teal",
        "glossary": [{"text": "示例病X", "fact": "x.def"}, {"text": "指标甲", "fact": "dx.a"}],
        "omissions": [],
        "pages": [
            {"id": "cover", "layout": "cover", "kicker": {"text": "程序验收"}, "title": {"text": "示例病X课件"},
             "subtitle": {"text": "虚构资料，仅用于检查生成线"}, "outline_ids": []},
            {"id": "part1", "layout": "divider", "title": {"text": "认识示例病X"}, "outline_ids": []},
            {"id": "overview", "layout": "bullets", "section": {"text": "概述"}, "title": {"text": "示例病X是什么"},
             "items": [{"fact": "x.def"}, {"fact": "x.prev"}, {"fact": "dx.rule"}], "outline_ids": [o[0]], "section_ids": ["s1"], "focus": {"fact": "x.def"}},
            {"id": "criteria", "layout": "cards", "section": {"text": "诊断"}, "title": {"text": "诊断需要的指标"},
             "cards": [{"label": {"text": "指标甲"}, "value": {"fact": "dx.a"}}, {"label": {"text": "另一指标"}, "value": {"fact": "dx.b"}}],
             "notes_title": {"text": "判断规则原文"}, "notes": [{"fact": "dx.rule"}], "outline_ids": [o[0]], "section_ids": ["s1"], "focus": {"fact": "dx.rule"}},
            {"id": "flow", "layout": "flow", "section": {"text": "评估"}, "title": {"text": "评估流程"},
             "nodes": [{"id": "n1", "ref": {"fact": "flow.1"}, "col": 0, "row": 0, "emphasis": "core"},
                       {"id": "n2", "ref": {"fact": "flow.2"}, "col": 1, "row": 0},
                       {"id": "n3", "ref": {"fact": "flow.3"}, "col": 2, "row": 1, "emphasis": "soft"}],
             "edges": [["n1", "n2", "flow.seq"], ["n2", "n3", "flow.seq"]],
             "side": [{"fact": "flow.seq"}, {"fact": "risk"}], "outline_ids": [o[1]], "section_ids": ["s2"], "focus": {"fact": "flow.1"}},
            {"id": "drugs", "layout": "table", "section": {"text": "治疗"}, "title": {"text": "药物一览"},
             "lead": {"fact": "a.limit"},
             "columns": ["药物", "靶点", "用法"], "widths": [2, 2, 4],
             "rows": [[[{"fact": "tbl.a"}], [{"fact": "tbl.a.t"}], [{"fact": "tbl.a.u"}]],
                      [[{"fact": "tbl.b"}], [{"fact": "tbl.b.t"}], [{"fact": "tbl.b.u"}, {"fact": "b.dose"}]],
                      [[{"text": "价格"}], [{"fact": "price.a.ppt"}], [{"fact": "price.b"}]]],
             "outline_ids": [o[1]], "section_ids": ["s2"], "focus": {"fact": "a.limit"}},
            {"id": "studies", "layout": "compare", "section": {"text": "证据"}, "title": {"text": "研究对比"},
             "panels": [{"heading": {"fact": "st.a"}, "value": {"fact": "st.a.v"}, "value_label": {"fact": "st.a.l"}, "items": [{"fact": "st.a.pop"}]},
                        {"heading": {"fact": "st.b"}, "value": {"fact": "st.b.v"}, "value_label": {"fact": "st.b.l"}, "items": [{"fact": "st.b.pop"}]}],
             "band": [{"fact": "st.caveat"}], "outline_ids": [o[2]], "section_ids": ["s3"], "focus": {"fact": "st.a.v"}},
            {"id": "followup", "layout": "statement", "section": {"text": "随访"}, "title": {"text": "随访结果"},
             "statement": {"fact": "fu"}, "support": [{"fact": "st.caveat"}], "outline_ids": [o[2]], "section_ids": ["s3"], "focus": {"fact": "fu"}},
            {"id": "end", "layout": "closing", "title": {"text": "小结"}, "items": [{"fact": "dx.rule"}, {"fact": "a.limit"}], "outline_ids": []},
        ],
    }


# unit ids when the sources are registered in SOURCES order as S01..S04
UIDS = {"txt_def": "S01:t1:para2", "txt_dx": "S01:t1:para3", "txt_a": "S01:t2:para5", "txt_b": "S01:t2:para6",
        "doc_flow": "S02:d1:para2", "doc_risk": "S02:d1:para3",
        "doc_a": "S02:d1:t1r2c1", "doc_at": "S02:d1:t1r2c2", "doc_au": "S02:d1:t1r2c3",
        "doc_b": "S02:d1:t1r3c1", "doc_bt": "S02:d1:t1r3c2", "doc_bu": "S02:d1:t1r3c3", "doc_fu": "S02:d2:para5",
        "ppt_a": "S03:s1:b2", "ppt_b": "S03:s1:b3", "ppt_notes": "S03:s1:notes",
        "ppt_price_a": "S03:s1:t1r1c2", "ppt_price_b": "S03:s1:t1r2c2", "xls_a": "S04:x1:r2"}
