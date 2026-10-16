"""Adversarial accounting checks. These fixtures make no medical approvals."""
import copy
import pytest
import test_deckflow as T
from test_deckflow import store  # noqa: F401
from test_summary_review_coverage import summarised
from app.deckflow import WorkflowError
from factdeck import source_coverage as sc
from factdeck import summary_evidence as se
from test_summary_evidence import understood_case


def case():
    s, units, claims = understood_case()
    assert s['source_coverage']['schema_version'] == sc.SCHEMA_V2 and 'conclusions' not in s['source_coverage']
    return s, units, claims


def v3_case():
    """An earlier model_understanding.v3 summary: page-level parts plus the six-facet qualifier ledger."""
    s, units, claims = understood_case()
    s['summary_algorithm'] = 'model_understanding.v3'
    s['source_coverage'] = sc.scaffold(s, units)
    s['source_coverage']['units'][0]['parts'] = [{'start': 0, 'end': len(units[0]['text']), 'disposition': 'EXPRESSED',
                                                  'reason': 'TEST', 'conclusion_ids': ['s1/c1']}]
    s['source_coverage']['units'][1]['parts'] = [{'start': 0, 'end': len(units[1]['text']), 'disposition': 'SOURCE_METADATA',
                                                  'reason': 'TEST', 'conclusion_ids': []}]
    facets = s['source_coverage']['conclusions'][0]['facets']
    for f in facets.values():
        f.update(status='NOT_STATED', reason='TEST')
    for f in ('condition', 'threshold'):
        q = '条件甲成立时' if f == 'condition' else '< 0.7'
        facets[f] = {'status': 'PRESENT', 'reason': f'TEST原文明确{f}',
                     'items': [{'unit_id': 'u1', 'source_quote': q, 'point_id': 's1.k1', 'summary_quote': q}]}
    return s, units, claims


def codes(s, units, claims=None):
    return {i['code'] for i in sc.audit(s, units, claims)['issues']}


def two_sentence_unit(s, units, part):
    """A second source unit on the taught page holding two sentences, registered by `part`."""
    units = units + [{'id': 'u3', 'page_id': 'p1', 'text': '甲句成立。乙句例外。'}]
    s['source_coverage']['source_units_sha256'] = sc.source_hash(units)
    s['source_coverage']['units'].append({'unit_id': 'u3', 'parts': part})
    return units


def test_accounted_does_not_mean_semantically_approved():
    s, units, claims = case()
    se.validate(s, units, claims, {'p1', 'p2'})
    report = sc.audit(s, units, claims)
    assert report['structural_status'] == 'ACCOUNTED'
    assert report['semantic_status'] == 'NOT_REVIEWED'
    assert report['counts']['expressed_parts'] == 1


@pytest.mark.parametrize('change,code', [
    (lambda s: s['source_coverage']['units'].pop(), 'UNACCOUNTED_UNIT'),
    (lambda s: s['source_coverage']['units'][0]['parts'].clear(), 'UNACCOUNTED_TEXT'),
    (lambda s: s['source_coverage']['units'][0]['parts'][0].update(start=0, end=3, quote='条件甲'), 'UNACCOUNTED_TEXT'),
    (lambda s: s['source_coverage']['units'][0]['parts'][0].update(segment_index=9), 'INVALID_SOURCE_SPAN'),
    (lambda s: s['source_coverage']['units'][0]['parts'][0].update(conclusion_ids=[]), 'UNBOUND_SOURCE'),
    (lambda s: s['source_coverage']['units'][0]['parts'][0].update(disposition='OMITTED_FOR_SLIDE_LIMIT'), 'INVALID_DISPOSITION'),
    (lambda s: s['source_coverage']['units'][0]['parts'][0].pop('expressions'), 'UNEXPRESSED_SOURCE'),
    (lambda s: s['source_coverage']['units'][0]['parts'][0]['expressions'][0].update(summary_quote='原文以外的说法'), 'UNEXPRESSED_SOURCE'),
    (lambda s: s['source_coverage']['units'][0]['parts'][0]['expressions'][0].update(point_id='s9.k1'), 'UNEXPRESSED_SOURCE'),
    (lambda s: s['sections'][0]['key_points'][0].update(point='这里有一个阈值'), 'UNEXPRESSED_SOURCE'),
    (lambda s: s['source_coverage']['units'][1]['parts'][0].update(disposition='PENDING', pending_kind='SOURCE_AMBIGUOUS'), 'INVALID_PENDING_LINK'),
    (lambda s: s['source_coverage'].update(schema_version=sc.SCHEMA), 'INVALID_SCHEMA'),
    (lambda s: s['source_coverage'].update(conclusions=[]), 'OBSOLETE_FACET_LEDGER'),
    (lambda s: s['source_coverage']['units'][0]['parts'][0].update(disposition='PENDING', pending_kind='SOURCE_AMBIGUOUS',
                                                                   pending_issue_index=0, conclusion_ids=[]), 'UNBOUND_CONCLUSION'),
])
def test_reject_silent_drops_unassessed_fields_and_evidence_only_answers(change, code):
    s, units, claims = case(); change(s)
    assert code in codes(s, units, claims)
    with pytest.raises(ValueError, match='来源覆盖登记'):
        sc.validate(s, units, claims)


