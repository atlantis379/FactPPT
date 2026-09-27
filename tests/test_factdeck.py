"""Fast checks for the fact gate and the authored-text lint (no browser needed)."""
from factdeck.facts import Fact, Derivation, verify, critical_tokens
from factdeck.deck import lint_text

UNITS = [
    {"id": "U1", "source_id": "S1", "location": "第7页 表格", "text": "——"},
    {"id": "U2", "source_id": "S1", "location": "第6页 表格", "text": "中国：202415\n美国：201716"},
    {"id": "U3", "source_id": "S2", "location": "第28页", "text": "本瑞利珠单抗治疗12个月，约44~48%的患者实现临床治愈2"},
    {"id": "U4", "source_id": "S3", "location": "第7页", "text": "986"},
    {"id": "U5", "source_id": "S4", "location": "表格", "text": "1,204", "needs_confirmation": True},
    {"id": "U6", "source_id": "S5", "location": "第8页", "text": "外周血\n嗜酸性粒细胞计数\n≥150/μL"},
]


def run(facts, ders=()):
    return verify(list(facts), list(ders), UNITS, {})


def test_number_not_in_quote_is_rejected():
    f = Fact("p", "U1", "——", display="5,348")
    run([f])
    assert f.status == "REJECTED"


def test_narrowed_endpoint_is_rejected():
    f = Fact("a", "U3", "本瑞利珠单抗治疗12个月，约44~48%的患者实现临床治愈", display="约44%–48%患者ACQ-6<1.5")
    run([f])
    assert f.status == "REJECTED"


def test_quote_must_exist_verbatim():
    f = Fact("q", "U3", "约44~48%的患者达到ACQ-6<1.5")
    run([f])
    assert f.status == "REJECTED"


def test_footnote_strip_needs_named_derivation_and_stays_pending():
    bare = Fact("y1", "U2", "中国：202415", display="2024")
    run([bare])
    assert bare.status == "REJECTED"
    d = Derivation("footnote", "角标", "去掉年份后的角标数字", ["y2"])
    f = Fact("y2", "U2", "中国：202415", display="2024", derivation="footnote")
    run([f], [d])
    assert f.status == "ACCEPTED" and f.needs_confirmation


def test_unit_change_is_caught():
    f = Fact("u", "U6", "外周血\n嗜酸性粒细胞计数\n≥150/μL", display="≥150/mL")
    run([f])
    assert f.status == "REJECTED"


def test_cross_source_conflict_and_image_uncertainty():
    a = Fact("t", "U4", "986", entity="奥马珠单抗", attribute="单价", value="986")
    b = Fact("i", "U5", "1,204", entity="奥马珠单抗", attribute="单价", value="1204")
    conflicts = run([a, b])
    assert len(conflicts) == 1 and a.needs_confirmation and b.needs_confirmation


def test_range_forms_are_equivalent():
    assert critical_tokens("约44~48%") == critical_tokens("44%~48%")


def test_authored_text_lint():
    assert lint_text("六种生物制剂中本瑞利珠单抗疗效最好", [])
    assert lint_text("早期启动可降低急性发作72%", [])
    assert lint_text("抗IL-5治疗适合嗜酸性表型", [])
    assert not lint_text("2型炎症：满足任一指标即可判断", ["2型炎症"])
    assert not lint_text("临床治愈：先看定义，再比较数字", [])
