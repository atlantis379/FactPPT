"""Local visual-worker lease heartbeats and bounded tool concurrency.

This helper never generates media or approves QA. Actual calls remain in Codex.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "output" / "worker_runtime"
LIMITS = {"image_gen": 1, "adobe": 2, "browser": 1}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + secrets.token_hex(6) + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf8")
    os.replace(temporary, path)


def database():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(RUNTIME / "tool_locks.sqlite3", timeout=20)
    db.execute("CREATE TABLE IF NOT EXISTS locks(token TEXT PRIMARY KEY, tool TEXT, owner TEXT, task_id TEXT, expires REAL)")
    db.commit()
    return db


def acquire(tool, owner, task_id, ttl=900):
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM locks WHERE expires<?", (time.time(),))
        if db.execute("SELECT COUNT(*) FROM locks WHERE tool=?", (tool,)).fetchone()[0] >= LIMITS[tool]:
            return None
        token = secrets.token_urlsafe(24)
        db.execute("INSERT INTO locks VALUES(?,?,?,?,?)", (token, tool, owner, task_id, time.time()+ttl))
        return {"token": token, "tool": tool, "owner": owner, "task_id": task_id}


def release(lock):
    with database() as db:
        db.execute("DELETE FROM locks WHERE token=? AND owner=?", (lock["token"], lock["owner"]))


def extend(owner, task_id):
    with database() as db:
        db.execute("UPDATE locks SET expires=? WHERE owner=? AND task_id=?", (time.time()+900, owner, task_id))


def heartbeat(args):
    task = read(args.task); start = time.monotonic()
    endpoint = args.server.rstrip("/")+f"/api/deck/workflows/{args.workflow_id}/tasks/{task['id']}/renew"
    with httpx.Client(timeout=20, trust_env=False) as client:
        while time.monotonic()-start < args.max_seconds and not Path(args.stop).exists():
            try:
                res = client.post(endpoint, json={"lease_token": task["lease_token"]})
                if res.status_code in (404, 409, 422):
                    print(json.dumps({"at":time.time(),"task_id":task["id"],"exit":"TASK_ENDED_OR_STALE","status":res.status_code}),flush=True)
                    break
                res.raise_for_status(); extend(task["worker"], task["id"])
                print(json.dumps({"at":time.time(),"task_id":task["id"],"renewed":True}),flush=True)
            except httpx.HTTPError as exc:
                print(json.dumps({"at":time.time(),"task_id":task["id"],"network_error":type(exc).__name__}),flush=True)
            for _ in range(args.interval):
                if Path(args.stop).exists() or time.monotonic()-start >= args.max_seconds: break
                time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "heartbeat"):
        p=sub.add_parser(name);p.add_argument("workflow_id");p.add_argument("--task",required=True,type=Path)
        p.add_argument("--stop",required=True,type=Path);p.add_argument("--server",default="http://127.0.0.1:8001")
        p.add_argument("--interval",type=int,default=90);p.add_argument("--max-seconds",type=int,default=3600)
        if name=="start":p.add_argument("--out",required=True,type=Path)
    p=sub.add_parser("lock");p.add_argument("--tool",choices=LIMITS,required=True);p.add_argument("--task",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path);p.add_argument("--wait-seconds",type=int,default=20)
    p=sub.add_parser("unlock");p.add_argument("--lock",required=True,type=Path)
    p=sub.add_parser("stop");p.add_argument("--stop",required=True,type=Path)
    args=parser.parse_args()
    if args.command in {"start","heartbeat"} and (not 1<=args.interval<=300 or not 1<=args.max_seconds<=7200):
        parser.error("Heartbeat interval must be 1–300 seconds and lifetime 1–7200 seconds")
    if args.command=="heartbeat":heartbeat(args)
    elif args.command=="start":
        if args.stop.exists():raise SystemExit("Use a new unique stop file for each task lease")
        args.out.parent.mkdir(parents=True,exist_ok=True)
        log=args.out.with_suffix(".log")
        cmd=[sys.executable,str(Path(__file__).resolve()),"heartbeat",args.workflow_id,"--task",str(args.task.resolve()),"--stop",str(args.stop.resolve()),"--server",args.server,"--interval",str(args.interval),"--max-seconds",str(args.max_seconds)]
        with log.open("ab") as output:
            proc=subprocess.Popen(cmd,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=output,stderr=output,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
        save(args.out,{"pid":proc.pid,"task_id":read(args.task)["id"],"log":str(log.resolve()),"stop":str(args.stop.resolve()),"max_seconds":args.max_seconds})
        print(json.dumps({"started":True,"pid":proc.pid,"log":str(log.resolve())}))
    elif args.command=="lock":
        task=read(args.task); end=time.monotonic()+min(max(args.wait_seconds,0),30)
        while True:
            lock=acquire(args.tool,task["worker"],task["id"])
            if lock:save(args.out,lock);print(json.dumps({"acquired":True,"tool":args.tool}));break
            if time.monotonic()>=end:print(json.dumps({"acquired":False,"tool":args.tool}));raise SystemExit(2)
            time.sleep(1)
    elif args.command=="unlock":release(read(args.lock));print('{"released":true}')
    else:args.stop.parent.mkdir(parents=True,exist_ok=True);args.stop.touch();print('{"stopped":true}')


if __name__=="__main__":main()
