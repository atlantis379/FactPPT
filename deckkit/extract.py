# -*- coding: utf-8 -*-
"""
Document -> deck.json extractor.

Deterministic and extractive: every string that ends up on a slide is copied
from the source document (no generation, no paraphrase, no invented numbers).
That keeps generic decks source-faithful by construction.

Supported inputs: .docx (python-docx), .pdf (pypdf), .txt/.md.
"""
import io
import os
import re

# --------------------------------------------------------------------- typing
BLOCK_KINDS = ("heading", "para", "bullet", "table")

_HEAD_NUM = re.compile(r"^\s*(?:第\s*[0-9一二三四五六七八九十]+\s*[章节部分]|[0-9]{1,2}(?:\.[0-9]{1,2}){0,3}\s*[、.．)）]?\s*|[一二三四五六七八九十]{1,3}\s*[、.．)）])\s*\S")
_HEAD_MD = re.compile(r"^\s*#{1,4}\s+\S")
_BULLET = re.compile(r"^\s*(?:[-*•·▪◦]|\(?[0-9]{1,2}[)）.、]|[（(][一二三四五六七八九十]+[)）])\s*\S")
_SENT_SPLIT = re.compile(r"(?<=[。！？；!?;])\s*")
_NUM = re.compile(
    r"(?P<val>[<>≥≤≈约]?\s*\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>%|％|万|亿|倍|米/像素|米|m|km²|km2|平方公里|万元|亿元|元|分钟|小时|天|周|个月|月|年|个|处|栋|例|人|家|项|级|dBm|dB|Gbps|Mbps|GB|MB|G|M)?"
)
_WS = re.compile(r"[ \t\u3000]+")
_PAGEMARK = re.compile(r"^=====\s*PAGE\s+(\d+)\s*=====$", re.I)


_CJK_SPACE = re.compile(r"(?<=[\u4e00-\u9fff])[ \t]+(?=[\u4e00-\u9fff])")


def _despace_cjk(s):
    """PDF text layers often put a space between every CJK glyph."""
    prev = None
    cur = s
    while prev != cur:
        prev = cur
        cur = _CJK_SPACE.sub("", cur)
    return cur


_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean(s):
    s = _CTRL.sub("", str(s or ""))
    s = _WS.sub(" ", s).strip()
    return _despace_cjk(s)


# ------------------------------------------------------------------ loaders
def load_docx(path):
    import docx
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = docx.Document(path)
    blocks, page = [], 1
    body = d.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            p = Paragraph(child, d)
            t = _clean(p.text)
            if not t:
                continue
            style = (p.style.name or "").lower() if p.style is not None else ""
            if "heading" in style or "标题" in style:
                kind = "heading"
            elif _BULLET.match(t):
                kind = "bullet"
            else:
                kind = "para"
            blocks.append({"kind": kind, "text": t, "page": page})
        elif child.tag == qn("w:tbl"):
            tb = Table(child, d)
            rows = []
            for row in tb.rows:
                cells = [_clean(c.text) for c in row.cells]
                # drop the horizontal-merge duplication python-docx produces
                dedup = []
                for c in cells:
                    if not dedup or dedup[-1] != c:
                        dedup.append(c)
                if any(dedup):
                    rows.append(dedup)
            if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
                blocks.append({"kind": "table", "rows": rows, "page": page})
    # .docx carries no physical pages: give every ~22 blocks a pseudo page so the
    # source footline stays informative instead of always reading "p.1"
    for i, b in enumerate(blocks):
        b["page"] = 1 + i // 22
    return blocks


_PDF_BOILER = re.compile(
    r"ISSN|CN\s*\d|网络首发|编辑部|引用格式|出版确认|收稿日期|本文编辑|版权|©|"
    r"https?://|link\.cnki|www\.|https：|网络首发地址|网络首发时间|"
    r"出版管理条例|期刊出版管理规定|学术不端|录用定稿|排版定稿|整期汇编|"
    r"中图分类号|文献标志码|通信作者|Corresponding|E-?mail|doi|DOI|"
    r"实用医学杂志|第\s*\d+\s*卷|Vol\.|No\.\s*\d+|The Journal of|"
    r"广播电视|广电总局|签约期刊|网络版|印刷出版",
    re.I)


