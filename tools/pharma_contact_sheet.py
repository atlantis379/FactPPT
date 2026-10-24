#!/usr/bin/env python3
"""Contact sheet: new pharma pages + the 3 GOLD pages in one grid (PIL)."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PH = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/sync/template-lib-pharma")
GOLD = Path(sys.argv[2] if len(sys.argv) > 2 else "/workspace/sync/template-lib-gold")
ITEMS = [(GOLD / f"{s}.png", f"GOLD · {s}") for s in ("01-algorithm", "02-abe-matrix", "03-tx-tree")]
ITEMS += [(p, f"PHARMA · {p.stem}") for p in sorted(PH.glob("[01][0-9]*.png"))]
COLS, TW, TH, PAD, LAB = 3, 960, 540, 28, 40
rows = (len(ITEMS) + COLS - 1) // COLS
sheet = Image.new("RGB", (COLS * TW + (COLS + 1) * PAD, rows * (TH + LAB) + (rows + 1) * PAD + 50), "#E4E8ED")
d = ImageDraw.Draw(sheet)
font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 24)
d.text((PAD, 14), f"FactPPTv2 template lib · GOLD (3) + pharma chart-led ({len(ITEMS) - 3}) · 示例数据，教学示意", fill="#0B3A5C", font=font)
for i, (p, label) in enumerate(ITEMS):
    r, c = divmod(i, COLS)
    x = PAD + c * (TW + PAD)
    y = 50 + PAD + r * (TH + LAB + PAD)
    im = Image.open(p).convert("RGB").resize((TW, TH), Image.LANCZOS)
    d.text((x, y), label, fill="#333333", font=font)
    sheet.paste(im, (x, y + LAB))
    d.rectangle([x - 1, y + LAB - 1, x + TW, y + LAB + TH], outline="#9A9A9A")
out = PH / "contact-sheet.png"
sheet.save(out, optimize=True)
print(out, sheet.size)
