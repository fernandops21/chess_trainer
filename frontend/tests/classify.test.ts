import { Chess } from "chess.js";
import { expect, test } from "vitest";
import type { AnalyseLine, AnalyseOut, Color } from "../src/api/types";
import {
  classifyMove,
  materialAfterReply,
  materialOf,
  pieceValue,
} from "../src/analysis/classify";

const INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const LIMIARES = { mistake: 100, blunder: 200 };

const linha = (move: string, score: number, pv: string[] = []): AnalyseLine => ({
  move,
  san: move,
  score,
  pv: pv.length > 0 ? pv : [move],
  pv_san: [],
});

const posicao = (
  fen: string,
  turn: Color,
  lines: AnalyseLine[],
  terminal: string | null = null,
): AnalyseOut => ({ fen, turn, terminal, lines });

/** Pai genérico: o melhor lance é `e2e4` valendo `score`, o segundo vale `segundo`. */
function pai(score: number, segundo?: number): AnalyseOut {
  const lines = [linha("e2e4", score)];
  if (segundo !== undefined) lines.push(linha("d2d4", segundo));
  return posicao(INICIAL, "white", lines);
}

const APOS_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1";

/** Filho genérico: avaliação `score` no POV do adversário (preto), sem sacrifício. */
function filho(score: number, pv: string[] = ["e7e5"]): AnalyseOut {
  return posicao(APOS_E4, "black", [linha(pv[0], score, pv)]);
}

const classificar = (
  parent: AnalyseOut,
  child: AnalyseOut | null,
  uci: string,
  isBook = false,
) => classifyMove({ parent, child, uci, isBook, thresholds: LIMIARES });

test("valores das peças", () => {
  expect(pieceValue("p")).toBe(100);
  expect(pieceValue("n")).toBe(300);
  expect(pieceValue("b")).toBe(300);
  expect(pieceValue("r")).toBe(500);
  expect(pieceValue("q")).toBe(900);
  expect(pieceValue("k")).toBe(0);
  expect(pieceValue("Q")).toBe(900);
  expect(pieceValue("x")).toBe(0);
});

test("material estático de cada lado", () => {
  // 8 peões, 2 cavalos, 2 bispos, 2 torres, 1 dama = 800 + 600 + 600 + 1000 + 900
  expect(materialOf(INICIAL, "white")).toBe(3900);
  expect(materialOf(INICIAL, "black")).toBe(3900);
  expect(materialOf("6k1/8/8/8/8/8/5PPP/6K1 w - - 0 1", "white")).toBe(300);
  expect(materialOf("6k1/8/8/8/8/8/5PPP/6K1 w - - 0 1", "black")).toBe(0);
});

// Sacrifício de dama: 1. Qxh7+ Kxh7 (a dama some do tabuleiro).
const SACRIFICIO = "6k1/5p1p/6p1/8/7Q/8/5PPP/6K1 w - - 0 1";
const DEPOIS_DO_SACRIFICIO = (() => {
  const chess = new Chess(SACRIFICIO);
  chess.move({ from: "h4", to: "h7" });
  return chess.fen();
})();

test("material depois da resposta do adversário", () => {
  expect(materialOf(SACRIFICIO, "white")).toBe(1200);
  // o rei come a dama: sobram os três peões
  expect(materialAfterReply(DEPOIS_DO_SACRIFICIO, "g8h7", "white")).toBe(300);
  // o rei foge: a dama fica em pé (e o peão de h7 já foi comido)
  expect(materialAfterReply(DEPOIS_DO_SACRIFICIO, "g8f8", "white")).toBe(1200);
  // resposta ausente ou ilegal: material da própria posição
  expect(materialAfterReply(DEPOIS_DO_SACRIFICIO, undefined, "white")).toBe(1200);
  expect(materialAfterReply(DEPOIS_DO_SACRIFICIO, "a1a8", "white")).toBe(1200);
});

test("livro tem prioridade sobre tudo", () => {
  const c = classificar(pai(30), filho(400), "b1a3", true);
  expect(c).toEqual({ kind: "livro", label: "livro", symbol: "📖", loss: null });
});

test("melhor: o lance é o primeiro da engine", () => {
  const c = classificar(pai(30), filho(-30), "e2e4");
  expect(c?.kind).toBe("melhor");
  expect(c?.symbol).toBe("★");
  expect(c?.loss).toBe(0);
});