@pytest.mark.parametrize('change,code', [
    (lambda s: s['source_coverage']['conclusions'][0]['facets'].pop('time'), 'MISSING_FACETS'),
    (lambda s: s['source_coverage']['conclusions'][0]['facets']['time'].update(status='UNASSESSED'), 'UNASSESSED_FACET'),
    (lambda s: s['source_coverage']['conclusions'][0]['facets']['threshold']['items'][0].update(source_quote='> 0.7'), 'UNBOUND_QUALIFIER'),
    (lambda s: s['source_coverage']['conclusions'][0]['facets']['threshold']['items'][0].update(summary_quote='> 0.7'), 'UNEXPRESSED_QUALIFIER'),
    (lambda s: s['source_coverage']['conclusions'].clear(), 'UNREGISTERED_CONCLUSION'),
])
def test_v3_summaries_keep_the_six_facet_ledger(change, code):
    s, units, claims = v3_case()
    assert sc.audit(s, units, claims)['structural_status'] == 'ACCOUNTED'
    change(s)
    assert code in codes(s, units, claims)


def test_one_part_cannot_register_a_whole_paragraph():
    s, units, claims = case()
    whole = {'start': 0, 'end': 10, 'disposition': 'EXPRESSED', 'reason': 'TEST整段', 'conclusion_ids': ['s1/c1'],
             'expressions': [{'point_id': 's1.k1', 'summary_quote': '条件甲'}]}
    units = two_sentence_unit(s, units, [whole])
    assert 'OVERSIZED_PART' in codes(s, units, claims)
    sentences = [dict(whole, start=None, end=None, segment_index=i) for i in (0, 1)]
    for p in sentences: p.pop('start'); p.pop('end')
    s['source_coverage']['units'][-1]['parts'] = sentences
    assert sc.audit(s, units, claims)['structural_status'] == 'ACCOUNTED'
    assert [(a, b) for a, b in sc.segments(units[-1]['text'])] == [(0, 5), (5, 10)]


def test_pending_names_a_source_reason_not_unfinished_writing():
    s, units, claims = case()
    part = s['source_coverage']['units'][1]['parts'][0]
    part.update(disposition='PENDING', pending_issue_index=0)
    assert 'INVALID_PENDING_KIND' in codes(s, units, claims)
    part['pending_kind'] = 'SOURCE_AMBIGUOUS'
    report = sc.validate(s, units, claims)
    assert report['pending'] == [{'target': 'u2/part0', 'pending_issue_index': 0}]
    assert report['semantic_status'] == 'NOT_REVIEWED'


def test_claimed_text_cannot_be_filed_as_non_claim():
    s, units, claims = case()
    s['source_coverage']['units'][0]['parts'][0] = {'segment_index': 0, 'disposition': 'NON_SUBSTANTIVE_LAYOUT',
                                                    'reason': 'TEST误归类', 'conclusion_ids': []}
    assert 'CLAIM_SPAN_DISMISSED' in codes(s, units, claims)


