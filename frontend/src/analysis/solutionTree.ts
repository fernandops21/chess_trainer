import type { Color, Solution } from "../api/types";
import { mesmaPosicao } from "../board/line";
import {
  addMove,
  emptyTree,
  fenAt,
  insertLine,
  mainline,
  setComment,
  setShapes,
} from "./moveTree";
import type { Tree } from "./moveTree";

/** O que basta de um exercício para montar a árvore: puzzle próprio, tática ou capítulo. */
export interface SolutionSource {
  fen_start: string;
  side_to_move: Color;
  solution: Solution;
  /** Posição de antes do lance do adversário e o lance em si; ausentes na maioria das fontes. */
  fen_before?: string | null;
  last_move?: string | null;
}

/**
 * Nó cuja posição é a `fen_start` do exercício: a raiz, ou o lance do
 * adversário quando ele abre a árvore. É onde ficam as marcações de "start" e
 * de onde saem os lances do solucionador.
 */
export function startNodeId(tree: Tree, fenStart: string): string | null {
  if (mesmaPosicao(tree.fen, fenStart)) return null;
  const primeiro = mainline(tree)[0];
  return primeiro ? primeiro.id : null;
}

/**
 * Árvore de análise a partir da solução de um exercício.
 *
 * A linha principal é a solução, precedida do lance do adversário quando ele
 * existe (aí a raiz é a posição de antes dele). Os comentários e as marcações
 * do autor acompanham os lances — as de "start" ficam na posição do exercício
 * — e os lances errados previstos entram como variações do primeiro lance do
 * solucionador. Função pura: nada aqui depende de React nem da API.
 */
export function treeFromSolution(p: SolutionSource): Tree {
  const ucis = p.solution.moves.map((m) => m.uci);
  // com o lance do adversário a linha inteira anda um meio-lance para a frente
  let offset = p.fen_before && p.last_move ? 1 : 0;
  let tree = emptyTree(offset ? p.fen_before! : p.fen_start, p.side_to_move);
  let linha = offset ? [p.last_move!, ...ucis] : ucis;
  let r = insertLine(tree, null, linha);
  // Dado incoerente: o lance guardado não cabe na posição guardada, ou cabe mas
  // leva a outra posição que não a do exercício. Nos dois casos a árvore ficaria
  // fora da solução, então ela recomeça em `fen_start`, como nas fontes que não
  // guardam o lance anterior.
  if (offset && (r.applied === 0 || !mesmaPosicao(fenAt(r.tree, mainline(r.tree)[0]?.id ?? null), p.fen_start))) {
    offset = 0;
    tree = emptyTree(p.fen_start, p.side_to_move);
    linha = ucis;
    r = insertLine(tree, null, linha);
  }
  tree = r.tree;
  if (p.solution.intro) tree = { ...tree, intro: p.solution.intro };

  const nos = mainline(tree);
  const noDe = (i: number) => nos[i + offset];

  for (const [chave, texto] of Object.entries(p.solution.comments ?? {})) {
    const no = noDe(Number(chave));
    if (no && texto) tree = setComment(tree, no.id, texto);
  }

  for (const [chave, marcas] of Object.entries(p.solution.shapes ?? {})) {
    if (marcas.length === 0) continue;
    // "start" é a posição do exercício: a raiz, ou o nó do lance do adversário
    const id = chave === "start" ? (offset ? nos[0]?.id ?? null : null) : noDe(Number(chave))?.id;
    if (id !== undefined) tree = setShapes(tree, id, marcas);
  }

  // variações do autor no primeiro lance que o solucionador tem de achar
  const primeiroSolver = p.solution.moves.findIndex((m) => m.by === "solver");
  const pai = nos[(primeiroSolver < 0 ? 0 : primeiroSolver) + offset - 1];
  for (const [uci, texto] of Object.entries(p.solution.wrong_moves ?? {})) {
    const add = addMove(tree, pai ? pai.id : null, uci);
    if (!add.node || !add.created) continue;
    tree = texto ? setComment(add.tree, add.node.id, texto) : add.tree;
  }
  return tree;
}

/**
 * Enxerta o lance da partida como variação da posição do exercício, com a
 * continuação que o punia. Devolve a árvore recebida quando o lance não é
 * legal ali.
 */
export function withMistakeVariation(
  tree: Tree,
  fenStart: string,
  uci: string,
  comment: string,
  continuation: string[],
): Tree {
  const pai = startNodeId(tree, fenStart);
  const add = addMove(tree, pai, uci);
  if (!add.node) return tree;
  // o lance já podia estar lá (um "lance errado" do autor): o comentário dele fica
  const comComentario = add.node.comment ? add.tree : setComment(add.tree, add.node.id, comment);
  return insertLine(comComentario, add.node.id, continuation).tree;
}

/**
 * A linha que o usuário jogou de fato, quando ela sai da solução (uma
 * alternativa aceita). Entra como variação no ponto em que divergiu, com o
 * comentário, e devolve também o id do último lance dela para o tabuleiro
 * abrir ali — foi o que o usuário viu, não a linha principal.
 */
export function withPlayedLine(
  tree: Tree,
  solution: string[],
  played: string[],
  comment: string,
): { tree: Tree; lastId: string | null; divergiu: boolean } {
  const nos = mainline(tree);
  // com o lance de introdução do adversário a linha principal começa um nó adiante
  const offset = Math.max(0, nos.length - solution.length);
  let d = 0;
  while (d < played.length && d < solution.length && played[d] === solution[d]) d++;
  if (d >= played.length) return { tree, lastId: null, divergiu: false };
  const parentId = d === 0 ? (offset ? nos[offset - 1]?.id ?? null : null) : nos[d - 1 + offset]?.id ?? null;
  const r = insertLine(tree, parentId, played.slice(d));
  if (r.applied === 0 || !r.lastId) return { tree, lastId: null, divergiu: false };
  const noDivergente = played.slice(d)[0];
  const comComentario = setComment(r.tree, idDoFilho(r.tree, parentId, noDivergente) ?? r.lastId, comment);
  return { tree: comComentario, lastId: r.lastId, divergiu: true };
}

/** Id do filho de `parentId` que joga `uci` (a raiz quando `parentId` é null). */
function idDoFilho(tree: Tree, parentId: string | null, uci: string): string | null {
  const filhos = parentId === null ? tree.root.children : acharNo(tree.root.children, parentId)?.children ?? [];
  return filhos.find((n) => n.uci === uci)?.id ?? null;
}

function acharNo(nos: Tree["root"]["children"], id: string): Tree["root"]["children"][number] | null {
  for (const n of nos) {
    if (n.id === id) return n;
    const achado = acharNo(n.children, id);
    if (achado) return achado;
  }
  return null;
}
