"""TOPIC_PASS (``topic_pass.v2``): inside one topic of the semantic map, the model decides what matters and how it
connects; code checks that every reference is real and that nothing was dropped without a reason.

The model reads every code-cut sentence of the topic (``factdeck.auto_claims``) and writes:

- ``question``: what the topic answers;
- ``messages``: each a role — core / support / limit (taught on the pages) or reserve (kept for the speaker notes and
  for reference, not on a page) — an authored one-line ``label`` that organises but carries no numbers, and the
  sentence ids that state it;
- ``relations`` between messages (sequence / contrast / condition / evidence) with the sentence ids they rest on;
- ``page_plan``: the taught messages on each page, in speaking order (the page budget is applied later, in DECK);
- ``checks``: sentences whose data the model could not verify or read with confidence — kept for review, never
  silently dropped;
- ``left_out``: sentences not used at all, each entry a typed reason (``why``) and a note;
- ``gaps``: what the audience will ask that the material does not answer.

Deciding what matters is separate from what fits on the slides: material that is relevant but does not fit goes to
a reserve message, not to ``left_out``.

Code holds principles, not limits on how the judgment is written (2026-10-28, user decision). It refuses what breaks
source accuracy: an unknown id; a sentence the customer excluded; an authored label carrying data (digits); a
sentence or table row that silently disappears (neither cited, checked nor left out — including a sentence another
topic referred here); a claim in the result that is not true (a ``duplicate`` whose ``same_as`` is not cited, an
``other_topic`` naming no other topic); a result that contradicts itself (a taught message not placed exactly once).
How carefully the omissions were judged is the reviewer's question: large entries, omitted sentences carrying numbers,
one off-topic note reused across many sentences and the page count against the budget are reported as signals.
"""
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping

from .auto_claims import row_key
from .lexicon import canon

SCHEMA = "topic_pass.v2"
ROLES = ("core", "support", "limit", "reserve")
TAUGHT = ("core", "support", "limit")
RELATIONS = ("sequence", "contrast", "condition", "evidence")
WHY = {"duplicate": "与已引用的句子重复（same_as 写那句的 id）",
       "administrative": "版权、审批号、联系方式、讲者声明、目录与页码等行政或版式信息",
       "other_topic": "属于另一个主题（topic 写主题 id）",
       "customer_decision": "客户的资料处理决定排除了它，但代码排除规则没有覆盖（decision 写是哪条决定）",
       "off_topic": "与本主题和本课受众无关（note 写明为什么）"}
ACCOUNTED = ("sentence", "cell")     # kinds that must be cited, checked or left out; cells are accounted per table row
REVIEW_ENTRY = 8                      # a left_out entry or an off-topic note covering more is shown to review
SHARED_WHY = ("administrative", "other_topic", "customer_decision", "duplicate")   # categories: one reason fits many
_SUFFIX = re.compile(r"[（(][^（）()]*[）)]\s*$|[\s:：,，;；-]*[A-Za-z0-9]+[:：~][A-Za-z0-9:~._-]+\s*$")
_DIGITS = re.compile(r"[0-9０-９]")
_ID = re.compile(r"^(?P<unit>.+)~(?P<n>\d+)$")


class TopicPassError(ValueError):
    pass


def _need(cond, msg):
    if not cond:
        raise TopicPassError(msg)


def _ids(value, where) -> list[str]:
    _need(isinstance(value, list) and all(isinstance(x, str) and x for x in value), f"{where} 须为句子 id 列表")
    return value


def key_of(c: dict) -> str:
    """What is accounted for: a sentence on its own, a table cell through its row."""
    return (row_key(c["unit_id"]) if c["kind"] == "cell" else None) or c["id"]


def expand(r: Mapping, known: Mapping[str, dict]) -> list[str]:
    """A left_out entry as sentence ids: {"from": "U~3", "to": "U~9"} within one unit, {"ids": [...]}, or
    {"row": "<table row>"} for every cell of a table row."""
    if "ids" in r:
        ids = _ids(r["ids"], "left_out.ids")
        bad = [x for x in ids if x not in known]
        _need(not bad, "left_out 中有不存在的句子：" + "、".join(bad[:8]))
        return ids
    if "row" in r:
        ids = [k for k, c in known.items() if row_key(c["unit_id"]) == r["row"]]
        _need(ids, f"left_out 的 row 不是本资料中的表格行：{r['row']}")
        return ids
    a, b = _ID.match(str(r.get("from", ""))), _ID.match(str(r.get("to", "")))
    _need(a and b and a["unit"] == b["unit"] and int(a["n"]) <= int(b["n"]),
          f"left_out 范围须为同一单元内的 from/to 句子 id（如 U~3 到 U~9）：{r.get('from')} → {r.get('to')}")
    ids = [f"{a['unit']}~{n}" for n in range(int(a["n"]), int(b["n"]) + 1)]
    _need(ids[0] in known and ids[-1] in known, f"left_out 范围的端点不存在：{r.get('from')} → {r.get('to')}")
    return [x for x in ids if x in known]


