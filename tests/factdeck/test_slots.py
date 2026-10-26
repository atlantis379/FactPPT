"""Slot pairing and per-slot provenance for teaching layouts."""

import json
import re
import unittest
from dataclasses import replace

from factdeck.facts import gate_display
from factdeck.fixtures import (
    burden_slide,
    claim_slide,
    matrix_slide,
    overlap_slide,
    pathway_slide,
    preview_slides,
    review_slide,
)
from factdeck.html_templates import render_html
from factdeck.layout_selector import Selection, select_layout
from factdeck.slots import (
    TRACE_MARK,
    SlotBinding,
    bind_layout,
    emit_fact_value,
    gate_keeps_display,
    judge_binding,
    judge_flow_zip,
    judge_item_zip,
    measure_record,
    trace_slide,
)
from factdeck.theme import MEASURE_JS


def _binding(**kwargs) -> SlotBinding:
    defaults = {
        "slot_id": "s",
        "role": "body",
        "kind": "text",
        "layout_id": "checklist",
        "display_text": "",
        "source_text": "",
        "source_id": "item:s",
        "source_field": "body",
        "pair_id": "item:s",
        "fact_bearing": True,
    }
    defaults.update(kwargs)
    return SlotBinding(**defaults)


class AdmissionTests(unittest.TestCase):
    def test_accepted_slot_needs_an_admitted_slice(self):
        source = "美泊利珠单抗 100 mg"
        verdict = judge_binding(
            _binding(display_text=source, source_text=source, source_field="body")
        )
        self.assertEqual(verdict.status, "ACCEPTED")
        self.assertTrue(verdict.admitted_slices)
        self.assertEqual(verdict.provenance, TRACE_MARK)
        self.assertFalse(verdict.admits_to_approved_graph)
        dose = next(item for item in verdict.admitted_slices if item.kind == "dose")
        self.assertEqual(dose.token, "100")
        self.assertEqual(source[dose.start : dose.end], dose.text)

    def test_plain_text_binding_is_not_accepted(self):
        verdict = judge_binding(_binding(display_text="并列说明，没有数值。", source_text="并列说明，没有数值。"))
        self.assertNotEqual(verdict.status, "ACCEPTED")
        self.assertEqual(verdict.reason_code, "NO_ADMITTED_SLICE")
        self.assertEqual(verdict.admitted_slices, ())
        self.assertEqual(verdict.provenance, "")

    def test_unbound_fact_slot_is_rejected(self):
        verdict = judge_binding(_binding(display_text="100 mg", source_text=None, source_id=None))
        self.assertEqual(verdict.status, "REJECTED")
        self.assertEqual(verdict.reason_code, "UNBOUND_SLOT")
        self.assertEqual(verdict.provenance, "")

    def test_display_outside_its_source_is_rejected(self):
        verdict = judge_binding(
            _binding(display_text="戒烟、锻炼、健康饮食", source_text="确认患者拥有书面哮喘行动计划")
        )
        self.assertEqual(verdict.status, "REJECTED")
        self.assertEqual(verdict.reason_code, "DISPLAY_NOT_IN_SOURCE")
        self.assertEqual(verdict.provenance, "")

    def test_duration_clip_is_not_an_admitted_value(self):
        source = next(item["body"] for item in review_slide()["items"] if "3个月" in item["body"])
        self.assertFalse(gate_keeps_display(source, "3个月"))
        verdict = judge_binding(
            _binding(role="value", display_text="3个月", source_text=source, source_id="item:standard", source_field="body")
        )
        self.assertEqual(verdict.status, "NEEDS_REVIEW")
        self.assertIn("DROP_TIME_WINDOW", gate_display(source, "3个月").omissions)
        self.assertEqual(verdict.provenance, "")
        self.assertFalse(emit_fact_value(verdict))
        kept = judge_binding(_binding(role="body", display_text=source, source_text=source, source_id="item:standard"))
        self.assertEqual(kept.status, "ACCEPTED")
        self.assertTrue(kept.admitted_slices)
        self.assertEqual(kept.provenance, TRACE_MARK)


