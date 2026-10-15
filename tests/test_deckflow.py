"""FactDeck mainline: protocol and gate tests.

Model outputs here are hand-written fixtures and approvals are test records; they are
not model evidence, customer sign-off or medical review. Content is invented.
"""
import copy
from pathlib import Path
import io
import zipfile

import pytest

from app.deckflow import summary_key_points, Store, WorkflowError, digest, input_hash, stage, verified
import factdeck_fixture as fx_

OUTLINE = "认识示例病X\n评估与治疗\n研究证据"


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "deckflow-data")


def read_all(store, wid, worker="reader-1"):
    store.queue(wid, "READ_SOURCE")
    while True:
        t = store.claim(wid, worker, "READ_SOURCE")
        if not t:
            break
        result = copy.deepcopy(t["brief"]["result_contract"])
        for row in result["pages"]:
            row["visual_inspected"] = True
            if row["id"] == "S03:s1":              # a chart on the slide, transcribed by the reader
                row["transcription"] = [{"id": "c1", "location": "柱状图 研究甲标签", "text": "缓解率38%"}]
        store.complete(wid, t["id"], t["lease_token"], result)
    return claim_all(store, wid)


def claim_all(store, wid, worker="claims-1"):
    """A mechanical claims list for the fixtures: one claim per text unit of each body page (test records only)."""
    store.queue(wid, "CLAIMS")
    while t := store.claim(wid, worker, "CLAIMS"):
        result = copy.deepcopy(t["brief"]["result_contract"])
        for row, page in zip(result["pages"], t["brief"]["pages"]):
            if page["classification"] != "SUBSTANTIVE":
                row["claims"] = []
                continue
            units = [u for u in page["units"] if u["text"].strip()]
            row["claims"] = [{"id": f"k{i}", "type": "background", "spans": [{"unit_id": u["id"], "quote": u["text"][:120]}]}
                             for i, u in enumerate(units, 1)]
            row["no_claims"] = "" if units else "本页没有文字（测试）"
        store.complete(wid, t["id"], t["lease_token"], result)
    return store.get(wid)


def claim_of(w, unit_id):
    """The fixture claim quoting a unit."""
    return next(k["id"] for s in w["sources"] for k in (s.get("claims") or {}).get("items", []) if unit_id in k["unit_ids"])


def clear_summary_review(contract):
    """Fill every verdict of a summary-review contract explicitly as passed (test record, not a real review).
    The contract itself carries empty verdicts: a real reviewer must judge each one."""
    r = copy.deepcopy(contract)
    for sec in r.get("sections") or []:
        sec["summary_verdict"] = sec.get("summary_verdict") or "ENTAILED"
        for row in sec.get("points", []) + sec.get("key_points", []):
            row["verdict"] = row.get("verdict") or "ENTAILED"
        if "core" in sec:
            sec["core"]["verdict"] = sec["core"].get("verdict") or "SUPPORTED"
        for row in sec.get("relations") or []:
            row["verdict"] = row.get("verdict") or "SUPPORTED"
    for row in r.get("coverage_review") or []:
        row["verdict"] = row.get("verdict") or ("FULL" if row["disposition"] == "EXPRESSED" else "ACCEPTED")
        if row["disposition"] == "EXPRESSED" and not row.get("point_evidence"):
            row["point_evidence"] = [{"point_id": e["point_id"], "quote": e["summary_quote"]} for e in row["author_expressions"]]
    return r


def review_summary(store, wid, worker="reviewer-S"):
    """An all-clear summary review (test record, not a real review)."""
    return run_task(store, wid, "SUMMARY_REVIEW", worker, lambda t: clear_summary_review(t["brief"]["result_contract"]))


def key_points(w, page_ids):
    """One key point per cited page that has text, resting on that page's first unit."""
    first = {}
    for s in w["sources"]:
        for u in s["units"] + s["transcriptions"]:
            first.setdefault(u["page_id"], u["id"])
    return [{"point": "本页要点（程序验收用）", "unit_ids": [first[p]]} for p in page_ids if p in first]


def candidate_decisions(w, page_ids, adopted=()):
    """Every candidate relation on these pages: adopted when named, otherwise declined (fixture decision, not a real review)."""
    from app.deckflow import relation_candidates_of, all_units
    unit_page = {u["id"]: u["page_id"] for u in all_units(w)}
    mine = sorted(cid for cid, c in relation_candidates_of(w).items() if any(unit_page.get(u) in set(page_ids) for u in c.get("unit_ids") or []))
    return [{"candidate": c, "decision": "ADOPTED"} if c in adopted else {"candidate": c, "decision": "REJECTED", "reason": "not_between_points"} for c in mine]


