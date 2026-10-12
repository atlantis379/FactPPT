"""Summarize measured draft/review artifacts; never infer cloud bills or approve."""
from __future__ import annotations
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.chapter_draft_benchmark import normalize_metadata, validate_page
from app.worker_context import unpack

OUT = ROOT / "output/chapter_draft_benchmark"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    manifest = read(OUT / "manifest.json")
    origin = datetime.fromisoformat(manifest["created_at"]).timestamp()
    specs = [("sol", "6.1 Sol", "candidate_k7", "candidate_k7_v2"),
             ("luna", "6 Luna", "candidate_r4_v2", "candidate_r4_v3"),
             ("local", "Bonsai27B", "candidate_n2", "candidate_n2_v2")]
    results = []
    for folder, model, first, final in specs:
        location = OUT / folder
        record = {"group": folder, "model": model, "cloud_tokens": None, "actual_fee": None}
        chapter = location / "chapter.result.json"
        if chapter.exists(): record["first_draft_archived_seconds_from_common_start"] = chapter.stat().st_mtime - origin
        if (location / "run.json").exists():
            run = read(location / "run.json")
            record["run"] = {k: v for k, v in run.items() if k != "records"}
            record["run"]["record_count"] = len(run.get("records", []))
        for label, blind in (("first_review", first), ("revision_review", final)):
            path = OUT / "review" / blind / "validation_report.json"
            if path.exists():
                record[label] = read(path)
                record[label + "_archived_seconds_from_common_start"] = path.stat().st_mtime - origin
        if folder == "local":
            first_receipts = [read(p) for p in location.glob("S03_*.receipt.json")]
            repair_receipts = [read(p) for p in (location / "structural_repair").glob("S03_*.receipt.json")]
            revision_receipts = [read(p) for p in (location / "revision1").glob("S03_*.receipt.json")]
            usages = [r.get("usage") or (r.get("response") or {}).get("usage") or {} for r in first_receipts + repair_receipts + revision_receipts]
            synth = location / "structural_repair/synthesis.receipt.json"
            if synth.exists(): usages.append((read(synth).get("response") or {}).get("usage") or {})
            global_receipts = [read(p) for p in (location / "revision1").glob("synthesis*.receipt.json")]
            for r in global_receipts: usages.append((r.get("response") or {}).get("usage") or {})
            record.update(first_requests=len(first_receipts),
                          first_structural_failures=sum(bool(r.get("error") or r.get("validation_errors")) for r in first_receipts),
                          structural_repair_model_calls=sum(r.get("model_calls", 0) for r in repair_receipts),
                          structural_repair_seconds=sum(r.get("elapsed_seconds", 0) for r in repair_receipts),
                          semantic_revision_model_calls=sum(r.get("model_calls", 0) for r in revision_receipts),
                          semantic_revision_seconds=sum(r.get("elapsed_seconds", 0) for r in revision_receipts),
                          semantic_revision_failed_repairs=sum(bool(r.get("retained_previous_candidate")) for r in revision_receipts),
                          global_revision_requests=sum(r.get("model_calls", 0) for r in global_receipts),
                          global_revision_seconds=sum(r.get("elapsed_seconds", 0) for r in global_receipts),
                          global_capacity_rejections=sum("400 Bad Request" in r.get("error", "") and not r.get("response") for r in global_receipts),
                          first_request_seconds=sum(r.get("elapsed_seconds", 0) for r in first_receipts),
                          local_prompt_tokens=sum(u.get("prompt_tokens", 0) for u in usages),
                          local_completion_tokens=sum(u.get("completion_tokens", 0) for u in usages),
                          local_cached_prompt_tokens=sum((u.get("prompt_tokens_details") or {}).get("cached_tokens", 0) for u in usages))
            production_failures = []
            for c in manifest["cases"]:
                result_file = location / (c["id"].replace(":", "_") + ".result.json")
                if result_file.exists():
                    brief = unpack(read(OUT / c["file"]))
                    result, _ = normalize_metadata(read(result_file), brief)
                    errors = validate_page(result, brief)
                    if errors: production_failures.append({"id": c["id"], "errors": errors})
                elif (location / (c["id"].replace(":", "_") + ".receipt.json")).exists():
                    production_failures.append({"id": c["id"], "errors": ["parse_or_request_failed"]})
            record["first_failures_after_deterministic_metadata_repair"] = production_failures
            coverage_chars = result_chars = 0
            for path in location.glob("S03_*.result.json"):
                row = read(path)
                coverage_chars += len(json.dumps(row.get("coverage", {}), ensure_ascii=False, separators=(",", ":")))
                result_chars += len(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            record["parsed_first_output_coverage_character_share"] = coverage_chars / result_chars if result_chars else None
            latencies = sorted(r["elapsed_seconds"] for r in first_receipts if "elapsed_seconds" in r)
            record["first_latency_median_seconds"] = statistics.median(latencies) if latencies else None
            record["first_latency_p95_seconds"] = latencies[max(0, math.ceil(.95 * len(latencies)) - 1)] if latencies else None
            if len(first_receipts) == manifest["source_pages"]:
                record["first_page_pass_archived_seconds_from_common_start"] = max(p.stat().st_mtime for p in location.glob("S03_*.receipt.json")) - origin
            repaired_chapter = location / "structural_repair/chapter.result.json"
            if repaired_chapter.exists():
                record["first_draft_archived_seconds_from_common_start"] = repaired_chapter.stat().st_mtime - origin
        results.append(record)
    resource_file = OUT / "resources.json"
    resources = read(resource_file) if resource_file.exists() else {}
    samples = resources.get("records", [])
    phases = {}
    stop_file = OUT / "server_stop_first.json"
    launch_file = OUT / "runtime_bounded/server_launch.json"
    if stop_file.exists() and launch_file.exists():
        first_end = datetime.fromisoformat(read(stop_file)["stopped_at"]).timestamp()
        bounded_start = datetime.fromisoformat(read(launch_file)["started_at"]).timestamp()
        for label, rows in (("first_default_cache", [r for r in samples if r["utc_epoch"] <= first_end]),
                            ("bounded_cache_repair", [r for r in samples if r["utc_epoch"] >= bounded_start])):
            available = [r["ram_available_bytes"] / 2**20 for r in rows]
            phases[label] = {"samples": len(rows), "min_available_ram_mib": min(available, default=None),
                             "median_available_ram_mib": statistics.median(available) if available else None,
                             "peak_gpu_mib": max((r.get("gpu_used_mib", 0) for r in rows), default=None)}
    report = {"schema": "chapter_benchmark_report.v1", "updated_at": datetime.now(timezone.utc).isoformat(),
              "source_pages": manifest["source_pages"], "source_claims": manifest["claim_count"], "results": results,
              "resources": {"samples": len(samples), "scope": resources.get("scope"),
                            "min_available_ram_mib": min((r["ram_available_bytes"] / 2**20 for r in samples), default=None),
                            "peak_gpu_mib": max((r.get("gpu_used_mib", 0) for r in samples), default=None),
                            "phases": phases},
              "human_confirmations": 0, "cloud_billing_data_available": False,
              "context_interpretation": {"experiment_effective_tokens": 16384, "user_target_tokens": 32768,
                  "current_gguf_declared_tokens": 262144, "installed_default_script_tokens": 65536,
                  "installed_default_script_kv": "q4_0", "larger_context_workflow_qualified": False,
                  "capacity_rejection_cause": "Experiment service configured at 16K, not the model's intrinsic 32K limit"}}
    retest_file = ROOT / "output/chapter_context_32k_retest/receipt.json"
    retest = read(retest_file) if retest_file.exists() else None
    if retest:
        report["context_capacity_retest"] = {k: retest.get(k) for k in
            ("request_sha256", "same_request_verified", "context", "http_status", "usage", "finish_reason", "json_parsed", "validation_errors", "elapsed_seconds", "resources", "medical_review_performed")}
    (OUT / "comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 同章首稿与独立审核实测", "", "2026-10-03；来源：S03，29页、376条论断。现网状态未改变。", "",
             "## 当前结果", "", "| 执行端 | 首稿审核阻断/提示 | 修订审核阻断/提示 | 待处理问题 | 可进入人工内容确认 |", "|---|---:|---:|---:|---|"]
    for r in results:
        first, final = r.get("first_review"), r.get("revision_review")
        def counts(value): return f"{value['blockers']} / {value['notes']}" if value else "待完成"
        current = final or first
        lines.append(f"| {r['model']} | {counts(first)} | {counts(final)} | {current['pending_issue_count'] if current else '待统计'} | {'是，仍须人工确认' if current and current['eligible_for_human_confirmation'] else '否 / 待完成'} |")
    lines += ["", "## 时间与费用口径", "",
              "共同起点是冻结manifest时间。到产物归档的时间包含执行端调度、代码、等待及审核，不等于纯模型推理时间。两名云端作者的计时起点不完整；Luna首稿run中的0.086秒是写文件/校验区间，不能当成首稿生成耗时。云端API计费token与实际费用未知，不用读取文件字节或本地token推算。",
              "", "| 执行端 | 首稿归档距共同起点 | 首轮审核归档距共同起点 | 修订复核归档距共同起点 |", "|---|---:|---:|---:|"]
    for r in results:
        def minutes(key): return f"{r[key]/60:.2f}分钟" if key in r else "待完成"
        lines.append(f"| {r['model']} | {minutes('first_draft_archived_seconds_from_common_start')} | {minutes('first_review_archived_seconds_from_common_start')} | {minutes('revision_review_archived_seconds_from_common_start')} |")
    local = next(r for r in results if r["group"] == "local")
    lines += ["", f"本地首轮已存档请求{local['first_requests']}次，累计请求{local['first_request_seconds']/60:.2f}分钟。原脚本标记{local['first_structural_failures']}页异常（含已撤回的要点条数限制）；撤回限制并补固定元数据后仍有{len(local['first_failures_after_deterministic_metadata_repair'])}页结构/解析失败。针对性结构修复调用{local['structural_repair_model_calls']}次。服务实报输入{local['local_prompt_tokens']}、输出{local['local_completion_tokens']} token，包含缓存输入{local['local_cached_prompt_tokens']} token。这些是本地计数。电费、设备摊销和云端对照费用未测。",
              f"本地页面语义修订请求{local['semantic_revision_model_calls']}次，累计请求{local['semantic_revision_seconds']/60:.2f}分钟，失败后保留上一版本{local['semantic_revision_failed_repairs']}页；全局修订请求{local['global_revision_requests']}次，其中上下文容量拒绝{local['global_capacity_rejections']}次。格式修复与语义修订分开计数。",
              "", "## 边界", "",
              "- 三组使用同一冻结来源与逐页合同，使用同一独立审核者的summary_review.v2逐项验收；未完成的审核在表中标注。云端Codex agent与本地HTTP执行方式不同；这是实际执行过程对照，不能解释成受控的纯模型速度排名。",
              "- coverage的全部ID仅说明完整输入遍历登记；不证明语义无遗漏。首稿、错误、代码修复、修订及审核各自保留。",
              "- 本地请求让模型输出完整coverage编号；云端执行端可以用代码填固定编号。因此执行时间也包含不同的元数据处理方式。本地已解析首稿中coverage占紧凑JSON字符约21%，字符占比不是token或费用占比；后续应由代码维护请求遍历账本，模型仍须对实际观点给出来源引用。",
              "- 本地首稿为串行单页请求，跨页续句可能不可见；云端执行端已读整章。修订为需要的页面增加实际邻页原单元，并允许生产合同支持的跨页引用。首轮限制和执行差异均使本实验不适合比较纯模型能力，未达到可确认版本时如实记失败终点。",
              "- 上下文纠正：本次两个服务回执均为16384（16K），用户指出的当前预算为32768（32K）。17234 token请求的拒绝由本次16K服务配置造成，不能作为32K模型能力限制。当前GGUF元数据声明262144，安装目录默认脚本为65536配q4_0 KV；这些是声明或配置，不是本流程已验证的有效容量。未测32K/64K下的同输入工作流，保留16K原回执，不改写历史。",
              "- 首轮提示误增每页1至3条要点上限，原生产合同没有这个要求。上限现已撤回，原稿和首轮失败记录保留；超出条数本身不算生产失败，不删内容来通过。云端首稿曾受到该提示影响，因此遗漏/密度比较受实验设计影响，不能用本章给出通用模型能力排名。所有未决事项仍阻止内容确认，不能把0阻断写成已可交付。",
              "- 本地首轮未限制llama-server默认8192MiB CPU提示缓存。修复和修订阶段使用cache-ram=0，另存参数和计时，不静默替换首轮记录。资源采样中途开始，曾因Windows文件锁中断，修复后恢复；记录有缺口且包含同机其他程序，不能当全程峰值、推算SaaS并发或归因全部内存。",
              "- 最后一轮审核执行端自报定位公共原文时打印了来源profile；该profile本来属于冻结共同输入，未读取候选作者目录、运行参数或费用。自报备注保留在reviewer_run.json；本试验仅隐藏候选作者标签，不声明为严格双盲研究。",
              "- 六页视觉试验、Adobe执行端与PPT主线没有因本次内容实验改变。", "",
              "## 实施与后续分工", "",
              "代码优先：无损证据包、审核目标覆盖、短回执、资产哈希复用、单槽排队、严格JSON及来源编号校验。详见项目CONTEXT_IMPLEMENTATION.md。",
              "",
              "本章两组云端候选的一轮修订结果中，Sol剩0阻断、Luna剩4阻断；暂将6.1 Sol用于条件密集总结和独立忠实度复核，6 Luna用于需要完整独立审核的首稿候选。这是本项目的暂定分工，首轮阻断计数不是通用准确率，两组输出密度不同，不能据单章为全部任务授予模型资格。",
              "",
              "Bonsai的16K单页执行方案在本机首轮累计请求41.34分钟，另有格式修复、全局汇总、12页语义修订及两轮独立复核；该方案未显示完整总结流程的时间优势，仍有阻断，暂未取得生产总结或正式审核资格。32K方案未实测，不能据本轮否定。后续以用户32K预算组织完整小节及邻页证据，为提示词和输出预留空间，再用相同证据范围、相同元数据处理及审核流程比较。扩大配置窗口本身不等于已发现的语义错误解决或推理速度提升。",
              "",
              "三组均在一轮语义修订后结束，未达到可确认版本。因此到可确认版本的总历时与费用均无法给出；表中是已实际发生的阶段时间和返工，不是完工报价。正式内容、语义审核和人工确认仍保持原流程。"]
    if retest:
        lines += ["", "## 后续32K单请求重测", "",
                  f"对先前被16K拒绝的原始请求原样重放：请求哈希一致，仅将服务窗口改为32768；HTTP {retest.get('http_status')}，请求耗时{retest['elapsed_seconds']:.2f}秒，实际输入{retest['usage']['prompt_tokens']}、输出{retest['usage']['completion_tokens']} token，基本JSON合同通过，finish_reason={retest.get('finish_reason')}。",
                  "本次证实该请求可以装入32K。未重跑29页或进行独立医学审核，不修改此前三组质量分数、人工确认或生产候选；32K整章质量和全流程时间仍未验证。详见output/chapter_context_32k_retest/report.md。"]
    (OUT / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"report": str((OUT / 'comparison.md').resolve()), "local_completed": local['first_requests']}, ensure_ascii=False))


if __name__ == "__main__": main()
