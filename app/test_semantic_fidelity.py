from __future__ import annotations

from app.main import Claim, Project, SourceRef, source_span_support, verifier
from app.semantic_fidelity import contradiction_signals, missing_source_signals


def _project(source: str, statement: str) -> Project:
    claim = Claim(
        id="c1", normalized_claim=statement, source_quote=source,
        provenance="SOURCE", risk="YELLOW",
        source_refs=[SourceRef(document_id="doc", page=1, quote=source)],
    )
    return Project(
        title="Evidence test", presentation_question="What did the source find?",
        documents=[{"id": "doc", "chunks": [{"page": 1, "text": source}]}],
        claims=[claim],
    )


def test_negation_reversal_blocks_quoted_claim_despite_high_overlap():
    project = _project("该观察记录未显示方案甲改善目标结局。", "该观察记录显示方案甲改善目标结局。")
    span = source_span_support(project.claims[0])
    assert span["coverage"] > 0.30
    assert span["status"] == "CONTRADICTED"
    assert "SHOW_REVERSAL" in span["semantic_signals"]
    result = verifier(project)
    assert result["status"] == "BLOCK"
    assert any(issue["type"] == "MINIMUM_SOURCE_SPAN" and issue["severity"] == "BLOCK"
               for issue in result["issues"])


def test_direction_reversal_blocks_claim():
    result = verifier(_project("本期成本较上期下降。", "本期成本较上期上升。"))
    assert result["status"] == "BLOCK"
    assert "DIRECTION_REVERSAL" in result["source_span_support"][0]["semantic_signals"]


def test_omitted_qualifier_requires_review():
    result = verifier(_project("本期增长率没有显示改善。", "本期增长率有所变化。"))
    assert result["status"] == "HUMAN_REVIEW_REQUIRED"
    assert "SHOW_OMITTED" in result["source_span_support"][0]["semantic_signals"]


def test_exact_source_statement_keeps_its_stance():
    text = "本期成本较上期下降。"
    result = verifier(_project(text, text))
    assert result["status"] == "PASS"
    assert contradiction_signals(text, text) == []
    assert missing_source_signals(text, text) == []


def test_english_negation_reversal_is_detected():
    issues = contradiction_signals("The trial did not show improvement.",
                                   "The trial showed improvement.")
    assert issues == ["SHOW_REVERSAL"]


def test_mixed_quote_requires_review_when_one_clause_is_silently_selected():
    source = "第一组未显示改善；第二组显示改善。"
    statement = "第二组显示改善。"
    result = verifier(_project(source, statement))
    assert result["status"] == "HUMAN_REVIEW_REQUIRED"
    assert "SHOW_OMITTED" in result["source_span_support"][0]["semantic_signals"]


def test_scope_expansion_is_blocked():
    source = "仅试点地区的客户满意率提升。"
    statement = "所有地区的客户满意率提升。"
    result = verifier(_project(source, statement))
    assert result["status"] == "BLOCK"
    assert "SCOPE_EXPANSION" in result["source_span_support"][0]["semantic_signals"]


def test_condition_removal_requires_review():
    source = "如果通过验收，项目可进入下一阶段。"
    statement = "项目可进入下一阶段。"
    result = verifier(_project(source, statement))
    assert result["status"] == "HUMAN_REVIEW_REQUIRED"
    assert "CONDITION_OMITTED" in result["source_span_support"][0]["semantic_signals"]


def test_strength_upgrade_is_blocked():
    source = "初步数据提示新流程可能缩短处理时间。"
    statement = "数据证明新流程一定缩短处理时间。"
    result = verifier(_project(source, statement))
    assert result["status"] == "BLOCK"
    assert "STRENGTH_UPGRADE" in result["source_span_support"][0]["semantic_signals"]
