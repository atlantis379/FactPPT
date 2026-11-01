"""Run the assertion round: a model writes claims, code accepts or refuses each one, and the deck's page count
falls out of what survived.

`check()` stops at the first error, so the round is driven per claim: each candidate is put in a list beside one
known-good claim and checked alone, which gives every refusal its own reason.  The survivors are then checked
together, which is the only place duplication and "never reaches an action" can be seen.

    python tmp/argument_run.py tmp/argument_draft2.json
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
src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tmp/argument_draft.json"
path = src if src.is_absolute() else ROOT / src
draft = json.loads(path.read_text(encoding="utf-8"))
GOOD = {"id": "anchor", "grade": "L3", "text": "全程推荐接种流感疫苗，减少 6 个月以上人群的风险",
        "evidence": ["pv-flu"]}


def kind(msg: str) -> str:
    for key, label in (("没有任何可核对的数字", "声明量化却无数字"),
                       ("句中有数字", "有数字却声明非量化"),
                       ("找不到", "数字不在所引句"),
                       ("的单位在来源句里没有", "单位被换"),
                       ("用了强推荐", "强度被抬高"),
                       ("不能单独成一页", "等级低于地板"),
                       ("须声明 grade", "等级缺失"),
                       ("须给出 scope", "定向却无对象"),
                       ("不是证据句的原文", "对象非原文"),
                       ("太短", "对象太笼统"),
                       ("说的是同一件事", "与前条同义")):
        if key in msg:
            return label
    return msg[:24]


print(f"{src.name}：{len(draft['claims'])} 条 —— 逐条体检\n")
passed, refused = [], []
for c in draft["claims"]:
    try:
        A.check({"schema_version": A.SCHEMA, "claims": [GOOD, c]}, facts)
        passed.append(c)
        print(f"  通过  {c['id']:4s} {c.get('grade')}  {c['text']}")
    except A.ArgumentError as e:
        refused.append((c, kind(str(e)), str(e)))
        print(f"  拒绝  {c['id']:4s} {c.get('grade')}  {c['text']}\n          → {str(e)[:100]}")

print(f"\n通过 {len(passed)} / 拒绝 {len(refused)}；"
      f"拒绝原因：{dict(Counter(k for _, k, _ in refused)) or '无'}")

final = {"schema_version": A.SCHEMA, "claims": passed}
try:
    res = A.check(final, facts)
except A.ArgumentError as e:
    print(f"\n整份体检未通过：{e}")
    res = None
if res:
    acts = [c["text"] for c in res["claims"] if c["action"]]
    print(f"\n整份通过：{res['grades']}，行动断言 {len(acts)} 条 —— {' / '.join(acts)}")
    rng = A.page_range(len(res["claims"]), minutes=20)
    print("页数：", A.verdict(20, rng))

(out := path.with_name(f"{path.stem}_checked.json")).write_text(
    json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
print("\nwrote", out)
