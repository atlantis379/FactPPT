"""Local workbench integration; all content and approvals are test fixtures."""
import copy
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import deckflow_api as api
from app.deckflow import Store
from test_deckflow import to_deck


def client_for(tmp_path, monkeypatch):
    store=Store(tmp_path/'data')
    monkeypatch.setattr(api,'store',store)
    app=FastAPI();app.include_router(api.router)
    return store,TestClient(app)


def test_progress_does_not_expose_evidence_or_mutate_workflow(tmp_path, monkeypatch):
    store,client=client_for(tmp_path,monkeypatch)
    w=store.create('测试项目','')
    before=store.get(w['id'])
    response=client.get(f"/api/deck/workflows/{w['id']}/progress")
    assert response.status_code==200
    assert set(response.json())=={'id','stage','updated_at','tasks'}
    assert store.get(w['id'])==before
    assert client.get('/api/deck/workflows/not-found/progress').status_code==404
    health=client.get('/api/deck/health').json()
    assert set(health['theme_palettes'])==set(health['themes'])


def test_ui_summary_edit_requires_new_independent_review_and_blocks_delivery(tmp_path, monkeypatch):
    store,client=client_for(tmp_path,monkeypatch)
    w=to_deck(store)
    old_approval=copy.deepcopy(w['content_approval'])
    result=copy.deepcopy(w['summary'])
    result['overall_summary']+='这是程序测试中的修订说明。'
    response=client.put(f"/api/deck/workflows/{w['id']}/summary",json={'operator':'TEST-EDITOR','result':result})
    assert response.status_code==200
    changed=response.json()
    assert changed['stage']=='SUMMARY_REVIEW_REQUIRED'
    assert changed['summary_meta']['author']=='operator:TEST-EDITOR'
    assert changed['content_approval'] is None
    assert changed['approval_subjects']['content']!=old_approval['subject_sha256']
    assert client.post(f"/api/deck/workflows/{w['id']}/export").status_code==409
    queued=client.post(f"/api/deck/workflows/{w['id']}/tasks",json={'kind':'SUMMARY_REVIEW'})
    assert queued.status_code==200
    progress=client.get(f"/api/deck/workflows/{w['id']}/progress").json()
    assert any(t['status']=='PENDING' for t in progress['tasks'])


def test_pending_answers_are_version_bound_and_do_not_approve_or_resolve(tmp_path, monkeypatch):
    store,client=client_for(tmp_path,monkeypatch)
    w=to_deck(store)
    summary=copy.deepcopy(w['summary'])
    summary['pending_issues']=['来源待核对','完整性待核对']
    w=client.put(f"/api/deck/workflows/{w['id']}/summary",json={'operator':'TEST-EDITOR','result':summary}).json()
    path=f"/api/deck/workflows/{w['id']}/summary/pending-responses"
    body={'operator':'TEST-HUMAN','subject_sha256':w['approval_subjects']['content'],
          'answers':[{'index':0,'answer':'UNAVAILABLE','note':''},{'index':1,'answer':'UNKNOWN','note':''}]}
    assert client.post(path,json={**body,'subject_sha256':'old'}).status_code==409
    assert client.post(path,json={**body,'answers':body['answers'][:1]}).status_code==422
    response=client.post(path,json=body)
    assert response.status_code==200
    saved=response.json()
    assert saved['summary']==w['summary']
    assert saved['content_approval'] is None
    assert saved['stage']=='SUMMARY_AMEND_RUNNING'
    assert saved['summary_pending_responses']['answers'][0]['issue']=='来源待核对'
    assert saved['summary_pending_responses']['operator']=='TEST-HUMAN'
    tasks=[t for t in saved['tasks'] if t['kind']=='SUMMARY_AMEND' and t['status']=='PENDING']
    assert len(tasks)==1
    assert tasks[0]['brief']['mode']=='pending_responses_only'
    again=client.post(path,json=body).json()
    assert len([t for t in again['tasks'] if t['kind']=='SUMMARY_AMEND'])==1
    assert client.post(f"/api/deck/workflows/{w['id']}/approvals/content",json={
        'customer':'TEST-HUMAN','operator':'TEST-HUMAN','method':'本机记录','subject_sha256':body['subject_sha256']}).status_code==409
    task=client.post(f"/api/deck/workflows/{w['id']}/tasks/claim",json={'worker':'TEST-AMENDER','kind':'SUMMARY_AMEND'}).json()
    complete_path=f"/api/deck/workflows/{w['id']}/tasks/{task['id']}/complete"
    changed=copy.deepcopy(summary)
    changed['sections'][0]['key_points'][0]['point']='篡改临床要点'
    assert client.post(complete_path,json={'lease_token':task['lease_token'],'result':changed}).status_code==422
    changed=copy.deepcopy(summary)
    changed['pending_issues']=[]
    assert client.post(complete_path,json={'lease_token':task['lease_token'],'result':changed}).status_code==422
    changed['pending_issues']=['完整性待核对']
    changed['overall_summary']+='；人工答复：来源资料目前不可提供。'
    completed=client.post(complete_path,json={'lease_token':task['lease_token'],'result':changed})
    assert completed.status_code==200
    final=completed.json()
    assert final['stage']=='SUMMARY_REVIEW_REQUIRED'
    assert final['content_approval'] is None
    assert any(t['kind']=='SUMMARY_REVIEW' and t['status']=='PENDING' for t in final['tasks'])
