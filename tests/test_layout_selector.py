"""Layout selector: relation classifier, minimum-data downgrade, deck rhythm, tie-break constraint."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from factdeck.template_lib import selector as S

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "factdeck" / "examples" / "copd_layout_sample" / "plan.json"

TK3 = [{"value": "0.58", "text": "亚组 A"}, {"value": "0.94", "text": "亚组 B"}, {"value": "0.70", "text": "总体"}]


def top(page):
    return S.classify(page)[0]


def chosen(result, i):
    return result["decisions"][i]["chosen"]["layout"]


# ------------------------------------------------------------------ classifier

@pytest.mark.parametrize("page,relation", [
    ({"title": "如果支气管舒张后 FEV1/FVC < 0.70，则确诊；否则考虑其他诊断"}, "conditional"),
    ({"title": "If post-BD FEV1/FVC < 0.70 then confirm COPD, otherwise re-evaluate (threshold)"}, "conditional"),
    ({"title": "随机、双盲、安慰剂对照 III 期研究", "text": ["入组 900 例，n = 450 / 450", "治疗 52 周，主要终点为加重年化率"]},
     "trial_setup"),
    ({"title": "Randomized double-blind placebo-controlled phase 3 trial",
      "text": ["Enrolled n = 939 patients", "52 weeks treatment; primary endpoint exacerbation rate"]}, "trial_setup"),
    ({"title": "亚组分析", "text": ["≥300：RR 0.58（0.45–0.75）", "<150：RR 0.94（0.66–1.34）",
                                  "≥65 岁：RR 0.68（0.52–0.89）", "95% CI"]}, "effect_sizes"),
    ({"title": "Subgroup hazard ratios", "text": ["HR 0.71 (0.60-0.84)", "HR 0.80 (0.62-1.03)", "HR 0.65 (0.50-0.85)",
                                                   "95% CI"]}, "effect_sizes"),
    ({"title": "上皮损伤释放 TSLP，激活 ILC2，通过 IL-5 引起嗜酸粒细胞募集，导致急性加重"}, "mechanism"),
    ({"title": "Allergen exposure activates epithelium, releases alarmins and leads to eosinophilic inflammation via IL-5"},
     "mechanism"),
    ({"title": "急性加重期与稳定期对照", "text": ["与稳定期相比，加重期需评估感染"]}, "contrast"),
    ({"title": "疑诊到确诊的四步路径", "text": ["首先询问危险因素", "然后体检", "随后肺功能", "最后综合评估"]}, "sequence"),
    ({"title": "一例患者就诊病程", "text": ["D0 就诊", "D1 检查", "D3 治疗", "W4 随访"]}, "chronology"),
    ({"title": "本节小结", "text": ["结论一", "结论二"]}, "takeaways"),
    ({"title": "COPD 研究格局", "text": ["10 项 III 期研究", "2027 年读出", "进行中"]}, "landscape"),
    ({"title": "随便几句话", "text": ["一些说明"]}, "points"),
])
def test_classifier_detects_relation_zh_en(page, relation):
    r = top(page)
    assert r.relation == relation
    assert r.score > 0 and r.signals            # every classification carries matched signals


def test_classifier_returns_all_relations_with_scores():
    rels = S.classify({"title": "如果 eos ≥ 300 则加用 ICS"})
    assert {r.relation for r in rels} == set(S.RELATIONS)
    assert rels == sorted(rels, key=lambda r: -r.score)
    assert any("如果" in s for s in rels[0].signals)


def test_structured_data_drives_matrix_and_dual_path():
    m = {"title": "分组", "data": {"axes": {"x": ["低症状", "高症状"], "y": ["低风险", "高风险"]},
                                 "cells": [{"label": "A"}, {"label": "B"}, {"label": "E"}]}}
    assert top(m).relation == "matrix"
    d = {"title": "随访调整", "data": {"paths": [{"label": "呼吸困难", "steps": ["a", "b"]},
                                             {"label": "加重", "steps": ["c", "d"]}]}}
    assert top(d).relation == "dual_path"


def test_over_time_series_maps_to_line_variant():
    page = {"title": "两组 FEV1 差值 P < 0.001", "data": {
        "series": [{"name": "A", "values": [0, 1, 2]}, {"name": "B", "values": [0, 2, 3]}],
        "x": [0, 12, 52], "stats": ["差值 82 mL"], "takeaways": TK3}}
    res = S.select_deck([page])
    assert chosen(res, 0) == "endpoint_readout/line"


# ---------------------------------------------------------- minimum data / downgrade

def forest_page(rows):
    return {"title": "亚组率比 RR（95% CI）", "text": ["亚组分析"],
            "data": {"effects": rows, "takeaways": TK3, "items": [{"heading": "x", "body": "y"}]}}


ROW = {"label": "a", "est": 0.7, "lo": 0.6, "hi": 0.8}


def test_forest_needs_three_rows_else_downgrades_and_never_fabricates():
    page = forest_page([dict(ROW), dict(ROW, label="b")])
    before = copy.deepcopy(page)
    res = S.select_deck([page])
    d = res["decisions"][0]
    assert d["chosen"]["layout"] != "forest_plot"
    dg = d["downgrades"][0]
    assert dg["from"] == "forest_plot" and "≥3" in dg["reason"]
    assert any(p.startswith("data_table_highlight") for p in dg["path"])   # chain walked
    assert page == before                                                  # input untouched
    ok = forest_page([dict(ROW, label=x) for x in "abc"])
    assert chosen(S.select_deck([ok]), 0) == "forest_plot"


def test_forest_rejects_inconsistent_ci():
    bad = forest_page([dict(ROW, label=x) for x in "ab"] + [{"label": "c", "est": 0.9, "lo": 1.0, "hi": 1.2}])
    assert "下限" in S.requirement_gap("forest_plot", bad)


def test_endpoint_needs_two_arms_else_evidence_or_key_points():
    page = {"title": "研究药使年化率降低 30%，P < 0.001", "text": ["主要终点"],
            "data": {"series": [{"name": "研究药", "values": [0.77]}], "categories": ["ITT"],
                     "stats": ["P < 0.001"], "items": [{"heading": "−30%", "body": "降低"}]}}
    d = S.select_deck([page])["decisions"][0]
    assert d["chosen"]["layout"] == "key_points"
    assert d["downgrades"][0]["from"] == "endpoint_readout/bar"
    assert "两组" in d["downgrades"][0]["reason"]
    # With 3–4 verbatim number-led takeaways the chain stops at evidence takeaways.
    page["data"]["takeaways"] = [dict(t, quote="原文", loc="p.1") for t in TK3]
    assert chosen(S.select_deck([page]), 0) == "key_points/evidence_takeaways"


def test_matrix_needs_two_axes_with_two_tiers():
    page = {"title": "ABE 矩阵", "data": {"axes": {"x": ["低", "高"], "y": ["仅一层"]}, "cells": [1, 2, 3]}}
    assert "2 个轴" in S.requirement_gap("assessment_matrix", page)
    page["data"]["axes"]["y"] = ["低风险", "高风险"]
    assert S.requirement_gap("assessment_matrix", page) is None


def test_trial_design_needs_arms_and_n_or_duration():
    page = {"title": "随机双盲 52 周", "data": {"timepoints": [-4, 0, 52], "takeaways": TK3,
                                            "steps": [{"when": w, "heading": h} for w, h in
                                                      [("−4 周", "筛选"), ("0", "随机"), ("52 周", "结束"), ("64 周", "随访")]]}}
    assert "治疗臂" in S.requirement_gap("trial_design", page)
    assert chosen(S.select_deck([page]), 0) == "timeline"
    page["data"]["arms"] = [{"name": "A"}, {"name": "B"}]
    assert "n 或治疗时长" in S.requirement_gap("trial_design", page)
    page["data"]["duration_weeks"] = 52
    assert S.requirement_gap("trial_design", page) is None


def test_swimlane_needs_three_dated_items():
    items = [{"label": "s1", "group": "A", "start": 2020, "end": 2023, "status": "met"},
             {"label": "s2", "group": "B", "start": 2021, "end": 2024, "status": "ongoing"}]
    page = {"title": "研究格局", "data": {"timed_items": items, "takeaways": TK3}}
    assert "≥3" in S.requirement_gap("landscape_swimlane", page)
    items.append({"label": "s3", "group": "B", "start": 2022, "end": 2025, "status": "not_met"})
    assert S.requirement_gap("landscape_swimlane", page) is None


def test_data_table_needs_three_rows_and_at_most_one_highlight():
    rows = [{"label": f"r{i}", "cells": ["1", "2"]} for i in range(12)]
    page = {"title": "基线特征表", "data": {"table": {"columns": ["A", "B"], "rows": rows}, "takeaways": TK3}}
    assert S.requirement_gap("data_table_highlight", page) is None          # no highlight: the source names none
    rows[3]["highlight"] = rows[4]["highlight"] = True
    assert "至多" in S.requirement_gap("data_table_highlight", page)
    rows[4]["highlight"] = False
    page["data"]["table"]["rows"] = rows[:2]
    assert "≥3" in S.requirement_gap("data_table_highlight", page)
    # a teaching table (drug × target × approval) qualifies without the number-led rail
    page["data"]["table"]["rows"], page["data"]["takeaways"] = rows[:6], []
    assert S.requirement_gap("data_table_highlight", page) is None
    page["data"]["takeaways"] = TK3[:1]
    assert "右栏" in S.requirement_gap("data_table_highlight", page)


def test_nothing_qualifies_falls_back_with_note():
    d = S.select_deck([{"title": "", "text": []}])["decisions"][0]
    assert d["chosen"]["layout"] == "key_points"
    assert "人工" in d["reason_zh"]


# ------------------------------------------------------------------------- rhythm

def timeline_page(pid):
    return {"id": pid, "title": "病程", "data": {"steps": [{"when": f"D{i}", "heading": f"h{i}"} for i in range(4)]}}


def test_no_same_layout_on_consecutive_content_pages():
    res = S.select_deck([timeline_page("a"), timeline_page("b"), timeline_page("c")])
    lays = [d["chosen"]["layout"] for d in res["decisions"]]
    assert lays == ["timeline", "flow", "timeline"]
    assert res["decisions"][1]["rhythm_adjustments"][0]["rule"] == "no_repeat"
    assert res["stats"]["consecutive_repeats"] == []


def test_cover_and_section_are_exempt():
    pages = [{"id": "c", "kind": "cover", "title": "封面"}, timeline_page("a"),
             {"id": "s", "kind": "section", "title": "第二章"}, {"id": "s2", "kind": "section", "title": "第三章"}]
    res = S.select_deck(pages)
    assert [d["chosen"]["layout"] for d in res["decisions"]] == ["cover", "timeline", "section", "section"]
    assert res["stats"]["content_pages"] == 1


def test_repeat_kept_when_no_qualified_alternative():
    p = {"title": "要点", "data": {"items": [{"heading": "a"}]}}
    res = S.select_deck([dict(p, id="1"), dict(p, id="2")])
    assert [d["chosen"]["layout"] for d in res["decisions"]] == ["key_points", "key_points"]
    assert res["decisions"][1]["rhythm_adjustments"][0]["rule"] == "no_repeat_unresolved"


def test_chart_ratio_promotes_qualified_chart_candidate():
    page = {"title": "A vs B 对照：与对照组相比的区别", "text": ["推荐 vs 不推荐", "两组对照", "差异"],
            "data": {"sides": [{"label": "A", "items": ["x"]}, {"label": "B", "items": ["y"]}],
                     "effects": [dict(ROW, label=x) for x in "abc"], "takeaways": TK3}}
    first = S.select_deck([page])["decisions"][0]
    assert first["chosen"]["layout"] == "forest_plot" or any(
        c["layout"] == "forest_plot" for c in first["candidates"] if c.get("qualified"))
    kp = {"title": "要点", "data": {"items": [{"heading": "a"}]}}
    pages = [dict(page, id="1"), dict(kp, id="2"), dict(page, id="3")]
    res = S.select_deck(pages)
    assert res["stats"]["chart_pages"] == 1 and res["stats"]["chart_target_met"]
    assert res["stats"]["chart_promotions"]
    promoted = [d for d in res["decisions"] if d["page_id"] in res["stats"]["chart_promotions"]][0]
    assert promoted["chosen"]["layout"] == "forest_plot"
    assert promoted["rhythm_adjustments"][-1]["rule"] == "chart_ratio"
    assert res["stats"]["consecutive_repeats"] == []


def test_chart_ratio_not_forced_without_qualified_charts():
    pages = [{"id": str(i), "title": "要点", "data": {"items": [{"heading": "a"}]}} for i in range(3)]
    res = S.select_deck(pages)
    assert res["stats"]["chart_pages"] == 0 and not res["stats"]["chart_target_met"]


# --------------------------------------------------------------- tie-break constraint

CLOSE = {"id": "t", "title": "x", "data": {"sides": [{"label": "A", "items": ["1"]}, {"label": "B", "items": ["2"]}],
                                         "steps": [{"heading": "s1"}, {"heading": "s2"}, {"heading": "s3"}]}}


def test_constrain_choice_accepts_only_candidates():
    assert S.constrain_choice('{"layout":"flow","reason":"顺序关系"}', ["flow", "comparison"]) == ("flow", "顺序关系")
    assert S.constrain_choice(("comparison", "对照"), ["flow", "comparison"])[0] == "comparison"
    lay, why = S.constrain_choice('{"layout":"forest_plot","reason":"x"}', ["flow", "comparison"])
    assert lay is None and "不在候选集" in why
    assert S.constrain_choice("not json", ["flow"])[0] is None
    assert S.constrain_choice('```json\n{"layout":"flow","reason":"a\\nb"}\n```', ["flow"]) == ("flow", "a b")


def test_tiebreaker_only_called_when_close_and_result_constrained():
    calls = []

    def bad(page, cands):
        calls.append([c["layout"] for c in cands])
        return '{"layout": "forest_plot", "reason": "编造"}'

    res = S.select_deck([CLOSE], tiebreaker=bad)
    d = res["decisions"][0]
    assert calls and set(calls[0]) == {"comparison", "flow"}
    assert d["tie_break"]["method"] == "deterministic" and "rejected" in d["tie_break"]
    assert d["chosen"]["layout"] in {"comparison", "flow"}

    good = S.make_llm_tiebreaker(lambda system, user: '{"layout":"flow","reason":"步骤更清楚"}')
    d2 = S.select_deck([CLOSE], tiebreaker=good)["decisions"][0]
    assert d2["chosen"]["layout"] == "flow" and d2["tie_break"]["method"] == "llm"

    def boom(page, cands):
        raise RuntimeError("offline")
    d3 = S.select_deck([CLOSE], tiebreaker=boom)["decisions"][0]
    assert d3["tie_break"]["method"] == "deterministic"

    calls.clear()
    clear_page = {"title": "x", "data": {"effects": [dict(ROW, label=c) for c in "abc"], "takeaways": TK3}}
    S.select_deck([clear_page], tiebreaker=bad)
    assert calls == []                                   # not close → no tie-break call


def test_llm_prompt_lists_only_candidates():
    system, user = S.llm_prompt(CLOSE, [{"layout": "flow", "score": 3, "signals": []}])
    assert "候选" in system
    assert json.loads(user)["candidates"][0]["layout"] == "flow"


def test_deterministic_default_is_repeatable():
    a = S.select_deck([CLOSE, CLOSE])
    b = S.select_deck([CLOSE, CLOSE])
    assert a == b
    assert a["decisions"][0]["chosen"]["layout"] != a["decisions"][1]["chosen"]["layout"]


# ------------------------------------------------------------------- record / report

def test_decision_record_fields_and_report():
    res = S.select_deck([timeline_page("a"), timeline_page("b")])
    d = res["decisions"][1]
    for k in ("relation", "relation_zh", "signals", "candidates", "downgrades", "tie_break",
              "rhythm_adjustments", "chosen", "reason_zh"):
        assert k in d
    assert d["reason_zh"] and "\n" not in d["reason_zh"]
    md = S.report_markdown(res)
    assert "| 页码 | 内容摘要 | 识别出的关系 | 命中信号 | 候选（分数） | 降级 | 最终版式 | 理由 |" in md
    assert "图表页" in md


# ---------------------------------------------------------------------- COPD sample

@pytest.mark.skipif(not PLAN.is_file(), reason="COPD plan not generated")
def test_copd_sample_selection():
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    for p in plan["pages"] + plan["stress_pages"]:
        assert "origin_layout" not in json.dumps(p.get("data"))       # selector input carries no layout hint
    res = S.select_deck([{k: v for k, v in p.items() if k not in ("origin_layout", "fills")} for p in plan["pages"]])
    st = res["stats"]
    assert st["chart_ratio"] >= 1 / 3 and st["consecutive_repeats"] == []
    same = sum(p["origin_layout"] == d["chosen"]["layout"] for p, d in zip(plan["pages"], res["decisions"]))
    assert same >= len(plan["pages"]) - 2
    stress = S.select_deck(plan["stress_pages"])
    assert all(d["downgrades"] for d in stress["decisions"])
    assert not any(d["chosen"]["is_chart"] for d in stress["decisions"])
