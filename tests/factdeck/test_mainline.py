"""Template mainline: render and the deck entry admit only gated fills.

The package has no HTTP ``/api/deck``. ``build_deck`` is the generation
entry, and it renders through the teaching-layout templates.
"""

import unittest
from dataclasses import replace
from pathlib import Path

from factdeck.deck import API_DECK, RENDERER, build_deck
from factdeck.fixtures import preview_slides, review_slide
from factdeck.html_templates import render_html
from factdeck.layout_selector import select_layout
from factdeck.slots import emit_on_screen, measured_text, screen_fill, trace_slide

_RENDER_PY = Path(__file__).resolve().parents[2] / "factdeck" / "render.py"


def _dose_slide() -> dict:
    return {
        "relation": "checklist",
        "title": "剂量",
        "items": [
            {
                "id": "dose",
                "title": "维持剂量",
                "body": "美泊利珠单抗 10 0 mg 皮下",
            }
        ],
    }


class RenderGateTests(unittest.TestCase):
    def test_render_omits_a_rejected_fill(self):
        slide = _dose_slide()
        selection = select_layout(slide)
        forced = replace(selection, anchor={**selection.anchor, "value": "100 mg"})
        html = render_html(slide, forced)
        trace = trace_slide(slide, forced)
        blocked = trace.by_id()["anchor-value"]
        self.assertEqual(blocked.status, "REJECTED")
        self.assertEqual(blocked.reason_code, "DISPLAY_NOT_IN_SOURCE")
        self.assertFalse(emit_on_screen(blocked))
        self.assertNotIn("100 mg", html)
        self.assertNotIn('data-slot="anchor-value"', html)
        self.assertNotIn('data-status="REJECTED"', html)
        self.assertIn("美泊利珠单抗 10 0 mg 皮下", html)

    def test_render_omits_a_rejected_non_value_fill(self):
        slide = _dose_slide()
        selection = select_layout(slide)
        forced = replace(selection, anchor={**selection.anchor, "label": "100 mg"})
        html = render_html(slide, forced)
        blocked = trace_slide(slide, forced).by_id()["anchor-label"]
        self.assertEqual(blocked.role, "title")
        self.assertEqual(blocked.status, "REJECTED")
        self.assertFalse(emit_on_screen(blocked))
        self.assertNotIn("100 mg", html)
        self.assertNotIn('data-slot="anchor-label"', html)
        self.assertIn("维持剂量", html)

    def test_render_omits_a_shortened_duration(self):
        slide = {
            "relation": "metric",
            "title": "疗程",
            "items": [
                {
                    "title": "疗程",
                    "value": "3个月",
                    "body": "指连续3个月及以上规范使用中-高剂量ICS-LABA",
                },
                {"title": "占比", "value": "3-10%"},
            ],
        }
        selection = select_layout(slide)
        self.assertEqual(selection.layout_id, "metric_row")
        self.assertEqual(selection.variant, "band")
        self.assertEqual(selection.anchor["value"], "3-10%")
        self.assertNotEqual(selection.anchor["value"], "3个月")
        html = render_html(slide, selection)
        trace = trace_slide(slide, selection)
        blocked = trace.by_id()["m1-value"]
        self.assertEqual(blocked.status, "NEEDS_REVIEW")
        self.assertIn("DROP_TIME_WINDOW", blocked.reason)
        self.assertFalse(emit_on_screen(blocked))
        self.assertNotIn("3个月", html)
        self.assertNotIn('data-status="NEEDS_REVIEW"', html)
        self.assertIn("3-10%", html)
        admitted = trace.by_id()["m2-value"]
        self.assertEqual(admitted.status, "ACCEPTED")
        self.assertIn("3-10%", admitted.display_text)
        self.assertIn('data-status="ACCEPTED"', html)

    def test_admitted_fill_survives_on_the_template(self):
        slide = {
            "relation": "metric",
            "title": "剂量",
            "items": [{"title": "维持剂量", "value": "美泊利珠单抗 100 mg"}],
        }
        selection = select_layout(slide)
        html = render_html(slide, selection)
        verdict = trace_slide(slide, selection).by_id()["hero-value"]
        self.assertEqual(verdict.status, "ACCEPTED")
        self.assertTrue(verdict.admitted_slices)
        self.assertIn("美泊利珠单抗 100 mg", html)
        self.assertIn('data-status="ACCEPTED"', html)
        self.assertIn(verdict.provenance, html)
        self.assertIn(f'data-layout="{selection.layout_id}"', html)

    def test_verbatim_prose_without_a_fact_slice_still_renders(self):
        html = render_html(review_slide(), select_layout(review_slide()))
        self.assertIn("行动计划", html)
        self.assertIn("确认患者拥有", html)
        self.assertIn("连续3个月及以上", html)
        self.assertNotRegex(html, r">\s*3个月\s*<")

    def test_selector_drops_a_value_the_gate_does_not_admit(self):
        slide = {
            "relation": "metric",
            "title": "剂量",
            "items": [
                {
                    "title": "剂量",
                    "value": "100 mg",
                    "body": "美泊利珠单抗 10 0 mg",
                }
            ],
        }
        selection = select_layout(slide)
        self.assertEqual(selection.layout_id, "metric_row")
        self.assertEqual(selection.anchor["value"], "")
        duration = select_layout(
            {
                "relation": "metric",
                "title": "疗程",
                "items": [
                    {
                        "title": "疗程",
                        "value": "3个月",
                        "body": "指连续3个月及以上规范使用中-高剂量ICS-LABA",
                    }
                ],
            }
        )
        self.assertEqual(duration.anchor["value"], "")
        self.assertEqual(screen_fill("美泊利珠单抗 10 0 mg", "100 mg"), "")
        self.assertEqual(screen_fill("美泊利珠单抗 100 mg", "美泊利珠单抗 100 mg"), "美泊利珠单抗 100 mg")
        html = render_html(slide, selection)
        blocked = trace_slide(slide, selection).by_id()["hero-value"]
        self.assertEqual(blocked.status, "REJECTED")
        self.assertNotIn("100 mg", html)
        self.assertNotIn('data-slot="hero-value"', html)


