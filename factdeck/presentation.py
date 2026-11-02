"""Presentation spec (``presentation.v2``): the model decides how a page is shown, code only checks the data.

The model reads the draft (each topic's messages and the verbatim sentences behind them) and answers, page by page:
what is this page's structure, which sentence leads, which number carries the page, what is the takeaway.  It never
writes displayed text: every content slot points at a sentence id and the code puts that sentence's own words there.
What the model may write is organising text only — short labels that name things and state nothing.

Why this exists: a fixed template with fixed slots can only show what fits its slots.  Pages whose material is
richer (200+ characters, a comparison, a number worth a whole page) were being squeezed into four equal cards.
Structure is a judgement about the material, so it belongs to the model; verbatim accuracy is a fact, so it stays
with the code.

What the model decides, and what it may not: it decides the structure, the sentences, the picture (composed from
parts, in the order it wants), which points lead, and whether a page is allowed to breathe.  It never decides
geometry, and it does not write what the page asserts: a headline is a reference (``factdeck.shown``), and a figure
takes each number from where it stands in the sentence, so what a number belongs to is read off the source.

Four structures to start (coarse on purpose — see ``STRUCTURES``); each maps to one parametric HTML layout rendered
to native shapes by ``factdeck.template_lib.native``.  Nothing here draws a picture or invents a coordinate.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from .lexicon import lexicon, lint_text, number_occurrences, number_spans
from .shown import ShownError, resolve

SCHEMA = "presentation.v2"

# structure → (min items, max items, needs a lead value)
STRUCTURES: dict[str, tuple[int, int, bool]] = {
    "stat": (0, 4, True),        # one number carries the page, a few points explain it
    "points": (3, 6, False),     # parallel points of equal weight
    "compare": (2, 8, False),    # two sides set against each other
    "steps": (3, 5, False),      # an ordered chain
}

# The visual form a page asks for, and what the material must contain before the code lets it be drawn that way.
# A page may always fall back to text; it may not claim a chart its sentences cannot fill.  Declaring the form is the
# model's judgement (it knows what the page is arguing); meeting the requirement is a fact the code can check.
FORMS: dict[str, str] = {
    "text": "无要求：文字版式",
    "bars": "≥2 个可比数值，同一量纲（百分比 / 倍数 / 例数）",
    "threshold": "≥1 个带比较符或「至少 / 超过 / 不超过」的阈值",
}

# A page's figure is a list of parts the model composes.  One part is the common case; two or three stack down the
# page (a split over a set of bars).  Each kind has its own data contract, checked against the sentences — the
# model decides which parts and in what order, the code decides their geometry.
FIGURES: dict[str, str] = {"split": FORMS["threshold"], "bars": FORMS["bars"]}
# A single part is reported under the shorthand the model is told about, so the answer and the menu share words.
_FORM_OF = {"split": "threshold", "bars": "bars"}
MAX_PARTS = 3
MAX_BARS = 6

# A page's role, borrowed from the design rules (§4.1): a hero page is allowed to breathe, a supporting page has
# to carry its area.  Declaring it is the model's call; whether the page has the material to justify it is not.
ROLES = ("hero", "supporting")
WEIGHTS = ("core", "support")

_TIME_UNITS = ("周", "个月", "月", "年", "天", "小时", "分钟")
_OP_CHARS = ("≥", "≤", ">", "<")
_THRESHOLD_WORDS = ("至少", "超过", "不超过", "不高于", "不低于", "高于", "低于", "最多", "不少于", "以上", "以下")
_CONDITION_WORDS = ("若", "如果", "对于", "当", "在…情况下", "一旦", "需要时")

# A comparison written as a word has an exact symbol, and "超过" and "至少" are not the same boundary: one is
# strict, the other inclusive.  Matching the model's op against words found in the sentence keeps it from
# softening ">" into "≥" where the number would then cover cases the source excludes.
_WORD_OP = {"至少": "≥", "不低于": "≥", "不少于": "≥", "超过": ">", "高于": ">", "大于": ">", "以上": ">",
            "不超过": "≤", "不高于": "≤", "最多": "≤", "至多": "≤", "以内": "≤", "以下": "≤",
            "低于": "<", "小于": "<", "少于": "<"}
_OP_COMPLEMENT = {"≥": "<", ">": "≤", "≤": ">", "<": "≥"}

_HEADLINE_MAX = 56    # two lines of the title
_LABEL_MAX = 18
_TAKEAWAY_MAX = 52
_ITEM_LABEL_MAX = 14
_INDICATOR_MAX = 14
_CLAUSE_MAX = 30      # one line of small print under a gauge

# A point has to stay readable in the column it lands in: three lines at the widest, and every structure has its
# own column width.  Checking this here means a sentence that cannot fit is refused before anything is drawn,
# instead of being found by looking at a picture afterwards.
_ITEM_MAX = {"stat": 74, "points": 86, "compare": 62, "steps": 40}

# A sentence that opens with a pronoun needs the one before it; alone on a slide it reads as a fragment
# ("这些国家中超过90%-95%的病例未被确诊" — which countries?).  Either the model cites the sentence before it too,
# or it picks another sentence.
_CTX_OPEN = re.compile(r"^(这|该|其|此|上述|前述|以上)")
_CTX_PHRASE = ("这些国家", "该国", "该组", "上述患者", "这些患者", "前者", "后者", "该研究", "该队列", "同上")


def context_dependent(text: str) -> bool:
    """Does this sentence only make sense with the one before it?"""
    t = text.strip()
    return bool(_CTX_OPEN.match(t)) or any(p in t for p in _CTX_PHRASE)


def _unit_of(token: str) -> str:
    """The unit a token ends in, from the same list that cut the token.  Units are project vocabulary, not code."""
    for u in sorted(lexicon()["units"], key=len, reverse=True):
        if token.endswith(u.lower()):
            return u.lower()
    return ""


def _qualifier(quote: str, hit: dict) -> str:
    """The word that qualifies this number where it stands, if any: part of what the source said about it."""
    before = quote[:hit["start"]].rstrip()
    return next((w for w in sorted(lexicon()["claim_qualifiers"], key=len, reverse=True) if before.endswith(w)), "")


def emphasis_spans(text: str) -> list[tuple[int, int]]:
    """Where the eye should land in a sentence: its numbers, each with the word that qualifies it.  Code marks these
    on every sentence alike, so emphasis needs no authored rewriting and can never emphasise something else."""
    out = []
    for h in number_occurrences(text):
        word = _qualifier(text, h)
        out.append((h["start"] - len(word) if text[:h["start"]].endswith(word) else h["start"], h["end"]))
    return out


def materials(fact_ids, facts: Mapping[str, dict]) -> dict:
    """What shapes these sentences actually contain — what a page's form has to be chosen from.

    A model cannot judge 'this page should be a trend line' without knowing whether the sentences hold time points.
    That form does not exist yet, and this inventory is how a caller can tell without guessing: it lists the numbers,
    the ones in time units, the ones that are thresholds, the units that have two or more values to compare, and the
    sentences that state a condition.
    """
    from collections import defaultdict

    numbers, timeline, thresholds, by_unit = [], [], [], defaultdict(list)
    for fid in fact_ids:
        q = facts[fid]["quote"]
        for sp in number_spans(q):
            item = {"token": sp["token"], "clause": sp["clause"], "fact": fid}
            numbers.append(item)
            unit = _unit_of(sp["token"])
            if unit in _TIME_UNITS:
                timeline.append(item)
            if sp["token"][:1] in _OP_CHARS or any(w in sp["clause"] for w in _THRESHOLD_WORDS):
                thresholds.append(item)
            if unit:
                by_unit[unit].append(item)
    comparable = {u: v for u, v in by_unit.items()
                  if len({x["token"] for x in v}) >= 2 and len({x["fact"] for x in v}) >= 2}
    conditions = [fid for fid in fact_ids
                  if any(w in facts[fid]["quote"][:14] for w in _CONDITION_WORDS)]
    return {"numbers": numbers, "timeline": timeline, "thresholds": thresholds,
            "comparable": comparable, "conditions": conditions}


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def names(name: str, text: str) -> bool:
    """Does `text` say this name, word for word?  Anything looser is a guess at what a sentence is about."""
    return _squash(name) in _squash(text)


class PresentationError(ShownError):
    """The spec would show something the material does not support."""


def _need(cond, msg: str) -> None:
    if not cond:
        raise PresentationError(msg)


def _fact(fid, facts: Mapping[str, dict], where: str) -> dict:
    _need(isinstance(fid, str) and fid in facts, f"{where} 引用了不存在的句子：{fid}")
    f = facts[fid]
    return {"fact": fid, "quote": f["quote"], "source_id": f.get("source_id"),
            "page_id": f.get("page_id") or f.get("location"), "unit_id": f.get("unit_id") or f.get("unit")}


def check(spec: Mapping, facts: Mapping[str, dict], confirmed=()) -> dict:
    """Validate a presentation against the draft's sentences. Returns the normalised spec with sentences resolved.

    Refused: an unknown structure; a page whose slot counts fall outside the structure; a sentence that is not in the
    draft; a lead value that is not one of the numbers in the sentence it names; a headline that is not a reference
    (``shown.resolve``).  Nothing is corrected — a page that cannot be supported has to be re-decided by the model.
    A headline that synthesises several sentences comes back in ``pending`` until a person confirms its digest
    (`confirmed`), and such a page cannot be rendered.
    """
    _need(isinstance(spec, Mapping), "呈现方案须为对象")
    _need(spec.get("schema_version") == SCHEMA, f"schema_version 须为 {SCHEMA}")
    pages = spec.get("pages")
    _need(isinstance(pages, list) and pages, "pages 不能为空")

    out, seen, pending = [], set(), []
    for i, p in enumerate(pages, 1):
        _need(isinstance(p, Mapping), f"第{i}页须为对象")
        pid = p.get("id") or f"p{i}"
        _need(pid not in seen, f"页 id 重复：{pid}")
        seen.add(pid)
        st = p.get("structure")
        _need(st in STRUCTURES, f"第{i}页 structure 须为 {' / '.join(STRUCTURES)}")
        lo, hi, needs_lead = STRUCTURES[st]
        role = p.get("role") or "supporting"
        _need(role in ROLES, f"第{i}页 role 须为 {' / '.join(ROLES)}")

        # The page's figure: the model composes it from parts, each with its own data contract.  A single `form`
        # is accepted as shorthand for one part, so a page can still be summed up in one word.
        parts_raw = p.get("figure")
        form = p.get("form") or "text"
        _need(form in FORMS, f"第{i}页 form 须为 {' / '.join(FORMS)}")
        if parts_raw is None and form != "text":
            parts_raw = [{"kind": "split", "thresholds": p.get("thresholds")} if form == "threshold"
                         else {"kind": "bars", "series": p.get("series")}]
        parts_raw = parts_raw or []
        _need(isinstance(parts_raw, list), f"第{i}页 figure 须为列表")
        _need(len(parts_raw) <= MAX_PARTS,
              f"第{i}页 figure 有 {len(parts_raw)} 部分，一页最多 {MAX_PARTS} 部分："
              f"一块以上已经不是图，是没有目录的拼贴——分页，或留一块加一句 takeaway")
        figures, fig_facts = _figure_parts(parts_raw, facts, i)
        drawn = "、".join(f["kind"] for f in figures)

        items = p.get("items") or []
        _need(isinstance(items, list), f"第{i}页 items 须为列表")
        if figures:
            # The figure is the page.  A point beside it competes for the same width and, at one part, leaves the
            # figure smaller than the text next to it: the sentence behind it belongs in the figure's own rows.
            _need(not items, f"第{i}页有 figure，不列 items：图本身就是这页的内容，"
                            f"要补充的话换一句放 takeaway，或把那条要点单独做一页")
        else:
            _need(lo <= len(items) <= hi, f"第{i}页（{st}）的 items 须为 {lo}–{hi} 条，现有 {len(items)} 条")
        resolved = [_item(it, facts, f"第{i}页 items[{k}]", st) for k, it in enumerate(items)]
        labels_seen = set()
        for k, r in enumerate(resolved):
            _need(r["label"] not in labels_seen, f"第{i}页 items[{k}] 的 label 与同页其它条重复：{r['label']}")
            labels_seen.add(r["label"])
        _weights(resolved, i, st)

        # The figure's own sentences count as cited on this page, before the headline is checked: a headline is
        # allowed to name the boundary number, and that number comes from the gauge's sentence.
        fact_ids = [f for r in resolved for f in r["facts"]]
        fact_ids += [f for f in fig_facts if f not in fact_ids]
        take = p.get("takeaway")
        if take is not None:
            resolved_take = _fact(take.get("fact") if isinstance(take, Mapping) else take, facts, f"第{i}页 takeaway")
            _need(len(resolved_take["quote"]) <= _TAKEAWAY_MAX,
                  f"第{i}页 takeaway 引用的一句话有 {len(resolved_take['quote'])} 字，超过一行的 {_TAKEAWAY_MAX} 字：换一句更短的")
            _need(resolved_take["fact"] not in fact_ids,
                  f"第{i}页 takeaway 与页内某条要点是同一句，重复无信息：换一句本页小结")
            fact_ids.append(resolved_take["fact"])
        else:
            resolved_take = None

        # A takeaway that cites a sentence the figure already draws prints it twice on one slide.
        if resolved_take is not None:
            _need(resolved_take["fact"] not in fig_facts,
                  f"第{i}页 takeaway 与图是同一句，等于把图再说一遍：换一句本页小结，或留空")

        # the lead is its own content slot, so its sentence counts as cited on this page.  A page drawn as a figure
        # already puts a number at full size; a second one would compete with it.
        lead = None
        if figures:
            _need(not p.get("lead"),
                  f"第{i}页要画 {drawn}，主数字已经在图里：不要另给 lead，把那个数放进图里，或二选一")
        elif needs_lead:
            l = p.get("lead")
            _need(isinstance(l, Mapping), f"第{i}页（{st}）须给出 lead（本页的主数字）")
            src = _fact(l.get("from"), facts, f"第{i}页 lead.from")
            fact_ids.append(src["fact"])
            value = l.get("value")
            _need(isinstance(value, str) and value.strip(), f"第{i}页 lead.value 须为文字")
            hits = {h["token"]: h for h in number_occurrences(src["quote"])}
            word = next((w for w in sorted(lexicon()["claim_qualifiers"], key=len, reverse=True)
                         if value.strip().startswith(w)), "")
            bare = value.strip()[len(word):].strip()
            _need(bare in hits and (not word or names(value, src["quote"])),
                  f"第{i}页 lead.value「{value}」不是该句中的数字（可选：{'、'.join(sorted(hits)) or '无'}）")
            # A number shown alone states an exact figure.  The sentence's qualifier stays with it, at any size.
            kept = _qualifier(src["quote"], hits[bare])
            _need(word == kept, f"第{i}页 lead.value「{value}」丢了原文的限定词「{kept}」：写成「{kept}{bare}」")
            label = _label(l.get("label"), f"第{i}页 lead.label", _LABEL_MAX)
            _need(label, f"第{i}页 lead.label 须为一行文字")
            lead = {"value": value.strip(), "word": word, "bare": bare, "label": label,
                    "fact": src["fact"], "quote": src["quote"]}

        # The largest words on the page, so they are the ones that may not be written: see factdeck.shown.
        headline, waiting, headline_em = None, False, []
        if p.get("headline") is not None:
            said = resolve(p["headline"], facts, f"第{i}页 headline", confirmed, PresentationError)
            headline, waiting = said["text"], said["pending"]
            _need(len(headline) <= _HEADLINE_MAX,
                  f"第{i}页 headline 有 {len(headline)} 字，标题最多两行 {_HEADLINE_MAX} 字：用 show 取节选，或换一句")
            _need(said["kind"] == "derivation" or not context_dependent(headline),
                  f"第{i}页 headline 以指代开头，单独读不懂（「{headline[:16]}…」）：换一句自带主语的")
            _need(not (resolved_take and resolved_take["fact"] in said["facts"]),
                  f"第{i}页 takeaway 与标题是同一句：换一句本页小结，或留空")
            em = p["headline"].get("em") or []
            em = [em] if isinstance(em, str) else em
            for piece in em:
                _need(isinstance(piece, str) and piece and piece in headline,
                      f"第{i}页 headline.em「{piece}」不是标题里的连续片段")
            headline_em = list(em)
            if waiting:
                pending.append({"page": pid, "text": headline, "from": said["facts"], "digest": said["digest"]})

        # A takeaway that repeats the number the page is already built around says nothing new either.
        _need(not (lead and resolved_take and lead["fact"] == resolved_take["fact"]),
              f"第{i}页 takeaway 与主数字是同一句，等于把标题重说一遍：换一句本页小结，或留空")

        side_labels = _labels(p.get("labels"), st, i)
        if st == "compare":
            _need(side_labels, f"第{i}页（compare）须给出 labels（左右两栏各叫什么）")
            half = (len(resolved) + 1) // 2
            for k, r in enumerate(resolved):
                side = 0 if k < half else 1
                _need(names(side_labels[side], r["quote"]),
                      f"第{i}页 items[{k}] 的句子没有提到「{side_labels[side]}」，放到这一栏会替它作原文没有的归属："
                      f"换到另一栏，或换一句明确说到它的")

        # Where the material is thin, the page still has to hold its area; role says whether it must.
        mat = materials(fact_ids, facts)

        out.append({"id": pid, "structure": st, "role": role,
                    "form": "text" if not figures else (
                        _FORM_OF[figures[0]["kind"]] if len(figures) == 1 else "composite"),
                    "figure": figures,
                    "headline": headline, "headline_em": headline_em, "pending": waiting, "lead": lead, "items": resolved,
                    "weights": [r["weight"] for r in resolved],
                    "takeaway": resolved_take,
                    # Kept flat for the renderer and for anything that only wants "the page's boundaries".
                    "thresholds": [t for f in figures if f["kind"] == "split" for t in f["thresholds"]],
                    "bars": next((f for f in figures if f["kind"] == "bars"), None),
                    "materials": {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in mat.items()},
                    "section": _label(p.get("section"), f"第{i}页 section", 16),
                    "labels": side_labels,
                    "span": None if p.get("span") is None else [str(x) for x in p["span"]]})
    return {"schema_version": SCHEMA, "pages": out, "pending": pending}


def _figure_parts(parts_raw, facts: Mapping[str, dict], i: int) -> tuple[list[dict], list[str]]:
    """Resolve the parts a page composes, each against its own contract.

    The model decides which parts a page has and in what order; the code decides what each kind may claim.  Two
    things are page-wide rather than part-wide: the count of gauges (two is the ceiling wherever they sit — a third
    turns the page into a table), and the naming of two groups of bars (two unnamed groups read as one mess).
    """
    parts, used, gauges = [], [], 0
    for k, part in enumerate(parts_raw):
        where = f"第{i}页 figure[{k}]"
        _need(isinstance(part, Mapping), f"{where} 须为对象")
        kind = part.get("kind")
        _need(kind in FIGURES, f"{where} 的 kind 须为 {' / '.join(FIGURES)}：「{kind}」不是可组合的部分")
        if kind == "split":
            th = _thresholds(part.get("thresholds"), facts, i)
            gauges += len(th)
            _need(gauges <= 2,
                  f"第{i}页有 {gauges} 根量规，一页最多 2 根：三根以上已经不是图，是一张表——"
                  f"把多出来的分到别的页，或改用 points 逐条列出")
            parts.append({"kind": "split", "thresholds": th})
            used += [t["fact"] for t in th]
        else:
            series = _bars(part.get("series"), facts, i, where)
            parts.append({"kind": "bars", "label": _label(part.get("label"), f"{where}.label", _LABEL_MAX),
                          "unit": series[0]["unit"], "base": series[0]["base"], "series": series})
            used += [s["fact"] for s in series]
    if sum(1 for p in parts if p["kind"] == "bars") > 1:
        for k, part in enumerate(parts):
            if part["kind"] == "bars":
                _need(part["label"],
                      f"第{i}页有两组柱形，figure[{k}] 须给出 label（这组柱量的是什么）："
                      f"两组无名柱并排，读者分不清哪根属于哪组")
    drawn = [t["indicator"] for part in parts if part["kind"] == "split" for t in part["thresholds"]]
    twice = sorted({x for x in drawn if drawn.count(x) > 1})
    _need(not twice,
          f"第{i}页同一根量规画了两遍（{'、'.join(twice)}）：同一页上重复的边界不传达任何新东西")
    return parts, used


def _bars(raw, facts: Mapping[str, dict], i: int, where: str) -> list[dict]:
    """A set of bars: one scale, so length means something.

    Two ways a bar chart lies, both refused here: values that do not share a unit (a 5-day course drawn beside 90%
    has no common scale, so the longer bar means nothing), and values that are not in the sentence they name (the
    length would be drawn from nothing).  Order is the model's: it may be by size, or the order the source lists
    them in, which itself carries meaning.
    """
    _need(isinstance(raw, list) and raw,
          f"{where} 要画柱形，须给出 series（每条：indicator / value / fact）")
    _need(len(raw) >= 2, f"{where} 只有 {len(raw)} 根柱，构不成比较：至少 2 根")
    _need(len(raw) <= MAX_BARS,
          f"{where} 有 {len(raw)} 根柱，一页最多 {MAX_BARS} 根：再多读不出长短，只会去读数字——那用 points")

    out, seen = [], set()
    for k, s in enumerate(raw):
        w = f"{where} series[{k}]"
        _need(isinstance(s, Mapping), f"{w} 须为对象")
        fid = s.get("fact")
        _fact(fid, facts, f"{w}.fact")
        quote = facts[fid]["quote"]
        ind = _name(s.get("indicator"), f"{w}.indicator")
        _need(ind, f"{w} 须给出 indicator（这根柱量的是谁，取原句里的词）")
        _need(ind not in seen, f"{w} 的 indicator 与同组另一根重复：同一根柱不画两遍")
        _need(names(ind, quote), f"{w} 的 indicator「{ind}」在这句里找不到：取原句里的词")
        seen.add(ind)
        value = str(s.get("value") or "").strip()
        hit = _hit(quote, value, ind)
        _need(hit, f"{w} 的 value「{value}」不是来源句中的数字"
                   f"（可选：{'、'.join(h['token'] for h in number_occurrences(quote)) or '无'}）")
        _need("-" not in value and "~" not in value and "至" not in value,
              f"{w} 的数值是一个区间（「{value}」），一根柱只能是一个数：换一个确定的值，或改用 threshold")
        # 「超过10%」is a bound.  A bar has one length, so drawing it would state an exact 10%.
        _need(not _bound(quote, hit), f"{w} 的「{value}」在原句里是一个界值，柱长只能画确定的数：改用 threshold")
        unit = _unit_of(value)
        _need(unit, f"{w} 的数值「{value}」没有单位，柱长无从比较：换一个带单位的数（% / 倍 / 例 / 天）")
        digits = value[: len(value) - len(unit)]
        try:
            amount = float(digits.replace(",", ""))
        except ValueError:
            raise PresentationError(f"{w} 的数值「{value}」不是一个可比较的数：柱长画不出来") from None
        _need(amount > 0, f"{w} 的数值「{value}」不大于 0，柱长为零：这一项用文字说")
        base = None
        if unit == "%":
            # Two percentages compare only over one denominator; the sentences have to name it in the same words.
            base = _name(s.get("base"), f"{w}.base")
            _need(base and names(base, quote), f"{w} 是百分比，须用 base 给出原句里的分母（占谁的百分之几）")
        out.append({"indicator": ind, "value": value, "numeral": digits, "unit": unit, "base": base,
                    "amount": amount, "fact": fid, "clause": hit["clause"], "at": hit["start"]})

    units = {x["unit"] for x in out}
    _need(len(units) == 1,
          f"{where} 的数值量纲不一致（{'、'.join(sorted(units))}）：柱长只有同一量纲才可比，"
          f"混在一组里长的并不比短的多——拆成两页，或改用 points")
    _need(len({x["value"] for x in out}) >= 2, f"{where} 每根柱的数值都一样，画出来是等长：这不是比较")
    bases = {_squash(x["base"] or "") for x in out}
    _need(len(bases) == 1, f"{where} 的分母不同（{'、'.join(sorted(bases))}）：比例不能画在一个刻度上——拆开，或改用 points")
    _belongs(out, facts, where)
    top = max(x["amount"] for x in out)
    for x in out:                       # zero-based: a bar's length is its share of the largest, nothing more
        x["ratio"] = round(x["amount"] / top, 4)
    return out


def _hit(quote: str, value: str, name: str) -> dict | None:
    """Where this value stands in the sentence, preferring the place next to its name."""
    hits = [h for h in number_occurrences(quote) if h["token"] == value]
    return next((h for h in hits if names(name, h["clause"])), hits[0] if hits else None)


def _bound(quote: str, hit: dict) -> bool:
    """Is this number one side of a comparison?  This can only refuse a bar, so an unlisted word costs a refusal
    that never comes, not a false pass of anything else."""
    before, after = quote[:hit["start"]].rstrip(), quote[hit["end"]:].lstrip()
    if hit["token"][:1] in _OP_CHARS or before[-1:] in _OP_CHARS:
        return True
    return any(before.endswith(w) for w in _WORD_OP) or after.startswith(("以上", "以下", "以内"))


def _belongs(bars: list[dict], facts: Mapping[str, dict], where: str) -> None:
    """Is each number the one its label's sentence gives it?  Read from positions, so no vocabulary is involved.

    A number belongs to a name in its own clause, when it is the only number there.  「分别高出15.5倍和2.8倍」has
    two, and there the only link is order: every number has to be drawn, in the order the names stand.  Anything
    else is a number lifted from a sentence that gives it to someone else.
    """
    by_fact: dict[str, list[dict]] = {}
    for x in bars:
        by_fact.setdefault(x["fact"], []).append(x)
    for fid, group in by_fact.items():
        quote = _squash(facts[fid]["quote"])
        order = sorted(group, key=lambda x: quote.find(_squash(x["indicator"])))
        _need([x["at"] for x in order] == sorted(x["at"] for x in order),
              f"{where} 的柱与原句的先后不符：「{'、'.join(x['indicator'] for x in order)}」"
              f"配的数是 {'、'.join(x['value'] for x in order)}，与它们在句中的顺序相反")
        hits = number_occurrences(facts[fid]["quote"])
        shared = [h["clause"] for h in hits]
        apart = [x for x in group if not names(x["indicator"], x["clause"]) or shared.count(x["clause"]) > 1]
        total = len(hits)
        _need(not apart or len(group) == total,
              f"{where} 的「{apart[0]['indicator'] if apart else ''}」与它的数不在一个分句，"
              f"这句有 {total} 个数只画了 {len(group)} 个，无从确定对应关系：取同一分句里的词")


def _weights(items: list[dict], i: int, structure: str) -> None:
    """Which points lead.  The code owns how much bigger a core point is set; the model says which ones are.

    Left unmarked, every point is set equal — right when the sentences really are parallel.  Marking is
    all-or-nothing and capped at two: one core point is a hierarchy, three cores are three headlines and no page,
    and marking only half leaves the renderer guessing what the rest are.
    """
    marked = [it for it in items if it.get("weight")]
    if not marked:
        for it in items:
            it["weight"] = "support"
        return
    _need(structure == "points",
          f"第{i}页（{structure}）不标 weight：stat 的主次由主数字表达，steps 靠编号成序，compare 靠两栏对照——"
          f"这些版式已经说出了谁先读，再标一遍是两套指令")
    _need(len(items) >= 2, f"第{i}页只有 {len(items)} 条要点，标不出主次：去掉 weight")
    _need(len(marked) == len(items),
          f"第{i}页有 {len(marked)}/{len(items)} 条标了 weight：要么每条都标，要么都不标——"
          f"只标一半，剩下的等于让排版猜")
    core = [it for it in items if it["weight"] == "core"]
    _need(core, f"第{i}页没有一条是 core：全标 support 等于没有主次，去掉 weight 就是等权版式")
    _need(len(core) < len(items), f"第{i}页 {len(items)} 条全是 core：没有一条退后，主次无从读起")
    _need(len(core) <= 2, f"第{i}页有 {len(core)} 条 core，最多 2 条：三条都要紧，就是都不要紧")


def _norm_op(raw: str) -> str | None:
    s = raw.strip().replace(" ", "")
    if s in _OP_CHARS:
        return s
    if s in (">=", "=>", "＞="):
        return "≥"
    if s in ("<=", "=<", "＜="):
        return "≤"
    if s in ("＞",):
        return ">"
    if s in ("＜",):
        return "<"
    return _WORD_OP.get(s)


def _ops_in(text: str) -> set[str]:
    """Every comparison the sentence itself makes.  Longest word first, then masked, so 不超过 does not also
    report 超过 — otherwise a page could claim the inclusive boundary the sentence never wrote."""
    found = {c for c in text if c in _OP_CHARS}
    take = text
    for w in sorted(_WORD_OP, key=len, reverse=True):
        if w in take:
            found.add(_WORD_OP[w])
            take = take.replace(w, "\0" * len(w))
    return found


def _thresholds(raw, facts: Mapping[str, dict], i: int) -> list[dict]:
    """The page's boundaries, each resolved against the sentence that states it.

    An axis asserts "this measure splits at this value", so three things have to be true and all three are checked:
    the value is a number that sentence contains, the comparison is the one that sentence uses (a model may not
    widen ">" into "≥"), and the indicator names something that sentence actually talks about.  A range
    ("90%-95%") cannot be split and is refused rather than drawn as a boundary it is not.
    """
    _need(isinstance(raw, list) and raw,
          f"第{i}页要画阈值轴，须给出 thresholds（每条：indicator / op / value / fact）")
    # Two boundaries can be read as a figure.  Three or four of different units are a list drawn as stripes: the
    # page stops being about a division and becomes a table nobody asked for.  A list belongs in points.
    _need(len(raw) <= 2,
          f"第{i}页有 {len(raw)} 根量规，一页最多 2 根：三根以上已经不是图，是一张表——"
          f"把多出来的分到别的页，或改用 points 逐条列出")

    out, seen = [], set()
    for k, t in enumerate(raw):
        where = f"第{i}页 thresholds[{k}]"
        _need(isinstance(t, Mapping), f"{where} 须为对象")
        fid = t.get("fact")
        _fact(fid, facts, f"{where}.fact")
        quote = facts[fid]["quote"]
        ind = _name(t.get("indicator"), f"{where}.indicator")
        _need(ind, f"{where} 须给出 indicator（这根量规量的是什么，取原句里的词）")
        _need(ind not in seen, f"{where} 的 indicator 与同页另一条重复：同一根量规不画两遍")
        _need(names(ind, quote), f"{where} 的 indicator「{ind}」在本页句子里找不到：取原句里的词")
        seen.add(ind)
        value = str(t.get("value") or "").strip()
        hit = _hit(quote, value, ind)
        _need(hit, f"{where} 的 value「{value}」不是来源句中的数字"
                   f"（可选：{'、'.join(h['token'] for h in number_occurrences(quote)) or '无'}）")
        token, clause = value, hit["clause"]
        _need(names(ind, clause), f"{where} 的 indicator「{ind}」与这个数不在一个分句：取「{clause}」里的词")

        op_raw = str(t.get("op") or "").strip()
        _need(op_raw, f"{where} 须给出 op（原文的比较符：≥ / > / ≤ / <）")
        op = _norm_op(op_raw)
        _need(op, f"{where} 的 op「{op_raw}」无法识别：用 ≥ / > / ≤ / <，或原文的「至少 / 不超过」")
        head = token[0]
        if head in _OP_CHARS:                     # the sentence prints the symbol itself
            _need(op == head, f"{where} 的 op 与原文不符：原文写的是「{head}」，方案写成「{op}」")
        else:                                     # word form: the sentence must contain a comparison to match
            seen_ops = _ops_in(clause)
            _need(seen_ops, f"{where} 的来源句没有比较符（「{clause}」），画不出阈值轴：改用文字，或换一句写明的")
            _need(op in seen_ops,
                  f"{where} 的 op「{op}」与原文不符：这一句表达的是 {'、'.join(sorted(seen_ops))}")

        numeral = token[1:].strip() if head in _OP_CHARS else token
        _need("-" not in numeral and "~" not in numeral and "至" not in numeral,
              f"{where} 的数值是一个区间（「{token}」），阈值轴只能画一个分界点：换一个确定的数，或改用 bars")
        _need(any(ch.isdigit() for ch in numeral), f"{where} 的 value「{value}」不含数字")

        _need(len(clause) <= _CLAUSE_MAX,
              f"{where} 的来源分句有 {len(clause)} 字，量规下的一行小字放不下 {_CLAUSE_MAX} 字：换一句更短的")
        # The number and its unit are one measurement but two typographic objects: the renderer sets the unit at a
        # fraction of the figure's size, so it needs them apart ("5天" → 5 + 天) while the label keeps the whole.
        unit = _unit_of(numeral)
        digits = numeral[: len(numeral) - len(unit)] if unit else numeral
        out.append({"indicator": ind, "op": op, "token": token, "numeral": digits, "unit": unit,
                    "fact": fid, "clause": clause,
                    "holds": op + numeral, "other": _OP_COMPLEMENT[op] + numeral})
    return out


def _item(it, facts: Mapping[str, dict], where: str, structure: str, max_chars: int | None = None) -> dict:
    """One point: a required short label, and the sentence(s) that state it.

    Two things are refused here rather than after rendering: a single sentence that opens with a pronoun (it would
    read as a fragment on the slide — cite the sentence before it too), and a point longer than its column holds.
    """
    _need(isinstance(it, Mapping), f"{where} 须为对象")
    ids = it.get("facts") or ([it["fact"]] if it.get("fact") else [])
    _need(isinstance(ids, list) and ids, f"{where} 须给出 facts（句子 id）")
    label = _label(it.get("label"), f"{where}.label", _ITEM_LABEL_MAX)
    _need(label, f"{where} 须给出 label（这一条的小标题，读者先看它）")
    parts = [_fact(x, facts, where) for x in ids]
    quote = "".join(x["quote"] for x in parts)
    if len(parts) == 1:
        _need(not context_dependent(quote),
              f"{where} 的句子以指代开头，单独一页读不懂（「{quote[:16]}…」）：把上一句一并引用，或换一句自带主语的")
    limit = max_chars or _ITEM_MAX[structure]
    _need(len(quote) <= limit,
          f"{where} 有 {len(quote)} 字，这页每栏最多放 {limit} 字：换短句，或改用别的结构")
    weight = it.get("weight")
    if weight is not None:
        _need(weight in WEIGHTS, f"{where}.weight 须为 {' / '.join(WEIGHTS)}")
    return {"label": label, "facts": [x["fact"] for x in parts], "quote": quote, "weight": weight,
            "source_id": parts[0]["source_id"], "page_id": parts[0]["page_id"],
            "units": [x["unit_id"] for x in parts]}


def _name(v, where: str) -> str | None:
    """A name quoted from a sentence: only its shape is checked here, the caller finds it in the sentence."""
    if v is None:
        return None
    _need(isinstance(v, str) and v.strip() and "\n" not in v, f"{where} 须为一行文字")
    _need(len(v.strip()) <= _INDICATOR_MAX, f"{where} 超过 {_INDICATOR_MAX} 字")
    return v.strip()


def _label(v, where: str, limit: int) -> str | None:
    """Organising text: the same lint every authored label gets.  It names; it states nothing."""
    if v is None:
        return None
    _need(isinstance(v, str) and v.strip() and "\n" not in v, f"{where} 须为一行文字")
    _need(len(v.strip()) <= limit, f"{where} 超过 {limit} 字")
    bad = lint_text(v.strip())
    _need(not bad, f"{where} 是组织文字，只命名不陈述：{'；'.join(bad)}")
    return v.strip()


def _labels(v, structure: str, i: int) -> list[str] | None:
    """Two sides of a comparison need names; a point set does not."""
    if v is None:
        return None
    _need(structure == "compare", f"第{i}页只有 compare 有 labels")
    _need(isinstance(v, list) and len(v) == 2, f"第{i}页 labels 须为两项")
    return [_label(x, f"第{i}页 labels[{k}]", 14) for k, x in enumerate(v)]


def contract(n: int = 8) -> dict:
    """What a model writing this needs to see: the forms it may ask for, and one page per structure.

    ``forms`` is the menu with its requirement; ``figures`` is what a page's picture may be made of.  A model picks
    a form because the page's argument needs it; the code then checks the requirement against the sentences.
    ``materials(fact_ids, facts)`` is the other half of that conversation — it lists the numbers, time points,
    thresholds and conditions the sentences actually hold, so the model can choose a form the material can carry
    instead of guessing.  ``roles`` and ``weights`` are the two dials for hierarchy: whether the page may breathe,
    and which points lead.
    """
    title = {"fact": "", "show": ""}
    point = {"fact": "", "label": ""}
    gauge = {"indicator": "", "op": "", "value": "", "fact": ""}
    pages = [
        {"id": "p1", "structure": "stat", "role": "hero", "section": "", "headline": title,
         "lead": {"value": "", "label": "", "from": ""}, "items": [point], "takeaway": {"fact": ""}},
        {"id": "p2", "structure": "points", "headline": title, "items": [point for _ in range(3)]},
        {"id": "p3", "structure": "compare", "headline": title,
         "items": [point for _ in range(4)], "labels": ["", ""]},
        {"id": "p4", "structure": "steps", "headline": title, "items": [point for _ in range(3)]},
        # One part, shorthand: the one-word way to say "this page is a boundary".
        {"id": "p5", "structure": "stat", "form": "threshold", "headline": title, "thresholds": [gauge]},
        # Composed: a boundary over a set of bars.  indicator is a word of the sentence; base names the denominator
        # of a percentage.
        {"id": "p6", "structure": "stat", "headline": title, "figure": [
            {"kind": "split", "thresholds": [gauge]},
            {"kind": "bars", "label": "", "series": [{"indicator": "", "value": "", "fact": "", "base": ""}
                                                     for _ in range(2)]}]},
        # Emphasis: two of four points carry the page, the rest support them.
        {"id": "p7", "structure": "points", "headline": title,
         "items": [{**point, "weight": "core"}, {**point, "weight": "support"}, {**point, "weight": "support"}]},
        # A synthesis across sentences is allowed, and stays off the slide until a person confirms it.
        {"id": "p8", "structure": "points", "headline": {"derived": "", "from": [""]}, "items": [point for _ in range(3)]},
    ]
    return {"schema_version": SCHEMA, "forms": FORMS, "figures": FIGURES,
            "roles": list(ROLES), "weights": list(WEIGHTS), "pages": pages[:n]}
