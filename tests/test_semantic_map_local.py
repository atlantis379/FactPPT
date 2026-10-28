"""Local FactPPTv2 semantic_map tests (no factdeck.summary / slots required)."""

from __future__ import annotations

import json
import unittest

from factdeck.semantic_map import (
    PIPELINE_ORDER,
    SCHEMA_VERSION,
    SEMANTIC_MAP_SCHEMA,
    STAGE,
    SemanticMapError,
    attach_claims,
    classify_key_points,
    parse_semantic_map,
)

_DEF = "定义节点的第一条完整说明。"
_TABLE = "旁支表格的完整说明。"


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


class ParseSemanticMapTests(unittest.TestCase):
    def test_happy_path_parses_and_orders_mainline_first(self):
        parsed = parse_semantic_map(json.dumps(_map()))
        self.assertEqual(parsed.schema_version, SEMANTIC_MAP_SCHEMA["$id"])
        self.assertEqual(parsed.teaching_ids(), ("definition", "pathway", "table"))
        self.assertEqual(STAGE, "SEMANTIC_MAP")
        again = parse_semantic_map(parsed.to_dict())
        self.assertEqual(again.teaching_ids(), parsed.teaching_ids())
        self.assertEqual(again.edges[0].source, "table")

    def test_digits_rejected_in_one_liner_and_thesis(self):
        bad = _map()
        bad["one_liner"] = "覆盖 100 mg 的方案。"
        with self.assertRaises(SemanticMapError) as caught:
            parse_semantic_map(bad)
        self.assertEqual(caught.exception.code, "DIGITS")
        bad2 = _map()
        bad2["nodes"][0]["thesis"] = "剂量是 100 mg。"
        with self.assertRaises(SemanticMapError) as caught:
            parse_semantic_map(bad2)
        self.assertEqual(caught.exception.code, "DIGITS")
        # title may carry a digit
        ok = _map()
        ok["nodes"][1]["title"] = "第2步"
        self.assertEqual(parse_semantic_map(ok).nodes[1].title, "第2步")

    def test_reserved_unassigned_id_forbidden(self):
        bad = _map()
        bad["nodes"][1]["id"] = "unassigned"
        with self.assertRaises(SemanticMapError) as caught:
            parse_semantic_map(bad)
        self.assertEqual(caught.exception.code, "RESERVED_ID")

    def test_pipeline_puts_map_before_claims(self):
        self.assertLess(PIPELINE_ORDER.index("SEMANTIC_MAP"), PIPELINE_ORDER.index("CLAIMS"))
        self.assertLess(PIPELINE_ORDER.index("CLAIMS"), PIPELINE_ORDER.index("SUMMARY"))


class AttachClaimsTests(unittest.TestCase):
    def test_missing_node_id_is_unassigned(self):
        orphan = _claim("c-orphan", _DEF, "definition")
        del orphan["semantic_node_id"]
        attached = attach_claims([orphan, _claim("c-def", _DEF, "definition")], _map())
        self.assertEqual([c.claim_id for c in attached.unassigned], ["c-orphan"])
        self.assertEqual([c.claim_id for c in attached.by_node["definition"]], ["c-def"])
        self.assertEqual(attached.violations[0].code, "MISSING_NODE")

    def test_explicit_unassigned_stays_out_of_real_nodes(self):
        attached = attach_claims(
            [
                _claim("c-unknown", _DEF, "nope"),
                _claim("c-bucket", _TABLE, "unassigned"),
                _claim("c-def", _DEF, "definition"),
            ],
            _map(),
        )
        self.assertEqual([c.claim_id for c in attached.unassigned], ["c-unknown", "c-bucket"])
        self.assertEqual([v.code for v in attached.violations], ["UNKNOWN_NODE", "UNASSIGNED"])
        placed = [c.claim_id for group in attached.by_node.values() for c in group]
        self.assertEqual(placed, ["c-def"])


class ClassifyKeyPointsTests(unittest.TestCase):
    def test_wrong_node_flagged(self):
        claims = [
            _claim("c-def", _DEF, "definition"),
            _claim("c-table", _TABLE, "table"),
        ]
        points = [{"id": "kp-def", "semantic_node_id": "definition", "claim_ids": ["c-table"]}]
        flags = classify_key_points(_map(), points, claims)
        self.assertEqual(flags[0].code, "WRONG_NODE")
        self.assertEqual(flags[0].claim_id, "c-table")


if __name__ == "__main__":
    unittest.main()


# ---- code-cut claims and topic passes (factdeck.auto_claims, factdeck.topic_pass)
import pytest

from factdeck import auto_claims, topic_pass
from factdeck.claims import qualifiers


def _unit(uid, text, page="P:1", **kw):
    return {"id": uid, "source_id": "P", "page_id": page, "text": text, **kw}


