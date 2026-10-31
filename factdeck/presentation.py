"""Presentation spec (``presentation.v1``): the model decides how a page is shown, code only checks the data.

The model reads the draft (each topic's messages and the verbatim sentences behind them) and answers, page by page:
what is this page's structure, which sentence leads, which number carries the page, what is the takeaway.  It never
writes displayed text: every content slot points at a sentence id and the code puts that sentence's own words there.
What the model may write is organising text — the headline and short labels — and those are checked against the
sentences on the page, so a number in a headline has to exist in the material.

Why this exists: a fixed template with fixed slots can only show what fits its slots.  Pages whose material is
richer (200+ characters, a comparison, a number worth a whole page) were being squeezed into four equal cards.
Structure is a judgement about the material, so it belongs to the model; verbatim accuracy is a fact, so it stays
with the code.

Four structures to start (coarse on purpose — see ``STRUCTURES``); each maps to one parametric HTML layout rendered
to native shapes by ``factdeck.template_lib.native``.  Nothing here draws a picture or invents a coordinate.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from .lexicon import critical_tokens, number_spans

SCHEMA = "presentation.v1"

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
    "bars": "≥2 个可比数值，且来自 ≥2 句（同一量纲：百分比 / 倍数 / 例数）",
    "trend": "≥3 个不同的时间量（周 / 月 / 年），可连成一条线",
    "threshold": "≥1 个带比较符或「至少 / 超过 / 不超过」的阈值",
    "steps": "≥3 条要点，构成先后顺序",
    "compare": "两侧各有名字，且两侧都有句子",
    "decision": "≥1 个条件句（若…则… / 在…情况下 / 对于…）",
}

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

_HEADLINE_MAX = 60
_LABEL_MAX = 18
_TAKEAWAY_MAX = 52
_ITEM_LABEL_MAX = 14
_INDICATOR_MAX = 14
_CLAUSE_MAX = 30      # one line of small print under a gauge

# A point has to stay readable in the column it lands in: three lines at the widest, and every structure has its
# own column width.  Checking this here means a sentence that cannot fit is refused before anything is drawn,
# instead of being found by looking at a picture afterwards.
_ITEM_MAX = {"stat": 74, "points": 86, "compare": 62, "steps": 40, "threshold": 58}

# A sentence that opens with a pronoun needs the one before it; alone on a slide it reads as a fragment
# ("这些国家中超过90%-95%的病例未被确诊" — which countries?).  Either the model cites the sentence before it too,
# or it picks another sentence.
_CTX_OPEN = re.compile(r"^(这|该|其|此|上述|前述|以上)")
_CTX_PHRASE = ("这些国家", "该国", "该组", "上述患者", "这些患者", "前者", "后者", "该研究", "该队列", "同上")


def context_dependent(text: str) -> bool:
    """Does this sentence only make sense with the one before it?"""
    t = text.strip()
    return bool(_CTX_OPEN.match(t)) or any(p in t for p in _CTX_PHRASE)


_UNIT_SUFFIX = tuple(sorted({"%", "倍", "例", "人", "次", "天", "周", "个月", "月", "年", "小时", "分钟", "分",
                             "级", "岁", "mg/L", "细胞/微升", "μL", "mL", "/分"}, key=len, reverse=True))


def _unit_of(token: str) -> str:
    for u in _UNIT_SUFFIX:
        if token.endswith(u):
            return u
    return ""


def materials(fact_ids, facts: Mapping[str, dict]) -> dict:
    """What shapes these sentences actually contain — what a page's form has to be chosen from.

    A model cannot judge 'this page should be a trend line' without knowing whether the sentences hold time points.
    This is that inventory: the numbers, the ones in time units, the ones that are thresholds, the units that have two
    or more values to compare, and the sentences that state a condition.
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


def form_supported(form: str, mat: dict, items=None, labels=None) -> tuple[bool, str]:
    """Can the material on this page carry that form?  Returns (ok, what is missing or the nearest form that fits)."""
    ok = _form_fits(form, mat, items, labels)
    if ok:
        return True, ""
    fits = [f for f in ("compare", "bars", "threshold", "steps", "decision")
            if f != form and _form_fits(f, mat, items, labels)]
    why = _FORM_WHY.get(form, "未知形式")
    if form == "trend":
        why = f"只有 {len({x['token'] for x in mat['timeline']})} 个时间量，连不成线（需要 ≥3 个不同的时点）"
    return False, f"{why}。按现有原料可以改画：{'、'.join(fits[:3]) or '文字'}"


