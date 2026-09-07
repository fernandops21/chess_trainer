import { Fragment, useRef, type ReactNode } from "react";
import { nagLabel } from "./moveTree";
import type { Tree, TreeNode } from "./moveTree";

export interface MenuPos {
  x: number;
  y: number;
}

export interface MoveTreeViewProps {
  tree: Tree;
  currentId: string | null;
  onGoTo: (id: string) => void;
  /** Botão direito (ou toque longo) num lance: abre o menu do nó. */
  onContextMenu?: (id: string, pos: MenuPos) => void;
  /** Nós que aparecem no livro de aberturas: ganham o símbolo do livro. */
  bookIds?: Set<string>;
}

/** Símbolo do lance que está no livro de aberturas. */
const BOOK_TITLE = "lance de livro (base de mestres)";

/** Comentário na árvore é só um resumo; a caixa embaixo do tabuleiro traz ele inteiro. */
const COMMENT_MAX = 80;
/** Recuo das variações, em pixels por nível, até um teto (senão some da tela). */
const INDENT_PX = 10;
const MAX_DEPTH = 6;
/** Quanto o dedo fica parado num lance até abrir o menu do nó. */
const LONG_PRESS_MS = 450;

function shortComment(text: string): string {
  return text.length > COMMENT_MAX ? `${text.slice(0, COMMENT_MAX)}…` : text;
}

/** De onde a numeração parte: a FEN inicial diz de quem é a vez e qual é o lance. */
interface Numbering {
  /** 1 quando a posição inicial é das pretas: o primeiro lance é meio lance. */
  offset: number;
  first: number;
}

function numbering(fen: string): Numbering {
  const parts = fen.split(" ");
  const first = Number(parts[5]);
  return { offset: parts[1] === "b" ? 1 : 0, first: Number.isFinite(first) && first > 0 ? first : 1 };
}

/** `1. ` nos lances das brancas; nos das pretas, `1... ` só no começo de uma linha. */
function movePrefix(n: Numbering, ply: number, force: boolean): string {
  const abs = ply + n.offset;
  const num = n.first + Math.floor(abs / 2);
  if (abs % 2 === 0) return `${num}. `;
  return force ? `${num}... ` : "";
}

interface MoveProps {
  node: TreeNode;
  prefix: string;
  current: boolean;
  book: boolean;
  onGoTo: (id: string) => void;
  onContextMenu?: (id: string, pos: MenuPos) => void;
}

function Move({ node, prefix, current, book, onGoTo, onContextMenu }: MoveProps) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const held = useRef(false);

  const clear = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };

  return (
    <button
      type="button"
      className={current ? "move cur" : "move"}
      aria-current={current ? "true" : undefined}
      onClick={() => {
        // o toque longo já abriu o menu: o clique que vem depois dele não navega
        if (held.current) { held.current = false; return; }
        onGoTo(node.id);
      }}
      onContextMenu={(e) => {
        if (!onContextMenu) return;
        e.preventDefault();
        onContextMenu(node.id, { x: e.clientX, y: e.clientY });
      }}
      onTouchStart={(e) => {
        held.current = false;
        if (!onContextMenu) return;
        const t = e.touches[0];
        if (!t) return;
        const pos = { x: t.clientX, y: t.clientY };
        clear();
        timer.current = setTimeout(() => {
          held.current = true;
          onContextMenu(node.id, pos);
        }, LONG_PRESS_MS);
      }}
      onTouchMove={clear}
      onTouchEnd={clear}
      onTouchCancel={clear}
    >
      {prefix}
      {node.san}
      {node.nags.map(nagLabel).join("")}
      {book && <span className="book" role="img" title={BOOK_TITLE} aria-label={BOOK_TITLE}>📖</span>}
    </button>
  );
}

interface Ctx {
  num: Numbering;
  currentId: string | null;
  bookIds?: Set<string>;
  onGoTo: (id: string) => void;
  onContextMenu?: (id: string, pos: MenuPos) => void;
}

/**
 * Desenha uma linha: o primeiro filho de cada nível segue corrido e cada irmão
 * dele abre uma variação recuada entre parênteses, recursivamente.
 */
function renderLine(nodes: TreeNode[], ply: number, depth: number, ctx: Ctx): ReactNode[] {
  const out: ReactNode[] = [];
  let level = nodes;
  let p = ply;
  // o primeiro lance de uma linha sempre leva o número, mesmo sendo das pretas
  let force = true;
  while (level.length > 0) {
    const main = level[0];
    const variations = level.slice(1);
    out.push(
      <Fragment key={main.id}>
        <Move
          node={main}
          prefix={movePrefix(ctx.num, p, force)}
          current={main.id === ctx.currentId}
          book={ctx.bookIds?.has(main.id) ?? false}
          onGoTo={ctx.onGoTo}
          onContextMenu={ctx.onContextMenu}
        />
        {main.comment !== "" && <span className="comment">{shortComment(main.comment)}</span>}{" "}
      </Fragment>,
    );
    for (const v of variations) {
      out.push(
        <div
          key={`var-${v.id}`}
          className="variation"
          style={{ marginLeft: INDENT_PX * Math.min(depth + 1, MAX_DEPTH) }}
        >
          ({renderLine([v], p, depth + 1, ctx)})
        </div>,
      );
    }
    // depois de uma variação a linha principal recomeça: o número volta a aparecer
    force = variations.length > 0;
    p++;
    level = main.children;
  }
  return out;
}

/** Árvore no formato do Lichess: linha principal corrida, variações recuadas. */
export function MoveTreeView({ tree, currentId, onGoTo, onContextMenu, bookIds }: MoveTreeViewProps) {
  const ctx: Ctx = { num: numbering(tree.fen), currentId, bookIds, onGoTo, onContextMenu };
  if (tree.root.children.length === 0) {
    return <div className="tree muted">Nenhum lance ainda: jogue no tabuleiro para começar a linha.</div>;
  }
  return <div className="tree">{renderLine(tree.root.children, 0, 0, ctx)}</div>;
}
