"""Protocol fixtures only: these files are not actual template deliverables."""
import copy
import json
from pathlib import Path
import pytest
from app import academic_templates as templates
from app.deckflow import Store, WorkflowError, render_input
from app.fact57098 import sha
from test_deckflow import to_deck
from test_visual_generation import flow
from factdeck.native_vectors import trace_svg


def library(tmp_path,monkeypatch,ready=True):
    monkeypatch.setattr(templates,'LIBRARY',tmp_path/'library')
    folder=templates.LIBRARY/'01_journal';folder.mkdir(parents=True)
    (folder/'design.png').write_bytes(b'TEST_DESIGN_NOT_REAL_IMAGE')
    for name in ('deck.pptx','deck.pdf','template.potx'):(folder/name).write_bytes(b'TEST_ONLY')
    (folder/'native_report.json').write_text(json.dumps({'image_objects':0,'pages':6}))
    checks=[{'contour_edit':True,'fill_recolor':True,'group_move':True} for _ in range(6)]
    (folder/'office_report.json').write_text(json.dumps({'editability':checks}))
    (folder/'qa.json').write_text(json.dumps({'text_free':True,'final_inspected':ready}))
    return folder


def test_uninspected_template_cannot_be_selected(tmp_path,monkeypatch):
    library(tmp_path,monkeypatch,False);store=Store(tmp_path/'data');w=store.create('TEST ONLY')
    assert not templates.list_templates()[0]['ready']
    with pytest.raises(WorkflowError):templates.asset('01_journal','deck.pptx')
    with pytest.raises(WorkflowError):store.settings(w['id'],{'visual_template':'01_journal'})
    assert store.get(w['id']).get('visual_template') is None
    with pytest.raises(WorkflowError):templates.asset('01_journal','../qa.json')


def test_selection_is_immutable_and_only_changes_visual_input(tmp_path,monkeypatch):
    folder=library(tmp_path,monkeypatch);store=Store(tmp_path/'data');w=to_deck(store)
    before=render_input(w,include_visual=False)
    chosen=store.settings(w['id'],{'visual_template':'01_journal'})
    assert chosen['summary']==w['summary'] and chosen['facts']==w['facts'] and chosen['deck']==w['deck']
    assert chosen['content_approval']==w['content_approval']
    assert render_input(chosen,include_visual=False)!=before
    snap=chosen['visual_template'];assert snap['design_sha256']==sha(b'TEST_DESIGN_NOT_REAL_IMAGE')
    (folder/'design.png').write_bytes(b'CHANGED_LIBRARY')
    assert store.path(snap['design_path']).read_bytes()==b'TEST_DESIGN_NOT_REAL_IMAGE'
    cleared=store.settings(w['id'],{'visual_template':None})
    assert render_input(cleared,include_visual=False)==before


def test_generation_binds_actual_template_and_palette(flow,tmp_path,monkeypatch):
    store,w=flow;library(tmp_path,monkeypatch)
    w=store.settings(w['id'],{'visual_template':'01_journal'})
    w=store.start_generation(w['id'])
    task=store.claim(w['id'],'TEST_ONLY','VISUAL_DESIGN');brief=task['brief']
    assert brief['assets']['academic_template']['sha256']==w['visual_template']['design_sha256']
    assert brief['receipt_contract']['input_assets']['academic_template']==w['visual_template']['design_sha256']
    assert '医学期刊风' in brief['prompt'] and '占位文字不作为事实' in brief['prompt']
    assert w['generation']['palette']['primary']=='#355E78'


def test_contact_size_is_opt_in_and_order_preserved():
    svg=b'<svg width="600" height="200"><path fill="#112244" d="M0 0L100 0L100 100Z"/><path fill="#224466" d="M5 5L105 5L105 105Z"/><path fill="#112244" d="M10 10L110 10L110 110Z"/></svg>'
    with pytest.raises(ValueError):trace_svg(svg)
    vectors,report=trace_svg(svg,preserve_order=True,target_size=(600,200))
    assert len(vectors)==3 and vectors[0]['fill']==vectors[2]['fill']!=vectors[1]['fill']
    assert vectors[-1]['commands'][0][1:]==[10,10]
