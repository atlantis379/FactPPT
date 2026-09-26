# -*- coding: utf-8 -*-
"""
Column-aware PDF extraction.

Naive line-order extraction interleaves the columns of a two-column journal /
report, producing text that reads mid-sentence across the page. This module uses
the actual text coordinates to:

  1. collect positioned fragments (x, y, text, size) via pypdf's visitor API
  2. find the vertical gutter (an x band with no text) -> column split
  3. rebuild lines inside each column, then emit in READING ORDER:
        full-width blocks (title/abstract) first, then the left column, then right

It also reports a quality metric so the two modes can be compared objectively
instead of by eye.
"""
import re

_WS = re.compile(r"[ \t\u3000]+")
_SENT_END = "。！？；：.!?;:"
_PAGEMARK = None


def _clean(s):
    return _WS.sub(" ", str(s or "")).strip()


def extract_positioned(page):
    """[(x, y, text, size)] in PAGE space for one page.

    pypdf's visitor reports the raw text matrix (tm); the page-space position is
    the text origin transformed by the current transformation matrix (cm):
        x = cm[0]*tm[4] + cm[2]*tm[5] + cm[4]
        y = cm[1]*tm[4] + cm[3]*tm[5] + cm[5]
    Using tm alone yields meaningless coordinates (text-space units).
    """
    parts = []

    def visitor(text, cm, tm, font_dict, font_size):
        t = text or ""
        if not t.strip():
            return
        try:
            x = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
            y = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
            size = float(font_size or 0) * abs(cm[3] or cm[0] or 1.0)
        except Exception:  # noqa: BLE001
            return
        parts.append((float(x), float(y), t, float(size)))
    try:
        page.extract_text(visitor_text=visitor)
    except Exception:  # noqa: BLE001
        pass
    return parts


def page_width(page):
    try:
        box = page.mediabox
        return float(box.width)
    except Exception:  # noqa: BLE001
        return 595.0


def detect_gutter(parts, width, lo=0.32, hi=0.68, band=0.035):
    """Find an empty vertical band near the middle -> the column gutter.

    Returns the split x, or None when the page looks single-column.
    """
    if not parts or width <= 0:
        return None
    half = band * width
    best = None
    steps = 40
    for i in range(steps + 1):
        s = width * (lo + (hi - lo) * i / steps)
        n = sum(1 for x, _y, t, _sz in parts if abs(x - s) <= half and len(t.strip()) > 1)
        if best is None or n < best[1]:
            best = (s, n)
    if best is None:
        return None
    split, hits = best
    left = sum(1 for x, _y, _t, _s in parts if x < split - half)
    right = sum(1 for x, _y, _t, _s in parts if x > split + half)
    total = max(1, len(parts))
    # a real gutter: almost nothing in the band, and both sides carry text
    if hits <= max(1, total * 0.012) and left >= total * 0.25 and right >= total * 0.25:
        return split
    return None


def _is_full_width(parts_sorted, y, split, width):
    """A fragment that starts left of the gutter and ends right of it."""
    row = [p for p in parts_sorted if abs(p[1] - y) < 3.0]
    if not row:
        return False
    xs = [p[0] for p in row]
    return min(xs) < split - width * 0.03 and max(xs) > split + width * 0.03


def build_lines(parts, split=None, y_tol=2.5):
    """Group fragments into text lines, per column when split is given."""
    lines = []

    def emit(group, col):
        group = sorted(group, key=lambda p: (round(p[1] / y_tol), p[0]))
        cur_y, buf, xs = None, [], []
        for x, y, t, _sz in group:
            if cur_y is None or abs(y - cur_y) <= y_tol:
                buf.append(t)
                xs.append(x)
                cur_y = y if cur_y is None else cur_y
            else:
                lines.append({"col": col, "y": cur_y, "x": min(xs), "text": _clean("".join(buf))})
                buf, xs, cur_y = [t], [x], y
        if buf:
            lines.append({"col": col, "y": cur_y, "x": min(xs), "text": _clean("".join(buf))})

    if split is None:
        emit(sorted(parts, key=lambda p: (-p[1], p[0])), 0)
    else:
        full = [p for p in parts if p[0] <= split - 6 and False]  # placeholder
        left = [p for p in parts if p[0] < split]
        right = [p for p in parts if p[0] >= split]
        # full-width rows (title / abstract) are detected per line and emitted first
        fw_y = []
        for p in sorted(parts, key=lambda q: -q[1]):
            xs_left = [q[0] for q in parts if abs(q[1] - p[1]) < 3.0]
            if xs_left and min(xs_left) < split - 10 and max(xs_left) > split + 10:
                fw_y.append(p[1])
        fw = [p for p in parts if any(abs(p[1] - y) < 3.0 for y in fw_y)]
        left = [p for p in left if p not in fw]
        right = [p for p in right if p not in fw]
        emit(fw, -1)
        emit(left, 0)
        emit(right, 1)
        lines.sort(key=lambda l: (l["col"], -l["y"]))
    return [l for l in lines if l["text"]]