def with_message(w, section):
    """Fixture information structure for a chapter whose points are its key points: the first key point is the core."""
    keys = section["key_points"]
    if keys:
        core = {"claim_id": keys[0]["claim_ids"][0]} if keys[0].get("claim_ids") else {"none": "TEST fixture: key points rest on units, not claims"}
        section["message"] = {"core": core,
                              "roles": {f"{section['id']}.k{i}": ("core" if i == 1 and "claim_id" in core else "support") for i in range(1, len(keys) + 1)},
                              "relations": [], "candidate_decisions": candidate_decisions(w, section["source_page_ids"])}
    return section


def summary(w):
    r = _summary(w)
    for sec in r["sections"]:
        with_message(w, sec)
    return r


def with_understanding(w, result):
    """Synthetic new-contract fixture; these reasons are TEST data, not a model audit."""
    from factdeck.summary_evidence import ALGORITHM, SCHEMA
    from app.deckflow import all_claims, all_units
    claims = all_claims(w)
    unit_page = {u['id']: u['page_id'] for u in all_units(w)}
    links = {p['id']: set() for s in w['sources'] for p in s['pages']}
    rows = []
    for section in result['sections']:
        for i, point in enumerate(section['key_points'], 1):
            pid = f"{section['id']}.k{i}"
            evidence = []
            cids = point.get('claim_ids') or [cid for cid, claim in claims.items()
                if any(sp['unit_id'] in point.get('unit_ids', []) for sp in claim['spans'])]
            if not point.get('claim_ids'):
                point['claim_ids'] = cids
            for cid in cids:
                for span in claims[cid]['spans']:
                    evidence.append({'id': f'e{len(evidence)+1}', 'unit_id': span['unit_id'], 'quote': span['quote'],
                                     'role': 'main', 'usage': 'TEACHING'})
                    links[unit_page[span['unit_id']]].add(pid)
            rows.append({'point_id': pid, 'selection_reason': 'TEST：验证要点与证据同步绑定的合同',
                         'context': 'TEST：完整上下文由fixture提供，非真实语义判断', 'evidence': evidence,
                         'data_items': [], 'figure_ids': []})
    result.update(summary_algorithm=ALGORITHM, evidence_index={'schema_version': SCHEMA, 'points': rows,
        'page_decisions': [{'page_id': p, 'disposition': 'TEACHING' if v else 'CONTEXT',
                            'reason': 'TEST：来源页处置记录', 'point_ids': sorted(v)} for p, v in links.items()]})
    result['source_understanding'] = {'schema_version': 'source_understanding.v1', 'sections': []}
    for section in result['sections']:
        sr = [r for r in rows if r['point_id'].rsplit('.k', 1)[0] == section['id']]
        if not sr:
            continue
        result['source_understanding']['sections'].append({'section_id': section['id'],
            'author_message': 'TEST合成来源主旨', 'organization': {'basis': 'ANALYST_ORGANIZATION', 'reason': 'TEST组织建议'},
            'conclusions': [{'id': f'c{i}', 'statement': 'TEST合成结论', 'conditions_and_limits': f'TEST保留来源条件{section["id"]}{i}',
                'point_ids': [r['point_id']], 'evidence_refs': [f"{r['point_id']}/{e['id']}" for e in r['evidence'][:1]]}
                for i, r in enumerate(sr, 1)], 'relations': [], 'relation_assessment': 'TEST不推断来源关系'})
    return with_source_coverage(result, all_units(w))


