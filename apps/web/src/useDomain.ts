import { useMemo } from "react";
import { useParams } from "react-router-dom";
import type { MediaType } from "./api";
import { SLUG_TO_MEDIA } from "./domains";

/**
 * Resolve the :domain route param to a slug + MediaType, or null if unknown.
 *
 * Memoized on the raw param so the returned object keeps a STABLE identity across
 * renders. Returning a fresh object literal here makes it unstable as a hook/effect
 * dependency (e.g. DomainHomePage's `load` useCallback), which re-fires the feed
 * effect every render -> infinite fetch loop (jitter, 429 storms, aborted fetches,
 * perpetually-busy UI).
 */
export function useDomain(): { slug: string; mediaType: MediaType } | null {
  const { domain } = useParams<{ domain: string }>();
  return useMemo(() => {
    if (!domain) return null;
    const mediaType = SLUG_TO_MEDIA[domain];
    if (!mediaType) return null;
    return { slug: domain, mediaType };
  }, [domain]);
}
