# Author: Pradeep Sahoo
"""Regenerate the README screenshots of the working code from real runs.

    python scripts/screenshots.py                  # every target
    python scripts/screenshots.py architecture     # use case 3: requirement document -> architecture
    python scripts/screenshots.py change           # use case 4: change risk report for CHG0030601

Each target runs the real command through the product configuration, opens the HTML page it wrote
in a headless Chromium browser (Edge or Chrome) and saves the top of the page. Needs Edge or Chrome;
the architecture page also needs network access for the pinned Mermaid renderer. Set BROWSER to a
browser executable to override detection.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config" / "product.toml"
SHOTS = REPO / "docs" / "stakeholder" / "screenshots"
DOC = REPO / "use-cases" / "architecture-adlc" / "data" / "synthetic" / "requirement-document.md"

# name -> (ecc arguments after --workdir, page relative to the workdir, output file, window size)
TARGETS = {
    "architecture": (["architecture", "--workdir", "{w}", "run", "--requirement-doc", str(DOC)],
                     "proposal/REQ-LOY-001.html", "18-architecture-from-document.png", (1440, 1010)),
    "change": (["change", "--workdir", "{w}", "assess", "CHG0030601"],
               "reports/CHG0030601.html", "19-change-risk-assessment.png", (1440, 1060)),
}

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


def shoot(name: str, cli) -> Path:
    args, page, out, (w, h) = TARGETS[name]
    work = Path(tempfile.mkdtemp(prefix=f"ecc-shot-{name}-"))
    if cli(["--config", str(CONFIG), *[a.replace("{w}", str(work)) for a in args]]) != 0:
        sys.exit(f"{name}: the run failed")
    SHOTS.mkdir(parents=True, exist_ok=True)
    subprocess.run([find_browser(), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-color-profile=srgb",
                    f"--window-size={w},{h}", "--virtual-time-budget=15000", f"--screenshot={SHOTS / out}",
                    (work / page).as_uri()], check=True, capture_output=True)
    return SHOTS / out


def main(argv: list[str]) -> None:
    sys.path[:0] = [str(REPO / "core" / "src")] + sorted(str(p) for p in (REPO / "use-cases").glob("*/src"))
    from ecc_core.cli import main as cli
    names = argv or list(TARGETS)
    unknown = [n for n in names if n not in TARGETS]
    if unknown:
        sys.exit(f"Unknown target(s): {', '.join(unknown)} (known: {', '.join(TARGETS)})")
    for n in names:
        print(f"Screenshot: {shoot(n, cli)}")


if __name__ == "__main__":
    main(sys.argv[1:])
