import { golpeImagemUrl } from "../api/client";
import { useIrmaos } from "../api/queries";
import { useBloco } from "./BlocoContext";

/** Cartão "Repetir o golpe": o golpe desenhado e o botão do bloco de irmãos (spec golpes §6). O
 *  botão aparece assim que o resultado está registrado, no erro (destacado) e no acerto: repetir
 *  é oferta, não castigo — e os votos do bloco não podem vir só dos golpes que o usuário erra. */
export function GolpeCard({ origem, id, resultado }: { origem: "own" | "lichess"; id: string; resultado: "acerto" | "erro" | null }) {
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
      {data.padrao && <p className="muted">Padrão: {data.padrao}</p>}
      {resultado !== null && (
        <button className={resultado === "erro" ? "primary" : undefined}
          onClick={() => iniciar({ anchorId: id, anchorOrigem: origem, itens, tiers, procedencias })}>Treinar {itens.length} parecidos</button>
      )}
    </div>
  );
}
