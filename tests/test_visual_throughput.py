"""Throughput changes to the A route: batch window, chained leases, mechanical receipts,
compact clean contract, layout preflight, per-page preview and early visual signals.

Protocol fixtures are invented. They do not constitute real tool calls or approvals."""
import argparse
from pathlib import Path
import copy
import json

import pytest
from PIL import Image, ImageDraw

from app.deck_generation import VISUAL_KINDS, CLEAN_PROMPT_LIMIT, ALLOWED_TOOLS
from app.fact57098 import sha
from test_visual_generation import flow, complete_one, png, SVG  # noqa: F401  (fixture)


def live_visual(w):
    return [t for t in w["tasks"] if t["kind"] in VISUAL_KINDS and t["status"] in {"PENDING", "RUNNING", "FAILED"}]


def test_batch_window_limits_queued_pages_and_withdraws_unclaimed_tasks(flow):
    store, w = flow; wid = w["id"]
    w = store.start_generation(wid, batch_size=2)
    w = complete_one(store, wid, "VISUAL_DESIGN")
    designs = [t for t in live_visual(w) if t["kind"] == "VISUAL_DESIGN"]
    assert len(designs) == 1 and len(w["generation"]["pages"]) > 3          # page 1 started + one more slot
    w = store.start_generation(wid, batch_size=1)                           # shrink: the unclaimed design is withdrawn
    assert not [t for t in live_visual(w) if t["kind"] == "VISUAL_DESIGN"]
    withdrawn = [t for t in w["tasks"] if t["kind"] == "VISUAL_DESIGN" and t["status"] == "CANCELLED"]
    assert withdrawn and all(t["attempts"] == 0 for t in withdrawn)
    for kind in VISUAL_KINDS[1:]: w = complete_one(store, wid, kind)        # finishing page 1 frees the slot
    assert [t["binding"] for t in live_visual(w)] == [w["generation"]["pages"][1]["id"]]


def test_clean_contract_is_compact_names_tools_and_local_paths(flow):
    store, w = flow; wid = w["id"]
    complete_one(store, wid, "VISUAL_DESIGN"); complete_one(store, wid, "VISUAL_LAYOUT")
    t = store.claim(wid, "fixture", "VISUAL_CLEAN")
    brief = t["brief"]
    assert len(brief["prompt"]) <= CLEAN_PROMPT_LIMIT and "native_regions" not in brief["prompt"]
    assert brief["regions"]["locked_boxes"] and brief["allowed_tools"] == ALLOWED_TOOLS["VISUAL_CLEAN"]
    assert "adobe" not in json.dumps(brief["allowed_tools"])
    design = brief["assets"]["design"]
    assert sha(open(design["local_path"], "rb").read()) == design["sha256"]


def test_claim_by_role_kinds(flow):
    store, w = flow; wid = w["id"]
    assert store.claim(wid, "vector-端", ("VISUAL_LAYOUT", "VISUAL_VECTOR")) is None
    t = store.claim(wid, "imagegen-端", ("VISUAL_DESIGN", "VISUAL_CLEAN"))
    assert t and t["kind"] == "VISUAL_DESIGN"


