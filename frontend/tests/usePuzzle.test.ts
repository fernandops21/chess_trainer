import { act, renderHook } from "@testing-library/react";
import type { PuzzleOut, ReviewIn, ReviewOut } from "../src/api/types";
import { usePuzzle, type UsePuzzleOptions } from "../src/train/usePuzzle";

const game = { id: "g", white: "a", black: "b", played_at: "2026-09-04T12:00:00", source_id: "https://x", my_color: "white" as const };
const srs = { ease: 2.5, interval_days: 0, lapses: 0, due_at: null, last_reviewed_at: null };
const mistake = { ply: 10, move_played: "x", move_uci: "e2e4", eval_before: 20, eval_after: -150, mistake_level: "mistake" as const, mistake_by: "me" as const };
const base = { end_reason: "material_gain" as const, theme: "tactic", category: "rapid", is_leech: false, srs, game, ply: 10, move_played: "x", mistake, siblings: [] };

const ONE_MOVE: PuzzleOut = { ...base, id: "p1", kind: "punish", fen_start: "4k3/8/8/3q4/8/2N5/7P/4K3 w - - 0 1", side_to_move: "white", solver_moves: 1,
  solution: { moves: [{ uci: "c3d5", by: "solver", alternatives: ["e1e2"] }], explanation_pv: [] } };
const MATE_IN_2: PuzzleOut = { ...base, id: "p2", kind: "punish", end_reason: "mate", fen_start: "2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 1", side_to_move: "white", solver_moves: 2,
  solution: { moves: [{ uci: "e1e8", by: "solver", alternatives: [] }, { uci: "c8e8", by: "engine", alternatives: [] }, { uci: "a4e8", by: "solver", alternatives: [] }], explanation_pv: [] } };
const PROMO: PuzzleOut = { ...base, id: "p3", kind: "avoid", end_reason: "explanation", fen_start: "8/P6k/8/8/8/8/8/K7 w - - 0 1", side_to_move: "white", solver_moves: 1,
  solution: { moves: [{ uci: "a7a8q", by: "solver", alternatives: [] }], explanation_pv: ["a7a8q", "h7g6"] } };
// Note: the brief's suggested fixture ("k7/PP6/8/8/8/8/8/K7 w - - 0 1" with
// b7b8q expected / a7a8q alternative) has no legal a7 move at all -- a8 is
// occupied by the black king, which blocks the a7-a8 push and isn't a legal
// diagonal-capture target either. Using a fen where both the expected move
// and its alternative are actually legal promotions instead: a7 can push to
// a8 (empty) or capture on b8 (a rook), both promoting.
const PROMO_ALT: PuzzleOut = { ...base, id: "p4", kind: "avoid", end_reason: "explanation", fen_start: "1r4k1/P7/8/8/8/8/8/K7 w - - 0 1", side_to_move: "white", solver_moves: 1,
  solution: { moves: [{ uci: "a7b8q", by: "solver", alternatives: ["a7a8q"] }], explanation_pv: [] } };
const BAD_ALT: PuzzleOut = { ...base, id: "p5", kind: "punish", fen_start: ONE_MOVE.fen_start, side_to_move: "white", solver_moves: 1,
  solution: { moves: [{ uci: "c3d5", by: "solver", alternatives: ["e1e1"] }], explanation_pv: [] } };

function review(over: Partial<ReviewOut> = {}): ReviewOut {
  return { id: "r", puzzle_id: "p", result: "correct", used_hint: false, ease: 2.6, interval_days: 1, due_at: "2026-09-05T12:00:00", lapses: 0, is_leech: false, ...over };
}

