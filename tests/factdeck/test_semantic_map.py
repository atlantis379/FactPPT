"""Semantic map schema, claim node ids, and summary chapter order.

The map is semantic_map.v1. Claims cite a node or land in unassigned.
SUMMARY chapters follow mainline nodes, then the other nodes. A key point
that cites another node's claim is rejected. The fact gate still drops a
clip the display rules do not admit.
"""

import json
import unittest

from factdeck.deck import build_deck
from factdeck.layout_selector import RETIRED_LAYOUTS
from factdeck.semantic_map import (
    PIPELINE_ORDER,
    SCHEMA_VERSION,
    SEMANTIC_MAP_SCHEMA,
    STAGE_ENTRY,
    SemanticMapError,
    attach_claims,
    classify_key_points,
    parse_semantic_map,
    summary_from_semantic_map,
)
from factdeck.summary import prepare_deck

_DEF = "定义节点的第一条完整说明。"
_DEF_2 = "定义节点的第二条完整说明。"
_PATH = "路径节点的完整说明。"
_TABLE = "旁支表格的完整说明。"
_CLIP = "3个月"
_CLIP_SOURCE = "指连续3个月及以上规范使用中-高剂量ICS-LABA"


def _map():
    return {
        "schema_version": SCHEMA_VERSION,
        "one_liner": "这份材料说明如何评估并选择路径。",
        "nodes": [
            {
                "id": "definition",
                "title": "定义",
                "role": "definition",
                "thesis": "先界定问题。",
                "unit_hints": ["u1"],
                "mainline": True,
            },
            {
                "id": "table",
                "title": "旁支",
                "role": "table",
                "thesis": "表格只作旁支。",
                "unit_hints": ["u2"],
                "mainline": False,
            },
            {
                "id": "pathway",
                "title": "路径",
                "role": "pathway",
                "thesis": "再给出路径。",
                "unit_hints": [],
                "mainline": True,
            },
        ],
        "edges": [{"from": "table", "to": "definition", "relation": "sequence"}],
    }


def _claim(claim_id, text, node, source_text=None):
    return {
        "claim_id": claim_id,
        "text": text,
        "source_text": text if source_text is None else source_text,
        "source_span_ids": [f"sp-{claim_id}"],
        "semantic_node_id": node,
    }


def _points():
    return [
        {"id": "kp-table", "semantic_node_id": "table", "claim_ids": ["c-table"]},
        {"id": "kp-def", "semantic_node_id": "definition", "claim_ids": ["c-def", "c-def-2"]},
        {"id": "kp-path", "semantic_node_id": "pathway", "claim_ids": ["c-path"]},
    ]


def _claims():
    return [
        _claim("c-def", _DEF, "definition"),
        _claim("c-def-2", _DEF_2, "definition"),
        _claim("c-table", _TABLE, "table"),
        _claim("c-path", _PATH, "pathway"),
    ]


