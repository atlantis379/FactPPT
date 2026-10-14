"""Information structure: the author's marks in the originals, candidate relations, and their backfill.

Content is invented; the fixtures only exercise the mechanism.
"""
import io

from docx import Document
from pptx import Presentation
from pptx.util import Inches, Pt

from app.deckflow import Store
from factdeck.ingest import extract_all
from factdeck.structure import candidates


def _pptx() -> bytes:
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[5])                  # title only
    s.shapes.title.text = "示例评估先于治疗"
    t = s.shapes.add_textbox(Inches(1), Inches(2), Inches(6), Inches(1)).text_frame
    p = t.paragraphs[0]
    for text, bold in (("常规说明，", False), ("关键步骤不可省略", True), ("，其余照常。", False)):
        r = p.add_run()
        r.text, r.font.bold = text, bold
    whole = s.shapes.add_textbox(Inches(1), Inches(3.5), Inches(6), Inches(0.5)).text_frame
    r = whole.paragraphs[0].add_run()
    r.text, r.font.bold = "整框加粗的标签", True
    foot = s.shapes.add_textbox(Inches(1), Inches(7), Inches(6), Inches(0.4)).text_frame
    fp = foot.paragraphs[0]
    for text, bold in (("缩写：", True), ("示例缩写说明", False)):
        r = fp.add_run()
        r.text, r.font.bold = text, bold
    s2 = prs.slides.add_slide(prs.slide_layouts[6])                 # blank: the headline is an ordinary text box
    n = s2.shapes.add_textbox(Inches(9), Inches(0.1), Inches(0.5), Inches(0.4)).text_frame
    n.text = "2"
    h = s2.shapes.add_textbox(Inches(0.5), Inches(0.4), Inches(8), Inches(0.8)).text_frame
    h.text = "无占位符的页标题"
    h.paragraphs[0].runs[0].font.size = Pt(28)
    for i, text in enumerate(("1、第一步检查", "2、第二步判断", "3、第三步随访")):
        s2.shapes.add_textbox(Inches(1), Inches(2 + i), Inches(6), Inches(0.6)).text_frame.text = text
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _docx() -> bytes:
    d = Document()
    d.add_heading("示例章节", level=1)
    p = d.add_paragraph()
    p.add_run("普通文字，")
    p.add_run("重点句子").bold = True
    p.add_run("，以及其他。")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def test_pptx_marks_titles_and_partial_emphasis_but_not_whole_boxes_or_footnotes():
    _, units, _ = extract_all("m.pptx", _pptx(), "S01")
    sig = {u.text: u.signals for u in units if u.signals}
    assert sig["示例评估先于治疗"]["title"] == ["示例评估先于治疗"]
    assert sig["常规说明，关键步骤不可省略，其余照常。"]["emphasis"] == ["关键步骤不可省略"]
    assert "整框加粗的标签" not in sig                               # a box's own style is not a mark
    assert "缩写：示例缩写说明" not in sig                            # footnote zone
    assert sig["无占位符的页标题"]["title"] == ["无占位符的页标题"]
    assert "2" not in sig                                             # a page number is no headline


def test_docx_marks_headings_and_bold_fragments():
    _, units, _ = extract_all("m.docx", _docx(), "S01")
    sig = {u.text: u.signals for u in units if u.signals}
    assert sig["示例章节"]["title"] == ["示例章节"]
    assert sig["普通文字，重点句子，以及其他。"]["emphasis"] == ["重点句子"]


def _u(uid, text, **kw):
    return {"id": uid, "page_id": uid.rsplit(":", 1)[0], "text": text, **kw}


def test_candidates_come_from_arrows_tables_numbering_and_connectives():
    units = [
        _u("S01:s1:b1", "甲"), _u("S01:s1:b2", "乙"), _u("S01:s1:b3", "丙"),
        _u("S01:s1:a1", "甲→乙", arrow={"from": "S01:s1:b1", "to": "S01:s1:b2", "label": None}),
        _u("S01:s1:a2", "乙→丙", arrow={"from": "S01:s1:b2", "to": "S01:s1:b3", "label": None}),
        _u("S01:s2:t1r1c1", "项目"), _u("S01:s2:t1r1c2", "数值"), _u("S01:s2:t1r2c1", "指标甲"), _u("S01:s2:t1r2c2", "10"),
        _u("S01:s3:b1", "1、检查"), _u("S01:s3:b2", "2、判断"),
        _u("S01:s4:b1", "满足以下任一条件即可：条件甲；条件乙"),
        _u("S01:s4:b2", "与对照组相比，示例组结果不同"),
    ]
    got = {(c["type"], c["basis"], tuple(c["unit_ids"])) for c in candidates(units)}
    assert ("sequence", "arrow", ("S01:s1:a1", "S01:s1:a2")) in got
    assert ("matrix", "table", ("S01:s2:t1r1c1", "S01:s2:t1r1c2", "S01:s2:t1r2c1", "S01:s2:t1r2c2")) in got
    assert ("sequence", "numbered", ("S01:s3:b1", "S01:s3:b2")) in got
    assert ("any_of", "connective", ("S01:s4:b1",)) in got
    assert ("compare", "connective", ("S01:s4:b2",)) in got
    ids = [c["id"] for c in candidates(units)]
    assert ids == [c["id"] for c in candidates(units)] and len(set(ids)) == len(ids)    # deterministic, unique


