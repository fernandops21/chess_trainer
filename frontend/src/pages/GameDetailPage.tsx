import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useGame, useStartJob, useStatus } from "../api/queries";
import { Board } from "../board/Board";
import { ErrorBox } from "../components/ErrorBox";
import { MoveList } from "../components/MoveList";
import { colorName, formatDate, formatEval, levelLabel, resultLabel } from "../lib/format";
import { buildPlies } from "../lib/plies";

export function GameDetailPage() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { data: game, error, isLoading } = useGame(id);
  const { data: status } = useStatus();
  const start = useStartJob();
  const plies = useMemo(() => (game ? buildPlies(game) : []), [game]);
  const [current, setCurrent] = useState<number>(Math.max(0, Number(params.get("ply")) || 0));

  useEffect(() => {
    if (plies.length > 0) setCurrent((c) => Math.min(c, plies.length));
  }, [plies.length]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "ArrowLeft") setCurrent((c) => Math.max(0, c - 1)); if (e.key === "ArrowRight") setCurrent((c) => Math.min(plies.length, c + 1)); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [plies.length]);

  if (isLoading) return <p className="muted">Carregando…</p>;
  if (error || !game) return <ErrorBox error={error ?? new Error("Partida não encontrada")} />;
  const ply = current > 0 ? plies[current - 1] : undefined;
  const fen = ply ? ply.fenAfter : plies[0]?.fenBefore ?? "start";
  const analyzing = status?.job.state === "running";
  return (
    <>
      <h1>{game.white} × {game.black}</h1>
      <div className="muted">{formatDate(game.played_at)} · {game.category} · você de {colorName(game.my_color).toLowerCase()} · {resultLabel(game.result, game.my_color)} · <a href={game.source_id} target="_blank" rel="noopener">chess.com</a></div>
      <div className="two-col" style={{ marginTop: 12 }}>
        <div>
          <Board fen={fen} orientation={game.my_color} lastMove={ply?.lastMove} viewOnly />
          <div className="row" style={{ marginTop: 6 }}>
            <button onClick={() => setCurrent(0)} aria-label="início">⏮</button>
            <button onClick={() => setCurrent((c) => Math.max(0, c - 1))} aria-label="anterior">◀</button>
            <button onClick={() => setCurrent((c) => Math.min(plies.length, c + 1))} aria-label="próximo">▶</button>
            <button onClick={() => setCurrent(plies.length)} aria-label="fim">⏭</button>
            <button onClick={() => navigate(`/analise?fen=${encodeURIComponent(fen)}&orientation=${game.my_color}&back=${encodeURIComponent(`/partidas/${game.id}?ply=${current}`)}`)}>
              Explorar daqui
            </button>
          </div>
          {ply && game.analyzed_at && (
            <div className="card" style={{ marginTop: 10 }}>
              <div>Lance {Math.ceil(ply.ply / 2)}{ply.ply % 2 ? "." : "…"} {ply.san} {ply.level && <span className={`tag ${ply.level}`}>{levelLabel(ply.level)}{ply.by === "me" ? " seu" : " do adversário"}</span>}</div>
              <div className="muted">avaliação {formatEval(ply.evalBefore ?? 0)} → {formatEval(ply.evalAfter ?? 0)}{ply.bestMove ? ` · melhor: ${ply.bestMove}` : ""}</div>
              {ply.puzzleIds.map((pid) => <button key={pid} style={{ marginTop: 6 }} onClick={() => navigate(`/treinar?puzzle=${pid}`)}>Treinar este</button>)}
            </div>
          )}
        </div>
        <div className="card">
          {!game.analyzed_at && (
            <div className="row" style={{ marginBottom: 10 }}>
              <span className="muted">Partida ainda não analisada.</span>
              <button className="primary" disabled={analyzing || start.isPending || !status?.engine.available} onClick={() => start.mutate({ kind: "analyze", game_id: game.id })}>
                {analyzing ? "Análise em andamento…" : "Analisar esta partida"}
              </button>
              <ErrorBox error={start.error} />
            </div>
          )}
          <MoveList plies={plies} current={current} onSelect={setCurrent} />
        </div>
      </div>
    </>
  );
}