def check(result: Mapping, topic_id: str, claims: Mapping[str, dict], pages: int | None = None,
          topics: set[str] | frozenset[str] = frozenset(), referred: Mapping[str, str] | None = None) -> dict:
    """Validate a topic pass against all claims (id → claim; the topic's own carry ``topic == topic_id``).
    ``referred`` (sentence id → topic) holds sentences other topics left out as belonging here: they are accounted for
    like this topic's own and may not be sent on as other_topic. Returns the accepted record with its review signals."""
    _need(isinstance(result, Mapping), "结果须为对象")
    _need(result.get("schema_version") == SCHEMA, f"schema_version 须为 {SCHEMA}")
    _need(result.get("topic") == topic_id, f"topic 须为 {topic_id}")
    q = result.get("question")
    _need(isinstance(q, str) and q.strip() and "\n" not in q, "question 须为一句话")
    referred = dict(referred or {})
    own = {k: c for k, c in claims.items() if c.get("topic") == topic_id or k in referred}

    def usable(ids, where):
        bad = [x for x in ids if x not in claims]
        _need(not bad, f"{where} 引用了不存在的句子：" + "、".join(bad[:8]))
        out = [x for x in ids if claims[x]["kind"] == "excluded"]
        _need(not out, f"{where} 引用了按客户决定排除的句子：" + "、".join(f"{x}（{claims[x].get('excluded_by', '')}）" for x in out[:5]))

    msgs = result.get("messages")
    _need(isinstance(msgs, list) and msgs, "messages 不能为空")
    seen, cited, borrowed = {}, set(), []
    for m in msgs:
        _need(isinstance(m, Mapping), "每条 message 须为对象")
        mid = m.get("id")
        _need(isinstance(mid, str) and mid and mid not in seen, f"message id 缺失或重复：{mid}")
        _need(m.get("role") in ROLES, f"{mid} 的 role 须为 {' / '.join(ROLES)}")
        label = m.get("label")
        _need(isinstance(label, str) and label.strip() and "\n" not in label, f"{mid} 的 label 须为一行文字")
        _need(not _DIGITS.search(label), f"{mid} 的 label 是组织文字，不能写数字：{label}")
        ids = _ids(m.get("claims"), f"{mid}.claims")
        _need(ids, f"{mid} 没有引用任何句子")
        usable(ids, mid)
        borrowed += [x for x in ids if x not in own]
        cited |= set(ids)
        seen[mid] = m
    _need(any(m["role"] == "core" for m in msgs), "至少要有一条 core 信息")

    rels, authored, based = result.get("relations") or [], [], set()
    _need(isinstance(rels, list), "relations 须为列表")
    for i, r in enumerate(rels, 1):
        _need(isinstance(r, Mapping) and r.get("type") in RELATIONS, f"第{i}条关系的 type 须为 {' / '.join(RELATIONS)}")
        ends = [r.get("from")] + list(r.get("to") or [])
        _need(len(ends) >= 2 and all(e in seen for e in ends), f"第{i}条关系的 from/to 须为已列出的 message id")
        basis = _ids(r.get("basis") or [], f"第{i}条关系的 basis")
        usable(basis, f"第{i}条关系")
        based |= set(basis)
        sources_of = lambda mid: {claims[x]["source_id"] for x in seen[mid]["claims"]}
        basis_src = {claims[x]["source_id"] for x in basis}
        if not basis or any(not (sources_of(e) & basis_src) for e in ends):
            authored.append(i)                   # the connection is the author's: no basis, or none from both ends

    plan = result.get("page_plan")
    _need(isinstance(plan, list) and plan and all(isinstance(p, list) and p for p in plan), "page_plan 须为非空的页列表")
    placed = [x for p in plan for x in p]
    taught = [k for k, m in seen.items() if m["role"] in TAUGHT]
    _need(sorted(placed) == sorted(taught), "page_plan 须把每条 core / support / limit 信息恰好放一次；reserve 信息不放进 page_plan")

    checked = set()
    for i, c in enumerate(result.get("checks") or [], 1):
        _need(isinstance(c, Mapping) and str(c.get("reason", "")).strip(), f"第{i}条 checks 须写明 reason（哪里拿不准）")
        ids = _ids(c.get("claims"), f"第{i}条 checks")
        usable(ids, f"第{i}条 checks")
        checked |= set(ids)

    left, left_out, per_note, other_topic, large, numeric_grouped = set(), [], defaultdict(list), [], [], []
    for i, r in enumerate(result.get("left_out") or [], 1):
        _need(isinstance(r, Mapping), f"第{i}条 left_out 须为对象")
        why, note = r.get("why"), str(r.get("note", "")).strip()
        _need(why in WHY, f"第{i}条 left_out 的 why 须为 {' / '.join(WHY)}")
        _need(note, f"第{i}条 left_out 须在 note 中写明具体原因")
        ids = expand(r, own)
        keys = {key_of(own[x]) for x in ids if own[x]["kind"] in ACCOUNTED}
        if len(keys) > REVIEW_ENTRY:
            large.append(i)
        if len(keys) > 1 and why not in SHARED_WHY:
            numeric_grouped += [x for x in ids if own[x]["kind"] in ACCOUNTED and own[x].get("numbers")]
        if why not in SHARED_WHY:                # an off-topic judgement is about the sentence; a shared one is shown to review
            per_note[canon(_SUFFIX.sub("", note)) or canon(note)] += list(keys)
        if why == "customer_decision":
            _need(str(r.get("decision", "")).strip(), f"第{i}条 left_out 为 customer_decision，decision 须写明是哪条客户决定")
        if why == "duplicate":
            same = r.get("same_as")
            _need(same in cited, f"第{i}条 left_out 为 duplicate，same_as 须是本结果中已引用的句子 id")
        if why == "other_topic":
            _need(r.get("topic") in topics and r.get("topic") != topic_id, f"第{i}条 left_out 为 other_topic，topic 须是另一个主题的 id")
            other_topic += [(x, r["topic"]) for x in ids]
        left |= set(ids)
        left_out.append({**{k: r[k] for k in ("from", "to", "ids", "row", "same_as", "topic", "decision") if k in r},
                         "why": why, "note": note, "n": len(keys)})

    done = cited | checked | left
    accounted = {key_of(c) for k, c in own.items() if k in done and c["kind"] in ACCOUNTED}
    missing = sorted({key_of(c) for c in own.values() if c["kind"] in ACCOUNTED} - accounted)
    _need(not missing, f"本主题有 {len(missing)} 句/表格行既没有引用、没有列入 checks、也没有列入 left_out：" + "、".join(missing[:10]))

    gaps = result.get("gaps") or []
    _need(isinstance(gaps, list) and all(isinstance(g, str) for g in gaps), "gaps 须为文字列表")
    signals = {
        "left_out_with_numbers": sorted(k for k in left - cited - checked if own[k].get("numbers")),
        "left_out_with_qualifiers": sorted(k for k in left - cited - checked if own[k].get("qualifiers")),
        "checks": sorted(checked),
        "authored_relations": authored,
        "borrowed_claims": sorted(set(borrowed) - set(referred)),
        "referred_in": sorted(referred),
        "other_topic": other_topic,
        "customer_decision": sorted(x for e in left_out if e["why"] == "customer_decision" for x in expand(e, own)),
        "large_left_out_entries": large,
        "numeric_left_out_in_groups": sorted(numeric_grouped),
        "shared_off_topic_notes": sorted(len(v) for v in per_note.values() if len(v) > REVIEW_ENTRY),
        "pages_vs_budget": [len(plan), pages],
    }
    n_keys = len({key_of(c) for c in own.values() if c["kind"] in ACCOUNTED})
    return {"schema_version": SCHEMA, "topic": topic_id, "question": q, "messages": [dict(m) for m in msgs],
            "relations": [dict(r) for r in rels], "page_plan": plan,
            "checks": [dict(c) for c in result.get("checks") or []], "left_out": left_out, "gaps": list(gaps),
            "signals": signals, "referenced": sorted(cited | based | checked | left), "counts": {"accounted": n_keys, "cited": len(cited), "checked": len(checked),
                                           "left_out": len(left - cited - checked)}}


def contract(topic_id: str) -> dict:
    return {"schema_version": SCHEMA, "topic": topic_id, "question": "",
            "messages": [{"id": "m1", "role": "core", "label": "", "claims": []}],
            "relations": [{"type": "sequence", "from": "m1", "to": [], "basis": []}],
            "page_plan": [["m1"]], "checks": [{"claims": [], "reason": ""}],
            "left_out": [{"ids": [], "why": "administrative", "note": ""}], "gaps": []}