def test_labelled_arrows_make_a_branch():
    units = [_u("S01:s1:a1", "问→是路径（是）", arrow={"from": "S01:s1:b1", "to": "S01:s1:b2", "label": "S01:s1:b4"})]
    assert candidates(units)[0]["type"] == "branch"


def test_backfill_adds_marks_and_relations_without_moving_existing_units(tmp_path):
    store = Store(tmp_path / "data")
    w = store.create("补录", "")
    w = store.add_source(w["id"], "m.pptx", _pptx())
    s = w["sources"][0]
    assert s["relations"]                                            # computed at import
    with store.transaction(w["id"], "TEST_OLD_INGEST") as ww:        # as imported by an ingest without marks
        for u in ww["sources"][0]["units"]:
            u.pop("signals", None)
        ww["sources"][0].pop("relations")
    before = [(u["id"], u["text"]) for u in store.get(w["id"])["sources"][0]["units"]]
    r = store.backfill_structure(w["id"])
    after = store.get(w["id"])["sources"][0]
    assert [(u["id"], u["text"]) for u in after["units"]] == before
    assert r["marked"]["S01"] >= 3 and not r["skipped"]
    assert after["relations"] == s["relations"]


# ------------------------------------------------------------------ the summary's information structure
import copy

import pytest

from app.deckflow import WorkflowError
import factdeck_fixture as fx_
import test_deckflow as T
from test_outline_structure import OUTLINE, add_messages, structured_summary


def _claimed(tmp_path):
    store = Store(tmp_path / "data")
    w = store.create("信息结构", OUTLINE)
    for name, make in fx_.SOURCES.items():
        store.add_source(w["id"], name, make())
    w = T.read_all(store, w["id"])
    store.queue(w["id"], "SUMMARY")
    t = store.claim(w["id"], "author-A", "SUMMARY")
    return store, w, t


def test_summary_message_is_checked_against_the_sources(tmp_path):
    store, w, t = _claimed(tmp_path)
    assert "message" in t["brief"]["result_contract"]["sections"][0] and "relation_types" in t["brief"]

    def submit(edit):
        r = add_messages(w, structured_summary(w))
        edit(r["sections"][0]["message"], r)
        store.complete(w["id"], t["id"], t["lease_token"], r)

    with pytest.raises(WorkflowError, match="core.claim_id"):
        submit(lambda m, r: m["core"].update(claim_id="S99:x#k1"))
    with pytest.raises(WorkflowError, match="恰好有一条核心"):
        submit(lambda m, r: m["roles"].update({k: "core" for k in m["roles"]}))
    with pytest.raises(WorkflowError, match="core / support / limit"):
        submit(lambda m, r: m["roles"].update({list(m["roles"])[1]: "background"}))
    with pytest.raises(WorkflowError, match="角色"):
        submit(lambda m, r: m["roles"].pop(list(m["roles"])[1]))
    with pytest.raises(WorkflowError, match="类型"):
        submit(lambda m, r: m["relations"].append({"type": "causes", "items": list(m["roles"]), "claim_ids": [m["core"]["claim_id"]]}))
    with pytest.raises(WorkflowError, match="不存在的论断"):
        submit(lambda m, r: m["relations"].append({"type": "any_of", "items": list(m["roles"]), "claim_ids": ["S99:x#k1"]}))
    with pytest.raises(WorkflowError, match="支撑它的论断"):
        submit(lambda m, r: m["relations"].append({"type": "any_of", "items": list(m["roles"]), "unit_ids": ["S01:p1:b1"]}))
    with pytest.raises(WorkflowError, match="候选关系"):
        submit(lambda m, r: m["relations"].append({"type": "any_of", "items": list(m["roles"]), "unit_ids": ["S01:p1:b1"],
                                                   "from_candidate": "R0000000000"}))
    with pytest.raises(WorkflowError, match="message"):
        submit(lambda m, r: r["sections"][0].pop("message"))
    submit(lambda m, r: m["relations"].append({"type": "all_of", "items": list(m["roles"]), "claim_ids": [m["core"]["claim_id"]]}))
    sec = store.get(w["id"])["summary"]["sections"]
    assert sec[0]["message"]["relations"][0]["manual"] is True
    assert any("人工判断" in x for x in sec[0]["message"]["warnings"])
    assert any("并列清单" in x for x in sec[1]["message"]["warnings"])


