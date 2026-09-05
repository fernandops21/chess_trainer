import type {
  DashboardOut,
  GameDetail,
  GameOut,
  GamesQuery,
  JobQueued,
  MistakeOut,
  MistakesQuery,
  PuzzleOut,
  QueueFilters,
  QueueOut,
  ReviewIn,
  ReviewOut,
  SessionIn,
  SessionOut,
  Settings,
  StatusOut,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

type Params = Record<string, string | number | boolean | undefined | null>;

export function qs(params: Params): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (body && body.detail !== undefined)
        detail =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail);
    } catch {
      /* corpo não é JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const post = (path: string, body?: unknown): RequestInit => ({
  method: "POST",
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  status: () => request<StatusOut>("/status"),
  dashboard: () => request<DashboardOut>("/dashboard"),
  settings: () => request<Settings>("/settings"),
  saveSettings: (body: Partial<Settings>) =>
    request<Settings>("/settings", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  importGames: () =>
    request<JobQueued>("/import", post("/import")),
  analyze: (p: { limit?: number; game_id?: string } = {}) =>
    request<JobQueued>(`/analyze${qs(p as Params)}`, post("/analyze")),
  regenerate: () =>
    request<JobQueued>("/puzzles/regenerate", post("/puzzles/regenerate")),
  cancelJob: () =>
    request<{ cancelled: boolean }>("/jobs/cancel", post("/jobs/cancel")),
  games: (p: GamesQuery = {}) =>
    request<GameOut[]>(`/games${qs(p as Params)}`),
  game: (id: string) => request<GameDetail>(`/games/${id}`),
  mistakes: (p: MistakesQuery = {}) =>
    request<MistakeOut[]>(`/mistakes${qs(p as Params)}`),
  puzzle: (id: string) => request<PuzzleOut>(`/puzzles/${id}`),
  queue: (p: QueueFilters = {}) =>
    request<QueueOut>(`/queue${qs(p as Params)}`),
  leeches: () => request<PuzzleOut[]>("/leeches"),
  unleech: (id: string) =>
    request<PuzzleOut>(`/puzzles/${id}/unleech`, post("")),
  createSession: (body: SessionIn) =>
    request<SessionOut>("/sessions", post("", body)),
  endSession: (id: string) =>
    request<SessionOut>(`/sessions/${id}/end`, post("")),
  review: (body: ReviewIn) =>
    request<ReviewOut>("/reviews", post("", body)),
};
