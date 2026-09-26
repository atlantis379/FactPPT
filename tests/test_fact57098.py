"""Protocol fixtures only: these PNGs are NOT actual model generation evidence."""
import copy
import io
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image

from app.fact57098 import Store, WorkflowError, digest, input_hash, sha, units, now, extract_document


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "isolated-data")


def create_read(store, count=1):
    w = store.create("临时协议验收（非医学课件）", "教学条目一\n教学条目二", {"language": "zh-CN", "duration_minutes": 45})
    for i in range(count):
        store.add_source(w["id"], f"source{i}.txt", f"测试全文第{i}份：保留来源和限定条件。".encode())
    store.queue(w["id"], "READ_SOURCE")
    for i in range(count):
        task = store.claim(w["id"], "test-reader")
        assert task and task["kind"] == "READ_SOURCE"
        result = copy.deepcopy(task["brief"]["result_contract"])
        for row in result["units"]:
            row.update(visual_inspected=True)
        store.complete(w["id"], task["id"], task["lease_token"], result)
    return store.get(w["id"])


def summary_result(w):
    return {"schema_version": "full_source_summary.v2", "input_sha256": input_hash(w),
            "overall_summary": "这是仅供程序验收的全文总结，不包含真实医学结论。它登记所有测试资料和教学条目，用于检查版本门禁。",
            "sections": [{"id": "section_1", "title": "测试章节", "summary": "本章节覆盖全部测试资料的来源单元与教学条目，专门用于验证来源绑定和确认流程。", "source_unit_ids": list(units(w))}],
            "outline_coverage": [{"outline_id": o["id"], "section_ids": ["section_1"]} for o in w["outline"]], "pending_issues": []}


def approve(store, w, kind):
    return store.approval(w["id"], kind, {"customer": "TEST-FIXTURE-CUSTOMER", "operator": "TEST-OPERATOR", "method": "AUTOMATED_PROTOCOL_TEST_NOT_REAL_APPROVAL", "subject_sha256": w["approval_subjects"][kind]})


def confirmed(store):
    w = create_read(store, 2)
    store.queue(w["id"], "SUMMARY")
    t = store.claim(w["id"], "test-author")
    store.complete(w["id"], t["id"], t["lease_token"], summary_result(w))
    return approve(store, store.get(w["id"]), "content")


def plan_result(w, count):
    return {"summary_sha256": digest(w["summary"]), "pages": [
        {"id": f"page_{i}", "title": f"测试页{i}", "locked_text": f"仅供程序验收的锁定正文，第{i}页，数值{i+1}；非真实医学内容。",
         "source_unit_ids": list(units(w)), "outline_ids": [o["id"] for o in w["outline"]] if i == 0 else [],
         "layout": "测试布局", "visual_strategy": "测试图形，不代表医学关系", "placement": "BODY", "critical_terms": [str(i+1)]} for i in range(count)]}


def planned(store, count=7):
    w = confirmed(store)
    store.queue(w["id"], "PAGE_PLAN")
    t = store.claim(w["id"], "test-author")
    return store.complete(w["id"], t["id"], t["lease_token"], plan_result(w, count))


def png(index):
    # Deliberately programmatic test fixture in isolated data; never preinstalled or delivered.
    b = io.BytesIO()
    Image.new("RGB", (1280, 720), (index % 255, (index*3) % 255, 120)).save(b, "PNG")
    return b.getvalue()


def receipt(task, content):
    return {"provider": "OpenAI", "engine": "image_gen", "tool_call_id": "TEST-FIXTURE-NOT-ACTUAL-IMAGEGEN-" + task["id"],
            "generated_at": now(), "image_sha256": sha(content), "contract_sha256": task["input_sha256"],
            "preliminary_qa": {"status": "TEST_FIXTURE", "issues": []}}


def finish_image(store, w, index):
    t = store.claim(w["id"], "test-image-worker", "IMAGE")
    assert t
    content = png(index)
    store.image_result(w["id"], t["id"], t["lease_token"], content, receipt(t, content))
    w = store.get(w["id"])
    p = next(p for p in w["pages"] if p["id"] == t["binding"])
    return store.review(w["id"], p["id"], {"reviewer": "TEST-FIXTURE-NOT-MEDICAL-REVIEW", "image_sha256": p["image"]["sha256"], "exact_text_checked": True, "visual_status": "PASS", "medical_status": "PASS"})


def ready(store, count=7):
    w = planned(store, count)
    store.queue(w["id"], "IMAGE")
    for i in range(min(5,count)):
        w = finish_image(store, w, i)
    w = approve(store, w, "style")
    index = 5
    while any(not p["image"] for p in w["pages"]):
        store.queue(w["id"], "IMAGE")
        remaining = min(5, sum(not p["image"] for p in w["pages"]))
        for _ in range(remaining):
            w = finish_image(store, w, index)
            index += 1
    assert w["stage"] == "READY_TO_EXPORT"
    return w


