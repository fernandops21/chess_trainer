import { Link } from "react-router-dom";
import type { PuzzleOut, ReviewOut } from "../api/types";
import { ErrorBox } from "../components/ErrorBox";
import { themeLabel } from "../lib/format";
import { LineViewer } from "./LineViewer";

export function ResultPanel({ puzzle, review, error, onRetry, onNext, nextLabel = "Próximo puzzle", nextDisabled, clockLabel }:
  { puzzle: PuzzleOut; review?: ReviewOut; error?: unknown; onRetry: () => void; onNext: () => void; nextLabel?: string; nextDisabled?: boolean; clockLabel?: string }) {
  const ucis = puzzle.solution.moves.map((m) => m.uci).concat(puzzle.kind === "avoid" ? puzzle.solution.explanation_pv.slice(1) : []);
  const clean = review && review.result === "correct" && !review.used_hint;
  return (
    <div className="two-col">
      <LineViewer fenStart={puzzle.fen_start} ucis={ucis} orientation={puzzle.side_to_move} startPly={puzzle.ply + 1} />
      <div className="card">
        {clockLabel && <div className="row"><span className="muted" aria-label="relógio">{clockLabel}</span></div>}
        {!!error && (<><ErrorBox error={error} /><button onClick={onRetry}>Tentar registrar de novo</button></>)}
        {review && (
          <>
            <div className={`msg ${clean ? "ok" : "bad"}`}>{clean ? "Resolvido sem erro." : "Concluído, mas contou como erro (volta em 1 dia)."}</div>
            <div className="muted">Próxima revisão em {review.interval_days} dia(s) · facilidade {review.ease} · lapsos {review.lapses}{review.is_leech ? " · virou sanguessuga" : ""}</div>
          </>
        )}
        <div style={{ marginTop: 10 }}><span className="tag">{themeLabel(puzzle.theme)}</span><span className="tag">{puzzle.category}</span><span className="tag">{puzzle.end_reason === "mate" ? "termina em mate" : puzzle.end_reason === "material_gain" ? "ganho de material" : "explicação"}</span></div>
        <div className="row" style={{ marginTop: 10 }}>
          <a href={puzzle.game.source_id} target="_blank" rel="noopener">partida no chess.com</a>
          <Link to={`/partidas/${puzzle.game.id}?ply=${puzzle.ply}`}>partida no app</Link>
          {review && <button className="primary" style={{ marginLeft: "auto" }} disabled={nextDisabled} onClick={onNext}>{nextDisabled ? "Carregando…" : nextLabel}</button>}
        </div>
      </div>
    </div>
  );
}
