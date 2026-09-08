import type { Settings } from "../../src/api/types";

/** Configurações completas para os testes que só precisam de um `Settings` válido
 *  (evita dublês parciais com `as never`, que escondem campos novos do tipo). */
export const SETTINGS: Settings = {
  chesscom_username: "eu", categories: ["rapid"], stockfish_path: "", analysis_depth: 18, puzzle_depth: 20,
  mistake_threshold_cp: 100, blunder_threshold_cp: 200, avoid_gap_cp: 150, new_per_day: 10, new_order: "random", leech_lapses: 5,
  analysis_seconds: 15, puzzle_search_seconds: 20,
  tactics_rating: 1200, tactics_window: 150, lichess_min_plays: 2000, lichess_min_popularity: 90,
  classify_moves: true, refute_wrong_moves: true, lichess_token_set: false,
};
