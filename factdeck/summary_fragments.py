"""Chunk-parallel summaries: a chapter's summary is the concatenation of section-owned fragments.

A fragment is a summary-shaped object holding one or more whole sections and everything that belongs to them: their
key points, understanding sections, evidence rows, page decisions for their pages, coverage rows for the units on their
pages and the pending issues they reference. Sessions write fragments for different chunks at the same time; code
merges each saved fragment into the task's draft. Code assembles and renumbers pending-issue indices; it never edits
authored text.
"""
from __future__ import annotations

import copy


def _pages(section):
    return set(section.get('source_page_ids') or [])


def _pending_refs(fragment):
    """Indices into fragment['pending_issues'] used by its evidence and coverage rows."""
    out = set()
    for row in (fragment.get('evidence_index') or {}).get('points') or []:
        for e in row.get('evidence') or []:
            if isinstance(e.get('pending_issue_index'), int):
                out.add(e['pending_issue_index'])
    for row in (fragment.get('source_coverage') or {}).get('units') or []:
        for p in row.get('parts') or []:
            if isinstance(p.get('pending_issue_index'), int):
                out.add(p['pending_issue_index'])
    return out


def _shift(fragment, mapping):
    for row in (fragment.get('evidence_index') or {}).get('points') or []:
        for e in row.get('evidence') or []:
            if isinstance(e.get('pending_issue_index'), int):
                e['pending_issue_index'] = mapping[e['pending_issue_index']]
    for row in (fragment.get('source_coverage') or {}).get('units') or []:
        for p in row.get('parts') or []:
            if isinstance(p.get('pending_issue_index'), int):
                p['pending_issue_index'] = mapping[p['pending_issue_index']]


def concat(parts, head=None):
    """One summary from parts in order: lists concatenated, pending-issue indices shifted. `head` supplies the
    top-level fields (schema_version, input_sha256, overall_summary, summary_algorithm …)."""
    out = {**(head or {}), 'sections': [], 'outline_coverage': [], 'pending_issues': []}
    understanding = index = coverage = None
    for p in parts:
        p = copy.deepcopy(p)
        shift = len(out['pending_issues'])
        _shift(p, {i: i + shift for i in range(len(p.get('pending_issues') or []))})
        out['sections'] += p.get('sections') or []
        out['outline_coverage'] += p.get('outline_coverage') or []
        out['pending_issues'] += p.get('pending_issues') or []
        u = p.get('source_understanding')
        if isinstance(u, dict):
            understanding = understanding or {**{k: v for k, v in u.items() if k != 'sections'}, 'sections': []}
            understanding['sections'] += u.get('sections') or []
        x = p.get('evidence_index')
        if isinstance(x, dict):
            index = index or {**{k: v for k, v in x.items() if k not in ('points', 'page_decisions')}, 'points': [], 'page_decisions': []}
            index['points'] += x.get('points') or []
            index['page_decisions'] += x.get('page_decisions') or []
        c = p.get('source_coverage')
        if isinstance(c, dict):
            coverage = coverage or {**{k: v for k, v in c.items() if k not in ('units', 'conclusions')}, 'units': []}
            if coverage.get('segmenter') != c.get('segmenter') or coverage.get('schema_version') != c.get('schema_version'):
                raise ValueError('各部分逐句登记须使用同一版本与切句器才能合并')
            coverage['units'] += c.get('units') or []
            if 'conclusions' in c:
                coverage.setdefault('conclusions', []).extend(c['conclusions'])
    if understanding:
        out['source_understanding'] = understanding
    if index:
        out['evidence_index'] = index
    if coverage:
        out['source_coverage'] = coverage
    return out


