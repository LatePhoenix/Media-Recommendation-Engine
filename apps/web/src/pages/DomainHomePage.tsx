import { useCallback, useEffect, useState } from "react";
import { api, ItemState, RatingLabel, RecommendationFeed, User } from "../api";
import { DOMAIN_LABEL } from "../domains";
import { useDomain } from "../useDomain";
import MediaCard from "../components/MediaCard";
import DomainSubnav from "../components/DomainSubnav";
import { CardSkeletons, EmptyState } from "../components/Poster";

const FEEDS = [
  { key: "best_next", title: "Best next" },
  { key: "something_different", title: "Something different" },
  { key: "from_your_servers", title: "From your servers" },
  { key: "pass_resurface", title: "Pass resurface" },
  { key: "because_you_loved", title: "Because you loved…" },
];

export default function DomainHomePage({ user }: { user: User }) {
  const domain = useDomain();
  const [feedKey, setFeedKey] = useState("best_next");
  const [feed, setFeed] = useState<RecommendationFeed | null>(null);
  const [states, setStates] = useState<Record<string, ItemState>>({});
  const [busyIds, setBusyIds] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hydrateStates = useCallback(async (slug: string) => {
    try {
      const saved = await api.listSaved(slug, { limit: 200 });
      const map: Record<string, ItemState> = {};
      for (const row of saved) map[row.item.id] = row.state;
      setStates(map);
    } catch {
      // Non-fatal: chips still update after local setState.
    }
  }, []);

  const load = useCallback(
    async (key: string) => {
      if (!domain) return;
      setLoading(true);
      setError(null);
      try {
        const next = await api.domainFeed(domain.slug, key);
        setFeed(next);
        await hydrateStates(domain.slug);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load feed");
      } finally {
        setLoading(false);
      }
    },
    [domain, hydrateStates],
  );

  useEffect(() => {
    load(feedKey);
  }, [feedKey, load]);

  if (!domain) return <section className="panel"><p className="error">Unknown domain.</p></section>;

  async function setState(itemId: string, state: ItemState, notes?: string) {
    if (!domain) return;
    setBusyIds((b) => ({ ...b, [itemId]: true }));
    try {
      await api.setState(domain.slug, itemId, { state, notes });
      setStates((s) => ({ ...s, [itemId]: state }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save state");
    } finally {
      setBusyIds((b) => {
        const next = { ...b };
        delete next[itemId];
        return next;
      });
    }
  }

  async function clearState(itemId: string) {
    if (!domain) return;
    setBusyIds((b) => ({ ...b, [itemId]: true }));
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
      setBusyIds((b) => {
        const next = { ...b };
        delete next[itemId];
        return next;
      });
    }
  }

  async function act(eventId: string, action: string, ratingLabel?: RatingLabel) {
    setBusyIds((b) => ({ ...b, [eventId]: true }));
    try {
      await api.recAction(eventId, action, ratingLabel);
      await load(feedKey);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusyIds((b) => {
        const next = { ...b };
        delete next[eventId];
        return next;
      });
    }
  }

  return (
    <div>
      <section className="panel feed-hero">
        <h2>
          {DOMAIN_LABEL[domain.mediaType]} · {FEEDS.find((f) => f.key === feedKey)?.title}
        </h2>
        <DomainSubnav slug={domain.slug} user={user} />
        <p className="lead">
          Recommendations for this domain live here. Mark Interested or Shortlist to shape ranking; your
          picks are kept in My List.
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
        <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => load(feedKey)}>
          Refresh feed
        </button>
      </section>

      {error && (
        <section className="panel">
          <p className="error">{error}</p>
        </section>
      )}

      <section className="panel">
        {loading && !feed ? (
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
                busy={Boolean(busyIds[card.item.id] || busyIds[card.event_id])}
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
