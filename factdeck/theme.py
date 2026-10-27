"""Hospital lecture chrome for teaching layouts.

White 16:9 page, a full-width title bar, and one list or one figure in the
body. The title bar is the measured ``title-rule`` so the PPTX matches the
HTML. Fact text still comes only from admitted slots.
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
  height: 136px; padding: 0 104px;
  display: flex; align-items: center; justify-content: space-between; gap: 32px;
  background: #0E4D7B; color: #FFFFFF;
}
.rule {
  position: absolute; z-index: 0; left: 0; top: 0;
  width: 1920px; height: 136px; margin: 0;
  background: #0E4D7B;
}
.titles, .fig { position: relative; z-index: 1; }
.titles { min-width: 0; }
.kicker {
  font-size: 18px; line-height: 1.3; letter-spacing: 0.02em;
  color: #D7E6F2; font-weight: 500;
}
h1 {
  margin: 6px 0 0; font-size: 46px; line-height: 1.2; font-weight: 700;
  color: #FFFFFF; max-width: 1500px;
}
.fig { font-size: 20px; color: #D7E6F2; letter-spacing: 0; padding-top: 28px; white-space: nowrap; }
main {
  flex: 1; display: flex; flex-direction: column; min-height: 0;
  margin: 40px 104px 8px;
}
footer {
  display: flex; justify-content: space-between; align-items: flex-end; gap: 32px;
  border-top: 1px solid #D5DCE3; padding-top: 10px;
  margin: 0 104px 26px;
  font-size: 15px; line-height: 1.4; color: #5C6770;
}
.folio { color: #0E4D7B; font-weight: 700; font-size: 16px; letter-spacing: 0; }
.source { text-align: right; max-width: 1480px; }

.hero-row {
  display: flex; gap: 56px; align-items: center;
  padding: 8px 0 28px; border-bottom: 1px solid #D5DCE3;
}
.hero {
  width: auto; min-width: 280px; background: transparent; color: #0E4D7B;
  padding: 0; display: flex; flex-direction: column; justify-content: center;
}
.hero .label { font-size: 22px; letter-spacing: 0; color: #243040; font-weight: 700; }
.hero .value {
  margin-top: 4px; font-size: 84px; line-height: 0.95; font-weight: 700;
  letter-spacing: 0; color: #0E4D7B;
}
.takeaway { flex: 1; display: flex; flex-direction: column; justify-content: center; padding: 0; }
.takeaway .label { font-size: 18px; letter-spacing: 0; color: #0E4D7B; font-weight: 700; }
.takeaway .text { margin-top: 8px; font-size: 30px; line-height: 1.45; color: #1A1A1A; font-weight: 700; }
.notes { margin-top: 8px; flex: 1; min-height: 0; }
.notes.cols-1, .notes.cols-2 {
  display: flex; flex-direction: column; justify-content: space-evenly;
}
.note {
  display: grid; grid-template-columns: 56px 1fr; column-gap: 8px;
  grid-template-areas: "idx title" "idx body";
  padding: 12px 0; border-bottom: none;
}
.note .idx { grid-area: idx; font-size: 26px; color: #0E4D7B; font-weight: 700; letter-spacing: 0; }
.note h3 { grid-area: title; margin: 0; font-size: 26px; line-height: 1.35; color: #1A1A1A; font-weight: 700; }
.note p { grid-area: body; margin: 4px 0 0; font-size: 22px; line-height: 1.5; color: #243040; }

.metric-band {
  flex: 1; display: flex; align-items: center; justify-content: space-between;
  gap: 48px; margin: 0; background: transparent; border: 0;
}
.metric-band .cell { flex: 1; padding: 0 8px; border: 0; }
.metric-band .label { font-size: 24px; color: #243040; letter-spacing: 0; font-weight: 700; }
.metric-band .value { margin-top: 12px; font-size: 72px; line-height: 1; font-weight: 700; color: #0E4D7B; letter-spacing: 0; }

.check-wrap { display: flex; flex-direction: column; gap: 12px; flex: 1; min-height: 0; }
.anchor-panel {
  width: auto; background: transparent; color: #1A1A1A;
  padding: 4px 0 16px 22px; border-left: 8px solid #0E4D7B;
  display: flex; flex-direction: column; justify-content: center;
}
.anchor-panel .label { font-size: 18px; letter-spacing: 0; color: #0E4D7B; font-weight: 700; }
.anchor-panel .value { margin-top: 6px; font-size: 48px; line-height: 1; font-weight: 700; color: #0E4D7B; }
.anchor-panel .text { margin-top: 8px; font-size: 28px; line-height: 1.45; color: #1A1A1A; font-weight: 700; }
.checks { flex: 1; display: flex; flex-direction: column; justify-content: space-evenly; min-height: 0; }
.check {
  display: grid; grid-template-columns: 56px 1fr; column-gap: 8px;
  grid-template-areas: "idx title" "idx body";
  padding: 8px 0; border-bottom: none;
}
.check .idx { grid-area: idx; font-size: 26px; color: #0E4D7B; font-weight: 700; letter-spacing: 0; }
.check h3 { grid-area: title; margin: 0; font-size: 26px; line-height: 1.3; color: #1A1A1A; font-weight: 700; }
.check p { grid-area: body; margin: 4px 0 0; font-size: 22px; line-height: 1.45; color: #243040; }

.ce { display: flex; flex-direction: column; gap: 8px; flex: 1; min-height: 0; }
.claim {
  flex: 0 0 auto; display: flex; flex-direction: column; justify-content: center;
  border-left: none; padding: 4px 0 12px;
}
.claim .label { font-size: 18px; letter-spacing: 0; color: #0E4D7B; font-weight: 700; }
.claim h2 { margin: 8px 0 0; font-size: 36px; line-height: 1.4; color: #1A1A1A; font-weight: 700; }
.ev { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.ev .label { font-size: 18px; letter-spacing: 0; color: #0E4D7B; font-weight: 700; margin: 8px 0 0; }
.ev-list { flex: 1; display: flex; flex-direction: column; justify-content: space-evenly; min-height: 0; }
.ev-item { border-top: none; padding: 6px 0; }
.ev-item h3 { margin: 0; font-size: 22px; color: #1A1A1A; font-weight: 700; }
.ev-item p { margin: 4px 0 0; font-size: 22px; line-height: 1.5; color: #243040; }
.ev-item strong { color: #0E4D7B; font-weight: 700; }

.matrix { flex: 1; display: flex; flex-direction: column; justify-content: center; }
.grid {
  display: grid; grid-template-columns: 148px 1fr 1fr; grid-template-rows: 68px 1fr 1fr;
  border-top: 1px solid #C5CED6; border-left: 1px solid #C5CED6;
  background: #FFFFFF; min-height: 620px;
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
.cell h3 { margin: 0; font-size: 24px; line-height: 1.35; color: #1A1A1A; font-weight: 700; }
.cell p { margin: 8px 0 0; font-size: 20px; line-height: 1.5; color: #243040; }

.tree { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.node { position: relative; color: #1A1A1A; }
.node-start {
  width: 760px; min-height: 78px; background: #0E4D7B; color: #FFFFFF;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 2px; padding: 12px 28px; text-align: center;
}
.node-start .chip { font-size: 15px; letter-spacing: 0; color: #D7E6F2; font-weight: 500; background: transparent; }
.node-start .ntitle { font-size: 28px; font-weight: 700; color: #FFFFFF; }
.node-decision {
  width: 820px; background: #FFFFFF; border: 2px solid #0E4D7B;
  padding: 14px 28px 16px; text-align: center;
}
.node-decision .chip, .node-action .chip, .node-exclude .chip {
  font-size: 15px; letter-spacing: 0; font-weight: 700; background: transparent; padding: 0;
}
.node-decision .chip { color: #0E4D7B; }
.node-decision .ntitle { margin-top: 2px; font-size: 28px; font-weight: 700; color: #1A1A1A; }
.threshold {
  display: block; margin-top: 6px; padding: 0; background: transparent;
  color: #0E4D7B; font-size: 24px; font-weight: 700;
}
.node-action {
  width: 540px; background: #FFFFFF; border: 2px solid #0E4D7B;
  padding: 14px 20px 16px; text-align: left;
}
.node-action .chip { color: #0E4D7B; }
.node-exclude {
  width: 540px; background: #FFFFFF; border: 2px dashed #8A5A2A;
  padding: 14px 20px 16px; text-align: left;
}
.node-exclude .chip { color: #8A5A2A; }
.node-action .ntitle, .node-exclude .ntitle { margin-top: 2px; font-size: 24px; font-weight: 700; color: #1A1A1A; }
.node-action .nbody, .node-exclude .nbody { margin-top: 6px; font-size: 18px; line-height: 1.45; color: #243040; }
.subline { margin-top: 8px; padding-top: 8px; border-top: 1px solid #D5DCE3; font-size: 18px; color: #1A1A1A; }
.stem { width: 3px; height: 32px; background: #2C3E50; }
.split { width: 1220px; display: flex; justify-content: space-between; position: relative; }
.bridge { position: absolute; left: 270px; right: 270px; top: 0; height: 3px; background: #2C3E50; }
.arm { width: 540px; display: flex; flex-direction: column; align-items: center; }
.stem-label { position: relative; width: 3px; height: 48px; }
.stem-label .stem { height: 48px; }
.edge-label {
  position: absolute; left: 16px; top: 12px;
  font-size: 22px; font-weight: 700; color: #1A1A1A; white-space: nowrap; background: transparent;
}

.table-wrap { flex: 1; display: flex; flex-direction: column; justify-content: flex-start; padding-top: 4px; }
table.clinical { width: 100%; border-collapse: collapse; background: #FFFFFF; border: 1px solid #C5CED6; }
caption { caption-side: bottom; text-align: left; padding-top: 8px; font-size: 15px; color: #5C6770; }
th {
  background: #0E4D7B; color: #FFFFFF; font-weight: 700; font-size: 18px;
  text-align: left; padding: 10px 12px; vertical-align: middle;
  border: 1px solid #0E4D7B;
}
td {
  font-size: 17px; line-height: 1.4; padding: 8px 12px; vertical-align: top;
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
