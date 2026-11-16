# Author: Pradeep Sahoo
"""Run the Engineering Command Centre from a checkout, with nothing installed.

    python ecc.py use-cases
    python ecc.py incident replay
    python ecc.py architecture run --requirement-doc <document.md>

Puts core/src and every use-cases/*/src on the import path, then runs `ecc`.
After `pip install -e core -e use-cases/<name> ...`, the `ecc` command does the same.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "core" / "src")] + sorted(str(p) for p in (ROOT / "use-cases").glob("*/src"))

from ecc_core.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
