"""Structure first: the course's whole structure is settled, independently reviewed and confirmed before any
chapter-level work (2026-10-14, validated on a copy before wider use; enabled per project by `structure_first`).

STRUCTURE         the author designs a course question and a teaching arc of 3–10 sections. Each section answers one
                  learner question, has a core sentence quoted from a source claim, owns its source pages and a page
                  budget set by teaching importance; links between sections (prerequisite / leads to / contrast /
                  elaborates) rest on claims; pages that do not serve the course are marked reference-only.
STRUCTURE_REVIEW  an independent reviewer judges the structure as a whole (coherent argument for the audience,
                  missing links, weighting) and restates the course argument from the structure alone.
confirmation      the customer confirms the structure (approval kind "structure").
SUMMARY and DECK then work inside the confirmed structure.

Code checks completeness and provenance; whether the arc teaches well is the reviewer's and the customer's call.
"""
from __future__ import annotations

import re

from app.fact57098 import digest, now, require

SCHEMA = "course_structure.v1"
REVIEW_SCHEMA = "course_structure_review.v1"
LINK_TYPES = {"prerequisite": "前提：先懂前一部分才能懂这一部分", "leads_to": "引出：前一部分的结论引出这一部分的问题",
              "contrast": "对照：两部分讲的情形相互对照", "elaborates": "展开：这一部分细化前一部分的某一点"}
REFERENCE_REASONS = {"abbreviations": "缩略词表", "references": "参考文献", "administrative": "出版、版权与编写方法等行政信息",
                     "out_of_scope": "超出本课受众与目的（须写明）"}
SECTIONS = (3, 10)
BUDGET_SLACK = 0.15


def _d():
    import app.deckflow as d
    return d


def structure_input(w: dict) -> str:
    return digest({"claims": _d().input_hash(w, structure=False), "requirements": w.get("requirements")})


def structure_current(w: dict) -> bool:
    s = w.get("structure")
    return bool(s) and s.get("input_sha256") == structure_input(w)


def review_input(w: dict) -> str:
    return digest({"structure": digest(w["structure"]["result"]), "input": structure_input(w), "schema": REVIEW_SCHEMA})


def review_current(w: dict) -> bool:
    r = w.get("structure_review")
    return structure_current(w) and bool(r) and r.get("input_sha256") == review_input(w)


def review_blockers(w: dict) -> list[str]:
    if not review_current(w):
        return []
    return list(w["structure_review"].get("blockers") or [])


def approved(w: dict) -> bool:
    a = w.get("structure_approval")
    return structure_current(w) and bool(a) and a["subject_sha256"] == digest(w["structure"]["result"])


def gate(w: dict):
    """(stage, items) when a structure-first project has not yet a confirmed structure, else None."""
    if not w.get("structure_first"):
        return None
    if not structure_current(w): return "STRUCTURE_REQUIRED", ["需要当前版本的课程整体结构（主线、部分、页数分配）"]
    if not review_current(w): return "STRUCTURE_REVIEW_REQUIRED", ["课程整体结构需要独立审查"]
    if review_blockers(w): return "STRUCTURE_ISSUES", ["结构审查有问题，须修订结构：" + "；".join(review_blockers(w)[:3])]
    if not approved(w): return "STRUCTURE_CONFIRMATION", ["客户尚未确认课程整体结构"]
    return None


def _pages(w):
    return [(s, p) for s in w["sources"] for p in s["pages"]]


def brief(w: dict) -> dict:
    d = _d()
    claims = d.all_claims(w)
    by_page = {}
    for c in claims.values():
        by_page.setdefault(c["page_id"], []).append(c)
    req = w.get("requirements") or {}
    return {"kind": "STRUCTURE", "requirements": req, "outline": [{"id": o["id"], "text": o["text"]} for o in w["outline"]],
            "sources": [{"id": s["id"], "title": s["title"], "profile": (s.get("claims") or {}).get("profile"),
                         "pages": [{"id": p["id"], "location": p["location"], "classification": (p.get("reading") or {}).get("classification"),
                                    "titles": sorted({t for u in s["units"] if u["page_id"] == p["id"] for t in (u.get("signals") or {}).get("title") or []}),
                                    "claims": [d.claim_view(k) for k in by_page.get(p["id"], [])]} for p in s["pages"]]} for s in w["sources"]],
            "link_types": LINK_TYPES, "reference_reasons": REFERENCE_REASONS,
            "rules": ["目标：为这门课（受众、目的、目标页数见 requirements）设计整体结构——一个课程核心问题，以及由 3–10 个部分组成的教学主线。"
                      "学习者按顺序学完，应能从头到尾复述课程的论证：每一部分回答一个学习者的问题，并以一句出自资料的论断作为核心句。",
                      "按教学重要性分配页数（page_budget 总和接近目标页数，偏差不超过15%），不按资料篇幅；资料的章节顺序只是参考，可以合并、拆分或重排。",
                      "部分之间的联系 links：除第一个部分外，每个部分至少有一条来自前面某个部分的联系（type 取自 link_types），列出支撑它的论断 claim_ids。",
                      "每个资料页恰好归入一个部分，或在 reference_only 中标为参考（原因取自 reference_reasons，out_of_scope 须写明）；"
                      "每个提纲条目（outline）出现在某个部分或某条 reference_only 的 outline_ids 中。",
                      "course_question、各部分 title 与 question 是作者文字：只提问和组织，不写数字、比较、药名或评价；内容由核心句和资料承担。"],
            "result_contract": {"schema_version": SCHEMA, "input_sha256": structure_input(w), "course_question": "",
                                "sections": [{"id": "a1", "title": "", "question": "", "core": {"claim_id": ""}, "source_page_ids": [],
                                              "outline_ids": [], "page_budget": 0}],
                                "links": [], "reference_only": []}}


