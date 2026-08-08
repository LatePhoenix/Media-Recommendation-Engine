import type { MediaType } from "./api";

/** Plural URL slug per media type (mirrors app/domains.py). */
export const MEDIA_TO_SLUG: Record<MediaType, string> = {
  movie: "movies",
  tv: "tv",
  audiobook: "audiobooks",
  game: "games",
  book: "books",
  comic: "comics",
};

export const SLUG_TO_MEDIA: Record<string, MediaType> = Object.fromEntries(
  Object.entries(MEDIA_TO_SLUG).map(([m, s]) => [s, m as MediaType]),
) as Record<string, MediaType>;

/** Display order in the side-nav. */
export const DOMAIN_ORDER: MediaType[] = ["movie", "tv", "audiobook", "game", "book", "comic"];

export const DOMAIN_LABEL: Record<MediaType, string> = {
  movie: "Movies",
  tv: "TV",
  audiobook: "Audiobooks",
  game: "Games",
  book: "Books",
  comic: "Comics",
};

/** Domain-specific label for the canonical `in_progress` state. */
export const IN_PROGRESS_LABEL: Record<MediaType, string> = {
  movie: "Watching now",
  tv: "Watching now",
  audiobook: "Listening now",
  game: "Playing now",
  book: "Reading now",
  comic: "Reading now",
};

export function slugForMedia(m: MediaType): string {
  return MEDIA_TO_SLUG[m];
}

export function enabledDomains(enabled: string[]): MediaType[] {
  const set = new Set(enabled);
  return DOMAIN_ORDER.filter((m) => set.has(m));
}
