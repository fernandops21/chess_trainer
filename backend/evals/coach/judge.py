"""Nota pedagógica por LLM-as-judge (spec §8.2), com rubrica fixa em português."""
from __future__ import annotations

from chess_trainer.coach.llm import ErroDoTreinador, LlmClient

RUBRICA = """Você avalia a explicação de um treinador de xadrez para um aluno, sobre um erro dele.
Dê uma nota de 1 a 5 considerando, em ordem: (1) correção: os lances e avaliações batem com o
contexto e a engine; (2) clareza: um jogador de clube entende sem esforço; (3) foco: fala do erro
deste aluno nesta posição, não de generalidades; (4) ação: termina com o que treinar, concreto.
5 = tudo isso; 3 = correta mas genérica ou confusa; 1 = errada ou inútil. Entregue nota e uma
justificativa de uma frase pela ferramenta."""

ESQUEMA_NOTA = {"type": "object", "properties": {"nota": {"type": "integer", "minimum": 1, "maximum": 5}, "justificativa": {"type": "string"}},
                "required": ["nota", "justificativa"], "additionalProperties": False}


def julgar(llm: LlmClient, contexto_texto: str, explicacao: str) -> dict:
    """Nota do juiz; nota 0 com a justificativa dizendo o que houve quando ele falha.

    Falha do juiz não derruba o item da amostra: a avaliação roda dezenas de itens e a
    nota é só uma das métricas. `max_tokens` com folga — a nota é curta, mas o raciocínio
    sai do mesmo orçamento e uma resposta cortada viraria `resposta_truncada`."""
    try:
        r = llm.run_agent(system=RUBRICA, user=f"## Contexto do exercício\n{contexto_texto}\n\n## Explicação do treinador\n{explicacao}",
                          ferramentas=[], esquema_final=ESQUEMA_NOTA, effort="medium", max_tokens=4096)
    except ErroDoTreinador as exc:
        return {"nota": 0, "justificativa": f"juiz falhou: {exc.mensagem}"}
    est = r.estruturado or {"nota": 0, "justificativa": "o juiz não devolveu nota"}
    return {"nota": int(est.get("nota", 0)), "justificativa": str(est.get("justificativa", ""))}