def _pdf_noise(text):
    tt = _clean(text)
    if len(re.findall(_PDF_BOILER, tt)) >= 2:
        return True
    if len(tt) < 60 and _PDF_BOILER.search(tt):
        return True
    # a line that is mostly latin metadata/URLs carries no deck value
    cjk = sum(1 for ch in tt if "\u4e00" <= ch <= "\u9fff")
    if len(tt) > 40 and cjk / max(1, len(tt)) < 0.2 and _PDF_BOILER.search(tt):
        return True
    return False


def _meta_ish(text):
    """Heuristic: journal/author metadata rather than article prose."""
    tt = _clean(text)
    if not tt:
        return True
    cjk = sum(1 for ch in tt if "\u4e00" <= ch <= "\u9fff")
    digits = sum(1 for ch in tt if ch.isdigit())
    latin = sum(1 for ch in tt if ch.isascii() and ch.isalpha())
    if _PDF_BOILER.search(tt):
        return True
    if len(tt) < 26 and ("：" in tt or ":" in tt):
        return True
    if latin > cjk * 1.5:
        return True
    if digits > len(tt) * 0.3:
        return True
    return False


def _looks_like_title(text):
    """A journal/report title line: substantial CJK, no sentence terminator."""
    s = _clean(text)
    if not (16 <= len(s) <= 90):
        return False
    if s.endswith(("。", "；", "，", "：", ".", ",", ";", "?")):
        return False
    cjk = sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff")
    return cjk >= 12 and not _FORM_LIKE.search(s)


def _trim_front_matter(blocks, limit=160):
    """Drop leading metadata blocks so a PDF deck starts with real content, but
    never trim past the title itself."""
    for i, b in enumerate(blocks[:limit]):
        if b.get("kind") == "table":
            return blocks[i:]
        txt = b.get("text", "")
        if _looks_like_title(txt):
            return blocks[i:]
        if len(_clean(txt)) >= 60 and not _meta_ish(txt):
            return blocks[i:]
    return blocks


# --------------------------------------------------------------- pdf cleanups
_CITE = re.compile(
    r"[（(]\s*\d{1,4}\s*(?:[,，、\-–—~]\s*\d{1,4}\s*)*[)）]"      # (471,1129)
    r"|［[\d,，、\-–—~\s]{1,24}］"                                     # ［42］
    r"|\[\d{1,3}(?:[,，]\s*\d{1,3})*\]"                              # [3]
)


def _strip_citations(s):
    """Remove reference numbers so they cannot leak into slides or KPI values."""
    prev, cur = None, s
    while prev != cur:
        prev, cur = cur, _CITE.sub("", cur)
    return _WS.sub(" ", cur).strip()


_FURNITURE_KEY = re.compile(r"[\d\s'’\"“”《》()（）\[\]［］:：,，.。;；、\-–—_]+")


def _furniture_key(txt):
    """Page furniture differs only by its page number / punctuation."""
    return _FURNITURE_KEY.sub("", txt or "")


def _drop_page_furniture(lines, min_pages=3, share=0.25, min_len=6, top_pages=3):
    """Drop running heads/footers.

    Two signals, either is sufficient:
      * the same NORMALISED line on a large share of pages (classic furniture)
      * a short line appearing at the TOP of `top_pages` or more pages
        (running heads carry the page number, so exact matching never fires)
    """
    from collections import defaultdict
    pages_of = defaultdict(set)
    top_of = defaultdict(set)
    keyed = defaultdict(list)
    for txt, pno, order in lines:
        k = _furniture_key(txt)
        if len(k) < min_len:
            continue
        pages_of[k].add(pno)
        keyed[k].append((txt, pno))
        if order <= 1 and len(txt) <= 90:
            top_of[k].add(pno)
    total_pages = len({p for _t, p, _o in lines}) or 1
    threshold = max(min_pages, int(total_pages * share))
    repeated = {k for k, pgs in pages_of.items() if len(pgs) >= threshold}
    repeated |= {k for k, pgs in top_of.items() if len(pgs) >= top_pages}
    # running heads repeat verbatim on a few pages and read as full sentences
    # ("…免责声明的段落"), while genuine repeated headings are short.
    for txt, pno, _o in lines:
        k = _furniture_key(txt)
        if len(k) >= min_len and len(txt) >= 14 and txt[-1] not in "。！？；":
            if len({q for _t, q, _oo in lines if _furniture_key(_t) == k}) >= top_pages:
                repeated.add(k)
    if not repeated:
        return lines, set()
    dropped = set()
    for k in repeated:
        for txt, _p in keyed[k]:
            if len(txt) <= 90:
                dropped.add(txt)
    kept = [ln for ln in lines if ln[0] not in dropped]
    return kept, dropped


