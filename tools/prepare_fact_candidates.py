"""Prepare source-bound fact candidates without approving or updating a workflow."""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.deckflow import Store, all_claims, all_units, digest
from factdeck import facts as fx


def prepare(data_root: Path, workflow_id: str, out: Path, supplements: list[dict]):
    store = Store(data_root)
    w = store.get(workflow_id)
    summary = w['summary']
    if not summary:
        raise ValueError('No summary is available')
    claims = all_claims(w)
    units = all_units(w)
    by_unit = {u['id']: u for u in units}
    raw_facts, origins, bindings = {}, {}, []

    def add(unit, quote, section_id, origin):
        if unit not in by_unit or not quote.strip():
            raise ValueError(f'Missing source unit or quote: {unit}')
        key = (unit, quote)
        fid = 'q_' + hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:20]
        if fid not in raw_facts:
            raw_facts[fid] = {'id': fid, 'unit': unit, 'quote': quote, 'display': quote,
                              'section_ids': [], 'note': 'Source excerpt candidate; human content confirmation pending.'}
            origins[fid] = {'claim_ids': [], 'point_ids': []}
        if section_id and section_id not in raw_facts[fid]['section_ids']:
            raw_facts[fid]['section_ids'].append(section_id)
        for k, v in origin.items():
            if v not in origins[fid][k]:
                origins[fid][k].append(v)
        return fid

    for section in summary['sections']:
        roles = section.get('message', {}).get('roles', {})
        for i, point in enumerate(section['key_points'], 1):
            pid = f"{section['id']}.k{i}"
            fact_ids = []
            for cid in point['claim_ids']:
                if cid not in claims:
                    raise ValueError(f'Missing claim: {cid}')
                for span in claims[cid]['spans']:
                    fid = add(span['unit_id'], span['quote'], section['id'], {'claim_ids': cid, 'point_ids': pid})
                    if fid not in fact_ids:
                        fact_ids.append(fid)
            for extra in [x for x in supplements if x['point_id'] == pid]:
                fact_ids.append(add(extra['unit'], extra['quote'], section['id'], {'point_ids': pid}))
            bindings.append({'point_id': pid, 'section_id': section['id'], 'role': roles.get(pid),
                             'claim_ids': point['claim_ids'], 'additional_unit_ids': point.get('unit_ids', []),
                             'fact_ids': list(dict.fromkeys(fact_ids))})

    unknown = {x['point_id'] for x in supplements} - {x['point_id'] for x in bindings}
    if unknown:
        raise ValueError(f'Supplement refers to unknown point: {sorted(unknown)}')
    result = {'summary_sha256': digest(summary), 'terms': [], 'facts': list(raw_facts.values()), 'derivations': []}
    facts, derivations, terms = fx.parse(result)
    fx.verify(facts, derivations, units, {}, terms)
    rejected = [asdict(f) for f in facts if f.status != 'ACCEPTED']
    if rejected:
        raise ValueError(json.dumps(rejected[:5], ensure_ascii=False))
    manifest = {'workflow_id': workflow_id, 'workflow_revision': w['revision'],
                'summary_sha256': digest(summary), 'state': 'DRAFT_PENDING_CONTENT_CONFIRMATION',
                'content_confirmed': False, 'workflow_updated': False,
                'pending_issues': summary['pending_issues'], 'point_count': len(bindings),
                'candidate_count': len(facts), 'verbatim_pass': len(facts),
                'source_transcription_pending': sum(f.needs_confirmation for f in facts),
                'point_bindings': bindings, 'origins': origins,
                'relations': {s['id']: s.get('message', {}).get('relations', []) for s in summary['sections']},
                'limitations': ['Verbatim matching does not prove medical correctness or semantic completeness.',
                                'Entity/attribute conflict classification and original figure selection remain to be authored.',
                                'Pending source/structure decisions must be resolved before formal acceptance.']}
    out.mkdir(parents=True, exist_ok=True)
    for name, value in [('result.json', result), ('manifest.json', manifest),
                        ('verification.json', {'summary_sha256': digest(summary), 'facts': [asdict(f) for f in facts],
                                               'semantic_conflicts_evaluated': False})]:
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    report = f'''# 下一步：事实库候选整理

状态：待内容确认的候选，不是工作流已经验收的事实库。

- 项目：{workflow_id}；总结版本：{digest(summary)}。
- 覆盖{len(bindings)}个总结要点，提取{len(facts)}个去重原文片段。
- {len(facts)}个片段通过现有事实库逐字引文/显示文字核验；{sum(f.needs_confirmation for f in facts)}个仍带来源转录待确认标记。
- 18项待确认清单原样保存在manifest.json，实际数量：{len(summary['pending_issues'])}。
- 未提交内容确认或正式FACTS任务，未改工作流状态。确认后可以用版本绑定的候选继续正式事实库整理。

逐字核验只证明引文存在于来源单元。实体/属性冲突分类、必要限制跨参考页绑定和原件图选择仍未完成；不能据此声称语义全部通过。范围、限制及关系在point_bindings和relations中保留，避免后续只传主结论。
'''
    (out / 'REPORT.md').write_text(report, encoding='utf-8')
    print(json.dumps({k: manifest[k] for k in ['state', 'point_count', 'candidate_count', 'verbatim_pass',
                                              'source_transcription_pending', 'summary_sha256']}, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root', type=Path, required=True)
    p.add_argument('--workflow', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--supplements', type=Path)
    args = p.parse_args()
    supplements = json.loads(args.supplements.read_text(encoding='utf-8')) if args.supplements else []
    prepare(args.data_root, args.workflow, args.out, supplements)
