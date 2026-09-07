import { act, renderHook } from "@testing-library/react";

// só o `play` do módulo de som vira dublê
vi.mock("../src/lib/sound", async (original) => ({
  ...(await original<typeof import("../src/lib/sound")>()),
  play: vi.fn(),
}));

import { play as tocar } from "../src/lib/sound";
import { useMoveTree } from "../src/analysis/useMoveTree";
import { emptyTree, findNode, insertLine, mainline } from "../src/analysis/moveTree";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const sans = (nodes: { san: string }[]) => nodes.map((n) => n.san);

test("play avança currentId, marca dirty e ignora lance ilegal", () => {
  const { result } = renderHook(() => useMoveTree(emptyTree(START)));
  expect(result.current.currentId).toBeNull();
  expect(result.current.fen).toBe(START);
  expect(result.current.turn).toBe("white");
  expect(result.current.dirty).toBe(false);
  expect(result.current.dests.get("e2")).toContain("e4");

  act(() => { expect(result.current.play("e2e5")).toBe(false); });
  expect(result.current.dirty).toBe(false);

  act(() => { result.current.play("e2e4"); });
  expect(result.current.currentId).toBe("n1");
  expect(result.current.turn).toBe("black");
  expect(result.current.lastMove).toEqual(["e2", "e4"]);
  expect(sans(result.current.path)).toEqual(["e4"]);
  expect(result.current.node?.san).toBe("e4");
  expect(result.current.dirty).toBe(true);

  act(() => { result.current.markSaved(); });
  expect(result.current.dirty).toBe(false);
  // repetir um lance já existente só navega: não suja a árvore
  act(() => { result.current.goStart(); result.current.play("e2e4"); });
  expect(result.current.currentId).toBe("n1");
  expect(result.current.dirty).toBe(false);
});

test("prev, next, goStart, goTo e navegação entre irmãos com up/down", () => {
  const { result } = renderHook(() => useMoveTree(emptyTree(START)));
  act(() => { result.current.insertLine(["e2e4", "e7e5"]); });
  act(() => { result.current.goStart(); result.current.insertLine(["e2e4", "c7c5"]); });
  act(() => { result.current.goStart(); result.current.insertLine(["e2e4", "e7e6"]); });
  const e4 = result.current.tree.root.children[0];
  expect(sans(e4.children)).toEqual(["e5", "c5", "e6"]);

  act(() => { result.current.goTo(e4.children[1].id) });
  expect(result.current.node?.san).toBe("c5");
  act(() => { result.current.up(); });
  expect(result.current.node?.san).toBe("e5");
  act(() => { result.current.up(); });
  expect(result.current.node?.san).toBe("e5"); // já é o primeiro irmão
  act(() => { result.current.down(); result.current.down(); });
  expect(result.current.node?.san).toBe("e6");
  act(() => { result.current.down(); });
  expect(result.current.node?.san).toBe("e6"); // já é o último irmão

  act(() => { result.current.prev(); });
  expect(result.current.node?.san).toBe("e4");
  act(() => { result.current.prev(); });
  expect(result.current.currentId).toBeNull();
  act(() => { result.current.prev(); });
  expect(result.current.currentId).toBeNull();
  act(() => { result.current.next(); result.current.next(); });
  expect(result.current.node?.san).toBe("e5"); // next segue o primeiro filho
  act(() => { result.current.next(); });
  expect(result.current.node?.san).toBe("e5"); // sem filhos: fica onde está
  act(() => { result.current.goStart(); });
  expect(result.current.currentId).toBeNull();
  expect(result.current.fen).toBe(START);
});

test("promote torna a linha atual a principal", () => {
  const { result } = renderHook(() => useMoveTree(emptyTree(START)));
  act(() => { result.current.insertLine(["e2e4", "e7e5", "g1f3"]); });
  act(() => { result.current.goStart(); result.current.insertLine(["e2e4", "c7c5", "g1f3"]); });
  act(() => { result.current.markSaved(); });
  const atual = result.current.currentId;
  act(() => { result.current.promote(); });
  expect(sans(mainline(result.current.tree))).toEqual(["e4", "c5", "Nf3"]);
  expect(result.current.currentId).toBe(atual); // promover não muda o nó atual
  expect(result.current.dirty).toBe(true);
});

test("deleteFrom apaga a subárvore e volta o nó atual para o pai", () => {
  const { result } = renderHook(() => useMoveTree(emptyTree(START)));
  act(() => { result.current.insertLine(["e2e4", "e7e5", "g1f3", "b8c6"]); });
  const alvo = result.current.tree.root.children[0].children[0].id; // e5
  act(() => { result.current.markSaved(); result.current.deleteFrom(alvo); });
  expect(sans(mainline(result.current.tree))).toEqual(["e4"]);
  expect(result.current.node?.san).toBe("e4"); // o atual estava abaixo do apagado
  expect(result.current.dirty).toBe(true);

  act(() => { result.current.deleteFrom(); }); // apaga o nó atual
  expect(result.current.tree.root.children).toEqual([]);
  expect(result.current.currentId).toBeNull();
});

