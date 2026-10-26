"""Preview copy taken from the biologics sample deck. No new clinical claims.

Axis labels on the matrix fixture are the relation supplied to the selector.
Cell sentences are the sample's own checklist items.
"""

from __future__ import annotations

SOURCE = "重度哮喘识别与生物制剂选择-国家质控中心培训"
SOURCE_GUIDE = "重度哮喘识别与生物制剂选择-国家质控中心培训；指南解读：重度哮喘精准诊治与生物制剂启用时机"
SOURCE_HT = "HT幻灯（解说词）靶向抗炎时代：哮喘合并慢阻肺"


def preview_slides() -> list[dict]:
    return [
        burden_slide(),
        review_slide(),
        claim_slide(),
        matrix_slide(),
        pathway_slide(),
        overlap_slide(),
    ]


def burden_slide() -> dict:
    """Sample slide 04. Five parallel points, one of them the 3–10% figure."""
    return {
        "preview_id": "metric-row",
        "role": "body",
        "kicker": "临床应用",
        "title": "疾病负担",
        "page": "04",
        "relation": "并列要点（兜底）",
        "proposed": "key_points",
        "source": SOURCE_GUIDE,
        "items": [
            {
                "id": "confirm",
                "title": "拟诊后的确诊情况",
                "body": "真实世界研究显示拟诊重度哮喘患者中约50%得到确诊，诊断重度哮喘前应进行系统评估",
            },
            {"id": "share", "title": "重度哮喘占比", "body": "3-10%"},
            {"id": "define", "title": "全球患病占比定义", "body": "重度哮喘全球占比"},
            {"id": "burden", "title": "疾病负担", "body": "相比轻中度哮喘，重度哮喘患者疾病负担重"},
            {
                "id": "life",
                "title": "生活影响",
                "body": "重度未控制哮喘患者面临更高的呼吸急促、活动受限、紧急使用吸入性药物和夜间憋醒风险",
            },
        ],
    }


def review_slide() -> dict:
    """Sample slide 14. Six management actions, previously six equal cards."""
    return {
        "preview_id": "checklist",
        "role": "body",
        "kicker": "临床应用",
        "title": "回顾并优化管理",
        "page": "14",
        "relation": "并列要点（兜底）",
        "proposed": "key_points",
        "source": SOURCE + "；HT幻灯（解说词）靶向抗炎时代：哮喘合并慢阻肺",
        "items": [
            {
                "id": "plan",
                "title": "行动计划",
                "body": "确认患者拥有（并知道如何使用）个性化的书面或电子哮喘行动计划",
            },
            {
                "id": "device",
                "title": "装置技术与方案调整",
                "body": "每次就诊时检查吸入装置使用技术，如果可行，可切换到MART",
            },
            {
                "id": "life",
                "title": "生活方式管理",
                "body": "例如戒烟、锻炼、健康饮食、减重等；接种流感、呼吸道合胞病毒等；采取过敏原规避措施",
            },
            {
                "id": "risk",
                "title": "加重风险药物",
                "body": "避免使用会加重哮喘的药物，如β受体阻断剂（含滴眼制剂）、存在阿司匹林诱发呼吸道疾病的患者",
            },
            {"id": "add", "title": "附加吸入治疗", "body": "如LABA、LAMA等"},
            {
                "id": "standard",
                "title": "持续治疗标准",
                "body": "指连续3个月及以上规范使用中-高剂量ICS-LABA治疗方案并且针对共患疾病和环境因素等",
            },
        ],
    }


def claim_slide() -> dict:
    """Slide 04 sentences split into the claim and the study sentence already beside it."""
    return {
        "preview_id": "claim-evidence",
        "role": "body",
        "kicker": "临床应用",
        "title": "拟诊后的确诊情况",
        "page": "04",
        "relation": "claim_evidence",
        "proposed": "key_points",
        "source": SOURCE_GUIDE,
        "items": [
            {
                "id": "confirm",
                "title": "拟诊后的确诊情况",
                "body": "诊断重度哮喘前应进行系统评估",
                "evidence": "真实世界研究显示拟诊重度哮喘患者中约50%得到确诊",
            },
            {"id": "share", "title": "重度哮喘占比", "body": "3-10%"},
            {"id": "burden", "title": "疾病负担", "body": "相比轻中度哮喘，重度哮喘患者疾病负担重"},
            {
                "id": "life",
                "title": "生活影响",
                "body": "重度未控制哮喘患者面临更高的呼吸急促、活动受限、紧急使用吸入性药物和夜间憋醒风险",
            },
        ],
    }


