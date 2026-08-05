# Entity Relationship Diagram

## Diagram

```mermaid
erDiagram
  User ||--o{ UserInteraction : has
  User ||--o{ ImportSource : configures
  User ||--o{ RecommendationList : owns
  User ||--o{ RecommendationEvent : receives
  Item ||--o{ ItemExternalRef : mapped_by
  Item ||--o{ UserInteraction : receives
  Item ||--o{ RecommendationEvent : appears_in
  Item ||--o{ SimilarityEdge : similar_to
  ImportSource ||--o{ ImportJob : runs
  RecommendationList ||--o{ RecommendationEvent : contains
  User {
    uuid id PK
    string email
    string username
    jsonb enabled_media_types
    jsonb preferences
    bool onboarding_complete
  }
  Item {
    uuid id PK
    enum media_type
    string title
    string series
    jsonb genres
    jsonb tags
    jsonb creators
    int release_year
    float popularity
    bool is_anchor
    jsonb extensions
  }
  ItemExternalRef {
    uuid id PK
    uuid item_id FK
    string source
    string external_id
  }
  UserInteraction {
    uuid id PK
    uuid user_id FK
    uuid item_id FK
    enum interaction_type
    float value
    enum source
    float confidence
    enum context
    timestamptz timestamp
  }
  RecommendationList {
    uuid id PK
    uuid user_id FK
    string feed_key
    string title
  }
  RecommendationEvent {
    uuid id PK
    uuid user_id FK
    uuid item_id FK
    string feed_key
    float score
    int rank
    jsonb factors
    string explanation
    string action_taken
  }
  ImportSource {
    uuid id PK
    uuid user_id FK
    string source
    string base_url
    text credentials_encrypted
  }
  ImportJob {
    uuid id PK
    uuid import_source_id FK
    enum status
    jsonb stats
    text error
  }
  EmbeddingVector {
    uuid id PK
    string entity_type
    uuid entity_id
    string model
    vector embedding
  }
  SimilarityEdge {
    uuid id PK
    uuid item_a_id FK
    uuid item_b_id FK
    string kind
    float score
  }
  ModelConfig {
    uuid id PK
    enum media_type
    string name
    jsonb weights
    bool active
  }
```

## Notes

- `media_type`: `movie | tv | book | audiobook | comic | game`
- `interaction_type`: `rate | pass | save | consume | finish | dismiss`
- `embeddings.embedding` is `vector(768)` for `nomic-embed-text` (Stage 6)
- `recommendation_events.factors` always stores structured score components and `reasons[]`
- Dedup path: `item_external_refs(source, external_id)` unique, then title/year/media_type fuzzy match
