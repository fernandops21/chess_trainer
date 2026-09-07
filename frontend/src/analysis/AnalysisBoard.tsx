import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Chess } from "chess.js";
import type { Key } from "chessground/types";
import { useAnalyse, useSettings } from "../api/queries";
import type { Shape } from "../api/types";
import { Board } from "../board/Board";
import { ErrorBox } from "../components/ErrorBox";
import { formatEval } from "../lib/format";
import { MoveTreeView } from "./MoveTreeView";
import { NodeMenu } from "./NodeMenu";
import { OpeningsPanel } from "./OpeningsPanel";
import { PositionEditor } from "./PositionEditor";
import { SaveChapterModal } from "./SaveChapterModal";
import { useBookMoves } from "./useBookMoves";
import { useMoveClassification } from "./useMoveClassification";
import { useMoveTree } from "./useMoveTree";
import { storage } from "../lib/storage";
import { MAX_NODES, countNodes, emptyTree } from "./moveTree";
import type { Tree } from "./moveTree";

export interface AnalysisBoardProps {
  tree: Tree;
  /** Liga comentários, NAGs, marcações salvas e o menu do nó. */
  editable?: boolean;
  /** Recebe a árvore nova a cada mudança (o pai guarda e salva). */
  onTreeChange?: (tree: Tree) => void;
  /** Botão "Salvar" e Ctrl+S. */
  onSave?: () => void;
  /** Hora do último salvamento do pai: ao mudar, o tabuleiro se dá por salvo. */
  savedAt?: number;
  backTo?: string;
  showSaveAsChapter?: boolean;
  /** Lance em que a navegação abre: `"last"` é o fim da linha principal. */
  initialNodeId?: string | "last";
  /** Motor ligado desde o começo (padrão). Desligado, um botão liga a análise. */
  engine?: boolean;
  /** Mostra o botão "Montar posição" (fora do resultado de exercício). */
  allowSetup?: boolean;
}

/** Abas do painel lateral: o motor ou o livro de aberturas. */
type Aba = "engine" | "aberturas";

/** Limiares de erro e blunder enquanto as configurações não chegam. */
const PADRAO_MISTAKE = 100;
const PADRAO_BLUNDER = 200;

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
 * muda é o `editable` e quem cuida de salvar. Sem `editable` o comentário do
 * lance (ou o enunciado, na posição inicial) aparece como cartão de leitura.
 */
