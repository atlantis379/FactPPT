from factdeck import free
from factdeck.deck import _structure

FIG = {"figure": "箭头把两步连起来"}


def page(html, css="", design=FIG):
    return {"id": "p", "layout": "free", "title": {"text": "主题"}, "html": html, "css": css, "design": design}


OK = ('<div data-shape data-t id="a" style="position:absolute;left:0;top:0;width:300px;background:var(--sky)">'
      '<span data-fact="f1"></span></div>'
      '<div data-t id="b" style="position:absolute;left:400px;top:0;width:300px"><span data-text>结果</span>'
      '<b><span data-fact="f2"></span></b></div>'
      '<svg data-edges style="position:absolute;left:0;top:0;width:1152px;height:100px">'
      '<polyline points="300,20 400,20" data-from="a" data-to="b" data-backed="s"/></svg>')


def test_a_well_formed_free_page_passes_and_reads_as_blocks():
    assert free.structure_errors(page(OK)) == []
    assert _structure(page(OK)) == []
    kinds = [(b["kind"], b.get("refs") or b.get("backed_by")) for b in free.view(page(OK))]
    assert kinds == [("text", [{"fact": "f1"}]), ("text", [{"text": "结果"}, {"fact": "f2"}]), ("arrow", "s")]


def test_loose_text_and_typed_facts_are_refused():
    assert any("span" in e for e in free.structure_errors(page('<div data-t>自己写的字</div>')))
    assert any("留空" in e for e in free.structure_errors(page('<div data-t><span data-fact="f1">改写</span></div>')))
    assert any("data-t" in e for e in free.structure_errors(page('<div><span data-fact="f1"></span></div>')))


def test_styles_powerpoint_cannot_show_are_refused():
    for style in ("box-shadow:0 2px 4px #000", "transform:rotate(3deg)", "opacity:.5", "background:linear-gradient(red,blue)",
                  "font-family:Arial", "--x:1"):
        html = f'<div data-t style="{style}"><span data-fact="f1"></span></div>'
        assert free.structure_errors(page(html)), style
    assert free.structure_errors(page('<div data-t class="x"><span data-fact="f1"></span></div>', css=".x{filter:blur(2px)}"))
    assert free.structure_errors(page('<div data-t><span data-fact="f1"></span></div>', css="@media print{.x{color:red}}"))
    assert free.structure_errors(page('<div data-t onclick="x()"><span data-fact="f1"></span></div>'))
    assert free.structure_errors(page('<script>x()</script>'))


def test_drawings_follow_the_drawing_principle():
    line = ('<div data-t><span data-fact="f1"></span></div><svg data-edges style="width:10px;height:10px">'
            '<polyline points="0,0 9,9"/></svg>')
    assert any("data-encodes" in e for e in free.structure_errors(page(line)))
    assert any("design.figure" in e for e in free.structure_errors(page(OK, design={})))
    unbacked = OK.replace(' data-backed="s"', '')
    assert any("data-backed" in e for e in free.structure_errors(page(unbacked)))


def test_render_fills_facts_and_scopes_css():
    fview = {"f1": {"text": "第一<句>", "pending": False}, "f2": {"text": "第二句", "pending": True}}
    html, css = free.render(page(OK, css=".x, .y > b{color:var(--accent)}"), fview, {}, lambda t, e: [(t, False)])
    assert 'data-fact="f1" class="f">第一&lt;句&gt;</span>' in html
    assert 'data-mark="pending"' in html and "data-authored" in html and "marker-end" in html
    assert css == "#p .body .x,#p .body .y > b{color:var(--accent)}"


def test_bars_are_proportional_on_their_scale():
    drawn = [{"fact": "a", "scale": "s", "length": 200}, {"fact": "b", "scale": "s", "length": 100}]
    assert free.bar_errors({}, {"a": 40, "b": 20}, drawn) == []
    assert free.bar_errors({}, {"a": 40, "b": 30}, drawn)
