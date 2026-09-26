"""Tests for the page contract, the two narrative gates, and exhibit extraction.

These pin the stage 1-5 remediation: the gates must be able to FAIL (positive and
negative polarity), the exhibits must be extractive, and the deferred figures must
stay declared rather than silently missing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deckkit import exhibits as EX  # noqa: E402
from deckkit import narrative_gates as NG  # noqa: E402
from deckkit import page_contract as PC  # noqa: E402


def page(**kwargs) -> dict:
    base = {"type": "cards", "page_id": "p1", "section_label": "第一节", "chip": "流行病学",
            "title": "流行病学：四项关键数据", "source_ref": {"page": 46, "kind": "原文"},
            "primary_message": "CAP 与 HAP 的发病率差异显著", "display_intent": "SHOW_EVIDENCE",
            "cognitive_unit": "疾病负担有多大", "body_kind": "bullets",
            "cards": [{"title": "", "body": "短句。", "tone": ""}]}
    base.update(kwargs)
    return base


def deck(slides: list[dict]) -> dict:
    return {"meta": {"title": "t"}, "theme": "clinical", "slides": slides}


def test_deckkit_import_keeps_browser_rendering_optional(monkeypatch, tmp_path):
    """Pure deck contracts must remain usable without the optional browser stack."""
    import sys

    monkeypatch.setitem(sys.modules, "playwright", None)
    with pytest.raises(RuntimeError, match="optional deckkit HTML renderer"):
        import deckkit
        deckkit.render("unused.html", tmp_path / "rendered")


# --------------------------------------------------------------- page contract
def test_a_complete_page_passes():
    result = PC.check(deck([page()]))
    assert result["status"] == "PASS", result["detail"]


def test_missing_primary_message_blocks():
    slide = page()
    del slide["primary_message"]
    result = PC.check(deck([slide]))
    assert result["status"] == "BLOCK"
    assert any(i["gate"] == "GATE-PAGE-001" for i in result["detail"])


def test_prose_over_the_density_limit_is_flagged():
    slide = page(body_kind="text", cards=[], body="长" * 400)
    result = PC.check(deck([slide]))
    assert any(i["gate"] == "GATE-PAGE-003" for i in result["detail"])


def test_title_repeating_the_body_is_flagged():
    slide = page(title="肺炎是终末气道炎症")
    slide["cards"] = [{"title": "", "body": "肺炎是终末气道炎症，可由病原微生物所致。", "tone": ""}]
    result = PC.check(deck([slide]))
    assert any(i["gate"] == "GATE-PAGE-004" for i in result["detail"])


def test_independent_pages_sharing_a_message_are_flagged():
    one, two = page(), page(page_id="p2")
    result = PC.check(deck([one, two]))
    assert any(i["gate"] == "GATE-PAGE-002" for i in result["detail"])


def test_a_declared_continuation_is_not_a_duplicate():
    first = page()
    second = page(page_id="p1c2", continues="p1", title="流行病学（续 2）")
    result = PC.check(deck([first, second]))
    assert not any(i["gate"] == "GATE-PAGE-002" for i in result["detail"])


def test_section_without_a_closing_page_is_flagged():
    slides = [page(page_id=f"p{i}", primary_message=f"消息{i}") for i in range(3)]
    result = PC.check(deck(slides))
    assert any(i["gate"] == "GATE-PAGE-005" for i in result["detail"])


def test_a_short_section_needs_no_closing_page():
    slides = [page(page_id=f"p{i}", primary_message=f"消息{i}") for i in range(2)]
    result = PC.check(deck(slides))
    assert not any(i["gate"] == "GATE-PAGE-005" for i in result["detail"])


# ------------------------------------------------------------ narrative gates
def test_w06_gates_pass_a_well_formed_deck():
    slides = [
        {"type": "cover", "page_id": "c"},
        page(page_id="p1", display_intent="ORIENT", primary_message="导览",
             section_label="第一节"),
        page(page_id="p2", primary_message="内容一", section_label="第一节"),
        page(page_id="p3", display_intent="SUMMARIZE", primary_message="小结",
             section_label="第二节"),
        page(page_id="p4", display_intent="COMPARE", primary_message="对照",
             section_label="第二节"),
        {"type": "closing", "page_id": "z"},
    ]
    result = NG.audit(deck(slides))
    assert result["W06-NR"]["status"] == "PASS", result["W06-NR"]["issues"]
    assert result["W06-NP"]["status"] == "PASS", result["W06-NP"]["issues"]


def test_w06_nr_flags_a_deck_that_does_not_orient():
    slides = [{"type": "cover", "page_id": "c"},
              page(page_id="p1", display_intent="EXPLAIN"),
              {"type": "closing", "page_id": "z"}]
    result = NG.audit(deck(slides))
    assert result["W06-NR"]["status"] == "REVISIONS_REQUIRED"
    assert any(i["rule"] == "REG-NARR-003" for i in result["W06-NR"]["issues"])


def test_w06_nr_flags_an_ungrounded_page():
    slides = [{"type": "cover", "page_id": "c"},
              page(page_id="p1", display_intent="ORIENT", source_ref=None),
              {"type": "closing", "page_id": "z"}]
    result = NG.audit(deck(slides))
    assert any(i["rule"] == "REG-NARR-002" for i in result["W06-NR"]["issues"])


def test_w06_np_reports_emergent_page_count():
    slides = [{"type": "cover", "page_id": "c"},
              page(page_id="p1", display_intent="ORIENT"),
              {"type": "closing", "page_id": "z"}]
    result = NG.audit(deck(slides))
    assert result["W06-NP"]["page_count_status"] == "EMERGENT"


# ------------------------------------------------------------------ exhibits
BLOCKS = [
    {"page": 3, "text": "CURB-65共五项指标，由4项指标英文首字母与年龄65岁组成，"
                        "满足1项得1分：①意识障碍（confusion，C）；②尿素氮（uremia，U）>7mmol/L；"
                        "③呼吸频率（respiratoryrate，R）≥30次/分；④血压（bloodpressure，B），"
                        "收缩压<90mmHg或舒张压≤60mmHg；年龄≥65岁。"},
    {"page": 4, "text": "评分0~1分，原则上门诊治疗即可；2分建议住院或严格随访下的院外治疗；"
                        "3~5分应住院治疗。"},
    {"page": 1, "text": "（一）解剖分类1.大叶性（肺泡性）肺炎病原体先在肺泡引起炎症，"
                        "经肺泡间孔（Cohn孔）向其他肺泡扩散。致病菌多为肺炎链球菌。"
                        "X线影像显示肺叶或肺段的实变阴影。"},
    {"page": 2, "text": "2.小叶性（支气管性）肺炎病原体经支气管人侵，引起细支气管的炎症。"
                        "X线影像显示为沿着肺纹理分布的不规则斑片状阴影。"},
    {"page": 2, "text": "3.间质性肺炎以肺间质受累为主的炎症，累及支气管壁。"
                        "X线影像表现为一侧或双侧肺下部不规则阴影。"},
]


def test_curb65_is_extracted_verbatim_with_five_items():
    page_out = EX.curb65(BLOCKS)
    assert page_out is not None
    assert len(page_out["rows"]) == 5
    joined = " ".join(" ".join(row) for row in page_out["rows"])
    assert "尿素氮" in joined and "收缩压" in joined


def test_anatomical_matrix_collects_across_blocks():
    page_out = EX.anatomical_matrix(BLOCKS)
    assert page_out is not None
    assert len(page_out["rows"]) == 3
    names = [row[0] for row in page_out["rows"]]
    assert names == ["大叶性（肺泡性）", "小叶性（支气管性）", "间质性"]
    # every X线 cell must be keyword-anchored, never a guessed sentence
    for row in page_out["rows"]:
        assert "X线" in row[2]


def test_deferred_exhibits_are_declared_with_a_reason():
    deferred = EX.deferred_exhibits()
    assert len(deferred) == 2
    for entry in deferred:
        assert entry["reason"] and entry["requires"]


def test_exhibits_inherit_the_section_they_are_injected_into():
    slides = [{"type": "statement", "page_id": "p1", "section_label": "第一节 肺炎概述",
               "chip": "节引导", "title": "第一节 肺炎概述"}]
    result = EX.inject({"slides": slides}, BLOCKS, after={0: "第一节"})
    injected = [s for s in result["slides"] if s.get("type") == "matrix"]
    assert injected, "at least one exhibit should be injected"
    assert all(s["section_label"] == "第一节 肺炎概述" for s in injected)