def test_cutting_keeps_every_character_and_splits_off_headings_headers_and_references():
    u = _unit("P:1", "（Some Journal ） ，2026 年 3 月，第 7 卷，第 1 期 1 概念 1.1 定义 缓解一般指病情长期处于低水平。"
                     "这一状态并不等同于治愈。 1. 张三. 某研究[J]. 某杂志,2025,48(3):208-248.")
    cl = auto_claims.cut([u], {"P:1": "SUBSTANTIVE"}, {"P:1": "t1"})
    assert not auto_claims.verify(cl, {"P:1": u})
    kinds = [(c["kind"], c["quote"]) for c in cl]
    assert kinds[0][0] == "reference" and "第 7 卷" in kinds[0][1]
    assert ("heading", "1 概念") in kinds and ("heading", "1.1 定义") in kinds
    assert ("sentence", "缓解一般指病情长期处于低水平。") in kinds and ("sentence", "这一状态并不等同于治愈。") in kinds
    assert kinds[-1][0] == "reference" and all(c["topic"] == "t1" for c in cl)


def test_a_repeated_author_title_is_content_but_a_repeated_footer_is_boilerplate():
    units = [_unit(f"P:{i}:t", "确诊前应系统评估", page=f"P:{i}", signals={"title": ["确诊前应系统评估"]}) for i in range(4)]
    units += [_unit(f"P:{i}:f", "仅供医疗卫生专业人士参考", page=f"P:{i}") for i in range(4)]
    kinds = {c["unit_id"]: c["kind"] for c in auto_claims.cut(units, {}, {})}
    assert kinds["P:0:t"] != "boilerplate" and kinds["P:0:f"] == "boilerplate"


def test_qualifier_characters_inside_other_words_are_not_qualifiers():
    assert qualifiers("对靶向治疗应答良好") == [] and qualifiers("不良反应风险增加") == []
    assert "不" in qualifiers("不要停止维持治疗") and "可能" in qualifiers("约三成患者可能获益")


def _claims():
    units = [_unit("A:1", "启动后需定期评估。三到四个月后评估反应。若无效则停用。", page="A:1"),
             _unit("B:1", "缓解不等同于治愈。停药后可能复发。随访3年。", page="B:1"),
             _unit("A:2:t1r1c2", "组甲", page="A:2"), _unit("A:2:t1r2c1", "缓解率", page="A:2"),
             _unit("A:2:t1r2c2", "百分之四十", page="A:2")]
    for u in units:
        u["source_id"] = u["id"][0]
    return {c["id"]: c for c in auto_claims.cut(units, {}, {u["id"]: "t" for u in units})}


def _pass(**kw):
    r = {"schema_version": topic_pass.SCHEMA, "topic": "t", "question": "启动后怎样评估？",
         "messages": [{"id": "m1", "role": "core", "label": "何时评估", "claims": ["A:1~1", "A:1~2"]},
                      {"id": "m2", "role": "limit", "label": "缓解不是治愈", "claims": ["B:1~1"]},
                      {"id": "m3", "role": "reserve", "label": "随访时长", "claims": ["B:1~3"]}],
         "relations": [{"type": "sequence", "from": "m1", "to": ["m2"], "basis": ["A:1~2"]}],
         "page_plan": [["m1", "m2"]],
         "checks": [{"claims": ["A:2:t1r2c2~1"], "reason": "看不清对应的组"}],
         "left_out": [{"ids": ["A:1~3"], "why": "other_topic", "topic": "u", "note": "停用条件另讲"},
                      {"ids": ["B:1~2"], "why": "duplicate", "same_as": "B:1~1", "note": "与上句意思重复"}],
         "gaps": ["资料未给出停药时点"]}
    r.update(kw)
    return r


