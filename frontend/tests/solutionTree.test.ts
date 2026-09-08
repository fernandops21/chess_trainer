import { expect, test } from "vitest";
import type { Solution } from "../src/api/types";
import { mainline } from "../src/analysis/moveTree";
import { treeFromSolution, withMistakeVariation } from "../src/analysis/solutionTree";
import type { SolutionSource } from "../src/analysis/solutionTree";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
/** Posição depois de 1.e4: é a `fen_start` de todos os casos daqui. */
const APOS_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1";

const solucao = (over: Partial<Solution> = {}): Solution => ({
  moves: [
    { uci: "e7e5", by: "solver", alternatives: [] },
    { uci: "g1f3", by: "engine", alternatives: [] },
    { uci: "b8c6", by: "solver", alternatives: [] },
  ],
  explanation_pv: [],
  ...over,
});

/** Exercício sem o lance do adversário: a árvore começa em `fen_start`. */
const sem = (over: Partial<SolutionSource> = {}): SolutionSource => ({
  fen_start: APOS_E4,
  side_to_move: "black",
  solution: solucao(),
  fen_before: null,
  last_move: null,
  ...over,
});

/** O mesmo exercício com o lance do adversário (1.e4) na frente. */
const com = (over: Partial<SolutionSource> = {}): SolutionSource =>
  sem({ fen_before: START, last_move: "e2e4", ...over });

const sans = (s: SolutionSource) => mainline(treeFromSolution(s)).map((n) => n.san);

test("sem o lance do adversário a raiz é a posição do exercício", () => {
  const t = treeFromSolution(sem());
  expect(t.fen).toBe(APOS_E4);
  expect(t.orientation).toBe("black");
  expect(mainline(t).map((n) => n.san)).toEqual(["e5", "Nf3", "Nc6"]);
});

test("com o lance do adversário a raiz recua e ele abre a linha principal", () => {
  const t = treeFromSolution(com());
  expect(t.fen).toBe(START);
  expect(mainline(t).map((n) => n.san)).toEqual(["e4", "e5", "Nf3", "Nc6"]);
});

test("lance do adversário incoerente com a posição cai na posição do exercício", () => {
  expect(sans(com({ last_move: "a7a5" }))).toEqual(["e5", "Nf3", "Nc6"]);
  expect(treeFromSolution(com({ last_move: "a7a5" })).fen).toBe(APOS_E4);
});

test("lance do adversário que leva a outra posição também cai na do exercício", () => {
  // 1.d4 é legal na raiz guardada, mas não leva à `fen_start` (que é depois de
  // 1.e4): a árvore ficaria contando outra história e recomeça no exercício
  const t = treeFromSolution(com({ last_move: "d2d4" }));
  expect(t.fen).toBe(APOS_E4);
  expect(mainline(t).map((n) => n.san)).toEqual(["e5", "Nf3", "Nc6"]);
});

test("o contador de lances não desmancha a árvore com o lance do adversário", () => {
  // mesma posição da `fen_start`, com outro contador: os 4 primeiros campos é
  // que dizem se o lance leva onde deve
  const outroContador = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 3 9";
  const t = treeFromSolution(com({ fen_start: outroContador }));
  expect(t.fen).toBe(START);
  expect(mainline(t).map((n) => n.san)).toEqual(["e4", "e5", "Nf3", "Nc6"]);
});

test("o enunciado vira o intro da árvore", () => {
  expect(treeFromSolution(sem({ solution: solucao({ intro: "Pretas jogam." }) })).intro).toBe("Pretas jogam.");
  expect(treeFromSolution(sem()).intro).toBe("");
});

test("os comentários vão para os lances da solução", () => {
  const s = solucao({ comments: { "0": "abre a diagonal", "2": "desenvolve com ataque" } });
  const linha = mainline(treeFromSolution(sem({ solution: s })));
  expect(linha.map((n) => n.comment)).toEqual(["abre a diagonal", "", "desenvolve com ataque"]);
});

test("com o lance do adversário os comentários andam um lance", () => {
  const s = solucao({ comments: { "0": "abre a diagonal", "2": "desenvolve com ataque" } });
  const linha = mainline(treeFromSolution(com({ solution: s })));
  expect(linha.map((n) => n.comment)).toEqual(["", "abre a diagonal", "", "desenvolve com ataque"]);
});

test("as marcações de 'start' ficam na posição do exercício e as demais nos lances", () => {
  const marcas = { start: [{ orig: "e4", brush: "green" }], "1": [{ orig: "g1", dest: "f3", brush: "blue" }] };
  const semLance = treeFromSolution(sem({ solution: solucao({ shapes: marcas }) }));
  expect(semLance.root.shapes).toEqual(marcas.start);
  expect(mainline(semLance)[1].shapes).toEqual(marcas["1"]);

  // com o lance do adversário, `fen_start` é a posição do nó dele: as marcações vão para lá
  const comLance = treeFromSolution(com({ solution: solucao({ shapes: marcas }) }));
  expect(comLance.root.shapes ?? []).toEqual([]);
  expect(mainline(comLance)[0].shapes).toEqual(marcas.start);
  expect(mainline(comLance)[2].shapes).toEqual(marcas["1"]);
});

test("os lances errados previstos viram variações no primeiro lance do solucionador", () => {
  const s = solucao({ wrong_moves: { d7d5: "as brancas comem de graça", a7a6: "lento demais" } });
  const t = treeFromSolution(sem({ solution: s }));
  expect(t.root.children.map((n) => n.san)).toEqual(["e5", "d5", "a6"]);
  expect(t.root.children[1].comment).toBe("as brancas comem de graça");
  expect(t.root.children[2].comment).toBe("lento demais");

  // com o lance do adversário elas viram irmãs do primeiro lance do solucionador
  const c = treeFromSolution(com({ solution: s }));
  expect(c.root.children.map((n) => n.san)).toEqual(["e4"]);
  expect(c.root.children[0].children.map((n) => n.san)).toEqual(["e5", "d5", "a6"]);
});

test("lance errado ilegal é ignorado", () => {
  const s = solucao({ wrong_moves: { h8h1: "impossível" } });
  expect(treeFromSolution(sem({ solution: s })).root.children.map((n) => n.san)).toEqual(["e5"]);
});

test("o lance da partida entra como variação com a continuação da punição", () => {
  const t = withMistakeVariation(treeFromSolution(sem()), APOS_E4, "f7f5", "Na partida você jogou f5", ["e4f5", "d7d6"]);
  const variacao = t.root.children[1];
  expect(variacao.san).toBe("f5");
  expect(variacao.comment).toBe("Na partida você jogou f5");
  expect(variacao.children[0].san).toBe("exf5");
  expect(variacao.children[0].children[0].san).toBe("d6");
});

test("com o lance do adversário a variação da partida sai do nó dele", () => {
  const t = withMistakeVariation(treeFromSolution(com()), APOS_E4, "f7f5", "Na partida você jogou f5", []);
  expect(t.root.children.map((n) => n.san)).toEqual(["e4"]);
  expect(t.root.children[0].children.map((n) => n.san)).toEqual(["e5", "f5"]);
});

test("lance da partida ilegal devolve a árvore intacta", () => {
  const base = treeFromSolution(sem());
  expect(withMistakeVariation(base, APOS_E4, "h8h1", "nada", [])).toBe(base);
});
