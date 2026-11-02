"""Designed pages (``designed.v1``): a generator makes the page look good, code decides whether it may ship.

The generator (Codex, Gemini, any model) writes a whole 1280×720 page as HTML/CSS in the dialect of ``factdeck.free``
and places visual assets in it.  It is free in everything a reader sees as design.  It is not free in what a page
states, so three things stay out of its hands:

  words    every shown string is a reference (``factdeck.shown``) or a linted label; an asset holds no text
  numbers  a bar's length is measured against its fact, a ring is drawn by code from the fact
  logic    an arrow needs a sentence that states it (``deck.arrow_backs``)

Code checks only what it can prove and refuses the rest.  It knows nothing about any subject: what a picture depicts
is judged in ``factdeck.assets``, and a person signs it off.  The source line and page number are written by code,
so a page cannot drop them, and the deck's font comes from the style pack, so the browser and PowerPoint agree.
"""
from __future__ import annotations

import html as _html
import re
from collections.abc import Collection, Mapping
from pathlib import Path

from . import free
from .assets import Manifest
from .compose import chain_backs
from .deck import arrow_backs, emph_spans
from .lexicon import lint_text, number_occurrences
from .shown import ShownError, digest, resolve
from .template_lib import native as N
from .template_lib.measure import MEASURE_JS

SCHEMA = "designed.v1"
W, H = 1280, 720

_FRAME = """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{margin:0;font-family:{font}}}
.slide{{position:relative;width:1280px;height:720px;overflow:hidden;background:{canvas};color:{ink}}}
.body{{position:absolute;left:0;top:0;width:1280px;height:720px}}
.foot{{position:absolute;left:64px;top:670px;width:1152px;height:20px;font-size:14px;line-height:20px;color:{caption}}}
.foot .pg{{position:absolute;right:0;top:0}}
{css}
</style><body><div class="slide" id="{pid}"><div class="body">{body}</div>
<div class="foot" data-tier="note"><span>{source}</span><span class="pg">{page} / {total}</span></div>
</div></body></html>"""


def _texts(page: Mapping, facts: Mapping, confirmed, errors: list, pending: list) -> dict:
    """Resolve every shown string on the page.  Returns the view ``free.render`` fills the page from."""
    view: dict[str, dict] = {}
    derived = page.get("derived") or {}
    for b in free.view(page):
        for ref in b.get("refs", []) if b["kind"] == "text" else []:
            if "text" in ref:
                bad = lint_text(ref["text"])
                if bad:
                    errors.append(f"作者文字「{ref['text']}」只能命名、不能陈述：{'；'.join(bad)}")
            elif "derived" in ref:
                did = ref["derived"]
                if did not in derived:
                    errors.append(f"综合句 {did} 没有在 derived 里写明")
                    continue
                said = resolve({"derived": derived[did].get("text"), "from": derived[did].get("from")},
                               facts, f"综合句 {did}", confirmed)
                view["derived:" + did] = {"text": said["text"], "pending": said["pending"]}
                if said["pending"]:
                    pending.append({"page": page.get("id"), "text": said["text"], "from": said["facts"], "digest": said["digest"]})
            else:
                try:
                    said = resolve({"fact": ref["fact"], **({"show": ref["show"]} if "show" in ref else {})},
                                   facts, f"文字 {ref['fact']}", confirmed)
                except ShownError as e:
                    errors.append(str(e))
                    continue
                view.setdefault(ref["fact"], {"text": facts[ref["fact"]]["quote"], "pending": False})
    return view


def _arrows(page: Mapping, facts: Mapping, errors: list) -> None:
    """An arrow says one thing leads to another.  It stands only where a sentence says so, in that order."""
    blocks = free.view(page)
    ends = {b["id"]: b for b in blocks if b["kind"] == "text"}
    for b in blocks:
        if b["kind"] != "arrow":
            continue
        head, tail = ends.get(b["from"]), ends.get(b["to"])
        fact = facts.get(b["backed_by"])
        refs = [next((r for r in e["refs"] if "fact" in r), None) if e else None for e in (head, tail)]
        if not (fact and refs[0] and refs[1]):
            errors.append(f"箭头 {b['from']}→{b['to']} 缺少两端的事实或支持句")
        elif not (arrow_backs(fact, refs[0], refs[1], facts) or chain_backs(fact, facts[refs[0]["fact"]], facts[refs[1]["fact"]])):
            errors.append(f"箭头 {b['from']}→{b['to']} 的支持句 {b['backed_by']} 既不是原件箭头，也没有依次说到两端：这个关系原文没有")


