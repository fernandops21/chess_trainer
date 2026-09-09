import { useMemo } from "react";
import type { AttemptOut, TacticOut } from "../api/types";
import { AnalysisBoard } from "../analysis/AnalysisBoard";
import { treeFromSolution, withPlayedLine } from "../analysis/solutionTree";
import { ErrorBox } from "../components/ErrorBox";
import { themeLabel } from "../lib/format";
import { QueueButtons } from "./QueueButtons";

const signed = (n: number) => (n > 0 ? `+${n}` : String(n));

export function TacticResultPanel({ tactic, attempt, played, durationMs, error, onRetry, onNext, nextDisabled, clockLabel }:
  { tactic: TacticOut; attempt?: AttemptOut; played?: string[]; durationMs?: number; error?: unknown; onRetry: () => void; onNext: () => void; nextDisabled?: boolean; clockLabel?: string }) {
  const clean = attempt && attempt.correct && !attempt.used_hint;
  const exploreHref = `/analise?fen=${encodeURIComponent(tactic.fen_start)}&orientation=${tactic.side_to_move}&back=${encodeURIComponent("/treinar")}`;
  // a solução vira a árvore do tabuleiro de análise: dá para sair da linha e
  // experimentar qualquer lance, sem pedir nada à engine antes de o usuário querer
  const { tree, alternativa } = useMemo(() => {
    const base = treeFromSolution(tactic);
    const jogada = played && played.length
      ? withPlayedLine(base, tactic.solution.moves.map((m) => m.uci), played, "Alternativa: também resolve. A linha principal segue ao lado.")
      : { tree: base, lastId: null, divergiu: false };
    return { tree: jogada.tree, alternativa: jogada.divergiu ? jogada.lastId : null };
  }, [tactic, played]);
  // mesma disposição do resultado dos exercícios: o cartão vai ao lado do
  // tabuleiro, não em cima dele
  const lateral = (
    <>
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
          {/* guardar leva o resultado da tentativa: a tática já entra agendada */}
          <QueueButtons puzzle={tactic} attempt={attempt} durationMs={durationMs} />
          {attempt && <button className="primary" style={{ marginLeft: "auto" }} disabled={nextDisabled} onClick={onNext}>{nextDisabled ? "Carregando…" : "Próximo"}</button>}
        </div>
      </div>
    </>
  );
  return <AnalysisBoard tree={tree} initialNodeId={alternativa ?? "last"} engine={false} allowSetup={false} sidePanel={lateral} />;
}
