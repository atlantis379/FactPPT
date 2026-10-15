"""Negative source/index fixtures and actual task/store integration; no real approvals."""
import copy
import json
import pytest
import test_deckflow as T
from test_deckflow import store  # noqa: F401
from test_summary_review_coverage import summarised
from app.deckflow import WorkflowError, digest
from factdeck import summary_evidence as se


def case():
    units = [{'id': 'u1', 'page_id': 'p1', 'text': '条件甲成立时，数值 < 0.7。'},
             {'id': 'u2', 'page_id': 'p2', 'text': '原文限制乙。', 'needs_confirmation': True}]
    claims = {'c1': {'spans': [{'unit_id': 'u1', 'quote': units[0]['text']}]}}
    summary = {'summary_algorithm': 'model_understanding.v1', 'pending_issues': ['TEST来源限制待裁定'],
               'sections': [{'id': 's1', 'source_page_ids': ['p1'], 'key_points': [{'claim_ids': ['c1']}]},
                            {'id': 'reference', 'source_page_ids': ['p2'], 'key_points': []}],
               'evidence_index': {'schema_version': se.SCHEMA,
                    'points': [{'point_id': 's1.k1', 'selection_reason': 'TEST回答课程问题', 'context': 'TEST条件限制仍保留',
                        'evidence': [{'id': 'e1', 'unit_id': 'u1', 'quote': units[0]['text'], 'role': 'main', 'usage': 'TEACHING'}],
                        'data_items': [{'evidence_id': 'e1', 'value': '0.7', 'operator': '<', 'meaning': 'TEST原文阈值'}]}],
                    'page_decisions': [{'page_id': 'p1', 'disposition': 'TEACHING', 'reason': 'TEST主内容', 'point_ids': ['s1.k1']},
                                       {'page_id': 'p2', 'disposition': 'REFERENCE', 'reason': 'TEST参考保留', 'point_ids': []}]}}
    return summary, units, claims


def test_index_preserves_source_offsets_and_creates_no_new_points():
    s, units, claims = case()
    s['evidence_index'] = se.validate(s, units, claims, {'p1', 'p2'})
    before = copy.deepcopy(s['sections'])
    c = se.candidates(s)
    assert s['sections'] == before
    e = s['evidence_index']['points'][0]['evidence'][0]
    assert units[0]['text'][e['start']:e['end']] == e['source_quote']
    assert c['result']['facts'][0]['quote'] == units[0]['text']
    assert c['pending_issues'] == s['pending_issues']


def test_existing_claim_span_is_indexed_without_reprinting_or_modifying_quote():
    s, units, claims = case()
    e = s['evidence_index']['points'][0]['evidence'][0]
    e.pop('quote'); e.pop('unit_id'); e.update(claim_id='c1', span_index=0)
    index = se.validate(s, units, claims, {'p1', 'p2'})
    assert index['points'][0]['evidence'][0]['source_quote'] == units[0]['text']
    e['quote'] = '模型自行改写的句子'
    with pytest.raises(ValueError, match='不得改写'):
        se.validate(s, units, claims, {'p1', 'p2'})


@pytest.mark.parametrize('change,message', [
    (lambda s: s['evidence_index']['points'][0].update(selection_reason=''), '选择理由'),
    (lambda s: s['evidence_index']['points'][0]['evidence'][0].update(quote='数值 > 9。'), '引文不在'),
    (lambda s: s['evidence_index']['points'][0]['data_items'][0].update(value='9'), '数据value'),
    (lambda s: s['evidence_index']['page_decisions'].pop(), '每个来源页'),
    (lambda s: s['evidence_index']['points'].append(copy.deepcopy(s['evidence_index']['points'][0])), '全部要点'),
])
def test_bad_understanding_index_is_rejected(change, message):
    s, units, claims = case(); change(s)
    with pytest.raises(ValueError, match=message):
        se.validate(s, units, claims, {'p1', 'p2'})


def test_reference_limits_stay_pending_and_cannot_be_silently_promoted():
    s, units, claims = case()
    row = s['evidence_index']['points'][0]
    row['evidence'].append({'id': 'e2', 'unit_id': 'u2', 'quote': units[1]['text'], 'role': 'limitation', 'usage': 'TEACHING'})
    s['evidence_index']['page_decisions'][1]['point_ids'] = ['s1.k1']
    with pytest.raises(ValueError, match='PENDING'):
        se.validate(s, units, claims, {'p1', 'p2'})
    row['evidence'][1].update(usage='PENDING', pending_reason='TEST跨参考页裁定', pending_issue_index=0)
    s['evidence_index'] = se.validate(s, units, claims, {'p1', 'p2'})
    c = se.candidates(s)
    assert next(f for f in c['result']['facts'] if f['unit'] == 'u2')['section_ids'] == []
    assert s['evidence_index']['points'][0]['evidence'][1]['needs_confirmation']
    s['pending_issues'] = []
    with pytest.raises(ValueError, match='实际待确认'):
        se.validate(s, units, claims, {'p1', 'p2'})


