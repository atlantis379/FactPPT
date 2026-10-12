"""Isolated native-PPT adapter for the visual prompt lab experiment.

This tool consumes actual, locally saved vector assets and authored region layouts.
It deliberately has no connection to production workflow state or APIs.
"""
from __future__ import annotations

import argparse
import copy
import json
import hashlib
import sys
from pathlib import Path
import math

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factdeck.visual_lab import validate_graph, digest as graph_digest

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "output" / "visual_prompt_lab"
GRAPH_FILES = (LAB / "semantic_graph.json", LAB / "extension_graph.json")
COMMON = LAB / "common_input.json"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _validated_graph_files():
    common_raw = COMMON.read_bytes()
    common = json.loads(common_raw.decode("utf-8"))
    pages_by_number = {p["number"]: p for p in common["pages"]}
    if len(pages_by_number) != len(common["pages"]):
        raise ValueError("common_input has duplicate page numbers")
    current_source_sha = hashlib.sha256(common_raw).hexdigest()
    specs = ((GRAPH_FILES[0], LAB / "graph_validation.json", LAB / "graph_review.json"),
             (GRAPH_FILES[1], LAB / "extension_graph_validation.json", LAB / "extension_graph_review.json"))
    all_graphs = {}
    graph_sha_by_page = {}
    for graph_path, validation_path, review_path in specs:
        graph = read_json(graph_path)
        selected = [pages_by_number[p["page"]["number"]] for p in graph["pages"]]
        check = validate_graph(selected, graph)
        recorded = read_json(validation_path)
        review = read_json(review_path)
        expected_graph_sha = graph_digest(graph)
        if recorded.get("structural_valid") is not True or recorded.get("graph_sha256") != expected_graph_sha:
            raise ValueError(f"graph validation is stale for {graph_path.name}")
        if review.get("status") != "SUPPORTED_WITH_NO_BLOCKERS" or review.get("graph_sha256") != expected_graph_sha:
            raise ValueError(f"independent graph review is stale or blocked for {graph_path.name}")
        if review.get("source_sha256") != current_source_sha:
            raise ValueError(f"independent graph review is not bound to current common_input: {graph_path.name}")
        if review.get("medical_approval") not in (False, "NOT_GRANTED"):
            raise ValueError(f"graph review carries an unexpected approval state: {graph_path.name}")
        if check["pages"] != len(graph["pages"]):
            raise ValueError(f"graph source validation did not cover every page: {graph_path.name}")
        for page in graph["pages"]:
            n = page["page"]["number"]
            if n in all_graphs:
                raise ValueError(f"duplicate graph page {n}")
            all_graphs[n] = page
            graph_sha_by_page[n] = expected_graph_sha
    return all_graphs, pages_by_number, current_source_sha, graph_sha_by_page


def _structurally_valid_graphs():
    common = read_json(COMMON)
    pages = {p["number"]: p for p in common["pages"]}
    result = {}
    for path in GRAPH_FILES:
        graph = read_json(path)
        selected = [pages[p["page"]["number"]] for p in graph["pages"]]
        validate_graph(selected, graph)
        for page in graph["pages"]:
            number = page["page"]["number"]
            if number in result:
                raise ValueError(f"duplicate graph page {number}")
            result[number] = page
    return result


def _fragment_index(graph):
    fragments = {f["id"]: f for f in graph["text_fragments"]}
    blocks = {b["block_index"]: b["text"] for b in graph["block_texts"]}
    for fragment in fragments.values():
        block = blocks.get(fragment["block_index"])
        if block is None or block[fragment["start"]:fragment["end"]] != fragment["quote"]:
            raise ValueError(f"fragment does not match source block: {fragment['id']}")
    return fragments, blocks


def _region_text(region, fragments, excluded_ids=()):
    ids = [i for i in region.get("label_fragment_ids", []) + region.get("body_fragment_ids", []) if i not in excluded_ids]
    ids.sort(key=lambda i: (fragments[i]["block_index"], fragments[i]["start"]))
    # Source offsets/quotes remain unchanged in the graph. Source line wrapping
    # is reflowed for the new layout, matching the design-prompt renderer.
    return "".join(fragments[i]["quote"] for i in ids).replace('\n',''), ids


