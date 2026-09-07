import { Link } from "react-router-dom";
import type { Key } from "chessground/types";
import type { PuzzleOut } from "../api/types";
import { MiniBoard } from "../board/MiniBoard";
import { uciToMove } from "../board/line";
import { formatEval, levelLabel } from "../lib/format";

/**
 * "Meu erro": a posição da partida em que o lance ruim foi jogado, com ele
 * destacado, a avaliação de antes e depois e os atalhos para a partida e para
 * a revisão de erros.
 *
 * No "evitar" o lance é seu e sai da própria posição do exercício; no "punir"
 * ele é do adversário e sai da posição de antes dele (`fen_before`). Sem erro
 * ou sem partida — táticas, estudos — o cartão não aparece.
 */
export function MistakeCard({ puzzle }: { puzzle: PuzzleOut }) {
  const { game, mistake } = puzzle;
  if (!game || !mistake) return null;
  const evitar = puzzle.kind === "avoid";
  const meu = mistake.mistake_by ? mistake.mistake_by === "me" : evitar;
  // no "punir" a posição de antes é a do adversário a jogar; sem ela, a do
  // exercício já mostra o lance recém-jogado nas mesmas casas
  const fen = evitar ? puzzle.fen_start : puzzle.fen_before ?? puzzle.fen_start;
  const mv = uciToMove(mistake.move_uci);
  return (
    <div className="card">
      <div className="row">
        <MiniBoard fen={fen} orientation={puzzle.side_to_move} lastMove={[mv.from as Key, mv.to as Key]} />
        <div style={{ flex: "1 1 200px" }}>
          <div>
            Na partida {meu ? "você jogou" : "o adversário jogou"} <b>{mistake.move_played}</b>{" "}
            ({formatEval(mistake.eval_before)} → {formatEval(mistake.eval_after)})
            {mistake.mistake_level && <> <span className={`tag ${mistake.mistake_level}`}>{levelLabel(mistake.mistake_level)}</span></>}
          </div>
          <div className="row" style={{ marginTop: 6 }}>
            <Link to={`/partidas/${game.id}?ply=${mistake.ply}`}>partida no app</Link>
            <Link to={`/erros?position=${encodeURIComponent(puzzle.fen_start)}`}>revisão de erros</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