def is_readable_line(text):
    """Heuristic: does this line look like a whole thought rather than a fragment?"""
    t = _clean(text)
    if len(t) < 8:
        return False
    if t[-1] in _SENT_END:
        return True
    # a long CJK line without terminator is often a wrapped line — accept it
    cjk = sum(1 for ch in t if "\u4e00" <= ch <= "\u9fff")
    if cjk >= 18 and len(t) >= 24:
        return True
    return False


_MERGE_RE = re.compile(r"[。！？；][^。！？；]{0,40}[。！？；]|(?<=[。！？；])[\u4e00-\u9fff]{6,}")


def merge_defect(text):
    """A line carrying a sentence ender and then MORE prose is a column merge:
    correct column-aware output ends a thought where the column ends."""
    return len(_MERGE_RE.findall(_clean(text))) > 0


def quality(lines):
    """Line count, readability, and the column-merge defect rate."""
    texts = [l["text"] if isinstance(l, dict) else str(l) for l in lines]
    if not texts:
        return {"lines": 0, "readable": 0, "readable_ratio": 0.0,
                "merge_defects": 0, "merge_ratio": 0.0}
    ok = sum(1 for t in texts if is_readable_line(t))
    bad = sum(1 for t in texts if merge_defect(t))
    return {"lines": len(texts), "readable": ok,
            "readable_ratio": round(ok / len(texts), 4),
            "merge_defects": bad, "merge_ratio": round(bad / len(texts), 4)}


# ---------------------------------------------------------------- layout mode
# pypdf's layout mode preserves the visual line, so a two-column page yields one
# line containing "left column text <padding> right column text". Splitting on
# that padding and ACCUMULATING each column separately recovers the column
# reading order that plain line-order extraction destroys.
_LINE_RE = re.compile(r"^(\s*)(.*?)(\s{5,})(\S.*)$")


def split_layout_line(line):
    """-> (lead, left, right) ; right is None for a single-fragment line."""
    m = _LINE_RE.match(line.rstrip())
    if m:
        return len(m.group(1)), _clean(m.group(2)), _clean(m.group(4))
    s = line.rstrip()
    return len(s) - len(s.lstrip()), _clean(s), None


