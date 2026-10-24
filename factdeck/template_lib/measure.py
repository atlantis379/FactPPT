"""Playwright layout QA for template-library slides (overflow, outside canvas, footer overlap, SVG text
collisions).  Used by tools/render_pharma_previews.py, tools/select_layouts.py and the template deck pipeline."""

MEASURE_JS = r"""
() => {
  const out = [];
  const slide = document.querySelector('.slide');
  const S = slide.getBoundingClientRect();
  const tol = 1.5;
  slide.querySelectorAll('[data-check="fit"]').forEach(el => {
    if (el.scrollHeight > el.clientHeight + tol || el.scrollWidth > el.clientWidth + tol) {
      out.push({kind:'overflow', slot: el.dataset.slot || el.className,
        sh: el.scrollHeight, ch: el.clientHeight, sw: el.scrollWidth, cw: el.clientWidth});
    }
  });
  // text clipped by ellipsis / overflow hidden
  slide.querySelectorAll('.htitle,.sub,.foot .row,.p,.d').forEach(el => {
    if (el.scrollWidth > el.clientWidth + tol) out.push({kind:'ellipsis', slot: el.dataset.slot || el.className,
      sw: el.scrollWidth, cw: el.clientWidth});
  });
  slide.querySelectorAll('*').forEach(el => {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return;
    if (r.left < S.left - tol || r.top < S.top - tol || r.right > S.right + tol || r.bottom > S.bottom + tol) {
      out.push({kind:'outside', tag: el.tagName, cls: String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className),
        r: [r.left - S.left, r.top - S.top, r.right - S.left, r.bottom - S.top].map(Math.round)});
    }
  });
  slide.querySelectorAll('svg').forEach(svg => {
    const B = svg.getBoundingClientRect();
    svg.querySelectorAll('text').forEach(t => {
      const r = t.getBoundingClientRect();
      if (r.left < B.left - tol || r.right > B.right + tol || r.top < B.top - tol || r.bottom > B.bottom + tol)
        out.push({kind:'svg-text-outside', text: t.textContent.slice(0, 24),
          r: [r.left - B.left, r.top - B.top, r.right - B.left, r.bottom - B.top].map(Math.round), box: [B.width, B.height]});
    });
  });
  // HTML text boxes inside svg-overlay containers (moa) must fit
  slide.querySelectorAll('[data-box]').forEach(el => {
    if (el.scrollHeight > el.clientHeight + tol || el.scrollWidth > el.clientWidth + tol)
      out.push({kind:'box-overflow', text: el.textContent.trim().slice(0, 20), sh: el.scrollHeight, ch: el.clientHeight});
  });
  const foot = slide.querySelector('.foot');
  const main = slide.querySelector('.main');
  if (foot && main) {
    const F = foot.getBoundingClientRect();
    main.querySelectorAll('*').forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.height && r.bottom > F.top + tol) out.push({kind:'overlaps-footer', tag: el.tagName,
        text: (el.textContent || '').trim().slice(0, 20), bottom: Math.round(r.bottom - S.top)});
    });
  }
  // SVG text vs SVG text collisions (labels overlapping each other)
  slide.querySelectorAll('svg').forEach(svg => {
    const ts = [...svg.querySelectorAll('text')].map(t => [t, t.getBoundingClientRect()]);
    for (let i = 0; i < ts.length; i++) for (let j = i + 1; j < ts.length; j++) {
      const a = ts[i][1], b = ts[j][1];
      const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (ox > 2 && oy > 3) out.push({kind:'svg-text-collision', a: ts[i][0].textContent.slice(0, 16), b: ts[j][0].textContent.slice(0, 16)});
    }
  });
  return out;
}
"""
