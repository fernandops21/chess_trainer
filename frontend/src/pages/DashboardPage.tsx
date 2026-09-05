import { useNavigate } from "react-router-dom";
import { useDashboard, useStatus } from "../api/queries";
import { ErrorBox } from "../components/ErrorBox";
import { JobCard } from "../components/JobCard";
import { StatCard } from "../components/StatCard";
import { formatDate } from "../lib/format";

export function DashboardPage() {
  const navigate = useNavigate();
  const dash = useDashboard();
  const status = useStatus();
  const d = dash.data;
  const s = status.data;
  return (
    <>
      <h1>Painel</h1>
      <ErrorBox error={dash.error ?? status.error} />
      {d && (
        <div className="row" style={{ alignItems: "stretch" }}>
          <StatCard value={d.due_today} label="vencidos hoje" />
          <StatCard value={d.new_available} label="novos disponíveis" hint={`${d.new_remaining_today} cabem hoje`} />
          <StatCard value={d.streak_days} label="dias seguidos" hint={`${d.reviews_today} revisões hoje`} />
        </div>
      )}
      <div className="row" style={{ margin: "6px 0 14px" }}>
        <button className="primary" onClick={() => navigate("/treinar")}>Treinar{d ? ` (${d.due_today + Math.min(d.new_available, d.new_remaining_today)})` : ""}</button>
      </div>
      {s && d && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Estado</h3>
          <div>{d.games_analyzed} de {d.games_total} partidas analisadas · {d.puzzles_total} puzzles · {d.leeches} sanguessugas</div>
          <div className="muted">Última importação: {s.last_import_at ? formatDate(s.last_import_at) : "nunca"}</div>
          <div>Engine: {s.engine.available ? <><span className="msg ok">encontrada</span> <span className="muted" style={{ fontSize: 13 }}>{s.engine.path}</span></> : <span className="msg bad">ausente — <a href="/config" onClick={(e) => { e.preventDefault(); navigate("/config"); }}>configurar</a></span>}</div>
        </div>
      )}
      <JobCard />
    </>
  );
}
