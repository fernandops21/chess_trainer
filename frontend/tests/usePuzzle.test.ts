import { act, renderHook } from "@testing-library/react";
import type { AnalyseLine, AnalyseOut, PuzzleOut, ReviewIn, ReviewOut } from "../src/api/types";

// o `play` vira dublê; o resto do módulo de som (sanSound) continua o de verdade
vi.mock("../src/lib/sound", async (original) => ({
  ...(await original<typeof import("../src/lib/sound")>()),
  play: vi.fn(),
}));

import { play } from "../src/lib/sound";
import { usePuzzle, type UsePuzzleOptions } from "../src/train/usePuzzle";

const sons = () => vi.mocked(play).mock.calls.map((c) => c[0]);

const game = { id: "g", white: "a", black: "b", played_at: "2026-09-04T12:00:00", source_id: "https://x", my_color: "white" as const };
const srs = { ease: 2.5, interval_days: 0, lapses: 0, due_at: null, last_reviewed_at: null };
const mistake = { ply: 10, move_played: "x", move_uci: "e2e4", eval_before: 20, eval_after: -150, mistake_level: "mistake" as const, mistake_by: "me" as const };
const base = { end_reason: "material_gain" as const, theme: "tactic", category: "rapid", is_leech: false, srs, game, ply: 10, move_played: "x", mistake, siblings: [],
  source: "own" as const, in_queue: true, fen_before: null, last_move: null, study: null };

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

beforeEach(() => { vi.useFakeTimers(); vi.mocked(play).mockClear(); });
afterEach(() => vi.useRealTimers());

test("lance certo conclui, registra e vai para result", async () => {
  const { result, submit, tick } = setup(ONE_MOVE);
  expect(result.current.state.phase).toBe("awaiting_move");
  expect(result.current.dests.get("c3")).toContain("d5");
  tick(4000);
  await act(async () => { result.current.tryMove("c3", "d5"); await Promise.resolve(); });
  expect(result.current.state.phase).toBe("result");
  expect(result.current.state.played).toEqual(["c3d5"]);
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
  expect(result.current.state.hintStage).toBe(1);
  expect(result.current.state.message).toEqual({ text: "Peça destacada. Clique de novo para jogar o lance (dica conta como erro).", tone: "bad" });
  expect(result.current.state.phase).toBe("awaiting_move");
  await act(async () => { result.current.tryMove("c3", "d5"); await Promise.resolve(); });
  expect(submit).toHaveBeenCalledWith(expect.objectContaining({ correct: true, used_hint: true }));
});

test("segundo clique na dica joga o lance esperado e a engine responde", async () => {
  const { result, submit } = setup(MATE_IN_2);
  expect(result.current.state.hintStage).toBe(0);
  act(() => result.current.useHint());
  expect(result.current.state.hintStage).toBe(1);
  expect(result.current.state.hint).toBe("e1");
  act(() => result.current.useHint());
  expect(result.current.state.phase).toBe("engine_replying");
  expect(result.current.state.lastMove).toEqual(["e1", "e8"]);
  expect(result.current.state.hintStage).toBe(0);
  expect(result.current.state.hint).toBeUndefined();
  await act(async () => { vi.advanceTimersByTime(100); });
  // no lance seguinte a dica volta ao estágio 0 e pode ser usada de novo
  expect(result.current.state.phase).toBe("awaiting_move");
  expect(result.current.state.idx).toBe(2);
  expect(result.current.state.hintStage).toBe(0);
  act(() => result.current.useHint());
  expect(result.current.state.hintStage).toBe(1);
  expect(result.current.state.hint).toBe("a4");
  await act(async () => { result.current.useHint(); await Promise.resolve(); });
  expect(result.current.state.phase).toBe("result");
  expect(submit).toHaveBeenCalledWith(expect.objectContaining({ correct: true, used_hint: true }));
});

test("dica joga a promoção da solução", async () => {
  const { result, submit } = setup(PROMO);
  act(() => result.current.useHint());
  expect(result.current.state.hint).toBe("a7");
  await act(async () => { result.current.useHint(); await Promise.resolve(); });
  expect(result.current.state.phase).toBe("result");
  expect(result.current.state.fen.startsWith("Q7/7k/")).toBe(true);
  expect(result.current.state.pendingPromotion).toBeUndefined();
  expect(submit).toHaveBeenCalledWith(expect.objectContaining({ correct: true, used_hint: true }));
});

