"""Candidate relations read from the originals' own structure.

Each candidate points at source units and says what it rests on (`basis`): a diagram's arrows, a table's rows and
columns, numbered steps, or a connective phrase from config/factdeck_lexicon.json. Candidates are proposals for the
summary author; nothing is accepted because a candidate exists.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from .lexicon import lexicon

RELATION_TYPES = ("sequence", "branch", "any_of", "all_of", "compare", "matrix", "evidence", "definition")
CUE_CONTEXT = 24              # characters of context kept on each side of a connective
_CELL = re.compile(r":t(\d+)r(\d+)c(\d+)$")
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def _rid(kind: str, basis: str, unit_ids: list[str]) -> str:
    return "R" + hashlib.sha1("|".join([kind, basis, *unit_ids]).encode("utf-8")).hexdigest()[:10]


def _cand(kind: str, basis: str, unit_ids: list[str], **extra) -> dict:
    return {"id": _rid(kind, basis, unit_ids), "type": kind, "basis": basis, "unit_ids": unit_ids, **extra}


def _step_no(line: str, seps: tuple[str, ...]) -> int | None:
    line = line.strip()
    if line[:1] and line[0] in _CIRCLED:
        return _CIRCLED.index(line[0]) + 1
    m = re.match(r"(\d{1,2})\s*(.)", line)
    if m and m.group(2) in seps:
        return int(m.group(1))
    return None


def _run(numbers: list[int]) -> bool:
    """At least two steps counting up from 1 without gaps."""
    return len(numbers) >= 2 and numbers == list(range(1, len(numbers) + 1))


def candidates(units: list[dict]) -> list[dict]:
    lex = lexicon()
    seps = tuple(lex.get("numbered_separators", []))
    cues = {k: v for k, v in (lex.get("relation_connectives") or {}).items() if k in RELATION_TYPES}
    out: list[dict] = []
    by_page: dict[str, list[dict]] = defaultdict(list)
    for u in units:
        by_page[u["page_id"]].append(u)
    for page_units in by_page.values():
        # diagram arrows: a chain is a sequence; labelled arrows or a box with two ways out make a branch
        arrows = [u for u in page_units if u.get("arrow")]
        if arrows:
            outs = defaultdict(int)
            for u in arrows:
                outs[u["arrow"]["from"]] += 1
            branch = any(u["arrow"].get("label") for u in arrows) or max(outs.values()) >= 2
            out.append(_cand("branch" if branch else "sequence", "arrow", [u["id"] for u in arrows]))
        # tables: rows × columns
        tables: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
        for u in page_units:
            m = _CELL.search(u["id"])
            if m:
                tables[m.group(1)].append((int(m.group(2)), int(m.group(3)), u["id"]))
        for cells in tables.values():
            if len({r for r, _, _ in cells}) >= 2 and len({c for _, c, _ in cells}) >= 2:
                out.append(_cand("matrix", "table", [i for _, _, i in sorted(cells)]))
        # numbered steps: boxes that start 1, 2, 3 … on one page
        steps = [(n, u["id"]) for u in page_units if not u.get("arrow") and not _CELL.search(u["id"])
                 for n in [_step_no(u["text"], seps)] if n]
        steps.sort()
        if _run([n for n, _ in steps]):
            out.append(_cand("sequence", "numbered", [i for _, i in steps]))
    for u in units:
        if u.get("arrow"):
            continue
        # numbered lines inside one text
        lines = [n for n in (_step_no(line, seps) for line in re.split(r"[\n\v]", u["text"])) if n]
        if _run(lines) and len(lines) == len(set(lines)):
            out.append(_cand("sequence", "numbered", [u["id"]]))
        # connectives: the first cue of each type, with its context
        for kind, phrases in cues.items():
            if not isinstance(phrases, list):
                continue
            hits = [(u["text"].find(p), p) for p in phrases if p and p in u["text"]]
            if hits:
                at, cue = min(hits)
                ctx = u["text"][max(0, at - CUE_CONTEXT): at + len(cue) + CUE_CONTEXT]
                out.append(_cand(kind, "connective", [u["id"]], cue=cue.strip(), excerpt=ctx.replace("\v", "\n")))
    seen, unique = set(), []
    for c in out:
        if c["id"] not in seen:
            seen.add(c["id"])
            unique.append(c)
    return unique
