import { useState } from "react";
import { Link } from "react-router-dom";
import { Session } from "./Session";
import type { SessionConfig } from "./SessionStart";
import { SessionSummary, type Done } from "./SessionSummary";

/** A tela Revisar não tem escolha nenhuma: a fila de vencidos inteira, sem filtro e sem tempo. */
const novaConfig = (): SessionConfig => ({
  source: "own",
  mode: "review",
  filters: { mode: "review" },
  plannedMinutes: null,
  themes: [],
});

type Resumo = { done: Done[]; elapsedLabel: string; reason: string };

/** Links da fila vazia: revisar não tem o que oferecer, os novos e os estudos têm. */
function SemVencidos() {
  return (
    <div className="row">
      <Link to="/treinar?mode=new">Fazer novos</Link>
      <Link to="/estudos">Estudos</Link>
    </div>
  );
}

export function ReviewPage() {
  // `rodada` remonta a sessão ("Nova sessão" no resumo): a config nova sozinha não
  // basta, porque a sessão só recomeça do zero com uma `key` diferente
  const [rodada, setRodada] = useState(0);
  const [config, setConfig] = useState<SessionConfig>(novaConfig);
  const [summary, setSummary] = useState<Resumo | null>(null);
  const novaSessao = () => { setSummary(null); setConfig(novaConfig()); setRodada((n) => n + 1); };

  return (
    <>
      <h1>Revisar</h1>
      {summary
        ? <SessionSummary {...summary} onNew={novaSessao} />
        : <Session key={rodada} config={config} heading={false} emptyActions={<SemVencidos />}
          onFinish={(done, elapsedLabel, reason) => setSummary({ done, elapsedLabel, reason })} />}
    </>
  );
}
