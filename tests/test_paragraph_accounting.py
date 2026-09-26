# -*- coding: utf-8 -*-
"""Paragraph-level read accounting (rule version `read_unit_classifier.v2`).

A unit-level receipt answers "did this page yield anything". That is not the same question as
"was the page read". The chapter's empirical-treatment table -- four patient groups and their
drugs -- sat on a page that had already produced candidates, so the page-level rule passed while
the most load-bearing paragraph in the section was never extracted. On the real chapter the
page-level rule reported a clean read of 222/222 meaning-critical values; the paragraph rule
found 116 of 251 substantive paragraphs represented by nothing at all.
"""
from __future__ import annotations

from app.read_units import (MIN_PARAGRAPH_CHARS, audit_read_receipts, classify_units,
                            paragraph_is_covered, segment_paragraphs)

LONG = ("社区获得性肺炎的临床诊断依据包括社区发病，以及新近出现的咳嗽、咳痰或原有呼吸道症状加重，"  # > 40 chars
        "并伴或不伴脓性痰、胸痛、呼吸困难。")
OTHER = "青壮年无基础疾病病人可选用青霉素类或呼吸喹诺酮类作为经验性治疗用药，疗程视病情而定。"


class _Ref:
    def __init__(self, page: int) -> None:
        self.page = page


class _Claim:
    def __init__(self, page: int, quote: str, claim: str = "") -> None:
        self.source_refs = [_Ref(page)]
        self.source_quote = quote
        self.normalized_claim = claim or quote


def _audit(text: str, receipts, claims=()):
    return audit_read_receipts(units=classify_units([{"page": 1, "text": text}]),
                               receipts=receipts, claims=list(claims))


LONG = LONG.replace("\n", "")


def test_segmenting_keeps_blank_lines_out_and_indexes_what_remains():
    paragraphs = segment_paragraphs("第一段。\n\n第二段。\n   \n第三段。")
    assert [p["index"] for p in paragraphs] == [0, 1, 2]
    assert [p["text"] for p in paragraphs] == ["第一段。", "第二段。", "第三段。"]


def test_a_quote_representing_a_paragraph_counts_as_covered():
    assert paragraph_is_covered(LONG, [LONG])
    # A quote from a different statement does not represent it.
    assert paragraph_is_covered(LONG, ["肺脓肿病人应给予体位引流并考虑手术指征，疗程通常需要数周。"]) is False


def test_a_substantive_paragraph_no_quote_represents_blocks_and_is_named():
    """The regression this rule exists for: a page with a candidate still had an unread paragraph."""
    text = f"{LONG}\n{OTHER}"
    result = _audit(text, [{"page": 1, "status": "HAS_CANDIDATES"}], [_Claim(1, LONG)])
    assert result["status"] == "BLOCK"
    assert result["statistics"]["paragraphs"] == 2
    assert result["statistics"]["paragraphs_covered"] == 1
    assert result["statistics"]["paragraphs_unaccounted"] == 1
    issue = next(item for item in result["issues"] if item["code"] == "PARAGRAPH_NOT_ACCOUNTED")
    assert issue["page"] == 1 and issue["paragraph"] == 1


def test_a_paragraph_excluded_with_an_allowed_reason_is_accepted():
    text = f"{LONG}\n{OTHER}"
    result = _audit(text, [{"page": 1, "status": "HAS_CANDIDATES",
                            "paragraph_exclusions": [{"paragraph": 1, "reason": "OPERATIONAL_DETAIL"}]}],
                    [_Claim(1, LONG)])
    assert result["status"] == "PASS"
    assert result["statistics"]["paragraphs_excluded"] == 1


def test_a_paragraph_exclusion_with_an_unknown_reason_is_refused():
    text = f"{LONG}\n{OTHER}"
    result = _audit(text, [{"page": 1, "status": "HAS_CANDIDATES",
                            "paragraph_exclusions": [{"paragraph": 1, "reason": "BECAUSE_I_SAID_SO"}]}],
                    [_Claim(1, LONG)])
    assert result["status"] == "BLOCK"
    assert any(item["code"] == "PARAGRAPH_EXCLUSION_REASON_UNKNOWN" for item in result["issues"])


def test_a_declined_unit_is_not_asked_for_a_receipt_per_paragraph():
    """A decline already states a reason for the whole page; a reference list does not need
    paragraph-by-paragraph paperwork on top of it."""
    result = _audit(f"{LONG}\n{OTHER}",
                    [{"page": 1, "status": "NO_QUOTABLE_CONTENT", "reason": "REFERENCE_LIST"}])
    assert result["statistics"]["paragraphs"] == 0
    assert not any(item["code"] == "PARAGRAPH_NOT_ACCOUNTED" for item in result["issues"])


def test_a_short_paragraph_is_accounted_for_by_its_neighbour():
    """Headings and labels are not substantively readable on their own."""
    text = "一、概述\n" + LONG
    result = _audit(text, [{"page": 1, "status": "HAS_CANDIDATES"}], [_Claim(1, LONG)])
    assert result["statistics"]["paragraphs"] == 1
    assert len("一、概述") < MIN_PARAGRAPH_CHARS
