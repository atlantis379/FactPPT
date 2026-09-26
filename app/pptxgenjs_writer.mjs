// Deterministic editable PPTX writer for a validated BeautificationPlan.
import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [planPath, outputPath, modulePath, workspaceDir] = process.argv.slice(2);
if (!planPath || !outputPath || !modulePath || !workspaceDir) {
  throw new Error("usage: node pptxgenjs_writer.mjs PLAN OUT PPTXGENJS_MODULE WORKSPACE");
}
const { default: PptxGenJS } = await import(pathToFileURL(path.resolve(modulePath)).href);
const plan = JSON.parse(await fs.readFile(planPath, "utf8"));
if (!Array.isArray(plan.pages) || !plan.tokens?.typography?.font_family || !plan.tokens?.colors?.background) {
  throw new Error("BeautificationPlan is missing pages, font, or background color");
}
const pptx = new PptxGenJS();
pptx.defineLayout({ name: "IR_1280_720", width: 1280 / 96, height: 720 / 96 });
pptx.layout = "IR_1280_720";
pptx.theme = { headFontFace: plan.tokens.typography.font_family,
               bodyFontFace: plan.tokens.typography.font_family, lang: "zh-CN" };

const inch = value => {
  if (!Number.isFinite(value)) throw new Error(`Invalid geometric value: ${value}`);
  return value / 96;
};
const point = value => {
  if (!Number.isFinite(value) || value <= 0) throw new Error(`Invalid font size: ${value}`);
  return value * 72 / 96;
};
const color = (value, fallback, allowOpacity = false) => {
  const raw = value ?? fallback;
  const match = String(raw ?? "").match(/^#([0-9a-fA-F]{6})(?:\/(\d{1,3}))?$/);
  if (!match) throw new Error(`Unsupported color value: ${String(raw)}`);
  if (match[2] !== undefined && Number(match[2]) > 100) {
    throw new Error(`Color opacity must be between 0 and 100: ${raw}`);
  }
  if (match[2] !== undefined && !allowOpacity) {
    throw new Error(`Opacity is unsupported in this color field: ${raw}`);
  }
  return match[1].toUpperCase();
};
const transparency = value => {
  if (value === "none") return 100;
  const raw = String(value ?? "");
  const match = raw.match(/^#[0-9a-fA-F]{6}(?:\/(\d{1,3}))?$/);
  if (!match) throw new Error(`Unsupported fill or line color: ${raw}`);
  if (match[1] === undefined) return 0;
  const opacity = Number(match[1]);
  if (opacity > 100) throw new Error(`Color opacity must be between 0 and 100: ${raw}`);
  return 100 - opacity;
};
const position = box => {
  if (!box || ![box.left, box.top, box.width, box.height].every(Number.isFinite)
      || box.width <= 0 || box.height <= 0) {
    throw new Error("Element has an invalid position box");
  }
  return { x: inch(box.left), y: inch(box.top), w: inch(box.width), h: inch(box.height) };
};
const geometry = (pptx, value) => {
  const types = { rect: pptx.ShapeType.rect, roundRect: pptx.ShapeType.roundRect,
                  ellipse: pptx.ShapeType.ellipse };
  if (!Object.hasOwn(types, value)) throw new Error(`Unsupported geometry: ${String(value)}`);
  return types[value];
};
const fillOptions = value => value === "none"
  ? { color: "FFFFFF", transparency: 100 }
  : { color: color(value, undefined, true), transparency: transparency(value) };
const lineOptions = (value, width = 1) => value === "none"
  ? { color: "FFFFFF", transparency: 100, width: 0 }
  : { color: color(value, undefined, true), transparency: transparency(value), width };
const textAlignment = value => {
  const allowed = new Set(["left", "center", "right", "justify", "distributed"]);
  if (!allowed.has(value)) throw new Error(`Unsupported text alignment: ${String(value)}`);
  return value;
};
const verticalAlignment = value => {
  const normalized = value === "middle" ? "mid" : value;
  if (!["top", "mid", "bottom"].includes(normalized)) {
    throw new Error(`Unsupported vertical alignment: ${String(value)}`);
  }
  return normalized;
};

function addText(slide, element) {
  const style = element.style || {};
  const fill = element.fill ?? "none";
  const line = element.line?.fill ?? "none";
  const options = {
    ...position(element.position), objectName: element.name, margin: 0,
    fontFace: plan.tokens.typography.font_family, fontSize: point(style.fontSize ?? 17),
    color: color(style.color, "#10243E"), bold: !!style.bold,
    align: textAlignment(style.alignment ?? "left"),
    valign: verticalAlignment(style.verticalAlignment ?? "top"),
    breakLine: false,
  };
  if (element.kind === "shape") {
    options.shape = geometry(pptx, element.geometry ?? "rect");
    options.fill = fillOptions(fill);
    options.line = lineOptions(line, element.line?.width ?? 1);
  }
  slide.addText(String(element.text ?? ""), options);
}

function addShape(slide, element) {
  slide.addShape(geometry(pptx, element.geometry ?? "rect"), {
    ...position(element.position), objectName: element.name,
    fill: fillOptions(element.fill ?? "none"),
    line: lineOptions(element.line?.fill ?? "none", element.line?.width ?? 1),
  });
}

for (const page of plan.pages) {
  if (!Array.isArray(page.elements) || !Array.isArray(page.connectors ?? [])) {
    throw new Error(`Page ${String(page.page_id)} has an invalid element or connector list`);
  }
  if (!Array.isArray(page.speaker_notes ?? [])) throw new Error("speaker_notes must be an array");
  const slide = pptx.addSlide();
  slide.background = { color: color(plan.tokens.colors.background) };
  for (const asset of page.editorial_assets || []) {
    slide.addImage({ path: path.join(workspaceDir, asset.path),
                     ...position(asset.placement), objectName: asset.asset_id,
                     altText: `asset-id:${asset.asset_id};sha256:${asset.sha256}` });
  }
  const boxes = new Map();
  for (const element of page.elements) {
    if (!element.name || !["text", "shape"].includes(element.kind)) {
      throw new Error(`Unsupported or unnamed element: ${String(element.name)}`);
    }
    boxes.set(element.name, element.position);
    if (element.kind === "text" || element.text !== undefined) addText(slide, element);
    else addShape(slide, element);
  }
  for (const connector of page.connectors || []) {
    const from = boxes.get(connector.from), to = boxes.get(connector.to);
    if (!from || !to) throw new Error(`Missing connector endpoint: ${connector.name}`);
    if (from.left >= to.left) throw new Error(`Writer only supports left-to-right connectors: ${connector.name}`);
    const x1 = from.left + from.width, y1 = from.top + from.height / 2;
    const x2 = to.left, y2 = to.top + to.height / 2;
    const direction = connector.direction ?? "FORWARD";
    if (!["FORWARD", "BIDIRECTIONAL", "NONE"].includes(direction)) {
      throw new Error(`Unsupported connector direction: ${String(direction)}`);
    }
    slide.addShape(pptx.ShapeType.line, {
      x: inch(x1), y: inch(y1), w: inch(x2 - x1), h: inch(y2 - y1),
      objectName: connector.name,
      line: { color: color(connector.color, "#50728B"), width: connector.width ?? 2,
              beginArrowType: direction === "BIDIRECTIONAL" ? "triangle" : "none",
              endArrowType: direction === "NONE" ? "none" : "triangle" },
    });
  }
  slide.addNotes((page.speaker_notes || []).join("\n"));
}
await pptx.writeFile({ fileName: outputPath });
