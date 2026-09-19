import { useState } from "react";
import { useSaveTactic, useSetQueue } from "../api/queries";
import type { AttemptOut, PuzzleOut, SaveTacticIn, TacticOut, Trainable } from "../api/types";

/**
 * Botões de fila do exercício mostrado.
 *
 * Puzzle da repetição: tira/devolve à fila. Tática do banco do Lichess:
 * guarda como exercício da repetição (uma vez só). O rótulo muda na hora
 * (estado local otimista) e volta ao anterior se a chamada falhar.
 *
 * `attempt` é o resultado da tentativa que está na tela: com ele a tática
 * guardada já entra agendada (a tentativa vale como primeira revisão).
 */
export function QueueButtons({ puzzle, attempt, durationMs, jaGuardado }:
  { puzzle: Trainable; attempt?: AttemptOut; durationMs?: number; jaGuardado?: boolean }) {
  return puzzle.kind === "tactic"
    ? <SaveTactic tactic={puzzle} attempt={attempt} durationMs={durationMs} jaGuardado={jaGuardado} />
    : <ToggleQueue puzzle={puzzle} />;
}

function ToggleQueue({ puzzle }: { puzzle: PuzzleOut }) {
  const [inQueue, setInQueue] = useState(puzzle.in_queue);
  const m = useSetQueue();
  const toggle = () => {
    const next = !inQueue;
    setInQueue(next);
    m.mutate({ id: puzzle.id, in_queue: next }, {
      onSuccess: (out) => setInQueue(out.in_queue),
      onError: () => setInQueue(!next),
    });
  };
  return (
    <button onClick={toggle} disabled={m.isPending}>
      {inQueue ? "Tirar da repetição" : "Voltar para a repetição"}
    </button>
  );
}

function SaveTactic({ tactic, attempt, durationMs, jaGuardado }: { tactic: TacticOut; attempt?: AttemptOut; durationMs?: number; jaGuardado?: boolean }) {
  const [saved, setSaved] = useState(tactic.saved);
  const m = useSaveTactic();
  // `jaGuardado`: quem chamou já pôs a tática na fila (o bloco de irmãos faz isso sozinho a cada
  // tentativa) — chega depois da montagem, por isso não pode ser só o valor inicial do estado
  if (saved || jaGuardado) return <button disabled>Guardado ✓</button>;
  const body: SaveTacticIn | undefined = attempt
    ? { correct: attempt.correct, used_hint: attempt.used_hint, duration_ms: durationMs }
    : undefined;
  return (
    <button onClick={() => m.mutate({ id: tactic.id, body }, { onSuccess: () => setSaved(true) })} disabled={m.isPending}>
      Guardar para repetir
    </button>
  );
}
