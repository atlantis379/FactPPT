"""Model-authored understanding and evidence; code verifies locations, never selects key points."""
from __future__ import annotations

import copy
import hashlib
import json
from .lexicon import canon, locate

ALGORITHM = 'model_understanding.v4'
SUPPORTED_ALGORITHMS = {'model_understanding.v1', 'model_understanding.v2', 'model_understanding.v3', ALGORITHM}
COVERAGE_ALGORITHMS = {'model_understanding.v3', ALGORITHM}
UNDERSTANDING_SCHEMA = 'source_understanding.v1'
SCHEMA = 'summary_evidence.v1'
ROLES = {'main', 'support', 'population', 'condition', 'limitation', 'risk', 'comparator', 'timeframe', 'uncertainty', 'data', 'footnote'}
DISPOSITIONS = {'TEACHING', 'CONTEXT', 'REFERENCE', 'PENDING'}
RULES = [
    'source_coverage.v2逐个登记source_coverage_input中的全部来源单元及代码切好的单句segments，绑定source_units_sha256。每个片段只能落在一个segment之内（填segment_index即整句，句内再分处置时写start/end）；不得用整段或整页一次登记。实质内容EXPRESSED指向section_id/conclusion_id，并在expressions中给出point_id与summary_quote——point正文里逐字存在、表达这句原文的那段话；代码核对其存在，独立审核逐句判断是否完整表达。',
    'PENDING只用于来源本身的问题（pending_pending_kinds），绑定pending_issue_index；没写进总结的实质内容不是PENDING，须写进总结。论断清单标为论断的原文不得归为非论断。非论断材料用明确分类并说明原因，重复翻译绑定duplicate_unit_id；不得用PPT页数或密度理由删掉实质内容。'.replace('pending_pending_kinds', 'SOURCE_AMBIGUOUS原文歧义/SOURCE_ILLEGIBLE无法辨认/SCOPE_DECISION跨章节或来源分配须人工裁定'),
    '总结是完整的教学笔记层，不是PPT选材：原文每句实质内容都要在point正文找得到。按brief的chunks顺序，每块完成“读→写→逐句登记”后用summary-draft保存进度，再做下一块；全部块完成后再组织章节结构与关系；不要先定主题数再往里装内容。任务若带draft，表示此前会话已完成draft.done_chunks，从下一块继续，不重做已完成块。point数量和长度随原文信息量走，一个point过长时拆成多个，不合并压缩。',
    '以下内容最容易被概括掉，须照原文写全：列举（危险因素、机制、症状、条件、设备、例子）逐项写出，不用“等”“多种因素”收尾；图表逐格写（每个框、每个箭头起止、量表每项的两端锚点与计分）；研究写清设计、人群、样本量、地区和效应值；机制链逐环写；定义写全判定标准；“可能”“尚不明确”“仍在研究”“首次显示”“弱相关”“不逊于”等模态与比较词原样保留；例外、否定和适用人群不得只留在context。',
    '不再单独登记六类限定条件：人群、时间、阈值、条件、例外、否定以及模态/强度词（可能、尚未证明、至关重要、弱相关）随原文句子写进point正文，由逐句审核判定是否完整。',
    '代码ACCOUNTED只表示登记与引用完整，不表示语义正确；独立审核逐句判定表达是否完整、分类是否成立、宽泛summary_quote是否真正覆盖原句。',
    '总结阶段没有压缩率、篇幅、要点数量、PPT页数或展示密度目标；完整准确理解优先。页数、密度和展示取舍留给DECK。',
    '先输出source_understanding，再写总结：每章回答作者在讲什么、为何这样组织、各结论如何关联。不是事后给已有摘要补理由；不得先看旧要点再按其数量合并。',
    'source_understanding的conclusions包含必要条件、限制及例外，随后映射到总结point_ids。关系可为前提、因果、相关、比较、并列、时序、例外、支持；原文未建立关系不得猜测。SOURCE_SUPPORTED须给逐字证据refs；ANALYST_ORGANIZATION只代表组织建议，不能冒充作者关系或医学结论。',
    '来源中的关键阈值、条件、否定、例外和流程分支须在理解及总结中明确表达；仅保留figure引用或证据索引不算表达。发现来源歧义写pending_issues，不静默补写。',
    'key_point.point是完整的总结结论及必要解释，不是主题目录或压缩标题。context补充背景，不得把直接改变结论含义的阈值、必要条件、否定或例外只放在context/引文中；这些须同时在point正文明确。',
    '先阅读完整文章/章节及连续段落上下文，再判断作者主旨、教学重点、主次和逻辑；论断清单是证据索引，不代替原文理解。',
    '按完整认知单元组织自然语言总结，可作忠实归纳。不得按每两条论断一组、每页固定条数或字数分组来决定重点；要点数量由内容和教学目标决定。',
    '同步填写evidence_index：每个key_point用<章节id>.k<序号>绑定选择理由selection_reason、上下文context和逐字evidence。每点至少一条main证据；条件、限制、风险和人群随结论绑定。',
    '已有论断片段直接引用claim_id与零起始span_index，由代码取原文和位置，不重复抄写引文。需细分或补论断清单遗漏的证据时才写unit_id＋quote。',
    'data_items由模型识别统计含义，再绑定evidence_id；value/operator/unit/context_quote均取对应引文原字，未知留空，不换算、不猜测。原表格的行/列标签与数值可分别作为证据片段绑定。',
    '所有来源页填写page_decisions和理由。参考和待定内容仍可检索。参考页中的必要限制若涉及教学部分，usage=PENDING并说明pending_reason及pending_issue_index（对应pending_issues的零起始序号），不自行改变确认的章节来源分配。',
    '章节message中的关系由模型根据原文判断并给出依据；代码仅检查引用及结构，不生成新的医学逻辑。重点选择理由不是事实依据。',
]


