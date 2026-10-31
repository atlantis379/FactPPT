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
    declared L4 → there must also be a scope, and the scope must be quoted from that sentence
    declared L2 → there must be a scope, and no digit (a digit lifts it to L3 on the spot)
    declared L0–L1 → refused, because the page would carry nothing a reader can check

The L2 case is the one that took a second pass to see.  A first version of this module demanded a number at
every grade, and the six assertions it then refused were all treatment decisions — first-line combination
therapy, when not to use immunotherapy, how to group patients.  Those sentences are the reason the guideline
exists, and a number is precisely what they do not have.  So the floor is "directed": the assertion names who
or under what condition, in the source's own words, and that is what code can check.

Everything else code can check is content, not style: modality may be lowered but never raised ("可以考虑"
printed as "推荐" is wrong with every digit correct), two assertions may not say one thing, and the list has to
reach an action somewhere or the listener is informed and unable to decide.

Page count is an output of this module, never an input (``page_range`` and ``verdict``).
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping

from .lexicon import number_spans

SCHEMA = "argument.v1"

GRADES = {
    "L0": "话题：名词短语，没有可被数据占据的位置",
    "L1": "态度：有判断词，但没有任何东西能推翻它",
    "L2": "定向：指定了对象或条件，可被推翻，但没有量",
    "L3": "量化：有一个出自证据句的数",
    "L4": "量化带范围：数加一个逐字出自原文的适用范围",
}
MIN_GRADE = "L2"
_ORDER = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}

# A number is data; the unit is what makes it the right data.  Digits are compared without their unit, because an
# assertion writes "5 天" where the sentence has "5天" — the unit is then checked on its own.
_NUM = re.compile(r"\d+(?:[.,]\d+)?(?:[-–~]\d+(?:[.,]\d+)?)?")
_UNITS = "%倍天周月年例人分级岁次"
# 「6 个月」: 个 is a counter, 月 is the unit.  Read as one token, 个 lands in the digits and the unit becomes
# "个月" in one place and "月" in another — and a unit mismatch is refused, so this is a false refusal waiting
# to happen to the most ordinary sentence in the material.
_COUNTER = "个"
# Reference numbers are apparatus, not wording: they sit inside the phrase a scope must quote verbatim
# (「加剧气流阻塞、(486) 疾病进展」) and a 486 in the apparatus must never be available to a claim as data.
_CITE = re.compile(r"[（(]\d{2,4}(?:[,，、]\d+)*[)）]")

# Modality by strength.  The gap between "可以考虑" and "推荐" is the gap between a correct slide and a wrong one,
# and it is invisible to every numeric check.
_MODAL_STRONG = ("推荐", "首选", "必须", "建议", "需要", "应当", "应该", "不宜", "不建议")
_MODAL_WEAK = ("可以考虑", "可考虑", "酌情", "视情况", "或许", "有利于")
_MODAL_ACT = re.compile(r"应(?![用对答急])|需(?![求要])")

_CLAIM_MAX = 40          # one line in a list; longer is a paragraph, and a page cannot be one assertion
_SCOPE_MAX = 34


class ArgumentError(ValueError):
    """The assertion list would claim something the material does not support."""


def _need(cond, msg: str) -> None:
    if not cond:
        raise ArgumentError(msg)


def _plain(text: str) -> str:
    """The sentence without its reference numbers."""
    return _CITE.sub("", text or "")


def _squash(text: str) -> str:
    """Wording compared with whitespace removed.

    Two reasons, both from the material: cutting "(486)" out of a sentence leaves a space behind, and the source
    writes "≥ 6 个月" where an assertion writes "6个月".  Neither difference is a difference in what was said.
    """
    return re.sub(r"\s+", "", _plain(text))


def _split(token: str) -> tuple[str, str]:
    """One numeral as the reader sees it: the digits and the unit they are written in ("≥5天" → 5 / 天)."""
    t = (token or "").strip()
    while t and t[0] in "≥≤><＞＜":
        t = t[1:]
    j = len(t)
    while j > 0 and t[j - 1] in _UNITS:
        j -= 1
    return (t[:j].replace(",", "").replace("‑", "-").replace("–", "-").rstrip(_COUNTER),
            t[j:].lstrip(_COUNTER))


