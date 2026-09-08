import { expect, test } from "vitest";
import { segmentar } from "../src/analysis/moveText";
import type { Segmento } from "../src/analysis/moveText";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
/** Brancas a jogar, com peão em d4 e cavalos em b1 e f4: "d5", "Nb4", "Nd5" e "Qb6" cabem
 *  no texto, mas "Nd5" só é legal enquanto d5 estiver vazia. */
const MEIO = "3qk3/pp3ppp/2n5/8/3PPN2/8/PP3PPP/1N2K3 w - - 0 1";

/** Só os textos dos segmentos de lance, na ordem. */
const lances = (segs: Segmento[]) => segs.filter((s) => s.kind === "lance").map((s) => s.text);
/** Só a prosa. */
const prosa = (segs: Segmento[]) => segs.filter((s) => s.kind === "texto").map((s) => s.text);

test("encadeia os lances a partir da âncora", () => {
  const segs = segmentar("A ideia é e4 e5 Nf3.", START);
  expect(lances(segs)).toEqual(["e4", "e5", "Nf3"]);
  const nf3 = segs.find((s) => s.kind === "lance" && s.san === "Nf3");
  expect(nf3 && nf3.kind === "lance" && nf3.linha.map((l) => l.san)).toEqual(["e4", "e5", "Nf3"]);
  expect(prosa(segs)).toEqual(["A ideia é ", " ", " ", "."]);
});

test("cada lance guarda a posição a que leva e a casa de origem/destino", () => {
  const [lance] = segmentar("e4", START).filter((s) => s.kind === "lance");
  expect(lance.kind === "lance" && lance.uci).toBe("e2e4");
  expect(lance.kind === "lance" && lance.lastMove).toEqual(["e2", "e4"]);
  expect(lance.kind === "lance" && lance.fen).toMatch(/^rnbqkbnr\/pppppppp\/8\/8\/4P3\/8\/PPPP1PPP\/RNBQKBNR b/);
});

test("um lance ilegal na sequência recomeça a linha a partir da âncora", () => {
  // "d5? Nb4" é a linha errada; "Nd5 Qb6" é outra linha, partindo da mesma posição
  const texto = "d5? Nb4 — avaliação cai de +2.56 para +1.62 · segue Nd5 Qb6";
  const segs = segmentar(texto, MEIO);
  expect(lances(segs)).toEqual(["d5?", "Nb4", "Nd5", "Qb6"]);
  const linhas = segs.filter((s) => s.kind === "lance").map((s) => (s.kind === "lance" ? s.linha.map((l) => l.san) : []));
  expect(linhas[0]).toEqual(["d5"]);
  expect(linhas[1]).toEqual(["d5", "Nb4"]);
  // "Nd5" é ilegal depois do peão ter ido a d5: recomeça da âncora
  expect(linhas[2]).toEqual(["Nd5"]);
  expect(linhas[3]).toEqual(["Nd5", "Qb6"]);
});

test("números de lance colados entram no texto do link", () => {
  const segs = segmentar("1. e4 e5 2. Nf3", START);
  expect(lances(segs)).toEqual(["1. e4", "e5", "2. Nf3"]);
  const primeiro = segs.find((s) => s.kind === "lance");
  expect(primeiro && primeiro.kind === "lance" && primeiro.san).toBe("e4");
});

test("número com reticências (lance das pretas) também entra no link", () => {
  const segs = segmentar("e4 1... e5", START);
  expect(lances(segs)).toEqual(["e4", "1... e5"]);
});

test("sufixos de xeque, mate e apreciação ficam no link e não atrapalham a legalidade", () => {
  const segs = segmentar("Qxf7# ganha", "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4");
  expect(lances(segs)).toEqual(["Qxf7#"]);

  const outro = segmentar("e4!? e5?! Nf3+", START);
  // "Nf3+" não dá xeque, mas o sufixo sai antes do julgamento: continua legal
  expect(lances(outro)).toEqual(["e4!?", "e5?!", "Nf3+"]);
});

test("roque curto e longo viram links", () => {
  const fen = "r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1";
  expect(lances(segmentar("O-O e depois O-O-O", fen))).toEqual(["O-O", "O-O-O"]);
});

test("palavra que parece lance mas é ilegal fica como texto", () => {
  const segs = segmentar("Nc3 não serve: Bh8 é impossível.", START);
  expect(lances(segs)).toEqual(["Nc3"]);
  expect(segs.filter((s) => s.kind === "texto").map((s) => s.text).join("")).toBe(" não serve: Bh8 é impossível.");
});

test("um lance dentro de outra palavra não conta", () => {
  const segs = segmentar("xe4x e um Nc3z", START);
  expect(lances(segs)).toEqual([]);
  expect(segs).toEqual([{ kind: "texto", text: "xe4x e um Nc3z" }]);
});

test("texto sem lance nenhum sai como um segmento só", () => {
  expect(segmentar("As brancas ganham a peça.", START)).toEqual([
    { kind: "texto", text: "As brancas ganham a peça." },
  ]);
});

test("FEN inválida devolve tudo como texto", () => {
  expect(segmentar("e4 e5", "isto não é uma FEN")).toEqual([{ kind: "texto", text: "e4 e5" }]);
});

test("texto vazio não vira segmento nenhum", () => {
  expect(segmentar("", START)).toEqual([]);
});
