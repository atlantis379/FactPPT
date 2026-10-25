"""Protocol fixtures are invented. They do not constitute real tool calls or approvals."""
import copy
import io
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image

from app.deckflow import Store, WorkflowError, checked, verified, render_current
from app.deck_generation import VISUAL_KINDS, view, ready
from factdeck.visual_layout import accept_layout, contract
from factdeck.native_vectors import trace_svg
from test_deckflow import to_deck, finish_gates

SVG=b'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"><path d="M900 80L1180 80L1180 500L900 500Z" fill="#355E78"/></svg>'


def png():
    b=io.BytesIO(); Image.new("RGB",(1280,720),"#f6f4ef").save(b,format="PNG"); return b.getvalue()


def model(text):
    return {"background":{"hex":"F6F4EF","a":1},"rasters":[],"shapes":[],"lines":[],"figures":[],"tables":[],
            "texts":[{"x":40,"y":40,"w":800,"h":600,"lineHeight":24,"align":"left","anchor":"top","nowrap":False,"role":"title",
                      "paras":[[{"text":text,"size":18,"bold":False,"color":{"hex":"151B24","a":1}}]]}]}


@pytest.fixture
def flow(tmp_path,monkeypatch):
    store=Store(tmp_path/"data"); w=finish_gates(store,to_deck(store))
    def prepare(deck,facts,sources,out,*args,**kwargs):
        out.mkdir(parents=True,exist_ok=True)
        models=[model(str(p["title"])+"\n"+"\n".join(facts[f]["display"] or facts[f]["quote"] for f in r["facts"])) for p,r in zip(deck["pages"],checked(w)["pages"])]
        (out/"native_model.json").write_text(json.dumps({"models":models,"notes":["fixture source notes"]*len(models),"font":"Microsoft YaHei"}),encoding="utf8")
    monkeypatch.setattr("factdeck.render.render",prepare)
    return store,store.start_generation(w["id"])


def fixture_plan(contract):
    """An invented plan that satisfies visual-grammar.5 for any fixture page: one entity unit on the focus
    passage (or the first passage), other passages with detected relation words left out as duplicates."""
    g=contract["grammar"]; passages=[x["text"] for x in g["passages"]]
    main=next((x["text"] for x in g["passages"] if x["focus"]),passages[0])
    term="".join(main.split())[:4]
    plan={"units":[{"text":main,"relation":{"type":"entity","span":""},"terms":[{"span":term,"role":"TEST"}],
                    "draw":[{"object":term+" TEST fixture drawing","bound_to":term,"derivation":""}],"encoding":""}],
          "omitted":[{"text":x["text"],"reason":"duplicate"} for x in g["passages"] if x["candidates"] and x["text"]!=main],"arrangement":"TEST"}
    return plan


def complete_one(store,wid,kind):
    if kind=="VISUAL_BLIND_READ":     # an independent identity reads the text-free image (invented fixture reading)
        t=store.claim(wid,"TEST_FIXTURE_BLIND_READER",kind)
        if not t: return store.get(wid)
        page=next(p for p in store.get(wid)["generation"]["pages"] if p["id"]==t["binding"])
        plan=page["assets"]["design"]["receipt"]["qa"]["illustration_plan"]
        result={"input_sha256":t["input_sha256"],"inspected":True,
                "objects":[{"description":"TEST","bound_to":term["span"]} for u in plan["units"] for term in u["terms"]],
                "relations":[{"type":u["relation"]["type"],"spans":[u["text"]]} for u in plan["units"]]}
        return store.complete(wid,t["id"],t["lease_token"],result)
    t=store.claim(wid,"TEST_FIXTURE_ONLY",kind); assert t
    if kind=="VISUAL_LAYOUT":
        result=copy.deepcopy(t["brief"]["result_contract"]); result["design_inspected"]=True
        return store.complete(wid,t["id"],t["lease_token"],result)
    data=SVG if kind=="VISUAL_VECTOR" else png()
    from app.fact57098 import sha
    receipt=copy.deepcopy(t["brief"]["receipt_contract"])
    receipt.update(tool_call_id="TEST_FIXTURE_NOT_A_REAL_CALL_"+t["id"],asset_sha256=sha(data),elapsed_seconds=1)
    receipt["qa"]={k:True for k in receipt["qa"]}
    if t["brief"].get("illustration_plan_contract"):   # content-page design: invented fixture plan
        from app.deck_generation import plan_prompt
        plan=fixture_plan(t["brief"]["illustration_plan_contract"])
        receipt["qa"]["illustration_plan"]=plan; receipt["prompt"]=plan_prompt(t["brief"]["prompt"],plan)
    return store.visual_asset(wid,t["id"],t["lease_token"],data,receipt)


