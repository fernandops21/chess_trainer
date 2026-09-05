import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { usePuzzleQuery } from "../api/queries";
import type { PuzzleOut, QueueOut, ReviewIn, SessionOut } from "../api/types";
import { ErrorBox } from "../components/ErrorBox";
import { Modal } from "../components/Modal";
import { PuzzleView } from "./PuzzleView";
import { ResultPanel } from "./ResultPanel";
import { SessionStart, type SessionConfig } from "./SessionStart";
import { SessionSummary, type Done } from "./SessionSummary";
import { usePuzzle } from "./usePuzzle";
import { mmss, useSessionClock } from "./useSessionClock";

/** Um puzzle da sessão: monta usePuzzle com key = puzzle.id para reiniciar o estado a cada puzzle. */
function SessionPuzzle({ puzzle, sessionId, clockLabel, orderInfo, onDone, presetHint, nextLabel }:
  { puzzle: PuzzleOut; sessionId: string | null; clockLabel?: string; orderInfo?: string; onDone: (d: Done) => void; presetHint?: boolean; nextLabel?: string }) {
  const submit = useCallback((body: ReviewIn) => api.review(body), []);
  const ctl = usePuzzle(puzzle, { sessionId, submit, presetHint });
  const { state } = ctl;
  if (state.phase === "result" || state.phase === "submit_error" || state.phase === "submitting") {
    return <ResultPanel puzzle={puzzle} review={state.review} error={state.error} onRetry={ctl.retrySubmit}
      onNext={() => state.review && onDone({ puzzle, review: state.review })} nextLabel={nextLabel} />;
  }
  return <PuzzleView puzzle={puzzle} ctl={ctl} clockLabel={clockLabel} orderInfo={orderInfo} />;
}

function SingleTrain({ id, seen }: { id: string; seen: boolean }) {
  const nav = useNavigate();
  const { data, error, isLoading } = usePuzzleQuery(id);
  if (isLoading) return <p className="muted">Carregando…</p>;
  if (error || !data) return <ErrorBox error={error ?? new Error("Puzzle não encontrado")} />;
  return <SessionPuzzle puzzle={data} sessionId={null} presetHint={seen} nextLabel="Voltar" onDone={() => nav(-1)} />;
}

function Session({ config, onFinish }: { config: SessionConfig; onFinish: (done: Done[], elapsedLabel: string, reason: string) => void }) {
  const qc = useQueryClient();
  const [session, setSession] = useState<SessionOut | null>(null);
  const [queue, setQueue] = useState<QueueOut | null>(null);
  const [i, setI] = useState(0);
  const [done, setDone] = useState<Done[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [askContinue, setAskContinue] = useState(false);
  const clock = useSessionClock(config.plannedMinutes);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const s = await api.createSession({ planned_minutes: config.plannedMinutes, filters: config.filters as Record<string, unknown> });
        const q = await api.queue(config.filters);
        if (alive) { setSession(s); setQueue(q); }
      } catch (e) { if (alive) setError(e); }
    })();
    return () => { alive = false; };
  }, [config]);

  const finish = useCallback(async (reason: string, all: Done[]) => {
    clock.stop();
    try { if (session) await api.endSession(session.id); } catch { /* resumo mesmo assim */ }
    void qc.invalidateQueries();
    onFinish(all, mmss(clock.elapsedMs), reason);
  }, [session, clock, onFinish, qc]);

  const advance = async (d: Done) => {
    const all = [...done, d];
    setDone(all);
    if (clock.expired) { setAskContinue(true); return; }
    await goNext(all);
  };

  const goNext = async (all: Done[]) => {
    if (!queue) return;
    if (i + 1 < queue.items.length) { setI(i + 1); return; }
    try {
      const q = await api.queue(config.filters);
      if (q.items.length === 0) { await finish("Fila vazia por hoje.", all); return; }
      setQueue(q); setI(0);
    } catch (e) { setError(e); }
  };

  if (error) return <ErrorBox error={error} />;
  if (!queue || !session) return <p className="muted">Preparando a sessão…</p>;
  if (queue.items.length === 0) {
    const reason = queue.new_available > 0 && queue.new_remaining_today === 0
      ? `Limite diário de novos atingido; há ${queue.new_available} esperando amanhã.` : "Nada vencido e nenhum puzzle novo disponível.";
    return <div className="card"><p>{reason}</p><Link to="/">Analisar mais partidas</Link></div>;
  }
  const puzzle = queue.items[i];
  return (
    <>
      <SessionPuzzle key={puzzle.id} puzzle={puzzle} sessionId={session.id} clockLabel={clock.label}
        orderInfo={`${done.length + 1}º da sessão · ${queue.due_count} vencidos`} onDone={advance} />
      <Modal open={askContinue} title="Tempo esgotado">
        <p>O tempo planejado acabou. Continuar ou encerrar?</p>
        <div className="row">
          <button className="primary" onClick={() => { clock.continueSession(); setAskContinue(false); void goNext(done); }}>Continuar</button>
          <button onClick={() => { setAskContinue(false); void finish("Tempo esgotado.", done); }}>Encerrar</button>
        </div>
      </Modal>
    </>
  );
}

export function TrainPage() {
  const [params] = useSearchParams();
  const single = params.get("puzzle");
  const [config, setConfig] = useState<SessionConfig | null>(null);
  const [summary, setSummary] = useState<{ done: Done[]; elapsedLabel: string; reason: string } | null>(null);

  if (single) return <><h1>Treinar</h1><SingleTrain id={single} seen={params.get("seen") === "1"} /></>;
  return (
    <>
      <h1>Treinar</h1>
      {summary ? <SessionSummary {...summary} onNew={() => { setSummary(null); setConfig(null); }} />
        : config ? <Session config={config} onFinish={(done, elapsedLabel, reason) => { setSummary({ done, elapsedLabel, reason }); }} />
        : <SessionStart onStart={setConfig} />}
    </>
  );
}
