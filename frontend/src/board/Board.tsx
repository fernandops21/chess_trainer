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

export function toConfig(p: BoardProps): Config {
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

/** Liga ou desliga uma marcação do usuário, preservando as outras. */
function toggleShape(api: Api, orig: Key, dest?: Key) {
  const shape: DrawShape = dest && dest !== orig ? { orig, dest, brush: "green" } : { orig, brush: "green" };
  const shapes = api.state.drawable.shapes ?? [];
  const kept = shapes.filter((s) => !(s.orig === shape.orig && s.dest === shape.dest && s.brush === shape.brush));
  api.setShapes(kept.length === shapes.length ? [...shapes, shape] : kept);
}

export function Board(props: BoardProps) {
  const host = useRef<HTMLDivElement>(null);
  const cg = useRef<Api | null>(null);
  const prevFen = useRef(props.fen);
  const prevShapes = useRef(props.shapes);
  const longPress = useRef(false);
  longPress.current = boardMode(props).longPress;

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
        toggleShape(api, orig, t ? api.getKeyAtDomPos([t.clientX, t.clientY]) : undefined);
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
    const moved = prevFen.current !== props.fen;
    // O chessground zera `drawable.shapes` sempre que a config traz uma `fen`;
    // como este efeito roda a cada render (relógio do pai, por exemplo), a `fen`
    // só vai junto quando a posição realmente mudou — assim as marcações do
    // usuário sobrevivem aos re-renders e somem ao trocar de posição.
    if (!moved) delete config.fen;
    cg.current?.set(config);
    // Trocar de posição (ou receber outra lista de marcações salvas) repõe o que
    // vem do `shapes`; sem `shapes`, o desenho do usuário some ao mudar de posição.
    if (moved || prevShapes.current !== props.shapes) {
      prevFen.current = props.fen;
      prevShapes.current = props.shapes;
      cg.current?.setShapes((props.shapes ?? []).map(toDrawShape));
    }
  });
  return <div className="board"><div ref={host} /></div>;
}
