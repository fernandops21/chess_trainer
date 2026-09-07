import type {
  AnalyseOut,
  AttemptIn,
  AttemptOut,
  ChapterDetail,
  ChapterIn,
  ChapterSaveIn,
  DashboardOut,
  GameDetail,
  GameOut,
  GamesQuery,
  JobQueued,
  MistakeOut,
  MistakesQuery,
  OpeningsDb,
  OpeningsOut,
  PuzzleOut,
  QueueFilters,
  QueueOut,
  ReviewIn,
  ReviewOut,
  SessionIn,
  SessionOut,
  Settings,
  SettingsIn,
  StatusOut,
  StudyDetail,
  StudyImportIn,
  StudyIn,
  StudyOut,
  StudyUpdateIn,
  TacticOut,
  TacticsStatus,
  ThemeCount,
  ThemeStat,
} from "./types";

export class ApiError extends Error {
  /**
   * @param details Mensagens do servidor quando o `detail` vem em lista (o
   *   editor de capítulo devolve uma por problema encontrado na árvore).
   */
  constructor(public status: number, message: string, public details?: string[]) {
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

function listaDeTextos(valor: unknown): valor is string[] {
  return Array.isArray(valor) && valor.length > 0 && valor.every((x) => typeof x === "string");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`;
    let lista: string[] | undefined;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (body && body.detail !== undefined) {
        if (typeof body.detail === "string") {
          detail = body.detail;
        } else if (listaDeTextos(body.detail)) {
          // 422 do editor: uma mensagem por problema da árvore
          lista = body.detail;
          detail = body.detail.join("; ");
        } else {
          detail = JSON.stringify(body.detail);
        }
      }
    } catch {
      /* corpo não é JSON */
    }
    throw new ApiError(res.status, detail, lista);
  }
  // 204 (DELETE) não tem corpo: `res.json()` lançaria
  if (res.status === 204) return undefined as T;
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
  saveSettings: (body: SettingsIn) =>
    request<Settings>("/settings", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  importGames: () =>
    request<JobQueued>("/import", post("/import")),
  analyze: (p: { limit?: number; game_id?: string } = {}) =>
    request<JobQueued>(`/analyze${qs(p as Params)}`, post("/analyze")),
  regenerate: (kind?: "avoid") =>
    request<JobQueued>(`/puzzles/regenerate${qs({ kind })}`, post("/puzzles/regenerate")),
  cancelJob: () =>
    request<{ cancelled: boolean }>("/jobs/cancel", post("/jobs/cancel")),
  games: (p: GamesQuery = {}) =>
    request<GameOut[]>(`/games${qs(p as Params)}`),
  game: (id: string) => request<GameDetail>(`/games/${id}`),
  mistakes: (p: MistakesQuery = {}) =>
    request<MistakeOut[]>(`/mistakes${qs(p as Params)}`),
  puzzle: (id: string) => request<PuzzleOut>(`/puzzles/${id}`),
  queue: (p: QueueFilters = {}) =>
    request<QueueOut>(`/queue${qs({
      category: p.category, theme: p.theme, kind: p.kind, color: p.color,
      sources: p.sources?.join(","), study_id: p.study_id,
    })}`),
  setQueue: (id: string, in_queue: boolean) =>
    request<PuzzleOut>(`/puzzles/${id}/queue`, post("", { in_queue })),
  leeches: () => request<PuzzleOut[]>("/leeches"),
  unleech: (id: string) =>
    request<PuzzleOut>(`/puzzles/${id}/unleech`, post("")),
  createSession: (body: SessionIn) =>
    request<SessionOut>("/sessions", post("", body)),
  endSession: (id: string) =>
    request<SessionOut>(`/sessions/${id}/end`, post("")),
  review: (body: ReviewIn) =>
    request<ReviewOut>("/reviews", post("", body)),
  analyse: (fen: string, multipv = 3) =>
    request<AnalyseOut>("/analyse", post("/analyse", { fen, multipv })),
  /** Livro de aberturas da posição (proxy do explorador do Lichess). */
  openings: (fen: string, db: OpeningsDb = "masters") =>
    request<OpeningsOut>(`/openings${qs({ fen, db })}`),
  tacticsStatus: () => request<TacticsStatus>("/tactics/status"),
  importTactics: () =>
    request<JobQueued>("/tactics/import", post("/tactics/import")),
  nextTactic: (p: { themes?: string[]; exclude?: string[] } = {}) =>
    request<TacticOut>(
      `/tactics/next${qs({ themes: p.themes?.join(","), exclude: p.exclude?.join(",") })}`,
    ),
  attempt: (body: AttemptIn) =>
    request<AttemptOut>("/tactics/attempts", post("", body)),
  saveTactic: (lichessId: string) =>
    request<PuzzleOut>(`/tactics/${lichessId}/save`, post("")),
  tacticThemes: () => request<ThemeCount[]>("/tactics/themes"),
  studies: () => request<StudyOut[]>("/studies"),
  study: (id: string) => request<StudyDetail>(`/studies/${id}`),
  importStudy: (body: StudyImportIn) =>
    request<JobQueued>("/studies/import", post("", body)),
  reimportStudy: (id: string) =>
    request<JobQueued>(`/studies/${id}/reimport`, post("")),
  setStudyQueue: (id: string, in_queue: boolean) =>
    request<StudyOut>(`/studies/${id}/queue`, post("", { in_queue })),
  deleteStudy: (id: string) =>
    request<void>(`/studies/${id}`, { method: "DELETE" }),
  createStudy: (body: StudyIn) => request<StudyOut>("/studies", post("", body)),
  updateStudy: (id: string, body: StudyUpdateIn) =>
    request<StudyOut>(`/studies/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  chapter: (id: string, cid: string) =>
    request<ChapterDetail>(`/studies/${id}/chapters/${cid}`),
  createChapter: (id: string, body: ChapterIn) =>
    request<ChapterDetail>(`/studies/${id}/chapters`, post("", body)),
  /** Salva a árvore: o servidor valida os lances, gera o PGN e o exercício. */
  saveChapter: (id: string, cid: string, body: ChapterSaveIn) =>
    request<ChapterDetail>(`/studies/${id}/chapters/${cid}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteChapter: (id: string, cid: string) =>
    request<void>(`/studies/${id}/chapters/${cid}`, { method: "DELETE" }),
  duplicateChapter: (id: string, cid: string) =>
    request<ChapterDetail>(`/studies/${id}/chapters/${cid}/duplicate`, post("")),
  themeStats: (days = 30) =>
    request<ThemeStat[]>(`/stats/themes${qs({ days })}`),
};

/** Downloads de PGN: links comuns, o navegador salva pelo Content-Disposition. */
export const studyPgnUrl = (id: string) => `/api/studies/${id}/pgn`;
export const chapterPgnUrl = (id: string, cid: string) =>
  `/api/studies/${id}/chapters/${cid}/pgn`;
