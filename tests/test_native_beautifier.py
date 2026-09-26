from pathlib import Path
import json
import subprocess

import pytest

from app.native_beautifier import (
    BeautificationPlanError,
    compile_beautification_plan,
    validate_beautification_plan,
)
from app.editorial_assets import EditorialAssetError, load_editorial_asset_manifest
from app.packager import (DEFAULT_NODE, DEFAULT_PPTXGENJS_MODULE,
                          _pptxgenjs_runtime_paths, build_pptx, verify_pptx)


ASSET_MANIFEST = Path("assets/editorial/chatgpt-image-underlay-v1.asset.json")
needs_public_writer = pytest.mark.skipif(
    not DEFAULT_NODE.is_file() or not DEFAULT_PPTXGENJS_MODULE.is_file(),
    reason="locked Node/PptxGenJS writer is not installed; run npm ci")


def claim(claim_id: str, text: str | None = None, provenance: str = "SOURCE") -> dict:
    return {
        "id": claim_id,
        "normalized_claim": text or f"Claim {claim_id}",
        "provenance": provenance,
        "risk": "GREEN",
        "conditions": ["适用人群"],
        "source_refs": [{"document_id": "guideline", "page": 12, "quote": "source"}],
    }


def page(visual_type: str, claims: list[dict], relationships: list[dict] | None = None) -> dict:
    return {
        "page_id": "p1",
        "title": "证据驱动的页面标题",
        "primary_message": "一页只表达一个可核验的核心信息。",
        "visual_type": visual_type,
        "claims": claims,
        "relationships": relationships or [],
    }


def deck(page_value: dict) -> dict:
    return {"project_id": "demo", "pages": [page_value]}


@pytest.mark.parametrize(
    ("visual_type", "claims", "relationships", "expected"),
    [
        ("EVIDENCE_MAP", [claim("a")], [], "EDITORIAL_STATEMENT"),
        ("EVIDENCE_MAP", [claim("a"), claim("b"), claim("c")], [], "EVIDENCE_CARDS"),
        ("EVIDENCE_MATRIX", [claim("a"), claim("b")], [], "COMPARISON_COLUMNS"),
        ("MANAGEMENT_CYCLE", [claim("a"), claim("b")], [], "TIMELINE"),
        (
            "CLINICAL_DECISION_MAP",
            [claim("a"), claim("b")],
            [{"id": "r1", "from_claim_id": "a", "to_claim_id": "b", "relation_type": "ASSOCIATION"}],
            "DECISION_FLOW",
        ),
    ],
)
def test_selects_deterministic_native_archetype(visual_type, claims, relationships, expected):
    plan = compile_beautification_plan(deck(page(visual_type, claims, relationships)))
    planned = plan["pages"][0]
    assert planned["selected_archetype"] == expected
    assert len(planned["candidates"]) == 5
    assert plan["native_editable"] is True


def test_plan_preserves_claims_relationships_and_sources():
    source = page(
        "CLINICAL_DECISION_MAP",
        [claim("a", "原文事实 A"), claim("b", "原文事实 B", "SYNTHESIS")],
        [{"id": "r1", "from_claim_id": "a", "to_claim_id": "b", "relation_type": "ASSOCIATION"}],
    )
    source_deck = deck(source)
    plan = compile_beautification_plan(source_deck)
    result = validate_beautification_plan(source_deck, plan)
    assert result["status"] == "PASS"
    names = {item["name"] for item in plan["pages"][0]["elements"]}
    assert {"claim:a", "claim:b", "source-trace:p1"} <= names
    assert plan["pages"][0]["connectors"][0]["name"] == "clinical_relationship:r1"
    assert plan["pages"][0]["connectors"][0]["direction"] == "FORWARD"
    assert plan["pages"][0]["source_lines"] == ["guideline p.12"]


def test_external_visual_providers_are_non_semantic_extension_points_only():
    plan = compile_beautification_plan(deck(page("EVIDENCE_MAP", [claim("a")])))
    policy = plan["external_asset_policy"]
    assert policy["default"] == "DISABLED"
    assert "chatgpt-image" in policy["providers"]
    assert "figma" in policy["providers"]
    assert "CLAIM" in policy["protected_native_roles"]
    assert "RELATIONSHIP" in policy["protected_native_roles"]


def test_chatgpt_image_manifest_is_hash_bound_and_enables_underlay_policy():
    asset = load_editorial_asset_manifest(ASSET_MANIFEST, workspace=Path.cwd())
    target_page = page("EVIDENCE_MAP", [claim("a")])
    target_page["page_id"] = "statement"
    plan = compile_beautification_plan(deck(target_page), editorial_assets=[asset])
    assert asset["pixel_dimensions"]["width"] >= 1280
    assert plan["external_asset_policy"]["default"] == "ENABLED_WITH_VALIDATED_MANIFEST"
    assert plan["pages"][0]["editorial_assets"][0]["asset_id"] == "chatgpt-image-underlay-v1"
    assert plan["pages"][0]["fusion"]["variant"] == "OPEN_FIELD"
    claim_element = next(item for item in plan["pages"][0]["elements"] if item["name"] == "claim:a")
    assert claim_element["position"]["left"] + claim_element["position"]["width"] <= 1050
    assert claim_element.get("fill") not in {"#FFFFFF", "#F8FCFD"}


