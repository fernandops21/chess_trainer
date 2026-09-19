import { createContext, useContext, type ReactNode } from "react";
import type { Procedencia, TacticOut } from "../api/types";

/** Bloco de repetição do golpe: a âncora (o golpe que o usuário errou) e os irmãos a treinar.
 *  `tiers` guarda o degrau da cascata de cada item (id da tática -> degrau), para o
 *  salvamento levar `sibling_tier` junto de `sibling_of` (spec golpes trechos §6).
 *  `procedencias` guarda a procedência completa de cada item (id da tática -> procedência),
 *  para o voto no resultado (`VotoDoGolpe`) mandar `n_lances`/`posicao`/`nivel`/`espelhado`
 *  junto do rótulo — o voto mora no bloco, não numa tela de rotulagem à parte. */
export type Bloco = {
  anchorId: string;
  anchorOrigem: "own" | "lichess";
  itens: TacticOut[];
  tiers: Record<string, string>;
  procedencias: Record<string, Procedencia>;
};
type Ctx = { iniciar: (bloco: Bloco) => void };

// padrão sem efeito: páginas fora do treino (e os testes que não passam `value`) ignoram o clique
const BlocoCtx = createContext<Ctx>({ iniciar: () => {} });

export const useBloco = () => useContext(BlocoCtx);

export function BlocoProvider({ value, children }: { value: Ctx; children: ReactNode }) {
  return <BlocoCtx.Provider value={value}>{children}</BlocoCtx.Provider>;
}
