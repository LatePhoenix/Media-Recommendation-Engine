from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

_HERE = Path(__file__).resolve()
API_ROOT = _HERE.parents[1]
# Monorepo checkout: <repo>/apps/api/alembic/env.py → parents[3] is repo root.
# Container image: /app/alembic/env.py → packages live at /packages (see Dockerfile).
if len(_HERE.parents) > 3 and (_HERE.parents[3] / "packages").is_dir():
    ROOT = _HERE.parents[3]
elif Path("/packages").is_dir():
    ROOT = Path("/")
else:
    ROOT = API_ROOT
for path in (ROOT, ROOT / "packages", API_ROOT):
    s = str(path)
    if s not in sys.path:
        sys.path.insert(0, s)

from app.config import get_settings  # noqa: E402
from app.db import Base  # noqa: E402
import app.models  # noqa: E402, F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
