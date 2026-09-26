"""Preflight the pinned Python environment and the selected PPTX writer."""
from __future__ import annotations

import importlib.metadata
import json
import sys
from pathlib import Path

from app.packager import _pptxgenjs_runtime_paths, _runtime_paths
from app.stage_contract import digest_file


LOCK = Path(__file__).with_name("requirements.lock")
EXTERNAL_LOCK = Path(__file__).with_name("external_runtime.lock.json")
WORKSPACE = Path(__file__).resolve().parents[1]


def check_environment(*, require_builder: bool = True, require_finalizer: bool = False) -> dict:
    problems: list[str] = []
    packages: dict[str, dict[str, str | None]] = {}
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        name, expected = line.split("==", 1)
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual = None
        packages[name] = {"expected": expected, "actual": actual}
        if actual != expected:
            problems.append(f"{name}: expected {expected}, found {actual or 'missing'}")
    runtime = None
    if require_builder:
        try:
            node, module = _pptxgenjs_runtime_paths()
            writer_version = json.loads((WORKSPACE / "node_modules" / "pptxgenjs" / "package.json")
                                        .read_text(encoding="utf-8"))["version"]
            runtime = {"writer": "pptxgenjs", "node": str(node),
                       "pptxgenjs_module": str(module), "pptxgenjs_version": writer_version}
        except RuntimeError as error:
            problems.append(str(error))
    if require_finalizer:
        try:
            node, modules, bin_dir, python, skill_dir = _runtime_paths()
            external = json.loads(EXTERNAL_LOCK.read_text(encoding="utf-8"))
            finalizer_file = skill_dir / external["presentation_finalizer"]["path"]
            artifact_file = modules / "@oai" / "artifact-tool" / "package.json"
            if json.loads(artifact_file.read_text(encoding="utf-8")).get("version") != external["artifact_tool"]["version"]:
                problems.append("Artifact Tool version differs from external_runtime.lock.json")
            if digest_file(finalizer_file) != external["presentation_finalizer"]["sha256"]:
                problems.append("Presentation finalizer bytes differ from external_runtime.lock.json")
            runtime = runtime or {}
            runtime.update({"finalizer_node": str(node), "artifact_tool_node_modules": str(modules),
                            "bin_dir": str(bin_dir), "python": str(python),
                            "presentations_skill": str(skill_dir),
                            "artifact_tool_version": external["artifact_tool"]["version"],
                            "presentation_finalizer_sha256": external["presentation_finalizer"]["sha256"]})
        except (RuntimeError, OSError, KeyError, ValueError) as error:
            problems.append(str(error))
    return {"status": "PASS" if not problems else "FAIL", "python": sys.version.split()[0],
            "lock": str(LOCK), "packages": packages, "runtime": runtime,
            "problems": problems}


def main() -> int:
    args = set(sys.argv[1:])
    unknown = args - {"--python-only", "--finalizer"}
    if unknown or ("--python-only" in args and "--finalizer" in args):
        print("usage: python -m app.reproducibility [--python-only | --finalizer]")
        return 2
    result = check_environment(require_builder="--python-only" not in args,
                              require_finalizer="--finalizer" in args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
