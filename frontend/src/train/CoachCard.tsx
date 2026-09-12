import { Fragment, useContext } from "react";
import { Link } from "react-router-dom";
import type { CoachExplanation, PuzzleOut } from "../api/types";
import { useCoachExplanation, useCoachStatus, useExplain } from "../api/queries";
import { PreviaContext } from "../analysis/previaContext";
import { TextoComLances } from "../analysis/TextoComLances";
import { ErrorBox } from "../components/ErrorBox";

const CITACAO = /\[c:([^\]\s]+)\]/g;

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

function Selo({ exp }: { exp: CoachExplanation }) {
  const { issues } = exp.verification;
  const rotulo = exp.status === "ok" ? "verificado pela engine" : exp.status === "warnings" ? "com ressalvas" : "não verificado";
  const classe = exp.status === "ok" ? "ok" : exp.status === "warnings" ? "warn" : "bad";
  return (
    <div>
      <span className={`msg ${classe}`}>{rotulo}</span>
      {issues.length > 0 && (
        <ul className="muted" style={{ margin: "6px 0 0 18px", padding: 0 }}>
          {issues.map((i, n) => <li key={n}>{i.detalhe}</li>)}
        </ul>
      )}
    </div>
  );
}

const usd = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/**
 * Cartão "Treinador": pede a explicação do erro ao backend e a mostra com os lances
 * clicáveis (prévia no tabuleiro grande), as citações dos estudos como links e o
 * selo do verificador. Sem chave da API configurada, não aparece.
 */
export function CoachCard({ puzzle, reviewId }: { puzzle: PuzzleOut; reviewId?: string }) {
  const { data: status } = useCoachStatus();
  const configurado = !!status?.configured;
  const { data: existente } = useCoachExplanation(puzzle.id, configurado);
  const explicar = useExplain();
  const previa = useContext(PreviaContext);
  if (!configurado) return null;
  const exp = explicar.data ?? existente ?? null;
  const pedir = () => explicar.mutate({ puzzle_id: puzzle.id, review_id: reviewId });
  const porId = new Map((exp?.citations ?? []).map((c) => [c.chunk_id, c]));
  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>Treinador</h3>
        {!explicar.isPending && (
          <button className={exp ? undefined : "primary"} onClick={pedir}>{exp ? "Explicar de novo" : "Explicar"}</button>
        )}
      </div>
      {status && status.index_chunks === 0 && (
        <div className="muted">Sem estudos indexados: a explicação não vai citar estudos (Configurações → Recriar índice).</div>
      )}
      {explicar.isPending && <p className="muted">Pensando… leva de 10 a 40 s.</p>}
      {!!explicar.error && <ErrorBox error={explicar.error} />}
      {exp && !explicar.isPending && (
        <>
          <Selo exp={exp} />
          <p style={{ whiteSpace: "pre-wrap" }}>
            {segmentarCitacoes(exp.text).map((s, i) =>
              s.kind === "texto" ? (
                <TextoComLances key={i} texto={s.text} fen={puzzle.fen_start} onPrevia={previa ?? (() => undefined)} />
              ) : (
                <Fragment key={i}>
                  {porId.has(s.id)
                    ? <Link to={porId.get(s.id)!.url} className="citacao" title={porId.get(s.id)!.caminho_san}>[{porId.get(s.id)!.estudo} › {porId.get(s.id)!.capitulo}]</Link>
                    : null}
                </Fragment>
              ),
            )}
          </p>
          <div className="muted">
            {exp.model} · US$ {usd.format(exp.cost_usd)} · {Math.round(exp.duration_ms / 1000)} s
            {exp.repaired ? " · corrigida uma vez" : ""}
            {exp.trace_url && <> · <a href={exp.trace_url} target="_blank" rel="noopener noreferrer">trace</a></>}
          </div>
        </>
      )}
    </div>
  );
}
