"""Fact-gate regressions for digit stitching and silent display omissions.

The historical whitespace fold is local to this file. Admission goes through
``gate_display`` and must not treat that fold as a match.
"""

import json
import re
import unittest
from decimal import Decimal

from factdeck.facts import canon, extract_unit_slices, gate_display
from factdeck.fixtures import burden_slide, pathway_slide, review_slide
from factdeck.layout_selector import select_layout


def _historical_whitespace_fold(text: str) -> str:
    """Delete every whitespace character, including gaps between digits."""

    return re.sub(r"\s+", "", text or "").casefold()


def _allow(omissions):
    names = tuple(omissions)
    return {
        "derivation": names,
        "human_gate": {
            "decision": "ALLOW_OMISSION",
            "reviewer_id": "rev-1",
            "covers": names,
        },
    }


class CanonTests(unittest.TestCase):
    def test_canon_keeps_digit_gaps(self):
        folded = canon("10 0 mg")
        self.assertEqual(folded, "10 0mg")
        self.assertNotIn("100", folded)
        self.assertNotEqual(folded, canon("100 mg"))

    def test_canon_folds_space_between_number_and_unit(self):
        self.assertEqual(canon("100 mg"), "100mg")
        self.assertEqual(canon("100mg"), canon("100 mg"))

    def test_historical_fold_would_accept_stitched_dose(self):
        source = "美泊利珠单抗 10 0 mg"
        display = "100 mg"
        self.assertIn(_historical_whitespace_fold(display), _historical_whitespace_fold(source))
        self.assertNotIn(canon(display), canon(source))


class SliceTests(unittest.TestCase):
    def test_spaced_dose_fragments_stay_separate_slices(self):
        source = "美泊利珠单抗 10 0 mg"
        doses = [item for item in extract_unit_slices(source) if item.kind == "dose"]
        self.assertEqual([item.token for item in doses], ["10", "0"])
        self.assertEqual([item.unit for item in doses], ["", "mg"])
        self.assertNotIn("100", [item.token for item in doses])

    def test_slice_offsets_point_at_original_text(self):
        source = "美泊利珠单抗 100 mg"
        slices = extract_unit_slices(source)
        self.assertTrue(slices)
        for item in slices:
            self.assertEqual(source[item.start : item.end], item.text)
        dose = next(item for item in slices if item.kind == "dose")
        self.assertEqual(dose.audit_value, Decimal("100"))
        self.assertIs(type(dose.audit_value), Decimal)

    def test_numeric_audit_value_is_decimal(self):
        source = "从1.8降至0.7，下降61%"
        doses = [item for item in extract_unit_slices(source) if item.kind == "dose"]
        values = [item.audit_value for item in doses]
        self.assertIn(Decimal("1.8"), values)
        self.assertIn(Decimal("0.7"), values)
        self.assertIn(Decimal("61"), values)
        self.assertTrue(all(type(item) is Decimal for item in values if item is not None))
        tenth = next(item for item in extract_unit_slices("比例 0.1%") if item.kind == "dose")
        self.assertEqual(tenth.audit_value, Decimal("0.1"))
        self.assertEqual(str(tenth.audit_value), "0.1")
        payload = gate_display(source, source).to_dict()
        json.dumps(payload)
        serialized = [item["audit_value"] for item in payload["evidence_slices"] if item["audit_value"] is not None]
        self.assertIn("1.8", serialized)
        self.assertTrue(all(isinstance(item, str) for item in serialized))
        self.assertTrue(all(not isinstance(item, float) for item in serialized))

    def test_range_endpoints_are_decimals(self):
        dose = next(item for item in extract_unit_slices("占比 3-10%") if item.kind == "dose")
        self.assertEqual(dose.token, "3-10")
        self.assertIsNone(dose.audit_value)
        self.assertEqual(dose.audit_low, Decimal("3"))
        self.assertEqual(dose.audit_high, Decimal("10"))
        self.assertIs(type(dose.audit_low), Decimal)
        self.assertIs(type(dose.audit_high), Decimal)

    def test_sign_is_part_of_the_slice(self):
        dose = next(item for item in extract_unit_slices("变化 -1.1") if item.kind == "dose")
        self.assertEqual(dose.token, "-1.1")
        self.assertEqual(dose.audit_value, Decimal("-1.1"))
        self.assertEqual(gate_display("变化 -1.1", "1.1").reason_code, "NUMERIC_BOUNDARY")
        self.assertEqual(gate_display("变化 -1.1", "-1.1").status, "ACCEPTED")

    def test_digit_inside_drug_name_is_not_a_dose(self):
        source = "起始使用抗IL-5R"
        self.assertFalse(any(item.kind == "dose" for item in extract_unit_slices(source)))
        self.assertEqual(gate_display(source, "5").reason_code, "ADDED_CONTENT")
        self.assertEqual(gate_display(source, "抗IL-5R").status, "ACCEPTED")

    def test_danshi_is_not_split_into_a_bare_dan(self):
        contrasts = [item.text for item in extract_unit_slices("但是应继续") if item.kind == "contrast"]
        self.assertEqual(contrasts, ["但是"])