def numbers(text: str) -> set[str]:
    """The digit strings a reader would check against the source: 70, 9.7, 15.5, 90-95.

    Two readers, unioned.  A plain regex finds every numeral but splits a range whose unit is repeated
    ("90%‑95%" → 90, 95); ``number_spans`` merges that range but judges what counts as data from its clause, so it
    misses the odd bare percentage.  Neither is right alone, and a number that is silently dropped from either
    side turns into a wrong pass.
    """
    out = {m.group(0).replace(",", "").replace("–", "-").replace("~", "-").replace("‑", "-")
           for m in _NUM.finditer(_plain(text))}
    out |= {_split(sp["token"])[0] for sp in number_spans(_plain(text))}
    return {d for d in out if d}


# Three kinds of numeral, and only one of them makes a sentence quantitative.
#   data       — 70%, 15.5, 4-6 周, 5 天: a quantity a reader can check and be wrong about
#   designator — FEV1, β2, PCV20, PCV21, SaO2: part of a name; it must be right, it does not quantify
#   label      — 2026 年: a year attached to a report, not a measurement
# Writing the assertion list from the material turned up the case that forced this split: 「推荐 PCV20 或
# PCV21」is a recommendation with no quantity in it, but a digits-only rule reads two numerals and demands L3.
_DESIGNATOR_BEFORE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzβΒ"


def _designator(text: str, m: re.Match) -> bool:
    """A numeral glued to the Latin name in front of it (FEV1, β2, PCV20) is part of that name."""
    i = m.start()
    return bool(i) and text[i - 1] in _DESIGNATOR_BEFORE


def _label(text: str, m: re.Match) -> bool:
    """A four-digit year is a date on the cover, not a measurement in the body."""
    tok = m.group(0)
    rest = text[m.end():].lstrip(" 　")
    return bool(re.fullmatch(r"(19|20)\d\d", tok)) and rest.startswith("年")


def data_numbers(text: str) -> set[str]:
    """The numerals in `text` that a quantitative claim can rest on — i.e. all of them but the names.

    ``numbers`` stays the verification set: a designator written wrong ("PCV21" for "PCV20") is still an error,
    so it is still compared against the source.  This is only about what may *lift* a grade.
    """
    t = text or ""
    named = {m.group(0).replace(",", "") for m in _NUM.finditer(t) if _designator(t, m) or _label(t, m)}
    return numbers(t) - named


def _units_of(text: str) -> set[str]:
    out = set()
    t = _plain(text)
    for m in _NUM.finditer(t):
        rest = t[m.end():].replace("％", "%").lstrip(" 　")
        if rest.startswith(_COUNTER):
            rest = rest[1:].lstrip(" 　")
        if rest and rest[0] in _UNITS:
            out.add(rest[0])
    out |= {_split(sp["token"])[1] for sp in number_spans(t)}
    return {u for u in out if u}


def _modal(text: str) -> str | None:
    if any(w in text for w in _MODAL_STRONG) or _MODAL_ACT.search(text):
        return "strong"
    if any(w in text for w in _MODAL_WEAK):
        return "weak"
    return None


def _lift(text: str) -> str:
    """What a too-weak assertion needs.  One message for every weak case, because telling a model *which* of
    L0-L1 it wrote needs a judgement code cannot make (see the module docstring)."""
    if data_numbers(text):
        return "句中有数，却声明成了更低的等级：有数的断言应当声明 L3（加适用范围就是 L4）"
    return ("这句没有指定对象，也没有数：补一个 scope（这句话说的是谁、在什么条件下），"
            "或补一个出自证据句的数——两者都有就是 L4")


def _shingles(text: str) -> set[str]:
    return {text[i:i + 2] for i in range(len(text) - 1)} or {text}


_NEG = set("不未无没非")


def same_assertion(a: dict, b: dict, threshold: float = 0.55) -> bool:
    """Two assertions are the same when they quantify the same thing in near-identical words.

    Different numbers make different assertions.  So do different polarities: 「70% 未被确诊」and「70% 已确诊」
    share every character but one and mean opposite things, which is why character overlap alone is not enough.
    Different scopes make different assertions too, and that one is not an edge case: 「单药仍有呼吸困难 → 升级」
    and 「单药期间加重 → 升级」differ only in the trigger, which is the whole content, and their character
    overlap is far above any threshold that would still catch a real duplicate.
    """
    if (a.get("scope") or "") != (b.get("scope") or ""):
        return False
    na, nb = a.get("numbers") or set(), b.get("numbers") or set()
    if na and nb and na != nb:
        return False
    if {c for c in a["text"] if c in _NEG} != {c for c in b["text"] if c in _NEG}:
        return False
    sa, sb = _shingles(a["text"]), _shingles(b["text"])
    return len(sa & sb) / max(1, len(sa | sb)) > threshold


