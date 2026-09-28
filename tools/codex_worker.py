"""Local transport for worker tasks (Codex, Claude or a person at a terminal).

It never simulates a model: it moves task contracts and authored results between
the executor and the app. Mainline (`--api deck`, default): READ_SOURCE,
SECOND_READ, SUMMARY, FACTS, DECK, SEMANTIC_REVIEW. The earlier full-slide image
workflow (`--api fact`) keeps its IMAGE command.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DECK_KINDS = ["READ_SOURCE", "SECOND_READ", "SUMMARY", "FACTS", "DECK", "SEMANTIC_REVIEW"]
FACT_KINDS = ["READ_SOURCE", "SUMMARY", "PAGE_PLAN", "IMAGE"]


def main():
    parser = argparse.ArgumentParser(description="FactPPTv2 执行端任务传输")
    parser.add_argument("--server", default="http://127.0.0.1:8001")
    parser.add_argument("--api", choices=["deck", "fact"], default="deck", help="deck=主线（事实库+渲染）；fact=旧整页图片流程")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    for command in ("show", "queue", "claim", "complete", "image", "fail", "renew", "render"):
        sub = commands.add_parser(command)
        sub.add_argument("workflow_id")
        if command == "queue":
            sub.add_argument("kind", choices=sorted(set(DECK_KINDS + FACT_KINDS)))
            sub.add_argument("--pages", nargs="+", help="仅旧流程IMAGE任务")
        if command == "claim":
            sub.add_argument("--worker", default="Codex-desktop", help="执行端标识；语义审查与第二次转录须与作者不同")
            sub.add_argument("--kind", choices=sorted(set(DECK_KINDS + FACT_KINDS)))
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
        if command == "render":
            sub.add_argument("--draft", action="store_true", help="草稿渲染（可含待确认项，不可审核）")
    args = parser.parse_args()
    if args.command == "image" and args.api != "fact":
        raise SystemExit("image 仅用于旧整页图片流程：请加 --api fact")
    if args.command == "render" and args.api != "deck":
        raise SystemExit("render 仅用于主线")
    kinds = DECK_KINDS if args.api == "deck" else FACT_KINDS
    if getattr(args, "kind", None) and args.kind not in kinds:
        raise SystemExit(f"{args.api} 流程的任务类型：{', '.join(kinds)}")
    base = args.server.rstrip("/") + f"/api/{args.api}/workflows"
    with httpx.Client(timeout=600, trust_env=False) as client:
        if args.command == "list":
            response = client.get(base)
        else:
            url = base + "/" + args.workflow_id
            if args.command == "show":
                response = client.get(url)
            elif args.command == "render":
                response = client.post(url + "/render", params={"draft": str(args.draft).lower()})
            elif args.command == "queue":
                body = {"kind": args.kind}
                if args.api == "fact":
                    body["page_ids"] = args.pages
                response = client.post(url + "/tasks", json=body)
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
        elif args.command in {"show", "render"} and args.api == "deck":
            print(json.dumps({k: result.get(k) for k in ("id", "title", "stage", "open_items", "render")}, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