def matrix_slide() -> dict:
    """Four actions from slide 14. Axis names are selector input, not a new claim."""
    return {
        "preview_id": "matrix-2x2",
        "role": "body",
        "kicker": "临床应用",
        "title": "回顾并优化管理",
        "page": "14",
        "relation": "matrix",
        "proposed": "key_points",
        "source": SOURCE,
        "axes": {"rows": ["患者", "治疗"], "cols": ["执行", "规避"]},
        "items": [
            {
                "id": "plan",
                "title": "行动计划",
                "body": "确认患者拥有（并知道如何使用）个性化的书面或电子哮喘行动计划",
            },
            {
                "id": "life",
                "title": "生活方式管理",
                "body": "例如戒烟、锻炼、健康饮食、减重等；接种流感、呼吸道合胞病毒等；采取过敏原规避措施",
            },
            {
                "id": "device",
                "title": "装置技术与方案调整",
                "body": "每次就诊时检查吸入装置使用技术，如果可行，可切换到MART",
            },
            {
                "id": "risk",
                "title": "加重风险药物",
                "body": "避免使用会加重哮喘的药物，如β受体阻断剂（含滴眼制剂）、存在阿司匹林诱发呼吸道疾病的患者",
            },
        ],
    }


def pathway_slide() -> dict:
    """Sample slide 21. One threshold, yes/no branches."""
    return {
        "preview_id": "algorithm-tree",
        "role": "body",
        "kicker": "临床应用",
        "title": "选择路径：按血嗜酸性粒细胞分层",
        "figure": "图 21",
        "page": "21",
        "relation": "条件/阈值判断",
        "proposed": "algorithm_tree",
        "source": SOURCE,
        "nodes": [
            {"id": "start", "type": "start", "title": "重度哮喘 (无OCS使用)"},
            {
                "id": "decision",
                "type": "decision",
                "title": "血液分层",
                "lines": ["血EOS＞1500 个细胞/μL"],
            },
            {
                "id": "workup",
                "type": "exclude",
                "title": "异常计数排查",
                "body": "排除寄生虫感染、血液病和其他EOS过多的情况",
            },
            {"id": "target", "type": "action", "title": "靶向方案", "body": "抗IL-5 抗IL-5R"},
            {
                "id": "other",
                "type": "action",
                "title": "其他分层",
                "lines": ["血EOS＜150 个细胞/μL", "150≤血EOS＜1500个细胞/μL"],
            },
        ],
        "edges": [
            {"from": "start", "to": "decision"},
            {"from": "decision", "to": "workup", "label": "是"},
            {"from": "workup", "to": "target"},
            {"from": "decision", "to": "other", "label": "否"},
        ],
    }


def overlap_slide() -> dict:
    """Sample slide 36. Asthma vs COPD vs overlap."""
    return {
        "preview_id": "data-table",
        "role": "body",
        "kicker": "临床应用",
        "title": "哮喘合并慢阻肺病的特征",
        "figure": "图 36",
        "page": "36",
        "relation": "多行×多列数据",
        "proposed": "data_table_highlight",
        "source": SOURCE_HT,
        "table": {
            "columns": ["项目", "哮喘", "慢阻肺病", "哮喘-慢阻肺病"],
            "widths": ["16%", "27%", "28%", "29%"],
            "highlight_columns": [3],
            "caption": "逐字引自原文，溯源见备注",
            "rows": [
                {
                    "label": "发病年龄",
                    "cells": ["通常在儿童期", "通常 >40岁", "通常 ≥40岁，但可能在成年早期或儿童期已有症状"],
                },
                {
                    "label": "呼吸系统症状模式",
                    "cells": [
                        "随时间变化，常由过敏原、运动或情绪触发",
                        "慢性，通常持续存在，尤其在运动时",
                        "症状持续但可能表现出变异性",
                    ],
                },
                {
                    "label": "肺功能",
                    "cells": [
                        "当前和 / 或既往存在可逆的气流受限",
                        "持续存在气流受限 (支气管扩张剂后FEV₁/FVC < 0.70)",
                        "气流受限不完全可逆，但常具有变异性",
                    ],
                },
                {
                    "label": "病史",
                    "cells": [
                        "有过敏史、个人或家族哮喘史",
                        "有害颗粒/气体（主要是烟草烟雾和生物质燃料）",
                        "常见个人或家族哮喘和过敏史，以及有害物质暴露史（如烟草烟雾）",
                    ],
                },
                {
                    "label": "病程",
                    "cells": ["治疗后或自发性改善", "治疗后仍缓慢进展", "治疗可显著改善症状，病情通常进展且需要高强度治疗"],
                },
                {"label": "胸部X光", "cells": ["通常正常", "严重过度充气及其他改变", "类似慢阻肺病"]},
                {
                    "label": "气道炎症",
                    "cells": [
                        "以嗜酸性粒细胞±中性粒细胞为特征",
                        "痰中以中性粒细胞±嗜酸性粒细胞为特征，可能有系统性炎症",
                        "痰中以嗜酸性粒细胞±中性粒细胞为特征",
                    ],
                },
            ],
        },
    }
