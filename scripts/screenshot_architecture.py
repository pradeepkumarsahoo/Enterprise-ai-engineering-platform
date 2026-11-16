# Author: Pradeep Sahoo
"""Regenerate the README screenshot of use case 3 from a real run.

Runs `ecc architecture run --requirement-doc` on the sample requirement document,
opens the generated proposal page in a headless Chromium browser (Edge or
Chrome) and saves a screenshot of the top of the page: the extracted
requirement on the left and the container diagram on the right.

    python scripts/screenshot_architecture.py

Needs Edge or Chrome installed, and network access for the pinned Mermaid
renderer. Set BROWSER to a browser executable to override detection.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "stakeholder" / "screenshots" / "18-architecture-from-document.png"
DOC = REPO / "use-cases" / "architecture-adlc" / "data" / "synthetic" / "requirement-document.md"
CONFIG = REPO / "config" / "product.toml"
SIZE = (1440, 1010)

CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


def find_browser() -> str:
    if os.environ.get("BROWSER"):
        return os.environ["BROWSER"]
    for c in CANDIDATES:
        if Path(c).exists():
            return c
    for name in ("msedge", "google-chrome", "chromium", "chromium-browser", "chrome"):
        if shutil.which(name):
            return shutil.which(name)
    sys.exit("No Edge or Chrome found; set BROWSER to a Chromium-based browser executable.")


def main() -> None:
    sys.path[:0] = [str(REPO / "core" / "src")] + sorted(str(p) for p in (REPO / "use-cases").glob("*/src"))
    from ecc_core.cli import main as cli

    work = Path(tempfile.mkdtemp(prefix="arch-shot-"))
    if cli(["--config", str(CONFIG), "architecture", "--workdir", str(work), "run", "--requirement-doc", str(DOC)]) != 0:
        sys.exit("architecture run failed")
    page = work / "proposal" / "REQ-LOY-001.html"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([find_browser(), "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-color-profile=srgb", f"--window-size={SIZE[0]},{SIZE[1]}",
                    "--virtual-time-budget=15000", f"--screenshot={OUT}", page.as_uri()],
                   check=True, capture_output=True)
    print(f"Screenshot: {OUT}")


if __name__ == "__main__":
    main()
