"""Deterministic accounting, not a semantic completeness oracle.

Models classify source spans and identify qualifiers. Code checks the frozen
source universe, span coverage, conclusion bindings and actual summary quotes.

source_coverage.v2 (model_understanding.v4) tightens the ledger after a measured
S03 run where page-sized EXPRESSED spans hid ~half of the source propositions:
every EXPRESSED part stays inside one code-cut sentence segment and names the
point text that expresses it; claim spans cannot be filed as non-claims; PENDING
names a source reason; an independent reviewer judges every part.
"""
from __future__ import annotations

import hashlib
import json
import re
from .lexicon import locate

SCHEMA = 'source_coverage.v1'
SCHEMA_V2 = 'source_coverage.v2'
FACETS = ('population', 'time', 'threshold', 'condition', 'exception', 'negation')
NON_CLAIM = ('SOURCE_METADATA', 'METHODS_GOVERNANCE', 'REFERENCE_LIST', 'AUTHOR_DISCLOSURE',
             'DUPLICATE_TRANSLATION', 'NON_SUBSTANTIVE_LAYOUT')
# v2 PENDING is a property of the source, never "not yet written".
PENDING_KINDS = ('SOURCE_AMBIGUOUS', 'SOURCE_ILLEGIBLE', 'SCOPE_DECISION')
TERMINATORS = set('。！？；!?;')
# sentence.v2 keeps a bracketed citation that closes a sentence ("…风险。(377)") with that sentence; v1 cut it off
# into a segment of its own, which then sat inside a claim span and could be neither expressed nor dismissed.
SEGMENTER = 'sentence.v2'
SEGMENTERS = ('sentence.v1', SEGMENTER)
_CITATION = re.compile(r'[ \t]*[(\[（【][ \t]*\d+(?:[ \t]*[,，、\-–—][ \t]*\d+)*[ \t]*[)\]）】]')
# One chunk is one worker session's bounded goal. S03 pilot (older Codex build): ~170 sentences per session; COPD run
# 2026-10-17 (Codex 0.163): sessions ended before finishing a 70–84 sentence chunk, so chunks are now ~40 sentences.
CHUNK_PAGES = 3
CHUNK_SEGMENTS = 40
# Reference-list pages (the reader classified the page REFERENCE and the claims list found no claim in the unit) are
# registered by code, one REFERENCE_LIST part per sentence; the reviewer judges each such page once. COPD book: 1,879
# of 6,367 sentences. An author row for a unit replaces the code registration (a reviewer rejected the page).
CODE_REGISTERED = 'code:reference_page'
CODE_REASON = '阅读分类为参考文献页，论断清单在本单元没有论断；程序逐句登记为参考文献，审核按页核对'
EXPRESSED_VERDICTS = ('FULL', 'PARTIAL', 'MISSING', 'CONTRADICTED')
# What a PARTIAL/CONTRADICTED sentence lost. v2 dropped the author-side six-facet ledger (S03 p1–p10: only 3 of 7
# review problems fell in those six; the rest were modality/strength, descriptors and relations) and asks the
# reviewer to name the category instead.
MISSING_FACETS = ('population', 'time', 'threshold', 'condition', 'exception', 'negation',
                  'modality', 'descriptor', 'relation', 'enumeration', 'number', 'other')
CLASSIFICATION_VERDICTS = ('ACCEPTED', 'REJECTED')
REUSE_WARNING = 3        # one summary phrase standing in for more sentences than this is shown to the reviewer


def source_hash(units):
    payload = sorted((u['id'], u['page_id'], u['text']) for u in units)
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode('utf-8')).hexdigest()


def conclusions(summary):
    return {f"{s['section_id']}/{c['id']}": c
            for s in summary.get('source_understanding', {}).get('sections', [])
            for c in s['conclusions']}