test("um lance do usuário também zera o estágio da dica", async () => {
  const { result } = setup(MATE_IN_2);
  act(() => result.current.useHint());
  expect(result.current.state.hintStage).toBe(1);
  act(() => result.current.tryMove("e1", "e8"));
  await act(async () => { vi.advanceTimersByTime(100); });
  expect(result.current.state.phase).toBe("awaiting_move");
  expect(result.current.state.hintStage).toBe(0);
  expect(result.current.state.hint).toBeUndefined();
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

// --- comentários do autor (estudos) -------------------------------------

const AUTHORED: PuzzleOut = { ...base, id: "p6", kind: "punish", source: "study", fen_start: "2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 1", side_to_move: "white", solver_moves: 2,
  solution: {
    moves: [{ uci: "e1e8", by: "solver", alternatives: [] }, { uci: "c8e8", by: "engine", alternatives: [] }, { uci: "a4e8", by: "solver", alternatives: [] }],
    explanation_pv: [],
    wrong_moves: { a4a8: "A dama sozinha não entra: a torre defende a8." },
    comments: { "0": "A torre corta o rei.", "2": "E a dama coleta." },
  } };

test("lance errado previsto pelo autor mostra o comentário dele", () => {
  const { result, submit } = setup(AUTHORED);
  act(() => result.current.tryMove("a4", "a8"));
  expect(result.current.state.phase).toBe("awaiting_move");
  expect(result.current.state.wrong).toBe(true);
  expect(result.current.state.message).toEqual({ text: "A dama sozinha não entra: a torre defende a8.", tone: "bad" });
  expect(submit).not.toHaveBeenCalled();
});

test("lance errado sem comentário do autor mantém a mensagem padrão", () => {
  const { result } = setup(AUTHORED);
  act(() => result.current.tryMove("g1", "h1"));
  expect(result.current.state.message).toEqual({ text: "Não é esse. Tente de novo.", tone: "bad" });
});

test("lance certo com comentário do autor entra no 'Certo!'", async () => {
  const { result } = setup(AUTHORED);
  act(() => result.current.tryMove("e1", "e8"));
  // a âncora é a posição de antes do lance recém-jogado: no comentário, "Te8" vira link
  expect(result.current.state.message).toEqual({ text: "Certo! — A torre corta o rei.", tone: "ok", fen: AUTHORED.fen_start });
  await act(async () => { vi.advanceTimersByTime(100); await Promise.resolve(); });
  expect(result.current.state.phase).toBe("awaiting_move");
  const antesDoUltimo = result.current.state.fen;
  await act(async () => { result.current.tryMove("a4", "e8"); await Promise.resolve(); });
  expect(result.current.state.message).toEqual({ text: "Certo! — E a dama coleta.", tone: "ok", fen: antesDoUltimo });
});

test("sem comentários a mensagem de acerto continua 'Certo!'", async () => {
  const { result } = setup(ONE_MOVE);
  await act(async () => { result.current.tryMove("c3", "d5"); await Promise.resolve(); });
  expect(result.current.state.message).toEqual({ text: "Certo!", tone: "ok", fen: ONE_MOVE.fen_start });
});

// --- último lance do adversário (fase "intro") ---------------------------

const ONE_MOVE_INTRO: PuzzleOut = { ...ONE_MOVE, id: "p6",
  fen_before: "4k3/8/8/8/3q4/2N5/7P/4K3 b - - 0 1", last_move: "d4d5" };
const MATE_IN_2_INTRO: PuzzleOut = { ...MATE_IN_2, id: "p7",
  fen_before: "6k1/2r2ppp/8/8/Q7/8/8/4R1K1 b - - 0 1", last_move: "c7c8" };

test("com último lance do adversário o puzzle abre em `intro`, sem peças liberadas", () => {
  const { result } = setup(MATE_IN_2_INTRO);
  expect(result.current.state.phase).toBe("intro");
  expect(result.current.state.fen).toBe(MATE_IN_2_INTRO.fen_before);
  expect(result.current.state.turn).toBe("black");
  expect(result.current.state.lastMove).toBeUndefined();
  expect(result.current.dests.size).toBe(0);

  // nada do usuário conta durante a introdução
  act(() => result.current.tryMove("e1", "e8"));
  act(() => result.current.useHint());
  expect(result.current.state.phase).toBe("intro");
  expect(result.current.state.idx).toBe(0);
  expect(result.current.state.usedHint).toBe(false);
});

test("passada a introdução, a posição vira a do puzzle com o lance destacado", () => {
  const { result } = setup(MATE_IN_2_INTRO);
  act(() => { vi.advanceTimersByTime(400); });
  expect(result.current.state.phase).toBe("awaiting_move");
  expect(result.current.state.fen).toBe(MATE_IN_2_INTRO.fen_start);
  expect(result.current.state.turn).toBe("white");
  expect(result.current.state.lastMove).toEqual(["c7", "c8"]);
  expect(result.current.dests.get("e1")).toContain("e8");
});

test("a duração enviada não conta a introdução", async () => {
  const { result, submit, tick } = setup(ONE_MOVE_INTRO);
  tick(400);
  act(() => { vi.advanceTimersByTime(400); });
  tick(4000);
  await act(async () => { result.current.tryMove("c3", "d5"); await Promise.resolve(); });
  expect(submit).toHaveBeenCalledWith(expect.objectContaining({ duration_ms: 4000 }));
});

test("sem `last_move` não há introdução", () => {
  const { result } = setup({ ...ONE_MOVE, fen_before: "4k3/8/8/8/3q4/2N5/7P/4K3 b - - 0 1", last_move: null });
  expect(result.current.state.phase).toBe("awaiting_move");
  expect(result.current.state.fen).toBe(ONE_MOVE.fen_start);
});

// --- histórico do exercício ---------------------------------------------

test("sem introdução o histórico começa na posição do exercício e cresce a cada lance", async () => {
  const { result } = setup(MATE_IN_2);
  expect(result.current.history).toEqual([{ fen: MATE_IN_2.fen_start, lastMove: undefined }]);

  act(() => result.current.tryMove("e1", "e8"));
  expect(result.current.history.length).toBe(2);
  expect(result.current.history[1].lastMove).toEqual(["e1", "e8"]);

  await act(async () => { vi.advanceTimersByTime(100); await Promise.resolve(); });
  expect(result.current.history.length).toBe(3);
  expect(result.current.history[2].fen).toBe(result.current.state.fen);
  expect(result.current.history[2].lastMove).toEqual(["c8", "e8"]);
});

test("com introdução o histórico guarda a posição de antes do lance do adversário", () => {
  const { result } = setup(MATE_IN_2_INTRO);
  // durante a introdução nada aconteceu ainda: só a posição de antes
  expect(result.current.history).toEqual([{ fen: MATE_IN_2_INTRO.fen_before }]);

  act(() => { vi.advanceTimersByTime(400); });
  expect(result.current.history).toEqual([
    { fen: MATE_IN_2_INTRO.fen_before },
    { fen: MATE_IN_2_INTRO.fen_start, lastMove: ["c7", "c8"] },
  ]);
});

test("na refutação o histórico termina no lance errado e na réplica", async () => {
  const { result } = setup(ONE_MOVE, { refute: true, analyse: engineDuble() });
  act(() => result.current.tryMove("h2", "h3"));
  expect(result.current.history.map((h) => h.fen)).toEqual([ONE_MOVE.fen_start, FEN_ERRO]);

  await escoar();
  expect(result.current.history.map((h) => h.fen)).toEqual([ONE_MOVE.fen_start, FEN_ERRO, FEN_REPLICA]);
  expect(result.current.history[2].lastMove).toEqual(["d5", "g2"]);

  // "Tentar de novo" tira as duas do histórico
  act(() => result.current.retryMove());
  expect(result.current.history.map((h) => h.fen)).toEqual([ONE_MOVE.fen_start]);
});

// --- sons -----------------------------------------------------------------

test("lance certo com captura toca 'capture' e resolver toca 'solved'", async () => {
  const { result } = setup(ONE_MOVE);
  await act(async () => { result.current.tryMove("c3", "d5"); await Promise.resolve(); });
  expect(sons()).toEqual(["solved"]); // no lance final só a conclusão soa
});

test("lance certo sem captura nem xeque toca 'move'", async () => {
  const { result } = setup(PROMO);
  act(() => result.current.tryMove("a7", "a8"));
  await act(async () => { result.current.choosePromotion("q"); await Promise.resolve(); });
  expect(sons()).toEqual(["solved"]);
});

test("xeque tem prioridade sobre captura, e a resposta da engine também soa", async () => {
  const { result } = setup(MATE_IN_2);
  act(() => result.current.tryMove("e1", "e8"));
  expect(sons()).toEqual(["check"]);
  await act(async () => { vi.advanceTimersByTime(100); });
  expect(sons()).toEqual(["check", "capture"]);
  await act(async () => { result.current.tryMove("a4", "e8"); await Promise.resolve(); });
  expect(sons()).toEqual(["check", "capture", "solved"]);
});

test("lance errado toca 'wrong'", () => {
  const { result } = setup(ONE_MOVE);
  act(() => result.current.tryMove("e1", "d1"));
  expect(sons()).toEqual(["wrong"]);
});

test("alternativa ilegal também toca 'wrong'", () => {
  const { result } = setup(BAD_ALT);
  act(() => result.current.tryMove("e1", "e1"));
  expect(sons()).toEqual(["wrong"]);
});

test("o primeiro estágio da dica toca 'hint'", () => {
  const { result } = setup(MATE_IN_2);
  act(() => result.current.useHint());
  expect(sons()).toEqual(["hint"]);
  // o segundo estágio joga o lance: soa como lance, não como dica
  act(() => result.current.useHint());
  expect(sons()).toEqual(["hint", "check"]);
});

// --- refutação do lance errado -------------------------------------------

// `h2h3` (SAN "h3") é um lance legal e errado em ONE_MOVE; a engine dublê
// responde `d5g2` (SAN "Qg2").
const FEN_ERRO = "4k3/8/8/3q4/8/2N4P/8/4K3 b - - 0 1";
const FEN_REPLICA = "4k3/8/8/8/8/2N4P/6q1/4K3 w - - 1 2";
const LINHA_DEPOIS: AnalyseLine = { move: "d5g2", san: "Qg2", score: 500, pv: ["d5g2"], pv_san: ["Qg2"] };
const LINHA_ANTES: AnalyseLine = { move: "c3d5", san: "Nxd5", score: 900, pv: ["c3d5"], pv_san: ["Nxd5"] };

const analiseOut = (fen: string, lines: AnalyseLine[], terminal: string | null = null): AnalyseOut =>
  ({ fen, turn: fen.split(" ")[1] === "b" ? "black" : "white", terminal, lines });

/** Dublê da engine: uma resposta para a posição de antes do erro e outra para a de depois. */
const engineDuble = (depois = analiseOut(FEN_ERRO, [LINHA_DEPOIS])) =>
  vi.fn(async (fen: string) => (fen === ONE_MOVE.fen_start ? analiseOut(fen, [LINHA_ANTES]) : depois));

/** Deixa as promessas do dublê chegarem ao estado. */
const escoar = async () => { await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); }); };

