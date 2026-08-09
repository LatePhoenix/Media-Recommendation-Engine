# Native Windows verification matrix (Phase 10)

Manual + scripted checks for the packaged installer (not Docker). Use a clean
Windows 10/11 **x64** VM (or spare machine) with **no** Docker Desktop requirement.

Related: [`installer.md`](installer.md), [`upgrades.md`](upgrades.md),
[`windows-services.md`](windows-services.md), [`ci-release.md`](ci-release.md),
[`adr-serve-web.md`](adr-serve-web.md).

**Artifact under test:** `MediaRecommendationEngine-Setup-{version}.exe`  
(from CI Release or local ISCC — see [`installer/BUILD.md`](../../installer/BUILD.md))

**Install roots:**

| Role | Path |
|------|------|
| Binaries | `%ProgramFiles%\Media Recommendation Engine\` |
| Data | `%ProgramData%\MediaRecommendationEngine\` |
| App URL | `http://127.0.0.1:8000/` |

**Services:** `mediarec-postgres`, `mediarec-redis`, `mediarec-api`, `mediarec-worker`, `mediarec-scheduler`

**Quick post-install smoke (after Setup finishes):**

```powershell
# Elevated optional; most checks are read-only
.\scripts\Verify-NativeInstall.ps1
# Or against an explicit root:
.\scripts\Verify-NativeInstall.ps1 -InstallRoot "C:\Program Files\Media Recommendation Engine"
```

Record results in the checklist tables below (`Pass` / `Fail` / `N/A` + notes).

---

## 0. Preconditions

| # | Check | Expected | Result |
|---|-------|----------|--------|
| 0.1 | Clean OS (or prior uninstall with ProgramData wiped if reusing VM) | No leftover `mediarec-*` services | |
| 0.2 | Ports `5432`, `6379`, `8000` free | `netstat -ano` shows no listeners | |
| 0.3 | Setup.exe SHA-256 matches `.sha256` sidecar | Hash equal | |
| 0.4 | Installer runs elevated | UAC / admin OK; no Docker / WSL / host Python prompts | |

---

## 1. Fresh install

| # | Check | How | Expected | Result |
|---|-------|-----|----------|--------|
| 1.1 | Silent-ish install completes | Run Setup; leave defaults; finish bootstrap | No error dialog; status bar finishes “Configuring services…” | |
| 1.2 | Payload present | Explorer or `Verify-NativeInstall.ps1` | `runtime\python`, `postgres`, `redis`, `winsw`, `app\web\index.html` | |
| 1.3 | Services running | `Get-Service mediarec-*` | All five **Running** within ~2 minutes | |
| 1.4 | Open shortcut | Start Menu → **Media Recommendation Engine** | Browser opens `http://127.0.0.1:8000/`; UI HTML loads (not raw API JSON) | |
| 1.5 | Liveness | `Invoke-WebRequest http://127.0.0.1:8000/health` | `200`, `"status":"ok"` | |
| 1.6 | Readiness | `…/health/ready` | `200`, database + redis `ok` | |
| 1.7 | Same-origin UI | DevTools Network on login/catalog | Requests go to `127.0.0.1:8000` (no separate `:5173`) | |
| 1.8 | pgvector | See §7 SQL snippet | Extension `vector` installed; `SELECT '[]'::vector` works | |
| 1.9 | Worker alive | Logs under `ProgramData\…\logs\mediarec-worker` or RQ after enqueue | No crash loop; process Running | |
| 1.10 | Secrets in ProgramData | `config\.env` exists; **not** under Program Files | Strong `API_SECRET_KEY`; passwords not defaults | |
| 1.11 | `install-state.json` | `config\install-state.json` | `app_version` matches `version.txt`; `upgrade: false` | |
| 1.12 | Diagnostics | Start Menu → **Collect Diagnostics** | Zip under `ProgramData\…\diagnostics`; secrets redacted | |

### Fresh-install PowerShell helpers

```powershell
Get-Service mediarec-* | Format-Table Name, Status, StartType
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/health/ready
Get-Content "$env:ProgramData\MediaRecommendationEngine\config\install-state.json"
```

---

## 2. Reboot

| # | Check | How | Expected | Result |
|---|-------|-----|----------|--------|
| 2.1 | Reboot | Restart Windows | — | |
| 2.2 | Auto-start | After login (wait up to ~3 min for delayed start) | All `mediarec-*` **Running** without opening Setup | |
| 2.3 | App reachable | Open Start Menu shortcut or hit `/health/ready` | UI + ready OK | |
| 2.4 | Data intact | Same user can log in / prior seed still present | No re-init wipe | |

