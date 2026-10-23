"""Composition recipes: a composed page written as {recipe, slots, options} instead of raw coordinates.

Each recipe is one proven way to lay out a content shape (sources compared row by row, nested sets, a step rail with
evidence, a value with bar groups, peer lanes, dated rows on a shared axis, entity rows). It measures its texts
(approximately, from character widths at the chosen size) and places `composed` blocks deterministically; the page
then goes through the same checks as any composed page, and the browser measurement stays the final word.

Slots hold fact references ({"fact": id, "emph"?}) or authored labels ({"text": ...}). Nothing here knows a
subject: names like "sets", "lanes" or "rows" describe shapes, not content.
"""
from __future__ import annotations

import math
import re

from .compose import BODY_W, BODY_H, LINE_H, LINE_H_DISPLAY


class RecipeError(ValueError):
    pass


# ---------------------------------------------------------------- measuring
def _wide(ch: str) -> bool:
    return ord(ch) >= 0x2E80


NARROW = {"%": 0.92, "@": 0.95, "W": 0.95, "M": 0.9, "m": 0.9, "w": 0.8}


def text_px(text: str, size: float) -> float:
    """Approximate rendered width of one line: CJK and full-width characters one em, digits ~0.6 em, capitals
    ~0.68 em, other Latin ~0.56 em (a little generous: the browser measurement is the final check)."""
    def em(ch):
        if _wide(ch):
            return 1.0
        if ch in NARROW:
            return NARROW[ch]
        return 0.6 if ch.isdigit() else 0.68 if ch.isupper() else 0.56
    return sum(em(c) for c in text) * size


def line_h(size: int) -> int:
    return round(size * (LINE_H_DISPLAY if size >= 24 else LINE_H))


def lines(text: str, size: int, width: float, one: bool = False) -> int:
    parts = [text.replace("\n", "")] if one else (text.split("\n") or [""])
    return sum(max(1, math.ceil(text_px(p.strip(), size) / max(width - 4, 1))) for p in parts)


def height(text: str, size: int, width: float, one: bool = False) -> int:
    return lines(text, size, width, one) * line_h(size)


def mkey(text: str, size: float, width: float) -> str:
    """Key of a measured text height: the shown text without whitespace, its size and box width (px)."""
    flat = re.sub(r"\s+", "", text)
    return f"{round(size)}|{round(width)}|{flat}"


class Ctx:
    """What a recipe needs: shown text of each ref, and the body height of this page."""

    def __init__(self, page: dict, facts: dict, measured: dict | None = None):
        self.facts, self.body_h = facts, BODY_H[bool(page.get("lead") or page.get("headline"))]
        self.measured = measured or {}          # text heights measured by the browser in a first rendering pass

    def height(self, text: str, size: int, width: float, one: bool = False) -> int:
        """Height of a text block: as measured in the browser when known, else estimated from character widths."""
        got = self.measured.get(mkey(text, size, width))
        return got if got else height(text, size, width, one)

    def text(self, ref) -> str:
        if isinstance(ref, dict) and "fact" in ref:
            f = self.facts.get(ref["fact"]) or {}
            return f.get("display") or f.get("quote") or ""
        if isinstance(ref, dict) and "text" in ref:
            return str(ref["text"])
        raise RecipeError(f"槽位需为 {{\"fact\": 编号}} 或 {{\"text\": 作者文字}}：{ref}")

    def fid(self, ref) -> str | None:
        return ref.get("fact") if isinstance(ref, dict) else None

    def width(self, ref, size: float) -> float:
        """Width of a one-line ref, including the pending-confirmation mark drawn after a pending fact."""
        f = self.facts.get(self.fid(ref) or "") or {}
        return text_px(self.text(ref).replace(chr(10), ""), size) + (0.6 * size if f.get("needs_confirmation") else 0)


def T(x, y, w, h, ref, role, **kw) -> dict:
    refs = ref if isinstance(ref, list) else [ref]
    return {"kind": "text", "x": round(x, 1), "y": round(y, 1), "w": round(w, 1), "h": math.ceil(h), "role": role, "refs": refs, **kw}


def S(x, y, w, h, tone, **kw) -> dict:
    return {"kind": "surface", "x": round(x, 1), "y": round(y, 1), "w": round(w, 1), "h": round(h, 1), "tone": tone, **kw}


def L(x, y, w, h, tone="line", **kw) -> dict:
    return {"kind": "rule", "x": round(x, 1), "y": round(y, 1), "w": round(w, 1), "h": round(h, 1), "tone": tone, **kw}


def M(x, y, d, tone, **kw) -> dict:
    return {"kind": "marker", "x": round(x, 1), "y": round(y, 1), "w": d, "h": d, "tone": tone, "round": True, **kw}


def grouped(blocks: list[dict], group: str) -> list[dict]:
    """Tag blocks as one editable unit (exported as a PowerPoint group: moving a lane moves its nodes)."""
    return [{**b, "group": b.get("group") or group} for b in blocks]


def A(a, b, backed_by, pts, tone="primary2") -> dict:
    return {"kind": "arrow", "from": a, "to": b, "backed_by": backed_by, "points": [[round(x, 1), round(y, 1)] for x, y in pts], "tone": tone}


def _size(role: str, size: int | None = None) -> int:
    from .compose import ROLES
    return size or ROLES[role][0]


