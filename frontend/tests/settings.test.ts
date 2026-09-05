import { validate } from "../src/pages/SettingsPage";

const ok = { chesscom_username: "x", categories: ["rapid"], stockfish_path: "", analysis_depth: 18, puzzle_depth: 20,
  mistake_threshold_cp: 100, blunder_threshold_cp: 200, avoid_gap_cp: 150, new_per_day: 10, leech_lapses: 5,
  analysis_seconds: 15, puzzle_search_seconds: 20, puzzle_reply_seconds: 10,
  tactics_rating: 1500, tactics_window: 300, lichess_min_plays: 100, lichess_min_popularity: 80 };

test("validate", () => {
  expect(validate(ok)).toEqual([]);
  expect(validate({ ...ok, puzzle_depth: 40 })).toHaveLength(1);
  expect(validate({ ...ok, blunder_threshold_cp: 90 })).toContain("blunder deve ser ≥ mistake");
  expect(validate({ ...ok, chesscom_username: " " })).toContain("informe o usuário do chess.com");
});
