"""Job observability: stages, LLM call tokens (unknown stays unknown), persistence, executor task stats."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from factdeck import jobstats as J

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTDECK_JOB_STATS_DB", str(tmp_path / "jobs.sqlite"))
    return tmp_path / "jobs.sqlite"


def test_stages_calls_and_tokens(tmp_path):
    with J.job("unit", out_dir=tmp_path / "o", meta={"x": 1}) as js:
        with J.stage("plan"):
            J.record_llm_call(model="m1", usage={"prompt_tokens": 10, "completion_tokens": 5}, elapsed=0.2, source="t")
        with J.stage("write"):
            J.record_llm_call(model="m2", usage=None, elapsed=0.1)
            J.record_llm_call(model="m3", usage={"input_tokens": 3, "output_tokens": 4, "total_tokens": 7})
    s = json.loads((tmp_path / "o" / "job_stats.json").read_text(encoding="utf-8"))
    assert [x["stage"] for x in s["stages"]] == ["plan", "write"]
    assert s["status"] == "OK" and s["total_seconds"] >= 0
    c = s["llm_calls"]
    assert c[0]["stage"] == "plan" and c[0]["total_tokens"] == 15 and c[0]["tokens_known"]
    assert c[1]["stage"] == "write" and c[1]["total_tokens"] is None and not c[1]["tokens_known"]
    assert c[2]["prompt_tokens"] == 3 and c[2]["total_tokens"] == 7
    assert s["tokens"] == {"calls": 3, "calls_tokens_unknown": 1, "prompt_tokens": 13, "completion_tokens": 9,
                           "total_tokens": 22}
    assert s["tokens_by_stage"]["write"]["tokens_unknown"] == 1
    assert J.get_job(js.job_id)["job_id"] == js.job_id
    assert J.list_jobs()[0]["llm_calls"] == 3


def test_no_job_means_no_record_and_failure_is_recorded():
    assert J.record_llm_call(model="m", usage={"total_tokens": 1}) is None
    with pytest.raises(RuntimeError):
        with J.job("boom") as js:
            with J.stage("s"):
                raise RuntimeError("x")
    s = J.get_job(js.job_id)
    assert s["status"] == "FAILED" and s["stages"][0]["status"] == "FAILED"


def test_ensure_job_joins_active_job():
    with J.job("outer") as outer:
        with J.ensure_job("inner") as inner:
            assert inner is outer
    with J.ensure_job("alone") as alone:
        assert J.current() is alone
    assert J.get_job(alone.job_id)


def test_semantic_model_call_is_recorded(monkeypatch):
    import app.semantic_model as sm

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            return json.dumps({"choices": [{"message": {"content": "{\"ok\": true}"}}],
                               "usage": {"prompt_tokens": 11, "completion_tokens": 2, "total_tokens": 13}}).encode()

    class Opener:
        def open(self, *a, **k): return Resp()

    monkeypatch.setattr(sm.urllib.request, "build_opener", lambda *a, **k: Opener())
    with J.job("sem") as js:
        with J.stage("summary"):
            assert sm.call_semantic_model("triage", {"x": 1}, {"model_id": "test-model", "url": "http://127.0.0.1:9/v1"}) == {"ok": True}
    calls = J.get_job(js.job_id)["llm_calls"]
    assert calls and calls[0]["stage"] == "triage" and calls[0]["model"] == "test-model"
    assert calls[0]["total_tokens"] == 13


def test_workflow_task_stats_never_invents_tokens():
    w = {"id": "w1", "tasks": [
        {"kind": "VISUAL_PAGE", "status": "COMPLETE", "attempts": 1, "claimed_at": "2026-10-25T01:00:00Z",
         "completed_at": "2026-10-25T01:02:00Z"},
        {"kind": "VISUAL_PAGE", "status": "FAILED", "attempts": 2, "claimed_at": "2026-10-25T01:00:00Z"},
        {"kind": "SUMMARY", "status": "COMPLETE", "attempts": 1}],
        "generation": {"pages": [{"assets": {"a": {"receipt": {"elapsed_seconds": 3.5}}, "b": {"receipt": {"tool": "x"}}}}]}}
    r = J.workflow_task_stats(w)
    assert r["by_kind"]["VISUAL_PAGE"] == {"tasks": 2, "complete": 1, "failed": 1, "attempts": 3, "work_seconds": 120.0,
                                           "timed": 1, "tokens": "unknown"}
    assert r["tasks"] == 3 and r["visual_tool_seconds"] == 3.5 and r["visual_unknown_timings"] == 1
    assert "unknown" in r["tokens"]


def test_cli_lists_and_shows(tmp_path, db):
    with J.job("cli", out_dir=tmp_path / "o") as js:
        with J.stage("a"):
            pass
    env = {"FACTDECK_JOB_STATS_DB": str(db), "PATH": "/usr/bin:/bin"}
    run = lambda *a: subprocess.run([sys.executable, str(ROOT / "tools" / "job_stats.py"), *a], capture_output=True,
                                    text=True, env=env, cwd=ROOT)
    assert js.job_id in run().stdout
    shown = run(js.job_id).stdout
    assert "阶段 a" in shown and "无模型调用" in shown
    assert json.loads(run(str(tmp_path / "o" / "job_stats.json"), "--json").stdout)["job_id"] == js.job_id


def test_api_endpoints(db):
    from fastapi.testclient import TestClient
    from app.deckflow_api import router
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    with J.job("api") as js:
        pass
    c = TestClient(app)
    assert any(j["job_id"] == js.job_id for j in c.get("/api/deck/job-stats").json()["jobs"])
    assert c.get(f"/api/deck/job-stats/{js.job_id}").json()["kind"] == "api"
    assert c.get("/api/deck/job-stats/nope").status_code == 404