def garbled(text):
    """Text lost to an encoding failure: mostly '?' or replacement characters."""
    if not isinstance(text, str):
        return False
    bad = text.count('?') + text.count('�')
    return bad >= 4 and bad > 0.3 * sum(not c.isspace() for c in text)


# Fields that copy source or summary text verbatim (or are ids): a faithful quote of a '????' cell is not an encoding failure.
VERBATIM_KEYS = frozenset({'quote', 'summary_quote', 'source_text', 'source_quote', 'context_quote', 'target_id', 'point_id',
                           'unit_id', 'issue_id', 'section_id', 'id', 'value'})


def garbled_paths(x, at='result', skip=VERBATIM_KEYS):
    """Paths of strings in a JSON value that are garbled, ignoring verbatim-copy and id fields."""
    if isinstance(x, dict):
        return [b for k, v in x.items() if k not in skip for b in garbled_paths(v, f'{at}.{k}', skip)]
    if isinstance(x, list):
        return [b for i, v in enumerate(x) for b in garbled_paths(v, f'{at}[{i}]', skip)]
    return [at] if garbled(x) else []


def authored_text(summary):
    """(field, text) for every model-authored prose field of a summary."""
    yield 'overall_summary', summary.get('overall_summary')
    for i, x in enumerate(summary.get('pending_issues') or []):
        yield f'pending_issues[{i}]', x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)
    for s in summary.get('sections') or []:
        yield f"{s.get('id')}.title", s.get('title'); yield f"{s.get('id')}.summary", s.get('summary')
        for i, k in enumerate(s.get('key_points') or [], 1):
            yield f"{s.get('id')}.k{i}.title", k.get('title'); yield f"{s.get('id')}.k{i}", k.get('point')
    for r in (summary.get('source_understanding') or {}).get('sections') or []:
        sid = r.get('section_id')
        yield f'{sid}.author_message', r.get('author_message'); yield f'{sid}.relation_assessment', r.get('relation_assessment')
        yield f'{sid}.organization', (r.get('organization') or {}).get('reason')
        for c in r.get('conclusions') or []:
            yield f"{sid}/{c.get('id')}.statement", c.get('statement')
            yield f"{sid}/{c.get('id')}.conditions_and_limits", c.get('conditions_and_limits')
        for i, x in enumerate(r.get('relations') or []):
            yield f'{sid}.relation{i}', x.get('explanation')
    for p in (summary.get('evidence_index') or {}).get('points') or []:
        yield f"{p.get('point_id')}.selection_reason", p.get('selection_reason'); yield f"{p.get('point_id')}.context", p.get('context')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def contract():
    return {'schema_version': SCHEMA, 'points': [{'point_id': 's1.k1', 'selection_reason': '', 'context': '',
            'evidence': [{'id': 'e1', 'claim_id': '', 'span_index': 0, 'role': 'main', 'usage': 'TEACHING'}],
            'data_items': [], 'figure_ids': []}],
            'page_decisions': [{'page_id': '', 'disposition': 'TEACHING', 'reason': '', 'point_ids': []}]}


def understanding_contract():
    return {'schema_version': UNDERSTANDING_SCHEMA, 'sections': [{
        'section_id': 's1', 'author_message': '',
        'organization': {'basis': 'SOURCE_SUPPORTED', 'reason': '', 'evidence_refs': ['s1.k1/e1']},
        'conclusions': [{'id': 'c1', 'statement': '', 'conditions_and_limits': '',
                         'point_ids': ['s1.k1'], 'evidence_refs': ['s1.k1/e1']}],
        'relations': [{'from': 'c1', 'to': 'c2', 'type': 'prerequisite',
                       'basis': 'SOURCE_SUPPORTED', 'explanation': '', 'evidence_refs': ['s1.k1/e1']}],
        'relation_assessment': ''}]}


