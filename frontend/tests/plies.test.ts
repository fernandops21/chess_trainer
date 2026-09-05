import { buildPlies } from "../src/lib/plies";
import type { GameDetail } from "../src/api/types";

const base: GameDetail = {
  id: "g", source_id: "s", white: "a", black: "b", result: "1-0", time_control: "600", category: "rapid",
  played_at: "2026-09-04T12:00:00", my_color: "white", analyzed_at: null, my_mistakes: 0,
  pgn: '[Event "x"]\n[Result "1-0"]\n\n1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0', positions: [],
};

test("deriva plies do PGN quando não analisada", () => {
  const plies = buildPlies(base);
  expect(plies).toHaveLength(7);
  expect(plies[0]).toMatchObject({ ply: 1, san: "e4", lastMove: ["e2", "e4"] });
  expect(plies[6].san).toBe("Qxf7#");
  expect(plies[6].evalAfter).toBeUndefined();
});

test("usa positions quando analisada", () => {
  const analyzed: GameDetail = { ...base, analyzed_at: "2026-09-04T13:00:00", positions: [
    { id: "p1", ply: 1, fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", move_played: "e4", move_uci: "e2e4", eval_before: 30, eval_after: 25, best_move: "e2e4", is_mistake: false, mistake_level: null, mistake_by: null, puzzle_ids: [] },
    { id: "p2", ply: 2, fen: "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1", move_played: "e5", move_uci: "e7e5", eval_before: -25, eval_after: -300, best_move: "c7c5", is_mistake: true, mistake_level: "blunder", mistake_by: "opponent", puzzle_ids: ["z"] },
  ] };
  const plies = buildPlies(analyzed);
  expect(plies).toHaveLength(2);
  expect(plies[1]).toMatchObject({ san: "e5", level: "blunder", by: "opponent", bestMove: "c7c5", puzzleIds: ["z"], evalAfter: -300 });
  expect(plies[1].fenAfter.split(" ")[1]).toBe("w");
});

test("deriva plies de PGN com comentários de relógio (chess.com)", () => {
  const withClock: GameDetail = {
    ...base,
    pgn: '[Event "x"]\n[Result "1-0"]\n[Link "https://www.chess.com/game/live/123"]\n\n1. e4 {[%clk 0:09:58.3]} e5 {[%clk 0:09:55.1]} 2. Qh5 {[%clk 0:09:50.0]} Nc6 {[%clk 0:09:45.2]} 3. Bc4 {[%clk 0:09:40.0]} Nf6 {[%clk 0:09:35.0]} 4. Qxf7# {[%clk 0:09:30.0]} 1-0',
  };
  const plies = buildPlies(withClock);
  expect(plies).toHaveLength(7);
  expect(plies[0]).toMatchObject({ ply: 1, san: "e4", lastMove: ["e2", "e4"] });
  expect(plies[6].san).toBe("Qxf7#");
});
