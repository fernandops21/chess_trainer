import { useState } from "react";
import { useSaveTactic, useSetQueue } from "../api/queries";
import type { PuzzleOut, TacticOut, Trainable } from "../api/types";

/**
 * Botões de fila do exercício mostrado.
 *
 * Puzzle da repetição: tira/devolve à fila. Tática do banco do Lichess:
 * guarda como exercício da repetição (uma vez só). O rótulo muda na hora
 * (estado local otimista) e volta ao anterior se a chamada falhar.
 */
export function QueueButtons({ puzzle }: { puzzle: Trainable }) {
  return puzzle.kind === "tactic" ? <SaveTactic tactic={puzzle} /> : <ToggleQueue puzzle={puzzle} />;
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

function SaveTactic({ tactic }: { tactic: TacticOut }) {
  const [saved, setSaved] = useState(tactic.saved);
  const m = useSaveTactic();
  if (saved) return <button disabled>Guardado ✓</button>;
  return (
    <button onClick={() => m.mutate(tactic.id, { onSuccess: () => setSaved(true) })} disabled={m.isPending}>
      Guardar para repetir
    </button>
  );
}