def segments(text, segmenter=SEGMENTER):
    """Sentence-level cut points: after each terminator, trailing whitespace attached. Domain-neutral punctuation only.
    sentence.v2 also attaches a closing citation marker when only a line break, a terminator or the end follows it;
    a numbered list marker such as "(1) 下一项" is followed by text and starts the next sentence."""
    out, start, i = [], 0, 0
    while i < len(text):
        if text[i] in TERMINATORS:
            j = i + 1
            while j < len(text) and (text[j] in TERMINATORS or text[j].isspace()):
                j += 1
            if segmenter != 'sentence.v1':
                m = _CITATION.match(text, i + 1)
                k = m.end() if m else -1
                if m and (k == len(text) or text[k] in TERMINATORS or text[k] in '\r\n'):
                    j = k
                    while j < len(text) and (text[j] in TERMINATORS or text[j].isspace()):
                        j += 1
            out.append((start, j)); start = i = j
            continue
        i += 1
    if start < len(text):
        out.append((start, len(text)))
    return [(a, b) for a, b in out if text[a:b].strip()]


def chunks(units, max_pages=CHUNK_PAGES, max_segments=CHUNK_SEGMENTS, light=frozenset()):
    """Consecutive whole pages, in source order, sized for one worker session. Code plans; the model writes.
    Units in `light` (judged once per page) add a page to the chunk without counting toward its size."""
    pages, order = {}, []
    for u in units:
        if u['page_id'] not in pages:
            pages[u['page_id']] = []; order.append(u['page_id'])
        pages[u['page_id']].append(u)
    out, cur = [], None
    for pid in order:
        heavy = [u for u in pages[pid] if u['id'] not in light]
        n = sum(len(segments(u['text'])) for u in heavy)
        size = 1 if heavy else 0
        if cur is None or (size and (cur['size'] >= max_pages or (cur['segments'] and cur['segments'] + n > max_segments))):
            cur = {'index': len(out), 'page_ids': [], 'unit_ids': [], 'segments': 0, 'size': 0}; out.append(cur)
        cur['page_ids'].append(pid); cur['unit_ids'] += [u['id'] for u in pages[pid]]; cur['segments'] += n; cur['size'] += size
    for c in out:
        del c['size']
    return out


def prefill_reference(ledger, units, unit_ids):
    """Register by code every unit in `unit_ids` the ledger does not register yet: one REFERENCE_LIST part per sentence."""
    if not isinstance(ledger, dict) or not isinstance(ledger.get('units'), list):
        return ledger
    segmenter = ledger.get('segmenter', SEGMENTER)
    have = {r.get('unit_id') for r in ledger['units'] if isinstance(r, dict)}
    for u in units:
        if u['id'] in unit_ids and u['id'] not in have:
            ledger['units'].append({'unit_id': u['id'], 'registered_by': CODE_REGISTERED,
                                    'parts': [{'segment_index': i, 'disposition': 'REFERENCE_LIST', 'reason': CODE_REASON,
                                               'conclusion_ids': []} for i, _ in enumerate(segments(u['text'], segmenter))]})
    return ledger


def target_fingerprint(t, points):
    """Everything a coverage verdict rests on: the source text, the registration and the full text of each named point.
    An earlier pass with the same fingerprint still holds."""
    payload = {k: t.get(k) for k in ('source_text', 'disposition', 'reason', 'pending_kind', 'pending_issue_index',
                                     'duplicate_unit_id', 'expressions')}
    payload['points'] = {e['point_id']: points.get(e['point_id'], '') for e in t.get('expressions') or []}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


_UNIT_CODES = {'INVALID_UNIT', 'INVALID_SOURCE_SPAN', 'OVERLAPPING_SPANS', 'MISSING_REASON', 'INVALID_CONCLUSION_LINK',
               'OVERSIZED_PART', 'UNBOUND_SOURCE', 'CROSS_SECTION_SOURCE', 'UNEXPRESSED_SOURCE', 'INVALID_PENDING_LINK',
               'INVALID_PENDING_KIND', 'INVALID_REFERENCE_LINK', 'INVALID_DUPLICATE_LINK', 'CLAIM_SPAN_DISMISSED',
               'INVALID_DISPOSITION', 'UNACCOUNTED_TEXT', 'UNACCOUNTED_UNIT'}