def test_topic_pass_accounts_for_every_sentence_and_row_and_flags_what_review_should_see():
    rec = topic_pass.check(_pass(), "t", _claims(), pages=1, topics={"t", "u"})
    assert rec["counts"]["checked"] == 1 and rec["signals"]["checks"] == ["A:2:t1r2c2~1"]
    assert rec["signals"]["authored_relations"] == [1]          # basis only from source A, the limit is from B
    assert rec["signals"]["other_topic"] == [("A:1~3", "u")]
    with pytest.raises(topic_pass.TopicPassError, match="既没有引用"):
        topic_pass.check(_pass(left_out=[]), "t", _claims(), topics={"t", "u"})
    with pytest.raises(topic_pass.TopicPassError, match="既没有引用"):     # the table row must be accounted for
        topic_pass.check(_pass(checks=[]), "t", _claims(), topics={"t", "u"})
    with pytest.raises(topic_pass.TopicPassError, match="reserve 信息不放进"):
        topic_pass.check(_pass(page_plan=[["m1", "m2", "m3"]]), "t", _claims(), topics={"t", "u"})
    with pytest.raises(topic_pass.TopicPassError, match="why"):
        topic_pass.check(_pass(left_out=[{"ids": ["A:1~3", "B:1~2"], "note": "不讲"}]), "t", _claims(), topics={"t", "u"})
    with pytest.raises(topic_pass.TopicPassError, match="same_as"):
        topic_pass.check(_pass(left_out=[{"ids": ["A:1~3"], "why": "other_topic", "topic": "u", "note": "x"},
                                         {"ids": ["B:1~2"], "why": "duplicate", "same_as": "A:1~3", "note": "y"}]), "t", _claims(), topics={"t", "u"})
    with pytest.raises(topic_pass.TopicPassError, match="另一个主题"):
        topic_pass.check(_pass(left_out=[{"ids": ["A:1~3"], "why": "other_topic", "topic": "t", "note": "x"},
                                         {"ids": ["B:1~2"], "why": "duplicate", "same_as": "B:1~1", "note": "y"}]), "t", _claims(), topics={"t", "u"})
    with pytest.raises(topic_pass.TopicPassError, match="core"):
        topic_pass.check(_pass(messages=[{"id": "m1", "role": "support", "label": "x", "claims": ["A:1~1"]}]), "t", _claims(), topics={"t", "u"})


def test_how_omissions_were_judged_is_signalled_for_review_not_refused():
    """Principles are refused (nothing disappears silently); the care of the judgment is reported (user, 2026-10-28)."""
    units = [_unit("A:1", "。".join(f"说明{n}项" for n in "甲乙丙丁戊己庚辛壬癸") + "。", page="A:1"),
             _unit("A:2", "结果为百分之四十。另组为三成。", page="A:2"), _unit("B:1", "缓解率为3成。复发率为2成。", page="B:1")]
    for u in units:
        u["source_id"] = u["id"][0]
    cl = {c["id"]: c for c in auto_claims.cut(units, {}, {u["id"]: "t" for u in units})}
    base = {"schema_version": topic_pass.SCHEMA, "topic": "t", "question": "问？",
            "messages": [{"id": "m1", "role": "core", "label": "要点", "claims": ["A:2~1", "A:2~2"]}], "page_plan": [["m1"]]}
    rec = topic_pass.check({**base, "left_out": [{"from": "A:1~1", "to": "A:1~10", "why": "off_topic", "note": "无关"},
                                                 {"ids": ["B:1~1", "B:1~2"], "why": "off_topic", "note": "无关（B:1）"}]}, "t", cl)
    sig = rec["signals"]
    assert sig["large_left_out_entries"] == [1] and sig["numeric_left_out_in_groups"] == ["B:1~1", "B:1~2"]
    assert sig["shared_off_topic_notes"] == [12]                 # the id suffix does not make the note a new one
    with pytest.raises(topic_pass.TopicPassError, match="既没有引用"):     # silent disappearance is still refused
        topic_pass.check({**base, "left_out": [{"from": "A:1~1", "to": "A:1~9", "why": "off_topic", "note": "无关"}]}, "t", cl)


def test_a_sentence_referred_from_another_topic_must_be_decided_here():
    cl = _claims()
    cl["X:1~1"] = {"id": "X:1~1", "unit_id": "X:1", "page_id": "X:1", "source_id": "X", "kind": "sentence",
                   "quote": "给药剂量为每四周一次。", "topic": "u"}
    with pytest.raises(topic_pass.TopicPassError, match="X:1~1"):
        topic_pass.check(_pass(), "t", cl, topics={"t", "u"}, referred={"X:1~1": "u"})
    r = _pass()
    r["messages"][2]["claims"].append("X:1~1")
    rec = topic_pass.check(r, "t", cl, topics={"t", "u"}, referred={"X:1~1": "u"})
    assert rec["signals"]["referred_in"] == ["X:1~1"] and rec["signals"]["borrowed_claims"] == []


def test_a_terminator_inside_brackets_does_not_cut_the_sentence():
    from factdeck.auto_claims import cut
    text = "该药还能减少低炎症（BEC<150/μl；FeNO<25 ppb）患者的急性发作，但未改善肺功能。下一句。括号未闭合（这里；后面很远" + "字" * 90 + "。"
    out = [c["quote"] for c in cut([{"id": "X:1:b1", "page_id": "X:1", "source_id": "X", "text": text}], {"X:1": "SUBSTANTIVE"}, {})]
    assert out[0].startswith("该药") and "FeNO<25 ppb）患者" in out[0]
    assert "下一句。" in out and any(q.startswith("括号未闭合（这里；") for q in out)
