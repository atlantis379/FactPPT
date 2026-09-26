"""Auditable PPTX packaging for approved Semantic Decks.

PptxGenJS is the reproducible default writer. Artifact Tool remains an explicit
legacy comparison/finalization route and is never selected as a silent fallback.
"""
from __future__ import annotations

import json
import hashlib
import html
import os
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path
from typing import Any

from app.editorial_assets import load_editorial_asset_manifest
from app.native_beautifier import (compile_beautification_plan, validate_beautification_plan,
                                   _source_lines)
from app import render_readback


WORKSPACE = Path(__file__).resolve().parents[1]


def _configured_node_for_tests() -> Path:
    """Expose the public Node writer executable to legacy integration tests."""
    node_path = os.environ.get("EASYPPT_NODE") or shutil.which("node")
    return Path(node_path) if node_path else WORKSPACE / "__node_unconfigured__"


DEFAULT_NODE = _configured_node_for_tests()
DEFAULT_PPTXGENJS_MODULE = WORKSPACE / "node_modules" / "pptxgenjs" / "dist" / "pptxgen.es.js"


def _pptxgenjs_runtime_paths() -> tuple[Path, Path]:
    """Resolve and verify the repo-locked public writer runtime."""
    node_path = os.environ.get("EASYPPT_NODE") or shutil.which("node")
    if not node_path or not Path(node_path).is_file():
        raise RuntimeError("Node.js is unavailable; install the version in .nvmrc or set EASYPPT_NODE")
    manifest_path = WORKSPACE / "node_modules" / "pptxgenjs" / "package.json"
    module_path = WORKSPACE / "node_modules" / "pptxgenjs" / "dist" / "pptxgen.es.js"
    package_json = WORKSPACE / "package.json"
    lock_json = WORKSPACE / "package-lock.json"
    if not manifest_path.is_file() or not module_path.is_file():
        raise RuntimeError("PptxGenJS is not installed; run `npm ci` from the repository root")
    if not package_json.is_file() or not lock_json.is_file():
        raise RuntimeError("The locked Node writer manifest is missing")
    try:
        expected = json.loads(package_json.read_text(encoding="utf-8"))["dependencies"]["pptxgenjs"]
        package_version = json.loads(manifest_path.read_text(encoding="utf-8")).get("version")
        lock_version = json.loads(lock_json.read_text(encoding="utf-8"))[
            "packages"]["node_modules/pptxgenjs"]["version"]
        expected_node = (WORKSPACE / ".nvmrc").read_text(encoding="utf-8").strip().lstrip("v")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"The locked Node writer configuration is invalid: {error}") from error
    if expected != package_version or expected != lock_version:
        raise RuntimeError("Installed PptxGenJS version differs from package.json/package-lock.json")
    result = subprocess.run([node_path, "--version"], check=True, capture_output=True, text=True)
    actual_node = result.stdout.strip().lstrip("v")
    if actual_node != expected_node:
        raise RuntimeError(f"Node.js version mismatch: expected {expected_node}, found {actual_node}")
    return Path(node_path), module_path