def with_source_coverage(result, units):
    """Synthetic structural fixture only. Never use to classify real sources."""
    from factdeck.source_coverage import scaffold
    ledger = scaffold(result, units)
    evidence = {r['point_id']: r['evidence'] for r in result['evidence_index']['points']}
    from factdeck.source_coverage import SCHEMA_V2, segments
    points = {f"{s['id']}.k{i}": k.get('point', '') for s in result['sections'] for i, k in enumerate(s.get('key_points') or [], 1)}
    for row, unit in zip(ledger['units'], units):
        found = [(f"{s['section_id']}/{c['id']}", c['point_ids'][0]) for s in result['source_understanding']['sections']
                 for c in s['conclusions'] if any(e['unit_id'] == unit['id']
                     for pid in c['point_ids'] for e in evidence[pid])]
        if not found:   # claimed text must be expressed in v2; bind it to a conclusion of the section that owns the page
            found = [(f"{u['section_id']}/{u['conclusions'][0]['id']}", u['conclusions'][0]['point_ids'][0])
                     for u in result['source_understanding']['sections']
                     for sec in result['sections'] if sec['id'] == u['section_id'] and unit['page_id'] in sec['source_page_ids']][:1]
        ids = [cid for cid, _ in found]
        if not unit['text']:
            continue
        if ledger['schema_version'] != SCHEMA_V2:
            row['parts'] = [{'start': 0, 'end': len(unit['text']), 'quote': unit['text'],
                'disposition': 'EXPRESSED' if ids else 'SOURCE_METADATA',
                'reason': 'TEST结构fixture，不是真实分类', 'conclusion_ids': ids}]
            continue
        # One part per code-cut sentence; the expression is a synthetic slice of the point, never a real judgment.
        row['parts'] = [{'segment_index': n, 'reason': 'TEST结构fixture，不是真实分类', 'conclusion_ids': ids,
                         **({'disposition': 'EXPRESSED', 'expressions': [{'point_id': pid, 'summary_quote': points.get(pid, '')[:4]} for _, pid in found]}
                            if ids else {'disposition': 'SOURCE_METADATA'})}
                        for n, _ in enumerate(segments(unit['text']))]
    for row in ledger.get('conclusions', []):
        for record in row['facets'].values():
            record.update(status='NOT_STATED', reason='TEST虚构字段，不是真实来源判断')
    result['source_coverage'] = ledger
    return result


def _summary(w):
    ids = [p["id"] for s in w["sources"] for p in s["pages"]]
    return {"schema_version": "full_source_summary.v3", "input_sha256": input_hash(w),
            "overall_summary": "程序验收用的虚构资料总结：示例病X的定义与诊断、评估流程与药物、两项研究及其不可直接比较的限制。",
            "sections": [{"id": "s1", "title": "概述与诊断", "summary": "示例病X的定义、患病率与两项诊断指标的同时满足规则。", "source_page_ids": ids[:3], "key_points": key_points(w, ids[:3])},
                         {"id": "s2", "title": "评估与治疗", "summary": "评估流程、高风险人群、药物靶点与用法以及用药限制。", "source_page_ids": ids[3:5], "key_points": key_points(w, ids[3:5])},
                         {"id": "s3", "title": "研究证据", "summary": "两项研究的人群与缓解率，以及随访结果和比较限制。", "source_page_ids": ids[5:], "key_points": key_points(w, ids[5:])}],
            "outline_coverage": [{"outline_id": o["id"], "section_ids": [f"s{i}"]} for i, o in enumerate(w["outline"], 1)],
            "pending_issues": []}


def run_task(store, wid, kind, worker, make):
    store.queue(wid, kind)
    t = store.claim(wid, worker, kind)
    assert t, kind
    result = make(t)
    if kind == 'SUMMARY' and t['brief'].get('summary_algorithm') and not result.get('summary_algorithm'):
        with_understanding(store.get(wid), result)
    if kind == 'DECK' and t['brief'].get('summary_key_points'):
        with_key_points(result, t['brief']['summary_key_points'])
    return store.complete(wid, t["id"], t["lease_token"], result)


def with_key_points(deck, key_points):
    """Synthetic fixture only: each content page teaches its chapters' key points; leftovers go to the last content page."""
    from factdeck.deck import NON_CONTENT
    ids = [k['key_point_id'] for k in key_points]
    content = [p for p in deck['pages'] if p.get('layout') not in NON_CONTENT and p.get('layout') != 'closing']
    for p in content:
        if 'key_point_ids' not in p:
            p['key_point_ids'] = [k for k in ids if k.rsplit('.k', 1)[0] in (p.get('section_ids') or [])] or ids[:1]
    used = {k for p in content for k in p['key_point_ids']}
    if content:
        content[-1]['key_point_ids'] += [k for k in ids if k not in used]
    return deck


def approve(store, w, kind):
    if kind == "content" and w["stage"] == "SUMMARY_REVIEW_REQUIRED":
        w = review_summary(store, w["id"])
    return store.approval(w["id"], kind, {"customer": "TEST-CUSTOMER", "operator": "TEST-OPERATOR",
                                          "method": "AUTOMATED_PROTOCOL_TEST_NOT_REAL_APPROVAL", "subject_sha256": w["approval_subjects"][kind],
                                          **({"acknowledged_issues": w["content_acknowledge"]} if kind == "content" else {})})


