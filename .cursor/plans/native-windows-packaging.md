\# Native Windows Packaging Plan for Media Recommendation Engine



\## Objective



Replace the current Docker Desktop runtime dependency with a professional native Windows installation flow that:

\- installs and runs the app without Docker

\- bundles all required runtime components

\- produces a single installer `.exe`

\- feels production-grade for non-technical users

\- preserves the current local-first architecture and recommendation behavior



\## Current state



Relevant existing files:

\- `README.md`

\- `installer/MediaRecommendationEngine.iss`

\- `installer/Start-MediaRec.ps1`

\- `installer/Stop-MediaRec.ps1`

\- `installer/setup-env.ps1`

\- `infra/docker-compose.yml`

\- `apps/api/\*\*`

\- `apps/web/\*\*`

\- `workers/\*\*`



Facts from current repo:

\- frontend is React + Vite + TypeScript

\- API is FastAPI + SQLAlchemy + Alembic

\- DB is PostgreSQL 16 + pgvector

\- jobs use Redis + RQ

\- Ollama enrichment is optional

\- current Windows installer deploys the repo and starts Docker-based compose

\- current installer warns if Docker is missing rather than eliminating the dependency



\## Target architecture



Replace Docker runtime responsibilities with native Windows components:



1\. Web UI

\- build static frontend with Vite

\- serve built assets from the native backend, or keep a lightweight local static server only if needed

\- prefer collapsing to a single localhost HTTP service if practical



2\. API

\- run FastAPI under a bundled Python 3.12 runtime

\- install dependencies into an app-local runtime folder

\- run as a Windows service



3\. Jobs

\- run RQ worker / scheduler as one or more Windows services

\- share the same bundled Python runtime as the API



4\. PostgreSQL

\- bundle a portable PostgreSQL 16 distribution

\- initialize cluster during install on first run

\- install pgvector files matching the exact PostgreSQL build

\- run PostgreSQL as a Windows service



5\. Redis

\- bundle a Windows-compatible Redis server binary

\- run as a Windows service



6\. Service orchestration

\- use WinSW for service installation, start, stop, logging, and recovery

\- do not require Docker, WSL, or host Python



7\. Installer

\- keep Inno Setup as the top-level installer

\- package all binaries, scripts, service wrappers, config templates, icons, and built assets into one installer `.exe`



\## Non-goals



\- do not migrate the database away from PostgreSQL

\- do not replace Redis unless it becomes impossible to package cleanly

\- do not redesign the recommendation logic

\- do not add cloud dependencies

\- do not require admin-only operational steps after install beyond normal service installation



\## Phase 1 - discovery and design freeze



\### Task 1.1: inventory runtime assumptions

Review:

\- `apps/api/\*\*`

\- `workers/\*\*`

\- `infra/docker-compose.yml`

\- `infra/entrypoint-api.sh`

\- `infra/entrypoint-recommender-scheduler.sh`

\- `README.md`



Deliverable:

\- document every assumption currently provided by Docker:

&#x20; - env vars

&#x20; - working directories

&#x20; - health checks

&#x20; - startup order

&#x20; - persistent paths

&#x20; - port bindings

&#x20; - container hostnames

&#x20; - data directories



Acceptance:

\- a markdown file in `docs/packaging/runtime-assumptions.md`



\### Task 1.2: choose final Windows runtime layout

Propose and document a final install layout like:



\- `%ProgramFiles%/Media Recommendation Engine/`

&#x20; - app binaries

&#x20; - service wrappers

&#x20; - scripts

&#x20; - web assets

\- `%ProgramData%/MediaRecommendationEngine/`

&#x20; - postgres data

&#x20; - redis data

&#x20; - logs

&#x20; - mutable config

\- `%LocalAppData%` only if a per-user model is intentionally chosen



Acceptance:

\- a markdown file in `docs/packaging/windows-layout.md`



Decision rules:

\- binaries in Program Files

\- mutable state in ProgramData

\- no production writes into install directory after install



\## Phase 2 - remove unnecessary process boundaries



\### Task 2.1: evaluate serving the frontend from FastAPI