test("lance errado com refutação entra numa cópia, a engine responde e a avaliação aparece", async () => {
  const analyse = engineDuble();
  const { result } = setup(ONE_MOVE, { refute: true, analyse });
  act(() => result.current.tryMove("h2", "h3"));
  // o lance errado está no tabuleiro, mas não no exercício: a engine ainda pensa
  expect(result.current.state.phase).toBe("refuting");
  expect(result.current.state.fen).toBe(FEN_ERRO);
  expect(result.current.state.wrong).toBe(true);
  expect(result.current.state.lastMove).toEqual(["h2", "h3"]);
  expect(result.current.state.message).toEqual({ text: "h3? Vendo a resposta…", tone: "bad", fen: ONE_MOVE.fen_start });
  expect(result.current.dests.size).toBe(0);

  await escoar();
  expect(result.current.state.phase).toBe("refuted");
  expect(result.current.state.fen).toBe(FEN_REPLICA);
  expect(result.current.state.lastMove).toEqual(["d5", "g2"]);
  expect(result.current.state.refutation).toMatchObject({ wrongSan: "h3", replySan: "Qg2", evalAfter: -500, evalBefore: 900, pvSan: [] });
  // âncora da refutação: a posição de antes do lance errado, para "h3?" e "Qg2" virarem links
  expect(result.current.state.message).toEqual({ text: "h3? Qg2 — avaliação cai de +9.00 para -5.00", tone: "bad", fen: ONE_MOVE.fen_start });
  expect(result.current.dests.size).toBe(0);
  expect(analyse).toHaveBeenCalledTimes(2);
  expect(analyse).toHaveBeenCalledWith(ONE_MOVE.fen_start, 1);
  expect(analyse).toHaveBeenCalledWith(FEN_ERRO, 1);
  expect(sons()).toEqual(["wrong", "move"]);
});

