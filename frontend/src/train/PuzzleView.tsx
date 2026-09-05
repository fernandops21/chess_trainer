import type { Key } from "chessground/types";
import type { PuzzleOut } from "../api/types";
import { Board } from "../board/Board";
import { colorName, kindLabel, themeLabel } from "../lib/format";
import type { usePuzzle } from "./usePuzzle";

type Ctl = ReturnType<typeof usePuzzle>;

export function PuzzleView({ puzzle, ctl, clockLabel, orderInfo }: { puzzle: PuzzleOut; ctl: Ctl; clockLabel?: string; orderInfo?: string }) {
  const { state, dests } = ctl;
  const playable = state.phase === "awaiting_move";
  return (
    <div className="two-col">
      <div>
        <Board
          fen={state.fen} orientation={puzzle.side_to_move} turnColor={state.turn}
          movableColor={playable ? puzzle.side_to_move : undefined} dests={dests}
          lastMove={state.lastMove} check={state.check} highlight={state.hint ? [state.hint] : []}
          onMove={(o: Key, d: Key) => ctl.tryMove(o, d)}
        />
        {state.pendingPromotion && (
          <div className="card row" style={{ marginTop: 8 }}>
            <span>Promover a:</span>
            <div className="promo">
              {(["q", "r", "b", "n"] as const).map((p) => <button key={p} onClick={() => ctl.choosePromotion(p)}>{{ q: "♕", r: "♖", b: "♗", n: "♘" }[p]}</button>)}
            </div>
            <button onClick={ctl.cancelPromotion}>Cancelar</button>
          </div>
        )}
      </div>
      <div className="card">
        <div style={{ fontSize: 20, fontWeight: 600 }}>{colorName(puzzle.side_to_move)} jogam · {kindLabel(puzzle.kind)}</div>
        <div className="muted">
          <span className="tag">{themeLabel(puzzle.theme)}</span><span className="tag">{puzzle.category}</span>
          {puzzle.game.white} × {puzzle.game.black}, lance {Math.ceil(puzzle.ply / 2)} · {puzzle.solver_moves} lance(s) seu(s)
          {puzzle.srs.due_at ? ` · revisão (intervalo ${puzzle.srs.interval_days} d)` : " · novo"}
          {orderInfo ? ` · ${orderInfo}` : ""}
        </div>
        <div className={`msg ${state.message.tone}`} aria-live="polite">{state.message.text}</div>
        <div className="row" style={{ marginTop: 10 }}>
          <button onClick={ctl.useHint} disabled={!playable || state.usedHint}>Dica</button>
          {clockLabel && <span className="muted" aria-label="relógio">{clockLabel}</span>}
        </div>
      </div>
    </div>
  );
}
