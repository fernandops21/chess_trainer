import { Chess } from "chess.js";
import type { Key } from "chessground/types";
import type { GameDetail, MistakeLevel } from "../api/types";
import { uciToMove } from "../board/line";

/** Ply da posição inicial de uma FEN: exercícios sem partida não guardam o lance de origem. */
export function startPlyFromFen(fen: string): number {
  const parts = fen.split(" ");
  const fullmove = Number(parts[5]);
  const n = Number.isFinite(fullmove) && fullmove > 0 ? Math.floor(fullmove) : 1;
  return (n - 1) * 2 + (parts[1] === "b" ? 1 : 0) + 1;
}

export interface Ply {
  ply: number; san: string; fenBefore: string; fenAfter: string; lastMove: [Key, Key];
  evalBefore?: number; evalAfter?: number; level?: MistakeLevel; by?: "me" | "opponent"; bestMove?: string; puzzleIds: string[];
}

export function buildPlies(game: GameDetail): Ply[] {
  if (game.analyzed_at && game.positions.length > 0) {
    return game.positions.map((p) => {
      let fenAfter = p.fen;
      let lastMove: [Key, Key] = [uciToMove(p.move_uci).from as Key, uciToMove(p.move_uci).to as Key];
      try {
        const c = new Chess(p.fen);
        const mv = c.move(uciToMove(p.move_uci));
        fenAfter = c.fen();
        lastMove = [mv.from as Key, mv.to as Key];
      } catch {
        // malformed row (illegal move for its fen): keep fenAfter = p.fen and
        // lastMove derived directly from the uci so the list still renders.
      }
      return {
        ply: p.ply, san: p.move_played, fenBefore: p.fen, fenAfter, lastMove,
        evalBefore: p.eval_before, evalAfter: p.eval_after, level: p.mistake_level ?? undefined, by: p.mistake_by ?? undefined,
        bestMove: p.best_move ?? undefined, puzzleIds: p.puzzle_ids,
      };
    });
  }
  const c = new Chess();
  try { c.loadPgn(game.pgn); } catch { try { c.loadPgn(stripComments(game.pgn)); } catch { return []; } }
  const history = c.history({ verbose: true });
  const walker = new Chess();
  return history.map((m, i) => {
    const fenBefore = walker.fen();
    walker.move(m.san);
    return { ply: i + 1, san: m.san, fenBefore, fenAfter: walker.fen(), lastMove: [m.from as Key, m.to as Key], puzzleIds: [] };
  });
}

function stripComments(pgn: string): string {
  return pgn.replace(/\{[^}]*\}/g, "");
}
