# Redis distribution for native Windows packaging

Phase 5.1 decision record: which Redis build we bundle on Windows, licensing notes,
persistence layout, and WinSW management.

Related:

- [`windows-layout.md`](windows-layout.md)
- [`runtime-assumptions.md`](runtime-assumptions.md) (Compose uses `redis:7-alpine` + `requirepass`)
- [`postgres-distribution.md`](postgres-distribution.md)

---

## Decision

| Item | Choice |
|------|--------|
| Engine | **Redis 7.4.x** (aligned with Docker `redis:7-alpine`) |
| Binary source | Community Windows builds: [redis-windows/redis-windows](https://github.com/redis-windows/redis-windows) |
| Pinned version | **7.4.10** |
| Artifact | `Redis-7.4.10-Windows-x64-msys2.zip` (no bundled Windows service — we use WinSW) |
| URL | `https://github.com/redis-windows/redis-windows/releases/download/7.4.10/Redis-7.4.10-Windows-x64-msys2.zip` |
| SHA256 | `3cfa2fa4e85e61d633f5d13971a559bb7961ebc3dd647718bfa8cf9ec7717912` |
| Install layout | `%ProgramFiles%\Media Recommendation Engine\runtime\redis\` |
| Data / logs | `%ProgramData%\MediaRecommendationEngine\redis\data\` and `...\logs\mediarec-redis\` |
| Bind | `127.0.0.1:6379` |
| Auth | `requirepass` (same as Compose / `.env.example`) |
| Service manager | **WinSW** `v2.12.0` (`WinSW-x64.exe`) via `mediarec-redis` |

**Rationale**

- Official Redis does not ship native Windows server binaries; Memurai Developer Edition is not suitable for always-on production (uptime limits / license).
- `redis-windows` publishes versioned zips compiled from upstream Redis source for Windows x64.
- Pin **7.4.10** to stay on the Redis 7 line used in Compose without jumping to Redis 8 yet.
- Prefer the **msys2** zip **without** the project’s own service wrapper so process lifecycle is owned by WinSW (Phase 6 pattern).

**Rejected for now**

| Option | Why not |
|--------|---------|
| Memurai Developer | Not for production packaging; restart limits |
| Memurai Enterprise | Commercial; revisit only if redis-windows proves inadequate |
| tporadowski/redis 5.x | Too old vs Compose Redis 7 clients/features |
| Keep Redis ephemeral (Compose today) | Native install must survive reboot (Phase 5 acceptance) |

---

## Licensing / redistribution

- Upstream Redis licensing applies to the Redis source (see Redis project license for the pinned version).
- [redis-windows/redis-windows](https://github.com/redis-windows/redis-windows) is **unofficial** and not affiliated with Redis Ltd. Retain their notices and our pin/URL/SHA256 in release docs.
- WinSW is MIT-licensed ([winsw/winsw](https://github.com/winsw/winsw)).

Before public redistribution, confirm Redis version license terms for 7.4.x and include NOTICE files in the installer payload.

---

## Persistence and paths

Compose Redis has **no** volume today ([`infra/docker-compose.yml`](../../infra/docker-compose.yml)). Native packaging enables persistence:

| Setting | Native value |
|---------|--------------|
| `dir` | `%ProgramData%\MediaRecommendationEngine\redis\data` (relative `./data` from workdir) |
| `dbfilename` | `dump.rdb` |
| `appendonly` | `yes` |
| `appendfilename` | `appendonly.aof` |
| `logfile` | `./redis.log` (resolved under the Redis `dir`; MSYS-safe) |
| `bind` | `127.0.0.1` |
| `protected-mode` | `yes` |
| `requirepass` | from ProgramData `.env` / install secrets |

Config file used at runtime is generated under ProgramData (mutable), not under Program Files:

`%ProgramData%\MediaRecommendationEngine\redis\redis.conf`

Working directory for `redis-server` / WinSW is `%ProgramData%\MediaRecommendationEngine\redis\` so all `dir` / `logfile` paths stay **relative** (MSYS-built `redis-server.exe` mishandles Windows drive-letter paths).

Template checked into the repo: [`installer/redis/redis.conf.template`](../../installer/redis/redis.conf.template).

---

## WinSW service

| Item | Value |
|------|-------|
| Service id | `mediarec-redis` |
| Definition | [`installer/services/mediarec-redis.xml`](../../installer/services/mediarec-redis.xml) |
| Executable | staged `runtime\winsw\mediarec-redis.exe` (copy of WinSW-x64) |
| Arguments | path to ProgramData `redis.conf` |

Acceptance (Phase 5.2): after install + service start, Redis returns after reboot; data and logs live under ProgramData.

Full multi-service dependency ordering lands in Phase 6; this phase ships the Redis service definition and verifies process + persistence without requiring a full installer reboot matrix.

---

## Scripts

| Script | Role |
|--------|------|
| [`scripts/package_redis_windows.ps1`](../../scripts/package_redis_windows.ps1) | Download Redis + WinSW, stage under `dist/native-windows` |
| [`scripts/verify_redis_windows.ps1`](../../scripts/verify_redis_windows.ps1) | Start Redis with ProgramData-style paths; `PING`, persist, confirm files |
| [`scripts/Initialize-MediaRecRedis.ps1`](../../scripts/Initialize-MediaRecRedis.ps1) | Write `redis.conf` into DataRoot; optional service install |

---

## Update strategy

1. Bump tag to the next **7.4.x** (or deliberate major bump) on [redis-windows releases](https://github.com/redis-windows/redis-windows/releases).
2. Re-pin asset name + SHA256 in `package_redis_windows.ps1` and this doc.
3. Re-run `verify_redis_windows.ps1` and an API `/health/ready` smoke against the packaged Redis URL.
4. Bump WinSW only when needed; keep `mediarec-redis.xml` compatible with WinSW 2.x.

---

## Verification

```powershell
.\scripts\package_redis_windows.ps1
.\scripts\verify_redis_windows.ps1
```

Expected:

- `runtime\redis\redis-server.exe` (or equivalent) exists
- `PING` returns `PONG` with requirepass
- `dump.rdb` and/or AOF appear under the verify data directory (outside Program Files payload)
