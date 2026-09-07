import { useEffect, useMemo, useRef, useState } from "react";
import type { Key } from "chessground/types";
import type { Shape } from "../api/types";
import { buildLine } from "../board/line";
import { Board } from "../board/Board";

interface LineViewerProps {
  fenStart: string;
  ucis: string[];
  orientation: "white" | "black";
  startPly: number;
  keyboard?: boolean;
  /** Posição de abertura, contada a partir de `fenStart` (0 = `fenStart`). */
  initialPos?: number;
  /** Posição corrente, também contada a partir de `fenStart` (−1 = `fenBefore`). */
  onPos?: (pos: number) => void;
  /** Posição de antes do último lance do adversário: vira a posição inicial da linha. */
  fenBefore?: string;
  lastMoveUci?: string;
  /** Setas e casas do autor do estudo: índice do lance (texto) ou "start". */
  shapes?: Record<string, Shape[]>;
  drawable?: boolean;
}

export function LineViewer({ fenStart, ucis, orientation, startPly, keyboard = true, initialPos, onPos, fenBefore, lastMoveUci, shapes, drawable = true }: LineViewerProps) {
  // `ucis` is often rebuilt fresh (new array, same contents) by callers that re-render on
  // every tick (e.g. a session clock). Deriving a stable string key from its contents keeps
  // `line`/`pos` from being recomputed/reset unless the moves actually changed.
  const key = ucis.join(" ");
  // Com o último lance do adversário a linha inteira recua uma posição: `offset`
  // é o quanto os índices internos ficam à frente dos índices vistos de fora
  // (que continuam contados a partir de `fenStart`, como sempre).
  const { line, offset } = useMemo(() => {
    if (fenBefore && lastMoveUci) {
      const withIntro = buildLine(fenBefore, [lastMoveUci, ...ucis]);
      // lance do adversário ilegal para a fen guardada: cai no comportamento de sempre
      if (withIntro.sans.length > 0) return { line: withIntro, offset: 1 };
    }
    return { line: buildLine(fenStart, ucis), offset: 0 };
  }, [fenStart, key, fenBefore, lastMoveUci]);
  const clamp = (n: number) => Math.max(0, Math.min(line.fens.length - 1, n));
  const opening = () => (initialPos == null ? line.fens.length - 1 : clamp(initialPos + offset));
  const [pos, setPos] = useState(opening);
  const touchX = useRef<number | null>(null);
  const lenRef = useRef(line.fens.length);
  lenRef.current = line.fens.length;
  useEffect(() => { setPos(opening()); }, [fenStart, key, fenBefore, lastMoveUci]);
  // avisa quem mostra algo por posição (comentários do autor do estudo, por exemplo)
  const onPosRef = useRef(onPos);
  onPosRef.current = onPos;
  useEffect(() => { onPosRef.current?.(pos - offset); }, [pos, offset]);

  const prev = () => setPos((p) => Math.max(0, p - 1));
  const next = () => setPos((p) => Math.min(lenRef.current - 1, p + 1));

  useEffect(() => {
    if (!keyboard) return;
    const h = (e: KeyboardEvent) => { if (e.key === "ArrowLeft") prev(); if (e.key === "ArrowRight") next(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [keyboard, key]);

  // marcações do autor: "start" na posição de `fenStart`, senão o índice do lance jogado
  const rel = pos - offset;
  const shapeKey = rel === 0 ? "start" : rel > 0 ? String(rel - 1) : null;
  const authored = (shapeKey ? shapes?.[shapeKey] : undefined) ?? [];
  const arrows = authored.filter((s) => s.dest).map((s) => ({ orig: s.orig as Key, dest: s.dest as Key, brush: s.brush }));
  const squares = authored.filter((s) => !s.dest).map((s) => ({ orig: s.orig as Key, brush: s.brush }));

  return (
    <div
      onTouchStart={(e) => { touchX.current = e.touches[0].clientX; }}
      onTouchEnd={(e) => { if (touchX.current == null) return; const dx = e.changedTouches[0].clientX - touchX.current; if (dx > 40) prev(); if (dx < -40) next(); touchX.current = null; }}
    >
      <Board fen={line.fens[pos]} orientation={orientation} lastMove={line.lastMoves[pos]} arrows={arrows} squares={squares} drawable={drawable} viewOnly />
      <div className="line" style={{ marginTop: 8 }}>
        {line.sans.map((san, i) => {
          const ply = startPly - offset + i;
          const num = ply % 2 === 1 ? `${Math.ceil(ply / 2)}. ` : i === 0 ? `${Math.ceil(ply / 2)}… ` : "";
          return <button key={i} className={`san ${i + 1 === pos ? "cur" : ""}`} onClick={() => setPos(i + 1)}>{num}{san}</button>;
        })}
      </div>
      <div className="row" style={{ marginTop: 6 }}>
        <button onClick={prev} aria-label="anterior">◀</button>
        <button onClick={next} aria-label="próximo">▶</button>
        <span className="muted">{pos}/{line.fens.length - 1}</span>
      </div>
    </div>
  );
}
