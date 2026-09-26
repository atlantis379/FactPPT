# -*- coding: utf-8 -*-
"""Theme-driven CSS. Layouts only reference tokens, never literal colours."""

CANVAS_W, CANVAS_H = 1280, 720


def tokens_css(t: dict) -> str:
    keys = [
        "bg", "bg2", "surface", "ink", "ink2", "muted", "line",
        "primary", "primary_soft", "accent", "accent_soft", "accent_text", "on_primary",
        "heading", "badge", "badge_on",
        "ok", "ok_soft", "warn", "warn_soft", "danger", "danger_soft",
    ]
    missing = [k for k in keys if k not in t]
    if missing:
        raise KeyError(f"theme is missing tokens: {missing}")
    body = "".join(f"  --{k}:{t[k]};\n" for k in keys)
    return (
        ":root{\n" + body +
        f"  --font:{t['font']};\n"
        f"  --tw:{t['title_weight']};\n"
        f"  --radius:{t['radius']};\n"
        f"  --shadow:{t['shadow']};\n"
        f"  --brand-bg:{t['brand_bg']};\n"
        f"  --figure-bg:{t['figure_bg']};\n"
        f"  --title-size:{t['title_size']};\n"
        "}\n"
    )


BASE_CSS = r"""
*{ box-sizing:border-box; }
html,body{ margin:0; padding:0; background:#8a8f98; }
body{ font-family:var(--font); -webkit-font-smoothing:antialiased; }

/* each slide is a fixed-size canvas: no height ambiguity, no overflow */
.slide{
  position:relative; width:1280px; height:720px; overflow:hidden;
  background:var(--bg); color:var(--ink); font-family:var(--font);
  margin:0 auto 18px;
}
.slide::before{
  content:''; position:absolute; inset:0; pointer-events:none;
  background:
    radial-gradient(1100px 560px at 88% 108%, color-mix(in srgb, var(--accent) 14%, transparent), transparent 62%),
    radial-gradient(820px 480px at -8% -12%, color-mix(in srgb, #ffffff 55%, transparent), transparent 60%);
}

/* ---- brand bar ---- */
.brand{ position:absolute; top:0; left:0; right:0; height:60px; background:var(--brand-bg);
  display:flex; align-items:center; justify-content:space-between; padding:0 58px 0 30px;
  box-shadow:0 3px 12px rgba(0,0,0,.12); z-index:5; }
.brand .bl{ font-size:21px; font-weight:800; color:var(--on_primary); letter-spacing:.01em; }
.brand .br{ font-size:12px; color:color-mix(in srgb, var(--on_primary) 78%, transparent); white-space:nowrap; }

/* ---- title block ---- */
.tblock{ position:absolute; top:66px; left:30px; right:120px; z-index:4; }
.tblock h1{ font-size:var(--title-size); line-height:1.12; margin:0; color:var(--heading);
  font-weight:var(--tw); }
.tblock .sub{ margin-top:4px; font-size:12.5px; color:var(--ink2); font-weight:700; }

/* ---- page chip ---- */
.pnum{ position:absolute; top:15px; right:16px; z-index:6; width:28px; height:28px; border-radius:50%;
  background:color-mix(in srgb, var(--on_primary) 16%, transparent);
  border:1.5px solid color-mix(in srgb, var(--on_primary) 55%, transparent);
  color:var(--on_primary); display:flex; align-items:center; justify-content:center;
  font-size:11.5px; font-weight:800; }

/* ---- footer ---- */
.foot{ position:absolute; left:0; right:0; bottom:0; height:34px; padding:9px 30px; z-index:5;
  display:flex; justify-content:space-between; font-size:10.5px; color:var(--muted);
  border-top:1px solid var(--line); background:color-mix(in srgb, var(--surface) 62%, transparent); }
.foot b{ color:var(--heading); }

/* ---- figure / motif ---- */
.fig{ position:relative; width:100%; height:100%; border-radius:calc(var(--radius) - 4px);
  overflow:hidden; background:var(--figure-bg); border:1px solid var(--line);
  display:flex; align-items:center; justify-content:center; }
.fig .motif{ width:100%; height:100%; display:block; color:var(--accent); }
.fig.solid .motif{ width:82%; height:82%; }
.fig.dim .motif{ opacity:.85; }

/* ---- step flow (3-4 illustrated steps) ---- */
.steps{ position:absolute; top:168px; left:30px; right:30px; height:392px; display:flex; gap:14px; z-index:3; }
.step{ flex:1; min-width:0; display:flex; flex-direction:column; background:var(--surface);
  border:1px solid var(--line); border-radius:var(--radius); padding:12px 14px; box-shadow:var(--shadow); }
.step .hd{ flex:0 0 auto; display:flex; align-items:center; gap:10px; margin-bottom:7px; }
.step .badge{ flex:0 0 auto; width:34px; height:34px; border-radius:50%; background:var(--badge);
  color:var(--badge_on); display:flex; align-items:center; justify-content:center;
  font-size:14px; font-weight:800; }
.step.alt .badge{ background:var(--accent); color:var(--badge_on); }
.step .tt{ font-size:14.5px; font-weight:800; color:var(--heading); line-height:1.22; }
.step .tt em{ font-style:normal; color:var(--accent-text); font-size:11.5px; display:block; margin-top:1px; font-weight:700; }
.step .tx{ flex:0 0 auto; font-size:12px; color:var(--ink2); line-height:1.45; margin-bottom:7px; }
.step .illobox{ flex:1 1 auto; min-height:0; display:flex; }

/* ---- bottom dock (rail + callout) ---- */
.bottomdock{ position:absolute; top:570px; left:0; right:0; z-index:4; }
.rail{ padding:0 30px; }
.rail .rtrack{ display:flex; gap:14px; }
.rail .rcell{ flex:1; text-align:center; position:relative; }
.rail .rline{ position:absolute; top:4px; left:0; right:0; height:3px;
  background:linear-gradient(90deg, var(--heading), var(--accent)); opacity:.5; }
.rail .rdot{ position:relative; width:11px; height:11px; border-radius:50%; background:var(--accent);
  margin:0 auto; z-index:2; box-shadow:0 0 0 4px color-mix(in srgb, var(--bg) 95%, transparent); }
.rail .rlab{ margin-top:5px; font-size:11.5px; font-weight:800; color:var(--heading); }
.callout{ margin:7px 30px 0; display:flex; gap:12px; align-items:center;
  background:color-mix(in srgb, var(--accent) 8%, var(--surface));
  border:1px solid var(--line); border-left:5px solid var(--primary);
  border-radius:calc(var(--radius) - 4px); padding:8px 16px; box-shadow:var(--shadow); }
.callout .ci{ flex:0 0 auto; width:26px; height:26px; color:var(--accent); }
.callout .ci svg{ width:100%; height:100%; }
.callout .ct{ font-size:12px; color:var(--ink2); line-height:1.45; }
.callout .ct b{ color:var(--heading); }

/* ---- KPI row ---- */
.kpis{ position:absolute; top:156px; left:30px; right:30px; height:146px; z-index:3;
  display:grid; grid-template-columns:repeat(4,1fr); gap:15px; }
.kpi{ background:var(--surface); border:1px solid var(--line); border-radius:var(--radius);
  padding:14px 16px 12px; box-shadow:var(--shadow); position:relative; }
.kpi .num{ font-size:34px; font-weight:800; color:var(--heading); line-height:1; }
.kpi .num em{ font-style:normal; font-size:17px; color:var(--accent); margin-left:3px; }
.kpi .lab{ margin-top:8px; font-size:12.5px; color:var(--ink2); line-height:1.45; }
.kpi .tag{ position:absolute; right:12px; top:11px; font-size:10px; font-weight:700; color:var(--muted); }

/* ---- card grids ---- */
.grid{ position:absolute; left:30px; right:30px; top:156px; display:grid; gap:15px; z-index:3; }
.grid.g2{ grid-template-columns:1fr 1fr; }
.grid.g3{ grid-template-columns:repeat(3,1fr); }
.grid.g4{ grid-template-columns:repeat(4,1fr); }
.grid.rows1{ height:174px; }
.grid.rows2{ height:272px; }
.grid.rows3{ height:372px; }
.card{ background:var(--surface); border:1px solid var(--line); border-radius:var(--radius);
  padding:13px 15px; box-shadow:var(--shadow); position:relative; overflow:hidden; }
.card .ct{ font-size:14.5px; font-weight:800; color:var(--heading); margin-bottom:6px;
  display:flex; align-items:center; gap:7px; }
.card .ct .dot{ width:8px; height:8px; border-radius:50%; background:var(--accent); flex:0 0 auto; }
.card.tone-ok .ct .dot{ background:var(--ok); }
.card.tone-warn .ct .dot{ background:var(--warn); }
.card.tone-danger .ct .dot{ background:var(--danger); }
.card .cb{ font-size:12.5px; color:var(--ink2); line-height:1.5; }
.card .pv{ position:absolute; left:15px; bottom:9px; font-size:10px; font-weight:700; color:var(--muted); }
.card.tone-ok{ border-left:4px solid var(--ok); }
.card.tone-warn{ border-left:4px solid var(--warn); }
.card.tone-danger{ border-left:4px solid var(--danger); }
.card.tone-accent{ border-left:4px solid var(--accent); }

/* ---- figure band ---- */
.band{ position:absolute; left:0; right:0; display:flex; justify-content:center; z-index:2; }
.band.top-kpi{ top:322px; }
.band.top-r1{ top:350px; }
.band.top-r2{ top:448px; }
.band.top-cmp{ top:362px; }
.band.top-plain{ top:330px; }

/* ---- comparison ---- */
.cmp{ position:absolute; top:156px; left:30px; right:30px; height:186px; z-index:3;
  display:grid; grid-template-columns:1fr 1fr; gap:16px; }
.pnl{ border-radius:var(--radius); padding:16px 18px; border:1.5px solid var(--line);
  position:relative; overflow:hidden; background:var(--surface); box-shadow:var(--shadow); }
.pnl.a{ border-color:color-mix(in srgb, var(--danger) 45%, var(--line)); background:var(--danger_soft); }
.pnl.b{ border-color:color-mix(in srgb, var(--accent) 45%, var(--line)); background:var(--accent_soft); }
.pnl .ph{ font-size:15px; font-weight:800; margin-bottom:8px; }
.pnl.a .ph{ color:var(--danger); } .pnl.b .ph{ color:var(--accent-text); }
.pnl .pb{ font-size:12.5px; color:var(--ink2); line-height:1.55; }
.pnl .tagline{ position:absolute; right:14px; top:15px; font-size:10.5px; font-weight:700; color:var(--muted); }

/* ---- statement ---- */
.stmt{ position:absolute; top:180px; left:90px; right:90px; z-index:3;
  background:var(--surface); border:1px solid var(--line); border-left:6px solid var(--accent);
  border-radius:var(--radius); padding:26px 30px; box-shadow:var(--shadow); }
.stmt .sk{ font-size:13px; font-weight:800; color:var(--accent-text); letter-spacing:.06em; margin-bottom:10px; }
.stmt .sb{ font-size:19px; line-height:1.6; color:var(--ink); font-weight:600; }

/* ---- timeline ---- */
.tl{ position:absolute; top:210px; left:40px; right:40px; z-index:3; height:300px; }
.tl .tline{ position:absolute; top:74px; left:0; right:0; height:4px; border-radius:2px;
  background:linear-gradient(90deg,var(--primary),var(--accent)); opacity:.55; }
.tl .titems{ display:flex; gap:16px; height:100%; }
.tl .ti{ flex:1; position:relative; }
.tl .tdot{ position:absolute; top:66px; left:50%; margin-left:-8px; width:16px; height:16px;
  border-radius:50%; background:var(--accent); box-shadow:0 0 0 4px var(--bg); }
.tl .tcard{ position:absolute; left:0; right:0; background:var(--surface); border:1px solid var(--line);
  border-radius:var(--radius); padding:12px 14px; box-shadow:var(--shadow); }
.tl .ti.up .tcard{ bottom:180px; }
.tl .ti.dn .tcard{ top:110px; }
.tl .tcard .tt{ font-size:13.5px; font-weight:800; color:var(--heading); margin-bottom:5px; }
.tl .tcard .tb{ font-size:12px; color:var(--ink2); line-height:1.45; }

/* ---- table ---- */
.tblwrap{ position:absolute; top:158px; left:30px; right:30px; z-index:3; }
table.dk{ width:100%; border-collapse:collapse; background:var(--surface);
  border-radius:var(--radius); overflow:hidden; box-shadow:var(--shadow); }
table.dk th{ background:var(--primary); color:var(--on_primary); font-size:12.5px;
  text-align:left; padding:10px 14px; font-weight:800; }
table.dk td{ font-size:12.5px; color:var(--ink2); padding:10px 14px;
  border-top:1px solid var(--line); vertical-align:top; }
table.dk tr:nth-child(even) td{ background:color-mix(in srgb, var(--bg2) 55%, transparent); }

/* ---- cover / closing hero ---- */
.hero{ position:absolute; inset:0; overflow:hidden; background:var(--brand-bg); color:var(--on_primary); }
.hero .hbg{ position:absolute; right:0; top:0; bottom:0; width:46%;
  display:flex; align-items:center; justify-content:center; color:var(--accent); opacity:.5; }
.hero .hbg svg{ width:78%; height:78%; }
.hero .hveil{ position:absolute; inset:0;
  background:linear-gradient(90deg, color-mix(in srgb, var(--primary) 88%, #000) 0%,
             color-mix(in srgb, var(--primary) 70%, transparent) 46%, transparent 78%); }
.hero .inner{ position:absolute; inset:0; padding:52px 58px; display:flex; flex-direction:column; z-index:3; }
.hero .kick{ font-size:13px; font-weight:800; letter-spacing:.2em;
  color:color-mix(in srgb, var(--on_primary) 72%, transparent); }
.hero h1{ font-size:46px; line-height:1.14; margin:16px 0 0; font-weight:800; }
.hero .rule{ width:66px; height:5px; border-radius:3px; margin:20px 0;
  background:linear-gradient(90deg,var(--accent),color-mix(in srgb, var(--accent) 45%, #fff)); }
.hero .sub{ font-size:18px; font-weight:600;
  color:color-mix(in srgb, var(--on_primary) 84%, transparent); }
.hero .hbody{ margin-top:14px; max-width:760px; font-size:14px; line-height:1.6;
  color:color-mix(in srgb, var(--on_primary) 76%, transparent); }
.hero .meta{ margin-top:auto; font-size:13px; line-height:1.75;
  color:color-mix(in srgb, var(--on_primary) 70%, transparent); }
.hero .meta b{ color:var(--on_primary); }
.hero.mini h1{ font-size:40px; }

/* ---- chart ---- */
.chartwrap{ position:absolute; top:148px; left:20px; right:20px; height:424px; z-index:3; }
.chartwrap svg.chart{ width:100%; height:100%; display:block; }
.chartfoot{ position:absolute; top:578px; left:30px; right:30px; font-size:11px; color:var(--muted);
  line-height:1.5; }
.chartfoot .chartmiss{ color:var(--warn); font-weight:700; margin-top:3px; }
.chartfail{ padding:24px 28px; border:1.5px solid var(--danger); background:var(--danger_soft);
  border-radius:var(--radius); color:var(--danger); font-size:13px; font-weight:700; }

/* ---- image archetypes ---- */
.ph-img{ object-fit:cover; display:block; }
.img-missing{ width:100%; height:100%; display:flex; flex-direction:column; gap:6px;
  align-items:center; justify-content:center; background:var(--figure-bg);
  border:1.5px dashed var(--line); border-radius:calc(var(--radius) - 4px); color:var(--muted); }
.img-missing .im-t{ font-size:12.5px; font-weight:800; color:var(--heading); }
.img-missing .im-s{ font-size:11px; }

.imghero{ position:absolute; inset:0; overflow:hidden; }
.imghero .ph-img{ position:absolute; inset:0; }
.ihscrim{ position:absolute; inset:0;
  background:linear-gradient(90deg, color-mix(in srgb, var(--primary) 92%, #000) 0%,
             color-mix(in srgb, var(--primary) 74%, transparent) 44%, transparent 78%); }
.ihinner{ position:absolute; inset:0; padding:0 58px; display:flex; flex-direction:column;
  justify-content:center; color:var(--on_primary); }
.ihinner .kick{ font-size:13px; font-weight:800; letter-spacing:.18em;
  color:color-mix(in srgb, var(--on_primary) 76%, transparent); }
.ihinner h1{ font-size:42px; line-height:1.16; margin:14px 0 0; font-weight:800; max-width:760px; }
.ihinner .sub{ margin-top:14px; font-size:17px; font-weight:600; max-width:720px;
  color:color-mix(in srgb, var(--on_primary) 86%, transparent); }
.ihinner .body{ margin-top:12px; font-size:13.5px; line-height:1.6; max-width:700px;
  color:color-mix(in srgb, var(--on_primary) 78%, transparent); }

.imgsplit{ position:absolute; top:150px; left:30px; right:30px; bottom:46px;
  display:grid; grid-template-columns:1fr 1fr; gap:34px; align-items:center; }
.imgsplit-fig{ margin:0; border-radius:var(--radius); overflow:hidden;
  border:1px solid var(--line); box-shadow:var(--shadow); }
.imgsplit-tx h2{ font-size:26px; line-height:1.2; margin:0 0 8px; color:var(--heading);
  font-weight:var(--tw); }
.imgsplit-tx .sb{ font-size:14px; color:var(--ink2); font-weight:700; margin-bottom:14px; }
.imgsplit-tx ul{ margin:0; padding-left:18px; }
.imgsplit-tx li{ font-size:13.5px; color:var(--ink); line-height:1.75; margin-bottom:6px; }
.imgsplit-tx .nb{ margin-top:14px; font-size:11px; color:var(--muted); }

.imggrid{ position:absolute; inset:0; }
.imggrid-cell{ position:absolute; margin:0; border-radius:var(--radius); overflow:hidden;
  border:1px solid var(--line); box-shadow:var(--shadow); background:var(--surface); }
.imggrid-cell figcaption{ padding:9px 14px; font-size:12.5px; color:var(--ink2); }

/* ---- page chip (section label) + keypoint bar ---- */
.brand .chip{ position:absolute; right:86px; top:14px; height:32px; padding:0 16px;
  border-radius:16px; background:var(--surface); border:1px solid var(--line);
  color:var(--heading); font-size:12.5px; font-weight:800;
  display:flex; align-items:center; letter-spacing:.02em; z-index:6; }
.kpbar{ position:absolute; left:30px; right:30px; bottom:46px; padding:11px 16px;
  border-radius:var(--radius); display:flex; gap:10px; align-items:flex-start;
  font-size:12.5px; line-height:1.55; z-index:5; }
.kpbar .kpi-icon{ flex:0 0 auto; width:18px; height:18px; }
.kpbar .kptxt{ color:var(--ink); }
.kpbar .kptxt b{ font-weight:800; }
.kpbar.info{ background:var(--accent_soft); border-left:5px solid var(--accent); }
.kpbar.warn{ background:var(--warn_soft); border-left:5px solid var(--warn); }
.kpbar.danger{ background:var(--danger_soft); border-left:5px solid var(--danger); }
.kpbar.ok{ background:var(--ok_soft); border-left:5px solid var(--ok); }

/* ---- matrix / quickref / flow ---- */
.mxwrap{ position:absolute; top:150px; left:30px; right:30px; z-index:3; }
table.mx{ width:100%; border-collapse:separate; border-spacing:0;
  border:1px solid var(--line); border-radius:var(--radius); overflow:hidden;
  background:var(--surface); }
table.mx th{ background:var(--primary); color:var(--on_primary); font-size:12.5px;
  font-weight:800; padding:11px 12px; text-align:left; }
table.mx td{ font-size:12px; color:var(--ink2); padding:10px 12px;
  border-top:1px solid var(--line); vertical-align:top; line-height:1.5; }
table.mx tr:nth-child(even) td{ background:var(--bg2); }
table.mx td.rowhead{ font-weight:800; color:var(--heading); }
/* pin the first column: left to itself the browser collapsed it to ~42px and a
   short row label then wrapped to six lines, overflowing the canvas */
table.mx th:first-child, table.mx td:first-child{ width:16%; }
table.mx th:not(:first-child), table.mx td:not(:first-child){ width:auto; }

.qrwrap{ position:absolute; top:152px; left:30px; right:30px; z-index:3;
  display:grid; gap:12px; }
.qrcard{ background:var(--surface); border:1px solid var(--line);
  border-left:4px solid var(--accent); border-radius:var(--radius); padding:12px 14px; }
.qrcard .qt{ font-size:13px; font-weight:800; color:var(--heading); margin-bottom:5px; }
.qrcard .qb{ font-size:12px; color:var(--ink2); line-height:1.5; }

.flowwrap{ position:absolute; top:156px; left:30px; right:30px; height:400px; z-index:3; }
.flowrow{ display:flex; align-items:center; gap:10px; margin-bottom:12px; }
.flowbox{ background:var(--surface); border:1.5px solid var(--accent);
  border-radius:10px; padding:9px 13px; font-size:12.5px; color:var(--heading);
  font-weight:700; }
.flowbox.decision{ border-style:dashed; border-color:var(--warn); }
.flowarrow{ color:var(--muted); font-size:15px; font-weight:800; }
.flowlabel{ font-size:11.5px; color:var(--muted); }

/* ---- print / PDF ---- */
@page{ size:1280px 720px; margin:0; }
@media print{
  html,body{ background:#fff; }
  .slide{ margin:0; break-after:page; page-break-after:always; }
}
"""
