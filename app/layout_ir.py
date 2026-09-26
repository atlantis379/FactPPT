"""Model-facing layout intent, kept separate from approved slide semantics.

The model may choose a visual composition and a focal Claim. It cannot supply
slide copy, geometry, source references, or medical relationships. Those remain
owned by the Semantic Deck and the deterministic compiler.
"""
from __future__ import annotations

import hashlib
import base64
import json
import math
import os
import urllib.request
from urllib.parse import urlparse
import unicodedata
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "layout-ir.v1"
BRIEF_VERSION = "layout-design-brief.v1"
MODEL_INSTRUCTIONS = (
    "You are designing editable medical teaching slides. Choose a composition "
    "from each page's VALID candidates using its goal, primary message, evidence "
    "structure and approved relationships. Avoid repeated card grids when a "
    "comparison, sequence, decision path or one focal point communicates better. "
    "Return JSON only: schema_version, semantic_digest, pages. Each page has "
    "page_id, archetype, optional focus_claim_id, and a concise rationale. "
    "FOCUS_EVIDENCE renders its focal Claim in the page's leading visual "
    "position, so its focus_claim_id must be the page's FIRST approved Claim; to "
    "emphasise a later Claim without reordering the approved sequence, use "
    "FLEX_COMPOSITION instead. "
    "FLEX_COMPOSITION also requires layout_tree: a nested row/column tree whose "
    "leaves are {kind:'claim', claim_id, weight:1..4}; containers have kind row "
    "or column, 2..4 children, optional gap:8..40 and weight:1..4. Keep Claims "
    "in their approved order and include each exactly once. "
    "Never rewrite, omit, infer, or add a Claim, number, relationship or source. "
    "Choose only a VALID candidate. If even the most conservative valid layout "
    "expresses the page poorly, state that limitation in the rationale. The "
    "application will reject layouts whose exact approved text cannot fit."
)


class LayoutIntentError(ValueError):
    """A proposed layout is stale, incomplete, or outside the approved envelope."""


def _validate_tree(node: Any, *, depth: int = 0) -> list[str]:
    if not isinstance(node, dict) or depth > 3:
        raise LayoutIntentError("FLEX_COMPOSITION tree must be a bounded object")
    kind = node.get("kind")
    weight = node.get("weight", 1)
    if not isinstance(weight, int) or isinstance(weight, bool) or not 1 <= weight <= 4:
        raise LayoutIntentError("Layout tree weight must be an integer from 1 to 4")
    if kind == "claim":
        if set(node) - {"kind", "claim_id", "weight"} or not isinstance(node.get("claim_id"), str):
            raise LayoutIntentError("Layout tree Claim leaf must contain only an approved claim_id")
        return [node["claim_id"]]
    if kind not in {"row", "column"} or set(node) - {"kind", "children", "gap", "weight"}:
        raise LayoutIntentError("Layout tree containers must be row or column")
    children = node.get("children")
    gap = node.get("gap", 20)
    if not isinstance(children, list) or not 2 <= len(children) <= 4 or not isinstance(gap, int) or not 8 <= gap <= 40:
        raise LayoutIntentError("Layout tree container requires 2-4 children and gap 8-40")
    result = []
    for child in children:
        result.extend(_validate_tree(child, depth=depth + 1))
    return result


def semantic_digest(deck: dict[str, Any]) -> str:
    """Bind design decisions to the fields whose change makes them stale."""
    locked = [{
        "page_id": page.get("page_id"),
        "title": page.get("title"),
        "primary_message": page.get("primary_message"),
        "visual_type": page.get("visual_type"),
        "goal": page.get("goal"),
        "renders_structure": page.get("renders_structure"),
        "structure_text": page.get("structure_text"),
        "structure_segments": page.get("structure_segments"),
        "claims": [{
            "id": claim.get("id"),
            "text": claim.get("normalized_claim"),
            "conditions": claim.get("conditions"),
            "numeric_facts": claim.get("numeric_facts"),
            "source_refs": claim.get("source_refs"),
        } for claim in page.get("claims", [])],
        "relationships": page.get("relationships", []),
    } for page in deck.get("pages", [])]
    return hashlib.sha256(json.dumps(locked, ensure_ascii=False, sort_keys=True,
                                     default=str).encode("utf-8")).hexdigest()


def _candidates(page: dict[str, Any]) -> list[dict[str, Any]]:
    # Import here to avoid a module cycle: native_beautifier consumes this IR.
    from app.native_beautifier import _evaluate_candidates
    return _evaluate_candidates(page, include_focus=True)