def test_same_limits_text_on_many_conclusions_is_rejected():
    s, units, claims = case()
    u = s['source_understanding']['sections'][0]
    s['sections'][0]['key_points'] += [{'claim_ids': ['c1'], 'point': 'x'} for _ in range(2)]
    s['evidence_index']['points'] += [dict(copy.deepcopy(s['evidence_index']['points'][0]), point_id=f's1.k{i}') for i in (2, 3)]
    u['conclusions'] += [dict(copy.deepcopy(u['conclusions'][0]), id=f'c{i}', point_ids=[f's1.k{i}'],
                              evidence_refs=[f's1.k{i}/e1']) for i in (2, 3)]
    s['evidence_index']['page_decisions'][0]['point_ids'] = ['s1.k1', 's1.k2', 's1.k3']
    with pytest.raises(ValueError, match='套话'):
        se.validate(s, units, claims, {'p1', 'p2'})


def test_one_phrase_standing_for_many_sentences_is_flagged_for_review():
    s, units, claims = case()
    text = '一。二。三。四。五。'
    parts = [{'segment_index': i, 'disposition': 'EXPRESSED', 'reason': 'TEST', 'conclusion_ids': ['s1/c1'],
              'expressions': [{'point_id': 's1.k1', 'summary_quote': '条件甲'}]} for i in range(5)]
    units = units + [{'id': 'u3', 'page_id': 'p1', 'text': text}]
    s['source_coverage']['source_units_sha256'] = sc.source_hash(units)
    s['source_coverage']['units'].append({'unit_id': 'u3', 'parts': parts})
    report = sc.audit(s, units, claims)
    assert report['structural_status'] == 'ACCOUNTED'
    assert report['warnings'][0]['code'] == 'REUSED_EXPRESSION' and len(report['warnings'][0]['parts']) == 5


def test_review_must_judge_every_part_and_explain_failures():
    s, units, claims = case()
    targets = sc.review_targets(s, units)
    assert [(t['target_id'], t['disposition']) for t in targets] == [('u1/part0', 'EXPRESSED'), ('u2/part0', 'SOURCE_METADATA')]
    assert targets[0]['source_text'] == units[0]['text'] and targets[0]['expressions'][0]['point_id'] == 's1.k1'
    with pytest.raises(ValueError, match='逐条判定'):
        sc.check_review(targets, [{'target_id': 'u1/part0', 'verdict': 'FULL'}])
    with pytest.raises(ValueError, match='判定须是'):
        sc.check_review(targets, [{'target_id': 'u1/part0', 'verdict': 'ACCEPTED'}, {'target_id': 'u2/part0', 'verdict': 'FULL'}])
    with pytest.raises(ValueError, match='写明'):
        sc.check_review(targets, [{'target_id': 'u1/part0', 'verdict': 'PARTIAL'}, {'target_id': 'u2/part0', 'verdict': 'ACCEPTED'}])
    partial = [{'target_id': 'u1/part0', 'verdict': 'PARTIAL', 'issue': 'TEST缺条件'}, {'target_id': 'u2/part0', 'verdict': 'ACCEPTED'}]
    with pytest.raises(ValueError, match='missing_facets'):
        sc.check_review(targets, partial)
    partial[0]['missing_facets'] = ['qualifier']
    with pytest.raises(ValueError, match='missing_facets'):
        sc.check_review(targets, partial)
    partial[0]['missing_facets'] = ['condition', 'modality']
    partial[0]['issue'] = '????????????'
    with pytest.raises(ValueError, match='损坏'):
        sc.check_review(targets, partial)
    partial[0]['issue'] = 'TEST缺条件'
    problems, ok = sc.check_review(targets, partial)
    assert [p['target_id'] for p in problems] == ['u1/part0'] and ok == ['u2/part0']
    assert problems[0]['missing_facets'] == ['condition', 'modality']
    points = sc.point_texts(s)
    bare = [{'target_id': 'u1/part0', 'verdict': 'FULL'}, {'target_id': 'u2/part0', 'verdict': 'ACCEPTED'}]
    with pytest.raises(ValueError, match='point_evidence'):
        sc.check_review(targets, bare, points)
    bare[0]['point_evidence'] = [{'point_id': 's1.k1', 'quote': '审核自己编的句子'}]
    with pytest.raises(ValueError, match='point_evidence'):
        sc.check_review(targets, bare, points)
    bare[0]['point_evidence'] = [{'point_id': 's1.k1', 'quote': '数值 < 0.7'}]
    assert sc.check_review(targets, bare, points) == ([], ['u1/part0', 'u2/part0'])


