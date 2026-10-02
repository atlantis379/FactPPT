"""Native typography preserves locked wording and rejects content edits."""
import copy
import pytest
from factdeck.visual_layout import accept_layout, contract, text_of
from test_visual_generation import model

def styled():
    m=model('01')
    m['texts'][0]['paras'].append([{'text':'仅限符合条件的人群','size':18,'bold':False,'color':{'hex':'151B24','a':1}}])
    result={'design_inspected':True,'objects':[{**{k:s[k] for k in ('id','x','y','w','h')},'font':'Noto Serif SC','line_height':60,'paragraph_styles':[{'size':48,'color':'#355E78'},{'size':32,'bold':True}]} for s in contract(m)['slots']], 'components':[{'name':'装饰','x':0,'y':0,'w':1280,'h':720}], 'differences':[]}
    return m,result

def test_native_and_browser_typography_roundtrip(tmp_path):
    from factdeck.render import build_pptx
    from factdeck.visual_render import document
    from pptx import Presentation
    m,r=styled(); out=accept_layout(m,r)
    assert text_of(out['texts'][0])==text_of(m['texts'][0])
    path=tmp_path/'styled.pptx'; build_pptx([out],{},['source notes'],path)
    slide=Presentation(path).slides[0]
    paras=slide.shapes.title.text_frame.paragraphs
    assert [p.text for p in paras]==['01','仅限符合条件的人群']
    assert all(p.runs[0].font.name=='Noto Serif SC' for p in paras)
    assert paras[0].runs[0].font.color.rgb.__str__()=='355E78'
    assert paras[1].runs[0].font.bold is True
    markup=document([out],[[]],'Microsoft YaHei')
    assert 'font-family:Noto Serif SC' in markup and 'font-size:32px' in markup

@pytest.mark.parametrize('bad',[{'text':'replace qualifier'}, {'font':'a; color:red'}, {'size':True}])
def test_styles_cannot_replace_text_or_inject_css(bad):
    m,r=styled(); r['objects'][0]['paragraph_styles'][0]=bad
    with pytest.raises(ValueError): accept_layout(m,r)

def test_mismatched_paragraph_count_is_rejected():
    m,r=styled(); r['objects'][0]['paragraph_styles'].pop()
    with pytest.raises(ValueError,match='逐段覆盖'): accept_layout(m,r)
