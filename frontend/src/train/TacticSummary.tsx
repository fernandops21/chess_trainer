import type { AttemptOut, TacticOut } from "../api/types";
import { themeLabel } from "../lib/format";

export interface TacticDone { tactic: TacticOut; attempt: AttemptOut }

export function TacticSummary({ done, elapsedLabel, reason, ratingStart, ratingEnd, onNew }:
  { done: TacticDone[]; elapsedLabel: string; reason: string; ratingStart: number; ratingEnd: number; onNew: () => void }) {
  const clean = (d: TacticDone) => d.attempt.correct && !d.attempt.used_hint;
  const ok = done.filter(clean);
  const failed = done.filter((d) => !clean(d));
  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Sessão encerrada</h2>
      <div className="muted">{reason}</div>
      <div className="row" style={{ marginTop: 10, gap: 24 }}>
        <div><div className="stat">{done.length}</div><div className="muted">táticas</div></div>
        <div><div className="stat">{ok.length}</div><div className="muted">sem erro</div></div>
        <div><div className="stat">{elapsedLabel}</div><div className="muted">tempo</div></div>
      </div>
      <div style={{ marginTop: 10 }}>{`Rating ${ratingStart} → ${ratingEnd}`}</div>
      {failed.length > 0 && (
        <>
          <h3>Para revisar</h3>
          <ul>
            {failed.map((d) => (
              <li key={d.tactic.id}>
                <a href={d.tactic.lichess_url} target="_blank" rel="noopener noreferrer">{themeLabel(d.tactic.theme)} · rating {d.tactic.rating}</a>
              </li>
            ))}
          </ul>
        </>
      )}
      <button className="primary" onClick={onNew}>Nova sessão</button>
    </div>
  );
}
