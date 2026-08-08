import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ItemDetail, ItemState } from "../api";
import { DOMAIN_LABEL, IN_PROGRESS_LABEL } from "../domains";
import { useDomain } from "../useDomain";
import { Poster } from "../components/Poster";

function stateOptions(domain: ReturnType<typeof useDomain>): { value: ItemState; label: string }[] {
  const inProgress = domain ? IN_PROGRESS_LABEL[domain.mediaType] : "In progress";
  return [
    { value: "interested", label: "Interested" },
    { value: "shortlisted", label: "Shortlist" },
    { value: "in_progress", label: inProgress },
    { value: "completed", label: "Completed" },
    { value: "passed", label: "Pass" },
    { value: "hidden", label: "Hide" },
  ];
}

export default function ItemDetailPage() {
  const domain = useDomain();
  const { itemId } = useParams<{ itemId: string }>();
  const [item, setItem] = useState<ItemDetail | null>(null);
  const [state, setStateVal] = useState<ItemState | null>(null);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!domain || !itemId) return;
    setLoading(true);
    setError(null);
    try {
      const [detail, st] = await Promise.all([
        api.item(domain.slug, itemId),
        api.getState(domain.slug, itemId).catch(() => null),
      ]);
      setItem(detail);
      setStateVal(st?.state ?? null);
      setNotes(st?.notes ?? "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load item");
    } finally {
      setLoading(false);
    }
  }, [domain, itemId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!domain) return <section className="panel"><p className="error">Unknown domain.</p></section>;

  async function setItemState(next: ItemState) {
    if (!domain || !itemId) return;
    setBusy(true);
    try {
      if (state === next) {
        await api.clearState(domain.slug, itemId);
        setStateVal(null);
      } else {
        await api.setState(domain.slug, itemId, { state: next, notes: notes || undefined });
        setStateVal(next);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update state");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <section className="panel">
        <p className="lead" style={{ marginBottom: 0 }}>
          <Link to={`/${domain.slug}`}>← {DOMAIN_LABEL[domain.mediaType]}</Link> ·{" "}
          <Link to={`/${domain.slug}/browse`}>Browse</Link>
        </p>
      </section>

      {error && <section className="panel"><p className="error">{error}</p></section>}

      {loading || !item ? (
        <section className="panel">
          <div className="detail-hero">
            <div className="skeleton detail-poster" />
            <div style={{ flex: 1 }}>
              <div className="skeleton" style={{ height: 32, width: "60%", marginBottom: 12 }} />
              <div className="skeleton" style={{ height: 16, width: "90%", marginBottom: 8 }} />
              <div className="skeleton" style={{ height: 16, width: "80%" }} />
            </div>
          </div>
        </section>
      ) : (
        <section className="panel">
          <div className="detail-hero">
            <Poster src={item.cover_url} title={item.title} className="detail-poster" />
            <div className="detail-info">
              <h2>{item.title}</h2>
              <div className="meta">
                <span className="chip">{item.media_type}</span>
                {item.release_year && <span className="chip">{item.release_year}</span>}
                {item.series && <span className="chip">{item.series}</span>}
                {(item.genres || []).slice(0, 5).map((g) => (
                  <span className="chip" key={g}>
                    {g}
                  </span>
                ))}
              </div>
              {item.description ? <p className="detail-desc">{item.description}</p> : null}

              <div className="detail-section">
                <p className="detail-section-title">Your list</p>
                <div className="state-row">
                  {stateOptions(domain).map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      disabled={busy}
                      className={`chip-btn ${state === opt.value ? "active" : ""}`}
                      onClick={() => setItemState(opt.value)}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
                <div className="row" style={{ marginTop: 10 }}>
                  <input
                    className="input"
                    placeholder="Note — recommended by… / watch with family…"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                  />
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={busy}
                    onClick={() => setItemState(state ?? "interested")}
                  >
                    Save note
                  </button>
                </div>
              </div>

              {(item.creators || []).length > 0 && (
                <div className="detail-section">
                  <p className="detail-section-title">Creators</p>
                  <div className="meta">
                    {item.creators.map((c) => (
                      <span className="chip" key={c}>
                        {c}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="detail-section">
                <p className="detail-section-title">Sources</p>
                {item.links.length === 0 ? (
                  <p className="muted small">No sources resolved.</p>
                ) : (
                  <div className="sources">
                    {item.links.map((l) => (
                      <a
                        key={l.provider}
                        className={`source-link ${l.verified ? "verified" : "unverified"}`}
                        href={l.external_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={l.verified ? `${l.label} (verified)` : `Search ${l.label} (unverified)`}
                      >
                        {l.label}
                        {!l.verified && <span className="src-flag">search</span>}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