def validate_graphs():
    graphs, common, _, _ = _validated_graph_files()
    if set(graphs) != set(common):
        raise ValueError("graph pages do not match frozen common_input page numbers")
    for number, graph in graphs.items():
        fragments, blocks = _fragment_index(graph)
        bindings = graph.get("block_bindings", [])
        aliases = {a["block_index"]: a for a in graph.get("render_aliases", [])}
        for alias in aliases.values():
            target = blocks[alias["block_index"]]
            covered = "".join(blocks[i] for i in alias["covered_by_block_indices"])
            if alias.get("normalization") != "whitespace_only" or "".join(target.split()) != "".join(covered.split()):
                raise ValueError(f"invalid nonrendering alias on page {number}")
        if bindings and len(bindings) != len(blocks):
            raise ValueError(f"source block binding count mismatch on page {number}")
        # Each non-alias source block must be covered exactly once by region fragments.
        uses = {}
        for region in graph["regions"]:
            for fragment_id in region.get("label_fragment_ids", []) + region.get("body_fragment_ids", []):
                if fragment_id not in fragments:
                    raise ValueError(f"unknown fragment {fragment_id} on page {number}")
                uses[fragment_id] = uses.get(fragment_id, 0) + 1
        for fragment_id, fragment in fragments.items():
            if uses.get(fragment_id) != 1:
                raise ValueError(f"fragment must belong to exactly one region: {fragment_id}")
        for relation in graph["relations"]:
            if not relation.get("source_mappings"):
                raise ValueError(f"relation lacks source mapping: {relation['id']}")
            for mapping in relation["source_mappings"]:
                if mapping["block_index"] not in blocks or any(i not in fragments for i in mapping["fragment_ids"]):
                    raise ValueError(f"relation has invalid source trace: {relation['id']}")
        # Table cell bindings are source-backed one-for-one; no flattened text surrogate.
        for binding in bindings:
            if binding.get("kind") == "table_cell" and not graph.get("source_table_shape"):
                raise ValueError(f"table cell binding without locked source table on page {number}")
    return graphs


def _manifest(path: Path):
    manifest = read_json(path)
    selected = manifest.get("selected_trial_ids")
    trials = manifest.get("trials")
    if not isinstance(selected, list) or len(selected) != 6 or len(set(selected)) != 6:
        raise ValueError("manifest.selected_trial_ids must contain six distinct trial ids")
    if not isinstance(trials, dict):
        raise ValueError("manifest.trials must map trial ids to asset/layout paths")
    common = read_json(COMMON)
    pages = {p["number"]: p for p in common["pages"]}
    frozen_page_numbers = set(pages)
    selected_numbers = []
    for trial_id in selected:
        trial = trials.get(trial_id)
        if not trial:
            raise ValueError(f"manifest has no trial record: {trial_id}")
        number = trial.get("page_number")
        if number not in pages:
            raise ValueError(f"trial {trial_id} has unsupported page_number {number}")
        selected_numbers.append(number)
    if len(selected_numbers) != len(set(selected_numbers)):
        raise ValueError("selected trials must use six distinct page numbers")
    if set(selected_numbers) != frozen_page_numbers:
        raise ValueError("selected trials must cover exactly the six frozen common_input pages")
    for trial_id in selected:
        trial = trials[trial_id]
        for key in ("svg_path", "components_path", "layout_path", "semantic_review_path", "design_png_path"):
            if not trial.get(key) or not Path(trial[key]).is_file():
                raise FileNotFoundError(f"trial {trial_id} missing required actual input: {key}={trial.get(key)}")
    graphs, pages, source_sha, graph_sha_by_page = _validated_graph_files()
    if set(graphs) != set(pages):
        raise ValueError("validated graphs do not cover exactly the six frozen common_input pages")
    result = []
    for trial_id in selected:
        trial = trials.get(trial_id)
        number = trial.get("page_number")
        paths = {key: Path(trial.get(key, "")) for key in ("svg_path", "components_path", "layout_path")}
        missing = [f"{key}={p}" for key, p in paths.items() if not p.is_file()]
        if missing:
            raise FileNotFoundError(f"trial {trial_id} missing actual assets/layout: " + ", ".join(missing))
        review_path = Path(trial.get("semantic_review_path", ""))
        design_path = Path(trial.get("design_png_path", ""))
        if not review_path.is_file() or not design_path.is_file():
            raise FileNotFoundError(f"trial {trial_id} requires a semantic review and its actual reviewed design PNG")
        review = read_json(review_path)
        _validate_semantic_review(review, trial_id, design_path, source_sha, graph_sha_by_page[number],Path(trial['clean_png_path']) if trial.get('clean_png_path') else None)
        layout = read_json(paths["layout_path"])
        result.append((trial_id, number, graphs[number], pages[number], paths, layout, review_path, design_path))
    return manifest, result


