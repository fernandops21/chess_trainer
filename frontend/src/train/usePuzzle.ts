import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Chess } from "chess.js";
import type { Key } from "chessground/types";
import type { ReviewIn, ReviewOut, Trainable } from "../api/types";
import { destsFrom } from "../board/dests";
import { uciToMove } from "../board/line";

/** O mínimo que a máquina de estados precisa: serve tanto para `PuzzleOut` quanto para `TacticOut`. */
export type PuzzleInput = Pick<Trainable, "id" | "fen_start" | "solution">;

export type Phase = "awaiting_move" | "engine_replying" | "solved" | "submitting" | "result" | "submit_error";
export type Promotion = "q" | "r" | "b" | "n";

export interface PuzzleState<R = ReviewOut> {
  phase: Phase;
  fen: string;
  turn: "white" | "black";
  idx: number;
  wrong: boolean;
  usedHint: boolean;
  message: { text: string; tone: "ok" | "bad" | "" };
  lastMove?: [Key, Key];
  check: boolean;
  hint?: Key;
  pendingPromotion?: { orig: Key; dest: Key };
  review?: R;
  error?: unknown;
}

export interface UsePuzzleOptions<R = ReviewOut> {
  sessionId: string | null;
  presetHint?: boolean;
  engineDelayMs?: number;
  submit: (body: ReviewIn) => Promise<R>;
  now?: () => number;
}

const turnOf = (c: Chess) => (c.turn() === "w" ? "white" : "black") as "white" | "black";

/**
 * Puzzle state machine.
 *
 * Contract: mount one `usePuzzle` instance per puzzle. Consumers MUST render
 * it with a React `key={puzzle.id}` (or otherwise force a remount when the
 * puzzle changes), e.g. `<Puzzle key={puzzle.id} puzzle={puzzle} ... />`.
 * All state (`phase`, `idx`, the underlying `chess.js` position, `startedAt`,
 * etc.) is initialised once on mount from the `puzzle` prop; this hook does
 * not watch `puzzle` for changes and performs no runtime reset if a new
 * puzzle object is passed into an already-mounted instance.
 */