def text_block(c: Ctx, x, y, w, ref, role, size=None, one=False, **kw) -> tuple[dict, int]:
    """A text block sized to its content; returns (block, height)."""
    s = _size(role, size)
    refs = ref if isinstance(ref, list) else [ref]
    joined = "　".join(c.text(r) for r in refs)
    h = c.height(joined, s, w, one)
    return T(x, y, w, h, ref, role, **({"size": size} if size else {}), **({"one": True} if one else {}), **kw), h


def foot(c: Ctx, refs, y_limit=None) -> tuple[list[dict], int]:
    """Reference lines (abbreviations, sources) stacked at the bottom of the body; returns (blocks, their top)."""
    out, h_total = [], 0
    sized = []
    for r in refs or []:
        h = c.height("　".join(c.text(x) for x in r) if isinstance(r, list) else c.text(r), 12, BODY_W)
        sized.append((r, h))
        h_total += h + 2
    y = (y_limit or c.body_h) - h_total
    top = y
    for r, h in sized:
        out.append(T(0, y, BODY_W, h, r, "ref"))
        y += h + 2
    return out, top


# ---------------------------------------------------------------- recipes
def clause_rows(c: Ctx, s: dict, o: dict) -> list[dict]:
    """2–3 sources (guidelines, studies, definitions) compared row by row: one column per source, the n-th clause of
    every source on the same row, each source's reference under its own column. Columns are peers."""
    cols = s["columns"]
    if not 2 <= len(cols) <= 3:
        raise RecipeError("clause_rows 需要 2–3 列")
    n = max(len(col["rows"]) for col in cols)
    gut = 48
    cw = (BODY_W - gut * (len(cols) - 1)) / len(cols)
    size = o.get("size", 21)
    head_h = max(c.height(c.text(col["head"]), 20, cw, True) for col in cols)
    row_h = [max((c.height(c.text(col["rows"][i]), size, cw) if i < len(col["rows"]) else 0) for col in cols) for i in range(n)]
    ref_h = max((c.height(c.text(col["ref"]), 12, cw) if col.get("ref") else 0) for col in cols)
    fb, foot_top = foot(c, s.get("foot"))
    avail = foot_top - 16
    top_h = 17 + head_h                            # accent tick + source heading
    region = avail - top_h - (ref_h + 12 if ref_h else 0)
    pad = (region - sum(row_h)) / (2 * n)          # the rows share the height: each row gets pad above and below
    shift = 0
    if pad > 56:                                   # a short comparison: cap the spacing, centre the block
        shift, pad = (region - sum(row_h) - 2 * n * 56) / 2, 56
    if pad < 12:
        raise RecipeError(f"clause_rows：内容需 {round(sum(row_h) + top_h + ref_h)} px，版心只有 {round(avail)} px（请拆页）")
    out = []
    ys = []
    y = shift + top_h
    for i in range(n):
        ys.append(y + pad)
        y += row_h[i] + 2 * pad
    ref_y = y + 12 - (shift if shift else 0) + shift
    for j, col in enumerate(cols):
        x = j * (cw + gut)
        seg = [L(x, shift, 40, 3, "accent"), T(x, shift + 14, cw, head_h, col["head"], "head", one=True, peer="source-head")]
        for i in range(n):
            if i < len(col["rows"]):
                seg.append(T(x, ys[i], cw, row_h[i], col["rows"][i], "key", size=size, peer="clause"))
        if col.get("ref"):
            seg.append(T(x, ref_y, cw, ref_h, col["ref"], "ref", peer="source-ref"))
        out += grouped(seg, f"source{j}")
        if j:
            out.append(L(x - gut / 2, shift, 1, ref_y + ref_h - shift))
    for i in range(1, n):                          # row separators run across all columns: the rows are the comparison
        out.append(L(0, ys[i] - pad, BODY_W, 1))
    return out + fb


