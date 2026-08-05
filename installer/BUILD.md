# Building the Windows installer

The installer is defined for [Inno Setup 7](https://jrsoftware.org/isdl.php)
(it also compiles under Inno Setup 6).
It packages the Docker Compose stack into a single `Setup.exe` that the end user
double-clicks; on the target machine only **Docker Desktop** is required at runtime.

## Prerequisites

- Inno Setup 7 (the `ISCC` compiler). Install from https://jrsoftware.org/isdl.php.

## Build

From the **repo root** (this machine's IS7 install lives under the user profile):

```powershell
& "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe" installer\MediaRecommendationEngine.iss
```

If `ISCC` is on your PATH, simply:

```powershell
ISCC installer\MediaRecommendationEngine.iss
```

The compiled installer is written to `installer\output\MediaRecommendationEngine-Setup.exe`.

## What the installer does

1. Checks that Docker is present (warns, does not block).
2. Copies the app into `C:\Program Files\Media Recommendation Engine`
   (excludes `.git`, `.venv`, `node_modules`, local `.env`, `pgdata`, etc.).
3. Runs `setup-env.ps1` to generate a strong `API_SECRET_KEY` and
   `CREDENTIALS_FERNET_KEY` so the API will boot.
4. Adds Start / Stop shortcuts (Start Menu, optional Desktop) using the app icon.
5. Optionally launches the stack, which runs `docker compose up -d --build`
   against the base compose file (image contents only, no source bind mounts)
   and opens http://localhost:5173.

Uninstalling stops the containers and removes the app files. The Postgres data
volume is left intact; remove it manually with
`docker volume rm infra_pgdata` if desired.
