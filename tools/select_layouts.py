#!/usr/bin/env python3
"""Run the layout selector on a slide-level content plan → selection.json + Chinese report (+ optional PNGs).

Usage:
  .venv/bin/python tools/select_layouts.py [--plan factdeck/examples/copd_layout_sample/plan.json]
         [--out /workspace/sync/layout-selector] [--render] [--llm]

Default mode is deterministic (no API key needed).  --llm enables the optional tie-breaker that uses
the repo's OpenAI-compatible endpoint config (EASYPPT_SEMANTIC_MODEL_*); it is only consulted when
qualified candidates' scores are close, and its answer must be one of those candidates.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factdeck import template_lib as tl  # noqa: E402
from factdeck.template_lib import selector as S  # noqa: E402

DEMO = "示例数据，教学示意，非诊疗建议"
THEME = "gold_clinical"
V1_THEME = "premium_clinical"
V1_FAMILIES = {"cover", "section", "key_points", "comparison", "flow", "timeline"}


def text_only(pages: list[dict]) -> list[dict]:
    """Ablation: same pages without structured data (what text signals alone detect)."""
    return [dict(p, data={}) for p in pages]


def agreement(pages, result):
    rows = []
    for p, d in zip(pages, result["decisions"]):
        if p.get("origin_layout") and d["kind"] not in S.EXEMPT_KINDS:
            rows.append((p["id"], p["origin_layout"], d["chosen"]["layout"]))
    same = sum(a == b for _, a, b in rows)
    return {"compared": len(rows), "same": same, "diff": [r for r in rows if r[1] != r[2]]}


def relation_of(layout: str) -> str:
    return next((r for r, (_, lay) in S.RELATIONS.items() if lay == layout), "")


def ablation(pages):
    out = []
    for p in pages:
        if p.get("kind") in S.EXEMPT_KINDS or not p.get("origin_layout"):
            continue
        rels = S.classify(dict(p, data={}))
        want = relation_of(p["origin_layout"].replace("/line", "/bar"))
        out.append({"page_id": p["id"], "expected_relation": want, "text_top": rels[0].relation,
                    "text_top_score": rels[0].score, "hit": rels[0].relation == want,
                    "expected_rank": [r.relation for r in rels].index(want) + 1 if want else None})
    return out


def with_demo_label(layout: str, fill: dict) -> dict:
    f = copy.deepcopy(fill)
    fam = S.LAYOUTS[layout][0]
    if fam == "cover":
        f["meta"] = f"{DEMO}  |  2026.10"
    elif fam == "section":
        pass
    elif fam in ("algorithm_tree", "assessment_matrix", "dual_path_tree"):
        src = f.get("source") or ""
        f["source"] = src.replace("教学示意，非诊疗建议", DEMO) if "教学示意，非诊疗建议" in src else (src + " · " + DEMO).strip(" ·")
    elif fam in ("key_points", "comparison", "flow", "timeline") and S.LAYOUTS[layout][1] != "evidence_takeaways":
        f["source"] = DEMO
    else:
        f["data_note"] = DEMO
    return f


def render(plan_pages, result, out: Path, prefix: str = "p") -> list[dict]:
    from playwright.sync_api import sync_playwright

    from tools.render_pharma_previews import MEASURE_JS

    shots = []
    jobs = []
    for p, d in zip(plan_pages, result["decisions"]):
        lay = d["chosen"]["layout"]
        fill = (p.get("fills") or {}).get(lay)
        stem = f"{prefix}{d['page_no']:02d}-{lay.replace('/', '-')}"
        if fill is None:
            shots.append({"page_no": d["page_no"], "layout": lay, "png": None, "note": "该页没有此版式的填充，未渲染"})
            continue
        fam, var = S.LAYOUTS[lay][0], S.LAYOUTS[lay][1]
        f = with_demo_label(lay, fill)
        f["page"] = f"{d['page_no']:02d}" if "page" in f or fam not in ("cover", "section") else f.get("page")
        rep = tl.validate_fill(fam, f, variant=var)
        if not rep["ok"]:
            shots.append({"page_no": d["page_no"], "layout": lay, "png": None, "note": "填充校验失败：" + "；".join(rep["errors"])})
            continue
        theme = V1_THEME if fam in V1_FAMILIES and var != "evidence_takeaways" else THEME
        html = tl.render_deck_html([{"family": fam, "fill": f, "variant": var, "theme": theme}], theme=theme)
        hp = out / "pages" / f"{stem}.html"
        hp.parent.mkdir(parents=True, exist_ok=True)
        hp.write_text(html, encoding="utf-8")
        jobs.append((d, stem, hp))
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=2)
        for d, stem, hp in jobs:
            page.goto(hp.as_uri())
            page.wait_for_timeout(120)
            issues = page.evaluate(MEASURE_JS) if d["chosen"]["family"] not in V1_FAMILIES else []
            png = out / "pages" / f"{stem}.png"
            page.locator(".slide").first.screenshot(path=str(png))
            shots.append({"page_no": d["page_no"], "layout": d["chosen"]["layout"], "png": str(png),
                          "qa_issues": len(issues)})
        browser.close()
    return sorted(shots, key=lambda s: s["page_no"])


def contact_sheet(shots, decisions, out: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    items = [s for s in shots if s.get("png")]
    cols, tw, th, pad, lab = 4, 640, 360, 20, 34
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * pad, rows * (th + lab + pad) + pad + 56), "#E4E8ED")
    dr = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 20)
    big = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 24)
    dr.text((pad, 14), f"FactPPTv2 版式选择器 · COPD 教学样例 · {len(items)} 页 · {DEMO}", fill="#0B3A5C", font=big)
    by_no = {d["page_no"]: d for d in decisions}
    for i, s in enumerate(items):
        r, c = divmod(i, cols)
        x, y = pad + c * (tw + pad), 56 + pad + r * (th + lab + pad)
        d = by_no[s["page_no"]]
        dr.text((x, y), f"p{s['page_no']:02d} · {d['chosen']['name_zh']} · {d['relation_zh']}", fill="#333333", font=font)
        im = Image.open(s["png"]).convert("RGB").resize((tw, th), Image.LANCZOS)
        sheet.paste(im, (x, y + lab))
        dr.rectangle([x - 1, y + lab - 1, x + tw, y + lab + th], outline="#9A9A9A")
    p = out / "contact-sheet.png"
    sheet.save(p, optimize=True)
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=str(ROOT / "factdeck/examples/copd_layout_sample/plan.json"))
    ap.add_argument("--out", default="/workspace/sync/layout-selector")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--llm", action="store_true", help="optional LLM tie-break (needs EASYPPT_SEMANTIC_MODEL_*)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))

    tb, mode = None, "deterministic"
    if args.llm:
        tb = S.env_llm_tiebreaker()
        mode = "llm" if tb else "deterministic（--llm 已请求，但未配置模型端点）"

    extra = plan.get("layout_signals")
    deck = S.select_deck(plan["pages"], tiebreaker=tb, extra_signals=extra)
    stress = S.select_deck(plan.get("stress_pages") or [], tiebreaker=tb, extra_signals=extra)
    abl = ablation(plan["pages"])
    agr = agreement(plan["pages"], deck)
    shots = render(plan["pages"], deck, out) if args.render else []
    stress_shots = render(plan.get("stress_pages") or [], stress, out, prefix="x") if args.render else []
    if shots:
        contact_sheet(shots, deck["decisions"], out)
    for s in shots + stress_shots:
        if s.get("png"):
            s["png"] = str(Path(s["png"]).relative_to(out))

    def strip(pages):
        return [{k: v for k, v in p.items() if k != "fills"} for p in pages]

    payload = {"mode": mode, "plan": str(Path(args.plan).relative_to(ROOT)) if Path(args.plan).is_relative_to(ROOT) else args.plan,
               "note": DEMO, "deck": deck, "stress": stress, "origin_agreement": agr,
               "text_only_ablation": abl, "renders": shots, "stress_renders": stress_shots, "pages_input": strip(plan["pages"]),
               "stress_input": strip(plan.get("stress_pages") or [])}
    (out / "selection.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "selection-report.md").write_text(report(plan, payload), encoding="utf-8")
    print(json.dumps(deck["stats"], ensure_ascii=False))
    print("agreement", agr["same"], "/", agr["compared"], "diff", agr["diff"])
    print("text-only hits", sum(a["hit"] for a in abl), "/", len(abl))
    for s in shots:
        print("render", s)
    return 0


def report(plan, payload) -> str:
    deck, stress = payload["deck"], payload["stress"]
    main_lines = S.report_markdown(deck, title="COPD 样例 · 版式选择报告").rstrip().split("\n")
    md = [main_lines[0], "\n".join([
        "",
        f"- 输入：`{payload['plan']}`（由 `tools/copd_layout_plan.py` 从仓库现有 COPD 教学样例拆页生成；"
        "选择器只读取标题、文字与结构化数据，不读取原版式）",
        f"- 运行模式：{payload['mode']}（无需 API key）",
        f"- {DEMO}。药企图表页的数字全部为 `pharma_fixtures.py` 中的虚构示例，研究名为“示例研究 A-1…”，未与任何真实试验名搭配。",
        "- 分数 = 文本信号权重 + 结构化数据信号权重；降级分数 ×0.8；“不合格”= 识别到该关系但最低数据不满足。",
        "- “图表页”= 决策算法树 / 评估矩阵 / 双路径树 / 试验设计 / 森林图 / 终点读出 / 机制级联 / 高亮数据表 / 研究格局泳道；"
        "要点、对照、流程、时间轴算文字型页。",
        ""])] + main_lines[1:] + [""]
    agr = payload["origin_agreement"]
    md += ["## 与样例原版式的对照（评估用）", "",
           f"- 内容页 {agr['compared']} 页中 {agr['same']} 页与样例作者原定版式一致。",
           *[f"- `{pid}`：原版式 `{a}` → 选择 `{b}`" for pid, a, b in agr["diff"]], ""]
    abl = payload["text_only_ablation"]
    md += ["## 仅凭文字（去掉结构化数据）的关系识别", "",
           f"命中 {sum(a['hit'] for a in abl)} / {len(abl)}。用来检验文本信号本身是否可靠；去掉数据后图表版式会因最低数据不足而降级，所以这里只比关系。", "",
           "| 页 | 期望关系 | 文字识别首位 | 期望关系排名 |", "|---|---|---|---|"]
    for a in abl:
        md.append(f"| {a['page_id']} | {S.RELATIONS[a['expected_relation']][0]} | "
                  f"{S.RELATIONS[a['text_top']][0]} {a['text_top_score']} | {a['expected_rank']} {'✓' if a['hit'] else '✗'} |")
    md += ["", "## 降级演示（构造页）", "",
           "以下 3 页是从同一样例中**截掉部分数据**构造的（不新增任何数字），用来演示“数据不足 → 沿降级链换版式、绝不补数”。", ""]
    for p in plan.get("stress_pages") or []:
        md.append(f"- `{p['id']}`：{p['provenance']}")
    md += ["", S.report_markdown(stress, title="降级演示结果").replace("# 降级演示结果", "### 降级演示结果").rstrip(), ""]
    if payload["renders"]:
        md += ["## 渲染", "", "每页按最终版式用样例内容填充渲染（`pages/*.png`），总览见 `contact-sheet.png`。", ""]
        for s in payload["renders"]:
            md.append(f"- p{s['page_no']:02d} `{s['layout']}`：" + (s["png"] if s.get("png") else s.get("note", "")))
        for s in payload.get("stress_renders") or []:
            md.append(f"- 降级演示 x{s['page_no']:02d} `{s['layout']}`：" + (s["png"] if s.get("png") else s.get("note", "")))
        md.append("")
    return "\n".join(md)


if __name__ == "__main__":
    raise SystemExit(main())
