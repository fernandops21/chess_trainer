import { Chess } from "chess.js";
import type { Shape } from "../api/types";
import { uciToMove } from "../board/line";

export type { Shape };

/**
 * Árvore de lances de um capítulo.
 *
 * Um nó guarda o lance que leva à posição dele (a posição inicial fica em
 * `tree.fen`). O primeiro filho de cada nível é a linha principal; os demais
 * são variações. Todas as funções deste módulo são puras: nunca alteram a
 * árvore recebida, devolvem uma nova com compartilhamento dos ramos intactos.
 */
export interface TreeNode {
  id: string;
  uci: string;
  san: string;
  comment: string;
  shapes: Shape[];
  nags: number[];
  children: TreeNode[];
}

export interface TreeRoot {
  /** Marcações do autor na posição inicial (chave "start" da solução). */
  shapes?: Shape[];
  children: TreeNode[];
}

export interface Tree {
  fen: string;
  orientation: "white" | "black";
  /** Enunciado do capítulo: comentário da posição inicial. */
  intro: string;
  root: TreeRoot;
}

/** Teto de nós por capítulo (o backend valida o mesmo limite). */
export const MAX_NODES = 2000;

/** NAGs de qualidade do lance: no máximo um deles por nó. */
export const MOVE_NAGS = [1, 2, 3, 4, 5, 6];

const NAG_LABELS: Record<number, string> = {
  1: "!", 2: "?", 3: "!!", 4: "??", 5: "!?", 6: "?!",
  7: "□", 10: "=", 13: "∞", 14: "⩲", 15: "⩱", 16: "±", 17: "∓",
  18: "+−", 19: "−+", 22: "⨀", 32: "⟳", 36: "→", 40: "↑", 132: "⇆",
};

/** Símbolo de um NAG (`$14` quando desconhecido). */
export function nagLabel(n: number): string {
  return NAG_LABELS[n] ?? `$${n}`;
}

/**
 * Liga/desliga um NAG numa lista, mantendo no máximo um símbolo de qualidade
 * de lance (`!`, `?`, `!!`, `??`, `!?`, `?!`). Devolve uma lista nova ordenada.
 */
export function toggleNagList(nags: number[], n: number): number[] {
  if (nags.includes(n)) return nags.filter((x) => x !== n);
  const base = MOVE_NAGS.includes(n) ? nags.filter((x) => !MOVE_NAGS.includes(x)) : nags;
  return [...base, n].sort((a, b) => a - b);
}

export function emptyTree(fen: string, orientation: "white" | "black" = "white"): Tree {
  return { fen, orientation, intro: "", root: { children: [] } };
}

function withChildren(tree: Tree, children: TreeNode[]): Tree {
  // preserva `root.shapes` (e qualquer outro campo da raiz) ao trocar os filhos
  return { ...tree, root: { ...tree.root, children } };
}

export function countNodes(tree: Tree): number {
  let total = 0;
  const walk = (nodes: TreeNode[]) => {
    for (const n of nodes) { total++; walk(n.children); }
  };
  walk(tree.root.children);
  return total;
}

/** Próximo id livre no formato `n<contador>`; ids existentes nunca mudam. */
export function nextId(tree: Tree): string {
  let max = 0;
  const walk = (nodes: TreeNode[]) => {
    for (const n of nodes) {
      const m = /^n(\d+)$/.exec(n.id);
      if (m) max = Math.max(max, Number(m[1]));
      walk(n.children);
    }
  };
  walk(tree.root.children);
  return `n${max + 1}`;
}

export function findNode(tree: Tree, id: string | null): TreeNode | null {
  if (!id) return null;
  const walk = (nodes: TreeNode[]): TreeNode | null => {
    for (const n of nodes) {
      if (n.id === id) return n;
      const hit = walk(n.children);
      if (hit) return hit;
    }
    return null;
  };
  return walk(tree.root.children);
}

/** Nós da raiz até `id` (inclusive). Lista vazia se `id` for nulo ou não existir. */
export function pathTo(tree: Tree, id: string | null): TreeNode[] {
  if (!id) return [];
  const walk = (nodes: TreeNode[], acc: TreeNode[]): TreeNode[] | null => {
    for (const n of nodes) {
      const here = [...acc, n];
      if (n.id === id) return here;
      const hit = walk(n.children, here);
      if (hit) return hit;
    }
    return null;
  };
  return walk(tree.root.children, []) ?? [];
}

/** Linha principal: o primeiro filho de cada nível. */
export function mainline(tree: Tree): TreeNode[] {
  const out: TreeNode[] = [];
  let nodes = tree.root.children;
  while (nodes.length > 0) {
    out.push(nodes[0]);
    nodes = nodes[0].children;
  }
  return out;
}

/** FEN depois dos lances da raiz até `id` (a posição inicial quando `id` é nulo). */
export function fenAt(tree: Tree, id: string | null): string {
  const path = pathTo(tree, id);
  if (path.length === 0) return tree.fen;
  const chess = new Chess(tree.fen);
  for (const n of path) {
    try { chess.move(uciToMove(n.uci)); } catch { break; }
  }
  return chess.fen();
}

/**
 * Aplica `fn` ao nó `id`. `fn` devolvendo `null` remove o nó (e a subárvore).
 * Devolve `null` quando o id não existe — assim quem chama pode preservar a
 * árvore original por identidade.
 */
