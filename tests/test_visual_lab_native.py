import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import shutil

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "visual_lab_native.py"
sys.path.insert(0, str(_MODULE_PATH.parents[1]))
_SPEC = importlib.util.spec_from_file_location("visual_lab_native", _MODULE_PATH)
adapter = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(adapter)


def test_source_emphasis_cannot_invent_or_normalize_a_threshold():
    retained={'threshold':'支气管扩张后FEV1/FVC< 0.7'}
    assert adapter._source_callout_excerpt({'source_region':'threshold','excerpt':'< 0.7'},retained)=='< 0.7'
    for excerpt in ['< 0.8','≤ 0.7','0.7前后改善','']:
        with pytest.raises(ValueError,match='exact excerpt'):
            adapter._source_callout_excerpt({'source_region':'threshold','excerpt':excerpt},retained)
    with pytest.raises(ValueError):
        adapter._source_callout_excerpt({'source_region':'missing','excerpt':'< 0.7'},retained)


def test_typographic_reflow_preserves_source_characters():
    source='肺力学（如全套肺功能检 查和运动试验）、'
    layout={'regions':{'node':{'x':20,'y':20,'w':350,'h':110}},
            'compact_interhan_spaces':['node'],
            'line_break_before':{'node':['（','和运动']}}
    text=adapter._new_text(source,'node',layout)
    actual=''.join(r['text'] for p in text['paras'] for r in p)
    assert '检查' in actual
    assert ''.join(actual.split()) == ''.join(source.split())
    layout['line_break_before']['node']=['无来源新增词']
    with pytest.raises(ValueError,match='existing source'):
        adapter._new_text(source,'node',layout)


def test_graph_fragments_reconstruct_source_and_alias_is_nonrendering():
    graphs = adapter._structurally_valid_graphs()
    assert set(graphs) == {1, 2, 5, 9, 20, 21}
    page21 = graphs[21]
    alias = page21["render_aliases"][0]
    blocks = {b["block_index"]: b["text"] for b in page21["block_texts"]}
    assert "".join(blocks[alias["block_index"]].split()) == "".join(
        "".join(blocks[i] for i in alias["covered_by_block_indices"]).split()
    )
    alias_ids = {f["id"] for f in page21["text_fragments"] if f["block_index"] == alias["block_index"]}
    locked_sentence = next(r for r in page21["regions"] if r["id"] == "locked_complete_sentence")
    rendered_ids = locked_sentence["label_fragment_ids"] + locked_sentence["body_fragment_ids"]
    assert alias_ids <= set(rendered_ids)  # builder filters these IDs before native text construction
    for graph in graphs.values():
        fragments = {}
        for fragment in graph["text_fragments"]:
            fragments.setdefault(fragment["block_index"], []).append(fragment)
        for block_index, parts in fragments.items():
            assert "".join(p["quote"] for p in sorted(parts, key=lambda p: p["start"])) == next(
                b["text"] for b in graph["block_texts"] if b["block_index"] == block_index
            )


def test_page20_has_native_table_cell_sources_and_graph_relations():
    graph = adapter._structurally_valid_graphs()[20]
    shape = graph["source_table_shape"][0]
    table_bindings = [b for b in graph["block_bindings"] if b["kind"] == "table_cell"]
    assert (shape["row_count"], shape["column_count"]) == (2, 2)
    assert len(table_bindings) == 4
    assert {(b["row"], b["column"]) for b in table_bindings} == {(r, c) for r in range(2) for c in range(2)}
    assert all(r.get("source_mappings") for r in graph["relations"])
    by_block = {}
    fragments = {f["id"]: f for f in graph["text_fragments"]}
    for region in graph["regions"]:
        for fid in region["label_fragment_ids"] + region["body_fragment_ids"]:
            by_block[fragments[fid]["block_index"]] = region["id"]
    for block_index, binding in enumerate(graph["block_bindings"]):
        if binding["kind"] == "table_cell":
            assert by_block[block_index].endswith("_cell")


def test_source_validator_rejects_changed_locked_source_text():
    common = json.loads(adapter.COMMON.read_text(encoding="utf-8"))
    source_page = common["pages"][0]
    graph = next(g for g in adapter._structurally_valid_graphs().values() if g["page"]["number"] == source_page["number"])
    broken = json.loads(json.dumps(graph, ensure_ascii=False))
    broken["block_texts"][0]["text"] += "新增文字"
    with pytest.raises(ValueError, match="Source text changed"):
        from factdeck.visual_lab import validate_graph
        validate_graph([source_page], {"schema_version": "semantic-graph.v1", "pages": [broken]})