def design_brief(deck: dict[str, Any], *, page_ids: list[str] | None = None) -> dict[str, Any]:
    """The only payload an optional layout model should receive."""
    selected = set(page_ids) if page_ids is not None else None
    pages = []
    for page in deck.get("pages", []):
        if selected is not None and page["page_id"] not in selected:
            continue
        pages.append({
            "page_id": page["page_id"],
            "goal": page.get("goal", ""),
            "title": page.get("title", ""),
            "primary_message": page.get("primary_message", ""),
            "visual_type": page.get("visual_type", ""),
            "claims": [{"id": c["id"], "text": c.get("normalized_claim", ""),
                        "conditions": c.get("conditions", []), "risk": c.get("risk", "")}
                       for c in page.get("claims", [])],
            "relationships": [{"id": r.get("id"), "from_claim_id": r.get("from_claim_id"),
                               "to_claim_id": r.get("to_claim_id"),
                               "relation_type": r.get("relation_type"),
                               "direction": r.get("direction")}
                              for r in page.get("relationships", [])],
            "candidates": _candidates(page),
        })
    if selected is not None and {p["page_id"] for p in pages} != selected:
        raise LayoutIntentError("Unknown page_id in layout brief request")
    return {"schema_version": BRIEF_VERSION, "semantic_digest": semantic_digest(deck),
            "instructions": MODEL_INSTRUCTIONS, "pages": pages}