def check(spec: Mapping, facts: Mapping[str, dict]) -> dict:
    """Validate an assertion list against the sentences behind it.  Returns it with evidence resolved.

    Refused, because each of these makes the page a decoration: a grade below L2; a declared quantisation with no
    digit in it; a digit in a claim declared adjectival; a digit or a unit that is not in the sentence it cites; a
    scope that is not the source's own wording; a modality stronger than the source's; two assertions that say one
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

        # L2 carries a scope instead of a number, which is where most of a guideline's action content lives.
        # L3 carries a number.  L4 carries both.  Everything named here has to be found in the sentences.
        scope = (c.get("scope") or c.get("boundary") or "").strip() or None

        digits = numbers(text)
        data = data_numbers(text)
        if g in ("L3", "L4"):
            _need(bool(data),
                  f"{where}声明 {g}（量化），但句中没有任何可核对的数字："
                  f"中文数词按原文写成数字（原文写 70% 就写 70%），否则读者无法核对")
        elif data:
            _need(False,
                  f"{where}句中有数字（{'、'.join(sorted(data))}），却声明成 {g}："
                  f"把等级提到 L3，或把这个数删掉——两者只能留一个")
        if digits:
            # A number in the assertion that no cited sentence contains is the one error that still looks
            # perfect once printed: every digit plausible, the page legible, and the sentence says otherwise.
            missing = digits - numbers(source)
            _need(not missing,
                  f"{where}的数字在自己引用的句子里找不到：{'、'.join(sorted(missing))}"
                  f"（可选：{'、'.join(sorted(numbers(source))) or '无'}）")
            wrong_unit = _units_of(text) - _units_of(source)
            _need(not wrong_unit,
                  f"{where}的单位在来源句里没有：{'、'.join(sorted(wrong_unit))}——"
                  f"「70%」写成「70 例」，数字一样，意思全变")

        if g in ("L2", "L4"):
            _need(scope,
                  f"{where}声明 {g}，须给出 scope：这句话说的是谁、在什么条件下（逐字取自证据句）——"
                  f"没有对象的断言无法核对，也无法放到页面上")
        if scope:
            _need("\n" not in scope and len(scope) <= _SCOPE_MAX,
                  f"{where}的 scope 须为一行、不超过 {_SCOPE_MAX} 字")
            _need(len(scope) >= 4,
                  f"{where}的 scope「{scope}」太短，没有说清适用于谁 / 什么条件")
            _need(_squash(scope) in _squash(source),
                  f"{where}的 scope「{scope}」不是证据句的原文：适用范围也要有出处，照抄那句里的写法")
            # A scope the assertion already contains adds nothing to the page: it prints the same words twice,
            # which is the failure the twenty-page deck had everywhere (its conclusion restated its title).
            _need(_squash(scope) not in _squash(text),
                  f"{where}的 scope「{scope}」在断言句里已经出现了：它不是适用条件，是把句子再说一遍——"
                  f"写清这句话说的是谁、在什么情况下，或删掉 scope 降为更低的等级")
            g = "L4" if data else "L2"

        # Modality may be lowered, never raised: "可以考虑" cannot become "推荐".
        want, have = _modal(text), _modal(source)
        _need(not (want == "strong" and have != "strong"),
              f"{where}用了强推荐（推荐 / 应 / 必须），来源句没有这个强度"
              f"{'（原文是「可以考虑」一类）' if have == 'weak' else '（原文只是描述）'}：数字都对，结论已经错了")

        out.append({"id": aid, "text": text, "grade": g, "evidence": list(ids), "quotes": quotes,
                    "scope": scope, "numbers": digits, "units": _units_of(text), "modal": want,
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
    d = data_numbers(text)
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
            "claims": [{"id": "c1", "grade": "L3", "text": "", "evidence": [""], "scope": ""}]}