_FORM_WHY = {
    "bars": "没有两项以上可比的同量纲数值（百分比 / 倍数 / 例数）",
    "threshold": "没有带比较符或「至少 / 不超过」这类阈值的数值",
    "steps": "要点少于 3 条，构不成步骤",
    "compare": "对照需要两侧各有名字，且两侧都有句子",
    "decision": "没有条件句（若…则… / 对于…）",
}


def _form_fits(form: str, mat: dict, items=None, labels=None) -> bool:
    if form == "text":
        return True
    if form == "bars":
        return bool(mat["comparable"])
    if form == "trend":
        return len({x["token"] for x in mat["timeline"]}) >= 3
    if form == "threshold":
        return bool(mat["thresholds"])
    if form == "steps":
        return bool(items) and len(items) >= 3
    if form == "compare":
        return bool(labels) and len(labels) == 2 and bool(items) and len(items) >= 2
    if form == "decision":
        return bool(mat["conditions"])
    return False


def shares_with(label: str, text: str) -> bool:
    """Does `text` name the thing `label` names?  Two-character overlap on a short label is enough evidence that a
    point belongs to that side of a comparison; no overlap at all means the page would assert an attribution the
    sentence does not make."""
    grams = {label[i:i + 2] for i in range(len(label) - 1)}
    return any(g in text for g in grams)


class PresentationError(ValueError):
    """The spec would show something the material does not support."""


def _need(cond, msg: str) -> None:
    if not cond:
        raise PresentationError(msg)


def _digits(text: str) -> set[str]:
    """Digits a reader would take as data (70%, 5-10%, 1.5倍) — Chinese numerals are prose, not data."""
    return {t for t in critical_tokens(text) if re.search(r"\d", t)}


def _page_tokens(fact_ids, facts: Mapping[str, dict]) -> set[str]:
    out: set[str] = set()
    for fid in fact_ids:
        for sp in number_spans(facts[fid]["quote"]):
            out.add(sp["token"])
    return out


def _fact(fid, facts: Mapping[str, dict], where: str) -> dict:
    _need(isinstance(fid, str) and fid in facts, f"{where} 引用了不存在的句子：{fid}")
    f = facts[fid]
    return {"fact": fid, "quote": f["quote"], "source_id": f.get("source_id"),
            "page_id": f.get("page_id") or f.get("location"), "unit_id": f.get("unit_id") or f.get("unit")}


