import { expect, test } from "vitest";
import { segmentar } from "../src/analysis/moveText";
import type { Segmento } from "../src/analysis/moveText";
import { novoChess } from "../src/lib/chess";

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

test("candidato colado numa palavra não engole o lance seguinte", () => {
  // o número "12." é parte do match recusado: pular o match inteiro perderia o "e4"
  const segs = segmentar("no12. e4 segue", START);
  expect(lances(segs)).toEqual(["e4"]);
  expect(prosa(segs)).toEqual(["no12. ", " segue"]);
});

test("notação longa não vira dois links encadeados", () => {
  // dama em d5 e peão em h4: soltos, "Qd1" e "h5" seriam legais
  const fen = "4k3/8/8/3Q4/7P/8/8/4K3 w - - 0 1";
  expect(lances(segmentar("Qd1-h5 é notação longa", fen))).toEqual([]);
  expect(lances(segmentar("Qd1 e h5", fen))).toEqual(["Qd1", "h5"]);
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

test("o número do lance manda a sequência de volta para a posição certa (estilo dos livros antigos)", () => {
  // Scheve × Teichmann depois de 7.a4; comentário do Chernev com "7 ... Nf6 8 a5" e variações
  const c = novoChess();
  for (const m of ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "c3", "Qe7", "O-O", "d6", "d4", "Bb6", "a4"]) c.move(m);
  const texto = "by 7 ... Nf6 8 a5. If then 8....Bxa5, 9 d5 and after 9...Nd8, 10 Rxa5. Should Black play 8...Nxa5, then 9 Rxa5 Bxa5 10 Qa4+.";
  const segs = segmentar(texto, c.fen());
  const lances = segs.filter((s) => s.kind === "lance") as Extract<Segmento, { kind: "lance" }>[];
  expect(lances.map((l) => l.text)).toEqual(["7 ... Nf6", "8 a5", "8....Bxa5", "9 d5", "9...Nd8", "10 Rxa5", "8...Nxa5", "9 Rxa5", "Bxa5", "10 Qa4+"]);
  // "8...Nxa5" volta para a posição depois de 8 a5, e não emenda no 10º lance
  expect(lances[6].linha.map((l) => l.san)).toEqual(["Nf6", "a5", "Nxa5"]);
  expect(lances[9].linha.map((l) => l.san)).toEqual(["Nf6", "a5", "Nxa5", "Rxa5", "Bxa5", "Qa4+"]);
});

test("um número que não bate com nada na linha não impede o lance de encadear", () => {
  const segs = segmentar("1. e4 e5 12. Nf3", START);
  const lances = segs.filter((s) => s.kind === "lance") as Extract<Segmento, { kind: "lance" }>[];
  expect(lances.map((l) => l.san)).toEqual(["e4", "e5", "Nf3"]);
  expect(lances[2].linha.length).toBe(3);
});

// --- lances resolvidos pelas linhas declaradas ---------------------------

/** A posição do exercício do vídeo: brancas a jogar, 18º lance. */
const VIDEO = "r4rk1/5ppp/pqn5/1p1QPpN1/3P4/P7/1P3PPP/R4RK1 w - - 1 18";
/** A linha que a explicação declarou a partir dela, com o 18...Ne7 que a prosa pula. */
const LINHA_VIDEO = [{ fen: VIDEO, lances: ["Rac1", "Ne7", "Qc5", "Qxc5", "dxc5"] }];

const soLances = (segs: Segmento[]) => segs.filter((s) => s.kind === "lance") as Extract<Segmento, { kind: "lance" }>[];

test("lance numerado que a prosa pulou é resolvido pela linha declarada", () => {
  const segs = segmentar("18.Rac1? 19.Qc5 Qxc5 20.dxc5 troca as damas", VIDEO, LINHA_VIDEO);
  const ls = soLances(segs);
  expect(ls.map((l) => l.text)).toEqual(["18.Rac1?", "19.Qc5", "Qxc5", "20.dxc5"]);
  // o 18...Ne7 vem da linha conhecida: sem ele "19.Qc5" caía na dama preta e o tabuleiro
  // da prévia não tinha nada a ver com a explicação
  expect(ls[1].linha.map((l) => l.san)).toEqual(["Rac1", "Ne7", "Qc5"]);
  // a posição de 19.Qc5 é a de depois de 18.Rac1 Ne7 19.Qc5, com as pretas a jogar
  expect(ls[1].fen).toBe("r4rk1/4nppp/pq6/1pQ1PpN1/3P4/P7/1P3PPP/2R2RK1 b - - 4 19");
  expect(ls[1].lastMove).toEqual(["d5", "c5"]);
  // e a cadeia continua a partir dali, com os lances seguintes da prosa
  expect(ls[2].linha.map((l) => l.san)).toEqual(["Rac1", "Ne7", "Qc5", "Qxc5"]);
  expect(ls[3].linha.map((l) => l.san)).toEqual(["Rac1", "Ne7", "Qc5", "Qxc5", "dxc5"]);
});

test("sem linhas conhecidas o comportamento antigo se mantém", () => {
  const ls = soLances(segmentar("18.Rac1? 19.Qc5 Qxc5", VIDEO));
  expect(ls.map((l) => l.text)).toEqual(["18.Rac1?", "19.Qc5", "Qxc5"]);
  // encadeando às cegas: "Qc5" vira lance das pretas logo depois de Rac1
  expect(ls[1].linha.map((l) => l.san)).toEqual(["Rac1", "Qc5"]);
});

test("a prosa pode ramificar da linha declarada com outro lance na mesma altura", () => {
  // 19.Qd6 não é o Qc5 da linha, mas é legal na posição em que a linha chega ao 19º
  const ls = soLances(segmentar("18.Rac1? 19.Qd6 seria outra ideia", VIDEO, LINHA_VIDEO));
  expect(ls.map((l) => l.text)).toEqual(["18.Rac1?", "19.Qd6"]);
  expect(ls[1].linha.map((l) => l.san)).toEqual(["Rac1", "Ne7", "Qd6"]);
});

test("linha declarada que não chega àquela altura não muda nada", () => {
  const curta = [{ fen: VIDEO, lances: ["Rac1"] }];
  const ls = soLances(segmentar("18.Rac1? 19.Qc5", VIDEO, curta));
  expect(ls[1].linha.map((l) => l.san)).toEqual(["Rac1", "Qc5"]);
});
