"""SUMMARY slimming and chapter limits in front of build_deck.

Overflow bullets are omitted whole. The pass does not rewrite a dose,
drug name, or duration into another string, and it does not spill extra
cards onto another page.
"""

import unittest

import factdeck.summary as summary
from factdeck.deck import build_deck
from factdeck.fixtures import matrix_slide, preview_slides
from factdeck.html_templates import render_html
from factdeck.layout_selector import select_layout
from factdeck.summary import (
    DEFAULT_BULLETS_PER_SECTION,
    DEFAULT_MAX_PAGES,
    DEFAULT_MAX_SECTIONS,
    prepare_deck,
    summary_from_outline,
    summary_from_slides,
)

_DOSE = "美泊利珠单抗 100 mg"
_DOSE_SOURCE = "美泊利珠单抗 100 mg 皮下"
_CLIP_SOURCE = "指连续3个月及以上规范使用中-高剂量ICS-LABA"
_OTHER = "奥马珠单抗 150 mg"
_A1 = "甲章第一页第一条完整说明。"
_A2 = "甲章第一页第二条完整说明。"
_A3 = "甲章第二页第一条完整说明。"
_A4 = "甲章第二页第二条完整说明。"
_B1 = "乙章仅有的一条完整说明。"
_REAL = "实章里的完整说明。"
_LATER = "丙章完整说明。"


def _items(section_id, bodies):
    return [
        {"id": f"{section_id}-{index}", "title": f"条目{index}", "body": body}
        for index, body in enumerate(bodies, start=1)
    ]


def _slide(title, section_id, bodies):
    return {"title": title, "section_id": section_id, "items": _items(section_id, bodies)}


def _outline():
    return {
        "sections": [
            {
                "id": "dose",
                "title": "剂量",
                "bullets": [
                    {
                        "id": "ok",
                        "title": "维持剂量",
                        "text": _DOSE,
                        "source_text": _DOSE_SOURCE,
                        "source_field": "body",
                        "source_id": "span-dose",
                    },
                    {"id": "clip", "text": "3个月", "source_text": _CLIP_SOURCE, "source_id": "span-time"},
                    {"id": "fill", "text": "可考虑加量"},
                ],
            },
            {
                "id": "other",
                "title": "其他",
                "bullets": [
                    {"id": "oma", "text": _OTHER, "source_text": _OTHER, "source_id": "span-oma"},
                ],
            },
        ]
    }


class SummaryShapeTests(unittest.TestCase):
    def test_outline_copies_bullet_text_and_names_the_knobs(self):
        deck_summary = summary_from_outline(_outline())
        bullet = deck_summary.sections[0].bullets[0]
        self.assertEqual(bullet.text, _DOSE)
        self.assertEqual(bullet.source_text, _DOSE_SOURCE)
        self.assertEqual(bullet.source_id, "span-dose")
        self.assertEqual(bullet.source_field, "body")
        self.assertEqual(deck_summary.to_dict()["sections"][0]["bullets"][0]["text"], _DOSE)
        self.assertIsNone(DEFAULT_MAX_SECTIONS)
        self.assertIsNone(DEFAULT_MAX_PAGES)
        self.assertIsNone(DEFAULT_BULLETS_PER_SECTION)
        documented = summary.__doc__
        self.assertIn("max_sections", documented)
        self.assertIn("max_pages", documented)
        self.assertIn("bullets_per_section", documented)
        self.assertIn("OVERFLOW", documented)
        self.assertIn("not spilled", documented)

    def test_slide_summary_uses_each_item_as_its_own_span(self):
        slides = preview_slides()
        deck_summary = summary_from_slides(slides)
        self.assertGreaterEqual(len(deck_summary.sections), 1)
        prepared = prepare_deck(slides)
        self.assertEqual(len(prepared.slides), len(slides))
        for original, slimmed in zip(slides, prepared.slides):
            self.assertEqual(list(slimmed.get("items") or []), list(original.get("items") or []))
            self.assertEqual(slimmed.get("relation"), original.get("relation"))
            self.assertEqual(slimmed.get("nodes"), original.get("nodes"))
            self.assertEqual(slimmed.get("table"), original.get("table"))
        for section in prepared.sections:
            for decision in section.bullets:
                self.assertEqual(decision.reason, "ADMITTED")
                self.assertTrue(decision.kept)
                self.assertEqual(decision.bullet.text, decision.bullet.source_text)


