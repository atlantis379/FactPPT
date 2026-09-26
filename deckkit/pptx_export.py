# -*- coding: utf-8 -*-
"""
PPTX export: mirror the deckkit archetypes into NATIVE, editable PowerPoint
objects using the same theme tokens as the HTML/CSS pipeline.

* every semantic string (title, subtitle, card/step/kpi text, footer) is a real
  editable text run — nothing is baked into an image
* only the decorative motif art is a bitmap (rendered per theme colour)
* geometry is the same 1280x720 grid as the HTML layouts, so both outputs match

px -> EMU : 9525 (1280 px == 12192000 EMU == 13.333 in)
px -> pt  : 0.75
"""
import os
import re

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

from . import motifs as MOTIFS
from . import motif_png, themes

EMU_PER_PX = 9525
W, H = 1280, 720

FOOT_H = 34
BRAND_H = 60


def E(px):
    return Emu(int(round(px * EMU_PER_PX)))


def P(px):
    return Pt(round(px * 0.75, 1))


def C(hexstr):
    h = str(hexstr).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _plain(s):
    """strip the <br/> allowance used by the HTML layouts"""
    return re.sub(r"<br\s*/?>", "\n", str(s or ""))


class Builder:
    def __init__(self, theme):
        self.t = theme
        self.prs = Presentation()
        self.prs.slide_width = E(W)
        self.prs.slide_height = E(H)
        self.blank = self.prs.slide_layouts[6]
        self._motifs = {}

    # ---------------------------------------------------------------- helpers
    def slide(self):
        return self.prs.slides.add_slide(self.blank)

    def _noshadow(self, shp):
        try:
            shp.shadow.inherit = False
        except Exception:  # noqa: BLE001
            pass
        return shp

    def rect(self, s, x, y, w, h, fill, line=None, shape=MSO_SHAPE.RECTANGLE, lw=1.0):
        shp = s.shapes.add_shape(shape, E(x), E(y), E(w), E(h))
        if fill is None:
            shp.fill.background()
        else:
            shp.fill.solid()
            shp.fill.fore_color.rgb = C(fill)
        if line is None:
            shp.line.fill.background()
        else:
            shp.line.color.rgb = C(line)
            shp.line.width = Pt(lw)
        return self._noshadow(shp)

    def rrect(self, s, x, y, w, h, fill, line=None, lw=1.0):
        return self.rect(s, x, y, w, h, fill, line, MSO_SHAPE.ROUNDED_RECTANGLE, lw)

    def text(self, s, x, y, w, h, runs, size=12.5, color=None, bold=False,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, spacing=1.15):
        """runs semantics:
             str                        -> one paragraph (\\n splits paragraphs)
             [(txt,sz,bold,color), ...] -> INLINE runs inside ONE paragraph
             [[run, run], [run, run]]   -> explicit list of paragraphs
        """
        tb = s.shapes.add_textbox(E(x), E(y), E(w), E(h))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

        if isinstance(runs, str):
            paras = [[(ln, size, bold, color)] for ln in _plain(runs).split("\n")]
        elif runs and isinstance(runs[0], (list, tuple)) and runs[0] and \
                isinstance(runs[0][0], (list, tuple)):
            paras = runs
        else:
            paras = [list(runs)]

        for pi, para in enumerate(paras):
            p = tf.paragraphs[0] if pi == 0 else tf.add_paragraph()
            p.alignment = align
            p.line_spacing = spacing
            for item in para:
                txt, sz, bd, cl = (list(item) + [size, bold, color])[:4]
                for li, line in enumerate(_plain(txt).split("\n")):
                    if li:
                        p = tf.add_paragraph()
                        p.alignment = align
                        p.line_spacing = spacing
                    r = p.add_run()
                    r.text = line
                    r.font.name = "微软雅黑"
                    r.font.size = P(sz)
                    r.font.bold = bd
                    r.font.color.rgb = C(cl or self.t["ink"])
        return tb

    def pic(self, s, motif, x, y, w, h, color=None):
        col = color or self.t["accent"]
        if motif not in self._motifs:
            self._motifs[motif] = motif_png.ensure(motif, col)
        s.shapes.add_picture(self._motifs[motif], E(x), E(y), E(w), E(h))

    def figbox(self, s, motif, x, y, w, h):
        self.rrect(s, x, y, w, h, self.t["surface"], self.t["line"], 0.75)
        pad = 0.12
        self.pic(s, motif, x + w * pad, y + h * pad, w * (1 - 2 * pad), h * (1 - 2 * pad))

    # ------------------------------------------------------------ common chrome
    def bg(self, s):
        """Full-bleed theme background — without it a dark theme renders on white
        and light headings become invisible."""
        self.rect(s, 0, 0, W, H, self.t["bg"])

    def brand(self, s, meta, sl=None):
        self.rect(s, 0, 0, W, BRAND_H, self.t["primary"])
        # a subtle accent edge instead of a gradient (PPTX gradients vary by viewer)
        self.rect(s, 0, BRAND_H - 3, W, 3, self.t["accent"])
        self.text(s, 30, 0, 900, BRAND_H, meta.get("brand", ""), 21,
                  self.t["on_primary"], True, anchor=MSO_ANCHOR.MIDDLE)
        if not (sl or {}).get("chip"):
            self.text(s, 880, 0, 340, BRAND_H, meta.get("tagline", ""), 12,
                      self.t["on_primary"], False, align=PP_ALIGN.RIGHT,
                      anchor=MSO_ANCHOR.MIDDLE)

    def tblock(self, s, title, sub):
        self.text(s, 30, 66, 1120, 40, title, 27, self.t["heading"], True)
        if sub:
            self.text(s, 30, 108, 1120, 24, sub, 12.5, self.t["ink2"], True)

    def pnum(self, s, n):
        self.rect(s, 1236, 15, 28, 28, self.t["accent"], shape=MSO_SHAPE.OVAL)
        self.text(s, 1236, 15, 28, 28, f"{n:02d}", 11.5, self.t["on_primary"], True,
                  align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

    def foot(self, s, meta, page):
        self.rect(s, 0, H - FOOT_H, W, FOOT_H, self.t["bg2"])
        left = f"{meta.get('source_label','Source')}: {meta.get('source','')}"
        if page:
            left += f" p.{page}"
        self.text(s, 30, H - FOOT_H + 9, 800, 18, left, 10.5, self.t["muted"])
        self.text(s, 950, H - FOOT_H + 9, 300, 18, meta.get("footer_right", ""), 10.5,
                  self.t["muted"], align=PP_ALIGN.RIGHT)

    def callout(self, s, label, text):
        if not text:
            return
        y = 570 + 46 + 7
        h = 62
        self.rrect(s, 30, y, W - 60, h, self.t["accent_soft"], self.t["line"], 0.75)
        self.rect(s, 30, y, 5, h, self.t["primary"])
        lab = f"{label}｜" if label else ""
        self.text(s, 50, y + 10, W - 110, h - 20,
                  [(lab, 12, True, self.t["heading"]), (text, 12, False, self.t["ink2"])],
                  12, anchor=MSO_ANCHOR.MIDDLE)


    @staticmethod
    def _plain(value) -> str:
        return str(value or "").replace("<b>", "").replace("</b>", "")

    def _subtitle(self, sl) -> str:
        """Mirror layouts.page_chrome so HTML and PPTX show the same source line."""
        sub = sl.get("subtitle")
        if sub:
            return sub
        ref = sl.get("source_ref")
        if isinstance(ref, dict):
            page, kind = ref.get("page"), ref.get("kind", "")
        else:
            page, kind = ref, ""
        if page:
            return f"教材第 {page} 页" + (f"（{kind}）" if kind else "")
        return ""

    def chip(self, s, sl):
        label = sl.get("chip") or ""
        if not label:
            return
        width = max(96, 22 + 14 * len(label))
        x = W - 86 - width
        y = (BRAND_H - 30) // 2
        self.rrect(s, x, y, width, 30, self.t["surface"], self.t["line"], 0.75)
        self.text(s, x, y, width, 30, label, 11.5, self.t["heading"], True,
                  align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

    def keypoint(self, s, sl):
        kp = sl.get("keypoint")
        if not kp:
            return
        tone = sl.get("keypoint_tone") or "info"
        if isinstance(kp, dict):
            tone = kp.get("tone", tone)
            text = kp.get("text", "")
        else:
            text = str(kp)
        text = self._plain(text)
        if not text:
            return
        fill = {"warn": self.t.get("warn_soft"), "danger": self.t.get("danger_soft"),
                "ok": self.t.get("ok_soft")}.get(tone, self.t.get("accent_soft"))
        bar = {"warn": self.t.get("warn"), "danger": self.t.get("danger"),
               "ok": self.t.get("ok")}.get(tone, self.t.get("accent"))
        h = 58
        y = H - 46 - h
        self.rrect(s, 30, y, W - 60, h, fill or self.t["bg2"], self.t["line"], 0.75)
        self.rect(s, 30, y, 5, h, bar or self.t["accent"])
        self.text(s, 50, y + 8, W - 110, h - 16, text, 12, self.t["ink2"], False,
                  anchor=MSO_ANCHOR.MIDDLE)

    # --------------------------------------------------- teaching carriers
    def matrix(self, s, sl, meta, n):
        cols = sl.get("columns") or []
        rows = sl.get("rows") or []
        if not cols or not rows:
            return
        nr, nc = len(rows) + 1, len(cols)
        tw = W - 60
        avail = H - 46 - 58 - 158
        th = min(44, max(26, avail // max(1, nr) - 6))
        shape = s.shapes.add_table(nr, nc, E(30), E(158), E(tw), E(th * nr))
        table = shape.table
        for c, name in enumerate(cols):
            cell = table.cell(0, c)
            cell.text = self._plain(name)
            cell.fill.solid()
            cell.fill.fore_color.rgb = C(self.t["primary"])
            for para in cell.text_frame.paragraphs:
                for run in para.runs:
                    run.font.size = Pt(11)
                    run.font.bold = True
                    run.font.color.rgb = C(self.t["on_primary"])
        for r, row in enumerate(rows, start=1):
            for c in range(nc):
                cell = table.cell(r, c)
                cell.text = self._plain(row[c] if c < len(row) else "")
                cell.fill.solid()
                cell.fill.fore_color.rgb = C(self.t["surface"] if r % 2 else self.t["bg2"])
                for para in cell.text_frame.paragraphs:
                    for run in para.runs:
                        run.font.size = Pt(10.5)
                        run.font.bold = (c == 0)
                        run.font.color.rgb = C(self.t["heading"] if c == 0
                                               else self.t["ink2"])

    def quickref(self, s, sl, meta, n):
        items = sl.get("items") or []
        cols = max(1, int(sl.get("cols", 3)))
        if not items:
            return
        rows = (len(items) + cols - 1) // cols
        gap = 14
        ch = min(150, int((H - 46 - 58 - 156 - gap * (rows - 1)) / max(1, rows)))
        cw = (W - 60 - gap * (cols - 1)) / cols
        for i, item in enumerate(items):
            r, c = divmod(i, cols)
            x = 30 + c * (cw + gap)
            y = 156 + r * (ch + gap)
            self.rrect(s, x, y, cw, ch, self.t["surface"], self.t["line"], 0.75)
            self.rect(s, x, y, 4, ch, self.t["accent"])
            self.text(s, x + 14, y + 12, cw - 28, 22,
                      self._plain(item.get("title", "")), 12.5, self.t["heading"], True)
            self.text(s, x + 14, y + 38, cw - 28, ch - 50,
                      self._plain(item.get("body", "")), 11.5, self.t["ink2"])

    def flow(self, s, sl, meta, n):
        rows = sl.get("flow") or []
        if not rows:
            return
        y = 168
        for row in rows:
            if isinstance(row, dict):
                row = [row]
            boxes = [b for b in row if isinstance(b, dict)]
            if not boxes:
                continue
            gap = 34
            bw = min(300, int((W - 60 - gap * (len(boxes) - 1)) / max(1, len(boxes))))
            x = 30
            for index, box in enumerate(boxes):
                decision = box.get("kind") == "decision"
                self.rrect(s, x, y, bw, 76, self.t["surface"],
                           self.t["warn"] if decision else self.t["accent"],
                           1.5 if decision else 1.0)
                self.text(s, x + 10, y + 8, bw - 20, 60,
                          self._plain(box.get("text", "")), 11.5, self.t["heading"], True,
                          anchor=MSO_ANCHOR.MIDDLE)
                x += bw
                if index < len(boxes) - 1:
                    self.text(s, x + 4, y + 22, gap - 8, 30, "→", 15,
                              self.t["muted"], True, align=PP_ALIGN.CENTER)
                    x += gap
            y += 96


    # ------------------------------------------------------------- archetypes
    def cover(self, s, sl, meta):
        self.rect(s, 0, 0, W, H, self.t["primary"])
        self.pic(s, sl.get("motif", "layers"), 700, 120, 520, 480, self.t["accent"])
        self.text(s, 58, 46, 900, 24, sl.get("kicker", ""), 13, self.t["accent"], True)
        self.text(s, 58, 84, 860, 200, _plain(sl.get("title", "")), 44,
                  self.t["on_primary"], True, spacing=1.12)
        self.rect(s, 58, 300, 66, 5, self.t["accent"])
        self.text(s, 58, 322, 820, 34, sl.get("subtitle", ""), 18,
                  self.t["on_primary"], False)
        if sl.get("body"):
            self.text(s, 58, 368, 760, 90, sl.get("body", ""), 14,
                      self.t["on_primary"], False, spacing=1.55)
        lines = [x for x in (sl.get("meta_lines") or
                             [meta.get("author", ""), meta.get("org", "")]) if x]
        if lines:
            self.text(s, 58, 590, 900, 80, "\n".join(_plain(x) for x in lines), 13,
                      self.t["on_primary"], False, spacing=1.5)

    def statement(self, s, sl, meta, n):
        st = sl
        self.rrect(s, 90, 180, W - 180, 240, self.t["surface"], self.t["line"], 0.75)
        self.rect(s, 90, 180, 6, 240, self.t["accent"])
        self.text(s, 116, 206, W - 240, 24, st.get("kicker", "KEY POINT"), 13,
                  self.t["accent"], True)
        self.text(s, 116, 240, W - 240, 150, st.get("body", ""), 19,
                  self.t["ink"], True, spacing=1.4)

    def steps(self, s, sl, meta, n):
        items = (sl.get("steps") or [])[:4]
        gap = 14
        cw = (W - 60 - gap * (len(items) - 1)) / max(1, len(items))
        for i, it in enumerate(items):
            x = 30 + i * (cw + gap)
            self.rrect(s, x, 168, cw, 392, self.t["surface"], self.t["line"], 0.75)
            badge = self.t["badge"] if i % 2 == 0 else self.t["accent"]
            self.rect(s, x + 14, 180, 34, 34, badge, shape=MSO_SHAPE.OVAL)
            self.text(s, x + 14, 180, 34, 34, f"{i+1:02d}", 14, self.t["badge_on"], True,
                      align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
            self.text(s, x + 58, 182, cw - 72, 22, it.get("title", ""), 14.5,
                      self.t["heading"], True)
            if it.get("qualifier"):
                self.text(s, x + 58, 204, cw - 72, 18, it.get("qualifier", ""), 11.5,
                          self.t["accent"], True)
            self.text(s, x + 14, 232, cw - 28, 60, it.get("body", ""), 12,
                      self.t["ink2"], False, spacing=1.45)
            self.figbox(s, it.get("motif") or MOTIFS.ROTATION[i], x + 14, 300, cw - 28, 244)
        rail = (sl.get("rail") or [])[:len(items)]
        if rail:
            ry = 570
            for i, lab in enumerate(rail):
                x = 30 + i * (cw + gap)
                self.rect(s, x, ry + 4, cw, 3, self.t["line"])
                self.rect(s, x + cw / 2 - 6, ry, 12, 12, self.t["accent"], shape=MSO_SHAPE.OVAL)
                self.text(s, x, ry + 20, cw, 18, lab, 11.5, self.t["heading"], True,
                          align=PP_ALIGN.CENTER)
        self.callout(s, sl.get("callout_label", ""), sl.get("callout", ""))

    def cards(self, s, sl, meta, n):
        items = sl.get("cards") or []
        cols = int(sl.get("cols", 3))
        rows = (len(items) + cols - 1) // cols
        gh = {1: 174, 2: 124, 3: 96}[min(rows, 3)]
        gap = 15
        cw = (W - 60 - gap * (cols - 1)) / cols
        for i, it in enumerate(items):
            r, c = divmod(i, cols)
            x = 30 + c * (cw + gap)
            y = 156 + r * (gh + gap)
            self.rrect(s, x, y, cw, gh, self.t["surface"], self.t["line"], 0.75)
            tone = it.get("tone", "")
            bar = {"ok": self.t["ok"], "warn": self.t["warn"], "danger": self.t["danger"]}.get(tone, self.t["accent"])
            self.rect(s, x, y, 4, gh, bar)
            self.rect(s, x + 15, y + 17, 8, 8, bar, shape=MSO_SHAPE.OVAL)
            self.text(s, x + 31, y + 12, cw - 46, 22, it.get("title", ""), 14.5,
                      self.t["heading"], True)
            self.text(s, x + 15, y + 38, cw - 30, gh - 56, it.get("body", ""), 12,
                      self.t["ink2"], False, spacing=1.45)
            if it.get("tag"):
                self.text(s, x + 15, y + gh - 18, cw - 30, 14, it["tag"], 10,
                          self.t["muted"], True)
        f = sl.get("figure")
        if f:
            top = {1: 350, 2: 448, 3: 448}[min(rows, 3)]
            fw, fh = sl.get("figure_size", [470, 235])
            self.figbox(s, f, (W - fw) / 2, top, fw, fh)

    def kpi(self, s, sl, meta, n):
        items = (sl.get("kpis") or [])[:4]
        gap = 15
        cw = (W - 60 - gap * (len(items) - 1)) / max(1, len(items))
        for i, k in enumerate(items):
            x = 30 + i * (cw + gap)
            self.rrect(s, x, 156, cw, 146, self.t["surface"], self.t["line"], 0.75)
            if k.get("tag"):
                self.text(s, x + 12, 167, cw - 24, 14, k["tag"], 10, self.t["muted"],
                          True, align=PP_ALIGN.RIGHT)
            self.text(s, x + 16, 176, cw - 32, 40,
                      [(str(k.get("value", "")), 34, True, self.t["heading"]),
                       (str(k.get("unit", "")), 17, True, self.t["accent"])], 34)
            self.text(s, x + 16, 224, cw - 32, 66, k.get("label", ""), 12.5,
                      self.t["ink2"], False, spacing=1.4)
        f = sl.get("figure")
        if f:
            fw, fh = sl.get("figure_size", [470, 200])
            self.figbox(s, f, (W - fw) / 2, 322, fw, fh)

    def compare(self, s, sl, meta, n):
        L = sl.get("left", {})
        R = sl.get("right", {})
        gap = 16
        cw = (W - 60 - gap) / 2
        for i, (pnl, side) in enumerate(((L, "a"), (R, "b"))):
            x = 30 + i * (cw + gap)
            fill = self.t["danger_soft"] if side == "a" else self.t["accent_soft"]
            line = self.t["danger"] if side == "a" else self.t["accent"]
            head = self.t["danger"] if side == "a" else self.t["accent"]
            self.rrect(s, x, 156, cw, 186, fill, line, 1.0)
            self.text(s, x + 18, 172, cw - 36, 22, pnl.get("heading", ""), 15, head, True)
            if pnl.get("tag"):
                self.text(s, x + 18, 172, cw - 36, 14, pnl["tag"], 10.5, self.t["muted"],
                          True, align=PP_ALIGN.RIGHT)
            self.text(s, x + 18, 204, cw - 36, 124, pnl.get("body", ""), 12.5,
                      self.t["ink2"], False, spacing=1.5)
        f = sl.get("figure")
        if f:
            fw, fh = sl.get("figure_size", [400, 200])
            self.figbox(s, f, (W - fw) / 2, 362, fw, fh)
        self.callout(s, sl.get("callout_label", ""), sl.get("callout", ""))

    def timeline(self, s, sl, meta, n):
        items = (sl.get("items") or [])[:4]
        gap = 16
        cw = (W - 80 - gap * (len(items) - 1)) / max(1, len(items))
        self.rect(s, 40, 284, W - 80, 4, self.t["line"])
        for i, it in enumerate(items):
            x = 40 + i * (cw + gap)
            self.rect(s, x + cw / 2 - 8, 276, 16, 16, self.t["accent"], shape=MSO_SHAPE.OVAL)
            if i % 2 == 0:
                y = 210
            else:
                y = 320
            self.rrect(s, x, y, cw, 96, self.t["surface"], self.t["line"], 0.75)
            self.text(s, x + 12, y + 10, cw - 24, 20, it.get("title", ""), 13.5,
                      self.t["heading"], True)
            self.text(s, x + 12, y + 34, cw - 24, 56, it.get("body", ""), 12,
                      self.t["ink2"], False, spacing=1.4)
        self.callout(s, sl.get("callout_label", ""), sl.get("callout", ""))

    def table(self, s, sl, meta, n):
        cols = sl.get("columns") or []
        rows = sl.get("rows") or []
        if not cols:
            return
        nr, nc = len(rows) + 1, len(cols)
        tw = W - 60
        avail_h = 720 - FOOT_H - 158 - 16
        th = min(46, max(28, avail_h // max(1, nr) - 6))
        shape = s.shapes.add_table(nr, nc, E(30), E(158), E(tw), E(th * nr))
        tbl = shape.table
        for c, name in enumerate(cols):
            cell = tbl.cell(0, c)
            cell.text = str(name)
            cell.fill.solid()
            cell.fill.fore_color.rgb = C(self.t["primary"])
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.LEFT
                for r in p.runs:
                    r.font.name = "微软雅黑"
                    r.font.size = P(12.5)
                    r.font.bold = True
                    r.font.color.rgb = C(self.t["on_primary"])
        for ri, row in enumerate(rows, start=1):
            for ci in range(nc):
                cell = tbl.cell(ri, ci)
                cell.text = str(row[ci]) if ci < len(row) else ""
                cell.fill.solid()
                cell.fill.fore_color.rgb = C(self.t["surface"] if ri % 2 else self.t["bg2"])
                for p in cell.text_frame.paragraphs:
                    for r in p.runs:
                        r.font.name = "微软雅黑"
                        r.font.size = P(12)
                        r.font.color.rgb = C(self.t["ink2"])


    def _alpha(self, shape, pct):
        """Give a solid fill transparency (python-pptx has no direct API)."""
        from pptx.oxml.ns import qn
        srgb = shape.fill._xPr.find(qn("a:solidFill"))
        if srgb is None:
            return
        clr = srgb.find(qn("a:srgbClr"))
        if clr is None:
            return
        alpha = clr.makeelement(qn("a:alpha"), {"val": str(int(pct * 1000))})
        clr.append(alpha)

    def _pic(self, s, src, box, focal, base_dir=None):
        """Native picture with a deterministic OOXML crop (same plan as HTML)."""
        from . import images as IM
        path = src if os.path.isabs(src) else os.path.join(base_dir or ".", src)
        size = IM.probe(path)
        if size is None:
            self.rrect(s, box["x"], box["y"], box["w"], box["h"], self.t["surface"],
                       self.t["line"], 1.0)
            self.text(s, box["x"] + 12, box["y"] + box["h"] / 2 - 10, box["w"] - 24, 20,
                      f"[图片缺失] {src}", 11, self.t["muted"], True, align=PP_ALIGN.CENTER)
            return None
        fx, fy = (focal or [0.5, 0.5])[:2]
        plan = IM.crop_plan(size[0], size[1], box["w"], box["h"], fx, fy)
        pic = s.shapes.add_picture(path, E(box["x"]), E(box["y"]), E(box["w"]), E(box["h"]))
        c = plan["ooxml_crop"]
        pic.crop_left, pic.crop_right = c["left"], c["right"]
        pic.crop_top, pic.crop_bottom = c["top"], c["bottom"]
        return plan

    def image_hero(self, s, sl, meta, n, base_dir=None):
        from . import images as IM
        box = IM.slot_boxes(sl)[0]
        self._pic(s, sl.get("src", ""), box, sl.get("focal"), base_dir)
        scrim = self.rect(s, 0, 0, int(W * 0.62), H, self.t["primary"])
        self._alpha(scrim, 88)
        self.text(s, 58, 210, 700, 24, sl.get("kicker", ""), 13, self.t["on_primary"], True)
        self.text(s, 58, 244, 760, 120, sl.get("title", ""), 40, self.t["on_primary"], True)
        self.text(s, 58, 372, 720, 30, sl.get("subtitle", ""), 17, self.t["on_primary"])
        if sl.get("body"):
            self.text(s, 58, 410, 700, 80, sl["body"], 13, self.t["on_primary"],
                      False, spacing=1.55)

    def image_split(self, s, sl, meta, n, base_dir=None):
        from . import images as IM
        box = IM.slot_boxes(sl)[0]
        self._pic(s, sl.get("src", ""), box, sl.get("focal"), base_dir)
        side = (sl.get("side") or "left").lower()
        tx = 658 if side == "left" else 30
        tw = 592
        self.text(s, tx, 176, tw, 40, sl.get("title", ""), 26, self.t["heading"], True)
        self.text(s, tx, 222, tw, 24, sl.get("subtitle", ""), 14, self.t["ink2"], True)
        y = 262
        for p in (sl.get("points") or [])[:6]:
            self.rect(s, tx + 2, y + 8, 6, 6, self.t["accent"], shape=MSO_SHAPE.OVAL)
            self.text(s, tx + 18, y, tw - 18, 46, p, 13, self.t["ink"], False, spacing=1.5)
            y += 50
        if sl.get("note"):
            self.text(s, tx, 588, tw, 30, sl["note"], 11, self.t["muted"], False, spacing=1.4)

    def image_grid(self, s, sl, meta, n, base_dir=None):
        from . import images as IM
        boxes = IM.slot_boxes(sl)
        for i, it in enumerate((sl.get("images") or [])[:4]):
            box = boxes[min(i, len(boxes) - 1)]
            self._pic(s, it.get("src", ""), box, it.get("focal"), base_dir)
            if it.get("caption"):
                self.text(s, box["x"], box["y"] + box["h"] + 8, box["w"], 20,
                          it["caption"], 12.5, self.t["ink2"])

    def chart(self, s, sl, meta, n):
        """Native PPTX chart built from the SAME geometry as the HTML/SVG chart."""
        from . import charts as CH
        spec = sl.get("chart") or {}
        errs = CH.spec_errors(spec)
        if errs:
            self.rrect(s, 60, 200, W - 120, 120, self.t["danger_soft"], self.t["danger"], 1.0)
            self.text(s, 84, 222, W - 168, 80,
                      "图表未通过规范校验：" + "；".join(errs), 13, self.t["danger"], True)
            return
        plot = {"x": 90, "y": 186, "w": 1090, "h": 300}
        g = CH.compute(spec, plot)
        pal = [self.t["accent"], self.t["primary"], self.t["ok"], self.t["warn"], self.t["danger"]]

        # gridlines + y ticks
        for tk in g["ticks"]:
            self.rect(s, plot["x"], tk["y"], plot["w"], 1, self.t["line"])
            lab = f'{tk["value"]:.0f}' if abs(tk["value"]) >= 1 or tk["value"] == 0 else f'{tk["value"]:.2f}'
            self.text(s, plot["x"] - 62, tk["y"] - 9, 52, 18, lab, 11,
                      self.t["muted"], False, align=PP_ALIGN.RIGHT)
        # baseline
        by = plot["y"] + plot["h"] - (g["baseline"] - g["y_min"]) / (g["y_max"] - g["y_min"]) * plot["h"]
        self.rect(s, plot["x"], by - 1, plot["w"], 2, self.t["ink2"])
        # categories
        for ci, c in enumerate(g["categories"]):
            cx = plot["x"] + g["slot"] * (ci + 0.5)
            self.text(s, cx - 60, plot["y"] + plot["h"] + 8, 120, 18, str(c), 11.5,
                      self.t["ink2"], False, align=PP_ALIGN.CENTER)
        # marks
        if g["kind"] == "line":
            for si, pts in enumerate(g["points"]):
                for a, b2 in zip(pts, pts[1:]):
                    ln = s.shapes.add_connector(1, E(a["x"]), E(a["y"]), E(b2["x"]), E(b2["y"]))
                    ln.line.color.rgb = C(pal[si % len(pal)])
                    ln.line.width = Pt(2.25)
                for p in pts:
                    self.rect(s, p["x"] - 5, p["y"] - 5, 10, 10, pal[si % len(pal)],
                              shape=MSO_SHAPE.OVAL)
                    self.text(s, p["x"] - 34, p["y"] - 26, 68, 16, f'{p["value"]:g}', 11,
                              self.t["ink2"], False, align=PP_ALIGN.CENTER)
        else:
            for b in g["bars"]:
                self.rect(s, b["x"], b["y"], b["w"], max(1.0, b["h"]), pal[b["series"] % len(pal)])
                self.text(s, b["x"] + b["w"] / 2 - 34, b["y"] - 20, 68, 16, f'{b["value"]:g}',
                          11, self.t["ink2"], False, align=PP_ALIGN.CENTER)
        # legend
        if len(g["series_names"]) > 1:
            lx = plot["x"]
            for si, name in enumerate(g["series_names"]):
                self.rect(s, lx, 158, 12, 12, pal[si % len(pal)])
                self.text(s, lx + 18, 156, 200, 16, name, 11.5, self.t["ink2"])
                lx += 40 + 15 * len(name)
        if sl.get("note"):
            self.text(s, 30, 560, W - 60, 34, sl["note"], 11, self.t["muted"], False, spacing=1.4)


ARCH = {
    "cover": "cover", "closing": "cover", "statement": "statement", "steps": "steps",
    "cards": "cards", "kpi": "kpi", "compare": "compare", "timeline": "timeline",
    "table": "table", "chart": "chart",
    "matrix": "matrix", "quickref": "quickref", "flow": "flow",
    "image-hero": "image_hero", "image-split": "image_split", "image-grid": "image_grid",
}


def export(deck, out_path, theme_name=None, inject_theme=True, base_dir=None):
    meta = deck.get("meta", {})
    tn = theme_name or deck.get("theme") or themes.DEFAULT_THEME
    t = themes.get(tn)
    t = dict(t)
    t.setdefault("mode", "light")
    b = Builder(t)
    for i, sl in enumerate(deck.get("slides", []), start=1):
        kind = (sl.get("type") or "cards").lower()
        fn = ARCH.get(kind)
        if fn is None:
            continue
        s = b.slide()
        if kind in ("cover", "closing"):
            b.cover(s, sl, meta)
            continue
        b.bg(s)
        b.brand(s, meta, sl)
        b.pnum(s, i)
        b.tblock(s, sl.get("title", ""), b._subtitle(sl))
        if kind.startswith("image-"):
            getattr(b, fn)(s, sl, meta, i, base_dir)
        else:
            getattr(b, fn)(s, sl, meta, i)
        b.chip(s, sl)
        b.keypoint(s, sl)
        ref = sl.get("source_ref")
        foot_page = ref.get("page") if isinstance(ref, dict) else sl.get("source_page")
        b.foot(s, meta, foot_page)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    b.prs.save(out_path)

    # make the export a real template: palette + fonts + master background
    if inject_theme:
        from . import pptx_theme
        pptx_theme.apply_to_pptx(out_path, t)

    return {"out": out_path, "slides": len(b.prs.slides._sldIdLst), "theme": tn,
            "theme_injected": bool(inject_theme)}


def readback_text(path):
    """All visible text in the PPTX (for fidelity checking)."""
    prs = Presentation(path)
    chunks = []
    for s in prs.slides:
        for shp in s.shapes:
            if shp.has_text_frame:
                chunks.append(shp.text_frame.text)
            if getattr(shp, "has_table", False) and shp.has_table:
                for row in shp.table.rows:
                    for cell in row.cells:
                        chunks.append(cell.text)
    return "\n".join(chunks)


def fidelity(deck, pptx_path):
    """Every deck string must be present, verbatim, in the PPTX."""
    text = readback_text(pptx_path)
    norm = lambda s: "".join(str(s).split())
    flat = norm(text)
    missing = []
    for i, sl in enumerate(deck.get("slides", []), 1):
        for key in ("title", "subtitle", "body", "callout"):
            v = sl.get(key)
            if v and norm(_plain(v)) not in flat:
                missing.append((i, key, str(v)[:34]))
        for coll, fields in (("cards", ("title", "body")), ("steps", ("title", "body", "qualifier")),
                             ("kpis", ("value", "label")), ("items", ("title", "body"))):
            for it in sl.get(coll, []) or []:
                for f in fields:
                    v = it.get(f)
                    if v and norm(v) not in flat:
                        missing.append((i, f"{coll}.{f}", str(v)[:34]))
        for side in ("left", "right"):
            for f in ("heading", "body"):
                v = (sl.get(side) or {}).get(f)
                if v and norm(v) not in flat:
                    missing.append((i, f"{side}.{f}", str(v)[:34]))
        for row in sl.get("rows", []) or []:
            for cellv in row:
                if cellv and norm(cellv) not in flat:
                    missing.append((i, "table", str(cellv)[:30]))
    return {"status": "PASS" if not missing else "FAIL", "missing": missing}
