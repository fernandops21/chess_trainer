import { useEffect, useState } from "react";
import { golpeImagemUrl } from "../api/client";
import { useGolpesStatus, useRotulagemContagem, useRotulagemProximo, useRotulagemResumo, useRotular } from "../api/queries";
import type { RotulagemItem, RotuloIn } from "../api/types";

/** Um botão de rótulo: o texto visível e o valor gravado (nunca a `tier` do candidato). */
const ROTULOS: { label: RotuloIn["label"]; texto: string }[] = [
  { label: "mesmo", texto: "mesmo golpe" },
  { label: "parecido", texto: "parecido" },
  { label: "nada", texto: "nada a ver" },
];

function mensagemDeErro(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/**
 * Rotulagem cega do conjunto de ouro (spec golpes, fase A): compara a âncora
 * com cada candidato sem nunca mostrar a camada (`tier`) que os aproximou —
 * ela só volta no `POST`, para não viciar quem rotula.
 *
 * Ferramenta de desenvolvimento: sem entrada na `Nav`, só existe com o
 * servidor iniciado com `CHESS_TRAINER_ROTULAGEM=1`.
 */
export function RotulagemPage() {
  const { data: status, isError: statusError, error: statusErrorObj } = useGolpesStatus();
  const ligado = status?.rotulagem === true;
  const { data: item, isLoading, isError, error, refetch } = useRotulagemProximo(ligado);
  const { data: contagem } = useRotulagemContagem(ligado);
  const { data: resumo } = useRotulagemResumo(ligado);
  const rotular = useRotular();
  const [candidatos, setCandidatos] = useState<RotulagemItem["candidatos"]>([]);
  const [erroRotular, setErroRotular] = useState<string | null>(null);

  useEffect(() => {
    setCandidatos(item?.candidatos ?? []);
  }, [item]);

  if (statusError) {
    return <p className="muted">Não consegui consultar o servidor. {mensagemDeErro(statusErrorObj)}</p>;
  }
  if (status?.rotulagem === false) {
    return <p>Rotulagem desligada: inicie o servidor com CHESS_TRAINER_ROTULAGEM=1.</p>;
  }
  if (!ligado) return null;

  async function enviar(candidato: RotulagemItem["candidatos"][number], label: RotuloIn["label"]) {
    if (!item) return;
    try {
      await rotular.mutateAsync({
        anchor_origem: item.anchor.origem,
        anchor_id: item.anchor.id,
        candidate_id: candidato.id,
        tier: candidato.tier,
        label,
        n_lances: candidato.procedencia?.n,
        posicao: candidato.procedencia?.posicao,
        nivel: candidato.procedencia?.nivel,
        espelhado: candidato.procedencia?.espelhado,
      });
      setErroRotular(null);
      const restantes = candidatos.filter((c) => c.id !== candidato.id);
      setCandidatos(restantes);
      if (restantes.length === 0) void refetch();
    } catch (e) {
      setErroRotular(`Não consegui gravar o rótulo; tente de novo. ${mensagemDeErro(e)}`);
    }
  }

  return (
    <>
      <h1>Rotulagem</h1>
      <p>{contagem?.total ?? 0} rótulos</p>
      {resumo && resumo.length > 0 && (
        <table style={{ marginBottom: 16 }}>
          <thead>
            <tr>
              <th>degrau</th><th>posição</th><th>lances</th><th>mesmo golpe</th><th>parecido</th>
              <th>nada a ver</th><th>total</th><th>% nada a ver</th>
            </tr>
          </thead>
          <tbody>
            {resumo.map((l) => (
              <tr key={`${l.tier}-${l.posicao}-${l.n_lances}`}>
                <td>{l.tier}</td><td>{l.posicao ?? "—"}</td><td>{l.n_lances ?? "—"}</td>
                <td>{l.mesmo}</td><td>{l.parecido}</td><td>{l.nada}</td><td>{l.total}</td>
                <td>{l.total > 0 ? `${Math.round((l.nada / l.total) * 100)}%` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {isLoading && <p className="muted">Carregando…</p>}
      {isError && (
        <p className="muted">
          Não consegui buscar o próximo item. {mensagemDeErro(error)}{" "}
          <button onClick={() => void refetch()}>Tentar de novo</button>
        </p>
      )}
      {!isLoading && !isError && item === null && <p className="muted">Nada para rotular.</p>}
      {item && (
        <div className="row" style={{ alignItems: "flex-start" }}>
          <div className="card" style={{ maxWidth: 320 }}>
            <img alt="A âncora" src={golpeImagemUrl(item.anchor.origem, item.anchor.id)} style={{ width: "100%" }} />
            <p>{item.anchor.assinatura}</p>
          </div>
          <div style={{ flex: 1 }}>
            {erroRotular && <p className="muted">{erroRotular}</p>}
            {candidatos.map((c) => (
              <div key={c.id} className="card" style={{ maxWidth: 320, marginBottom: 12 }}>
                <img alt="O candidato" src={golpeImagemUrl("lichess", c.id)} style={{ width: "100%" }} />
                <div className="row">
                  {ROTULOS.map((r) => (
                    <button key={r.label} onClick={() => void enviar(c, r.label)} disabled={rotular.isPending}>
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
