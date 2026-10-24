// Template-library HTML → native PowerPoint model (runs inside the Playwright page, one slide at a time).
// Generic: walks the rendered DOM, not template-specific markers.  Returns an ordered paint list in CSS px
// relative to the slide's top-left corner:
//   box   — element backgrounds (solid / linear-gradient), borders, radius, shadow
//   text  — one text box per block-level text owner, with styled runs (size, weight, colour, spacing)
//   table — native table grid (cells, spans, fills, borders, runs)
//   line / poly / ellipse / rect — SVG primitives mapped through getScreenCTM (chart geometry stays exact)
// Pictures are never produced; <img> or url() backgrounds are reported in `unsupported`.
(args) => {
  const slide = document.querySelector(args && args.selector ? args.selector : '.slide');
  const S = slide.getBoundingClientRect();
  const px = (v) => parseFloat(v) || 0;
  const rel = (r) => ({ x: r.left - S.left, y: r.top - S.top, w: r.width, h: r.height });
  const parseColor = (c) => {
    if (!c) return null;
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(/[\s,\/]+/).filter(Boolean).map((x) => parseFloat(x));
    const a = p.length >= 4 ? p[3] : 1;
    if (a <= 0.001) return null;
    return { hex: p.slice(0, 3).map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join(''), a };
  };
  const out = { width: S.width, height: S.height, background: null, items: [], unsupported: [], counts: {} };
  out.background = parseColor(getComputedStyle(slide).backgroundColor);

  // ---------- 1. materialize ::before / ::after as real elements (so they can be measured and exported)
  if (!document.getElementById('__np_style')) {
    const st = document.createElement('style');
    st.id = '__np_style';
    st.textContent = '.__np::before,.__np::after{content:none!important}';
    document.head.appendChild(st);
  }
  const hosts = [...slide.querySelectorAll('*')].filter((el) => !el.closest('svg'));
  hosts.unshift(slide);
  for (const el of hosts) {
    if (el.classList.contains('__np')) continue;
    const made = [];
    for (const pseudo of ['::before', '::after']) {
      const cs = getComputedStyle(el, pseudo);
      if (!cs.content || cs.content === 'none' || cs.content === 'normal' || cs.display === 'none') continue;
      const span = document.createElement('span');
      span.dataset.pseudo = pseudo;
      for (let i = 0; i < cs.length; i++) {
        const prop = cs[i];
        if (prop === 'content') continue;
        span.style.setProperty(prop, cs.getPropertyValue(prop));
      }
      const q = cs.content.match(/^"((?:[^"\\]|\\.)*)"$/);
      span.textContent = q ? q[1].replace(/\\(.)/g, '$1') : '';
      made.push([pseudo, span]);
    }
    if (made.length) {
      el.classList.add('__np');
      for (const [pseudo, span] of made) {
        if (pseudo === '::before') el.insertBefore(span, el.firstChild); else el.appendChild(span);
      }
    }
  }

  // ---------- helpers
  const all = [...slide.querySelectorAll('*')];
  const order = new Map();
  all.forEach((el, i) => order.set(el, i + 1));
  order.set(slide, 0);
  const endIndex = (el) => {
    let last = el;
    while (last.lastElementChild) last = last.lastElementChild;
    return order.get(last) || order.get(el);
  };
  const opacityOf = (el) => {
    let o = 1;
    for (let e = el; e && e !== document.body; e = e.parentElement) o *= parseFloat(getComputedStyle(e).opacity);
    return o;
  };
  const zOf = (el) => {
    let z = 0;
    for (let e = el; e && e !== slide; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.position !== 'static' && cs.zIndex !== 'auto') z = parseInt(cs.zIndex) || 0;
    }
    return z;
  };
  const hidden = (el) => {
    const cs = getComputedStyle(el);
    return cs.display === 'none' || cs.visibility === 'hidden' || cs.visibility === 'collapse';
  };
  const isInline = (el) => {
    const d = getComputedStyle(el).display;
    return d === 'inline' || d === 'contents';
  };
  const push = (item, el, phase) => {
    item.z = zOf(el);
    item.order = phase === 'text' ? endIndex(el) + 0.5 : (order.get(el) || 0);
    out.items.push(item);
    out.counts[item.type] = (out.counts[item.type] || 0) + 1;
  };

  // ---------- 2. boxes
  function gradientOf(bg, opacity) {
    const m = bg.match(/linear-gradient\((.*)\)\s*$/);
    if (!m) return null;
    const body = m[1];
    let angle = 180;
    const am = body.match(/^\s*(-?[\d.]+)deg\s*,/);
    if (am) angle = parseFloat(am[1]);
    else if (/^\s*to right/.test(body)) angle = 90;
    else if (/^\s*to left/.test(body)) angle = 270;
    else if (/^\s*to top/.test(body)) angle = 0;
    const stops = [];
    const re = /(rgba?\([^)]+\)|transparent)\s*([\d.]+%)?/g;
    let s;
    while ((s = re.exec(body))) {
      const c = s[1] === 'transparent' ? { hex: 'ffffff', a: 0 } : (parseColor(s[1]) || { hex: 'ffffff', a: 0 });
      stops.push({ hex: c.hex, a: c.a * opacity, pos: s[2] ? parseFloat(s[2]) / 100 : null });
    }
    if (stops.length < 2) return null;
    stops.forEach((st, i) => { if (st.pos === null) st.pos = i / (stops.length - 1); });
    return { angle, stops };
  }
  function shadowOf(v) {
    if (!v || v === 'none') return null;
    const first = v.split(/,(?![^(]*\))/)[0];
    if (/inset/.test(first)) return null;
    const c = parseColor((first.match(/rgba?\([^)]+\)/) || [])[0]);
    const nums = first.replace(/rgba?\([^)]+\)/, '').trim().split(/\s+/).map(px);
    if (!c) return null;
    return { dx: nums[0] || 0, dy: nums[1] || 0, blur: nums[2] || 0, color: c };
  }
  function boxOf(el) {
    if (el === slide) return;
    const cs = getComputedStyle(el);
    const r = rel(el.getBoundingClientRect());
    if (r.w < 0.5 || r.h < 0.5) return;
    const op = opacityOf(el);
    if (op < 0.01) return;
    if (cs.backgroundImage && /url\(/.test(cs.backgroundImage)) out.unsupported.push('background-image url: ' + (el.className || el.tagName));
    let fill = parseColor(cs.backgroundColor);
    if (fill) fill = { hex: fill.hex, a: fill.a * op };
    const grad = cs.backgroundImage && cs.backgroundImage !== 'none' ? gradientOf(cs.backgroundImage, op) : null;
    const sides = ['Top', 'Right', 'Bottom', 'Left'].map((s) => {
      const w = cs['border' + s + 'Style'] === 'none' || cs['border' + s + 'Style'] === 'hidden' ? 0 : px(cs['border' + s + 'Width']);
      const c = parseColor(cs['border' + s + 'Color']);
      return { w, color: c ? { hex: c.hex, a: c.a * op } : null, dash: cs['border' + s + 'Style'] };
    });
    const visibleSides = sides.filter((s) => s.w > 0 && s.color);
    const shadow = shadowOf(cs.boxShadow);
    if (!fill && !grad && !visibleSides.length) return;
    const rad = (v) => (String(v).trim().endsWith('%') ? parseFloat(v) / 100 * Math.min(r.w, r.h) : px(v));
    const radii = [cs.borderTopLeftRadius, cs.borderTopRightRadius, cs.borderBottomRightRadius, cs.borderBottomLeftRadius].map(rad);
    const uniform = visibleSides.length === 4 && sides.every((s) => s.w === sides[0].w && s.color && s.color.hex === sides[0].color.hex);
    const item = { type: 'box', ...r, fill, grad, radius: Math.max(...radii), radii, shadow: shadow ? { ...shadow, color: { hex: shadow.color.hex, a: shadow.color.a * op } } : null,
      line: uniform ? { w: sides[0].w, color: sides[0].color, dash: sides[0].dash } : null,
      edges: uniform ? [] : sides.map((s, i) => ({ side: ['top', 'right', 'bottom', 'left'][i], ...s })).filter((s) => s.w > 0 && s.color),
      tag: el.tagName.toLowerCase(), cls: String(el.className || '') };
    push(item, el, 'box');
  }

  // ---------- 3. text owners
  const textOwners = new Set();
  const tw = document.createTreeWalker(slide, NodeFilter.SHOW_TEXT);
  let tn;
  while ((tn = tw.nextNode())) {
    if (!tn.textContent.trim()) continue;
    const p = tn.parentElement;
    if (!p || p.closest('svg, style, script, table, title')) continue;
    let owner = p;
    while (owner !== slide && isInline(owner)) owner = owner.parentElement;
    textOwners.add(owner);
  }
  function runsOf(owner, blocks) {   // blocks: also take block children as paragraphs (table cells)
    const paras = [[]];
    const ranges = [];
    const walk = (node) => {
      for (const ch of node.childNodes) {
        if (ch.nodeType === 3) {
          const pe = ch.parentElement;
          if (hidden(pe)) continue;
          const cs = getComputedStyle(pe);
          const pre = /pre/.test(cs.whiteSpace);
          const lines = pre ? ch.textContent.split('\n') : [ch.textContent];
          const range = document.createRange();
          range.selectNodeContents(ch);
          ranges.push(range);
          let sup = 0;
          for (let e = pe; e && e !== owner; e = e.parentElement) {
            const va = getComputedStyle(e).verticalAlign;
            if (va === 'super' || e.tagName === 'SUP') { sup = 1; break; }
            if (va === 'sub' || e.tagName === 'SUB') { sup = -1; break; }
          }
          const tt = cs.textTransform;
          lines.forEach((line, i) => {
            if (i > 0) paras.push([]);
            let t = line.replace(/[\s\n\t]+/g, ' ');
            if (tt === 'uppercase') t = t.toUpperCase();
            if (!t.length) return;
            const col = parseColor(cs.color);
            paras[paras.length - 1].push({ text: t, size: px(cs.fontSize), bold: parseInt(cs.fontWeight) >= 600,
              color: col ? { hex: col.hex, a: col.a * opacityOf(pe) } : null, italic: cs.fontStyle === 'italic',
              spacing: cs.letterSpacing === 'normal' ? 0 : px(cs.letterSpacing), sup,
              font: cs.fontFamily.split(',')[0].replace(/["']/g, '').trim() });
          });
        } else if (ch.nodeType === 1) {
          if (hidden(ch) || ch.tagName === 'svg' || ch.tagName === 'STYLE') continue;
          if (ch.tagName === 'BR') { paras.push([]); continue; }
          if (!isInline(ch)) {                    // its own text owner — unless the caller collects blocks
            if (!blocks) continue;
            if (paras[paras.length - 1].length) paras.push([]);
            walk(ch);
            paras.push([]);
            continue;
          }
          const cs = getComputedStyle(ch);
          const fs = px(cs.fontSize);
          const cur = paras[paras.length - 1];
          if (px(cs.marginLeft) + px(cs.paddingLeft) >= fs * 0.25 && cur.length) cur.push({ ...cur[cur.length - 1], text: ' ' });
          walk(ch);
          const now = paras[paras.length - 1];
          if (px(cs.marginRight) + px(cs.paddingRight) >= fs * 0.25 && now.length) now.push({ ...now[now.length - 1], text: ' ', sup: 0 });
        }
      }
    };
    walk(owner);
    const cleaned = paras.map((p) => {
      const q = p.filter((r) => r.text.length);
      if (q.length) { q[0].text = q[0].text.replace(/^\s+/, ''); q[q.length - 1].text = q[q.length - 1].text.replace(/\s+$/, ''); }
      return q.filter((r) => r.text.length);
    });
    while (cleaned.length && !cleaned[cleaned.length - 1].length) cleaned.pop();
    while (cleaned.length && !cleaned[0].length) cleaned.shift();
    return { paras: cleaned, ranges };
  }
  function textOf(owner) {
    const { paras, ranges } = runsOf(owner);
    if (!paras.some((p) => p.length)) return;
    const rects = [];
    ranges.forEach((rg) => [...rg.getClientRects()].forEach((r) => { if (r.width > 0.1 && r.height > 0.1) rects.push(r); }));
    if (!rects.length) return;
    const cs = getComputedStyle(owner);
    const L = Math.min(...rects.map((r) => r.left)), T = Math.min(...rects.map((r) => r.top));
    const R = Math.max(...rects.map((r) => r.right)), B = Math.max(...rects.map((r) => r.bottom));
    const ob = owner.getBoundingClientRect();
    const cl = ob.left + px(cs.paddingLeft) + px(cs.borderLeftWidth), cr = ob.right - px(cs.paddingRight) - px(cs.borderRightWidth);
    const fs = px(cs.fontSize);
    const lh = cs.lineHeight === 'normal' ? fs * 1.3 : px(cs.lineHeight);
    const centers = rects.map((r) => (r.top + r.bottom) / 2).sort((a, b) => a - b);
    let nLines = 0, lastC = -1e9;
    centers.forEach((c) => { if (c - lastC > lh * 0.6) { nLines += 1; lastC = c; } });
    let align = cs.textAlign;
    if (align === 'start' || align === 'justify' || align === '-webkit-auto') align = 'left';
    if (align === 'end') align = 'right';
    if (align === '-webkit-center') align = 'center';
    if (cs.display.includes('flex') && cs.justifyContent === 'center' && cs.flexDirection.startsWith('row')) align = 'center';
    const nowrap = /nowrap|pre$/.test(cs.whiteSpace) || nLines <= paras.length;
    // content-area rects → CSS line boxes (half-leading above the first line)
    const contentH = Math.max(...rects.map((r) => r.height));
    const lead = Math.max(0, (lh - Math.min(contentH, lh * 1.5)) / 2);
    // single-line text sits where the browser put its glyphs (inline-block swatches / bullets before it stay
    // clear); wrapping text keeps the owner's content width so PowerPoint wraps at the same measure
    let x = Math.min(L, cl), w = Math.max(R, cr) - x;
    if (nowrap || cr - cl < R - L || cr <= cl) { x = L; w = R - L; }
    const item = { type: 'text', x, y: T - lead, w, h: (B - T) + 2 * lead, align, nowrap, lineHeight: lh,
      lines: nLines, paras, textW: R - L, textX: L, cls: String(owner.className || owner.tagName) };
    push(item, owner, 'text');
  }

  // ---------- 4. tables
  function tableOf(t) {
    const tr = rel(t.getBoundingClientRect());
    const rows = [...t.rows];
    const xs = new Set(), ys = [];
    rows.forEach((row) => [...row.cells].forEach((c) => { const r = c.getBoundingClientRect(); xs.add(Math.round(r.left - S.left)); xs.add(Math.round(r.right - S.left)); }));
    const cols = [...xs].sort((a, b) => a - b).filter((v, i, a) => i === 0 || v - a[i - 1] > 1.5);
    const near = (v) => cols.reduce((bi, c, i) => (Math.abs(c - v) < Math.abs(cols[bi] - v) ? i : bi), 0);
    const out_rows = rows.map((row) => {
      const rr = row.getBoundingClientRect();
      const rowFill = parseColor(getComputedStyle(row).backgroundColor);
      return { y: rr.top - S.top, h: rr.height, cells: [...row.cells].map((c) => {
        const cs = getComputedStyle(c), r = c.getBoundingClientRect();
        const { paras } = runsOf(c, true);
        const side = (s) => ({ w: cs['border' + s + 'Style'] === 'none' ? 0 : px(cs['border' + s + 'Width']), color: parseColor(cs['border' + s + 'Color']) });
        let va = cs.verticalAlign;
        return { c0: near(r.left - S.left), c1: near(r.right - S.left), fill: parseColor(cs.backgroundColor) || rowFill,
          pad: [px(cs.paddingTop), px(cs.paddingRight), px(cs.paddingBottom), px(cs.paddingLeft)],
          align: cs.textAlign === 'right' || cs.textAlign === 'end' ? 'right' : cs.textAlign === 'center' ? 'center' : 'left',
          anchor: va === 'bottom' ? 'bottom' : va === 'top' ? 'top' : 'middle',
          lineHeight: cs.lineHeight === 'normal' ? px(cs.fontSize) * 1.3 : px(cs.lineHeight),
          borders: { top: side('Top'), right: side('Right'), bottom: side('Bottom'), left: side('Left') }, paras };
      }) };
    });
    push({ type: 'table', ...tr, cols, rows: out_rows }, t, 'box');
  }

  // ---------- 5. SVG primitives
  function svgOf(svg) {
    const op0 = opacityOf(svg);
    svg.querySelectorAll('*').forEach((el) => {
      const tag = el.tagName.toLowerCase();
      if (el.closest('defs, marker, clipPath, mask, pattern, title')) return;
      if (!['rect', 'line', 'polyline', 'polygon', 'path', 'circle', 'ellipse', 'text'].includes(tag)) {
        if (['image', 'foreignobject', 'use'].includes(tag)) out.unsupported.push('svg ' + tag);
        return;
      }
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') return;
      const m = el.getScreenCTM();
      const P = (x, y) => [m.a * x + m.c * y + m.e - S.left, m.b * x + m.d * y + m.f - S.top];
      const scale = Math.sqrt(Math.abs(m.a * m.d - m.b * m.c)) || 1;
      let op = op0;
      for (let e = el; e && e !== svg; e = e.parentElement) op *= parseFloat(getComputedStyle(e).opacity);
      const fillC = cs.fill && cs.fill !== 'none' ? parseColor(cs.fill) : null;
      const fill = fillC ? { hex: fillC.hex, a: fillC.a * op * parseFloat(cs.fillOpacity) } : null;
      const strokeC = cs.stroke && cs.stroke !== 'none' ? parseColor(cs.stroke) : null;
      const sw = px(cs.strokeWidth) * scale;
      const stroke = strokeC && sw > 0 ? { hex: strokeC.hex, a: strokeC.a * op * parseFloat(cs.strokeOpacity), w: sw,
        dash: cs.strokeDasharray && cs.strokeDasharray !== 'none' } : null;
      const base = { fill, stroke, svgClass: String(el.getAttribute('class') || ''), shape: el.getAttribute('data-shape') || '' };
      if (tag === 'text') {
        const txt = el.textContent.replace(/\s+/g, ' ').trim();
        if (!txt) return;
        const r = el.getBoundingClientRect();
        const angle = Math.atan2(m.b, m.a) * 180 / Math.PI;
        const fs = px(cs.fontSize) * scale;
        const len = el.getComputedTextLength() * scale;
        const anchor = cs.textAnchor === 'middle' ? 'center' : cs.textAnchor === 'end' ? 'right' : 'left';
        const col = fill || { hex: '000000', a: 1 };
        push({ type: 'text', svg: true, x: r.left - S.left, y: r.top - S.top, w: r.width, h: r.height, cx: (r.left + r.right) / 2 - S.left,
          cy: (r.top + r.bottom) / 2 - S.top, rotation: Math.abs(angle) > 0.5 ? angle : 0, textLen: len, align: anchor, nowrap: true,
          lineHeight: fs * 1.25, lines: 1, paras: [[{ text: txt, size: fs, bold: parseInt(cs.fontWeight) >= 600, color: col, spacing: 0, sup: 0,
            font: cs.fontFamily.split(',')[0].replace(/["']/g, '').trim() }]], cls: base.svgClass }, el, 'box');
        return;
      }
      if (!fill && !stroke) return;
      if (tag === 'line') {
        const a = P(el.x1.baseVal.value, el.y1.baseVal.value), b = P(el.x2.baseVal.value, el.y2.baseVal.value);
        push({ type: 'line', ...base, points: [a, b] }, el, 'box');
      } else if (tag === 'rect') {
        const x = el.x.baseVal.value, y = el.y.baseVal.value, w = el.width.baseVal.value, h = el.height.baseVal.value;
        if (w <= 0 || h <= 0) return;
        const a = P(x, y), b = P(x + w, y + h);
        const rx = (el.rx && el.rx.baseVal ? el.rx.baseVal.value : 0) * scale;
        push({ type: 'rect', ...base, x: Math.min(a[0], b[0]), y: Math.min(a[1], b[1]), w: Math.abs(b[0] - a[0]), h: Math.abs(b[1] - a[1]), radius: rx }, el, 'box');
      } else if (tag === 'circle' || tag === 'ellipse') {
        const cx = el.cx.baseVal.value, cy = el.cy.baseVal.value;
        const rx = tag === 'circle' ? el.r.baseVal.value : el.rx.baseVal.value, ry = tag === 'circle' ? el.r.baseVal.value : el.ry.baseVal.value;
        const a = P(cx - rx, cy - ry), b = P(cx + rx, cy + ry);
        push({ type: 'ellipse', ...base, x: Math.min(a[0], b[0]), y: Math.min(a[1], b[1]), w: Math.abs(b[0] - a[0]), h: Math.abs(b[1] - a[1]) }, el, 'box');
      } else if (tag === 'polyline' || tag === 'polygon') {
        const nums = (el.getAttribute('points') || '').trim().split(/[\s,]+/).map(parseFloat);
        const pts = [];
        for (let i = 0; i + 1 < nums.length; i += 2) pts.push(P(nums[i], nums[i + 1]));
        if (pts.length >= 2) push({ type: 'poly', ...base, paths: [{ points: pts, closed: tag === 'polygon' }] }, el, 'box');
      } else if (tag === 'path') {
        const d = el.getAttribute('d') || '';
        const paths = [];
        if (/[CcSsQqTtAa]/.test(d)) {               // curves: sample the outline (still a native freeform)
          const L = el.getTotalLength(), n = Math.max(8, Math.min(160, Math.round(L / 3)));
          const pts = [];
          for (let i = 0; i <= n; i++) { const q = el.getPointAtLength(L * i / n); pts.push(P(q.x, q.y)); }
          paths.push({ points: pts, closed: /[Zz]\s*$/.test(d) });
        } else {
          const toks = d.match(/[MmLlHhVvZz]|-?(?:\d*\.\d+|\d+)(?:e-?\d+)?/g) || [];
          let i = 0, cmd = 'M', x = 0, y = 0, sx = 0, sy = 0, cur = null;
          const num = () => parseFloat(toks[i++]);
          while (i < toks.length) {
            if (/[A-Za-z]/.test(toks[i])) cmd = toks[i++];
            if (cmd === 'Z' || cmd === 'z') { if (cur) { cur.closed = true; } x = sx; y = sy; cur = null; continue; }
            if (cmd === 'M' || cmd === 'm') {
              const nx = num(), ny = num();
              x = cmd === 'm' ? x + nx : nx; y = cmd === 'm' ? y + ny : ny; sx = x; sy = y;
              cur = { points: [P(x, y)], closed: false }; paths.push(cur);
              cmd = cmd === 'm' ? 'l' : 'L';
              continue;
            }
            if (cmd === 'L') { x = num(); y = num(); } else if (cmd === 'l') { x += num(); y += num(); }
            else if (cmd === 'H') x = num(); else if (cmd === 'h') x += num();
            else if (cmd === 'V') y = num(); else if (cmd === 'v') y += num();
            else { i++; continue; }
            if (!cur) { cur = { points: [P(sx, sy)], closed: false }; paths.push(cur); }
            cur.points.push(P(x, y));
          }
        }
        const good = paths.filter((p) => p.points.length >= 2);
        if (good.length) push({ type: 'poly', ...base, paths: good }, el, 'box');
      }
    });
  }

  // ---------- 6. walk in DOM order
  for (const el of [slide, ...slide.querySelectorAll('*')]) {
    if (el !== slide && (el.closest('svg') && el.tagName.toLowerCase() !== 'svg')) continue;
    if (el.closest('table') && el.tagName !== 'TABLE') continue;
    let h = false;
    for (let e = el; e && e !== document.body; e = e.parentElement) if (hidden(e)) { h = true; break; }
    if (h) continue;
    const tag = el.tagName.toLowerCase();
    if (tag === 'img' || tag === 'picture' || tag === 'canvas' || tag === 'video') { out.unsupported.push(tag); continue; }
    if (tag === 'svg') { boxOf(el); svgOf(el); continue; }
    if (tag === 'table') { tableOf(el); continue; }
    if (tag === 'style' || tag === 'script') continue;
    boxOf(el);
    if (textOwners.has(el)) textOf(el);
  }
  out.items.forEach((it, i) => { it.seq = i; });
  out.items.sort((a, b) => (a.z - b.z) || (a.order - b.order) || (a.seq - b.seq));
  return out;
}
