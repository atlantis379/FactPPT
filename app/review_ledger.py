"""Issue ledger for independent reviews (docs/SEMANTIC_REVIEW_PROTOCOL.md).

A review round never replaces the previous one's problems. Every issue has a stable id, a severity, a category,
source and page evidence and a status history. Each later round of the same check must give every unresolved
issue a disposition with evidence; an issue is closed only by an independent reviewer's evidenced FIXED or by a
recorded human ruling. Code checks that the ledger is complete and consistent; it does not judge content.

Statuses:
  OPEN         still wrong (or not yet re-checked)
  NEEDS_HUMAN  a human decision is needed (source evidence, scope, relation not stated by the source)
  RETAINED     kept: the evidence available to the reviewer is not enough to decide
  FIXED        an independent reviewer saw the fix (evidence refs into the current version)
  HUMAN_RULED  a person ruled on it (dismissed as unfounded, or decided include/exclude)
"""
from __future__ import annotations

import copy

from app.fact57098 import WorkflowError, now, require

PREFIX = {"summary": "SR", "semantic": "SEM"}
CATEGORIES = {"CONTENT_ERROR": "内容错误", "EVIDENCE_MISSING": "来源证据缺失",
              "EXPRESSION_AMBIGUITY": "页面表达歧义", "HUMAN_DECISION": "人工决策"}
DISPOSITIONS = ("FIXED", "OPEN", "NEEDS_HUMAN", "RETAINED")
UNRESOLVED = {"OPEN", "NEEDS_HUMAN", "RETAINED"}
CLOSED = {"FIXED", "HUMAN_RULED"}
STATUS_NAMES = {"OPEN": "仍未解决", "NEEDS_HUMAN": "待人工确认", "RETAINED": "依据不足而保留",
                "FIXED": "已修复（经独立复核）", "HUMAN_RULED": "已人工裁定"}


def book(w: dict, scope: str) -> dict:
    """The scope's ledger; a project reviewed before the ledger existed is seeded once from its last review."""
    books = w.setdefault("issue_ledger", {})
    if scope not in books:
        books[scope] = {"seq": 0, "issues": [], "rounds": []}
        _seed(w, scope, books[scope])
    return books[scope]


def _seed(w: dict, scope: str, b: dict) -> None:
    r = w.get("summary_review" if scope == "summary" else "semantic_review")
    if not r or r.get("checks"):
        return
    rnd = {"round": 1, "check": "LEGACY", "reviewer": r.get("reviewer"), "input_sha256": r.get("input_sha256"),
           "at": r.get("at"), "legacy": True, "new": []}
    for i in r.get("issues") or []:
        check = "SUMMARY" if scope == "summary" else ("COVERAGE" if str(i.get("id", "")).startswith("coverage#") else "RELATIONS")
        ruled = (r.get("dismissed") or {}).get(i.get("id"))
        issue = _new(b, scope, {"severity": i.get("severity", "BLOCKER"), "category": None, "check": check,
                                "ref": i.get("page_id") or i.get("ref") or "general", "source_ref": i.get("ref", ""),
                                "evidence": "", "problem": i.get("problem", ""), "suggestion": "", "legacy_id": i.get("id")},
                     rnd, "OPEN")
        if ruled:
            _move(issue, "HUMAN_RULED", rnd, ruled.get("reason", ""), [], ruled.get("reviewer"))
        rnd["new"].append(issue["id"])
    b["rounds"].append(rnd)


def _new(b: dict, scope: str, fields: dict, rnd: dict, status: str) -> dict:
    b["seq"] += 1
    issue = {"id": f"{PREFIX[scope]}-{b['seq']:04d}", "scope": scope, **fields, "status": status,
             "opened": {k: rnd.get(k) for k in ("round", "reviewer", "input_sha256", "at")},
             "history": [{"round": rnd["round"], "status": status, "reviewer": rnd.get("reviewer"), "at": rnd.get("at"),
                          "input_sha256": rnd.get("input_sha256"), "evidence": fields.get("evidence", ""), "evidence_refs": []}]}
    b["issues"].append(issue)
    return issue


def _move(issue: dict, status: str, rnd: dict, evidence: str, refs: list, reviewer=None, **extra) -> None:
    issue["status"] = status
    issue["history"].append({"round": rnd["round"], "status": status, "reviewer": reviewer or rnd.get("reviewer"),
                             "at": rnd.get("at") or now(), "input_sha256": rnd.get("input_sha256"),
                             "evidence": evidence, "evidence_refs": refs, **extra})


def issues(w: dict, scope: str) -> list[dict]:
    return book(w, scope)["issues"]


def unresolved(w: dict, scope: str, check: str | None = None) -> list[dict]:
    return [i for i in issues(w, scope) if i["status"] in UNRESOLVED and (check is None or i["check"] == check)]