test("setComment, setShapes e toggleNag no nó atual; comentário do início vira intro", () => {
  const { result } = renderHook(() => useMoveTree(emptyTree(START)));
  act(() => { result.current.setComment("Enunciado"); });
  expect(result.current.tree.intro).toBe("Enunciado");

  act(() => { result.current.play("e2e4"); result.current.markSaved(); });
  act(() => { result.current.setComment("Abertura do rei"); });
  act(() => { result.current.setShapes([{ orig: "e4", brush: "green" }]); });
  act(() => { result.current.toggleNag(1); });
  act(() => { result.current.toggleNag(5); });
  const n = findNode(result.current.tree, result.current.currentId!)!;
  expect(n.comment).toBe("Abertura do rei");
  expect(n.shapes).toEqual([{ orig: "e4", brush: "green" }]);
  expect(n.nags).toEqual([5]); // 1 e 5 são exclusivos entre si
  expect(result.current.dirty).toBe(true);
  act(() => { result.current.toggleNag(5); });
  expect(findNode(result.current.tree, result.current.currentId!)!.nags).toEqual([]);
});

test("insertLine avança até o último lance legal e setTree limpa o dirty", () => {
  const { result } = renderHook(() => useMoveTree(emptyTree(START)));
  act(() => { expect(result.current.insertLine(["e2e4", "e7e5", "e2e4"])).toBe(2); });
  expect(sans(result.current.path)).toEqual(["e4", "e5"]);
  expect(result.current.dirty).toBe(true);

  const outra = emptyTree("8/8/8/8/8/8/8/K6k w - - 0 1", "black");
  act(() => { result.current.setTree(outra); });
  expect(result.current.tree).toBe(outra);
  expect(result.current.currentId).toBeNull();
  expect(result.current.fen).toBe(outra.fen);
  expect(result.current.dirty).toBe(false);
});

test("setTree mantém o lance atual quando a árvore nova traz o mesmo caminho", () => {
  const { result } = renderHook(() => useMoveTree(emptyTree(START)));
  act(() => { result.current.insertLine(["e2e4", "e7e5"]); });
  const atual = result.current.currentId;
  const fen = result.current.fen;

  // o pai devolve a mesma linha com outro enunciado (é o que ele faz ao salvar)
  const outra = { ...result.current.tree, intro: "novo enunciado" };
  act(() => { result.current.setTree(outra); });
  expect(result.current.tree).toBe(outra);
  expect(result.current.currentId).toBe(atual);
  expect(result.current.fen).toBe(fen);
  expect(result.current.dirty).toBe(false);

  // já uma árvore em que aquele id leva a outros lances recomeça do início
  const trocada = insertLine(emptyTree(START), null, ["d2d4", "d7d5"]).tree;
  act(() => { result.current.setTree(trocada); });
  expect(result.current.currentId).toBeNull();
});

test("setShapes não suja a árvore quando as marcações são as mesmas", () => {
  const { result } = renderHook(() => useMoveTree(emptyTree(START)));
  act(() => { result.current.play("e2e4"); result.current.markSaved(); });
  const antes = result.current.tree;

  act(() => { result.current.setShapes([{ orig: "e4", brush: "green" }]); });
  expect(result.current.dirty).toBe(true);
  const comMarcacao = result.current.tree;

  // o chessground reavisa a mesma lista a cada redesenho: nada muda
  act(() => { result.current.markSaved(); });
  act(() => { result.current.setShapes([{ orig: "e4", brush: "green" }]); });
  expect(result.current.tree).toBe(comMarcacao);
  expect(result.current.dirty).toBe(false);
  expect(antes).not.toBe(comMarcacao);
});

test("jogar um lance toca o som correspondente", () => {
  vi.mocked(tocar).mockClear();
  const { result } = renderHook(() => useMoveTree(emptyTree(START)));

  // lance ilegal não soa
  act(() => { result.current.play("e2e5"); });
  expect(tocar).not.toHaveBeenCalled();

  act(() => { result.current.play("e2e4"); });
  expect(tocar).toHaveBeenLastCalledWith("move");

  act(() => { result.current.play("d7d5"); });
  act(() => { result.current.play("e4d5"); });
  expect(tocar).toHaveBeenLastCalledWith("capture");

  act(() => { result.current.play("d8d5"); });
  expect(tocar).toHaveBeenLastCalledWith("capture");

  // com o peão de e2 já em d5, a dama em e5 dá xeque pela coluna
  act(() => { result.current.play("b1c3"); });
  act(() => { result.current.play("d5e5"); });
  expect(tocar).toHaveBeenLastCalledWith("check");

  // navegar não toca nada
  const antes = vi.mocked(tocar).mock.calls.length;
  act(() => { result.current.prev(); });
  act(() => { result.current.goStart(); });
  act(() => { result.current.next(); });
  expect(vi.mocked(tocar).mock.calls.length).toBe(antes);
});
