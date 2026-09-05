import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTacticsStatus } from "../api/queries";
import type { QueueFilters } from "../api/types";
import { storage } from "../lib/storage";
import { ThemePicker } from "./ThemePicker";

export type SessionSource = "own" | "tactics";

export interface SessionConfig {
  source: SessionSource;
  filters: QueueFilters;
  plannedMinutes: number | null;
  themes: string[];
}

const asKind = (v: string): QueueFilters["kind"] => (v === "punish" || v === "avoid" ? v : undefined);
const asColor = (v: string): QueueFilters["color"] => (v === "white" || v === "black" ? v : undefined);
const asSource = (v: unknown): SessionSource => (v === "tactics" ? "tactics" : "own");
const clampMinutes = (v: number): number => Math.min(180, Math.max(5, v || 25));

export function SessionStart({ onStart }: { onStart: (c: SessionConfig) => void }) {
  const [params] = useSearchParams();
  const [timed, setTimed] = useState<boolean>(storage.get("train.timed", true));
  const [minutes, setMinutes] = useState<number>(storage.get("train.minutes", 25));
  const [source, setSource] = useState<SessionSource>(() =>
    params.get("source") ? asSource(params.get("source")) : asSource(storage.get<SessionSource>("train.source", "own")));
  const [themes, setThemes] = useState<string[]>(() => storage.get<string[]>("train.themes", []));
  const [kind, setKind] = useState<string>("");
  const [color, setColor] = useState<string>("");
  const [category, setCategory] = useState<string>("");
  // só consulta o banco de táticas quando ele importa para a escolha atual
  const { data: tactics } = useTacticsStatus(source === "tactics");
  // enquanto carrega (`undefined`) o botão continua liberado
  const missingTactics = source === "tactics" && tactics?.imported === false;

  const start = () => {
    const clamped = clampMinutes(minutes);
    storage.set("train.timed", timed); storage.set("train.minutes", clamped);
    storage.set("train.source", source); storage.set("train.themes", themes);
    onStart({
      source,
      filters: source === "tactics" ? {} : { kind: asKind(kind), color: asColor(color), category: category || undefined },
      plannedMinutes: timed ? clamped : null,
      themes,
    });
  };

  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Nova sessão</h2>
      <div className="row">
        <label><input type="radio" name="source" checked={source === "own"} onChange={() => setSource("own")} /> Meus erros</label>
        <label><input type="radio" name="source" checked={source === "tactics"} onChange={() => setSource("tactics")} /> Táticas do Lichess</label>
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <label><input type="radio" name="mode" checked={!timed} onChange={() => setTimed(false)} /> até acabar a fila</label>
        <label><input type="radio" name="mode" checked={timed} onChange={() => setTimed(true)} /> por tempo:</label>
        <input type="number" min={5} max={180} value={minutes} disabled={!timed} aria-label="Minutos"
          onChange={(e) => setMinutes(clampMinutes(Number(e.target.value)))} style={{ width: 80 }} /> min
      </div>
      {source === "tactics" ? (
        <div style={{ marginTop: 10 }}>
          <ThemePicker selected={themes} onChange={setThemes} />
          {missingTactics && (
            <div className="msg bad" style={{ marginTop: 10 }}>
              Banco de táticas não importado — <Link to="/config">baixar em Configurações</Link>
            </div>
          )}
        </div>
      ) : (
        <div className="row" style={{ marginTop: 10 }}>
          <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Tipo">
            <option value="">punir e evitar</option><option value="punish">só punir</option><option value="avoid">só evitar</option>
          </select>
          <select value={color} onChange={(e) => setColor(e.target.value)} aria-label="Cor">
            <option value="">qualquer cor</option><option value="white">brancas</option><option value="black">pretas</option>
          </select>
          <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Categoria">
            <option value="">qualquer categoria</option><option value="rapid">rapid</option><option value="daily">daily</option><option value="classical">classical</option><option value="blitz">blitz</option><option value="bullet">bullet</option>
          </select>
        </div>
      )}
      <div className="row" style={{ marginTop: 14 }}>
        <button className="primary" onClick={start} disabled={missingTactics}>Começar</button>
      </div>
    </div>
  );
}
