"""A structured (Markdown) teaching outline organises the summary and the deck.

Content is invented test data; approvals are test records, not customer sign-off.
"""
import copy

import pytest

from app.deckflow import Store, WorkflowError, parse_structured_outline, input_hash
from factdeck.deck import check
import factdeck_fixture as fx_
import test_deckflow as T
from test_layout_guidance import facts as flow_facts

OUTLINE = """# 示例课程
**授课对象**：规培医生

## 第一部分 概述（建议5 min）
### 1. 认识示例病X
- 定义与患病率
- 诊断指标：
  - 指标甲
  - 指标乙
**注意：**
- 两项指标需同时满足

## 第二部分 治疗（建议10 min）
### 1. 评估与药物
评估维度：
- 评估流程
- 资料中没有的内容
### 2. 药物总览
| 药物 | 靶点 |
|---|---|
| 药物A | T-1 |

## 建议课件页数分配
- 第一部分：2–3页
- 第二部分：3页
"""


def test_markdown_outline_becomes_parts_items_and_points():
    items, parts = parse_structured_outline(OUTLINE)
    assert [i["text"] for i in items] == ["第一部分 概述：认识示例病X", "第二部分 治疗：评估与药物", "第二部分 治疗：药物总览"]
    assert [p["text"] for p in items[0]["points"]] == ["定义与患病率", "诊断指标：指标甲；指标乙", "注意：两项指标需同时满足"]
    assert [p["text"] for p in items[1]["points"]] == ["评估维度：评估流程", "评估维度：资料中没有的内容"]
    assert items[2]["points"][0]["text"] == "表格：药物、靶点"                  # the table's figures are not taken
    assert items[0]["points"][1]["id"] == "outline_1.2"
    assert parts == [{"title": "第一部分 概述", "pages": [2, 3]}, {"title": "第二部分 治疗", "pages": [3, 3]}]


def test_plain_outline_is_still_split_by_line():
    items, parts = parse_structured_outline("认识示例病X\n评估与治疗")
    assert [i["text"] for i in items] == ["认识示例病X", "评估与治疗"] and parts == []


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "deckflow-data")


def structured_summary(w):
    ids = [p["id"] for s in w["sources"] for p in s["pages"]]
    first = {}
    for s in w["sources"]:
        for u in s["units"] + s["transcriptions"]:
            first.setdefault(u["page_id"], u["id"])
    chunks = [ids[:3], ids[3:5], ids[5:]]
    sections = []
    for n, (o, pages) in enumerate(zip(w["outline"], chunks), 1):
        cover = [{"point_id": p["id"], "point": p["text"], "claim_ids": [T.claim_of(w, first[pages[0]])]} for p in o["points"]]
        sections.append({"id": f"s{n}", "outline_id": o["id"], "title": o["text"], "summary": "程序验收用的虚构章节总结，逐条覆盖本提纲条目的要点。",
                         "source_page_ids": pages, "key_points": T.key_points(w, pages), "point_coverage": cover})
    return {"schema_version": "full_source_summary.v3", "input_sha256": input_hash(w),
            "overall_summary": "程序验收用的虚构资料总结：示例病X的定义与诊断、评估流程与药物、两项研究及其不可直接比较的限制。",
            "sections": sections, "outline_coverage": [], "pending_issues": []}


def add_messages(w, r):
    """A minimal valid information structure per section: the first supported point is the core, its first unit
    the core sentence, no relations."""
    units = [u for s in w["sources"] for u in s["units"] + s["transcriptions"]]
    text = {u["id"]: u["text"] for u in units}
    for sec in r["sections"]:
        rows = [x for x in sec.get("point_coverage") or [] if x.get("unsupported") is None]
        if not sec.get("outline_id") or not rows:
            sec.pop("message", None)
            continue
        uid = next(u["id"] for u in units if u["page_id"] in sec["source_page_ids"] and len(u["text"].strip()) >= 8)
        cid = T.claim_of(w, uid)
        if cid not in rows[0]["claim_ids"]:
            rows[0]["claim_ids"].insert(0, cid)
        sec.setdefault("message", {"core": {"claim_id": cid},
                                   "roles": {x["point_id"]: "core" if i == 0 else "support" for i, x in enumerate(rows)},
                                   "relations": []})
        sec["message"].setdefault("candidate_decisions", T.candidate_decisions(
            w, sec["source_page_ids"], adopted={x.get("from_candidate") for x in sec["message"]["relations"] if x.get("from_candidate")}))
    return r


