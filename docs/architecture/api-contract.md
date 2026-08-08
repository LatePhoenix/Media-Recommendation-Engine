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

## Domains (Phase 1/2)

Per-vertical routes. `{domain}` is a plural slug: `movies`, `tv`, `audiobooks`,
`games`, `books`, `comics`. Books and comics are opt-in — a domain the user has not
enabled returns `403`; an unknown slug returns `404`. Default enabled set:
`movie, tv, audiobook, game`.

Each media type is scored on its own — a movie is never ranked against a book.

| Method | Path | Query / Body | Response |
|--------|------|--------------|----------|
| GET | `/api/{domain}/recommendations/feeds` | — | feed key + title list |
| GET | `/api/{domain}/recommendations/feeds/{feed_key}` | `limit` | `RecommendationFeedOut` (single media type) |
| GET | `/api/{domain}/model-config` | — | active per-media-type ranking `weights` |
| GET | `/api/{domain}/series` | `limit`, `offset` | `SeriesOut[]` (franchise/series list) |
| GET | `/api/{domain}/series/{id}` | — | `SeriesDetailOut` (sequence-ordered items) |
| GET | `/api/{domain}/creators/{id}` | — | `CreatorDetailOut` (items by that creator) |
| GET | `/api/{domain}/catalog/items` | filters (below) | `ItemOut[]` |
| GET | `/api/{domain}/catalog/items/{id}` | — | `ItemDetailOut` (item + resolved `links[]`) |
| GET | `/api/{domain}/items/{id}/links` | — | `ExternalLinkOut[]` (lazily resolved) |
| POST | `/api/{domain}/items/{id}/links/resolve` | — | re-resolve, `ExternalLinkOut[]` |
| PUT | `/api/{domain}/items/{id}/links/{provider}` | `{external_url, external_key?, confidence?}` | manual override (admin) |
| GET | `/api/{domain}/items/{id}/state` | — | `ItemStateOut` or `null` |
| PUT | `/api/{domain}/items/{id}/state` | `{state, notes?, priority?, source?}` | `ItemStateOut` |
| DELETE | `/api/{domain}/items/{id}/state` | — | `204` |
| GET | `/api/{domain}/saved` | `state` (repeatable), `sort`, `limit`, `offset` | `SavedItemOut[]` |
| GET | `/api/{domain}/collections` | — | `CollectionOut[]` |
| POST | `/api/{domain}/collections` | `{name, description?, is_default?}` | `CollectionOut` |
| GET | `/api/{domain}/collections/{id}` | — | `CollectionDetailOut` (with items) |
| POST | `/api/{domain}/collections/{id}/items` | `{item_id, sort_order?}` | `204` |
| DELETE | `/api/{domain}/collections/{id}/items/{item_id}` | — | `204` |

**Interest states** (`state`): `interested`, `shortlisted`, `in_progress`,
`completed`, `passed`, `hidden`. `in_progress` renders per domain as Watching /
Listening / Playing / Reading now. Ranking effect (deterministic, inspectable):
interested/shortlisted reinforce the item's genres/tags/creators and define the
"saved affinity" surface that bumps similar candidates (`saved_related_item`
factor); completed counts as seen; passed suppresses via the pass cooldown; hidden
is excluded from every feed.

**Browse filters** (`/catalog/items`): common — `q`, `genre`, `creator`, `series`,
`language`, `release_year`, `year_min`, `year_max`, `length_min`, `length_max`,
`anchors_only`, `sort` (`popularity|title|release_year|recently_added`), `limit`,
`offset`. Domain extension attributes — `publisher` (comics), `narrator`
(audiobooks), `platform` (games). `state` filters by the current user's saved
state (watched / play status).

**Saved sort** (`/saved`): `recently_added`, `priority`, `release_date`, `score`.

**External links (Phase 3):** `ExternalLinkOut = {provider, label, external_key?, external_url, confidence, resolution_method, verified}`. Providers by media — movies/tv: `imdb, rottentomatoes, metacritic, tmdb`; books/audiobooks: `openlibrary, googlebooks`; comics: `comicvine`; games: `metacritic, igdb`. `resolution_method ∈ api | search | manual | imported`. Verified deep links (`confidence ≥ 0.6`) are built from harvested provider keys (Plex/Trakt guids) or manual overrides; otherwise a `search` link is returned and flagged unverified. Resolution never downgrades a verified link or overwrites a `manual` one.

**Metadata quality (Phase 4):** imports now canonicalize on ingest — the same title
from different sources collapses into one item via normalized-title/alias matching
(`item_aliases`), and denormalized creators/series/tags are resolved into canonical
`creators` / `series` / `canonical_tags` (with `item_creators` / `series_items` /
`item_tags` links). `SeriesDetailOut` powers franchise pages; `POST /api/admin/items/merge`
is the admin dedup tool that repoints all references (including `UserInteraction`) onto a surviving item.

> The media-agnostic `/api/recommendations/feeds/{feed_key}` is **deprecated**; it
> now scopes to the user's first enabled domain. Prefer the per-domain route.

## Admin / ops (Phase 5)

Authenticated; requires `is_admin` (first registered user is admin). `{domain}` is
resolved by slug without the enablement check so ops can inspect every vertical.
Registration can be locked with `REGISTRATION_ENABLED=false` after bootstrap
(single-household / local-first default).

| Method | Path | Query / Body | Response |
|--------|------|--------------|----------|
| GET | `/api/admin/{domain}/model-configs` | — | `AdminModelConfigOut[]` (all named configs) |
| POST | `/api/admin/{domain}/model-configs` | `{name, weights, active}` | upsert a config; activating one deactivates the rest |
| GET | `/api/admin/{domain}/metrics` | `config?`, `k` | offline metrics (below) |
| GET | `/api/admin/{domain}/metrics/compare` | `control=default`, `treatment`, `k` | `{control, treatment}` metric sets |
| POST | `/api/admin/items/merge` | `{primary_id, duplicate_id}` | merge duplicate into primary (repoints interactions + FKs) |

**Ranking (Phase 5):** the deterministic core stays authoritative. Components:
`collaborative` (item-item co-occurrence CF, built nightly by
`rebuild_collaborative_edges` via the `recommender-scheduler` service), `content`, `embedding` (optional, pgvector), `popularity`,
`novelty`, `interest` (saved affinity), `serendipity`, `availability` (on a connected
server), minus `seen`/`recent_pass` penalties. Candidate generation is layered
(popularity/trending + collaborative expansion), and re-ranking caps franchise
(`max_per_series`) and creator (`max_per_creator`) concentration. Each served
`recommendation_events.factors` carries a `structured` payload
(`liked_similar_items`, `shared_tags`, `same_creator`, `community_overlap`,
`novelty_reason`, `saved_related_item`, `candidate_layers`) plus the `config` used.
Serve a treatment with `GET /api/{domain}/recommendations/feeds/{feed_key}?config=<name>`.

**Metrics:** `served`, `save_rate`, `positive_rate`, `pass_rate`, `completion_rate`,
`precision_at_k`, `pass_resurface_success`, `diversity_index` — computed from served
events, groupable by config for A/B comparison.

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