def nested_sets(c: Ctx, s: dict, o: dict) -> list[dict]:
    """Sets inside sets (A ⊃ B ⊃ C) drawn as circles that share their lowest point, names and optional values inside;
    beside them one keyed row per set with its definitions. The innermost set is the one strong area."""
    sets = s["sets"]
    if not 2 <= len(sets) <= 4:
        raise RecipeError("nested_sets 需要 2–4 层")
    tones = ["white", "tint", "strong", "strong"][:len(sets)]
    if len(sets) == 4:
        tones = ["white", "tint", "tint", "strong"]
    note_h = c.height(c.text(s["note"]), 12, 420) if s.get("note") else 0
    D = min(400, c.body_h - note_h - 16)
    ds = [round(D * (1 - 0.3 * i) if len(sets) <= 3 else D * (1 - 0.22 * i)) for i in range(len(sets))]
    cx, bottom = D / 2 + 10, D
    out = []
    for d, tone in zip(ds, tones):
        out.append(S(cx - d / 2, bottom - d, d, d, tone, round=True))
    for i, (st, d, tone) in enumerate(zip(sets, ds, tones)):
        dark = tone == "strong"
        top = bottom - d + (26 if i == 0 else 18)
        inner = ds[i + 1] if i + 1 < len(ds) else 0
        room = d - inner                        # the band of this ring above the next one
        w = min(200, d * 0.62)
        out.append(T(cx - w / 2, top, w, line_h(18), st["name"], "head", size=18, align="center", one=True,
                     **({"tone": "on-dark"} if dark else {})))
        if st.get("value") and (room >= 110 or i == len(sets) - 1):
            vw = d * 0.78 if i == len(sets) - 1 else w
            vs = next((z for z in (40, 34, 32, 28, 26, 24) if c.width(st["value"], z) <= vw - 8), 24)
            out.append(T(cx - vw / 2, top + 30, vw, line_h(vs), st["value"], "value", size=vs, align="center",
                         **({"tone": "on-dark-accent"} if dark else {})))
    if s.get("note"):
        out.append(T(0, D + 12, 420, note_h, s["note"], "ref"))
    X = D + 70
    W = BODY_W - X
    y = 0
    heights = []
    for st in sets:
        h = line_h(17) + 6 + sum(c.height(c.text(it["ref"] if "ref" in it else it), 15 if it.get("role", "sub") == "sub" else 13, W - 26) + 8
                                  for it in st.get("items") or [])
        heights.append(h)
    gap = max(20, (c.body_h - sum(heights)) / max(len(sets), 1) - 4)
    for i, (st, tone) in enumerate(zip(sets, tones)):
        out += [M(X, y + 6, 14, tone), T(X + 26, y, 400, line_h(17), st["name"], "head", size=17, one=True)]
        yy = y + line_h(17) + 6
        for it in st.get("items") or []:
            ref, role = (it["ref"], it.get("role", "sub")) if isinstance(it, dict) and "ref" in it else (it, "sub")
            b, h = text_block(c, X + 26, yy, W - 26, ref, role)
            out.append(b)
            yy += h + 8
        y = yy + gap / 2
        if i < len(sets) - 1:
            out.append(L(X, y - 8, W, 1))
            y += gap / 2
    return out


def evidence_column(c: Ctx, x: float, w: float, items: list, y: float = 0) -> list[dict]:
    """A column of evidence items: {value, label} pairs, bar groups {axis?, rows: [[label, value], ...], strong?},
    notes {head?, items: [refs]}; items are separated by rules. The gaps shrink (to 6 px) when the column is long."""
    for gap in (16, 12, 8, 6):
        out, end = _evidence(c, x, w, items, y, gap)
        if end <= c.body_h - 4:
            return out
    raise RecipeError(f"证据栏需 {round(end)} px，版心只有 {c.body_h} px（请减少证据项或拆页）")


def _evidence(c: Ctx, x: float, w: float, items: list, y: float, gap: int) -> tuple[list[dict], float]:
    out = []
    for k, it in enumerate(items):
        if k:
            out.append(L(x, y, w, 1))
            y += gap
        if "value" in it:
            vw = min(w * 0.4, c.width(it["value"], 34) + 16)
            lb, lh = text_block(c, x + vw + 16, y + 8, w - vw - 16, it["label"], "sub")
            out += [T(x, y, vw, line_h(34), it["value"], "value", size=34, tone="primary2"), lb]
            y += max(line_h(34), lh + 8) + gap
        elif "rows" in it:
            if it.get("axis"):
                out.append(T(x, y, w, line_h(13), it["axis"], "label"))
                y += line_h(13) + 6
            out += bar_rows(c, x, y, w, it["rows"], it.get("strong", len(it["rows"]) - 1), it.get("scale", f"s{k}"))
            y += len(it["rows"]) * 36 + gap / 2
        else:
            if it.get("head"):
                out.append(T(x, y, w, line_h(13), it["head"], "label"))
                y += line_h(13) + 6
            for r in it.get("items") or []:
                b, h = text_block(c, x, y, w, r, "ref")
                out.append(b)
                y += h + 6
    return out, y


def bar_rows(c: Ctx, x, y, w, rows, strong, scale, row_h=36, label_w=None) -> list[dict]:
    """Label | bar (length ∝ value, from zero, on one scale) | value; the `strong` row is the one dark bar."""
    label_w = label_w or max(text_px(c.text(l), 15) for l, _ in rows) + 8
    vals = []
    for _, v in rows:
        nums = re.findall(r"-?\d[\d,]*\.?\d*", c.text(v))
        if len(nums) != 1:
            raise RecipeError(f"条形数值事实须恰好含一个数：{c.text(v)}")
        vals.append(abs(float(nums[0].replace(",", ""))))
    val_w = max(text_px(c.text(v), 16) for _, v in rows) + 24
    bw = w - label_w - 24 - val_w
    out = []
    for i, ((l, v), n) in enumerate(zip(rows, vals)):
        yy = y + i * row_h
        on = i == strong
        ww = n / (max(vals) or 1) * bw
        out += [T(x, yy, label_w, 30, l, "sub", align="right"),
                {"kind": "bar", "x": round(x + label_w + 14, 1), "y": yy + 5, "max_w": round(bw, 1), "h": 20, "value_of": c.fid(v),
                 "scale": scale, "tone": "strong" if on else "quiet"},
                T(x + label_w + 24 + ww, yy, val_w, 30, v, "body", weight="bold", tone="primary" if on else "muted")]
    return out


