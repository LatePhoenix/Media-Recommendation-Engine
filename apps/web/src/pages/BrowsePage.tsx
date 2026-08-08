import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, BrowseFilters, Item, ItemState, MediaType } from "../api";
import { DOMAIN_LABEL } from "../domains";
import { useDomain } from "../useDomain";
import MediaCard from "../components/MediaCard";
import { CardSkeletons, EmptyState } from "../components/Poster";

// Which filter fields make sense per media type (Phase 1 per-domain filters).
function fieldsFor(media: MediaType): string[] {
  switch (media) {
    case "movie":
    case "tv":
      return ["genre", "year_min", "year_max", "language", "watched"];
    case "book":
    case "audiobook":
      return ["genre", "creator", "series", "narrator", "length_min", "length_max"];
    case "comic":
      return ["publisher", "series", "creator", "genre"];
    case "game":
      return ["platform", "year_min", "year_max", "genre", "play"];
    default:
      return ["genre"];
  }
}

export default function BrowsePage() {
  const domain = useDomain();
  const [filters, setFilters] = useState<BrowseFilters>({ sort: "popularity" });
  const [items, setItems] = useState<Item[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = useCallback(async () => {
    if (!domain) return;
    setBusy(true);
    setError(null);
    try {
      setItems(await api.browse(domain.slug, filters));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Browse failed");
    } finally {
      setBusy(false);
    }
  }, [domain, filters]);

  useEffect(() => {
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [domain]);

  if (!domain) return <section className="panel"><p className="error">Unknown domain.</p></section>;

  const fields = fieldsFor(domain.mediaType);
  const set = (patch: Partial<BrowseFilters>) => setFilters((f) => ({ ...f, ...patch }));

  async function setState(itemId: string, state: ItemState, notes?: string) {
    if (!domain) return;
    try {
      await api.setState(domain.slug, itemId, { state, notes });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save state");
    }
  }
  async function clearState(itemId: string) {
    if (!domain) return;
    try {
      await api.clearState(domain.slug, itemId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not clear state");
    }
  }

  return (
    <div>
      <section className="panel feed-hero">
        <h2>{DOMAIN_LABEL[domain.mediaType]} · Browse</h2>
        <p className="lead">
          <Link to={`/${domain.slug}`}>Feeds</Link> · <Link to={`/${domain.slug}/saved`}>Saved</Link> ·{" "}
          <Link to={`/${domain.slug}/series`}>Series</Link>
        </p>
        <div className="filter-grid">
          <input className="input" placeholder="Search title" onChange={(e) => set({ q: e.target.value || undefined })} />
          {fields.includes("genre") && (
            <input className="input" placeholder="Genre" onChange={(e) => set({ genre: e.target.value || undefined })} />
          )}
          {fields.includes("creator") && (
            <input className="input" placeholder="Author / creator" onChange={(e) => set({ creator: e.target.value || undefined })} />
          )}
          {fields.includes("series") && (
            <input className="input" placeholder="Series" onChange={(e) => set({ series: e.target.value || undefined })} />
          )}
          {fields.includes("narrator") && (
            <input className="input" placeholder="Narrator" onChange={(e) => set({ narrator: e.target.value || undefined })} />
          )}
          {fields.includes("publisher") && (
            <input className="input" placeholder="Publisher" onChange={(e) => set({ publisher: e.target.value || undefined })} />
          )}
          {fields.includes("platform") && (
            <input className="input" placeholder="Platform" onChange={(e) => set({ platform: e.target.value || undefined })} />
          )}
          {fields.includes("language") && (
            <input className="input" placeholder="Language" onChange={(e) => set({ language: e.target.value || undefined })} />
          )}
          {fields.includes("year_min") && (
            <input
              className="input"
              type="number"
              placeholder="Year from"
              onChange={(e) => set({ year_min: e.target.value ? Number(e.target.value) : undefined })}
            />
          )}
          {fields.includes("year_max") && (
            <input
              className="input"
              type="number"
              placeholder="Year to"
              onChange={(e) => set({ year_max: e.target.value ? Number(e.target.value) : undefined })}
            />
          )}
          {fields.includes("length_min") && (
            <input
              className="input"
              type="number"
              placeholder="Min length"
              onChange={(e) => set({ length_min: e.target.value ? Number(e.target.value) : undefined })}
            />
          )}
          {fields.includes("length_max") && (
            <input
              className="input"
              type="number"
              placeholder="Max length"
              onChange={(e) => set({ length_max: e.target.value ? Number(e.target.value) : undefined })}
            />
          )}
          {fields.includes("watched") && (
            <select className="input" onChange={(e) => set({ state: (e.target.value || undefined) as ItemState | undefined })}>
              <option value="">Any watched status</option>
              <option value="in_progress">Watching now</option>
              <option value="completed">Watched</option>
            </select>
          )}
          {fields.includes("play") && (
            <select className="input" onChange={(e) => set({ state: (e.target.value || undefined) as ItemState | undefined })}>
              <option value="">Any play status</option>
              <option value="in_progress">Playing now</option>
              <option value="completed">Completed</option>
            </select>
          )}
          <select className="input" value={filters.sort} onChange={(e) => set({ sort: e.target.value as BrowseFilters["sort"] })}>
            <option value="popularity">Popularity</option>
            <option value="title">Title</option>
            <option value="release_year">Release year</option>
            <option value="recently_added">Recently added</option>
          </select>
          <button className="btn btn-primary" type="button" disabled={busy} onClick={run}>
            Apply
          </button>
        </div>
      </section>

      {error && <section className="panel"><p className="error">{error}</p></section>}

      <section className="panel">
        {busy && !items.length ? (
          <CardSkeletons />
        ) : !items.length ? (
          <EmptyState glyph="⌕">No items match. Try loosening filters.</EmptyState>
        ) : (
          <div className="grid-cards">
            {items.map((item) => (
              <MediaCard
                key={item.id}
                item={item}
                mediaType={domain.mediaType}
                domainSlug={domain.slug}
                busy={busy}
                onSetState={setState}
                onClearState={clearState}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