BUILDER_MJS = r'''import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const [inputPath, outputPath, previewDir, workspaceDir] = process.argv.slice(2);
const plan = JSON.parse(await fs.readFile(inputPath, "utf8"));
const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const family = plan.tokens?.typography?.font_family || "Microsoft YaHei";
const renderedSlides = [];

function addText(slide, element, autoFit) {
  const shape = slide.shapes.add({
    geometry: "textbox", name: element.name, position: element.position, fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = String(element.text || "");
  shape.text.style = { typeface: family, autoFit, ...element.style };
  return shape;
}

function addShape(slide, element, autoFit) {
  const shape = slide.shapes.add({
    geometry: element.geometry || "rect", name: element.name, position: element.position,
    fill: element.fill || "none",
    line: { style: "solid", fill: element.line?.fill || "none", width: element.line?.width || 0 },
  });
  if (element.text) {
    shape.text = String(element.text);
    shape.text.style = { typeface: family, autoFit, ...element.style };
  }
  return shape;
}

for (const page of plan.pages || []) {
  const slide = presentation.slides.add();
  renderedSlides.push(slide);
  slide.background.fill = plan.tokens.colors.background;
  for (const asset of page.editorial_assets || []) {
    const imageBytes = await fs.readFile(path.join(workspaceDir, asset.path));
    const image = slide.images.add({
      blob: new Uint8Array(imageBytes),
      contentType: asset.content_type,
      alt: `asset-id:${asset.asset_id};sha256:${asset.sha256}`,
      prompt: asset.prompt_provenance?.prompt,
      fit: asset.placement.fit,
      position: {
        left: asset.placement.left, top: asset.placement.top,
        width: asset.placement.width, height: asset.placement.height,
      },
    });
    image.name = asset.asset_id;
  }
  const objects = new Map();
  const autoFit = page.layout_intent ? "none" : "shrinkText";
  for (const element of page.elements || []) {
    const object = element.kind === "text" ? addText(slide, element, autoFit) : addShape(slide, element, autoFit);
    objects.set(element.name, object);
  }
  for (const connectorSpec of page.connectors || []) {
    const source = objects.get(connectorSpec.from);
    const target = objects.get(connectorSpec.to);
    if (!source || !target) throw new Error(`Connector endpoint missing: ${connectorSpec.name}`);
    const fromLeft = source.position.left <= target.position.left;
    const direction = connectorSpec.direction || "FORWARD";
    const lineEnds = direction === "BIDIRECTIONAL"
      ? { head: { type: "arrow", width: "sm", length: "sm" }, tail: { type: "arrow", width: "sm", length: "sm" } }
      : direction === "NONE" ? {}
      : { tail: { type: "arrow", width: "sm", length: "sm" } };
    const connector = slide.shapes.connect(source, target, {
      kind: "straight", fromSide: fromLeft ? "right" : "left", toSide: fromLeft ? "left" : "right",
      line: { style: "solid", fill: connectorSpec.color || plan.tokens.colors.relationship, width: connectorSpec.width || 2 },
      ...lineEnds,
    });
    connector.name = connectorSpec.name;
  }
  slide.speakerNotes.textFrame.setText(page.speaker_notes || []);
  slide.speakerNotes.setVisible(true);
}

const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(outputPath);
if (previewDir) {
  await fs.mkdir(previewDir, { recursive: true });
  for (const [index, slide] of renderedSlides.entries()) {
    const preview = await presentation.export({ slide, format: "png", scale: 1 });
    await fs.writeFile(`${previewDir}/slide-${String(index + 1).padStart(2, "0")}.png`, new Uint8Array(await preview.arrayBuffer()));
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(`${previewDir}/slide-${String(index + 1).padStart(2, "0")}.layout.json`, await layout.text());
  }
}
'''


FINALIZER_MJS = r'''import path from "node:path";
import { pathToFileURL } from "node:url";

const [candidatePath, finalPath, workspaceDir, receiptPath, slideCount, pythonExecutable, skillDir] = process.argv.slice(2);
const { finalizePresentation } = await import(pathToFileURL(
  path.join(skillDir, "container_tools/artifact_tool_utils.mjs"),
).href);
const result = await finalizePresentation({
  explicitTotalSlideCount: Number(slideCount),
  requiredNativeTableOwnerSlides: [],
  requiredNativeChartOwnerSlides: [],
  workspaceDir,
  candidatePath,
  finalPath,
  pythonExecutable,
  integrityValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_layout_geometry.py"),
  layoutArgs: [
    "--expected-slide-size-emu", "12192000,6858000",
    "--validate-heading-fit",
  ],
  fontPolicy: { basis: "design", families: ["Microsoft YaHei"] },
  verifyArtifactToolImport: true,
  receiptPath,
});
console.log(JSON.stringify(result));
'''


