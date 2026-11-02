"""Facts → assertions → pages → native PPTX, with no generator in the loop.

This is the smallest thing that proves the chain: every shown string is a reference (``shown``), every page is
checked as part of a partition of the assertions (``argument``), each page is laid out by code at a fixed
geometry, and ``designed.export`` measures it, audits it and writes native PPTX.  It is deliberately not a
designer — a text page is a title plus its evidence — because the point here is that nothing states what its
sentence does not.

The plan is one file: pages, each with a title and the evidence under it, all of them references.  The claims are
derived from the pages rather than written twice, so the assertion list and the deck cannot drift apart.

A derivation waits for a person: unconfirmed ones are reported in ``pending`` and their page is not drawn.
``--confirm-all`` signs every digest in the run, which is how the export path was exercised before a review UI
exists.  It is not how a deck should ship.
"""
from __future__ import annotations

import html as _html
import json
import sys
from pathlib import Path

from . import argument, designed, shown
from .assets import Manifest, styles

PAD, CONTENT_W = 64, 1152
TITLE_TOP, TITLE_SIZE = 64, 40
BODY_BOTTOM, BODY_SIZE = 660, 24
TITLE_CHARS, TITLE_LINE = 28, 56     # full-width characters per title line at 40px, and its leading
BODY_CHARS, BODY_LINE = 48, 34       # the same for a body line at 24px