def facts_result(w):
    r = fx_.facts_proposal(fx_.UIDS)
    r["facts"].append({"id": "chart.a", "unit": "S03:s1:x.c1", "quote": "缓解率38%", "section_ids": ["s3"]})
    r["summary_sha256"] = digest(w["summary"])
    return r


def deck_result(w):
    d = fx_.deck_spec([o["id"] for o in w["outline"]])
    d["pages"][6]["panels"][0]["items"].append({"fact": "chart.a"})
    d["facts_sha256"] = w["facts"]["result_sha256"]
    from app.deckflow import summary_key_points
    kp = summary_key_points(w)
    return with_key_points(d, [{"key_point_id": k} for k in kp]) if kp is not None else d


def to_deck(store):
    w = store.create("示例病X（程序验收）", OUTLINE, {"audience": "规培医生", "target_pages": 9, "purpose": "程序验收"}, generation_route="CODE_NATIVE")
    # This fixture exercises the retained legacy order: facts/deck before second read.
    # New-source-policy rejection is tested separately in test_source_prevention_integration.
    with store.transaction(w["id"], "LEGACY_PROTOCOL_TEST_FIXTURE") as saved:
        saved.pop("source_evidence_policy", None)
    for name, make in fx_.SOURCES.items():
        store.add_source(w["id"], name, make())
    w = read_all(store, w["id"])
    assert stage(w) == "SUMMARY_REQUIRED"
    w = run_task(store, w["id"], "SUMMARY", "author-A", lambda t: summary(w))
    w = approve(store, w, "content")
    w = run_task(store, w["id"], "FACTS", "author-A", lambda t: facts_result(w))
    w = run_task(store, w["id"], "DECK", "author-A", lambda t: deck_result(w))
    return w


def test_sources_are_split_into_pages_and_quotable_units(store):
    w = store.create("拆分", "")
    for name, make in fx_.SOURCES.items():
        w = store.add_source(w["id"], name, make())
    assert [s["id"] for s in w["sources"]] == ["S01", "S02", "S03", "S04"]
    units = {u["id"]: u for s in w["sources"] for u in s["units"]}
    assert set(fx_.UIDS.values()) <= set(units)
    assert units["S03:s1:t1r2c2"]["location"] == "第1页 表格1 第2行第2列"
    assert all(p["requires_visual"] for p in w["sources"][2]["pages"])        # slides are always checked visually
    with pytest.raises(WorkflowError):
        store.add_source(w["id"], "again.txt", fx_.txt_source())
    with pytest.raises(WorkflowError):
        store.add_source(w["id"], "x.exe", b"MZ")


def test_reading_must_cover_every_page_and_inspect_visuals(store):
    w = store.create("阅读", "")
    w = store.add_source(w["id"], "studies.pptx", fx_.pptx_source())
    store.queue(w["id"], "READ_SOURCE")
    t = store.claim(w["id"], "reader-1")
    lazy = copy.deepcopy(t["brief"]["result_contract"])
    with pytest.raises(WorkflowError, match="视觉"):
        store.complete(w["id"], t["id"], t["lease_token"], lazy)
    lazy["pages"] = []
    with pytest.raises(WorkflowError, match="全部页面"):
        store.complete(w["id"], t["id"], t["lease_token"], lazy)


def test_summary_key_points_must_rest_on_units_of_the_section(store):
    w = store.create("关键依据", OUTLINE)
    for name, make in fx_.SOURCES.items():
        store.add_source(w["id"], name, make())
    w = read_all(store, w["id"])
    store.queue(w["id"], "SUMMARY")
    t = store.claim(w["id"], "author-A", "SUMMARY")
    assert all("units" in p for s in t["brief"]["sources"] for p in s["pages"])

    def submit(edit):
        r = summary(w)
        edit(r["sections"])
        with_understanding(w, r)
        store.complete(w["id"], t["id"], t["lease_token"], r)

    with pytest.raises(WorkflowError, match="key_points"):
        submit(lambda ss: ss[0].update(key_points=[]))
    with pytest.raises(WorkflowError, match="不存在的论断或文字单元"):
        submit(lambda ss: ss[0]["key_points"][0].update(unit_ids=["S99:x"]))
    with pytest.raises(WorkflowError, match="未引用页面"):
        submit(lambda ss: ss[0]["key_points"][0].update(unit_ids=ss[2]["key_points"][0]["unit_ids"]))
    submit(lambda ss: None)
    assert store.get(w["id"])["summary"]["sections"][0]["key_points"]


