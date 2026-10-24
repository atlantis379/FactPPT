#!/usr/bin/env python3
"""Render GOLD-density COPD template previews → HTML + PNG (1280×720 @2x)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factdeck import template_lib as tl

OUT = Path("/workspace/sync/template-lib-gold")
THEME = "gold_clinical"
SRC = "Adapted from GOLD 2026 teaching materials (structure only) · 教学示意，非诊疗建议"

ALGO = {
    "id": "gold-algo",
    "section": "COPD · 诊断",
    "title": "疑诊 COPD → 肺功能确诊算法",
    "figure": "图 2.1",
    "takeaway": "支气管舒张后 FEV1/FVC < 0.70 是确认持续气流受限的关键阈值",
    "source": SRC,
    "page": "01",
    "start_heading": "疑诊 COPD",
    "start_body": "呼吸困难 / 慢性咳嗽咳痰 + 危险因素（吸烟、职业暴露、生物燃料等）",
    "decision_heading": "支气管舒张试验后肺功能",
    "decision_threshold": "FEV1/FVC < 0.70（post-BD）",
    "yes_label": "是 · 实线 · < 0.70",
    "yes_heading": "确认 COPD",
    "yes_body": "持续气流受限成立；进入综合评估（ABE）与分级",
    "no_label": "否 · 虚线 · ≥ 0.70",
    "no_heading": "考虑其他诊断 / 随访",
    "no_items": [
        "哮喘 / ACO",
        "支气管扩张",
        "充血性心衰",
        "肺结核后遗",
        "弥漫性泛细支气管炎",
        "闭塞性细支气管炎",
    ],
    "follow_nodes": [
        {"heading": "鉴别与合并症", "body": "影像、嗜酸粒细胞、心血管与肺癌筛查指征"},
        {"heading": "进入 ABE 评估", "body": "症状负担（mMRC/CAT）× 过去 1 年加重史"},
    ],
}

ABE = {
    "id": "gold-abe",
    "section": "COPD · 评估",
    "title": "初始药物治疗：ABE 分组评估矩阵",
    "figure": "图 3.1",
    "takeaway": "分组由症状负担与加重史共同决定；数值阈值必须写在图上",
    "source": SRC,
    "page": "02",
    "x_left": "mMRC 0–1  ·  CAT < 10",
    "x_right": "mMRC ≥ 2  ·  CAT ≥ 10",
    "y_top": "≥ 2 次中度加重\n或 ≥ 1 次导致住院",
    "y_bottom": "0 或 1 次中度加重\n（未导致住院）",
    "e_label": "组别 E",
    "e_rx": "LABA + LAMA",
    "e_note": "血 eos ≥ 300 个/µL 时考虑 LABA+LAMA+ICS",
    "a_label": "组别 A",
    "a_rx": "一种支气管舒张剂",
    "a_note": "按症状反应继续或调整",
    "b_label": "组别 B",
    "b_rx": "LABA + LAMA",
    "b_note": "单吸入装置可提高便利与依从",
    "footnote": "* 单吸入装置可能较多吸入器更便利有效。CAT = COPD Assessment Test；mMRC = 改良 Medical Research Council 呼吸困难量表。",
}

TX = {
    "id": "gold-tx",
    "section": "COPD · 随访升级",
    "title": "随访治疗调整：双路径升级树",
    "figure": "图 4.1",
    "takeaway": "按主导表现分路径：呼吸困难走舒张升级；加重走 eos 分层的抗炎升级",
    "source": SRC,
    "page": "03",
    "left_label": "呼吸困难路径",
    "right_label": "急性加重路径",
    "left_nodes": [
        {"heading": "LABA 或 LAMA", "body": "单药长效支气管舒张", "kind": "drug"},
        {"heading": "LABA + LAMA", "body": "仍有呼吸困难 → 双支扩", "kind": "drug"},
        {
            "heading": "装置 / 非药物 / 鉴别",
            "body": "更换吸入装置；肺康复与氧疗评估；排查心衰、贫血等其他气促原因",
            "kind": "note",
        },
    ],
    "right_nodes": [
        {"heading": "LABA 或 LAMA", "body": "当前为基础治疗", "kind": "drug"},
        {
            "heading": "LABA + LAMA + ICS",
            "body": "血 eos ≥ 300；或 eos ≥ 100 且 ≥2 次中度加重/1 次住院",
            "kind": "split_left",
            "branch": "eos ≥ 300\n（或 ≥100 + 高危加重）",
        },
        {
            "heading": "LABA + LAMA",
            "body": "血 eos < 300 且未达高危加重指征",
            "kind": "split_right",
            "branch": "eos < 300",
        },
        {
            "heading": "仍有加重 → 加用",
            "body": "Roflumilast（FEV1 < 50% 且慢性支气管炎）· Azithromycin（优选既往吸烟者）",
            "kind": "end",
        },
        {
            "heading": "ICS 降阶梯指征",
            "body": "肺炎风险升高、不当指征或明显不良反应时考虑减停 ICS",
            "kind": "note",
        },
    ],
    "footnote": "* 单吸入装置可能更便利。** ICS 降阶梯需个体化权衡加重风险与肺炎等不良反应。eos = 血嗜酸粒细胞（个/µL）。",
}

PAGES = [
    ("01-algorithm", "algorithm_tree", ALGO),
    ("02-abe-matrix", "assessment_matrix", ABE),
    ("03-tx-tree", "dual_path_tree", TX),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    html_paths = []
    for stem, family, fill in PAGES:
        report = tl.validate_fill(family, fill)
        if not report["ok"]:
            raise SystemExit(f"{family} invalid: {report['errors']}")
        # Single-page deck shell so shared CSS + theme tokens apply
        html = tl.render_deck_html([{"family": family, "fill": fill}], theme=THEME)
        path = OUT / f"{stem}.html"
        path.write_text(html, encoding="utf-8")
        html_paths.append((stem, path))
        print("html", path, "chars", len(html))

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=2)
        for stem, path in html_paths:
            page.goto(path.as_uri())
            page.locator(".slide").first.screenshot(path=str(OUT / f"{stem}.png"))
            print("png", OUT / f"{stem}.png")
        browser.close()
    print("done", OUT)


if __name__ == "__main__":
    main()