class PairingTests(unittest.TestCase):
    def test_flow_node_zip_is_rejected_and_loses_provenance(self):
        nodes = pathway_slide()["nodes"]
        zipped = judge_flow_zip(nodes)
        self.assertEqual(zipped.status, "REJECTED")
        mismatched = [item for item in zipped.slots if item.reason_code == "PAIR_MISMATCH"]
        truncated = [item for item in zipped.slots if item.reason_code == "PAIR_TRUNCATED"]
        self.assertTrue(mismatched)
        self.assertTrue(truncated)
        drug = next(item for item in zipped.slots if "抗IL-5" in item.display_text)
        self.assertEqual(drug.status, "REJECTED")
        self.assertEqual(drug.reason_code, "PAIR_MISMATCH")
        self.assertEqual(drug.provenance, "")
        self.assertEqual(drug.admitted_slices, ())
        self.assertTrue(all(item.provenance != TRACE_MARK for item in zipped.slots))
        self.assertIn(zipped.status, {"REJECTED", "NEEDS_REVIEW"})

    def test_item_title_body_zip_is_rejected(self):
        zipped = judge_item_zip(review_slide()["items"])
        self.assertEqual(zipped.status, "REJECTED")
        self.assertTrue(all(item.reason_code == "PAIR_MISMATCH" for item in zipped.slots))
        duration = next(item for item in zipped.slots if "连续3个月" in item.display_text)
        self.assertNotEqual(duration.status, "ACCEPTED")
        self.assertEqual(duration.provenance, "")
        paired = trace_slide(review_slide())
        admitted = next(item for item in paired.slots if item.slot_id == "c6-body")
        self.assertEqual(admitted.status, "ACCEPTED")
        self.assertEqual(admitted.source_id, "item:standard")
        self.assertEqual(admitted.provenance, TRACE_MARK)
        self.assertEqual(duration.source_id, "item:standard")
        self.assertNotEqual(duration.pair_id, admitted.pair_id)

    def test_same_node_title_and_line_stay_paired(self):
        trace = trace_slide(pathway_slide())
        title = trace.by_id()["decision-title"]
        line = trace.by_id()["decision-line1"]
        self.assertEqual(title.pair_id, line.pair_id)
        self.assertEqual(title.source_id, line.source_id)
        self.assertEqual(line.status, "ACCEPTED")
        self.assertEqual(line.provenance, TRACE_MARK)
        self.assertTrue(any(item.kind == "dose" for item in line.admitted_slices))
        self.assertEqual(trace.status, "CLEAN")


