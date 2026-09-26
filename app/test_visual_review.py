from __future__ import annotations

import uuid
from pathlib import Path

from app.visual_review import review_issues, sha256_file


def receipt():
    root = Path(__file__).parent / ".codex_build" / "visual-review-tests" / uuid.uuid4().hex / "one"
    png = root / "powerpoint_png"
    png.mkdir(parents=True)
    deck = root / "preview.pptx"
    deck.write_bytes(b"pptx output")
    images = []
    for index, page_id in enumerate(("p1", "p2"), start=1):
        path = png / f"slide-{index:02}.png"
        path.write_bytes(f"powerpoint slide {index}".encode())
        images.append({"page_id": page_id, "path": str(path), "sha256": sha256_file(path)})
    return root.parent, {"semantic_digest": "semantic", "layout_design_digest": "design",
                         "plan_digest": "plan", "editorial_asset_sha256s": [],
                         "renderer": "powerpoint", "preview_path": str(deck),
                         "preview_sha256": sha256_file(deck), "images": images,
                         "pages": [{"page_id": "p1", "verdict": "PASS"},
                                   {"page_id": "p2", "verdict": "PASS"}]}


def issues(record, root):
    return review_issues(record, page_ids=["p1", "p2"], semantic_digest="semantic",
                         design_digest="design", plan_digest="plan", asset_hashes=[],
                         review_root=root)


def test_visual_review_requires_exact_powerpoint_bytes_and_all_slides():
    root, record = receipt()
    assert issues(record, root) == []
    record["pages"][1]["verdict"] = "REVISE"
    assert any("still requires" in issue for issue in issues(record, root))
    record["pages"][1]["verdict"] = "PASS"
    record["images"][0]["page_id"] = "other"
    assert any("every slide" in issue for issue in issues(record, root))
    record["images"][0]["page_id"] = "p1"
    (root / "one" / "preview.pptx").write_bytes(b"changed")
    assert any("bytes changed" in issue for issue in issues(record, root))


def test_visual_review_rejects_non_powerpoint_and_stale_plan():
    root, record = receipt()
    record["renderer"] = "artifact-tool"
    record["plan_digest"] = "old"
    result = issues(record, root)
    assert any("PowerPoint" in issue for issue in result)
    assert any("plan_digest" in issue for issue in result)