class DrugAndDoseAdmissionTests(unittest.TestCase):
    def test_whitespace_fold_cannot_stitch_dose_fragments(self):
        source = "美泊利珠单抗 10 0 mg 皮下"
        display = "美泊利珠单抗 100 mg"
        self.assertIn(_historical_whitespace_fold(display), _historical_whitespace_fold(source))
        result = gate_display(source, display)
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reason_code, "NUMERIC_STITCH")
        self.assertIn("ADDED_CONTENT", result.issues)
        self.assertFalse(result.admits_to_approved_graph)

    def test_newline_between_digits_is_still_a_stitch(self):
        result = gate_display("10\n0 mg", "100 mg")
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reason_code, "NUMERIC_STITCH")

    def test_canon_substring_is_not_admission(self):
        source = "美泊利珠单抗 100 mg"
        display = "10 mg"
        self.assertIn(canon("10"), canon(source))
        result = gate_display(source, display)
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reason_code, "NUMERIC_BOUNDARY")

    def test_drug_prefix_is_not_a_slice(self):
        source = "抗IL-5R"
        display = "抗IL-5"
        self.assertIn(canon(display), canon(source))
        result = gate_display(source, display)
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reason_code, "ADDED_CONTENT")
        self.assertIn("抗IL-5", result.added_texts)

    def test_original_dose_with_unit_space_is_accepted(self):
        source = "美泊利珠单抗 100 mg"
        result = gate_display(source, "美泊利珠单抗100mg")
        self.assertEqual(result.status, "ACCEPTED")
        self.assertEqual(result.reason_code, "EXTRACTIVE_FAITHFUL")
        self.assertEqual(result.issues, ())
        dose = next(item for item in result.evidence_slices if item.kind == "dose")
        self.assertEqual(dose.audit_value, Decimal("100"))

    def test_range_is_not_collapsed_or_split(self):
        source = "占比 3-10%"
        self.assertEqual(gate_display(source, "3-10%").status, "ACCEPTED")
        self.assertEqual(gate_display(source, "3–10%").status, "ACCEPTED")
        collapsed = gate_display(source, "310%")
        self.assertEqual(collapsed.status, "REJECTED")
        self.assertEqual(collapsed.reason_code, "ADDED_CONTENT")
        endpoint = gate_display(source, "10%")
        self.assertEqual(endpoint.status, "REJECTED")
        self.assertEqual(endpoint.reason_code, "NUMERIC_BOUNDARY")

    def test_spaced_range_matches_hyphen_range(self):
        self.assertEqual(gate_display("占比 3 - 10%", "3-10%").status, "ACCEPTED")

    def test_rounding_is_not_silent(self):
        source = "FEV₁/FVC < 0.70"
        faithful = gate_display(source, source)
        self.assertEqual(faithful.status, "ACCEPTED")
        shortened = gate_display(source, "FEV₁/FVC < 0.7")
        self.assertEqual(shortened.status, "REJECTED")
        self.assertEqual(shortened.reason_code, "NUMERIC_BOUNDARY")

    def test_flipped_comparator_is_rejected(self):
        result = gate_display("血EOS＞1500 个细胞/μL", "血EOS＜1500 个细胞/μL")
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reason_code, "ADDED_CONTENT")
        self.assertIn("＜", result.added_texts)

    def test_added_drug_is_rejected(self):
        source = "100 mg，每 4 周 1 次"
        display = "美泊利珠单抗 100 mg，每 4 周 1 次"
        result = gate_display(source, display)
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reason_code, "ADDED_CONTENT")

    def test_drug_casefold_matches_original_slice(self):
        result = gate_display("Mepolizumab 100 mg", "mepolizumab 100 mg")
        self.assertEqual(result.status, "ACCEPTED")

    def test_empty_display_is_rejected(self):
        self.assertEqual(gate_display("100 mg", "").reason_code, "EMPTY_DISPLAY")
        self.assertEqual(gate_display("100 mg", "   ").reason_code, "EMPTY_DISPLAY")
        self.assertEqual(gate_display("100 mg", "...").reason_code, "VACUOUS_DISPLAY")

    def test_clinical_spaced_count_does_not_stitch(self):
        line = pathway_slide()["nodes"][1]["lines"][0]
        stitched = line.replace("1500", "150 0")
        self.assertIn(_historical_whitespace_fold(line), _historical_whitespace_fold(stitched))
        result = gate_display(stitched, line)
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reason_code, "NUMERIC_STITCH")
        self.assertEqual(gate_display(line, line.replace(" ", "")).status, "ACCEPTED")