def test_empty_and_content_gate(store):
    assert store.list() == []
    w = store.create("空项目", "")
    for kind in ("SUMMARY", "PAGE_PLAN", "IMAGE"):
        with pytest.raises(WorkflowError): store.queue(w["id"], kind)
    with pytest.raises(WorkflowError): store.export(w["id"])
    assert store.get(w["id"])["stage"] == "READING_REQUIRED"


def test_full_read_and_outline_coverage(store):
    w = create_read(store, 3)
    assert w["stage"] == "SUMMARY_REQUIRED"
    broken = summary_result(w)
    broken["sections"][0]["source_unit_ids"].pop()
    with store.transaction(w["id"], "TEST") as state:
        with pytest.raises(WorkflowError): store.accept_summary(state, broken)
    broken = summary_result(w)
    broken["outline_coverage"] = []
    with store.transaction(w["id"], "TEST") as state:
        with pytest.raises(WorkflowError): store.accept_summary(state, broken)


def test_sample_gate_and_small_deck(store):
    w = planned(store, 7)
    with pytest.raises(WorkflowError): store.queue(w["id"], "IMAGE", ["page_6"])
    store.queue(w["id"], "IMAGE")
    assert len([t for t in store.get(w["id"])["tasks"] if t["kind"] == "IMAGE"]) == 5
    with pytest.raises(WorkflowError): approve(store, store.get(w["id"]), "style")
    w2 = ready(store, 2)
    assert len(w2["pages"]) == 2
    assert w2["style_approval"]


def test_atomic_claim_resume_and_attempts(store):
    w = planned(store, 7)
    store.queue(w["id"], "IMAGE")
    store.queue(w["id"], "IMAGE")
    with ThreadPoolExecutor(max_workers=8) as pool:
        claimed = list(pool.map(lambda i: store.claim(w["id"], f"worker-{i}", "IMAGE"), range(8)))
    claimed = [t for t in claimed if t]
    assert len(claimed) == 5
    assert len({t["id"] for t in claimed}) == 5
    reopened = Store(store.root)
    assert reopened.get(w["id"])["tasks"][-1]["status"] == "RUNNING"
    t = claimed[0]
    for attempt in range(3):
        reopened.fail(w["id"], t["id"], t["lease_token"], "fixture failure")
        if attempt < 2:
            t = reopened.claim(w["id"], "worker-retry", "IMAGE")
    failed = next(t for t in reopened.get(w["id"])["tasks"] if t["status"] == "FAILED")
    assert failed["attempts"] == 3
    assert reopened.claim(w["id"], "worker-extra", "IMAGE") is None


def test_invalid_receipt_and_unreviewed_export(store):
    w = planned(store, 1)
    store.queue(w["id"], "IMAGE")
    t = store.claim(w["id"], "fixture")
    content = png(1)
    bad = receipt(t, content)
    bad["tool_call_id"] = ""
    with pytest.raises(WorkflowError): store.image_result(w["id"], t["id"], t["lease_token"], content, bad)
    bad = receipt(t, content)
    bad["image_sha256"] = "0"*64
    with pytest.raises(WorkflowError): store.image_result(w["id"], t["id"], t["lease_token"], content, bad)
    store.image_result(w["id"], t["id"], t["lease_token"], content, receipt(t, content))
    with pytest.raises(WorkflowError): store.export(w["id"])


def test_replacement_invalidates_review_and_sample_approval(store):
    w = ready(store, 7)
    old_hash = w["pages"][0]["image"]["sha256"]
    w = store.queue(w["id"], "IMAGE", ["page_0"])
    assert w["style_approval"] is None
    assert w["pages"][0]["review"] is None
    t = store.claim(w["id"], "fixture", "IMAGE")
    content = png(200)
    w = store.image_result(w["id"], t["id"], t["lease_token"], content, receipt(t, content))
    with pytest.raises(WorkflowError):
        store.review(w["id"], "page_0", {"reviewer": "test", "image_sha256": old_hash, "exact_text_checked": True, "visual_status": "PASS", "medical_status": "PASS"})
    assert w["stage"] == "SAMPLES_REVIEW"


def test_content_style_and_page_count_changes(store):
    w = ready(store, 7)
    w = store.settings(w["id"], {"style": "新的测试风格"})
    assert w["content_approval"] and w["style_approval"] is None
    assert all(p["image"] is None for p in w["pages"])
    with store.transaction(w["id"], "TEST_PLAN_CHANGE") as state:
        store.accept_plan(state, plan_result(state, 8))
    w = store.get(w["id"])
    assert len(w["pages"]) == 8 and w["style_approval"] is None
    w = store.settings(w["id"], {"outline": "新的教学内容"})
    assert w["summary"] is None and not w["pages"] and w["content_approval"] is None


