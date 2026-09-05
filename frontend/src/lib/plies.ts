import { Chess } from "chess.js";
import type { Key } from "chessground/types";
import type { GameDetail, MistakeLevel } from "../api/types";
import { uciToMove } from "../board/line";

export interface Ply {
  ply: number; san: string; fenBefore: string; fenAfter: string; lastMove: [Key, Key];
  evalBefore?: number; evalAfter?: number; level?: MistakeLevel; by?: "me" | "opponent"; bestMove?: string; puzzleIds: string[];
}

export function buildPlies(game: GameDetail): Ply[] {
  if (game.analyzed_at && game.positions.length > 0) {
    return game.positions.map((p) => {
      const c = new Chess(p.fen);
      const mv = c.move(uciToMove(p.move_uci));
      return {
        ply: p.ply, san: p.move_played, fenBefore: p.fen, fenAfter: c.fen(), lastMove: [mv.from as Key, mv.to as Key],
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
