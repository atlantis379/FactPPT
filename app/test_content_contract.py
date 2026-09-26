from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.content_contract import (
    ControlledCalculation,
    DataFact,
    EvidenceAssertion,
    SlideStatement,
    SourceExcerpt,
    SourceLocator,
    ReviewReceipt,
    apply_review,
    assess_assertion,
    assess_calculation,
    assess_slide_statement,
    contract_digest,
    digest,
)


def excerpt(quote: str, *, extracted_text: str | None = None) -> SourceExcerpt:
    return SourceExcerpt(
        id="s1", source_sha256=digest("source file"),
        locator=SourceLocator(kind="PDF", page=3),
        extracted_text=extracted_text or quote, quote=quote,
    )


def assertion(text: str) -> EvidenceAssertion:
    return EvidenceAssertion(id="a1", text=text, source_excerpt_ids=["s1"])


def test_source_locators_require_native_position():
    SourceLocator(kind="PDF", page=1)
    SourceLocator(kind="DOCX", paragraph=0)
    SourceLocator(kind="XLSX", sheet="销量", cell="B7")
    for bad in ({"kind": "PDF"}, {"kind": "DOCX"},
                {"kind": "XLSX", "sheet": "销量"}):
        with pytest.raises(ValidationError):
            SourceLocator(**bad)


def test_quote_must_occur_in_extracted_text():
    with pytest.raises(ValidationError, match="quote must occur"):
        excerpt("增长20%", extracted_text="下降20%")


def test_verbatim_assertion_and_unchanged_slide_statement_are_supported():
    source = excerpt("本期收入增长20%。")
    claim = assertion(source.quote)
    assert assess_assertion(claim, {"s1": source}).status == "SUPPORTED"
    slide = SlideStatement(id="p1", text=claim.text, assertion_ids=["a1"])
    assert assess_slide_statement(slide, {"a1": claim}).status == "SUPPORTED"


def test_negation_reversal_blocks_assertion_and_slide_statement():
    source = excerpt("该观察记录未显示方案甲改善目标结局。")
    claim = assertion("该观察记录显示方案甲改善目标结局。")
    finding = assess_assertion(claim, {"s1": source})
    assert finding.status == "BLOCK"
    assert "SHOW_REVERSAL" in finding.codes
    faithful = assertion(source.quote)
    slide = SlideStatement(id="p1", text=claim.text, assertion_ids=["a1"])
    finding = assess_slide_statement(slide, {"a1": faithful})
    assert finding.status == "BLOCK"


def test_paraphrase_requires_review_and_missing_link_blocks():
    source = excerpt("在已完成问卷的客户中，满意率为80%。")
    claim = assertion("客户满意率为80%。")
    assert assess_assertion(claim, {"s1": source}).status == "NEEDS_REVIEW"
    assert assess_assertion(claim, {}).status == "BLOCK"
    slide = SlideStatement(id="p1", text="满意率为80%", assertion_ids=["a1"])
    assert assess_slide_statement(slide, {"a1": claim}).status == "NEEDS_REVIEW"
    assert assess_slide_statement(slide, {}).status == "BLOCK"


def test_literal_substring_cannot_auto_approve_removed_condition():
    source = excerpt("仅当客户同意后方可共享资料。")
    claim = assertion("客户同意后方可共享资料。")
    assert assess_assertion(claim, {"s1": source}).status == "NEEDS_REVIEW"


def test_controlled_percent_change_and_bad_result():
    item = ControlledCalculation(
        id="growth", operation="PERCENT_CHANGE", inputs=["100", "120"],
        input_ids=["baseline", "latest"], result="20", unit="%",
    )
    assert item.result == "20"
    with pytest.raises(ValidationError, match="result does not equal"):
        ControlledCalculation.model_validate({**item.model_dump(), "result": "25"})


def test_controlled_calculation_rejects_division_by_zero():
    with pytest.raises(ValidationError, match="division by zero"):
        ControlledCalculation(
            id="growth", operation="RATIO", inputs=["0", "4"],
            input_ids=["baseline", "latest"], result="0", unit="ratio",
        )


def test_review_is_independent_and_bound_to_source_and_claim_version():
    source = excerpt("在已完成问卷的客户中，满意率为80%。")
    claim = assertion("已完成问卷的客户满意率为80%。")
    finding = assess_assertion(claim, {"s1": source})
    key = contract_digest(claim, [source])
    receipt = ReviewReceipt(subject_digest=key, author_id="writer",
                            reviewer_id="reviewer", reviewer_kind="HUMAN",
                            decision="APPROVE", evidence_ids=["s1"],
                            rationale="Reviewed the scope against the cited source.")
    assert apply_review(finding, key, "writer", receipt).status == "SUPPORTED"
    changed = assertion("已完成问卷的客户满意率为90%。")
    changed_key = contract_digest(changed, [source])
    assert apply_review(finding, changed_key, "writer", receipt).codes == ["STALE_REVIEW"]
    with pytest.raises(ValidationError, match="author cannot review"):
        ReviewReceipt(subject_digest=key, author_id="writer", reviewer_id="writer",
                      reviewer_kind="HUMAN", decision="APPROVE", evidence_ids=["s1"],
                      rationale="Reviewed the scope against the cited source.")


