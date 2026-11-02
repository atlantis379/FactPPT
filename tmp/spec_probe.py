"""Can the material support a picture at all?  Before any model draws anything, the spec has to pass.

`assets.check_spec` asks two things of every spec: each element is a word of a sentence, and each relation is
carried by one sentence naming both ends.  If the guideline's prose cannot meet that, a better drawing model buys
nothing — so this runs over the obvious illustration candidates in the 83 facts, with no provider and no key.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factdeck import assets as A

facts = {f["id"]: f for f in json.loads((ROOT / "output/gold2026_deck/facts_verified.json")
                                        .read_text(encoding="utf-8"))["facts"]}

SPECS = {
    "气道与肺泡如何造成气流阻塞（def-core）": {
        "schema_version": "figure.v1", "mode": "schematic",
        "elements": [{"name": "气道", "fact": "def-core"},
                     {"name": "支气管炎", "fact": "def-core"},
                     {"name": "细支气管炎", "fact": "def-core"},
                     {"name": "肺泡", "fact": "def-core"},
                     {"name": "肺气肿", "fact": "def-core"},
                     {"name": "气流阻塞", "fact": "def-core"}],
        "relations": [{"kind": "contains", "from": "气道", "to": "支气管炎", "fact": "def-core"},
                      {"kind": "contains", "from": "气道", "to": "细支气管炎", "fact": "def-core"},
                      {"kind": "contains", "from": "肺泡", "to": "肺气肿", "fact": "def-core"},
                      {"kind": "leads_to", "from": "气道", "to": "气流阻塞", "fact": "def-core"}],
        "anchors": {"a1": {"name": "肺泡", "x": 0.72, "y": 0.42}},
    },
    "急性加重时会发生什么（ex-def）": {
        "schema_version": "figure.v1", "mode": "schematic",
        "elements": [{"name": "呼吸困难", "fact": "ex-def"},
                     {"name": "咳嗽", "fact": "ex-def"},
                     {"name": "痰量", "fact": "ex-def"},
                     {"name": "呼吸急促", "fact": "ex-def"},
                     {"name": "心动过速", "fact": "ex-def"}],
        "relations": [],
    },
    "肺康复包含什么（np-rehab）": {
        "schema_version": "figure.v1", "mode": "realistic",
        "elements": [{"name": "肺康复", "fact": "np-rehab"},
                     {"name": "疾病特异性教育", "fact": "np-rehab"},
                     {"name": "运动训练", "fact": "np-rehab"}],
        "relations": [{"kind": "contains", "from": "肺康复", "to": "疾病特异性教育", "fact": "np-rehab"},
                      {"kind": "contains", "from": "肺康复", "to": "运动训练", "fact": "np-rehab"}],
    },
    "反例：想画一个原文没说的关系（应当被拒）": {
        "schema_version": "figure.v1", "mode": "schematic",
        "elements": [{"name": "吸烟", "fact": "np-smoke"},
                     {"name": "气流阻塞", "fact": "def-core"}],
        "relations": [{"kind": "leads_to", "from": "吸烟", "to": "气流阻塞", "fact": "np-smoke"}],
    },
}

for label, spec in SPECS.items():
    try:
        got = A.check_spec(spec, facts)
        print(f"  通过  {label}：{len(got['elements'])} 元素 / {len(got['relations'])} 关系")
    except A.AssetError as e:
        print(f"  拒绝  {label}\n          → {e}")

# what a prompt looks like, built by code from the spec and the pack — never freehand
style = A.styles()["clinical_blue"]
print("\n生成的提示词（临床蓝，def-core）：\n  " + A.prompt_for(SPECS["气道与肺泡如何造成气流阻塞（def-core）"], style))
print("\n清单里的每个标定点都会变成一句要盲读回答的问题：")
for q in A.checklist(SPECS["气道与肺泡如何造成气流阻塞（def-core）"])[:4]:
    print("  ·", q["ask"])
