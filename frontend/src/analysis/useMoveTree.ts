import { useCallback, useMemo, useRef, useState } from "react";
import { Chess } from "chess.js";
import type { Key } from "chessground/types";
import { destsFrom } from "../board/dests";
import { uciToMove } from "../board/line";
import {
  MAX_NODES,
  addMove,
  countNodes,
  deleteFrom as deleteFromTree,
  fenAt,
  findNode,
  insertLine as insertLineTree,
  pathTo,
  promote as promoteTree,
  setComment as setCommentTree,
  setShapes as setShapesTree,
  toggleNag as toggleNagTree,
} from "./moveTree";
import type { Shape, Tree, TreeNode } from "./moveTree";

/** Duas listas de marcações com o mesmo conteúdo, na mesma ordem. */
function mesmasMarcacoes(a: Shape[], b: Shape[]): boolean {
  return a.length === b.length && a.every((s, i) => s.orig === b[i].orig && s.dest === b[i].dest && s.brush === b[i].brush);
}

interface State {
  tree: Tree;
  /** Nó exibido; `null` é a posição inicial da árvore. */
  currentId: string | null;
  dirty: boolean;
}

/**
 * Navegação e edição de uma árvore de lances.
 *
 * A árvore é imutável: cada mutação troca `tree` por uma nova e liga `dirty`,
 * que só volta a `false` em `markSaved()` ou `setTree()`. Navegar (incluindo
 * jogar um lance que já existe na árvore) não suja nada.
 */
