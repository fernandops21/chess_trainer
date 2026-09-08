import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { usePuzzleQuery } from "../api/queries";
import { ErrorBox } from "../components/ErrorBox";
import { Session, SessionPuzzle } from "./Session";
import { SessionStart, type SessionConfig } from "./SessionStart";
import { SessionSummary, type Done } from "./SessionSummary";
import { TacticSession, type TacticSummaryData } from "./TacticSession";
import { TacticSummary } from "./TacticSummary";

function SingleTrain({ id, seen }: { id: string; seen: boolean }) {
  const nav = useNavigate();
  // aberto direto pela URL não tem histórico para voltar: cai na tela de treino
  const back = () => (window.history.length > 1 ? nav(-1) : nav("/treinar"));
  const { data, error, isLoading } = usePuzzleQuery(id);
  if (isLoading) return <p className="muted">Carregando…</p>;
  if (error || !data) return <ErrorBox error={error ?? new Error("Puzzle não encontrado")} />;
  return <SessionPuzzle key={data.id} puzzle={data} sessionId={null} presetHint={seen} nextLabel="Voltar" onDone={back} />;
}

type OwnSummary = { done: Done[]; elapsedLabel: string; reason: string };

export function TrainPage() {
  const [params] = useSearchParams();
  const single = params.get("puzzle");
  const [config, setConfig] = useState<SessionConfig | null>(null);
  const [summary, setSummary] = useState<OwnSummary | null>(null);
  const [tacticSummary, setTacticSummary] = useState<TacticSummaryData | null>(null);
  const restart = () => { setSummary(null); setTacticSummary(null); setConfig(null); };

  if (single) return <><h1>Treinar</h1><SingleTrain id={single} seen={params.get("seen") === "1"} /></>;

  let body;
  if (tacticSummary) body = <TacticSummary {...tacticSummary} onNew={restart} />;
  else if (summary) body = <SessionSummary {...summary} onNew={restart} />;
  else if (config?.source === "tactics") body = <TacticSession config={config} onFinish={setTacticSummary} />;
  else if (config) body = <Session config={config} onFinish={(done, elapsedLabel, reason) => setSummary({ done, elapsedLabel, reason })} />;
  else body = <SessionStart onStart={setConfig} />;

  return <><h1>Treinar</h1>{body}</>;
}
