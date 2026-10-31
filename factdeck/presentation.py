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

_HEADLINE_MAX = 60
_LABEL_MAX = 18
_TAKEAWAY_MAX = 52
_ITEM_LABEL_MAX = 14

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

        items = p.get("items")
        _need(isinstance(items, list), f"第{i}页 items 须为列表")
        _need(lo <= len(items) <= hi, f"第{i}页（{st}）的 items 须为 {lo}–{hi} 条，现有 {len(items)} 条")
        resolved = [_item(it, facts, f"第{i}页 items[{k}]", st) for k, it in enumerate(items)]
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

        # the lead is its own content slot, so its sentence counts as cited on this page
        lead = None
        if needs_lead:
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

        out.append({"id": pid, "structure": st, "headline": headline, "lead": lead, "items": resolved,
                    "takeaway": resolved_take,
                    "section": _label(p.get("section"), f"第{i}页 section", 16),
                    "labels": side_labels,
                    "span": None if p.get("span") is None else [str(x) for x in p["span"]]})
    return {"schema_version": SCHEMA, "pages": out}


def _item(it, facts: Mapping[str, dict], where: str, structure: str) -> dict:
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
    _need(len(quote) <= _ITEM_MAX[structure],
          f"{where} 有 {len(quote)} 字，{structure} 的每栏最多放 {_ITEM_MAX[structure]} 字：换短句，或改用别的结构")
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
    """What a model writing this needs to see: one page per structure, with the fields each one requires."""
    return {
        "schema_version": SCHEMA,
        "pages": [
            {"id": "p1", "structure": "stat", "headline": "", "lead": {"value": "", "label": "", "from": ""},
             "items": [{"fact": ""}], "takeaway": {"fact": ""}},
            {"id": "p2", "structure": "points", "headline": "", "items": [{"fact": ""} for _ in range(3)]},
            {"id": "p3", "structure": "compare", "headline": "", "items": [{"fact": ""} for _ in range(4)]},
            {"id": "p4", "structure": "steps", "headline": "", "items": [{"fact": ""} for _ in range(3)]},
        ][:n],
    }
