import { Fragment, useContext, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Citacao, CoachExplanation, IssueOut, PuzzleOut } from "../api/types";
import { useCoachExplanation, useCoachStatus, useExplain } from "../api/queries";
import { PreviaContext } from "../analysis/previaContext";
import { TextoComLances } from "../analysis/TextoComLances";
import { ErrorBox } from "../components/ErrorBox";

const CITACAO = /\[c:([^\]\s]+)\]/g;
/** O lance que o verificador cita entre apóstrofos: `'Rf8' aparece no texto…`. */
const ENTRE_APOSTROFOS = /'([^']+)'/;

/** Quebra o texto em prosa e marcadores de citação, na ordem. */
export function segmentarCitacoes(texto: string): ({ kind: "texto"; text: string } | { kind: "citacao"; id: string })[] {
  const out: ({ kind: "texto"; text: string } | { kind: "citacao"; id: string })[] = [];
  let ultimo = 0;
  for (const m of texto.matchAll(CITACAO)) {
    const i = m.index ?? 0;
    if (i > ultimo) out.push({ kind: "texto", text: texto.slice(ultimo, i) });
    out.push({ kind: "citacao", id: m[1] });
    ultimo = i + m[0].length;
  }
  if (ultimo < texto.length) out.push({ kind: "texto", text: texto.slice(ultimo) });
  return out;
}

/**
 * As ressalvas do verificador prontas para ler: sem repetição (o mesmo `detalhe` vale
 * uma vez) e com os lances soltos numa linha só — o verificador aponta um por um, e dez
 * avisos iguais na frente do texto eram o que escondia a explicação.
 */
export function agruparIssues(issues: IssueOut[]): string[] {
  const vistos = new Set<string>();
  const linhas: string[] = [];
  const soltos: string[] = [];
  let lugarDosSoltos = -1;
  for (const i of issues) {
    if (vistos.has(i.detalhe)) continue;
    vistos.add(i.detalhe);
    if (i.tipo === "lance_sem_linha") {
      soltos.push(ENTRE_APOSTROFOS.exec(i.detalhe)?.[1] ?? i.detalhe);
      // a linha agrupada fica onde o primeiro aviso desse tipo apareceu
      if (lugarDosSoltos < 0) lugarDosSoltos = linhas.push("") - 1;
      continue;
    }
    linhas.push(i.detalhe);
  }
  if (lugarDosSoltos >= 0) linhas[lugarDosSoltos] = `Lances citados fora das linhas: ${soltos.join(", ")}`;
  return linhas;
}

/** Selo do verificador ao lado do título. Com ressalvas ou erros, elas ficam fechadas. */
function Selo({ exp }: { exp: CoachExplanation }) {
  const { issues } = exp.verification;
  const n = issues.length;
  const ok = exp.status === "ok";
  const rotulo = ok ? "verificado pela engine" : exp.status === "warnings" ? `com ressalvas (${n})` : `não verificado (${n})`;
  const classe = ok ? "ok" : exp.status === "warnings" ? "warn" : "bad";
  if (ok || n === 0) return <span className={`msg ${classe}`}>{rotulo}</span>;
  return (
    <details className="selo-ressalvas">
      <summary className={`msg ${classe}`}>{rotulo}</summary>
      <ul>
        {agruparIssues(issues).map((linha, i) => <li key={i}>{linha}</li>)}
      </ul>
    </details>
  );
}

function Rotulo({ children }: { children: ReactNode }) {
  return <div className="bloco-rotulo">{children}</div>;
}

const ESTILO_PROSA = { whiteSpace: "pre-wrap" as const, lineHeight: 1.5, margin: "2px 0 10px" };

