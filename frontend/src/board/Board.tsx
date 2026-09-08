import { useEffect, useRef } from "react";
import { Chessground } from "chessground";
import type { Api } from "chessground/api";
import type { Config } from "chessground/config";
import type { DrawShape } from "chessground/draw";
import type { Key } from "chessground/types";
import type { Shape } from "../api/types";
import "chessground/assets/chessground.base.css";
import "chessground/assets/chessground.brown.css";
import "chessground/assets/chessground.cburnett.css";

export interface BoardProps {
  fen: string;
  orientation: "white" | "black";
  turnColor?: "white" | "black";
  movableColor?: "white" | "black";
  dests?: Map<Key, Key[]>;
  lastMove?: [Key, Key];
  check?: boolean;
  /** Casas destacadas em verde (dica). */
  highlight?: Key[];
  arrows?: { orig: Key; dest: Key; brush?: string }[];
  /** Casas destacadas com cor própria (marcações do autor do estudo). */
  squares?: { orig: Key; brush?: string }[];
  onMove?: (orig: Key, dest: Key) => void;
  viewOnly?: boolean;
  coordinates?: boolean;
  /** Botão direito (ou toque longo no celular) desenha setas/casas. */
  drawable?: boolean;
  /** Marcações do usuário a mostrar no tabuleiro (o editor guarda as do nó atual). */
  shapes?: Shape[];
  /** Avisa quando o usuário desenha ou apaga uma marcação. Sem isto, o desenho é passageiro. */
  onShapesChange?: (shapes: Shape[]) => void;
  /** Modo montagem: peça solta, clique na casa e arrastar para fora apaga. */
  editor?: BoardEditor;
  /** Selo sobre uma casa (a classificação do lance atual, na Análise). */
  badge?: BoardBadge;
}

/** Selo desenhado por cima de uma casa: só enfeite, sem clique nem leitura de tela. */
export interface BoardBadge {
  square: Key;
  text: string;
  /** Classe do selo (`class-melhor`, `class-blunder`…): a cor vem do CSS. */
  className: string;
}

/**
 * Montagem de posição: o tabuleiro deixa de jogar xadrez e vira um editor —
 * qualquer peça vai para qualquer casa, arrastar para fora do tabuleiro apaga
 * e o clique é do pai (é ele quem sabe qual peça da paleta está escolhida).
 */
export interface BoardEditor {
  /** Clique numa casa (o chessground avisa antes de qualquer seleção). */
  onSquareClick: (key: Key) => void;
  /** Peças mudaram no tabuleiro; vem só a parte das peças da FEN. */
  onChange: (fen: string) => void;
  /** Uma peça da paleta está escolhida: o clique coloca, então arrastar fica desligado
   *  (o chessground avisa a seleção no início do arrasto e a origem seria sobrescrita). */
  placing?: boolean;
}

/** Lado da casa, em porcentagem do tabuleiro. */
const CASA_PCT = 12.5;

/**
 * Canto superior esquerdo de uma casa, em porcentagem do tabuleiro, conforme a
 * orientação. Com as brancas embaixo, a coluna `a` fica à esquerda e a fileira
 * 8 em cima; virado, é o contrário.
 *
 * `topo`/`direita` dizem se a casa está na primeira fileira ou na última coluna
 * de quem olha: é onde o selo perde a margem negativa para não sair do tabuleiro.
 */
export function squarePercent(square: Key, orientation: "white" | "black"): { left: number; top: number; topo: boolean; direita: boolean } {
  const file = square.charCodeAt(0) - 97;
  const rank = Number(square[1]) - 1;
  const col = orientation === "white" ? file : 7 - file;
  const row = orientation === "white" ? 7 - rank : rank;
  return { left: col * CASA_PCT, top: row * CASA_PCT, topo: row === 0, direita: col === 7 };
}