Investigate whether the built Vite output can be served directly by FastAPI/Starlette static files.



If feasible:

\- remove the need for a separate web server in native packaging

\- keep dev flow unchanged



If not feasible:

\- keep a separate local static server only for native packaging



Acceptance:

\- architecture decision record in `docs/packaging/adr-serve-web.md`



Preferred outcome:

\- single localhost service for UI + API in production native install



\### Task 2.2: define native process model

Target service model:

\- `mediarec-postgres`

\- `mediarec-redis`

\- `mediarec-api`

\- `mediarec-worker`

\- optional `mediarec-scheduler` if scheduler logic must be independent



Acceptance:

\- service map in `docs/packaging/windows-services.md`



\## Phase 3 - bundle Python runtime



\### Task 3.1: create Python runtime assembly script

Add scripts that:

\- obtain Python 3.12 embedded or equivalent app-local runtime

\- install required packages into an app-local folder

\- verify imports for FastAPI, SQLAlchemy, Alembic, psycopg, RQ, Redis client, and project packages



Suggested files:

\- `scripts/package\_python\_runtime.ps1`

\- `scripts/verify\_python\_runtime.ps1`



Acceptance:

\- running the packaging script creates a reproducible runtime folder

\- verification script passes on a clean Windows machine or CI runner



\### Task 3.2: make app startup independent of developer paths

Remove assumptions that rely on:

\- repo-root cwd

\- editable installs

\- manually set `PYTHONPATH`

\- developer shell activation



Acceptance:

\- packaged API and worker entrypoints run from app-local paths only



Suggested implementation:

\- explicit launcher modules

\- deterministic config loading

\- no hidden dependency on shell state



\## Phase 4 - bundle PostgreSQL and pgvector



\### Task 4.1: choose PostgreSQL distribution source

Select a portable Windows PostgreSQL 16 distribution compatible with redistribution terms.



Deliverable:

\- `docs/packaging/postgres-distribution.md`



\### Task 4.2: build and package pgvector for the exact PostgreSQL version

Create a reproducible build process for pgvector on Windows matching the bundled PostgreSQL version.



Suggested files:

\- `scripts/build\_pgvector\_windows.ps1`

\- `scripts/verify\_pgvector\_windows.ps1`



Acceptance:

\- installer payload contains:

&#x20; - `vector.dll`

&#x20; - `vector.control`

&#x20; - required SQL migration files

\- `CREATE EXTENSION vector;` succeeds on packaged PostgreSQL



\### Task 4.3: initialize database on first install

Create install-time logic to:

\- initialize cluster if missing

\- create database and user if required

\- enable pgvector

\- run Alembic migrations

\- seed app data if needed



Acceptance:

\- fresh machine install reaches healthy API without manual DB steps



\## Phase 5 - bundle Redis



\### Task 5.1: package Redis for Windows

Choose the Windows Redis binary source and document licensing and update strategy.



Deliverable:

\- `docs/packaging/redis-distribution.md`



\### Task 5.2: service wrapper and persistence

Set Redis persistence and logs to ProgramData paths.

Install and manage with WinSW.



Acceptance:

\- Redis survives reboot

\- logs and data are outside Program Files



\## Phase 6 - introduce WinSW service wrappers



\### Task 6.1: create WinSW configs

Add service definitions for each runtime process.



Suggested files:

\- `installer/services/mediarec-postgres.xml`

\- `installer/services/mediarec-redis.xml`

\- `installer/services/mediarec-api.xml`

\- `installer/services/mediarec-worker.xml`



Acceptance:

\- each service can install, start, stop, and uninstall independently

\- logs are captured per service



\### Task 6.2: add failure recovery and dependency ordering

Ensure:

\- API waits for Postgres and Redis readiness

\- worker waits for API dependencies

\- services restart on failure



Acceptance:

\- reboot test succeeds without manual sequencing



\## Phase 7 - refactor installer



\### Task 7.1: evolve `installer/MediaRecommendationEngine.iss`

Refactor the Inno Setup script to:

\- remove Docker dependency checks

\- package runtime payloads instead of raw repo source where appropriate

\- install service wrapper executables and XML

\- write config templates

