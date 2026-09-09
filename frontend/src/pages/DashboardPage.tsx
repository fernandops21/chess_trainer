import { Link, useNavigate } from "react-router-dom";
import { useDashboard, useStatus, useTacticsStatus, useThemeStats } from "../api/queries";
import { ErrorBox } from "../components/ErrorBox";
import { JobCard } from "../components/JobCard";
import { StatCard } from "../components/StatCard";
import { ThemeBars } from "../components/ThemeBars";
import { formatDate, themeLabel } from "../lib/format";

export function DashboardPage() {
  const navigate = useNavigate();
  const dash = useDashboard();
  const status = useStatus();
  const tactics = useTacticsStatus();
  const themes = useThemeStats(30);
  const d = dash.data;
  const s = status.data;
  const t = tactics.data;
  const rows = themes.data ?? [];
  // "mais fraco" só faz sentido com alguma amostra: menos de 3 tentativas é ruído.
  const weakest = rows.filter((r) => r.attempts >= 3).reduce<(typeof rows)[number] | null>(
    (worst, r) => (worst === null || r.accuracy < worst.accuracy ? r : worst), null);
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
        {/* revisar só serve o que venceu; a primeira vez de cada exercício é em "Fazer novos" */}
        <button className="primary" onClick={() => navigate("/revisar")}>Revisar{d ? ` (${d.due_today})` : ""}</button>
        <button onClick={() => navigate("/treinar?mode=new")}>Fazer novos</button>
        <Link to="/progresso" style={{ alignSelf: "center" }}>Progresso</Link>
      </div>
      {s && d && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Estado</h3>
          <div>{d.games_analyzed} de {d.games_total} partidas analisadas · {d.puzzles_total} exercícios no total (todas as fontes) · {d.leeches} sanguessugas</div>
          {d.by_source && (
            <div className="muted">
              {d.by_source.own?.in_queue ?? 0} dos seus erros · {d.by_source.lichess?.in_queue ?? 0} do Lichess · {d.by_source.study?.in_queue ?? 0} de estudos
            </div>
          )}
          <div className="muted">Última importação: {s.last_import_at ? formatDate(s.last_import_at) : "nunca"}</div>
          <div>Engine: {s.engine.available ? <><span className="msg ok">encontrada</span> <span className="muted" style={{ fontSize: 13 }}>{s.engine.path}</span></> : <span className="msg bad">ausente — <Link to="/config">configurar</Link></span>}</div>
        </div>
      )}
      {t?.imported && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Táticas</h3>
          <div className="row" style={{ alignItems: "stretch" }}>
            <StatCard value={t.rating} label="rating de táticas" hint={`janela ±${t.window}`} />
            <StatCard value={t.attempts_today} label="tentativas hoje" hint={`${t.attempts_total} no total`} />
            <StatCard
              value={t.attempts_30d > 0 ? `${Math.round((100 * t.correct_30d) / t.attempts_30d)}%` : "—"}
              label="acerto (30 dias)"
              hint={`${t.correct_30d}/${t.attempts_30d} tentativas`}
            />
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <button onClick={() => navigate("/treinar?source=tactics")}>Treinar táticas</button>
          </div>
        </div>
      )}
      {t && !t.imported && (
        <div className="muted" style={{ margin: "6px 0 14px" }}>
          Banco de táticas não importado — <Link to="/config">baixar em Configurações</Link>
        </div>
      )}
      {rows.length > 0 && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Por tema (30 dias)</h3>
          <ThemeBars rows={rows} />
          {weakest && (
            <div className="muted" style={{ marginTop: 8 }}>
              Tema mais fraco: {weakest.label || themeLabel(weakest.theme)} ({Math.round(weakest.accuracy * 100)}%)
            </div>
          )}
        </div>
      )}
      <JobCard />
    </>
  );
}