def test_earlier_v3_ledgers_keep_their_contract():
    s, units, claims = v3_case()
    assert s['source_coverage']['schema_version'] == sc.SCHEMA
    assert sc.audit(s, units, claims)['structural_status'] == 'ACCOUNTED'


def test_source_hash_detects_changed_text_and_new_units_but_not_order():
    s, units, _ = case()
    assert sc.source_hash(units) == sc.source_hash(list(reversed(units)))
    altered = copy.deepcopy(units); altered[0]['text'] += '新增例外'
    assert 'STALE_SOURCE' in codes(s, altered)
    assert 'UNACCOUNTED_UNIT' in codes(s, units + [{'id': 'u3', 'page_id': 'p2', 'text': '新增'}])


def test_scaffold_leaves_all_semantic_decisions_unassessed():
    s, units, _ = case(); s['source_coverage'] = sc.scaffold(s, units)
    report = sc.audit(s, units)
    assert report['structural_status'] == 'BLOCKED' and 'conclusions' not in s['source_coverage']
    assert {'UNACCOUNTED_TEXT', 'UNBOUND_CONCLUSION'} <= {i['code'] for i in report['issues']}
    s, units, _ = v3_case(); s['source_coverage'] = sc.scaffold(s, units)
    assert len([i for i in sc.audit(s, units)['issues'] if i['code'] == 'UNASSESSED_FACET']) == 6


def test_brief_hands_the_author_code_cut_sentences(store):
    w = T.read_all(store, summarised_raw(store))
    store.queue(w['id'], 'SUMMARY')
    t = store.claim(w['id'], 'author-v4', 'SUMMARY')
    b = t['brief']
    assert b['summary_algorithm'] == se.ALGORITHM
    assert b['result_contract']['source_coverage']['schema_version'] == sc.SCHEMA_V2
    unit = b['source_coverage_input']['units'][0]
    assert unit['segments'] and all({'index', 'start', 'end'} <= set(x) for x in unit['segments'])


def summarised_raw(store):
    w = store.create('虚构覆盖测试', T.OUTLINE, {'audience': '本科生'})
    for name, make in T.fx_.SOURCES.items():
        store.add_source(w['id'], name, make())
    return w['id']


def test_coverage_verdicts_become_ledger_blockers_for_the_author(store):
    w = summarised(store)
    store.queue(w['id'], 'SUMMARY_REVIEW')
    t = store.claim(w['id'], 'independent-v4', 'SUMMARY_REVIEW')
    assert t['brief']['coverage_targets']
    result = T.clear_summary_review(t['brief']['result_contract'])
    row = next(r for r in result['coverage_review'] if r['disposition'] == 'EXPRESSED')
    row['verdict'] = 'MISSING'
    with pytest.raises(WorkflowError, match='写明'):
        store.complete(w['id'], t['id'], t['lease_token'], result)
    row['issue'] = 'TEST：point正文没有这句的条件'
    result['coverage_review'].pop()
    with pytest.raises(WorkflowError, match='逐条判定'):
        store.complete(w['id'], t['id'], t['lease_token'], result)
    result = T.clear_summary_review(t['brief']['result_contract'])
    next(r for r in result['coverage_review'] if r['target_id'] == row['target_id']).update(verdict='MISSING', issue=row['issue'], point_evidence=[])
    w = store.complete(w['id'], t['id'], t['lease_token'], result)
    assert w['stage'] == 'SUMMARY_ISSUES'
    store.queue(w['id'], 'SUMMARY')
    again = store.claim(w['id'], 'author-A', 'SUMMARY')
    assert any(i['ref'] == row['target_id'] for i in again['brief']['review_issues'])
    assert again['brief']['revision_base'] == store.get(w['id'])['summary']