const toShape = (s: DrawShape): Shape => ({ orig: s.orig, dest: s.dest, brush: s.brush ?? "green" });
const toDrawShape = (s: Shape): DrawShape => ({ orig: s.orig as Key, dest: s.dest as Key | undefined, brush: s.brush });

/** Quanto tempo o dedo fica parado até virar desenho, e o quanto pode escorregar antes disso. */
const LONG_PRESS_MS = 350;
const LONG_PRESS_SLACK_PX = 12;

/** Ponteiro grosso (celular/tablet): não existe botão direito para desenhar. */
function coarsePointer(): boolean {
  // no jsdom (e em navegadores antigos) `matchMedia` não existe: trata como ponteiro fino
  const mm = typeof window === "undefined" ? undefined : window.matchMedia;
  try {
    return typeof mm === "function" && mm.call(window, "(pointer: coarse)").matches;
  } catch {
    return false;
  }
}

/** Como o tabuleiro se comporta, conforme só-leitura, marcações e tipo de ponteiro. */
function boardMode(p: BoardProps) {
  const readOnly = p.viewOnly ?? false;
  const draw = p.drawable ?? false;
  // Congelado com marcações: o `viewOnly` do chessground não registra evento
  // nenhum no tabuleiro — nem o do botão direito —, então mantemos os eventos
  // ligados e travamos arrastar, selecionar e premove.
  //
  // No celular é ao contrário: sem botão direito não haveria o que ganhar, e os
  // eventos ligados travariam a rolagem da página perto das peças. Aí o
  // `viewOnly` de verdade é melhor. O preço: no celular dá para desenhar no
  // tabuleiro do puzzle e no da análise (onde arrastar peça já segura a
  // rolagem), mas não na linha do resultado.
  const frozen = readOnly && draw && !coarsePointer();
  return { readOnly, frozen, viewOnly: readOnly && !frozen, longPress: draw && !readOnly && coarsePointer() };
}

/**
 * Config do modo montagem, por fora do caminho normal: nada de lances legais,
 * dica, marcações ou premove — só peças que vão e vêm. O `events.change` é
 * ligado no componente, que é quem tem a instância para pedir a FEN.
 */
function editorConfig(p: BoardProps, editor: BoardEditor): Config {
  return {
    fen: p.fen,
    orientation: p.orientation,
    turnColor: p.turnColor ?? "white",
    check: false,
    lastMove: undefined,
    // no editor o rei anda livre: sem roque automático (senão a torre pula junto)
    autoCastle: false,
    viewOnly: false,
    coordinates: p.coordinates ?? true,
    animation: { duration: 200 },
    movable: { free: true, color: "both", dests: new Map(), showDests: false, events: {} },
    draggable: { enabled: !editor.placing, deleteOnDropOff: true },
    // clicar é da paleta: sem isto o chessground moveria a peça selecionada
    selectable: { enabled: false },
    premovable: { enabled: false },
    drawable: { enabled: false, visible: false, autoShapes: [] },
    events: { select: editor.onSquareClick },
  };
}

export function toConfig(p: BoardProps): Config {
  if (p.editor) return editorConfig(p, p.editor);
  const { readOnly, frozen, viewOnly, longPress } = boardMode(p);
  return {
    fen: p.fen,
    orientation: p.orientation,
    turnColor: p.turnColor,
    check: p.check,
    lastMove: p.lastMove,
    viewOnly,
    coordinates: p.coordinates ?? true,
    animation: { duration: 200 },
    movable: { free: false, color: readOnly ? undefined : p.movableColor, dests: frozen ? new Map() : p.dests ?? new Map(), showDests: !frozen, events: { after: p.onMove } },
    draggable: { enabled: !frozen },
    selectable: { enabled: !frozen },
    premovable: { enabled: !frozen },
    drawable: {
      enabled: p.drawable ?? false,
      visible: true,
      // No celular quem desenha é o nosso toque longo, e o `eraseOnClick` do chessground
      // roda já no `touchstart` — antes dos 350 ms —, apagando tudo a cada gesto: só daria
      // para ter uma marcação por vez e repetir o gesto nunca apagaria. Desligado, as
      // marcações ficam até a posição mudar. No computador o clique esquerdo continua limpando.
      eraseOnClick: !longPress,
      // O chessground avisa aqui a cada seta/casa desenhada ou apagada. Ele não
      // dispara isto no `setShapes` da API, então devolver as marcações pelo
      // `shapes` não vira laço.
      onChange: p.onShapesChange ? (shapes: DrawShape[]) => p.onShapesChange!(shapes.map(toShape)) : undefined,
      autoShapes: [
        ...(p.highlight ?? []).map((k) => ({ orig: k, brush: "green" })),
        ...(p.arrows ?? []).map((a) => ({ orig: a.orig, dest: a.dest, brush: a.brush ?? "green" })),
        ...(p.squares ?? []).map((s) => ({ orig: s.orig, brush: s.brush ?? "green" })),
      ],
    },
  };
}

