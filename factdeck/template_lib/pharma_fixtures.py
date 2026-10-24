"""Illustrative COPD fixtures for the pharma chart-led families.

ALL NUMBERS ARE DEMO DATA (示例数据) — not results of any real trial.  Study names
are fictional ("研究药 X", "示例研究 A-1"); layout language only follows public
pharma congress / IR slides (structure only).
"""
from __future__ import annotations

from .pharma import DEMO_NOTE, STRUCT_NOTE

_FOOT = {"data_note": DEMO_NOTE, "source": STRUCT_NOTE}

TRIAL = {
    "id": "ph-trial", "page": "04", "figure": "图 5.1",
    "section": "COPD · 研究设计",
    "title": "52 周双盲设计以急性加重年化率为主要终点，随机 1:1 分配 900 例",
    "subtitle": "示例 III 期研究：在背景三联吸入治疗基础上评估研究药 X（虚构）",
    "design_label": "随机、双盲、安慰剂对照、平行组、多中心 III 期研究（示例）",
    "population": "中重度 COPD 伴 2 型炎症证据（筛选期血 eos ≥ 150 个/µL）",
    "timepoints": [
        {"week": -4, "label": "第 −4 周", "tag": "筛选"},
        {"week": 0, "label": "基线", "tag": "随机化"},
        {"week": 52, "label": "第 52 周", "tag": "治疗结束"},
        {"week": 64, "label": "第 64 周", "tag": "随访结束"},
    ],
    "phases": [
        {"from": -4, "to": 0, "label": "筛选期 4 周"},
        {"from": 0, "to": 52, "label": "治疗期 52 周"},
        {"from": 52, "to": 64, "label": "安全性随访 12 周"},
    ],
    "screen_note": ["导入期", "确认 eos 与加重史", "稳定背景三联"],
    "randomisation": {"week": 0, "ratio": "1:1", "n": "900", "label": "随机化"},
    "treatment_end_week": 52,
    "arms": [
        {"name": "研究药 X 300 mg SC q2w", "detail": "+ 背景 ICS / LABA / LAMA", "n": "450", "role": "active"},
        {"name": "安慰剂 SC q2w", "detail": "+ 背景 ICS / LABA / LAMA", "n": "450", "role": "control"},
    ],
    "inclusion": [
        "40–80 岁；支气管舒张后 FEV1/FVC < 0.70",
        "支气管舒张后 FEV1 占预计值 30%–70%",
        "过去 1 年 ≥ 2 次中度或 ≥ 1 次重度急性加重",
        "筛选期血嗜酸粒细胞 ≥ 150 个/µL",
        "稳定三联吸入治疗 ≥ 3 个月；吸烟史 ≥ 10 包年",
    ],
    "endpoints": [
        {"tier": "主要", "text": "52 周中重度急性加重年化率"},
        {"tier": "关键次要", "text": "第 12 / 52 周支气管舒张前 FEV1 较基线变化"},
        {"tier": "次要", "text": "SGRQ 总分、E-RS:COPD 症状评分变化"},
        {"tier": "安全性", "text": "TEAE、严重不良事件、抗药抗体"},
    ],
    "rail_label": "设计要点",
    "takeaways": [
        {"value": "1:1", "text": "随机分配，按地区与 ICS 剂量分层"},
        {"value": "52 周", "text": "完整覆盖季节周期，保证加重事件率可估计"},
        {"value": "≥ 150", "text": "个/µL 血 eos 入组富集 2 型炎症，按 300 分层"},
        {"value": "12 周", "text": "停药后安全性随访，观察迟发不良事件"},
    ],
    "abbrev": "R = 随机化；SC = 皮下注射；q2w = 每 2 周 1 次；ICS = 吸入糖皮质激素；LABA = 长效 β2 激动剂；LAMA = 长效抗胆碱能药；eos = 血嗜酸粒细胞；SGRQ = 圣乔治呼吸问卷；TEAE = 治疗期间出现的不良事件",
    **_FOOT,
}

