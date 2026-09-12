from types import SimpleNamespace

import httpx
import pytest

from chess_trainer.coach.costs import Uso
from chess_trainer.coach.llm import (FERRAMENTA_FINAL, TETO_TOKENS_SAIDA, AnthropicClient, ErroDoTreinador,
                                     Ferramenta, executar_ferramenta)
from tests.fakes import FakeLlm

ESQUEMA = {"type": "object", "properties": {"texto": {"type": "string"}}, "required": ["texto"], "additionalProperties": False}


def soma(entrada: dict) -> str:
    return str(entrada["a"] + entrada["b"])


FERR = Ferramenta("somar", "Soma dois números.", {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                                                  "required": ["a", "b"], "additionalProperties": False}, soma)


def bloco_texto(t):
    return SimpleNamespace(type="text", text=t)


def bloco_tool(id_, name, inp):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=inp)


def resposta(content, stop_reason="tool_use", inp=100, out=20, cr=0, cw=0):
    return SimpleNamespace(content=content, stop_reason=stop_reason, stop_details=None,
                           usage=SimpleNamespace(input_tokens=inp, output_tokens=out, cache_read_input_tokens=cr, cache_creation_input_tokens=cw))


class ClienteFalso:
    """Dublê do `anthropic.Anthropic`: devolve as respostas na ordem e guarda os pedidos."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.pedidos = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.pedidos.append(kwargs)
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_executar_ferramenta_captura_erros():
    ok = executar_ferramenta([FERR], "somar", {"a": 2, "b": 3})
    assert ok.resultado == "5" and not ok.erro
    ruim = executar_ferramenta([FERR], "somar", {"a": 2})
    assert ruim.erro and "b" in ruim.resultado
    inexistente = executar_ferramenta([FERR], "nada", {})
    assert inexistente.erro and "desconhecida" in inexistente.resultado


def test_loop_chama_ferramenta_e_para_na_entrega():
    cliente = ClienteFalso([
        resposta([bloco_texto("vou somar"), bloco_tool("t1", "somar", {"a": 1, "b": 2})]),
        resposta([bloco_tool("t2", FERRAMENTA_FINAL, {"texto": "três"})], cr=500, cw=0),
    ])
    llm = AnthropicClient("sk", "claude-opus-5", client=cliente)
    r = llm.run_agent(system="S", user="U", ferramentas=[FERR], esquema_final=ESQUEMA, effort="medium")
    assert r.estruturado == {"texto": "três"} and r.texto == "vou somar"
    assert [c.nome for c in r.chamadas] == ["somar"] and r.chamadas[0].resultado == "3"
    assert r.uso == Uso(200, 40, 500, 0) and r.n_chamadas_api == 2 and r.model == "claude-opus-5"
    p = cliente.pedidos[0]
    assert p["model"] == "claude-opus-5" and p["output_config"] == {"effort": "medium"} and p["thinking"] == {"type": "adaptive"}
    assert p["system"][0]["cache_control"] == {"type": "ephemeral"} and p["tools"][-1]["name"] == FERRAMENTA_FINAL
    assert p["tools"][-1]["strict"] is True and p["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    # o segundo pedido carrega a resposta do assistente e o resultado da ferramenta
    seg = cliente.pedidos[1]["messages"]
    assert seg[1]["role"] == "assistant" and seg[2]["content"][0] == {"type": "tool_result", "tool_use_id": "t1", "content": "3"}


def test_fim_sem_entrega_devolve_texto_e_estruturado_nulo():
    cliente = ClienteFalso([resposta([bloco_texto("não sei")], stop_reason="end_turn")])
    r = AnthropicClient("sk", "claude-opus-5", client=cliente).run_agent(system="S", user="U", ferramentas=[], esquema_final=ESQUEMA, effort="high")
    assert r.estruturado is None and r.texto == "não sei" and r.stop_reason == "end_turn"


def test_ferramenta_com_erro_volta_como_is_error():
    cliente = ClienteFalso([
        resposta([bloco_tool("t1", "somar", {"a": 1})]),
        resposta([bloco_tool("t2", FERRAMENTA_FINAL, {"texto": "x"})]),
    ])
    AnthropicClient("sk", "claude-opus-5", client=cliente).run_agent(system="S", user="U", ferramentas=[FERR], esquema_final=ESQUEMA, effort="high")
    assert cliente.pedidos[1]["messages"][2]["content"][0]["is_error"] is True


def test_recusa_e_teto_de_tokens():
    cliente = ClienteFalso([resposta([], stop_reason="refusal")])
    with pytest.raises(ErroDoTreinador) as exc:
        AnthropicClient("sk", "claude-opus-5", client=cliente).run_agent(system="S", user="U", ferramentas=[], esquema_final=ESQUEMA, effort="high")
    assert exc.value.codigo == "recusa"
    cliente = ClienteFalso([resposta([bloco_tool("t1", "somar", {"a": 1, "b": 1})], out=TETO_TOKENS_SAIDA + 1)])
    with pytest.raises(ErroDoTreinador) as exc:
        AnthropicClient("sk", "claude-opus-5", client=cliente).run_agent(system="S", user="U", ferramentas=[FERR], esquema_final=ESQUEMA, effort="high")
    assert exc.value.codigo == "custo_excedido"


def test_erros_do_sdk_viram_codigos():
    import anthropic
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    def status(cls, code):
        return cls("x", response=httpx.Response(code, request=req), body=None)

    casos = [
        (status(anthropic.AuthenticationError, 401), "chave_recusada"),
        (status(anthropic.RateLimitError, 429), "limite_de_uso"),
        (status(anthropic.BadRequestError, 400), "requisicao_invalida"),
        (status(anthropic.InternalServerError, 500), "erro_da_api"),
        (anthropic.APIConnectionError(request=req), "sem_conexao"),
    ]
    for erro, codigo in casos:
        cliente = ClienteFalso([erro])
        with pytest.raises(ErroDoTreinador) as exc:
            AnthropicClient("sk", "claude-opus-5", client=cliente).run_agent(system="S", user="U", ferramentas=[], esquema_final=ESQUEMA, effort="high")
        assert exc.value.codigo == codigo, codigo


def test_fake_llm_segue_o_roteiro_e_executa_as_ferramentas():
    fake = FakeLlm([[("ferramenta", "somar", {"a": 4, "b": 5}), ("texto", "pensando"), ("final", {"texto": "nove"})]])
    r = fake.run_agent(system="S", user="U", ferramentas=[FERR], esquema_final=ESQUEMA, effort="low")
    assert r.estruturado == {"texto": "nove"} and r.chamadas[0].resultado == "9" and r.texto == "pensando"
    assert fake.prompts[0]["ferramentas"] == ["somar"] and fake.prompts[0]["effort"] == "low"
    with pytest.raises(AssertionError):
        fake.run_agent(system="S", user="U", ferramentas=[], esquema_final=ESQUEMA, effort="low")
