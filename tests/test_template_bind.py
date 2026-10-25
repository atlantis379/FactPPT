"""Template-library fills bound to the fact store (factdeck/template_lib/bind.py): every shown string is a fact
reference or a checked authored label, every drawn number is stated by a page fact, footers come from the facts
used, and the trace covers every slot.  Deck specs carry bound fills as `layout: "template"` pages."""
from __future__ import annotations

import copy
import json

import pytest

from factdeck import deck as D
from factdeck.template_lib import bind, integrate, slots
from factdeck.template_lib import selector as S

F = lambda i: {"fact": i}          # noqa: E731
T = lambda s: {"text": s}          # noqa: E731


def fact(fid, text, *, source="S01", loc="p. 12", status="ACCEPTED", **kw):
    return {"id": fid, "unit": f"{source}:{fid}", "quote": text, "display": "", "status": status, "problems": [],
            "needs_confirmation": False, "figure": "", "caption": [], "scope": [], "context": {},
            "source_id": source, "location": loc, **kw}


FACTS = {f["id"]: f for f in [
    fact("t.title", "血嗜酸粒细胞≥300个/µL亚组获益最大"),
    fact("t.sub", "52周中重度急性加重年化率的亚组率比"),
    fact("t.drug", "研究药"),
    fact("t.pbo", "安慰剂"),
    fact("t.l1", "总体人群"),
    fact("t.l2", "<150"),
    fact("t.l3", "≥300"),
    fact("t.r1", "总体人群 RR 0.70（95% CI 0.58–0.84）"),
    fact("t.r2", "<150亚组 RR 0.94（0.66–1.34）"),
    fact("t.r3", "≥300亚组 RR 0.58（0.45–0.75），风险降低42%", source="S02", loc="表 3 · p. 26"),
    fact("t.v1", "0.70"),
    fact("t.v2", "0.94"),
    fact("t.v3", "0.58"),
    fact("t.bad", "被拒绝的句子", status="REJECTED", problems=["不是逐字引文"]),
]}
SOURCES = {"S01": "GOLD 2026 报告", "S02": "某研究 52 周结果"}


def forest_fill():
    return {
        "section": T("亚组分析"),
        "subtitle": F("t.sub"),
        "col_a": F("t.drug"), "col_c": F("t.pbo"),
        "axis": {"min": 0.25, "max": 2.0, "ticks": [0.25, 0.5, 1, 2]},
        "rows": [
            {"label": F("t.l1"), "overall": True, "est": 0.70, "lo": 0.58, "hi": 0.84},
            {"label": F("t.l2"), "est": 0.94, "lo": 0.66, "hi": 1.34},
            {"label": F("t.l3"), "est": 0.58, "lo": 0.45, "hi": 0.75},
        ],
        "takeaways": [{"value": F("t.v1"), "text": F("t.r1")}, {"value": F("t.v2"), "text": F("t.r2")},
                      {"value": F("t.v3"), "text": F("t.r3")}],
    }


def resolve(fill, **kw):
    return bind.resolve("forest_plot", None, fill, FACTS, title=F("t.title"), sources=SOURCES, page_no=5, **kw)


def test_bound_forest_resolves_traces_and_writes_footer():
    r = resolve(forest_fill())
    assert r["errors"] == [], r["errors"]
    f = r["fill"]
    assert f["title"] == "血嗜酸粒细胞≥300个/µL亚组获益最大"
    assert f["rows"][2]["label"] == "≥300" and f["rows"][2]["est"] == 0.58
    # chrome written by code: no sample-data note, sources numbered, superscripts per takeaway
    assert f["data_note"] == bind.BOUND_NOTE and "示例" not in json.dumps(f, ensure_ascii=False)
    assert f["figure"] == "图 5"
    assert [x["text"] for x in f["refs"]] == ["GOLD 2026 报告", "某研究 52 周结果"]
    assert f["takeaways"][0]["refs"] == ["1"] and f["takeaways"][2]["refs"] == ["1", "2"]   # t.r3 is S02
    assert slots.validate_fill("forest_plot", {**f, "page": "05"})["ok"]
    # every shown slot and every drawn number is in the trace
    kinds = {t["slot"]: t for t in r["trace"]}
    assert kinds["fill.rows[2].label"]["fact"] == "t.l3"
    assert kinds["fill.section"]["kind"] == "authored"
    assert set(kinds["fill.rows[2].est"]["backed_by"]) == {"t.r1", "t.r3", "t.v3"}   # 0.58 is also r1's CI
    assert "fill.axis.min" not in kinds                      # scale frame, not data
    assert set(r["facts"]) >= {"t.title", "t.r1", "t.r2", "t.r3"}


