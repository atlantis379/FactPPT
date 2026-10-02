"""Real browser regression: table auto-growth must block native export."""
from playwright.sync_api import sync_playwright

from factdeck.visual_layout import accept_layout
from factdeck.visual_render import LAYOUT_CHECK_JS, document, fit_text_lineboxes
from test_visual_table_styles import table_fixture


def measure(model):
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        page=browser.new_page(viewport={'width':1280,'height':720})
        page.set_content(document([model],[[]],'Microsoft YaHei'))
        page.evaluate('document.fonts.ready')
        result=page.locator('#slide1').evaluate(LAYOUT_CHECK_JS)
        browser.close()
        return result


def test_large_table_font_uses_matching_parent_metrics_and_preserves_box():
    model,result=table_fixture()
    result['objects'][1].update(h=210,font='Noto Serif SC',size=20,line_height=26,
                                col_widths=[280,480],row_heights=[50,80,80])
    edited=accept_layout(model,result)
    checks=measure(edited)
    assert checks['overflow']==[] and checks['overlap']==[]
    assert abs(checks['table_dimensions'][0]['height']-210)<=1.5


def test_table_auto_growth_and_footer_intersection_are_detected():
    model,result=table_fixture()
    result['objects'][1].update(font='Noto Serif SC',size=24,line_height=32)
    edited=accept_layout(model,result)
    footer=dict(edited['texts'][0]); footer.update(y=291,h=30)
    edited['texts'].append(footer)
    checks=measure(edited)
    assert any('exceeds locked' in issue for issue in checks['overflow'])
    assert checks['overlap']


def test_text_metric_adjustment_must_not_expand_into_a_table():
    model,_=table_fixture()
    model['texts'][0].update(y=70,h=50)
    assert fit_text_lineboxes(model,[{'scroll_h':66,'client_h':50,'scroll_w':800,'client_w':800}])==[]
    assert model['texts'][0]['h']==50
