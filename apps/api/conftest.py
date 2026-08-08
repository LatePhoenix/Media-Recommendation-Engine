"""Pytest bootstrap — runs before any test module (and before the ``app`` package)
is imported.

``app/__init__.py`` eagerly imports ``app.models -> app.db -> get_settings()``, which
validates ``API_SECRET_KEY`` at import time. pytest imports the ``app`` package before a
test module's own body runs, so the required secrets (and the repo/packages import
paths) must be set here — the earliest hook — rather than per-test. This lets
``python -m pytest app/tests`` work from ``apps/api`` with no manual env setup.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault(
    "API_SECRET_KEY", "test-secret-key-that-is-definitely-long-enough-1234567890"
)
os.environ.setdefault("CREDENTIALS_FERNET_KEY", "vyErqHdYcVkJLcxYI04YW5JVAuRBAu3ad58GfOzMf3k=")

_here = Path(__file__).resolve().parent  # apps/api
_root = _here.parents[1]  # repo root
for _p in (str(_here), str(_root), str(_root / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
