import {
  MAX_NODES,
  addMove,
  countNodes,
  deleteFrom,
  emptyTree,
  fenAt,
  findNode,
  insertLine,
  mainline,
  nagLabel,
  nextId,
  pathTo,
  promote,
  setComment,
  setNags,
  setShapes,
  toggleNagList,
} from "../src/analysis/moveTree";
import type { Tree } from "../src/analysis/moveTree";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

const sans = (nodes: { san: string }[]) => nodes.map((n) => n.san);

/** 1.e4 e5 2.Nf3 Nc6 na principal e 1.e4 c5 2.Nf3 d6 como variação. */
function sicilianTree(): { tree: Tree; e5: string; c5: string; d6: string } {
  const a = insertLine(emptyTree(START), null, ["e2e4", "e7e5", "g1f3", "b8c6"]);
  const b = insertLine(a.tree, null, ["e2e4", "c7c5", "g1f3", "d7d6"]);
  const e4 = b.tree.root.children[0];
  return { tree: b.tree, e5: e4.children[0].id, c5: e4.children[1].id, d6: b.lastId! };
}

test("emptyTree começa vazia e na posição informada", () => {
  const t = emptyTree(START, "black");
  expect(t.fen).toBe(START);
  expect(t.orientation).toBe("black");
  expect(t.intro).toBe("");
  expect(t.root.children).toEqual([]);
  expect(countNodes(t)).toBe(0);
  expect(nextId(t)).toBe("n1");
  expect(fenAt(t, null)).toBe(START);
});

test("addMove cria variação quando o lance difere e segue o filho quando igual", () => {
  const t0 = emptyTree(START);
  const a = addMove(t0, null, "e2e4");
  expect(a.created).toBe(true);
  expect(a.node?.san).toBe("e4");
  expect(t0.root.children).toEqual([]); // árvore original intacta

  const b = addMove(a.tree, a.node!.id, "e7e5");
  const c = addMove(b.tree, a.node!.id, "c7c5");
  expect(c.created).toBe(true);
  expect(c.node?.san).toBe("c5");
  expect(sans(c.tree.root.children[0].children)).toEqual(["e5", "c5"]); // variação vai para o fim

  const again = addMove(c.tree, a.node!.id, "e7e5");
  expect(again.created).toBe(false);
  expect(again.node?.id).toBe(b.node!.id);
  expect(again.tree).toBe(c.tree); // seguir um filho existente não muda a árvore
  expect(countNodes(c.tree)).toBe(3);
});

test("addMove ignora lance ilegal e pai inexistente", () => {
  const t = emptyTree(START);
  const bad = addMove(t, null, "e2e5");
  expect(bad.node).toBeNull();
  expect(bad.created).toBe(false);
  expect(bad.tree).toBe(t);

  const orphan = addMove(t, "n99", "e2e4");
  expect(orphan.node).toBeNull();
  expect(orphan.tree).toBe(t);
});

test("addMove normaliza a promoção e reconhece o filho existente", () => {
  const t = emptyTree("8/4P3/8/8/8/8/8/K6k w - - 0 1");
  const a = addMove(t, null, "e7e8q");
  expect(a.node?.san).toBe("e8=Q");
  const b = addMove(a.tree, null, "e7e8q");
  expect(b.created).toBe(false);
  expect(b.node?.id).toBe(a.node!.id);
});

test("findNode e pathTo", () => {
  const { tree, c5, d6 } = sicilianTree();
  expect(findNode(tree, d6)?.san).toBe("d6");
  expect(findNode(tree, "n999")).toBeNull();
  expect(sans(pathTo(tree, d6))).toEqual(["e4", "c5", "Nf3", "d6"]);
  expect(sans(pathTo(tree, c5))).toEqual(["e4", "c5"]);
  expect(pathTo(tree, null)).toEqual([]);
  expect(pathTo(tree, "n999")).toEqual([]);
});

test("mainline segue o primeiro filho de cada nível", () => {
  const { tree } = sicilianTree();
  expect(sans(mainline(tree))).toEqual(["e4", "e5", "Nf3", "Nc6"]);
});

test("promote de uma variação aninhada torna-a linha principal em todos os níveis", () => {
  const { tree, d6, e5 } = sicilianTree();
  const p = promote(tree, d6);
  expect(sans(mainline(p))).toEqual(["e4", "c5", "Nf3", "d6"]);
  expect(sans(mainline(tree))).toEqual(["e4", "e5", "Nf3", "Nc6"]); // original intacta
  expect(countNodes(p)).toBe(countNodes(tree)); // nada some ao promover
  expect(findNode(p, e5)?.san).toBe("e5"); // a antiga principal vira variação
  expect(promote(p, "n999")).toBe(p);
});

test("fenAt continua correto depois da promoção", () => {
  const { tree, d6, e5 } = sicilianTree();
  const p = promote(tree, d6);
  expect(fenAt(p, d6)).toBe(fenAt(tree, d6));
  expect(fenAt(p, e5)).toBe(fenAt(tree, e5));
  expect(fenAt(p, d6).split(" ")[0]).toBe("rnbqkbnr/pp2pppp/3p4/2p5/4P3/5N2/PPPP1PPP/RNBQKB1R");
  expect(fenAt(p, null)).toBe(START);
});

