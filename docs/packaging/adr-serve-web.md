# ADR: Serve the web UI from FastAPI (native packaging)

- **Status:** Accepted
- **Date:** 2026-08-08
- **Context:** Phase 2.1 of [`.cursor/plans/native-windows-packaging.md`](../../.cursor/plans/native-windows-packaging.md)
- **Related:** [`runtime-assumptions.md`](runtime-assumptions.md), [`windows-layout.md`](windows-layout.md)

---

## Context

Today production Compose serves the Vite build with **nginx** on host port `5173`, while the API runs separately on `8000`:

- Build: [`infra/Dockerfile.web`](../../infra/Dockerfile.web)
- SPA config: [`infra/nginx-web.conf`](../../infra/nginx-web.conf) (`try_files` → `/index.html`)
- FastAPI ([`apps/api/app/main.py`](../../apps/api/app/main.py)) has **no** `StaticFiles` mount and no SPA fallback
- The browser calls the API via bake-time `VITE_API_BASE_URL` defaulting to `http://localhost:8000` ([`apps/web/src/api.ts`](../../apps/web/src/api.ts), [`Poster.tsx`](../../apps/web/src/components/Poster.tsx))
- Nginx does **not** reverse-proxy `/api` — it is static-only

Native packaging wants fewer Windows services and a production-grade single localhost experience.

---

## Decision

**Production native Windows packaging will serve the built Vite `dist` from FastAPI/Starlette on the API port (`8000`), with an SPA fallback for non-API routes.**

Do **not** ship a separate local static server (nginx/caddy/`http.server`) for the native installer unless a later blocker proves FastAPI static serving insufficient.

Docker and local Vite HMR remain unchanged for now:

- Compose `web` service + nginx path stays for Docker installs/dev
- Dev overlay continues to use Vite on `5173`

---

## Rationale (tied to this codebase)

1. **Already a two-origin browser model.** The UI does not go through nginx to reach the API; it uses an absolute API base URL. Collapsing UI onto `:8000` with a relative/empty `VITE_API_BASE_URL` for native builds removes a second HTTP process without fighting an existing reverse-proxy design (there isn’t one).

2. **Additive API change.** Static mounting can be gated (e.g. only when `WEB_DIST_DIR` is set / points at a real directory). Docker can keep nginx and leave the mount disabled.

3. **Fewer WinSW services and ports.** One less service and one less port-conflict class versus “API + static server.” Matches the plan preference for a single localhost HTTP service.

4. **Auth model fits same-origin.** API auth is Bearer-token based with CORS `allow_credentials=False` ([`apps/api/app/main.py`](../../apps/api/app/main.py)). Same-origin UI reduces CORS surface for packaged installs.

5. **Separate static server adds little.** Recreating nginx-on-5173 + API-on-8000 on Windows only preserves the current split without packaging benefit.

---

## Consequences

### Positive

- Single app URL for native users (e.g. `http://127.0.0.1:8000/`)
- One WinSW-managed HTTP process for UI+API
- Simpler firewall/port messaging and Start Menu shortcut

### Implementation status

- FastAPI mounts Vite `dist` when `WEB_DIST_DIR` is set ([`apps/api/app/static_ui.py`](../../apps/api/app/static_ui.py)).
- Native web build uses empty `VITE_API_BASE_URL` ([`scripts/package_web_dist.ps1`](../../scripts/package_web_dist.ps1)).
- WinSW `mediarec-api` sets `WEB_DIST_DIR` to `{install}\app\web`.
- CI builds and ships the UI inside the Setup.exe ([`ci-release.md`](ci-release.md)).

### Developer Compose (unchanged)

- Do not remove [`infra/Dockerfile.web`](../../infra/Dockerfile.web), [`infra/nginx-web.conf`](../../infra/nginx-web.conf), or the compose `web` service — they remain for **developer** workflows.
- Do not require FastAPI static serving for Compose until explicitly migrated.

### Risks

| Risk | Mitigation |
|------|------------|
| SPA catch-all shadows API routes | Register API routes first; only fall back for `GET` HTML navigations / missing files |
| Asset caching / large static load on uvicorn | Acceptable for local single-user; revisit only if profiling shows a problem |
| Relative API base breaks Docker UI on `:5173` | Use build-arg only for native artifact builds; Docker keeps `http://localhost:8000` |

---

## Alternatives considered

| Alternative | Why not (for native) |
|-------------|----------------------|
| Keep separate nginx/static service | Extra binary, service, port; no reverse-proxy benefit in this repo |
| Bundle only Vite preview | Not production-oriented; still a second Node process |
| Reverse-proxy API through a front nginx | Larger packaging surface; contradicts current client which already targets `:8000` |

---

## Verification (when implemented)

1. `npm run build` in `apps/web` with empty/`""` `VITE_API_BASE_URL`.
2. Start API with `WEB_DIST_DIR` pointing at that `dist`.
3. Open `http://127.0.0.1:8000/` → UI loads.
4. `GET http://127.0.0.1:8000/health` still returns JSON.
5. Login / catalog calls succeed same-origin (no CORS failure in browser console).
6. `docker compose -f infra/docker-compose.yml up --build` still serves UI on `http://127.0.0.1:5173` via nginx and API on `:8000`.

**Expected:** native path is one HTTP service; Docker path unchanged.

---

## Decision record

| Field | Value |
|-------|-------|
| Chosen approach | FastAPI serves Vite `dist` for native production |
| Separate static server | Rejected for native packaging |
| Docker nginx | Retained for now |
| Next code touchpoints | `apps/api/app/main.py`, `apps/api/app/config.py`, `apps/web/src/api.ts`, `Poster.tsx` (after Phase 1–2 approval / before or alongside Phase 3) |
