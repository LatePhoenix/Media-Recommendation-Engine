/**
 * Shared enums and constants mirrored by the API.
 * Prefer regenerating from OpenAPI when the contract stabilizes.
 */

export const MediaTypes = [
  "movie",
  "tv",
  "book",
  "audiobook",
  "comic",
  "game",
] as const;
export type MediaType = (typeof MediaTypes)[number];

export const InteractionTypes = [
  "rate",
  "pass",
  "save",
  "consume",
  "finish",
  "dismiss",
] as const;
export type InteractionType = (typeof InteractionTypes)[number];

/** Durable per-user intent states (Phase 2 interest layer). */
export const ItemStates = [
  "interested",
  "shortlisted",
  "in_progress",
  "completed",
  "passed",
  "hidden",
] as const;
export type ItemState = (typeof ItemStates)[number];

export const InterestSources = ["manual", "imported", "inferred"] as const;
export type InterestSource = (typeof InterestSources)[number];

/** Public-metadata providers for outbound source links (Phase 3). */
export const LinkProviders = [
  "imdb",
  "rottentomatoes",
  "metacritic",
  "tmdb",
  "openlibrary",
  "googlebooks",
  "igdb",
  "comicvine",
] as const;
export type LinkProvider = (typeof LinkProviders)[number];

export const ResolutionMethods = ["api", "search", "manual", "imported"] as const;
export type ResolutionMethod = (typeof ResolutionMethods)[number];

export const RatingLabels = [
  "Loved it",
  "Liked it",
  "Meh",
  "Disliked it",
  "Hated it",
] as const;
export type RatingLabel = (typeof RatingLabels)[number];

export const RATING_WEIGHTS: Record<RatingLabel, number> = {
  "Loved it": 2.0,
  "Liked it": 1.0,
  Meh: 0.0,
  "Disliked it": -1.0,
  "Hated it": -2.0,
};

export const FeedKeys = [
  "best_next",
  "something_different",
  "from_your_servers",
  "pass_resurface",
  "because_you_loved",
] as const;
export type FeedKey = (typeof FeedKeys)[number];

export const ImportSources = [
  "jellyfin",
  "plex",
  "audiobookshelf",
  "komga",
  "trakt",
  "csv",
  "manual",
] as const;
export type ImportSource = (typeof ImportSources)[number];