def _style(text, size=20, bold=False, color="151B24"):
    return [{"text": text, "size": size, "bold": bold, "color": {"hex": color, "a": 1}, "superscript": False, "mark": False}]


def _box(region_id, layout):
    entry = layout.get("regions", {}).get(region_id)
    if not isinstance(entry, dict) or not all(k in entry for k in ("x", "y", "w", "h")):
        raise ValueError(f"authored layout needs x/y/w/h for region {region_id}")
    box = {k: float(entry[k]) for k in ("x", "y", "w", "h")}
    if any(not math.isfinite(v) for v in box.values()) or box["w"] <= 0 or box["h"] <= 0 or box["x"] < 0 or box["y"] < 0 or box["x"] + box["w"] > 1280 or box["y"] + box["h"] > 720:
        raise ValueError(f"authored layout region is outside the slide: {region_id}")
    return box


def _new_text(text, region_id, layout, role="", default_size=20, bold=False):
    box = _box(region_id, layout)
    opts = layout["regions"][region_id]
    if region_id in layout.get('compact_interhan_spaces', []):
        import re
        text = re.sub(r'(?<=[\u4e00-\u9fff])[ \t]+(?=[\u4e00-\u9fff])', '', text)
    for boundary in layout.get('line_break_before', {}).get(region_id, []):
        if not boundary or boundary not in text:
            raise ValueError('Typographic break must reference existing source text')
        text = text.replace(boundary, '\n' + boundary, 1)
    return {**box, "align": opts.get("align", "left"), "anchor": opts.get("anchor", "top"),
            "role": role, "group": opts.get("group", ""), "lineHeight": float(opts.get("lineHeight", default_size * 1.3)),
            "nowrap": bool(opts.get("nowrap", False)), "paras": [_style(text, float(opts.get("size", default_size)), bool(opts.get("bold", bold)), opts.get("color", "151B24"))]}


def _source_callout_excerpt(callout, retained_region_texts):
    excerpt=callout['excerpt']
    source=retained_region_texts.get(callout['source_region'],'')
    if not isinstance(excerpt,str) or not excerpt or excerpt not in source:
        raise ValueError('Visual callout must be an exact excerpt of a retained source region')
    return excerpt


def _color_value(value, where):
    if isinstance(value, dict) and isinstance(value.get("hex"), str):
        value = value["hex"]
    if not isinstance(value, str) or len(value.removeprefix("#")) != 6:
        raise ValueError(f"{where} must be a six digit hex color")
    value = value.removeprefix("#")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{where} must be a six digit hex color") from exc
    return {"hex":value.upper(),"a":1}


def _table_dimensions(table_layout, table, graph_shape):
    original_columns = [float(c["w"]) for c in table["rows"][0]["cells"]]
    original_rows = [float(r["h"]) for r in table["rows"]]
    width, height = float(table_layout["w"]), float(table_layout["h"])
    if 'col_widths' in table_layout and 'column_widths' in table_layout and table_layout['col_widths']!=table_layout['column_widths']:
        raise ValueError('Conflicting authored column width fields')
    columns = table_layout.get("col_widths",table_layout.get('column_widths'))
    rows = table_layout.get("row_heights")
    if columns is None:
        columns = [v * width / sum(original_columns) for v in original_columns]
    if rows is None:
        rows = [v * height / sum(original_rows) for v in original_rows]
    columns = [float(v) for v in columns]
    rows = [float(v) for v in rows]
    if len(columns) != graph_shape["column_count"] or len(rows) != graph_shape["row_count"]:
        raise ValueError("authored table row_heights/col_widths do not match locked source table shape")
    if any(not math.isfinite(v) or v <= 0 for v in columns + rows):
        raise ValueError("authored table row_heights/col_widths must be finite positive values")
    if abs(sum(columns) - width) > 1 or abs(sum(rows) - height) > 1:
        raise ValueError("authored table row_heights/col_widths must sum to table w/h")
    # Absorb harmless rounding so PowerPoint's cell dimensions exactly fill the outer table.
    columns[-1] += width - sum(columns)
    rows[-1] += height - sum(rows)
    sx, sy = width / sum(original_columns), height / sum(original_rows)
    return columns, rows, sx, sy


