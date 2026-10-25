"""Template-library generation flow: plan → selector → fill → HTML → Playwright measure → native PPTX → verify.

A *plan* is a slide-level content plan (see factdeck/examples/copd_layout_sample/plan.json)::

    {"title": ..., "note": <data note stamped on every page, e.g. 示例数据，教学示意，非诊疗建议>,
     "layout_signals": {...optional project terms for the selector...},
     "pages": [{"id", "kind", "title", "text": [...], "data": {...}, "proposed_layout"?: ..., "fills": {layout: fill}}]}

The selector decides every page's layout (integrate.decide: a proposed layout is kept only when qualified).
Fills come from the plan unchanged (fact-only content stays upstream); this flow never writes content.
Every run is a job with total / per-stage wall time and model-call usage (factdeck/jobstats.py).
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .. import jobstats
from . import bind
from . import integrate
from . import native as N
from . import selector as S
from .html_render import render_deck_html
from .measure import MEASURE_JS
from .slots import validate_fill

V1_FAMILIES = {"cover", "section", "key_points", "comparison", "flow", "timeline"}
V1_THEME, CHART_THEME = "premium_clinical", "gold_clinical"


def theme_for(layout: str, plan: dict) -> str:
    fam, var = S.LAYOUTS[layout][0], S.LAYOUTS[layout][1]
    themes = plan.get("themes") or {}
    if layout in themes:
        return themes[layout]
    if plan.get("theme"):
        return plan["theme"]
    return V1_THEME if fam in V1_FAMILIES and var != "evidence_takeaways" else CHART_THEME


def stamp_note(layout: str, fill: dict, note: str | None) -> dict:
    """Put the plan's data note (e.g. 示例数据，教学示意，非诊疗建议) into the slot each family shows it in."""
    f = copy.deepcopy(fill)
    if not note:
        return f
    fam, var = S.LAYOUTS[layout][0], S.LAYOUTS[layout][1]
    if fam == "cover":
        meta = f.get("meta") or ""
        f["meta"] = meta if note in meta else (f"{note}  |  {meta}".strip(" |") if meta else note)
    elif fam == "section":
        pass
    elif fam in ("algorithm_tree", "assessment_matrix", "dual_path_tree"):
        src = f.get("source") or ""
        f["source"] = src if note in src else (src.replace("教学示意，非诊疗建议", note) if "教学示意，非诊疗建议" in src
                                                 else (src + " · " + note).strip(" ·"))
    elif fam in ("key_points", "comparison", "flow", "timeline") and var != "evidence_takeaways":
        f["source"] = note
    else:
        f["data_note"] = note
    return f


def _office_png(pptx: Path, out_dir: Path, dpi: int = 60) -> dict:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice or not shutil.which("pdftoppm"):
        return {"status": "SKIPPED", "reason": "LibreOffice / pdftoppm not installed"}
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run([soffice, "--headless", f"-env:UserInstallation=file://{tmp}/u", "--convert-to", "pdf",
                            "--outdir", tmp, str(pptx)], capture_output=True, text=True, timeout=600)
        pdf = Path(tmp) / (pptx.stem + ".pdf")
        if not pdf.exists():
            return {"status": "FAILED", "reason": (r.stderr or r.stdout)[-300:]}
        shutil.copy(pdf, out_dir / pdf.name)
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(out_dir / "slide")], check=True, timeout=600)
    return {"status": "OK", "pdf": str(out_dir / (pptx.stem + ".pdf")),
            "pngs": sorted(str(p) for p in out_dir.glob("slide-*.png"))}


def _bound_input(page: dict, facts: dict) -> dict:
    """Selector input of a bound plan page: read from the resolved fill the page would show, not from plan text."""
    fills = {k: v for k, v in (page.get("fills") or {}).items() if k in S.LAYOUTS}
    first = page.get("proposed_layout") if page.get("proposed_layout") in fills else next(iter(fills), None)
    if not first:
        return {**page, "text": [], "data": {}}
    fam, var = S.LAYOUTS[first][0], S.LAYOUTS[first][1]
    res = bind.resolve(fam, var, fills[first], facts, title=page.get("title"), page_checks=False)
    sel = integrate.page_from_fill(page.get("id"), first, res["fill"], kind=page.get("kind") or "content",
                                   proposed=page.get("proposed_layout"))
    return {**sel, "fills": page.get("fills")}


