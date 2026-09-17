import { useEffect, useState } from "react";
import { golpeImagemUrl } from "../api/client";
import { useGolpesStatus, useRotulagemContagem, useRotulagemProximo, useRotular } from "../api/queries";
import type { RotulagemItem, RotuloIn } from "../api/types";

/** Um botão de rótulo: o texto visível e o valor gravado (nunca a `tier` do candidato). */
const ROTULOS: { label: RotuloIn["label"]; texto: string }[] = [
  { label: "mesmo", texto: "mesmo golpe" },
  { label: "parecido", texto: "parecido" },
  { label: "nada", texto: "nada a ver" },
];

/**
 * Rotulagem cega do conjunto de ouro (spec golpes, fase A): compara a âncora
 * com cada candidato sem nunca mostrar a camada (`tier`) que os aproximou —
 * ela só volta no `POST`, para não viciar quem rotula.
 *
 * Ferramenta de desenvolvimento: sem entrada na `Nav`, só existe com o
 * servidor iniciado com `CHESS_TRAINER_ROTULAGEM=1`.
 */
export function RotulagemPage() {
  const { data: status } = useGolpesStatus();
  const ligado = status?.rotulagem === true;
  const { data: item, refetch } = useRotulagemProximo(ligado);
  const { data: contagem } = useRotulagemContagem(ligado);
  const rotular = useRotular();
  const [candidatos, setCandidatos] = useState<RotulagemItem["candidatos"]>([]);

  useEffect(() => {
    setCandidatos(item?.candidatos ?? []);
  }, [item]);

  if (status?.rotulagem === false) {
    return <p>Rotulagem desligada: inicie o servidor com CHESS_TRAINER_ROTULAGEM=1.</p>;
  }
  if (!ligado) return null;

  async function enviar(candidateId: string, tier: string, label: RotuloIn["label"]) {
    if (!item) return;
    await rotular.mutateAsync({
      anchor_origem: item.anchor.origem,
      anchor_id: item.anchor.id,
      candidate_id: candidateId,
      tier,
      label,
    });
    const restantes = candidatos.filter((c) => c.id !== candidateId);
    setCandidatos(restantes);
    if (restantes.length === 0) void refetch();
  }

  return (
    <>
      <h1>Rotulagem</h1>
      <p>{contagem?.total ?? 0} rótulos</p>
      {!item && <p className="muted">Nada para rotular.</p>}
      {item && (
        <div className="row" style={{ alignItems: "flex-start" }}>
          <div className="card" style={{ maxWidth: 320 }}>
            <img alt="A âncora" src={golpeImagemUrl(item.anchor.origem, item.anchor.id)} style={{ width: "100%" }} />
            <p>{item.anchor.assinatura}</p>
          </div>
          <div style={{ flex: 1 }}>
            {candidatos.map((c) => (
              <div key={c.id} className="card" style={{ maxWidth: 320, marginBottom: 12 }}>
                <img alt="O candidato" src={golpeImagemUrl("lichess", c.id)} style={{ width: "100%" }} />
                <div className="row">
                  {ROTULOS.map((r) => (
                    <button key={r.label} onClick={() => void enviar(c.id, c.tier, r.label)} disabled={rotular.isPending}>
                      {r.texto}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
