// Public, locked PptxGenJS writer. Images are supplied by actual generation jobs.
import fs from 'node:fs/promises';
import path from 'node:path';
import pptxgen from 'pptxgenjs';

const [contractPath, folder] = process.argv.slice(2);
const contract = JSON.parse(await fs.readFile(contractPath, 'utf8'));
if (!contract.pages?.length) throw new Error('Empty delivery contract');

function presentation() {
  const pptx = new pptxgen();
  pptx.layout = 'LAYOUT_WIDE';
  pptx.author = 'FactPPTv2';
  pptx.subject = '57098-full-slide.v1';
  pptx.title = contract.title;
  pptx.lang = 'zh-CN';
  pptx.theme = { headFontFace: 'Microsoft YaHei', bodyFontFace: 'Microsoft YaHei', lang: 'zh-CN' };
  return pptx;
}

const editable = presentation();
const imageDeck = presentation();
for (const [index, page] of contract.pages.entries()) {
  const notes = [page.title, page.locked_text, '来源', ...page.source_locations.map(s => `${s.filename} · ${s.location} · SHA256 ${s.source_sha256}`)].join('\n');
  const slide = editable.addSlide();
  slide.background = { color: 'FFFFFF' };
  slide.addText(page.title, { x: .65, y: .45, w: 12.0, h: .8, fontSize: 28, bold: true, color: '17354A', margin: 0, breakLine: false, valign: 'mid' });
  // This content deck is the editable audit counterpart, not the generated layout.
  const lines = page.locked_text.split('\n');
  const fontSize = lines.length > 15 || page.locked_text.length > 900 ? 16 : 22;
  slide.addText(page.locked_text, { x: .7, y: 1.5, w: 11.95, h: 5.2, fontSize, color: '213547', valign: 'top', margin: 0, fit: 'resize' });
  slide.addText(`${index + 1} / ${contract.pages.length}`, { x: 11.5, y: 7.08, w: 1.2, h: .2, fontSize: 10, color: '65818E', align: 'right', margin: 0 });
  slide.addNotes(notes);

  const imageSlide = imageDeck.addSlide();
  imageSlide.addImage({ path: page.image_path, x: 0, y: 0, w: 13.333333, h: 7.5 });
  imageSlide.addNotes(notes);
}
await editable.writeFile({ fileName: path.join(folder, 'editable.pptx') });
await imageDeck.writeFile({ fileName: path.join(folder, 'image_pages.pptx') });
process.stdout.write(JSON.stringify({ pages: contract.pages.length, writer: 'pptxgenjs', outputs: ['editable.pptx', 'image_pages.pptx'] }));
