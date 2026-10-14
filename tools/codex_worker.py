"""Local transport for worker tasks (Codex, Claude or a person at a terminal).

It never simulates a model: it moves task contracts and authored results between
the executor and the app. Mainline (`--api deck`, default): READ_SOURCE,
SECOND_READ, SUMMARY, FACTS, DECK, SEMANTIC_REVIEW. The earlier full-slide image
workflow (`--api fact`) keeps its IMAGE command.
"""
from __future__ import annotations
import argparse
from contextlib import nullcontext
import hashlib
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.worker_context import pack as pack_context, metrics as context_metrics


def asset_url_allowed(workflow_id, name, asset_url):
    prefix = f"/api/deck/workflows/{workflow_id}"
    return (asset_url.startswith(prefix + "/generation/assets/")
            or asset_url.startswith(prefix + "/visual-standard/standard_content_")
            or asset_url.startswith(prefix + "/visual-standard/project_reference_")
            or (name == "academic_template" and asset_url == prefix + "/visual-template"))
DECK_KINDS = ["READ_SOURCE", "SECOND_READ", "CLAIMS", "STRUCTURE", "STRUCTURE_REVIEW", "SUMMARY", "SUMMARY_AMEND", "SUMMARY_REVIEW", "FACTS", "DECK", "SEMANTIC_REVIEW", "VISUAL_CRITIQUE", "VISUAL_DESIGN", "VISUAL_LAYOUT", "VISUAL_CLEAN", "VISUAL_VECTOR", "VISUAL_BLIND_READ"]
FACT_KINDS = ["READ_SOURCE", "SUMMARY", "PAGE_PLAN", "IMAGE"]
VISUAL_KINDS = ["VISUAL_DESIGN", "VISUAL_LAYOUT", "VISUAL_CLEAN", "VISUAL_VECTOR", "VISUAL_BLIND_READ"]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def fetch_assets(client, server, workflow_id, task, out):
    """Reference assets for a visual task: copied from the local archive when the
    checksum matches (same machine), otherwise downloaded and verified."""
    out.mkdir(parents=True, exist_ok=True); downloaded = {}
    for name, asset in task["brief"].get("assets", {}).items():
        if not asset_url_allowed(workflow_id, name, asset["url"]): raise SystemExit("参考资产地址不属于当前项目")
        dest = out / (name + (".svg" if name == "vector" else ".png"))
        if not (dest.is_file() and sha256(dest.read_bytes()) == asset["sha256"]):
            local = Path(asset["local_path"]) if asset.get("local_path") else None
            if local and local.is_file() and sha256(local.read_bytes()) == asset["sha256"]:
                content = local.read_bytes()
            else:
                res = client.get(server.rstrip("/") + asset["url"]); res.raise_for_status(); content = res.content
                if sha256(content) != asset["sha256"]: raise SystemExit("参考资产校验失败")
            dest.write_bytes(content)
        downloaded[name] = str(dest.resolve())
    return downloaded


def build_receipt(task, data, args):
    """Fill the receipt contract mechanically. The worker supplies only what a tool call
    and an inspection produce: the actual file, its call identifier, timing and QA verdicts."""
    brief = task["brief"]; receipt = json.loads(json.dumps(brief["receipt_contract"], ensure_ascii=False))
    allowed = brief.get("allowed_tools") or [receipt["tool"]]
    tool = args.tool or allowed[0]
    if tool not in allowed: raise SystemExit("该阶段只接受这些工具：" + "、".join(allowed))
    if not args.tool_call_id.strip(): raise SystemExit("须填写实际调用标识")
    qa = {"inspected": True}
    plan_contract = brief.get("illustration_plan_contract")
    if plan_contract:
        if not args.illustration_plan: raise SystemExit("正文页设计稿须提供 --illustration-plan（实际用于生图的插图方案）")
        plan = json.loads(args.illustration_plan.read_text(encoding="utf-8-sig"))
        receipt["prompt"] = design_prompt(task, plan); qa["illustration_plan"] = plan
    if task["kind"] == "VISUAL_CLEAN":
        qa.update(text_free=args.text_free, semantic_graphics_removed=args.semantic_removed, illustrations_kept=args.illustrations_kept)
    if args.qa_json: qa.update(json.loads(args.qa_json.read_text(encoding="utf-8-sig")))
    if args.qa_note: qa["review"] = args.qa_note
    receipt.update(contract_sha256=task["input_sha256"], asset_sha256=sha256(data), tool=tool, tool_call_id=args.tool_call_id, qa=qa)
    if args.timing_unknown:
        receipt.update(elapsed_seconds=None, timing_status="UNKNOWN_AFTER_INTERRUPTION", timing_note=args.timing_unknown)
    elif args.elapsed is None:
        raise SystemExit("须提供 --elapsed（实际调用秒数），或用 --timing-unknown 说明为何缺失")
    else:
        receipt["elapsed_seconds"] = args.elapsed
    return receipt


