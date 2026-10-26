import unittest

from factdeck.fixtures import burden_slide, matrix_slide, pathway_slide, preview_slides, review_slide
from factdeck.html_templates import render_html
from factdeck.layout_selector import RETIRED_LAYOUTS, clean_source, select_layout


class SelectorTests(unittest.TestCase):
    def test_five_parallel_points_use_hero_metric_not_cards(self):
        selection = select_layout(burden_slide())
        self.assertEqual(selection.layout_id, "metric_row")
        self.assertEqual(selection.variant, "hero_plus_notes")
        self.assertLessEqual(selection.columns, 2)
        self.assertNotEqual(selection.columns, 5)
        self.assertEqual(selection.anchor["value"], "3-10%")
        self.assertNotIn(selection.layout_id, RETIRED_LAYOUTS)

    def test_six_actions_use_two_column_checklist(self):
        selection = select_layout(review_slide())
        self.assertEqual(selection.layout_id, "checklist")
        self.assertEqual(selection.columns, 2)
        self.assertNotEqual(selection.columns, 6)
        self.assertEqual(selection.anchor["value"], "")
        self.assertIn("连续3个月及以上", selection.anchor["statement"])
        self.assertNotEqual(selection.anchor["value"], "3个月")

    def test_plain_five_bullets_are_a_checklist(self):
        slide = {
            "relation": "并列要点（兜底）",
            "proposed": "key_points",
            "title": "要点",
            "items": [{"title": f"要点{i}", "body": "并列说明文字，没有数值。"} for i in range(1, 6)],
        }
        selection = select_layout(slide)
        self.assertEqual(selection.layout_id, "checklist")
        self.assertLessEqual(selection.columns, 2)
        self.assertNotIn(selection.layout_id, RETIRED_LAYOUTS)

    def test_four_items_without_axes_are_not_a_matrix(self):
        slide = {
            "proposed": "key_points",
            "title": "四项",
            "items": [{"title": f"项{i}", "body": "说明"} for i in range(4)],
        }
        selection = select_layout(slide)
        self.assertEqual(selection.layout_id, "checklist")
        self.assertNotEqual(selection.layout_id, "matrix_2x2")

    def test_four_items_with_axes_are_a_matrix(self):
        selection = select_layout(matrix_slide())
        self.assertEqual(selection.layout_id, "matrix_2x2")
        self.assertEqual(selection.columns, 2)

    def test_claim_evidence_relation(self):
        slide = {
            "relation": "claim_evidence",
            "title": "确诊",
            "items": [
                {"id": "c", "title": "拟诊后的确诊情况", "body": "诊断重度哮喘前应进行系统评估", "evidence": "真实世界研究显示约50%得到确诊"},
            ],
        }
        selection = select_layout(slide)
        self.assertEqual(selection.layout_id, "claim_evidence")
        self.assertEqual(selection.columns, 2)

    def test_threshold_is_not_degraded_to_key_points(self):
        slide = pathway_slide()
        slide = {**slide, "proposed": "key_points"}
        selection = select_layout(slide)
        self.assertEqual(selection.layout_id, "algorithm_tree")
        self.assertIn("key_points", selection.reason)

    def test_repeated_algorithm_is_kept(self):
        first = select_layout(pathway_slide())
        second = select_layout(pathway_slide(), previous=first.layout_id)
        self.assertEqual(second.layout_id, "algorithm_tree")
        self.assertIn("保留", second.reason)

    def test_close_alternative_breaks_a_repeat(self):
        slide = {
            "title": "负担",
            "items": [
                {"id": "a", "title": "占比", "body": "3-10%"},
                {"id": "b", "title": "确诊", "body": "需要系统评估", "evidence": "真实世界研究显示约50%得到确诊"},
                {"id": "c", "title": "负担", "body": "疾病负担重", "evidence": "相比轻中度哮喘负担更重"},
            ],
        }
        first = select_layout(slide)
        self.assertEqual(first.layout_id, "claim_evidence")
        second = select_layout(slide, previous="claim_evidence")
        self.assertEqual(second.layout_id, "metric_row")
        self.assertIn("改用", second.reason)

    def test_three_metrics_share_a_band(self):
        slide = {
            "relation": "metric",
            "title": "三项数值",
            "items": [
                {"title": "占比", "value": "3-10%"},
                {"title": "确诊", "value": "50%"},
                {"title": "随访", "value": "3个月"},
            ],
        }
        selection = select_layout(slide)
        self.assertEqual(selection.layout_id, "metric_row")
        self.assertEqual(selection.variant, "band")
        self.assertEqual(selection.columns, 3)

    def test_preview_deck_never_selects_retired_cards(self):
        previous = None
        seen = []
        for slide in preview_slides():
            selection = select_layout(slide, previous=previous)
            self.assertNotIn(selection.layout_id, RETIRED_LAYOUTS)
            item_count = len(slide.get("items") or [])
            if item_count >= 4:
                self.assertLess(selection.columns, item_count)
                self.assertLessEqual(selection.columns, 2)
            seen.append(selection.layout_id)
            previous = selection.layout_id
        self.assertEqual(
            seen,
            ["metric_row", "checklist", "claim_evidence", "matrix_2x2", "algorithm_tree", "data_table_highlight"],
        )

    def test_source_hash_is_stripped(self):
        dirty = "重度哮喘识别 f004 d2.bu.v ex_d.t.eos3_0_16 aabbccdd"
        self.assertNotIn("f004", clean_source(dirty))
        self.assertNotIn("d2.bu", clean_source(dirty))
        self.assertNotIn("aabbccdd", clean_source(dirty))
        self.assertIn("重度哮喘识别", clean_source(dirty))


