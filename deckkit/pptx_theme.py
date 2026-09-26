# -*- coding: utf-8 -*-
"""
Write deckkit tokens INTO the exported .pptx theme part.

Why: colours applied per-shape make a deck that looks right but behaves wrong —
in PowerPoint the theme colour picker still shows Office defaults, so recolouring
or re-theming from the ribbon does nothing sensible. Injecting the palette (and
the font scheme, and a master background) turns our export into a proper
template.

Round-trip: `theme-from-pptx` on an exported deck recovers the same tokens, which
is asserted by the CLI self-check.
"""
import os
import re
import shutil
import zipfile

from . import colorutil as CU

A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _c(tag, hexval, sysval=None):
    if sysval:
        return f'<a:{tag}><a:sysClr val="{sysval}" lastClr="{hexval.lstrip("#").upper()}"/></a:{tag}>'
    return f'<a:{tag}><a:srgbClr val="{hexval.lstrip("#").upper()}"/></a:{tag}>'


def scheme_colors(t):
    """Map deckkit tokens onto the OOXML colour slots (round-trip stable)."""
    return {
        "dk1": (t["ink"] if t.get("mode") == "dark" else "#000000", None),
        "lt1": ("#FFFFFF", "window"),
        "dk2": (t["ink"], None),
        "lt2": (t["bg2"], None),
        "accent1": (t["primary"], None),      # brand
        "accent2": (t["accent"], None),       # emphasis
        "accent3": (t["ok"], None),
        "accent4": (t["warn"], None),
        "accent5": (t["danger"], None),
        "accent6": (t["heading"], None),
        "hlink": (t["primary"], None),
        "folHlink": (t["accent"], None),
    }


def _font_name(stack):
    """'微软雅黑','Segoe UI' -> 微软雅黑"""
    m = re.findall(r"'([^']+)'", stack or "")
    return (m[0] if m else (stack or "Microsoft YaHei").split(",")[0].strip())


def theme_xml(t, name="deckkit"):
    cols = scheme_colors(t)
    scheme = "".join(_c(k, v[0], v[1]) for k, v in cols.items())
    latin = _font_name(t.get("font"))
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="{A}" name="{name}">
  <a:themeElements>
    <a:clrScheme name="{name}">{scheme}</a:clrScheme>
    <a:fontScheme name="{name}">
      <a:majorFont><a:latin typeface="{latin}"/><a:ea typeface="{latin}"/><a:cs typeface=""/>
        <a:font script="Hans" typeface="{latin}"/></a:majorFont>
      <a:minorFont><a:latin typeface="{latin}"/><a:ea typeface="{latin}"/><a:cs typeface=""/>
        <a:font script="Hans" typeface="{latin}"/></a:minorFont>
    </a:fontScheme>
    <a:fmtScheme name="{name}">
      <a:fillStyleLst>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      </a:fillStyleLst>
      <a:lnStyleLst>
        <a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
        <a:ln w="12700"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
        <a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
      </a:lnStyleLst>
      <a:effectStyleLst>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
      </a:effectStyleLst>
      <a:bgFillStyleLst>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      </a:bgFillStyleLst>
    </a:fmtScheme>
  </a:themeElements>
</a:theme>'''


def _inject_master_bg(xml, bg):
    solid = (f'<p:bg><p:bgPr><a:solidFill>'
             f'<a:srgbClr val="{bg.lstrip("#").upper()}"/></a:solidFill>'
             f'<a:effectLst/></p:bgPr></p:bg>')
    if "<p:bg>" in xml:
        return re.sub(r"<p:bg>.*?</p:bg>", solid, xml, count=1, flags=re.S)
    return re.sub(r"(<p:cSld[^>]*>)", r"\1" + solid, xml, count=1)


def apply_to_pptx(path, theme):
    """Rewrite theme1.xml (+ master background) inside an existing .pptx."""
    tmp = path + ".tmp"
    with zipfile.ZipFile(path) as zin, \
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if re.match(r"ppt/theme/theme\d+\.xml$", item.filename):
                data = theme_xml(theme).encode("utf-8")
            elif re.match(r"ppt/slideMasters/slideMaster\d+\.xml$", item.filename):
                xml = data.decode("utf-8")
                data = _inject_master_bg(xml, theme["bg"]).encode("utf-8")
            zout.writestr(item, data)
    shutil.move(tmp, path)
    return path


def round_trip_report(original, recovered, extracted_colors=None,
                      keys=("bg", "accent", "ink", "font")):
    """Verify the palette we WROTE is exactly what a reader reads back.

    Two levels:
      * seed fidelity  — accent1/accent2/lt1/dk2 literals must match byte-for-byte
      * token stability — derived tokens (bg, accent, ink, font) must survive the
        re-derivation; `primary` is regenerated from the brand seed on purpose
        (the brand-bar colour must stay dark enough for white text), so it is
        checked against accent1 rather than against the derived value.
    """
    cols = (extracted_colors or {})
    rows, bad = [], 0

    if cols:
        seeds = [("accent1", original.get("primary")),
                 ("accent2", original.get("accent")),
                 ("dk2", original.get("ink")),
                 ("lt2", original.get("bg2"))]
        for slot, written in seeds:
            got = cols.get(slot)
            same = (written or "").upper() == (got or "").upper()
            bad += 0 if same else 1
            rows.append({"slot": slot, "written": written, "read_back": got,
                         "match": same, "kind": "seed"})

    for k in keys:
        a, b = original.get(k), recovered.get(k)
        if k == "font":
            same = _font_name(a) == _font_name(b)
        else:
            same = (a or "").upper() == (b or "").upper()
        bad += 0 if same else 1
        rows.append({"token": k, "written": a, "read_back": b, "match": same,
                     "kind": "derived"})

    return {"status": "PASS" if not bad else "FAIL", "mismatches": bad, "checks": rows}
