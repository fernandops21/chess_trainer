import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { novoChess } from "../lib/chess";
import type { Key } from "chessground/types";
import { useAnalyse, useSettings } from "../api/queries";
import type { Shape } from "../api/types";
import { Board } from "../board/Board";
import { ErrorBox } from "../components/ErrorBox";
import { EvalBar } from "./EvalBar";
import { PreviaContext } from "./previaContext";
import { formatEval } from "../lib/format";
import { ClassIcon } from "./classIcons";
import { MoveTreeView } from "./MoveTreeView";
import { TextoComLances } from "./TextoComLances";
import { segmentar } from "./moveText";
import type { LanceDaLinha } from "./moveText";
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
  /** Cartões do dono do tabuleiro, no topo da coluna da direita (o resultado do
   *  exercício, por exemplo), acima do painel do motor e da lista de lances. */
  sidePanel?: ReactNode;
  /** `"livro"`: cada lance é uma página — à direita só o comentário do lance atual, a lista fica sob o tabuleiro. */
  layout?: "analise" | "livro";
  /** Avisa o dono a cada troca do lance atual (para links que voltam ao mesmo lance). */
  onCurrentChange?: (id: string | null) => void;
}

/** Abas do painel lateral: o motor ou o livro de aberturas. */
type Aba = "engine" | "aberturas";
/** Limites do tamanho da letra da página do livro, em rem. */
const LETRA_MIN = 0.8;
const LETRA_MAX = 1.6;

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
  sidePanel,
  layout = "analise",
  onCurrentChange,
}: AnalysisBoardProps) {
  const livro = layout === "livro";
  const mt = useMoveTree(tree, initialNodeId);
  const avisarAtual = useRef(onCurrentChange);
  avisarAtual.current = onCurrentChange;
  useEffect(() => { avisarAtual.current?.(mt.currentId); }, [mt.currentId]);
  // o motor desligado só custa um botão: quem quiser a análise liga na hora
  const [motor, setMotor] = useState(engine);
  const [orient, setOrient] = useState(tree.orientation);
  const [menu, setMenu] = useState<{ id: string; x: number; y: number } | null>(null);
  const [salvarComo, setSalvarComo] = useState(false);
  const [montando, setMontando] = useState(false);
  // Prévia: a linha lida de um comentário, mostrada no tabuleiro sem entrar na
  // árvore. Enquanto ela está na tela o tabuleiro é só de leitura.
  const [previa, setPrevia] = useState<LanceDaLinha[] | null>(null);
  const naPrevia = previa && previa.length > 0 ? previa[previa.length - 1] : null;
  // tamanho da letra da página do livro (rem), guardado no navegador
  const [letra, setLetra] = useState<number>(() => {
    const v = Number(storage.get<number>("livro.letra", 1));
    return Number.isFinite(v) ? Math.min(LETRA_MAX, Math.max(LETRA_MIN, v)) : 1;
  });
  const mudarLetra = (delta: number) => setLetra((atual) => {
    const novo = Math.round(Math.min(LETRA_MAX, Math.max(LETRA_MIN, atual + delta)) * 10) / 10;
    storage.set("livro.letra", novo);
    return novo;
  });
  const [aba, setAba] = useState<Aba>(() =>
    storage.get<Aba>("analysis.sidePanel", "engine") === "aberturas" ? "aberturas" : "engine",
  );
  // com a prévia na tela a análise é a da posição dela
  const fenNaTela = naPrevia ? naPrevia.fen : mt.fen;
  const turnNaTela: "white" | "black" = naPrevia ? (fenNaTela.split(" ")[1] === "b" ? "black" : "white") : mt.turn;
  const { data, error, isFetching } = useAnalyse(motor ? fenNaTela : null);
  const { data: settings } = useSettings();
  // símbolo do livro nos lances do caminho atual que estão na base de mestres
  // sem engine (resultado do exercício) o livro também espera o usuário pedir análise
  // (a prévia não mexe no caminho: os símbolos da árvore não somem por causa dela)
  const bookIds = useBookMoves(mt.tree, motor ? mt.path : []);
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
      !naPrevia && mt.node && classeAtual
        ? { square: mt.node.uci.slice(2, 4) as Key, text: classeAtual.symbol, className: `class-${classeAtual.kind}`, icon: <ClassIcon kind={classeAtual.kind} size="100%" /> }
        : undefined,
    [naPrevia, mt.node, classeAtual],
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
        // outra análise na tela: a prévia da anterior não tem mais onde morar
        setPrevia(null);
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
      setPrevia(null);
      fn();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [prev, next, up, down, goStart, onSave, montando]);

  const inCheck = useMemo(() => { try { return novoChess(fenNaTela).inCheck(); } catch { return false; } }, [fenNaTela]);
  const best = data && !data.terminal ? data.lines[0] : undefined;
  // A barra de avaliação guarda a última leitura: enquanto a engine calcula a
  // posição nova a consulta ainda não respondeu, e voltar ao meio pareceria
  // que a vantagem sumiu.
  const ultimaBarra = useRef<{ score: number | null; turn: "white" | "black"; terminal: string | null }>({ score: null, turn: "white", terminal: null });
  if (data) ultimaBarra.current = { score: best?.score ?? null, turn: data.turn as "white" | "black", terminal: data.terminal };
  const barra = data ? { score: best?.score ?? null, turn: turnNaTela, terminal: data.terminal } : ultimaBarra.current;

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

  /** Navegar, jogar ou entrar com uma linha desfaz a prévia. */
  const semPrevia = useCallback(<A extends unknown[]>(fn: (...args: A) => unknown) => (...args: A) => {
    setPrevia(null);
    return fn(...args);
  }, []);

  // O texto do comentário quebrado em prosa e lances, uma vez só: no editor ele
  // serve tanto para saber se há lance quanto para a fila de botões embaixo da
  // caixa (segmentar de novo ali custaria uma segunda leitura por tecla).
  const segsComentario = useMemo(
    () => (comentario === "" ? [] : segmentar(comentario, mt.fen)),
    [comentario, mt.fen],
  );
  const temLance = segsComentario.some((seg) => seg.kind === "lance");

  const trocarAba = (nova: Aba) => {
    setAba(nova);
    storage.set("analysis.sidePanel", nova);
  };

  const onMove = (orig: Key, dest: Key) => {
    setPrevia(null);
    if (!mt.play(`${orig}${dest}`)) mt.play(`${orig}${dest}q`);
  };

  /**
   * A posição montada vira o começo de uma análise nova: a árvore inteira é
   * trocada, então uma análise com lances pede confirmação antes.
   */
  const usarPosicao = (fen: string) => {
    if (countNodes(mt.tree) > 0 && !window.confirm("Substituir a análise atual pela nova posição?")) return;
    mt.setTree(emptyTree(fen, orient));
    setPrevia(null);
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
    // com painel ao lado (resultado do exercício), o tabuleiro fica preso no topo
    // enquanto o texto da direita rola: ler a explicação não pode tirar a posição da tela
    <div className={`two-col${sidePanel ? " tabuleiro-fixo" : ""}`}>
      <div>
        {previa && (
          <div className="previa row">
            <span>prévia: {previa.map((l) => l.san).join(" ")} · </span>
            <button onClick={() => setPrevia(null)}>voltar</button>
            {editable && (
              <button onClick={() => { mt.insertLine(previa.map((l) => l.uci)); setPrevia(null); }}>
                adicionar como variação
              </button>
            )}
          </div>
        )}
        <div className="board-row">
        {motor && <EvalBar score={barra.score} turn={barra.turn} orientation={orient} terminal={barra.terminal} />}
        <Board
          fen={fenNaTela}
          orientation={orient}
          turnColor={turnNaTela}
          movableColor={naPrevia ? undefined : mt.turn}
          dests={naPrevia ? undefined : mt.dests}
          lastMove={naPrevia ? naPrevia.lastMove : mt.lastMove}
          check={inCheck}
          arrows={arrows}
          squares={squares}
          drawable
          shapes={editable ? marcacoes : undefined}
          badge={badge}
          onShapesChange={editable ? mt.setShapes : undefined}
          onMove={onMove}
        />
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <button onClick={semPrevia(goStart)} disabled={mt.currentId === null && !previa} aria-label="posição inicial">⏮</button>
          <button onClick={semPrevia(prev)} disabled={mt.currentId === null && !previa} aria-label="lance anterior">◀</button>
          <button onClick={semPrevia(next)} aria-label="próximo lance">▶</button>
          <button onClick={() => setOrient((o) => (o === "white" ? "black" : "white"))}>Inverter</button>
          {allowSetup && <button onClick={() => setMontando(true)}>Montar posição</button>}
          {onSave && <button className="primary" onClick={onSave}>Salvar</button>}
          {showSaveAsChapter && <button onClick={() => setSalvarComo(true)}>Salvar como capítulo</button>}
          {backTo && <Link to={backTo}>Voltar</Link>}
        </div>
        {livro ? (
          // no modo livro a lista de lances fica sob o tabuleiro, compacta e sem
          // os comentários: eles são a "página" da coluna da direita
          <div className="movelist" style={{ marginTop: 12 }}>
            <MoveTreeView
              tree={mt.tree}
              currentId={mt.currentId}
              onGoTo={semPrevia(mt.goTo)}
              bookIds={bookIds}
              classes={classes}
              semComentarios
              onContextMenu={editable ? (id, pos) => setMenu({ id, ...pos }) : undefined}
            />
          </div>
        ) : editable ? (
          <div className="card" style={{ marginTop: 12 }}>
            <div className="muted">{tituloComentario}</div>
            <textarea
              aria-label="Comentário"
              style={{ width: "100%", minHeight: 70 }}
              value={comentario}
              onChange={(e) => mt.setComment(e.target.value)}
            />
            {temLance && (
              <div className="muted">
                Lances do comentário: <TextoComLances texto={comentario} fen={mt.fen} segmentos={segsComentario} onPrevia={setPrevia} apenasLances />
              </div>
            )}
            <div className="muted">Botão direito no tabuleiro desenha setas e casas: elas ficam salvas neste lance.</div>
          </div>
        ) : (
          // leitura: o texto do autor por inteiro (na árvore ele sai cortado)
          comentario !== "" && (
            <div className="card" style={{ marginTop: 12 }}>
              <div className="muted">{tituloComentario}</div>
              <div style={{ whiteSpace: "pre-wrap" }}>
                <TextoComLances texto={comentario} fen={mt.fen} segmentos={segsComentario} onPrevia={setPrevia} />
              </div>
            </div>
          )
        )}
      </div>
      <div>
        {/* `painel-lateral` é só gancho de teste e de estilo futuro — sem CSS hoje, e nada de `max-height`: rolagem aqui cortaria o botão "Próximo" */}
        {sidePanel && <PreviaContext.Provider value={setPrevia}><div className="painel-lateral">{sidePanel}</div></PreviaContext.Provider>}
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
          <OpeningsPanel fen={fenNaTela} onPlay={semPrevia((uci: string) => mt.play(uci))} />
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
          {classeAtual && !naPrevia && (
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
                  <button className="pvline" style={{ flex: "1 1 200px" }} onClick={semPrevia(() => mt.play(line.move))}>
                    {formatEval(data.turn === "black" ? -line.score : line.score)} {line.pv_san.join(" ")}
                  </button>
                  <button onClick={semPrevia(() => mt.insertLine(line.pv))}>adicionar como variação</button>
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
          {livro ? (
            // a página do lance atual: o comentário do autor inteiro, em fonte de
            // leitura; sem lance escolhido, o enunciado do capítulo
            <div className="livro-pagina" style={{ fontSize: `${letra}rem` }}>
              <div className="muted row" style={{ justifyContent: "space-between" }}>
                <span>{mt.node ? mt.node.san : "Início"}</span>
                <span className="livro-letra">
                  <button type="button" aria-label="Diminuir a letra" title="Diminuir a letra" onClick={() => mudarLetra(-0.1)} disabled={letra <= LETRA_MIN}>A−</button>
                  <button type="button" aria-label="Aumentar a letra" title="Aumentar a letra" onClick={() => mudarLetra(0.1)} disabled={letra >= LETRA_MAX}>A+</button>
                </span>
              </div>
              {editable ? (
                // no editor a página é a caixa do comentário do lance atual
                <>
                  <textarea
                    aria-label="Comentário"
                    style={{ width: "100%", minHeight: 160, font: "inherit", lineHeight: "inherit" }}
                    value={comentario}
                    onChange={(e) => mt.setComment(e.target.value)}
                    placeholder={mt.node ? `Comentário de ${mt.node.san}` : "Enunciado do capítulo"}
                  />
                  {temLance && (
                    <div className="muted" style={{ fontSize: ".85rem" }}>
                      Lances do comentário: <TextoComLances texto={comentario} fen={mt.fen} segmentos={segsComentario} onPrevia={setPrevia} apenasLances />
                    </div>
                  )}
                  <div className="muted" style={{ fontSize: ".85rem" }}>Botão direito no tabuleiro desenha setas e casas; na lista, abre o menu do lance.</div>
                </>
              ) : comentario !== "" ? (
                <TextoComLances texto={comentario} fen={mt.fen} segmentos={segsComentario} onPrevia={setPrevia} />
              ) : (
                <div className="muted">Sem comentário neste lance.</div>
              )}
            </div>
          ) : (
            <MoveTreeView
              tree={mt.tree}
              currentId={mt.currentId}
              onGoTo={semPrevia(mt.goTo)}
              bookIds={bookIds}
              classes={classes}
              onContextMenu={editable ? (id, pos) => setMenu({ id, ...pos }) : undefined}
            />
          )}
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