FOREST = {
    "id": "ph-forest", "page": "05", "figure": "图 5.2",
    "section": "COPD · 亚组分析",
    "title": "血 eos ≥ 300 个/µL 亚组获益最大：急性加重风险降低 42%",
    "subtitle": "52 周中重度急性加重年化率的亚组率比（研究药 X vs 安慰剂；示例数据）",
    "col_a": "研究药 X", "col_c": "安慰剂", "est_head": "RR",
    "effect_label": "率比（95% CI，对数轴）",
    "favours_left": "倾向研究药 X", "favours_right": "倾向安慰剂",
    "axis": {"min": 0.25, "max": 2.0, "ticks": [0.25, 0.5, 1, 2]},
    "rows": [
        {"label": "总体人群", "overall": True, "n_a": "450", "n_c": "450", "est": 0.70, "lo": 0.58, "hi": 0.84},
        {"label": "基线血嗜酸粒细胞（个/µL）", "kind": "group"},
        {"label": "< 150", "n_a": "96", "n_c": "101", "est": 0.94, "lo": 0.66, "hi": 1.34},
        {"label": "150 – < 300", "n_a": "158", "n_c": "152", "est": 0.79, "lo": 0.60, "hi": 1.04},
        {"label": "≥ 300", "n_a": "196", "n_c": "197", "est": 0.58, "lo": 0.45, "hi": 0.75, "highlight": True},
        {"label": "年龄", "kind": "group"},
        {"label": "< 65 岁", "n_a": "232", "n_c": "228", "est": 0.72, "lo": 0.56, "hi": 0.93},
        {"label": "≥ 65 岁", "n_a": "218", "n_c": "222", "est": 0.68, "lo": 0.52, "hi": 0.89},
        {"label": "吸烟状态", "kind": "group"},
        {"label": "目前吸烟", "n_a": "126", "n_c": "131", "est": 0.76, "lo": 0.54, "hi": 1.07},
        {"label": "既往吸烟", "n_a": "324", "n_c": "319", "est": 0.67, "lo": 0.54, "hi": 0.83},
    ],
    "takeaways": [
        {"value": "0.58", "text": "eos ≥ 300 亚组率比（95% CI 0.45–0.75），风险降低 42%"},
        {"value": "0.94", "text": "eos < 150 亚组 CI 跨越 1，未见明确获益"},
        {"value": "3 层", "text": "eos 越高效应越强，呈梯度趋势（示例交互 P = 0.03）"},
        {"value": "0.68–0.72", "text": "年龄与吸烟分层效应一致，CI 相互重叠"},
    ],
    "abbrev": "RR = 率比（rate ratio）；CI = 置信区间；eos = 血嗜酸粒细胞；n = 各组随机化人数",
    "footnote": "RR < 1 表示研究药 X 组急性加重年化率低于安慰剂；负二项回归，校正地区、ICS 剂量与既往加重次数（示意）。",
    **_FOOT,
}

ENDPOINT_BAR = {
    "id": "ph-endpoint", "page": "06", "figure": "图 5.3",
    "section": "COPD · 主要终点",
    "title": "研究药 X 使 52 周中重度急性加重年化率降低 30%",
    "subtitle": "主要终点：52 周中重度急性加重年化率（意向治疗人群；示例数据）",
    "chart_title": "年化中重度急性加重率",
    "y_label": "次 / 患者·年（95% CI）",
    "categories": ["总体人群（ITT）", "血 eos ≥ 300 个/µL"],
    "series": [
        {"name": "安慰剂", "role": "control", "values": [1.10, 1.30], "lo": [0.96, 1.08], "hi": [1.26, 1.56], "n": ["450", "197"]},
        {"name": "研究药 X 300 mg q2w", "role": "active", "values": [0.77, 0.75], "lo": [0.66, 0.61], "hi": [0.90, 0.92], "n": ["450", "196"]},
    ],
    "annotations": [{"text": "−30%", "sub": "RR 0.70"}, {"text": "−42%", "sub": "RR 0.58"}],
    "stats": {"title": "主要终点 · 52 周", "lines": ["RR 0.70（95% CI 0.58–0.84）", "P < 0.001（负二项回归）"]},
    "takeaways": [
        {"value": "−30%", "text": "ITT 人群中重度急性加重年化率：0.77 vs 1.10 次/年", "refs": ["1"]},
        {"value": "−42%", "text": "eos ≥ 300 亚组：0.75 vs 1.30 次/年", "refs": ["1"]},
        {"value": "0.33", "unit": "次/年", "text": "绝对差值；约每 3 例治疗 1 年少 1 次加重"},
        {"value": "P < 0.001", "text": "主要终点达到预设分层检验第一步"},
    ],
    "refs": [{"id": "1", "text": "示例源文档 A《示例 III 期研究报告》表 3，p. 26（虚构，教学用）"}],
    "abbrev": "ITT = 意向治疗；RR = 率比；CI = 置信区间；q2w = 每 2 周 1 次；eos = 血嗜酸粒细胞",
    **_FOOT,
}