def validate_layout_ir(deck: dict[str, Any], layout_ir: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(layout_ir, dict) or layout_ir.get("schema_version") != SCHEMA_VERSION:
        raise LayoutIntentError(f"Expected {SCHEMA_VERSION}")
    if layout_ir.get("semantic_digest") != semantic_digest(deck):
        raise LayoutIntentError("Layout intent is stale relative to the approved Semantic Deck")
    if set(layout_ir) - {"schema_version", "semantic_digest", "pages", "adapter"}:
        raise LayoutIntentError("Layout intent contains unsupported top-level fields")
    page_index = {page["page_id"]: page for page in deck.get("pages", [])}
    proposals = layout_ir.get("pages")
    if not isinstance(proposals, list):
        raise LayoutIntentError("Layout intent pages must be a list")
    seen: set[str] = set()
    for proposal in proposals:
        if not isinstance(proposal, dict) or set(proposal) - {"page_id", "archetype", "focus_claim_id", "layout_tree", "rationale"}:
            raise LayoutIntentError("Layout page contains unsupported fields")
        page_id = proposal.get("page_id")
        if page_id in seen or page_id not in page_index:
            raise LayoutIntentError(f"Duplicate or unknown layout page: {page_id}")
        seen.add(page_id)
        page = page_index[page_id]
        valid = {c["archetype"] for c in _candidates(page) if c["status"] == "VALID"}
        if proposal.get("archetype") not in valid:
            raise LayoutIntentError(f"Page {page_id}: archetype is not a valid candidate")
        focal = proposal.get("focus_claim_id")
        claim_ids = {c["id"] for c in page.get("claims", [])}
        if focal is not None and (proposal["archetype"] not in {"FOCUS_EVIDENCE", "FLEX_COMPOSITION"} or focal not in claim_ids):
            raise LayoutIntentError(f"Page {page_id}: invalid focal Claim")
        if proposal["archetype"] == "FOCUS_EVIDENCE" and not focal:
            raise LayoutIntentError(f"Page {page_id}: FOCUS_EVIDENCE requires focus_claim_id")
        if proposal["archetype"] == "FOCUS_EVIDENCE":
            # The focal block occupies the page's leading visual position. Promoting a
            # Claim that is not first in the approved sequence would silently reorder
            # the page while every Claim text stays byte-identical, which is exactly
            # the class of presentation-level distortion this system exists to block.
            approved = [str(claim.get("id", "")) for claim in page.get("claims", [])]
            if approved and focal != approved[0]:
                raise LayoutIntentError(
                    f"Page {page_id}: FOCUS_EVIDENCE leads with its focal Claim, so "
                    f"focus_claim_id must be the first approved Claim ({approved[0]}), "
                    f"not {focal}; use FLEX_COMPOSITION to emphasise a later Claim without "
                    "reordering the approved sequence")
        if proposal["archetype"] == "FLEX_COMPOSITION":
            tree = proposal.get("layout_tree")
            if not isinstance(tree, dict) or tree.get("kind") not in {"row", "column"}:
                raise LayoutIntentError(f"Page {page_id}: FLEX_COMPOSITION requires a row/column layout_tree")
            leaf_order = _validate_tree(tree)
            approved_order = [claim["id"] for claim in page.get("claims", [])]
            if leaf_order != approved_order:
                raise LayoutIntentError(f"Page {page_id}: layout tree must contain every Claim once in approved order")
        elif "layout_tree" in proposal:
            raise LayoutIntentError(f"Page {page_id}: layout_tree requires FLEX_COMPOSITION")
        if not isinstance(proposal.get("rationale"), str) or not proposal["rationale"].strip():
            raise LayoutIntentError(f"Page {page_id}: visual rationale is required")
    return layout_ir


def merge_layout_ir(deck: dict[str, Any], existing: dict[str, Any] | None,
                    incoming: dict[str, Any]) -> dict[str, Any]:
    validate_layout_ir(deck, incoming)
    old_pages = validate_layout_ir(deck, existing)["pages"] if existing else []
    merged = {p["page_id"]: p for p in old_pages}
    merged.update({p["page_id"]: p for p in incoming["pages"]})
    return validate_layout_ir(deck, {
        "schema_version": SCHEMA_VERSION,
        "semantic_digest": semantic_digest(deck),
        "pages": [merged[page["page_id"]] for page in deck["pages"] if page["page_id"] in merged],
        "adapter": incoming.get("adapter", existing.get("adapter") if existing else None),
    })


def configured_model() -> dict[str, Any]:
    """An OpenAI-compatible chat endpoint; secrets stay in environment variables."""
    url = os.environ.get("EASYPPT_LAYOUT_MODEL_URL", "").strip()
    model_id = os.environ.get("EASYPPT_LAYOUT_MODEL_ID", "").strip()
    if not url or not model_id:
        raise LayoutIntentError("Set EASYPPT_LAYOUT_MODEL_URL and EASYPPT_LAYOUT_MODEL_ID")
    parsed = urlparse(url)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme not in ({"http", "https"} if local else {"https"}) or not parsed.hostname:
        raise LayoutIntentError("Layout model URL must be loopback HTTP or HTTPS")
    return {"url": url, "model_id": model_id, "external": not local,
            "adapter_id": f"openai-compatible:{model_id}",
            "api_key_env": "EASYPPT_LAYOUT_MODEL_API_KEY"}


def configured_review_model() -> dict[str, Any]:
    """A separately configured vision reviewer for PowerPoint-rendered slides."""
    url = os.environ.get("EASYPPT_LAYOUT_REVIEW_MODEL_URL", "").strip()
    model_id = os.environ.get("EASYPPT_LAYOUT_REVIEW_MODEL_ID", "").strip()
    if not url or not model_id:
        raise LayoutIntentError("Set EASYPPT_LAYOUT_REVIEW_MODEL_URL and EASYPPT_LAYOUT_REVIEW_MODEL_ID")
    parsed = urlparse(url)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme not in ({"http", "https"} if local else {"https"}) or not parsed.hostname:
        raise LayoutIntentError("Visual review model URL must be loopback HTTP or HTTPS")
    design_url = os.environ.get("EASYPPT_LAYOUT_MODEL_URL", "").strip()
    design_id = os.environ.get("EASYPPT_LAYOUT_MODEL_ID", "").strip()
    if url == design_url and model_id == design_id:
        raise LayoutIntentError("Visual reviewer must differ from the layout designer")
    return {"url": url, "model_id": model_id, "external": not local,
            "adapter_id": f"openai-compatible:{model_id}",
            "api_key_env": "EASYPPT_LAYOUT_REVIEW_MODEL_API_KEY"}


def _call_json_model(messages: list[dict[str, Any]], model: dict[str, Any]) -> dict[str, Any]:
    payload = {"model": model["model_id"], "temperature": 0.2, "messages": messages}
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get(model.get("api_key_env", "EASYPPT_LAYOUT_MODEL_API_KEY"), "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(model["url"],
                                     data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                     headers=headers, method="POST")
    try:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, fp, code, msg, headers, newurl):
                return None

        with urllib.request.build_opener(NoRedirect).open(request, timeout=90) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(content)
    except (OSError, KeyError, IndexError, TypeError, ValueError) as error:
        raise LayoutIntentError(f"Layout model call or JSON response failed: {type(error).__name__}") from error
    if not isinstance(result, dict):
        raise LayoutIntentError("Layout model response must be a JSON object")
    return result


def call_layout_model(brief: dict[str, Any], model: dict[str, Any], *, feedback: str = "") -> dict[str, Any]:
    """Run one model design call; the caller must enforce data-egress policy."""
    messages = [{"role": "system", "content": MODEL_INSTRUCTIONS},
                {"role": "user", "content": json.dumps(brief, ensure_ascii=False)}]
    if feedback:
        messages.append({"role": "user", "content": "Previous design needs revision. "
                         "Choose another valid composition without changing content. Feedback: " + feedback[:1000]})
    return _call_json_model(messages, model)