def test_raw_strings_and_code_written_slots_are_refused():
    fill = forest_fill()
    fill["subtitle"] = "52周中重度急性加重年化率"
    fill["source"] = "自己写的来源"
    fill["takeaways"][0]["refs"] = ["1"]
    errs = " ".join(resolve(fill)["errors"])
    assert "fill.subtitle 需写成" in errs
    assert "fill.source" in errs and "fill.takeaways[0].refs" in errs


def test_peer_items_need_their_own_names():
    # a real DECK run headed every card "来源要点": the names said nothing about the cards
    fill = {"items": [{"heading": T("要点"), "body": F("t.r1")}, {"heading": T("要点"), "body": F("t.r2")},
                      {"heading": T("亚组"), "body": F("t.r3")}]}
    r = bind.resolve("key_points", None, fill, FACTS, title=F("t.title"), sources=SOURCES)
    assert any("items[].heading" in e and "2 项同名“要点”" in e for e in r["errors"]), r["errors"]
    fill["items"][1]["heading"] = F("t.l2")                  # a fact name, or a distinct label, is fine
    assert bind.resolve("key_points", None, fill, FACTS, title=F("t.title"), sources=SOURCES)["errors"] == []
    fill["items"][2]["sub"] = T(" ")                         # the same run padded a table with an empty column
    assert any("作者文字为空" in e for e in bind.resolve("key_points", None, fill, FACTS, title=F("t.title"))["errors"])


def test_teaching_table_without_a_rail_binds_and_qualifies():
    fill = {"stub_head": T("人群"), "columns": [{"label": T("研究药")}, {"label": T("安慰剂")}],
            "rows": [{"label": F("t.l1"), "cells": [F("t.v1"), F("t.r1")]},
                     {"label": F("t.l2"), "cells": [F("t.v2"), F("t.r2")]},
                     {"label": F("t.l3"), "cells": [F("t.v3"), F("t.r3")]}]}
    r = bind.resolve("data_table_highlight", None, fill, FACTS, title=F("t.title"), sources=SOURCES, page_no=3)
    assert r["errors"] == [], r["errors"]
    assert r["fill"]["rows"][2]["cells"] == ["0.58", "≥300亚组 RR 0.58（0.45–0.75），风险降低42%"]
    assert slots.validate_fill("data_table_highlight", r["fill"])["ok"]
    page = integrate.page_from_fill("p3", "data_table_highlight", r["fill"])
    assert S.requirement_gap("data_table_highlight", page) is None
    one = {**fill, "columns": fill["columns"][:1], "rows": [{**x, "cells": x["cells"][:1]} for x in fill["rows"]]}
    r1 = bind.resolve("data_table_highlight", None, one, FACTS, title=F("t.title"), sources=SOURCES, page_no=3)
    assert r1["errors"] == [] and slots.validate_fill("data_table_highlight", r1["fill"])["ok"]   # object × one attribute
    assert "cells" in json.dumps(integrate.template_library_brief()["data_table_highlight"]["slots"])


def test_unbacked_number_is_an_error_never_a_guess():
    fill = forest_fill()
    fill["rows"][1]["hi"] = 1.40                             # not stated by any fact on the page
    r = resolve(fill)
    assert any("fill.rows[1].hi" in e and "1.4" in e for e in r["errors"])


def test_number_from_another_row_is_flagged():
    fill = forest_fill()
    fill["rows"][1] = {"label": F("t.r2"), "est": 0.58, "lo": 0.45, "hi": 0.75}   # row 2's own fact says 0.94
    r = resolve(fill)
    assert r["errors"] == []
    assert any("fill.rows[1].est" in w and "同一行" in w for w in r["warnings"])


def test_authored_text_rules_and_fact_status():
    fill = forest_fill()
    fill["section"] = T("降低42%")
    fill["col_a"] = F("t.bad")
    fill["col_c"] = F("nope")
    fill["subtitle"] = {"fact": "t.sub", "emph": ["52周"]}
    errs = " ".join(resolve(fill)["errors"])
    assert "fill.section" in errs and "未通过的事实 t.bad" in errs and "不存在的事实 nope" in errs
    assert "emph" in errs


def test_scope_label_cut_off_must_be_stated_on_page():
    facts = copy.deepcopy(FACTS)
    facts["t.l1"]["scope"] = ["中国"]
    r = bind.resolve("forest_plot", None, forest_fill(), facts, title=F("t.title"))
    assert any("范围标签“中国”" in e for e in r["errors"])


def test_numbers_in_parses_ranges_signs_and_spacing():
    assert bind.numbers_in("RR 0.70（95% CI 0.58–0.84）") == {0.7, 95, 0.58, 0.84}
    assert bind.numbers_in("降低 −30%，n = 1 100") == {-30, 1100}
    assert bind.numbers_in("第-4周") == {-4}


# ---------------------------------------------------------------- deck specs: layout "template"

def deck_with(page):
    return {"pages": [page]}


def template_page(**t):
    return {"id": "p5", "layout": "template", "title": F("t.title"),
            "template": {"layout": "forest_plot", "fill": forest_fill(), **t}}