class SchemaTests(unittest.TestCase):
    def test_minimal_artifact_parses_and_orders_mainline_first(self):
        parsed = parse_semantic_map(json.dumps(_map()))
        self.assertEqual(parsed.schema_version, SEMANTIC_MAP_SCHEMA["$id"])
        self.assertEqual(parsed.teaching_ids(), ("definition", "pathway", "table"))
        self.assertEqual(SEMANTIC_MAP_SCHEMA["required"], ["schema_version", "one_liner", "nodes"])
        self.assertIn("definition", SEMANTIC_MAP_SCHEMA["node_roles"])
        self.assertIn("sequence", SEMANTIC_MAP_SCHEMA["edge_relations"])
        again = parse_semantic_map(parsed.to_dict())
        self.assertEqual(again.teaching_ids(), parsed.teaching_ids())
        self.assertEqual(again.edges[0].source, "table")
        self.assertEqual(again.edges[0].target, "definition")

    def test_node_title_may_carry_a_digit_and_thesis_may_not(self):
        artifact = _map()
        artifact["nodes"][1]["title"] = "第2步"
        self.assertEqual(parse_semantic_map(artifact).nodes[1].title, "第2步")
        artifact["nodes"][1]["thesis"] = "剂量是 100 mg。"
        with self.assertRaises(SemanticMapError) as caught:
            parse_semantic_map(artifact)
        self.assertEqual(caught.exception.code, "DIGITS")

    def test_rejects_version_role_digits_extra_field_and_edges(self):
        cases = []
        bad_version = _map()
        bad_version["schema_version"] = "0.2"
        cases.append((bad_version, "SCHEMA_VERSION"))
        bad_role = _map()
        bad_role["nodes"][0]["role"] = "background"
        cases.append((bad_role, "ROLE"))
        bad_digits = _map()
        bad_digits["one_liner"] = "覆盖 100 mg 的方案。"
        cases.append((bad_digits, "DIGITS"))
        bad_sentences = _map()
        bad_sentences["one_liner"] = "第一句。第二句。"
        cases.append((bad_sentences, "MULTI_SENTENCE"))
        bad_field = _map()
        bad_field["notes"] = "旁注"
        cases.append((bad_field, "UNKNOWN_FIELD"))
        bad_id = _map()
        bad_id["nodes"][2]["id"] = "definition"
        cases.append((bad_id, "DUPLICATE_ID"))
        reserved = _map()
        reserved["nodes"][1]["id"] = "unassigned"
        cases.append((reserved, "RESERVED_ID"))
        bad_relation = _map()
        bad_relation["edges"] = [{"from": "definition", "to": "pathway", "relation": "causes"}]
        cases.append((bad_relation, "RELATION"))
        self_edge = _map()
        self_edge["edges"] = [{"from": "definition", "to": "definition", "relation": "sequence"}]
        cases.append((self_edge, "SELF_EDGE"))
        missing_end = _map()
        missing_end["edges"] = [{"from": "definition", "to": "missing", "relation": "evidence"}]
        cases.append((missing_end, "EDGE_ENDPOINT"))
        for artifact, code in cases:
            with self.subTest(code=code):
                with self.assertRaises(SemanticMapError) as caught:
                    parse_semantic_map(artifact)
                self.assertEqual(caught.exception.code, code)

    def test_pipeline_order_puts_the_map_before_claims_and_summary(self):
        self.assertLess(PIPELINE_ORDER.index("SEMANTIC_MAP"), PIPELINE_ORDER.index("CLAIMS"))
        self.assertLess(PIPELINE_ORDER.index("CLAIMS"), PIPELINE_ORDER.index("SUMMARY"))
        self.assertLess(PIPELINE_ORDER.index("SUMMARY"), PIPELINE_ORDER.index("FACTS"))
        self.assertLess(PIPELINE_ORDER.index("FACTS"), PIPELINE_ORDER.index("SLOTS"))
        self.assertLess(PIPELINE_ORDER.index("SLOTS"), PIPELINE_ORDER.index("PPT"))
        self.assertIsNone(STAGE_ENTRY["INGEST"])
        self.assertIsNone(STAGE_ENTRY["SUMMARY_REVIEW"])
        self.assertEqual(STAGE_ENTRY["FACTS"], "factdeck.facts.gate_display")