def accept(w: dict, result: dict, author: str) -> None:
    d = _d()
    require(w.get("structure_first"), "本项目未启用“先定整体结构”", 409)
    require(d.fully_claimed(w), "全部资料完成阅读和论断清单后才能提交课程结构")
    require(isinstance(result, dict) and result.get("schema_version") == SCHEMA, f"课程结构版本须为 {SCHEMA}", 422)
    require(result.get("input_sha256") == structure_input(w), "课程结构对应的资料或需求已过期")
    authored = lambda t: isinstance(t, str) and 2 <= len(t.strip()) <= 120 and not re.search(r"\d", t)
    require(authored(result.get("course_question")), "课程核心问题须为120字以内的作者文字，不含数字", 422)
    secs = result.get("sections")
    require(isinstance(secs, list) and SECTIONS[0] <= len(secs) <= SECTIONS[1], f"教学主线须有 {SECTIONS[0]}–{SECTIONS[1]} 个部分", 422)
    ids = [s.get("id") for s in secs if isinstance(s, dict)]
    require(len(ids) == len(secs) and all(isinstance(i, str) and i for i in ids) and len(set(ids)) == len(ids), "部分编号不能为空或重复", 422)
    claims = d.all_claims(w)
    known_pages = {p["id"] for _, p in _pages(w)}
    outline_ids = {o["id"] for o in w["outline"]}
    seen_pages, seen_outline, total = [], set(), 0
    for s in secs:
        sid = s["id"]
        require(authored(s.get("title")) and authored(s.get("question")), f"部分 {sid} 的 title 与 question 须为作者文字，不含数字", 422)
        pages = s.get("source_page_ids")
        require(isinstance(pages, list) and pages and set(pages) <= known_pages, f"部分 {sid} 须列出它的资料页", 422)
        core = (s.get("core") or {}).get("claim_id")
        require(core in claims, f"部分 {sid} 的核心句须指向存在的论断（core.claim_id）", 422)
        require(claims[core]["page_id"] in pages, f"部分 {sid} 的核心句须来自本部分的资料页", 422)
        budget = s.get("page_budget")
        require(isinstance(budget, int) and not isinstance(budget, bool) and budget >= 1, f"部分 {sid} 须给出页数 page_budget（≥1）", 422)
        ol = s.get("outline_ids") or []
        require(isinstance(ol, list) and set(ol) <= outline_ids, f"部分 {sid} 的 outline_ids 须是提纲条目", 422)
        seen_pages += pages; seen_outline |= set(ol); total += budget
    for r in result.get("reference_only") or []:
        require(isinstance(r, dict) and r.get("reason") in REFERENCE_REASONS, "reference_only 的原因须取自 reference_reasons", 422)
        if r["reason"] == "out_of_scope":
            require(len(str(r.get("note", "")).strip()) >= 4, "标为 out_of_scope 时须在 note 写明为何超出本课范围", 422)
        pages = r.get("source_page_ids")
        require(isinstance(pages, list) and pages and set(pages) <= known_pages, "reference_only 须列出资料页", 422)
        seen_pages += pages; seen_outline |= set(r.get("outline_ids") or [])
    dup = sorted({p for p in seen_pages if seen_pages.count(p) > 1})
    require(not dup, "以下资料页被归入多处：" + "、".join(dup[:10]), 422)
    missing = sorted(known_pages - set(seen_pages))
    require(not missing, f"以下资料页未归入任何部分或参考：{'、'.join(missing[:10])}（共 {len(missing)} 页）", 422)
    require(outline_ids <= seen_outline, "以下提纲条目未出现在结构中：" + "、".join(sorted(outline_ids - seen_outline)), 422)
    target = (w.get("requirements") or {}).get("target_pages")
    if target:
        require(abs(total - target) <= max(1, round(target * BUDGET_SLACK)), f"页数分配合计 {total} 页，与目标 {target} 页偏差超过15%", 422)
    order = {sid: i for i, sid in enumerate(ids)}
    links = result.get("links")
    require(isinstance(links, list), "links 须为列表", 422)
    incoming = set()
    for i, l in enumerate(links, 1):
        require(isinstance(l, dict) and l.get("from") in order and l.get("to") in order and l["from"] != l["to"],
                f"第{i}条联系须连接两个不同的部分（from / to）", 422)
        require(l.get("type") in LINK_TYPES, f"第{i}条联系的类型须取自 link_types", 422)
        cids = l.get("claim_ids")
        require(isinstance(cids, list) and cids and all(c in claims for c in cids), f"第{i}条联系须列出支撑它的论断（claim_ids）", 422)
        if order[l["from"]] < order[l["to"]]:
            incoming.add(l["to"])
    loose = [sid for sid in ids[1:] if sid not in incoming]
    require(not loose, "以下部分没有来自前面部分的联系，主线在此断开：" + "、".join(loose), 422)
    w["structure"] = {"result": result, "input_sha256": structure_input(w), "author": author, "at": now()}
    w["structure_approval"] = None
    w["structure_review"] = None


