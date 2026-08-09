# Native Python runtime packaging (Phase 3)

How to assemble and verify the app-local CPython 3.12 runtime used by the native
Windows installer path. Docker / `scripts/dev.ps1` remain unchanged.

Related:

- [`windows-layout.md`](windows-layout.md) — Program Files payload shape
- [`runtime-assumptions.md`](runtime-assumptions.md) — env / path assumptions
- [`adr-serve-web.md`](adr-serve-web.md) — UI serving (static mount still future)

---

## Scripts

| Script | Purpose |
|--------|---------|
| [`scripts/package_python_runtime.ps1`](../../scripts/package_python_runtime.ps1) | Download embeddable CPython 3.12, install `apps/api/requirements.txt`, stage `app/{api,packages,workers}` |
| [`scripts/verify_python_runtime.ps1`](../../scripts/verify_python_runtime.ps1) | Import FastAPI/SQLAlchemy/Alembic/psycopg/redis/rq + project modules; exercise `python -m app.launch --help` |

Pinned embed URL (default):

`https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip`

---

## Output layout

Default `-OutDir`: `<repo>/dist/native-windows/` (gitignored via `dist/`).

```text
dist/native-windows/
  runtime/python/          # python.exe + Lib/site-packages
  app/api/                 # staged apps/api
  app/packages/            # staged packages (enrichment, …)
  app/workers/             # staged workers
  python-runtime.meta.txt
```

This mirrors `%ProgramFiles%\Media Recommendation Engine\` from `windows-layout.md`.

The embeddable `python312._pth` is rewritten to include:

```text
python312.zip
.
Lib\site-packages
..\..\app\api
..\..\app\packages
..\..\app
import site
```

so `python -m app.launch …` works without host `PYTHONPATH` or a developer venv (embed builds ignore cwd/`PYTHONPATH` when `._pth` is present).

---

## Launchers (no developer shell required)

Packaged / service-friendly entrypoints live in [`apps/api/app/launch.py`](../../apps/api/app/launch.py):

```text
python -m app.launch api
python -m app.launch worker --queues imports
python -m app.launch worker --queues recommender
python -m app.launch migrate
python -m app.launch seed
python -m app.launch scheduler
```

Path bootstrap: [`apps/api/app/paths.py`](../../apps/api/app/paths.py)

Config files (in order, process env always wins):

1. `MEDIAREC_ENV_FILE`
2. `%PROGRAMDATA%\MediaRecommendationEngine\config\.env`
3. cwd `.env`
4. `<api_root>/.env`

Optional env:

| Variable | Purpose |
|----------|---------|
| `MEDIAREC_ROOT` | Install root (`…\Media Recommendation Engine` or `dist\native-windows`) |
| `MEDIAREC_ENV_FILE` | Absolute path to dotenv |
| `MEDIAREC_API_HOST` / `MEDIAREC_API_PORT` | uvicorn bind (defaults `127.0.0.1` / `8000`) |
| `WEB_DIST_DIR` | Future static UI dir (setting present; mount not wired yet) |
| `CF_REBUILD_INTERVAL_SECONDS` | Scheduler interval |
| `MEDIAREC_SCHEDULER_WARMUP_SECONDS` | Scheduler initial sleep (default 30) |

---

## Verification

```powershell
# From repo root (network required on first package run)
.\scripts\package_python_runtime.ps1
.\scripts\verify_python_runtime.ps1

# Refresh deps/app trees without re-downloading embed zip extract:
.\scripts\package_python_runtime.ps1 -SkipDownload
.\scripts\verify_python_runtime.ps1
```

Expected:

- `verify_python_runtime.ps1` prints `Verification passed`
- Third-party and project imports succeed without Postgres/Redis
- `python -m app.launch --help` lists subcommands

Unit tests (developer venv, from `apps/api`):

```powershell
$env:API_SECRET_KEY = "test-secret-key-that-is-definitely-long-enough-1234567890"
python -m pytest app/tests/test_paths.py app/tests/test_security.py -q
```

---

## WinSW preview (later phase)

Example service command (not installed yet):

```text
<executable>%BASE%\..\runtime\python\python.exe</executable>
<arguments>-m app.launch api</arguments>
<workingdirectory>%BASE%\..\app\api</workingdirectory>
```

Set `MEDIAREC_ROOT` and `MEDIAREC_ENV_FILE` in the service environment so cwd does not matter for secrets.

---

## Unresolved risks

| Risk | Notes |
|------|-------|
| Embed + pip on locked-down networks | Cache under `dist/cache/`; pin URLs; CI must allow python.org + PyPI |
| Native deps / wheels | `psycopg[binary]` and `uvicorn[standard]` need win_amd64 wheels for 3.12 |
| `app/__init__.py` eager imports | Still requires `API_SECRET_KEY` in the environment before importing `app.*`; launchers and WinSW must set secrets first |
| Redis password mismatch | App default Redis URL has no password; production `.env` must include `requirepass` credentials |
