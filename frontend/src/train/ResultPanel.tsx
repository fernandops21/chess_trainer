import { useMemo } from "react";
import { Link } from "react-router-dom";
import type { PuzzleOut, ReviewOut } from "../api/types";
import { usePuzzleQuery } from "../api/queries";
import { AnalysisBoard } from "../analysis/AnalysisBoard";
import { treeFromSolution, withMistakeVariation } from "../analysis/solutionTree";
import { ErrorBox } from "../components/ErrorBox";
import { categoryLabel, formatEval, themeLabel } from "../lib/format";
import { buildLine } from "../board/line";
import { MistakeCard } from "./MistakeCard";
import { QueueButtons } from "./QueueButtons";

export function ResultPanel({ puzzle, review, error, onRetry, onNext, nextLabel = "Próximo puzzle", nextDisabled, clockLabel }:
  { puzzle: PuzzleOut; review?: ReviewOut; error?: unknown; onRetry: () => void; onNext: () => void; nextLabel?: string; nextDisabled?: boolean; clockLabel?: string }) {
  const isAvoid = puzzle.kind === "avoid";
  const bestSan = buildLine(puzzle.fen_start, puzzle.solution.moves.slice(0, 1).map((m) => m.uci)).sans[0] ?? puzzle.solution.moves[0]?.uci;
  const punishSibling = isAvoid ? puzzle.siblings.find((s) => s.kind === "punish") : undefined;
  const { data: refutation } = usePuzzleQuery(punishSibling?.id ?? null);
  const clean = review && review.result === "correct" && !review.used_hint;
  const exploreHref = `/analise?fen=${encodeURIComponent(puzzle.fen_start)}&orientation=${puzzle.side_to_move}&back=${encodeURIComponent("/treinar")}`;
  // erro da partida: o cartão já traz a posição, a avaliação e o link da partida
  const comErro = puzzle.source === "own" && puzzle.mistake && puzzle.game ? puzzle : null;
  // a solução vira a árvore do tabuleiro de análise; no "evitar", o lance jogado
  // na partida entra como variação com a punição dele (quando ela já chegou)
  const tree = useMemo(() => {
    const base = treeFromSolution(puzzle);
    if (!isAvoid || !refutation || !puzzle.mistake) return base;
    return withMistakeVariation(
      base,
      puzzle.fen_start,
      puzzle.mistake.move_uci,
      `Na partida você jogou ${puzzle.mistake.move_played}`,
      refutation.solution.moves.map((m) => m.uci),
    );
  }, [puzzle, isAvoid, refutation]);
  // o resultado e o cartão do erro vão para o topo da coluna da direita: em cima
  // do tabuleiro eles empurravam tudo para baixo e sobrava espaço ao lado
  const lateral = (
    <>
      <div className="card">
        {clockLabel && <div className="row"><span className="muted" aria-label="relógio">{clockLabel}</span></div>}
        {!!error && (<><ErrorBox error={error} /><button onClick={onRetry}>Tentar registrar de novo</button></>)}
        {review && (
          <>
            <div className={`msg ${clean ? "ok" : "bad"}`}>{clean ? "Resolvido sem erro." : "Concluído, mas contou como erro (volta em 1 dia)."}</div>
            <div className="muted">Próxima revisão em {review.interval_days} dia(s) · facilidade {review.ease} · lapsos {review.lapses}{review.is_leech ? " · virou sanguessuga" : ""}</div>
          </>
        )}
        {puzzle.study && <div className="muted">{puzzle.study.title} · {puzzle.study.chapter_name}</div>}
        {/* sem o cartão do erro (exercício sem partida), o resumo em uma linha */}
        {isAvoid && puzzle.mistake && !comErro && (
          <p>Na partida você jogou <b>{puzzle.mistake.move_played}</b> ({formatEval(puzzle.mistake.eval_before)} → {formatEval(puzzle.mistake.eval_after)}). O melhor era <b>{bestSan}</b>.</p>
        )}
        <div style={{ marginTop: 10 }}><span className="tag">{themeLabel(puzzle.theme)}</span><span className="tag">{categoryLabel(puzzle.category)}</span><span className="tag">{puzzle.end_reason === "mate" ? "termina em mate" : puzzle.end_reason === "material_gain" ? "ganho de material" : "explicação"}</span></div>
        <div className="row" style={{ marginTop: 10 }}>
          {puzzle.game && <a href={puzzle.game.source_id} target="_blank" rel="noopener">partida no chess.com</a>}
          {/* com o cartão do erro, o link da partida no app é o dele */}
          {puzzle.game && puzzle.ply != null && !comErro && <Link to={`/partidas/${puzzle.game.id}?ply=${puzzle.ply}`}>partida no app</Link>}
          {puzzle.study?.lichess_url && <a href={puzzle.study.lichess_url} target="_blank" rel="noopener noreferrer">ver no Lichess</a>}
          <a href={exploreHref} target="_blank" rel="noopener noreferrer">Explorar</a>
          <QueueButtons puzzle={puzzle} />
          {review && <button className="primary" style={{ marginLeft: "auto" }} disabled={nextDisabled} onClick={onNext}>{nextDisabled ? "Carregando…" : nextLabel}</button>}
        </div>
      </div>
      {comErro && <MistakeCard puzzle={comErro} />}
    </>
  );
  return <AnalysisBoard tree={tree} initialNodeId="last" engine={false} allowSetup={false} sidePanel={lateral} />;
}