def call_visual_review_model(brief: dict[str, Any], image_path: Path,
                             model: dict[str, Any]) -> dict[str, Any]:
    """Advisory visual critique of an actual rendered slide, never a factual gate."""
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    messages = [
        {"role": "system", "content": (
            "Review the rendered medical presentation slide for visual hierarchy, legibility, "
            "unnecessary whitespace, crowded text, and whether its chosen visual grammar "
            "serves the stated page goal. Do not judge or rewrite medical facts. Return JSON "
            "only with page_id, verdict (PASS or REVISE), and concerns (array of concise strings). "
            "This is advisory; deterministic source and object checks remain authoritative.")},
        {"role": "user", "content": [
            {"type": "text", "text": json.dumps(brief, ensure_ascii=False)},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded}},
        ]},
    ]
    result = _call_json_model(messages, model)
    expected_page = brief["pages"][0]["page_id"]
    if (result.get("page_id") != expected_page or result.get("verdict") not in {"PASS", "REVISE"}
            or not isinstance(result.get("concerns"), list)
            or not all(isinstance(item, str) for item in result["concerns"])):
        raise LayoutIntentError(f"Invalid visual review response for page {expected_page}")
    return {"page_id": expected_page, "verdict": result["verdict"],
            "concerns": result["concerns"][:10]}


def _fallback_width(text: str, font_px: float) -> float:
    return sum(font_px * (1.0 if unicodedata.east_asian_width(ch) in "WF" else 0.56)
               for ch in text)


#: DrawingML default text-frame insets, in IR canvas pixels (the IR canvas is 96 px/in).
#: The writer emits ``<a:bodyPr anchor="t">`` without explicit inset attributes, so a
#: reader applies these defaults and lays the text out inside a SMALLER area than the
#: declared box. Measuring a text box as if it had no inset under-reports the wrapped
#: line count right at the wrap boundary: the estimator said two lines, the renderer
#: drew three, and the overflow landed on the provenance label below.
TEXT_FRAME_INSET_HORIZONTAL = 9.6   # lIns = rIns = 91440 EMU = 0.1 in
TEXT_FRAME_INSET_VERTICAL = 4.8     # tIns = bIns = 45720 EMU = 0.05 in


def text_frame_insets(kind: str) -> tuple[float, float]:
    """The insets a text frame of this kind really gets in the delivered file."""
    if kind == "text":
        return TEXT_FRAME_INSET_HORIZONTAL, TEXT_FRAME_INSET_VERTICAL
    # A shape carries its own visible border, so the planner already budgets padding.
    return 16.0, 8.0


def measure_text(text: str, width: int, font_size: int, *,
                 horizontal_inset: int = 16, vertical_inset: int = 8) -> dict[str, Any]:
    """Conservative CJK-aware line measure; Pillow upgrades it to glyph widths."""
    # The shared IR uses a 96 px/in canvas, including its font sizes.
    font_px = font_size
    measure = None
    method = "unicode-width-estimate"
    try:
        from PIL import ImageFont
        font_path = Path(r"C:\Windows\Fonts\msyh.ttc")
        if font_path.exists():
            font = ImageFont.truetype(str(font_path), round(font_px))
            measure = lambda value: font.getlength(value)
            method = "pillow-microsoft-yahei"
    except (ImportError, OSError):
        pass
    measure = measure or (lambda value: _fallback_width(value, font_px))
    available = max(1, width - 2 * horizontal_inset)
    lines = 0
    for paragraph in str(text).split("\n"):
        if not paragraph:
            lines += 1
            continue
        current = ""
        for ch in paragraph:
            if current and measure(current + ch) > available:
                lines += 1
                current = ch
            else:
                current += ch
        lines += 1 if current else 0
    required_height = math.ceil(max(1, lines) * font_px * 1.28 + 2 * vertical_inset)
    return {"method": method, "line_count": lines, "required_height": required_height}


def assess_plan_text_fit(plan: dict[str, Any]) -> dict[str, Any]:
    """Flag boxes likely to trigger PowerPoint's silent font shrinking."""
    issues = []
    for page in plan.get("pages", []):
        for element in page.get("elements", []):
            if not str(element.get("name", "")).startswith(("claim:", "title:", "primary:", "source-trace:")):
                continue
            text = element.get("text", "")
            if not text:
                continue
            pos = element["position"]
            font_size = element.get("style", {}).get("fontSize", 17)
            horizontal_inset, vertical_inset = text_frame_insets(element["kind"])
            measured = measure_text(text, pos["width"], font_size,
                                    horizontal_inset=horizontal_inset,
                                    vertical_inset=0 if element["kind"] == "text" else vertical_inset)
            if measured["required_height"] > pos["height"]:
                issues.append({"page_id": page["page_id"], "object": element["name"],
                               "declared_height": pos["height"], **measured})
    return {"status": "PASS" if not issues else "REVIEW", "issues": issues}
