import { useState, type ReactNode } from "react";

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
  const initial = title.trim().charAt(0).toUpperCase() || "?";
  const cls = className ?? `poster${wide ? " wide" : ""}`;
  return (
    <div className={cls}>
      {src && !failed ? (
        <img src={src} alt="" loading="lazy" onError={() => setFailed(true)} />
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