def test_deck_template_page_passes_the_gate_and_records_the_decision():
    res = D.check(deck_with(template_page()), FACTS)
    page = res["pages"][0]
    assert page["errors"] == [] and res["deck_errors"] == [], (page["errors"], res["deck_errors"])
    assert {"t.title", "t.l3", "t.r3"} <= set(page["facts"])
    rec = res["template_layouts"]["pages"]["p5"]
    assert rec["layout"] == "forest_plot" and rec["rendered_layout"] == "forest_plot" and rec["reason_zh"]


def test_deck_template_page_reports_fill_errors():
    p = template_page()
    p["template"]["fill"]["rows"][0]["est"] = 0.71
    res = D.check(deck_with(p), FACTS)
    assert any("template[forest_plot]" in e and "0.71" in e for e in res["pages"][0]["errors"])


def test_deck_template_page_without_a_fill_for_the_selected_layout_is_refused():
    # the only fill is written for a layout the content cannot back: refused, never rendered as something else
    p = {"id": "p5", "layout": "template", "title": F("t.title"),
         "template": {"layout": "trial_design", "fills": {"trial_design": forest_fill()}}}
    res = D.check(deck_with(p), FACTS)
    rec = res["template_layouts"]["pages"]["p5"]
    assert rec["layout"] != "trial_design"
    assert any("没有可用的填充" in e for e in res["deck_errors"])


def test_deck_plan_feeds_the_pipeline():
    plan = integrate.deck_plan(deck_with(template_page()))
    assert plan["bound"] and plan["pages"][0]["fills"]["forest_plot"]["rows"][0]["label"] == F("t.l1")
    from factdeck.template_lib import pipeline
    with pytest.raises(ValueError):
        pipeline.run(plan, "unused-out-dir-never-written")


def test_trace_markdown_covers_every_page():
    r = resolve(forest_fill())
    md = bind.trace_markdown([{"page_no": 1, "page_id": "p5", "layout": "forest_plot", "bound": True, "trace": r["trace"]},
                              {"page_no": 2, "page_id": "demo", "layout": "flow", "bound": False}], sources=SOURCES)
    assert "第 1 页 · p5" in md and "t.l3" in md and "某研究 52 周结果" in md and "表 3 · p. 26" in md
    assert "第 2 页 · demo" in md and "未溯源" in md
    assert any("【溯源】t.r3：某研究 52 周结果 · 表 3 · p. 26" == x for x in bind.notes_lines(r["trace"], SOURCES))


def test_selector_input_of_a_bound_page_comes_from_the_resolved_fill():
    sel = integrate.deck_page_input(template_page(), FACTS)
    assert sel["proposed_layout"] == "forest_plot"
    assert [e["est"] for e in sel["data"]["effects"]] == [0.70, 0.94, 0.58]
    assert "≥300" in sel["text"]
    assert S.requirement_gap("forest_plot", sel) is None


# ---------------------------------------------------------------- end to end: bound plan → native PPTX + trace

def _chromium_ok() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            pw.chromium.launch().close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _chromium_ok(), reason="playwright chromium not available")
def test_bound_deck_renders_native_pptx_with_trace(tmp_path):
    import os
    from pptx import Presentation
    from factdeck.template_lib import pipeline
    os.environ["FACTDECK_JOB_STATS_DB"] = str(tmp_path / "stats.sqlite")
    bad = template_page()
    bad["id"] = "p6"
    bad["template"]["fill"]["rows"][0]["est"] = 0.71                    # unbacked → not rendered, reported
    plan = integrate.deck_plan({"title": "绑定样例", "pages": [template_page(), bad]})
    rec = pipeline.run(plan, tmp_path / "out", facts=FACTS, sources=SOURCES, previews=False)
    ok, refused = rec["pages"]
    assert ok["status"] == "OK" and ok["rendered_layout"] == "forest_plot" and not ok.get("qa_issues")
    assert refused["status"] == "FILL_UNBOUND" and any("0.71" in e for e in refused["errors"])
    prs = Presentation(rec["native"]["pptx"])
    slide = prs.slides[0]
    shown = " ".join(sh.text_frame.text for sh in slide.shapes if sh.has_text_frame)
    assert "≥300" in shown and "示例数据" not in shown and bind.BOUND_NOTE in shown
    notes = slide.notes_slide.notes_text_frame.text
    assert "【溯源】t.r3：某研究 52 周结果 · 表 3 · p. 26" in notes
    md = (tmp_path / "out" / "trace.md").read_text(encoding="utf-8")
    assert "第 1 页 · p5" in md and "第 2 页 · p6" in md and "未渲染" in md
    tr = json.loads((tmp_path / "out" / "trace.json").read_text(encoding="utf-8"))
    assert tr["bound"] and len(tr["pages"]) == 2
