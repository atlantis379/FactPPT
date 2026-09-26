// Experimental renderer for an existing BeautificationPlan. Not a production route.
import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [planPath, outputPath, modulePath, workspaceDir] = process.argv.slice(2);
if (!planPath || !outputPath || !modulePath || !workspaceDir) {
  throw new Error("usage: node pptxgenjs_compare.mjs PLAN OUT PPTXGENJS_MODULE WORKSPACE");
}
const { default: PptxGenJS } = await import(pathToFileURL(path.resolve(modulePath)).href);
const plan = JSON.parse(await fs.readFile(planPath, "utf8"));
const pptx = new PptxGenJS();
pptx.defineLayout({ name: "IR_1280_720", width: 1280 / 96, height: 720 / 96 });
pptx.layout = "IR_1280_720";
pptx.theme = { headFontFace: plan.tokens.typography.font_family,
               bodyFontFace: plan.tokens.typography.font_family, lang: "zh-CN" };

const inch = value => value / 96;
// The IR canvas and Artifact Tool fontSize are CSS-pixel based; PptxGenJS uses points.
const point = value => value * 72 / 96;
const color = value => String(value || "#FFFFFF").match(/^#([0-9a-fA-F]{6})/)?.[1] || "FFFFFF";
const transparency = value => {
  const match = String(value || "").match(/\/(\d{1,3})$/);
  return match ? Math.max(0, Math.min(100, 100 - Number(match[1]))) : 0;
};
const position = box => ({ x: inch(box.left), y: inch(box.top),
                            w: inch(box.width), h: inch(box.height) });

function addText(slide, element) {
  const style = element.style || {};
  const fill = element.fill || "none";
  const line = element.line?.fill || "none";
  slide.addText(String(element.text || ""), {
    ...position(element.position), objectName: element.name, margin: 0,
    fontFace: plan.tokens.typography.font_family, fontSize: point(style.fontSize || 17),
    color: color(style.color || "#10243E"), bold: !!style.bold,
    align: style.alignment || "left",
    valign: style.verticalAlignment === "middle" ? "mid" : (style.verticalAlignment || "top"),
    breakLine: false,
    ...(element.kind === "shape" ? {
      fill: fill === "none" ? { color: "FFFFFF", transparency: 100 }
                            : { color: color(fill), transparency: transparency(fill) },
      line: line === "none" ? { color: "FFFFFF", transparency: 100, width: 0 }
                             : { color: color(line), transparency: transparency(line), width: element.line?.width || 1 },
    } : {}),
  });
}

function addShape(slide, element) {
  const fill = element.fill || "none";
  const line = element.line?.fill || "none";
  slide.addShape(element.geometry === "roundRect" ? pptx.ShapeType.roundRect : pptx.ShapeType.rect, {
    ...position(element.position), objectName: element.name,
    fill: fill === "none" ? { color: "FFFFFF", transparency: 100 }
                          : { color: color(fill), transparency: transparency(fill) },
    line: line === "none" ? { color: "FFFFFF", transparency: 100, width: 0 }
                           : { color: color(line), transparency: transparency(line), width: element.line?.width || 1 },
  });
}

for (const page of plan.pages) {
  const slide = pptx.addSlide();
  slide.background = { color: color(plan.tokens.colors.background) };
  for (const asset of page.editorial_assets || []) {
    slide.addImage({ path: path.join(workspaceDir, asset.path),
                     ...position(asset.placement), objectName: asset.asset_id,
                     altText: `asset-id:${asset.asset_id};sha256:${asset.sha256}` });
  }
  const boxes = new Map();
  for (const element of page.elements) {
    boxes.set(element.name, element.position);
    if (element.kind === "text" || element.text) addText(slide, element);
    else addShape(slide, element);
  }
  for (const connector of page.connectors || []) {
    const from = boxes.get(connector.from), to = boxes.get(connector.to);
    if (!from || !to) throw new Error(`Missing connector endpoint: ${connector.name}`);
    if (from.left >= to.left) throw new Error(`Comparison renderer only supports left-to-right connectors: ${connector.name}`);
    const x1 = from.left + from.width, y1 = from.top + from.height / 2;
    const x2 = to.left, y2 = to.top + to.height / 2;
    slide.addShape(pptx.ShapeType.line, {
      x: inch(x1), y: inch(y1), w: inch(x2 - x1), h: inch(y2 - y1),
      objectName: connector.name,
      line: { color: color(connector.color), width: connector.width || 2,
              beginArrowType: connector.direction === "BIDIRECTIONAL" ? "triangle" : "none",
              endArrowType: connector.direction === "NONE" ? "none" : "triangle" },
    });
  }
  slide.addNotes((page.speaker_notes || []).join("\n"));
}
await pptx.writeFile({ fileName: outputPath });
