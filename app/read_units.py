# -*- coding: utf-8 -*-
"""Per-unit reading receipts: what "I read the full text" has to account for.

Why this exists
---------------
The model route used to accept a reading as complete when it returned *some* quote-grounded
candidate. Nothing required a source unit to be accounted for, so a reader could hand back
three assertions from an eleven-page paper and pass. On the real GOLD 2026 material that is
exactly what happened: the read was scoped to what the deck intended to show, and eleven
meaning-critical values -- including all five magnitude figures on page 3 -- were never
extracted, with nothing noticing.

Two ideas fix that, and this module owns both:

* **Every source unit must be accounted for.** Either it yielded at least one grounded
  candidate, or the reader declines it with a reason from a closed list. A unit the code
  independently classifies as carrying content may not be declined at all.
* **Meaning-critical tokens must be accounted for one by one.** Thresholds, unit-bearing
  measurements and magnitude figures are enumerated by code from the unit text; each must be
  covered by an accepted candidate's own words, or excluded with a stated reason. Thresholds
  (`≥`, `≤`, `<`, `>`) may not be excluded -- they are the class whose silent loss this
  project exists to prevent.

The split matters: the *reading* must be broad and account for everything, and the *triage*
decides what is shown. Conflating the two is what made completeness unverifiable.

Scope
-----
These rules govern a **reading** -- the model route or an accepted reading artifact. They do
not govern `source_extractor`, the rule-based candidate generator: that is a candidate
generator, not a reader (the README says as much), and its output is already undeliverable
because RED numeric facts cannot be bound by rules alone.
"""
from __future__ import annotations

import re
from typing import Any

#: Bump when the classification or token rules change, so a challenged judgement can be
#: traced to the rule that produced it.
RULE_VERSION = "read_unit_classifier.v2"

#: Emphasis vocabulary used to *measure* a unit. Phase 2 reuses the artifact's own declared
#: `profile.signal_lexicon`; this default keeps Phase 1 self-contained and auditable.
DEFAULT_EMPHASIS_MARKERS = ("首次", "关键", "重要", "必须", "优先", "推荐", "强调", "警示", "零容忍")

#: Boilerplate that marks publication apparatus rather than clinical content.
BOILERPLATE_MARKERS = (
    "ISSN", "CN 44", "doi", "DOI", "收稿日期", "网络首发", "编辑部", "参考文献",
    "通信作者", "Corresponding author", "Author contributions", "Conflict of interest",
    "中图分类号", "文献标志码", "引用本文", "Citation", "Key words", "期刊",
)

#: A reference list carries dozens of bracketed citations; a body page carries a handful of
#: superscripts. Measured on the real material, body pages peak at 16 and reference lists
#: start at 44, so the gap is wide. Counting a body page as apparatus because of its
#: superscripts is how a completeness rule earns a reputation for noise.
REFERENCE_LIST_CITATION_MARKERS = 25

RECEIPT_HAS_CANDIDATES = "HAS_CANDIDATES"
RECEIPT_DECLINED = "NO_QUOTABLE_CONTENT"
RECEIPT_STATUSES = (RECEIPT_HAS_CANDIDATES, RECEIPT_DECLINED)

#: Why a unit may be declined. A closed list, because "nothing worth quoting" is exactly the
#: claim that must be reviewable rather than free text.
DECLINE_REASONS = (
    "MASTHEAD_OR_PUBLICATION_METADATA",
    "REFERENCE_LIST",
    "ACKNOWLEDGEMENT_OR_CONTRIBUTION",
    "TABLE_OF_CONTENTS",
    "DUPLICATE_OF_ANOTHER_UNIT",
    "OTHER",
)

