from __future__ import annotations

from app.paths import ensure_sys_path

ensure_sys_path()

from app.seed import seed

if __name__ == "__main__":
    seed()