class DisplayOmissionTests(unittest.TestCase):
    def test_contrast_and_population_drop_is_not_accepted(self):
        source = next(item["body"] for item in burden_slide()["items"] if str(item["body"]).startswith("相比"))
        display = "重度哮喘患者疾病负担重"
        result = gate_display(source, display)
        self.assertNotEqual(result.status, "ACCEPTED")
        self.assertEqual(result.status, "NEEDS_REVIEW")
        self.assertEqual(result.omissions, ("DROP_CONTRAST", "DROP_POPULATION"))
        self.assertIn("相比", result.omitted_texts)
        self.assertIn("轻中度哮喘", result.omitted_texts)
        self.assertIn("CONTRAST_DROPPED", result.issues)
        self.assertIn("POPULATION_CHANGED", result.issues)

    def test_full_contrast_sentence_is_accepted(self):
        source = next(item["body"] for item in burden_slide()["items"] if str(item["body"]).startswith("相比"))
        result = gate_display(source, source)
        self.assertEqual(result.status, "ACCEPTED")
        self.assertEqual(result.omissions, ())

    def test_quantifier_and_population_drop_on_percent(self):
        source = next(item["body"] for item in burden_slide()["items"] if "50%" in item["body"])
        result = gate_display(source, "50%")
        self.assertEqual(result.status, "NEEDS_REVIEW")
        self.assertEqual(result.omissions, ("DROP_POPULATION", "DROP_QUANTIFIER"))
        self.assertIn("约", result.omitted_texts)
        self.assertTrue(any("拟诊" in text for text in result.omitted_texts))
        self.assertEqual(gate_display(source, source).status, "ACCEPTED")

    def test_time_and_quantifier_drop_on_duration_fragment(self):
        source = next(item["body"] for item in review_slide()["items"] if "3个月" in item["body"])
        result = gate_display(source, "3个月")
        self.assertEqual(result.status, "NEEDS_REVIEW")
        self.assertEqual(result.omissions, ("DROP_QUANTIFIER", "DROP_TIME_WINDOW"))
        self.assertTrue(any("连续" in text and "3个月" in text for text in result.omitted_texts))
        self.assertIn("及以上", result.omitted_texts)
        self.assertTrue(any("中-高" in text for text in result.omitted_texts))
        self.assertEqual(gate_display(source, source).status, "ACCEPTED")

    def test_layout_duration_anchor_is_not_admitted(self):
        slide = review_slide()
        source = next(item["body"] for item in slide["items"] if "3个月" in item["body"])
        selection = select_layout(slide)
        self.assertNotEqual(selection.anchor["value"], "3个月")
        self.assertEqual(selection.anchor["value"], "")
        bare = gate_display(source, "3个月")
        self.assertNotEqual(bare.status, "ACCEPTED")
        self.assertIn("DROP_TIME_WINDOW", bare.omissions)
        admitted = gate_display(source, selection.anchor["statement"])
        self.assertEqual(admitted.status, "ACCEPTED")

    def test_schedule_drop_is_not_accepted(self):
        source = "美泊利珠单抗 100 mg，每 4 周 1 次"
        shortened = gate_display(source, "美泊利珠单抗 100 mg")
        self.assertEqual(shortened.status, "NEEDS_REVIEW")
        self.assertEqual(shortened.omissions, ("DROP_TIME_WINDOW",))
        self.assertIn("TIME_WINDOW_CHANGED", shortened.issues)
        self.assertEqual(gate_display(source, source).status, "ACCEPTED")

    def test_pre_post_comparison_cannot_collapse_to_one_endpoint(self):
        source = "12个月内急性发作率从1.8降至0.7，下降61%"
        result = gate_display(source, "61%")
        self.assertEqual(result.status, "NEEDS_REVIEW")
        self.assertEqual(result.omissions, ("DROP_CONTRAST", "DROP_TIME_WINDOW"))
        self.assertIn("降至", result.omitted_texts)
        self.assertIn("从", result.omitted_texts)
        self.assertTrue(any(text.startswith("12个月") for text in result.omitted_texts))
        self.assertEqual(gate_display(source, source).status, "ACCEPTED")

    def test_age_window_contrast_and_time_cannot_collapse(self):
        source = "通常 ≥40岁，但可能在成年早期或儿童期已有症状"
        result = gate_display(source, "≥40岁")
        self.assertEqual(result.status, "NEEDS_REVIEW")
        self.assertEqual(result.omissions, ("DROP_CONTRAST", "DROP_TIME_WINDOW"))
        self.assertIn("但", result.omitted_texts)
        self.assertIn("成年早期", result.omitted_texts)
        self.assertIn("儿童期", result.omitted_texts)
        self.assertEqual(gate_display(source, source).status, "ACCEPTED")

    def test_comparator_symbol_drop_is_not_accepted(self):
        line = pathway_slide()["nodes"][1]["lines"][0]
        self.assertEqual(gate_display(line, line).status, "ACCEPTED")
        dropped = gate_display(line, line.replace("＞", ""))
        self.assertEqual(dropped.status, "NEEDS_REVIEW")
        self.assertEqual(dropped.omissions, ("DROP_QUANTIFIER",))
        bare = gate_display(line, "1500")
        self.assertEqual(bare.status, "REJECTED")
        self.assertEqual(bare.reason_code, "NUMERIC_UNIT_MISMATCH")

    def test_second_threshold_line_is_faithful_to_itself(self):
        line = pathway_slide()["nodes"][4]["lines"][1]
        self.assertEqual(gate_display(line, line).status, "ACCEPTED")