def test_fact_gate_runs_on_the_store(store):
    w = to_deck(store)
    v = verified(w)
    assert v["facts"]["bad.num"]["status"] == "REJECTED"
    assert v["facts"]["bad.neg"]["status"] == "REJECTED"
    assert v["facts"]["chart.a"]["needs_confirmation"]                          # transcription, no second read yet
    assert [c["key"] for c in v["conflicts"]] == ["药物A|单价(元)"]
    assert w["facts"]["rejected"] == 2


def test_deck_with_authored_claims_is_refused(store):
    w = to_deck(store)
    bad = deck_result(w)
    bad["pages"][2]["title"] = {"text": "药物A显著降低发作72%"}
    with pytest.raises(WorkflowError, match="作者文字"):
        store.author(w["id"], "DECK", bad, "editor")
    bad = deck_result(w)
    bad["pages"] = [p for p in bad["pages"] if w["outline"][2]["id"] not in (p.get("outline_ids") or [])]
    with pytest.raises(WorkflowError, match="提纲"):
        store.author(w["id"], "DECK", bad, "editor")


def test_deck_may_carve_verbatim_facts_for_its_slots(store):
    w = to_deck(store)
    store.queue(w["id"], "DECK")
    brief = store.claim(w["id"], "author-A", "DECK")["brief"]
    assert brief["units"] and brief["result_contract"]["facts"] == [] and brief["layouts"]["flow"]["example"]["edges"]

    def deck(*cut, card=({"fact": "risk.who"}, {"fact": "risk.age"})):
        d = deck_result(w)
        d["facts"] = [dict(c) for c in cut]
        d["pages"][3]["cards"].append({"label": card[0], "value": card[1]})
        return d

    who = {"id": "risk.who", "unit": fx_.UIDS["doc_risk"], "quote": "高风险人群", "section_ids": ["s2"]}
    age = {"id": "risk.age", "unit": fx_.UIDS["doc_risk"], "quote": "年龄≥65岁", "section_ids": ["s2"]}
    with pytest.raises(WorkflowError, match="未通过核对"):
        store.author(w["id"], "DECK", deck(who, {**age, "quote": "年龄≥60岁"}), "editor")        # not in the unit
    with pytest.raises(WorkflowError, match="未通过核对"):
        store.author(w["id"], "DECK", deck(who, {**age, "display": "年龄65岁"}), "editor")       # drops the operator
    with pytest.raises(WorkflowError, match="重复"):
        store.author(w["id"], "DECK", deck(who, {**age, "id": "risk"}, card=({"fact": "risk.who"}, {"fact": "risk"})), "editor")
    with pytest.raises(WorkflowError, match="不能带推导"):
        store.author(w["id"], "DECK", deck(who, {**age, "derivation": "d1"}), "editor")
    with pytest.raises(WorkflowError, match="没有在任何页面使用"):
        store.author(w["id"], "DECK", deck(who, age, {"id": "spare", "unit": fx_.UIDS["doc_risk"], "quote": "既往住院≥2次"}), "editor")
    w = store.author(w["id"], "DECK", deck(who, age), "editor")
    v = verified(w)
    assert v["facts"]["risk.age"]["status"] == "ACCEPTED" and v["facts"]["risk.age"]["carved"]
    assert not v["facts"]["risk"]["carved"]
    store.queue(w["id"], "SEMANTIC_REVIEW")
    t = store.claim(w["id"], "reviewer-B", "SEMANTIC_REVIEW")
    shown = {f["id"]: f for p in t["brief"]["pages"] for f in p["facts"]}
    assert shown["risk.age"]["carved_by_deck"] and shown["risk.age"]["unit_text"].startswith("高风险人群")


def all_clear(t, edit=None):
    """An all-clear checklist result filled from the contract (test record, not a real review)."""
    r = copy.deepcopy(t["brief"]["result_contract"])
    for key in ("source_pages", "teaching_items"):
        for row in r.get(key) or []:
            if not row["status"]:
                row.update(status="EXCLUDED", reason="测试：本页不讲")
    for row in r.get("relations") or []:
        row["verdict"] = row["verdict"] or "SUPPORTED"
        if "expression" in row:
            row["expression"] = row["expression"] or "EXPRESSED"
    for row in r.get("chapters") or []:
        row.update(restated=row["restated"] or "测试：页面复述的核心论点", core_on_pages=row["core_on_pages"] or "YES",
                   limits_on_pages=row["limits_on_pages"] or "YES")
    for row in r.get("pages") or []:
        row["verdict"] = row["verdict"] or "SUPPORTED"
    for row in r.get("prior_issues") or []:
        row.update(status="FIXED", evidence="测试：已对照修订页", evidence_refs=[t["brief"]["pages"][0]["page"]["id"]])
    r["viewed_source_pages"] = list(t["brief"]["must_view_source_pages"])
    if edit:
        edit(r)
    return r


