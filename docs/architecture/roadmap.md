# Roadmap (v2 / v3 / ops)

## Stage 5 — Collaborative filtering (v2) ✅ implemented

- Deterministic item–item CF from explicit ratings + implicit consume/finish +
  interest states — co-occurrence cosine, **not** ALS, so ranking stays inspectable
  and authoritative (see `workers/recommender/jobs.py::cooccurrence_scores`)
- Nightly `rebuild_collaborative_edges` populates `similarity_edges` with
  `kind='collaborative'` (note: `collaborative`, not the earlier `collab`)
- `model_configs.weights.collaborative` defaults > 0 per media type
- Layered candidate generation (popularity/trending + collaborative expansion)
- Re-ranking caps: `max_per_series` (franchise), `max_per_creator`
- Offline metrics + control/treatment compare via named `model_configs` (admin API)

## Stage 6 — Ollama enrichment (v3) — partially scaffolded

- Embedding scoring is wired as an optional component: `engine._edge_scores(kind="embedding")`
  reads `similarity_edges kind='embedding'`; weight defaults 0 until edges exist
- TODO: flip `ENRICHMENT_ENABLED=true`; embedding worker (description/tags/series →
  `embeddings` pgvector) + build `kind='embedding'` edges (`generate_embeddings_stub`)
- Explanation prose from structured `factors` (LLM writes copy; factors remain source of truth)
- **Still forbidden:** LLM as ranking authority or negative-intent judge

## Stage 7 — Admin / ops (partially implemented)

- ✅ Per-media model-config inspect/edit + control-vs-treatment metrics compare
  (`/api/admin/{domain}/...`)
- ✅ Recommendation quality metrics: served, save/positive/pass/completion rates,
  precision@k, pass-resurface success, diversity index
- TODO: sync health dashboard (last status per import source)
- TODO: failed import retry + dead-letter visibility
- TODO: cold-start vs mature-user coverage stats

## Non-goals

- Neural rankers before real interaction volume
- Chatbot UX pretending to be a recommender
- Six separate engines per media type
