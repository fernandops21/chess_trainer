import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useDashboard, useQueue, useStudies, useTacticsStatus } from "../api/queries";
import type { PuzzleSource, QueueFilters, QueueMode } from "../api/types";
import { storage } from "../lib/storage";
import { ThemePicker } from "./ThemePicker";

export type SessionSource = "own" | "tactics";

/** O que a tela de início oferece: os três modos da fila e as táticas do Lichess. */
type Choice = QueueMode | "tactics";

export interface SessionConfig {
  source: SessionSource;
  /** Modo da fila; nas táticas do Lichess não vale (elas vêm do banco do Lichess). */
  mode: QueueMode;
  filters: QueueFilters;
  plannedMinutes: number | null;
  themes: string[];
}

const SOURCES: { value: PuzzleSource; label: string }[] = [
  { value: "own", label: "Meus erros" },
  { value: "lichess", label: "Lichess guardados" },
  { value: "study", label: "Estudos" },
];

const asKind = (v: string): QueueFilters["kind"] => (v === "punish" || v === "avoid" ? v : undefined);
const asColor = (v: string): QueueFilters["color"] => (v === "white" || v === "black" ? v : undefined);
const asChoice = (v: unknown): Choice | null =>
  v === "review" || v === "new" || v === "study" || v === "tactics" ? v : null;
const clampMinutes = (v: number): number => Math.min(180, Math.max(5, v || 25));

export function SessionStart({ onStart }: { onStart: (c: SessionConfig) => void }) {
  const [params] = useSearchParams();
  const studyParam = params.get("study");
  const [timed, setTimed] = useState<boolean>(storage.get("train.timed", true));
  const [minutes, setMinutes] = useState<number>(storage.get("train.minutes", 25));
  // `?study=` vem do botão "Treinar este estudo": ele manda mais que o `?mode=`,
  // que o `?source=` e que a última escolha guardada. Sem estudo escolhido não há
  // o que treinar, então "study" (guardado ou na URL) cai na repetição espaçada.
  const [choice, setChoice] = useState<Choice>(() => {
    if (studyParam) return "study";
    const naUrl = asChoice(params.get("mode")) ?? (params.get("source") === "tactics" ? "tactics" : null);
    const escolha = naUrl ?? asChoice(storage.get<Choice>("train.mode", "review"));
    return escolha && escolha !== "study" ? escolha : "review";
  });
  const [themes, setThemes] = useState<string[]>(() => storage.get<string[]>("train.themes", []));
  // fontes da fila (só na repetição espaçada): vazio = todas. Não fica guardado —
  // toda sessão nova começa sem filtro, senão um filtro velho esconde vencidos sem aviso.
  const [sources, setSources] = useState<PuzzleSource[]>([]);
  const [studyId, setStudyId] = useState<string>(studyParam ?? "");
  const [kind, setKind] = useState<string>("");
  const [color, setColor] = useState<string>("");
  const [category, setCategory] = useState<string>("");
  const source: SessionSource = choice === "tactics" ? "tactics" : "own";
  const mode: QueueMode = choice === "tactics" ? "review" : choice;
  // só consulta o banco de táticas quando ele importa para a escolha atual
  const { data: tactics } = useTacticsStatus(source === "tactics");
  const { data: studies } = useStudies(source === "own");
  // enquanto carrega (`undefined`) o botão continua liberado
  const missingTactics = source === "tactics" && tactics?.imported === false;
  // Com filtro na repetição espaçada dá para acabar numa fila menor que a do menu sem
  // entender por quê: a contagem filtrada aparece ao lado do total de vencidos.
  const filtrando = source === "own" && mode === "review" && (sources.length > 0 || !!kind || !!color || !!category);
  // só o número interessa aqui: `count_only` poupa o servidor de montar os
  // exercícios da fila inteira para mostrar uma contagem
  const filtrosFila: QueueFilters = {
    mode: "review", sources: sources.length ? sources : undefined,
    kind: asKind(kind), color: asColor(color), category: category || undefined,
    count_only: true,
  };
  const { data: filaFiltrada } = useQueue(filtrosFila, filtrando);
  const totalVencidos = useDashboard().data?.due_today;

  const toggleSource = (s: PuzzleSource) =>
    setSources((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : SOURCES.map((o) => o.value).filter((v) => v === s || prev.includes(v))));

  // escolher um modo desmarca o estudo; escolher um estudo vira o modo "study"
  const pick = (c: Choice) => { setChoice(c); setStudyId(""); };
  const pickStudy = (id: string) => { setStudyId(id); setChoice(id ? "study" : "review"); };

  const start = () => {
    const clamped = clampMinutes(minutes);
    storage.set("train.timed", timed); storage.set("train.minutes", clamped);
    storage.set("train.mode", choice); storage.set("train.themes", themes);
    onStart({
      source,
      mode,
      filters: source === "tactics" ? {} : mode === "study" ? { mode, study_id: studyId } : {
        mode,
        kind: asKind(kind), color: asColor(color), category: category || undefined,
        sources: mode === "review" && sources.length ? sources : undefined,
      },
      plannedMinutes: timed ? clamped : null,
      themes,
    });
  };

  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Nova sessão</h2>
      <div className="row">
        <label><input type="radio" name="modo" checked={choice === "review"} onChange={() => pick("review")} /> Repetição espaçada</label>
        <label><input type="radio" name="modo" checked={choice === "new"} onChange={() => pick("new")} /> Novos (meus erros)</label>
        <label><input type="radio" name="modo" checked={choice === "tactics"} onChange={() => pick("tactics")} /> Táticas do Lichess</label>
      </div>
      {source === "own" && (
        <div className="row" style={{ marginTop: 10 }}>
          <span className="muted">ou treinar um estudo inteiro:</span>
          <select value={studyId} onChange={(e) => pickStudy(e.target.value)} aria-label="Estudo">
            <option value="">nenhum</option>
            {(studies ?? []).map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
          </select>
        </div>
      )}
      {source === "own" && mode === "review" && (
        <div className="row" style={{ marginTop: 10 }}>
          <span className="muted">Fontes:</span>
          {SOURCES.map((s) => (
            <button key={s.value} className={`tag ${sources.includes(s.value) ? "selected" : ""}`} aria-pressed={sources.includes(s.value)}
              onClick={() => toggleSource(s.value)}>{s.label}</button>
          ))}
          <span className="muted">{sources.length ? "" : "(todas)"}</span>
          {filtrando && filaFiltrada && (
            <span className="muted">
              {filaFiltrada.due_count} vencido(s) com estes filtros
              {totalVencidos === undefined ? "" : ` · ${totalVencidos} no total`}
            </span>
          )}
        </div>
      )}
      {mode === "new" && (
        <div className="muted" style={{ marginTop: 10 }}>
          Exercícios dos seus erros que você ainda não revisou nenhuma vez, até o limite diário.
        </div>
      )}
      <div className="row" style={{ marginTop: 10 }}>
        <label><input type="radio" name="duracao" checked={!timed} onChange={() => setTimed(false)} /> até acabar a fila</label>
        <label><input type="radio" name="duracao" checked={timed} onChange={() => setTimed(true)} /> por tempo:</label>
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
      ) : mode !== "study" && (
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
