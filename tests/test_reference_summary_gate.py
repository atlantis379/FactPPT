"""An approved reference allocation may contain substantive pages without teaching points.
Synthetic protocol fixture; no medical judgement or real approval is represented.
"""
import copy
import pytest
import app.deckflow as d


@pytest.fixture
def gate_case(monkeypatch):
    store=d.Store.__new__(d.Store)
    store.source_integrity=lambda w:None
    store.snapshot=lambda *args:None
    monkeypatch.setattr(d,'fully_claimed',lambda w:True)
    monkeypatch.setattr(d,'input_hash',lambda w:'TEST')
    monkeypatch.setattr(d,'all_units',lambda w:[])
    monkeypatch.setattr(d,'pages',lambda w:{p:{'reading':{'classification':'SUBSTANTIVE'}} for p in ['P1','P2']})
    monkeypatch.setattr(d,'structured',lambda w:False)
    monkeypatch.setattr(d,'cite',lambda *args:None)
    monkeypatch.setattr(d.Store,'_message',staticmethod(lambda *args:None))
    monkeypatch.setattr(d.structure_stage,'approved',lambda w:bool(w.get('structure_approval')))
    w={'structure_first':True,'structure_approval':{'TEST_ONLY':True},'outline':[{'id':'o1'}],
       'structure':{'result':{'sections':[{'id':'a1','core':{'claim_id':'C1'},'source_page_ids':['P1']}],
                              'reference_only':[{'source_page_ids':['P2']}]}}}
    r={'schema_version':'full_source_summary.v3','input_sha256':'TEST',
       'overall_summary':'TEST synthetic summary explains source allocation and preserves the human review gate.',
       'sections':[{'id':'a1','title':'Teaching','summary':'TEST synthetic teaching summary with sufficient length.',
                    'source_page_ids':['P1'],'key_points':[{'point':'TEST point','claim_ids':['C1']}],
                    'message':{'core':{'claim_id':'C1'}}},
                   {'id':'ref','title':'Reference','summary':'TEST substantive reference page allocated by the approved structure.',
                    'source_page_ids':['P2'],'key_points':[]}],
       'outline_coverage':[{'outline_id':'o1','section_ids':['a1','ref']}],'pending_issues':[]}
    return store,w,r


def test_approved_substantive_reference_does_not_require_invented_core(gate_case):
    store,w,r=gate_case
    store.accept_summary(w,copy.deepcopy(r),'TEST_AUTHOR')
    assert w['summary']['sections'][-1]['key_points']==[]


def test_unapproved_reference_allocation_still_requires_teaching_points(gate_case):
    store,w,r=gate_case;w['structure_approval']=None
    with pytest.raises(d.WorkflowError,match='关键依据'):
        store.accept_summary(w,r,'TEST_AUTHOR')


def test_teaching_section_cannot_hide_its_points_as_reference(gate_case):
    store,w,r=gate_case;r['sections'][0]['key_points']=[]
    with pytest.raises(d.WorkflowError,match='关键依据'):
        store.accept_summary(w,r,'TEST_AUTHOR')


def test_reference_page_cannot_be_given_teaching_points_without_reallocation(gate_case):
    store,w,r=gate_case;r['sections'][1]['key_points']=[{'point':'TEST new teaching point','claim_ids':['C2']}]
    with pytest.raises(d.WorkflowError,match='参考'):
        store.accept_summary(w,r,'TEST_AUTHOR')
