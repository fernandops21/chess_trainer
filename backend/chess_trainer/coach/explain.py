"""Pipeline da explicação (spec §7): contexto -> recuperação -> agente ->
verificação -> uma correção -> resultado. Não toca em banco: quem persiste é
`gravar`, o que permite rodar o mesmo pipeline na avaliação offline."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable

from chess_trainer.coach.costs import Uso, custo_usd
from chess_trainer.coach.llm import (FERRAMENTA_FINAL, TETO_TOKENS_SAIDA, ChamadaFerramenta, ErroDoTreinador,
                                     LlmClient)
from chess_trainer.coach.observability import NoopTracer, Tracer
from chess_trainer.coach.prompts import ESQUEMA_EXPLICACAO, PROMPT_VERSION, SYSTEM_PROMPT, mensagem_de_correcao, mensagem_inicial
from chess_trainer.coach.tools import ContextoExercicio, ferramentas_do_treinador
from chess_trainer.coach.verify import CITACAO_RE, Analisar, Verificacao, verificar
from chess_trainer.core.models import CoachExplanation

VARIANTES = ("prompt", "agente", "agente_rag")
FERRAMENTA_BUSCA = "buscar_estudos"
AVISO_RETENTATIVA = (
    f"\n\nSua resposta anterior não chegou pela ferramenta `{FERRAMENTA_FINAL}`. "
    f"Desta vez chame `{FERRAMENTA_FINAL}` com a explicação completa."
)


@dataclass(frozen=True)
class OpcoesExplicacao:
    variante: str = "agente_rag"
    effort: str = "high"
    k_trechos: int = 5


@dataclass
class ResultadoExplicacao:
    contexto: ContextoExercicio
    model: str
    prompt_version: str
    effort: str
    variante: str
    # prosa derivada dos blocos (`na_partida` + `por_que`), para o verificador e a avaliação
    texto: str
    estruturado: dict | None
    linhas: list[dict]
    citacoes: list[dict]
    verificacao: Verificacao
    status: str
    repaired: bool
    uso: Uso
    custo_usd: float
    duration_ms: int
    trace_id: str | None
    n_chamadas_api: int
    trechos: list[dict] = field(default_factory=list)


def consulta_de_busca(ctx: ContextoExercicio) -> str:
    partes = [ctx.tema, " ".join(ctx.solucao_san[:2])]
    if ctx.lance_errado:
        partes.append(f"erro {ctx.lance_errado['san']}")
    if ctx.partida:
        partes.append(ctx.partida.get("lances_em_volta", ""))
    return " ".join(p for p in partes if p).strip()


def _status(v: Verificacao) -> str:
    if not v.ok:
        return "errors"
    return "warnings" if v.issues else "ok"


def _trechos_das_ferramentas(chamadas: list[ChamadaFerramenta]) -> list[dict]:
    """Trechos que o próprio agente achou chamando `buscar_estudos`. Precisam entrar na lista
    recuperada: sem isso, citar um deles viraria `citacao_inexistente`. Resultado mal formado
    (a ferramenta devolve texto de erro, por exemplo) é simplesmente ignorado."""
    achados: list[dict] = []
    for c in chamadas:
        if c.nome != FERRAMENTA_BUSCA or c.erro:
            continue
        try:
            dados = json.loads(c.resultado)
        except (ValueError, TypeError):
            continue
        if not isinstance(dados, list):
            continue
        achados.extend(t for t in dados if isinstance(t, dict) and t.get("chunk_id"))
    return achados


def texto_da_resposta(estruturado: dict) -> str:
    """A prosa da resposta em blocos: `na_partida` e `por_que` colados. É o que o
    verificador confere, o que o juiz da avaliação lê e o que fica em `text` no banco."""
    partes = [str(estruturado.get(campo) or "").strip() for campo in ("na_partida", "por_que")]
    return "\n\n".join(p for p in partes if p)


def _verificar(estruturado: dict, ctx: ContextoExercicio, trechos: list[dict], analisar: Analisar) -> Verificacao:
    # o verificador trabalha com um `texto`: os blocos entram derivados nele
    estruturado = {**estruturado, "texto": texto_da_resposta(estruturado)}
    return verificar(estruturado, fen_inicial=ctx.fen_inicial, fen_erro=ctx.fen_erro,
                     lances_permitidos=set(ctx.lances_permitidos), trechos_ids={t["chunk_id"] for t in trechos}, analisar=analisar)


def explicar(*, contexto: ContextoExercicio, llm: LlmClient, analisar: Analisar,
             estatisticas: Callable[[int], list[dict]] | None, buscar: Callable[[str, int], list[dict]] | None,
             opcoes: OpcoesExplicacao, tracer: Tracer | None = None) -> ResultadoExplicacao:
    tracer = tracer or NoopTracer()
    if opcoes.variante not in VARIANTES:
        raise ValueError(f"variante desconhecida: {opcoes.variante}")
    inicio = time.monotonic()
    try:
        with tracer.span("coach.explain", puzzle_id=contexto.puzzle_id, variante=opcoes.variante, prompt_version=PROMPT_VERSION, model=llm.model):
            trace_id = tracer.trace_id()
            with tracer.span("contexto"):
                texto_ctx = contexto.texto()
            trechos: list[dict] = []
            if opcoes.variante == "agente_rag" and buscar is not None:
                with tracer.span("recuperacao"):
                    trechos = list(buscar(consulta_de_busca(contexto), opcoes.k_trechos))
            if opcoes.variante == "prompt":
                ferramentas = []
            else:
                ferramentas = ferramentas_do_treinador(contexto, analisar, estatisticas,
                                                       buscar if opcoes.variante == "agente_rag" else None)
            user = mensagem_inicial(texto_ctx, trechos)
            uso = Uso()
            n_api = 0

            def chamar(nome: str, mensagem: str):
                nonlocal uso, n_api
                with tracer.span(nome):
                    r = llm.run_agent(system=SYSTEM_PROMPT, user=mensagem, ferramentas=ferramentas,
                                      esquema_final=ESQUEMA_EXPLICACAO, effort=opcoes.effort)
                    uso = uso + r.uso
                    n_api += r.n_chamadas_api
                    tracer.geracao(nome, llm.model, r.uso, custo_usd(llm.model, r.uso), chamadas=[c.nome for c in r.chamadas])
                # o teto vale para a explicação inteira: o cliente só vê uma chamada, e
                # retentativa + correção podem somar bem mais do que cada uma por si
                if uso.output_tokens > TETO_TOKENS_SAIDA:
                    raise ErroDoTreinador("custo_excedido", "a explicação passou do teto de tokens e foi interrompida")
                # o que o agente buscou sozinho vale tanto quanto o que veio da recuperação
                ids = {t["chunk_id"] for t in trechos}
                for t in _trechos_das_ferramentas(r.chamadas):
                    if t["chunk_id"] not in ids:
                        ids.add(t["chunk_id"])
                        trechos.append(t)
                return r

            r1 = chamar("llm", user)
            if r1.estruturado is None:
                r1 = chamar("llm_retentativa", user + AVISO_RETENTATIVA)
                if r1.estruturado is None:
                    raise ErroDoTreinador("resposta_fora_do_esquema", "o modelo não entregou a explicação no formato esperado")
            with tracer.span("verificacao"):
                v1 = _verificar(r1.estruturado, contexto, trechos, analisar)
            escolhido, v, repaired = r1, v1, False
            if not v1.ok:
                r2 = chamar("correcao", user + mensagem_de_correcao(r1.estruturado, v1.to_dict()))
                if r2.estruturado is not None:
                    with tracer.span("verificacao_correcao"):
                        v2 = _verificar(r2.estruturado, contexto, trechos, analisar)
                    if v2.erros < v1.erros:
                        escolhido, v, repaired = r2, v2, True
            est = escolhido.estruturado or {}
            texto = texto_da_resposta(est)
            # a mesma união que o verificador usa: o campo `citacoes` e os marcadores [c:ID] do texto
            citadas = {str(c) for c in (est.get("citacoes") or [])} | set(CITACAO_RE.findall(texto))
            citacoes = [t for t in trechos if t["chunk_id"] in citadas]
            resultado = ResultadoExplicacao(
                contexto=contexto, model=llm.model, prompt_version=PROMPT_VERSION, effort=opcoes.effort, variante=opcoes.variante,
                texto=texto, estruturado=est, linhas=list(est.get("linhas") or []), citacoes=citacoes,
                verificacao=v, status=_status(v), repaired=repaired, uso=uso, custo_usd=custo_usd(llm.model, uso),
                duration_ms=int((time.monotonic() - inicio) * 1000), trace_id=trace_id, n_chamadas_api=n_api, trechos=trechos,
            )
    finally:
        tracer.flush()
    return resultado


def gravar(db, resultado: ResultadoExplicacao, review_id: str | None) -> CoachExplanation:
    """Guarda a explicação e apaga as anteriores do mesmo exercício (só a última fica)."""
    for antiga in db.query(CoachExplanation).filter_by(puzzle_id=resultado.contexto.puzzle_id).all():
        db.delete(antiga)
    row = CoachExplanation(
        puzzle_id=resultado.contexto.puzzle_id, review_id=review_id, model=resultado.model,
        prompt_version=resultado.prompt_version, effort=resultado.effort, variante=resultado.variante,
        text=resultado.texto, structured_json=json.dumps(resultado.estruturado or {}, ensure_ascii=False),
        lines_json=json.dumps(resultado.linhas, ensure_ascii=False),
        citations_json=json.dumps(resultado.citacoes, ensure_ascii=False),
        verification_json=json.dumps(resultado.verificacao.to_dict(), ensure_ascii=False),
        status=resultado.status, repaired=resultado.repaired,
        input_tokens=resultado.uso.input_tokens, output_tokens=resultado.uso.output_tokens,
        cache_read_tokens=resultado.uso.cache_read_tokens, cache_write_tokens=resultado.uso.cache_write_tokens,
        cost_usd=resultado.custo_usd, trace_id=resultado.trace_id, duration_ms=resultado.duration_ms,
    )
    db.add(row)
    db.commit()
    return row