test("excelente: perde no máximo 20 cp", () => {
  const c = classificar(pai(30), filho(-15), "d2d4");
  expect(c?.kind).toBe("excelente");
  expect(c?.label).toBe("excelente");
  expect(c?.loss).toBe(15);
});

test("bom: perde no máximo 50 cp", () => {
  const c = classificar(pai(30), filho(10), "d2d4");
  expect(c?.kind).toBe("bom");
  expect(c?.loss).toBe(40);
});

test("imprecisão: perde até o limiar de imprecisão", () => {
  const c = classificar(pai(30), filho(50), "d2d4");
  expect(c?.kind).toBe("imprecisao");
  expect(c?.label).toBe("imprecisão");
  expect(c?.loss).toBe(80);
});

test("erro: perde até o limiar de blunder", () => {
  const c = classificar(pai(30), filho(120), "d2d4");
  expect(c?.kind).toBe("erro");
  expect(c?.loss).toBe(150);
});

test("blunder: perde acima do limiar de blunder", () => {
  const c = classificar(pai(30), filho(370), "d2d4");
  expect(c?.kind).toBe("blunder");
  expect(c?.symbol).toBe("??");
  expect(c?.loss).toBe(400);
});

test("os limiares vêm das configurações", () => {
  const args = { parent: pai(30), child: filho(50), uci: "d2d4", isBook: false };
  expect(classifyMove({ ...args, thresholds: { mistake: 60, blunder: 100 } })?.kind).toBe("erro");
  expect(classifyMove({ ...args, thresholds: { mistake: 200, blunder: 300 } })?.kind).toBe("imprecisao");
});

test("ótimo: única boa jogada em posição ainda não ganha", () => {
  const c = classificar(pai(200, 40), filho(-200), "e2e4");
  expect(c?.kind).toBe("otimo");
  expect(c?.symbol).toBe("!");
});

test("ótimo exige diferença de 150 cp para a segunda linha", () => {
  expect(classificar(pai(200, 60), filho(-200), "e2e4")?.kind).toBe("melhor");
  expect(classificar(pai(200, 50), filho(-200), "e2e4")?.kind).toBe("otimo");
});

test("ótimo não vale em posição já ganha nem sem segunda linha", () => {
  expect(classificar(pai(600, 100), filho(-600), "e2e4")?.kind).toBe("melhor");
  expect(classificar(pai(200), filho(-200), "e2e4")?.kind).toBe("melhor");
});

test("brilhante: melhor lance que sacrifica material e continua bem", () => {
  const parent = posicao(SACRIFICIO, "white", [linha("h4h7", 99997)]);
  const child = posicao(DEPOIS_DO_SACRIFICIO, "black", [linha("g8h7", -99996, ["g8h7", "g1g2"])]);
  const c = classificar(parent, child, "h4h7");
  expect(c?.kind).toBe("brilhante");
  expect(c?.symbol).toBe("!!");
  // mates viram ±3000 cp na conta da perda
  expect(c?.loss).toBe(0);
});

test("não é brilhante quando o adversário não come nada", () => {
  const parent = posicao(SACRIFICIO, "white", [linha("h4h7", 300)]);
  const child = posicao(DEPOIS_DO_SACRIFICIO, "black", [linha("g8f8", -300, ["g8f8", "h7h8"])]);
  expect(classificar(parent, child, "h4h7")?.kind).toBe("melhor");
});

test("não é brilhante quando a posição fica perdida depois do lance", () => {
  const parent = posicao(SACRIFICIO, "white", [linha("h4h7", -400)]);
  const child = posicao(DEPOIS_DO_SACRIFICIO, "black", [linha("g8h7", 400, ["g8h7", "g1g2"])]);
  expect(classificar(parent, child, "h4h7")?.kind).toBe("melhor");
});

test("mate de quem joga limita a perda a 3000 cp", () => {
  // o melhor lance dava mate e o lance jogado deixa a posição igual
  const c = classificar(pai(99995), filho(0), "d2d4");
  expect(c?.kind).toBe("blunder");
  expect(c?.loss).toBe(3000);
});

