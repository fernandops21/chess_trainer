import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Chess } from "chess.js";
import type { Key } from "chessground/types";
import { useAnalyse } from "../api/queries";
import type { Shape } from "../api/types";
import { Board } from "../board/Board";
import { ErrorBox } from "../components/ErrorBox";
import { formatEval } from "../lib/format";
import { MoveTreeView } from "./MoveTreeView";
import { NodeMenu } from "./NodeMenu";
import { SaveChapterModal } from "./SaveChapterModal";
import { useMoveTree } from "./useMoveTree";
import type { Tree } from "./moveTree";

export interface AnalysisBoardProps {
  tree: Tree;
  /** Liga comentários, NAGs, marcações salvas e o menu do nó. */
  editable?: boolean;
  /** Recebe a árvore nova a cada mudança (o pai guarda e salva). */
  onTreeChange?: (tree: Tree) => void;
  /** Botão "Salvar" e Ctrl+S. */
  onSave?: () => void;
  backTo?: string;
  showSaveAsChapter?: boolean;
}

/** Lista fixa: sem ela, um `[]` novo a cada render repõe as marcações do tabuleiro à toa. */
const SEM_MARCACOES: Shape[] = [];

function terminalLabel(terminal: string): string {
  if (terminal === "checkmate") return "Xeque-mate";
  if (terminal === "stalemate") return "Afogamento";
  return "Empate";
}

/**
 * Tabuleiro de análise completo: árvore de variações, comentários, marcações
 * salvas e o motor ao lado. É o mesmo componente do editor de capítulo — o que
 * muda é o `editable` e quem cuida de salvar.
 */
