"""Claims cut by code: every unit split into verbatim sentences, each attached to the topic the model put its unit under.

The model reads the whole material and names its topics (``semantic_map.v1`` nodes, each with the units it rests on);
code cannot summarise, but it can cut and attach without changing a character:

- a unit is split at sentence terminators and list markers; a table cell or label stays whole;
- each piece keeps its unit id and offsets, so ``unit.text[start:end] == quote``;
- numbers, qualifiers and citation marks are read off the quote (``factdeck.claims``);
- section headings ("1.1 临床缓解的概念"), journal running headers and bibliography entries glued into body text are cut
  off as their own pieces;
- a run of six or more bare numbers (chart values flattened by the PDF text layer) is cut off from the sentence it is
  glued to, so the sentence survives on its own;
- a piece is tagged ``reference`` (reference page, a bibliography entry or a running header), ``heading``,
  ``boilerplate`` (the same text on three or more pages of one source: watermarks, footers — unless the author marked it
  as a title, which repeats on purpose), ``data`` (a bare number run), ``gloss`` (an abbreviation's expansion
  "RR：相对危险比；"), ``cell`` (one cell of a table: read with its row and column headers, see ``table_context``), ``header`` (a cell of
  a table's first row),
  ``label`` (a short fragment with no sentence) or ``sentence``;
- the topic is the map node whose ``unit_hints`` contain the unit; a unit no node names stays unattached.

Domain-neutral: punctuation and layout only. Nothing here decides what a sentence means.
"""
from __future__ import annotations

import re
from collections import defaultdict

from .claims import cites, qualifiers
from .lexicon import _BIBLIO, canon, critical_tokens
from .source_coverage import segments

SCHEMA = "auto_claims.v4"
SEGMENTER = "sentence.v3"           # bracket-aware: a terminator inside soon-closing brackets does not end the sentence
LABEL_CHARS = 8              # a piece this short (canon characters) without a terminator is a label, not a sentence
BOILERPLATE_PAGES = 3        # the same piece on this many pages of one source is a watermark or a footer
_BULLET = re.compile(r"(?:^|(?<=\s))[•·▪●○◆➢►▶❖](?=\s*\S)")
_BIB_WORDS = re.compile(r"\bet al\b|\bDOI\b|doi\.org|\[J\]|\d{4}\s*;\s*\d+\s*\(\s*\d+\s*\)\s*:\s*\d+", re.I)
_END = re.compile(r"[。！？；!?;]\s*$")
# a journal running header "（Biomedical Transformation ） ，2026 年 3 月，第 7 卷，第 1 期", spaced or not
_HEADER = re.compile(r"(?:[（(]\s*[A-Za-z][A-Za-z .&-]{2,80}[）)]\s*[，,]?\s*)?"
                     r"\d{4}\s*年\s*\d{1,2}\s*月\s*[，,]?\s*第\s*\d+\s*卷\s*[，,]?\s*第\s*\d+\s*期")
# numbered section headings at the start of a piece: "1 临床缓解的定义与评估标准", "1.1 临床缓解的概念"
_HEADING = re.compile(r"\d{1,2}(?:\.\d{1,2})*\s+[^\s。！？；，,]{2,30}(?=\s)")
_NUM = r"[-+]?\d+(?:\.\d+)?%?"
_NUMRUN = re.compile(rf"(?:(?<=\s)|^){_NUM}(?:\s+{_NUM}){{5,}}(?=\s|$)")
# "RR：相对危险比；" "FF，氟替卡松；" "OCS=口服糖皮质激素": an abbreviation and its expansion
_GLOSS = re.compile(r"^[•·*]?\s*[A-Za-z][A-Za-z0-9₀-₉⁰-⁹\-/·αβγ]{0,15}\s*[：:，,=]\s*[^。；;：:]{1,40}[；;。]?$")
# a numbered reference line "1. Global Initiative for Asthma. …, 2025." / "2. Richard Beasley, et al. …"
_REFLINE = re.compile(r"\s*\d{1,2}\s*\.\s*\S.*(?:\bet al\b|\[J\]|\d{4}\s*[;.,:)]|\d{4}\s*$|Global Initiative|Guideline|Strategy)")
# the volume(issue)pages tail of a citation cut off at a ";" — "199(12)1471 -1477", "100(6) 2171 -80"
_BIBTAIL = re.compile(r"\d{1,4}\s*\(\s*\d{1,3}\s*\)\s*:?\s*\d{1,5}\s*[-–]\s*\d{1,5}\.?")
_CELL = re.compile(r"^(?P<table>.+:t\d+)r(?P<r>\d+)c(?P<c>\d+)$")


