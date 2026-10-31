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


def locate(text: str, quote: str) -> tuple[int, int] | None:
    """Where `quote` occurs in `text` under `canon` matching: (start, end) offsets into the raw text, first occurrence."""
    chars, where = [], []
    for i, ch in enumerate(text):
        c = canon(ch)
        if c:
            chars.append(c)
            where.append(i)
    q = canon(quote)
    k = "".join(chars).find(q) if q else -1
    if k < 0:
        return None
    return where[k], where[k + len(q) - 1] + 1


def numeric_spacing(text: str) -> str:
    """Normalise typography without joining separate numeric values."""
    return canon(re.sub(r"(?<=\d)\s+(?=\d)", "\u241f", text))


def verbatim_span(text: str, quote: str) -> tuple[int, int] | None:
    """Locate a quote, retaining whitespace that separates digits on either side."""
    start = 0
    while start < len(text):
        at = locate(text[start:], quote)
        if at is None:
            return None
        a, b = start + at[0], start + at[1]
        if numeric_spacing(text[a:b]) == numeric_spacing(quote):
            return a, b
        start = a + 1
    return None


_OP =r"[≥≤<>]|>=|<="
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


_CLAUSE_BREAK = re.compile(r"[，,；;。！？!?：:、\n（）()\[\]【】]")
_RANGE_JOIN = re.compile(r"^[~\-－—–至到]$")
# A bare integer in front of these is a classification number (2型, 1级), not a quantity.
_CLASSIFIER = "型级线"
_YEAR = re.compile(r"^(19|20)\d{2}$")


def _token_of(m: re.Match) -> str:
    """The same normalised form ``critical_tokens`` produces, for one match of ``_num_re``."""
    op, a, sep, b, unit = m.group(1) or "", m.group(2).replace(",", ""), m.group(3), m.group(4), m.group(5) or ""
    op = {">=": "≥", "<=": "≤"}.get(op, op)
    return f"{op}{a}" + (f"-{b.replace(',', '')}" if b else "") + unit.lower()


def number_spans(text: str) -> list[dict]:
    """Every quantity in `text` with the smallest complete clause around it, verbatim, plus its offsets.

    A page needs one number to carry its visual weight; the clause is what makes that number readable on its own
    (``70%`` alone means nothing, ``其中约70%为2型炎症`` does).  Nothing here is authored: the clause is a slice of the
    source sentence, so a caller can show the number and still trace it to one place in the document.

    Adjacent values joined by a range mark (``5%~10%``) are one span, not two.  Classification numbers (``2型``),
    years and anything the cut already flagged as a chart dump are not quantities and are left out.
    """
    hits = []
    for m in _num_re().finditer(text):
        token = _token_of(m)
        plain = re.fullmatch(r"(\d+)([^\d]*)", token)
        if plain and _YEAR.match(plain.group(1)):                       # 2024年 is a date, not a measure
            continue
        if plain and not plain.group(2) and text[m.end():m.end() + 1] in _CLASSIFIER:
            continue                                                    # 2型炎症 / 1级推荐
        hits.append({"token": token, "m": m})
    merged = []
    for h in hits:                                                      # 5% + ~ + 10% → one span
        if merged and _RANGE_JOIN.match(text[merged[-1]["end_m"].end():h["m"].start()].strip() or ""):
            prev = merged[-1]
            a, b = prev["m"].group(2).replace(",", ""), h["m"].group(2).replace(",", "")
            unit = (h["m"].group(5) or prev["m"].group(5) or "").lower()
            prev["token"], prev["end_m"] = f"{a}-{b}{unit}", h["m"]
            continue
        merged.append({**h, "end_m": h["m"]})
    out, seen = [], set()
    for item in merged:
        m, last = item["m"], item["end_m"]
        start = 0
        for br in _CLAUSE_BREAK.finditer(text, 0, m.start()):
            start = br.end()
        nxt = _CLAUSE_BREAK.search(text, last.end())
        end = nxt.start() if nxt else len(text)
        lead = len(text[start:end]) - len(text[start:end].lstrip())
        clause = text[start:end].strip()
        if not clause or clause in seen:                                # one anchor per clause
            continue
        seen.add(clause)
        out.append({"token": item["token"], "clause": clause, "start": start + lead, "end": end})
    return out


