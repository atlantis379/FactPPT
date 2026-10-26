"""Lexicon contract for the display fact gate."""

import unittest

from factdeck.lexicon import (
    CONTRAST_PHRASES,
    DERIVATION_BY_KIND,
    DERIVATIONS,
    DRUGS,
    ISSUE_BY_DERIVATION,
    POPULATION_PHRASES,
    QUANTIFIER_PHRASES,
    TIME_PATTERNS,
)


class LexiconTests(unittest.TestCase):
    def test_derivations_match_omission_classes(self):
        self.assertEqual(
            DERIVATIONS,
            frozenset(
                {
                    "DROP_CONTRAST",
                    "DROP_POPULATION",
                    "DROP_TIME_WINDOW",
                    "DROP_QUANTIFIER",
                }
            ),
        )

    def test_each_derivation_has_a_gate_issue(self):
        self.assertEqual(set(ISSUE_BY_DERIVATION), set(DERIVATIONS))
        self.assertEqual(set(DERIVATION_BY_KIND.values()), set(DERIVATIONS))
        self.assertEqual(ISSUE_BY_DERIVATION["DROP_CONTRAST"], "CONTRAST_DROPPED")
        self.assertEqual(ISSUE_BY_DERIVATION["DROP_POPULATION"], "POPULATION_CHANGED")
        self.assertEqual(ISSUE_BY_DERIVATION["DROP_TIME_WINDOW"], "TIME_WINDOW_CHANGED")
        self.assertEqual(ISSUE_BY_DERIVATION["DROP_QUANTIFIER"], "MISSING_QUALIFIER")

    def test_drug_list_has_biologics_and_il5_family(self):
        for name in ("美泊利珠单抗", "mepolizumab", "抗IL-5R", "抗IL-5", "ICS-LABA", "OCS"):
            self.assertIn(name, DRUGS)
        self.assertGreater(len("抗IL-5R"), len("抗IL-5"))

    def test_qualifier_lists_cover_four_classes(self):
        self.assertIn("相比", CONTRAST_PHRASES)
        self.assertIn("降至", CONTRAST_PHRASES)
        self.assertIn("拟诊重度哮喘患者", POPULATION_PHRASES)
        self.assertIn("轻中度哮喘", POPULATION_PHRASES)
        self.assertIn("及以上", QUANTIFIER_PHRASES)
        self.assertIn("中-高剂量", QUANTIFIER_PHRASES)
        self.assertTrue(TIME_PATTERNS)
        self.assertTrue(any("儿童期" in pattern for pattern in TIME_PATTERNS))


if __name__ == "__main__":
    unittest.main()
