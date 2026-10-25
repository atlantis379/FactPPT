"""Bind a template-library fill to the fact store and trace every shown word and drawn number to its source.

A *bound fill* has the shape of an ordinary slot fill (see manifest.json), except that every shown string is a
reference, the same convention FactDeck deck pages use::

    {"fact": "<fact id>"}      a verbatim fact; shown as its `display` (or `quote`)
    {"text": "<label>"}        authored text: organises and names only (lexicon.lint_text: no numbers, drug /
                               entity names, comparisons or evaluative wording)

Other leaves:

* numbers (bar values, estimates, CIs, weeks, years) are drawn as geometry; each must occur as a number in a fact
  shown in the same fill ("geometry follows facts").  Scale frames (`axis`, `year_start`, `year_end`, `today`)
  are exempt.
* enum / id keys (`kind`, `role`, `status`, …) take short ASCII codes.
* footer and chrome (`page`, `figure`, `data_note`, `source`, `refs`, evidence `quote` / `loc`) are written by
  code from the facts used; a fill that writes them is refused.

`resolve()` returns the plain fill the renderer takes, a trace record per slot, the facts used, and errors.
Nothing here edits or completes content: an unbacked number or a raw string is an error, never a guess.
"""
from __future__ import annotations

import re
from typing import Any

from ..lexicon import canon, lint_text
from . import pharma
from . import slots as slotmod

BOUND_NOTE = "逐字引自原文，溯源见备注"
CODE_KEYS = {"id", "kind", "role", "mark", "status", "key", "target", "variant", "theme"}
CODE_WRITTEN = {"page", "figure", "data_note", "source", "refs", "loc", "quote", "head_quote", "number"}  # number: section ordinal
FRAME_KEYS = {"axis", "year_start", "year_end", "today"}
CODE_VALUE = re.compile(r"[A-Za-z0-9_-]{1,24}")
MAX_REFS = 4                                   # footer capacity of the pharma families
_NUM = re.compile(r"(?<![\d.])([-−]?)(\d+(?:\.\d+)?)")


def numbers_in(text: str) -> set[float]:
    """Numbers a fact's text states, under canon matching ("1 100" → 1100, "0.70" → 0.7, "−30%" → -30).
    A minus counts as a sign only when it does not join a range ("57–107" is 57 and 107)."""
    t = canon(text).replace(",", "")
    out = set()
    for m in _NUM.finditer(t):
        sign, v = m.group(1), float(m.group(2))
        if sign and m.start() > 0 and t[m.start() - 1].isdigit():
            sign = ""
        out.add(-v if sign else v)
    return out


def shown_text(f: dict) -> str:
    return str(f.get("display") or f.get("quote") or "")


PEER_NAME = re.compile(r"(fill\.\w+)\[\d+\]\.(heading|label)")    # the name slot of an item in a list slot

def _is_fact_ref(node: Any) -> bool:
    return isinstance(node, dict) and isinstance(node.get("fact"), str) and set(node) <= {"fact", "emph"}


def _is_text_ref(node: Any) -> bool:
    return isinstance(node, dict) and set(node) == {"text"} and isinstance(node["text"], str)


def ref_view(fill: Any, path: str = "fill") -> dict[str, dict]:
    """Every reference in a bound fill, flat by slot path (for deck.check's fact / authored-text walk)."""
    out: dict[str, dict] = {}
    if _is_fact_ref(fill) or _is_text_ref(fill):
        out[path] = fill
    elif isinstance(fill, dict):
        for k, v in fill.items():
            if k not in CODE_KEYS | CODE_WRITTEN | FRAME_KEYS:
                out.update(ref_view(v, f"{path}.{k}"))
    elif isinstance(fill, list):
        for i, v in enumerate(fill):
            out.update(ref_view(v, f"{path}[{i}]"))
    return out