def step_rail(c: Ctx, s: dict, o: dict) -> list[dict]:
    """Steps read top to bottom on a rail, the end point the one strong area; evidence in a column beside."""
    steps, end = s["steps"], s["end"]
    backs = s.get("arrows") or []
    rail_w = o.get("rail_w") or min(520, max(text_px(c.text(r).replace("\n", ""), 17) for r in steps) + 60)
    n = len(steps)
    end_h = 48
    gap = min(62, (c.body_h - end_h - 16) / n)
    out = []
    ys = [8 + i * gap for i in range(n)]
    for i, (r, y) in enumerate(zip(steps, ys)):
        out += [M(0, y + 8, 12, "white"), T(30, y, rail_w - 30, line_h(17), r, "body", one=True, id=f"st{i}", peer="step")]
    end_y = 8 + n * gap + 4
    end_w = text_px(c.text(end).replace("\n", ""), 20) + 48
    out += [S(0, end_y, end_w, end_h, "strong", radius=8), T(20, end_y + 9, end_w - 30, 30, end, "head", size=20, tone="on-dark", id="st-end")]
    for i, fid in enumerate(backs[:n]):
        a = ys[i] + 22
        z = (ys[i + 1] + 6) if i + 1 < n else end_y - 2
        out.append(A(f"st{i}", f"st{i + 1}" if i + 1 < n else "st-end", fid, [[6, a], [6, z]]))
    X = rail_w + 60
    out.append(L(X - 30, 8, 1, c.body_h - 24))
    out += evidence_column(c, X, BODY_W - X, s.get("evidence") or [])
    return out


def value_bars(c: Ctx, s: dict, o: dict) -> list[dict]:
    """One headline value with its label and supporting lines on the left; one or more bar groups on the right, each
    with its own claim as heading. In every group only the `strong` bar is dark."""
    lw = o.get("left_w", 330)
    vb = T(0, 0, lw, line_h(56), s["value"], "value", size=56, tone="primary")
    lb, lh = text_block(c, 0, line_h(56) + 6, lw, s["label"], "head", size=17)
    out, y = [vb, lb], line_h(56) + 6 + lh + 10
    for k, r in enumerate(s.get("support") or []):
        if k:
            out.append(L(0, y + 8, 48, 3, "accent"))
            y += 26
        b, h = text_block(c, 0, y, lw, r, "body", one=True)
        out.append(b)
        y += h + 12
    X = lw + 90
    out.append(L(lw + 46, 6, 1, c.body_h - 24))
    groups = s["charts"]
    per = (c.body_h - 10) / len(groups)
    for g, ch in enumerate(groups):
        y = g * per
        start = len(out)
        out.append(T(X, y, BODY_W - X, line_h(18), ch["head"], "head", size=18, one=True))
        y += line_h(18) + 4
        if ch.get("sub"):
            out.append(T(X, y, BODY_W - X, line_h(13), ch["sub"], "note"))
            y += line_h(13) + 12
        out += bar_rows(c, X, y, BODY_W - X, ch["rows"], ch.get("strong", len(ch["rows"]) - 1), f"g{g}", row_h=44)
        out[start:] = grouped(out[start:], f"chart{g}")
    return out


def lanes(c: Ctx, s: dict, o: dict) -> list[dict]:
    """Parallel processes as peer lanes (same surface), each a heading and nodes joined by arrows (backed by the
    sentence the nodes were cut from, or by source arrows). An optional strip hangs from one lane: what belongs to it
    is shown by position, not by making that lane darker."""
    ls = s["lanes"]
    att = s.get("attach")
    fb, foot_top = foot(c, s.get("foot"))
    NX, W = 200, BODY_W
    lane_hs = []
    for ln in ls:
        n = len(ln["nodes"])
        nw = (W - NX - 24 - 44 * (n - 1)) / n
        lane_hs.append(max(96, max(c.height(c.text(r), 16, nw) for r in ln["nodes"]) + 32))
    att_h = 0
    if att:
        att_h = 40 + line_h(15) + 12 + line_h(26) + 4 + line_h(15) + 10
    gap = max(16, (foot_top - 12 - sum(lane_hs) - att_h) / (len(ls) + (1 if att else 0)))
    out, y = [], 0
    for li, (ln, h) in enumerate(zip(ls, lane_hs)):
        n = len(ln["nodes"])
        nw = (W - NX - 24 - 44 * (n - 1)) / n
        seg = [S(0, y, W, h, "tint", peer="lane"), T(24, y + (h - 32) / 2, 160, 32, ln["head"], "head", size=21, peer="lane-head")]
        for i, r in enumerate(ln["nodes"]):
            x = NX + i * (nw + 44)
            seg.append(T(x, y + 12, nw, h - 24, r, "body", size=16, valign="middle", id=f"l{li}n{i}", peer="lane-node"))
            if i and ln.get("backed_by"):
                seg.append(A(f"l{li}n{i - 1}", f"l{li}n{i}", ln["backed_by"], [[x - 36, y + h / 2], [x - 8, y + h / 2]]))
        out += grouped(seg, f"lane{li}")
        y += h
        if att and att.get("to", 0) == li:
            items = att["items"]
            start = len(out)
            out += [L(92, y, 2, 30, "accent"), L(92, y + 28, W - 92, 2, "accent")]
            yy = y + 38
            if att.get("head"):
                out.append(T(112, yy, W - 112, line_h(15), att["head"], "head", size=15))
                yy += line_h(15) + 12
            cw = (W - 112) / len(items)
            for i, it in enumerate(items):
                x = 112 + i * cw
                out.append(T(x, yy, cw - 12, line_h(26), it["big"], "value", size=26, peer="attach-big"))
                if it.get("small"):
                    out.append(T(x, yy + line_h(26) + 4, cw - 12, line_h(15), it["small"], "sub", one=True, peer="attach-small"))
            y = yy + line_h(26) + 4 + line_h(15)
            out[start:] = grouped(out[start:], "attached")
        y += gap
    return out + fb


