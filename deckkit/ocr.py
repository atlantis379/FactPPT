"""OCR ingest for scanned documents.

Why this exists
---------------
A scanned PDF carries page images and no text layer, so the extractor sees
nothing at all. That was a documented limit of this toolkit; teaching materials
photographed with a phone scanner are exactly that case.

What it produces
----------------
The SAME block shape ``extract.py`` consumes, plus provenance the text path never
needs:

    {"kind": ..., "text": ..., "page": n,
     "ocr_confidence": 0.97, "ocr_image": "Im1.jpg", "ocr_low_confidence": False}

OCR is a lossy, fallible transform on medical text. A misread number or negation
is a safety problem, so every line keeps its confidence and low-confidence lines
are FLAGGED for review rather than silently trusted.

Engine
------
``rapidocr_onnxruntime`` (PaddleOCR models on ONNX Runtime). PaddleOCR itself is
importable here but its native runtime is broken (``libpaddle`` missing), so the
ONNX port is the working path.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

#: images smaller than this are watermarks/logos/thumbs, not page content
MIN_IMAGE_BYTES = 60_000
#: below this OCR score a line is flagged for human review
LOW_CONFIDENCE = 0.90

_WS = re.compile(r"[ \t\u3000]+")
_CJK_SPACE = re.compile(r"(?<=[\u4e00-\u9fff])[ \t]+(?=[\u4e00-\u9fff])")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean(s: str) -> str:
    s = _CTRL.sub("", str(s or ""))
    s = _WS.sub(" ", s).strip()
    prev = None
    while prev != s:
        prev, s = s, _CJK_SPACE.sub("", s)
    return s


_ENGINE: Any = None


def engine():
    """Lazily construct the OCR engine (model load is the slow part)."""
    global _ENGINE
    if _ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _ENGINE = RapidOCR()
    return _ENGINE


# ------------------------------------------------------------------ extraction
def page_images(pdf_path: str | Path, *, min_bytes: int = MIN_IMAGE_BYTES) -> list[dict]:
    """Embedded page images big enough to be page content."""
    import pypdf
    reader = pypdf.PdfReader(str(pdf_path), strict=False)
    found = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            images = list(page.images)
        except Exception:  # noqa: BLE001
            continue
        for order, image in enumerate(images):
            data = image.data
            if len(data) < min_bytes:
                continue
            found.append({"page": number, "order": order,
                          "name": getattr(image, "name", f"p{number}_{order}"),
                          "bytes": data})
    return found


def _group_paragraphs(lines: Sequence[tuple[float, str]], max_len: int = 240) -> list[str]:
    """Join OCR lines into paragraphs; a line ending a sentence closes one.

    Kept as a pure helper so it can be unit-tested without the engine.
    """
    paragraphs: list[str] = []
    buffer = ""
    for _top, text in lines:
        buffer = (buffer + text) if buffer else text
        if len(buffer) >= 24 and buffer.endswith(("。", "！", "？", "；")):
            paragraphs.append(buffer)
            buffer = ""
        elif len(buffer) >= max_len:
            paragraphs.append(buffer)
            buffer = ""
    if buffer:
        paragraphs.append(buffer)
    return paragraphs


def ocr_image(data: bytes) -> dict:
    """OCR one image -> ordered lines with confidence."""
    import numpy as np
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        array = np.array(image.convert("RGB"))
    result, _elapsed = engine()(array)
    rows = []
    for box, text, score in (result or []):
        cleaned = _clean(text)
        if not cleaned:
            continue
        ys = [point[1] for point in box]
        xs = [point[0] for point in box]
        rows.append({"top": float(min(ys)), "left": float(min(xs)),
                     "text": cleaned, "score": float(score)})
    rows.sort(key=lambda r: (round(r["top"] / 12.0), r["left"]))
    return {"lines": rows}


_FURNITURE = re.compile(r"^(NOTES?\s*\d*|\d{1,3}|[ivxlcdm]{1,6})$", re.I)
#: scan footers get glued INTO a paragraph by the line merger, in either order
#: ("NOTES47" and "61NOTES" both occur), so they are stripped as tokens
_FURNITURE_TOKEN = re.compile(r"(?:NOTES?\s*\d+|\d+\s*NOTES?)(?![\d])", re.I)
#: stray table-border / column artefacts left by the recogniser
_BORDER = re.compile(r"^[|｜丨\-—_=~]+")
_FURNITURE_KEY = re.compile(r"[\d\s\W_]+")


def _strip_furniture_tokens(text: str) -> str:
    cleaned = _FURNITURE_TOKEN.sub("", text or "")
    cleaned = _BORDER.sub("", cleaned.strip())
    return _clean(cleaned)


def strip_running_head(blocks: list[dict], *, min_share: float = 0.25,
                       max_len: int = 24, min_keep: int = 12,
                       rounds: int = 4) -> int:
    """Remove page running heads that got glued to the front of paragraphs.

    A scan repeats a header at the top of every page (the chapter title, or the
    section name), and the line merger prepends it to that page's first paragraph.
    The threshold is therefore derived from the number of PAGES, not blocks: a
    header appears about once per page, which can be a small fraction of blocks.

    The longest qualifying prefix wins, so "第六章肺部感染性疾病" is stripped whole
    rather than leaving a dangling "病". Several header families can coexist, so
    the pass repeats. A strip only happens when a substantial remainder survives.
    Returns the number of blocks changed, keeping the edit auditable.
    """
    from collections import Counter
    pages = len({block.get("page") for block in blocks}) or 1
    threshold = max(3, int(pages * min_share))
    changed = 0
    for _round in range(rounds):
        counts: Counter = Counter()
        for block in blocks:
            text = block.get("text", "")
            for length in range(4, min(max_len, len(text)) + 1):
                counts[text[:length]] += 1
        best = ""
        for prefix, count in counts.items():
            if count >= threshold and len(prefix) > len(best):
                best = prefix
        if not best:
            break
        touched = 0
        for block in blocks:
            text = block.get("text", "")
            if text.startswith(best) and len(text) - len(best) >= min_keep:
                block["text"] = _clean(text[len(best):].lstrip("，。、；：.· "))
                touched += 1
        if not touched:
            break
        changed += touched
    return changed


def _furniture_key(text: str) -> str:
    """Normalised key for cross-page repetition (digits/punctuation stripped)."""
    return _FURNITURE_KEY.sub("", text or "")


def _drop_furniture(pages_rows: Sequence[tuple[int, list[dict]]], *,
                    share: float = 0.30, min_pages: int = 3) -> tuple[list, set]:
    """Remove running heads/footers and page numbers from OCR rows.

    Scan footers ("NOTES47", bare page numbers) are page furniture, not content.
    They are detected by normalised cross-page repetition plus a furniture
    pattern -- the same principle used on text-layer PDFs, where it needs
    coordinates; here the repetition alone is enough.
    """
    from collections import defaultdict
    pages_of = defaultdict(set)
    for page, rows in pages_rows:
        for row in rows:
            key = _furniture_key(row["text"])
            if len(key) >= 3:
                pages_of[key].add(page)
    total_pages = len({p for p, _ in pages_rows}) or 1
    threshold = max(min_pages, int(total_pages * share))
    repeated = {key for key, pages in pages_of.items() if len(pages) >= threshold}

    kept: list[tuple[int, list[dict]]] = []
    dropped: set[str] = set()
    for page, rows in pages_rows:
        survivors = []
        for row in rows:
            text = row["text"]
            if _FURNITURE.match(text) or _furniture_key(text) in repeated:
                dropped.add(text)
                continue
            survivors.append(row)
        kept.append((page, survivors))
    return kept, dropped


def ocr_pdf(path: str | Path, *, min_bytes: int = MIN_IMAGE_BYTES,
            low_confidence: float = LOW_CONFIDENCE, progress=None) -> tuple[list[dict], dict]:
    """OCR a scanned PDF into extractor-shaped blocks. Returns (blocks, report)."""
    images = page_images(path, min_bytes=min_bytes)
    pages_rows: list[tuple[int, list[dict]]] = []
    report = {"file": str(path), "pages_ocred": 0, "lines": 0,
              "low_confidence_lines": 0, "min_score": None, "pages": {},
              "furniture_dropped": 0, "engine": "rapidocr_onnxruntime"}
    for index, item in enumerate(images, start=1):
        if progress:
            progress(index, len(images), item["page"])
        pages_rows.append((item["page"], ocr_image(item["bytes"])["lines"]))

    pages_rows, dropped = _drop_furniture(pages_rows)
    report["furniture_dropped"] = len(dropped)

    blocks: list[dict] = []
    for page, rows in pages_rows:
        scores = [r["score"] for r in rows] or [0.0]
        image_name = next((i["name"] for i in images if i["page"] == page), "")
        report["pages_ocred"] += 1
        report["lines"] += len(rows)
        report["pages"][str(page)] = {
            "lines": len(rows), "min_score": round(min(scores), 3),
            "mean_score": round(sum(scores) / len(scores), 3),
            "image": image_name,
        }
        report["min_score"] = round(min(scores), 3) if report["min_score"] is None \
            else min(report["min_score"], round(min(scores), 3))
        # Paragraph grouping keeps per-line confidence by attributing the WEAKEST
        # line in the paragraph: a paragraph is only as trustworthy as its worst line.
        groups: list[list[dict]] = []
        buffer: list[dict] = []
        length = 0
        for row in rows:
            buffer.append(row)
            length += len(row["text"])
            if length >= 24 and row["text"].endswith(("。", "！", "？", "；")):
                groups.append(buffer)
                buffer, length = [], 0
            elif length >= 240:
                groups.append(buffer)
                buffer, length = [], 0
        if buffer:
            groups.append(buffer)
        for group in groups:
            text = _strip_furniture_tokens("".join(r["text"] for r in group))
            if not text:
                continue
            weakest = min(r["score"] for r in group)
            low = weakest < low_confidence
            if low:
                report["low_confidence_lines"] += 1
            blocks.append({"kind": "para", "text": text, "page": page,
                           "ocr_confidence": round(weakest, 3),
                           "ocr_image": image_name,
                           "ocr_low_confidence": low})
    return blocks, report


def write_blocks(path: str | Path, blocks: list[dict], report: dict,
                 target: str | Path) -> str:
    payload = {"source": str(path), "report": report, "blocks": blocks}
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target)


def to_markdown(blocks: Sequence[dict], *, page_marker: str = "===== PAGE {page} =====") -> str:
    """Render OCR blocks as marker-delimited text for ``extract.load_text``.

    The marker matches the extractor's own ``_PAGEMARK`` so the page attribution
    the OCR produced survives into the deck: a slide can still say which scanned
    page it came from. Low-confidence blocks are marked for review rather than
    silently trusted.
    """
    lines: list[str] = []
    current = None
    for block in blocks:
        page = block.get("page")
        if page != current:
            lines.append("")
            lines.append(page_marker.format(page=page))
            current = page
        text = block.get("text", "")
        if block.get("ocr_low_confidence"):
            text = f"{text}  [OCR低置信 {block.get('ocr_confidence')} 需人工核对]"
        lines.append(text)
    return "\n".join(lines).strip() + "\n"


def write_markdown(blocks: Sequence[dict], target: str | Path) -> str:
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(to_markdown(blocks), encoding="utf-8")
    return str(target)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        print("usage: python -m deckkit.ocr PDF [-o BLOCKS.json] [--md TEXT.md] "
              "[--min-score 0.9]")
        return 2
    pdf = args[0]
    target = args[args.index("-o") + 1] if "-o" in args else "deckkit/out/ocr_blocks.json"
    md_target = args[args.index("--md") + 1] if "--md" in args else None
    low = float(args[args.index("--min-score") + 1]) if "--min-score" in args else LOW_CONFIDENCE

    def progress(index: int, total: int, page: int) -> None:
        print(f"  OCR {index}/{total} (page {page})", flush=True)

    blocks, report = ocr_pdf(pdf, low_confidence=low, progress=progress)
    write_blocks(pdf, blocks, report, target)
    if md_target:
        write_markdown(blocks, md_target)
        print("markdown written to", md_target)
    print(json.dumps({k: v for k, v in report.items() if k != "pages"},
                     ensure_ascii=False, indent=2))
    print("blocks written to", target)
    return 0 if blocks else 1


if __name__ == "__main__":
    raise SystemExit(main())
