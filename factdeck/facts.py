"""Fact store: every substantive statement on a slide must come from here.

A fact is proposed (by a model or a person) as a *quote* inside a source unit.
Code — not the model — decides whether it is accepted:

* the quote must exist verbatim (whitespace/width-insensitive) in that unit;
* the text shown on the slide (`display`) must be made of pieces of the quote, in
  order (extractive compression). Dropping a negation or qualifier, rewording, or
  showing a critical token (number+operator+unit, technical token, project term)
  that is not in the quote needs an explicit, named derivation that a person
  confirms; until then the fact is shown as pending;
* facts that give the same entity/attribute different values across sources become
  conflicts for a person to resolve;
* uncertainty in the unit itself (image transcription without an agreeing second
  read) is carried forward as `needs_confirmation`.

A *figure fact* shows a picture taken from an original (`figure` = figure id)
instead of a quote. Its state (checksum, crop/de-identification review, licence,
transcription of text inside the picture) is decided by the caller and passed in
as `figures`; `caption` lists ordinary facts shown under the picture.

Confirmation state (derivations, conflict resolutions) is passed in by the caller;
a `confirmed` flag written by the proposer is ignored.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .lexicon import canon, critical_tokens, extractive, dropped_blockers


@dataclass
class Fact:
    id: str
    unit: str = ""
    quote: str = ""
    display: str = ""
    entity: str = ""          # e.g. drug or study name, used for conflict detection
    attribute: str = ""       # e.g. "单价(元/支)"
    value: str = ""
    derivation: str = ""      # comma-separated ids of derivations that justify display beyond the quote
    note: str = ""
    section_ids: list[str] = field(default_factory=list)   # summary sections this fact belongs to
    figure: str = ""          # figure id: this fact shows a source picture instead of a quote
    caption: list[str] = field(default_factory=list)       # facts shown under the picture
    # filled by verification
    status: str = "PENDING"   # ACCEPTED | REJECTED
    needs_confirmation: bool = False
    problems: list[str] = field(default_factory=list)
    dropped: str = ""         # text of the quote that the display leaves out (for semantic review)
    location: str = ""
    source_id: str = ""

    def text(self) -> str:
        return self.display or self.quote or (f"〔图〕{self.location or self.figure}" if self.figure else "")


@dataclass
class Derivation:
    id: str
    claim: str
    rule: str
    evidence: list[str]
    kind: str = "rewrite"     # rewrite | mapping | footnote | unit_conversion
    confirmed: bool = False
    rejected: bool = False    # a reviewer decided the derivation does not hold
    problems: list[str] = field(default_factory=list)


@dataclass
class Conflict:
    entity: str
    attribute: str
    values: dict[str, list[str]]   # value -> fact ids
    resolution: str = ""           # fact id chosen by a person, or "" while open

    @property
    def key(self) -> str:
        return f"{self.entity}|{self.attribute}"


FACT_FIELDS = {f for f in Fact.__dataclass_fields__} - {"status", "needs_confirmation", "problems", "dropped", "location", "source_id"}
DER_FIELDS = {"id", "claim", "rule", "evidence", "kind"}


def parse(raw: dict) -> tuple[list[Fact], list[Derivation], list[dict]]:
    """Proposed fact store → objects. Unknown keys are dropped; proposer's `confirmed` is ignored."""
    facts = [Fact(**{k: v for k, v in f.items() if k in FACT_FIELDS}) for f in raw.get("facts", [])]
    ders = [Derivation(**{k: v for k, v in d.items() if k in DER_FIELDS}) for d in raw.get("derivations", [])]
    return facts, ders, list(raw.get("terms", []))


