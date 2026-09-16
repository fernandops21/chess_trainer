import { Fragment, useContext, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Citacao, CoachExplanation, PuzzleOut } from "../api/types";
import { useCoachExplanation, useCoachStatus, useExplain } from "../api/queries";
import { PreviaContext } from "../analysis/previaContext";
import { TextoComLances } from "../analysis/TextoComLances";
import { ErrorBox } from "../components/ErrorBox";

const CITACAO = /\[c:([^\]\s]+)\]/g;
/** O que o cartão diz quando sobrou erro depois da correção: não há explicação para mostrar. */
const SEM_EXPLICACAO = "Não consegui uma explicação que passe na verificação da engine para este exercício.";

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
 * A explicação passou: sem `erro` depois da rodada de correção. Os avisos ficam no banco
 * e no log para a avaliação offline; para o aluno, ou a explicação foi verificada pela
 * engine ou não existe.
 */
function verificada(exp: CoachExplanation): boolean {
  return exp.status !== "errors";
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
 * lances clicáveis, as citações dos estudos como links e o selo "verificado pela engine"
 * no título. Explicação que não passou na verificação não aparece: o cartão diz isso e
 * oferece tentar de novo. Sem chave da API configurada, não aparece.
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
  const mostrar = !!(pronto && verificada(exp!));
  const emBlocos = !!(mostrar && (exp!.na_partida || exp!.por_que));
  const treinar = exp?.treinar ?? [];
  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <div className="row" style={{ alignItems: "baseline" }}>
          <h3 style={{ margin: 0 }}>Treinador</h3>
          {mostrar && <span className="msg ok">verificado pela engine</span>}
        </div>
        {/* fora do ar enquanto a explicação já guardada não chegou: clicar aqui pediria
            uma explicação nova (e paga) para um exercício que talvez já tenha uma.
            Com explicação na tela, quem repete é o botão discreto do rodapé */}
        {!exp && !explicar.isPending && !carregando && (
          <button className="primary" onClick={pedir}>Explicar</button>
        )}
      </div>
      {explicar.isPending && <p className="muted">Pensando… costuma levar cerca de um minuto.</p>}
      {!!explicar.error && <ErrorBox error={explicar.error} />}
      {pronto && (
        <>
          {!mostrar ? (
            // sobrou erro depois da correção: nada da explicação chega ao aluno
            <p style={ESTILO_PROSA}>{SEM_EXPLICACAO}</p>
          ) : emBlocos ? (
            <>
              {exp!.na_partida && (
                <>
                  <Rotulo>Na partida</Rotulo>
                  {/* o lance que o aluno jogou aparece aqui: também clicável */}
                  <Prosa texto={exp!.na_partida} fen={puzzle.fen_start} citacoes={exp!.citations} />
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
              {treinar.length > 0 && (
                <>
                  <Rotulo>Treinar</Rotulo>
                  <ul style={{ margin: "2px 0 10px 18px", padding: 0, lineHeight: 1.5 }}>
                    {treinar.map((t, i) => <li key={i}>{t}</li>)}
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