def _apply_native_table_layout(table, table_layout, graph_shape, cell_region_by_position):
    columns, row_heights, sx, sy = _table_dimensions(table_layout, table, graph_shape)
    table.update({k: float(table_layout[k]) for k in ("x", "y", "w", "h")})
    font_scale = min(sx, sy)
    global_font_size = table_layout.get("font_size")
    if global_font_size is not None:
        global_font_size = float(global_font_size)
        if not math.isfinite(global_font_size) or global_font_size < 12:
            raise ValueError("authored table font_size must be at least 12px and finite")
    cell_styles = table_layout.get("cell_styles", {})
    for ri, row in enumerate(table["rows"]):
        row["h"] = row_heights[ri]
        for ci, cell in enumerate(row["cells"]):
            cell["w"] = columns[ci]
            rid = cell_region_by_position[(ri, ci)]
            style = cell_styles.get(rid, {})
            if not isinstance(style, dict):
                raise ValueError(f"table cell style must be an object: {rid}")
            if set(style) - {"font_size", "font_color", "fill", "border", "bold", "pad", "line_height", "align", "anchor"}:
                raise ValueError(f"unsupported table cell style property: {rid}")
            size = style.get("font_size", global_font_size)
            if size is not None:
                size = float(size)
                if not math.isfinite(size) or size < 12:
                    raise ValueError(f"authored table font_size for {rid} must be at least 12px")
            for para in cell.get("paras", []):
                for run in para:
                    if size is None:
                        run["size"] = max(12, float(run["size"]) * font_scale)
                    else:
                        run["size"] = size
                    if "font_color" in style:
                        run["color"] = _color_value(style["font_color"], f"font_color for {rid}")
                    if "bold" in style:
                        run["bold"] = bool(style["bold"])
            old_pad = cell["pad"]
            if "pad" in style:
                pad = style["pad"]
                if not isinstance(pad, list) or len(pad) != 4 or any(not isinstance(v, (int,float)) or isinstance(v,bool) or not math.isfinite(v) or v < 0 for v in pad):
                    raise ValueError(f"table cell pad must contain four finite nonnegative values: {rid}")
                cell["pad"] = [float(v) for v in pad]
            else:
                cell["pad"] = [float(old_pad[0])*sy, float(old_pad[1])*sx, float(old_pad[2])*sy, float(old_pad[3])*sx]
            natural_line_height = max((float(run["size"]) * 1.15 for para in cell.get("paras", []) for run in para), default=12)
            cell["lineHeight"] = float(style.get("line_height", max(float(cell["lineHeight"])*sy, natural_line_height)))
            if not math.isfinite(cell["lineHeight"]) or cell["lineHeight"] < natural_line_height:
                raise ValueError(f"table cell line_height must be finite and positive: {rid}")
            if "fill" in style:
                cell["fill"] = _color_value(style["fill"], f"fill for {rid}")
            if "border" in style:
                cell["border"] = _color_value(style["border"], f"border for {rid}") if style["border"] is not None else None
            if 'align' in style:
                if style['align'] not in ('left','center','right'):raise ValueError('Invalid cell alignment')
                cell['align']=style['align']
            if 'anchor' in style:
                if style['anchor'] not in ('top','middle','bottom'):raise ValueError('Invalid cell anchor')
                cell['anchor']=style['anchor']


