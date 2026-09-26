"""Generator-independent readback verification of a RENDERED .pptx.

Why this module exists
----------------------
Every other check in this project reads the *declaration* (semantic deck, plan
JSON, verification result). A whole class of defect exists only in the rendered
artifact and is invisible to those checks:

    ①③          declared: 1, 2, 3, 4
    ②④          rendered: 1, 3, 2, 4     <- the reader sees a broken sequence

The GOLD 2026 audit found exactly this (finding A04: a two-column placement made
the numbering read 1->3->2->4). That deck was produced by a different pipeline;
the point is not that one deck was wrong, it is that **no layer of this system
could see the defect class at all**.

Independence is the whole point
-------------------------------
A verifier that shares the generator's implementation, runtime or intermediate
JSON cannot catch the generator's systematic errors. This module therefore:

  * reads the delivered file with ``python-pptx`` only -- never the builder's own
    inspection output, and never the Node layout tool;
  * imposes no dependency on the beautifier, so it can validate a deck produced
    by any pipeline, including externally supplied ones;
  * recomputes geometry, order and text from the bytes actually shipped.

Defect family covered
---------------------
  SLIDE_COUNT_MISMATCH      delivered slide count differs from the contract
  MANDATORY_OBJECT_MISSING  a declared mandatory object is absent from the slide
  OBJECT_OFF_CANVAS         an object extends past the canvas edge
  EXACT_TEXT_MISSING        a locked string is not present on the slide
  TEXT_TRUNCATED            rendered text is shorter than the declared text
  EMPTY_TEXT_OBJECT         a declared non-empty text object renders empty
  READING_ORDER_MISMATCH    visual reading order contradicts the declared order
  Z_ORDER_INVERTED          a decorative layer is rendered above a semantic one
  SEMANTIC_LAYER_OCCLUDED   a semantic object is covered by an overlay
  UNKNOWN_OBJECT            the slide carries an object absent from the contract

Deliberately NOT covered (stated, not implied): colour, font, aesthetic quality,
and anything requiring the generator's internals.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Sequence

EMU_PER_PX = 9525
DEFAULT_CANVAS = (1280, 720)

#: objects whose TOP edges fall within this fraction of the median object height
#: belong to the same visual band
ROW_BAND_RATIO = 0.50
#: a semantic object is considered occluded when an overlay covers this fraction
OCCLUSION_RATIO = 0.50
#: geometry comparisons are exact within a pixel
BOX_TOLERANCE_PX = 1.0


# ------------------------------------------------------------------ extraction
def _px(emu: Any) -> float:
    return round(float(emu) / EMU_PER_PX, 3)


def read_slide_shapes(pptx_path: str | Path) -> list[dict]:
    """Per slide, the shapes actually present in the delivered file.

    Reads the shipped bytes with python-pptx. Shape document order is PowerPoint
    z-order (later = nearer the viewer).
    """
    from pptx import Presentation
    presentation = Presentation(str(pptx_path))
    slides = []
    for index, slide in enumerate(presentation.slides):
        shapes = []
        for z, shape in enumerate(slide.shapes):
            text = ""
            if shape.has_text_frame:
                text = shape.text_frame.text or ""
            shapes.append({
                "name": shape.name,
                "z": z,
                "box": [_px(shape.left), _px(shape.top),
                        _px(shape.width), _px(shape.height)],
                "text": text,
                "is_text": bool(shape.has_text_frame),
                "is_picture": shape.shape_type is not None and str(shape.shape_type).startswith("PICTURE"),
                "is_chart": bool(shape.has_chart),
            })
        slides.append({"index": index, "shapes": shapes})
    return slides


def canvas_size(pptx_path: str | Path) -> tuple[int, int]:
    from pptx import Presentation
    presentation = Presentation(str(pptx_path))
    return (round(presentation.slide_width / EMU_PER_PX),
            round(presentation.slide_height / EMU_PER_PX))


# -------------------------------------------------------------------- geometry
def _vertical_overlap(a: Sequence[float], b: Sequence[float]) -> float:
    top = max(a[1], b[1])
    bottom = min(a[1] + a[3], b[1] + b[3])
    if bottom <= top:
        return 0.0
    shorter = min(a[3], b[3]) or 1.0
    return (bottom - top) / shorter


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 1.0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def compute_visual_order(shapes: Sequence[dict]) -> list[str]:
    """Deterministic visual reading order: bands top-to-bottom, left-to-right.

    A band is a set of objects whose TOP edges fall within a tolerance derived
    from the median object height. Top-band clustering (rather than vertical-range
    overlap) is used on purpose: a tall decorative rule -- the 8x76 accent bar the
    native builder draws beside the header -- would otherwise drag the title below
    it into the header band and invent a reading-order defect that a reader does
    not experience.
    """
    if not shapes:
        return []
    band = max(4.0, _median([s["box"][3] for s in shapes]) * ROW_BAND_RATIO)
    ordered = sorted(shapes, key=lambda s: (s["box"][1], s["box"][0]))
    order: list[str] = []
    band_top: float | None = None
    row: list[dict] = []
    for shape in ordered:
        top = shape["box"][1]
        if band_top is None or abs(top - band_top) <= band:
            row.append(shape)
            band_top = top if band_top is None else band_top
        else:
            order.extend(s["name"] for s in sorted(row, key=lambda s: s["box"][0]))
            row = [shape]
            band_top = top
    order.extend(s["name"] for s in sorted(row, key=lambda s: s["box"][0]))
    return order


def _intersection_area(a: Sequence[float], b: Sequence[float]) -> float:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[0] + a[2], b[0] + b[2])
    bottom = min(a[1] + a[3], b[1] + b[3])
    if right <= left or bottom <= top:
        return 0.0
    return (right - left) * (bottom - top)


# ------------------------------------------------------------------- contract
def contract_from_plan(plan: dict, *, canvas: Sequence[int] | None = None,
                       roles: dict | None = None,
                       visual_contracts: Sequence[dict] | None = None) -> dict:
    """Adapt the application's own declarations into a readback contract.

    Inputs are exactly what the app already produces:
      * the beautification plan -- element names and geometry;
      * optionally the visual contracts -- ``exact_text_register`` (locked text)
        and ``mandatory_object_ids``.

    Joins that must be explicit rather than assumed:
      * element NAMES are the join key between plan and file;
      * ``reading_index`` (if present) states the intended reading position,
        otherwise plan order is the intended order;
      * ``mandatory_object_ids`` are CLAIM ids while plan elements are named
        ``claim:<claim_id>``, so the id is mapped to its element name -- otherwise
        the mandatory check could never match anything;
      * ``connectors`` carry no geometry, so they are registered name-only rather
        than having a box invented for them;
    * ``editorial_assets`` ARE geometry-bearing: the builder names each underlay
        after its ``asset_id`` and positions it at ``placement``, so they are
        registered like any other object instead of surfacing as "unknown";
      * layer ``roles`` are NOT guessed; without an explicit declaration the
        Z-order/occlusion checks are reported as not performed.

    The plan carries no canvas; the native builder is fixed at 1280x720, which is
    therefore the default and can be overridden.
    """
    contracts_by_page = {c.get("page_id"): c for c in (visual_contracts or [])}
    pages = []
    for page in plan.get("pages", []):
        elements = page.get("elements") or []
        declared = []
        for position, element in enumerate(elements):
            declared.append({
                "name": element.get("name"),
                "box": [element["position"][k] for k in ("left", "top", "width", "height")],
                "text": element.get("text", ""),
                "order": element.get("reading_index", position),
                "has_geometry": True,
            })
        for connector in page.get("connectors") or []:
            if connector.get("name"):
                declared.append({"name": connector["name"], "box": None, "text": "",
                                 "order": None, "has_geometry": False})
        # The native builder names each editorial underlay after its asset_id and
        # places it at asset.placement, so underlays are contract-described too --
        # no need to guess, and no need to let them register as "unknown".
        for asset in page.get("editorial_assets") or []:
            placement = asset.get("placement") or {}
            name = asset.get("asset_id")
            if name and all(k in placement for k in ("left", "top", "width", "height")):
                declared.append({
                    "name": name,
                    "box": [placement[k] for k in ("left", "top", "width", "height")],
                    "text": "", "order": None, "has_geometry": True,
                })

        visual = contracts_by_page.get(page.get("page_id")) or {}
        locked = visual.get("exact_text_register")
        if locked is None:
            locked = page.get("exact_text_register") or []
        mandatory_ids = [str(i) for i in (visual.get("mandatory_object_ids") or [])]
        names = {o["name"] for o in declared}
        mandatory = []
        for claim_id in mandatory_ids:
            for candidate in (f"claim:{claim_id}", claim_id):
                if candidate in names:
                    mandatory.append(candidate)
                    break

        # Reading order is the page's OWN semantic sequence. The element array is
        # a construction order (the flow archetype emits a whole column before the
        # next one), so using it as the reading order would invent defects. The
        # page declares its sequence through ``claim_ids``.
        reading_order = []
        for claim_id in [str(c) for c in (page.get("claim_ids") or [])]:
            for candidate in (f"claim:{claim_id}", f"step:{claim_id}"):
                if candidate in names:
                    reading_order.append(candidate)
                    break

        page_roles = (roles or {}).get(page.get("page_id")) or page.get("roles") or {}
        pages.append({
            "page_id": page.get("page_id"),
            "objects": declared,
            "mandatory": mandatory,
            "exact_text": [str(t) for t in locked],
            "required_text_by_object": page.get("required_text_by_object") or {},
            "reading_order": reading_order,
            "roles": dict(page_roles),
        })
    return {"canvas": list(canvas or plan.get("canvas") or DEFAULT_CANVAS), "pages": pages}


# ------------------------------------------------------------------ verification
#: issue severity per code. Anything declared in the contract and then missing,
#: moved or mutated in the delivered file BLOCKS: shipping a deck that silently
#: dropped a declared element is exactly the defect this verifier exists to stop.
SEVERITY = {
    "ARTIFACT_MISSING": "BLOCK",
    "RENDER_CANVAS_MISMATCH": "BLOCK",
    "SLIDE_COUNT_MISMATCH": "BLOCK",
    "MANDATORY_OBJECT_MISSING": "BLOCK",
    "EXPECTED_OBJECT_MISSING": "BLOCK",
    "OBJECT_OFF_CANVAS": "BLOCK",
    "EXACT_TEXT_MISSING": "BLOCK",
    "EXACT_TEXT_MUTATED": "BLOCK",
    "TEXT_TRUNCATED": "BLOCK",
    "EMPTY_TEXT_OBJECT": "BLOCK",
    "REQUIRED_TEXT_MISSING": "BLOCK",
    "UNDECLARED_CHART": "BLOCK",
    "READING_ORDER_MISMATCH": "BLOCK",
    "Z_ORDER_INVERTED": "BLOCK",
    "SEMANTIC_LAYER_OCCLUDED": "BLOCK",
    # cosmetic / informational divergence: reported, not delivery-blocking
    "GEOMETRY_DRIFT": "HUMAN_REVIEW",
    "UNKNOWN_OBJECT": "HUMAN_REVIEW",
}


def _issue(code: str, **detail) -> dict:
    return {"code": code, "severity": SEVERITY.get(code, "HUMAN_REVIEW"), "detail": detail}


def _co_located_names(shapes: Sequence[dict]) -> set[str]:
    """Names sharing a box with another shape (e.g. a scrim exactly over a card).

    Such layers are not participants in a reading SEQUENCE -- their relative order
    is undefined, so judging reading order between them would be a false positive.
    """
    groups: list[list[dict]] = []
    for shape in shapes:
        for group in groups:
            if all(abs(shape["box"][i] - group[0]["box"][i]) <= BOX_TOLERANCE_PX
                   for i in range(4)):
                group.append(shape)
                break
        else:
            groups.append([shape])
    return {s["name"] for group in groups if len(group) > 1 for s in group}


def _verify_page(page_contract: dict, rendered: dict, canvas: Sequence[int]) -> list[dict]:
    issues: list[dict] = []
    by_name = {s["name"]: s for s in rendered["shapes"]}
    declared = {o["name"]: o for o in page_contract["objects"]}

    # declared objects must exist, at the declared place, carrying the declared text
    for name, obj in declared.items():
        found = by_name.get(name)
        if found is None:
            issues.append(_issue("MANDATORY_OBJECT_MISSING" if name in page_contract["mandatory"]
                                 else "EXPECTED_OBJECT_MISSING",
                                 page_id=page_contract["page_id"], object=name))
            continue
        for axis, index in (("left", 0), ("top", 1), ("width", 2), ("height", 3)):
            if not obj.get("has_geometry", True):
                break
            if abs(found["box"][index] - obj["box"][index]) > BOX_TOLERANCE_PX:
                issues.append(_issue("GEOMETRY_DRIFT", page_id=page_contract["page_id"],
                                     object=name, axis=axis,
                                     declared=obj["box"][index], rendered=found["box"][index]))
        rendered_text = found["text"] or ""
        declared_text = obj.get("text") or ""
        if declared_text and not rendered_text.strip():
            issues.append(_issue("EMPTY_TEXT_OBJECT", page_id=page_contract["page_id"],
                                 object=name, declared=declared_text[:60]))
        elif declared_text and rendered_text.strip() != declared_text.strip():
            code = "TEXT_TRUNCATED" if rendered_text.strip() in declared_text else "EXACT_TEXT_MUTATED"
            issues.append(_issue(code, page_id=page_contract["page_id"], object=name,
                                 declared=declared_text[:80], rendered=rendered_text[:80]))
        for required in (page_contract.get("required_text_by_object") or {}).get(name, []):
            if required and required not in rendered_text:
                issues.append(_issue("REQUIRED_TEXT_MISSING", page_id=page_contract["page_id"],
                                     object=name, required=required))

    # nothing may be added that the contract does not know about
    for name in by_name:
        if name not in declared:
            issues.append(_issue("UNDECLARED_CHART" if by_name[name].get("is_chart") else "UNKNOWN_OBJECT",
                                 page_id=page_contract["page_id"], object=name))

    # canvas bounds
    width, height = canvas
    for shape in rendered["shapes"]:
        left, top, w, h = shape["box"]
        if left < -BOX_TOLERANCE_PX or top < -BOX_TOLERANCE_PX or \
                left + w > width + BOX_TOLERANCE_PX or top + h > height + BOX_TOLERANCE_PX:
            issues.append(_issue("OBJECT_OFF_CANVAS", page_id=page_contract["page_id"],
                                 object=shape["name"], box=shape["box"], canvas=list(canvas)))

    # locked strings must be visible somewhere on the slide
    slide_text = "\n".join(s["text"] or "" for s in rendered["shapes"])
    for locked in page_contract.get("exact_text", []):
        if locked and locked not in slide_text:
            issues.append(_issue("EXACT_TEXT_MISSING", page_id=page_contract["page_id"],
                                 text=str(locked)[:80]))

    # reading order: the visual sequence of the page's DECLARED semantic order must
    # match. Co-located layers are excluded: a stacked scrim/card pair has no
    # reading order between its members, so comparing them would be a false
    # positive. When the page declares no order the check is not performed, and the
    # coverage block says so rather than implying a pass.
    stacked = _co_located_names(rendered["shapes"])
    declared_order = [n for n in (page_contract.get("reading_order") or []) if n in by_name]
    if len(declared_order) >= 2:
        wanted = set(declared_order)
        participants = [s for s in by_name.values()
                        if s["name"] in wanted and s["name"] not in stacked]
        visual = [n for n in compute_visual_order(participants) if n in wanted]
        if visual != declared_order:
            issues.append(_issue("READING_ORDER_MISMATCH", page_id=page_contract["page_id"],
                                 declared=declared_order, rendered=visual))

    # layer roles: decorative must not sit above semantic, nor cover it
    roles = page_contract.get("roles") or {}
    semantic = set(roles.get("semantic") or [])
    overlay = set(roles.get("overlay") or [])
    if semantic and overlay:
        # z grows toward the viewer, so a violation is an overlay stacked ABOVE a
        # semantic object: max(overlay z) > min(semantic z).
        top_overlay = max((by_name[n]["z"] for n in overlay if n in by_name), default=-1)
        bottom_semantic = min((by_name[n]["z"] for n in semantic if n in by_name),
                              default=10 ** 6)
        if top_overlay > bottom_semantic:
            issues.append(_issue("Z_ORDER_INVERTED", page_id=page_contract["page_id"],
                                 semantic_z=bottom_semantic, overlay_z=top_overlay))
        for s_name in semantic:
            if s_name not in by_name:
                continue
            for o_name in overlay:
                if o_name not in by_name or by_name[o_name]["z"] < by_name[s_name]["z"]:
                    continue
                area = by_name[s_name]["box"][2] * by_name[s_name]["box"][3]
                if area <= 0:
                    continue
                covered = _intersection_area(by_name[s_name]["box"], by_name[o_name]["box"]) / area
                if covered >= OCCLUSION_RATIO:
                    issues.append(_issue("SEMANTIC_LAYER_OCCLUDED",
                                         page_id=page_contract["page_id"],
                                         object=s_name, by=o_name, covered=round(covered, 3)))
    return issues


def verify_render(pptx_path: str | Path, contract: dict) -> dict:
    """Verify a rendered .pptx against a readback contract."""
    path = Path(pptx_path)
    if not path.exists():
        missing = _issue("ARTIFACT_MISSING", path=str(path))
        return {"status": "BLOCK", "issues": [missing], "omission_report": [missing],
                "slides_checked": 0}

    slides = read_slide_shapes(path)
    canvas = list(contract.get("canvas") or DEFAULT_CANVAS)
    file_canvas = canvas_size(path)
    issues: list[dict] = []

    if list(file_canvas) != [round(v) for v in canvas]:
        issues.append(_issue("RENDER_CANVAS_MISMATCH", declared=list(canvas),
                             rendered=list(file_canvas)))
    pages = contract.get("pages", [])
    if len(slides) != len(pages):
        issues.append(_issue("SLIDE_COUNT_MISMATCH", declared=len(pages), rendered=len(slides)))

    for page_contract, rendered in zip(pages, slides):
        issues.extend(_verify_page(page_contract, rendered, canvas))

    blocked = [i for i in issues if i.get("severity") == "BLOCK"]
    status = "PASS" if not issues else ("BLOCK" if blocked else "HUMAN_REVIEW_REQUIRED")
    roles_declared = any((page.get("roles") or {}) for page in pages)
    order_declared = any(page.get("reading_order") for page in pages)
    return {
        "status": status,
        "artifact": str(path),
        "artifact_sha256": _sha256(path),
        "slides_checked": len(slides),
        "issues": issues,
        "omission_report": [issue for issue in issues if issue["code"] in {
            "SLIDE_COUNT_MISMATCH", "MANDATORY_OBJECT_MISSING", "EXPECTED_OBJECT_MISSING",
            "EXACT_TEXT_MISSING", "EXACT_TEXT_MUTATED", "TEXT_TRUNCATED",
            "EMPTY_TEXT_OBJECT", "REQUIRED_TEXT_MISSING", "UNDECLARED_CHART"}],
        "coverage": {
            "geometry": "CHECKED",
            "reading_order": "CHECKED" if order_declared
                             else "NOT_CHECKED_NO_ORDER_DECLARED",
            "exact_text": "CHECKED" if any(p.get("exact_text") for p in pages)
                          else "NOT_CHECKED_NO_LOCKED_TEXT_DECLARED",
            "z_order_and_occlusion": "CHECKED" if roles_declared
                                     else "NOT_CHECKED_NO_ROLES_DECLARED",
            "colour_and_aesthetics": "NOT_CHECKED",
        },
    }


def _sha256(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_report(pptx_path: str | Path, contract: dict, target: str | Path) -> dict:
    """Run the check and persist the machine-readable report."""
    result = verify_render(pptx_path, contract)
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    Path(target).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    """Run the readback on any deck, independently of how it was produced.

        python -m app.render_readback <deck.pptx> <plan.json> [--out report.json]
                                       [--visual-contracts contracts.json]

    Exit code 0 = PASS, 1 = not PASS (BLOCK or human review), 2 = usage error.
    """
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2:
        print(__doc__)
        print("usage: python -m app.render_readback DECK.pptx PLAN.json "
              "[--out REPORT.json] [--visual-contracts CONTRACTS.json]")
        return 2
    pptx_path, plan_path = args[0], args[1]
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    visual_contracts = None
    if "--visual-contracts" in args:
        vc_path = args[args.index("--visual-contracts") + 1]
        visual_contracts = json.loads(Path(vc_path).read_text(encoding="utf-8"))
    contract = contract_from_plan(plan, visual_contracts=visual_contracts)
    result = verify_render(pptx_path, contract)
    if "--out" in args:
        target = args[args.index("--out") + 1]
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
