import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AdminModelConfig, api, DomainMetrics, MetricsComparison } from "../api";
import { DOMAIN_LABEL } from "../domains";
import { useDomain } from "../useDomain";

function MetricsTable({ title, metrics }: { title: string; metrics: DomainMetrics }) {
  return (
    <div>
      <h3>{title}</h3>
      <table className="metrics-table">
        <tbody>
          {Object.entries(metrics).map(([k, v]) => (
            <tr key={k}>
              <td className="muted">{k}</td>
              <td className="mono">{v === null ? "—" : String(v)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AdminPage() {
  const domain = useDomain();
  const [configs, setConfigs] = useState<AdminModelConfig[]>([]);
  const [metrics, setMetrics] = useState<DomainMetrics | null>(null);
  const [comparison, setComparison] = useState<MetricsComparison | null>(null);
  const [treatment, setTreatment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!domain) return;
    setBusy(true);
    setError(null);
    try {
      const [cfg, met] = await Promise.all([
        api.adminModelConfigs(domain.slug),
        api.adminMetrics(domain.slug),
      ]);
      setConfigs(cfg);
      setMetrics(met);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load admin data");
    } finally {
      setBusy(false);
    }
  }, [domain]);

  useEffect(() => {
    load();
  }, [load]);

  if (!domain) return <section className="panel"><p className="error">Unknown domain.</p></section>;

  async function compare() {
    if (!domain || !treatment) return;
    setBusy(true);
    setError(null);
    try {
      setComparison(await api.adminCompare(domain.slug, treatment));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Compare failed");
    } finally {
      setBusy(false);
    }
  }

  const weightKeys = Array.from(
    new Set(configs.flatMap((c) => Object.keys(c.weights))),
  ).sort();

  return (
    <div>
      <section className="panel feed-hero">
        <h2>{DOMAIN_LABEL[domain.mediaType]} · Admin</h2>
        <p className="lead">
          Per-media ranking weights and offline metrics. <Link to={`/${domain.slug}`}>Feeds</Link>
        </p>
      </section>

      {error && <section className="panel"><p className="error">{error}</p></section>}

      <section className="panel">
        <h3>Model configs</h3>
        {!configs.length ? (
          <p className="muted">No configs. Run the seed to create per-media defaults.</p>
        ) : (
          <div className="table-scroll">
            <table className="metrics-table">
              <thead>
                <tr>
                  <th>weight</th>
                  {configs.map((c) => (
                    <th key={c.id} className="mono">
                      {c.name}
                      {c.active ? " ★" : ""}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {weightKeys.map((wk) => (
                  <tr key={wk}>
                    <td className="muted">{wk}</td>
                    {configs.map((c) => (
                      <td key={c.id} className="mono">
                        {c.weights[wk] ?? "—"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel">
        {metrics && <MetricsTable title="Metrics (active/default served)" metrics={metrics} />}
      </section>

      <section className="panel">
        <h3>Compare control vs treatment</h3>
        <div className="row">
          <input
            className="input"
            placeholder="Treatment config name"
            value={treatment}
            onChange={(e) => setTreatment(e.target.value)}
          />
          <button className="btn btn-primary" type="button" disabled={busy || !treatment} onClick={compare}>
            Compare
          </button>
        </div>
        {comparison && (
          <div className="compare-grid">
            <MetricsTable title="Control (default)" metrics={comparison.control} />
            <MetricsTable title={`Treatment (${treatment})`} metrics={comparison.treatment} />
          </div>
        )}
      </section>
    </div>
  );
}
