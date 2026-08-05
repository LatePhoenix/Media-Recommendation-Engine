import { useEffect, useState, type ReactNode } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, logout, User } from "./api";
import AuthPage from "./pages/AuthPage";
import OnboardingPage from "./pages/OnboardingPage";
import FeedsPage from "./pages/FeedsPage";
import ImportsPage from "./pages/ImportsPage";

function Shell({ user, onLogout, children }: { user: User; onLogout: () => void; children: ReactNode }) {
  const loc = useLocation();
  const link = (to: string, label: string) => (
    <Link to={to} className={loc.pathname === to ? "active" : ""}>
      {label}
    </Link>
  );
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden />
          <h1>Media Recommendation Engine</h1>
          <span>
            {user.username} · hybrid · local-first
          </span>
        </div>
        <nav className="nav">
          {link("/", "Feeds")}
          {link("/onboarding", "Onboarding")}
          {link("/imports", "Imports")}
          <button type="button" className="linkish" onClick={onLogout}>
            Sign out
          </button>
        </nav>
      </header>
      {children}
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => localStorage.removeItem("token"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="auth-layout">
        <p className="muted">Loading…</p>
      </div>
    );
  }

  if (!user) {
    return (
      <Routes>
        <Route
          path="*"
          element={
            <AuthPage
              onAuthed={async () => {
                const me = await api.me();
                setUser(me);
                navigate(me.onboarding_complete ? "/" : "/onboarding");
              }}
            />
          }
        />
      </Routes>
    );
  }

  const onLogout = () => {
    logout();
    setUser(null);
    navigate("/login");
  };

  return (
    <Shell user={user} onLogout={onLogout}>
      <Routes>
        <Route path="/" element={<FeedsPage />} />
        <Route
          path="/onboarding"
          element={
            <OnboardingPage
              onComplete={async () => {
                const me = await api.updateMe({ onboarding_complete: true });
                setUser(me);
                navigate("/");
              }}
            />
          }
        />
        <Route path="/imports" element={<ImportsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  );
}