def test_connector_direction_arrow_and_region_anchors_are_enforced():
    graph = adapter._structurally_valid_graphs()[21]
    relation = next(r for r in graph["relations"] if r["id"] == "r21_condition")
    layout = {"regions": {"symptom_obstruction_condition": {"x": 100, "y": 200, "w": 200, "h": 80}, "assessment_intro": {"x": 500, "y": 200, "w": 240, "h": 80}}}
    valid = {"from_region":"symptom_obstruction_condition","to_region":"assessment_intro","arrow":True,"points":[[300,240],[500,240]]}
    pts, arrow = adapter._connector_geometry(valid, relation, graph, layout, None)
    assert pts == valid["points"] and arrow is True
    reversed_edge = {**valid,"from_region":"assessment_intro","to_region":"symptom_obstruction_condition","points":[[500,240],[300,240]]}
    with pytest.raises(ValueError, match="disagree with graph direction"):
        adapter._connector_geometry(reversed_edge, relation, graph, layout, None)
    undirected = {**valid,"arrow":False}
    with pytest.raises(ValueError, match="needs a directed arrow"):
        adapter._connector_geometry(undirected, relation, graph, layout, None)
    misplaced = {**valid,"points":[[420,100],[500,240]]}
    with pytest.raises(ValueError, match="not attached"):
        adapter._connector_geometry(misplaced, relation, graph, layout, None)


def test_nondirectional_relation_rejects_arrow():
    graph = adapter._structurally_valid_graphs()[20]
    relation = next(r for r in graph["relations"] if r["id"] == "r20_row_classification")
    layout = {"regions": {}, "table": {"x":64,"y":210,"w":1152,"h":122}}
    connector = {"from_region":relation["from"][0],"to_region":relation["to"][0],"arrow":True,"points":[[100,240],[1100,240]]}
    with pytest.raises(ValueError, match="arrow is not permitted"):
        adapter._connector_geometry(connector, relation, graph, layout, graph["source_table_shape"][0])


def test_manifest_rejects_blocker_review_even_when_files_exist():
  with tempfile.TemporaryDirectory(dir=adapter.LAB) as tmp:
    tmp_path = Path(tmp)
    design = tmp_path / "design.png"
    design.write_bytes(b"actual image bytes")
    review = tmp_path / "review.json"
    review.write_text(json.dumps({"status": "BLOCKERS_PRESENT"}), encoding="utf-8")
    with pytest.raises(ValueError, match="has blockers"):
        adapter._validate_semantic_review(json.loads(review.read_text(encoding="utf-8")), "trial", design, "source", "graph")


def test_clear_review_requires_current_source_graph_and_actual_asset_hashes():
  with tempfile.TemporaryDirectory(dir=adapter.LAB) as tmp:
    design = Path(tmp) / "design.png"
    design.write_bytes(b"real design")
    review = {"status":"PASS","reviewed_asset_sha256":hashlib.sha256(design.read_bytes()).hexdigest(),"source_sha256":"source-current","graph_sha256":"graph-current"}
    adapter._validate_semantic_review(review, "trial", design, "source-current", "graph-current")
    with pytest.raises(ValueError, match="not bound to current common_input"):
        adapter._validate_semantic_review(review, "trial", design, "source-old", "graph-current")
    with pytest.raises(ValueError, match="not bound to its current graph"):
        adapter._validate_semantic_review(review, "trial", design, "source-current", "graph-old")
    review["reviewed_asset_sha256"] = "wrong-image-hash"
    with pytest.raises(ValueError, match="actual design PNG hash"):
        adapter._validate_semantic_review(review, "trial", design, "source-current", "graph-current")


def test_manifest_reports_missing_actual_svg_explicitly():
  with tempfile.TemporaryDirectory(dir=adapter.LAB) as tmp:
    tmp_path = Path(tmp)
    design = tmp_path / "design.png"
    design.write_bytes(b"png")
    review = tmp_path / "review.json"
    review.write_text(json.dumps({"status": "PASS", "reviewed_asset_sha256": hashlib.sha256(design.read_bytes()).hexdigest()}), encoding="utf-8")
    trial = {"page_number": 2, "svg_path": str(tmp_path / "absent.svg"), "components_path": str(tmp_path / "components.json"), "layout_path": str(tmp_path / "layout.json"), "semantic_review_path": str(review), "design_png_path": str(design)}
    (tmp_path / "components.json").write_text("[]", encoding="utf-8")
    (tmp_path / "layout.json").write_text("{}", encoding="utf-8")
    trial_ids = [f"t{i}" for i in range(6)]
    page_numbers = [2, 5, 9, 1, 20, 21]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"selected_trial_ids": trial_ids, "trials": {trial_id: {**trial, "page_number":number} for trial_id, number in zip(trial_ids, page_numbers)}}), encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="missing required actual input: svg_path"):
        adapter._manifest(manifest_path)


