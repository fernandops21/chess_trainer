// A árvore de lances é definida junto das funções que a manipulam
// (`analysis/moveTree.ts`); aqui ela só entra no contrato do capítulo.
// O `import type` é apagado na compilação: não há ciclo em tempo de execução.
import type { Tree, TreeNode, TreeRoot } from "../analysis/moveTree";
export type { Tree, TreeNode, TreeRoot };

export type Color = "white" | "black";
export type PuzzleKind = "punish" | "avoid";
export type MistakeLevel = "mistake" | "blunder";
/** De onde veio o exercício: erro de partida própria, tática guardada do Lichess ou capítulo de estudo. */
export type PuzzleSource = "own" | "lichess" | "study";
/** Modo da fila: revisar o que venceu, fazer novos ou treinar um estudo inteiro. */
export type QueueMode = "review" | "new" | "study";
/** Ordem dos novos: sorteada ou partida mais recente primeiro. */
export type NewOrder = "random" | "recent";

export interface Settings {
  chesscom_username: string;
  categories: string[];
  stockfish_path: string;
  analysis_depth: number;
  puzzle_depth: number;
  mistake_threshold_cp: number;
  blunder_threshold_cp: number;
  avoid_gap_cp: number;
  /** Lance único: distância mínima da melhor linha para a segunda enquanto o exercício continua. */
  unique_gap_cp: number;
  new_per_day: number;
  /** Ordem dos exercícios novos: sorteados ou pela partida mais recente. */
  new_order: NewOrder;
  leech_lapses: number;
  analysis_seconds: number;
  puzzle_search_seconds: number;
  tactics_rating: number;
  tactics_window: number;
  lichess_min_plays: number;
  lichess_min_popularity: number;
  /** Classificar automaticamente os lances na Análise (usa a engine). */
  classify_moves: boolean;
  /** Ao errar no treino, mostra a réplica da engine e a queda de avaliação. */
  refute_wrong_moves: boolean;
  /** Só diz se há um token do Lichess guardado: o valor nunca sai da API. */
  lichess_token_set: boolean;
  /** Só diz se há uma chave da Anthropic guardada: o valor nunca sai da API. */
  anthropic_api_key_set: boolean;
  coach_model: "claude-opus-5" | "claude-sonnet-5";
  coach_effort: "low" | "medium" | "high";
  langfuse_public_key: string;
  /** Só diz se há uma chave secreta do LangFuse guardada: o valor nunca sai da API. */
  langfuse_secret_key_set: boolean;
  langfuse_host: string;
}

/**
 * Corpo do `PUT /api/settings`. Os segredos viajam à parte porque não voltam no
 * `GET`: mandar o campo ausente mantém o que está guardado, `""` apaga.
 */
export type SettingsIn = Omit<Partial<Settings>, "lichess_token_set" | "anthropic_api_key_set" | "langfuse_secret_key_set"> & {
  lichess_token?: string;
  anthropic_api_key?: string;
  langfuse_secret_key?: string;
};

export interface JobStatus {
  state: "idle" | "running" | "error";
  job: string | null;
  stage: string;
  done: number;
  total: number;
  message: string;
  error: string | null;
  finished_at: string | null;
  cancel_requested: boolean;
}

export interface StatusOut {
  engine: { available: boolean; path: string | null };
  job: JobStatus;
  games_total: number;
  games_pending: number;
  last_import_at: string | null;
  local_url: string;
}

export interface DashboardOut {
  due_today: number;
  new_available: number;
  new_remaining_today: number;
  streak_days: number;
  reviews_today: number;
  last_import_at: string | null;
  games_total: number;
  games_analyzed: number;
  puzzles_total: number;
  leeches: number;
  /** Contagem por fonte; ausente em respostas antigas. */
  by_source?: Partial<Record<PuzzleSource, SourceCount>>;
}

export interface SourceCount {
  in_queue: number;
  due: number;
}

export interface GameOut {
  id: string;
  source_id: string;
  white: string;
  black: string;
  result: string;
  time_control: string;
  category: string;
  played_at: string;
  my_color: Color;
  analyzed_at: string | null;
  my_mistakes: number;
}

export interface PositionOut {
  id: string;
  ply: number;
  fen: string;
  move_played: string;
  move_uci: string;
  eval_before: number;
  eval_after: number;
  best_move: string | null;
  is_mistake: boolean;
  mistake_level: MistakeLevel | null;
  mistake_by: "me" | "opponent" | null;
  puzzle_ids: string[];
}