---

## 3. Upgrade

Prereq: two Setup builds (vN and vN+1), same Inno `AppId` ([`upgrades.md`](upgrades.md)).

| # | Check | How | Expected | Result |
|---|-------|-----|----------|--------|
| 3.1 | Baseline | Install vN; register a user; rate ≥1 item **or** note `postgres\data` mtimes + copy of `.env` hashes | Data exists | |
| 3.2 | Capture secrets | `Get-FileHash …\config\.env` | Save hash | |
| 3.3 | Install vN+1 | Run newer Setup over existing install | Bootstrap completes; no “wipe data” | |
| 3.4 | `.env` preserved | Compare hash / spot-check `API_SECRET_KEY`, DB/Redis passwords | Unchanged | |
| 3.5 | DB preserved | Login with same user; ratings present | Intact | |
| 3.6 | Redis preserved | Persistence files under `redis\data` still present | Intact | |
| 3.7 | Version bump | `version.txt` + `install-state.json` | New version; `upgrade: true` or `previous_version` set | |
| 3.8 | Services | `Get-Service mediarec-*` + `/health/ready` | Running / ready | |

---

## 4. Failure / recovery

| # | Check | How | Expected | Result |
|---|-------|-----|----------|--------|
| 4.1 | Stop Postgres | `Stop-Service mediarec-postgres` | `/health/ready` → **503** / degraded | |
| 4.2 | Restart Postgres | `Start-Service mediarec-postgres`; wait | API recovers (WinSW restart + `wait_for_deps`); ready → **200** within ~2 min | |
| 4.3 | Stop Redis | `Stop-Service mediarec-redis` | Ready degraded; worker/scheduler may restart | |
| 4.4 | Restart Redis | `Start-Service mediarec-redis` | Ready recovers | |
| 4.5 | Stop Services shortcut | Start Menu → **Stop Services** | Services stop; **no** PowerShell window flash for user | |
| 4.6 | Corrupt env path | Rename `config\.env` → `.env.bak`; restart `mediarec-api` | Service fails or logs clear missing-env error; restore file → recovers | |
| 4.7 | Occupied port 8000 | Stop API; start `python -m http.server 8000` (or any listener); start `mediarec-api` | Failure visible in `logs\mediarec-api`; stop conflict → API starts | |
| 4.8 | Occupied 5432 / 6379 | (Optional) foreign Postgres/Redis on same ports before install | Bootstrap/service start fails with actionable logs; document workaround (stop foreign service) | |

---

## 5. Uninstall

| # | Check | How | Expected | Result |
|---|-------|-----|----------|--------|
| 5.1 | Uninstall keep data | Apps & features → Uninstall; answer **No** to remove data | Program Files gone; `mediarec-*` services gone; ProgramData **remains** | |
| 5.2 | Reinstall over kept data | Install again | Reuses DB/secrets; user can log in | |
| 5.3 | Uninstall wipe data | Uninstall; answer **Yes** to remove data | ProgramData tree removed | |
| 5.4 | Clean slate | `Get-Service mediarec-*` errors; ports free | No orphans | |

---

## 6. Non-goals / out of scope for this matrix

- Optional developer Compose path (`infra/docker-compose.yml`) — separate smoke
- Code signing / SmartScreen reputation
- Multi-user concurrent clients on one install
- Ollama enrichment (optional; leave disabled)

---

## 7. SQL: confirm pgvector

With services running (use install `psql` + password from ProgramData `.env`):

```powershell
$root = "$env:ProgramFiles\Media Recommendation Engine"
$envFile = "$env:ProgramData\MediaRecommendationEngine\config\.env"
$pgPass = (Select-String -Path $envFile -Pattern '^POSTGRES_PASSWORD=(.+)$').Matches.Groups[1].Value
$env:PGPASSWORD = $pgPass
& "$root\runtime\postgres\bin\psql.exe" -h 127.0.0.1 -p 5432 -U mediarec -d mediarec -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
& "$root\runtime\postgres\bin\psql.exe" -h 127.0.0.1 -p 5432 -U mediarec -d mediarec -c "SELECT '[1,2,3]'::vector;"
```

Expected: one `vector` row; second query returns a vector literal without error.

---

## 8. Sign-off

| Field | Value |
|-------|-------|
| Build / version | |
| Setup SHA-256 | |
| OS build | |
| Tester | |
| Date | |
| Overall | Pass / Fail |
| Blocking issues | |

**Phase 10 acceptance:** every section 1–5 has been executed at least once on a clean VM against a CI-built or locally compiled Setup.exe, with failures filed before shipping a public release.