def test_closing_citation_stays_with_its_sentence_but_list_markers_do_not():
    text = '风险高出2.0倍。(377)\n下一句话。(363, 365–366)'
    assert sc.segments(text, 'sentence.v1') == [(0, 9), (9, 20), (20, 34)]      # v1: citation glued to the next sentence
    assert [text[a:b].strip() for a, b in sc.segments(text)] == ['风险高出2.0倍。(377)', '下一句话。(363, 365–366)']
    assert [x[0] for x in sc.segments('如下。(1) 第一项。')] == [0, 3]


def test_ledgers_cut_by_the_earlier_segmenter_keep_validating():
    s, units, claims = case()
    units = units + [{'id': 'u3', 'page_id': 'p1', 'text': '甲句。(12)\n'}]
    s['source_coverage']['source_units_sha256'] = sc.source_hash(units)
    part = {'disposition': 'EXPRESSED', 'reason': 'TEST', 'conclusion_ids': ['s1/c1'],
            'expressions': [{'point_id': 's1.k1', 'summary_quote': '条件甲'}]}
    s['source_coverage']['units'].append({'unit_id': 'u3', 'parts': [dict(part, segment_index=0)]})
    assert sc.audit(s, units, claims)['structural_status'] == 'ACCOUNTED'
    s['source_coverage']['segmenter'] = 'sentence.v1'
    s['source_coverage']['units'][-1]['parts'] = [dict(part, segment_index=0)]
    assert 'UNACCOUNTED_TEXT' in codes(s, units, claims)          # v1 left "(12)" as a second segment
    s['source_coverage']['units'][-1]['parts'] = [dict(part, segment_index=0), dict(part, segment_index=1)]
    assert sc.audit(s, units, claims)['structural_status'] == 'ACCOUNTED'
    s['source_coverage']['segmenter'] = 'sentence.v9'
    assert 'INVALID_SEGMENTER' in codes(s, units, claims)


def test_chunks_are_whole_consecutive_pages_within_session_limits():
    units = [{'id': f'u{p}{i}', 'page_id': f'p{p}', 'text': '句。' * 30} for p in range(1, 9) for i in range(2)]
    plan = sc.chunks(units, max_pages=5, max_segments=130)
    assert [c['page_ids'] for c in plan] == [['p1', 'p2'], ['p3', 'p4'], ['p5', 'p6'], ['p7', 'p8']]
    assert all(c['segments'] <= 130 for c in plan) and [u for c in plan for u in c['unit_ids']] == [u['id'] for u in units]
    single = sc.chunks(units[:2], max_segments=10)          # one oversized page is still one chunk, never split
    assert [c['page_ids'] for c in single] == [['p1']]


def test_chunk_progress_counts_only_registration_issues_of_its_units():
    s, units, claims = case()
    plan = [{'index': 0, 'page_ids': ['p1'], 'unit_ids': ['u1'], 'segments': 1},
            {'index': 1, 'page_ids': ['p2'], 'unit_ids': ['u2'], 'segments': 1}]
    assert [c['open_issues'] for c in sc.chunk_progress(s, units, claims, plan)] == [0, 0]
    s['source_coverage']['units'][1]['parts'].clear()
    assert [c['open_issues'] for c in sc.chunk_progress(s, units, claims, plan)] == [0, 1]


