# -*- coding: utf-8 -*-
"""deckkit CLI.

    python -m deckkit themes
    python -m deckkit check  DECK.json
    python -m deckkit build  DECK.json --theme clinical -o OUTDIR
    python -m deckkit render DECK.json --theme clinical -o OUTDIR [--png] [--pdf]
    python -m deckkit gallery DECK.json -o OUTDIR        # same deck, every theme
"""
import argparse
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
from . import themes, build
from .render import render as render_deck, render_themes
from .layouts import BUILDERS

VALID_TYPES = set(BUILDERS)


def _deck_dir(deck_path):
    """Directory of the deck JSON — local asset paths resolve against it."""
    try:
        return os.path.dirname(os.path.abspath(str(deck_path)))
    except Exception:  # noqa: BLE001
        return None


def _load(p):
    return build.load_deck(p)


def cmd_themes(a):
    print(f"{'name':<12}{'label':<26}canvas  description")
    print("-" * 78)
    for k, t in themes.THEMES.items():
        print(f"{k:<12}{t['label']:<26}1280x720  primary={t['primary']} accent={t['accent']}")
    print(f"\ndefault: {themes.DEFAULT_THEME}")
    return 0


def cmd_check(a):
    d = _load(a.deck)
    errs, warns = [], []
    if not d.get("slides"):
        errs.append("no slides")
    meta = d.get("meta", {})
    for key in ("brand",):
        if not meta.get(key):
            warns.append(f"meta.{key} missing (brand bar will be empty)")
    tn = a.theme or d.get("theme") or themes.DEFAULT_THEME
    if tn not in themes.THEMES:
        errs.append(f"unknown theme {tn!r}")
    for i, s in enumerate(d.get("slides", []), 1):
        kind = (s.get("type") or "cards").lower()
        if kind not in VALID_TYPES:
            errs.append(f"slide {i}: unknown type {kind!r}")
            continue
        if kind == "cards":
            n = len(s.get("cards", []))
            if n == 0:
                errs.append(f"slide {i}: cards slide with no cards")
            if n > 6:
                warns.append(f"slide {i}: {n} cards (>6) may be cramped")
        if kind == "steps":
            n = len(s.get("steps", []))
            if n == 0:
                errs.append(f"slide {i}: steps slide with no steps")
            if n > 4:
                errs.append(f"slide {i}: {n} steps exceeds the 4-column maximum")
        if kind == "kpi" and not s.get("kpis"):
            errs.append(f"slide {i}: kpi slide with no kpis")
        if kind == "table" and not s.get("columns"):
            errs.append(f"slide {i}: table slide with no columns")
        if not s.get("title") and kind not in ("cover", "closing"):
            warns.append(f"slide {i}: no title")
    print(json.dumps({
        "deck": os.path.basename(str(a.deck)),
        "theme": tn, "slides": len(d.get("slides", [])),
        "status": "FAIL" if errs else ("PASS_WITH_WARNINGS" if warns else "PASS"),
        "errors": errs, "warnings": warns,
    }, ensure_ascii=False, indent=2))
    return 1 if errs else 0


def cmd_build(a):
    d = _load(a.deck)
    out = os.path.join(a.out, "slides.html")
    build.write_html(d, out, a.theme, base_dir=_deck_dir(a.deck))
    print(f"html -> {out}  ({build.slide_count(d)} slides, theme={a.theme or d.get('theme') or themes.DEFAULT_THEME})")
    return 0


