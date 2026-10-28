"""Semantic-first content route (2026-10-27; per project `semantic_map_first`, on for new projects via the API).

The model understands, code keeps the sources exact:

READ_SOURCE / SECOND_READ  as before: text layer by code, pictures transcribed by workers.
SEMANTIC_MAP  a model reads every page and names the material's topics in speaking order (role, one-sentence thesis,
              the units each rests on, main line, page budget) and the links between them. Code checks the schema,
              that every unit hint is real and that every substantive page is covered.
claims        code cuts every unit into verbatim sentences (`factdeck.auto_claims`) and attaches each to the topic that
              names its unit — no model task.
exclusions    the customer's decisions that rule material out ("this page is not used", "this number is wrong") are
              recorded as rules (`exclusions`); code marks the matching sentences excluded — they are not shown to the
              model and a result citing one is refused.
TOPIC_PASS    one task per topic: a model reads all of the topic's sentences (table cells with their row and column
              headers) and decides the question, the messages (core / support / limit on the pages, reserve for the
              notes) with the sentence ids that state them, the relations, the page plan, what to check, what is left
              out and why, and the gaps (`factdeck.topic_pass`). Code refuses unknown or excluded ids and omissions
              without a reason, and reports signals for review.
draft         code assembles topics → messages → verbatim sentences (`draft`), and the same draft as a summary
              (`summary_view`, kept in w["summary"]) so the customer confirmation, the deck checks (every core and
              limit message on a page) and speaker notes work as for any confirmed summary.
confirmation  the customer confirms the draft; code then builds the fact store from the sentences the draft cites
              (`draft_facts`) — no FACTS task.
DECK          the model presents the confirmed draft page by page (`deck_brief`); code checks the facts as before.
"""
from __future__ import annotations

from app.fact57098 import digest, now, require
from factdeck import auto_claims, topic_pass
from factdeck.semantic_map import NODE_ROLES, SCHEMA_VERSION, STAGE, UNASSIGNED_NODE_ID, SemanticMapError, parse_semantic_map

SUMMARY_ALGORITHM = "topic_draft.v1"
FACTS_AUTHOR = "code:topic-draft"
RELATION_TYPES = {"sequence": "sequence", "contrast": "compare", "condition": "branch", "evidence": "evidence"}
PAGE_CHARS = 700          # text shown per page in the brief, spent on its units in order; every unit id is listed


def _d():
    import app.deckflow as d
    return d


def enabled(w: dict) -> bool:
    return bool(w.get("semantic_map_first"))


def semantic_map_input(w: dict) -> str:
    """What the map rests on: every source's readings and transcriptions, the outline and the requirements."""
    d = _d()
    return digest({"sources": [{"id": s["id"], "sha256": s["sha256"], "readings": [p["reading"] for p in s["pages"]],
                                "units": [(u["id"], u["text"]) for u in d.all_units(w) if u["page_id"] in {p["id"] for p in s["pages"]}]}
                               for s in w["sources"]],
                   "outline": w.get("outline"), "requirements": w.get("requirements"), "schema": SCHEMA_VERSION})


def semantic_map_current(w: dict) -> bool:
    m = w.get("semantic_map")
    return bool(m) and m.get("input_sha256") == semantic_map_input(w)


def nodes(w: dict) -> list[dict]:
    return list((w.get("semantic_map") or {}).get("result", {}).get("nodes") or [])


def gate(w: dict):
    """(stage, open items) of a semantic-first project once its sources are read; None for other projects."""
    if not enabled(w):
        return None
    if not semantic_map_current(w):
        return "SEMANTIC_MAP_REQUIRED", ["资料的语义地图尚未完成或已过期"]
    todo = [n["title"] for n in nodes(w) if not topic_current(w, n["id"])]
    if todo:
        return "TOPICS_REQUIRED", [f"{len(todo)} 个主题尚未梳理重点：" + "、".join(todo[:5])]
    if not _d().content_approved(w):
        pending = unconfirmed_sentences(w)
        return "CONTENT_CONFIRMATION", ["客户尚未确认初稿"] + ([f"初稿引用的 {len(pending)} 句图片/图表转录尚未核定"] if pending else [])
    return None


