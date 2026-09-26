# -*- coding: utf-8 -*-
"""
Theme-adaptive vector motifs.

Every motif is drawn with currentColor, so a single motif renders in ANY theme's
palette by setting `color` on its container. This is what makes the illustration
layer theme-independent (no per-theme artwork, no AI generation required).

All motifs use a 400x200 (2:1) viewBox with generous margins.
"""


def _w(body):
    return ('<svg class="motif" viewBox="0 0 400 200" preserveAspectRatio="xMidYMid meet" '
            'xmlns="http://www.w3.org/2000/svg" fill="none" stroke="currentColor" '
            'stroke-linecap="round" stroke-linejoin="round">' + body + '</svg>')


# --- trend / activity: turbulent wave settling into a calm line -------------
WAVE = _w('''
<path d="M26 112 c12 -44 21 44 33 0 c12 -44 21 44 33 0 c11 -38 19 38 30 0" stroke-width="5" opacity=".95"/>
<path d="M136 112 c18 -24 30 24 48 0 c16 -20 28 20 46 0" stroke-width="5" opacity=".8"/>
<path d="M244 112 H372" stroke-width="6"/>
<circle cx="372" cy="112" r="7" fill="currentColor" stroke="none"/>
<path d="M26 152 H372" stroke-width="2" opacity=".3"/>
''')

# --- growth / burden: ascending bars ---------------------------------------
BARS = _w('''
<path d="M60 160 H350" stroke-width="2" opacity=".3"/>
<rect x="86" y="112" width="34" height="48" rx="5" fill="currentColor" stroke="none" opacity=".45"/>
<rect x="146" y="84" width="34" height="76" rx="5" fill="currentColor" stroke="none" opacity=".62"/>
<rect x="206" y="56" width="34" height="104" rx="5" fill="currentColor" stroke="none" opacity=".8"/>
<rect x="266" y="26" width="34" height="134" rx="5" fill="currentColor" stroke="none"/>
''')

# --- network / loop: connected nodes in a cycle ----------------------------
NODES = _w('''
<circle cx="200" cy="100" r="62" stroke-width="3" stroke-dasharray="12 10" opacity=".55"/>
<path d="M258 100 l-20 -13 v26 z" fill="currentColor" stroke="none"/>
<circle cx="200" cy="38" r="20" stroke-width="4" fill="none"/>
<circle cx="262" cy="100" r="20" stroke-width="4" fill="none"/>
<circle cx="200" cy="162" r="20" stroke-width="4" fill="none"/>
<circle cx="138" cy="100" r="20" stroke-width="4" fill="none"/>
<circle cx="200" cy="38" r="7" fill="currentColor" stroke="none"/>
<circle cx="262" cy="100" r="7" fill="currentColor" stroke="none"/>
<circle cx="200" cy="162" r="7" fill="currentColor" stroke="none"/>
<circle cx="138" cy="100" r="7" fill="currentColor" stroke="none"/>
''')

# --- target / goal ---------------------------------------------------------
TARGET = _w('''
<circle cx="200" cy="100" r="66" stroke-width="3" opacity=".35"/>
<circle cx="200" cy="100" r="46" stroke-width="3" opacity=".6"/>
<circle cx="200" cy="100" r="26" stroke-width="4" fill="currentColor" fill-opacity=".16"/>
<circle cx="200" cy="100" r="8" fill="currentColor" stroke="none"/>
<path d="M200 20 v16 M200 164 v16 M120 100 h16 M264 100 h16" stroke-width="4" opacity=".7"/>
''')

# --- shield / protection ---------------------------------------------------
SHIELD = _w('''
<path d="M200 24 l58 21 v46 c0 34 -26 58 -58 69 -32 -11 -58 -35 -58 -69 V45 z"
      stroke-width="5" fill="currentColor" fill-opacity=".08"/>
<path d="M178 100 l16 17 30 -35" stroke-width="7"/>
''')

# --- globe / global --------------------------------------------------------
GLOBE = _w('''
<ellipse cx="200" cy="100" rx="126" ry="86" stroke-width="5"/>
<path d="M74 100 H326 M200 14 V186" stroke-width="3" opacity=".5"/>
<path d="M110 46 c34 26 34 82 0 108 M290 46 c-34 26 -34 82 0 108" stroke-width="3" opacity=".5"/>
<ellipse cx="152" cy="76" rx="40" ry="26" fill="currentColor" stroke="none" opacity=".22"/>
<ellipse cx="248" cy="128" rx="46" ry="28" fill="currentColor" stroke="none" opacity=".16"/>
''')

