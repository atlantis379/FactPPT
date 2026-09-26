"""Render-readback verification: the defect family, one positive and one negative each.

The fixtures are SYNTHESISED, not copied from any single deck. The GOLD 2026 audit
found one instance of the reading-order defect (A04: a two-column placement read
1->3->2->4); it is reproduced here as one witness of the class, together with a
clean variant that must pass, so the checker is shown to discriminate rather than
merely to fire.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.render_readback import (DEFAULT_CANVAS, compute_visual_order,  # noqa: E402
                                 contract_from_plan, verify_render)

EMU = 9525


def make_deck(tmp_path: Path, pages, *, canvas=DEFAULT_CANVAS, filename="deck.pptx") -> Path:
    """paint a .pptx from a simple spec: pages = [[(name, box, text), ...], ...]

    List order is z-order (later = on top), exactly as PowerPoint stacks shapes.
    """
    from pptx import Presentation
    from pptx.util import Emu
    presentation = Presentation()
    presentation.slide_width = Emu(canvas[0] * EMU)
    presentation.slide_height = Emu(canvas[1] * EMU)
    blank = presentation.slide_layouts[6]
    for page in pages:
        slide = presentation.slides.add_slide(blank)
        for name, box, text in page:
            shape = slide.shapes.add_textbox(Emu(int(box[0] * EMU)), Emu(int(box[1] * EMU)),
                                             Emu(int(box[2] * EMU)), Emu(int(box[3] * EMU)))
            shape.name = name
            shape.text_frame.text = text
    target = tmp_path / filename
    presentation.save(str(target))
    return target


def quad_contract(order=("n1", "n2", "n3", "n4")) -> dict:
    """A 2x2 numbered grid whose page DECLARES the reading order 1,2,3,4.

    Reading order is a page-level declaration (in the app it comes from the page's
    own claim sequence), never the element array order -- that array is a
    construction order and using it would invent defects.
    """
    boxes = {"n1": [80, 200, 480, 180], "n2": [640, 200, 480, 180],
             "n3": [80, 420, 480, 180], "n4": [640, 420, 480, 180]}
    objects = [{"name": n, "box": boxes[n], "text": n, "has_geometry": True}
               for n in order]
    return {
        "canvas": list(DEFAULT_CANVAS),
        "pages": [{"page_id": "p1", "objects": objects, "mandatory": [], "exact_text": [],
                   "reading_order": list(order), "roles": {}}],
    }


# --------------------------------------------------------------- the positive
def test_row_major_placement_matches_the_declared_reading_order(tmp_path):
    contract = quad_contract()
    deck = make_deck(tmp_path, [[
        ("n1", [80, 200, 480, 180], "n1"),
        ("n2", [640, 200, 480, 180], "n2"),
        ("n3", [80, 420, 480, 180], "n3"),
        ("n4", [640, 420, 480, 180], "n4"),
    ]])
    result = verify_render(deck, contract)
    assert result["status"] == "PASS", result["issues"]
    assert result["issues"] == []


# ------------------------------------------- the A04 witness (real defect class)
def test_column_major_placement_reads_1_3_2_4_and_is_caught(tmp_path):
    """GOLD audit A04 reproduced: the reader sees 1 -> 3 -> 2 -> 4."""
    contract = quad_contract()
    deck = make_deck(tmp_path, [[
        ("n1", [80, 200, 480, 180], "n1"),      # top-left   = 1
        ("n3", [640, 200, 480, 180], "n3"),     # top-right  = 3   <- out of order
        ("n2", [80, 420, 480, 180], "n2"),      # bottom-left= 2
        ("n4", [640, 420, 480, 180], "n4"),     # bottom-right = 4
    ]])
    result = verify_render(deck, contract)
    assert result["status"] == "BLOCK"
    codes = {issue["code"] for issue in result["issues"]}
    assert "READING_ORDER_MISMATCH" in codes
    order_issue = next(i for i in result["issues"] if i["code"] == "READING_ORDER_MISMATCH")
    assert order_issue["detail"]["declared"] == ["n1", "n2", "n3", "n4"]
    assert order_issue["detail"]["rendered"] == ["n1", "n3", "n2", "n4"]


def test_visual_order_helper_is_row_major_and_ltr():
    shapes = [
        {"name": "b", "box": [640, 200, 480, 180]},
        {"name": "a", "box": [80, 200, 480, 180]},
        {"name": "d", "box": [640, 420, 480, 180]},
        {"name": "c", "box": [80, 420, 480, 180]},
    ]
    assert compute_visual_order(shapes) == ["a", "b", "c", "d"]


def test_tall_decorative_bar_does_not_drag_the_title_into_the_header_band():
    """Regression from a real built deck.

    The native builder draws an 8x76 accent bar beside the header. Judging bands by
    vertical overlap merged the title (top=78) into the header row (top=42) and
    produced a READING_ORDER_MISMATCH that no reader would experience. Bands are
    therefore keyed on TOP edges.
    """
    shapes = [
        {"name": "accent", "box": [64, 42, 8, 76]},
        {"name": "page-number", "box": [88, 42, 44, 24]},
        {"name": "visual-type", "box": [138, 42, 430, 24]},
        {"name": "title", "box": [88, 78, 1120, 58]},
        {"name": "primary", "box": [88, 146, 1120, 58]},
    ]
    assert compute_visual_order(shapes) == [
        "accent", "page-number", "visual-type", "title", "primary"]


def test_small_top_misalignment_stays_in_one_band():
    """Real designs are not pixel-aligned; a few pixels must not split a row."""
    shapes = [
        {"name": "a", "box": [80, 200, 480, 180]},
        {"name": "b", "box": [640, 204, 480, 180]},   # 4px lower
    ]
    assert compute_visual_order(shapes) == ["a", "b"]


def test_tall_left_column_is_not_merged_into_one_row():
    """A tall object must not swallow a distant neighbour into the same band."""
    shapes = [
        {"name": "tall", "box": [80, 100, 300, 520]},
        {"name": "low", "box": [640, 420, 300, 120]},
    ]
    assert compute_visual_order(shapes) == ["tall", "low"]


# ------------------------------------------------------------- remaining defects
def test_slide_count_mismatch_is_caught(tmp_path):
    contract = quad_contract()          # declares exactly one page
    deck = make_deck(tmp_path, [[("n1", [80, 200, 480, 180], "n1")],
                                [("n1", [80, 200, 480, 180], "n1")]])   # delivers two
    result = verify_render(deck, contract)
    assert "SLIDE_COUNT_MISMATCH" in {i["code"] for i in result["issues"]}


def test_mandatory_object_missing_is_caught(tmp_path):
    contract = quad_contract()
    contract["pages"][0]["mandatory"] = ["n2"]
    deck = make_deck(tmp_path, [[
        ("n1", [80, 200, 480, 180], "n1"),
        ("n3", [80, 420, 480, 180], "n3"),
        ("n4", [640, 420, 480, 180], "n4"),
    ]])
    result = verify_render(deck, contract)
    issue = next(i for i in result["issues"] if i["detail"].get("object") == "n2")
    assert issue["code"] == "MANDATORY_OBJECT_MISSING"
    assert issue["severity"] == "BLOCK"
    assert result["status"] == "BLOCK"


def test_any_declared_object_missing_from_the_file_blocks_delivery(tmp_path):
    """A declared object absent from the render is a broken promise, not a warning.

    The MANDATORY/EXPECTED distinction routes the fix; it does not soften the
    verdict, because shipping a deck that silently dropped declared content is the
    failure mode this verifier exists to catch.
    """
    contract = quad_contract()
    deck = make_deck(tmp_path, [[
        ("n1", [80, 200, 480, 180], "n1"),
        ("n2", [640, 200, 480, 180], "n2"),
        ("n3", [80, 420, 480, 180], "n3"),
    ]])
    result = verify_render(deck, contract)
    issue = next(i for i in result["issues"] if i["detail"].get("object") == "n4")
    assert issue["code"] == "EXPECTED_OBJECT_MISSING"
    assert issue["severity"] == "BLOCK"
    assert result["status"] == "BLOCK"


def test_object_off_canvas_is_caught(tmp_path):
    contract = quad_contract()
    contract["pages"][0]["objects"] = [
        {"name": "wide", "box": [80, 200, 1400, 180], "text": "wide", "has_geometry": True}]
    deck = make_deck(tmp_path, [[("wide", [80, 200, 1400, 180], "wide")]])
    result = verify_render(deck, contract)
    assert "OBJECT_OFF_CANVAS" in {i["code"] for i in result["issues"]}
    assert result["status"] == "BLOCK"


def test_canvas_mismatch_is_caught(tmp_path):
    contract = quad_contract()
    deck = make_deck(tmp_path, [[("n1", [80, 200, 480, 180], "n1")]],
                     canvas=(1024, 768))
    result = verify_render(deck, contract)
    assert "RENDER_CANVAS_MISMATCH" in {i["code"] for i in result["issues"]}


def test_exact_text_missing_is_caught(tmp_path):
    """A locked threshold must be visible on the slide, not merely declared."""
    contract = quad_contract()
    contract["pages"][0]["exact_text"] = ["20%"]
    deck = make_deck(tmp_path, [[
        ("n1", [80, 200, 480, 180], "n1"),
        ("n2", [640, 200, 480, 180], "n2"),
        ("n3", [80, 420, 480, 180], "n3"),
        ("n4", [640, 420, 480, 180], "n4"),
    ]])
    result = verify_render(deck, contract)
    assert "EXACT_TEXT_MISSING" in {i["code"] for i in result["issues"]}


def test_exact_text_present_passes(tmp_path):
    contract = quad_contract()
    contract["pages"][0]["exact_text"] = ["20%"]
    deck = make_deck(tmp_path, [[
        ("n1", [80, 200, 480, 180], "risk threshold 20%"),
        ("n2", [640, 200, 480, 180], "n2"),
        ("n3", [80, 420, 480, 180], "n3"),
        ("n4", [640, 420, 480, 180], "n4"),
    ]])
    contract["pages"][0]["objects"][0]["text"] = "risk threshold 20%"
    assert verify_render(deck, contract)["status"] == "PASS"


def test_text_truncated_is_caught(tmp_path):
    contract = quad_contract()
    deck = make_deck(tmp_path, [[
        ("n1", [80, 200, 480, 180], "2026 GOLD"),
        ("n2", [640, 200, 480, 180], "n2"),
        ("n3", [80, 420, 480, 180], "n3"),
        ("n4", [640, 420, 480, 180], "n4"),
    ]])
    contract["pages"][0]["objects"][0]["text"] = "2026 GOLD global strategy update"
    result = verify_render(deck, contract)
    assert "TEXT_TRUNCATED" in {i["code"] for i in result["issues"]}
    assert result["status"] == "BLOCK"


def test_empty_text_object_is_caught(tmp_path):
    contract = quad_contract()
    deck = make_deck(tmp_path, [[
        ("n1", [80, 200, 480, 180], ""),
        ("n2", [640, 200, 480, 180], "n2"),
        ("n3", [80, 420, 480, 180], "n3"),
        ("n4", [640, 420, 480, 180], "n4"),
    ]])
    result = verify_render(deck, contract)
    assert "EMPTY_TEXT_OBJECT" in {i["code"] for i in result["issues"]}


def test_unknown_object_is_reported_as_soft(tmp_path):
    contract = quad_contract()
    deck = make_deck(tmp_path, [[
        ("n1", [80, 200, 480, 180], "n1"),
        ("n2", [640, 200, 480, 180], "n2"),
        ("n3", [80, 420, 480, 180], "n3"),
        ("n4", [640, 420, 480, 180], "n4"),
        ("injected", [640, 620, 480, 60], "unexpected"),
    ]])
    result = verify_render(deck, contract)
    assert "UNKNOWN_OBJECT" in {i["code"] for i in result["issues"]}
    assert result["status"] == "HUMAN_REVIEW_REQUIRED"


def test_geometry_drift_is_reported_as_soft(tmp_path):
    contract = quad_contract()
    deck = make_deck(tmp_path, [[
        ("n1", [96, 200, 480, 180], "n1"),      # 16px right of the declared box
        ("n2", [640, 200, 480, 180], "n2"),
        ("n3", [80, 420, 480, 180], "n3"),
        ("n4", [640, 420, 480, 180], "n4"),
    ]])
    result = verify_render(deck, contract)
    assert any(i["code"] == "GEOMETRY_DRIFT" and i["detail"]["axis"] == "left"
               for i in result["issues"])
    assert result["status"] == "HUMAN_REVIEW_REQUIRED"


def test_z_order_inversion_is_caught(tmp_path):
    contract = quad_contract()
    contract["pages"][0]["roles"] = {"semantic": ["card"], "overlay": ["scrim"]}
    contract["pages"][0]["objects"] = [
        {"name": "card", "box": [80, 200, 480, 180], "text": "card", "has_geometry": True},
        {"name": "scrim", "box": [80, 200, 480, 180], "text": "", "has_geometry": True},
    ]
    # scrim painted FIRST => card sits above it: correct
    good = make_deck(tmp_path, [[("scrim", [80, 200, 480, 180], ""),
                                 ("card", [80, 200, 480, 180], "card")]],
                      filename="good.pptx")
    assert verify_render(good, contract)["status"] == "PASS"
    # scrim painted LAST => it covers the semantic card: inverted
    bad = make_deck(tmp_path, [[("card", [80, 200, 480, 180], "card"),
                                ("scrim", [80, 200, 480, 180], "")]],
                     filename="bad.pptx")
    result = verify_render(bad, contract)
    assert "Z_ORDER_INVERTED" in {i["code"] for i in result["issues"]}
    assert "SEMANTIC_LAYER_OCCLUDED" in {i["code"] for i in result["issues"]}


def test_partial_overlay_below_the_threshold_is_not_flagged(tmp_path):
    contract = quad_contract()
    contract["pages"][0]["roles"] = {"semantic": ["card"], "overlay": ["scrim"]}
    contract["pages"][0]["objects"] = [
        {"name": "card", "box": [80, 200, 480, 180], "text": "card", "has_geometry": True},
        {"name": "scrim", "box": [80, 380, 480, 40], "text": "", "has_geometry": True},
    ]
    deck = make_deck(tmp_path, [[("card", [80, 200, 480, 180], "card"),
                                 ("scrim", [80, 380, 480, 40], "")]])
    result = verify_render(deck, contract)
    assert "SEMANTIC_LAYER_OCCLUDED" not in {i["code"] for i in result["issues"]}


def test_missing_artifact_is_a_block_not_a_pass(tmp_path):
    result = verify_render(tmp_path / "nope.pptx", quad_contract())
    assert result["status"] == "BLOCK"
    assert result["issues"][0]["code"] == "ARTIFACT_MISSING"


def test_report_states_what_it_did_not_check(tmp_path):
    """The verifier must declare its own coverage boundary, not imply totality."""
    contract = quad_contract()
    deck = make_deck(tmp_path, [[("n1", [80, 200, 480, 180], "n1"),
                                 ("n2", [640, 200, 480, 180], "n2"),
                                 ("n3", [80, 420, 480, 180], "n3"),
                                 ("n4", [640, 420, 480, 180], "n4")]])
    report = verify_render(deck, contract)
    assert report["coverage"]["colour_and_aesthetics"] == "NOT_CHECKED"
    assert report["coverage"]["reading_order"] == "CHECKED"
    assert report["artifact_sha256"]


def test_coverage_admits_when_locked_text_or_roles_were_not_declared(tmp_path):
    """Absent a declaration the check cannot run; saying CHECKED would overclaim."""
    contract = quad_contract()          # no exact_text, no roles
    deck = make_deck(tmp_path, [[("n1", [80, 200, 480, 180], "n1"),
                                 ("n2", [640, 200, 480, 180], "n2"),
                                 ("n3", [80, 420, 480, 180], "n3"),
                                 ("n4", [640, 420, 480, 180], "n4")]])
    coverage = verify_render(deck, contract)["coverage"]
    assert coverage["exact_text"] == "NOT_CHECKED_NO_LOCKED_TEXT_DECLARED"
    assert coverage["z_order_and_occlusion"] == "NOT_CHECKED_NO_ROLES_DECLARED"


# ------------------------------------------------- integration with the app plan
def test_contract_adapter_reads_the_real_beautification_plan():
    """The adapter must join on the plan's element names, not on invented ones."""
    from app.native_beautifier import compile_beautification_plan
    deck = {
        "project_id": "prj_test",
        "presentation_question": "question",
        "pages": [{
            "page_id": "p1",
            "title": "Sourced fact",
            "primary_message": "Sourced fact",
            "visual_type": "EVIDENCE_MAP",
            "provenance": "SOURCE",
            "claims": [{
                "id": "c1", "normalized_claim": "Sourced fact", "provenance": "SOURCE",
                "risk": "GREEN", "conditions": ["context"], "numeric_facts": [],
                "source_refs": [{"document_id": "d", "page": 1, "quote": "Sourced fact"}],
            }],
            "relationships": [],
        }],
    }
    plan = compile_beautification_plan(deck)
    contract = contract_from_plan(plan)
    assert contract["canvas"] == list(DEFAULT_CANVAS)
    page = contract["pages"][0]
    assert page["page_id"] == "p1"
    names = [o["name"] for o in page["objects"]]
    assert any(n.startswith("title:") for n in names), names
    assert any(n.startswith("claim:") for n in names), names
    # every geometry-bearing object declares a 4-number box in canvas coordinates
    for obj in page["objects"]:
        if obj["has_geometry"]:
            assert len(obj["box"]) == 4
            assert all(isinstance(v, (int, float)) for v in obj["box"])
        else:
            assert obj["box"] is None