class _Binder:
    def __init__(self, facts: dict[str, dict], glossary, terms):
        self.facts, self.glossary, self.terms = facts, list(glossary), list(terms)
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.trace: list[dict] = []
        self.used: list[str] = []
        self.numbers: list[tuple[str, float, list[str]]] = []      # (path, value, fact ids of the enclosing item)

    def fact(self, path: str, node: dict) -> str | None:
        fid = node["fact"]
        f = self.facts.get(fid)
        if "emph" in node:
            self.errors.append(f"{path}：模板页暂不支持强调片段（emph），请去掉")
        if not f:
            self.errors.append(f"{path} 引用了不存在的事实 {fid}")
            return None
        if f.get("figure"):
            self.errors.append(f"{path}：模板页没有原件图位置，不能放图事实 {fid}")
            return None
        if f.get("status") != "ACCEPTED":
            self.errors.append(f"{path} 引用了未通过的事实 {fid}：{'；'.join(f.get('problems') or []) or f.get('status')}")
            return None
        self.used.append(fid)
        text = shown_text(f)
        self.trace.append({"slot": path, "kind": "fact", "text": text, "fact": fid, "quote": f.get("quote", ""),
                           "unit": f.get("unit", ""), "source_id": f.get("source_id") or str(f.get("unit", "")).split(":")[0],
                           "location": f.get("location", ""), "needs_confirmation": bool(f.get("needs_confirmation"))})
        return text

    def text(self, path: str, value: str) -> str:
        if not str(value).strip():                     # a blank label pads a slot (an empty column, a filler card)
            self.errors.append(f"{path}：作者文字为空——不要用空文字占位；该格没有内容就删去这一项（或这一列）")
        for p in lint_text(value, self.glossary, self.terms):
            self.errors.append(f"{path} “{value}”：{p}")
        self.trace.append({"slot": path, "kind": "authored", "text": value})
        return value

    def walk(self, node: Any, path: str, key: str | None, item_facts: list[str]) -> Any:
        if _is_fact_ref(node):
            return self.fact(path, node)
        if _is_text_ref(node):
            return self.text(path, node["text"])
        if key in FRAME_KEYS:
            return node
        if isinstance(node, bool) or node is None:
            return node
        if isinstance(node, (int, float)):
            self.numbers.append((path, float(node), item_facts))
            return node
        if isinstance(node, str):
            if key in CODE_KEYS:
                if not CODE_VALUE.fullmatch(node):
                    self.errors.append(f"{path}：{key} 只能是简短代码（字母、数字、-、_），收到“{node}”")
                return node
            self.errors.append(f"{path} 需写成 {{\"fact\": 编号}} 或 {{\"text\": 作者文字}}，收到原样文字“{node[:30]}”")
            return None
        if isinstance(node, list):
            return [self.walk(v, f"{path}[{i}]", key, item_facts) for i, v in enumerate(node)]
        if isinstance(node, dict):
            local = [r["fact"] for r in ref_view(node).values() if "fact" in r]   # facts of this item (a row, a series)
            out = {}
            for k, v in node.items():
                if k in CODE_WRITTEN:
                    self.errors.append(f"{path}.{k}：页码、图号、数据说明、来源、证据号与摘录由代码写入，填充中不要写")
                    continue
                out[k] = self.walk(v, f"{path}.{k}", k, local or item_facts)
            return out
        self.errors.append(f"{path}：无法识别的值 {node!r}")
        return None

    def check_peer_names(self) -> None:
        """Peer items (cards, nodes, rows) named by one and the same authored label say nothing about each item."""
        groups: dict[str, dict[str, int]] = {}
        for t in self.trace:
            m = PEER_NAME.fullmatch(t["slot"]) if t["kind"] == "authored" else None
            if m:
                g = groups.setdefault(m[1] + "[]." + m[2], {})
                g[t["text"]] = g.get(t["text"], 0) + 1
        for slot, names in groups.items():
            for name, n in names.items():
                if n > 1:
                    self.errors.append(f"{slot}：{n} 项同名“{name}”——同一组的每项名称须说明该项自己的内容（或引用事实）")

    def check_numbers(self) -> None:
        page = {fid: numbers_in(shown_text(self.facts[fid])) for fid in dict.fromkeys(self.used)}
        for path, v, local in self.numbers:
            backing = [fid for fid, nums in page.items() if any(abs(v - n) < 1e-9 for n in nums)]
            if not backing:
                self.errors.append(f"{path}：图上画出的数值 {v:g} 不在本页任何事实中（图形须由本页显示的事实支撑）")
                continue
            local_numeric = [fid for fid in local if page.get(fid)]
            if local_numeric and not set(backing) & set(local_numeric):
                self.warnings.append(f"{path}：数值 {v:g} 出现在本页事实 {'、'.join(backing)}，但不在同一行/系列的事实中，请核对")
            self.trace.append({"slot": path, "kind": "number", "value": v, "backed_by": backing})


