import { useState } from "react";
import { useCancelJob, useStartJob, useStatus } from "../api/queries";
import { ErrorBox } from "./ErrorBox";
import { storage } from "../lib/storage";

const JOB_LABEL: Record<string, string> = {
  import: "Importação",
  analyze: "Análise",
  regenerate: "Recriação de todos os puzzles",
  regenerate_avoid: "Recriação dos puzzles evitar",
  import_lichess: "Importação das táticas do Lichess",
  import_study: "Importação de estudo do Lichess",
};

const JOB_RUNNING_HINT: Record<string, string> = {
  regenerate: "apaga os exercícios das suas partidas e gera de novo com as regras atuais; táticas e estudos ficam",
  regenerate_avoid: "apaga só os puzzles evitar das suas partidas e gera de novo; os punir e o histórico ficam",
  import_lichess: "baixa o banco (~300 MB) e importa as táticas filtradas; leva uns 5 minutos",
  import_study: "baixa o PGN do estudo e cria um exercício por capítulo",
};

/** Até onde o cancelamento deixa a tarefa chegar: cada job para num ponto diferente. */
const CANCEL_LABEL: Record<string, [string, string]> = {
  import_lichess: ["Cancelar (após o lote atual)", "Cancelando… termina o lote atual e para"],
  // o estudo é gravado de uma vez no fim: cancelar antes disso não deixa nada pela metade
  import_study: ["Cancelar (antes de gravar)", "Cancelando… o estudo não será gravado"],
  import: ["Cancelar (após a partida atual)", "Cancelando… termina a partida atual e para"],
  analyze: ["Cancelar (após a partida atual)", "Cancelando… termina a partida atual e para"],
  regenerate: ["Cancelar (após a partida atual)", "Cancelando… termina a partida atual e para"],
  regenerate_avoid: ["Cancelar (após a partida atual)", "Cancelando… termina a partida atual e para"],
};
const CANCEL_FALLBACK: [string, string] = ["Cancelar", "Cancelando…"];

export function JobCard() {
  const { data: status } = useStatus();
  const start = useStartJob();
  const cancel = useCancelJob();
  const [n, setN] = useState<number>(storage.get("dashboard.analyzeN", 5));
  if (!status) return null;
  const job = status.job;
  const running = job.state === "running";
  const pct = job.total > 0 ? Math.round((100 * job.done) / job.total) : 0;
  // A importação das táticas não sabe o total de linhas: barra indeterminada e só a mensagem.
  const unknownTotal = job.total === 0;
  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>Tarefas</h3>
      {running && (
        <>
          <div>
            {JOB_LABEL[job.job ?? ""] ?? job.job} em andamento:{" "}
            {unknownTotal ? <span className="muted">{job.message}</span> : <>{job.done}/{job.total} {job.message && <span className="muted">· {job.message}</span>}</>}
            {job.job && JOB_RUNNING_HINT[job.job] && <div className="muted">{JOB_RUNNING_HINT[job.job]}</div>}
          </div>
          {unknownTotal
            ? <progress style={{ width: "100%" }} aria-label="em andamento" />
            : <progress value={job.done} max={Math.max(job.total, 1)} style={{ width: "100%" }} aria-label={`${pct}%`} />}
          <button className="danger" onClick={() => cancel.mutate()} disabled={cancel.isPending || job.cancel_requested}>
            {(CANCEL_LABEL[job.job ?? ""] ?? CANCEL_FALLBACK)[job.cancel_requested ? 1 : 0]}
          </button>
        </>
      )}
      {!running && job.state === "error" && <ErrorBox error={new Error(`${JOB_LABEL[job.job ?? ""] ?? "Tarefa"} falhou: ${job.error}`)} />}
      {!running && job.state === "idle" && job.job && <div className="muted">Última tarefa: {JOB_LABEL[job.job] ?? job.job} · {job.message}</div>}
      {!running && (
        <div className="row" style={{ marginTop: 10 }}>
          <button onClick={() => start.mutate({ kind: "import" })} disabled={start.isPending}>Importar agora</button>
          <button className="primary" onClick={() => start.mutate({ kind: "analyze", limit: n })} disabled={start.isPending || !status.engine.available}>Analisar</button>
          <input type="number" min={1} max={200} value={n} style={{ width: 80 }} aria-label="Quantas partidas"
            onChange={(e) => { const v = Math.min(200, Math.max(1, Number(e.target.value) || 1)); setN(v); storage.set("dashboard.analyzeN", v); }} />
          <span className="muted">partidas pendentes: {status.games_pending}</span>
        </div>
      )}
      <ErrorBox error={start.error ?? cancel.error} />
    </div>
  );
}