def test_default_route_and_original_gates(tmp_path):
    store=Store(tmp_path/"data"); w=store.create("New")
    assert w["generation_route"]=="TEMPLATE_LIB"      # route A stopped 2026-10-25 (AGENTS.md 决策记录)
    assert store.create("A",generation_route="A_NATIVE_VECTOR")["generation_route"]=="A_NATIVE_VECTOR"
    with pytest.raises(WorkflowError,match="页面规格"): store.start_generation(w["id"])
    assert not store.get(w["id"])["generation"]


def test_clean_prompt_preserves_non_table_cards_and_only_removes_actual_tables(flow):
    store,w=flow;wid=w['id']
    w=complete_one(store,wid,'VISUAL_DESIGN')
    w=complete_one(store,wid,'VISUAL_LAYOUT')
    t=store.claim(wid,'TEST_FIXTURE_ONLY','VISUAL_CLEAN')
    prompt=t['brief']['prompt']
    assert '卡片容器不是表格，禁止删除卡片' in prompt
    assert '彻底删除整块表格' not in prompt
    assert t['brief']['receipt_contract']['prompt']==prompt
    from test_visual_table_styles import table_fixture
    altered=copy.deepcopy(w)
    altered['generation']['pages'][0]['layout']['model']['tables']=table_fixture()[0]['tables']
    prompt=store.generation_brief(altered,'VISUAL_CLEAN',t['binding'])['prompt']
    assert '彻底删除整块表格' in prompt and '仅保留非表格的装饰色块' in prompt
    assert '禁止删除卡片' not in prompt
    assert '只保留大片底色、表头色块和最外侧边框' not in prompt


def test_chain_is_automatic_and_claims_are_serialized(flow):
    store,w=flow; wid=w["id"]
    assert len([t for t in w["tasks"] if t["kind"] in VISUAL_KINDS])==1  # first design fixes suite style
    with ThreadPoolExecutor(2) as pool:
        claimed=list(pool.map(lambda _:store.claim(wid,"fixture","VISUAL_DESIGN"),range(2)))
    assert sum(t is not None for t in claimed)==1
    t=next(t for t in claimed if t); store.fail(wid,t["id"],t["lease_token"],"fixture retry")
    for _ in w["deck"]["result"]["pages"]:
        for kind in VISUAL_KINDS: w=complete_one(store,wid,kind)
    assert ready(w) and w["generation"]["render"]["status"]=="PENDING"
    assert w["generation_status"]["cost"]["accepted_tool_calls"]==3*len(w["generation"]["pages"])
    assert not w["render"] and not w["style_approval"] and not w["page_reviews"]
    before=len(w["tasks"]); w=store.start_generation(wid); assert len(w["tasks"])==before
    assert "lease_token" not in json.dumps(w["generation_status"])


def test_interrupted_timing_is_explicit_and_excluded_from_duration(flow):
    from app.fact57098 import sha
    store,w=flow; t=store.claim(w['id'],'TEST_FIXTURE_ONLY','VISUAL_DESIGN')
    receipt=copy.deepcopy(t['brief']['receipt_contract']); data=png()
    receipt.update(asset_sha256=sha(data),tool_call_id='TEST_NOT_A_REAL_CALL',elapsed_seconds=None,qa={'inspected':True})
    with pytest.raises(WorkflowError,match='耗时无效'): store.visual_asset(w['id'],t['id'],t['lease_token'],data,receipt)
    receipt.update(timing_status='UNKNOWN_AFTER_INTERRUPTION',timing_note='TEST: duration unavailable; not zero')
    w=store.visual_asset(w['id'],t['id'],t['lease_token'],data,receipt)
    cost=w['generation_status']['cost']
    assert cost['accepted_tool_calls']==1 and cost['unknown_tool_timings']==1
    assert cost['reported_tool_seconds']==0
    assert w['generation']['pages'][0]['assets']['design']['receipt']['elapsed_seconds'] is None


