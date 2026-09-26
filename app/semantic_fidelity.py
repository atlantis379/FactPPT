"""Conservative, domain-independent guards for source-to-claim paraphrases.

These checks identify contradictions that token overlap cannot detect. They do not
claim to prove entailment: an unrecognized paraphrase still needs independent
semantic or human review before it can be called source-supported.
"""
from __future__ import annotations

import re


_STANCE = {
    "show": (
        r"未显示|没有显示|不显示|并未显示|未发现|没有发现|未观察到|没有观察到|"
        r"未表明|不表明|未证实|没有证实|不支持|未支持|"
        r"\b(?:(?:did|does|do) not (?:show|find|observe|demonstrate|support)|"
        r"no evidence of|not shown|not observed|failed to show)\b",
        r"显示|发现|观察到|表明|证实|支持|"
        r"\b(?:shows?|showed|found|observed|demonstrates?|supports?)\b",
    ),
    "direction": (
        r"下降|降低|减少|低于|缩小|减弱|"
        r"\b(?:decreas(?:e|ed|es)|reduc(?:e|ed|es)|lower than|fell)\b",
        r"上升|提高|增加|高于|扩大|增强|"
        r"\b(?:increas(?:e|ed|es)|rais(?:e|ed|es)|higher than|rose)\b",
    ),
}

_NARROW_SCOPE = re.compile(r"仅|只限|仅限|部分|少数|试点|样本|\b(?:only|some|pilot|sample)\b", re.IGNORECASE)
_BROAD_SCOPE = re.compile(r"全部|所有|任何|普遍|全体|\b(?:all|every|always|universal)\b", re.IGNORECASE)
_UNCERTAIN = re.compile(r"可能|或许|初步|提示|相关|倾向|估计|\b(?:may|might|preliminary|associated|estimated)\b", re.IGNORECASE)
_CERTAIN = re.compile(r"证明|证实|确定|必然|一定|确保|导致|\b(?:proves?|certain|always|causes?|guarantees?)\b", re.IGNORECASE)
_CONDITIONS = re.compile(
    r"如果[^，。；]{1,40}|若[^，。；]{1,40}|在[^，。；]{2,40}(?:条件下|情况下|期间|人群中|客户中)|"
    r"截至\d{4}[^，。；]{0,20}|\b(?:if|provided that|among|as of)\b[^,.\n]{2,60}",
    re.IGNORECASE,
)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()


def _signal(text: str, group: str) -> str | None:
    """Return a polarity, MIXED for conflicting clauses, or None if absent."""
    negative, positive = _STANCE[group]
    is_negative = bool(re.search(negative, text, re.IGNORECASE))
    # Remove recognized negative phrases before checking their embedded verbs.
    without_negative = re.sub(negative, "", text, flags=re.IGNORECASE)
    is_positive = bool(re.search(positive, without_negative, re.IGNORECASE))
    if is_negative and is_positive:
        return "mixed"
    if not is_negative and not is_positive:
        return None
    return "negative" if is_negative else "positive"


def contradiction_signals(source: str, statement: str) -> list[str]:
    """Find clear stance/direction reversals; empty does not mean entailed."""
    issues = []
    for group in _STANCE:
        left = _signal(source, group)
        right = _signal(statement, group)
        if left in {"negative", "positive"} and right in {"negative", "positive"} and left != right:
            issues.append(f"{group.upper()}_REVERSAL")
    if _NARROW_SCOPE.search(source) and _BROAD_SCOPE.search(statement) and not _BROAD_SCOPE.search(source):
        issues.append("SCOPE_EXPANSION")
    if _UNCERTAIN.search(source) and _CERTAIN.search(statement) and not _CERTAIN.search(source):
        issues.append("STRENGTH_UPGRADE")
    return issues


def missing_source_signals(source: str, statement: str) -> list[str]:
    """Catch a source qualifier that disappeared without an explicit reversal."""
    issues = []
    for group in _STANCE:
        left = _signal(source, group)
        right = _signal(statement, group)
        if (left is not None and right is None) or (left == "mixed" and right != "mixed"):
            issues.append(f"{group.upper()}_OMITTED")
    if _NARROW_SCOPE.search(source) and not _NARROW_SCOPE.search(statement):
        issues.append("SCOPE_QUALIFIER_OMITTED")
    if _UNCERTAIN.search(source) and not _UNCERTAIN.search(statement):
        issues.append("UNCERTAINTY_OMITTED")
    conditions = [_compact(match.group()) for match in _CONDITIONS.finditer(source)]
    if conditions and any(condition not in _compact(statement) for condition in conditions):
        issues.append("CONDITION_OMITTED")
    return issues
