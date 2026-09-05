import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Chess } from "chess.js";
import type { Key } from "chessground/types";
import { useAnalyse } from "../api/queries";
import { Board } from "../board/Board";
import { ErrorBox } from "../components/ErrorBox";
import { formatEval } from "../lib/format";
import { useAnalysis } from "./useAnalysis";

function terminalLabel(terminal: string): string {
  if (terminal === "checkmate") return "Xeque-mate";
  if (terminal === "stalemate") return "Afogamento";
  return "Empate";
}

export function AnalysisBoard({ fenStart, orientation, backTo }: { fenStart: string; orientation: "white" | "black"; backTo: string }) {
  const an = useAnalysis(fenStart);
  const [orient, setOrient] = useState(orientation);
  const { data, error, isFetching } = useAnalyse(an.fen);

  const inCheck = useMemo(() => new Chess(an.fen).inCheck(), [an.fen]);
  const best = data?.lines[0];
  const arrows = best ? [{ orig: best.move.slice(0, 2) as Key, dest: best.move.slice(2, 4) as Key, brush: "green" }] : [];

  const onMove = (orig: Key, dest: Key) => {
    if (!an.play(`${orig}${dest}`)) an.play(`${orig}${dest}q`);
  };

  return (
    <div className="two-col">
      <div>
        <Board
          fen={an.fen} orientation={orient} turnColor={an.turn} movableColor={an.turn}
          dests={an.dests} lastMove={an.lastMove} check={inCheck} arrows={arrows}
          onMove={onMove}
        />
        <div className="row" style={{ marginTop: 8 }}>
          <button onClick={an.reset} disabled={an.fens.length <= 1} aria-label="posição inicial">⏮</button>
          <button onClick={an.undo} disabled={an.index === 0} aria-label="desfazer">◀</button>
          <button onClick={() => setOrient((o) => (o === "white" ? "black" : "white"))}>Inverter</button>
          <Link to={backTo}>Voltar</Link>
        </div>
      </div>
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
              <button key={i} className="pvline" onClick={() => an.playLine(line.pv)}>
                {formatEval(data.turn === "black" ? -line.score : line.score)} {line.pv_san.join(" ")}
              </button>
            ))}
          </div>
        )}
        {an.sans.length > 0 && (
          <div className="row" style={{ marginTop: 10 }}>
            <button onClick={() => an.goTo(0)} style={{ fontWeight: an.index === 0 ? 700 : 400 }}>início</button>
            {an.sans.map((san, i) => (
              <button key={i} onClick={() => an.goTo(i + 1)} style={{ fontWeight: an.index === i + 1 ? 700 : 400 }}>{san}</button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