/**
 * Liga ou desliga uma marcação do usuário, preservando as outras, e avisa o
 * pai: o `setShapes` da API não dispara o `drawable.onChange` do chessground,
 * então sem este aviso o desenho do toque longo nunca chegaria à árvore.
 */
function toggleShape(api: Api, orig: Key, dest: Key | undefined, avisar?: (shapes: Shape[]) => void) {
  const shape: DrawShape = dest && dest !== orig ? { orig, dest, brush: "green" } : { orig, brush: "green" };
  const shapes = api.state.drawable.shapes ?? [];
  const kept = shapes.filter((s) => !(s.orig === shape.orig && s.dest === shape.dest && s.brush === shape.brush));
  const novas = kept.length === shapes.length ? [...shapes, shape] : kept;
  api.setShapes(novas);
  avisar?.(novas.map(toShape));
}

export function Board(props: BoardProps) {
  const host = useRef<HTMLDivElement>(null);
  const cg = useRef<Api | null>(null);
  const prevFen = useRef(props.fen);
  // true entre um lance feito no tabuleiro e a próxima sincronização da `fen`
  const pendingSync = useRef(false);
  const prevShapes = useRef(props.shapes);
  const longPress = useRef(false);
  longPress.current = boardMode(props).longPress;
  // o gesto do toque longo é registrado uma vez só: a props mais nova vem daqui
  const aoMudarMarcacoes = useRef(props.onShapesChange);
  aoMudarMarcacoes.current = props.onShapesChange;

  useEffect(() => {
    if (!host.current) return;
    cg.current = Chessground(host.current, toConfig(props));
    if (props.shapes?.length) cg.current.setShapes(props.shapes.map(toDrawShape));
    return () => { cg.current?.destroy(); cg.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Toque longo para desenhar: o chessground 9 só começa uma seta com o botão
  // direito ou com shift, então no celular não haveria como marcar nada.
  // Segurar o dedo numa casa entra no modo desenho; soltar em outra casa vira
  // seta, soltar na mesma vira destaque, e repetir o gesto apaga.
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let orig: Key | null = null;
    let from: [number, number] | null = null;
    let drawing = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const reset = () => {
      if (timer) clearTimeout(timer);
      timer = null; orig = null; from = null; drawing = false;
    };

    const onStart = (e: TouchEvent) => {
      reset();
      if (!longPress.current || e.touches.length !== 1) return;
      const t = e.touches[0];
      const key = cg.current?.getKeyAtDomPos([t.clientX, t.clientY]);
      if (!key) return;
      orig = key;
      from = [t.clientX, t.clientY];
      timer = setTimeout(() => {
        timer = null;
        drawing = true;
        // o chessground começou a arrastar a peça no mesmo toque: cancelar
        // evita jogar um lance junto com a marcação
        cg.current?.cancelMove();
        navigator.vibrate?.(10);
      }, LONG_PRESS_MS);
    };

    const onMove = (e: TouchEvent) => {
      if (drawing) { e.preventDefault(); return; }
      const t = e.touches[0];
      if (!from || !t) return;
      // escorregou antes da hora: é rolagem da página ou arrastar de peça
      if (Math.hypot(t.clientX - from[0], t.clientY - from[1]) > LONG_PRESS_SLACK_PX) reset();
    };

    const onEnd = (e: TouchEvent) => {
      const api = cg.current;
      if (drawing && orig && api) {
        const t = e.changedTouches[0];
        toggleShape(api, orig, t ? api.getKeyAtDomPos([t.clientX, t.clientY]) : undefined, aoMudarMarcacoes.current);
      }
      reset();
    };

    el.addEventListener("touchstart", onStart, { passive: true });
    el.addEventListener("touchmove", onMove, { passive: false });
    el.addEventListener("touchend", onEnd);
    el.addEventListener("touchcancel", reset);
    return () => {
      reset();
      el.removeEventListener("touchstart", onStart);
      el.removeEventListener("touchmove", onMove);
      el.removeEventListener("touchend", onEnd);
      el.removeEventListener("touchcancel", reset);
    };
  }, []);

  useEffect(() => {
    const config = toConfig(props);
    // Um lance que o app recusou (errado no puzzle, ilegal na análise) deixa a
    // peça deslocada dentro do chessground enquanto a `fen` do app não muda;
    // nesse caso a `fen` precisa ir junto para a peça voltar ao lugar.
    const fenChanged = prevFen.current !== props.fen;
    const moved = fenChanged || pendingSync.current;
    if (config.movable?.events) {
      const after = props.onMove;
      config.movable.events.after = (orig: Key, dest: Key) => { pendingSync.current = true; after?.(orig, dest); };
    }
    // A FEN das peças só a instância sabe dizer, daí o aviso ser montado aqui.
    // O `set({fen})` do chessground não dispara este evento: devolver a posição
    // pelo `fen` não vira laço.
    if (props.editor && config.events) {
      const aoMudar = props.editor.onChange;
      config.events.change = () => { if (cg.current) aoMudar(cg.current.getFen()); };
    }
    // O chessground zera `drawable.shapes` sempre que a config traz uma `fen`;
    // como este efeito roda a cada render (relógio do pai, por exemplo), a `fen`
    // só vai junto quando a posição realmente mudou — assim as marcações do
    // usuário sobrevivem aos re-renders e somem ao trocar de posição.
    if (!moved) delete config.fen;
    // ao repor a posição depois de um lance recusado, as marcações do usuário
    // seriam zeradas pela `fen`; guardamos e devolvemos.
    const keep = pendingSync.current && !fenChanged ? cg.current?.state.drawable.shapes ?? [] : null;
    cg.current?.set(config);
    pendingSync.current = false;
    if (keep && keep.length) cg.current?.setShapes(keep);
    // Trocar de posição (ou receber outra lista de marcações salvas) repõe o que
    // vem do `shapes`; sem `shapes`, o desenho do usuário some ao mudar de posição.
    if (fenChanged || prevShapes.current !== props.shapes) {
      prevFen.current = props.fen;
      prevShapes.current = props.shapes;
      cg.current?.setShapes((props.shapes ?? []).map(toDrawShape));
    }
  });
  const badge = props.badge;
  const pos = badge ? squarePercent(badge.square, props.orientation) : null;
  return (
    <div className="board">
      <div ref={host} />
      {badge && pos && (
        <span
          className={`board-badge${pos.topo ? " board-badge--topo" : ""}${pos.direita ? " board-badge--direita" : ""} ${badge.className}`}
          style={{
            left: `${pos.left}%`,
            top: `${pos.top}%`,
            width: `${CASA_PCT}%`,
            height: `${CASA_PCT}%`,
            pointerEvents: "none",
          }}
          aria-hidden="true"
        >
          <span>{badge.text}</span>
        </span>
      )}
    </div>
  );
}
