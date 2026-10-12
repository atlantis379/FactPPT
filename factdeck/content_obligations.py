"""Fail-closed source bindings for qualifications and excerpt context.

This module does not infer clinical relationships. It accepts explicitly recorded
semantic bundles and derives only bindings already stated by summary claim scopes
or outline-message limit roles. Call it after the ordinary deck checker.
"""
from __future__ import annotations

from factdeck.context import NOTES, signals

ROLES = {"population", "condition", "limit", "footnote", "list", "context"}
STATES = {"COVERED", "EXCERPT", "NEEDS_HUMAN"}
_HIDDEN = {"design", "speaker_notes", "internal_notes"}


def _sources(w):
    units = {}
    claims = {}
    confirmations = ((w.get("confirmations") or {}).get("transcriptions") or {})
    for src in w.get("sources", []) or []:
        for u in (src.get("units", []) or []) + (src.get("transcriptions", []) or []):
            u = dict(u)
            if u.get("id") in confirmations:
                c = confirmations[u["id"]]
                if c.get("decision") == "CONFIRM":
                    u["text"], u["needs_confirmation"] = c.get("text", u.get("text", "")), False
            elif u.get("second_read", {}).get("agree"):
                u["needs_confirmation"] = False
            elif u.get("second_read") and not u["second_read"].get("agree"):
                u["needs_confirmation"] = True
                u["confirmation_reason"] = "两次独立转录不一致，须人工对照原件"
            units[u.get("id")] = u
        for c in ((src.get("claims") or {}).get("items") or []):
            claims[c.get("id")] = c
    for proposal in w.get("transcription_proposals", []) or []:
        if not isinstance(proposal, dict) or not proposal.get("id"):
            continue
        units[proposal["id"]] = {"id": proposal["id"], "source_id": proposal.get("source_id"),
                                 "page_id": proposal.get("page_id"), "text": proposal.get("text", ""),
                                 "needs_confirmation": True, "confirmation_reason": "转录更正提议待人工确认"}
        c = confirmations.get(proposal["id"])
        if c and c.get("decision") == "CONFIRM":
            units[proposal["id"]].update(text=c.get("text",proposal.get("text","")), needs_confirmation=False)
    return units, claims


def _text(value, parent_key=""):
    if parent_key.lower() in _HIDDEN:
        return
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _text(v, k)
    elif isinstance(value, list):
        for v in value:
            yield from _text(v, parent_key)
    elif isinstance(value, str):
        yield value


def _fact_map(verified):
    rows = verified.get("facts", {}) if isinstance(verified, dict) else {}
    if isinstance(rows, list):
        return {x.get("id"): x for x in rows if isinstance(x, dict)}
    return rows if isinstance(rows, dict) else {}