def blocking(w: dict, scope: str) -> list[dict]:
    """Blockers not closed by an evidenced fix or a human ruling (NEEDS_HUMAN blockers wait for the ruling)."""
    return [i for i in unresolved(w, scope) if i["severity"] == "BLOCKER"]


def awaiting_human(w: dict, scope: str) -> list[dict]:
    return [i for i in unresolved(w, scope) if i["status"] == "NEEDS_HUMAN"]


def to_acknowledge(w: dict, scope: str) -> list[str]:
    """Unresolved non-blocking items the confirming person must see listed (and acknowledge) before confirming."""
    return sorted(i["id"] for i in unresolved(w, scope) if i["severity"] != "BLOCKER")


def view(i: dict, response: dict | None = None) -> dict:
    """An issue as a reviewer or author sees it: the whole history, so a new round starts from the last one."""
    out = {k: i.get(k) for k in ("id", "check", "severity", "category", "status", "ref", "source_ref", "evidence",
                                  "problem", "suggestion", "relation")}
    out["history"] = copy.deepcopy(i["history"])
    if response:
        out["author_response"] = response
    return out


def counts(w: dict, scope: str) -> dict:
    out = {s: 0 for s in STATUS_NAMES}
    for i in issues(w, scope):
        out[i["status"]] += 1
    out["blocking"] = len(blocking(w, scope))
    out["awaiting_human"] = len(awaiting_human(w, scope))
    out["rounds"] = len(book(w, scope)["rounds"])
    return out


def _text(x, field: str, label: str, need: bool = True) -> str:
    v = str(x.get(field) or "").strip()
    require(v or not need, f"{label}需填写 {field}", 422)
    return v[:2000]


def record_round(w: dict, scope: str, check: str, *, reviewer: str, input_sha256: str, dispositions, new_issues,
                 valid_refs: set, ok_refs: set = frozenset(), problem_refs: set = frozenset(), auto_issues=(), meta=None) -> dict:
    """Apply one review round of `check`. Every unresolved issue of the check needs a disposition (FIXED needs
    evidence refs into the current version); reviewer-written issues need the full record; `auto_issues` are issues
    the code derives from verdicts and merge into an unresolved issue on the same ref instead of duplicating it.
    ok_refs / problem_refs are what this round judged fine / wrong: a disposition contradicting them is refused."""
    b = book(w, scope)
    rnd = {"round": len(b["rounds"]) + 1, "check": check, "reviewer": reviewer, "input_sha256": input_sha256, "at": now(),
           "dispositions": {}, "new": [], "reopened": [], "merged": [], **(meta or {})}
    need = {i["id"]: i for i in unresolved(w, scope, check)}
    rows = dispositions or []
    require(isinstance(rows, list) and all(isinstance(r, dict) for r in rows), "prior_issues 需为列表", 422)
    got = [r.get("issue_id") for r in rows]
    missing, extra = sorted(set(need) - set(got)), sorted({str(x) for x in got} - set(need))
    require(len(got) == len(set(got)) and not missing and not extra,
            "须逐条回看此前全部未闭环问题（prior_issues 不多不少，不得重复）" + (f"：缺少 {'、'.join(missing)}" if missing else "")
            + (f"；不存在或已闭环 {'、'.join(extra)}" if extra else ""), 422)
    staying = set()
    for r in rows:
        i, st = need[r["issue_id"]], r.get("status")
        require(st in DISPOSITIONS, f"{i['id']} 的处置须是 {' / '.join(DISPOSITIONS)} 之一", 422)
        ev = _text(r, "evidence", f"{i['id']} 的处置")
        refs = r.get("evidence_refs") or []
        require(isinstance(refs, list) and all(isinstance(x, str) for x in refs), f"{i['id']} 的 evidence_refs 需为编号列表", 422)
        if st == "FIXED":
            require(refs and set(refs) <= valid_refs, f"{i['id']} 标为已修复时须给出当前版本中的页面/要点编号作为证据（evidence_refs）", 422)
            require(i["ref"] not in problem_refs, f"{i['id']} 标为已修复，但本轮对 {i['ref']} 的判定仍有问题", 422)
        elif st == "OPEN":
            require(i["ref"] not in ok_refs, f"{i['id']} 标为仍未解决，但本轮把 {i['ref']} 判为通过；请给出一致的结论", 422)
        _move(i, st, rnd, ev, refs)
        rnd["dispositions"][st] = rnd["dispositions"].get(st, 0) + 1
        if st != "FIXED":
            staying.add(i["id"])
    for x in new_issues or []:
        require(isinstance(x, dict), "问题需为对象", 422)
        sev = x.get("severity")
        require(sev in {"BLOCKER", "NOTE"}, "问题需给出严重程度（BLOCKER / NOTE）", 422)
        cat = x.get("category")
        require(cat in CATEGORIES, "问题需分类：" + " / ".join(f"{k}（{v}）" for k, v in CATEGORIES.items()), 422)
        ref = str(x.get("ref") or "").strip()
        src = _text(x, "source_ref", "问题（来源位置）")
        require(ref in valid_refs or (ref == "general" and src), f"问题的 ref “{ref}” 不是当前版本中的页面、来源页、单元、要点或关系编号", 422)
        fields = {"severity": sev, "category": cat, "check": check, "ref": ref, "source_ref": src,
                  "evidence": _text(x, "evidence", "问题（证据）"), "problem": _text(x, "problem", "问题（说明）"),
                  "suggestion": _text(x, "suggestion", "问题（建议处置）"), "relation": _text(x, "relation", "", False)}
        if x.get('existing_issue_id'):
            old = next((i for i in b['issues'] if i['id'] == x['existing_issue_id']), None)
            require(old and old['id'] in staying and old['check'] == check,
                    'existing_issue_id 须指向本检查表本轮已处置且尚未闭环的问题', 422)
            _move(old, 'NEEDS_HUMAN' if cat == 'HUMAN_DECISION' else 'OPEN', rnd,
                  fields['evidence'], [ref], continued_on=ref)
            if sev == 'BLOCKER':
                old['severity'] = 'BLOCKER'
            rnd['merged'].append(old['id'])
            continue
        if x.get("reopens"):
            old = next((i for i in b["issues"] if i["id"] == x["reopens"]), None)
            require(old and old["status"] == "FIXED" and old["check"] == check, f"reopens 只能指向本检查表中已标为修复的问题：{x['reopens']}", 422)
            old.update({k: v for k, v in fields.items() if k != "check"})
            _move(old, "NEEDS_HUMAN" if cat == "HUMAN_DECISION" else "OPEN", rnd, fields["evidence"], [], reopened=True)
            rnd["reopened"].append(old["id"])
            continue
        rnd["new"].append(_new(b, scope, fields, rnd, "NEEDS_HUMAN" if cat == "HUMAN_DECISION" else "OPEN")["id"])
    for x in auto_issues:
        same = next((i for i in b["issues"] if i["id"] in staying and i["ref"] == x["ref"] and i["check"] == check), None)
        status = "NEEDS_HUMAN" if x["category"] == "HUMAN_DECISION" else "OPEN"
        if same:
            if x["severity"] == "BLOCKER":
                same["severity"] = "BLOCKER"
            same["problem"] = x["problem"]
            if same["status"] == "OPEN" and status == "NEEDS_HUMAN":
                _move(same, status, rnd, x["evidence"], [])
            rnd["merged"].append(same["id"])
            continue
        rnd["new"].append(_new(b, scope, {"check": check, "suggestion": "", "relation": "", **x}, rnd, status)["id"])
    b["rounds"].append(rnd)
    return rnd


