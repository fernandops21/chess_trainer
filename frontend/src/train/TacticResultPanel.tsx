import type { AttemptOut, TacticOut } from "../api/types";
import { ErrorBox } from "../components/ErrorBox";
import { themeLabel } from "../lib/format";
import { startPlyFromFen } from "../lib/plies";
import { LineViewer } from "./LineViewer";
import { QueueButtons } from "./QueueButtons";

const signed = (n: number) => (n > 0 ? `+${n}` : String(n));

export function TacticResultPanel({ tactic, attempt, error, onRetry, onNext, nextDisabled, clockLabel }:
  { tactic: TacticOut; attempt?: AttemptOut; error?: unknown; onRetry: () => void; onNext: () => void; nextDisabled?: boolean; clockLabel?: string }) {
  const ucis = tactic.solution.moves.map((m) => m.uci);
  const clean = attempt && attempt.correct && !attempt.used_hint;
  const exploreHref = `/analise?fen=${encodeURIComponent(tactic.fen_start)}&orientation=${tactic.side_to_move}&back=${encodeURIComponent("/treinar")}`;
  return (
    <div className="two-col">
      <div>
        <LineViewer fenStart={tactic.fen_start} ucis={ucis} orientation={tactic.side_to_move}
          startPly={startPlyFromFen(tactic.fen_start)} initialPos={tactic.solution.moves.length} />
      </div>
      <div className="card">
        {clockLabel && <div className="row"><span className="muted" aria-label="relógio">{clockLabel}</span></div>}
        {!!error && (<><ErrorBox error={error} /><button onClick={onRetry}>Tentar registrar de novo</button></>)}
        {attempt && (
          <>
            <div className={`msg ${clean ? "ok" : "bad"}`}>{clean ? "Resolvido sem erro." : "Concluído, mas contou como erro."}</div>
            <div className="muted">{`Rating ${attempt.rating_before} → ${attempt.rating_after} (${signed(attempt.delta)})`}</div>
          </>
        )}
        <div style={{ marginTop: 10 }}>
          {tactic.themes.map((t) => <span key={t} className="tag">{themeLabel(t)}</span>)}
          <span className="tag">rating {tactic.rating}</span>
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <a href={tactic.lichess_url} target="_blank" rel="noopener noreferrer">ver no Lichess</a>
          <a href={exploreHref} target="_blank" rel="noopener noreferrer">Explorar</a>
          <QueueButtons puzzle={tactic} />
          {attempt && <button className="primary" style={{ marginLeft: "auto" }} disabled={nextDisabled} onClick={onNext}>{nextDisabled ? "Carregando…" : "Próximo"}</button>}
        </div>
      </div>
    </div>
  );
}
