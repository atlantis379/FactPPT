"""Native PPTX for template-library pages: editable text boxes, native tables, native shapes for charts,
no pictures / embedded SVG.  Uses the COPD sample plan (demo data) and a headless Chromium (Playwright)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "factdeck" / "examples" / "copd_layout_sample" / "plan.json"
WANT = ("cover", "flow-dx", "cmp-rec", "ph-table", "ph-endpoint", "ph-forest", "ph-moa")


def _chromium_ok() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            pw.chromium.launch().close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _chromium_ok(), reason="playwright chromium not available")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    import os
    from factdeck.template_lib import pipeline
    out = tmp_path_factory.mktemp("native")
    os.environ.setdefault("FACTDECK_JOB_STATS_DB", str(out / "jobs.sqlite"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    plan["pages"] = [p for p in plan["pages"] if p["id"] in WANT]
    rec = pipeline.run(plan, out, previews=False)
    from factdeck.template_lib.native import inspect_pptx
    return out, rec, inspect_pptx(out / "deck.pptx")


def by_id(rec, insp):
    return {e["page_id"]: s for e, s in zip(rec["pages"], insp["slides"])}


def test_every_page_is_native_with_no_pictures(built):
    out, rec, insp = built
    assert [e["status"] for e in rec["pages"]] == ["OK"] * len(WANT)
    assert insp["aspect"] == pytest.approx(16 / 9, abs=1e-3)
    for s in insp["slides"]:
        assert s["pictures"] == 0 and not s["svg_embedded"]
        assert s["text_frames"] + s["table_cells_with_text"] > 0
    assert rec["verify"]["pictures"] == 0 and rec["verify"]["svg_embedded"] is False
    assert not rec["verify"]["qa_issue_pages"]


def test_chart_pages_use_native_shapes(built):
    _, rec, insp = built
    s = by_id(rec, insp)
    for pid in ("ph-endpoint", "ph-forest"):
        k = s[pid]["kinds"]
        assert k.get("autoshape", 0) >= 5 and k.get("connector", 0) >= 5 and k.get("textbox", 0) >= 10, (pid, k)
    assert s["flow-dx"]["kinds"].get("freeform", 0) >= 1          # arrowheads / connectors drawn as shapes


def test_text_is_editable_chinese_in_text_frames(built):
    out, rec, insp = built
    from pptx import Presentation
    prs = Presentation(str(out / "deck.pptx"))
    cover = prs.slides[0]
    texts = [sh.text_frame.text for sh in cover.shapes if sh.has_text_frame and sh.text_frame.text.strip()]
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    title = next(p for p in plan["pages"] if p["id"] == "cover")["fills"]["cover"]["title"]
    assert any(title.replace("\n", "") in t.replace("\n", "").replace("\v", "") for t in texts)
    assert not any(tag in t for s in insp["slides"] for t in s["texts"] for tag in ("<div", "<span", "<br", "&lt;"))


def test_tables_are_native_with_cell_text(built):
    out, rec, insp = built
    s = by_id(rec, insp)
    assert s["ph-table"]["tables"] == 1 and s["ph-table"]["table_cells_with_text"] >= 20
    assert s["cmp-rec"]["tables"] == 1 and s["cmp-rec"]["table_cells_with_text"] >= 8
    from pptx import Presentation
    prs = Presentation(str(out / "deck.pptx"))
    idx = [e["page_id"] for e in rec["pages"]].index("ph-table")
    tbl = next(sh for sh in prs.slides[idx].shapes if sh.has_table).table
    assert len(tbl.rows) >= 5 and len(tbl.columns) >= 3


def test_demo_label_and_decision_notes(built):
    out, rec, insp = built
    from pptx import Presentation
    prs = Presentation(str(out / "deck.pptx"))
    joined = "\n".join(t for s in insp["slides"] for t in s["texts"])
    assert "示例数据" in joined
    notes = prs.slides[1].notes_slide.notes_text_frame.text
    assert "【版式】" in notes
    job = json.loads((out / "job.json").read_text(encoding="utf-8"))
    assert all("layout_decision" in e and e["layout_decision"]["reason_zh"] for e in job["pages"])
    assert (out / "decisions.json").is_file()


def test_job_stats_written_for_the_run(built):
    out, rec, _ = built
    st = json.loads((out / "job_stats.json").read_text(encoding="utf-8"))
    names = [s["stage"] for s in st["stages"]]
    assert names[:6] == ["select", "fill", "render_html", "measure", "native", "verify"]
    assert st["status"] == "OK" and st["total_seconds"] > 0
    assert st["tokens"]["calls"] == 0                               # offline: tie-break off, no model call
