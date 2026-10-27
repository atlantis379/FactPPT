"""Lecture-slide density. Fact gate, pairing, slim, and half-sentences stay put."""

import unittest

from factdeck.deck import build_deck
from factdeck.fixtures import burden_slide, claim_slide, preview_slides, review_slide
from factdeck.theme import CSS


class DensityTokenTests(unittest.TestCase):
    def test_margin_title_bar_and_gap(self):
        self.assertIn("height: 88px; padding: 0 56px;", CSS)
        self.assertIn("width: 1920px; height: 88px;", CSS)
        self.assertIn("margin: 20px 56px 6px;", CSS)
        self.assertIn("margin: 0 56px 16px;", CSS)
        self.assertNotIn("104px", CSS)
        self.assertNotIn("height: 136px", CSS)
        self.assertIn(".checks.cols-2", CSS)
        self.assertIn("grid-template-columns: 1fr 1fr", CSS)
        self.assertIn("width: 96%", CSS)
        self.assertIn("min-height: 720px", CSS)

    def test_review_checklist_is_two_columns_across_the_content_width(self):
        page = build_deck([review_slide()])[0]
        self.assertIn("check-wrap stack", page.html)
        self.assertIn("checks cols-2", page.html)
        self.assertIn("anchor-panel", page.html)
        self.assertNotIn("checks cols-1", page.html)
        self.assertIn('class="footer-line"', page.html)
        self.assertIn('class="folio"', page.html)
        self.assertIn('class="source"', page.html)

    def test_short_checklist_keeps_one_column_and_a_side_lead(self):
        slide = {
            "title": "要点",
            "items": [
                {"id": "a", "title": "要点1", "body": "并列说明整句保留编号1，没有剂量。"},
                {"id": "b", "title": "要点2", "body": "并列说明整句保留编号2，没有剂量。"},
            ],
        }
        page = build_deck([slide])[0]
        self.assertEqual(page.columns, 1)
        self.assertIn("check-wrap split", page.html)
        self.assertIn("checks cols-1", page.html)
        self.assertNotIn("checks cols-2", page.html)
        self.assertIn("anchor-panel", page.html)
        self.assertIn("并列说明整句保留编号1，没有剂量。", page.html)

    def test_footer_takeaway_is_the_admitted_claim(self):
        burden = build_deck([burden_slide()])[0]
        self.assertIn("metric-split beside", burden.html)
        self.assertIn("hero-row", burden.html)
        self.assertIn("相比轻中度哮喘，重度哮喘患者疾病负担重", burden.html)
        self.assertNotIn('data-slot="footer-take"', burden.html)
        self.assertEqual(burden.trace_status, "CLEAN")
        claim = build_deck([claim_slide()])[0]
        self.assertIn("ce-split", claim.html)
        self.assertIn('data-slot="footer-take"', claim.html)
        self.assertIn("诊断重度哮喘前应进行系统评估", claim.html)
        self.assertIn('class="folio"', claim.html)
        self.assertIn('class="source"', claim.html)
        self.assertEqual(claim.trace_status, "CLEAN")

    def test_figure_pages_keep_folio_and_source_without_a_new_sentence(self):
        pages = {page.preview_id: page for page in build_deck(preview_slides())}
        for preview_id in ("matrix-2x2", "algorithm-tree", "data-table"):
            html = pages[preview_id].html
            self.assertIn('class="folio"', html)
            self.assertIn('class="source"', html)
            self.assertNotIn('data-slot="footer-take"', html)
            self.assertEqual(pages[preview_id].trace_status, "CLEAN")
