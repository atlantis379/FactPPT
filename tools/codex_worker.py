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
DECK_KINDS = ["READ_SOURCE", "SECOND_READ", "CLAIMS", "SUMMARY", "SUMMARY_REVIEW", "FACTS", "DECK", "SEMANTIC_REVIEW", "VISUAL_CRITIQUE", "VISUAL_DESIGN", "VISUAL_LAYOUT", "VISUAL_CLEAN", "VISUAL_VECTOR"]
FACT_KINDS = ["READ_SOURCE", "SUMMARY", "PAGE_PLAN", "IMAGE"]


def main():
    parser = argparse.ArgumentParser(description="FactPPTv2 执行端任务传输")
    parser.add_argument("--server", default="http://127.0.0.1:8001")
    parser.add_argument("--api", choices=["deck", "fact"], default="deck", help="deck=主线（事实库+渲染）；fact=旧整页图片流程")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    for command in ("show", "queue", "claim", "complete", "image", "asset", "fetch-assets", "generate", "generation", "revise", "fail", "renew", "render", "backfill-structure", "backfill-arrows"):
        sub = commands.add_parser(command)
        sub.add_argument("workflow_id")
        if command == "queue":
            sub.add_argument("kind", choices=sorted(set(DECK_KINDS + FACT_KINDS)))
            sub.add_argument("--pages", nargs="+", help="旧流程IMAGE或主线视觉任务单页修订")
            sub.add_argument("--sources", nargs="+", help="仅主线CLAIMS：重做这些资料的论断清单")
        if command == "claim":
            sub.add_argument("--worker", default="Codex-desktop", help="执行端标识；语义审查与第二次转录须与作者不同")
            sub.add_argument("--kind", choices=sorted(set(DECK_KINDS + FACT_KINDS)))
            sub.add_argument("--out", type=Path)
            sub.add_argument("--binding", help="主线中只领取指定页面或资料的任务")
        if command in {"complete", "asset"}:
            sub.add_argument("--compact", action="store_true", help="主线仅返回本次完成确认，减少完整项目传输")
        if command in {"complete", "image", "asset", "fetch-assets", "fail", "renew"}:
            sub.add_argument("--task", type=Path, required=True, help="claim命令保存的任务合同（含租约）")
        if command == "complete":
            sub.add_argument("--result", type=Path, required=True)
        if command == "image":
            sub.add_argument("--png", type=Path, required=True)
            sub.add_argument("--receipt", type=Path, required=True, help="实际ImageGen调用的记录；必须提供调用标识与生成时间")
        if command == "asset":
            sub.add_argument("--file", type=Path, required=True, help="真实工具产生的PNG或SVG")
            sub.add_argument("--receipt", type=Path, required=True, help="按任务 receipt_contract 保存真实调用与检查记录")
        if command == "fetch-assets": sub.add_argument("--out", type=Path, required=True, help="下载当前合同中的参考资产")
        if command == "revise":
            sub.add_argument("--page", required=True)
            sub.add_argument("--kind", choices=DECK_KINDS[-4:], required=True)
        if command == "fail":
            sub.add_argument("--error", required=True)
        if command == "render":
            sub.add_argument("--draft", action="store_true", help="草稿渲染（可含待确认项，不可审核）")
        if command == "generate":
            sub.add_argument("--first-pages", type=int, help="明确启动已核对的前N页范围；须与页面规格一致")
    args = parser.parse_args()
    if args.command == "image" and args.api != "fact":
        raise SystemExit("image 仅用于旧整页图片流程：请加 --api fact")
    if args.command in {"asset", "fetch-assets", "generate", "generation", "revise", "render", "backfill-structure", "backfill-arrows"} and args.api != "deck":
        raise SystemExit(f"{args.command} 仅用于主线")
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
            elif args.command == "generate":
                response = client.post(url + "/generation", json={"first_pages": args.first_pages} if args.first_pages else {})
            elif args.command == "generation": response = client.get(url + "/generation")
            elif args.command == "revise": response = client.post(url + "/generation/revise", json={"page_id":args.page,"kind":args.kind})
            elif args.command in {"backfill-structure", "backfill-arrows"}:   # sources imported by an earlier ingest
                response = client.post(url + "/backfill-structure")
            elif args.command == "queue":
                body = {"kind": args.kind}
                if args.api == "fact":
                    body["page_ids"] = args.pages
                elif args.sources:
                    body["sources"] = args.sources
                elif args.pages: body["pages"] = args.pages
                response = client.post(url + "/tasks", json=body)
            elif args.command == "claim":
                body = {"worker": args.worker, "kind": args.kind}
                if args.binding:
                    if args.api != "deck": raise SystemExit("--binding 仅用于主线")
                    body["binding"] = args.binding
                response = client.post(url + "/tasks/claim", json=body)
            else:
                task = json.loads(args.task.read_text(encoding="utf-8-sig"))
                task_url = url + "/tasks/" + task["id"]
                token = task["lease_token"]
                if args.command == "complete":
                    result = json.loads(args.result.read_text(encoding="utf-8-sig"))
                    response = client.post(task_url + "/complete", params={"compact":True} if args.api == "deck" and args.compact else {}, json={"lease_token": token, "result": result})
                elif args.command == "image":
                    content = args.png.read_bytes()
                    receipt = json.loads(args.receipt.read_text(encoding="utf-8-sig"))
                    # Bind actual bytes to the leased content; never invent tool_call_id or QA.
                    receipt["image_sha256"] = hashlib.sha256(content).hexdigest()
                    receipt["contract_sha256"] = task["input_sha256"]
                    response = client.post(task_url + "/image", data={"lease_token": token, "receipt": json.dumps(receipt, ensure_ascii=False)}, files={"file": (args.png.name, content, "image/png")})
                elif args.command == "asset":
                    content=args.file.read_bytes(); receipt=json.loads(args.receipt.read_text(encoding="utf-8-sig"))
                    receipt["asset_sha256"]=hashlib.sha256(content).hexdigest(); receipt["contract_sha256"]=task["input_sha256"]
                    response=client.post(task_url+"/asset",params={"compact":True} if args.compact else {},data={"lease_token":token,"receipt":json.dumps(receipt,ensure_ascii=False)},files={"file":(args.file.name,content,"image/svg+xml" if args.file.suffix.lower()==".svg" else "image/png")})
                elif args.command == "fetch-assets":
                    args.out.mkdir(parents=True,exist_ok=True); downloaded={}
                    for name,asset in task["brief"].get("assets",{}).items():
                        asset_url=asset["url"]
                        if not asset_url.startswith(f"/api/deck/workflows/{args.workflow_id}/generation/assets/"): raise SystemExit("参考资产地址不属于当前项目")
                        res=client.get(args.server.rstrip("/")+asset_url); res.raise_for_status()
                        if hashlib.sha256(res.content).hexdigest()!=asset["sha256"]: raise SystemExit("参考资产校验失败")
                        dest=args.out/(name+(".svg" if name=="vector" else ".png")); dest.write_bytes(res.content); downloaded[name]=str(dest.resolve())
                    print(json.dumps(downloaded,ensure_ascii=False,indent=2)); return
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
        elif args.command in {"show", "render", "generate", "revise"} and args.api == "deck":
            summary = {k: result.get(k) for k in ("id", "title", "stage", "open_items", "generation_status", "render")}
            if args.command == "render" and args.draft:
                summary["render"] = result.get("draft_render")
                summary["artifact_kind"] = "CONTENT_DRAFT"
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