def chunk_progress(summary, units, claims, plan):
    """Per planned chunk: open registration issues on its units. A chunk with none is done (structure only)."""
    issues = audit(summary, units, claims)['issues']
    where = {}
    for i in issues:
        if i['code'] in _UNIT_CODES:
            where.setdefault(str(i['target']).split('/')[0], []).append(i['code'])
    return [{'index': c['index'], 'page_ids': c['page_ids'],
             'open_issues': sum(len(where.get(u, [])) for u in c['unit_ids'])} for c in plan]


def review_progress(targets, rows, points, plan):
    """Per planned chunk: whether every coverage target of its units is judged with a valid row (code checks only)."""
    rows = [r for r in rows or [] if isinstance(r, dict)]
    out = []
    for c in plan:
        own = set(c['unit_ids'])
        sub_t = [t for t in targets if t['unit_id'] in own]
        ids = {t['target_id'] for t in sub_t}
        sub_r = [r for r in rows if r.get('target_id') in ids]
        try:
            check_review(sub_t, sub_r, points)
            problem = ''
        except ValueError as error:
            problem = str(error)
        out.append({'index': c['index'], 'page_ids': c['page_ids'], 'targets': len(sub_t),
                    'judged': len({r.get('target_id') for r in sub_r}), 'problem': problem})
    return out


def coverage_input(units):
    return {'schema_version': SCHEMA_V2, 'segmenter': SEGMENTER, 'source_units_sha256': source_hash(units),
            'units': [{'unit_id': u['id'], 'page_id': u['page_id'], 'characters': len(u['text']),
                       'segments': [{'index': i, 'start': a, 'end': b} for i, (a, b) in enumerate(segments(u['text']))]}
                      for u in units]}


def expected_schema(summary):
    return SCHEMA_V2 if summary.get('summary_algorithm') == 'model_understanding.v4' else SCHEMA


def contract(schema=SCHEMA):
    part = {'start': 0, 'end': 0, 'disposition': 'EXPRESSED', 'reason': '', 'conclusion_ids': ['s1/c1']}
    if schema == SCHEMA_V2:
        part = {'segment_index': 0, 'disposition': 'EXPRESSED', 'reason': '', 'conclusion_ids': ['s1/c1'],
                'expressions': [{'point_id': 's1.k1', 'summary_quote': ''}]}
        return {'schema_version': schema, 'segmenter': SEGMENTER, 'source_units_sha256': '', 'units': [{'unit_id': '', 'parts': [part]}]}
    return {'schema_version': schema, 'source_units_sha256': '',
            'units': [{'unit_id': '', 'parts': [part]}],
            'conclusions': [{'conclusion_id': 's1/c1', 'facets': {
                f: {'status': 'UNASSESSED', 'reason': '', 'items': []} for f in FACETS}}]}


def scaffold(summary, units):
    """No inferred classifications or semantic PASS defaults."""
    schema = expected_schema(summary)
    ledger = {'schema_version': schema, 'source_units_sha256': source_hash(units),
              'units': [{'unit_id': u['id'], 'parts': []} for u in units]}
    if schema == SCHEMA_V2:
        ledger['segmenter'] = SEGMENTER
    if schema == SCHEMA:
        ledger['conclusions'] = [{'conclusion_id': cid, 'facets': {
            f: {'status': 'UNASSESSED', 'reason': '', 'items': []} for f in FACETS}} for cid in conclusions(summary)]
    return ledger


def _claim_spans(claims, by_unit):
    """Where the claims author marked a proposition: {unit_id: [(start, end)]}."""
    out = {}
    for c in (claims or {}).values():
        for sp in c.get('spans', []):
            u = by_unit.get(sp.get('unit_id'))
            if not u:
                continue
            a, b = sp.get('start'), sp.get('end')
            if not (type(a) is int and type(b) is int and u['text'][a:b] == sp.get('quote')):
                where = locate(u['text'], sp.get('quote') or '')
                if where is None:
                    continue
                a, b = where
            out.setdefault(u['id'], []).append((a, b))
    return out


def point_texts(summary):
    return {f"{s['id']}.k{i}": p.get('point', '') for s in summary.get('sections', [])
            for i, p in enumerate(s.get('key_points', []), 1)}