def _connector_geometry(connector, relation, graph, layout, table_shape):
    source_region = connector.get("from_region")
    target_region = connector.get("to_region")
    if source_region not in relation["from"] or target_region not in relation["to"]:
        raise ValueError(f"connector endpoints disagree with graph direction: {relation['id']}")
    directed = relation["type"] in ("in_order", "condition")
    arrow = connector.get("arrow", False)
    if arrow and not directed:
        raise ValueError(f"arrow is not permitted for {relation['type']} relation {relation['id']}")
    if directed:
        if not arrow:
            raise ValueError(f"source-supported {relation['type']} relation needs a directed arrow: {relation['id']}")
        parents = {r["id"]: r.get("parent_region_id") for r in graph["regions"]}
        if parents.get(source_region) != parents.get(target_region):
            raise ValueError(f"cross-scope arrow is not permitted for relation {relation['id']}")
    points = connector.get("points")
    if not isinstance(points, list) or len(points) < 2:
        raise ValueError(f"connector needs at least two points: {relation['id']}")
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2 or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in point):
            raise ValueError(f"connector has invalid coordinates: {relation['id']}")
        if not (0 <= point[0] <= 1280 and 0 <= point[1] <= 720):
            raise ValueError(f"connector is outside the page: {relation['id']}")
    boxes = {rid: _box(rid, layout) for rid in layout.get("regions", {})}
    if table_shape and layout.get("table"):
        table = layout["table"]
        cell_map = {}
        for binding_index, binding in enumerate(graph.get("block_bindings", [])):
            if binding.get("kind") != "table_cell":
                continue
            rid = next((r["id"] for r in graph["regions"] if any(
                next(f for f in graph["text_fragments"] if f["id"] == fid)["block_index"] == binding_index
                for fid in r.get("label_fragment_ids", []) + r.get("body_fragment_ids", []))), None)
            if rid:
                cell_map[(binding["row"], binding["column"])] = rid
        for row in table_shape["rows"]:
            y = table["y"] + sum(r["height"] for r in table_shape["rows"][:row["row_index"]])
            for cell in row["cells"]:
                rid = cell_map.get((row["row_index"], cell["column_index"]))
                if rid:
                    x = table["x"] + sum(c["width"] for c in table_shape["rows"][0]["cells"][:cell["column_index"]])
                    boxes[rid] = {"x":x,"y":y,"w":cell["width"],"h":row["height"]}
    for label, point, rid in (("source", points[0], source_region), ("target", points[-1], target_region)):
        if rid not in boxes:
            raise ValueError(f"connector {label} region has no authored box: {rid}")
        box = boxes[rid]
        dx = max(box["x"] - point[0], 0, point[0] - (box["x"] + box["w"]))
        dy = max(box["y"] - point[1], 0, point[1] - (box["y"] + box["h"]))
        if math.hypot(dx, dy) > 12:
            raise ValueError(f"connector {label} endpoint is not attached to region {rid}")
    return points, arrow


def _validate_semantic_review(review, trial_id, design_path, source_sha, expected_graph_sha,clean_path=None):
    actual_sha = hashlib.sha256(design_path.read_bytes()).hexdigest()
    if review.get("status") in ("BLOCKERS_PRESENT", "BLOCKED", "FAIL") or review.get("blockers_present") is True:
        raise ValueError(f"trial {trial_id} semantic review has blockers")
    if review.get("status") not in ("PASS", "CLEAR", "NO_BLOCKERS"):
        raise ValueError(f"trial {trial_id} semantic review is missing a clear status")
    if review.get('scope')=='CLEAN_ARTWORK_AND_LOCKED_GRAPH':
        if clean_path is None or not clean_path.is_file():raise ValueError('Actual clean PNG required for clean-stage review')
        if review.get('original_design_sha256')!=actual_sha or review.get('reviewed_asset_sha256')!=hashlib.sha256(clean_path.read_bytes()).hexdigest():raise ValueError('Clean review must bind both actual clean PNG and original design')
        if review.get('original_design_approved') is not False:raise ValueError('Clean-stage clearance must not approve failed original design')
    elif review.get("reviewed_asset_sha256") != actual_sha:
        raise ValueError(f"trial {trial_id} review is not bound to the actual design PNG hash")
    if review.get("source_sha256") != source_sha:
        raise ValueError(f"trial {trial_id} semantic review is not bound to current common_input")
    if review.get("graph_sha256") != expected_graph_sha:
        raise ValueError(f"trial {trial_id} semantic review is not bound to its current graph")