def date_axis(c: Ctx, s: dict, o: dict) -> list[dict]:
    """One row per entity: attribute cells, then dated markers on one shared axis (x ∝ year). Each date kind is
    named once in a legend (the date facts may drop that label: it is stated here). The `primary` kind is labelled
    beside its marker; the others above and below."""
    rows, kinds = s["rows"], s["legend"]
    heads = s.get("headers") or []
    fb, foot_top = foot(c, s.get("foot"))
    col_w = o.get("col_w") or [160, 120, 130][:len(rows[0]["cells"])]
    AX0 = sum(col_w) + 10 * len(col_w) + 30
    years = [int(m) for r in rows for ref in r["dates"].values() for m in re.findall(r"(?:19|20)\d\d", c.text(ref))[:1]]
    if not years:
        raise RecipeError("date_axis 的日期事实中没有年份")
    y0, y1 = min(years), max(years)
    AXW = BODY_W - AX0 - 80
    xo = lambda yr: AX0 + (yr - y0) / max(1, y1 - y0) * AXW
    out, x = [], 0
    for h, w in zip(heads, col_w):
        out.append(T(x, 0, w, line_h(13), h, "label"))
        x += w + 10
    if s.get("axis_head"):
        out.append(T(AX0, 0, BODY_W - AX0, line_h(13), s["axis_head"], "label"))
    lx = AX0
    for k in kinds:
        out += [M(lx, 32, 12, k["tone"]), T(lx + 18, 26, 70, line_h(15), k["label"], "sub")]
        lx += 96
    top = 64
    rh = min(60, (foot_top - 12 - top) / len(rows))
    for i, r in enumerate(rows):
        y = top + i * rh
        x = 0
        start = len(out)
        out.append(L(0, y + rh - 1, BODY_W, 1))
        for j, (cell, w) in enumerate(zip(r["cells"], col_w)):
            out.append(T(x, y + (rh - 30) / 2, w, 30, cell, "head" if j == 0 else "sub", **({"size": 17} if j == 0 else {}), peer=f"col{j}"))
            x += w + 10
        mid = y + rh / 2
        out.append(L(AX0, mid, AXW, 1))
        others = [k for k in kinds if not k.get("primary")]
        for n, k in enumerate(others):
            ref = r["dates"].get(k["key"])
            if not ref:
                continue
            yr = int(re.findall(r"(?:19|20)\d\d", c.text(ref))[0])
            dy = -8 if n % 2 == 0 else 8
            ly = mid - 30 if n % 2 == 0 else mid + 12
            out += [M(xo(yr) - 6, mid + dy - 6, 12, k["tone"]), T(xo(yr) - 24, ly, 48, 18, ref, "ref", align="center")]
        for k in kinds:
            if k.get("primary") and r["dates"].get(k["key"]):
                ref = r["dates"][k["key"]]
                yr = int(re.findall(r"(?:19|20)\d\d", c.text(ref))[0])
                out += [M(xo(yr) - 8, mid - 8, 16, k["tone"]), T(xo(yr) + 14, mid - 14, 64, 28, ref, "body", weight="bold", tone="accent")]
        out[start:] = grouped(out[start:], f"row{i}")
    return out + fb


INDENT = 24                  # px per nesting level of a sub-row's first cell


