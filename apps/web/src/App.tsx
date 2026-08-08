import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, logout, User } from "./api";
import { DOMAIN_LABEL, enabledDomains, slugForMedia } from "./domains";
import AuthPage from "./pages/AuthPage";
import OnboardingPage from "./pages/OnboardingPage";
import DomainHomePage from "./pages/DomainHomePage";
import BrowsePage from "./pages/BrowsePage";
import SavedPage from "./pages/SavedPage";
import SeriesPage from "./pages/SeriesPage";
import AdminPage from "./pages/AdminPage";
import ItemDetailPage from "./pages/ItemDetailPage";
import ImportsPage from "./pages/ImportsPage";
import { getTheme, toggleTheme, type Theme } from "./theme";

function Shell({ user, onLogout, children }: { user: User; onLogout: () => void; children: ReactNode }) {
  const loc = useLocation();
  const domains = useMemo(() => enabledDomains(user.enabled_media_types), [user.enabled_media_types]);
  const isActive = (to: string) => loc.pathname === to || loc.pathname.startsWith(to + "/");
  const [theme, setThemeState] = useState<Theme>(getTheme());

  return (
    <div className="app-shell with-nav">
      <aside className="sidenav">
        <div className="brand">
          <div className="brand-mark" aria-hidden />
          <strong>Media Engine</strong>
        </div>
        <nav className="nav-group">
          <span className="nav-label">Domains</span>
          {domains.map((m) => {
            const slug = slugForMedia(m);
            return (
              <Link key={m} to={`/${slug}`} className={isActive(`/${slug}`) ? "active" : ""}>
                {DOMAIN_LABEL[m]}
              </Link>
            );
          })}
        </nav>
        <nav className="nav-group">
          <span className="nav-label">Account</span>
          <Link to="/onboarding" className={isActive("/onboarding") ? "active" : ""}>
            Onboarding
          </Link>
          <Link to="/imports" className={isActive("/imports") ? "active" : ""}>
            Imports
          </Link>
          <button type="button" className="linkish" onClick={onLogout}>
            Sign out
          </button>
        </nav>
        <div className="nav-foot">
          <button
            type="button"
            className="theme-toggle"
            onClick={() => setThemeState(toggleTheme())}
            title="Toggle light / dark"
          >
            {theme === "dark" ? "◐ Light" : "◑ Dark"}
          </button>
          <span className="muted small">{user.username} · hybrid · local-first</span>
        </div>
      </aside>
      <main className="content">{children}</main>
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

  const domains = enabledDomains(user.enabled_media_types);
  const home = domains.length ? `/${slugForMedia(domains[0])}` : "/onboarding";

  return (
    <Shell user={user} onLogout={onLogout}>
      <Routes>
        <Route
          path="/onboarding"
          element={
            <OnboardingPage
              onComplete={async () => {
                const me = await api.updateMe({ onboarding_complete: true });
                setUser(me);
                navigate(home);
              }}
            />
          }
        />
        <Route path="/imports" element={<ImportsPage />} />
        <Route path="/:domain" element={<DomainHomePage user={user} />} />
        <Route path="/:domain/browse" element={<BrowsePage />} />
        <Route path="/:domain/saved" element={<SavedPage />} />
        <Route path="/:domain/series" element={<SeriesPage />} />
        <Route path="/:domain/series/:seriesId" element={<SeriesPage />} />
        <Route
          path="/:domain/admin"
          element={user.is_admin ? <AdminPage /> : <Navigate to={home} replace />}
        />
        <Route path="/:domain/item/:itemId" element={<ItemDetailPage />} />
        <Route path="/" element={<Navigate to={home} replace />} />
        <Route path="*" element={<Navigate to={home} replace />} />
      </Routes>
    </Shell>
  );
}
