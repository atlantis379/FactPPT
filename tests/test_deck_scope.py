"""Prefix generation keeps the full spec and preserves all content/review gates.

All sources and review records in these tests are invented protocol fixtures.
"""
import copy
import json

import pytest

from app.deck_scope import context, scope_of
from app.deckflow import Store, WorkflowError, checked, digest, deck_input
from test_deckflow import to_deck, finish_gates


def scoped_flow(tmp_path):
    store = Store(tmp_path / 'data')
    w = finish_gates(store, to_deck(store))
    # Migrate this old, plain-outline test fixture to explicit points. No new facts.
    with store.transaction(w['id'], 'TEST_STRUCTURED_POINTS') as ww:
        for o in ww['outline']:
            o['points'] = [{'id': o['id'] + '.1', 'text': o['text']}]
        for s in ww['summary']['sections']:
            if s.get('outline_id'):
                s['point_coverage'] = [{'point_id': s['outline_id'] + '.1', 'unit_ids': s.get('unit_ids', [])}]
        # Fixture binding changes are not an approval of any real content.
        ww['summary']['input_sha256'] = __import__('app.deckflow', fromlist=['input_hash']).input_hash(ww)
        ww['facts']['result']['summary_sha256'] = digest(ww['summary'])
        ww['facts']['input_sha256'] = __import__('app.deckflow', fromlist=['facts_input']).facts_input(ww)
        ww['deck']['input_sha256'] = deck_input(ww)
    w = store.get(w['id'])
    d = copy.deepcopy(w['deck']['result'])
    for p in d['pages'][:4]:
        if p.get('outline_ids'):
            p['point_ids'] = [x + '.1' for x in p['outline_ids']]
    d['generation_scope'] = {'kind': 'PREFIX', 'page_count': 4, 'total_pages': 9,
                             'base_page_ids': [p['id'] for p in d['pages']]}
    # Restore real test-record summary approval after the fixture-only migration.
    from test_deckflow import approve
    approve(store, w, 'content')
    w = store.get(w['id'])
    d['facts_sha256'] = w['facts']['result_sha256']
    with store.transaction(w['id'], 'TEST_SCOPED_DECK') as ww:
        store.accept_deck(ww, d, 'author-A')
    return store, store.get(w['id'])


def test_scope_preserves_full_spec_and_reports_excluded_coverage(tmp_path):
    store, w = scoped_flow(tmp_path)
    c = checked(w)
    assert len(w['deck']['result']['pages']) == 9
    assert len(c['pages']) == 4 and c['errors'] == 0
    assert c['scope']['complete_deck'] is False
    assert set(c['scope']['outside_scope_points']) == {'outline_2.1', 'outline_3.1'}
    assert {r['point_id'] for r in c['coverage']['points']} == {'outline_1.1'}
    brief = store.brief(w, 'SEMANTIC_REVIEW', 'COVERAGE')
    assert [r['page_id'] for r in brief['result_contract']['pages']] == ['cover', 'part1', 'overview', 'criteria']
    assert brief['scope']['complete_deck'] is False
    with pytest.raises(WorkflowError, match='之外'):
        store.accept_semantic(w, brief['result_contract'], 'author-A', 'COVERAGE')
    with pytest.raises(WorkflowError, match='整套交付'):
        store.export(w['id'])


def test_outside_pages_cannot_be_changed_in_prefix_run(tmp_path):
    store, w = scoped_flow(tmp_path)
    d = copy.deepcopy(w['deck']['result']); d['facts_sha256'] = w['facts']['result_sha256']
    d['pages'][5]['title'] = {'text': 'Changed'}
    with pytest.raises(WorkflowError, match='范围之外'):
        store.accept_deck(w, d, 'author-A')


def test_prefix_needs_explicit_request_and_semantic_review(tmp_path, monkeypatch):
    store, w = scoped_flow(tmp_path)
    with pytest.raises(WorkflowError, match='明确指定'):
        store.start_generation(w['id'])
    with pytest.raises(WorkflowError, match='独立语义'):
        store.start_generation(w['id'], 4)
    import test_deckflow as T
    T.semantic_review(store, w['id'])
    def prepare(deck, facts, sources, out, *args, **kwargs):
        assert len(deck['pages']) == 4
        out.mkdir(parents=True, exist_ok=True)
        from test_visual_generation import model
        data = {'models': [model(p['id']) for p in deck['pages']], 'notes': ['fixture'] * 4, 'font': 'Microsoft YaHei'}
        (out / 'native_model.json').write_text(json.dumps(data), encoding='utf8')
    monkeypatch.setattr('factdeck.render.render', prepare)
    w = store.start_generation(w['id'], 4)
    assert len(w['generation']['pages']) == 4
    assert len(w['deck']['result']['pages']) == 9
    assert w['generation_status']['scope']['page_count'] == 4
    assert w['generation_status']['complete_deck'] is False
    assert not w['render'] and not w['style_approval'] and not w['page_reviews']


@pytest.mark.parametrize('value', [{}, {'kind': 'PREFIX'}, {'kind': 'PREFIX', 'page_count': True, 'total_pages': 2, 'base_page_ids': ['a', 'b']}])
def test_malformed_scopes_cannot_fall_back_to_whole_deck(value):
    with pytest.raises(WorkflowError):
        scope_of({'pages': [{'id': 'a'}, {'id': 'b'}], 'generation_scope': value})
