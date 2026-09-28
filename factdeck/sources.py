"""Folder-based loading for the command line (the app stores sources itself).

Source ids come from `sources_manifest.json` ({"S07": "<file stem>", ...}) so fact
references stay valid when files are added or renamed around them; new files get
the next free id. Transcriptions of images/charts live in
`<name>.transcription.json` (next to the file or in the project's transcriptions
folder) as {"title", "independent_reads", "reads_agree", "cells": [{id, location, text}]}.
A `<stem>.text.json` slide dump is used only when the `.pptx` itself is absent.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path

from .ingest import SUPPORTED, extract, Unit
from .lexicon import canon as normalize  # noqa: F401  (kept for callers of the old name)


@dataclass
class Source:
    id: str
    filename: str
    sha256: str
    kind: str
    title: str


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stem(path: Path) -> str:
    name = path.name
    if name.lower().endswith(".text.json"):
        return name[:-len(".text.json")]
    return path.stem


def _dump_units(sid: str, data: dict) -> list[dict]:
    units = []
    for slide in data["slides"]:
        n, box, tab = slide["slide"], 0, 0
        for shape in slide["shapes"]:
            if shape["kind"] == "text":
                box += 1
                units.append(asdict(Unit(f"{sid}:s{n}:b{box}", sid, f"{sid}:s{n}", f"第{n}页 文本框{box}", shape["text"], "pptx_text")))
            elif shape["kind"] == "table":
                tab += 1
                for r, row in enumerate(shape["rows"], 1):
                    for c, cell in enumerate(row, 1):
                        if cell.strip():
                            units.append(asdict(Unit(f"{sid}:s{n}:t{tab}r{r}c{c}", sid, f"{sid}:s{n}", f"第{n}页 表格{tab} 第{r}行第{c}列", cell, "pptx_table_cell")))
        if slide.get("notes", "").strip():
            units.append(asdict(Unit(f"{sid}:s{n}:notes", sid, f"{sid}:s{n}", f"第{n}页 演讲者备注", slide["notes"], "pptx_notes")))
    return units


def load_sources(folder: Path, manifest: Path | None = None, transcriptions: Path | None = None) -> tuple[list[Source], list[dict]]:
    ids: dict[str, str] = {}
    if manifest and manifest.exists():
        ids = {v: k for k, v in json.loads(manifest.read_text(encoding="utf-8")).items()}
    chosen: dict[str, Path] = {}
    for p in sorted(folder.iterdir()):
        if not p.is_file() or p.name.endswith(".transcription.json"):
            continue
        if p.suffix.lower() not in SUPPORTED and not p.name.lower().endswith(".text.json"):
            continue
        stem = _stem(p)
        if stem in chosen and chosen[stem].suffix.lower() == ".pptx":
            continue
        chosen[stem] = p
    next_no = max([int(x[1:]) for x in ids.values()] + [0]) + 1
    for stem in sorted(chosen):
        if stem not in ids:
            ids[stem] = f"S{next_no:02d}"
            next_no += 1
    if manifest:
        manifest.write_text(json.dumps({v: k for k, v in sorted(ids.items(), key=lambda kv: kv[1])}, ensure_ascii=False, indent=1), encoding="utf-8")

    sources: list[Source] = []
    units: list[dict] = []
    for stem, path in sorted(chosen.items(), key=lambda kv: ids[kv[0]]):
        sid, name = ids[stem], path.name
        if name.lower().endswith(".text.json"):
            sources.append(Source(sid, stem + ".pptx", sha256_file(path), "pptx(text dump)", stem))
            units += _dump_units(sid, json.loads(path.read_text(encoding="utf-8")))
            continue
        pages, us = extract(name, path.read_bytes(), sid)
        title = stem
        tr = path.with_name(name + ".transcription.json")
        if not tr.exists() and transcriptions:
            tr = transcriptions / (name + ".transcription.json")
        if tr.exists():
            t = json.loads(tr.read_text(encoding="utf-8"))
            title = t.get("title", stem)
            agreed = t.get("independent_reads", 1) >= 2 and t.get("reads_agree", False)
            page_id = t.get("page_id") or pages[0].id
            loc = next((p.location for p in pages if p.id == page_id), "")
            for cell in t["cells"]:
                cid = cell["id"]
                us.append(Unit(f"{sid}:{cid}", sid, page_id, (loc + " " if loc and not cell["location"].startswith(loc) else "") + cell["location"],
                               cell["text"], "visual_transcription", needs_confirmation=not agreed))
        sources.append(Source(sid, name, sha256_file(path), path.suffix.lower().lstrip("."), title))
        units += [asdict(u) for u in us]
    return sources, units


def save(sources: list[Source], units: list[dict], out: Path) -> None:
    out.write_text(json.dumps({"sources": [asdict(s) for s in sources], "units": units}, ensure_ascii=False, indent=1), encoding="utf-8")
