"""Native table styles may change; invented fixture evidence cannot change."""
import copy

import pytest

from factdeck.visual_layout import accept_layout, contract, text_of
from test_visual_generation import model


def table_fixture():
    m=model('锁定表格测试')
    m['texts'][0]['h']=50
    cells=[['项目','限定条件'],['项目甲','≥12岁\n仅限符合条件的人群'],['项目乙','≤300 cells/μL；并非全部患者']]
    rows=[]
    for ri,row in enumerate(cells):
        items=[]
        for ci,text in enumerate(row):
            items.append({'w':[220,540][ci], 'fill':{'hex':'3E6278' if ri==0 else 'F6F4EF','a':1},
                          'border':{'hex':'D8E0E8','a':1},'pad':[6,12,6,12], 'lineHeight':20,
                          'paras':[[{'text':para,'size':14,'bold':ri==0,'color':{'hex':'FFFFFF' if ri==0 else '151B24','a':1}}] for para in text.split('\n')]})
        rows.append({'h':[40,60,60][ri],'cells':items})
    m['tables']=[{'x':40,'y':130,'w':760,'h':160,'rows':rows}]
    result={'design_inspected':True,
            'objects':[{k:s[k] for k in ('id','x','y','w','h')} for s in contract(m)['slots']],
            'components':[{'name':'decorative artwork','x':850,'y':100,'w':350,'h':450}], 'differences':[]}
    return m,result


def test_table_style_native_roundtrip_preserves_cells_and_format(tmp_path):
    from factdeck.render import PX, build_pptx
    from factdeck.visual_render import document
    from pptx import Presentation
    m,result=table_fixture(); before=copy.deepcopy(m)
    result['objects'][1].update(font='Noto Serif SC',size=20,line_height=26,
                                col_widths=[280,480],row_heights=[42,59,59])
    out=accept_layout(m,result)
    assert m==before  # edits never mutate the source lock
    wanted=[[text_of(c) for c in r['cells']] for r in m['tables'][0]['rows']]
    assert [[text_of(c) for c in r['cells']] for r in out['tables'][0]['rows']]==wanted
    for original,edited in zip(m['tables'][0]['rows'],out['tables'][0]['rows']):
        for a,b in zip(original['cells'],edited['cells']):
            assert b['fill']==a['fill'] and b['border']==a['border'] and b['pad']==a['pad']
            assert [r['bold'] for p in b['paras'] for r in p]==[r['bold'] for p in a['paras'] for r in p]
    path=tmp_path/'table.pptx'; build_pptx([out],{},['fixture source notes'],path)
    slide=Presentation(path).slides[0]
    table=next(s.table for s in slide.shapes if s.has_table)
    assert [[c.text for c in r.cells] for r in table.rows]==wanted
    assert [round(c.width/PX,2) for c in table.columns]==[280,480]
    assert [round(r.height/PX,2) for r in table.rows]==[42,59,59]
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.text_frame.paragraphs:
                assert all(r.font.name=='Noto Serif SC' and r.font.size.pt==15 for r in paragraph.runs)
    assert slide.notes_slide.notes_text_frame.text=='fixture source notes'
    markup=document([out],[[]],'Microsoft YaHei')
    assert 'font-family:Noto Serif SC' in markup and 'font-size:20px' in markup


@pytest.mark.parametrize('bad',[
    {'cells':[['replacement']]}, {'paras':[['replacement']]}, {'rows':[]}, {'text':'replacement'},
    {'col_widths':[760]}, {'col_widths':[280,480,1]}, {'col_widths':[280,479]},
    {'col_widths':[True,759]}, {'col_widths':[float('nan'),480]}, {'col_widths':[0,760]},
    {'col_widths':None}, {'row_heights':[80,80]}, {'row_heights':[42,59,58]},
    {'row_heights':[42,float('inf'),59]}, {'row_heights':[-1,80,81]},
    {'font':'x; color:red'}, {'size':True}, {'size':float('inf')}, {'size':10},
    {'line_height':False}, {'line_height':221}, {'color':'#000000'},
    {'bold':True}, {'paragraph_styles':[]}, {'unknown':'new value'},
])
def test_table_rejects_content_changes_and_invalid_geometry(bad):
    m,result=table_fixture(); result['objects'][1].update(bad)
    with pytest.raises(ValueError): accept_layout(m,result)


def test_old_table_geometry_behavior_and_styles_stay_compatible():
    m,result=table_fixture(); result['objects'][1].update(w=1140,h=240)
    out=accept_layout(m,result)['tables'][0]
    assert [r['h'] for r in out['rows']]==[60,90,90]
    assert [c['w'] for c in out['rows'][0]['cells']]==[330,810]
    assert out['rows'][1]['cells'][0]['paras']==m['tables'][0]['rows'][1]['cells'][0]['paras']


def test_table_dimensions_cannot_be_applied_to_text():
    m,result=table_fixture(); result['objects'][0]['col_widths']=[800]
    with pytest.raises(ValueError,match='只适用于表格'): accept_layout(m,result)
