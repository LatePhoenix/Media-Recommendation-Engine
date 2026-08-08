import { useParams } from "react-router-dom";
import type { MediaType } from "./api";
import { SLUG_TO_MEDIA } from "./domains";

/** Resolve the :domain route param to a slug + MediaType, or null if unknown. */
export function useDomain(): { slug: string; mediaType: MediaType } | null {
  const { domain } = useParams<{ domain: string }>();
  if (!domain) return null;
  const mediaType = SLUG_TO_MEDIA[domain];
  if (!mediaType) return null;
  return { slug: domain, mediaType };
}
