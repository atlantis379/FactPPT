import json
from pathlib import Path
from tools.publish_visual_prompt_lab import current_native_review, LAB
from tools import publish_visual_prompt_lab as publisher


def test_replaced_picture_invalidates_previous_native_visual_review():
    native=LAB/'native_textbook'
    review=json.loads((native/'final_visual_review.json').read_text(encoding='utf-8'))
    assert current_native_review(native,review)
    review['slides'][0]['native_image_sha256']='0'*64
    assert not current_native_review(native,review)


def test_missing_page_is_not_a_six_page_review():
    native=LAB/'native_textbook'
    review=json.loads((native/'final_visual_review.json').read_text(encoding='utf-8'))
    review['slides'].pop()
    assert not current_native_review(native,review)


def test_human_style_confirmation_is_invalidated_by_changed_bound_asset(monkeypatch):
    assert publisher.current_style_confirmation() is not None
    original=publisher.file_sha
    def changed(path):
        return '0'*64 if Path(path).name=='slide04.png' else original(path)
    monkeypatch.setattr(publisher,'file_sha',changed)
    assert publisher.current_style_confirmation() is None
