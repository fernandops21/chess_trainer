import { Link } from "react-router-dom";
import type { Key } from "chessground/types";
import type { PuzzleOut } from "../api/types";
import { MiniBoard } from "../board/MiniBoard";
import { buildLine, uciToMove } from "../board/line";
import { formatEval, levelLabel } from "../lib/format";

/**
 * "Meu erro" / "Na partida": o que aconteceu na partida em volta do erro, com o
 * lance destacado no mini-tabuleiro, as avaliações e os atalhos para a partida
 * e para a revisão de erros.
 *
 * No "evitar" o lance é seu e sai da própria posição do exercício. No "punir" o
 * erro é do adversário e sai da posição de antes dele (`fen_before`) — mas
 * quando a API traz `mistake.my_reply` o que interessa é a sua resposta: o
 * tabuleiro passa a mostrar a posição do exercício com o lance que você jogou,
 * e o texto diz o que você deixou passar. Sem erro ou sem partida — táticas,
 * estudos — o cartão não aparece.
 */
export function MistakeCard({ puzzle }: { puzzle: PuzzleOut }) {
  const { game, mistake } = puzzle;
  if (!game || !mistake) return null;
  const evitar = puzzle.kind === "avoid";
  const meu = mistake.mistake_by ? mistake.mistake_by === "me" : evitar;
  const resposta = evitar ? null : mistake.my_reply ?? null;
  // posição do erro, a que casa com a revisão de erros (o FEN de antes do lance ruim);
  // no "punir" sem `fen_before` a do exercício já mostra o lance nas mesmas casas
  const fenErro = evitar ? puzzle.fen_start : puzzle.fen_before ?? puzzle.fen_start;
  // com a resposta da partida o tabuleiro mostra o seu lance, não o do adversário
  const fen = resposta ? puzzle.fen_start : fenErro;
  const mv = uciToMove(resposta ? resposta.move_uci : mistake.move_uci);
  // o primeiro lance da solução em SAN: é o que você deixou passar (ou achou)
  const solucao = puzzle.solution.moves[0];
  const solucaoSan = solucao ? buildLine(puzzle.fen_start, [solucao.uci]).sans[0] ?? solucao.uci : null;
  const achou = !!resposta && !!solucao
    && (resposta.move_uci === solucao.uci || solucao.alternatives.includes(resposta.move_uci));
  return (
    <div className="card">
      <div className="row">
        <MiniBoard fen={fen} orientation={puzzle.side_to_move} lastMove={[mv.from as Key, mv.to as Key]} />
        <div style={{ flex: "1 1 200px" }}>
          <div>
            Na partida {meu ? "você jogou" : "o adversário jogou"} <b>{mistake.move_played}</b>{" "}
            ({formatEval(mistake.eval_before)} → {formatEval(mistake.eval_after)})
            {mistake.mistake_level && <> <span className={`tag ${mistake.mistake_level}`}>{levelLabel(mistake.mistake_level)}</span></>}
            {resposta && (achou
              ? <>. Você achou <b>{resposta.move_played}</b> na partida.</>
              : <>
                  . Você respondeu <b>{resposta.move_played}</b>{" "}
                  ({formatEval(resposta.eval_before)} → {formatEval(resposta.eval_after)})
                  {solucaoSan && <> e deixou passar <b>{solucaoSan}</b></>}.
                </>)}
          </div>
          <div className="row" style={{ marginTop: 6 }}>
            <Link to={`/partidas/${game.id}?ply=${mistake.ply}`}>partida no app</Link>
            <Link to={`/erros?position=${encodeURIComponent(fenErro)}`}>revisão de erros</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