def check(spec: Mapping, facts: Mapping[str, dict]) -> dict:
    """Validate a presentation against the draft's sentences. Returns the normalised spec with sentences resolved.

    Refused: an unknown structure; a page whose slot counts fall outside the structure; a sentence that is not in the
    draft; a lead value that is not one of the numbers in the sentence it names; a headline carrying a number the
    page's own sentences do not contain.  Nothing is corrected — a page that cannot be supported has to be re-decided
    by the model.
    """
    _need(isinstance(spec, Mapping), "呈现方案须为对象")
    _need(spec.get("schema_version") == SCHEMA, f"schema_version 须为 {SCHEMA}")
    pages = spec.get("pages")
    _need(isinstance(pages, list) and pages, "pages 不能为空")

    out, seen = [], set()
    for i, p in enumerate(pages, 1):
        _need(isinstance(p, Mapping), f"第{i}页须为对象")
        pid = p.get("id") or f"p{i}"
        _need(pid not in seen, f"页 id 重复：{pid}")
        seen.add(pid)
        st = p.get("structure")
        _need(st in STRUCTURES, f"第{i}页 structure 须为 {' / '.join(STRUCTURES)}")
        lo, hi, needs_lead = STRUCTURES[st]
        form = p.get("form") or "text"
        _need(form in FORMS, f"第{i}页 form 须为 {' / '.join(FORMS)}")

        items = p.get("items") or []
        _need(isinstance(items, list), f"第{i}页 items 须为列表")
        if form == "text":
            _need(lo <= len(items) <= hi, f"第{i}页（{st}）的 items 须为 {lo}–{hi} 条，现有 {len(items)} 条")
        elif form == "threshold":
            # A gauge is the page.  A point beside it competes for the same width and, at one gauge, leaves the
            # figure smaller than the text next to it: the sentence that explains a boundary belongs in takeaway,
            # or on a page of its own.
            _need(not items, f"第{i}页画阈值轴，不列 items：量规本身就是这页的内容，"
                            f"要补充的话换一句放 takeaway，或把那条要点单独做一页")
        else:                                   # the figure carries the page; a few points may annotate it
            _need(0 <= len(items) <= 3, f"第{i}页（{form}）的 items 最多 3 条点评，现有 {len(items)} 条")
        max_chars = _ITEM_MAX.get(form)
        resolved = [_item(it, facts, f"第{i}页 items[{k}]", st, max_chars) for k, it in enumerate(items)]
        labels_seen = set()
        for k, r in enumerate(resolved):
            _need(r["label"] not in labels_seen, f"第{i}页 items[{k}] 的 label 与同页其它条重复：{r['label']}")
            labels_seen.add(r["label"])

        fact_ids = [f for r in resolved for f in r["facts"]]
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

        # The figure's own sentences count as cited on this page, before the headline is checked: a headline is
        # allowed to name the boundary number, and that number comes from the gauge's sentence.
        thresholds = _thresholds(p.get("thresholds"), facts, i) if form == "threshold" else []
        fact_ids.extend(t["fact"] for t in thresholds if t["fact"] not in fact_ids)
        # A takeaway that cites the gauge's own sentence prints it twice on one slide: the gauge already shows it.
        th_facts = {t["fact"] for t in thresholds}
        if resolved_take is not None:
            _need(resolved_take["fact"] not in th_facts,
                  f"第{i}页 takeaway 与量规是同一句，等于把量规再说一遍：换一句本页小结，或留空")

        # the lead is its own content slot, so its sentence counts as cited on this page.  A page drawn as a figure
        # already puts a number at full size; a second one would compete with it.
        lead = None
        if form != "text":
            _need(not p.get("lead"),
                  f"第{i}页要画 {form}，主数字已经在图里：不要另给 lead，把那个数放进 thresholds / lead 二选一")
        elif needs_lead:
            l = p.get("lead")
            _need(isinstance(l, Mapping), f"第{i}页（{st}）须给出 lead（本页的主数字）")
            src = _fact(l.get("from"), facts, f"第{i}页 lead.from")
            fact_ids.append(src["fact"])
            value = l.get("value")
            _need(isinstance(value, str) and value.strip(), f"第{i}页 lead.value 须为文字")
            tokens = {sp["token"] for sp in number_spans(src["quote"])}
            _need(value.strip() in tokens,
                  f"第{i}页 lead.value「{value}」不是该句中的数字（可选：{'、'.join(sorted(tokens)) or '无'}）")
            label = (l.get("label") or "").strip()
            _need(label and "\n" not in label, f"第{i}页 lead.label 须为一行文字")
            _need(len(label) <= _LABEL_MAX, f"第{i}页 lead.label 超过 {_LABEL_MAX} 字")
            _need(not _digits(label), f"第{i}页 lead.label 是组织文字，数字写进 lead.value：{label}")
            lead = {"value": value.strip(), "label": label, "fact": src["fact"], "quote": src["quote"]}

        headline = p.get("headline")
        if headline is not None:
            _need(isinstance(headline, str) and headline.strip() and "\n" not in headline, f"第{i}页 headline 须为一行文字")
            headline = headline.strip()
            _need(len(headline) <= _HEADLINE_MAX, f"第{i}页 headline 超过 {_HEADLINE_MAX} 字")
            allowed = _page_tokens(fact_ids, facts)
            extra = sorted(_digits(headline) - allowed)
            _need(not extra, f"第{i}页 headline 的数字在本页句子中找不到：{'、'.join(extra)}")

        # A takeaway that repeats the number the page is already built around says nothing new either.
        _need(not (lead and resolved_take and lead["fact"] == resolved_take["fact"]),
              f"第{i}页 takeaway 与主数字是同一句，等于把标题重说一遍：换一句本页小结，或留空")

        side_labels = _labels(p.get("labels"), st, i)
        if st == "compare":
            _need(side_labels, f"第{i}页（compare）须给出 labels（左右两栏各叫什么）")
            half = (len(resolved) + 1) // 2
            for k, r in enumerate(resolved):
                side = 0 if k < half else 1
                _need(shares_with(side_labels[side], r["quote"]),
                      f"第{i}页 items[{k}] 的句子没有提到「{side_labels[side]}」，放到这一栏会替它作原文没有的归属："
                      f"换到另一栏，或换一句明确说到它的")

        # The form is the model's judgement; whether the material can carry it is the code's check.
        mat = materials(fact_ids, facts)
        ok, why = form_supported(form, mat, resolved, side_labels)
        _need(ok, f"第{i}页要画 {form}（{FORMS[form]}），但这页的原料不支持：{why}")

        out.append({"id": pid, "structure": st, "form": form, "headline": headline, "lead": lead, "items": resolved,
                    "takeaway": resolved_take,
                    "thresholds": thresholds,
                    "materials": {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in mat.items()},
                    "section": _label(p.get("section"), f"第{i}页 section", 16),
                    "labels": side_labels,
                    "span": None if p.get("span") is None else [str(x) for x in p["span"]]})
    return {"schema_version": SCHEMA, "pages": out}


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
        ind = _label(t.get("indicator"), f"{where}.indicator", _INDICATOR_MAX)
        _need(ind, f"{where} 须给出 indicator（这根量规量的是什么）")
        _need(ind not in seen, f"{where} 的 indicator 与同页另一条重复：同一根量规不画两遍")
        _need(shares_with(ind, quote),
              f"{where} 的 indicator「{ind}」在本页句子里找不到：换一个句子说得出名字的指标")
        seen.add(ind)
        spans = {sp["token"]: sp for sp in number_spans(quote)}
        value = str(t.get("value") or "").strip()
        _need(value in spans,
              f"{where} 的 value「{value}」不是来源句中的数字（可选：{'、'.join(spans) or '无'}）")
        token, clause = value, spans[value]["clause"]

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
    return {"label": label, "facts": [x["fact"] for x in parts], "quote": quote,
            "source_id": parts[0]["source_id"], "page_id": parts[0]["page_id"],
            "units": [x["unit_id"] for x in parts]}


