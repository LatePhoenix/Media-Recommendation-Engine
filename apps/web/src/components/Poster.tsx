import { useEffect, useState, type ReactNode } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function resolveSrc(src?: string | null): string | null {
  if (!src) return null;
  if (src.startsWith("/api/")) return `${API_BASE}${src}`;
  return src;
}

export function Poster({
  src,
  title,
  wide,
  className,
}: {
  src?: string | null;
  title: string;
  wide?: boolean;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const initial = title.trim().charAt(0).toUpperCase() || "?";
  const cls = className ?? `poster${wide ? " wide" : ""}`;
  const resolved = resolveSrc(src);
  const needsAuth = Boolean(src?.startsWith("/api/"));

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setFailed(false);
    setBlobUrl(null);
    if (!needsAuth || !resolved) return;
    (async () => {
      try {
        const resp = await fetch(resolved, { headers: authHeaders() });
        if (!resp.ok) throw new Error("artwork fetch failed");
        const blob = await resp.blob();
        objectUrl = URL.createObjectURL(blob);
        if (!cancelled) setBlobUrl(objectUrl);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [needsAuth, resolved]);

  const imgSrc = needsAuth ? blobUrl : resolved;

  return (
    <div className={cls}>
      {imgSrc && !failed ? (
        <img src={imgSrc} alt="" loading="lazy" onError={() => setFailed(true)} />
      ) : (
        <div className="poster-fallback" aria-hidden>
          {initial}
        </div>
      )}
    </div>
  );
}

export function CardSkeletons({ count = 6 }: { count?: number }) {
  return (
    <div className="grid-cards">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="skeleton skeleton-card" />
      ))}
    </div>
  );
}

export function EmptyState({ glyph, children }: { glyph?: string; children: ReactNode }) {
  return (
    <div className="empty-state">
      <span className="glyph" aria-hidden>
        {glyph ?? "◍"}
      </span>
      <p className="muted">{children}</p>
    </div>
  );
}