def audit(summary, units, claims=None):
    problems, pending, reference, warnings = [], [], [], []
    def issue(code, target, detail):
        problems.append({'code': code, 'target': target, 'detail': detail})
    def nonempty(x):
        return isinstance(x, str) and bool(x.strip())
    def pending_link(obj, target):
        n = obj.get('pending_issue_index')
        if type(n) is not int or not 0 <= n < len(summary.get('pending_issues', [])):
            issue('INVALID_PENDING_LINK', target, '必须绑定实际pending_issues序号')
        else:
            pending.append({'target': target, 'pending_issue_index': n})
    def rows(value, field):
        if not isinstance(value, list) or not all(isinstance(r, dict) for r in value):
            issue('INVALID_ROWS', field, '需要对象列表'); return []
        return value
    by_unit = {u['id']: u for u in units}
    if len(by_unit) != len(units):
        issue('DUPLICATE_SOURCE_ID', 'units', '来源单元编号必须唯一')
    cs = conclusions(summary)
    section_pages = {s['id']: set(s.get('source_page_ids', [])) for s in summary.get('sections', [])}
    points = point_texts(summary)
    schema = expected_schema(summary)
    v2 = schema == SCHEMA_V2
    claimed = _claim_spans(claims, by_unit) if v2 else {}
    ledger = summary.get('source_coverage')
    if not isinstance(ledger, dict):
        ledger = {}
        issue('MISSING_LEDGER', 'source_coverage', '尚未登记逐单元去向及限定条件')
    if ledger.get('schema_version') != schema:
        issue('INVALID_SCHEMA', 'source_coverage', schema)
    if ledger.get('source_units_sha256') != source_hash(units):
        issue('STALE_SOURCE', 'source_units_sha256', '来源单元集合或原文已变化')
    segmenter = ledger.get('segmenter', SEGMENTER)
    if v2 and segmenter not in SEGMENTERS:
        issue('INVALID_SEGMENTER', 'segmenter', '/'.join(SEGMENTERS))
    seen, mapped = set(), {cid: [] for cid in cs}
    expression_use = {}
    counts = {'parts': 0, 'expressed_parts': 0, 'characters': {}}
    for row in rows(ledger.get('units', []), 'units'):
        uid = row.get('unit_id')
        if not isinstance(uid, str) or uid not in by_unit or uid in seen:
            issue('INVALID_UNIT', str(uid), '单元未知或重复'); continue
        seen.add(uid); text = by_unit[uid]['text']; covered = bytearray(len(text))
        cuts = segments(text, segmenter) if v2 and segmenter in SEGMENTERS else []
        for i, part in enumerate(rows(row.get('parts'), uid)):
            target = f'{uid}/part{i}'
            if v2 and 'segment_index' in part and 'start' not in part and 'end' not in part:
                n = part['segment_index']
                if type(n) is int and 0 <= n < len(cuts):
                    part['start'], part['end'] = cuts[n]
            a, b = part.get('start'), part.get('end')
            if (type(a) is not int or type(b) is not int or not 0 <= a < b <= len(text)
                    or ('quote' in part and part['quote'] != text[a:b])):
                issue('INVALID_SOURCE_SPAN', target, '需准确字符位置与逐字引文'); continue
            if any(covered[a:b]):
                issue('OVERLAPPING_SPANS', target, '同一单元的处置片段不能重叠')
            covered[a:b] = b'\1' * (b-a)
            counts['parts'] += 1
            if not nonempty(part.get('reason')):
                issue('MISSING_REASON', target, '必须说明处置依据')
            disposition = part.get('disposition')
            key = str(disposition)
            counts['characters'][key] = counts['characters'].get(key, 0) + sum(not c.isspace() for c in text[a:b])
            ids = part.get('conclusion_ids')
            if not isinstance(ids, list) or any(not isinstance(c, str) or c not in cs for c in ids):
                issue('INVALID_CONCLUSION_LINK', target, '结论绑定无效'); continue
            if v2 and not any(x <= a and b <= y for x, y in cuts):
                issue('OVERSIZED_PART', target, '每个片段须在代码切分的单句segment之内；不得用整段/整页一次登记')
            if disposition == 'EXPRESSED':
                counts['expressed_parts'] += 1
                if not ids: issue('UNBOUND_SOURCE', target, '已表达内容必须指向理解结论')
                for cid in ids:
                    if by_unit[uid]['page_id'] not in section_pages.get(cid.split('/')[0], set()):
                        issue('CROSS_SECTION_SOURCE', target, '跨章节/参考页原文须先保留PENDING裁定')
                    mapped[cid].append((uid, a, b))
                if v2:
                    allowed = {p for cid in ids for p in cs[cid].get('point_ids', [])}
                    ex = part.get('expressions')
                    if not isinstance(ex, list) or not ex or not all(isinstance(e, dict) for e in ex):
                        issue('UNEXPRESSED_SOURCE', target, '须给出point正文中表达这句原文的summary_quote'); continue
                    for n, e in enumerate(ex):
                        pid, sq = e.get('point_id'), e.get('summary_quote')
                        if pid not in allowed or not nonempty(sq) or locate(points.get(pid, ''), sq) is None:
                            issue('UNEXPRESSED_SOURCE', f'{target}/expr{n}', 'summary_quote必须逐字出现在所绑定结论的point正文；context/索引/引文不算')
                        else:
                            expression_use.setdefault((pid, sq.strip()), []).append(target)
            elif disposition == 'PENDING':
                pending_link(part, target)
                if v2 and part.get('pending_kind') not in PENDING_KINDS:
                    issue('INVALID_PENDING_KIND', target, 'PENDING只用于来源本身的问题：' + '/'.join(PENDING_KINDS) + '；未写完的内容须写进总结')
            elif disposition in NON_CLAIM:
                reference.append({'target': target, 'disposition': disposition, 'reason': part['reason'] if nonempty(part.get('reason')) else ''})
                if ids: issue('INVALID_REFERENCE_LINK', target, '非论断材料不得冒充已表达内容')
                if disposition == 'DUPLICATE_TRANSLATION':
                    dup = part.get('duplicate_unit_id')
                    other = by_unit.get(dup) if isinstance(dup, str) else None
                    if other is None or other['id'] == uid:
                        issue('INVALID_DUPLICATE_LINK', target, '重复翻译必须绑定另一来源单元供语义复核')
                elif any(x < b and a < y for x, y in claimed.get(uid, [])):
                    issue('CLAIM_SPAN_DISMISSED', target, '论断清单已标为论断的原文不能归为非论断；须表达或按来源原因待定')
            else:
                issue('INVALID_DISPOSITION', target, '实质内容须表达或待定；不得以PPT篇幅为由略去')
        # Ignore whitespace only; do not silently drop punctuation, captions or numbers.
        gaps = []; start = None
        for i in range(len(text)+1):
            missing = i < len(text) and not text[i].isspace() and not covered[i]
            if missing and start is None: start = i
            if not missing and start is not None:
                gaps.append({'start': start, 'end': i, 'quote': text[start:i]}); start = None
        if gaps: issue('UNACCOUNTED_TEXT', uid, gaps)
    for uid in sorted(set(by_unit)-seen):
        issue('UNACCOUNTED_UNIT', uid, '来源单元未登记')
    for (pid, sq), targets in expression_use.items():
        if len(targets) > REUSE_WARNING:
            warnings.append({'code': 'REUSED_EXPRESSION', 'target': pid, 'summary_quote': sq, 'parts': targets,
                             'detail': '同一短语代表多句原文；审核须逐句确认是否真正表达'})
    registered = set()
    facet_reasons = {}
    if v2:
        for cid in sorted(cs):
            if not mapped[cid]: issue('UNBOUND_CONCLUSION', cid, '结论没有已登记的原文片段')
        if 'conclusions' in ledger:
            issue('OBSOLETE_FACET_LEDGER', 'conclusions', 'v2不再登记六类限定条件；限定是否表达由逐句审核判定')
    for row in rows(ledger.get('conclusions', []) if not v2 else [], 'conclusions'):
        cid = row.get('conclusion_id')
        if not isinstance(cid, str) or cid not in cs or cid in registered:
            issue('INVALID_CONCLUSION', str(cid), '理解结论未知或重复'); continue
        registered.add(cid)
        if not mapped[cid]: issue('UNBOUND_CONCLUSION', cid, '结论没有已登记的原文片段')
        facets = row.get('facets')
        if not isinstance(facets, dict) or set(facets) != set(FACETS):
            issue('MISSING_FACETS', cid, '人群/时间/阈值/条件/例外/否定须逐项登记'); continue
        for facet, record in facets.items():
            target = f'{cid}/{facet}'
            if not isinstance(record, dict):
                issue('INVALID_FACET', target, '字段须为对象'); continue
            status = record.get('status')
            if not nonempty(record.get('reason')):
                issue('MISSING_REASON', target, '说明原文有无此限定条件的依据')
            elif status in {'PRESENT', 'PENDING'}:
                facet_reasons.setdefault(record['reason'].strip(), set()).add(cid)
            items = rows(record.get('items'), target)
            if status == 'NOT_STATED':
                if items: issue('INVALID_ABSENCE', target, '无此条件不能同时填存在项')
            elif status == 'PENDING':
                pending_link(record, target)
            elif status == 'PRESENT':
                if not items: issue('MISSING_QUALIFIER', target, '至少一条原文限定条件')
            else:
                issue('UNASSESSED_FACET', target, '字段尚未完成判断')
            for n, item in enumerate(items):
                at = f'{target}/{n}'; uid = item.get('unit_id')
                u = by_unit.get(uid) if isinstance(uid, str) else None
                quote = item.get('source_quote')
                span = locate(u['text'], quote) if u and nonempty(quote) else None
                if span is None or not any(uid == u['id'] and a <= span[0] and span[1] <= b
                                           for uid, a, b in mapped[cid]):
                    issue('UNBOUND_QUALIFIER', at, '限定条件必须来自本结论已登记原文')
                pid = item.get('point_id'); sq = item.get('summary_quote')
                if not isinstance(pid, str) or pid not in cs[cid]['point_ids'] or not nonempty(sq) or locate(points.get(pid, ''), sq) is None:
                    issue('UNEXPRESSED_QUALIFIER', at, '必须绑定本结论point正文真实表达；索引/引文/context不算')
    if not v2:
        for cid in sorted(set(cs)-registered):
            issue('UNREGISTERED_CONCLUSION', cid, '结论限定条件未登记')
    return {'schema_version': schema, 'structural_status': 'BLOCKED' if problems else 'ACCOUNTED',
            'semantic_status': 'NOT_REVIEWED', 'issues': problems, 'pending': pending,
            'non_claim_decisions': reference, 'warnings': warnings,
            'counts': {'source_units': len(by_unit), 'registered_units': len(seen),
                       'conclusions': len(cs), 'registered_conclusions': len(registered),
                       'parts': counts['parts'], 'expressed_parts': counts['expressed_parts'],
                       'non_whitespace_characters_by_disposition': counts['characters']}}


