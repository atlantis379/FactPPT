"""Model-authored understanding and evidence; code verifies locations, never selects key points."""
from __future__ import annotations

import copy
import hashlib
import json
from .lexicon import canon, locate

ALGORITHM = 'model_understanding.v1'
SCHEMA = 'summary_evidence.v1'
ROLES = {'main', 'support', 'population', 'condition', 'limitation', 'risk', 'comparator', 'timeframe', 'uncertainty', 'data', 'footnote'}
DISPOSITIONS = {'TEACHING', 'CONTEXT', 'REFERENCE', 'PENDING'}
RULES = [
    '先阅读完整文章/章节及连续段落上下文，再判断作者主旨、教学重点、主次和逻辑；论断清单是证据索引，不代替原文理解。',
    '按完整认知单元组织自然语言总结，可作忠实归纳。不得按每两条论断一组、每页固定条数或字数分组来决定重点；要点数量由内容和教学目标决定。',
    '同步填写evidence_index：每个key_point用<章节id>.k<序号>绑定选择理由selection_reason、上下文context和逐字evidence。每点至少一条main证据；条件、限制、风险和人群随结论绑定。',
    '已有论断片段直接引用claim_id与零起始span_index，由代码取原文和位置，不重复抄写引文。需细分或补论断清单遗漏的证据时才写unit_id＋quote。',
    'data_items由模型识别统计含义，再绑定evidence_id；value/operator/unit/context_quote均取对应引文原字，未知留空，不换算、不猜测。原表格的行/列标签与数值可分别作为证据片段绑定。',
    '所有来源页填写page_decisions和理由。参考和待定内容仍可检索。参考页中的必要限制若涉及教学部分，usage=PENDING并说明pending_reason及pending_issue_index（对应pending_issues的零起始序号），不自行改变确认的章节来源分配。',
    '章节message中的关系由模型根据原文判断并给出依据；代码仅检查引用及结构，不生成新的医学逻辑。重点选择理由不是事实依据。',
]


def need(ok, message):
    if not ok:
        raise ValueError(message)


def contract():
    return {'schema_version': SCHEMA, 'points': [{'point_id': 's1.k1', 'selection_reason': '', 'context': '',
            'evidence': [{'id': 'e1', 'claim_id': '', 'span_index': 0, 'role': 'main', 'usage': 'TEACHING'}],
            'data_items': [], 'figure_ids': []}],
            'page_decisions': [{'page_id': '', 'disposition': 'TEACHING', 'reason': '', 'point_ids': []}]}


