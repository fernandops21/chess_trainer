import { useState } from "react";
import { useProgress, useThemeStats } from "../api/queries";
import type { PuzzleSource } from "../api/types";
import { ErrorBox } from "../components/ErrorBox";
import { StatCard } from "../components/StatCard";
import { BarChart } from "../components/charts/BarChart";
import { LineChart } from "../components/charts/LineChart";
import { formatDate, themeLabel } from "../lib/format";

const PERIODOS = [30, 90, 365];

const FONTES: Record<PuzzleSource, string> = {
  own: "meus erros",
  lichess: "Lichess",
  study: "estudos",
};

/** Acerto em porcentagem; sem tentativas vira travessão. */
function acerto(certas: number, total: number): string {
  return total > 0 ? `${Math.round((100 * certas) / total)}%` : "—";
}

/** "AAAA-MM-DD" → "DD/MM" (o dia já vem no fuso local do servidor). */
function diaCurto(dia: string): string {
  const [, mes, d] = dia.split("-");
  return `${d}/${mes}`;
}

export function ProgressPage() {
  const [dias, setDias] = useState(90);
  const progresso = useProgress(dias);
  const temas = useThemeStats(dias);
  const p = progresso.data;
  const linhasTema = temas.data ?? [];
  return (
    <>
      <h1>Progresso</h1>
      <div className="row card" role="group" aria-label="Período">
        {PERIODOS.map((d) => (
          <button
            key={d}
            className={`tag${d === dias ? " selected" : ""}`}
            aria-pressed={d === dias}
            onClick={() => setDias(d)}
          >
            {d} dias
          </button>
        ))}
      </div>
      <ErrorBox error={progresso.error} />
      {progresso.isLoading && <p className="muted">Carregando…</p>}
      {p && (
        <>
          <div className="row" style={{ alignItems: "stretch" }}>
            <StatCard value={p.streak_days} label="dias seguidos" hint="sequência de dias com revisão" />
            <StatCard value={p.totals.reviews} label="revisões no período"
                      hint={`${p.totals.correct} certas · ${acerto(p.totals.correct, p.totals.reviews)} de acerto`} />
            <StatCard value={p.totals.puzzles_in_queue} label="exercícios na fila" />
          </div>
          {p.reviews_per_day.length === 0 ? (
            <p className="muted" style={{ marginTop: 14 }}>Ainda não há revisões neste período.</p>
          ) : (
            <div className="card">
              <h3 style={{ marginTop: 0 }}>Revisões por dia</h3>
              <BarChart
                titulo="Revisões por dia"
                bars={p.reviews_per_day.map((d) => ({ label: diaCurto(d.day), correct: d.correct, wrong: d.wrong }))}
              />
              <div className="grafico-legenda">
                <span><span className="amostra" style={{ background: "var(--ok)" }} />certas</span>
                <span><span className="amostra" style={{ background: "var(--bad)" }} />erradas</span>
              </div>
            </div>
          )}
          {p.tactics_rating.length > 0 && (
            <div className="card">
              <h3 style={{ marginTop: 0 }}>Rating de táticas</h3>
              <LineChart
                titulo="Rating de táticas"
                points={p.tactics_rating.map((ponto) => ({ label: formatDate(ponto.at), value: ponto.rating }))}
              />
            </div>
          )}
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Por fonte</h3>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left" }}>fonte</th>
                  <th style={{ textAlign: "right" }}>revisões</th>
                  <th style={{ textAlign: "right" }}>certas</th>
                  <th style={{ textAlign: "right" }}>acerto</th>
                </tr>
              </thead>
              <tbody>
                {(Object.keys(FONTES) as PuzzleSource[]).map((fonte) => {
                  const linha = p.by_source[fonte] ?? { reviews: 0, correct: 0 };
                  return (
                    <tr key={fonte}>
                      <td>{FONTES[fonte]}</td>
                      <td style={{ textAlign: "right" }}>{linha.reviews}</td>
                      <td style={{ textAlign: "right" }}>{linha.correct}</td>
                      <td style={{ textAlign: "right" }}>{acerto(linha.correct, linha.reviews)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
      {linhasTema.length > 0 && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Por tema</h3>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left" }}>tema</th>
                <th style={{ textAlign: "right" }}>tentativas</th>
                <th style={{ textAlign: "right" }}>certas</th>
                <th style={{ textAlign: "right" }}>acerto</th>
              </tr>
            </thead>
            <tbody>
              {linhasTema.map((r) => (
                <tr key={r.theme}>
                  <td>{r.label || themeLabel(r.theme)}</td>
                  <td style={{ textAlign: "right" }}>{r.attempts}</td>
                  <td style={{ textAlign: "right" }}>{r.correct}</td>
                  <td style={{ textAlign: "right" }}>{acerto(r.correct, r.attempts)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
