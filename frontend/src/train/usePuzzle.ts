import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Chess } from "chess.js";
import type { Key } from "chessground/types";
import type { PuzzleOut, ReviewIn, ReviewOut } from "../api/types";
import { destsFrom } from "../board/dests";
import { uciToMove } from "../board/line";

export type Phase = "awaiting_move" | "engine_replying" | "solved" | "submitting" | "result" | "submit_error";
export type Promotion = "q" | "r" | "b" | "n";

export interface PuzzleState {
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
  review?: ReviewOut;
  error?: unknown;
}

export interface UsePuzzleOptions {
  sessionId: string | null;
  presetHint?: boolean;
  engineDelayMs?: number;
  submit: (body: ReviewIn) => Promise<ReviewOut>;
  now?: () => number;
}

const turnOf = (c: Chess) => (c.turn() === "w" ? "white" : "black") as "white" | "black";

export function usePuzzle(puzzle: PuzzleOut, opts: UsePuzzleOptions) {
  const chessRef = useRef(new Chess(puzzle.fen_start));
  const now = opts.now ?? Date.now;
  const startedAt = useRef(now());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [state, setState] = useState<PuzzleState>(() => ({
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

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  const snapshot = (partial: Partial<PuzzleState>) => (prev: PuzzleState): PuzzleState => {
    const c = chessRef.current;
    return { ...prev, fen: c.fen(), turn: turnOf(c), check: c.inCheck(), ...partial };
  };

  const doSubmit = useCallback(async (wrong: boolean, usedHint: boolean) => {
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
    }
  }, [puzzle.id, opts.sessionId, opts.submit, now]);

  const finish = useCallback((wrong: boolean, usedHint: boolean) => {
    setState(snapshot({ phase: "solved", hint: undefined, message: { text: "Certo!", tone: "ok" } }));
    void doSubmit(wrong, usedHint);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doSubmit]);

  const applySolverMove = useCallback((uci: string) => {
    const c = chessRef.current;
    const mv = c.move(uciToMove(uci));
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
        const r = chessRef.current.move(uciToMove(reply.uci));
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
    const needsPromotion = expected && expected.uci.length === 5 && expected.uci.startsWith(`${orig}${dest}`);
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

  const retrySubmit = useCallback(() => { void doSubmit(wrongRef.current, usedHintRef.current); }, [doSubmit]);

  const dests = useMemo(() => (state.phase === "awaiting_move" ? destsFrom(chessRef.current) : new Map<Key, Key[]>()), [state.phase, state.fen]);

  return { state, dests, tryMove, choosePromotion, cancelPromotion, useHint, retrySubmit };
}
