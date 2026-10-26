"""Card-wall refusal and the half-sentence ban on the deck mainline.

An equal multi-column grid needs an admitted fact that differentiates the
peers. A clipped clause is omitted with its bullet or slot. A full source
span and a gate-accepted slice stay.
"""

import unittest
from dataclasses import replace

from factdeck.deck import build_deck
from factdeck.facts import dangling_half_sentence
from factdeck.fixtures import preview_slides, review_slide
from factdeck.html_templates import render_html
from factdeck.layout_selector import is_equal_card_wall, select_layout
from factdeck.slots import emit_on_screen, measured_text, screen_fill, trace_slide
from factdeck.summary import prepare_deck

_PLAN = "确认患者拥有（并知道如何使用）个性化的书面或电子哮喘行动计划"
_DOSE = "美泊利珠单抗 100 mg"
_DOSE_SOURCE = "美泊利珠单抗 100 mg 皮下"
_CLIP_SOURCE = "指连续3个月及以上规范使用中-高剂量ICS-LABA"


def _prose(count, prefix="并列说明整句保留"):
    return [
        {"id": f"p{index}", "title": f"要点{index}", "body": f"{prefix}编号{index}，没有剂量。"}
        for index in range(1, count + 1)
    ]


class CardWallTests(unittest.TestCase):
    def test_undifferentiated_peers_stay_one_column(self):
        slide = {"title": "要点", "relation": "并列要点（兜底）", "items": _prose(5)}
        selection = select_layout(slide)
        self.assertEqual(selection.layout_id, "checklist")
        self.assertEqual(selection.columns, 1)
        self.assertFalse(is_equal_card_wall(slide, selection))
        page = build_deck([slide])[0]
        self.assertEqual(page.layout_id, "checklist")
        self.assertEqual(page.columns, 1)
        self.assertIn("checks cols-1", page.html)
        self.assertNotIn("checks cols-2", page.html)
        self.assertIn("并列说明整句保留编号1，没有剂量。", page.html)
        self.assertIn("并列说明整句保留编号5，没有剂量。", page.html)

    def test_unadmitted_metric_does_not_open_a_peer_wall(self):
        slide = {
            "title": "要点",
            "relation": "并列要点（兜底）",
            "items": [*_prose(5), {"id": "fake", "title": "占比", "body": "3-10%", "source_text": ""}],
        }
        selection = select_layout(slide)
        self.assertEqual(selection.layout_id, "checklist")
        self.assertEqual(selection.columns, 1)
        self.assertFalse(is_equal_card_wall(slide, selection))
        page = build_deck([slide])[0]
        self.assertEqual(page.columns, 1)
        self.assertIn("checks cols-1", page.html)
        self.assertNotIn("3-10%", page.html)
        self.assertIn("并列说明整句保留编号1，没有剂量。", page.html)

    def test_admitted_metric_may_use_a_differentiated_row(self):
        slide = {
            "title": "负担",
            "relation": "并列要点（兜底）",
            "items": [{"id": "share", "title": "重度哮喘占比", "body": "3-10%"}, *_prose(5)],
        }
        selection = select_layout(slide)
        self.assertEqual(selection.layout_id, "metric_row")
        self.assertEqual(selection.variant, "hero_plus_notes")
        self.assertLess(selection.columns, len(slide["items"]))
        self.assertFalse(is_equal_card_wall(slide, selection))
        page = build_deck([slide])[0]
        self.assertEqual(page.layout_id, "metric_row")
        self.assertIn("3-10%", page.html)
        self.assertNotIn("equal_card_wall", page.html)

    def test_actions_keep_two_checklist_columns(self):
        selection = select_layout(review_slide())
        self.assertEqual(selection.layout_id, "checklist")
        self.assertEqual(selection.columns, 2)
        self.assertFalse(is_equal_card_wall(review_slide(), selection))

    def test_forced_equal_columns_cannot_reach_html(self):
        slide = {"title": "要点", "items": _prose(5)}
        selection = select_layout(slide)
        walled = replace(selection, columns=5)
        self.assertTrue(is_equal_card_wall(slide, walled))
        with self.assertRaisesRegex(RuntimeError, "equal card wall"):
            render_html(slide, walled)
        retired = replace(selection, layout_id="equal_card_wall")
        self.assertTrue(is_equal_card_wall(slide, retired))
        with self.assertRaisesRegex(RuntimeError, "retired or unknown layout"):
            render_html(slide, retired)

    def test_a_deck_of_peer_pages_is_not_a_card_wall(self):
        slides = []
        for name in ("甲", "乙"):
            slides.append(
                {
                    "title": f"{name}章",
                    "section_id": name,
                    "items": [
                        {"id": f"{name}{index}", "title": f"要点{index}", "body": f"{name}章并列说明整句编号{index}。"}
                        for index in range(1, 5)
                    ],
                }
            )
        pages = build_deck(slides)
        self.assertEqual(len(pages), 2)
        for page in pages:
            self.assertEqual(page.layout_id, "checklist")
            self.assertEqual(page.columns, 1)
            self.assertIn("checks cols-1", page.html)
            self.assertNotIn("checks cols-2", page.html)
        self.assertEqual(
            [page.layout_id for page in build_deck(preview_slides())],
            ["metric_row", "checklist", "claim_evidence", "matrix_2x2", "algorithm_tree", "data_table_highlight"],
        )


