import { Chess } from "chess.js";
import type { Key } from "chessground/types";

export function uciToMove(uci: string): { from: string; to: string; promotion?: string } {
  const m: { from: string; to: string; promotion?: string } = { from: uci.slice(0, 2), to: uci.slice(2, 4) };
  if (uci.length > 4) m.promotion = uci[4];
  return m;
}

/** Duas FENs que descrevem a mesma posição (o contador de lances não conta). */
export function mesmaPosicao(a: string, b: string): boolean {
  return a.split(" ").slice(0, 4).join(" ") === b.split(" ").slice(0, 4).join(" ");
}

export function buildLine(fenStart: string, ucis: string[]) {
  const chess = new Chess(fenStart);
  const fens = [chess.fen()];
  const sans: string[] = [];
  const lastMoves: ([Key, Key] | undefined)[] = [undefined];
  for (const uci of ucis) {
    try {
      const mv = chess.move(uciToMove(uci));
      sans.push(mv.san);
      fens.push(chess.fen());
      lastMoves.push([mv.from as Key, mv.to as Key]);
    } catch {
      break;
    }
  }
  return { fens, sans, lastMoves };
}