def test_new_task_requires_index_and_fact_candidate_is_version_bound(store):
    w = summarised(store)
    store.queue(w['id'], 'SUMMARY'); t = store.claim(w['id'], 'new-author', 'SUMMARY')
    assert t['brief']['summary_algorithm'] == se.ALGORITHM
    assert t['brief']['context_mode'] == 'FULL_SECTION_CONTEXT_WITH_CLAIM_INDEX'
    legacy = T.summary(w)
    with pytest.raises(WorkflowError, match='同步证据索引合同'):
        store.complete(w['id'], t['id'], t['lease_token'], legacy)
    r = T.with_understanding(w, T.summary(w))
    w = store.complete(w['id'], t['id'], t['lease_token'], r)
    c = w['summary_fact_candidates']
    assert c['summary_sha256'] == digest(w['summary'])
    saved = json.loads(store.path(c['path']).read_text(encoding='utf-8'))['value']
    assert saved['result']['summary_sha256'] == c['summary_sha256']
    assert w['content_approval'] is None and w['stage'] == 'SUMMARY_REVIEW_REQUIRED'
    assert store.brief(w, 'FACTS', None)['fact_candidates'] == saved
    altered = copy.deepcopy(w); altered['summary']['overall_summary'] += 'TEST修改'
    assert 'fact_candidates' not in store.brief(altered, 'FACTS', None)
    assert store.brief(w, 'SUMMARY_REVIEW', None)['evidence_index'] == w['summary']['evidence_index']


def test_old_leased_summary_contract_is_still_accepted(store):
    w = summarised(store); store.queue(w['id'], 'SUMMARY')
    with store.transaction(w['id'], 'TEST_OLD_CONTRACT') as raw:
        task = next(t for t in raw['tasks'] if t['kind'] == 'SUMMARY' and t['status'] == 'PENDING')
        task['brief'].pop('summary_algorithm', None)
    t = store.claim(w['id'], 'legacy-author', 'SUMMARY')
    w = store.complete(w['id'], t['id'], t['lease_token'], T.summary(w))
    assert not w['summary'].get('summary_algorithm') and w['summary_fact_candidates'] is None


def understood_case():
    s, units, claims = case()
    s['summary_algorithm'] = se.ALGORITHM
    s['sections'][0]['key_points'][0]['point'] = '条件甲成立时，数值 < 0.7。'
    s['source_understanding'] = {'schema_version': se.UNDERSTANDING_SCHEMA, 'sections': [{
        'section_id': 's1', 'author_message': 'TEST有条件的阈值',
        'organization': {'basis': 'SOURCE_SUPPORTED', 'reason': 'TEST来源结构', 'evidence_refs': ['s1.k1/e1']},
        'conclusions': [{'id': 'c1', 'statement': 'TEST阈值', 'conditions_and_limits': 'TEST条件甲成立',
                         'point_ids': ['s1.k1'], 'evidence_refs': ['s1.k1/e1']}],
        'relations': [], 'relation_assessment': 'TEST单结论不猜测关系'}]}
    T.with_source_coverage(s, units)
    return s, units, claims


def test_v2_requires_understanding_but_v1_remains_valid():
    s, units, claims = case()
    se.validate(s, units, claims, {'p1', 'p2'})
    s['summary_algorithm'] = se.ALGORITHM
    with pytest.raises(ValueError, match='原文理解结果'):
        se.validate(s, units, claims, {'p1', 'p2'})


@pytest.mark.parametrize('change,message', [
    (lambda u: u['sections'][0]['conclusions'][0].update(evidence_refs=['s1.k1/nonexistent']), '证据引用'),
    (lambda u: u['sections'][0]['conclusions'][0].update(point_ids=['s2.k1']), '本章有效要点'),
    (lambda u: u['sections'][0].update(relations=[{'from':'c1', 'to':'c2'}]), '关系端点'),
    (lambda u: u['sections'][0]['organization'].update(basis='MODEL_FACT'), '组织依据'),
    (lambda u: u['sections'][0]['organization'].update(basis='ANALYST_ORGANIZATION', evidence_refs=['invented']), '证据引用'),
])
def test_understanding_rejects_unbound_claims_and_invented_endpoints(change, message):
    s, units, claims = understood_case(); change(s['source_understanding'])
    with pytest.raises(ValueError, match=message):
        se.validate(s, units, claims, {'p1', 'p2'})


def test_understanding_does_not_force_a_relation_or_a_short_summary():
    s, units, claims = understood_case()
    s['sections'][0]['summary'] = 'TEST完整上下文' * 1000
    se.validate(s, units, claims, {'p1', 'p2'})


@pytest.mark.parametrize('version', ['model_understanding.v1', 'model_understanding.v2'])
def test_previous_leased_tasks_remain_compatible(store, version):
    w = summarised(store); store.queue(w['id'], 'SUMMARY')
    with store.transaction(w['id'], 'TEST_V1_LEASE') as raw:
        task = next(t for t in raw['tasks'] if t['kind'] == 'SUMMARY' and t['status'] == 'PENDING')
        task['brief']['summary_algorithm'] = version
        task['brief']['result_contract'].pop('source_understanding', None)
    t = store.claim(w['id'], 'v1-author', 'SUMMARY')
    r = T.with_understanding(w, T.summary(w))
    r['summary_algorithm'] = version
    r.pop('source_coverage')
    if version == 'model_understanding.v1': r.pop('source_understanding')
    accepted = store.complete(w['id'], t['id'], t['lease_token'], r)
    assert accepted['summary']['summary_algorithm'] == version
    assert ('source_understanding' in accepted['summary']) == (version != 'model_understanding.v1')


def test_text_lost_to_an_encoding_failure_is_refused():
    s, units, claims = understood_case()
    se.validate(s, units, claims, {'p1', 'p2'})
    s['source_understanding']['sections'][0]['conclusions'][0]['statement'] = '????????????1?'
    with pytest.raises(ValueError, match='s1/c1.statement'):
        se.validate(s, units, claims, {'p1', 'p2'})
    assert not se.garbled('是否需要复查？可以吗? 是的')
