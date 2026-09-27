"""Fact store: every medical statement on a slide must come from here.

A fact is proposed (by a model or a person) as a *quote* inside a source unit.
Code — not the model — decides whether it is accepted:

* the quote must exist verbatim (whitespace-insensitive) in that unit;
* the text shown on the slide (`display`) may be shorter than the quote, but every
  critical token in it (numbers with their comparison operator and unit, drug
  names, molecular targets, scale names) must occur as a token in the quote;
  anything else needs an explicit, named derivation that a human confirms;
* facts that describe the same entity/attribute with different values across
  sources become conflicts for a human to resolve;
* uncertainty (image transcription, chart read-outs, column mapping) is carried
  forward as `needs_confirmation` and shown on the slide until confirmed.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .sources import normalize

# ---- critical tokens -------------------------------------------------------

DRUGS = ["奥马珠单抗", "美泊利珠单抗", "本瑞利珠单抗", "度普利尤单抗", "特泽利尤单抗", "德莫奇单抗",
         "司普奇拜单抗", "瑞加瑞珠单抗"]
_OP = r"[≥≤<>＜＞]"
_NUM = r"\d+(?:[.,]\d+)*"
_UNIT = r"(?:%|mg|mL|ml|ppb|/μL|/µL|/μl|cells/μL|周|个月|岁|倍|元|针|年|mL)?"
_NUM_RE = re.compile(rf"({_OP}\s*)?({_NUM})(?:\s*[-~～–]\s*({_NUM}))?\s*({_UNIT})")
_TARGET_RE = re.compile(r"IL-?\d+R?α?|IgE|TSLP|FeNO|ACQ-?\d|ACT|FEV1|EOS|OCS|ICS-?LABA|Q\d+W|Q\d+M")


def _canon(text: str) -> str:
    t = text.replace("＜", "<").replace("＞", ">").replace("‑", "-").replace("–", "-").replace("～", "~")
    t = t.replace("µ", "μ").replace("IL‑", "IL-")
    return normalize(t)


def critical_tokens(text: str) -> set[str]:
    t = _canon(text)
    t = re.sub(r"(\d)%\s*([-~])\s*(\d)", r"\1\2\3", t)   # 44%~48% == 44~48%
    tokens: set[str] = set()
    for m in _NUM_RE.finditer(t):
        op, a, b, unit = m.group(1) or "", m.group(2).replace(",", ""), m.group(3), m.group(4) or ""
        op = op.strip()
        unit = unit.lower().replace("/μl", "/μl").replace("cells", "")
        tokens.add(f"{op}{a}" + (f"-{b.replace(',', '')}" if b else "") + unit)
    for d in DRUGS:
        if d in t:
            tokens.add(d)
    for m in _TARGET_RE.finditer(t):
        tokens.add(m.group(0).replace("-", ""))
    return tokens


# ---- data model ------------------------------------------------------------

@dataclass
class Fact:
    id: str
    unit: str
    quote: str
    display: str = ""
    entity: str = ""          # e.g. drug name, used for conflict detection
    attribute: str = ""       # e.g. "单价(元/支)"
    value: str = ""
    derivation: str = ""      # id of a derivation that justifies display/entity beyond the quote
    note: str = ""
    # filled by verification
    status: str = "PENDING"   # ACCEPTED | REJECTED
    needs_confirmation: bool = False
    problems: list[str] = field(default_factory=list)
    location: str = ""
    source_id: str = ""

    def text(self) -> str:
        return self.display or self.quote


@dataclass
class Derivation:
    id: str
    claim: str
    rule: str
    evidence: list[str]
    confirmed: bool = False
    problems: list[str] = field(default_factory=list)


@dataclass
class Conflict:
    entity: str
    attribute: str
    values: dict[str, list[str]]   # value -> fact ids
    resolution: str = ""           # fact id chosen by a human, or "" while open


def load(path: Path) -> tuple[list[Fact], list[Derivation], dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    facts = [Fact(**f) for f in raw["facts"]]
    ders = [Derivation(**d) for d in raw.get("derivations", [])]
    return facts, ders, raw.get("resolutions", {})


def verify(facts: list[Fact], ders: list[Derivation], units: list[dict], resolutions: dict):
    by_unit = {u["id"]: u for u in units}
    by_fact = {f.id: f for f in facts}
    by_der = {d.id: d for d in ders}

    for f in facts:
        u = by_unit.get(f.unit)
        if not u:
            f.status, f.problems = "REJECTED", [f"来源单元不存在：{f.unit}"]
            continue
        f.location, f.source_id = u["location"], u["source_id"]
        if _canon(f.quote) not in _canon(u["text"]) and _canon(f.quote) not in _canon(u.get("alt_text", "")):
            f.status, f.problems = "REJECTED", ["引文在来源单元中不存在（不是逐字引用）"]
            continue
        f.needs_confirmation = bool(u.get("needs_confirmation"))
        if f.needs_confirmation:
            f.problems.append("来源为图片转录，尚无第二次独立读取")
        f_ders = [by_der[x] for x in f.derivation.split(",") if x in by_der]
        for x in f.derivation.split(","):
            if x and x not in by_der:
                f.problems.append(f"引用了不存在的推导：{x}")
        extra = critical_tokens(f.text()) - critical_tokens(f.quote)
        if extra:
            d = next((x for x in f_ders if x.id == "footnote" or x.rule.startswith("去掉")), None) if f_ders else None
            if not d:
                f.status = "REJECTED"
                f.problems.append("显示文字含引文中没有的关键项：" + "、".join(sorted(extra)))
                continue
            f.problems.append(f"显示文字经推导“{d.rule}”得到：" + "、".join(sorted(extra)))
            if not d.confirmed:
                f.needs_confirmation = True
        pending = [d.id for d in f_ders if not d.confirmed]
        if pending:
            f.needs_confirmation = True
            f.problems.append("依赖待确认的推导：" + "、".join(pending))
        f.status = "ACCEPTED"

    for d in ders:
        missing = [e for e in d.evidence if e not in by_fact or by_fact[e].status != "ACCEPTED"]
        if missing:
            d.problems.append("证据事实缺失或未通过：" + "、".join(missing))

    conflicts: list[Conflict] = []
    groups: dict[tuple[str, str], dict[str, list[str]]] = {}
    for f in facts:
        if f.status == "ACCEPTED" and f.entity and f.attribute and f.value:
            groups.setdefault((f.entity, f.attribute), {}).setdefault(_canon(f.value).replace(",", ""), []).append(f.id)
    for (entity, attr), values in groups.items():
        if len(values) > 1:
            c = Conflict(entity, attr, values, resolutions.get(f"{entity}|{attr}", ""))
            conflicts.append(c)
            if not c.resolution:
                for ids in values.values():
                    for fid in ids:
                        by_fact[fid].needs_confirmation = True
                        by_fact[fid].problems.append(f"来源之间不一致：{entity}·{attr}")
    return conflicts


def report(facts, ders, conflicts, sources: list[dict]) -> str:
    title = {s["id"]: s["title"] for s in sources}
    lines = ["# 事实库核对报告", ""]
    acc = [f for f in facts if f.status == "ACCEPTED"]
    rej = [f for f in facts if f.status == "REJECTED"]
    conf = [f for f in acc if f.needs_confirmation]
    lines += [f"- 事实 {len(facts)} 条：通过 {len(acc)}，拒绝 {len(rej)}，通过但需人工确认 {len(conf)}",
              f"- 推导 {len(ders)} 条：已确认 {sum(d.confirmed for d in ders)}",
              f"- 来源冲突 {len(conflicts)} 处：未解决 {sum(1 for c in conflicts if not c.resolution)}", ""]
    if rej:
        lines += ["## 被拒绝的事实", ""]
        for f in rej:
            lines.append(f"- `{f.id}` {f.text()} — {'；'.join(f.problems)}")
        lines.append("")
    if conflicts:
        lines += ["## 来源冲突（须人工选择）", ""]
        for c in conflicts:
            lines.append(f"- **{c.entity} · {c.attribute}**" + ("（已解决）" if c.resolution else "（未解决）"))
            for v, ids in c.values.items():
                locs = "；".join(f"{title.get(next(x for x in facts if x.id == i).source_id, '')} {next(x for x in facts if x.id == i).location}" for i in ids)
                lines.append(f"  - {v}：{locs}")
        lines.append("")
    if ders:
        lines += ["## 推导（非逐字，须人工确认）", ""]
        for d in ders:
            lines.append(f"- `{d.id}` {d.claim} — 规则：{d.rule}；证据：{', '.join(d.evidence)}"
                         + ("" if not d.problems else f"；问题：{'；'.join(d.problems)}")
                         + ("（已确认）" if d.confirmed else "（待确认）"))
        lines.append("")
    if conf:
        lines += ["## 需人工确认的事实", ""]
        for f in conf:
            why = "；".join(f.problems)
            lines.append(f"- `{f.id}` {f.text()} — {title.get(f.source_id, '')} {f.location}：{why}")
    return "\n".join(lines) + "\n"


def dump(facts, ders, conflicts, path: Path):
    path.write_text(json.dumps({"facts": [asdict(f) for f in facts], "derivations": [asdict(d) for d in ders],
                                "conflicts": [asdict(c) for c in conflicts]}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
