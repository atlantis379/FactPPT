"""Fail-closed M0 governance checks. Uses only the Python standard library."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FROZEN_GLOBS = ("docs/specs/*.md", "docs/decisions/ADR-*.md", "schemas/v0_2/**/*")
REQUIRED_RULES = {
    "CORE-001", "EVID-001", "TRACE-001", "NUM-001", "NUM-002", "REL-001",
    "STATE-001", "STATE-002", "SCHEMA-001", "MILESTONE-001", "MILESTONE-002",
    "CHANGE-001", "TEST-001", "CI-001", "AUDIT-001", "REVIEW-001",
    "IDEMP-001", "SEC-001",
}
BOOTSTRAP_PATHS = (
    "docs/specs/DEVELOPMENT_CONTRACT.md", "docs/specs/SYSTEM_SPEC_v0.3.md",
    "docs/decisions/ADR-006-sol-mainline.md", "evaluation/evaluation_thresholds.yaml",
)
SKIP_PATTERN = re.compile(r"\b(?:unittest\.)?skip(?:If|Unless)?\s*\(|@(?:unittest\.)?skip(?:If|Unless)?\b|pytest\.mark\.skip(?:if)?\b|pytest\.skip\s*\(")


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


def has_executable_skip(source: str) -> bool:
    tree = ast.parse(source)
    skip_names = {
        "skip", "skipIf", "skipUnless", "unittest.skip", "unittest.skipIf",
        "unittest.skipUnless", "pytest.skip", "pytest.mark.skip", "pytest.mark.skipif",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and dotted_name(node.func) in skip_names:
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if any(dotted_name(decorator) in skip_names for decorator in node.decorator_list):
                return True
    return False


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def section_items(text: str, heading: str) -> list[str]:
    match = re.search(rf"(?m)^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not match:
        raise ValueError(f"missing section: {heading}")
    return re.findall(r"(?m)^- (.+?)\s*$", match.group(1))


def check_manifest(root: Path = ROOT) -> None:
    check_line_endings_policy(root)
    manifest = json.loads((root / "schemas/frozen_manifest.json").read_text(encoding="utf-8"))
    artifacts = manifest["artifacts"]
    if not artifacts or len(artifacts) != len(set(artifacts)):
        raise ValueError("frozen manifest empty or duplicate")
    expected = {p.relative_to(root).as_posix() for pattern in FROZEN_GLOBS for p in root.glob(pattern) if p.is_file()}
    if set(artifacts) != expected:
        raise ValueError(f"frozen inventory mismatch: missing={sorted(expected-set(artifacts))}, stale={sorted(set(artifacts)-expected)}")
    for name, recorded in artifacts.items():
        if not re.fullmatch(r"[0-9a-f]{64}", recorded) or digest(root / name) != recorded:
            raise ValueError(f"frozen hash mismatch: {name}")


def check_line_endings_policy(root: Path = ROOT) -> None:
    attrs = (root / ".gitattributes").read_text(encoding="utf-8")
    for pattern in ("*.md", "*.json", "*.yaml", "*.yml", "*.py"):
        if not re.search(rf"(?m)^{re.escape(pattern)} text eol=lf\s*$", attrs):
            raise ValueError(f"LF Git attribute missing: {pattern}")


def check_paths(paths: list[str], root: Path = ROOT) -> None:
    contract = (root / "docs/milestones/CURRENT.md").read_text(encoding="utf-8")
    status = re.search(r"(?m)^\*\*status:\*\* (\w+)\s*$", contract)
    if not status or status.group(1) not in {"ACTIVE", "FROZEN"}:
        raise ValueError("Current Milestone is not ACTIVE or verified FROZEN")
    if status.group(1) == "FROZEN":
        verify_frozen_completion(contract, root)
    allowed = section_items(contract, "Allowed paths")
    forbidden = section_items(contract, "Forbidden paths")
    if not allowed or not forbidden:
        raise ValueError("milestone path lists empty")
    for path in paths:
        normalized = path.replace("\\", "/").removeprefix("./")
        if normalized.startswith("/") or ".." in Path(normalized).parts:
            raise ValueError(f"unsafe path: {path}")
        matches = lambda pattern: fnmatch.fnmatchcase(normalized, pattern) or (pattern.endswith("/**") and normalized.startswith(pattern[:-3] + "/"))
        if any(matches(p) for p in forbidden) or not any(matches(p) for p in allowed):
            raise ValueError(f"outside milestone: {path}")


def verify_frozen_completion(contract: str, root: Path = ROOT) -> None:
    criteria = section_items_text(contract, "Acceptance criteria")
    if not contract.startswith("# Milestone M0 ") or not re.search(r"(?m)^- \[x\]", criteria) or re.search(r"(?m)^- \[ \]", criteria):
        raise ValueError("FROZEN milestone has unchecked acceptance criteria")
    report = root / "docs/milestone_reports/M0_FINAL.md"
    audit = root / "docs/audit/M0_AUDIT.yaml"
    if not report.is_file() or not audit.is_file():
        raise ValueError("FROZEN milestone lacks completion or audit evidence")
    report_text = report.read_text(encoding="utf-8")
    audit_text = audit.read_text(encoding="utf-8")
    golden_none = bool(re.search(r"(?m)^## Golden subset\s*$\nnone;", contract))
    report_pass = (
        re.search(r"(?m)^milestone_id: M0\s*$", report_text)
        and re.search(r"(?m)^status: PASS\s*$", report_text)
        and re.search(r"(?m)^tests:\s*$\n  passed: [1-9]\d*\s*$\n  failed: 0\s*$", report_text)
        and re.search(r"(?m)^ci_result: PASS\s*$", report_text)
        and re.search(r"(?m)^frozen_hash: PASS\s*$", report_text)
        and re.search(r"(?m)^audit_result: PASS\s*$", report_text)
        and re.search(r"(?m)^golden_regression: NOT_APPLICABLE\s*$", report_text)
        and golden_none
    )
    if not report_pass:
        raise ValueError("FROZEN completion report lacks passing gates")
    if not re.search(r"(?m)^milestone_id: M0\s*$", audit_text) or not re.search(r"(?m)^result: PASS\s*$", audit_text) or not re.search(r"(?m)^findings: \[\]\s*$", audit_text):
        raise ValueError("FROZEN audit evidence is not a clean PASS")


def section_items_text(text: str, heading: str) -> str:
    match = re.search(rf"(?m)^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not match:
        raise ValueError(f"missing section: {heading}")
    return match.group(1)


def check_registry(root: Path = ROOT) -> None:
    text = (root / "config/rule_registry.yaml").read_text(encoding="utf-8")
    ids = re.findall(r"(?m)^- id: ([A-Z]+-\d+)\s*$", text)
    if len(ids) != len(set(ids)) or set(ids) != REQUIRED_RULES:
        raise ValueError("rule registry IDs missing or duplicated")
    for block in re.split(r"(?m)(?=^- id: )", text)[1:]:
        if "status: ACTIVE" not in block or "level:" not in block:
            raise ValueError("rule registry entry incomplete")
        if "ci_gate: null" not in block and "ci_gate:" not in block:
            raise ValueError("rule gate missing")
    for rule, function in (("SCHEMA-001", "check_manifest"), ("MILESTONE-001", "check_paths"), ("TEST-001", "check_test_integrity")):
        block = next(b for b in re.split(r"(?m)(?=^- id: )", text)[1:] if b.startswith(f"- id: {rule}\n"))
        if f"code: tools/governance/check.py::{function}" not in block or "ci_gate: governance" not in block:
            raise ValueError(f"{rule} M0 enforcement mapping missing")
        refs = re.findall(r"tests/governance/[\w.]+::[\w.]+", block)
        if not refs or any(not (root / ref.split("::")[0]).is_file() for ref in refs):
            raise ValueError(f"{rule} test reference missing")
    workflow = (root / ".github/workflows/governance.yml").read_text(encoding="utf-8")
    if "python tools/governance/check.py" not in workflow or "python -m unittest discover -s tests/governance" not in workflow:
        raise ValueError("governance CI gate disconnected")


def git_lines(args: list[str], root: Path = ROOT) -> list[str]:
    return subprocess.check_output(["git", *args], cwd=root, text=True).splitlines()


def git_text(args: list[str], root: Path = ROOT) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True)


def test_inventory(source: str) -> dict[str, int]:
    tree = ast.parse(source)
    inventory = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            assertions = sum(
                isinstance(child, ast.Assert) or
                (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr.startswith("assert"))
                for child in ast.walk(node)
            )
            inventory[node.name] = assertions
    return inventory


def check_test_integrity(base: str | None, root: Path = ROOT) -> None:
    if base is None:
        changed = git_lines(["ls-files", "tests"], root)
        deleted = modified = []
    else:
        changes = git_lines(["diff", "--name-status", "-M", f"{base}...HEAD"], root)
        deleted = [x for x in changes if (x.startswith("D\t") and x.split("\t")[1].startswith("tests/")) or (x.startswith("R") and x.split("\t")[1].startswith("tests/"))]
        modified = [x.split("\t")[1] for x in changes if x.startswith("M\ttests/")]
        changed = [x.split("\t")[-1] for x in changes if x.startswith(("A\ttests/", "M\ttests/"))]
    if deleted:
        raise ValueError(f"tests deleted: {deleted}")
    for name in modified:
        previous = test_inventory(git_text(["show", f"{base}:{name}"], root))
        current = test_inventory((root / name).read_text(encoding="utf-8"))
        if any(test not in current or current[test] < count for test, count in previous.items()):
            raise ValueError(f"test inventory or assertions weakened: {name}")
    for name in changed:
        content = (root / name).read_text(encoding="utf-8")
        if (has_executable_skip(content) if name.endswith(".py") else SKIP_PATTERN.search(content)):
            raise ValueError(f"test skip introduced: {name}")


def check_manifest_change(base: str, root: Path = ROOT) -> None:
    changed = git_lines(["diff", "--name-only", f"{base}...HEAD", "--", "schemas/frozen_manifest.json"], root)
    if changed:
        prior = json.loads(git_text(["show", f"{base}:schemas/frozen_manifest.json"], root))
        current = json.loads((root / "schemas/frozen_manifest.json").read_text(encoding="utf-8"))
        affected = {name for name in set(prior["artifacts"]) | set(current["artifacts"]) if prior["artifacts"].get(name) != current["artifacts"].get(name)}
        if not affected:
            raise ValueError("manifest metadata change lacks artifact justification")
        cr_paths = git_lines(["ls-tree", "-r", "--name-only", base, "docs/change_requests"], root)
        for artifact in affected:
            approved = False
            for path in cr_paths:
                if not path.endswith(".md"):
                    continue
                if git_lines(["diff", "--name-only", f"{base}...HEAD", "--", path], root):
                    continue
                cr = git_text(["show", f"{base}:{path}"], root)
                if (
                    re.search(r"(?m)^\*\*status:\*\* APPROVED\s*$", cr)
                    and re.search(rf"(?m)^\*\*affected_artifact:\*\* {re.escape(artifact)}\s*$", cr)
                    and re.search(r"(?m)^approved_by: (?!null\s*$)\S.+$", cr)
                    and re.search(r"(?m)^approved_at: \d{4}-\d{2}-\d{2}(?:T\S+)?\s*$", cr)
                ):
                    approved = True
                    break
            if not approved:
                raise ValueError(f"manifest change lacks pre-existing unchanged APPROVED CR: {artifact}")


def check_initial_baseline(root: Path = ROOT) -> None:
    commits = git_lines(["rev-list", "--count", "HEAD"], root)
    if commits != ["1"]:
        raise ValueError("initial baseline only valid for the root commit")
    paths = git_lines(["ls-files"], root)
    if not paths:
        raise ValueError("initial baseline has no tracked files")
    ordinary = [p for p in paths if p not in BOOTSTRAP_PATHS]
    check_paths(ordinary, root)
    check_test_integrity(None, root)


def changed_paths(base: str) -> list[str]:
    output = subprocess.check_output(["git", "diff", "--name-only", f"{base}...HEAD"], cwd=ROOT, text=True)
    return [line for line in output.splitlines() if line]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", help="Git base revision for milestone path checks")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--initial-baseline", action="store_true", help="Root commit only: validate inventory without a prior diff")
    args = parser.parse_args()
    check_manifest()
    check_registry()
    if args.initial_baseline and (args.base or args.changed_file):
        raise SystemExit("initial baseline cannot combine with changed paths")
    if args.initial_baseline:
        check_initial_baseline()
        print("governance PASS (initial tracked baseline)")
        return
    paths = args.changed_file + (changed_paths(args.base) if args.base else [])
    if not paths and not args.initial_baseline:
        raise SystemExit("changed paths required; pass --base or --changed-file")
    if paths:
        check_paths(paths)
    if args.base:
        check_test_integrity(args.base)
        check_manifest_change(args.base)
    print(f"governance PASS ({len(paths)} changed paths)")


if __name__ == "__main__":
    main()