#: Why a meaning-critical token may be left out of the deck. Thresholds are absent on purpose.
#: A unit-level receipt says "this page yielded something". That is not "the page was read": the
#: empirical-treatment table -- four patient groups and their drugs -- sat in a page that already had
#: candidates, so the page-level rule passed while the most load-bearing paragraph of the section was
#: never extracted. Prose content lives in paragraphs, so paragraphs are accounted for individually.
PARAGRAPH_EXCLUSION_REASONS = (
    "HEADING_OR_LABEL", "TABLE_OR_FIGURE_CAPTION", "OPERATIONAL_DETAIL",
    "DUPLICATED_ELSEWHERE_IN_DECK", "CONTEXT_ONLY_NOT_A_FINDING", "NOT_DECISION_RELEVANT_FOR_AUDIENCE",
    "SUPERSEDED_BY_ANOTHER_TOKEN", "SOURCE_ITSELF_QUALIFIES_OR_RETRACTS",
)
#: Headings, labels and table cells: accounted for by the paragraph they belong to.
MIN_PARAGRAPH_CHARS = 40
#: How much of a paragraph's vocabulary an accepted quote must carry to represent it.
PARAGRAPH_COVERAGE_RATIO = 0.5


EXCLUSION_REASONS = (
    "NOT_DECISION_RELEVANT_FOR_AUDIENCE",
    "DUPLICATED_ELSEWHERE_IN_DECK",
    "CONTEXT_ONLY_NOT_A_FINDING",
    "SUPERSEDED_BY_ANOTHER_TOKEN",
    "SOURCE_ITSELF_QUALIFIES_OR_RETRACTS",
)

CLASSIFICATIONS = ("CONTENT_BEARING", "MIXED", "NON_CONTENT")

_CITATION = re.compile(r"[［\[][^］\]]*[］\]]")
#: Calendar references are identifiers, not measurements: "2021 年", "2025-12-08", "2 月".
_CALENDAR = re.compile(r"(?:19|20)\d{2}\s*(?:年|月|日)?(?:\s*[-—－]\s*\d{1,2}\s*[-—－]?\s*\d{0,2})?")
_THRESHOLD = re.compile(r"[≥≤><]\s*\d+(?:\.\d+)?(?:\s*[%％])?")
_MEASUREMENT = re.compile(r"\d[\d,\.]*\s*(?:%|％|岁|d\b|天|周|次|mg\b|g\b|mL|mmHg|mmol)")
_MAGNITUDE = re.compile(r"\d[\d,\.]*\s*(?:万亿|亿|万)")


def content_text(text: str) -> str:
    """Unit text with publication apparatus and calendar references removed.

    Citation brackets hold reference numbers and page ranges that are not findings, and a
    calendar year is an identifier rather than a measurement -- counting either would make
    the audit fire on the masthead and the reference list, which is how a completeness rule
    earns a reputation for noise and then gets switched off.
    """
    return _CALENDAR.sub(" ", _CITATION.sub(" ", text or ""))


def _token(value: str) -> str:
    """Whitespace-collapsed token form.

    PDF extraction wraps lines mid-value ("≥\\n75 岁"), so a raw match is neither readable in
    a finding nor nameable in an exclusion. Both sides of the comparison use this form, so
    collapsing cannot hide a difference.
    """
    return re.sub(r"\s+", "", value or "")


def measure_unit(text: str, *, emphasis_markers: tuple[str, ...] = DEFAULT_EMPHASIS_MARKERS) -> dict[str, Any]:
    """Deterministic signals for one unit. Counted by code, never asserted by a model."""
    body = content_text(text)
    return {
        "chars": len(text or ""),
        "content_chars": len(body),
        "thresholds": sorted({_token(match.group(0)) for match in _THRESHOLD.finditer(body)}),
        "measurements": sorted({_token(match.group(0)) for match in _MEASUREMENT.finditer(body)}),
        "magnitudes": sorted({_token(match.group(0)) for match in _MAGNITUDE.finditer(body)}),
        "emphasis": sorted({marker for marker in emphasis_markers if marker in body}),
        "boilerplate": sorted({marker for marker in BOILERPLATE_MARKERS if marker in (text or "")}),
        "citation_markers": len(_CITATION.findall(text or "")),
    }


