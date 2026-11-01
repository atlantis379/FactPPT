"""Is one page per assertion necessary?  This checks the alternative: 50 assertions, 21 pages, nothing dropped.

The rule being tested is not "a page may hold several assertions" but "a page carries one judgement, and the
objects it enumerates live in the evidence area".  Three things follow and each is checkable:

  1. every assertion is covered by exactly one page (a partition — nothing dropped, nothing counted twice)
  2. every page's own judgement passes `check()` against the sentences it cites
  3. the judgements do not collapse into each other (the whole set passes together)

What code cannot check is whether the enumeration under a judgement is homogeneous — whether "三种疫苗都该打"
is one decision while "诊断" and "谁该查" are two.  That is the model's call, same division of labour as the
grade itself.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factdeck import argument as A

facts = {f["id"]: f for f in json.loads((ROOT / "output/gold2026_deck/facts_verified.json")
                                        .read_text(encoding="utf-8"))["facts"]}
plan = json.loads((ROOT / "tmp/argument_pages.json").read_text(encoding="utf-8"))
claims = json.loads((ROOT / "tmp/argument_free_checked.json")
                    .read_text(encoding="utf-8"))["claims"]
have = {c["id"]: c for c in claims}

pages = plan["pages"]
covered = [cid for p in pages for cid in p["covers"]]
tally = Counter(covered)
missing = sorted(set(have) - set(tally))
extra = sorted(set(tally) - set(have))
dup = sorted(c for c, n in tally.items() if n > 1)

print(f"{len(have)} 条断言 → {len(pages)} 页（平均 {len(have) / len(pages):.1f} 条/页）\n")
for p in pages:
    c = p["claim"]
    mark = "" if len(p["covers"]) == 1 else f"  ← {len(p['covers'])} 条并入"
    print(f"  {p['pid']}  {c['grade']}  {c['text']}{mark}")
    for cid in p["covers"]:
        print(f"          · {have[cid]['text']}")

print(f"\n覆盖：{len(tally)}/{len(have)} 条；重复 {dup or '无'}；遗漏 {missing or '无'}；多余 {extra or '无'}")

# 1. each judgement on its own — beside one known-good action claim, because "the deck reaches an action" is a
#    property of the set, not of a page
ANCHOR = {"id": "anchor", "grade": "L3", "text": "全程推荐接种流感疫苗，减少 6 个月以上人群的风险",
          "evidence": ["pv-flu"]}
bad = []
for p in pages:
    try:
        A.check({"schema_version": A.SCHEMA, "claims": [ANCHOR, dict(p["claim"], id="c1")]}, facts)
    except A.ArgumentError as e:
        bad.append((p["pid"], str(e)))
print(f"逐页体检：{len(pages) - len(bad)}/{len(pages)} 通过")
for pid, msg in bad:
    print(f"  {pid} → {msg[:90]}")

# 2. all judgements together: no two say the same thing, and the set reaches an action
try:
    res = A.check({"schema_version": A.SCHEMA, "claims": [dict(p["claim"], id=p["pid"]) for p in pages]},
                  facts)
    print(f"整份：通过，{res['grades']}，行动 {sum(1 for c in res['claims'] if c['action'])} 页")
except A.ArgumentError as e:
    print(f"整份未通过：{str(e)[:120]}")