\- initialize secrets

\- run first-time DB setup

\- start services

\- add shortcuts for open app, stop services, uninstall, diagnostics



Acceptance:

\- installer no longer references Docker at runtime



\### Task 7.2: replace PowerShell-centric user experience

Current behavior depends heavily on PowerShell launchers. Replace this with:

\- Start Menu shortcut to open the app URL

\- optional tray app or control panel for start/stop/status

\- PowerShell retained only for internal maintenance tasks



Acceptance:

\- normal user never needs to see a terminal



\## Phase 8 - professional polish



\### Task 8.1: add upgrade-safe config and data handling

Ensure upgrades:

\- preserve DB and Redis data

\- preserve generated secrets

\- preserve user config

\- do not overwrite mutable files blindly



Acceptance:

\- install v1, use app, install v2 over it, data remains intact



\### Task 8.2: add logging and diagnostics bundle

Create a script to collect:

\- service status

\- recent logs

\- config summary with secrets redacted

\- port status

\- DB readiness check



Suggested files:

\- `installer/Collect-Diagnostics.ps1`



Acceptance:

\- support bundle can be generated from Start Menu shortcut



\### Task 8.3: add version metadata and branding

Polish:

\- app icon consistency

\- installer metadata

\- uninstall display name

\- versioned upgrade path

\- product publisher fields

\- optional code-signing support in release pipeline



Acceptance:

\- installer UX looks like software, not a repo dump



\## Phase 9 - GitHub Actions release pipeline



\### Task 9.1: build frontend artifact

Create workflow steps to:

\- install Node

\- build `apps/web`

\- collect production web assets



\### Task 9.2: assemble Python runtime

Create workflow steps to:

\- install Python 3.12

\- assemble packaged runtime

\- verify imports and app startup



\### Task 9.3: assemble Postgres + pgvector + Redis payload

Create workflow steps to:

\- fetch pinned runtime binaries

\- build or fetch pgvector-compatible files

\- stage them into installer payload folders



\### Task 9.4: compile Inno Setup installer

Use a Windows GitHub Actions runner to compile the `.iss` installer.



\### Task 9.5: publish artifacts

Upload:

\- installer exe

\- checksums

\- optional diagnostics docs

\- optional portable zip for internal testing



Suggested workflow files:

\- `.github/workflows/build-native-windows-installer.yml`



Acceptance:

\- a tagged release produces a downloadable installer artifact automatically



\## Phase 10 - verification matrix



\### Fresh install tests

\- clean Windows VM

\- install via generated `.exe`

\- app opens successfully

\- first-run bootstrap completes

\- API health passes

\- worker runs

\- DB has pgvector enabled



\### Reboot tests

\- reboot machine

\- all required services return automatically

\- app remains reachable



\### Upgrade tests

\- install old version

\- create sample data

\- install new version

\- verify data retention and service continuity



\### Failure tests

\- stop Postgres manually and confirm recovery behavior

\- corrupt config path and confirm actionable error

\- occupied port handling gives a clear message



\### Uninstall tests

\- remove app binaries and service registrations cleanly

\- respect user choice on whether to retain data



Deliverable:

\- `docs/packaging/test-matrix.md`



\## Implementation order



Execute in this order:

1\. runtime assumptions inventory

2\. decide single-service vs split web serving

3\. package Python runtime

4\. package PostgreSQL

5\. build pgvector compatibility process

6\. package Redis

7\. add WinSW services

8\. refactor installer

9\. add CI pipeline

10\. run verification matrix

11\. polish shortcuts, branding, diagnostics, upgrades



\## Code change guidance



General principles:

\- prefer additive changes first, then retire Docker-specific runtime paths once native packaging is proven

\- keep dev workflow intact unless a change clearly improves both dev and prod

\- do not break the existing Docker path until native installer is validated

\- create docs alongside code, not after



\## Required outputs from Cursor



For each phase:

\- code changes

\- docs updates

\- exact files changed

\- verification commands

\- unresolved risks



At the end:

\- open a PR-ready summary with:

&#x20; - architecture decisions

&#x20; - changed files

&#x20; - test evidence

&#x20; - known limitations