def _drop_duplicate_blocks(blocks):
    """Layered PDFs re-emit the same text; a repeated paragraph adds nothing."""
    seen, out = set(), []
    for b in blocks:
        key = _clean(b.get("text", ""))
        if len(key) >= 12:
            if key in seen:
                continue
            seen.add(key)
        out.append(b)
    return out


def _looks_like_fragment(text):
    """A line that begins mid-sentence (after our cleanups) is not a heading."""
    s = _clean(text)
    if not s:
        return True
    if s[0] in "，。、；：）】」』”’%,.;:)":
        return True
    if s[0] in "/\-–—" and not s[:2].replace(" ", "").isdigit():
        return True
    return False


def _parse_pages(spec):
    """'14-147' / '14-' / '-147' / '5' -> (lo, hi); None -> whole document."""
    if not spec:
        return (1, 10 ** 9)
    m = re.match(r"^\s*(\d+)?\s*(?:-\s*(\d+)?)?\s*$", str(spec))
    if not m or (m.group(1) is None and m.group(2) is None):
        raise ValueError(f"bad --pages value {spec!r}; use e.g. 14-147")
    lo = int(m.group(1)) if m.group(1) else 1
    hi = int(m.group(2)) if m.group(2) else 10 ** 9
    if hi < lo:
        raise ValueError(f"bad --pages range {spec!r}")
    return (lo, hi)


def load_pdf(path, mode="auto", pages=None):
    """Extract PDF text blocks.

    mode="auto"/"columns" -> column-aware (layout mode + gutter split), which
    avoids fusing the two columns of a journal/report page into one line.
    mode="flow"           -> plain line-order extraction.
    """
    import pypdf
    lo, hi = _parse_pages(pages)
    lines = []
    if mode != "flow":
        from . import pdf_columns as PC
        reader = pypdf.PdfReader(path, strict=False)
        for pno, page in enumerate(reader.pages, start=1):
            if not (lo <= pno <= hi):
                continue
            blocks_page, _info = PC.page_blocks(page, pno)
            for order, b in enumerate(blocks_page):
                lines.append((b["text"], pno, order))
    else:
        reader = pypdf.PdfReader(path, strict=False)
        for i, page in enumerate(reader.pages, start=1):
            if not (lo <= i <= hi):
                continue
            raw = ""
            try:
                raw = page.extract_text(extraction_mode="layout") or ""
            except Exception:  # noqa: BLE001
                raw = ""
            if not raw.strip():
                try:
                    raw = page.extract_text() or ""
                except Exception:  # noqa: BLE001
                    raw = ""
            for order, line in enumerate(raw.splitlines()):
                lines.append((line, i, order))

    lines = [(_strip_citations(_clean(x)), p, o) for x, p, o in lines]
    lines = [(x, p, o) for x, p, o in lines if x]
    lines, _furniture = _drop_page_furniture(lines)

    blocks = []
    for raw_text, page_no, _order in lines:
        t = _clean(raw_text)
        if not t or _pdf_noise(t):
            continue
        if _HEAD_NUM.match(t) or _HEAD_MD.match(t):
            kind = "heading"
        elif _BULLET.match(t):
            kind = "bullet"
        else:
            kind = "para"
        blocks.append({"kind": kind, "text": t, "page": page_no})
    blocks = _drop_duplicate_blocks(blocks)
    return _trim_front_matter(blocks)


