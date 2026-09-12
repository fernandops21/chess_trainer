"""Uma explicação de verdade contra a API (custa alguns centavos). Só roda com
`ANTHROPIC_API_KEY` no ambiente e `-m network`; fora do CI."""
import os

import pytest

from chess_trainer.coach.explain import OpcoesExplicacao, explicar
from chess_trainer.coach.llm import AnthropicClient
from chess_trainer.coach.tools import contexto_do_exercicio
from tests.test_coach_explain import analisar
from tests.test_coach_tools import puzzle_punir

pytestmark = pytest.mark.network


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="sem ANTHROPIC_API_KEY")
def test_explicacao_real_passa_no_verificador(db_session):
    ctx = contexto_do_exercicio(db_session, puzzle_punir(db_session))
    llm = AnthropicClient(os.environ["ANTHROPIC_API_KEY"], os.environ.get("COACH_MODEL", "claude-sonnet-5"))
    r = explicar(contexto=ctx, llm=llm, analisar=analisar, estatisticas=None, buscar=None,
                 opcoes=OpcoesExplicacao(variante="agente", effort="low"))
    print(r.texto, r.verificacao.to_dict(), r.custo_usd)
    assert r.estruturado is not None and 60 <= len(r.texto.split()) <= 400
    assert r.verificacao.erros == 0, r.verificacao.to_dict()