def _leaders(page: Mapping, assets: Mapping[str, dict], view: Mapping, facts: Mapping, errors: list) -> None:
    """A leader names a place on a picture.  Its label must say the name that place was reviewed under."""
    blocks = free.view(page)
    ends = {b["id"]: b for b in blocks if b["kind"] == "text"}
    for b in blocks:
        if b["kind"] != "leader":
            continue
        aid, _, key = b["anchor"].partition(":")
        anchor = ((assets.get(aid, {}).get("spec") or {}).get("anchors") or {}).get(key)
        if not anchor:
            errors.append(f"引线 {b['anchor']} 指向的标定点不存在：标注位置须先写进图意规格，并经过核对")
            continue
        label = ends.get(b["label"])
        said = "".join(r.get("show") or facts.get(r.get("fact"), {}).get("quote") or r.get("text") or "" for r in (label or {}).get("refs", []))
        if anchor["name"] not in said:
            errors.append(f"引线 {b['anchor']} 的标注须说到「{anchor['name']}」：这个位置是按这个名字核对的")


def check(page: Mapping, facts: Mapping[str, dict], assets: Mapping[str, dict], confirmed: Collection[str] = ()) -> dict:
    """Everything provable before drawing.  ``errors`` refuse the page; ``pending`` waits for a person."""
    errors = list(free.structure_errors(dict(page, design=page.get("design") or {"figure": "designed"}), rich=True))
    pending: list[dict] = []
    root, _ = free.parse(page.get("html") or "")
    used = [n.attrs["data-asset"] for n in root.walk() if n.has("data-asset")]
    for a in used:
        if a not in assets:
            errors.append(f"素材 {a} 不在清单里")
    if errors:
        return {"errors": errors, "pending": pending, "view": {}, "assets": used}
    view = _texts(page, facts, confirmed, errors, pending)
    _arrows(page, facts, errors)
    _leaders(page, assets, view, facts, errors)
    return {"errors": errors, "pending": pending, "view": view, "assets": used}


def render_html(page: Mapping, check_result: Mapping, assets: Mapping[str, dict], style: Mapping, *,
                source: str, page_no: int, total: int) -> str:
    body, css = free.render(dict(page), check_result["view"], {k: v["file"] for k, v in assets.items()}, emph_spans)
    tokens = "\n".join(f"#{page['id']}{{--{k}:{v}}}" for k, v in style["tokens"].items())
    return _FRAME.format(font=style["font"], canvas=style["tokens"]["canvas"], ink=style["tokens"]["ink"],
                         caption=style["tokens"]["caption"], css=tokens + "\n" + css, pid=page["id"], body=body,
                         source=_html.escape(source), page=page_no, total=total)


LEADERS_JS = """() => [...document.querySelectorAll('polyline[data-anchor]')].map((el) => {
  const [aid] = el.dataset.anchor.split(':');
  const m = el.getScreenCTM(), pts = [...el.points], end = pts[pts.length - 1];
  const r = document.querySelector(`img[data-asset="${aid}"]`).getBoundingClientRect();
  return { anchor: el.dataset.anchor, x: m.a * end.x + m.e, y: m.d * end.y + m.f, left: r.left, top: r.top, w: r.width, h: r.height };
})"""
LEADER_TOLERANCE = 10    # px on the slide: a leader that lands beside its point names something else


def leader_errors(drawn: list[dict], assets: Mapping[str, dict]) -> list[str]:
    out = []
    for d in drawn:
        aid, _, key = d["anchor"].partition(":")
        a = assets[aid]["spec"]["anchors"][key]
        gap = ((d["x"] - d["left"] - a["x"] * d["w"]) ** 2 + (d["y"] - d["top"] - a["y"] * d["h"]) ** 2) ** .5
        if gap > LEADER_TOLERANCE:
            out.append(f"引线 {d['anchor']} 的终点离标定点 {gap:.0f}px：引线画到了别的结构上")
    return out


BARS_JS = """() => [...document.querySelectorAll('[data-value-of][data-shape]')].map((e) => ({
  fact: e.dataset.valueOf, scale: e.dataset.scale, length: e.getBoundingClientRect().width }))"""


