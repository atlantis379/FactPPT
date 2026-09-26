"""Regression tests for source-bound visual prompts and asset deduplication."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.visual_prompt_contract import (VisualPromptContractError, asset_reuse_status,
                                        compile_deck, generated_asset_tasks)


ROOT = Path(__file__).resolve().parent / "validation" / "visual_sample_4_pages"


def _fixture():
    deck = json.loads((ROOT / "visual_contract.json").read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "asset_registry.json").read_text(encoding="utf-8"))
    return deck, registry


def test_four_pages_share_style_and_reuse_three_transparent_assets():
    deck, registry = _fixture()
    prompts = compile_deck(deck)
    assert len(prompts) == 4
    assert len({item["style_digest"] for item in prompts}) == 1
    assert len(generated_asset_tasks(deck)) == 3
    status = asset_reuse_status(deck, registry, registry_root=ROOT)
    assert [item["status"] for item in status] == ["REUSE"] * 3


def test_repeated_theme_does_not_create_another_generation_task():
    deck, _ = _fixture()
    repeated = copy.deepcopy(deck["pages"][-1])
    repeated["CONTENT_LOCK"]["page_id"] = "05-repeated-visual"
    repeated["CONTENT_LOCK"]["folio"] = "VISUAL SAMPLE / 05—05"
    deck["pages"].append(repeated)
    tasks = generated_asset_tasks(deck)
    assert len(tasks) == 3
    assert all(len(task["page_ids"]) == 2 for task in tasks)


def test_changed_meaning_or_hash_cannot_reuse_old_asset():
    deck, registry = _fixture()
    deck["pages"][-1]["VISUAL_METAPHOR"]["assets"][0]["medical_semantics"] += "（修改）"
    status = asset_reuse_status(deck, registry, registry_root=ROOT)
    assert status[0]["status"] == "GENERATE_REQUIRED"
    assert [item["status"] for item in status[1:]] == ["REUSE", "REUSE"]

    deck, registry = _fixture()
    registry["assets"][1]["sha256"] = "0" * 64
    status = asset_reuse_status(deck, registry, registry_root=ROOT)
    assert status[1]["status"] == "GENERATE_REQUIRED"


def test_medical_text_must_bind_registered_source():
    deck, _ = _fixture()
    deck["pages"][0]["CONTENT_LOCK"]["text_blocks"][2]["source_refs"] = ["unknown-ref"]
    with pytest.raises(VisualPromptContractError, match="unknown source ref"):
        compile_deck(deck)