class HumanGateTests(unittest.TestCase):
    def _contrast(self):
        return next(item["body"] for item in burden_slide()["items"] if str(item["body"]).startswith("相比"))

    def test_named_derivation_and_human_gate_allow_omission(self):
        source = self._contrast()
        display = "重度哮喘患者疾病负担重"
        gate = _allow(("DROP_CONTRAST", "DROP_POPULATION"))
        result = gate_display(source, display, **gate)
        self.assertEqual(result.status, "ACCEPTED")
        self.assertEqual(result.reason_code, "HUMAN_GATE_OMISSION")
        self.assertIn("CONTRAST_DROPPED", result.issues)
        self.assertIn("POPULATION_CHANGED", result.issues)
        self.assertFalse(result.admits_to_approved_graph)

    def test_partial_human_gate_stays_needs_review(self):
        source = self._contrast()
        display = "重度哮喘患者疾病负担重"
        result = gate_display(
            source,
            display,
            derivation=("DROP_CONTRAST", "DROP_POPULATION"),
            human_gate={
                "decision": "ALLOW_OMISSION",
                "reviewer_id": "rev-1",
                "covers": ("DROP_CONTRAST",),
            },
        )
        self.assertEqual(result.status, "NEEDS_REVIEW")
        missing_reviewer = gate_display(
            source,
            display,
            derivation=("DROP_CONTRAST", "DROP_POPULATION"),
            human_gate={"decision": "ALLOW_OMISSION", "reviewer_id": "  ", "covers": ("DROP_CONTRAST", "DROP_POPULATION")},
        )
        self.assertEqual(missing_reviewer.status, "NEEDS_REVIEW")

    def test_graph_approved_decision_is_not_a_human_gate(self):
        source = self._contrast()
        result = gate_display(
            source,
            "重度哮喘患者疾病负担重",
            derivation=("DROP_CONTRAST", "DROP_POPULATION"),
            human_gate={
                "decision": "APPROVED",
                "reviewer_id": "rev-1",
                "covers": ("DROP_CONTRAST", "DROP_POPULATION"),
            },
        )
        self.assertEqual(result.status, "NEEDS_REVIEW")
        self.assertNotEqual(result.status, "ACCEPTED")

    def test_free_text_derivation_is_ignored(self):
        source = self._contrast()
        result = gate_display(
            source,
            "重度哮喘患者疾病负担重",
            derivation="把对比删了",
            human_gate={
                "decision": "ALLOW_OMISSION",
                "reviewer_id": "rev-1",
                "covers": ("DROP_CONTRAST", "DROP_POPULATION"),
            },
        )
        self.assertEqual(result.status, "NEEDS_REVIEW")

    def test_human_gate_cannot_launder_numeric_stitch(self):
        gate = _allow(("DROP_CONTRAST", "DROP_POPULATION", "DROP_QUANTIFIER", "DROP_TIME_WINDOW"))
        result = gate_display("美泊利珠单抗 10 0 mg", "100 mg", **gate)
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reason_code, "NUMERIC_STITCH")

    def test_display_acceptance_is_not_graph_approval(self):
        samples = [
            gate_display("美泊利珠单抗 100 mg", "美泊利珠单抗 100 mg"),
            gate_display("相比轻中度哮喘，重度哮喘患者疾病负担重", "重度哮喘患者疾病负担重"),
            gate_display("10 0 mg", "100 mg"),
        ]
        self.assertEqual([item.status for item in samples], ["ACCEPTED", "NEEDS_REVIEW", "REJECTED"])
        for item in samples:
            self.assertIn(item.status, {"ACCEPTED", "NEEDS_REVIEW", "REJECTED"})
            self.assertNotIn(item.status, {"APPROVED", "VERIFIED", "CANDIDATE", "SUPPORTED"})
            self.assertFalse(item.admits_to_approved_graph)


if __name__ == "__main__":
    unittest.main()
