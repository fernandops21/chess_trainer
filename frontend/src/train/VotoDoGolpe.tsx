import { useState } from "react";
import { useGolpeVoto, useVotarGolpe } from "../api/queries";
import type { Procedencia } from "../api/types";

/** Um botão de voto: o texto visível e o valor gravado. */
const ROTULOS: { label: "mesmo" | "parecido" | "nada"; texto: string }[] = [
  { label: "mesmo", texto: "mesmo golpe" },
  { label: "parecido", texto: "parecido" },
  { label: "nada", texto: "nada a ver" },
];

/**
 * Voto sobre um irmão do bloco: "tem a ver com o erro que o usuário treinou?" (spec golpes
 * trechos §8, revisão "o voto mora no bloco" — julgar "é o mesmo golpe?" exige jogar o
 * irmão, e é isso que o bloco já faz; a tela de rotulagem à parte saiu).
 *
 * Opcional: "Próximo" funciona sem votar. Nunca mostra a procedência (degrau, nível,
 * posição do trecho) nem a `tier` — elas só viajam junto do voto para o placar de
 * Configurações, sem aparecer para quem vota.
 */
export function VotoDoGolpe({ anchorOrigem, anchorId, candidateId, procedencia, tier, onVotado }:
  { anchorOrigem: "own" | "lichess"; anchorId: string; candidateId: string; procedencia?: Procedencia; tier: string;
    /** chamado depois que o voto grava: no bloco, votar já leva ao próximo irmão */
    onVotado?: () => void }) {
  const { data } = useGolpeVoto(anchorOrigem, anchorId, candidateId);
  const votar = useVotarGolpe();
  const [erro, setErro] = useState(false);
  const escolhido = data?.label ?? null;

  async function votarEm(label: "mesmo" | "parecido" | "nada") {
    setErro(false);
    try {
      await votar.mutateAsync({
        anchor_origem: anchorOrigem,
        anchor_id: anchorId,
        candidate_id: candidateId,
        tier,
        label,
        n_lances: procedencia?.n,
        posicao: procedencia?.posicao,
        nivel: procedencia?.nivel,
        espelhado: procedencia?.espelhado,
      });
      onVotado?.();
    } catch {
      // a marca anterior fica como está: só o aviso muda
      setErro(true);
    }
  }

  return (
    <div className="card">
      <h4 style={{ marginTop: 0 }}>Tem a ver com o seu erro?</h4>
      {erro && <p className="muted">Não consegui gravar o voto.</p>}
      <div className="row">
        {ROTULOS.map((r) => (
          <button
            key={r.label}
            aria-pressed={escolhido === r.label}
            className={escolhido === r.label ? "primary" : undefined}
            disabled={votar.isPending}
            onClick={() => void votarEm(r.label)}
          >
            {r.texto}
          </button>
        ))}
      </div>
    </div>
  );
}
