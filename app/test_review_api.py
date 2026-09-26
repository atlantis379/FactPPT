"""Public v2 review routes fail closed until identity and source trust exist."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.content_contract import digest
from app.main import QUALIFIED_REVIEW_IDS, app


def package_payload() -> dict:
    quote = "第三季度营收为100万元。"
    return {
        "source_excerpts": [{"id": "s", "source_sha256": digest("forged input"),
                             "locator": {"kind": "PDF", "page": 2},
                             "extracted_text": quote, "quote": quote}],
        "assertions": [{"id": "a", "text": quote, "source_excerpt_ids": ["s"]}],
        "slide_statements": [{"id": "p", "text": quote, "assertion_ids": ["a"]}],
    }


def review_body() -> dict:
    return {"package": package_payload(), "author_id": "claimed-generator",
            "reviewer_id": "claimed-reviewer", "decision": "APPROVE",
            "rationale": "I claim to have read the source file.",
            "assertion_ids": ["a"], "slide_statement_ids": ["p"]}


@pytest.mark.parametrize("method,path,body", [
    ("get", "/api/v2/reviewers", None),
    ("post", "/api/v2/reviewers", {"reviewer_id": "claimed-reviewer", "reviewer_kind": "HUMAN"}),
    ("post", "/api/v2/reviews", review_body()),
    ("post", "/api/v2/delivery-gate", review_body()),
])
def test_public_review_and_delivery_endpoints_fail_closed(method, path, body, monkeypatch):
    store = Path(__file__).with_name(f"unused-review-store-{uuid4().hex}.json")
    monkeypatch.setattr("app.main.REVIEW_STORE", store)
    client = TestClient(app)
    response = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
    assert response.status_code == 503
    assert "authenticated" in response.json()["detail"]
    assert not store.exists()


def test_client_supplied_quote_and_hash_still_need_source_verification():
    response = TestClient(app).post("/api/v2/content/verify", json=package_payload())
    assert response.status_code == 200
    assert response.json()["status"] == "NEEDS_REVIEW"
    assert response.json()["source_findings"]["s"]["codes"] == ["SOURCE_FILE_NOT_VERIFIED"]


def test_no_model_qualification_is_preinstalled_without_real_evidence():
    assert QUALIFIED_REVIEW_IDS == set()