def test_submit_chains_the_same_page_to_the_same_worker(flow, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app import deckflow_api
    store, w = flow; monkeypatch.setattr(deckflow_api, "store", store)
    monkeypatch.setattr(store, "run_generation", lambda wid: None)
    monkeypatch.setattr(store, "run_page_preview", lambda wid, page: None)
    app = FastAPI(); app.include_router(deckflow_api.router); client = TestClient(app)
    wid = w["id"]; base = f"/api/deck/workflows/{wid}"
    t = client.post(base + "/tasks/claim", json={"worker": "W1", "kinds": ["VISUAL_DESIGN"]}).json()
    data = png(); receipt = copy.deepcopy(t["brief"]["receipt_contract"])
    receipt.update(asset_sha256=sha(data), tool_call_id="TEST_NOT_REAL", elapsed_seconds=1, qa={"inspected": True})
    r = client.post(base + f'/tasks/{t["id"]}/asset', params={"chain": True},
                    data={"lease_token": t["lease_token"], "receipt": json.dumps(receipt)}, files={"file": ("a.png", data, "image/png")}).json()
    nxt = r["next"]
    assert r["status"] == "COMPLETE" and nxt["kind"] == "VISUAL_LAYOUT" and nxt["binding"] == t["binding"]
    assert nxt["worker"] == "W1" and nxt["status"] == "RUNNING" and nxt["lease_token"]
    # A role-limited chain does not hand over a stage the worker does not do.
    result = copy.deepcopy(nxt["brief"]["result_contract"]); result["design_inspected"] = True
    r = client.post(base + f'/tasks/{nxt["id"]}/complete', params={"chain": True, "chain_kinds": ["VISUAL_VECTOR"]},
                    json={"lease_token": nxt["lease_token"], "result": result}).json()
    assert r["status"] == "COMPLETE" and r["next"] is None


def cli_args(**kw):
    base = dict(tool=None, tool_call_id="TEST_NOT_REAL", elapsed=12.5, timing_unknown=None, text_free=False,
                semantic_removed=False, qa_json=None, qa_note=None, illustration_plan=None, illustrations_kept=False, element_review=None)
    base.update(kw); return argparse.Namespace(**base)


def test_cli_builds_receipts_mechanically_and_server_accepts_them(flow):
    from tools.codex_worker import build_receipt, layout_result
    store, w = flow; wid = w["id"]
    t = store.claim(wid, "fixture", "VISUAL_DESIGN"); data = png()
    receipt = build_receipt(t, data, cli_args(qa_note="fixture review"))
    assert receipt["prompt"] == t["brief"]["prompt"] and receipt["asset_sha256"] == sha(data)
    assert receipt["contract_sha256"] == t["input_sha256"] and receipt["qa"] == {"inspected": True, "review": "fixture review"}
    with pytest.raises(SystemExit): build_receipt(t, data, cli_args(tool="some_other_tool"))
    with pytest.raises(SystemExit): build_receipt(t, data, cli_args(elapsed=None))
    unknown = build_receipt(t, data, cli_args(elapsed=None, timing_unknown="TEST: interrupted"))
    assert unknown["elapsed_seconds"] is None and unknown["timing_status"] == "UNKNOWN_AFTER_INTERRUPTION"
    store.visual_asset(wid, t["id"], t["lease_token"], data, receipt)
    t = store.claim(wid, "fixture", "VISUAL_LAYOUT")
    with pytest.raises(SystemExit): layout_result(t, _patch({"objects": [{"id": "not-a-locked-object"}]}))
    result = layout_result(t, None)
    assert result["design_inspected"] and result["objects"] == t["brief"]["result_contract"]["objects"]
    w = store.complete(wid, t["id"], t["lease_token"], result)
    t = store.claim(wid, "fixture", "VISUAL_CLEAN")
    clean = build_receipt(t, data, cli_args())
    assert clean["qa"]["text_free"] is False                      # never asserted on the worker's behalf
    with pytest.raises(Exception, match="说明插画|残字"): store.visual_asset(wid, t["id"], t["lease_token"], data, clean)
    clean = build_receipt(t, data, cli_args(text_free=True, semantic_removed=True))
    with pytest.raises(Exception, match="说明插画"): store.visual_asset(wid, t["id"], t["lease_token"], data, clean)
    clean = build_receipt(t, data, cli_args(text_free=True, semantic_removed=True, illustrations_kept=True))
    store.visual_asset(wid, t["id"], t["lease_token"], data, clean)


def _patch(value):
    import tempfile, pathlib
    path = pathlib.Path(tempfile.mkdtemp()) / "patch.json"; path.write_text(json.dumps(value), encoding="utf8")
    return path


def test_layout_preflight_rejects_overflow_before_any_tool_call(flow):
    from app.deckflow import WorkflowError
    store, w = flow; wid = w["id"]
    complete_one(store, wid, "VISUAL_DESIGN")
    t = store.claim(wid, "fixture", "VISUAL_LAYOUT")
    result = copy.deepcopy(t["brief"]["result_contract"]); result["design_inspected"] = True
    result["objects"][0].update(w=40, h=20)
    with pytest.raises(WorkflowError, match="版面预检"): store.complete(wid, t["id"], t["lease_token"], result)
    assert not store.get(wid)["generation"]["pages"][0]["layout"]
    result = copy.deepcopy(t["brief"]["result_contract"]); result["design_inspected"] = True
    w = store.complete(wid, t["id"], t["lease_token"], result)
    page = w["generation_status"]["pages"][0]
    assert page["preflight"]["overflow"] == [] and page["preflight"]["basis"] == "design"


def card_model(text_hex="F8F6EE", card=(100, 100, 400, 200)):
    x, y, cw, ch = card
    return {"background": {"hex": "F8F6EE", "a": 1}, "rasters": [], "figures": [], "tables": [], "lines": [],
            "shapes": [{"x": x, "y": y, "w": cw, "h": ch, "fill": {"hex": "FFFFFF", "a": 1}, "radius": 8, "line": None, "accents": []}],
            "texts": [{"x": x+20, "y": y+20, "w": 200, "h": 40, "paras": [[{"text": "标题", "size": 20, "color": {"hex": text_hex, "a": 1}}]]},
                      {"x": 700, "y": 100, "w": 300, "h": 40, "paras": [[{"text": "正文", "size": 18, "color": {"hex": "151B24", "a": 1}}]]}]}


def test_contrast_and_occlusion_signals(tmp_path):
    from factdeck.visual_qa import contrast_issues, occlusion_issues
    clean = tmp_path / "clean.png"; im = Image.new("RGB", (1280, 720), "#FDFCF7"); d = ImageDraw.Draw(im)
    d.rectangle((100, 100, 500, 420), fill="#F2EEE3")                    # artwork card taller than the native card
    d.ellipse((130, 200, 230, 300), fill="#2D5A47")                      # icon hidden under the native card
    im.save(clean)
    issues = contrast_issues(card_model(), clean)
    assert [i["text"] for i in issues] == ["标题"] and issues[0]["basis"] == "native_surface"
    assert not contrast_issues(card_model("151B24"), clean)
    found = {(i["type"], i.get("side")) for i in occlusion_issues(card_model(), clean)}
    assert ("ARTWORK_HIDDEN", None) in found and ("CONTAINER_EXTENDS", "bottom") in found
    plain = tmp_path / "plain.png"; Image.new("RGB", (1280, 720), "#FDFCF7").save(plain)
    assert not occlusion_issues(card_model(), plain)


def test_page_preview_is_recorded_shown_and_dropped_on_revision(flow, monkeypatch):
    store, w = flow; wid = w["id"]
    for kind in VISUAL_KINDS: w = complete_one(store, wid, kind)
    page = w["generation"]["pages"][0]["id"]
    calls = []
    def fake_render(generation, out, asset_path, title=""):
        calls.append([p["id"] for p in generation["pages"]]); out.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1280, 720), "white").save(out / "slide01.png")
        return {"summary": {"slides": 1, "overflow": 0}, "office": {"engine": "TEST_NOT_OFFICE", "editability": []}}
    monkeypatch.setattr("factdeck.visual_render.render", fake_render)
    preview = store.run_page_preview(wid, page)
    assert calls == [[page]] and preview["status"] == "COMPLETE"
    assert store.run_page_preview(wid, page)["fingerprint"] == preview["fingerprint"] and len(calls) == 1   # reused
    w = store.get(wid); shown = w["generation_status"]["pages"][0]["preview"]
    assert shown["status"] == "COMPLETE" and shown["url"].endswith(f"/previews/{page}")
    assert not w["render"] and not w["page_reviews"]                                                      # binds no review
    w = store.revise_generation(wid, page, "VISUAL_VECTOR")
    assert "preview" not in w["generation_status"]["pages"][0]
    assert store.run_page_preview(wid, w["generation"]["pages"][1]["id"]) is None                          # assets incomplete


