import { useEffect, useState } from "react";
import { api, Item, MediaType, OnboardingStatus, RATING_LABELS, RatingLabel } from "../api";

const MEDIA_OPTIONS: MediaType[] = ["movie", "tv", "audiobook", "comic", "book"];

export default function OnboardingPage({ onComplete }: { onComplete: () => Promise<void> }) {
  const [mediaType, setMediaType] = useState<MediaType>("movie");
  const [items, setItems] = useState<Item[]>([]);
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [rated, setRated] = useState<Record<string, RatingLabel>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function refresh() {
    const [anchors, st] = await Promise.all([api.anchors(mediaType), api.onboardingStatus()]);
    setItems(anchors);
    setStatus(st);
  }

  useEffect(() => {
    refresh().catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, [mediaType]);

  async function submitRatings() {
    const entries = Object.entries(rated);
    if (!entries.length) return;
    setBusy(true);
    setError(null);
    try {
      await api.rateBatch(
        entries.map(([item_id, rating_label]) => ({
          item_id,
          interaction_type: "rate",
          rating_label,
          context: "onboarding",
        })),
      );
      setRated({});
      setMsg(`Saved ${entries.length} ratings`);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  const count = status?.ratings_by_media_type?.[mediaType] ?? 0;
  const min = status?.min_ratings ?? 10;

  return (
    <div>
      <section className="panel feed-hero">
        <h2>Calibrate your taste</h2>
        <p className="lead">
          Rate popular anchors on a 5-point scale. Pass is not used here — these ratings seed content-based ranking.
        </p>
        <div className="tabs">
          {MEDIA_OPTIONS.map((mt) => (
            <button
              key={mt}
              type="button"
              className={`tab ${mediaType === mt ? "active" : ""}`}
              onClick={() => setMediaType(mt)}
            >
              {mt}
            </button>
          ))}
        </div>
        <p className="mono muted">
          {mediaType}: {count}/{min} ratings
          {status?.ready_media_types?.length
            ? ` · ready: ${status.ready_media_types.join(", ")}`
            : ""}
        </p>
      </section>

      <section className="panel">
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
          <h2 style={{ margin: 0 }}>Anchor titles</h2>
          <div className="row">
            <button className="btn btn-secondary" type="button" disabled={busy || !Object.keys(rated).length} onClick={submitRatings}>
              Save ratings ({Object.keys(rated).length})
            </button>
            <button
              className="btn btn-primary"
              type="button"
              disabled={busy || !(status && (status.ready_media_types.length > 0 || count >= min))}
              onClick={() => onComplete()}
            >
              Finish onboarding
            </button>
          </div>
        </div>
        {error && <p className="error">{error}</p>}
        {msg && <p className="success">{msg}</p>}
        <div className="grid-cards">
          {items.map((item) => (
            <article key={item.id} className="media-card">
              <h3>{item.title}</h3>
              <div className="meta">
                <span className="chip">{item.media_type}</span>
                {item.release_year ? <span className="chip">{item.release_year}</span> : null}
                {(item.genres || []).slice(0, 3).map((g) => (
                  <span className="chip" key={g}>
                    {g}
                  </span>
                ))}
              </div>
              <div className="rating-row">
                {RATING_LABELS.map((label) => (
                  <button
                    key={label}
                    type="button"
                    className={`btn ${rated[item.id] === label ? "btn-primary" : "btn-secondary"}`}
                    onClick={() => setRated((r) => ({ ...r, [item.id]: label }))}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
