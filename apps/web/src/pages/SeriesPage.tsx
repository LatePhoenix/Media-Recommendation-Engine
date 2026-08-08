import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ItemState, Series, SeriesDetail } from "../api";
import { DOMAIN_LABEL } from "../domains";
import { useDomain } from "../useDomain";
import MediaCard from "../components/MediaCard";

export default function SeriesPage() {
  const domain = useDomain();
  const { seriesId } = useParams<{ seriesId?: string }>();
  const [list, setList] = useState<Series[]>([]);
  const [detail, setDetail] = useState<SeriesDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!domain) return;
    setBusy(true);
    setError(null);
    try {
      if (seriesId) {
        setDetail(await api.series(domain.slug, seriesId));
      } else {
        setList(await api.listSeries(domain.slug));
        setDetail(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load series");
    } finally {
      setBusy(false);
    }
  }, [domain, seriesId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!domain) return <section className="panel"><p className="error">Unknown domain.</p></section>;

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
        <h2>
          {DOMAIN_LABEL[domain.mediaType]} · {detail ? detail.name : "Series & franchises"}
        </h2>
        <p className="lead">
          <Link to={`/${domain.slug}`}>Feeds</Link> · <Link to={`/${domain.slug}/browse`}>Browse</Link>
          {detail && (
            <>
              {" "}
              · <Link to={`/${domain.slug}/series`}>All series</Link>
            </>
          )}
          {detail?.franchise ? <span className="muted"> — franchise: {detail.franchise}</span> : null}
        </p>
      </section>

      {error && <section className="panel"><p className="error">{error}</p></section>}

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
                busy={busy}
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