class ClaimAttachmentTests(unittest.TestCase):
    def test_missing_node_id_is_unassigned_and_not_placed_on_the_first_node(self):
        orphan = _claim("c-orphan", _DEF, "definition")
        del orphan["semantic_node_id"]
        attached = attach_claims([orphan, _claim("c-def", _DEF, "definition")], _map())
        self.assertEqual([claim.claim_id for claim in attached.unassigned], ["c-orphan"])
        self.assertEqual([claim.claim_id for claim in attached.by_node["definition"]], ["c-def"])
        self.assertEqual(attached.violations[0].code, "MISSING_NODE")
        self.assertEqual(list(attached.by_node), ["definition", "table", "pathway"])

    def test_unknown_and_explicit_unassigned_stay_out_of_real_nodes(self):
        attached = attach_claims(
            [
                _claim("c-unknown", _DEF, "nope"),
                _claim("c-bucket", _TABLE, "unassigned"),
                _claim("c-def", _DEF, "definition"),
            ],
            _map(),
        )
        self.assertEqual([claim.claim_id for claim in attached.unassigned], ["c-unknown", "c-bucket"])
        self.assertEqual([item.code for item in attached.violations], ["UNKNOWN_NODE", "UNASSIGNED"])
        placed = [claim.claim_id for group in attached.by_node.values() for claim in group]
        self.assertEqual(placed, ["c-def"])

    def test_reworded_claim_and_missing_span_are_rejected(self):
        reworded = _claim("c-def", "改写后的句子。", "definition", source_text=_DEF)
        with self.assertRaises(SemanticMapError) as caught:
            attach_claims([reworded], _map())
        self.assertEqual(caught.exception.code, "NON_VERBATIM")
        stitched = _claim("c-def", "100mg", "definition", source_text="100 mg")
        with self.assertRaises(SemanticMapError) as caught:
            attach_claims([stitched], _map())
        self.assertEqual(caught.exception.code, "NON_VERBATIM")
        missing = _claim("c-def", _DEF, "definition")
        missing["source_span_ids"] = []
        with self.assertRaises(SemanticMapError) as caught:
            attach_claims([missing], _map())
        self.assertEqual(caught.exception.code, "MISSING_SPAN")

    def test_unit_hints_do_not_move_a_claim(self):
        claim = _claim("c-def", _DEF, "definition")
        claim["unit_id"] = "u2"
        attached = attach_claims([claim], _map(), units={"u2": _DEF, "u1": "别的原文。"})
        self.assertEqual([item.claim_id for item in attached.by_node["definition"]], ["c-def"])
        self.assertEqual(attached.by_node["table"], ())
        self.assertEqual(attached.violations, ())
        claim["text"] = "不在单元里的句子。"
        claim["source_text"] = "不在单元里的句子。"
        with self.assertRaises(SemanticMapError) as caught:
            attach_claims([claim], _map(), units={"u2": _DEF})
        self.assertEqual(caught.exception.code, "NON_VERBATIM")


