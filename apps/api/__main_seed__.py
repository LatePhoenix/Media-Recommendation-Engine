from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for path in (ROOT / "packages", ROOT / "workers", Path(__file__).resolve().parents[1]):
    s = str(path)
    if s not in sys.path:
        sys.path.insert(0, s)

from app.seed import seed

if __name__ == "__main__":
    seed()
