import { Chess } from "chess.js";
import type { AnalyseOut, Color } from "../api/types";
import { uciToMove } from "../board/line";

/**
 * Classificação de um lance no estilo chess.com, a partir da análise da
 * posição de onde ele parte (o pai) e da posição a que ele leva (o filho).
 *
 * Tudo aqui é puro: quem chama já tem as duas análises em mãos
 * (`useMoveClassification` cuida das consultas).
 */
export type ClassKind =
  | "livro"
  | "brilhante"
  | "otimo"
  | "melhor"
  | "excelente"
  | "bom"
  | "imprecisao"
  | "erro"
  | "blunder";

export interface Classification {
  kind: ClassKind;
  /** Nome em português, para o `title` do selo. */
  label: string;
  /** Símbolo curto do selo. */
  symbol: string;
  /** Perda em centipeões; `null` quando não dá para medir (livro, filho ausente). */
  loss: number | null;
}

const ROTULOS: Record<ClassKind, { label: string; symbol: string }> = {
  livro: { label: "livro", symbol: "📖" },
  brilhante: { label: "brilhante", symbol: "!!" },
  otimo: { label: "ótimo", symbol: "!" },
  melhor: { label: "melhor", symbol: "★" },
  excelente: { label: "excelente", symbol: "✓" },
  bom: { label: "bom", symbol: "·" },
  imprecisao: { label: "imprecisão", symbol: "?!" },
  erro: { label: "erro", symbol: "?" },
  blunder: { label: "blunder", symbol: "??" },
};

/** Acima disso o score é mate (±(100000 − n)) e vira ±`MATE_CP` na conta da perda. */
const MATE_MIN = 90000;
const MATE_CP = 3000;
/** Queda de material que caracteriza um sacrifício. */
const SACRIFICIO_CP = 200;
/** Até onde a posição depois do lance ainda não é "perdida" (POV de quem jogou). */
const NAO_PERDIDO_CP = -50;
/** Vantagem da primeira linha sobre a segunda que faz do lance a única boa jogada. */
const GAP_OTIMO_CP = 150;
/** Acima disso a posição já está ganha e "ótimo" não se aplica. */
const TETO_OTIMO_CP = 500;
const EXCELENTE_CP = 20;
const BOM_CP = 50;

const VALORES: Record<string, number> = { p: 100, n: 300, b: 300, r: 500, q: 900, k: 0 };

/** Valor estático da peça (`p`, `n`, `b`, `r`, `q`, `k`), em centipeões. */
export function pieceValue(role: string): number {
  return VALORES[role.toLowerCase()] ?? 0;
}

/** Soma do material de um lado, lida direto da parte de peças do FEN. */
export function materialOf(fen: string, color: Color): number {
  const pecas = fen.split(" ")[0] ?? "";
  const branco = color === "white";
  let total = 0;
  for (const ch of pecas) {
    if (!/[a-z]/i.test(ch)) continue;
    if ((ch === ch.toUpperCase()) !== branco) continue;
    total += pieceValue(ch);
  }
  return total;
}

/**
 * Material de `color` depois de o adversário responder com `replyUci` na
 * posição `fenChild`. Sem resposta (ou com uma resposta que não é legal ali)
 * fica o material da própria posição — é o que sobra de mais razoável.
 */
export function materialAfterReply(
  fenChild: string,
  replyUci: string | undefined,
  color: Color,
): number {
  if (!replyUci) return materialOf(fenChild, color);
  try {
    const chess = new Chess(fenChild);
    chess.move(uciToMove(replyUci));
    return materialOf(chess.fen(), color);
  } catch {
    return materialOf(fenChild, color);
  }
}

/** Score da engine em centipeões, com os mates presos em ±`MATE_CP`. */
function emCp(score: number): number {
  if (score >= MATE_MIN) return MATE_CP;
  if (score <= -MATE_MIN) return -MATE_CP;
  return score;
}

export interface ClassifyInput {
  /** Análise da posição de onde o lance parte. */
  parent: AnalyseOut;
  /** Análise da posição depois do lance; `null` enquanto ela não chegou. */
  child: AnalyseOut | null;
  uci: string;
  /** O lance está no livro de mestres (`useBookMoves`). */
  isBook: boolean;
  thresholds: { mistake: number; blunder: number };
}

/**
 * Classifica um lance. As categorias são testadas na ordem do plano e a
 * primeira que casa vence. Devolve `null` quando não há como classificar
 * (engine indisponível, ou lance que não é o melhor e ainda sem o filho).
 */
export function classifyMove({
  parent,
  child,
  uci,
  isBook,
  thresholds,
}: ClassifyInput): Classification | null {
  if (isBook) return classe("livro", null);

  const melhorLinha = parent.lines[0];
  if (!melhorLinha) return null;

  const eOMelhor = uci === melhorLinha.move;
  const sBest = emCp(melhorLinha.score);
  const linhaFilho = child?.lines[0] ?? null;

  // Avaliação depois do lance, sempre no POV de quem jogou: o score do filho
  // é do POV do adversário, por isso o sinal troca.
  let depois: number | null = null;
  if (linhaFilho) depois = -emCp(linhaFilho.score);
  else if (child?.terminal === "checkmate") depois = MATE_CP;
  else if (child?.terminal) depois = 0; // afogamento ou empate

  // O lance que dá mate é, por definição, o melhor da posição.
  const deuMate = child?.terminal === "checkmate";
  const loss = depois === null ? null : Math.max(0, sBest - depois);

  if (
    (eOMelhor || deuMate) &&
    child !== null &&
    linhaFilho !== null &&
    depois !== null &&
    depois >= NAO_PERDIDO_CP &&
    materialOf(parent.fen, parent.turn) -
      materialAfterReply(child.fen, linhaFilho.pv[0], parent.turn) >=
      SACRIFICIO_CP
  ) {
    return classe("brilhante", loss);
  }

  // "ótimo" só sai com o filho em mãos: enquanto ele não chega o lance fica
  // em "melhor", que é a única categoria que não pode mudar depois.
  if (
    eOMelhor &&
    depois !== null &&
    parent.lines.length > 1 &&
    melhorLinha.score - parent.lines[1].score >= GAP_OTIMO_CP &&
    melhorLinha.score <= TETO_OTIMO_CP
  ) {
    return classe("otimo", loss);
  }

  if (eOMelhor || deuMate) return classe("melhor", loss);
  if (loss === null) return null;

  if (loss <= EXCELENTE_CP) return classe("excelente", loss);
  if (loss <= BOM_CP) return classe("bom", loss);
  if (loss <= thresholds.mistake) return classe("imprecisao", loss);
  if (loss <= thresholds.blunder) return classe("erro", loss);
  return classe("blunder", loss);
}

function classe(kind: ClassKind, loss: number | null): Classification {
  return { kind, ...ROTULOS[kind], loss };
}
