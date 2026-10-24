"""Per-job observability: total wall time, per-stage wall time and per-model-call token usage.

Usage::

    with job("template_deck", out_dir=out) as js:          # writes out/job_stats.json + indexes the job
        with stage("select"):
            ...
        record_llm_call(stage="select", model="m", usage=raw.get("usage"), elapsed=1.2)

Model call sites (app/semantic_model.py, app/layout_ir.py, the selector's LLM tie-break) call
`record_llm_call` — a no-op when no job is active.  Token counts are copied from the endpoint's own `usage`
field; when an endpoint returns none the call is recorded with `tokens_known: false` and null counts (never
estimated).  Jobs are indexed in a small SQLite file (FACTDECK_JOB_STATS_DB, default data/job_stats.sqlite)
so `tools/job_stats.py` and `/api/deck/job-stats` can list them.  Domain-neutral; no app imports.
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "factdeck.job_stats.v1"
_current: contextvars.ContextVar["JobStats | None"] = contextvars.ContextVar("factdeck_job", default=None)
_stage: contextvars.ContextVar[str | None] = contextvars.ContextVar("factdeck_stage", default=None)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_path() -> Path:
    return Path(os.environ.get("FACTDECK_JOB_STATS_DB") or ROOT / "data" / "job_stats.sqlite")


def normalize_usage(usage: Any) -> dict:
    """OpenAI-style usage → {prompt_tokens, completion_tokens, total_tokens, tokens_known}. Unknown stays None."""
    if not isinstance(usage, dict):
        return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None, "tokens_known": False}
    p = usage.get("prompt_tokens", usage.get("input_tokens"))
    c = usage.get("completion_tokens", usage.get("output_tokens"))
    t = usage.get("total_tokens")
    if t is None and isinstance(p, int) and isinstance(c, int):
        t = p + c
    known = all(isinstance(x, int) for x in (p, c, t))
    return {"prompt_tokens": p if isinstance(p, int) else None, "completion_tokens": c if isinstance(c, int) else None,
            "total_tokens": t if isinstance(t, int) else None, "tokens_known": known}


class JobStats:
    def __init__(self, kind: str, *, job_id: str | None = None, out_dir: Path | str | None = None,
                 meta: dict | None = None):
        self.job_id = job_id or f"{kind}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        self.kind = kind
        self.out_dir = Path(out_dir) if out_dir else None
        self.meta = dict(meta or {})
        self.started_at = _now()
        self._t0 = time.perf_counter()
        self.stages: list[dict] = []
        self.calls: list[dict] = []
        self.status = "RUNNING"
        self.error: str | None = None
        self.total_seconds: float | None = None

    # -- stages
    @contextlib.contextmanager
    def stage(self, name: str, **info: Any) -> Iterator[dict]:
        rec = {"stage": name, "started_at": _now(), "seconds": None, "status": "RUNNING", **info}
        self.stages.append(rec)
        tok = _stage.set(name)
        t0 = time.perf_counter()
        try:
            yield rec
            rec["status"] = "OK"
        except BaseException as e:
            rec["status"] = "FAILED"
            rec["error"] = f"{type(e).__name__}: {e}"[:300]
            raise
        finally:
            rec["seconds"] = round(time.perf_counter() - t0, 3)
            _stage.reset(tok)

    # -- model calls
    def record_call(self, *, stage: str | None = None, model: str | None = None, usage: Any = None, elapsed: float | None = None,
                    ok: bool = True, source: str = "", error: str | None = None, **extra: Any) -> dict:
        rec = {"stage": stage or _stage.get() or "unstaged", "model": model, "source": source, "ok": ok,
               "seconds": round(elapsed, 3) if isinstance(elapsed, (int, float)) else None, "at": _now(),
               **normalize_usage(usage), **extra}
        if error:
            rec["error"] = str(error)[:300]
        self.calls.append(rec)
        return rec

    # -- summary / persistence
    def summary(self) -> dict:
        total = self.total_seconds if self.total_seconds is not None else round(time.perf_counter() - self._t0, 3)
        by_stage: dict[str, dict] = {}
        for s in self.stages:
            b = by_stage.setdefault(s["stage"], {"seconds": 0.0, "runs": 0})
            b["seconds"] = round(b["seconds"] + (s["seconds"] or 0), 3)
            b["runs"] += 1
        tok = {"calls": len(self.calls), "calls_tokens_unknown": sum(not c["tokens_known"] for c in self.calls),
               "prompt_tokens": sum(c["prompt_tokens"] or 0 for c in self.calls),
               "completion_tokens": sum(c["completion_tokens"] or 0 for c in self.calls),
               "total_tokens": sum(c["total_tokens"] or 0 for c in self.calls)}
        per_stage_tokens: dict[str, dict] = {}
        for c in self.calls:
            b = per_stage_tokens.setdefault(c["stage"], {"calls": 0, "total_tokens": 0, "tokens_unknown": 0})
            b["calls"] += 1
            b["total_tokens"] += c["total_tokens"] or 0
            b["tokens_unknown"] += (not c["tokens_known"])
        return {"schema": SCHEMA, "job_id": self.job_id, "kind": self.kind, "status": self.status, "error": self.error,
                "started_at": self.started_at, "total_seconds": total, "stages": self.stages, "stage_seconds": by_stage,
                "llm_calls": self.calls, "tokens": tok, "tokens_by_stage": per_stage_tokens, "meta": self.meta,
                "out_dir": str(self.out_dir) if self.out_dir else None}

    def save(self) -> dict:
        s = self.summary()
        if self.out_dir:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            (self.out_dir / "job_stats.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
        try:
            index_job(s)
        except sqlite3.Error as e:          # the index is a convenience; the JSON next to the output is the record
            s.setdefault("warnings", []).append(f"job index not written: {e}")
        return s


@contextlib.contextmanager
def job(kind: str, **kw: Any) -> Iterator[JobStats]:
    js = JobStats(kind, **kw)
    tok = _current.set(js)
    try:
        yield js
        js.status = "OK"
    except BaseException as e:
        js.status = "FAILED"
        js.error = f"{type(e).__name__}: {e}"[:300]
        raise
    finally:
        js.total_seconds = round(time.perf_counter() - js._t0, 3)
        _current.reset(tok)
        js.save()


def current() -> JobStats | None:
    return _current.get()


@contextlib.contextmanager
def stage(name: str, **info: Any) -> Iterator[dict | None]:
    js = _current.get()
    if js is None:
        yield None
        return
    with js.stage(name, **info) as rec:
        yield rec


def record_llm_call(**kw: Any) -> dict | None:
    """Record one model call on the active job (no-op without one)."""
    js = _current.get()
    return js.record_call(**kw) if js is not None else None


# ------------------------------------------------------------------ index (SQLite)

def _connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(p), timeout=30)
    db.execute("""CREATE TABLE IF NOT EXISTS job_stats(job_id TEXT PRIMARY KEY, kind TEXT, status TEXT, started_at TEXT,
                  total_seconds REAL, llm_calls INTEGER, total_tokens INTEGER, tokens_unknown INTEGER, out_dir TEXT,
                  summary TEXT NOT NULL)""")
    return db


def index_job(s: dict, path: Path | None = None) -> None:
    db = _connect(path)
    try:
        with db:
            db.execute("INSERT OR REPLACE INTO job_stats VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (s["job_id"], s["kind"], s["status"], s["started_at"], s["total_seconds"], s["tokens"]["calls"],
                        s["tokens"]["total_tokens"], s["tokens"]["calls_tokens_unknown"], s.get("out_dir"),
                        json.dumps(s, ensure_ascii=False)))
    finally:
        db.close()


def list_jobs(limit: int = 20, path: Path | None = None) -> list[dict]:
    p = path or db_path()
    if not p.exists():
        return []
    db = _connect(p)
    try:
        rows = db.execute("SELECT job_id, kind, status, started_at, total_seconds, llm_calls, total_tokens, tokens_unknown, "
                          "out_dir FROM job_stats ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
    finally:
        db.close()
    keys = ("job_id", "kind", "status", "started_at", "total_seconds", "llm_calls", "total_tokens", "tokens_unknown", "out_dir")
    return [dict(zip(keys, r)) for r in rows]


def get_job(job_id: str, path: Path | None = None) -> dict | None:
    p = path or db_path()
    if not p.exists():
        return None
    db = _connect(p)
    try:
        row = db.execute("SELECT summary FROM job_stats WHERE job_id = ?", (job_id,)).fetchone()
    finally:
        db.close()
    return json.loads(row[0]) if row else None


# ------------------------------------------------------------------ worker tasks (Codex / human executors)

def _ts(v: Any) -> float | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def workflow_task_stats(w: dict) -> dict:
    """Executor tasks of a /api/deck workflow: per task kind, count / attempts / claimed→completed wall time.
    Executors do not report tokens to the app, so tokens are marked unknown (never estimated).  Visual receipts'
    own `elapsed_seconds` are summed where present."""
    kinds: dict[str, dict] = {}
    for t in w.get("tasks") or []:
        k = kinds.setdefault(t.get("kind", "?"), {"tasks": 0, "complete": 0, "failed": 0, "attempts": 0,
                                                 "work_seconds": 0.0, "timed": 0, "tokens": "unknown"})
        k["tasks"] += 1
        k["attempts"] += int(t.get("attempts") or 0)
        k["complete"] += t.get("status") == "COMPLETE"
        k["failed"] += t.get("status") == "FAILED"
        a, b = _ts(t.get("claimed_at")), _ts(t.get("completed_at"))
        if a and b and b >= a:
            k["work_seconds"] = round(k["work_seconds"] + (b - a), 1)
            k["timed"] += 1
    receipts = []
    for p in ((w.get("generation") or {}).get("pages") or []):
        for asset in (p.get("assets") or {}).values():
            r = (asset or {}).get("receipt") or {}
            if r:
                receipts.append(r)
    return {"workflow_id": w.get("id"), "by_kind": kinds,
            "tasks": sum(k["tasks"] for k in kinds.values()),
            "work_seconds": round(sum(k["work_seconds"] for k in kinds.values()), 1),
            "visual_receipts": len(receipts),
            "visual_tool_seconds": round(sum(r["elapsed_seconds"] for r in receipts
                                             if isinstance(r.get("elapsed_seconds"), (int, float))), 3),
            "visual_unknown_timings": sum(not isinstance(r.get("elapsed_seconds"), (int, float)) for r in receipts),
            "tokens": "unknown（执行端未向应用报告 token 用量）",
            "note": "work_seconds = 领取→完成（最后一次尝试）的墙钟时间，含执行端等待；不是计费依据"}


@contextlib.contextmanager
def ensure_job(kind: str, **kw: Any) -> Iterator[JobStats]:
    """Join the active job, or open (and persist) a new one for this unit of work."""
    js = _current.get()
    if js is not None:
        yield js
        return
    with job(kind, **kw) as new:
        yield new
