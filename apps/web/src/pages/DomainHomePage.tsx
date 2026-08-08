import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ItemState, RatingLabel, RecommendationFeed } from "../api";
import { DOMAIN_LABEL } from "../domains";
import { useDomain } from "../useDomain";
import MediaCard from "../components/MediaCard";
import { CardSkeletons, EmptyState } from "../components/Poster";

const FEEDS = [
  { key: "best_next", title: "Best next" },
  { key: "something_different", title: "Something different" },
  { key: "from_your_servers", title: "From your servers" },
  { key: "pass_resurface", title: "Pass resurface" },
  { key: "because_you_loved", title: "Because you loved…" },
];

export default function DomainHomePage() {
  const domain = useDomain();
  const [feedKey, setFeedKey] = useState("best_next");
  const [feed, setFeed] = useState<RecommendationFeed | null>(null);
  const [states, setStates] = useState<Record<string, ItemState>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    async (key: string) => {
      if (!domain) return;
      setBusy(true);
      setError(null);
      try {
        setFeed(await api.domainFeed(domain.slug, key));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load feed");
      } finally {
        setBusy(false);
      }
    },
    [domain],
  );

  useEffect(() => {
    setStates({});
    load(feedKey);
  }, [feedKey, load]);

  if (!domain) return <section className="panel"><p className="error">Unknown domain.</p></section>;

  async function setState(itemId: string, state: ItemState, notes?: string) {
    if (!domain) return;
    setBusy(true);
    try {
      await api.setState(domain.slug, itemId, { state, notes });
      setStates((s) => ({ ...s, [itemId]: state }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save state");
    } finally {
      setBusy(false);
    }
  }

  async function clearState(itemId: string) {
    if (!domain) return;
    setBusy(true);
    try {
      await api.clearState(domain.slug, itemId);
      setStates((s) => {
        const next = { ...s };
        delete next[itemId];
        return next;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not clear state");
    } finally {
      setBusy(false);
    }
  }

  async function act(eventId: string, action: string, ratingLabel?: RatingLabel) {
    setBusy(true);
    try {
      await api.recAction(eventId, action, ratingLabel);
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
        <h2>{DOMAIN_LABEL[domain.mediaType]} · {FEEDS.find((f) => f.key === feedKey)?.title}</h2>
        <p className="lead">
          Deterministic, single-domain ranking. Interested and Shortlist feed the scorer; Pass suppresses
          temporarily. <Link to={`/${domain.slug}/browse`}>Browse</Link> ·{" "}
          <Link to={`/${domain.slug}/saved`}>Saved</Link> · <Link to={`/${domain.slug}/series`}>Series</Link> ·{" "}
          <Link to={`/${domain.slug}/admin`}>Admin</Link>
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
        <button className="btn btn-secondary" type="button" disabled={busy} onClick={() => load(feedKey)}>
          Refresh feed
        </button>
      </section>

      {error && <section className="panel"><p className="error">{error}</p></section>}

      <section className="panel">
        {busy && !feed ? (
          <CardSkeletons />
        ) : !feed?.items?.length ? (
          <EmptyState glyph="✦">No candidates yet. Rate a few titles in onboarding or import a library.</EmptyState>
        ) : (
          <div className="grid-cards">
            {feed?.items.map((card) => (
              <MediaCard
                key={card.event_id}
                item={card.item}
                mediaType={domain.mediaType}
                domainSlug={domain.slug}
                rank={card.rank}
                score={card.score}
                explanation={card.explanation}
                factors={card.factors}
                eventId={card.event_id}
                currentState={states[card.item.id] ?? null}
                busy={busy}
                onSetState={setState}
                onClearState={clearState}
                onAct={act}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