def review_brief(w: dict) -> dict:
    d = _d()
    s = w["structure"]["result"]
    claims = d.all_claims(w)
    count = {}
    for c in claims.values():
        count.setdefault(c["page_id"], {}).setdefault(c["type"], 0)
        count[c["page_id"]][c["type"]] += 1
    def weight(pages):
        out = {}
        for p in pages:
            for k, v in count.get(p, {}).items():
                out[k] = out.get(k, 0) + v
        return out
    text = lambda cid: d.claim_view(claims[cid])["text"] if cid in claims else "（论断不存在）"
    return {"kind": "STRUCTURE_REVIEW", "requirements": w.get("requirements"), "course_question": s["course_question"],
            "sections": [{**{k: x[k] for k in ("id", "title", "question", "page_budget", "source_page_ids", "outline_ids")},
                          "core": text(x["core"]["claim_id"]), "claims_by_type_on_pages": weight(x["source_page_ids"])} for x in s["sections"]],
            "links": [{**l, "claims": [text(c) for c in l["claim_ids"]]} for l in s["links"]],
            "reference_only": s.get("reference_only") or [], "link_types": LINK_TYPES,
            "rules": ["独立审查整体结构，不逐条核对要点。只看这份结构：先在 restated 中用自己的话复述这门课从头到尾的论证（至少两三句）。",
                      "verdict：COHERENT（对目标受众是一条连贯的论证，能按目的教会他们）或 REVISE。",
                      "sections：逐个判断 OK / ISSUE——问题是否是学习者需要回答的，核心句是否真是该部分最重要的一句，资料页归属是否合理；ISSUE 写明原因。",
                      "links：逐条判断 SUPPORTED（所引论断支持这条联系及方向）/ UNSUPPORTED；missing_links 列出缺少的重要联系 {from, to, reason}。",
                      "weighting：页数分配是否符合教学重要性（OK / ISSUE），对照 claims_by_type_on_pages 与 requirements；reference_only 是否把需要讲的内容排除了。",
                      "审查人须不同于结构作者和论断清单作者。"],
            "result_contract": {"schema_version": REVIEW_SCHEMA, "input_sha256": review_input(w), "restated": "", "verdict": "",
                                "sections": [{"id": x["id"], "verdict": "", "issue": ""} for x in s["sections"]],
                                "links": [{"index": i, "verdict": "", "issue": ""} for i in range(1, len(s["links"]) + 1)],
                                "missing_links": [], "weighting": {"verdict": "", "issue": ""}}}


