"""Layout selector: pick one template-library layout per slide, with an explainable record.

Pipeline per page (all deterministic unless a tie-breaker is plugged in):

  1. classify()      — rule-based relation detection from title/text (中文 + English signals)
                       plus structured data; every relation gets a score + the signals it matched.
  2. qualify()       — per-layout minimum-data check.  A layout whose data is missing is never
                       "filled in": it is downgraded along a fixed chain (e.g. forest_plot →
                       data_table_highlight → key_points) and the reason is recorded.
  3. tie-break       — only among *qualified* candidates whose top scores are close.  Pluggable
                       (e.g. an LLM); the answer must be in the candidate set or it is rejected
                       and the deterministic rule (highest score, then rhythm) decides.
  4. rhythm          — no identical layout on consecutive content pages; chart pages ≥ 1/3 of
                       content pages when qualified candidates allow.  Cover / section exempt.

Input page (dict)::

    {"id": "p5", "kind": "content" | "cover" | "section",
     "title": "...", "text": ["sentence", ...],
     "data": {...optional structured data, see REQUIREMENTS...}}

Nothing here reads a page's intended layout; it only looks at content.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

# --------------------------------------------------------------------------- catalogue

# layout id → (family, variant, 中文名, is_chart)
LAYOUTS: dict[str, tuple[str, str | None, str, bool]] = {
    "cover": ("cover", None, "封面", False),
    "section": ("section", None, "章节页", False),
    "algorithm_tree": ("algorithm_tree", None, "决策算法树", True),
    "assessment_matrix": ("assessment_matrix", None, "评估矩阵", True),
    "dual_path_tree": ("dual_path_tree", None, "双路径治疗树", True),
    "trial_design": ("trial_design", None, "试验设计图", True),
    "forest_plot": ("forest_plot", None, "森林图", True),
    "endpoint_readout/bar": ("endpoint_readout", "bar", "终点读出（柱图）", True),
    "endpoint_readout/line": ("endpoint_readout", "line", "终点读出（折线）", True),
    "moa_cascade": ("moa_cascade", None, "机制级联图", True),
    "data_table_highlight": ("data_table_highlight", None, "高亮数据表", True),
    "landscape_swimlane": ("landscape_swimlane", None, "研究格局泳道", True),
    "key_points/evidence_takeaways": ("key_points", "evidence_takeaways", "证据要点", False),
    "comparison": ("comparison", None, "对照页", False),
    "flow": ("flow", None, "流程页", False),
    "timeline": ("timeline", None, "时间轴", False),
    "key_points": ("key_points", None, "要点卡片", False),
}
CHART_LAYOUTS = {k for k, v in LAYOUTS.items() if v[3]}

_RAIL = "；右栏 3–4 条数字开头的要点（takeaways）"
# What requirement_gap checks, said once for the DECK worker's brief (keep the two in step).
REQUIRES_ZH: dict[str, str] = {
    "algorithm_tree": "至少 1 个判定条件，同时有条件、“是”去向和“否”去向",
    "assessment_matrix": "2 个轴、每轴 ≥2 个分层，≥3 格结论",
    "dual_path_tree": "恰好 2 条路径，每条 ≥2 步",
    "trial_design": "2–3 个治疗臂、各臂 n 或治疗时长、≥3 个时间点" + _RAIL,
    "forest_plot": "≥3 行带 95% CI 的效应量（0 < 下限 ≤ 估计值 ≤ 上限）" + _RAIL,
    "endpoint_readout/bar": "两组（臂）各自的数值、个数与类别一致、统计框（差值/95% CI/P 值）" + _RAIL,
    "endpoint_readout/line": "同柱图，另需 ≥3 个数值型时间点" + _RAIL,
    "moa_cascade": "3–6 级机制链" + _RAIL,
    "data_table_highlight": "1–4 个数据列（不要用空列凑数）、3–18 行（rows[].cells 每列一格，按列序）、至多 1 行高亮；右栏可不写"
                            "（写则 3–4 条数字开头的要点），不写时表格占满正文、文字单元格自动换行",
    "landscape_swimlane": "≥3 项带起止年份和状态（达到/未达到/进行中）的研究/药物，2–6 个分组" + _RAIL,
    "key_points/evidence_takeaways": "3–4 条数字开头的结论，每条带逐字摘录",
    "comparison": "A/B 两侧各 1–8 条（或 rows 写成两列对照表）",
    "flow": "3–6 个步骤",
    "timeline": "4–6 个带时间标签的节点",
    "key_points": "1–6 条要点（1 条会提示并入相邻页）；每张卡片的 heading 是这张卡片自己的名称，同页卡片不得同名",
}
EXEMPT_KINDS = {"cover", "section"}

# relation id → (中文名, preferred layout)
RELATIONS: dict[str, tuple[str, str]] = {
    "conditional": ("条件/阈值判断", "algorithm_tree"),
    "matrix": ("双轴分层交叉", "assessment_matrix"),
    "dual_path": ("两条平行路径", "dual_path_tree"),
    "trial_setup": ("试验设计", "trial_design"),
    "effect_sizes": ("多行效应量（HR/RR + 95% CI）", "forest_plot"),
    "arm_readout": ("两组终点对比", "endpoint_readout/bar"),
    "mechanism": ("因果/机制链", "moa_cascade"),
    "tabular": ("多行×多列数据", "data_table_highlight"),
    "landscape": ("研究/药物×年份格局", "landscape_swimlane"),
    "takeaways": ("数字化结论", "key_points/evidence_takeaways"),
    "contrast": ("A vs B 对照", "comparison"),
    "sequence": ("步骤序列", "flow"),
    "chronology": ("时间先后", "timeline"),
    "points": ("并列要点（兜底）", "key_points"),
}

# Downgrade chain: if a layout's minimum data is missing, try the next one.  Never fabricate.
DOWNGRADE: dict[str, str] = {
    "forest_plot": "data_table_highlight",
    "data_table_highlight": "comparison",
    "endpoint_readout/line": "endpoint_readout/bar",
    "endpoint_readout/bar": "key_points/evidence_takeaways",
    "key_points/evidence_takeaways": "key_points",
    "trial_design": "timeline",
    "landscape_swimlane": "timeline",
    "timeline": "flow",
    "assessment_matrix": "comparison",
    "dual_path_tree": "comparison",
    "algorithm_tree": "flow",
    "moa_cascade": "flow",
    "flow": "key_points",
    "comparison": "key_points",
}

# --------------------------------------------------------------------------- signals

@dataclass
class Sig:
    name: str
    pattern: str
    weight: float = 1.0


def _p(*alts: str) -> str:
    return "(?:" + "|".join(alts) + ")"


# Generic relation / statistics signals only.  Subject vocabulary (clinical-trial, biomedical, care-pathway
# words) lives in config/layout_signals.json and is merged in by load_signals(); a project may add its own
# terms through the plan's "layout_signals" (same shape).  Nothing disease-specific belongs in this file.
GENERIC_SIGNALS: dict[str, list[Sig]] = {
    "conditional": [
        Sig("如果/若…则", _p(r"如果", r"若[^，。]{0,20}则", r"则", r"否则", r"是否"), 1.5),
        Sig("是/否分支", _p(r"(?<![a-zA-Z])是\s*[·:：]", r"否\s*[·:：]", r"\byes\b", r"\bno\b"), 1.0),
        Sig("if/then", _p(r"\bif\b", r"\bthen\b", r"\botherwise\b"), 1.5),
        Sig("阈值/cut-off", _p(r"阈值", r"cut-?off", r"threshold", r"临界"), 1.0),
        Sig("比较符号 ≥ < 阈值", r"[≥≤<>]\s*\d", 0.5),
    ],
    "matrix": [
        Sig("矩阵/象限", _p(r"矩阵", r"象限", r"matrix", r"quadrant", r"grid"), 2.0),
        Sig("分组 A/B/E", _p(r"组别\s*[A-E]", r"[A-E]\s*组", r"group\s*[A-E]\b"), 1.5),
        Sig("× 交叉", _p(r"×", r"交叉", r"横轴", r"纵轴"), 1.0),
    ],
    "dual_path": [
        Sig("双/两条路径", _p(r"双路径", r"两条路径", r"两种路径", r"dual[- ]path", r"two (?:routes|paths)"), 2.5),
        Sig("X 路径", r"\S{1,6}路径", 1.0),
        Sig("分路径/分别走", _p(r"分路径", r"分别", r"走[^，。]{0,8}升级"), 1.0),
        Sig("升级/降阶梯", _p(r"升级", r"降阶梯", r"escalat", r"de-?escalat"), 0.5),
    ],
    "trial_setup": [
        Sig("第 N 周 / weeks", _p(r"第\s*[−-]?\d+\s*周", r"\d+\s*周", r"\bweeks?\s*\d+", r"\d+\s*weeks?"), 0.5),
    ],
    "effect_sizes": [
        Sig("HR/RR/OR", _p(r"\bHR\b", r"\bRR\b", r"\bOR\b", r"\bIRR\b", r"率比", r"风险比", r"比值比", r"hazard ratio", r"rate ratio"), 1.5),
        Sig("95% CI", _p(r"95\s*%\s*CI", r"置信区间"), 1.5),
        Sig("亚组/subgroup", _p(r"亚组", r"subgroup", r"森林图", r"forest"), 1.5),
        Sig("区间 a–b", r"\d\.\d+\s*[–~-]\s*\d\.\d+", 0.5),
    ],
    "arm_readout": [
        Sig("vs/两组", _p(r"\bvs\.?\b", r"versus", r"两组", r"组间", r"对比", r"相比"), 1.0),
        Sig("差值/降低 N%", _p(r"差值", r"降低\s*\d", r"[−-]\s*\d+\s*%", r"改善", r"reduc", r"difference"), 1.0),
        Sig("P 值", r"\bP\s*[<=＜]\s*0?\.\d", 1.5),
    ],
    "mechanism": [
        Sig("导致/引起/诱导", _p(r"导致", r"引起", r"诱导", r"促进", r"\bcaus", r"leads? to", r"induc"), 1.5),
        Sig("通过…", r"通过[^，。]{1,20}(引起|导致|作用|激活|抑制)", 1.0),
        Sig("通路/机制/级联", _p(r"通路", r"机制", r"级联", r"pathway", r"mechanism", r"cascade"), 1.5),
        Sig("箭头链 →", r"→[^→]+→", 0.5),
    ],
    "tabular": [
        Sig("表/table", _p(r"^表", r"表\s*\d", r"\btable\b"), 1.5),
        Sig("均值(SD)/n(%)", _p(r"均值", r"中位数", r"\bSD\b", r"IQR", r"n\s*[（(]\s*%"), 1.0),
    ],
    "landscape": [
        Sig("格局/管线/泳道", _p(r"格局", r"管线", r"泳道", r"landscape", r"pipeline"), 2.0),
        Sig("多项研究", _p(r"\d+\s*项", r"研究名", r"studies", r"trials"), 1.0),
        Sig("读出/进行中", _p(r"读出", r"进行中", r"readout", r"ongoing"), 1.0),
        Sig("年份", r"(?:19|20)\d{2}\s*(?:年|–|-)", 0.5),
    ],
    "takeaways": [
        Sig("结论/小结/要点", _p(r"结论", r"小结", r"总结", r"takeaway", r"conclusion", r"key finding"), 1.5),
        Sig("证据号/源页码", _p(r"证据号", r"源文档", r"逐字", r"p\.\s*\d+"), 1.0),
    ],
    "contrast": [
        Sig("A vs B/对照", _p(r"\bvs\.?\b", r"对照", r"versus", r"compared with"), 1.0),
        Sig("与…相比/区别", _p(r"与[^，。]{1,12}相比", r"区别", r"差异", r"不同于"), 1.0),
        Sig("推荐/不推荐", r"推荐.{0,6}不推荐", 1.5),
        Sig("期/类二分", r"(\S{1,6})(期|组)与(\S{1,6})(期|组)", 1.0),
    ],
    "sequence": [
        Sig("步骤/路径/流程", _p(r"步骤", r"\d\s*步", r"路径", r"流程", r"阶梯", r"step", r"process", r"workflow"), 1.5),
        Sig("首先/然后/最后", _p(r"首先", r"然后", r"随后", r"最后", r"first", r"then", r"finally"), 1.0),
        Sig("节点", r"节点", 0.5),
        Sig("→", r"→", 0.5),
    ],
    "chronology": [
        Sig("日期/D0/W4", _p(r"\bD\d+\b", r"\bW\d+\b", r"第\s*\d+\s*天", r"\d{4}[./-]\d{1,2}", r"\d+\s*月\s*\d+\s*日"), 1.5),
        Sig("时间轴/时间线", _p(r"时间轴", r"时间线", r"timeline", r"chronolog"), 1.5),
    ],
    "points": [],
}

SIGNALS_CONFIG = Path(__file__).resolve().parents[2] / "config" / "layout_signals.json"


def _sigs_from(spec: dict | None) -> dict[str, list[Sig]]:
    """{relation: [{name, patterns|pattern, weight}]} → Sig lists (unknown relations are ignored)."""
    out: dict[str, list[Sig]] = {}
    for rel, items in (spec or {}).items():
        if rel.startswith("_") or rel not in RELATIONS or not isinstance(items, list):
            continue
        for it in items:
            pats = it.get("patterns") or ([it["pattern"]] if it.get("pattern") else [])
            if pats:
                out.setdefault(rel, []).append(Sig(str(it.get("name") or pats[0]), _p(*pats), float(it.get("weight", 1.0))))
    return out


@lru_cache(maxsize=4)
def _config_signals(path: str) -> dict[str, list[Sig]]:
    p = Path(path)
    if not p.exists():
        return {}
    return _sigs_from(json.loads(p.read_text(encoding="utf-8")).get("signals"))


def load_signals(extra: dict | None = None, *, config: Path | str | None = None) -> dict[str, list[Sig]]:
    """Generic signals + subject pack (config/layout_signals.json, or FACTDECK_LAYOUT_SIGNALS) + project terms."""
    import os
    path = str(config or os.environ.get("FACTDECK_LAYOUT_SIGNALS") or SIGNALS_CONFIG)
    merged = {k: list(v) for k, v in GENERIC_SIGNALS.items()}
    for src in (_config_signals(path), _sigs_from(extra)):
        for rel, sigs in src.items():
            merged.setdefault(rel, []).extend(sigs)
    return merged


TEXT_SIGNALS = load_signals()   # default set (generic + subject pack); select_deck(signals=...) overrides

_DIGIT = re.compile(r"\d")
_CI_ROW = re.compile(r"(\d+(?:\.\d+)?)\s*[（(]\s*(?:95\s*%\s*CI\s*)?(\d+(?:\.\d+)?)\s*[–~-]\s*(\d+(?:\.\d+)?)\s*[)）]")
_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")


def _text(page: dict) -> str:
    parts = [str(page.get("title") or "")]
    parts += [str(t) for t in page.get("text") or []]
    return "\n".join(parts)


def _n(x: Any) -> int:
    return len(x) if isinstance(x, (list, tuple)) else 0


def _num(v: Any) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


# ------------------------------------------------------------------ structural signals

def _structural(page: dict) -> dict[str, list[tuple[str, float]]]:
    d = page.get("data") or {}
    out: dict[str, list[tuple[str, float]]] = {k: [] for k in RELATIONS}
    effects = [e for e in d.get("effects") or [] if all(_num(e.get(k)) for k in ("est", "lo", "hi"))]
    if effects:
        out["effect_sizes"].append((f"数据：{len(effects)} 行效应量含 95% CI", 2.0 + min(len(effects), 8) * 0.5))
    arms = d.get("arms") or []
    if arms:
        has_n = any(a.get("n") for a in arms)
        w = 1.5 + (1.0 if has_n else 0) + (1.0 if d.get("duration_weeks") or _n(d.get("timepoints")) else 0)
        out["trial_setup"].append((f"数据：{len(arms)} 个治疗臂" + ("（含 n）" if has_n else "")
                                   + ("、有时长/时间点" if w >= 3.5 else ""), w))
    series = [s for s in d.get("series") or [] if _n(s.get("values"))]
    if len(series) >= 2:
        w = 3.0 + (1.0 if d.get("stats") else 0)
        out["arm_readout"].append((f"数据：{len(series)} 组数值序列" + ("+统计框" if d.get("stats") else ""), w))
    table = d.get("table") or {}
    rows, cols = table.get("rows") or [], table.get("columns") or []
    if rows and cols:
        numeric = sum(1 for r in rows for c in (r.get("cells") or []) if _DIGIT.search(str(c)))
        w = min(6.0, 1.0 + numeric / 8)
        out["tabular"].append((f"数据：{len(rows)} 行 × {len(cols)} 列，{numeric} 个数值单元格", w))
    items = [i for i in d.get("timed_items") or [] if _num(i.get("start"))]
    if items:
        groups = {i.get("group") for i in items}
        out["landscape"].append((f"数据：{len(items)} 项研究带年份、{len(groups)} 个分组", 2.0 + min(len(items), 10) * 0.3))
    chain = d.get("chain") or []
    if len(chain) >= 3:
        out["mechanism"].append((f"数据：{len(chain)} 级因果链", 3.0 + (1.0 if d.get("action_points") else 0)))
    axes = d.get("axes") or {}
    if axes:
        tiers = [len(axes.get("x") or []), len(axes.get("y") or [])]
        out["matrix"].append((f"数据：双轴分层 {tiers[0]}×{tiers[1]}", 4.0 if min(tiers) >= 2 else 1.0))
    paths = d.get("paths") or []
    if len(paths) == 2:
        out["dual_path"].append(("数据：2 条平行路径", 4.0))
    conds = d.get("conditions") or []
    if conds:
        out["conditional"].append((f"数据：{len(conds)} 个判定节点（是/否分支）", 4.0))
    sides = d.get("sides") or []
    if len(sides) == 2:
        out["contrast"].append(("数据：A/B 两侧对照", 3.0))
    steps = d.get("steps") or []
    if steps:
        timed = [s for s in steps if s.get("when")]
        if len(timed) >= max(2, len(steps) - 1):
            out["chronology"].append((f"数据：{len(timed)} 个带时间标签的节点", 3.0))
            out["sequence"].append((f"数据：{len(steps)} 个顺序节点", 1.5))
        else:
            out["sequence"].append((f"数据：{len(steps)} 个顺序节点", 3.0))
    tks = [t for t in d.get("takeaways") or [] if _DIGIT.search(str(t.get("value") or ""))]
    if 3 <= len(tks) <= 4:
        verb = all(t.get("quote") and t.get("loc") for t in tks)
        out["takeaways"].append((f"数据：{len(tks)} 条数字开头结论" + ("（带逐字摘录+源位置）" if verb else ""),
                                 4.0 if verb else 1.0))
    if d.get("items"):
        out["points"].append((f"数据：{_n(d.get('items'))} 条并列要点", 1.0))
    return out


# ------------------------------------------------------------------------- classify

@dataclass
class RelationScore:
    relation: str
    score: float
    signals: list[str] = field(default_factory=list)

    @property
    def layout(self) -> str:
        layout = RELATIONS[self.relation][1]
        return layout


def classify(page: dict, signals: dict[str, list[Sig]] | None = None) -> list[RelationScore]:
    """Score every relation for one page; returns relations sorted by score (desc)."""
    signals = TEXT_SIGNALS if signals is None else signals
    text = _text(page)
    struct = _structural(page)
    scores: list[RelationScore] = []
    for rel in RELATIONS:
        rs = RelationScore(rel, 0.0)
        for sig in signals.get(rel, []):
            hits = re.findall(sig.pattern, text, flags=re.IGNORECASE | re.MULTILINE)
            if hits:
                k = min(len(hits), 3)                 # repeated hits count, but saturate
                rs.score += sig.weight * (1 + 0.25 * (k - 1))
                rs.signals.append(f"文本：{sig.name}×{len(hits)}")
        for name, w in struct.get(rel, []):
            rs.score += w
            rs.signals.append(name)
        scores.append(rs)
    # text-only effect rows like "0.58（0.45–0.75）"
    ci_rows = _CI_ROW.findall(text)
    if len(ci_rows) >= 2:
        eff = next(s for s in scores if s.relation == "effect_sizes")
        eff.score += 0.5 * min(len(ci_rows), 6)
        eff.signals.append(f"文本：{len(ci_rows)} 处“估计值（下限–上限）”")
    # time axis → line variant of the endpoint readout
    rd = next(s for s in scores if s.relation == "arm_readout")
    if rd.score and _is_over_time(page):
        rd.signals.append("数据：x 为时间点（→ 折线变体）")
    pts = next(s for s in scores if s.relation == "points")
    pts.score += 0.5
    pts.signals.append("兜底")
    for s in scores:
        s.score = round(s.score, 2)
    return sorted(scores, key=lambda s: (-s.score, list(RELATIONS).index(s.relation)))


def _is_over_time(page: dict) -> bool:
    d = page.get("data") or {}
    x = d.get("x") or []
    return len(x) >= 3 and all(_num(v) for v in x)


def relation_layout(rel: RelationScore, page: dict) -> str:
    if rel.relation == "arm_readout" and _is_over_time(page):
        return "endpoint_readout/line"
    return rel.layout


# ------------------------------------------------------------- minimum data requirements

def _takeaway_rail(d: dict) -> str | None:
    tks = [t for t in d.get("takeaways") or [] if _DIGIT.search(str(t.get("value") or ""))]
    if not 3 <= len(tks) <= 4:
        return f"右栏需要 3–4 条数字开头的要点（现有 {len(tks)} 条）"
    return None


def requirement_gap(layout: str, page: dict) -> str | None:
    """None when the page's own data satisfies *layout*; else a Chinese reason.  Never fabricates."""
    d = page.get("data") or {}
    text = _text(page)
    if layout in ("cover", "section"):
        return None if page.get("title") else "缺标题"
    if layout == "forest_plot":
        rows = [e for e in d.get("effects") or [] if all(_num(e.get(k)) for k in ("est", "lo", "hi"))]
        if len(rows) < 3:
            return f"森林图需要 ≥3 行带 95% CI 的效应量（现有 {len(rows)} 行）"
        if any(not (0 < float(e["lo"]) <= float(e["est"]) <= float(e["hi"])) for e in rows):
            return "效应量须满足 0 < 下限 ≤ 估计值 ≤ 上限"
        return _takeaway_rail(d)
    if layout == "data_table_highlight":
        t = d.get("table") or {}
        rows, cols = t.get("rows") or [], t.get("columns") or []
        if not 1 <= len(cols) <= 4:
            return f"数据表需要 1–4 个数据列（现有 {len(cols)} 列）"
        if len(rows) < 3:
            return f"数据表需要 ≥3 行（模板契约 3–18 行，现有 {len(rows)} 行）"
        if len(rows) > 18:
            return f"数据表超过 18 行（{len(rows)} 行），需拆页"
        if sum(bool(r.get("highlight")) for r in rows) > 1:
            return "数据表至多标出 1 行重点（源文档未指明时不标）"
        return _takeaway_rail(d) if d.get("takeaways") else None
    if layout.startswith("endpoint_readout"):
        series = [s for s in d.get("series") or [] if _n(s.get("values"))]
        if len(series) < 2:
            return f"终点读出需要两组（臂）各自的数值（现有 {len(series)} 组）"
        n = len(d.get("x") or []) if layout.endswith("line") else len(d.get("categories") or [])
        if layout.endswith("line") and not _is_over_time(page):
            return "折线变体需要 ≥3 个数值型时间点"
        if n == 0 or any(len(s["values"]) != n for s in series):
            return "各组数值个数须与类别/时间点一致"
        if not d.get("stats"):
            return "需要统计框（差值 / 95% CI / P 值）"
        return _takeaway_rail(d)
    if layout == "trial_design":
        arms = d.get("arms") or []
        if not 2 <= len(arms) <= 3:
            return f"试验设计需要 2–3 个治疗臂（现有 {len(arms)} 个）"
        if not (any(a.get("n") for a in arms) or d.get("duration_weeks")):
            return "试验设计需要各臂 n 或治疗时长"
        if _n(d.get("timepoints")) < 3:
            return f"试验设计需要 ≥3 个时间点（现有 {_n(d.get('timepoints'))} 个）"
        return _takeaway_rail(d)
    if layout == "landscape_swimlane":
        items = [i for i in d.get("timed_items") or [] if _num(i.get("start")) and _num(i.get("end"))]
        groups = {i.get("group") for i in items}
        if len(items) < 3:
            return f"泳道图需要 ≥3 项带起止年份的研究/药物（现有 {len(items)} 项）"
        if not 2 <= len(groups) <= 6:
            return f"泳道图需要 2–6 个分组（现有 {len(groups)} 个）"
        if any(i.get("status") not in ("met", "not_met", "ongoing") for i in items):
            return "每项研究需要状态（达到/未达到/进行中）"
        return _takeaway_rail(d)
    if layout == "moa_cascade":
        chain = d.get("chain") or []
        if not 3 <= len(chain) <= 6:
            return f"机制级联需要 3–6 级（现有 {len(chain)} 级）"
        return _takeaway_rail(d)
    if layout == "assessment_matrix":
        ax = d.get("axes") or {}
        if len(ax.get("x") or []) < 2 or len(ax.get("y") or []) < 2:
            return "评估矩阵需要 2 个轴且每轴 ≥2 个分层"
        if _n(d.get("cells")) < 3:
            return "评估矩阵需要各格的结论（≥3 格）"
        return None
    if layout == "dual_path_tree":
        paths = d.get("paths") or []
        if len(paths) != 2 or any(_n(p.get("steps")) < 2 for p in paths):
            return "双路径树需要恰好 2 条路径、每条 ≥2 步"
        return None
    if layout == "algorithm_tree":
        conds = d.get("conditions") or []
        if not conds:
            return "决策树需要至少 1 个判定条件及“是/否”两个去向"
        c = conds[0]
        if not (c.get("test") and c.get("yes") and c.get("no")):
            return "判定节点须同时给出条件、“是”去向与“否”去向"
        return None
    if layout == "key_points/evidence_takeaways":
        tks = [t for t in d.get("takeaways") or [] if _DIGIT.search(str(t.get("value") or ""))]
        if not 3 <= len(tks) <= 4:
            return f"证据要点需要 3–4 条数字开头的结论（现有 {len(tks)} 条）"
        if not all(t.get("quote") and t.get("loc") for t in tks):
            return "证据要点每条须带逐字摘录与源位置"
        return None
    if layout == "comparison":
        sides = d.get("sides") or []
        if len(sides) != 2 or any(_n(s.get("items")) < 1 for s in sides):
            return "对照页需要 A/B 两侧各 ≥1 条"
        if any(_n(s.get("items")) > 8 for s in sides):
            return "对照页每侧最多 8 条，需拆页"
        return None
    if layout == "flow":
        steps = d.get("steps") or []
        if not 3 <= len(steps) <= 6:
            return f"流程页需要 3–6 个步骤（现有 {len(steps)} 个）"
        return None
    if layout == "timeline":
        steps = [s for s in d.get("steps") or [] if s.get("when")]
        if not 4 <= len(steps) <= 6:
            return f"时间轴需要 4–6 个带时间标签的节点（现有 {len(steps)} 个）"
        return None
    if layout == "key_points":
        n = _n(d.get("items")) or len([t for t in page.get("text") or [] if str(t).strip()])
        if n < 1:
            return "没有任何可展示的要点"
        if n > 6:
            return f"要点卡片最多 6 条（现有 {n} 条），需拆页"
        return None
    return f"未知版式 {layout}"