def test_confirmation_draft_is_a_storyboard(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app.deckflow_api as api
    from app.main import app
    store, w, t = _claimed(tmp_path)
    monkeypatch.setattr(api, "store", store)
    r = add_messages(w, structured_summary(w))
    m = r["sections"][0]["message"]
    points = list(m["roles"])
    m["roles"][points[-1]] = "limit"
    m["relations"].append({"type": "all_of", "items": points[:2], "claim_ids": [m["core"]["claim_id"]]})
    store.complete(w["id"], t["id"], t["lease_token"], r)
    text = TestClient(app).get(f"/api/deck/workflows/{w['id']}/confirmation-draft").text
    names = {x["point_id"]: x["point"] for x in r["sections"][0]["point_coverage"]}
    core = next(s for s in store.get(w["id"])["summary"]["sections"] if s["id"] == r["sections"][0]["id"])["message"]["core"]
    m["core"]["quote"] = core["quote"]
    assert f"**核心句**：「{m['core']['quote']}」" in text
    assert f"均需满足：{names[points[0]]} / {names[points[1]]}（人工判断，请确认）" in text
    assert f"限定要点（必须上页）：{names[points[-1]]}" in text
    assert "## 故事线" in text and f"1. {r['sections'][0]['title']}：「{m['core']['quote']}」" in text
    assert "逻辑：未列出关系" in text                                   # the second item lists none


# ------------------------------------------------------------------ the pages against the information structure
from factdeck.deck import check
from test_layout_guidance import facts as flow_facts
from test_outline_structure import GOOD, outline_and_sections


def _deck_run(edit_pages):
    items, parts, sections = outline_and_sections()
    cover = {"outline_1.1": ["P1"], "outline_1.2": ["D1"], "outline_1.3": ["D2"]}
    for r in sections[0]["point_coverage"]:
        r["unit_ids"] = cover[r["point_id"]]
    sections[0]["message"] = {"core": {"unit_id": "P1", "quote": "诱因作用于屏障"},
                              "roles": {"outline_1.1": "core", "outline_1.2": "support", "outline_1.3": "limit"},
                              "relations": [{"type": "sequence", "items": ["outline_1.1", "outline_1.2"], "unit_ids": ["D1", "D3"]}]}
    pages = [dict(p) for p in GOOD]
    pages[1]["focus"] = {"fact": "p1"}
    pages[2] = dict(pages[2], items=[{"fact": "p1"}, {"fact": "n2"}], focus={"fact": "p1"})
    edit_pages(pages)
    return check({"pages": pages, "omissions": [{"section_id": s["id"], "reason": "测试"} for s in sections]}, flow_facts(),
                 outline=items, sections=sections, parts=parts)


def test_pages_follow_the_information_structure():
    res = _deck_run(lambda p: None)
    assert res["errors"] == 0, res["deck_errors"]
    assert not any("焦点" in x or "版式宜用" in x for x in res["warnings"])


def test_limit_point_must_show_its_own_text():
    res = _deck_run(lambda p: p.__setitem__(2, dict(p[2], items=[{"fact": "p1"}])))
    assert any("限定要点 outline_1.3" in e for e in res["deck_errors"])


def test_focus_is_marked_shown_and_central():
    missing = _deck_run(lambda p: p[1].pop("focus"))
    assert any("a：须标注本页焦点" in x for x in missing["deck_errors"])      # a content page without a focus is an error
    absent = _deck_run(lambda p: p[1].__setitem__("focus", {"fact": "n3"}))
    assert any("焦点 n3 须是本页显示的事实" in e for e in absent["deck_errors"])
    side = _deck_run(lambda p: p[2].__setitem__("focus", {"fact": "n2"}))
    assert any("焦点 n2 既不属于" in x for x in side["warnings"])


def test_relation_on_a_plain_list_suggests_a_fitting_layout():
    res = _deck_run(lambda p: p[1].__setitem__("items", [{"fact": "p1"}, {"fact": "n1"}]))
    assert any("sequence" in x and "flow / timeline" in x for x in res["warnings"])
