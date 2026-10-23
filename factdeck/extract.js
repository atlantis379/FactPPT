// Runs inside the rendered page. For one slide it returns
//  - an export model (shapes, text boxes with styled runs, tables, connectors, rasters)
//  - checks: untracked text, fact text mismatches, overflow, out-of-bounds, overlaps
// Coordinates are CSS px relative to the slide's top-left corner.
(args) => {
  const { slideId, expected } = args;
  const HIERARCHY_SHORT = 16;          // a hero value is at most 16 characters (deck.HERO_MAX_CHARS)
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
  const out = { shapes: [], texts: [], tables: [], lines: [], rasters: [], figures: [], icons: [],
    checks: { untracked: [], mismatch: [], overflow: [], bounds: [], overlap: [], figure_distortion: [], hierarchy: [], unsupported: [] }, authored: [] };

  // ---- runs: walk text nodes, split paragraphs at block-level descendants
  function runsOf(container) {
    const paras = [[]];
    const walk = (node) => {
      for (const ch of node.childNodes) {
        if (ch.nodeType === 3) {
          const cs = getComputedStyle(ch.parentElement);
          // pre-line text keeps the original's line breaks: each line is its own PowerPoint paragraph
          const lines = cs.whiteSpace === 'pre-line' ? ch.textContent.split('\n') : [ch.textContent];
          lines.forEach((line, i) => {
            if (i > 0) paras.push([]);
            const t = line.replace(/\s+/g, ' ');
            if (!t.trim() && !paras[paras.length - 1].length) return;
            paras[paras.length - 1].push({ text: t, size: px(cs.fontSize), bold: parseInt(cs.fontWeight) >= 600,
              color: color(cs.color), superscript: cs.verticalAlign !== 'baseline' && ch.parentElement.dataset.mark ? true : false,
              mark: !!ch.parentElement.closest('[data-mark]') });
          });
        } else if (ch.nodeType === 1) {
          const cs = getComputedStyle(ch);
          if (cs.display === 'none') continue;
          if (ch.tagName === 'BR') { paras.push([]); continue; }
          const block = cs.display === 'block' || cs.display === 'list-item' || cs.display === 'flex';
          if (block && paras[paras.length - 1].length) paras.push([]);
          walk(ch);
          if (block) {
            // the gap a block leaves under itself becomes the paragraph's space after
            const gap = px(cs.marginBottom) + px(cs.paddingBottom);
            const last = [...paras].reverse().find((p) => p.length);
            if (gap > 0 && last) last.forEach((r) => { r.after = Math.max(r.after || 0, gap); });
            paras.push([]);
          }
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
    const grp = el.closest('[data-group]');
    return { x: r.x + pl, y: r.y + pt, w: r.w - pl - pr, h: r.h - pt - pb, align, anchor,
      role: el.closest('.head .title, .L-cover .t, .L-divider .t') ? 'title' : '', group: grp ? slideId + ':' + grp.dataset.group : '',
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
    const grp = el.closest('[data-group]');
    // a radius in % (50% = a circle) is a share of the shorter side
    const rad = (v) => (String(v).trim().endsWith('%') ? parseFloat(v) / 100 * Math.min(r.w, r.h) : px(v));
    const shape = { ...r, fill: color(cs.backgroundColor), radius: rad(cs.borderTopLeftRadius) || rad(cs.borderTopRightRadius) || rad(cs.borderBottomRightRadius),
      line: null, accents: [], group: grp ? slideId + ':' + grp.dataset.group : '' };
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
  slide.querySelectorAll('li, .ci, .ti').forEach((el) => {
    const b = getComputedStyle(el, '::before');
    if (b.content && b.content !== 'none' && b.display !== 'none' && px(b.width) > 0) out.shapes.push(shapeOf(el, '::before'));
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
      const stroke = color(getComputedStyle(pl).stroke);
      out.lines.push({ points: pts, color: stroke ? stroke.hex : '19376d', w: parseFloat(getComputedStyle(pl).strokeWidth) || 2,
        arrow: !pl.dataset.plain, support: pl.dataset.edge, dash: getComputedStyle(pl).strokeDasharray !== 'none',
        group: pl.dataset.group ? slideId + ':' + pl.dataset.group : '' });
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
    if (p.closest('svg, style')) continue;
    if (!p.closest('[data-fact],[data-authored],[data-chrome],[data-mark]')) out.checks.untracked.push(n.textContent.trim().slice(0, 60));
  }
  slide.querySelectorAll('[data-authored]').forEach((el) => out.authored.push(el.textContent.trim()));
  slide.querySelectorAll('[data-fact]').forEach((el) => {
    const want = expected[el.dataset.fact];
    if (el.textContent.replace(/\s+/g, '') !== (want || '').replace(/\s+/g, '')) out.checks.mismatch.push({ fact: el.dataset.fact, got: el.textContent, want });
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
  // ---- hierarchy: running text in the body never outranks the title; only short values (a number, a phrase) may
  const title = slide.querySelector('.head .title');
  if (title) {
    const tsize = px(getComputedStyle(title).fontSize);
    slide.querySelectorAll('.body [data-t]').forEach((el) => {
      const text = el.textContent.replace(/\s+/g, '');
      if (text.length > HIERARCHY_SHORT && px(getComputedStyle(el).fontSize) > tsize + 0.5)
        out.checks.hierarchy.push(text.slice(0, 30));
    });
  }
  // ---- rings of free pages: drawn natively from the percentages the code computed
  out.rings = [...slide.querySelectorAll('[data-ring]')].map((el) => {
    const c = (sel) => { const p = el.querySelector(sel); return p ? color(getComputedStyle(p).stroke) : null; };
    const pale = el.querySelector('.ring-pale');
    return { ...rel(el.getBoundingClientRect()), solid: parseFloat(el.dataset.solid), pale: parseFloat(el.dataset.pale),
      thick: parseFloat(el.dataset.thick), track: c('.ring-track'), tone: c('.ring-solid') || c('.ring-pale'),
      paleOpacity: pale ? parseFloat(getComputedStyle(pale).strokeOpacity) : 1 };
  });
  // ---- icons of composed pages: exported from their files, above the surfaces they sit on
  slide.querySelectorAll('img[data-icon]').forEach((el) => out.icons.push({ id: el.dataset.icon, ...rel(el.getBoundingClientRect()) }));
  // ---- source figures: exported from the archived original; must be whole, in bounds and uncovered
  slide.querySelectorAll('img[data-figure]').forEach((el) => {
    const r = rel(el.getBoundingClientRect());
    out.figures.push({ id: el.dataset.figure, ...r, nw: el.naturalWidth, nh: el.naturalHeight });
    if (!el.complete || !el.naturalWidth) out.checks.figure_distortion.push(el.dataset.figure + '（图片未加载）');
    if (r.x < -0.5 || r.y < -0.5 || r.x + r.w > 1280.5 || r.y + r.h > 720.5) out.checks.bounds.push('图超出页面：' + el.dataset.figure);
    const A = el.getBoundingClientRect();
    slide.querySelectorAll('[data-t]').forEach((t) => {
      const B = t.getBoundingClientRect();
      const ix = Math.min(A.right, B.right) - Math.max(A.left, B.left), iy = Math.min(A.bottom, B.bottom) - Math.max(A.top, B.top);
      if (ix > 1 && iy > 1) out.checks.overlap.push(['图 ' + el.dataset.figure, t.textContent.trim().slice(0, 24)]);
    });
  });
  // ---- chart bars: drawn length, recomputed from the facts in Python
  out.chart_bars = [...slide.querySelectorAll('[data-bar]')].map((el) => {
    const r = el.getBoundingClientRect();
    return { fact: el.dataset.bar, length: el.dataset.dir === 'h' ? r.width : r.height, plot: parseFloat(el.dataset.plot) };
  });
  // free pages: bars (the longer side is the length) and whatever PowerPoint could not show the way the browser does
  slide.querySelectorAll('[data-value-of]:not([data-ring]):not([data-pictogram])').forEach((el) => {
    const r = el.getBoundingClientRect();
    out.chart_bars.push({ fact: el.dataset.valueOf, scale: el.dataset.scale, length: Math.max(r.width, r.height) });
  });
  if (slide.classList.contains('L-free')) {
    slide.querySelectorAll('.body *').forEach((el) => {
      if (el.closest('svg') && el.tagName.toLowerCase() !== 'svg') return;
      const cs = getComputedStyle(el), what = (el.textContent || el.tagName).trim().slice(0, 20);
      const bad = [];
      if (cs.boxShadow !== 'none') bad.push('阴影');
      if (cs.transform !== 'none') bad.push('变换');
      if (parseFloat(cs.opacity) < 1) bad.push('透明度');
      if (cs.backgroundImage !== 'none') bad.push('背景图/渐变');
      if (cs.textShadow !== 'none') bad.push('文字阴影');
      if (cs.filter !== 'none') bad.push('滤镜');
      if (cs.fontStyle === 'italic') bad.push('斜体');
      if (cs.textDecorationLine !== 'none') bad.push('下划线/删除线');
      if (cs.letterSpacing !== 'normal' && px(cs.letterSpacing) !== 0) bad.push('字距');
      const painted = color(cs.backgroundColor) || ['Top', 'Right', 'Bottom', 'Left'].some((s) => px(cs['border' + s + 'Width']) > 0 && cs['border' + s + 'Style'] !== 'none');
      if (painted && !el.hasAttribute('data-shape') && el.tagName.toLowerCase() !== 'svg') bad.push('有填充或边框却没有 data-shape（不会导出）');
      if (bad.length) out.checks.unsupported.push(what + '：' + bad.join('、'));
    });
  }
  // ---- occupancy: how far down the body's content reaches, as a share of the body's height (the body is top-anchored,
  // so a low share means an empty lower part of the page)
  const bodyEl = slide.querySelector('.body');
  if (bodyEl) {
    const B = bodyEl.getBoundingClientRect(), cs = getComputedStyle(bodyEl);
    const top = B.top + px(cs.paddingTop), height = B.bottom - px(cs.paddingBottom) - top;
    let bottom = top;
    bodyEl.querySelectorAll('[data-t], [data-shape], table, img, svg').forEach((el) => {
      const r = el.getBoundingClientRect(); if (r.height > 0 && r.width > 0) bottom = Math.max(bottom, r.bottom);
    });
    out.occupancy = height > 0 ? Math.round(Math.min(1, (bottom - top) / height) * 100) / 100 : 1;
    // ---- largest hole: the biggest rectangle of the body that holds no ink, as a share of the body's area. Ink is
    // what the eye sees as content: the line boxes of text (not the boxes around it), filled or tinted surfaces,
    // pictures and drawn lines. An outlined box with little text in it still counts as a hole.
    const G = 8, left = B.left + px(cs.paddingLeft), width = B.right - px(cs.paddingRight) - left;
    const nx = Math.max(1, Math.floor(width / G)), ny = Math.max(1, Math.floor(height / G));
    const ink = Array.from({ length: ny }, () => new Uint8Array(nx));
    const mark = (r) => {
      if (r.width <= 0 || r.height <= 0) return;
      const x0 = Math.max(0, Math.floor((r.left - left) / G)), x1 = Math.min(nx - 1, Math.floor((r.right - left - 0.01) / G));
      const y0 = Math.max(0, Math.floor((r.top - top) / G)), y1 = Math.min(ny - 1, Math.floor((r.bottom - top - 0.01) / G));
      for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) ink[y][x] = 1;
    };
    const range = document.createRange();
    bodyEl.querySelectorAll('[data-t], td, th').forEach((el) => {
      range.selectNodeContents(el);
      [...range.getClientRects()].forEach(mark);
    });
    bodyEl.querySelectorAll('[data-shape], td, th').forEach((el) => {      // hairlines and thin bars divide, they do not fill
      const c = color(getComputedStyle(el).backgroundColor), r = el.getBoundingClientRect();
      if (c && c.hex !== 'ffffff' && r.width >= 6 && r.height >= 6) mark(r);
    });
    bodyEl.querySelectorAll('img, svg polyline, svg rect, svg path:not(marker path)').forEach((el) => mark(el.getBoundingClientRect()));
    // maximal all-empty rectangle (histogram method)
    const hgt = new Array(nx).fill(0);
    let best = 0, rect = null;
    for (let y = 0; y < ny; y++) {
      for (let x = 0; x < nx; x++) hgt[x] = ink[y][x] ? 0 : hgt[x] + 1;
      const st = [];
      for (let x = 0; x <= nx; x++) {
        const h = x < nx ? hgt[x] : 0;
        let start = x;
        while (st.length && st[st.length - 1][1] >= h) {
          const [sx, sh] = st.pop();
          if (sh * (x - sx) > best) { best = sh * (x - sx); rect = { x: sx * G, y: (y - sh + 1) * G, w: (x - sx) * G, h: sh * G }; }
          start = sx;
        }
        st.push([start, h]);
      }
    }
    out.hole = { share: Math.round(best / (nx * ny) * 100) / 100, rect };
    // ---- composition metrics (signals for the author and reviewer, calibrated on reviewed pages; never errors)
    // balance: where the ink's centre of mass sits against the body centre (1 = centred, 0 = in a corner)
    let mass = 0, mx = 0, my = 0;
    for (let y = 0; y < ny; y++) for (let x = 0; x < nx; x++) if (ink[y][x]) { mass++; mx += x + 0.5; my += y + 0.5; }
    const dx = mass ? (mx / mass - nx / 2) / (nx / 2) : 0, dy = mass ? (my / mass - ny / 2) / (ny / 2) : 0;
    // alignment: share of text blocks whose left edge lines up (±2 px) with another block's left edge
    const blocks = [...bodyEl.querySelectorAll('[data-t]')].map((el) => el.getBoundingClientRect()).filter((r) => r.width > 0 && r.height > 0);
    const aligned = blocks.filter((a, i) => blocks.some((b, j) => i !== j && Math.abs(a.left - b.left) <= 2)).length;
    // spacing regularity: vertical gaps between blocks stacked on one left edge (1 = all gaps equal)
    const cols = {};
    blocks.forEach((r) => { const k = Math.round(r.left / 4); (cols[k] = cols[k] || []).push(r); });
    const gaps = [];
    Object.values(cols).forEach((rs) => {
      rs.sort((a, b) => a.top - b.top);
      for (let i = 1; i < rs.length; i++) { const g = rs[i].top - rs[i - 1].bottom; if (g >= 0 && g < 120) gaps.push(g); }
    });
    const mean = gaps.length ? gaps.reduce((a, b) => a + b, 0) / gaps.length : 0;
    const sd = gaps.length ? Math.sqrt(gaps.reduce((a, b) => a + (b - mean) ** 2, 0) / gaps.length) : 0;
    // type sizes: distinct sizes of running text in the body (14–23 px; references and labels below, data values above)
    const sizes = new Set();
    const walker2 = document.createTreeWalker(bodyEl, NodeFilter.SHOW_TEXT);
    let t2;
    while ((t2 = walker2.nextNode())) {
      if (!t2.textContent.trim() || t2.parentElement.closest('[data-mark]')) continue;
      const fs = Math.round(px(getComputedStyle(t2.parentElement).fontSize));
      if (fs >= 14 && fs < 24) sizes.add(fs);
    }
    // strong areas: dark filled surfaces larger than a marker (bars are data marks, not surfaces)
    const dark = [...bodyEl.querySelectorAll('[data-shape], th')].filter((el) => {
      if (el.classList.contains('bar') || el.hasAttribute('data-bar')) return false;
      const c = color(getComputedStyle(el).backgroundColor), r = el.getBoundingClientRect();
      if (!c || r.width * r.height < 900) return false;
      const [R, G, B] = [0, 2, 4].map((i) => parseInt(c.hex.slice(i, i + 2), 16) / 255);
      return 0.2126 * R + 0.7152 * G + 0.0722 * B < 0.3 && c.a > 0.5;
    });
    const headRow = bodyEl.querySelector('th') ? 1 : 0;                  // a table header row counts once, not per cell
    out.metrics = { balance: Math.round((1 - Math.sqrt((dx * dx + dy * dy) / 2)) * 100) / 100, centre: [Math.round(dx * 100) / 100, Math.round(dy * 100) / 100],
      alignment: blocks.length ? Math.round(aligned / blocks.length * 100) / 100 : 1,
      regularity: mean ? Math.round(Math.max(0, 1 - sd / mean) * 100) / 100 : 1,
      type_sizes: [...sizes].sort((a, b) => a - b),
      strong_areas: dark.filter((el) => el.tagName !== 'TH').length + headRow };
  }
  // tables in bounds
  // body content must stay above the footer
  const foot = slide.querySelector('.foot');
  if (foot) {
    const limit = rel(foot.getBoundingClientRect()).y;
    slide.querySelectorAll('.body [data-t], .body table, .body [data-shape], .body img[data-figure]').forEach((el) => {
      const r = rel(el.getBoundingClientRect());
      if (r.h > 0 && r.y + r.h > limit + 0.5) out.checks.bounds.push('正文超出版心（与页脚重叠）：' + el.textContent.trim().slice(0, 30));
    });
  }
  return out;
}