def test_summary_follows_the_outline_point_by_point(store):
    w = store.create("结构化提纲", OUTLINE)
    assert w["outline_parts"][0]["pages"] == [2, 3]
    for name, make in fx_.SOURCES.items():
        store.add_source(w["id"], name, make())
    w = T.read_all(store, w["id"])
    store.queue(w["id"], "SUMMARY")
    t = store.claim(w["id"], "author-A", "SUMMARY")
    assert [s.get("outline_id") for s in t["brief"]["result_contract"]["sections"]][:3] == ["outline_1", "outline_2", "outline_3"]

    def submit(edit):
        r = structured_summary(w)
        edit(r)
        add_messages(w, r)
        T.with_understanding(w, r)
        store.complete(w["id"], t["id"], t["lease_token"], r)

    with pytest.raises(WorkflowError, match="提纲顺序"):
        submit(lambda r: r["sections"].reverse())
    with pytest.raises(WorkflowError, match="point_coverage"):
        submit(lambda r: r["sections"][0]["point_coverage"].pop())
    with pytest.raises(WorkflowError, match="写明原因"):
        submit(lambda r: r["sections"][1]["point_coverage"][1].update(claim_ids=[], unsupported=""))
    with pytest.raises(WorkflowError, match="支撑它的论断"):
        submit(lambda r: r["sections"][1]["point_coverage"][1].update(claim_ids=[]))
    submit(lambda r: r["sections"][1]["point_coverage"][1].update(claim_ids=[], unsupported="资料未涉及此内容"))
    w = store.get(w["id"])
    assert [m["outline_id"] for m in w["summary"]["outline_coverage"]] == ["outline_1", "outline_2", "outline_3"]


# ------------------------------------------------------------------ the deck against the outline
def outline_and_sections():
    items, parts = parse_structured_outline(OUTLINE)
    sections = [{"id": f"s{i}", "title": o["text"], "outline_id": o["id"],
                 "point_coverage": [{"point_id": p["id"], "unit_ids": ["x"]} for p in o["points"]]} for i, o in enumerate(items, 1)]
    sections[1]["point_coverage"][1] = {"point_id": "outline_2.2", "unsupported": "资料未涉及此内容"}
    return items, parts, sections


def page(pid, points, layout="bullets"):
    return {"id": pid, "layout": layout, "title": {"text": "要点"}, "items": [{"fact": "p1"}], "point_ids": points, "section_ids": []}


def divider(pid):
    return {"id": pid, "layout": "divider", "title": {"text": "部分"}}


def run(pages):
    items, parts, sections = outline_and_sections()
    return check({"pages": pages, "omissions": [{"section_id": s["id"], "reason": "测试"} for s in sections]}, flow_facts(),
                 outline=items, sections=sections, parts=parts)


GOOD = [divider("d1"), page("a", ["outline_1.1", "outline_1.2"]), page("b", ["outline_1.3"]),
        divider("d2"), page("c", ["outline_2.1"]), page("d", ["outline_3.1"]), page("e", ["outline_3.1"])]


def test_deck_covers_every_supported_point_in_outline_order():
    res = run(GOOD)
    assert res["errors"] == 0, res["deck_errors"] + [e for p in res["pages"] for e in p["errors"]]
    assert {p["point_id"]: p["unsupported"] for p in res["coverage"]["points"]}["outline_2.2"] == "资料未涉及此内容"
    assert not any("提纲建议" in w for w in res["warnings"])


def test_deck_outline_errors_and_warnings():
    missing = run([p for p in GOOD if p["id"] != "b"])
    assert any("outline_1.3" in e for e in missing["deck_errors"])
    shown_gap = run(GOOD[:5] + [page("x", ["outline_2.2"])] + GOOD[5:])
    assert any("无资料支撑" in e for e in shown_gap["deck_errors"])
    swapped = run([GOOD[0], GOOD[4], GOOD[1], GOOD[2], GOOD[3], GOOD[5], GOOD[6]])
    assert any("顺序" in e for e in swapped["deck_errors"])
    unmarked = run(GOOD[:1] + [dict(GOOD[1], point_ids=[])] + GOOD[2:])
    assert any("point_ids" in e for e in unmarked["deck_errors"])
    no_divider = run([p for p in GOOD if p["id"] != "d2"])
    assert any("章节页" in w for w in no_divider["warnings"])
    long = run(GOOD + [page(f"f{i}", ["outline_3.1"]) for i in range(3)])
    assert any("提纲建议 3–3 页" in w for w in long["warnings"])
