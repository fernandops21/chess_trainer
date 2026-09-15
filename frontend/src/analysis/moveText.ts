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

/**
 * Uma linha que a explicação declarou: os SAN, na ordem, a partir de `fen`.
 *
 * É o que o segmentador usa para achar a posição de um lance numerado que a
 * prosa cita pulando lances ("18.Rac1? 19.Qc5" omite o 18...Ne7): a linha traz
 * a sequência inteira, a prosa só os lances que importam.
 */
export interface LinhaConhecida {
  fen: string;
  lances: string[];
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
 * 1. número do lance, opcional: `12.`, `12...`, `12. `, e também o jeito dos
 *    livros antigos, `12 Nf3` (número, espaço) e `12 ... Nf6` / `12....Nf6`;
 * 2. o SAN em si (roque, peça ou peão, com desambiguação e promoção);
 * 3. xeque/mate (`+`, `#`) e apreciação (`!`, `?`, `!!`, `?!`…).
 *
 * Os sufixos e o número ficam no texto do segmento, mas saem antes de o
 * chess.js julgar a legalidade. O número (grupo 2) e as reticências (grupo 3)
 * dizem em que lance da linha o autor está: com eles a sequência volta para
 * essa posição em vez de encadear às cegas.
 */
const CANDIDATO =
  /((?:(\d{1,3})[ \t]*(\.{1,4})?[ \t]*)?)(O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x?[a-h]?[1-8](?:=[QRBN])?)([+#]?)([!?]{0,2})/g;

/** Número do lance e lado a jogar de uma FEN. */
function ondeEsta(fen: string): { numero: number; pretas: boolean } {
  const campos = fen.split(" ");
  return { numero: Number(campos[5]) || 1, pretas: campos[1] === "b" };
}

/**
 * Um lance só pode nascer entre limites de palavra: nada de pescar dentro de
 * "Nc3x". O hífen conta como vizinho para a notação longa ("Qd1-h5") não virar
 * dois links encadeados; o roque não sofre porque `O-O-O` e `O-O` casam
 * inteiros na alternância do candidato.
 */
const VIZINHO = /[A-Za-z0-9-]/;

/** `Qxf7#!` -> `Qxf7`: sem xeque/mate nem apreciação, para comparar dois SAN. */
function limparSan(san: string): string {
  return san.replace(/[!?]/g, "").replace(/[+#]+$/, "");
}

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
 * Procura nas linhas declaradas a posição com esse número e lado, e devolve a
 * sequência que chega até o lance do texto: o prefixo da linha até ali mais o
 * lance. É assim que "19.Qc5", citado depois de "18.Rac1?", reencontra o
 * 18...Ne7 que a prosa pulou, em vez de jogar Qc5 a partir da âncora.
 *
 * Quando o SAN do texto é o próprio lance seguinte da linha, a resposta é
 * imediata; quando difere mas é legal ali, a prosa está ramificando da linha e
 * a sequência vale do mesmo jeito — só que uma linha que case exato vem antes.
 */
function pelasLinhas(
  linhas: LinhaConhecida[],
  numero: number,
  pretas: boolean,
  san: string,
): LanceDaLinha[] | null {
  let ramo: LanceDaLinha[] | null = null;
  for (const declarada of linhas) {
    try {
      novoChess(declarada.fen);
    } catch {
      continue;
    }
    const prefixo: LanceDaLinha[] = [];
    let fen = declarada.fen;
    // uma volta a mais que os lances: a posição do fim da linha também conta
    for (let i = 0; i <= declarada.lances.length; i++) {
      const onde = ondeEsta(fen);
      if (onde.numero === numero && onde.pretas === pretas) {
        // a linha passa por esta altura uma vez só: achou ou não achou
        const lance = tentar(fen, san);
        if (lance) {
          const proximo = declarada.lances[i];
          if (proximo !== undefined && limparSan(proximo) === limparSan(lance.san)) return [...prefixo, lance];
          ramo = ramo ?? [...prefixo, lance];
        }
        break;
      }
      const proximo = declarada.lances[i];
      if (proximo === undefined) break;
      const jogado = tentar(fen, limparSan(proximo));
      if (!jogado) break;
      prefixo.push(jogado);
      fen = jogado.fen;
    }
  }
  return ramo;
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
 * `linhas` são as sequências que o autor do texto declarou (as `linhas` da
 * explicação do treinador, cada uma com a FEN de onde parte). Um lance numerado
 * que a cadeia corrente não alcança é procurado nelas: a prosa pula lances, a
 * linha declarada não.
 *
 * FEN inválida devolve o texto inteiro como um segmento só.
 */
export function segmentar(texto: string, fenAncora: string, linhas: LinhaConhecida[] = []): Segmento[] {
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

    const san = m[4];
    let lance: LanceDaLinha | null = null;
    let nova: LanceDaLinha[] = [];

    // Com número, o autor diz onde está: "8 a5" é o 8º lance das brancas,
    // "8...Bxa5" o das pretas. A linha volta até a posição com esse número
    // (a âncora conta), e o lance parte dali — é assim que "after 7...Nf6
    // 8 a5, play 8...Nxa5" recomeça no 8º em vez de emendar no 10º.
    const numero = m[2] ? Number(m[2]) : null;
    if (numero !== null) {
      const pretas = (m[3] ?? "").length >= 2;
      const posicoes = [fenAncora, ...linha.map((l) => l.fen)];
      for (let i = posicoes.length - 1; i >= 0; i--) {
        const onde = ondeEsta(posicoes[i]);
        if (onde.numero === numero && onde.pretas === pretas) {
          lance = tentar(posicoes[i], san);
          if (lance) nova = [...linha.slice(0, i), lance];
          break;
        }
      }
      // A cadeia lida do texto não chega a esse número — a prosa pulou lances.
      // As linhas declaradas chegam: a sequência passa a ser a delas até ali.
      if (!lance && linhas.length > 0) {
        const daLinha = pelasLinhas(linhas, numero, pretas, san);
        if (daLinha) {
          lance = daLinha[daLinha.length - 1];
          nova = daLinha;
        }
      }
    }
    if (!lance) {
      lance = tentar(fenAtual, san);
      if (lance) {
        nova = [...linha, lance];
      } else {
        // recomeço de sequência: o lance pode ser resposta a outro lance do texto
        lance = fenAtual === fenAncora ? null : tentar(fenAncora, san);
        if (!lance) continue;
        nova = [lance];
      }
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