export function usePuzzle<R = ReviewOut>(puzzle: PuzzleInput, opts: UsePuzzleOptions<R>) {
  const chessRef = useRef(new Chess(puzzle.fen_start));
  const now = opts.now ?? Date.now;
  const startedAt = useRef(now());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [state, setState] = useState<PuzzleState<R>>(() => ({
    phase: "awaiting_move",
    fen: puzzle.fen_start,
    turn: turnOf(chessRef.current),
    idx: 0,
    wrong: false,
    usedHint: !!opts.presetHint,
    message: opts.presetHint ? { text: "Solução já vista: conta como dica.", tone: "bad" } : { text: "", tone: "" },
    check: chessRef.current.inCheck(),
  }));

  // Mutable bits read from within the engine-reply setTimeout callback, which
  // closes over the render that scheduled it. Keep them in refs so the
  // callback always sees the latest value instead of a stale snapshot.
  const wrongRef = useRef(state.wrong);
  wrongRef.current = state.wrong;
  const usedHintRef = useRef(state.usedHint);
  usedHintRef.current = state.usedHint;
  // Guards against double-submit: true for the whole lifetime of a submit
  // attempt (set synchronously before the first `setState`, cleared in a
  // `finally`), so a rapid double call to `retrySubmit()` cannot fire a
  // second request while the first is still in flight.
  const submittingRef = useRef(false);

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  const snapshot = (partial: Partial<PuzzleState<R>>) => (prev: PuzzleState<R>): PuzzleState<R> => {
    const c = chessRef.current;
    return { ...prev, fen: c.fen(), turn: turnOf(c), check: c.inCheck(), ...partial };
  };

  const doSubmit = useCallback(async (wrong: boolean, usedHint: boolean) => {
    submittingRef.current = true;
    setState((p) => ({ ...p, phase: "submitting", error: undefined }));
    const body: ReviewIn = {
      puzzle_id: puzzle.id, session_id: opts.sessionId, correct: !wrong, used_hint: usedHint,
      duration_ms: Math.max(0, now() - startedAt.current),
    };
    try {
      const review = await opts.submit(body);
      setState((p) => ({ ...p, phase: "result", review }));
    } catch (error) {
      setState((p) => ({ ...p, phase: "submit_error", error }));
    } finally {
      submittingRef.current = false;
    }
  }, [puzzle.id, opts.sessionId, opts.submit, now]);

  const finish = useCallback((wrong: boolean, usedHint: boolean) => {
    setState(snapshot({ phase: "solved", hint: undefined, message: { text: "Certo!", tone: "ok" } }));
    void doSubmit(wrong, usedHint);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doSubmit]);

  const applySolverMove = useCallback((uci: string) => {
    const c = chessRef.current;
    let mv: ReturnType<Chess["move"]>;
    try {
      mv = c.move(uciToMove(uci));
    } catch {
      // Textually matched an expected uci/alternative but chess.js rejects it
      // as an illegal move on the current position (e.g. a malformed
      // alternative). Score it as a wrong attempt instead of crashing.
      setState((p) => ({ ...p, wrong: true, pendingPromotion: undefined, message: { text: "Lance inválido", tone: "bad" } }));
      return;
    }
    const nextIdx = c.history().length;
    const last: [Key, Key] = [mv.from as Key, mv.to as Key];
    const moves = puzzle.solution.moves;
    if (nextIdx >= moves.length) {
      setState(snapshot({ idx: nextIdx, lastMove: last, pendingPromotion: undefined }));
      finish(wrongRef.current, usedHintRef.current);
      return;
    }
    const reply = moves[nextIdx];
    if (reply.by === "engine") {
      setState(snapshot({ phase: "engine_replying", idx: nextIdx, lastMove: last, hint: undefined, pendingPromotion: undefined, message: { text: "Certo!", tone: "ok" } }));
      timer.current = setTimeout(() => {
        let r: ReturnType<Chess["move"]>;
        try {
          r = chessRef.current.move(uciToMove(reply.uci));
        } catch {
          // A malformed uci from the backend for the engine's reply. Surface
          // it as a submit error instead of throwing out of the timer.
          setState((p) => ({ ...p, phase: "submit_error", error: new Error("Solução inválida do servidor") }));
          return;
        }
        const afterReply = chessRef.current.history().length;
        const replyLast: [Key, Key] = [r.from as Key, r.to as Key];
        if (afterReply >= moves.length) {
          setState(snapshot({ idx: afterReply, lastMove: replyLast }));
          finish(wrongRef.current, usedHintRef.current);
        } else {
          setState(snapshot({ phase: "awaiting_move", idx: afterReply, lastMove: replyLast }));
        }
      }, opts.engineDelayMs ?? 350);
    } else {
      setState(snapshot({ phase: "awaiting_move", idx: nextIdx, lastMove: last, hint: undefined, pendingPromotion: undefined, message: { text: "Certo!", tone: "ok" } }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [puzzle.solution.moves, opts.engineDelayMs, finish]);

  const judge = useCallback((orig: Key, dest: Key, promotion?: Promotion) => {
    const expected = puzzle.solution.moves[state.idx];
    if (!expected || expected.by !== "solver") return;
    const uci = `${orig}${dest}${promotion ?? ""}`;
    const ok = uci === expected.uci || expected.alternatives.includes(uci);
    if (!ok) {
      setState((p) => ({ ...p, wrong: true, pendingPromotion: undefined, message: { text: "Não é esse. Tente de novo.", tone: "bad" } }));
      return;
    }
    applySolverMove(uci);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [puzzle.solution.moves, state.idx, applySolverMove]);

  const tryMove = useCallback((orig: Key, dest: Key, promotion?: Promotion) => {
    if (state.phase !== "awaiting_move") return;
    const expected = puzzle.solution.moves[state.idx];
    const candidates = expected ? [expected.uci, ...expected.alternatives] : [];
    const needsPromotion = candidates.some((u) => u.length === 5 && u.startsWith(`${orig}${dest}`));
    if (needsPromotion && !promotion) {
      setState((p) => ({ ...p, pendingPromotion: { orig, dest } }));
      return;
    }
    judge(orig, dest, promotion);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.phase, state.idx, puzzle.solution.moves, judge]);

  const choosePromotion = useCallback((piece: Promotion) => {
    const pp = state.pendingPromotion;
    if (!pp) return;
    judge(pp.orig, pp.dest, piece);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.pendingPromotion, judge]);

  const cancelPromotion = useCallback(() => setState((p) => ({ ...p, pendingPromotion: undefined })), []);

  const useHint = useCallback(() => {
    if (state.phase !== "awaiting_move") return;
    const expected = puzzle.solution.moves[state.idx];
    if (!expected) return;
    setState((p) => ({ ...p, usedHint: true, hint: expected.uci.slice(0, 2) as Key, message: { text: "Peça destacada (dica conta como erro).", tone: "bad" } }));
  }, [state.phase, state.idx, puzzle.solution.moves]);

  const retrySubmit = useCallback(() => {
    if (state.phase !== "submit_error" || submittingRef.current) return;
    void doSubmit(wrongRef.current, usedHintRef.current);
  }, [doSubmit, state.phase]);

  const dests = useMemo(() => (state.phase === "awaiting_move" ? destsFrom(chessRef.current) : new Map<Key, Key[]>()), [state.phase, state.fen]);

  return { state, dests, tryMove, choosePromotion, cancelPromotion, useHint, retrySubmit };
}

/** Retorno de `usePuzzle`; use `PuzzleCtl<unknown>` para aceitar qualquer resultado de submit. */
export type PuzzleCtl<R = ReviewOut> = ReturnType<typeof usePuzzle<R>>;
