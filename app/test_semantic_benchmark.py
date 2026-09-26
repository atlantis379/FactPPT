from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.content_contract import EvidenceAssertion, SourceExcerpt, SourceLocator, assess_assertion, digest


CASES = json.loads(Path(__file__).with_name("semantic_benchmark.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_cross_industry_source_to_assertion_benchmark(case):
    excerpt = SourceExcerpt(
        id="source", source_sha256=digest(case["source"]),
        locator=SourceLocator(kind="PDF", page=1),
        extracted_text=case["source"], quote=case["source"],
    )
    assertion = EvidenceAssertion(id="assertion", text=case["assertion"],
                                  source_excerpt_ids=["source"])
    assert assess_assertion(assertion, {"source": excerpt}).status == case["expected"]
