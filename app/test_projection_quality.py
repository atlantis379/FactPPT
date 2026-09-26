"""Regression checks for the reusable academic projection gate."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from app.projection_quality import contrast, evaluate
from app.visual_prompt_contract import compile_deck


ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "validation" / "stability_sample_4_pages"
LEDGER = ROOT / ".codex_build" / "stability_sample_4_pages" / "authoring_ledger_v4_final.json"
PPTX = SAMPLE / "four_page_stability_sample_v4_final.pptx"


def read(name: str) -> dict:
    return json.loads((SAMPLE / name).read_text(encoding="utf-8"))


def evaluate_sample(*, contract=None, ledger=None):
    return evaluate(contract or read("content_contract.json"), read("content_contract_v3.json"),
                    read("projection_profile.json"),
                    ledger or json.loads(LEDGER.read_text(encoding="utf-8")),
                    PPTX, workspace=ROOT)


def test_final_sample_is_source_bound_and_projection_legible():
    result = evaluate_sample()
    assert result["status"] == "PASS", result["failures"]
    assert len(compile_deck(read("content_contract.json"))) == 4


def test_threshold_drift_is_caught_before_visual_review():
    contract = read("content_contract.json")
    contract["pages"][3]["CONTENT_LOCK"]["text_blocks"][-1]["text"] = "SpO₂ ≥92%"
    result = evaluate_sample(contract=contract)
    assert result["status"] == "FAIL"
    assert any("CONTENT_LOCK" in issue for issue in result["failures"])


def test_small_low_contrast_or_auto_shrunk_text_is_caught():
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    ledger = copy.deepcopy(ledger)
    ledger[0]["font_size_px"] = 12
    ledger[0]["color"] = "#aab8c4"
    ledger[0]["auto_fit"] = "shrink"
    result = evaluate_sample(ledger=ledger)
    assert result["status"] == "FAIL"
    assert any("font floor" in issue for issue in result["failures"])
    assert any("contrast" in issue for issue in result["failures"])
    assert any("auto shrink" in issue for issue in result["failures"])


def test_dark_teal_is_readable_on_pale_teal():
    assert contrast("#087780", "#EDF9F9") >= 4.5
    assert contrast("#12999F", "#EDF9F9") < 4.5
