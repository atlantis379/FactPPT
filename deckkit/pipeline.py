# -*- coding: utf-8 -*-
"""
End-to-end pipeline: one document in, a finished, gated deck out.

    python -m deckkit all report.docx --theme clinical -o out/report

Stages
  1 extract   document -> deck.json   (docx/pdf/txt/md, column-aware for PDFs)
  2 build     deck.json -> self-contained slides.html (+ local assets copied)
  3 render    HTML -> per-slide PNG + PDF
  4 pptx      deck.json -> native editable .pptx, tokens written into the theme,
              re-ingested to verify the round trip
  5 gates     overflow audit · WCAG contrast · chart geometry · image crop
  6 report    machine-readable JSON + human-readable summary

The command exits non-zero if any stage or gate fails, so it can be wired into
CI or a batch run over many documents.
"""
import io
import json
import os
import time

from . import audit as AUDIT
from . import build as BUILD
from . import extract as X
from . import pptx_export as PE
from . import pptx_theme as PT
from . import theme_gen as TG
from . import theme_from_pptx as TFP
from . import themes
# NOTE: `from . import render` would bind the FUNCTION re-exported by
# deckkit/__init__.py, not the module — import the callable by its own name.
from .render import render as render_deck


def _stage(name, fn):
    t0 = time.time()
    try:
        detail = fn()
        return {"stage": name, "status": "PASS", "seconds": round(time.time() - t0, 2),
                "detail": detail if isinstance(detail, dict) else {"value": detail}}
    except Exception as e:  # noqa: BLE001
        return {"stage": name, "status": "FAIL", "seconds": round(time.time() - t0, 2),
                "error": f"{type(e).__name__}: {e}"}


def _chart_slides(deck):
    return [(i, sl.get("chart") or {}) for i, sl in enumerate(deck.get("slides", []), 1)
            if (sl.get("type") or "").lower() == "chart"]


def _image_slides(deck):
    return [(i, sl) for i, sl in enumerate(deck.get("slides", []), 1)
            if (sl.get("type") or "").startswith("image-")]


