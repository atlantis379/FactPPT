#!/usr/bin/env python3
"""Job observability: wall time, per-stage time, LLM calls/tokens.

  python tools/job_stats.py                     # recent jobs (index: FACTDECK_JOB_STATS_DB or data/job_stats.sqlite)
  python tools/job_stats.py JOB_ID              # one job (from index)
  python tools/job_stats.py path/to/job_stats.json   # a job file written next to its outputs
  python tools/job_stats.py --workflow WF_ID    # executor tasks of a /api/deck workflow (tokens unknown)
  add --json for raw JSON
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factdeck.jobstats import get_job, list_jobs, workflow_task_stats  # noqa: E402


def _tok(v):
    return "未知" if v is None else str(v)


def show(s: dict) -> str:
    tok = s.get("tokens") or {}
    unk = tok.get("calls_tokens_unknown", 0)
    out = [f"job {s['job_id']}  kind={s.get('kind')}  status={s.get('status')}  started={s.get('started_at')}",
           f"  总耗时 {s.get('total_seconds')} s"]
    for st in s.get("stages") or []:
        out.append(f"  - 阶段 {st['stage']:<14} {st.get('seconds') or 0:>8.3f} s  {st.get('status')}")
    out.append(f"  LLM 调用 {tok.get('calls', 0)} 次；tokens prompt={tok.get('prompt_tokens', 0)} "
               f"completion={tok.get('completion_tokens', 0)} total={tok.get('total_tokens', 0)}"
               + (f"（另有 {unk} 次调用未返回用量，未计入、记为未知）" if unk else ""))
    for c in s.get("llm_calls") or []:
        out.append(f"    · [{c.get('stage')}] {c.get('model')} {c.get('source') or ''} "
                   f"p={_tok(c.get('prompt_tokens'))} c={_tok(c.get('completion_tokens'))} "
                   f"t={_tok(c.get('total_tokens'))} {c.get('seconds')} s{'' if c.get('ok', True) else ' FAILED'}")
    if not (s.get("llm_calls") or []):
        out.append("    （本次无模型调用）")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job", nargs="?", help="job id or path to job_stats.json")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--workflow", help="workflow id in the /api/deck store")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.workflow:
        from app.deckflow import Store
        root = os.environ.get("FACTDECK_DATA_ROOT")
        w = Store(Path(root) if root else None).get(a.workflow)
        r = workflow_task_stats(w)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    if a.job:
        p = Path(a.job)
        s = json.loads(p.read_text(encoding="utf-8")) if p.suffix == ".json" and p.is_file() else get_job(a.job)
        if s is None:
            print(f"job not found: {a.job}", file=sys.stderr)
            return 1
        print(json.dumps(s, ensure_ascii=False, indent=2) if a.json else show(s))
        return 0
    jobs = list_jobs(a.limit)
    if a.json:
        print(json.dumps(jobs, ensure_ascii=False, indent=2))
        return 0
    if not jobs:
        print("（尚无记录的 job）")
    for s in jobs:
        unk = f"（{s['tokens_unknown']} 次未知）" if s.get("tokens_unknown") else ""
        print(f"{s['job_id']}  {s.get('kind'):<22} {s.get('status'):<6} {s.get('total_seconds'):>8} s  "
              f"LLM {s.get('llm_calls', 0)} 次 / tokens {s.get('total_tokens', 0)}{unk}  {s.get('started_at')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