class DeckMainlineTests(unittest.TestCase):
    def test_build_deck_is_the_template_path(self):
        slides = preview_slides()
        pages = build_deck(slides)
        self.assertIsNone(API_DECK)
        self.assertEqual(len(pages), len(slides))
        previous = None
        for slide, page in zip(slides, pages):
            selection = select_layout(slide, previous=previous)
            self.assertEqual(page.layout_id, selection.layout_id)
            self.assertEqual(page.variant, selection.variant)
            self.assertEqual(page.renderer, RENDERER)
            self.assertEqual(page.selection["layout_id"], selection.layout_id)
            self.assertIn(f'data-layout="{selection.layout_id}"', page.html)
            self.assertNotIn("key_points", page.html)
            self.assertIsNone(page.to_dict()["api_deck"])
            previous = selection.layout_id
        self.assertEqual(
            [page.layout_id for page in pages],
            ["metric_row", "checklist", "claim_evidence", "matrix_2x2", "algorithm_tree", "data_table_highlight"],
        )

    def test_preview_entry_measures_build_deck_pages(self):
        source = _RENDER_PY.read_text(encoding="utf-8")
        self.assertIn("pages = build_deck(slides)", source)
        self.assertNotIn("render_html", source)
        self.assertNotIn("select_layout", source)

    def test_checklist_page_keeps_the_admitted_sentence(self):
        page = build_deck([review_slide()])[0]
        self.assertEqual(page.layout_id, "checklist")
        self.assertEqual(page.renderer, RENDERER)
        self.assertEqual(page.trace_status, "CLEAN")
        self.assertIn("连续3个月及以上", page.html)
        self.assertNotIn("3个月</", page.html)
        self.assertNotRegex(page.html, r">\s*3个月\s*<")
        self.assertIn('data-status="ACCEPTED"', page.html)
        self.assertIn("行动计划", page.html)


class MeasuredDrawTests(unittest.TestCase):
    def test_measured_text_drops_gated_bad_slots(self):
        self.assertEqual(measured_text({"text": "100 mg", "status": "REJECTED", "fact": "1", "role": "body"}), "")
        self.assertEqual(measured_text({"text": "3个月", "status": "NEEDS_REVIEW", "fact": "1", "role": "value"}), "")
        self.assertEqual(measured_text({"text": "3个月", "status": "BOUND", "fact": "1", "role": "value"}), "")
        kept = measured_text({"text": "美泊利珠单抗 100 mg", "status": "ACCEPTED", "fact": "1", "role": "value"})
        self.assertEqual(kept, "美泊利珠单抗 100 mg")
        self.assertEqual(measured_text({"text": "行动计划", "status": "BOUND", "fact": "1", "role": "title"}), "行动计划")
        self.assertEqual(measured_text({"text": "来源：示例", "status": "CHROME", "fact": "0", "role": "chrome"}), "来源：示例")


if __name__ == "__main__":
    unittest.main()
