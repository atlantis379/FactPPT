"""Validated non-semantic editorial assets for PPTX composition."""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any


class EditorialAssetError(ValueError):
    """Raised when an editorial asset cannot safely enter the slide renderer."""


def _png_dimensions(payload: bytes) -> tuple[int, int]:
    if len(payload) < 24 or payload[:8] != b"\x89PNG\r\n\x1a\n" or payload[12:16] != b"IHDR":
        raise EditorialAssetError("ChatGPT Image editorial asset must be a genuine PNG file.")
    return struct.unpack(">II", payload[16:24])


def load_editorial_asset_manifest(manifest: Path | dict[str, Any], *, workspace: Path) -> dict[str, Any]:
    """Load and validate a hash-bound ChatGPT Image editorial underlay."""
    data = json.loads(Path(manifest).read_text(encoding="utf-8")) if isinstance(manifest, Path) else dict(manifest)
    if data.get("schema_version") != "chatgpt_image_editorial_asset.v0.1":
        raise EditorialAssetError("Unsupported ChatGPT Image asset manifest schema.")
    if data.get("provider") != "chatgpt-image" or data.get("generation_mode") != "built-in-imagegen":
        raise EditorialAssetError("Editorial asset provider provenance is missing or unsupported.")
    if data.get("asset_class") != "NONSEMANTIC_EDITORIAL_BASE" or data.get("layer_role") != "EDITORIAL_UNDERLAY":
        raise EditorialAssetError("ChatGPT Image may only enter the MVP as a non-semantic editorial underlay.")
    if data.get("content_type") != "image/png":
        raise EditorialAssetError("Only PNG editorial underlays are supported by this MVP.")
    relative = Path(str(data.get("path", "")))
    if not relative.as_posix() or relative.is_absolute() or ".." in relative.parts:
        raise EditorialAssetError("Editorial asset path must be relative to the workspace and may not traverse parents.")
    workspace = workspace.resolve()
    asset_path = (workspace / relative).resolve()
    try:
        asset_path.relative_to(workspace)
    except ValueError as error:
        raise EditorialAssetError("Editorial asset resolves outside the workspace.") from error
    payload = asset_path.read_bytes()
    actual_hash = hashlib.sha256(payload).hexdigest()
    if actual_hash.lower() != str(data.get("sha256", "")).lower():
        raise EditorialAssetError("Editorial asset SHA-256 does not match its manifest.")
    width, height = _png_dimensions(payload)
    if width < 1280 or height < 720 or not 1.6 <= width / height <= 1.9:
        raise EditorialAssetError("Editorial underlay must be a landscape image large enough for a 16:9 slide.")
    pages = data.get("page_ids")
    if not isinstance(pages, list) or not pages or not all(isinstance(value, str) and value for value in pages):
        raise EditorialAssetError("Editorial asset must declare one or more target page IDs (or '*').")
    review = data.get("content_review", {})
    required_checks = {"no_text", "no_numbers", "no_medical_claim", "no_relationship_encoding", "no_watermark", "safe_regions_clear"}
    if review.get("status") != "PASS" or any(review.get("checked", {}).get(key) is not True for key in required_checks):
        raise EditorialAssetError("Editorial asset content review is incomplete or not PASS.")
    placement = data.get("placement", {})
    if placement != {"left": 0, "top": 0, "width": 1280, "height": 720, "fit": "cover"}:
        raise EditorialAssetError("MVP ChatGPT Image underlay must use the full 1280x720 canvas at z0.")
    fusion_theme = data.get("fusion_theme", {})
    palette = fusion_theme.get("palette", {})
    required_palette = {"background", "surface", "ink", "muted", "line", "accent", "accent_soft", "warm"}
    if fusion_theme.get("reuse_mode") != "MASTER_UNDERLAY" or set(palette) != required_palette:
        raise EditorialAssetError("Editorial asset must declare a complete approved fusion theme and reuse mode.")
    if any(not isinstance(value, str) or not value.startswith("#") or len(value) != 7 for value in palette.values()):
        raise EditorialAssetError("Fusion palette values must be six-digit hex colors.")
    content_zone = fusion_theme.get("content_zone", {})
    decoration_zone = fusion_theme.get("protected_decoration_zone", {})
    if content_zone != {"left": 64, "top": 36, "width": 960, "height": 620}:
        raise EditorialAssetError("Fusion content zone must preserve the approved left editorial field.")
    if decoration_zone != {"left": 1050, "top": 0, "width": 230, "height": 720}:
        raise EditorialAssetError("Fusion theme must protect the approved right-edge decoration zone.")
    surface_opacity = fusion_theme.get("surface_opacity")
    if not isinstance(surface_opacity, int) or not 55 <= surface_opacity <= 88:
        raise EditorialAssetError("Fusion surface opacity must be between 55 and 88 percent.")
    normalized = dict(data)
    normalized["sha256"] = actual_hash
    normalized["pixel_dimensions"] = {"width": width, "height": height}
    return normalized


def assets_for_page(assets: list[dict[str, Any]], page_id: str) -> list[dict[str, Any]]:
    selected = [asset for asset in assets if "*" in asset["page_ids"] or page_id in asset["page_ids"]]
    if len(selected) > 1:
        raise EditorialAssetError(f"Page {page_id} has multiple editorial underlays; MVP permits exactly zero or one.")
    return selected