class SlimDropTests(unittest.TestCase):
    def test_slim_drops_unbound_filler_and_keeps_the_admitted_fact(self):
        slide = {
            "title": "剂量",
            "items": [
                {"id": "dose", "title": "维持剂量", "body": _DOSE},
                {"id": "fill", "title": "备注", "body": "建议结合临床经验调整", "source_text": ""},
            ],
        }
        prepared = prepare_deck([slide])
        reasons = {bullet.bullet.item_id: bullet.reason for bullet in prepared.sections[0].bullets}
        self.assertEqual(reasons["dose"], "ADMITTED")
        self.assertEqual(reasons["fill"], "UNBOUND")
        self.assertEqual([item["id"] for item in prepared.slides[0]["items"]], ["dose"])
        pages = build_deck([slide])
        self.assertIn(_DOSE, pages[0].html)
        self.assertNotIn("建议结合临床经验调整", pages[0].html)
        raw = render_html(slide, select_layout(slide))
        self.assertIn("建议结合临床经验调整", raw)

    def test_ungated_clip_is_omitted_and_not_rewritten(self):
        slide = {
            "title": "剂量",
            "relation": "metric",
            "items": [
                {
                    "id": "dose",
                    "title": "维持剂量",
                    "value": "100 mg",
                    "body": "美泊利珠单抗 10 0 mg 皮下",
                },
                {
                    "id": "course",
                    "title": "疗程",
                    "value": "3个月",
                    "body": _CLIP_SOURCE,
                },
            ],
        }
        prepared = prepare_deck([slide])
        by_id = {bullet.bullet.item_id: bullet for bullet in prepared.sections[0].bullets}
        self.assertEqual(by_id["dose"].reason, "ADMITTED")
        self.assertIn("value", by_id["dose"].stripped_fields)
        self.assertEqual(by_id["course"].reason, "ADMITTED")
        self.assertIn("value", by_id["course"].stripped_fields)
        dose = prepared.slides[0]["items"][0]
        course = prepared.slides[0]["items"][1]
        self.assertNotIn("value", dose)
        self.assertEqual(dose["body"], "美泊利珠单抗 10 0 mg 皮下")
        self.assertNotIn("value", course)
        self.assertEqual(course["body"], _CLIP_SOURCE)
        html = build_deck([slide])[0].html
        self.assertIn("美泊利珠单抗 10 0 mg 皮下", html)
        self.assertIn(_CLIP_SOURCE, html)
        self.assertNotIn("100 mg", html)
        self.assertNotRegex(html, r">\s*3个月\s*<")

    def test_outline_drops_a_clip_instead_of_substituting_its_source(self):
        prepared = prepare_deck(summary=_outline())
        reasons = {
            bullet.bullet.item_id: bullet.reason
            for section in prepared.sections
            for bullet in section.bullets
        }
        self.assertEqual(reasons["ok"], "ADMITTED")
        self.assertEqual(reasons["clip"], "UNGATED")
        self.assertEqual(reasons["fill"], "UNBOUND")
        self.assertEqual(reasons["oma"], "ADMITTED")
        html = "".join(page.html for page in build_deck(summary=_outline()))
        self.assertIn(_DOSE, html)
        self.assertIn(_OTHER, html)
        self.assertNotIn("可考虑加量", html)
        self.assertNotIn(_CLIP_SOURCE, html)
        self.assertNotIn("3个月", html)
        self.assertEqual(prepared.summary.sections[0].bullets[1].text, "3个月")

    def test_slides_and_summary_together_are_rejected(self):
        with self.assertRaises(ValueError):
            prepare_deck([{"title": "剂量", "items": []}], summary=_outline())


