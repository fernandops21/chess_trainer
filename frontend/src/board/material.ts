import { novoChess } from "../lib/chess";

/** Quantas peças de cada tipo (sem o rei, que não é capturável). */
export interface Pecas { p: number; n: number; b: number; r: number; q: number }

export interface Material {
  /** O que cada lado capturou: as peças do adversário que faltam no tabuleiro. */
  capturadasPor: { white: Pecas; black: Pecas };
  /** Material das brancas menos o das pretas; positivo é vantagem branca. */
  saldo: number;
}

/** Tipos em ordem de valor, que é a ordem em que a barra os mostra. */
export const TIPOS = ["p", "n", "b", "r", "q"] as const;
export type Tipo = (typeof TIPOS)[number];

/** Quantas peças de cada tipo cada lado começa com. */
const INICIAL: Pecas = { p: 8, n: 2, b: 2, r: 2, q: 1 };
const VALOR: Pecas = { p: 1, n: 3, b: 3, r: 5, q: 9 };

const zeros = (): Pecas => ({ p: 0, n: 0, b: 0, r: 0, q: 0 });

const ehTipo = (c: string): c is Tipo => (TIPOS as readonly string[]).includes(c);

/** O que falta do lado, sem nunca ficar negativo: promoção dá peça a mais. */
const faltando = (noTabuleiro: Pecas): Pecas => {
  const faltam = zeros();
  for (const t of TIPOS) faltam[t] = Math.max(0, INICIAL[t] - noTabuleiro[t]);
  return faltam;
};

const valor = (pecas: Pecas): number => TIPOS.reduce((soma, t) => soma + pecas[t] * VALOR[t], 0);

/**
 * Material capturado e saldo da posição, como no indicador ao lado do
 * tabuleiro.
 *
 * A conta é por falta: cada peça que não está no tabuleiro conta como
 * capturada pelo outro lado. Não é a história da partida — uma peça promovida
 * "esconde" o peão que virou dama —, mas é o que o jogador vê na tela e o que
 * os sites de xadrez mostram. A FEN vem pelo `novoChess`, que aceita os
 * diagramas de estudo sem rei; FEN inválida devolve tudo zerado, porque a barra
 * não é lugar de derrubar a tela.
 */
export function materialCapturado(fen: string): Material {
  let tabuleiro = "";
  try {
    tabuleiro = novoChess(fen).fen().split(" ")[0] ?? "";
  } catch {
    return { capturadasPor: { white: zeros(), black: zeros() }, saldo: 0 };
  }
  const noTabuleiro = { white: zeros(), black: zeros() };
  for (const c of tabuleiro) {
    const t = c.toLowerCase();
    if (ehTipo(t)) noTabuleiro[c === t ? "black" : "white"][t] += 1;
  }
  return {
    capturadasPor: { white: faltando(noTabuleiro.black), black: faltando(noTabuleiro.white) },
    saldo: valor(noTabuleiro.white) - valor(noTabuleiro.black),
  };
}