ENDPOINT_LINE = {
    "id": "ph-endpoint-line", "page": "06b", "figure": "图 5.4",
    "section": "COPD · 关键次要终点",
    "title": "研究药 X 第 12 周起改善 FEV1 约 80 mL，获益维持至第 52 周",
    "subtitle": "支气管舒张前 FEV1 较基线 LS 均值变化（mL，±95% CI；示例数据）",
    "chart_title": "支气管舒张前 FEV1 较基线变化",
    "y_label": "LS 均值变化（mL）",
    "x_label": "周",
    "x": [0, 4, 12, 24, 36, 52],
    "series": [
        {"name": "安慰剂", "role": "control", "values": [0, 52, 60, 58, 62, 54],
         "lo": [0, 34, 42, 38, 41, 31], "hi": [0, 70, 78, 78, 83, 77], "n": ["450", "441", "433", "420", "411", "402"]},
        {"name": "研究药 X 300 mg q2w", "short": "研究药 X", "role": "active", "values": [0, 128, 142, 136, 146, 138],
         "lo": [0, 110, 124, 116, 125, 115], "hi": [0, 146, 160, 156, 167, 161], "n": ["450", "444", "437", "427", "419", "410"]},
    ],
    "stats": {"title": "LS 均值差（95% CI）", "lines": ["第 12 周：82 mL（57–107），P < 0.001", "第 52 周：84 mL（52–116），P < 0.001"]},
    "takeaways": [
        {"value": "82", "unit": "mL", "text": "第 12 周 FEV1 组间差值，首个评估点即显现"},
        {"value": "84", "unit": "mL", "text": "第 52 周差值，与第 12 周相当，获益未衰减"},
        {"value": "4 周", "text": "两组曲线自第 4 周起分离，CI 不再重叠"},
    ],
    "abbrev": "FEV1 = 第 1 秒用力呼气容积；LS = 最小二乘；CI = 置信区间；MMRM = 重复测量混合模型",
    "footnote": "MMRM 分析，校正基线 FEV1、地区与 ICS 剂量；图下为各时间点有观测值的人数（示意）。",
    **_FOOT,
}