def test_receipt_and_text_cannot_replace_locked_content(flow):
    store,w=flow; wid=w["id"]; t=store.claim(wid,"fixture","VISUAL_DESIGN")
    receipt=copy.deepcopy(t["brief"]["receipt_contract"])
    with pytest.raises(WorkflowError,match="实际文件"): store.visual_asset(wid,t["id"],t["lease_token"],png(),receipt)
    store.fail(wid,t["id"],t["lease_token"],"fixture validation")
    complete_one(store,wid,"VISUAL_DESIGN")
    t=store.claim(wid,"fixture","VISUAL_LAYOUT"); r=copy.deepcopy(t["brief"]["result_contract"]); r["design_inspected"]=True
    r["objects"][0]["text"]="replace evidence"
    with pytest.raises(ValueError,match="只能调整"): store.complete(wid,t["id"],t["lease_token"],r)
    r["objects"]=[]
    with pytest.raises(ValueError,match="全部锁定对象"): store.complete(wid,t["id"],t["lease_token"],r)
    assert not store.get(wid)["generation"]["pages"][0]["layout"]


def test_failed_tasks_resume_and_content_changes_cancel_stale(flow):
    store,w=flow; wid=w["id"]
    for _ in range(3):
        t=store.claim(wid,"fixture","VISUAL_DESIGN"); store.fail(wid,t["id"],t["lease_token"],"fixture failure")
    assert store.get(wid)["generation_status"]["status"]=="FAILED"
    w=store.start_generation(wid); assert len([t for t in w["tasks"] if t["kind"]=="VISUAL_DESIGN"])==2
    t=store.claim(wid,"fixture","VISUAL_DESIGN")
    w=store.settings(wid,{"theme":"plum"})
    assert w["generation_status"]["status"]=="STALE"
    with pytest.raises(WorkflowError): store.complete(wid,t["id"],t["lease_token"],{})


@pytest.mark.parametrize("bad",[b'<svg><image href="https://external/asset"/></svg>',b'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///secret">]><svg/>',b'<svg><script>alert(1)</script></svg>',b'<svg><metadata><script>alert(1)</script></metadata></svg>',b'<svg width="1280" height="720"><path filter="url(#x)" d="M0 0L1 1"/></svg>'])
def test_vectors_reject_bitmap_external_and_unsupported_effects(bad):
    with pytest.raises(ValueError): trace_svg(bad)


def test_native_groups_and_text_roundtrip(tmp_path):
    from factdeck.render import build_pptx
    from factdeck.native_vectors import add_native_vectors
    from pptx import Presentation
    m=model("≤ 300 cells/μL；仅限指定人群")
    path=tmp_path/"native.pptx"; build_pptx([m],{},["source notes"],path)
    v,stat=trace_svg(SVG,[{"name":"editable illustration","x":800,"y":0,"w":480,"h":720}]); add_native_vectors(path,[v])
    slide=Presentation(path).slides[0]
    assert slide.shapes.title.text==m["texts"][0]["paras"][0][0]["text"]
    assert any(s.shape_type==6 and s.name=="editable illustration" for s in slide.shapes)
    assert not any(s.shape_type==13 for s in slide.shapes)
    assert slide.notes_slide.notes_text_frame.text=="source notes"