def run(doc, outdir, theme_name=None, *, title=None, subtitle=None, brand=None,
        tagline=None, source=None, source_label="来源", author=None, org=None,
        max_slides=16, pdf_mode="auto", pages=None,
        do_pptx=True, do_render=True,
        do_gates=True, quiet=True):
    """Run the whole pipeline. Returns a report dict."""
    os.makedirs(outdir, exist_ok=True)
    started = time.time()
    report = {"doc": os.path.basename(str(doc)), "doc_path": str(doc),
              "outdir": os.path.abspath(outdir), "stages": [], "outputs": {}}

    # ---------------------------------------------------------------- 1 extract
    state = {}

    def _extract():
        # an existing deck.json is taken as-is (build/render/pptx/gates only)
        if str(doc).lower().endswith(".json"):
            with io.open(doc, encoding="utf-8") as f:
                deck = json.load(f)
            for k, v in (("title", title), ("subtitle", subtitle), ("brand", brand),
                         ("tagline", tagline), ("author", author), ("org", org)):
                if v:
                    deck.setdefault("meta", {})[k] = v
            state["deck"] = deck
            state["deck_path"] = str(doc)
            kinds = {}
            for s in deck.get("slides", []):
                kinds[s.get("type", "?")] = kinds.get(s.get("type", "?"), 0) + 1
            return {"blocks": 0, "slides": len(deck.get("slides", [])),
                    "title": (deck.get("meta") or {}).get("title"),
                    "archetypes": kinds, "source": "existing deck.json"}
        blocks = X.load_blocks(doc, pdf_mode=pdf_mode, pages=pages)
        deck = X.to_deck(blocks, title=title, subtitle=subtitle, brand=brand,
                         tagline=tagline, source=source or os.path.basename(str(doc)),
                         source_label=source_label, author=author, org=org,
                         max_slides=max_slides, theme=theme_name, path=doc,
                         pdf_mode=pdf_mode, pages=pages)
        deck.setdefault("meta", {})
        path = os.path.join(outdir, "deck.json")
        with io.open(path, "w", encoding="utf-8") as f:
            json.dump(deck, f, ensure_ascii=False, indent=2)
        state["deck"] = deck
        state["deck_path"] = path
        kinds = {}
        for s in deck["slides"]:
            kinds[s.get("type", "?")] = kinds.get(s.get("type", "?"), 0) + 1
        return {"blocks": len(blocks), "slides": len(deck["slides"]),
                "title": deck["meta"].get("title"), "archetypes": kinds,
                "pdf_mode": pdf_mode}
    report["stages"].append(_stage("extract", _extract))
    if "deck" not in state:
        report["status"] = "FAIL"
        report["failed_stages"] = ["extract"]
        report["seconds"] = round(time.time() - started, 2)
        return report

    deck = state["deck"]
    base_dir = os.path.dirname(os.path.abspath(str(doc)))
    tn = theme_name or deck.get("theme") or themes.DEFAULT_THEME
    report["theme"] = tn

    # ------------------------------------------------------------------ 2 build
    html_path = os.path.join(outdir, "slides.html")

    def _build():
        BUILD.write_html(deck, html_path, tn, base_dir=base_dir)
        assets = BUILD.collect_assets(deck)
        return {"html": html_path, "assets_referenced": len(assets),
                "assets_missing": [a for a in assets
                                   if not os.path.isfile(os.path.join(base_dir, a))]}
    report["stages"].append(_stage("build", _build))
    report["outputs"]["html"] = html_path

    # ----------------------------------------------------------------- 3 render
    if do_render:
        def _render():
            pdf_path = os.path.join(outdir, f"deck_{tn}.pdf")
            png_dir = os.path.join(outdir, "png")
            res = render_deck(html_path, png_dir, pdf=pdf_path, png=True,
                              quiet=quiet)
            return {"png_count": len(res.get("png") or []), "pdf": res.get("pdf")}
        report["stages"].append(_stage("render", _render))
        png_dir = os.path.join(outdir, "png")
        report["outputs"]["png_dir"] = png_dir
        for f in os.listdir(outdir):
            if f.endswith(".pdf"):
                report["outputs"]["pdf"] = os.path.join(outdir, f)

    # ------------------------------------------------------------------- 4 pptx
    if do_pptx:
        pptx_path = os.path.join(outdir, "deck.pptx")

        def _pptx():
            res = PE.export(deck, pptx_path, tn, base_dir=base_dir)
            fid = PE.fidelity(deck, pptx_path)
            out = {"fidelity": fid["status"], "missing": fid["missing"][:8],
                   "slides": res["slides"], "theme_injected": res["theme_injected"]}
            if res["theme_injected"]:
                t = dict(themes.get(tn))
                t.setdefault("mode", "light")
                got = TFP.to_theme(TFP.read_template(pptx_path), name="rt")
                out["roundtrip"] = PT.round_trip_report(
                    t, got, TFP.read_template(pptx_path).get("colors"))
            state["pptx"] = out
            return out
        st = _stage("pptx", _pptx)
        report["stages"].append(st)
        report["outputs"]["pptx"] = pptx_path
        if st["status"] == "PASS" and state.get("pptx", {}).get("fidelity") != "PASS":
            st["status"] = "FAIL"
        if st["status"] == "PASS" and state.get("pptx", {}).get("roundtrip", {}).get(
                "status") == "FAIL":
            st["status"] = "FAIL"

    # ------------------------------------------------------------------ 5 gates
    if do_gates:
        def _gate_overflow():
            r = AUDIT.audit(html_path, quiet=True)
            return {"issues": len(r.get("issues", [])), "slides": r.get("slides"),
                    "detail": r.get("issues", [])[:6]}
        report["stages"].append(_stage("gate:overflow", _gate_overflow))

        def _gate_contrast():
            t = themes.get(tn)
            bad = TG.check_theme(t)
            return {"violations": len(bad), "detail": bad[:5]}
        report["stages"].append(_stage("gate:contrast", _gate_contrast))

        charts = _chart_slides(deck)
        if charts:
            def _gate_charts():
                from . import chart_geometry as CG
                from . import charts as CH
                rows, bad = [], 0
                for i, spec in charts:
                    errs = CH.spec_errors(spec)
                    if errs:
                        rows.append({"slide": i, "status": "SPEC_FAIL", "errors": errs})
                        bad += 1
                        continue
                    r = CG.audit(html_path, i - 1, spec)
                    bad += 1 if r["status"] != "PASS" else 0
                    rows.append({"slide": i, "status": r["status"],
                                 "marks": r["marks_checked"], "issues": r["issues"][:3]})
                return {"charts": len(rows), "failed": bad, "detail": rows}
            report["stages"].append(_stage("gate:charts", _gate_charts))

        imgs = _image_slides(deck)
        if imgs:
            def _gate_images():
                from . import image_geometry as IG
                from . import images as IM
                spec = [{"slide": i, "errors": IM.spec_errors(sl)}
                        for i, sl in imgs if IM.spec_errors(sl)]
                r = IG.audit(deck, html_path, base_dir=base_dir)
                return {"images_checked": r["images_checked"], "spec_failures": spec,
                        "status": r["status"], "issues": r["issues"][:6]}
            report["stages"].append(_stage("gate:images", _gate_images))

    # ----------------------------------------------------------------- 6 report
    failed = [s["stage"] for s in report["stages"] if s["status"] != "PASS"]
    for s in report["stages"]:
        if s["stage"].startswith("gate:"):
            d = s.get("detail") or {}
            n = d.get("issues", d.get("violations", d.get("failed", 0)))
            if isinstance(n, list):
                n = len(n)
            if s["status"] == "PASS" and n:
                s["status"] = "FAIL"
    failed = [s["stage"] for s in report["stages"] if s["status"] != "PASS"]
    report["status"] = "PASS" if not failed else "FAIL"
    report["failed_stages"] = failed
    report["seconds"] = round(time.time() - started, 2)

    with io.open(os.path.join(outdir, "pipeline_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    report["outputs"]["report"] = os.path.join(outdir, "pipeline_report.json")
    return report


def summary_markdown(report):
    """A short human-readable run summary."""
    L = [f"# Pipeline report — {report['doc']}", ""]
    L.append(f"- theme: `{report.get('theme')}`")
    L.append(f"- status: **{report['status']}**  ({report.get('seconds')}s)")
    L.append("")
    L.append("| stage | status | seconds | detail |")
    L.append("|---|---|---|---|")
    for s in report["stages"]:
        d = s.get("detail") or {}
        if s["stage"] == "extract":
            info = f"{d.get('slides')} slides · {d.get('blocks')} blocks · {d.get('title','')[:34]}"
        elif s["stage"] == "build":
            info = f"{d.get('assets_referenced')} assets"
        elif s["stage"] == "render":
            info = ", ".join(f"{k}={v}" for k, v in list(d.items())[:3])
        elif s["stage"] == "pptx":
            info = f"fidelity={d.get('fidelity')} roundtrip={(d.get('roundtrip') or {}).get('status')}"
        else:
            info = str({k: v for k, v in list(d.items())[:3]})[:70]
        if s["status"] != "PASS" and s.get("error"):
            info = s["error"][:70]
        L.append(f"| {s['stage']} | {s['status']} | {s.get('seconds')} | {info} |")
    L.append("")
    outs = report.get("outputs", {})
    L.append("## outputs")
    for k in ("html", "pdf", "png_dir", "pptx", "report"):
        if outs.get(k):
            L.append(f"- {k}: `{outs[k]}`")
    return "\n".join(L) + "\n"