def classify(signals: dict[str, Any]) -> str:
    """CONTENT_BEARING / MIXED / NON_CONTENT, from signals the caller can inspect.

    Publication apparatus is only allowed to make a unit non-content when the unit carries
    no independent content signal. A page that is mostly references but states a finding is
    MIXED, and MIXED is held to the content-bearing requirement -- the safe direction.
    """
    # Any concrete value at all makes a unit worth accounting for -- a page that states one
    # measurement among its references is MIXED, not apparatus. Measured on the real
    # material, no genuinely non-content unit states one, so the stricter bar costs nothing
    # and removes the case where a finding was filed as publication apparatus.
    content_signal = (bool(signals["thresholds"]) or bool(signals["measurements"])
                      or bool(signals["magnitudes"]) or len(signals["emphasis"]) >= 2)
    apparatus = bool(signals["boilerplate"]) or signals["citation_markers"] >= REFERENCE_LIST_CITATION_MARKERS
    if not apparatus:
        return "CONTENT_BEARING"
    return "MIXED" if content_signal else "NON_CONTENT"


def classify_units(chunks: list[dict[str, Any]], *,
                   overrides: dict[int, str] | None = None,
                   emphasis_markers: tuple[str, ...] = DEFAULT_EMPHASIS_MARKERS) -> list[dict[str, Any]]:
    """Classify every source unit, recording the inputs so a challenge can be answered."""
    overrides = overrides or {}
    units = []
    for chunk in chunks:
        page = chunk.get("page")
        signals = measure_unit(chunk.get("text", ""), emphasis_markers=emphasis_markers)
        computed = classify(signals)
        override = overrides.get(page)
        units.append({
            "page": page,
            "computed_classification": computed,
            "classification": override or computed,
            "classification_source": "REVIEWER_OVERRIDE" if override else "CODE_RULE",
            "rule_version": RULE_VERSION,
            "signals": signals,
            # The unit's own text, so the audit can account for its paragraphs without a second
            # source of truth for what was read.
            "text": chunk.get("text", ""),
        })
    return units


def terms(text: str) -> set[str]:
    """Term index for overlap scoring: ASCII words plus Chinese 2/3/4-grams.

    Defined here, in the lower module, because both the read audit and the application's
    relevance scoring need the same definition -- two copies would drift, and the audit would
    then be measuring coverage with different terms than the gate that rejects it.
    """
    tokens = {token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}", text)}
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        tokens.add(run)
        for size in (2, 3, 4):
            tokens.update(run[index:index + size] for index in range(len(run) - size + 1))
    return tokens


def segment_paragraphs(text: str) -> list[dict[str, Any]]:
    """Split a unit into paragraphs, keeping each one's position and length."""
    paragraphs: list[dict[str, Any]] = []
    for raw in (value.strip() for value in (text or "").splitlines()):
        if raw:
            paragraphs.append({"index": len(paragraphs), "chars": len(raw), "text": raw})
    return paragraphs


def paragraph_is_covered(paragraph: str, quotes: list[str]) -> bool:
    """True when an accepted quote represents this paragraph, not merely touches it."""
    paragraph_terms = terms(paragraph)
    if not paragraph_terms:
        return False
    normalised = _normalise(paragraph)
    for quote in quotes:
        probe = _normalise(quote)
        if not probe:
            continue
        if probe in normalised or normalised in probe:
            return True
        if len(terms(quote) & paragraph_terms) / len(paragraph_terms) >= PARAGRAPH_COVERAGE_RATIO:
            return True
    return False