export function AnalysisBoard({
  tree,
  editable = false,
  onTreeChange,
  onSave,
  backTo,
  showSaveAsChapter = false,
}: AnalysisBoardProps) {
  const mt = useMoveTree(tree);
  const [orient, setOrient] = useState(tree.orientation);
  const [menu, setMenu] = useState<{ id: string; x: number; y: number } | null>(null);
  const [salvarComo, setSalvarComo] = useState(false);
  const { data, error, isFetching } = useAnalyse(mt.fen);

  // Vaivém com o pai: a árvore que chega de fora reinicia o hook e a que nasce
  // aqui sobe pelo `onTreeChange`. Um pai que guarda o que recebe devolve a
  // mesma árvore no próximo render — esse eco não pode reiniciar a navegação,
  // daí guardar tanto o último `tree` do pai quanto a última que mandamos.
  const doPai = useRef(tree);
  const enviada = useRef(tree);
  const { setTree } = mt;
  useEffect(() => {
    if (tree !== doPai.current) {
      doPai.current = tree;
      if (tree !== enviada.current) {
        enviada.current = tree;
        setTree(tree);
        setOrient(tree.orientation);
        return;
      }
    }
    if (mt.tree !== enviada.current) {
      enviada.current = mt.tree;
      onTreeChange?.(mt.tree);
    }
  }, [tree, mt.tree, setTree, onTreeChange]);

  const { prev, next, up, down, goStart } = mt;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) {
        if (!onSave) return;
        e.preventDefault();
        onSave();
        return;
      }
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      // digitando no comentário, as setas andam no texto e não na árvore
      const alvo = e.target as HTMLElement | null;
      const tag = alvo?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || alvo?.isContentEditable) return;
      const acoes: Record<string, (() => void) | undefined> = {
        ArrowLeft: prev, ArrowRight: next, ArrowUp: up, ArrowDown: down, Home: goStart,
      };
      const fn = acoes[e.key];
      if (!fn) return;
      e.preventDefault();
      fn();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [prev, next, up, down, goStart, onSave]);

  const inCheck = useMemo(() => new Chess(mt.fen).inCheck(), [mt.fen]);
  const best = data && !data.terminal ? data.lines[0] : undefined;

  // marcações salvas do nó atual (as da posição inicial ficam na raiz)
  const raizShapes = mt.tree.root.shapes;
  const marcacoes = useMemo(
    () => (mt.currentId ? mt.node?.shapes : raizShapes) ?? SEM_MARCACOES,
    [mt.currentId, mt.node, raizShapes],
  );

  // fora do modo edição as marcações do autor são só enfeite (`autoShapes`);
  // no modo edição elas viram as marcações do usuário, que ele pode apagar
  const arrows = useMemo(() => {
    const out: { orig: Key; dest: Key; brush?: string }[] = [];
    if (best) out.push({ orig: best.move.slice(0, 2) as Key, dest: best.move.slice(2, 4) as Key, brush: "green" });
    if (!editable) {
      for (const s of marcacoes) if (s.dest) out.push({ orig: s.orig as Key, dest: s.dest as Key, brush: s.brush });
    }
    return out;
  }, [best, editable, marcacoes]);
  const squares = useMemo(
    () => (editable ? [] : marcacoes.filter((s) => !s.dest).map((s) => ({ orig: s.orig as Key, brush: s.brush }))),
    [editable, marcacoes],
  );

  const onMove = (orig: Key, dest: Key) => {
    if (!mt.play(`${orig}${dest}`)) mt.play(`${orig}${dest}q`);
  };

  return (
    <div className="two-col">
      <div>
        <Board
          fen={mt.fen}
          orientation={orient}
          turnColor={mt.turn}
          movableColor={mt.turn}
          dests={mt.dests}
          lastMove={mt.lastMove}
          check={inCheck}
          arrows={arrows}
          squares={squares}
          drawable
          shapes={editable ? marcacoes : undefined}
          onShapesChange={editable ? mt.setShapes : undefined}
          onMove={onMove}
        />
        <div className="row" style={{ marginTop: 8 }}>
          <button onClick={goStart} disabled={mt.currentId === null} aria-label="posição inicial">⏮</button>
          <button onClick={prev} disabled={mt.currentId === null} aria-label="lance anterior">◀</button>
          <button onClick={next} aria-label="próximo lance">▶</button>
          <button onClick={() => setOrient((o) => (o === "white" ? "black" : "white"))}>Inverter</button>
          {onSave && <button className="primary" onClick={onSave}>Salvar</button>}
          {showSaveAsChapter && <button onClick={() => setSalvarComo(true)}>Salvar como capítulo</button>}
          {backTo && <Link to={backTo}>Voltar</Link>}
        </div>
        {editable && (
          <div className="card" style={{ marginTop: 12 }}>
            <div className="muted">
              {mt.node ? `Comentário de ${mt.node.san}` : "Enunciado (posição inicial)"}
            </div>
            <textarea
              aria-label="Comentário"
              style={{ width: "100%", minHeight: 70 }}
              value={mt.node ? mt.node.comment : mt.tree.intro}
              onChange={(e) => mt.setComment(e.target.value)}
            />
            <div className="muted">Botão direito no tabuleiro desenha setas e casas: elas ficam salvas neste lance.</div>
          </div>
        )}
      </div>
      <div>
        <div className="card">
          {data?.terminal ? (
            <div className="eval-big">{terminalLabel(data.terminal)}</div>
          ) : (
            <>
              <div className="eval-big">{best ? formatEval(data && data.turn === "black" ? -best.score : best.score) : "…"}</div>
              <div className="muted">avaliação (ponto de vista das brancas)</div>
            </>
          )}
          {isFetching && <div className="muted">analisando…</div>}
          <ErrorBox error={error} />
          {data && !data.terminal && (
            <div style={{ marginTop: 10 }}>
              {data.lines.map((line, i) => (
                <div className="row" key={i}>
                  <button className="pvline" style={{ flex: "1 1 200px" }} onClick={() => mt.play(line.move)}>
                    {formatEval(data.turn === "black" ? -line.score : line.score)} {line.pv_san.join(" ")}
                  </button>
                  <button onClick={() => mt.insertLine(line.pv)}>adicionar como variação</button>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="card">
          <MoveTreeView
            tree={mt.tree}
            currentId={mt.currentId}
            onGoTo={mt.goTo}
            onContextMenu={editable ? (id, pos) => setMenu({ id, ...pos }) : undefined}
          />
        </div>
      </div>
      {menu && (
        <NodeMenu
          x={menu.x}
          y={menu.y}
          onPromote={() => mt.promote(menu.id)}
          onDelete={() => mt.deleteFrom(menu.id)}
          onNag={(n) => { mt.goTo(menu.id); mt.toggleNag(n); }}
          onClose={() => setMenu(null)}
        />
      )}
      {salvarComo && <SaveChapterModal tree={mt.tree} onClose={() => setSalvarComo(false)} />}
    </div>
  );
}