class TemplateTests(unittest.TestCase):
    def test_metric_html_has_no_card_chrome(self):
        slide = burden_slide()
        html = render_html(slide, select_layout(slide))
        self.assertIn('data-layout="metric_row"', html)
        self.assertIn("hero-row", html)
        self.assertNotIn("box-shadow:", html.split("#fd-measure")[0].split("box-shadow: none")[1])
        self.assertNotIn("key_points", html)
        self.assertIn("3-10%", html)
        self.assertNotIn("f004", html)

    def test_algorithm_uses_four_node_types(self):
        slide = pathway_slide()
        html = render_html(slide, select_layout(slide))
        for kind in ("node-start", "node-decision", "node-action", "node-exclude"):
            self.assertIn(kind, html)
        self.assertIn("是", html)
        self.assertIn("否", html)
        self.assertIn("血EOS＞1500 个细胞/μL", html)

    def test_table_highlights_overlap_column_and_badges(self):
        slide = {
            "title": "对照",
            "kicker": "临床应用",
            "page": "36",
            "source": "来源：示例 aabbccddeeff",
            "table": {
                "columns": ["项目", "甲", "乙"],
                "highlight_columns": [2],
                "widths": ["20%", "40%", "40%"],
                "rows": [{"label": "是否持续", "cells": ["是", "否"]}],
                "caption": "逐字引自原文",
            },
        }
        html = render_html(slide, select_layout(slide))
        self.assertIn("data-layout=\"data_table_highlight\"", html)
        self.assertIn("badge-yes", html)
        self.assertIn("badge-no", html)
        self.assertIn("th class=\"hi\"", html)
        self.assertNotIn("aabbccddeeff", html)
        self.assertIn("width:20%", html)

    def test_checklist_html_is_two_columns(self):
        slide = review_slide()
        html = render_html(slide, select_layout(slide))
        self.assertIn('data-layout="checklist"', html)
        self.assertIn("checks cols-2", html)
        self.assertIn("anchor-panel", html)
        self.assertNotIn("card", html)


if __name__ == "__main__":
    unittest.main()