def cmd_render(a):
    d = _load(a.deck)
    tn = a.theme or d.get("theme") or themes.DEFAULT_THEME
    outdir = a.out
    os.makedirs(outdir, exist_ok=True)
    html = os.path.join(outdir, f"slides_{tn}.html")
    build.write_html(d, html, tn, base_dir=_deck_dir(a.deck))
    pdf = os.path.join(outdir, f"deck_{tn}.pdf") if a.pdf else None
    res = render_deck(html, os.path.join(outdir, "png"), pdf=pdf, png=a.png)
    print(json.dumps({
        "theme": tn, "html": html, "pdf": res["pdf"],
        "png_count": len(res["png"]), "png_dir": os.path.join(outdir, "png"),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_gallery(a):
    d = _load(a.deck)
    names = a.themes.split(",") if a.themes else list(themes.THEMES)
    res = render_themes(d, a.out, names, png=a.png, pdf=a.pdf)
    summary = {k: {"html": os.path.join(a.out, k, "slides.html"),
                   "pdf": v["pdf"], "png": len(v["png"])} for k, v in res.items()}
    print(json.dumps({"themes": names, "out": a.out, "results": summary},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_audit(a):
    d = _load(a.deck)
    tn = a.theme or d.get("theme") or themes.DEFAULT_THEME
    outdir = a.out
    os.makedirs(outdir, exist_ok=True)
    html = os.path.join(outdir, f"slides_{tn}.html")
    build.write_html(d, html, tn, base_dir=_deck_dir(a.deck))
    from .audit import audit
    res = audit(html)
    print(json.dumps({"theme": tn, "slides": res["slides"],
                      "issues": len(res["issues"]),
                      "status": "PASS" if not res["issues"] else "FAIL",
                      "detail": res["issues"][:20]}, ensure_ascii=False, indent=2))
    return 1 if res["issues"] else 0


def cmd_selftest(a):
    """Build + audit a canonical deck under every theme. Regression guard."""
    d = _load(a.deck)
    from .audit import audit
    tmp = a.out or os.path.join("deckkit", "out", "_selftest")
    rows, failed = [], 0
    for tn in themes.THEMES:
        os.makedirs(tmp, exist_ok=True)
        html = os.path.join(tmp, f"selftest_{tn}.html")
        try:
            build.write_html(d, html, tn, base_dir=_deck_dir(a.deck))          # token completeness is enforced here
            res = audit(html, quiet=True)
            bad = len(res["issues"])
            failed += 1 if bad else 0
            rows.append({"theme": tn, "slides": res["slides"], "issues": bad,
                         "status": "PASS" if not bad else "FAIL"})
        except Exception as e:  # noqa: BLE001
            failed += 1
            rows.append({"theme": tn, "slides": 0, "issues": -1, "status": f"ERROR {type(e).__name__}: {e}"})
    print(json.dumps({"deck": os.path.basename(str(a.deck)), "themes_tested": len(rows),
                      "failed": failed, "results": rows},
                     ensure_ascii=False, indent=2))
    return 1 if failed else 0


def cmd_extract(a):
    from . import extract as X
    blocks = X.load_blocks(a.doc, pages=getattr(a, "pages", None))
    deck = X.to_deck(
        blocks, title=a.title, subtitle=a.subtitle, brand=a.brand, tagline=a.tagline,
        source=a.source or os.path.basename(a.doc), source_label=a.source_label,
        author=a.author, org=a.org, max_slides=a.max_slides, theme=a.theme, path=a.doc,
    )
    out = a.out
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with io.open(out, "w", encoding="utf-8") as f:
        json.dump(deck, f, ensure_ascii=False, indent=2)
    types = [s.get("type") for s in deck["slides"]]
    print(json.dumps({
        "doc": os.path.basename(a.doc), "blocks": len(blocks), "out": out,
        "title": deck["meta"]["title"], "slides": len(deck["slides"]),
        "archetypes": {t: types.count(t) for t in sorted(set(types))},
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_pptx(a):
    d = _load(a.deck)
    from . import pptx_export as PE
    res = PE.export(d, a.out, a.theme, inject_theme=not a.no_inject_theme,
                    base_dir=_deck_dir(a.deck))
    fid = PE.fidelity(d, a.out)
    out = {**res, "fidelity": fid["status"], "missing": fid["missing"][:12]}
    if getattr(a, "roundtrip", False):
        from . import pptx_theme, theme_from_pptx as TP
        t = dict(themes.get(a.theme or d.get("theme") or themes.DEFAULT_THEME))
        t.setdefault("mode", "light")
        recovered = TP.to_theme(TP.read_template(a.out), name="roundtrip")
        ex = TP.read_template(a.out)
        out["roundtrip"] = pptx_theme.round_trip_report(t, recovered, ex.get("colors"))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    ok = fid["status"] == "PASS"
    if getattr(a, "roundtrip", False):
        ok = ok and out["roundtrip"]["status"] == "PASS"
    return 0 if ok else 1


def _chart_slides(d):
    return [(i, sl.get("chart") or {}) for i, sl in enumerate(d.get("slides", []), 1)
            if (sl.get("type") or "").lower() == "chart"]


def cmd_chartcheck(a):
    d = _load(a.deck)
    from . import chart_geometry as CG
    tn = a.theme or d.get("theme") or themes.DEFAULT_THEME
    os.makedirs(a.out, exist_ok=True)
    html = os.path.join(a.out, "slides.html")
    build.write_html(d, html, tn, base_dir=_deck_dir(a.deck))
    rows, failed = [], 0
    for i, spec in _chart_slides(d):
        errs = __import__("deckkit.charts", fromlist=["x"]).spec_errors(spec)
        if errs:
            rows.append({"slide": i, "status": "SPEC_FAIL", "errors": errs})
            failed += 1
            continue
        r = CG.audit(html, i - 1, spec)
        failed += 1 if r["status"] != "PASS" else 0
        rows.append({"slide": i, "kind": spec.get("kind"), "status": r["status"],
                     "marks": r["marks_checked"], "issues": r["issues"][:4]})
    print(json.dumps({"deck": os.path.basename(str(a.deck)), "theme": tn,
                      "charts": len(rows), "failed": failed, "results": rows},
                     ensure_ascii=False, indent=2))
    return 1 if failed else 0


def cmd_chartselftest(a):
    """Prove the geometry checker can FAIL: inject corruption into each fixture."""
    d = _load(a.deck)
    from . import chart_geometry as CG
    from . import charts as CH
    tn = a.theme or d.get("theme") or themes.DEFAULT_THEME
    os.makedirs(a.out, exist_ok=True)
    html = os.path.join(a.out, "slides.html")
    build.write_html(d, html, tn, base_dir=_deck_dir(a.deck))

    valid = [(i, s) for i, s in _chart_slides(d) if not CH.spec_errors(s)]
    if not valid:
        print(json.dumps({"status": "FAIL", "detail": "no valid chart fixture"}))
        return 1

    def pick(needs):
        if needs == "multiseries":
            for i, s in valid:
                if len(s.get("series") or []) > 1:
                    return i, s
            return None
        if needs == "line":
            for i, s in valid:
                if (s.get("kind") or "bar") == "line":
                    return i, s
            return None
        for i, s in valid:
            if (s.get("kind") or "bar") != "line":
                return i, s
        return valid[0]

    base_i, base_s = pick("any")
    base = CG.audit(html, base_i - 1, base_s)
    rows = [{"fixture": "baseline-correct", "target_slide": base_i,
             "expected": "PASS", "actual": base["status"]}]
    bad = 0 if base["status"] == "PASS" else 1

    for name, js, needs in CG.NEGATIVE_FIXTURES:
        tgt = pick(needs)
        if tgt is None:
            rows.append({"fixture": name, "expected": "FAIL", "actual": "SKIPPED_NO_FIXTURE"})
            bad += 1
            continue
        ti, ts = tgt
        r = CG.audit(html, ti - 1, ts, mutate=js)
        ok = r["status"] == "FAIL"
        bad += 0 if ok else 1
        rows.append({"fixture": name, "target_slide": ti, "expected": "FAIL",
                     "actual": r["status"],
                     "caught": (r["issues"][0]["check"] if r["issues"] else None)})

    errs = CH.spec_errors({"kind": "bar", "categories": ["x"], "series": [{"values": [1]}]})
    rows.append({"fixture": "bar-without-baseline", "expected": "SPEC_FAIL",
                 "actual": "SPEC_FAIL" if errs else "PASS"})
    bad += 0 if errs else 1

    print(json.dumps({"deck": os.path.basename(str(a.deck)), "fixtures": len(rows),
                      "unexpected": bad, "results": rows}, ensure_ascii=False, indent=2))
    return 1 if bad else 0


def cmd_theme_from(a):
    from . import theme_gen as TG
    t = TG.from_brand(a.brand, name=a.name, mode=a.mode, accent=a.accent,
                      font=a.font, label=a.label)
    path = themes.save_user_theme(a.name, t)
    bad = TG.check_theme(t)
    print(json.dumps({
        "name": a.name, "brand": a.brand, "mode": a.mode, "saved": path,
        "tokens": {k: t[k] for k in ("bg", "surface", "ink", "heading", "primary",
                                     "accent", "accent_text", "on_primary",
                                     "badge", "badge_on")},
        "contrast": "PASS" if not bad else "FAIL", "violations": bad,
    }, ensure_ascii=False, indent=2))
    return 1 if bad else 0


def cmd_themecheck(a):
    from . import theme_gen as TG
    names = a.themes.split(",") if a.themes else list(themes.THEMES)
    rows, failed = [], 0
    for n in names:
        try:
            t = themes.get(n)
        except KeyError as e:
            rows.append({"theme": n, "status": "UNKNOWN", "detail": str(e)})
            failed += 1
            continue
        bad = TG.check_theme(t)
        failed += 1 if bad else 0
        rows.append({"theme": n, "status": "PASS" if not bad else "FAIL",
                     "violations": bad})
    print(json.dumps({"themes_checked": len(rows), "failed": failed, "results": rows},
                     ensure_ascii=False, indent=2))
    return 1 if failed else 0


def cmd_theme_from_pptx(a):
    from . import theme_from_pptx as TP
    ex = TP.read_template(a.pptx)
    t = TP.to_theme(ex, name=a.name, mode=a.mode, font=a.font, label=a.label)
    t["extracted_from"] = ex.get("theme_part")
    path = themes.save_user_theme(a.name, t)
    from . import theme_gen as TG
    bad = TG.check_theme(t)
    sw, sh = ex.get("slide_size") or (0, 0)
    aspect = round(sw / sh, 3) if sh else None
    print(json.dumps({
        "name": a.name, "template": os.path.basename(a.pptx),
        "mode": t.get("mode"), "slide_size": ex.get("slide_size"),
        "template_aspect": aspect,
        "aspect_note": ("模板为 16:9" if aspect and abs(aspect - 16 / 9) < 0.02
                        else "模板非 16:9；deckkit 只吸收配色与字体，版式始终使用 16:9 栅格"),
        "master_bg": ex.get("master_bg"),
        "template_colors": ex.get("colors"),
        "template_fonts": ex.get("fonts", {}).get("minorFont"),
        "saved": path,
        "mapped": {k: t[k] for k in ("bg", "surface", "ink", "heading", "primary",
                                     "accent", "accent_text", "on_primary", "font")},
        "contrast": "PASS" if not bad else "FAIL", "violations": bad,
    }, ensure_ascii=False, indent=2))
    return 1 if bad else 0


def _image_slides(d):
    return [(i, sl) for i, sl in enumerate(d.get("slides", []), 1)
            if (sl.get("type") or "").startswith("image-")]


def cmd_imagecheck(a):
    d = _load(a.deck)
    from . import image_geometry as IG
    from . import images as IM
    tn = a.theme or d.get("theme") or themes.DEFAULT_THEME
    os.makedirs(a.out, exist_ok=True)
    html = os.path.join(a.out, "slides.html")
    build.write_html(d, html, tn, base_dir=_deck_dir(a.deck))
    spec = []
    for i, sl in _image_slides(d):
        errs = IM.spec_errors(sl)
        if errs:
            spec.append({"slide": i, "status": "SPEC_FAIL", "errors": errs})
    r = IG.audit(d, html)
    print(json.dumps({"deck": os.path.basename(str(a.deck)), "theme": tn,
                      "image_slides": len(_image_slides(d)), "spec_failures": spec,
                      "images_checked": r["images_checked"],
                      "status": r["status"], "issues": r["issues"][:10]},
                     ensure_ascii=False, indent=2))
    return 1 if (r["status"] != "PASS" or spec) else 0


def cmd_imageselftest(a):
    """Prove the crop checker can FAIL: inject corruption and expect detection."""
    d = _load(a.deck)
    from . import image_geometry as IG
    tn = a.theme or d.get("theme") or themes.DEFAULT_THEME
    os.makedirs(a.out, exist_ok=True)
    html = os.path.join(a.out, "slides.html")
    build.write_html(d, html, tn, base_dir=_deck_dir(a.deck))
    base = IG.audit(d, html)
    rows = [{"fixture": "crop-correct", "expected": "PASS", "actual": base["status"]}]
    bad = 0 if base["status"] == "PASS" else 1
    for name, js in IG.NEGATIVE_FIXTURES:
        r = IG.audit(d, html, mutate=js)
        ok = r["status"] == "FAIL"
        bad += 0 if ok else 1
        rows.append({"fixture": name, "expected": "FAIL", "actual": r["status"],
                     "caught": (r["issues"][0]["check"] if r["issues"] else None)})
    print(json.dumps({"deck": os.path.basename(str(a.deck)), "fixtures": len(rows),
                      "unexpected": bad, "results": rows}, ensure_ascii=False, indent=2))
    return 1 if bad else 0


def cmd_all(a):
    from . import pipeline
    theme_names = (a.themes.split(",") if a.themes else [a.theme])
    reports = []
    for tn in theme_names:
        outdir = a.out if len(theme_names) == 1 else os.path.join(a.out, tn.strip() or "default")
        rep = pipeline.run(
            a.doc, outdir, tn,
            title=a.title, subtitle=a.subtitle, brand=a.brand, tagline=a.tagline,
            source=a.source, source_label=a.source_label, author=a.author, org=a.org,
            max_slides=a.max_slides, pdf_mode=a.pdf_mode, pages=a.pages,
            do_pptx=not a.no_pptx, do_render=not a.no_render, do_gates=not a.no_gates,
            quiet=not a.verbose)
        md = pipeline.summary_markdown(rep)
        with io.open(os.path.join(outdir, "REPORT.md"), "w", encoding="utf-8") as f:
            f.write(md)
        reports.append(rep)
    failed = [r for r in reports if r["status"] != "PASS"]
    print(json.dumps({"doc": os.path.basename(str(a.doc)),
                      "variants": len(reports), "failed": len(failed),
                      "results": [{"theme": r.get("theme"), "status": r["status"],
                                   "outdir": r["outdir"],
                                   "slides": next(((s.get("detail") or {}).get("slides")
                                                   for s in r["stages"]
                                                   if s["stage"] == "extract"), None),
                                   "failed_stages": r["failed_stages"],
                                   "errors": [s.get("error") for s in r["stages"]
                                              if s.get("error")][:3],
                                   "seconds": r["seconds"]} for r in reports]},
                     ensure_ascii=False, indent=2))
    return 1 if failed else 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="deckkit", description="theme-pluggable PPT beautification")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("themes").set_defaults(fn=cmd_themes)

    c = sub.add_parser("check"); c.add_argument("deck"); c.add_argument("--theme"); c.set_defaults(fn=cmd_check)

    b = sub.add_parser("build"); b.add_argument("deck"); b.add_argument("--theme"); b.add_argument("-o", "--out", default="out"); b.set_defaults(fn=cmd_build)

    r = sub.add_parser("render"); r.add_argument("deck"); r.add_argument("--theme"); r.add_argument("-o", "--out", default="out")
    r.add_argument("--png", action="store_true", default=True); r.add_argument("--no-png", dest="png", action="store_false")
    r.add_argument("--pdf", action="store_true", default=True); r.add_argument("--no-pdf", dest="pdf", action="store_false")
    r.set_defaults(fn=cmd_render)

    g = sub.add_parser("gallery"); g.add_argument("deck"); g.add_argument("-o", "--out", default="gallery")
    g.add_argument("--themes", help="comma separated; default = all")
    g.add_argument("--png", action="store_true", default=False); g.add_argument("--pdf", action="store_true", default=True)
    g.set_defaults(fn=cmd_gallery)

    au = sub.add_parser("audit"); au.add_argument("deck"); au.add_argument("--theme"); au.add_argument("-o", "--out", default="deckkit/out/_audit")
    au.set_defaults(fn=cmd_audit)

    st = sub.add_parser("selftest"); st.add_argument("deck"); st.add_argument("-o", "--out", default="deckkit/out/_selftest")
    st.set_defaults(fn=cmd_selftest)

    ex = sub.add_parser("extract", help="document -> deck.json (docx/pdf/txt/md)")
    ex.add_argument("doc")
    ex.add_argument("-o", "--out", default="deckkit/out/extracted/deck.json")
    ex.add_argument("--title"); ex.add_argument("--subtitle"); ex.add_argument("--brand")
    ex.add_argument("--tagline"); ex.add_argument("--source"); ex.add_argument("--source-label", default="来源")
    ex.add_argument("--author"); ex.add_argument("--org")
    ex.add_argument("--theme"); ex.add_argument("--max-slides", type=int, default=16)
    ex.add_argument("--pages", help="PDF page range, e.g. 14-147 (skips cover matter / references)")
    ex.set_defaults(fn=cmd_extract)

    px = sub.add_parser("pptx", help="deck.json -> native editable .pptx")
    px.add_argument("deck")
    px.add_argument("-o", "--out", default="deckkit/out/deck.pptx")
    px.add_argument("--theme")
    px.add_argument("--no-inject-theme", action="store_true",
                    help="skip writing tokens into the pptx theme part")
    px.add_argument("--roundtrip", action="store_true",
                    help="re-ingest the exported theme and compare tokens")
    px.set_defaults(fn=cmd_pptx)

    cc = sub.add_parser("chartcheck", help="verify chart geometry against declared data")
    cc.add_argument("deck"); cc.add_argument("--theme"); cc.add_argument("-o", "--out", default="deckkit/out/_chartcheck")
    cc.set_defaults(fn=cmd_chartcheck)

    cs = sub.add_parser("chartselftest", help="positive + injected-negative chart fixtures")
    cs.add_argument("deck"); cs.add_argument("--theme"); cs.add_argument("-o", "--out", default="deckkit/out/_chartselftest")
    cs.set_defaults(fn=cmd_chartselftest)

    tf = sub.add_parser("theme-from", help="generate a full theme from a brand colour")
    tf.add_argument("brand")
    tf.add_argument("--name", default="custom")
    tf.add_argument("--mode", choices=["light", "dark"], default="light")
    tf.add_argument("--accent"); tf.add_argument("--font"); tf.add_argument("--label")
    tf.set_defaults(fn=cmd_theme_from)

    tc = sub.add_parser("themecheck", help="WCAG contrast audit for themes")
    tc.add_argument("--themes", help="comma separated; default = all")
    tc.set_defaults(fn=cmd_themecheck)

    tp = sub.add_parser("theme-from-pptx", help="ingest a company .pptx template theme")
    tp.add_argument("pptx")
    tp.add_argument("--name", default="from-template")
    tp.add_argument("--mode", choices=["light", "dark"])
    tp.add_argument("--font"); tp.add_argument("--label")
    tp.set_defaults(fn=cmd_theme_from_pptx)

    ic = sub.add_parser("imagecheck", help="verify image crop geometry on the rendered page")
    ic.add_argument("deck"); ic.add_argument("--theme"); ic.add_argument("-o", "--out", default="deckkit/out/_imagecheck")
    ic.set_defaults(fn=cmd_imagecheck)

    isf = sub.add_parser("imageselftest", help="positive + injected-negative image fixtures")
    isf.add_argument("deck"); isf.add_argument("--theme"); isf.add_argument("-o", "--out", default="deckkit/out/_imageselftest")
    isf.set_defaults(fn=cmd_imageselftest)

    al = sub.add_parser("all", help="document -> gated deck (extract/build/render/pptx/gates)")
    al.add_argument("doc")
    al.add_argument("-o", "--out", default="deckkit/out/pipeline")
    al.add_argument("--theme"); al.add_argument("--themes", help="comma separated variants")
    al.add_argument("--title"); al.add_argument("--subtitle"); al.add_argument("--brand")
    al.add_argument("--tagline"); al.add_argument("--source"); al.add_argument("--source-label", default="来源")
    al.add_argument("--author"); al.add_argument("--org")
    al.add_argument("--max-slides", type=int, default=16)
    al.add_argument("--pdf-mode", choices=["auto", "flow"], default="auto")
    al.add_argument("--pages", help="PDF page range, e.g. 14-147 (skips cover matter / references)")
    al.add_argument("--no-pptx", action="store_true"); al.add_argument("--no-render", action="store_true")
    al.add_argument("--no-gates", action="store_true"); al.add_argument("--verbose", action="store_true")
    al.set_defaults(fn=cmd_all)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
