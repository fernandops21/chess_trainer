import { useEffect, useRef } from "react";
import { Chessground } from "chessground";
import type { Api } from "chessground/api";
import type { Config } from "chessground/config";
import type { Key } from "chessground/types";
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
  /** Botão direito desenha setas/casas (clique esquerdo apaga). Não são salvas. */
  drawable?: boolean;
}

export function toConfig(p: BoardProps): Config {
  // O `viewOnly` do chessground não registra evento nenhum no tabuleiro — nem o
  // do botão direito. Para um tabuleiro só de leitura onde ainda dá para
  // desenhar (linha do resultado), deixamos os eventos ligados e travamos
  // arrastar, selecionar e premove.
  const readOnly = p.viewOnly ?? false;
  const frozen = readOnly && !!p.drawable;
  return {
    fen: p.fen,
    orientation: p.orientation,
    turnColor: p.turnColor,
    check: p.check,
    lastMove: p.lastMove,
    viewOnly: readOnly && !p.drawable,
    coordinates: p.coordinates ?? true,
    animation: { duration: 200 },
    movable: { free: false, color: readOnly ? undefined : p.movableColor, dests: frozen ? new Map() : p.dests ?? new Map(), showDests: !frozen, events: { after: p.onMove } },
    draggable: { enabled: !frozen },
    selectable: { enabled: !frozen },
    premovable: { enabled: !frozen },
    drawable: {
      enabled: p.drawable ?? false,
      visible: true,
      eraseOnClick: true,
      autoShapes: [
        ...(p.highlight ?? []).map((k) => ({ orig: k, brush: "green" })),
        ...(p.arrows ?? []).map((a) => ({ orig: a.orig, dest: a.dest, brush: a.brush ?? "green" })),
        ...(p.squares ?? []).map((s) => ({ orig: s.orig, brush: s.brush ?? "green" })),
      ],
    },
  };
}

export function Board(props: BoardProps) {
  const host = useRef<HTMLDivElement>(null);
  const cg = useRef<Api | null>(null);
  const prevFen = useRef(props.fen);
  useEffect(() => {
    if (!host.current) return;
    cg.current = Chessground(host.current, toConfig(props));
    return () => { cg.current?.destroy(); cg.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    if (moved) {
      prevFen.current = props.fen;
      cg.current?.setShapes([]);
    }
  });
  return <div className="board"><div ref={host} /></div>;
}
