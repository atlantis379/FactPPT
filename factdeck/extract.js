// Runs inside the rendered page. For one slide it returns
//  - an export model (shapes, text boxes with styled runs, tables, connectors, rasters)
//  - checks: untracked text, fact text mismatches, overflow, out-of-bounds, overlaps
// Coordinates are CSS px relative to the slide's top-left corner.
(args) => {
  const { slideId, expected } = args;
  const slide = document.getElementById(slideId);
  const S = slide.getBoundingClientRect();
  const rel = (r) => ({ x: r.left - S.left, y: r.top - S.top, w: r.width, h: r.height });
  const px = (v) => parseFloat(v) || 0;
  const color = (c) => {
    const m = c && c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map((x) => parseFloat(x));
    if (p.length === 4 && p[3] === 0) return null;
    return { hex: p.slice(0, 3).map((v) => Math.round(v).toString(16).padStart(2, '0')).join(''), a: p.length === 4 ? p[3] : 1 };
  };
  const out = { shapes: [], texts: [], tables: [], lines: [], rasters: [], checks: { untracked: [], mismatch: [], overflow: [], bounds: [], overlap: [] }, authored: [] };

  // ---- runs: walk text nodes, split paragraphs at block-level descendants
  function runsOf(container) {
    const paras = [[]];
    const walk = (node) => {
      for (const ch of node.childNodes) {
        if (ch.nodeType === 3) {
          const t = ch.textContent.replace(/\s+/g, ' ');
          if (!t.trim() && !paras[paras.length - 1].length) continue;
          const cs = getComputedStyle(ch.parentElement);
          paras[paras.length - 1].push({ text: t, size: px(cs.fontSize), bold: parseInt(cs.fontWeight) >= 600,
            color: color(cs.color), superscript: cs.verticalAlign !== 'baseline' && ch.parentElement.dataset.mark ? true : false,
            mark: !!ch.parentElement.closest('[data-mark]') });
        } else if (ch.nodeType === 1) {
          const cs = getComputedStyle(ch);
          if (cs.display === 'none') continue;
          const block = cs.display === 'block' || cs.display === 'list-item' || cs.display === 'flex';
          if (block && paras[paras.length - 1].length) paras.push([]);
          walk(ch);
          if (block) paras.push([]);
        }
      }
    };
    walk(container);
    return paras.filter((p) => p.length).map((p) => {
      p[0].text = p[0].text.replace(/^\s+/, ''); p[p.length - 1].text = p[p.length - 1].text.replace(/\s+$/, '');
      return p.filter((r) => r.text.length);
    });
  }
  function textBox(el) {
    const cs = getComputedStyle(el);
    const r = rel(el.getBoundingClientRect());
    const pl = px(cs.paddingLeft) + px(cs.borderLeftWidth), pr = px(cs.paddingRight) + px(cs.borderRightWidth);
    const pt = px(cs.paddingTop) + px(cs.borderTopWidth), pb = px(cs.paddingBottom) + px(cs.borderBottomWidth);
    let align = cs.textAlign === 'center' || cs.justifyContent === 'center' ? 'center' : (cs.textAlign === 'right' ? 'right' : 'left');
    const anchor = cs.display === 'flex' && cs.alignItems === 'center' ? 'middle' : 'top';
    return { x: r.x + pl, y: r.y + pt, w: r.w - pl - pr, h: r.h - pt - pb, align, anchor,
      lineHeight: cs.lineHeight === 'normal' ? px(cs.fontSize) * 1.3 : px(cs.lineHeight),
      nowrap: cs.whiteSpace === 'nowrap', paras: runsOf(el) };
  }
  function shapeOf(el, pseudo) {
    const cs = getComputedStyle(el, pseudo || null);
    let r;
    if (pseudo) {
      const host = rel(el.getBoundingClientRect());
      r = { x: host.x + px(cs.left), y: host.y + px(cs.top), w: px(cs.width), h: px(cs.height) };
    } else r = rel(el.getBoundingClientRect());
    const bw = [px(cs.borderTopWidth), px(cs.borderRightWidth), px(cs.borderBottomWidth), px(cs.borderLeftWidth)];
    const shape = { ...r, fill: color(cs.backgroundColor), radius: px(cs.borderTopLeftRadius) || px(cs.borderTopRightRadius) || px(cs.borderBottomRightRadius),
      line: null, accents: [] };
    const uniform = bw.every((b) => b === bw[0]);
    if (uniform && bw[0] > 0) shape.line = { w: bw[0], color: color(cs.borderTopColor) };
    else {
      const minB = Math.min(...bw);
      if (minB > 0) shape.line = { w: minB, color: color(cs.borderRightColor) };
      if (bw[0] > minB) shape.accents.push({ x: r.x, y: r.y, w: r.w, h: bw[0], color: color(cs.borderTopColor), top: true });
      if (bw[3] > minB) shape.accents.push({ x: r.x, y: r.y, w: bw[3], h: r.h, color: color(cs.borderLeftColor) });
    }
    return shape;
  }

  // ---- shapes (+ ::before bullets)
  slide.querySelectorAll('[data-shape]').forEach((el) => out.shapes.push(shapeOf(el)));
  slide.querySelectorAll('li, .ci').forEach((el) => {
    const b = getComputedStyle(el, '::before');
    if (b.content && b.content !== 'none' && px(b.width) > 0) out.shapes.push(shapeOf(el, '::before'));
  });
  // ---- slide background
  out.background = color(getComputedStyle(slide).backgroundColor);
  // ---- rasters (decorative art without text)
  slide.querySelectorAll('[data-raster]').forEach((el) => out.rasters.push({ id: el.dataset.raster, ...rel(el.getBoundingClientRect()) }));
  // ---- connectors
  slide.querySelectorAll('svg[data-edges]').forEach((svg) => {
    const o = rel(svg.getBoundingClientRect());
    svg.querySelectorAll('polyline').forEach((pl) => {
      const pts = pl.getAttribute('points').trim().split(/\s+/).map((p) => p.split(',').map(Number)).map(([x, y]) => [x + o.x, y + o.y]);
      out.lines.push({ points: pts, color: '19376d', w: 2, arrow: true, support: pl.dataset.edge });
    });
  });
  // ---- text boxes (not inside tables)
  slide.querySelectorAll('[data-t]').forEach((el) => out.texts.push(textBox(el)));
  // ---- tables
  slide.querySelectorAll('table[data-table]').forEach((t) => {
    const tr = rel(t.getBoundingClientRect());
    const rows = [...t.rows].map((row) => ({ h: row.getBoundingClientRect().height, cells: [...row.cells].map((c) => {
      const cs = getComputedStyle(c);
      return { w: c.getBoundingClientRect().width, fill: color(cs.backgroundColor), pad: [px(cs.paddingTop), px(cs.paddingRight), px(cs.paddingBottom), px(cs.paddingLeft)],
        border: color(cs.borderBottomColor) && px(cs.borderBottomWidth) ? color(cs.borderBottomColor) : null, lineHeight: px(cs.lineHeight), paras: runsOf(c) };
    }) }));
    out.tables.push({ ...tr, rows });
  });

  // ---- checks
  const walker = document.createTreeWalker(slide, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    if (!n.textContent.trim()) continue;
    const p = n.parentElement;
    if (p.closest('svg')) continue;
    if (!p.closest('[data-fact],[data-authored],[data-chrome],[data-mark]')) out.checks.untracked.push(n.textContent.trim().slice(0, 60));
  }
  slide.querySelectorAll('[data-authored]').forEach((el) => out.authored.push(el.textContent.trim()));
  slide.querySelectorAll('[data-fact]').forEach((el) => {
    const want = expected[el.dataset.fact];
    if (el.textContent !== want) out.checks.mismatch.push({ fact: el.dataset.fact, got: el.textContent, want });
  });
  const tb = [...slide.querySelectorAll('[data-t], td, th')];
  tb.forEach((el) => {
    if (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1)
      out.checks.overflow.push({ text: el.textContent.trim().slice(0, 40), sh: el.scrollHeight, ch: el.clientHeight, sw: el.scrollWidth, cw: el.clientWidth });
    const r = rel(el.getBoundingClientRect());
    if (r.x < -0.5 || r.y < -0.5 || r.x + r.w > 1280.5 || r.y + r.h > 720.5) out.checks.bounds.push(el.textContent.trim().slice(0, 40));
  });
  const leaf = [...slide.querySelectorAll('[data-t]')];
  for (let i = 0; i < leaf.length; i++) for (let j = i + 1; j < leaf.length; j++) {
    const a = leaf[i], b = leaf[j];
    if (a.contains(b) || b.contains(a)) continue;
    const A = a.getBoundingClientRect(), B = b.getBoundingClientRect();
    const ix = Math.min(A.right, B.right) - Math.max(A.left, B.left), iy = Math.min(A.bottom, B.bottom) - Math.max(A.top, B.top);
    if (ix > 2 && iy > 2) out.checks.overlap.push([a.textContent.trim().slice(0, 24), b.textContent.trim().slice(0, 24)]);
  }
  // tables in bounds
  slide.querySelectorAll('table').forEach((t) => {
    const r = rel(t.getBoundingClientRect());
    if (r.y + r.h > 720 - 60) out.checks.bounds.push('表格超出正文区域（与页脚重叠）');
  });
  return out;
}