export function useMoveTree(initial: Tree) {
  const ref = useRef<State>({ tree: initial, currentId: null, dirty: false });
  const [, bump] = useState(0);
  // FEN por nó, memoizado enquanto o objeto `tree` for o mesmo.
  const fenCache = useRef<{ tree: Tree | null; map: Map<string | null, string> }>({ tree: null, map: new Map() });

  const commit = useCallback((next: State) => {
    ref.current = next;
    bump((v) => v + 1);
  }, []);

  const fenOf = useCallback((tree: Tree, id: string | null): string => {
    if (fenCache.current.tree !== tree) fenCache.current = { tree, map: new Map() };
    const hit = fenCache.current.map.get(id);
    if (hit !== undefined) return hit;
    const value = fenAt(tree, id);
    fenCache.current.map.set(id, value);
    return value;
  }, []);

  /** Aplica uma mutação na árvore; `id` opcional muda também o nó atual. */
  const mutate = useCallback((fn: (s: State) => Tree, currentId?: string | null) => {
    const s = ref.current;
    const tree = fn(s);
    if (tree === s.tree && currentId === undefined) return;
    commit({ tree, currentId: currentId === undefined ? s.currentId : currentId, dirty: s.dirty || tree !== s.tree });
  }, [commit]);

  const goTo = useCallback((id: string | null) => {
    const s = ref.current;
    if (id !== null && !findNode(s.tree, id)) return;
    if (id === s.currentId) return;
    commit({ ...s, currentId: id });
  }, [commit]);

  const goStart = useCallback(() => goTo(null), [goTo]);

  const play = useCallback((uci: string): boolean => {
    const s = ref.current;
    const r = addMove(s.tree, s.currentId, uci);
    if (!r.node) return false;
    commit({ tree: r.tree, currentId: r.node.id, dirty: s.dirty || r.created });
    return true;
  }, [commit]);

  const prev = useCallback(() => {
    const s = ref.current;
    if (!s.currentId) return;
    const path = pathTo(s.tree, s.currentId);
    goTo(path.length >= 2 ? path[path.length - 2].id : null);
  }, [goTo]);

  const next = useCallback(() => {
    const s = ref.current;
    const node = findNode(s.tree, s.currentId);
    const children = node ? node.children : s.tree.root.children;
    if (children.length > 0) goTo(children[0].id);
  }, [goTo]);

  /** Irmãos do nó atual e a posição dele entre eles. */
  const siblings = useCallback((s: State): { list: TreeNode[]; at: number } => {
    if (!s.currentId) return { list: [], at: -1 };
    const path = pathTo(s.tree, s.currentId);
    const list = path.length >= 2 ? path[path.length - 2].children : s.tree.root.children;
    return { list, at: list.findIndex((n) => n.id === s.currentId) };
  }, []);

  const step = useCallback((delta: number) => {
    const { list, at } = siblings(ref.current);
    const to = at + delta;
    if (at < 0 || to < 0 || to >= list.length) return;
    goTo(list[to].id);
  }, [goTo, siblings]);

  const up = useCallback(() => step(-1), [step]);
  const down = useCallback(() => step(1), [step]);

  const promote = useCallback((id?: string) => {
    const target = id ?? ref.current.currentId;
    mutate((s) => promoteTree(s.tree, target));
  }, [mutate]);

  const deleteFrom = useCallback((id?: string) => {
    const s = ref.current;
    const target = id ?? s.currentId;
    if (!target) return;
    const path = pathTo(s.tree, target);
    if (path.length === 0) return;
    const tree = deleteFromTree(s.tree, target);
    if (tree === s.tree) return;
    // Se o nó apagado estava no caminho do atual, o atual passa a ser o pai dele.
    const atual = pathTo(s.tree, s.currentId).some((n) => n.id === target)
      ? (path.length >= 2 ? path[path.length - 2].id : null)
      : s.currentId;
    commit({ tree, currentId: atual, dirty: true });
  }, [commit]);

  /** Sem nó atual, o comentário é o enunciado (`intro`) do capítulo. */
  const setComment = useCallback((text: string) => {
    mutate((s) => (s.currentId ? setCommentTree(s.tree, s.currentId, text) : (s.tree.intro === text ? s.tree : { ...s.tree, intro: text })));
  }, [mutate]);

  const setShapes = useCallback((shapes: Shape[]) => {
    mutate((s) => {
      // o tabuleiro reavisa a mesma lista a cada redesenho: sem isto, olhar as
      // marcações de um lance já sujaria o capítulo
      const atuais = (s.currentId ? findNode(s.tree, s.currentId)?.shapes : s.tree.root.shapes) ?? [];
      return mesmasMarcacoes(atuais, shapes) ? s.tree : setShapesTree(s.tree, s.currentId, shapes);
    });
  }, [mutate]);

  const toggleNag = useCallback((nag: number) => {
    mutate((s) => toggleNagTree(s.tree, s.currentId, nag));
  }, [mutate]);

  /** Entra com uma linha a partir do nó atual; devolve quantos lances entraram. */
  const insertLine = useCallback((ucis: string[]): number => {
    const s = ref.current;
    const r = insertLineTree(s.tree, s.currentId, ucis);
    if (r.applied === 0) return 0;
    commit({ tree: r.tree, currentId: r.lastId, dirty: s.dirty || r.inserted > 0 });
    return r.applied;
  }, [commit]);

  /**
   * Troca a árvore inteira pela que veio de fora. O lance atual fica quando o
   * mesmo id leva pelos mesmos lances na árvore nova — é o que acontece ao
   * salvar, que só mexe no enunciado ou na orientação —; sendo outra linha,
   * a navegação recomeça da posição inicial.
   */
  const setTree = useCallback((tree: Tree) => {
    const s = ref.current;
    const antes = pathTo(s.tree, s.currentId);
    const agora = pathTo(tree, s.currentId);
    const mesmoLance =
      tree.fen === s.tree.fen &&
      antes.length > 0 &&
      antes.length === agora.length &&
      antes.every((n, i) => n.uci === agora[i].uci);
    commit({ tree, currentId: mesmoLance ? s.currentId : null, dirty: false });
  }, [commit]);

  const markSaved = useCallback(() => {
    const s = ref.current;
    if (!s.dirty) return;
    commit({ ...s, dirty: false });
  }, [commit]);

  const { tree, currentId, dirty } = ref.current;
  // árvore no limite: `play` e `insertLine` param de criar lances novos
  const cheia = useMemo(() => countNodes(tree) >= MAX_NODES, [tree]);
  const node = findNode(tree, currentId);
  const path = useMemo(() => pathTo(tree, currentId), [tree, currentId]);
  const fen = fenOf(tree, currentId);
  const turn = (fen.split(" ")[1] === "w" ? "white" : "black") as "white" | "black";
  const dests = useMemo(() => destsFrom(new Chess(fen)), [fen]);
  const lastMove = useMemo(() => {
    if (!node) return undefined;
    const m = uciToMove(node.uci);
    return [m.from, m.to] as [Key, Key];
  }, [node]);

  return {
    tree, currentId, node, path, fen, turn, dests, lastMove, dirty, cheia,
    play, goTo, goStart, prev, next, up, down,
    promote, deleteFrom, setComment, setShapes, toggleNag, insertLine, setTree, markSaved,
  };
}
