"""Replay a semantic-first project's accepted work under the current code — no model calls, no writes.

    python tools/replay.py DATA_ROOT WORKFLOW_ID [--out report.md]

Run it before committing a change to the cutter, the topic-pass contract or their checks. It reads the project
read-only, takes the raw results the executors submitted (immutable snapshots, matched to their tasks by hash) and
the briefs they were shown (task archives), and on an in-memory copy re-accepts the semantic map and every topic
pass in their original order. For each pass it reports:

- REFUSED: the current checks would refuse what was accepted (the reason is the check's own message);
- text changed under id: a sentence the result references whose current text is not the text the executor read in
  its brief — the result would be read against other text;
- missing: a referenced id the current cut no longer has;
- counts and signals that differ from the accepted record.

Exit status 1 when anything is refused or a reference changed text, so it can gate a change.

With --apply it writes back the passes re-accepted cleanly (current checks pass, every referenced sentence has
exactly the text the executor read): accepted work follows a rule or cutter change without a model call; the rest
stays stale for a real rerun.
"""
from __future__ import annotations

import argparse
import copy
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.deckflow import WorkflowError, digest  # noqa: E402
from app import semantic_map_stage as sm  # noqa: E402
from factdeck import topic_pass  # noqa: E402

KINDS = {"SEMANTIC_MAP": "semantic_map", "TOPIC_PASS": "topic_pass"}


def load(data_root: Path, workflow_id: str) -> dict:
    db = sqlite3.connect(f"file:{(data_root / 'workflow.sqlite3').as_posix()}?mode=ro", uri=True)
    row = db.execute("SELECT state FROM workflows WHERE id=?", (workflow_id,)).fetchone()
    if not row:
        raise SystemExit(f"no workflow {workflow_id} in {data_root}")
    return json.loads(row[0])


def snapshots(data_root: Path, w: dict) -> dict[str, dict]:
    """Raw submitted results by their hash (what a task's result_sha256 names)."""
    out = {}
    for f in sorted((data_root / w["id"] / "snapshots").glob("*.json")):
        with f.open(encoding="utf-8") as fh:
            head = fh.read(200)
        if not any(f'"kind": "{k}"' in head for k in KINDS.values()):
            continue
        value = json.loads(f.read_text(encoding="utf-8"))["value"]
        out[digest(value)] = value
    return out


def brief_of(data_root: Path, t: dict) -> dict:
    if t.get("archive"):
        heavy = json.loads((data_root / t["archive"]["path"]).read_text(encoding="utf-8"))["value"]
        return heavy.get("brief") or {}
    return t.get("brief") or {}


def shown_text(brief: dict) -> dict[str, str]:
    """Sentence id → the text the executor was shown in its brief."""
    rows = list(brief.get("sentences") or []) + list(brief.get("referred_from_other_topics") or [])
    return {r[0]: r[2] for r in rows if isinstance(r, list) and len(r) >= 3}


def referenced(result: dict, own: dict) -> set[str]:
    ids = {c for m in result.get("messages") or [] for c in m.get("claims") or []}
    ids |= {c for r in result.get("relations") or [] for c in r.get("basis") or []}
    ids |= {c for k in result.get("checks") or [] for c in k.get("claims") or []}
    for e in result.get("left_out") or []:
        try:
            ids |= set(topic_pass.expand(e, own))
        except topic_pass.TopicPassError:
            ids |= set(e.get("ids") or []) | {x for x in (e.get("from"), e.get("to")) if x}
    return ids


def replay(data_root: Path, workflow_id: str) -> dict:
    return _replay(data_root, workflow_id)[0]


