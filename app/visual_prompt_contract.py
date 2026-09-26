"""Compile source-bound medical slide plans into repeatable image prompts.

This module prepares prompts and verification manifests. It does not grant an
image generator authority over medical facts or certify generated pixels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "medical-visual-deck.v1"
PAGE_SECTIONS = {"CONTENT_LOCK", "LAYOUT", "VISUAL_METAPHOR", "NEGATIVE_CONSTRAINTS"}
MEDICAL_ROLES = {"medical", "threshold", "relationship"}
ASSET_BASE_FIELDS = {"id", "kind", "description", "medical_semantics", "source_refs"}
GENERATED_ASSET_FIELDS = {"asset_key", "background_policy", "reuse_policy"}


class VisualPromptContractError(ValueError):
    pass


def _digest(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VisualPromptContractError(f"{label} must be nonempty text")
    return value.strip()


def _text_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise VisualPromptContractError(f"{label} must be a nonempty list")
    return [_nonempty(item, label) for item in value]


def validate_deck(deck: dict[str, Any]) -> dict[str, Any]:
    """Reject stale-looking or incomplete plans before prompt compilation."""
    if not isinstance(deck, dict) or deck.get("schema_version") != SCHEMA_VERSION:
        raise VisualPromptContractError(f"Expected {SCHEMA_VERSION}")
    if set(deck) != {"schema_version", "STYLE_LOCK", "source_registry", "NEGATIVE_CONSTRAINTS", "pages"}:
        raise VisualPromptContractError("Deck must contain style, source registry, negatives, and pages")

    registry = deck["source_registry"]
    if not isinstance(registry, dict) or not registry:
        raise VisualPromptContractError("source_registry must bind the cited source locations")
    for ref, record in registry.items():
        _nonempty(ref, "source_registry key")
        if not isinstance(record, dict) or set(record) != {"document", "locator", "sha256"}:
            raise VisualPromptContractError(f"Invalid source registry record: {ref}")
        _nonempty(record["document"], f"{ref}.document")
        _nonempty(record["locator"], f"{ref}.locator")
        digest = str(record["sha256"])
        if len(digest) != 64 or any(c not in "0123456789abcdefABCDEF" for c in digest):
            raise VisualPromptContractError(f"{ref}.sha256 must be a SHA-256 hex digest")

    style = deck["STYLE_LOCK"]
    if not isinstance(style, dict) or set(style) != {
        "style_id", "canvas", "background", "palette", "typography",
        "iconography", "surfaces", "visual_references",
    }:
        raise VisualPromptContractError("STYLE_LOCK has missing or unsupported fields")
    for key in ("style_id", "background", "typography", "iconography", "surfaces"):
        _nonempty(style[key], f"STYLE_LOCK.{key}")
    if style["canvas"] != "16:9":
        raise VisualPromptContractError("STYLE_LOCK.canvas must be 16:9")
    palette = style["palette"]
    if not isinstance(palette, dict) or not palette or any(
        not isinstance(k, str) or not isinstance(v, str) or not v.startswith("#")
        for k, v in palette.items()
    ):
        raise VisualPromptContractError("STYLE_LOCK.palette needs named hex colors")
    if not isinstance(style["visual_references"], list):
        raise VisualPromptContractError("STYLE_LOCK.visual_references must be a list")
    _text_list(deck["NEGATIVE_CONSTRAINTS"], "deck.NEGATIVE_CONSTRAINTS")
    pages = deck["pages"]
    if not isinstance(pages, list) or not pages:
        raise VisualPromptContractError("pages must be a nonempty list")

    seen_pages: set[str] = set()
    for page in pages:
        if not isinstance(page, dict) or set(page) != PAGE_SECTIONS:
            raise VisualPromptContractError("Each page needs CONTENT_LOCK, LAYOUT, VISUAL_METAPHOR, NEGATIVE_CONSTRAINTS")
        content = page["CONTENT_LOCK"]
        if not isinstance(content, dict) or set(content) != {
            "page_id", "eyebrow", "folio", "title", "subtitle", "text_blocks",
            "footer_left", "footer_right", "speaker_notes_source_refs",
        }:
            raise VisualPromptContractError("CONTENT_LOCK has missing or unsupported fields")
        page_id = _nonempty(content["page_id"], "CONTENT_LOCK.page_id")
        if page_id in seen_pages:
            raise VisualPromptContractError(f"Duplicate page_id: {page_id}")
        seen_pages.add(page_id)
        for key in ("eyebrow", "folio", "title", "subtitle", "footer_left", "footer_right"):
            _nonempty(content[key], f"{page_id}.{key}")
        note_refs = _text_list(content["speaker_notes_source_refs"], f"{page_id}.speaker_notes_source_refs")
        if set(note_refs) - set(registry):
            raise VisualPromptContractError(f"{page_id}: unknown speaker-note source ref")

        blocks = content["text_blocks"]
        if not isinstance(blocks, list) or not blocks:
            raise VisualPromptContractError(f"{page_id}: text_blocks must be nonempty")
        block_ids: list[str] = []
        for block in blocks:
            if not isinstance(block, dict) or set(block) != {"id", "text", "role", "source_refs"}:
                raise VisualPromptContractError(f"{page_id}: invalid text block")
            block_id = _nonempty(block["id"], f"{page_id}.text_block.id")
            _nonempty(block["text"], f"{page_id}.{block_id}.text")
            role = _nonempty(block["role"], f"{page_id}.{block_id}.role")
            refs = block["source_refs"]
            if not isinstance(refs, list) or any(not isinstance(x, str) or not x.strip() for x in refs):
                raise VisualPromptContractError(f"{page_id}.{block_id}: invalid source_refs")
            if role in MEDICAL_ROLES and not refs:
                raise VisualPromptContractError(f"{page_id}.{block_id}: medical text needs source_refs")
            if set(refs) - set(registry):
                raise VisualPromptContractError(f"{page_id}.{block_id}: unknown source ref")
            if block_id in block_ids:
                raise VisualPromptContractError(f"{page_id}: duplicate text block {block_id}")
            block_ids.append(block_id)

        layout = page["LAYOUT"]
        if not isinstance(layout, dict) or set(layout) != {"grammar", "hierarchy", "regions", "reading_order"}:
            raise VisualPromptContractError(f"{page_id}: invalid LAYOUT")
        _nonempty(layout["grammar"], f"{page_id}.LAYOUT.grammar")
        _nonempty(layout["hierarchy"], f"{page_id}.LAYOUT.hierarchy")
        if layout["reading_order"] != block_ids:
            raise VisualPromptContractError(f"{page_id}: reading_order must match text_blocks order")
        regions = layout["regions"]
        if not isinstance(regions, list) or not regions:
            raise VisualPromptContractError(f"{page_id}: regions must be nonempty")
        placed: list[str] = []
        for region in regions:
            if not isinstance(region, dict) or set(region) != {"id", "position", "composition", "content_ids"}:
                raise VisualPromptContractError(f"{page_id}: invalid layout region")
            for key in ("id", "position", "composition"):
                _nonempty(region[key], f"{page_id}.region.{key}")
            placed.extend(_text_list(region["content_ids"], f"{page_id}.region.content_ids"))
        if sorted(placed) != sorted(block_ids):
            raise VisualPromptContractError(f"{page_id}: every text block must appear in exactly one region")

        metaphor = page["VISUAL_METAPHOR"]
        if not isinstance(metaphor, dict) or set(metaphor) != {"intent", "assets"}:
            raise VisualPromptContractError(f"{page_id}: invalid VISUAL_METAPHOR")
        _nonempty(metaphor["intent"], f"{page_id}.VISUAL_METAPHOR.intent")
        if not isinstance(metaphor["assets"], list):
            raise VisualPromptContractError(f"{page_id}: assets must be a list")
        for asset in metaphor["assets"]:
            if not isinstance(asset, dict) or not ASSET_BASE_FIELDS <= set(asset):
                raise VisualPromptContractError(f"{page_id}: invalid visual asset")
            expected = (ASSET_BASE_FIELDS | GENERATED_ASSET_FIELDS
                        if asset["kind"] == "medical_illustration" else ASSET_BASE_FIELDS)
            if set(asset) != expected:
                raise VisualPromptContractError(f"{page_id}: invalid asset fields for {asset['kind']}")
            for key in ("id", "kind", "description", "medical_semantics"):
                _nonempty(asset[key], f"{page_id}.asset.{key}")
            if asset["kind"] == "medical_illustration":
                _text_list(asset["source_refs"], f"{page_id}.asset.source_refs")
                _nonempty(asset["asset_key"], f"{page_id}.asset.asset_key")
                if asset["background_policy"] != "TRANSPARENT_ALPHA":
                    raise VisualPromptContractError(f"{page_id}: medical illustration must have transparent alpha")
                if asset["reuse_policy"] != "REUSE_BY_CONTRACT_DIGEST":
                    raise VisualPromptContractError(f"{page_id}: generated asset must be reusable by contract digest")
            elif not isinstance(asset["source_refs"], list):
                raise VisualPromptContractError(f"{page_id}: invalid asset source_refs")
            if set(asset["source_refs"]) - set(registry):
                raise VisualPromptContractError(f"{page_id}: unknown asset source ref")
        if not isinstance(page["NEGATIVE_CONSTRAINTS"], list):
            raise VisualPromptContractError(f"{page_id}: NEGATIVE_CONSTRAINTS must be a list")
        for item in page["NEGATIVE_CONSTRAINTS"]:
            _nonempty(item, f"{page_id}.NEGATIVE_CONSTRAINTS")

    return deck


def generated_asset_tasks(deck: dict[str, Any]) -> list[dict[str, Any]]:
    """One generation task per distinct meaning/style contract, across all pages."""
    validate_deck(deck)
    tasks: dict[str, dict[str, Any]] = {}
    style = deck["STYLE_LOCK"]
    for page in deck["pages"]:
        for asset in page["VISUAL_METAPHOR"]["assets"]:
            if asset["kind"] != "medical_illustration":
                continue
            key = asset["asset_key"]
            contract = {
                "style_id": style["style_id"],
                "palette": style["palette"],
                "kind": asset["kind"],
                "description": asset["description"],
                "medical_semantics": asset["medical_semantics"],
                "source_refs": asset["source_refs"],
                "background_policy": asset["background_policy"],
            }
            digest = _digest(contract)
            if key in tasks:
                if tasks[key]["contract_digest"] != digest:
                    raise VisualPromptContractError(f"Asset key {key} has conflicting meanings")
                tasks[key]["page_ids"].append(page["CONTENT_LOCK"]["page_id"])
                continue
            prompt = "\n".join([
                "只生成一张独立医学插画素材，不生成整页 PPT。",
                f"主题：{asset['description']}",
                f"必须表达的医学语义：{asset['medical_semantics']}",
                f"整套风格：{style['style_id']}；{style['iconography']}；{style['surfaces']}",
                f"颜色：{style['palette']}",
                "背景必须是真透明 Alpha；只保留主体，不带白底、卡片、阴影、标题、文字、数字或水印。",
                "同一 asset_key 与 contract_digest 已有合格素材时直接复用，禁止再次生成。",
            ])
            tasks[key] = {"asset_key": key, "contract_digest": digest,
                          "page_ids": [page["CONTENT_LOCK"]["page_id"]],
                          "prompt": prompt, "source_refs": asset["source_refs"]}
    return list(tasks.values())


def asset_reuse_status(deck: dict[str, Any], registry: dict[str, Any],
                       *, registry_root: Path) -> list[dict[str, Any]]:
    """Reuse only a reviewed, hash-matched, genuinely transparent asset."""
    if not isinstance(registry, dict) or registry.get("schema_version") != "medical-visual-assets.v1":
        raise VisualPromptContractError("Expected medical-visual-assets.v1 registry")
    entries = registry.get("assets")
    if not isinstance(entries, list):
        raise VisualPromptContractError("Asset registry needs an assets list")
    by_key = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("asset_key"), str):
            raise VisualPromptContractError("Invalid registry asset entry")
        if entry["asset_key"] in by_key:
            raise VisualPromptContractError(f"Duplicate asset key in registry: {entry['asset_key']}")
        by_key[entry["asset_key"]] = entry
    root = registry_root.resolve()
    result = []
    for task in generated_asset_tasks(deck):
        item = {k: v for k, v in task.items() if k != "prompt"}
        entry = by_key.get(task["asset_key"])
        if not entry or entry.get("contract_digest") != task["contract_digest"]:
            item.update(status="GENERATE_REQUIRED", reason="missing or changed asset contract")
            result.append(item)
            continue
        relative = Path(str(entry.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts or not relative.name:
            item.update(status="GENERATE_REQUIRED", reason="unsafe asset path")
            result.append(item)
            continue
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            item.update(status="GENERATE_REQUIRED", reason="asset file missing")
            result.append(item)
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry.get("sha256") or entry.get("review_status") != "VISUAL_PASS_CONCEPTUAL_ONLY":
            item.update(status="GENERATE_REQUIRED", reason="hash or visual review mismatch")
            result.append(item)
            continue
        from PIL import Image, UnidentifiedImageError
        try:
            with Image.open(path) as image:
                if image.mode != "RGBA" or image.width < 512 or image.height < 512:
                    item.update(status="GENERATE_REQUIRED", reason="asset is not a sufficiently large RGBA image")
                else:
                    alpha = image.getchannel("A")
                    corners = [alpha.getpixel(point) for point in
                               ((0, 0), (image.width - 1, 0),
                                (0, image.height - 1), (image.width - 1, image.height - 1))]
                    if any(value != 0 for value in corners) or alpha.getextrema()[1] == 0:
                        item.update(status="GENERATE_REQUIRED", reason="background alpha is not transparent")
                    else:
                        item.update(status="REUSE", path=str(path), sha256=digest)
        except (OSError, UnidentifiedImageError):
            item.update(status="GENERATE_REQUIRED", reason="invalid image file")
        result.append(item)
    return result


def compile_page(deck: dict[str, Any], page: dict[str, Any]) -> dict[str, Any]:
    """Make a full-slide prompt, an art-only prompt, and exact-text manifest."""
    validate_deck(deck)
    if page not in deck["pages"]:
        raise VisualPromptContractError("Page is not in validated deck")
    style, content, layout = deck["STYLE_LOCK"], page["CONTENT_LOCK"], page["LAYOUT"]
    metaphor = page["VISUAL_METAPHOR"]
    negatives = deck["NEGATIVE_CONSTRAINTS"] + page["NEGATIVE_CONSTRAINTS"]
    palette = "、".join(f"{name}={value}" for name, value in style["palette"].items())
    style_lines = [
        f"STYLE_LOCK（整套保持一致，ID={style['style_id']}）",
        f"画幅：{style['canvas']} 横版。背景：{style['background']}",
        f"配色：{palette}。字体：{style['typography']}",
        f"图标：{style['iconography']}。表面与细节：{style['surfaces']}",
    ]
    text_lines = [
        "CONTENT_LOCK（以下引号中的文字必须逐字准确，不得改写或补充）",
        "字段名只用于定位，不要显示在画面上；只呈现引号中的锁定文字。",
        f"页眉：{json.dumps(content['eyebrow'], ensure_ascii=False)}",
        f"页码：{json.dumps(content['folio'], ensure_ascii=False)}",
        f"标题：{json.dumps(content['title'], ensure_ascii=False)}",
        f"副标题：{json.dumps(content['subtitle'], ensure_ascii=False)}",
    ]
    text_lines += [f"{block['id']}：{json.dumps(block['text'], ensure_ascii=False)}"
                   for block in content["text_blocks"]]
    text_lines += [
        f"左页脚：{json.dumps(content['footer_left'], ensure_ascii=False)}",
        f"右页脚：{json.dumps(content['footer_right'], ensure_ascii=False)}",
    ]
    layout_lines = [f"LAYOUT：{layout['grammar']}。视觉层级：{layout['hierarchy']}"]
    layout_lines += [
        (f"区域 {r['id']}，位置 {r['position']}：承载 {', '.join(r['content_ids'])}"
         if r['composition'] == layout['grammar'] else
         f"区域 {r['id']}，位置 {r['position']}：{r['composition']}；承载 {', '.join(r['content_ids'])}")
        for r in layout["regions"]
    ]
    art_lines = [f"VISUAL_METAPHOR：{metaphor['intent']}"] + [
        f"素材 {a['id']}（{a['kind']}）：{a['description']}；医学语义：{a['medical_semantics']}"
        for a in metaphor["assets"]
    ]
    negative_lines = ["NEGATIVE_CONSTRAINTS："] + [f"- {item}" for item in negatives]
    shared = style_lines + layout_lines + art_lines + negative_lines
    full_prompt = "\n".join([
        "生成一张供医学学术汇报使用的完整 PPT 图像。保持 16:9。",
        *style_lines, *text_lines, *layout_lines, *art_lines, *negative_lines,
        "文字正确性优先：若无法准确绘制某段文字，保留该处空白，禁止生成近似字。",
    ])
    art_prompt = "\n".join([
        "只生成该页的背景、图标和插画素材，不画任何文字、数字、符号、页码或来源。",
        "保留标题、正文、页脚所需的空白，由程序叠加锁定文字。",
        *shared,
    ])
    locked_text = [
        {"id": key, "text": content[key]}
        for key in ("eyebrow", "folio", "title", "subtitle")
    ] + [{"id": block["id"], "text": block["text"], "role": block["role"],
          "source_refs": block["source_refs"]} for block in content["text_blocks"]] + [
        {"id": "footer_left", "text": content["footer_left"]},
        {"id": "footer_right", "text": content["footer_right"]},
    ]
    return {
        "page_id": content["page_id"], "style_digest": _digest(style),
        "content_digest": _digest(content), "full_slide_prompt": full_prompt,
        "art_only_prompt": art_prompt, "locked_text": locked_text,
        "speaker_notes_source_refs": content["speaker_notes_source_refs"],
        "asset_manifest": metaphor["assets"],
        "status": "PROMPTS_ONLY_REQUIRES_GENERATION_AND_PIXEL_REVIEW",
    }


def compile_deck(deck: dict[str, Any]) -> list[dict[str, Any]]:
    validate_deck(deck)
    return [compile_page(deck, page) for page in deck["pages"]]


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile medical visual page contracts to prompts")
    parser.add_argument("deck_json", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--asset-registry", type=Path,
                        help="Reuse reviewed transparent assets; generate prompts only for missing meanings")
    args = parser.parse_args()
    deck = json.loads(args.deck_json.read_text(encoding="utf-8"))
    compiled = compile_deck(deck)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for item in compiled:
        page_dir = args.output_dir / item["page_id"]
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "full_slide_prompt.txt").write_text(item["full_slide_prompt"], encoding="utf-8")
        (page_dir / "art_only_prompt.txt").write_text(item["art_only_prompt"], encoding="utf-8")
        (page_dir / "verification_manifest.json").write_text(
            json.dumps({k: v for k, v in item.items() if not k.endswith("_prompt")},
                       ensure_ascii=False, indent=2), encoding="utf-8")
    tasks = generated_asset_tasks(deck)
    status = (asset_reuse_status(
        deck, json.loads(args.asset_registry.read_text(encoding="utf-8")),
        registry_root=args.asset_registry.parent)
        if args.asset_registry else [
            {**{k: v for k, v in task.items() if k != "prompt"},
             "status": "GENERATE_REQUIRED", "reason": "no asset registry"}
            for task in tasks
        ])
    (args.output_dir / "asset_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    asset_dir = args.output_dir / "assets"
    for task, item in zip(tasks, status):
        prompt_file = asset_dir / f"{task['asset_key']}.prompt.txt"
        if item["status"] == "GENERATE_REQUIRED":
            asset_dir.mkdir(exist_ok=True)
            prompt_file.write_text(task["prompt"], encoding="utf-8")
        elif prompt_file.is_file():
            prompt_file.unlink()
    print(f"compiled {len(compiled)} pages; reused {sum(x['status'] == 'REUSE' for x in status)} "
          f"of {len(status)} generated assets -> {args.output_dir}")


if __name__ == "__main__":
    main()