function mapNode(nodes: TreeNode[], id: string, fn: (n: TreeNode) => TreeNode | null): TreeNode[] | null {
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    if (n.id === id) {
      const next = fn(n);
      const copy = nodes.slice();
      if (next === null) copy.splice(i, 1);
      else copy[i] = next;
      return copy;
    }
    const sub = mapNode(n.children, id, fn);
    if (sub) {
      const copy = nodes.slice();
      copy[i] = { ...n, children: sub };
      return copy;
    }
  }
  return null;
}

function patch(tree: Tree, id: string | null, fn: (n: TreeNode) => TreeNode): Tree {
  if (!id) return tree;
  const children = mapNode(tree.root.children, id, fn);
  return children ? withChildren(tree, children) : tree;
}

export function setComment(tree: Tree, id: string | null, comment: string): Tree {
  return patch(tree, id, (n) => ({ ...n, comment }));
}

export function setShapes(tree: Tree, id: string | null, shapes: Shape[]): Tree {
  // na posição inicial (sem nó atual) as marcações vivem na raiz
  if (id === null) return { ...tree, root: { ...tree.root, shapes } };
  return patch(tree, id, (n) => ({ ...n, shapes }));
}

export function setNags(tree: Tree, id: string | null, nags: number[]): Tree {
  return patch(tree, id, (n) => ({ ...n, nags }));
}

export function toggleNag(tree: Tree, id: string | null, nag: number): Tree {
  return patch(tree, id, (n) => ({ ...n, nags: toggleNagList(n.nags, nag) }));
}

/** Remove o nó e toda a subárvore dele. */
export function deleteFrom(tree: Tree, id: string | null): Tree {
  if (!id) return tree;
  const children = mapNode(tree.root.children, id, () => null);
  return children ? withChildren(tree, children) : tree;
}

/**
 * Promove a linha do nó: ele passa a ser o primeiro entre os irmãos e o mesmo
 * vale para cada ancestral, de modo que o caminho inteiro vira linha principal.
 */
export function promote(tree: Tree, id: string | null): Tree {
  if (!id) return tree;
  const lift = (nodes: TreeNode[], i: number): TreeNode[] => {
    if (i === 0) return nodes;
    const copy = nodes.slice();
    const [n] = copy.splice(i, 1);
    copy.unshift(n);
    return copy;
  };
  const walk = (nodes: TreeNode[]): TreeNode[] | null => {
    const at = nodes.findIndex((n) => n.id === id);
    if (at >= 0) return lift(nodes.slice(), at);
    for (let i = 0; i < nodes.length; i++) {
      const sub = walk(nodes[i].children);
      if (sub) {
        const copy = nodes.slice();
        copy[i] = { ...nodes[i], children: sub };
        return lift(copy, i);
      }
    }
    return null;
  };
  const children = walk(tree.root.children);
  return children ? withChildren(tree, children) : tree;
}

export interface AddMoveResult {
  tree: Tree;
  /** O nó alcançado, novo ou já existente; `null` se o lance for ilegal ou a árvore estiver cheia. */
  node: TreeNode | null;
  /** `true` só quando um nó novo foi criado. */
  created: boolean;
}

/**
 * Joga `uci` a partir de `parentId` (ou da posição inicial, com `null`).
 * Se já existir um filho com esse lance, apenas o devolve — sem mudar a árvore.
 */
export function addMove(tree: Tree, parentId: string | null, uci: string): AddMoveResult {
  const nada: AddMoveResult = { tree, node: null, created: false };
  const parent = parentId ? findNode(tree, parentId) : null;
  if (parentId && !parent) return nada;

  const chess = new Chess(fenAt(tree, parentId));
  let san: string;
  let canon: string;
  try {
    const mv = chess.move(uciToMove(uci));
    san = mv.san;
    canon = `${mv.from}${mv.to}${mv.promotion ?? ""}`;
  } catch {
    return nada;
  }

  const siblings = parent ? parent.children : tree.root.children;
  const existing = siblings.find((n) => n.uci === canon);
  if (existing) return { tree, node: existing, created: false };
  if (countNodes(tree) >= MAX_NODES) return nada;

  const node: TreeNode = { id: nextId(tree), uci: canon, san, comment: "", shapes: [], nags: [], children: [] };
  const next = parent
    ? patch(tree, parentId, (n) => ({ ...n, children: [...n.children, node] }))
    : withChildren(tree, [...tree.root.children, node]);
  return { tree: next, node, created: true };
}

export interface InsertLineResult {
  tree: Tree;
  /** Último nó alcançado (o próprio `parentId` se nenhum lance passou). */
  lastId: string | null;
  /** Quantos nós novos entraram na árvore. */
  inserted: number;
  /** Quantos lances foram percorridos, criados ou já existentes. */
  applied: number;
}

/**
 * Entra com uma sequência de lances a partir de `parentId`, seguindo os filhos
 * que já existem e criando os que faltam. Para no primeiro lance ilegal.
 */
export function insertLine(tree: Tree, parentId: string | null, ucis: string[]): InsertLineResult {
  let out = tree;
  let lastId = parentId;
  let inserted = 0;
  let applied = 0;
  for (const uci of ucis) {
    const r = addMove(out, lastId, uci);
    if (!r.node) break;
    out = r.tree;
    lastId = r.node.id;
    applied++;
    if (r.created) inserted++;
  }
  return { tree: out, lastId, inserted, applied };
}