def load_text(path):
    blocks, page = [], 1
    for line in io.open(path, encoding="utf-8", errors="ignore").read().splitlines():
        m = _PAGEMARK.match(line.strip())
        if m:
            page = int(m.group(1))
            continue
        t = _clean(line)
        if not t:
            continue
        if _HEAD_MD.match(t) or _HEAD_NUM.match(t):
            kind = "heading"
        elif _BULLET.match(t):
            kind = "bullet"
        else:
            kind = "para"
        blocks.append({"kind": kind, "text": t, "page": page})
    return blocks


def load_blocks(path, pdf_mode="auto", pages=None):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        return load_docx(path)
    if ext == ".pdf":
        return load_pdf(path, mode=pdf_mode, pages=pages)
    if ext in (".txt", ".md"):
        return load_text(path)
    raise ValueError(f"unsupported input: {ext} (use .docx/.pdf/.txt/.md)")


# ------------------------------------------------------------- segmentation
_GENERIC_HEAD = re.compile(
    r"^(?:目\s*录|摘\s*要|abstract|前\s*言|引\s*言|背\s*景|概\s*述|简\s*介|小组介绍|团队介绍|"
    r"成员介绍|人员分工|汇报提纲|提\s*纲|contents?|主要工作|工作内容|总结|结论|参考文献|致\s*谢)\s*$",
    re.I)


_FORM_LIKE = re.compile(
    r"分\s*类\s*号|单位代码|密\s*级|学\s*号|论文题目|作者姓名|指导教师|申请学位|"
    r"专业名称|论文提交|答辩日期|培养单位|UDC|中图分类号|"
    r"院\s*[（(]?系|姓\s*名|学\s*科\s*专\s*业|学\s*位\s*类\s*型|"
    r"论文扉页|学位论文|独创性声明|使用授权|本人声明|签字|日期\s*[:：]", re.I)


def _is_form_like(text):
    t = _clean(text)
    if _FORM_LIKE.search(t):
        return True
    # a line that is mostly codes / numbers / punctuation is form matter
    letters = sum(1 for ch in t if "\u4e00" <= ch <= "\u9fff")
    return letters < max(3, len(t) * 0.45)


def _filename_title(path):
    if not path:
        return ""
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = re.sub(r"[（(]?\s*[vV]\s*\d+(?:\.\d+)*\s*[)）]?\s*$", "", stem)
    stem = re.sub(r"[（(][^)）]*[)）]\s*$", "", stem)
    return _clean(stem)


def _join_wrapped_title(title, blocks, idx, limit=90):
    """Append the following block when it continues a wrapped title."""
    if not title or title.endswith(("。", "；", "，", "：", ".", ",", "?", "！")):
        return title
    for j in (idx + 1, idx + 2):
        if j >= len(blocks):
            break
        nb = blocks[j]
        if nb.get("kind") not in ("para", "heading"):
            continue
        nxt = _clean(nb.get("text", ""))
        if not (5 <= len(nxt) <= 40):
            return title
        if re.search(r"[0-9A-Za-z]", nxt):
            return title
        cjk = sum(1 for ch in nxt if "\u4e00" <= ch <= "\u9fff")
        if cjk < 5 or cjk < len(nxt) * 0.6:
            return title
        if nxt.endswith(("。", "；", "：", "!", "?")):
            return title
        joined = title + nxt
        return joined if len(joined) <= limit else title
    return title