export interface GameDetail extends GameOut {
  pgn: string;
  positions: PositionOut[];
}

export interface PuzzleRef {
  id: string;
  kind: PuzzleKind;
  theme: string;
  is_leech: boolean;
  /** `false` = fora da repetição (o puzzle continua, só não é servido). */
  in_queue?: boolean;
}

export interface MistakeOut {
  position_id: string;
  game_id: string;
  ply: number;
  fen: string;
  move_played: string;
  move_uci: string;
  best_move: string | null;
  eval_before: number;
  eval_after: number;
  mistake_level: MistakeLevel;
  mistake_by: "me" | "opponent";
  category: string;
  played_at: string;
  white: string;
  black: string;
  my_color: Color;
  puzzles: PuzzleRef[];
}

export interface SolutionMove {
  uci: string;
  by: "solver" | "engine";
  alternatives: string[];
}

/** Seta (`orig` + `dest`) ou casa destacada (`orig` só) desenhada pelo autor do estudo. */
export interface Shape {
  orig: string;
  dest?: string;
  brush: string;
}

export interface Solution {
  moves: SolutionMove[];
  explanation_pv: string[];
  /** Lances errados previstos pelo autor: UCI -> comentário dele. */
  wrong_moves?: Record<string, string>;
  /** Comentários da linha principal: índice do lance (como texto) -> comentário. */
  comments?: Record<string, string>;
  /** Setas e casas do autor: índice do lance ou "start" para a posição inicial. */
  shapes?: Record<string, Shape[]>;
  /** Enunciado do capítulo (comentário antes do primeiro lance). */
  intro?: string;
}

export interface SrsOut {
  ease: number;
  interval_days: number;
  lapses: number;
  due_at: string | null;
  last_reviewed_at: string | null;
}

export interface GameRef {
  id: string;
  white: string;
  black: string;
  played_at: string;
  source_id: string;
  my_color: Color;
}

/** O que você respondeu na partida ao erro do adversário (o ply seguinte ao dele). */
export interface MyReplyInfo {
  ply: number;
  move_played: string;
  move_uci: string;
  eval_before: number;
  eval_after: number;
}

export interface MistakeRef {
  ply: number;
  move_played: string;
  move_uci: string;
  eval_before: number;
  eval_after: number;
  mistake_level: MistakeLevel | null;
  mistake_by: "me" | "opponent" | null;
  /** Só nos "punir": nulo no "evitar" e quando o erro foi o último lance da partida. */
  my_reply?: MyReplyInfo | null;
}

export interface PuzzleSibling {
  id: string;
  kind: PuzzleKind;
}

export interface StudyRef {
  id: string;
  title: string;
  chapter_id: string;
  chapter_name: string;
  lichess_url: string | null;
}

export interface PuzzleOut {
  id: string;
  kind: PuzzleKind;
  fen_start: string;
  side_to_move: Color;
  solution: Solution;
  end_reason: "mate" | "material_gain" | "explanation";
  theme: string;
  category: string;
  solver_moves: number;
  is_leech: boolean;
  srs: SrsOut;
  source: PuzzleSource;
  in_queue: boolean;
  /** Posição antes do último lance do adversário e o lance em si (UCI); nulos quando a fonte não guarda. */
  fen_before: string | null;
  last_move: string | null;
  /** Partida, erro e estudo dependem da fonte: fora de `own` não há partida. */
  game: GameRef | null;
  ply: number | null;
  move_played: string | null;
  mistake: MistakeRef | null;
  study: StudyRef | null;
  siblings: PuzzleSibling[];
}

/** Tática do banco do Lichess: mesmo formato de treino dos puzzles próprios,
 *  sem SRS/partida e com rating/temas do Lichess. */
export interface TacticOut {
  id: string;
  kind: "tactic";
  fen_start: string;
  side_to_move: Color;
  solution: Solution;
  end_reason: "mate" | "material_gain";
  theme: string;
  themes: string[];
  category: "lichess";
  rating: number;
  solver_moves: number;
  lichess_url: string;
  /** Posição de antes do lance do adversário e o lance em si: ligam a introdução animada. */
  fen_before?: string;
  last_move?: string;
  popularity: number;
  nb_plays: number;
  opening_tags: string[];
  /** Já guardada como exercício da repetição (e ainda na fila). */
  saved: boolean;
}