def test_manifest_rejects_duplicate_selected_pages_before_asset_loading():
    with tempfile.TemporaryDirectory(dir=adapter.LAB) as tmp:
        tmp_path = Path(tmp)
        trial_ids = [f"t{i}" for i in range(6)]
        numbers = [2, 2, 9, 1, 20, 21]
        trials = {trial_id:{"page_number":number} for trial_id, number in zip(trial_ids, numbers)}
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({"selected_trial_ids":trial_ids,"trials":trials}), encoding="utf-8")
        with pytest.raises(ValueError, match="distinct page numbers"):
            adapter._manifest(manifest_path)


def test_current_graph_review_must_match_frozen_source_and_graph_digest(monkeypatch):
  with tempfile.TemporaryDirectory(dir=adapter.LAB) as tmp:
    temp_lab = Path(tmp)
    for name in ["common_input.json", "semantic_graph.json", "extension_graph.json", "graph_validation.json", "extension_graph_validation.json", "graph_review.json", "extension_graph_review.json"]:
        shutil.copy2(adapter.LAB / name, temp_lab / name)
    common = temp_lab / "common_input.json"
    monkeypatch.setattr(adapter, "COMMON", common)
    monkeypatch.setattr(adapter, "LAB", temp_lab)
    monkeypatch.setattr(adapter, "GRAPH_FILES", (temp_lab / "semantic_graph.json", temp_lab / "extension_graph.json"))
    review_path = temp_lab / "graph_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["source_sha256"] = "stale-source-digest"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    with pytest.raises(ValueError, match="not bound to current common_input"):
        adapter.validate_graphs()


def test_native_table_resize_updates_grid_and_cell_metrics_without_text_change():
    common = json.loads(adapter.COMMON.read_text(encoding="utf-8"))
    source = next(p for p in common["pages"] if p["number"] == 20)
    table = json.loads(json.dumps(source["lock"]["model"]["tables"][0]))
    original_text = [["".join(run["text"] for para in cell["paras"] for run in para) for cell in row["cells"]] for row in table["rows"]]
    shape = adapter._structurally_valid_graphs()[20]["source_table_shape"][0]
    cell_map = {(0,0):"history_header_cell",(0,1):"group_header_cell",(1,0):"exacerbation_history_cell",(1,1):"group_e_cell"}
    adapter._apply_native_table_layout(table, {"x":80,"y":160,"w":900,"h":150,"col_widths":[600,300],"row_heights":[60,90],"font_size":18}, shape, cell_map)
    assert [c["w"] for c in table["rows"][0]["cells"]] == [600,300]
    assert [r["h"] for r in table["rows"]] == [60,90]
    assert sum(c["w"] for c in table["rows"][0]["cells"]) == table["w"]
    assert sum(r["h"] for r in table["rows"]) == table["h"]
    assert [["".join(run["text"] for para in cell["paras"] for run in para) for cell in row["cells"]] for row in table["rows"]] == original_text
    assert all(run["size"] == 18 for row in table["rows"] for cell in row["cells"] for para in cell["paras"] for run in para)
    assert table["rows"][0]["cells"][0]["pad"] != source["lock"]["model"]["tables"][0]["rows"][0]["cells"][0]["pad"]


def test_native_table_proportionally_scales_and_rejects_bad_geometry():
    common = json.loads(adapter.COMMON.read_text(encoding="utf-8"))
    source = next(p for p in common["pages"] if p["number"] == 20)
    table = json.loads(json.dumps(source["lock"]["model"]["tables"][0]))
    shape = adapter._structurally_valid_graphs()[20]["source_table_shape"][0]
    positions = {(0,0):"history_header_cell",(0,1):"group_header_cell",(1,0):"exacerbation_history_cell",(1,1):"group_e_cell"}
    adapter._apply_native_table_layout(table, {"x":0,"y":0,"w":table["w"]*2,"h":table["h"]*2}, shape, positions)
    assert table["rows"][0]["cells"][0]["w"] == pytest.approx(source["lock"]["model"]["tables"][0]["rows"][0]["cells"][0]["w"]*2)
    assert table["rows"][0]["cells"][0]["paras"][0][0]["size"] == pytest.approx(source["lock"]["model"]["tables"][0]["rows"][0]["cells"][0]["paras"][0][0]["size"]*2)
    table = json.loads(json.dumps(source["lock"]["model"]["tables"][0]))
    with pytest.raises(ValueError, match="must sum to table w/h"):
        adapter._apply_native_table_layout(table, {"x":0,"y":0,"w":1000,"h":100,"col_widths":[100,100],"row_heights":[50,50]}, shape, positions)
