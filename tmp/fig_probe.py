"""Composed-figure probe: what a page looks like when the model decides the picture, the emphasis and the room.

Four pages, all from GOLD 2026 sentences:
  p-hero    one number, and the page is allowed to breathe (role: hero)
  p-bars    four multipliers on one scale — the compact bar geometry
  p-pct     two miss-rates on one scale — the roomy bar geometry, each bar with its own unit
  p-mix     a boundary stacked over a pair of bars — the composite geometry (rendering only: the two parts do
            not share an argument, which is exactly the thing code cannot check and the model must)
Plus the refusals, so the checks can be read without a picture.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factdeck import presentation as P
from factdeck.design_audit import DESIGN_JS, audit as design_audit
from factdeck.presentation_render import render_page
from factdeck.template_lib import native as N
from factdeck.template_lib.measure import MEASURE_JS

facts = {f["id"]: f for f in json.loads((ROOT / "output/gold2026_deck/facts_verified.json")
                                        .read_text(encoding="utf-8"))["facts"]}

RISK = [{"indicator": "急性加重风险", "value": "15.5倍", "fact": "ud-exac"},
        {"indicator": "呼吸系统死亡风险", "value": "4.3倍", "fact": "ud-death"},
        {"indicator": "全因死亡风险", "value": "2.0倍", "fact": "ud-death"}]
PCT = [{"indicator": "全球未确诊比例", "value": "70%", "fact": "ud-70"},
       {"indicator": "二十七国未确诊比例", "value": "81%", "fact": "ud-81"}]

SPEC = {
    "schema_version": "presentation.v1",
    "pages": [
        {"id": "p-hero", "structure": "stat", "role": "hero", "section": "疾病负担",
         "headline": "七成患者不知道自己得病",
         "lead": {"value": "70%", "label": "成人患者未被确诊", "from": "ud-70"},
         "items": [{"facts": ["ud-81"], "label": "确诊的人更少"}]},
        {"id": "p-bars", "structure": "stat", "section": "疾病负担",
         "headline": "相对同龄人，风险高出几倍",
         "figure": [{"kind": "bars", "label": "慢性阻塞性肺疾病患者相对同龄人的风险",
                     "series": RISK}]},
        {"id": "p-pct", "structure": "stat", "section": "疾病负担",
         "headline": "两国数字，七成以上没被确诊",
         "figure": [{"kind": "bars", "series": PCT}]},
        {"id": "p-mix", "structure": "stat", "section": "版式样张",
         "headline": "一条界线，一组柱",
         "figure": [{"kind": "split", "thresholds": [
             {"indicator": "呼吸困难评分", "op": "≥", "value": "≥5", "fact": "sv-mod-vas"}]},
             {"kind": "bars", "series": PCT}]},
    ],
}

out = ROOT / "tmp" / "fig_probe"
out.mkdir(parents=True, exist_ok=True)
(out / "fig_spec.json").write_text(json.dumps(SPEC, ensure_ascii=False, indent=1), encoding="utf-8")
pages = P.check(SPEC, facts)["pages"]
for pg in pages:
    shape = "+".join(f["kind"] for f in pg["figure"]) or pg["structure"]
    print(f'{pg["id"]:8s} role={pg["role"]:10s} form={pg["form"]:10s} shape={shape:12s} weights={pg["weights"]}')

print("\n--- refusals (each must raise) ---")
BAD = {
    "量纲混了": {"id": "b1", "structure": "stat", "lead": None, "figure": [{"kind": "bars", "series": [
        {"indicator": "激素疗程", "value": "5天", "fact": "ex-steroid"},
        {"indicator": "全球未确诊比例", "value": "70%", "fact": "ud-70"}]}]},
    "一根柱": {"id": "b2", "structure": "stat", "lead": None, "figure": [{"kind": "bars", "series": [
        {"indicator": "全球未确诊比例", "value": "70%", "fact": "ud-70"}]}]},
    "区间当柱": {"id": "b3", "structure": "stat", "lead": None, "figure": [{"kind": "bars", "series": [
        {"indicator": "中低收入国家未确诊比例", "value": "90-95%", "fact": "ud-lmic"},
        {"indicator": "全球未确诊比例", "value": "70%", "fact": "ud-70"}]}]},
    "两组柱无名": {"id": "b4", "structure": "stat", "lead": None, "figure": [
        {"kind": "bars", "series": PCT}, {"kind": "bars", "series": PCT}]},
    "四部分": {"id": "b5", "structure": "stat", "lead": None, "figure": [
        {"kind": "bars", "label": "一", "series": PCT}, {"kind": "bars", "label": "二", "series": PCT},
        {"kind": "bars", "label": "三", "series": PCT}, {"kind": "bars", "label": "四", "series": PCT}]},
    "未知部件": {"id": "b6", "structure": "stat", "lead": None, "figure": [{"kind": "pie", "series": PCT}]},
    "主次只标一半": {"id": "b7", "structure": "points", "items": [
        {"facts": ["ud-70"], "label": "全球", "weight": "core"},
        {"facts": ["ud-81"], "label": "多国"},
        {"facts": ["ud-death"], "label": "死亡"}]},
    "全是核心": {"id": "b8", "structure": "points", "items": [
        {"facts": ["ud-70"], "label": "全球", "weight": "core"},
        {"facts": ["ud-81"], "label": "多国", "weight": "core"},
        {"facts": ["ud-death"], "label": "死亡", "weight": "core"}]},
    "steps 标主次": {"id": "b9", "structure": "steps", "items": [
        {"facts": ["ud-70"], "label": "全球", "weight": "core"},
        {"facts": ["ud-81"], "label": "多国", "weight": "support"},
        {"facts": ["ud-death"], "label": "死亡", "weight": "support"}]},
    "未知 role": {"id": "b10", "structure": "stat", "role": "cover", "lead": None,
                  "items": [{"facts": ["ud-70"], "label": "全球"}]},
    "图页带主数字": {"id": "b11", "structure": "stat", "figure": [{"kind": "bars", "series": PCT}],
                    "lead": {"value": "70%", "label": "未确诊", "from": "ud-70"}},
}
for name, page in BAD.items():
    try:
        P.check({"schema_version": "presentation.v1", "pages": [page]}, facts)
        print(f"  {name:12s} —— 未拒绝（问题！）")
    except P.PresentationError as e:
        print(f"  {name:12s} —— {e}")

models, all_rules = [], []
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 720})
    for i, page in enumerate(pages, 1):
        html = render_page(page, page_no=i, total=len(pages), source="来源：2026 GOLD 报告（中文版）",
                           section=page.get("section"))
        f = out / f"fig_p{i}.html"
        f.write_text("<!doctype html><meta charset='utf-8'>" + html, encoding="utf-8")
        pg.goto(f.as_uri())
        pg.wait_for_timeout(200)
        issues = pg.evaluate(MEASURE_JS)
        rules = design_audit(pg.evaluate(DESIGN_JS, 0), role=page["role"], figure=bool(page["figure"]))
        errs = [r for r in rules if r.get("level") != "warn"]
        print(f'\n{page["id"]} overflow={len(issues)} design: {len(errs)} error / {len(rules) - len(errs)} warn')
        for r in rules:
            print("     ", r.get("level", "error"), r["rule"], r["detail"])
        all_rules += rules
        pg.locator(".slide").screenshot(path=str(out / f'fig_p{i}.png'))
        models.append(N.extract_slide(pg))
    b.close()

pptx = out / "figure_v5.pptx"
N.build_pptx(models, pptx, title="GOLD 2026 — 组合图形样张")
info = N.inspect_pptx(pptx)
print("\n" + json.dumps({k: info[k] for k in ("slides", "pictures", "svg", "unsupported") if k in info},
                        ensure_ascii=False))
print("size", pptx.stat().st_size)