MOA = {
    "id": "ph-moa", "page": "07", "figure": "图 5.5",
    "section": "COPD · 作用机制",
    "title": "2 型炎症级联有 4 个可干预节点：上游警报素与下游细胞因子",
    "subtitle": "暴露 → 上皮警报素 → 2 型细胞因子 → 效应细胞 → 临床结局；金色框为生物制剂作用点（结构示意）",
    "stages": [
        {"label": "暴露 / 触发", "items": [
            {"id": "smoke", "label": "吸烟 / 生物燃料", "sub": "慢性氧化应激"},
            {"id": "pollut", "label": "空气污染颗粒物"},
            {"id": "virus", "label": "病毒 / 细菌感染", "sub": "急性加重常见诱因"}]},
        {"label": "上皮警报素", "items": [
            {"id": "il33", "label": "IL-33", "sub": "上皮损伤释放"},
            {"id": "tslp", "label": "TSLP", "sub": "上皮源性"},
            {"id": "il25", "label": "IL-25"}]},
        {"label": "2 型细胞因子", "items": [
            {"id": "il4", "label": "IL-4 / IL-13", "sub": "共用 IL-4Rα"},
            {"id": "il5", "label": "IL-5", "sub": "嗜酸粒细胞存活"},
            {"id": "ilc2", "label": "Th2 / ILC2 活化", "sub": "细胞因子来源"}]},
        {"label": "效应细胞 / 组织", "items": [
            {"id": "eos", "label": "嗜酸粒细胞浸润"},
            {"id": "goblet", "label": "杯状细胞化生", "sub": "黏液高分泌"},
            {"id": "mast", "label": "肥大细胞脱颗粒"},
            {"id": "sm", "label": "气道平滑肌收缩"}]},
        {"label": "临床结局", "items": [
            {"id": "exa", "label": "中重度急性加重"},
            {"id": "fev1", "label": "FEV1 加速下降"},
            {"id": "remod", "label": "气道重塑"},
            {"id": "sx", "label": "症状负担 / 生活质量"}]},
    ],
    "callouts": [
        {"key": "A", "label": "抗 TSLP 单抗", "sub": "阻断上游警报素", "target": "tslp"},
        {"key": "B", "label": "抗 IL-33 / ST2", "sub": "阻断警报素信号", "target": "il33"},
        {"key": "C", "label": "抗 IL-4Rα 单抗", "sub": "同时阻断 IL-4 / IL-13", "target": "il4"},
        {"key": "D", "label": "抗 IL-5 / IL-5Rα", "sub": "减少嗜酸粒细胞", "target": "il5"},
    ],
    "phenotype_note": "表型标志：血 eos ≥ 300 个/µL、FeNO 升高提示 2 型炎症主导（阈值为示例）",
    "takeaways": [
        {"value": "4 个", "text": "可干预节点：TSLP、IL-33、IL-4Rα 与 IL-5 通路"},
        {"value": "2 层", "text": "上游警报素阻断范围更广；下游细胞因子阻断更聚焦"},
        {"value": "≥ 300", "unit": "个/µL", "text": "血 eos 是选择下游靶点人群的常用标志（示例阈值）"},
    ],
    "abbrev": "TSLP = 胸腺基质淋巴细胞生成素；ST2 = IL-33 受体；IL-4Rα = IL-4 受体 α 链；ILC2 = 2 型固有淋巴细胞；FeNO = 呼出气一氧化氮",
    "footnote": "⊣ 表示药物抑制作用点；箭头表示通路激活方向。仅为结构化机制示意，不代表疗效比较。",
    **_FOOT,
}