def semantic_review(store, wid, workers=("reviewer-B", "reviewer-C"), edit=None):
    """Both independent checklists, all clear unless `edit` changes a result (edit(check, result))."""
    store.queue(wid, "SEMANTIC_REVIEW")
    w = None
    for worker in workers:
        t = store.claim(wid, worker, "SEMANTIC_REVIEW")
        if not t:
            break
        w = store.complete(wid, t["id"], t["lease_token"], all_clear(t, (lambda r, c=t["binding"]: edit(c, r)) if edit else None))
    return w or store.get(wid)


def test_semantic_review_must_be_independent_and_blocks_on_issues(store):
    w = to_deck(store)
    store.queue(w["id"], "SEMANTIC_REVIEW")
    assert store.claim(w["id"], "author-A", "SEMANTIC_REVIEW") is None      # the author is never handed the review
    t = store.claim(w["id"], "reviewer-B", "SEMANTIC_REVIEW")
    assert t["binding"] == "COVERAGE" and t["brief"]["regression"]["mode"] == "FULL"
    assert any(f["dropped_from_quote"] == "" for p in t["brief"]["pages"] for f in p["facts"])
    page = t["brief"]["pages"][2]["page"]["id"]

    def flag(r):
        r["pages"][2] = {"page_id": page, "verdict": "ISSUES", "issues": [{
            "severity": "BLOCKER", "category": "CONTENT_ERROR", "ref": "x.prev", "source_ref": "overview.txt 第1段",
            "evidence": "页面只显示患病率", "problem": "节选未说明患病率的统计人群", "suggestion": "补出人群"}]}
    w = store.complete(w["id"], t["id"], t["lease_token"], all_clear(t, flag))
    assert store.claim(w["id"], "reviewer-B", "SEMANTIC_REVIEW") is None    # the second checklist needs another identity
    t = store.claim(w["id"], "reviewer-C", "SEMANTIC_REVIEW")
    assert t["binding"] == "RELATIONS" and any(r["kind"] == "grouping" for r in t["brief"]["relations"])
    w = store.complete(w["id"], t["id"], t["lease_token"], all_clear(t))
    assert "语义审查有 1 个阻断问题" in " ".join(w["open_items"])
    issue = w["issue_ledger"]["semantic"]["issues"][0]
    assert issue["id"] == "SEM-0001" and issue["ref"] == "x.prev" and issue["check"] == "COVERAGE"
    w = store.dismiss_issue(w["id"], "SEM-0001", {"reviewer": "TEST-REVIEWER", "reason": "来源原文即为成人患病率，页面已写明成人"})
    assert "语义审查" not in " ".join(w["open_items"])
    assert w["semantic_review"]["dismissed"]["SEM-0001"]["reviewer"] == "TEST-REVIEWER"


def finish_gates(store, w):
    w = semantic_review(store, w["id"])
    assert w["stage"] == "CONFIRMATIONS_REQUIRED", w["open_items"]
    with pytest.raises(WorkflowError, match="正式渲染前"):
        store.render(w["id"])
    w = store.resolve_conflict(w["id"], {"reviewer": "TEST-REVIEWER", "entity": "药物A", "attribute": "单价(元)", "fact_id": "price.a.ppt"})
    assert verified(w)["facts"]["price.a.xls"]["status"] == "REJECTED"
    # second, blind transcription by another worker
    store.queue(w["id"], "SECOND_READ")
    t = store.claim(w["id"], "reader-1", "SECOND_READ")
    assert "text" not in t["brief"]["cells"][0]
    with pytest.raises(WorkflowError, match="不同的执行端"):
        store.complete(w["id"], t["id"], t["lease_token"], {"source_sha256": t["brief"]["source"]["sha256"], "cells": [{"unit_id": "S03:s1:x.c1", "text": "缓解率38%"}]})
    store.fail(w["id"], t["id"], t["lease_token"], "same reader")
    t = store.claim(w["id"], "reader-2", "SECOND_READ")
    w = store.complete(w["id"], t["id"], t["lease_token"], {"source_sha256": t["brief"]["source"]["sha256"], "cells": [{"unit_id": "S03:s1:x.c1", "text": "缓解率 38%"}]})
    assert not verified(w)["facts"]["chart.a"]["needs_confirmation"]
    assert w["stage"] == "RENDER_REQUIRED", w["open_items"]
    return w