test("'Tentar de novo' devolve o lance do adversário destacado quando o puzzle teve introdução", async () => {
  const { result } = setup(ONE_MOVE_INTRO, { refute: true, analyse: engineDuble() });
  act(() => { vi.advanceTimersByTime(400); });
  expect(result.current.state.lastMove).toEqual(["d4", "d5"]);
  act(() => result.current.tryMove("h2", "h3"));
  await escoar();
  expect(result.current.state.phase).toBe("refuted");
  expect(result.current.state.lastMove).toEqual(["d5", "g2"]);

  act(() => result.current.retryMove());
  expect(result.current.state.phase).toBe("awaiting_move");
  expect(result.current.state.lastMove).toEqual(["d4", "d5"]);
});

test("'Tentar de novo' volta à posição e o lance certo ainda conta como erro", async () => {
  const { result, submit } = setup(ONE_MOVE, { refute: true, analyse: engineDuble() });
  act(() => result.current.tryMove("h2", "h3"));
  await escoar();
  expect(result.current.state.phase).toBe("refuted");

  act(() => result.current.retryMove());
  expect(result.current.state.phase).toBe("awaiting_move");
  expect(result.current.state.fen).toBe(ONE_MOVE.fen_start);
  expect(result.current.state.lastMove).toBeUndefined();
  expect(result.current.state.refutation).toBeUndefined();
  expect(result.current.state.message).toEqual({ text: "Tente de novo.", tone: "bad" });
  expect(result.current.dests.get("c3")).toContain("d5");

  await act(async () => { result.current.tryMove("c3", "d5"); await Promise.resolve(); });
  expect(result.current.state.phase).toBe("result");
  expect(submit).toHaveBeenCalledWith(expect.objectContaining({ correct: false }));
});

