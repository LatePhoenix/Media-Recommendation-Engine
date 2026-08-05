import { FormEvent, useEffect, useState } from "react";
import { api, ImportSource } from "../api";

export default function ImportsPage() {
  const [sources, setSources] = useState<ImportSource[]>([]);
  const [source, setSource] = useState("jellyfin");
  const [displayName, setDisplayName] = useState("Home Jellyfin");
  const [baseUrl, setBaseUrl] = useState("http://localhost:8096");
  const [apiKey, setApiKey] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [csvText, setCsvText] = useState(
    "title,media_type,year,genres,creators,rating_label\nThe Prestige,movie,2006,Thriller|Drama,Christopher Nolan,Liked it",
  );
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setSources(await api.listSources());
  }

  useEffect(() => {
    refresh().catch((e) => setError(e instanceof Error ? e.message : "Failed"));
  }, []);

  function selectSource(nextSource: string) {
    setSource(nextSource);
    const defaults: Record<string, { name: string; url: string }> = {
      jellyfin: { name: "Home Jellyfin", url: "http://localhost:8096" },
      plex: { name: "Home Plex", url: "http://localhost:32400" },
      audiobookshelf: { name: "Home Audiobookshelf", url: "http://localhost:13378" },
      komga: { name: "Home Komga", url: "http://localhost:25600" },
      trakt: { name: "Trakt", url: "https://api.trakt.tv" },
    };
    const selected = defaults[nextSource];
    if (selected) {
      setDisplayName(selected.name);
      setBaseUrl(selected.url);
    }
  }

  async function addSource(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const credentials: Record<string, string> = {};
      if (apiKey) credentials.api_key = apiKey;
      if (username) credentials.username = username;
      if (password) credentials.password = password;
      await api.createSource({
        source,
        display_name: displayName,
        base_url: baseUrl || undefined,
        credentials,
      });
      setMsg("Source added");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  async function sync(id: string) {
    setBusy(true);
    try {
      await api.syncSource(id);
      setMsg("Sync started");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setBusy(false);
    }
  }

  async function runCsv() {
    setBusy(true);
    setError(null);
    try {
      const lines = csvText.trim().split(/\r?\n/);
      const headers = lines[0].split(",").map((h) => h.trim());
      const rows = lines.slice(1).filter(Boolean).map((line) => {
        const cols = line.split(",");
        const row: Record<string, unknown> = {};
        headers.forEach((h, i) => {
          row[h] = cols[i]?.trim();
        });
        if (typeof row.genres === "string") {
          row.genres = (row.genres as string).split("|");
        }
        if (typeof row.creators === "string") {
          row.creators = (row.creators as string).split("|");
        }
        return row;
      });
      const result = await api.importCsv(rows);
      setMsg(`CSV import: ${JSON.stringify(result)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "CSV failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <section className="panel">
        <h2>Connected sources</h2>
        <p className="lead">
          Jellyfin, Plex, and Audiobookshelf sync catalog + consumption. Komga/Trakt are stubbed. This app owns
          pass/save/rate.
        </p>
        {!sources.length ? (
          <p className="muted">No sources yet.</p>
        ) : (
          <div className="stack">
            {sources.map((s) => (
              <div key={s.id} className="row" style={{ justifyContent: "space-between" }}>
                <div>
                  <strong>{s.display_name}</strong>
                  <div className="mono muted">
                    {s.source} · {s.base_url || "—"} · {s.last_status || "never synced"}
                  </div>
                </div>
                <button className="btn btn-secondary" type="button" disabled={busy} onClick={() => sync(s.id)}>
                  Sync
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <h2>Add source</h2>
        <form className="stack" onSubmit={addSource}>
          <div className="row">
            <label className="field">
              Type
              <select value={source} onChange={(e) => selectSource(e.target.value)}>
                <option value="jellyfin">Jellyfin</option>
                <option value="plex">Plex</option>
                <option value="audiobookshelf">Audiobookshelf</option>
                <option value="komga">Komga (stub)</option>
                <option value="trakt">Trakt (stub)</option>
              </select>
            </label>
            <label className="field">
              Display name
              <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
            </label>
          </div>
          <label className="field">
            Base URL
            <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://..." />
          </label>
          {source === "plex" ? (
            <p className="muted">
              When the API runs in Docker on Windows, use <span className="mono">http://host.docker.internal:32400</span>{" "}
              for a Plex server on this machine.
            </p>
          ) : null}
          <div className="row">
            <label className="field">
              {source === "plex" ? "Plex access token" : "API key / token"}
              <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
            </label>
            <label className="field">
              Username
              <input value={username} onChange={(e) => setUsername(e.target.value)} />
            </label>
            <label className="field">
              Password
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
          </div>
          <button className="btn btn-primary" type="submit" disabled={busy}>
            Add source
          </button>
        </form>
      </section>

      <section className="panel">
        <h2>CSV / manual import</h2>
        <p className="lead">Columns: title, media_type, year, genres (pipe-separated), creators, rating_label</p>
        <textarea rows={6} value={csvText} onChange={(e) => setCsvText(e.target.value)} />
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn btn-secondary" type="button" disabled={busy} onClick={runCsv}>
            Import CSV rows
          </button>
        </div>
      </section>

      {error && <p className="error">{error}</p>}
      {msg && <p className="success">{msg}</p>}
    </div>
  );
}
