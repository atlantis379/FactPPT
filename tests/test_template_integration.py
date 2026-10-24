"""Selector wired into the generation flow: proposals kept only when qualified, decisions recorded, subject
vocabulary from config (code stays domain-neutral).  Content is invented test data."""
from __future__ import annotations

import json
from pathlib import Path

from factdeck.deck import check
from factdeck.template_lib import integrate as I
from factdeck.template_lib import selector as S

from factdeck import facts as fx

UNITS = [{"id": "S1", "source_id": "S01", "location": "第2页", "text": "甲细胞释放乙因子，激活丙细胞"},
         {"id": "N1", "source_id": "S01", "location": "第4页", "text": "轻度"}]


def facts():
    F = lambda i, u, q: {"id": i, "unit": u, "quote": q}
    Fs, D, T = fx.parse({"facts": [F("c1", "S1", "甲细胞释放乙因子"), F("c2", "S1", "激活丙细胞"), F("k1", "N1", "轻度")]})
    fx.verify(Fs, D, UNITS, {}, T)
    return {f["id"]: f for f in fx.as_dict(Fs, D, [])["facts"]}

ROOT = Path(__file__).resolve().parents[1]
STEPS = {"title": "从筛查到随访的四步路径", "text": ["首先询问危险因素", "然后体检", "随后检查", "最后综合评估"],
         "data": {"steps": [{"heading": h} for h in ("询问", "体检", "检查", "评估")]}}


def page(pid, proposal=None, **kw):
    return {"id": pid, **STEPS, **({"proposed_layout": proposal} if proposal else {}), **kw}


def test_proposal_kept_when_selector_agrees():
    d = I.decide([page("a", "flow")])["decisions"][0]
    assert d["chosen"]["layout"] == "flow"
    assert d["proposal"]["status"] == "kept" and "保留" in d["proposal"]["reason_zh"]


def test_proposal_kept_when_qualified_but_not_first_choice():
    d = I.decide([page("a", "key_points")])["decisions"][0]
    assert d["proposal"]["selector_choice"] == "flow"
    assert "key_points" in d["proposal"]["qualified_candidates"]
    assert d["chosen"]["layout"] == "key_points" and d["proposal"]["status"] == "kept"
    assert "合格候选" in d["reason_zh"]


def test_unqualified_proposal_is_overridden_with_reason():
    res = I.decide([page("a", "endpoint_readout/bar"), page("b", "no_such_layout")])
    a, b = res["decisions"]
    assert a["proposal"]["status"] == "overridden" and a["chosen"]["layout"] != "endpoint_readout/bar"
    assert "最低数据要求" in a["proposal"]["reason_zh"]
    assert b["proposal"]["status"] == "overridden" and "未知版式" in b["proposal"]["reason_zh"]
    assert res["stats"]["proposals"]["overridden"] == ["a", "b"]


def test_alias_and_exempt_pages():
    assert I.normalize_layout("endpoint_bar") == ("endpoint_readout/bar",)
    assert I.normalize_layout("endpoint_readout") == ("endpoint_readout/bar", "endpoint_readout/line")
    d = I.decide([{"id": "c", "kind": "cover", "title": "封面", "proposed_layout": "flow"}])["decisions"][0]
    assert d["chosen"]["layout"] == "cover" and d["proposal"]["status"] == "exempt"


def test_page_record_carries_full_decision():
    rec = I.page_record(I.decide([page("a")])["decisions"][0])
    for k in ("layout", "relation", "signals", "candidates", "downgrades", "reason_zh", "proposal"):
        assert k in rec
    assert rec["proposal"]["status"] == "none"
    json.dumps(rec, ensure_ascii=False)


def test_resolve_fill_falls_back_to_qualified_candidate_only():
    d = I.decide([page("a")])["decisions"][0]
    lay, fill, why = I.resolve_fill({"fills": {"key_points": {"x": 1}}}, d)
    assert lay == "key_points" and fill == {"x": 1} and "合格候选" in why
    lay, fill, why = I.resolve_fill({"fills": {"forest_plot": {"x": 1}}}, d)
    assert fill is None and "未渲染" in why


def test_subject_vocabulary_lives_in_config_not_code():
    src = (ROOT / "factdeck" / "template_lib" / "selector.py").read_text(encoding="utf-8")
    generic = json.dumps(S.GENERIC_SIGNALS, ensure_ascii=False, default=str)
    for word in ("确诊", "双盲", "不良事件", "基线特征"):
        assert word not in generic
    cfg = json.loads((ROOT / "config" / "layout_signals.json").read_text(encoding="utf-8"))
    assert "trial_setup" in json.dumps(cfg, ensure_ascii=False)
    assert "COPD" not in src and "mMRC" not in src
    bare = S.load_signals(config=ROOT / "nonexistent.json")
    full = S.load_signals()
    assert sum(map(len, full.values())) > sum(map(len, bare.values()))
    proj = S.load_signals({"matrix": [{"name": "项目词", "patterns": ["甲乙丙"], "weight": 1.0}]})
    assert any(s.name == "项目词" for s in proj["matrix"])


def test_llm_tie_break_off_by_default():
    plan = json.loads((ROOT / "factdeck" / "examples" / "copd_layout_sample" / "plan.json").read_text(encoding="utf-8"))
    assert all(d["tie_break"] is None for d in I.decide(plan["pages"])["decisions"])


def test_deck_check_records_template_decisions():
    fs = facts()
    flow = {"id": "fl", "layout": "flow", "title": {"text": "机制路径"}, "nodes": [{"ref": {"fact": "c1"}}, {"ref": {"fact": "c2"}}],
            "edges": [{"from": 0, "to": 1}]}
    deck = {"pages": [dict(flow, template={"layout": "flow"}),
                      dict(flow, id="fl2", template={"layout": "forest_plot"}),
                      {"id": "plain", "layout": "bullets", "title": {"text": "无模板"}, "items": [{"fact": "k1"}]}]}
    res = check(deck, fs)
    tl = res["template_layouts"]
    assert set(tl["pages"]) == {"fl", "fl2"}                       # only opted-in pages
    assert tl["pages"]["fl2"]["proposal"]["status"] == "overridden"
    assert any("fl2" in w and "forest_plot" in w for w in res["warnings"])
    assert check({"pages": [dict(flow, template="flow")]}, fs)["deck_errors"]


def test_copd_plan_decisions_match_selector_baseline():
    plan = json.loads((ROOT / "factdeck" / "examples" / "copd_layout_sample" / "plan.json").read_text(encoding="utf-8"))
    res = I.decide(plan["pages"], extra_signals=plan.get("layout_signals"))
    sel = S.select_deck(plan["pages"], extra_signals=plan.get("layout_signals"))
    assert [d["chosen"]["layout"] for d in res["decisions"]] == [d["chosen"]["layout"] for d in sel["decisions"]]
    assert res["stats"]["chart_target_met"] and not res["stats"]["consecutive_repeats"]