def split_fragments(display: str) -> list[str]:
    return [p for p in re.split(r"[,;、…/():\s·]+|\.{3}", canon(display)) if p]


def extractive(display: str, quote: str) -> tuple[bool, str]:
    """Is `display` made only of pieces of `quote`, in order?

    Returns (ok, dropped_text). Dropping a negation or qualifier ("不", "仅", "以上")
    changes the meaning even though every remaining piece is verbatim, so callers
    treat a blocker inside the dropped text as a rewrite.
    """
    if numeric_spacing(display) == numeric_spacing(quote):
        return True, ""
    # Keep digit separators while locating display fragments as well as whole quotes.
    q = numeric_spacing(quote)
    pos, dropped = 0, []
    for piece in split_fragments(re.sub(r"(?<=\d)\s+(?=\d)", "\u241f", display)):
        i = q.find(piece, pos)
        if i < 0:
            return False, ""
        dropped.append(q[pos:i])
        pos = i + len(piece)
    dropped.append(q[pos:])
    return True, "".join(dropped)


def scope_labels(display: str, quote: str) -> list[str]:
    """Labels the display cuts off right before text it keeps ("中国：2017" shown as "2017" drops the label "中国").

    Such a label sets the scope of what follows it; the excerpt stays correct only when the page states the label
    elsewhere (once, for the whole group). A dropped entry that is not followed by kept text is not a scope label."""
    q = canon(quote)
    pos, labels = 0, []
    for piece in split_fragments(display):
        i = q.find(piece, pos)
        if i < 0:
            return []
        m = re.search(r"([^\s:;,。、()\[\]0-9]{1,16})\s*:\s*$", q[pos:i])
        if m:
            labels.append(m.group(1))
        pos = i + len(piece)
    return labels


_SENT_END = re.compile(r"[。！？；!?;•➢►▶❖]|(?<=[a-z0-9)])\.(?=\s*[A-Z(])")
_CLAUSE = re.compile(r"[、:：()（）\[\]【】]|(?<!\d)[,，]|[,，](?!\d)")     # a comma inside a number is not a clause break
_CITE = re.compile(r"[(\[]\d{1,4}(?:[-–,，]\d{1,4})*[)\]]")                 # reference markers "(13)", "[14,15]", "(118-126)"
# bibliography glued into a sentence by the text layer: a numbered GB/T 7714 entry "2.作者.题名[J].刊名,2025,48(3):208-248.",
# the volume:pages tail of one "16:611-624.", a journal issue header "2026年3月,第7卷,第1期" — citations, not context
_BIBLIO = re.compile(r"(?:(?<![^\s.。:;➢•])\d{1,3}\.[^。\[\]]{2,160}?\[[A-Z](?:/OL)?\]\.?[^。]{0,80}?\d{4}\s*,\s*\d+\s*(?:\(\s*\d+\s*\))?"
                     r"\s*:\s*\d+(?:\s*[-–]\s*\d+)?\.?"
                     r"|^\s*\d{1,4}\s*(?:\(\s*\d+\s*\))?\s*:\s*\d+\s*[-–]\s*\d+\s*\."
                     r"|\d{4}年\d{1,2}月\s*,?\s*第\d+卷\s*,?\s*第\d+期)")
_PAGE_NO = re.compile(r"\s\d{1,4}\s*$")                                       # a running header or footer ends with its page number
_ENUM = re.compile(r"(?<![(\d.])\d{1,2}\)")                                   # list numbering "1)" "2)"
_FIG_REF = re.compile(r"(?:如|见|参见)?(?:图|表|Figure|Table)[\dA-Z]+(?:\.\d+)*(?:所示|中)?")   # "如图2.5所示": a pointer, not context
_LIST_START = re.compile(r"\s*(?:[•·▪●○◆➢►▶❖\-–]|\d{1,2}[.、)）])")
SHORT_LINE = 15              # a line this short without end punctuation is a heading or a label, not a wrapped sentence


