"""Actual failed stability evidence must not qualify an extension candidate."""
import pytest
from tools import visual_prompt_lab as lab


@pytest.mark.parametrize('winner,errors', [(None, []), ('editorial', ['UNSOURCED_CURVE_AXES'])])
def test_extension_rejects_unqualified_actual_image_review(tmp_path, monkeypatch, winner, errors):
    monkeypatch.setattr(lab,'ROOT',tmp_path)
    monkeypatch.setattr(lab,'LAB',tmp_path/'lab')
    lab.write(lab.LAB/'common_input.json',{'frozen':True})
    image=tmp_path/'actual.png';image.write_bytes(b'actual output fixture')
    with lab.db() as db:
        db.execute('INSERT INTO trials(id,result_path) VALUES(?,?)',('stability_editorial_09_r2','actual.png'))
    review=tmp_path/'review.json'
    lab.write(review,{'source_sha256':lab.file_sha(lab.LAB/'common_input.json'),'provisional_winner':winner,
        'trials':[{'trial_id':'stability_editorial_09_r2','image_sha256':lab.file_sha(image),'viewed':True,
                   'strategy':'editorial','hard_error_ids':errors}]})
    with pytest.raises(ValueError,match='winner|accuracy blockers'):
        lab.add_phase('extension',['editorial'],review)
    with lab.db() as db:
        assert db.execute("SELECT COUNT(*) FROM trials WHERE phase='extension'").fetchone()[0]==0
