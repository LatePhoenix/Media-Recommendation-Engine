# PostgreSQL distribution for native Windows packaging

Phase 4.1 decision record: which PostgreSQL 16 build we bundle, licensing notes,
and how pgvector is obtained for the **exact** major version.

Related:

- [`windows-layout.md`](windows-layout.md)
- [`runtime-assumptions.md`](runtime-assumptions.md) (Docker uses `pgvector/pgvector:pg16`)
- [`python-runtime.md`](python-runtime.md)

---

## Decision

| Item | Choice |
|------|--------|
| Engine | **PostgreSQL 16** (matches Docker `pgvector/pgvector:pg16`) |
| Binary source | **EDB Windows x64 binaries zip** (same bits as the EDB installer, without StackBuilder UI) |
| Pinned version | **16.14-1** |
| Download URL | `https://get.enterprisedb.com/postgresql/postgresql-16.14-1-windows-x64-binaries.zip` |
| Install layout | `%ProgramFiles%\Media Recommendation Engine\runtime\postgres\` (staged as `dist/native-windows/runtime/postgres`) |
| Data directory | `%ProgramData%\MediaRecommendationEngine\postgres\data\` |
| Listen | `127.0.0.1` only (local-first) |

**Rationale**

- Official PostgreSQL Windows binaries are published by EDB for expert/redistribution-style bundling ([PostgreSQL Windows downloads](https://www.postgresql.org/download/windows/) note zip archives for embedding).
- Portable enough to extract under Program Files without running the GUI installer.
- Keeps major version aligned with the current Docker image and app expectations (JSONB, UUID, pgvector).

**Rejected for now**

| Option | Why not |
|--------|---------|
| Require host-installed PostgreSQL | Breaks “no Docker / no host DB” installer goal |
| Migrate off PostgreSQL | Explicit non-goal in the packaging plan |
| Unofficial “PostgreSQL Portable” SourceForge packs | Weaker provenance vs EDB zip |

---

## Licensing / redistribution

- PostgreSQL itself is licensed under the [PostgreSQL License](https://www.postgresql.org/about/licence/) (permissive).
- EDB binaries are convenience archives of the Windows installer payload. Before public release distribution, confirm current EDB redistribution terms on the download page and retain notices under `LICENSE` / `NOTICE` in the installer payload.
- Do **not** ship pgAdmin/StackBuilder UI components we do not need; packaging scripts strip `doc`, `pgAdmin*`, and `StackBuilder` when present.

---

## pgvector on Windows

Official [pgvector](https://github.com/pgvector/pgvector) releases do **not** publish Windows DLLs. StackBuilder also does not ship pgvector.

Pinned approach for reproducible packaging:

| Item | Value |
|------|-------|
| Extension | pgvector **0.8.6** |
| Target | PostgreSQL **16** Windows x64 |
| Primary artifact | Community Windows build: [andreiramani/pgvector_pgsql_windows](https://github.com/andreiramani/pgvector_pgsql_windows) tag `0.8.6_16` |
| Asset | `vector.v0.8.6-pg16.zip` |
| URL | `https://github.com/andreiramani/pgvector_pgsql_windows/releases/download/0.8.6_16/vector.v0.8.6-pg16.zip` |
| SHA256 | `faeaecb100488397ce5d38424b8c931be0f29e1668be7d4e75c26fe2eb056522` |
| Install paths | `lib\vector.dll`, `share\extension\vector.control`, `share\extension\vector*.sql` |

Scripts:

- [`scripts/build_pgvector_windows.ps1`](../../scripts/build_pgvector_windows.ps1) — default: fetch + verify SHA256 + install into staged Postgres; optional `-FromSource` using VS + `Makefile.win` against the staged `PGROOT`.
- [`scripts/verify_pgvector_windows.ps1`](../../scripts/verify_pgvector_windows.ps1) — temp cluster + `CREATE EXTENSION vector`.

**Risk:** the default path trusts a third-party Windows build. Mitigations: pin URL + SHA256, document source, prefer `-FromSource` in CI once Visual Studio Build Tools are available on the Windows runner.

Required core extensions (same as [`infra/init-db.sql`](../../infra/init-db.sql)):

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

`uuid-ossp` ships with EDB PostgreSQL; `vector` comes from the pgvector payload above.

---

## Scripts (Phase 4)

| Script | Role |
|--------|------|
| [`scripts/package_postgres_windows.ps1`](../../scripts/package_postgres_windows.ps1) | Download EDB zip, stage `runtime/postgres`, invoke pgvector install |
| [`scripts/build_pgvector_windows.ps1`](../../scripts/build_pgvector_windows.ps1) | Fetch pinned Windows pgvector (or build from source) into a Postgres root |
| [`scripts/verify_pgvector_windows.ps1`](../../scripts/verify_pgvector_windows.ps1) | Init ephemeral cluster; prove `CREATE EXTENSION vector` |
| [`scripts/Initialize-MediaRecDatabase.ps1`](../../scripts/Initialize-MediaRecDatabase.ps1) | First-install: initdb, role/db, extensions, Alembic, seed |

---

## Update strategy

1. Bump `PostgresEdBVersion` (e.g. `16.14-1` → next 16.x) in `package_postgres_windows.ps1` when EDB publishes a newer 16.x zip.
2. Re-pin pgvector asset to a release built for **PostgreSQL 16** (tag suffix `_16`); recompute SHA256.
3. Re-run `verify_pgvector_windows.ps1` and a migrate/seed smoke test before cutting an installer.

Do **not** jump major versions (16 → 17) without an explicit migration plan; the Docker stack and this native pin stay on 16 until deliberately changed.

---

## Authentication note (Windows)

PostgreSQL on Windows uses TCP for `-h 127.0.0.1` connections. `Initialize-MediaRecDatabase.ps1` configures loopback `trust` in `pg_hba.conf` for `127.0.0.1/32` and `::1/128` because the native install binds only to localhost. Application role passwords are still set for `DATABASE_URL` compatibility with the Python drivers.

---

## Verification

```powershell
.\scripts\package_postgres_windows.ps1
.\scripts\verify_pgvector_windows.ps1
# Optional full bootstrap against a temp ProgramData-style tree:
.\scripts\Initialize-MediaRecDatabase.ps1 -InstallRoot .\dist\native-windows -DataRoot .\dist\native-windows-data -Port 55432
```

Expected:

- `runtime\postgres\bin\postgres.exe` exists
- `runtime\postgres\lib\vector.dll` and `share\extension\vector.control` exist
- verify script prints `CREATE EXTENSION vector` success
- Initialize script leaves a cluster that accepts `DATABASE_URL` with the generated role
