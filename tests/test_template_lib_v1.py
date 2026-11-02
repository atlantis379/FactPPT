"""Template Library v1: slot contract + HTML render with Chinese sample content.

No PowerPoint / ImageGen / Adobe. Content is teaching-fixture text, not clinical advice.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from factdeck import template_lib as tl
from factdeck.template_lib import slots as slotmod

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "factdeck" / "template_lib"


# --- Chinese respiratory-teaching fixtures (validation only) -----------------

COVER_ZH = {
    "id": "cover-copd",
    "kicker": "呼吸内科教学",
    "title": "慢性阻塞性肺疾病的诊疗要点",
    "subtitle": "以指南结构组织课堂主线",
    "affiliation": "示意单位 · 呼吸与危重症医学科",
    "presenter": "示意讲者",
    "meta": "教学示意课件  |  2026.10",
}

SECTION_ZH = {
    "id": "sec-02",
    "number": "2",
    "title": "病理生理要点",
    "subtitle": "气流受限、气道炎症与肺气肿改变",
}

KEY3_ZH = {
    "id": "kp-3",
    "section": "COPD · 诊断",
    "title": "诊断与评估三点",
    "items": [
        {"tag": "症状", "heading": "呼吸困难", "sub": "活动后", "body": "进行性加重，需排除其他心肺疾病"},
        {"tag": "检查", "heading": "肺功能", "sub": "金标准", "body": "吸入支气管舒张剂后 FEV1/FVC < 0.70"},
        {"tag": "评估", "heading": "综合分级", "sub": "GOLD", "body": "结合症状负担与急性加重频率"},
    ],
    "takeaway": "肺功能是确认持续气流受限的关键依据",
    "source": "教学示意 · 非诊疗建议",
    "page": "03",
}

KEY6_ZH = {
    "id": "kp-6",
    "section": "COPD · 管理",
    "title": "稳定期管理六要点",
    "items": [
        {"tag": "戒烟", "heading": "戒烟干预", "body": "最有效减缓肺功能下降的措施"},
        {"tag": "疫苗", "heading": "疫苗接种", "body": "流感与肺炎球菌等按指南建议"},
        {"tag": "药物", "heading": "支气管舒张", "body": "长效制剂改善症状与运动耐量"},
        {"tag": "吸入", "heading": "吸入技术", "body": "核对装置使用，减少残留与误用"},
        {"tag": "康复", "heading": "肺康复", "body": "运动训练与教育改善生活质量"},
        {"tag": "随访", "heading": "随访计划", "body": "症状、加重与合并症定期评估"},
    ],
    "takeaway": "非药物措施与吸入治疗同样关键",
    "page": "08",
}


def test_manifest_declares_cover_section_keypoints_and_cc_by():
    m = tl.load_manifest()
    assert m["library_id"] == "factdeck.template_lib.v1"
    assert "premium_clinical" in m["themes"]
    assert m["version"].startswith("1.")  # 1.2 craft + 1.3 GOLD density
    assert set(m["families"]) >= {"cover", "section", "key_points"}
    assert m["families"]["key_points"]["capacity"]["cards_3"] == 3
    assert m["families"]["key_points"]["capacity"]["cards_6"] == 6
    assert "cards_4" in m["families"]["key_points"]["variants"]
    assert m["source_layout"]["license"] == "CC-BY-4.0"
    assert "SNUBH" in m["source_layout"]["branding_stripped"]
    assert "reference only" in m["academic_reference_only"]["note"].lower() or "reference-only" in m["academic_reference_only"]["note"].lower() or "参考" in m["academic_reference_only"]["note"] or "NOT" in m["academic_reference_only"]["note"]


def test_attribution_and_license_files_exist():
    assert (LIB / "ATTRIBUTION.md").is_file()
    text = (LIB / "ATTRIBUTION.md").read_text(encoding="utf-8")
    assert "CC BY 4.0" in text or "CC-BY-4.0" in text
    assert "medical-ppt-design" in text
    assert "SNUBH" in text  # documents stripping
    assert (LIB / "third_party" / "medical-ppt-design" / "LICENSE").is_file()
    assert (ROOT / "docs" / "TEMPLATE_LIB_V1.md").is_file()


def test_journal_and_steel_themes_match_academic_seeds():
    from app.academic_templates import STYLES

    seeds = {s[0]: s for s in STYLES}
    j = tl.get_theme("journal")
    s = tl.get_theme("steel")
    assert j["accent"].upper() == "#" + seeds["journal"][2]
    assert j["canvas"].upper() == "#" + seeds["journal"][3]
    assert j["ink"].upper() == "#" + seeds["journal"][4]
    assert s["accent"].upper() == "#" + seeds["steel"][2]
    assert s["canvas"].upper() == "#" + seeds["steel"][3]
    assert s["ink"].upper() == "#" + seeds["steel"][4]
    # FactDeck CSS vars used by deck.html.j2 token system
    for t in (j, s):
        for key in ("ink", "primary", "primary2", "accent", "accent2", "accent-on-dark", "soft", "sky", "line", "muted"):
            assert key in t and t[key].startswith("#")


def test_premium_clinical_theme_tokens_and_list_order():
    t = tl.get_theme("premium_clinical")
    assert t["ink"].startswith("#")
    assert t["accent"] == "#1A6B7C"
    assert t["canvas"] == "#F4F2EC"
    assert t["headline"] == t["ink"]
    for key in ("surface", "rail", "shadow", "takeaway-bg", "on-accent"):
        assert key in t
    themes = tl.list_themes()
    assert themes[0]["id"] == "gold_clinical" and themes[-1]["id"] == "premium_clinical"
    assert {x["id"] for x in themes} >= {"premium_clinical", "journal", "steel"}
    html = tl.render_page_html("cover", COVER_ZH, theme="premium_clinical")
    assert "data-theme=\"premium_clinical\"" in html
    assert "cover-band" in html
    assert "#1A6B7C" in html or "premium_clinical" in html


def test_premium_keypoints_use_rail_not_outline_pills():
    html = tl.render_page_html("key_points", KEY3_ZH, theme="premium_clinical")
    assert "is-lead" in html
    assert "border:1px solid #D9D9D9" not in html
    assert html.count("data-slot=\"heading\"") == 3
    assert "肺功能" in html


def test_inch_zones_map_to_1280x720():
    zones = tl.zone_map_px("cover")
    assert zones["title"]["x"] == pytest.approx(0.6 * 96, rel=0, abs=0.02)
    assert zones["title"]["y"] == pytest.approx(2.0512 * 96, rel=0, abs=0.02)
    body = tl.zone_map_px("key_points")["body_card"]
    assert body["w"] == pytest.approx(12.7946 * 96, rel=0, abs=0.05)
    assert body["x"] + body["w"] < 1280 + 1


@pytest.mark.parametrize("theme", ["premium_clinical", "journal", "steel"])
def test_cover_and_section_validate_and_render_chinese(theme):
    assert tl.validate_fill("cover", COVER_ZH)["ok"]
    assert tl.validate_fill("section", SECTION_ZH)["ok"]
    cover_html = tl.render_page_html("cover", COVER_ZH, theme=theme)
    section_html = tl.render_page_html("section", SECTION_ZH, theme=theme)
    assert "慢性阻塞性肺疾病" in cover_html
    assert "呼吸内科教学" in cover_html
    assert "病理生理要点" in section_html
    assert "data-family=\"cover\"" in cover_html
    assert "data-family=\"section\"" in section_html
    assert "SNUBH" not in cover_html and "분당" not in cover_html
    assert theme in cover_html or tl.get_theme(theme)["accent"] in cover_html


def test_key_points_3_and_6_variants():
    r3 = tl.validate_fill("key_points", KEY3_ZH)
    assert r3["ok"] and r3["variant"] == "cards_3"
    r6 = tl.validate_fill("key_points", KEY6_ZH)
    assert r6["ok"] and r6["variant"] == "cards_6"
    html3 = tl.render_page_html("key_points", KEY3_ZH, theme="journal")
    html6 = tl.render_page_html("key_points", KEY6_ZH, theme="steel")
    assert html3.count('data-slot="heading"') == 3
    assert html6.count('data-slot="heading"') == 6
    assert "肺功能" in html3
    assert "戒烟干预" in html6
    assert 'data-variant="cards_3"' in html3
    assert 'data-variant="cards_6"' in html6


def test_key_points_4_variant_and_over_capacity_refused():
    items4 = [{"tag": f"T{i}", "heading": f"要点{i}", "body": f"说明{i}"} for i in range(1, 5)]
    fill4 = {"title": "四要点示意", "items": items4}
    assert tl.validate_fill("key_points", fill4)["variant"] == "cards_4"
    html = tl.render_page_html("key_points", fill4, theme="journal")
    assert 'data-variant="cards_4"' in html

    too_many = {"title": "过量", "items": [{"heading": f"点{i}"} for i in range(7)]}
    bad = tl.validate_fill("key_points", too_many)
    assert not bad["ok"]
    with pytest.raises(ValueError, match="容量|拆页"):
        tl.normalize_fill("key_points", too_many)


def test_slot_overflow_reports_long_title():
    long_title = {"title": "中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中"}
    bad = tl.validate_fill("cover", long_title)
    assert not bad["ok"]
    assert any("title" in e for e in bad["errors"])


def test_deck_html_shell_and_write(tmp_path):
    pages = [
        {"family": "cover", "fill": COVER_ZH},
        {"family": "section", "fill": SECTION_ZH},
        {"family": "key_points", "fill": KEY3_ZH},
        {"family": "key_points", "fill": KEY6_ZH, "theme": "steel"},
    ]
    html = tl.render_deck_html(pages, theme="journal")
    assert html.count('class="slide') == 4
    assert "factdeck.template_lib.v1" in html
    out = tl.write_deck_html(pages, tmp_path / "tl_v1_demo.html", theme="journal")
    assert out.is_file() and "慢性阻塞性肺疾病" in out.read_text(encoding="utf-8")


def test_native_hook_points_to_native_builder():
    info = tl.native_describe()
    assert info["task"] == tl.T_TEMPLATE_NATIVE == "T_TEMPLATE_NATIVE"
    assert info["status"] == "native"
    prepared = tl.native_prepare("cover", COVER_ZH, theme="journal")
    assert prepared["status"] == "prepared"
    assert prepared["native"]["status"] == "ready"
    assert prepared["page"]["title"] == COVER_ZH["title"]
    assert prepared["native"]["shapes"] == []


def test_no_snubh_branding_in_shipped_templates():
    for path in (LIB / "html").glob("*.j2"):
        text = path.read_text(encoding="utf-8")
        assert "SNUBH" not in text and "SNUH" not in text
        assert "분당" not in text and "박상민" not in text
    art = json.loads((LIB / "artwork" / "paths.stub.json").read_text(encoding="utf-8"))
    assert art == {} or art.get("paths") in (None, [], {})


def test_html_templates_exist_for_all_manifest_families():
    m = tl.load_manifest()
    for fam, spec in m["families"].items():
        assert (LIB / "html" / spec["html"]).is_file(), fam


# --- Non-card logic layouts (comparison / flow / timeline) --------------------

CMP_DUAL_ZH = {
    "id": "cmp-ae-stable",
    "section": "COPD · 对照",
    "title": "急性加重期与稳定期对照",
    "left_label": "急性加重",
    "right_label": "稳定期",
    "left_items": [
        {"text": "呼吸困难急性加重或痰量脓性增加"},
        {"text": "需评估是否合并感染与呼吸衰竭"},
        {"text": "短期全身糖皮质激素可缩短恢复"},
        {"text": "抗菌药物用于有感染指征者"},
    ],
    "right_items": [
        {"text": "症状相对平稳，活动耐量可评估"},
        {"text": "以长效支气管舒张剂维持治疗"},
        {"text": "强调戒烟、疫苗与肺康复"},
        {"text": "定期随访加重频率与合并症"},
    ],
    "takeaway": "加重期抢救症状，稳定期减少未来加重",
    "source": "教学示意 · 非诊疗建议",
    "page": "12",
}

CMP_TABLE_ZH = {
    "id": "cmp-rec",
    "section": "COPD · 推荐",
    "title": "推荐与不推荐对照",
    "left_label": "推荐",
    "right_label": "不推荐",
    "rows": [
        {"left": "支气管舒张剂吸入作为基石", "right": "长期口服糖皮质激素维持"},
        {"left": "有指征时联合 ICS", "right": "经验性长期广谱抗菌预防"},
        {"left": "戒烟与疫苗接种", "right": "忽视吸入装置核查"},
        {"left": "肺康复与随访计划", "right": "仅靠短效缓解剂长期控制"},
    ],
    "takeaway": "稳定期管理优先可验证的非药物与吸入方案",
    "page": "13",
}

FLOW4_ZH = {
    "id": "flow-dx",
    "section": "COPD · 诊断路径",
    "title": "疑诊到确诊的四步路径",
    "nodes": [
        {"tag": "问诊", "heading": "危险因素", "body": "吸烟史与症状询问"},
        {"tag": "体检", "heading": "体征筛查", "body": "呼吸音与呼吸形态"},
        {"tag": "检查", "heading": "肺功能", "body": "舒张后 FEV1/FVC"},
        {"tag": "分级", "heading": "综合评估", "body": "症状与加重史"},
    ],
    "takeaway": "肺功能是确认持续气流受限的关键步骤",
    "page": "14",
}

FLOW6_ZH = {
    "id": "flow-step",
    "section": "COPD · 阶梯治疗",
    "title": "稳定期阶梯治疗六节点",
    "nodes": [
        {"heading": "评估", "body": "症状与表型"},
        {"heading": "戒烟", "body": "行为与药物"},
        {"heading": "疫苗", "body": "流感/肺炎球菌"},
        {"heading": "支气管舒张", "body": "长效吸入"},
        {"heading": "加用 ICS", "body": "有指征时"},
        {"heading": "随访", "body": "加重与依从"},
    ],
    "page": "15",
}

TL4_ZH = {
    "id": "tl-case4",
    "section": "病例 · 时间轴",
    "title": "一例 COPD 患者就诊病程",
    "nodes": [
        {"label": "D0", "heading": "就诊", "body": "活动后气促加重"},
        {"label": "D1", "heading": "检查", "body": "肺功能与胸片"},
        {"label": "D3", "heading": "治疗", "body": "启动吸入方案"},
        {"label": "W4", "heading": "随访", "body": "症状与装置复查"},
    ],
    "takeaway": "首诊确认气流受限后尽早进入维持与随访",
    "page": "16",
}

TL6_ZH = {
    "id": "tl-case6",
    "section": "病例 · 时间轴",
    "title": "从加重到稳定的六节点病程",
    "nodes": [
        {"label": "就诊", "heading": "急诊", "body": "气促与脓痰"},
        {"label": "检验", "heading": "感染评估", "body": "血常规与血气"},
        {"label": "影像", "heading": "胸片/CT", "body": "排除气胸肺炎"},
        {"label": "治疗", "heading": "加重处理", "body": "氧疗与短程激素"},
        {"label": "出院", "heading": "方案调整", "body": "长效吸入衔接"},
        {"label": "随访", "heading": "门诊复查", "body": "加重诱因教育"},
    ],
    "page": "17",
}


def test_manifest_declares_comparison_flow_timeline():
    m = tl.load_manifest()
    assert set(m["families"]) >= {"cover", "section", "key_points", "comparison", "flow", "timeline"}
    assert m["families"]["comparison"]["pattern"].startswith("C-")
    assert m["families"]["flow"]["pattern"].startswith("K-")
    assert m["families"]["timeline"]["pattern"].startswith("J-")
    assert m["families"]["flow"]["capacity"]["horizontal_6"] == 6
    assert m["families"]["timeline"]["capacity"]["nodes_4"] == 4
    assert "table_2n" in m["families"]["comparison"]["variants"]
    # Cards remain; new families are additive
    assert "cards_3" in m["families"]["key_points"]["variants"]


@pytest.mark.parametrize("theme", ["premium_clinical", "journal", "steel"])
def test_comparison_dual_column_renders_not_cards(theme):
    r = tl.validate_fill("comparison", CMP_DUAL_ZH)
    assert r["ok"] and r["variant"] == "dual_column"
    html = tl.render_page_html("comparison", CMP_DUAL_ZH, theme=theme)
    assert 'data-family="comparison"' in html
    assert 'data-variant="dual_column"' in html
    assert "急性加重" in html and "稳定期" in html
    assert "pillar" not in html.lower()
    assert 'data-slot="left_items"' in html and 'data-slot="right_items"' in html
    assert html.count('data-shape="column-divider"') == 1
    assert "SNUBH" not in html


def test_comparison_table_2n_variant():
    r = tl.validate_fill("comparison", CMP_TABLE_ZH)
    assert r["ok"] and r["variant"] == "table_2n"
    html = tl.render_page_html("comparison", CMP_TABLE_ZH, theme="journal")
    assert 'data-variant="table_2n"' in html
    assert html.count("<tr") >= 5  # header + 4 rows
    assert "推荐" in html and "不推荐" in html
    assert "pillar" not in html.lower()


@pytest.mark.parametrize("theme", ["premium_clinical", "journal", "steel"])
def test_flow_horizontal_and_capacity(theme):
    r4 = tl.validate_fill("flow", FLOW4_ZH)
    assert r4["ok"] and r4["variant"] == "horizontal_4"
    html4 = tl.render_page_html("flow", FLOW4_ZH, theme=theme)
    assert 'data-family="flow"' in html4
    assert 'data-orientation="horizontal"' in html4
    assert html4.count('data-slot="heading"') == 4
    assert html4.count('data-shape="connector"') == 3
    assert "诊断路径" in html4 or "四步路径" in html4
    assert "pillar" not in html4.lower()

    r6 = tl.validate_fill("flow", FLOW6_ZH)
    assert r6["ok"] and r6["variant"] == "horizontal_6"
    html6 = tl.render_page_html("flow", FLOW6_ZH, theme=theme)
    assert html6.count('data-slot="heading"') == 6

    vertical = dict(FLOW4_ZH, id="flow-v")
    rv = tl.validate_fill("flow", vertical, variant="vertical_4")
    assert rv["ok"] and rv["variant"] == "vertical_4"
    htmlv = tl.render_page_html("flow", vertical, theme=theme, variant="vertical_4")
    assert 'data-orientation="vertical"' in htmlv

    too_many = {"title": "过量流程", "nodes": [{"heading": f"步{i}"} for i in range(7)]}
    bad = tl.validate_fill("flow", too_many)
    assert not bad["ok"]
    with pytest.raises(ValueError, match="容量|拆页"):
        tl.normalize_fill("flow", too_many)


@pytest.mark.parametrize("theme", ["premium_clinical", "journal", "steel"])
def test_timeline_milestone_track_not_cards(theme):
    r4 = tl.validate_fill("timeline", TL4_ZH)
    assert r4["ok"] and r4["variant"] == "nodes_4"
    html4 = tl.render_page_html("timeline", TL4_ZH, theme=theme)
    assert 'data-family="timeline"' in html4
    assert 'data-pattern="J-timeline-milestone"' in html4
    assert html4.count('data-shape="milestone-dot"') == 4
    assert "就诊" in html4 and "随访" in html4
    assert "pillar" not in html4.lower()

    r6 = tl.validate_fill("timeline", TL6_ZH)
    assert r6["ok"] and r6["variant"] == "nodes_6"
    html6 = tl.render_page_html("timeline", TL6_ZH, theme=theme)
    assert html6.count('data-shape="milestone-dot"') == 6
    assert 'data-variant="nodes_6"' in html6

    too_many = {"title": "过长病程", "nodes": [{"label": f"T{i}", "heading": f"点{i}"} for i in range(7)]}
    bad = tl.validate_fill("timeline", too_many)
    assert not bad["ok"]


def test_deck_html_includes_logic_layouts(tmp_path):
    pages = [
        {"family": "comparison", "fill": CMP_DUAL_ZH},
        {"family": "flow", "fill": FLOW4_ZH},
        {"family": "timeline", "fill": TL4_ZH},
        {"family": "key_points", "fill": KEY3_ZH},  # cards still work
    ]
    html = tl.render_deck_html(pages, theme="journal")
    assert html.count('class="slide') == 4
    assert 'data-family="comparison"' in html
    assert 'data-family="flow"' in html
    assert 'data-family="timeline"' in html
    assert 'data-family="key_points"' in html
    out = tl.write_deck_html(pages, tmp_path / "tl_v1_logic.html", theme="steel")
    assert out.is_file() and "急性加重" in out.read_text(encoding="utf-8")


# --- GOLD density layouts (algorithm / ABE matrix / dual-path) ---------------

ALGO_ZH = {
    "id": "gold-algo",
    "title": "疑诊 COPD → 肺功能确诊算法",
    "figure": "图 2.1",
    "takeaway": "支气管舒张后 FEV1/FVC < 0.70 是确认持续气流受限的关键阈值",
    "source": "Adapted from GOLD 2026 teaching materials (structure only)",
    "page": "01",
    "start_heading": "疑诊 COPD",
    "start_body": "症状 + 危险因素",
    "decision_heading": "支气管舒张试验后肺功能",
    "decision_threshold": "FEV1/FVC < 0.70（post-BD）",
    "yes_label": "是 · < 0.70",
    "yes_heading": "确认 COPD",
    "yes_body": "进入 ABE 评估",
    "no_label": "否 · ≥ 0.70",
    "no_heading": "考虑其他诊断",
    "no_items": ["哮喘", "支气管扩张", "充血性心衰"],
    "follow_nodes": [
        {"heading": "鉴别与合并症", "body": "影像与嗜酸粒细胞"},
        {"heading": "进入 ABE 评估", "body": "症状 × 加重史"},
    ],
}

ABE_ZH = {
    "id": "gold-abe",
    "title": "初始药物治疗：ABE 分组评估矩阵",
    "figure": "图 3.1",
    "x_left": "mMRC 0–1 · CAT < 10",
    "x_right": "mMRC ≥ 2 · CAT ≥ 10",
    "y_top": "≥2 次中度加重或 ≥1 次住院",
    "y_bottom": "0 或 1 次中度加重（未住院）",
    "e_label": "组别 E",
    "e_rx": "LABA + LAMA",
    "e_note": "血 eos ≥ 300 考虑 +ICS",
    "a_label": "组别 A",
    "a_rx": "一种支气管舒张剂",
    "b_label": "组别 B",
    "b_rx": "LABA + LAMA",
    "source": "Adapted from GOLD 2026 teaching materials (structure only)",
    "page": "02",
}

TX_ZH = {
    "id": "gold-tx",
    "title": "随访治疗调整：双路径升级树",
    "figure": "图 4.1",
    "left_label": "呼吸困难路径",
    "right_label": "急性加重路径",
    "left_nodes": [
        {"heading": "LABA 或 LAMA", "kind": "drug"},
        {"heading": "LABA + LAMA", "kind": "drug"},
        {"heading": "装置与鉴别", "body": "非药物与其他气促原因", "kind": "note"},
    ],
    "right_nodes": [
        {"heading": "LABA 或 LAMA", "kind": "drug"},
        {"heading": "LABA+LAMA+ICS", "kind": "split_left", "branch": "eos ≥ 300"},
        {"heading": "LABA + LAMA", "kind": "split_right", "branch": "eos < 300"},
        {"heading": "Roflumilast / Azithromycin", "kind": "end"},
    ],
    "source": "Adapted from GOLD 2026 teaching materials (structure only)",
    "page": "03",
}


def test_manifest_declares_gold_families_and_theme():
    m = tl.load_manifest()
    assert m["version"].startswith("1.3")
    assert "gold_clinical" in m["themes"]
    assert set(m["families"]) >= {
        "algorithm_tree", "assessment_matrix", "dual_path_tree",
        "cover", "key_points", "comparison", "flow", "timeline",
    }
    assert m["families"]["algorithm_tree"]["pattern"].startswith("GOLD-")
    assert m["families"]["assessment_matrix"]["pattern"].startswith("GOLD-")
    assert m["families"]["dual_path_tree"]["pattern"].startswith("GOLD-")
    t = tl.get_theme("gold_clinical")
    assert t["accent"] == "#C4A35A"
    assert t["primary"] == "#0B3A5C"
    assert t["canvas"] == "#FFFFFF"


def test_algorithm_tree_branch_not_cards():
    r = tl.validate_fill("algorithm_tree", ALGO_ZH)
    assert r["ok"] and r["variant"] == "branch_decision"
    html = tl.render_page_html("algorithm_tree", ALGO_ZH, theme="gold_clinical")
    assert 'data-family="algorithm_tree"' in html
    assert 'data-pattern="GOLD-algorithm-branch"' in html
    assert "FEV1/FVC" in html and "0.70" in html
    assert 'data-shape="yes-branch"' in html and 'data-shape="no-branch"' in html
    assert "is-dashed" in html
    assert "pillar" not in html.lower()
    assert "is-lead" not in html  # no premium card lead gradient


def test_assessment_matrix_abe_thresholds():
    r = tl.validate_fill("assessment_matrix", ABE_ZH)
    assert r["ok"] and r["variant"] == "abe_2x2"
    html = tl.render_page_html("assessment_matrix", ABE_ZH, theme="gold_clinical")
    assert 'data-family="assessment_matrix"' in html
    assert 'data-shape="abe-matrix"' in html
    assert "mMRC" in html and "CAT" in html
    assert "组别 E" in html and "组别 A" in html and "组别 B" in html
    assert "eos ≥ 300" in html or "eos" in html
    assert "pillar" not in html.lower()
    # 版式本身不得携带任何主题内容：轴提示只能由填充提供
    assert 'class="axis-hint"' not in html
    hint_html = tl.render_page_html(
        "assessment_matrix", {**ABE_ZH, "x_hint": "症状负担", "y_hint": "加重史"},
        theme="gold_clinical",
    )
    assert 'class="axis-hint"' in hint_html and "症状负担" in hint_html and "加重史" in hint_html


def test_dual_path_tree_escalation_splits():
    r = tl.validate_fill("dual_path_tree", TX_ZH)
    assert r["ok"] and r["variant"] == "dyspnea_exacerbation"
    page = tl.normalize_fill("dual_path_tree", TX_ZH, theme="gold_clinical")
    assert any(s["type"] == "split" for s in page["right_steps"])
    html = tl.render_page_html("dual_path_tree", TX_ZH, theme="gold_clinical")
    assert 'data-family="dual_path_tree"' in html
    assert 'data-shape="dyspnea-path"' in html
    assert 'data-shape="exacerbation-path"' in html
    assert 'data-shape="eos-split"' in html
    assert "呼吸困难" in html and "急性加重" in html
    assert "LABA" in html and "ICS" in html
    assert "pillar" not in html.lower()


def test_gold_deck_html_three_grammars(tmp_path):
    pages = [
        {"family": "algorithm_tree", "fill": ALGO_ZH},
        {"family": "assessment_matrix", "fill": ABE_ZH},
        {"family": "dual_path_tree", "fill": TX_ZH},
    ]
    html = tl.render_deck_html(pages, theme="gold_clinical")
    assert html.count('class="slide') == 3
    assert 'data-family="algorithm_tree"' in html
    assert 'data-family="assessment_matrix"' in html
    assert 'data-family="dual_path_tree"' in html
    assert html.count('data-shape="gold-accent"') == 3
    out = tl.write_deck_html(pages, tmp_path / "gold_copd.html", theme="gold_clinical")
    assert out.is_file() and "FEV1/FVC" in out.read_text(encoding="utf-8")