def brief(w: dict) -> dict:
    d = _d()
    by_page: dict[str, list] = {}
    for u in d.all_units(w):
        by_page.setdefault(u["page_id"], []).append(u)
    req = w.get("requirements") or {}
    return {"kind": STAGE, "schema_version": SCHEMA_VERSION, "input_sha256": semantic_map_input(w),
            "node_roles": sorted(NODE_ROLES),
            "sources": [{"id": s["id"], "title": s.get("title") or s.get("filename"),
                         "source_url": f"/api/deck/workflows/{w['id']}/sources/{s['id']}/file",
                         "pages": [{"id": p["id"], "location": p["location"], "classification": p["reading"]["classification"],
                                    "units": _page_units(by_page.get(p["id"], []))}
                                   for p in s["pages"]]} for s in w["sources"]],
            "rules": ["读完全部资料的全部页面，决定这批原始材料的整体结构：把内容划分为有序的语义节点 nodes，顺序即讲解顺序（不必照资料原顺序）。",
                      "每个节点：id 为不含空格的短编号；title 为一行标题；role 取自 node_roles；thesis 用一句话说明这一节点讲什么；"
                      "unit_hints 列出该节点依据的单元 id（只能用本合同 units 中的 id，不得虚构）；mainline 标出服务于 requirements 中受众与目的的主线节点（true），"
                      "其余为支线或参考（false）。",
                      "每个正文页（classification 为 SUBSTANTIVE）至少有一个单元出现在某个节点的 unit_hints 中；缩略词、参考文献等页可归入 role 为 other 的节点。",
                      "title、thesis、one_liner 是作者组织文字：不写数字（阿拉伯或全角），不写比较或评价结论；one_liner 与每个 thesis 各一句。",
                      f"禁止使用保留节点 id `{UNASSIGNED_NODE_ID}`。",
                      "edges 可选：from/to 为节点 id，relation 取自 sequence（先后）、contrast（对照）、condition（条件/分支）、evidence（证据支撑）。",
                      "pages 为每个节点的页数预算，按讲解重要性分配，不按资料篇幅；各节点之和接近 requirements.target_pages（未给出时按内容估计），"
                      "不上页的节点写 0。",
                      "每页只显示前若干字（标 cut 的单元被截断或未显示文字）；需要全文时按 source_url 查看原件。"],
            "requirements": req,
            "result_contract": {"input_sha256": semantic_map_input(w), "schema_version": SCHEMA_VERSION, "one_liner": "",
                                "nodes": [{"id": "n1", "title": "", "role": "other", "thesis": "", "unit_hints": [], "mainline": True, "pages": 0}],
                                "edges": []}}


def _page_units(units: list[dict]) -> list[dict]:
    """A page's units for the brief: text in order up to PAGE_CHARS (a page stored as one long unit shows its body,
    not only its running header); later units keep their id with the text left out."""
    left, out = PAGE_CHARS, []
    for u in units:
        text = " ".join(u["text"].split())
        shown = text[:max(left, 0)]
        left -= len(shown)
        out.append({"id": u["id"], "text": shown} | ({"cut": True} if len(shown) < len(text) else {})
                   | ({"signals": u["signals"]} if u.get("signals") else {}))
    return out


def accept(w: dict, result: dict, author: str) -> None:
    d = _d()
    require(enabled(w), "本项目未启用“先定语义地图”（设置 semantic_map_first）", 409)
    require(d.fully_read(w), "全部资料完成阅读后才能提交语义地图", 409)
    require(isinstance(result, dict), "语义地图结果须为对象", 422)
    require(result.get("input_sha256") == semantic_map_input(w), "语义地图对应的资料、阅读或转录已变更", 409)
    try:
        parsed = parse_semantic_map({k: v for k, v in result.items() if k != "input_sha256"})
    except SemanticMapError as e:
        raise d.WorkflowError(f"语义地图不合格：{e}", 422)
    units = {u["id"]: u for u in d.all_units(w)}
    unknown = sorted({h for n in parsed.nodes for h in n.unit_hints if h not in units})
    require(not unknown, "unit_hints 中有不存在的单元：" + "、".join(unknown[:10]), 422)
    hinted = {units[h]["page_id"] for n in parsed.nodes for h in n.unit_hints}
    missing = [p["location"] for s in w["sources"] for p in s["pages"]
               if p["reading"]["classification"] == "SUBSTANTIVE" and p["id"] not in hinted
               and any(u["page_id"] == p["id"] for u in units.values())]
    require(not missing, "以下正文页没有归入任何节点：" + "、".join(missing[:10]), 422)
    payload = parsed.to_dict()
    w["semantic_map"] = {"schema_version": SCHEMA_VERSION, "input_sha256": semantic_map_input(w), "result": payload,
                         "result_sha256": digest(payload), "author": author, "accepted_at": now()}
    refresh_summary(w)                       # topic passes under the old map are stale until redone