def test_full_mainline_to_delivery(store):
    pytest.importorskip("playwright")
    w = finish_gates(store, to_deck(store))
    w = store.render(w["id"])
    assert w["render"]["hard_errors"] == 0, w["render"]["summary"]
    assert w["render"]["summary"]["pending_confirmation"] == 0
    assert w["stage"] == "SAMPLES_REVIEW"
    rec = lambda p: {"reviewer": "TEST-REVIEWER", "png_sha256": p["sha256"], "sources_checked": True, "visual_status": "PASS", "content_status": "PASS"}
    for p in w["render"]["pages"][:5]:
        w = store.review(w["id"], p["id"], rec(p))
    assert w["stage"] == "STYLE_CONFIRMATION"
    w = approve(store, w, "style")
    for p in w["render"]["pages"][5:]:
        w = store.review(w["id"], p["id"], rec(p))
    assert w["stage"] == "READY_TO_EXPORT"
    w = store.export(w["id"])
    assert w["stage"] == "DELIVERED"
    d = w["deliveries"][-1]
    with zipfile.ZipFile(store.path(d["path"] + "/delivery.zip")) as z:
        names = z.namelist()
        assert {"deck.pptx", "deck.pdf", "facts_report.md", "verification_report.json"} <= set(names)
        from pptx import Presentation
        prs = Presentation(io.BytesIO(z.read("deck.pptx")))
        assert len(prs.slides) == 9
        notes = prs.slides[2].notes_slide.notes_text_frame.text
        assert "来源追溯" in notes and "overview.txt" in notes
        # complete-notes summary: the page's key points go verbatim into the speaker notes, before the provenance
        page = store.get(w["id"])["deck"]["result"]["pages"][2]
        kp = summary_key_points(store.get(w["id"]))
        assert notes.startswith("【讲稿】") and all(kp[k] in notes for k in page["key_point_ids"])
        assert notes.index("【讲稿】") < notes.index("来源追溯")
    # changing the requirements makes the deck, review and delivery stale
    w = store.settings(w["id"], {"requirements": {"audience": "护士", "target_pages": 12}})
    assert w["stage"] == "DECK_REQUIRED"


def test_visual_critique_is_independent_bound_to_the_images_and_never_reviews_pages(store):
    pytest.importorskip("playwright")
    w = store.render(finish_gates(store, to_deck(store))["id"])
    store.queue(w["id"], "VISUAL_CRITIQUE")
    t = store.claim(w["id"], w["deck"]["author"], "VISUAL_CRITIQUE")
    brief = t["brief"]
    assert all(Path(p["png"]).exists() and "design" in p and "signals" in p for p in brief["pages"])
    r = copy.deepcopy(brief["result_contract"])
    with pytest.raises(WorkflowError, match="页面作者之外"):
        store.complete(w["id"], t["id"], t["lease_token"], r)
    store.fail(w["id"], t["id"], t["lease_token"], "author cannot critique")
    t = store.claim(w["id"], "critic-C", "VISUAL_CRITIQUE")
    first = r["pages"][0]["page_id"]
    r["pages"][0]["rubric"]["whitespace"] = "REVISE"
    with pytest.raises(WorkflowError, match="具体修改意见"):
        store.complete(w["id"], t["id"], t["lease_token"], r)
    r["pages"][0]["fixes"] = ["下半部空白：把相邻的研究说明并入本页"]
    bad = copy.deepcopy(r)
    bad["pages"][1]["png_sha256"] = "0" * 64
    with pytest.raises(WorkflowError, match="不是当前版本"):
        store.complete(w["id"], t["id"], t["lease_token"], bad)
    w = store.complete(w["id"], t["id"], t["lease_token"], r)
    assert w["critique"]["revise"] == [first] and w["page_reviews"] == {}
    # the page author sees what to revise; a human review with a rubric item marked cannot pass the page
    store.queue(w["id"], "DECK")
    deck_brief = store.claim(w["id"], "author-A2", "DECK")["brief"]
    assert deck_brief["visual_critique"][first]["fixes"]
    p = w["render"]["pages"][0]
    with pytest.raises(WorkflowError, match="评分项"):
        store.review(w["id"], p["id"], {"reviewer": "R", "png_sha256": p["sha256"], "sources_checked": True, "visual_status": "PASS",
                                        "content_status": "PASS", "rubric": {"whitespace": "REVISE"}})