def sentence_of(text: str, quote: str) -> tuple[str, int, int, int] | None:
    """The sentence of `text` that holds `quote`: (canon sentence, raw start in `text`, quote start, quote end in the
    canon sentence). Sentences end at end punctuation, bullets and list items, and after a short line (a heading or
    label); a long line ending without punctuation is wrapping. Multi-sentence quotes take all their sentences."""
    at = locate(text, quote)
    if not at:
        return None
    ends = {m.end() for m in _SENT_END.finditer(text)}
    pos = 0
    for line in text.split("\n"):
        nxt = pos + len(line) + 1
        if (len(line.strip()) <= SHORT_LINE and not _SENT_END.search(line[-1:] or "")) or _LIST_START.match(text[nxt:nxt + 4]) \
                or _PAGE_NO.search(line):
            ends.add(min(nxt, len(text)))
        pos = nxt
    start = max([e for e in ends if e <= at[0]], default=0)
    end = min([e for e in ends if e >= at[1]], default=len(text))
    s = canon(text[start:end])
    q0 = len(canon(text[start:at[0]]))
    return s, start, q0, q0 + len(canon(quote))


def shown_spans(sentence: str, q0: int, q1: int, display: str) -> list[list[int]]:
    """Where the shown text sits in the canon sentence: the quote, or the in-order pieces of its excerpt."""
    if not display:
        return [[q0, q1]]
    spans, pos = [], q0
    for piece in split_fragments(display):
        i = sentence.find(piece, pos, q1)
        if i < 0:
            return [[q0, q1]]
        spans.append([i, i + len(piece)])
        pos = i + len(piece)
    return spans


def _bears_context(clause: str, trailing: bool) -> bool:
    lx = lexicon()
    if trailing:
        return any(canon(w) in clause for w in lx["context_trailing"])
    return bool(re.search(r"\d", clause) or _CN_NUM.search(clause)) or any(canon(w) in clause for w in lx["context_markers"])


def missing_context(sentence: str, covered: list[list[int]]) -> list[str]:
    """Clauses of a sentence left off the page that set the context of what is shown: before or between the shown
    pieces, a clause with a number or a study, population, time, place, comparator or condition word; after them, a
    qualifying clause ("特别是…", "相较于…"). A further statement after the shown text is not context."""
    if not covered:
        return []
    spans = sorted(covered)
    merged = [list(spans[0])]
    for a, b in spans[1:]:
        if a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    gaps = [(0, merged[0][0], False)] + [(merged[i][1], merged[i + 1][0], False) for i in range(len(merged) - 1)] \
        + [(merged[-1][1], len(sentence), True)]
    plain = sentence
    for pattern in (_BIBLIO, _CITE, _ENUM):
        plain = pattern.sub(lambda m: "," * len(m.group(0)), plain)       # same length: covered offsets stay valid
    out = []
    for a, b, trailing in gaps:
        for clause in _CLAUSE.split(plain[a:b]):
            clause = clause.strip("。！？；!?;•.\"'“”‘’-–—~")
            if clause and not _FIG_REF.fullmatch(clause) and _bears_context(clause, trailing):
                out.append(clause)
    return out


def context_stated(clause: str, page_text: list[str]) -> bool:
    """A missing context clause counts as stated when the page shows it, with or without a leading connective."""
    # PDF text layers occasionally insert ASCII control separators inside a phrase (for example,
    # between a list marker and its label). They are extraction artifacts, not visible wording.
    clause = re.sub(r"[\x00-\x1f\x7f]", "", clause)
    page_text = [re.sub(r"[\x00-\x1f\x7f]", "", text) for text in page_text]
    core = clause
    for w in sorted(lexicon()["context_signals"]["leading_connectives"], key=len, reverse=True):
        if core.startswith(canon(w)):
            core = core[len(canon(w)):]
            break
    return any(clause in t or (core and core in t) for t in page_text)


def dropped_blockers(dropped: str) -> list[str]:
    # Reference markers are bibliographic metadata, not dropped clinical qualifiers.
    dropped = _CITE.sub("", dropped)
    stripped = re.sub(r"[,;、:()\[\]【】“”\"'。.!！?？\-~]", "", dropped)
    words = dict.fromkeys(lexicon()["dropped_text_blockers"] + lexicon()["claim_qualifiers"])
    found = [w for w in words if w in stripped]
    found += sorted(critical_tokens(dropped))
    # English words require boundaries: 'not' in 'notation' is not a negation.
    found += re.findall(r"\b(?:not|no|never|only|except|unless|may|might|some|most|approximately|about|at least|at most)\b", dropped, re.I)
    return list(dict.fromkeys(found))


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