def review_targets(summary, units):
    """Every registered part an independent reviewer must judge (v2): expressed parts against the point
    text they name, everything else for its classification. Call on a ledger that passed audit()."""
    by_unit = {u['id']: u for u in units}
    points = point_texts(summary)
    segmenter = summary['source_coverage'].get('segmenter', SEGMENTER)
    out, pages = [], {}
    for row in summary['source_coverage']['units']:
        if row.get('registered_by') == CODE_REGISTERED:
            u = by_unit[row['unit_id']]
            if u['page_id'] not in pages:
                pages[u['page_id']] = {'target_id': f"{u['page_id']}/reference_page", 'unit_id': u['id'], 'page_id': u['page_id'],
                                       'source_text': '', 'disposition': 'REFERENCE_LIST', 'reason': CODE_REASON,
                                       'registered_by': CODE_REGISTERED, 'unit_ids': []}
                out.append(pages[u['page_id']])
            p = pages[u['page_id']]
            p['unit_ids'].append(u['id'])
            p['source_text'] += ('\n' if p['source_text'] else '') + u['text']
            continue
        text = by_unit[row['unit_id']]['text']
        cuts = segments(text, segmenter)
        for i, part in enumerate(row['parts']):
            a, b = part.get('start'), part.get('end')
            if a is None:
                a, b = cuts[part['segment_index']]
            t = {'target_id': f"{row['unit_id']}/part{i}", 'unit_id': row['unit_id'],
                 'page_id': by_unit[row['unit_id']]['page_id'], 'source_text': text[a:b],
                 'disposition': part['disposition'], 'reason': part.get('reason', '')}
            if part['disposition'] == 'EXPRESSED':
                t['expressions'] = [{'point_id': e['point_id'], 'summary_quote': e['summary_quote']}
                                    for e in part.get('expressions', [])]
            else:
                for k in ('pending_kind', 'pending_issue_index', 'duplicate_unit_id'):
                    if k in part: t[k] = part[k]
            out.append(t)
    return out