class HalfSentenceTests(unittest.TestCase):
    def test_dangling_clause_is_not_a_full_slice(self):
        self.assertTrue(dangling_half_sentence(_PLAN, "确认患者拥有"))
        self.assertFalse(dangling_half_sentence(_PLAN, _PLAN))
        self.assertFalse(dangling_half_sentence(_DOSE_SOURCE, _DOSE))
        self.assertTrue(dangling_half_sentence(_CLIP_SOURCE, "3个月"))
        self.assertEqual(screen_fill(_PLAN, "确认患者拥有"), "")
        self.assertEqual(screen_fill(_DOSE_SOURCE, _DOSE), _DOSE)
        self.assertEqual(screen_fill(_CLIP_SOURCE, "3个月"), "")

    def test_anchor_clip_is_omitted_and_the_sentence_stays(self):
        slide = {
            "relation": "checklist",
            "title": "计划",
            "items": [{"id": "plan", "title": "行动计划", "body": _PLAN}],
        }
        selection = select_layout(slide)
        forced = replace(selection, anchor={**selection.anchor, "statement": "确认患者拥有"})
        html = render_html(slide, forced)
        blocked = trace_slide(slide, forced).by_id()["anchor-text"]
        self.assertEqual(blocked.reason_code, "HALF_SENTENCE")
        self.assertEqual(blocked.status, "REJECTED")
        self.assertFalse(emit_on_screen(blocked))
        self.assertNotIn('data-slot="anchor-text"', html)
        self.assertNotIn('data-status="REJECTED"', html)
        self.assertIn(_PLAN, html)
        self.assertEqual(measured_text({"text": "确认患者拥有", "status": blocked.status, "fact": "1", "role": "body"}), "")

    def test_source_text_clip_does_not_render_as_its_own_sentence(self):
        slide = {
            "title": "计划",
            "items": [{"id": "plan", "title": "行动计划", "body": "确认患者拥有", "source_text": _PLAN}],
        }
        html = render_html(slide, select_layout(slide))
        self.assertNotIn("确认患者拥有", html)
        self.assertNotIn(_PLAN, html)
        self.assertIn("行动计划", html)
        verdict = trace_slide(slide).by_id()["c1-body"]
        self.assertEqual(verdict.reason_code, "HALF_SENTENCE")
        self.assertFalse(emit_on_screen(verdict))

    def test_half_sentence_bullet_is_omitted_whole(self):
        outline = {
            "sections": [
                {
                    "id": "plan",
                    "title": "计划",
                    "bullets": [
                        {"id": "clip", "text": "确认患者拥有", "source_text": _PLAN, "source_id": "span-plan"},
                        {"id": "full", "text": _PLAN, "source_text": _PLAN, "source_id": "span-full"},
                        {
                            "id": "dose",
                            "text": _DOSE,
                            "source_text": _DOSE_SOURCE,
                            "source_field": "body",
                            "source_id": "span-dose",
                        },
                    ],
                }
            ]
        }
        prepared = prepare_deck(summary=outline)
        reasons = {bullet.bullet.item_id: bullet.reason for bullet in prepared.sections[0].bullets}
        self.assertEqual(reasons["clip"], "HALF_SENTENCE")
        self.assertEqual(reasons["full"], "ADMITTED")
        self.assertEqual(reasons["dose"], "ADMITTED")
        self.assertEqual(prepared.summary.sections[0].bullets[0].text, "确认患者拥有")
        self.assertEqual([item["id"] for item in prepared.slides[0]["items"]], ["full", "dose"])
        html = build_deck(summary=outline)[0].html
        self.assertIn(_PLAN, html)
        self.assertIn(_DOSE, html)
        self.assertNotIn(_DOSE_SOURCE, html)

    def test_only_a_half_sentence_emits_no_page(self):
        outline = {
            "sections": [
                {
                    "id": "plan",
                    "title": "计划",
                    "bullets": [{"id": "clip", "text": "确认患者拥有", "source_text": _PLAN}],
                }
            ]
        }
        prepared = prepare_deck(summary=outline)
        self.assertEqual(prepared.sections[0].bullets[0].reason, "HALF_SENTENCE")
        self.assertEqual(prepared.slides, ())
        self.assertEqual(build_deck(summary=outline), [])
        self.assertEqual(prepared.summary.sections[0].bullets[0].text, "确认患者拥有")

    def test_duration_fragment_stays_ungated(self):
        prepared = prepare_deck(
            summary={
                "sections": [
                    {
                        "id": "course",
                        "title": "疗程",
                        "bullets": [{"id": "clip", "text": "3个月", "source_text": _CLIP_SOURCE}],
                    }
                ]
            }
        )
        self.assertEqual(prepared.sections[0].bullets[0].reason, "UNGATED")
        self.assertEqual(build_deck(summary={"sections": prepared.summary.to_dict()["sections"]}), [])
