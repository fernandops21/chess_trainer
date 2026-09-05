import { useState } from "react";
import { Link } from "react-router-dom";
import { useGames } from "../api/queries";
import type { Color, GamesQuery } from "../api/types";
import { ErrorBox } from "../components/ErrorBox";
import { colorName, formatDate, resultLabel } from "../lib/format";

const PAGE = 50;

export function GamesPage() {
  const [q, setQ] = useState<GamesQuery>({ limit: PAGE, offset: 0 });
  const { data, error, isLoading } = useGames(q);
  const set = (patch: Partial<GamesQuery>) => setQ({ ...q, ...patch, offset: 0 });
  return (
    <>
      <h1>Partidas</h1>
      <div className="row card">
        <select value={q.category ?? ""} onChange={(e) => set({ category: e.target.value || undefined })} aria-label="Categoria">
          <option value="">categoria</option><option value="rapid">rapid</option><option value="daily">daily</option><option value="classical">classical</option><option value="blitz">blitz</option><option value="bullet">bullet</option>
        </select>
        <select value={q.color ?? ""} onChange={(e) => set({ color: (e.target.value || undefined) as Color | undefined })} aria-label="Cor">
          <option value="">cor</option><option value="white">brancas</option><option value="black">pretas</option>
        </select>
        <select value={q.result ?? ""} onChange={(e) => set({ result: e.target.value || undefined })} aria-label="Resultado">
          <option value="">resultado</option><option value="1-0">1-0</option><option value="0-1">0-1</option><option value="1/2-1/2">empate</option>
        </select>
        <select value={q.analyzed === undefined ? "" : String(q.analyzed)} onChange={(e) => set({ analyzed: e.target.value === "" ? undefined : e.target.value === "true" })} aria-label="Analisada">
          <option value="">todas</option><option value="true">analisadas</option><option value="false">pendentes</option>
        </select>
      </div>
      <ErrorBox error={error} />
      {isLoading && <p className="muted">Carregando…</p>}
      {data && (
        <div className="card" style={{ padding: 0 }}>
          {data.map((g) => (
            <Link key={g.id} to={`/partidas/${g.id}`} className="gamerow">
              <span className="muted">{formatDate(g.played_at)}</span>
              <span>{g.my_color === "white" ? g.black : g.white}</span>
              <span className="muted">{colorName(g.my_color)}</span>
              <span>{resultLabel(g.result, g.my_color)}</span>
              <span className="tag">{g.category}</span>
              <span>{g.analyzed_at ? `${g.my_mistakes} erro(s)` : <span className="muted">pendente</span>}</span>
            </Link>
          ))}
          {data.length === 0 && <p className="muted" style={{ padding: 16 }}>Nenhuma partida.</p>}
        </div>
      )}
      <div className="row" style={{ marginTop: 10 }}>
        <button disabled={(q.offset ?? 0) === 0} onClick={() => setQ({ ...q, offset: Math.max(0, (q.offset ?? 0) - PAGE) })}>◀ anteriores</button>
        <button disabled={!data || data.length < PAGE} onClick={() => setQ({ ...q, offset: (q.offset ?? 0) + PAGE })}>próximas ▶</button>
      </div>
    </>
  );
}