def build_generation(manifest_path: Path):
    manifest, selected = _manifest(manifest_path)
    generation = {"font": manifest.get("font", read_json(COMMON).get("font", "Microsoft YaHei")), "pages": [], "figures": [], "logos": []}
    trace = {}
    for trial_id, number, graph, locked, paths, layout, review_path, design_path in selected:
        if layout.get("schema_version") != "visual-lab-native-layout.v1":
            raise ValueError(f"unsupported authored layout schema for {trial_id}")
        fragments, _ = _fragment_index(graph)
        aliases = {a["block_index"] for a in graph.get("render_aliases", [])}
        alias_fragment_ids = {f["id"] for f in fragments.values() if f["block_index"] in aliases}
        model = {"shapes": [], "texts": [], "tables": [], "lines": [],
                 "rasters": [], "figures": [], "background": copy.deepcopy(locked["lock"]["model"].get("background", {"hex":"F6F4EF","a":1})),
                 "checks": {k: [] for k in ("untracked","mismatch","overflow","bounds","overlap","figure_distortion","hierarchy","authored_lint","chart_geometry","figure_low_dpi")}}
        table_regions = {r["id"]: r for r in graph["regions"] if r["id"].endswith("_cell")}
        table_shape = (graph.get("source_table_shape") or [None])[0]
        table_region_ids = [r["id"] for r in table_regions.values()]
        # Build a native table only from the graph's locked cell bindings.
        if table_shape:
            table_box = layout.get("table")
            if not table_box:
                raise ValueError(f"layout {trial_id} needs a table box")
            checked_table_box = {k: float(table_box[k]) for k in ("x", "y", "w", "h")}
            if any(not math.isfinite(v) for v in checked_table_box.values()) or checked_table_box["w"] <= 0 or checked_table_box["h"] <= 0 or checked_table_box["x"] < 0 or checked_table_box["y"] < 0 or checked_table_box["x"] + checked_table_box["w"] > 1280 or checked_table_box["y"] + checked_table_box["h"] > 720:
                raise ValueError(f"table box is outside the slide for {trial_id}")
            rows = []
            cell_bindings = [(i, b) for i, b in enumerate(graph.get("block_bindings", [])) if b.get("kind") == "table_cell"]
            cell_region_by_block = {}
            for region_id, region in table_regions.items():
                for fragment_id in region.get("label_fragment_ids", []) + region.get("body_fragment_ids", []):
                    cell_region_by_block[fragments[fragment_id]["block_index"]] = region_id
            if len(table_region_ids) != len(cell_bindings) or len(table_region_ids) != table_shape["row_count"] * table_shape["column_count"]:
                raise ValueError(f"table cell graph/layout mismatch on page {number}")
            by_cell = {}
            for block_index, binding in cell_bindings:
                region_id = cell_region_by_block.get(block_index)
                if region_id is None:
                    raise ValueError(f"table cell block has no graph region on page {number}: {block_index}")
                by_cell[(binding["row"], binding["column"])] = region_id
            source_table = locked["lock"]["model"].get("tables", [])
            if len(source_table) != 1 or len(source_table[0]["rows"]) != table_shape["row_count"]:
                raise ValueError(f"locked native table shape mismatch on page {number}")
            table = copy.deepcopy(source_table[0])
            provenance = []
            for ri, row in enumerate(table["rows"]):
                for ci, cell in enumerate(row["cells"]):
                    rid = by_cell[(ri, ci)]; _, ids = _region_text(table_regions[rid], fragments)
                    # Keep source paragraph boundaries inside table cells so an
                    # English heading cannot fuse with its following sentence.
                    value=''.join(fragments[i]['quote'] for i in ids)
                    # Replace only text runs. Native table geometry and typography are resized below.
                    if cell.get("paras") and cell["paras"][0]:
                        source_run = copy.deepcopy(cell["paras"][0][0])
                        source_run["text"] = value
                        cell["paras"] = [[{**source_run,'text':line}] for line in value.split('\n')]
                    else:
                        cell["paras"] = [[_style(value, 15, False, "151B24")[0]]]
                    provenance.append({"region_id": rid, "fragment_ids": ids, "rendered_text": value, "kind": "native_table_cell", "row":ri,"column":ci})
            _apply_native_table_layout(table, {**table_box,**checked_table_box}, table_shape, by_cell)
            model["tables"].append(table)
            trace[str(number)] = provenance
        else:
            trace[str(number)] = []
        typography_text = {r['id']: _region_text(r, fragments, alias_fragment_ids)[0] for r in graph['regions']}
        punctuation_moves = []
        for transfer in layout.get('punctuation_transfers', []):
            source, target = transfer['from_region'], transfer['to_region']
            mark = transfer['punctuation']
            if mark not in ('，','、','；','。') or not typography_text[source].startswith(mark):
                raise ValueError('Only an existing source boundary punctuation may be moved')
            source_region = next(r for r in graph['regions'] if r['id'] == source)
            target_region = next(r for r in graph['regions'] if r['id'] == target)
            _, source_ids = _region_text(source_region, fragments, alias_fragment_ids)
            _, target_ids = _region_text(target_region, fragments, alias_fragment_ids)
            a, z = fragments[target_ids[-1]], fragments[source_ids[0]]
            if not ((a['block_index'] == z['block_index'] and a['end'] == z['start']) or (a['block_index'] + 1 == z['block_index'] and z['start'] == 0)):
                raise ValueError('Punctuation transfer must preserve adjacent source reading order')
            before = typography_text[target] + typography_text[source]
            typography_text[target] += mark
            typography_text[source] = typography_text[source][1:]
            assert before == typography_text[target] + typography_text[source]
            punctuation_moves.append(transfer)
        for region in graph["regions"]:
            rid = region["id"]
            if rid in table_regions: continue
            text, ids = _region_text(region, fragments, alias_fragment_ids)
            if not text: continue
            box = layout.get("regions", {}).get(rid)
            if box is None:
                raise ValueError(f"layout {trial_id} missing graph region {rid}")
            model["texts"].append(_new_text(typography_text[rid], rid, layout, role="title" if "title" in rid else "", default_size=26 if "title" in rid else 18, bold="title" in rid))
            trace[str(number)].append({"region_id":rid,"fragment_ids":ids,"rendered_text":typography_text[rid],"source_region_text":text,"punctuation_transfers":punctuation_moves,"kind":"native_text"})
        relations = {r["id"]: r for r in graph["relations"]}
        # A visual emphasis repeats an exact in-order excerpt while its complete
        # source-bound region remains on the page. It cannot author new values.
        for callout in layout.get('source_callouts', []):
            source_id=callout['source_region']
            excerpt=_source_callout_excerpt(callout,typography_text)
            callout_id=callout['id']
            model['texts'].append(_new_text(excerpt,callout_id,{'regions':{callout_id:callout}},role='visual_emphasis'))
            trace[str(number)].append({'region_id':callout_id,'source_region_id':source_id,'rendered_text':excerpt,'kind':'source_bound_visual_emphasis','full_context_retained':True})
        for scope in layout.get('scopes',[]):
            relation=relations.get(scope.get('relation_id'))
            members=set(scope.get('region_ids',[]))
            if not relation or members!=set(relation['from']+relation['to']):raise ValueError('Scope enclosure must exactly match its source-bound relation endpoints')
            box=_box('scope',{'regions':{'scope':scope}})
            for member in members:
                child=_box(member,layout)
                if child['x']<box['x'] or child['y']<box['y'] or child['x']+child['w']>box['x']+box['w'] or child['y']+child['h']>box['y']+box['h']:raise ValueError('Scope enclosure must contain all and only governed nodes')
            for other in set(layout['regions'])-members:
                child=_box(other,layout);cx=child['x']+child['w']/2;cy=child['y']+child['h']/2
                if box['x']<cx<box['x']+box['w'] and box['y']<cy<box['y']+box['h']:raise ValueError('Scope enclosure includes an unrelated source node')
            model['shapes'].append({**box,'radius':8,'fill':None,'line':{'w':2,'color':_color_value(scope.get('color','78917E'),'scope color')},'group':scope.get('id','scope'),'accents':[]})
        for connector in layout.get("connectors", []):
            rid = connector.get("relation_id")
            if rid not in relations:
                raise ValueError(f"connector references unsupported graph relation {rid}")
            if not relations[rid].get("source_mappings"):
                raise ValueError(f"connector relation lacks source trace: {rid}")
            points, arrow = _connector_geometry(connector, relations[rid], graph, layout, table_shape)
            width = connector.get("width", 2)
            if not isinstance(width, (int, float)) or isinstance(width, bool) or not math.isfinite(width) or width <= 0:
                raise ValueError(f"connector width is invalid: {rid}")
            model["lines"].append({"points":points,"color":connector.get("color","355E78"),"w":float(width),"arrow":arrow,"support":rid,"group":""})
        renderable_regions = {r["id"] for r in graph["regions"] if r["id"] not in table_regions and
                              any(i not in alias_fragment_ids for i in r.get("label_fragment_ids", []) + r.get("body_fragment_ids", []))}
        if set(layout.get("regions", {})) != renderable_regions:
            raise ValueError(f"layout {trial_id} region ids must exactly match non-table graph regions")
        trace[str(number)].append({"kind":"nonrendering_alias","block_indices":sorted(aliases),"reason":"validated whitespace-only duplicate; omitted from native text"})
        raw_notes=locked["lock"]["notes"]
        native_notes=raw_notes.replace('\x01','')
        trace[str(number)].append({'kind':'notes_normalization','removed_control':'U+0001 only',
            'raw_sha256':hashlib.sha256(raw_notes.encode()).hexdigest(),
            'native_sha256':hashlib.sha256(native_notes.encode()).hexdigest(),
            'count':raw_notes.count('\x01')})
        generation["pages"].append({"id":locked["id"],"number":number,"lock":{"notes":native_notes,"design":locked["lock"]["design"]},
              "layout":{"model":model,"components":read_json(paths["components_path"]),"preserve_vector_order":bool(layout.get('preserve_vector_order',False))},"assets":{"vector":{"path":str(paths["svg_path"].resolve())}}})
    return generation, trace, selected


