export type Color = "white" | "black";
export type PuzzleKind = "punish" | "avoid";
export type MistakeLevel = "mistake" | "blunder";

export interface Settings {
  chesscom_username: string;
  categories: string[];
  stockfish_path: string;
  analysis_depth: number;
  puzzle_depth: number;
  mistake_threshold_cp: number;
  blunder_threshold_cp: number;
  avoid_gap_cp: number;
  new_per_day: number;
  leech_lapses: number;
  analysis_seconds: number;
  puzzle_search_seconds: number;
  puzzle_reply_seconds: number;
}

export interface JobStatus {
  state: "idle" | "running" | "error";
  job: string | null;
  stage: string;
  done: number;
  total: number;
  message: string;
  error: string | null;
  finished_at: string | null;
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

export interface Solution {
  moves: SolutionMove[];
  explanation_pv: string[];
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

export interface MistakeRef {
  ply: number;
  move_played: string;
  move_uci: string;
  eval_before: number;
  eval_after: number;
  mistake_level: MistakeLevel | null;
  mistake_by: "me" | "opponent" | null;
}

export interface PuzzleSibling {
  id: string;
  kind: PuzzleKind;
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
  game: GameRef;
  ply: number;
  move_played: string;
  mistake: MistakeRef;
  siblings: PuzzleSibling[];
}

export interface QueueFilters {
  category?: string;
  theme?: string;
  kind?: PuzzleKind;
  color?: Color;
}

export interface QueueOut {
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
