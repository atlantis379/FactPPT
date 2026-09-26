# -*- coding: utf-8 -*-
"""用本机 PowerPoint 把交付 PPTX 导出成逐页 PNG，作为排版复核的实物依据。

为什么必须有这一步：`build_pptx(preview_dir=...)` 里的 PNG 是写出器自带的
光栅化结果，不等于放映效果。文字换行、标点位置、字号观感这些只在真实
PowerPoint 里才算数（真实课件实测两者一致，但这份一致性本身也需要被验证）。

用法：
    python app/validation/render_with_powerpoint.py IN.pptx OUT_DIR [WIDTH HEIGHT]

产出：OUT_DIR/slide-01.png ... slide-NN.png（1280x720 是写入口径尺寸）。
需要 pywin32 + 本机安装 PowerPoint。
"""
from __future__ import annotations

import sys
from pathlib import Path

def render(src: Path, out: Path, width: int = 1280, height: int = 720) -> dict:
    """Export every slide of `src` to `out/slide-NN.png`; returns what was produced."""
    try:
        import win32com.client
    except ModuleNotFoundError as error:
        raise RuntimeError("PowerPoint rendering requires pywin32 and desktop PowerPoint") from error
    src = Path(src).resolve()
    out = Path(out).resolve()
    if not src.exists():
        raise FileNotFoundError(f"missing presentation: {src}")
    out.mkdir(parents=True, exist_ok=True)
    application = win32com.client.Dispatch("PowerPoint.Application")
    try:
        presentation = application.Presentations.Open(str(src), ReadOnly=True, WithWindow=False)
        try:
            for index in range(1, presentation.Slides.Count + 1):
                presentation.Slides(index).Export(str(out / f"slide-{index:02d}.png"), "PNG", width, height)
            count = presentation.Slides.Count
        finally:
            presentation.Close()
    finally:
        application.Quit()
    return {"renderer": "powerpoint", "slides": count, "png_dir": str(out),
            "png": sorted(str(path) for path in out.glob("slide-*.png"))}


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    result = render(Path(sys.argv[1]), Path(sys.argv[2]),
                    int(sys.argv[3]) if len(sys.argv) > 3 else 1280,
                    int(sys.argv[4]) if len(sys.argv) > 4 else 720)
    print("exported slides:", result["slides"], "->", result["png_dir"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