function setup(puzzle: PuzzleOut, extra: Partial<UsePuzzleOptions<ReviewOut>> = {}) {
  const submit = vi.fn(async (body: ReviewIn) => review({ used_hint: !!body.used_hint, result: body.correct ? "correct" : "wrong" }));
  let t = 1000;
  const hook = renderHook(() => usePuzzle<ReviewOut>(puzzle, { sessionId: "s1", submit, engineDelayMs: 100, now: () => t, ...extra }));
  return { ...hook, submit, tick: (ms: number) => { t += ms; } };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

test("lance certo conclui, registra e vai para result", async () => {
  const { result, submit, tick } = setup(ONE_MOVE);
  expect(result.current.state.phase).toBe("awaiting_move");
  expect(result.current.dests.get("c3")).toContain("d5");
  tick(4000);
  await act(async () => { result.current.tryMove("c3", "d5"); await Promise.resolve(); });
  expect(result.current.state.phase).toBe("result");
  expect(submit).toHaveBeenCalledWith({ puzzle_id: "p1", session_id: "s1", correct: true, used_hint: false, duration_ms: 4000 });
  expect(result.current.state.review?.result).toBe("correct");
  expect(result.current.dests.size).toBe(0);
});

test("alternativa aceita", async () => {
  const { result, submit } = setup(ONE_MOVE);
  await act(async () => { result.current.tryMove("e1", "e2"); await Promise.resolve(); });
  expect(result.current.state.phase).toBe("result");
  expect(submit).toHaveBeenCalledWith(expect.objectContaining({ correct: true }));
});

test("lance errado é desfeito e marca wrong; puzzle continua", async () => {
  const { result, submit } = setup(ONE_MOVE);
  act(() => result.current.tryMove("e1", "d1"));
  expect(result.current.state.phase).toBe("awaiting_move");
  expect(result.current.state.fen).toBe(ONE_MOVE.fen_start);
  expect(result.current.state.wrong).toBe(true);
  expect(result.current.state.message.tone).toBe("bad");
  await act(async () => { result.current.tryMove("c3", "d5"); await Promise.resolve(); });
  expect(submit).toHaveBeenCalledWith(expect.objectContaining({ correct: false }));
});

test("dica marca usedHint e destaca a origem", async () => {
  const { result, submit } = setup(ONE_MOVE);
  act(() => result.current.useHint());
  expect(result.current.state.usedHint).toBe(true);
  expect(result.current.state.hint).toBe("c3");
  await act(async () => { result.current.tryMove("c3", "d5"); await Promise.resolve(); });
  expect(submit).toHaveBeenCalledWith(expect.objectContaining({ correct: true, used_hint: true }));
});

test("resposta da engine é aplicada após o atraso e o puzzle segue", async () => {
  const { result } = setup(MATE_IN_2);
  act(() => result.current.tryMove("e1", "e8"));
  expect(result.current.state.phase).toBe("engine_replying");
  expect(result.current.dests.size).toBe(0);
  await act(async () => { vi.advanceTimersByTime(100); });
  expect(result.current.state.phase).toBe("awaiting_move");
  expect(result.current.state.idx).toBe(2);
  expect(result.current.state.lastMove).toEqual(["c8", "e8"]);
  await act(async () => { result.current.tryMove("a4", "e8"); await Promise.resolve(); });
  expect(result.current.state.phase).toBe("result");
});

test("promoção pede a peça quando a solução promove", async () => {
  const { result, submit } = setup(PROMO);
  act(() => result.current.tryMove("a7", "a8"));
  expect(result.current.state.pendingPromotion).toEqual({ orig: "a7", dest: "a8" });
  expect(result.current.state.phase).toBe("awaiting_move");
  await act(async () => { result.current.choosePromotion("q"); await Promise.resolve(); });
  expect(result.current.state.phase).toBe("result");
  expect(submit).toHaveBeenCalledWith(expect.objectContaining({ correct: true }));
});

test("promoção errada conta como erro", async () => {
  const { result } = setup(PROMO);
  act(() => result.current.tryMove("a7", "a8"));
  act(() => result.current.choosePromotion("n"));
  expect(result.current.state.wrong).toBe(true);
  expect(result.current.state.pendingPromotion).toBeUndefined();
});

test("falha no envio não avança; retry funciona", async () => {
  const submit = vi.fn().mockRejectedValueOnce(new Error("rede")).mockResolvedValueOnce(review());
  const { result } = renderHook(() => usePuzzle(ONE_MOVE, { sessionId: null, submit, engineDelayMs: 100 }));
  await act(async () => { result.current.tryMove("c3", "d5"); await Promise.resolve(); });
  expect(result.current.state.phase).toBe("submit_error");
  await act(async () => { result.current.retrySubmit(); await Promise.resolve(); });
  expect(result.current.state.phase).toBe("result");
  expect(submit).toHaveBeenCalledTimes(2);
  expect(submit.mock.calls[1][0]).toMatchObject({ session_id: null });
});

test("cancelPromotion limpa a promoção pendente sem enviar", async () => {
  const { result, submit } = setup(PROMO);
  act(() => result.current.tryMove("a7", "a8"));
  expect(result.current.state.pendingPromotion).toEqual({ orig: "a7", dest: "a8" });
  act(() => result.current.cancelPromotion());
  expect(result.current.state.pendingPromotion).toBeUndefined();
  expect(result.current.state.phase).toBe("awaiting_move");
  expect(submit).not.toHaveBeenCalled();
});

test("retrySubmit não reenvia fora de submit_error (ex.: em result)", async () => {
  const { result, submit } = setup(ONE_MOVE);
  await act(async () => { result.current.tryMove("c3", "d5"); await Promise.resolve(); });
  expect(result.current.state.phase).toBe("result");
  expect(submit).toHaveBeenCalledTimes(1);
  act(() => result.current.retrySubmit());
  expect(submit).toHaveBeenCalledTimes(1);
});

test("promoção considera alternativas ao decidir se precisa de peça", async () => {
  const { result, submit } = setup(PROMO_ALT);
  act(() => result.current.tryMove("a7", "a8"));
  expect(result.current.state.pendingPromotion).toEqual({ orig: "a7", dest: "a8" });
  expect(result.current.state.phase).toBe("awaiting_move");
  await act(async () => { result.current.choosePromotion("q"); await Promise.resolve(); });
  expect(result.current.state.phase).toBe("result");
  expect(submit).toHaveBeenCalledWith(expect.objectContaining({ correct: true }));
});

test("alternativa textualmente válida mas ilegal no tabuleiro conta como erro, sem crash", async () => {
  const { result, submit } = setup(BAD_ALT);
  act(() => result.current.tryMove("e1", "e1"));
  expect(result.current.state.phase).toBe("awaiting_move");
  expect(result.current.state.wrong).toBe(true);
  expect(result.current.state.message).toEqual({ text: "Lance inválido", tone: "bad" });
  expect(submit).not.toHaveBeenCalled();
});

test("presetHint começa como dica usada", () => {
  const { result } = setup(ONE_MOVE, { presetHint: true });
  expect(result.current.state.usedHint).toBe(true);
  expect(result.current.state.message.text).toMatch(/Solução já vista/);
});