def test_cli_claim_submit_layout_chain_in_process(flow, monkeypatch, tmp_path, capsys):
    import sys
    from app import deckflow_api
    from tools import codex_worker
    store, w = flow; wid = w["id"]
    monkeypatch.setattr(deckflow_api, "store", store)
    monkeypatch.setattr(store, "run_generation", lambda wid: None)
    monkeypatch.setattr(store, "run_page_preview", lambda wid, page: None)
    def cli(*argv):
        monkeypatch.setattr(sys, "argv", ["codex_worker.py", "--in-process", *argv]); codex_worker.main()
        return json.loads(capsys.readouterr().out)
    out = cli("claim", wid, "--worker", "W1", "--kinds", "VISUAL_DESIGN", "--out", str(tmp_path / "t1.json"), "--assets-dir", str(tmp_path / "a1"))
    assert out["kind"] == "VISUAL_DESIGN" and out["assets"] == {}
    (tmp_path / "design.png").write_bytes(png())
    out = cli("submit", wid, "--task", str(tmp_path / "t1.json"), "--file", str(tmp_path / "design.png"), "--tool-call-id", "TEST_NOT_REAL",
              "--elapsed", "3", "--inspected", "--qa-note", "fixture", "--next-out", str(tmp_path / "t2.json"))
    assert out["status"] == "COMPLETE" and out["next"]["kind"] == "VISUAL_LAYOUT"
    design = Path(out["next"]["assets"]["design"]); assert design.read_bytes() == png()
    with pytest.raises(SystemExit): cli("layout", wid, "--task", str(tmp_path / "t2.json"), "--inspected")   # must say how it matches the design
    out = cli("layout", wid, "--task", str(tmp_path / "t2.json"), "--inspected", "--matches-design", "TEST fixture: design keeps locked positions",
              "--next-out", str(tmp_path / "t3.json"))
    assert out["status"] == "COMPLETE" and out["next"]["kind"] == "VISUAL_CLEAN" and out["next"]["binding"] == w["generation"]["pages"][0]["id"]
    receipt = store.get(wid)["generation"]["pages"][0]["assets"]["design"]["receipt"]
    assert receipt["tool_call_id"] == "TEST_NOT_REAL" and receipt["elapsed_seconds"] == 3.0 and receipt["worker"] == "W1"


