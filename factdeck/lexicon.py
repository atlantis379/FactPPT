"""Critical tokens and authored-text lint, independent of any one subject.

Critical tokens are the parts of a statement that change its meaning when they
change: numbers with their comparison operator and unit, technical Latin tokens
(IL-5, FEV1, HbA1c, Q4W), Chinese numerals with a measure word, and the project's
own terms (entity names declared with the fact store and verified in the sources).
The defaults live in config/factdeck_lexicon.json and contain no disease-specific
vocabulary.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEXICON = ROOT / "config" / "factdeck_lexicon.json"


@lru_cache(maxsize=1)
def lexicon() -> dict:
    return json.loads(LEXICON.read_text(encoding="utf-8"))


def canon(text: str) -> str:
    """Width/whitespace-insensitive form used for matching. Never used for display."""
    t = text.translate(str.maketrans({"＜": "<", "＞": ">", "‑": "-", "–": "-", "—": "-", "‐": "-", "～": "~",
                                      "µ": "μ", "　": " ", " ": " ", "\t": " ", "（": "(", "）": ")",
                                      "％": "%", "：": ":", "，": ",", "；": ";", "≧": "≥", "≦": "≤"}))
    t = re.sub(r"[０-９]", lambda m: chr(ord(m.group(0)) - 0xFEE0), t)
    return re.sub(r"\s+", "", t)


_OP = r"[≥≤<>]|>=|<="
_NUM = r"\d+(?:[.,]\d+)*"
_CN_NUM = re.compile(r"[零一二三四五六七八九十两百千万几半]+(?:个月|小时|分钟|[种个项条次倍年月周天成组类期例针剂支岁分级])")
_LATIN = re.compile(r"[A-Za-zα-ωΑ-Ω][A-Za-z0-9α-ωΑ-Ω]*(?:[-/][A-Za-z0-9α-ω]+)*")


@lru_cache(maxsize=1)
def _num_re() -> re.Pattern:
    units = sorted(lexicon()["units"], key=len, reverse=True)
    unit = "(?:" + "|".join(re.escape(u) for u in units) + ")?"
    return re.compile(rf"({_OP})?({_NUM})(?:([-~])({_NUM}))?({unit})")


def critical_tokens(text: str, terms: tuple[str, ...] | list[str] = ()) -> set[str]:
    t = canon(text)
    t = re.sub(r"(\d)%([-~])(\d)", r"\1\2\3", t)          # 44%~48% == 44~48%
    tokens: set[str] = set()
    for m in _num_re().finditer(t):
        op, a, sep, b, unit = m.group(1) or "", m.group(2).replace(",", ""), m.group(3), m.group(4), m.group(5) or ""
        op = {">=": "≥", "<=": "≤"}.get(op, op)
        tokens.add(f"{op}{a}" + (f"-{b.replace(',', '')}" if b else "") + unit.lower())
    for m in _CN_NUM.finditer(t):
        tokens.add(m.group(0))
    for m in _LATIN.finditer(t):
        w = m.group(0)
        if re.search(r"\d", w) or sum(c.isupper() for c in w) >= 2 or re.search(r"[α-ωΑ-Ω]", w):
            tokens.add(w.replace("-", "").upper())
    for term in terms:
        if term and canon(term) in t:
            tokens.add("term:" + canon(term))
    return tokens


def split_fragments(display: str) -> list[str]:
    return [p for p in re.split(r"[,;、…/():\s·]+|\.{3}", canon(display)) if p]


def extractive(display: str, quote: str) -> tuple[bool, str]:
    """Is `display` made only of pieces of `quote`, in order?

    Returns (ok, dropped_text). Dropping a negation or qualifier ("不", "仅", "以上")
    changes the meaning even though every remaining piece is verbatim, so callers
    treat a blocker inside the dropped text as a rewrite.
    """
    q = canon(quote)
    pos, dropped = 0, []
    for piece in split_fragments(display):
        i = q.find(piece, pos)
        if i < 0:
            return False, ""
        dropped.append(q[pos:i])
        pos = i + len(piece)
    dropped.append(q[pos:])
    return True, "".join(dropped)


def dropped_blockers(dropped: str) -> list[str]:
    stripped = re.sub(r"[,;、:()\[\]【】“”\"'。.!！?？\-~]", "", dropped)
    return [w for w in lexicon()["dropped_text_blockers"] if w in stripped]


def lint_text(text: str, glossary: list[str] | tuple[str, ...] = (), terms: list[str] | tuple[str, ...] = ()) -> list[str]:
    """Problems with model-authored text (titles, leads, labels, column headers).

    Authored text may organise and name things but may not state anything medical:
    no numbers, operators, technical tokens, project entity names, drug-like names,
    or evaluative/directional wording. Glossary terms (each backed by a fact) are
    removed before the check.
    """
    t = text
    for term in sorted(glossary, key=len, reverse=True):
        t = t.replace(term, "")
    problems = []
    toks = {x for x in critical_tokens(t, terms)}
    if toks:
        problems.append("作者文字含关键项：" + "、".join(sorted(x.replace("term:", "") for x in toks)))
    if re.search(r"[≥≤<>＜＞%％‰]", t):
        problems.append("作者文字含比较符号或百分号")
    lx = lexicon()
    for suffix in lx["authored_forbidden_suffixes"]:
        m = re.search(r"[一-鿿]{1,6}" + re.escape(suffix), t)
        if m:
            problems.append("作者文字含疑似药物/分子名称：" + m.group(0))
    for w in lx["authored_forbidden_words"]:
        if w in t:
            problems.append("作者文字含评价或方向性措辞：" + w)
    return problems
