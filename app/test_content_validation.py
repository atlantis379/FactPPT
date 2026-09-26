from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.content_contract import (ControlledCalculation, DataFact, EvidenceAssertion,
                                  ReviewReceipt, SlideStatement, SourceExcerpt, SourceLocator,
                                  contract_digest, digest)
from app.content_validation import ContentPackage, verify_content_package
from app.main import app


def package(quote: str, claim: str, slide: str | None = None) -> ContentPackage:
    return ContentPackage(
        source_excerpts=[SourceExcerpt(
            id="s", source_sha256=digest("input"), locator=SourceLocator(kind="PDF", page=2),
            extracted_text=quote, quote=quote,
        )],
        assertions=[EvidenceAssertion(id="a", text=claim, source_excerpt_ids=["s"])],
        slide_statements=[SlideStatement(id="p", text=slide or claim, assertion_ids=["a"])],
    )


def test_upstream_assertion_review_carries_through_to_unchanged_slide():
    item = package("仅试点地区的收入增长。", "试点地区的收入增长。")
    report = verify_content_package(item)
    assert report.status == "NEEDS_REVIEW"
    assert report.assertion_findings["a"].status == "NEEDS_REVIEW"
    assert report.slide_findings["p"].codes == ["UPSTREAM_ASSERTION_NEEDS_REVIEW"]


def test_upstream_contradiction_blocks_unchanged_slide():
    item = package("该观察记录未显示方案甲改善目标结局。", "该观察记录显示方案甲改善目标结局。")
    report = verify_content_package(item)
    assert report.status == "BLOCK"
    assert report.slide_findings["p"].codes == ["UPSTREAM_ASSERTION_BLOCKED"]


def test_v2_route_accepts_cross_industry_package():
    item = package("第三季度营收为100万元。", "第三季度营收为100万元。")
    response = TestClient(app).post("/api/v2/content/verify", json=item.model_dump())
    assert response.status_code == 200
    assert response.json()["status"] == "NEEDS_REVIEW"
    assert response.json()["source_findings"]["s"]["codes"] == ["SOURCE_FILE_NOT_VERIFIED"]


def test_duplicate_ids_are_rejected():
    item = package("本期收入增长。", "本期收入增长。")
    with pytest.raises(ValidationError, match="duplicate assertion id"):
        ContentPackage.model_validate({
            **item.model_dump(), "assertions": [item.assertions[0].model_dump()] * 2,
        })
    with pytest.raises(ValidationError, match="unique across content kinds"):
        ContentPackage.model_validate({
            **item.model_dump(), "slide_statements": [
                {**item.slide_statements[0].model_dump(), "id": "a"}],
        })


def test_trusted_independent_review_can_approve_paraphrase_but_not_reversal():
    item = package("在已完成问卷的客户中，满意率为80%。", "已完成问卷的客户满意率为80%。")
    key = contract_digest(item.assertions[0], item.source_excerpts)
    receipt = ReviewReceipt(subject_digest=key, author_id="generator",
                            reviewer_id="independent-reviewer", reviewer_kind="HUMAN",
                            decision="APPROVE", evidence_ids=["s"],
                            rationale="Reviewed the population and conclusion.")
    reviews = {"a": receipt}
    assert verify_content_package(item, authored_by="generator",
                                  trusted_assertion_reviews=reviews,
                                  trusted_excerpts={"s": item.source_excerpts[0]}).status == "SUPPORTED"
    changed = package("在已完成电话问卷的客户中，满意率为80%。", "已完成问卷的客户满意率为80%。")
    stale = verify_content_package(changed, authored_by="generator",
                                   trusted_assertion_reviews=reviews,
                                   trusted_excerpts={"s": changed.source_excerpts[0]})
    assert stale.status == "NEEDS_REVIEW"
    assert stale.assertion_findings["a"].codes == ["STALE_REVIEW"]
    reversed_item = package("该观察记录未显示方案甲改善目标结局。",
                            "该观察记录显示方案甲改善目标结局。")
    assert verify_content_package(reversed_item, authored_by="generator",
                                  trusted_assertion_reviews=reviews,
                                  trusted_excerpts={"s": reversed_item.source_excerpts[0]}).status == "BLOCK"


def test_public_v2_route_does_not_accept_review_receipts():
    item = package("在已完成问卷的客户中，满意率为80%。", "客户满意率为80%。")
    key = contract_digest(item.assertions[0], item.source_excerpts)
    payload = item.model_dump()
    payload["trusted_assertion_reviews"] = {
        "a": ReviewReceipt(subject_digest=key, author_id="generator",
                           reviewer_id="other", reviewer_kind="HUMAN",
                           decision="APPROVE", evidence_ids=["s"],
                           rationale="Reviewed the population and conclusion.").model_dump(mode="json")
    }
    response = TestClient(app).post("/api/v2/content/verify", json=payload)
    assert response.status_code == 422


def test_forged_extraction_is_blocked_even_for_verbatim_claim():
    item = package("第三季度营收为100万元。", "第三季度营收为100万元。")
    trusted = SourceExcerpt(
        id="s", source_sha256=digest("actual source file"),
        locator=SourceLocator(kind="PDF", page=2),
        extracted_text="第三季度营收为90万元。", quote="第三季度营收为90万元。",
    )
    report = verify_content_package(item, trusted_excerpts={"s": trusted})
    assert report.status == "BLOCK"
    assert report.source_findings["s"].codes == ["SOURCE_EXCERPT_MISMATCH"]
    assert report.assertion_findings["a"].codes == ["UPSTREAM_SOURCE_BLOCKED"]


def test_calculation_waits_for_trusted_source_extraction():
    item = package("上期收入为100万元。", "上期收入为100万元。")
    second = SourceExcerpt(id="s2", source_sha256=digest("input2"),
                           locator=SourceLocator(kind="XLSX", sheet="收入", cell="B3"),
                           extracted_text="120万元", quote="120万元")
    item.source_excerpts.append(second)
    item.data_facts = [
        DataFact(id="old", source_excerpt_id="s", value="100", unit="万元"),
        DataFact(id="new", source_excerpt_id="s2", value="120", unit="万元"),
    ]
    item.calculations = [ControlledCalculation(id="growth", operation="PERCENT_CHANGE",
                                              inputs=["100", "120"], input_ids=["old", "new"],
                                              result="20", unit="%")]
    untrusted = verify_content_package(item)
    assert untrusted.calculation_findings["growth"].codes == ["UPSTREAM_SOURCE_NOT_VERIFIED"]
    trusted = verify_content_package(item, trusted_excerpts={source.id: source for source in item.source_excerpts})
    assert trusted.calculation_findings["growth"].status == "SUPPORTED"