def test_role_claims_finish_pages_in_flight_before_new_designs(flow):
    store, w = flow; wid = w["id"]
    store.start_generation(wid, batch_size=3)
    complete_one(store, wid, "VISUAL_DESIGN"); complete_one(store, wid, "VISUAL_LAYOUT")
    w = store.get(wid)
    assert {t["kind"] for t in live_visual(w)} == {"VISUAL_DESIGN", "VISUAL_CLEAN"}
    t = store.claim(wid, "imagegen", ("VISUAL_DESIGN", "VISUAL_CLEAN"))
    assert t["kind"] == "VISUAL_CLEAN" and t["binding"] == w["generation"]["pages"][0]["id"]


def test_brief_change_reissues_pending_designs_on_resume(flow, monkeypatch):
    from app import deck_generation
    store, w = flow; wid = w["id"]
    complete_one(store, wid, "VISUAL_DESIGN")
    before = {t["id"] for t in live_visual(store.get(wid)) if t["kind"] == "VISUAL_DESIGN"}
    monkeypatch.setattr(deck_generation, "DESIGN_BRIEF_VERSION", "TEST-brief-next")
    w = store.start_generation(wid)
    after = live_visual(w)
    designs = {t["id"] for t in after if t["kind"] == "VISUAL_DESIGN"}
    assert before and designs and not before & designs                  # old-brief designs replaced, window refilled
    assert all(store.generation_fingerprint(w, t["kind"], t["binding"]) == t["input_sha256"] for t in after)


def test_named_sample_pages_take_the_batch_slots(flow):
    store, w = flow; wid = w["id"]
    complete_one(store, wid, "VISUAL_DESIGN")
    pages = [p["id"] for p in store.get(wid)["generation"]["pages"]]
    sample = [pages[-1], pages[-3]]
    w = store.start_generation(wid, batch_size=3, pages=sample)
    designs = [t["binding"] for t in live_visual(w) if t["kind"] == "VISUAL_DESIGN"]
    assert sorted(designs) == sorted(sample)                       # deck-order pages outside the sample wait