def _label(v, where: str, limit: int) -> str | None:
    if v is None:
        return None
    _need(isinstance(v, str) and v.strip() and "\n" not in v, f"{where} 须为一行文字")
    _need(len(v.strip()) <= limit, f"{where} 超过 {limit} 字")
    _need(not _digits(v), f"{where} 是组织文字，不能写数字：{v}")
    return v.strip()


def _labels(v, structure: str, i: int) -> list[str] | None:
    """Two sides of a comparison need names; a point set does not."""
    if v is None:
        return None
    _need(structure == "compare", f"第{i}页只有 compare 有 labels")
    _need(isinstance(v, list) and len(v) == 2, f"第{i}页 labels 须为两项")
    return [_label(x, f"第{i}页 labels[{k}]", 14) for k, x in enumerate(v)]


def contract(n: int = 4) -> dict:
    """What a model writing this needs to see: the forms it may ask for, and one page per structure.

    ``forms`` is the menu with its requirement.  A model picks a form because the page's argument needs it; the
    code then checks the requirement against the sentences.  ``materials(fact_ids, facts)`` is the other half of
    that conversation — it lists the numbers, time points, thresholds and conditions the sentences actually hold,
    so the model can choose a form the material can carry instead of guessing.
    """
    pages = [
        {"id": "p1", "structure": "stat", "form": "text", "headline": "",
         "lead": {"value": "", "label": "", "from": ""}, "items": [{"fact": ""}], "takeaway": {"fact": ""}},
        {"id": "p2", "structure": "points", "form": "text", "headline": "", "items": [{"fact": ""} for _ in range(3)]},
        {"id": "p3", "structure": "compare", "form": "text", "headline": "",
         "items": [{"fact": ""} for _ in range(4)], "labels": ["", ""]},
        {"id": "p4", "structure": "steps", "form": "text", "headline": "", "items": [{"fact": ""} for _ in range(3)]},
        {"id": "p5", "structure": "stat", "form": "threshold", "headline": "",
         "thresholds": [{"indicator": "", "op": "", "value": "", "fact": ""}]},
    ]
    return {"schema_version": SCHEMA, "forms": FORMS, "pages": pages[:n]}
