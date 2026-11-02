"""argument.v2 — assertions are references, and the page count comes from judgements.

The errors at the top are the ones argument.v1 passed: a model's prose, tested by looking for tokens in the cited
sentence.  They are refused here by construction, because an assertion can no longer be written.
"""
from __future__ import annotations

import pytest

from factdeck import argument as A
from factdeck import shown

FACTS = {
    "no": {"quote": "A组患者不建议使用吸入性糖皮质激素。"},
    "may": {"quote": "既往吸烟者可以考虑加用阿奇霉素，治疗反应个体差异大。"},
    "over": {"quote": "超过70%的患者未确诊，30%已确诊。"},
    "abx": {"quote": "对于有脓痰、既往肺部感染史等的患者，推荐抗生素治疗总疗程为5天。"},
    "ster": {"quote": "对于中度/重度急性加重的患者，推荐使用全身性糖皮质激素，疗程不超过5天。"},
}


def spec(*claims) -> dict:
    return {"schema_version": A.SCHEMA, "claims": list(claims)}


def say(**ref) -> dict:
    return {"say": ref}


@pytest.mark.parametrize("ref", [
    {"fact": "no", "show": "A组患者建议使用吸入性糖皮质激素"},          # the negation removed
    {"fact": "may", "show": "既往吸烟者加用阿奇霉素"},                  # the modality removed
    {"fact": "over", "show": "70%的患者未确诊"},                        # the bound removed
    {"fact": "over", "show": "不足70%的患者未确诊"},                    # the bound flipped
    {"fact": "over", "show": "30%的患者未确诊"},                        # the number moved to another subject
    {"fact": "ster", "show": "推荐使用全身性糖皮质激素，疗程5天"},      # 「不超过」rounded away
])
def test_an_assertion_cannot_change_what_its_sentence_says(ref):
    with pytest.raises(A.ArgumentError):
        A.check(spec(say(**ref)), FACTS)


def test_an_assertion_cannot_be_written_at_all():
    with pytest.raises(A.ArgumentError, match="不能直接写成文字"):
        A.check(spec({"say": "全球70%的成人患者未被确诊"}), FACTS)


def test_a_faithful_excerpt_is_an_assertion():
    res = A.check(spec(say(fact="abx", show="推荐抗生素治疗总疗程为5天"), say(fact="no")), FACTS)
    assert [c["text"] for c in res["claims"]] == ["推荐抗生素治疗总疗程为5天", FACTS["no"]["quote"]]
    assert res["pending"] == []


def test_a_synthesis_waits_for_a_person():
    ref = {"derived": "抗生素与激素疗程都围绕5天", "from": ["abx", "ster"]}
    res = A.check(spec(say(**ref)), FACTS)
    assert res["pending"][0]["text"] == ref["derived"]
    done = A.check(spec(say(**ref)), FACTS, confirmed={res["pending"][0]["digest"]})
    assert done["pending"] == []


def test_a_confirmation_covers_these_words_over_these_sentences_only():
    d = shown.digest("抗生素疗程5天", ["abx"], FACTS)
    assert d != shown.digest("抗生素疗程7天", ["abx"], FACTS)
    assert d != shown.digest("抗生素疗程5天", ["abx"], {"abx": {"quote": "抗生素疗程为7天。"}})


def test_an_unknown_sentence_and_a_repeated_assertion_are_refused():
    with pytest.raises(A.ArgumentError, match="引用了不存在的句子"):
        A.check(spec(say(fact="nope")), FACTS)
    with pytest.raises(A.ArgumentError, match="是同一句"):
        A.check(spec(say(fact="no"), say(fact="no")), FACTS)


# ------------------------------------------------------------------------------------ the pages

def claims(*ids) -> list[dict]:
    return [{"id": i} for i in ids]


def test_pages_partition_the_assertions():
    assert A.partition([{"covers": ["a", "b"]}, {"covers": ["c"]}], claims("a", "b", "c")) == 2


@pytest.mark.parametrize("pages,msg", [
    ([{"covers": ["a"]}], "没有落到任何一页"),
    ([{"covers": ["a", "b"]}, {"covers": ["b"]}], "落在两页上"),
    ([{"covers": ["a", "b", "z"]}], "清单里没有"),
])
def test_a_merge_may_not_lose_or_repeat_an_assertion(pages, msg):
    with pytest.raises(A.ArgumentError, match=msg):
        A.partition(pages, claims("a", "b"))


def test_the_page_count_follows_from_the_judgements():
    assert "成立" in A.verdict(21, A.page_range(21, minutes=20))
    rng = A.page_range(13)
    assert (rng["low"], rng["high"], rng["sections"]) == (13, 17, 4)
    assert "不成立" in A.verdict(20, rng) and "太挤" in A.verdict(6, rng)


def test_the_clock_caps_the_page_count():
    rng = A.page_range(40, minutes=20)
    assert (rng["high"], rng["time_max"], rng["over"]) == (24, 24, 16)
    assert "讲不完" in A.verdict(40, rng) and "删掉 16 个" in A.verdict(40, rng)