def design_prompt(task, plan):
    """The exact image_gen prompt for a content page: contract prompt + the plan's drawing list.
    The plan is checked first, so a plan the server would refuse never costs an image call."""
    from factdeck.visual_grammar import check_plan, plan_prompt
    contract = task["brief"].get("illustration_plan_contract")
    if not contract: return task["brief"]["prompt"]
    try:
        check_plan(plan, contract["layout"], [x["text"] for x in contract["grammar"]["passages"]], contract["grammar"]["focus"])
    except ValueError as e:
        raise SystemExit("作图方案未通过检查（未生成提示词，不要生图）：" + str(e))
    return plan_prompt(task["brief"]["prompt"], plan)


def layout_result(task, patch_path):
    """The proposed layout is the locked geometry; a patch adjusts named objects only."""
    result = json.loads(json.dumps(task["brief"]["result_contract"], ensure_ascii=False))
    if patch_path:
        patch = json.loads(patch_path.read_text(encoding="utf-8-sig"))
        by_id = {o["id"]: o for o in result["objects"]}
        for change in patch.get("objects", []):
            if change.get("id") not in by_id: raise SystemExit("补丁对象不在锁定合同中：" + str(change.get("id")))
            by_id[change["id"]].update(change)
        for key in ("components", "differences"):
            if key in patch: result[key] = patch[key]
    result["design_inspected"] = True
    return result


