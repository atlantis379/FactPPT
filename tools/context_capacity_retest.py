"""Replay the exact rejected request at 32K, without changing production content."""
from __future__ import annotations
import ctypes
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.worker_context import fingerprint
from tools.chapter_draft_benchmark import read, save, parse_response
from tools.local_benchmark_resources import Memory

OUT = ROOT / "output/chapter_context_32k_retest"
OLD = ROOT / "output/chapter_draft_benchmark"


def main():
    original = OLD / "local/revision1/synthesis.capacity_failure.request.json"
    first_receipt = read(OLD / "local/revision1/synthesis.capacity_failure.receipt.json")
    request = read(original)
    key = fingerprint(request)
    if key != first_receipt["request_sha256"]:
        raise ValueError("Original request hash mismatch")
    runtime = read(OUT / "runtime/server_launch.json")
    previous_runtime = read(OLD / "runtime_bounded/server_launch.json")
    for field in ("model_sha256", "runtime_sha256", "cache_ram_mib"):
        if runtime[field] != previous_runtime[field]:
            raise ValueError("Retest runtime identity changed: " + field)
    previous_args = previous_runtime["cmd"].copy()
    previous_args[previous_args.index("-c")+1] = "32768"
    if runtime["cmd"] != previous_args or runtime["context"] != 32768:
        raise ValueError("Only context may change in runtime arguments")
    receipt_path = OUT / "receipt.json"
    if receipt_path.exists():
        raise ValueError("Retest already recorded; do not overwrite or silently repeat")
    save(OUT / "request.json", request)
    records = []
    stop = threading.Event()
    def sample():
        while not stop.is_set():
            memory = Memory(); memory.length = ctypes.sizeof(memory)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))
            row = {"utc_epoch": time.time(), "ram_available_bytes": memory.available_physical}
            try:
                raw = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"], text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW).strip()
                used, load = raw.split(",")
                row.update(gpu_used_mib=int(used), gpu_utilization_percent=int(load))
            except Exception as exc:
                row["error"] = str(exc)
            records.append(row)
            stop.wait(3)
    watcher = threading.Thread(target=sample, daemon=True)
    receipt = {"schema": "context_capacity_retest.v1", "started_at": datetime.now(timezone.utc).isoformat(),
               "original_request": str(original), "request_sha256": key, "same_request_verified": True,
               "previous_context": 16384, "context": 32768, "previous_rejected_tokens": 17234,
               "max_output_tokens": request["max_tokens"], "model_calls": 1,
               "medical_review_performed": False, "human_confirmed": False, "production_changed": False}
    start = time.perf_counter()
    watcher.start()
    try:
        with httpx.Client(timeout=600, trust_env=False) as client:
            health = client.get("http://127.0.0.1:8083/health"); health.raise_for_status()
            response = client.post("http://127.0.0.1:8083/v1/chat/completions", json=request)
            receipt.update(http_status=response.status_code)
            if not response.is_success:
                receipt["response_body"] = response.text
            response.raise_for_status()
            raw = response.json()
            save(OUT / "response.json", raw)
            receipt.update(usage=raw.get("usage"), timings=raw.get("timings"), finish_reason=raw["choices"][0].get("finish_reason"))
            result, wrapper = parse_response(raw["choices"][0]["message"]["content"])
            errors = []
            if not isinstance(result.get("overall_summary"), str) or len(result["overall_summary"]) < 40:
                errors.append("overall_summary")
            for field in ("pending_issues", "chapter_omission_notes"):
                if not isinstance(result.get(field), list): errors.append(field)
            receipt.update(json_parsed=True, validation_errors=errors, format_wrapper_removed=wrapper)
            save(OUT / "result.json", result)
    except Exception as exc:
        receipt["error"] = str(exc)
    finally:
        receipt.update(elapsed_seconds=time.perf_counter()-start, ended_at=datetime.now(timezone.utc).isoformat())
        stop.set(); watcher.join(timeout=6)
        save(OUT / "resources.json", {"scope": "Host-wide samples during this single request, including other applications; not isolated memory attribution", "records": records})
        receipt["resources"] = {"samples": len(records), "min_available_ram_mib": min((r["ram_available_bytes"]/2**20 for r in records), default=None),
                                "peak_gpu_mib": max((r.get("gpu_used_mib", 0) for r in records), default=None)}
        save(receipt_path, receipt)
    success = receipt.get("http_status") == 200 and receipt.get("json_parsed") and not receipt.get("validation_errors") and not receipt.get("error")
    lines = ["# 32K 原始请求容量重测", "", "2026-10-03。仅重放先前被16K拒绝的同一请求，不重跑整章，不更新生产候选或人工确认。", "",
             "| 项目 | 原16K | 本次32K |", "|---|---|---|",
             f"| 服务上下文 | 16384 | 32768 |", f"| 请求哈希 | `{key}` | 相同 |",
             f"| HTTP | 400，17234 token超过窗口 | {receipt.get('http_status', '失败')} |",
             f"| 请求耗时 | {first_receipt['elapsed_seconds']:.2f}秒（拒绝） | {receipt['elapsed_seconds']:.2f}秒 |",
             f"| 输出上限 | {request['max_tokens']} | 相同 |", "",
             f"容量及基本JSON合同：{'通过' if success else '未通过，见receipt.json'}。",
             f"实际usage：`{json.dumps(receipt.get('usage'), ensure_ascii=False)}`。",
             f"结束原因：`{receipt.get('finish_reason')}`。资源采样：`{json.dumps(receipt['resources'], ensure_ascii=False)}`。", "",
             "请求内容、温度、seed、输出上限、权重、运行库、KV类型、槽位及CPU缓存参数均保持一致，仅将服务窗口16K改为32K。",
             "原16K已拒绝，没有可比较的生成速度；本次完整请求耗时不是32K/16K速度比。",
             "仅验证容量与基本JSON结构，没有独立医学复核，不代表整章质量通过、32K持续负载合格或原先四个阻断已解决。"]
    (OUT / "report.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(json.dumps({"success": bool(success), "elapsed_seconds": receipt["elapsed_seconds"], "http_status": receipt.get("http_status"), "error": receipt.get("error"), "report": str(OUT / "report.md")}, ensure_ascii=False))


if __name__ == "__main__": main()