BODY = ["治疗分为两类：一类旨在减轻症状的影响", "这种方法适用于任何场合"]


def content_page_with_body(store, wid, texts=BODY):
    """Fixture pages hold all text in one title box; give one content page body passages (invented fixture text)."""
    from app import deck_generation
    w = store.start_generation(wid, batch_size=60)
    w = complete_one(store, wid, "VISUAL_DESIGN")
    page = next(p for p in w["generation"]["pages"][1:] if deck_generation.page_role(w, p["id"]) == "content"
                and deck_generation.illustrated(deck_generation.page_layout(w, p["id"])))
    with store.transaction(wid, "TEST_FIXTURE_BODY_TEXT") as state:
        m = next(x for x in state["generation"]["pages"] if x["id"] == page["id"])["lock"]["model"]
        for k, text in enumerate(texts):
            m["texts"].append({"x": 860, "y": 40 + 90 * k, "w": 380, "h": 80, "lineHeight": 24, "align": "left", "anchor": "top", "nowrap": False,
                               "role": "", "paras": [[{"text": text, "size": 16, "bold": False, "color": {"hex": "151B24", "a": 1}}]]})
    store.start_generation(wid)
    return page["id"]


def good_plan():
    return {"units": [{"text": BODY[0], "relation": {"type": "categories", "span": "分为两类"},
                       "terms": [{"span": "治疗", "role": "whole"}, {"span": "症状的影响", "role": "category"}],
                       "draw": [{"object": "治疗 的分支示意", "bound_to": "治疗", "derivation": ""},
                                {"object": "通用的症状示意符号", "bound_to": "症状的影响", "derivation": "generic_symbol"}], "encoding": ""}],
            "omitted": [{"text": BODY[1], "reason": "duplicate"}], "arrangement": "插画在文字左侧"}


def test_content_page_contract_carries_passages_candidates_and_no_plan_noise(flow):
    from app import deck_generation
    store, w = flow; wid = w["id"]
    pid = content_page_with_body(store, wid)
    t = store.claim(wid, "fixture", "VISUAL_DESIGN", pid)
    c = t["brief"]["illustration_plan_contract"]
    assert c["grammar"]["version"] == "visual-grammar.5" and c["layout"] == deck_generation.page_layout(store.get(wid), pid)
    passages = {x["text"]: x["candidates"] for x in c["grammar"]["passages"]}
    assert "categories" in passages[BODY[0]] and "purpose_means" in passages[BODY[0]] and "scope" in passages[BODY[1]]
    assert "插图目标" in t["brief"]["prompt"] and "本页是正文页" in t["brief"]["prompt"] and "参考首张设计稿统一整套视觉" not in t["brief"]["prompt"]
    prompt = deck_generation.plan_prompt(t["brief"]["prompt"], good_plan())
    assert deck_generation.PLAN_MARK in prompt and "duplicate" not in prompt and "omitted" not in prompt      # the image model sees only the list


def test_v5_plan_rules_are_general_and_bind_everything_drawn():
    from factdeck.visual_grammar import check_plan
    check_plan(good_plan(), "statement", BODY)
    def bad(change):
        plan = good_plan(); change(plan); return plan
    cases = [
        (lambda p: p["units"][0]["relation"].update(span="导致"), "span"),                                   # relation not stated
        (lambda p: p["units"][0]["terms"].append({"span": "不在原文", "role": "x"}), "逐字"),
        (lambda p: p["units"][0]["draw"].pop(), "未绑定"),                                                   # every term drawn
        (lambda p: p["units"][0]["draw"].append({"object": "风景", "bound_to": "风景", "derivation": ""}), "绑定"),
        (lambda p: p["units"][0]["draw"].append({"object": "一个人", "bound_to": "治疗", "derivation": "made_up"}), "derivation"),
        (lambda p: p["units"][0]["draw"].append({"object": "患者 示意", "bound_to": "治疗", "derivation": "generic_symbol"}), "人物"),
        (lambda p: p.update(omitted=[]), "关系词"),                                                          # candidate passage must be handled
        (lambda p: p.update(omitted=[{"text": BODY[1], "reason": "attribution_only"}]), "attribution_only"),
        (lambda p: p.update(units=[], omitted=[]), "omitted"),
    ]
    for change, message in cases:
        with pytest.raises(ValueError, match=message): check_plan(bad(change), "statement", BODY)
    carrier = good_plan(); carrier["units"][0]["draw"].append({"object": "患者 轮廓作症状载体", "bound_to": "症状的影响", "derivation": "carrier"})
    check_plan(carrier, "statement", BODY)
    with pytest.raises(ValueError, match="焦点"):                                                           # the focus is never left out
        check_plan({"units": [], "omitted": [{"text": BODY[0], "reason": "duplicate"}, {"text": BODY[1], "reason": "duplicate"}]}, "statement", BODY, focus=BODY[0])
    blocker = {"units": [{"text": "使用β-block剂", "relation": {"type": "entity", "span": ""}, "terms": [{"span": "β-block剂", "role": "x"}],
                          "draw": [{"object": "β-block剂 的药瓶示意", "bound_to": "β-block剂", "derivation": ""}], "encoding": ""}]}
    check_plan(blocker, "statement", ["使用β-block剂"])                                                     # no keyword ban on legitimate terms