def split(summary, unit_pages):
    """The summary's sections as fragments, one per section, in order. Rows belong to the section that owns their
    page (unit rows and page decisions), point (evidence rows) or id (understanding); pending issues travel with the
    fragment that references them (unreferenced ones stay with the first fragment)."""
    sections = summary.get('sections') or []
    owner_page = {}
    for s in sections:
        for p in s.get('source_page_ids') or []:
            owner_page.setdefault(p, s['id'])
    frags = {s['id']: {'sections': [s]} for s in sections}
    for s in (summary.get('source_understanding') or {}).get('sections') or []:
        f = frags.get(s.get('section_id'))
        if f is not None:
            f.setdefault('source_understanding', {k: v for k, v in summary['source_understanding'].items() if k != 'sections'} | {'sections': []})
            f['source_understanding']['sections'].append(s)
    index = summary.get('evidence_index') or {}
    head_ix = {k: v for k, v in index.items() if k not in ('points', 'page_decisions')}
    for row in index.get('points') or []:
        f = frags.get(str(row.get('point_id', '')).rsplit('.k', 1)[0])
        if f is not None:
            f.setdefault('evidence_index', head_ix | {'points': [], 'page_decisions': []})['points'].append(row)
    for d in index.get('page_decisions') or []:
        f = frags.get(owner_page.get(d.get('page_id')))
        if f is not None:
            f.setdefault('evidence_index', head_ix | {'points': [], 'page_decisions': []})['page_decisions'].append(d)
    cov = summary.get('source_coverage') or {}
    head_cov = {k: v for k, v in cov.items() if k not in ('units', 'conclusions')}
    for row in cov.get('units') or []:
        f = frags.get(owner_page.get(unit_pages.get(row.get('unit_id'))))
        if f is not None:
            f.setdefault('source_coverage', head_cov | {'units': []})['units'].append(row)
    pending = summary.get('pending_issues') or []
    order = [frags[s['id']] for s in sections]
    claimed = {}
    for f in order:
        for i in sorted(_pending_refs(f)):
            claimed.setdefault(i, f)
    for i in range(len(pending)):
        claimed.setdefault(i, order[0] if order else None)
    for f in order:
        mine = [i for i in range(len(pending)) if claimed.get(i) is f]
        f['pending_issues'] = [pending[i] for i in mine]
        mapping = {old: new for new, old in enumerate(mine)}
        # an index another fragment owns is moved here too (it is that fragment's issue, referenced from here)
        for i in sorted(_pending_refs(f) - set(mine)):
            mapping[i] = len(f['pending_issues']); f['pending_issues'].append(pending[i])
        _shift(f, mapping)
    return order


def apply(summary, fragment, unit_pages):
    """The draft summary with `fragment` merged in: sections with the fragment's ids are replaced, the fragment's
    pages may not belong to any other section, and the result is ordered by each section's first page."""
    new_ids = [s['id'] for s in fragment.get('sections') or []]
    if not new_ids or len(new_ids) != len(set(new_ids)):
        raise ValueError('片段须含至少一个章节，章节编号不重复')
    new_pages = set().union(*(_pages(s) for s in fragment['sections']))
    kept = [f for f in split(summary or {}, unit_pages) if f['sections'][0]['id'] not in new_ids]
    clash = sorted(new_pages & set().union(set(), *(_pages(f['sections'][0]) for f in kept)))
    if clash:
        raise ValueError(f"片段的资料页已属于其他章节：{'、'.join(clash[:5])}；同一页只能由一个章节写")
    page_order = {}
    for n, p in enumerate(sorted(unit_pages.values(), key=_page_key)):
        page_order.setdefault(p, n)
    parts = kept + [fragment]
    parts.sort(key=lambda f: min((page_order.get(p, 10**9) for p in _pages(f['sections'][0])), default=10**9))
    head = {k: v for k, v in (summary or {}).items() if k not in
            ('sections', 'outline_coverage', 'pending_issues', 'source_understanding', 'evidence_index', 'source_coverage')}
    head.update({k: v for k, v in fragment.items() if k in ('schema_version', 'input_sha256', 'summary_algorithm') and v})
    out = concat(parts, head)
    if (summary or {}).get('outline_coverage'):
        out['outline_coverage'] = summary['outline_coverage']
    return out


def _page_key(page_id):
    sid, _, rest = page_id.partition(':')
    digits = ''.join(ch for ch in rest if ch.isdigit())
    return (sid, int(digits) if digits else 0, rest)


def apply_review(result, fragment):
    """A review draft with a fragment's judgments merged in (coverage rows by target, section rows by section)."""
    out = copy.deepcopy(result or {})
    for key, field in (('coverage_review', 'target_id'), ('sections', 'section_id')):
        rows = {r.get(field): r for r in out.get(key) or [] if isinstance(r, dict)}
        for r in fragment.get(key) or []:
            if isinstance(r, dict) and r.get(field):
                rows[r[field]] = r
        out[key] = list(rows.values())
    for k, v in fragment.items():
        if k not in ('coverage_review', 'sections', 'fragment_chunks') and k not in out:
            out[k] = v
    return out
