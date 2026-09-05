import { useState } from "react";
import type { QueueFilters } from "../api/types";
import { storage } from "../lib/storage";

export interface SessionConfig { filters: QueueFilters; plannedMinutes: number | null; }

const asKind = (v: string): QueueFilters["kind"] => (v === "punish" || v === "avoid" ? v : undefined);
const asColor = (v: string): QueueFilters["color"] => (v === "white" || v === "black" ? v : undefined);
const clampMinutes = (v: number): number => Math.min(180, Math.max(5, v || 25));

export function SessionStart({ onStart }: { onStart: (c: SessionConfig) => void }) {
  const [timed, setTimed] = useState<boolean>(storage.get("train.timed", true));
  const [minutes, setMinutes] = useState<number>(storage.get("train.minutes", 25));
  const [kind, setKind] = useState<string>("");
  const [color, setColor] = useState<string>("");
  const [category, setCategory] = useState<string>("");

  const start = () => {
    const clamped = clampMinutes(minutes);
    storage.set("train.timed", timed); storage.set("train.minutes", clamped);
    onStart({
      filters: { kind: asKind(kind), color: asColor(color), category: category || undefined },
      plannedMinutes: timed ? clamped : null,
    });
  };

  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Nova sessão</h2>
      <div className="row">
        <label><input type="radio" name="mode" checked={!timed} onChange={() => setTimed(false)} /> até acabar a fila</label>
        <label><input type="radio" name="mode" checked={timed} onChange={() => setTimed(true)} /> por tempo:</label>
        <input type="number" min={5} max={180} value={minutes} disabled={!timed} aria-label="Minutos"
          onChange={(e) => setMinutes(clampMinutes(Number(e.target.value)))} style={{ width: 80 }} /> min
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Tipo">
          <option value="">punir e evitar</option><option value="punish">só punir</option><option value="avoid">só evitar</option>
        </select>
        <select value={color} onChange={(e) => setColor(e.target.value)} aria-label="Cor">
          <option value="">qualquer cor</option><option value="white">brancas</option><option value="black">pretas</option>
        </select>
        <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Categoria">
          <option value="">qualquer categoria</option><option value="rapid">rapid</option><option value="daily">daily</option><option value="blitz">blitz</option><option value="bullet">bullet</option>
        </select>
      </div>
      <div className="row" style={{ marginTop: 14 }}><button className="primary" onClick={start}>Começar</button></div>
    </div>
  );
}
