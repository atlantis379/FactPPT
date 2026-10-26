"""Shared academic-steel chrome. Body slides use rules and color blocks, not floating cards."""

CSS = """
* { box-sizing: border-box; box-shadow: none; border-radius: 0; }
html, body {
  margin: 0; width: 1920px; height: 1080px; overflow: hidden;
  background: #F3F1EB;
  color: #1B2838;
  font-family: "Noto Sans", "WenQuanYi Micro Hei", sans-serif;
}
.slide {
  width: 1920px; height: 1080px; padding: 48px 72px 36px;
  display: flex; flex-direction: column;
}
.top { display: flex; justify-content: space-between; align-items: flex-start; }
.kicker {
  font-size: 18px; letter-spacing: 0.16em; color: #5E7184; font-weight: 700;
}
h1 {
  margin: 8px 0 0; font-size: 52px; line-height: 1.15; font-weight: 700;
  color: #0E2C4A; max-width: 1500px;
}
.rule { width: 72px; height: 4px; background: #1F6F78; margin-top: 16px; }
.fig { font-size: 18px; color: #5E7184; letter-spacing: 0.08em; padding-top: 8px; }
main { flex: 1; display: flex; flex-direction: column; min-height: 0; margin-top: 28px; }
footer {
  display: flex; justify-content: space-between; align-items: flex-end; gap: 32px;
  border-top: 1px solid #DDD7CC; padding-top: 12px; margin-top: 16px;
  font-size: 16px; color: #6A6258;
}
.folio { color: #0E2C4A; font-weight: 700; font-size: 18px; letter-spacing: 0.04em; }
.source { text-align: right; max-width: 1500px; line-height: 1.4; }

.hero-row { display: flex; gap: 48px; align-items: stretch; min-height: 240px; }
.hero {
  width: 560px; background: #0E2C4A; color: #fff;
  padding: 32px 40px; display: flex; flex-direction: column; justify-content: center;
}
.hero .label { font-size: 20px; letter-spacing: 0.08em; color: #D5E2EA; }
.hero .value { margin-top: 8px; font-size: 112px; line-height: 0.95; font-weight: 700; letter-spacing: -0.03em; }
.takeaway { flex: 1; display: flex; flex-direction: column; justify-content: center; padding-right: 12px; }
.takeaway .label { font-size: 16px; letter-spacing: 0.14em; color: #1F6F78; font-weight: 700; }
.takeaway .text { margin-top: 12px; font-size: 32px; line-height: 1.45; color: #0E2C4A; font-weight: 700; }
.notes { margin-top: 12px; }
.notes.cols-1 { flex: 1; display: flex; flex-direction: column; justify-content: space-between; }
.notes.cols-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0 64px; align-content: space-between; flex: 1; }
.note {
  padding: 18px 0 20px; border-bottom: 1px solid #DDD7CC;
}
.note .idx { font-size: 15px; color: #1F6F78; font-weight: 700; letter-spacing: 0.08em; }
.note h3 { margin: 4px 0 0; font-size: 24px; line-height: 1.3; color: #0E2C4A; font-weight: 700; }
.note p { margin: 6px 0 0; font-size: 20px; line-height: 1.55; color: #3E4A56; }

.metric-band {
  display: flex; border-top: 6px solid #0E2C4A; margin-top: 12px;
}
.metric-band .cell { flex: 1; padding: 36px 32px 28px; border-right: 1px solid #DDD7CC; }
.metric-band .cell:last-child { border-right: none; }
.metric-band .label { font-size: 20px; color: #5E7184; letter-spacing: 0.06em; }
.metric-band .value { margin-top: 12px; font-size: 80px; line-height: 1; font-weight: 700; color: #0E2C4A; }

.check-wrap { display: flex; gap: 48px; flex: 1; min-height: 0; }
.anchor-panel {
  width: 440px; background: #0E2C4A; color: #fff; padding: 36px 32px;
  display: flex; flex-direction: column; justify-content: center;
}
.anchor-panel .label { font-size: 18px; letter-spacing: 0.12em; color: #D5E2EA; }
.anchor-panel .value { margin-top: 16px; font-size: 80px; line-height: 1; font-weight: 700; }
.anchor-panel .text { margin-top: 20px; font-size: 20px; line-height: 1.5; color: #E4EEF3; }
.checks { flex: 1; display: grid; gap: 0 40px; align-content: start; }
.checks.cols-1 { grid-template-columns: 1fr; }
.checks.cols-2 { grid-template-columns: 1fr 1fr; }
.check { padding: 12px 0 14px; border-bottom: 1px solid #DDD7CC; }
.check .idx { font-size: 15px; color: #1F6F78; font-weight: 700; letter-spacing: 0.06em; }
.check h3 { margin: 2px 0 0; font-size: 22px; line-height: 1.3; color: #0E2C4A; font-weight: 700; }
.check p { margin: 4px 0 0; font-size: 18px; line-height: 1.5; color: #3E4A56; }

.ce { display: flex; gap: 64px; flex: 1; min-height: 0; }
.claim {
  flex: 0 0 46%; display: flex; flex-direction: column; justify-content: center;
  border-left: 8px solid #0E2C4A; padding: 12px 12px 12px 32px;
}
.claim .label { font-size: 16px; letter-spacing: 0.14em; color: #1F6F78; font-weight: 700; }
.claim h2 { margin: 14px 0 0; font-size: 40px; line-height: 1.35; color: #0E2C4A; font-weight: 700; }
.ev { flex: 1; display: flex; flex-direction: column; justify-content: center; }
.ev .label { font-size: 16px; letter-spacing: 0.14em; color: #1F6F78; font-weight: 700; margin-bottom: 6px; }
.ev-item { border-top: 1px solid #DDD7CC; padding: 14px 0 16px; }
.ev-item h3 { margin: 0; font-size: 20px; color: #0E2C4A; font-weight: 700; }
.ev-item p { margin: 6px 0 0; font-size: 20px; line-height: 1.5; color: #3E4A56; }
.ev-item strong { color: #0E2C4A; font-weight: 700; }

.matrix { flex: 1; display: flex; flex-direction: column; justify-content: center; }
.grid {
  display: grid; grid-template-columns: 168px 1fr 1fr; grid-template-rows: 64px 1fr 1fr;
  border-top: 1px solid #D5CFC4; border-left: 1px solid #D5CFC4; min-height: 640px;
}
.corner, .gh, .rh, .cell { border-right: 1px solid #D5CFC4; border-bottom: 1px solid #D5CFC4; padding: 16px 20px; }
.corner { background: #F3F1EB; }
.gh { background: #0E2C4A; color: #fff; font-size: 22px; font-weight: 700; display: flex; align-items: center; }
.rh { background: #E7EEF2; color: #0E2C4A; font-size: 20px; font-weight: 700; display: flex; align-items: center; }
.cell h3 { margin: 0; font-size: 24px; color: #0E2C4A; font-weight: 700; }
.cell p { margin: 10px 0 0; font-size: 18px; line-height: 1.5; color: #3E4A56; }

.tree { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.node { position: relative; }
.node-start {
  width: 680px; min-height: 84px; background: #0E2C4A; color: #fff;
  display: flex; align-items: center; justify-content: center; gap: 18px;
}
.node-start .chip { font-size: 14px; letter-spacing: 0.14em; color: #D5E2EA; }
.node-start .ntitle { font-size: 28px; font-weight: 700; }
.node-decision {
  width: 760px; background: #fff; border: 2px solid #0E2C4A; padding: 16px 28px 18px;
}
.node-decision .chip, .node-action .chip, .node-exclude .chip {
  font-size: 14px; letter-spacing: 0.14em; font-weight: 700;
}
.node-decision .chip { color: #1F6F78; }
.node-decision .ntitle { margin-top: 4px; font-size: 28px; font-weight: 700; color: #0E2C4A; }
.threshold {
  display: inline-block; margin-top: 8px; padding: 4px 10px;
  background: #F4EBD4; color: #0E2C4A; font-size: 22px; font-weight: 700;
}
.node-action {
  width: 500px; background: #E7EEF2; border-left: 6px solid #1F4E79; padding: 16px 20px 18px;
}
.node-action .chip { color: #1F4E79; }
.node-exclude {
  width: 500px; background: #F7F5F0; border: 1.5px dashed #8A8175; padding: 16px 20px 18px;
}
.node-exclude .chip { color: #8A4B3C; }
.node-action .ntitle, .node-exclude .ntitle { margin-top: 4px; font-size: 24px; font-weight: 700; color: #0E2C4A; }
.node-action .nbody, .node-exclude .nbody { margin-top: 6px; font-size: 18px; line-height: 1.45; color: #3E4A56; }
.subline { margin-top: 8px; padding-top: 8px; border-top: 1px solid #D5CFC4; font-size: 18px; color: #0E2C4A; }
.stem { width: 2px; height: 40px; background: #5C6B7A; }
.split { width: 1180px; display: flex; justify-content: space-between; position: relative; }
.bridge { position: absolute; left: 250px; right: 250px; top: 0; height: 2px; background: #5C6B7A; }
.arm { width: 500px; display: flex; flex-direction: column; align-items: center; }
.stem-label { position: relative; width: 2px; height: 56px; }
.stem-label .stem { height: 56px; }
.edge-label {
  position: absolute; left: 14px; top: 16px;
  font-size: 20px; font-weight: 700; color: #0E2C4A; white-space: nowrap;
}

.table-wrap { flex: 1; display: flex; flex-direction: column; justify-content: flex-start; padding-top: 8px; }
table.clinical { width: 100%; border-collapse: collapse; background: #fff; }
caption { caption-side: bottom; text-align: left; padding-top: 10px; font-size: 15px; color: #6A6258; }
th {
  background: #0E2C4A; color: #fff; font-weight: 700; font-size: 18px;
  text-align: left; padding: 12px 14px; vertical-align: bottom;
}
td {
  font-size: 17px; line-height: 1.45; padding: 11px 16px; vertical-align: top;
  border-bottom: 1px solid #E4DDD2; color: #1B2838;
}
td.rowhead { font-weight: 700; color: #0E2C4A; background: #F7F6F2; width: 16%; }
td.hi, th.hi { background: #F4EBD4; color: #0E2C4A; }
th.hi { background: #8A6430; color: #fff; }
.badge { display: inline-block; padding: 2px 8px; font-size: 15px; font-weight: 700; line-height: 1.4; }
.badge-yes { background: #E5F2F2; color: #0E6B6B; }
.badge-no { background: #F8EBE7; color: #8A4B3C; }
#fd-measure { position: absolute; left: -10000px; top: 0; width: 1px; height: 1px; overflow: hidden; }
"""

