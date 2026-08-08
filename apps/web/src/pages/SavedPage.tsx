import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ItemState, SavedItem, SavedSort } from "../api";
import { DOMAIN_LABEL, IN_PROGRESS_LABEL } from "../domains";
import { useDomain } from "../useDomain";
import MediaCard from "../components/MediaCard";
import { CardSkeletons, EmptyState } from "../components/Poster";

const SORTS: { value: SavedSort; label: string }[] = [
  { value: "recently_added", label: "Recently added" },
  { value: "priority", label: "Priority" },
  { value: "release_date", label: "Release date" },
  { value: "score", label: "Score" },
];

export default function SavedPage() {
  const domain = useDomain();
  const [filter, setFilter] = useState<ItemState | "all">("all");
  const [sort, setSort] = useState<SavedSort>("recently_added");
  const [rows, setRows] = useState<SavedItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const stateTabs: { value: ItemState | "all"; label: string }[] = domain
    ? [
        { value: "all", label: "All" },
        { value: "interested", label: "Interested" },
        { value: "shortlisted", label: "Shortlist" },
        { value: "in_progress", label: IN_PROGRESS_LABEL[domain.mediaType] },
        { value: "completed", label: "Completed" },
        { value: "passed", label: "Passed" },
      ]
    : [];

  const load = useCallback(async () => {
    if (!domain) return;
    setBusy(true);
    setError(null);
    try {
      const opts = filter === "all" ? { sort } : { state: [filter], sort };
      setRows(await api.listSaved(domain.slug, opts));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load saved items");
    } finally {
      setBusy(false);
    }
  }, [domain, filter, sort]);

  useEffect(() => {
    load();
  }, [load]);

  if (!domain) return <section className="panel"><p className="error">Unknown domain.</p></section>;

  async function setState(itemId: string, state: ItemState, notes?: string) {
    if (!domain) return;
    setBusy(true);
    try {
      await api.setState(domain.slug, itemId, { state, notes });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update state");
    } finally {
      setBusy(false);
    }
  }

  async function clearState(itemId: string) {
    if (!domain) return;
    setBusy(true);
    try {
      await api.clearState(domain.slug, itemId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <section className="panel feed-hero">
        <h2>{DOMAIN_LABEL[domain.mediaType]} · Saved</h2>
        <p className="lead">
          Your durable interest list for this domain. <Link to={`/${domain.slug}`}>Feeds</Link> ·{" "}
          <Link to={`/${domain.slug}/browse`}>Browse</Link> · <Link to={`/${domain.slug}/series`}>Series</Link>
        </p>
        <div className="tabs">
          {stateTabs.map((t) => (
            <button
              key={t.value}
              type="button"
              className={`tab ${filter === t.value ? "active" : ""}`}
              onClick={() => setFilter(t.value)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="row">
          <label className="muted small">Sort</label>
          <select className="input" value={sort} onChange={(e) => setSort(e.target.value as SavedSort)}>
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      </section>

      {error && <section className="panel"><p className="error">{error}</p></section>}

      <section className="panel">
        {busy && !rows.length ? (
          <CardSkeletons />
        ) : !rows.length ? (
          <EmptyState glyph="❑">Nothing saved here yet. Mark items Interested or Shortlist from a feed.</EmptyState>
        ) : (
          <div className="grid-cards">
            {rows.map((row) => (
              <MediaCard
                key={row.item.id}
                item={row.item}
                mediaType={domain.mediaType}
                domainSlug={domain.slug}
                currentState={row.state}
                notes={row.notes}
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
