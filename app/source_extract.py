"""Bounded, non-truncating source extraction for v2 content verification."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from typing import Literal

from pydantic import BaseModel

from app.content_contract import SourceExcerpt, SourceLocator


MAX_SOURCE_BYTES = 40 * 1024 * 1024
MAX_SOURCE_UNITS = 100_000
MAX_EXTRACTED_CHARS = 20_000_000
EXTRACTOR_VERSION = "source_extract.v1"


class SourceCapacityError(ValueError):
    """The complete source cannot be processed within a declared limit."""


class SourceExtraction(BaseModel):
    filename: str
    kind: Literal["PDF", "DOCX", "XLSX"]
    extractor_version: str = EXTRACTOR_VERSION
    source_sha256: str
    status: Literal["COMPLETE", "NEEDS_REVIEW"]
    issues: list[str]
    units_total: int
    units_extracted: int
    excerpts: list[SourceExcerpt]


def _kind(filename: str) -> Literal["PDF", "DOCX", "XLSX"]:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    kinds = {"pdf": "PDF", "docx": "DOCX", "xlsx": "XLSX"}
    if extension not in kinds:
        raise ValueError("unsupported source file type; expected PDF, DOCX or XLSX")
    return kinds[extension]


def _source_excerpt(source_sha256: str, locator: SourceLocator, text: str) -> SourceExcerpt:
    position = json.dumps(locator.model_dump(exclude_none=True), sort_keys=True)
    key = hashlib.sha256(f"{source_sha256}:{position}".encode("utf-8")).hexdigest()[:24]
    return SourceExcerpt(id=f"source_{key}", source_sha256=source_sha256,
                         locator=locator, extracted_text=text, quote=text)


def extract_source(filename: str, content: bytes, *,
                   max_bytes: int = MAX_SOURCE_BYTES,
                   max_units: int = MAX_SOURCE_UNITS,
                   max_chars: int = MAX_EXTRACTED_CHARS) -> SourceExtraction:
    """Return all text units or explicitly fail; never slice source text."""
    kind = _kind(filename)
    if len(content) > max_bytes:
        raise SourceCapacityError(f"source exceeds {max_bytes} byte limit")
    source_sha256 = hashlib.sha256(content).hexdigest()
    excerpts: list[SourceExcerpt] = []
    issues: list[str] = []
    units_total = 0
    chars_total = 0

    def add(locator: SourceLocator, value: str):
        nonlocal units_total, chars_total
        units_total += 1
        if units_total > max_units:
            raise SourceCapacityError(f"source exceeds {max_units} extraction-unit limit")
        text = value.strip()
        chars_total += len(text)
        if chars_total > max_chars:
            raise SourceCapacityError(f"source exceeds {max_chars} extracted-character limit")
        if text:
            excerpts.append(_source_excerpt(source_sha256, locator, text))

    if kind == "PDF":
        from pypdf import PdfReader
        from pypdf.generic import ContentStream

        reader = PdfReader(io.BytesIO(content))
        if not reader.pages:
            issues.append("EMPTY_PDF")
        for number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            if not text.strip():
                issues.append(f"PDF_PAGE_{number}_NO_EXTRACTABLE_TEXT")
            resources = page.get("/Resources")
            if resources and resources.get_object().get("/XObject"):
                issues.append(f"PDF_PAGE_{number}_NON_TEXT_OBJECT_PRESENT")
            contents = page.get_contents()
            if contents is not None:
                drawing_ops = {b"S", b"s", b"f", b"F", b"f*", b"B", b"B*",
                               b"b", b"b*", b"sh", b"Do", b"BI"}
                if any(operator in drawing_ops for _operands, operator in
                       ContentStream(contents, reader).operations):
                    issues.append(f"PDF_PAGE_{number}_VECTOR_OR_IMAGE_CONTENT_PRESENT")
            start = len(text) - len(text.lstrip())
            end = start + len(text.strip())
            add(SourceLocator(kind="PDF", page=number,
                              start=start, end=end) if text.strip() else
                SourceLocator(kind="PDF", page=number), text)
    elif kind == "DOCX":
        from docx import Document
        from docx.table import Table

        document = Document(io.BytesIO(content))

        def collect_part(part, part_name: Literal["body", "header", "footer"],
                         section_index: int | None = None):
            paragraph_index = table_index = 0
            for block in part.iter_inner_content():
                if isinstance(block, Table):
                    for row_index, row in enumerate(block.rows):
                        for column_index, cell in enumerate(row.cells):
                            add(SourceLocator(kind="DOCX", part=part_name, section=section_index,
                                              table=table_index, row=row_index,
                                              column=column_index), cell.text)
                            if cell.tables:
                                issues.append(f"DOCX_NESTED_TABLE_NOT_EXTRACTED:{part_name}:{table_index}:{row_index}:{column_index}")
                    table_index += 1
                else:
                    add(SourceLocator(kind="DOCX", part=part_name, section=section_index,
                                      paragraph=paragraph_index), block.text)
                    paragraph_index += 1

        collect_part(document, "body")
        for section_index, section in enumerate(document.sections):
            collect_part(section.header, "header", section_index)
            collect_part(section.footer, "footer", section_index)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if any(name.startswith(("word/media/", "word/embeddings/", "word/charts/"))
                   for name in archive.namelist()):
                issues.append("DOCX_NON_TEXT_OBJECT_PRESENT")
            if any(name.startswith("word/") and name.endswith(".xml") and
                   any(marker in archive.read(name) for marker in
                       (b"txbxContent", b"footnoteReference", b"endnoteReference", b"altChunk"))
                   for name in archive.namelist()):
                issues.append("DOCX_UNEXTRACTED_TEXT_CONTAINER_PRESENT")
        if not excerpts:
            issues.append("DOCX_NO_EXTRACTABLE_TEXT")
    else:
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=False)
        try:
            for sheet in workbook.worksheets:
                for row in sheet.iter_rows():
                    for cell in row:
                        if cell.value is None:
                            continue
                        if cell.data_type == "f":
                            issues.append(f"XLSX_FORMULA_VALUE_UNAVAILABLE:{sheet.title}!{cell.coordinate}")
                        add(SourceLocator(kind="XLSX", sheet=sheet.title,
                                          cell=cell.coordinate), str(cell.value))
        finally:
            workbook.close()
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if any(name.startswith(("xl/media/", "xl/charts/", "xl/drawings/"))
                   for name in archive.namelist()):
                issues.append("XLSX_NON_CELL_OBJECT_PRESENT")
            if any(name.startswith(("xl/comments", "xl/threadedComments/", "xl/externalLinks/"))
                   for name in archive.namelist()):
                issues.append("XLSX_UNEXTRACTED_ANNOTATION_OR_LINK_PRESENT")
        if not excerpts:
            issues.append("XLSX_NO_EXTRACTABLE_CELLS")
    return SourceExtraction(filename=filename, kind=kind, source_sha256=source_sha256,
                            status="NEEDS_REVIEW" if issues else "COMPLETE",
                            issues=issues, units_total=units_total,
                            units_extracted=len(excerpts), excerpts=excerpts)