/** O que o motor de treino sabe resolver: puzzle próprio ou tática do Lichess. */
export type Trainable = PuzzleOut | TacticOut;

export interface AttemptIn {
  puzzle_id: string;
  session_id?: string | null;
  correct: boolean;
  used_hint?: boolean;
  duration_ms?: number;
}

export interface AttemptOut {
  id: string;
  puzzle_id: string;
  correct: boolean;
  used_hint: boolean;
  rating_before: number;
  rating_after: number;
  delta: number;
  puzzle_rating: number;
}

/** Corpo opcional de `POST /api/tactics/{id}/save`: com o resultado, a tática
 *  guardada já entra agendada (a tentativa vale como primeira revisão). */
export interface SaveTacticIn {
  correct: boolean;
  used_hint?: boolean;
  duration_ms?: number;
  session_id?: string | null;
}

export interface TacticsStatus {
  imported: boolean;
  count: number;
  imported_at: string | null;
  source_rows: number | null;
  rating: number;
  window: number;
  attempts_total: number;
  attempts_today: number;
  attempts_30d: number;
  correct_30d: number;
}

export interface ThemeCount {
  theme: string;
  label: string;
  count: number;
}

export interface ThemeStat {
  theme: string;
  label: string;
  attempts: number;
  correct: number;
  accuracy: number;
  own: number;
  lichess: number;
}

export interface DayReviews {
  /** Dia local no formato "AAAA-MM-DD"; dias sem revisão não vêm na lista. */
  day: string;
  correct: number;
  wrong: number;
}

export interface RatingPoint {
  at: string;
  rating: number;
}

export interface SourceReviews {
  reviews: number;
  correct: number;
}

export interface ProgressTotals {
  reviews: number;
  correct: number;
  puzzles_in_queue: number;
}

export interface ProgressOut {
  reviews_per_day: DayReviews[];
  /** Um ponto por tentativa de tática, em ordem cronológica. */
  tactics_rating: RatingPoint[];
  by_source: Partial<Record<PuzzleSource, SourceReviews>>;
  streak_days: number;
  totals: ProgressTotals;
}

export interface QueueFilters {
  /** Ausente = `review` (a repetição espaçada). */
  mode?: QueueMode;
  category?: string;
  theme?: string;
  kind?: PuzzleKind;
  color?: Color;
  /** Fontes aceitas; vazio ou ausente = todas. */
  sources?: PuzzleSource[];
  study_id?: string;
  /** Só as contagens: a resposta vem com `items` vazio (`count_only=1` na query). */
  count_only?: boolean;
  /** Só no modo `new`: serve tudo o que há de novo, sem descontar o limite diário. */
  ignore_limit?: boolean;
}

export interface QueueOut {
  mode: QueueMode;
  due_count: number;
  new_available: number;
  new_remaining_today: number;
  items: PuzzleOut[];
}

export interface SessionIn {
  planned_minutes?: number | null;
  filters?: Record<string, unknown>;
}

export interface SessionOut {
  id: string;
  started_at: string;
  ended_at: string | null;
  planned_minutes: number | null;
  filters: Record<string, unknown>;
  reviews: number;
  correct: number;
  total_duration_ms: number;
}

export interface ReviewIn {
  puzzle_id: string;
  session_id?: string | null;
  correct: boolean;
  used_hint?: boolean;
  duration_ms?: number;
}

export interface ReviewOut {
  id: string;
  puzzle_id: string;
  result: "correct" | "wrong";
  used_hint: boolean;
  ease: number;
  interval_days: number;
  due_at: string;
  lapses: number;
  is_leech: boolean;
}

export interface JobQueued {
  queued: boolean;
  job: string;
}

export interface StudyOut {
  id: string;
  title: string;
  author: string;
  source_url: string;
  lichess_id: string | null;
  imported_at: string | null;
  chapter_count: number;
  /** Capítulos com exercício, estejam eles na repetição ou não. */
  exercise_count: number;
  in_queue: number;
  due_today: number;
  /** Importado do Lichess ou criado aqui; ausente nas respostas anteriores ao editor. */
  origin?: "lichess" | "local";
  updated_at?: string | null;
}

