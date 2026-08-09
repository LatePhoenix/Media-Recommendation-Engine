// Empty string = same-origin (native FastAPI static UI). `||` would break that.
const API_BASE =
  import.meta.env.VITE_API_BASE_URL !== undefined
    ? import.meta.env.VITE_API_BASE_URL
    : "http://localhost:8000";


export type MediaType = "movie" | "tv" | "book" | "audiobook" | "comic" | "game";

export const RATING_LABELS = [
  "Loved it",
  "Liked it",
  "Meh",
  "Disliked it",
  "Hated it",
] as const;

export type RatingLabel = (typeof RATING_LABELS)[number];

export const ITEM_STATES = [
  "interested",
  "shortlisted",
  "in_progress",
  "completed",
  "passed",
  "hidden",
] as const;
export type ItemState = (typeof ITEM_STATES)[number];

export type SavedSort = "recently_added" | "priority" | "release_date" | "score";
export type BrowseSort = "popularity" | "title" | "release_year" | "recently_added";

export interface SavedItem {
  item: Item;
  state: ItemState;
  source: string;
  notes?: string | null;
  priority?: number | null;
  created_at: string;
  updated_at: string;
}

export interface ItemStateRow {
  item_id: string;
  media_type: MediaType;
  state: ItemState;
  source: string;
  notes?: string | null;
  priority?: number | null;
  created_at: string;
  updated_at: string;
}

export interface Collection {
  id: string;
  media_type: MediaType;
  name: string;
  description?: string | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface CollectionDetail extends Collection {
  items: Item[];
}

export interface Series {
  id: string;
  media_type: MediaType;
  name: string;
  franchise?: string | null;
}

export interface SeriesDetail extends Series {
  items: Item[];
}

export interface Creator {
  id: string;
  name: string;
  kind?: string | null;
}

export interface CreatorDetail extends Creator {
  items: Item[];
}

export interface ExternalLink {
  provider: string;
  label: string;
  external_key?: string | null;
  external_url: string;
  confidence: number;
  resolution_method: string;
  verified: boolean;
}

export interface ItemDetail extends Item {
  description?: string | null;
  links: ExternalLink[];
}

export interface ModelConfig {
  media_type: MediaType;
  name: string;
  weights: Record<string, number>;
  active: boolean;
}

export interface AdminModelConfig extends ModelConfig {
  id: string;
}

export type DomainMetrics = Record<string, number | string | null>;

export interface MetricsComparison {
  media_type: MediaType;
  control: DomainMetrics;
  treatment: DomainMetrics;
}

export interface BrowseFilters {
  q?: string;
  genre?: string;
  creator?: string;
  series?: string;
  language?: string;
  release_year?: number;
  year_min?: number;
  year_max?: number;
  length_min?: number;
  length_max?: number;
  publisher?: string;
  narrator?: string;
  platform?: string;
  state?: ItemState;
  anchors_only?: boolean;
  sort?: BrowseSort;
  limit?: number;
  offset?: number;
}

export interface User {
  id: string;
  email: string;
  username: string;
  enabled_media_types: string[];
  preferences: Record<string, unknown>;
  onboarding_complete: boolean;
  is_admin?: boolean;
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

  // --- Per-domain (Phase 1/2). `domain` is a plural slug, e.g. "movies". ---

  domainFeed: (domain: string, feedKey: string, limit = 20) =>
    request<RecommendationFeed>(`/api/${domain}/recommendations/feeds/${feedKey}?limit=${limit}`),

  modelConfig: (domain: string) => request<ModelConfig>(`/api/${domain}/model-config`),

  itemLinks: (domain: string, itemId: string) =>
    request<ExternalLink[]>(`/api/${domain}/items/${itemId}/links`),

  item: (domain: string, itemId: string) =>
    request<ItemDetail>(`/api/${domain}/catalog/items/${itemId}`),

  listSeries: (domain: string) => request<Series[]>(`/api/${domain}/series`),

  series: (domain: string, seriesId: string) =>
    request<SeriesDetail>(`/api/${domain}/series/${seriesId}`),

  creator: (domain: string, creatorId: string) =>
    request<CreatorDetail>(`/api/${domain}/creators/${creatorId}`),

  // --- Admin / ops (Phase 5) ---

  adminModelConfigs: (domain: string) =>
    request<AdminModelConfig[]>(`/api/admin/${domain}/model-configs`),

  adminMetrics: (domain: string, config?: string) =>
    request<DomainMetrics>(
      `/api/admin/${domain}/metrics${config ? `?config=${encodeURIComponent(config)}` : ""}`,
    ),

  adminCompare: (domain: string, treatment: string, control = "default") =>
    request<MetricsComparison>(
      `/api/admin/${domain}/metrics/compare?control=${encodeURIComponent(control)}&treatment=${encodeURIComponent(treatment)}`,
    ),

  browse: (domain: string, filters: BrowseFilters = {}) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
    });
    const qs = params.toString();
    return request<Item[]>(`/api/${domain}/catalog/items${qs ? `?${qs}` : ""}`);
  },

  getState: (domain: string, itemId: string) =>
    request<ItemStateRow | null>(`/api/${domain}/items/${itemId}/state`),

  setState: (
    domain: string,
    itemId: string,
    payload: { state: ItemState; notes?: string; priority?: number },
  ) =>
    request<ItemStateRow>(`/api/${domain}/items/${itemId}/state`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  clearState: (domain: string, itemId: string) =>
    request(`/api/${domain}/items/${itemId}/state`, { method: "DELETE" }),

  listSaved: (
    domain: string,
    opts: { state?: ItemState[]; sort?: SavedSort; limit?: number } = {},
  ) => {
    const params = new URLSearchParams();
    (opts.state || []).forEach((s) => params.append("state", s));
    if (opts.sort) params.set("sort", opts.sort);
    if (opts.limit) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return request<SavedItem[]>(`/api/${domain}/saved${qs ? `?${qs}` : ""}`);
  },

  listCollections: (domain: string) => request<Collection[]>(`/api/${domain}/collections`),

  createCollection: (domain: string, payload: { name: string; description?: string }) =>
    request<Collection>(`/api/${domain}/collections`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

export function logout() {
  localStorage.removeItem("token");
}