def accept_review(w: dict, result: dict, reviewer: str) -> None:
    require(structure_current(w), "没有当前版本的课程结构")
    require(reviewer not in {w["structure"]["author"]} | {(s.get("claims") or {}).get("reader") for s in w["sources"]},
            "结构审查须由结构作者和论断清单作者之外的执行端完成", 422)
    require(isinstance(result, dict) and result.get("schema_version") == REVIEW_SCHEMA and result.get("input_sha256") == review_input(w),
            "结构审查对应的结构已过期", 422)
    require(len(str(result.get("restated", "")).strip()) >= 20, "须先复述这门课的论证（restated）", 422)
    require(result.get("verdict") in {"COHERENT", "REVISE"}, "verdict 须为 COHERENT 或 REVISE", 422)
    s = w["structure"]["result"]
    blockers = []
    rows = {r.get("id"): r for r in result.get("sections") or [] if isinstance(r, dict)}
    require(set(rows) == {x["id"] for x in s["sections"]}, "须逐个判断全部部分", 422)
    for sid, r in rows.items():
        require(r.get("verdict") in {"OK", "ISSUE"}, f"部分 {sid} 的结论须为 OK / ISSUE", 422)
        if r["verdict"] == "ISSUE":
            require(str(r.get("issue", "")).strip(), f"部分 {sid} 判为 ISSUE 时须写明问题", 422)
            blockers.append(f"{sid}：{r['issue']}")
    links = {r.get("index"): r for r in result.get("links") or [] if isinstance(r, dict)}
    require(set(links) == set(range(1, len(s["links"]) + 1)), "须逐条判断全部联系", 422)
    for i, r in links.items():
        require(r.get("verdict") in {"SUPPORTED", "UNSUPPORTED"}, f"第{i}条联系的结论须为 SUPPORTED / UNSUPPORTED", 422)
        if r["verdict"] == "UNSUPPORTED":
            require(str(r.get("issue", "")).strip(), f"第{i}条联系判为 UNSUPPORTED 时须写明问题", 422)
            blockers.append(f"联系{i}：{r['issue']}")
    wt = result.get("weighting") or {}
    require(wt.get("verdict") in {"OK", "ISSUE"}, "weighting 的结论须为 OK / ISSUE", 422)
    if wt["verdict"] == "ISSUE":
        require(str(wt.get("issue", "")).strip(), "weighting 判为 ISSUE 时须写明问题", 422)
        blockers.append("页数分配：" + wt["issue"])
    missing = result.get("missing_links") or []
    require(isinstance(missing, list) and all(isinstance(m, dict) and str(m.get("reason", "")).strip() for m in missing), "missing_links 每项须写明原因", 422)
    blockers += [f"缺少联系 {m.get('from')}→{m.get('to')}：{m['reason']}" for m in missing]
    if result["verdict"] == "REVISE" and not blockers:
        blockers.append("审查人判定整体须修订：" + str(result.get("restated"))[:200])
    w["structure_review"] = {"input_sha256": review_input(w), "reviewer": reviewer, "at": now(), "verdict": result["verdict"],
                             "restated": result["restated"], "blockers": blockers, "result": result}


def story(w: dict) -> list[str]:
    """The course's line of argument from the structure: question, each section's question and core, and its links."""
    d = _d()
    s = w["structure"]["result"]
    claims = d.all_claims(w)
    out = [f"课程问题：{s['course_question']}"]
    for i, x in enumerate(s["sections"], 1):
        quote = d.claim_view(claims[x["core"]["claim_id"]])["text"] if x["core"]["claim_id"] in claims else ""
        inbound = [f"{l['from']}{LINK_TYPES[l['type']].split('：')[0]}" for l in s["links"] if l["to"] == x["id"]]
        out.append(f"{i}. {x['title']}（{x['page_budget']}页）｜{x['question']}｜「{quote}」" + (f"｜承接：{'、'.join(inbound)}" if inbound else ""))
    return out


def summary_checks(w: dict, sections: list[dict]) -> None:
    """A summary written inside a confirmed structure: one chapter per structure section, in order, on the section's
    pages, with the section's core sentence; reference-only pages may form trailing chapters without key points."""
    if not (w.get("structure_first") and approved(w)):
        return
    arc = w["structure"]["result"]["sections"]
    require([s.get("id") for s in sections[:len(arc)]] == [x["id"] for x in arc], "总结章节须与已确认结构的部分一一对应、同序（id 相同）", 422)
    for s, x in zip(sections, arc):
        require(set(s.get("source_page_ids") or []) == set(x["source_page_ids"]), f"章节 {s['id']} 的资料页须与结构中该部分一致", 422)
        core = ((s.get("message") or {}).get("core") or {}).get("claim_id")
        require(core == x["core"]["claim_id"], f"章节 {s['id']} 的核心句须是结构中确认的核心句 {x['core']['claim_id']}", 422)
    ref_pages = {p for r in w["structure"]["result"].get("reference_only") or [] for p in r["source_page_ids"]}
    for s in sections[len(arc):]:
        require(set(s.get("source_page_ids") or []) <= ref_pages and not s.get("key_points"),
                f"结构外的章节 {s['id']} 只能收录标为参考的资料页，且不写要点", 422)
