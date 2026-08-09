import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ItemState, Series, SeriesDetail } from "../api";
import { DOMAIN_LABEL } from "../domains";
import { useDomain } from "../useDomain";
import MediaCard from "../components/MediaCard";
import DomainSubnav from "../components/DomainSubnav";

export default function SeriesPage() {
  const domain = useDomain();
  const { seriesId } = useParams<{ seriesId?: string }>();
  const [list, setList] = useState<Series[]>([]);
  const [detail, setDetail] = useState<SeriesDetail | null>(null);
  const [states, setStates] = useState<Record<string, ItemState>>({});
  const [busyIds, setBusyIds] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const hydrateStates = useCallback(async (slug: string) => {
    try {
      const saved = await api.listSaved(slug, { limit: 200 });
      const map: Record<string, ItemState> = {};
      for (const row of saved) map[row.item.id] = row.state;
      setStates(map);
    } catch {
      /* ignore */
    }
  }, []);

  const load = useCallback(async () => {
    if (!domain) return;
    setBusy(true);
    setError(null);
    try {
      if (seriesId) {
        setDetail(await api.series(domain.slug, seriesId));
        await hydrateStates(domain.slug);
      } else {
        setList(await api.listSeries(domain.slug));
        setDetail(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load series");
    } finally {
      setBusy(false);
    }
  }, [domain, seriesId, hydrateStates]);

  useEffect(() => {
    load();
  }, [load]);

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

  return (
    <div>
      <section className="panel feed-hero">
        <h2>
          {DOMAIN_LABEL[domain.mediaType]} · {detail ? detail.name : "Series & franchises"}
        </h2>
        <DomainSubnav slug={domain.slug} />
        <p className="lead">
          {detail ? (
            <>
              <Link to={`/${domain.slug}/series`}>All series</Link>
              {detail.franchise ? <span className="muted"> — franchise: {detail.franchise}</span> : null}
            </>
          ) : (
            "Canonical series and franchises for this domain."
          )}
        </p>
      </section>

      {error && (
        <section className="panel">
          <p className="error">{error}</p>
        </section>
      )}

      {!detail ? (
        <section className="panel">
          {!list.length && !busy ? (
            <p className="muted">No series yet. Import a library to populate canonical series.</p>
          ) : (
            <ul className="series-list">
              {list.map((s) => (
                <li key={s.id}>
                  <Link to={`/${domain.slug}/series/${s.id}`}>{s.name}</Link>
                  {s.franchise ? <span className="muted small"> · {s.franchise}</span> : null}
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : (
        <section className="panel">
          <div className="grid-cards">
            {detail.items.map((item) => (
              <MediaCard
                key={item.id}
                item={item}
                mediaType={domain.mediaType}
                domainSlug={domain.slug}
                currentState={states[item.id] ?? null}
                busy={Boolean(busyIds[item.id])}
                onSetState={setState}
                onClearState={clearState}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