def build_obligations(w: dict, deck: dict | None = None, verified: dict | None = None) -> dict:
    """Return automatic obligations plus explicit bundles and per-fact context signals.

    Explicit `semantic_bundles` entries use `id`, `primary_fact_refs`,
    `source_unit_refs`, `dependent_fact_refs` (or `dependent_unit_refs`), `role`,
    and optional `adjacent_page_allowed`. Unresolved bundles are never guessed.
    """
    units, claims = _sources(w)
    if verified is not None:
        facts = _fact_map(verified)
        for f in (deck or {}).get("facts", []) or []:
            if isinstance(f, dict) and f.get("id"):
                facts.setdefault(f["id"], f)
    else:
        facts = _fact_map(((w.get("facts") or {}).get("result") or {}))
        for f in (deck or {}).get("facts", []) or []:
            if isinstance(f, dict) and f.get("id"):
                facts[f["id"]] = f
    out = []
    # Claim scopes are literal source excerpts (validated by the claims gate).
    for cid, claim in claims.items():
        scope = claim.get("scope") or {}
        primary_units = list(dict.fromkeys(claim.get("unit_ids") or [x.get("unit_id") for x in claim.get("spans") or [] if x.get("unit_id")]))
        claim_quotes = [str(x.get("quote") or "") for x in claim.get("spans") or []]
        # A scope belongs to the claim's main sentence only when the claim has
        # one explicit source span. Any of several table/context fragments is
        # not a safe substitute for the whole claim.
        has_single_main_span = len(claim_quotes) == 1 and bool(claim_quotes[0])
        primary_facts = [fid for fid, f in facts.items() if f.get("unit") in primary_units and
                         str(f.get("quote") or "") and
                         has_single_main_span and claim_quotes[0] in str(f.get("quote") or "")]
        for role in ("population", "condition"):
            excerpt = str(scope.get(role) or "").strip()
            if not excerpt:
                continue
            source_refs = [uid for uid in primary_units if uid in units and excerpt in str(units[uid].get("text") or "")]
            dependent_facts = [fid for fid, f in facts.items() if f.get("unit") in source_refs and
                               excerpt in str(f.get("display") or f.get("quote") or "")]
            out.append({"id": f"claim:{cid}:{role}", "role": role, "source_unit_refs": source_refs,
                        "primary_fact_refs": primary_facts, "dependent_fact_refs": dependent_facts, "primary_claim_id": cid,
                        "evidence_excerpt": excerpt, "adjacent_page_allowed": False,
                        "unresolved": not source_refs or not primary_facts})
    # The outline message explicitly marks limiting points; use its stated unit refs.
    for sec in ((w.get("summary") or {}).get("sections") or []):
        msg = sec.get("message") or {}
        roles = msg.get("roles") or {}
        coverage = {x.get("point_id"): x for x in sec.get("point_coverage") or []}
        core_id = ((msg.get("core") or {}).get("claim_id"))
        core_claim = claims.get(core_id) or {}
        core_units = list(dict.fromkeys(core_claim.get("unit_ids") or [x.get("unit_id") for x in core_claim.get("spans") or [] if x.get("unit_id")]))
        core_quotes = [str(x.get("quote") or "") for x in core_claim.get("spans") or []]
        core_facts = [fid for fid, f in facts.items() if f.get("unit") in core_units and
                      str(f.get("quote") or "") and
                      len(core_quotes) == 1 and bool(core_quotes[0]) and
                      core_quotes[0] in str(f.get("quote") or "")]
        for pid, role in roles.items():
            if role != "limit":
                continue
            uids = list(dict.fromkeys(coverage.get(pid, {}).get("unit_ids") or []))
            out.append({"id": f"summary:{sec.get('id')}:{pid}:limit", "role": "limit",
                        "primary_fact_refs": core_facts,
                        "source_unit_refs": uids, "dependent_fact_refs": [], "dependent_unit_refs": uids,
                        "adjacent_page_allowed": False, "unresolved": not uids or not core_facts})
    explicit = []
    for b in (w.get("semantic_bundles") or []) + ((deck or {}).get("content_bindings") or []):
        explicit.append(dict(b) if isinstance(b, dict) else {"id": "invalid", "unresolved": True})
    ctx = {}
    for fid, f in facts.items():
        if f.get("figure"):
            continue
        u = units.get(f.get("unit"))
        if not u:
            continue
        for sig in signals(f.get("quote", ""), f.get("display"), u.get("text", "")):
            if sig["kind"] not in {"lead_in", "leading_connective"}:
                continue
            sid = f"{fid}:{sig['kind']}"
            ctx[sid] = {"id": sid, "fact_ref": fid, "unit_ref": f["unit"], "dependency_unit_refs": [], **sig,
                        "description": NOTES.get(sig["kind"], "")}
            if sig["kind"] == "leading_connective":
                source = next((s for s in w.get("sources", []) if any(x.get("id") == f["unit"] for x in (s.get("units") or []) + (s.get("transcriptions") or []))), None)
                if source:
                    seq = [x.get("id") for x in (source.get("units") or []) + (source.get("transcriptions") or [])]
                    ix = seq.index(f["unit"]) if f["unit"] in seq else -1
                    if ix > 0:
                        ctx[sid]["dependency_unit_refs"] = [seq[ix - 1]]
    return {"obligations": out, "semantic_bundles": explicit, "context_signals": ctx}