def test_design_prompt_refuses_a_bad_plan_before_any_image_call(flow, tmp_path):
    from app.deckflow import WorkflowError
    from app.deck_generation import plan_prompt
    from tools.codex_worker import build_receipt, design_prompt
    store, w = flow; wid = w["id"]
    pid = content_page_with_body(store, wid)
    t = store.claim(wid, "fixture", "VISUAL_DESIGN", pid); data = png()
    broken = good_plan(); broken["omitted"] = []
    with pytest.raises(SystemExit, match="未通过检查"): design_prompt(t, broken)
    assert design_prompt(t, good_plan()) == plan_prompt(t["brief"]["prompt"], good_plan())
    path = tmp_path / "plan.json"; path.write_text(json.dumps(good_plan(), ensure_ascii=False), encoding="utf8")
    receipt = build_receipt(t, data, cli_args(illustration_plan=path))
    with pytest.raises(WorkflowError, match="提示词"): store.visual_asset(wid, t["id"], t["lease_token"], data, dict(receipt, prompt=t["brief"]["prompt"]))
    w = store.visual_asset(wid, t["id"], t["lease_token"], data, receipt)
    assert next(p for p in w["generation"]["pages"] if p["id"] == pid)["assets"]["design"]["receipt"]["qa"]["illustration_plan"] == good_plan()


def test_blind_read_is_independent_compared_with_the_plan_and_gates_export(flow, tmp_path):
    from app.deck_generation import plan_prompt, ready
    store, w = flow; wid = w["id"]
    pid = content_page_with_body(store, wid)
    t = store.claim(wid, "designer", "VISUAL_DESIGN", pid); data = png()
    receipt = copy.deepcopy(t["brief"]["receipt_contract"])
    receipt.update(asset_sha256=sha(data), tool_call_id="TEST_NOT_REAL", elapsed_seconds=1, qa={"inspected": True, "illustration_plan": good_plan()},
                   prompt=plan_prompt(t["brief"]["prompt"], good_plan()))
    store.visual_asset(wid, t["id"], t["lease_token"], data, receipt)
    for kind, worker in (("VISUAL_LAYOUT", "designer"), ("VISUAL_CLEAN", "designer")):
        t = store.claim(wid, worker, kind, pid)
        if kind == "VISUAL_LAYOUT":
            r = copy.deepcopy(t["brief"]["result_contract"]); r["design_inspected"] = True; store.complete(wid, t["id"], t["lease_token"], r)
        else:
            rc = copy.deepcopy(t["brief"]["receipt_contract"]); rc.update(asset_sha256=sha(data), tool_call_id="TEST_NOT_REAL", elapsed_seconds=1,
                                                                        qa={k: True for k in rc["qa"]})
            store.visual_asset(wid, t["id"], t["lease_token"], data, rc)
    assert store.claim(wid, "designer", "VISUAL_BLIND_READ", pid) is None           # never the author of the plan or clean image
    t = store.claim(wid, "reader", "VISUAL_BLIND_READ", pid)
    assert "design" not in t["brief"] and "illustration_plan" not in json.dumps(t["brief"]) and list(t["brief"]["assets"]) == ["clean"]
    reading = {"input_sha256": t["input_sha256"], "inspected": True,
               "objects": [{"description": "一棵树", "bound_to": "无"}, {"description": "分支", "bound_to": "治疗"}], "relations": []}
    w = store.complete(wid, t["id"], t["lease_token"], reading)
    page = next(p for p in w["generation_status"]["pages"] if p["id"] == pid)
    assert page["blind_read"]["status"] == "FAIL" and len(page["blind_read"]["issues"]) == 3     # extra object, missing relation, missing term
    assert not ready(w)
    w = store.revise_generation(wid, pid, "VISUAL_BLIND_READ")
    t = store.claim(wid, "reader", "VISUAL_BLIND_READ", pid)
    reading = {"input_sha256": t["input_sha256"], "inspected": True,
               "objects": [{"description": "分支", "bound_to": "治疗"}, {"description": "症状符号", "bound_to": "症状的影响"}],
               "relations": [{"type": "categories", "spans": ["分为两类"]}]}
    w = store.complete(wid, t["id"], t["lease_token"], reading)
    assert next(p for p in w["generation_status"]["pages"] if p["id"] == pid)["blind_read"]["status"] == "PASS"