def run(plan: dict, out: Path | str, *, tiebreaker: S.TieBreaker | None = None, font: str = N.DEFAULT_FONT,
        previews: bool = True, office_render: bool = False, job_id: str | None = None,
        facts: dict[str, dict] | None = None, sources: dict[str, str] | None = None,
        glossary=(), terms=(), page_notes: dict[str, str] | None = None) -> dict:
    """Run the whole flow for one plan; returns the job record (also written to out/job.json).

    With `facts` (id → verified fact dict) every fill is a bound fill (template_lib/bind.py): shown strings are
    fact references or checked authored labels, drawn numbers are backed by page facts, footers come from the facts
    used, and a trace report (trace.json / trace.md) covers every page.  Without it the plan's fills are shown as
    they are (sample data) and the report says so.  `page_notes` (page id → text) go first in each slide's
    speaker notes."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    bound = facts is not None
    if plan.get("bound") and not bound:
        raise ValueError("该计划的填充引用事实库（bound），须传入 facts")
    pages = [_bound_input(p, facts) for p in plan["pages"]] if bound else plan["pages"]
    note = None if bound else plan.get("note")
    record: dict[str, Any] = {"title": plan.get("title"), "note": note, "bound": bound, "pages": [], "native": None}
    with jobstats.job("template_deck", job_id=job_id, out_dir=out,
                      meta={"title": plan.get("title"), "pages": len(pages), "bound": bound,
                            "llm_tie_break": "on" if tiebreaker else "off"}) as js:
        record["job_id"] = js.job_id
        with jobstats.stage("select"):
            res = integrate.decide(pages, tiebreaker=tiebreaker, extra_signals=plan.get("layout_signals"))
        record["selection_stats"] = res["stats"]

        with jobstats.stage("fill"):
            jobs, sections = [], 0
            for src, page, d in zip(plan["pages"], pages, res["decisions"]):
                lay, fill, fallback = integrate.resolve_fill(page, d)
                entry = {"page_no": d["page_no"], "page_id": d["page_id"], "layout_decision": integrate.page_record(d),
                         "rendered_layout": lay, "fill_fallback": fallback, "status": "PENDING"}
                record["pages"].append(entry)
                if fill is None:
                    entry["status"] = "NO_FILL"
                    continue
                fam, var = S.LAYOUTS[lay][0], S.LAYOUTS[lay][1]
                if bound:
                    sections += fam == "section"
                    b = bind.resolve(fam, var, fill, facts, title=src.get("title"), section_no=sections,
                                     sources=sources, glossary=glossary, terms=terms, page_no=d["page_no"])
                    entry.update(trace=b["trace"], facts=b["facts"], pending=b["pending"], bind_warnings=b["warnings"])
                    if b["errors"]:
                        entry["status"] = "FILL_UNBOUND"
                        entry["errors"] = b["errors"]
                        continue
                    f = b["fill"]
                else:
                    f = stamp_note(lay, fill, note)
                if fam not in ("cover", "section"):
                    f["page"] = f"{d['page_no']:02d}"
                rep = validate_fill(fam, f, variant=var)
                if not rep["ok"]:
                    entry["status"] = "FILL_INVALID"
                    entry["errors"] = rep["errors"]
                    continue
                theme = theme_for(lay, plan)
                entry.update(family=fam, variant=var, fill=f)
                jobs.append((entry, fam, var, f, theme))

        with jobstats.stage("render_html", pages=len(jobs)):
            (out / "pages").mkdir(exist_ok=True)
            for entry, fam, var, f, theme in jobs:
                html = render_deck_html([{"family": fam, "fill": f, "variant": var, "theme": theme}], theme=theme)
                hp = out / "pages" / f"p{entry['page_no']:02d}-{entry['rendered_layout'].replace('/', '-')}.html"
                hp.write_text(html, encoding="utf-8")
                entry["html"] = str(hp.relative_to(out))
                entry["theme"] = theme

        models, notes = [], []
        with jobstats.stage("measure", pages=len(jobs)):
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                pg = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
                for entry, *_ in jobs:
                    # self-contained HTML: loaded as content, so a long Windows path (>260) cannot break the load
                    pg.set_content((out / entry["html"]).read_text(encoding="utf-8"), wait_until="load")
                    pg.evaluate("document.fonts.ready.then(() => true)")
                    pg.wait_for_timeout(60)
                    entry["qa_issues"] = pg.evaluate(MEASURE_JS)
                    if previews:
                        png = out / "pages" / (Path(entry["html"]).stem + ".png")
                        pg.locator(".slide").first.screenshot(path=str(png))
                        entry["preview_png"] = str(png.relative_to(out))
                    m = N.extract_slide(pg)
                    entry["measured"] = m["counts"]
                    entry["unsupported"] = m["unsupported"]
                    models.append(m)
                    ld = entry["layout_decision"]
                    script = (page_notes or {}).get(entry["page_id"])
                    notes.append((f"{script}\n\n" if script else "") + f"【版式】{ld['name_zh']}（{ld['layout']}）— {ld['reason_zh']}"
                                 + (f"\n【版式提议】{ld['proposal']['reason_zh']}" if ld.get("proposal") else "")
                                 + (f"\n【数据说明】{note}" if note else "")
                                 + "".join("\n" + x for x in bind.notes_lines(entry.get("trace") or [], sources)))
                browser.close()

        with jobstats.stage("native", pages=len(models)):
            pptx = out / "deck.pptx"
            built = N.build_pptx(models, pptx, title=plan.get("title") or "", font=font, notes=notes)
            for (entry, *_), rep in zip(jobs, built["slides"]):
                entry["slide"] = rep["slide"]
                entry["native_written"] = rep["written"]
                entry["status"] = "OK"
            record["native"] = {"pptx": str(pptx), "font": font, "version": N.VERSION}

        with jobstats.stage("verify"):
            insp = N.inspect_pptx(pptx)
            for (entry, *_), sl in zip(jobs, insp["slides"]):
                entry["pptx"] = {k: sl[k] for k in ("shapes", "kinds", "pictures", "text_frames", "tables",
                                                    "table_cells_with_text", "svg_embedded")}
            record["verify"] = {"aspect": insp["aspect"], "slides": len(insp["slides"]),
                                "pictures": sum(s["pictures"] for s in insp["slides"]),
                                "svg_embedded": any(s["svg_embedded"] for s in insp["slides"]),
                                "qa_issue_pages": [e["page_id"] for e in record["pages"] if e.get("qa_issues")]}

        if office_render:
            with jobstats.stage("office_render"):
                record["office_render"] = _office_png(pptx, out / "pptx-render")
        record["stats"] = js.summary()
    record["stats"] = jobstats.get_job(record["job_id"]) or record["stats"]
    (out / "job.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    trace = [{"page_no": e["page_no"], "page_id": e["page_id"], "layout": e["rendered_layout"], "bound": bound,
              "status": e["status"], "errors": e.get("errors") or [], "trace": e.get("trace") or []}
             for e in record["pages"]]
    (out / "trace.json").write_text(json.dumps({"bound": bound, "sources": sources or {}, "pages": trace},
                                               ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "trace.md").write_text(bind.trace_markdown(trace, title=f"溯源报告 · {plan.get('title') or ''}".strip(" ·"),
                                                      sources=sources), encoding="utf-8")
    (out / "decisions.json").write_text(json.dumps(
        {"stats": res["stats"], "pages": [{"page_id": e["page_id"], **e["layout_decision"]} for e in record["pages"]]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    return record
