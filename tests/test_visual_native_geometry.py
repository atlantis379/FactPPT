"""Native export must honour A text bounds and schema-ordered table borders."""
from pptx import Presentation
from pptx.oxml.ns import qn
from factdeck.render import build_pptx,PX
from test_visual_table_styles import table_fixture


def test_a_text_bounds_are_exact_and_legacy_default_is_preserved(tmp_path):
    model,_=table_fixture()
    exact=tmp_path/'exact.pptx';legacy=tmp_path/'legacy.pptx'
    build_pptx([model],{},['fixture notes'],exact,strict_text_geometry=True)
    build_pptx([model],{},['fixture notes'],legacy)
    text=lambda p:next(s for s in Presentation(p).slides[0].shapes if s.has_text_frame and s.text.strip())
    assert abs(text(exact).width/PX-model['texts'][0]['w'])<.01
    assert abs(text(legacy).width/PX-(model['texts'][0]['w']*1.03+2))<.01
    assert text(exact).text==text(legacy).text


def test_native_table_border_children_precede_fill_and_do_not_duplicate(tmp_path):
    model,_=table_fixture();path=tmp_path/'table.pptx'
    build_pptx([model],{},['fixture notes'],path,strict_text_geometry=True)
    table=next(s.table for s in Presentation(path).slides[0].shapes if s.has_table)
    for row in table.rows:
        for cell in row.cells:
            props=cell._tc.get_or_add_tcPr();tags=[el.tag for el in props]
            lines=[qn('a:'+side) for side in ('lnL','lnR','lnT','lnB')]
            assert tags[:4]==lines
            assert all(tags.count(tag)==1 for tag in lines)
            assert props.find(qn('a:lnL')).find(qn('a:noFill')) is not None
            assert props.find(qn('a:lnB')).find(qn('a:solidFill')).find(qn('a:srgbClr')).get('val')=='D8E0E8'


def test_serif_ink_overhang_is_allowed_only_for_small_nowrap_text_in_clear_space():
    from factdeck.visual_render import safe_nowrap_ink_overhang
    model,_=table_fixture();text=model['texts'][0]
    text.update(x=40,y=40,w=100,h=50,nowrap=True)
    assert safe_nowrap_ink_overhang(model,text,14)
    assert not safe_nowrap_ink_overhang(model,text,17)
    text['nowrap']=False
    assert not safe_nowrap_ink_overhang(model,text,14)
    text['paras']=[[{'text':'3-10%','size':115,'bold':False,'color':None}]]
    assert safe_nowrap_ink_overhang(model,text,14)
    text['nowrap']=True
    neighbour=dict(text);neighbour.update(x=150,w=50)
    model['texts'].append(neighbour)
    assert not safe_nowrap_ink_overhang(model,text,14)


def test_measured_office_width_headroom_respects_neighbours_and_artwork_container():
    from factdeck.visual_render import clear_font_width_headroom
    model,_=table_fixture();text=model['texts'][0];text.update(x=40,y=40,w=100,h=50)
    assert clear_font_width_headroom(model,text,10)
    assert not clear_font_width_headroom(model,text,17)
    assert not clear_font_width_headroom(model,text,10,[{'x':35,'y':35,'w':108,'h':70}])
    neighbour=dict(text);neighbour.update(x=150,w=50);model['texts'].append(neighbour)
    assert not clear_font_width_headroom(model,text,15)
