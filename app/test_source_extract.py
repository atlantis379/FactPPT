from __future__ import annotations

import io

import pytest
from docx import Document
from fpdf import FPDF
from openpyxl import Workbook

from app.content_contract import EvidenceAssertion, SlideStatement
from app.content_validation import ContentPackage, verify_content_files
from app.source_extract import SourceCapacityError, extract_source


def pdf_bytes(lines: list[str]) -> bytes:
    pdf = FPDF(format=(210, 1000))
    pdf.add_page()
    pdf.set_font("Helvetica", size=9)
    for line in lines:
        pdf.cell(0, 4, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def docx_bytes() -> bytes:
    document = Document()
    for index in range(31):
        document.add_paragraph(f"Observation {index}")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Metric"
    table.cell(0, 1).text = "100 units"
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def xlsx_bytes() -> bytes:
    workbook = Workbook()
    first = workbook.active
    first.title = "Baseline"
    first["B2"] = 100
    next_sheet = workbook.create_sheet("Current")
    next_sheet["C4"] = 120
    next_sheet["D4"] = "=C4+1"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_long_pdf_page_is_not_silently_truncated():
    content = pdf_bytes([f"Record {index:03d} " + "A" * 110 for index in range(120)])
    extraction = extract_source("source.pdf", content)
    assert extraction.status == "COMPLETE"
    assert extraction.units_total == 1
    assert len(extraction.excerpts[0].extracted_text) > 12_000
    assert extraction.excerpts[0].locator.page == 1
    assert extraction.excerpts[0].source_sha256 == extraction.source_sha256


def test_empty_pdf_page_has_visible_coverage_issue():
    pdf = FPDF()
    pdf.add_page()
    content = bytes(pdf.output())
    extraction = extract_source("blank.pdf", content)
    assert extraction.status == "NEEDS_REVIEW"
    assert extraction.issues == ["PDF_PAGE_1_NO_EXTRACTABLE_TEXT"]


def test_pdf_vector_drawing_cannot_be_reported_as_full_text_coverage():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 8, "Visible label")
    pdf.line(20, 20, 100, 20)
    extraction = extract_source("chart.pdf", bytes(pdf.output()))
    assert extraction.status == "NEEDS_REVIEW"
    assert "PDF_PAGE_1_VECTOR_OR_IMAGE_CONTENT_PRESENT" in extraction.issues


def test_word_paragraphs_and_table_cells_keep_native_locations():
    extraction = extract_source("material.docx", docx_bytes())
    assert extraction.status == "COMPLETE"
    assert any(item.extracted_text == "Observation 30" and item.locator.paragraph == 30
               for item in extraction.excerpts)
    assert any(item.extracted_text == "100 units" and item.locator.table == 0
               and item.locator.row == 0 and item.locator.column == 1
               for item in extraction.excerpts)


def test_word_interleaved_table_preserves_source_reading_order():
    document = Document()
    document.add_paragraph("Before table")
    document.add_table(rows=1, cols=1).cell(0, 0).text = "Middle cell"
    document.add_paragraph("After table")
    buffer = io.BytesIO()
    document.save(buffer)
    extraction = extract_source("ordered.docx", buffer.getvalue())
    assert [item.extracted_text for item in extraction.excerpts] == [
        "Before table", "Middle cell", "After table"]
    assert extraction.status == "COMPLETE"


def test_excel_multisheet_and_formula_are_visible():
    extraction = extract_source("numbers.xlsx", xlsx_bytes())
    assert extraction.status == "NEEDS_REVIEW"
    assert any(item.locator.sheet == "Baseline" and item.locator.cell == "B2"
               for item in extraction.excerpts)
    assert any(item.locator.sheet == "Current" and item.locator.cell == "C4"
               for item in extraction.excerpts)
    assert "XLSX_FORMULA_VALUE_UNAVAILABLE:Current!D4" in extraction.issues


def test_capacity_limit_blocks_instead_of_returning_partial_excerpts():
    with pytest.raises(SourceCapacityError, match="extraction-unit limit"):
        extract_source("material.docx", docx_bytes(), max_units=10)
    with pytest.raises(SourceCapacityError, match="byte limit"):
        extract_source("numbers.xlsx", xlsx_bytes(), max_bytes=5)
    with pytest.raises(SourceCapacityError, match="extracted-character limit"):
        extract_source("material.docx", docx_bytes(), max_chars=20)


def test_verified_file_bytes_can_support_exact_word_assertion():
    content = docx_bytes()
    extracted = extract_source("material.docx", content)
    source = next(item for item in extracted.excerpts if item.extracted_text == "Observation 30")
    package = ContentPackage(
        source_excerpts=[source],
        assertions=[EvidenceAssertion(id="a", text=source.quote,
                                      source_excerpt_ids=[source.id])],
        slide_statements=[SlideStatement(id="p", text=source.quote, assertion_ids=["a"])],
    )
    report, extractions = verify_content_files(package, [("material.docx", content)])
    assert report.status == "SUPPORTED"
    assert extractions[0].source_sha256 == source.source_sha256


def test_formula_in_workbook_keeps_extraction_review_visible():
    content = xlsx_bytes()
    extracted = extract_source("numbers.xlsx", content)
    source = next(item for item in extracted.excerpts if item.locator.cell == "B2")
    package = ContentPackage(
        source_excerpts=[source],
        assertions=[EvidenceAssertion(id="a", text=source.quote,
                                      source_excerpt_ids=[source.id])],
    )
    report, _ = verify_content_files(package, [("numbers.xlsx", content)])
    assert report.status == "NEEDS_REVIEW"
    assert report.source_findings[source.id].codes == ["SOURCE_EXTRACTION_INCOMPLETE"]


def test_three_input_formats_share_one_generic_verification_contract():
    pdf_content = pdf_bytes(["Q3 revenue reached 100 units."])
    word_content = docx_bytes()
    workbook = Workbook()
    workbook.active.title = "Sales"
    workbook.active["B2"] = "Revenue 120 units"
    buffer = io.BytesIO()
    workbook.save(buffer)
    excel_content = buffer.getvalue()
    files = [("report.pdf", pdf_content), ("notes.docx", word_content),
             ("sales.xlsx", excel_content)]
    extracted = [extract_source(name, data) for name, data in files]
    sources = [extracted[0].excerpts[0], extracted[1].excerpts[0],
               extracted[2].excerpts[0]]
    assertions = [EvidenceAssertion(id=f"a{index}", text=source.quote,
                                    source_excerpt_ids=[source.id])
                  for index, source in enumerate(sources)]
    slides = [SlideStatement(id=f"p{index}", text=claim.text,
                             assertion_ids=[claim.id])
              for index, claim in enumerate(assertions)]
    report, records = verify_content_files(ContentPackage(
        source_excerpts=sources, assertions=assertions, slide_statements=slides,
    ), files)
    assert report.status == "SUPPORTED"
    assert {record.kind for record in records} == {"PDF", "DOCX", "XLSX"}
