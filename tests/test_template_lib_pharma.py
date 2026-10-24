"""Pharma chart-led families (v1.3.1): slot/data contract, SVG geometry, honesty footer.

All fixtures are illustrative demo data (示例数据) — see factdeck/template_lib/pharma_fixtures.py.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest

from factdeck import template_lib as tl
from factdeck.template_lib import pharma
from factdeck.template_lib import pharma_fixtures as fx

LIB = Path(__file__).resolve().parents[1] / "factdeck" / "template_lib"
THEME = "gold_clinical"

CASES = [(family, variant, fill) for _stem, family, variant, fill in fx.PAGES]


def _render(family, fill, variant=None):
    return tl.render_page_html(family, fill, theme=THEME, variant=variant)


def test_manifest_declares_pharma_families_and_evidence_variant():
    m = tl.load_manifest()
    assert set(pharma.FAMILIES) <= set(m["families"])
    for fam in pharma.FAMILIES:
        spec = m["families"][fam]
        assert spec["pattern"].startswith("PHARMA-"), fam
        assert (LIB / "html" / spec["html"]).is_file()
        assert "takeaway_rail" in spec["zones_in"] and "footer" in spec["zones_in"]
    kp = m["families"]["key_points"]
    assert "evidence_takeaways" in kp["variants"] and kp["capacity"]["evidence_takeaways"] == 4
    # existing variants untouched
    assert kp["variants"][:3] == ["cards_3", "cards_4", "cards_6"]


@pytest.mark.parametrize("family,variant,fill", CASES)
def test_fixture_validates_and_renders_chrome(family, variant, fill):
    r = tl.validate_fill(family, fill, variant=variant)
    assert r["ok"], r["errors"]
    html = _render(family, fill, variant)
    assert f'data-family="{family}"' in html
    assert 'data-batch="pharma"' in html
    assert 'data-slot="title"' in html and fill["title"] in html
    assert 'data-slot="figure"' in html and fill["figure"] in html
    # honesty + structural source footer on every page
    assert pharma.DEMO_NOTE in html and pharma.STRUCT_NOTE in html
    assert 'data-slot="abbrev"' in html
    # charts are drawn, never embedded images
    assert "<img" not in html and "background-image" not in html


@pytest.mark.parametrize("family,variant,fill", CASES)
def test_takeaways_or_items_are_number_led(family, variant, fill):
    items = fill.get("takeaways") or fill.get("items")
    assert 3 <= len(items) <= 4
    assert all(re.search(r"\d", it["value"]) for it in items)


def test_footer_defaults_honesty_note_when_omitted():
    fill = copy.deepcopy(fx.FOREST)
    fill.pop("data_note"), fill.pop("source")
    html = _render("forest_plot", fill)
    assert pharma.DEMO_NOTE in html and pharma.STRUCT_NOTE in html


def test_pharma_templates_use_one_accent_plus_greys_and_no_web_cards():
    css = (LIB / "html" / "_pharma.css.j2").read_text(encoding="utf-8")
    for name in ("trial_design", "forest_plot", "endpoint_readout", "moa_cascade",
                 "data_table_highlight", "landscape_swimlane", "evidence_takeaways"):
        css += (LIB / "html" / f"{name}.html.j2").read_text(encoding="utf-8")
    for hx in re.findall(r"#([0-9A-Fa-f]{6})\b", css):
        r, g, b = hx[0:2], hx[2:4], hx[4:6]
        assert r.upper() == g.upper() == b.upper(), f"non-grey literal colour #{hx}"
    assert "box-shadow" not in css and "border-radius" not in css
    assert "gradient" not in css


def test_non_rendered_accent_is_theme_gold():
    t = tl.get_theme(THEME)
    html = tl.render_deck_html([{"family": "forest_plot", "fill": fx.FOREST}], theme=THEME)
    assert f"--accent:{t['accent']}" in html  # accent arrives only via :root theme tokens
    assert html.count('data-highlight="true"') == 1


# --- trial design ------------------------------------------------------------

def test_trial_design_geometry_and_arms():
    page = tl.normalize_fill("trial_design", fx.TRIAL, theme=THEME)
    g = page["geo"]
    xs = [t["x"] for t in g["timepoints"]]
    assert xs == sorted(xs) and len(xs) == 4
    assert len(g["arms"]) == 2 and all(a["w"] > 300 for a in g["arms"])
    assert g["endpoint_x"] == pytest.approx(xs[2])  # treatment ends at week 52
    html = _render("trial_design", fx.TRIAL)
    assert 'data-shape="trial-schematic"' in html and "R 1:1" in html and "N = 900" in html
    assert html.count('data-shape="arm"') == 2 and "n = 450" in html
    assert 'data-slot="inclusion"' in html and 'data-slot="endpoints"' in html


def test_trial_design_rejects_too_few_timepoints():
    bad = copy.deepcopy(fx.TRIAL)
    bad["timepoints"] = bad["timepoints"][:2]
    r = tl.validate_fill("trial_design", bad)
    assert not r["ok"] and any("timepoints" in e for e in r["errors"])


# --- forest plot -------------------------------------------------------------

def test_forest_log_axis_geometry():
    page = tl.normalize_fill("forest_plot", fx.FOREST, theme=THEME)
    g = page["geo"]
    ticks = {t["v"]: t["x"] for t in g["ticks"]}
    # log axis: equal spacing per doubling
    assert ticks[0.5] - ticks[0.25] == pytest.approx(ticks[1.0] - ticks[0.5], abs=0.2)
    assert g["x_ref"] == pytest.approx(ticks[1.0])
    for r in g["rows"]:
        if r["kind"] != "group":
            assert r["xl"] <= r["xe"] <= r["xh"]
    hl = [r for r in g["rows"] if r["highlight"]]
    assert len(hl) == 1 and hl[0]["label"] == "≥ 300" and hl[0]["xh"] < g["x_ref"]
    html = _render("forest_plot", fx.FOREST)
    assert 'data-axis="log"' in html and 'data-shape="ref-line-1"' in html
    assert 'data-shape="overall-diamond"' in html
    assert "倾向研究药 X" in html and "倾向安慰剂" in html
    assert "0.45–0.75" in html


@pytest.mark.parametrize("mutate,needle", [
    (lambda f: f["rows"][2].update(lo=1.5), "lo ≤ est ≤ hi"),
    (lambda f: f["rows"][3].update(highlight=True), "最多高亮 1 行"),
    (lambda f: f.update(axis={"min": 1.2, "max": 3}), "对数轴"),
])
def test_forest_rejects_bad_data(mutate, needle):
    bad = copy.deepcopy(fx.FOREST)
    mutate(bad)
    r = tl.validate_fill("forest_plot", bad)
    assert not r["ok"] and any(needle in e for e in r["errors"]), r["errors"]


# --- endpoint readout --------------------------------------------------------

def test_endpoint_bar_from_payload():
    page = tl.normalize_fill("endpoint_readout", fx.ENDPOINT_BAR, variant="bar", theme=THEME)
    g = page["geo"]
    assert g["kind"] == "bar" and len(g["groups"]) == 2
    b_ctl, b_act = g["groups"][0]["bars"]
    assert b_ctl["h"] > b_act["h"]  # 1.10 vs 0.77 → taller placebo bar
    assert b_ctl["h"] / b_act["h"] == pytest.approx(1.10 / 0.77, rel=0.01)
    assert b_ctl["yhi"] < b_ctl["y"] < b_ctl["ylo"]
    html = _render("endpoint_readout", fx.ENDPOINT_BAR, "bar")
    assert 'data-chart-kind="bar"' in html and html.count('data-shape="error-bar"') == 4
    assert 'data-shape="stats-box"' in html and "P &lt; 0.001" in html
    assert 'data-shape="comparison-bracket"' in html


def test_endpoint_line_variant_with_n_at_risk():
    page = tl.normalize_fill("endpoint_readout", fx.ENDPOINT_LINE, variant="line", theme=THEME)
    g = page["geo"]
    assert g["kind"] == "line" and len(g["series"]) == 2 and len(g["n_rows"]) == 2
    assert [t["x"] for t in g["xticks"]] == sorted(t["x"] for t in g["xticks"])
    html = _render("endpoint_readout", fx.ENDPOINT_LINE, "line")
    assert 'data-chart-kind="line"' in html and 'data-shape="n-at-risk"' in html
    assert html.count('data-shape="ci-whisker"') == 12


def test_endpoint_rejects_length_mismatch_and_missing_stats():
    bad = copy.deepcopy(fx.ENDPOINT_BAR)
    bad["series"][0]["values"] = [1.1]
    bad["stats"] = {}
    r = tl.validate_fill("endpoint_readout", bad, variant="bar")
    assert not r["ok"]
    assert any("长度" in e for e in r["errors"]) and any("stats" in e for e in r["errors"])


def test_endpoint_unknown_variant_refused():
    r = tl.validate_fill("endpoint_readout", fx.ENDPOINT_BAR, variant="pie")
    assert not r["ok"]


# --- MoA cascade -------------------------------------------------------------

def test_moa_callouts_connect_to_targets_without_crossing_lanes():
    page = tl.normalize_fill("moa_cascade", fx.MOA, theme=THEME)
    g = page["geo"]
    assert len(g["cols"]) == 5 and len(g["callouts"]) == 4
    targets = [it for c in g["cols"] for it in c["items"] if it["target"]]
    assert {t["label"] for t in targets} == {"TSLP", "IL-33", "IL-4 / IL-13", "IL-5"}
    html = _render("moa_cascade", fx.MOA)
    assert html.count('data-shape="inhibition-connector"') == 4
    assert html.count('data-shape="t-bar"') == 4
    assert html.count('data-shape="stage"') == 5
    assert "<img" not in html


def test_moa_rejects_unknown_target():
    bad = copy.deepcopy(fx.MOA)
    bad["callouts"][0]["target"] = "nope"
    r = tl.validate_fill("moa_cascade", bad)
    assert not r["ok"] and any("target" in e for e in r["errors"])


# --- data table --------------------------------------------------------------

def test_data_table_dense_one_highlight():
    html = _render("data_table_highlight", fx.TABLE)
    assert 'data-shape="data-table"' in html
    assert html.count("<tr") >= 13
    assert html.count('data-highlight="true"') == 1
    assert "N = 900" in html and 'data-slot="footnotes"' in html


@pytest.mark.parametrize("mutate,needle", [
    (lambda f: f.update(rows=f["rows"][:8]), "12–18"),
    (lambda f: f["rows"][2].update(highlight=True), "仅须高亮 1 行"),
    (lambda f: f["rows"][1].update(cells=["1", "2"]), "单元格数"),
])
def test_data_table_rejects(mutate, needle):
    bad = copy.deepcopy(fx.TABLE)
    mutate(bad)
    r = tl.validate_fill("data_table_highlight", bad)
    assert not r["ok"] and any(needle in e for e in r["errors"]), r["errors"]


# --- swimlane ----------------------------------------------------------------

def test_swimlane_bars_on_year_axis_with_status_markers():
    page = tl.normalize_fill("landscape_swimlane", fx.SWIM, theme=THEME)
    g = page["geo"]
    assert len(g["lanes"]) == 5 and g["years"][0]["y"] == 2019
    for ln in g["lanes"]:
        for b in ln["bars"]:
            assert g["tx0"] <= b["x"] < b["xe"] <= g["tx1"]
    html = _render("landscape_swimlane", fx.SWIM)
    for st in ("met", "not_met", "ongoing"):
        assert f'data-status="{st}"' in html
    assert 'data-shape="today-line"' in html and 'data-shape="legend"' in html
    assert html.count('data-shape="study-bar"') == 10


def test_swimlane_rejects_bad_status_and_range():
    bad = copy.deepcopy(fx.SWIM)
    bad["lanes"][0]["studies"][0]["status"] = "great"
    bad["lanes"][1]["studies"][0]["end"] = 2035
    r = tl.validate_fill("landscape_swimlane", bad)
    assert not r["ok"]
    assert any("status" in e for e in r["errors"]) and any("轴范围" in e for e in r["errors"])


# --- evidence takeaways (key_points variant) ---------------------------------

def test_evidence_takeaways_superscripts_point_to_footer_refs():
    r = tl.validate_fill("key_points", fx.EVIDENCE, variant="evidence_takeaways")
    assert r["ok"], r["errors"]
    html = _render("key_points", fx.EVIDENCE, "evidence_takeaways")
    assert 'data-pattern="PHARMA-evidence-takeaways"' in html
    assert "pillar" not in html  # not the card layout
    used = set()
    for m in re.finditer(r'data-evidence="([^"]+)"', html):
        used |= set(m.group(1).split(","))
    defined = set(re.findall(r'data-ref="([^"]+)"', html))
    assert used and used <= defined
    assert html.count('data-shape="verbatim-quote"') == 4 and "p. 26" in html


def test_evidence_takeaways_rejects_missing_or_unknown_refs():
    bad = copy.deepcopy(fx.EVIDENCE)
    bad["items"][0]["refs"] = []
    bad["items"][1]["refs"] = ["9"]
    bad["items"][2]["value"] = "显著"
    r = tl.validate_fill("key_points", bad, variant="evidence_takeaways")
    assert not r["ok"]
    joined = "；".join(r["errors"])
    assert "必须带证据号" in joined and "未在 refs 中定义" in joined and "数字" in joined


def test_key_points_cards_unchanged_by_evidence_variant():
    # auto-variant still picks card variants for legacy fills
    fill = {"title": "三点", "items": [{"heading": "a"}, {"heading": "b"}, {"heading": "c"}]}
    assert tl.validate_fill("key_points", fill)["variant"] == "cards_3"


def test_takeaway_rail_refuses_over_capacity_and_non_numeric():
    bad = copy.deepcopy(fx.FOREST)
    bad["takeaways"] = bad["takeaways"] + [{"value": "5", "text": "x"}]
    assert not tl.validate_fill("forest_plot", bad)["ok"]
    bad = copy.deepcopy(fx.FOREST)
    bad["takeaways"][0]["value"] = "很好"
    r = tl.validate_fill("forest_plot", bad)
    assert not r["ok"] and any("number-led" in e for e in r["errors"])


def test_pharma_deck_renders_all_pages():
    pages = [{"family": f, "fill": fill, "variant": v} for f, v, fill in CASES]
    html = tl.render_deck_html(pages, theme=THEME)
    assert html.count('data-batch="pharma"') == len(CASES)
    assert html.count('data-shape="gold-accent"') == len(CASES)


def test_native_hook_accepts_pharma_geometry():
    env = tl.native_prepare("forest_plot", fx.FOREST, theme=THEME)
    assert env["status"] == "prepared" and env["page"]["geo"]["rows"]
    assert set(pharma.FAMILIES) <= set(tl.native_describe()["accepts_families"])
