import { useEffect, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { usePuzzleQuery } from "../api/queries";
import { ErrorBox } from "../components/ErrorBox";
import { configDoBloco } from "./bloco";
import { type Bloco, BlocoProvider, type ChegadaDoBloco } from "./BlocoContext";
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
  // a sessão que estava em andamento antes do cartão "Repetir o golpe" abrir o bloco:
  // "Voltar ao treino" a retoma depois do resumo, em vez de largar o usuário no início.
  // `undefined` é "não veio de um bloco" (não oferece o botão); `null` é um valor válido
  // (o bloco abriu direto da tela de início, sem sessão em andamento antes dele).
  const [configAntesDoBloco, setConfigAntesDoBloco] = useState<SessionConfig | null | undefined>(undefined);
  const restart = () => { setSummary(null); setTacticSummary(null); setConfig(null); setConfigAntesDoBloco(undefined); setVoltarPara(null); };
  const voltarAoBloco = () => {
    setTacticSummary(null);
    setConfig(configAntesDoBloco ?? null);
    setConfigAntesDoBloco(undefined);
  };
  // o cartão "Repetir o golpe" troca a configuração da sessão em andamento pela do
  // bloco de irmãos; a `key` força o remonte da `TacticSession` (sem ela, a troca de
  // config reaproveitaria a instância — e os refs de uma sessão já em curso — em vez
  // de começar a sessão do bloco do zero)
  const iniciar = (bloco: Bloco) => { setConfigAntesDoBloco(config); setConfig(configDoBloco(bloco)); };

  // o bloco aberto a partir de OUTRA tela (Revisar, exercício avulso) chega no estado da
  // navegação: começa direto nele e guarda para onde voltar. O estado é limpo em seguida, para
  // um F5 ou o "voltar" do navegador não reabrirem o mesmo bloco.
  const navegar = useNavigate();
  const onde = useLocation();
  const chegada = onde.state as ChegadaDoBloco | null;
  const [voltarPara, setVoltarPara] = useState<string | null>(null);
  useEffect(() => {
    if (!chegada?.bloco) return;
    setSummary(null);
    setTacticSummary(null);
    setConfigAntesDoBloco(undefined);
    setConfig(configDoBloco(chegada.bloco));
    setVoltarPara(chegada.voltarPara);
    navegar("/treinar", { replace: true, state: null });
  }, [chegada, navegar]);
  const voltarParaOrigem = voltarPara === null ? undefined : () => navegar(voltarPara);
  const rotuloDeVolta = voltarPara?.startsWith("/revisar") ? "Voltar à revisão" : voltarPara !== null ? "Voltar" : undefined;

  if (single && !chegada?.bloco) return <><h1>Treinar</h1><SingleTrain id={single} seen={params.get("seen") === "1"} /></>;

  let body;
  if (tacticSummary) body = <TacticSummary {...tacticSummary} onNew={restart} onVoltar={voltarParaOrigem ?? (configAntesDoBloco !== undefined ? voltarAoBloco : undefined)} voltarLabel={rotuloDeVolta} />;
  else if (summary) body = <SessionSummary {...summary} onNew={restart} />;
  else if (config?.source === "tactics") body = <TacticSession key={config.bloco ? `bloco-${config.bloco.anchorId}` : "tactics"} config={config} onFinish={setTacticSummary} />;
  else if (config) body = <Session config={config} onFinish={(done, elapsedLabel, reason) => setSummary({ done, elapsedLabel, reason })} />;
  else body = <SessionStart onStart={setConfig} />;

  return <BlocoProvider value={{ iniciar }}><h1>Treinar</h1>{body}</BlocoProvider>;
}
