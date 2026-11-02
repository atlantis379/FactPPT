"""The deck's argument (``argument.v2``): what this deck asserts, decided before any page exists.

``factdeck.claims`` records what the *source* says, sentence by sentence.  This module records what the *deck*
asserts to the reader.  A deck is a chain of assertions, not a sequence of layouts.

**Assertions are references, not prose.**  The first version had the model write each assertion and declare its
grade, and code verified the declaration: digit in the sentence, modality not raised, scope quoted.  That passed
「不建议」→「建议」and「超过70%」→「不足70%」, and 21 of 21 pages cleared it while one rounded 「不超过5天」to 「5 天」
and one turned 「可能有一定益处」into 「用于」.  The checks were reading words without their place in the sentence, so
what they reported as safe was not.  They are gone, with the grades they served.  An assertion is now what
``factdeck.shown`` allows on a slide: an excerpt, or a derivation a person has confirmed.

**Pages.**  A page carries one judgement and the objects it enumerates live in its evidence area, so pages are a
partition of the assertions (``partition``), and the page count comes from judgements, not from assertions: 50
assertions from the guideline partition into 21 pages with nothing dropped.  ``page_range`` then takes that number.
Which assertions belong to one judgement is the model's call; that nothing was lost or told twice is code's.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

from .shown import ShownError, resolve

SCHEMA = "argument.v2"
_CLAIM_MAX = 56          # what fits the two lines of a title


class ArgumentError(ShownError):
    """The assertion list would claim something the material does not support."""


def _need(cond, msg: str) -> None:
    if not cond:
        raise ArgumentError(msg)


def check(spec: Mapping, facts: Mapping[str, dict], confirmed=()) -> dict:
    """Resolve an assertion list to the sentences behind it.  Nothing is rewritten; the model re-decides.

    Derivations a person has not confirmed are returned in ``pending``: they stay on the list, off the slides.
    """
    _need(isinstance(spec, Mapping), "断言清单须为对象")
    _need(spec.get("schema_version") == SCHEMA, f"schema_version 须为 {SCHEMA}")
    raw = spec.get("claims")
    _need(isinstance(raw, list) and raw, "claims 不能为空")

    out, seen, texts = [], set(), {}
    for k, c in enumerate(raw, 1):
        where = f"第{k}条断言"
        _need(isinstance(c, Mapping), f"{where}须为对象")
        aid = c.get("id") or f"c{k}"
        _need(aid not in seen, f"断言 id 重复：{aid}")
        seen.add(aid)
        said = resolve(c.get("say"), facts, where, confirmed, ArgumentError)
        text = said["text"]
        _need(len(text) <= _CLAIM_MAX, f"{where}有 {len(text)} 字，上限 {_CLAIM_MAX} 字：用 show 取节选，或换一句")
        _need(text not in texts, f"断言 {texts.get(text)} 与 {aid} 是同一句：合并，或删掉一条")
        texts[text] = aid
        out.append({"id": aid, **said})
    return {"schema_version": SCHEMA, "claims": out,
            "pending": [{"id": c["id"], "text": c["text"], "from": c["facts"], "digest": c["digest"]}
                        for c in out if c["pending"]]}


def partition(pages: list[Mapping], claims: list[Mapping]) -> int:
    """Every assertion on exactly one page.  Returns the number of pages, which is the number of judgements.

    A merge that quietly drops an assertion looks exactly like a good merge, so this is what makes merging safe.
    """
    have = {c["id"] for c in claims}
    covered = [cid for p in pages for cid in p["covers"]]
    missing = sorted(have - set(covered))
    _need(not missing, f"这些断言没有落到任何一页：{'、'.join(missing)}")
    twice = sorted({c for c in covered if covered.count(c) > 1})
    _need(not twice, f"这些断言落在两页上：{'、'.join(twice)}")
    extra = sorted(set(covered) - have)
    _need(not extra, f"页面引用了清单里没有的断言：{'、'.join(extra)}")
    return len(pages)


def page_range(judgements: int, minutes: float | None = None, dwell_seconds: int = 50) -> dict:
    """How many pages these judgements can honestly fill — the number is an answer, not an input.

    Lower bound is one page per judgement: two judgements sharing a page leave it about neither.  The budget adds a
    section cover every four.  The clock then caps it, and when the cap lands below the judgement count the two
    constraints contradict each other, which is worth saying out loud.
    """
    _need(judgements >= 1, "判断数为零时没有页数可算")
    sections = math.ceil(judgements / 4)
    budget = judgements + sections
    out = {"judgements": judgements, "low": judgements, "budget": budget, "high": budget,
           "sections": sections, "time_max": None, "over": 0, "capped_by": None}
    if minutes:
        t = int(minutes * 60 // dwell_seconds)
        out.update(time_max=t, high=min(budget, t), capped_by=f"{minutes:g} 分钟 × {dwell_seconds}s")
        if out["high"] < judgements:
            out["over"] = judgements - out["high"]
    return out


def verdict(target: int, rng: dict) -> str:
    """Would `target` pages be honest?  Says what to do when it would not."""
    lo, hi = rng["low"], rng["high"]
    if lo <= target <= hi:
        return f"{target} 页成立：{rng['judgements']} 个判断，区间 {lo}–{hi} 页"
    if target > hi:
        if rng["over"]:
            return (f"{target} 页在 {rng['capped_by']} 里讲不完：这段时间只够 {hi} 页，"
                    f"而 {rng['judgements']} 个判断至少需要 {lo} 页。删掉 {rng['over']} 个，或加时长")
        return (f"{target} 页不成立：{rng['judgements']} 个判断只撑得起 {lo}–{hi} 页"
                f"{'（受时长限制）' if rng.get('capped_by') else ''}。多出的 {target - hi} 页没有内容可放")
    return (f"{target} 页太挤：{rng['judgements']} 个判断至少需要 {lo} 页。"
            f"删掉 {lo - target} 个判断，或加页；同一判断下的对象可以进证据区，不必各占一页")


def contract() -> dict:
    """What a model writing this needs to see."""
    return {"schema_version": SCHEMA,
            "claims": [{"id": "c1", "say": {"fact": "", "show": ""}},
                       {"id": "c2", "say": {"derived": "", "from": [""]}}],
            "pages": [{"id": "p1", "covers": ["c1", "c2"]}]}
