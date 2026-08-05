import { FormEvent, useState } from "react";
import { api } from "../api";

export default function AuthPage({ onAuthed }: { onAuthed: () => Promise<void> }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "register") {
        await api.register(email, username, password);
      }
      await api.login(username, password);
      await onAuthed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Auth failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-layout">
      <form className="auth-card stack" onSubmit={submit}>
        <div className="brand-mark" aria-hidden />
        <h1>Media Recommendation Engine</h1>
        <p className="sub">
          Deterministic hybrid recommender. Rate anchors, import libraries, get explainable feeds.
        </p>
        <div className="tabs">
          <button type="button" className={`tab ${mode === "login" ? "active" : ""}`} onClick={() => setMode("login")}>
            Sign in
          </button>
          <button
            type="button"
            className={`tab ${mode === "register" ? "active" : ""}`}
            onClick={() => setMode("register")}
          >
            Create account
          </button>
        </div>
        {mode === "register" && (
          <label className="field">
            Email
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
        )}
        <label className="field">
          Username
          <input required value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        </label>
        <label className="field">
          Password
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="btn btn-primary" disabled={busy} type="submit">
          {busy ? "Working…" : mode === "login" ? "Sign in" : "Create account"}
        </button>
      </form>
    </div>
  );
}