TABLE = {
    "id": "ph-table", "page": "08", "figure": "表 5.1",
    "section": "COPD · 基线特征",
    "title": "两组基线特征均衡：44% 患者血 eos ≥ 300 个/µL，加重负担相近",
    "subtitle": "随机化人群基线人口学与疾病特征（示例数据）",
    "stub_head": "特征",
    "columns": [{"label": "研究药 X", "sub": "n = 450"}, {"label": "安慰剂", "sub": "n = 450"}, {"label": "合计", "sub": "N = 900"}],
    "rows": [
        {"label": "人口学", "kind": "group"},
        {"label": "年龄，岁，均值（SD）", "cells": ["65.2（8.1）", "65.6（7.9）", "65.4（8.0）"]},
        {"label": "男性，n（%）", "mark": "a", "cells": ["306（68.0）", "300（66.7）", "606（67.3）"]},
        {"label": "BMI，kg/m²，均值（SD）", "cells": ["25.8（4.6）", "26.1（4.9）", "26.0（4.8）"]},
        {"label": "目前吸烟，n（%）", "cells": ["126（28.0）", "131（29.1）", "257（28.6）"]},
        {"label": "吸烟量，包年，均值（SD）", "cells": ["38.4（18.2）", "39.1（19.0）", "38.8（18.6）"]},
        {"label": "疾病特征", "kind": "group"},
        {"label": "支气管舒张后 FEV1，L，均值（SD）", "cells": ["1.38（0.46）", "1.36（0.47）", "1.37（0.46）"]},
        {"label": "FEV1 占预计值 %，均值（SD）", "cells": ["50.4（12.6）", "49.8（13.0）", "50.1（12.8）"]},
        {"label": "过去 1 年中重度加重，次，均值", "cells": ["2.3", "2.2", "2.3"]},
        {"label": "过去 1 年 ≥ 1 次住院，n（%）", "cells": ["117（26.0）", "112（24.9）", "229（25.4）"]},
        {"label": "血 eos ≥ 300 个/µL，n（%）", "cells": ["196（43.6）", "197（43.8）", "393（43.7）"], "highlight": True, "mark": "b"},
        {"label": "血 eos，个/µL，中位数（IQR）", "cells": ["280（190–410）", "275（185–400）", "278（188–405）"]},
        {"label": "CAT 总分，均值（SD）", "cells": ["20.1（6.4）", "20.4（6.2）", "20.3（6.3）"]},
        {"label": "背景三联（ICS/LABA/LAMA），n（%）", "cells": ["441（98.0）", "443（98.4）", "884（98.2）"]},
    ],
    "footnotes": [
        "百分比以各组随机化人数为分母；连续变量报告均值（SD）或中位数（IQR）。",
        "血 eos 为筛选期与基线两次测定中的较高值（示意定义）。",
    ],
    "takeaways": [
        {"value": "44%", "text": "血 eos ≥ 300 个/µL，两组 43.6% vs 43.8%"},
        {"value": "2.3", "unit": "次", "text": "既往 1 年平均中重度加重，属高加重负担人群"},
        {"value": "50%", "text": "FEV1 占预计值均值约 50%，以中重度气流受限为主"},
        {"value": "98%", "text": "接受背景三联吸入治疗，便于评估加用获益"},
    ],
    "abbrev": "SD = 标准差；IQR = 四分位距；BMI = 体重指数；FEV1 = 第 1 秒用力呼气容积；eos = 血嗜酸粒细胞；CAT = COPD 评估测试",
    **_FOOT,
}

SWIM = {
    "id": "ph-swim", "page": "09", "figure": "图 5.6",
    "section": "COPD · 研究格局",
    "title": "10 项 III 期研究已读出 6 项，其中 3 项达到主要终点",
    "subtitle": "COPD 2 型炎症靶点 III 期研究时间线（研究名与结果均为虚构示例）",
    "year_start": 2019, "year_end": 2029, "today": 2026.8, "today_label": "当前",
    "lanes": [
        {"label": "抗 IL-4Rα", "sub": "单抗 · q2w", "focus": True, "studies": [
            {"name": "示例研究 A-1", "start": 2019.4, "end": 2023.2, "status": "met", "result": "RR 0.70", "note": "eos ≥ 150，n = 900"},
            {"name": "示例研究 A-2", "start": 2020.3, "end": 2024.4, "status": "met", "result": "RR 0.66", "note": "eos ≥ 300，n = 930"}]},
        {"label": "抗 IL-5", "sub": "单抗 · q4w", "studies": [
            {"name": "示例研究 B-1", "start": 2019.0, "end": 2022.5, "status": "not_met", "result": "RR 0.86", "note": "eos ≥ 150，n = 830"},
            {"name": "示例研究 B-2", "start": 2023.0, "end": 2027.4, "status": "ongoing", "result": "2027", "note": "eos ≥ 300，n ≈ 800"}]},
        {"label": "抗 IL-5Rα", "sub": "单抗 · q8w", "studies": [
            {"name": "示例研究 C-1", "start": 2019.3, "end": 2023.0, "status": "not_met", "result": "RR 0.83", "note": "eos ≥ 220，n = 1 100"}]},
        {"label": "抗 IL-33 / ST2", "sub": "单抗 · q4w", "studies": [
            {"name": "示例研究 D-1", "start": 2021.2, "end": 2025.4, "status": "met", "result": "RR 0.75", "note": "既往吸烟，n = 860"},
            {"name": "示例研究 D-2", "start": 2021.6, "end": 2025.6, "status": "not_met", "result": "RR 0.92", "note": "既往吸烟，n = 870"},
            {"name": "示例研究 D-3", "start": 2024.0, "end": 2027.8, "status": "ongoing", "result": "2027", "note": "目前吸烟者，n ≈ 900"}]},
        {"label": "抗 TSLP", "sub": "单抗 · q4w", "studies": [
            {"name": "示例研究 E-1", "start": 2023.6, "end": 2027.6, "status": "ongoing", "result": "2027", "note": "不限 eos，n ≈ 1 000"},
            {"name": "示例研究 E-2", "start": 2024.2, "end": 2028.0, "status": "ongoing", "result": "2028", "note": "eos ≥ 150，n ≈ 950"}]},
    ],
    "takeaways": [
        {"value": "3 / 6", "text": "已读出 6 项中 3 项达到主要终点（示例）"},
        {"value": "≥ 150", "unit": "个/µL", "text": "达到终点的下游靶点研究均设血 eos 入组门槛"},
        {"value": "4 项", "text": "进行中研究预计 2027–2028 年读出，集中于上游靶点"},
    ],
    "abbrev": "q2w / q4w / q8w = 每 2 / 4 / 8 周给药；RR = 主要终点急性加重率比；eos = 血嗜酸粒细胞（个/µL）",
    "footnote": "条形起点 = 首例入组，终点 = 主要终点读出（进行中为预计）；结果标记同时以形状与文字编码。",
    **_FOOT,
}

