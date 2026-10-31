"""Argument probe: does the deck that exists carry assertions, and is its page count honest?

Two questions, both answered against `output/gold2026_deck`:
  1. how many of the 20 titles can stand as a quantified assertion at all?
  2. with that many, how many pages can the deck honestly be?
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factdeck import argument as A

facts = {f["id"]: f for f in json.loads((ROOT / "output/gold2026_deck/facts_verified.json")
                                        .read_text(encoding="utf-8"))["facts"]}
deck = json.loads((ROOT / "output/gold2026_deck/deck.json").read_text(encoding="utf-8"))
with_digits = [f for f in facts.values() if A.numbers(f["quote"])]
print(f"材料：{len(facts)} 条可逐字引用的句子，其中 {len(with_digits)} 条含可核对的数字")

print("\n--- 20 页标题：能不能当量化断言 ---")
content = strong = 0
for p in deck["pages"]:
    t = p["title"]
    text = t if isinstance(t, str) else (t.get("text") or "")
    structural = p["id"].startswith("sec") or p["id"] == "cover"
    d = A.numbers(text)
    ok = A.quantifiable(text, facts, list(facts))
    if not structural:
        content += 1
        strong += bool(ok)
    mark = "结构" if structural else ("可量化" if ok else "无数字")
    print(f"  {mark:4s} | {(text or '(无标题)'):<28} | 数字 {sorted(d) if d else '—'}")
print(f"\n  内容页 {content} 页；标题里带可核对数字的 {strong} 页；"
      f"材料里含数字的句子 {len(with_digits)} 条 —— 提炼端缺，不是材料端缺")

print("\n--- 断言清单体检（样张：四条真断言 + 七种拒绝）---")
SAMPLE = {"schema_version": A.SCHEMA, "claims": [
    {"id": "c1", "grade": "L3", "text": "全球 70% 的成人患者未被确诊", "evidence": ["ud-70"]},
    {"id": "c2", "grade": "L3", "text": "27 国研究中 81% 的病例未被确诊", "evidence": ["ud-81"]},
    {"id": "c3", "grade": "L3", "text": "相对同龄人，急性加重风险高出 15.5 倍", "evidence": ["ud-exac"]},
    {"id": "c4", "grade": "L4", "text": "推荐全身激素，疗程不超过 5 天", "evidence": ["ex-steroid"],
     "boundary": "适用于中度或重度急性加重"},
]}
BAD = {
    "话题当断言": {"id": "b1", "grade": "L3", "text": "非药物治疗的要点", "evidence": ["ud-70"]},
    "等级声明过低": {"id": "b2", "grade": "L2", "text": "漏诊比误诊更常见", "evidence": ["ud-70"]},
    "数字不在句里": {"id": "b3", "grade": "L3", "text": "全球 80% 的成人患者未被确诊", "evidence": ["ud-70"]},
    "单位被换掉": {"id": "b4", "grade": "L3", "text": "全球 70 例成人患者未被确诊", "evidence": ["ud-70"]},
    "强度被抬高": {"id": "b5", "grade": "L3", "text": "50 岁以上成人都应接种疫苗", "evidence": ["pv-pcv"]},
    "边界数字没出处": {"id": "b6", "grade": "L4", "text": "全球 70% 的成人患者未被确诊", "evidence": ["ud-70"],
                       "boundary": "在低收入国家超过 90%"},
    "与第一条同义": {"id": "b7", "grade": "L3", "text": "全球 70% 的成人患者未被确诊", "evidence": ["ud-70"]},
}
for name, c in BAD.items():
    try:
        A.check({"schema_version": A.SCHEMA, "claims": [SAMPLE["claims"][0], c]}, facts)
        print(f"  {name:10s} —— 未拒绝（问题！）")
    except A.ArgumentError as e:
        print(f"  {name:10s} —— {e}")

res = A.check(SAMPLE, facts)
print()
for c in res["claims"]:
    print(f'  {c["id"]} {c["grade"]} {"行动 " if c["action"] else "     "}{c["text"]}'
          + (f'（边界：{c["boundary"]}）' if c["boundary"] else ""))

print("\n--- 页数：20 是输入还是答案 ---")
for n in (6, 13, 18):
    print("  ", A.verdict(20, A.page_range(n)))
print("  ", A.verdict(20, A.page_range(18, minutes=20)))