test("deleteFrom remove o nó e toda a subárvore", () => {
  const { tree, c5, d6, e5 } = sicilianTree();
  const d = deleteFrom(tree, c5);
  expect(findNode(d, c5)).toBeNull();
  expect(findNode(d, d6)).toBeNull();
  expect(findNode(d, e5)?.san).toBe("e5");
  expect(countNodes(d)).toBe(countNodes(tree) - 3);
  expect(countNodes(tree)).toBe(7);
  expect(deleteFrom(d, "n999")).toBe(d);

  const raiz = deleteFrom(tree, tree.root.children[0].id);
  expect(raiz.root.children).toEqual([]);
});

test("insertLine segue os filhos existentes e para no primeiro lance ilegal", () => {
  const t = emptyTree(START);
  const a = insertLine(t, null, ["e2e4", "e7e5", "g1f3"]);
  expect(a.inserted).toBe(3);
  expect(a.applied).toBe(3);
  expect(findNode(a.tree, a.lastId!)?.san).toBe("Nf3");

  const b = insertLine(a.tree, null, ["e2e4", "e7e5", "b1c3", "e2e4"]);
  expect(b.inserted).toBe(1); // só o Nc3 é novo; o e4 final é ilegal
  expect(b.applied).toBe(3);
  expect(findNode(b.tree, b.lastId!)?.san).toBe("Nc3");
  expect(countNodes(b.tree)).toBe(4);

  const c = insertLine(a.tree, null, []);
  expect(c.inserted).toBe(0);
  expect(c.lastId).toBeNull();
  expect(c.tree).toBe(a.tree);
});

test("insertLine a partir de um nó do meio da árvore", () => {
  const { tree, c5 } = sicilianTree();
  const r = insertLine(tree, c5, ["b1c3", "b8c6"]);
  expect(r.inserted).toBe(2);
  expect(sans(pathTo(r.tree, r.lastId!))).toEqual(["e4", "c5", "Nc3", "Nc6"]);
});

test("setComment, setShapes e setNags devolvem uma árvore nova", () => {
  const { tree, c5 } = sicilianTree();
  const shapes = [{ orig: "d4", brush: "red" }, { orig: "c5", dest: "d4", brush: "green" }];
  const t1 = setComment(tree, c5, "Siciliana");
  const t2 = setShapes(t1, c5, shapes);
  const t3 = setNags(t2, c5, [5]);
  expect(findNode(t3, c5)?.comment).toBe("Siciliana");
  expect(findNode(t3, c5)?.shapes).toEqual(shapes);
  expect(findNode(t3, c5)?.nags).toEqual([5]);
  expect(findNode(tree, c5)?.comment).toBe(""); // original intacta
  expect(findNode(tree, c5)?.nags).toEqual([]);
  expect(setComment(t3, "n999", "x")).toBe(t3);
});

test("nextId ignora ids fora do padrão e não repete os existentes", () => {
  const { tree } = sicilianTree();
  expect(nextId(tree)).toBe("n8");
  const t = addMove(tree, null, "d2d4").tree;
  expect(findNode(t, "n8")?.san).toBe("d4");
  expect(nextId(t)).toBe("n9");
});

test("addMove respeita o limite de nós", () => {
  // Árvore sintética larga: só a contagem importa para o limite.
  const irmaos = (n: number): Tree => ({
    ...emptyTree(START),
    root: {
      children: Array.from({ length: n }, (_, i) => ({
        id: `n${i + 1}`, uci: "e2e4", san: "e4", comment: "", shapes: [], nags: [], children: [],
      })),
    },
  });

  const quase = irmaos(MAX_NODES - 1);
  const ok = addMove(quase, null, "d2d4");
  expect(ok.created).toBe(true);
  expect(countNodes(ok.tree)).toBe(MAX_NODES);

  const cheio = addMove(ok.tree, null, "g1f3");
  expect(cheio.node).toBeNull();
  expect(cheio.created).toBe(false);
  expect(cheio.tree).toBe(ok.tree);
  // seguir um filho existente continua funcionando com a árvore cheia
  expect(addMove(ok.tree, null, "e2e4").node?.id).toBe("n1");
});

test("toggleNagList mantém no máximo um símbolo de qualidade de lance", () => {
  expect(toggleNagList([], 1)).toEqual([1]);
  expect(toggleNagList([1], 1)).toEqual([]);
  expect(toggleNagList([1], 4)).toEqual([4]);
  expect(toggleNagList([3, 14], 6)).toEqual([6, 14]);
  expect(toggleNagList([14], 16)).toEqual([14, 16]); // avaliações não são exclusivas
  expect(toggleNagList([14, 16], 14)).toEqual([16]);
});

test("nagLabel devolve o símbolo", () => {
  expect([1, 2, 3, 4, 5, 6].map(nagLabel)).toEqual(["!", "?", "!!", "??", "!?", "?!"]);
  expect(nagLabel(14)).toBe("⩲");
  expect(nagLabel(999)).toBe("$999");
});