def _replay(data_root: Path, workflow_id: str) -> tuple[dict, dict, dict]:
    """(report, the replayed in-memory project, the project as loaded)."""
    w0 = load(data_root, workflow_id)
    raw = snapshots(data_root, w0)
    done = [t for t in w0["tasks"] if t["kind"] in KINDS and t["status"] == "COMPLETE" and t.get("result_sha256") in raw]
    done.sort(key=lambda t: t.get("completed_at") or "")
    w = copy.deepcopy(w0)
    report = {"workflow": workflow_id, "map": None, "topics": [], "skipped": []}

    # the accepted map: the archived map result whose content is the accepted map, re-accepted under current checks;
    # without one (a map recorded by other means) the recorded map is kept
    accepted = w0.get("semantic_map")
    maps = [t for t in done if t["kind"] == "SEMANTIC_MAP"]
    match = next((t for t in reversed(maps) if accepted and digest(_payload(raw[t["result_sha256"]])) == digest(_payload(accepted["result"]))), None)
    if accepted and match:
        r = copy.deepcopy(raw[match["result_sha256"]])
        entry = {"input_changed": r.get("input_sha256") != sm.semantic_map_input(w)}
        r["input_sha256"] = sm.semantic_map_input(w)
        w["topic_passes"], w["semantic_map"] = {}, None
        try:
            sm.accept(w, r, match["worker"])
            entry["status"] = "OK"
        except WorkflowError as e:
            entry["status"], entry["reason"] = "REFUSED", str(e)
        report["map"] = entry
        if entry["status"] != "OK":
            return report, w, w0
    elif accepted:
        w["semantic_map"] = {**accepted, "input_sha256": sm.semantic_map_input(w)}
        report["map"] = {"status": "OK", "input_changed": accepted.get("input_sha256") != sm.semantic_map_input(w0),
                         "note": "no archived result matches the accepted map; the recorded map was kept"}
    w["topic_passes"] = {}

    # the passes the project holds now, each with the task that produced it, in acceptance order
    holds = {n: p for n, p in (w0.get("topic_passes") or {}).items()}
    tasks = {}
    for t in done:
        if t["kind"] == "TOPIC_PASS" and t["binding"] in holds:
            tasks[t["binding"]] = t                    # the latest completed task for the topic
    for node in sorted(holds, key=lambda n: holds[n].get("accepted_at") or ""):
        t = tasks.get(node)
        if not t:
            report["skipped"].append({"topic": node, "why": "no archived result for the accepted pass"})
            continue
        r = copy.deepcopy(raw[t["result_sha256"]])
        brief = brief_of(data_root, t)
        shown = shown_text(brief)
        referrals = [row[0] for row in brief.get("referred_from_other_topics") or []] if brief else None
        cl = sm.claims(w)
        own = {k: c for k, c in cl.items() if c.get("topic") == node or k in (referrals or [])}
        refs = referenced(r, own if own else cl)
        entry = {"topic": node, "task": t["id"], "input_changed": r.get("input_sha256") != sm.topic_input(w, node),
                 "missing": sorted(x for x in refs if x not in cl),
                 "text_changed": [{"id": x, "shown": shown[x], "now": cl[x]["quote"]} for x in sorted(refs)
                                  if x in cl and x in shown and " ".join(shown[x].split()) != " ".join(cl[x]["quote"].split())]}
        # references outside the brief (borrowed sentences) are checked against the anchors the pass was accepted on
        for x, a in sorted((holds[node]["result"].get("anchors") or {}).items()):
            if x in cl and x not in shown and sm.anchor(cl[x]["quote"]) != a:
                entry["text_changed"].append({"id": x, "shown": "（接受时的原文，见 anchors）", "now": cl[x]["quote"]})
            elif x not in cl and x not in entry["missing"]:
                entry["missing"].append(x)
        # a reference whose original text is known neither from the brief nor from an anchor cannot be vouched for
        entry["unverified"] = sorted(x for x in refs | set(referrals or []) if x in cl and x not in shown
                                     and x not in (holds[node]["result"].get("anchors") or {}))
        r["input_sha256"] = sm.topic_input(w, node)
        try:
            sm.accept_topic(w, node, r, t["worker"], referrals)
            new = w["topic_passes"][node]["result"]
            old = holds[node]["result"]
            entry["status"] = "OK"
            entry["counts"] = {k: [old["counts"].get(k), v] for k, v in new["counts"].items() if old["counts"].get(k) != v}
            entry["signals"] = {k: [_n(old["signals"].get(k)), _n(v)] for k, v in new["signals"].items()
                                if _n(old["signals"].get(k)) != _n(v)}
        except WorkflowError as e:
            entry["status"], entry["reason"] = "REFUSED", str(e)
        entry["applicable"] = (entry["status"] == "OK" and not entry["text_changed"] and not entry["missing"]
                               and not entry["unverified"])
        report["topics"].append(entry)
    return report, w, w0


