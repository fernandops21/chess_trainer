import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useSettings, useStudy } from "../api/queries";
import type { PuzzleOut, QueueOut, ReviewIn, SessionOut } from "../api/types";
import { ErrorBox } from "../components/ErrorBox";
import { Modal } from "../components/Modal";
import { PuzzleView } from "./PuzzleView";
import { ResultPanel } from "./ResultPanel";
import type { SessionConfig } from "./SessionStart";
import type { Done } from "./SessionSummary";
import { useEndOnExit } from "./useEndOnExit";
import { usePuzzle } from "./usePuzzle";
import { mmss, useSessionClock } from "./useSessionClock";

/** Um puzzle da sessão: monta usePuzzle com key = puzzle.id para reiniciar o estado a cada puzzle. */
export function SessionPuzzle({ puzzle, sessionId, clockLabel, orderInfo, onDone, presetHint, nextLabel, nextDisabled, onSkip, skipDisabled }:
  { puzzle: PuzzleOut; sessionId: string | null; clockLabel?: string; orderInfo?: string; onDone: (d: Done) => void; presetHint?: boolean; nextLabel?: string; nextDisabled?: boolean; onSkip?: () => void; skipDisabled?: boolean }) {
  const qc = useQueryClient();
  const submit = useCallback(async (body: ReviewIn) => {
    const out = await api.review(body);
    // a revisão muda o SRS: painel e fila precisam refletir isso
    void qc.invalidateQueries({ queryKey: ["dashboard"] });
    void qc.invalidateQueries({ queryKey: ["queue"] });
    return out;
  }, [qc]);
  // enquanto as configurações não chegam, a refutação fica ligada (é o padrão)
  const { data: settings } = useSettings();
  const ctl = usePuzzle(puzzle, { sessionId, submit, presetHint, refute: settings?.refute_wrong_moves ?? true });
  const { state } = ctl;
  if (state.phase === "result" || state.phase === "submit_error" || state.phase === "submitting") {
    return <ResultPanel puzzle={puzzle} review={state.review} error={state.error} onRetry={ctl.retrySubmit}
      onNext={() => state.review && onDone({ puzzle, review: state.review })} nextLabel={nextLabel} nextDisabled={nextDisabled} clockLabel={clockLabel} />;
  }
  return <PuzzleView puzzle={puzzle} ctl={ctl} clockLabel={clockLabel} orderInfo={orderInfo} onSkip={onSkip} skipDisabled={skipDisabled} />;
}

/** Mensagem de fila vazia conforme o modo. */
export function emptyMessage(mode: SessionConfig["mode"], queue: QueueOut): string {
  if (mode === "study") return "Este estudo não tem exercícios na repetição.";
  if (mode === "new") {
    return queue.new_available === 0
      ? "Sem erros novos."
      : `Sem erros novos (ou limite diário atingido: ${queue.new_available} esperando amanhã).`;
  }
  return "Nada vencido. Faça novos ou treine um estudo.";
}