def _trim(text: str, s: int, e: int) -> tuple[int, int]:
    while s < e and text[s].isspace():
        s += 1
    while e > s and text[e - 1].isspace():
        e -= 1
    return s, e


def _pieces(text: str) -> list[tuple[int, int, str]]:
    """Sentence pieces of a unit as (start, end, hint), whitespace-trimmed. List markers start a new piece; running
    headers and bibliography entries become ``reference`` pieces; leading numbered headings become ``heading``."""
    cuts = []
    for a, b in segments(text, SEGMENTER):
        starts = [a] + [m.start() for m in _BULLET.finditer(text, a, b) if m.start() > a]
        for i, s0 in enumerate(starts):
            e0 = starts[i + 1] if i + 1 < len(starts) else b
            marks = sorted([(m.start(), m.end()) for m in _HEADER.finditer(text, s0, e0)]
                           + [(m.start(), m.end()) for m in _BIBLIO.finditer(text, s0, e0)])
            at = s0
            for ms, me in marks:
                if ms < at:
                    continue
                cuts.append((at, ms, ""))
                cuts.append((ms, me, "reference"))
                at = me
            cuts.append((at, e0, ""))
    lined = []
    for s, e, hint in cuts:                      # reference lines printed under a sentence are references, not the sentence
        lines = [(m.start(), m.end()) for m in re.finditer(r"[^\n]+", text[s:e])] if not hint and "\n" in text[s:e] else []
        refs = [_REFLINE.match(text, s + a, s + b) is not None for a, b in lines]
        if not any(refs):
            lined.append((s, e, hint))
            continue
        at, cur = s, refs[0]
        for (a, b), ref in zip(lines, refs):
            if ref != cur:
                lined.append((at, s + a, "reference" if cur else ""))
                at, cur = s + a, ref
        lined.append((at, e, "reference" if cur else ""))
    cuts = lined
    split = []
    for s, e, hint in cuts:                      # a flattened chart's number run is not part of the sentence beside it
        at = s
        for m in ([] if hint else _NUMRUN.finditer(text, s, e)):
            split += [(at, m.start(), ""), (m.start(), m.end(), "data")]
            at = m.end()
        split.append((at, e, hint))
    out = []
    for s, e, hint in split:
        s, e = _trim(text, s, e)
        if not hint and (m := _BIBTAIL.match(text, s, e)):
            out.append((s, m.end(), "reference"))
            s, e = _trim(text, m.end(), e)
        while not hint and (m := _HEADING.match(text, s, e)) and m.end() < e:
            out.append((s, m.end(), "heading"))
            s, e = _trim(text, m.end(), e)
        if s < e:
            out.append((s, e, hint))
    return out


def _kind(quote: str, page_class: str, repeated: bool, hint: str, titled: bool, unit_id: str = "") -> str:
    if hint:
        return hint
    if page_class == "REFERENCE" or _BIBLIO.search(quote) or _BIB_WORDS.search(quote):
        return "reference"
    if repeated and not titled:
        return "boilerplate"
    if _GLOSS.match(quote.strip()):
        return "gloss"
    if (m := _CELL.match(unit_id)):
        return "header" if m["r"] == "1" else "cell"          # a table's first row names its columns
    if len(canon(quote)) < LABEL_CHARS and not _END.search(quote):
        return "label"
    return "sentence"