EXCLUSION_KEYS = {"id", "decision", "reason", "pages", "units", "sentences", "contains", "sources"}


def check_exclusions(rules) -> list[dict]:
    """Validate the customer's exclusion rules: each names what it excludes (pages, units, sentence ids, or a text
    fragment, optionally limited to sources) and the decision it records."""
    require(isinstance(rules, list), "exclusions 须为列表", 422)
    ids = set()
    for r in rules:
        require(isinstance(r, dict) and not set(r) - EXCLUSION_KEYS, "每条排除规则须为对象，字段为 " + "、".join(sorted(EXCLUSION_KEYS)), 422)
        require(isinstance(r.get("id"), str) and r["id"] and r["id"] not in ids, "排除规则须有不重复的 id", 422)
        require(str(r.get("decision", "")).strip(), f"排除规则 {r['id']} 须写明对应的客户决定（decision）", 422)
        require(any(r.get(k) for k in ("pages", "units", "sentences", "contains")), f"排除规则 {r['id']} 须给出 pages / units / sentences / contains 之一", 422)
        for k in ("pages", "units", "sentences", "sources"):
            require(r.get(k) is None or (isinstance(r[k], list) and all(isinstance(x, str) and x for x in r[k])), f"排除规则 {r['id']} 的 {k} 须为字符串列表", 422)
        require(r.get("contains") is None or (isinstance(r["contains"], str) and r["contains"].strip()), f"排除规则 {r['id']} 的 contains 须为原文片段", 422)
        ids.add(r["id"])
    return rules


def _excluded_by(c: dict, rules: list[dict]) -> dict | None:
    for r in rules:
        if r.get("sources") and c["source_id"] not in r["sources"]:
            continue
        if (c["page_id"] in (r.get("pages") or ()) or c["unit_id"] in (r.get("units") or ()) or c["id"] in (r.get("sentences") or ())
                or (r.get("contains") and auto_claims.canon(r["contains"]) in auto_claims.canon(c["quote"]))):
            return r
    return None


def claims(w: dict) -> dict[str, dict]:
    """Every unit cut into verbatim sentences, each attached to the topic whose unit hints name its unit (id → claim);
    sentences the customer's exclusion rules match are marked excluded."""
    d = _d()
    topic_of = {h: n["id"] for n in nodes(w) for h in n["unit_hints"]}
    page_class = {p["id"]: p["reading"]["classification"] for s in w["sources"] for p in s["pages"]}
    rules = w.get("exclusions") or []
    out = {}
    for c in auto_claims.cut(d.all_units(w), page_class, topic_of):
        r = _excluded_by(c, rules) if rules else None
        if r:
            c = {**c, "kind": "excluded", "excluded_by": f"{r['id']}：{r['decision']}"}
        out[c["id"]] = c
    return out


def _node(w: dict, node_id: str) -> dict:
    n = next((n for n in nodes(w) if n["id"] == node_id), None)
    require(n, f"语义地图上没有主题 {node_id}", 404)
    return n


def referred_to(w: dict, node_id: str) -> dict[str, str]:
    """Sentences other topics' accepted passes left out as belonging to this topic (sentence id → referring topic)."""
    out = {}
    for t_id, t in sorted((w.get("topic_passes") or {}).items()):
        if t_id == node_id:
            continue
        for c, to in t["result"]["signals"].get("other_topic") or []:
            if to == node_id:
                out.setdefault(c, t_id)
    return out