def _sources_of(trace: list[dict], prefix: str | None = None) -> list[str]:
    out: list[str] = []
    for t in trace:
        if t["kind"] == "fact" and (prefix is None or t["slot"].startswith(prefix)) and t["source_id"] not in out:
            out.append(t["source_id"])
    return out


def _fit(s: str, n: int) -> str:
    return s if len(s) <= n else s[: max(n - 1, 0)] + "…"


def _write_chrome(family: str, variant: str | None, fill: dict, trace: list[dict], sources: dict[str, str],
                  page_no: int | None, errors: list[str], section_no: int | None = None) -> None:
    """Footer and chrome from the facts used: data note, numbered source list (page `refs` + item superscripts) or a
    one-line `source`, evidence quote / location, figure number."""
    spec = slotmod.family_spec(family)
    slots = spec.get("slots") or {}
    used = _sources_of(trace)
    label = lambda sid: sources.get(sid) or sid                                  # noqa: E731
    if "data_note" in slots:
        fill["data_note"] = BOUND_NOTE
    if "figure" in slots:
        fill["figure"] = f"图 {page_no}" if page_no is not None else "图"
    if family == "section" and section_no is not None:
        fill["number"] = str(section_no)
    if "refs" in slots:
        if len(used) > MAX_REFS:
            errors.append(f"本页引用了 {len(used)} 个来源，页脚至多 {MAX_REFS} 个，请拆页")
        rule = (slots["refs"].get("item") or {}).get("text") or {}
        fill["refs"] = [{"id": str(i + 1), "text": _fit(label(sid), int(rule.get("max_chars") or 120))}
                        for i, sid in enumerate(used[:MAX_REFS])]
        num = {sid: str(i + 1) for i, sid in enumerate(used)}
        list_key = "items" if family == "key_points" else "takeaways"
        for i, it in enumerate(fill.get(list_key) or []):
            if isinstance(it, dict):
                it["refs"] = [num[s] for s in _sources_of(trace, f"fill.{list_key}[{i}].")]
    elif "source" in slots:
        rule = slots["source"]
        names = [label(s) for s in used]
        line = "来源：" + "；".join(names)
        n = int(rule.get("max_chars") or 80)
        fill["source"] = line if len(line) <= n else _fit("来源：" + names[0], n - 6) + f" 等 {len(names)} 份"
    if family == "key_points" and variant == pharma.EVIDENCE_VARIANT:
        item = spec.get("evidence_takeaways", {}).get("item", {})
        for i, it in enumerate(fill.get("items") or []):
            src = [t for t in trace if t["kind"] == "fact" and t["slot"].startswith(f"fill.items[{i}].text")]
            if isinstance(it, dict) and src:
                t = src[0]
                it["quote"] = _fit(f"“{t['quote']}”", int(item.get("quote", {}).get("max_chars") or 90))
                it["loc"] = _fit(" · ".join(x for x in (label(t["source_id"]), t["location"]) if x),
                                 int(item.get("loc", {}).get("max_chars") or 30))


