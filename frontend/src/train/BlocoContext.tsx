import { createContext, useContext, type ReactNode } from "react";
import type { TacticOut } from "../api/types";

/** Bloco de repetição do golpe: a âncora (o golpe que o usuário errou) e os irmãos a treinar. */
export type Bloco = { anchorId: string; anchorOrigem: "own" | "lichess"; itens: TacticOut[] };
type Ctx = { iniciar: (bloco: Bloco) => void };

// padrão sem efeito: páginas fora do treino (e os testes que não passam `value`) ignoram o clique
const BlocoCtx = createContext<Ctx>({ iniciar: () => {} });

export const useBloco = () => useContext(BlocoCtx);

export function BlocoProvider({ value, children }: { value: Ctx; children: ReactNode }) {
  return <BlocoCtx.Provider value={value}>{children}</BlocoCtx.Provider>;
}