def topic_input(w: dict, node_id: str) -> str:
    """What a topic pass rests on: the map, the topic's units, the sentences other topics referred to it, the
    customer's exclusions and the cutting and checking rules. A new referral makes the topic due again."""
    hints = set(_node(w, node_id)["unit_hints"])
    return digest({"map": (w.get("semantic_map") or {}).get("result_sha256"), "topic": node_id,
                   "units": [(u["id"], u["text"]) for u in _d().all_units(w) if u["id"] in hints],
                   "referred": sorted(referred_to(w, node_id)),
                   "exclusions": w.get("exclusions") or [], "schemas": [auto_claims.SCHEMA, topic_pass.SCHEMA]})


def topic_current(w: dict, node_id: str) -> bool:
    t = (w.get("topic_passes") or {}).get(node_id)
    return bool(t) and semantic_map_current(w) and t.get("input_sha256") == topic_input(w, node_id)


def pending_topics(w: dict) -> list[str]:
    return [n["id"] for n in nodes(w) if not topic_current(w, n["id"])]


def topic_brief(w: dict, node_id: str) -> dict:
    n = _node(w, node_id)
    m = w["semantic_map"]["result"]
    cl = claims(w)
    refs = referred_to(w, node_id)
    mine = [c for c in cl.values() if c["topic"] == node_id]
    shown = [c for c in mine if c["kind"] in ("sentence", "cell", "header", "label", "heading", "gloss", "data")]
    where = auto_claims.table_context([u for u in _d().all_units(w) if u["id"] in set(n["unit_hints"])
                                       or u["id"] in {cl[c]["unit_id"] for c in refs if c in cl}])
    titles = {x["id"]: x["title"] for x in nodes(w)}
    excluded = {}
    for c in mine:
        if c["kind"] == "excluded":
            excluded[c["excluded_by"]] = excluded.get(c["excluded_by"], 0) + 1
    return {"kind": "TOPIC_PASS", "schema_version": topic_pass.SCHEMA, "input_sha256": topic_input(w, node_id),
            "topic": {k: n[k] for k in ("id", "title", "role", "thesis", "mainline")} | ({"pages": n["pages"]} if n.get("pages") is not None else {}),
            "material": {"one_liner": m["one_liner"], "topics": [{"id": x["id"], "title": x["title"]} for x in nodes(w)],
                         "links": [{"from": titles[e["from"]], "to": titles[e["to"]], "relation": e["relation"]}
                                   for e in m.get("edges") or [] if node_id in (e["from"], e["to"])]},
            "requirements": w.get("requirements") or {},
            "sentences": [[c["id"], c["kind"], " ".join(c["quote"].split())] + ([where[c["unit_id"]]] if c["unit_id"] in where else [])
                          for c in shown],
            "referred_from_other_topics": [[c, cl[c]["kind"], " ".join(cl[c]["quote"].split()), f"由主题 {refs[c]}（{titles.get(refs[c], '')}）转来"]
                                           for c in refs if c in cl and cl[c]["kind"] != "excluded"],
            "excluded_by_customer": [{"rule": k, "sentences": v} for k, v in excluded.items()],
            "why_kinds": topic_pass.WHY,
            "rules": ["sentences 是本主题全部原文句子，由代码从资料中逐字切出：[句子id, 类型, 原文, 位置]。类型 sentence 为句子；cell 为表格的一格，"
                      "位置写出它所在的行标题和列标题；header 为表格首行的列标题；label 为图表标签等短片段；heading 为章节标题；gloss 为缩写注释；data 为图表中连成一串的数字。"
                      "视觉转录的格子在位置中写出它在原图中的位置。客户决定排除的句子已由代码去掉（见 excluded_by_customer），不得引用。",
                      "读完全部句子，像资深讲者一样决定这一主题要讲什么：question 写本主题要回答的一个问题；messages 列出信息，"
                      "role 取 core（核心）/ support（支撑）/ limit（限定：不可遗漏的人群、时间、条件、否定、例外、不确定性，单独成条）上页讲授，"
                      "reserve（备查）放与主题相关、但不必上页的内容（细节数据、研究设计细节、补充证据），进入讲稿备注和备查。",
                      "先判断什么重要、属于哪条信息，不考虑页面放不放得下：相关但放不下的内容放进 reserve，不要列入 left_out。页数在后面的页面阶段安排。",
                      "label 是你写的一行组织性标题：不写数字、药名、比较或评价结论；内容只通过 claims 中的句子 id 承载，不改写、不概括原文。",
                      "引用必须准确：一条信息引用的句子必须真的表达这条信息。拿不准的数据（看不清对应关系、数值可疑、来源之间不一致）不要略去，"
                      "列入 checks 并写明哪里拿不准，交审查核对。需要别的主题的句子时可以引用其 id，代码会标为借用。",
                      "relations：type 取 sequence / contrast / condition / evidence；from 为一条信息 id，to 为信息 id 列表；"
                      "basis 为直接表达这一关系的句子 id。没有依据句或依据句不来自两端信息的资料时，代码会标为作者组织，交审查。",
                      "page_plan：把每条 core / support / limit 信息恰好放到一页，按讲解顺序；reserve 不进 page_plan。topic.pages 只是参考。",
                      "每个 sentence 和每个表格行（cell 按行计）要么被某条信息引用，要么列入 checks，要么列入 left_out。gloss、data、label、heading、header 不必交代。",
                      "left_out 只用于确实不用的内容，逐条判断：每条写 why（取自 why_kinds）和 note（具体原因），并用 ids、from/to（同一单元内的句子 id 范围）"
                      "或 row（表格行，如 \"S01:s15:t1r5\"）指明句子；duplicate 写 same_as（已引用的那句 id），other_topic 写 topic（主题 id），"
                      "customer_decision 写 decision（哪条客户决定）。行政信息、转给其他主题、客户决定、重复可以共用一条 note；"
                      "off_topic 是对具体句子的判断。审查会重点看：大批略去、被略去的带数字句子、套用在多句上的同一条 off_topic 理由。",
                      "referred_from_other_topics 是其他主题判断属于本主题的句子：与本主题的句子同样处理（引用、列入 checks 或 left_out）。",
                      "gaps：受众会关心、但资料没有回答的问题。"],
            "result_contract": topic_pass.contract(node_id) | {"input_sha256": topic_input(w, node_id)}}