def resolve(family: str, variant: str | None, fill: dict, facts: dict[str, dict], *, title: Any = None,
            sources: dict[str, str] | None = None, glossary=(), terms=(), page_no: int | None = None,
            page_checks: bool = True, section_no: int | None = None) -> dict:
    """Bound fill → {fill (plain, for the renderer), trace, facts, errors, warnings, pending}.

    `title` (a reference) is the page title, shown in the fill's title slot; a fill may instead carry its own."""
    b = _Binder(facts, glossary, terms)
    src = dict(fill)
    if title is not None:
        src["title"] = title
    plain = b.walk(src, "fill", None, [])
    b.check_numbers()
    b.check_peer_names()
    if page_checks:                                    # off when deck.check runs them on the whole page itself
        if not b.used and family not in ("cover", "section"):
            b.errors.append("内容页至少要引用一条事实")
        from ..deck import context_errors              # deck.py imports this package lazily; no cycle at load
        b.errors += context_errors(b.used, facts)
    if not b.errors:
        _write_chrome(family, variant, plain, b.trace, sources or {}, page_no, b.errors, section_no)
    return {"fill": plain, "trace": b.trace, "facts": sorted(set(b.used)), "errors": b.errors,
            "warnings": b.warnings, "pending": sorted({t["fact"] for t in b.trace if t.get("needs_confirmation")})}


def trace_markdown(pages: list[dict], *, title: str = "溯源报告", sources: dict[str, str] | None = None) -> str:
    """One section per page: every shown slot with its fact, source and location; every drawn number with the facts
    that state it.  `pages`: [{page_no, page_id, layout, bound, trace, errors?}]."""
    sources = sources or {}
    lines = [f"# {title}", ""]
    for p in pages:
        lines.append(f"## 第 {p['page_no']} 页 · {p['page_id']} · {p.get('layout') or ''}")
        if not p.get("bound"):
            lines += ["", "未绑定事实库：本页内容为示例数据，未溯源。", ""]
            continue
        if p.get("errors"):
            lines += ["", "未渲染：" + "；".join(p["errors"]), ""]
            continue
        tr = p.get("trace") or []
        facts = [t for t in tr if t["kind"] == "fact"]
        nums = [t for t in tr if t["kind"] == "number"]
        authored = [t for t in tr if t["kind"] == "authored"]
        lines += ["", f"事实 {len(facts)} 处 · 作者标签 {len(authored)} 处 · 图形数值 {len(nums)} 个（均有事实支撑）", "",
                  "| 位置 | 显示文字 | 事实 | 来源 | 原文位置 |", "|---|---|---|---|---|"]
        for t in facts:
            cell = lambda s: str(s).replace("|", "\\|").replace("\n", " ")                  # noqa: E731
            lines.append(f"| {t['slot'][5:]} | {cell(t['text'])} | {t['fact']}{'（待确认）' if t['needs_confirmation'] else ''} "
                         f"| {cell(sources.get(t['source_id']) or t['source_id'])} | {cell(t['location'] or t['unit'])} |")
        for t in authored:
            lines.append(f"| {t['slot'][5:]} | {t['text']} | 作者标签 | — | — |")
        for t in nums:
            lines.append(f"| {t['slot'][5:]} | 数值 {t['value']:g} | {'、'.join(t['backed_by'])} | — | — |")
        lines.append("")
    return "\n".join(lines)


def notes_lines(trace: list[dict], sources: dict[str, str] | None = None) -> list[str]:
    """Speaker-notes lines: each fact shown on the slide → source · location."""
    sources = sources or {}
    out = []
    for t in trace:
        if t["kind"] == "fact":
            out.append(f"【溯源】{t['fact']}：{sources.get(t['source_id']) or t['source_id']} · "
                       f"{t['location'] or t['unit']}")
    return list(dict.fromkeys(out))