test("engine indisponível cai na mensagem de sempre, sem travar o exercício", async () => {
  const analyse = vi.fn(async () => { throw new Error("engine não encontrada"); });
  const { result } = setup(ONE_MOVE, { refute: true, analyse });
  act(() => result.current.tryMove("h2", "h3"));
  expect(result.current.state.phase).toBe("refuting");
  await escoar();
  expect(result.current.state.phase).toBe("awaiting_move");
  expect(result.current.state.fen).toBe(ONE_MOVE.fen_start);
  expect(result.current.state.lastMove).toBeUndefined();
  expect(result.current.state.wrong).toBe(true);
  expect(result.current.state.refutation).toBeUndefined();
  expect(result.current.state.message).toEqual({ text: "Não é esse. Tente de novo.", tone: "bad" });
  expect(result.current.dests.get("c3")).toContain("d5");
});

test("com a refutação desligada nada é pedido à engine", () => {
  const analyse = engineDuble();
  const { result } = setup(ONE_MOVE, { analyse });
  act(() => result.current.useHint());
  expect(result.current.state.hintStage).toBe(1);
  act(() => result.current.tryMove("h2", "h3"));
  expect(analyse).not.toHaveBeenCalled();
  expect(result.current.state.phase).toBe("awaiting_move");
  expect(result.current.state.fen).toBe(ONE_MOVE.fen_start);
  expect(result.current.state.wrong).toBe(true);
  expect(result.current.state.message).toEqual({ text: "Não é esse. Tente de novo.", tone: "bad" });
  // o lance errado zera a dica igual à refutação zera
  expect(result.current.state.hintStage).toBe(0);
  expect(result.current.state.hint).toBeUndefined();
});

