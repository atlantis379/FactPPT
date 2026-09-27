"""Deck specification checks.

Pages reference facts by id. Text written by the model (titles, leads, labels) is
allowed only if it carries no medical content of its own: no numbers (Arabic or
Chinese with a measure word), no comparison operators, no drug names and no
molecular targets — except glossary terms that are themselves backed by a fact.
Every arrow in a diagram must name the fact that supports it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .facts import critical_tokens, DRUGS

CN_NUM = re.compile(r"[一二三四五六七八九十两百千万几半]+\s*(?:种|个|项|条|次|倍|年|月|周|天|成|组|类|期|例|针|剂|支|岁|分)")
OPS = re.compile(r"[≥≤<>＜＞%％]")


def walk(node, path=""):
    """Yield (path, kind, value) for every fact reference and authored text in a page."""
    if isinstance(node, dict):
        if "fact" in node and len(node) == 1:
            yield path, "fact", node["fact"]
            return
        if "text" in node and len(node) == 1:
            yield path, "text", node["text"]
            return
        for k, v in node.items():
            if k in ("id", "layout", "art", "widths", "edges"):
                continue
            if k == "columns":
                for i, c in enumerate(v):
                    yield f"{path}.columns[{i}]", "text", c
                continue
            yield from walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")


def lint_text(text: str, terms: list[str]) -> list[str]:
    t = text
    for term in sorted(terms, key=len, reverse=True):
        t = t.replace(term, "")
    problems = []
    toks = critical_tokens(t)
    if toks:
        problems.append("作者文字含关键项：" + "、".join(sorted(toks)))
    if CN_NUM.search(t):
        problems.append("作者文字含中文数量词：" + CN_NUM.search(t).group(0))
    if OPS.search(t):
        problems.append("作者文字含比较符号或百分号")
    for d in DRUGS:
        if d in t:
            problems.append("作者文字含药名：" + d)
    return problems


def check(deck: dict, facts: dict[str, dict]) -> dict:
    terms = [x["text"] for x in deck.get("terms", [])]
    result = {"pages": [], "errors": 0, "pending": 0}
    for term in deck.get("terms", []):
        f = facts.get(term["fact"])
        if not f or f["status"] != "ACCEPTED" or term["text"] not in f["quote"].replace(" ", ""):
            result["errors"] += 1
            result.setdefault("term_errors", []).append(term)
    for page in deck["pages"]:
        errors, pending, used = [], [], []
        for path, kind, value in walk(page):
            if kind == "text":
                for p in lint_text(value, terms):
                    errors.append(f"{path} “{value}”：{p}")
            else:
                f = facts.get(value)
                if not f:
                    errors.append(f"{path} 引用了不存在的事实 {value}")
                elif f["status"] != "ACCEPTED":
                    errors.append(f"{path} 引用了被拒绝的事实 {value}：{'；'.join(f['problems'])}")
                else:
                    used.append(value)
                    if f["needs_confirmation"]:
                        pending.append(value)
        for a, b, support in page.get("edges", []):
            if support not in used:
                errors.append(f"箭头 {a}→{b} 的支持事实 {support} 未在本页引用或未通过")
        result["pages"].append({"id": page["id"], "facts": sorted(set(used)), "pending": sorted(set(pending)),
                                "errors": errors})
        result["errors"] += len(errors)
        result["pending"] += len(set(pending))
    return result


def main(project: Path) -> dict:
    deck = json.loads((project / "deck.json").read_text(encoding="utf-8"))
    facts = {f["id"]: f for f in json.loads((project / "facts_verified.json").read_text(encoding="utf-8"))["facts"]}
    res = check(deck, facts)
    (project / "deck_check.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


if __name__ == "__main__":
    import sys
    r = main(Path(sys.argv[1]))
    for p in r["pages"]:
        print(f"{p['id']:10s} 事实{len(p['facts']):3d}  待确认{len(p['pending']):3d}  错误{len(p['errors'])}")
        for e in p["errors"]:
            print("    ✗", e)
    print("总错误", r["errors"])