# --------------------------------------------------------------------------- tie-break

TieBreaker = Callable[[dict, list[dict]], tuple[str, str]]
"""(page, qualified candidates [{layout, score, relation, signals}]) → (layout id, one-line reason)."""

CLOSE_ABS = 1.0      # top-2 gap ≤ this …
CLOSE_REL = 0.15     # … or ≤ 15 % of the top score → "close"


def scores_close(a: float, b: float) -> bool:
    return (a - b) <= CLOSE_ABS or (a > 0 and (a - b) / a <= CLOSE_REL)


def constrain_choice(answer: Any, candidates: list[str]) -> tuple[str | None, str]:
    """Validate a tie-breaker's raw answer.  Accepts (id, reason) / dict / JSON string.

    Returns (layout id or None when rejected, reason or rejection message)."""
    layout, reason = None, ""
    try:
        if isinstance(answer, str):
            s = answer.strip()
            if s.startswith("```"):
                s = s.split("\n", 1)[-1].rsplit("```", 1)[0]
            answer = json.loads(s)
        if isinstance(answer, dict):
            layout, reason = answer.get("layout"), answer.get("reason", "")
        elif isinstance(answer, (tuple, list)) and len(answer) == 2:
            layout, reason = answer
    except (ValueError, TypeError):
        return None, "输出不是合法 JSON"
    if not isinstance(layout, str) or layout not in candidates:
        return None, f"输出版式 {layout!r} 不在候选集 {candidates} 中"
    reason = " ".join(str(reason or "").split())[:80]
    return layout, reason or "（模型未给理由）"