def run(manifest_path: Path, out: Path):
    generation, trace, selected = build_generation(manifest_path)
    # Import only after validation so missing inputs never leave partial exports.
    from factdeck.visual_render import render
    render(generation, out, lambda p: Path(p))
    (out / "source_trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    _, _, source_sha, graph_sha_by_page = _validated_graph_files()
    semantic_binding = []
    for trial_id, number, graph, locked, paths, layout, review_path, design_path in selected:
        semantic_binding.append({"trial_id":trial_id,"page_number":number,"page_id":locked["id"],
            "source_sha256":source_sha,"graph_sha256":graph_sha_by_page[number],
            "design_png_sha256":hashlib.sha256(design_path.read_bytes()).hexdigest(),
            "vector_svg_sha256":hashlib.sha256(paths["svg_path"].read_bytes()).hexdigest(),
            "review_path":str(review_path.resolve()),"native_content_bindings":trace[str(number)],
            "relations":[{"id":r["id"],"type":r["type"],"from":r["from"],"to":r["to"],"source_mappings":r["source_mappings"]} for r in graph["relations"]]})
    (out / "native_semantic_binding.json").write_text(json.dumps({"schema_version":"visual-lab-native-semantic-binding.v1","font":generation["font"],"pages":semantic_binding,"approval":"NOT_GRANTED"},ensure_ascii=False,indent=2),encoding="utf-8")
    (out / "adapter_manifest.json").write_text(json.dumps({"selected_trial_ids":[x[0] for x in selected],"page_numbers":[x[1] for x in selected],"font":generation["font"],"native_text":True,"native_tables":True,"connectors_from_graph_relations_only":True},ensure_ascii=False,indent=2),encoding="utf-8")
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "build"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--manifest", type=Path, required=True)
        if name == "build": cmd.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            manifest, selected = _manifest(args.manifest)
            print(json.dumps({"valid":True,"selected_trial_ids":[x[0] for x in selected],"page_numbers":[x[1] for x in selected]},ensure_ascii=False))
        else:
            out = run(args.manifest, args.out)
            print(f"Native rendering completed: {out}")
    except Exception as exc:
        print(f"visual_lab_native: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
