import { Link, useLocation } from "react-router-dom";
import type { User } from "../api";

/** Domain-scoped primary nav: Feeds · Browse · My List · Series. */
export default function DomainSubnav({
  slug,
  user,
}: {
  slug: string;
  user?: User | null;
}) {
  const loc = useLocation();
  const base = `/${slug}`;
  const is = (to: string, exact = false) =>
    exact ? loc.pathname === to : loc.pathname === to || loc.pathname.startsWith(to + "/");

  return (
    <nav className="domain-subnav" aria-label="Domain">
      <Link to={base} className={is(base, true) ? "active" : ""}>
        Feeds
      </Link>
      <Link to={`${base}/browse`} className={is(`${base}/browse`) ? "active" : ""}>
        Browse
      </Link>
      <Link to={`${base}/saved`} className={is(`${base}/saved`) || is(`${base}/my-list`) ? "active" : ""}>
        My List
      </Link>
      <Link to={`${base}/series`} className={is(`${base}/series`) ? "active" : ""}>
        Series
      </Link>
      {user?.is_admin ? (
        <Link to={`${base}/admin`} className={is(`${base}/admin`) ? "active" : ""}>
          Admin
        </Link>
      ) : null}
    </nav>
  );
}
