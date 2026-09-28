"""Text extraction keeps what the slide shows: superscripts and subscripts stay in place."""
import io

from factdeck.ingest import extract_all


def pptx_with_scripts() -> bytes:
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[6])
    tf = s.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1)).text_frame
    p = tf.paragraphs[0]
    for text, base in [("正常上限0.5×10", 0), ("9", 30000), ("/L，FEV", 0), ("1", -25000), ("下降", 0), ("1-3", 30000)]:
        r = p.add_run()
        r.text = text
        if base:
            r.font._rPr.set("baseline", str(base))
    tf.add_paragraph().text = "第二段"
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def test_pptx_superscript_and_subscript_are_kept():
    _, units, _ = extract_all("a.pptx", pptx_with_scripts(), "S01")
    assert units[0].text == "正常上限0.5×10⁹/L，FEV₁下降¹⁻³\n第二段"