def test_contract_maps_connectors_and_mandatory_claim_ids():
    """The app's own fields must drive the checks, and the id->name join must work.

    ``mandatory_object_ids`` are CLAIM ids while plan elements are named
    ``claim:<id>``; without the mapping the mandatory check could never match.
    """
    from app.native_beautifier import compile_beautification_plan
    deck = {
        "project_id": "prj_lock",
        "presentation_question": "q",
        "pages": [{
            "page_id": "p1", "title": "T", "primary_message": "T",
            "visual_type": "EVIDENCE_MAP", "provenance": "SOURCE",
            "claims": [
                {"id": "c1", "normalized_claim": "Alpha fact", "provenance": "SOURCE",
                 "risk": "RED", "conditions": ["c"], "numeric_facts": [],
                 "source_refs": [{"document_id": "d", "page": 1, "quote": "Alpha"}]},
                {"id": "c2", "normalized_claim": "Beta fact", "provenance": "SOURCE",
                 "risk": "GREEN", "conditions": ["c"], "numeric_facts": [],
                 "source_refs": [{"document_id": "d", "page": 1, "quote": "Beta"}]},
            ],
            "relationships": [{"id": "rel1", "from_claim_id": "c1", "to_claim_id": "c2",
                               "relation_type": "ASSOCIATION", "provenance": "SOURCE",
                               "risk": "GREEN", "status": "SUPPORTED",
                               "source_refs": [{"document_id": "d", "page": 1,
                                                "quote": "relation"}]}],
        }],
    }
    plan = compile_beautification_plan(deck)
    visual_contracts = [{
        "page_id": "p1",
        "exact_text_register": ["Alpha fact"],
        "mandatory_object_ids": ["c1"],
    }]
    page = contract_from_plan(plan, visual_contracts=visual_contracts)["pages"][0]

    connector_names = [o["name"] for o in page["objects"] if not o["has_geometry"]]
    assert connector_names, "plan connectors must be registered so they are not 'unknown'"
    assert any(n.startswith("clinical_relationship:") for n in connector_names)
    assert page["exact_text"] == ["Alpha fact"]
    assert page["mandatory"] == ["claim:c1"], page["mandatory"]