def test_reference_images_by_page_role(flow, monkeypatch, tmp_path):
    from app import deck_generation
    store, w = flow; wid = w["id"]
    store.start_generation(wid, batch_size=60)
    w = complete_one(store, wid, "VISUAL_DESIGN"); pages = w["generation"]["pages"]
    content = next(p for p in pages[1:] if deck_generation.page_role(w, p["id"]) == "content")
    assert list(store.design_references(w, content)) == ["style_reference"]          # nothing bound: palette from the first design
    for p in pages[1:]:
        if deck_generation.page_role(w, p["id"]) == "cover":
            assert list(store.design_references(w, p)) == ["style_reference"]
    image = tmp_path / "ref.png"; image.write_bytes(png())
    monkeypatch.setattr(deck_generation, "standard_content_references", lambda w: [{"name": "standard_content_02", "sha256": sha(png()), "path": image}])
    assert list(store.design_references(w, content)) == ["standard_content_02"]
    monkeypatch.setattr(deck_generation, "project_content_references", lambda w: [{"name": "project_reference_01", "sha256": sha(png()), "path": image}])
    refs = store.design_references(w, content)
    assert list(refs) == ["project_reference_01"] and refs["project_reference_01"]["url"].endswith("/visual-standard/project_reference_01")


def test_focus_pages_with_spare_slots_do_not_churn_tasks(flow):
    store, w = flow; wid = w["id"]
    complete_one(store, wid, "VISUAL_DESIGN")
    pages = [p["id"] for p in store.get(wid)["generation"]["pages"]]
    sample = [pages[-1]]
    w = store.start_generation(wid, batch_size=7, pages=sample)
    before = len(w["tasks"])
    for _ in range(3):                                            # repeated advances (resume) must be stable
        w = store.start_generation(wid)
    assert len(w["tasks"]) == before
    designs = [t["binding"] for t in live_visual(w) if t["kind"] == "VISUAL_DESIGN"]
    assert designs == sample                                     # pages outside the sample set are not opened


def test_missing_reference_images_are_left_out_not_fatal(flow, monkeypatch, tmp_path):
    from app import deck_generation
    store, w = flow; wid = w["id"]
    w = complete_one(store, wid, "VISUAL_DESIGN")
    missing = tmp_path / "gone.png"
    assert deck_generation.verified_file(missing, "0" * 64, tmp_path) is False
    real = tmp_path / "ref.png"; real.write_bytes(png())
    assert deck_generation.verified_file(real, sha(png()), tmp_path) is True
    assert deck_generation.verified_file(real, "f" * 64, tmp_path) is False             # changed content
    assert deck_generation.verified_file(real, sha(png()), tmp_path / "elsewhere") is False  # outside its root
    store.start_generation(wid)                                                          # advancing never raises