EVIDENCE = {
    "id": "ph-evidence", "page": "10", "figure": "要点 5.7",
    "section": "COPD · 本节小结",
    "title": "加重 −30%、FEV1 +82 mL：eos ≥ 300 人群获益最大",
    "subtitle": "每条结论均带证据号，指向源文档页码与逐字摘录（FactPPT 逐字溯源）",
    "items": [
        {"value": "−30%", "text": "研究药 X 使 52 周中重度急性加重年化率降低 30%（0.77 vs 1.10 次/年）",
         "refs": ["1"], "quote": "“…年化率为 0.77 vs 1.10（RR 0.70，95% CI 0.58–0.84；P < 0.001）…”", "loc": "源文档 A · 表 3 · p. 26"},
        {"value": "+82", "unit": "mL", "text": "第 12 周支气管舒张前 FEV1 组间差值 82 mL，第 52 周维持 84 mL",
         "refs": ["1"], "quote": "“…LS 均值差 82 mL（95% CI 57–107）…第 52 周为 84 mL…”", "loc": "源文档 A · 图 4 · p. 29"},
        {"value": "0.58", "text": "血 eos ≥ 300 个/µL 亚组率比最低，提示表型分层的重要性",
         "refs": ["1", "2"], "quote": "“…≥ 300 cells/µL 亚组 RR 0.58（0.45–0.75）…”", "loc": "源文档 A · 图 6 · p. 33；源文档 B · p. 7"},
        {"value": "12.1%", "text": "两组 TEAE 导致停药比例相近（12.1% vs 11.8%），未见新安全信号",
         "refs": ["3"], "quote": "“…导致停药的 TEAE：12.1% vs 11.8%…”", "loc": "源文档 C · 表 5 · p. 41"},
    ],
    "refs": [
        {"id": "1", "text": "示例源文档 A《示例 III 期研究报告》（虚构）"},
        {"id": "2", "text": "示例源文档 B《亚组分析附录》（虚构）"},
        {"id": "3", "text": "示例源文档 C《安全性汇总》（虚构）"},
    ],
    "abbrev": "RR = 率比；CI = 置信区间；LS = 最小二乘；TEAE = 治疗期间出现的不良事件；eos = 血嗜酸粒细胞",
    **_FOOT,
}

PAGES = [
    ("04-trial-design", "trial_design", None, TRIAL),
    ("05-forest-plot", "forest_plot", None, FOREST),
    ("06-endpoint-readout", "endpoint_readout", "bar", ENDPOINT_BAR),
    ("06b-endpoint-readout-line", "endpoint_readout", "line", ENDPOINT_LINE),
    ("07-moa-cascade", "moa_cascade", None, MOA),
    ("08-data-table", "data_table_highlight", None, TABLE),
    ("09-landscape-swimlane", "landscape_swimlane", None, SWIM),
    ("10-evidence-takeaways", "key_points", "evidence_takeaways", EVIDENCE),
]