def entity_rows(c: Ctx, s: dict, o: dict) -> list[dict]:
    """One row per entity, columns of attributes; a cell is one ref or a list of refs (one per line). Column widths
    follow the longest content of each column; the row height follows its tallest cell."""
    heads, rows = s["headers"], s["rows"]
    levels = s.get("levels") or [0] * len(rows)          # a sub-row is indented under the row naming its group
    roles = o.get("roles") or ["head"] + ["sub"] * (len(heads) - 1)
    sizes = o.get("sizes") or [17 if r == "head" else (22 if r == "value" else 15) for r in roles]
    fb, foot_top = foot(c, s.get("foot"))
    cells = lambda cell: cell if isinstance(cell, list) else [cell]
    natural = [max(max((text_px(c.text(r).replace("\n", "") if (o.get("one") or [False] * 9)[j] else max(c.text(r).split("\n"), key=len), sizes[j])
                        for r in cells(row[j])), default=0) + (INDENT * lv if j == 0 else 0) for row, lv in zip(rows, levels)) + 16
               for j in range(len(heads))]
    natural = [max(n, text_px(c.text(h), 13) + 16) for n, h in zip(natural, heads)]
    spare = BODY_W - sum(natural) - 16 * (len(heads) - 1)
    available = BODY_W - 16 * (len(heads) - 1)
    requested_widths = o.get("widths")
    if requested_widths and len(requested_widths) == len(heads) and sum(requested_widths) > 0:
        widths = [available * float(n) / sum(requested_widths) for n in requested_widths]
    else:
        widths = [n + spare * n / sum(natural) for n in natural] if spare > 0 else [n * available / sum(natural) for n in natural]
    xs = [sum(widths[:j]) + 16 * j for j in range(len(heads))]
    out = [T(x, 0, w, line_h(13), h, "label", one=True) for x, w, h in zip(xs, widths, heads)]
    one = o.get("one") or [False] * len(heads)
    tones = o.get("tones") or [None] * len(heads)
    y = line_h(13) + 10
    heights = []
    for row, lv in zip(rows, levels):
        hh = max(sum(c.height(c.text(r), sizes[j], widths[j] - (INDENT * lv if j == 0 else 0), one[j]) for r in cells(row[j]))
                 for j in range(len(heads)))
        heights.append(hh + 12)
    room = foot_top - 12 - y
    if sum(heights) > room:
        raise RecipeError(f"entity_rows：{len(rows)} 行需 {sum(heights)} px，版心只剩 {round(room)} px（请拆页）")
    extra = min(16, (room - sum(heights)) / len(rows))
    for k, (row, hh, lv) in enumerate(zip(rows, heights, levels)):
        hh += extra
        start = len(out)
        if not (k and lv > levels[k - 1]):              # no rule between a group row and its first sub-row
            out.append(L(0, y, BODY_W, 1))
        for j, (x, w) in enumerate(zip(xs, widths)):
            if j == 0 and lv:
                x, w = x + INDENT * lv, w - INDENT * lv
            yy = y + 6 + extra / 2
            for r in cells(row[j]):
                h = c.height(c.text(r), sizes[j], w, one[j])
                out.append(T(x, yy, w, h, r, roles[j], size=sizes[j], peer=f"col{j}",
                             **({"one": True} if one[j] else {}), **({"tone": tones[j]} if tones[j] else {})))
                yy += h
        out[start:] = grouped(out[start:], f"row{k}")
        y += hh
    out.append(L(0, y, BODY_W, 1))
    return out + fb


def criteria(c: Ctx, s: dict, o: dict) -> list[dict]:
    """A rule and the items it names: criteria (any of / all of), checks to perform, dimensions to weigh. The rule
    (optional) leads with an accent rule; the items are peer cells (same tint) in a grid of 2–4 columns that fills the
    body, each a name, an optional value and its details; optional notes sit under the grid. Type size follows the
    amount of text: short items are set larger rather than floating in empty cells."""
    items = s["items"]
    if not 2 <= len(items) <= 9:
        raise RecipeError("criteria 需要 2–9 项")
    fb, foot_top = foot(c, s.get("foot"))
    y, out = 0, []
    if s.get("rule"):
        rb, rh = text_block(c, 20, 0, BODY_W - 20, s["rule"], "key", size=o.get("rule_size", 20))
        out += [L(0, 2, 4, rh - 4, "accent"), {**rb, "tone": "primary"}]
        y = rh + 22
    if s.get("items_head"):                        # what the items are ("评估并解决以下问题"), above the grid
        out.append(T(0, y, BODY_W, line_h(15), s["items_head"], "label", size=15))
        y += line_h(15) + 12
    ncol = o.get("columns") or (len(items) if len(items) <= 3 else 2 if len(items) == 4 else 3)
    nrow = math.ceil(len(items) / ncol)
    gut, pad = 20, 20
    cw = (BODY_W - gut * (ncol - 1)) / ncol
    inner = cw - 2 * pad
    notes = s.get("notes")
    notes_h = 0
    if notes:
        notes_h = (line_h(13) + 6 if notes.get("head") else 0) + sum(c.height(c.text(r), 13, BODY_W) + 4 for r in notes["items"]) + 18
    room = foot_top - 12 - y - notes_h

    def need(sizes, pad, inner):
        ns, vs, ds = sizes
        hs = []
        for it in items:
            h = 2 * pad
            if it.get("name"):
                h += c.height(c.text(it["name"]), ns, inner, True) + 8
            if it.get("value"):
                h += line_h(vs) + 6
            h += sum(c.height(c.text(r), ds, inner) + 6 for r in it.get("detail") or [])
            hs.append(h)
        return [max(hs[r * ncol:(r + 1) * ncol]) for r in range(nrow)]
    # the largest type tier whose rows still fit comfortably (≤ 80% of the room); the smallest must fit at all
    # a value is one line: cap its size so the longest value fits the cell (28 px is the floor of the scale used here)
    longest = max((it["value"] for it in items if it.get("value")), key=lambda r: c.width(r, 1), default=None)
    fit = next((z for z in (48, 40, 34, 32, 28) if longest is None or c.width(longest, z) <= inner), 28)
    tiers = [(24, min(48, fit), 20), (22, min(40, fit), 18), (20, min(34, fit), 17), (18, min(28, fit), 15),
             (17, min(26, fit), 14)]
    rows, sizes = None, tiers[-1]
    for pad in (20, 14, 10):                       # when the page is tight the card's own padding gives way first
        inner = cw - 2 * pad
        sizes = next((t for t in tiers if sum(need(t, pad, inner)) + gut * (nrow - 1) <= room * 0.8), tiers[-1])
        rows = need(sizes, pad, inner)
        if sum(rows) + gut * (nrow - 1) <= room:
            break
    if sum(rows) + gut * (nrow - 1) > room:
        raise RecipeError(f"criteria：{len(items)} 项需 {round(sum(rows))} px，版心只剩 {round(room)} px（请拆页）")
    spare = (room - sum(rows) - gut * (nrow - 1)) / nrow
    row_h = [h + spare for h in rows]              # cells share the whole height: the grid holds the page
    ns, vs, ds = sizes
    for k, it in enumerate(items):
        r, col = divmod(k, ncol)
        x, top = col * (cw + gut), y + sum(row_h[:r]) + gut * r
        seg = [S(x, top, cw, row_h[r], "tint", peer="item-cell"), L(x + pad, top + pad - 6, 32, 3, "accent")]
        yy = top + pad + 6
        if it.get("name"):
            nb, nh = text_block(c, x + pad, yy, inner, it["name"], "head", size=ns, one=True, peer="item-name")
            seg.append(nb)
            yy += nh + 8
        if it.get("value"):
            seg.append(T(x + pad, yy, inner, line_h(vs), it["value"], "value", size=vs, peer="item-value"))
            yy += line_h(vs) + 6
        for d in it.get("detail") or []:
            db, dh = text_block(c, x + pad, yy, inner, d, "sub", size=ds, peer="item-detail")
            seg.append(db)
            yy += dh + 6
        out += grouped(seg, f"item{k}")
    if notes:
        yy = y + sum(row_h) + gut * (nrow - 1) + 18
        seg = []
        if notes.get("head"):
            seg.append(T(0, yy, BODY_W, line_h(13), notes["head"], "label"))
            yy += line_h(13) + 6
        for r in notes["items"]:
            nb, nh = text_block(c, 0, yy, BODY_W, r, "note")
            seg.append(nb)
            yy += nh + 4
        out += grouped(seg, "notes")
    return out + fb