def load(path: Path) -> tuple[list[Fact], list[Derivation], dict]:
    """CLI helper: a facts.json with inline `confirmed` flags and `resolutions`, edited by a person."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    facts, ders, _ = parse(raw)
    confirmed = {d["id"] for d in raw.get("derivations", []) if d.get("confirmed")}
    for d in ders:
        d.confirmed = d.id in confirmed
    return facts, ders, raw.get("resolutions", {})


def _verify_figure(f: Fact, figures: dict):
    """figures[id] = {source_id, location, pending: [reasons], rejected: [reasons]} (decided by the caller)."""
    if f.unit or f.quote or f.display or f.derivation:
        f.status, f.problems = "REJECTED", ["图事实只引用图，不能同时带引文、显示文字或推导"]
        return
    g = figures.get(f.figure)
    if not g:
        f.status, f.problems = "REJECTED", [f"图不存在：{f.figure}"]
        return
    f.location, f.source_id = g["location"], g["source_id"]
    if g.get("rejected"):
        f.status, f.problems = "REJECTED", list(g["rejected"])
        return
    if g.get("pending"):
        f.needs_confirmation = True
        f.problems += list(g["pending"])
    f.status = "ACCEPTED"


def verify(facts: list[Fact], ders: list[Derivation], units: list[dict], resolutions: dict,
           terms: list[str] | tuple[str, ...] = (), figures: dict | None = None) -> list[Conflict]:
    by_unit = {u["id"]: u for u in units}
    by_fact = {f.id: f for f in facts}
    by_der = {d.id: d for d in ders}
    terms = tuple(terms)
    seen: set[str] = set()

    for f in facts:
        f.status, f.problems, f.needs_confirmation, f.dropped = "PENDING", [], False, ""
        if not f.id or f.id in seen:
            f.status, f.problems = "REJECTED", ["事实编号为空或重复"]
            continue
        seen.add(f.id)
        if f.figure:
            _verify_figure(f, figures or {})
            continue
        if f.caption:
            f.status, f.problems = "REJECTED", ["只有图事实可以带图注（caption）"]
            continue
        u = by_unit.get(f.unit)
        if not u:
            f.status, f.problems = "REJECTED", [f"来源单元不存在：{f.unit}"]
            continue
        f.location, f.source_id = u["location"], u["source_id"]
        if not canon(f.quote) or (canon(f.quote) not in canon(u["text"]) and canon(f.quote) not in canon(u.get("alt_text", ""))):
            f.status, f.problems = "REJECTED", ["引文在来源单元中不存在（不是逐字引用）"]
            continue
        if u.get("needs_confirmation"):
            f.needs_confirmation = True
            f.problems.append(u.get("confirmation_reason") or "来源为图片/图表转录，尚无一致的第二次独立读取")
        f_ders = []
        for x in [x.strip() for x in f.derivation.split(",") if x.strip()]:
            if x in by_der:
                f_ders.append(by_der[x])
            else:
                f.problems.append(f"引用了不存在的推导：{x}")
        dead = [d.id for d in f_ders if d.rejected]
        if dead:
            f.status = "REJECTED"
            f.problems.append("依赖的推导已被审核人否定：" + "、".join(dead))
            continue
        extra = critical_tokens(f.text(), terms) - critical_tokens(f.quote, terms)
        ok, dropped = extractive(f.text(), f.quote) if f.display else (True, "")
        blockers = dropped_blockers(dropped) if ok else []
        f.dropped = dropped if ok else ""
        rewritten = not ok or bool(blockers)
        if extra or rewritten:
            if not f_ders:
                f.status = "REJECTED"
                if extra:
                    f.problems.append("显示文字含引文中没有的关键项：" + "、".join(sorted(x.replace("term:", "") for x in extra)))
                if not ok:
                    f.problems.append("显示文字不是引文的逐字节选（改写需命名推导并经人工确认）")
                if blockers:
                    f.problems.append("显示文字删去了否定/限定词：" + "、".join(blockers))
                continue
            f.problems.append("显示文字经推导得到：" + "；".join(d.rule for d in f_ders))
        pending = [d.id for d in f_ders if not d.confirmed]
        if pending:
            f.needs_confirmation = True
            f.problems.append("依赖待确认的推导：" + "、".join(pending))
        f.status = "ACCEPTED"

    for d in ders:
        d.problems = []
        missing = [e for e in d.evidence if e not in by_fact or by_fact[e].status != "ACCEPTED"]
        if not d.evidence or missing:
            d.problems.append("证据事实缺失或未通过：" + ("、".join(missing) or "未列出证据"))

    conflicts: list[Conflict] = []
    groups: dict[tuple[str, str], dict[str, list[str]]] = {}
    for f in facts:
        if f.status == "ACCEPTED" and not f.figure and f.entity and f.attribute and f.value:
            groups.setdefault((f.entity, f.attribute), {}).setdefault(canon(f.value).replace(",", ""), []).append(f.id)
    for (entity, attr), values in groups.items():
        if len(values) > 1:
            chosen = resolutions.get(f"{entity}|{attr}", "")
            if chosen and not any(chosen in ids for ids in values.values()):
                chosen = ""
            c = Conflict(entity, attr, values, chosen)
            conflicts.append(c)
            for ids in values.values():
                for fid in ids:
                    fact = by_fact[fid]
                    if not c.resolution:
                        fact.needs_confirmation = True
                        fact.problems.append(f"来源之间不一致：{entity}·{attr}")
                    elif fid not in next(v for v in values.values() if c.resolution in v):
                        fact.status = "REJECTED"
                        fact.problems.append(f"来源冲突已裁定采用 {c.resolution}，本条不再使用")
    for f in facts:                       # captions: ordinary accepted facts, checked after conflicts are settled
        if f.figure and f.status == "ACCEPTED":
            bad = [c for c in f.caption if c not in by_fact or by_fact[c].figure or by_fact[c].status != "ACCEPTED"]
            if bad:
                f.status = "REJECTED"
                f.problems.append("图注须为已通过的文字事实：" + "、".join(bad))

    return conflicts


def report(facts, ders, conflicts, sources: list[dict]) -> str:
    title = {s["id"]: s.get("title") or s.get("filename", s["id"]) for s in sources}
    by_id = {f.id: f for f in facts}
    lines = ["# 事实库核对报告", ""]
    acc = [f for f in facts if f.status == "ACCEPTED"]
    rej = [f for f in facts if f.status == "REJECTED"]
    conf = [f for f in acc if f.needs_confirmation]
    lines += [f"- 事实 {len(facts)} 条：通过 {len(acc)}，拒绝 {len(rej)}，通过但需人工确认 {len(conf)}",
              f"- 推导 {len(ders)} 条：已确认 {sum(d.confirmed for d in ders)}",
              f"- 来源冲突 {len(conflicts)} 处：未解决 {sum(1 for c in conflicts if not c.resolution)}", ""]
    if rej:
        lines += ["## 被拒绝的事实", ""]
        lines += [f"- `{f.id}` {f.text()} — {'；'.join(f.problems)}" for f in rej]
        lines.append("")
    if conflicts:
        lines += ["## 来源冲突（须人工选择）", ""]
        for c in conflicts:
            lines.append(f"- **{c.entity} · {c.attribute}**" + (f"（已采用 {c.resolution}）" if c.resolution else "（未解决）"))
            for v, ids in c.values.items():
                locs = "；".join(f"`{i}` {title.get(by_id[i].source_id, '')} {by_id[i].location}" for i in ids)
                lines.append(f"  - {v}：{locs}")
        lines.append("")
    if ders:
        lines += ["## 推导（非逐字，须人工确认）", ""]
        for d in ders:
            lines.append(f"- `{d.id}` {d.claim} — 规则：{d.rule}；证据：{', '.join(d.evidence)}"
                         + ("" if not d.problems else f"；问题：{'；'.join(d.problems)}")
                         + ("（已确认）" if d.confirmed else "（已否定）" if d.rejected else "（待确认）"))
        lines.append("")
    if conf:
        lines += ["## 需人工确认的事实", ""]
        lines += [f"- `{f.id}` {f.text()} — {title.get(f.source_id, '')} {f.location}：{'；'.join(f.problems)}" for f in conf]
    return "\n".join(lines) + "\n"


def as_dict(facts, ders, conflicts) -> dict:
    return {"facts": [asdict(f) for f in facts], "derivations": [asdict(d) for d in ders],
            "conflicts": [{**asdict(c), "key": c.key} for c in conflicts]}


def dump(facts, ders, conflicts, path: Path):
    path.write_text(json.dumps(as_dict(facts, ders, conflicts), ensure_ascii=False, indent=1), encoding="utf-8")