class LayoutTraceTests(unittest.TestCase):
    def test_teaching_layouts_bind_every_html_slot(self):
        for slide in preview_slides():
            selection = select_layout(slide)
            html = render_html(slide, selection)
            trace = trace_slide(slide, selection)
            found = set(re.findall(r'data-slot="([^"]+)"', html))
            bound = {item.slot_id for item in trace.bindings}
            self.assertEqual(found, bound, selection.layout_id)
            self.assertEqual(trace.status, "CLEAN")
            for verdict in trace.slots:
                self.assertTrue(verdict.role)
                self.assertIn(verdict.kind, {"text", "shape", "line"})
                record = measure_record(verdict)
                self.assertEqual(record["role"], verdict.role)
                self.assertEqual(record["status"], verdict.status)
                if verdict.status == "ACCEPTED":
                    self.assertTrue(verdict.admitted_slices)
                    self.assertEqual(verdict.provenance, TRACE_MARK)
                    self.assertIn(f'data-provenance="{TRACE_MARK}"', html)
                    self.assertTrue(record["sourceId"])
                    self.assertTrue(record["slices"])
                else:
                    self.assertEqual(verdict.provenance, "")
                    self.assertEqual(verdict.admitted_slices, ())
            footer = re.search(r'<div class="source"[^>]*>', html)
            self.assertIsNotNone(footer)
            self.assertNotIn("data-provenance", footer.group(0))
            self.assertEqual(trace.by_id()["source"].status, "CHROME")
            self.assertEqual(trace.by_id()["source"].provenance, "")
            self.assertFalse(trace.to_dict()["admits_to_approved_graph"])
            self.assertTrue(all(not item.admits_to_approved_graph for item in trace.slots))

    def test_checklist_does_not_emit_the_shortened_duration(self):
        slide = review_slide()
        selection = select_layout(slide)
        html = render_html(slide, selection)
        self.assertEqual(selection.anchor["value"], "")
        self.assertNotIn('data-slot="anchor-value"', html)
        self.assertIn("连续3个月及以上", html)
        self.assertNotRegex(html, r'data-slot="anchor-value"[^>]*>\s*3个月\s*<')
        forced = replace(selection, anchor={**selection.anchor, "value": "3个月"})
        forced_html = render_html(slide, forced)
        forced_trace = trace_slide(slide, forced)
        blocked = forced_trace.by_id()["anchor-value"]
        self.assertEqual(forced_trace.status, "NEEDS_REVIEW")
        self.assertEqual(blocked.status, "NEEDS_REVIEW")
        self.assertEqual(blocked.provenance, "")
        self.assertNotIn('data-slot="anchor-value"', forced_html)
        self.assertIn("连续3个月及以上", forced_html)
        admitted = forced_trace.by_id()["anchor-text"]
        self.assertEqual(admitted.status, "ACCEPTED")
        self.assertEqual(admitted.provenance, TRACE_MARK)
        self.assertIn('data-slot="anchor-text"', forced_html)
        self.assertIn(f'data-source-id="{admitted.source_id}"', forced_html)

    def test_each_teaching_layout_has_a_typed_fact_slot(self):
        slides = {
            "metric_row": burden_slide(),
            "checklist": review_slide(),
            "claim_evidence": claim_slide(),
            "matrix_2x2": matrix_slide(),
            "algorithm_tree": pathway_slide(),
            "data_table_highlight": overlap_slide(),
        }
        for layout_id, slide in slides.items():
            trace = trace_slide(slide)
            self.assertEqual(trace.layout_id, layout_id)
            facts = [item for item in trace.slots if item.fact_bearing]
            self.assertTrue(facts)
            admitted = [item for item in facts if item.status == "ACCEPTED"]
            self.assertTrue(admitted, layout_id)
            for item in admitted:
                self.assertTrue(item.source_id)
                self.assertTrue(item.source_field)
                self.assertTrue(item.admitted_slices)
                self.assertEqual(item.provenance, TRACE_MARK)
            self.assertTrue(any(item.role in {"body", "value", "line", "cell", "title"} for item in admitted))

    def test_caption_mention_of_trace_is_not_a_slot_provenance(self):
        html = render_html(overlap_slide(), select_layout(overlap_slide()))
        caption = re.search(r"<caption[^>]*>", html)
        self.assertIsNotNone(caption)
        self.assertNotIn("data-provenance", caption.group(0))
        self.assertIn("溯源见备注", html)

    def test_measure_script_copies_slot_type_and_source(self):
        for field in ("dataset.role", "dataset.sourceId", "dataset.sourceField", "dataset.pair", "dataset.status", "dataset.provenance", "dataset.slices"):
            self.assertIn(field, MEASURE_JS)
        selection = select_layout(review_slide())
        verdict = trace_slide(review_slide(), selection).by_id()["c6-body"]
        record = measure_record(verdict)
        self.assertEqual(record["role"], "body")
        self.assertEqual(record["sourceId"], "item:standard")
        self.assertEqual(record["sourceField"], "body")
        self.assertEqual(record["provenance"], TRACE_MARK)
        self.assertEqual(record["status"], "ACCEPTED")
        slices = json.loads(record["slices"])
        self.assertTrue(slices)
        self.assertTrue(any(item["kind"] == "time_window" for item in slices))


class RenderGuardTests(unittest.TestCase):
    def test_band_and_stacked_tree_slots_match_html(self):
        band = {
            "relation": "metric",
            "title": "三项数值",
            "items": [
                {"title": "占比", "value": "3-10%"},
                {"title": "确诊", "value": "约50%"},
                {"title": "剂量", "value": "美泊利珠单抗 100 mg"},
            ],
        }
        stacked = {
            "title": "流程",
            "nodes": [
                {"id": "a", "type": "start", "title": "起始使用抗IL-5R"},
                {"id": "b", "type": "action", "title": "处置", "body": "美泊利珠单抗 100 mg"},
            ],
        }
        for slide in (band, stacked):
            selection = select_layout(slide)
            html = render_html(slide, selection)
            trace = trace_slide(slide, selection)
            found = set(re.findall(r'data-slot="([^"]+)"', html))
            self.assertEqual(found, {item.slot_id for item in trace.bindings})
            self.assertEqual(trace.status, "CLEAN")
            self.assertTrue(any(item.status == "ACCEPTED" and item.provenance == TRACE_MARK for item in trace.slots))

    def test_checklist_body_text_is_not_the_bare_duration(self):
        slide = review_slide()
        selection = select_layout(slide)
        self.assertIsInstance(selection, Selection)
        html = render_html(slide, selection)
        self.assertIn('data-role="body"', html)
        self.assertIn('data-source-field="body"', html)
        self.assertNotIn(">3个月<", html)


if __name__ == "__main__":
    unittest.main()
