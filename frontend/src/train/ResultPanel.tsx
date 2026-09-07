import { useState } from "react";
import { Link } from "react-router-dom";
import type { PuzzleOut, ReviewOut } from "../api/types";
import { usePuzzleQuery } from "../api/queries";
import { ErrorBox } from "../components/ErrorBox";
import { formatEval, themeLabel } from "../lib/format";
import { startPlyFromFen } from "../lib/plies";
import { buildLine } from "../board/line";
import { LineViewer } from "./LineViewer";
import { QueueButtons } from "./QueueButtons";

export function ResultPanel({ puzzle, review, error, onRetry, onNext, nextLabel = "Próximo puzzle", nextDisabled, clockLabel }:
  { puzzle: PuzzleOut; review?: ReviewOut; error?: unknown; onRetry: () => void; onNext: () => void; nextLabel?: string; nextDisabled?: boolean; clockLabel?: string }) {
  const ucis = puzzle.solution.moves.map((m) => m.uci);
  const isAvoid = puzzle.kind === "avoid";
  // sem partida (Lichess, estudo) a numeração vem da própria FEN
  const startPly = puzzle.ply == null ? startPlyFromFen(puzzle.fen_start) : isAvoid ? puzzle.ply : puzzle.ply + 1;
  const bestSan = buildLine(puzzle.fen_start, ucis.slice(0, 1)).sans[0] ?? ucis[0];
  const punishSibling = isAvoid ? puzzle.siblings.find((s) => s.kind === "punish") : undefined;
  const { data: refutation } = usePuzzleQuery(punishSibling?.id ?? null);
  const clean = review && review.result === "correct" && !review.used_hint;
  const exploreHref = `/analise?fen=${encodeURIComponent(puzzle.fen_start)}&orientation=${puzzle.side_to_move}&back=${encodeURIComponent("/treinar")}`;
  // comentário do autor do estudo para o lance da posição mostrada na linha
  const [pos, setPos] = useState(puzzle.solution.moves.length);
  const comment = pos > 0 ? puzzle.solution.comments?.[String(pos - 1)] : undefined;
  return (
    <div className="two-col">
      <div>
        <LineViewer fenStart={puzzle.fen_start} ucis={ucis} orientation={puzzle.side_to_move} startPly={startPly} initialPos={puzzle.solution.moves.length} onPos={setPos} />
        {comment && <p style={{ marginTop: 8 }}>{comment}</p>}
        {isAvoid && refutation && puzzle.mistake && (
          <div className="card" style={{ marginTop: 12 }}>
            <b>O que acontecia depois de {puzzle.mistake.move_played}</b>
            <LineViewer fenStart={refutation.fen_start} ucis={refutation.solution.moves.map((m) => m.uci)} orientation={puzzle.side_to_move}
              startPly={refutation.ply == null ? startPlyFromFen(refutation.fen_start) : refutation.ply + 1} initialPos={0} keyboard={false} />
          </div>
        )}
      </div>
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
        {isAvoid && puzzle.mistake && (
          <p>Na partida você jogou <b>{puzzle.mistake.move_played}</b> ({formatEval(puzzle.mistake.eval_before)} → {formatEval(puzzle.mistake.eval_after)}). O melhor era <b>{bestSan}</b>.</p>
        )}
        <div style={{ marginTop: 10 }}><span className="tag">{themeLabel(puzzle.theme)}</span><span className="tag">{puzzle.category}</span><span className="tag">{puzzle.end_reason === "mate" ? "termina em mate" : puzzle.end_reason === "material_gain" ? "ganho de material" : "explicação"}</span></div>
        <div className="row" style={{ marginTop: 10 }}>
          {puzzle.game && <a href={puzzle.game.source_id} target="_blank" rel="noopener">partida no chess.com</a>}
          {puzzle.game && puzzle.ply != null && <Link to={`/partidas/${puzzle.game.id}?ply=${puzzle.ply}`}>partida no app</Link>}
          {puzzle.study?.lichess_url && <a href={puzzle.study.lichess_url} target="_blank" rel="noopener noreferrer">ver no Lichess</a>}
          <a href={exploreHref} target="_blank" rel="noopener noreferrer">Explorar</a>
          <QueueButtons puzzle={puzzle} />
          {review && <button className="primary" style={{ marginLeft: "auto" }} disabled={nextDisabled} onClick={onNext}>{nextDisabled ? "Carregando…" : nextLabel}</button>}
        </div>
      </div>
    </div>
  );
}
