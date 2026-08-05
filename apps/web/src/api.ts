const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export type MediaType = "movie" | "tv" | "book" | "audiobook" | "comic" | "game";

export const RATING_LABELS = [
  "Loved it",
  "Liked it",
  "Meh",
  "Disliked it",
  "Hated it",
] as const;

export type RatingLabel = (typeof RATING_LABELS)[number];

export interface User {
  id: string;
  email: string;
  username: string;
  enabled_media_types: string[];
  preferences: Record<string, unknown>;
  onboarding_complete: boolean;
}

export interface Item {
  id: string;
  media_type: MediaType;
  title: string;
  series?: string | null;
  genres: string[];
  creators: string[];
  release_year?: number | null;
  description?: string | null;
  cover_url?: string | null;
  popularity: number;
  is_anchor: boolean;
}

export interface RecommendationCard {
  event_id: string;
  item: Item;
  score: number;
  rank: number;
  feed_key: string;
  factors: Record<string, unknown>;
  explanation?: string | null;
}

export interface RecommendationFeed {
  feed_key: string;
  title: string;
  items: RecommendationCard[];
  generated_at: string;
}

export interface OnboardingStatus {
  complete: boolean;
  ratings_by_media_type: Record<string, number>;
  min_ratings: number;
  ready_media_types: string[];
}

export interface ImportSource {
  id: string;
  source: string;
  display_name: string;
  base_url?: string | null;
  last_sync_at?: string | null;
  last_status?: string | null;
}

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: HeadersInit = {
    ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...authHeaders(),
    ...(init.headers || {}),
  };
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  register: (email: string, username: string, password: string) =>
    request<User>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, username, password }),
    }),

  login: async (username: string, password: string) => {
    const form = new URLSearchParams();
    form.set("username", username);
    form.set("password", password);
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
    });
    if (!res.ok) throw new Error("Login failed");
    const data = (await res.json()) as { access_token: string };
    localStorage.setItem("token", data.access_token);
    return data;
  },

  me: () => request<User>("/api/auth/me"),

  updateMe: (payload: Partial<User> & { onboarding_complete?: boolean }) =>
    request<User>("/api/auth/me", { method: "PATCH", body: JSON.stringify(payload) }),

  anchors: (mediaType: MediaType, limit = 40) =>
    request<Item[]>(`/api/onboarding/anchors?media_type=${mediaType}&limit=${limit}`),

  onboardingStatus: () => request<OnboardingStatus>("/api/onboarding/status"),

  rateBatch: (
    interactions: {
      item_id: string;
      interaction_type: string;
      rating_label?: string;
      context?: string;
    }[],
  ) =>
    request("/api/interactions/batch", {
      method: "POST",
      body: JSON.stringify({ interactions }),
    }),

  feeds: () => request<{ feed_key: string; title: string }[]>("/api/recommendations/feeds"),

  feed: (feedKey: string, limit = 20) =>
    request<RecommendationFeed>(`/api/recommendations/feeds/${feedKey}?limit=${limit}`),

  recAction: (eventId: string, action: string, ratingLabel?: string) =>
    request("/api/recommendations/actions", {
      method: "POST",
      body: JSON.stringify({
        event_id: eventId,
        action,
        rating_label: ratingLabel,
      }),
    }),

  listSources: () => request<ImportSource[]>("/api/imports/sources"),

  createSource: (payload: {
    source: string;
    display_name: string;
    base_url?: string;
    credentials?: Record<string, string>;
  }) =>
    request<ImportSource>("/api/imports/sources", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  syncSource: (id: string) =>
    request(`/api/imports/sources/${id}/sync`, { method: "POST" }),

  importCsv: (rows: Record<string, unknown>[]) =>
    request("/api/imports/csv", { method: "POST", body: JSON.stringify({ rows }) }),
};

export function logout() {
  localStorage.removeItem("token");
}
