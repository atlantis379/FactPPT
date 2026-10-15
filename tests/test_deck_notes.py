"""Complete-notes summaries (model_understanding.v4) reach the deck without selection loss. Synthetic data only."""
from factdeck.deck import _key_point_coverage, teaching_notes
from app.deck_scope import check_spec

KP = {"s1.k1": "要点一全文：条件甲时数值<0.7。", "s1.k2": "要点二全文，尚未证明可区分。", "s2.k1": "要点三全文。"}


def run(pages):
    errors, coverage = [], {}
    _key_point_coverage(pages, KP, coverage, errors.append)
    return errors, coverage


def test_every_key_point_must_be_taught_and_may_span_pages():
    pages = [{"id": "cover", "layout": "cover"},
             {"id": "a", "layout": "bullets", "key_point_ids": ["s1.k1"]},
             {"id": "b", "layout": "cards", "key_point_ids": ["s1.k1", "s1.k2"]}]
    errors, coverage = run(pages)
    assert len(errors) == 1 and "s2.k1" in errors[0] and "不得删减" in errors[0]
    pages.append({"id": "c", "layout": "flow", "key_point_ids": ["s2.k1"]})
    errors, coverage = run(pages)
    assert not errors
    assert {r["key_point_id"]: r["pages"] for r in coverage["key_points"]}["s1.k1"] == ["a", "b"]


def test_content_pages_must_name_valid_key_points():
    errors, _ = run([{"id": "a", "layout": "bullets"}, {"id": "b", "layout": "bullets", "key_point_ids": ["s9.k9", *KP]}])
    assert any("a：内容页需用 key_point_ids" in e for e in errors)
    assert any("s9.k9" in e for e in errors)


def test_speaker_notes_carry_the_full_summary_text_verbatim():
    pages = [{"id": "cover", "layout": "cover"}, {"id": "a", "layout": "cards", "key_point_ids": ["s1.k2", "s1.k1"]}]
    notes = teaching_notes(pages, KP)
    assert list(notes) == ["a"]
    assert notes["a"] == "〔s1.k2〕要点二全文，尚未证明可区分。\n\n〔s1.k1〕要点一全文：条件甲时数值<0.7。"


def test_target_pages_do_not_pressure_a_complete_notes_deck():
    deck = {"pages": [{"id": "a", "layout": "statement", "title": {"text": "标题"}, "statement": {"text": "说明"},
                       "key_point_ids": list(KP)}]}
    plain = check_spec(deck, {}, [], None, None, {"target_pages": 20}, None)
    notes = check_spec(deck, {}, [], None, None, {"target_pages": 20}, None, key_points=KP)
    assert any("相差较大" in x for x in plain["warnings"])
    assert not any("相差较大" in x for x in notes["warnings"])