def _runtime_paths() -> tuple[Path, Path, Path, Path, Path]:
    node_path = os.environ.get("EASYPPT_ARTIFACT_NODE") or shutil.which("node")
    modules_path = os.environ.get("EASYPPT_ARTIFACT_NODE_MODULES")
    skill_path = os.environ.get("EASYPPT_PRESENTATIONS_SKILL_DIR")
    if not node_path or not modules_path or not skill_path:
        raise RuntimeError("Artifact Tool runtime is unconfigured: set "
                           "EASYPPT_ARTIFACT_NODE_MODULES and EASYPPT_PRESENTATIONS_SKILL_DIR; "
                           "install Node.js or set EASYPPT_ARTIFACT_NODE")
    node = Path(node_path)
    modules = Path(modules_path)
    skill_dir = Path(skill_path)
    bin_dir = Path(os.environ.get("EASYPPT_ARTIFACT_BIN_DIR") or node.parent)
    python = Path(os.environ.get("EASYPPT_ARTIFACT_PYTHON") or sys.executable)
    missing = [str(path) for path in (node, modules, bin_dir, python, skill_dir) if not path.exists()]
    if missing:
        raise RuntimeError("Artifact Tool runtime is unavailable: " + ", ".join(missing))
    external_lock = json.loads((Path(__file__).with_name("external_runtime.lock.json"))
                               .read_text(encoding="utf-8"))
    package_file = modules / "@oai" / "artifact-tool" / "package.json"
    finalizer_file = skill_dir / external_lock["presentation_finalizer"]["path"]
    if not package_file.is_file() or not finalizer_file.is_file():
        raise RuntimeError("Artifact Tool package or presentation finalizer is missing")
    if json.loads(package_file.read_text(encoding="utf-8")).get("version") != external_lock["artifact_tool"]["version"]:
        raise RuntimeError("Artifact Tool version differs from external_runtime.lock.json")
    finalizer_hash = hashlib.sha256(finalizer_file.read_bytes()).hexdigest()
    if finalizer_hash != external_lock["presentation_finalizer"]["sha256"]:
        raise RuntimeError("Presentation finalizer differs from external_runtime.lock.json")
    return node, modules, bin_dir, python, skill_dir


def _console_text(*streams: bytes | str | None) -> str:
    """Decode a localised Windows console tool's output without crashing.

    ``mklink`` writes in the OEM code page (GBK on a Chinese Windows). Decoding its
    bytes as UTF-8 raises UnicodeDecodeError and aborts the build before the real
    failure can be reported.
    """
    for stream in streams:
        if not stream:
            continue
        if isinstance(stream, bytes):
            return stream.decode("utf-8", "replace").strip()
        return stream.strip()
    return ""


def _clear_link_path(link: Path) -> None:
    """Free the link path so a fresh link attempt has somewhere to go.

    ``Path.rmdir`` is not sufficient on Windows: it refuses a directory junction whose
    target is not empty, and a hardened sandbox can leave a plain empty directory behind
    in place of a failed symlink. ``rmdir`` through cmd clears either an empty directory
    or the reparse point itself, and never recurses into a populated tree.
    """
    if link.is_symlink():
        link.unlink()
        return
    if not link.exists():
        return
    result = subprocess.run(["cmd", "/d", "/c", "rmdir", str(link)], capture_output=True)
    if link.exists():
        raise RuntimeError(f"Refusing to replace {link} while linking the Artifact Tool runtime: "
                           + (_console_text(result.stdout, result.stderr)
                              or f"rmdir exited {result.returncode}"))


def _ensure_node_modules_link(build_dir: Path, modules: Path) -> None:
    """Expose the Artifact Tool runtime to the generated builder script.

    Node resolves ``@oai/artifact-tool`` from ``build_dir/node_modules``, so the
    throwaway build directory needs a link to the qualified runtime modules. Success is
    judged by RESOLVING THE PACKAGE, never by the link existing: a sandboxed or
    unprivileged ``os.symlink`` can degrade into a plain empty directory without
    raising, and the resulting failure then surfaces far away as an
    ``ERR_MODULE_NOT_FOUND`` inside Node.
    """
    probe = Path("@oai") / "artifact-tool"
    link = build_dir / "node_modules"
    if (link / probe).exists():
        return
    attempts: list[str] = []
    _clear_link_path(link)
    try:
        os.symlink(modules, link, target_is_directory=True)
        attempts.append("symlink")
    except OSError as error:
        attempts.append(f"symlink: {error}")
    if not (link / probe).exists():
        # Windows commonly disallows symbolic links for standard accounts; directory
        # junctions provide the same local module resolution without needing
        # developer-mode privileges.
        _clear_link_path(link)
        result = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(link), str(modules)],
                                capture_output=True)
        attempts.append("mklink /J: " + (_console_text(result.stdout, result.stderr)
                                         or f"exit {result.returncode}"))
    if not (link / probe).exists():
        raise RuntimeError("Unable to link the Artifact Tool runtime into the presentation build "
                           "directory; @oai/artifact-tool would not resolve. " + " | ".join(attempts))


