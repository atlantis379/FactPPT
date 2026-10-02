"""Concurrency and stale-lease checks use fictional protocol fixtures."""
import copy
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_visual_generation import flow, complete_one
from app.deckflow import WorkflowError


def test_parallel_workers_claim_only_their_page_and_do_not_duplicate(flow):
    store,w=flow;wid=w['id'];w=complete_one(store,wid,'VISUAL_DESIGN')
    ids=[p['id'] for p in w['generation']['pages']]
    tasks=[('A','VISUAL_LAYOUT',ids[0]),('B','VISUAL_DESIGN',ids[1]),('C','VISUAL_DESIGN',ids[1])]
    with ThreadPoolExecutor(3) as pool:
        claimed=list(pool.map(lambda a:store.claim(wid,*a),tasks))
    assert claimed[0]['binding']==ids[0]
    others=[t for t in claimed[1:] if t]
    assert len(others)==1 and others[0]['binding']==ids[1]
    assert store.claim(wid,'D','VISUAL_DESIGN','absent-page') is None


def test_expired_handoff_rejects_old_token_and_preserves_page_contract(flow):
    store,w=flow;wid=w['id'];t=store.claim(wid,'A','VISUAL_DESIGN')
    with store.transaction(wid,'TEST_EXPIRE') as state:
        next(x for x in state['tasks'] if x['id']==t['id'])['lease_until']=0
    newer=store.claim(wid,'B','VISUAL_DESIGN',t['binding'])
    assert newer['input_sha256']==t['input_sha256']
    with pytest.raises(WorkflowError,match='租约'):
        store.renew(wid,t['id'],t['lease_token'])
    assert store.renew(wid,newer['id'],newer['lease_token'])['lease_until']>0


def test_compact_ack_does_not_return_source_content_or_lease():
    from app.deckflow_api import completion_ack
    w={'id':'fixture','stage':'GENERATION_RUNNING','sources':[{'private':'fixture'}],
       'generation':{'render':{'status':'WAITING_ASSETS'}},
       'tasks':[{'id':'task','status':'COMPLETE','result_sha256':'sha','lease_token':'fixture-secret'}]}
    result=completion_ack(w,'task')
    assert result['task_id']=='task' and result['status']=='COMPLETE'
    assert 'sources' not in result and 'lease_token' not in str(result)


def test_tool_capacity_and_ownership(tmp_path,monkeypatch):
    from tools import visual_worker_runtime as rt
    monkeypatch.setattr(rt,'RUNTIME',tmp_path)
    with ThreadPoolExecutor(3) as pool:
        locks=list(pool.map(lambda i:rt.acquire('adobe',str(i),str(i)),range(3)))
    assert len([x for x in locks if x])==2
    lock=next(x for x in locks if x)
    wrong=copy.deepcopy(lock);wrong['owner']='wrong'
    rt.release(wrong)
    assert rt.acquire('adobe','D','D') is None
    rt.release(lock)
    assert rt.acquire('adobe','D','D') is not None


def test_reused_archived_receipt_is_not_a_second_tool_call(flow):
    from app.deck_generation import view
    store,w=flow;w=complete_one(store,w['id'],'VISUAL_DESIGN')
    before=view(w)['cost']['accepted_tool_calls']
    page=w['generation']['pages'][0]
    page['history']=[{'assets':copy.deepcopy(page['assets'])}]
    assert view(w)['cost']['accepted_tool_calls']==before