export interface ChapterOut {
  id: string;
  order: number;
  name: string;
  lichess_url: string | null;
  mode: "gamebook" | "read";
  in_queue: boolean;
  puzzle_id: string | null;
  intro_comment: string;
  /** Nulo nos capítulos importados antes do editor. */
  updated_at: string | null;
}

/** Capítulo com a árvore: o que o editor carrega e salva. */
export interface ChapterDetail extends ChapterOut {
  fen: string;
  orientation: Color;
  tree: Tree;
  pgn: string;
}

/** Criação do capítulo: sem árvore ainda (posição inicial e modo). */
export interface ChapterIn {
  name: string;
  fen?: string;
  orientation?: Color;
  mode?: ChapterOut["mode"];
}

/** Salvamento do capítulo: o servidor valida a árvore, gera o PGN e o exercício. */
export interface ChapterSaveIn {
  name: string;
  mode: ChapterOut["mode"];
  orientation: Color;
  tree: Tree;
}

export interface StudyIn {
  title: string;
  author: string;
}

export interface StudyUpdateIn {
  title?: string;
  author?: string;
  chapter_order?: string[];
}

export interface StudyDetail extends StudyOut {
  chapters: ChapterOut[];
}

export interface StudyImportIn {
  url?: string;
  pgn?: string;
  /** Título escolhido na importação (o nome do arquivo PGN); vence o do PGN. */
  title?: string;
}

export interface GamesQuery {
  category?: string;
  color?: Color;
  result?: string;
  analyzed?: boolean;
  limit?: number;
  offset?: number;
}

export interface MistakesQuery {
  level?: MistakeLevel;
  theme?: string;
  category?: string;
  by?: "me" | "opponent" | "all";
  limit?: number;
}

export interface AnalyseLine {
  move: string;
  san: string;
  score: number;
  pv: string[];
  pv_san: string[];
}

export interface AnalyseOut {
  fen: string;
  turn: Color;
  terminal: string | null;
  lines: AnalyseLine[];
}

/** Base do livro de aberturas: partidas de mestres ou de jogadores do Lichess. */
export type OpeningsDb = "masters" | "lichess";

export interface OpeningMove {
  uci: string;
  san: string;
  games: number;
  white: number;
  draws: number;
  black: number;
  avg_rating: number | null;
}

export interface OpeningsOut {
  opening: { eco: string; name: string } | null;
  total: number;
  white: number;
  draws: number;
  black: number;
  moves: OpeningMove[];
}

/**
 * Estado do treinador com IA. Em desenvolvimento: `enabled` só vem verdadeiro com o
 * servidor iniciado com CHESS_TRAINER_COACH=1; desligado, nada dele aparece (nem em
 * Configurações). Ligado, o cartão ainda depende de `configured` (chave da API).
 */
export interface CoachStatus {
  enabled: boolean;
  configured: boolean;
  model: string;
  effort: string;
  embeddings_ready: boolean;
  index_chunks: number;
  index_model: string;
  index_stale: number;
  vector_backend: string;
  langfuse_configured: boolean;
}

/** Trecho de estudo citado pela explicação, com o link do lance no capítulo. */
export interface Citacao {
  chunk_id: string;
  study_id: string;
  estudo: string;
  chapter_id: string;
  capitulo: string;
  node_id: string | null;
  caminho_san: string;
  texto: string;
  url: string;
}

/** Um problema que o verificador (engine) achou na explicação. */
export interface IssueOut {
  tipo: string;
  gravidade: "erro" | "aviso";
  detalhe: string;
  linha_idx: number | null;
}

/** A explicação do erro escrita pelo treinador, já passada pelo verificador. */
export interface CoachExplanation {
  id: string;
  puzzle_id: string;
  created_at: string;
  model: string;
  prompt_version: string;
  /** Prosa derivada dos blocos; explicação gravada antes deles só tem isto. */
  text: string;
  /** Blocos da resposta. Opcionais: um backend anterior a eles não os manda. */
  na_partida?: string | null;
  por_que?: string | null;
  padrao?: string | null;
  treinar?: string[];
  lines: unknown[];
  citations: Citacao[];
  verification: { ok: boolean; issues: IssueOut[] };
  status: "ok" | "warnings" | "errors";
  repaired: boolean;
  cost_usd: number;
  tokens: { input: number; output: number; cache_read: number; cache_write: number };
  duration_ms: number;
  trace_url: string | null;
}
