import { novoChess } from "../lib/chess";
import type { Key } from "chessground/types";

/** Um lance de uma sequência lida do texto, com a posição a que ele leva. */
export interface LanceDaLinha {
  san: string;
  uci: string;
  /** Posição depois do lance. */
  fen: string;
  lastMove: [Key, Key];
}

/** Pedaço do texto: prosa comum ou um lance clicável. */
export type Segmento =
  | { kind: "texto"; text: string }
  | ({
      kind: "lance";
      /** O texto como o autor escreveu (com número de lance e sufixos). */
      text: string;
      /** A sequência da âncora até este lance, inclusive. */
      linha: LanceDaLinha[];
    } & LanceDaLinha);

/**
 * Candidato a lance no texto.
 *
 * 1. número do lance, opcional e colado (`12.`, `12...`, `12. `);
 * 2. o SAN em si (roque, peça ou peão, com desambiguação e promoção);
 * 3. xeque/mate (`+`, `#`) e apreciação (`!`, `?`, `!!`, `?!`…).
 *
 * Os sufixos e o número ficam no texto do segmento, mas saem antes de o
 * chess.js julgar a legalidade.
 */
const CANDIDATO =
  /((?:\d{1,3}\.(?:\.\.)?[ \t]*)?)(O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x?[a-h]?[1-8](?:=[QRBN])?)([+#]?)([!?]{0,2})/g;

/**
 * Um lance só pode nascer entre limites de palavra: nada de pescar dentro de
 * "Nc3x". O hífen conta como vizinho para a notação longa ("Qd1-h5") não virar
 * dois links encadeados; o roque não sofre porque `O-O-O` e `O-O` casam
 * inteiros na alternância do candidato.
 */
const VIZINHO = /[A-Za-z0-9-]/;

/** Tenta o SAN na posição; devolve o lance com a posição nova, ou `null` se for ilegal. */
function tentar(fen: string, san: string): LanceDaLinha | null {
  try {
    const chess = novoChess(fen);
    const mv = chess.move(san);
    if (!mv) return null;
    return {
      san: mv.san,
      uci: `${mv.from}${mv.to}${mv.promotion ?? ""}`,
      fen: chess.fen(),
      lastMove: [mv.from as Key, mv.to as Key],
    };
  } catch {
    return null;
  }
}

/**
 * Quebra o texto do autor em prosa e lances jogáveis a partir de `fenAncora`.
 *
 * Os lances encadeiam: cada um parte da posição do anterior, de modo que
 * "Nc3 Qb6" descreve uma linha de dois lances. Um candidato ilegal na posição
 * corrente recomeça a sequência a partir da âncora (é o caso de "d5? Nb4 …
 * segue Nc3 Qb6", em que "Nc3" é resposta a "d5" e não continuação de "Nb4");
 * ilegal também ali, ele volta a ser texto comum e não mexe na sequência.
 *
 * FEN inválida devolve o texto inteiro como um segmento só.
 */
export function segmentar(texto: string, fenAncora: string): Segmento[] {
  if (texto === "") return [];
  try {
    novoChess(fenAncora);
  } catch {
    return [{ kind: "texto", text: texto }];
  }

  const segs: Segmento[] = [];
  let pos = 0;
  let fenAtual = fenAncora;
  let linha: LanceDaLinha[] = [];

  CANDIDATO.lastIndex = 0;
  for (let m = CANDIDATO.exec(texto); m; m = CANDIDATO.exec(texto)) {
    const fim = m.index + m[0].length;
    const antes = texto[m.index - 1];
    const depois = texto[fim];
    if ((antes && VIZINHO.test(antes)) || (depois && VIZINHO.test(depois))) {
      // Recomeça um caractere adiante, e não depois do match inteiro: um lance
      // legítimo pode estar dentro dele ("no12. e4" perderia o "e4").
      CANDIDATO.lastIndex = m.index + 1;
      continue;
    }

    const san = m[2];
    let lance = tentar(fenAtual, san);
    let nova: LanceDaLinha[];
    if (lance) {
      nova = [...linha, lance];
    } else {
      // recomeço de sequência: o lance pode ser resposta a outro lance do texto
      lance = fenAtual === fenAncora ? null : tentar(fenAncora, san);
      if (!lance) continue;
      nova = [lance];
    }

    if (m.index > pos) segs.push({ kind: "texto", text: texto.slice(pos, m.index) });
    segs.push({ kind: "lance", text: m[0], ...lance, linha: nova });
    pos = fim;
    linha = nova;
    fenAtual = lance.fen;
  }

  if (pos < texto.length) segs.push({ kind: "texto", text: texto.slice(pos) });
  return segs;
}
