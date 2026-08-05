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
