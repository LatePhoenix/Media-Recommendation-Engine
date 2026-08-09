"""Install / monorepo path resolution for native packaging and Docker.

Call :func:`ensure_sys_path` before importing project packages that live outside
``apps/api`` (``workers``, ``enrichment`` under ``packages/``).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _here() -> Path:
    return Path(__file__).resolve()


def resolve_api_root() -> Path:
    """Directory that contains the ``app`` package and ``alembic.ini``."""
    return _here().parents[1]


def resolve_shared_root() -> Path:
    """Directory that contains ``packages/`` and (usually) ``workers/``.

    Layouts:
    - Packaged: ``<root>/app/packages``, ``<root>/app/workers`` (shared root = ``<root>/app``)
    - Monorepo: ``<repo>/packages``, ``<repo>/workers`` (shared root = ``<repo>``)
    - ``MEDIAREC_ROOT``: install root (``…/Media Recommendation Engine``) or monorepo root
    """
    explicit = os.environ.get("MEDIAREC_ROOT", "").strip()
    if explicit:
        root = Path(explicit).resolve()
        packaged = root / "app"
        if (packaged / "packages").is_dir():
            return packaged
        if (root / "packages").is_dir():
            return root
        # Allow pointing MEDIAREC_ROOT directly at the ``app`` payload folder.
        if (root / "packages").is_dir() or (root / "api").is_dir():
            if (root / "packages").is_dir():
                return root

    here = _here()
    # Packaged: <root>/app/api/app/paths.py → parents[2] == <root>/app
    packaged_app = here.parents[2]
    if (packaged_app / "packages").is_dir() and (
        (packaged_app / "workers").is_dir() or (packaged_app / "api").is_dir()
    ):
        return packaged_app

    # Monorepo: <repo>/apps/api/app/paths.py → parents[3] == <repo>
    if len(here.parents) > 3:
        repo = here.parents[3]
        if (repo / "packages").is_dir():
            return repo

    # Container image: /packages mounted at filesystem root (see infra/Dockerfile.api).
    if Path("/packages").is_dir():
        return Path("/")

    return resolve_api_root()


def resolve_install_root() -> Path | None:
    """Program Files-style install root when the packaged layout is present."""
    explicit = os.environ.get("MEDIAREC_ROOT", "").strip()
    if explicit:
        root = Path(explicit).resolve()
        if (root / "app" / "packages").is_dir() or (root / "runtime" / "python").is_dir():
            return root

    shared = resolve_shared_root()
    # shared == <root>/app → install root is parent
    if shared.name == "app" and (shared.parent / "runtime").is_dir():
        return shared.parent
    if (shared / "runtime" / "python").is_dir():
        return shared
    return None


def resolve_env_files() -> tuple[str, ...]:
    """Ordered dotenv paths (later files do not override earlier in pydantic v2 —
    environment variables always win). First existing files are preferred.

    Search order:
    1. ``MEDIAREC_ENV_FILE`` (explicit)
    2. ``%PROGRAMDATA%\\MediaRecommendationEngine\\config\\.env``
    3. ``<install>/`` is not used for secrets (immutable); skip Program Files
    4. cwd ``.env`` (Docker / developer)
    5. ``<api_root>/.env``
    """
    found: list[str] = []

    def _add(path: Path) -> None:
        try:
            resolved = str(path.resolve())
        except OSError:
            return
        if path.is_file() and resolved not in found:
            found.append(resolved)

    explicit = os.environ.get("MEDIAREC_ENV_FILE", "").strip()
    if explicit:
        _add(Path(explicit))

    program_data = os.environ.get("PROGRAMDATA", "").strip()
    if program_data:
        _add(Path(program_data) / "MediaRecommendationEngine" / "config" / ".env")

    _add(Path.cwd() / ".env")
    _add(resolve_api_root() / ".env")

    return tuple(found)


def ensure_sys_path() -> Path:
    """Insert api + shared roots onto ``sys.path``. Returns shared root."""
    api_root = resolve_api_root()
    shared = resolve_shared_root()
    candidates = [
        api_root,
        shared / "packages",
        shared,  # so ``import workers`` works when workers/ lives under shared
    ]
    # Packaged workers live under shared/workers; monorepo same.
    for path in candidates:
        s = str(path)
        if path.is_dir() and s not in sys.path:
            sys.path.insert(0, s)
    return shared