def check_review(targets, rows, points=None):
    """The reviewer judged every part exactly once; returns (problems, passed). No semantic defaults.
    With `points` (point_id -> text), every FULL/PARTIAL/CONTRADICTED verdict must quote the point text it read:
    this binds each verdict to its target and stops position-based mark strings from drifting."""
    need = {t['target_id']: t for t in targets}
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError('coverage_review需为对象列表')
    got = [r.get('target_id') for r in rows]
    if len(got) != len(set(got)) or set(got) != set(need):
        missing = sorted(set(need) - set(got))[:5]
        raise ValueError('coverage_review须逐条判定全部登记片段（不多不少，不得重复）' + (f'：缺少 {"、".join(missing)}' if missing else ''))
    problems, passed = [], []
    for r in rows:
        t = need[r['target_id']]; v = r.get('verdict')
        allowed = EXPRESSED_VERDICTS if t['disposition'] == 'EXPRESSED' else CLASSIFICATION_VERDICTS
        if v not in allowed:
            raise ValueError(f"{r['target_id']} 的判定须是 {' / '.join(allowed)} 之一")
        if points is not None and v in {'FULL', 'PARTIAL', 'CONTRADICTED'}:
            ev = r.get('point_evidence')
            if (not isinstance(ev, list) or not ev or not all(isinstance(e, dict) and e.get('point_id') in points
                    and isinstance(e.get('quote'), str) and e['quote'].strip()
                    and locate(points[e['point_id']], e['quote']) is not None for e in ev)):
                raise ValueError(f"{r['target_id']} 判为{v}时须在point_evidence给出所读point正文的逐字依据")
        if v in {'FULL', 'ACCEPTED'}:
            passed.append(r['target_id']); continue
        text = r.get('issue') if isinstance(r.get('issue'), str) else ''
        if not text.strip():
            raise ValueError(f"{r['target_id']} 未通过时须写明缺少或错误的内容")
        if text.count('?') + text.count('\ufffd') > len(text.strip()) / 2:
            raise ValueError(f"{r['target_id']} 的说明文字已损坏（多为?），请用UTF-8重新写入")
        if v in {'PARTIAL', 'CONTRADICTED'}:
            mf = r.get('missing_facets')
            if not isinstance(mf, list) or not mf or not set(mf) <= set(MISSING_FACETS):
                raise ValueError(f"{r['target_id']} 判为{v}时须在missing_facets标明缺失类别：" + '/'.join(MISSING_FACETS))
        problems.append({'target_id': r['target_id'], 'unit_id': t['unit_id'], 'verdict': v,
                         'source_text': t['source_text'], 'issue': text.strip(),
                         'missing_facets': list(r.get('missing_facets') or [])})
    return problems, passed


def validate(summary, units, claims=None):
    report = audit(summary, units, claims)
    if report['issues']:
        first = report['issues'][0]
        raise ValueError(f"来源覆盖登记未完成：{first['code']} {first['target']}（共{len(report['issues'])}项，运行tools/audit_summary_coverage.py查看）")
    return report