test("lance errado que dá mate fica em 'refuted' sem réplica", async () => {
  const analyse = engineDuble(analiseOut(FEN_ERRO, [], "checkmate"));
  const { result } = setup(ONE_MOVE, { refute: true, analyse });
  act(() => result.current.tryMove("h2", "h3"));
  await escoar();
  expect(result.current.state.phase).toBe("refuted");
  expect(result.current.state.fen).toBe(FEN_ERRO);
  expect(result.current.state.refutation?.replySan).toBeUndefined();
  expect(result.current.state.message).toEqual({ text: "h3? — é mate, mas não é a solução do exercício", tone: "bad", fen: ONE_MOVE.fen_start });
  expect(sons()).toEqual(["wrong"]);
});

test("resposta atrasada de uma tentativa anterior não volta ao tabuleiro", async () => {
  const caixa: { responder?: (o: AnalyseOut) => void } = {};
  const analyse = vi.fn((fen: string) => (fen === ONE_MOVE.fen_start
    ? Promise.resolve(analiseOut(fen, [LINHA_ANTES]))
    : new Promise<AnalyseOut>((res) => { caixa.responder = res; })));
  const { result } = setup(ONE_MOVE, { refute: true, analyse });
  act(() => result.current.tryMove("h2", "h3"));
  expect(result.current.state.phase).toBe("refuting");
  act(() => result.current.retryMove());
  expect(result.current.state.phase).toBe("awaiting_move");

  await act(async () => { caixa.responder?.(analiseOut(FEN_ERRO, [LINHA_DEPOIS])); await Promise.resolve(); });
  expect(result.current.state.phase).toBe("awaiting_move");
  expect(result.current.state.fen).toBe(ONE_MOVE.fen_start);
  expect(result.current.state.refutation).toBeUndefined();
  expect(sons()).toEqual(["wrong"]);
});

test("desmontar com a engine pensando não mexe mais no estado", async () => {
  const caixa: { responder?: (o: AnalyseOut) => void } = {};
  const analyse = vi.fn((fen: string) => (fen === ONE_MOVE.fen_start
    ? Promise.resolve(analiseOut(fen, [LINHA_ANTES]))
    : new Promise<AnalyseOut>((res) => { caixa.responder = res; })));
  const { result, unmount } = setup(ONE_MOVE, { refute: true, analyse });
  act(() => result.current.tryMove("h2", "h3"));
  // só a posição depois do erro é pedida de cara; a de antes vem depois da réplica
  expect(analyse).toHaveBeenCalledTimes(1);
  unmount();
  await act(async () => { caixa.responder?.(analiseOut(FEN_ERRO, [LINHA_DEPOIS])); await Promise.resolve(); });
  // a réplica que chegou depois do desmonte não foi aplicada: nem som de lance,
  // nem a pergunta seguinte à engine (o `result` congela em `unmount`, então o
  // guarda de verdade é o que a resposta atrasada deixou de fazer)
  expect(sons()).toEqual(["wrong"]);
  expect(analyse).toHaveBeenCalledTimes(1);
});

// --- casos menos comuns da refutação --------------------------------------

