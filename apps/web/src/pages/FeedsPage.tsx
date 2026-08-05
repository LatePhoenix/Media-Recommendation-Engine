import { useEffect, useState } from "react";
import { api, RATING_LABELS, RatingLabel, RecommendationFeed } from "../api";

const FEEDS = [
  { key: "best_next", title: "Best next" },
  { key: "something_different", title: "Something different" },
  { key: "from_your_servers", title: "From your servers" },
  { key: "pass_resurface", title: "Pass resurface" },
  { key: "because_you_loved", title: "Because you loved…" },
];

export default function FeedsPage() {
  const [feedKey, setFeedKey] = useState("best_next");
  const [feed, setFeed] = useState<RecommendationFeed | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [ratingFor, setRatingFor] = useState<string | null>(null);

  async function load(key = feedKey) {
    setBusy(true);
    setError(null);
    try {
      const data = await api.feed(key);
      setFeed(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load feed");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    load(feedKey);
  }, [feedKey]);

  async function act(eventId: string, action: string, ratingLabel?: RatingLabel) {
    setBusy(true);
    try {
      await api.recAction(eventId, action, ratingLabel);
      setRatingFor(null);
      await load(feedKey);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <section className="panel feed-hero">
        <h2>{FEEDS.find((f) => f.key === feedKey)?.title ?? "Recommendations"}</h2>
        <p className="lead">
          Deterministic ranking with stored explanation factors. Pass suppresses temporarily — it is not a dislike.
        </p>
        <div className="tabs">
          {FEEDS.map((f) => (
            <button
              key={f.key}
              type="button"
              className={`tab ${feedKey === f.key ? "active" : ""}`}
              onClick={() => setFeedKey(f.key)}
            >
              {f.title}
            </button>
          ))}
        </div>
        <button className="btn btn-secondary" type="button" disabled={busy} onClick={() => load()}>
          Refresh feed
        </button>
      </section>

      {error && (
        <section className="panel">
          <p className="error">{error}</p>
        </section>
      )}

      <section className="panel">
        {!feed?.items?.length && !busy ? (
          <p className="muted">No candidates yet. Complete onboarding ratings or import a library.</p>
        ) : (
          <div className="grid-cards">
            {feed?.items.map((card) => (
              <article key={card.event_id} className="media-card">
                <div className="meta">
                  <span className="chip">#{card.rank}</span>
                  <span className="chip mono">score {card.score.toFixed(3)}</span>
                  <span className="chip">{card.item.media_type}</span>
                </div>
                <h3>{card.item.title}</h3>
                <div className="meta">
                  {(card.item.genres || []).slice(0, 4).map((g) => (
                    <span className="chip" key={g}>
                      {g}
                    </span>
                  ))}
                </div>
                {card.explanation ? <p className="explanation">{card.explanation}</p> : null}
                <p className="factors">
                  reasons: {JSON.stringify((card.factors as { reasons?: string[] }).reasons || [])}
                </p>
                <div className="row">
                  <button className="btn btn-secondary" type="button" disabled={busy} onClick={() => setRatingFor(card.event_id)}>
                    Rate
                  </button>
                  <button className="btn btn-secondary" type="button" disabled={busy} onClick={() => act(card.event_id, "save")}>
                    Save
                  </button>
                  <button className="btn btn-ghost" type="button" disabled={busy} onClick={() => act(card.event_id, "pass")}>
                    Pass
                  </button>
                  <button className="btn btn-primary" type="button" disabled={busy} onClick={() => act(card.event_id, "consume")}>
                    Consumed
                  </button>
                </div>
                {ratingFor === card.event_id && (
                  <div className="rating-row">
                    {RATING_LABELS.map((label) => (
                      <button
                        key={label}
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => act(card.event_id, "rate", label)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