def test_draft_render_is_not_reviewable(store):
    pytest.importorskip("playwright")
    w = to_deck(store)
    w = store.render(w["id"], draft=True)
    assert w["draft_render"]["summary"]["pending_confirmation"] > 0
    assert w["render"] is None
    p = w["draft_render"]["pages"][0]
    with pytest.raises(WorkflowError, match="正式渲染"):
        store.review(w["id"], p["id"], {"reviewer": "R", "png_sha256": p["sha256"], "sources_checked": True, "visual_status": "PASS", "content_status": "PASS"})


def test_changing_sources_invalidates_everything_downstream(store):
    w = to_deck(store)
    w = store.add_source(w["id"], "extra.md", "# 追加\n\n追加的虚构资料。".encode())
    assert w["stage"] == "READING_REQUIRED"
    assert all(t["status"] != "PENDING" or t["kind"] == "READ_SOURCE" for t in w["tasks"])


def test_api_routes_are_mounted(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app.deckflow_api as api
    from app.main import app
    monkeypatch.setattr(api, "store", Store(tmp_path / "api-data"))
    c = TestClient(app)
    assert c.get("/api/deck/health").json()["mainline"] is True
    r = c.post("/api/deck/workflows", json={"title": "接口", "outline": "条目", "requirements": {"target_pages": 5, "audience": "学生"}})
    assert r.status_code == 201
    wid = r.json()["id"]
    r = c.post(f"/api/deck/workflows/{wid}/sources", files={"file": ("a.docx", fx_.docx_source())})
    assert r.status_code == 200 and r.json()["sources"][0]["id"] == "S01"
    assert c.post(f"/api/deck/workflows/{wid}/tasks", json={"kind": "FACTS"}).status_code == 409
    assert c.post("/api/deck/workflows", json={"title": "x", "requirements": {"bogus": 1}}).status_code == 422
    assert c.post("/api/deck/workflows", json={"title": "x", "theme": "neon"}).status_code == 422


def test_home_serves_the_tabler_ui_and_its_assets():
    import re
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    home = c.get("/")
    assert home.status_code == 200 and "FactDeck" in home.text
    assets = re.findall(r'(?:href|src)="(/web/[^"]+)"', home.text)
    paths = [a.split("?")[0] for a in assets]               # scripts carry a cache-busting version
    assert "/web/vendor/tabler/tabler.min.css" in paths and "/web/deck/app.js" in paths
    for path in assets:
        assert c.get(path).status_code == 200, path


def test_render_endpoint_runs_inside_the_server(tmp_path, monkeypatch):
    pytest.importorskip("playwright")
    from fastapi.testclient import TestClient
    import app.deckflow_api as api
    from app.main import app
    s = Store(tmp_path / "api-render")
    monkeypatch.setattr(api, "store", s)
    w = to_deck(s)
    c = TestClient(app)
    r = c.post(f"/api/deck/workflows/{w['id']}/render", params={"draft": "true"})
    assert r.status_code == 200, r.text
    first = r.json()["draft_render"]["pages"][0]["file"]
    png = c.get(f"/api/deck/workflows/{w['id']}/render/draft/{first}")
    assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
    assert c.get(f"/api/deck/workflows/{w['id']}/render/draft/..%2Fsecret").status_code == 404


def test_confirmation_draft_quotes_key_point_evidence(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app.deckflow_api as api
    from app.main import app
    s = Store(tmp_path / "api-draft")
    monkeypatch.setattr(api, "store", s)
    w = s.create("确认稿", OUTLINE)
    for name, make in fx_.SOURCES.items():
        s.add_source(w["id"], name, make())
    w = read_all(s, w["id"])
    w = run_task(s, w["id"], "SUMMARY", "author-A", lambda t: summary(w))
    text = TestClient(app).get(f"/api/deck/workflows/{w['id']}/confirmation-draft").text
    k = w["summary"]["sections"][0]["key_points"][0]
    u = next(u for x in w["sources"] for u in x["units"] if u["id"] == k["unit_ids"][0])
    assert f"要点：{k['point']}" in text and " ".join(u["text"].split()) in text
