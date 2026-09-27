"""Load raw materials into addressable source units.

A *unit* is the smallest piece of source text we can point at: one PPTX text box,
one PPTX table cell, one PDF page, or one transcribed cell of an image.
Facts may only quote text that exists inside a unit, so every unit carries a
stable id, a human-readable location and the SHA-256 of the file it came from.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Unit:
    id: str
    source_id: str
    location: str          # human readable, e.g. "第7页 表格 第8行第3列"
    text: str
    method: str            # pptx_text | pptx_table_cell | pdf_page | image_transcription
    needs_confirmation: bool = False
    alt_text: str = ""     # another reading of the same unit (e.g. PDF columns read separately)


@dataclass
class Source:
    id: str
    filename: str
    sha256: str
    kind: str
    title: str


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(text: str) -> str:
    """Whitespace/width-insensitive form used for quote matching. Never used for display."""
    table = str.maketrans({"　": " ", " ": " ", "\t": " ", "‑": "-", "‐": "-"})
    return re.sub(r"\s+", "", text.translate(table))


def _pptx_units(source_id: str, slides: list[dict]) -> list[Unit]:
    units: list[Unit] = []
    for slide in slides:
        n = slide["slide"]
        box = tab = 0
        for shape in slide["shapes"]:
            if shape["kind"] == "text":
                box += 1
                units.append(Unit(f"{source_id}:s{n}:b{box}", source_id, f"第{n}页 文本框{box}",
                                  shape["text"], "pptx_text"))
            elif shape["kind"] == "table":
                tab += 1
                for r, row in enumerate(shape["rows"], 1):
                    for c, cell in enumerate(row, 1):
                        if cell.strip():
                            units.append(Unit(f"{source_id}:s{n}:t{tab}r{r}c{c}", source_id,
                                              f"第{n}页 表格{tab} 第{r}行第{c}列", cell, "pptx_table_cell"))
        if slide.get("notes", "").strip():
            units.append(Unit(f"{source_id}:s{n}:notes", source_id, f"第{n}页 演讲者备注",
                              slide["notes"], "pptx_notes"))
    return units


def _pptx_to_slides(path: Path) -> list[dict]:
    from pptx import Presentation

    def walk(shape, out):
        if shape.shape_type == 6:
            for child in shape.shapes:
                walk(child, out)
        elif getattr(shape, "has_table", False) and shape.has_table:
            out.append({"kind": "table", "rows": [[c.text for c in row.cells] for row in shape.table.rows]})
        elif getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
            out.append({"kind": "text", "text": shape.text_frame.text})

    slides = []
    for i, slide in enumerate(Presentation(str(path)).slides, 1):
        shapes: list[dict] = []
        for shape in slide.shapes:
            walk(shape, shapes)
        notes = slide.notes_slide.notes_text_frame.text if slide.has_notes_slide else ""
        slides.append({"slide": i, "shapes": shapes, "notes": notes})
    return slides


def _pdf_units(source_id: str, path: Path) -> list[Unit]:
    """One unit per page. poppler's pdftotext does reading-order analysis, which keeps
    two-column journal text and full-width tables in the right order (pdfplumber's
    line-by-line extraction interleaves the columns)."""
    import subprocess
    import pdfplumber
    columns = []
    with pdfplumber.open(str(path)) as pdf:
        pages = len(pdf.pages)
        for page in pdf.pages:   # second reading: left column, then right column
            w, h = page.width, page.height
            columns.append((page.crop((0, 0, w / 2, h)).extract_text() or "") + "\n" +
                           (page.crop((w / 2, 0, w, h)).extract_text() or ""))
    units = []
    for i in range(1, pages + 1):
        try:
            text = subprocess.run(["pdftotext", "-f", str(i), "-l", str(i), "-enc", "UTF-8", str(path), "-"],
                                  capture_output=True, text=True, check=True, encoding="utf-8").stdout
        except (OSError, subprocess.CalledProcessError):   # poppler not installed (typical on Windows)
            with pdfplumber.open(str(path)) as pdf:
                text = pdf.pages[i - 1].extract_text() or ""
        units.append(Unit(f"{source_id}:p{i}", source_id, f"第{i}页", text, "pdf_page",
                          alt_text=columns[i - 1]))
    return units


def _stem(path: Path) -> str:
    name = path.name
    for suffix in (".text.json", ".pptx", ".pdf", ".jpg", ".jpeg", ".png"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def load_sources(folder: Path, manifest: Path | None = None, transcriptions: Path | None = None
                 ) -> tuple[list[Source], list[Unit]]:
    """Read every supported file in `folder`.

    Source ids come from `manifest` ({"S07": "<file stem>", ...}) so that fact references stay
    valid when files are added or renamed around them; unknown files get the next free id and
    the manifest is updated. `.pptx` is read directly; a `<stem>.text.json` dump (made on the
    user's machine when the original was too large to transfer) is used only if the `.pptx`
    is absent. Images need `<name>.transcription.json` next to them or in `transcriptions`.
    """
    ids: dict[str, str] = {}
    if manifest and manifest.exists():
        ids = {v: k for k, v in json.loads(manifest.read_text(encoding="utf-8")).items()}
    candidates = [p for p in folder.iterdir() if p.is_file() and not p.name.endswith(".transcription.json")
                  and p.suffix.lower() in {".pptx", ".pdf", ".jpg", ".jpeg", ".png", ".json"}]
    chosen: dict[str, Path] = {}
    for p in sorted(candidates):
        if p.suffix.lower() == ".json" and not p.name.endswith(".text.json"):
            continue
        stem = _stem(p)
        if stem in chosen and chosen[stem].suffix.lower() == ".pptx":
            continue
        chosen[stem] = p
    used = set(ids.values())
    next_no = max([int(x[1:]) for x in used] + [0]) + 1
    for stem in sorted(chosen):
        if stem not in ids:
            ids[stem] = f"S{next_no:02d}"
            next_no += 1
    if manifest:
        manifest.write_text(json.dumps({v: k for k, v in sorted(ids.items(), key=lambda kv: kv[1])},
                                       ensure_ascii=False, indent=1), encoding="utf-8")

    sources: list[Source] = []
    units: list[Unit] = []
    for stem, path in sorted(chosen.items(), key=lambda kv: ids[kv[0]]):
        sid, name = ids[stem], path.name
        if name.endswith(".text.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            sources.append(Source(sid, stem + ".pptx", sha256_file(path), "pptx(text dump)", stem))
            units += _pptx_units(sid, data["slides"])
        elif path.suffix.lower() == ".pptx":
            sources.append(Source(sid, name, sha256_file(path), "pptx", stem))
            units += _pptx_units(sid, _pptx_to_slides(path))
        elif path.suffix.lower() == ".pdf":
            sources.append(Source(sid, name, sha256_file(path), "pdf", stem))
            units += _pdf_units(sid, path)
        else:
            tr = path.with_name(name + ".transcription.json")
            if not tr.exists() and transcriptions:
                tr = transcriptions / (name + ".transcription.json")
            t = json.loads(tr.read_text(encoding="utf-8")) if tr.exists() else None
            sources.append(Source(sid, name, sha256_file(path), "image", (t or {}).get("title", stem)))
            if t:
                confirmed = t.get("independent_reads", 1) >= 2 and t.get("reads_agree", False)
                for cell in t["cells"]:
                    units.append(Unit(f"{sid}:{cell['id']}", sid, cell["location"], cell["text"],
                                      "image_transcription", needs_confirmation=not confirmed))
    return sources, units


def save(sources: list[Source], units: list[Unit], out: Path) -> None:
    out.write_text(json.dumps({"sources": [asdict(s) for s in sources],
                               "units": [asdict(u) for u in units]}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
