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

/** Campo das peças da FEN (o primeiro). */
const pecasDe = (fen: string) => fen.trim().split(/\s+/)[0] ?? "";

const quantos = (pecas: string, letra: string) => [...pecas].filter((c) => c === letra).length;

/**
 * Dá para montar este diagrama sem rei com `skipValidation`?
 *
 * `skipValidation` desliga TODAS as conferências do chess.js, e ele olha os
 * reis antes das duas últimas — então o que vem depois da falta de rei fica
 * por nossa conta:
 *
 * - peão na primeira ou na última fila: `moves()`/`move()` estouram com
 *   `Cannot mix BigInt and other types` (e dentro de um render isso é tela
 *   branca, justamente o que este módulo existe para evitar);
 * - rei repetido: o chess.js guarda uma casa por cor e apaga o primeiro rei
 *   em silêncio, mostrando um diagrama que não é o do arquivo.
 *
 * Nesses dois casos a FEN volta a ser inválida, como era antes.
 */
function diagramaMontavel(pecas: string): boolean {
  const filas = pecas.split("/");
  if (/[pP]/.test((filas[0] ?? "") + (filas[7] ?? ""))) return false;
  return quantos(pecas, "K") <= 1 && quantos(pecas, "k") <= 1;
}

/**
 * A mesma FEN sem as flags de roque da cor que não tem rei no tabuleiro.
 *
 * Sem rei, `_moves()` monta o roque a partir da casa -1 e `moves()` quebra ao
 * ler a casa de origem. Campo que fica vazio vira `-`.
 */
function semRoqueDaCorSemRei(fen: string): string {
  const campos = fen.trim().split(/\s+/);
  const pecas = campos[0] ?? "";
  const roque = [...(campos[2] ?? "")]
    .filter((c) => "KQkq".includes(c))
    .filter((c) => (c === c.toUpperCase() ? pecas.includes("K") : pecas.includes("k")))
    .join("");
  campos[2] = roque === "" ? "-" : roque;
  return campos.join(" ");
}

/**
 * `new Chess(fen)` que aceita diagramas sem os reis.
 *
 * Quem decide o retry é a FEN — o campo das peças sem os dois reis e sem os
 * defeitos que `diagramaMontavel` lista —, e a mensagem do chess.js entra só
 * como confirmação de que foi por isso que ele recusou. Aí o chess.js gera
 * lances pseudo-legais (ele já se protege quando o rei do lado a jogar não
 * existe), que é o que se quer num diagrama. Qualquer outro erro de FEN é
 * relançado, para quem chama continuar tratando FEN inválida como inválida.
 */
export function novoChess(fen?: string): Chess {
  try {
    return new Chess(fen);
  } catch (erro) {
    if (
      fen !== undefined &&
      !temOsDoisReis(fen) &&
      diagramaMontavel(pecasDe(fen)) &&
      erro instanceof Error &&
      SEM_REI.test(erro.message)
    ) {
      return new Chess(semRoqueDaCorSemRei(fen), { skipValidation: true });
    }
    throw erro;
  }
}

/** A FEN tem os dois reis? Só o campo das peças conta. */
export function temOsDoisReis(fen: string): boolean {
  const pecas = pecasDe(fen);
  return pecas.includes("K") && pecas.includes("k");
}