def llm_prompt(page: dict, cands: list[dict]) -> tuple[str, str]:
    system = ("你只在给定候选版式中选一个最能表达本页逻辑关系的版式。只输出 JSON："
              '{"layout":"<候选 id 之一>","reason":"<一句中文理由>"}。不得输出候选以外的 id，不得改写内容。')
    user = json.dumps({
        "title": page.get("title"), "text": (page.get("text") or [])[:12],
        "candidates": [{"layout": c["layout"], "name": LAYOUTS[c["layout"]][2], "score": c["score"],
                        "signals": c["signals"][:5]} for c in cands],
    }, ensure_ascii=False)
    return system, user


def make_llm_tiebreaker(complete: Callable[[str, str], str]) -> TieBreaker:
    """Wrap any `complete(system, user) -> str` chat function as a tie-breaker."""
    def tb(page: dict, cands: list[dict]) -> tuple[str, str]:
        system, user = llm_prompt(page, cands)
        return complete(system, user)  # type: ignore[return-value]  (validated by constrain_choice)
    tb.method = "llm"  # type: ignore[attr-defined]
    return tb


def env_llm_tiebreaker() -> TieBreaker | None:
    """Optional: reuse the repo's OpenAI-compatible endpoint config (EASYPPT_SEMANTIC_MODEL_*).

    Returns None when no endpoint is configured.  Off by default; enable with --llm."""
    import os
    import urllib.request

    from app.semantic_model import configured_semantic_model   # lazy: app is optional

    model = configured_semantic_model()
    if not model:
        return None

    def complete(system: str, user: str) -> str:
        body = {"model": model["model_id"], "temperature": 0.0,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        headers = {"Content-Type": "application/json"}
        key = os.environ.get("EASYPPT_SEMANTIC_MODEL_API_KEY", "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        req = urllib.request.Request(model["url"], data=json.dumps(body, ensure_ascii=False).encode(),
                                     headers=headers, method="POST")
        import time

        from factdeck.jobstats import record_llm_call
        raw, started = None, time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = json.loads(r.read().decode())
        finally:   # observability: the endpoint's own usage, or unknown — never estimated
            record_llm_call(stage="select", model=model["model_id"], source="selector.tie_break",
                            usage=raw.get("usage") if isinstance(raw, dict) else None,
                            elapsed=time.perf_counter() - started, ok=isinstance(raw, dict))
        content = raw["choices"][0]["message"]["content"]
        return content if isinstance(content, str) else json.dumps(content)

    return make_llm_tiebreaker(complete)


# --------------------------------------------------------------------------- selection

@dataclass
class Decision:
    page_no: int
    page_id: str
    kind: str
    summary: str
    relation: str = ""
    relation_zh: str = ""
    signals: list[str] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    downgrades: list[dict] = field(default_factory=list)
    tie_break: dict | None = None
    rhythm: list[dict] = field(default_factory=list)
    layout: str = ""
    reason_zh: str = ""

    def as_dict(self) -> dict:
        fam, var, name, chart = LAYOUTS[self.layout]
        return {
            "page_no": self.page_no, "page_id": self.page_id, "kind": self.kind, "summary": self.summary,
            "relation": self.relation, "relation_zh": self.relation_zh, "signals": self.signals,
            "candidates": self.candidates, "downgrades": self.downgrades, "tie_break": self.tie_break,
            "rhythm_adjustments": self.rhythm,
            "chosen": {"layout": self.layout, "family": fam, "variant": var, "name_zh": name, "is_chart": chart},
            "reason_zh": self.reason_zh,
        }


def _summary(page: dict, n: int = 30) -> str:
    t = str(page.get("title") or "").strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def candidates_for(page: dict, signals: dict[str, list[Sig]] | None = None) -> tuple[list[RelationScore], list[dict], list[dict], list[dict]]:
    """Classify, then qualify each relation's layout (walking the downgrade chain).

    Returns (relations, qualified candidates sorted by score, rejected candidates, downgrades).
    Downgrades are recorded for relations that carry real weight (≥ 2 and ≥ half the top score)."""
    rels = classify(page, signals)
    top = rels[0].score if rels else 0.0
    best: dict[str, dict] = {}
    rejected: dict[str, dict] = {}
    downgrades: list[dict] = []
    for r in rels:
        if r.score <= 0:
            continue
        significant = r.score >= max(2.0, 0.5 * top)
        layout = origin = relation_layout(r, page)
        score, seen, path, first_gap = r.score, [], [], None
        while layout and layout not in seen:
            seen.append(layout)
            gap = requirement_gap(layout, page)
            if gap is None:
                c = best.get(layout)
                if not c or score > c["score"]:
                    best[layout] = {"layout": layout, "relation": r.relation, "score": round(score, 2),
                                    "signals": r.signals, "qualified": True,
                                    "via": origin if origin != layout else None}
                break
            first_gap = first_gap or gap
            path.append(f"{layout}：{gap}")
            if layout == origin and r.score >= 1.0 and layout not in rejected:
                rejected[layout] = {"layout": layout, "relation": r.relation, "score": r.score,
                                    "qualified": False, "gap": gap}
            layout = DOWNGRADE.get(layout)
            score = score * 0.8                        # a downgraded fit is a weaker fit
        if path and significant:
            final = seen[-1] if requirement_gap(seen[-1], page) is None else None
            downgrades.append({"from": origin, "to": final, "relation": r.relation,
                               "reason": first_gap, "path": path})
    cands = sorted(best.values(), key=lambda c: (-c["score"], list(LAYOUTS).index(c["layout"])))
    rej = [v for k, v in rejected.items() if k not in best]
    return rels, cands, rej, downgrades


def _deterministic(cands: list[dict], prev: str | None, chart_short: bool) -> dict:
    """Highest score; at equal score prefer a layout ≠ previous page, then a chart when short."""
    top = cands[0]["score"]
    tied = [c for c in cands if math.isclose(c["score"], top)]
    tied.sort(key=lambda c: (c["layout"] == prev, not (chart_short and c["layout"] in CHART_LAYOUTS),
                             list(LAYOUTS).index(c["layout"])))
    return tied[0]


def select_deck(pages: list[dict], *, tiebreaker: TieBreaker | None = None,
                chart_ratio: float = 1 / 3, signals: dict[str, list[Sig]] | None = None,
                extra_signals: dict | None = None) -> dict:
    """Select a layout for every page.  Returns {"decisions": [...], "stats": {...}}.

    `extra_signals` = project terms ({relation: [{name, patterns, weight}]}) merged onto the default set."""
    if signals is None and extra_signals:
        signals = load_signals(extra_signals)
    decisions: list[Decision] = []
    pools: list[list[dict]] = []
    prev_layout: str | None = None
    content_total = sum(1 for p in pages if (p.get("kind") or "content") not in EXEMPT_KINDS)
    need_charts = math.ceil(content_total * chart_ratio)
    charts_so_far = 0
    content_seen = 0

    for i, page in enumerate(pages, 1):
        kind = page.get("kind") or "content"
        dec = Decision(i, str(page.get("id") or f"p{i}"), kind, _summary(page))
        if kind in EXEMPT_KINDS:
            dec.layout, dec.relation, dec.relation_zh = kind, kind, LAYOUTS[kind][2]
            dec.reason_zh = f"{LAYOUTS[kind][2]}不参与关系识别与节奏约束"
            dec.candidates = [{"layout": kind, "score": None, "qualified": requirement_gap(kind, page) is None}]
            decisions.append(dec)
            pools.append([])
            continue
        content_seen += 1
        rels, cands, rejected, downs = candidates_for(page, signals)
        top_rel = rels[0]
        dec.relation, dec.relation_zh = top_rel.relation, RELATIONS[top_rel.relation][0]
        dec.signals = top_rel.signals
        dec.downgrades = downs
        dec.candidates = [dict(c, signals=c["signals"][:6]) for c in cands] + rejected
        pools.append(cands)
        if not cands:          # nothing at all qualifies — keep the fallback but say so
            dec.layout = "key_points"
            dec.reason_zh = "无任何版式满足最低数据要求，暂用要点卡片；需人工补充内容"
            decisions.append(dec)
            prev_layout = None
            continue

        pool = list(cands)
        if prev_layout and pool[0]["layout"] == prev_layout:
            if len(pool) > 1:
                dec.rhythm.append({"rule": "no_repeat", "from": prev_layout, "to": pool[1]["layout"],
                                   "reason": f"与上一内容页同为{LAYOUTS[prev_layout][2]}，改用次优合格候选"})
                pool = [c for c in pool if c["layout"] != prev_layout]
            else:
                dec.rhythm.append({"rule": "no_repeat_unresolved", "from": prev_layout, "to": prev_layout,
                                   "reason": "与上一内容页版式相同，但没有其他合格候选，保留（不为换版式而编造数据）"})
        remaining_pages = content_total - content_seen + 1
        chart_short = (need_charts - charts_so_far) >= remaining_pages
        chosen = pool[0]
        if len(pool) > 1 and scores_close(pool[0]["score"], pool[1]["score"]):
            close = [c for c in pool if scores_close(pool[0]["score"], c["score"])]
            ids = [c["layout"] for c in close]
            det = _deterministic(close, prev_layout, chart_short)
            tb = {"between": ids, "method": "deterministic", "choice": det["layout"],
                  "reason": "分数接近，按最高分 + 节奏规则确定"}
            if tiebreaker is not None:
                try:
                    lay, why = constrain_choice(tiebreaker(page, close), ids)
                except Exception as e:  # noqa: BLE001 — any tie-breaker failure falls back
                    lay, why = None, f"调用失败：{type(e).__name__}"
                if lay:
                    det = next(c for c in close if c["layout"] == lay)
                    tb.update(method=getattr(tiebreaker, "method", "custom"), choice=lay, reason=why)
                else:
                    tb.update(rejected=why, reason="外部裁决无效，已回退确定性规则：" + why)
            chosen = det
            dec.tie_break = tb
        dec.layout = chosen["layout"]
        prev_layout = dec.layout
        charts_so_far += dec.layout in CHART_LAYOUTS
        decisions.append(dec)

    # Pass 2 — chart ratio: promote non-chart pages whose qualified pool has a chart layout.
    content_idx = [k for k, d in enumerate(decisions) if d.kind not in EXEMPT_KINDS]
    charts = sum(decisions[k].layout in CHART_LAYOUTS for k in content_idx)
    promotions = []
    if charts < need_charts:
        options = []
        for k in content_idx:
            d = decisions[k]
            if d.layout in CHART_LAYOUTS:
                continue
            cur = next((c["score"] for c in pools[k] if c["layout"] == d.layout), 0)
            for c in pools[k]:
                if c["layout"] in CHART_LAYOUTS:
                    options.append((cur - c["score"], k, c))
                    break
        for loss, k, c in sorted(options, key=lambda o: o[0]):
            if charts >= need_charts:
                break
            nb = [decisions[j].layout for j in _content_neighbours(content_idx, k)]
            if c["layout"] in nb:
                continue
            d = decisions[k]
            d.rhythm.append({"rule": "chart_ratio", "from": d.layout, "to": c["layout"],
                             "reason": f"图表页不足 1/3，改用合格的图表候选（分差 {loss:.1f}）"})
            d.layout = c["layout"]
            charts += 1
            promotions.append(d.page_id)

    for d in decisions:
        if d.kind not in EXEMPT_KINDS and not d.reason_zh:
            d.reason_zh = _reason(d)
    n_content = len(content_idx)
    stats = {
        "pages": len(decisions),
        "content_pages": n_content,
        "chart_pages": charts,
        "chart_ratio": round(charts / n_content, 3) if n_content else 0.0,
        "chart_ratio_target": round(chart_ratio, 3),
        "chart_target_met": charts >= need_charts,
        "repeat_avoided": sum(1 for d in decisions for r in d.rhythm if r["rule"] == "no_repeat"),
        "repeat_unresolved": [d.page_id for d in decisions for r in d.rhythm if r["rule"] == "no_repeat_unresolved"],
        "chart_promotions": promotions,
        "downgraded_pages": [d.page_id for d in decisions if d.downgrades],
        "tie_breaks": [d.page_id for d in decisions if d.tie_break],
        "consecutive_repeats": [decisions[b].page_id for a, b in zip(content_idx, content_idx[1:])
                                if decisions[a].layout == decisions[b].layout],
        "layout_counts": _counts(d.layout for d in decisions),
    }
    return {"decisions": [d.as_dict() for d in decisions], "stats": stats}


def _content_neighbours(content_idx: list[int], k: int) -> list[int]:
    """Previous / next *content* page (cover and section pages are skipped, not separators)."""
    pos = content_idx.index(k)
    return [content_idx[j] for j in (pos - 1, pos + 1) if 0 <= j < len(content_idx)]


def _counts(it) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in it:
        out[x] = out.get(x, 0) + 1
    return out


def _clean_signal(s: str) -> str:
    return re.sub(r"^(文本|数据)：", "", s)


def _reason(d: Decision) -> str:
    name = LAYOUTS[d.layout][2]
    chosen = next((c for c in d.candidates if c["layout"] == d.layout), None)
    rel_zh = RELATIONS[chosen["relation"]][0] if chosen else d.relation_zh
    sig = "、".join(_clean_signal(s) for s in (chosen or {}).get("signals", d.signals)[:2]) or "无强信号"
    parts = [f"内容呈“{rel_zh}”关系（{sig}），用{name}"]
    if chosen and chosen.get("via"):
        parts.append(f"由{LAYOUTS[chosen['via']][2]}降级而来")
    for r in d.rhythm:
        parts.append({"no_repeat": "为避免与上页重复而换用次优候选",
                      "no_repeat_unresolved": "与上页相同但无合格替代，保留",
                      "chart_ratio": "为满足图表页≥1/3而升为图表"}[r["rule"]])
    if d.tie_break and d.tie_break.get("method") != "deterministic":
        parts.append(f"候选接近由{d.tie_break['method']}裁决")
    return "；".join(parts)


# --------------------------------------------------------------------------- report

def report_markdown(result: dict, *, title: str = "版式选择报告") -> str:
    """Chinese explainable report: one table row per page + deck stats."""
    def esc(s: Any) -> str:
        return str(s).replace("|", "／").replace("\n", " ")

    lines = [f"# {title}", "",
             "| 页码 | 内容摘要 | 识别出的关系 | 命中信号 | 候选（分数） | 降级 | 最终版式 | 理由 |",
             "|---|---|---|---|---|---|---|---|"]
    for d in result["decisions"]:
        if d["kind"] in EXEMPT_KINDS:
            lines.append(f"| {d['page_no']} | {esc(d['summary'])} | —（{d['relation_zh']}） | — | — | — | "
                         f"{d['chosen']['name_zh']} `{d['chosen']['layout']}` | {esc(d['reason_zh'])} |")
            continue
        sig = "；".join(_clean_signal(s) for s in d["signals"][:4])
        ok = [c for c in d["candidates"] if c.get("qualified")]
        bad = [c for c in d["candidates"] if not c.get("qualified")]
        cands = "；".join(f"{LAYOUTS[c['layout']][2]} {c['score']}" for c in ok[:4])
        if bad:
            cands += "；不合格：" + "、".join(f"{LAYOUTS[c['layout']][2]} {c['score']}" for c in bad[:3])
        downs = "；".join(f"{LAYOUTS[x['from']][2]}→{LAYOUTS[x['to']][2] if x['to'] else '无'}：{x['reason']}"
                          for x in d["downgrades"]) or "—"
        lines.append(f"| {d['page_no']} | {esc(d['summary'])} | {d['relation_zh']} | {esc(sig)} | {esc(cands)} | "
                     f"{esc(downs)} | **{d['chosen']['name_zh']}** `{d['chosen']['layout']}` | {esc(d['reason_zh'])} |")
    s = result["stats"]
    lines += ["", "## 全篇统计", "",
              f"- 总页数 {s['pages']}，内容页 {s['content_pages']}（封面/章节页不计）",
              f"- 图表页 {s['chart_pages']} / {s['content_pages']} = {s['chart_ratio']:.0%}"
              f"（目标 ≥ {s['chart_ratio_target']:.0%}：{'达到' if s['chart_target_met'] else '未达到'}）",
              f"- 节奏调整：避免相邻重复 {s['repeat_avoided']} 次；为图表比例升级 {len(s['chart_promotions'])} 页"
              + (f"（{', '.join(s['chart_promotions'])}）" if s["chart_promotions"] else ""),
              f"- 发生降级的页：{', '.join(s['downgraded_pages']) or '无'}",
              f"- 分数接近触发裁决的页：{', '.join(s['tie_breaks']) or '无'}",
              f"- 相邻重复残留：{', '.join(s['consecutive_repeats']) or '无'}"
              + (f"（无合格替代：{', '.join(s['repeat_unresolved'])}）" if s["repeat_unresolved"] else ""),
              "- 版式分布：" + "，".join(f"{LAYOUTS[k][2]} ×{v}" for k, v in s["layout_counts"].items())]
    return "\n".join(lines) + "\n"