def bar_values(drawn: list[dict], facts: Mapping) -> tuple[dict[str, float], list[str]]:
    """The number each bar stands for: one exact number in its sentence, or the bar is refused."""
    values, errors = {}, []
    for b in drawn:
        hits = number_occurrences(facts[b["fact"]]["quote"])
        if len(hits) != 1:
            errors.append(f"条形 {b['fact']}：这句有 {len(hits)} 个数，须拆成只含一个数的事实")
            continue
        values[b["fact"]] = float(re.match(r"[^\d]*([\d.]+)", hits[0]["token"]).group(1))
    return values, errors


def trace(pages: list[Mapping], checked: list[dict], facts: Mapping[str, dict], manifest: Manifest,
          note: str = "") -> str:
    """Where every shown line came from, and for each picture how far it got.  The wording is deliberate: a picture
    is reported as signed by a person, never as verified, because nothing here can verify one.

    `note` says how the derivations were confirmed.  This report cannot tell a review from a blanket signature, so
    it does not claim one: without a note it prints the digest and leaves the question open.
    """
    lines = ["# 溯源报告", ""]
    if note:
        lines += [f"> {note}", ""]
    for p, c in zip(pages, checked):
        lines += [f"## {p['id']}", ""]
        for b in free.view(p):
            for r in b.get("refs", []) if b["kind"] == "text" else []:
                if "fact" in r:
                    f = facts[r["fact"]]
                    lines.append(f"- 「{r.get('show') or f['quote']}」← {f.get('source_id', '')} {f.get('location', '')}（{r['fact']}）")
                elif "derived" in r:
                    d = p["derived"][r["derived"]]
                    h = digest(d["text"], d["from"], facts)
                    lines.append(f"- 综合句「{d['text']}」← {'、'.join(d['from'])}（digest {h}）")
                else:
                    lines.append(f"- 标签「{r['text']}」（只命名）")
        for aid in c["assets"]:
            e = manifest.items[aid]
            lines.append(f"- 图 {aid}（{e['role']}）：{e['provider']} {e['model']}，sha256 {e['sha256'][:12]}")
            if e.get("review"):
                lines.append(f"  - 核对：{e['review']['reader']}；不确定：{'、'.join(e['review']['unsure']) or '无'}；"
                             f"超出原文的内容：{'、'.join(e['review']['beyond']) or '无'}")
            if e.get("signed"):
                lines.append(f"  - 主讲人已确认：{e['signed']['by']}（本报告不代表图的内容已被验证）")
        lines.append("")
    return "\n".join(lines)


def export(pages: list[Mapping], facts: Mapping[str, dict], manifest: Manifest, style: Mapping, out: Path | str,
           *, source: str, confirmed: Collection[str] = (), shots: Path | str | None = None,
           note: str = "") -> dict:
    """Check, draw, measure and write a deck.  A page with any error or pending line is refused, never written."""
    out = Path(out).resolve()      # the temporary page files are opened by the browser as file:// URIs
    assets = manifest.items
    from playwright.sync_api import sync_playwright

    from .design_audit import DESIGN_JS, audit

    checked = [check(p, facts, assets, confirmed) for p in pages]
    report: list[dict] = [{"page": p["id"], "errors": list(c["errors"]), "pending": c["pending"]}
                          for p, c in zip(pages, checked)]
    for c, row in zip(checked, report):
        row["pending"] = row["pending"] + [{"asset": a, "why": w} for a in c["assets"] if a in assets for w in manifest.blockers(a)]
    models = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        tab = browser.new_page(viewport={"width": W, "height": H})
        for i, (p, c, row) in enumerate(zip(pages, checked, report), 1):
            if row["errors"]:
                continue
            tmp = Path(out).with_suffix(f".p{i}.html")
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(render_html(p, c, assets, style, source=source, page_no=i, total=len(pages)), encoding="utf-8")
            tab.goto(tmp.as_uri())
            tab.wait_for_timeout(150)
            row["errors"] += [f'{x["kind"]}：{x.get("slot") or x.get("text") or x.get("tag") or ""}' for x in tab.evaluate(MEASURE_JS)]
            drawn = tab.evaluate(BARS_JS)
            values, bad = bar_values(drawn, facts)
            row["errors"] += bad + (free.bar_errors(dict(p), values, drawn) if not bad else [])
            row["errors"] += leader_errors(tab.evaluate(LEADERS_JS), assets)
            rules = audit(tab.evaluate(DESIGN_JS, 0), role=p.get("role") or "supporting")
            row["errors"] += [f'{r["rule"]}：{r["detail"]}' for r in rules if r.get("level") != "warn"]
            row["warnings"] = [r["detail"] for r in rules if r.get("level") == "warn"]
            if shots:
                Path(shots).mkdir(parents=True, exist_ok=True)
                tab.locator(".slide").screenshot(path=str(Path(shots) / f"{p['id']}.png"))
            if not row["errors"] and not row["pending"]:
                models.append(N.extract_slide(tab))
                row["lines"] = {_key(" ".join(r["text"] for para in it["paras"] for r in para)): it["lines"]
                                for it in models[-1]["items"] if it["type"] == "text"}
        browser.close()
    ok = len(models) == len(pages)
    written = N.build_pptx(models, out, title=source, font=style.get("pptx_font") or N.DEFAULT_FONT) if ok else None
    if ok:
        Path(out).with_suffix(".trace.md").write_text(trace(pages, checked, facts, manifest, note), encoding="utf-8")
    return {"ok": ok, "pages": report, "pptx": written["path"] if written else None}


