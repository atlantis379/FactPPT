"""The deck's argument (``argument.v1``): what this deck asserts, decided before any page exists.

``factdeck.claims`` records what the *source* says, sentence by sentence.  This module records what the *deck*
asserts to the reader — a different object, and one that survives being detached from its paragraph.

A deck is a chain of assertions, not a sequence of layouts.  A page is one assertion made visible; when the
assertion is missing the page has nothing to show and becomes a list of points, which is what half of a
twenty-page deck turns out to be when the slots are counted before the assertions are.

**Who decides what the grade is.**  The model does, and it must say so in the spec.  A first attempt had code
grade the text from keyword tables and it failed on the material in this repo: 「漏诊是最先要处理的问题」and
「初始治疗按分组选择」both came out as "noun phrase", because Chinese assertion structures outrun any list of
words.  A wrong grade is worse than no grade — it sends back advice that does not apply.  So the grade is a
declaration, and code verifies the declaration instead of guessing it:

    declared L3 → there must be a digit in the assertion, and that digit in the sentence it cites
    declared L4 → there must also be a boundary, and the boundary's digits must also be in that sentence
    declared L0–L2 → refused, because the page would carry nothing a reader can check

Everything else code can check is content, not style: modality may be lowered but never raised ("可以考虑"
printed as "推荐" is wrong with every digit correct), two assertions may not say one thing, and the list has to
reach an action somewhere or the listener is informed and unable to decide.

Page count is an output of this module, never an input (``page_range`` and ``verdict``).
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping

SCHEMA = "argument.v1"

GRADES = {
    "L0": "话题：名词短语，没有可被数据占据的位置",
    "L1": "态度：有判断词，但没有任何东西能推翻它",
    "L2": "方向：有主体和方向，可被数据推翻，但没有量",
    "L3": "量化：方向加一个出自证据句的数",
    "L4": "边界：量化加一个声明出来的适用范围",
}
MIN_GRADE = "L3"
_ORDER = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}

# A number is data; the unit is what makes it the right data.  Digits are compared without their unit, because an
# assertion writes "5 天" where the sentence has "5天" — the unit is then checked on its own.
_NUM = re.compile(r"\d+(?:[.,]\d+)?(?:[-–~]\d+(?:[.,]\d+)?)?")
_UNITS = "%倍天周月年例人分级岁次"

# Modality by strength.  The gap between "可以考虑" and "推荐" is the gap between a correct slide and a wrong one,
# and it is invisible to every numeric check.
_MODAL_STRONG = ("推荐", "首选", "必须", "建议", "需要", "应当", "应该", "不宜", "不建议")
_MODAL_WEAK = ("可以考虑", "可考虑", "酌情", "视情况", "或许", "有利于")
_MODAL_ACT = re.compile(r"应(?![用对答急])|需(?![求要])")

_CLAIM_MAX = 40          # one line in a list; longer is a paragraph, and a page cannot be one assertion
_BOUNDARY_MAX = 34


class ArgumentError(ValueError):
    """The assertion list would claim something the material does not support."""


def _need(cond, msg: str) -> None:
    if not cond:
        raise ArgumentError(msg)


def numbers(text: str) -> set[str]:
    """The digit strings a reader would check against the source: 70, 9.7, 15.5, 90-95."""
    return {m.group(0).replace(",", "").replace("–", "-").replace("~", "-")
            for m in _NUM.finditer(text or "")}


def _units_of(text: str) -> set[str]:
    out = set()
    for m in _NUM.finditer(text or ""):
        rest = (text or "")[m.end():].replace("％", "%").lstrip(" 　")
        if rest and rest[0] in _UNITS:
            out.add(rest[0])
    return out


def _modal(text: str) -> str | None:
    if any(w in text for w in _MODAL_STRONG) or _MODAL_ACT.search(text):
        return "strong"
    if any(w in text for w in _MODAL_WEAK):
        return "weak"
    return None


def _lift(text: str) -> str:
    """What a too-weak assertion needs.  One message for every weak case, because telling a model *which* of
    L0-L2 it wrote needs a judgement code cannot make (see the module docstring)."""
    if numbers(text):
        return "句中有数，但等级声明的不是量化：要么声明 L3，要么把这个数删掉——两者只能留一个"
    return ("这句里没有可核对的数字：把它改写成「比什么、多多少、出处是哪一句」，"
            "或者并进相邻那条有数的断言里")


def _shingles(text: str) -> set[str]:
    return {text[i:i + 2] for i in range(len(text) - 1)} or {text}


_NEG = set("不未无没非")


def same_assertion(a: dict, b: dict, threshold: float = 0.55) -> bool:
    """Two assertions are the same when they quantify the same thing in near-identical words.

    Different numbers make different assertions.  So do different polarities: 「70% 未被确诊」and「70% 已确诊」
    share every character but one and mean opposite things, which is why character overlap alone is not enough.
    """
    na, nb = a.get("numbers") or set(), b.get("numbers") or set()
    if na and nb and na != nb:
        return False
    if {c for c in a["text"] if c in _NEG} != {c for c in b["text"] if c in _NEG}:
        return False
    sa, sb = _shingles(a["text"]), _shingles(b["text"])
    return len(sa & sb) / max(1, len(sa | sb)) > threshold


def check(spec: Mapping, facts: Mapping[str, dict]) -> dict:
    """Validate an assertion list against the sentences behind it.  Returns it with evidence resolved.

    Refused, because each of these makes the page a decoration: a grade below L3; a declared quantisation with no
    digit in it; a digit or a unit that is not in the sentence it cites; a modality stronger than the source's; a
    boundary with no quantity to bind, or one carrying digits from outside the source; two assertions that say one
    thing; a list that never reaches an action.  Nothing is rewritten — the model re-decides.
    """
    _need(isinstance(spec, Mapping), "断言清单须为对象")
    _need(spec.get("schema_version") == SCHEMA, f"schema_version 须为 {SCHEMA}")
    raw = spec.get("claims")
    _need(isinstance(raw, list) and raw, "claims 不能为空")

    out, seen = [], set()
    for k, c in enumerate(raw, 1):
        where = f"第{k}条断言"
        _need(isinstance(c, Mapping), f"{where}须为对象")
        aid = c.get("aid") or c.get("id") or f"c{k}"
        _need(aid not in seen, f"断言 id 重复：{aid}")
        seen.add(aid)
        text = (c.get("text") or "").strip()
        _need(bool(text) and "\n" not in text, f"{where}的 text 须为一行文字")
        _need(len(text) <= _CLAIM_MAX, f"{where}有 {len(text)} 字，断言是一行话，上限 {_CLAIM_MAX} 字")

        # The grade is the model's judgement about its own sentence; code only asks whether the evidence carries it.
        g = c.get("grade")
        _need(g in GRADES,
              f"{where}须声明 grade（{' / '.join(GRADES)}）：这句有多强是模型的判断，代码只核对它是否被证据支撑")
        _need(_ORDER[g] >= _ORDER[MIN_GRADE],
              f"{where}「{text}」声明为 {g}（{GRADES[g]}）：低于 {MIN_GRADE} 的句子不能单独成一页——"
              f"{_lift(text)}")

        ids = c.get("evidence")
        _need(isinstance(ids, list) and ids, f"{where}须给出 evidence（支撑它的句子 id）：没有出处的断言是意见")
        quotes = []
        for fid in ids:
            _need(isinstance(fid, str) and fid in facts, f"{where}引用了不存在的句子：{fid}")
            quotes.append(facts[fid]["quote"])
        source = "".join(quotes)

        digits = numbers(text)
        _need(bool(digits),
              f"{where}声明 {g}（量化），但句中没有任何可核对的数字："
              f"中文数词按原文写成数字（原文写 70% 就写 70%），否则读者无法核对")
        # A number in the assertion that no cited sentence contains is the one error that still looks perfect
        # once printed: every digit plausible, the page legible, and the sentence says otherwise.
        missing = digits - numbers(source)
        _need(not missing,
              f"{where}的数字在自己引用的句子里找不到：{'、'.join(sorted(missing))}"
              f"（可选：{'、'.join(sorted(numbers(source))) or '无'}）")
        wrong_unit = _units_of(text) - _units_of(source)
        _need(not wrong_unit,
              f"{where}的单位在来源句里没有：{'、'.join(sorted(wrong_unit))}——"
              f"「70%」写成「70 例」，数字一样，意思全变")

        # Modality may be lowered, never raised: "可以考虑" cannot become "推荐".
        want, have = _modal(text), _modal(source)
        _need(not (want == "strong" and have != "strong"),
              f"{where}用了强推荐（推荐 / 应 / 必须），来源句没有这个强度"
              f"{'（原文是「可以考虑」一类）' if have == 'weak' else '（原文只是描述）'}：数字都对，结论已经错了")

        boundary = (c.get("boundary") or "").strip() or None
        if g == "L4":
            _need(boundary,
                  f"{where}声明 L4（带边界），但没有给 boundary：边界要单独写出来，代码才能核它的出处")
        if boundary:
            _need("\n" not in boundary and len(boundary) <= _BOUNDARY_MAX,
                  f"{where}的 boundary 须为一行、不超过 {_BOUNDARY_MAX} 字")
            leaked = numbers(boundary) - numbers(source)
            _need(not leaked,
                  f"{where}的边界里有句外的数字：{'、'.join(sorted(leaked))}——边界也要有出处")
            _need(len(boundary) >= 4,
                  f"{where}的 boundary「{boundary}」太短，没有说清适用于谁 / 什么条件")
            g = "L4"

        out.append({"id": aid, "text": text, "grade": g, "evidence": list(ids), "quotes": quotes,
                    "boundary": boundary, "numbers": digits, "units": _units_of(text), "modal": want,
                    "action": want == "strong" and have == "strong"})

    # Two assertions that differ only in wording grow the page count without growing the argument.
    for a in range(len(out)):
        for b in range(a + 1, len(out)):
            _need(not same_assertion(out[a], out[b]),
                  f"断言「{out[a]['text']}」与「{out[b]['text']}」说的是同一件事：合并，或删掉一条")

    # A deck that never reaches an action leaves the listener informed and unable to decide anything.
    _need(any(c["action"] for c in out),
          "整份清单没有一条落到行动（推荐 / 应 / 必须，且来源句也有这个强度）："
          "医学材料的终点是「怎么做」，全篇描述等于没给结论")

    tally: dict[str, int] = {}
    for c in out:
        tally[c["grade"]] = tally.get(c["grade"], 0) + 1
    return {"schema_version": SCHEMA, "claims": out, "grades": tally}


def quantifiable(text: str, facts: Mapping[str, dict], evidence) -> bool:
    """Could this sentence become an L3 at all — does it already carry a number that its evidence has?

    This is the one question about strength that code *can* answer on its own, and it needs no model: a title
    with no digit in it cannot pass as quantified however it is worded.  Used to audit a deck that already
    exists, where the grades were never declared.
    """
    d = numbers(text)
    if not d:
        return False
    src = "".join(facts[f]["quote"] for f in evidence if f in facts)
    return d <= numbers(src) and not (_units_of(text) - _units_of(src))


def page_range(n_claims: int, minutes: float | None = None, dwell_seconds: int = 50) -> dict:
    """How many pages these assertions can honestly fill — the number is an answer, not an input.

    Lower bound is one page per assertion: an assertion that has to share its page is an assertion the page is
    not about.  The budget adds a section cover every four assertions.  The clock then caps it, and when the cap
    lands below the assertion count the two constraints contradict each other — which is worth saying out loud
    instead of quietly producing pages nobody has time to read.
    """
    _need(n_claims >= 1, "断言数为零时没有页数可算")
    body = n_claims
    sections = math.ceil(body / 4)
    budget = body + sections
    out = {"claims": n_claims, "low": n_claims, "budget": budget, "high": budget,
           "sections": sections, "time_max": None, "over": 0, "capped_by": None}
    if minutes:
        t = int(minutes * 60 // dwell_seconds)
        out.update(time_max=t, high=min(budget, t), capped_by=f"{minutes:g} 分钟 × {dwell_seconds}s")
        if out["high"] < n_claims:
            out["over"] = n_claims - out["high"]
    return out


def verdict(target: int, rng: dict) -> str:
    """Would `target` pages be honest?  Says what to do when it would not."""
    lo, hi = rng["low"], rng["high"]
    if lo <= target <= hi:
        return (f"{target} 页成立：{rng['claims']} 条断言 = {lo} 页内容 + {rng['sections']} 页章节，"
                f"区间 {lo}–{hi} 页")
    if target > hi:
        if rng["over"]:
            return (f"{target} 页在 {rng['capped_by']} 里讲不完：这段时间只够 {hi} 页，"
                    f"而 {rng['claims']} 条断言至少需要 {lo} 页。删掉 {rng['over']} 条，或加 {rng['over']} 分钟")
        return (f"{target} 页不成立：{rng['claims']} 条断言只撑得起 {lo}–{hi} 页"
                f"{'（受时长限制）' if rng.get('capped_by') else ''}。"
                f"多出的 {target - hi} 页没有断言可放，只能靠要点陈列填——"
                f"要么补 {target - lo} 条有出处的断言，要么讲 {hi} 页")
    return (f"{target} 页太挤：{rng['claims']} 条断言至少需要 {lo} 页。"
            f"一页放两条，读者只会记住其中一条——删掉 {lo - target} 条，或加页")


def contract() -> dict:
    """What a model writing this needs to see."""
    return {"schema_version": SCHEMA, "grades": GRADES, "min_grade": MIN_GRADE,
            "claims": [{"id": "c1", "grade": "L3", "text": "", "evidence": [""], "boundary": ""}]}