def test_chunked_summary_resumes_from_a_draft_in_a_new_session(store):
    w = T.read_all(store, summarised_raw(store))
    store.queue(w['id'], 'SUMMARY')
    t = store.claim(w['id'], 'author-v4', 'SUMMARY')
    plan = t['brief']['chunks']
    assert plan and [u for c in plan for u in c['unit_ids']] == [u['unit_id'] for u in t['brief']['source_coverage_input']['units']]
    full = T.with_understanding(store.get(w['id']), T.summary(store.get(w['id'])))
    partial = copy.deepcopy(full)
    first = set(plan[0]['unit_ids'])
    for row in partial['source_coverage']['units']:
        if row['unit_id'] not in first: row['parts'] = []
    with store.transaction(w['id'], 'TEST_EARLIER_ATTEMPTS') as raw:
        next(x for x in raw['tasks'] if x['id'] == t['id'])['attempts'] = 3
    ack = store.save_summary_draft(w['id'], t['id'], t['lease_token'], partial)
    assert ack['done_chunks'] == [0] and ack['chunks'] == len(plan) > 1
    with store.transaction(w['id'], 'TEST_SESSION_STOPS') as raw:      # the session ends; its lease runs out
        task = next(x for x in raw['tasks'] if x['id'] == t['id'])
        assert task['attempts'] == 0                                     # progress is not a failed attempt
        task['lease_until'] = 0
    again = store.claim(w['id'], 'author-v4b', 'SUMMARY')
    assert again['id'] == t['id'] and again['draft']['done_chunks'] == ack['done_chunks']
    assert again['draft']['summary']['source_coverage'] == partial['source_coverage']
    w = store.complete(w['id'], again['id'], again['lease_token'], full)
    assert w['summary_meta']['contributors'] == ['author-v4', 'author-v4b']
    store.queue(w['id'], 'SUMMARY_REVIEW')
    assert store.claim(w['id'], 'author-v4', 'SUMMARY_REVIEW') is None       # an earlier session's identity is an author too
    assert store.claim(w['id'], 'independent-v4', 'SUMMARY_REVIEW')


def test_draft_is_only_for_chunked_summary_tasks(store):
    w = T.read_all(store, summarised_raw(store))
    store.queue(w['id'], 'SUMMARY')
    t = store.claim(w['id'], 'author-v4', 'SUMMARY')
    with pytest.raises(WorkflowError, match='租约'):
        store.save_summary_draft(w['id'], t['id'], 'wrong-token', {})
    with pytest.raises(WorkflowError, match='结果对象'):
        store.save_summary_draft(w['id'], t['id'], t['lease_token'], [])


def test_sentence_review_is_checkpointed_by_chunk(store):
    w = summarised(store)
    store.queue(w['id'], 'SUMMARY_REVIEW')
    t = store.claim(w['id'], 'independent-v4', 'SUMMARY_REVIEW')
    plan = t['brief']['chunks']
    assert len(plan) > 1
    full = T.clear_summary_review(t['brief']['result_contract'])
    first = {u for u in plan[0]['unit_ids']}
    partial = dict(full, coverage_review=[r for r in full['coverage_review'] if r['target_id'].split('/')[0] in first])
    ack = store.save_summary_draft(w['id'], t['id'], t['lease_token'], partial)
    assert ack['done_chunks'] == [0]
    bad = dict(partial, coverage_review=[dict(r, point_evidence=[]) if r['verdict'] == 'FULL' else r for r in partial['coverage_review']])
    with pytest.raises(WorkflowError):                 # a draft that drops a finished chunk is refused
        store.save_summary_draft(w['id'], t['id'], t['lease_token'], bad)
    with store.transaction(w['id'], 'TEST_SESSION_STOPS') as raw:
        next(x for x in raw['tasks'] if x['id'] == t['id'])['lease_until'] = 0
    assert store.claim(w['id'], 'author-A', 'SUMMARY_REVIEW') is None              # the author still cannot pick it up
    again = store.claim(w['id'], 'independent-v4', 'SUMMARY_REVIEW')
    assert again['id'] == t['id'] and again['draft']['done_chunks'] == [0] and again['draft']['result'] == partial
    w = store.complete(w['id'], again['id'], again['lease_token'], full)
    assert w['summary_review']['reviewer'] == 'independent-v4'


def test_review_text_lost_to_encoding_is_refused(store):
    w = summarised(store)
    store.queue(w['id'], 'SUMMARY_REVIEW')
    t = store.claim(w['id'], 'independent-v4', 'SUMMARY_REVIEW')
    result = T.clear_summary_review(t['brief']['result_contract'])
    result['sections'][0].update(summary_verdict='PARTIAL', summary_issue='??????????????/?????')
    with pytest.raises(WorkflowError, match='summary_issue'):
        store.complete(w['id'], t['id'], t['lease_token'], result)