def test_real_preparation_keeps_source_figures_and_drops_old_decoration(tmp_path):
    from test_figures import to_figure_deck, review, licence
    store=Store(tmp_path/"real-preparation"); w=to_figure_deck(store)
    with pytest.raises(WorkflowError,match="正式渲染前"): store.start_generation(w["id"])
    review(store,w); licence(store,w)
    w=store.start_generation(w["id"])
    assert w["generation_route"]=="A_NATIVE_VECTOR"
    assert len(w["generation"]["pages"])==len(w["deck"]["result"]["pages"])
    assert not any(p["lock"]["model"]["rasters"] for p in w["generation"]["pages"])
    assert any(p["lock"]["model"]["figures"] for p in w["generation"]["pages"])
    assert all("【来源追溯】" in p["lock"]["notes"] for p in w["generation"]["pages"] if p["lock"]["notes"])


def test_render_job_failure_is_persistent_and_resume_does_not_repeat_tools(flow,monkeypatch):
    store,w=flow; wid=w["id"]
    for _ in w["deck"]["result"]["pages"]:
        for kind in VISUAL_KINDS: w=complete_one(store,wid,kind)
    before=w["generation_status"]["cost"]["accepted_tool_calls"]
    def fail(*args,**kwargs): raise RuntimeError("TEST: Office not available")
    monkeypatch.setattr("factdeck.visual_render.render",fail)
    w=store.run_generation(wid)
    assert w["generation_status"]["status"]=="FAILED" and "Office" in w["generation_status"]["render"]["error"]
    assert not w["render"] and not w["page_reviews"]
    assert "lease_token" not in json.dumps(w["generation_status"])
    w=store.start_generation(wid)
    assert w["generation"]["render"]["status"]=="PENDING"
    assert w["generation_status"]["cost"]["accepted_tool_calls"]==before


def test_renderer_upgrade_recompiles_existing_assets_without_worker_calls(flow,monkeypatch):
    from app.deckflow import render_input
    from app import deck_generation
    store,w=flow;wid=w['id']
    for _ in w['deck']['result']['pages']:
        for kind in VISUAL_KINDS:w=complete_one(store,wid,kind)
    old_input=render_input(w);task_ids=[t['id'] for t in w['tasks']]
    before=w['generation_status']['cost']['accepted_tool_calls']
    with store.transaction(wid,'TEST_COMPLETE_OLD_RENDER') as state:
        state['generation']['render']={'status':'COMPLETE','attempts':1,'error':None}
        state['render']={'input_sha256':old_input,'draft':False,'hard_errors':0}
    monkeypatch.setattr(deck_generation,'NATIVE_RENDER_VERSION','TEST_RENDERER_REVISION')
    w=store.start_generation(wid)
    assert w['generation']['render']['status']=='PENDING'
    assert [t['id'] for t in w['tasks']]==task_ids
    assert w['generation_status']['cost']['accepted_tool_calls']==before
    assert all(all(kind in p['assets'] for kind in ('design','clean','vector')) for p in w['generation']['pages'])


def test_visual_api_upload_binding_and_auto_render_schedule(flow,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app import deckflow_api
    store,w=flow; monkeypatch.setattr(deckflow_api,"store",store)
    calls=[]; monkeypatch.setattr(store,"run_generation",lambda wid:calls.append(wid))
    app=FastAPI(); app.include_router(deckflow_api.router); client=TestClient(app)
    wid=w["id"]; base=f"/api/deck/workflows/{wid}"; t=store.claim(wid,"TEST_FIXTURE_ONLY","VISUAL_DESIGN")
    data=png(); from app.fact57098 import sha
    receipt=copy.deepcopy(t["brief"]["receipt_contract"]); receipt.update(asset_sha256=sha(data),tool_call_id="TEST_NOT_REAL",elapsed_seconds=1,qa={"inspected":True})
    response=client.post(base+f'/tasks/{t["id"]}/asset',data={"lease_token":t["lease_token"],"receipt":json.dumps(receipt)},files={"file":("actual.png",data,"image/png")})
    assert response.status_code==200 and calls==[wid]
    status=client.get(base+"/generation").json()
    assert status["pages"][0]["stages"]["design"]
    asset=client.get(status["pages"][0]["assets"]["design"]["url"])
    assert asset.content==data
    assert client.post(base+f'/tasks/{t["id"]}/asset',data={"lease_token":t["lease_token"],"receipt":json.dumps(receipt)},files={"file":("again.png",data,"image/png")}).status_code==409
