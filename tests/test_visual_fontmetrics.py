from factdeck.visual_render import fit_text_lineboxes
from test_visual_generation import model
from factdeck.visual_layout import text_of

def test_measured_height_preserves_wording_and_size_with_strict_limits():
    m=model('≥12岁；仅限符合条件的人群'); t=m['texts'][0]; t.update(y=40,h=50)
    before=text_of(t); size=t['paras'][0][0]['size']
    change=fit_text_lineboxes(m,[{'scroll_h':62,'client_h':50,'scroll_w':800,'client_w':800}])
    assert change and t['h']==62 and text_of(t)==before and t['paras'][0][0]['size']==size
    assert not fit_text_lineboxes(m,[{'scroll_h':100,'client_h':62,'scroll_w':800,'client_w':800}])
    other=model('来源')['texts'][0]; other.update(y=103,h=20); m['texts'].append(other)
    assert not fit_text_lineboxes(m,[{'scroll_h':110,'client_h':100,'scroll_w':800,'client_w':800}])
    assert t['h']==62
