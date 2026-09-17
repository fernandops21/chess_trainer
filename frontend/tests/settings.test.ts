import { validate } from "../src/pages/SettingsPage";

const ok = { chesscom_username: "x", categories: ["rapid"], stockfish_path: "", analysis_depth: 18, puzzle_depth: 20,
  mistake_threshold_cp: 100, blunder_threshold_cp: 200, avoid_gap_cp: 150, unique_gap_cp: 150, new_per_day: 10, new_order: "random" as const, leech_lapses: 5,
  analysis_seconds: 15, puzzle_search_seconds: 20,
  tactics_rating: 1500, tactics_window: 300, lichess_min_plays: 100, lichess_min_popularity: 80,
  classify_moves: true, refute_wrong_moves: true, lichess_token_set: false,
  anthropic_api_key_set: false, coach_model: "claude-opus-5" as const, coach_effort: "high" as const,
  langfuse_public_key: "", langfuse_secret_key_set: false, langfuse_host: "",
  golpes_enabled: true, golpes_bloco: 5, golpes_faixa_abaixo: 100, golpes_faixa_acima: 500 };

test("validate", () => {
  expect(validate(ok)).toEqual([]);
  expect(validate({ ...ok, puzzle_depth: 40 })).toHaveLength(1);
  expect(validate({ ...ok, blunder_threshold_cp: 90 })).toContain("blunder deve ser ≥ mistake");
  expect(validate({ ...ok, chesscom_username: " " })).toContain("informe o usuário do chess.com");
});

test("validate: campos das táticas", () => {
  expect(validate({ ...ok, tactics_window: 49 })).toContain("janela de rating mínima é 50");
  expect(validate({ ...ok, tactics_window: 50 })).toEqual([]);
  expect(validate({ ...ok, tactics_rating: 399 })).toContain("rating de táticas entre 400 e 3200");
  expect(validate({ ...ok, tactics_rating: 3201 })).toContain("rating de táticas entre 400 e 3200");
  expect(validate({ ...ok, lichess_min_popularity: -101 })).toContain("popularidade entre -100 e 100");
  expect(validate({ ...ok, lichess_min_popularity: 101 })).toContain("popularidade entre -100 e 100");
  expect(validate({ ...ok, lichess_min_popularity: -100 })).toEqual([]);
  expect(validate({ ...ok, lichess_min_plays: -1 })).toContain("mínimo de partidas não pode ser negativo");
  expect(validate({ ...ok, lichess_min_plays: 0 })).toEqual([]);
});

test("validate: bloco de irmãos dos golpes", () => {
  expect(validate({ ...ok, golpes_bloco: 2 })).toContain("Irmãos por bloco: entre 3 e 10");
  expect(validate({ ...ok, golpes_bloco: 11 })).toContain("Irmãos por bloco: entre 3 e 10");
  expect(validate({ ...ok, golpes_bloco: 3 })).toEqual([]);
  expect(validate({ ...ok, golpes_bloco: 10 })).toEqual([]);
});

test("validate: faixa do bloco dos golpes", () => {
  expect(validate({ ...ok, golpes_faixa_abaixo: -1 })).toContain("Faixa do bloco (abaixo): entre 0 e 1000");
  expect(validate({ ...ok, golpes_faixa_abaixo: 1001 })).toContain("Faixa do bloco (abaixo): entre 0 e 1000");
  expect(validate({ ...ok, golpes_faixa_abaixo: 0 })).toEqual([]);
  expect(validate({ ...ok, golpes_faixa_abaixo: 1000 })).toEqual([]);
  expect(validate({ ...ok, golpes_faixa_acima: -1 })).toContain("Faixa do bloco (acima): entre 0 e 2000");
  expect(validate({ ...ok, golpes_faixa_acima: 2001 })).toContain("Faixa do bloco (acima): entre 0 e 2000");
  expect(validate({ ...ok, golpes_faixa_acima: 0 })).toEqual([]);
  expect(validate({ ...ok, golpes_faixa_acima: 2000 })).toEqual([]);
});