def audit_read_receipts(*, units: list[dict[str, Any]], receipts: Any, claims: list[Any],
                        emitters: Any = None) -> dict[str, Any]:
    """Check that a reading accounted for every unit and every meaning-critical token.

    `receipts` is the reading's own per-unit statement; `claims` are the accepted candidates.
    Returns structured findings plus the counts an auditor needs to see, because a
    completeness rule that only says PASS is indistinguishable from one that does nothing.
    """
    issues: list[dict[str, Any]] = []
    classified = {unit["page"]: unit for unit in units}

    provided: dict[int, dict[str, Any]] = {}
    if not isinstance(receipts, list):
        issues.append({"code": "READ_RECEIPTS_MISSING", "message":
                       "A reading must account for every source unit; no unit receipts were returned"})
        receipts = []
    for item in receipts:
        if not isinstance(item, dict) or not isinstance(item.get("page"), int):
            issues.append({"code": "READ_RECEIPT_MALFORMED",
                           "message": f"Unit receipt is not an object with a page: {item!r}"})
            continue
        page = item["page"]
        if page in provided:
            issues.append({"code": "READ_RECEIPT_DUPLICATE", "page": page,
                           "message": "A source unit was accounted for more than once"})
            continue
        provided[page] = item

    by_page: dict[int, list[Any]] = {}
    for claim in claims:
        for ref in getattr(claim, "source_refs", []) or []:
            by_page.setdefault(ref.page, []).append(claim)

    stats = {"units": len(units), "accounted": 0, "declined": 0, "declined_content_bearing": 0,
             "tokens": 0, "tokens_covered": 0, "tokens_excluded": 0, "tokens_unaccounted": 0,
             "thresholds_unaccounted": 0,
             "paragraphs": 0, "paragraphs_covered": 0, "paragraphs_excluded": 0,
             "paragraphs_unaccounted": 0}

    for unit in units:
        page = unit["page"]
        receipt = provided.get(page)
        if receipt is None:
            issues.append({"code": "UNIT_NOT_ACCOUNTED", "page": page,
                           "message": f"Source unit {page} was never accounted for"})
            continue
        stats["accounted"] += 1
        status = receipt.get("status")
        page_claims = by_page.get(page, [])
        if status not in RECEIPT_STATUSES:
            issues.append({"code": "READ_RECEIPT_STATUS_UNKNOWN", "page": page,
                           "message": f"Unit {page} declares status={status!r}; "
                                      f"expected one of {list(RECEIPT_STATUSES)}"})
            continue

        if status == RECEIPT_DECLINED:
            stats["declined"] += 1
            reason = receipt.get("reason")
            if reason not in DECLINE_REASONS:
                issues.append({"code": "DECLINE_WITHOUT_ALLOWED_REASON", "page": page,
                               "message": f"Unit {page} is declined with reason={reason!r}; "
                                          f"expected one of {list(DECLINE_REASONS)}"})
            if unit["classification"] in ("CONTENT_BEARING", "MIXED"):
                stats["declined_content_bearing"] += 1
                issues.append({"code": "CONTENT_UNIT_DECLINED", "page": page,
                               "classification": unit["classification"],
                               "message": f"Unit {page} is classified {unit['classification']} by code "
                                          f"({_signal_summary(unit['signals'])}) but the reading declares it "
                                          "holds nothing quotable; a unit with content may not be declined"})
            if page_claims:
                issues.append({"code": "RECEIPT_CONTRADICTS_ITS_OWN_CANDIDATES", "page": page,
                               "message": f"Unit {page} is declined but carries "
                                          f"{len(page_claims)} accepted candidate(s)"})
        else:
            if not page_claims:
                issues.append({"code": "RECEIPT_WITHOUT_CANDIDATE", "page": page,
                               "message": f"Unit {page} is reported as read but produced no accepted "
                                          "candidate; a receipt is not evidence of reading"})

        excluded = {}
        for item in receipt.get("exclusions") or []:
            if not isinstance(item, dict):
                issues.append({"code": "EXCLUSION_MALFORMED", "page": page,
                               "message": f"Exclusion entry is not an object: {item!r}"})
                continue
            excluded[str(item.get("token", "")).strip()] = item.get("reason")

        covered_text = " ".join(
            _normalise(claim.source_quote or "") + " " + _normalise(claim.normalized_claim)
            for claim in page_claims)
        for kind, tokens in (("thresholds", unit["signals"]["thresholds"]),
                             ("measurements", unit["signals"]["measurements"]),
                             ("magnitudes", unit["signals"]["magnitudes"])):
            for token in tokens:
                stats["tokens"] += 1
                probe = _normalise(token)
                if probe and probe in covered_text:
                    stats["tokens_covered"] += 1
                    continue
                reason = excluded.get(token.strip())
                if reason is not None:
                    if kind == "thresholds":
                        stats["thresholds_unaccounted"] += 1
                        issues.append({"code": "THRESHOLD_MAY_NOT_BE_EXCLUDED", "page": page,
                                       "token": token,
                                       "message": f"Unit {page}: threshold {token!r} may not be excluded; "
                                                  "thresholds must be extracted and reviewable"})
                        continue
                    if reason not in EXCLUSION_REASONS:
                        issues.append({"code": "EXCLUSION_REASON_UNKNOWN", "page": page, "token": token,
                                       "message": f"Unit {page}: exclusion of {token!r} states "
                                                  f"reason={reason!r}; expected one of {list(EXCLUSION_REASONS)}"})
                        continue
                    stats["tokens_excluded"] += 1
                    continue
                stats["tokens_unaccounted"] += 1
                if kind == "thresholds":
                    stats["thresholds_unaccounted"] += 1
                issues.append({"code": "MEANING_TOKEN_NOT_ACCOUNTED", "page": page,
                               "token": token, "kind": kind,
                               "message": f"Unit {page}: {kind} value {token!r} is neither covered by an "
                                          "accepted candidate nor excluded with a reason"})

        # Paragraph-level accounting: a unit receipt answers "did this page yield anything"; this
        # answers "was each substantive paragraph of it dealt with" -- the question that would have
        # caught a whole treatment table going missing.
        paragraph_exclusions: dict[int, Any] = {}
        for item in receipt.get("paragraph_exclusions") or []:
            if not isinstance(item, dict):
                issues.append({"code": "PARAGRAPH_EXCLUSION_MALFORMED", "page": page,
                               "message": f"Paragraph exclusion entry is not an object: {item!r}"})
                continue
            try:
                paragraph_exclusions[int(item.get("paragraph", -1))] = item.get("reason")
            except (TypeError, ValueError):
                issues.append({"code": "PARAGRAPH_EXCLUSION_MALFORMED", "page": page,
                               "message": f"Paragraph exclusion names no paragraph index: {item!r}"})
        quotes = [str(claim.source_quote or "") for claim in page_claims]
        # A declined unit already states a reason for the page as a whole; demanding a receipt for
        # every paragraph of a reference list would be paperwork, not review.
        paragraphs_to_account = [] if status == RECEIPT_DECLINED else segment_paragraphs(unit.get("text") or "")
        for paragraph in paragraphs_to_account:
            if paragraph["chars"] < MIN_PARAGRAPH_CHARS:
                continue
            stats["paragraphs"] += 1
            if paragraph_is_covered(paragraph["text"], quotes):
                stats["paragraphs_covered"] += 1
                continue
            reason = paragraph_exclusions.get(paragraph["index"])
            if reason is not None:
                if reason not in PARAGRAPH_EXCLUSION_REASONS:
                    issues.append({"code": "PARAGRAPH_EXCLUSION_REASON_UNKNOWN", "page": page,
                                   "paragraph": paragraph["index"],
                                   "message": f"Unit {page} paragraph {paragraph['index']} excludes with "
                                              f"reason={reason!r}; expected one of "
                                              f"{list(PARAGRAPH_EXCLUSION_REASONS)}"})
                    continue
                stats["paragraphs_excluded"] += 1
                continue
            stats["paragraphs_unaccounted"] += 1
            issues.append({"code": "PARAGRAPH_NOT_ACCOUNTED", "page": page,
                           "paragraph": paragraph["index"], "chars": paragraph["chars"],
                           "excerpt": paragraph["text"][:60],
                           "message": f"Unit {page} paragraph {paragraph['index']} "
                                      f"({paragraph['chars']} chars) is neither represented by an accepted "
                                      f"quote nor excluded with a reason: {paragraph['text'][:60]!r}"})

    return {"status": "PASS" if not issues else "BLOCK", "rule_version": RULE_VERSION,
            "units": units, "issues": issues, "statistics": stats}


def _signal_summary(signals: dict[str, Any]) -> str:
    return (f"thresholds={len(signals['thresholds'])}, measurements={len(signals['measurements'])}, "
            f"magnitudes={len(signals['magnitudes'])}, emphasis={len(signals['emphasis'])}")


def _normalise(text: str) -> str:
    return re.sub(r"\s+", "", text or "")