test("a avaliação de antes que chega depois da réplica reescreve a mensagem", async () => {
  const caixa: { responder?: (o: AnalyseOut) => void } = {};
  const analyse = vi.fn((fen: string) => (fen === ONE_MOVE.fen_start
    ? new Promise<AnalyseOut>((res) => { caixa.responder = res; })
    : Promise.resolve(analiseOut(FEN_ERRO, [LINHA_DEPOIS]))));
  const { result } = setup(ONE_MOVE, { refute: true, analyse });
  act(() => result.current.tryMove("h2", "h3"));
  await escoar();
  // sem a avaliação de antes a mensagem sai só com a de agora
  expect(result.current.state.phase).toBe("refuted");
  expect(result.current.state.refutation?.evalBefore).toBeUndefined();
  expect(result.current.state.message.text).toBe("h3? Qg2 — avaliação -5.00");

  await act(async () => { caixa.responder?.(analiseOut(ONE_MOVE.fen_start, [LINHA_ANTES])); await Promise.resolve(); });
  expect(result.current.state.phase).toBe("refuted");
  expect(result.current.state.refutation?.evalBefore).toBe(900);
  expect(result.current.state.message.text).toBe("h3? Qg2 — avaliação cai de +9.00 para -5.00");
});

test("a mensagem junta a continuação da engine e o comentário do autor", async () => {
  const linha: AnalyseLine = { ...LINHA_DEPOIS, pv_san: ["Qg2", "Kf1", "Qxh1", "Ke2", "Qg2", "Ke1", "Qxh2"] };
  const comAutor: PuzzleOut = { ...ONE_MOVE, id: "p8",
    solution: { ...ONE_MOVE.solution, wrong_moves: { h2h3: "Perde a dama." } } };
  const analyse = vi.fn(async (fen: string) => (fen === comAutor.fen_start
    ? analiseOut(fen, [LINHA_ANTES])
    : analiseOut(FEN_ERRO, [linha])));
  const { result } = setup(comAutor, { refute: true, analyse });
  act(() => result.current.tryMove("h2", "h3"));
  await escoar();
  expect(result.current.state.phase).toBe("refuted");
  // a continuação para na quinta jogada depois da réplica
  expect(result.current.state.refutation?.pvSan).toEqual(["Kf1", "Qxh1", "Ke2", "Qg2", "Ke1"]);
  expect(result.current.state.message).toEqual({
    text: "h3? Qg2 — avaliação cai de +9.00 para -5.00 · segue Kf1 Qxh1 Ke2 Qg2 Ke1 — Perde a dama.",
    tone: "bad",
    fen: comAutor.fen_start,
  });
});

// Peão em a7 que pode promover sem que a solução (`c3d5`) seja uma promoção:
// o lance errado chega como `a7a8`, sem a peça, e a refutação promove a dama.
const PROMO_ERRADA: PuzzleOut = { ...base, id: "p9", kind: "punish", fen_start: "4k3/P7/8/3q4/8/2N5/7P/4K3 w - - 0 1", side_to_move: "white", solver_moves: 1,
  solution: { moves: [{ uci: "c3d5", by: "solver", alternatives: [] }], explanation_pv: [] } };
const FEN_PROMO = "Q3k3/8/8/3q4/8/2N5/7P/4K3 b - - 0 1";
const LINHA_PROMO: AnalyseLine = { move: "d5a8", san: "Qxa8", score: 900, pv: ["d5a8"], pv_san: ["Qxa8"] };

test("lance errado de peão à última fila é refutado promovendo a dama", async () => {
  const analyse = vi.fn(async (fen: string) => (fen === PROMO_ERRADA.fen_start
    ? analiseOut(fen, [LINHA_ANTES])
    : analiseOut(FEN_PROMO, [LINHA_PROMO])));
  const { result } = setup(PROMO_ERRADA, { refute: true, analyse });
  act(() => result.current.tryMove("a7", "a8"));
  // sem a peça da promoção o lance entrou como dama, e não foi só recusado
  expect(result.current.state.phase).toBe("refuting");
  expect(result.current.state.fen).toBe(FEN_PROMO);
  expect(result.current.state.lastMove).toEqual(["a7", "a8"]);

  await escoar();
  expect(result.current.state.phase).toBe("refuted");
  expect(result.current.state.refutation).toMatchObject({ wrongSan: "a8=Q+", replySan: "Qxa8", evalAfter: -900, evalBefore: 900 });
  expect(result.current.state.fen).toBe("q3k3/8/8/8/8/2N5/7P/4K3 w - - 0 2");
  expect(analyse).toHaveBeenCalledWith(FEN_PROMO, 1);
  expect(sons()).toEqual(["wrong", "capture"]);
});
