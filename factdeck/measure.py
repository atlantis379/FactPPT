"""Open the HTML in headless Chrome and read slot boxes plus a screenshot."""

from __future__ import annotations

import html as html_lib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

CHROME = "/usr/bin/google-chrome-stable" if Path("/usr/bin/google-chrome-stable").is_file() else (
    shutil.which("google-chrome") or shutil.which("chromium")
)


def measure_html(
    html: str,
    screenshot: Path | None = None,
    window: tuple[int, int] = (1920, 1080),
    *,
    require_slots: bool = True,
    html_path: Path | None = None,
) -> list[dict]:
    if not CHROME:
        raise RuntimeError("chrome is required to measure slide HTML")
    width, height = window
    with tempfile.TemporaryDirectory(prefix="factdeck-") as directory:
        profile = Path(directory) / "profile"
        if html_path is None:
            src = Path(directory) / "slide.html"
            src.write_text(html, encoding="utf-8")
        else:
            src = html_path
        cmd = [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            f"--user-data-dir={profile}",
            f"--window-size={width},{height}",
            "--virtual-time-budget=2000",
            "--timeout=20000",
            "--dump-dom",
        ]
        if screenshot is not None:
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            cmd.append(f"--screenshot={screenshot}")
        cmd.append(str(src))
        try:
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=40)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("chrome measure timed out") from exc
        dom = proc.stdout
        start = dom.find('<pre id="fd-measure">')
        end = dom.find("</pre>", start)
        if start < 0 or end < 0:
            if not require_slots and screenshot is not None and screenshot.is_file():
                return []
            raise RuntimeError(f"measure tag missing (chrome exit {proc.returncode}): {proc.stderr[-500:]}")
        payload = html_lib.unescape(dom[start + len('<pre id="fd-measure">') : end])
        slots = json.loads(payload)
        if screenshot is not None and not screenshot.is_file():
            raise RuntimeError("chrome did not write the screenshot")
        return slots
