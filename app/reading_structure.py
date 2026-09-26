# -*- coding: utf-8 -*-
"""Reading-structure artifact: gate it, then join it to the app's Claim Table.

Policy context: `SOURCE_READING_TO_NARRATIVE_DERIVATION_POLICY_v0.2`. The reading,
structure, narrative and allocation in `reading_structure_artifact.v0.2` are semantic
acts a language model performed **outside** this application (the skill's W01-R
stage). This module is how the application takes that work seriously:

* **Gate it.** The code-checkable part of the policy is enforced on import, so an
  artifact that did not read the full text, derived its structure mechanically, or
  dropped a block without declaring it, is refused rather than trusted.
* **Join it.** The artifact anchors pages to source *blocks*; the application anchors
  claims to (document, page). `source.sha256` binds the artifact to one imported
  document and a block's `unit` is that document's page number, so the join is exact
  rather than heuristic.
* **Anchor order.** Walking `narrative_order` → node → blocks → pages → claims gives
  the deck a claim order that is *derivable from a declared narrative*, which is what
  `LD-01` protects. Before this module the "approved order" had no provenance at all.

Nothing here writes project state, and nothing here trusts the artifact.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA_VERSION = "reading_structure_artifact.v0.2"
ACCEPTED_DISPOSITIONS = {"READING_STRUCTURE_ACCEPTED", "READING_STRUCTURE_ACCEPTED_WITH_DECLARED_GAPS"}
COVERAGE_STATES = {"in_deck", "evidence_only"}
READING_MODES = {"FULL_TEXT_READ"}
STRUCTURE_DERIVATIONS = {"LLM_SEMANTIC_SYNTHESIS"}
MIN_CHARACTER_COVERAGE = 0.98
MIN_THREAD_CHARS = 20
MIN_REASON_CHARS = 20

#: Pages that render the argument's shape rather than evidence may legitimately
#: carry no source blocks; an evidence page may not.
STRUCTURE_RENDERING_KINDS = {"ROADMAP", "SECTION_QUESTION", "PART_RECAP", "CONSOLIDATION"}

#: Material-agnostic figure intents the policy allows at allocation time.
FIGURE_INTENTS = ("CAUSAL", "PROGRESSION", "COMPARISON", "TAXONOMY", "PROCESS",
                  "SCALE", "DATA", "QUOTATION", "NONE")


def artifact_digest(artifact: dict[str, Any]) -> str:
    encoded = json.dumps(artifact, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _issue(code: str, rule: str, message: str, *, object_id: Any = None) -> dict[str, Any]:
    issue = {"code": code, "rule": rule, "severity": "BLOCK", "message": message}
    if object_id is not None:
        issue["object"] = object_id
    return issue


def validate_reading_structure(artifact: Any) -> list[dict[str, Any]]:
    """Every code-checkable policy clause, as a list of blocking issues.

    Deliberately narrower than the policy: whether a thread truly captures the
    argument, or whether an emphasis judgement is sound, cannot be automated. Those
    remain human review, and this function never reports them as PASS.
    """
    issues: list[dict[str, Any]] = []
    if not isinstance(artifact, dict):
        return [_issue("ARTIFACT_NOT_AN_OBJECT", "REG-READ-001", "Reading artifact must be a JSON object")]
    if artifact.get("schema_version") != SCHEMA_VERSION:
        issues.append(_issue("SCHEMA_MISMATCH", "REG-READ-001",
                             f"Expected {SCHEMA_VERSION}, got {artifact.get('schema_version')!r}"))
        return issues

    pass_record = artifact.get("reading_pass") or {}
    if pass_record.get("reading_mode") not in READING_MODES:
        issues.append(_issue("NOT_A_FULL_TEXT_READ", "REG-READ-001",
                             f"reading_mode is {pass_record.get('reading_mode')!r}; heading or page splitting "
                             "may inventory the material but never constitutes the structure"))
    blocks_read, blocks_total = pass_record.get("blocks_read"), pass_record.get("blocks_total")
    if not isinstance(blocks_read, int) or not isinstance(blocks_total, int) or blocks_read != blocks_total:
        issues.append(_issue("INCOMPLETE_READ", "REG-READ-001",
                             f"blocks_read={blocks_read} != blocks_total={blocks_total}"))
    chars_read, chars_total = pass_record.get("chars_read"), pass_record.get("chars_total")
    if isinstance(chars_read, int) and isinstance(chars_total, int) and chars_total > 0:
        if chars_read / chars_total < MIN_CHARACTER_COVERAGE:
            issues.append(_issue("CHARACTERS_NOT_FULLY_READ", "REG-READ-001",
                                 f"read {chars_read}/{chars_total} characters "
                                 f"(<{MIN_CHARACTER_COVERAGE:.0%})"))
    if pass_record.get("structure_derivation") not in STRUCTURE_DERIVATIONS:
        issues.append(_issue("MECHANICAL_STRUCTURE_DERIVATION", "REG-READ-001",
                             f"structure_derivation is {pass_record.get('structure_derivation')!r}; "
                             "a structure produced by splitting the material is a table of contents"))

    # REG-READ-018: a reading belongs to a run, not to a document. The completeness checks above
    # certify that a reading happened; they cannot certify that it happened for THIS generation.
    # A cache keyed by source hash, a frozen `authored` answer file, a replayed endpoint response
    # and a previously accepted artifact all satisfy every criterion above while no reader met the
    # material in hand -- which is how a comparison of "different drivers" once measured a fixture
    # and reported it as reader agreement.
    if str(pass_record.get("reused_from") or "").strip():
        issues.append(_issue("READING_REUSED_FROM_PRIOR_ARTIFACT", "REG-READ-018",
                             f"This reading was reused from an earlier one "
                             f"({pass_record.get('reused_from')}); every generation run reads the source "
                             "again. A prior reading may be a declared comparison baseline, never this "
                             "run's reading"))
    read_from = str(pass_record.get("read_from_sha256") or "").strip().lower()
    artifact_source = str((artifact.get("source") or {}).get("sha256") or "").strip().lower()
    if read_from and artifact_source and read_from != artifact_source:
        issues.append(_issue("READ_FROM_A_DIFFERENT_SOURCE", "REG-READ-018",
                             f"read_from_sha256={read_from[:12]}... does not match source.sha256="
                             f"{artifact_source[:12]}...; this reading was taken from different bytes "
                             "than the material it is attached to"))

    structure = artifact.get("structure") or {}
    thread = str(structure.get("thread") or "").strip()
    if len(thread) < MIN_THREAD_CHARS:
        issues.append(_issue("THREAD_MISSING", "REG-READ-004",
                             "The thread must be stated in the reader's own words"))

    blocks = artifact.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        issues.append(_issue("NO_BLOCKS", "REG-READ-002", "Artifact declares no source blocks"))
        blocks = []
    block_ids: list[Any] = []
    for block in blocks:
        block_id = block.get("block_id") if isinstance(block, dict) else None
        block_ids.append(block_id)
        if not isinstance(block, dict):
            issues.append(_issue("BLOCK_NOT_AN_OBJECT", "REG-READ-002", "Block entry must be an object"))
            continue
        if block.get("coverage") not in COVERAGE_STATES:
            issues.append(_issue("BLOCK_COVERAGE_MISSING", "REG-READ-002",
                                 f"Block {block_id} has coverage={block.get('coverage')!r}; every block "
                                 "ends as in_deck or evidence_only", object_id=block_id))
        if block.get("coverage") == "evidence_only" and not str(block.get("evidence_only_reason") or "").strip():
            issues.append(_issue("EVIDENCE_ONLY_WITHOUT_REASON", "REG-READ-002",
                                 f"Block {block_id} is evidence_only without a reason", object_id=block_id))
    duplicates = sorted({str(value) for value in block_ids if block_ids.count(value) > 1}, key=str)
    if duplicates:
        issues.append(_issue("DUPLICATE_BLOCK_IDS", "REG-READ-002",
                             f"Block ids must be unique; duplicated={duplicates[:5]}"))
    known_blocks = {value for value in block_ids if value is not None}

    nodes = structure.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        issues.append(_issue("NO_NODES", "REG-READ-003", "Artifact derives no nodes of meaning"))
        nodes = []
    node_ids: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            issues.append(_issue("NODE_NOT_AN_OBJECT", "REG-READ-003", "Node entry must be an object"))
            continue
        node_id = str(node.get("node_id") or "")
        node_ids.append(node_id)
        if len(str(node.get("why_here") or "").strip()) < 8:
            issues.append(_issue("NODE_WITHOUT_WHY_HERE", "REG-READ-003",
                                 "Every node states why_here as a question answered or a role in the "
                                 "thread; source headings are not admissible", object_id=node_id))
        referenced = node.get("source_block_ids") or []
        if not referenced:
            issues.append(_issue("NODE_WITHOUT_BLOCKS", "REG-READ-003",
                                 f"Node {node_id} cites no source block", object_id=node_id))
        unknown = sorted({str(value) for value in referenced if value not in known_blocks})
        if unknown:
            issues.append(_issue("NODE_REFERENCES_UNKNOWN_BLOCK", "REG-READ-002",
                                 f"Node {node_id} cites unknown blocks {unknown[:5]}", object_id=node_id))

    narrative = artifact.get("narrative") or {}
    order = [str(value) for value in (narrative.get("narrative_order") or [])]
    if sorted(order) != sorted(node_ids) or len(set(order)) != len(order):
        issues.append(_issue("NARRATIVE_ORDER_INCOMPLETE", "REG-READ-014",
                             "narrative_order must list every node exactly once; "
                             f"declared={len(order)} nodes={len(node_ids)}"))
    reason = str(narrative.get("difference_reason") or "").strip()
    if not reason or len(reason) < MIN_REASON_CHARS:
        issues.append(_issue("NARRATIVE_ORDER_UNDECLARED", "REG-READ-014",
                             "The narrative must state how its order differs from source order and what "
                             "that accomplishes; an identical order requires justification, not silence"))

    pages = artifact.get("page_plan")
    if not isinstance(pages, list) or not pages:
        issues.append(_issue("NO_PAGES", "REG-READ-015", "Artifact allocates no page"))
        pages = []
    page_ids: list[str] = []
    exposed_nodes: set[str] = set()
    blocks_by_node = {str(node.get("node_id")): {value for value in (node.get("source_block_ids") or [])}
                      for node in nodes if isinstance(node, dict)}
    declares_node_ids = any(page.get("narrative_node_ids") for page in pages if isinstance(page, dict))
    for page in pages:
        if not isinstance(page, dict):
            issues.append(_issue("PAGE_NOT_AN_OBJECT", "REG-READ-015", "Page entry must be an object"))
            continue
        page_id = str(page.get("page_id") or "")
        page_ids.append(page_id)
        if len(str(page.get("why_this_page") or "").strip()) < 8:
            issues.append(_issue("PAGE_WITHOUT_WHY_THIS_PAGE", "REG-READ-015",
                                 f"Page {page_id} must state why it exists, not what it contains",
                                 object_id=page_id))
        if page.get("figure_intent") not in FIGURE_INTENTS:
            issues.append(_issue("PAGE_WITHOUT_FIGURE_INTENT", "REG-READ-015",
                                 f"Page {page_id} declares figure_intent={page.get('figure_intent')!r}; "
                                 f"allowed={list(FIGURE_INTENTS)}", object_id=page_id))
        node_refs = [str(value) for value in (page.get("narrative_node_ids") or [])]
        exposed_nodes.update(node_refs)
        unknown_nodes = sorted({value for value in node_refs if value not in set(node_ids)})
        if unknown_nodes:
            issues.append(_issue("PAGE_REFERENCES_UNKNOWN_NODE", "REG-READ-017",
                                 f"Page {page_id} cites unknown nodes {unknown_nodes[:5]}", object_id=page_id))
        block_refs = page.get("source_block_ids") or []
        # A node is rendered when its evidence reaches a page: either the page names
        # the node, or it carries a block the node claims. The second test is what
        # makes this work for a reading artifact whose pages are one-per-node and do
        # not yet carry node ids.
        shared = {value for value in block_refs}
        for node_id, node_blocks in blocks_by_node.items():
            if node_blocks & shared:
                exposed_nodes.add(node_id)
        renders = str(page.get("renders_structure") or "NONE")
        if renders in STRUCTURE_RENDERING_KINDS:
            structure_text = str(page.get("structure_text") or "").strip()
            segments = page.get("structure_segments") or []
            if not structure_text and not any(str(item).strip() for item in segments):
                issues.append(_issue("STRUCTURE_PAGE_WITHOUT_CONTENT", "REG-READ-015",
                                     f"Page {page_id} renders {renders} but has no structure_text or "
                                     "structure_segments to show the audience", object_id=page_id))
        else:
            if page.get("figure_intent") != "NONE" and not block_refs:
                issues.append(_issue("EVIDENCE_PAGE_WITHOUT_BLOCKS", "REG-READ-012",
                                     f"Page {page_id} declares figure_intent={page.get('figure_intent')} "
                                     "but records no source block, so it cannot be audited later",
                                     object_id=page_id))
            if page.get("figure_intent") == "NONE" and not (page.get("on_slide_text")
                                                            or page.get("section_label")
                                                            or page.get("action_title")):
                issues.append(_issue("EMPTY_PAGE", "REG-READ-015",
                                     f"Page {page_id} declares no figure and no stated content, so it "
                                     "would render as an empty page", object_id=page_id))
        unknown = sorted({str(value) for value in block_refs if value not in known_blocks})
        if unknown:
            issues.append(_issue("PAGE_REFERENCES_UNKNOWN_BLOCK", "REG-READ-002",
                                 f"Page {page_id} cites unknown blocks {unknown[:5]}", object_id=page_id))
    duplicate_pages = sorted({value for value in page_ids if page_ids.count(value) > 1})
    if duplicate_pages:
        issues.append(_issue("DUPLICATE_PAGE_IDS", "REG-READ-015",
                             f"Page ids must be unique; duplicated={duplicate_pages[:5]}"))
    unexposed = sorted(set(node_ids) - exposed_nodes)
    if unexposed:
        issues.append(_issue("NODE_NOT_EXPOSED", "REG-READ-017",
                             f"The derived structure must be rendered, not merely declared; nodes exposed "
                             f"by no page: {unexposed[:10]}"))
    if declares_node_ids:
        issues.extend(_narrative_sequence_issues(pages, narrative, _issue))

    failed_checks = sorted(name for name, check in (artifact.get("checks") or {}).items()
                           if isinstance(check, dict) and check.get("status") == "FAIL")
    disposition = artifact.get("disposition")
    if disposition == "READING_STRUCTURE_REJECTED":
        issues.append(_issue("DISPOSITION_REJECTED", "REG-READ-004",
                             "The artifact's own disposition is READING_STRUCTURE_REJECTED"))
    elif disposition not in ACCEPTED_DISPOSITIONS:
        issues.append(_issue("DISPOSITION_UNKNOWN", "REG-READ-009",
                             f"Unknown disposition {disposition!r}; accepted={sorted(ACCEPTED_DISPOSITIONS)}"))
    if failed_checks and disposition != "READING_STRUCTURE_ACCEPTED_WITH_DECLARED_GAPS":
        issues.append(_issue("UNDECLARED_GAPS", "REG-READ-010",
                             f"Checks report FAIL ({failed_checks}) but the disposition does not declare "
                             "gaps; an undeclared gap is a rejection"))
    if failed_checks and not artifact.get("coverage_declaration"):
        issues.append(_issue("FAILURES_WITHOUT_DECLARATION", "REG-READ-010",
                             f"Checks report FAIL ({failed_checks}) with no coverage_declaration; failures "
                             "may not be cleared by weakening the check"))
    return issues


def _narrative_sequence_issues(pages: list[Any], narrative: dict[str, Any],
                               issue_factory: Any) -> list[dict[str, Any]]:
    """Pages must not walk the declared narrative backwards.

    The page plan's own array order is the allocation order. This check proves that
    order does not contradict the narrative order M3 declared, which is the anchor
    `LD-01` relies on downstream: without it "the approved order" is whatever the
    artifact happened to list.

    Pages that render the argument's shape -- a roadmap, a section question, a recap,
    a consolidation page -- legitimately reach back across the whole narrative, and an
    appendix page may revisit an early node at the end. So the invariant is on FIRST
    appearances: the order in which nodes are first presented must follow the declared
    narrative order. A node may be revisited afterwards; it may not be introduced late.
    """
    index = {str(node_id): position
             for position, node_id in enumerate(narrative.get("narrative_order") or [])}
    issues: list[dict[str, Any]] = []
    introduced: set[str] = set()
    highest = -1
    for page in pages:
        if not isinstance(page, dict):
            continue
        if str(page.get("renders_structure") or "NONE") in STRUCTURE_RENDERING_KINDS:
            continue
        positions = [index[str(value)] for value in (page.get("narrative_node_ids") or [])
                     if str(value) in index]
        for position in sorted(positions):
            if position < highest and str(position) not in introduced:
                issues.append(issue_factory(
                    "PAGE_ORDER_CONTRADICTS_NARRATIVE", "REG-READ-017",
                    f"Page {page.get('page_id')} introduces narrative node {position + 1} after the "
                    f"deck has already introduced node {highest + 1}; first appearances must follow "
                    "the declared narrative order",
                    object_id=page.get("page_id")))
        for position in positions:
            introduced.add(str(position))
        if positions:
            highest = max(highest, max(positions))
    return issues


def summarize(artifact: dict[str, Any]) -> dict[str, Any]:
    """The facts a reviewer needs without opening the artifact."""
    pass_record = artifact.get("reading_pass") or {}
    checks = artifact.get("checks") or {}
    return {
        "schema_version": artifact.get("schema_version"),
        "disposition": artifact.get("disposition"),
        "reading_mode": pass_record.get("reading_mode"),
        "structure_derivation": pass_record.get("structure_derivation"),
        "blocks_read": pass_record.get("blocks_read"),
        "blocks_total": pass_record.get("blocks_total"),
        "chars_read": pass_record.get("chars_read"),
        "chars_total": pass_record.get("chars_total"),
        "nodes": len((artifact.get("structure") or {}).get("nodes") or []),
        "pages": len(artifact.get("page_plan") or []),
        "open_checks": sorted(name for name, check in checks.items()
                              if isinstance(check, dict) and check.get("status") == "FAIL"),
        "coverage_declaration_basis": (artifact.get("coverage_declaration") or {}).get("basis"),
        "source_sha256": (artifact.get("source") or {}).get("sha256"),
        # REG-READ-018. Reported rather than assumed: an artifact predating the rule declares none
        # of these, and a reviewer must be able to see that freshness was not established instead
        # of reading the absence as a pass.
        "executed_for_run": pass_record.get("executed_for_run"),
        "read_from_sha256": pass_record.get("read_from_sha256"),
        "reused_from": pass_record.get("reused_from"),
        "read_freshness_established": bool(pass_record.get("executed_for_run"))
                                      and not pass_record.get("reused_from"),
    }


def join_pages_to_claims(artifact: dict[str, Any], project: Any) -> dict[str, Any]:
    """Map artifact pages onto approved Claims, through pages, not by guesswork.

    The join is `source.sha256` → imported document, then block `unit` → that
    document's page number → any Claim whose SourceRef cites that page. Anything the
    reading reached but the Claim Table does not cover, and any approved Claim the
    reading never reached, is reported as a gap rather than quietly dropped.

    **Two allocation modes, and the difference matters.** A `SourceRef` is page-granular, so
    a unit-level join can only ever hand a whole source page to one artifact page: when two
    pages cite the same unit, the later one gets nothing. That makes "one page per source
    unit" the only workable shape, which forces the deck to follow the source's own page
    boundaries and discards a reading that grouped the material by argument.

    A page may therefore name the Claims it owns in `claim_texts`. Text, not id: ids are
    minted per extraction, and an accepted reading artifact must not be tied to one run.
    With `claim_texts` present the page owns exactly those Claims, in that order, and
    `source_block_ids` is recorded as provenance only -- it no longer allocates. A text that
    matches nothing is reported (`PAGE_CLAIM_TEXT_NOT_FOUND`), never guessed at.
    """
    source = artifact.get("source") or {}
    source_sha = source.get("sha256")
    document = next((item for item in project.documents if item.get("sha256") == source_sha), None)
    node_ids = {str(node.get("node_id")) for node in (artifact.get("structure") or {}).get("nodes") or []}
    block_by_id = {block.get("block_id"): block for block in artifact.get("blocks") or []}
    pages: list[dict[str, Any]] = []
    ordered: list[str] = []
    gaps: list[dict[str, Any]] = []
    assigned: set[str] = set()

    if document is None:
        return {"document_id": None, "artifact_source_sha256": source_sha,
                "pages": [], "ordered_claim_ids": [], "gaps": [
                    {"code": "SOURCE_NOT_IMPORTED", "message":
                     "No imported document matches the artifact's source sha256; import that document "
                     "before designing pages from this reading"}],
                "join": {"evidence_pages": 0, "pages_with_claims": 0, "pages_without_claims": 0,
                         "claims_joined": 0, "claims_unjoined": 0, "narrative_nodes": len(node_ids)}}

    # Only Claims the triage approved may reach a page. Letting APPENDIX candidates join
    # would render the whole candidate set, which is a different deck from the one the
    # triage decisions approved. Superseded versions are excluded for the same reason an
    # immutable revision exists at all: the successor is the Claim, the predecessor is its
    # history.
    live = [claim for claim in project.claims if not getattr(claim, "superseded_by_claim_id", None)]
    approved = {claim.id for claim in live if claim.triage in ("MUST_INCLUDE", "SHOULD_INCLUDE")}
    claims_by_page: dict[int, list[Any]] = {}
    approved_by_text: dict[str, Any] = {}
    for claim in live:
        if claim.id not in approved:
            continue
        approved_by_text[claim.normalized_claim] = claim
        for ref in claim.source_refs:
            if ref.document_id == document["id"]:
                claims_by_page.setdefault(ref.page, []).append(claim)
    ordered_pages = {str(page.get("page_id")): page for page in artifact.get("page_plan") or []}

    for page_id in _narrative_page_order(artifact, ordered_pages):
        page = ordered_pages[page_id]
        renders = str(page.get("renders_structure") or "NONE")
        block_refs = [value for value in (page.get("source_block_ids") or [])]
        units: list[int] = []
        for block_id in block_refs:
            block = block_by_id.get(block_id) or {}
            unit = block.get("unit")
            if isinstance(unit, int) and unit not in units:
                units.append(unit)
        claim_ids: list[str] = []
        overlapped: list[str] = []
        unmatched: list[str] = []
        named = page.get("claim_texts")
        if isinstance(named, list) and named:
            for text in named:
                claim = approved_by_text.get(str(text))
                if claim is None:
                    unmatched.append(str(text))
                    continue
                if claim.id in assigned:
                    if claim.id not in overlapped:
                        overlapped.append(claim.id)
                    continue
                if claim.id not in claim_ids:
                    claim_ids.append(claim.id)
        else:
            for unit in units:
                for claim in claims_by_page.get(unit, []):
                    if claim.id in assigned:
                        # A Claim rendered on two slides is a duplicate. First page wins and
                        # the overlap is recorded rather than hidden.
                        if claim.id not in overlapped:
                            overlapped.append(claim.id)
                        continue
                    if claim.id not in claim_ids:
                        claim_ids.append(claim.id)
        assigned.update(claim_ids)
        entry = {"page_id": page_id, "renders_structure": renders, "overlapped_claim_ids": overlapped,
                 "unmatched_claim_texts": unmatched,
                 "allocation_mode": "CLAIM_TEXTS" if (isinstance(named, list) and named) else "SOURCE_UNITS",
                 "figure_intent": page.get("figure_intent"), "why_this_page": page.get("why_this_page"),
                 #: The audience-facing subtitle, distinct from why_this_page (which is the reading's
                 #: own reason for the page existing). Kept separate because substituting the reason
                 #: put production rationale on the slide, where a reader sees it as a message.
                 "primary_message": page.get("primary_message"),
                 #: Only a structure page reads these: the throughline it must display.
                 "structure_text": page.get("structure_text"),
                 "structure_segments": page.get("structure_segments") or [],
                 "action_title": page.get("action_title") or page.get("section_label"),
                 "on_slide_text": page.get("on_slide_text") or [],
                 "speaker_notes": page.get("speaker_notes"),
                 "narrative_node_ids": [str(value) for value in (page.get("narrative_node_ids") or [])],
                 "source_block_ids": block_refs, "source_units": units, "claim_ids": claim_ids}
        pages.append(entry)
        ordered.extend(claim_ids)
        if entry["overlapped_claim_ids"]:
            gaps.append({"code": "CLAIM_ALREADY_PLACED", "page_id": page_id,
                         "claim_ids": entry["overlapped_claim_ids"],
                         "message": "Another reading page already owns these Claims; they are not repeated here"})
        if unmatched:
            gaps.append({"code": "PAGE_CLAIM_TEXT_NOT_FOUND", "page_id": page_id,
                         "claim_texts": unmatched[:5],
                         "message": "This page names Claims the approved Claim Table does not contain; the "
                                    "artifact and the extraction disagree and neither is guessed at"})
        # Structure pages intentionally carry no evidence Claims.  Their role is to render
        # the approved narrative shape (ROADMAP / SECTION_QUESTION / PART_RECAP /
        # CONSOLIDATION), so they must remain renderable without a Claim binding.
        if renders not in STRUCTURE_RENDERING_KINDS and not claim_ids:
            gaps.append({"code": "PAGE_WITHOUT_APPROVED_CLAIM", "page_id": page_id,
                         "units": units, "message":
                         "The reading allocated this page to source content that has no approved Claim; "
                         "no page was built for it"})
    unjoined = sorted(approved - set(ordered))
    if unjoined:
        gaps.append({"code": "APPROVED_CLAIM_NOT_IN_READING", "claim_ids": unjoined,
                     "message": "Approved Claims that the reading never reached; they are reported, not "
                                "silently dropped"})
    return {
        "document_id": document["id"],
        "artifact_source_sha256": source_sha,
        "pages": pages,
        "ordered_claim_ids": ordered,
        "gaps": gaps,
        "join": {
            "evidence_pages": sum(1 for page in pages if page["renders_structure"] not in STRUCTURE_RENDERING_KINDS),
            "pages_with_claims": sum(1 for page in pages if page["claim_ids"]),
            "pages_without_claims": sum(1 for page in pages
                                        if not page["claim_ids"]
                                        and page["renders_structure"] not in STRUCTURE_RENDERING_KINDS),
            "claims_joined": len(set(ordered)),
            "claims_unjoined": len(unjoined),
            "claims_overlapped": sum(len(page["overlapped_claim_ids"]) for page in pages),
            "narrative_nodes": len(node_ids),
        },
    }


def _narrative_page_order(artifact: dict[str, Any], pages_by_id: dict[str, dict]) -> list[str]:
    """Pages in narrative order: by node order first, then by the artifact's own order.

    The artifact's `page_plan` array order is already the allocation order, so it is
    authoritative; the node walk only moves pages that the page plan itself left out
    of sequence. This keeps the app from inventing an order the artifact did not state.
    """
    declared = [str(page.get("page_id")) for page in artifact.get("page_plan") or []]
    return [page_id for page_id in declared if page_id in pages_by_id]
