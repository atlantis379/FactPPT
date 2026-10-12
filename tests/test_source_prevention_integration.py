import copy
import pytest
from app.deckflow import Store, all_units, WorkflowError


def workflow():
    return {'sources':[{'id':'S01','sha256':'a'*64,'units':[],
        'transcriptions':[{'id':'S01:p1:c1','source_id':'S01','page_id':'S01:p1',
                          'location':'page 1 cell 1','text':'CATTM','needs_confirmation':True}]}],
        'confirmations':{'transcriptions':{}}}


def test_correction_is_a_pending_unit_and_never_replaces_the_original(tmp_path):
    store = Store(tmp_path)
    w = workflow()
    source_before = copy.deepcopy(w['sources'])
    store._transcription_proposals(w,[{'source_unit_id':'S01:p1:c1','source_sha256':'a'*64,
        'text':'CAT™','reason':'Original-page glyph correction','confirmed':True}],'author-A')
    assert w['sources'] == source_before
    correction = all_units(w)[-1]
    assert correction['id'] == 'correction:S01:p1:c1'
    assert correction['needs_confirmation'] is True
    assert correction['text'] == 'CAT™' and correction['original_text'] == 'CATTM'


def test_correction_rejects_a_different_source_version(tmp_path):
    with pytest.raises(WorkflowError):
        Store(tmp_path)._transcription_proposals(workflow(),[{'source_unit_id':'S01:p1:c1',
            'source_sha256':'b'*64,'text':'CAT™','reason':'correction'}],'author-A')


def test_only_recorded_human_confirmation_releases_correction(tmp_path):
    w = workflow()
    Store(tmp_path)._transcription_proposals(w,[{'source_unit_id':'S01:p1:c1','source_sha256':'a'*64,
        'text':'CAT™','reason':'glyph correction'}],'author-A')
    w['confirmations']['transcriptions']['correction:S01:p1:c1'] = {'decision':'CONFIRM','text':'CAT™'}
    assert all_units(w)[-1]['needs_confirmation'] is False
    assert all_units(w)[0]['needs_confirmation'] is True


def test_new_projects_reject_unverified_transcription_before_fact_store(tmp_path):
    import test_deckflow as T
    s = Store(tmp_path)
    assert s.create('NEW-POLICY-FIXTURE')['source_evidence_policy'] == 'verified-transcription.v1'
    legacy = T.to_deck(s)
    legacy['source_evidence_policy'] = 'verified-transcription.v1'
    with pytest.raises(WorkflowError, match='未核定的视觉转录'):
        s.accept_facts(legacy, T.facts_result(legacy), 'FIXTURE-WRITER')