def apply(data_root: Path, workflow_id: str) -> dict:
    """Write back the passes the replay re-accepted cleanly — current checks pass and every referenced sentence has
    exactly the text the executor read — so accepted work follows a code change without a model call. Anything else
    stays stale for a real rerun. Refuses if the project changed since it was read."""
    from app.deckflow import Store, now, require
    report, w, w0 = _replay(data_root, workflow_id)
    ok = [t for t in report["topics"] if t.get("applicable")]
    report["applied"] = []
    if not ok:
        return report
    st = Store(data_root)
    with st.transaction(workflow_id, "REPLAY_APPLY") as ww:
        require(digest(ww.get("topic_passes")) == digest(w0.get("topic_passes"))
                and digest(ww.get("semantic_map")) == digest(w0.get("semantic_map")), "项目在重放后已变更，请重新运行", 409)
        if not sm.semantic_map_current(ww):
            report["apply_note"] = "the recorded map is not current under this code; nothing applied"
            return report
        for t in ok:
            ww["topic_passes"][t["topic"]] = {**w["topic_passes"][t["topic"]],
                                              "reaccepted": {"by": "code:replay", "task": t["task"], "at": now()}}
            report["applied"].append(t["topic"])
        sm.refresh_summary(ww)
    return report


def _payload(r: dict) -> dict:
    """A map result's content, as accepted (the parsed form drops input_sha256)."""
    from factdeck.semantic_map import parse_semantic_map
    try:
        return parse_semantic_map({k: v for k, v in r.items() if k != "input_sha256"}).to_dict()
    except Exception:
        return r


def _where(a: str, b: str) -> tuple[str, str]:
    """The two texts from just before where they first differ."""
    a, b = " ".join(a.split()), " ".join(b.split())
    i = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    s = max(i - 12, 0)
    return ("…" if s else "") + a[s:s + 50], ("…" if s else "") + b[s:s + 50]


def _n(v):
    return len(v) if isinstance(v, (list, dict)) else v


def failed(report: dict) -> bool:
    return ((report["map"] or {}).get("status") == "REFUSED"
            or any(t["status"] == "REFUSED" or t["text_changed"] or t["missing"] for t in report["topics"]))


def markdown(report: dict) -> str:
    out = [f"# Replay {report['workflow']}\n"]
    m = report["map"]
    if m:
        out.append(f"- map: {m['status']}" + (f" — {m['reason']}" if m.get("reason") else "")
                   + (" (input changed)" if m["input_changed"] else "") + (f" — {m['note']}" if m.get("note") else ""))
    for t in report["topics"]:
        line = f"- {t['topic']}: {t['status']}" + (f" — {t['reason']}" if t.get("reason") else "")
        line += " (input changed)" if t["input_changed"] else ""
        line += f"; {len(t['text_changed'])} text changed under id" if t["text_changed"] else ""
        line += f"; {len(t['missing'])} missing" if t["missing"] else ""
        line += f"; {len(t['unverified'])} without a known original text" if t.get("unverified") else ""
        line += "; applied" if t["topic"] in report.get("applied", []) else ""
        line += f"; counts {t['counts']}" if t.get("counts") else ""
        line += f"; signals {t['signals']}" if t.get("signals") else ""
        out.append(line)
        for x in t["text_changed"][:5]:
            a, b = _where(x["shown"], x["now"])
            out.append(f"  - {x['id']}: shown「{a}」now「{b}」")
        if t["missing"]:
            out.append("  - missing: " + "、".join(t["missing"][:8]))
    for s in report["skipped"]:
        out.append(f"- {s['topic']}: skipped — {s['why']}")
    out.append("\nRESULT: " + ("FAIL" if failed(report) else "PASS"))
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("data_root", type=Path)
    ap.add_argument("workflow_id")
    ap.add_argument("--out", type=Path, help="write the markdown report here (JSON beside it)")
    ap.add_argument("--apply", action="store_true", help="write back the passes re-accepted cleanly (no model call)")
    a = ap.parse_args()
    report = (apply if a.apply else replay)(a.data_root.resolve(), a.workflow_id)
    md = markdown(report)
    if a.out:
        a.out.write_text(md, encoding="utf-8")
        a.out.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.stdout.write(md)
    sys.exit(1 if failed(report) else 0)


if __name__ == "__main__":
    main()
