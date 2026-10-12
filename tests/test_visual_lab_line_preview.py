import pytest
from factdeck.visual_render import document


@pytest.mark.parametrize('flag,expected',[(False,False),(True,True),(None,True)])
def test_browser_relation_preview_honors_native_arrow_flag(flag,expected):
    line={'points':[[1,2],[3,4]],'color':'123456','w':2}
    if flag is not None:line['arrow']=flag
    model={'shapes':[],'texts':[],'tables':[],'lines':[line],'background':{'hex':'FFFFFF','a':1}}
    result=document([model],[[]],'Microsoft YaHei')
    assert ('marker-end=' in result)==expected
