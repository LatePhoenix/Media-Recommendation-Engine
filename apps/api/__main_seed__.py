from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
if len(_HERE.parents) > 3 and (_HERE.parents[3] / "packages").is_dir():
    ROOT = _HERE.parents[3]
elif Path("/packages").is_dir():
    ROOT = Path("/")
else:
    ROOT = _HERE.parents[1]
for path in (ROOT / "packages", ROOT / "workers", _HERE.parents[1]):
    s = str(path)
    if s not in sys.path:
        sys.path.insert(0, s)

from app.seed import seed

if __name__ == "__main__":
    seed()