def validate_understanding(summary, index):
    """Check bindings and provenance, never infer whether a semantic relation is true."""
    u = summary.get('source_understanding')
    need(isinstance(u, dict) and u.get('schema_version') == UNDERSTANDING_SCHEMA,
         '需先提供source_understanding.v1原文理解结果')
    rows = u.get('sections')
    sections = {s['id']: s for s in summary['sections'] if s.get('key_points')}
    need(isinstance(rows, list) and all(isinstance(r, dict) for r in rows) and
         len(rows) == len(sections) and {r.get('section_id') for r in rows} == set(sections),
         '理解结果须覆盖全部有要点的章节且不能重复')
    refs = {f"{p['point_id']}/{e['id']}": p['point_id'] for p in index['points'] for e in p['evidence']}
    if summary.get('summary_algorithm') == ALGORITHM:
        limits = [c.get('conditions_and_limits', '').strip() for r in rows if isinstance(r, dict)
                  for c in r.get('conclusions') or [] if isinstance(c, dict)]
        repeated = {x for x in limits if x and limits.count(x) > 2}
        need(not repeated, '多条结论使用同一套话conditions_and_limits；须按各结论原文写明条件与限制')
    def text_field(obj, field):
        need(isinstance(obj.get(field), str) and obj[field].strip(), f'理解结果需说明{field}')
    def evidence(obj, points):
        er = obj.get('evidence_refs')
        need(isinstance(er, list) and er and all(isinstance(x, str) and refs.get(x) in points for x in er),
             '理解或关系证据引用不存在或不属于本章/结论')
    for row in rows:
        text_field(row, 'author_message'); text_field(row, 'relation_assessment')
        sid = row['section_id']
        points = {f'{sid}.k{i}' for i, _ in enumerate(sections[sid]['key_points'], 1)}
        org = row.get('organization')
        need(isinstance(org, dict) and org.get('basis') in {'SOURCE_SUPPORTED', 'ANALYST_ORGANIZATION'},
             '组织依据须区分来源支持与模型组织建议')
        text_field(org, 'reason')
        if org['basis'] == 'SOURCE_SUPPORTED' or org.get('evidence_refs'): evidence(org, points)
        conclusions = row.get('conclusions')
        need(isinstance(conclusions, list) and conclusions and all(isinstance(c, dict) for c in conclusions),
             '理解结果需列出结论')
        ids = [c.get('id') for c in conclusions]
        need(all(isinstance(i, str) and i for i in ids) and len(ids) == len(set(ids)), '理解结论编号不可重复或为空')
        covered = set()
        by_id = {}
        for c in conclusions:
            text_field(c, 'statement'); text_field(c, 'conditions_and_limits')
            cp = c.get('point_ids')
            need(isinstance(cp, list) and cp and all(isinstance(p, str) and p in points for p in cp),
                 '理解结论须绑定本章有效要点')
            evidence(c, set(cp)); covered.update(cp); by_id[c['id']] = set(cp)
        need(covered == points, '所有总结要点须映射到原文理解结论')
        relations = row.get('relations')
        need(isinstance(relations, list) and all(isinstance(r, dict) for r in relations), '理解关系须为列表；无关系时说明理由')
        for r in relations:
            need(r.get('from') in by_id and r.get('to') in by_id and r['from'] != r['to'], '关系端点须为不同的有效结论')
            need(r.get('type') in {'prerequisite', 'cause', 'association', 'comparison', 'parallel', 'sequence', 'exception', 'support'}, '理解关系类型无效')
            need(r.get('basis') in {'SOURCE_SUPPORTED', 'ANALYST_ORGANIZATION'}, '关系须区分来源支持与组织建议')
            text_field(r, 'explanation')
            if r['basis'] == 'SOURCE_SUPPORTED' or r.get('evidence_refs'): evidence(r, by_id[r['from']] | by_id[r['to']])


def validate(summary, units, claims, page_ids, figure_ids=()):
    if summary.get('summary_algorithm') == ALGORITHM:
        broken = [f for f, t in authored_text(summary) if garbled(t)]
        need(not broken, '以下字段的文字已损坏（多为?，通常是写入时编码错误），请用UTF-8重写：' + '、'.join(broken[:10]))
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
    if summary.get('summary_algorithm') in {'model_understanding.v2', 'model_understanding.v3', ALGORITHM}:
        validate_understanding(summary, index)
    if summary.get('summary_algorithm') in COVERAGE_ALGORITHMS:
        from .source_coverage import validate as validate_coverage
        validate_coverage(summary, units, claims)
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