class ChapterLimitTests(unittest.TestCase):
    def _chapters(self):
        return [
            _slide("甲一", "chapter-a", [_A1, _A2]),
            _slide("甲二", "chapter-a", [_A3, _A4]),
            _slide("乙", "chapter-b", [_B1]),
        ]

    def test_bullet_cap_omits_later_bullets_on_the_same_page(self):
        bodies = [f"说明整句保留编号{label}。" for label in ("甲", "乙", "丙", "丁", "戊")]
        slide = {"title": "说明", "items": _items("note", bodies)}
        prepared = prepare_deck([slide], bullets_per_section=2)
        reasons = [bullet.reason for bullet in prepared.sections[0].bullets]
        self.assertEqual(reasons, ["ADMITTED", "ADMITTED", "OVERFLOW", "OVERFLOW", "OVERFLOW"])
        pages = build_deck([slide], bullets_per_section=2)
        self.assertEqual(len(pages), 1)
        self.assertIn(bodies[0], pages[0].html)
        self.assertIn(bodies[1], pages[0].html)
        self.assertNotIn(bodies[2], pages[0].html)
        self.assertNotIn(bodies[4], pages[0].html)

    def test_max_sections_keeps_a_chapter_and_max_pages_keeps_a_slide(self):
        slides = self._chapters()
        by_section = prepare_deck(slides, max_sections=1)
        self.assertEqual(len(by_section.slides), 2)
        self.assertTrue(by_section.sections[0].emitted)
        self.assertFalse(by_section.sections[1].emitted)
        self.assertEqual(by_section.sections[1].bullets[0].reason, "SECTION_CUT")
        section_html = "".join(page.html for page in build_deck(slides, max_sections=1))
        self.assertIn(_A1, section_html)
        self.assertIn(_A4, section_html)
        self.assertNotIn(_B1, section_html)

        by_page = prepare_deck(slides, max_pages=1)
        self.assertEqual(len(by_page.slides), 1)
        self.assertEqual(by_page.slides[0]["title"], "甲一")
        self.assertEqual(by_page.sections[0].bullets[2].reason, "PAGE_CUT")
        self.assertEqual(by_page.sections[1].bullets[0].reason, "PAGE_CUT")
        page_html = build_deck(slides, max_pages=1)[0].html
        self.assertIn(_A1, page_html)
        self.assertNotIn(_A3, page_html)
        self.assertNotIn(_B1, page_html)

    def test_bullet_budget_is_shared_inside_one_section(self):
        prepared = prepare_deck(self._chapters(), bullets_per_section=3)
        reasons = [bullet.reason for bullet in prepared.sections[0].bullets]
        self.assertEqual(reasons, ["ADMITTED", "ADMITTED", "ADMITTED", "OVERFLOW"])
        self.assertEqual(prepared.sections[1].bullets[0].reason, "ADMITTED")
        html = "".join(page.html for page in build_deck(self._chapters(), bullets_per_section=3))
        self.assertIn(_A3, html)
        self.assertNotIn(_A4, html)
        self.assertIn(_B1, html)

    def test_empty_section_consumes_max_sections_but_not_max_pages(self):
        slides = [
            {
                "title": "空章",
                "section_id": "empty",
                "items": [{"id": "fill", "body": "没有来源的填充句", "source_text": ""}],
            },
            _slide("实章", "real", [_REAL]),
            _slide("丙", "later", [_LATER]),
        ]
        capped = prepare_deck(slides, max_sections=1)
        self.assertEqual(capped.slides, ())
        self.assertEqual(capped.sections[0].bullets[0].reason, "UNBOUND")
        self.assertEqual(capped.sections[1].bullets[0].reason, "SECTION_CUT")
        self.assertEqual(build_deck(slides, max_sections=1), [])

        paged = prepare_deck(slides, max_pages=1)
        self.assertEqual(len(paged.slides), 1)
        self.assertEqual(paged.slides[0]["items"][0]["body"], _REAL)
        self.assertEqual(paged.sections[2].bullets[0].reason, "PAGE_CUT")
        self.assertNotIn(_LATER, build_deck(slides, max_pages=1)[0].html)

    def test_zero_and_negative_caps(self):
        slides = [_slide("实章", "real", [_REAL])]
        self.assertEqual(build_deck(slides, max_pages=0), [])
        self.assertEqual(prepare_deck(slides, max_pages=0).sections[0].bullets[0].reason, "PAGE_CUT")
        self.assertEqual(prepare_deck(slides, bullets_per_section=0).sections[0].bullets[0].reason, "OVERFLOW")
        with self.assertRaises(ValueError):
            prepare_deck(slides, max_sections=-1)
        with self.assertRaises(TypeError):
            prepare_deck(slides, max_pages=True)

    def test_cover_section_is_not_given_a_body(self):
        slides = [
            {"role": "cover", "title": "封面", "section_id": "cover"},
            _slide("正文", "body", ["正文完整说明。"]),
        ]
        prepared = prepare_deck(slides, max_sections=1)
        self.assertEqual(prepared.slides, ())
        self.assertFalse(prepared.sections[1].emitted)
        pages = build_deck(slides, max_sections=2)
        self.assertEqual(len(pages), 1)
        self.assertIn("正文完整说明。", pages[0].html)
        self.assertNotIn("封面", pages[0].html)

    def test_matrix_overflow_drops_cards_without_raising(self):
        slide = matrix_slide()
        kept = slide["items"][0]["body"]
        dropped = slide["items"][3]["body"]
        pages = build_deck([slide], bullets_per_section=2)
        self.assertEqual(len(pages), 1)
        self.assertIn(kept, pages[0].html)
        self.assertNotIn(dropped, pages[0].html)
        self.assertNotIn("100 mg", pages[0].html)


if __name__ == "__main__":
    unittest.main()
