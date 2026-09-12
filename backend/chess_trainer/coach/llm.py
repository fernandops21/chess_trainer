"""Cliente LLM do treinador (spec §4.1).

`LlmClient` é a interface que o pipeline usa; `AnthropicClient` a implementa
com o SDK oficial e um loop de ferramentas explícito. A resposta final vem
por uma ferramenta (`entregar_explicacao`) com esquema estrito: o modelo a
chama quando termina, e o loop para. Erros do SDK viram `ErroDoTreinador`
com um código curto que a API traduz em mensagem."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from chess_trainer.coach.costs import Uso

FERRAMENTA_FINAL = "entregar_explicacao"
MAX_ITERACOES = 12
# teto por chamada: a resposta final traz texto longo, linhas e citações, e o raciocínio
# adaptativo entra no mesmo orçamento — com folga de menos que isso a entrega vem cortada
MAX_TOKENS_RESPOSTA = 16_000
# teto da explicação inteira (soma das chamadas), conferido aqui e em `explain.chamar`:
# tem de ficar acima do teto por chamada, senão uma entrega válida e já paga seria jogada fora
TETO_TOKENS_SAIDA = 20_000


class ErroDoTreinador(Exception):
    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


@dataclass(frozen=True)
class Ferramenta:
    nome: str
    descricao: str
    schema: dict
    fn: Callable[[dict], str]

    def definicao(self) -> dict:
        return {"name": self.nome, "description": self.descricao, "input_schema": self.schema}


@dataclass
class ChamadaFerramenta:
    nome: str
    entrada: dict
    resultado: str
    erro: bool = False


@dataclass
class ResultadoAgente:
    texto: str
    estruturado: dict | None
    uso: Uso
    chamadas: list[ChamadaFerramenta] = field(default_factory=list)
    stop_reason: str = "end_turn"
    model: str = ""
    n_chamadas_api: int = 0


class LlmClient(Protocol):
    model: str

    def run_agent(self, *, system: str, user: str, ferramentas: list[Ferramenta], esquema_final: dict,
                  effort: str, max_tokens: int = MAX_TOKENS_RESPOSTA) -> ResultadoAgente: ...


def executar_ferramenta(ferramentas: list[Ferramenta], nome: str, entrada: dict) -> ChamadaFerramenta:
    """Roda a ferramenta; qualquer exceção vira resultado de erro (o modelo lê e se ajusta)."""
    f = next((x for x in ferramentas if x.nome == nome), None)
    if f is None:
        return ChamadaFerramenta(nome, entrada, f"ferramenta desconhecida: {nome}", erro=True)
    try:
        return ChamadaFerramenta(nome, entrada, f.fn(entrada))
    except Exception as exc:  # noqa: BLE001 - o erro é devolvido ao modelo como texto
        return ChamadaFerramenta(nome, entrada, f"erro na ferramenta {nome}: {exc}", erro=True)


def _ferramenta_final(esquema: dict) -> dict:
    return {
        "name": FERRAMENTA_FINAL,
        "description": "Entrega a explicação final ao aluno. Chame exatamente uma vez, quando terminar.",
        "strict": True,
        "input_schema": esquema,
        "cache_control": {"type": "ephemeral"},
    }


class AnthropicClient:
    def __init__(self, api_key: str, model: str, client: Any = None):
        self.model = model
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
        self._client = client

    def _create(self, **kwargs):
        import anthropic

        try:
            return self._client.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise ErroDoTreinador("chave_recusada", "a chave da API foi recusada; confira em Configurações") from exc
        except anthropic.RateLimitError as exc:
            raise ErroDoTreinador("limite_de_uso", "limite de uso da API atingido; tente de novo em alguns minutos") from exc
        except anthropic.BadRequestError as exc:
            raise ErroDoTreinador("requisicao_invalida", f"a API recusou o pedido: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise ErroDoTreinador("erro_da_api", f"erro da API ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ErroDoTreinador("sem_conexao", "sem conexão com a API da Anthropic") from exc

    def run_agent(self, *, system: str, user: str, ferramentas: list[Ferramenta], esquema_final: dict,
                  effort: str, max_tokens: int = MAX_TOKENS_RESPOSTA) -> ResultadoAgente:
        tools = [f.definicao() for f in ferramentas] + [_ferramenta_final(esquema_final)]
        messages: list[dict] = [{"role": "user", "content": user}]
        uso = Uso()
        chamadas: list[ChamadaFerramenta] = []
        textos: list[str] = []
        estruturado: dict | None = None
        stop_reason = "end_turn"
        n = 0
        for _ in range(MAX_ITERACOES):
            resp = self._create(
                model=self.model, max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                tools=tools, thinking={"type": "adaptive"}, output_config={"effort": effort}, messages=messages,
            )
            n += 1
            u = resp.usage
            uso = uso + Uso(u.input_tokens, u.output_tokens, u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0)
            stop_reason = resp.stop_reason
            if uso.output_tokens > TETO_TOKENS_SAIDA:
                raise ErroDoTreinador("custo_excedido", "a explicação passou do teto de tokens e foi interrompida")
            if stop_reason == "refusal":
                raise ErroDoTreinador("recusa", "o modelo recusou responder a este pedido")
            # cortado no meio: sem a entrega final, o que sobrou não serve de explicação
            if stop_reason == "max_tokens" and not any(b.type == "tool_use" and b.name == FERRAMENTA_FINAL for b in resp.content):
                raise ErroDoTreinador("resposta_truncada", "a resposta passou do limite de tokens e foi cortada")
            textos.extend(b.text for b in resp.content if b.type == "text")
            usos = [b for b in resp.content if b.type == "tool_use"]
            if not usos:
                break
            messages.append({"role": "assistant", "content": resp.content})
            resultados = []
            for b in usos:
                entrada = dict(b.input) if isinstance(b.input, dict) else json.loads(b.input)
                if b.name == FERRAMENTA_FINAL:
                    estruturado = entrada
                    resultados.append({"type": "tool_result", "tool_use_id": b.id, "content": "ok"})
                    continue
                ch = executar_ferramenta(ferramentas, b.name, entrada)
                chamadas.append(ch)
                item = {"type": "tool_result", "tool_use_id": b.id, "content": ch.resultado}
                if ch.erro:
                    item["is_error"] = True
                resultados.append(item)
            messages.append({"role": "user", "content": resultados})
            if estruturado is not None:
                break
        return ResultadoAgente("\n".join(t for t in textos if t), estruturado, uso, chamadas, stop_reason, self.model, n)