def main():
    parser = argparse.ArgumentParser(description="FactPPTv2 执行端任务传输")
    parser.add_argument("--server", default="http://127.0.0.1:8001")
    parser.add_argument("--in-process", action="store_true", help="本机直接调用同一API及SQLite事务；用于服务未启动或回环连接受限时，不跳过验收与租约")
    parser.add_argument("--api", choices=["deck", "fact"], default="deck", help="deck=主线（事实库+渲染）；fact=旧整页图片流程")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    for command in ("show", "queue", "claim", "complete", "image", "asset", "submit", "layout", "design-prompt", "adopt-rules", "fetch-assets", "generate", "generation", "revise", "fail", "renew", "render", "page-preview", "backfill-structure", "backfill-arrows"):
        sub = commands.add_parser(command)
        sub.add_argument("workflow_id")
        if command == "queue":
            sub.add_argument("kind", choices=sorted(set(DECK_KINDS + FACT_KINDS)))
            sub.add_argument("--pages", nargs="+", help="旧流程IMAGE或主线视觉任务单页修订")
            sub.add_argument("--sources", nargs="+", help="仅主线CLAIMS：重做这些资料的论断清单")
            sub.add_argument("--checks", nargs="+", choices=["COVERAGE", "RELATIONS"], help="仅主线SEMANTIC_REVIEW：只排队这些检查表（默认两张都排）")
        if command == "claim":
            sub.add_argument("--worker", default="Codex-desktop", help="执行端标识；语义审查与第二次转录须与作者不同")
            sub.add_argument("--kind", choices=sorted(set(DECK_KINDS + FACT_KINDS)))
            sub.add_argument("--kinds", nargs="+", choices=VISUAL_KINDS, help="按角色领取其中任一类视觉任务，例如生图端：VISUAL_DESIGN VISUAL_CLEAN")
            sub.add_argument("--out", type=Path)
            sub.add_argument("--assets-dir", type=Path, help="视觉任务：同时取出参考资产到此目录")
            sub.add_argument("--binding", help="主线中只领取指定页面、资料或语义检查表（COVERAGE / RELATIONS）的任务")
            sub.add_argument("--input-format", choices=["original", "shared-v1"], default="original", help="另存无损去重模型输入；原任务和租约不变")
        if command in {"queue", "complete", "asset", "fail"}:
            sub.add_argument("--compact", action="store_true", default=True, help="主线默认返回简短回执，减少完整项目传输")
            sub.add_argument("--full-response", action="store_false", dest="compact", help="恢复原完整项目响应；旧流程保持原行为")
        if command in {"complete", "image", "asset", "submit", "layout", "design-prompt", "fetch-assets", "fail", "renew"}:
            sub.add_argument("--task", type=Path, required=True, help="claim命令保存的任务合同（含租约）")
        if command == "complete":
            sub.add_argument("--result", type=Path, required=True)
        if command == "image":
            sub.add_argument("--png", type=Path, required=True)
            sub.add_argument("--receipt", type=Path, required=True, help="实际ImageGen调用的记录；必须提供调用标识与生成时间")
        if command == "asset":
            sub.add_argument("--file", type=Path, required=True, help="真实工具产生的PNG或SVG")
            sub.add_argument("--receipt", type=Path, required=True, help="按任务 receipt_contract 保存真实调用与检查记录")
        if command == "submit":
            sub.add_argument("--file", type=Path, required=True, help="真实工具产生的PNG或SVG")
            sub.add_argument("--tool-call-id", required=True, help="实际工具调用标识（照抄工具返回）")
            sub.add_argument("--tool", help="实际使用的工具名；默认合同允许的第一个")
            sub.add_argument("--elapsed", type=float, help="实际调用秒数")
            sub.add_argument("--timing-unknown", help="中断后无法取得耗时的具体说明（耗时记为未知，不按零计）")
            sub.add_argument("--inspected", action="store_true", required=True, help="确认已查看实际输出")
            sub.add_argument("--text-free", action="store_true", help="去字：已查看确认无残字")
            sub.add_argument("--semantic-removed", action="store_true", help="去字：已移除数据柱、连接线和箭头（待原生重建）")
            sub.add_argument("--illustrations-kept", action="store_true", help="去字：已逐项核对说明插画完整保留")
            sub.add_argument("--qa-note", help="检查结论（写入回执 qa.review）")
            sub.add_argument("--qa-json", type=Path, help="补充的检查字段（JSON对象）")
            sub.add_argument("--save-receipt", type=Path, help="另存实际提交的回执")
            sub.add_argument("--illustration-plan", type=Path, help="正文页设计稿：实际用于生图的插图方案JSON")
        if command == "design-prompt":
            sub.add_argument("--illustration-plan", type=Path, required=True, help="作图方案JSON：{units:[{text, relation, terms, draw, encoding}], omitted, arrangement}")
            sub.add_argument("--out", type=Path, required=True, help="写出完整生图提示词（原样交给 image_gen）")
        if command == "layout":
            sub.add_argument("--inspected", action="store_true", required=True, help="确认已查看实际设计稿")
            sub.add_argument("--patch", type=Path, help="只调整几何的补丁：{objects:[{id,x,y,w,h,…}], components, differences}")
            sub.add_argument("--matches-design", help="不加补丁时必填：说明为何默认坐标已与设计稿中文字位置一致")
        if command in {"submit", "layout"}:
            sub.add_argument("--next-out", type=Path, help="提交后把同页下一步直接租给本执行端，合同写到此文件")
            sub.add_argument("--next-kinds", nargs="+", choices=VISUAL_KINDS, help="续领时只接这些类型（双执行端分工）")
            sub.add_argument("--assets-dir", type=Path, help="续领任务的参考资产目录（默认与合同同目录的 assets）")
        if command == "page-preview": sub.add_argument("--page", required=True)
        if command == "adopt-rules":
            sub.add_argument("--operator", required=True, help="采纳新内容规则的操作人")
            sub.add_argument("--reason", required=True, help="为何在项目中途改用新规则")
        if command == "fetch-assets": sub.add_argument("--out", type=Path, required=True, help="下载当前合同中的参考资产")
        if command == "revise":
            sub.add_argument("--page", required=True)
            sub.add_argument("--kind", choices=VISUAL_KINDS, required=True)
        if command == "fail":
            sub.add_argument("--error", required=True)
        if command == "render":
            sub.add_argument("--draft", action="store_true", help="草稿渲染（可含待确认项，不可审核）")
        if command == "generate":
            sub.add_argument("--first-pages", type=int, help="明确启动已核对的前N页范围；须与页面规格一致")
            sub.add_argument("--batch-size", type=int, help="同时在制的页数（默认5）；其余页随前面完成依次排队")
            sub.add_argument("--pages", nargs="+", help="先做这些页（样页轮）；不在列表的页暂不新开")
    args = parser.parse_args()
    if args.command == "image" and args.api != "fact":
        raise SystemExit("image 仅用于旧整页图片流程：请加 --api fact")
    if args.command == "design-prompt":
        task = json.loads(args.task.read_text(encoding="utf-8-sig"))
        prompt = design_prompt(task, json.loads(args.illustration_plan.read_text(encoding="utf-8-sig")))
        args.out.write_text(prompt, encoding="utf-8"); print(json.dumps({"prompt_file": str(args.out.resolve()), "chars": len(prompt)}, ensure_ascii=False)); return
    if args.command in {"asset", "submit", "layout", "fetch-assets", "generate", "generation", "revise", "render", "page-preview", "backfill-structure", "backfill-arrows"} and args.api != "deck":
        raise SystemExit(f"{args.command} 仅用于主线")
    if args.command == "claim" and args.input_format == "shared-v1" and (args.api != "deck" or args.kind not in {"SUMMARY", "SUMMARY_REVIEW", "DECK", "SEMANTIC_REVIEW"}):
        raise SystemExit("shared-v1 需明确指定主线 SUMMARY、SUMMARY_REVIEW、DECK 或 SEMANTIC_REVIEW")
    kinds = DECK_KINDS if args.api == "deck" else FACT_KINDS
    if getattr(args, "kind", None) and args.kind not in kinds:
        raise SystemExit(f"{args.api} 流程的任务类型：{', '.join(kinds)}")
    base = args.server.rstrip("/") + f"/api/{args.api}/workflows"
    if args.in_process:
        from fastapi.testclient import TestClient
        from app.main import app
        transport = TestClient(app, base_url="http://127.0.0.1:8001")
    else:
        transport = httpx.Client(timeout=600, trust_env=False)
    # A one-shot worker request must not start/stop the server's recovery workers.
    # API handlers and their validation/SQLite transactions still execute normally.
    context = nullcontext(transport) if args.in_process else transport
    with context as client:
        if args.command == "list":
            response = client.get(base)
        else:
            url = base + "/" + args.workflow_id
            if args.command == "show":
                response = client.get(url)
            elif args.command == "render":
                response = client.post(url + "/render", params={"draft": str(args.draft).lower()})
            elif args.command == "generate":
                body = {k: v for k, v in (("first_pages", args.first_pages), ("batch_size", args.batch_size), ("pages", args.pages)) if v}
                response = client.post(url + "/generation", json=body)
            elif args.command == "page-preview": response = client.post(url + f"/generation/previews/{args.page}")
            elif args.command == "adopt-rules": response = client.post(url + "/rules/adopt", json={"operator": args.operator, "reason": args.reason})
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
                elif args.checks:
                    body["checks"] = args.checks
                elif args.pages: body["pages"] = args.pages
                response = client.post(url + "/tasks", params={"compact":True} if args.api == "deck" and args.compact else {}, json=body)
            elif args.command == "claim":
                if args.kind and args.kinds: raise SystemExit("--kind 与 --kinds 只能用其一")
                body = {"worker": args.worker, "kind": args.kind} if not args.kinds else {"worker": args.worker, "kinds": args.kinds}
                if args.binding:
                    if args.api != "deck": raise SystemExit("--binding 仅用于主线")
                    body["binding"] = args.binding
                response = client.post(url + "/tasks/claim", json=body)
            else:
                task = json.loads(args.task.read_text(encoding="utf-8-sig"))
                task_url = url + "/tasks/" + task["id"]
                token = task["lease_token"]
                chain = {"chain": True, "compact": True, **({"chain_kinds": args.next_kinds} if args.next_kinds else {})} if getattr(args, "next_out", None) else {"compact": True}
                if args.command == "layout":
                    if task["kind"] != "VISUAL_LAYOUT": raise SystemExit("layout 只用于 VISUAL_LAYOUT 任务")
                    if not args.patch and not (args.matches_design or "").strip(): raise SystemExit("版面须对照设计稿：提供 --patch，或用 --matches-design 说明默认坐标为何已与设计稿一致")
                    result = layout_result(task, args.patch)
                    if not args.patch: result["differences"] = ["对照设计稿，默认坐标保留：" + args.matches_design.strip()]
                    response = client.post(task_url + "/complete", params=chain, json={"lease_token": token, "result": result})
                elif args.command == "submit":
                    if task["kind"] not in {"VISUAL_DESIGN", "VISUAL_CLEAN", "VISUAL_VECTOR"}: raise SystemExit("submit 只用于生图、去字和矢量化任务")
                    content = args.file.read_bytes(); receipt = build_receipt(task, content, args)
                    if args.save_receipt: args.save_receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
                    response = client.post(task_url + "/asset", params=chain, data={"lease_token": token, "receipt": json.dumps(receipt, ensure_ascii=False)},
                                           files={"file": (args.file.name, content, "image/svg+xml" if args.file.suffix.lower() == ".svg" else "image/png")})
                elif args.command == "complete":
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
                    print(json.dumps(fetch_assets(client, args.server, args.workflow_id, task, args.out), ensure_ascii=False, indent=2)); return
                elif args.command == "renew":
                    response = client.post(task_url + "/renew", json={"lease_token": token})
                else:
                    response = client.post(task_url + "/fail", params={"compact":True} if args.api == "deck" and args.compact else {}, json={"lease_token": token, "error": args.error})
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
            receipt = {"task_id": result["id"], "kind": result["kind"], "binding": result.get("binding"), "contract_file": str(path.resolve()), "lease_until": result["lease_until"]}
            if args.assets_dir and result["kind"] in VISUAL_KINDS:
                receipt["assets"] = fetch_assets(client, args.server, args.workflow_id, result, args.assets_dir)
            if args.input_format == "shared-v1":
                packet = pack_context(result["brief"])
                model_path = path.with_name(path.stem + ".model.json")
                model_path.write_text(json.dumps(packet, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                metric_path = path.with_name(path.stem + ".context_metrics.json")
                metric_path.write_text(json.dumps(context_metrics(result["brief"], packet), ensure_ascii=False, indent=2), encoding="utf-8")
                receipt.update(model_input_file=str(model_path.resolve()), context_metrics_file=str(metric_path.resolve()))
            print(json.dumps(receipt, ensure_ascii=False))
        elif args.command in {"submit", "layout"}:
            nxt = result.pop("next", None)
            if getattr(args, "next_out", None):
                result["next"] = None
                if nxt:
                    args.next_out.parent.mkdir(parents=True, exist_ok=True)
                    args.next_out.write_text(json.dumps(nxt, ensure_ascii=False, indent=2), encoding="utf-8")
                    folder = args.assets_dir or args.next_out.parent / "assets"
                    result["next"] = {"task_id": nxt["id"], "kind": nxt["kind"], "binding": nxt["binding"], "contract_file": str(args.next_out.resolve()),
                                      "lease_until": nxt["lease_until"], "assets": fetch_assets(client, args.server, args.workflow_id, nxt, folder)}
            print(json.dumps(result, ensure_ascii=False, indent=2))
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
