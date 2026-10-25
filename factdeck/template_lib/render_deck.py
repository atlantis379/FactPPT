"""Render a deck spec whose pages are template-library pages (`layout: "template"`) for the FactDeck workflow.

Same output contract as `factdeck.render.render`, so the workflow's RENDER, page review and export take it as is:
deck.pptx (native objects), deck.pdf and deck.html (browser render of the same pages), slideNN.png (one per page,
for page review) and render_report.json ({slides, summary, hard_errors, warnings, font, theme}).

Flow: deck.check → template_lib.pipeline.run with the fact store (bound fills, selector, Playwright measure, native
PPTX, trace.md / trace.json) → PPTX read-back (every fact a page shows is in its slide, whole) → report.
Hard errors: a page not rendered, text clipped or overflowing in the measure, a fact missing from its slide, a
picture or embedded SVG in the PPTX.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..deck import check as deck_check
from . import integrate
from . import native as N
from . import pipeline
from .html_render import render_deck_html

VERSION = "template-render.1"
THEME = "template_lib"
_PRINT = "<style>@page{size:1280px 720px;margin:0}</style>"


_PPT_EXPORT = r"""
$ErrorActionPreference = 'Stop'
$app = New-Object -ComObject PowerPoint.Application
try {
  $p = $app.Presentations.Open($env:FD_PPTX, $true, $false, $false)
  for ($i = 1; $i -le $p.Slides.Count; $i++) { $p.Slides.Item($i).Export((Join-Path $env:FD_OUT ('ppt{0:D2}.png' -f $i)), 'PNG', 1280, 720) }
  $p.Close()
} finally { $app.Quit() }
"""


def _powerpoint_installed() -> bool:
    import sys
    if sys.platform != "win32":
        return False
    import winreg
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"PowerPoint.Application"))
        return True
    except OSError:
        return False


def appearance(out: Path, n_slides: int) -> dict:
    """Does the PPTX look like the browser render in an office program?  PowerPoint itself (Windows, COM export)
    when installed, else LibreOffice (factdeck.render.appearance_check); each slide is compared with slideNN.png."""
    from ..render import DRIFT_MAX, appearance_check
    if not _powerpoint_installed():
        return {**appearance_check(out, n_slides), "renderer": "LibreOffice"}
    import os
    import subprocess
    from PIL import Image, ImageChops, ImageStat
    dst = out / "pptx-render"
    dst.mkdir(exist_ok=True)
    env = {**os.environ, "FD_PPTX": str((out / "deck.pptx").resolve()), "FD_OUT": str(dst.resolve())}
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PPT_EXPORT], env=env, check=True,
                       capture_output=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as e:
        return {"status": "skipped", "renderer": "PowerPoint", "reason": f"PowerPoint 导出失败：{str(e)[:200]}"}
    slides = []
    for i in range(1, n_slides + 1):
        png = dst / f"ppt{i:02d}.png"
        if not png.exists():
            return {"status": "skipped", "renderer": "PowerPoint", "reason": f"PowerPoint 未导出第 {i} 页"}
        a = Image.open(png).convert("L").resize((640, 360))
        b = Image.open(out / f"slide{i:02d}.png").convert("L").resize((640, 360))
        slides.append({"slide": i, "drift": round(ImageStat.Stat(ImageChops.difference(a, b)).mean[0] / 255, 3),
                       "png": f"pptx-render/{png.name}"})
    return {"status": "checked", "renderer": "PowerPoint", "slides": slides,
            "drifted": [x["slide"] for x in slides if x["drift"] > DRIFT_MAX]}


def is_template_deck(deck: dict) -> bool:
    return any(isinstance(p, dict) and p.get("layout") == "template" for p in deck.get("pages") or [])


def _label(src: dict, sid: str) -> str:
    from ..render import short_title
    return short_title(str(src.get("title") or src.get("filename") or sid))


def render(deck: dict, facts: dict[str, dict], sources: dict[str, dict], out: Path, terms=(),
           teaching_notes: dict[str, str] | None = None, font: str = N.DEFAULT_FONT) -> dict:
    """`facts`: verified facts by id; `sources` by id ({title|filename}); `teaching_notes` by page id."""
    from playwright.sync_api import sync_playwright
    from ..render import readback

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    chk = deck_check(deck, facts, terms)
    if chk["errors"]:
        raise ValueError(f"页面规格检查未通过：{chk['errors']} 处错误")
    pages = deck.get("pages") or []
    if not all(p.get("layout") == "template" for p in pages):
        raise ValueError("模板库渲染要求全部页面为模板页（layout: template）")
    labels = {sid: _label(s, sid) for sid, s in sources.items()}
    glossary = [x["text"] for x in deck.get("glossary", deck.get("terms", []))]
    notes = {pid: f"【讲稿】\n{t}" for pid, t in (teaching_notes or {}).items() if t}
    rec = pipeline.run(integrate.deck_plan(deck), out / "template", facts=facts, sources=labels, glossary=glossary,
                       terms=terms, font=font, page_notes=notes)
    bad = [e for e in rec["pages"] if e["status"] != "OK"]
    if bad:
        raise ValueError("模板页未能渲染：" + "；".join(f"{e['page_id']} {e['status']} {'；'.join(e.get('errors') or [])}"
                                                   f"{e.get('fill_fallback') or ''}" for e in bad))

    shutil.copy(rec["native"]["pptx"], out / "deck.pptx")
    for i, e in enumerate(rec["pages"], 1):
        shutil.copy(out / "template" / e["preview_png"], out / f"slide{i:02d}.png")
    html = render_deck_html([{"family": e["family"], "variant": e["variant"], "fill": e["fill"], "theme": e["theme"]}
                             for e in rec["pages"]])
    (out / "deck.html").write_text(html.replace("</head>", _PRINT + "</head>", 1), encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 720})
        pg.set_content((out / "deck.html").read_text(encoding="utf-8"), wait_until="load")   # path-length safe
        pg.evaluate("document.fonts.ready.then(() => true)")
        pg.emulate_media(media="print")
        pg.pdf(path=str(out / "deck.pdf"), width="1280px", height="720px", print_background=True)
        browser.close()

    fview = {fid: {"text": f.get("display") or f.get("quote") or "", "figure": f.get("figure")} for fid, f in facts.items()}
    shown = [sorted(set(e.get("facts") or [])) for e in rec["pages"]]
    rb = readback(out / "deck.pptx", shown, fview)
    slides = []
    for p, e, c, r in zip(pages, rec["pages"], chk["pages"], rb):
        ld = e["layout_decision"]
        slides.append({"id": p["id"], "layout": e["rendered_layout"], "layout_name": ld["name_zh"], "layout_reason": ld["reason_zh"],
                       "design": p.get("design") or {}, "signals": c.get("signals") or [], "review": c.get("review") or [],
                       "occupancy": None, "hole": None, "metrics": {}, "qa_issues": e.get("qa_issues") or [],
                       "bind_warnings": e.get("bind_warnings") or [], "pptx": e.get("pptx"), "pptx_readback": r})
    verify = rec["verify"]
    summary = {"slides": len(pages), "facts_on_slides": sum(len(x) for x in shown),
               "pending_confirmation": sum(len(c["pending"]) for c in chk["pages"]),
               "overflow": sum(len(s["qa_issues"]) for s in slides),
               "pptx_missing_facts": sum(len(r["missing"]) for r in rb),
               "pictures": verify["pictures"], "svg_embedded": int(bool(verify["svg_embedded"])),
               "chart_pages": rec["selection_stats"].get("chart_pages"),
               "chart_target_met": rec["selection_stats"].get("chart_target_met")}
    st = rec["selection_stats"]
    warnings = [f"{s['id']}：{w}" for s in slides for w in s["bind_warnings"]]
    if st.get("consecutive_repeats"):
        warnings.append(f"相邻内容页使用相同版式：{'、'.join(st['consecutive_repeats'])}")
    if st.get("chart_target_met") is False:
        warnings.append(f"图表页占比 {st.get('chart_ratio')}，低于 1/3（内容不支持更多图表时可接受）")
    look = appearance(out, len(pages))
    if look["status"] != "checked":
        warnings.append(f"未用办公软件核对 PPTX 画面：{look.get('reason')}；请在页面审核时用 PowerPoint 打开 deck.pptx")
    elif look["drifted"]:
        warnings.append(f"{look['renderer']} 中画面与浏览器渲染差异较大的页：{'、'.join(map(str, look['drifted']))}（请在 PowerPoint 中检查）")
    report = {"engine": VERSION, "route": "TEMPLATE_LIB", "theme": THEME, "font": font, "slides": slides,
              "summary": summary, "hard_errors": summary["overflow"] + summary["pptx_missing_facts"] + summary["pictures"]
              + summary["svg_embedded"], "warnings": warnings, "job_id": rec["job_id"],
              "stats": {k: rec["stats"].get(k) for k in ("total_seconds", "stage_seconds", "tokens")},
              "trace_report": "template/trace.md", "selection": st, "appearance": look}
    (out / "render_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report
