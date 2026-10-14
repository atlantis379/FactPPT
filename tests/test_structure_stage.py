"""Structure first: the course structure is written, independently reviewed and confirmed before the summary, and the
summary then follows it. Fixture data are invented; they are not real reviews or approvals."""
import copy

import pytest

import test_deckflow as T
from test_deckflow import store  # noqa: F401  (fixture)
from app.deckflow import WorkflowError, all_claims, story_line


def claimed(store):
    w = store.create("结构优先", T.OUTLINE, {"audience": "本科生"})
    for name, make in T.fx_.SOURCES.items():
        store.add_source(w["id"], name, make())
    T.read_all(store, w["id"])
    return store.settings(w["id"], {"structure_first": True})


def structure_result(w, contract):
    """Three sections over the sources' pages, each with a core claim on its own pages, linked in order."""
    pages = [p["id"] for s in w["sources"] for p in s["pages"]]
    claims = all_claims(w)
    by_page = {}
    for c in claims.values():
        by_page.setdefault(c["page_id"], []).append(c["id"])
    with_claims = [p for p in pages if by_page.get(p)]
    cut = [with_claims[0], with_claims[len(with_claims) // 2], with_claims[-1]]
    groups, current = [[], [], []], 0
    for p in pages:
        if current < 2 and p == cut[current + 1]:
            current += 1
        groups[current].append(p)
    r = copy.deepcopy(contract)
    r["course_question"] = "学习者应如何理解这门课的主线"
    r["sections"] = [{"id": f"a{i}", "title": f"第{'一二三'[i - 1]}部分", "question": "这一部分要回答什么问题", "core": {"claim_id": by_page[cut[i - 1]][0]},
                      "source_page_ids": g, "outline_ids": [w["outline"][i - 1]["id"]] if i <= len(w["outline"]) else [], "page_budget": 3}
                     for i, g in enumerate(groups, 1)]
    for o in w["outline"][3:]:
        r["sections"][-1]["outline_ids"].append(o["id"])
    r["links"] = [{"from": "a1", "to": "a2", "type": "leads_to", "claim_ids": [by_page[cut[1]][0]]},
                  {"from": "a2", "to": "a3", "type": "prerequisite", "claim_ids": [by_page[cut[2]][0]]}]
    return r


def write_structure(store, wid, change=None):
    store.queue(wid, "STRUCTURE")
    t = store.claim(wid, "author-S", "STRUCTURE")
    r = structure_result(store.get(wid), t["brief"]["result_contract"])
    if change:
        change(r)
    return store.complete(wid, t["id"], t["lease_token"], r)


def review(store, wid, worker="reviewer-R", verdict="COHERENT", edit=None):
    store.queue(wid, "STRUCTURE_REVIEW")
    t = store.claim(wid, worker, "STRUCTURE_REVIEW")
    assert t, "review task"
    r = copy.deepcopy(t["brief"]["result_contract"])
    assert r["verdict"] == "" and all(x["verdict"] == "" for x in r["sections"])              # nothing passes by default
    r.update(restated="TEST：先认识问题，再学会判断，最后掌握处理，三部分前后承接。", verdict=verdict, weighting={"verdict": "OK", "issue": ""})
    for x in r["sections"]: x["verdict"] = "OK"
    for x in r["links"]: x["verdict"] = "SUPPORTED"
    if edit:
        edit(r)
    return store.complete(wid, t["id"], t["lease_token"], r)


def approve_structure(store, w):
    return store.approval(w["id"], "structure", {"customer": "TEST-CUSTOMER", "operator": "TEST-OPERATOR",
                                                 "method": "AUTOMATED_PROTOCOL_TEST_NOT_REAL_APPROVAL", "subject_sha256": w["approval_subjects"]["structure"]})


@pytest.mark.parametrize("change, message", [
    (lambda r: r["sections"][1]["source_page_ids"].pop(), "未归入"),
    (lambda r: r.update(links=r["links"][:1]), "主线在此断开"),
    (lambda r: r["sections"][0]["core"].update(claim_id=r["sections"][2]["core"]["claim_id"]), "本部分的资料页"),
    (lambda r: r["sections"][0].update(question="第3个问题"), "不含数字"),
])
def test_structure_is_complete_connected_and_grounded(store, change, message):
    w = claimed(store)
    assert w["stage"] == "STRUCTURE_REQUIRED"
    with pytest.raises(WorkflowError, match=message):
        write_structure(store, w["id"], change)


def test_structure_is_reviewed_independently_confirmed_and_then_shapes_the_summary(store):
    w = claimed(store)
    with pytest.raises(WorkflowError, match="独立审查与客户确认"):
        store.queue(w["id"], "SUMMARY")
    w = write_structure(store, w["id"])
    assert w["stage"] == "STRUCTURE_REVIEW_REQUIRED" and story_line(w)[0].startswith("课程问题")
    store.queue(w["id"], "STRUCTURE_REVIEW")
    assert store.claim(w["id"], "author-S", "STRUCTURE_REVIEW") is None                      # never the structure's author
    t = store.claim(w["id"], "reviewer-R", "STRUCTURE_REVIEW")
    store.fail(w["id"], t["id"], t["lease_token"], "TEST: hand back")
    w = review(store, w["id"], edit=lambda r: r["links"][0].update(verdict="UNSUPPORTED", issue="TEST：所引论断不支持这一承接"))
    assert w["stage"] == "STRUCTURE_ISSUES"
    with pytest.raises(WorkflowError, match="结构审查"):
        approve_structure(store, w)
    w = write_structure(store, w["id"], lambda r: r.update(course_question="学习者应如何理解这门课的完整主线"))   # revised structure
    w = review(store, w["id"])
    assert w["stage"] == "STRUCTURE_CONFIRMATION"
    w = approve_structure(store, w)
    assert w["stage"] == "SUMMARY_REQUIRED"
    store.queue(w["id"], "SUMMARY")
    t = store.claim(w["id"], "author-A", "SUMMARY")
    assert t["brief"]["structure"]["sections"] and any("已确认的课程结构" in r for r in t["brief"]["rules"])
    sections = []
    for x in w["structure"]["result"]["sections"]:
        core = x["core"]["claim_id"]
        sec = {"id": x["id"], "title": x["title"], "summary": "TEST：本部分按已确认结构组织的总结文字，保留限定条件。", "source_page_ids": x["source_page_ids"],
               "key_points": [{"point": "TEST 要点", "claim_ids": [core]}],
               "message": {"core": {"claim_id": core}, "roles": {f"{x['id']}.k1": "core"}, "relations": [],
                           "candidate_decisions": T.candidate_decisions(w, x["source_page_ids"])}}
        sections.append(sec)
    good = {"schema_version": "full_source_summary.v3", "input_sha256": t["brief"]["result_contract"]["input_sha256"],
            "overall_summary": "TEST：按已确认的课程结构撰写的全文总结，覆盖全部资料页，保留人群、阈值与限定条件，并说明各部分之间如何承接。", "sections": sections,
            "outline_coverage": [{"outline_id": o["id"], "section_ids": [next(x["id"] for x in w["structure"]["result"]["sections"] if o["id"] in x["outline_ids"])]}
                                 for o in w["outline"]], "pending_issues": []}
    T.with_understanding(w, good)
    swapped = copy.deepcopy(good); swapped["sections"][0]["message"]["core"]["claim_id"] = sections[1]["message"]["core"]["claim_id"]
    swapped["sections"][0]["key_points"][0]["claim_ids"] = [sections[1]["message"]["core"]["claim_id"]]
    with pytest.raises(WorkflowError):
        store.complete(w["id"], t["id"], t["lease_token"], swapped)
    w = store.complete(w["id"], t["id"], t["lease_token"], good)
    assert w["stage"] == "SUMMARY_REVIEW_REQUIRED"
    # changing the confirmed structure makes the summary stale
    w = write_structure(store, w["id"], lambda r: r.update(course_question="学习者如何把握这门课的主线与边界"))
    assert w["stage"] == "STRUCTURE_REVIEW_REQUIRED"


def test_projects_without_the_switch_are_unchanged(store):
    w = store.create("普通项目", T.OUTLINE)
    assert not w.get("structure_first")
    for name, make in T.fx_.SOURCES.items():
        store.add_source(w["id"], name, make())
    w = T.read_all(store, w["id"])
    assert w["stage"] == "SUMMARY_REQUIRED"
    with pytest.raises(WorkflowError, match="未启用"):
        store.queue(w["id"], "STRUCTURE")


def test_structure_first_switch_is_guarded_and_recorded(store):
    from test_outline_structure import OUTLINE as POINTS_OUTLINE
    w = store.create("提纲带要点", POINTS_OUTLINE)
    with pytest.raises(WorkflowError, match="提纲带要点"):
        store.settings(w["id"], {"structure_first": True})
    w = claimed(store)
    assert w["settings_history"][-1]["structure_first"] is True and w["settings_history"][-1]["had_summary"] is False