def _build_with_artifact_tool(plan: dict[str, Any], target: Path, *,
                              preview_dir: Path | None, mark_operation: bool,
                              finalize: bool, validation_receipt: Path | None) -> None:
    """Legacy comparison writer; never used unless explicitly selected."""
    node, modules, bin_dir, python, skill_dir = _runtime_paths()
    temp_root = Path(os.environ.get("EASYPPT_BUILD_TMP", Path(__file__).resolve().parent / ".codex_build" / "tmp")).resolve()
    temp_root.mkdir(parents=True, exist_ok=True)
    build_dir = temp_root / f"presentation-build-{uuid.uuid4().hex}"
    build_dir.mkdir()
    try:
        input_path = build_dir / "beautification-plan.json"
        builder_path = build_dir / "build-native-editable-deck.mjs"
        finalizer_path = build_dir / "finalize-native-editable-deck.mjs"
        candidate_path = build_dir / "candidate.pptx"
        receipt_path = validation_receipt or (build_dir / "validation.json")
        input_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        builder_path.write_text(BUILDER_MJS, encoding="utf-8")
        finalizer_path.write_text(FINALIZER_MJS, encoding="utf-8")
        _ensure_node_modules_link(build_dir, modules)
        runtime_env = os.environ | {"RUNTIME_NODE": str(node), "RUNTIME_NODE_MODULES": str(modules), "RUNTIME_BIN_DIR": str(bin_dir)}
        if mark_operation:
            marker = skill_dir / "container_tools" / "mark_artifact_operation_started.mjs"
            subprocess.run([str(node), str(marker), "--operation-kind", "create", "--expected-output-count", "1", "--output-format", "pptx"], cwd=skill_dir, env=runtime_env, check=True, capture_output=True, text=True)
        rendered_path = candidate_path if finalize else target
        command = [str(node), str(builder_path), str(input_path), str(rendered_path), str(preview_dir or ""), str(WORKSPACE)]
        subprocess.run(command, cwd=build_dir, env=runtime_env, check=True, capture_output=True, text=True)
        if finalize:
            subprocess.run([
                str(node), str(finalizer_path), str(candidate_path), str(target), str(WORKSPACE),
                str(receipt_path), str(len(plan["pages"])), str(python), str(skill_dir),
            ], cwd=build_dir, env=runtime_env, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "Artifact Tool failed to generate PPTX.").strip()
        raise RuntimeError(detail) from error
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)


def _render_pptx_previews(target: Path, preview_dir: Path) -> None:
    """Render optional previews with desktop PowerPoint, never with the writer."""
    try:
        from app.validation.render_with_powerpoint import render
    except ModuleNotFoundError as error:
        raise RuntimeError("PowerPoint previews require pywin32 and desktop PowerPoint") from error
    render(target, preview_dir)