def test_chatgpt_image_manifest_requires_native_layer_fusion_theme():
    manifest = __import__("json").loads(ASSET_MANIFEST.read_text(encoding="utf-8"))
    manifest.pop("fusion_theme")
    with pytest.raises(EditorialAssetError, match="fusion theme"):
        load_editorial_asset_manifest(manifest, workspace=Path.cwd())


def test_chatgpt_image_manifest_rejects_hash_mismatch():
    manifest = __import__("json").loads(ASSET_MANIFEST.read_text(encoding="utf-8"))
    manifest["sha256"] = "0" * 64
    with pytest.raises(EditorialAssetError, match="SHA-256"):
        load_editorial_asset_manifest(manifest, workspace=Path.cwd())


def test_over_capacity_blocks_instead_of_dropping_claims():
    with pytest.raises(BeautificationPlanError, match="split the PageSpec"):
        compile_beautification_plan(deck(page("EVIDENCE_MAP", [claim(str(index)) for index in range(5)])))


def test_relationship_outside_page_is_blocked():
    relationship = {"id": "r", "from_claim_id": "a", "to_claim_id": "missing", "relation_type": "ASSOCIATION"}
    with pytest.raises(BeautificationPlanError, match="outside the page Claim set"):
        compile_beautification_plan(deck(page("CLINICAL_DECISION_MAP", [claim("a"), claim("b")], [relationship])))


@needs_public_writer
def test_native_pptx_round_trip(tmp_path):
    source = deck(page(
        "CLINICAL_DECISION_MAP",
        [claim("a", "高危人群进入评估"), claim("b", "经验证后进入分层")],
        [{"id": "r1", "from_claim_id": "a", "to_claim_id": "b", "relation_type": "CONDITIONAL"}],
    ))
    run_dir = tmp_path / "native-beautifier-test"
    target = run_dir / "native-beautification-mvp.pptx"
    plan_target = run_dir / "native-beautification-mvp.plan.json"
    build_pptx(source, target, plan_target=plan_target)
    result = verify_pptx(source, target)
    assert target.exists()
    assert plan_target.exists()
    assert result["status"] == "PASS"
    assert result["native_editable"] is True
    assert result["selected_archetypes"] == ["DECISION_FLOW"]


@needs_public_writer
def test_public_writer_blocks_unsupported_visual_values(tmp_path):
    try:
        node, module = _pptxgenjs_runtime_paths()
    except RuntimeError as error:
        pytest.skip(str(error))
    source = deck(page("EVIDENCE_MAP", [claim("a", "有来源的事实")]))
    plan = compile_beautification_plan(source)
    shape = next(element for element in plan["pages"][0]["elements"]
                 if element["kind"] == "shape")
    shape["fill"] = "linear(90deg, #FFFFFF 0%, #000000 100%)"
    plan_path = tmp_path / "unsupported-plan.json"
    output_path = tmp_path / "unsupported.pptx"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    writer_path = Path(__file__).resolve().parents[1] / "app" / "pptxgenjs_writer.mjs"

    result = subprocess.run(
        [str(node), str(writer_path), str(plan_path), str(output_path), str(module),
         str(Path(__file__).resolve().parents[1])],
        capture_output=True, text=True)

    assert result.returncode != 0
    assert "Unsupported color value" in result.stderr
    assert not output_path.exists()


@needs_public_writer
def test_public_writer_round_trips_all_five_archetypes(tmp_path):
    pages = [
        page("EVIDENCE_MAP", [claim("statement", "A source-backed statement")]),
        page("EVIDENCE_MAP", [claim("card-a"), claim("card-b"), claim("card-c")]),
        page("EVIDENCE_MATRIX", [claim("compare-a"), claim("compare-b")]),
        page("MANAGEMENT_CYCLE", [claim("time-a"), claim("time-b")]),
        page("CLINICAL_DECISION_MAP", [claim("flow-a"), claim("flow-b")], [
            {"id": "flow-link", "from_claim_id": "flow-a", "to_claim_id": "flow-b",
             "relation_type": "ASSOCIATION"}]),
    ]
    for index, item in enumerate(pages, start=1):
        item["page_id"] = f"p{index}"
    source = {"project_id": "all-writer-archetypes", "pages": pages}
    target = tmp_path / "all-archetypes.pptx"

    build_pptx(source, target, mark_operation=False)

    result = verify_pptx(source, target)
    assert result["status"] == "PASS", result["issues"]
    assert result["native_editable"] is True
    assert result["slides_checked"] == 5
    assert result["selected_archetypes"] == [
        "EDITORIAL_STATEMENT", "EVIDENCE_CARDS", "COMPARISON_COLUMNS",
        "TIMELINE", "DECISION_FLOW"]


@needs_public_writer
def test_chatgpt_image_underlay_keeps_semantic_objects_native(tmp_path):
    source = deck(page("EVIDENCE_MAP", [claim("a", "证据文字仍为原生文本框")]))
    manifest = __import__("json").loads(ASSET_MANIFEST.read_text(encoding="utf-8"))
    manifest["page_ids"] = ["p1"]
    run_dir = tmp_path / "chatgpt-image-underlay-test"
    target = run_dir / "chatgpt-image-underlay.pptx"
    build_pptx(source, target, editorial_asset_manifest=manifest)
    result = verify_pptx(source, target, editorial_asset_manifest=manifest)
    assert result["status"] == "PASS"
    assert result["native_editable"] is True
    assert result["editorial_asset_ids"] == ["chatgpt-image-underlay-v1"]