/** Prosa do treinador: lances clicáveis (prévia no tabuleiro) e citações como links. */
function Prosa({ texto, fen, citacoes }: { texto: string; fen: string; citacoes: Citacao[] }) {
  const previa = useContext(PreviaContext);
  const porId = new Map(citacoes.map((c) => [c.chunk_id, c]));
  return (
    <p style={ESTILO_PROSA}>
      {segmentarCitacoes(texto).map((s, i) =>
        s.kind === "texto" ? (
          <TextoComLances key={i} texto={s.text} fen={fen} onPrevia={previa ?? (() => undefined)} />
        ) : (
          <Fragment key={i}>
            {porId.has(s.id)
              ? <Link to={porId.get(s.id)!.url} className="citacao" title={porId.get(s.id)!.caminho_san}>[{porId.get(s.id)!.estudo} › {porId.get(s.id)!.capitulo}]</Link>
              : null}
          </Fragment>
        ),
      )}
    </p>
  );
}

const usd = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/**
 * Cartão "Treinador": pede a explicação do erro ao backend e a mostra em blocos curtos
 * ("Na partida", "Por que", o padrão e o que treinar), lidos ao lado do tabuleiro, com os
 * lances clicáveis, as citações dos estudos como links e o selo do verificador no título.
 * Sem chave da API configurada, não aparece.
 */
export function CoachCard({ puzzle, reviewId }: { puzzle: PuzzleOut; reviewId?: string }) {
  const { data: status } = useCoachStatus();
  const configurado = !!status?.configured;
  const { data: existente, isLoading: carregando } = useCoachExplanation(puzzle.id, configurado);
  const explicar = useExplain();
  if (!configurado) return null;
  const exp = explicar.data ?? existente ?? null;
  const pedir = () => explicar.mutate({ puzzle_id: puzzle.id, review_id: reviewId });
  const pronto = exp && !explicar.isPending;
  const emBlocos = !!(pronto && (exp!.na_partida || exp!.por_que));
  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="row">
          <h3 style={{ margin: 0 }}>Treinador</h3>
          {pronto && <Selo exp={exp!} />}
        </div>
        {/* fora do ar enquanto a explicação já guardada não chegou: clicar aqui pediria
            uma explicação nova (e paga) para um exercício que talvez já tenha uma.
            Com explicação na tela, quem repete é o botão discreto do rodapé */}
        {!exp && !explicar.isPending && !carregando && (
          <button className="primary" onClick={pedir}>Explicar</button>
        )}
      </div>
      {explicar.isPending && <p className="muted">Pensando… leva de 10 a 40 s.</p>}
      {!!explicar.error && <ErrorBox error={explicar.error} />}
      {pronto && (
        <>
          {emBlocos ? (
            <>
              {exp!.na_partida && (
                <>
                  <Rotulo>Na partida</Rotulo>
                  <p style={ESTILO_PROSA}>{exp!.na_partida}</p>
                </>
              )}
              {exp!.por_que && (
                <>
                  <Rotulo>Por que</Rotulo>
                  <Prosa texto={exp!.por_que} fen={puzzle.fen_start} citacoes={exp!.citations} />
                </>
              )}
              {exp!.padrao && (
                <div style={{ marginBottom: 10 }}>
                  <Rotulo>Padrão</Rotulo>
                  <span className="tag">{exp!.padrao}</span>
                </div>
              )}
              {exp!.treinar.length > 0 && (
                <>
                  <Rotulo>Treinar</Rotulo>
                  <ul style={{ margin: "2px 0 10px 18px", padding: 0, lineHeight: 1.5 }}>
                    {exp!.treinar.map((t, i) => <li key={i}>{t}</li>)}
                  </ul>
                </>
              )}
            </>
          ) : (
            // explicação gravada antes dos blocos: o texto corrido, como era
            <Prosa texto={exp!.text} fen={puzzle.fen_start} citacoes={exp!.citations} />
          )}
          <small className="muted" style={{ display: "block" }}>
            {exp!.model} · US$ {usd.format(exp!.cost_usd)} · {Math.round(exp!.duration_ms / 1000)} s
            {exp!.repaired ? " · corrigida uma vez" : ""}
            {exp!.trace_url && <> · <a href={exp!.trace_url} target="_blank" rel="noopener noreferrer">trace</a></>}
            {status && status.index_chunks === 0 && " · sem estudos indexados (Configurações → Recriar índice)"}
            {" · "}
            <button style={{ minHeight: 28, padding: "0 10px" }} onClick={pedir}>Explicar de novo</button>
          </small>
        </>
      )}
    </div>
  );
}
