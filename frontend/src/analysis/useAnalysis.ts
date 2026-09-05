import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Chess } from "chess.js";
import type { Key } from "chessground/types";
import { destsFrom } from "../board/dests";
import { uciToMove } from "../board/line";

export interface UseAnalysisOptions {
  /** Intervalo entre lances de `playLine`, em ms. Injetável para teste. */
  stepMs?: number;
}

interface Stack {
  fens: string[];
  sans: string[];
  lastMoves: ([Key, Key] | undefined)[];
  index: number;
}

function initStack(fenStart: string): Stack {
  return { fens: [fenStart], sans: [], lastMoves: [undefined], index: 0 };
}

/**
 * Pilha de posições para o tabuleiro de análise.
 *
 * `fens[i]`/`lastMoves[i]` são a posição após i lances (fens[0] é a posição
 * inicial); `sans[i]` é o SAN do lance que produziu `fens[i+1]`. `index`
 * aponta a posição atualmente exibida — pode ficar no meio da pilha (via
 * `goTo`) sem descartar o que vem depois; jogar um novo lance a partir daí
 * (`play`) descarta o futuro.
 */
export function useAnalysis(fenStart: string, opts: UseAnalysisOptions = {}) {
  const stepMs = opts.stepMs ?? 250;
  const stackRef = useRef<Stack>(initStack(fenStart));
  const [, bump] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const play = useCallback((uci: string): boolean => {
    const s = stackRef.current;
    const chess = new Chess(s.fens[s.index]);
    let san: string;
    let from: Key, to: Key;
    try {
      const mv = chess.move(uciToMove(uci));
      san = mv.san;
      from = mv.from as Key;
      to = mv.to as Key;
    } catch {
      return false;
    }
    stackRef.current = {
      fens: [...s.fens.slice(0, s.index + 1), chess.fen()],
      sans: [...s.sans.slice(0, s.index), san],
      lastMoves: [...s.lastMoves.slice(0, s.index + 1), [from, to]],
      index: s.index + 1,
    };
    bump((v) => v + 1);
    return true;
  }, []);

  const undo = useCallback(() => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null; }
    const s = stackRef.current;
    if (s.index === 0) return;
    stackRef.current = {
      fens: s.fens.slice(0, s.index),
      sans: s.sans.slice(0, s.index - 1),
      lastMoves: s.lastMoves.slice(0, s.index),
      index: s.index - 1,
    };
    bump((v) => v + 1);
  }, []);

  const reset = useCallback(() => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null; }
    stackRef.current = initStack(fenStart);
    bump((v) => v + 1);
  }, [fenStart]);

  const goTo = useCallback((i: number) => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null; }
    const s = stackRef.current;
    const index = Math.max(0, Math.min(i, s.fens.length - 1));
    stackRef.current = { ...s, index };
    bump((v) => v + 1);
  }, []);

  const playLine = useCallback((ucis: string[]) => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null; }
    let i = 0;
    const step = () => {
      play(ucis[i]);
      i++;
      if (i < ucis.length) timer.current = setTimeout(step, stepMs);
    };
    if (ucis.length > 0) step();
  }, [play, stepMs]);

  useEffect(() => () => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null; }
  }, []);

  const s = stackRef.current;
  const fen = s.fens[s.index];
  const turn = (fen.split(" ")[1] === "w" ? "white" : "black") as "white" | "black";
  const dests = useMemo(() => destsFrom(new Chess(fen)), [fen]);
  const lastMove = s.lastMoves[s.index];

  return { fens: s.fens, sans: s.sans, index: s.index, fen, turn, dests, play, playLine, undo, reset, goTo, lastMove };
}