def _build_with_pptxgenjs(plan: dict[str, Any], target: Path, *,
                          preview_dir: Path | None, mark_operation: bool,
                          finalize: bool, validation_receipt: Path | None) -> None:
    """Write through the repository-locked public PPTX generator."""
    node, module = _pptxgenjs_runtime_paths()
    temp_root = Path(os.environ.get("EASYPPT_BUILD_TMP", Path(__file__).resolve().parent / ".codex_build" / "tmp")).resolve()
    temp_root.mkdir(parents=True, exist_ok=True)
    build_dir = temp_root / f"presentation-build-{uuid.uuid4().hex}"
    build_dir.mkdir()
    try:
        input_path = build_dir / "beautification-plan.json"
        finalizer_path = build_dir / "finalize-native-editable-deck.mjs"
        candidate_path = build_dir / "candidate.pptx"
        receipt_path = validation_receipt or (build_dir / "validation.json")
        input_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        output_path = candidate_path if finalize else target
        writer = Path(__file__).with_name("pptxgenjs_writer.mjs")
        subprocess.run([str(node), str(writer), str(input_path), str(output_path),
                        str(module), str(WORKSPACE)], cwd=WORKSPACE,
                       check=True, capture_output=True, text=True)
        if finalize:
            final_node, modules, bin_dir, python, skill_dir = _runtime_paths()
            finalizer_path.write_text(FINALIZER_MJS, encoding="utf-8")
            runtime_env = os.environ | {"RUNTIME_NODE": str(final_node),
                                        "RUNTIME_NODE_MODULES": str(modules),
                                        "RUNTIME_BIN_DIR": str(bin_dir)}
            if mark_operation:
                marker = skill_dir / "container_tools" / "mark_artifact_operation_started.mjs"
                subprocess.run([str(final_node), str(marker), "--operation-kind", "create",
                                "--expected-output-count", "1", "--output-format", "pptx"],
                               cwd=skill_dir, env=runtime_env, check=True,
                               capture_output=True, text=True)
            subprocess.run([str(final_node), str(finalizer_path), str(candidate_path),
                            str(target), str(WORKSPACE), str(receipt_path),
                            str(len(plan["pages"])), str(python), str(skill_dir)],
                           cwd=build_dir, env=runtime_env, check=True,
                           capture_output=True, text=True)
        if preview_dir is not None:
            _render_pptx_previews(target, preview_dir)
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "PptxGenJS failed to generate PPTX.").strip()
        raise RuntimeError(detail) from error
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)


def build_pptx(
    deck: dict[str, Any],
    target: Path,
    *,
    plan_target: Path | None = None,
    preview_dir: Path | None = None,
    mark_operation: bool = True,
    finalize: bool = False,
    validation_receipt: Path | None = None,
    editorial_asset_manifest: Path | dict[str, Any] | list[Path | dict[str, Any]] | None = None,
    layout_ir: dict[str, Any] | None = None,
    writer: str = "pptxgenjs",
) -> Path:
    """Build and verify an editable PPTX from an approved Semantic Deck.

    PptxGenJS is the reproducible default. ``writer="artifact_tool"`` is kept
    only for explicit local comparison against the legacy private runtime.
    Previews are rendered separately by PowerPoint when requested.
    """
    manifest_items = editorial_asset_manifest if isinstance(editorial_asset_manifest, list) else ([editorial_asset_manifest] if editorial_asset_manifest is not None else [])
    editorial_assets = [load_editorial_asset_manifest(item, workspace=WORKSPACE) for item in manifest_items]
    plan = compile_beautification_plan(deck, editorial_assets=editorial_assets, layout_ir=layout_ir)
    plan_validation = validate_beautification_plan(deck, plan)
    if plan_validation["status"] != "PASS":
        raise ValueError(f"BeautificationPlan failed validation: {plan_validation['issues']}")
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if plan_target is not None:
        plan_target = Path(plan_target).resolve()
        plan_target.parent.mkdir(parents=True, exist_ok=True)
        plan_target.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    if preview_dir is not None:
        preview_dir = Path(preview_dir).resolve()
        preview_dir.mkdir(parents=True, exist_ok=True)
    if validation_receipt is not None:
        validation_receipt = Path(validation_receipt).resolve()
        validation_receipt.parent.mkdir(parents=True, exist_ok=True)
    if writer == "pptxgenjs":
        _build_with_pptxgenjs(plan, target, preview_dir=preview_dir,
                              mark_operation=mark_operation, finalize=finalize,
                              validation_receipt=validation_receipt)
    elif writer == "artifact_tool":
        _build_with_artifact_tool(plan, target, preview_dir=preview_dir,
                                  mark_operation=mark_operation, finalize=finalize,
                                  validation_receipt=validation_receipt)
    else:
        raise ValueError("writer must be 'pptxgenjs' or 'artifact_tool'")
    return target


def _slide_xml_files(archive: zipfile.ZipFile) -> list[str]:
    pattern = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
    return sorted((name for name in archive.namelist() if pattern.match(name)), key=lambda name: int(pattern.match(name).group(1)))


def _visible_text(xml: str) -> str:
    """Text as a reader sees it, with XML entities decoded.

    `<`, `>` and `&` are escaped in OOXML (`&lt;14 d`), so a raw extraction compares an
    approved Claim containing "<14 d" against "&lt;14 d" and reports the slide as altered
    when it is in fact correct. Decoding makes the check read the rendered text rather than
    the markup.
    """
    return "\n".join(html.unescape(match)
                     for match in re.findall(r"<a:t>(.*?)</a:t>", xml, flags=re.DOTALL))