def key_value(c: Ctx, s: dict, o: dict) -> list[dict]:
    """One key value (a frequency, a threshold, a share) on the page's one strong panel with its label; the points
    that qualify it (conditions, caveats, how to measure) as a ruled list beside it, sharing the body height."""
    fb, foot_top = foot(c, s.get("foot"))
    room = foot_top - 12
    lw = o.get("left_w", 420)
    pad = 36
    vs = next((z for z in (64, 56, 48, 40) if c.width(s["value"], z) <= lw - 2 * pad), 40)
    lb_h = c.height(c.text(s["label"]), 20, lw - 2 * pad)
    ph = min(room, max(260, line_h(vs) + 16 + lb_h + 2 * pad))
    py = (room - ph) / 2
    out = grouped([S(0, py, lw, ph, "strong", radius=12),
                   T(pad, py + pad, lw - 2 * pad, line_h(vs), s["value"], "value", size=vs, tone="on-dark-accent"),
                   T(pad, py + pad + line_h(vs) + 16, lw - 2 * pad, lb_h, s["label"], "head", size=20, tone="on-dark")], "key")
    X = lw + 56
    W = BODY_W - X
    pts = s.get("points") or []
    size = next((z for z in (20, 18, 17) if sum(c.height(c.text(r), z, W) for r in pts) + 40 * len(pts) <= room), 17)
    hs = [c.height(c.text(r), size, W) for r in pts]
    gap = max(24, min(64, (room - sum(hs)) / max(len(pts), 1)))
    y = max(0, (room - sum(hs) - gap * (len(pts) - 1)) / 2)
    for k, (r, h) in enumerate(zip(pts, hs)):
        if k:
            out.append(L(X, y - gap / 2, W, 1))
        out += [M(X - 22, y + 10, 10, "accent"), T(X, y, W, h, r, "body", size=size, peer="point")]
        y += h + gap
    return out + fb