test("levar mate depois do lance também limita a perda", () => {
  const c = classificar(pai(30), filho(99991), "d2d4");
  expect(c?.loss).toBe(3030);
  expect(c?.kind).toBe("blunder");
});

test("perda nunca fica negativa", () => {
  const c = classificar(pai(30), filho(-90), "d2d4");
  expect(c?.loss).toBe(0);
  expect(c?.kind).toBe("excelente");
});

test("sem as linhas do pai não há classificação", () => {
  expect(classificar(posicao(INICIAL, "white", []), filho(0), "e2e4")).toBeNull();
});

test("sem a posição filha só o melhor lance é classificado", () => {
  const c = classificar(pai(200, 40), null, "e2e4");
  expect(c?.kind).toBe("melhor");
  expect(c?.loss).toBeNull();
  expect(classificar(pai(30), null, "d2d4")).toBeNull();
  // filha sem linhas e sem final de partida é o mesmo caso
  const semLinhas = posicao(APOS_E4, "black", []);
  expect(classificar(pai(30), semLinhas, "e2e4")?.kind).toBe("melhor");
  expect(classificar(pai(30), semLinhas, "d2d4")).toBeNull();
});

// Mate sufocado: as brancas entregaram a dama antes e dão mate com o cavalo.
// A posição do mate é o fim da linha — não há resposta do adversário a contar.
const MATE_SUFOCADO = "6rk/6pp/8/6N1/8/8/1q6/6K1 w - - 0 1";
const DEPOIS_DO_MATE = "6rk/5Npp/8/8/8/8/1q6/6K1 b - - 1 1";

test("brilhante: mate dado com menos material do que o adversário", () => {
  const parent = posicao(MATE_SUFOCADO, "white", [linha("g5f7", 99999)]);
  const mate = posicao(DEPOIS_DO_MATE, "black", [], "checkmate");
  const c = classificar(parent, mate, "g5f7");
  expect(c?.kind).toBe("brilhante");
  expect(c?.symbol).toBe("!!");
  expect(c?.loss).toBe(0);
});

// Mate na última fileira com as brancas por cima no material.
const MATE_TRANQUILO = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1";
const DEPOIS_DO_MATE_TRANQUILO = "R5k1/5ppp/8/8/8/8/5PPP/6K1 b - - 1 1";

test("mate sem material entregue é só o melhor lance", () => {
  const parent = posicao(MATE_TRANQUILO, "white", [linha("a1a8", 99999)]);
  const mate = posicao(DEPOIS_DO_MATE_TRANQUILO, "black", [], "checkmate");
  expect(classificar(parent, mate, "a1a8")?.kind).toBe("melhor");
});

test("lance que dá mate conta como o melhor", () => {
  const mate = posicao(APOS_E4, "black", [], "checkmate");
  const c = classificar(pai(30), mate, "d1h5");
  expect(c?.kind).toBe("melhor");
  expect(c?.loss).toBe(0);
});

test("lance que afoga o adversário vale como empate", () => {
  const afogamento = posicao(APOS_E4, "black", [], "stalemate");
  const c = classificar(pai(400), afogamento, "d1h5");
  expect(c?.kind).toBe("blunder");
  expect(c?.loss).toBe(400);
});

// Troca de damas: 1. Qxd8+ Kxd8. Cada lado perde uma dama, a diferença de
// material não muda — não é sacrifício.
const TROCA_DE_DAMAS = "3qk3/8/8/8/8/8/8/3QK3 w - - 0 1";
const DEPOIS_DA_TROCA = (() => {
  const chess = new Chess(TROCA_DE_DAMAS);
  chess.move({ from: "d1", to: "d8" });
  return chess.fen();
})();

test("troca simples não é sacrifício, mesmo sendo o melhor lance", () => {
  const parent = posicao(TROCA_DE_DAMAS, "white", [linha("d1d8", 50)]);
  const child = posicao(DEPOIS_DA_TROCA, "black", [linha("e8d8", -50, ["e8d8"])]);
  expect(classificar(parent, child, "d1d8")?.kind).toBe("melhor");
});

test("ótimo usa os scores com mates presos: posição perdida por força", () => {
  // −99000 e −99500 são dois mates: a diferença real entre as linhas é zero
  const c = classificar(pai(-99000, -99500), filho(99000), "e2e4");
  expect(c?.kind).toBe("melhor");
});
