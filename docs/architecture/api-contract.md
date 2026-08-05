# API Contract

Base URL: `http://localhost:8000`  
Auth: Bearer JWT from `POST /api/auth/login` (OAuth2 password form).

## Auth

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/api/auth/register` | `{email, username, password}` | `UserOut` |
| POST | `/api/auth/login` | form: `username`, `password` | `{access_token, token_type}` |
| GET | `/api/auth/me` | — | `UserOut` |
| PATCH | `/api/auth/me` | `{enabled_media_types?, preferences?, onboarding_complete?}` | `UserOut` |

## Catalog

| Method | Path | Query | Response |
|--------|------|-------|----------|
| GET | `/api/catalog/items` | `q`, `media_type`, `anchors_only`, `limit`, `offset` | `ItemOut[]` |
| GET | `/api/catalog/items/{id}` | — | `ItemOut` |

## Interactions

| Method | Path | Body | Notes |
|--------|------|------|-------|
| POST | `/api/interactions` | `{item_id, interaction_type, value?, rating_label?, source?, confidence?, context?}` | Pass uses `interaction_type: "pass"` |
| POST | `/api/interactions/batch` | `{interactions: [...]}` | Onboarding batch ratings |

`rating_label` ∈ Loved it / Liked it / Meh / Disliked it / Hated it → numeric weights 2 / 1 / 0 / -1 / -2.

## Onboarding

| Method | Path | Query | Response |
|--------|------|-------|----------|
| GET | `/api/onboarding/anchors` | `media_type`, `limit` | Popular seed `ItemOut[]` |
| GET | `/api/onboarding/status` | — | counts, ready types, complete flag |

## Recommendations

| Method | Path | Response |
|--------|------|----------|
| GET | `/api/recommendations/feeds` | feed key + title list |
| GET | `/api/recommendations/feeds/{feed_key}` | `RecommendationFeedOut` with cards + factors + explanation |
| POST | `/api/recommendations/actions` | `{event_id, action, value?, rating_label?}` |

Feed keys: `best_next`, `something_different`, `from_your_servers`, `pass_resurface`, `because_you_loved`.

Every served card persists a `recommendation_events` row with `factors` JSON.

## Imports

| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/api/imports/sources` | — | sources |
| POST | `/api/imports/sources` | `{source, display_name, base_url?, credentials?, config?}` | source (creds encrypted) |
| POST | `/api/imports/sources/{id}/sync` | — | `ImportJobOut` |
| GET | `/api/imports/jobs` | — | recent jobs |
| POST | `/api/imports/csv` | `{rows: [{title, media_type, year, genres, creators, rating_label}]}` | stats |

## Health

`GET /health` → `{status, enrichment_enabled, version}`

OpenAPI UI: `/docs`