export function Session({ config, onFinish, emptyActions }:
  { config: SessionConfig; onFinish: (done: Done[], elapsedLabel: string, reason: string) => void; emptyActions?: ReactNode }) {
  const qc = useQueryClient();
  const [session, setSession] = useState<SessionOut | null>(null);
  const [queue, setQueue] = useState<QueueOut | null>(null);
  // a lista fica no estado: pular reordena os itens sem tocar na fila do servidor
  const [items, setItems] = useState<PuzzleOut[]>([]);
  const [i, setI] = useState(0);
  const [skipped, setSkipped] = useState(0);
  const [done, setDone] = useState<Done[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [askContinue, setAskContinue] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const clock = useSessionClock(config.plannedMinutes);
  // Guarda a promessa em andamento (não um booleano): sob StrictMode o efeito
  // roda duas vezes e a segunda execução precisa se reinscrever no mesmo
  // request, senão o resultado cai numa closure já morta.
  const startP = useRef<Promise<[SessionOut, QueueOut]> | null>(null);
  // a sessão criada e se ela já foi encerrada no servidor: sair da tela encerra,
  // e terminar normalmente também — nenhuma das duas pode encerrar duas vezes
  const sessionRef = useRef<SessionOut | null>(null);
  const endedRef = useRef(false);
  useEndOnExit(sessionRef, endedRef);
  // posição de cada puzzle na primeira carga: usada para o "capítulo N de M" do
  // estudo continuar certo depois de um pulo reordenar `items`
  const ordemInicial = useRef<Map<string, number>>(new Map());
  // o título do estudo só é buscado no modo estudo
  const { data: study } = useStudy(config.mode === "study" ? config.filters.study_id ?? null : null);
  const heading = config.mode === "new" ? "Novos (meus erros)"
    : config.mode === "study" ? study?.title ?? "Estudo"
      : "Repetição espaçada";

  useEffect(() => {
    startP.current ??= (async () => {
      const s = await api.createSession({ planned_minutes: config.plannedMinutes, filters: config.filters as Record<string, unknown> });
      sessionRef.current = s;
      return [s, await api.queue(config.filters)] as [SessionOut, QueueOut];
    })();
    let alive = true;
    startP.current.then(
      ([s, q]) => {
        if (!alive) return;
        setSession(s); setQueue(q); setItems(q.items);
        ordemInicial.current = new Map(q.items.map((p, idx) => [p.id, idx]));
      },
      (e) => { if (alive) setError(e); },
    );
    return () => { alive = false; };
  }, [config]);

  const finish = useCallback(async (reason: string, all: Done[]) => {
    clock.stop();
    try {
      if (session && !endedRef.current) { endedRef.current = true; await api.endSession(session.id); }
    } catch { /* resumo mesmo assim */ }
    void qc.invalidateQueries();
    onFinish(all, mmss(clock.elapsedMs), reason);
  }, [session, clock, onFinish, qc]);

  const advance = async (d: Done) => {
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

  const goNext = async (all: Done[]) => {
    if (!queue) return;
    if (i + 1 < items.length) { setI(i + 1); return; }
    if (config.mode === "study") {
      // a fila do estudo é fixa (o backend sempre devolve o estudo inteiro), então
      // recarregar aqui só repetiria os mesmos exercícios: terminado o último item
      // da lista (e nada pendente segundo `all`), a sessão acaba
      const resolvidosAgora = new Set(all.map((d) => d.puzzle.id));
      const pendente = items.findIndex((p) => !resolvidosAgora.has(p.id));
      if (pendente === -1) await finish("Estudo concluído.", all);
      else setI(pendente); // sobrou algo pendente (não deveria): vai até ele em vez de travar
      return;
    }
    try {
      const q = await api.queue(config.filters);
      // um puzzle já resolvido nesta sessão pode voltar a aparecer na fila
      // recarregada (ex.: lapso com intervalo zerado) — não serve de novo
      const resolvidosAgora = new Set(all.map((d) => d.puzzle.id));
      const restantes = q.items.filter((p) => !resolvidosAgora.has(p.id));
      if (restantes.length === 0) { await finish("Fila vazia por hoje.", all); return; }
      setQueue(q); setItems(restantes); setI(0);
    } catch {
      await finish("Não foi possível recarregar a fila.", all);
    }
  };

  // Quem já foi respondido continua na lista (o resumo e a ordem da sessão
  // saem de `done`), então pular só pode andar entre os que ainda faltam:
  // voltar a um resolvido registraria uma segunda revisão do mesmo puzzle.
  const resolvidos = new Set(done.map((d) => d.puzzle.id));
  const pendentes = items.filter((p) => !resolvidos.has(p.id)).length;

  // pular não registra revisão: manda o puzzle para o fim da lista e segue para o próximo
  const skip = () => {
    if (pendentes < 2) return;
    const rest = [...items.slice(0, i), ...items.slice(i + 1)];
    const novos = [...rest, items[i]];
    // o próximo já ocupa a posição `i`; se o pulado era o último, volta ao
    // começo — e, de um jeito ou de outro, passa por cima dos já resolvidos
    // (o pulado espera no fim, então a volta sempre termina)
    let j = i >= rest.length ? 0 : i;
    while (resolvidos.has(novos[j].id)) j = (j + 1) % novos.length;
    setItems(novos);
    setI(j);
    setSkipped(skipped + 1);
  };

  if (error) return <ErrorBox error={error} />;
  if (!queue || !session) return <p className="muted">Preparando a sessão…</p>;
  if (items.length === 0) {
    return (
      <div className="card">
        <h2 style={{ marginTop: 0 }}>{heading}</h2>
        <p>{emptyMessage(config.mode, queue)}</p>
        {emptyActions ?? <Link to="/">Analisar mais partidas</Link>}
      </div>
    );
  }
  const puzzle = items[i];
  // o capítulo exibido é a posição original do puzzle no estudo, não a posição
  // atual em `items` (que muda a cada pulo)
  const capitulo = (ordemInicial.current.get(puzzle.id) ?? i) + 1;
  const orderInfo = (config.mode === "study"
    ? `capítulo ${capitulo} de ${items.length}`
    : `${done.length + 1}º da sessão · ${queue.due_count} vencidos`)
    + (skipped > 0 ? ` · ${skipped} ${skipped === 1 ? "pulado" : "pulados"}` : "");
  return (
    <>
      <h2 style={{ marginTop: 0 }}>{heading}</h2>
      <SessionPuzzle key={puzzle.id} puzzle={puzzle} sessionId={session.id} clockLabel={clock.label}
        orderInfo={orderInfo} onDone={advance} nextDisabled={advancing}
        onSkip={skip} skipDisabled={pendentes < 2} />
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