_READ_LINES = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$app = New-Object -ComObject PowerPoint.Application
try {
  $p = $app.Presentations.Open($env:FD_PPTX, $true, $false, $false)
  $out = foreach ($s in $p.Slides) { foreach ($sh in $s.Shapes) { if ($sh.HasTextFrame -and $sh.TextFrame.HasText) {
    @{ slide = $s.SlideIndex; text = $sh.TextFrame.TextRange.Text; lines = $sh.TextFrame.TextRange.Lines().Count } } } }
  $p.Close()
  ConvertTo-Json -Compress -InputObject @($out)
} finally { $app.Quit() }
"""


def _key(text: str) -> str:
    return re.sub(r"\s+", "", text)


def line_parity(pptx: Path | str, pages: list[dict]) -> dict:
    """Does PowerPoint break each text box where the browser did?  Read back from PowerPoint itself, so a drift in
    fonts or metrics shows up as a number, not as a surprise on the day.  Skipped where PowerPoint is not installed."""
    import json
    import os
    import subprocess

    from .template_lib.render_deck import _powerpoint_installed
    if not _powerpoint_installed():
        return {"status": "skipped", "reason": "PowerPoint 未安装"}
    env = {**os.environ, "FD_PPTX": str(Path(pptx).resolve())}
    done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _READ_LINES], env=env,
                          capture_output=True, timeout=180, check=True)
    read = json.loads(done.stdout.decode("utf-8"))
    total, diff = 0, []
    for row in read:
        want = pages[row["slide"] - 1].get("lines", {}).get(_key(row["text"]))
        if want is None:
            continue
        total += 1
        if want != row["lines"]:
            diff.append({"text": row["text"][:24], "browser": want, "powerpoint": row["lines"]})
    return {"status": "checked", "boxes": total, "same": total - len(diff), "share": round((total - len(diff)) / max(total, 1), 3), "diff": diff}


def contract() -> dict:
    """What a generator needs to see."""
    return {"schema_version": SCHEMA, "canvas": [W, H],
            "rules": ["页面是 1280×720 的完整画布，版式、配色、卡片、阴影、渐变都由你决定。",
                      "文字只能放在 data-t 文本框里：<span data-fact=\"id\" data-show=\"原句节选\"></span> 或 "
                      "<span data-text>只命名、不陈述的标签</span>。跨句综合写进 derived，用 data-derived 引用，人确认后才显示。",
                      "图片只用 <img data-asset=\"id\" data-role=\"backdrop|illustration|icon\">，图片里不放文字。",
                      "箭头用 svg data-edges 的 polyline，data-from / data-to / data-backed 必填；条形用 data-value-of + data-scale。",
                      "插图上的标注用 polyline data-anchor=\"素材:标定点\" data-label=\"文本框 id\"，终点落在图意规格标定的位置；文字不压在插图上。",
                      "给文字标 data-tier（title/label/body/note）。页脚的来源和页码由代码写，不要自己写。"],
            "page": {"id": "", "role": "supporting", "html": "", "css": "", "derived": {"d1": {"text": "", "from": [""]}}}}
