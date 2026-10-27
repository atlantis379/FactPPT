"""Hospital lecture chrome for teaching layouts.

White 16:9 page and a full-width medical-blue title bar. The bar is the
measured ``title-rule`` so the PPTX matches the HTML. Body copy sits in a
56px margin with a 20px gap under the bar. Fact text still comes only from
admitted slots.
"""

CSS = """
* { box-sizing: border-box; box-shadow: none; border-radius: 0; }
html, body {
  margin: 0; width: 1920px; height: 1080px; overflow: hidden;
  background: #FFFFFF;
  color: #1A1A1A;
  font-family: "WenQuanYi Micro Hei", "Droid Sans Fallback", "Noto Sans", sans-serif;
}
.slide {
  width: 1920px; height: 1080px; padding: 0;
  display: flex; flex-direction: column;
  background: #FFFFFF;
}
.top {
  position: relative; z-index: 1;
  height: 88px; padding: 0 56px;
  display: flex; align-items: center; justify-content: space-between; gap: 28px;
  background: #0E4D7B; color: #FFFFFF;
}
.rule {
  position: absolute; z-index: 0; left: 0; top: 0;
  width: 1920px; height: 88px; margin: 0;
  background: #0E4D7B;
}
.titles, .fig { position: relative; z-index: 1; }
.titles { min-width: 0; }
.kicker {
  font-size: 16px; line-height: 1.2; letter-spacing: 0.02em;
  color: #D7E6F2; font-weight: 500;
}
h1 {
  margin: 2px 0 0; font-size: 40px; line-height: 1.15; font-weight: 700;
  color: #FFFFFF; max-width: 1640px;
}
.fig { font-size: 18px; color: #D7E6F2; letter-spacing: 0; padding-top: 0; white-space: nowrap; }
main {
  flex: 1; display: flex; flex-direction: column; justify-content: flex-start; min-height: 0;
  margin: 20px 56px 6px;
}
footer {
  display: flex; flex-direction: column; gap: 6px;
  border-top: 1px solid #D5DCE3; padding-top: 8px;
  margin: 0 56px 16px;
  font-size: 16px; line-height: 1.35; color: #5C6770;
}
.footer-line { display: flex; justify-content: space-between; align-items: flex-end; gap: 32px; }
.take-line { margin: 0; font-size: 20px; line-height: 1.35; color: #1A1A1A; font-weight: 700; }
.folio { color: #0E4D7B; font-weight: 700; font-size: 16px; letter-spacing: 0; }
.source { text-align: right; max-width: 1500px; }

.metric-split { width: 100%; min-height: 720px; display: flex; flex-direction: column; gap: 8px; }
.metric-split.beside {
  display: grid; grid-template-columns: minmax(520px, 0.92fr) 1.14fr; gap: 48px; align-items: stretch;
}
.hero-row {
  display: flex; gap: 36px; align-items: center;
  padding: 12px 0 20px; border-bottom: 1px solid #D5DCE3;
}
.metric-split.beside .hero-row {
  flex-direction: column; align-items: flex-start; justify-content: center; gap: 28px;
  padding: 8px 36px 8px 0; border-bottom: 0; border-right: 1px solid #D5DCE3;
}
.hero {
  width: auto; min-width: 280px; background: transparent; color: #0E4D7B;
  padding: 0; display: flex; flex-direction: column; justify-content: center;
}
.hero .label { font-size: 24px; letter-spacing: 0; color: #243040; font-weight: 700; }
.hero .value {
  margin-top: 4px; font-size: 92px; line-height: 0.95; font-weight: 700;
  letter-spacing: 0; color: #0E4D7B;
}
.takeaway { flex: 1; display: flex; flex-direction: column; justify-content: center; padding: 0; }
.takeaway .label { font-size: 18px; letter-spacing: 0; color: #0E4D7B; font-weight: 700; }
.takeaway .text { margin-top: 8px; font-size: 32px; line-height: 1.4; color: #1A1A1A; font-weight: 700; }
.notes { margin-top: 4px; flex: 1; min-height: 0; }
.metric-split.beside .notes { margin-top: 0; }
.notes.cols-1 { display: flex; flex-direction: column; justify-content: space-between; }
.notes.cols-2 {
  display: grid; grid-template-columns: 1fr 1fr; column-gap: 40px; row-gap: 8px; align-content: space-between;
}
.note {
  display: grid; grid-template-columns: 56px 1fr; column-gap: 8px;
  grid-template-areas: "idx title" "idx body";
  padding: 14px 0; border-bottom: 1px solid #E3E8EE;
}
.note .idx { grid-area: idx; font-size: 28px; color: #0E4D7B; font-weight: 700; letter-spacing: 0; }
.note h3 { grid-area: title; margin: 0; font-size: 28px; line-height: 1.3; color: #1A1A1A; font-weight: 700; }
.note p { grid-area: body; margin: 6px 0 0; font-size: 24px; line-height: 1.45; color: #243040; }

.metric-band {
  width: 100%; min-height: 720px; display: flex; align-items: center; justify-content: space-between;
  gap: 48px; margin: 0; background: transparent; border: 0;
}
.metric-band .cell { flex: 1; padding: 0 8px; border: 0; }
.metric-band .label { font-size: 24px; color: #243040; letter-spacing: 0; font-weight: 700; }
.metric-band .value { margin-top: 12px; font-size: 72px; line-height: 1; font-weight: 700; color: #0E4D7B; letter-spacing: 0; }

.check-wrap { width: 100%; min-height: 720px; display: flex; flex-direction: column; gap: 12px; }
.check-wrap.split {
  display: grid; grid-template-columns: minmax(460px, 0.36fr) 1fr; gap: 40px; align-items: stretch;
}
.anchor-panel {
  width: auto; background: transparent; color: #1A1A1A;
  padding: 4px 0 12px 22px; border-left: 8px solid #0E4D7B;
  display: flex; flex-direction: column; justify-content: center;
}
.check-wrap.split .anchor-panel { justify-content: center; padding-right: 12px; }
.anchor-panel .label { font-size: 18px; letter-spacing: 0; color: #0E4D7B; font-weight: 700; }
.anchor-panel .value { margin-top: 6px; font-size: 48px; line-height: 1; font-weight: 700; color: #0E4D7B; }
.anchor-panel .text { margin-top: 8px; font-size: 30px; line-height: 1.4; color: #1A1A1A; font-weight: 700; }
.checks { flex: 1; min-height: 0; }
.checks.cols-1 { display: flex; flex-direction: column; justify-content: space-between; }
.checks.cols-2 {
  display: grid; grid-template-columns: 1fr 1fr; column-gap: 48px; row-gap: 4px; align-content: space-between;
}
.check {
  display: grid; grid-template-columns: 52px 1fr; column-gap: 8px;
  grid-template-areas: "idx title" "idx body";
  padding: 12px 0; border-bottom: 1px solid #E3E8EE;
}
.check .idx { grid-area: idx; font-size: 28px; color: #0E4D7B; font-weight: 700; letter-spacing: 0; }
.check h3 { grid-area: title; margin: 0; font-size: 28px; line-height: 1.3; color: #1A1A1A; font-weight: 700; }
.check p { grid-area: body; margin: 6px 0 0; font-size: 24px; line-height: 1.45; color: #243040; }

.ce { width: 100%; min-height: 720px; display: flex; flex-direction: column; gap: 8px; }
.ce-split { display: flex; flex-direction: column; gap: 4px; }
.claim {
  flex: 0 0 auto; display: flex; flex-direction: column; justify-content: center;
  border-left: 8px solid #0E4D7B; padding: 4px 0 16px 22px;
}
.claim .label { font-size: 18px; letter-spacing: 0; color: #0E4D7B; font-weight: 700; }
.claim h2 { margin: 10px 0 0; font-size: 40px; line-height: 1.35; color: #1A1A1A; font-weight: 700; }
.ev { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.ev .label { font-size: 18px; letter-spacing: 0; color: #0E4D7B; font-weight: 700; margin: 0 0 8px; }
.ev-list { flex: 1; display: flex; flex-direction: column; justify-content: space-between; gap: 0; min-height: 0; }
.ev-item { border-bottom: 1px solid #E3E8EE; padding: 16px 0; }
.ev-item h3 { margin: 0; font-size: 26px; color: #1A1A1A; font-weight: 700; }
.ev-item p { margin: 6px 0 0; font-size: 24px; line-height: 1.45; color: #243040; }
.ev-item strong { color: #0E4D7B; font-weight: 700; }

.matrix { width: 100%; min-height: 720px; display: flex; flex-direction: column; justify-content: stretch; }
.grid {
  flex: 1; width: 100%;
  display: grid; grid-template-columns: 168px 1fr 1fr; grid-template-rows: 76px 1fr 1fr;
  border-top: 1px solid #C5CED6; border-left: 1px solid #C5CED6;
  background: #FFFFFF; min-height: 720px;
}
.corner, .gh, .rh, .cell {
  border-right: 1px solid #C5CED6; border-bottom: 1px solid #C5CED6;
  padding: 16px 22px; background: #FFFFFF;
}
.corner { background: #F4F7FA; }
.gh {
  background: #0E4D7B; color: #FFFFFF; font-size: 24px; font-weight: 700;
  display: flex; align-items: center;
}
.rh {
  background: #E8EEF4; color: #0E4D7B; font-size: 22px; font-weight: 700;
  display: flex; align-items: center;
}
.cell h3 { margin: 0; font-size: 28px; line-height: 1.3; color: #1A1A1A; font-weight: 700; }
.cell p { margin: 10px 0 0; font-size: 24px; line-height: 1.45; color: #243040; }
.cell { display: flex; flex-direction: column; justify-content: center; }

.tree {
  width: 100%; min-height: 720px;
  display: flex; flex-direction: column; align-items: center; justify-content: space-between;
}
.node { position: relative; color: #1A1A1A; }
.node-start {
  width: 84%; min-height: 84px; background: #0E4D7B; color: #FFFFFF;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 2px; padding: 14px 28px; text-align: center;
}
.node-start .chip { font-size: 15px; letter-spacing: 0; color: #D7E6F2; font-weight: 500; background: transparent; }
.node-start .ntitle { font-size: 30px; font-weight: 700; color: #FFFFFF; }
.node-decision {
  width: 92%; background: #FFFFFF; border: 2px solid #0E4D7B;
  padding: 16px 32px 18px; text-align: center;
}
.node-decision .chip, .node-action .chip, .node-exclude .chip {
  font-size: 15px; letter-spacing: 0; font-weight: 700; background: transparent; padding: 0;
}
.node-decision .chip { color: #0E4D7B; }
.node-decision .ntitle { margin-top: 2px; font-size: 30px; font-weight: 700; color: #1A1A1A; }
.threshold {
  display: block; margin-top: 8px; padding: 0; background: transparent;
  color: #0E4D7B; font-size: 28px; font-weight: 700;
}
.node-action {
  width: 100%; background: #FFFFFF; border: 2px solid #0E4D7B;
  padding: 16px 22px 18px; text-align: left;
}
.node-action .chip { color: #0E4D7B; }
.node-exclude {
  width: 100%; background: #FFFFFF; border: 2px dashed #8A5A2A;
  padding: 16px 22px 18px; text-align: left;
}
.node-exclude .chip { color: #8A5A2A; }
.node-action .ntitle, .node-exclude .ntitle { margin-top: 2px; font-size: 26px; font-weight: 700; color: #1A1A1A; }
.node-action .nbody, .node-exclude .nbody { margin-top: 8px; font-size: 22px; line-height: 1.45; color: #243040; }
.subline { margin-top: 8px; padding-top: 8px; border-top: 1px solid #D5DCE3; font-size: 22px; color: #1A1A1A; }
.stem { width: 3px; height: 36px; background: #2C3E50; }
.split { width: 96%; display: flex; justify-content: space-between; position: relative; }
.bridge { position: absolute; left: 23.5%; right: 23.5%; top: 0; height: 3px; background: #2C3E50; }
.arm { width: 47%; display: flex; flex-direction: column; align-items: center; }
.stem-label { position: relative; width: 3px; height: 44px; }
.stem-label .stem { height: 44px; }
.edge-label {
  position: absolute; left: 16px; top: 12px;
  font-size: 22px; font-weight: 700; color: #1A1A1A; white-space: nowrap; background: transparent;
}

.table-wrap { width: 100%; height: 720px; display: flex; flex-direction: column; justify-content: flex-start; padding-top: 2px; }
table.clinical { width: 100%; height: 100%; border-collapse: collapse; background: #FFFFFF; border: 1px solid #C5CED6; }
caption { caption-side: bottom; text-align: left; padding-top: 8px; font-size: 16px; color: #5C6770; }
th {
  background: #0E4D7B; color: #FFFFFF; font-weight: 700; font-size: 20px;
  text-align: left; padding: 12px 14px; vertical-align: middle;
  border: 1px solid #0E4D7B;
}
td {
  font-size: 20px; line-height: 1.4; padding: 12px 14px; vertical-align: middle;
  border: 1px solid #D5DCE3; color: #1A1A1A; background: #FFFFFF;
}
td.rowhead { font-weight: 700; color: #1A1A1A; background: #F4F7FA; }
td.hi { background: #FFF6DE; color: #1A1A1A; }
th.hi { background: #A67C2D; color: #FFFFFF; border-color: #A67C2D; }
td.yes-word { color: #146C43; font-weight: 700; }
td.no-word { color: #9E2F2F; font-weight: 700; }
.badge { display: inline; padding: 0; background: transparent; font-size: inherit; font-weight: 700; line-height: inherit; }
.badge-yes, .badge-no { background: transparent; color: inherit; }
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