def detect_title(blocks, path=None):
    """Prefer a descriptive filename (users name files by topic); else best heading."""
    fn = _filename_title(path)

    def _title_like(b):
        if b.get("kind") == "table" or "text" not in b:
            return False
        s = _clean(b["text"])
        if not (10 <= len(s) <= 70):
            return False
        if s.endswith(("。", "；", "，", ".", ",", ";", "：")):
            return False
        if _GENERIC_HEAD.match(s) or _is_form_like(s) or _FORM_LIKE.search(s):
            return False
        if "：" in s or ":" in s:      # form fields read "label: value"
            return False
        return True

    heads = [b["text"] for b in blocks[:150]
             if b.get("kind") == "heading" and 6 <= len(b.get("text", "")) <= 70]
    useful = [h for h in heads if not _GENERIC_HEAD.match(h) and not _is_form_like(h)]
    # a title-like line that REPEATS (cover + title page) is the strongest signal
    # a descriptive filename is normally the most trustworthy title
    if len(fn) >= 8:
        return fn

    from collections import Counter as _C
    cand = [(_clean(b["text"]), i) for i, b in enumerate(blocks[:200]) if _title_like(b)]
    if cand:
        reps = _C(s for s, _i in cand)
        best = max(reps.items(), key=lambda kv: (kv[1], len(kv[0])))
        if best[1] >= 2 and len(best[0]) >= 10:
            return best[0]
        _first = next((i for i, b in enumerate(blocks[:200])
                       if _clean(b.get("text", "")) == best[0]), -1)
        # no repetition: the title is the earliest substantial title-like line
        # (journal articles place it at the top of page 1)
        for s, si in cand:
            if len(s) >= 16:
                return _join_wrapped_title(s, blocks, si)
        if _first >= 0:
            return _join_wrapped_title(best[0], blocks, _first)
        longest = max(reps.keys(), key=len)
        if len(longest) >= 12:
            return longest
    # a descriptive filename is usually the most reliable title
    if useful:
        cand = max(useful[:8], key=len)
        if len(cand) >= 8:
            return cand
    if len(fn) >= 4:
        return fn
    if useful:
        return useful[0]
    for b in blocks[:20]:
        if b["kind"] == "para" and not _is_form_like(b["text"]):
            t = b["text"]
            if 6 <= len(t) <= 40 and not t.endswith(("。", "；", ".", "，", ",")):
                return t
    return (fn or (blocks[0]["text"][:40] if blocks else "Untitled"))


def _is_short_heading(text):
    if not (3 <= len(text) <= 26):
        return False
    if text.endswith(("。", "；", "，", "：", "、", ".", ",", ";")):
        return False
    # a heading has no sentence-final punctuation inside
    return not any(ch in text for ch in "。；")


def segment(blocks, title):
    """Group blocks into sections. Falls back to fixed-size chunks."""
    sections, cur = [], None
    started = False
    for b in blocks:
        t = b["text"] if b["kind"] != "table" else ""
        is_head = (b["kind"] == "heading") or (_is_short_heading(t) and len(t) <= 26)
        if b["kind"] == "table":
            is_head = False
        if is_head and _clean(t) != _clean(title):
            if cur:
                sections.append(cur)
            cur = {"heading": _clean(t), "blocks": [], "page": b.get("page", 1)}
            started = True
            continue
        if cur is None:
            cur = {"heading": "", "blocks": [], "page": b.get("page", 1)}
        cur["blocks"].append(b)
        started = True
    if cur:
        sections.append(cur)

    sections = [s for s in sections if s["blocks"] or s["heading"]]
    if len(sections) >= 4:
        return sections

    # fallback: chunk paragraphs into groups of 3
    chunks, buf = [], []
    for b in blocks:
        if _clean(b.get("text", "")) == _clean(title):
            continue
        buf.append(b)
        if len(buf) >= 3:
            chunks.append({"heading": "", "blocks": buf, "page": buf[0].get("page", 1)})
            buf = []
    if buf:
        chunks.append({"heading": "", "blocks": buf, "page": buf[0].get("page", 1)})
    return chunks