class SummaryOrderTests(unittest.TestCase):
    def test_classify_flags_a_key_point_from_another_node(self):
        points = [{"id": "kp-def", "semantic_node_id": "definition", "claim_ids": ["c-table"]}]
        flags = classify_key_points(_map(), points, _claims())
        self.assertEqual(flags[0].code, "WRONG_NODE")
        self.assertEqual(flags[0].claim_id, "c-table")
        self.assertEqual(flags[0].claim_node_id, "table")

    def test_summary_rejects_key_point_whose_claims_belong_to_another_node(self):
        points = [{"id": "kp-def", "semantic_node_id": "definition", "claim_ids": ["c-table"]}]
        with self.assertRaises(SemanticMapError) as caught:
            summary_from_semantic_map(_map(), points, _claims())
        self.assertEqual(caught.exception.code, "WRONG_NODE")
        with self.assertRaises(SemanticMapError) as caught:
            build_deck(semantic_map=_map(), key_points=points, claims=_claims())
        self.assertEqual(caught.exception.code, "WRONG_NODE")

    def test_summary_rejects_a_key_point_that_is_not_on_the_map(self):
        points = [{"id": "kp-new", "semantic_node_id": "invented", "claim_ids": ["c-def"]}]
        flags = classify_key_points(_map(), points, _claims())
        self.assertEqual(flags[0].code, "UNKNOWN_NODE")
        with self.assertRaises(SemanticMapError) as caught:
            summary_from_semantic_map(_map(), points, _claims())
        self.assertEqual(caught.exception.code, "UNKNOWN_NODE")

    def test_summary_refuses_an_unassigned_claim(self):
        orphan = _claim("c-def", _DEF, "definition")
        del orphan["semantic_node_id"]
        with self.assertRaises(SemanticMapError) as caught:
            summary_from_semantic_map(_map(), [], [orphan])
        self.assertEqual(caught.exception.code, "MISSING_NODE")

    def test_chapters_follow_mainline_then_branch_and_keep_key_point_order(self):
        deck = summary_from_semantic_map(_map(), _points(), _claims())
        self.assertEqual([section.section_id for section in deck.sections], ["definition", "pathway", "table"])
        self.assertEqual([bullet.text for bullet in deck.sections[0].bullets], [_DEF, _DEF_2])
        self.assertEqual([bullet.text for bullet in deck.sections[1].bullets], [_PATH])
        self.assertEqual([bullet.text for bullet in deck.sections[2].bullets], [_TABLE])
        self.assertEqual(deck.sections[0].bullets[0].text, _DEF)

    def test_key_point_text_outside_its_claim_is_rejected(self):
        claim = _claim("c-def", "正文完整说明。", "definition", source_text="前缀。正文完整说明。")
        point = {"id": "kp-def", "semantic_node_id": "definition", "claim_ids": ["c-def"], "text": "前缀"}
        with self.assertRaises(SemanticMapError) as caught:
            summary_from_semantic_map(_map(), [point], [claim])
        self.assertEqual(caught.exception.code, "NON_VERBATIM")

    def test_map_summary_still_omits_a_half_sentence(self):
        plan = "确认患者拥有（并知道如何使用）个性化的书面或电子哮喘行动计划"
        claim = _claim("c-plan", plan, "definition")
        point = {
            "id": "kp-plan",
            "semantic_node_id": "definition",
            "claim_ids": ["c-plan"],
            "text": "确认患者拥有",
        }
        deck = summary_from_semantic_map(_map(), [point], [claim])
        self.assertEqual(deck.sections[0].bullets[0].text, "确认患者拥有")
        prepared = prepare_deck(summary=deck)
        self.assertEqual(prepared.sections[0].bullets[0].reason, "HALF_SENTENCE")
        self.assertEqual(build_deck(semantic_map=_map(), key_points=[point], claims=[claim]), [])

    def test_build_deck_renders_map_order_and_still_omits_an_ungated_clip(self):
        clip = _claim("c-clip", _CLIP_SOURCE, "definition")
        full = _claim("c-full", "正文完整说明。", "definition")
        points = [
            {
                "id": "kp-clip",
                "semantic_node_id": "definition",
                "claim_ids": ["c-clip"],
                "text": _CLIP,
            },
            {"id": "kp-full", "semantic_node_id": "definition", "claim_ids": ["c-full"]},
            {"id": "kp-table", "semantic_node_id": "table", "claim_ids": ["c-table"]},
        ]
        claims = [clip, full, _claim("c-table", _TABLE, "table")]
        deck = summary_from_semantic_map(_map(), points, claims)
        self.assertEqual(deck.sections[0].bullets[0].text, _CLIP)
        prepared = prepare_deck(summary=deck)
        reasons = [bullet.reason for bullet in prepared.sections[0].bullets]
        self.assertEqual(reasons, ["UNGATED", "ADMITTED"])
        self.assertEqual(prepared.sections[0].bullets[0].bullet.text, _CLIP)
        pages = build_deck(semantic_map=_map(), key_points=points, claims=claims)
        self.assertEqual(len(pages), 2)
        self.assertIn("正文完整说明。", pages[0].html)
        self.assertNotIn(_CLIP, pages[0].html)
        self.assertNotIn(_TABLE, pages[0].html)
        self.assertIn(_TABLE, pages[1].html)
        self.assertNotIn("正文完整说明。", pages[1].html)
        for page in pages:
            self.assertNotIn(page.layout_id, RETIRED_LAYOUTS)
        with self.assertRaises(ValueError):
            build_deck([{"title": "剂量", "items": []}], semantic_map=_map(), key_points=[], claims=[])
        with self.assertRaises(ValueError):
            build_deck(key_points=[])


if __name__ == "__main__":
    unittest.main()
