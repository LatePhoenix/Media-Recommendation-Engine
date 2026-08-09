"""Path-independent process entrypoints for native packaging and local runs.

Usage (from ``apps/api`` or packaged ``app/api``, with deps on ``PYTHONPATH`` / embed):

    python -m app.launch api
    python -m app.launch worker --queues imports
    python -m app.launch worker --queues recommender
    python -m app.launch migrate
    python -m app.launch seed
    python -m app.launch scheduler
"""

from __future__ import annotations

import argparse
import os
import sys
import time


def _bootstrap() -> None:
    from app.paths import ensure_sys_path

    ensure_sys_path()


def wait_for_deps() -> None:
    """Block until Postgres + Redis accept connections (WinSW start races).

    Controlled by ``MEDIAREC_WAIT_DEPS_SECONDS`` (default 0 = skip; services set 120).
    """
    total = int(os.environ.get("MEDIAREC_WAIT_DEPS_SECONDS", "0"))
    if total <= 0:
        return

    from sqlalchemy import create_engine, text

    from app.config import get_settings

    settings = get_settings()
    deadline = time.time() + total
    last_err = ""
    print(f"waiting up to {total}s for database + redis…", flush=True)
    while time.time() < deadline:
        db_ok = False
        redis_ok = False
        try:
            eng = create_engine(settings.database_url, pool_pre_ping=True)
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            eng.dispose()
            db_ok = True
        except Exception as exc:  # noqa: BLE001
            last_err = f"database: {exc}"

        try:
            from redis import Redis

            r = Redis.from_url(
                settings.redis_url, socket_connect_timeout=0.5, socket_timeout=0.5
            )
            r.ping()
            redis_ok = True
        except Exception as exc:  # noqa: BLE001
            last_err = f"redis: {exc}"

        if db_ok and redis_ok:
            print("dependencies ready", flush=True)
            return
        time.sleep(1.0)

    raise SystemExit(f"dependencies not ready after {total}s ({last_err})")


def cmd_api(_args: argparse.Namespace) -> int:
    import uvicorn

    wait_for_deps()
    host = os.environ.get("MEDIAREC_API_HOST", "127.0.0.1")
    port = int(os.environ.get("MEDIAREC_API_PORT", "8000"))
    # Import app after path bootstrap (side-effect: loads settings).
    uvicorn.run("app.main:app", host=host, port=port, log_level="info")
    return 0


def cmd_worker(args: argparse.Namespace) -> int:
    from redis import Redis
    from rq import Queue, Worker

    wait_for_deps()
    from app.config import get_settings

    settings = get_settings()
    conn = Redis.from_url(settings.redis_url)
    names = args.queues or ["imports", "recommender"]
    queues = [Queue(name, connection=conn) for name in names]
    Worker(queues, connection=conn).work(with_scheduler=False)
    return 0


def cmd_migrate(_args: argparse.Namespace) -> int:
    from alembic import command
    from alembic.config import Config

    from app.paths import resolve_api_root

    api_root = resolve_api_root()
    cfg = Config(str(api_root / "alembic.ini"))
    # Ensure script_location resolves relative to api root even if cwd differs.
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    command.upgrade(cfg, "head")
    return 0


def cmd_seed(_args: argparse.Namespace) -> int:
    from app.seed import seed

    seed()
    return 0


def cmd_scheduler(_args: argparse.Namespace) -> int:
    """Windows-friendly replacement for ``infra/entrypoint-recommender-scheduler.sh``."""
    from redis import Redis
    from rq import Queue

    wait_for_deps()
    from app.config import get_settings

    settings = get_settings()
    interval = int(os.environ.get("CF_REBUILD_INTERVAL_SECONDS", "86400"))
    warm = int(os.environ.get("MEDIAREC_SCHEDULER_WARMUP_SECONDS", "30"))
    print(f"recommender-scheduler: interval={interval}s warmup={warm}s", flush=True)
    time.sleep(warm)
    while True:
        print("recommender-scheduler: enqueue nightly_retrain_stub", flush=True)
        conn = Redis.from_url(settings.redis_url)
        Queue("recommender", connection=conn).enqueue(
            "workers.recommender.jobs.nightly_retrain_stub"
        )
        time.sleep(interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="app.launch",
        description="Media Recommendation Engine process launcher (native packaging).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("api", help="Run uvicorn (API; optional static UI later)")

    worker = sub.add_parser("worker", help="Run RQ worker")
    worker.add_argument(
        "--queues",
        nargs="+",
        default=None,
        help="Queue names (default: imports recommender)",
    )

    sub.add_parser("migrate", help="Run alembic upgrade head")
    sub.add_parser("seed", help="Run app seed")
    sub.add_parser("scheduler", help="Enqueue CF rebuilds on an interval")
    return parser


def main(argv: list[str] | None = None) -> int:
    _bootstrap()
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "api": cmd_api,
        "worker": cmd_worker,
        "migrate": cmd_migrate,
        "seed": cmd_seed,
        "scheduler": cmd_scheduler,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