def _lines(text: str, per: int) -> int:
    return max(1, -(-len(text) // per))


def _tops(lines: list[dict], title: str) -> list[int]:
    """Place the evidence so the empty bands are equal, and none of them grows past what the rules allow.

    The band the rules measure starts at the title's last line, which depends on how the title wraps, and ends at
    the bottom of the content area.  Both are computed here from the same arithmetic the browser will use, so a
    page does not have to be drawn before it can be laid out.  A page with one line cannot fill the band: such a
    page is a hero, or it needs more evidence.
    """
    if not lines:
        return []
    hs = [BODY_LINE * _lines(x["text"], BODY_CHARS) for x in lines]
    top0 = TITLE_TOP + TITLE_LINE * _lines(title, TITLE_CHARS)
    gap = max(16, (BODY_BOTTOM - top0 - sum(hs)) / (len(lines) + 1))
    tops, at = [], top0
    for h in hs:
        at += gap
        tops.append(round(at))
        at += h
    return tops


def _attr(text: str) -> str:
    return _html.escape(text, quote=True)


def _show(show: str | None) -> str:
    return f' data-show="{_attr(show)}"' if show else ""


def _span(line: dict, facts: dict, tier: str, top: int, size: int, did: str) -> str:
    """One text box holding one reference.  A derivation stays empty until the exporter fills it in by its id."""
    if line["kind"] == "derivation":
        inner = f'<span data-derived="{did}"></span>'
    else:
        fid = line["facts"][0]
        whole = facts[fid]["quote"]
        inner = f'<span data-fact="{fid}"{_show(None if line["text"] == whole else line["text"])}></span>'
    weight = ";font-weight:700" if tier == "title" else ""
    return (f'<div data-t data-tier="{tier}" style="position:absolute;left:{PAD}px;top:{top}px;'
            f'width:{CONTENT_W}px;font-size:{size}px;line-height:1.4{weight}">{inner}</div>')


def page_of(pid: str, title: dict, points: list[dict], facts: dict, role: str = "supporting") -> dict:
    """One resolved page → a designed.v1 page.  Positions from code, content from references."""
    out = {"id": pid, "role": role, "derived": {}, "html": "",
           "design": {"figure": "designed"}}
    blocks = [_span(title, facts, "title", TITLE_TOP, TITLE_SIZE, "d0")]
    if title["kind"] == "derivation":
        out["derived"]["d0"] = {"text": title["text"], "from": title["facts"]}
    for pt, top in zip(points, _tops(points, title["text"])):
        blocks.append(_span(pt, facts, "body", top, BODY_SIZE, f"d{top}"))
        if pt["kind"] == "derivation":
            out["derived"][f"d{top}"] = {"text": pt["text"], "from": pt["facts"]}
    out["html"] = "".join(blocks)
    return out


def _refs(plan: dict) -> tuple[list[dict], list[dict]]:
    """The plan's titles as the assertion list, plus the page→assertion map.

    Only titles are assertions.  Evidence under a title is not a judgement — it is the sentence the judgement
    rests on — so it is resolved by ``shown`` (the same gate) but not held to the title's two-line length.
    """
    claims, pages = [], []
    for p in plan["pages"]:
        cid = f'{p["id"]}.t'
        claims.append({"id": cid, "say": p["say"]})
        pages.append({"id": p["id"], "covers": [cid]})
    return claims, pages


def run(plan_path: Path | str, facts_path: Path | str, out: Path | str, *, confirmed=(), shots=None,
        note: str = "") -> dict:
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    facts = {f["id"]: f for f in json.loads(Path(facts_path).read_text(encoding="utf-8"))["facts"]}
    style = styles()["clinical_blue"]

    claims, pages_meta = _refs(plan)
    checked = argument.check({"schema_version": argument.SCHEMA, "claims": claims}, facts, confirmed)
    judgements = argument.partition(pages_meta, checked["claims"])
    by_id = {c["id"]: c for c in checked["claims"]}

    prepared, pending, refused = [], list(checked["pending"]), []
    for p in plan["pages"]:
        title = by_id.get(f'{p["id"]}.t')
        if title is None or title["pending"]:
            continue
        pts = []
        for k, ref in enumerate(p.get("points") or []):
            try:
                got = shown.resolve(ref, facts, f'页面 {p["id"]} 第{k + 1} 条证据', confirmed)
            except shown.ShownError as e:
                refused.append({"page": p["id"], "why": str(e)})
                continue
            if got["pending"]:
                pending.append({"page": p["id"], "text": got["text"], "from": got["facts"], "digest": got["digest"]})
                continue
            pts.append(got)
        prepared.append(page_of(p["id"], title, pts, facts, p.get("role") or "supporting"))

    built = designed.export(prepared, facts, Manifest(Path(out).parent / "assets"), style, out,
                            source=plan.get("source") or "GOLD 2026", confirmed=confirmed, shots=shots, note=note)
    return {"claims": len(checked["claims"]), "judgements": judgements, "prepared": len(prepared),
            "planned": len(plan["pages"]), "pending": pending, "refused": refused,
            "pages": built["pages"], "pptx": built["pptx"], "ok": built["ok"]}


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="facts → assertions → pages → native PPTX")
    ap.add_argument("plan")
    ap.add_argument("--facts", default="output/gold2026_deck/facts_verified.json")
    ap.add_argument("--out", default="output/argument_run/deck.pptx")
    ap.add_argument("--shots")
    ap.add_argument("--confirm-all", action="store_true", help="sign every digest in the plan (testing only)")
    a = ap.parse_args(argv)

    plan = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    facts = {f["id"]: f for f in json.loads(Path(a.facts).read_text(encoding="utf-8"))["facts"]}
    confirmed = set()
    if a.confirm_all:
        for p in plan["pages"]:
            for ref in [p["say"], *(p.get("points") or [])]:
                if "derived" in ref:
                    confirmed.add(shown.digest(ref["derived"], ref["from"], facts))

    note = ("测试运行：全部综合句由 --confirm-all 统一签署，未经逐条人工核对；本报告不代表其中任何一句已被核对。"
            if a.confirm_all else "")
    res = run(a.plan, a.facts, a.out, confirmed=confirmed, shots=a.shots, note=note)
    print(f"断言 {res['claims']} 条 → 判断 {res['judgements']} 页；可画 {res['prepared']}/{res['planned']} 页；"
          f"待确认 {len(res['pending'])} 处")
    for row in res["pages"]:
        if row["errors"]:
            print(f'  {row["page"]}  ' + "；".join(row["errors"][:3]))
    print("PPTX：", res["pptx"] or "未写出")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