RECIPES = {
    "criteria": (criteria, "一条规则及其列出的各项：满足任一/均需满足的条件、需执行的检查、需权衡的维度；各项并列（名称、可选数值、说明），可附参考说明",
                 {"rule": {"fact": "r"}, "items": [{"name": {"fact": "n1"}, "value": {"fact": "v1"}, "detail": [{"fact": "d1"}]},
                                                   {"name": {"fact": "n2"}, "detail": [{"fact": "d2"}]}],
                  "notes": {"head": {"text": "说明"}, "items": [{"fact": "x"}]}}),
    "key_value": (key_value, "一个关键数值（频率、阈值、比例）及其说明在左；限定它的条件、注意事项在右，逐条排列",
                  {"value": {"fact": "v"}, "label": {"fact": "l"}, "points": [{"fact": "p1"}, {"fact": "p2"}]}),
    "clause_rows": (clause_rows, "2–3 份来源（指南、研究、定义）逐条对照：每份一栏，第 n 条对齐在同一行，出处放在各自栏下；各栏同等处理",
                    {"columns": [{"head": {"fact": "h1"}, "rows": [{"fact": "a1"}, {"fact": "b1"}], "ref": {"fact": "r1"}},
                                 {"head": {"fact": "h2"}, "rows": [{"fact": "a2"}, {"fact": "b2"}], "ref": {"fact": "r2"}}],
                     "foot": [{"fact": "gl"}]}),
    "nested_sets": (nested_sets, "包含关系 A ⊃ B ⊃ C：以同底的圆表示，圆内只放名称与数值；旁边逐层列出定义，最内层为唯一深色",
                    {"sets": [{"name": {"fact": "n1"}, "items": [{"fact": "d1"}]}, {"name": {"fact": "n2"}, "value": {"fact": "v2"}, "items": [{"fact": "d2"}]},
                              {"name": {"fact": "n3"}, "value": {"fact": "v3"}, "items": [{"ref": {"fact": "d3"}, "role": "note"}]}],
                     "note": {"fact": "vn"}}),
    "step_rail": (step_rail, "自上而下的步骤（终点为唯一深色），箭头由原件箭头支持；旁边一栏放证据：数值+说明、条形组、研究说明",
                  {"steps": [{"fact": "s1"}, {"fact": "s2"}], "end": {"fact": "s3"}, "arrows": ["a1", "a2"],
                   "evidence": [{"value": {"fact": "v1"}, "label": {"fact": "l1"}},
                                {"axis": {"fact": "ax"}, "rows": [[{"fact": "c1"}, {"fact": "n1"}], [{"fact": "c2"}, {"fact": "n2"}]]},
                                {"head": {"text": "研究说明"}, "items": [{"fact": "d1"}]}]}),
    "value_bars": (value_bars, "一个关键数值及其说明在左；右侧一至三组条形，每组以其原文结论为题，只有被主张的一组为深色",
                   {"value": {"fact": "v"}, "label": {"fact": "l"}, "support": [{"fact": "s1"}],
                    "charts": [{"head": {"fact": "h1"}, "sub": [{"fact": "ax1"}, {"fact": "p1"}],
                                "rows": [[{"fact": "c1"}, {"fact": "n1"}], [{"fact": "c2"}, {"fact": "n2"}]]}]}),
    "lanes": (lanes, "并列的过程/通路：每条一道（同一底色），标题+环节+箭头；可把一条附属信息挂在所属的那一道下方（用位置表达归属）",
              {"lanes": [{"head": {"fact": "h1"}, "nodes": [{"fact": "a1"}, {"fact": "a2"}], "backed_by": "s1"},
                         {"head": {"fact": "h2"}, "nodes": [{"fact": "b1"}, {"fact": "b2"}], "backed_by": "s2"}],
               "attach": {"to": 0, "head": {"fact": "t"}, "items": [{"big": {"fact": "t1"}, "small": {"fact": "d1"}}]},
               "foot": [{"fact": "gl"}]}),
    "date_axis": (date_axis, "多个对象的日期：每个对象一行（属性列 + 共享时间轴上的标记），日期种类在图例中只写一次；primary 种类标在标记旁",
                  {"headers": [{"text": "对象"}, {"text": "属性"}], "axis_head": {"fact": "ax"},
                   "legend": [{"key": "a", "label": {"fact": "la"}, "tone": "strong"}, {"key": "b", "label": {"fact": "lb"}, "tone": "accent", "primary": True}],
                   "rows": [{"cells": [{"fact": "o1"}, {"fact": "p1"}], "dates": {"a": {"fact": "d1a"}, "b": {"fact": "d1b"}}}],
                   "foot": [{"fact": "gl"}]}),
    "entity_rows": (entity_rows, "每个对象一行、属性分列；一格可放多条（每条一行）；栏宽按内容分配，行高按最高的一格；"
                                 "有上下级的行用 levels 给出每行层级（0 为顶层，子项缩进在其上一级行下），上一级单独成行、其余格可为空列表",
                    {"headers": [{"text": "对象"}, {"text": "属性"}], "rows": [[{"fact": "o1"}, [{"fact": "p1"}, {"fact": "p2"}]]],
                     "foot": [{"fact": "gl"}]}),
}


def expand(page: dict, facts: dict, measured: dict | None = None) -> dict:
    """A recipe page with its blocks placed (the recipe name is kept; slots and options are consumed)."""
    if page.get("layout") != "composed" or ("recipe" not in page and "diagram" not in page):
        return page
    blocks: list[dict] = []
    if "recipe" in page:
        if page["recipe"] not in RECIPES:
            raise RecipeError(f"未知构图方案：{page['recipe']}（可用：{'、'.join(RECIPES)}）")
        fn = RECIPES[page["recipe"]][0]
        c = Ctx(page, facts, (measured or {}).get(page.get("id")))
        blocks = fn(c, page.get("slots") or {}, page.get("options") or {})
    if page.get("diagram"):
        from . import figures
        texts = {fid: (f.get("display") or f.get("quote") or "") for fid, f in facts.items()}
        blocks = blocks + figures.build(page["diagram"], texts) + list(page.get("blocks") or [])
    else:
        blocks = blocks + list(page.get("blocks") or [])
    return {**{k: v for k, v in page.items() if k not in ("slots", "options", "diagram")}, "blocks": blocks}


def expand_deck(deck: dict, facts: dict, measured: dict | None = None) -> tuple[dict, dict[str, str]]:
    """The deck with every recipe page expanded, and the errors of pages whose recipe could not be applied."""
    pages, errors = [], {}
    for p in deck.get("pages") or []:
        try:
            pages.append(expand(p, facts, measured))
        except (RecipeError, KeyError, IndexError, TypeError) as e:
            errors[p.get("id")] = f"构图方案 {p.get('recipe')} 无法生成：{e.__class__.__name__ if not isinstance(e, RecipeError) else ''}{e}"
            pages.append({**{k: v for k, v in p.items() if k not in ("slots", "options")}, "blocks": p.get("blocks") or []})
    return {**deck, "pages": pages}, errors