def rule(w: dict, scope: str, issue_id: str, record: dict, input_sha256: str | None) -> None:
    """A person's written ruling closes an unresolved issue (unfounded, or a decision such as include/exclude)."""
    require(str(record.get("reviewer", "")).strip() and str(record.get("reason", "")).strip(), "需填写审核人和理由", 422)
    i = next((i for i in issues(w, scope) if i["id"] == issue_id or i.get("legacy_id") == issue_id), None)
    require(i, "问题不存在", 404)
    require(i["status"] in UNRESOLVED, f"{i['id']} 已闭环（{STATUS_NAMES[i['status']]}）", 409)
    rnd = {"round": len(book(w, scope)["rounds"]), "input_sha256": input_sha256, "at": now()}
    _move(i, "HUMAN_RULED", rnd, str(record["reason"]), [], record["reviewer"],
          identity_assurance="LOCAL_RECORDED_NOT_AUTHENTICATED")


def legacy_view(w: dict, scope: str) -> tuple[list[dict], dict]:
    """(issues, dismissed) in the shape earlier screens and reports read; the ledger stays the authority."""
    out, ruled = [], {}
    for i in issues(w, scope):
        out.append({"id": i["id"], "ref": i["ref"], "page_id": i["ref"] if scope == "semantic" else None,
                    "severity": i["severity"], "problem": i["problem"], "status": i["status"], "category": i["category"],
                    "check": i["check"], "source_ref": i.get("source_ref", ""), "suggestion": i.get("suggestion", ""),
                    "rounds": len(i["history"])})
        if i["status"] == "HUMAN_RULED":
            h = i["history"][-1]
            ruled[i["id"]] = {"reviewer": h["reviewer"], "reason": h["evidence"], "at": h["at"]}
    return out, ruled


__all__ = ["book", "issues", "unresolved", "blocking", "awaiting_human", "to_acknowledge", "view", "counts",
           "record_round", "rule", "legacy_view", "CATEGORIES", "DISPOSITIONS", "STATUS_NAMES", "WorkflowError"]
