import { Chess } from "chess.js";

/**
 * Criação de posições do chess.js num ponto só.
 *
 * Aulas e estudos usam diagramas sem os dois reis ("as brancas dão mate em
 * dois com estas peças"), que o Lichess mostra sem reclamar. O chess.js 1.4.0
 * recusa essas FENs com exceção, e uma exceção no meio de um render derruba a
 * tela inteira — era o que acontecia ao abrir um capítulo assim.
 */

const SEM_REI = /missing (white|black) king/;

/**
 * `new Chess(fen)` que aceita diagramas sem os reis.
 *
 * Só a falta de rei passa pela validação desligada: aí o chess.js gera lances
 * pseudo-legais (ele já se protege quando o rei do lado a jogar não existe),
 * o que é exatamente o que se quer num diagrama. Qualquer outro erro de FEN é
 * relançado, para quem chama continuar tratando FEN inválida como inválida.
 */
export function novoChess(fen?: string): Chess {
  try {
    return new Chess(fen);
  } catch (erro) {
    if (fen !== undefined && erro instanceof Error && SEM_REI.test(erro.message)) {
      return new Chess(fen, { skipValidation: true });
    }
    throw erro;
  }
}

/** A FEN tem os dois reis? Só o campo das peças conta. */
export function temOsDoisReis(fen: string): boolean {
  const pecas = fen.trim().split(" ")[0];
  return pecas.includes("K") && pecas.includes("k");
}