def validate(summary, units, claims, page_ids, figure_ids=()):
    index = copy.deepcopy(summary.get('evidence_index'))
    need(isinstance(index, dict) and index.get('schema_version') == SCHEMA, '需提供summary_evidence.v1同步证据索引')
    points = {f"{s['id']}.k{i}": (s, p) for s in summary['sections'] for i, p in enumerate(s.get('key_points', []), 1)}
    rows = index.get('points')
    need(isinstance(rows, list) and all(isinstance(r, dict) for r in rows), 'evidence_index.points需为对象列表')
    need(len(rows) == len(points) and {r.get('point_id') for r in rows} == set(points), '同步证据索引须逐项覆盖全部要点且不能重复')
    by_unit = {u['id']: u for u in units}
    reference = {p for s in summary['sections'] if not s.get('key_points') for p in s['source_page_ids']}
    page_points = {p: set() for p in page_ids}
    for row in rows:
        pid = row['point_id']; section, point = points[pid]
        need(isinstance(row.get('selection_reason'), str) and row['selection_reason'].strip(), f'{pid}需说明重点选择理由')
        need(isinstance(row.get('context'), str) and row['context'].strip(), f'{pid}需说明上下文')
        evidence = row.get('evidence')
        need(isinstance(evidence, list) and evidence and all(isinstance(e, dict) for e in evidence), f'{pid}需绑定逐字证据')
        ids = [e.get('id') for e in evidence]
        need(all(isinstance(i, str) and i for i in ids) and len(ids) == len(set(ids)), f'{pid}证据编号不可为空或重复')
        cited_units = {sp['unit_id'] for c in point.get('claim_ids', []) for sp in claims[c]['spans']}
        main = False
        for e in evidence:
            if e.get('claim_id'):
                c = claims.get(e['claim_id']); n = e.get('span_index')
                need(c is not None and type(n) is int and 0 <= n < len(c['spans']), f'{pid}论断片段引用不存在')
                span = c['spans'][n]
                need(not e.get('unit_id') or e['unit_id'] == span['unit_id'], f'{pid}论断与单元绑定不一致')
                need(not e.get('quote') or canon(e['quote']) == canon(span['quote']), f'{pid}不得改写引用的论断片段')
                e.update(unit_id=span['unit_id'], quote=span['quote'])
                if e.get('role') == 'main':
                    need(e['claim_id'] in point.get('claim_ids', []), f'{pid}main论断须为本要点引用')
            u = by_unit.get(e.get('unit_id')); quote = e.get('quote')
            need(u is not None and isinstance(quote, str) and canon(quote), f'{pid}证据需有效单元及非空引文')
            where = locate(u['text'], quote)
            need(where is not None, f'{pid}引文不在原始单元{e["unit_id"]}中')
            need(e.get('role') in ROLES and e.get('usage') in {'TEACHING', 'PENDING'}, f'{pid}证据角色或用途不合法')
            if e['usage'] == 'PENDING':
                need(isinstance(e.get('pending_reason'), str) and e['pending_reason'].strip(), f'{pid}待定证据需说明原因')
                pending_index = e.get('pending_issue_index')
                need(type(pending_index) is int and 0 <= pending_index < len(summary['pending_issues']), f'{pid}待定证据须绑定实际待确认事项pending_issue_index')
            elif u['page_id'] not in section['source_page_ids']:
                need(False, f'{pid}跨章节/参考页证据须标为PENDING并保留裁定')
            if e['role'] == 'main':
                need(e['unit_id'] in cited_units and e['usage'] == 'TEACHING', f'{pid}main证据须绑定本要点引用并可用于本章')
                main = True
            e.update(start=where[0], end=where[1], source_quote=u['text'][where[0]:where[1]],
                     page_id=u['page_id'], needs_confirmation=bool(u.get('needs_confirmation')))
            page_points[u['page_id']].add(pid)
        need(main, f'{pid}至少需一条main证据')
        data = row.get('data_items', [])
        need(isinstance(data, list) and all(isinstance(d, dict) for d in data), f'{pid}data_items需为对象列表')
        by_evidence = {e['id']: e for e in evidence}
        for d in data:
            e = by_evidence.get(d.get('evidence_id'))
            need(e is not None and isinstance(d.get('meaning'), str) and d['meaning'].strip(), f'{pid}数据需绑定证据并说明统计含义')
            need(isinstance(d.get('value'), str) and canon(d['value']), f'{pid}数据取值不能为空')
            for key in ('value', 'operator', 'unit', 'context_quote'):
                token = d.get(key, '')
                need(isinstance(token, str) and (not token or canon(token) in canon(e['source_quote'])), f'{pid}数据{key}不在绑定引文中')
        figs = row.get('figure_ids', [])
        need(isinstance(figs, list) and set(figs) <= set(figure_ids), f'{pid}引用的原件图不存在')
    decisions = index.get('page_decisions')
    need(isinstance(decisions, list) and all(isinstance(d, dict) for d in decisions), 'page_decisions需为对象列表')
    need(len(decisions) == len(page_ids) and {d.get('page_id') for d in decisions} == set(page_ids), '需为每个来源页记录处置理由，且不能重复')
    for d in decisions:
        p = d['page_id']
        need(d.get('disposition') in DISPOSITIONS and isinstance(d.get('reason'), str) and d['reason'].strip(), f'{p}需有效处置及理由')
        need(isinstance(d.get('point_ids'), list) and set(d['point_ids']) == page_points[p], f'{p}要点索引与逐字证据不一致')
        need(d['disposition'] != 'TEACHING' or (page_points[p] and p not in reference), f'{p}不能把无要点或参考页标为TEACHING')
    return index


def candidates(summary):
    """Compile only model-bound evidence; do not select, split or rewrite a key point."""
    raw, origins = {}, {}
    for p in summary['evidence_index']['points']:
        section = p['point_id'].rsplit('.k', 1)[0]
        for e in p['evidence']:
            key = (e['unit_id'], e['start'], e['end'])
            fid = 'e_' + hashlib.sha256(json.dumps(key).encode()).hexdigest()[:20]
            if fid not in raw:
                raw[fid] = {'id': fid, 'unit': e['unit_id'], 'quote': e['source_quote'], 'display': e['source_quote'], 'section_ids': []}
                origins[fid] = []
            if e['usage'] == 'TEACHING' and section not in raw[fid]['section_ids']:
                raw[fid]['section_ids'].append(section)
            origins[fid].append({'point_id': p['point_id'], 'evidence_id': e['id'], 'role': e['role'], 'usage': e['usage']})
    return {'result': {'facts': list(raw.values()), 'terms': [], 'derivations': []}, 'bindings': origins,
            'pending_issues': copy.deepcopy(summary['pending_issues'])}
