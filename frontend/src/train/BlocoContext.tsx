import { createContext, useContext, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
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

// padrão sem efeito só para componente testado sem provedor nenhum. No app todo botão do cartão
// tem um provedor: o `BlocoGlobal` do App (qualquer tela) ou o da tela Treinar (troca no lugar).
const BlocoCtx = createContext<Ctx>({ iniciar: () => {} });

/** O que viaja no estado da navegação quando o bloco abre a partir de outra tela. */
export type ChegadaDoBloco = { bloco: Bloco; voltarPara: string };

export const useBloco = () => useContext(BlocoCtx);

export function BlocoProvider({ value, children }: { value: Ctx; children: ReactNode }) {
  return <BlocoCtx.Provider value={value}>{children}</BlocoCtx.Provider>;
}

/** Provedor do App inteiro: fora da tela Treinar (Revisar, exercício avulso, o que vier), o botão
 *  "Treinar N parecidos" leva para /treinar com o bloco e o caminho de volta no estado da
 *  navegação. Sem isto o clique caía no padrão vazio e não acontecia nada, em silêncio. */
export function BlocoGlobal({ children }: { children: ReactNode }) {
  const navegar = useNavigate();
  const onde = useLocation();
  const iniciar = (bloco: Bloco) => {
    const estado: ChegadaDoBloco = { bloco, voltarPara: onde.pathname + onde.search };
    navegar("/treinar", { state: estado });
  };
  return <BlocoCtx.Provider value={{ iniciar }}>{children}</BlocoCtx.Provider>;
}
