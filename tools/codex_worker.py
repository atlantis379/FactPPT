"""Local transport for Codex tasks. It never simulates a model or image tool."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="FactPPTv2 Codex协作任务传输")
    parser.add_argument("--server", default="http://127.0.0.1:8001")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    for command in ("show", "queue", "claim", "complete", "image", "fail", "renew"):
        sub = commands.add_parser(command)
        sub.add_argument("workflow_id")
        if command == "queue":
            sub.add_argument("kind", choices=["READ_SOURCE", "SUMMARY", "PAGE_PLAN", "IMAGE"])
            sub.add_argument("--pages", nargs="+")
        if command == "claim":
            sub.add_argument("--worker", default="Codex-desktop")
            sub.add_argument("--kind", choices=["READ_SOURCE", "SUMMARY", "PAGE_PLAN", "IMAGE"])
            sub.add_argument("--out", type=Path)
        if command in {"complete", "image", "fail", "renew"}:
            sub.add_argument("--task", type=Path, required=True, help="claim命令保存的任务合同（含租约）")
        if command == "complete":
            sub.add_argument("--result", type=Path, required=True)
        if command == "image":
            sub.add_argument("--png", type=Path, required=True)
            sub.add_argument("--receipt", type=Path, required=True, help="实际ImageGen调用的记录；必须提供调用标识与生成时间")
        if command == "fail":
            sub.add_argument("--error", required=True)
    args = parser.parse_args()
    base = args.server.rstrip("/") + "/api/fact/workflows"
    with httpx.Client(timeout=150, trust_env=False) as client:
        if args.command == "list":
            response = client.get(base)
        else:
            url = base + "/" + args.workflow_id
            if args.command == "show":
                response = client.get(url)
            elif args.command == "queue":
                response = client.post(url + "/tasks", json={"kind": args.kind, "page_ids": args.pages})
            elif args.command == "claim":
                response = client.post(url + "/tasks/claim", json={"worker": args.worker, "kind": args.kind})
            else:
                task = json.loads(args.task.read_text(encoding="utf-8-sig"))
                task_url = url + "/tasks/" + task["id"]
                token = task["lease_token"]
                if args.command == "complete":
                    result = json.loads(args.result.read_text(encoding="utf-8-sig"))
                    response = client.post(task_url + "/complete", json={"lease_token": token, "result": result})
                elif args.command == "image":
                    content = args.png.read_bytes()
                    receipt = json.loads(args.receipt.read_text(encoding="utf-8-sig"))
                    # Bind actual bytes to the leased content; never invent tool_call_id or QA.
                    receipt["image_sha256"] = hashlib.sha256(content).hexdigest()
                    receipt["contract_sha256"] = task["input_sha256"]
                    response = client.post(task_url + "/image", data={"lease_token": token, "receipt": json.dumps(receipt, ensure_ascii=False)}, files={"file": (args.png.name, content, "image/png")})
                elif args.command == "renew":
                    response = client.post(task_url + "/renew", json={"lease_token": token})
                else:
                    response = client.post(task_url + "/fail", json={"lease_token": token, "error": args.error})
        if response.status_code == 204:
            print("No pending task")
            return
        if response.is_error:
            raise SystemExit(f"HTTP {response.status_code}: {response.text}")
        result = response.json()
        if args.command == "claim":
            path = args.out or ROOT / "data" / "worker" / (result["id"] + ".json")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"task_id": result["id"], "kind": result["kind"], "contract_file": str(path.resolve()), "lease_until": result["lease_until"]}, ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
