"""Offline, lossless task-payload measurement; never calls workflow APIs/models.

This prototype measures exact repeated text and a reversible shared-text envelope.
It does not qualify the envelope as a production model prompt.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
REF = "$shared_text"


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def metrics(obj):
    text = canonical(obj)
    return {"utf8_bytes": len(text.encode("utf-8")), "characters": len(text),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def visit(node):
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from visit(value)
    elif isinstance(node, list):
        for value in node:
            yield from visit(value)


def pack(payload):
    """Intern identical complete strings only. Source identities remain separate."""
    if any(isinstance(n, dict) and REF in n for n in visit(payload)):
        raise ValueError("Input conflicts with reserved reference key")
    counts = Counter(n for n in visit(payload) if isinstance(n, str) and len(n) >= 80)
    selected = {}
    for text, count in counts.items():
        if count < 2:
            continue
        key = f"t{len(selected)+1}"
        literal = len(canonical(text).encode("utf-8"))
        ref_bytes = len(canonical({REF: key}).encode("utf-8"))
        entry_overhead = len(canonical(key).encode("utf-8")) + 2
        if count * literal > literal + entry_overhead + count * ref_bytes:
            selected[text] = key
    def transform(node):
        if isinstance(node, str) and node in selected:
            return {REF: selected[node]}
        if isinstance(node, dict):
            return {k: transform(v) for k, v in node.items()}
        if isinstance(node, list):
            return [transform(v) for v in node]
        return node
    return {"schema": "context_assessment.shared_text.v1", "instructions": "Read shared_texts as exact source text. References preserve the entire string; no text is omitted.",
            "payload": transform(payload), "shared_texts": {key: text for text, key in selected.items()}}


def unpack(envelope):
    texts = envelope["shared_texts"]
    def restore(node):
        if isinstance(node, dict) and set(node) == {REF}:
            return texts[node[REF]]
        if isinstance(node, dict):
            return {k: restore(v) for k, v in node.items()}
        if isinstance(node, list):
            return [restore(v) for v in node]
        return node
    return restore(envelope["payload"])


def duplicates(payload):
    counts = Counter(n for n in visit(payload) if isinstance(n, str) and len(n) >= 80)
    return {"repeated_distinct_strings": sum(c > 1 for c in counts.values()),
            "extra_occurrences": sum(c - 1 for c in counts.values() if c > 1),
            "redundant_raw_text_utf8_bytes": sum(len(t.encode("utf-8")) * (c - 1) for t, c in counts.items() if c > 1)}


def unit_stats(payload):
    entries = defaultdict(list)
    for n in visit(payload):
        if isinstance(n, dict) and isinstance(n.get("id"), str) and isinstance(n.get("text"), str) and "#" not in n["id"]:
            entries[n["id"]].append(n["text"])
    return {"occurrences": sum(len(v) for v in entries.values()), "unique_ids": len(entries),
            "conflicting_text_ids": [k for k, v in entries.items() if len(set(v)) > 1],
            "same_id_redundant_text_utf8_bytes": sum(sum(len(t.encode("utf-8")) for t in v) - len(v[0].encode("utf-8")) for v in entries.values() if len(set(v)) == 1)}


def measure(payload):
    tick = time.perf_counter()
    envelope = pack(payload)
    restored = unpack(envelope)
    if restored != payload or metrics(restored)["sha256"] != metrics(payload)["sha256"]:
        raise AssertionError("Lossless roundtrip failed")
    before, after = metrics(payload), metrics(envelope)
    return envelope, {"original": before, "packed": after, "saved_utf8_bytes": before["utf8_bytes"] - after["utf8_bytes"],
                      "saved_percent": round(100 * (1 - after["utf8_bytes"] / before["utf8_bytes"]), 2),
                      "roundtrip_equal": True, "duplicate_text": duplicates(payload), "unit_text": unit_stats(payload),
                      "pack_and_verify_seconds": round(time.perf_counter() - tick, 4)}


def invariants():
    text = "PaO2 ≤55毫米汞柱；病史及问卷；可能而非必然；剂量300 mg/2 weeks；" * 8
    original = {"units": [{"id": "source-A", "text": text}, {"id": "source-B", "text": text}],
                "changed": {"id": "source-C", "text": text.replace("≤", "<")}, "rules": ["必须全覆盖"]}
    envelope = pack(original)
    assert unpack(envelope) == original
    assert envelope["payload"]["units"][0]["id"] != envelope["payload"]["units"][1]["id"]
    assert envelope["payload"]["changed"]["text"] == original["changed"]["text"]
    ref = envelope["payload"]["units"][0]["text"][REF]
    bad = json.loads(canonical(envelope))
    del bad["shared_texts"][ref]
    try:
        unpack(bad)
    except KeyError:
        pass
    else:
        raise AssertionError("Missing evidence did not fail closed")
    try:
        pack({REF: "preexisting"})
    except ValueError:
        pass
    else:
        raise AssertionError("Reserved input was silently overwritten")
    return {"roundtrip": True, "source_ids_preserved": True, "operator_change_stays_distinct": True,
            "missing_reference_rejected": True, "reserved_key_collision_rejected": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "output/context_assessment")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    files = {"SUMMARY": ROOT / "data/worker/chapter_intake/SUMMARY_task.json",
             "SUMMARY_REVIEW": ROOT / "data/worker/chapter_summary_review_C.json"}
    results = {"metric_scope": "canonical brief only; UTF-8 bytes/characters, not billable tokens", "invariant_checks": invariants(), "tasks": {}}
    payloads = {}
    for kind, path in files.items():
        raw = path.read_bytes()
        brief = json.loads(raw.decode("utf-8-sig"))["brief"]
        payloads[kind] = brief
        envelope, stats = measure(brief)
        stats.update(source_path=str(path), source_file_bytes=len(raw), source_file_sha256=hashlib.sha256(raw).hexdigest())
        results["tasks"][kind] = stats
        (out / f"{kind}_packed.json").write_text(canonical(envelope), encoding="utf-8")
    # Conservative 8 chapter review packets: all existing common fields/rules repeated,
    # each packet keeps full source units for that chapter. No quote-only truncation.
    review = payloads["SUMMARY_REVIEW"]
    rows = []
    for section in review["sections"]:
        chapter = dict(review)
        chapter["sections"] = [section]
        chapter["result_contract"] = dict(review["result_contract"])
        chapter["result_contract"]["sections"] = [r for r in review["result_contract"]["sections"] if r["section_id"] == section["section_id"]]
        env, stats = measure(chapter)
        rows.append({"section_id": section["section_id"], **stats})
        (out / f"review_{section['section_id']}_packed.json").write_text(canonical(env), encoding="utf-8")
    total = sum(r["packed"]["utf8_bytes"] for r in rows)
    original = metrics(review)["utf8_bytes"]
    results["review_chapters"] = {"packets": rows, "sum_packed_utf8_bytes": total, "max_packet_utf8_bytes": max(r["packed"]["utf8_bytes"] for r in rows),
                                 "saved_percent_vs_one_original": round(100*(1-total/original), 2),
                                 "semantic_verdict_coverage": "Existing unstructured key_points result slots are missing; production split is blocked until contract coverage is repaired"}
    # Repeated chapter generation/resume can reuse identical packets only as artifacts.
    # Independent review tasks never reuse author verdicts; task lease is not in the model prompt.
    results["cross_task_shared_text"] = duplicates(list(payloads.values()))
    results["limitations"] = ["No model inference or tokenization in this run", "Shared references need worker support and model comprehension testing", "Chapter splits evaluated for byte size, not cross-chapter semantic quality", "No production tasks, approvals or runtime routes modified"]
    (out / "assessment.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"tasks": {k: {x: v[x] for x in ['original', 'packed', 'saved_percent', 'roundtrip_equal']} for k, v in results['tasks'].items()},
                      "chapter_review_total_bytes": total, "chapter_max_bytes": results["review_chapters"]["max_packet_utf8_bytes"],
                      "chapter_review_saved_percent": results["review_chapters"]["saved_percent_vs_one_original"],
                      "invariants": results["invariant_checks"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