def validate_deck(w: dict, deck: dict, verified: dict, check: dict) -> dict:
    """Return `{errors, pending}`; errors block a new formal DECK submission.

    The caller supplies ordinary `factdeck.deck.check` output. Facts in notes,
    design text, or unknown refs cannot satisfy a content obligation.
    """
    errors, pending, warnings = [], [], []
    built = build_obligations(w, deck, verified)
    facts = _fact_map(verified)
    pages = {p.get("id"): p for p in deck.get("pages", []) or []}
    checked_pages = {p.get("id"): p for p in (check or {}).get("pages", []) or []}
    placements, page_text = {}, {}
    for pid, page in pages.items():
        res = checked_pages.get(pid) or {}
        placements[pid] = {fid for fid in (res.get("facts") or []) if fid in facts and facts[fid].get("status") == "ACCEPTED"}
        page_text[pid] = " ".join(_text(page))
    all_refs = set(facts)
    source_unit_ids = set(_sources(w)[0])
    # Explicit bundles are validation contracts; unknown relationship records stay pending.
    for b in built["semantic_bundles"]:
        bid = str(b.get("id") or "(unnamed)")
        role = b.get("role")
        if role not in ROLES:
            errors.append(f"语义绑定 {bid} 的 role 无效；允许 {', '.join(sorted(ROLES))}")
            continue
        src = b.get("source_unit_refs") or []
        if not src or any(uid not in source_unit_ids for uid in src):
            errors.append(f"语义绑定 {bid} 缺少有效来源单元原文证据")
            continue
        primary = b.get("primary_fact_refs") or []
        depfacts = b.get("dependent_fact_refs") or []
        depunits = b.get("dependent_unit_refs") or []
        if not primary or (not depfacts and not depunits):
            errors.append(f"语义绑定 {bid} 必须同时登记 primary_fact_refs 和 dependent_fact_refs/dependent_unit_refs")
            continue
        if any(x not in all_refs for x in primary + depfacts):
            errors.append(f"语义绑定 {bid} 引用了不存在的事实")
            continue
        if any(x not in source_unit_ids for x in depunits):
            errors.append(f"语义绑定 {bid} 引用了不存在的限定来源单元")
            continue
        if b.get("relationship_status") in {"UNKNOWN", "NEEDS_HUMAN"} or b.get("unresolved"):
            pending.append(f"语义绑定 {bid} 的来源关系尚未确认")
            continue
        if b.get("relationship_evidence") not in src:
            errors.append(f"语义绑定 {bid} 必须指定 source_unit_refs 中的 relationship_evidence")
            continue
        for primary_ref in primary:
            main_pages = {p for p, refs in placements.items() if primary_ref in refs}
            if not main_pages:
                continue
            requirements = [("fact", fid) for fid in depfacts] + [("unit", uid) for uid in depunits]
            allowed_adjacent = b.get("adjacent_page_allowed") is True
            for p in main_pages:
                allowed_pages = {p}
                if allowed_adjacent:
                    order = list(pages)
                    idx = order.index(p)
                    allowed_pages.update(order[max(0, idx-1):idx] + order[idx+1:idx+2])
                covered = all(
                    any(ref in placements.get(q, set()) for q in allowed_pages) if kind == "fact" else
                    any(any(f.get("unit") == ref and fid in placements.get(q, set()) for fid, f in facts.items())
                        for q in allowed_pages)
                    for kind, ref in requirements
                )
                if not covered:
                    errors.append(f"页面 {p} 使用主事实 {primary_ref}，但未显示 {role} 限定事实（绑定 {bid}）")
    # Automatically extracted claim-scope / summary-limit bindings.
    for ob in built["obligations"]:
        if ob["unresolved"]:
            warnings.append(f"{ob['id']} 未能将限定关系映射到唯一主事实；需要时可登记显式 semantic_bundle")
            continue
        for primary in ob.get("primary_fact_refs", []):
            main_pages = {p for p, refs in placements.items() if primary in refs}
            for p in main_pages:
                depfacts = set(ob.get("dependent_fact_refs") or [])
                depunits = set(ob.get("dependent_unit_refs") or [])
                missing_fact = depfacts and not (depfacts & placements[p])
                missing_unit = [uid for uid in depunits if not any(fid in placements[p] and facts[fid].get("unit") == uid for fid in facts)]
                if not depfacts and not depunits:
                    errors.append(f"页面 {p} 使用主事实 {primary}，但没有显示含原文限定“{ob['evidence_excerpt']}”的事实")
                elif missing_fact or missing_unit:
                    errors.append(f"页面 {p} 使用主事实 {primary}，但未同页显示 {ob['role']} 限定事实")
    # Require explicit disposition of every detected context shape. No response closes a source obligation.
    used = set().union(*placements.values()) if placements else set()
    sigs = {sid: s for sid, s in built["context_signals"].items() if s["fact_ref"] in used}
    responses = {x.get("signal_id"): x for x in deck.get("context_responses") or [] if isinstance(x, dict)}
    if len(responses) != len(deck.get("context_responses") or []):
        errors.append("context_responses 含重复或无效记录")
    missing, extra = set(sigs) - set(responses), set(responses) - set(sigs)
    if missing:
        errors.append("缺少 context_responses：" + "、".join(sorted(missing)))
    if extra:
        errors.append("context_responses 引用了未知信号：" + "、".join(sorted(extra)))
    for sid, row in responses.items():
        if sid not in sigs:
            continue
        state = row.get("state")
        if state not in STATES:
            errors.append(f"{sid} 的 state 须为 COVERED / EXCERPT / NEEDS_HUMAN")
            continue
        refs = row.get("evidence_refs") or []
        if any(x not in all_refs and x not in pages and x not in source_unit_ids for x in refs):
            errors.append(f"{sid} 的 evidence_refs 含不存在的事实或页面编号")
            continue
        reason = str(row.get("reason") or "").strip()
        if state == "NEEDS_HUMAN":
            if not reason:
                errors.append(f"{sid} 标为 NEEDS_HUMAN 时须写明待确认内容")
            else:
                pending.append(f"{sid}：{reason}")
        elif state == "COVERED":
            target_pages = [p for p, placed in placements.items() if sigs[sid]["fact_ref"] in placed]
            related = {fid for fid, f in facts.items() if f.get("unit") in
                       ({sigs[sid]["unit_ref"]} | set(sigs[sid].get("dependency_unit_refs") or [])) and fid != sigs[sid]["fact_ref"]}
            # A diagram's list cells are separate units. Explicit source bindings
            # supply that topology; require every dependent cell visibly on the target page.
            for b in built["semantic_bundles"]:
                dep = set(b.get("dependent_fact_refs") or [])
                if (b.get("role") in {"list", "context"} and sigs[sid]["fact_ref"] in (b.get("primary_fact_refs") or [])
                        and b.get("relationship_evidence") in (b.get("source_unit_refs") or [])
                        and b.get("relationship_status") == "SUPPORTED" and dep
                        and dep <= all_refs and any(dep <= placements[p] for p in target_pages)):
                    related |= dep
            if row.get("adjacent_page_allowed") is True:
                expanded = set(target_pages)
                order = list(pages)
                for p in target_pages:
                    i = order.index(p)
                    expanded.update(order[max(0, i - 1):i] + order[i + 1:i + 2])
                target_pages = list(expanded)
            if not refs or not set(refs) <= related:
                errors.append(f"{sid} 标为 COVERED 时须引用其来源单元的依赖事实")
            elif not any(set(refs) <= placements.get(p, set()) for p in target_pages):
                errors.append(f"{sid} 的 COVERED 证据须与触发事实同页，或在明确允许的相邻页显示")
        else:  # EXCERPT
            if not reason or not refs:
                errors.append(f"{sid} 标为 EXCERPT 时须写明节选理由并引用证据")
            marker = str(row.get("marker") or "").strip()
            target_pages = [p for p, placed in placements.items() if sigs[sid]["fact_ref"] in placed]
            if not marker or not any(marker in page_text.get(p, "") for p in target_pages):
                errors.append(f"{sid} 的 EXCERPT 必须在证据页面显示明确节选标记")
    # Unconfirmed transcription is pending and handled by the formal-render gate.
    for pid, used in placements.items():
        for fid in used:
            f = facts[fid]
            if f.get("needs_confirmation"):
                pending.append(f"页面 {pid} 使用待确认转录事实 {fid}；正式生成前需完成对照确认")
    return {"errors": errors, "pending": pending, "warnings": warnings}


__all__ = ["build_obligations", "validate_deck", "ROLES", "STATES"]
