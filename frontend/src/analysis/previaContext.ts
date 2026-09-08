import { createContext } from "react";
import type { LanceDaLinha } from "./moveText";

/**
 * Quem tem um tabuleiro com prévia (o tabuleiro de análise, a tela do
 * exercício) oferece aqui a função que a abre; cartões renderizados dentro
 * dele (o "Na partida", por exemplo) tornam seus lances clicáveis sem precisar
 * saber de quem é o tabuleiro. Fora de um provedor, os lances ficam só texto.
 */
export const PreviaContext = createContext<((linha: LanceDaLinha[]) => void) | null>(null);
