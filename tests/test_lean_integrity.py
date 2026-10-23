"""Adversarial regressions for the lean workflow's deterministic content gate."""
from dataclasses import asdict
import pytest
from factdeck.facts import Fact, Derivation, verify
from factdeck.deck import check


def units(text):
    return [{"id": "u", "source_id": "s", "location": "p1", "text": text}]


@pytest.mark.parametrize("source,quote,display", [
    ("剂量分5 10 20三档", "510", ""),
    ("本品10mg每日一次", "本品1 0mg每日一次", ""),
    ("剂量5 10mg", "剂量5 10mg", "剂量510mg"),
])
def test_numeric_whitespace_cannot_create_or_split_a_number(source, quote, display):
    f = Fact("f", "u", quote, display=display)
    verify([f], [], units(source), {})
    assert f.status == "REJECTED"


def test_valid_quote_is_replaced_with_actual_source_slice():
    f = Fact("f", "u", "成人患者10mg")
    verify([f], [], units("成人\n患者10 mg"), {})
    assert f.status == "ACCEPTED" and f.quote == "成人\n患者10 mg"


@pytest.mark.parametrize("evidence", [[], ["missing"], ["f"]])
def test_confirmed_derivation_still_needs_independent_evidence(evidence):
    f = Fact("f", "u", "5mg", display="20mg", derivation="d")
    d = Derivation("d", "20mg", "test", evidence, confirmed=True)
    verify([f], [d], units("5mg"), {})
    assert f.status == "REJECTED" and d.problems


def test_derivation_cycles_and_dependants_are_rejected():
    fs = [Fact("a", "u", "5mg", display="20mg", derivation="d1"),
          Fact("b", "u", "5mg", display="20mg", derivation="d2")]
    ds = [Derivation("d1", "", "test", ["b"], confirmed=True),
          Derivation("d2", "", "test", ["a"], confirmed=True)]
    verify(fs, ds, units("5mg"), {})
    assert all(f.status == "REJECTED" for f in fs)


@pytest.mark.parametrize("source,display", [
    ("部分患者可获得缓解", "患者可获得缓解"),
    ("大约30%的患者有效", "30%的患者有效"),
    ("12/20例患者有效", "20例患者有效"),
    ("治疗12个月时复发率8%", "复发率8%"),
    ("may improve outcomes", "improve outcomes"),
    ("not recommended", "recommended"),
])
def test_qualifiers_and_numbers_cannot_be_dropped(source, display):
    f = Fact("f", "u", source, display=display)
    verify([f], [], units(source), {})
    assert f.status == "REJECTED"


def test_nested_content_is_checked_even_when_a_valid_lead_is_present():
    f = Fact("good", "u", "说明")
    verify([f], [], units("说明"), {})
    p = {"id": "p", "layout": "nested", "title": {"text": "层级"}, "lead": {"fact": "good"},
         "levels": [{"heading": {"fact": "missing"}, "items": [{"text": "12 mg"}]},
                    {"heading": {"fact": "good"}, "items": []}]}
    r = check({"pages": [p]}, {f.id: asdict(f)})
    assert r["errors"] >= 2
