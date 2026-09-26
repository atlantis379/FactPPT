"""W15 visual review receipt for the exact PowerPoint-rendered deck being delivered."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review_issues(record: dict[str, Any] | None, *, page_ids: list[str],
                  semantic_digest: str, design_digest: str, plan_digest: str,
                  asset_hashes: list[str], review_root: Path) -> list[str]:
    """Fail closed on stale, partial, failed, or non-PowerPoint visual reviews."""
    if not record:
        return ["No W15 visual review exists for this deck"]
    issues: list[str] = []
    for key, expected in (("semantic_digest", semantic_digest),
                          ("layout_design_digest", design_digest),
                          ("plan_digest", plan_digest),
                          ("editorial_asset_sha256s", asset_hashes)):
        if record.get(key) != expected:
            issues.append(f"Visual review {key} is stale")
    if record.get("renderer") != "powerpoint":
        issues.append("Visual review must use PowerPoint-exported PNGs")
    pages = record.get("pages") or []
    if len(pages) != len(page_ids) or [item.get("page_id") for item in pages] != page_ids:
        issues.append("Visual review must cover every slide in deck order")
    for item in pages:
        if item.get("verdict") != "PASS":
            issues.append(f"Slide {item.get('page_id')} still requires visual revision")
    try:
        preview = Path(record["preview_path"]).resolve(strict=True)
        if not preview.is_relative_to(review_root.resolve(strict=True)) or preview.name != "preview.pptx":
            issues.append("Reviewed PPTX is outside the managed review directory")
        elif sha256_file(preview) != record.get("preview_sha256"):
            issues.append("Reviewed PPTX bytes changed after visual review")
    except (KeyError, OSError, ValueError):
        issues.append("Reviewed PPTX is missing")
    images = record.get("images") or []
    if len(images) != len(page_ids) or [item.get("page_id") for item in images] != page_ids:
        issues.append("Visual review has no image receipt for every slide")
    for item in images:
        try:
            path = Path(item["path"]).resolve(strict=True)
            if not path.is_relative_to(review_root.resolve(strict=True)):
                issues.append(f"Slide {item.get('page_id')} image is outside the review directory")
            elif sha256_file(path) != item.get("sha256"):
                issues.append(f"Slide {item.get('page_id')} image changed after review")
        except (KeyError, OSError, ValueError):
            issues.append(f"Slide {item.get('page_id')} image is missing")
    return issues
