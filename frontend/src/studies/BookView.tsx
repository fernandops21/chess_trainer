import { Fragment, useEffect, useMemo, useRef, type ReactNode } from "react";
import { ClassIcon } from "../analysis/classIcons";
import type { Classification } from "../analysis/classify";
import { nagLabel } from "../analysis/moveTree";
import type { Tree, TreeNode } from "../analysis/moveTree";
import { TextoComLances } from "../analysis/TextoComLances";
import type { LanceDaLinha } from "../analysis/moveText";
import { uciToMove } from "../board/line";
import { novoChess } from "../lib/chess";

export interface BookViewProps {
  tree: Tree;
  currentId: string | null;
  /** Clicar num lance em negrito navega até ele. */
  onGoTo: (id: string) => void;
  /** Classificação de cada lance do caminho atual (`useMoveClassification`). */
  classes?: ReadonlyMap<string, Classification>;
  /** Nós que aparecem no livro de aberturas: ganham o símbolo do livro. */
  bookIds?: Set<string>;
  /** Prévia da linha lida de dentro de um comentário (os lances do texto). */
  onPrevia?: (linha: LanceDaLinha[]) => void;
}

/** Símbolo do lance que está no livro de aberturas (o mesmo da lista). */
const BOOK_TITLE = "lance de livro (base de mestres)";

/** De onde a numeração parte: a FEN inicial diz de quem é a vez e qual é o lance. */
interface Numeracao {
  /** 1 quando a posição inicial é das pretas: o primeiro lance é meio lance. */
  offset: number;
  primeiro: number;
}

function numeracao(fen: string): Numeracao {
  const partes = fen.split(" ");
  const primeiro = Number(partes[5]);
  return {
    offset: partes[1] === "b" ? 1 : 0,
    primeiro: Number.isFinite(primeiro) && primeiro > 0 ? primeiro : 1,
  };
}

/**
 * `3. ` nos lances das brancas; nos das pretas, `3...` só quando o lance abre
 * um parágrafo (é assim que o livro impresso retoma a linha depois da prosa).
 */
function prefixoLance(n: Numeracao, ply: number, forcar: boolean): string {
  const abs = ply + n.offset;
  const numero = n.primeiro + Math.floor(abs / 2);
  if (abs % 2 === 0) return `${numero}. `;
  return forcar ? `${numero}...` : "";
}

interface Ctx {
  /** FEN de cada nó, prontas de um percurso só (ver `fensDaArvore`). */
  fens: ReadonlyMap<string, string>;
  /** FEN da raiz: reserva para o nó que ficou de fora do mapa. */
  fenRaiz: string;
  num: Numeracao;
  currentId: string | null;
  classes?: ReadonlyMap<string, Classification>;
  bookIds?: Set<string>;
  onGoTo: (id: string) => void;
  onPrevia: (linha: LanceDaLinha[]) => void;
}

interface LanceProps {
  node: TreeNode;
  prefixo: string;
  ctx: Ctx;
}

/** Um lance do texto: em negrito, clicável, com os selos colados nele. */
function Lance({ node, prefixo, ctx }: LanceProps) {
  const atual = node.id === ctx.currentId;
  const ref = useRef<HTMLButtonElement>(null);

  // andando pelos lances, o texto acompanha: o lance atual entra na parte
  // visível da rolagem (o jsdom não tem `scrollIntoView`, daí a guarda)
  useEffect(() => {
    const el = ref.current;
    if (!atual || !el || typeof el.scrollIntoView !== "function") return;
    el.scrollIntoView({ block: "nearest" });
  }, [atual]);

  const cls = ctx.classes?.get(node.id);
  const livro = ctx.bookIds?.has(node.id) ?? false;
  return (
    <button
      ref={ref}
      type="button"
      className={atual ? "livro-lance atual" : "livro-lance"}
      aria-current={atual ? "true" : undefined}
      onClick={() => ctx.onGoTo(node.id)}
    >
      {prefixo}
      {node.san}
      {node.nags.map(nagLabel).join("")}
      {livro ? (
        <span className="book" role="img" title={BOOK_TITLE} aria-label={BOOK_TITLE}><ClassIcon kind="livro" /></span>
      ) : (
        cls && <span className={`class class-${cls.kind}`} role="img" title={cls.label} aria-label={cls.label}><ClassIcon kind={cls.kind} /></span>
      )}
    </button>
  );
}

/** Um lance à espera de entrar na corrida, com o prefixo já decidido. */
interface NaCorrida {
  node: TreeNode;
  prefixo: string;
}

/**
 * Escreve uma linha como prosa: lances sem comentário se juntam numa corrida
 * ("5. O-O d6 6. d4 Bb6") e cada lance comentado abre um parágrafo próprio,
 * com o comentário inteiro. As variações vêm logo depois do parágrafo do lance
 * principal a que respondem, recuadas, pelas mesmas regras.
 */
