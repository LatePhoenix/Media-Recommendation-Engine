# Roadmap (v2 / v3 / ops)

## Stage 5 — Collaborative filtering (v2)

- Item–item CF from explicit ratings + implicit consume/finish/save
- Weighted ALS / `implicit` library over sparse matrices
- Nightly RQ job in `workers/recommender/jobs.py` (replace `nightly_retrain_stub`)
- Populate `similarity_edges` with `kind=collab`
- Set `model_configs.weights.collaborative > 0` per media type
- Evaluation: offline precision@k / recall@k dashboard (admin)
- A/B via multiple `model_configs` rows (`name=control|treatment`)

## Stage 6 — Ollama enrichment (v3)

- Flip `ENRICHMENT_ENABLED=true`; use `packages/enrichment.OllamaEnricher`
- Embedding worker: description + tags + series blurbs → `embeddings` (pgvector)
- Semantic ANN candidate generation as additional retrieval channel (`c·embedding`)
- Explanation prose from structured `factors` (LLM writes copy; factors remain source of truth)
- Optional taste-summary generation for profile UI
- **Still forbidden:** LLM as ranking authority or negative-intent judge

## Stage 7 — Admin / ops

- Sync health dashboard (last status per import source)
- Failed import retry + dead-letter visibility
- Model stats: interaction counts, coverage, cold-start vs mature users
- Recommendation quality audit: sample events, action rates, pass resurface outcomes

## Non-goals

- Neural rankers before real interaction volume
- Chatbot UX pretending to be a recommender
- Six separate engines per media type
