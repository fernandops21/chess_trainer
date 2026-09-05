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
  highlight?: Key[];
  onMove?: (orig: Key, dest: Key) => void;
  viewOnly?: boolean;
  coordinates?: boolean;
}

function toConfig(p: BoardProps): Config {
  return {
    fen: p.fen,
    orientation: p.orientation,
    turnColor: p.turnColor,
    check: p.check,
    lastMove: p.lastMove,
    viewOnly: p.viewOnly ?? false,
    coordinates: p.coordinates ?? true,
    animation: { duration: 200 },
    movable: { free: false, color: p.viewOnly ? undefined : p.movableColor, dests: p.dests ?? new Map(), showDests: true, events: { after: p.onMove } },
    drawable: { enabled: false, autoShapes: (p.highlight ?? []).map((k) => ({ orig: k, brush: "green" })) },
  };
}

export function Board(props: BoardProps) {
  const host = useRef<HTMLDivElement>(null);
  const cg = useRef<Api | null>(null);
  useEffect(() => {
    if (!host.current) return;
    cg.current = Chessground(host.current, toConfig(props));
    return () => { cg.current?.destroy(); cg.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { cg.current?.set(toConfig(props)); });
  return <div className="board"><div ref={host} /></div>;
}
