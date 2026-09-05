import { useEffect, useState } from "react";
import type { ChangeEvent } from "react";
import { useSaveSettings, useSettings, useStartJob, useStatus } from "../api/queries";
import type { Settings } from "../api/types";
import { ErrorBox } from "../components/ErrorBox";
import { Modal } from "../components/Modal";

const CATEGORIES = ["rapid", "daily", "classical", "blitz", "bullet"];
const RANGES: Record<string, [number, number]> = {
  analysis_depth: [6, 30], puzzle_depth: [6, 30], mistake_threshold_cp: [50, 1000], blunder_threshold_cp: [50, 1000],
  avoid_gap_cp: [50, 1000], new_per_day: [1, 100], leech_lapses: [2, 20],
  analysis_seconds: [1, 120], puzzle_search_seconds: [1, 120], puzzle_reply_seconds: [1, 120],
};

export function validate(s: Settings): string[] {
  const errs: string[] = [];
  for (const [k, [lo, hi]] of Object.entries(RANGES)) {
    const v = s[k as keyof Settings] as number;
    if (!Number.isInteger(v) || v < lo || v > hi) errs.push(`${k}: inteiro entre ${lo} e ${hi}`);
  }
  if (s.blunder_threshold_cp < s.mistake_threshold_cp) errs.push("blunder deve ser ≥ mistake");
  if (!s.chesscom_username.trim()) errs.push("informe o usuário do chess.com");
  return errs;
}

export function SettingsPage() {
  const { data, error } = useSettings();
  const { data: status } = useStatus();
  const save = useSaveSettings();
  const start = useStartJob();
  const [form, setForm] = useState<Settings | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [confirmAvoid, setConfirmAvoid] = useState(false);
  const [saved, setSaved] = useState(false);
  useEffect(() => { if (data && !form) setForm(data); }, [data, form]);
  if (error) return <ErrorBox error={error} />;
  if (!form) return <p className="muted">Carregando…</p>;
  const errs = validate(form);
  const num = (k: keyof Settings) => (e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: Number(e.target.value) });
  const field = (label: string, k: keyof Settings) => (
    <label className="row" style={{ justifyContent: "space-between" }}>{label}<input type="number" value={form[k] as number} onChange={num(k)} style={{ width: 100 }} /></label>
  );
  return (
    <>
      <h1>Configurações</h1>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Chess.com</h3>
        <label className="row" style={{ justifyContent: "space-between" }}>usuário<input value={form.chesscom_username} onChange={(e) => setForm({ ...form, chesscom_username: e.target.value })} /></label>
        <div className="row" style={{ marginTop: 8 }}>
          {CATEGORIES.map((c) => (
            <label key={c}><input type="checkbox" checked={form.categories.includes(c)} onChange={(e) => setForm({ ...form, categories: e.target.checked ? [...form.categories, c] : form.categories.filter((x) => x !== c) })} /> {c}</label>
          ))}
        </div>
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Engine</h3>
        <label className="row" style={{ justifyContent: "space-between" }}>caminho do Stockfish<input value={form.stockfish_path} placeholder="vazio = procurar em engines/ ou no PATH" onChange={(e) => setForm({ ...form, stockfish_path: e.target.value })} style={{ flex: 1 }} /></label>
        <div className="muted">Estado atual: {status?.engine.available ? `encontrada em ${status.engine.path}` : "não encontrada"} (salve para testar um caminho novo)</div>
        {field("profundidade da análise", "analysis_depth")}
        {field("profundidade do puzzle", "puzzle_depth")}
        {field("tempo máximo por busca da análise (s)", "analysis_seconds")}
        {field("tempo máximo por busca do puzzle (s)", "puzzle_search_seconds")}
        {field("tempo máximo da resposta do defensor (s)", "puzzle_reply_seconds")}
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Erros e treino</h3>
        {field("limiar de mistake (cp)", "mistake_threshold_cp")}
        {field("limiar de blunder (cp)", "blunder_threshold_cp")}
        {field("gap mínimo do puzzle evitar (cp)", "avoid_gap_cp")}
        {field("puzzles novos por dia", "new_per_day")}
        {field("sanguessuga após N erros", "leech_lapses")}
      </div>
      {errs.length > 0 && <div className="msg bad">{errs.join(" · ")}</div>}
      <div className="row">
        <button className="primary" disabled={errs.length > 0 || save.isPending} onClick={() => save.mutate(form, { onSuccess: (s) => { setForm(s); setSaved(true); setTimeout(() => setSaved(false), 2500); } })}>Salvar</button>
        {saved && <span className="msg ok">Salvo.</span>}
        <ErrorBox error={save.error} />
      </div>
      <div className="card" style={{ marginTop: 20 }}>
        <h3 style={{ marginTop: 0 }}>Acesso pelo celular</h3>
        <div>Na mesma rede Wi-Fi, abra <b>{status?.local_url ?? "…"}</b>. Qualquer aparelho na rede consegue acessar; não há login.</div>
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0, color: "var(--bad)" }}>Perigo</h3>
        <button className="danger" onClick={() => setConfirm(true)} disabled={status?.job.state === "running"}>Regerar puzzles</button>
        <button className="danger" onClick={() => setConfirmAvoid(true)} disabled={status?.job.state === "running"}>Regerar só os evitar</button>
        <ErrorBox error={start.error} />
      </div>
      <Modal open={confirm} title="Regerar todos os puzzles?" onClose={() => setConfirm(false)}>
        <p>Isso apaga todos os puzzles e <b>todo o histórico de treino</b> (revisões, intervalos, sequência) e gera tudo de novo com os limiares atuais. Não pode ser desfeito.</p>
        <div className="row"><button className="danger" onClick={() => { start.mutate({ kind: "regenerate" }); setConfirm(false); }}>Regerar</button><button onClick={() => setConfirm(false)}>Cancelar</button></div>
      </Modal>
      <Modal open={confirmAvoid} title="Regerar só os puzzles 'evitar'?" onClose={() => setConfirmAvoid(false)}>
        <p>Apaga e regera só os puzzles "evitar" (e o histórico de treino deles). Os "punir" e seu histórico ficam.</p>
        <div className="row"><button className="danger" onClick={() => { start.mutate({ kind: "regenerate", avoidOnly: true }); setConfirmAvoid(false); }}>Regerar</button><button onClick={() => setConfirmAvoid(false)}>Cancelar</button></div>
      </Modal>
    </>
  );
}
