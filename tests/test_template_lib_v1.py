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


def test_inch_zones_map_to_1280x720():
    zones = tl.zone_map_px("cover")
    assert zones["title"]["x"] == pytest.approx(0.6 * 96, rel=0, abs=0.02)
    assert zones["title"]["y"] == pytest.approx(2.0512 * 96, rel=0, abs=0.02)
    body = tl.zone_map_px("key_points")["body_card"]
    assert body["w"] == pytest.approx(12.7946 * 96, rel=0, abs=0.05)
    assert body["x"] + body["w"] < 1280 + 1


@pytest.mark.parametrize("theme", ["journal", "steel"])
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


def test_native_hook_is_stub_but_prepares_model():
    info = tl.native_describe()
    assert info["task"] == tl.T_TEMPLATE_NATIVE == "T_TEMPLATE_NATIVE"
    assert info["status"] == "stub"
    prepared = tl.native_prepare("cover", COVER_ZH, theme="journal")
    assert prepared["status"] == "prepared"
    assert prepared["native"]["status"] == "stub"
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
