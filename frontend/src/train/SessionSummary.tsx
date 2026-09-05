import { Link } from "react-router-dom";
import type { PuzzleOut, ReviewOut } from "../api/types";

export interface Done { puzzle: PuzzleOut; review: ReviewOut; }

export function SessionSummary({ done, elapsedLabel, reason, onNew }: { done: Done[]; elapsedLabel: string; reason: string; onNew: () => void }) {
  const ok = done.filter((d) => d.review.result === "correct" && !d.review.used_hint);
  const failed = done.filter((d) => !(d.review.result === "correct" && !d.review.used_hint));
  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Sessão encerrada</h2>
      <div className="muted">{reason}</div>
      <div className="row" style={{ marginTop: 10, gap: 24 }}>
        <div><div className="stat">{done.length}</div><div className="muted">puzzles</div></div>
        <div><div className="stat">{ok.length}</div><div className="muted">sem erro</div></div>
        <div><div className="stat">{elapsedLabel}</div><div className="muted">tempo</div></div>
      </div>
      {failed.length > 0 && (
        <>
          <h3>Para revisar</h3>
          <ul>{failed.map((d) => <li key={d.puzzle.id}><Link to={`/erros?position=${encodeURIComponent(d.puzzle.fen_start)}`}>{d.puzzle.game.white} × {d.puzzle.game.black}, lance {Math.ceil(d.puzzle.ply / 2)}</Link></li>)}</ul>
        </>
      )}
      <button className="primary" onClick={onNew}>Nova sessão</button>
    </div>
  );
}