def row_key(unit_id: str) -> str | None:
    """The table row a cell unit belongs to ("S01:s15:t1r2"), or None for a unit that is not a table cell."""
    m = _CELL.match(unit_id)
    return f"{m['table']}r{m['r']}" if m else None


def table_context(units: list[dict]) -> dict[str, str]:
    """Unit id → where a table cell or chart transcription sits, so a bare value can be read: the cell's row header
    (first column) and column header (first row), or the reader's location note for a transcribed chart cell."""
    by_id = {u["id"]: u for u in units}
    out = {}
    for u in units:
        m = _CELL.match(u["id"])
        if m:
            row = by_id.get(f"{m['table']}r{m['r']}c1")
            col = by_id.get(f"{m['table']}r1c{m['c']}")
            parts = ([f"行：{' '.join(row['text'].split())[:40]}"] if row and m["c"] != "1" else []) + \
                    ([f"列：{' '.join(col['text'].split())[:40]}"] if col and m["r"] != "1" else [])
            if parts:
                out[u["id"]] = "｜".join(parts)
        elif u.get("method") == "visual_transcription" and u.get("location"):
            out[u["id"]] = u["location"][:80]
    return out


def cut(units: list[dict], page_class: dict[str, str], topic_of: dict[str, str]) -> list[dict]:
    """Every unit's verbatim pieces as claims, in unit order."""
    raw = []
    for u in units:
        for a, b, hint in _pieces(u["text"]):
            raw.append((u, a, b, u["text"][a:b], hint))
    pages_of = defaultdict(set)
    for u, _, _, q, _ in raw:
        pages_of[(u["source_id"], canon(q))].add(u["page_id"])
    out, n = [], defaultdict(int)
    for u, a, b, q, hint in raw:
        n[u["id"]] += 1
        repeated = len(pages_of[(u["source_id"], canon(q))]) >= BOILERPLATE_PAGES
        titled = bool((u.get("signals") or {}).get("title"))
        c = {"id": f"{u['id']}~{n[u['id']]}", "unit_id": u["id"], "page_id": u["page_id"], "source_id": u["source_id"],
             "start": a, "end": b, "quote": q, "kind": _kind(q, page_class.get(u["page_id"], ""), repeated, hint, titled, u["id"]),
             "topic": topic_of.get(u["id"])}
        for k, v in (("numbers", sorted(critical_tokens(q))), ("qualifiers", qualifiers(q)), ("cites", cites(q))):
            if v:
                c[k] = v
        if u.get("needs_confirmation"):
            c["needs_confirmation"] = True
        out.append(c)
    return out


def draft(semantic_map: dict, claims: list[dict]) -> dict:
    """Topics in teaching order (mainline first, as the map orders them), each with its sentences; the rest listed."""
    by_topic = defaultdict(list)
    for c in claims:
        by_topic[c["topic"]].append(c)
    nodes = semantic_map["nodes"]
    order = [n for n in nodes if n["mainline"]] + [n for n in nodes if not n["mainline"]]
    topics = []
    for n in order:
        cs = by_topic.get(n["id"], [])
        topics.append({"id": n["id"], "title": n["title"], "role": n["role"], "thesis": n["thesis"], "mainline": n["mainline"],
                       "claims": [c["id"] for c in cs if c["kind"] == "sentence"],
                       "labels": [c["id"] for c in cs if c["kind"] == "label"],
                       "set_aside": {k: sum(1 for c in cs if c["kind"] == k) for k in ("reference", "boilerplate") if any(c["kind"] == k for c in cs)}})
    return {"schema_version": SCHEMA, "one_liner": semantic_map["one_liner"], "edges": semantic_map.get("edges") or [],
            "topics": topics, "unattached": [c["id"] for c in by_topic.get(None, []) if c["kind"] in ("sentence", "label")]}


def verify(claims: list[dict], units: dict[str, dict]) -> list[str]:
    """Every claim is its unit's text at its offsets — the property the rest of the pipeline relies on."""
    return [c["id"] for c in claims if units[c["unit_id"]]["text"][c["start"]:c["end"]] != c["quote"]]