function renderLinha(nodes: TreeNode[], ply: number, ctx: Ctx): ReactNode[] {
  const out: ReactNode[] = [];
  let corrida: NaCorrida[] = [];

  const fecharCorrida = () => {
    if (corrida.length === 0) return;
    const lances = corrida;
    corrida = [];
    out.push(
      <p className="livro-lances" key={`corrida-${lances[0].node.id}`}>
        {lances.map((l, i) => (
          <Fragment key={l.node.id}>
            {i > 0 ? " " : null}
            <Lance node={l.node} prefixo={l.prefixo} ctx={ctx} />
          </Fragment>
        ))}
      </p>,
    );
  };

  let nivel = nodes;
  let p = ply;
  while (nivel.length > 0) {
    const principal = nivel[0];
    const variacoes = nivel.slice(1);
    if (principal.comment !== "") {
      // o lance comentado fecha a corrida e vira parágrafo, sempre com o número
      fecharCorrida();
      out.push(
        <p className="livro-par" key={principal.id}>
          <Lance node={principal} prefixo={prefixoLance(ctx.num, p, true)} ctx={ctx} />{" "}
          <TextoComLances
            texto={principal.comment}
            fen={ctx.fens.get(principal.id) ?? ctx.fenRaiz}
            onPrevia={ctx.onPrevia}
          />
        </p>,
      );
    } else {
      // quem abre a corrida leva o número, mesmo sendo lance das pretas
      corrida.push({ node: principal, prefixo: prefixoLance(ctx.num, p, corrida.length === 0) });
    }
    if (variacoes.length > 0) {
      // as variações ficam logo abaixo do lance principal correspondente
      fecharCorrida();
      for (const v of variacoes) {
        out.push(
          <div className="livro-variacao" key={`var-${v.id}`}>
            {renderLinha([v], p, ctx)}
          </div>,
        );
      }
    }
    p++;
    nivel = principal.children;
  }
  fecharCorrida();
  return out;
}

/**
 * A FEN de cada nó da árvore, num percurso em pré-ordem só.
 *
 * Antes cada lance comentado chamava `fenAt`, que reconstrói a linha desde a
 * raiz: num capítulo de 60 lances comentados isso é quadrático e cada tecla
 * pesava décimos de segundo. Aqui um único tabuleiro desce pela árvore e
 * desfaz o lance na volta. O nó cujo lance é ilegal (árvore importada torta)
 * fica de fora do mapa, junto com a subárvore dele.
 */
function fensDaArvore(tree: Tree): Map<string, string> {
  const map = new Map<string, string>();
  let chess;
  try {
    chess = novoChess(tree.fen);
  } catch {
    return map;
  }
  const walk = (nodes: TreeNode[]) => {
    for (const n of nodes) {
      try {
        chess.move(uciToMove(n.uci));
      } catch {
        continue;
      }
      map.set(n.id, chess.fen());
      walk(n.children);
      chess.undo();
    }
  };
  walk(tree.root.children);
  return map;
}

/**
 * Modo livro: a árvore do capítulo lida como a página de um livro de xadrez —
 * o enunciado abrindo, os lances comentados em parágrafos e as variações
 * recuadas. Serve à leitura do capítulo; o editor e a Análise continuam com a
 * lista de lances (`MoveTreeView`), que é melhor para mexer na árvore.
 */
export function BookView({ tree, currentId, onGoTo, classes, bookIds, onPrevia }: BookViewProps) {
  const fens = useMemo(() => fensDaArvore(tree), [tree]);

  // os dois callbacks vão por referência para não entrarem nas dependências:
  // assim a página só é reescrita quando a árvore, o lance atual ou os selos
  // mudam — e não a cada render de quem chama
  const cbs = useRef({ onGoTo, onPrevia });
  cbs.current.onGoTo = onGoTo;
  cbs.current.onPrevia = onPrevia;

  const pagina = useMemo(() => {
    const ctx: Ctx = {
      fens,
      fenRaiz: tree.fen,
      num: numeracao(tree.fen),
      currentId,
      classes,
      bookIds,
      onGoTo: (id) => cbs.current.onGoTo(id),
      onPrevia: (linha) => cbs.current.onPrevia?.(linha),
    };
    const vazio = tree.root.children.length === 0;
    return (
      <>
        {tree.intro !== "" && (
          <p className="livro-par">
            <TextoComLances texto={tree.intro} fen={tree.fen} onPrevia={ctx.onPrevia} />
          </p>
        )}
        {vazio ? (
          tree.intro === "" && <p className="muted">Nenhum lance ainda: jogue no tabuleiro para começar a linha.</p>
        ) : (
          renderLinha(tree.root.children, 0, ctx)
        )}
      </>
    );
  }, [tree, fens, currentId, classes, bookIds]);

  return <div className="livro">{pagina}</div>;
}
