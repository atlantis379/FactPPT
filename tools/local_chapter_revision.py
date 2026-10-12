"""One isolated local semantic revision, driven by an accepted independent review."""
from __future__ import annotations
import argparse
import shutil
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timezone

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.chapter_draft_benchmark import OUT, read, save, normalize_metadata, validate_page, parse_response, assemble
from app.worker_context import canonical, fingerprint, unpack


def selected_pages(review):
    selected = set()
    for section in review["sections"]:
        if section["summary_verdict"] != "ENTAILED" or any(p["verdict"] != "ENTAILED" for p in section["key_points"]):
            selected.add(section["section_id"])
    for issue in review["issues"]:
        if issue["severity"] == "BLOCKER":
            selected.update(re.findall(r"S\d+:p\d+", issue["ref"]))
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--blind-id", required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8083")
    parser.add_argument("--retry-global-capacity", action="store_true", help="Once, after an HTTP 400 rejection with no generated response; use only relevant pages")
    args = parser.parse_args()
    out = args.out
    folder = out / "local/revision1"
    if args.retry_global_capacity:
        previous = read(folder / "synthesis.receipt.json")
        archive = folder / "synthesis.capacity_failure.receipt.json"
        if archive.exists() or "400 Bad Request" not in previous.get("error", "") or "response" in previous or "result" in previous:
            raise ValueError("Capacity retry only once, after rejection without a generated result")
        (folder / "synthesis.receipt.json").rename(archive)
        (folder / "synthesis.request.json").rename(folder / "synthesis.capacity_failure.request.json")
        shutil.copyfile(folder / "run.json", folder / "run.before_capacity_retry.json")
    source = out / "local/structural_repair"
    review_folder = out / "review" / args.blind_id
    validation = read(review_folder / "validation_report.json")
    if not validation["review_contract_accepted"] or not validation["candidate_contract_accepted"]:
        raise ValueError("An accepted first candidate and independent review are required")
    review = read(review_folder / "result.json")
    manifest = read(out / "manifest.json")
    candidate = read(source / "chapter.result.json")
    selected = selected_pages(review)
    identity = {"candidate_sha256": fingerprint(candidate), "review_sha256": fingerprint(review),
                "selected_pages": sorted(selected), "started_at": datetime.now(timezone.utc).isoformat(),
                "selection": "all non-ENTAILED summary/key-point verdicts and pages named in BLOCKER refs; no semantic revision beyond revision1"}
    version_file = folder / "version.json"
    if version_file.exists():
        old = read(version_file)
        if any(old[k] != identity[k] for k in ("candidate_sha256", "review_sha256", "selected_pages")):
            raise ValueError("Revision cache version changed")
    else:
        save(version_file, identity)
    started = time.perf_counter()
    records = []
    with httpx.Client(timeout=600, trust_env=False) as client:
        response = client.get(args.endpoint.rstrip("/") + "/v1/models"); response.raise_for_status()
        model = response.json()["data"][0]["id"]
        for index, case in enumerate(manifest["cases"]):
            name = case["id"].replace(":", "_")
            original_file = source / (name + ".result.json")
            record_file = folder / (name + ".receipt.json")
            if record_file.exists():
                records.append(read(record_file)); continue
            if case["id"] not in selected:
                shutil.copyfile(original_file, folder / original_file.name)
                record = {"id": case["id"], "model_calls": 0, "unchanged": True}
                save(record_file, record); records.append(record); continue
            packet = read(out / case["file"]); brief = unpack(packet)
            section_review = next(s for s in review["sections"] if s["section_id"] == case["id"])
            related_issues = [i for i in review["issues"] if case["id"] in set(re.findall(r"S\d+:p\d+", i["ref"] + " " + i["problem"]))]
            neighbor_ids = {manifest["cases"][i]["id"] for i in (index-1, index+1) if 0 <= i < len(manifest["cases"])}
            for issue in related_issues:
                neighbor_ids.update(re.findall(r"S\d+:p\d+", issue["problem"]))
            neighbors = []
            neighbor_briefs = []
            for c in manifest["cases"]:
                if c["id"] in neighbor_ids and c["id"] != case["id"]:
                    evidence = unpack(read(out / c["file"]))
                    neighbor_briefs.append(evidence)
                    neighbors.append({"page": evidence["page"], "units": evidence["units"]})
            content = {"packet": packet, "original_candidate": read(original_file), "review": section_review,
                       "issues": related_issues, "neighbor_evidence": neighbors,
                       "instruction": "依据实际原文修复独立审核指出的问题，保留全部重要事实、数字、符号、条件、否定和限制。key_points无条数上限，撤回首轮1至3条提示。跨页续句可引用所提供邻页的实际unit_ids，并将相应邻页加入source_page_ids；不能猜编号。coverage仍保留主页面的原固定清单。只返回本页完整JSON。已解决问题可移除pending_issues，无法解决则保留并说明，不能自行批准医学内容。"}
            request = {"model": model, "messages": [{"role": "system", "content": manifest["system"]}, {"role": "user", "content": canonical(content)}],
                       "temperature": 0, "seed": 42, "max_tokens": 4000, "response_format": {"type": "json_object"}}
            record = {"id": case["id"], "model_calls": 1, "started_at": datetime.now(timezone.utc).isoformat(), "request_sha256": fingerprint(request)}
            save(folder / (name + ".request.json"), request)
            start = time.perf_counter()
            result = read(original_file)
            try:
                response = client.post(args.endpoint.rstrip("/") + "/v1/chat/completions", json=request); response.raise_for_status()
                raw = response.json(); record["response"] = raw
                proposed, wrapped = parse_response(raw["choices"][0]["message"]["content"])
                proposed, repairs = normalize_metadata(proposed, brief, neighbor_briefs)
                errors = validate_page(proposed, brief, neighbor_briefs)
                record.update(validation_errors=errors, metadata_repairs=repairs, format_wrapper_removed=wrapped)
                if not errors: result = proposed
                else: record["retained_previous_candidate"] = True
            except Exception as exc:
                record.update(error=str(exc), retained_previous_candidate=True)
                if isinstance(exc, httpx.HTTPStatusError):
                    record.update(http_status=exc.response.status_code, response_body=exc.response.text)
            record["elapsed_seconds"] = time.perf_counter() - start
            save(folder / original_file.name, result)
            save(record_file, record); records.append(record)
            print(canonical({"revision": case["id"], "seconds": record["elapsed_seconds"], "errors": record.get("validation_errors"), "error": record.get("error")}), flush=True)
    global_synthesis = read(source / "synthesis.receipt.json")["result"]
    global_issues = [i for i in review["issues"] if not re.findall(r"S\d+:p\d+", i["ref"])]
    synthesis_file = folder / "synthesis.receipt.json"
    if global_issues:
        if synthesis_file.exists():
            saved = read(synthesis_file)
            if "result" in saved: global_synthesis = saved["result"]
        else:
            global_pages = {p for i in global_issues for p in re.findall(r"S\d+:p\d+", i["problem"])}
            actual_units = [unpack(read(out / c["file"]))["units"] for c in manifest["cases"] if c["id"] in global_pages]
            rows = [read(folder / (c["id"].replace(":", "_") + ".result.json")) for c in manifest["cases"]]
            content = {"previous_synthesis": global_synthesis, "global_review": global_issues,
                       "original_units": actual_units, "revised_pages": [{"id": r["id"], "summary": r["summary"], "pending_issues": r["pending_issues"]} for r in rows if r["id"] in global_pages],
                       "instruction": "仅依据实际原文修复全局审核指出的章节总述错误，其他事实、主题及未决问题保留，不添加新医学观点。保留诊疗条件、否定和并列分类。已解决的全局问题可删除，无法解决的pending_issues保留。只返回overall_summary、pending_issues、chapter_omission_notes；至少40字，不重写sections，不批准内容。"}
            request = {"model": model, "messages": [{"role": "system", "content": manifest["system"]}, {"role": "user", "content": canonical(content)}], "temperature": 0, "seed": 42, "max_tokens": 2200, "response_format": {"type": "json_object"}}
            save(folder / "synthesis.request.json", request)
            record = {"model_calls": 1, "started_at": datetime.now(timezone.utc).isoformat(), "request_sha256": fingerprint(request)}
            start = time.perf_counter()
            try:
                with httpx.Client(timeout=600, trust_env=False) as client:
                    response = client.post(args.endpoint.rstrip("/") + "/v1/chat/completions", json=request); response.raise_for_status()
                    raw = response.json(); record["response"] = raw
                    proposed, _ = parse_response(raw["choices"][0]["message"]["content"])
                    if not isinstance(proposed.get("overall_summary"), str) or len(proposed["overall_summary"]) < 40 or not isinstance(proposed.get("pending_issues"), list) or not isinstance(proposed.get("chapter_omission_notes"), list):
                        raise ValueError("Incomplete global synthesis contract")
                    global_synthesis = proposed; record["result"] = proposed
            except Exception as exc:
                record.update(error=str(exc), retained_previous_candidate=True)
            record["elapsed_seconds"] = time.perf_counter()-start
            save(synthesis_file, record)
    assemble(out, "local/revision1", global_synthesis)
    prior_elapsed = read(folder / "run.before_capacity_retry.json").get("elapsed_seconds_this_run", 0) if args.retry_global_capacity else 0
    save(folder / "run.json", {"model": model, "elapsed_seconds_this_run": prior_elapsed+time.perf_counter()-started,
         "selected_pages": sorted(selected), "model_calls": sum(r["model_calls"] for r in records),
         "failed_repairs": sum(bool(r.get("retained_previous_candidate")) for r in records),
         "global_synthesis_unchanged": not global_issues, "capacity_retry": args.retry_global_capacity, "independent_recheck_required": True})


if __name__ == "__main__": main()
