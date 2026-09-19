import type { AttemptOut, TacticOut } from "../api/types";
import { themeLabel } from "../lib/format";
import { storage } from "../lib/storage";

export interface TacticDone { tactic: TacticOut; attempt: AttemptOut }

export function TacticSummary({ done, elapsedLabel, reason, ratingStart, ratingEnd, onNew, onVoltar, voltarLabel }:
  { done: TacticDone[]; elapsedLabel: string; reason: string; ratingStart: number; ratingEnd: number; onNew: () => void; onVoltar?: () => void; voltarLabel?: string }) {
  const clean = (d: TacticDone) => d.attempt.correct && !d.attempt.used_hint;
  const ok = done.filter(clean);
  const failed = done.filter((d) => !clean(d));
  // a sessão acabou porque nenhum candidato bateu com os temas: oferecer recomeçar sem eles
  const noCandidates = reason.toLowerCase().includes("nenhuma tática disponível");
  return (
    <div className="card">
      {/* `onVoltar` só existe quando este resumo é o de um bloco de irmãos: aí quem acabou foi o
         bloco, não o treino — "Sessão encerrada" dava a entender o contrário */}
      <h2 style={{ marginTop: 0 }}>{onVoltar ? "Bloco concluído" : "Sessão encerrada"}</h2>
      <div className="muted">{onVoltar ? "Os irmãos entraram na sua fila de repetição. O botão abaixo leva de volta para onde você estava." : reason}</div>
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
      <div className="row">
        {/* o cartão do golpe trocou a sessão em andamento pelo bloco de irmãos (spec §6):
           "Voltar ao treino" retoma de onde o bloco interrompeu, em vez de descartá-la */}
        {onVoltar
          ? <button className="primary" onClick={onVoltar}>{voltarLabel ?? "Voltar ao treino"}</button>
          : <button className="primary" onClick={onNew}>Nova sessão</button>}
        {noCandidates && <button onClick={() => { storage.set("train.themes", []); onNew(); }}>Nova sessão sem temas</button>}
      </div>
    </div>
  );
}