def test_model_review_requires_qualification_registry_match():
    source = excerpt("本期收入约增长20%。")
    claim = assertion("本期收入增长约20%。")
    finding = assess_assertion(claim, {"s1": source})
    key = contract_digest(claim, [source])
    receipt = ReviewReceipt(subject_digest=key, author_id="writer", reviewer_id="review-model",
                            reviewer_kind="QUALIFIED_MODEL", qualification_id="review-v1",
                            decision="APPROVE", evidence_ids=["s1"],
                            rationale="Reviewed the source qualifier and assertion.")
    assert apply_review(finding, key, "writer", receipt).codes == ["UNQUALIFIED_REVIEW_ROUTE"]
    assert apply_review(finding, key, "writer", receipt, {"review-v1"}).status == "SUPPORTED"


def test_calculation_inputs_are_bound_to_source_values_and_units():
    earlier = excerpt("上期收入为100万元。")
    latest = excerpt("本期收入为120万元。")
    latest.id = "s2"
    facts = {
        "earlier": DataFact(id="earlier", source_excerpt_id="s1", value="100", unit="万元"),
        "latest": DataFact(id="latest", source_excerpt_id="s2", value="120", unit="万元"),
    }
    calculation = ControlledCalculation(id="growth", operation="PERCENT_CHANGE", inputs=["100", "120"],
                                        input_ids=["earlier", "latest"], result="20", unit="%")
    assert assess_calculation(calculation, facts, {"s1": earlier, "s2": latest}).status == "SUPPORTED"
    changed = {**facts, "latest": DataFact(id="latest", source_excerpt_id="s2", value="125", unit="万元")}
    assert assess_calculation(calculation, changed, {"s1": earlier, "s2": latest}).codes == ["CALCULATION_INPUT_MISMATCH"]


def test_calculation_rejects_unit_mismatch_and_nonfinite_inputs():
    first = excerpt("上期收入为100万元。")
    second = excerpt("本期收入为120元。")
    second.id = "s2"
    facts = {
        "first": DataFact(id="first", source_excerpt_id="s1", value="100", unit="万元"),
        "second": DataFact(id="second", source_excerpt_id="s2", value="120", unit="元"),
    }
    calculation = ControlledCalculation(id="growth", operation="PERCENT_CHANGE", inputs=["100", "120"],
                                        input_ids=["first", "second"], result="20", unit="%")
    assert assess_calculation(calculation, facts, {"s1": first, "s2": second}).codes == ["INCOMPATIBLE_INPUT_UNITS"]
    with pytest.raises(ValidationError, match="finite"):
        DataFact(id="bad", source_excerpt_id="s1", value="NaN", unit="元")


def test_short_unit_cannot_match_suffix_of_a_different_source_unit():
    first = excerpt("上期收入为100万元。")
    second = excerpt("本期收入为120万元。")
    second.id = "s2"
    facts = {
        "first": DataFact(id="first", source_excerpt_id="s1", value="100", unit="元"),
        "second": DataFact(id="second", source_excerpt_id="s2", value="120", unit="元"),
    }
    calculation = ControlledCalculation(id="growth", operation="PERCENT_CHANGE",
                                        inputs=["100", "120"], input_ids=["first", "second"],
                                        result="20", unit="%")
    assert assess_calculation(calculation, facts, {"s1": first, "s2": second}).codes == ["DATA_FACT_SOURCE_BINDING"]


def test_derived_number_requires_linked_supported_calculation():
    earlier = excerpt("上期收入为100万元。")
    latest = excerpt("本期收入为120万元。")
    latest.id = "s2"
    facts = {
        "earlier": DataFact(id="earlier", source_excerpt_id="s1", value="100", unit="万元"),
        "latest": DataFact(id="latest", source_excerpt_id="s2", value="120", unit="万元"),
    }
    calculation = ControlledCalculation(id="growth", operation="PERCENT_CHANGE",
                                        inputs=["100", "120"], input_ids=["earlier", "latest"],
                                        result="20", unit="%")
    claim = EvidenceAssertion(id="a", text="收入增长20%。", source_excerpt_ids=["s1", "s2"])
    sources = {"s1": earlier, "s2": latest}
    assert assess_assertion(claim, sources).codes == ["UNSOURCED_NUMBER"]
    linked = claim.model_copy(update={"calculation_ids": ["growth"]})
    assert assess_assertion(linked, sources, {"growth": calculation}, facts).status == "NEEDS_REVIEW"
    incomplete_link = linked.model_copy(update={"source_excerpt_ids": ["s1"]})
    assert assess_assertion(incomplete_link, sources, {"growth": calculation}, facts).codes == ["CALCULATION_SOURCE_NOT_LINKED"]


def test_numeric_equivalence_preserves_commas_and_decimal_format():
    source = excerpt("今年订单数为1,000单。")
    claim = assertion("今年订单数为1000.0单。")
    assert assess_assertion(claim, {"s1": source}).status == "NEEDS_REVIEW"
    changed = assertion("今年订单数为1,200单。")
    assert assess_assertion(changed, {"s1": source}).codes == ["UNSOURCED_NUMBER"]


def test_slide_cannot_add_a_number_missing_from_approved_assertion():
    claim = assertion("第三季度营收为100万元。")
    slide = SlideStatement(id="p", text="第三季度营收为120万元。", assertion_ids=["a1"])
    assert assess_slide_statement(slide, {"a1": claim}).codes == ["UNAPPROVED_SLIDE_NUMBER"]


def test_unit_change_is_blocked_in_assertion_and_slide():
    source = excerpt("第三季度营收为100万元。")
    changed = assertion("第三季度营收为100元。")
    assert assess_assertion(changed, {"s1": source}).codes == ["UNIT_MISMATCH"]
    faithful = assertion(source.quote)
    slide = SlideStatement(id="p", text=changed.text, assertion_ids=["a1"])
    assert assess_slide_statement(slide, {"a1": faithful}).codes == ["UNAPPROVED_SLIDE_UNIT"]
