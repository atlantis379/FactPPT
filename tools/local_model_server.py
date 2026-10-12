"""Owned, loopback-only local benchmark server with bounded CPU prompt cache."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import socket
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def file_hash(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8083)
    parser.add_argument("--context", type=int, default=32768, help="Text benchmark target; record and qualify the effective window independently of model metadata")
    parser.add_argument("--cache-ram", type=int, default=0, help="MiB; 0 disables CPU prompt cache (server otherwise defaults to 8192)")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or args.context < 4096 or args.cache_ram < 0:
        parser.error("Invalid local runtime limits")
    args.out.mkdir(parents=True, exist_ok=True)
    record_path = args.out / "server_launch.json"
    if record_path.exists(): parser.error("Use a fresh launch directory; never overwrite a server receipt")
    runtime, model = args.runtime.resolve(), args.model.resolve()
    if not runtime.is_file() or not model.is_file(): parser.error("Runtime or model missing")
    with socket.socket() as probe:
        probe.settimeout(1)
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            parser.error("Port already occupied; do not launch a second GPU server")
    # Hash model weights streaming so the 6GB file is never loaded into Python RAM.
    identity = {"runtime_sha256": file_hash(runtime), "model_sha256": file_hash(model), "model_bytes": model.stat().st_size}
    cmd = [str(runtime), "-m", str(model), "-ngl", "99", "-c", str(args.context), "-fa", "on", "-ctk", "q8_0", "-ctv", "q8_0", "-np", "1", "--jinja", "--reasoning", "off", "--cache-ram", str(args.cache_ram), "--host", "127.0.0.1", "--port", str(args.port)]
    with (args.out / "server.stdout.log").open("ab") as stdout, (args.out / "server.stderr.log").open("ab") as stderr:
        process = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    record = {"pid": process.pid, "started_at": datetime.now(timezone.utc).isoformat(), "cmd": cmd, **identity,
              "cache_ram_mib": args.cache_ram, "context": args.context, "port": args.port}
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"pid": process.pid, "receipt": str(record_path.resolve())}, ensure_ascii=False))


if __name__ == "__main__": main()
