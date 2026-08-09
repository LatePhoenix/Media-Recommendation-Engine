import { useCallback, useEffect, useState } from "react";
import { api, ItemState, SavedItem, SavedSort } from "../api";
import { DOMAIN_LABEL, IN_PROGRESS_LABEL } from "../domains";
import { useDomain } from "../useDomain";
import MediaCard from "../components/MediaCard";
import DomainSubnav from "../components/DomainSubnav";
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
  const [busyIds, setBusyIds] = useState<Record<string, boolean>>({});
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
      setError(e instanceof Error ? e.message : "Failed to load My List");
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
    setBusyIds((b) => ({ ...b, [itemId]: true }));
    try {
      await api.setState(domain.slug, itemId, { state, notes });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update state");
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
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove");
    } finally {
      setBusyIds((b) => {
        const next = { ...b };
        delete next[itemId];
        return next;
      });
    }
  }

  return (
    <div>
      <section className="panel feed-hero">
        <h2>{DOMAIN_LABEL[domain.mediaType]} · My List</h2>
        <DomainSubnav slug={domain.slug} />
        <p className="lead">
          Your durable interest list for this domain — Interested, Shortlist, in progress, completed, and
          passes.
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

      {error && (
        <section className="panel">
          <p className="error">{error}</p>
        </section>
      )}

      <section className="panel">
        {busy && !rows.length ? (
          <CardSkeletons />
        ) : !rows.length ? (
          <EmptyState glyph="❑">Nothing here yet. Mark items Interested or Shortlist from Feeds or Browse.</EmptyState>
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
                busy={Boolean(busyIds[row.item.id])}
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
