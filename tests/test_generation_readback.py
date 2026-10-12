from pathlib import Path

from pptx import Presentation
from pptx.util import Inches
from jinja2 import Environment, FileSystemLoader

from factdeck.render import readback, cover_art, emph_spans, oneline, THEMES


def test_readback_decodes_ooxml_controls_but_preserves_literal_escape_and_detects_omission(tmp_path):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(2))
    box.text = 'Alpha\x01Beta\nLiteral _x0001_'
    out = tmp_path / 'controls.pptx'
    prs.save(out)
    facts = {'control': {'text': 'Alpha\x01Beta'}, 'literal': {'text': 'Literal _x0001_'},
             'missing': {'text': 'Gamma not on slide'}}
    result = readback(out, [list(facts)], facts)
    assert result[0]['missing'] == ['missing']


def test_cover_items_are_present_in_exportable_html():
    env = Environment(loader=FileSystemLoader(Path('factdeck/templates')), autoescape=True)
    env.globals['emph_spans'] = emph_spans
    env.filters['oneline'] = oneline
    page = {'id':'cover', 'layout':'cover', 'title':{'text':'Course'}, 'items':[{'fact':'title'}],
            'art':cover_art(7), 'chrome_meta':'', 'pending_count':0}
    html = env.get_template('deck.html.j2').render(pages=[page], deck={},
        facts={'title':{'id':'title','text':'Source grounded heading','pending':False,'conflict':False}},
        theme=next(iter(THEMES.values())), brand_font='Arial')
    assert 'data-fact="title"' in html and 'Source grounded heading' in html
