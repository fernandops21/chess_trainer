import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { Key } from "chessground/types";
import { useLeeches, useMistakes, usePuzzleQuery, useUnleech } from "../api/queries";
import type { MistakeOut, MistakesQuery, PuzzleOut } from "../api/types";
import { Board } from "../board/Board";
import { MiniBoard } from "../board/MiniBoard";
import { uciToMove } from "../board/line";
import { ErrorBox } from "../components/ErrorBox";
import { Modal } from "../components/Modal";
import { formatDate, formatEval, levelLabel, puzzleTitle, themeLabel } from "../lib/format";
import { LineViewer } from "../train/LineViewer";

function MistakeDetail({ m, onClose }: { m: MistakeOut; onClose: () => void }) {
  const nav = useNavigate();
  const punish = m.puzzles.find((p) => p.kind === "punish");
  const { data: puzzle } = usePuzzleQuery(punish?.id ?? null);
  const played = uciToMove(m.move_uci);
  return (
    <Modal open title={`Lance ${Math.ceil(m.ply / 2)}: ${m.move_played}`} onClose={onClose}>
      {puzzle ? (
        <LineViewer fenStart={puzzle.fen_start} ucis={puzzle.solution.moves.map((x) => x.uci)} orientation={m.my_color} startPly={(puzzle.ply ?? 0) + 1} keyboard={false} />
      ) : (
        <Board fen={m.fen} orientation={m.my_color} lastMove={[played.from as Key, played.to as Key]} viewOnly />
      )}
      <div className="muted" style={{ marginTop: 8 }}>
        Você jogou <b>{m.move_played}</b> ({formatEval(m.eval_before)} → {formatEval(m.eval_after)}); melhor era <b>{m.best_move}</b>.
        {puzzle && <> Refutação acima ({themeLabel(puzzle.theme)}).</>}
        {m.puzzles.length === 0 && m.mistake_by === "me" && <> Sem puzzle: posicional ou trivial.</>}
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <Link to={`/partidas/${m.game_id}?ply=${m.ply}`}>ver na partida</Link>
        <button onClick={() => nav(`/analise?fen=${encodeURIComponent(m.fen)}&orientation=${m.my_color}&back=${encodeURIComponent("/erros")}`)}>
          Explorar
        </button>
        {m.puzzles.map((p) => (
          <button key={p.id} onClick={() => nav(`/treinar?puzzle=${p.id}&seen=1`)}>
            Treinar este ({p.kind === "punish" ? "punir" : "evitar"})
          </button>
        ))}
        <button onClick={onClose} style={{ marginLeft: "auto" }}>Fechar</button>
      </div>
    </Modal>
  );
}

function LeechCard({ p }: { p: PuzzleOut }) {
  const unleech = useUnleech();
  return (
    <div className="row" style={{ padding: "8px 0", borderBottom: "1px solid var(--line)" }}>
      <MiniBoard fen={p.fen_start} orientation={p.side_to_move} />
      <div style={{ flex: 1 }}>
        <div>{puzzleTitle(p)} · {themeLabel(p.theme)}</div>
        <div className="muted">{p.srs.lapses} erros seguidos</div>
      </div>
      <button onClick={() => unleech.mutate(p.id)} disabled={unleech.isPending}>Devolver à fila</button>
    </div>
  );
}

export function MistakesPage() {
  const [q, setQ] = useState<MistakesQuery>({ by: "me", limit: 50 });
  const { data, error, isLoading } = useMistakes(q);
  const leeches = useLeeches();
  const [open, setOpen] = useState<MistakeOut | null>(null);
  const items = data ?? [];
  return (
    <>
      <h1>Revisão de erros</h1>
      {leeches.data && leeches.data.length > 0 && (
        <div className="card"><h3 style={{ marginTop: 0 }}>Sanguessugas</h3>{leeches.data.map((p) => <LeechCard key={p.id} p={p} />)}</div>
      )}
      <div className="row card">
        <select value={q.level ?? ""} onChange={(e) => setQ({ ...q, level: (e.target.value || undefined) as MistakesQuery["level"], limit: 50 })} aria-label="Nível">
          <option value="">mistake e blunder</option><option value="mistake">só mistake</option><option value="blunder">só blunder</option>
        </select>
        <select value={q.category ?? ""} onChange={(e) => setQ({ ...q, category: e.target.value || undefined, limit: 50 })} aria-label="Categoria">
          <option value="">categoria</option><option value="rapid">rapid</option><option value="daily">daily</option><option value="classical">classical</option><option value="blitz">blitz</option><option value="bullet">bullet</option>
        </select>
        <label><input type="checkbox" checked={q.by === "all"} onChange={(e) => setQ({ ...q, by: e.target.checked ? "all" : "me", limit: 50 })} /> incluir erros do adversário</label>
      </div>
      <ErrorBox error={error ?? leeches.error} />
      {isLoading && <p className="muted">Carregando…</p>}
      <div className="card" style={{ padding: 0 }}>
        {items.map((m) => (
          <button key={m.position_id} className="mistakerow" onClick={() => setOpen(m)}>
            <MiniBoard fen={m.fen} orientation={m.my_color} />
            <div style={{ flex: 1, textAlign: "left" }}>
              <div><b>{m.move_played}</b> <span className={`tag ${m.mistake_level}`}>{levelLabel(m.mistake_level)}</span>{m.mistake_by === "opponent" && <span className="tag">adversário</span>}{m.puzzles.length === 0 && m.mistake_by === "me" && <span className="tag">posicional</span>}{m.puzzles.length > 0 && m.puzzles.every((p) => p.in_queue === false) && <span className="tag">fora da repetição</span>}</div>
              <div className="muted">{formatEval(m.eval_before)} → {formatEval(m.eval_after)} · melhor {m.best_move} {m.puzzles[0] && `· ${themeLabel(m.puzzles[0].theme)}`}</div>
              <div className="muted">{m.white} × {m.black} · {formatDate(m.played_at)} · {m.category}</div>
            </div>
          </button>
        ))}
        {!isLoading && items.length === 0 && <p className="muted" style={{ padding: 16 }}>Nenhum erro com esses filtros.</p>}
        {items.length >= (q.limit ?? 50) && <div style={{ padding: 16, textAlign: "center" }}><button onClick={() => setQ({ ...q, limit: (q.limit ?? 50) + 50 })}>Mostrar mais</button></div>}
      </div>
      {open && <MistakeDetail m={open} onClose={() => setOpen(null)} />}
    </>
  );
}
