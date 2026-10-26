"""Closed lists for the display fact gate.

Comparison, population, time-window, and quantifier markers are explicit so
dropping one is a named omission. This is not a per-document segmentation
profile, and it does not approve a semantic-graph object.
"""

from __future__ import annotations

# Screen doses and drug names must match one of these names, not a prefix.
DRUGS = (
    "美泊利珠单抗",
    "贝那利珠单抗",
    "瑞利珠单抗",
    "度普利尤单抗",
    "奥马珠单抗",
    "替泽利尤单抗",
    "mepolizumab",
    "benralizumab",
    "reslizumab",
    "dupilumab",
    "omalizumab",
    "tezepelumab",
    "β受体阻断剂",
    "阿司匹林",
    "抗IL-5R",
    "抗IL-4R",
    "抗IL-13",
    "抗IL-5",
    "抗IL-4",
    "抗TSLP",
    "抗IgE",
    "ICS-LABA",
    "LABA",
    "LAMA",
    "ICS",
    "OCS",
)

CONTRAST_PHRASES = (
    "相比",
    "相较",
    "相对于",
    "对比",
    "对照",
    "而不是",
    "而非",
    "然而",
    "但是",
    "高于",
    "低于",
    "优于",
    "劣于",
    "降至",
    "升至",
    "下降",
    "升高",
    "降低",
    "增加",
    "减少",
    "但",
)

POPULATION_PHRASES = (
    "拟诊重度哮喘患者",
    "拟诊轻中度哮喘患者",
    "重度未控制哮喘患者",
    "重度哮喘患者",
    "轻中度哮喘患者",
    "轻中度哮喘",
    "重度哮喘",
    "轻度哮喘",
    "中度哮喘",
    "未控制哮喘",
    "哮喘患者",
    "老年人",
    "孕妇",
    "人群",
    "成人",
    "儿童",
    "患者",
)

QUANTIFIER_PHRASES = (
    "及以上",
    "及以下",
    "至少",
    "超过",
    "大约",
    "高达",
    "以上",
    "以下",
    "左右",
    "中-高剂量",
    "中－高剂量",
    "中—高剂量",
    "高剂量",
    "低剂量",
    "所有",
    "部分",
    "仅",
)

# Longer window first. Overlap resolution keeps the longest match.
TIME_PATTERNS = (
    r"每\s*[0-9０-９]+(?:\.[0-9０-９]+)?\s*个?(?:月|周|天|日|年|小时|分钟)\s*[0-9０-９]+\s*次",
    r"连续\s*[0-9０-９]+(?:\.[0-9０-９]+)?\s*个?(?:月|周|天|日|年|小时|分钟)内?",
    r"每\s*[0-9０-９]+(?:\.[0-9０-９]+)?\s*个?(?:月|周|天|日|年|小时|分钟)内?",
    r"[0-9０-９]+(?:\.[0-9０-９]+)?\s*个?(?:月|周|天|日|年|小时|分钟)内?",
    r"儿童期|成年早期|成年期",
)

# A dose unit is attached only to a contiguous digit run. Longer units first.
DOSE_UNIT_ALTERNATION = (
    r"个细胞/[μµu]L|个/[μµu]L|mg/kg|μg|µg|ug|mg|mL|ml|IU|%|％|"
    r"个月|小时|分钟|岁|周|天|日|月|年|倍"
)

DERIVATIONS = frozenset(
    {
        "DROP_CONTRAST",
        "DROP_POPULATION",
        "DROP_TIME_WINDOW",
        "DROP_QUANTIFIER",
    }
)

DERIVATION_BY_KIND = {
    "contrast": "DROP_CONTRAST",
    "population": "DROP_POPULATION",
    "time_window": "DROP_TIME_WINDOW",
    "quantifier": "DROP_QUANTIFIER",
}

ISSUE_BY_DERIVATION = {
    "DROP_CONTRAST": "CONTRAST_DROPPED",
    "DROP_POPULATION": "POPULATION_CHANGED",
    "DROP_TIME_WINDOW": "TIME_WINDOW_CHANGED",
    "DROP_QUANTIFIER": "MISSING_QUALIFIER",
}