def test_contract_without_visual_contracts_degrades_to_no_locked_text():
    """Absent the visual contracts there is no locked text and no mandatory set --
    and the contract must say so by absence, not by inventing values."""
    from app.native_beautifier import compile_beautification_plan
    plan = compile_beautification_plan({
        "project_id": "p", "presentation_question": "q",
        "pages": [{"page_id": "p1", "title": "T", "primary_message": "T",
                   "visual_type": "EVIDENCE_MAP", "provenance": "SOURCE",
                   "relationships": [],
                   "claims": [{"id": "c1", "normalized_claim": "Alpha fact",
                               "provenance": "SOURCE", "risk": "GREEN",
                               "conditions": ["c"], "numeric_facts": [],
                               "source_refs": [{"document_id": "d", "page": 1,
                                                "quote": "Alpha"}]}]}]})
    page = contract_from_plan(plan)["pages"][0]
    assert page["exact_text"] == []
    assert page["mandatory"] == []
    assert page["roles"] == {}


def test_declared_connector_is_not_reported_as_unknown(tmp_path):
    contract = quad_contract()
    contract["pages"][0]["objects"].append(
        {"name": "clinical_relationship:r", "box": None, "text": "",
         "order": None, "has_geometry": False})
    deck = make_deck(tmp_path, [[
        ("n1", [80, 200, 480, 180], "n1"),
        ("n2", [640, 200, 480, 180], "n2"),
        ("n3", [80, 420, 480, 180], "n3"),
        ("n4", [640, 420, 480, 180], "n4"),
        ("clinical_relationship:r", [300, 300, 200, 20], ""),
    ]])
    result = verify_render(deck, contract)
    assert "UNKNOWN_OBJECT" not in {i["code"] for i in result["issues"]}
    assert result["status"] == "PASS"