def accept_topic(w: dict, node_id: str, result: dict, author: str) -> None:
    require(semantic_map_current(w), "语义地图已过期，请先重做 SEMANTIC_MAP", 409)
    n = _node(w, node_id)
    require(isinstance(result, dict) and result.get("input_sha256") == topic_input(w, node_id), "主题对应的地图或资料已变更", 409)
    try:
        rec = topic_pass.check({k: v for k, v in result.items() if k != "input_sha256"}, node_id, claims(w), n.get("pages"),
                               {x["id"] for x in nodes(w)}, referred_to(w, node_id))
    except topic_pass.TopicPassError as e:
        raise _d().WorkflowError(f"主题 {n['title']} 的重点梳理不合格：{e}", 422)
    w.setdefault("topic_passes", {})[node_id] = {"input_sha256": topic_input(w, node_id), "result": rec,
                                                "result_sha256": digest(rec), "author": author, "accepted_at": now()}
    refresh_summary(w)


def draft_ready(w: dict) -> bool:
    return semantic_map_current(w) and bool(nodes(w)) and not pending_topics(w)


def refresh_summary(w: dict) -> None:
    """Keep w["summary"] equal to the draft while every topic is worked out; clear it otherwise."""
    w["summary"] = summary_view(w) if draft_ready(w) else None


