import { golpeImagemUrl } from "../api/client";
import { useIrmaos } from "../api/queries";
import { useBloco } from "./BlocoContext";

/** Cartão "Repetir o golpe": o golpe desenhado e, no erro, o bloco de irmãos (spec golpes §6). */
export function GolpeCard({ origem, id, errou }: { origem: "own" | "lichess"; id: string; errou: boolean }) {
  const { data } = useIrmaos(origem, id);
  const { iniciar } = useBloco();
  // sem irmãos o cartão não existe (spec §6): nada para repetir, nada para mostrar
  if (!data || data.itens.length === 0) return null;
  const itens = data.itens.map((i) => i.tactic);
  const tiers = Object.fromEntries(data.itens.map((i) => [i.tactic.id, i.tier]));
  // só entram os itens com procedência (todo item da cascata tem, mas o campo é opcional no
  // tipo): o voto no resultado (`VotoDoGolpe`) usa para mandar a procedência junto do rótulo
  const procedencias = Object.fromEntries(
    data.itens.filter((i) => i.procedencia).map((i) => [i.tactic.id, i.procedencia!]),
  );
  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>Repetir o golpe</h3>
      <img alt="O golpe desenhado" src={golpeImagemUrl(origem, id)} style={{ width: "100%", maxWidth: 320 }} />
      {errou && itens.length > 0 && (
        <button onClick={() => iniciar({ anchorId: id, anchorOrigem: origem, itens, tiers, procedencias })}>Treinar {itens.length} parecidos</button>
      )}
    </div>
  );
}
