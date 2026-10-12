import pytest
from factdeck.render import build_pptx
from factdeck.visual_render import document
from pptx import Presentation
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from tools.visual_lab_native import _table_dimensions


def test_authored_column_widths_are_not_silently_replaced_by_source_proportions():
    table={'rows':[{'h':47,'cells':[{'w':994},{'w':158}]},{'h':75,'cells':[{'w':994},{'w':158}]}]}
    layout={'w':1170,'h':256,'column_widths':[879,291],'row_heights':[82,174]}
    shape={'column_count':2,'row_count':2}
    columns,rows,_,_=_table_dimensions(layout,table,shape)
    assert columns==[879,291] and rows==[82,174]
    layout['col_widths']=[1000,170]
    with pytest.raises(ValueError,match='Conflicting'):_table_dimensions(layout,table,shape)


def test_table_alignment_reaches_office_objects_and_browser(tmp_path):
    cell={'w':300,'fill':None,'border':None,'pad':[8,8,8,8],
          'lineHeight':32,'align':'center','anchor':'middle',
          'paras':[[{'text':'E','size':24,'bold':True,'color':None}]]}
    table={'x':40,'y':40,'w':300,'h':120,'rows':[{'h':120,'cells':[cell]}]}
    model={'shapes':[],'texts':[],'tables':[table],'lines':[],'rasters':[],
           'background':{'hex':'FFFFFF','a':1}}
    path=tmp_path/'alignment.pptx'
    build_pptx([model],{},[''],path)
    native=next(s.table for s in Presentation(path).slides[0].shapes if s.has_table).cell(0,0)
    assert native.vertical_anchor == MSO_ANCHOR.MIDDLE
    assert native.text_frame.paragraphs[0].alignment == PP_ALIGN.CENTER
    html=document([model],[[]],'Microsoft YaHei')
    assert 'text-align:center;vertical-align:middle' in html
