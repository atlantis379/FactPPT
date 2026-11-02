"""figure.v1 and the asset manifest.  Nothing here knows a subject: the facts are about gearboxes on purpose.

A picture cannot be proved right, so every test is about the order of proof: what a spec may ask for, who may review
what, and that nothing ships on a promise.  No network: the provider is a stand-in.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from factdeck import assets as A

FACTS = {
    "g": {"quote": "齿轮箱内部包含行星齿轮和输出轴。"},
    "h": {"quote": "外壳位于行星齿轮的外侧。"},
    "x": {"quote": "润滑油需要每年更换。"},
}


def spec(**kw) -> dict:
    base = {"schema_version": A.SCHEMA, "id": "s1", "mode": "schematic",
            "elements": [{"name": "行星齿轮", "fact": "g"}, {"name": "外壳", "fact": "h"}],
            "relations": [{"from": "外壳", "to": "行星齿轮", "kind": "surrounds", "fact": "h"}]}
    base.update(kw)
    return base


def png(path: Path, colour=(40, 90, 200, 255), size=(64, 64)) -> bytes:
    Image.new("RGBA", size, colour).save(path)
    return path.read_bytes()


def manifest(tmp_path, role="illustration", provider="drawer") -> A.Manifest:
    m = A.Manifest(tmp_path)
    data = png(tmp_path / "src.png")
    m.add("fig", role, A.Picture(data, provider, "model-1"), spec=A.check_spec(spec(), FACTS), prompt="p", style="clinical_blue")
    return m


def good_reviews(m, aid="fig"):
    items = A.checklist(m.items[aid]["spec"])
    return {"has_text": False, "objects": ["齿轮"]}, {"answers": [{"id": c["id"], "answer": "yes"} for c in items]}


# ----------------------------------------------------------------------------------------------- the spec

def test_a_spec_is_resolved_against_its_sentences():
    assert [e["name"] for e in A.check_spec(spec(), FACTS)["elements"]] == ["行星齿轮", "外壳"]


def test_a_picture_may_not_be_asked_for_something_no_sentence_says():
    with pytest.raises(A.AssetError, match="不是这句里的词"):
        A.check_spec(spec(elements=[{"name": "涡轮", "fact": "g"}], relations=[]), FACTS)


def test_a_relation_needs_one_sentence_naming_both_ends():
    bad = [{"from": "外壳", "to": "行星齿轮", "kind": "surrounds", "fact": "g"}]
    with pytest.raises(A.AssetError, match="没有在同一句里说到"):
        A.check_spec(spec(relations=bad), FACTS)


def test_an_unknown_relation_or_mode_is_refused():
    with pytest.raises(A.AssetError, match="kind 须为"):
        A.check_spec(spec(relations=[{"from": "外壳", "to": "行星齿轮", "kind": "beats", "fact": "h"}]), FACTS)
    with pytest.raises(A.AssetError, match="mode 须为"):
        A.check_spec(spec(mode="poster"), FACTS)


def test_the_prompt_is_built_from_the_spec_and_the_pack_and_forbids_text():
    pack = A.styles()["clinical_blue"]
    a = A.prompt_for(A.check_spec(spec(), FACTS), pack)
    assert a == A.prompt_for(A.check_spec(spec(), FACTS), pack)
    assert "行星齿轮" in a and pack["image"]["rendering"] in a and "text" in a


def test_style_packs_hold_no_subject_matter():
    words = "".join(str(p) for p in A.styles().values())
    for w in ("肺", "血管", "COPD", "anatomy", "medical organ"):
        assert w not in words


# -------------------------------------------------------------------------------------------- the review

def test_a_picture_is_never_reviewed_by_the_vendor_that_drew_it(tmp_path):
    m = manifest(tmp_path)
    with pytest.raises(A.AssetError, match="须由另一家核对"):
        m.review("fig", "drawer", *good_reviews(m))


def test_the_checklist_covers_every_element_and_relation_and_anchor(tmp_path):
    ids = {c["id"] for c in A.checklist({**spec(), "anchors": {"a1": {"name": "外壳", "x": .2, "y": .3}}})}
    assert ids == {"e:行星齿轮", "e:外壳", "r:外壳|行星齿轮", "a:a1"}


def test_a_no_rejects_and_says_why(tmp_path):
    m = manifest(tmp_path)
    blind, ans = good_reviews(m)
    ans["answers"][-1]["answer"] = "no"
    e = m.review("fig", "reader", blind, ans)
    assert e["status"] == A.REJECTED and "核对未过" in e["review"]["reasons"][0]
    assert "未通过核对" in m.blockers("fig")[0]


def test_text_in_a_picture_rejects_it(tmp_path):
    m = manifest(tmp_path)
    blind, ans = good_reviews(m)
    assert m.review("fig", "reader", {**blind, "has_text": True}, ans)["status"] == A.REJECTED


def test_an_unanswered_item_does_not_pass(tmp_path):
    m = manifest(tmp_path)
    blind, ans = good_reviews(m)
    ans["answers"].pop()
    assert m.review("fig", "reader", blind, ans)["status"] == A.REJECTED


def test_unsure_and_beyond_reach_the_person(tmp_path):
    m = manifest(tmp_path)
    blind, ans = good_reviews(m)
    ans["answers"][0]["answer"] = "unsure"
    ans["beyond"] = ["轴承"]
    e = m.review("fig", "reader", blind, ans)
    assert e["status"] == A.REVIEWED and e["review"]["unsure"] and e["review"]["beyond"] == ["轴承"]


# ------------------------------------------------------------------------------------------- the sign-off

def test_a_generated_picture_cannot_ship(tmp_path):
    m = manifest(tmp_path)
    assert "等待主讲人确认" in m.blockers("fig")[0]
    with pytest.raises(A.AssetError, match="还没有通过核对"):
        m.sign("fig", "张医生")


def test_a_reviewed_illustration_still_waits_for_a_signature(tmp_path):
    m = manifest(tmp_path)
    m.review("fig", "reader", *good_reviews(m))
    assert "等待主讲人确认" in m.blockers("fig")[0]
    m.sign("fig", "主讲人")
    assert m.blockers("fig") == [] and m.items["fig"]["status"] == A.SIGNED


def test_a_changed_file_voids_the_signature(tmp_path):
    m = manifest(tmp_path)
    m.review("fig", "reader", *good_reviews(m))
    m.sign("fig", "主讲人")
    png(Path(m.items["fig"]["file"]), (200, 40, 40, 255))
    assert "已被改动" in m.blockers("fig")[0]


def test_a_backdrop_needs_a_review_but_no_signature(tmp_path):
    m = A.Manifest(tmp_path)
    m.add("bg", "backdrop", A.Picture(png(tmp_path / "s.png"), "drawer", "m"), spec=None, prompt="p", style="s")
    assert "还没有核对" in m.blockers("bg")[0]
    m.review("bg", "reader", {"has_text": False}, {"answers": []})
    assert m.blockers("bg") == []


def test_an_illustration_needs_a_spec(tmp_path):
    m = A.Manifest(tmp_path)
    with pytest.raises(A.AssetError, match="图意规格"):
        m.add("x", "illustration", A.Picture(png(tmp_path / "s.png"), "d", "m"), spec=None, prompt="p", style="s")


def test_a_figure_from_the_source_needs_its_licence_and_a_signature(tmp_path):
    src = tmp_path / "orig.png"
    png(src)
    m = A.Manifest(tmp_path / "m")
    with pytest.raises(A.AssetError, match="授权"):
        m.adopt("o", "illustration", src, licence="")
    m.adopt("o", "illustration", src, licence="原文图 2，已获授权")
    assert "等待主讲人确认" in m.blockers("o")[0]
    m.sign("o", "主讲人")
    assert m.blockers("o") == []


def test_the_manifest_survives_a_reload(tmp_path):
    manifest(tmp_path)
    assert A.Manifest(tmp_path).items["fig"]["provider"] == "drawer"


# ---------------------------------------------------------------------------------------------- the style

def test_a_picture_far_from_the_anchor_is_named(tmp_path):
    m = manifest(tmp_path)
    m.set_anchor("fig")
    data = png(tmp_path / "warm.png", (220, 60, 20, 255))
    m.add("other", "illustration", A.Picture(data, "drawer", "m"), spec=A.check_spec(spec(), FACTS), prompt="p", style="s")
    assert any("warmth" in x for x in m.style_issues("other"))


def test_a_picture_near_the_anchor_passes_and_the_anchor_is_not_compared_with_itself(tmp_path):
    m = manifest(tmp_path)
    m.set_anchor("fig")
    data = png(tmp_path / "near.png", (46, 96, 205, 255))
    m.add("other", "illustration", A.Picture(data, "drawer", "m"), spec=A.check_spec(spec(), FACTS), prompt="p", style="s")
    assert m.style_issues("other") == [] and m.style_issues("fig") == []


def test_normalize_fits_the_slot_and_clears_a_plain_background(tmp_path):
    src = tmp_path / "s.png"
    im = Image.new("RGBA", (100, 50), (250, 250, 250, 255))
    im.paste((10, 10, 10, 255), (40, 15, 60, 35))
    im.save(src)
    dst = tmp_path / "d.png"
    A.normalize(src, dst, (64, 64), key_background=True)
    out = Image.open(dst)
    assert out.size == (64, 64) and out.getpixel((0, 0))[3] == 0 and out.getpixel((32, 32))[3] == 255