# --- layers / architecture -------------------------------------------------
LAYERS = _w('''
<path d="M200 32 L312 76 L200 120 L88 76 Z" stroke-width="4" fill="currentColor" fill-opacity=".14"/>
<path d="M88 106 L200 150 L312 106" stroke-width="4" opacity=".8"/>
<path d="M88 136 L200 180 L312 136" stroke-width="4" opacity=".5"/>
''')

# --- flow / process chain --------------------------------------------------
FLOW = _w('''
<rect x="30" y="76" width="66" height="48" rx="8" stroke-width="4" fill="currentColor" fill-opacity=".10"/>
<rect x="132" y="76" width="66" height="48" rx="8" stroke-width="4" fill="currentColor" fill-opacity=".10"/>
<rect x="234" y="76" width="66" height="48" rx="8" stroke-width="4" fill="currentColor" fill-opacity=".10"/>
<path d="M96 100 h30 M198 100 h30" stroke-width="4"/>
<path d="M120 100 l-11 -7 v14 z M222 100 l-11 -7 v14 z" fill="currentColor" stroke="none"/>
<path d="M300 100 h56" stroke-width="4" opacity=".6"/>
<path d="M350 100 l-11 -7 v14 z" fill="currentColor" stroke="none" opacity=".6"/>
''')

# --- gauge / measurement ---------------------------------------------------
GAUGE = _w('''
<path d="M92 148 a108 108 0 0 1 216 0" stroke-width="12" opacity=".25"/>
<path d="M92 148 a108 108 0 0 1 74 -103" stroke-width="12"/>
<path d="M200 148 L246 82" stroke-width="6"/>
<circle cx="200" cy="148" r="10" fill="currentColor" stroke="none"/>
<path d="M92 148 h16 M308 148 h-16 M200 40 v14" stroke-width="4" opacity=".6"/>
''')

# --- grid / matrix ---------------------------------------------------------
GRID = _w('''
<rect x="96" y="40" width="208" height="120" rx="8" stroke-width="4"/>
<path d="M148 40 V160 M200 40 V160 M252 40 V160 M96 80 H304 M96 120 H304" stroke-width="2.5" opacity=".45"/>
<rect x="148" y="80" width="52" height="40" fill="currentColor" stroke="none" opacity=".55"/>
<rect x="252" y="120" width="52" height="40" fill="currentColor" stroke="none" opacity=".35"/>
''')

# --- pulse / vital ---------------------------------------------------------
PULSE = _w('''
<path d="M30 108 H104 l20 -40 28 76 24 -52 18 26 h30" stroke-width="5"/>
<path d="M244 108 H372" stroke-width="5" opacity=".35"/>
<circle cx="276" cy="108" r="6" fill="currentColor" stroke="none" opacity=".5"/>
''')

# --- scale / balance -------------------------------------------------------
SCALE = _w('''
<path d="M200 36 V150" stroke-width="5"/>
<path d="M136 62 H264" stroke-width="5"/>
<path d="M136 62 l-34 52 h68 z" stroke-width="4" fill="currentColor" fill-opacity=".12"/>
<path d="M264 62 l-34 52 h68 z" stroke-width="4" fill="currentColor" fill-opacity=".12"/>
<path d="M158 150 h84" stroke-width="6"/>
''')

# --- check / verified ------------------------------------------------------
CHECK = _w('''
<circle cx="200" cy="100" r="62" stroke-width="5"/>
<path d="M168 100 l22 24 44 -50" stroke-width="9"/>
''')

# --- doc / report ----------------------------------------------------------
DOC = _w('''
<path d="M132 30 h96 l44 44 v96 a8 8 0 0 1 -8 8 H132 a8 8 0 0 1 -8 -8 V38 a8 8 0 0 1 8 -8 z"
      stroke-width="5" fill="currentColor" fill-opacity=".07"/>
<path d="M228 30 v44 h44" stroke-width="4"/>
<path d="M150 104 h100 M150 128 h100 M150 152 h64" stroke-width="4" opacity=".55"/>
''')

MOTIFS = {
    "wave": WAVE, "bars": BARS, "nodes": NODES, "target": TARGET, "shield": SHIELD,
    "globe": GLOBE, "layers": LAYERS, "flow": FLOW, "gauge": GAUGE, "grid": GRID,
    "pulse": PULSE, "scale": SCALE, "check": CHECK, "doc": DOC,
}

# rotate through these when a slide supplies no motif, so pages still look designed
ROTATION = ["wave", "layers", "nodes", "target", "flow", "bars", "grid", "check"]


def get(name, fallback="wave"):
    return MOTIFS.get((name or "").strip().lower(), MOTIFS[fallback])


def auto(i):
    return MOTIFS[ROTATION[i % len(ROTATION)]]