MEASURE_JS = """
<script>
window.addEventListener('load', () => {
  const slots = [...document.querySelectorAll('[data-slot]')].map((el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const ownsText = !el.querySelector('[data-slot]');
    const side = (name) => ({
      w: parseFloat(cs[`border${name}Width`]) || 0,
      style: cs[`border${name}Style`],
      color: cs[`border${name}Color`]
    });
    return {
      id: el.dataset.slot,
      kind: el.dataset.kind || 'text',
      role: el.dataset.role || '',
      sourceId: el.dataset.sourceId || '',
      sourceField: el.dataset.sourceField || '',
      pairId: el.dataset.pair || '',
      fact: el.dataset.fact || '',
      status: el.dataset.status || '',
      provenance: el.dataset.provenance || '',
      slices: el.dataset.slices || '',
      x: r.x, y: r.y, w: r.width, h: r.height,
      text: ownsText ? (el.innerText || '').trim() : '',
      fill: cs.backgroundColor,
      color: cs.color,
      size: cs.fontSize,
      weight: cs.fontWeight,
      align: cs.textAlign,
      lh: cs.lineHeight,
      border: { top: side('Top'), right: side('Right'), bottom: side('Bottom'), left: side('Left') }
    };
  });
  const pre = document.createElement('pre');
  pre.id = 'fd-measure';
  pre.textContent = JSON.stringify(slots);
  document.body.appendChild(pre);
});
</script>
"""
