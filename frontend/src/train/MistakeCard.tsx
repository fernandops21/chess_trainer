import { useContext } from "react";
import { Link } from "react-router-dom";
import type { Key } from "chessground/types";
import type { PuzzleOut } from "../api/types";
import { MiniBoard } from "../board/MiniBoard";
import { buildLine, uciToMove } from "../board/line";
import { formatEval, levelLabel } from "../lib/format";
import { PreviaContext } from "../analysis/previaContext";
import type { LanceDaLinha } from "../analysis/moveText";

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
/** Um lance do cartão: link que abre a prévia no tabuleiro grande quando há um, senão só negrito. */
function Lance({ san, fen, uci }: { san: string; fen: string | null; uci: string | null }) {
  const previa = useContext(PreviaContext);
  const linha: LanceDaLinha[] | null = (() => {
    if (!previa || !fen || !uci) return null;
    const l = buildLine(fen, [uci]);
    return l.sans[0] && l.lastMoves[1] ? [{ san: l.sans[0], uci, fen: l.fens[1], lastMove: l.lastMoves[1] }] : null;
  })();
  if (!linha) return <b>{san}</b>;
  return (
    <button type="button" className="lance-no-texto" title="mostrar no tabuleiro" onClick={() => previa!(linha)}>
      <b>{san}</b>
    </button>
  );
}

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
            Na partida {meu ? "você jogou" : "o adversário jogou"} <Lance san={mistake.move_played} fen={fenErro} uci={mistake.move_uci} />{" "}
            ({formatEval(mistake.eval_before)} → {formatEval(mistake.eval_after)})
            {mistake.mistake_level && <> <span className={`tag ${mistake.mistake_level}`}>{levelLabel(mistake.mistake_level)}</span></>}
            {resposta && (achou
              ? <>. Você achou <Lance san={resposta.move_played} fen={puzzle.fen_start} uci={resposta.move_uci} /> na partida.</>
              : <>
                  . Você respondeu <Lance san={resposta.move_played} fen={puzzle.fen_start} uci={resposta.move_uci} />{" "}
                  ({formatEval(resposta.eval_before)} → {formatEval(resposta.eval_after)})
                  {solucaoSan && solucao && <> e deixou passar <Lance san={solucaoSan} fen={puzzle.fen_start} uci={solucao.uci} /></>}.
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