def test_stale_callback_and_lease_renewal(store):
    w = planned(store, 1)
    store.queue(w["id"], "IMAGE")
    t = store.claim(w["id"], "fixture")
    assert store.renew(w["id"], t["id"], t["lease_token"])["lease_until"] >= t["lease_until"]
    store.settings(w["id"], {"outline": "变更提纲"})
    content = png(2)
    with pytest.raises(WorkflowError): store.image_result(w["id"], t["id"], t["lease_token"], content, receipt(t, content))


@pytest.mark.parametrize("count", [1, 7, 55])
def test_dynamic_export_and_versioning(store, count):
    w = ready(store, count)
    w = store.export(w["id"])
    assert w["stage"] == "DELIVERED"
    d = w["deliveries"][-1]
    with zipfile.ZipFile(store.path(d["path"] + "/image_pages.pptx")) as archive:
        assert len([n for n in archive.namelist() if n.startswith('ppt/media/') and not n.endswith('/')]) == count
        for i in range(1, count+1):
            xml = archive.read(f"ppt/slides/slide{i}.xml").decode()
            assert "<p:pic>" in xml and "<a:t>" not in xml
    with zipfile.ZipFile(store.path(d["path"] + "/delivery.zip")) as archive:
        assert len([n for n in archive.namelist() if n.startswith("image_pages/")]) == count
    if count == 1:
        original = store.path(d["path"] + "/image_pages.pptx").read_bytes()
        w = store.export(w["id"])
        assert w["deliveries"][-1]["version"] == 2
        assert store.path(d["path"] + "/image_pages.pptx").read_bytes() == original


def test_missing_or_tampered_image_and_source_blocks_delivery(store):
    w = ready(store, 1)
    file = store.path(w["pages"][0]["image"]["path"])
    original = file.read_bytes()
    file.write_bytes(b"tampered")
    with pytest.raises(WorkflowError): store.export(w["id"])
    file.write_bytes(original)
    source = store.path(w["sources"][0]["path"])
    source.write_bytes(b"changed source")
    with pytest.raises(WorkflowError): store.export(w["id"])


def test_pptx_image_pdf_docx_xlsx_extraction():
    from pptx import Presentation
    from pptx.util import Inches
    from docx import Document
    from openpyxl import Workbook
    from fpdf import FPDF
    p = Presentation()
    for i in range(3):
        s = p.slides.add_slide(p.slide_layouts[6])
        s.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1)).text = f"Fixture page {i}"
    b = io.BytesIO(); p.save(b)
    result = extract_document("sample.pptx", b.getvalue(), "fixture")
    assert len(result) == 3 and all(u["requires_visual"] for u in result)
    assert "Fixture page 2" in result[2]["text"]
    assert extract_document("sample.png", png(5), "fixture")[0]["requires_visual"]
    d = Document(); d.add_paragraph("Fixture paragraph"); b = io.BytesIO(); d.save(b)
    assert "Fixture paragraph" in extract_document("sample.docx", b.getvalue(), "fixture")[0]["text"]
    x = Workbook(); x.active['A1'] = 'Fixture cell'; b = io.BytesIO(); x.save(b)
    assert "Fixture cell" in extract_document("sample.xlsx", b.getvalue(), "fixture")[0]["text"]
    pdf = FPDF(); pdf.add_page(); pdf.set_font('Helvetica',size=12); pdf.cell(text='Fixture PDF'); content=bytes(pdf.output())
    assert "Fixture PDF" in extract_document("sample.pdf", content, "fixture")[0]["text"]


def test_api_and_legacy_empty(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import app.fact57098_api as api
    import app.main as main
    monkeypatch.setattr(api, "store", Store(tmp_path / "api-data"))
    monkeypatch.setattr(main, "STORE", tmp_path / "empty-projects.json")
    with TestClient(main.app) as client:
        assert client.get('/api/fact/health').json()['projects'] == 0
        assert client.get('/api/projects').json() == []
        assert client.get('/docs').status_code == 200
        w = client.post('/api/fact/workflows',json={"title":"API fixture","outline":"测试提纲"}).json()
        assert client.post(f"/api/fact/workflows/{w['id']}/tasks",json={"kind":"IMAGE"}).status_code == 409
        response = client.post(f"/api/fact/workflows/{w['id']}/sources",files={"file":("source.txt",b'fixture text','text/plain')})
        assert response.status_code == 200
        assert client.get(f"/api/fact/workflows/{w['id']}/confirmation-draft").status_code == 409
        assert client.post(f"/api/fact/workflows/{w['id']}/export").status_code == 409


def test_no_runtime_old_root_dependency():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for name in ("app/fact57098.py", "app/fact57098_api.py", "app/fact57098_writer.mjs", "tools/codex_worker.py", "start.ps1"):
        text = (root / name).read_text(encoding="utf-8")
        assert "E:\\EasyPPT" not in text and "E:/EasyPPT" not in text