def verify_pptx(
    deck: dict[str, Any],
    target: Path,
    *,
    editorial_asset_manifest: Path | dict[str, Any] | list[Path | dict[str, Any]] | None = None,
    visual_contracts: list[dict[str, Any]] | None = None,
    layout_ir: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify native objects against the Semantic Deck and beautification contract.

    Beyond the declaration-level checks this runs a generator-independent readback
    of the rendered file (app.render_readback) -- the only layer able to see
    rendering-level defects such as a layout that breaks the reading order.
    """
    issues: list[dict[str, Any]] = []
    try:
        manifest_items = editorial_asset_manifest if isinstance(editorial_asset_manifest, list) else ([editorial_asset_manifest] if editorial_asset_manifest is not None else [])
        editorial_assets = [load_editorial_asset_manifest(item, workspace=WORKSPACE) for item in manifest_items]
        plan = compile_beautification_plan(deck, editorial_assets=editorial_assets, layout_ir=layout_ir)
    except ValueError as error:
        return {"status": "FAIL", "issues": [{"type": "BEAUTIFICATION_PLAN", "message": str(error)}], "slides_checked": 0}
    with zipfile.ZipFile(target) as archive:
        slides = _slide_xml_files(archive)
        media_hashes = {
            hashlib.sha256(archive.read(name)).hexdigest(): name
            for name in archive.namelist() if name.startswith("ppt/media/") and not name.endswith("/")
        }
        if len(slides) != len(deck["pages"]):
            issues.append({"type": "PAGE_COUNT", "message": "Rendered PPTX slide count differs from Semantic Deck."})
        for ordinal, page in enumerate(deck["pages"]):
            if len(page.get("claims", [])) > 4:
                issues.append({"type": "CLAIM_CAPACITY", "page_id": page["page_id"], "message": "Semantic page exceeds the native beautifier capacity of four Claims."})
            if ordinal >= len(slides):
                break
            xml = archive.read(slides[ordinal]).decode("utf-8")
            visible_text = _visible_text(xml)
            expected_assets = plan["pages"][ordinal].get("editorial_assets", [])
            picture_count = xml.count("<p:pic>")
            if picture_count != len(expected_assets):
                issues.append({"type": "EDITORIAL_ASSET_COUNT", "page_id": page["page_id"], "message": "Rendered picture count differs from the validated non-semantic asset plan."})
            for asset in expected_assets:
                if asset["asset_id"] not in xml:
                    issues.append({"type": "EDITORIAL_ASSET_IDENTITY", "page_id": page["page_id"], "asset_id": asset["asset_id"], "message": "Rendered underlay does not retain its asset identity."})
                if asset["sha256"] not in media_hashes:
                    issues.append({"type": "EDITORIAL_ASSET_HASH", "page_id": page["page_id"], "asset_id": asset["asset_id"], "message": "Embedded underlay bytes do not match the approved SHA-256."})
            for expected, kind in ((page["title"], "TITLE"), (page["primary_message"], "PRIMARY_MESSAGE")):
                if expected not in visible_text:
                    issues.append({"type": kind, "page_id": page["page_id"], "message": f"Required {kind.lower()} is missing or altered."})
            expected_footer = "Source traceability: " + " · ".join(_source_lines(page.get("claims", [])))
            if expected_footer not in visible_text:
                issues.append({"type": "SOURCE_TRACEABILITY", "page_id": page["page_id"], "message": "Page source traceability footer is absent or altered."})
            notes_name = f"ppt/notesSlides/notesSlide{ordinal + 1}.xml"
            notes_xml = archive.read(notes_name).decode("utf-8") if notes_name in archive.namelist() else ""
            notes_text = _visible_text(notes_xml)
            if "[Sources]" not in notes_text or any(source not in notes_text for source in _source_lines(page.get("claims", []))):
                issues.append({"type": "SPEAKER_NOTES", "page_id": page["page_id"], "message": "Page speaker notes do not retain its source block."})
            expected_claims = {claim["id"] for claim in page.get("claims", [])}
            rendered_claims = set(re.findall(r'claim:([^"<]+)', xml))
            if expected_claims != rendered_claims:
                issues.append({"type": "CLAIM_FIDELITY", "page_id": page["page_id"], "message": "Rendered Claim object IDs do not exactly match the Semantic Page Graph."})
            for claim in page.get("claims", []):
                if claim.get("normalized_claim", "") not in visible_text:
                    issues.append({"type": "CLAIM_TEXT", "page_id": page["page_id"], "claim_id": claim["id"], "message": "Approved Claim text is missing or altered."})
                for condition in claim.get("conditions", []):
                    if str(condition).strip() and str(condition).strip() not in visible_text:
                        issues.append({"type": "CONDITION_OMITTED", "page_id": page["page_id"],
                                       "claim_id": claim["id"], "condition": condition,
                                       "message": "Approved condition is missing from the delivered slide."})
            expected_relationships = {relationship["id"] for relationship in page.get("relationships", [])}
            rendered_relationships = set(re.findall(r'clinical_relationship:([^"<]+)', xml))
            if expected_relationships != rendered_relationships:
                issues.append({"type": "RELATIONSHIP_FIDELITY", "page_id": page["page_id"], "message": "Rendered connectors do not exactly match explicit Semantic Relationship IDs."})
            expected_archetype = plan["pages"][ordinal]["selected_archetype"]
            if f"Layout: {expected_archetype}" not in notes_text:
                issues.append({"type": "LAYOUT_PROVENANCE", "page_id": page["page_id"], "message": "Speaker notes do not identify the selected beautification archetype."})
            expected_fusion = plan["pages"][ordinal]["fusion"]["variant"]
            if expected_assets and f"Fusion: {expected_fusion}" not in notes_text:
                issues.append({"type": "FUSION_PROVENANCE", "page_id": page["page_id"], "message": "Speaker notes do not identify the underlay/native-layer fusion variant."})
    # Declaration-level divergence already means FAIL. The readback adds
    # rendering-level findings: BLOCK ones also fail delivery, soft ones are
    # reported for routing without turning a cosmetic drift into a blocker.
    declaration_failed = bool(issues)
    readback = render_readback.verify_render(
        target, render_readback.contract_from_plan(plan, visual_contracts=visual_contracts))
    for issue in readback["issues"]:
        issues.append({
            "type": "RENDER_" + issue["code"],
            "severity": issue["severity"],
            "message": f"Readback of the rendered file: {issue['code']}",
            "detail": issue["detail"],
        })
    readback_blocked = any(issue.get("severity") == "BLOCK" for issue in readback["issues"])
    return {
        "status": "FAIL" if (declaration_failed or readback_blocked) else "PASS",
        "issues": issues,
        "omission_report": [issue for issue in issues if issue["type"] in {
            "PAGE_COUNT", "TITLE", "PRIMARY_MESSAGE", "SOURCE_TRACEABILITY",
            "CLAIM_FIDELITY", "CLAIM_TEXT", "CONDITION_OMITTED",
            "RELATIONSHIP_FIDELITY", "SPEAKER_NOTES"} or
            issue["type"].startswith("RENDER_") and issue["type"] in {
                "RENDER_SLIDE_COUNT_MISMATCH", "RENDER_MANDATORY_OBJECT_MISSING",
                "RENDER_EXPECTED_OBJECT_MISSING", "RENDER_EXACT_TEXT_MISSING",
                "RENDER_EXACT_TEXT_MUTATED", "RENDER_TEXT_TRUNCATED",
                "RENDER_EMPTY_TEXT_OBJECT", "RENDER_REQUIRED_TEXT_MISSING",
                "RENDER_UNDECLARED_CHART"}],
        "slides_checked": len(deck["pages"]),
        "render_readback": readback,
        "native_editable": not any(issue["type"] in {"CLAIM_FIDELITY", "CLAIM_TEXT", "RELATIONSHIP_FIDELITY"} for issue in issues),
        "editorial_asset_ids": [asset["asset_id"] for asset in editorial_assets],
        "editorial_asset_sha256s": [asset["sha256"] for asset in editorial_assets],
        "selected_archetypes": [page["selected_archetype"] for page in plan["pages"]],
    }