export function AnalysisBoard({
  tree,
  editable = false,
  onTreeChange,
  onSave,
  savedAt,
  backTo,
  showSaveAsChapter = false,
  initialNodeId,
  engine = true,
  allowSetup = true,
}: AnalysisBoardProps) {
  const mt = useMoveTree(tree, initialNodeId);
  // o motor desligado só custa um botão: quem quiser a análise liga na hora
  const [motor, setMotor] = useState(engine);
  const [orient, setOrient] = useState(tree.orientation);
  const [menu, setMenu] = useState<{ id: string; x: number; y: number } | null>(null);
  const [salvarComo, setSalvarComo] = useState(false);
  const [montando, setMontando] = useState(false);
  const [aba, setAba] = useState<Aba>(() =>
    storage.get<Aba>("analysis.sidePanel", "engine") === "aberturas" ? "aberturas" : "engine",
  );
  const { data, error, isFetching } = useAnalyse(motor ? mt.fen : null);
  const { data: settings } = useSettings();
  // símbolo do livro nos lances do caminho atual que estão na base de mestres
  const bookIds = useBookMoves(mt.tree, mt.path);
  // classificação (melhor, erro, blunder…) de cada lance do caminho atual
  const classes = useMoveClassification(mt.tree, mt.path, {
    enabled: motor && (settings?.classify_moves ?? false),
    thresholds: {
      mistake: settings?.mistake_threshold_cp ?? PADRAO_MISTAKE,
      blunder: settings?.blunder_threshold_cp ?? PADRAO_BLUNDER,
    },
    bookIds,
  });
  const classeAtual = mt.node ? classes.get(mt.node.id) : undefined;
  // selo sobre a casa de destino do lance atual, como no chess.com
  const badge = useMemo(
    () =>
      mt.node && classeAtual
        ? { square: mt.node.uci.slice(2, 4) as Key, text: classeAtual.symbol, className: `class-${classeAtual.kind}` }
        : undefined,
    [mt.node, classeAtual],
  );

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

  // O pai salvou: nada muda na tela, só o `dirty` do hook volta a ficar limpo.
  const { markSaved } = mt;
  useEffect(() => {
    if (savedAt !== undefined) markSaved();
  }, [savedAt, markSaved]);

  const { prev, next, up, down, goStart } = mt;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // com o editor de posição aberto a árvore está escondida: nada de navegar nela
      if (montando) return;
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
  }, [prev, next, up, down, goStart, onSave, montando]);

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
    // no modo edição o verde é do usuário: a sugestão do motor sai de azul
    if (best) out.push({ orig: best.move.slice(0, 2) as Key, dest: best.move.slice(2, 4) as Key, brush: editable ? "blue" : "green" });
    if (!editable) {
      for (const s of marcacoes) if (s.dest) out.push({ orig: s.orig as Key, dest: s.dest as Key, brush: s.brush });
    }
    return out;
  }, [best, editable, marcacoes]);
  const squares = useMemo(
    () => (editable ? [] : marcacoes.filter((s) => !s.dest).map((s) => ({ orig: s.orig as Key, brush: s.brush }))),
    [editable, marcacoes],
  );

  // Comentário do lance atual; na posição inicial, o enunciado do capítulo.
  const comentario = mt.node ? mt.node.comment : mt.tree.intro;
  const tituloComentario = mt.node
    ? `Comentário de ${mt.node.san}`
    : editable
      ? "Enunciado (posição inicial)"
      : "Enunciado";

  const trocarAba = (nova: Aba) => {
    setAba(nova);
    storage.set("analysis.sidePanel", nova);
  };

  const onMove = (orig: Key, dest: Key) => {
    if (!mt.play(`${orig}${dest}`)) mt.play(`${orig}${dest}q`);
  };

  /**
   * A posição montada vira o começo de uma análise nova: a árvore inteira é
   * trocada, então uma análise com lances pede confirmação antes.
   */
  const usarPosicao = (fen: string) => {
    if (countNodes(mt.tree) > 0 && !window.confirm("Substituir a análise atual pela nova posição?")) return;
    mt.setTree(emptyTree(fen, orient));
    setMontando(false);
  };

  if (montando) {
    return (
      <PositionEditor
        initialFen={mt.fen}
        orientation={orient}
        onUse={usarPosicao}
        onCancel={() => setMontando(false)}
      />
    );
  }

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
          badge={badge}
          onShapesChange={editable ? mt.setShapes : undefined}
          onMove={onMove}
        />
        <div className="row" style={{ marginTop: 8 }}>
          <button onClick={goStart} disabled={mt.currentId === null} aria-label="posição inicial">⏮</button>
          <button onClick={prev} disabled={mt.currentId === null} aria-label="lance anterior">◀</button>
          <button onClick={next} aria-label="próximo lance">▶</button>
          <button onClick={() => setOrient((o) => (o === "white" ? "black" : "white"))}>Inverter</button>
          {allowSetup && <button onClick={() => setMontando(true)}>Montar posição</button>}
          {onSave && <button className="primary" onClick={onSave}>Salvar</button>}
          {showSaveAsChapter && <button onClick={() => setSalvarComo(true)}>Salvar como capítulo</button>}
          {backTo && <Link to={backTo}>Voltar</Link>}
        </div>
        {editable ? (
          <div className="card" style={{ marginTop: 12 }}>
            <div className="muted">{tituloComentario}</div>
            <textarea
              aria-label="Comentário"
              style={{ width: "100%", minHeight: 70 }}
              value={comentario}
              onChange={(e) => mt.setComment(e.target.value)}
            />
            <div className="muted">Botão direito no tabuleiro desenha setas e casas: elas ficam salvas neste lance.</div>
          </div>
        ) : (
          // leitura: o texto do autor por inteiro (na árvore ele sai cortado)
          comentario !== "" && (
            <div className="card" style={{ marginTop: 12 }}>
              <div className="muted">{tituloComentario}</div>
              <div style={{ whiteSpace: "pre-wrap" }}>{comentario}</div>
            </div>
          )
        )}
      </div>
      <div>
        {!motor ? (
          <div className="card">
            <button onClick={() => setMotor(true)}>Analisar com a engine</button>
          </div>
        ) : (
        <>
        <div className="tabs" role="tablist" aria-label="Painel de análise">
          <button role="tab" aria-selected={aba === "engine"} onClick={() => trocarAba("engine")}>Engine</button>
          <button role="tab" aria-selected={aba === "aberturas"} onClick={() => trocarAba("aberturas")}>Aberturas</button>
        </div>
        {aba === "aberturas" ? (
          <OpeningsPanel fen={mt.fen} onPlay={(uci) => mt.play(uci)} />
        ) : (
        <div className="card">
          {data?.terminal ? (
            <div className="eval-big">{terminalLabel(data.terminal)}</div>
          ) : (
            <>
              <div className="eval-big">{best ? formatEval(data && data.turn === "black" ? -best.score : best.score) : "…"}</div>
              <div className="muted">avaliação (ponto de vista das brancas)</div>
            </>
          )}
          {classeAtual && (
            <div className="muted">
              lance: <span className={`classe-nome class-${classeAtual.kind}`}>{classeAtual.label}</span>
              {classeAtual.loss !== null && ` (${formatEval(-classeAtual.loss)})`}
            </div>
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
        )}
        </>
        )}
        <div className="card">
          {/* cheia, a árvore não aceita lance novo: dizer isso aqui evita o
              tabuleiro que "não obedece" quando o lance simplesmente não entra */}
          {editable && mt.cheia && (
            <div className="msg">
              Limite de {MAX_NODES} lances por capítulo: apague alguma variação para entrar com outro lance.
            </div>
          )}
          <MoveTreeView
            tree={mt.tree}
            currentId={mt.currentId}
            onGoTo={mt.goTo}
            bookIds={bookIds}
            classes={classes}
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