def page_blocks(page, pno, min_gap=5):
    """Column-aware blocks for ONE page -> (blocks, info)."""
    try:
        raw = page.extract_text(extraction_mode="layout") or ""
    except Exception:  # noqa: BLE001
        raw = ""
    lines = [l for l in raw.splitlines() if l.strip()]
    info = {"page": pno, "two_column": False, "pad": None, "left": 0, "right": 0,
            "input_merged": 0, "raw_lines": len(lines)}
    if not lines:
        return [], info
    parsed = [split_layout_line(l) for l in lines]
    paired = [p for p in parsed if p[2] is not None]
    info["input_merged"] = len(paired)
    right_starts = sorted(p[0] + len(p[1]) + min_gap for p in paired)
    pad = right_starts[len(right_starts) // 2] if right_starts else None
    two_col = pad is not None and len(paired) >= max(3, len(parsed) * 0.25)
    info["two_column"] = bool(two_col)
    info["pad"] = pad

    full, left, right = [], [], []
    for lead, a, b in parsed:
        if b is not None:
            left.append(a)
            right.append(b)
        elif two_col and pad is not None and lead >= pad - 4:
            right.append(a)
        elif two_col and lead > 0 and lead >= (pad or 0) * 0.6:
            right.append(a)
        else:
            full.append(a)
    info["left"], info["right"] = len(left), len(right)

    blocks = []
    groups = [full] + ([left, right] if two_col else [])
    for grp in groups:
        items = []
        for text in grp:
            text = _despace(text)
            if len(text) < 2 or _is_noise(text):
                continue
            items.append(text)
        for para in merge_paragraphs(items):
            blocks.append({"kind": "para", "text": para, "page": pno})
    return blocks, info


_HEAD_TAIL = re.compile(r"(：|:)$")
_SENT_END = "。！？；.!?;"


def looks_like_heading(text):
    """Short, no sentence ender, not starting mid-sentence, not a data line."""
    s = _clean(text)
    if not (3 <= len(s) <= 30):
        return False
    # a short question is a section heading ("什么是慢性阻塞性肺疾病？")
    if s[-1] in "？?" and len(s) <= 22:
        return True
    if s[-1] in _SENT_END:
        return False
    if s[0] in "，。、；：）】」』”’%,.;:)/\\-–—":
        return False
    if re.match(r"^[\d\s.,%－\-–—]+$", s):
        return False
    if _HEAD_TAIL.search(s):
        return True
    cjk = sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff")
    return cjk >= max(3, len(s) * 0.6)


def merge_paragraphs(items, max_len=220, min_len=24):
    """Join wrapped lines into paragraphs; heading-like lines stand alone."""
    out, buf = [], ""
    for it in items:
        if looks_like_heading(it):
            if buf:
                out.append(buf)
                buf = ""
            out.append(it)
            continue
        buf = (buf + it) if buf else it
        if len(buf) >= min_len and buf[-1] in "。！？；":
            out.append(buf)
            buf = ""
        elif len(buf) >= max_len:
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out


def paginate_layout(path, min_gap=5):
    """Column-aware blocks built from layout-mode lines. Returns (blocks, report)."""
    import pypdf
    reader = pypdf.PdfReader(path, strict=False)
    blocks = []
    report = {"pages": 0, "two_column_pages": 0, "lines": 0, "readable": 0,
              "columns": [], "mode": "columns", "input_merged": 0, "output_merged": 0}
    for pno, page in enumerate(reader.pages, start=1):
        page_out, info = page_blocks(page, pno, min_gap)
        if not info["raw_lines"]:
            continue
        blocks.extend(page_out)
        report["pages"] += 1
        report["input_merged"] += info["input_merged"]
        report["two_column_pages"] += 1 if info["two_column"] else 0
        report["columns"].append({k: info[k] for k in
                                  ("page", "two_column", "pad", "left", "right", "input_merged")})
        for b in page_out:
            report["lines"] += 1
            report["readable"] += 1 if is_readable_line(b["text"]) else 0
            report["output_merged"] += 1 if _line_has_gap(b["text"], min_gap) else 0
    report["readable_ratio"] = round(report["readable"] / max(1, report["lines"]), 4)
    return blocks, report


def _line_has_gap(text, min_gap=5):
    return re.search(r"\s{%d,}" % min_gap, text or "") is not None


_CJK_SPACE = re.compile(r"(?<=[\u4e00-\u9fff])[ \t]+(?=[\u4e00-\u9fff])")


def _despace(s):
    prev, cur = None, s
    while prev != cur:
        prev, cur = cur, _CJK_SPACE.sub("", cur)
    return cur


_NOISE = re.compile(
    r"ISSN|CN\s*\d|网络首发|编辑部|引用格式|出版确认|收稿日期|本文编辑|版权|©|"
    r"https?://|www\.|出版管理条例|期刊出版管理规定|学术不端|录用定稿|排版定稿|"
    r"整期汇编|广电总局|签约期刊|网络版|印刷出版|中图分类号|文献标志码|"
    r"实用医学杂志|The Journal of|第\s*\d+\s*卷|Vol\.|No\.\s*\d+", re.I)


def _is_noise(text):
    return len(_NOISE.findall(text)) >= 1 and len(text) < 90


def paginate_flow(path, mode="flow"):
    """Visitor-coordinate extraction (single-column pages). Kept for comparison."""
    import pypdf
    reader = pypdf.PdfReader(path, strict=False)
    blocks, report = [], {"mode": mode, "pages": 0, "two_column_pages": 0, "quality": []}
    for i, page in enumerate(reader.pages, start=1):
        parts = extract_positioned(page)
        if not parts:
            continue
        w = page_width(page)
        split = detect_gutter(parts, w) if mode != "flow" else None
        report["pages"] += 1
        if split:
            report["two_column_pages"] += 1
        lines = build_lines(parts, split)
        report["quality"].append(quality(lines))
        for ln in lines:
            blocks.append({"kind": "para", "text": _despace(ln["text"]), "page": i})
    tot = sum(q["lines"] for q in report["quality"]) or 1
    ok = sum(q["readable"] for q in report["quality"])
    report["readable_ratio"] = round(ok / tot, 4)
    report["merge_defects"] = sum(q.get("merge_defects", 0) for q in report["quality"])
    report["merge_ratio"] = round(report["merge_defects"] / tot, 4)
    report["total_lines"] = tot
    return blocks, report


def paginate(path, mode="auto"):
    """auto/columns -> column-aware layout mode; flow -> visitor coordinates."""
    if mode == "flow":
        return paginate_flow(path)
    return paginate_layout(path)

