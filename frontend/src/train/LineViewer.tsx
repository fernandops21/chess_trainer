import { useEffect, useMemo, useRef, useState } from "react";
import { buildLine } from "../board/line";
import { Board } from "../board/Board";

export function LineViewer({ fenStart, ucis, orientation, startPly, keyboard = true }: { fenStart: string; ucis: string[]; orientation: "white" | "black"; startPly: number; keyboard?: boolean }) {
  // `ucis` is often rebuilt fresh (new array, same contents) by callers that re-render on
  // every tick (e.g. a session clock). Deriving a stable string key from its contents keeps
  // `line`/`pos` from being recomputed/reset unless the moves actually changed.
  const key = ucis.join(" ");
  const line = useMemo(() => buildLine(fenStart, ucis), [fenStart, key]);
  const [pos, setPos] = useState(line.fens.length - 1);
  const touchX = useRef<number | null>(null);
  const lenRef = useRef(line.fens.length);
  lenRef.current = line.fens.length;
  useEffect(() => { setPos(line.fens.length - 1); }, [fenStart, key]);

  const prev = () => setPos((p) => Math.max(0, p - 1));
  const next = () => setPos((p) => Math.min(lenRef.current - 1, p + 1));

  useEffect(() => {
    if (!keyboard) return;
    const h = (e: KeyboardEvent) => { if (e.key === "ArrowLeft") prev(); if (e.key === "ArrowRight") next(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [keyboard, key]);

  return (
    <div
      onTouchStart={(e) => { touchX.current = e.touches[0].clientX; }}
      onTouchEnd={(e) => { if (touchX.current == null) return; const dx = e.changedTouches[0].clientX - touchX.current; if (dx > 40) prev(); if (dx < -40) next(); touchX.current = null; }}
    >
      <Board fen={line.fens[pos]} orientation={orientation} lastMove={line.lastMoves[pos]} viewOnly />
      <div className="line" style={{ marginTop: 8 }}>
        {line.sans.map((san, i) => {
          const ply = startPly + i;
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