# ------------------------------------------------------------------ helpers
def sentences(text):
    parts = [p.strip() for p in _SENT_SPLIT.split(text) if p.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def numbers_in(text):
    out = []
    for m in _NUM.finditer(text):
        v = _clean(m.group("val"))
        u = _clean(m.group("unit"))
        if not v:
            continue
        # ignore bare integers that are clearly list numbering
        if not u and len(v) <= 2:
            continue
        out.append({"value": v, "unit": u, "context": _clean(text)})
    return out


def pick_text(text, budget=90):
    """Extractive: keep the most informative sentences, in original order,
    always hard-capped to `budget` characters."""
    text = _clean(text)
    if len(text) <= budget:
        return text
    sents = [s if len(s) <= budget else s[:budget].rstrip("，,。;；:：、 ") + "…"
             for s in sentences(text)]
    scored = []
    for i, s in enumerate(sents):
        score = 0.0
        if _NUM.search(s):
            score += 3.0
        if 8 <= len(s) <= budget:
            score += 1.6
        elif len(s) > budget:
            score += 0.4
        score += max(0.0, 1.2 - 0.12 * i)
        scored.append((score, i, s))
    chosen, used = [], 0
    for score, i, s in sorted(scored, key=lambda x: -x[0]):
        if used + len(s) > budget and chosen:
            continue
        chosen.append((i, s))
        used += len(s)
        if used >= budget * 0.92:
            break
    chosen.sort()
    out = "".join(s for _, s in chosen) or text[:budget]
    if len(out) > budget:                      # final guarantee
        out = out[:budget].rstrip("，,。;；:：、 ") + "…"
    return out


def heading_of(section):
    h = _clean(section.get("heading", ""))
    h = re.sub(r"^#{1,4}\s*", "", h)
    h = re.sub(r"^(?:第\s*[0-9一二三四五六七八九十]+\s*[章节部分]|[0-9]{1,2}(?:\.[0-9]{1,2}){0,3}\s*[、.．)）]?|[一二三四五六七八九十]{1,3}\s*[、.．)）])\s*", "", h)
    return h.strip(" :：.．、") or ""


def bullets_of(section):
    out = []
    for b in section["blocks"]:
        if b["kind"] in ("bullet", "para"):
            t = _clean(b.get("text", ""))
            if 6 <= len(t):
                out.append(t)
    return out


# ------------------------------------------------------------------ assembly
MOTIF_CYCLE = ["wave", "layers", "nodes", "target", "flow", "bars", "grid", "check",
               "pulse", "gauge", "globe", "shield", "scale", "doc"]

# a genuine process must show ordering, not just short lines
_SEQ = re.compile(
    r"[①②③④⑤⑥⑦⑧⑨]|第[一二三四五六七八九十]+步|步骤\s*\d|step\s*\d|"
    r"首先|其次|再次|然后|接着|最后|首先|流程|工艺|环节|阶段|路径|闭环|顺序",
    re.I)
_CONCLUSION = re.compile(r"总结|结论|展望|结语|小结|结论与展望|下一步|未来", re.I)
_JUNK_HEAD = re.compile(r"名词解释|术语|定义|参考文献|致谢|附录", re.I)
_BOILER = re.compile(r"课题来源|项目背景|公司简介|单位简介|编制说明|修订记录|封面", re.I)


def _leading_title(text, limit=16, fallback="要点"):
    """A card/step title taken from the item's own leading phrase."""
    t = _clean(text)
    for sep in ("：", ":", "——", "—", "，", ",", "。", "；", ";"):
        idx = t.find(sep)
        if 2 <= idx <= limit:
            out = t[:idx].strip()
            if len(out) >= 2:
                return out
            break
    out = t[:limit].rstrip("，,。;；:：、 ")
    return out if len(out) >= 2 else fallback


def _is_listlike(bl):
    return len(bl) >= 2 and all(len(b) <= 72 for b in bl)


def _title_echo(text, title):
    """True when `text` is the document title (optionally with a small tail)."""
    a, b = _clean(text), _clean(title)
    if not a or not b or len(b) < 6:
        return False
    if a == b:
        return True
    # allow the title plus a tiny suffix/prefix, e.g. "题目：<title>"
    if (a.startswith(b) or a.endswith(b)) and len(a) - len(b) <= 6:
        return True
    # a truncated echo: the card heading is a substantial prefix of the title
    return b.startswith(a) and len(a) >= max(8, int(len(b) * 0.5))


def _strip_title_echoes(deck):
    """Remove title repeats from slide bodies; drop slides that become empty."""
    title = (deck.get("meta") or {}).get("title", "")
    if not title:
        return deck
    kept = []
    for s in deck.get("slides", []):
        if s.get("type") in ("cover", "closing"):
            kept.append(s)
            continue
        if _title_echo(s.get("subtitle", ""), title):
            s["subtitle"] = ""
        for coll, field in (("cards", "body"), ("cards", "title"),
                            ("steps", "body"), ("items", "body")):
            for it in s.get(coll) or []:
                if _title_echo(it.get(field, ""), title):
                    it[field] = ""
        def _real(it):
            head = _clean(it.get("title"))
            body = _clean(it.get("body"))
            return bool(body) or bool(head and head not in ("要点", "说明", "概述"))

        s["cards"] = [c for c in (s.get("cards") or []) if _real(c)]
        s["steps"] = [c for c in (s.get("steps") or []) if _real(c)]
        s["items"] = [c for c in (s.get("items") or []) if _real(c)]
        empty = (s.get("type") in ("cards", "steps", "timeline")
                 and not (s.get("cards") or s.get("steps") or s.get("items")))
        if empty:
            continue
        kept.append(s)
    deck["slides"] = kept
    return deck


def even_sample(items, k):
    """Pick k items spread evenly across the list (keeps document-wide coverage)."""
    if k <= 0 or not items:
        return []
    if len(items) <= k:
        return list(items)
    step = len(items) / float(k)
    return [items[min(len(items) - 1, int(i * step))] for i in range(k)]


def _kpi_labels_trustworthy(kpis):
    """Distinct, substantially complete labels — otherwise metrics mislead."""
    labels = [(k.get("label") or "").strip() for k in kpis]
    if len(labels) < 2:
        return False
    if len(set(labels)) != len(labels):          # duplicated captions
        return False
    for lab in labels:
        if lab in ("", "—", "要点") or len(lab) < 6:
            return False
        # a label cut off mid-sentence reads as a fragment
        if not lab.endswith(("。", "；", "，", "：", "%", ")", "）")) and len(lab) >= 30:
            return False
    return True


def to_deck(blocks, *, pdf_mode="auto", pages=None, title=None, path=None, subtitle=None, brand=None, tagline=None,
            source=None, source_label="来源", author=None, org=None,
            max_slides=16, theme=None, **kw):
    title = _clean(title) or detect_title(blocks, path=path)
    sections = segment(blocks, title)

    if not subtitle:
        for b in blocks:
            if b["kind"] in ("para", "bullet") and _clean(b.get("text", "")) != title:
                subtitle = pick_text(b["text"], 46)
                break
    subtitle = subtitle or ""

    meta = {
        "brand": _clean(brand) or (title[:18] if title else "演示文稿"),
        "tagline": _clean(tagline) or subtitle[:24],
        "kicker": _clean(org) or "",
        "source": _clean(source) or "",
        "source_label": source_label,
        "footer_right": title[:30] if title else "",
        "author": _clean(author) or "",
        "org": _clean(org) or "",
        "title": title,
    }

    slides = [{"type": "cover", "title": title, "subtitle": subtitle,
               "kicker": meta["kicker"], "motif": "layers"}]
    if meta["author"] or meta["org"]:
        slides[0]["meta_lines"] = [x for x in (meta["author"], meta["org"]) if x]

    def _skip(sec):
        h = heading_of(sec)
        if _JUNK_HEAD.search(h):
            return True
        if _BOILER.search(h):
            return True
        # only an exact title repeat is cover matter (similarity skipping is unsafe)
        if h and _clean(h) == _clean(title):
            return True
        return False

    # a section must actually carry text to earn a slide (empty cover/form lines
    # otherwise consume the whole budget)
    body_sections = [s for s in sections if bullets_of(s) and not _skip(s)]
    # spread the pick across the whole document rather than taking the first N
    body_sections = even_sample(body_sections, max(0, max_slides - 2))

    for idx, sec in enumerate(body_sections):
        h = heading_of(sec)
        page = sec.get("page", 1)
        motif = MOTIF_CYCLE[idx % len(MOTIF_CYCLE)]
        bl = bullets_of(sec)
        joined = " ".join(bl)
        if not h:
            h = _leading_title(bl[0]) if bl else f"第 {idx+1} 部分"

        # 1) explicit table wins
        tbl = next((b for b in sec["blocks"] if b["kind"] == "table"), None)
        if tbl:
            rows = tbl["rows"]
            width = max(len(r) for r in rows)
            cols = rows[0] + [""] * (width - len(rows[0]))
            body = [r + [""] * (width - len(r)) for r in rows[1:]][:8]
            slides.append({"type": "table", "title": h,
                           "subtitle": pick_text(joined, 40),
                           "source_page": page, "columns": cols, "rows": body})
            continue

        # 2) metrics
        nums, seen = [], set()
        for b in sec["blocks"]:
            for n in numbers_in(b.get("text", "")):
                key = (n["value"], n["unit"])
                if key in seen:
                    continue
                seen.add(key)
                nums.append(n)
        if len(nums) >= 4 and all(len(b) < 260 for b in bl[:4]):
            kpis = []
            for n in nums[:4]:
                ctx = pick_text(n["context"], 40)
                ctx = ctx.replace(n["value"], "").replace(n["unit"], "", 1).strip(" ，,。;；:：")
                kpis.append({"value": n["value"], "unit": n["unit"], "tag": "",
                             "label": ctx[:40] or "—"})
            if _kpi_labels_trustworthy(kpis):
                slides.append({"type": "kpi", "title": h, "subtitle": pick_text(joined, 46),
                               "source_page": page, "figure": motif,
                               "figure_size": [420, 180], "kpis": kpis})
                continue
            # labels are not trustworthy -> fall through to a text layout

        # 3) process ONLY when ordering is explicit
        if _is_listlike(bl) and 2 <= len(bl) <= 4 and _SEQ.search(h + joined[:160]):
            steps = []
            for i, b in enumerate(bl):
                steps.append({"title": _leading_title(b), "qualifier": "",
                              "body": pick_text(b, 68),
                              "motif": MOTIF_CYCLE[(idx + i) % len(MOTIF_CYCLE)]})
            slides.append({"type": "steps", "title": h,
                           "subtitle": pick_text(joined, 44), "source_page": page,
                           "steps": steps, "rail": [s["title"][:6] for s in steps],
                           "callout_label": "", "callout": ""})
            continue

        # 4) list-like section -> one card per item (best for enumerations)
        if _is_listlike(bl) and 2 <= len(bl) <= 4:
            cards = [{"title": _leading_title(b), "body": pick_text(b, 84),
                      "tag": "", "tone": ["accent", "ok", "warn", "accent"][i % 4]}
                     for i, b in enumerate(bl)]
            slides.append({"type": "cards", "title": h,
                           "subtitle": pick_text(joined, 44), "source_page": page,
                           "cols": 2 if len(cards) == 2 else (3 if len(cards) == 3 else 2),
                           "figure": motif, "figure_size": [420, 168], "cards": cards})
            continue

        # 5) prose -> grouped cards
        if bl:
            groups = sentences(joined)
            ncards = 3 if len(joined) > 220 else 2
            per = max(1, len(groups) // ncards)
            cards, i = [], 0
            for c in range(ncards):
                chunk = "".join(groups[i:i + per]) if groups else joined
                i += per
                cards.append({"title": _leading_title(chunk, 14),
                              "body": pick_text(chunk, 78), "tag": "",
                              "tone": ["accent", "ok", "warn"][c % 3]})
            slides.append({"type": "cards", "title": h,
                           "subtitle": pick_text(joined, 44), "source_page": page,
                           "cols": 2 if ncards == 2 else 3,
                           "figure": motif, "figure_size": [420, 168], "cards": cards})
            continue

    # closing: prefer an explicit conclusion section, else the last body sentence
    tail = ""
    for sec in body_sections:
        if _CONCLUSION.search(heading_of(sec) or ""):
            for b in sec["blocks"]:
                if b["kind"] in ("para", "bullet"):
                    tail = pick_text(b["text"], 86)
                    break
        if tail:
            break
    if not tail:
        for sec in reversed(body_sections):
            for b in reversed(sec["blocks"]):
                if b["kind"] in ("para", "bullet") and len(_clean(b.get("text", ""))) >= 20:
                    tail = pick_text(b["text"], 86)
                    break
            if tail:
                break
    slides.append({"type": "closing", "title": "总结", "subtitle": "",
                   "body": tail or subtitle, "motif": "check",
                   "meta_lines": [meta["footer_right"]]})

    return _strip_title_echoes({"meta": meta, "theme": theme or "corporate",
                                "slides": slides})
