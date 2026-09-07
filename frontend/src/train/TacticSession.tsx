import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";
import { useTacticsStatus } from "../api/queries";
import type { AttemptOut, ReviewIn, SessionOut, TacticOut } from "../api/types";
import { ErrorBox } from "../components/ErrorBox";
import { Modal } from "../components/Modal";
import { PuzzleView } from "./PuzzleView";
import type { SessionConfig } from "./SessionStart";
import { TacticResultPanel } from "./TacticResultPanel";
import type { TacticDone } from "./TacticSummary";
import { usePuzzle } from "./usePuzzle";
import { mmss, useSessionClock } from "./useSessionClock";

export interface TacticSummaryData {
  done: TacticDone[];
  elapsedLabel: string;
  reason: string;
  ratingStart: number;
  ratingEnd: number;
}

const DEFAULT_RATING = 1200;

/** Uma tática da sessão: monta usePuzzle com key = tactic.id para reiniciar o estado a cada tática. */
function TacticPuzzle({ tactic, sessionId, clockLabel, orderInfo, onDone, nextDisabled }:
  { tactic: TacticOut; sessionId: string | null; clockLabel?: string; orderInfo?: string; onDone: (d: TacticDone) => void; nextDisabled?: boolean }) {
  const qc = useQueryClient();
  // o tempo de resolução não volta na tentativa: guardamos o que foi enviado
  // para que "Guardar para repetir" mande o resultado completo
  const durationRef = useRef<number | undefined>(undefined);
  const submit = useCallback(async (body: ReviewIn) => {
    durationRef.current = body.duration_ms;
    const out = await api.attempt(body);
    // a tentativa mexe no rating e nas estatísticas por tema
    void qc.invalidateQueries({ queryKey: ["tactics"] });
    void qc.invalidateQueries({ queryKey: ["stats"] });
    return out;
  }, [qc]);
  const ctl = usePuzzle<AttemptOut>(tactic, { sessionId, submit });
  const { state } = ctl;
  if (state.phase === "result" || state.phase === "submit_error" || state.phase === "submitting") {
    return <TacticResultPanel tactic={tactic} attempt={state.review} durationMs={durationRef.current} error={state.error} onRetry={ctl.retrySubmit}
      onNext={() => state.review && onDone({ tactic, attempt: state.review })} nextDisabled={nextDisabled} clockLabel={clockLabel} />;
  }
  return <PuzzleView puzzle={tactic} ctl={ctl} clockLabel={clockLabel} orderInfo={orderInfo} />;
}

export function TacticSession({ config, onFinish }: { config: SessionConfig; onFinish: (s: TacticSummaryData) => void }) {
  const qc = useQueryClient();
  const [session, setSession] = useState<SessionOut | null>(null);
  const [tactic, setTactic] = useState<TacticOut | null>(null);
  const [done, setDone] = useState<TacticDone[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [askContinue, setAskContinue] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const clock = useSessionClock(config.plannedMinutes);
  const { data: status } = useTacticsStatus();
  const startRating = status?.rating ?? DEFAULT_RATING;
  // a fila é infinita: não repetir o que já apareceu nesta sessão
  const seen = useRef<string[]>([]);
  const sessionRef = useRef<SessionOut | null>(null);
  const finished = useRef(false);
  // `finish` é chamado a partir de closures async (efeito de início, `goNext`) que podem ter
  // capturado uma versão antiga de `finish`/`startRating`; o ref garante que ele sempre lê o
  // rating do status mais recente, mesmo que o status só tenha chegado depois do começo.
  const startRatingRef = useRef(startRating);
  startRatingRef.current = startRating;
  // limite de ids em `exclude` para manter a query string com tamanho previsível
  const MAX_EXCLUDE = 200;
  const excludeIds = () => seen.current.slice(-MAX_EXCLUDE);
  // Mesma proteção do treino próprio: sob StrictMode o efeito roda duas vezes
  // e a segunda execução precisa se reinscrever no mesmo request.
  const startP = useRef<Promise<[SessionOut, TacticOut]> | null>(null);

  const arrive = (t: TacticOut) => {
    if (!seen.current.includes(t.id)) seen.current.push(t.id);
    setTactic(t);
  };

  const finish = useCallback(async (reason: string, all: TacticDone[]) => {
    if (finished.current) return;
    finished.current = true;
    clock.stop();
    try { if (sessionRef.current) await api.endSession(sessionRef.current.id); } catch { /* resumo mesmo assim */ }
    void qc.invalidateQueries();
    onFinish({
      done: all,
      elapsedLabel: mmss(clock.elapsedMs),
      reason,
      ratingStart: all.length ? all[0].attempt.rating_before : startRatingRef.current,
      ratingEnd: all.length ? all[all.length - 1].attempt.rating_after : startRatingRef.current,
    });
  }, [clock, onFinish, qc]);

  useEffect(() => {
    startP.current ??= (async () => {
      const s = await api.createSession({ planned_minutes: config.plannedMinutes, filters: { source: "tactics", themes: config.themes } });
      sessionRef.current = s;
      return [s, await api.nextTactic({ themes: config.themes, exclude: excludeIds() })] as [SessionOut, TacticOut];
    })();
    let alive = true;
    startP.current.then(
      ([s, t]) => { if (alive) { setSession(s); arrive(t); } },
      (e) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 404) void finish(e.message, []);
        else setError(e);
      },
    );
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  const goNext = async (all: TacticDone[]) => {
    try {
      arrive(await api.nextTactic({ themes: config.themes, exclude: excludeIds() }));
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) await finish(e.message, all);
      else await finish("Não foi possível buscar a próxima tática.", all);
    }
  };

  const advance = async (d: TacticDone) => {
    const all = [...done, d];
    setDone(all);
    if (clock.expired) { setAskContinue(true); return; }
    setAdvancing(true);
    try {
      await goNext(all);
    } finally {
      setAdvancing(false);
    }
  };

  if (error) return <ErrorBox error={error} />;
  if (!tactic || !session) return <p className="muted">Preparando a sessão…</p>;
  const rating = done.length ? done[done.length - 1].attempt.rating_after : startRating;
  return (
    <>
      <TacticPuzzle key={tactic.id} tactic={tactic} sessionId={session.id} clockLabel={clock.label}
        orderInfo={`${done.length + 1}ª tática · rating ${rating}`} onDone={advance} nextDisabled={advancing} />
      <div className="row"><button onClick={() => void finish("Sessão encerrada.", done)}>Encerrar sessão</button></div>
      <Modal open={askContinue} title="Tempo esgotado">
        <p>O tempo planejado acabou. Continuar ou encerrar?</p>
        <div className="row">
          <button className="primary" onClick={() => {
            clock.continueSession(); setAskContinue(false);
            // mesmo bloqueio do avanço normal: sem ele o Próximo segue clicável durante a
            // busca e um segundo clique registraria o mesmo resultado duas vezes
            setAdvancing(true);
            void goNext(done).finally(() => setAdvancing(false));
          }}>Continuar</button>
          <button onClick={() => { setAskContinue(false); void finish("Tempo esgotado.", done); }}>Encerrar</button>
        </div>
      </Modal>
    </>
  );
}