def summary_view(w: dict) -> dict:
    """The draft as a summary: a section per topic, a key point per message (role, sentence ids, units)."""
    cl = claims(w)
    m = w["semantic_map"]["result"]
    sections = []
    for n in [n for n in nodes(w) if n["mainline"]] + [n for n in nodes(w) if not n["mainline"]]:
        rec = w["topic_passes"][n["id"]]["result"]
        kp = {x["id"]: f"{n['id']}.k{i}" for i, x in enumerate(rec["messages"], 1)}
        units = lambda ids: list(dict.fromkeys(cl[c]["unit_id"] for c in ids if c in cl))
        sections.append({
            "id": n["id"], "title": n["title"], "summary": rec["question"], "mainline": n["mainline"], "pages": n.get("pages"),
            "source_page_ids": list(dict.fromkeys(cl[c]["page_id"] for x in rec["messages"] for c in x["claims"] if c in cl)),
            "key_points": [{"id": kp[x["id"]], "point": x["label"] + "：" + " ".join(" ".join(cl[c]["quote"].split()) for c in x["claims"] if c in cl),
                            "label": x["label"], "claim_ids": list(x["claims"]), "unit_ids": units(x["claims"]),
                            **({"reserve": True} if x["role"] == "reserve" else {})} for x in rec["messages"]],
            # reserve material is taught in the notes: it counts as support, which pages may show but need not
            "message": {"roles": {kp[x["id"]]: ("support" if x["role"] == "reserve" else x["role"]) for x in rec["messages"]},
                        "relations": [{"type": RELATION_TYPES[r["type"]], "items": [kp[r["from"]]] + [kp[t] for t in r["to"]],
                                       "unit_ids": units(r["basis"]), "claim_ids": list(r["basis"])} for r in rec["relations"]]},
            "page_plan": [[kp[x] for x in page] for page in rec["page_plan"]], "gaps": rec["gaps"],
            "checks": [{"claim_ids": c["claims"], "reason": c["reason"]} for c in rec.get("checks") or []]})
    return {"summary_algorithm": SUMMARY_ALGORITHM, "input_sha256": _d().input_hash(w), "overall_summary": m["one_liner"],
            "sections": sections, "pending_issues": [], "outline_coverage": [],
            "semantic_map_sha256": w["semantic_map"]["result_sha256"],
            "topic_passes": {k: v["result_sha256"] for k, v in sorted((w.get("topic_passes") or {}).items())}}


def cited(w: dict) -> list[str]:
    """Sentence ids the draft cites, in draft order, once each."""
    out = []
    for sec in (w.get("summary") or {}).get("sections") or []:
        for k in sec["key_points"]:
            out += [c for c in k["claim_ids"] if c not in out]
    return out


def unconfirmed_sentences(w: dict) -> list[str]:
    """Cited sentences quoting a picture/chart transcription that has no agreeing second reading or human check."""
    cl = claims(w)
    return [c for c in cited(w) if cl.get(c, {}).get("needs_confirmation")]


def draft_facts(w: dict) -> dict:
    """The fact store of a confirmed draft: one fact per cited sentence, quoting it whole."""
    cl = claims(w)
    sec_of = {}
    for sec in w["summary"]["sections"]:
        for k in sec["key_points"]:
            for c in k["claim_ids"]:
                sec_of.setdefault(c, []).append(sec["id"])
    facts = [{"id": c, "unit": cl[c]["unit_id"], "quote": cl[c]["quote"], "display": cl[c]["quote"],
              "section_ids": list(dict.fromkeys(sec_of[c])), "note": "初稿引用原句（代码切分）"} for c in cited(w) if c in cl]
    return {"summary_sha256": digest(w["summary"]), "terms": [], "facts": facts, "derivations": []}


def deck_brief(w: dict, b: dict) -> None:
    """DECK for a confirmed draft: the model presents it; the draft decides what each page says."""
    b["topic_draft"] = [{"section_id": sec["id"], "title": sec["title"], "question": sec["summary"], "pages": sec.get("pages"),
                         "page_plan": sec["page_plan"], "gaps": sec["gaps"],
                         "messages": [{"key_point_id": k["id"], "role": "reserve" if k.get("reserve") else sec["message"]["roles"][k["id"]],
                                       "label": k["label"], "facts": k["claim_ids"]} for k in sec["key_points"]],
                         "relations": sec["message"]["relations"]}
                        for sec in w["summary"]["sections"]]
    b["rules"].insert(0, "本项目的内容已由模型梳理、客户确认（topic_draft）：每个主题的 page_plan 是建议的分页，每页讲其中列出的信息；"
                         "页面的 key_point_ids 写该页讲的信息（key_point_id），内容只引用该信息的 facts（事实 id 即原句 id），"
                         "原句太长或要放进图表格子时，按原文切出更细的逐字事实（deck facts，同一核对）。"
                         "core 与 limit 信息每条至少上一页；reserve 信息写进讲稿备注，不必上页；relations 决定版式（先后→流程/时间轴，对照→对照/表格，条件→决策树，证据→证据要点）。"
                         "pages 为 0 的主题不上页，在 omissions 中写明原因。")


def draft(w: dict) -> dict:
    """The first draft, assembled by code: topics in speaking order → messages → their verbatim sentences."""
    cl = claims(w)
    m = w["semantic_map"]["result"]
    order = [n for n in nodes(w) if n["mainline"]] + [n for n in nodes(w) if not n["mainline"]]
    topics = []
    for n in order:
        t = (w.get("topic_passes") or {}).get(n["id"])
        rec = t["result"] if t and topic_current(w, n["id"]) else None
        topics.append({"id": n["id"], "title": n["title"], "mainline": n["mainline"], "pages": n.get("pages"),
                       "current": bool(rec), "question": rec and rec["question"],
                       "checks": [{"reason": c["reason"], "sentences": [{"id": x, "quote": cl[x]["quote"]} for x in c["claims"] if x in cl]}
                                  for c in (rec or {}).get("checks") or []],
                       "page_plan": rec and rec["page_plan"], "gaps": rec and rec["gaps"],
                       "signals": rec and rec["signals"], "relations": rec and rec["relations"],
                       "messages": [{**{k: x[k] for k in ("id", "role", "label")},
                                     "sentences": [{"id": c, "quote": cl[c]["quote"], "source_id": cl[c]["source_id"],
                                                    "page_id": cl[c]["page_id"]} for c in x["claims"] if c in cl]}
                                    for x in (rec["messages"] if rec else [])]})
    # sentences a topic left out as belonging to another topic that this other topic never uses
    used = {c for t in (w.get("topic_passes") or {}).values() for x in t["result"]["messages"] for c in x["claims"]}
    lost = [{"sentence": c, "from_topic": t_id, "to_topic": to} for t_id, t in (w.get("topic_passes") or {}).items()
            for c, to in t["result"]["signals"].get("other_topic") or [] if c not in used]
    return {"one_liner": m["one_liner"], "edges": m.get("edges") or [], "topics": topics, "lost_between_topics": lost}


def draft_markdown(d: dict) -> str:
    role = {"core": "核心", "support": "支撑", "limit": "限定", "reserve": "备查"}
    out = [f"# 初稿\n\n{d['one_liner']}\n"]
    for t in d["topics"]:
        out.append(f"\n## {t['title']}" + ("" if t["mainline"] else "（支线）"))
        if not t["current"]:
            out.append("\n（尚未梳理重点）")
            continue
        out.append(f"\n**{t['question']}**")
        msgs = {x["id"]: x for x in t["messages"]}
        for i, page in enumerate(t["page_plan"], 1):
            out.append(f"\n### 第{i}页")
            for mid in page:
                x = msgs[mid]
                out.append(f"\n**{x['label']}**（{role[x['role']]}）")
                out += [f"- {' '.join(q['quote'].split())}  `{q['id']}`" for q in x["sentences"]]
        reserve = [x for x in t["messages"] if x["role"] == "reserve"]
        if reserve:
            out.append("\n### 备查（讲稿备注）")
            for x in reserve:
                out.append(f"\n**{x['label']}**")
                out += [f"- {' '.join(q['quote'].split())}  `{q['id']}`" for q in x["sentences"]]
        if t["checks"]:
            out.append("\n### 待核对")
            for c in t["checks"]:
                out.append(f"\n{c['reason']}")
                out += [f"- {' '.join(q['quote'].split())}  `{q['id']}`" for q in c["sentences"]]
        if t["gaps"]:
            out.append("\n资料缺口：" + "；".join(t["gaps"]))
    return "\n".join(out) + "\n"
